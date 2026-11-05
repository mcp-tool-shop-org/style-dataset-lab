#!/usr/bin/env bash
# Free pre-flight resolve & pin check for sdlab Colab kits (Item 5).
# Usage: bash scripts/colab/preflight_resolve.sh <lane1|lane3|1|3> [--wheel-dir <dir>]
#
# Checks (with zero colab CLI calls):
# 1. Re-runs `uv pip compile` against scripts/colab/locks/lane<N>.in and fails
#    with `LOCK_DRIFT` if the output differs from committed scripts/colab/locks/lane<N>.lock.
# 2. Checks that every pinned upstream git sha exists via `git ls-remote`,
#    failing with `PIN_NOT_FOUND` if missing.
# 3. For lane 3 (or when --wheel-dir / SDLAB_WHEEL_DIR is checked), verifies that
#    the local pre-built wheels listed in scripts/colab/locks/lane3-local-wheels.json
#    exist (`LOCAL_WHEEL_MISSING`) and match their recorded sha256 (`LOCAL_WHEEL_SHA_MISMATCH`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

LANE_RAW="${1:-}"
if [[ -z "${LANE_RAW}" ]]; then
  echo "Usage: $0 <lane1|lane3> [--wheel-dir <dir>]" >&2
  exit 2
fi
shift || true

WHEEL_DIR="${SDLAB_WHEEL_DIR:-}"
SKIP_LOCAL_WHEELS="${SDLAB_SKIP_LOCAL_WHEEL_CHECK:-0}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --wheel-dir)
      WHEEL_DIR="${2:-}"
      shift 2
      ;;
    --skip-local-wheels)
      SKIP_LOCAL_WHEELS=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

case "${LANE_RAW}" in
  lane1|1)
    LANE="lane1"
    PY_VER="3.14.9"
    IN_REL="scripts/colab/locks/lane1.in"
    LOCK_REL="scripts/colab/locks/lane1.lock"
    LAUNCH_SH="${SCRIPT_DIR}/launch_lane1_stub.sh"
    ;;
  lane3|3)
    LANE="lane3"
    PY_VER="3.12.15"
    IN_REL="scripts/colab/locks/lane3.in"
    LOCK_REL="scripts/colab/locks/lane3.lock"
    LAUNCH_SH="${SCRIPT_DIR}/launch_lane3_stub.sh"
    ;;
  *)
    echo "Unknown lane: ${LANE_RAW} (expected lane1 or lane3)" >&2
    exit 2
    ;;
esac

IN_FILE="${SDLAB_PREFLIGHT_IN_FILE:-${REPO_ROOT}/${IN_REL}}"
LOCK_FILE="${SDLAB_PREFLIGHT_LOCK_FILE:-${REPO_ROOT}/${LOCK_REL}}"

if [[ ! -f "${IN_FILE}" ]] || [[ ! -f "${LOCK_FILE}" ]]; then
  echo "LOCK_DRIFT: missing ${IN_FILE} or ${LOCK_FILE}" >&2
  exit 1
fi

