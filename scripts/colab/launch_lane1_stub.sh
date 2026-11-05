#!/usr/bin/env bash
# Stub launch kit for Lane 1 (render) Colab CPU high-mem window (Part C, PR #45).
# Checks input sha256s before opening, holds /tmp/colab-window-open.lock, opens CPU --high-mem,
# runs CPython 3.15.1 uv venv + ComfyUI --cpu + 64x64 fixture render + stamp read-back + kill + resume,
# enforces launch_guards.py (wall, cap, vitals/DEAD HARNESS, host-RAM), downloads result tar,
# scrubs tokens from all kept logs, writes window.json and outcome.draft.json, and stops its own
# session in an EXIT trap on every exit path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/colab/colab_window.sh
source "${SCRIPT_DIR}/colab_window.sh"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-lane1-stub-$(date -u +%Y%m%dT%H%M%SZ)"
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
LANE1_PY="${SCRIPT_DIR}/lane1_render.py"
WINDOW_SH="${SCRIPT_DIR}/colab_window.sh"

colab_guard_fake_cli_if_test

actual_sha() {
  sha256sum "$1" | awk '{print $1}'
}

EXP_LANE1_SHA="${EXPECTED_LANE1_RENDER_SHA:-$(actual_sha "${LANE1_PY}")}"
EXP_GUARDS_SHA="${EXPECTED_LAUNCH_GUARDS_SHA:-$(actual_sha "${GUARDS_PY}")}"
EXP_WINDOW_SHA="${EXPECTED_COLAB_WINDOW_SHA:-$(actual_sha "${WINDOW_SH}")}"

SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
  "${LANE1_PY}=${EXP_LANE1_SHA}" \
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
    "${PY_BIN}" "${OUT_DIR}" "render" "${SESSION}" "${CARD}" \
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

REMOTE_RUNNER="${OUT_DIR}/remote_lane1_stub.sh"
cat > "${REMOTE_RUNNER}" << 'REMOTEEOF'
#!/usr/bin/env bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=""
mkdir -p /content/lane1_out

(
  while true; do
    echo "=== VITALS $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    if [ -f /sys/fs/cgroup/memory.events ]; then
      sed 's/^/CGROUP_MEM: /' /sys/fs/cgroup/memory.events || true
    fi
    head -n 3 /proc/meminfo | sed 's/^/MEM: /' || true
    echo "PROC:"
    ps -ef | grep -E "comfy|main\.py|lane1_render\.py" | grep -v grep || true
    echo 'HARNESS: {"phase": "run"}'
    sleep 15
  done
) >> /content/lane1_out/vitals.log 2>&1 &
VITALS_PID="$!"
trap 'kill "${VITALS_PID}" 2>/dev/null || true' EXIT

pip install --quiet "uv==0.13.5"
uv python install 3.15.1
uv venv /content/venv-lane1 --python 3.15.1 --seed
source /content/venv-lane1/bin/activate

if [ ! -d /content/ComfyUI ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /content/ComfyUI
fi
uv pip install -r /content/ComfyUI/requirements.txt

python /content/ComfyUI/main.py --cpu --listen 127.0.0.1 --port 8188 --disable-auto-launch \
  > /content/lane1_out/comfyui.log 2>&1 &
COMFY_PID="$!"

for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

cat > /content/lane1_out/jobs.jsonl << 'JOBSEOF'
{"job_id":"stub_01","run_id":"run_stub_01","template_id":"stub_fixture_64","seed":101,"width":64,"height":64,"canon_sha":"a881cb5ba656e0618080d2269498fda7f36ac93a","entry_id":"ships/brig","entry_sha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111","workflow_sha":"sha256:2222222222222222222222222222222222222222222222222222222222222222"}
{"job_id":"stub_02","run_id":"run_stub_01","template_id":"stub_fixture_64","seed":102,"width":64,"height":64,"canon_sha":"a881cb5ba656e0618080d2269498fda7f36ac93a","entry_id":"ships/brig","entry_sha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111","workflow_sha":"sha256:2222222222222222222222222222222222222222222222222222222222222222"}
JOBSEOF

set +e
python /content/lane1_render.py \
  --cpu --bootstrap \
  --window-json /content/lane1_out/vm_window.json \
  --jobs /content/lane1_out/jobs.jsonl \
  --renders /content/lane1_out/renders.jsonl \
  --out-dir /content/lane1_out/pngs \
  --copy-back-dir /content/lane1_out/copy_back \
  --copy-back-every 1 \
  --kill-after 1
RC1=$?
set -e
if [ "${RC1}" -ne 75 ]; then
  echo "Expected exit 75 on deliberate kill-after=1, got ${RC1}" >&2
  exit 1
fi

SHA_BEFORE="$(sha256sum /content/lane1_out/pngs/stub_01.png | awk '{print $1}')"

python /content/lane1_render.py \
  --cpu \
  --jobs /content/lane1_out/jobs.jsonl \
  --renders /content/lane1_out/renders.jsonl \
  --out-dir /content/lane1_out/pngs \
  --copy-back-dir /content/lane1_out/copy_back \
  --copy-back-every 1

SHA_AFTER="$(sha256sum /content/lane1_out/pngs/stub_01.png | awk '{print $1}')"
SHA_COPY="$(sha256sum /content/lane1_out/copy_back/stub_01.png | awk '{print $1}')"
if [ "${SHA_BEFORE}" != "${SHA_AFTER}" ] || [ "${SHA_BEFORE}" != "${SHA_COPY}" ]; then
  echo "Resume hash mismatch: before=${SHA_BEFORE} after=${SHA_AFTER} copy=${SHA_COPY}" >&2
  exit 1
fi

kill "${COMFY_PID}" 2>/dev/null || true
tar -czf /content/lane1_stub_bundle.tar.gz -C /content/lane1_out .
REMOTEEOF

colab upload -s "${SESSION}" "${LANE1_PY}" /content/lane1_render.py </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab upload -s "${SESSION}" "${GUARDS_PY}" /content/launch_guards.py </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab upload -s "${SESSION}" "${REMOTE_RUNNER}" /content/remote_lane1_stub.sh </dev/null >> "${OUT_DIR}/colab.log" 2>&1

colab exec -s "${SESSION}" "bash /content/remote_lane1_stub.sh" </dev/null > "${OUT_DIR}/vitals.log" 2>&1 &
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
colab download -s "${SESSION}" /content/lane1_stub_bundle.tar.gz "${OUT_DIR}/lane1_stub_bundle.tar.gz" </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
