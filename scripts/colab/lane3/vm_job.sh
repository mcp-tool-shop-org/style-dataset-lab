#!/usr/bin/env bash
# VM job entrypoint for Lane 3 (train), executed inside colab-runner.
# Preserves pinned versions and block markers (# >>> sdlab-*) for lock & mode-gate tests.
set -euo pipefail

PINNED_UV_VERSION="0.13.5"
PINNED_UV_WHEEL_SHA256="fa8d26e08e34c29c0c4e820cf3181757086d547240b4f4d31ff1d8bd810ca946"
PINNED_PYTHON_VERSION="3.12.15"
PINNED_PYTHON_BUILD="20261021"
PINNED_PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu130"
PINNED_AI_TOOLKIT_REPO="https://github.com/ostris/ai-toolkit.git"
PINNED_AI_TOOLKIT_COMMIT="beb94824c51480a04d3c86c718603676fdef6938"
PINNED_OVERRIDE_SHA="649f42488bf2f520b93c3efa105724be236094d614480440d0df8a07c72e1e94"
PINNED_LOCAL_WHEELS_MANIFEST_SHA="579016010aae8e5549ffc5b4777f5899a6e410eafba680a61ab3841e758b6320"

LANE3_DISK_REQUIRED_GIB="${LANE3_DISK_REQUIRED_GIB:-75}"
LANE3_GPU_SMOKE_SECONDS="${LANE3_GPU_SMOKE_SECONDS:-5}"
LANE3_DOWNLOAD_PROBE_SECONDS="${LANE3_DOWNLOAD_PROBE_SECONDS:-60}"
LANE3_DOWNLOAD_PROBE_BYTES="${LANE3_DOWNLOAD_PROBE_BYTES:-2147483648}"

WORK_DIR="${CR_WORK_DIR:-$(pwd)}"
OUT_ROOT="${CR_OUT_DIR:-/content}"
export LANE3_OUT="${OUT_ROOT}/lane3_out"
TRAIN_PID=""
COPY_PID=""

cleanup_procs() {
  local p
  for p in "${COPY_PID:-}" "${TRAIN_PID:-}"; do
    if [ -n "${p}" ]; then
      kill "${p}" 2>/dev/null || true
    fi
  done
}
trap cleanup_procs EXIT

write_phase_atomic() {
  local phase="$1"
  mkdir -p "${OUT_ROOT}" "${LANE3_OUT}"
  local tmp="${OUT_ROOT}/.phase.txt.tmp.$$"
  if ! { printf '%s\n' "${phase}" > "${tmp}" && mv -f "${tmp}" "${OUT_ROOT}/phase.txt"; }; then
    rm -f "${tmp}" 2>/dev/null || true
    echo "REFUSED: PHASE_WRITE_FAILED: failed to write ${OUT_ROOT}/phase.txt (${phase})" >&2
    exit 77
  fi
}

mkdir -p "${OUT_ROOT}" "${LANE3_OUT}/checkpoints" "${LANE3_OUT}/rung_outputs" "/content/wheels" 2>/dev/null || mkdir -p "${OUT_ROOT}" "${LANE3_OUT}/checkpoints" "${LANE3_OUT}/rung_outputs"
: >> "${OUT_ROOT}/setup.log"

# >>> sdlab-hf-token
LANE3_HF_READ_TOKEN=""
LANE3_HF_TOKEN_STAGED=0
for tok_cand in "${WORK_DIR}/lane3_hf_read_token" "/content/lane3_hf_read_token"; do
  if [ -f "${tok_cand}" ]; then
    LANE3_HF_READ_TOKEN="$(cat "${tok_cand}")"
    [ -s "${tok_cand}" ] && LANE3_HF_TOKEN_STAGED=1
    shred -u "${tok_cand}" 2>/dev/null || rm -f "${tok_cand}"
    if [ -e "${tok_cand}" ]; then
      echo "REFUSED: HF_TOKEN_SHRED_FAILED: ${tok_cand} is still on the VM" >&2
      exit 1
    fi
  fi
done
unset HF_TOKEN_GGUF_READ HF_TOKEN HUGGING_FACE_HUB_TOKEN || true
# <<< sdlab-hf-token

