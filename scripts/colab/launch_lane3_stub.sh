#!/usr/bin/env bash
# Stub launch kit for Lane 3 (train) Colab CPU high-mem window (Part C, PR #47).
# Checks input sha256s before opening, holds /tmp/colab-window-open.lock, opens CPU --high-mem,
# runs CPython 3.15.1 uv venv + ostris/ai-toolkit install with ai-toolkit-override-py315.txt
# (proving sentencepiece==0.2.1 and wheels) + 1 CPU training step on a tiny synthetic package
# with checkpoint written, enforces launch_guards.py (wall, cap, vitals/DEAD HARNESS, host-RAM),
# downloads result tar, scrubs tokens from all kept logs, writes window.json and outcome.draft.json,
# and stops its own session in an EXIT trap on every exit path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/colab/colab_window.sh
source "${SCRIPT_DIR}/colab_window.sh"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-lane3-stub-$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR=""
CAP="${CAP:-0.05}"
WALL_S="${WALL_S:-900}"
GRACE_S="${GRACE_S:-60}"
MARGIN="${MARGIN:-0.01}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --card) CARD="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --cap) CAP="$2"; shift 2 ;;
    --wall-s) WALL_S="$2"; shift 2 ;;
    --grace-s) GRACE_S="$2"; shift 2 ;;
    --margin) MARGIN="$2"; shift 2 ;;
    *)
      echo "REFUSED: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "${OUT_DIR}" ]; then
  OUT_DIR="/tmp/${SESSION}"
fi
mkdir -p "${OUT_DIR}"

PY_BIN="$(colab_resolve_python)"
GUARDS_PY="${SCRIPT_DIR}/launch_guards.py"
OVERRIDE_TXT="${SCRIPT_DIR}/ai-toolkit-override-py315.txt"
WINDOW_SH="${SCRIPT_DIR}/colab_window.sh"

colab_guard_fake_cli_if_test

actual_sha() {
  sha256sum "$1" | awk '{print $1}'
}

EXP_OVERRIDE_SHA="${EXPECTED_OVERRIDE_SHA:-$(actual_sha "${OVERRIDE_TXT}")}"
EXP_GUARDS_SHA="${EXPECTED_LAUNCH_GUARDS_SHA:-$(actual_sha "${GUARDS_PY}")}"
EXP_WINDOW_SHA="${EXPECTED_COLAB_WINDOW_SHA:-$(actual_sha "${WINDOW_SH}")}"

SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
  "${OVERRIDE_TXT}=${EXP_OVERRIDE_SHA}" \
  "${GUARDS_PY}=${EXP_GUARDS_SHA}" \
  "${WINDOW_SH}=${EXP_WINDOW_SHA}")"

OPENED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$(date -u +%s)"
SESSION_OPENED=0
WALL_WATCHER_PID=""
EXEC_PID=""

cleanup_on_exit() {
  local rc=$?
  trap - EXIT TERM INT
  if [ -n "${EXEC_PID}" ]; then
    pkill -P "${EXEC_PID}" 2>/dev/null || true
    kill -9 "${EXEC_PID}" 2>/dev/null || true
  fi
  if [ -n "${WALL_WATCHER_PID}" ]; then
    pkill -P "${WALL_WATCHER_PID}" 2>/dev/null || true
    kill -9 "${WALL_WATCHER_PID}" 2>/dev/null || true
  fi
  if [ "${SESSION_OPENED}" -eq 1 ]; then
    colab stop -s "${SESSION}" </dev/null >> "${OUT_DIR}/colab.log" 2>&1 || true
  fi
  local closed_at
  closed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  colab_write_window_and_outcome \
    "${PY_BIN}" "${OUT_DIR}" "train" "${SESSION}" "${CARD}" \
    "${CAP}" "${WALL_S}" "${GRACE_S}" "${MARGIN}" \
    "${OPENED_AT}" "${closed_at}" "${rc}" "${SHAS_JSON}" || true
  colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" || true
  exit "${rc}"
}
trap cleanup_on_exit EXIT
trap 'exit 143' TERM INT

# Pre-open cap and host-RAM check via launch_guards.py
colab_check_cap_and_ram "${PY_BIN}" "${GUARDS_PY}" "stub" "0" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}"

# Independent wall watcher (cannot be blocked by a child timeout)
WALL_INT="${WALL_S%.*}"
GRACE_INT="${GRACE_S%.*}"
WALL_LIMIT_S="$(( WALL_INT > GRACE_INT ? WALL_INT - GRACE_INT : 1 ))"
MAIN_PID="$$"
(
  exec >/dev/null 2>&1 </dev/null
  sleep "${WALL_LIMIT_S}"
  echo "WALL_GUARD_TRIPPED after ${WALL_LIMIT_S}s" >> "${OUT_DIR}/guards.log"
  kill -TERM "${MAIN_PID}" 2>/dev/null || true
) &
WALL_WATCHER_PID="$!"

