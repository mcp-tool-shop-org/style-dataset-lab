#!/usr/bin/env bash
# Shared Colab window lifecycle, lock, live wall/cap/vitals/RAM guards, token scrubber, and EXIT trap.
#
# Bounded cleanup and salvage contract (every step runs under `timeout -k` in a subshell with
# default SIGTERM/SIGINT dispositions so a wedged child is killed by SIGKILL after the grace):
#   COLAB_KILL_GRACE_S_DEFAULT=10               (`timeout -k 10` SIGTERM->SIGKILL grace)
#   COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT=300        (5 min + 10 s -k = 310 s when bundle size is unknown)
#   COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT=180 (3 min + 10 s -k = 190 s on `colab restart-kernel`)
#   COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT=330    (330 s + 10 s -k = 340 s over bundle-now `--timeout 300`)
#   COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT=300 (5 min + 10 s -k = 310 s on salvage `colab download`)
#   SALVAGE_DEADLINE_S=840                      (190 + 340 + 310 = 840 s total salvage deadline;
#                                                past it, cleanup skips remaining salvage and runs `colab stop`)
#   COLAB_STOP_TIMEOUT_S_DEFAULT=60             (60 s + 10 s -k = 70 s per `colab stop` attempt)
#   COLAB_STOP_ATTEMPTS_DEFAULT=2               (1 retry -> 2 * 70 = 140 s worst-case stop bound)
#   COLAB_SESSIONS_TIMEOUT_S_DEFAULT=30         (30 s + 10 s -k = 40 s on closing `colab sessions`)
# Worst-case time from guard trip to `colab stop` attempted (`cleanup_stop_attempted_by_s`) and
# total cleanup bound through `colab stop` completion (`cleanup_bound_s`):
#   Lane 3 (train):  cleanup_stop_attempted_by_s = 840 s, cleanup_bound_s = 840 + 140 = 980 s
#   Lane 1 (render): cleanup_stop_attempted_by_s = 0 s,   cleanup_bound_s = 140 s
# Cap guard cleanup reserve (reserves cleanup_bound_s before the trip so total spend stays <= cap):
#   effective_trip = cap - margin - cleanup_reserve; cleanup_reserve = (cleanup_bound_s / 3600) * priced_rate
#   Refuses CAP_TOO_SMALL_FOR_CLEANUP before any colab call when effective_trip <= 0 or when
#   runtime_to_trip < --min-runtime-s; --dry prints the trip arithmetic and exits.
set -euo pipefail

COLAB_KILL_GRACE_S_DEFAULT=10
COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT=300
COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT=180
COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT=330
COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT=300
SALVAGE_DEADLINE_S_DEFAULT=840
COLAB_STOP_TIMEOUT_S_DEFAULT=60
COLAB_STOP_ATTEMPTS_DEFAULT=2
COLAB_SESSIONS_TIMEOUT_S_DEFAULT=30

export COLAB_KILL_GRACE_S="${COLAB_KILL_GRACE_S_DEFAULT}"
export COLAB_DOWNLOAD_TIMEOUT_S="${COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT}"
export COLAB_SALVAGE_RESTART_TIMEOUT_S="${COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT}"
export COLAB_SALVAGE_EXEC_TIMEOUT_S="${COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT}"
export COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S="${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT}"
export SALVAGE_DEADLINE_S="${SALVAGE_DEADLINE_S_DEFAULT}"
export COLAB_STOP_TIMEOUT_S="${COLAB_STOP_TIMEOUT_S_DEFAULT}"
export COLAB_STOP_ATTEMPTS="${COLAB_STOP_ATTEMPTS_DEFAULT}"
export COLAB_SESSIONS_TIMEOUT_S="${COLAB_SESSIONS_TIMEOUT_S_DEFAULT}"
COLAB_CLEANUP_SIGNAL_COUNT=0
COLAB_CLEANUP_SKIP_SALVAGE=0

# colab_apply_test_cleanup_overrides <test_mode>: in fake-colab test mode only, allow short per-step
# timeouts and salvage deadline so tests can exercise hung children and `timeout -k` in seconds.
colab_apply_test_cleanup_overrides() {
  local test_mode="$1"
  [ "${test_mode}" = "1" ] || return 0
  if [ -n "${SDLAB_TEST_KILL_GRACE_S:-}" ]; then
    export COLAB_KILL_GRACE_S="${SDLAB_TEST_KILL_GRACE_S}"
  fi
  if [ -n "${SDLAB_TEST_DOWNLOAD_TIMEOUT_S:-}" ]; then
    export COLAB_DOWNLOAD_TIMEOUT_S="${SDLAB_TEST_DOWNLOAD_TIMEOUT_S}"
    export COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S="${SDLAB_TEST_DOWNLOAD_TIMEOUT_S}"
  fi
  if [ -n "${SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S:-}" ]; then
    export COLAB_SALVAGE_RESTART_TIMEOUT_S="${SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S}"
  fi
  if [ -n "${SDLAB_TEST_SALVAGE_EXEC_TIMEOUT_S:-}" ]; then
    export COLAB_SALVAGE_EXEC_TIMEOUT_S="${SDLAB_TEST_SALVAGE_EXEC_TIMEOUT_S}"
  fi
  if [ -n "${SDLAB_TEST_STOP_TIMEOUT_S:-}" ]; then
    export COLAB_STOP_TIMEOUT_S="${SDLAB_TEST_STOP_TIMEOUT_S}"
  fi
  if [ -n "${SDLAB_TEST_SESSIONS_TIMEOUT_S:-}" ]; then
    export COLAB_SESSIONS_TIMEOUT_S="${SDLAB_TEST_SESSIONS_TIMEOUT_S}"
  fi
  local step_sum=$(( (COLAB_SALVAGE_RESTART_TIMEOUT_S + COLAB_KILL_GRACE_S) \
    + (COLAB_SALVAGE_EXEC_TIMEOUT_S + COLAB_KILL_GRACE_S) \
    + (COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S + COLAB_KILL_GRACE_S) ))
  if [ -n "${SDLAB_TEST_SALVAGE_DEADLINE_S:-}" ]; then
    export SALVAGE_DEADLINE_S="${SDLAB_TEST_SALVAGE_DEADLINE_S}"
  else
    export SALVAGE_DEADLINE_S="${step_sum}"
  fi
}

# colab_compute_cleanup_bounds <lane>: compute and export COLAB_CLEANUP_STOP_ATTEMPTED_BY_S and
# COLAB_CLEANUP_BOUND_S for <lane> ("train" = 840 s / 980 s default; "render" = 0 s / 140 s default)
# so the pre-open cap budget check, --dry, the live cap guard, and window.json all share one figure.
colab_compute_cleanup_bounds() {
  local lane="$1"
  local kill_grace_s="${COLAB_KILL_GRACE_S:-10}"
  local salvage_restart_s="${COLAB_SALVAGE_RESTART_TIMEOUT_S:-180}"
  local salvage_exec_s="${COLAB_SALVAGE_EXEC_TIMEOUT_S:-330}"
  local salvage_download_s="${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S:-300}"
  local salvage_steps_sum=$(( (salvage_restart_s + kill_grace_s) \
    + (salvage_exec_s + kill_grace_s) \
    + (salvage_download_s + kill_grace_s) ))
  local salvage_deadline_s="${SALVAGE_DEADLINE_S:-${salvage_steps_sum}}"
  local stop_timeout_s="${COLAB_STOP_TIMEOUT_S:-60}"
  local stop_attempts="${COLAB_STOP_ATTEMPTS:-2}"
  local stop_bound_s=$(( stop_attempts * (stop_timeout_s + kill_grace_s) ))
  local cleanup_stop_attempted_by_s=0
  if [ "${lane}" = "train" ]; then
    cleanup_stop_attempted_by_s="${salvage_steps_sum}"
    if [ "${salvage_deadline_s}" -lt "${cleanup_stop_attempted_by_s}" ]; then
      cleanup_stop_attempted_by_s="${salvage_deadline_s}"
    fi
  fi
  export COLAB_LANE="${lane}"
  export COLAB_CLEANUP_STOP_ATTEMPTED_BY_S="${cleanup_stop_attempted_by_s}"
  export COLAB_CLEANUP_BOUND_S=$(( cleanup_stop_attempted_by_s + stop_bound_s ))
}

# colab_run_bounded <timeout_s> <kill_grace_s> <cmd> [args...]: run a command under `timeout -k`
# in a subshell that resets TERM and INT to default dispositions (`trap - TERM INT`) before exec.
# Children never inherit SIG_IGN, so `timeout`'s initial SIGTERM can terminate well-behaved
# children and `timeout -k` sends SIGKILL after <kill_grace_s> if a child traps or ignores SIGTERM.
colab_run_bounded() {
  local timeout_s="$1"
  local kill_grace_s="$2"
  shift 2
  (
    trap - TERM INT
    exec timeout -k "${kill_grace_s}" "${timeout_s}" "$@" </dev/null
  )
}

# colab_rc_is_timeout <rc>: GNU `timeout` returns 124 when the command times out on SIGTERM and
# 137 (128 + 9) when `-k` escalates to SIGKILL.
colab_rc_is_timeout() {
  local rc="$1"
  [ "${rc}" -eq 124 ] || [ "${rc}" -eq 137 ]
}

# colab_on_cleanup_signal <out_dir>: trap handler installed during `cleanup_on_exit` instead of
# `trap '' TERM INT`. Because a shell function handles TERM/INT rather than ignoring them (`SIG_IGN`),
# child processes spawned from `cleanup_on_exit` inherit default signal dispositions (`SIG_DFL`) on
# exec, while a late TERM/INT from the independent wall watcher or operator does not abort cleanup
# before `colab stop`. A second signal sets COLAB_CLEANUP_SKIP_SALVAGE=1 so cleanup skips any
# remaining salvage step and goes straight to `colab stop`.
colab_on_cleanup_signal() {
  local out_dir="$1"
  COLAB_CLEANUP_SIGNAL_COUNT=$((COLAB_CLEANUP_SIGNAL_COUNT + 1))
  local action="continue_bounded_cleanup"
  if [ "${COLAB_CLEANUP_SIGNAL_COUNT}" -ge 2 ]; then
    COLAB_CLEANUP_SKIP_SALVAGE=1
    action="skip_remaining_salvage"
  fi
  if [ -n "${out_dir}" ] && [ -d "${out_dir}" ]; then
    printf 'CLEANUP_SIGNAL count=%s action=%s\n' "${COLAB_CLEANUP_SIGNAL_COUNT}" "${action}" >> "${out_dir}/guards.log"
  fi
}

