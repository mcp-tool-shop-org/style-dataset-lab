#!/usr/bin/env bash
# VM job entrypoint for Lane 1 (render), executed inside colab-runner.
# Mode selection via env:
#   LANE1_MODE=stub (default) | render_cpu_stub | render
#   LANE1_SYNTHETIC_PROOF=1    (optional CPU/T4 synthetic fixture proof without HF/ComfyUI)
#   LANE1_LOCAL_FAST=1         (optional offline unit/--local-cpu test mode without network uv)
set -euo pipefail

PINNED_UV_VERSION="0.13.5"
PINNED_UV_WHEEL_SHA256="fa8d26e08e34c29c0c4e820cf3181757086d547240b4f4d31ff1d8bd810ca946"
PINNED_PYTHON_VERSION="3.14.9"
PINNED_PYTHON_BUILD="20261021"
PINNED_PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu130"
PINNED_COMFYUI_REPO="https://github.com/comfyanonymous/ComfyUI.git"
PINNED_COMFYUI_COMMIT="49b61c3cd044fb65acd97a960467a00414694146"
PINNED_COMFY_HEADLESS_SPEC="comfy-headless==3.1.0"
PINNED_LOCK_SHA="619e7105be1bead576aecae2bfc4c5318c6a5f9935a6e12e85c7d8163ca594dd"

LANE1_DISK_REQUIRED_GIB="${LANE1_DISK_REQUIRED_GIB:-50}"
LANE1_GPU_SMOKE_SECONDS="${LANE1_GPU_SMOKE_SECONDS:-5}"
LANE1_DOWNLOAD_PROBE_SECONDS="${LANE1_DOWNLOAD_PROBE_SECONDS:-60}"
LANE1_DOWNLOAD_PROBE_BYTES="${LANE1_DOWNLOAD_PROBE_BYTES:-2147483648}"
LANE1_COMFY_PORT="${LANE1_COMFY_PORT:-8188}"

WORK_DIR="${CR_WORK_DIR:-$(pwd)}"
OUT_ROOT="${CR_OUT_DIR:-/content/lane1_out}"
LANE1_OUT="${OUT_ROOT}/lane1_out"
COMFY_PID=""

cleanup_procs() {
  if [ -n "${COMFY_PID:-}" ]; then
    kill "${COMFY_PID}" 2>/dev/null || true
    COMFY_PID=""
  fi
}
trap cleanup_procs EXIT

write_phase_atomic() {
  local phase="$1"
  mkdir -p "${OUT_ROOT}" "${LANE1_OUT}"
  local tmp="${OUT_ROOT}/.phase.txt.tmp.$$"
  if ! { printf '%s\n' "${phase}" > "${tmp}" && mv -f "${tmp}" "${OUT_ROOT}/phase.txt"; }; then
    rm -f "${tmp}" 2>/dev/null || true
    echo "REFUSED: PHASE_WRITE_FAILED: failed to write ${OUT_ROOT}/phase.txt (${phase})" >&2
    exit 77
  fi
}

mkdir -p "${OUT_ROOT}" "${LANE1_OUT}/pngs" "${LANE1_OUT}/copy_back"
: >> "${OUT_ROOT}/setup.log"

# >>> sdlab-hf-token
LANE1_HF_READ_TOKEN=""
LANE1_HF_TOKEN_STAGED=0
for tok_cand in "${WORK_DIR}/lane1_hf_read_token" "/content/lane1_hf_read_token"; do
  if [ -f "${tok_cand}" ]; then
    LANE1_HF_READ_TOKEN="$(cat "${tok_cand}")"
    [ -s "${tok_cand}" ] && LANE1_HF_TOKEN_STAGED=1
    shred -u "${tok_cand}" 2>/dev/null || rm -f "${tok_cand}"
    if [ -e "${tok_cand}" ]; then
      echo "REFUSED: HF_TOKEN_SHRED_FAILED: ${tok_cand} is still on the VM" >&2
      exit 1
    fi
  fi
