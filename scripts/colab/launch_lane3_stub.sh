#!/usr/bin/env bash
# Launch kit for Lane 3 (train) Colab windows: the CPU install-path stub (Part C, PR #47) and, with
# --train, the GPU rung. Checks pinned input sha256s (including itself) and runs preflight_resolve.sh
# before opening, holds /tmp/colab-window-open.lock, opens the card (CPU: --high-mem; GPU: --shape standard|high-mem), runs CPython 3.12.15
# uv venv + wheel-only install from hash-locked lane3.lock and pre-built local wheels in
# lane3-local-wheels.json + pinned ostris/ai-toolkit + the import gate. Without --train it stops
# there: TRAIN_SKIPPED and train=skipped_cpu_stub in window.json (never a trained result). With
# --train (a GPU card, either --rung-job 20|500 or --job <path> --job-sha <sha> with
# --dataset-manifest <path> --dataset-manifest-sha <sha>, plus --model, --model-revision,
# --host-ram-required-gib, --download-max-seconds and --dataset-dir, each a named refusal when
# missing) the remote script's LANE3_MODE=train runs the training window: GPU smoke / disk /
# host-RAM guards before the model download, the download with its DOWNLOAD_TOO_SLOW probe, the
# batched dataset tar (/content/lane3_dataset.tar, packed and sha-recorded before `colab new` and
# verified by archive sha + per-item sha on the VM), the active job YAML (uploaded as
# /content/rung-qwen-image.yaml)
# and ai-toolkit's run.py, copying each checkpoint and sample into the bundle as it is saved; the
# bundle is downloaded at the end and, after a failure, whatever it holds. Enforces live
# launch_guards.py (wall, cap, vitals/DEAD HARNESS, host-RAM), scrubs VM-side logs before tarring,
# and stops its own session in an EXIT trap on every exit path.
#
# Bounded setup, post-failure salvage, and stop contract (colab_window.sh):
#   open-lock wait: timeout -k 10 180 (190 s)
#   colab new: timeout -k 10 180 (190 s)
#   colab upload: timeout -k 10 120 (130 s)
#   colab download: timeout -k 10 ${COLAB_DOWNLOAD_TIMEOUT_S:-300} (default 300 s -> 310 s; --download-timeout-s / COLAB_DOWNLOAD_TIMEOUT_S)
#   restart-kernel: timeout -k 10 180 (190 s)
#   bundle-now exec (--timeout 300): timeout -k 10 330 (340 s)
#   salvage download: timeout -k 10 ${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S:-300} per projected part (default 300 s -> 310 s * N)
#   SALVAGE_DEADLINE_S=190+340+N*310 (840 s for N=1; 1150 s for N=2 rung jobs; past it -> colab stop)
#   colab stop: timeout -k 10 60 with 1 retry (2 * 70 = 140 s)
#   wall watcher escalation: 30 s after TERM -> watcher runs `colab stop` itself (stop_path: trap | watcher)
#   measured from trip: cleanup_stop_attempted_by_s = 310 + SALVAGE_DEADLINE_S (1150 s for N=1; 1460 s for N=2),
#                       cleanup_bound_s = cleanup_stop_attempted_by_s + 140 (1290 s for N=1; 1600 s for N=2)
#   effective_trip = cap - margin - cleanup_reserve; cleanup_reserve = (cleanup_bound_s / 3600) * priced_rate
#   (CAP_TOO_SMALL_FOR_CLEANUP up front; --min-runtime-s; --dry)
set -euo pipefail

PINNED_UV_VERSION="0.13.5"
# sha256 of uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl on PyPI (the Colab VM platform)
PINNED_UV_WHEEL_SHA256="fa8d26e08e34c29c0c4e820cf3181757086d547240b4f4d31ff1d8bd810ca946"
PINNED_PYTHON_VERSION="3.12.15"
# python-build-standalone release that uv 0.13.5 installs for PINNED_PYTHON_VERSION. uv embeds the
# archive URL and sha256 (crates/uv-python-managed/download-metadata.json at 0.13.5) and checks the
# sha256 on download (crates/uv-python-managed/src/downloads.rs:770-777), so pinning uv by hash pins
# the interpreter; the remote script refuses PYTHON_BUILD_MISMATCH if the install's BUILD differs.
PINNED_PYTHON_BUILD="20261021"
PINNED_PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu130"
PINNED_AI_TOOLKIT_REPO="https://github.com/ostris/ai-toolkit.git"
PINNED_AI_TOOLKIT_COMMIT="beb94824c51480a04d3c86c718603676fdef6938"
PINNED_OVERRIDE_SHA="649f42488bf2f520b93c3efa105724be236094d614480440d0df8a07c72e1e94"
PINNED_LOCAL_WHEELS_MANIFEST_SHA="579016010aae8e5549ffc5b4777f5899a6e410eafba680a61ab3841e758b6320"
PINNED_INSTALL_CLASSIFIER_SHA="ccccf077795148c14a7aa430e3575db45f097549a8b6a43aa149d78238513fd1"
PINNED_LAUNCH_GUARDS_SHA="61519c8a72dd16e91042368b232e48d60581a92807bb0d1333b5f845ffe90c24"
PINNED_REMOTE_RUNNER_SHA="2ff3499ce2075a3fe0eaa83c75585eb694401c04775bd36e30975eac19ce2456"
PINNED_COLAB_WINDOW_SHA="13bee0c4d6e1c4165632f97b6af3885740e8c404172de93b0293db0ccc2f1d77"
PINNED_LANE3_RUNG_SHA="957c6e327ecb1d92aa64d7e832de276c07539dc3d27a92f3c4d2c1bbe0b4c05e"
PINNED_BUNDLE_NOW_SHA="e986835500add747c1188f2819505348c977f9ab6ecd800bc46875329a183b1d"
PINNED_RUNG_YAML_SHA="11209a00067047f791d563ac1b083e22e7de6ae46dc2f240927d571c6cdb79d1"
PINNED_RUNG500_YAML_SHA="05936602be498b9c59d13329109521567cd507e52b4984bdb1a493253bab71d7"
PINNED_RUNG_DATASET_SHA="fa87eda99ceb4a900fa549041a187a75ebc2041e4e27ba7547b5822db43b701d"
PINNED_SELF_SHA="f106f8060a014eee75295aa4aea49919b334d9c5a999f391c346275a5adc559d"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_SH="${SCRIPT_DIR}/launch_lane3_stub.sh"
# shellcheck source=scripts/colab/colab_window.sh
source "${SCRIPT_DIR}/colab_window.sh"

