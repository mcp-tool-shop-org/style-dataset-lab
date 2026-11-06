#!/usr/bin/env bash
# Stub launch kit for Lane 3 (train) Colab CPU high-mem window (Part C, PR #47).
# Checks pinned input sha256s (including itself) and runs preflight_resolve.sh before opening,
# holds /tmp/colab-window-open.lock, opens CPU --high-mem, runs CPython 3.12.15 uv venv + wheel-only
# install from hash-locked lane3.lock and pre-built local wheels in lane3-local-wheels.json + pinned
# ostris/ai-toolkit + generates synth_job.yaml for a 1-step CPU training run on the synthetic package +
# verifies the .safetensors checkpoint exists and records its path in window.json, enforces live
# launch_guards.py (wall, cap, vitals/DEAD HARNESS, host-RAM), scrubs VM-side logs before tarring,
# downloads result tar, and stops its own session in an EXIT trap on every exit path.
set -euo pipefail

PINNED_UV_VERSION="0.13.5"
# sha256 of uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl on PyPI (the Colab VM platform)
PINNED_UV_WHEEL_SHA256="fa8d26e08e34c29c0c4e820cf3181757086d547240b4f4d31ff1d8bd810ca946"
PINNED_PYTHON_VERSION="3.12.15"
PINNED_PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu130"
PINNED_AI_TOOLKIT_REPO="https://github.com/ostris/ai-toolkit.git"
PINNED_AI_TOOLKIT_COMMIT="beb94824c51480a04d3c86c718603676fdef6938"
PINNED_OVERRIDE_SHA="09d15fae7473fd76131bb01578a6b060b20c3b10e91eccd8133377ea17b03286"
PINNED_LOCAL_WHEELS_MANIFEST_SHA="579016010aae8e5549ffc5b4777f5899a6e410eafba680a61ab3841e758b6320"
PINNED_INSTALL_CLASSIFIER_SHA="ccccf077795148c14a7aa430e3575db45f097549a8b6a43aa149d78238513fd1"
PINNED_LAUNCH_GUARDS_SHA="8e664906e6deb45b498a0193e916d2d424f7e9b5839f39e63ea07f81a4682a78"
PINNED_REMOTE_RUNNER_SHA="7d4fc25401c1504910615f1aaea4418a6694196530380c11c9a9a25b02f83537"
PINNED_COLAB_WINDOW_SHA="af85f6d3a3eceae88c4e1b49c0ee107d76cc9bb29efe678cd8df16cbcaf275eb"
PINNED_SELF_SHA="666beaa2ade7d3bffb71906381044a2a6081e8728e597ff87d47ef54fc33611d"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_SH="${SCRIPT_DIR}/launch_lane3_stub.sh"
# shellcheck source=scripts/colab/colab_window.sh
source "${SCRIPT_DIR}/colab_window.sh"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-lane3-stub-$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR=""
WHEEL_DIR="${SDLAB_WHEEL_DIR:-}"
CAP="${CAP:-0.05}"
WALL_S="${WALL_S:-900}"
GRACE_S="${GRACE_S:-60}"
MARGIN="${MARGIN:-0.01}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --card) CARD="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --wheel-dir) WHEEL_DIR="$2"; shift 2 ;;
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

# The pre-built wheels live outside the repository; there is no default location.
if [ -z "${WHEEL_DIR}" ]; then
  echo "REFUSED: WHEEL_DIR_REQUIRED: pass --wheel-dir <dir> or set SDLAB_WHEEL_DIR" >&2
  exit 2
fi

if [ -z "${OUT_DIR}" ]; then
  OUT_DIR="/tmp/${SESSION}"
fi
colab_refuse_nonempty_out_dir "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

PY_BIN="$(colab_resolve_python)"
GUARDS_PY="${SCRIPT_DIR}/launch_guards.py"
LOCK_FILE="${SCRIPT_DIR}/locks/lane3.lock"
LOCAL_WHEELS_JSON="${SCRIPT_DIR}/locks/lane3-local-wheels.json"
# Test hook: a fixture manifest, used only under the fake colab CLI (the pre-flight refuses it live).
if [ "${SDLAB_TEST_FAKE_COLAB:-0}" = "1" ] && [ -n "${SDLAB_PREFLIGHT_WHEELS_MANIFEST:-}" ]; then
  LOCAL_WHEELS_JSON="${SDLAB_PREFLIGHT_WHEELS_MANIFEST}"
