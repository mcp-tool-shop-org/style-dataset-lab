#!/usr/bin/env bash
# Single-session CPU-high-mem probe for the unchunked `colab upload` (PUT) and `colab download`
# (GET) size limits in google-colab-cli (`colab_cli/contents.py`).
#
# Booked through the Publisher and executed by the Book Keeper. Uses `colab_window.sh`'s open lock,
# cap/RAM/wall guards, session open (`CPU-high-mem`), EXIT trap, bounded `colab stop`, receipt
# writer, and token scrubber.
#
# Default sweeps (sizes configurable via `--upload-sizes-mb` and `--download-sizes-mb`):
#   - Uploads:   16, 32, 64, 96, 128, 160, 200 MiB (random bytes, VM sha256 checked, stops at first failure)
#   - Downloads: 256, 512, 768, 1024, 1536, 2048 MiB (VM writes random bytes, rig downloads via single
#                `colab download` and checks sha256, stops at first failure)
# Records pass/fail, HTTP status, token-scrubbed CLI error text, sha256s, and elapsed seconds per
# transfer to `<out-dir>/probe_upload_limit.json`, deleting temporary files on both VM and rig after
# each step, and always stops its session on exit.
set -euo pipefail

PINNED_LAUNCH_GUARDS_SHA="e660f9f72c53ad00d662911ec9620c0ba3f38a85cd9d0ae1e4ab86b6684223a8"
PINNED_COLAB_WINDOW_SHA="c90f0803c4a00d78ea294588b1a7eca91e575b6c8a1aef3c5455caecb57d0ca7"
PINNED_SELF_SHA="5adc24a55d929eb46ce862fa65ae12fbb9979c68802e7cfb32a04776be549c13"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_SH="${SCRIPT_DIR}/probe_upload_limit.sh"
# shellcheck source=scripts/colab/colab_window.sh
source "${SCRIPT_DIR}/colab_window.sh"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-probe-upload-limit-$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR=""
CAP="${CAP:-0.20}"
WALL_S="${WALL_S:-1800}"
GRACE_S="${GRACE_S:-60}"
MARGIN="${MARGIN:-0.01}"
MIN_RUNTIME_S=""
UPLOAD_SIZES_MB="16,32,64,96,128,160,200"
DOWNLOAD_SIZES_MB="256,512,768,1024,1536,2048"
UPLOAD_TIMEOUT_S_ARG=""
UPLOAD_REASSEMBLE_TIMEOUT_S_ARG=""
UPLOAD_REASSEMBLE_MB_S_ARG=""
DOWNLOAD_TIMEOUT_S_ARG=""
DRY_RUN=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --card) CARD="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --session) SESSION="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --out-dir) OUT_DIR="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --cap) CAP="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --wall-s) WALL_S="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --grace-s) GRACE_S="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --margin) MARGIN="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --min-runtime-s) MIN_RUNTIME_S="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-sizes-mb) UPLOAD_SIZES_MB="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-sizes-mb) DOWNLOAD_SIZES_MB="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-timeout-s) UPLOAD_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-reassemble-timeout-s) UPLOAD_REASSEMBLE_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-reassemble-mb-s) UPLOAD_REASSEMBLE_MB_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-timeout-s) DOWNLOAD_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --dry) DRY_RUN=1; shift ;;
    *)
      echo "REFUSED: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if ! colab_card_is_cpu "${CARD}"; then
  echo "REFUSED: PROBE_CPU_ONLY: probe_upload_limit.sh runs only on CPU-high-mem or CPU (got --card '${CARD}')" >&2
  exit 2
fi

# Large download sweeps (up to 2048 MiB) default to a 600 s per-step download bound unless configured.
if [ -z "${DOWNLOAD_TIMEOUT_S_ARG}" ] && [ -z "${COLAB_CALLER_DOWNLOAD_TIMEOUT_S:-}" ]; then
  colab_configure_download_timeout "600" "default" || exit 2
else
  colab_configure_download_timeout "${DOWNLOAD_TIMEOUT_S_ARG}" || exit 2
fi
if [ -z "${UPLOAD_TIMEOUT_S_ARG}" ] && [ -z "${COLAB_CALLER_UPLOAD_TIMEOUT_S:-}" ]; then
  colab_configure_upload_timeout "300" "default" || exit 2
