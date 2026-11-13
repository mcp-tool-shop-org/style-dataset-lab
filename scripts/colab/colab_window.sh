#!/usr/bin/env bash
# Shared Colab window lifecycle, lock, live wall/cap/vitals/RAM guards, token scrubber, and EXIT trap.
#
# Bounded cleanup and salvage contract (every step runs under `timeout -k` in a subshell with
# default SIGTERM/SIGINT dispositions so a wedged child is killed by SIGKILL after the grace):
#   COLAB_KILL_GRACE_S_DEFAULT=10               (`timeout -k 10` SIGTERM->SIGKILL grace)
#   COLAB_OPEN_LOCK_TIMEOUT_S_DEFAULT=180       (3 min + 10 s -k = 190 s wait on /tmp/colab-window-open.lock)
#   COLAB_NEW_TIMEOUT_S_DEFAULT=180             (3 min + 10 s -k = 190 s on `colab new`)
#   COLAB_UPLOAD_TIMEOUT_S_DEFAULT=120          (2 min + 10 s -k = 130 s per `colab upload`)
#   COLAB_WALL_ESCALATE_S_DEFAULT=30            (watcher first wait = max(COLAB_WALL_ESCALATE_S, COLAB_IN_FLIGHT_BOUND_S))
#   COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT=300        (5 min + 10 s -k = 310 s when bundle size is unknown)
#   COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT=180 (3 min + 10 s -k = 190 s on `colab restart-kernel`)
#   COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT=330    (330 s + 10 s -k = 340 s over bundle-now `--timeout 300`)
#   COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT=300 (5 min + 10 s -k = 310 s per salvage download part)
#   COLAB_SALVAGE_DOWNLOAD_PARTS_DEFAULT=1      (projected keep-all bundle parts; N >= 1)
#   SALVAGE_DEADLINE_S=190+340+D*310            (D download steps: N for N=1; 2 + 2N for N>1, because a split salvage also
#                                                fetches the VM's split manifest and each of those steps may retry once on
#                                                5xx: 840 s for N=1; 2390 s for N=2; 3630 s for N=4;
#                                                past it, cleanup skips remaining salvage and runs `colab stop`)
#   COLAB_UPLOAD_REASSEMBLE_MB_S_DEFAULT=25     (VM reassembly exec bound = max(upload_timeout, ceil(bytes/(rate*1e6))+30),
#                                                or explicit COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S)
#   COLAB_STOP_TIMEOUT_S_DEFAULT=60             (60 s + 10 s -k = 70 s per `colab stop` attempt)
#   COLAB_STOP_ATTEMPTS_DEFAULT=2               (1 retry -> 2 * 70 = 140 s worst-case stop bound)
#   COLAB_SESSIONS_TIMEOUT_S_DEFAULT=30         (30 s + 10 s -k = 40 s on `colab sessions`)
# Worst-case time measured from the guard trip to `colab stop` attempted (`cleanup_stop_attempted_by_s`)
# and total cleanup bound from the trip through `colab stop` completion (`cleanup_bound_s`):
#   in_flight_bound_s = max(COLAB_DOWNLOAD_TIMEOUT_S, COLAB_UPLOAD_TIMEOUT_S, COLAB_SESSIONS_TIMEOUT_S,
#                           VM download-prepare exec = min(COLAB_DOWNLOAD_TIMEOUT_S, 180 s),
#                           VM upload-reassembly exec = COLAB_REASSEMBLE_BOUND_S) + COLAB_KILL_GRACE_S
#                     = 300 + 10 = 310 s unless an upload can chunk and its reassembly bound is longer
#   first_wait_s      = max(COLAB_WALL_ESCALATE_S, COLAB_IN_FLIGHT_BOUND_S) = max(30, 310) = 310 s from trip
#   second_wait_s     = cleanup_stop_attempted_by_s = in_flight_bound_s + salvage_bound_s, measured from trip
#   Lane 3 (train):  cleanup_stop_attempted_by_s = 310 + (190 + 340 + D * 310) (1150 s for N=1; 2700 s for N=2),
#                    cleanup_bound_s = cleanup_stop_attempted_by_s + 140 (1290 s for N=1; 2840 s for N=2)
#   Lane 1 (render): cleanup_stop_attempted_by_s = 310 + 0 = 310 s,
#                    cleanup_bound_s = 310 + 0 + 140 = 450 s (the stubs)
#   Lane 1 real --render (COLAB_RENDER_SALVAGE=1): the same salvage as the train lane, so a wall or cap trip keeps the
#                    stamped PNGs and renders.jsonl: cleanup_stop_attempted_by_s = 310 + SALVAGE_DEADLINE_S
# Cap guard cleanup reserve (reserves cleanup_bound_s before the trip so total spend stays <= cap):
#   effective_trip = cap - margin - cleanup_reserve; cleanup_reserve = (cleanup_bound_s / 3600) * priced_rate
#   Refuses CAP_TOO_SMALL_FOR_CLEANUP before any colab call when effective_trip <= 0 or when
#   runtime_to_trip < --min-runtime-s; --dry prints the trip arithmetic and exits.
set -euo pipefail

COLAB_WINDOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLAB_KILL_GRACE_S_DEFAULT=10
COLAB_OPEN_LOCK_TIMEOUT_S_DEFAULT=180
COLAB_NEW_TIMEOUT_S_DEFAULT=180
COLAB_UPLOAD_TIMEOUT_S_DEFAULT=120
COLAB_WALL_ESCALATE_S_DEFAULT=30
COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT=300
COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT=180
COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT=330
COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT=300
COLAB_SALVAGE_DOWNLOAD_PARTS_DEFAULT=1
SALVAGE_DEADLINE_S_DEFAULT=840
COLAB_STOP_TIMEOUT_S_DEFAULT=60
COLAB_STOP_ATTEMPTS_DEFAULT=2
COLAB_SESSIONS_TIMEOUT_S_DEFAULT=30
COLAB_UPLOAD_CHUNK_BYTES_DEFAULT=33554432
COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT=268435456
COLAB_UPLOAD_REASSEMBLE_MB_S_DEFAULT=25

COLAB_CALLER_DOWNLOAD_TIMEOUT_S="${COLAB_DOWNLOAD_TIMEOUT_S:-}"
COLAB_CALLER_UPLOAD_TIMEOUT_S="${COLAB_UPLOAD_TIMEOUT_S:-}"
COLAB_CALLER_UPLOAD_CHUNK_BYTES="${COLAB_UPLOAD_CHUNK_BYTES:-}"
COLAB_CALLER_DOWNLOAD_CHUNK_BYTES="${COLAB_DOWNLOAD_CHUNK_BYTES:-}"
COLAB_CALLER_UPLOAD_REASSEMBLE_TIMEOUT_S="${COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S:-}"
COLAB_CALLER_UPLOAD_REASSEMBLE_MB_S="${COLAB_UPLOAD_REASSEMBLE_MB_S:-}"
export COLAB_KILL_GRACE_S="${COLAB_KILL_GRACE_S_DEFAULT}"
export COLAB_OPEN_LOCK_TIMEOUT_S="${COLAB_OPEN_LOCK_TIMEOUT_S_DEFAULT}"
export COLAB_NEW_TIMEOUT_S="${COLAB_NEW_TIMEOUT_S_DEFAULT}"
if [[ "${COLAB_CALLER_UPLOAD_TIMEOUT_S}" =~ ^[1-9][0-9]*$ ]]; then
  export COLAB_UPLOAD_TIMEOUT_S="${COLAB_CALLER_UPLOAD_TIMEOUT_S}"
  export COLAB_UPLOAD_TIMEOUT_SOURCE="env"
else
  export COLAB_UPLOAD_TIMEOUT_S="${COLAB_UPLOAD_TIMEOUT_S_DEFAULT}"
  export COLAB_UPLOAD_TIMEOUT_SOURCE="default"
fi
if [[ "${COLAB_CALLER_UPLOAD_REASSEMBLE_TIMEOUT_S}" =~ ^[1-9][0-9]*$ ]]; then
  export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S="${COLAB_CALLER_UPLOAD_REASSEMBLE_TIMEOUT_S}"
  export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_SOURCE="env"
else
  export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S=""
  export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_SOURCE="size_and_rate"
fi
if [[ "${COLAB_CALLER_UPLOAD_REASSEMBLE_MB_S}" =~ ^[0-9]+(\.[0-9]+)?$ ]] && ! [[ "${COLAB_CALLER_UPLOAD_REASSEMBLE_MB_S}" =~ ^0+(\.0+)?$ ]]; then
  export COLAB_UPLOAD_REASSEMBLE_MB_S="${COLAB_CALLER_UPLOAD_REASSEMBLE_MB_S}"
  export COLAB_UPLOAD_REASSEMBLE_MB_S_SOURCE="env"
else
  export COLAB_UPLOAD_REASSEMBLE_MB_S="${COLAB_UPLOAD_REASSEMBLE_MB_S_DEFAULT}"
  export COLAB_UPLOAD_REASSEMBLE_MB_S_SOURCE="default"
fi
export COLAB_WALL_ESCALATE_S="${COLAB_WALL_ESCALATE_S_DEFAULT}"
export COLAB_DOWNLOAD_TIMEOUT_S="${COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT}"
export COLAB_DOWNLOAD_TIMEOUT_SOURCE="default"
if [ -n "${COLAB_CALLER_UPLOAD_CHUNK_BYTES}" ]; then
  export COLAB_UPLOAD_CHUNK_BYTES="${COLAB_CALLER_UPLOAD_CHUNK_BYTES}"
  export COLAB_UPLOAD_CHUNK_SOURCE="env"
else
  export COLAB_UPLOAD_CHUNK_BYTES="${COLAB_UPLOAD_CHUNK_BYTES_DEFAULT}"
  export COLAB_UPLOAD_CHUNK_SOURCE="default"
fi
if [ -n "${COLAB_CALLER_DOWNLOAD_CHUNK_BYTES}" ]; then
  export COLAB_DOWNLOAD_CHUNK_BYTES="${COLAB_CALLER_DOWNLOAD_CHUNK_BYTES}"
  export COLAB_DOWNLOAD_CHUNK_SOURCE="env"
else
  export COLAB_DOWNLOAD_CHUNK_BYTES="${COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT}"
  export COLAB_DOWNLOAD_CHUNK_SOURCE="default"
fi
export COLAB_SALVAGE_RESTART_TIMEOUT_S="${COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT}"
export COLAB_SALVAGE_EXEC_TIMEOUT_S="${COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT}"
export COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S="${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT}"
export COLAB_SALVAGE_DOWNLOAD_PARTS="${COLAB_SALVAGE_DOWNLOAD_PARTS_DEFAULT}"
export SALVAGE_DEADLINE_S="${SALVAGE_DEADLINE_S_DEFAULT}"
export COLAB_STOP_TIMEOUT_S="${COLAB_STOP_TIMEOUT_S_DEFAULT}"
export COLAB_STOP_ATTEMPTS="${COLAB_STOP_ATTEMPTS_DEFAULT}"
export COLAB_SESSIONS_TIMEOUT_S="${COLAB_SESSIONS_TIMEOUT_S_DEFAULT}"
COLAB_CLEANUP_SIGNAL_COUNT=0
COLAB_CLEANUP_SKIP_SALVAGE=0
COLAB_SALVAGE_STEP_PID=""

# colab_salvage_steps_sum_s: the worst-case wall of one post-failure salvage, from the environment:
# restart-kernel + bundle-now exec + every download step. A single-part bundle is one GET. A
# multi-part bundle also fetches the VM's split manifest and every part, and each of those steps may
# be retried once on HTTP 5xx (`_colab_download_transfer`), so it counts 2 + 2 * parts download steps.
colab_salvage_steps_sum_s() {
  local grace="${COLAB_KILL_GRACE_S:-10}"
  local restart_s="${COLAB_SALVAGE_RESTART_TIMEOUT_S:-180}"
  local exec_s="${COLAB_SALVAGE_EXEC_TIMEOUT_S:-330}"
  local dl_s="${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S:-300}"
  local parts="${COLAB_SALVAGE_DOWNLOAD_PARTS:-1}"
  local dl_steps="${parts}"
  if [ "${parts}" -gt 1 ]; then
    dl_steps=$(( 2 + 2 * parts ))
  fi
  echo $(( (restart_s + grace) + (exec_s + grace) + dl_steps * (dl_s + grace) ))
}

# colab_reassemble_bound_s: the longest VM-side chunked-upload reassembly `colab exec`, in seconds, from the
# environment: 0 when no upload can chunk (COLAB_UPLOAD_MAX_BYTES known and within COLAB_UPLOAD_CHUNK_BYTES);
# the explicit COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S when set; otherwise the size-and-rate bound
# max(upload timeout, ceil(max_bytes / (mb_s * 1e6)) + 30) that `colab_upload_checked` applies.
colab_reassemble_bound_s() {
  local max_bytes="${COLAB_UPLOAD_MAX_BYTES:-}"
  local chunk="${COLAB_UPLOAD_CHUNK_BYTES:-${COLAB_UPLOAD_CHUNK_BYTES_DEFAULT:-33554432}}"
  local up_s="${COLAB_UPLOAD_TIMEOUT_S:-120}"
  if [[ "${max_bytes}" =~ ^[0-9]+$ ]] && [ "${max_bytes}" -le "${chunk}" ]; then
    echo 0
    return 0
  fi
  if [ -n "${COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S:-}" ]; then
    echo "${COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S}"
    return 0
  fi
  if [[ "${max_bytes}" =~ ^[0-9]+$ ]]; then
    awk -v b="${max_bytes}" -v r="${COLAB_UPLOAD_REASSEMBLE_MB_S:-${COLAB_UPLOAD_REASSEMBLE_MB_S_DEFAULT:-25}}" -v u="${up_s}" \
      'BEGIN { x = b / (r * 1000000.0); t = (x == int(x)) ? x : int(x) + 1; t = t + 30; if (t < u) t = u; printf "%d\n", t }'
    return 0
  fi
  echo 0
}