# colab_enter_cleanup_trap <out_dir>: arm cleanup signal handling at the start of `cleanup_on_exit`.
colab_enter_cleanup_trap() {
  local out_dir="$1"
  trap - EXIT
  trap 'colab_on_cleanup_signal "'"${out_dir}"'"' TERM INT
}

colab_resolve_python() {
  if [ -n "${SDLAB_PYTHON:-}" ] && [ -x "${SDLAB_PYTHON}" ]; then
    echo "${SDLAB_PYTHON}"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  command -v python
}

colab_refuse_nonempty_out_dir() {
  local out_dir="$1"
  if [ -d "${out_dir}" ] && [ -n "$(ls -A "${out_dir}" 2>/dev/null)" ]; then
    echo "REFUSED: OUT_DIR_NOT_EMPTY: ${out_dir} already exists and is not empty" >&2
    return 97
  fi
}

# colab_refuse_logged <out_dir> <CODE> <message>: one refusal line, `REFUSED: <CODE>: <message>`,
# on stderr and (when the out dir exists) in guards.log, where window.json reads refusal codes.
colab_refuse_logged() {
  local out_dir="$1"
  local code="$2"
  shift 2
  local line="REFUSED: ${code}: $*"
  if [ -n "${out_dir}" ] && [ -d "${out_dir}" ]; then
    printf '%s\n' "${line}" >> "${out_dir}/guards.log"
  fi
  printf '%s\n' "${line}" >&2
}

# Fake-colab test mode: SDLAB_TEST_FAKE_COLAB=1 AND the `colab` on PATH carries the fake's
# #SDLAB_FAKE_COLAB_CLI=1 marker. The same gate preflight_resolve.sh uses for its test hooks.
colab_fake_test_mode_active() {
  [ "${SDLAB_TEST_FAKE_COLAB:-0}" = "1" ] || return 1
  local colab_bin
  colab_bin="$(command -v colab || true)"
  [ -n "${colab_bin}" ] && grep -q '^#SDLAB_FAKE_COLAB_CLI=1$' "${colab_bin}" 2>/dev/null
}

# colab_refuse_volatile_out_dir <out_dir> <test_mode>: the evidence of a paid window must survive a
# WSL VM restart, so a live run refuses an out dir on tmpfs/ramfs (filesystem type of the nearest
# existing ancestor, read with `stat -f`, and `findmnt` when present) or under /tmp, /var/tmp or
# /dev/shm (path prefix, for when the type cannot be read). Fake-colab tests use tmp dirs, so test
# mode is exempt.
colab_refuse_volatile_out_dir() {
  local out_dir="$1"
  local test_mode="$2"
  if [ "${test_mode}" = "1" ]; then
    return 0
  fi
  local abs
  abs="$(realpath -m -- "${out_dir}" 2>/dev/null || printf '%s' "${out_dir}")"
  local prefix
  for prefix in /tmp /var/tmp /dev/shm; do
    if [ "${abs}" = "${prefix}" ] || [ "${abs#"${prefix}"/}" != "${abs}" ]; then
      echo "REFUSED: OUT_DIR_VOLATILE: --out-dir ${abs} is under ${prefix}, which does not survive a WSL VM restart; use a directory on a persistent disk" >&2
      return 96
    fi
  done
  local probe="${abs}"
  while [ ! -e "${probe}" ] && [ "${probe}" != "/" ] && [ -n "${probe}" ]; do
    probe="$(dirname -- "${probe}")"
  done
  local fstypes=""
  fstypes="$(stat -f -c %T -- "${probe}" 2>/dev/null || true)"
  if command -v findmnt >/dev/null 2>&1; then
    fstypes="${fstypes} $(findmnt -n -o FSTYPE -T "${probe}" 2>/dev/null || true)"
  fi
  local fstype
  for fstype in ${fstypes}; do
    case "${fstype}" in
      tmpfs|ramfs)
        echo "REFUSED: OUT_DIR_VOLATILE: --out-dir ${abs} is on ${fstype} (checked at ${probe}), which does not survive a WSL VM restart; use a directory on a persistent disk" >&2
        return 96
        ;;
    esac
  done
}

# colab_refuse_live_pin_overrides <out_dir> <test_mode> <VAR>...: the EXPECTED_*_SHA overrides exist
# for the fake-colab suite only. In a live run any of them set is PIN_OVERRIDE_IN_LIVE_RUN.
colab_refuse_live_pin_overrides() {
  local out_dir="$1"
  local test_mode="$2"
  shift 2
  if [ "${test_mode}" = "1" ]; then
    return 0
  fi
  local set_vars=()
  local var
  for var in "$@"; do
    if [ -n "${!var:-}" ]; then
      set_vars+=("${var}")
    fi
  done
  if [ "${#set_vars[@]}" -gt 0 ]; then
    colab_refuse_logged "${out_dir}" PIN_OVERRIDE_IN_LIVE_RUN "${set_vars[*]} set without SDLAB_TEST_FAKE_COLAB=1 and the fake colab CLI on PATH"
    return 1
  fi
}

# The one remote directory that exists before the kit runs anything on the VM: the kernel's working
# directory. `colab upload` is a single Jupyter contents-API PUT of the file (google-colab-cli 0.7.4,
# colab_cli/contents.py upload/_request); it creates no parent directory, and a PUT into a missing
# one fails (HTTP 500 in window sdlab-l3-stub-3). So the kits upload flat into this directory and
# the remote script makes and fills its own subdirectories.
COLAB_REMOTE_ROOT="/content"

# _colab_http_status <cli output>: the HTTP status a failed contents-API call reported, or "none".
_colab_http_status() {
  local status=""
  status="$(grep -oE '\b[1-5][0-9]{2} (Client|Server) Error' <<< "$1" | head -n 1 | cut -d' ' -f1 || true)"
  if [ -z "${status}" ] && grep -q 'File or directory not found' <<< "$1"; then
    status="404"
  fi
  printf '%s' "${status:-none}"
}

# colab_upload_checked <session> <local> <remote> <out_dir>: upload one file into COLAB_REMOTE_ROOT.
# Refuses REMOTE_PARENT_UNVERIFIED (before any call) for a destination in any other directory, and
# UPLOAD_FAILED (keeping the HTTP status) when the CLI exits non-zero or does not print its success
# line. The CLI's own text, which can carry the session token in a URL, goes to colab.log only.
colab_upload_checked() {
  local session="$1"
  local src="$2"
  local dst="$3"
  local out_dir="$4"
  local parent="${dst%/*}"
  if [ "${parent}" != "${COLAB_REMOTE_ROOT}" ] || [ -z "${dst##*/}" ]; then
    colab_refuse_logged "${out_dir}" REMOTE_PARENT_UNVERIFIED "${dst}: the kit uploads only into ${COLAB_REMOTE_ROOT}, the one remote directory that exists before the remote script runs"
    return 1
  fi
  if [ ! -f "${src}" ]; then
    colab_refuse_logged "${out_dir}" UPLOAD_FAILED "${src} -> ${dst}: local file missing (http=none)"
    return 1
  fi
  local out=""
  local rc=0
  out="$(colab upload -s "${session}" "${src}" "${dst}" </dev/null 2>&1)" || rc=$?
  printf '%s\n' "${out}" >> "${out_dir}/colab.log"
  if [ "${rc}" -ne 0 ] || ! grep -Fq "[colab] Uploaded '" <<< "${out}"; then
    colab_refuse_logged "${out_dir}" UPLOAD_FAILED "${src} -> ${dst}: colab upload rc=${rc} http=$(_colab_http_status "${out}") (CLI output in colab.log)"
    return 1
  fi
}

# colab_download_checked <session> <remote> <local> <out_dir>: the CLI writes the local file with a
# plain open() and creates no local directory, so the local parent is checked first. Bounded by
# `timeout -k ${COLAB_KILL_GRACE_S} ${COLAB_DOWNLOAD_TIMEOUT_S}` (default 300 s + 10 s -k = 310 s
# when bundle size is unknown); logs `SALVAGE_STEP_TIMEOUT download` on timeout and refuses
# DOWNLOAD_FAILED (keeping the HTTP status; 404 when the remote file is missing).
colab_download_checked() {
  local session="$1"
  local src="$2"
  local dst="$3"
  local out_dir="$4"
  local dst_parent
  dst_parent="$(dirname -- "${dst}")"
  if [ ! -d "${dst_parent}" ]; then
    colab_refuse_logged "${out_dir}" DOWNLOAD_FAILED "${src} -> ${dst}: local directory ${dst_parent} does not exist (http=none)"
    return 1
  fi
  local dl_timeout="${COLAB_DOWNLOAD_TIMEOUT_S:-300}"
  local kill_grace="${COLAB_KILL_GRACE_S:-10}"
  local out=""
  local rc=0
  out="$(colab_run_bounded "${dl_timeout}" "${kill_grace}" colab download -s "${session}" "${src}" "${dst}" 2>&1)" || rc=$?
  printf '%s\n' "${out}" >> "${out_dir}/colab.log"
  if colab_rc_is_timeout "${rc}"; then
    echo "SALVAGE_STEP_TIMEOUT download timeout_s=${dl_timeout} kill_grace_s=${kill_grace} rc=${rc}" >> "${out_dir}/guards.log"
  fi
  if [ "${rc}" -ne 0 ] || ! grep -Fq "[colab] Downloaded '" <<< "${out}" || [ ! -s "${dst}" ]; then
    colab_refuse_logged "${out_dir}" DOWNLOAD_FAILED "${src} -> ${dst}: colab download rc=${rc} http=$(_colab_http_status "${out}") (CLI output in colab.log)"
    return 1
  fi
}

colab_guard_fake_cli_if_test() {
  local colab_bin
  colab_bin="$(command -v colab || true)"
  if [ -z "${colab_bin}" ]; then
    echo "REFUSED: colab CLI not found in PATH" >&2
    return 98
  fi
  if [ "${SDLAB_TEST_FAKE_COLAB:-0}" = "1" ]; then
    if ! grep -q "^#SDLAB_FAKE_COLAB_CLI=1$" "${colab_bin}" 2>/dev/null; then
      echo "REFUSED: REAL_COLAB_FORBIDDEN: colab resolved to ${colab_bin} without #SDLAB_FAKE_COLAB_CLI=1 marker" >&2
      return 99
    fi
  fi
}

colab_verify_input_shas() {
  local py_bin="$1"
  local guards_py="$2"
  shift 2
  local args=()
  for pair in "$@"; do
    args+=("--verify-sha" "${pair}")
  done
  "${py_bin}" "${guards_py}" "${args[@]}" </dev/null
}

