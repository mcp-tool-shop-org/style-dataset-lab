#!/usr/bin/env bash
# Stub launch kit for Lane 1 (render) Colab CPU high-mem window (Part C, PR #45).
# Checks pinned input sha256s (including itself) and runs preflight_resolve.sh before opening,
# holds /tmp/colab-window-open.lock, opens CPU --high-mem (a GPU card needs --shape), runs CPython 3.14.9 uv venv + wheel-only
# install from hash-locked lane1.lock + pinned ComfyUI --cpu + comfy-headless + 64x64 fixture render +
# stamp read-back + kill + resume, enforces live launch_guards.py (wall, cap, vitals/DEAD HARNESS,
# host-RAM), scrubs VM-side logs before tarring, downloads result tar, merges VM facts/balances/rate/
# downloaded shas into window.json, and stops its own session in an EXIT trap.
set -euo pipefail

PINNED_UV_VERSION="0.13.5"
# sha256 of uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl on PyPI (the Colab VM platform)
PINNED_UV_WHEEL_SHA256="fa8d26e08e34c29c0c4e820cf3181757086d547240b4f4d31ff1d8bd810ca946"
PINNED_PYTHON_VERSION="3.14.9"
# python-build-standalone release that uv 0.13.5 installs for PINNED_PYTHON_VERSION. uv embeds the
# archive URL and sha256 (crates/uv-python-managed/download-metadata.json at 0.13.5) and checks the
# sha256 on download (crates/uv-python-managed/src/downloads.rs:770-777), so pinning uv by hash pins
# the interpreter; the remote script refuses PYTHON_BUILD_MISMATCH if the install's BUILD differs.
PINNED_PYTHON_BUILD="20261021"
PINNED_PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu130"
PINNED_COMFYUI_REPO="https://github.com/comfyanonymous/ComfyUI.git"
PINNED_COMFYUI_COMMIT="158419f3a0017c2ce123484b14b6c527716d6ec8"
PINNED_COMFY_HEADLESS_SPEC="comfy-headless==3.1.0"
PINNED_LOCK_SHA="93904e77dc9ef4ce983a875809b3e399dfe206754c20b48b2a2c14e75278738c"
PINNED_LANE1_RENDER_SHA="45a2cf892cda07c8aa312e2995ef9d5f9fdd575b6e70a737d4137ed0eecb52b7"
PINNED_INSTALL_CLASSIFIER_SHA="ccccf077795148c14a7aa430e3575db45f097549a8b6a43aa149d78238513fd1"
PINNED_LAUNCH_GUARDS_SHA="84b505966f476cf0a944147fb638e6128c17dde14bdd69bcb3c3762f3c284795"
PINNED_REMOTE_RUNNER_SHA="7b346c97e2a56f86ead9417c1cbaa903f2ce1dd41aca7df41f32a78fae32c896"
PINNED_COLAB_WINDOW_SHA="79029af51608020fcf0898a9aba3add694612726474c00c7f755b213abb8fa1e"
PINNED_SELF_SHA="c5a6a0bbbd2ca2b98b40489e911e4b89186b721e2c90ca387ba522ae3967c7ac"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_SH="${SCRIPT_DIR}/launch_lane1_stub.sh"
# shellcheck source=scripts/colab/colab_window.sh
source "${SCRIPT_DIR}/colab_window.sh"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-lane1-stub-$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR=""
CAP="${CAP:-0.05}"
WALL_S="${WALL_S:-900}"
GRACE_S="${GRACE_S:-60}"
MARGIN="${MARGIN:-0.01}"
MAX_RATE=""
SHAPE=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --card) CARD="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --cap) CAP="$2"; shift 2 ;;
    --wall-s) WALL_S="$2"; shift 2 ;;
    --grace-s) GRACE_S="$2"; shift 2 ;;
    --margin) MARGIN="$2"; shift 2 ;;
    --max-rate) MAX_RATE="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --shape) SHAPE="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    *)
      echo "REFUSED: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# The evidence directory is the operator's choice; there is no default location.
