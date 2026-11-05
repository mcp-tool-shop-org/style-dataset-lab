#!/usr/bin/env bash
# Shared Colab window lifecycle, lock, wall/cap/vitals/RAM guards, token scrubber, and EXIT trap.
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

  local usage_json
  usage_json="$(colab usage </dev/null 2>>"${out_dir}/colab.log" || echo '{"balance_ccu":10.0,"rate_ccu_per_hour":0.08}')"
  echo "${usage_json}" >> "${out_dir}/usage.log"

  "${py_bin}" "${guards_py}" \
    --mode "${mode}" \
    --elapsed-s "${elapsed_s}" \
    --wall-s "${wall_s}" \
    --grace-s "${grace_s}" \
    --cap "${cap}" \
    --margin "${margin}" \
    --rate "0.08" </dev/null >> "${out_dir}/guards.log"

  "${py_bin}" "${guards_py}" \
    --check-ram \
    --current-anon-mb "${CURRENT_ANON_MB:-512}" \
    --projected-delta-mb "${PROJECTED_DELTA_MB:-2048}" \
    --mem-total-mb "${MEM_TOTAL_MB:-12288}" </dev/null >> "${out_dir}/guards.log"
}

colab_open_session_locked() {
  local session="$1"
  local card="$2"
  local out_dir="$3"
  local lock_file="${COLAB_OPEN_LOCK:-/tmp/colab-window-open.lock}"
  mkdir -p "$(dirname "${lock_file}")"

  local new_args=()
  if [ "${card}" = "CPU-high-mem" ] || [ "${card}" = "CPU" ]; then
    new_args=("new" "--high-mem" "-s" "${session}")
  else
    new_args=("new" "--gpu" "${card}" "--high-mem" "-s" "${session}")
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
  done < <(find "${out_dir}" -type f \( -name "*.log" -o -name "*.json" -o -name "*.txt" \) -print0 2>/dev/null || true)
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
import json
import sys
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
window_payload = {
    "window_id": session,
    "lane": lane,
    "session": session,
    "card": card,
    "cap": cap,
    "wall_s": wall_s,
    "grace_s": grace_s,
    "margin": margin,
    "input_shas": shas_raw.get("verified_shas", shas_raw),
    "opened_at": opened_at,
    "closed_at": closed_at,
    "exit_code": exit_code,
}
(out_dir / "window.json").write_text(json.dumps(window_payload, indent=2) + "\n", encoding="utf-8", newline="\n")

outcome_payload = {
    "window_id": session,
    "lane": lane,
    "session": session,
    "card": card,
    "status": "ok" if exit_code == 0 else "failed",
    "exit_code": exit_code,
    "opened_at": opened_at,
    "closed_at": closed_at,
}
(out_dir / "outcome.draft.json").write_text(json.dumps(outcome_payload, indent=2) + "\n", encoding="utf-8", newline="\n")
PYEOF
}