# 1. Check local wheels first (for lane3, unless --skip-local-wheels is set for CI)
if [[ "${LANE}" == "lane3" ]] && [[ "${SKIP_LOCAL_WHEELS}" != "1" ]]; then
  WHEELS_MANIFEST="${SDLAB_PREFLIGHT_WHEELS_MANIFEST:-${REPO_ROOT}/scripts/colab/locks/lane3-local-wheels.json}"
  if [[ ! -f "${WHEELS_MANIFEST}" ]]; then
    echo "LOCAL_WHEEL_MISSING: manifest ${WHEELS_MANIFEST} not found" >&2
    exit 1
  fi

  PY_BIN="$(command -v python3 || command -v python)"
  if [[ -z "${WHEEL_DIR}" ]]; then
    WHEEL_DIR="$("${PY_BIN}" -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); print(d.get("default_wheel_dir", ""))' "${WHEELS_MANIFEST}")"
  fi
  # Convert Windows E:/... path to /mnt/e/... when running inside WSL
  if [[ "${WHEEL_DIR}" =~ ^([A-Za-z]):/(.*)$ ]] && [[ -d "/mnt/${BASH_REMATCH[1],,}" ]]; then
    DRIVE_LOWER="${BASH_REMATCH[1],,}"
    REST_PATH="${BASH_REMATCH[2]}"
    if [[ ! -d "${WHEEL_DIR}" ]] && [[ -d "/mnt/${DRIVE_LOWER}/${REST_PATH}" ]]; then
      WHEEL_DIR="/mnt/${DRIVE_LOWER}/${REST_PATH}"
    fi
  fi

  if [[ -z "${WHEEL_DIR}" ]] || [[ ! -d "${WHEEL_DIR}" ]]; then
    echo "LOCAL_WHEEL_MISSING: wheel directory '${WHEEL_DIR}' does not exist" >&2
    exit 1
  fi

  WHEEL_CHECK_OUT="$("${PY_BIN}" - "${WHEELS_MANIFEST}" "${WHEEL_DIR}" <<'PY'
import hashlib
import json
import os
import sys

manifest_path = sys.argv[1]
wheel_dir = sys.argv[2]

with open(manifest_path, "r", encoding="utf-8") as f:
    data = json.load(f)

wheels = data.get("wheels", [])
if not wheels:
    print("LOCAL_WHEEL_MISSING: no wheels listed in manifest")
    sys.exit(1)

for entry in wheels:
    fname = entry.get("filename", "")
    expected_sha = entry.get("sha256", "").lower().removeprefix("sha256:")
    fpath = os.path.join(wheel_dir, fname)
    if not fname or not os.path.isfile(fpath):
        print(f"LOCAL_WHEEL_MISSING: {fname} not found in {wheel_dir}")
        sys.exit(1)
    h = hashlib.sha256()
    with open(fpath, "rb") as wf:
        while chunk := wf.read(65536):
            h.update(chunk)
    actual_sha = h.hexdigest().lower()
    if actual_sha != expected_sha:
        print(f"LOCAL_WHEEL_SHA_MISMATCH: {fname} expected {expected_sha}, got {actual_sha}")
        sys.exit(1)

print("LOCAL_WHEELS_OK")
PY
  )" || {
    echo "${WHEEL_CHECK_OUT}" >&2
    exit 1
  }
fi

