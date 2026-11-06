#!/usr/bin/env bash
# Shared body of the lane 3 GPU-rung local walks (walk_a_real_load.sh, walk_b_quantised.sh): run the
# kit's own train-mode remote script on the rig's GPU, in WSL, in a bwrap-bound /content, with the
# kit's own uploads staged flat as a window leaves them, and instruments around it. Sourced, not run.
#
# Required arguments (no defaults; each missing one is WALK_ARG_MISSING):
#   --wheel-dir <dir>      the two pre-built local wheels lane3-local-wheels.json lists
#   --hf-home <dir>        an HF home whose hub/ holds Qwen/Qwen-Image at the pinned revision (and,
#                          for walk (b), the accuracy recovery adapter); bound READ-ONLY to
#                          /content/hf_home, with the hub offline
#   --dataset-dir <dir>    the images scripts/colab/lane3/rung-dataset.json lists (sha256-checked)
#   --evidence-root <dir>  where <UTC timestamp>-walk-a|b/ is written; must be under /mnt/e/ (a
#                          persistent disk, never WSL's tmpfs)
#   --wall-s <seconds>     the walk's wall-clock cap, enforced by `timeout --kill-after` around the
#                          whole sandbox (and by the sampler)
# Modes (run in this order):
#   --check                every step that needs no GPU and no network (arguments, inputs, emit,
#                          staging), then print the exact command and stop
#   --prepare              install mode WITH network, no GPU, no HF cache: installs the venv,
#                          CPython and ai-toolkit into ${HOME}/sdlab-gpu-walk/content, fills the uv
#                          cache, fetches the pinned uv wheel for offline pip, writes prepared.ok
#   --offline-install-check  install mode with the GPU run's sandbox (no network, no GPU): proves
#                          the offline reinstall the GPU run depends on
#   (no mode)              the GPU run: needs prepared.ok for this kit; no network (--unshare-net),
#                          HF_HUB_OFFLINE=1, read-only HF cache, GPU_BUSY check, VRAM ceiling
# Refusals: WALK_ARG_MISSING, WALK_ARG_INVALID, WALK_INPUT_MISSING, WALK_NOT_PREPARED, GPU_BUSY
# (another process holds more than 2 GiB on the GPU, named), each one `REFUSED: <CODE>: <detail>`.
set -euo pipefail

WALK_KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WALK_REVISION="75e0b4be04f60ec59a75f475837eced720f823b6"
WALK_MODEL="Qwen/Qwen-Image"
WALK_ARA_REPO_DIR="models--ostris--accuracy_recovery_adapters"
WALK_ARA_REVISION="daf7bdfa5878178b1bde518336ad672dd914bdae"
WALK_ARA_FILE="qwen_image_torchao_uint3.safetensors"
# The idle 5090's Windows desktop holds about 2,100 MiB (no compute job), so GPU_BUSY trips above
# 3 GiB; the baseline read at start is logged, and the walk's own use (memory.used minus that
# baseline) is bounded at 28 GiB, so the card never goes past about 30 GiB in total.
WALK_GPU_BUSY_MAX_MIB="3072"
WALK_VRAM_CEILING_MIB="28672"
WALK_MEM_FLOOR_GIB="2"
WALK_NVIDIA_SMI="/usr/lib/wsl/lib/nvidia-smi"
WALK_WINDOWS_SMI="/mnt/c/Windows/System32/nvidia-smi.exe"
WALK_UV_WHEEL="uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"

walk_refuse() {
  echo "REFUSED: $1: $2" >&2
  exit 2
}