done
unset HF_TOKEN_GGUF_READ HF_TOKEN HUGGING_FACE_HUB_TOKEN || true
# <<< sdlab-hf-token

# >>> sdlab-lane1-mode
LANE1_MODE="${LANE1_MODE:-stub}"
case "${LANE1_MODE}" in
  stub)
    export CUDA_VISIBLE_DEVICES=""
    ;;
  render_cpu_stub)
    export CUDA_VISIBLE_DEVICES=""
    if [ "${LANE1_LOCAL_FAST:-0}" != "1" ]; then
      if ! [[ "${LANE1_HOST_RAM_REQUIRED_GIB:-}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${LANE1_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?$ ]]; then
        echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: LANE1_MODE=render_cpu_stub needs LANE1_HOST_RAM_REQUIRED_GIB" >&2
        exit 1
      fi
      if ! [[ "${LANE1_DOWNLOAD_MAX_SECONDS:-}" =~ ^[1-9][0-9]*$ ]]; then
        echo "REFUSED: DOWNLOAD_LIMIT_MISSING: LANE1_MODE=render_cpu_stub needs LANE1_DOWNLOAD_MAX_SECONDS" >&2
        exit 1
      fi
    fi
    ;;
  render)
    if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L 2>/dev/null | grep -q '^GPU [0-9]'; then
      echo "REFUSED: RENDER_REQUIRES_GPU: LANE1_MODE=render needs an NVIDIA GPU; nvidia-smi lists none on this VM" >&2
      exit 1
    fi
    if [ "${LANE1_SYNTHETIC_PROOF:-0}" != "1" ]; then
      if ! [[ "${LANE1_JOBS_SHA256:-}" =~ ^[0-9a-f]{64}$ ]]; then
        echo "REFUSED: RENDER_JOBS_SHA_REQUIRED: LANE1_MODE=render needs LANE1_JOBS_SHA256 (64-hex)" >&2
        exit 1
      fi
      if ! [[ "${LANE1_COPY_BACK_EVERY:-}" =~ ^[1-9][0-9]*$ ]]; then
        echo "REFUSED: RENDER_COPY_BACK_REQUIRED: LANE1_MODE=render needs LANE1_COPY_BACK_EVERY" >&2
        exit 1
      fi
      if ! [[ "${LANE1_HOST_RAM_REQUIRED_GIB:-}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${LANE1_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?$ ]]; then
        echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: LANE1_MODE=render needs LANE1_HOST_RAM_REQUIRED_GIB" >&2
        exit 1
      fi
      if ! [[ "${LANE1_DOWNLOAD_MAX_SECONDS:-}" =~ ^[1-9][0-9]*$ ]]; then
        echo "REFUSED: DOWNLOAD_LIMIT_MISSING: LANE1_MODE=render needs LANE1_DOWNLOAD_MAX_SECONDS" >&2
        exit 1
      fi
    fi
    ;;
  *)
    echo "REFUSED: LANE1_MODE_INVALID: LANE1_MODE=${LANE1_MODE}; expected stub, render_cpu_stub or render" >&2
    exit 1
    ;;
esac
# <<< sdlab-lane1-mode

write_phase_atomic setup

LOCK_PATH="${WORK_DIR}/lane1.lock"
ACTUAL_LOCK_SHA="$(sha256sum "${LOCK_PATH}" | awk '{print $1}')"
echo "${ACTUAL_LOCK_SHA}  ${LOCK_PATH}" > "${LANE1_OUT}/lock.sha256"
if [ "${ACTUAL_LOCK_SHA}" != "${PINNED_LOCK_SHA}" ]; then
  echo "REFUSED: LOCK_HASH_MISMATCH: ${LOCK_PATH} sha256=${ACTUAL_LOCK_SHA} expected=${PINNED_LOCK_SHA}" >&2
  exit 1
fi

write_synthetic_png_outputs() {
  local py_bin="$1"
  local render_state="$2"
  local prefix="$3"
  "${py_bin}" - "${LANE1_OUT}" "${render_state}" "${prefix}" "${PINNED_COMFYUI_COMMIT}" << 'SYNTHEOF'
import hashlib, json, struct, sys, zlib
from pathlib import Path

out_dir = Path(sys.argv[1])
render_state, prefix, comfyui_commit = sys.argv[2], sys.argv[3], sys.argv[4]
pngs_dir, copy_dir = out_dir / "pngs", out_dir / "copy_back"
pngs_dir.mkdir(parents=True, exist_ok=True)
copy_dir.mkdir(parents=True, exist_ok=True)

def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

def _text_chunk(k: str, v: str) -> bytes:
    return _chunk(b"tEXt", k.encode("latin-1") + b"\x00" + v.encode("latin-1"))

def _make_png(seed: int, gpu_tag: str) -> bytes:
    w, h = 64, 64
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            rows.extend(((x * 4 + seed) & 255, (y * 4 + seed) & 255, ((x ^ y) * 3) & 255))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + _text_chunk("sdlab:licence", "CC-BY-4.0")
        + _text_chunk("sdlab:credit", "mcp-tool-shop")
        + _text_chunk("sdlab:proof", gpu_tag)
        + _chunk(b"IDAT", zlib.compress(bytes(rows)))
        + _chunk(b"IEND", b"")
    )

gpu_info = {"device": None, "cuda_matmul_ok": False}
if prefix.startswith("t4"):
    import torch
    assert torch.cuda.is_available(), "CUDA requested for live GPU proof but unavailable"
    a = torch.randn((512, 512), device="cuda")
    b = torch.randn((512, 512), device="cuda")
    c = (a @ b).mean().item()
    torch.cuda.synchronize()
    gpu_info = {"device": torch.cuda.get_device_name(0), "cuda_matmul_ok": True, "sample_mean": round(float(c), 6)}

rows = []
for idx in (1, 2):
    jid = f"{prefix}_0{idx}"
    raw = _make_png(100 + idx, f"{render_state}:{gpu_info.get('device') or 'cpu'}")
    p = pngs_dir / f"{jid}.png"
    cp = copy_dir / f"{jid}.png"
    p.write_bytes(raw)
    cp.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    rows.append({"job_id": jid, "status": "ok", "sha256": sha, "licence": "CC-BY-4.0", "credit": "mcp-tool-shop"})

(out_dir / "renders.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
win = {
    "python": sys.version.split()[0],
    "comfyui_commit": comfyui_commit,
    "render_state": render_state,
    "synthetic_proof": True,
    "gpu": gpu_info,
    "rendered": len(rows),
}
(out_dir / "vm_window.json").write_text(json.dumps(win, indent=2) + "\n", encoding="utf-8")
print("SYNTHETIC_PROOF_OK", json.dumps(win), flush=True)
SYNTHEOF
}

if [ "${LANE1_LOCAL_FAST:-0}" = "1" ]; then
  write_phase_atomic run
  write_synthetic_png_outputs python3 "local_fast_stub" "local" 2>&1 | tee -a "${OUT_ROOT}/setup.log"
  exit 0
fi

bootstrap_uv_python() {
  unset UV_SYSTEM_PYTHON || true
  export UV_PYTHON_INSTALL_DIR="${OUT_ROOT}/.sdlab_python_314/install"
  export UV_NO_BUILD=1
  printf 'uv==%s --hash=sha256:%s\n' "${PINNED_UV_VERSION}" "${PINNED_UV_WHEEL_SHA256}" > "${OUT_ROOT}/uv-bootstrap.txt"
  pip install --quiet --require-hashes --only-binary :all: --no-deps -r "${OUT_ROOT}/uv-bootstrap.txt"
  uv python install "${PINNED_PYTHON_VERSION}"
  uv venv --python "${PINNED_PYTHON_VERSION}" "${OUT_ROOT}/venv-lane1"
  "${OUT_ROOT}/venv-lane1/bin/python" - "${PINNED_PYTHON_VERSION}" "${PINNED_PYTHON_BUILD}" "${UV_PYTHON_INSTALL_DIR}" "${LANE1_OUT}/python_identity.json" << 'PYIDEOF'
import hashlib, json, subprocess, sys
from pathlib import Path

version, want_build, install_dir, out_json = sys.argv[1:5]
key = f"cpython-{version}-linux-x86_64-gnu"
inst = Path(install_dir) / key
build_f = inst / "BUILD"
build = build_f.read_text(encoding="utf-8").strip() if build_f.is_file() else None
binary = inst / "bin" / f"python{'.'.join(version.split('.')[:2])}"
binary_sha = f"sha256:{hashlib.sha256(binary.resolve().read_bytes()).hexdigest()}" if binary.is_file() else None
listing = subprocess.run(["uv", "python", "list", version, "--only-downloads", "--output-format", "json"], capture_output=True, text=True, check=False)
download_url = next((e.get("url") for e in json.loads(listing.stdout or "[]") if e.get("key") == key), None) if listing.returncode == 0 else None
rec = {"key": key, "build": build, "pinned_build": want_build, "download_url": download_url, "sys_version": sys.version, "binary_sha256": binary_sha}
Path(out_json).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
print("PYTHON_IDENTITY " + json.dumps(rec), flush=True)
if build != want_build or binary_sha is None:
    sys.stderr.write(f"REFUSED: PYTHON_BUILD_MISMATCH: {key} build={build!r} pinned={want_build}\n")
    raise SystemExit(1)
PYIDEOF
}

if [ "${LANE1_SYNTHETIC_PROOF:-0}" = "1" ]; then
  bootstrap_uv_python 2>&1 | tee -a "${OUT_ROOT}/setup.log"
  write_phase_atomic run
  if [ "${LANE1_MODE}" = "render" ]; then
    write_synthetic_png_outputs python3 "rendered_synthetic_proof" "t4" 2>&1 | tee -a "${OUT_ROOT}/setup.log"
  else
    write_synthetic_png_outputs "${OUT_ROOT}/venv-lane1/bin/python" "stub_synthetic_proof" "stub" 2>&1 | tee -a "${OUT_ROOT}/setup.log"
  fi
  exit 0
fi

# Production / full ComfyUI + weights path
bootstrap_uv_python 2>&1 | tee -a "${OUT_ROOT}/setup.log"
{
  if [ ! -d /content/ComfyUI ]; then
    git clone "${PINNED_COMFYUI_REPO}" /content/ComfyUI
  fi
  git -C /content/ComfyUI fetch --depth 1 origin "${PINNED_COMFYUI_COMMIT}" || true
  git -C /content/ComfyUI checkout "${PINNED_COMFYUI_COMMIT}"
  ACTUAL_COMFYUI_COMMIT="$(git -C /content/ComfyUI rev-parse HEAD)"
  if [ "${ACTUAL_COMFYUI_COMMIT}" != "${PINNED_COMFYUI_COMMIT}" ]; then
    echo "REFUSED: PIN_NOT_FOUND: ComfyUI commit mismatch: got ${ACTUAL_COMFYUI_COMMIT}, expected ${PINNED_COMFYUI_COMMIT}" >&2
    exit 1
  fi
  set +e
  uv pip install --python "${OUT_ROOT}/venv-lane1/bin/python" --require-hashes --only-binary :all: --extra-index-url "${PINNED_PYTORCH_INDEX_URL}" --index-strategy unsafe-best-match -r "${LOCK_PATH}" > "${LANE1_OUT}/wheels.log" 2>&1
  UV_RC=$?
  set -e
  cat "${LANE1_OUT}/wheels.log"
  if [ "${UV_RC}" -ne 0 ]; then
    "${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/classify_install_log.py" --lane lane1 --log "${LANE1_OUT}/wheels.log" >&2 \
      || echo "REFUSED: INSTALL_FAILED during lane1 lock install" >&2
    exit 1
  fi
} 2>&1 | tee -a "${OUT_ROOT}/setup.log"

if [ "${LANE1_MODE}" = "stub" ]; then
  write_phase_atomic run
  "${OUT_ROOT}/venv-lane1/bin/python" /content/ComfyUI/main.py --cpu --listen 127.0.0.1 --port "${LANE1_COMFY_PORT}" --disable-auto-launch \
    > "${LANE1_OUT}/comfyui.log" 2>&1 &
  COMFY_PID="$!"
  for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${LANE1_COMFY_PORT}/system_stats" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  cat > "${LANE1_OUT}/jobs.jsonl" << 'JOBSEOF'
{"job_id":"stub_01","run_id":"run_stub_01","template_id":"stub_fixture_64","seed":101,"width":64,"height":64,"canon_sha":"a881cb5ba656e0618080d2269498fda7f36ac93a","entry_id":"ships/brig","entry_sha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111","licence":"CC-BY-4.0","credit":"mcp-tool-shop","workflow_sha":"sha256:2222222222222222222222222222222222222222222222222222222222222222"}
{"job_id":"stub_02","run_id":"run_stub_01","template_id":"stub_fixture_64","seed":102,"width":64,"height":64,"canon_sha":"a881cb5ba656e0618080d2269498fda7f36ac93a","entry_id":"ships/brig","entry_sha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111","licence":"CC-BY-4.0","credit":"mcp-tool-shop","workflow_sha":"sha256:2222222222222222222222222222222222222222222222222222222222222222"}
JOBSEOF
  "${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/lane1_render.py" --cpu --bootstrap --comfy-pid "${COMFY_PID}" --comfyui-commit "${PINNED_COMFYUI_COMMIT}" \
    --window-json "${LANE1_OUT}/vm_window.json" --jobs "${LANE1_OUT}/jobs.jsonl" --renders "${LANE1_OUT}/renders.jsonl" \
    --out-dir "${LANE1_OUT}/pngs" --copy-back-dir "${LANE1_OUT}/copy_back" --copy-back-every 1
  cleanup_procs
  exit 0
fi

LANE1_HF_HOME="/content/hf_home"
LANE1_MODELS_DIR="/content/ComfyUI/models"
mkdir -p "${LANE1_HF_HOME}" "${LANE1_MODELS_DIR}"
GUARDS_EXTRA_ARGS=()
[ "${LANE1_MODE}" = "render_cpu_stub" ] && GUARDS_EXTRA_ARGS+=("--cpu-stub")
"${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/lane1_render.py" --vm-guards --hf-home "${LANE1_HF_HOME}" --models-dir "${LANE1_MODELS_DIR}" \
  --lane1-out "${LANE1_OUT}" --disk-required-gib "${LANE1_DISK_REQUIRED_GIB}" --smoke-seconds "${LANE1_GPU_SMOKE_SECONDS}" \
  --ram-required-gib "${LANE1_HOST_RAM_REQUIRED_GIB}" --meminfo /proc/meminfo --shm /dev/shm --guards-out "${LANE1_OUT}/render_guards.json" \
  "${GUARDS_EXTRA_ARGS[@]}" 2>&1 | tee -a "${OUT_ROOT}/setup.log"

if [ "${LANE1_HF_TOKEN_STAGED:-0}" = "1" ]; then
  HF_TOKEN_GGUF_READ="${LANE1_HF_READ_TOKEN}" "${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/lane1_render.py" --download-weights \
    --weights-manifest "${WORK_DIR}/weights_manifest.json" --hf-home "${LANE1_HF_HOME}" --models-dir "${LANE1_MODELS_DIR}" \
    --max-seconds "${LANE1_DOWNLOAD_MAX_SECONDS}" --probe-seconds "${LANE1_DOWNLOAD_PROBE_SECONDS}" --probe-bytes "${LANE1_DOWNLOAD_PROBE_BYTES}" \
    --download-log "${LANE1_OUT}/weights_download.log" --download-out "${LANE1_OUT}/weights_download.json" 2>&1 | tee -a "${OUT_ROOT}/setup.log"
else
  "${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/lane1_render.py" --download-weights \
    --weights-manifest "${WORK_DIR}/weights_manifest.json" --hf-home "${LANE1_HF_HOME}" --models-dir "${LANE1_MODELS_DIR}" \
    --max-seconds "${LANE1_DOWNLOAD_MAX_SECONDS}" --probe-seconds "${LANE1_DOWNLOAD_PROBE_SECONDS}" --probe-bytes "${LANE1_DOWNLOAD_PROBE_BYTES}" \
    --download-log "${LANE1_OUT}/weights_download.log" --download-out "${LANE1_OUT}/weights_download.json" 2>&1 | tee -a "${OUT_ROOT}/setup.log"
fi
LANE1_HF_READ_TOKEN=""
export HF_HUB_OFFLINE=1

if [ "${LANE1_MODE}" = "render_cpu_stub" ]; then
  "${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/lane1_render.py" --merge-render-facts --lane1-out "${LANE1_OUT}" --render-state skipped_cpu_stub
  echo "RENDER_CPU_STUB_OK: weights downloaded, sha256-checked and unpacked on CPU" | tee -a "${OUT_ROOT}/setup.log"
  exit 0
fi

ACTUAL_JOBS_SHA="$(sha256sum "${WORK_DIR}/jobs.jsonl" | awk '{print $1}')"
if [ "${ACTUAL_JOBS_SHA}" != "${LANE1_JOBS_SHA256}" ]; then
  echo "REFUSED: JOBS_SHA_MISMATCH: ${WORK_DIR}/jobs.jsonl sha256=${ACTUAL_JOBS_SHA} expected=${LANE1_JOBS_SHA256}" >&2
  exit 1
fi
cp -f "${WORK_DIR}/jobs.jsonl" "${LANE1_OUT}/jobs.jsonl"
write_phase_atomic run
COMFY_URL="http://127.0.0.1:${LANE1_COMFY_PORT}"
"${OUT_ROOT}/venv-lane1/bin/python" /content/ComfyUI/main.py --listen 127.0.0.1 --port "${LANE1_COMFY_PORT}" --disable-auto-launch \
  > "${LANE1_OUT}/comfyui.log" 2>&1 &
COMFY_PID="$!"
COMFY_READY=0
for _ in $(seq 1 120); do
  if curl -sf "${COMFY_URL}/system_stats" >/dev/null 2>&1; then COMFY_READY=1; break; fi
  if ! kill -0 "${COMFY_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if [ "${COMFY_READY}" -ne 1 ]; then
  tail -n 40 "${LANE1_OUT}/comfyui.log" >&2 || true
  echo "REFUSED: COMFY_STARTUP_FAILED: ComfyUI failed to listen on ${COMFY_URL}" >&2
  exit 1
fi
QUEUE_EXTRA=(--max-consecutive-failures "${LANE1_MAX_CONSECUTIVE_FAILURES:-2}")
[ -n "${LANE1_JOB_TIMEOUT_S:-}" ] && QUEUE_EXTRA+=(--job-timeout-s "${LANE1_JOB_TIMEOUT_S}")
"${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/lane1_render.py" --bootstrap --window-id "${CR_RUN_ID:-win_lane1_render}" \
  --comfy-url "${COMFY_URL}" --comfy-pid "${COMFY_PID}" --comfyui-commit "${PINNED_COMFYUI_COMMIT}" \
  --window-json "${LANE1_OUT}/vm_window.json" --jobs "${LANE1_OUT}/jobs.jsonl" --renders "${LANE1_OUT}/renders.jsonl" \
  --out-dir "${LANE1_OUT}/pngs" --copy-back-dir "${LANE1_OUT}/copy_back" --copy-back-every "${LANE1_COPY_BACK_EVERY}" "${QUEUE_EXTRA[@]}"
cleanup_procs
RENDER_STATE="rendered"
grep -q '"status": "failed"' "${LANE1_OUT}/renders.jsonl" 2>/dev/null && RENDER_STATE="rendered_with_failures"
"${OUT_ROOT}/venv-lane1/bin/python" "${WORK_DIR}/lane1_render.py" --merge-render-facts --lane1-out "${LANE1_OUT}" --render-state "${RENDER_STATE}"