# 2. Check pinned upstream git shas via git ls-remote
check_git_pin() {
  local repo_url="$1"
  local expected_sha="$2"
  local label="$3"

  if [[ ! "${expected_sha}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "PIN_NOT_FOUND: invalid sha '${expected_sha}' for ${label}" >&2
    exit 1
  fi

  local ls_out=""
  if [[ -n "${SDLAB_PREFLIGHT_LS_REMOTE_OVERRIDE:-}" ]]; then
    ls_out="${SDLAB_PREFLIGHT_LS_REMOTE_OVERRIDE}"
  else
    ls_out="$(GIT_DIR=/dev/null git -C /tmp ls-remote "${repo_url}" 2>/dev/null || true)"
  fi

  if grep -Fq "${expected_sha}" <<<"${ls_out}"; then
    return 0
  fi

  echo "PIN_NOT_FOUND: ${label} commit ${expected_sha} not found in git ls-remote ${repo_url}" >&2
  exit 1
}

if [[ "${LANE}" == "lane1" ]]; then
  COMFY_REPO="${SDLAB_PREFLIGHT_PIN_REPO:-$(grep -E '^PINNED_COMFYUI_REPO=' "${LAUNCH_SH}" | head -n1 | cut -d'"' -f2)}"
  COMFY_SHA="${SDLAB_PREFLIGHT_PIN_SHA:-$(grep -E '^PINNED_COMFYUI_COMMIT=' "${LAUNCH_SH}" | head -n1 | cut -d'"' -f2)}"
  check_git_pin "${COMFY_REPO}" "${COMFY_SHA}" "ComfyUI"
else
  AITK_REPO="${SDLAB_PREFLIGHT_PIN_REPO:-$(grep -E '^PINNED_AI_TOOLKIT_REPO=' "${LAUNCH_SH}" | head -n1 | cut -d'"' -f2)}"
  AITK_SHA="${SDLAB_PREFLIGHT_PIN_SHA:-$(grep -E '^PINNED_AI_TOOLKIT_COMMIT=' "${LAUNCH_SH}" | head -n1 | cut -d'"' -f2)}"
  check_git_pin "${AITK_REPO}" "${AITK_SHA}" "ai-toolkit"
fi

# 3. Re-run uv pip compile and compare with committed lock
if [[ "${SDLAB_PREFLIGHT_FAST_COMPILE_MOCK:-0}" == "1" ]]; then
  TMP_LOCK="$(mktemp)"
  trap 'rm -f "${TMP_LOCK}"' EXIT
  if [[ -n "${SDLAB_PREFLIGHT_MOCK_COMPILE_OUT:-}" ]]; then
    cp "${SDLAB_PREFLIGHT_MOCK_COMPILE_OUT}" "${TMP_LOCK}"
  else
    cp "${REPO_ROOT}/${LOCK_REL}" "${TMP_LOCK}"
  fi
else
  UV_BIN="${UV_BIN:-$(command -v uv || true)}"
  if [[ -z "${UV_BIN}" ]] && [[ -x "${HOME}/uv13bin/uv" ]]; then
    UV_BIN="${HOME}/uv13bin/uv"
  fi
  if [[ -z "${UV_BIN}" ]]; then
    echo "LOCK_DRIFT: uv binary not found" >&2
    exit 1
  fi

  TMP_LOCK="$(mktemp)"
  trap 'rm -f "${TMP_LOCK}"' EXIT

  CUSTOM_CMD="uv pip compile --generate-hashes --only-binary :all: --python-platform x86_64-manylinux_2_28 --python-version ${PY_VER} --extra-index-url https://download.pytorch.org/whl/cu130 --index-strategy unsafe-best-match ${IN_REL} -o ${LOCK_REL}"

  (
    cd "${REPO_ROOT}"
    "${UV_BIN}" pip compile \
      --generate-hashes \
      --only-binary :all: \
      --python-platform x86_64-manylinux_2_28 \
      --python-version "${PY_VER}" \
      --extra-index-url https://download.pytorch.org/whl/cu130 \
      --index-strategy unsafe-best-match \
      --custom-compile-command "${CUSTOM_CMD}" \
      "${IN_FILE}" \
      -o "${TMP_LOCK}" >/dev/null 2>&1
  ) || {
    echo "LOCK_DRIFT: uv pip compile failed for ${LANE} (python ${PY_VER})" >&2
    exit 1
  }
fi

NORM_COMMITTED="$(mktemp)"
NORM_COMPILED="$(mktemp)"
trap 'rm -f "${TMP_LOCK:-}" "${NORM_COMMITTED}" "${NORM_COMPILED}"' EXIT
tr -d '\r' < "${LOCK_FILE}" > "${NORM_COMMITTED}"
tr -d '\r' < "${TMP_LOCK}" > "${NORM_COMPILED}"

if ! diff -u "${NORM_COMMITTED}" "${NORM_COMPILED}" >/dev/null 2>&1; then
  echo "LOCK_DRIFT: compiled output for ${LANE} differs from committed ${LOCK_FILE}" >&2
  diff -u "${NORM_COMMITTED}" "${NORM_COMPILED}" | head -n 40 >&2 || true
  exit 1
fi

PIN_COUNT="$(grep -c '^[a-zA-Z0-9_-]*==' "${NORM_COMMITTED}")"
echo "PREFLIGHT_OK lane=${LANE} python=${PY_VER} pins=${PIN_COUNT}"