if [ -z "${OUT_DIR}" ]; then
  echo "REFUSED: OUT_DIR_REQUIRED: pass --out-dir <dir> on a persistent disk" >&2
  exit 2
fi

# Test mode needs the flag AND the fake-marked colab CLI on PATH (refused if the flag is set
# without the fake). The pin overrides below are honoured only in test mode.
colab_guard_fake_cli_if_test
TEST_MODE=0
if colab_fake_test_mode_active; then
  TEST_MODE=1
fi

colab_refuse_volatile_out_dir "${OUT_DIR}" "${TEST_MODE}"
colab_refuse_nonempty_out_dir "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

PY_BIN="$(colab_resolve_python)"
GUARDS_PY="${SCRIPT_DIR}/launch_guards.py"
LANE1_PY="${SCRIPT_DIR}/lane1_render.py"
RUNNER_PY="${SCRIPT_DIR}/remote_runner.py"
CLASSIFIER_PY="${SCRIPT_DIR}/classify_install_log.py"
WINDOW_SH="${SCRIPT_DIR}/colab_window.sh"
LOCK_FILE="${SCRIPT_DIR}/locks/lane1.lock"

PIN_OVERRIDE_VARS=(
  EXPECTED_LANE1_LOCK_SHA
  EXPECTED_LANE1_RENDER_SHA
  EXPECTED_INSTALL_CLASSIFIER_SHA
  EXPECTED_LAUNCH_GUARDS_SHA
  EXPECTED_REMOTE_RUNNER_SHA
  EXPECTED_COLAB_WINDOW_SHA
  EXPECTED_LAUNCH_LANE1_STUB_SHA
)
colab_refuse_live_pin_overrides "${OUT_DIR}" "${TEST_MODE}" "${PIN_OVERRIDE_VARS[@]}"
EXP_LOCK_SHA="${PINNED_LOCK_SHA}"
EXP_LANE1_SHA="${PINNED_LANE1_RENDER_SHA}"
EXP_CLASSIFIER_SHA="${PINNED_INSTALL_CLASSIFIER_SHA}"
EXP_GUARDS_SHA="${PINNED_LAUNCH_GUARDS_SHA}"
EXP_RUNNER_SHA="${PINNED_REMOTE_RUNNER_SHA}"
EXP_WINDOW_SHA="${PINNED_COLAB_WINDOW_SHA}"
EXP_SELF_SHA="${PINNED_SELF_SHA}"
if [ "${TEST_MODE}" = "1" ]; then
  EXP_LOCK_SHA="${EXPECTED_LANE1_LOCK_SHA:-${EXP_LOCK_SHA}}"
  EXP_LANE1_SHA="${EXPECTED_LANE1_RENDER_SHA:-${EXP_LANE1_SHA}}"
  EXP_CLASSIFIER_SHA="${EXPECTED_INSTALL_CLASSIFIER_SHA:-${EXP_CLASSIFIER_SHA}}"
  EXP_GUARDS_SHA="${EXPECTED_LAUNCH_GUARDS_SHA:-${EXP_GUARDS_SHA}}"
  EXP_RUNNER_SHA="${EXPECTED_REMOTE_RUNNER_SHA:-${EXP_RUNNER_SHA}}"
  EXP_WINDOW_SHA="${EXPECTED_COLAB_WINDOW_SHA:-${EXP_WINDOW_SHA}}"
  EXP_SELF_SHA="${EXPECTED_LAUNCH_LANE1_STUB_SHA:-${EXP_SELF_SHA}}"
fi

SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
  "${LOCK_FILE}=${EXP_LOCK_SHA}" \
  "${LANE1_PY}=${EXP_LANE1_SHA}" \
  "${CLASSIFIER_PY}=${EXP_CLASSIFIER_SHA}" \
  "${GUARDS_PY}=${EXP_GUARDS_SHA}" \
  "${RUNNER_PY}=${EXP_RUNNER_SHA}" \
  "${WINDOW_SH}=${EXP_WINDOW_SHA}" \
  "${SELF_SH}=${EXP_SELF_SHA}")"

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
    colab_stop_and_log_closing "${PY_BIN}" "${SESSION}" "${OUT_DIR}"
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