walk_main() {
  local which="$1"
  shift
  local wheel_dir="" hf_home="" dataset_dir="" evidence_root="" wall_s="" mode="gpu"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --wheel-dir) wheel_dir="${2:-}"; shift 2 ;;
      --hf-home) hf_home="${2:-}"; shift 2 ;;
      --dataset-dir) dataset_dir="${2:-}"; shift 2 ;;
      --evidence-root) evidence_root="${2:-}"; shift 2 ;;
      --wall-s) wall_s="${2:-}"; shift 2 ;;
      --check) mode="check"; shift ;;
      --prepare) mode="prepare"; shift ;;
      --offline-install-check) mode="offline-install"; shift ;;
      *) walk_refuse WALK_ARG_INVALID "unknown argument $1" ;;
    esac
  done
  local a
  for a in wheel_dir hf_home dataset_dir evidence_root wall_s; do
    [ -n "${!a}" ] || walk_refuse WALK_ARG_MISSING "--${a//_/-} is required (there is no default)"
  done
  [[ "${wall_s}" =~ ^[1-9][0-9]*$ ]] || walk_refuse WALK_ARG_INVALID "--wall-s ${wall_s} is not a whole number of seconds"
  case "${evidence_root}" in
    /mnt/e/*) ;;
    *) walk_refuse WALK_ARG_INVALID "--evidence-root ${evidence_root} must be under /mnt/e/ (persistent; WSL's /tmp is tmpfs)" ;;
  esac
  command -v bwrap >/dev/null || walk_refuse WALK_INPUT_MISSING "bwrap is not installed"
  local py="${WALK_PYTHON:-$(command -v python3)}"

  local snapshot="${hf_home}/hub/models--Qwen--Qwen-Image/snapshots/${WALK_REVISION}"
  [ -f "${snapshot}/transformer/diffusion_pytorch_model.safetensors.index.json" ] \
    || walk_refuse WALK_INPUT_MISSING "${WALK_MODEL} at ${WALK_REVISION} is not in ${hf_home} (download it first: hf download ${WALK_MODEL} --revision ${WALK_REVISION})"
  local ara_host="${hf_home}/hub/${WALK_ARA_REPO_DIR}/snapshots/${WALK_ARA_REVISION}/${WALK_ARA_FILE}"
  if [ "${which}" = "b" ]; then
    [ -f "${ara_host}" ] || walk_refuse WALK_INPUT_MISSING "${ara_host} (hf download ostris/accuracy_recovery_adapters ${WALK_ARA_FILE} --revision ${WALK_ARA_REVISION})"
  fi
  "${py}" "${WALK_KIT_DIR}/lane3_rung.py" dataset --manifest "${WALK_KIT_DIR}/lane3/rung-dataset.json" --src "${dataset_dir}" >/dev/null \
    || walk_refuse WALK_INPUT_MISSING "the fixture dataset in ${dataset_dir} does not match rung-dataset.json"

  local ts ev walk content
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  ev="${evidence_root}/${ts}-walk-${which}"
  walk="${HOME}/sdlab-gpu-walk"
  content="${walk}/content"
  mkdir -p "${ev}" "${walk}/home"

  # Walk (a) sets the host-RAM threshold to a 1 GiB placeholder: it is the walk that measures the
  # peak the request's real threshold (+20%) comes from. Walk (b) keeps the same placeholder.
  local ram_placeholder_gib="1"
  bash "${WALK_KIT_DIR}/launch_lane3_stub.sh" --emit-remote-script "${ev}/remote_lane3_stub.sh" --train \
    --model "${WALK_MODEL}" --model-revision "${WALK_REVISION}" --host-ram-required-gib "${ram_placeholder_gib}" \
    --download-max-seconds "${wall_s}" > "${ev}/emit.out"
  local kit_sha
  kit_sha="$(sha256sum "${ev}/remote_lane3_stub.sh" | cut -d' ' -f1)"

  if [ "${mode}" = "prepare" ]; then
    rm -rf "${content}" "${walk}/prepared.ok"
  else
    # The GPU run reuses what --prepare installed (venv, CPython, ai-toolkit clone) and the uv cache:
    # it has no network. Only the run's own outputs are cleared.
    if [ "${mode}" != "check" ]; then
      [ -f "${walk}/prepared.ok" ] && [ "$(cat "${walk}/prepared.ok")" = "${kit_sha}" ] \
        || walk_refuse WALK_NOT_PREPARED "run the same walk with --prepare first (network on, no GPU) for this kit"
    fi
    rm -rf "${content}/lane3_out" "${content}/lane3_train" "${content}/lane3_dataset" "${content}/lane3_stub_bundle.tar.gz"
  fi
  mkdir -p "${content}/hf_home" "${content}/.walk_wheelhouse"
  cp "${WALK_KIT_DIR}/locks/lane3.lock" "${WALK_KIT_DIR}/locks/lane3-local-wheels.json" "${WALK_KIT_DIR}/launch_guards.py" \
    "${WALK_KIT_DIR}/classify_install_log.py" "${WALK_KIT_DIR}/lane3_rung.py" "${WALK_KIT_DIR}/lane3/rung-dataset.json" "${content}/"
  cp "${ev}/remote_lane3_stub.sh" "${content}/remote_lane3_stub.sh"
  "${py}" -c 'import json, sys; [print(w["filename"]) for w in json.load(open(sys.argv[1]))["wheels"]]' \
    "${WALK_KIT_DIR}/locks/lane3-local-wheels.json" | while IFS= read -r w; do cp "${wheel_dir}/${w}" "${content}/"; done
  "${py}" -c 'import json, sys; [print(i["image"]) for i in json.load(open(sys.argv[1]))["items"]]' \
    "${WALK_KIT_DIR}/lane3/rung-dataset.json" | while IFS= read -r f; do cp "${dataset_dir}/${f}" "${content}/"; done
  if [ "${which}" = "b" ]; then
    "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" derive-walk-b --rung-yaml "${WALK_KIT_DIR}/lane3/rung-qwen-image.yaml" \
      --ara-path "/content/hf_home/hub/${WALK_ARA_REPO_DIR}/snapshots/${WALK_ARA_REVISION}/${WALK_ARA_FILE}" \
      --out "${content}/rung-qwen-image.yaml"
  else
    cp "${WALK_KIT_DIR}/lane3/rung-qwen-image.yaml" "${content}/rung-qwen-image.yaml"
  fi
  cp "${content}/rung-qwen-image.yaml" "${ev}/rung-job-template.yaml"
  find "${content}" -maxdepth 1 -type f -exec sha256sum {} + > "${ev}/inputs.sha256" 2>/dev/null || true

  # Stand-in for Colab's root pip, as in the CPU walks: a seeded venv of the box's python3 first on
  # PATH, so the script's `pip install` puts uv in a bin directory on PATH.
  if [ ! -x "${walk}/colab-sys/bin/pip" ]; then
    "${HOME}/.sdlab-uv135/bin/uv" venv --seed --python /usr/bin/python3 "${walk}/colab-sys" >/dev/null
  fi
  # Colab's root pip has no uv: take it out of the stand-in each time (binary and metadata), so the
  # script's own hash-checked `pip install uv` is what puts it on PATH.
  "${walk}/colab-sys/bin/pip" uninstall -y -q uv >/dev/null 2>&1 || true
  rm -f "${walk}/colab-sys/bin/uv" "${walk}/colab-sys/bin/uvx"

  local cmd_file="${ev}/walk-command.txt"
  printf '%q ' bash "${WALK_KIT_DIR}/lane3/walk_${which}_$( [ "${which}" = a ] && echo real_load || echo quantised ).sh" \
    --wheel-dir "${wheel_dir}" --hf-home "${hf_home}" --dataset-dir "${dataset_dir}" --evidence-root "${evidence_root}" \
    --wall-s "${wall_s}" > "${cmd_file}"
  echo >> "${cmd_file}"
  echo "WALK_COMMAND $(cat "${cmd_file}")"
  if [ "${mode}" = "check" ]; then
    echo "WALK_CHECK_OK evidence=${ev} (no GPU used; the run itself was not started)"
    return 0
  fi

  local bw=()
  local d
  for d in /usr /etc /opt /var /srv /run /sys /mnt/wsl; do [ -e "$d" ] && bw+=(--ro-bind "$d" "$d"); done
  for d in /bin /lib /lib64 /sbin; do [ -L "$d" ] && bw+=(--symlink "$(readlink "$d")" "$d"); done
  bw+=(--bind "${HOME}" "${HOME}" --ro-bind "${WALK_KIT_DIR}" "${WALK_KIT_DIR}" --bind "${content}" /content)
  bw+=(--dev /dev --proc /proc --tmpfs /tmp --chdir /content --die-with-parent)
  local run_env=()
  local lane3_mode_env=()
  if [ "${mode}" = "prepare" ]; then
    # Network on (PyPI, the CPython download, the ai-toolkit clone); no GPU, no HF cache.
    bw+=(--tmpfs /usr/lib/wsl)
    run_env+=(CUDA_VISIBLE_DEVICES=)
  else
    # No network: the HF cache read-only and the hub offline; uv and pip from the prepared caches.
    bw+=(--unshare-net --ro-bind "${hf_home}" /content/hf_home)
    # Every wheel of the lock (and uv itself) from the wheelhouse --prepare filled, read-only.
    [ -f "${walk}/wheelhouse/${WALK_UV_WHEEL}" ] \
      || walk_refuse WALK_NOT_PREPARED "${walk}/wheelhouse/${WALK_UV_WHEEL} is missing; run --prepare"
    [ -f "${walk}/simple/torch/index.html" ] || walk_refuse WALK_NOT_PREPARED "${walk}/simple is missing; run --prepare"
    bw+=(--ro-bind "${walk}/wheelhouse" /content/.walk_wheelhouse --ro-bind "${walk}/simple" /content/.walk_simple)
    # uv takes the lock from a file:// simple index of the wheelhouse (both the default index and, in
    # place of download.pytorch.org, the kit's PINNED_PYTORCH_INDEX_URL); the lock's hashes still bind.
    run_env+=(HF_HUB_OFFLINE=1 UV_OFFLINE=1 UV_DEFAULT_INDEX=file:///content/.walk_simple UV_VENV_CLEAR=1
      PIP_NO_INDEX=1 PIP_FIND_LINKS=/content/.walk_wheelhouse)
    if [ "${mode}" = "offline-install" ]; then
      bw+=(--tmpfs /usr/lib/wsl)
      run_env+=(CUDA_VISIBLE_DEVICES=)
    else
      [ -e /dev/dxg ] && bw+=(--dev-bind /dev/dxg /dev/dxg)
      while IFS= read -r kv; do lane3_mode_env+=("$kv"); done < <(grep '^LANE3_' "${ev}/remote_lane3_stub.sh.env")
    fi
  fi
  local base_env=()
  while IFS= read -r kv; do
    if [ "${mode}" != "prepare" ] && [[ "${kv}" == PINNED_PYTORCH_INDEX_URL=* ]]; then
      kv="PINNED_PYTORCH_INDEX_URL=file:///content/.walk_simple"
    fi
    base_env+=("$kv")
  done < <(grep -v '^LANE3_' "${ev}/remote_lane3_stub.sh.env")

  if [ "${mode}" = "gpu" ]; then
    "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" gpu-busy --nvidia-smi "${WALK_NVIDIA_SMI}" \
      --windows-smi "${WALK_WINDOWS_SMI}" --max-mib "${WALK_GPU_BUSY_MAX_MIB}" | tee "${ev}/gpu-busy.txt" || exit 3
    "${WALK_NVIDIA_SMI}" --query-gpu=memory.used --format=csv,noheader,nounits | head -n 1 | tr -d ' ' > "${ev}/gpu-baseline-mib.txt"
    echo "GPU_BASELINE_MIB $(cat "${ev}/gpu-baseline-mib.txt") (walk's own use bounded at ${WALK_VRAM_CEILING_MIB} MiB above it)"
  fi

  date -u +%Y-%m-%dT%H:%M:%SZ > "${ev}/started_at.txt"
  local start_s
  start_s="$(date +%s)"
  # The wall binds independently of the sampler: `timeout` kills the whole sandbox at --wall-s
  # (SIGKILL 30 s later if it has not gone), and --die-with-parent takes the sandbox down with it.
  timeout --kill-after=30 "${wall_s}" bwrap "${bw[@]}" -- taskset -c 0-7 env -i \
    HOME="${walk}/home" \
    PATH="${walk}/colab-sys/bin:/usr/lib/wsl/lib:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    LD_LIBRARY_PATH=/usr/lib/wsl/lib LANG=C.UTF-8 UV_SYSTEM_PYTHON=1 \
    OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 \
    SDLAB_REMOTE_SCRIPT=/content/remote_lane3_stub.sh "${run_env[@]}" \
    "${base_env[@]}" "${lane3_mode_env[@]}" \
    /usr/bin/python3 -u "${WALK_KIT_DIR}/remote_runner.py" > "${ev}/runner.log" 2>&1 &
  local run_pid=$!
  local smi_args=()
  [ "${mode}" = "gpu" ] && smi_args=(--nvidia-smi "${WALK_NVIDIA_SMI}" --vram-csv "${ev}/vram.csv" \
    --vram-ceiling-mib "${WALK_VRAM_CEILING_MIB}" --vram-baseline-mib "$(cat "${ev}/gpu-baseline-mib.txt")")
  [ "${mode}" = "gpu" ] || : > "${ev}/vram.csv"
  "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" sample --root-pid "${run_pid}" \
    --train-log "${content}/lane3_out/train.log" --out "${ev}/host_rss.csv" \
    --oom-grace-s 60 --mem-floor-gib "${WALK_MEM_FLOOR_GIB}" --wall-s "${wall_s}" "${smi_args[@]}" > "${ev}/sampler.log" 2>&1 &
  local sampler_pid=$!
  local rc=0
  wait "${run_pid}" || rc=$?
  wait "${sampler_pid}" || true
  # remote_runner.py exits 0 whatever the script did; the script's own rc is its SDLAB_REMOTE_RC line.
  local remote_rc
  remote_rc="$(grep -E '^SDLAB_REMOTE_RC=-?[0-9]+$' "${ev}/runner.log" | tail -n 1 | cut -d= -f2)"
  if [ "${rc}" -eq 0 ]; then
    rc="${remote_rc:-99}"
  fi
  echo "rc=${rc} wall_s=$(( $(date +%s) - start_s ))" | tee "${ev}/result.txt"
  date -u +%Y-%m-%dT%H:%M:%SZ > "${ev}/ended_at.txt"

  mkdir -p "${ev}/lane3_out"
  cp -r "${content}/lane3_out/." "${ev}/lane3_out/" 2>/dev/null || true
  [ -f "${content}/lane3_stub_bundle.tar.gz" ] && cp "${content}/lane3_stub_bundle.tar.gz" "${ev}/" || true
  touch "${ev}/lane3_out/train.log"
  "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" summarize --host-csv "${ev}/host_rss.csv" --vram-csv "${ev}/vram.csv" \
    --train-log "${ev}/lane3_out/train.log" --stop-file "${ev}/host_rss.stop.txt" --out "${ev}/summary.json"
  tail -n 25 "${ev}/runner.log"
  if [ "${mode}" = "prepare" ] && [ "${rc}" -eq 0 ]; then
    # A wheelhouse of every wheel in the hash-locked lock (and the pinned uv wheel), for the GPU
    # run's offline install: uv's cache alone cannot resolve offline (cuda-toolkit, 2026-11-06).
    mkdir -p "${walk}/wheelhouse"
    local plats=()
    local v
    for v in $(seq 17 39); do plats+=(--platform "manylinux_2_${v}_x86_64"); done
    "${walk}/colab-sys/bin/pip" download --quiet --require-hashes --only-binary :all: --no-deps "${plats[@]}" \
      --platform manylinux2014_x86_64 --platform linux_x86_64 --platform any --python-version 3.12 \
      --implementation cp --abi cp312 --abi abi3 --abi none --extra-index-url "$(grep '^PINNED_PYTORCH_INDEX_URL=' "${ev}/remote_lane3_stub.sh.env" | cut -d= -f2-)" \
      -r "${WALK_KIT_DIR}/locks/lane3.lock" -d "${walk}/wheelhouse" \
      || walk_refuse WALK_INPUT_MISSING "pip could not fill the wheelhouse from lane3.lock"
    "${walk}/colab-sys/bin/pip" download --quiet --only-binary :all: --no-deps --platform manylinux2014_x86_64 \
      --python-version 3.12 -d "${walk}/wheelhouse" "uv==0.13.5"
    [ -f "${walk}/wheelhouse/${WALK_UV_WHEEL}" ] || walk_refuse WALK_INPUT_MISSING "pip did not fetch ${WALK_UV_WHEEL}"
    rm -rf "${walk}/simple"
    "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" simple-index --wheelhouse "${walk}/wheelhouse" \
      --link-root /content/.walk_wheelhouse --out "${walk}/simple"
    printf '%s' "${kit_sha}" > "${walk}/prepared.ok"
    echo "WALK_PREPARED ${walk} for kit ${kit_sha}"
  fi
  echo "WALK_EVIDENCE ${ev}"
  return "${rc}"
}