fi
RUNNER_PY="${SCRIPT_DIR}/remote_runner.py"
CLASSIFIER_PY="${SCRIPT_DIR}/classify_install_log.py"
WINDOW_SH="${SCRIPT_DIR}/colab_window.sh"

colab_guard_fake_cli_if_test

EXP_OVERRIDE_SHA="${EXPECTED_OVERRIDE_SHA:-${PINNED_OVERRIDE_SHA}}"
EXP_LOCAL_WHEELS_SHA="${EXPECTED_LOCAL_WHEELS_MANIFEST_SHA:-${PINNED_LOCAL_WHEELS_MANIFEST_SHA}}"
EXP_CLASSIFIER_SHA="${EXPECTED_INSTALL_CLASSIFIER_SHA:-${PINNED_INSTALL_CLASSIFIER_SHA}}"
EXP_GUARDS_SHA="${EXPECTED_LAUNCH_GUARDS_SHA:-${PINNED_LAUNCH_GUARDS_SHA}}"
EXP_RUNNER_SHA="${EXPECTED_REMOTE_RUNNER_SHA:-${PINNED_REMOTE_RUNNER_SHA}}"
EXP_WINDOW_SHA="${EXPECTED_COLAB_WINDOW_SHA:-${PINNED_COLAB_WINDOW_SHA}}"
EXP_SELF_SHA="${EXPECTED_LAUNCH_LANE3_STUB_SHA:-${PINNED_SELF_SHA}}"

SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
  "${LOCK_FILE}=${EXP_OVERRIDE_SHA}" \
  "${LOCAL_WHEELS_JSON}=${EXP_LOCAL_WHEELS_SHA}" \
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
    "${PY_BIN}" "${OUT_DIR}" "train" "${SESSION}" "${CARD}" \
    "${CAP}" "${WALL_S}" "${GRACE_S}" "${MARGIN}" \
    "${OPENED_AT}" "${closed_at}" "${rc}" "${SHAS_JSON}" || true
  colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" || true
  exit "${rc}"
}
trap cleanup_on_exit EXIT
trap 'exit 143' TERM INT

if [[ "${WHEEL_DIR}" =~ ^([A-Za-z]):/(.*)$ ]] && [[ -d "/mnt/${BASH_REMATCH[1],,}" ]]; then
  DRIVE_LOWER="${BASH_REMATCH[1],,}"
  REST_PATH="${BASH_REMATCH[2]}"
  if [[ ! -d "${WHEEL_DIR}" ]] && [[ -d "/mnt/${DRIVE_LOWER}/${REST_PATH}" ]]; then
    WHEEL_DIR="/mnt/${DRIVE_LOWER}/${REST_PATH}"
  fi
fi

# Free pre-flight resolve, git pin check, and local wheel sha verification before any colab CLI call.
# The pre-flight honours its SDLAB_PREFLIGHT_* test hooks only under the fake colab CLI
# and refuses them in a live run (PREFLIGHT_TEST_HOOK_IN_LIVE_RUN).
PREFLIGHT_OUT=""
if ! PREFLIGHT_OUT="$(bash "${SCRIPT_DIR}/preflight_resolve.sh" lane3 --wheel-dir "${WHEEL_DIR}" 2>&1)"; then
  printf '%s\n' "${PREFLIGHT_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
  exit 1
fi
printf '%s\n' "${PREFLIGHT_OUT}" >> "${OUT_DIR}/guards.log"

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
cat > "${REMOTE_RUNNER}" << REMOTEEOF
#!/usr/bin/env bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=""
mkdir -p /content/lane3_out /content/lane3_out/checkpoints

: "\${PINNED_UV_VERSION:?missing PINNED_UV_VERSION}"
: "\${PINNED_UV_WHEEL_SHA256:?missing PINNED_UV_WHEEL_SHA256}"
: "\${PINNED_PYTHON_VERSION:?missing PINNED_PYTHON_VERSION}"
: "\${PINNED_PYTORCH_INDEX_URL:?missing PINNED_PYTORCH_INDEX_URL}"
: "\${PINNED_AI_TOOLKIT_REPO:?missing PINNED_AI_TOOLKIT_REPO}"
: "\${PINNED_AI_TOOLKIT_COMMIT:?missing PINNED_AI_TOOLKIT_COMMIT}"
: "\${PINNED_OVERRIDE_SHA:?missing PINNED_OVERRIDE_SHA}"