colab_poll_usage_and_ram() {
  local py_bin="$1"
  local out_dir="$2"
  local fault_mode="${SDLAB_FAULT_POLL_HELPER:-}"
  if [ -f "${out_dir}/start_balance.txt" ] && [ -n "${SDLAB_FAULT_POLL_HELPER_MIDRUN:-}" ]; then
    fault_mode="${SDLAB_FAULT_POLL_HELPER_MIDRUN}"
  fi
  if [ "${fault_mode}" = "crash" ]; then
    return 137
  elif [ "${fault_mode}" = "empty" ]; then
    return 0
  elif [ "${fault_mode}" = "short" ]; then
    echo "9.85 9.85"
    return 0
  fi
  local default_rate="${RATE_CCU_PER_HOUR:-0.26}"
  local guards_py
  guards_py="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/launch_guards.py"

  local usage_text=""
  local usage_rc=0
  # Bounded: a hung `colab usage` cannot stretch a poll (or the live guard loop) past 30 s.
  usage_text="$(colab_run_bounded 30 5 colab usage 2>>"${out_dir}/colab.log")" || usage_rc=$?
  printf '%s\n' "${usage_text}" >> "${out_dir}/usage.log"

  "${py_bin}" - "${out_dir}" "${default_rate}" "${usage_rc}" "${usage_text}" "${guards_py}" "${COLAB_CARD_CLASS:?the kit must set COLAB_CARD_CLASS to gpu or cpu}" << 'PYEOF'
import os
import re
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
default_rate = float(sys.argv[2])
usage_rc = int(sys.argv[3])
raw_usage = sys.argv[4]
guards_py = Path(sys.argv[5])
card_class = sys.argv[6]

sys.path.insert(0, str(guards_py.parent))
import launch_guards as lg


def _read_float(p: Path) -> float | None:
    if not p.exists():
        return None
    try:
        return float(p.read_text(encoding="utf-8").strip())
    except Exception:
        return None


start_f = out_dir / "start_balance.txt"
end_f = out_dir / "end_balance.txt"
rate_f = out_dir / "rate_measured.txt"
rate_pre_f = out_dir / "rate_measured_pre_open.txt"
rate_post_f = out_dir / "rate_measured_post_open.txt"
rate_proj_f = out_dir / "rate_for_projection.txt"
rate_src_f = out_dir / "rate_source.txt"
err_f = out_dir / "usage_parse_error.txt"
opened_marker = out_dir / "session_opened.txt"

session_opened = opened_marker.exists()
existing_pre = _read_float(rate_pre_f)
existing_post = _read_float(rate_post_f)

rate_unread = False
try:
    parsed = lg.parse_usage_text(
        raw_usage,
        card_class,
        usage_rc=usage_rc,
        configured_rate=default_rate,
        session_opened=session_opened,
        post_open_rate=existing_post,
        pre_open_rate=existing_pre,
    )
except lg.RateUnread as exc:
    # A GPU window without a positive live rate. Before the open there is no window to price, so
    # only the balance and the pre-open reading are kept (projection 0). After the open it is
    # RATE_UNREAD: the post-open rate read treats it as "not yet" and polls again; the live cap
    # check refuses RATE_UNREAD. (Once a positive live rate has been read, parse_usage_text keeps
    # it, so a later reading of 0.00 never gets here.)
    part = exc.partial
    rate_unread = session_opened
    parsed = {
        "ok": True,
        "balance": part["balance"],
        "rate_measured": part["rate_measured"],
        "rate_measured_pre_open": part["rate_measured_pre_open"],
        "rate_measured_post_open": part["rate_measured_post_open"],
        "rate_for_projection": 0.0,
        "rate_source": "live_rate_unread" if session_opened else "pre_open_no_window",
        "error": None,
    }

if card_class == "gpu" and session_opened:
    import json as _json
    from datetime import datetime, timezone
    state_f = out_dir / "rate_window.json"
    try:
        state = _json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}
    except ValueError:
        state = {}
    max_rate = _read_float(out_dir / "max_rate.txt")
    if parsed.get("ok"):
        import time as _time
        state = lg.update_window_rate(state, account_rate=parsed.get("rate_measured"),
                                      pre_open_rate=existing_pre,
                                      at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                      epoch=_time.time(),
                                      assignments=lg.parse_active_assignments(raw_usage),
                                      min_gap_s=float(os.environ.get("COLAB_RATE_READ_INTERVAL_S", lg.RATE_STABLE_GAP_S)))
        state_f.write_text(_json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    if max_rate is not None:
        parsed["rate_for_projection"] = lg.gpu_projection_rate(state, max_rate)
        parsed["rate_source"] = "max_of_max_rate_and_stable_window"
        rate_unread = state.get("best_stable") is None and rate_unread

if parsed["ok"]:
    bal = parsed["balance"]
    if not start_f.exists():
        start_f.write_text(f"{bal}\n", encoding="utf-8", newline="\n")
    start_bal_str = start_f.read_text(encoding="utf-8").strip()
    end_f.write_text(f"{bal}\n", encoding="utf-8", newline="\n")
    cur_bal_str = f"{bal}"
    if parsed["rate_measured_pre_open"] is not None:
        rate_pre_f.write_text(f"{parsed['rate_measured_pre_open']}\n", encoding="utf-8", newline="\n")
    if parsed["rate_measured_post_open"] is not None:
        rate_post_f.write_text(f"{parsed['rate_measured_post_open']}\n", encoding="utf-8", newline="\n")
    if parsed["rate_measured_post_open"] is not None:
        rate_f.write_text(f"{parsed['rate_measured_post_open']}\n", encoding="utf-8", newline="\n")
    elif parsed["rate_measured_pre_open"] is not None:
        rate_f.write_text(f"{parsed['rate_measured_pre_open']}\n", encoding="utf-8", newline="\n")
    rate_proj_f.write_text(f"{parsed['rate_for_projection']}\n", encoding="utf-8", newline="\n")
    rate_src_f.write_text(f"{parsed['rate_source']}\n", encoding="utf-8", newline="\n")
    err_tok = "RATE_UNREAD" if rate_unread else "NONE"
else:
    err_msg = str(parsed["error"] or "COLAB_USAGE_PARSE_FAILED")
    err_f.write_text(f"{err_msg}\n", encoding="utf-8", newline="\n")
    if end_f.exists():
        end_f.unlink()
    start_bal_str = start_f.read_text(encoding="utf-8").strip() if start_f.exists() else "NONE"
    cur_bal_str = "NONE"
    rate_proj_f.write_text(f"{parsed['rate_for_projection']}\n", encoding="utf-8", newline="\n")
    rate_src_f.write_text(f"{parsed['rate_source']}\n", encoding="utf-8", newline="\n")
    err_tok = "COLAB_USAGE_PARSE_FAILED"

# The host-RAM reading is not taken here: the RAM check reads vitals.log itself
# (launch_guards.py --check-ram --ram-vitals-file, host_ram_status), so no default value can stand
# in for a VM reading.
print(f"{start_bal_str} {cur_bal_str} {parsed['rate_for_projection']} {err_tok}")
PYEOF
}

# colab_read_post_open_rate <py> <out_dir> <polls> <interval_s> <max_rate>: right after a GPU window
# opens, poll `colab usage` (the account's rate) until the window rate (post-open minus pre-open)
# is stable and at or above the floor (launch_guards.update_window_rate). None within <polls> polls
# is RATE_UNREAD; a stable window rate above <max_rate> is RATE_ABOVE_MAX. Both are refusals the
# caller ends the window on (the session is stopped by its EXIT trap, before any upload). Every
# reading is kept in rate_window.json and lands in window.json.
colab_read_post_open_rate() {
  local py_bin="$1"
  local out_dir="$2"
  local polls="$3"
  local interval_s="$4"
  local max_rate="$5"
  local guards_dir
  guards_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local i=0
  local decision="unread"
  while [ "${i}" -lt "${polls}" ]; do
    i=$((i + 1))
    colab_poll_usage_and_ram "${py_bin}" "${out_dir}" >/dev/null 2>&1 || true
    decision="$("${py_bin}" - "${guards_dir}" "${out_dir}" "${max_rate}" << 'PYEOF'
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import launch_guards as lg
f = Path(sys.argv[2]) / "rate_window.json"
state = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
print(lg.window_rate_decision(state, float(sys.argv[3])))
PYEOF
)"
    [ "${decision}" != "unread" ] && break
    [ "${i}" -lt "${polls}" ] && sleep "${interval_s}"
  done
  "${py_bin}" - "${out_dir}" "${max_rate}" "${i}" "${decision}" << 'PYEOF'
import json, sys
from pathlib import Path
out, max_rate, polls, decision = Path(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
f = out / "rate_window.json"
state = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
last = (state.get("readings") or [{}])[-1]
rec = {"decision": decision, "window_rate": state.get("best_stable"), "account_rate": last.get("account_rate"),
       "pre_open_rate": last.get("pre_open_rate"), "max_rate": max_rate, "floor": state.get("floor"),
       "polls": polls, "priced_at": max(max_rate, state.get("best_stable") or 0.0)}
(out / "rate_check.json").write_text(json.dumps(rec) + "\n", encoding="utf-8")
PYEOF
  if [ "${decision}" = "assignments_unreadable" ]; then
    colab_refuse_logged "${out_dir}" ASSIGNMENTS_UNREADABLE "colab usage gave no readable Active assignments count (missing or 0) on 3 consecutive reads (rate_window.json)"
    return 1
  fi
  if [ "${decision}" = "unread" ]; then
    colab_refuse_logged "${out_dir}" RATE_UNREAD "no stable window rate at or above the GPU floor in ${i} polls after open; the window is not run on a configured or CPU rate"
    return 1
  fi
  echo "RATE_READ $(cat "${out_dir}/rate_check.json")" >> "${out_dir}/guards.log"
  if [ "${decision}" = "above_max" ]; then
    colab_refuse_logged "${out_dir}" RATE_ABOVE_MAX "the window's stable rate is above --max-rate ${max_rate}/h (rate_check.json)"
    return 1
  fi
}

# colab_midrun_rate_check <py> <out_dir>: on a GPU window, every live cycle re-reads the rate (the
# cap check's own poll); a stable window rate that has risen above --max-rate is RATE_ABOVE_MAX.
colab_midrun_rate_check() {
  local py_bin="$1"
  local out_dir="$2"
  [ "${COLAB_CARD_CLASS:-}" = "gpu" ] && [ -f "${out_dir}/max_rate.txt" ] && [ -f "${out_dir}/rate_window.json" ] || return 0
  local guards_dir
  guards_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local decision
  decision="$("${py_bin}" - "${guards_dir}" "${out_dir}" << 'PYEOF'
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import launch_guards as lg
out = Path(sys.argv[2])
state = json.loads((out / "rate_window.json").read_text(encoding="utf-8"))
print(lg.window_rate_decision(state, float((out / "max_rate.txt").read_text(encoding="utf-8").strip())))
PYEOF
)"
  if [ "${decision}" = "assignments_unreadable" ]; then
    colab_refuse_logged "${out_dir}" ASSIGNMENTS_UNREADABLE "mid-run: 3 consecutive bad reads: no readable Active assignments count (missing or 0), or a stable window rate below the floor (rate_window.json)"
    return 1
  fi
  if [ "${decision}" = "above_max" ]; then
    colab_refuse_logged "${out_dir}" RATE_ABOVE_MAX "mid-run: the window's stable rate rose above --max-rate $(cat "${out_dir}/max_rate.txt")/h (rate_window.json)"
    return 1
  fi
}

