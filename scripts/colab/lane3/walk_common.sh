#!/usr/bin/env bash
# Shared body of the lane 3 GPU-rung local walks (walk_a_real_load.sh, walk_b_quantised.sh): run the
# kit's own train-mode remote script on the rig's GPU, in WSL, in a bwrap-bound /content, with the
# kit's own uploads staged flat as a window leaves them, and instruments around it. Sourced, not run.
#
# Required arguments (no defaults; each missing one is WALK_ARG_MISSING):
#   --wheel-dir <dir>      the two pre-built local wheels lane3-local-wheels.json lists
#   --hf-home <dir>        an HF home whose hub/ holds Qwen/Qwen-Image at the pinned revision; it is
#                          bound to /content/hf_home, so the kit's download step finds it cached
#   --dataset-dir <dir>    the images scripts/colab/lane3/rung-dataset.json lists (sha256-checked)
#   --evidence-root <dir>  where <UTC timestamp>-walk-a|b/ is written (a persistent disk)
#   --wall-s <seconds>     the walk's wall-clock cap (the sampler kills the run at it)
# Modes:
#   --check                every step that needs no GPU (arguments, inputs, emit, staging), then
#                          print the exact command and stop
#   --install-only         run the remote script in install mode (no GPU, CUDA hidden): proves the
#                          staging and warms the uv cache under ${HOME}/sdlab-gpu-walk/home
# Refusals: WALK_ARG_MISSING, WALK_ARG_INVALID, WALK_INPUT_MISSING, GPU_BUSY (another process holds
# more than 2 GiB on the GPU, named), each one `REFUSED: <CODE>: <detail>` line.
set -euo pipefail

