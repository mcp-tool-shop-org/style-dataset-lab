#!/usr/bin/env bash
# Launch kit for Lane 3 (train) Colab windows: the CPU install-path stub (Part C, PR #47) and, with
# --train, the GPU rung. Checks pinned input sha256s (including itself) and runs preflight_resolve.sh
# before opening, holds /tmp/colab-window-open.lock, opens the card --high-mem, runs CPython 3.12.15
# uv venv + wheel-only install from hash-locked lane3.lock and pre-built local wheels in
# lane3-local-wheels.json + pinned ostris/ai-toolkit + the import gate. Without --train it stops
# there: TRAIN_SKIPPED and train=skipped_cpu_stub in window.json (never a trained result). With
# --train (a GPU card, --model, --model-revision, --host-ram-required-gib, --download-max-seconds and
# --dataset-dir, each a named refusal when missing) the remote script's LANE3_MODE=train runs the
# rung: GPU smoke / disk / host-RAM guards before the model download, the download with its
# DOWNLOAD_TOO_SLOW probe, the fixture dataset, the committed rung YAML (lane3/rung-qwen-image.yaml)
# and ai-toolkit's run.py, copying each checkpoint and sample into the bundle as it is saved; the
# bundle is downloaded at the end and, after a failure, whatever it holds. Enforces live
# launch_guards.py (wall, cap, vitals/DEAD HARNESS, host-RAM), scrubs VM-side logs before tarring,
# and stops its own session in an EXIT trap on every exit path.
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
PINNED_LAUNCH_GUARDS_SHA="6e458a8037f6933d6e5f0b8497ca9d5c2e57323f8a08b0b9a526ca9d07026d2a"
PINNED_REMOTE_RUNNER_SHA="7b346c97e2a56f86ead9417c1cbaa903f2ce1dd41aca7df41f32a78fae32c896"
PINNED_COLAB_WINDOW_SHA="5e19f1786b5179950129c1c3c283dd607c7513eb57651557f9cd08ac96196639"
PINNED_LANE3_RUNG_SHA="47462c632c86dff2979d479503f9651bf37d4560713136ebc0c8c91b51e4275b"
PINNED_BUNDLE_NOW_SHA="06db15826c9c5f229dbbab24ad405606723ae0fde4d911e464bf29c6c04db3f0"
PINNED_RUNG_YAML_SHA="f4774e926c5edd7d4defa67beeca0f17599cd20d143710726a8718f2a77e9533"
PINNED_RUNG_DATASET_SHA="fa87eda99ceb4a900fa549041a187a75ebc2041e4e27ba7547b5822db43b701d"
PINNED_SELF_SHA="91f390b7137c4f926a330a1f11d57525a35044d793af563ccae28d238f0f00d1"

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
    "\${LANE3_PY}" /content/lane3_rung.py finish --lane3-out /content/lane3_out --failed-rc "\${rc}" || true
    while IFS= read -r -d '' f; do
      "\${LANE3_PY}" /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
    done < <(find /content/lane3_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" -o -name "*.txt" \) -print0 2>/dev/null || true)
    tar -czf /content/lane3_stub_bundle.tar.gz -C /content/lane3_out . || true
    echo "TRAIN_BUNDLE_AFTER_FAILURE rc=\${rc} /content/lane3_stub_bundle.tar.gz"
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

"\${LANE3_PY}" /content/lane3_rung.py dataset --manifest /content/rung-dataset.json --src /content \
  --dest "\${LANE3_DATASET_DIR}" 2>&1 | tee -a /content/lane3_out/setup.log
"\${LANE3_PY}" /content/lane3_rung.py render-job --template /content/rung-qwen-image.yaml \
  --out /content/lane3_out/rung_job.yaml --training-folder "\${LANE3_TRAINING_FOLDER}" \
  --dataset-dir "\${LANE3_DATASET_DIR}" --model-path "\${LANE3_MODEL_PATH}" 2>&1 | tee -a /content/lane3_out/setup.log

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
wait "\${COPY_PID}"
# A final sweep of the training folder, in its own process: a copy-off watcher that died mid-run
# leaves nothing behind.
"\${LANE3_PY}" /content/lane3_rung.py copy-off --final-only --watch "\${LANE3_TRAINING_FOLDER}" \
  --bundle /content/lane3_out/rung_outputs --manifest /content/lane3_out/rung_outputs/manifest.jsonl
set -e
if [ "\${TRAIN_RC}" -ne 0 ]; then
  echo "--- last 40 lines of train.log ---"
  tail -n 40 /content/lane3_out/train.log || true
  echo "REFUSED: TRAIN_FAILED: ai-toolkit run.py exited \${TRAIN_RC}; see lane3_out/train.log" >&2
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
  if ! grep -Eq '"path": "[^"]+\.(png|jpg|jpeg|webp)"' /content/lane3_out/rung_outputs/manifest.jsonl; then
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

while IFS= read -r -d '' f; do
  /content/venv-lane3/bin/python /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
done < <(find /content/lane3_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" -o -name "*.txt" \) -print0 2>/dev/null || true)
tar -czf /content/lane3_stub_bundle.tar.gz -C /content/lane3_out .
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
LANE3_GPU_SMOKE_SECONDS="5"
LANE3_DOWNLOAD_PROBE_SECONDS="60"
LANE3_DOWNLOAD_PROBE_BYTES="2147483648"
# The rung's wall must cover, after the grace: the download limit the request sets, the install
# (uv, CPython, the 158-pin lock, ai-toolkit; 900 s allowed) and the training work (model load,
# latent and text-embedding caching, 20 steps, one save, one six-image 1024^2 grid at 25 steps with
# true CFG; 1800 s allowed, against the consult's 12-19 min estimate for the whole rung).
LANE3_INSTALL_ALLOWANCE_S="900"
# A GPU window's live rate is read right after open: up to 24 polls 5 s apart (2 min).
LANE3_RATE_READ_POLLS="24"
LANE3_RATE_READ_INTERVAL_S="5"
LANE3_TRAIN_ALLOWANCE_S="1800"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-lane3-stub-$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR=""
WHEEL_DIR="${SDLAB_WHEEL_DIR:-}"
CAP="${CAP:-0.05}"
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
DATASET_DIR=""
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
    --model) TRAIN_MODEL="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --model-revision) TRAIN_MODEL_REVISION="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --host-ram-required-gib) TRAIN_HOST_RAM_REQUIRED_GIB="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-max-seconds) TRAIN_DOWNLOAD_MAX_SECONDS="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --dataset-dir) SESSION_ARGS+=("$1"); DATASET_DIR="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    *)
      echo "REFUSED: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ "${TRAIN_REQUESTED}" != "1" ] && [ -n "${TRAIN_MODEL}${TRAIN_MODEL_REVISION}${TRAIN_HOST_RAM_REQUIRED_GIB}${TRAIN_DOWNLOAD_MAX_SECONDS}${DATASET_DIR}" ]; then
  echo "REFUSED: TRAIN_OPTION_WITHOUT_TRAIN: --model, --model-revision, --host-ram-required-gib, --download-max-seconds and --dataset-dir need --train" >&2
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
  TRAIN_NEED_S="$(( TRAIN_DOWNLOAD_MAX_SECONDS + LANE3_INSTALL_ALLOWANCE_S + LANE3_TRAIN_ALLOWANCE_S ))"
  if ! [[ "${WALL_S}" =~ ^[0-9]+$ ]] || ! [[ "${GRACE_S}" =~ ^[0-9]+$ ]] \
    || [ "$(( WALL_S - GRACE_S ))" -lt "${TRAIN_NEED_S}" ]; then
    echo "REFUSED: TRAIN_WALL_TOO_SHORT: --wall-s ${WALL_S} minus grace ${GRACE_S} must cover ${TRAIN_NEED_S} s (download limit ${TRAIN_DOWNLOAD_MAX_SECONDS} + install ${LANE3_INSTALL_ALLOWANCE_S} + train ${LANE3_TRAIN_ALLOWANCE_S})" >&2
    exit 2
  fi
  if ! [[ "${TRAIN_MAX_RATE}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${TRAIN_MAX_RATE}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: TRAIN_MAX_RATE_REQUIRED: --train needs --max-rate <units/h>, the highest live rate the window may run at" >&2
    exit 2
  fi
  if [ -z "${DATASET_DIR}" ]; then
    echo "REFUSED: TRAIN_DATASET_REQUIRED: --train needs --dataset-dir <dir> holding the images listed in scripts/colab/lane3/rung-dataset.json" >&2
    exit 2
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
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_RATE_READ_INTERVAL_S:-}" ]; then
  LANE3_RATE_READ_INTERVAL_S="${SDLAB_TEST_RATE_READ_INTERVAL_S}"
fi
if [ "${TEST_MODE}" = "1" ] && [ -n "${SDLAB_TEST_GPU_SMOKE_SECONDS:-}" ]; then
  LANE3_GPU_SMOKE_SECONDS="${SDLAB_TEST_GPU_SMOKE_SECONDS}"
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
  EXPECTED_RUNG_DATASET_SHA
  EXPECTED_BUNDLE_NOW_SHA
  SDLAB_TEST_HF_ENDPOINT
  SDLAB_TEST_RUNG_DATASET_MANIFEST
  SDLAB_TEST_DOWNLOAD_PROBE_SECONDS
  SDLAB_TEST_DISK_REQUIRED_GIB
  SDLAB_TEST_GPU_SMOKE_SECONDS
  SDLAB_TEST_RATE_READ_INTERVAL_S
)
colab_refuse_live_pin_overrides "${OUT_DIR}" "${TEST_MODE}" "${PIN_OVERRIDE_VARS[@]}"
EXP_OVERRIDE_SHA="${PINNED_OVERRIDE_SHA}"
EXP_LOCAL_WHEELS_SHA="${PINNED_LOCAL_WHEELS_MANIFEST_SHA}"
EXP_CLASSIFIER_SHA="${PINNED_INSTALL_CLASSIFIER_SHA}"
EXP_GUARDS_SHA="${PINNED_LAUNCH_GUARDS_SHA}"
EXP_RUNNER_SHA="${PINNED_REMOTE_RUNNER_SHA}"
EXP_WINDOW_SHA="${PINNED_COLAB_WINDOW_SHA}"
EXP_SELF_SHA="${PINNED_SELF_SHA}"
EXP_RUNG_SHA="${PINNED_LANE3_RUNG_SHA}"
EXP_RUNG_YAML_SHA="${PINNED_RUNG_YAML_SHA}"
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
  "${RUNG_DATASET_JSON}=${EXP_RUNG_DATASET_SHA}" \
  "${BUNDLE_NOW_PY}=${EXP_BUNDLE_NOW_SHA}" \
  "${SELF_SH}=${EXP_SELF_SHA}")"