# Free pre-flight resolve & git pin check before any colab CLI call.
# The pre-flight honours its SDLAB_PREFLIGHT_* test hooks only under the fake colab CLI
# and refuses them in a live run (PREFLIGHT_TEST_HOOK_IN_LIVE_RUN).
PREFLIGHT_OUT=""
if ! PREFLIGHT_OUT="$(bash "${SCRIPT_DIR}/preflight_resolve.sh" lane1 2>&1)"; then
  printf '%s\n' "${PREFLIGHT_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
  exit 1
fi
printf '%s\n' "${PREFLIGHT_OUT}" >> "${OUT_DIR}/guards.log"

# Pre-open cap and host-RAM check via launch_guards.py
# The card class sets the rate policy: a CPU stub keeps the labelled configured rate; a GPU card
# goes through the shared GPU rate gate (colab_window.sh: required --max-rate, a stable window rate
# at or above the floor, max pricing, the mid-run re-read and the assignment-count re-baseline).
colab_gpu_rate_gate_arm "${OUT_DIR}" "${CARD}" "${MAX_RATE}" "$(colab_fake_test_mode_active && echo 1 || echo 0)"
# A GPU card names its machine shape (--shape standard|high-mem, no default: SHAPE_REQUIRED); a CPU
# card keeps colab new --high-mem and takes no --shape (colab_window.sh, colab_shape_gate_arm).
colab_shape_gate_arm "${OUT_DIR}" "${CARD}" "${SHAPE}"
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

# Hold /tmp/colab-window-open.lock while opening with colab new (CPU: --high-mem; GPU: --high-mem
# only for --shape high-mem, then the session row's Shape is checked: SHAPE_MISMATCH)
SESSION_OPENED=1
colab_open_session_locked "${SESSION}" "${CARD}" "${OUT_DIR}"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"

REMOTE_RUNNER="${OUT_DIR}/remote_lane1_stub.sh"
cat > "${REMOTE_RUNNER}" << REMOTEEOF
#!/usr/bin/env bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=""

# >>> sdlab-remote-dirs
# The kit uploads every file flat into /content (colab upload creates no remote directory).
# This block makes the run's directory and checks it exists afterwards.
sdlab_remote_mkdir() {
  local d
  for d in "\$@"; do
    mkdir -p "\${d}" 2>/dev/null || true
    if [ ! -d "\${d}" ]; then
      echo "REFUSED: REMOTE_DIR_CREATE_FAILED: \${d}" >&2
      exit 1
    fi
  done
}
sdlab_remote_mkdir /content/lane1_out
# <<< sdlab-remote-dirs

: "\${PINNED_UV_VERSION:?missing PINNED_UV_VERSION}"
: "\${PINNED_UV_WHEEL_SHA256:?missing PINNED_UV_WHEEL_SHA256}"
: "\${PINNED_PYTHON_VERSION:?missing PINNED_PYTHON_VERSION}"
: "\${PINNED_PYTHON_BUILD:?missing PINNED_PYTHON_BUILD}"
: "\${PINNED_PYTORCH_INDEX_URL:?missing PINNED_PYTORCH_INDEX_URL}"
: "\${PINNED_COMFYUI_REPO:?missing PINNED_COMFYUI_REPO}"
: "\${PINNED_COMFYUI_COMMIT:?missing PINNED_COMFYUI_COMMIT}"
: "\${PINNED_COMFY_HEADLESS_SPEC:?missing PINNED_COMFY_HEADLESS_SPEC}"
: "\${PINNED_LOCK_SHA:?missing PINNED_LOCK_SHA}"