else
  colab_configure_upload_timeout "${UPLOAD_TIMEOUT_S_ARG}" || exit 2
fi
colab_configure_upload_reassemble_timeout "${UPLOAD_REASSEMBLE_TIMEOUT_S_ARG}" "${UPLOAD_REASSEMBLE_MB_S_ARG}" || exit 2

PY_BIN="$(colab_resolve_python)"
GUARDS_PY="${SCRIPT_DIR}/launch_guards.py"

PARSED_SIZES=""
if ! PARSED_SIZES="$("${PY_BIN}" - "${UPLOAD_SIZES_MB}" "${DOWNLOAD_SIZES_MB}" << 'PYEOF'
import json
import sys


def parse_list(raw: str, label: str) -> list[dict]:
    tokens = [t.strip() for t in raw.replace(" ", ",").split(",") if t.strip()]
    if not tokens:
        sys.stderr.write(f"REFUSED: PROBE_SIZES_INVALID: {label} must name at least one positive MiB size\n")
        raise SystemExit(2)
    out = []
    for tok in tokens:
        try:
            val = float(tok)
        except ValueError:
            sys.stderr.write(f"REFUSED: PROBE_SIZES_INVALID: {label} entry {tok!r} is not a number\n")
            raise SystemExit(2)
        n_bytes = int(round(val * 1024 * 1024))
        if val <= 0 or n_bytes <= 0:
            sys.stderr.write(f"REFUSED: PROBE_SIZES_INVALID: {label} entry {tok!r} must be > 0\n")
            raise SystemExit(2)
        mb_val: int | float = int(val) if val.is_integer() else round(val, 6)
        out.append({"size_mb": mb_val, "bytes": n_bytes})
    return out


up = parse_list(sys.argv[1], "--upload-sizes-mb")
dl = parse_list(sys.argv[2], "--download-sizes-mb")
print(json.dumps({"uploads": up, "downloads": dl}))
PYEOF
)"; then
  exit 2
fi

if [ "${DRY_RUN}" = "1" ]; then
  DRY_TEST_MODE=0
  if colab_fake_test_mode_active; then
    DRY_TEST_MODE=1
  fi
  colab_apply_test_cleanup_overrides "${DRY_TEST_MODE}"
  colab_dry_cap_budget "${PY_BIN}" "${GUARDS_PY}" "probe" "${CARD}" "${CAP}" "${MARGIN}" "" "${RATE_CCU_PER_HOUR:-0.26}" "${MIN_RUNTIME_S}"
  exit $?
fi

if [ -z "${OUT_DIR}" ]; then
  echo "REFUSED: OUT_DIR_REQUIRED: pass --out-dir <dir> on a persistent disk" >&2
  exit 2
fi

colab_guard_fake_cli_if_test
TEST_MODE=0
if colab_fake_test_mode_active; then
  TEST_MODE=1
fi

colab_refuse_volatile_out_dir "${OUT_DIR}" "${TEST_MODE}"
colab_refuse_nonempty_out_dir "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

WINDOW_SH="${SCRIPT_DIR}/colab_window.sh"
PIN_OVERRIDE_VARS=(
  EXPECTED_LAUNCH_GUARDS_SHA
  EXPECTED_COLAB_WINDOW_SHA
  EXPECTED_PROBE_UPLOAD_LIMIT_SHA
  SDLAB_TEST_KILL_GRACE_S
  SDLAB_TEST_DOWNLOAD_TIMEOUT_S
  SDLAB_TEST_UPLOAD_TIMEOUT_S
  SDLAB_TEST_UPLOAD_REASSEMBLE_TIMEOUT_S
  SDLAB_TEST_UPLOAD_REASSEMBLE_MB_S
  SDLAB_TEST_UPLOAD_CHUNK_BYTES
  SDLAB_TEST_DOWNLOAD_CHUNK_BYTES
  SDLAB_TEST_STOP_TIMEOUT_S
  SDLAB_TEST_SESSIONS_TIMEOUT_S
  SDLAB_TEST_OPEN_LOCK_TIMEOUT_S
  SDLAB_TEST_NEW_TIMEOUT_S
  SDLAB_TEST_WALL_ESCALATE_S
)
colab_refuse_live_pin_overrides "${OUT_DIR}" "${TEST_MODE}" "${PIN_OVERRIDE_VARS[@]}"
colab_apply_test_cleanup_overrides "${TEST_MODE}"