# >>> sdlab-lane3-mode
LANE3_MODE="${LANE3_MODE:-install}"
case "${LANE3_MODE}" in
  install)
    export CUDA_VISIBLE_DEVICES=""
    ;;
  train)
    if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L 2>/dev/null | grep -q '^GPU [0-9]'; then
      echo "REFUSED: TRAIN_REQUIRES_GPU: LANE3_MODE=train needs an NVIDIA GPU; nvidia-smi lists none on this VM" >&2
      exit 1
    fi
    if [ -z "${LANE3_MODEL_NAME_OR_PATH:-}" ]; then
      echo "REFUSED: TRAIN_MODEL_REQUIRED: LANE3_MODE=train needs LANE3_MODEL_NAME_OR_PATH (the job's model:name_or_path)" >&2
      exit 1
    fi
    case "${LANE3_MODEL_NAME_OR_PATH}" in
      *[!A-Za-z0-9._/:@-]*)
        echo "REFUSED: TRAIN_MODEL_REQUIRED: LANE3_MODEL_NAME_OR_PATH is not a plain model name or path" >&2
        exit 1
        ;;
    esac
    if ! [[ "${LANE3_MODEL_REVISION:-}" =~ ^[0-9a-f]{40}$ ]]; then
      echo "REFUSED: TRAIN_MODEL_REVISION_REQUIRED: LANE3_MODE=train needs LANE3_MODEL_REVISION, the model repo's 40-hex commit" >&2
      exit 1
    fi
    if ! [[ "${LANE3_HOST_RAM_REQUIRED_GIB:-}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${LANE3_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?$ ]]; then
      echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: LANE3_MODE=train needs LANE3_HOST_RAM_REQUIRED_GIB (MemAvailable the run needs, in GiB)" >&2
      exit 1
    fi
    if ! [[ "${LANE3_DOWNLOAD_MAX_SECONDS:-}" =~ ^[1-9][0-9]*$ ]]; then
      echo "REFUSED: DOWNLOAD_LIMIT_MISSING: LANE3_MODE=train needs LANE3_DOWNLOAD_MAX_SECONDS (the longest projected model download the request accepts)" >&2
      exit 1
    fi
    ;;
  *)
    echo "REFUSED: LANE3_MODE_INVALID: LANE3_MODE=${LANE3_MODE}; expected install or train" >&2
    exit 1
    ;;
esac
# <<< sdlab-lane3-mode

write_phase_atomic setup
LOCK_FILE="${WORK_DIR}/lane3.lock"
OVERRIDE_SHA="$(sha256sum "${LOCK_FILE}" | awk '{print $1}')"
echo "${OVERRIDE_SHA}  ${LOCK_FILE}" > "${LANE3_OUT}/override.sha256"
if [ "${OVERRIDE_SHA}" != "${PINNED_OVERRIDE_SHA}" ]; then
  echo "REFUSED: LOCK_HASH_MISMATCH: ${LOCK_FILE} sha256=${OVERRIDE_SHA} expected=${PINNED_OVERRIDE_SHA}" >&2
  exit 1
fi

if [ "${LANE3_LOCAL_FAST:-0}" = "1" ]; then
  echo "TRAIN_SKIPPED: cpu stub; training needs a GPU rung" | tee -a "${OUT_ROOT}/setup.log"
  python3 - "${PINNED_AI_TOOLKIT_COMMIT}" "${OVERRIDE_SHA}" "${LANE3_MODE}" "${LANE3_OUT}/vm_window.json" << 'FASTEOF'
import json, sys
from pathlib import Path

rec = {"ai_toolkit_commit": sys.argv[1], "override_sha256": f"sha256:{sys.argv[2]}", "lane3_mode": sys.argv[3], "train": "skipped_cpu_stub", "checkpoint_path": None}
Path(sys.argv[4]).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
print("WINDOW_JSON " + json.dumps(rec), flush=True)
FASTEOF
  exit 0
fi

{
  unset UV_SYSTEM_PYTHON || true
  export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_312/install"
  export UV_NO_BUILD=1
  printf 'uv==%s --hash=sha256:%s\n' "${PINNED_UV_VERSION}" "${PINNED_UV_WHEEL_SHA256}" > /content/uv-bootstrap.txt
  pip install --quiet --require-hashes --only-binary :all: --no-deps -r /content/uv-bootstrap.txt
  uv python install "${PINNED_PYTHON_VERSION}"
  uv venv --python "${PINNED_PYTHON_VERSION}" /content/venv-lane3
} 2>&1 | tee -a "${OUT_ROOT}/setup.log"

# >>> sdlab-local-wheels-lock
/content/venv-lane3/bin/python - "${PINNED_LOCAL_WHEELS_MANIFEST_SHA}" << 'WHEELPYEOF'
import hashlib, json, os, sys
from pathlib import Path

want_manifest_sha = sys.argv[1]
work_dir = Path(os.environ.get("CR_WORK_DIR") or "/content")
mf_path = work_dir / "lane3-local-wheels.json" if (work_dir / "lane3-local-wheels.json").is_file() else Path("/content/lane3-local-wheels.json")
wheels_dir = work_dir / "wheels" if (work_dir / "wheels").is_dir() else Path("/content/wheels")
actual_mf_sha = hashlib.sha256(mf_path.read_bytes()).hexdigest()
if actual_mf_sha != want_manifest_sha:
    sys.stderr.write(f"REFUSED: LOCAL_WHEELS_MANIFEST_SHA_MISMATCH: {actual_mf_sha} != {want_manifest_sha}\n")
    raise SystemExit(1)
data = json.loads(mf_path.read_text(encoding="utf-8"))
lines = []
for entry in data.get("wheels", []):
    pkg, ver, fname, exp_sha = entry["package"], entry["version"], entry["filename"], entry["sha256"].lower().removeprefix("sha256:")
    wpath = wheels_dir / fname
    if not wpath.is_file():
        sys.stderr.write(f"REFUSED: LOCAL_WHEEL_MISSING on VM: {wpath}\n")
        raise SystemExit(1)
    actual = hashlib.sha256(wpath.read_bytes()).hexdigest()
    if actual != exp_sha:
        sys.stderr.write(f"REFUSED: LOCAL_WHEEL_SHA_MISMATCH on VM: {fname} expected={exp_sha} actual={actual}\n")
        raise SystemExit(1)
    lines.append(f"{pkg}=={ver} --hash=sha256:{exp_sha}" + chr(10))
out_lock = Path(os.environ.get("LANE3_OUT") or "/content/lane3_out") / "local-wheels.lock"
out_lock.parent.mkdir(parents=True, exist_ok=True)
out_lock.write_text("".join(lines), encoding="utf-8")
WHEELPYEOF
# <<< sdlab-local-wheels-lock

# Production ai-toolkit clone + hash-locked install + import gate + optional train
{
  if [ ! -d /content/ai-toolkit ]; then
    git clone "${PINNED_AI_TOOLKIT_REPO}" /content/ai-toolkit
  fi
  git -C /content/ai-toolkit fetch --depth 1 origin "${PINNED_AI_TOOLKIT_COMMIT}" || true
  git -C /content/ai-toolkit checkout "${PINNED_AI_TOOLKIT_COMMIT}"
  WHEELS_DIR="${WORK_DIR}/wheels"
  [ -d "${WHEELS_DIR}" ] || WHEELS_DIR="/content/wheels"
  set +e
  uv pip install --python /content/venv-lane3/bin/python --require-hashes --only-binary :all: --extra-index-url "${PINNED_PYTORCH_INDEX_URL}" --index-strategy unsafe-best-match -r "${LOCK_FILE}" > "${LANE3_OUT}/wheels.log" 2>&1
  UV_RC1=$?
  uv pip install --python /content/venv-lane3/bin/python --require-hashes --only-binary :all: --no-index --find-links "${WHEELS_DIR}" --no-deps -r "${LANE3_OUT}/local-wheels.lock" >> "${LANE3_OUT}/wheels.log" 2>&1
  UV_RC2=$?
  set -e
  cat "${LANE3_OUT}/wheels.log"
  if [ "${UV_RC1}" -ne 0 ] || [ "${UV_RC2}" -ne 0 ]; then
    /content/venv-lane3/bin/python "${WORK_DIR}/classify_install_log.py" --lane lane3 --log "${LANE3_OUT}/wheels.log" >&2 \
      || echo "REFUSED: INSTALL_FAILED during lane3 lock install" >&2
    exit 1
  fi
  /content/venv-lane3/bin/python -c '
import importlib, sys
REQUIRED = ("sentencepiece", "torch", "torchaudio", "safetensors", "yaml", "oyaml", "PIL", "diffusers", "lycoris")
for m in REQUIRED:
    mod = importlib.import_module(m)
    mod_file = getattr(mod, "__file__", None) or ""
    print(f"VENV_IMPORT {m} {mod_file}", flush=True)
    if not mod_file.startswith("/content/venv-lane3/"):
        sys.stderr.write(f"REFUSED: VENV_IMPORT_OUTSIDE_VENV {m}: {mod_file}\n")
        raise SystemExit(1)
import sentencepiece as spm
print("SENTENCEPIECE_OK", spm.__version__, flush=True)
' | tee "${LANE3_OUT}/sentencepiece.txt"
} 2>&1 | tee -a "${OUT_ROOT}/setup.log"

# >>> sdlab-train-or-skip
CHECKPOINT_PATH=""
if [ "${LANE3_MODE:-install}" != "train" ]; then
  write_phase_atomic run
  LANE3_TRAIN_STATE="skipped_cpu_stub"
  echo "TRAIN_SKIPPED: cpu stub; training needs a GPU rung" | tee -a "${LANE3_OUT}/setup.log"
else
  LANE3_TRAIN_STATE="trained"
  # >>> sdlab-lane3-train
  LANE3_PY="/content/venv-lane3/bin/python"
  LANE3_HF_HOME="/content/hf_home"
  LANE3_TRAINING_FOLDER="/content/lane3_train"
  LANE3_DATASET_DIR="/content/lane3_dataset"
  mkdir -p "${LANE3_HF_HOME}" "${LANE3_TRAINING_FOLDER}" "${LANE3_OUT}/rung_outputs"
  "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" guards --hf-home "${LANE3_HF_HOME}" --training-folder "${LANE3_TRAINING_FOLDER}" \
    --disk-required-gib "${LANE3_DISK_REQUIRED_GIB}" --smoke-seconds "${LANE3_GPU_SMOKE_SECONDS}" --ram-required-gib "${LANE3_HOST_RAM_REQUIRED_GIB:-}" \
    --meminfo /proc/meminfo --shm /dev/shm --out "${LANE3_OUT}/train_guards.json" 2>&1 | tee -a "${LANE3_OUT}/setup.log"
  if [ "${LANE3_HF_TOKEN_STAGED:-0}" = "1" ]; then
    HF_TOKEN_GGUF_READ="${LANE3_HF_READ_TOKEN}" "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" download \
      --repo "${LANE3_MODEL_NAME_OR_PATH}" --revision "${LANE3_MODEL_REVISION:-}" --hf-home "${LANE3_HF_HOME}" \
      --max-seconds "${LANE3_DOWNLOAD_MAX_SECONDS:-}" --probe-seconds "${LANE3_DOWNLOAD_PROBE_SECONDS}" \
      --probe-bytes "${LANE3_DOWNLOAD_PROBE_BYTES}" --log "${LANE3_OUT}/model_download.log" \
      --out "${LANE3_OUT}/model_download.json" 2>&1 | tee -a "${LANE3_OUT}/setup.log"
  else
    "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" download \
      --repo "${LANE3_MODEL_NAME_OR_PATH}" --revision "${LANE3_MODEL_REVISION:-}" --hf-home "${LANE3_HF_HOME}" \
      --max-seconds "${LANE3_DOWNLOAD_MAX_SECONDS:-}" --probe-seconds "${LANE3_DOWNLOAD_PROBE_SECONDS}" \
      --probe-bytes "${LANE3_DOWNLOAD_PROBE_BYTES}" --log "${LANE3_OUT}/model_download.log" \
      --out "${LANE3_OUT}/model_download.json" 2>&1 | tee -a "${LANE3_OUT}/setup.log"
  fi
  LANE3_HF_READ_TOKEN=""
  LANE3_MODEL_PATH="$("${LANE3_PY}" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["snapshot_path"])' "${LANE3_OUT}/model_download.json")"
  "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" dataset --manifest "${WORK_DIR}/rung-dataset.json" --dest "${LANE3_DATASET_DIR}" --src "${WORK_DIR}" 2>&1 | tee -a "${LANE3_OUT}/setup.log"
  "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" render-job --template "${WORK_DIR}/rung-qwen-image.yaml" --out "${LANE3_OUT}/rung_job.yaml" \
    --training-folder "${LANE3_TRAINING_FOLDER}" --dataset-dir "${LANE3_DATASET_DIR}" --model-path "${LANE3_MODEL_PATH}" 2>&1 | tee -a "${LANE3_OUT}/setup.log"
  write_phase_atomic run
  HF_HOME="${LANE3_HF_HOME}" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    /content/venv-lane3/bin/python /content/ai-toolkit/run.py "${LANE3_OUT}/rung_job.yaml" > "${LANE3_OUT}/train.log" 2>&1 &
  TRAIN_PID=$!
  "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" copy-off --watch "${LANE3_TRAINING_FOLDER}" --bundle "${LANE3_OUT}/rung_outputs" \
    --manifest "${LANE3_OUT}/rung_outputs/manifest.jsonl" --pid "${TRAIN_PID}" --train-log "${LANE3_OUT}/train.log" &
  COPY_PID=$!
  set +e
  wait "${TRAIN_PID}"; TRAIN_RC=$?
  wait "${COPY_PID}" || true
  set -e
  if [ "${TRAIN_RC}" -ne 0 ]; then
    tail -n 40 "${LANE3_OUT}/train.log" >&2 || true
    echo "REFUSED: TRAIN_FAILED: ai-toolkit run.py exited ${TRAIN_RC}" >&2
    exit 1
  fi
  "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" write-train-manifest --watch "${LANE3_TRAINING_FOLDER}" --out "${LANE3_OUT}/training_folder_manifest.json"
  "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" copy-off --final-only --watch "${LANE3_TRAINING_FOLDER}" --bundle "${LANE3_OUT}/rung_outputs" --manifest "${LANE3_OUT}/rung_outputs/manifest.jsonl"
  FOUND_CKPT="$("${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" checkpoint --bundle "${LANE3_OUT}/rung_outputs" --manifest "${LANE3_OUT}/rung_outputs/manifest.jsonl" || true)"
  if [ -z "${FOUND_CKPT}" ]; then
    echo "REFUSED: TRAIN_CHECKPOINT_MISSING: no complete .safetensors checkpoint was copied off" >&2
    exit 1
  fi
  CHECKPOINT_PATH="${FOUND_CKPT}"
  "${LANE3_PY}" "${WORK_DIR}/lane3_rung.py" finish --lane3-out "${LANE3_OUT}"
  # <<< sdlab-lane3-train
fi
# <<< sdlab-train-or-skip

# >>> sdlab-lane3-window
/content/venv-lane3/bin/python - "${PINNED_AI_TOOLKIT_COMMIT}" "${OVERRIDE_SHA}" "${LANE3_MODE:-install}" "${LANE3_TRAIN_STATE}" "${CHECKPOINT_PATH}" "${LANE3_OUT}/vm_window.json" << 'WINPYEOF'
import json, sys
from pathlib import Path

rec = {
    "ai_toolkit_commit": sys.argv[1],
    "override_sha256": f"sha256:{sys.argv[2]}",
    "lane3_mode": sys.argv[3],
    "train": sys.argv[4],
    "checkpoint_path": sys.argv[5] or None,
}
facts_p = Path(sys.argv[6]).parent / "train_facts.json"
if facts_p.is_file():
    rec.update(json.loads(facts_p.read_text(encoding="utf-8")))
Path(sys.argv[6]).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
print("WINDOW_JSON " + json.dumps(rec), flush=True)
WINPYEOF
# <<< sdlab-lane3-window