echo "setup" > /content/lane3_out/phase.txt
: > /content/lane3_out/setup.log
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
      grep -E '^(MemTotal|MemAvailable|AnonPages):' /proc/meminfo | sed 's/^/MEM: /' || true
      SETUP_SZ="\$(wc -c < /content/lane3_out/setup.log 2>/dev/null | tr -d '[:space:]' || echo 0)"
      echo "SETUP_BYTES: \${SETUP_SZ:-0}"
      echo "PROC:"
      ps -ef | grep -E "ai-toolkit|run\.py" | grep -v grep || true
      CUR_PHASE="\$(cat /content/lane3_out/phase.txt 2>/dev/null || echo setup)"
      printf 'HARNESS: {"phase": "%s"}\n' "\${CUR_PHASE}"
    } | tee -a /content/lane3_out/vitals.log
    sleep 15
  done
) &
VITALS_PID="\$!"
trap 'kill "\${VITALS_PID}" 2>/dev/null || true' EXIT

OVERRIDE_SHA="\$(sha256sum /content/lane3.lock | awk '{print \$1}')"
echo "\${OVERRIDE_SHA}  /content/lane3.lock" > /content/lane3_out/override.sha256

{
  unset UV_SYSTEM_PYTHON
  export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_312/install"
  export UV_NO_BUILD=1
  # uv itself is installed by hash: only the pinned manylinux x86_64 wheel is accepted.
  printf 'uv==%s --hash=sha256:%s\n' "\${PINNED_UV_VERSION}" "\${PINNED_UV_WHEEL_SHA256}" > /content/uv-bootstrap.txt
  pip install --quiet --require-hashes --only-binary :all: --no-deps -r /content/uv-bootstrap.txt
  uv python install "\${PINNED_PYTHON_VERSION}"
  uv venv --python "\${PINNED_PYTHON_VERSION}" /content/venv-lane3
  /content/venv-lane3/bin/python -c '
import sys
if not (sys.version.startswith("3.12.15") and sys.prefix.startswith("/content/venv-lane")):
    sys.stderr.write(f"REFUSED: VENV_PYTHON_MISMATCH version={sys.version!r} prefix={sys.prefix!r}\n")
    raise SystemExit(1)
'
  /content/venv-lane3/bin/python -c 'import sys; assert sys.version.startswith("3.12.15"), sys.version; assert sys.prefix.startswith("/content/venv-lane"), sys.prefix'
} 2>&1 | tee -a /content/lane3_out/setup.log
{
  unset UV_SYSTEM_PYTHON
  export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_312/install"
  export UV_NO_BUILD=1
  if [ "\${OVERRIDE_SHA}" != "\${PINNED_OVERRIDE_SHA}" ]; then
    echo "REFUSED: LOCK_HASH_MISMATCH: /content/lane3.lock sha256=\${OVERRIDE_SHA} expected=\${PINNED_OVERRIDE_SHA}" >&2
    exit 1
  fi

  # Verify uploaded local wheels on VM against lane3-local-wheels.json and generate local-wheels.lock
  /content/venv-lane3/bin/python - << 'WHEELPYEOF'
import hashlib
import json
import sys
from pathlib import Path

manifest = json.loads(Path("/content/lane3-local-wheels.json").read_text(encoding="utf-8"))
lines = []
for entry in manifest.get("wheels", []):
    fname = entry["filename"]
    pkg = entry["package"]
    ver = entry["version"]
    exp_sha = entry["sha256"].lower().removeprefix("sha256:")
    wpath = Path("/content/wheels") / fname
    if not wpath.is_file():
        sys.stderr.write(f"REFUSED: LOCAL_WHEEL_MISSING on VM: {wpath}\n")
        raise SystemExit(1)
    act_sha = hashlib.sha256(wpath.read_bytes()).hexdigest().lower()
    if act_sha != exp_sha:
        sys.stderr.write(f"REFUSED: LOCAL_WHEEL_SHA_MISMATCH on VM: {fname} got {act_sha} expected {exp_sha}\n")
        raise SystemExit(1)
    lines.append(f"{pkg}=={ver} \\\n    --hash=sha256:{exp_sha}\n")
Path("/content/lane3_out/local-wheels.lock").write_text("".join(lines), encoding="utf-8")
WHEELPYEOF

  if [ ! -d /content/ai-toolkit ]; then
    git clone "\${PINNED_AI_TOOLKIT_REPO}" /content/ai-toolkit
  fi
  git -C /content/ai-toolkit fetch --depth 1 origin "\${PINNED_AI_TOOLKIT_COMMIT}" || true
  git -C /content/ai-toolkit checkout "\${PINNED_AI_TOOLKIT_COMMIT}"
  ACTUAL_AI_TOOLKIT_COMMIT="\$(git -C /content/ai-toolkit rev-parse HEAD)"
  if [ "\${ACTUAL_AI_TOOLKIT_COMMIT}" != "\${PINNED_AI_TOOLKIT_COMMIT}" ]; then
    echo "REFUSED: PIN_NOT_FOUND: ai-toolkit commit mismatch: got \${ACTUAL_AI_TOOLKIT_COMMIT}, expected \${PINNED_AI_TOOLKIT_COMMIT}" >&2
    exit 1
  fi

  set +e
  uv pip install --python /content/venv-lane3/bin/python --require-hashes --only-binary :all: --extra-index-url "\${PINNED_PYTORCH_INDEX_URL}" --index-strategy unsafe-best-match -r /content/lane3.lock > /content/lane3_out/wheels.log 2>&1
  UV_RC1=\$?
  uv pip install --python /content/venv-lane3/bin/python --require-hashes --only-binary :all: --no-index --find-links /content/wheels --no-deps -r /content/lane3_out/local-wheels.lock >> /content/lane3_out/wheels.log 2>&1
  UV_RC2=\$?
  set -e
  cat /content/lane3_out/wheels.log
  if [ "\${UV_RC1}" -ne 0 ] || [ "\${UV_RC2}" -ne 0 ]; then
    /content/venv-lane3/bin/python /content/classify_install_log.py --lane lane3 --log /content/lane3_out/wheels.log >&2 \
      || echo "REFUSED: INSTALL_FAILED during lane3 lock install (classifier did not run)" >&2
    exit 1
  fi

  /content/venv-lane3/bin/python -c '
import importlib
import sys

REQUIRED = ("sentencepiece", "torch", "safetensors", "yaml", "oyaml", "PIL", "diffusers", "lycoris")
for mod_name in REQUIRED:
    try:
        mod = importlib.import_module(mod_name)
    except Exception as exc:
        sys.stderr.write(f"REFUSED: VENV_IMPORT_FAILED {mod_name}: {exc}\n")
        raise SystemExit(1)
    mod_file = getattr(mod, "__file__", None) or ""
    print(f"VENV_IMPORT {mod_name} {mod_file}", flush=True)
    if not mod_file.startswith("/content/venv-lane3/"):
        sys.stderr.write(f"REFUSED: VENV_IMPORT_OUTSIDE_VENV {mod_name}: {mod_file}\n")
        raise SystemExit(1)
import sentencepiece as spm
print("SENTENCEPIECE_OK", spm.__version__, flush=True)
' | tee /content/lane3_out/sentencepiece.txt
} 2>&1 | tee -a /content/lane3_out/setup.log