EXP_GUARDS_SHA="${PINNED_LAUNCH_GUARDS_SHA}"
EXP_WINDOW_SHA="${PINNED_COLAB_WINDOW_SHA}"
EXP_SELF_SHA="${PINNED_SELF_SHA}"
if [ "${TEST_MODE}" = "1" ]; then
  EXP_GUARDS_SHA="${EXPECTED_LAUNCH_GUARDS_SHA:-${EXP_GUARDS_SHA}}"
  EXP_WINDOW_SHA="${EXPECTED_COLAB_WINDOW_SHA:-${EXP_WINDOW_SHA}}"
  EXP_SELF_SHA="${EXPECTED_PROBE_UPLOAD_LIMIT_SHA:-${EXP_SELF_SHA}}"
fi

SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
  "${GUARDS_PY}=${EXP_GUARDS_SHA}" \
  "${WINDOW_SH}=${EXP_WINDOW_SHA}" \
  "${SELF_SH}=${EXP_SELF_SHA}")"

OPENED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$(date -u +%s)"
SESSION_OPENED=0
WALL_WATCHER_PID=""
EXEC_PID=""
PROBE_WORK="${OUT_DIR}/.probe_work"
RECEIPT_JSON="${OUT_DIR}/probe_upload_limit.json"

"${PY_BIN}" - "${RECEIPT_JSON}" "${SESSION}" "${CARD}" "${OPENED_AT}" "${PARSED_SIZES}" << 'PYEOF'
import json
import sys
from pathlib import Path

out_p = Path(sys.argv[1])
spec = json.loads(sys.argv[5])
payload = {
    "session": sys.argv[2],
    "card": sys.argv[3],
    "opened_at": sys.argv[4],
    "closed_at": None,
    "status": "in_progress",
    "requested_upload_sizes_mb": [x["size_mb"] for x in spec["uploads"]],
    "requested_download_sizes_mb": [x["size_mb"] for x in spec["downloads"]],
    "uploads": [],
    "downloads": [],
    "summary": None,
}
out_p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
PYEOF

probe_finalize_receipt() {
  local exit_rc="$1"
  local closed_ts="$2"
  "${PY_BIN}" - "${RECEIPT_JSON}" "${exit_rc}" "${closed_ts}" << 'PYEOF' || true
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(0)
rc = int(sys.argv[2])
closed_at = sys.argv[3]
doc = json.loads(p.read_text(encoding="utf-8"))
ups = doc.get("uploads", [])
dls = doc.get("downloads", [])
passed_ups = [r["size_mb"] for r in ups if r.get("passed")]
failed_ups = [r["size_mb"] for r in ups if not r.get("passed")]
passed_dls = [r["size_mb"] for r in dls if r.get("passed")]
failed_dls = [r["size_mb"] for r in dls if not r.get("passed")]
doc["closed_at"] = closed_at
doc["status"] = "ok" if rc == 0 else "failed"
doc["exit_code"] = rc
doc["summary"] = {
    "max_passed_upload_mb": max(passed_ups) if passed_ups else None,
    "first_failed_upload_mb": failed_ups[0] if failed_ups else None,
    "upload_stopped_at_first_failure": bool(failed_ups),
    "max_passed_download_mb": max(passed_dls) if passed_dls else None,
    "first_failed_download_mb": failed_dls[0] if failed_dls else None,
    "download_stopped_at_first_failure": bool(failed_dls),
}
p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
PYEOF
}