OPENED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$(date -u +%s)"
SESSION_OPENED=0
WALL_WATCHER_PID=""
EXEC_PID=""
EXEC_STARTED=0
TOKEN_DIR=""

# lane3_download_bundle_after_failure <rc>: after a failed or stopped exec, restart the session's
# kernel, then run lane3_bundle_now.py on the VM. Every exec on a session runs on its one stored kernel
# and Jupyter runs one cell at a time (docs/colab-cli-contract.md, section 1), so while the killed
# exec's cell still runs, a new exec would only queue behind it: `colab restart-kernel` ends that cell.
# Processes the cell spawned may outlive the restart, so bundle-now kills the rung's processes by
# command line either way. A rig-side kill (wall, cap, stall, dead harness) stops only the local exec: the
# VM-side script keeps running and its EXIT trap never fires, so bundle-now stops it, sweeps the
# training folder, writes the failure record and tars lane3_out. Then the bundle is downloaded:
# whatever the run had saved. Nothing here writes a REFUSED line, so the window's refusal stays the
# one that stopped the run.
lane3_download_bundle_after_failure() {
  local rc="$1"
  local dl_out=""
  local dl_rc=0
  local dst="${OUT_DIR}/lane3_stub_bundle.tar.gz"
  timeout 180 colab restart-kernel -s "${SESSION}" </dev/null >> "${OUT_DIR}/bundle_now.log" 2>&1 || true
  colab exec -s "${SESSION}" -f "${BUNDLE_NOW_PY}" --timeout 300 --env "SDLAB_CONTENT=/content" \
    --env "SDLAB_BUNDLE_RC=${rc}" </dev/null >> "${OUT_DIR}/bundle_now.log" 2>&1 || true
  dl_out="$(colab download -s "${SESSION}" /content/lane3_stub_bundle.tar.gz "${dst}" </dev/null 2>&1)" || dl_rc=$?
  printf '%s\n' "${dl_out}" >> "${OUT_DIR}/colab.log"
  if [ "${dl_rc}" -eq 0 ] && [ -s "${dst}" ]; then
    echo "BUNDLE_AFTER_FAILURE: downloaded lane3_stub_bundle.tar.gz (rc=${rc})" >> "${OUT_DIR}/guards.log"
  else
    rm -f "${dst}"
    echo "BUNDLE_AFTER_FAILURE: none on the VM (rc=${rc}, download rc=${dl_rc})" >> "${OUT_DIR}/guards.log"
  fi
}

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
  if [ -n "${TOKEN_DIR}" ]; then
    rm -rf "${TOKEN_DIR}" || true
  fi
  if [ "${rc}" -ne 0 ] && [ "${TRAIN_REQUESTED}" = "1" ] && [ "${EXEC_STARTED}" = "1" ] \
    && [ ! -s "${OUT_DIR}/lane3_stub_bundle.tar.gz" ]; then
    lane3_download_bundle_after_failure "${rc}" || true
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
  if [ "${TRAIN_REQUESTED}" = "1" ] && [ "${SESSION_OPENED}" -eq 1 ]; then
    echo "REMINDER: check ~/.config/colab-cli/history for the token's last 4 characters (the kit never reads that history)"
  fi
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