# The remote script the kit uploads and runs on the VM. The live path and --emit-remote-script
# both write it through this one function, so an emitted file is byte for byte what a window runs.
lane3_write_remote_script() {
  local dest="$1"
  cat > "${dest}" << REMOTEEOF
#!/usr/bin/env bash
set -euo pipefail

# >>> sdlab-hf-token
# The GPU rung's HF read token reaches the VM only as a file the kit uploads
# (/content/lane3_hf_read_token; never --env or argv, which the colab CLI writes into its history).
# It is read into a shell variable and shredded here, before anything else runs, and handed to the
# model download step's environment alone. Logs are scrubbed of hf_ tokens before bundling.
LANE3_HF_READ_TOKEN=""
LANE3_HF_TOKEN_STAGED=0
if [ -f /content/lane3_hf_read_token ]; then
  LANE3_HF_READ_TOKEN="\$(cat /content/lane3_hf_read_token)"
  # Staged = the uploaded file was there and held something; set before the shred, from the file.
  [ -s /content/lane3_hf_read_token ] && LANE3_HF_TOKEN_STAGED=1
  shred -u /content/lane3_hf_read_token 2>/dev/null || rm -f /content/lane3_hf_read_token
  if [ -e /content/lane3_hf_read_token ]; then
    echo "REFUSED: HF_TOKEN_SHRED_FAILED: /content/lane3_hf_read_token is still on the VM" >&2
    exit 1
  fi
fi
unset HF_TOKEN_GGUF_READ HF_TOKEN HUGGING_FACE_HUB_TOKEN
# <<< sdlab-hf-token

# >>> sdlab-lane3-mode
# LANE3_MODE=install (the default, and the only mode this kit ever passes) runs the install path
# and stops after the import gate: the CPU stub's acceptance. LANE3_MODE=train also runs the
# training step, for a later GPU rung; it is refused here, before any install, on a VM with no
# NVIDIA GPU (TRAIN_REQUIRES_GPU) or with no model configured (TRAIN_MODEL_REQUIRED).
LANE3_MODE="\${LANE3_MODE:-install}"
case "\${LANE3_MODE}" in
  install)
    export CUDA_VISIBLE_DEVICES=""
    ;;
  train)
    if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L 2>/dev/null | grep -q '^GPU [0-9]'; then
      echo "REFUSED: TRAIN_REQUIRES_GPU: LANE3_MODE=train needs an NVIDIA GPU; nvidia-smi lists none on this VM" >&2
      exit 1
    fi
    if [ -z "\${LANE3_MODEL_NAME_OR_PATH:-}" ]; then
      echo "REFUSED: TRAIN_MODEL_REQUIRED: LANE3_MODE=train needs LANE3_MODEL_NAME_OR_PATH (the job's model:name_or_path)" >&2
      exit 1
    fi
    # A glob over the whole value (a newline included), not a line-wise grep.
    case "\${LANE3_MODEL_NAME_OR_PATH}" in
      *[!A-Za-z0-9._/:@-]*)
        echo "REFUSED: TRAIN_MODEL_REQUIRED: LANE3_MODEL_NAME_OR_PATH is not a plain model name or path" >&2
        exit 1
        ;;
    esac
    # The GPU rung's request values. None has a default: each missing one is its own refusal,
    # before any install and long before the model download.
    if ! [[ "\${LANE3_MODEL_REVISION:-}" =~ ^[0-9a-f]{40}\$ ]]; then
      echo "REFUSED: TRAIN_MODEL_REVISION_REQUIRED: LANE3_MODE=train needs LANE3_MODEL_REVISION, the model repo's 40-hex commit" >&2
      exit 1
    fi
    if ! [[ "\${LANE3_HOST_RAM_REQUIRED_GIB:-}" =~ ^[0-9]+(\.[0-9]+)?\$ ]] || [[ "\${LANE3_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?\$ ]]; then
      echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: LANE3_MODE=train needs LANE3_HOST_RAM_REQUIRED_GIB (MemAvailable the run needs, in GiB)" >&2
      exit 1
    fi
    if ! [[ "\${LANE3_DOWNLOAD_MAX_SECONDS:-}" =~ ^[1-9][0-9]*\$ ]]; then
      echo "REFUSED: DOWNLOAD_LIMIT_MISSING: LANE3_MODE=train needs LANE3_DOWNLOAD_MAX_SECONDS (the longest projected model download the request accepts)" >&2
      exit 1
    fi
    ;;
  *)
    echo "REFUSED: LANE3_MODE_INVALID: LANE3_MODE=\${LANE3_MODE}; expected install or train" >&2
    exit 1
    ;;
esac
# <<< sdlab-lane3-mode

# >>> sdlab-remote-dirs
# The kit uploads every file flat into /content (colab upload creates no remote directory).
# This block makes the run's directories and moves the uploaded wheels into /content/wheels,
# checking each directory and file exists afterwards.
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
sdlab_remote_mkdir /content/lane3_out /content/lane3_out/checkpoints /content/wheels
python3 -c 'import json, sys; [print(w["filename"]) for w in json.load(open(sys.argv[1], encoding="utf-8")).get("wheels", [])]' /content/lane3-local-wheels.json > /content/lane3_out/wheel-names.txt
while IFS= read -r wheel_fname; do
  [ -z "\${wheel_fname}" ] && continue
  if [ ! -f "/content/\${wheel_fname}" ]; then
    echo "REFUSED: LOCAL_WHEEL_MISSING on VM: /content/\${wheel_fname} was not uploaded" >&2
    exit 1
  fi
  if ! mv -f "/content/\${wheel_fname}" "/content/wheels/\${wheel_fname}" || [ ! -f "/content/wheels/\${wheel_fname}" ]; then
    echo "REFUSED: REMOTE_DIR_CREATE_FAILED: could not place \${wheel_fname} in /content/wheels" >&2
    exit 1
  fi
done < /content/lane3_out/wheel-names.txt
# <<< sdlab-remote-dirs

: "\${PINNED_UV_VERSION:?missing PINNED_UV_VERSION}"
: "\${PINNED_UV_WHEEL_SHA256:?missing PINNED_UV_WHEEL_SHA256}"
: "\${PINNED_PYTHON_VERSION:?missing PINNED_PYTHON_VERSION}"
: "\${PINNED_PYTHON_BUILD:?missing PINNED_PYTHON_BUILD}"
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
      if [ -f /sys/fs/cgroup/memory.stat ]; then
        grep -E '^(anon|shmem|file) ' /sys/fs/cgroup/memory.stat | sed 's/^/CGROUP_MEM_STAT: /' || true
      fi
      grep -E '^(MemTotal|MemAvailable|AnonPages|Shmem):' /proc/meminfo | sed 's/^/MEM: /' || true
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
  # Interpreter identity: uv's build tag, download URL, sys.version and the binary's sha256.
  /content/venv-lane3/bin/python - "\${PINNED_PYTHON_VERSION}" "\${PINNED_PYTHON_BUILD}" "\${UV_PYTHON_INSTALL_DIR}" /content/lane3_out/python_identity.json << 'PYIDEOF'
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
} 2>&1 | tee -a /content/lane3_out/setup.log
{
  unset UV_SYSTEM_PYTHON
  export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_312/install"
  export UV_NO_BUILD=1
  if [ "\${OVERRIDE_SHA}" != "\${PINNED_OVERRIDE_SHA}" ]; then
    echo "REFUSED: LOCK_HASH_MISMATCH: /content/lane3.lock sha256=\${OVERRIDE_SHA} expected=\${PINNED_OVERRIDE_SHA}" >&2
    exit 1
  fi

# >>> sdlab-local-wheels-lock
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
    # One requirement per line, ended with chr(10). This heredoc is nested in the kit's unquoted
    # REMOTEEOF heredoc, which turns a doubled backslash into one, so a backslash escape written
    # here reaches Python changed (sdlab-l3-stub-4: uv refused a literal backslash-n).
    lines.append(f"{pkg}=={ver} --hash=sha256:{exp_sha}" + chr(10))
Path("/content/lane3_out/local-wheels.lock").write_text("".join(lines), encoding="utf-8")
WHEELPYEOF
# <<< sdlab-local-wheels-lock

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

REQUIRED = ("sentencepiece", "torch", "torchaudio", "safetensors", "yaml", "oyaml", "PIL", "diffusers", "lycoris")
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

# >>> sdlab-train-or-skip
# The CPU stub (LANE3_MODE=install) ends its acceptance at the import gate above: it writes
# TRAIN_SKIPPED, records train=skipped_cpu_stub (never a trained result) and still bundles the
# install evidence. Only LANE3_MODE=train, which the mode gate admits on a GPU VM with a model, a
# pinned revision, a host-RAM threshold and a download limit, runs the GPU rung below.
CHECKPOINT_PATH=""
if [ "\${LANE3_MODE:-install}" != "train" ]; then
  LANE3_TRAIN_STATE="skipped_cpu_stub"
  echo "TRAIN_SKIPPED: cpu stub; training needs a GPU rung" | tee -a /content/lane3_out/setup.log
else
  LANE3_TRAIN_STATE="trained"
# >>> sdlab-lane3-train
# The GPU rung, in order: guards (GPU smoke, disk, host RAM, /dev/shm record) before any download;
# the model snapshot at the pinned revision (unauthenticated, with the DOWNLOAD_TOO_SLOW probe);
# the fixture dataset (sha256-checked); the job rendered from the committed rung YAML with the
# local snapshot path; ai-toolkit's run.py with the hub offline, so nothing unpinned is fetched;
# and a copy-off watcher that puts each saved checkpoint and sample into lane3_out/rung_outputs
# with a manifest line (sha256) as it appears. Any failure still bundles lane3_out (EXIT trap), so
# the kit can download what was saved. Copy-off reaches only the VM's bundle directory: the CLI
# downloads at the end, so a VM that is lost mid-run loses its outputs (a Drive mount would be
# needed for true mid-run copy-off, and is left out).
: "\${LANE3_DISK_REQUIRED_GIB:?missing LANE3_DISK_REQUIRED_GIB}"
: "\${LANE3_GPU_SMOKE_SECONDS:?missing LANE3_GPU_SMOKE_SECONDS}"
: "\${LANE3_DOWNLOAD_PROBE_SECONDS:?missing LANE3_DOWNLOAD_PROBE_SECONDS}"
: "\${LANE3_DOWNLOAD_PROBE_BYTES:?missing LANE3_DOWNLOAD_PROBE_BYTES}"
LANE3_PY="/content/venv-lane3/bin/python"
LANE3_HF_HOME="/content/hf_home"
LANE3_TRAINING_FOLDER="/content/lane3_train"
LANE3_DATASET_DIR="/content/lane3_dataset"
lane3_train_on_exit() {
  local rc=\$?
  trap - EXIT
  kill "\${VITALS_PID:-}" 2>/dev/null || true
  if [ "\${rc}" -ne 0 ] && [ ! -f /content/lane3_stub_bundle.tar.gz ]; then
    if [ -d "\${LANE3_TRAINING_FOLDER}" ] && [ ! -f /content/lane3_out/training_folder_manifest.json ]; then
      "\${LANE3_PY}" /content/lane3_rung.py write-train-manifest --watch "\${LANE3_TRAINING_FOLDER}" \
        --out /content/lane3_out/training_folder_manifest.json || true
      "\${LANE3_PY}" /content/lane3_rung.py copy-off --final-only --watch "\${LANE3_TRAINING_FOLDER}" \
        --bundle /content/lane3_out/rung_outputs --manifest /content/lane3_out/rung_outputs/manifest.jsonl || true
    fi
    "\${LANE3_PY}" /content/lane3_rung.py finish --lane3-out /content/lane3_out --failed-rc "\${rc}" || true
    while IFS= read -r -d '' f; do
      "\${LANE3_PY}" /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
    done < <(find /content/lane3_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" -o -name "*.txt" \) -print0 2>/dev/null || true)
    rm -f /content/lane3_stub_bundle.tar.gz.tmp
    if tar -czf /content/lane3_stub_bundle.tar.gz.tmp -C /content/lane3_out .; then
      mv -f /content/lane3_stub_bundle.tar.gz.tmp /content/lane3_stub_bundle.tar.gz
      echo "TRAIN_BUNDLE_AFTER_FAILURE rc=\${rc} /content/lane3_stub_bundle.tar.gz"
    else
      rm -f /content/lane3_stub_bundle.tar.gz.tmp
    fi
  fi
  exit "\${rc}"
}
trap lane3_train_on_exit EXIT
mkdir -p "\${LANE3_HF_HOME}" "\${LANE3_TRAINING_FOLDER}" /content/lane3_out/rung_outputs

"\${LANE3_PY}" /content/lane3_rung.py guards \
  --hf-home "\${LANE3_HF_HOME}" --training-folder "\${LANE3_TRAINING_FOLDER}" \
  --disk-required-gib "\${LANE3_DISK_REQUIRED_GIB}" --smoke-seconds "\${LANE3_GPU_SMOKE_SECONDS}" --ram-required-gib "\${LANE3_HOST_RAM_REQUIRED_GIB:-}" \
  --meminfo /proc/meminfo --shm /dev/shm --out /content/lane3_out/train_guards.json 2>&1 | tee -a /content/lane3_out/setup.log

# >>> sdlab-lane3-download
# The token reaches the download step's environment only when one was staged; otherwise the
# variable is not set at all, so the step records token_used false.
lane3_download() {
  "\${LANE3_PY}" /content/lane3_rung.py download \
    --repo "\${LANE3_MODEL_NAME_OR_PATH}" --revision "\${LANE3_MODEL_REVISION:-}" --hf-home "\${LANE3_HF_HOME}" \
    --max-seconds "\${LANE3_DOWNLOAD_MAX_SECONDS:-}" --probe-seconds "\${LANE3_DOWNLOAD_PROBE_SECONDS}" \
    --probe-bytes "\${LANE3_DOWNLOAD_PROBE_BYTES}" --log /content/lane3_out/model_download.log \
    --out /content/lane3_out/model_download.json
}
if [ "\${LANE3_HF_TOKEN_STAGED:-0}" = "1" ]; then
  HF_TOKEN_GGUF_READ="\${LANE3_HF_READ_TOKEN}" lane3_download 2>&1 | tee -a /content/lane3_out/setup.log
else
  lane3_download 2>&1 | tee -a /content/lane3_out/setup.log
fi
# <<< sdlab-lane3-download
LANE3_HF_READ_TOKEN=""
LANE3_MODEL_PATH="\$("\${LANE3_PY}" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["snapshot_path"])' /content/lane3_out/model_download.json)"

LANE3_DS_ARGS=(--manifest /content/rung-dataset.json --dest "\${LANE3_DATASET_DIR}")
if [ -n "\${LANE3_DATASET_MANIFEST_SHA256:-}" ]; then
  LANE3_DS_ARGS+=(--manifest-sha "\${LANE3_DATASET_MANIFEST_SHA256}")
fi
if [ -n "\${LANE3_DATASET_ARCHIVE_SHA256:-}" ] || [ -f /content/lane3_dataset.tar ]; then
  LANE3_DS_ARGS+=(--archive /content/lane3_dataset.tar --archive-sha "\${LANE3_DATASET_ARCHIVE_SHA256:-}" --unlink-archive)
else
  LANE3_DS_ARGS+=(--src /content)
fi
"\${LANE3_PY}" /content/lane3_rung.py dataset "\${LANE3_DS_ARGS[@]}" 2>&1 | tee -a /content/lane3_out/setup.log
LANE3_RENDER_ARGS=(--template /content/rung-qwen-image.yaml --out /content/lane3_out/rung_job.yaml
  --training-folder "\${LANE3_TRAINING_FOLDER}" --dataset-dir "\${LANE3_DATASET_DIR}" --model-path "\${LANE3_MODEL_PATH}")
if [ -n "\${LANE3_JOB_SHA256:-}" ]; then
  LANE3_RENDER_ARGS+=(--template-sha "\${LANE3_JOB_SHA256}")
fi
"\${LANE3_PY}" /content/lane3_rung.py render-job "\${LANE3_RENDER_ARGS[@]}" 2>&1 | tee -a /content/lane3_out/setup.log
if [ -n "\${LANE3_PROJECTED_OUTPUT_BYTES:-}" ]; then
  "\${LANE3_PY}" /content/lane3_rung.py check-output-disk --training-folder "\${LANE3_TRAINING_FOLDER}" \
    --projected-bytes "\${LANE3_PROJECTED_OUTPUT_BYTES}" --out /content/lane3_out/output_disk_check.json 2>&1 | tee -a /content/lane3_out/setup.log
fi

echo "run" > /content/lane3_out/phase.txt
# >>> sdlab-train-step
set +e
HF_HOME="\${LANE3_HF_HOME}" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
  /content/venv-lane3/bin/python /content/ai-toolkit/run.py /content/lane3_out/rung_job.yaml > /content/lane3_out/train.log 2>&1 &
TRAIN_PID=\$!
"\${LANE3_PY}" /content/lane3_rung.py copy-off --watch "\${LANE3_TRAINING_FOLDER}" \
  --bundle /content/lane3_out/rung_outputs --manifest /content/lane3_out/rung_outputs/manifest.jsonl \
  --pid "\${TRAIN_PID}" --train-log /content/lane3_out/train.log &
COPY_PID=\$!
wait "\${TRAIN_PID}"
TRAIN_RC=\$?
echo "setup" > /content/lane3_out/phase.txt
wait "\${COPY_PID}"
# Record the complete manifest of the training folder before the final sweep so the rig can verify
# every file (path, bytes, sha256) arrived in the downloaded bundle.
"\${LANE3_PY}" /content/lane3_rung.py write-train-manifest --watch "\${LANE3_TRAINING_FOLDER}" \
  --out /content/lane3_out/training_folder_manifest.json 2>&1 | tee -a /content/lane3_out/setup.log
WL_MANIFEST_RC=\$?
# A final sweep of the training folder, in its own process: a copy-off watcher that died mid-run
# leaves nothing behind.
"\${LANE3_PY}" /content/lane3_rung.py copy-off --final-only --watch "\${LANE3_TRAINING_FOLDER}" \
  --bundle /content/lane3_out/rung_outputs --manifest /content/lane3_out/rung_outputs/manifest.jsonl
FINAL_COPY_RC=\$?
set -e
if [ "\${TRAIN_RC}" -ne 0 ]; then
  echo "--- last 40 lines of train.log ---"
  tail -n 40 /content/lane3_out/train.log || true
  echo "REFUSED: TRAIN_FAILED: ai-toolkit run.py exited \${TRAIN_RC}; see lane3_out/train.log" >&2
  exit 1
fi
if [ "\${WL_MANIFEST_RC}" -ne 0 ] || [ "\${FINAL_COPY_RC}" -ne 0 ]; then
  exit 1
fi
# <<< sdlab-train-step

  # Only a complete checkpoint counts: copy-off marks a .safetensors whose header does not parse or
  # whose size does not match its data offsets as partial in the manifest.
  FOUND_CKPT="\$("\${LANE3_PY}" /content/lane3_rung.py checkpoint --bundle /content/lane3_out/rung_outputs \
    --manifest /content/lane3_out/rung_outputs/manifest.jsonl || true)"
  if [ -z "\${FOUND_CKPT}" ]; then
    echo "REFUSED: TRAIN_CHECKPOINT_MISSING: no complete .safetensors checkpoint was copied off to lane3_out/rung_outputs" >&2
    exit 1
  fi
  CHECKPOINT_PATH="\${FOUND_CKPT}"
  if ! grep -Eq '"path": "([^"_][^"/]*/)*[^"/]+\.(png|jpg|jpeg|webp)"' /content/lane3_out/rung_outputs/manifest.jsonl; then
    echo "REFUSED: TRAIN_SAMPLE_MISSING: no sample image was copied off to lane3_out/rung_outputs" >&2
    exit 1
  fi
  "\${LANE3_PY}" /content/lane3_rung.py finish --lane3-out /content/lane3_out
# <<< sdlab-lane3-train
fi
# <<< sdlab-train-or-skip

# >>> sdlab-lane3-window
/content/venv-lane3/bin/python - "\${PINNED_AI_TOOLKIT_COMMIT}" "\${OVERRIDE_SHA}" "\${LANE3_MODE:-install}" "\${LANE3_TRAIN_STATE}" "\${CHECKPOINT_PATH}" << 'WINPYEOF'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ai_commit = sys.argv[1]
override_sha = sys.argv[2]
lane3_mode = sys.argv[3]
train_state = sys.argv[4]
ckpt_path = sys.argv[5] or None
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
    "lane3_mode": lane3_mode,
    "train": train_state,
    "checkpoint_path": ckpt_path,
}
# Train mode: the guards' measurements, the model download record and the copied-off outputs.
facts_p = Path("/content/lane3_out/train_facts.json")
if facts_p.is_file():
    rec.update(json.loads(facts_p.read_text(encoding="utf-8")))
Path("/content/lane3_out/vm_window.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
print("WINDOW_JSON " + json.dumps(rec), flush=True)
WINPYEOF

if [ "\${LANE3_MODE:-install}" = "train" ]; then
  /content/venv-lane3/bin/python /content/lane3_rung.py check-bundle-disk \
    --bundle-dir /content/lane3_out --out /content/lane3_out/bundle_disk_check.json 2>&1 | tee -a /content/lane3_out/setup.log
fi
while IFS= read -r -d '' f; do
  /content/venv-lane3/bin/python /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
done < <(find /content/lane3_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" -o -name "*.txt" \) -print0 2>/dev/null || true)
rm -f /content/lane3_stub_bundle.tar.gz.tmp
tar -czf /content/lane3_stub_bundle.tar.gz.tmp -C /content/lane3_out .
mv -f /content/lane3_stub_bundle.tar.gz.tmp /content/lane3_stub_bundle.tar.gz
# <<< sdlab-lane3-window
REMOTEEOF
}

# The environment the kit hands the remote script through colab exec --env, one KEY=VALUE a line;
# $1 is the lock sha256 the remote script must find.
lane3_remote_env() {
  printf '%s\n' \
    "PINNED_UV_VERSION=${PINNED_UV_VERSION}" \
    "PINNED_UV_WHEEL_SHA256=${PINNED_UV_WHEEL_SHA256}" \
    "PINNED_PYTHON_VERSION=${PINNED_PYTHON_VERSION}" \
    "PINNED_PYTHON_BUILD=${PINNED_PYTHON_BUILD}" \
    "PINNED_PYTORCH_INDEX_URL=${PINNED_PYTORCH_INDEX_URL}" \
    "PINNED_AI_TOOLKIT_REPO=${PINNED_AI_TOOLKIT_REPO}" \
    "PINNED_AI_TOOLKIT_COMMIT=${PINNED_AI_TOOLKIT_COMMIT}" \
    "PINNED_OVERRIDE_SHA=$1"
  if [ "${TRAIN_REQUESTED:-0}" = "1" ]; then
    printf '%s\n' \
      "LANE3_MODE=train" \
      "LANE3_MODEL_NAME_OR_PATH=${TRAIN_MODEL}" \
      "LANE3_MODEL_REVISION=${TRAIN_MODEL_REVISION}" \
      "LANE3_HOST_RAM_REQUIRED_GIB=${TRAIN_HOST_RAM_REQUIRED_GIB}" \
      "LANE3_DOWNLOAD_MAX_SECONDS=${TRAIN_DOWNLOAD_MAX_SECONDS}" \
      "LANE3_DISK_REQUIRED_GIB=${LANE3_DISK_REQUIRED_GIB}" \
      "LANE3_GPU_SMOKE_SECONDS=${LANE3_GPU_SMOKE_SECONDS}" \
      "LANE3_DOWNLOAD_PROBE_SECONDS=${LANE3_DOWNLOAD_PROBE_SECONDS}" \
      "LANE3_DOWNLOAD_PROBE_BYTES=${LANE3_DOWNLOAD_PROBE_BYTES}"
    if [ -n "${ACTIVE_JOB_SHA:-}" ]; then
      printf '%s\n' "LANE3_JOB_SHA256=${ACTIVE_JOB_SHA}"
    fi
    if [ -n "${ACTIVE_DATASET_SHA:-}" ]; then
      printf '%s\n' "LANE3_DATASET_MANIFEST_SHA256=${ACTIVE_DATASET_SHA}"
    fi
    if [ -n "${DATASET_ARCHIVE_SHA:-}" ]; then
      printf '%s\n' "LANE3_DATASET_ARCHIVE_SHA256=${DATASET_ARCHIVE_SHA}"
    fi
    if [ -n "${PROJECTED_OUTPUT_BYTES:-}" ]; then
      printf '%s\n' "LANE3_PROJECTED_OUTPUT_BYTES=${PROJECTED_OUTPUT_BYTES}"
    fi
  fi
}

# lane3_check_train_request: the GPU rung's request values, each a named refusal when missing or
# malformed (no defaults), checked before anything reads the disk and before any colab call.
lane3_check_train_request() {
  if [ -z "${TRAIN_MODEL}" ]; then
    echo "REFUSED: TRAIN_MODEL_REQUIRED: --train needs --model <hf repo id> (LANE3_MODEL_NAME_OR_PATH)" >&2
    return 2
  fi
  if ! [[ "${TRAIN_MODEL}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "REFUSED: TRAIN_MODEL_REQUIRED: --model ${TRAIN_MODEL} is not a Hugging Face repo id" >&2
    return 2
  fi
  if ! [[ "${TRAIN_MODEL_REVISION}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "REFUSED: TRAIN_MODEL_REVISION_REQUIRED: --train needs --model-revision <40-hex commit of ${TRAIN_MODEL}>" >&2
    return 2
  fi
  if ! [[ "${TRAIN_HOST_RAM_REQUIRED_GIB}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${TRAIN_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: --train needs --host-ram-required-gib <GiB> (walk (a)'s measured peak host RSS + 20%)" >&2
    return 2
  fi
  if ! [[ "${TRAIN_DOWNLOAD_MAX_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: DOWNLOAD_LIMIT_MISSING: --train needs --download-max-seconds <s> (longest projected model download accepted)" >&2
    return 2
  fi
}

# Lane 3 GPU rung constants (Publisher's decisions, 2026-11-06): free disk on the HF cache's and the
# training folder's filesystems before the ~58 GB download, and the download probe window: the
# first 60 s or 2 GiB of new bytes, whichever comes first; and the GPU smoke matmul's ~5 s.
LANE3_DISK_REQUIRED_GIB="75"
LANE3_VM_DISK_BUDGET_GIB="75"
LANE3_GPU_SMOKE_SECONDS="5"
LANE3_DOWNLOAD_PROBE_SECONDS="60"
LANE3_DOWNLOAD_PROBE_BYTES="2147483648"
# The window's wall must cover, after the grace: the download limit the request sets, the setup
# (uv, CPython, the 158-pin lock, ai-toolkit; 900 s allowed), and either the fixed 1800 s rung
# allowance (`--rung-job`) or `steps * seconds_per_step + fetch` (`--job`).
LANE3_INSTALL_ALLOWANCE_S="900"
LANE3_TRAIN_ALLOWANCE_S="1800"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-lane3-stub-$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR=""
WHEEL_DIR="${SDLAB_WHEEL_DIR:-}"
CAP="${CAP:-0.15}"
WALL_S="${WALL_S:-900}"
GRACE_S="${GRACE_S:-60}"
MARGIN="${MARGIN:-0.01}"
EMIT_REMOTE_SCRIPT=""
EMIT_REQUESTED=0
TRAIN_REQUESTED=0
WALL_SET=0
CAP_SET=0
TRAIN_MODEL=""
TRAIN_MODEL_REVISION=""
TRAIN_HOST_RAM_REQUIRED_GIB=""
TRAIN_DOWNLOAD_MAX_SECONDS=""
TRAIN_MAX_RATE=""
SHAPE=""
DATASET_DIR=""
RUNG_JOB=""
JOB_YAML=""
JOB_SHA=""
DATASET_MANIFEST=""
DATASET_MANIFEST_SHA=""
MIN_RUNTIME_S=""
DOWNLOAD_TIMEOUT_S_ARG=""
UPLOAD_TIMEOUT_S_ARG=""
UPLOAD_REASSEMBLE_TIMEOUT_S_ARG=""
UPLOAD_REASSEMBLE_MB_S_ARG=""
UPLOAD_CHUNK_BYTES_ARG=""
DOWNLOAD_CHUNK_BYTES_ARG=""
DOWNLOAD_FLOOR_MB_S_ARG=""
UPLOAD_FLOOR_MB_S_ARG=""
SECONDS_PER_STEP_ARG=""
CHECKPOINT_SIZE_BYTES_ARG=""
OPTIMIZER_SIZE_BYTES_ARG=""
OPTIMIZER_SIZE_SOURCE_ARG=""
SAMPLES_AND_LOGS_BYTES_ARG=""
AUXILIARY_KEEP_ALL_BYTES_ARG=""
OUTPUT_OVERHEAD_FACTOR_ARG=""
EXPECTED_MODEL_BYTES_ARG=""
VM_DISK_BUDGET_GIB_ARG=""
PROJECTED_OUTPUT_BYTES=""
DRY_RUN=0
SESSION_ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --emit-remote-script) EMIT_REQUESTED=1; EMIT_REMOTE_SCRIPT="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --card) SESSION_ARGS+=("$1"); CARD="$2"; shift 2 ;;
    --session) SESSION_ARGS+=("$1"); SESSION="$2"; shift 2 ;;
    --out-dir) SESSION_ARGS+=("$1"); OUT_DIR="$2"; shift 2 ;;
    --wheel-dir) SESSION_ARGS+=("$1"); WHEEL_DIR="$2"; shift 2 ;;
    --cap) SESSION_ARGS+=("$1"); CAP="$2"; CAP_SET=1; shift 2 ;;
    --wall-s) SESSION_ARGS+=("$1"); WALL_S="$2"; WALL_SET=1; shift 2 ;;
    --grace-s) SESSION_ARGS+=("$1"); GRACE_S="$2"; shift 2 ;;
    --margin) SESSION_ARGS+=("$1"); MARGIN="$2"; shift 2 ;;
    --train) TRAIN_REQUESTED=1; shift ;;
    --max-rate) SESSION_ARGS+=("$1"); TRAIN_MAX_RATE="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --shape) SESSION_ARGS+=("$1"); SHAPE="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --min-runtime-s) SESSION_ARGS+=("$1"); MIN_RUNTIME_S="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-timeout-s) SESSION_ARGS+=("$1"); DOWNLOAD_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-timeout-s) SESSION_ARGS+=("$1"); UPLOAD_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-reassemble-timeout-s) SESSION_ARGS+=("$1"); UPLOAD_REASSEMBLE_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-reassemble-mb-s) SESSION_ARGS+=("$1"); UPLOAD_REASSEMBLE_MB_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-chunk-bytes) SESSION_ARGS+=("$1"); UPLOAD_CHUNK_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-chunk-bytes) SESSION_ARGS+=("$1"); DOWNLOAD_CHUNK_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-floor-mb-s) SESSION_ARGS+=("$1"); DOWNLOAD_FLOOR_MB_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-floor-mb-s) SESSION_ARGS+=("$1"); UPLOAD_FLOOR_MB_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --seconds-per-step) SESSION_ARGS+=("$1"); SECONDS_PER_STEP_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --checkpoint-size-bytes) SESSION_ARGS+=("$1"); CHECKPOINT_SIZE_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --optimizer-size-bytes) SESSION_ARGS+=("$1"); OPTIMIZER_SIZE_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --optimizer-size-source) SESSION_ARGS+=("$1"); OPTIMIZER_SIZE_SOURCE_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --samples-and-logs-bytes) SESSION_ARGS+=("$1"); SAMPLES_AND_LOGS_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --auxiliary-keep-all-bytes) SESSION_ARGS+=("$1"); AUXILIARY_KEEP_ALL_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --output-overhead-factor) SESSION_ARGS+=("$1"); OUTPUT_OVERHEAD_FACTOR_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --expected-model-bytes) SESSION_ARGS+=("$1"); EXPECTED_MODEL_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --vm-disk-budget-gib) SESSION_ARGS+=("$1"); VM_DISK_BUDGET_GIB_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --dry) SESSION_ARGS+=("$1"); DRY_RUN=1; shift ;;
    --model) TRAIN_MODEL="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --model-revision) TRAIN_MODEL_REVISION="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --host-ram-required-gib) TRAIN_HOST_RAM_REQUIRED_GIB="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-max-seconds) TRAIN_DOWNLOAD_MAX_SECONDS="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --dataset-dir) SESSION_ARGS+=("$1"); DATASET_DIR="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --rung-job) SESSION_ARGS+=("$1"); RUNG_JOB="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --job) SESSION_ARGS+=("$1"); JOB_YAML="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --job-sha) SESSION_ARGS+=("$1"); JOB_SHA="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --dataset-manifest) SESSION_ARGS+=("$1"); DATASET_MANIFEST="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --dataset-manifest-sha) SESSION_ARGS+=("$1"); DATASET_MANIFEST_SHA="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    *)
      echo "REFUSED: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ "${TRAIN_REQUESTED}" != "1" ] && [ -n "${TRAIN_MODEL}${TRAIN_MODEL_REVISION}${TRAIN_HOST_RAM_REQUIRED_GIB}${TRAIN_DOWNLOAD_MAX_SECONDS}${DATASET_DIR}${RUNG_JOB}${JOB_YAML}${JOB_SHA}${DATASET_MANIFEST}${DATASET_MANIFEST_SHA}${DOWNLOAD_FLOOR_MB_S_ARG}${UPLOAD_FLOOR_MB_S_ARG}${SECONDS_PER_STEP_ARG}${CHECKPOINT_SIZE_BYTES_ARG}${OPTIMIZER_SIZE_BYTES_ARG}${OPTIMIZER_SIZE_SOURCE_ARG}${SAMPLES_AND_LOGS_BYTES_ARG}${AUXILIARY_KEEP_ALL_BYTES_ARG}${OUTPUT_OVERHEAD_FACTOR_ARG}${EXPECTED_MODEL_BYTES_ARG}${VM_DISK_BUDGET_GIB_ARG}" ]; then
  echo "REFUSED: TRAIN_OPTION_WITHOUT_TRAIN: --model, --model-revision, --host-ram-required-gib, --download-max-seconds, --dataset-dir, --rung-job, --job, --job-sha, --dataset-manifest, --dataset-manifest-sha and the training projection flags need --train" >&2
  exit 2