echo "setup" > /content/lane1_out/phase.txt
: > /content/lane1_out/setup.log
(
  while true; do
    {
      echo "=== VITALS \$(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
      if [ -f /sys/fs/cgroup/memory.current ]; then
        echo "CGROUP_MEM_CURRENT: \$(cat /sys/fs/cgroup/memory.current)" || true
      fi
      if [ -f /sys/fs/cgroup/memory.max ]; then
        echo "CGROUP_MEM_MAX: \$(cat /sys/fs/cgroup/memory.max)" || true
      fi
      if [ -f /sys/fs/cgroup/memory.events ]; then
        sed 's/^/CGROUP_MEM: /' /sys/fs/cgroup/memory.events || true
      fi
      if [ -f /sys/fs/cgroup/memory.stat ]; then
        grep -E '^(anon|shmem|file) ' /sys/fs/cgroup/memory.stat | sed 's/^/CGROUP_MEM_STAT: /' || true
      fi
      grep -E '^(MemTotal|MemAvailable|AnonPages|Shmem):' /proc/meminfo | sed 's/^/MEM: /' || true
      SETUP_SZ="\$(wc -c < /content/lane1_out/setup.log 2>/dev/null | tr -d '[:space:]' || echo 0)"
      echo "SETUP_BYTES: \${SETUP_SZ:-0}"
      echo "PROC:"
      ps -ef | grep -E "comfy|main\.py|lane1_render\.py" | grep -v grep || true
      CUR_PHASE="\$(cat /content/lane1_out/phase.txt 2>/dev/null || echo setup)"
      printf 'HARNESS: {"phase": "%s"}\n' "\${CUR_PHASE}"
    } | tee -a /content/lane1_out/vitals.log
    sleep 15
  done
) &
VITALS_PID="\$!"
trap 'kill "\${VITALS_PID}" 2>/dev/null || true' EXIT