cleanup_on_exit() {
  local rc=$?
  colab_enter_cleanup_trap "${OUT_DIR}"
  rm -rf "${PROBE_WORK}" || true
  if [ -f "${OUT_DIR}/watcher_escalated.txt" ]; then
    sleep 3600
    exit 137
  fi
  printf 'trap\n' > "${OUT_DIR}/stop_path.txt"
  printf '1\n' > "${OUT_DIR}/stop_reached.txt"
  if [ "${SESSION_OPENED}" -eq 1 ] && { [ -f "${OUT_DIR}/session_open_started.txt" ] || [ -f "${OUT_DIR}/session_opened.txt" ]; }; then
    colab_stop_and_log_closing "${PY_BIN}" "${SESSION}" "${OUT_DIR}"
  fi
  if [ -f "${OUT_DIR}/watcher_escalated.txt" ]; then
    sleep 3600
    exit 137
  fi
  if [ -f "${OUT_DIR}/wall_trip_epoch.txt" ] && [ ! -f "${OUT_DIR}/watcher_escalated.txt" ] && [ ! -f "${OUT_DIR}/watcher_wait.txt" ]; then
    printf 'cleanup_seen\n' > "${OUT_DIR}/watcher_wait.txt"
  fi
  colab_release_wall_watcher "${OUT_DIR}" "${SESSION}" "${WALL_WATCHER_PID}"
  local closed_at
  closed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  probe_finalize_receipt "${rc}" "${closed_at}"
  colab_write_window_and_outcome \
    "${PY_BIN}" "${OUT_DIR}" "probe" "${SESSION}" "${CARD}" \
    "${CAP}" "${WALL_S}" "${GRACE_S}" "${MARGIN}" \
    "${OPENED_AT}" "${closed_at}" "${rc}" "${SHAS_JSON}" || true
  colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" || true
  exit "${rc}"
}
trap cleanup_on_exit EXIT
trap 'exit 143' TERM INT

colab_gpu_rate_gate_arm "${OUT_DIR}" "${CARD}" "" "${TEST_MODE}"
colab_shape_gate_arm "${OUT_DIR}" "${CARD}" ""
colab_cap_budget_gate "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" "probe" "${CARD}" "${CAP}" "${MARGIN}" "" "${RATE_CCU_PER_HOUR:-0.26}" "${MIN_RUNTIME_S}"
colab_check_cap_and_ram "${PY_BIN}" "${GUARDS_PY}" "stub" "0" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}"

WALL_INT="${WALL_S%.*}"
GRACE_INT="${GRACE_S%.*}"
WALL_LIMIT_S="$(( WALL_INT > GRACE_INT ? WALL_INT - GRACE_INT : 1 ))"
MAIN_PID="$$"
colab_run_wall_watcher \
  "${MAIN_PID}" "${WALL_LIMIT_S}" "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" \
  "probe" "${SESSION}" "${CARD}" "${CAP}" "${WALL_S}" "${GRACE_S}" "${MARGIN}" \
  "${OPENED_AT}" "${SHAS_JSON}" &
WALL_WATCHER_PID="$!"

SESSION_OPENED=1
colab_open_session_locked "${SESSION}" "${CARD}" "${OUT_DIR}"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
colab_check_pre_exec_cap "${OUT_DIR}"

mkdir -p "${PROBE_WORK}"
VM_HELPER_PY="${PROBE_WORK}/probe_vm_helper.py"
cat > "${VM_HELPER_PY}" << 'PYEOF'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["SDLAB_CONTENT"])
op = os.environ["SDLAB_PROBE_OP"]
target = root / os.environ["SDLAB_PROBE_NAME"]

if op == "verify_and_unlink":
    if not target.is_file():
        print("SDLAB_PROBE_VM_JSON " + json.dumps({"exists": False, "bytes": 0, "sha256": None}), flush=True)
    else:
        h = hashlib.sha256()
        sz = 0
        with target.open("rb") as fh:
            for blk in iter(lambda: fh.read(1 << 20), b""):
                sz += len(blk)
                h.update(blk)
        target.unlink(missing_ok=True)
        print("SDLAB_PROBE_VM_JSON " + json.dumps({"exists": True, "bytes": sz, "sha256": h.hexdigest()}), flush=True)
elif op == "write_random":
    want = int(os.environ["SDLAB_PROBE_BYTES"])
    h = hashlib.sha256()
    rem = want
    with target.open("wb") as fh:
        while rem > 0:
            step = min(4 << 20, rem)
            buf = os.urandom(step)
            fh.write(buf)
            h.update(buf)
            rem -= len(buf)
    print("SDLAB_PROBE_VM_JSON " + json.dumps({"ok": True, "bytes": want, "sha256": h.hexdigest()}), flush=True)