fi

# --emit-remote-script <file>: write the remote script exactly as a window would upload it, plus
# <file>.env with the KEY=VALUE environment the kit passes it, then exit. It makes no colab call,
# runs no pre-flight and opens nothing, so it is refused beside any option that belongs to a window.
# With --train and the request values (--model, --model-revision, --host-ram-required-gib,
# --download-max-seconds) the .env carries the train-mode variables too, checked as a window would.
if [ "${EMIT_REQUESTED}" = "1" ]; then
  if [ "${#SESSION_ARGS[@]}" -gt 0 ]; then
    echo "REFUSED: EMIT_REMOTE_SCRIPT_EXCLUSIVE: --emit-remote-script opens no window; drop ${SESSION_ARGS[*]}" >&2
    exit 2
  fi
  if [ -z "${EMIT_REMOTE_SCRIPT}" ]; then
    echo "REFUSED: EMIT_REMOTE_SCRIPT_PATH_REQUIRED: pass --emit-remote-script <file>" >&2
    exit 2
  fi
  if [ "${TRAIN_REQUESTED}" = "1" ]; then
    lane3_check_train_request || exit 2
  fi
  lane3_write_remote_script "${EMIT_REMOTE_SCRIPT}"
  lane3_remote_env "${PINNED_OVERRIDE_SHA}" > "${EMIT_REMOTE_SCRIPT}.env"
  echo "REMOTE_SCRIPT_EMITTED ${EMIT_REMOTE_SCRIPT} env=${EMIT_REMOTE_SCRIPT}.env"
  exit 0
