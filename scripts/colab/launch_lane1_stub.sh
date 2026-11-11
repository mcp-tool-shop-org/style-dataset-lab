#!/usr/bin/env bash
# Launch kit for Lane 1 (render) Colab windows: CPU high-mem stub (Part C, PR #45), CPU stub of
# --render (install + weights download + sha256/unpack check on CPU), and --render on a Colab GPU.
# Checks pinned input sha256s (including itself) and runs preflight_resolve.sh before opening,
# holds /tmp/colab-window-open.lock, opens CPU --high-mem (a GPU card needs --shape), runs CPython 3.14.9 uv venv + wheel-only
# install from hash-locked lane1.lock + pinned ComfyUI + comfy-headless + queue render +
# stamp read-back + kill + resume, enforces live launch_guards.py (wall, cap, vitals/DEAD HARNESS,
# host-RAM), scrubs VM-side logs before tarring, downloads result tar, merges VM facts/balances/rate/
# downloaded shas into window.json, and stops its own session in an EXIT trap.
# Bounded setup, download, and stop contract (colab_window.sh):
#   open-lock wait: timeout -k 10 180 (190 s)
#   colab new: timeout -k 10 180 (190 s)
#   colab upload: timeout -k 10 120 (130 s)
#   colab download: timeout -k 10 300 (310 s)
#   colab stop: timeout -k 10 60 with 1 retry (2 * 70 = 140 s)
#   wall watcher escalation: 30 s after TERM -> watcher runs `colab stop` itself (stop_path: trap | watcher)
#   measured from trip: cleanup_stop_attempted_by_s = 310 s, cleanup_bound_s = 310 + 140 = 450 s
#   effective_trip = cap - margin - cleanup_reserve; cleanup_reserve = (cleanup_bound_s / 3600) * priced_rate
#   (CAP_TOO_SMALL_FOR_CLEANUP up front; --min-runtime-s; --dry)
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
PINNED_LANE3_RUNG_SHA="47462c632c86dff2979d479503f9651bf37d4560713136ebc0c8c91b51e4275b"
PINNED_INSTALL_CLASSIFIER_SHA="ccccf077795148c14a7aa430e3575db45f097549a8b6a43aa149d78238513fd1"
PINNED_LAUNCH_GUARDS_SHA="4c0c0ab6410eaa511a808d00f09a09d42d5d5b7d0504d85d58cfe3c65baeb085"
PINNED_REMOTE_RUNNER_SHA="393929ed704ccbacaee2b590010e348a5d635cbdd70361209d3e0103d1fba6eb"
PINNED_COLAB_WINDOW_SHA="db761fb414da915c8835bad8ef1544992e39aa5b3d636a1d81d17d231f26e974"
PINNED_SELF_SHA="2138d73dc803e5ad463fbec5189bbb477c3a96bde23384c4f9eef97bee7454c5"

LANE1_DISK_REQUIRED_GIB="50"
LANE1_CPU_STUB_DISK_REQUIRED_GIB="5"
LANE1_GPU_SMOKE_SECONDS="5"
LANE1_DOWNLOAD_PROBE_SECONDS="60"
LANE1_DOWNLOAD_PROBE_BYTES="2147483648"
LANE1_COMFY_PORT="8188"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_SH="${SCRIPT_DIR}/launch_lane1_stub.sh"
# shellcheck source=scripts/colab/colab_window.sh
source "${SCRIPT_DIR}/colab_window.sh"

CARD="${CARD:-CPU-high-mem}"
SESSION="sdlab-lane1-stub-$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR=""
CAP="${CAP:-0.10}"
WALL_S="${WALL_S:-900}"
GRACE_S="${GRACE_S:-60}"
MARGIN="${MARGIN:-0.01}"
MAX_RATE=""
SHAPE=""
MIN_RUNTIME_S=""
DOWNLOAD_TIMEOUT_S_ARG=""
UPLOAD_TIMEOUT_S_ARG=""
UPLOAD_CHUNK_BYTES_ARG=""
DOWNLOAD_CHUNK_BYTES_ARG=""
DRY_RUN=0
RENDER_REQUESTED=0
RENDER_CPU_STUB=0
CAP_SET=0
WEIGHTS_MANIFEST=""
WEIGHTS_MANIFEST_SET=0
JOBS_FILE=""
JOBS_SET=0
JOBS_SHA256=""
JOBS_SHA_SET=0
COPY_BACK_EVERY=""
COPY_BACK_SET=0
RENDER_HOST_RAM_REQUIRED_GIB=""
HOST_RAM_SET=0
RENDER_DOWNLOAD_MAX_SECONDS=""
DOWNLOAD_MAX_SET=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --card) CARD="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --session) SESSION="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --out-dir) OUT_DIR="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --cap) CAP="${2:-}"; CAP_SET=1; shift; [ "$#" -gt 0 ] && shift ;;
    --wall-s) WALL_S="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --grace-s) GRACE_S="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --margin) MARGIN="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --max-rate) MAX_RATE="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --shape) SHAPE="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --min-runtime-s) MIN_RUNTIME_S="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-timeout-s) DOWNLOAD_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-timeout-s) UPLOAD_TIMEOUT_S_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --upload-chunk-bytes) UPLOAD_CHUNK_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --download-chunk-bytes) DOWNLOAD_CHUNK_BYTES_ARG="${2:-}"; shift; [ "$#" -gt 0 ] && shift ;;
    --dry) DRY_RUN=1; shift ;;
    --render) RENDER_REQUESTED=1; shift ;;
    --render-cpu-stub) RENDER_CPU_STUB=1; shift ;;
    --weights-manifest) WEIGHTS_MANIFEST="${2:-}"; WEIGHTS_MANIFEST_SET=1; shift; [ "$#" -gt 0 ] && shift ;;
    --jobs) JOBS_FILE="${2:-}"; JOBS_SET=1; shift; [ "$#" -gt 0 ] && shift ;;
    --jobs-sha256) JOBS_SHA256="${2:-}"; JOBS_SHA_SET=1; shift; [ "$#" -gt 0 ] && shift ;;
    --copy-back-every) COPY_BACK_EVERY="${2:-}"; COPY_BACK_SET=1; shift; [ "$#" -gt 0 ] && shift ;;
    --host-ram-required-gib) RENDER_HOST_RAM_REQUIRED_GIB="${2:-}"; HOST_RAM_SET=1; shift; [ "$#" -gt 0 ] && shift ;;
    --download-max-seconds) RENDER_DOWNLOAD_MAX_SECONDS="${2:-}"; DOWNLOAD_MAX_SET=1; shift; [ "$#" -gt 0 ] && shift ;;
    *)
      echo "REFUSED: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