/content/venv-lane3/bin/python - << 'SYNTHEOF'
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

cat > /content/lane3_out/synth_job.yaml << 'YAMLEOF'
job: extension
config:
  name: synth_lora
  process:
    - type: sd_trainer
      training_folder: /content/lane3_out/checkpoints
      device: cpu
      network:
        type: lora
        linear: 4
        linear_alpha: 4
      save:
        dtype: float32
        save_every: 1
        max_step_saves_to_keep: 1
      datasets:
        - folder_path: /content/lane3_out/synth_pkg
          caption_ext: txt
          resolution: [64, 64]
      train:
        batch_size: 1
        steps: 1
        lr: 0.0001
        optimizer: adamw
        dtype: fp32
YAMLEOF

echo "run" > /content/lane3_out/phase.txt
/content/venv-lane3/bin/python /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml \
  > /content/lane3_out/train.log 2>&1

CHECKPOINT_PATH="/content/lane3_out/checkpoints/synth_lora.safetensors"
if [ ! -s "\${CHECKPOINT_PATH}" ]; then
  FOUND_CKPT="\$(find /content/lane3_out/checkpoints -name '*.safetensors' -type f | head -n 1 || true)"
  if [ -n "\${FOUND_CKPT}" ] && [ -s "\${FOUND_CKPT}" ]; then
    cp "\${FOUND_CKPT}" "\${CHECKPOINT_PATH}"
  else
    echo "REFUSED: expected non-empty .safetensors checkpoint at \${CHECKPOINT_PATH}" >&2
    exit 1
  fi
