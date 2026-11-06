#!/usr/bin/env bash
# Shared Colab window lifecycle, lock, live wall/cap/vitals/RAM guards, token scrubber, and EXIT trap.
set -euo pipefail

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
# plain open() and creates no local directory, so the local parent is checked first. Refuses
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
  local out=""
  local rc=0
  out="$(colab download -s "${session}" "${src}" "${dst}" </dev/null 2>&1)" || rc=$?
  printf '%s\n' "${out}" >> "${out_dir}/colab.log"
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
  usage_text="$(timeout -k 5 30 colab usage </dev/null 2>>"${out_dir}/colab.log")" || usage_rc=$?
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

# Parse VM /proc/meminfo and cgroup memory from vitals.log when present
anon_mb = float(os.environ.get("CURRENT_ANON_MB", "512")) if "os" in sys.modules else 512.0
mem_total_mb = 12288.0
cgroup_max_mb = ""
vitals_f = out_dir / "vitals.log"
if vitals_f.exists():
    vtxt = vitals_f.read_text(encoding="utf-8", errors="replace")
    m_tot = re.findall(r"MemTotal:\s*(\d+)\s*kB", vtxt)
    if m_tot:
        mem_total_mb = round(int(m_tot[-1]) / 1024.0, 1)
    m_anon = re.findall(r"AnonPages:\s*(\d+)\s*kB", vtxt)
    if m_anon:
        anon_mb = round(int(m_anon[-1]) / 1024.0, 1)
    m_cg_cur = re.findall(r"CGROUP_MEM_CURRENT:\s*(\d+)", vtxt)
    if m_cg_cur:
        anon_mb = round(int(m_cg_cur[-1]) / (1024.0 * 1024.0), 1)
    m_cg_max = re.findall(r"CGROUP_MEM_MAX:\s*(\d+)", vtxt)
    if m_cg_max:
        cgroup_max_mb = str(round(int(m_cg_max[-1]) / (1024.0 * 1024.0), 1))

print(f"{start_bal_str} {cur_bal_str} {parsed['rate_for_projection']} {err_tok} {anon_mb} {mem_total_mb} {cgroup_max_mb}")
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
    colab_refuse_logged "${out_dir}" ASSIGNMENTS_UNREADABLE "mid-run: colab usage gave no readable Active assignments count (missing or 0) on 3 consecutive reads (rate_window.json)"
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
  local start_bal="" cur_bal="" rate_val="" err_tok="" anon_mb="" mem_total_mb="" cgroup_max_mb=""
  if [ "${poll_rc}" -ne 0 ]; then
    err_tok="COLAB_USAGE_PARSE_FAILED"
    printf 'COLAB_USAGE_PARSE_FAILED: usage poll helper exited with status %s\n' "${poll_rc}" > "${out_dir}/usage_parse_error.txt"
  else
    read -r start_bal cur_bal rate_val err_tok anon_mb mem_total_mb cgroup_max_mb <<< "${metrics}"
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

  if [ "${mode}" = "live" ] && ! colab_midrun_rate_check "${py_bin}" "${out_dir}"; then
    return 1
  fi
  local guard_rc=0
  "${py_bin}" "${guards_py}" "${guard_args[@]}" </dev/null >> "${out_dir}/guards.log" || guard_rc=$?
  if [ "${guard_rc}" -ne 0 ]; then
    if [ "${err_tok}" != "NONE" ] && [ -n "${err_tok}" ]; then
      echo "REFUSED: COLAB_USAGE_PARSE_FAILED" >&2
    fi
    return 1
  fi

  local ram_args=(
    "--check-ram"
    "--current-anon-mb" "${CURRENT_ANON_MB:-${anon_mb:-512}}"
    "--projected-delta-mb" "${PROJECTED_DELTA_MB:-2048}"
    "--mem-total-mb" "${MEM_TOTAL_MB:-${mem_total_mb:-12288}}"
  )
  if [ -n "${cgroup_max_mb:-}" ]; then
    ram_args+=("--cgroup-max-mb" "${cgroup_max_mb}")
  fi
  local ram_rc=0
  "${py_bin}" "${guards_py}" "${ram_args[@]}" </dev/null >> "${out_dir}/guards.log" || ram_rc=$?
  if [ "${ram_rc}" -ne 0 ]; then
    return "${ram_rc}"
  fi
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

    run_only_bytes="$(grep -Ev '^(===[[:space:]]*VITALS|CGROUP_MEM(_CURRENT|_MAX)?:|MEM:|SETUP_BYTES:|PROC:|HARNESS:|[[:space:]]*[0-9]+[[:space:]]+.*(comfy|main\.py|ai-toolkit|run\.py|llama-server|ollama|lane1_render\.py))' "${out_dir}/vitals.log" 2>/dev/null | wc -c | tr -d '[:space:]' || echo 0)"
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

    local vitals_rc=0
    "${py_bin}" "${guards_py}" \
      --vitals-file "${out_dir}/vitals.log" \
      --idle-seconds "${idle_s}" \
      --setup-idle-seconds "${setup_idle_s}" \
      --stall-s "${stall_s}" \
      --setup-stall-s "${setup_stall_s}" </dev/null >> "${out_dir}/guards.log" || vitals_rc=$?
    if [ "${vitals_rc}" -ne 0 ]; then
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

  "${py_bin}" "${guards_py}" --vitals-file "${out_dir}/vitals.log" --idle-seconds 0 --setup-idle-seconds 0 --stall-s "${stall_s}" --setup-stall-s "${setup_stall_s}" </dev/null >> "${out_dir}/guards.log"
  local end_epoch elapsed_final
  end_epoch="$(date -u +%s)"
  elapsed_final="$((end_epoch - start_epoch))"
  colab_check_cap_and_ram "${py_bin}" "${guards_py}" "live" "${elapsed_final}" "${wall_s}" "${grace_s}" "${cap}" "${margin}" "${out_dir}"
}