colab_configure_download_timeout "${DOWNLOAD_TIMEOUT_S_ARG}" || exit 2
colab_configure_upload_timeout "${UPLOAD_TIMEOUT_S_ARG}" || exit 2
colab_configure_upload_chunk_bytes "${UPLOAD_CHUNK_BYTES_ARG}" || exit 2
colab_configure_download_chunk_bytes "${DOWNLOAD_CHUNK_BYTES_ARG}" || exit 2

if [ "${RENDER_REQUESTED}" != "1" ] && [ "${RENDER_CPU_STUB}" != "1" ] \
  && [ "${WEIGHTS_MANIFEST_SET}${JOBS_SET}${JOBS_SHA_SET}${COPY_BACK_SET}${HOST_RAM_SET}${DOWNLOAD_MAX_SET}" != "000000" ]; then
  echo "REFUSED: RENDER_OPTION_WITHOUT_RENDER: --weights-manifest, --jobs, --jobs-sha256, --copy-back-every, --host-ram-required-gib and --download-max-seconds need --render" >&2
  exit 2
fi

if [ "${RENDER_CPU_STUB}" = "1" ] && [ "${JOBS_SET}${JOBS_SHA_SET}${COPY_BACK_SET}" != "000" ]; then
  echo "REFUSED: RENDER_OPTION_WITHOUT_RENDER: --jobs, --jobs-sha256 and --copy-back-every belong to GPU --render, not --render-cpu-stub" >&2
  exit 2
fi

if [ "${DRY_RUN}" = "1" ]; then
  if [ "${RENDER_REQUESTED}" = "1" ] && [ "${RENDER_CPU_STUB}" != "1" ]; then
    if colab_card_is_cpu "${CARD}"; then
      echo "REFUSED: RENDER_REQUIRES_GPU: --render --dry on card ${CARD}; real-model rendering needs a GPU card" >&2
      exit 2
    fi
    if [ "${CAP_SET}" != "1" ] || ! [[ "${CAP}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${CAP}" =~ ^0+(\.0+)?$ ]]; then
      echo "REFUSED: RENDER_CAP_REQUIRED: --render needs an explicit positive --cap (the CPU stub default does not apply)" >&2
      exit 2
    fi
    if ! [[ "${MAX_RATE}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${MAX_RATE}" =~ ^0+(\.0+)?$ ]]; then
      echo "REFUSED: RENDER_MAX_RATE_REQUIRED: --render needs --max-rate <units/h>, the highest live rate the window may run at" >&2
      exit 2
    fi
  fi
  DRY_TEST_MODE=0
  if colab_fake_test_mode_active; then
    DRY_TEST_MODE=1
  fi
  colab_apply_test_cleanup_overrides "${DRY_TEST_MODE}"
  PY_BIN="$(colab_resolve_python)"
  GUARDS_PY="${SCRIPT_DIR}/launch_guards.py"
  colab_dry_cap_budget "${PY_BIN}" "${GUARDS_PY}" "render" "${CARD}" "${CAP}" "${MARGIN}" "${MAX_RATE}" "${RATE_CCU_PER_HOUR:-0.26}" "${MIN_RUNTIME_S}"
  exit $?
fi

LANE1_MODE="stub"
BUNDLE_NAME="lane1_stub_bundle.tar.gz"
JOBS_SHA256_CLEAN=""