colab_check_cap_and_ram() {
  local py_bin="$1"
  local guards_py="$2"
  local mode="$3"
  local elapsed_s="$4"
  local wall_s="$5"
  local grace_s="$6"
  local cap="$7"
  local margin="$8"
  local out_dir="$9"

  local metrics=""
  local poll_rc=0
  metrics="$(colab_poll_usage_and_ram "${py_bin}" "${out_dir}")" || poll_rc=$?
  local start_bal="" cur_bal="" rate_val="" err_tok=""
  if [ "${poll_rc}" -ne 0 ]; then
    err_tok="COLAB_USAGE_PARSE_FAILED"
    printf 'COLAB_USAGE_PARSE_FAILED: usage poll helper exited with status %s\n' "${poll_rc}" > "${out_dir}/usage_parse_error.txt"
  else
    read -r start_bal cur_bal rate_val err_tok <<< "${metrics}"
    if [ -z "${metrics}" ] || [ -z "${start_bal}" ] || [ -z "${cur_bal}" ] || [ -z "${rate_val}" ] || [ -z "${err_tok}" ] || [ "${start_bal}" = "NONE" ] || [ "${cur_bal}" = "NONE" ]; then
      err_tok="COLAB_USAGE_PARSE_FAILED"
      if [ ! -s "${out_dir}/usage_parse_error.txt" ]; then
        printf 'COLAB_USAGE_PARSE_FAILED: incomplete or missing usage metrics (%s)\n' "${metrics}" > "${out_dir}/usage_parse_error.txt"
      fi
    fi
  fi

  local guard_args=(
    "--mode" "${mode}"
    "--elapsed-s" "${elapsed_s}"
    "--wall-s" "${wall_s}"
    "--grace-s" "${grace_s}"
    "--cap" "${cap}"
    "--margin" "${margin}"
    "--cleanup-bound-s" "${COLAB_CLEANUP_BOUND_S:-0}"
    "--rate" "${rate_val:-0.26}"
  )
  if [ "${start_bal}" != "NONE" ] && [ -n "${start_bal}" ]; then
    guard_args+=("--start-balance" "${start_bal}")
  fi
  if [ "${cur_bal}" != "NONE" ] && [ -n "${cur_bal}" ]; then
    guard_args+=("--current-balance" "${cur_bal}")
  fi
  if [ "${err_tok}" = "RATE_UNREAD" ]; then
    colab_refuse_logged "${out_dir}" RATE_UNREAD "a GPU window has no positive live post-open rate; it is not priced with a configured rate"
    return 1
  fi
  if [ "${err_tok}" != "NONE" ] && [ -n "${err_tok}" ]; then
    local err_detail="${err_tok}"
    if [ -f "${out_dir}/usage_parse_error.txt" ]; then
      err_detail="$(cat "${out_dir}/usage_parse_error.txt")"
    fi
    guard_args+=("--usage-parse-error" "${err_detail}")
  fi

  # Every guard trip below is a named refusal (REFUSED: <CODE>: <why> in guards.log, where
  # window.json reads refusal_code and why), and its record, with the numbers that tripped it,
  # goes to guards.log first. A trip used to leave refusal_code null: the wall/cap record had no
  # REFUSED line, and the RAM guard's message went to stderr only.
  local guard_rc=0 guard_out=""
  guard_out="$("${py_bin}" "${guards_py}" "${guard_args[@]}" </dev/null)" || guard_rc=$?
  [ -n "${guard_out}" ] && printf '%s\n' "${guard_out}" >> "${out_dir}/guards.log"
  if [ "${mode}" = "live" ] && ! colab_midrun_rate_check "${py_bin}" "${out_dir}"; then
    return 1
  fi
  if [ "${guard_rc}" -ne 0 ]; then
    colab_refuse_from_guard_record "${py_bin}" "${out_dir}" "${guard_out}" GUARD_FAILED
    return 1
  fi

  # Private memory from the newest complete vitals sample (or the one before it); no vitals yet is
  # a skipped check, never a default. Two samples with no complete one is HOST_RAM_UNREADABLE.
  local ram_args=(
    "--check-ram"
    "--projected-delta-mb" "${PROJECTED_DELTA_MB:-2048}"
    "--ram-vitals-file" "${out_dir}/vitals.log"
  )
  local ram_rc=0 ram_out=""
  ram_out="$("${py_bin}" "${guards_py}" "${ram_args[@]}" </dev/null)" || ram_rc=$?
  [ -n "${ram_out}" ] && printf '%s\n' "${ram_out}" >> "${out_dir}/guards.log"
  if [ "${ram_rc}" -ne 0 ]; then
    colab_refuse_from_guard_record "${py_bin}" "${out_dir}" "${ram_out}" GUARD_FAILED
    return "${ram_rc}"
  fi
}

# colab_refuse_from_guard_record <py> <out_dir> <guard stdout> <fallback CODE>: a guard that exited
# non-zero names its refusal in its JSON record (`refusal: {code, why}`); log it with
# colab_refuse_logged. A guard that crashed before printing one is refused under <fallback CODE>.
colab_refuse_from_guard_record() {
  local py_bin="$1"
  local out_dir="$2"
  local record="$3"
  local fallback="$4"
  local parsed=""
  parsed="$(printf '%s' "${record}" | "${py_bin}" -c '
import json, sys
code, why = "", ""
for line in reversed(sys.stdin.read().splitlines()):
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    ref = rec.get("refusal") if isinstance(rec, dict) else None
    if isinstance(ref, dict) and ref.get("code"):
        code, why = str(ref["code"]), " ".join(str(ref.get("why") or "").split())
        break
print(code + "\t" + why)
' 2>/dev/null || true)"
  local code="${parsed%%$'\t'*}"
  local why="${parsed#*$'\t'}"
  if [ -z "${code}" ] || [ "${parsed}" = "${code}" ]; then
    code="${fallback}"
    why="the guard exited non-zero without a refusal record (its stderr is in the launcher output)"
  fi
  colab_refuse_logged "${out_dir}" "${code}" "${why}"
}

colab_run_exec_with_live_guards() {
  local py_bin="$1"
  local guards_py="$2"
  local session="$3"
  local runner_py="$4"
  local start_epoch="$5"
  local wall_s="$6"
  local grace_s="$7"
  local cap="$8"
  local margin="$9"
  local out_dir="${10}"
  shift 10
  local env_pairs=("$@")

  local poll_s="${GUARD_POLL_INTERVAL_S:-2}"
  local stall_s="${STALL_S:-300}"
  local setup_stall_s="${SETUP_STALL_S:-600}"
  local last_size=0
  local last_progress_epoch
  last_progress_epoch="$(date -u +%s)"
  local last_setup_bytes=0
  local last_setup_progress_epoch="${last_progress_epoch}"

  local wall_int="${wall_s%.*}"
  local grace_int="${grace_s%.*}"
  local exec_timeout="$(( wall_int + grace_int + 60 ))"

  local exec_args=("-s" "${session}" "-f" "${runner_py}" "--timeout" "${exec_timeout}")
  for kv in "${env_pairs[@]}"; do
    exec_args+=("--env" "${kv}")
  done

  colab exec "${exec_args[@]}" </dev/null > "${out_dir}/vitals.log" 2>&1 &
  EXEC_PID="$!"

  while kill -0 "${EXEC_PID}" 2>/dev/null; do
    sleep "${poll_s}"
    if ! kill -0 "${EXEC_PID}" 2>/dev/null; then
      break
    fi
    local now_epoch elapsed_s cur_size idle_s cur_setup_bytes setup_idle_s run_only_bytes
    now_epoch="$(date -u +%s)"
    elapsed_s="$((now_epoch - start_epoch))"

    local check_rc=0
    colab_check_cap_and_ram "${py_bin}" "${guards_py}" "live" "${elapsed_s}" "${wall_s}" "${grace_s}" "${cap}" "${margin}" "${out_dir}" || check_rc=$?
    if [ "${check_rc}" -ne 0 ]; then
      pkill -P "${EXEC_PID}" 2>/dev/null || true
      kill -9 "${EXEC_PID}" 2>/dev/null || true
      wait "${EXEC_PID}" 2>/dev/null || true
      EXEC_PID=""
      return 91
    fi

    # Run output only: every vitals line the emitters print is skipped (launch_guards.VITALS_LINE_PREFIXES,
    # one list, checked against the emitters by tests), so vitals blocks never count as progress.
    run_only_bytes="$("${py_bin}" "${guards_py}" --run-output-bytes "${out_dir}/vitals.log" </dev/null 2>/dev/null || echo 0)"
    cur_size="${run_only_bytes:-0}"
    if [ "${cur_size:-0}" != "${last_size}" ]; then
      last_size="${cur_size:-0}"
      last_progress_epoch="${now_epoch}"
    fi
    idle_s="$((now_epoch - last_progress_epoch))"

    cur_setup_bytes="$(grep -E '^SETUP_BYTES:[[:space:]]*[0-9]+[[:space:]]*$' "${out_dir}/vitals.log" 2>/dev/null | tail -n 1 | awk -F: '{gsub(/[[:space:]]/, "", $2); print $2}' || true)"
    if [ -n "${cur_setup_bytes}" ] && [ "${cur_setup_bytes}" != "${last_setup_bytes}" ]; then
      last_setup_bytes="${cur_setup_bytes}"
      last_setup_progress_epoch="${now_epoch}"
    fi
    setup_idle_s="$((now_epoch - last_setup_progress_epoch))"

    local vitals_rc=0 vitals_out=""
    vitals_out="$("${py_bin}" "${guards_py}" \
      --vitals-file "${out_dir}/vitals.log" \
      --idle-seconds "${idle_s}" \
      --setup-idle-seconds "${setup_idle_s}" \
      --stall-s "${stall_s}" \
      --setup-stall-s "${setup_stall_s}" </dev/null)" || vitals_rc=$?
    [ -n "${vitals_out}" ] && printf '%s\n' "${vitals_out}" >> "${out_dir}/guards.log"
    if [ "${vitals_rc}" -ne 0 ]; then
      colab_refuse_from_guard_record "${py_bin}" "${out_dir}" "${vitals_out}" GUARD_FAILED
      pkill -P "${EXEC_PID}" 2>/dev/null || true
      kill -9 "${EXEC_PID}" 2>/dev/null || true
      wait "${EXEC_PID}" 2>/dev/null || true
      EXEC_PID=""
      return 93
    fi
  done

  local exec_rc=0
  wait "${EXEC_PID}" || exec_rc=$?
  EXEC_PID=""

  colab_scrub_all_logs "${py_bin}" "${guards_py}" "${out_dir}"

  local marker_line=""
  marker_line="$(grep -E '^SDLAB_REMOTE_RC=-?[0-9]+$' "${out_dir}/vitals.log" 2>/dev/null | tail -n 1 | tr -d '\r' || true)"
  if [ -z "${marker_line}" ]; then
    echo "REFUSED: SDLAB_REMOTE_RC marker missing from vitals.log (colab exec_rc=${exec_rc})" >> "${out_dir}/guards.log"
    if [ "${exec_rc}" -ne 0 ]; then
      return "${exec_rc}"
    fi
    return 94
  fi
  local remote_rc="${marker_line#SDLAB_REMOTE_RC=}"
  if [ "${remote_rc}" -ne 0 ]; then
    echo "REFUSED: remote runner reported SDLAB_REMOTE_RC=${remote_rc}" >> "${out_dir}/guards.log"
    return "${remote_rc}"
  fi

  local final_vitals_rc=0 final_vitals_out=""
  final_vitals_out="$("${py_bin}" "${guards_py}" --vitals-file "${out_dir}/vitals.log" --idle-seconds 0 --setup-idle-seconds 0 --stall-s "${stall_s}" --setup-stall-s "${setup_stall_s}" </dev/null)" || final_vitals_rc=$?
  [ -n "${final_vitals_out}" ] && printf '%s\n' "${final_vitals_out}" >> "${out_dir}/guards.log"
  if [ "${final_vitals_rc}" -ne 0 ]; then
    colab_refuse_from_guard_record "${py_bin}" "${out_dir}" "${final_vitals_out}" GUARD_FAILED
    return 93
  fi
  local end_epoch elapsed_final
  end_epoch="$(date -u +%s)"
  elapsed_final="$((end_epoch - start_epoch))"
  colab_check_cap_and_ram "${py_bin}" "${guards_py}" "live" "${elapsed_final}" "${wall_s}" "${grace_s}" "${cap}" "${margin}" "${out_dir}"
}