colab_stop_and_log_closing() {
  local py_bin="$1"
  local session="$2"
  local out_dir="$3"
  colab stop -s "${session}" </dev/null >> "${out_dir}/colab.log" 2>&1 || true
  colab sessions </dev/null >> "${out_dir}/colab.log" 2>&1 || true
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
  colab sessions </dev/null > "${rows_file}" 2>&1 || true
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
    "TRAIN_SAMPLE_MISSING",
    "TRAIN_WALL_REQUIRED",
    "TRAIN_CAP_REQUIRED",
    "TRAIN_WALL_TOO_SHORT",
    "MODEL_AUTH_FAILED",
    "MODEL_REVISION_NOT_FOUND",
    "MODEL_METADATA_FAILED",
    "HF_TOKEN_STAGING_FAILED",
    "HF_TOKEN_SHRED_FAILED",
)
# A refusal code comes only from a line the kit itself emits, starting `REFUSED: <CODE>`, in the
# files those lines are written to: guards.log (rig side), the exec stream in vitals.log, and the
# VM's setup.log inside a downloaded bundle. Free text never counts: colab.log (CLI output) is not
# read, and every vitals PROC: section (a `ps` listing, which shows the import gate's own
# `python -c` source with its refusal words) is skipped up to the block's HARNESS: line.
REFUSED_LINE_RE = re.compile(r"^REFUSED: ([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?=[:\s]|$)")


def first_refusal(text: str, skip_proc: bool) -> str | None:
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
            return m.group(1)
    return None


refusal_sources: list[tuple[str | None, bool]] = []
for log_name, skip_proc in (("guards.log", False), ("vitals.log", True)):
    lp = out_dir / log_name
    if lp.exists():
        refusal_sources.append((lp.read_text(encoding="utf-8", errors="replace"), skip_proc))
refusal_sources.append((bundle_member_text("setup.log"), False))

refusal_code: str | None = None
for src_text, skip_proc in refusal_sources:
    if src_text:
        refusal_code = first_refusal(src_text, skip_proc)
        if refusal_code:
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
    train_fields = {
        "train": train_state,
        "trained": bool(final_status == "ok" and train_state == "trained"),
    }

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
    "cap": cap,
    "wall_s": wall_s,
    "grace_s": grace_s,
    "margin": margin,
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
    "exit_code": exit_code,
    "opened_at": opened_at,
    "closed_at": closed_at,
    **train_fields,
}
(out_dir / "outcome.draft.json").write_text(json.dumps(outcome_payload, indent=2) + "\n", encoding="utf-8", newline="\n")
PYEOF
}