fi

lane3_translate_wsl_path() {
  local raw="$1"
  if [[ "${raw}" =~ ^([A-Za-z]):/(.*)$ ]] && [[ -d "/mnt/${BASH_REMATCH[1],,}" ]]; then
    local drive_lower="${BASH_REMATCH[1],,}"
    local rest_path="${BASH_REMATCH[2]}"
    if [[ ! -e "${raw}" ]] && [[ -e "/mnt/${drive_lower}/${rest_path}" ]]; then
      printf '%s' "/mnt/${drive_lower}/${rest_path}"
      return 0
    fi
  fi
  printf '%s' "${raw}"
}

# lane3_upload_max_bytes <local-wheels-json> <wheel-dir> <dataset-archive-or-dir> [other files...]: the size in
# bytes of the largest file this window uploads (a directory counts as the sum of its files, a LOWER bound of
# the dataset tar: tar headers and padding add to it), so the cap gate can price the VM-side chunked-upload reassembly exec (COLAB_UPLOAD_MAX_BYTES).
lane3_upload_max_bytes() {
  "${PY_BIN}" -c '
import json, os, sys
wheels_json, wheel_dir, dataset = sys.argv[1:4]
sizes = [0]

def add_file(path):
    try:
        sizes.append(os.path.getsize(path))
    except OSError:
        pass

try:
    with open(wheels_json, encoding="utf-8") as fh:
        for w in json.load(fh).get("wheels", []):
            if wheel_dir:
                add_file(os.path.join(wheel_dir, w["filename"]))
except (OSError, ValueError, KeyError, TypeError):
    pass
if dataset and os.path.isdir(dataset):
    total = 0
    for root, _dirs, files in os.walk(dataset):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    sizes.append(total)
elif dataset:
    add_file(dataset)
for extra in sys.argv[4:]:
    if extra:
        add_file(extra)
print(max(sizes))
' "$@" | tr -d '\r'
}

colab_configure_download_timeout "${DOWNLOAD_TIMEOUT_S_ARG}" || exit 2
colab_configure_upload_timeout "${UPLOAD_TIMEOUT_S_ARG}" || exit 2
colab_configure_upload_reassemble_timeout "${UPLOAD_REASSEMBLE_TIMEOUT_S_ARG}" "${UPLOAD_REASSEMBLE_MB_S_ARG}" || exit 2
colab_configure_upload_chunk_bytes "${UPLOAD_CHUNK_BYTES_ARG}" || exit 2
colab_configure_download_chunk_bytes "${DOWNLOAD_CHUNK_BYTES_ARG}" || exit 2