if [ "${RENDER_CPU_STUB}" = "1" ]; then
  if ! colab_card_is_cpu "${CARD}"; then
    echo "REFUSED: RENDER_CPU_STUB_REQUIRES_CPU: --render-cpu-stub runs on a CPU card; got ${CARD}" >&2
    exit 2
  fi
  WEIGHTS_MANIFEST="${WEIGHTS_MANIFEST:-${SCRIPT_DIR}/lane1/render-cpu-stub-manifest.json}"
  RENDER_HOST_RAM_REQUIRED_GIB="${RENDER_HOST_RAM_REQUIRED_GIB:-4}"
  RENDER_DOWNLOAD_MAX_SECONDS="${RENDER_DOWNLOAD_MAX_SECONDS:-300}"
  if ! [[ "${RENDER_HOST_RAM_REQUIRED_GIB}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${RENDER_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: --host-ram-required-gib must be a positive number of GiB" >&2
    exit 2
  fi
  if ! [[ "${RENDER_DOWNLOAD_MAX_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: DOWNLOAD_LIMIT_MISSING: --download-max-seconds must be a positive integer number of seconds" >&2
    exit 2
  fi
  LANE1_DISK_REQUIRED_GIB="${LANE1_CPU_STUB_DISK_REQUIRED_GIB}"
  LANE1_MODE="render_cpu_stub"
  BUNDLE_NAME="lane1_render_bundle.tar.gz"
elif [ "${RENDER_REQUESTED}" = "1" ]; then
  if colab_card_is_cpu "${CARD}"; then
    echo "REFUSED: RENDER_REQUIRES_GPU: --render on card ${CARD}; real-model rendering needs a GPU card" >&2
    exit 2
  fi
  case "${SHAPE}" in
    standard | high-mem) ;;
    "")
      echo "REFUSED: SHAPE_REQUIRED: a GPU card (${CARD}) needs --shape standard|high-mem; there is no default" >&2
      exit 2
      ;;
    *)
      echo "REFUSED: SHAPE_INVALID: --shape ${SHAPE}: use standard or high-mem" >&2
      exit 2
      ;;
  esac
  if [ "${SHAPE}" = "standard" ] && colab_card_is_single_shape "${CARD}"; then
    echo "REFUSED: SHAPE_STANDARD_UNAVAILABLE: ${CARD} has a single high-memory shape; pass --shape high-mem" >&2
    exit 2
  fi
  if [ -z "${WEIGHTS_MANIFEST}" ]; then
    echo "REFUSED: RENDER_MANIFEST_REQUIRED: --render needs --weights-manifest <json>" >&2
    exit 2
  fi
  if [ -z "${JOBS_FILE}" ]; then
    echo "REFUSED: RENDER_JOBS_REQUIRED: --render needs --jobs <jobs.jsonl>" >&2
    exit 2
  fi
  JOBS_SHA256_CLEAN="${JOBS_SHA256#sha256:}"
  JOBS_SHA256_CLEAN="${JOBS_SHA256_CLEAN,,}"
  if ! [[ "${JOBS_SHA256_CLEAN}" =~ ^[0-9a-f]{64}$ ]]; then
    echo "REFUSED: RENDER_JOBS_SHA_REQUIRED: --render needs --jobs-sha256 <64-hex>" >&2
    exit 2
  fi
  if ! [[ "${COPY_BACK_EVERY}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: RENDER_COPY_BACK_REQUIRED: --render needs --copy-back-every <positive int>" >&2
    exit 2
  fi
  if ! [[ "${RENDER_HOST_RAM_REQUIRED_GIB}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${RENDER_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: --render needs --host-ram-required-gib <GiB>" >&2
    exit 2
  fi
  if ! [[ "${RENDER_DOWNLOAD_MAX_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REFUSED: DOWNLOAD_LIMIT_MISSING: --render needs --download-max-seconds <s>" >&2
    exit 2
  fi
  if [ "${CAP_SET}" != "1" ] || ! [[ "${CAP}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${CAP}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: RENDER_CAP_REQUIRED: --render needs an explicit positive --cap (the CPU stub default does not apply)" >&2
    exit 2
  fi
  if ! [[ "${MAX_RATE}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "${MAX_RATE}" =~ ^0+(\.0+)?$ ]]; then
    echo "REFUSED: RENDER_MAX_RATE_REQUIRED: --render needs --max-rate <units/h>, the highest live rate the window may run at" >&2
    exit 2
  fi
  LANE1_MODE="render"
  BUNDLE_NAME="lane1_render_bundle.tar.gz"
fi

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
RUNG_PY="${SCRIPT_DIR}/lane3_rung.py"
RUNNER_PY="${SCRIPT_DIR}/remote_runner.py"
CLASSIFIER_PY="${SCRIPT_DIR}/classify_install_log.py"
WINDOW_SH="${SCRIPT_DIR}/colab_window.sh"
LOCK_FILE="${SCRIPT_DIR}/locks/lane1.lock"

PIN_OVERRIDE_VARS=(
  EXPECTED_LANE1_LOCK_SHA
  EXPECTED_LANE1_RENDER_SHA
  EXPECTED_LANE3_RUNG_SHA
  EXPECTED_INSTALL_CLASSIFIER_SHA
  EXPECTED_LAUNCH_GUARDS_SHA
  EXPECTED_REMOTE_RUNNER_SHA
  EXPECTED_COLAB_WINDOW_SHA
  EXPECTED_LAUNCH_LANE1_STUB_SHA
  SDLAB_TEST_RATE_READ_INTERVAL_S
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
  SDLAB_TEST_UPLOAD_CHUNK_BYTES
  SDLAB_TEST_DOWNLOAD_CHUNK_BYTES
  SDLAB_TEST_WALL_ESCALATE_S
  SDLAB_TEST_DISK_REQUIRED_GIB
  SDLAB_TEST_SMOKE_SECONDS
  SDLAB_TEST_PROBE_SECONDS
  SDLAB_TEST_PROBE_BYTES
  SDLAB_TEST_COMFY_PORT
)
colab_refuse_live_pin_overrides "${OUT_DIR}" "${TEST_MODE}" "${PIN_OVERRIDE_VARS[@]}"
colab_apply_test_cleanup_overrides "${TEST_MODE}"
if [ "${TEST_MODE}" = "1" ]; then
  LANE1_DISK_REQUIRED_GIB="${SDLAB_TEST_DISK_REQUIRED_GIB:-${LANE1_DISK_REQUIRED_GIB}}"
  LANE1_GPU_SMOKE_SECONDS="${SDLAB_TEST_SMOKE_SECONDS:-${LANE1_GPU_SMOKE_SECONDS}}"
  LANE1_DOWNLOAD_PROBE_SECONDS="${SDLAB_TEST_PROBE_SECONDS:-${LANE1_DOWNLOAD_PROBE_SECONDS}}"
  LANE1_DOWNLOAD_PROBE_BYTES="${SDLAB_TEST_PROBE_BYTES:-${LANE1_DOWNLOAD_PROBE_BYTES}}"
  LANE1_COMFY_PORT="${SDLAB_TEST_COMFY_PORT:-${LANE1_COMFY_PORT}}"
fi

EXP_LOCK_SHA="${PINNED_LOCK_SHA}"
EXP_LANE1_SHA="${PINNED_LANE1_RENDER_SHA}"
EXP_RUNG_SHA="${PINNED_LANE3_RUNG_SHA}"
EXP_CLASSIFIER_SHA="${PINNED_INSTALL_CLASSIFIER_SHA}"
EXP_GUARDS_SHA="${PINNED_LAUNCH_GUARDS_SHA}"
EXP_RUNNER_SHA="${PINNED_REMOTE_RUNNER_SHA}"
EXP_WINDOW_SHA="${PINNED_COLAB_WINDOW_SHA}"
EXP_SELF_SHA="${PINNED_SELF_SHA}"
if [ "${TEST_MODE}" = "1" ]; then
  EXP_LOCK_SHA="${EXPECTED_LANE1_LOCK_SHA:-${EXP_LOCK_SHA}}"
  EXP_LANE1_SHA="${EXPECTED_LANE1_RENDER_SHA:-${EXP_LANE1_SHA}}"
  EXP_RUNG_SHA="${EXPECTED_LANE3_RUNG_SHA:-${EXP_RUNG_SHA}}"
  EXP_CLASSIFIER_SHA="${EXPECTED_INSTALL_CLASSIFIER_SHA:-${EXP_CLASSIFIER_SHA}}"
  EXP_GUARDS_SHA="${EXPECTED_LAUNCH_GUARDS_SHA:-${EXP_GUARDS_SHA}}"
  EXP_RUNNER_SHA="${EXPECTED_REMOTE_RUNNER_SHA:-${EXP_RUNNER_SHA}}"
  EXP_WINDOW_SHA="${EXPECTED_COLAB_WINDOW_SHA:-${EXP_WINDOW_SHA}}"
  EXP_SELF_SHA="${EXPECTED_LAUNCH_LANE1_STUB_SHA:-${EXP_SELF_SHA}}"
fi

SHAS_JSON="$(colab_verify_input_shas "${PY_BIN}" "${GUARDS_PY}" \
  "${LOCK_FILE}=${EXP_LOCK_SHA}" \
  "${LANE1_PY}=${EXP_LANE1_SHA}" \
  "${RUNG_PY}=${EXP_RUNG_SHA}" \
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
EXEC_IN_FLIGHT=0
TOKEN_DIR=""

lane1_download_partial_bundle_on_failure() {
  local failed_rc="$1"
  local dl_t="${COLAB_DOWNLOAD_TIMEOUT_S:-300}"
  local kill_grace="${COLAB_KILL_GRACE_S:-10}"
  local dl_rc=0
  local dl_out=""
  colab_run_bounded_salvage_step "${dl_t}" "${kill_grace}" \
    colab download -s "${SESSION}" "/content/${BUNDLE_NAME}" "${OUT_DIR}/${BUNDLE_NAME}" \
    > "${OUT_DIR}/.partial_dl.out" 2>&1 || dl_rc=$?
  dl_out="$(cat "${OUT_DIR}/.partial_dl.out" 2>/dev/null || true)"
  rm -f "${OUT_DIR}/.partial_dl.out"
  [ -n "${dl_out}" ] && printf '%s\n' "${dl_out}" >> "${OUT_DIR}/colab.log"
  if colab_rc_is_timeout "${dl_rc}"; then
    echo "SALVAGE_STEP_TIMEOUT download timeout_s=${dl_t} kill_grace_s=${kill_grace} rc=${dl_rc}" >> "${OUT_DIR}/guards.log"
  fi
  if [ "${dl_rc}" -eq 0 ] && [ -s "${OUT_DIR}/${BUNDLE_NAME}" ]; then
    echo "BUNDLE_AFTER_FAILURE: downloaded ${BUNDLE_NAME} (rc=${failed_rc})" >> "${OUT_DIR}/guards.log"
  else
    rm -f "${OUT_DIR}/${BUNDLE_NAME}"
    echo "BUNDLE_AFTER_FAILURE: none on the VM (rc=${failed_rc}, download rc=${dl_rc})" >> "${OUT_DIR}/guards.log"
  fi
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
  if [ "${rc}" -ne 0 ] && [ "${LANE1_MODE}" != "stub" ] && [ "${EXEC_IN_FLIGHT}" = "1" ] \
    && [ ! -s "${OUT_DIR}/${BUNDLE_NAME}" ] && [ ! -f "${OUT_DIR}/wall_trip_epoch.txt" ] \
    && [ "${COLAB_CLEANUP_SKIP_SALVAGE:-0}" != "1" ]; then
    lane1_download_partial_bundle_on_failure "${rc}" || true
  fi
  if [ -f "${OUT_DIR}/watcher_escalated.txt" ]; then
    sleep 3600
    exit 137
  fi
  printf 'trap\n' > "${OUT_DIR}/stop_path.txt"
  printf '1\n' > "${OUT_DIR}/stop_reached.txt"
  if [ "${SESSION_OPENED}" -eq 1 ] && { [ -f "${OUT_DIR}/session_open_started.txt" ] || [ -f "${OUT_DIR}/session_opened.txt" ]; }; then
    colab_stop_and_log_closing "${PY_BIN}" "${SESSION}" "${OUT_DIR}"
  fi
  if [ -f "${OUT_DIR}/watcher_escalated.txt" ]; then
    sleep 3600
    exit 137
  fi
  if [ -f "${OUT_DIR}/wall_trip_epoch.txt" ] && [ ! -f "${OUT_DIR}/watcher_escalated.txt" ] && [ ! -f "${OUT_DIR}/watcher_wait.txt" ]; then
    printf 'cleanup_seen\n' > "${OUT_DIR}/watcher_wait.txt"
  fi
  if [ -n "${WALL_WATCHER_PID}" ]; then
    pkill -P "${WALL_WATCHER_PID}" 2>/dev/null || true
    kill -9 "${WALL_WATCHER_PID}" 2>/dev/null || true
  fi
  rm -f "${OUT_DIR}/.watcher_tracked_pids.txt"
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

# The card class sets the rate policy: a CPU stub keeps the labelled configured rate; a GPU card
# goes through the shared GPU rate gate (colab_window.sh: required --max-rate, a stable window rate
# at or above the floor, max pricing, the mid-run re-read and the assignment-count re-baseline).
colab_gpu_rate_gate_arm "${OUT_DIR}" "${CARD}" "${MAX_RATE}" "${TEST_MODE}"
# A GPU card names its machine shape (--shape standard|high-mem, no default: SHAPE_REQUIRED); a CPU
# card keeps colab new --high-mem and takes no --shape (colab_window.sh, colab_shape_gate_arm).
colab_shape_gate_arm "${OUT_DIR}" "${CARD}" "${SHAPE}"
# Refuse CAP_TOO_SMALL_FOR_CLEANUP before any colab call when cap - margin - cleanup_reserve <= 0
# or when the cap leaves less runtime than --min-runtime-s.
colab_cap_budget_gate "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" "render" "${CARD}" "${CAP}" "${MARGIN}" "${MAX_RATE}" "${RATE_CCU_PER_HOUR:-0.26}" "${MIN_RUNTIME_S}"

# Render / render-cpu-stub input pinning & validation before any colab call.
if [ "${LANE1_MODE}" = "render" ]; then
  VALIDATE_OUT=""
  if ! VALIDATE_OUT="$("${PY_BIN}" "${LANE1_PY}" --validate-render-inputs --weights-manifest "${WEIGHTS_MANIFEST}" --jobs "${JOBS_FILE}" --jobs-sha256 "${JOBS_SHA256_CLEAN}" 2>&1)"; then
    printf '%s\n' "${VALIDATE_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
    exit 2
  fi
  printf '%s\n' "${VALIDATE_OUT}" >> "${OUT_DIR}/guards.log"
elif [ "${LANE1_MODE}" = "render_cpu_stub" ]; then
  VALIDATE_OUT=""
  if ! VALIDATE_OUT="$("${PY_BIN}" "${LANE1_PY}" --validate-render-inputs --weights-manifest "${WEIGHTS_MANIFEST}" --allow-no-jobs 2>&1)"; then
    printf '%s\n' "${VALIDATE_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
    exit 2
  fi
  printf '%s\n' "${VALIDATE_OUT}" >> "${OUT_DIR}/guards.log"
fi

# Free pre-flight resolve & git pin check before any colab CLI call.
# The pre-flight honours its SDLAB_PREFLIGHT_* test hooks only under the fake colab CLI
# and refuses them in a live run (PREFLIGHT_TEST_HOOK_IN_LIVE_RUN).
PREFLIGHT_OUT=""
if ! PREFLIGHT_OUT="$(bash "${SCRIPT_DIR}/preflight_resolve.sh" lane1 2>&1)"; then
  printf '%s\n' "${PREFLIGHT_OUT}" | tee -a "${OUT_DIR}/guards.log" >&2
  exit 1
fi
printf '%s\n' "${PREFLIGHT_OUT}" >> "${OUT_DIR}/guards.log"

# Stage HF_TOKEN_GGUF_READ when provided for --render / --render-cpu-stub as a mode-600 file in a
# private tmpfs directory (never --env or argv; shredded on the VM before anything else runs).
if [ "${LANE1_MODE}" != "stub" ] && [ -n "${HF_TOKEN_GGUF_READ:-}" ]; then
  if [[ "${HF_TOKEN_GGUF_READ}" =~ [[:space:]] ]]; then
    colab_refuse_logged "${OUT_DIR}" HF_READ_TOKEN_MISSING "HF_TOKEN_GGUF_READ must not contain whitespace"
    exit 1
  fi
  if ! TOKEN_DIR="$(umask 077 && mktemp -d "${XDG_RUNTIME_DIR:-/dev/shm}/sdlab-l1-tok.XXXXXX" 2>/dev/null)"; then
    TOKEN_DIR=""
    colab_refuse_logged "${OUT_DIR}" HF_TOKEN_STAGING_FAILED "no private tmpfs directory (XDG_RUNTIME_DIR or /dev/shm) for the token file"
    exit 1
  fi
  if ! ( umask 077 && printf '%s' "${HF_TOKEN_GGUF_READ}" > "${TOKEN_DIR}/lane1_hf_read_token" ) \
    || ! chmod 600 "${TOKEN_DIR}/lane1_hf_read_token"; then
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
MAIN_PID="$$"
colab_run_wall_watcher \
  "${MAIN_PID}" "${WALL_LIMIT_S}" "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}" \
  "render" "${SESSION}" "${CARD}" "${CAP}" "${WALL_S}" "${GRACE_S}" "${MARGIN}" \
  "${OPENED_AT}" "${SHAS_JSON}" &
WALL_WATCHER_PID="$!"

# Hold /tmp/colab-window-open.lock while opening with colab new (CPU: --high-mem; GPU: --high-mem
# only for --shape high-mem, then the session row's Shape is checked: SHAPE_MISMATCH)
SESSION_OPENED=1
colab_open_session_locked "${SESSION}" "${CARD}" "${OUT_DIR}"
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
colab_check_pre_exec_cap "${OUT_DIR}"

REMOTE_RUNNER="${OUT_DIR}/remote_lane1_stub.sh"
cat > "${REMOTE_RUNNER}" << REMOTEEOF
#!/usr/bin/env bash
set -euo pipefail

# >>> sdlab-hf-token
# The HF read token reaches the VM only as /content/lane1_hf_read_token (never --env or argv).
# Read into a shell variable and shred here, before anything else runs, and hand only to the
# weights download step's environment. Logs are scrubbed of hf_ tokens before bundling.
LANE1_HF_READ_TOKEN=""
LANE1_HF_TOKEN_STAGED=0
if [ -f /content/lane1_hf_read_token ]; then
  LANE1_HF_READ_TOKEN="\$(cat /content/lane1_hf_read_token)"
  [ -s /content/lane1_hf_read_token ] && LANE1_HF_TOKEN_STAGED=1
  shred -u /content/lane1_hf_read_token 2>/dev/null || rm -f /content/lane1_hf_read_token
  if [ -e /content/lane1_hf_read_token ]; then
    echo "REFUSED: HF_TOKEN_SHRED_FAILED: /content/lane1_hf_read_token is still on the VM" >&2
    exit 1
  fi
fi
unset HF_TOKEN_GGUF_READ HF_TOKEN HUGGING_FACE_HUB_TOKEN
# <<< sdlab-hf-token

# >>> sdlab-lane1-mode
LANE1_MODE="\${LANE1_MODE:-stub}"
case "\${LANE1_MODE}" in
  stub)
    export CUDA_VISIBLE_DEVICES=""
    ;;
  render_cpu_stub)
    export CUDA_VISIBLE_DEVICES=""
    if ! [[ "\${LANE1_HOST_RAM_REQUIRED_GIB:-}" =~ ^[0-9]+(\.[0-9]+)?\$ ]] || [[ "\${LANE1_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?\$ ]]; then
      echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: LANE1_MODE=render_cpu_stub needs LANE1_HOST_RAM_REQUIRED_GIB" >&2
      exit 1
    fi
    if ! [[ "\${LANE1_DOWNLOAD_MAX_SECONDS:-}" =~ ^[1-9][0-9]*\$ ]]; then
      echo "REFUSED: DOWNLOAD_LIMIT_MISSING: LANE1_MODE=render_cpu_stub needs LANE1_DOWNLOAD_MAX_SECONDS" >&2
      exit 1
    fi
    ;;
  render)
    if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L 2>/dev/null | grep -q '^GPU [0-9]'; then
      echo "REFUSED: RENDER_REQUIRES_GPU: LANE1_MODE=render needs an NVIDIA GPU; nvidia-smi lists none on this VM" >&2
      exit 1
    fi
    if ! [[ "\${LANE1_JOBS_SHA256:-}" =~ ^[0-9a-f]{64}\$ ]]; then
      echo "REFUSED: RENDER_JOBS_SHA_REQUIRED: LANE1_MODE=render needs LANE1_JOBS_SHA256 (64-hex)" >&2
      exit 1
    fi
    if ! [[ "\${LANE1_COPY_BACK_EVERY:-}" =~ ^[1-9][0-9]*\$ ]]; then
      echo "REFUSED: RENDER_COPY_BACK_REQUIRED: LANE1_MODE=render needs LANE1_COPY_BACK_EVERY" >&2
      exit 1
    fi
    if ! [[ "\${LANE1_HOST_RAM_REQUIRED_GIB:-}" =~ ^[0-9]+(\.[0-9]+)?\$ ]] || [[ "\${LANE1_HOST_RAM_REQUIRED_GIB}" =~ ^0+(\.0+)?\$ ]]; then
      echo "REFUSED: HOST_RAM_THRESHOLD_MISSING: LANE1_MODE=render needs LANE1_HOST_RAM_REQUIRED_GIB" >&2
      exit 1
    fi
    if ! [[ "\${LANE1_DOWNLOAD_MAX_SECONDS:-}" =~ ^[1-9][0-9]*\$ ]]; then
      echo "REFUSED: DOWNLOAD_LIMIT_MISSING: LANE1_MODE=render needs LANE1_DOWNLOAD_MAX_SECONDS" >&2
      exit 1
    fi
    ;;
  *)
    echo "REFUSED: LANE1_MODE_INVALID: LANE1_MODE=\${LANE1_MODE}; expected stub, render_cpu_stub or render" >&2
    exit 1
    ;;
esac
# <<< sdlab-lane1-mode

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

  /content/venv-lane1/bin/python - "\${LANE1_MODE:-stub}" << 'IMPEOF'
import importlib
import sys

mode = sys.argv[1]
required = ["comfy_headless", "torch", "safetensors", "PIL", "yaml", "aiohttp"]
if mode != "stub":
    required.append("huggingface_hub")
for mod_name in required:
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
IMPEOF
} 2>&1 | tee -a /content/lane1_out/setup.log

if [ "\${LANE1_MODE:-stub}" = "stub" ]; then
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
else
# >>> sdlab-lane1-render
: "\${LANE1_DISK_REQUIRED_GIB:?missing LANE1_DISK_REQUIRED_GIB}"
: "\${LANE1_GPU_SMOKE_SECONDS:?missing LANE1_GPU_SMOKE_SECONDS}"
: "\${LANE1_DOWNLOAD_PROBE_SECONDS:?missing LANE1_DOWNLOAD_PROBE_SECONDS}"
: "\${LANE1_DOWNLOAD_PROBE_BYTES:?missing LANE1_DOWNLOAD_PROBE_BYTES}"
LANE1_HF_HOME="/content/hf_home"
LANE1_MODELS_DIR="/content/ComfyUI/models"
COMFY_PID=""

lane1_render_on_exit() {
  local rc=\$?
  trap - EXIT
  kill "\${COMFY_PID:-}" 2>/dev/null || true
  kill "\${VITALS_PID:-}" 2>/dev/null || true
  if [ "\${rc}" -ne 0 ] && [ ! -f /content/lane1_render_bundle.tar.gz ]; then
    /content/venv-lane1/bin/python /content/lane1_render.py \
      --merge-render-facts --lane1-out /content/lane1_out --failed-rc "\${rc}" || true
    while IFS= read -r -d '' f; do
      /content/venv-lane1/bin/python /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
    done < <(find /content/lane1_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" -o -name "*.txt" \) -print0 2>/dev/null || true)
    tar -czf /content/lane1_render_bundle.tar.gz -C /content/lane1_out . || true
    echo "RENDER_BUNDLE_AFTER_FAILURE rc=\${rc} /content/lane1_render_bundle.tar.gz"
  fi
  exit "\${rc}"
}
trap lane1_render_on_exit EXIT

mkdir -p "\${LANE1_HF_HOME}" "\${LANE1_MODELS_DIR}" /content/lane1_out/copy_back

GUARDS_EXTRA_ARGS=()
if [ "\${LANE1_MODE}" = "render_cpu_stub" ]; then
  GUARDS_EXTRA_ARGS+=("--cpu-stub")
fi
/content/venv-lane1/bin/python /content/lane1_render.py \
  --vm-guards \
  --hf-home "\${LANE1_HF_HOME}" \
  --models-dir "\${LANE1_MODELS_DIR}" \
  --lane1-out /content/lane1_out \
  --disk-required-gib "\${LANE1_DISK_REQUIRED_GIB}" \
  --smoke-seconds "\${LANE1_GPU_SMOKE_SECONDS}" \
  --ram-required-gib "\${LANE1_HOST_RAM_REQUIRED_GIB}" \
  --meminfo /proc/meminfo \
  --shm /dev/shm \
  --guards-out /content/lane1_out/render_guards.json \
  "\${GUARDS_EXTRA_ARGS[@]}" 2>&1 | tee -a /content/lane1_out/setup.log

lane1_download_weights() {
  /content/venv-lane1/bin/python /content/lane1_render.py \
    --download-weights \
    --weights-manifest /content/weights_manifest.json \
    --hf-home "\${LANE1_HF_HOME}" \
    --models-dir "\${LANE1_MODELS_DIR}" \
    --max-seconds "\${LANE1_DOWNLOAD_MAX_SECONDS}" \
    --probe-seconds "\${LANE1_DOWNLOAD_PROBE_SECONDS}" \
    --probe-bytes "\${LANE1_DOWNLOAD_PROBE_BYTES}" \
    --download-log /content/lane1_out/weights_download.log \
    --download-out /content/lane1_out/weights_download.json
}
if [ "\${LANE1_HF_TOKEN_STAGED:-0}" = "1" ]; then
  HF_TOKEN_GGUF_READ="\${LANE1_HF_READ_TOKEN}" lane1_download_weights 2>&1 | tee -a /content/lane1_out/setup.log
else
  lane1_download_weights 2>&1 | tee -a /content/lane1_out/setup.log
fi
LANE1_HF_READ_TOKEN=""

if [ "\${LANE1_MODE}" = "render_cpu_stub" ]; then
  /content/venv-lane1/bin/python - "\${PINNED_COMFYUI_COMMIT}" /content/lane1_out/vm_window.json << 'CPUSTUBEOF'
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

comfy_commit, out_p = sys.argv[1], Path(sys.argv[2])
sys_py_bin = (
    os.environ["SDLAB_FAKE_SYS_PYTHON_BIN"]
    if (os.environ.get("FAKE_VM_SITE") and os.environ.get("SDLAB_FAKE_SYS_PYTHON_BIN"))
    else "/usr/bin/python3"
)
sys_py = subprocess.run([sys_py_bin, "--version"], capture_output=True, text=True, check=False).stdout.strip().split()[-1]
try:
    uv_ver = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False).stdout.strip() or "uv 0.13.5"
except OSError:
    uv_ver = "uv 0.13.5"
py_sha = "sha256:" + hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
rec = {
    "system_python": sys_py,
    "python": sys.version.split()[0],
    "python_sha256": py_sha,
    "uv": uv_ver,
    "comfyui_commit": comfy_commit,
    "lane1_mode": "render_cpu_stub",
}
out_p.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
CPUSTUBEOF
  /content/venv-lane1/bin/python /content/lane1_render.py \
    --merge-render-facts --lane1-out /content/lane1_out --render-state skipped_cpu_stub
  echo "RENDER_CPU_STUB_OK: weights downloaded, sha256-checked and unpacked on CPU" | tee -a /content/lane1_out/setup.log
else
  ACTUAL_JOBS_SHA="\$(sha256sum /content/jobs.jsonl | awk '{print \$1}')"
  if [ "\${ACTUAL_JOBS_SHA}" != "\${LANE1_JOBS_SHA256}" ]; then
    echo "REFUSED: JOBS_SHA_MISMATCH: /content/jobs.jsonl sha256=\${ACTUAL_JOBS_SHA} expected=\${LANE1_JOBS_SHA256}" >&2
    exit 1
  fi
  mv /content/jobs.jsonl /content/lane1_out/jobs.jsonl
  FIRST_JOB_ID="\$(/content/venv-lane1/bin/python -c 'import json, sys; print(next(json.loads(ln)["job_id"] for ln in open(sys.argv[1], encoding="utf-8") if ln.strip()))' /content/lane1_out/jobs.jsonl)"

  echo "run" > /content/lane1_out/phase.txt
  COMFY_PORT="\${LANE1_COMFY_PORT:-8188}"
  COMFY_URL="http://127.0.0.1:\${COMFY_PORT}"
  /content/venv-lane1/bin/python /content/ComfyUI/main.py --listen 127.0.0.1 --port "\${COMFY_PORT}" --disable-auto-launch \
    > /content/lane1_out/comfyui.log 2>&1 &
  COMFY_PID="\$!"

  COMFY_READY=0
  for _ in \$(seq 1 120); do
    if curl -sf "\${COMFY_URL}/system_stats" >/dev/null 2>&1; then
      COMFY_READY=1
      break
    fi
    if ! kill -0 "\${COMFY_PID}" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if [ "\${COMFY_READY}" -ne 1 ]; then
    tail -n 40 /content/lane1_out/comfyui.log >&2 || true
    echo "REFUSED: COMFY_STARTUP_FAILED: ComfyUI failed to listen on \${COMFY_URL}" >&2
    exit 1
  fi

  set +e
  /content/venv-lane1/bin/python /content/lane1_render.py \
    --bootstrap \
    --window-id "\${LANE1_SESSION_ID:-win_lane1_render}" \
    --comfy-url "\${COMFY_URL}" \
    --comfy-pid "\${COMFY_PID}" \
    --comfyui-commit "\${PINNED_COMFYUI_COMMIT}" \
    --window-json /content/lane1_out/vm_window.json \
    --jobs /content/lane1_out/jobs.jsonl \
    --renders /content/lane1_out/renders.jsonl \
    --out-dir /content/lane1_out/pngs \
    --copy-back-dir /content/lane1_out/copy_back \
    --copy-back-every "\${LANE1_COPY_BACK_EVERY}" \
    --kill-after 1
  RC1=\$?
  set -e
  if [ "\${RC1}" -ne 75 ]; then
    echo "Expected exit 75 on deliberate kill-after=1, got \${RC1}" >&2
    exit 1
  fi

  SHA_BEFORE="\$(sha256sum "/content/lane1_out/pngs/\${FIRST_JOB_ID}.png" | awk '{print \$1}')"

  /content/venv-lane1/bin/python /content/lane1_render.py \
    --window-id "\${LANE1_SESSION_ID:-win_lane1_render}" \
    --comfy-url "\${COMFY_URL}" \
    --jobs /content/lane1_out/jobs.jsonl \
    --renders /content/lane1_out/renders.jsonl \
    --out-dir /content/lane1_out/pngs \
    --copy-back-dir /content/lane1_out/copy_back \
    --copy-back-every "\${LANE1_COPY_BACK_EVERY}"

  SHA_AFTER="\$(sha256sum "/content/lane1_out/pngs/\${FIRST_JOB_ID}.png" | awk '{print \$1}')"
  SHA_COPY="\$(sha256sum "/content/lane1_out/copy_back/\${FIRST_JOB_ID}.png" | awk '{print \$1}')"
  if [ "\${SHA_BEFORE}" != "\${SHA_AFTER}" ] || [ "\${SHA_BEFORE}" != "\${SHA_COPY}" ]; then
    echo "Resume hash mismatch: before=\${SHA_BEFORE} after=\${SHA_AFTER} copy=\${SHA_COPY}" >&2
    exit 1
  fi

  kill "\${COMFY_PID}" 2>/dev/null || true
  COMFY_PID=""
  /content/venv-lane1/bin/python /content/lane1_render.py \
    --merge-render-facts --lane1-out /content/lane1_out --render-state rendered
fi

while IFS= read -r -d '' f; do
  /content/venv-lane1/bin/python /content/launch_guards.py --scrub-file "\${f}" </dev/null || true
done < <(find /content/lane1_out -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" -o -name "*.txt" \) -print0 2>/dev/null || true)
tar -czf /content/lane1_render_bundle.tar.gz -C /content/lane1_out .
# <<< sdlab-lane1-render
fi
REMOTEEOF

# Every upload goes flat into /content, the one remote directory that exists before the remote
# script runs.
colab_upload_checked "${SESSION}" "${LOCK_FILE}" /content/lane1.lock "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${LANE1_PY}" /content/lane1_render.py "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${GUARDS_PY}" /content/launch_guards.py "${OUT_DIR}"
colab_upload_checked "${SESSION}" "${CLASSIFIER_PY}" /content/classify_install_log.py "${OUT_DIR}"
if [ "${LANE1_MODE}" != "stub" ]; then
  colab_upload_checked "${SESSION}" "${RUNG_PY}" /content/lane3_rung.py "${OUT_DIR}"
  colab_upload_checked "${SESSION}" "${WEIGHTS_MANIFEST}" /content/weights_manifest.json "${OUT_DIR}"
  if [ "${LANE1_MODE}" = "render" ]; then
    colab_upload_checked "${SESSION}" "${JOBS_FILE}" /content/jobs.jsonl "${OUT_DIR}"
  fi
  if [ -n "${TOKEN_DIR}" ]; then
    colab_upload_checked "${SESSION}" "${TOKEN_DIR}/lane1_hf_read_token" /content/lane1_hf_read_token "${OUT_DIR}"
    rm -rf "${TOKEN_DIR}"
    TOKEN_DIR=""
  fi
fi
colab_upload_checked "${SESSION}" "${REMOTE_RUNNER}" /content/remote_lane1_stub.sh "${OUT_DIR}"
colab_check_pre_exec_cap "${OUT_DIR}"

REMOTE_ENV=(
  "SDLAB_REMOTE_SCRIPT=/content/remote_lane1_stub.sh"
  "PINNED_UV_VERSION=${PINNED_UV_VERSION}"
  "PINNED_UV_WHEEL_SHA256=${PINNED_UV_WHEEL_SHA256}"
  "PINNED_PYTHON_VERSION=${PINNED_PYTHON_VERSION}"
  "PINNED_PYTHON_BUILD=${PINNED_PYTHON_BUILD}"
  "PINNED_PYTORCH_INDEX_URL=${PINNED_PYTORCH_INDEX_URL}"
  "PINNED_COMFYUI_REPO=${PINNED_COMFYUI_REPO}"
  "PINNED_COMFYUI_COMMIT=${PINNED_COMFYUI_COMMIT}"
  "PINNED_COMFY_HEADLESS_SPEC=${PINNED_COMFY_HEADLESS_SPEC}"
  "PINNED_LOCK_SHA=${EXP_LOCK_SHA}"
)
if [ "${LANE1_MODE}" != "stub" ]; then
  REMOTE_ENV+=(
    "LANE1_MODE=${LANE1_MODE}"
    "LANE1_SESSION_ID=${SESSION}"
    "LANE1_HOST_RAM_REQUIRED_GIB=${RENDER_HOST_RAM_REQUIRED_GIB}"
    "LANE1_DOWNLOAD_MAX_SECONDS=${RENDER_DOWNLOAD_MAX_SECONDS}"
    "LANE1_DISK_REQUIRED_GIB=${LANE1_DISK_REQUIRED_GIB}"
    "LANE1_GPU_SMOKE_SECONDS=${LANE1_GPU_SMOKE_SECONDS}"
    "LANE1_DOWNLOAD_PROBE_SECONDS=${LANE1_DOWNLOAD_PROBE_SECONDS}"
    "LANE1_DOWNLOAD_PROBE_BYTES=${LANE1_DOWNLOAD_PROBE_BYTES}"
    "LANE1_COMFY_PORT=${LANE1_COMFY_PORT}"
  )
  if [ "${LANE1_MODE}" = "render" ]; then
    REMOTE_ENV+=(
      "LANE1_JOBS_SHA256=${JOBS_SHA256_CLEAN}"
      "LANE1_COPY_BACK_EVERY=${COPY_BACK_EVERY}"
    )
  fi
fi

EXEC_IN_FLIGHT=1
colab_run_exec_with_live_guards \
  "${PY_BIN}" "${GUARDS_PY}" "${SESSION}" "${RUNNER_PY}" \
  "${START_EPOCH}" "${WALL_S}" "${GRACE_S}" "${CAP}" "${MARGIN}" "${OUT_DIR}" \
  "${REMOTE_ENV[@]}"

# Download result tar before EXIT trap stops the session
colab_download_checked "${SESSION}" "/content/${BUNDLE_NAME}" "${OUT_DIR}/${BUNDLE_NAME}" "${OUT_DIR}"
EXEC_IN_FLIGHT=0
colab_scrub_all_logs "${PY_BIN}" "${GUARDS_PY}" "${OUT_DIR}"