# colab_salvage_bundle_after_failure <session> <bundle_now_py> <remote_path> <local_dst> <out_dir> <failed_rc>:
# bounded post-failure salvage under SALVAGE_DEADLINE_S (default 840 s = 190 + 340 + 310):
#   1. `colab restart-kernel` under `timeout -k ${COLAB_KILL_GRACE_S} ${COLAB_SALVAGE_RESTART_TIMEOUT_S}` (180 s + 10 s -k)
#   2. bundle-now `colab exec --timeout 300` under `timeout -k ${COLAB_KILL_GRACE_S} ${COLAB_SALVAGE_EXEC_TIMEOUT_S}` (330 s + 10 s -k)
#   3. `colab download` under `timeout -k ${COLAB_KILL_GRACE_S} ${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S}` (300 s + 10 s -k)
# Past SALVAGE_DEADLINE_S (or when a second cleanup signal sets COLAB_CLEANUP_SKIP_SALVAGE=1),
# remaining salvage steps are skipped (`SALVAGE_DEADLINE_EXCEEDED <step>` in guards.log) so cleanup
# goes straight to `colab stop`. Every step timeout is logged as `SALVAGE_STEP_TIMEOUT <step>` in
# guards.log. Nothing here writes a REFUSED line, so the window's refusal stays the one that stopped the run.
colab_salvage_bundle_after_failure() {
  local session="$1"
  local bundle_now_py="$2"
  local remote_path="$3"
  local local_dst="$4"
  local out_dir="$5"
  local failed_rc="$6"

  local kill_grace="${COLAB_KILL_GRACE_S:-10}"
  local restart_t="${COLAB_SALVAGE_RESTART_TIMEOUT_S:-180}"
  local exec_t="${COLAB_SALVAGE_EXEC_TIMEOUT_S:-330}"
  local dl_t="${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S:-300}"
  local deadline_s="${SALVAGE_DEADLINE_S:-840}"
  local start_epoch
  start_epoch="$(date -u +%s)"

  local now_epoch elapsed_s remaining_s step_t
  now_epoch="$(date -u +%s)"
  elapsed_s=$((now_epoch - start_epoch))
  if [ "${COLAB_CLEANUP_SKIP_SALVAGE:-0}" = "1" ] || [ "${elapsed_s}" -ge "${deadline_s}" ]; then
    echo "SALVAGE_DEADLINE_EXCEEDED restart-kernel elapsed_s=${elapsed_s} deadline_s=${deadline_s}" >> "${out_dir}/guards.log"
  else
    remaining_s=$((deadline_s - elapsed_s))
    step_t="${restart_t}"
    [ "${remaining_s}" -lt "${step_t}" ] && step_t="${remaining_s}"
    local restart_rc=0
    colab_run_bounded "${step_t}" "${kill_grace}" colab restart-kernel -s "${session}" >> "${out_dir}/bundle_now.log" 2>&1 || restart_rc=$?
    if colab_rc_is_timeout "${restart_rc}"; then
      echo "SALVAGE_STEP_TIMEOUT restart-kernel timeout_s=${step_t} kill_grace_s=${kill_grace} rc=${restart_rc}" >> "${out_dir}/guards.log"
    fi
  fi

  now_epoch="$(date -u +%s)"
  elapsed_s=$((now_epoch - start_epoch))
  if [ "${COLAB_CLEANUP_SKIP_SALVAGE:-0}" = "1" ] || [ "${elapsed_s}" -ge "${deadline_s}" ]; then
    echo "SALVAGE_DEADLINE_EXCEEDED bundle-now elapsed_s=${elapsed_s} deadline_s=${deadline_s}" >> "${out_dir}/guards.log"
  else
    remaining_s=$((deadline_s - elapsed_s))
    step_t="${exec_t}"
    [ "${remaining_s}" -lt "${step_t}" ] && step_t="${remaining_s}"
    local exec_rc=0
    colab_run_bounded "${step_t}" "${kill_grace}" colab exec -s "${session}" -f "${bundle_now_py}" --timeout 300 \
      --env "SDLAB_CONTENT=/content" --env "SDLAB_BUNDLE_RC=${failed_rc}" >> "${out_dir}/bundle_now.log" 2>&1 || exec_rc=$?
    if colab_rc_is_timeout "${exec_rc}"; then
      echo "SALVAGE_STEP_TIMEOUT bundle-now timeout_s=${step_t} kill_grace_s=${kill_grace} rc=${exec_rc}" >> "${out_dir}/guards.log"
    fi
  fi

  local dl_out=""
  local dl_rc=0
  now_epoch="$(date -u +%s)"
  elapsed_s=$((now_epoch - start_epoch))
  if [ "${COLAB_CLEANUP_SKIP_SALVAGE:-0}" = "1" ] || [ "${elapsed_s}" -ge "${deadline_s}" ]; then
    echo "SALVAGE_DEADLINE_EXCEEDED download elapsed_s=${elapsed_s} deadline_s=${deadline_s}" >> "${out_dir}/guards.log"
    dl_rc=124
  else
    remaining_s=$((deadline_s - elapsed_s))
    step_t="${dl_t}"
    [ "${remaining_s}" -lt "${step_t}" ] && step_t="${remaining_s}"
    dl_out="$(colab_run_bounded "${step_t}" "${kill_grace}" colab download -s "${session}" "${remote_path}" "${local_dst}" 2>&1)" || dl_rc=$?
    printf '%s\n' "${dl_out}" >> "${out_dir}/colab.log"
    if colab_rc_is_timeout "${dl_rc}"; then
      echo "SALVAGE_STEP_TIMEOUT download timeout_s=${step_t} kill_grace_s=${kill_grace} rc=${dl_rc}" >> "${out_dir}/guards.log"
    fi
  fi

  if [ "${dl_rc}" -eq 0 ] && [ -s "${local_dst}" ]; then
    echo "BUNDLE_AFTER_FAILURE: downloaded $(basename -- "${local_dst}") (rc=${failed_rc})" >> "${out_dir}/guards.log"
  else
    rm -f "${local_dst}"
    echo "BUNDLE_AFTER_FAILURE: none on the VM (rc=${failed_rc}, download rc=${dl_rc})" >> "${out_dir}/guards.log"
  fi
}

colab_stop_and_log_closing() {
  local py_bin="$1"
  local session="$2"
  local out_dir="$3"
  local attempts="${COLAB_STOP_ATTEMPTS:-2}"
  local stop_timeout="${COLAB_STOP_TIMEOUT_S:-60}"
  local sessions_timeout="${COLAB_SESSIONS_TIMEOUT_S:-30}"
  local kill_grace="${COLAB_KILL_GRACE_S:-10}"
  local attempt=1
  while [ "${attempt}" -le "${attempts}" ]; do
    local stop_rc=0
    colab_run_bounded "${stop_timeout}" "${kill_grace}" colab stop -s "${session}" >> "${out_dir}/colab.log" 2>&1 || stop_rc=$?
    if [ "${stop_rc}" -eq 0 ]; then
      break
    fi
    if colab_rc_is_timeout "${stop_rc}"; then
      echo "STOP_TIMEOUT attempt=${attempt}/${attempts} session=${session} timeout_s=${stop_timeout} kill_grace_s=${kill_grace} rc=${stop_rc}" >> "${out_dir}/guards.log"
    else
      echo "STOP_FAILED attempt=${attempt}/${attempts} session=${session} rc=${stop_rc}" >> "${out_dir}/guards.log"
    fi
    if [ "${attempt}" -lt "${attempts}" ]; then
      local next_attempt=$((attempt + 1))
      echo "STOP_RETRY attempt=${next_attempt}/${attempts} session=${session}" >> "${out_dir}/guards.log"
    fi
    attempt=$((attempt + 1))
  done
  local sess_rc=0
  colab_run_bounded "${sessions_timeout}" "${kill_grace}" colab sessions >> "${out_dir}/colab.log" 2>&1 || sess_rc=$?
  if colab_rc_is_timeout "${sess_rc}"; then
    echo "SESSIONS_TIMEOUT session=${session} timeout_s=${sessions_timeout} kill_grace_s=${kill_grace} rc=${sess_rc}" >> "${out_dir}/guards.log"
  fi
  colab_poll_usage_and_ram "${py_bin}" "${out_dir}" >/dev/null 2>&1 || true
}