if [ "${DRY_RUN}" = "1" ]; then
  if [ -n "${JOB_YAML}" ] && [ "${COLAB_DOWNLOAD_TIMEOUT_SOURCE}" = "default" ] && [ -z "${DOWNLOAD_FLOOR_MB_S_ARG}" ]; then
    echo "REFUSED: DOWNLOAD_TIMEOUT_REQUIRED: --job must not use the 300 s default download timeout; pass --download-timeout-s <s> or --download-floor-mb-s <MB/s>" >&2
    exit 2
  fi
  DRY_TEST_MODE=0
  if colab_fake_test_mode_active; then
    DRY_TEST_MODE=1
  fi
  PY_BIN="$(colab_resolve_python)"
  GUARDS_PY="${SCRIPT_DIR}/launch_guards.py"
  if [ "${TRAIN_REQUESTED}" = "1" ]; then
    DRY_ACTIVE_JOB=""
    DRY_IS_REAL="0"
    if [ "${RUNG_JOB}" = "500" ]; then
      DRY_ACTIVE_JOB="${SCRIPT_DIR}/lane3/rung-qwen-image-500.yaml"
    elif [ "${RUNG_JOB}" = "20" ]; then
      DRY_ACTIVE_JOB="${SCRIPT_DIR}/lane3/rung-qwen-image.yaml"
    elif [ -n "${JOB_YAML}" ]; then
      DRY_ACTIVE_JOB="$(lane3_translate_wsl_path "${JOB_YAML}")"
      DRY_IS_REAL="1"
    fi
    if [ -n "${DRY_ACTIVE_JOB}" ] && [ -f "${DRY_ACTIVE_JOB}" ]; then
      DRY_EFF_DL_CHUNK="${COLAB_DOWNLOAD_CHUNK_BYTES}"
      if [ "${DRY_TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_DOWNLOAD_CHUNK_BYTES:-}" ]; then
        DRY_EFF_DL_CHUNK="${SDLAB_TEST_DOWNLOAD_CHUNK_BYTES}"
      fi
      DRY_EXPLICIT_DL=""
      if [ "${COLAB_DOWNLOAD_TIMEOUT_SOURCE}" != "default" ]; then
        DRY_EXPLICIT_DL="${COLAB_DOWNLOAD_TIMEOUT_S}"
      fi
      DRY_PLAN_ARGS=(
        --job-yaml "${DRY_ACTIVE_JOB}"
        --is-real-job "${DRY_IS_REAL}"
        --explicit-download-timeout-s "${DRY_EXPLICIT_DL}"
        --download-timeout-source "${COLAB_DOWNLOAD_TIMEOUT_SOURCE}"
        --default-download-timeout-s "${COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT}"
        --download-chunk-bytes "${DRY_EFF_DL_CHUNK}"
      )
      [ -n "${DOWNLOAD_FLOOR_MB_S_ARG}" ] && DRY_PLAN_ARGS+=(--download-floor-mb-s "${DOWNLOAD_FLOOR_MB_S_ARG}")
      [ -n "${CHECKPOINT_SIZE_BYTES_ARG}" ] && DRY_PLAN_ARGS+=(--checkpoint-size-bytes "${CHECKPOINT_SIZE_BYTES_ARG}")
      [ -n "${OPTIMIZER_SIZE_BYTES_ARG}" ] && DRY_PLAN_ARGS+=(--optimizer-size-bytes "${OPTIMIZER_SIZE_BYTES_ARG}")
      [ -n "${SAMPLES_AND_LOGS_BYTES_ARG}" ] && DRY_PLAN_ARGS+=(--samples-and-logs-bytes "${SAMPLES_AND_LOGS_BYTES_ARG}")
      [ -n "${AUXILIARY_KEEP_ALL_BYTES_ARG}" ] && DRY_PLAN_ARGS+=(--auxiliary-keep-all-bytes "${AUXILIARY_KEEP_ALL_BYTES_ARG}")
      DRY_DL_RES=""
      if ! DRY_DL_RES="$("${PY_BIN}" "${SCRIPT_DIR}/lane3_rung.py" dry-download-bounds "${DRY_PLAN_ARGS[@]}" | tr -d '\r')"; then
        exit 2
      fi
      IFS=$'\t' read -r DRY_DL_S DRY_DL_SRC DRY_DL_PARTS <<< "${DRY_DL_RES}"
      colab_configure_download_timeout "${DRY_DL_S}" "${DRY_DL_SRC}" "${DRY_DL_PARTS}" || exit 2
    fi
  fi
  colab_apply_test_cleanup_overrides "${DRY_TEST_MODE}"
  DRY_UPLOAD_DATASET=""
  if [ "${TRAIN_REQUESTED}" = "1" ] && [ -n "${DATASET_DIR}" ]; then
    DRY_UPLOAD_DATASET="$(lane3_translate_wsl_path "${DATASET_DIR}")"
  fi
  COLAB_UPLOAD_MAX_BYTES="$(lane3_upload_max_bytes "${SCRIPT_DIR}/locks/lane3-local-wheels.json" "$(lane3_translate_wsl_path "${WHEEL_DIR}")" "${DRY_UPLOAD_DATASET}" "${SCRIPT_DIR}/lane3_rung.py" "${SCRIPT_DIR}/launch_guards.py")"
  export COLAB_UPLOAD_MAX_BYTES
  colab_dry_cap_budget "${PY_BIN}" "${GUARDS_PY}" "train" "${CARD}" "${CAP}" "${MARGIN}" "${TRAIN_MAX_RATE}" "${RATE_CCU_PER_HOUR:-0.26}" "${MIN_RUNTIME_S}"
  exit $?
fi

# --train runs the GPU rung (LANE3_MODE=train): a GPU card, the model repo and its pinned revision,
# the host-RAM threshold, the download limit and the fixture dataset directory are all required,
# each a named refusal, before any check that reads the disk and before any colab call. Without
# --train the kit is the CPU install-path stub and passes no LANE3_MODE.
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  if colab_card_is_cpu "${CARD}"; then
    echo "REFUSED: TRAIN_REQUIRES_GPU: --train on card ${CARD}; training needs a GPU rung" >&2
    exit 2
  fi
  lane3_check_train_request || exit 2
  # The rung downloads with the read token the request puts in HF_TOKEN_GGUF_READ (the colab skill
  # forwards it through WSLENV); there is no anonymous fallback, so the receipt always says which
  # path ran (hf_token_used). The value is never written to a file or a log.
  if [ -z "${HF_TOKEN_GGUF_READ:-}" ] || [[ "${HF_TOKEN_GGUF_READ}" =~ [[:space:]] ]]; then
    echo "REFUSED: HF_READ_TOKEN_MISSING: --train needs a Hugging Face read token in HF_TOKEN_GGUF_READ (environment only)" >&2
    exit 2
  fi
  if [ "${WALL_SET}" != "1" ]; then
    echo "REFUSED: TRAIN_WALL_REQUIRED: --train needs an explicit --wall-s (the CPU stub's default does not apply)" >&2
    exit 2
  fi
  if [ "${CAP_SET}" != "1" ]; then
    echo "REFUSED: TRAIN_CAP_REQUIRED: --train needs an explicit --cap (the CPU stub's default does not apply)" >&2
    exit 2
  fi
  if ! [[ "${WALL_S}" =~ ^[0-9]+$ ]] || ! [[ "${GRACE_S}" =~ ^[0-9]+$ ]] || [ "$(( WALL_S - GRACE_S ))" -le 0 ]; then
    echo "REFUSED: TRAIN_WALL_TOO_SHORT: --wall-s ${WALL_S} minus grace ${GRACE_S} must be a positive integer number of seconds" >&2
    exit 2
  fi
  if ! [[ "${TRAIN_MAX_RATE}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${TRAIN_MAX_RATE}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: TRAIN_MAX_RATE_REQUIRED: --train needs --max-rate <units/h>, the highest live rate the window may run at" >&2
    exit 2
  fi
  if [ -z "${DATASET_DIR}" ]; then
    echo "REFUSED: TRAIN_DATASET_REQUIRED: --train needs --dataset-dir <dir> holding the images listed in the dataset manifest" >&2
    exit 2
  fi
  NORM_JOB_SHA=""
  NORM_DATASET_MANIFEST_SHA=""
  if [ -n "${RUNG_JOB}" ]; then
    if [ -n "${JOB_YAML}${JOB_SHA}${DATASET_MANIFEST}${DATASET_MANIFEST_SHA}" ]; then
      echo "REFUSED: JOB_CONFLICT: --rung-job cannot be combined with --job, --job-sha, --dataset-manifest or --dataset-manifest-sha" >&2
      exit 2
    fi
    case "${RUNG_JOB}" in
      20 | 500) ;;
      *)
        echo "REFUSED: RUNG_JOB_REQUIRED: --train needs --rung-job 20|500 (no default)" >&2
        exit 2
        ;;
    esac
  elif [ -z "${JOB_YAML}${JOB_SHA}${DATASET_MANIFEST}${DATASET_MANIFEST_SHA}" ]; then
    echo "REFUSED: RUNG_JOB_REQUIRED: --train needs --rung-job 20|500 or --job <path> --job-sha <64-hex>" >&2
    exit 2
  else
    if [ -z "${JOB_YAML}" ]; then
      echo "REFUSED: JOB_REQUIRED: real-run path needs --job <path>" >&2
      exit 2
    fi
    NORM_JOB_SHA="${JOB_SHA#sha256:}"
    NORM_JOB_SHA="${NORM_JOB_SHA,,}"
    if ! [[ "${NORM_JOB_SHA}" =~ ^[0-9a-f]{64}$ ]]; then
      echo "REFUSED: JOB_SHA_REQUIRED: --job needs --job-sha <64-hex sha256>" >&2
      exit 2
    fi
    if [ -z "${DATASET_MANIFEST}" ]; then
      echo "REFUSED: DATASET_MANIFEST_REQUIRED: --job needs --dataset-manifest <path>" >&2
      exit 2
    fi
    NORM_DATASET_MANIFEST_SHA="${DATASET_MANIFEST_SHA#sha256:}"
    NORM_DATASET_MANIFEST_SHA="${NORM_DATASET_MANIFEST_SHA,,}"
    if ! [[ "${NORM_DATASET_MANIFEST_SHA}" =~ ^[0-9a-f]{64}$ ]]; then
      echo "REFUSED: DATASET_MANIFEST_SHA_REQUIRED: --dataset-manifest needs --dataset-manifest-sha <64-hex sha256>" >&2
      exit 2
    fi
  fi
fi

# The pre-built wheels live outside the repository; there is no default location.
if [ -z "${WHEEL_DIR}" ]; then
  echo "REFUSED: WHEEL_DIR_REQUIRED: pass --wheel-dir <dir> or set SDLAB_WHEEL_DIR" >&2
  exit 2
fi

# The evidence directory is the operator's choice; there is no default location.
if [ -z "${OUT_DIR}" ]; then
  echo "REFUSED: OUT_DIR_REQUIRED: pass --out-dir <dir> on a persistent disk" >&2
  exit 2
fi

# Test mode needs the flag AND the fake-marked colab CLI on PATH (refused if the flag is set
# without the fake). Every test hook and pin override below is honoured only in test mode.
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
LOCK_FILE="${SCRIPT_DIR}/locks/lane3.lock"
LOCAL_WHEELS_JSON="${SCRIPT_DIR}/locks/lane3-local-wheels.json"
# Test hook: a fixture manifest, used only under the fake colab CLI (the pre-flight refuses it live).
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_PREFLIGHT_WHEELS_MANIFEST:-}" ]; then
  LOCAL_WHEELS_JSON="${SDLAB_PREFLIGHT_WHEELS_MANIFEST}"
fi
RUNNER_PY="${SCRIPT_DIR}/remote_runner.py"
CLASSIFIER_PY="${SCRIPT_DIR}/classify_install_log.py"
WINDOW_SH="${SCRIPT_DIR}/colab_window.sh"
RUNG_PY="${SCRIPT_DIR}/lane3_rung.py"
BUNDLE_NOW_PY="${SCRIPT_DIR}/lane3_bundle_now.py"
RUNG_YAML="${SCRIPT_DIR}/lane3/rung-qwen-image.yaml"
RUNG500_YAML="${SCRIPT_DIR}/lane3/rung-qwen-image-500.yaml"
RUNG_DATASET_JSON="${SCRIPT_DIR}/lane3/rung-dataset.json"
# Test hooks: a fixture dataset manifest, a short download probe, a disk threshold and a short GPU
# smoke, honoured only under the fake colab CLI (set in a live run, they are PIN_OVERRIDE_IN_LIVE_RUN below).
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_RUNG_DATASET_MANIFEST:-}" ]; then
  RUNG_DATASET_JSON="${SDLAB_TEST_RUNG_DATASET_MANIFEST}"
fi
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_DOWNLOAD_PROBE_SECONDS:-}" ]; then
  LANE3_DOWNLOAD_PROBE_SECONDS="${SDLAB_TEST_DOWNLOAD_PROBE_SECONDS}"
fi
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_DISK_REQUIRED_GIB:-}" ]; then
  LANE3_DISK_REQUIRED_GIB="${SDLAB_TEST_DISK_REQUIRED_GIB}"