# Train mode: the fixture dataset is checked against its manifest (sha256 of every image) before
# any colab call; DATASET_FILE_MISSING / DATASET_SHA_MISMATCH.
if [ "${TRAIN_REQUESTED}" = "1" ]; then
  DATASET_OUT=""
  if ! DATASET_OUT="$("${PY_BIN}" "${RUNG_PY}" dataset --manifest "${RUNG_DATASET_JSON}" --src "${DATASET_DIR}" 2>&1)"; then
    printf '%s\n' "${DATASET_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
    exit 1
  fi
  printf '%s\n' "${DATASET_OUT}" >> "${OUT_DIR}/guards.log"
fi

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

# The card class sets the rate policy (launch_guards.parse_usage_text): a GPU window is priced on
# max(--max-rate, the highest stable window rate); a CPU stub keeps the labelled configured rate.
if colab_card_is_cpu "${CARD}"; then
  export COLAB_CARD_CLASS=cpu
else
  export COLAB_CARD_CLASS=gpu
  if [ -z "${TRAIN_MAX_RATE}" ]; then
    colab_refuse_logged "${OUT_DIR}" MAX_RATE_REQUIRED "a GPU card needs --max-rate <units/h>"
    exit 2
  fi
  printf '%s\n' "${TRAIN_MAX_RATE}" > "${OUT_DIR}/max_rate.txt"