# True when the card names a CPU runtime (no GPU): the kits' CPU-high-mem default, or CPU.
colab_card_is_cpu() {
  [ "$1" = "CPU-high-mem" ] || [ "$1" = "CPU" ]
}

# The GPU rate gate, shared by every lane. A kit calls colab_gpu_rate_gate_arm before it opens; a
# GPU card then needs a positive --max-rate (MAX_RATE_REQUIRED otherwise), and the post-open rate
# polls run 5 s apart (SDLAB_TEST_RATE_READ_INTERVAL_S only under the fake colab CLI). A CPU card
# keeps its configured rate and is untouched. colab_open_session_locked refuses
# GPU_RATE_GATE_NOT_ARMED for a GPU card that was not armed, so no lane can open a GPU window
# without the gate: after `colab new` succeeds it starts the cap clock (START_EPOCH) and reads the
# stable window rate (colab_read_post_open_rate), before the caller uploads anything.
COLAB_RATE_READ_POLLS_DEFAULT=24
COLAB_RATE_READ_INTERVAL_S_DEFAULT=5

# colab_gpu_rate_gate_arm <out_dir> <card> <max_rate> <test_mode>
colab_gpu_rate_gate_arm() {
  local out_dir="$1"
  local card="$2"
  local max_rate="$3"
  local test_mode="$4"
  rm -f "${out_dir}/gpu_rate_gate_armed.txt"
  if colab_card_is_cpu "${card}"; then
    export COLAB_CARD_CLASS=cpu
    return 0
  fi
  export COLAB_CARD_CLASS=gpu
  if ! [[ "${max_rate}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${max_rate}" =~ ^0+(\.0+)?$ ]]; then
    colab_refuse_logged "${out_dir}" MAX_RATE_REQUIRED "a GPU card (${card}) needs --max-rate <units/h>, the highest window rate it may run at"
    return 2
  fi
  export COLAB_RATE_READ_POLLS="${COLAB_RATE_READ_POLLS_DEFAULT}"
  export COLAB_RATE_READ_INTERVAL_S="${COLAB_RATE_READ_INTERVAL_S_DEFAULT}"
  if [ -n "${SDLAB_TEST_RATE_READ_INTERVAL_S:-}" ]; then
    if [ "${test_mode}" != "1" ]; then
      colab_refuse_logged "${out_dir}" PIN_OVERRIDE_IN_LIVE_RUN "SDLAB_TEST_RATE_READ_INTERVAL_S set without SDLAB_TEST_FAKE_COLAB=1 and the fake colab CLI on PATH"
      return 1
    fi
    export COLAB_RATE_READ_INTERVAL_S="${SDLAB_TEST_RATE_READ_INTERVAL_S}"
  fi
  printf '%s\n' "${max_rate}" > "${out_dir}/max_rate.txt"
  printf '%s %s %s\n' "${card}" "${max_rate}" "${COLAB_RATE_READ_INTERVAL_S}" > "${out_dir}/gpu_rate_gate_armed.txt"
}

# The machine shape gate, shared by every lane. A GPU card names its shape with --shape
# standard|high-mem; there is no default, because a hidden --high-mem once sent every GPU card
# shape=HIGH_RAM, a machine nobody had priced. A CPU card keeps its fixed `colab new --high-mem`
# and takes no --shape. colab_open_session_locked refuses SHAPE_REQUIRED for a GPU card that was
# not armed here, passes --high-mem only for high-mem, and checks the session row's Shape after open.
#
# google-colab-cli 0.7.4 drops --high-mem for L4, V5E1 and V6E1 (colab_cli/client.py:90-95,
# HIGH_MEM_ONLY_ACCELERATORS; resolve_assign_shape returns None for them at :109-110): those cards
# exist in a single high-memory shape, so --shape standard is refused for them before any colab call.
colab_card_is_single_shape() {
  case "${1^^}" in
    L4 | V5E1 | V6E1) return 0 ;;
  esac
  return 1
}

# The Shape a `colab sessions` row prints for a requested shape (shape_display_label,
# colab_cli/client.py:114-118).
colab_shape_row_label() {
  if [ "$1" = "high-mem" ]; then
    printf 'High-RAM\n'
  else
    printf 'Standard\n'
  fi
}

# colab_shape_gate_arm <out_dir> <card> <shape>
colab_shape_gate_arm() {
  local out_dir="$1"
  local card="$2"
  local shape="$3"
  rm -f "${out_dir}/shape_requested.txt"
  if colab_card_is_cpu "${card}"; then
    if [ -n "${shape}" ]; then
      colab_refuse_logged "${out_dir}" SHAPE_NOT_FOR_CPU "a CPU card (${card}) always opens with colab new --high-mem; drop --shape ${shape}"
      return 2
    fi
    return 0
  fi
  case "${shape}" in
    standard | high-mem) ;;
    "")
      colab_refuse_logged "${out_dir}" SHAPE_REQUIRED "a GPU card (${card}) needs --shape standard|high-mem; there is no default"
      return 2
      ;;
    *)
      colab_refuse_logged "${out_dir}" SHAPE_INVALID "--shape ${shape}: use standard or high-mem"
      return 2
      ;;
  esac
  if [ "${shape}" = "standard" ] && colab_card_is_single_shape "${card}"; then
    colab_refuse_logged "${out_dir}" SHAPE_STANDARD_UNAVAILABLE "${card} has a single high-memory shape (google-colab-cli 0.7.4 colab_cli/client.py:90-95); pass --shape high-mem"
    return 2
  fi
  printf '%s\n' "${shape}" > "${out_dir}/shape_requested.txt"
}