elif op == "unlink":
    target.unlink(missing_ok=True)
    print("SDLAB_PROBE_VM_JSON " + json.dumps({"ok": True}), flush=True)
PYEOF

# --- Direction 1: single-PUT `colab upload` sweep -------------------------------------------------
mapfile -t UP_ROWS < <(
  "${PY_BIN}" -c 'import json, sys; [print(x["size_mb"], x["bytes"], sep="\t") for x in json.loads(sys.argv[1])["uploads"]]' "${PARSED_SIZES}" | tr -d '\r'
)

for row in "${UP_ROWS[@]}"; do
  [ -z "${row}" ] && continue
  IFS=$'\t' read -r sz_mb sz_bytes <<< "${row}"
  colab_check_pre_exec_cap "${OUT_DIR}" "probe_upload_${sz_mb}mb"

  local_probe="${PROBE_WORK}/probe_up.bin"
  rig_sha="$("${PY_BIN}" - "${local_probe}" "${sz_bytes}" << 'PYEOF' | tr -d '\r'
import hashlib, os, sys
from pathlib import Path

p = Path(sys.argv[1])
rem = int(sys.argv[2])
h = hashlib.sha256()
with p.open("wb") as fh:
    while rem > 0:
        step = min(4 << 20, rem)
        buf = os.urandom(step)
        fh.write(buf)
        h.update(buf)
        rem -= len(buf)
print(h.hexdigest())
PYEOF
  )"

  t0="$("${PY_BIN}" -c 'import time; print(f"{time.monotonic():.6f}")' | tr -d '\r')"
  up_rc=0
  up_out="$(colab_upload_raw_bounded "${SESSION}" "${local_probe}" "/content/probe_up.bin" "${COLAB_UPLOAD_TIMEOUT_S}" "${COLAB_KILL_GRACE_S}")" || up_rc=$?
  t1="$("${PY_BIN}" -c 'import time; print(f"{time.monotonic():.6f}")' | tr -d '\r')"
  rm -f "${local_probe}"
  printf '%s\n' "${up_out}" >> "${OUT_DIR}/colab.log"
  http_st="$(_colab_http_status "${up_out}")"

  vm_sha=""
  vm_bytes="0"
  if [ "${up_rc}" -eq 0 ] && grep -Fq "[colab] Uploaded '" <<< "${up_out}"; then
    v_rc=0
    v_out="$(colab_run_bounded 120 "${COLAB_KILL_GRACE_S}" colab exec -s "${SESSION}" -f "${VM_HELPER_PY}" \
      --timeout 120 --env "SDLAB_CONTENT=/content" --env "SDLAB_PROBE_OP=verify_and_unlink" \
      --env "SDLAB_PROBE_NAME=probe_up.bin" 2>&1)" || v_rc=$?
    printf '%s\n' "${v_out}" >> "${OUT_DIR}/colab.log"
    IFS=$'\t' read -r vm_bytes vm_sha < <(
      "${PY_BIN}" -c '
import json, sys
raw = sys.stdin.read()
rec = {}
for ln in reversed(raw.splitlines()):
    if ln.strip().startswith("SDLAB_PROBE_VM_JSON "):
        rec = json.loads(ln.strip()[len("SDLAB_PROBE_VM_JSON "):])
        break
nb = int(rec.get("bytes") or 0); sh = rec.get("sha256") or ""
print(f"{nb}\t{sh}")
' <<< "${v_out}" | tr -d '\r'
    )
  else
    colab_run_bounded 30 "${COLAB_KILL_GRACE_S}" colab exec -s "${SESSION}" -f "${VM_HELPER_PY}" \
      --timeout 30 --env "SDLAB_CONTENT=/content" --env "SDLAB_PROBE_OP=unlink" \
      --env "SDLAB_PROBE_NAME=probe_up.bin" >> "${OUT_DIR}/colab.log" 2>&1 || true
  fi

  step_passed="$("${PY_BIN}" - "${RECEIPT_JSON}" "${GUARDS_PY}" "${sz_mb}" "${sz_bytes}" "${rig_sha}" "${vm_sha}" "${vm_bytes}" "${up_rc}" "${http_st}" "${t0}" "${t1}" "${up_out}" << 'PYEOF' | tr -d '\r'