# colab_configure_download_timeout [cli_override] [forced_source] [part_count]: resolve the
# `colab download` timeout from `--download-timeout-s <s>` (precedence 1), `COLAB_DOWNLOAD_TIMEOUT_S`
# in the caller's environment (precedence 2), or `COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT` (300 s,
# precedence 3), and record the projected bundle `part_count` (default `${COLAB_SALVAGE_DOWNLOAD_PARTS:-1}`).
# Refuses DOWNLOAD_TIMEOUT_INVALID (exit 2) before `colab new` when non-positive or non-integer, and
# scales both normal and post-failure salvage download bounds + SALVAGE_DEADLINE_S across all
# projected salvage parts so cleanup_bound_s, the rig cap-budget gate, and window.json agree.
colab_configure_download_timeout() {
  local cli_val="${1:-}"
  local forced_src="${2:-}"
  local part_count="${3:-${COLAB_SALVAGE_DOWNLOAD_PARTS:-1}}"
  local chosen="${cli_val}"
  local src="cli"
  if [ -z "${chosen}" ]; then
    if [ -n "${COLAB_CALLER_DOWNLOAD_TIMEOUT_S}" ]; then
      chosen="${COLAB_CALLER_DOWNLOAD_TIMEOUT_S}"
      src="env"
    else
      chosen="${COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT}"
      src="default"
    fi
  fi
  if [ -n "${forced_src}" ]; then
    src="${forced_src}"
  fi
  if ! [[ "${chosen}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: DOWNLOAD_TIMEOUT_INVALID: download timeout '${chosen}' must be a positive integer (seconds)" >&2
    return 2
  fi
  if ! [[ "${part_count}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: DOWNLOAD_TIMEOUT_INVALID: salvage download part_count '${part_count}' must be a positive integer" >&2
    return 2
  fi
  export COLAB_DOWNLOAD_TIMEOUT_S="${chosen}"
  export COLAB_DOWNLOAD_TIMEOUT_SOURCE="${src}"
  export COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S="${chosen}"
  export COLAB_SALVAGE_DOWNLOAD_PARTS="${part_count}"
  export SALVAGE_DEADLINE_S="$(colab_salvage_steps_sum_s)"
}

# colab_configure_upload_timeout [cli_override]: resolve the `colab upload` timeout from
# `--upload-timeout-s <s>` (precedence 1), `COLAB_UPLOAD_TIMEOUT_S` in the caller's environment
# (precedence 2), or `COLAB_UPLOAD_TIMEOUT_S_DEFAULT` (120 s, precedence 3). Refuses
# UPLOAD_TIMEOUT_INVALID (exit 2) before `colab new` when non-positive or non-integer.
colab_configure_upload_timeout() {
  local cli_val="${1:-}"
  local chosen="${cli_val}"
  local src="cli"
  if [ -z "${chosen}" ]; then
    if [ -n "${COLAB_CALLER_UPLOAD_TIMEOUT_S}" ]; then
      chosen="${COLAB_CALLER_UPLOAD_TIMEOUT_S}"
      src="env"
    else
      chosen="${COLAB_UPLOAD_TIMEOUT_S_DEFAULT}"
      src="default"
    fi
  fi
  if ! [[ "${chosen}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: UPLOAD_TIMEOUT_INVALID: upload timeout '${chosen}' must be a positive integer (seconds)" >&2
    return 2
  fi
  export COLAB_UPLOAD_TIMEOUT_S="${chosen}"
  export COLAB_UPLOAD_TIMEOUT_SOURCE="${src}"
}

# colab_configure_upload_reassemble_timeout [cli_timeout_s] [cli_mb_s]: configure the VM-side
# chunked-upload reassembly `colab exec` bound: either an explicit positive-integer timeout
# (`--upload-reassemble-timeout-s` / `COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S`) or derived from file size
# and stated VM disk+hash throughput (`--upload-reassemble-mb-s` / `COLAB_UPLOAD_REASSEMBLE_MB_S`,
# default 25 MB/s, floored at `COLAB_UPLOAD_TIMEOUT_S`). Refuses UPLOAD_TIMEOUT_INVALID (exit 2)
# before `colab new` when malformed or non-positive.
colab_configure_upload_reassemble_timeout() {
  local cli_timeout="${1:-}"
  local cli_rate="${2:-}"
  local chosen_timeout="${cli_timeout}"
  local timeout_src="cli"
  if [ -z "${chosen_timeout}" ]; then
    if [ -n "${COLAB_CALLER_UPLOAD_REASSEMBLE_TIMEOUT_S}" ]; then
      chosen_timeout="${COLAB_CALLER_UPLOAD_REASSEMBLE_TIMEOUT_S}"
      timeout_src="env"
    else
      chosen_timeout=""
      timeout_src="size_and_rate"
    fi
  fi
  if [ -n "${chosen_timeout}" ] && ! [[ "${chosen_timeout}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: UPLOAD_TIMEOUT_INVALID: upload reassemble timeout '${chosen_timeout}' must be a positive integer (seconds)" >&2
    return 2
  fi
  local chosen_rate="${cli_rate}"
  local rate_src="cli"
  if [ -z "${chosen_rate}" ]; then
    if [ -n "${COLAB_CALLER_UPLOAD_REASSEMBLE_MB_S}" ]; then
      chosen_rate="${COLAB_CALLER_UPLOAD_REASSEMBLE_MB_S}"
      rate_src="env"
    else
      chosen_rate="${COLAB_UPLOAD_REASSEMBLE_MB_S_DEFAULT}"
      rate_src="default"
    fi
  fi
  if ! [[ "${chosen_rate}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${chosen_rate}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: UPLOAD_TIMEOUT_INVALID: upload reassemble rate '${chosen_rate}' must be a positive number (MB/s)" >&2
    return 2
  fi
  export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S="${chosen_timeout}"
  export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_SOURCE="${timeout_src}"
  export COLAB_UPLOAD_REASSEMBLE_MB_S="${chosen_rate}"
  export COLAB_UPLOAD_REASSEMBLE_MB_S_SOURCE="${rate_src}"
}

# colab_configure_upload_chunk_bytes [cli_override]: resolve `COLAB_UPLOAD_CHUNK_BYTES` from
# `--upload-chunk-bytes <int>` (precedence 1), `COLAB_UPLOAD_CHUNK_BYTES` in the caller's environment
# (precedence 2), or `COLAB_UPLOAD_CHUNK_BYTES_DEFAULT` (33554432 = 32 MiB, precedence 3). Refuses
# UPLOAD_CHUNK_BYTES_INVALID (exit 2) before `colab new` when non-positive or non-integer.
colab_configure_upload_chunk_bytes() {
  local cli_val="${1:-}"
  local chosen="${cli_val}"
  local src="cli"
  if [ -z "${chosen}" ]; then
    if [ -n "${COLAB_CALLER_UPLOAD_CHUNK_BYTES}" ]; then
      chosen="${COLAB_CALLER_UPLOAD_CHUNK_BYTES}"
      src="env"
    else
      chosen="${COLAB_UPLOAD_CHUNK_BYTES_DEFAULT}"
      src="default"
    fi
  fi
  if ! [[ "${chosen}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: UPLOAD_CHUNK_BYTES_INVALID: upload chunk size '${chosen}' must be a positive integer (bytes)" >&2
    return 2
  fi
  export COLAB_UPLOAD_CHUNK_BYTES="${chosen}"
  export COLAB_UPLOAD_CHUNK_SOURCE="${src}"
}

# colab_configure_download_chunk_bytes [cli_override]: resolve `COLAB_DOWNLOAD_CHUNK_BYTES` from
# `--download-chunk-bytes <int>` (precedence 1), `COLAB_DOWNLOAD_CHUNK_BYTES` in the caller's
# environment (precedence 2), or `COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT` (268435456 = 256 MiB,
# precedence 3). Refuses DOWNLOAD_CHUNK_BYTES_INVALID (exit 2) before `colab new` when non-positive
# or non-integer.
colab_configure_download_chunk_bytes() {
  local cli_val="${1:-}"
  local chosen="${cli_val}"
  local src="cli"
  if [ -z "${chosen}" ]; then
    if [ -n "${COLAB_CALLER_DOWNLOAD_CHUNK_BYTES}" ]; then
      chosen="${COLAB_CALLER_DOWNLOAD_CHUNK_BYTES}"
      src="env"
    else
      chosen="${COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT}"
      src="default"
    fi
  fi
  if ! [[ "${chosen}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: DOWNLOAD_CHUNK_BYTES_INVALID: download chunk size '${chosen}' must be a positive integer (bytes)" >&2
    return 2
  fi
  export COLAB_DOWNLOAD_CHUNK_BYTES="${chosen}"
  export COLAB_DOWNLOAD_CHUNK_SOURCE="${src}"
}

# colab_apply_test_cleanup_overrides <test_mode>: in fake-colab test mode only, allow short per-step
# timeouts and salvage deadline so tests can exercise hung children and `timeout -k` in seconds.
colab_apply_test_cleanup_overrides() {
  local test_mode="$1"
  [ "${test_mode}" = "1" ] || return 0
  if [ -n "${SDLAB_TEST_KILL_GRACE_S:-}" ]; then
    export COLAB_KILL_GRACE_S="${SDLAB_TEST_KILL_GRACE_S}"
  fi
  if [ -n "${SDLAB_TEST_OPEN_LOCK_TIMEOUT_S:-}" ]; then
    export COLAB_OPEN_LOCK_TIMEOUT_S="${SDLAB_TEST_OPEN_LOCK_TIMEOUT_S}"
  fi
  if [ -n "${SDLAB_TEST_NEW_TIMEOUT_S:-}" ]; then
    export COLAB_NEW_TIMEOUT_S="${SDLAB_TEST_NEW_TIMEOUT_S}"
  fi
  if [ -n "${SDLAB_TEST_UPLOAD_TIMEOUT_S:-}" ]; then
    export COLAB_UPLOAD_TIMEOUT_S="${SDLAB_TEST_UPLOAD_TIMEOUT_S}"
  fi
  if [ -n "${SDLAB_TEST_UPLOAD_REASSEMBLE_TIMEOUT_S:-}" ]; then
    export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S="${SDLAB_TEST_UPLOAD_REASSEMBLE_TIMEOUT_S}"
    export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_SOURCE="test_override"
  fi
  if [ -n "${SDLAB_TEST_UPLOAD_REASSEMBLE_MB_S:-}" ]; then
    export COLAB_UPLOAD_REASSEMBLE_MB_S="${SDLAB_TEST_UPLOAD_REASSEMBLE_MB_S}"
    export COLAB_UPLOAD_REASSEMBLE_MB_S_SOURCE="test_override"
  fi
  if [ -n "${SDLAB_TEST_UPLOAD_CHUNK_BYTES:-}" ]; then
    export COLAB_UPLOAD_CHUNK_BYTES="${SDLAB_TEST_UPLOAD_CHUNK_BYTES}"
    export COLAB_UPLOAD_CHUNK_SOURCE="test_override"
  fi
  if [ -n "${SDLAB_TEST_DOWNLOAD_CHUNK_BYTES:-}" ]; then
    export COLAB_DOWNLOAD_CHUNK_BYTES="${SDLAB_TEST_DOWNLOAD_CHUNK_BYTES}"
    export COLAB_DOWNLOAD_CHUNK_SOURCE="test_override"
  fi
  if [ -n "${SDLAB_TEST_WALL_ESCALATE_S:-}" ]; then
    export COLAB_WALL_ESCALATE_S="${SDLAB_TEST_WALL_ESCALATE_S}"
  fi
  if [ -n "${SDLAB_TEST_DOWNLOAD_TIMEOUT_S:-}" ]; then
    export COLAB_DOWNLOAD_TIMEOUT_S="${SDLAB_TEST_DOWNLOAD_TIMEOUT_S}"
    export COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S="${SDLAB_TEST_DOWNLOAD_TIMEOUT_S}"
    if [ -z "${SDLAB_TEST_UPLOAD_TIMEOUT_S:-}" ] && [ "${COLAB_UPLOAD_TIMEOUT_S}" -gt "${COLAB_DOWNLOAD_TIMEOUT_S}" ]; then
      export COLAB_UPLOAD_TIMEOUT_S="${SDLAB_TEST_DOWNLOAD_TIMEOUT_S}"
    fi
    if [ -z "${SDLAB_TEST_SESSIONS_TIMEOUT_S:-}" ] && [ "${COLAB_SESSIONS_TIMEOUT_S}" -gt "${COLAB_DOWNLOAD_TIMEOUT_S}" ]; then
      export COLAB_SESSIONS_TIMEOUT_S="${SDLAB_TEST_DOWNLOAD_TIMEOUT_S}"
    fi
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
  local step_sum
  step_sum="$(colab_salvage_steps_sum_s)"
  if [ -n "${SDLAB_TEST_SALVAGE_DEADLINE_S:-}" ]; then
    export SALVAGE_DEADLINE_S="${SDLAB_TEST_SALVAGE_DEADLINE_S}"
  else
    export SALVAGE_DEADLINE_S="${step_sum}"
  fi
}

# colab_compute_cleanup_bounds <lane>: compute and export COLAB_CLEANUP_STOP_ATTEMPTED_BY_S and
# COLAB_CLEANUP_BOUND_S measured from the trip for <lane> ("train" = 1150 s / 1290 s for N=1,
# 1460 s / 1600 s for N=2; "render" = 310 s / 450 s default): longest in-flight bounded step +
# salvage (scaled by projected part_count) + stop, so the pre-open cap budget check, --dry, the
# live cap guard, and window.json all share one figure.
colab_compute_cleanup_bounds() {
  local lane="$1"
  local kill_grace_s="${COLAB_KILL_GRACE_S:-10}"
  local dl_timeout_s="${COLAB_DOWNLOAD_TIMEOUT_S:-300}"
  local up_timeout_s="${COLAB_UPLOAD_TIMEOUT_S:-120}"
  local sess_timeout_s="${COLAB_SESSIONS_TIMEOUT_S:-30}"
  # The longest single bounded step that can be in flight when a guard trips: a download or upload
  # step, a sessions poll, the VM download-prepare exec (min(download timeout, 180 s)), or the VM
  # upload-reassembly exec (explicit timeout, or size-and-rate over the largest upload).
  local prep_exec_s="${dl_timeout_s}"
  [ "${prep_exec_s}" -gt 180 ] && prep_exec_s=180
  local reassemble_s=0
  reassemble_s="$(colab_reassemble_bound_s)"
  local in_flight_step_s="${dl_timeout_s}"
  local cand_s
  for cand_s in "${up_timeout_s}" "${sess_timeout_s}" "${prep_exec_s}" "${reassemble_s}"; do
    if [ "${cand_s}" -gt "${in_flight_step_s}" ]; then
      in_flight_step_s="${cand_s}"
    fi
  done
  local in_flight_bound_s=$(( in_flight_step_s + kill_grace_s ))
  local salvage_restart_s="${COLAB_SALVAGE_RESTART_TIMEOUT_S:-180}"
  local salvage_exec_s="${COLAB_SALVAGE_EXEC_TIMEOUT_S:-330}"
  local salvage_download_s="${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S:-300}"
  local salvage_steps_sum
  salvage_steps_sum="$(colab_salvage_steps_sum_s)"
  local salvage_deadline_s="${SALVAGE_DEADLINE_S:-${salvage_steps_sum}}"
  local stop_timeout_s="${COLAB_STOP_TIMEOUT_S:-60}"
  local stop_attempts="${COLAB_STOP_ATTEMPTS:-2}"
  local stop_bound_s=$(( stop_attempts * (stop_timeout_s + kill_grace_s) ))
  local salvage_bound_s=0
  # A real `--render` window (COLAB_RENDER_SALVAGE=1, set by the lane 1 kit) keeps what it rendered on a trip, so
  # its cleanup pays the same bounded salvage the train lane does; the stubs keep no salvage.
  if [ "${lane}" = "train" ] || { [ "${lane}" = "render" ] && [ "${COLAB_RENDER_SALVAGE:-0}" = "1" ]; }; then
    salvage_bound_s="${salvage_steps_sum}"
    if [ "${salvage_deadline_s}" -lt "${salvage_bound_s}" ]; then
      salvage_bound_s="${salvage_deadline_s}"
    fi
  fi
  local cleanup_stop_attempted_by_s=$(( in_flight_bound_s + salvage_bound_s ))
  export COLAB_LANE="${lane}"
  export COLAB_IN_FLIGHT_BOUND_S="${in_flight_bound_s}"
  export COLAB_REASSEMBLE_BOUND_S="${reassemble_s}"
  export COLAB_PREP_EXEC_BOUND_S="${prep_exec_s}"
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
    if [ -n "${COLAB_ACTIVE_OUT_DIR:-}" ] && [ -d "${COLAB_ACTIVE_OUT_DIR}" ]; then
      printf '%s\n' "${BASHPID:-$$}" >> "${COLAB_ACTIVE_OUT_DIR}/.watcher_tracked_pids.txt" 2>/dev/null || true
    fi
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
# before `colab stop`. A second signal sets COLAB_CLEANUP_SKIP_SALVAGE=1 and kills any in-flight
# salvage step so cleanup skips remaining salvage and goes straight to `colab stop`.
colab_on_cleanup_signal() {
  local out_dir="$1"
  COLAB_CLEANUP_SIGNAL_COUNT=$((COLAB_CLEANUP_SIGNAL_COUNT + 1))
  local action="continue_bounded_cleanup"
  if [ "${COLAB_CLEANUP_SIGNAL_COUNT}" -ge 2 ]; then
    COLAB_CLEANUP_SKIP_SALVAGE=1
    action="skip_remaining_salvage"
    if [ -n "${COLAB_SALVAGE_STEP_PID:-}" ]; then
      pkill -9 -P "${COLAB_SALVAGE_STEP_PID}" 2>/dev/null || true
      kill -9 "${COLAB_SALVAGE_STEP_PID}" 2>/dev/null || true
    fi
  fi
  if [ -n "${out_dir}" ] && [ -d "${out_dir}" ]; then
    printf 'CLEANUP_SIGNAL count=%s action=%s\n' "${COLAB_CLEANUP_SIGNAL_COUNT}" "${action}" >> "${out_dir}/guards.log"
  fi
}

# colab_run_bounded_salvage_step <timeout_s> <kill_grace_s> <cmd> [args...]: run a salvage step in a
# backgrounded Python wrapper that resets SIGTERM and SIGINT to SIG_DFL and execs `timeout -k`, while
# waiting in an interruptible `wait` loop in the main shell so a first TERM logs and continues and a
# second TERM aborts the in-flight salvage step immediately.
colab_run_bounded_salvage_step() {
  local timeout_s="$1"
  local kill_grace_s="$2"
  shift 2
  local py_bin="${PY_BIN:-$(colab_resolve_python)}"
  "${py_bin}" -c '
import os, signal, sys
signal.signal(signal.SIGTERM, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.SIG_DFL)
os.execvp("timeout", ["timeout", "-k", sys.argv[1], sys.argv[2], *sys.argv[3:]])
' "${kill_grace_s}" "${timeout_s}" "$@" </dev/null &
  COLAB_SALVAGE_STEP_PID="$!"
  if [ -n "${COLAB_ACTIVE_OUT_DIR:-}" ] && [ -d "${COLAB_ACTIVE_OUT_DIR}" ]; then
    printf '%s\n' "${COLAB_SALVAGE_STEP_PID}" >> "${COLAB_ACTIVE_OUT_DIR}/.watcher_tracked_pids.txt" 2>/dev/null || true
  fi
  local step_rc=0
  while true; do
    step_rc=0
    wait "${COLAB_SALVAGE_STEP_PID}" 2>/dev/null || step_rc=$?
    if ! kill -0 "${COLAB_SALVAGE_STEP_PID}" 2>/dev/null; then
      break
    fi
    if [ "${COLAB_CLEANUP_SKIP_SALVAGE:-0}" = "1" ]; then
      pkill -9 -P "${COLAB_SALVAGE_STEP_PID}" 2>/dev/null || true
      kill -9 "${COLAB_SALVAGE_STEP_PID}" 2>/dev/null || true
      wait "${COLAB_SALVAGE_STEP_PID}" 2>/dev/null || true
      step_rc=143
      break
    fi
  done
  COLAB_SALVAGE_STEP_PID=""
  return "${step_rc}"
}

# colab_enter_cleanup_trap <out_dir>: arm cleanup signal handling and record the cleanup start
# epoch (`time.time()` float seconds, matching wall_trip_epoch.txt) in cleanup_started.txt
# at the very top of `cleanup_on_exit` (before post-failure salvage) so `colab_run_wall_watcher`
# knows the main shell entered cleanup and waits up to COLAB_CLEANUP_STOP_ATTEMPTED_BY_S for salvage.
colab_enter_cleanup_trap() {
  local out_dir="$1"
  if [ -n "${out_dir}" ] && [ -d "${out_dir}" ] && [ ! -f "${out_dir}/cleanup_started.txt" ]; then
    local py_bin="${PY_BIN:-$(colab_resolve_python)}"
    "${py_bin}" -c 'import sys, time; open(sys.argv[1], "w", encoding="utf-8").write(f"{time.time():.6f}\n")' "${out_dir}/cleanup_started.txt" 2>/dev/null \
      || date -u +%s > "${out_dir}/cleanup_started.txt"
  fi
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

# colab_upload_raw_bounded <session> <local> <remote> <timeout_s> <kill_grace_s>: run one single-PUT
# `colab upload` under `colab_run_bounded`, printing captured CLI output on stdout and returning the
# CLI exit code. Shared by `colab_upload_checked` and `probe_upload_limit.sh`.
colab_upload_raw_bounded() {
  local session="$1"
  local src="$2"
  local dst="$3"
  local timeout_s="$4"
  local kill_grace_s="$5"
  colab_run_bounded "${timeout_s}" "${kill_grace_s}" colab upload -s "${session}" "${src}" "${dst}" 2>&1
}

# colab_download_raw_bounded <session> <remote> <local> <timeout_s> <kill_grace_s>: run one single-GET
# `colab download` under `colab_run_bounded`, printing captured CLI output on stdout and returning the
# CLI exit code. Shared by `colab_download_checked` and `probe_upload_limit.sh`.
colab_download_raw_bounded() {
  local session="$1"
  local src="$2"
  local dst="$3"
  local timeout_s="$4"
  local kill_grace_s="$5"
  colab_run_bounded "${timeout_s}" "${kill_grace_s}" colab download -s "${session}" "${src}" "${dst}" 2>&1
}

_colab_resolve_helper_python() {
  if [ -n "${PY_BIN:-}" ]; then
    printf '%s' "${PY_BIN}"
  else
    colab_resolve_python
  fi
}

# colab_upload_checked <session> <local> <remote> <out_dir>: upload one file flat into COLAB_REMOTE_ROOT.
# - Files <= COLAB_UPLOAD_CHUNK_BYTES (default 32 MiB = 33554432): uploaded in a single `colab upload`
#   (retried once on HTTP 5xx), bounded by `timeout -k ${COLAB_KILL_GRACE_S} ${COLAB_UPLOAD_TIMEOUT_S}`.
# - Files > COLAB_UPLOAD_CHUNK_BYTES: split on the rig into parts <= COLAB_UPLOAD_CHUNK_BYTES (each
#   with its own sha256 + whole-file sha256), uploaded flat one part at a time under per-part
#   `${COLAB_UPLOAD_TIMEOUT_S}` (1 retry per part on HTTP 5xx; second failure refuses UPLOAD_PART_FAILED),
#   reassembled in order on the VM, whole-file sha256 verified against the rig's before use (refusing
#   UPLOAD_SHA_MISMATCH and removing target + parts on any mismatch), and parts deleted on the VM.
# Every upload records chunk_bytes and part_count in `${out_dir}/upload_receipts.jsonl`.
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
  local chunk_bytes="${COLAB_UPLOAD_CHUNK_BYTES:-${COLAB_UPLOAD_CHUNK_BYTES_DEFAULT}}"
  if ! [[ "${chunk_bytes}" =~ ^[1-9][0-9]*$ ]]; then
    colab_refuse_logged "${out_dir}" UPLOAD_CHUNK_BYTES_INVALID "COLAB_UPLOAD_CHUNK_BYTES='${chunk_bytes}' must be a positive integer (bytes)"
    return 2
  fi
  colab_check_pre_exec_cap "${out_dir}" "pre_upload" || return 1

  local py_bin
  py_bin="$(_colab_resolve_helper_python)"
  local upload_timeout="${COLAB_UPLOAD_TIMEOUT_S:-120}"
  local kill_grace="${COLAB_KILL_GRACE_S:-10}"

  local file_bytes="" rig_sha=""
  read -r file_bytes rig_sha < <(
    "${py_bin}" -c '
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
h = hashlib.sha256()
sz = 0
with p.open("rb") as fh:
    for blk in iter(lambda: fh.read(1 << 20), b""):
        sz += len(blk)
        h.update(blk)
print(sz, h.hexdigest())
' "${src}" | tr -d '\r'
  )

  # Single-request fast path when file_bytes <= COLAB_UPLOAD_CHUNK_BYTES.
  if [ "${file_bytes}" -le "${chunk_bytes}" ]; then
    local out="" rc=0 attempts=1 retries=0 http_st="none"
    out="$(colab_upload_raw_bounded "${session}" "${src}" "${dst}" "${upload_timeout}" "${kill_grace}")" || rc=$?
    printf '%s\n' "${out}" >> "${out_dir}/colab.log"
    if colab_rc_is_timeout "${rc}"; then
      echo "UPLOAD_TIMEOUT ${src} -> ${dst} timeout_s=${upload_timeout} kill_grace_s=${kill_grace} rc=${rc}" >> "${out_dir}/guards.log"
    elif [ "${rc}" -ne 0 ] || ! grep -Fq "[colab] Uploaded '" <<< "${out}"; then
      http_st="$(_colab_http_status "${out}")"
      if [[ "${http_st}" =~ ^5[0-9]{2}$ ]]; then
        colab_check_pre_exec_cap "${out_dir}" "pre_upload_retry" || return 1
        attempts=2
        retries=1
        echo "UPLOAD_RETRY ${src} -> ${dst} http=${http_st} attempt=2/2" >> "${out_dir}/guards.log"
        rc=0
        out="$(colab_upload_raw_bounded "${session}" "${src}" "${dst}" "${upload_timeout}" "${kill_grace}")" || rc=$?
        printf '%s\n' "${out}" >> "${out_dir}/colab.log"
        if colab_rc_is_timeout "${rc}"; then
          echo "UPLOAD_TIMEOUT ${src} -> ${dst} timeout_s=${upload_timeout} kill_grace_s=${kill_grace} rc=${rc}" >> "${out_dir}/guards.log"
        fi
      fi
    fi
    if [ "${rc}" -ne 0 ] || ! grep -Fq "[colab] Uploaded '" <<< "${out}"; then
      http_st="$(_colab_http_status "${out}")"
      "${py_bin}" -c '
import json, pathlib, sys
rec = {
    "local": sys.argv[2], "remote": sys.argv[3], "mode": "single",
    "bytes": int(sys.argv[4]), "sha256": sys.argv[5],
    "chunk_bytes": int(sys.argv[6]), "part_count": 1,
    "retries": int(sys.argv[7]), "http_status": sys.argv[8], "ok": False,
}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${out_dir}/upload_receipts.jsonl" "${src}" "${dst}" "${file_bytes}" "${rig_sha}" "${chunk_bytes}" "${retries}" "${http_st}"
      colab_refuse_logged "${out_dir}" UPLOAD_FAILED "${src} -> ${dst}: colab upload rc=${rc} http=${http_st} attempts=${attempts} (CLI output in colab.log)"
      return 1
    fi
    "${py_bin}" -c '
import json, pathlib, sys
rec = {
    "local": sys.argv[2], "remote": sys.argv[3], "mode": "single",
    "bytes": int(sys.argv[4]), "sha256": sys.argv[5],
    "chunk_bytes": int(sys.argv[6]), "part_count": 1,
    "retries": int(sys.argv[7]), "ok": True,
}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${out_dir}/upload_receipts.jsonl" "${src}" "${dst}" "${file_bytes}" "${rig_sha}" "${chunk_bytes}" "${retries}"
    colab_check_pre_exec_cap "${out_dir}" "post_upload" || return 1
    return 0
  fi

  # Chunked upload path: split on rig -> upload flat parts with 1 retry on 5xx -> VM reassemble + whole-file sha256 check -> delete VM parts.
  local dst_name="${dst##*/}"
  local tmp_up_dir="${out_dir}/.sdlab_up_tmp_$$_${RANDOM}"
  mkdir -p "${tmp_up_dir}"
  local split_meta=""
  if ! split_meta="$("${py_bin}" - "${src}" "${dst_name}" "${chunk_bytes}" "${rig_sha}" "${tmp_up_dir}" << 'PYEOF'
import hashlib
import json
import os
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst_name = sys.argv[2]
chunk_bytes = int(sys.argv[3])
whole_sha = sys.argv[4]
tmp_dir = Path(sys.argv[5])

safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", dst_name)[:48]
nonce = hashlib.sha256(f"{dst_name}:{whole_sha}:{os.getpid()}".encode("utf-8")).hexdigest()[:10]
prefix = f".sdlab_up_{safe_base}_{nonce}"
parts = []
total = 0
idx = 0
with src.open("rb") as fh:
    while True:
        buf = fh.read(chunk_bytes)
        if not buf:
            break
        part_local = tmp_dir / f"part.{idx:04d}"
        part_local.write_bytes(buf)
        part_sha = hashlib.sha256(buf).hexdigest()
        remote_name = f"{prefix}.part.{idx:04d}"
        parts.append({
            "index": idx,
            "local_name": part_local.name,
            "remote_name": remote_name,
            "bytes": len(buf),
            "sha256": part_sha,
        })
        total += len(buf)
        idx += 1

manifest_remote_name = f"{prefix}.manifest.json"
manifest = {
    "target_name": dst_name,
    "prefix": prefix,
    "whole_bytes": total,
    "whole_sha256": whole_sha,
    "chunk_bytes": chunk_bytes,
    "part_count": len(parts),
    "parts": [
        {
            "index": p["index"],
            "remote_name": p["remote_name"],
            "bytes": p["bytes"],
            "sha256": p["sha256"],
        }
        for p in parts
    ],
}
(tmp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
lines = [f"META {len(parts)} {manifest_remote_name} {prefix}"]
for p in parts:
    lines.append(f"PART {p['index']} {p['local_name']} {p['remote_name']}")
print("\n".join(lines))
PYEOF
  )"; then
    rm -rf "${tmp_up_dir}"
    colab_refuse_logged "${out_dir}" UPLOAD_PART_FAILED "${src} -> ${dst}: failed to split file into ${chunk_bytes}-byte chunks on rig"
    return 1
  fi

  local part_count=0 manifest_remote_name="" up_prefix=""
  local part_indices=() part_locals=() part_remotes=()
  while IFS=' ' read -r tag f1 f2 f3; do
    tag="${tag//$'\r'/}"
    f3="${f3//$'\r'/}"
    if [ "${tag}" = "META" ]; then
      part_count="${f1}"
      manifest_remote_name="${f2}"
      up_prefix="${f3}"
    elif [ "${tag}" = "PART" ]; then
      part_indices+=("${f1}")
      part_locals+=("${f2}")
      part_remotes+=("${f3}")
    fi
  done <<< "${split_meta}"

  cat > "${tmp_up_dir}/cleanup_parts.py" << 'PYEOF'
import os
from pathlib import Path

root = Path(os.environ["SDLAB_CONTENT"])
prefix = os.environ["SDLAB_UP_PREFIX"]
for fp in root.iterdir():
    if fp.name.startswith(prefix + ".") and fp.is_file():
        fp.unlink(missing_ok=True)
print("SDLAB_UPLOAD_CLEANUP_OK", flush=True)
PYEOF

  local total_retries=0
  local uploaded_parts=0
  local k=0
  while [ "${k}" -lt "${part_count}" ]; do
    if ! colab_check_pre_exec_cap "${out_dir}" "pre_upload_part_${k}"; then
      rm -rf "${tmp_up_dir}"
      return 1
    fi
    local p_local="${tmp_up_dir}/${part_locals[$k]}"
    local p_remote="${COLAB_REMOTE_ROOT}/${part_remotes[$k]}"
    local p_num=$((k + 1))
    local out="" rc=0 attempts=1 http_st="none"
    out="$(colab_upload_raw_bounded "${session}" "${p_local}" "${p_remote}" "${upload_timeout}" "${kill_grace}")" || rc=$?
    printf '%s\n' "${out}" >> "${out_dir}/colab.log"
    if colab_rc_is_timeout "${rc}"; then
      echo "UPLOAD_TIMEOUT ${src} -> ${dst} part=${p_num}/${part_count} timeout_s=${upload_timeout} kill_grace_s=${kill_grace} rc=${rc}" >> "${out_dir}/guards.log"
    elif [ "${rc}" -ne 0 ] || ! grep -Fq "[colab] Uploaded '" <<< "${out}"; then
      http_st="$(_colab_http_status "${out}")"
      if [[ "${http_st}" =~ ^5[0-9]{2}$ ]]; then
        if ! colab_check_pre_exec_cap "${out_dir}" "pre_upload_part_retry_${k}"; then
          rm -rf "${tmp_up_dir}"
          return 1
        fi
        attempts=2
        total_retries=$((total_retries + 1))
        echo "UPLOAD_PART_RETRY ${src} -> ${dst} part=${p_num}/${part_count} http=${http_st} attempt=2/2" >> "${out_dir}/guards.log"
        rc=0
        out="$(colab_upload_raw_bounded "${session}" "${p_local}" "${p_remote}" "${upload_timeout}" "${kill_grace}")" || rc=$?
        printf '%s\n' "${out}" >> "${out_dir}/colab.log"
        if colab_rc_is_timeout "${rc}"; then
          echo "UPLOAD_TIMEOUT ${src} -> ${dst} part=${p_num}/${part_count} timeout_s=${upload_timeout} kill_grace_s=${kill_grace} rc=${rc}" >> "${out_dir}/guards.log"
        fi
      fi
    fi
    if [ "${rc}" -ne 0 ] || ! grep -Fq "[colab] Uploaded '" <<< "${out}"; then
      http_st="$(_colab_http_status "${out}")"
      if [ "${uploaded_parts}" -gt 0 ] && ! colab_rc_is_timeout "${rc}"; then
        local clean_t="${upload_timeout}"
        [ "${clean_t}" -gt 30 ] && clean_t=30
        colab_run_bounded "${clean_t}" "${kill_grace}" colab exec -s "${session}" -f "${tmp_up_dir}/cleanup_parts.py" \
          --timeout "${clean_t}" --env "SDLAB_CONTENT=/content" --env "SDLAB_UP_PREFIX=${up_prefix}" >> "${out_dir}/colab.log" 2>&1 || true
      fi
      rm -rf "${tmp_up_dir}"
      "${py_bin}" -c '
import json, pathlib, sys
rec = {
    "local": sys.argv[2], "remote": sys.argv[3], "mode": "chunked",
    "bytes": int(sys.argv[4]), "sha256": sys.argv[5],
    "chunk_bytes": int(sys.argv[6]), "part_count": int(sys.argv[7]),
    "uploaded_parts": int(sys.argv[8]), "failed_part": int(sys.argv[9]),
    "retries": int(sys.argv[10]), "http_status": sys.argv[11], "ok": False,
}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${out_dir}/upload_receipts.jsonl" "${src}" "${dst}" "${file_bytes}" "${rig_sha}" "${chunk_bytes}" "${part_count}" "${uploaded_parts}" "${k}" "${total_retries}" "${http_st}"
      colab_refuse_logged "${out_dir}" UPLOAD_PART_FAILED "${src} -> ${dst} part ${p_num}/${part_count}: colab upload rc=${rc} http=${http_st} attempts=${attempts} (CLI output in colab.log)"
      return 1
    fi
    rm -f "${p_local}"
    uploaded_parts=$((uploaded_parts + 1))
    k=$((k + 1))
  done

  # Upload the small reassembly manifest flat into /content (with 1 retry on 5xx).
  local man_remote="${COLAB_REMOTE_ROOT}/${manifest_remote_name}"
  local m_out="" m_rc=0 m_http="none"
  m_out="$(colab_upload_raw_bounded "${session}" "${tmp_up_dir}/manifest.json" "${man_remote}" "${upload_timeout}" "${kill_grace}")" || m_rc=$?
  printf '%s\n' "${m_out}" >> "${out_dir}/colab.log"
  if [ "${m_rc}" -ne 0 ] || ! grep -Fq "[colab] Uploaded '" <<< "${m_out}"; then
    m_http="$(_colab_http_status "${m_out}")"
    if ! colab_rc_is_timeout "${m_rc}" && [[ "${m_http}" =~ ^5[0-9]{2}$ ]]; then
      total_retries=$((total_retries + 1))
      m_rc=0
      m_out="$(colab_upload_raw_bounded "${session}" "${tmp_up_dir}/manifest.json" "${man_remote}" "${upload_timeout}" "${kill_grace}")" || m_rc=$?
      printf '%s\n' "${m_out}" >> "${out_dir}/colab.log"
    fi
  fi
  if [ "${m_rc}" -ne 0 ] || ! grep -Fq "[colab] Uploaded '" <<< "${m_out}"; then
    m_http="$(_colab_http_status "${m_out}")"
    rm -rf "${tmp_up_dir}"
    colab_refuse_logged "${out_dir}" UPLOAD_PART_FAILED "${src} -> ${dst} manifest: colab upload rc=${m_rc} http=${m_http} (CLI output in colab.log)"
    return 1
  fi

  cat > "${tmp_up_dir}/reassemble_upload.py" << 'PYEOF'
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["SDLAB_CONTENT"])
manifest_path = root / os.environ["SDLAB_UP_MANIFEST"]


def _emit(payload: dict) -> None:
    print("SDLAB_UPLOAD_REASSEMBLE_JSON " + json.dumps(payload), flush=True)


if not manifest_path.is_file():
    _emit({"ok": False, "code": "UPLOAD_PART_FAILED", "detail": f"missing manifest {manifest_path.name} on VM"})
    raise SystemExit(1)

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
target_name = manifest["target_name"]
prefix = manifest["prefix"]
exp_whole_bytes = int(manifest["whole_bytes"])
exp_whole_sha = str(manifest["whole_sha256"]).lower()
parts = manifest["parts"]
target_path = root / target_name
tmp_target = root / f"{prefix}.reassembling"

missing_parts = []
bad_parts = []
try:
    with tmp_target.open("wb") as out_fh:
        for p in parts:
            idx = int(p["index"])
            p_path = root / p["remote_name"]
            if not p_path.is_file():
                missing_parts.append(idx)
                continue
            p_hasher = hashlib.sha256()
            p_bytes = 0
            with p_path.open("rb") as in_fh:
                for blk in iter(lambda: in_fh.read(1 << 20), b""):
                    p_bytes += len(blk)
                    p_hasher.update(blk)
                    out_fh.write(blk)
            if p_bytes != int(p["bytes"]) or p_hasher.hexdigest().lower() != str(p["sha256"]).lower():
                bad_parts.append(idx)

    if missing_parts:
        tmp_target.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        _emit({
            "ok": False,
            "code": "UPLOAD_PART_FAILED",
            "detail": f"{target_name}: missing part(s) {missing_parts} on VM",
        })
        raise SystemExit(1)

    whole_hasher = hashlib.sha256()
    got_whole_bytes = 0
    with tmp_target.open("rb") as verify_fh:
        for blk in iter(lambda: verify_fh.read(1 << 20), b""):
            got_whole_bytes += len(blk)
            whole_hasher.update(blk)
    got_whole_sha = whole_hasher.hexdigest().lower()

    if got_whole_bytes != exp_whole_bytes or got_whole_sha != exp_whole_sha or bad_parts:
        tmp_target.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        _emit({
            "ok": False,
            "code": "UPLOAD_SHA_MISMATCH",
            "detail": (
                f"{target_name}: VM whole-file sha256={got_whole_sha} (bytes={got_whole_bytes}) "
                f"!= rig sha256={exp_whole_sha} (bytes={exp_whole_bytes}); bad_parts={bad_parts}"
            ),
        })
        raise SystemExit(1)

    os.replace(tmp_target, target_path)
    _emit({
        "ok": True,
        "bytes": got_whole_bytes,
        "sha256": got_whole_sha,
        "part_count": len(parts),
    })
finally:
    manifest_path.unlink(missing_ok=True)
    tmp_target.unlink(missing_ok=True)
    for p in parts:
        (root / p["remote_name"]).unlink(missing_ok=True)
PYEOF

  local reassemble_mb_s="${COLAB_UPLOAD_REASSEMBLE_MB_S:-${COLAB_UPLOAD_REASSEMBLE_MB_S_DEFAULT}}"
  local reassemble_timeout="" reassemble_timeout_src=""
  if [ -n "${COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S:-}" ]; then
    reassemble_timeout="${COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S}"
    reassemble_timeout_src="${COLAB_UPLOAD_REASSEMBLE_TIMEOUT_SOURCE:-explicit}"
  else
    reassemble_timeout="$("${py_bin}" -c '
import math, sys
up_t = int(sys.argv[1])
f_bytes = int(sys.argv[2])
mb_s = float(sys.argv[3])
by_size = math.ceil(f_bytes / (mb_s * 1_000_000.0)) + 30
print(max(up_t, by_size))
' "${upload_timeout}" "${file_bytes}" "${reassemble_mb_s}" | tr -d '\r')"
    reassemble_timeout_src="size_and_rate"
  fi

  local reassemble_out="" reassemble_rc=0
  reassemble_out="$(colab_run_bounded "${reassemble_timeout}" "${kill_grace}" colab exec -s "${session}" -f "${tmp_up_dir}/reassemble_upload.py" \
    --timeout "${reassemble_timeout}" --env "SDLAB_CONTENT=/content" --env "SDLAB_UP_MANIFEST=${manifest_remote_name}" 2>&1)" || reassemble_rc=$?
  printf '%s\n' "${reassemble_out}" >> "${out_dir}/colab.log"
  rm -rf "${tmp_up_dir}"

  if colab_rc_is_timeout "${reassemble_rc}"; then
    echo "UPLOAD_TIMEOUT ${src} -> ${dst} step=reassemble timeout_s=${reassemble_timeout} kill_grace_s=${kill_grace} rc=${reassemble_rc}" >> "${out_dir}/guards.log"
  fi

  local parsed_status="" parsed_code="" parsed_detail=""
  IFS=$'\t' read -r parsed_status parsed_code parsed_detail < <(
    "${py_bin}" -c '
import json, sys
raw = sys.stdin.read()
rec = None
for ln in reversed(raw.splitlines()):
    ln = ln.strip()
    if ln.startswith("SDLAB_UPLOAD_REASSEMBLE_JSON "):
        try:
            rec = json.loads(ln[len("SDLAB_UPLOAD_REASSEMBLE_JSON "):])
            break
        except ValueError:
            pass
if rec is None:
    print("ERR\tUPLOAD_PART_FAILED\tmissing SDLAB_UPLOAD_REASSEMBLE_JSON marker from VM reassembly")
elif not rec.get("ok"):
    code = str(rec.get("code") or "UPLOAD_SHA_MISMATCH")
    detail = str(rec.get("detail") or "VM reassembly failed").replace("\t", " ").replace("\n", " ")
    print(f"ERR\t{code}\t{detail}")
else:
    sh = rec.get("sha256", "")
    print(f"OK\tOK\t{sh}")
' <<< "${reassemble_out}" | tr -d '\r'
  )

  if [ "${reassemble_rc}" -ne 0 ] && [ "${parsed_status}" = "OK" ]; then
    parsed_status="ERR"
    parsed_code="UPLOAD_PART_FAILED"
    parsed_detail="${src} -> ${dst}: VM reassembly colab exec rc=${reassemble_rc}"
  fi

  if [ "${parsed_status}" != "OK" ]; then
    "${py_bin}" -c '
import json, pathlib, sys
rec = {
    "local": sys.argv[2], "remote": sys.argv[3], "mode": "chunked",
    "bytes": int(sys.argv[4]), "sha256": sys.argv[5],
    "chunk_bytes": int(sys.argv[6]), "part_count": int(sys.argv[7]),
    "uploaded_parts": int(sys.argv[7]), "retries": int(sys.argv[8]),
    "reassemble_timeout_s": int(sys.argv[10]),
    "reassemble_timeout_source": sys.argv[11],
    "reassemble_mb_s": float(sys.argv[12]),
    "refusal_code": sys.argv[9], "ok": False,
}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${out_dir}/upload_receipts.jsonl" "${src}" "${dst}" "${file_bytes}" "${rig_sha}" "${chunk_bytes}" "${part_count}" "${total_retries}" "${parsed_code:-UPLOAD_PART_FAILED}" "${reassemble_timeout}" "${reassemble_timeout_src}" "${reassemble_mb_s}"
    colab_refuse_logged "${out_dir}" "${parsed_code:-UPLOAD_PART_FAILED}" "${src} -> ${dst}: ${parsed_detail}"
    return 1
  fi

  "${py_bin}" -c '
import json, pathlib, sys
rec = {
    "local": sys.argv[2], "remote": sys.argv[3], "mode": "chunked",
    "bytes": int(sys.argv[4]), "sha256": sys.argv[5],
    "chunk_bytes": int(sys.argv[6]), "part_count": int(sys.argv[7]),
    "uploaded_parts": int(sys.argv[7]), "retries": int(sys.argv[8]),
    "reassemble_timeout_s": int(sys.argv[9]),
    "reassemble_timeout_source": sys.argv[10],
    "reassemble_mb_s": float(sys.argv[11]),
    "ok": True,
}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${out_dir}/upload_receipts.jsonl" "${src}" "${dst}" "${file_bytes}" "${rig_sha}" "${chunk_bytes}" "${part_count}" "${total_retries}" "${reassemble_timeout}" "${reassemble_timeout_src}" "${reassemble_mb_s}"
  colab_check_pre_exec_cap "${out_dir}" "post_upload" || return 1
}

# _colab_write_download_prepare_py <path>: emit the single-source VM-side inspect/split helper from
# `launch_guards.py` (`# >>> sdlab-download-prep` ... `# <<< sdlab-download-prep`, no `__file__`).
_colab_write_download_prepare_py() {
  local target_py="$1"
  local py_bin
  py_bin="$(_colab_resolve_helper_python)"
  "${py_bin}" - "${COLAB_WINDOW_DIR}/launch_guards.py" "${target_py}" << 'PYEOF'
import pathlib, sys

src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
start_marker = "# >>> sdlab-download-prep"
end_marker = "# <<< sdlab-download-prep"
i = src.find(start_marker)
j = src.find(end_marker)
if i < 0 or j < 0 or j <= i:
    raise SystemExit("missing sdlab-download-prep markers in launch_guards.py")
block = src[i : j + len(end_marker)]
epilogue = (
    "\n\nif __name__ == \"__main__\":\n"
    "    prepare_single_content_download(\n"
    "        _dl_os.environ[\"SDLAB_CONTENT\"],\n"
    "        _dl_os.environ[\"SDLAB_DL_REL\"],\n"
    "        int(_dl_os.environ[\"SDLAB_DL_CHUNK_BYTES\"]),\n"
    "    )\n"
)
pathlib.Path(sys.argv[2]).write_text(block + epilogue, encoding="utf-8", newline="\n")
PYEOF
}

# _colab_update_download_receipt <py_bin> <receipt_json> <jsonl_path_or_empty> <json_payload>
_colab_update_download_receipt() {
  local py_bin="$1"
  local receipt_json="$2"
  local jsonl_path="$3"
  local payload="$4"
  "${py_bin}" -c '
import json, pathlib, sys
rec = json.loads(sys.argv[3])
p = pathlib.Path(sys.argv[1])
tmp = p.with_suffix(p.suffix + ".tmp")
tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
tmp.replace(p)
if sys.argv[2]:
    with pathlib.Path(sys.argv[2]).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec) + "\n")
' "${receipt_json}" "${jsonl_path}" "${payload}"
}

# _colab_keep_arrived_parts <py_bin> <tmp_dl_dir> <out_dir> <receipt_file> <mode> <dst>: a chunked
# download failed after some parts had arrived and verified. Never delete verified bytes: move every
# arrived part (and the VM's split manifest) from the temp directory into
# `<out_dir>/salvage_partial/<mode>_<name>[_n]/` with `arrived_parts_receipt.json`, then remove the
# temp directory. A part that failed its own check is not kept (it was never verified).
_colab_keep_arrived_parts() {
  "$1" - "$2" "$3" "$4" "$5" "$6" "${7:-}" << 'PYEOF'
import json, pathlib, re, shutil, sys

tmp_dir = pathlib.Path(sys.argv[1])
out_dir = pathlib.Path(sys.argv[2])
receipt_p = pathlib.Path(sys.argv[3])
mode = sys.argv[4]
dst_name = pathlib.Path(sys.argv[5]).name
if mode == "refetch" and sys.argv[6]:
    # a refetch writes to a temp file (cand_N.bin): name the directory after the training file instead
    dst_name = re.sub(r"[^A-Za-z0-9._-]", "_", sys.argv[6].removeprefix("/content/lane3_train/"))
kept = []
try:
    rec = json.loads(receipt_p.read_text(encoding="utf-8")) if receipt_p.is_file() else {}
except ValueError:
    rec = {}
arrived = [int(i) for i in (rec.get("arrived_parts") or [])]
if arrived and tmp_dir.is_dir() and tmp_dir.name.startswith(".sdlab_dl_tmp_") and tmp_dir.parent == out_dir:
    base = out_dir / "salvage_partial"
    base.mkdir(parents=True, exist_ok=True)
    dest = base / f"{mode}_{dst_name}"
    n = 1
    while dest.exists():
        n += 1
        dest = base / f"{mode}_{dst_name}_{n}"
    dest.mkdir()
    for idx in arrived:
        src = tmp_dir / f"part.{idx:04d}"
        if src.is_file():
            shutil.move(str(src), str(dest / src.name))
            kept.append(src.name)
    man = tmp_dir / "manifest.json"
    if man.is_file():
        shutil.move(str(man), str(dest / "vm_split_manifest.json"))
        kept.append("vm_split_manifest.json")
    rec["kept_files"] = kept
    rec["kept_dir"] = dest.as_posix()
    (dest / "arrived_parts_receipt.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
if tmp_dir.is_dir() and tmp_dir.name.startswith(".sdlab_dl_tmp_") and tmp_dir.parent == out_dir:
    shutil.rmtree(tmp_dir, ignore_errors=True)
PYEOF
}

# _colab_download_transfer <mode: normal|salvage|refetch> <session> <remote> <local> <out_dir> [arg6] [arg7]:
# Shared implementation for `colab_download_checked` (normal), `colab_salvage_bundle_after_failure`
# (salvage), and `colab_refetch_missing_bundle_files` (refetch). Splits files >
# COLAB_DOWNLOAD_CHUNK_BYTES (default 256 MiB) on the VM with a sha256 manifest of parts + whole
# file (refusing DOWNLOAD_SPLIT_DISK_LOW before any GET when VM free disk is insufficient), downloads
# parts one at a time under per-part timeout with 1 retry per part on HTTP 5xx, records arrived parts
# incrementally to disk (`bundle_download.json` / `salvage_bundle_download.json`), reassembles on the
# rig, and verifies the whole-file sha256 against the VM's manifest. No post-download VM cleanup exec
# is run because `colab stop` wipes `/content` and an extra exec wastes units.
_colab_download_transfer() {
  local mode="$1"
  local session="$2"
  local src="$3"
  local dst="$4"
  local out_dir="$5"
  local salvage_start="${6:-0}"
  local salvage_deadline="${7:-0}"
  local refetch_timeout_cap=""
  local refetch_expected_sha=""
  if [ "${mode}" = "refetch" ]; then
    refetch_timeout_cap="${6:-}"
    refetch_expected_sha="${7:-}"
    salvage_start="0"
    salvage_deadline="0"
  fi

  local dst_parent
  dst_parent="$(dirname -- "${dst}")"
  if [ ! -d "${dst_parent}" ]; then
    if [ "${mode}" = "normal" ]; then
      colab_refuse_logged "${out_dir}" DOWNLOAD_FAILED "${src} -> ${dst}: local directory ${dst_parent} does not exist (http=none)"
    fi
    return 1
  fi

  local chunk_bytes="${COLAB_DOWNLOAD_CHUNK_BYTES:-${COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT}}"
  if ! [[ "${chunk_bytes}" =~ ^[1-9][0-9]*$ ]]; then
    if [ "${mode}" = "normal" ]; then
      colab_refuse_logged "${out_dir}" DOWNLOAD_CHUNK_BYTES_INVALID "COLAB_DOWNLOAD_CHUNK_BYTES='${chunk_bytes}' must be a positive integer (bytes)"
      return 2
    fi
    chunk_bytes="${COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT}"
  fi

  local py_bin
  py_bin="$(_colab_resolve_helper_python)"
  local kill_grace="${COLAB_KILL_GRACE_S:-10}"
  local base_timeout="${COLAB_DOWNLOAD_TIMEOUT_S:-300}"
  if [ "${mode}" = "salvage" ]; then
    base_timeout="${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S:-300}"
  elif [ "${mode}" = "refetch" ] && [[ "${refetch_timeout_cap}" =~ ^[1-9][0-9]*$ ]]; then
    if [ "${refetch_timeout_cap}" -lt "${base_timeout}" ]; then
      base_timeout="${refetch_timeout_cap}"
    fi
  fi
  local receipt_file="${out_dir}/bundle_download.json"
  local receipt_jsonl="${out_dir}/download_receipts.jsonl"
  if [ "${mode}" = "salvage" ]; then
    receipt_file="${out_dir}/salvage_bundle_download.json"
  elif [ "${mode}" = "refetch" ]; then
    receipt_file="${out_dir}/.refetch_last_download.json"
    receipt_jsonl="${out_dir}/refetch_receipts.jsonl"
  fi

  _dl_step_run() {
    local want_t="$1"
    local cap_out_file="$2"
    shift 2
    local eff_t="${want_t}"
    if [ "${mode}" = "salvage" ]; then
      local now_e elapsed_e rem_e
      now_e="$(date -u +%s)"
      elapsed_e=$((now_e - salvage_start))
      if [ "${COLAB_CLEANUP_SKIP_SALVAGE:-0}" = "1" ] || [ "${elapsed_e}" -ge "${salvage_deadline}" ]; then
        echo "SALVAGE_DEADLINE_EXCEEDED download elapsed_s=${elapsed_e} deadline_s=${salvage_deadline}" >> "${out_dir}/guards.log"
        : > "${cap_out_file}"
        return 124
      fi
      rem_e=$((salvage_deadline - elapsed_e))
      [ "${rem_e}" -lt "${eff_t}" ] && eff_t="${rem_e}"
      colab_run_bounded_salvage_step "${eff_t}" "${kill_grace}" "$@" > "${cap_out_file}" 2>&1
    else
      colab_run_bounded "${eff_t}" "${kill_grace}" "$@" > "${cap_out_file}" 2>&1
    fi
  }

  local tmp_dl_dir="${out_dir}/.sdlab_dl_tmp_$$_${RANDOM}"
  mkdir -p "${tmp_dl_dir}"

  local prep_state="DIRECT"
  local prep_split="0"
  local prep_whole_bytes="0"
  local prep_whole_sha=""
  local prep_part_count="1"
  local prep_manifest_remote=""
  local prep_prefix=""

  if [[ "${src}" == /content/* ]] && [ -n "${src#/content/}" ]; then
    local rel_src="${src#/content/}"
    local prior_log="${out_dir}/vitals.log"
    if [ "${mode}" = "salvage" ]; then
      prior_log="${out_dir}/bundle_now.log"
    elif [ "${mode}" = "refetch" ]; then
      prior_log=""
    fi
    local need_prep_exec="1"
    if [ -n "${prior_log}" ] && [ -f "${prior_log}" ]; then
      IFS=$'\t' read -r prep_state prep_split prep_whole_bytes prep_whole_sha prep_part_count prep_manifest_remote prep_prefix < <(
        "${py_bin}" -c '
import json, pathlib, sys
raw = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
want_rel = sys.argv[2]
want_chunk = int(sys.argv[3])
done_marker = f"SDLAB_DOWNLOAD_PREPARE_DONE chunk_bytes={want_chunk}"
rec = None
saw_done = False
for ln in reversed(raw.splitlines()):
    s = ln.strip()
    if s == done_marker:
        saw_done = True
    elif s.startswith("SDLAB_DOWNLOAD_PREPARE_JSON "):
        try:
            cand = json.loads(s[len("SDLAB_DOWNLOAD_PREPARE_JSON "):])
        except ValueError:
            continue
        if cand.get("rel") == want_rel and int(cand.get("chunk_bytes", -1)) == want_chunk:
            rec = cand
            break
if rec is not None:
    if not rec.get("exists"):
        print("DIRECT\t0\t0\t-\t1\t-\t-")
    elif rec.get("split_failed"):
        wb = int(rec.get("whole_bytes") or 0)
        pc = int(rec.get("part_count") or 1)
        code = str(rec.get("error_code") or "DOWNLOAD_SPLIT_DISK_LOW").replace("\t", " ").replace("\n", " ") or "DOWNLOAD_SPLIT_DISK_LOW"
        why = str(rec.get("why") or "VM split failed due to low disk").replace("\t", " ").replace("\n", " ") or "VM split failed due to low disk"
        print(f"SPLIT_ERR\t0\t{wb}\t-\t{pc}\t{code}\t{why}")
    elif not rec.get("split"):
        wb = int(rec["whole_bytes"]); ws = rec["whole_sha256"] or "-"
        print(f"SINGLE\t0\t{wb}\t{ws}\t1\t-\t-")
    else:
        wb = int(rec["whole_bytes"]); ws = rec["whole_sha256"] or "-"
        pc = int(rec["part_count"]); mr = rec["manifest_remote"] or "-"; px = rec["prefix"] or "-"
        print(f"SPLIT\t1\t{wb}\t{ws}\t{pc}\t{mr}\t{px}")
elif saw_done:
    print("DIRECT\t0\t0\t-\t1\t-\t-")
else:
    print("NEED_PREP\t0\t0\t-\t1\t-\t-")
' "${prior_log}" "${rel_src}" "${chunk_bytes}" | tr -d '\r'
      )
      [ "${prep_whole_sha}" = "-" ] && prep_whole_sha=""
      [ "${prep_manifest_remote}" = "-" ] && prep_manifest_remote=""
      [ "${prep_prefix}" = "-" ] && prep_prefix=""
      if [ "${prep_state}" != "NEED_PREP" ]; then
        need_prep_exec="0"
      elif [ "${mode}" = "salvage" ]; then
        prep_state="DIRECT"
        need_prep_exec="0"
      else
        prep_state="DIRECT"
      fi
    fi

    if [ "${need_prep_exec}" = "1" ]; then
      _colab_write_download_prepare_py "${tmp_dl_dir}/prepare_download.py"
      local prep_rc=0
      local prep_t="${base_timeout}"
      [ "${prep_t}" -gt 180 ] && prep_t=180
      _dl_step_run "${prep_t}" "${tmp_dl_dir}/prep.out" colab exec -s "${session}" -f "${tmp_dl_dir}/prepare_download.py" \
        --timeout "${prep_t}" --env "SDLAB_CONTENT=/content" --env "SDLAB_DL_REL=${rel_src}" \
        --env "SDLAB_DL_CHUNK_BYTES=${chunk_bytes}" || prep_rc=$?
      local prep_out=""
      prep_out="$(cat "${tmp_dl_dir}/prep.out" 2>/dev/null || true)"
      [ -n "${prep_out}" ] && printf '%s\n' "${prep_out}" >> "${out_dir}/colab.log"
      if colab_rc_is_timeout "${prep_rc}"; then
        echo "SALVAGE_STEP_TIMEOUT download timeout_s=${prep_t} kill_grace_s=${kill_grace} rc=${prep_rc}" >> "${out_dir}/guards.log"
        rm -rf "${tmp_dl_dir}"
        rm -f "${dst}"
        if [ "${mode}" = "normal" ]; then
          colab_refuse_logged "${out_dir}" DOWNLOAD_FAILED "${src} -> ${dst}: VM download prepare timed out rc=${prep_rc} (CLI output in colab.log)"
        fi
        return "${prep_rc}"
      fi
      IFS=$'\t' read -r prep_state prep_split prep_whole_bytes prep_whole_sha prep_part_count prep_manifest_remote prep_prefix < <(
        "${py_bin}" -c '
import json, sys
prep_rc = int(sys.argv[1])
raw = sys.stdin.read()
rec = None
for ln in reversed(raw.splitlines()):
    ln = ln.strip()
    if ln.startswith("SDLAB_DOWNLOAD_PREPARE_JSON "):
        try:
            rec = json.loads(ln[len("SDLAB_DOWNLOAD_PREPARE_JSON "):])
            break
        except ValueError:
            pass
if rec is None:
    low = raw.lower()
    if "enospc" in low or "no space left on device" in low:
        print(f"SPLIT_ERR\t0\t0\t-\t1\tDOWNLOAD_SPLIT_DISK_LOW\tVM download prepare exited rc={prep_rc} with ENOSPC")
    else:
        print(f"PREP_ERR\t0\t0\t-\t1\tDOWNLOAD_FAILED\tVM download prepare failed rc={prep_rc} without SDLAB_DOWNLOAD_PREPARE_JSON")
elif not rec.get("exists"):
    print("DIRECT\t0\t0\t-\t1\t-\t-")
elif rec.get("split_failed"):
    wb = int(rec.get("whole_bytes") or 0)
    pc = int(rec.get("part_count") or 1)
    code = str(rec.get("error_code") or "DOWNLOAD_SPLIT_DISK_LOW").replace("\t", " ").replace("\n", " ") or "DOWNLOAD_SPLIT_DISK_LOW"
    why = str(rec.get("why") or "VM split failed due to low disk").replace("\t", " ").replace("\n", " ") or "VM split failed due to low disk"
    print(f"SPLIT_ERR\t0\t{wb}\t-\t{pc}\t{code}\t{why}")
elif not rec.get("split"):
    wb = int(rec["whole_bytes"]); ws = rec["whole_sha256"] or "-"
    print(f"SINGLE\t0\t{wb}\t{ws}\t1\t-\t-")
else:
    wb = int(rec["whole_bytes"]); ws = rec["whole_sha256"] or "-"
    pc = int(rec["part_count"]); mr = rec["manifest_remote"] or "-"; px = rec["prefix"] or "-"
    print(f"SPLIT\t1\t{wb}\t{ws}\t{pc}\t{mr}\t{px}")
' "${prep_rc}" <<< "${prep_out}" | tr -d '\r'
      )
      [ "${prep_whole_sha}" = "-" ] && prep_whole_sha=""
      [ "${prep_manifest_remote}" = "-" ] && prep_manifest_remote=""
      [ "${prep_prefix}" = "-" ] && prep_prefix=""
      if [ "${mode}" = "refetch" ]; then
        # The VM's own copy is the source of truth for this fetch. A file that is missing on the VM, or
        # whose sha256 there differs from the training-folder manifest, cannot be repaired by fetching it
        # again: report it (return 3 / 4) without a transfer.
        if [ "${prep_state}" = "DIRECT" ]; then
          echo "BUNDLE_REFETCH_VM_SOURCE_MISSING src=${src}" >> "${out_dir}/guards.log"
          rm -rf "${tmp_dl_dir}"
          rm -f "${dst}"
          return 3
        fi
        if { [ "${prep_state}" = "SINGLE" ] || [ "${prep_state}" = "SPLIT" ]; } && [ -n "${refetch_expected_sha}" ] \
          && [ "${prep_whole_sha}" != "${refetch_expected_sha}" ]; then
          echo "BUNDLE_REFETCH_VM_SOURCE_SHA_MISMATCH src=${src} vm_sha256=${prep_whole_sha} expected_sha256=${refetch_expected_sha}" >> "${out_dir}/guards.log"
          rm -rf "${tmp_dl_dir}"
          rm -f "${dst}"
          return 4
        fi
      fi
    fi
  fi

  if [ "${prep_state}" = "SPLIT_ERR" ]; then
    local split_err_code="${prep_manifest_remote:-DOWNLOAD_SPLIT_DISK_LOW}"
    local split_err_why="${prep_prefix:-VM download split ran out of disk}"
    local split_fail_rec
    split_fail_rec="$("${py_bin}" -c '
import json, sys
print(json.dumps({
    "remote": sys.argv[1], "local": sys.argv[2], "phase": sys.argv[3], "mode": "chunked",
    "chunk_bytes": int(sys.argv[4]), "whole_bytes_expected": int(sys.argv[5]),
    "whole_sha256_expected": None, "part_count": int(sys.argv[6]), "arrived_parts": [],
    "retries": 0, "verified": False, "whole_sha256_actual": None,
    "error_code": sys.argv[7], "why": sys.argv[8], "status": "split_disk_low",
}))
' "${src}" "${dst}" "${mode}" "${chunk_bytes}" "${prep_whole_bytes}" "${prep_part_count}" "${split_err_code}" "${split_err_why}")"
    _colab_update_download_receipt "${py_bin}" "${receipt_file}" "${receipt_jsonl}" "${split_fail_rec}"
    rm -rf "${tmp_dl_dir}"
    rm -f "${dst}"
    if [ "${mode}" = "normal" ]; then
      colab_refuse_logged "${out_dir}" "${split_err_code}" "${src} -> ${dst}: ${split_err_why}"
    else
      echo "${mode^^}_DOWNLOAD_SPLIT_DISK_LOW ${src} -> ${dst}: ${split_err_why}" >> "${out_dir}/guards.log"
    fi
    return 1
  fi

  if [ "${prep_state}" = "PREP_ERR" ]; then
    local prep_err_why="${prep_prefix:-VM download prepare failed}"
    rm -rf "${tmp_dl_dir}"
    rm -f "${dst}"
    if [ "${mode}" = "normal" ]; then
      colab_refuse_logged "${out_dir}" DOWNLOAD_FAILED "${src} -> ${dst}: ${prep_err_why} (CLI output in colab.log)"
    else
      echo "${mode^^}_DOWNLOAD_PREP_FAILED ${src} -> ${dst}: ${prep_err_why}" >> "${out_dir}/guards.log"
    fi
    return 1
  fi

  # Single-GET path (`prep_state == DIRECT` when missing/non-/content, or `SINGLE` when <= chunk_bytes).
  if [ "${prep_state}" != "SPLIT" ]; then
    if [ "${prep_state}" = "SINGLE" ]; then
      local init_single
      init_single="$("${py_bin}" -c '
import json, sys
print(json.dumps({
    "remote": sys.argv[1], "local": sys.argv[2], "phase": sys.argv[3], "mode": "single",
    "chunk_bytes": int(sys.argv[4]), "whole_bytes_expected": int(sys.argv[5]),
    "whole_sha256_expected": sys.argv[6], "part_count": 1, "arrived_parts": [],
    "retries": 0, "verified": False, "whole_sha256_actual": None, "status": "in_progress",
}))
' "${src}" "${dst}" "${mode}" "${chunk_bytes}" "${prep_whole_bytes}" "${prep_whole_sha}")"
      _colab_update_download_receipt "${py_bin}" "${receipt_file}" "" "${init_single}"
    fi

    local dl_rc=0 dl_out=""
    _dl_step_run "${base_timeout}" "${tmp_dl_dir}/dl.out" colab download -s "${session}" "${src}" "${dst}" || dl_rc=$?
    dl_out="$(cat "${tmp_dl_dir}/dl.out" 2>/dev/null || true)"
    rm -rf "${tmp_dl_dir}"
    [ -n "${dl_out}" ] && printf '%s\n' "${dl_out}" >> "${out_dir}/colab.log"
    if colab_rc_is_timeout "${dl_rc}"; then
      echo "SALVAGE_STEP_TIMEOUT download timeout_s=${base_timeout} kill_grace_s=${kill_grace} rc=${dl_rc}" >> "${out_dir}/guards.log"
    fi
    if [ "${dl_rc}" -ne 0 ] || ! grep -Fq "[colab] Downloaded '" <<< "${dl_out}" || [ ! -s "${dst}" ]; then
      local http_st
      http_st="$(_colab_http_status "${dl_out}")"
      rm -f "${dst}"
      if [ "${prep_state}" = "SINGLE" ]; then
        local fail_single
        fail_single="$("${py_bin}" -c '
import json, sys
print(json.dumps({
    "remote": sys.argv[1], "local": sys.argv[2], "phase": sys.argv[3], "mode": "single",
    "chunk_bytes": int(sys.argv[4]), "whole_bytes_expected": int(sys.argv[5]),
    "whole_sha256_expected": sys.argv[6], "part_count": 1, "arrived_parts": [],
    "retries": 0, "http_status": sys.argv[7], "verified": False, "whole_sha256_actual": None,
    "status": "download_failed",
}))
' "${src}" "${dst}" "${mode}" "${chunk_bytes}" "${prep_whole_bytes}" "${prep_whole_sha}" "${http_st}")"
        _colab_update_download_receipt "${py_bin}" "${receipt_file}" "${receipt_jsonl}" "${fail_single}"
      fi
      if [ "${mode}" = "normal" ]; then
        colab_refuse_logged "${out_dir}" DOWNLOAD_FAILED "${src} -> ${dst}: colab download rc=${dl_rc} http=${http_st} (CLI output in colab.log)"
        return 1
      fi
      return "${dl_rc:-1}"
    fi

    if [ "${prep_state}" = "SINGLE" ] && [ -n "${prep_whole_sha}" ]; then
      local got_bytes="" got_sha=""
      read -r got_bytes got_sha < <(
        "${py_bin}" -c '
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
h = hashlib.sha256()
sz = 0
with p.open("rb") as fh:
    for blk in iter(lambda: fh.read(1 << 20), b""):
        sz += len(blk)
        h.update(blk)
print(sz, h.hexdigest())
' "${dst}" | tr -d '\r'
      )
      if [ "${got_bytes}" != "${prep_whole_bytes}" ] || [ "${got_sha}" != "${prep_whole_sha}" ]; then
        rm -f "${dst}"
        local bad_single
        bad_single="$("${py_bin}" -c '
import json, sys
print(json.dumps({
    "remote": sys.argv[1], "local": sys.argv[2], "phase": sys.argv[3], "mode": "single",
    "chunk_bytes": int(sys.argv[4]), "whole_bytes_expected": int(sys.argv[5]),
    "whole_sha256_expected": sys.argv[6], "part_count": 1, "arrived_parts": [],
    "retries": 0, "verified": False, "whole_sha256_actual": sys.argv[7], "status": "sha_mismatch",
}))
' "${src}" "${dst}" "${mode}" "${chunk_bytes}" "${prep_whole_bytes}" "${prep_whole_sha}" "${got_sha}")"
        _colab_update_download_receipt "${py_bin}" "${receipt_file}" "${receipt_jsonl}" "${bad_single}"
        if [ "${mode}" = "normal" ]; then
          colab_refuse_logged "${out_dir}" DOWNLOAD_SHA_MISMATCH "${src} -> ${dst}: local sha256=${got_sha} (bytes=${got_bytes}) != VM sha256=${prep_whole_sha} (bytes=${prep_whole_bytes})"
        fi
        return 1
      fi
      local ok_single
      ok_single="$("${py_bin}" -c '
import json, sys
print(json.dumps({
    "remote": sys.argv[1], "local": sys.argv[2], "phase": sys.argv[3], "mode": "single",
    "chunk_bytes": int(sys.argv[4]), "whole_bytes_expected": int(sys.argv[5]),
    "whole_sha256_expected": sys.argv[6], "part_count": 1, "arrived_parts": [0],
    "retries": 0, "verified": True, "whole_sha256_actual": sys.argv[7], "status": "verified",
}))
' "${src}" "${dst}" "${mode}" "${chunk_bytes}" "${prep_whole_bytes}" "${prep_whole_sha}" "${got_sha}")"
      _colab_update_download_receipt "${py_bin}" "${receipt_file}" "${receipt_jsonl}" "${ok_single}"
    fi
    return 0
  fi

  # Chunked download path: initialize incremental receipt BEFORE part 0 so any forced wall stop
  # leaves the exact arrived parts recorded on disk.
  local init_chunked
  init_chunked="$("${py_bin}" -c '
import json, sys
print(json.dumps({
    "remote": sys.argv[1], "local": sys.argv[2], "phase": sys.argv[3], "mode": "chunked",
    "chunk_bytes": int(sys.argv[4]), "whole_bytes_expected": int(sys.argv[5]),
    "whole_sha256_expected": sys.argv[6], "part_count": int(sys.argv[7]),
    "arrived_parts": [], "arrived_part_details": [], "retries": 0,
    "verified": False, "whole_sha256_actual": None, "failed_part": None, "status": "in_progress",
}))
' "${src}" "${dst}" "${mode}" "${chunk_bytes}" "${prep_whole_bytes}" "${prep_whole_sha}" "${prep_part_count}")"
  _colab_update_download_receipt "${py_bin}" "${receipt_file}" "" "${init_chunked}"

  # Fetch the VM's split manifest (with 1 retry on 5xx).
  local man_local="${tmp_dl_dir}/manifest.json"
  local m_rc=0 m_out="" m_http="none" total_retries=0
  _dl_step_run "${base_timeout}" "${tmp_dl_dir}/man.out" colab download -s "${session}" "${prep_manifest_remote}" "${man_local}" || m_rc=$?
  m_out="$(cat "${tmp_dl_dir}/man.out" 2>/dev/null || true)"
  [ -n "${m_out}" ] && printf '%s\n' "${m_out}" >> "${out_dir}/colab.log"
  if colab_rc_is_timeout "${m_rc}"; then
    echo "SALVAGE_STEP_TIMEOUT download timeout_s=${base_timeout} kill_grace_s=${kill_grace} rc=${m_rc}" >> "${out_dir}/guards.log"
  elif [ "${m_rc}" -ne 0 ] || ! grep -Fq "[colab] Downloaded '" <<< "${m_out}" || [ ! -s "${man_local}" ]; then
    m_http="$(_colab_http_status "${m_out}")"
    if [[ "${m_http}" =~ ^5[0-9]{2}$ ]]; then
      total_retries=$((total_retries + 1))
      m_rc=0
      _dl_step_run "${base_timeout}" "${tmp_dl_dir}/man.out" colab download -s "${session}" "${prep_manifest_remote}" "${man_local}" || m_rc=$?
      m_out="$(cat "${tmp_dl_dir}/man.out" 2>/dev/null || true)"
      [ -n "${m_out}" ] && printf '%s\n' "${m_out}" >> "${out_dir}/colab.log"
      if colab_rc_is_timeout "${m_rc}"; then
        echo "SALVAGE_STEP_TIMEOUT download timeout_s=${base_timeout} kill_grace_s=${kill_grace} rc=${m_rc}" >> "${out_dir}/guards.log"
      fi
    fi
  fi
  if [ "${m_rc}" -ne 0 ] || ! grep -Fq "[colab] Downloaded '" <<< "${m_out}" || [ ! -s "${man_local}" ]; then
    m_http="$(_colab_http_status "${m_out}")"
    rm -rf "${tmp_dl_dir}"
    rm -f "${dst}"
    local fail_man
    fail_man="$("${py_bin}" -c '
import json, pathlib, sys
rec = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
rec.update({"retries": int(sys.argv[2]), "http_status": sys.argv[3], "status": "manifest_download_failed"})
print(json.dumps(rec))
' "${receipt_file}" "${total_retries}" "${m_http}")"
    _colab_update_download_receipt "${py_bin}" "${receipt_file}" "${receipt_jsonl}" "${fail_man}"
    if [ "${mode}" = "normal" ]; then
      colab_refuse_logged "${out_dir}" DOWNLOAD_PART_FAILED "${src} -> ${dst} manifest: colab download rc=${m_rc} http=${m_http} (CLI output in colab.log)"
    fi
    return 1
  fi

  local part_rows=""
  if ! part_rows="$("${py_bin}" -c '
import json, pathlib, sys
m = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
parts = m.get("parts")
if not isinstance(parts, list) or len(parts) != int(sys.argv[2]) or str(m.get("whole_sha256", "")).lower() != sys.argv[3].lower():
    raise SystemExit(1)
for p in parts:
    ix = int(p["index"]); rp = p["remote_path"]; nb = int(p["bytes"]); ps = str(p["sha256"]).lower()
    print(f"{ix}\t{rp}\t{nb}\t{ps}")
' "${man_local}" "${prep_part_count}" "${prep_whole_sha}" | tr -d '\r')"; then
    rm -rf "${tmp_dl_dir}"
    rm -f "${dst}"
    if [ "${mode}" = "normal" ]; then
      colab_refuse_logged "${out_dir}" DOWNLOAD_PART_FAILED "${src} -> ${dst}: invalid download manifest from VM"
    fi
    return 1
  fi

  local p_indices=() p_remotes=() p_bytes_list=() p_shas=()
  while IFS=$'\t' read -r pi pr pb ps; do
    [ -z "${pi}" ] && continue
    p_indices+=("${pi}")
    p_remotes+=("${pr}")
    p_bytes_list+=("${pb}")
    p_shas+=("${ps}")
  done <<< "${part_rows}"

  local k=0
  while [ "${k}" -lt "${prep_part_count}" ]; do
    local p_idx="${p_indices[$k]}"
    local p_remote="${p_remotes[$k]}"
    local p_exp_bytes="${p_bytes_list[$k]}"
    local p_exp_sha="${p_shas[$k]}"
    local p_local
    printf -v p_local '%s/part.%04d' "${tmp_dl_dir}" "${p_idx}"
    local p_num=$((k + 1))
    local p_rc=0 p_out="" p_http="none" p_attempts=1
    _dl_step_run "${base_timeout}" "${tmp_dl_dir}/part.out" colab download -s "${session}" "${p_remote}" "${p_local}" || p_rc=$?
    p_out="$(cat "${tmp_dl_dir}/part.out" 2>/dev/null || true)"
    [ -n "${p_out}" ] && printf '%s\n' "${p_out}" >> "${out_dir}/colab.log"
    if colab_rc_is_timeout "${p_rc}"; then
      echo "SALVAGE_STEP_TIMEOUT download timeout_s=${base_timeout} kill_grace_s=${kill_grace} rc=${p_rc}" >> "${out_dir}/guards.log"
    elif [ "${p_rc}" -ne 0 ] || ! grep -Fq "[colab] Downloaded '" <<< "${p_out}" || [ ! -s "${p_local}" ]; then
      p_http="$(_colab_http_status "${p_out}")"
      if [[ "${p_http}" =~ ^5[0-9]{2}$ ]]; then
        p_attempts=2
        total_retries=$((total_retries + 1))
        echo "DOWNLOAD_PART_RETRY ${src} -> ${dst} part=${p_num}/${prep_part_count} http=${p_http} attempt=2/2" >> "${out_dir}/guards.log"
        rm -f "${p_local}"
        p_rc=0
        _dl_step_run "${base_timeout}" "${tmp_dl_dir}/part.out" colab download -s "${session}" "${p_remote}" "${p_local}" || p_rc=$?
        p_out="$(cat "${tmp_dl_dir}/part.out" 2>/dev/null || true)"
        [ -n "${p_out}" ] && printf '%s\n' "${p_out}" >> "${out_dir}/colab.log"
        if colab_rc_is_timeout "${p_rc}"; then
          echo "SALVAGE_STEP_TIMEOUT download timeout_s=${base_timeout} kill_grace_s=${kill_grace} rc=${p_rc}" >> "${out_dir}/guards.log"
        fi
      fi
    fi

    if [ "${p_rc}" -ne 0 ] || ! grep -Fq "[colab] Downloaded '" <<< "${p_out}" || [ ! -s "${p_local}" ]; then
      p_http="$(_colab_http_status "${p_out}")"
      local arrived_csv=""
      IFS=$'\t' read -r arrived_csv < <(
        "${py_bin}" -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rec = json.loads(p.read_text(encoding="utf-8"))
rec.update({
    "retries": int(sys.argv[2]),
    "failed_part": int(sys.argv[3]),
    "http_status": sys.argv[4],
    "verified": False,
    "status": "part_failed",
})
print(",".join(str(x) for x in rec["arrived_parts"]) or "none")
p.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
with pathlib.Path(sys.argv[5]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${receipt_file}" "${total_retries}" "${p_idx}" "${p_http}" "${receipt_jsonl}" | tr -d '\r'
      )
      _colab_keep_arrived_parts "${py_bin}" "${tmp_dl_dir}" "${out_dir}" "${receipt_file}" "${mode}" "${dst}" "${src}"
      rm -f "${dst}"
      if [ "${mode}" = "normal" ]; then
        colab_refuse_logged "${out_dir}" DOWNLOAD_PART_FAILED "${src} -> ${dst} part ${p_num}/${prep_part_count}: colab download rc=${p_rc} http=${p_http} attempts=${p_attempts} arrived_parts=[${arrived_csv}] (CLI output in colab.log; verified parts kept in ${out_dir}/salvage_partial)"
      fi
      return 1
    fi

    local got_p_bytes="" got_p_sha=""
    read -r got_p_bytes got_p_sha < <(
      "${py_bin}" -c '
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
h = hashlib.sha256()
sz = 0
with p.open("rb") as fh:
    for blk in iter(lambda: fh.read(1 << 20), b""):
        sz += len(blk)
        h.update(blk)
print(sz, h.hexdigest())
' "${p_local}" | tr -d '\r'
    )
    if [ "${got_p_bytes}" != "${p_exp_bytes}" ] || [ "${got_p_sha}" != "${p_exp_sha}" ]; then
      "${py_bin}" -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rec = json.loads(p.read_text(encoding="utf-8"))
rec.update({
    "retries": int(sys.argv[2]),
    "failed_part": int(sys.argv[3]),
    "verified": False,
    "status": "part_sha_mismatch",
})
p.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
with pathlib.Path(sys.argv[4]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${receipt_file}" "${total_retries}" "${p_idx}" "${receipt_jsonl}"
      rm -f "${tmp_dl_dir}/part.$(printf '%04d' "${p_idx}")"
      _colab_keep_arrived_parts "${py_bin}" "${tmp_dl_dir}" "${out_dir}" "${receipt_file}" "${mode}" "${dst}" "${src}"
      rm -f "${dst}"
      if [ "${mode}" = "normal" ]; then
        colab_refuse_logged "${out_dir}" DOWNLOAD_SHA_MISMATCH "${src} -> ${dst} part ${p_num}/${prep_part_count}: local sha256=${got_p_sha} (bytes=${got_p_bytes}) != VM manifest sha256=${p_exp_sha} (bytes=${p_exp_bytes})"
      fi
      return 1
    fi

    # Record arrived + verified part immediately on disk before moving to the next part.
    "${py_bin}" -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rec = json.loads(p.read_text(encoding="utf-8"))
idx = int(sys.argv[2])
rec["arrived_parts"].append(idx)
rec["arrived_part_details"].append({
    "index": idx,
    "bytes": int(sys.argv[3]),
    "sha256": sys.argv[4],
    "attempts": int(sys.argv[5]),
})
rec["retries"] = int(sys.argv[6])
tmp = p.with_suffix(p.suffix + ".tmp")
tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
tmp.replace(p)
' "${receipt_file}" "${p_idx}" "${got_p_bytes}" "${got_p_sha}" "${p_attempts}" "${total_retries}"

    k=$((k + 1))
  done

  # Reassemble on the rig and verify whole-file sha256 against the VM manifest before placing ${dst}.
  local reassembled_sha="" reassemble_ok=""
  IFS=$'\t' read -r reassemble_ok reassembled_sha < <(
    "${py_bin}" -c '
import hashlib, os, pathlib, sys
tmp_dir = pathlib.Path(sys.argv[1])
part_count = int(sys.argv[2])
dst = pathlib.Path(sys.argv[3])
exp_bytes = int(sys.argv[4])
exp_sha = sys.argv[5].lower()
tmp_dst = dst.with_name(dst.name + ".sdlab_reassembling")
whole_h = hashlib.sha256()
total = 0
with tmp_dst.open("wb") as out_fh:
    for idx in range(part_count):
        part_p = tmp_dir / f"part.{idx:04d}"
        with part_p.open("rb") as in_fh:
            for blk in iter(lambda: in_fh.read(1 << 20), b""):
                out_fh.write(blk)
                whole_h.update(blk)
                total += len(blk)
got_sha = whole_h.hexdigest().lower()
if total != exp_bytes or got_sha != exp_sha:
    tmp_dst.unlink(missing_ok=True)
    dst.unlink(missing_ok=True)
    print(f"MISMATCH\t{got_sha}:{total}")
else:
    os.replace(tmp_dst, dst)
    print(f"OK\t{got_sha}")
' "${tmp_dl_dir}" "${prep_part_count}" "${dst}" "${prep_whole_bytes}" "${prep_whole_sha}" | tr -d '\r'
  )

  if [ "${reassemble_ok}" != "OK" ]; then
    rm -f "${dst}"
    "${py_bin}" -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rec = json.loads(p.read_text(encoding="utf-8"))
rec.update({
    "verified": False,
    "whole_sha256_actual": sys.argv[2],
    "status": "whole_sha_mismatch",
})
p.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
with pathlib.Path(sys.argv[3]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${receipt_file}" "${reassembled_sha}" "${receipt_jsonl}"
    _colab_keep_arrived_parts "${py_bin}" "${tmp_dl_dir}" "${out_dir}" "${receipt_file}" "${mode}" "${dst}" "${src}"
    if [ "${mode}" = "normal" ]; then
      colab_refuse_logged "${out_dir}" DOWNLOAD_SHA_MISMATCH "${src} -> ${dst}: reassembled sha256=${reassembled_sha} != VM manifest sha256=${prep_whole_sha}:${prep_whole_bytes}"
    fi
    return 1
  fi

  "${py_bin}" -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rec = json.loads(p.read_text(encoding="utf-8"))
rec.update({
    "verified": True,
    "whole_sha256_actual": sys.argv[2],
    "status": "verified",
})
tmp = p.with_suffix(p.suffix + ".tmp")
tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
tmp.replace(p)
with pathlib.Path(sys.argv[3]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${receipt_file}" "${reassembled_sha}" "${receipt_jsonl}"

  rm -rf "${tmp_dl_dir}"
  return 0
}

# colab_download_checked <session> <remote> <local> <out_dir>: verified download (single-GET up to
# COLAB_DOWNLOAD_CHUNK_BYTES, or multi-part split + manifest + per-part 5xx retry + whole-file sha256
# verification above COLAB_DOWNLOAD_CHUNK_BYTES).
colab_download_checked() {
  local session="$1"
  local src="$2"
  local dst="$3"
  local out_dir="$4"
  _colab_download_transfer "normal" "${session}" "${src}" "${dst}" "${out_dir}"
}

# colab_refetch_missing_bundle_files <py_bin> <rung_py> <session> <bundle_tar> <manifest_check_json> <out_dir> <wall_start_epoch> <wall_limit_s> [pass_no] [pass_deadline_epoch] [only_list_file]:
# When initial `verify-bundle` fails on the success path, fetch each missing or mismatched file
# directly from `/content/lane3_train/<rel>` on the still-live VM (one bounded attempt per file per
# pass, within the remaining wall reserve before `wall_limit_s` and, on pass 2, before
# <pass_deadline_epoch>), verify bytes + sha256 against the VM's `training_folder_manifest.json`, and
# stage each verified file under `<out_dir>/recovered_train_outputs/<rel>`. A file whose VM source is
# itself bad (missing on the VM, or a different sha256 on the VM) is recorded as `vm_source_missing` or
# `vm_source_sha_mismatch` and is never retried: another fetch could only return the same bytes.
# This function does not repair the bundle: the repair runs on the rig after `colab stop`
# (`colab_repair_recovered_bundle`). Every pass appends to `.bundle_refetch_entries.jsonl` and rewrites
# `bundle_refetch.json` from it (the last entry for a path wins).
colab_refetch_missing_bundle_files() {
  local py_bin="$1"
  local rung_py="$2"
  local session="$3"
  local bundle_tar="$4"
  local manifest_check_json="$5"
  local out_dir="$6"
  local wall_start_epoch="$7"
  local wall_limit_s="$8"
  local pass_no="${9:-1}"
  local pass_deadline_epoch="${10:-0}"
  local only_list_file="${11:-}"

  local kill_grace="${COLAB_KILL_GRACE_S:-10}"
  local refetch_tmp="${out_dir}/.sdlab_refetch_tmp"
  local recovered_root="${out_dir}/recovered_train_outputs"
  local entries_all="${out_dir}/.bundle_refetch_entries.jsonl"
  mkdir -p "${recovered_root}"
  if [ "${pass_no}" = "1" ]; then
    rm -f "${out_dir}/.recovered_files.txt" "${entries_all}"
    : > "${out_dir}/.recovered_files.txt"
    : > "${entries_all}"
  fi
  rm -rf "${refetch_tmp}"
  mkdir -p "${refetch_tmp}"

  local rows=""
  rows="$("${py_bin}" - "${manifest_check_json}" "${only_list_file}" << 'PYEOF' | tr -d '\r'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(0)
only = None
if sys.argv[2]:
    op = pathlib.Path(sys.argv[2])
    only = {ln.strip() for ln in op.read_text(encoding="utf-8").splitlines() if ln.strip()} if op.is_file() else set()
data = json.loads(p.read_text(encoding="utf-8"))
bad = data.get("bad_entries") or []
for item in bad:
    rel = str(item.get("path") or "").strip()
    if not rel or ".." in pathlib.PurePosixPath(rel).parts:
        continue
    if only is not None and rel not in only:
        continue
    exp_b = int(item.get("expected_bytes") if item.get("expected_bytes") is not None else (item.get("bytes") or 0))
    exp_sha = str(item.get("expected_sha256") or item.get("sha256") or "").lower() or "-"
    reason = str(item.get("reason") or "mismatch") or "mismatch"
    print(f"{rel}\t{exp_b}\t{exp_sha}\t{reason}")
PYEOF
  )" || rows=""

  if [ -z "${rows}" ]; then
    if [ "${pass_no}" = "1" ]; then
      "${py_bin}" -c '
import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text(json.dumps({
    "attempted_files": [], "recovered_files": [], "still_bad_files": [], "source_bad_files": [],
    "repaired_bundle": False, "repair_status": "nothing_to_repair", "entries": [],
}, indent=2) + "\n", encoding="utf-8", newline="\n")
' "${out_dir}/bundle_refetch.json"
    fi
    rm -rf "${refetch_tmp}"
    return 1
  fi

  local file_list_csv=""
  file_list_csv="$("${py_bin}" -c 'import sys; print(",".join(ln.split("\t")[0] for ln in sys.stdin.read().splitlines() if ln.strip()))' <<< "${rows}" | tr -d '\r')"
  echo "BUNDLE_REFETCH_START session=${session} pass=${pass_no} files=[${file_list_csv}]" | tee -a "${out_dir}/guards.log" >&2

  local entries_jsonl="${refetch_tmp}/entries.jsonl"
  : > "${entries_jsonl}"
  local idx=0
  local recovered_count=0

  while IFS=$'\t' read -r b_rel b_exp_bytes b_exp_sha b_reason; do
    [ -z "${b_rel}" ] && continue
    [ "${b_exp_sha}" = "-" ] && b_exp_sha=""
    local rem_wall_s
    rem_wall_s="$("${py_bin}" -c '
import math, sys, time
start_e = float(sys.argv[1])
limit_s = float(sys.argv[2])
grace_k = int(sys.argv[3])
deadline_e = float(sys.argv[4])
now = time.time()
rem = math.floor((start_e + limit_s) - now) - grace_k
if deadline_e > 0:
    rem = min(rem, math.floor(deadline_e - now) - grace_k)
print(rem)
' "${wall_start_epoch}" "${wall_limit_s}" "${kill_grace}" "${pass_deadline_epoch}" | tr -d '\r')"

    if [ "${rem_wall_s}" -le 0 ]; then
      echo "BUNDLE_REFETCH_SKIPPED_WALL_RESERVE rel=${b_rel} pass=${pass_no} rem_wall_s=${rem_wall_s}" | tee -a "${out_dir}/guards.log" >&2
      "${py_bin}" -c '
import json, pathlib, sys
rec = {"path": sys.argv[2], "initial_reason": sys.argv[3], "pass": int(sys.argv[5]), "attempted": False, "recovered": False, "status": "skipped_wall_reserve", "rem_wall_s": int(sys.argv[4]), "source_bad": False}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${entries_jsonl}" "${b_rel}" "${b_reason}" "${rem_wall_s}" "${pass_no}"
      idx=$((idx + 1))
      continue
    fi

    local cand_local="${refetch_tmp}/cand_${idx}.bin"
    local dl_rc=0
    _colab_download_transfer "refetch" "${session}" "/content/lane3_train/${b_rel}" "${cand_local}" "${out_dir}" "${rem_wall_s}" "${b_exp_sha}" || dl_rc=$?

    local verify_state="" got_b="0" got_s="" source_bad="False"
    if [ "${dl_rc}" -eq 3 ]; then
      verify_state="VM_SOURCE_MISSING"
      source_bad="True"
    elif [ "${dl_rc}" -eq 4 ]; then
      verify_state="VM_SOURCE_SHA_MISMATCH"
      source_bad="True"
    elif [ "${dl_rc}" -eq 0 ] && [ -f "${cand_local}" ]; then
      read -r verify_state got_b got_s < <(
        "${py_bin}" -c '
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
exp_b = int(sys.argv[2])
exp_s = sys.argv[3].lower()
h = hashlib.sha256()
sz = 0
with p.open("rb") as fh:
    for blk in iter(lambda: fh.read(1 << 20), b""):
        sz += len(blk)
        h.update(blk)
gs = h.hexdigest().lower()
st = "OK" if (sz == exp_b and gs == exp_s) else "MISMATCH"
print(f"{st}\t{sz}\t{gs}")
' "${cand_local}" "${b_exp_bytes}" "${b_exp_sha}" | tr -d '\r'
      )
    else
      verify_state="DOWNLOAD_FAILED"
    fi

    if [ "${verify_state}" = "OK" ]; then
      local dest_rec="${recovered_root}/${b_rel}"
      mkdir -p "$(dirname -- "${dest_rec}")"
      mv -f "${cand_local}" "${dest_rec}"
      printf '%s\n' "${b_rel}" >> "${out_dir}/.recovered_files.txt"
      recovered_count=$((recovered_count + 1))
      echo "BUNDLE_REFETCH_FILE_OK rel=${b_rel} pass=${pass_no} bytes=${got_b} sha256=${got_s}" | tee -a "${out_dir}/guards.log" >&2
      "${py_bin}" -c '
import json, pathlib, sys
rec = {"path": sys.argv[2], "initial_reason": sys.argv[3], "pass": int(sys.argv[6]), "attempted": True, "recovered": True, "status": "recovered", "bytes": int(sys.argv[4]), "sha256": sys.argv[5], "source_bad": False}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${entries_jsonl}" "${b_rel}" "${b_reason}" "${got_b}" "${got_s}" "${pass_no}"
    else
      rm -f "${cand_local}"
      echo "BUNDLE_REFETCH_FILE_FAILED rel=${b_rel} pass=${pass_no} state=${verify_state} dl_rc=${dl_rc} source_bad=${source_bad}" | tee -a "${out_dir}/guards.log" >&2
      "${py_bin}" -c '
import json, pathlib, sys
rec = {"path": sys.argv[2], "initial_reason": sys.argv[3], "pass": int(sys.argv[6]), "attempted": True, "recovered": False, "status": sys.argv[4].lower(), "dl_rc": int(sys.argv[5]), "source_bad": sys.argv[7] == "True"}
with pathlib.Path(sys.argv[1]).open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec) + "\n")
' "${entries_jsonl}" "${b_rel}" "${b_reason}" "${verify_state}" "${dl_rc}" "${pass_no}" "${source_bad}"
    fi
    idx=$((idx + 1))
  done <<< "${rows}"

  cat "${entries_jsonl}" >> "${entries_all}"
  _colab_write_bundle_refetch_json "${py_bin}" "${entries_all}" "${out_dir}/bundle_refetch.json" "pending_after_stop"
  rm -rf "${refetch_tmp}"
  return 0
}

# _colab_write_bundle_refetch_json <py_bin> <entries_jsonl> <out_json> <repair_status>: rewrite
# bundle_refetch.json from the accumulated entries (last entry per path wins). repaired_bundle is true
# only once `repair_status` is "repaired".
_colab_write_bundle_refetch_json() {
  "$1" - "$2" "$3" "$4" << 'PYEOF'
import json, pathlib, sys
entries_p = pathlib.Path(sys.argv[1])
out_p = pathlib.Path(sys.argv[2])
repair_status = sys.argv[3]
all_entries = [json.loads(ln) for ln in entries_p.read_text(encoding="utf-8").splitlines() if ln.strip()]
latest = {}
for e in all_entries:
    latest[e["path"]] = e
entries = list(latest.values())
payload = {
    "attempted_files": [e["path"] for e in entries if e.get("attempted")],
    "recovered_files": [e["path"] for e in entries if e.get("recovered")],
    "still_bad_files": [e["path"] for e in entries if not e.get("recovered")],
    "source_bad_files": [e["path"] for e in entries if e.get("source_bad")],
    "repaired_bundle": repair_status == "repaired",
    "repair_status": repair_status,
    "passes": sorted({int(e.get("pass", 1)) for e in all_entries}),
    "entries": all_entries,
}
out_p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
PYEOF
}

# colab_refetch_followup_pass <py_bin> <guards_py> <rung_py> <session> <bundle_tar> <manifest_check_json> <out_dir> <wall_start_epoch> <wall_limit_s> <cap> <margin>:
# Replaces the old blind session hold. After the first per-file refetch, files whose VM source is bad
# (missing, or a different sha256 on the VM) are not retried and nothing waits for them: the session
# goes straight to the stop. Files that failed for any other reason (a transfer failure, a mismatch
# after the transfer) get ONE more bounded refetch pass while the VM is still up, bounded by the
# salvage bound and the cap left after the stop reserve. It never sleeps. session_hold.json records
# what ran (status skipped_source_bad | skipped_nothing_to_retry | skipped_no_cap_budget | followup_refetch).
colab_refetch_followup_pass() {
  local py_bin="$1"
  local guards_py="$2"
  local rung_py="$3"
  local session="$4"
  local bundle_tar="$5"
  local manifest_check_json="$6"
  local out_dir="$7"
  local wall_start_epoch="$8"
  local wall_limit_s="$9"
  local cap="${10}"
  local margin="${11}"

  printf '1\n' > "${out_dir}/cleanup_started.txt"

  local plan=""
  plan="$("${py_bin}" - "${guards_py}" "${out_dir}" "${cap}" "${margin}" << 'PYEOF' | tr -d '\r'
import importlib.util, json, math, os, pathlib, sys, time

guards_py = pathlib.Path(sys.argv[1])
out_dir = pathlib.Path(sys.argv[2])
cap = float(sys.argv[3])
margin = float(sys.argv[4])

spec = importlib.util.spec_from_file_location("launch_guards", guards_py)
lg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lg)

kill_grace_s = int(os.environ.get("COLAB_KILL_GRACE_S", "10"))
salvage_restart_s = int(os.environ.get("COLAB_SALVAGE_RESTART_TIMEOUT_S", "180"))
salvage_exec_s = int(os.environ.get("COLAB_SALVAGE_EXEC_TIMEOUT_S", "330"))
salvage_download_s = int(os.environ.get("COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S", "300"))
salvage_parts = int(os.environ.get("COLAB_SALVAGE_DOWNLOAD_PARTS", "1"))
salvage_dl_steps = salvage_parts if salvage_parts <= 1 else 2 + 2 * salvage_parts
salvage_steps_sum = (
    (salvage_restart_s + kill_grace_s)
    + (salvage_exec_s + kill_grace_s)
    + salvage_dl_steps * (salvage_download_s + kill_grace_s)
)
salvage_deadline_s = int(os.environ.get("SALVAGE_DEADLINE_S", str(salvage_steps_sum)))
salvage_bound_s = min(salvage_steps_sum, salvage_deadline_s)

stop_timeout_s = int(os.environ.get("COLAB_STOP_TIMEOUT_S", "60"))
stop_attempts = int(os.environ.get("COLAB_STOP_ATTEMPTS", "2"))
stop_bound_s = stop_attempts * (stop_timeout_s + kill_grace_s)

def _read_float(p: pathlib.Path):
    try:
        return float(p.read_text(encoding="utf-8").strip()) if p.is_file() else None
    except Exception:
        return None

open_epoch = _read_float(out_dir / "session_open_epoch.txt")
elapsed_s = max(0.0, time.time() - open_epoch) if open_epoch is not None else 0.0
max_rate = _read_float(out_dir / "max_rate.txt") or float(os.environ.get("RATE_CCU_PER_HOUR", "0.26"))
state_f = out_dir / "rate_window.json"
try:
    state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.is_file() else {}
except Exception:
    state = {}
proj = lg.gpu_projection_rate(state, max_rate)
priced_rate = float(proj) if proj is not None and float(proj) > 0.0 else float(max_rate)
start_bal = _read_float(out_dir / "start_balance.txt")
cur_bal = _read_float(out_dir / "end_balance.txt")
measured_drop = max(0.0, start_bal - cur_bal) if (start_bal is not None and cur_bal is not None) else 0.0
spent_now = max(measured_drop, (elapsed_s / 3600.0) * priced_rate)
stop_reserve = (stop_bound_s / 3600.0) * priced_rate
avail_units = max(0.0, cap - margin - spent_now - stop_reserve)
rem_cap_s = math.floor((avail_units / priced_rate) * 3600.0) if priced_rate > 0.0 else salvage_bound_s
pass_budget_s = max(0, min(salvage_bound_s, rem_cap_s))

entries_p = out_dir / ".bundle_refetch_entries.jsonl"
latest = {}
if entries_p.is_file():
    for ln in entries_p.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            e = json.loads(ln)
            latest[e["path"]] = e
unresolved = [e for e in latest.values() if not e.get("recovered")]
source_bad = [e["path"] for e in unresolved if e.get("source_bad")]
retry = [e["path"] for e in unresolved if not e.get("source_bad") and e.get("status") != "skipped_wall_reserve"]

mc_path = out_dir / "bundle_manifest_check.json"
missing_files, mismatched_files = [], []
if mc_path.is_file():
    try:
        mc = json.loads(mc_path.read_text(encoding="utf-8"))
        missing_files = list(mc.get("missing_files") or [])
        mismatched_files = list(mc.get("mismatched_files") or [])
    except Exception:
        pass

if not unresolved:
    status = "skipped_nothing_to_retry"
elif not retry:
    status = "skipped_source_bad" if source_bad else "skipped_nothing_to_retry"
elif pass_budget_s <= 0:
    status = "skipped_no_cap_budget"
else:
    status = "followup_refetch"

if unresolved:
    (out_dir / "session_hold.json").write_text(json.dumps({
        "session": os.environ.get("SESSION", ""),
        "status": status,
        "hold_bound_s": salvage_bound_s,
        "planned_hold_s": pass_budget_s if status == "followup_refetch" else 0,
        "held_s": 0.0,
        "slept": False,
        "retry_files": retry,
        "source_bad_files": source_bad,
        "missing_files": missing_files,
        "mismatched_files": mismatched_files,
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
(out_dir / ".followup_retry_files.txt").write_text("".join(f"{r}\n" for r in retry), encoding="utf-8", newline="\n")
print(f"{status}\t{pass_budget_s}\t{salvage_bound_s}\t{','.join(source_bad) or 'none'}\t{','.join(retry) or 'none'}")
PYEOF
  )" || plan="skipped_nothing_to_retry	0	0	none	none"

  local f_status="" f_budget="0" f_bound="0" f_source_bad="none" f_retry="none"
  IFS=$'\t' read -r f_status f_budget f_bound f_source_bad f_retry <<< "${plan}"

  if [ "${f_status}" != "followup_refetch" ]; then
    echo "BUNDLE_REFETCH_FOLLOWUP_SKIPPED session=${session} reason=${f_status} source_bad_files=[${f_source_bad}] retry_files=[${f_retry}]" | tee -a "${out_dir}/guards.log" >&2
    return 0
  fi

  echo "BUNDLE_REFETCH_FOLLOWUP_START session=${session} budget_s=${f_budget} salvage_bound_s=${f_bound} retry_files=[${f_retry}] source_bad_files=[${f_source_bad}]" | tee -a "${out_dir}/guards.log" >&2
  local t0 t1 deadline_epoch
  t0="$(date -u +%s)"
  deadline_epoch=$(( t0 + f_budget ))
  colab_refetch_missing_bundle_files "${py_bin}" "${rung_py}" "${session}" "${bundle_tar}" "${manifest_check_json}" \
    "${out_dir}" "${wall_start_epoch}" "${wall_limit_s}" 2 "${deadline_epoch}" "${out_dir}/.followup_retry_files.txt" || true
  t1="$(date -u +%s)"
  "${py_bin}" -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rec = json.loads(p.read_text(encoding="utf-8"))
rec.update({"held_s": float(sys.argv[2]), "completed": True})
p.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
' "${out_dir}/session_hold.json" "$(( t1 - t0 ))"
  echo "BUNDLE_REFETCH_FOLLOWUP_DONE session=${session} elapsed_s=$(( t1 - t0 )) budget_s=${f_budget}" | tee -a "${out_dir}/guards.log" >&2
}

# colab_print_unresolved_download_cmds <py_bin> <session> <out_dir>: before `colab stop`, print one
# ready-to-run `colab download -s <session> <vm path> <rig path>` line per file that is still unresolved
# (to guards.log, stderr and unresolved_downloads.txt), so the operator has the command to hand.
colab_print_unresolved_download_cmds() {
  local py_bin="$1"
  local session="$2"
  local out_dir="$3"
  local lines=""
  lines="$("${py_bin}" - "${session}" "${out_dir}" << 'PYEOF' | tr -d '\r'
import json, pathlib, shlex, sys
session = sys.argv[1]
out_dir = pathlib.Path(sys.argv[2])
entries_p = out_dir / ".bundle_refetch_entries.jsonl"
latest = {}
if entries_p.is_file():
    for ln in entries_p.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            e = json.loads(ln)
            latest[e["path"]] = e
for rel, e in latest.items():
    if e.get("recovered"):
        continue
    vm_path = "/content/lane3_train/" + rel
    rig_path = (out_dir / "recovered_train_outputs" / rel).as_posix()
    cmd = "colab download -s " + shlex.quote(session) + " " + shlex.quote(vm_path) + " " + shlex.quote(rig_path)
    print(f"BUNDLE_UNRESOLVED_FILE rel={rel} status={e.get('status')} run: {cmd}")
PYEOF
  )" || lines=""
  : > "${out_dir}/unresolved_downloads.txt"
  if [ -n "${lines}" ]; then
    printf '%s\n' "${lines}" | tee -a "${out_dir}/guards.log" "${out_dir}/unresolved_downloads.txt" >&2
  fi
}

# colab_stop_session_early <py_bin> <session> <out_dir>: stop the billed session as soon as every
# transfer is done, before any rig-side work (bundle repair, re-verification). Writes the same
# stop_path / stop_reached markers the EXIT trap writes and a `stopped_early.txt` marker so the trap
# does not stop the session a second time.
colab_stop_session_early() {
  local py_bin="$1"
  local session="$2"
  local out_dir="$3"
  printf '1\n' > "${out_dir}/cleanup_started.txt"
  printf 'trap\n' > "${out_dir}/stop_path.txt"
  printf '1\n' > "${out_dir}/stop_reached.txt"
  echo "STOP_EARLY_BEFORE_RIG_REPAIR session=${session}" | tee -a "${out_dir}/guards.log" >&2
  colab_stop_and_log_closing "${py_bin}" "${session}" "${out_dir}"
  # `colab_stop_and_log_closing` never fails, so confirm the stop from its own record. Only a confirmed stop
  # leaves `stopped_early.txt` (which tells the EXIT trap not to stop again). An unconfirmed one leaves the
  # trap to make its own bounded attempts, and withdraws `stop_reached.txt` so the wall watcher stays armed.
  if grep -F "STOP_COMPLETED" "${out_dir}/stop.log" 2>/dev/null | grep -Fq "session=${session}"; then
    printf '1\n' > "${out_dir}/stopped_early.txt"
  else
    rm -f "${out_dir}/stopped_early.txt" "${out_dir}/stop_reached.txt"
    echo "STOP_EARLY_UNCONFIRMED session=${session}: the EXIT trap will stop the session" | tee -a "${out_dir}/guards.log" >&2
  fi
}

# colab_repair_recovered_bundle <py_bin> <rung_py> <bundle_tar> <out_dir>: after the session has
# stopped, splice the SHA-verified refetched files into the bundle (`repair-bundle`) and record the
# outcome in bundle_refetch.json. Returns 0 when nothing needed repairing or the repair succeeded.
colab_repair_recovered_bundle() {
  local py_bin="$1"
  local rung_py="$2"
  local bundle_tar="$3"
  local out_dir="$4"
  local entries_all="${out_dir}/.bundle_refetch_entries.jsonl"
  local recovered_root="${out_dir}/recovered_train_outputs"
  [ -f "${entries_all}" ] || return 0
  if [ ! -s "${out_dir}/.recovered_files.txt" ]; then
    _colab_write_bundle_refetch_json "${py_bin}" "${entries_all}" "${out_dir}/bundle_refetch.json" "nothing_recovered"
    return 0
  fi
  local repair_args=(--stage-dir "${recovered_root}")
  while IFS= read -r spec_line; do
    [ -z "${spec_line}" ] && continue
    repair_args+=(--rel-file "${spec_line}")
  done < "${out_dir}/.recovered_files.txt"
  local repair_out="" repair_rc=0
  repair_out="$("${py_bin}" "${rung_py}" repair-bundle --bundle-tar "${bundle_tar}" "${repair_args[@]}" 2>&1)" || repair_rc=$?
  if [ "${repair_rc}" -eq 0 ]; then
    printf '%s\n' "${repair_out}" >> "${out_dir}/guards.log"
    _colab_write_bundle_refetch_json "${py_bin}" "${entries_all}" "${out_dir}/bundle_refetch.json" "repaired"
  else
    printf '%s\n' "${repair_out}" | tee -a "${out_dir}/guards.log" >&2
    _colab_write_bundle_refetch_json "${py_bin}" "${entries_all}" "${out_dir}/bundle_refetch.json" "repair_failed"
  fi
  return "${repair_rc}"
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
    colab_check_pre_exec_cap "${out_dir}" "rate_poll_${i}" || return 1
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
    if [ "${i}" -lt "${polls}" ]; then
      sleep "${interval_s}"
      colab_check_pre_exec_cap "${out_dir}" "rate_poll_sleep_${i}" || return 1
    fi
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

  local dl_chunk_env="${COLAB_DOWNLOAD_CHUNK_BYTES:-${COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT}}"
  local exec_args=(
    "-s" "${session}" "-f" "${runner_py}" "--timeout" "${exec_timeout}"
    "--env" "SDLAB_CONTENT=/content"
    "--env" "SDLAB_DL_CHUNK_BYTES=${dl_chunk_env}"
  )
  for kv in "${env_pairs[@]}"; do
    exec_args+=("--env" "${kv}")
  done

  colab exec "${exec_args[@]}" </dev/null > "${out_dir}/vitals.log" 2>&1 &
  EXEC_PID="$!"
  printf '%s\n' "${EXEC_PID}" >> "${out_dir}/.watcher_tracked_pids.txt" 2>/dev/null || true

  while kill -0 "${EXEC_PID}" 2>/dev/null; do
    sleep "${poll_s}"
    if ! kill -0 "${EXEC_PID}" 2>/dev/null; then
      break
    fi
    local now_epoch elapsed_s cur_size idle_s cur_setup_bytes setup_idle_s run_only_bytes
    now_epoch="$(date -u +%s)"
    if [ -f "${out_dir}/session_open_epoch.txt" ]; then
      elapsed_s="$("${py_bin}" -c 'import sys, time; print(f"{max(0.0, time.time() - float(open(sys.argv[1], encoding="utf-8").read().strip())):.6f}")' "${out_dir}/session_open_epoch.txt" 2>/dev/null || echo "$((now_epoch - start_epoch))")"
    else
      elapsed_s="$((now_epoch - start_epoch))"
    fi

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
    colab_run_bounded_salvage_step "${step_t}" "${kill_grace}" colab restart-kernel -s "${session}" >> "${out_dir}/bundle_now.log" 2>&1 || restart_rc=$?
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
    local dl_chunk_salvage="${COLAB_DOWNLOAD_CHUNK_BYTES:-${COLAB_DOWNLOAD_CHUNK_BYTES_DEFAULT}}"
    colab_run_bounded_salvage_step "${step_t}" "${kill_grace}" colab exec -s "${session}" -f "${bundle_now_py}" --timeout 300 \
      --env "SDLAB_CONTENT=/content" --env "SDLAB_BUNDLE_RC=${failed_rc}" \
      --env "SDLAB_DL_CHUNK_BYTES=${dl_chunk_salvage}" >> "${out_dir}/bundle_now.log" 2>&1 || exec_rc=$?
    if colab_rc_is_timeout "${exec_rc}"; then
      echo "SALVAGE_STEP_TIMEOUT bundle-now timeout_s=${step_t} kill_grace_s=${kill_grace} rc=${exec_rc}" >> "${out_dir}/guards.log"
    fi
  fi

  local dl_rc=0
  now_epoch="$(date -u +%s)"
  elapsed_s=$((now_epoch - start_epoch))
  if [ "${COLAB_CLEANUP_SKIP_SALVAGE:-0}" = "1" ] || [ "${elapsed_s}" -ge "${deadline_s}" ]; then
    echo "SALVAGE_DEADLINE_EXCEEDED download elapsed_s=${elapsed_s} deadline_s=${deadline_s}" >> "${out_dir}/guards.log"
    dl_rc=124
  else
    _colab_download_transfer "salvage" "${session}" "${remote_path}" "${local_dst}" "${out_dir}" "${start_epoch}" "${deadline_s}" || dl_rc=$?
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
      echo "STOP_COMPLETED attempt=${attempt}/${attempts} session=${session}" >> "${out_dir}/guards.log"
      echo "STOP_COMPLETED attempt=${attempt}/${attempts} session=${session}" >> "${out_dir}/stop.log"
      break
    fi
    if colab_rc_is_timeout "${stop_rc}"; then
      echo "STOP_TIMEOUT attempt=${attempt}/${attempts} session=${session} timeout_s=${stop_timeout} kill_grace_s=${kill_grace} rc=${stop_rc}" >> "${out_dir}/guards.log"
      echo "STOP_TIMEOUT attempt=${attempt}/${attempts} session=${session} timeout_s=${stop_timeout} kill_grace_s=${kill_grace} rc=${stop_rc}" >> "${out_dir}/stop.log"
    else
      echo "STOP_FAILED attempt=${attempt}/${attempts} session=${session} rc=${stop_rc}" >> "${out_dir}/guards.log"
      echo "STOP_FAILED attempt=${attempt}/${attempts} session=${session} rc=${stop_rc}" >> "${out_dir}/stop.log"
    fi
    if [ "${attempt}" -lt "${attempts}" ]; then
      local next_attempt=$((attempt + 1))
      echo "STOP_RETRY attempt=${next_attempt}/${attempts} session=${session}" >> "${out_dir}/guards.log"
      echo "STOP_RETRY attempt=${next_attempt}/${attempts} session=${session}" >> "${out_dir}/stop.log"
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
  export COLAB_ACTIVE_PY_BIN="${py_bin}"
  export COLAB_ACTIVE_GUARDS_PY="${guards_py}"
  export COLAB_ACTIVE_OUT_DIR="${out_dir}"
  export COLAB_ACTIVE_CAP="${cap}"
  export COLAB_ACTIVE_MARGIN="${margin}"
}

# colab_check_pre_exec_cap <out_dir>: evaluate the cap guard during pre-exec (between `colab new`
# succeeding and `colab exec` starting: rate polls, shape check, and uploads) using elapsed time
# since session_open_epoch.txt, the latest account balance, and the priced rate known at that moment
# (on GPU: max(--max-rate, highest stable window rate so far); on CPU: configured/pre-open rate).
# On a trip, records phase="pre_exec", logs REFUSED: CAP_GUARD_TRIPPED, and returns 1 so the caller's
# EXIT trap stops the session immediately (without salvage, since EXEC_IN_FLIGHT=0).
colab_check_pre_exec_cap() {
  local out_dir="$1"
  local checkpoint="${2:-pre_exec}"
  [ -n "${out_dir}" ] && [ -f "${out_dir}/session_opened.txt" ] || return 0
  [ "${EXEC_IN_FLIGHT:-0}" != "1" ] && [ ! -f "${out_dir}/cleanup_started.txt" ] && [ ! -f "${out_dir}/stop_reached.txt" ] || return 0
  local py_bin="${COLAB_ACTIVE_PY_BIN:-${PY_BIN:-}}"
  local guards_py="${COLAB_ACTIVE_GUARDS_PY:-${GUARDS_PY:-}}"
  local cap="${COLAB_ACTIVE_CAP:-${CAP:-}}"
  local margin="${COLAB_ACTIVE_MARGIN:-${MARGIN:-0.01}}"
  local wall_s="${WALL_S:-1800}"
  local grace_s="${GRACE_S:-120}"
  [ -n "${py_bin}" ] && [ -n "${guards_py}" ] && [ -n "${cap}" ] || return 0

  local guard_out=""
  local guard_rc=0
  guard_out="$("${py_bin}" - "${guards_py}" "${out_dir}" "${wall_s}" "${grace_s}" "${cap}" "${margin}" "${COLAB_CLEANUP_BOUND_S:-0}" "${COLAB_CARD_CLASS:-cpu}" "${RATE_CCU_PER_HOUR:-0.26}" "${checkpoint}" << 'PYEOF'
import json, sys, time
from pathlib import Path

guards_py = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
wall_s = float(sys.argv[3])
grace_s = float(sys.argv[4])
cap = float(sys.argv[5])
margin = float(sys.argv[6])
cleanup_bound_s = float(sys.argv[7])
card_class = sys.argv[8]
default_rate = float(sys.argv[9])
checkpoint = sys.argv[10]

sys.path.insert(0, str(guards_py.parent))
import launch_guards as lg

def _read_float(p: Path) -> float | None:
    if not p.is_file():
        return None
    try:
        return float(p.read_text(encoding="utf-8").strip())
    except Exception:
        return None

open_epoch = _read_float(out_dir / "session_open_epoch.txt")
elapsed_s = max(0.0, time.time() - open_epoch) if open_epoch is not None else 0.0

if card_class == "gpu":
    max_rate = _read_float(out_dir / "max_rate.txt") or default_rate
    state_f = out_dir / "rate_window.json"
    try:
        state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.is_file() else {}
    except Exception:
        state = {}
    proj = lg.gpu_projection_rate(state, max_rate)
    priced_rate = float(proj) if proj is not None and float(proj) > 0.0 else float(max_rate)
else:
    priced_rate = _read_float(out_dir / "rate_for_projection.txt") or default_rate

start_bal = _read_float(out_dir / "start_balance.txt")
cur_bal = _read_float(out_dir / "end_balance.txt")
if cur_bal is None:
    cur_bal = start_bal
err_f = out_dir / "usage_parse_error.txt"
usage_err = err_f.read_text(encoding="utf-8").strip() if err_f.is_file() and err_f.stat().st_size > 0 else None

argv = [
    "--mode", "pre_exec",
    "--phase", "pre_exec",
    "--checkpoint", checkpoint,
    "--elapsed-s", f"{elapsed_s:.6f}",
    "--wall-s", str(wall_s),
    "--grace-s", str(grace_s),
    "--cap", str(cap),
    "--margin", str(margin),
    "--cleanup-bound-s", str(cleanup_bound_s),
    "--rate", str(priced_rate),
]
if start_bal is not None:
    argv += ["--start-balance", str(start_bal)]
if cur_bal is not None:
    argv += ["--current-balance", str(cur_bal)]
if usage_err:
    argv += ["--usage-parse-error", usage_err]
raise SystemExit(lg.main(argv))
PYEOF
)" || guard_rc=$?

  if [ -n "${guard_out}" ]; then
    printf '%s\n' "${guard_out}" >> "${out_dir}/guards.log"
  fi
  if [ "${guard_rc}" -ne 0 ]; then
    printf 'pre_exec\n' > "${out_dir}/cap_trip_phase.txt"
    colab_refuse_from_guard_record "${py_bin}" "${out_dir}" "${guard_out}" CAP_GUARD_TRIPPED
    return 1
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

# colab_classify_open_failure <session> <out_dir> <new_out_file> <rc>:
# Distinguish HTTP 412 (account cap; never retry) from HTTP 503 (pool empty; retry later)
# and generic open failures, recording session_open_status.json and emitting a named refusal.
colab_classify_open_failure() {
  local session="$1"
  local out_dir="$2"
  local new_out_file="$3"
  local rc="$4"
  local is_timeout=0
  if colab_rc_is_timeout "${rc}"; then
    is_timeout=1
  fi

  local code_and_why
  code_and_why="$("${PY_BIN:?the kit must set PY_BIN}" - "${session}" "${out_dir}" "${new_out_file}" "${rc}" "${is_timeout}" << 'PYEOF'
import json
import re
import sys
from pathlib import Path

session = sys.argv[1]
out_dir = Path(sys.argv[2])
new_out_file = Path(sys.argv[3])
rc = int(sys.argv[4])
is_timeout = sys.argv[5] == "1"

raw = new_out_file.read_text(encoding="utf-8", errors="replace") if new_out_file.is_file() else ""
is_412 = (not is_timeout) and bool(
    re.search(r"(?:\bHTTP[/\s]*\d*(?:\.\d+)?\s+412\b|\b412\b|precondition failed|account(?:[\s_-]+assignment)?[\s_-]+cap)", raw, re.I)
)
is_503 = (not is_timeout) and (not is_412) and bool(
    re.search(r"(?:\bHTTP[/\s]*\d*(?:\.\d+)?\s+503\b|\b503\b|service unavailable|pool empty|backend unavailable)", raw, re.I)
)

if is_412:
    rec = {
        "http_status": 412,
        "classification": "account_cap",
        "retry_policy": "never_retry",
        "attempts": 1,
        "rc": rc,
    }
    code = "SESSION_OPEN_412_ACCOUNT_CAP"
    why = f"colab new -s {session} returned HTTP 412 (account cap; never retry)"
    guard_line = f"OPEN_412_ACCOUNT_CAP session={session} retry=never rc={rc}"
elif is_503:
    rec = {
        "http_status": 503,
        "classification": "pool_empty",
        "retry_policy": "retry_later",
        "attempts": 1,
        "rc": rc,
    }
    code = "SESSION_OPEN_503_POOL_EMPTY"
    why = f"colab new -s {session} returned HTTP 503 (pool empty; retry later)"
    guard_line = f"OPEN_503_POOL_EMPTY session={session} retry=later rc={rc}"
else:
    rec = {
        "http_status": None,
        "classification": "timeout" if is_timeout else "open_failed",
        "retry_policy": "inspect_error",
        "attempts": 1,
        "rc": rc,
    }
    code = "SESSION_OPEN_FAILED"
    why = f"colab new -s {session} failed (rc={rc})"
    guard_line = ""

(out_dir / "session_open_status.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
if guard_line:
    with (out_dir / "guards.log").open("a", encoding="utf-8", newline="\n") as gf:
        gf.write(guard_line + "\n")
    try:
        (out_dir / "session_open_started.txt").unlink()
    except OSError:
        pass
print(f"{code}\t{why}")
PYEOF
)"
  local r_code="${code_and_why%%$'\t'*}"
  local r_why="${code_and_why#*$'\t'}"
  colab_refuse_logged "${out_dir}" "${r_code:-SESSION_OPEN_FAILED}" "${r_why:-colab new -s ${session} failed (rc=${rc})}"
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

  local open_lock_timeout="${COLAB_OPEN_LOCK_TIMEOUT_S:-180}"
  local new_timeout="${COLAB_NEW_TIMEOUT_S:-180}"
  local kill_grace="${COLAB_KILL_GRACE_S:-10}"
  local new_out_file="${out_dir}/.colab_new_last.log"
  local open_rc=0
  if command -v flock >/dev/null 2>&1; then
    (
      local lock_rc=0
      colab_run_bounded "${open_lock_timeout}" "${kill_grace}" flock -x 9 || lock_rc=$?
      if [ "${lock_rc}" -ne 0 ]; then
        if colab_rc_is_timeout "${lock_rc}"; then
          echo "OPEN_LOCK_TIMEOUT lock=${lock_file} session=${session} timeout_s=${open_lock_timeout} kill_grace_s=${kill_grace} rc=${lock_rc}" >> "${out_dir}/guards.log"
        fi
        colab_refuse_logged "${out_dir}" OPEN_LOCK_TIMEOUT "could not acquire ${lock_file} within ${open_lock_timeout} s (rc=${lock_rc})"
        exit "${lock_rc}"
      fi
      printf '1\n' > "${lock_file}.held"
      printf '1\n' > "${out_dir}/session_open_started.txt"
      : > "${new_out_file}"
      local new_rc=0
      colab_run_bounded "${new_timeout}" "${kill_grace}" colab "${new_args[@]}" > "${new_out_file}" 2>&1 || new_rc=$?
      cat "${new_out_file}" >> "${out_dir}/colab.log" 2>/dev/null || true
      rm -f "${lock_file}.held"
      if colab_rc_is_timeout "${new_rc}"; then
        echo "NEW_TIMEOUT session=${session} timeout_s=${new_timeout} kill_grace_s=${kill_grace} rc=${new_rc}" >> "${out_dir}/guards.log"
      fi
      if [ "${new_rc}" -ne 0 ]; then
        colab_classify_open_failure "${session}" "${out_dir}" "${new_out_file}" "${new_rc}"
        rm -f "${new_out_file}"
        exit "${new_rc}"
      fi
      rm -f "${new_out_file}"
    ) 9>"${lock_file}" || open_rc=$?
    if [ "${open_rc}" -ne 0 ]; then
      return "${open_rc}"
    fi
  else
    local lock_dir="${lock_file}.lockdir"
    local lock_rc=0
    colab_run_bounded "${open_lock_timeout}" "${kill_grace}" bash -c 'while ! mkdir "$1" 2>/dev/null; do sleep 0.1; done' _ "${lock_dir}" || lock_rc=$?
    if [ "${lock_rc}" -ne 0 ]; then
      if colab_rc_is_timeout "${lock_rc}"; then
        echo "OPEN_LOCK_TIMEOUT lock=${lock_file} session=${session} timeout_s=${open_lock_timeout} kill_grace_s=${kill_grace} rc=${lock_rc}" >> "${out_dir}/guards.log"
      fi
      colab_refuse_logged "${out_dir}" OPEN_LOCK_TIMEOUT "could not acquire ${lock_dir} within ${open_lock_timeout} s (rc=${lock_rc})"
      return "${lock_rc}"
    fi
    printf '1\n' > "${lock_file}.held"
    printf '1\n' > "${out_dir}/session_open_started.txt"
    : > "${new_out_file}"
    local rc=0
    colab_run_bounded "${new_timeout}" "${kill_grace}" colab "${new_args[@]}" > "${new_out_file}" 2>&1 || rc=$?
    cat "${new_out_file}" >> "${out_dir}/colab.log" 2>/dev/null || true
    rm -f "${lock_file}.held"
    rmdir "${lock_dir}" 2>/dev/null || true
    if colab_rc_is_timeout "${rc}"; then
      echo "NEW_TIMEOUT session=${session} timeout_s=${new_timeout} kill_grace_s=${kill_grace} rc=${rc}" >> "${out_dir}/guards.log"
    fi
    if [ "${rc}" -ne 0 ]; then
      colab_classify_open_failure "${session}" "${out_dir}" "${new_out_file}" "${rc}"
      rm -f "${new_out_file}"
      return "${rc}"
    fi
    rm -f "${new_out_file}"
  fi
  "${PY_BIN:?the kit must set PY_BIN}" -c 'import json, sys; open(sys.argv[1], "w", encoding="utf-8", newline="\n").write(json.dumps({"http_status": 200, "classification": "opened", "retry_policy": "none", "attempts": 1, "rc": 0}, indent=2) + "\n")' "${out_dir}/session_open_status.json"
  printf '1\n' > "${out_dir}/session_opened.txt"
  # The cap clock starts the moment `colab new` succeeds on both GPU and CPU: rate polls, shape check,
  # and uploads are billed time and are checked against effective_trip throughout pre-exec.
  START_EPOCH="$(date -u +%s)"
  export START_EPOCH
  "${PY_BIN:?the kit must set PY_BIN}" -c 'import sys, time; open(sys.argv[1], "w", encoding="utf-8").write(f"{time.time():.6f}\n")' "${out_dir}/session_open_epoch.txt" 2>/dev/null \
    || printf '%s\n' "${START_EPOCH}" > "${out_dir}/session_open_epoch.txt"
  date -u -d "@${START_EPOCH}" +%Y-%m-%dT%H:%M:%SZ > "${out_dir}/cap_clock_started_at.txt"
  colab_check_pre_exec_cap "${out_dir}" "post_new" || return 1
  if ! colab_card_is_cpu "${card}"; then
    colab_check_session_shape "${session}" "${out_dir}" "${shape}" || return 1
    colab_check_pre_exec_cap "${out_dir}" "post_shape_check" || return 1
    colab_read_post_open_rate "${PY_BIN:?the kit must set PY_BIN}" "${out_dir}" "${COLAB_RATE_READ_POLLS}" \
      "${COLAB_RATE_READ_INTERVAL_S}" "$(cat "${out_dir}/max_rate.txt")" || return 1
    colab_check_pre_exec_cap "${out_dir}" "post_rate_read" || return 1
  fi
}

# colab_run_wall_watcher <main_pid> <wall_limit_s> <py_bin> <guards_py> <out_dir> <lane> <session> <card> <cap> <wall_s> <grace_s> <margin> <opened_at> <shas_json>:
# independent wall watcher with pre-trip liveness polling and post-trip escalation. During the
# <wall_limit_s> pre-trip wait, polls <main_pid> (`kill -0`) about every 1 s. If <main_pid> exits
# normally before the trip (`STOP_COMPLETED` logged), or dies before `colab new` (neither
# `session_open_started.txt` nor `session_opened.txt` exists), the watcher cleans up and exits 0
# without calling `colab stop`. If <main_pid> disappears before the trip after a session open was
# started/completed and before `STOP_COMPLETED`, the watcher kills tracked child pids, runs bounded
# `colab_stop_and_log_closing`, and writes `watcher_wait: "launcher_gone_pre_trip"` and
# `stop_path: "watcher"`, plus `window.json` and `outcome.draft.json`. Otherwise, when <wall_limit_s>
# elapses, writes `wall_trip_epoch.txt`, logs `REFUSED: WALL_GUARD_TRIPPED`, sends SIGTERM to
# <main_pid>, and waits for bounded trap cleanup or escalates.
colab_run_wall_watcher() {
  local main_pid="$1"
  local wall_limit_s="$2"
  local py_bin="$3"
  local guards_py="$4"
  local out_dir="$5"
  local lane="$6"
  local session="$7"
  local card="$8"
  local cap="$9"
  local wall_s="${10}"
  local grace_s="${11}"
  local margin="${12}"
  local opened_at="${13}"
  local shas_json="${14}"

  exec >/dev/null 2>&1 </dev/null
  trap - EXIT TERM INT
  colab_compute_cleanup_bounds "${lane}"
  local escalate_s="${COLAB_WALL_ESCALATE_S:-30}"
  local in_flight_bound_s="${COLAB_IN_FLIGHT_BOUND_S:-310}"
  local first_wait_s="${escalate_s}"
  if [ "${in_flight_bound_s}" -gt "${first_wait_s}" ]; then
    first_wait_s="${in_flight_bound_s}"
  fi
  local cleanup_stop_by_s="${COLAB_CLEANUP_STOP_ATTEMPTED_BY_S:-310}"
  local watcher_pid="${BASHPID:-$$}"

  local pre_trip_rc=0
  "${py_bin}" - "${main_pid}" "${watcher_pid}" "${wall_limit_s}" "${session}" "${out_dir}" << 'PYEOF' || pre_trip_rc=$?
import os, signal, sys, time
from pathlib import Path

main_pid = int(sys.argv[1])
watcher_pid = int(sys.argv[2])
wall_limit_s = float(sys.argv[3])
session = sys.argv[4]
out_dir = Path(sys.argv[5])
watcher_wait_p = out_dir / "watcher_wait.txt"
tracked_p = out_dir / ".watcher_tracked_pids.txt"
self_pid = os.getpid()

def stop_completed() -> bool:
    marker = f"session={session}"
    for log_name in ("stop.log", "guards.log"):
        lp = out_dir / log_name
        if not lp.is_file():
            continue
        try:
            for line in lp.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("STOP_COMPLETED ") and marker in line:
                    return True
        except OSError:
            continue
    return False

tracked_pids: set[int] = set()
last_written_pids: set[int] = set()

def record_children(flush: bool = False) -> None:
    if tracked_p.is_file():
        try:
            for line in tracked_p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    if pid not in (main_pid, watcher_pid, self_pid):
                        tracked_pids.add(pid)
        except OSError:
            pass
    stack = [main_pid, *list(tracked_pids)]
    seen: set[int] = set()
    used_task_children = False
    while stack:
        cur = stack.pop()
        if cur in seen or cur in (watcher_pid, self_pid):
            continue
        seen.add(cur)
        if cur != main_pid:
            tracked_pids.add(cur)
        ch_file = Path(f"/proc/{cur}/task/{cur}/children")
        if ch_file.is_file():
            used_task_children = True
            try:
                for tok in ch_file.read_text(encoding="utf-8").split():
                    if tok.isdigit():
                        stack.append(int(tok))
            except OSError:
                pass
    if not used_task_children:
        children: dict[int, list[int]] = {}
        for stat_p in Path("/proc").glob("[0-9]*/stat"):
            try:
                data = stat_p.read_text(encoding="utf-8")
                pid_s, rest = data.split(" (", 1)
                ppid_s = rest.rsplit(") ", 1)[1].split()[1]
                children.setdefault(int(ppid_s), []).append(int(pid_s))
            except Exception:
                continue
        stack = [main_pid, *list(tracked_pids)]
        seen = set()
        while stack:
            cur = stack.pop()
            if cur in seen or cur in (watcher_pid, self_pid):
                continue
            seen.add(cur)
            if cur != main_pid:
                tracked_pids.add(cur)
            stack.extend(children.get(cur, []))
    if tracked_pids and (flush or tracked_pids != last_written_pids):
        try:
            tracked_p.write_text("".join(f"{p}\n" for p in sorted(tracked_pids)), encoding="utf-8", newline="\n")
            last_written_pids.clear()
            last_written_pids.update(tracked_pids)
        except OSError:
            pass

def launcher_alive() -> bool:
    try:
        os.kill(main_pid, 0)
        return True
    except OSError:
        return False

def session_was_opened() -> bool:
    return (out_dir / "session_open_started.txt").is_file() or (out_dir / "session_opened.txt").is_file()

def kill_tracked() -> None:
    record_children(flush=True)
    for pid in sorted(tracked_pids, reverse=True):
        if pid not in (main_pid, watcher_pid, self_pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

deadline = time.monotonic() + max(0.0, wall_limit_s)
while True:
    record_children()
    if stop_completed():
        sys.exit(0)
    if (out_dir / "stop_reached.txt").is_file() and not session_was_opened():
        sys.exit(0)
    if not launcher_alive():
        if stop_completed():
            sys.exit(0)
        if not session_was_opened():
            kill_tracked()
            sys.exit(0)
        record_children(flush=True)
        watcher_wait_p.write_text("launcher_gone_pre_trip\n", encoding="utf-8", newline="\n")
        sys.exit(1)
    rem = deadline - time.monotonic()
    if rem <= 0.0:
        break
    time.sleep(min(1.0, rem))

record_children(flush=True)
sys.exit(2)
PYEOF

  local wait_rc=0
  if [ "${pre_trip_rc}" -eq 0 ]; then
    rm -f "${out_dir}/.watcher_tracked_pids.txt"
    return 0
  elif [ "${pre_trip_rc}" -eq 1 ]; then
    wait_rc=1
  elif [ "${pre_trip_rc}" -eq 2 ]; then
    "${py_bin}" -c 'import sys, time; open(sys.argv[1], "w", encoding="utf-8").write(f"{time.time():.6f}\n")' "${out_dir}/wall_trip_epoch.txt" 2>/dev/null \
      || date -u +%s > "${out_dir}/wall_trip_epoch.txt"
    echo "REFUSED: WALL_GUARD_TRIPPED: independent wall watcher: ${wall_limit_s} s (wall - grace) elapsed" >> "${out_dir}/guards.log"
    kill -TERM "${main_pid}" 2>/dev/null || true

    "${py_bin}" - "${main_pid}" "${watcher_pid}" "${escalate_s}" "${in_flight_bound_s}" "${cleanup_stop_by_s}" "${session}" "${out_dir}" << 'PYEOF' || wait_rc=$?
import os, sys, time
from pathlib import Path

main_pid = int(sys.argv[1])
watcher_pid = int(sys.argv[2])
escalate_s = float(sys.argv[3])
in_flight_bound_s = float(sys.argv[4])
cleanup_stop_by_s = float(sys.argv[5])
session = sys.argv[6]
out_dir = Path(sys.argv[7])
cleanup_started_p = out_dir / "cleanup_started.txt"
stop_reached_p = out_dir / "stop_reached.txt"
watcher_wait_p = out_dir / "watcher_wait.txt"
tracked_p = out_dir / ".watcher_tracked_pids.txt"
self_pid = os.getpid()

def stop_completed() -> bool:
    marker = f"session={session}"
    for log_name in ("stop.log", "guards.log"):
        lp = out_dir / log_name
        if not lp.is_file():
            continue
        try:
            for line in lp.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("STOP_COMPLETED ") and marker in line:
                    return True
        except OSError:
            continue
    return False

tracked_pids: set[int] = set()

def record_children() -> None:
    if tracked_p.is_file():
        try:
            for line in tracked_p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    if pid not in (main_pid, watcher_pid, self_pid):
                        tracked_pids.add(pid)
        except OSError:
            pass
    children: dict[int, list[int]] = {}
    for stat_p in Path("/proc").glob("[0-9]*/stat"):
        try:
            data = stat_p.read_text(encoding="utf-8")
            pid_s, rest = data.split(" (", 1)
            ppid_s = rest.rsplit(") ", 1)[1].split()[1]
            children.setdefault(int(ppid_s), []).append(int(pid_s))
        except Exception:
            continue
    stack = [main_pid, *list(tracked_pids)]
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur in seen or cur in (watcher_pid, self_pid):
            continue
        seen.add(cur)
        if cur != main_pid:
            tracked_pids.add(cur)
        stack.extend(children.get(cur, []))
    if tracked_pids:
        try:
            tracked_p.write_text("".join(f"{p}\n" for p in sorted(tracked_pids)), encoding="utf-8", newline="\n")
        except OSError:
            pass

def launcher_alive() -> bool:
    try:
        os.kill(main_pid, 0)
        return True
    except OSError:
        return False

trip_mono = time.monotonic()
first_wait_s = max(escalate_s, in_flight_bound_s)
first_deadline = trip_mono + first_wait_s
cleanup_seen = False

while time.monotonic() < first_deadline:
    record_children()
    if stop_completed():
        watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
        sys.exit(0)
    if cleanup_started_p.exists() or stop_reached_p.exists():
        cleanup_seen = True
        watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
        break
    if not launcher_alive():
        if stop_completed():
            watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
            sys.exit(0)
        if cleanup_started_p.exists() or stop_reached_p.exists():
            cleanup_seen = True
            break
        watcher_wait_p.write_text("escalated_launcher_gone\n", encoding="utf-8", newline="\n")
        sys.exit(1)
    time.sleep(0.05)

if not cleanup_seen:
    record_children()
    if stop_completed():
        watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
        sys.exit(0)
    elif cleanup_started_p.exists() or stop_reached_p.exists():
        cleanup_seen = True
        watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
    elif not launcher_alive():
        watcher_wait_p.write_text("escalated_launcher_gone\n", encoding="utf-8", newline="\n")
        sys.exit(1)
    else:
        watcher_wait_p.write_text("escalated_no_cleanup\n", encoding="utf-8", newline="\n")
        sys.exit(1)

stop_deadline = trip_mono + cleanup_stop_by_s
while time.monotonic() < stop_deadline:
    record_children()
    if stop_completed():
        watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
        sys.exit(0)
    if not launcher_alive():
        if stop_completed():
            watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
            sys.exit(0)
        watcher_wait_p.write_text("escalated_launcher_gone\n", encoding="utf-8", newline="\n")
        sys.exit(1)
    time.sleep(0.05)

record_children()
if stop_completed():
    watcher_wait_p.write_text("cleanup_seen\n", encoding="utf-8", newline="\n")
    sys.exit(0)
if not launcher_alive():
    watcher_wait_p.write_text("escalated_launcher_gone\n", encoding="utf-8", newline="\n")
    sys.exit(1)
watcher_wait_p.write_text("escalated_cleanup_overran\n", encoding="utf-8", newline="\n")
sys.exit(1)
PYEOF
  else
    rm -f "${out_dir}/.watcher_tracked_pids.txt"
    return 0
  fi

  if [ "${wait_rc}" -ne 1 ] || grep -q "^STOP_COMPLETED .*session=${session}" "${out_dir}/stop.log" 2>/dev/null; then
    rm -f "${out_dir}/.watcher_tracked_pids.txt"
    return 0
  fi

  local watcher_wait_state
  watcher_wait_state="$(cat "${out_dir}/watcher_wait.txt" 2>/dev/null || echo escalated_no_cleanup)"
  printf '1\n' > "${out_dir}/watcher_escalated.txt"
  printf 'watcher\n' > "${out_dir}/stop_path.txt"
  if [ "${watcher_wait_state}" = "launcher_gone_pre_trip" ] || [ "${watcher_wait_state}" = "escalated_launcher_gone" ] || [ -f "${out_dir}/stop_reached.txt" ]; then
    "${py_bin}" - "${main_pid}" "${watcher_pid}" "${out_dir}/.watcher_tracked_pids.txt" << 'PYEOF'
import os, signal, sys
from pathlib import Path

main_pid = int(sys.argv[1])
watcher_pid = int(sys.argv[2])
tracked_p = Path(sys.argv[3])
self_pid = os.getpid()
roots: list[int] = []
if tracked_p.is_file():
    for line in tracked_p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.isdigit():
            roots.append(int(line))
children: dict[int, list[int]] = {}
for stat_p in Path("/proc").glob("[0-9]*/stat"):
    try:
        data = stat_p.read_text(encoding="utf-8")
        pid_s, rest = data.split(" (", 1)
        ppid_s = rest.rsplit(") ", 1)[1].split()[1]
        children.setdefault(int(ppid_s), []).append(int(pid_s))
    except Exception:
        continue
roots.extend(children.get(main_pid, []))
out: list[int] = []
seen: set[int] = set()
stack = list(roots)
while stack:
    cur = stack.pop()
    if cur in seen or cur in (main_pid, watcher_pid, self_pid):
        continue
    seen.add(cur)
    out.append(cur)
    stack.extend(children.get(cur, []))
for pid in reversed(out):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
PYEOF
  fi
  echo "WALL_WATCHER_ESCALATED session=${session} escalate_s=${escalate_s} first_wait_s=${first_wait_s} cleanup_stop_attempted_by_s=${cleanup_stop_by_s} watcher_wait=${watcher_wait_state}" >> "${out_dir}/guards.log"
  if [ -f "${out_dir}/session_open_started.txt" ] || [ -f "${out_dir}/session_opened.txt" ]; then
    colab_stop_and_log_closing "${py_bin}" "${session}" "${out_dir}"
  fi
  local closed_at
  closed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  colab_write_window_and_outcome \
    "${py_bin}" "${out_dir}" "${lane}" "${session}" "${card}" \
    "${cap}" "${wall_s}" "${grace_s}" "${margin}" \
    "${opened_at}" "${closed_at}" 137 "${shas_json}" || true
  rm -f "${out_dir}/.watcher_tracked_pids.txt"
  colab_scrub_all_logs "${py_bin}" "${guards_py}" "${out_dir}" || true

  "${py_bin}" - "${main_pid}" "${watcher_pid}" << 'PYEOF'
import os, signal, sys
from pathlib import Path

main_pid = int(sys.argv[1])
watcher_pid = int(sys.argv[2])
children: dict[int, list[int]] = {}
for stat_p in Path("/proc").glob("[0-9]*/stat"):
    try:
        data = stat_p.read_text(encoding="utf-8")
        pid_s, rest = data.split(" (", 1)
        ppid_s = rest.rsplit(") ", 1)[1].split()[1]
        children.setdefault(int(ppid_s), []).append(int(pid_s))
    except Exception:
        continue

def subtree(root: int) -> list[int]:
    out: list[int] = []
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur == watcher_pid:
            continue
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out

for pid in reversed(subtree(main_pid)):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
PYEOF
  kill -9 "${main_pid}" 2>/dev/null || true
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
  done < <(find "${out_dir}" -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" -o -name "*.txt" -o -name "*.sh" \) -print0 2>/dev/null || true)
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
    "OPEN_LOCK_TIMEOUT",
    "SESSION_OPEN_FAILED",
    "UPLOAD_FAILED",
    "UPLOAD_PART_FAILED",
    "UPLOAD_SHA_MISMATCH",
    "UPLOAD_CHUNK_BYTES_INVALID",
    "DOWNLOAD_FAILED",
    "DOWNLOAD_PART_FAILED",
    "DOWNLOAD_SHA_MISMATCH",
    "DOWNLOAD_CHUNK_BYTES_INVALID",
    "DOWNLOAD_SPLIT_DISK_LOW",
    "PROBE_CPU_ONLY",
    "PROBE_SIZES_INVALID",
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
    "DATASET_MANIFEST_REQUIRED",
    "DATASET_MANIFEST_SHA_REQUIRED",
    "DATASET_MANIFEST_MISSING",
    "DATASET_MANIFEST_SHA_MISMATCH",
    "DATASET_MANIFEST_INVALID",
    "DATASET_ARCHIVE_SHA_MISMATCH",
    "JOB_REQUIRED",
    "JOB_SHA_REQUIRED",
    "JOB_CONFLICT",
    "JOB_FILE_MISSING",
    "JOB_SHA_MISMATCH",
    "JOB_TEMPLATE_INVALID",
    "JOB_UNPINNED_HUB_REF",
    "JOB_UNSUPPORTED_HUB_REF",
    "JOB_MODEL_LICENCE_NOT_ALLOWED",
    "JOB_SAVE_CADENCE_INVALID",
    "JOB_SAMPLE_CADENCE_INVALID",
    "JOB_TRIGGER_WITH_CACHED_EMBEDDINGS",
    "JOB_CAPTION_DROPOUT_INVALID",
    "DOWNLOAD_TIMEOUT_INVALID",
    "DOWNLOAD_TIMEOUT_REQUIRED",
    "DOWNLOAD_TIMEOUT_TOO_SHORT",
    "UPLOAD_TIMEOUT_INVALID",
    "UPLOAD_TIMEOUT_TOO_SHORT",
    "INPUT_FILE_MISSING",
    "INPUT_SHA_MISMATCH",
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
    "TRAIN_STEP_TIME_REQUIRED",
    "TRAIN_WALL_TOO_SHORT",
    "TRAIN_OUTPUT_PROJECTION_REQUIRED",
    "OPTIMIZER_SIZE_SOURCE_REQUIRED",
    "TRAIN_OUTPUT_DISK_LOW",
    "COPY_OFF_FAILED",
    "BUNDLE_DISK_LOW",
    "TRAIN_OUTPUT_MANIFEST_MISMATCH",
    "RUNG_JOB_REQUIRED",
    "MODEL_AUTH_FAILED",
    "MODEL_REVISION_NOT_FOUND",
    "MODEL_METADATA_FAILED",
    "HF_TOKEN_STAGING_FAILED",
    "HF_TOKEN_SHRED_FAILED",
    "LANE1_MODE_INVALID",
    "RENDER_OPTION_WITHOUT_RENDER",
    "RENDER_REQUIRES_GPU",
    "RENDER_CPU_STUB_REQUIRES_CPU",
    "RENDER_MANIFEST_REQUIRED",
    "RENDER_JOBS_REQUIRED",
    "RENDER_JOBS_SHA_REQUIRED",
    "RENDER_COPY_BACK_REQUIRED",
    "RENDER_CAP_REQUIRED",
    "RENDER_MAX_RATE_REQUIRED",
    "JOBS_FILE_MISSING",
    "JOBS_SHA_MISMATCH",
    "RENDER_JOB_INVALID",
    "WEIGHTS_MANIFEST_INVALID",
    "WEIGHTS_REVISION_INVALID",
    "WEIGHTS_DEST_INVALID",
    "WEIGHTS_LICENCE_INVALID",
    "WEIGHTS_MODEL_EXCLUDED",
    "WEIGHTS_MOUNT_FORBIDDEN",
    "WEIGHTS_SHA_MISMATCH",
    "WEIGHTS_CORRUPT",
    "BG_REMOVAL_FORBIDDEN",
    "COMFY_STARTUP_FAILED",
    "RENDER_CONSECUTIVE_FAILURES",
    "BIREFNET_NODE_NOT_INSTALLED",
    "WEIGHTS_DISK_LOW",
    "SESSION_OPEN_412_ACCOUNT_CAP",
    "SESSION_OPEN_503_POOL_EMPTY",
    # Rig-side live guards (colab_check_cap_and_ram, colab_run_exec_with_live_guards).
    "HOST_RAM_PROJECTION_EXCEEDED",
    "HOST_RAM_UNREADABLE",
    "WALL_GUARD_TRIPPED",
    "CAP_GUARD_TRIPPED",
    "COLAB_USAGE_PARSE_FAILED",
    "DEAD_HARNESS_TRIPPED",
    "STALL_GUARD_TRIPPED",
    "SETUP_STALL_TRIPPED",
    "VITALS_PHASE_UNREADABLE",
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
    job_sha256 = read_text_file(out_dir / "job_sha256.txt") or rung_job_sha256
    dataset_manifest_sha256 = read_text_file(out_dir / "dataset_manifest_sha256.txt")
    dataset_archive_sha256 = read_text_file(out_dir / "dataset_archive_sha256.txt")

    bundle_sizes: dict[str, int] = {}
    bundle_texts: dict[str, str] = {}
    for tar_p in sorted(out_dir.glob("*.tar.gz")):
        if not tarfile.is_tarfile(tar_p):
            continue
        try:
            with tarfile.open(tar_p, "r:gz") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    rel = member.name.lstrip("/")
                    while rel.startswith("./"):
                        rel = rel[2:]
                    bundle_sizes[rel] = member.size
                    if rel in ("rung_job.yaml", "train.log", "rung_outputs/manifest.jsonl") and rel not in bundle_texts:
                        ext = tf.extractfile(member)
                        if ext is not None:
                            bundle_texts[rel] = ext.read().decode("utf-8", errors="replace")
        except Exception:
            continue

    rung_job_yaml_text = bundle_texts.get("rung_job.yaml")
    train_log_text = bundle_texts.get("train.log")
    manifest_jsonl_text = bundle_texts.get("rung_outputs/manifest.jsonl")

    train_steps_target: int | None = None
    job_name: str | None = None
    if rung_job_yaml_text is not None:
        m_steps = re.search(r"^\s*steps:\s*(\d+)\s*$", rung_job_yaml_text, re.M)
        if m_steps:
            train_steps_target = int(m_steps.group(1))
        m_name = re.search(r"^\s{2}name:\s*(\S+)\s*$", rung_job_yaml_text, re.M) or re.search(
            r"^\s*name:\s*(\S+)\s*$", rung_job_yaml_text, re.M
        )
        if m_name:
            job_name = m_name.group(1).strip("\"'")

    latest_manifest: dict[str, dict] = {}
    if manifest_jsonl_text is not None:
        for ln in manifest_jsonl_text.splitlines():
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("path"), str):
                latest_manifest[rec["path"]] = rec

    complete_ckpts: list[str] = []
    for rel_ckpt, rec in sorted(latest_manifest.items()):
        if (
            not rel_ckpt.endswith(".safetensors")
            or any(part.startswith("_") for part in Path(rel_ckpt).parts[:-1])
            or rec.get("partial")
        ):
            continue
        rec_bytes = int(rec.get("bytes") or 0)
        tar_rel = f"rung_outputs/{rel_ckpt}"
        if rec_bytes > 0 and bundle_sizes.get(tar_rel) == rec_bytes:
            complete_ckpts.append(rel_ckpt)

    step_candidates: list[int] = []
    for rel_ckpt in complete_ckpts:
        ckpt_name = Path(rel_ckpt).name
        m_ckpt = (
            re.match(rf"^{re.escape(job_name)}_(\d+)\.safetensors$", ckpt_name)
            if job_name
            else re.search(r"_(\d{6,})\.safetensors$", ckpt_name)
        )
        if m_ckpt:
            step_candidates.append(int(m_ckpt.group(1)))

    if train_log_text is not None:
        for frame in re.split(r"[\r\n]+", train_log_text):
            if not frame:
                continue
            if job_name and train_steps_target is not None:
                for m_bar in re.finditer(
                    rf"(?:^|\b){re.escape(job_name)}:.*?\b(\d+)/{train_steps_target}(?!\d)",
                    frame,
                ):
                    step_candidates.append(int(m_bar.group(1)))
            if train_steps_target is not None:
                for m_st in re.finditer(rf"\bsteps?\s+(\d+)/{train_steps_target}(?!\d)", frame, re.I):
                    step_candidates.append(int(m_st.group(1)))
            for m_sav in re.finditer(r"\bSaving at step\s+(\d+)\b", frame):
                step_candidates.append(int(m_sav.group(1)))

    train_steps_done: int | None
    if step_candidates:
        train_steps_done = max(step_candidates)
    elif train_log_text is not None or manifest_jsonl_text is not None:
        train_steps_done = 0
    else:
        train_steps_done = None

    final_checkpoint_present = False
    final_checkpoint_path: str | None = None
    if train_steps_target is not None and train_steps_target > 0 and complete_ckpts:
        matched_final: str | None = None
        for rel_ckpt in complete_ckpts:
            ckpt_name = Path(rel_ckpt).name
            m_ckpt = (
                re.match(rf"^{re.escape(job_name)}_(\d+)\.safetensors$", ckpt_name)
                if job_name
                else re.search(r"_(\d{6,})\.safetensors$", ckpt_name)
            )
            if m_ckpt and int(m_ckpt.group(1)) == train_steps_target:
                matched_final = rel_ckpt
                break
        if matched_final is None and job_name:
            numbered_suffix = f"_{train_steps_target:09d}.safetensors"
            has_partial_final = any(
                p.endswith(numbered_suffix)
                and not any(part.startswith("_") for part in Path(p).parts[:-1])
                and bool(r.get("partial"))
                for p, r in latest_manifest.items()
            )
            if not has_partial_final:
                for rel_ckpt in complete_ckpts:
                    if Path(rel_ckpt).name == f"{job_name}.safetensors":
                        matched_final = rel_ckpt
                        break
        if matched_final is not None:
            final_checkpoint_present = True
            final_checkpoint_path = f"rung_outputs/{matched_final}"

    train_completed = bool(
        train_steps_target is not None
        and train_steps_target > 0
        and train_steps_done == train_steps_target
        and final_checkpoint_present
    )

    run_plan: dict = {}
    if (out_dir / "run_plan.json").is_file():
        try:
            loaded_plan = json.loads((out_dir / "run_plan.json").read_text(encoding="utf-8"))
            if isinstance(loaded_plan, dict):
                run_plan = loaded_plan
        except ValueError:
            run_plan = {}
    bundle_manifest_check = None
    if (out_dir / "bundle_manifest_check.json").is_file():
        try:
            bundle_manifest_check = json.loads((out_dir / "bundle_manifest_check.json").read_text(encoding="utf-8"))
        except ValueError:
            bundle_manifest_check = None
    bundle_refetch = None
    if (out_dir / "bundle_refetch.json").is_file():
        try:
            bundle_refetch = json.loads((out_dir / "bundle_refetch.json").read_text(encoding="utf-8"))
        except ValueError:
            bundle_refetch = None
    salvage_partial = []
    sp_dir = out_dir / "salvage_partial"
    if sp_dir.is_dir():
        salvage_partial = sorted(d.name for d in sp_dir.iterdir() if d.is_dir())
    unresolved_downloads = []
    ud_p = out_dir / "unresolved_downloads.txt"
    if ud_p.is_file():
        unresolved_downloads = [ln for ln in ud_p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    session_hold = None
    if (out_dir / "session_hold.json").is_file():
        try:
            session_hold = json.loads((out_dir / "session_hold.json").read_text(encoding="utf-8"))
        except ValueError:
            session_hold = None

    train_fields = {
        "train": train_state,
        "trained": bool(final_status == "ok" and train_state == "trained"),
        "train_steps_done": train_steps_done,
        "train_steps_target": train_steps_target,
        "final_checkpoint_present": final_checkpoint_present,
        "final_checkpoint_path": final_checkpoint_path,
        "train_completed": train_completed,
        "rung_job": rung_job,
        "rung_job_sha256": rung_job_sha256,
        "job_sha256": job_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "dataset_archive_sha256": dataset_archive_sha256,
        "bundle_projection": run_plan.get("bundle_projection"),
        "download_timeout_basis": run_plan.get("download_timeout_basis"),
        "upload_timeout_check": run_plan.get("upload_timeout_check"),
        "wall_allowance": run_plan.get("wall_allowance"),
        "output_disk_projection": run_plan.get("output_disk_projection"),
        "training_output_manifest_check": bundle_manifest_check,
        "bundle_refetch": bundle_refetch,
        "session_hold": session_hold,
        "salvage_partial_dirs": salvage_partial,
        "unresolved_download_commands": unresolved_downloads,
        "stopped_before_rig_repair": (out_dir / "stopped_early.txt").is_file(),
    }

kill_grace_s = int(os.environ.get("COLAB_KILL_GRACE_S", "10"))
dl_timeout_s = int(os.environ.get("COLAB_DOWNLOAD_TIMEOUT_S", "300"))
dl_timeout_source = os.environ.get("COLAB_DOWNLOAD_TIMEOUT_SOURCE", "default")
up_timeout_s = int(os.environ.get("COLAB_UPLOAD_TIMEOUT_S", "120"))
up_timeout_source = os.environ.get("COLAB_UPLOAD_TIMEOUT_SOURCE", "default")
up_reassemble_timeout_raw = os.environ.get("COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S", "").strip()
up_reassemble_timeout_s = int(up_reassemble_timeout_raw) if up_reassemble_timeout_raw.isdigit() and int(up_reassemble_timeout_raw) > 0 else None
up_reassemble_timeout_source = os.environ.get("COLAB_UPLOAD_REASSEMBLE_TIMEOUT_SOURCE", "size_and_rate")
up_reassemble_mb_s = float(os.environ.get("COLAB_UPLOAD_REASSEMBLE_MB_S", "25"))
up_reassemble_mb_s_source = os.environ.get("COLAB_UPLOAD_REASSEMBLE_MB_S_SOURCE", "default")
up_chunk_bytes = int(os.environ.get("COLAB_UPLOAD_CHUNK_BYTES", "33554432"))
up_chunk_source = os.environ.get("COLAB_UPLOAD_CHUNK_SOURCE", "default")
dl_chunk_bytes = int(os.environ.get("COLAB_DOWNLOAD_CHUNK_BYTES", "268435456"))
dl_chunk_source = os.environ.get("COLAB_DOWNLOAD_CHUNK_SOURCE", "default")

upload_transfers: list[dict] = []
if (out_dir / "upload_receipts.jsonl").is_file():
    for uln in (out_dir / "upload_receipts.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        if not uln.strip():
            continue
        try:
            urec = json.loads(uln)
            if isinstance(urec, dict):
                upload_transfers.append(urec)
        except ValueError:
            pass

bundle_download: dict | None = None
if (out_dir / "bundle_download.json").is_file():
    try:
        loaded_bd = json.loads((out_dir / "bundle_download.json").read_text(encoding="utf-8"))
        if isinstance(loaded_bd, dict):
            bundle_download = loaded_bd
    except ValueError:
        bundle_download = None

salvage_bundle_download: dict | None = None
if (out_dir / "salvage_bundle_download.json").is_file():
    try:
        loaded_sbd = json.loads((out_dir / "salvage_bundle_download.json").read_text(encoding="utf-8"))
        if isinstance(loaded_sbd, dict):
            salvage_bundle_download = loaded_sbd
    except ValueError:
        salvage_bundle_download = None

effective_bundle_download = bundle_download if bundle_download is not None else salvage_bundle_download
sess_timeout_s = int(os.environ.get("COLAB_SESSIONS_TIMEOUT_S", "30"))
prep_exec_s = min(dl_timeout_s, 180)
reassemble_bound_s = int(os.environ.get("COLAB_REASSEMBLE_BOUND_S", "0") or "0")
in_flight_bound_s = max(dl_timeout_s, up_timeout_s, sess_timeout_s, prep_exec_s, reassemble_bound_s) + kill_grace_s
salvage_restart_s = int(os.environ.get("COLAB_SALVAGE_RESTART_TIMEOUT_S", "180"))
salvage_exec_s = int(os.environ.get("COLAB_SALVAGE_EXEC_TIMEOUT_S", "330"))
salvage_download_s = int(os.environ.get("COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S", "300"))
salvage_parts = int(os.environ.get("COLAB_SALVAGE_DOWNLOAD_PARTS", "1"))
salvage_download_steps = salvage_parts if salvage_parts <= 1 else 2 + 2 * salvage_parts
salvage_steps_sum_s = (
    (salvage_restart_s + kill_grace_s)
    + (salvage_exec_s + kill_grace_s)
    + salvage_download_steps * (salvage_download_s + kill_grace_s)
)
salvage_deadline_s = int(os.environ.get("SALVAGE_DEADLINE_S", str(salvage_steps_sum_s)))
stop_timeout_s = int(os.environ.get("COLAB_STOP_TIMEOUT_S", "60"))
stop_attempts = int(os.environ.get("COLAB_STOP_ATTEMPTS", "2"))
stop_bound_s = stop_attempts * (stop_timeout_s + kill_grace_s)
salvage_bound_s = (
    min(salvage_steps_sum_s, salvage_deadline_s)
    if (lane == "train" or (lane == "render" and os.environ.get("COLAB_RENDER_SALVAGE", "0") == "1"))
    else 0
)
cleanup_stop_attempted_by_s = in_flight_bound_s + salvage_bound_s
cleanup_bound_s = cleanup_stop_attempted_by_s + stop_bound_s
stop_path_raw = read_text_file(out_dir / "stop_path.txt")
stop_path = stop_path_raw if stop_path_raw in ("trap", "watcher") else "trap"
watcher_wait_raw = read_text_file(out_dir / "watcher_wait.txt")
watcher_wait = (
    watcher_wait_raw
    if watcher_wait_raw in (
        "none",
        "cleanup_seen",
        "escalated_no_cleanup",
        "escalated_cleanup_overran",
        "escalated_launcher_gone",
        "launcher_gone_pre_trip",
    )
    else "none"
)
cap_trip_phase = read_text_file(out_dir / "cap_trip_phase.txt")

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

session_open_status: dict | None = None
if (out_dir / "session_open_status.json").is_file():
    try:
        loaded_sos = json.loads((out_dir / "session_open_status.json").read_text(encoding="utf-8"))
        if isinstance(loaded_sos, dict):
            session_open_status = loaded_sos
    except ValueError:
        session_open_status = None

window_payload = {
    **vm_facts,
    "window_id": session,
    "lane": lane,
    "session": session,
    "card": card,
    "shape_requested": shape_requested,
    "shape_check": shape_check,
    "session_open_status": session_open_status,
    "status": final_status,
    "refusal_code": refusal_code,
    "why": refusal_why,
    "cap": cap,
    "cap_ccu": cap,
    "wall_s": wall_s,
    "grace_s": grace_s,
    "margin": margin,
    "download_timeout_s": dl_timeout_s,
    "download_timeout_source": dl_timeout_source,
    "salvage_download_timeout_s": salvage_download_s,
    "salvage_download_parts": salvage_parts,
    "salvage_deadline_s": salvage_deadline_s,
    "upload_timeout_s": up_timeout_s,
    "upload_timeout_source": up_timeout_source,
    "upload_reassemble_timeout_s": up_reassemble_timeout_s,
    "upload_reassemble_timeout_source": up_reassemble_timeout_source,
    "upload_reassemble_mb_s": up_reassemble_mb_s,
    "upload_reassemble_mb_s_source": up_reassemble_mb_s_source,
    "upload_chunk_bytes": up_chunk_bytes,
    "upload_chunk_source": up_chunk_source,
    "download_chunk_bytes": dl_chunk_bytes,
    "download_chunk_source": dl_chunk_source,
    "upload_transfers": upload_transfers,
    "bundle_download": effective_bundle_download,
    "salvage_bundle_download": salvage_bundle_download,
    "cleanup_stop_attempted_by_s": cleanup_stop_attempted_by_s,
    "cleanup_bound_s": cleanup_bound_s,
    "stop_path": stop_path,
    "watcher_wait": watcher_wait,
    "phase": cap_trip_phase if cap_trip_phase else ("live" if (out_dir / "session_opened.txt").is_file() else "pre_open"),
    "cap_trip_phase": cap_trip_phase,
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
    "session_open_status": session_open_status,
    "status": final_status,
    "refusal_code": refusal_code,
    "why": refusal_why,
    "phase": cap_trip_phase if cap_trip_phase else ("live" if (out_dir / "session_opened.txt").is_file() else "pre_open"),
    "cap_trip_phase": cap_trip_phase,
    "watcher_wait": watcher_wait,
    "exit_code": exit_code,
    "opened_at": opened_at,
    "closed_at": closed_at,
    "upload_chunk_bytes": up_chunk_bytes,
    "download_chunk_bytes": dl_chunk_bytes,
    "upload_transfers": upload_transfers,
    "bundle_download": effective_bundle_download,
    "salvage_bundle_download": salvage_bundle_download,
    **train_fields,
}
(out_dir / "outcome.draft.json").write_text(json.dumps(outcome_payload, indent=2) + "\n", encoding="utf-8", newline="\n")
PYEOF
}