fi
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_GPU_SMOKE_SECONDS:-}" ]; then
  LANE3_GPU_SMOKE_SECONDS="${SDLAB_TEST_GPU_SMOKE_SECONDS}"
fi
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_INSTALL_ALLOWANCE_S:-}" ]; then
  LANE3_INSTALL_ALLOWANCE_S="${SDLAB_TEST_INSTALL_ALLOWANCE_S}"
fi
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_VM_DISK_BUDGET_GIB:-}" ]; then
  LANE3_VM_DISK_BUDGET_GIB="${SDLAB_TEST_VM_DISK_BUDGET_GIB}"
fi
TEST_TRAIN_ALLOWANCE_S=""
TEST_FETCH_ALLOWANCE_S=""
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_TRAIN_ALLOWANCE_S:-}" ]; then
  LANE3_TRAIN_ALLOWANCE_S="${SDLAB_TEST_TRAIN_ALLOWANCE_S}"
  TEST_TRAIN_ALLOWANCE_S="${SDLAB_TEST_TRAIN_ALLOWANCE_S}"
  TEST_FETCH_ALLOWANCE_S="${SDLAB_TEST_FETCH_ALLOWANCE_S:-}"
fi

PIN_OVERRIDE_VARS=(
  EXPECTED_OVERRIDE_SHA
  EXPECTED_LOCAL_WHEELS_MANIFEST_SHA
  EXPECTED_INSTALL_CLASSIFIER_SHA
  EXPECTED_LAUNCH_GUARDS_SHA
  EXPECTED_REMOTE_RUNNER_SHA
  EXPECTED_COLAB_WINDOW_SHA
  EXPECTED_LAUNCH_LANE3_STUB_SHA
  EXPECTED_LANE3_RUNG_SHA
  EXPECTED_RUNG_YAML_SHA
  EXPECTED_RUNG500_YAML_SHA
  EXPECTED_RUNG_DATASET_SHA
  EXPECTED_BUNDLE_NOW_SHA
  SDLAB_TEST_HF_ENDPOINT
  SDLAB_TEST_RUNG_DATASET_MANIFEST
  SDLAB_TEST_DOWNLOAD_PROBE_SECONDS
  SDLAB_TEST_DISK_REQUIRED_GIB
  SDLAB_TEST_VM_DISK_BUDGET_GIB
  SDLAB_TEST_GPU_SMOKE_SECONDS
  SDLAB_TEST_RATE_READ_INTERVAL_S
  SDLAB_TEST_INSTALL_ALLOWANCE_S
  SDLAB_TEST_TRAIN_ALLOWANCE_S
  SDLAB_TEST_FETCH_ALLOWANCE_S
  SDLAB_TEST_KILL_GRACE_S
  SDLAB_TEST_DOWNLOAD_TIMEOUT_S
  SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S
  SDLAB_TEST_SALVAGE_EXEC_TIMEOUT_S
  SDLAB_TEST_SALVAGE_DEADLINE_S
  SDLAB_TEST_STOP_TIMEOUT_S
  SDLAB_TEST_SESSIONS_TIMEOUT_S
  SDLAB_TEST_OPEN_LOCK_TIMEOUT_S
  SDLAB_TEST_NEW_TIMEOUT_S
  SDLAB_TEST_UPLOAD_TIMEOUT_S
  SDLAB_TEST_UPLOAD_REASSEMBLE_TIMEOUT_S
  SDLAB_TEST_UPLOAD_REASSEMBLE_MB_S
  SDLAB_TEST_UPLOAD_CHUNK_BYTES
  SDLAB_TEST_DOWNLOAD_CHUNK_BYTES
  SDLAB_TEST_WALL_ESCALATE_S
)
colab_refuse_live_pin_overrides "${OUT_DIR}" "${TEST_MODE}" "${PIN_OVERRIDE_VARS[@]}"
colab_apply_test_cleanup_overrides "${TEST_MODE}"
EXP_OVERRIDE_SHA="${PINNED_OVERRIDE_SHA}"
EXP_LOCAL_WHEELS_SHA="${PINNED_LOCAL_WHEELS_MANIFEST_SHA}"
EXP_CLASSIFIER_SHA="${PINNED_INSTALL_CLASSIFIER_SHA}"
EXP_GUARDS_SHA="${PINNED_LAUNCH_GUARDS_SHA}"
EXP_RUNNER_SHA="${PINNED_REMOTE_RUNNER_SHA}"
EXP_WINDOW_SHA="${PINNED_COLAB_WINDOW_SHA}"
EXP_SELF_SHA="${PINNED_SELF_SHA}"
EXP_RUNG_SHA="${PINNED_LANE3_RUNG_SHA}"
EXP_RUNG_YAML_SHA="${PINNED_RUNG_YAML_SHA}"
EXP_RUNG500_YAML_SHA="${PINNED_RUNG500_YAML_SHA}"
EXP_RUNG_DATASET_SHA="${PINNED_RUNG_DATASET_SHA}"
EXP_BUNDLE_NOW_SHA="${PINNED_BUNDLE_NOW_SHA}"
if [ "${TEST_MODE}" = "1" ]; then
  EXP_OVERRIDE_SHA="${EXPECTED_OVERRIDE_SHA:-${EXP_OVERRIDE_SHA}}"
  EXP_LOCAL_WHEELS_SHA="${EXPECTED_LOCAL_WHEELS_MANIFEST_SHA:-${EXP_LOCAL_WHEELS_SHA}}"
  EXP_CLASSIFIER_SHA="${EXPECTED_INSTALL_CLASSIFIER_SHA:-${EXP_CLASSIFIER_SHA}}"
  EXP_GUARDS_SHA="${EXPECTED_LAUNCH_GUARDS_SHA:-${EXP_GUARDS_SHA}}"
  EXP_RUNNER_SHA="${EXPECTED_REMOTE_RUNNER_SHA:-${EXP_RUNNER_SHA}}"
  EXP_WINDOW_SHA="${EXPECTED_COLAB_WINDOW_SHA:-${EXP_WINDOW_SHA}}"
  EXP_SELF_SHA="${EXPECTED_LAUNCH_LANE3_STUB_SHA:-${EXP_SELF_SHA}}"
  EXP_RUNG_SHA="${EXPECTED_LANE3_RUNG_SHA:-${EXP_RUNG_SHA}}"
  EXP_RUNG_YAML_SHA="${EXPECTED_RUNG_YAML_SHA:-${EXP_RUNG_YAML_SHA}}"
  EXP_RUNG500_YAML_SHA="${EXPECTED_RUNG500_YAML_SHA:-${EXP_RUNG500_YAML_SHA}}"
  EXP_RUNG_DATASET_SHA="${EXPECTED_RUNG_DATASET_SHA:-${EXP_RUNG_DATASET_SHA}}"
  EXP_BUNDLE_NOW_SHA="${EXPECTED_BUNDLE_NOW_SHA:-${EXP_BUNDLE_NOW_SHA}}"
fi

SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
  "${LOCK_FILE}=${EXP_OVERRIDE_SHA}" \
  "${LOCAL_WHEELS_JSON}=${EXP_LOCAL_WHEELS_SHA}" \
  "${CLASSIFIER_PY}=${EXP_CLASSIFIER_SHA}" \
  "${GUARDS_PY}=${EXP_GUARDS_SHA}" \
  "${RUNNER_PY}=${EXP_RUNNER_SHA}" \
  "${WINDOW_SH}=${EXP_WINDOW_SHA}" \
  "${RUNG_PY}=${EXP_RUNG_SHA}" \
  "${RUNG_YAML}=${EXP_RUNG_YAML_SHA}" \
  "${RUNG500_YAML}=${EXP_RUNG500_YAML_SHA}" \
  "${RUNG_DATASET_JSON}=${EXP_RUNG_DATASET_SHA}" \
  "${BUNDLE_NOW_PY}=${EXP_BUNDLE_NOW_SHA}" \
  "${SELF_SH}=${EXP_SELF_SHA}")"

ACTIVE_JOB_YAML="${RUNG_YAML}"
ACTIVE_JOB_SHA=""
ACTIVE_DATASET_JSON="${RUNG_DATASET_JSON}"
ACTIVE_DATASET_SHA=""
DATASET_ARCHIVE="${OUT_DIR}/.lane3_dataset.tar"
DATASET_ARCHIVE_SHA=""
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  if [ -n "${RUNG_JOB}" ]; then
    if [ "${RUNG_JOB}" = "500" ]; then
      ACTIVE_JOB_YAML="${RUNG500_YAML}"
      ACTIVE_JOB_SHA="${EXP_RUNG500_YAML_SHA}"
    else
      ACTIVE_JOB_YAML="${RUNG_YAML}"
      ACTIVE_JOB_SHA="${EXP_RUNG_YAML_SHA}"
    fi
    ACTIVE_DATASET_JSON="${RUNG_DATASET_JSON}"
    ACTIVE_DATASET_SHA="${EXP_RUNG_DATASET_SHA}"
    printf '%s\n' "${ACTIVE_JOB_SHA}" > "${OUT_DIR}/rung_job_sha256.txt"
    printf '%s\n' "${RUNG_JOB}" > "${OUT_DIR}/rung_job.txt"
  else
    ACTIVE_JOB_YAML="${JOB_YAML}"
    ACTIVE_JOB_SHA="${NORM_JOB_SHA}"
    ACTIVE_DATASET_JSON="${DATASET_MANIFEST}"
    ACTIVE_DATASET_SHA="${NORM_DATASET_MANIFEST_SHA}"
  fi
  printf '%s\n' "${ACTIVE_JOB_SHA}" > "${OUT_DIR}/job_sha256.txt"
  printf '%s\n' "${ACTIVE_DATASET_SHA}" > "${OUT_DIR}/dataset_manifest_sha256.txt"
fi

OPENED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$(date -u +%s)"
SESSION_OPENED=0
WALL_WATCHER_PID=""
EXEC_PID=""
EXEC_IN_FLIGHT=0
TOKEN_DIR=""

# lane3_download_bundle_after_failure <rc>: after a failed or stopped exec, run bounded salvage via
# colab_salvage_bundle_after_failure (`colab restart-kernel` under `timeout -k 10 180`, bundle-now
# `colab exec --timeout 300` under `timeout -k 10 330`, and `colab download` under `timeout -k 10 ${COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S}`,
# all under `SALVAGE_DEADLINE_S`). Every exec on a session runs on its one stored kernel and
# Jupyter runs one cell at a time (docs/colab-cli-contract.md, section 1), so while the killed exec's
# cell still runs, a new exec would only queue behind it: `colab restart-kernel` ends that cell.
# Processes the cell spawned may outlive the restart, so bundle-now kills the rung's processes by
# command line either way. A rig-side kill (wall, cap, stall, dead harness) stops only the local exec:
# the VM-side script keeps running and its EXIT trap never fires, so bundle-now stops it, sweeps the
# training folder, writes the failure record and tars lane3_out. Nothing here writes a REFUSED line,
# so the window's refusal stays the one that stopped the run.
lane3_download_bundle_after_failure() {
  local rc="$1"
  colab_salvage_bundle_after_failure \
    "${SESSION}" "${BUNDLE_NOW_PY}" /content/lane3_stub_bundle.tar.gz \
    "${OUT_DIR}/lane3_stub_bundle.tar.gz" "${OUT_DIR}" "${rc}"
}