# colab_dry_cap_budget <py_bin> <guards_py> <lane> <card> <cap> <margin> <max_rate> <default_rate> <min_runtime_s>:
# print the cap trip arithmetic (launch_guards.py --dry) and exit before any colab call.
colab_dry_cap_budget() {
  local py_bin="$1"
  local guards_py="$2"
  local lane="$3"
  local card="$4"
  local cap="$5"
  local margin="$6"
  local max_rate="$7"
  local default_rate="$8"
  local min_runtime_s="$9"
  colab_compute_cleanup_bounds "${lane}"
  local priced_rate="${default_rate}"
  local eff_max_rate="${max_rate:-${default_rate}}"
  if ! colab_card_is_cpu "${card}"; then
    if ! [[ "${max_rate}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${max_rate}" =~ ^0+(\.0+)?$ ]]; then
      echo "REFUSED: MAX_RATE_REQUIRED: a GPU card (${card}) needs --max-rate <units/h>, the highest window rate it may run at" >&2
      return 2
    fi
    priced_rate="${max_rate}"
    eff_max_rate="${max_rate}"
  fi
  local dry_args=(
    "--dry"
    "--cap" "${cap}"
    "--margin" "${margin}"
    "--cleanup-bound-s" "${COLAB_CLEANUP_BOUND_S}"
    "--rate" "${priced_rate}"
    "--max-rate" "${eff_max_rate}"
  )
  if [ -n "${min_runtime_s}" ]; then
    if ! [[ "${min_runtime_s}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
      echo "REFUSED: CAP_TOO_SMALL_FOR_CLEANUP: --min-runtime-s ${min_runtime_s} must be a non-negative number of seconds" >&2
      return 2
    fi
    dry_args+=("--min-runtime-s" "${min_runtime_s}")
  fi
  "${py_bin}" "${guards_py}" "${dry_args[@]}" </dev/null
}

# colab_cap_budget_gate <py_bin> <guards_py> <out_dir> <lane> <card> <cap> <margin> <max_rate> <default_rate> <min_runtime_s>:
# refuse CAP_TOO_SMALL_FOR_CLEANUP before any colab call when cap - margin - cleanup_reserve <= 0
# or when the cap leaves less runtime than --min-runtime-s.
colab_cap_budget_gate() {
  local py_bin="$1"
  local guards_py="$2"
  local out_dir="$3"
  local lane="$4"
  local card="$5"
  local cap="$6"
  local margin="$7"
  local max_rate="$8"
  local default_rate="$9"
  local min_runtime_s="${10:-}"
  colab_compute_cleanup_bounds "${lane}"
  if [ -n "${min_runtime_s}" ] && ! [[ "${min_runtime_s}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    colab_refuse_logged "${out_dir}" CAP_TOO_SMALL_FOR_CLEANUP "--min-runtime-s ${min_runtime_s} must be a non-negative number of seconds"
    return 2
  fi
  local priced_rate="${default_rate}"
  local eff_max_rate="${default_rate}"
  if ! colab_card_is_cpu "${card}"; then
    priced_rate="${max_rate}"
    eff_max_rate="${max_rate}"
  fi
  local budget_args=(
    "--check-cap-budget"
    "--cap" "${cap}"
    "--margin" "${margin}"
    "--cleanup-bound-s" "${COLAB_CLEANUP_BOUND_S}"
    "--rate" "${priced_rate}"
    "--max-rate" "${eff_max_rate}"
  )
  if [ -n "${min_runtime_s}" ]; then
    budget_args+=("--min-runtime-s" "${min_runtime_s}")
  fi
  local budget_rc=0 budget_out=""
  budget_out="$("${py_bin}" "${guards_py}" "${budget_args[@]}" </dev/null 2>/dev/null)" || budget_rc=$?
  [ -n "${budget_out}" ] && printf '%s\n' "${budget_out}" >> "${out_dir}/guards.log"
  if [ "${budget_rc}" -ne 0 ]; then
    colab_refuse_from_guard_record "${py_bin}" "${out_dir}" "${budget_out}" CAP_TOO_SMALL_FOR_CLEANUP
    return 2
  fi
}

# colab_check_session_shape <session> <out_dir> <shape>: after `colab new`, the session's row in
# `colab sessions` must print the Shape the request asked for. Writes shape_check.json (requested,
# expected and observed values) and refuses SHAPE_MISMATCH otherwise; the caller's EXIT trap stops
# the session.
colab_check_session_shape() {
  local session="$1"
  local out_dir="$2"
  local shape="$3"
  local expected
  expected="$(colab_shape_row_label "${shape}")"
  local rows_file="${out_dir}/sessions_after_open.txt"
  colab_run_bounded "${COLAB_SESSIONS_TIMEOUT_S:-30}" "${COLAB_KILL_GRACE_S:-10}" colab sessions > "${rows_file}" 2>&1 || true
  cat "${rows_file}" >> "${out_dir}/colab.log"
  local observed rc=0
  observed="$("${PY_BIN:?the kit must set PY_BIN}" - "${session}" "${rows_file}" "${shape}" "${expected}" "${out_dir}/shape_check.json" << 'PYEOF'
import json
import re
import sys
from pathlib import Path

session, rows_file, shape, expected, out = sys.argv[1:6]
observed = None
for line in Path(rows_file).read_text(encoding="utf-8", errors="replace").splitlines():
    if line.startswith(f"[{session}] "):
        m = re.search(r"\|\s*Shape:\s*([^|]+?)\s*(?:\||$)", line)
        observed = m.group(1) if m else None
        break
rec = {"requested": shape, "expected": expected, "observed": observed, "match": observed == expected}
Path(out).write_text(json.dumps(rec) + "\n", encoding="utf-8")
print(observed if observed is not None else "none")
sys.exit(0 if rec["match"] else 3)
PYEOF
)" || rc=$?
  if [ "${rc}" -ne 0 ]; then
    colab_refuse_logged "${out_dir}" SHAPE_MISMATCH "requested --shape ${shape} (Shape: ${expected}); the session row reads Shape: ${observed:-none} (shape_check.json)"
    return 1
  fi
}

colab_open_session_locked() {
  local session="$1"
  local card="$2"
  local out_dir="$3"
  local lock_file="${COLAB_OPEN_LOCK:-/tmp/colab-window-open.lock}"
  mkdir -p "$(dirname "${lock_file}")"
  if ! colab_card_is_cpu "${card}"; then
    if [ "${COLAB_CARD_CLASS:-}" != "gpu" ] || [ ! -s "${out_dir}/gpu_rate_gate_armed.txt" ] || [ ! -s "${out_dir}/max_rate.txt" ]; then
      colab_refuse_logged "${out_dir}" GPU_RATE_GATE_NOT_ARMED "a GPU card (${card}) opens only after colab_gpu_rate_gate_arm"
      return 2
    fi
    if [ ! -s "${out_dir}/shape_requested.txt" ]; then
      colab_refuse_logged "${out_dir}" SHAPE_REQUIRED "a GPU card (${card}) opens only after colab_shape_gate_arm with --shape standard|high-mem"
      return 2
    fi
  fi

  # A CPU card keeps its fixed --high-mem. A GPU card sends --high-mem only for --shape high-mem.
  local new_args=()
  local shape=""
  if colab_card_is_cpu "${card}"; then
    new_args=("new" "--high-mem" "-s" "${session}")
  else
    shape="$(cat "${out_dir}/shape_requested.txt")"
    new_args=("new" "--gpu" "${card}")
    if [ "${shape}" = "high-mem" ]; then
      new_args+=("--high-mem")
    fi
    new_args+=("-s" "${session}")
  fi

  if command -v flock >/dev/null 2>&1; then
    (
      flock -x 9
      printf '1\n' > "${lock_file}.held"
      colab "${new_args[@]}" </dev/null >> "${out_dir}/colab.log" 2>&1
      rm -f "${lock_file}.held"
    ) 9>"${lock_file}"
  else
    local lock_dir="${lock_file}.lockdir"
    while ! mkdir "${lock_dir}" 2>/dev/null; do
      sleep 0.1
    done
    printf '1\n' > "${lock_file}.held"
    local rc=0
    colab "${new_args[@]}" </dev/null >> "${out_dir}/colab.log" 2>&1 || rc=$?
    rm -f "${lock_file}.held"
    rmdir "${lock_dir}" 2>/dev/null || true
    if [ "${rc}" -ne 0 ]; then
      return "${rc}"
    fi
  fi
  printf '1\n' > "${out_dir}/session_opened.txt"
  if ! colab_card_is_cpu "${card}"; then
    # The cap and wall clock starts the moment `colab new` succeeds: the rate polls and everything
    # after them are billed time and count.
    START_EPOCH="$(date -u +%s)"
    date -u -d "@${START_EPOCH}" +%Y-%m-%dT%H:%M:%SZ > "${out_dir}/cap_clock_started_at.txt"
    colab_check_session_shape "${session}" "${out_dir}" "${shape}" || return 1
    colab_read_post_open_rate "${PY_BIN:?the kit must set PY_BIN}" "${out_dir}" "${COLAB_RATE_READ_POLLS}" \
      "${COLAB_RATE_READ_INTERVAL_S}" "$(cat "${out_dir}/max_rate.txt")" || return 1
  fi
}

colab_scrub_all_logs() {
  local py_bin="$1"
  local guards_py="$2"
  local out_dir="$3"
  if [ ! -d "${out_dir}" ]; then
    return 0
  fi
  local scrub_args=()
  while IFS= read -r -d '' f; do
    scrub_args+=("--scrub-file" "${f}")
  done < <(find "${out_dir}" -type f \( -name "*.log" -o -name "*.json" -o -name "*.txt" -o -name "*.sh" \) -print0 2>/dev/null || true)
  if [ "${#scrub_args[@]}" -gt 0 ]; then
    "${py_bin}" "${guards_py}" "${scrub_args[@]}" </dev/null || true
  fi
}

colab_write_window_and_outcome() {
  local py_bin="$1"
  local out_dir="$2"
  local lane="$3"
  local session="$4"
  local card="$5"
  local cap="$6"
  local wall_s="$7"
  local grace_s="$8"
  local margin="$9"
  local opened_at="${10}"
  local closed_at="${11}"
  local exit_code="${12}"
  local shas_json="${13}"

  "${py_bin}" - "${out_dir}" "${lane}" "${session}" "${card}" "${cap}" "${wall_s}" "${grace_s}" "${margin}" "${opened_at}" "${closed_at}" "${exit_code}" "${shas_json}" << 'PYEOF'
import hashlib
import json
import os
import re
import sys
import tarfile
from pathlib import Path

out_dir = Path(sys.argv[1])
lane = sys.argv[2]
session = sys.argv[3]
card = sys.argv[4]
cap = float(sys.argv[5])
wall_s = int(float(sys.argv[6]))
grace_s = int(float(sys.argv[7]))
margin = float(sys.argv[8])
opened_at = sys.argv[9]
closed_at = sys.argv[10]
exit_code = int(sys.argv[11])
shas_raw = json.loads(sys.argv[12])

out_dir.mkdir(parents=True, exist_ok=True)


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def read_float_file(p: Path) -> float | None:
    if not p.exists():
        return None
    try:
        return float(p.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def read_text_file(p: Path) -> str | None:
    if not p.exists():
        return None
    val = p.read_text(encoding="utf-8", errors="replace").strip()
    return val if val else None


vm_facts: dict = {}
vm_win_file = out_dir / "vm_window.json"
if vm_win_file.exists():
    try:
        vm_facts.update(json.loads(vm_win_file.read_text(encoding="utf-8")))
    except Exception:
        pass

for tar_p in sorted(out_dir.glob("*.tar.gz")):
    if tarfile.is_tarfile(tar_p):
        try:
            with tarfile.open(tar_p, "r:gz") as tf:
                for member in tf.getmembers():
                    if Path(member.name).name == "vm_window.json":
                        ext = tf.extractfile(member)
                        if ext is not None:
                            vm_facts.update(json.loads(ext.read().decode("utf-8")))
        except Exception:
            pass

vitals_p = out_dir / "vitals.log"
if vitals_p.exists():
    for line in vitals_p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("WINDOW_JSON "):
            try:
                vm_facts.update(json.loads(line[len("WINDOW_JSON ") :].strip()))
            except Exception:
                pass
        elif line.startswith("PYTHON_IDENTITY "):
            try:
                vm_facts["python_identity"] = json.loads(line[len("PYTHON_IDENTITY ") :].strip())
            except Exception:
                pass


def bundle_member_text(name: str) -> str | None:
    """Text of the first member called `name` in a downloaded bundle, or None."""
    for tar_p in sorted(out_dir.glob("*.tar.gz")):
        if not tarfile.is_tarfile(tar_p):
            continue
        try:
            with tarfile.open(tar_p, "r:gz") as tf:
                for member in tf.getmembers():
                    if Path(member.name).name == name and member.isfile():
                        ext = tf.extractfile(member)
                        if ext is not None:
                            return ext.read().decode("utf-8", errors="replace")
        except Exception:
            continue
    return None


REFUSAL_CODES = (
    "WHEEL_MISSING",
    "LOCK_HASH_MISMATCH",
    "LOCAL_WHEEL_MISSING",
    "LOCAL_WHEEL_SHA_MISMATCH",
    "INSTALL_NETWORK_FAILURE",
    "INSTALL_FAILED",
    "LOCK_DRIFT",
    "LOCK_COMPILE_FAILED",
    "LOCK_INPUT_MISSING",
    "PIN_NOT_FOUND",
    "PIN_CHECK_UNAVAILABLE",
    "UV_VERSION_MISMATCH",
    "PREFLIGHT_TOOL_MISSING",
    "PREFLIGHT_TEST_HOOK_IN_LIVE_RUN",
    "VENV_PYTHON_MISMATCH",
    "VENV_IMPORT_OUTSIDE_VENV",
    "VENV_IMPORT_FAILED",
    "WHEEL_DIR_REQUIRED",
    "UPLOAD_FAILED",
    "DOWNLOAD_FAILED",
    "REMOTE_DIR_CREATE_FAILED",
    "REMOTE_PARENT_UNVERIFIED",
    "PYTHON_BUILD_MISMATCH",
    "LANE3_MODE_INVALID",
    "TRAIN_REQUIRES_GPU",
    "TRAIN_MODEL_REQUIRED",
    "TRAIN_FAILED",
    "TRAIN_CHECKPOINT_MISSING",
    "TRAIN_MODEL_REVISION_REQUIRED",
    "HOST_RAM_THRESHOLD_MISSING",
    "DOWNLOAD_LIMIT_MISSING",
    "TRAIN_DATASET_REQUIRED",
    "TRAIN_OPTION_WITHOUT_TRAIN",
    "GPU_SMOKE_FAILED",
    "DISK_FREE_LOW",
    "HOST_RAM_LOW",
    "DOWNLOAD_TOO_SLOW",
    "MODEL_DOWNLOAD_FAILED",
    "DATASET_FILE_MISSING",
    "DATASET_SHA_MISMATCH",
    "JOB_TEMPLATE_INVALID",
    "HF_READ_TOKEN_MISSING",
    "RATE_UNREAD",
    "RATE_ABOVE_MAX",
    "ASSIGNMENTS_UNREADABLE",
    "GPU_RATE_GATE_NOT_ARMED",
    "SHAPE_REQUIRED",
    "SHAPE_INVALID",
    "SHAPE_NOT_FOR_CPU",
    "SHAPE_STANDARD_UNAVAILABLE",
    "SHAPE_MISMATCH",
    "MAX_RATE_REQUIRED",
    "TRAIN_MAX_RATE_REQUIRED",
    "CAP_TOO_SMALL_FOR_CLEANUP",
    "TRAIN_SAMPLE_MISSING",
    "TRAIN_WALL_REQUIRED",
    "TRAIN_CAP_REQUIRED",
    "TRAIN_WALL_TOO_SHORT",
    "RUNG_JOB_REQUIRED",
    "MODEL_AUTH_FAILED",
    "MODEL_REVISION_NOT_FOUND",
    "MODEL_METADATA_FAILED",
    "HF_TOKEN_STAGING_FAILED",
    "HF_TOKEN_SHRED_FAILED",
    # Rig-side live guards (colab_check_cap_and_ram, colab_run_exec_with_live_guards).
    "HOST_RAM_PROJECTION_EXCEEDED",
    "HOST_RAM_UNREADABLE",
    "WALL_GUARD_TRIPPED",
    "CAP_GUARD_TRIPPED",
    "COLAB_USAGE_PARSE_FAILED",
    "DEAD_HARNESS_TRIPPED",
    "STALL_GUARD_TRIPPED",
    "SETUP_STALL_TRIPPED",
    "GUARD_FAILED",
)
# A refusal code comes only from a line the kit itself emits, starting `REFUSED: <CODE>`, in the
# files those lines are written to: guards.log (rig side), the exec stream in vitals.log, and the
# VM's setup.log inside a downloaded bundle. Free text never counts: colab.log (CLI output) is not
# read, and every vitals PROC: section (a `ps` listing, which shows the import gate's own
# `python -c` source with its refusal words) is skipped up to the block's HARNESS: line.
REFUSED_LINE_RE = re.compile(r"^REFUSED: ([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?=[:\s]|$)")


def first_refusal(text: str, skip_proc: bool) -> tuple[str, str | None] | None:
    """(code, why) of the first kit refusal line; why is the text after `REFUSED: <CODE>: `."""
    in_proc = False
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if skip_proc:
            if line.startswith("PROC:"):
                in_proc = True
                continue
            if in_proc:
                if line.startswith("HARNESS:") or line.startswith("=== VITALS"):
                    in_proc = False
                else:
                    continue
        m = REFUSED_LINE_RE.match(line)
        if m and m.group(1) in REFUSAL_CODES:
            rest = line[m.end():].lstrip(":").strip()
            return m.group(1), (rest or None)
    return None


refusal_sources: list[tuple[str | None, bool]] = []
for log_name, skip_proc in (("guards.log", False), ("vitals.log", True)):
    lp = out_dir / log_name
    if lp.exists():
        refusal_sources.append((lp.read_text(encoding="utf-8", errors="replace"), skip_proc))
refusal_sources.append((bundle_member_text("setup.log"), False))

refusal_code: str | None = None
refusal_why: str | None = None
for src_text, skip_proc in refusal_sources:
    if src_text:
        found = first_refusal(src_text, skip_proc)
        if found:
            refusal_code, refusal_why = found
            break

downloaded_files: dict[str, str] = {}
for artifact in sorted(list(out_dir.glob("*.tar.gz")) + list(out_dir.glob("*.safetensors"))):
    if artifact.is_file():
        downloaded_files[artifact.name] = sha256_path(artifact)

usage_parse_error = read_text_file(out_dir / "usage_parse_error.txt")
rate_readings = None
if (out_dir / "rate_window.json").is_file():
    try:
        rate_readings = json.loads((out_dir / "rate_window.json").read_text(encoding="utf-8")).get("readings")
    except ValueError:
        rate_readings = None
cap_clock_started_at = read_text_file(out_dir / "cap_clock_started_at.txt")
# The machine shape a GPU card asked for (--shape) and what its session row showed after open;
# a CPU card takes no --shape and always opens --high-mem, so both stay null for it.
shape_requested = read_text_file(out_dir / "shape_requested.txt")
shape_check = None
if (out_dir / "shape_check.json").is_file():
    try:
        shape_check = json.loads((out_dir / "shape_check.json").read_text(encoding="utf-8"))
    except ValueError:
        shape_check = None
rate_check = None
if (out_dir / "rate_check.json").is_file():
    try:
        rate_check = json.loads((out_dir / "rate_check.json").read_text(encoding="utf-8"))
    except ValueError:
        rate_check = None
rate_measured_pre_open = read_float_file(out_dir / "rate_measured_pre_open.txt")
rate_measured_post_open = read_float_file(out_dir / "rate_measured_post_open.txt")
rate_measured = (
    rate_measured_post_open
    if rate_measured_post_open is not None
    else read_float_file(out_dir / "rate_measured.txt")
)
rate_for_projection = read_float_file(out_dir / "rate_for_projection.txt")
rate_used_for_cap_and_projection = rate_for_projection
rate_source = read_text_file(out_dir / "rate_source.txt") or (
    "post_open_measured"
    if (rate_measured_post_open is not None and rate_measured_post_open > 0.0)
    else (
        "configured_pending_post_open_rate"
        if (rate_measured_post_open is not None and rate_measured_post_open == 0.0)
        else (
            "max_of_pre_open_and_configured"
            if rate_measured_pre_open is not None
            else "configured"
        )
    )
)

final_status = "ok" if exit_code == 0 else (refusal_code or "failed")

# Lane 3 (train): what the VM says about training, normalised so it cannot be read as a passed
# training by accident. "skipped_cpu_stub" (the CPU install-path stub stopped at the import gate)
# and any value other than "trained" mean not trained; `trained` is true only for a window that
# ended ok AND whose VM reported train=trained. Other lanes carry neither field.
train_fields: dict = {}
if lane == "train":
    vm_train = vm_facts.get("train")
    train_state = vm_train if vm_train in ("skipped_cpu_stub", "trained") else None
    rung_job = read_text_file(out_dir / "rung_job.txt")
    rung_job_sha256 = read_text_file(out_dir / "rung_job_sha256.txt")
    train_fields = {
        "train": train_state,
        "trained": bool(final_status == "ok" and train_state == "trained"),
        "rung_job": rung_job,
        "rung_job_sha256": rung_job_sha256,
    }

kill_grace_s = int(os.environ.get("COLAB_KILL_GRACE_S", "10"))
salvage_restart_s = int(os.environ.get("COLAB_SALVAGE_RESTART_TIMEOUT_S", "180"))
salvage_exec_s = int(os.environ.get("COLAB_SALVAGE_EXEC_TIMEOUT_S", "330"))
salvage_download_s = int(os.environ.get("COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S", "300"))
salvage_steps_sum_s = (
    (salvage_restart_s + kill_grace_s)
    + (salvage_exec_s + kill_grace_s)
    + (salvage_download_s + kill_grace_s)
)
salvage_deadline_s = int(os.environ.get("SALVAGE_DEADLINE_S", str(salvage_steps_sum_s)))
stop_timeout_s = int(os.environ.get("COLAB_STOP_TIMEOUT_S", "60"))
stop_attempts = int(os.environ.get("COLAB_STOP_ATTEMPTS", "2"))
stop_bound_s = stop_attempts * (stop_timeout_s + kill_grace_s)
cleanup_stop_attempted_by_s = min(salvage_steps_sum_s, salvage_deadline_s) if lane == "train" else 0
cleanup_bound_s = cleanup_stop_attempted_by_s + stop_bound_s

cap_trip_formula = (
    "effective_trip = cap - margin - cleanup_reserve; cleanup_reserve = (cleanup_bound_s / 3600) * priced_rate"
)
priced_rate_for_cap: float | None = None
if rate_used_for_cap_and_projection is not None and rate_used_for_cap_and_projection > 0.0:
    priced_rate_for_cap = rate_used_for_cap_and_projection
elif (out_dir / "max_rate.txt").is_file():
    priced_rate_for_cap = read_float_file(out_dir / "max_rate.txt")
if priced_rate_for_cap is None and (out_dir / "guards.log").is_file():
    for gline in reversed((out_dir / "guards.log").read_text(encoding="utf-8", errors="replace").splitlines()):
        if gline.startswith("{") and '"priced_rate"' in gline:
            try:
                grec = json.loads(gline)
                pr = grec.get("priced_rate") or (grec.get("cap") or {}).get("priced_rate")
                if pr is not None and float(pr) > 0.0:
                    priced_rate_for_cap = float(pr)
                    break
            except Exception:
                pass
if priced_rate_for_cap is None and card in ("CPU-high-mem", "CPU"):
    priced_rate_for_cap = float(os.environ.get("RATE_CCU_PER_HOUR", "0.26"))

if priced_rate_for_cap is not None:
    cleanup_reserve_units: float | None = round((cleanup_bound_s / 3600.0) * float(priced_rate_for_cap), 6)
    effective_trip_units: float | None = round(float(cap) - float(margin) - cleanup_reserve_units, 6)
else:
    cleanup_reserve_units = None
    effective_trip_units = None

window_payload = {
    **vm_facts,
    "window_id": session,
    "lane": lane,
    "session": session,
    "card": card,
    "shape_requested": shape_requested,
    "shape_check": shape_check,
    "status": final_status,
    "refusal_code": refusal_code,
    "why": refusal_why,
    "cap": cap,
    "wall_s": wall_s,
    "grace_s": grace_s,
    "margin": margin,
    "cleanup_stop_attempted_by_s": cleanup_stop_attempted_by_s,
    "cleanup_bound_s": cleanup_bound_s,
    "cleanup_reserve_units": cleanup_reserve_units,
    "effective_trip_units": effective_trip_units,
    "cap_trip_formula": cap_trip_formula,
    "formula": cap_trip_formula,
    "start_balance": read_float_file(out_dir / "start_balance.txt"),
    "end_balance": read_float_file(out_dir / "end_balance.txt"),
    "rate_measured": rate_measured,
    "rate_measured_pre_open": rate_measured_pre_open,
    "rate_measured_post_open": rate_measured_post_open,
    "rate_used_for_cap_and_projection": rate_used_for_cap_and_projection,
    "rate_for_projection": rate_for_projection,
    "rate_source": rate_source,
    "usage_parse_error": usage_parse_error,
    "rate_check": rate_check,
    "rate_readings": rate_readings,
    "cap_clock_started_at": cap_clock_started_at,
    "input_shas": shas_raw.get("verified_shas", shas_raw),
    "downloaded_files": downloaded_files,
    "opened_at": opened_at,
    "closed_at": closed_at,
    "exit_code": exit_code,
    **train_fields,
}
(out_dir / "window.json").write_text(json.dumps(window_payload, indent=2) + "\n", encoding="utf-8", newline="\n")

outcome_payload = {
    "window_id": session,
    "lane": lane,
    "session": session,
    "card": card,
    "status": final_status,
    "refusal_code": refusal_code,
    "why": refusal_why,
    "exit_code": exit_code,
    "opened_at": opened_at,
    "closed_at": closed_at,
    **train_fields,
}
(out_dir / "outcome.draft.json").write_text(json.dumps(outcome_payload, indent=2) + "\n", encoding="utf-8", newline="\n")
PYEOF
}