fi

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
# The cap and wall clock starts the moment `colab new` succeeds: the rate polls, the uploads and the
# gate below are all billed time and all count.
START_EPOCH="$(date -u +%s)"
date -u -d "@${START_EPOCH}" +%Y-%m-%dT%H:%M:%SZ > "${OUT_DIR}/cap_clock_started_at.txt"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
# A GPU window runs only on its live rate: read it right after open (bounded polls), refuse
# RATE_UNREAD without one and RATE_ABOVE_MAX above --max-rate, before any upload. A CPU stub keeps
# the configured rate (labelled `configured` in window.json).
if ! colab_card_is_cpu "${CARD}"; then
  colab_read_post_open_rate "${PY_BIN}" "${OUT_DIR}" "${LANE3_RATE_READ_POLLS}" "${LANE3_RATE_READ_INTERVAL_S}" "${TRAIN_MAX_RATE}"
fi

REMOTE_RUNNER="${OUT_DIR}/remote_lane3_stub.sh"
lane3_write_remote_script "${REMOTE_RUNNER}"

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
  colab_upload_checked "${SESSION}" "${RUNG_YAML}" /content/rung-qwen-image.yaml "${OUT_DIR}"
  colab_upload_checked "${SESSION}" "${RUNG_DATASET_JSON}" /content/rung-dataset.json "${OUT_DIR}"
  # The read token staged before the window opened; the VM reads and shreds it first thing.
  colab_upload_checked "${SESSION}" "${TOKEN_DIR}/lane3_hf_read_token" /content/lane3_hf_read_token "${OUT_DIR}"
  rm -rf "${TOKEN_DIR}"
  TOKEN_DIR=""
  while IFS= read -r image_fname; do
    [ -z "${image_fname}" ] && continue
    colab_upload_checked "${SESSION}" "${DATASET_DIR}/${image_fname}" "/content/${image_fname}" "${OUT_DIR}"
  done < <("${PY_BIN}" -c 'import json, sys; print("\n".join(i["image"] for i in json.load(open(sys.argv[1], encoding="utf-8"))["items"]))' "${RUNG_DATASET_JSON}")
fi
colab_upload_checked "${SESSION}" "${REMOTE_RUNNER}" /content/remote_lane3_stub.sh "${OUT_DIR}"

REMOTE_ENV=()
mapfile -t REMOTE_ENV < <(lane3_remote_env "${EXP_OVERRIDE_SHA}")
EXEC_STARTED=1
colab_run_exec_with_live_guards \
  "${PY_BIN}" "${GUARDS_PY}" "${SESSION}" "${RUNNER_PY}" \
  "${START_EPOCH}" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}" \
  "SDLAB_REMOTE_SCRIPT=/content/remote_lane3_stub.sh" \
  "${REMOTE_ENV[@]}"

# Download result tar before EXIT trap stops the session
colab_download_checked "${SESSION}" /content/lane3_stub_bundle.tar.gz "${OUT_DIR}/lane3_stub_bundle.tar.gz" "${OUT_DIR}"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