import json
import sys
from pathlib import Path

receipt_p = Path(sys.argv[1])
guards_py = Path(sys.argv[2])
sys.path.insert(0, str(guards_py.parent))
import launch_guards as lg

raw_mb = float(sys.argv[3])
size_mb: int | float = int(raw_mb) if raw_mb.is_integer() else round(raw_mb, 6)
size_bytes = int(sys.argv[4])
rig_sha = sys.argv[5]
vm_sha = sys.argv[6] or None
vm_bytes = int(sys.argv[7])
rc = int(sys.argv[8])
http_status = sys.argv[9]
elapsed_s = round(max(0.0, float(sys.argv[11]) - float(sys.argv[10])), 4)
cli_text = lg.scrub_colab_tokens(sys.argv[12]).strip()

sha_match = bool(rc == 0 and vm_sha is not None and vm_sha == rig_sha and vm_bytes == size_bytes)
passed = bool(rc == 0 and "[colab] Uploaded '" in sys.argv[12] and sha_match)
error_text = None
if not passed:
    error_text = cli_text if cli_text else f"upload failed rc={rc} vm_bytes={vm_bytes}"
    if rc == 0 and "[colab] Uploaded '" in sys.argv[12] and not sha_match:
        error_text = f"VM sha256/bytes mismatch: vm={vm_sha}:{vm_bytes} expected={rig_sha}:{size_bytes}"

rec = {
    "size_mb": size_mb,
    "bytes": size_bytes,
    "passed": passed,
    "rc": rc,
    "http_status": None if http_status == "none" else int(http_status),
    "error_text": error_text,
    "seconds": elapsed_s,
    "rig_sha256": rig_sha,
    "vm_sha256": vm_sha,
    "sha256_match": sha_match,
}
doc = json.loads(receipt_p.read_text(encoding="utf-8"))
doc["uploads"].append(rec)
receipt_p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
print("1" if passed else "0")
PYEOF
  )"

  if [ "${step_passed}" != "1" ]; then
    break
  fi
done

# --- Direction 2: single-GET `colab download` sweep -----------------------------------------------
mapfile -t DL_ROWS < <(
  "${PY_BIN}" -c 'import json, sys; [print(x["size_mb"], x["bytes"], sep="\t") for x in json.loads(sys.argv[1])["downloads"]]' "${PARSED_SIZES}" | tr -d '\r'
)

for row in "${DL_ROWS[@]}"; do
  [ -z "${row}" ] && continue
  IFS=$'\t' read -r sz_mb sz_bytes <<< "${row}"
  colab_check_pre_exec_cap "${OUT_DIR}" "probe_download_${sz_mb}mb"

  w_rc=0
  w_out="$(colab_run_bounded "${COLAB_DOWNLOAD_TIMEOUT_S}" "${COLAB_KILL_GRACE_S}" colab exec -s "${SESSION}" -f "${VM_HELPER_PY}" \
    --timeout "${COLAB_DOWNLOAD_TIMEOUT_S}" --env "SDLAB_CONTENT=/content" --env "SDLAB_PROBE_OP=write_random" \
    --env "SDLAB_PROBE_NAME=probe_dl.bin" --env "SDLAB_PROBE_BYTES=${sz_bytes}" 2>&1)" || w_rc=$?
  printf '%s\n' "${w_out}" >> "${OUT_DIR}/colab.log"
  vm_sha="$("${PY_BIN}" -c '
import json, sys
raw = sys.stdin.read()
sha = ""
for ln in reversed(raw.splitlines()):
    if ln.strip().startswith("SDLAB_PROBE_VM_JSON "):
        rec = json.loads(ln.strip()[len("SDLAB_PROBE_VM_JSON "):])
        if rec.get("ok") and rec.get("sha256"):
            sha = str(rec["sha256"])
        break