# Hold /tmp/colab-window-open.lock while opening with colab new (--high-mem default)
SESSION_OPENED=1
colab_open_session_locked "${SESSION}" "${CARD}" "${OUT_DIR}"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"

REMOTE_RUNNER="${OUT_DIR}/remote_lane3_stub.sh"
cat > "${REMOTE_RUNNER}" << 'REMOTEEOF'
#!/usr/bin/env bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=""
mkdir -p /content/lane3_out

(
  while true; do
    echo "=== VITALS $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    if [ -f /sys/fs/cgroup/memory.events ]; then
      sed 's/^/CGROUP_MEM: /' /sys/fs/cgroup/memory.events || true
    fi
    head -n 3 /proc/meminfo | sed 's/^/MEM: /' || true
    echo "PROC:"
    ps -ef | grep -E "ai-toolkit|run\.py" | grep -v grep || true
    echo 'HARNESS: {"phase": "run"}'
    sleep 15
  done
) >> /content/lane3_out/vitals.log 2>&1 &
VITALS_PID="$!"
trap 'kill "${VITALS_PID}" 2>/dev/null || true' EXIT

sha256sum /content/ai-toolkit-override-py315.txt > /content/lane3_out/override.sha256

pip install --quiet "uv==0.13.5"
uv python install 3.15.1
uv venv /content/venv-lane3 --python 3.15.1 --seed
source /content/venv-lane3/bin/activate

if [ ! -d /content/ai-toolkit ]; then
  git clone --depth 1 https://github.com/ostris/ai-toolkit.git /content/ai-toolkit
fi
uv pip install -r /content/ai-toolkit/requirements.txt \
  --override /content/ai-toolkit-override-py315.txt \
  > /content/lane3_out/wheels.log 2>&1

python -c "import sentencepiece as spm; print('SENTENCEPIECE_OK', spm.__version__)" \
  | tee /content/lane3_out/sentencepiece.txt

python - << 'SYNTHEOF'
import hashlib
import json
import struct
import zlib
from pathlib import Path

pkg = Path("/content/lane3_out/synth_pkg")
pkg.mkdir(parents=True, exist_ok=True)

def make_png(seed_b: int) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_d = struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_d + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_d) & 0xFFFFFFFF)
    row = bytes([0] + [seed_b & 0xFF, (seed_b * 3) & 0xFF, (seed_b * 7) & 0xFF] * 64)
    idat_d = zlib.compress(row * 64)
    idat = struct.pack(">I", len(idat_d)) + b"IDAT" + idat_d + struct.pack(">I", zlib.crc32(b"IDAT" + idat_d) & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    return sig + ihdr + idat + iend

items = []
for idx in (1, 2):
    img_b = make_png(idx * 17)
    img_p = pkg / f"sample_{idx:02d}.png"
    txt_p = pkg / f"sample_{idx:02d}.txt"
    img_p.write_bytes(img_b)
    txt_p.write_text(f"portlight ship synthetic fixture {idx}\n", encoding="utf-8")
    items.append({"image": img_p.name, "sha256": hashlib.sha256(img_b).hexdigest()})

(pkg / "dataset_manifest.json").write_text(json.dumps({"seed": 42, "items": items}, indent=2) + "\n", encoding="utf-8")
SYNTHEOF

python /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml \
  > /content/lane3_out/train.log 2>&1

tar -czf /content/lane3_stub_bundle.tar.gz -C /content/lane3_out .
REMOTEEOF

colab upload -s "${SESSION}" "${OVERRIDE_TXT}" /content/ai-toolkit-override-py315.txt </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab upload -s "${SESSION}" "${GUARDS_PY}" /content/launch_guards.py </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab upload -s "${SESSION}" "${REMOTE_RUNNER}" /content/remote_lane3_stub.sh </dev/null >> "${OUT_DIR}/colab.log" 2>&1

colab exec -s "${SESSION}" "bash /content/remote_lane3_stub.sh" </dev/null > "${OUT_DIR}/vitals.log" 2>&1 &
EXEC_PID="$!"
wait "${EXEC_PID}"
EXEC_RC=$?
EXEC_PID=""

colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"

if [ "${EXEC_RC}" -ne 0 ]; then
  exit "${EXEC_RC}"
fi

# Evaluate vitals.log and DEAD HARNESS watcher via launch_guards.py
"${PY_BIN}" "${GUARDS_PY}" --vitals-file "${OUT_DIR}/vitals.log" --idle-seconds 0 --stall-s 300 </dev/null >> "${OUT_DIR}/guards.log"

NOW_EPOCH="$(date -u +%s)"
ELAPSED_S="$((NOW_EPOCH - START_EPOCH))"
colab_check_cap_and_ram "${PY_BIN}" "${GUARDS_PY}" "stub" "${ELAPSED_S}" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}"

# Download result tar before EXIT trap stops the session
colab download -s "${SESSION}" /content/lane3_stub_bundle.tar.gz "${OUT_DIR}/lane3_stub_bundle.tar.gz" </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