{
  unset UV_SYSTEM_PYTHON
  export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_314/install"
  export UV_NO_BUILD=1
  # uv itself is installed by hash: only the pinned manylinux x86_64 wheel is accepted.
  printf 'uv==%s --hash=sha256:%s\n' "\${PINNED_UV_VERSION}" "\${PINNED_UV_WHEEL_SHA256}" > /content/uv-bootstrap.txt
  pip install --quiet --require-hashes --only-binary :all: --no-deps -r /content/uv-bootstrap.txt
  uv python install "\${PINNED_PYTHON_VERSION}"
  uv venv --python "\${PINNED_PYTHON_VERSION}" /content/venv-lane1
  /content/venv-lane1/bin/python -c '
import sys
if not (sys.version.startswith("3.14.9") and sys.prefix.startswith("/content/venv-lane")):
    sys.stderr.write(f"REFUSED: VENV_PYTHON_MISMATCH version={sys.version!r} prefix={sys.prefix!r}\n")
    raise SystemExit(1)
'
  /content/venv-lane1/bin/python -c 'import sys; assert sys.version.startswith("3.14.9"), sys.version; assert sys.prefix.startswith("/content/venv-lane"), sys.prefix'
  # Interpreter identity: uv's build tag, download URL, sys.version and the binary's sha256.
  /content/venv-lane1/bin/python - "\${PINNED_PYTHON_VERSION}" "\${PINNED_PYTHON_BUILD}" "\${UV_PYTHON_INSTALL_DIR}" /content/lane1_out/python_identity.json << 'PYIDEOF'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

version, want_build, install_dir, out_json = sys.argv[1:5]
key = "cpython-" + version + "-linux-x86_64-gnu"
inst = Path(install_dir) / key
build_f = inst / "BUILD"
build = build_f.read_text(encoding="utf-8").strip() if build_f.is_file() else None
minor = ".".join(version.split(".")[:2])
binary = inst / "bin" / ("python" + minor)
binary_sha = None
if binary.is_file():
    binary_sha = "sha256:" + hashlib.sha256(binary.resolve().read_bytes()).hexdigest()
download_url = None
listing = subprocess.run(
    ["uv", "python", "list", version, "--only-downloads", "--output-format", "json"],
    capture_output=True, text=True, check=False,
)
try:
    for entry in json.loads(listing.stdout or "[]"):
        if entry.get("key") == key:
            download_url = entry.get("url")
except ValueError:
    pass
rec = {
    "key": key,
    "build": build,
    "pinned_build": want_build,
    "download_url": download_url,
    "sys_version": sys.version,
    "binary": str(binary.resolve()) if binary.exists() else str(binary),
    "binary_sha256": binary_sha,
}
Path(out_json).write_text(json.dumps(rec, indent=2) + chr(10), encoding="utf-8")
print("PYTHON_IDENTITY " + json.dumps(rec), flush=True)
if build != want_build or binary_sha is None:
    sys.stderr.write("REFUSED: PYTHON_BUILD_MISMATCH: " + key + " build=" + repr(build) + " pinned=" + want_build + chr(10))
    raise SystemExit(1)
PYIDEOF
} 2>&1 | tee -a /content/lane1_out/setup.log
{
  unset UV_SYSTEM_PYTHON
  export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_314/install"
  export UV_NO_BUILD=1
  ACTUAL_LOCK_SHA="\$(sha256sum /content/lane1.lock | awk '{print \$1}')"
  echo "\${ACTUAL_LOCK_SHA}  /content/lane1.lock" > /content/lane1_out/lock.sha256
  if [ "\${ACTUAL_LOCK_SHA}" != "\${PINNED_LOCK_SHA}" ]; then
    echo "REFUSED: LOCK_HASH_MISMATCH: /content/lane1.lock sha256=\${ACTUAL_LOCK_SHA} expected=\${PINNED_LOCK_SHA}" >&2
    exit 1
  fi

  if [ ! -d /content/ComfyUI ]; then
    git clone "\${PINNED_COMFYUI_REPO}" /content/ComfyUI
  fi
  git -C /content/ComfyUI fetch --depth 1 origin "\${PINNED_COMFYUI_COMMIT}" || true
  git -C /content/ComfyUI checkout "\${PINNED_COMFYUI_COMMIT}"
  ACTUAL_COMFYUI_COMMIT="\$(git -C /content/ComfyUI rev-parse HEAD)"
  if [ "\${ACTUAL_COMFYUI_COMMIT}" != "\${PINNED_COMFYUI_COMMIT}" ]; then
    echo "REFUSED: PIN_NOT_FOUND: ComfyUI commit mismatch: got \${ACTUAL_COMFYUI_COMMIT}, expected \${PINNED_COMFYUI_COMMIT}" >&2
    exit 1
  fi

  set +e
  uv pip install --python /content/venv-lane1/bin/python --require-hashes --only-binary :all: --extra-index-url "\${PINNED_PYTORCH_INDEX_URL}" --index-strategy unsafe-best-match -r /content/lane1.lock > /content/lane1_out/wheels.log 2>&1
  UV_RC=\$?
  set -e
  cat /content/lane1_out/wheels.log
  if [ "\${UV_RC}" -ne 0 ]; then
    /content/venv-lane1/bin/python /content/classify_install_log.py --lane lane1 --log /content/lane1_out/wheels.log >&2 \
      || echo "REFUSED: INSTALL_FAILED during lane1 lock install (classifier did not run)" >&2
    exit 1
  fi

  /content/venv-lane1/bin/python -c '
import importlib
import sys

REQUIRED = ("comfy_headless", "torch", "safetensors", "PIL", "yaml", "aiohttp")
for mod_name in REQUIRED:
    try:
        mod = importlib.import_module(mod_name)
    except Exception as exc:
        sys.stderr.write(f"REFUSED: VENV_IMPORT_FAILED {mod_name}: {exc}\n")
        raise SystemExit(1)
    mod_file = getattr(mod, "__file__", None) or ""
    print(f"VENV_IMPORT {mod_name} {mod_file}", flush=True)
    if not mod_file.startswith("/content/venv-lane1/"):
        sys.stderr.write(f"REFUSED: VENV_IMPORT_OUTSIDE_VENV {mod_name}: {mod_file}\n")
        raise SystemExit(1)
from comfy_headless import ComfyClient
assert ComfyClient is not None
'
} 2>&1 | tee -a /content/lane1_out/setup.log

echo "run" > /content/lane1_out/phase.txt
/content/venv-lane1/bin/python /content/ComfyUI/main.py --cpu --listen 127.0.0.1 --port 8188 --disable-auto-launch \
  > /content/lane1_out/comfyui.log 2>&1 &
COMFY_PID="\$!"