cleanup_on_exit() {
  local rc=$?
  colab_enter_cleanup_trap "${OUT_DIR}"
  if [ -n "${EXEC_PID}" ]; then
    pkill -P "${EXEC_PID}" 2>/dev/null || true
    kill -9 "${EXEC_PID}" 2>/dev/null || true
    wait "${EXEC_PID}" 2>/dev/null || true
  fi
  if [ -n "${TOKEN_DIR}" ]; then
    rm -rf "${TOKEN_DIR}" || true
  fi
  rm -f "${DATASET_ARCHIVE:-}" || true
  if [ "${rc}" -ne 0 ] && [ "${TRAIN_REQUESTED}" = "1" ] && [ "${EXEC_IN_FLIGHT}" = "1" ] \
    && [ ! -s "${OUT_DIR}/lane3_stub_bundle.tar.gz" ]; then
    lane3_download_bundle_after_failure "${rc}" || true
  fi
  if [ "${TRAIN_REQUESTED}" = "1" ] && [ -s "${OUT_DIR}/lane3_stub_bundle.tar.gz" ] \
    && [ ! -f "${OUT_DIR}/bundle_manifest_check.json" ]; then
    "${PY_BIN}" "${RUNG_PY}" verify-bundle --bundle-tar "${OUT_DIR}/lane3_stub_bundle.tar.gz" \
      --out "${OUT_DIR}/bundle_manifest_check.json" >/dev/null 2>&1 || true
  fi
  if [ -f "${OUT_DIR}/watcher_escalated.txt" ]; then
    sleep 3600
    exit 137
  fi
  printf 'trap\n' > "${OUT_DIR}/stop_path.txt"
  printf '1\n' > "${OUT_DIR}/stop_reached.txt"
  if [ "${SESSION_OPENED}" -eq 1 ] && { [ -f "${OUT_DIR}/session_open_started.txt" ] || [ -f "${OUT_DIR}/session_opened.txt" ]; } \
    && [ ! -f "${OUT_DIR}/stopped_early.txt" ]; then
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
  colab_write_window_and_outcome \
    "${PY_BIN}" "${OUT_DIR}" "train" "${SESSION}" "${CARD}" \
    "${CAP}" "${WALL_S}" "${GRACE_S}" "${MARGIN}" \
    "${OPENED_AT}" "${closed_at}" "${rc}" "${SHAS_JSON}" || true
  colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" || true
  if [ "${TRAIN_REQUESTED}" = "1" ] && [ "${SESSION_OPENED}" -eq 1 ]; then
    echo "REMINDER: check ~/.config/colab-cli/history for the token's last 4 characters (the kit never reads that history)"
  fi
  exit "${rc}"
}
trap cleanup_on_exit EXIT
trap 'exit 143' TERM INT

# The card class sets the rate policy (launch_guards.parse_usage_text): a GPU window is priced on
# max(--max-rate, the highest stable window rate); a CPU stub keeps the labelled configured rate.
colab_gpu_rate_gate_arm "${OUT_DIR}" "${CARD}" "${TRAIN_MAX_RATE}" "${TEST_MODE}"
# A GPU card names its machine shape (--shape standard|high-mem, no default: SHAPE_REQUIRED); a CPU
# stub keeps colab new --high-mem and takes no --shape (colab_window.sh, colab_shape_gate_arm).
colab_shape_gate_arm "${OUT_DIR}" "${CARD}" "${SHAPE}"

WHEEL_DIR="$(lane3_translate_wsl_path "${WHEEL_DIR}")"
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  DATASET_DIR="$(lane3_translate_wsl_path "${DATASET_DIR}")"
  ACTIVE_JOB_YAML="$(lane3_translate_wsl_path "${ACTIVE_JOB_YAML}")"
  ACTIVE_DATASET_JSON="$(lane3_translate_wsl_path "${ACTIVE_DATASET_JSON}")"
fi

# Train mode: before any colab call and before preflight_resolve.sh, verify the job YAML's sha256,
# pinned hub references + licence allow-list, save/sample cadences, trigger/cache_text_embeddings
# compatibility and explicit caption dropout (`check-job`); verify the dataset manifest + every
# image sha256 while packing one deterministic tar archive (`dataset`); and resolve the bundle
# download timeout, upload timeout check, job-derived wall allowance and output disk projection
# (`plan-run`).
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  JOB_CHECK_OUT=""
  if ! JOB_CHECK_OUT="$("${PY_BIN}" "${RUNG_PY}" check-job --template "${ACTIVE_JOB_YAML}" --template-sha "${ACTIVE_JOB_SHA}" --model-revision "${TRAIN_MODEL_REVISION}" --model-repo "${TRAIN_MODEL}" --plan-out "${OUT_DIR}/job_plan.json" 2>&1)"; then
    printf '%s\n' "${JOB_CHECK_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
    exit 2
  fi
  printf '%s\n' "${JOB_CHECK_OUT}" >> "${OUT_DIR}/guards.log"

  DATASET_OUT=""
  if ! DATASET_OUT="$("${PY_BIN}" "${RUNG_PY}" dataset --manifest "${ACTIVE_DATASET_JSON}" --manifest-sha "${ACTIVE_DATASET_SHA}" --src "${DATASET_DIR}" --pack-archive "${DATASET_ARCHIVE}" --archive-sha-out "${OUT_DIR}/dataset_archive_sha256.txt" 2>&1)"; then
    printf '%s\n' "${DATASET_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
    exit 2
  fi
  printf '%s\n' "${DATASET_OUT}" >> "${OUT_DIR}/guards.log"
  DATASET_ARCHIVE_SHA="$(tr -d '\r\n' < "${OUT_DIR}/dataset_archive_sha256.txt")"

  IS_REAL_JOB="0"
  if [ -z "${RUNG_JOB}" ]; then
    IS_REAL_JOB="1"
  fi
  EXPLICIT_DL_TIMEOUT=""
  if [ "${COLAB_DOWNLOAD_TIMEOUT_SOURCE}" != "default" ]; then
    EXPLICIT_DL_TIMEOUT="${COLAB_DOWNLOAD_TIMEOUT_S}"
  fi
  EFFECTIVE_VM_BUDGET_GIB="${VM_DISK_BUDGET_GIB_ARG:-${LANE3_VM_DISK_BUDGET_GIB}}"
  PLAN_ARGS=(
    --job-plan "${OUT_DIR}/job_plan.json"
    --is-real-job "${IS_REAL_JOB}"
    --explicit-download-timeout-s "${EXPLICIT_DL_TIMEOUT}"
    --download-timeout-source "${COLAB_DOWNLOAD_TIMEOUT_SOURCE}"
    --default-download-timeout-s "${COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT}"
    --download-chunk-bytes "${COLAB_DOWNLOAD_CHUNK_BYTES}"
    --upload-timeout-s "${COLAB_UPLOAD_TIMEOUT_S}"
    --upload-timeout-source "${COLAB_UPLOAD_TIMEOUT_SOURCE}"
    --upload-chunk-bytes "${COLAB_UPLOAD_CHUNK_BYTES}"
    --dataset-archive "${DATASET_ARCHIVE}"
    --download-max-seconds "${TRAIN_DOWNLOAD_MAX_SECONDS}"
    --setup-allowance-s "${LANE3_INSTALL_ALLOWANCE_S}"
    --rung-train-allowance-s "${LANE3_TRAIN_ALLOWANCE_S}"
    --wall-s "${WALL_S}"
    --grace-s "${GRACE_S}"
    --test-train-allowance-s "${TEST_TRAIN_ALLOWANCE_S}"
    --test-fetch-allowance-s "${TEST_FETCH_ALLOWANCE_S}"
    --vm-disk-budget-gib "${EFFECTIVE_VM_BUDGET_GIB}"
    --out "${OUT_DIR}/run_plan.json"
  )
  [ -n "${DOWNLOAD_FLOOR_MB_S_ARG}" ] && PLAN_ARGS+=(--download-floor-mb-s "${DOWNLOAD_FLOOR_MB_S_ARG}")
  [ -n "${UPLOAD_FLOOR_MB_S_ARG}" ] && PLAN_ARGS+=(--upload-floor-mb-s "${UPLOAD_FLOOR_MB_S_ARG}")
  [ -n "${SECONDS_PER_STEP_ARG}" ] && PLAN_ARGS+=(--seconds-per-step "${SECONDS_PER_STEP_ARG}")
  [ -n "${CHECKPOINT_SIZE_BYTES_ARG}" ] && PLAN_ARGS+=(--checkpoint-size-bytes "${CHECKPOINT_SIZE_BYTES_ARG}")
  [ -n "${OPTIMIZER_SIZE_BYTES_ARG}" ] && PLAN_ARGS+=(--optimizer-size-bytes "${OPTIMIZER_SIZE_BYTES_ARG}")
  [ -n "${OPTIMIZER_SIZE_SOURCE_ARG}" ] && PLAN_ARGS+=(--optimizer-size-source "${OPTIMIZER_SIZE_SOURCE_ARG}")
  [ -n "${SAMPLES_AND_LOGS_BYTES_ARG}" ] && PLAN_ARGS+=(--samples-and-logs-bytes "${SAMPLES_AND_LOGS_BYTES_ARG}")
  [ -n "${AUXILIARY_KEEP_ALL_BYTES_ARG}" ] && PLAN_ARGS+=(--auxiliary-keep-all-bytes "${AUXILIARY_KEEP_ALL_BYTES_ARG}")
  [ -n "${OUTPUT_OVERHEAD_FACTOR_ARG}" ] && PLAN_ARGS+=(--output-overhead-factor "${OUTPUT_OVERHEAD_FACTOR_ARG}")
  [ -n "${EXPECTED_MODEL_BYTES_ARG}" ] && PLAN_ARGS+=(--expected-model-bytes "${EXPECTED_MODEL_BYTES_ARG}")

  PLAN_OUT=""
  if ! PLAN_OUT="$("${PY_BIN}" "${RUNG_PY}" plan-run "${PLAN_ARGS[@]}" 2>&1)"; then
    printf '%s\n' "${PLAN_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
    exit 2
  fi
  printf '%s\n' "${PLAN_OUT}" >> "${OUT_DIR}/guards.log"

  read -r RESOLVED_DL_S RESOLVED_DL_SRC RESOLVED_DL_PARTS PROJECTED_OUTPUT_BYTES < <(
    "${PY_BIN}" -c 'import json, sys; p = json.load(open(sys.argv[1], encoding="utf-8")); b = p["download_timeout_basis"]; print(p["download_timeout_s"], ("projected" if b["mode"] == "projected" else b["source"]), int(b.get("part_count") or 1), p["output_disk_projection"]["projected_output_bytes"])' "${OUT_DIR}/run_plan.json" | tr -d '\r'
  )
  colab_configure_download_timeout "${RESOLVED_DL_S}" "${RESOLVED_DL_SRC}" "${RESOLVED_DL_PARTS}" || exit 2
  colab_apply_test_cleanup_overrides "${TEST_MODE}"

  if [ -z "${RUNG_JOB}" ]; then
    SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
      "${LOCK_FILE}=${EXP_OVERRIDE_SHA}" \
      "${LOCAL_WHEELS_JSON}=${EXP_LOCAL_WHEELS_SHA}" \
      "${CLASSIFIER_PY}=${EXP_CLASSIFIER_SHA}" \
      "${GUARDS_PY}=${EXP_GUARDS_SHA}" \
      "${RUNNER_PY}=${EXP_RUNNER_SHA}" \
      "${WINDOW_SH}=${EXP_WINDOW_SHA}" \
      "${RUNG_PY}=${EXP_RUNG_SHA}" \
      "${RUNG_YAML}=${EXP_RUNG_YAML_SHA}" \
      "${RUNG500_YAML}=${EXP_RUNG500_YAML_SHA}" \
      "${RUNG_DATASET_JSON}=${EXP_RUNG_DATASET_SHA}" \
      "${BUNDLE_NOW_PY}=${EXP_BUNDLE_NOW_SHA}" \
      "${SELF_SH}=${EXP_SELF_SHA}" \
      "${ACTIVE_JOB_YAML}=${ACTIVE_JOB_SHA}" \
      "${ACTIVE_DATASET_JSON}=${ACTIVE_DATASET_SHA}")"
  fi