print(sha)
' <<< "${w_out}" | tr -d '\r')"

  local_dl="${PROBE_WORK}/probe_dl.bin"
  rm -f "${local_dl}"
  dl_rc=0
  dl_out=""
  t0="$("${PY_BIN}" -c 'import time; print(f"{time.monotonic():.6f}")' | tr -d '\r')"
  if [ "${w_rc}" -eq 0 ] && [ -n "${vm_sha}" ]; then
    dl_out="$(colab_download_raw_bounded "${SESSION}" "/content/probe_dl.bin" "${local_dl}" "${COLAB_DOWNLOAD_TIMEOUT_S}" "${COLAB_KILL_GRACE_S}")" || dl_rc=$?
  else
    dl_rc=1
    dl_out="VM failed to write probe_dl.bin (exec rc=${w_rc})"
  fi
  t1="$("${PY_BIN}" -c 'import time; print(f"{time.monotonic():.6f}")' | tr -d '\r')"
  printf '%s\n' "${dl_out}" >> "${OUT_DIR}/colab.log"
  http_st="$(_colab_http_status "${dl_out}")"

  # Always clean up the VM file immediately before checking next size.
  colab_run_bounded 30 "${COLAB_KILL_GRACE_S}" colab exec -s "${SESSION}" -f "${VM_HELPER_PY}" \
    --timeout 30 --env "SDLAB_CONTENT=/content" --env "SDLAB_PROBE_OP=unlink" \
    --env "SDLAB_PROBE_NAME=probe_dl.bin" >> "${OUT_DIR}/colab.log" 2>&1 || true

  rig_sha=""
  rig_bytes="0"
  if [ -f "${local_dl}" ]; then
    IFS=$'\t' read -r rig_bytes rig_sha < <(
      "${PY_BIN}" -c '
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
h = hashlib.sha256()
sz = 0
with p.open("rb") as fh:
    for blk in iter(lambda: fh.read(1 << 20), b""):
        sz += len(blk)
        h.update(blk)
print(f"{sz}\t{h.hexdigest()}")
' "${local_dl}" | tr -d '\r'
    )
    rm -f "${local_dl}"
  fi

  step_passed="$("${PY_BIN}" - "${RECEIPT_JSON}" "${GUARDS_PY}" "${sz_mb}" "${sz_bytes}" "${vm_sha}" "${rig_sha}" "${rig_bytes}" "${dl_rc}" "${http_st}" "${t0}" "${t1}" "${dl_out}" << 'PYEOF' | tr -d '\r'
import json
import sys
from pathlib import Path

receipt_p = Path(sys.argv[1])
guards_py = Path(sys.argv[2])
sys.path.insert(0, str(guards_py.parent))
import launch_guards as lg

raw_mb = float(sys.argv[3])
size_mb: int | float = int(raw_mb) if raw_mb.is_integer() else round(raw_mb, 6)
size_bytes = int(sys.argv[4])
vm_sha = sys.argv[5] or None
rig_sha = sys.argv[6] or None
rig_bytes = int(sys.argv[7])
rc = int(sys.argv[8])
http_status = sys.argv[9]
elapsed_s = round(max(0.0, float(sys.argv[11]) - float(sys.argv[10])), 4)
cli_text = lg.scrub_colab_tokens(sys.argv[12]).strip()

sha_match = bool(rc == 0 and vm_sha is not None and rig_sha == vm_sha and rig_bytes == size_bytes)
passed = bool(rc == 0 and "[colab] Downloaded '" in sys.argv[12] and sha_match)
error_text = None
if not passed:
    error_text = cli_text if cli_text else f"download failed rc={rc} rig_bytes={rig_bytes}"
    if rc == 0 and "[colab] Downloaded '" in sys.argv[12] and not sha_match:
        error_text = f"rig sha256/bytes mismatch: rig={rig_sha}:{rig_bytes} expected={vm_sha}:{size_bytes}"

rec = {
    "size_mb": size_mb,
    "bytes": size_bytes,
    "passed": passed,
    "rc": rc,
    "http_status": None if http_status == "none" else int(http_status),
    "error_text": error_text,
    "seconds": elapsed_s,
    "vm_sha256": vm_sha,
    "rig_sha256": rig_sha,
    "sha256_match": sha_match,
}
doc = json.loads(receipt_p.read_text(encoding="utf-8"))
doc["downloads"].append(rec)
receipt_p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
print("1" if passed else "0")
PYEOF
  )"

  if [ "${step_passed}" != "1" ]; then
    break
  fi
done

colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