WALK_KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WALK_REVISION="75e0b4be04f60ec59a75f475837eced720f823b6"
WALK_MODEL="Qwen/Qwen-Image"
WALK_ARA_REPO_DIR="models--ostris--accuracy_recovery_adapters"
WALK_ARA_REVISION="daf7bdfa5878178b1bde518336ad672dd914bdae"
WALK_ARA_FILE="qwen_image_torchao_uint3.safetensors"
WALK_GPU_BUSY_MAX_MIB="2048"
WALK_NVIDIA_SMI="/usr/lib/wsl/lib/nvidia-smi"
WALK_WINDOWS_SMI="/mnt/c/Windows/System32/nvidia-smi.exe"

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
      --install-only) mode="install"; shift ;;
      *) walk_refuse WALK_ARG_INVALID "unknown argument $1" ;;
    esac
  done
  local a
  for a in wheel_dir hf_home dataset_dir evidence_root wall_s; do
    [ -n "${!a}" ] || walk_refuse WALK_ARG_MISSING "--${a//_/-} is required (there is no default)"
  done
  [[ "${wall_s}" =~ ^[1-9][0-9]*$ ]] || walk_refuse WALK_ARG_INVALID "--wall-s ${wall_s} is not a whole number of seconds"
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

  rm -rf "${content}"
  mkdir -p "${content}/hf_home"
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
  sha256sum "${content}"/* 2>/dev/null > "${ev}/inputs.sha256" || true

  # Stand-in for Colab's root pip, as in the CPU walks: a seeded venv of the box's python3 first on
  # PATH, so the script's `pip install` puts uv in a bin directory on PATH.
  if [ ! -x "${walk}/colab-sys/bin/pip" ]; then
    "${HOME}/.sdlab-uv135/bin/uv" venv --seed --python /usr/bin/python3 "${walk}/colab-sys" >/dev/null
  fi
  rm -f "${walk}/colab-sys/bin/uv" "${walk}/colab-sys/bin/uvx"

  local bw=()
  local d
  for d in /usr /etc /opt /var /srv /run /sys /mnt/wsl; do [ -e "$d" ] && bw+=(--ro-bind "$d" "$d"); done
  # The kit itself (remote_runner.py runs from it), read-only, wherever the clone lives.
  bw+=(--ro-bind "${WALK_KIT_DIR}" "${WALK_KIT_DIR}")
  for d in /bin /lib /lib64 /sbin; do [ -L "$d" ] && bw+=(--symlink "$(readlink "$d")" "$d"); done
  bw+=(--bind "${HOME}" "${HOME}" --bind "${content}" /content --bind "${hf_home}" /content/hf_home)
  bw+=(--dev /dev --proc /proc --tmpfs /tmp --chdir /content)
  local lane3_mode_env=()
  if [ "${mode}" = "install" ]; then
    # Install mode: no GPU device, the WSL driver libraries hidden, and no train variables.
    bw+=(--tmpfs /usr/lib/wsl)
  else
    [ -e /dev/dxg ] && bw+=(--dev-bind /dev/dxg /dev/dxg)
    while IFS= read -r kv; do lane3_mode_env+=("$kv"); done < <(grep '^LANE3_' "${ev}/remote_lane3_stub.sh.env")
  fi
  local base_env=()
  while IFS= read -r kv; do base_env+=("$kv"); done < <(grep -v '^LANE3_' "${ev}/remote_lane3_stub.sh.env")

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

  if [ "${mode}" = "gpu" ]; then
    "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" gpu-busy --nvidia-smi "${WALK_NVIDIA_SMI}" \
      --windows-smi "${WALK_WINDOWS_SMI}" --max-mib "${WALK_GPU_BUSY_MAX_MIB}" | tee "${ev}/gpu-busy.txt" || exit 3
  fi

  date -u +%Y-%m-%dT%H:%M:%SZ > "${ev}/started_at.txt"
  local start_s
  start_s="$(date +%s)"
  local cvd=()
  [ "${mode}" = "install" ] && cvd=(CUDA_VISIBLE_DEVICES=)
  bwrap "${bw[@]}" -- taskset -c 0-7 env -i \
    HOME="${walk}/home" \
    PATH="${walk}/colab-sys/bin:/usr/lib/wsl/lib:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    LD_LIBRARY_PATH=/usr/lib/wsl/lib LANG=C.UTF-8 UV_SYSTEM_PYTHON=1 \
    OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 \
    SDLAB_REMOTE_SCRIPT=/content/remote_lane3_stub.sh "${cvd[@]}" \
    "${base_env[@]}" "${lane3_mode_env[@]}" \
    /usr/bin/python3 -u "${WALK_KIT_DIR}/remote_runner.py" > "${ev}/runner.log" 2>&1 &
  local run_pid=$!
  local smi_pid=""
  if [ "${mode}" = "gpu" ]; then
    "${WALK_NVIDIA_SMI}" --query-gpu=timestamp,memory.used --format=csv,noheader,nounits -lms 1000 > "${ev}/vram.csv" 2>&1 &
    smi_pid=$!
  else
    : > "${ev}/vram.csv"
  fi
  "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" sample --root-pid "${run_pid}" \
    --train-log "${content}/lane3_out/train.log" --out "${ev}/host_rss.csv" \
    --oom-grace-s 60 --mem-floor-gib 2 --wall-s "${wall_s}" > "${ev}/sampler.log" 2>&1 &
  local sampler_pid=$!
  local rc=0
  wait "${run_pid}" || rc=$?
  wait "${sampler_pid}" || true
  [ -n "${smi_pid}" ] && { kill "${smi_pid}" 2>/dev/null || true; wait "${smi_pid}" 2>/dev/null || true; }
  echo "rc=${rc} wall_s=$(( $(date +%s) - start_s ))" | tee "${ev}/result.txt"
  date -u +%Y-%m-%dT%H:%M:%SZ > "${ev}/ended_at.txt"

  mkdir -p "${ev}/lane3_out"
  cp -r "${content}/lane3_out/." "${ev}/lane3_out/" 2>/dev/null || true
  [ -f "${content}/lane3_stub_bundle.tar.gz" ] && cp "${content}/lane3_stub_bundle.tar.gz" "${ev}/" || true
  touch "${ev}/lane3_out/train.log"
  "${py}" "${WALK_KIT_DIR}/lane3/walk_probe.py" summarize --host-csv "${ev}/host_rss.csv" --vram-csv "${ev}/vram.csv" \
    --train-log "${ev}/lane3_out/train.log" --stop-file "${ev}/host_rss.stop.txt" --out "${ev}/summary.json"
  tail -n 25 "${ev}/runner.log"
  echo "WALK_EVIDENCE ${ev}"
}