fi

# Refuse CAP_TOO_SMALL_FOR_CLEANUP before any colab call when cap - margin - cleanup_reserve <= 0
# or when the cap leaves less runtime than --min-runtime-s (using the resolved download/upload bounds).
COLAB_UPLOAD_MAX_BYTES="$(lane3_upload_max_bytes "${LOCAL_WHEELS_JSON}" "${WHEEL_DIR}" "${DATASET_ARCHIVE:-}" "${RUNG_PY}" "${GUARDS_PY}" "${LOCK_FILE}" "${CLASSIFIER_PY}")"
export COLAB_UPLOAD_MAX_BYTES
colab_cap_budget_gate "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" "train" "${CARD}" "${CAP}" "${MARGIN}" "${TRAIN_MAX_RATE}" "${RATE_CCU_PER_HOUR:-0.26}" "${MIN_RUNTIME_S}"

# Free pre-flight resolve, git pin check, and local wheel sha verification before any colab CLI call.
# The pre-flight honours its SDLAB_PREFLIGHT_* test hooks only under the fake colab CLI
# and refuses them in a live run (PREFLIGHT_TEST_HOOK_IN_LIVE_RUN).
PREFLIGHT_OUT=""
if ! PREFLIGHT_OUT="$(bash "${SCRIPT_DIR}/preflight_resolve.sh" lane3 --wheel-dir "${WHEEL_DIR}" 2>&1)"; then
  printf '%s\n' "${PREFLIGHT_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
  exit 1
fi
printf '%s\n' "${PREFLIGHT_OUT}" >> "${OUT_DIR}/guards.log"

# Train mode: the model at the pinned revision must answer the request's read token before any
# spend (MODEL_AUTH_FAILED, MODEL_REVISION_NOT_FOUND, MODEL_METADATA_FAILED). The token reaches the
# check through its environment (HF_TOKEN_GGUF_READ), never its argv.
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  MODEL_CHECK_OUT=""
  if ! MODEL_CHECK_OUT="$("${PY_BIN}" "${RUNG_PY}" model-check --repo "${TRAIN_MODEL}" --revision "${TRAIN_MODEL_REVISION}" 2>&1)"; then
    printf '%s\n' "${MODEL_CHECK_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
    exit 1
  fi
  printf '%s\n' "${MODEL_CHECK_OUT}" >> "${OUT_DIR}/guards.log"
fi

# Train mode: stage the read token before any colab call, as a mode-600 file in a private tmpfs
# directory (removed after the upload and by the EXIT trap); HF_TOKEN_STAGING_FAILED otherwise.
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  if ! TOKEN_DIR="$(umask 077 && mktemp -d "${XDG_RUNTIME_DIR:-/dev/shm}/sdlab-l3-tok.XXXXXX" 2>/dev/null)"; then
    TOKEN_DIR=""
    colab_refuse_logged "${OUT_DIR}" HF_TOKEN_STAGING_FAILED "no private tmpfs directory (XDG_RUNTIME_DIR or /dev/shm) for the token file"
    exit 1
  fi
  if ! ( umask 077 && printf '%s' "${HF_TOKEN_GGUF_READ}" > "${TOKEN_DIR}/lane3_hf_read_token" ) \
    || ! chmod 600 "${TOKEN_DIR}/lane3_hf_read_token"; then
    colab_refuse_logged "${OUT_DIR}" HF_TOKEN_STAGING_FAILED "could not write the token file in the private directory"
    exit 1
  fi
fi

# Pre-open cap and host-RAM check via launch_guards.py
colab_check_cap_and_ram "${PY_BIN}" "${GUARDS_PY}" "stub" "0" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}"

# Independent wall watcher (cannot be blocked by a child timeout; escalates to `colab stop` + SIGKILL)
WALL_INT="${WALL_S%.*}"
GRACE_INT="${GRACE_S%.*}"
WALL_LIMIT_S="$(( WALL_INT > GRACE_INT ? WALL_INT - GRACE_INT : 1 ))"
WALL_WATCHER_START_EPOCH="$("${PY_BIN}" -c 'import time; print(f"{time.time():.6f}")' 2>/dev/null || date -u +%s)"
MAIN_PID="$$"
colab_run_wall_watcher \
  "${MAIN_PID}" "${WALL_LIMIT_S}" "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" \
  "train" "${SESSION}" "${CARD}" "${CAP}" "${WALL_S}" "${GRACE_S}" "${MARGIN}" \
  "${OPENED_AT}" "${SHAS_JSON}" &
WALL_WATCHER_PID="$!"

# Hold /tmp/colab-window-open.lock while opening with colab new (CPU: --high-mem; GPU: --high-mem
# only for --shape high-mem, then the session row's Shape is checked: SHAPE_MISMATCH)
SESSION_OPENED=1
colab_open_session_locked "${SESSION}" "${CARD}" "${OUT_DIR}"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
colab_check_pre_exec_cap "${OUT_DIR}"

REMOTE_RUNNER="${OUT_DIR}/remote_lane3_stub.sh"
lane3_write_remote_script "${REMOTE_RUNNER}"
colab_check_pre_exec_cap "${OUT_DIR}"

# Every upload goes flat into /content, the one remote directory that exists before the remote
# script runs; the script's sdlab-remote-dirs block moves the wheels into /content/wheels.
WHEEL_NAMES=()
while IFS= read -r wheel_fname; do
  [ -z "${wheel_fname}" ] && continue
  WHEEL_NAMES+=("${wheel_fname}")
done < <("${PY_BIN}" -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); print("\n".join(w["filename"] for w in d.get("wheels", [])))' "${LOCAL_WHEELS_JSON}")
colab_upload_checked "${SESSION}" "${LOCK_FILE}" /content/lane3.lock "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${LOCAL_WHEELS_JSON}" /content/lane3-local-wheels.json "${OUT_DIR}"
for wheel_fname in "${WHEEL_NAMES[@]}"; do
  colab_upload_checked "${SESSION}" "${WHEEL_DIR}/${wheel_fname}" "/content/${wheel_fname}" "${OUT_DIR}"
done
colab_upload_checked "${SESSION}" "${GUARDS_PY}" /content/launch_guards.py "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${CLASSIFIER_PY}" /content/classify_install_log.py "${OUT_DIR}"
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  colab_upload_checked "${SESSION}" "${RUNG_PY}" /content/lane3_rung.py "${OUT_DIR}"
  colab_upload_checked "${SESSION}" "${ACTIVE_JOB_YAML}" /content/rung-qwen-image.yaml "${OUT_DIR}"
  colab_upload_checked "${SESSION}" "${ACTIVE_DATASET_JSON}" /content/rung-dataset.json "${OUT_DIR}"
  # The read token staged before the window opened; the VM reads and shreds it first thing.
  colab_upload_checked "${SESSION}" "${TOKEN_DIR}/lane3_hf_read_token" /content/lane3_hf_read_token "${OUT_DIR}"
  rm -rf "${TOKEN_DIR}"
  TOKEN_DIR=""
  colab_upload_checked "${SESSION}" "${DATASET_ARCHIVE}" /content/lane3_dataset.tar "${OUT_DIR}"
  rm -f "${DATASET_ARCHIVE}"
fi
colab_upload_checked "${SESSION}" "${REMOTE_RUNNER}" /content/remote_lane3_stub.sh "${OUT_DIR}"

REMOTE_ENV=()
mapfile -t REMOTE_ENV < <(lane3_remote_env "${EXP_OVERRIDE_SHA}")
colab_check_pre_exec_cap "${OUT_DIR}"
EXEC_IN_FLIGHT=1
colab_run_exec_with_live_guards \
  "${PY_BIN}" "${GUARDS_PY}" "${SESSION}" "${RUNNER_PY}" \
  "${START_EPOCH}" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}" \
  "SDLAB_REMOTE_SCRIPT=/content/remote_lane3_stub.sh" \
  "${REMOTE_ENV[@]}"

# Download result tar before EXIT trap stops the session (EXEC_IN_FLIGHT stays 1 so a failed
# normal download still triggers post-failure salvage in cleanup_on_exit).
colab_download_checked "${SESSION}" /content/lane3_stub_bundle.tar.gz "${OUT_DIR}/lane3_stub_bundle.tar.gz" "${OUT_DIR}"
EXEC_IN_FLIGHT=0
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  VERIFY_BUNDLE_OUT=""
  if ! VERIFY_BUNDLE_OUT="$("${PY_BIN}" "${RUNG_PY}" verify-bundle --bundle-tar "${OUT_DIR}/lane3_stub_bundle.tar.gz" --out "${OUT_DIR}/bundle_manifest_check.json" 2>&1)"; then
    echo "BUNDLE_VERIFY_INITIAL_MISMATCH session=${SESSION} detail=$(printf '%s' "${VERIFY_BUNDLE_OUT}" | tr '\r\n' ' ')" | tee -a "${OUT_DIR}/guards.log" >&2
    # While the VM is up: fetch each bad file once (files whose VM source is itself bad are not
    # retried), then at most one more bounded pass for files that failed for another reason. Nothing
    # sleeps. Print a ready-to-run `colab download` line per unresolved file, then stop the session
    # BEFORE any rig-side work (bundle repair, re-verification), which does not need the VM.
    colab_refetch_missing_bundle_files \
      "${PY_BIN}" "${RUNG_PY}" "${SESSION}" \
      "${OUT_DIR}/lane3_stub_bundle.tar.gz" "${OUT_DIR}/bundle_manifest_check.json" \
      "${OUT_DIR}" "${WALL_WATCHER_START_EPOCH}" "${WALL_LIMIT_S}" 1 || true
    colab_refetch_followup_pass \
      "${PY_BIN}" "${GUARDS_PY}" "${RUNG_PY}" "${SESSION}" \
      "${OUT_DIR}/lane3_stub_bundle.tar.gz" "${OUT_DIR}/bundle_manifest_check.json" \
      "${OUT_DIR}" "${WALL_WATCHER_START_EPOCH}" "${WALL_LIMIT_S}" "${CAP}" "${MARGIN}" || true
    colab_print_unresolved_download_cmds "${PY_BIN}" "${SESSION}" "${OUT_DIR}" || true
    colab_stop_session_early "${PY_BIN}" "${SESSION}" "${OUT_DIR}"
    colab_repair_recovered_bundle "${PY_BIN}" "${RUNG_PY}" "${OUT_DIR}/lane3_stub_bundle.tar.gz" "${OUT_DIR}" || true
    REVERIFY_ARGS=(--bundle-tar "${OUT_DIR}/lane3_stub_bundle.tar.gz" --out "${OUT_DIR}/bundle_manifest_check.json")
    if [ -s "${OUT_DIR}/.recovered_files.txt" ]; then
      while IFS= read -r rec_spec; do
        [ -z "${rec_spec}" ] && continue
        REVERIFY_ARGS+=(--recovered-file "${rec_spec}")
      done < "${OUT_DIR}/.recovered_files.txt"
    fi
    VERIFY_BUNDLE_OUT=""
    if ! VERIFY_BUNDLE_OUT="$("${PY_BIN}" "${RUNG_PY}" verify-bundle "${REVERIFY_ARGS[@]}" 2>&1)"; then
      printf '%s\n' "${VERIFY_BUNDLE_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
      exit 1
    fi
    echo "BUNDLE_REFETCH_RECOVERED session=${SESSION}" | tee -a "${OUT_DIR}/guards.log" >&2
  fi
  printf '%s\n' "${VERIFY_BUNDLE_OUT}" >> "${OUT_DIR}/guards.log"
fi
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