fi

/content/venv-lane3/bin/python - "\${PINNED_AI_TOOLKIT_COMMIT}" "\${OVERRIDE_SHA}" "\${CHECKPOINT_PATH}" << 'WINPYEOF'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ai_commit = sys.argv[1]
override_sha = sys.argv[2]
ckpt_path = sys.argv[3]
sys_py = subprocess.run(["/usr/bin/python3", "--version"], capture_output=True, text=True, check=False).stdout.strip().split()[-1]
uv_ver = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False).stdout.strip()
py_sha = "sha256:" + hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
rec = {
    "system_python": sys_py,
    "python": sys.version.split()[0],
    "python_sha256": py_sha,
    "uv": uv_ver,
    "ai_toolkit_commit": ai_commit,
    "override_sha256": f"sha256:{override_sha}",
    "checkpoint_path": ckpt_path,
}
Path("/content/lane3_out/vm_window.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
print("WINDOW_JSON " + json.dumps(rec), flush=True)
WINPYEOF

while IFS= read -r -d '' f; do
  /content/venv-lane3/bin/python /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
done < <(find /content/lane3_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.txt" \) -print0 2>/dev/null || true)
tar -czf /content/lane3_stub_bundle.tar.gz -C /content/lane3_out .
REMOTEEOF

colab upload -s "${SESSION}" "${LOCK_FILE}" /content/lane3.lock </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab upload -s "${SESSION}" "${LOCAL_WHEELS_JSON}" /content/lane3-local-wheels.json </dev/null >> "${OUT_DIR}/colab.log" 2>&1
while IFS= read -r wheel_fname; do
  [ -z "${wheel_fname}" ] && continue
  colab upload -s "${SESSION}" "${WHEEL_DIR}/${wheel_fname}" "/content/wheels/${wheel_fname}" </dev/null >> "${OUT_DIR}/colab.log" 2>&1
done < <("${PY_BIN}" -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); print("\n".join(w["filename"] for w in d.get("wheels", [])))' "${LOCAL_WHEELS_JSON}")
colab upload -s "${SESSION}" "${GUARDS_PY}" /content/launch_guards.py </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab upload -s "${SESSION}" "${CLASSIFIER_PY}" /content/classify_install_log.py </dev/null >> "${OUT_DIR}/colab.log" 2>&1
colab upload -s "${SESSION}" "${REMOTE_RUNNER}" /content/remote_lane3_stub.sh </dev/null >> "${OUT_DIR}/colab.log" 2>&1

colab_run_exec_with_live_guards \
  "${PY_BIN}" "${GUARDS_PY}" "${SESSION}" "${RUNNER_PY}" \
  "${START_EPOCH}" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}" \
  "SDLAB_REMOTE_SCRIPT=/content/remote_lane3_stub.sh" \
  "PINNED_UV_VERSION=${PINNED_UV_VERSION}" \
  "PINNED_UV_WHEEL_SHA256=${PINNED_UV_WHEEL_SHA256}" \
  "PINNED_PYTHON_VERSION=${PINNED_PYTHON_VERSION}" \
  "PINNED_PYTORCH_INDEX_URL=${PINNED_PYTORCH_INDEX_URL}" \
  "PINNED_AI_TOOLKIT_REPO=${PINNED_AI_TOOLKIT_REPO}" \
  "PINNED_AI_TOOLKIT_COMMIT=${PINNED_AI_TOOLKIT_COMMIT}" \
  "PINNED_OVERRIDE_SHA=${EXP_OVERRIDE_SHA}"

# Download result tar before EXIT trap stops the session
colab download -s "${SESSION}" /content/lane3_stub_bundle.tar.gz "${OUT_DIR}/lane3_stub_bundle.tar.gz" </dev/null >> "${OUT_DIR}/colab.log" 2>&1
if [ ! -s "${OUT_DIR}/lane3_stub_bundle.tar.gz" ]; then
  echo "REFUSED: downloaded bundle ${OUT_DIR}/lane3_stub_bundle.tar.gz is missing or empty" >&2
  exit 1
fi
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