for _ in \$(seq 1 60); do
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
/content/venv-lane1/bin/python /content/lane1_render.py \
  --cpu --bootstrap \
  --comfy-pid "\${COMFY_PID}" \
  --comfyui-commit "\${PINNED_COMFYUI_COMMIT}" \
  --window-json /content/lane1_out/vm_window.json \
  --jobs /content/lane1_out/jobs.jsonl \
  --renders /content/lane1_out/renders.jsonl \
  --out-dir /content/lane1_out/pngs \
  --copy-back-dir /content/lane1_out/copy_back \
  --copy-back-every 1 \
  --kill-after 1
RC1=\$?
set -e
if [ "\${RC1}" -ne 75 ]; then
  echo "Expected exit 75 on deliberate kill-after=1, got \${RC1}" >&2
  exit 1
fi

SHA_BEFORE="\$(sha256sum /content/lane1_out/pngs/stub_01.png | awk '{print \$1}')"

/content/venv-lane1/bin/python /content/lane1_render.py \
  --cpu \
  --jobs /content/lane1_out/jobs.jsonl \
  --renders /content/lane1_out/renders.jsonl \
  --out-dir /content/lane1_out/pngs \
  --copy-back-dir /content/lane1_out/copy_back \
  --copy-back-every 1

SHA_AFTER="\$(sha256sum /content/lane1_out/pngs/stub_01.png | awk '{print \$1}')"
SHA_COPY="\$(sha256sum /content/lane1_out/copy_back/stub_01.png | awk '{print \$1}')"
if [ "\${SHA_BEFORE}" != "\${SHA_AFTER}" ] || [ "\${SHA_BEFORE}" != "\${SHA_COPY}" ]; then
  echo "Resume hash mismatch: before=\${SHA_BEFORE} after=\${SHA_AFTER} copy=\${SHA_COPY}" >&2
  exit 1
fi

kill "\${COMFY_PID}" 2>/dev/null || true
while IFS= read -r -d '' f; do
  /content/venv-lane1/bin/python /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
done < <(find /content/lane1_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.txt" \) -print0 2>/dev/null || true)
tar -czf /content/lane1_stub_bundle.tar.gz -C /content/lane1_out .
REMOTEEOF

# Every upload goes flat into /content, the one remote directory that exists before the remote
# script runs.
colab_upload_checked "${SESSION}" "${LOCK_FILE}" /content/lane1.lock "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${LANE1_PY}" /content/lane1_render.py "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${GUARDS_PY}" /content/launch_guards.py "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${CLASSIFIER_PY}" /content/classify_install_log.py "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${REMOTE_RUNNER}" /content/remote_lane1_stub.sh "${OUT_DIR}"

colab_run_exec_with_live_guards \
  "${PY_BIN}" "${GUARDS_PY}" "${SESSION}" "${RUNNER_PY}" \
  "${START_EPOCH}" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}" \
  "SDLAB_REMOTE_SCRIPT=/content/remote_lane1_stub.sh" \
  "PINNED_UV_VERSION=${PINNED_UV_VERSION}" \
  "PINNED_UV_WHEEL_SHA256=${PINNED_UV_WHEEL_SHA256}" \
  "PINNED_PYTHON_VERSION=${PINNED_PYTHON_VERSION}" \
  "PINNED_PYTHON_BUILD=${PINNED_PYTHON_BUILD}" \
  "PINNED_PYTORCH_INDEX_URL=${PINNED_PYTORCH_INDEX_URL}" \
  "PINNED_COMFYUI_REPO=${PINNED_COMFYUI_REPO}" \
  "PINNED_COMFYUI_COMMIT=${PINNED_COMFYUI_COMMIT}" \
  "PINNED_COMFY_HEADLESS_SPEC=${PINNED_COMFY_HEADLESS_SPEC}" \
  "PINNED_LOCK_SHA=${EXP_LOCK_SHA}"

# Download result tar before EXIT trap stops the session
colab_download_checked "${SESSION}" /content/lane1_stub_bundle.tar.gz "${OUT_DIR}/lane1_stub_bundle.tar.gz" "${OUT_DIR}"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
