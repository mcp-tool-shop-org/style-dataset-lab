#!/usr/bin/env bash
# Free pre-flight resolve & pin check for sdlab Colab kits.
# Usage: bash scripts/colab/preflight_resolve.sh <lane1|lane3|1|3> [--wheel-dir <dir>] [--skip-local-wheels]
#
# Checks, with zero colab CLI calls. Every failure is one line `REFUSED: <CODE>: <detail>` on
# stderr, exit 1:
# 1. Tools and inputs: git (and python for lane 3) on PATH and uv unless the compile is
#    mocked (`PREFLIGHT_TOOL_MISSING`); the lane's .in, .lock and, for lane 3, the local-wheel
#    manifest (`LOCK_INPUT_MISSING`).
# 2. Lane 3 local wheels (skipped with --skip-local-wheels, as CI does): the wheel directory
#    comes from --wheel-dir or SDLAB_WHEEL_DIR, never a default (`WHEEL_DIR_REQUIRED`); each
#    wheel in scripts/colab/locks/lane3-local-wheels.json must exist (`LOCAL_WHEEL_MISSING`)
#    and match its sha256 (`LOCAL_WHEEL_SHA_MISMATCH`).
# 3. Every pinned upstream git commit (the kit's ComfyUI or ai-toolkit pin, and for lane 3
#    each git_commit in the wheel manifest) is fetched by sha into a throwaway bare repo, so
#    a commit that is not a branch tip still passes. A commit the server says it does not
#    have is `PIN_NOT_FOUND`; an unreachable server or any other fetch failure is
#    `PIN_CHECK_UNAVAILABLE`.
# 4. uv must be the kits' pinned version (`UV_VERSION_MISMATCH`; this script refuses, it
#    never installs uv). The compile is re-run; a failed compile is `LOCK_COMPILE_FAILED`,
#    and a compile that succeeds but differs from the committed lock is `LOCK_DRIFT`.
#
# Test hooks (the SDLAB_PREFLIGHT_* variables listed in TEST_HOOK_VARS) are honoured only
# when SDLAB_TEST_FAKE_COLAB=1 and `colab` on PATH is the fake CLI (#SDLAB_FAKE_COLAB_CLI=1).
# Any of them set in a live run is `PREFLIGHT_TEST_HOOK_IN_LIVE_RUN`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

refuse() {
  local code="$1"
  shift
  echo "REFUSED: ${code}: $*" >&2
  exit 1
}

TEST_HOOK_VARS=(
  SDLAB_PREFLIGHT_FAST_COMPILE_MOCK
  SDLAB_PREFLIGHT_MOCK_COMPILE_OUT
  SDLAB_PREFLIGHT_LS_REMOTE_OVERRIDE
  SDLAB_PREFLIGHT_PIN_REPO
  SDLAB_PREFLIGHT_PIN_SHA
  SDLAB_PREFLIGHT_LOCK_FILE
  SDLAB_PREFLIGHT_IN_FILE
  SDLAB_PREFLIGHT_WHEELS_MANIFEST
)

fake_colab_active() {
  [ "${SDLAB_TEST_FAKE_COLAB:-0}" = "1" ] || return 1
  local colab_bin
  colab_bin="$(command -v colab || true)"
  [ -n "${colab_bin}" ] && grep -q '^#SDLAB_FAKE_COLAB_CLI=1$' "${colab_bin}" 2>/dev/null
}

SET_HOOKS=()
for hook_var in "${TEST_HOOK_VARS[@]}"; do
  if [ -n "${!hook_var:-}" ]; then
    SET_HOOKS+=("${hook_var}")
  fi
done
TEST_MODE=0
if fake_colab_active; then
  TEST_MODE=1
elif [ "${#SET_HOOKS[@]}" -gt 0 ]; then
  refuse PREFLIGHT_TEST_HOOK_IN_LIVE_RUN "${SET_HOOKS[*]} set without SDLAB_TEST_FAKE_COLAB=1 and the fake colab CLI on PATH"
fi

# hook <name>: the hook's value in a fake-colab test run, empty otherwise.
hook() {
  if [ "${TEST_MODE}" = "1" ]; then
    printf '%s' "${!1:-}"
  fi
}

LANE_RAW="${1:-}"
if [[ -z "${LANE_RAW}" ]]; then
  echo "Usage: $0 <lane1|lane3> [--wheel-dir <dir>] [--skip-local-wheels]" >&2
  exit 2
fi
shift || true

WHEEL_DIR="${SDLAB_WHEEL_DIR:-}"
SKIP_LOCAL_WHEELS=0
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

IN_FILE="$(hook SDLAB_PREFLIGHT_IN_FILE)"
IN_FILE="${IN_FILE:-${REPO_ROOT}/${IN_REL}}"
LOCK_FILE="$(hook SDLAB_PREFLIGHT_LOCK_FILE)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/${LOCK_REL}}"
WHEELS_MANIFEST="$(hook SDLAB_PREFLIGHT_WHEELS_MANIFEST)"
WHEELS_MANIFEST="${WHEELS_MANIFEST:-${REPO_ROOT}/scripts/colab/locks/lane3-local-wheels.json}"
COMPILE_MOCK="$(hook SDLAB_PREFLIGHT_FAST_COMPILE_MOCK)"

# 1. Tools and inputs
command -v git >/dev/null 2>&1 || refuse PREFLIGHT_TOOL_MISSING "git not found on PATH"
PY_BIN=""
if [[ "${LANE}" == "lane3" ]]; then
  PY_BIN="$(command -v python3 || command -v python || true)"
  [[ -n "${PY_BIN}" ]] || refuse PREFLIGHT_TOOL_MISSING "python3 not found on PATH"
fi
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
if [[ "${COMPILE_MOCK}" != "1" ]]; then
  [[ -n "${UV_BIN}" && -x "${UV_BIN}" ]] || refuse PREFLIGHT_TOOL_MISSING "uv not found (PATH or UV_BIN)"
fi

[[ -f "${IN_FILE}" ]] || refuse LOCK_INPUT_MISSING "${IN_FILE} not found"
[[ -f "${LOCK_FILE}" ]] || refuse LOCK_INPUT_MISSING "${LOCK_FILE} not found"
if [[ "${LANE}" == "lane3" ]]; then
  [[ -f "${WHEELS_MANIFEST}" ]] || refuse LOCK_INPUT_MISSING "wheel manifest ${WHEELS_MANIFEST} not found"
fi

# 2. Lane 3 local wheels
if [[ "${LANE}" == "lane3" ]] && [[ "${SKIP_LOCAL_WHEELS}" != "1" ]]; then
  [[ -n "${WHEEL_DIR}" ]] || refuse WHEEL_DIR_REQUIRED "lane 3 needs --wheel-dir <dir> or SDLAB_WHEEL_DIR"
  # A Windows drive path (X:/...) given inside WSL is read through /mnt/<x>/...
  if [[ "${WHEEL_DIR}" =~ ^([A-Za-z]):/(.*)$ ]] && [[ ! -d "${WHEEL_DIR}" ]]; then
    WSL_PATH="/mnt/${BASH_REMATCH[1],,}/${BASH_REMATCH[2]}"
    if [[ -d "${WSL_PATH}" ]]; then
      WHEEL_DIR="${WSL_PATH}"
    fi
  fi
  [[ -d "${WHEEL_DIR}" ]] || refuse LOCAL_WHEEL_MISSING "wheel directory '${WHEEL_DIR}' does not exist"

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

# 3. Pinned upstream git commits, fetched by sha
export GIT_TERMINAL_PROMPT=0
export GIT_HTTP_LOW_SPEED_LIMIT=1000
export GIT_HTTP_LOW_SPEED_TIME=60
PIN_TMP_DIRS=()
TMP_LOCK=""
NORM_COMMITTED=""
NORM_COMPILED=""
COMPILE_LOG=""
cleanup() {
  rm -f "${TMP_LOCK}" "${NORM_COMMITTED}" "${NORM_COMPILED}" "${COMPILE_LOG}"
  local d
  for d in "${PIN_TMP_DIRS[@]}"; do
    rm -rf "${d}"
  done
}
trap cleanup EXIT

check_git_pin() {
  local repo_url="$1"
  local expected_sha="$2"
  local label="$3"

  if [[ ! "${expected_sha}" =~ ^[0-9a-f]{40}$ ]]; then
    refuse PIN_NOT_FOUND "invalid sha '${expected_sha}' for ${label}"
  fi
  [[ -n "${repo_url}" ]] || refuse LOCK_INPUT_MISSING "no repository URL for ${label}"

  local bare
  bare="$(mktemp -d)"
  PIN_TMP_DIRS+=("${bare}")
  git init -q --bare "${bare}"

  local out=""
  if ! out="$(git -C "${bare}" ls-remote "${repo_url}" HEAD 2>&1)"; then
    refuse PIN_CHECK_UNAVAILABLE "cannot reach ${repo_url} for ${label}: $(printf '%s\n' "${out}" | tail -n 1)"
  fi
  if out="$(git -C "${bare}" fetch -q --no-tags --depth 1 --filter=blob:none "${repo_url}" "${expected_sha}" 2>&1)" \
    && git -C "${bare}" cat-file -e "${expected_sha}^{commit}" 2>/dev/null; then
    echo "PIN_OK ${label} ${expected_sha}"
    return 0
  fi
  if grep -Eqi "not our ref|unadvertised object|couldn't find remote ref|no such remote ref|not a valid object" <<<"${out}"; then
    refuse PIN_NOT_FOUND "${label} commit ${expected_sha} not found in ${repo_url}"
  fi
  refuse PIN_CHECK_UNAVAILABLE "fetch of ${label} ${expected_sha} from ${repo_url} failed: $(printf '%s\n' "${out}" | tail -n 1)"
}

PIN_REPO_HOOK="$(hook SDLAB_PREFLIGHT_PIN_REPO)"
PIN_SHA_HOOK="$(hook SDLAB_PREFLIGHT_PIN_SHA)"
if [[ "${LANE}" == "lane1" ]]; then
  PIN_LABEL="ComfyUI"
  PIN_REPO_VAR="PINNED_COMFYUI_REPO"
  PIN_SHA_VAR="PINNED_COMFYUI_COMMIT"
else
  PIN_LABEL="ai-toolkit"
  PIN_REPO_VAR="PINNED_AI_TOOLKIT_REPO"
  PIN_SHA_VAR="PINNED_AI_TOOLKIT_COMMIT"
fi
PIN_REPO="${PIN_REPO_HOOK:-$(grep -E "^${PIN_REPO_VAR}=" "${LAUNCH_SH}" | head -n1 | cut -d'"' -f2)}"
PIN_SHA="${PIN_SHA_HOOK:-$(grep -E "^${PIN_SHA_VAR}=" "${LAUNCH_SH}" | head -n1 | cut -d'"' -f2)}"
check_git_pin "${PIN_REPO}" "${PIN_SHA}" "${PIN_LABEL}"

if [[ "${LANE}" == "lane3" ]]; then
  MANIFEST_PINS="$("${PY_BIN}" - "${WHEELS_MANIFEST}" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
for entry in data.get("wheels", []):
    if entry.get("git_commit"):
        print(f"{entry.get('git_repo', '')}\t{entry['git_commit']}\t{entry.get('package', '?')}")
PY
  )"
  while IFS=$'\t' read -r m_repo m_sha m_pkg; do
    [[ -z "${m_sha:-}" ]] && continue
    check_git_pin "${m_repo}" "${m_sha}" "${m_pkg}"
  done <<<"${MANIFEST_PINS}"
fi

# 4. uv version, then re-run the compile and compare with the committed lock
TMP_LOCK="$(mktemp)"
if [[ "${COMPILE_MOCK}" == "1" ]]; then
  MOCK_OUT="$(hook SDLAB_PREFLIGHT_MOCK_COMPILE_OUT)"
  cp "${MOCK_OUT:-${REPO_ROOT}/${LOCK_REL}}" "${TMP_LOCK}"
else
  PINNED_UV="$(grep -E '^PINNED_UV_VERSION=' "${LAUNCH_SH}" | head -n1 | cut -d'"' -f2)"
  [[ -n "${PINNED_UV}" ]] || refuse LOCK_INPUT_MISSING "PINNED_UV_VERSION not found in ${LAUNCH_SH}"
  UV_VER_LINE="$("${UV_BIN}" --version 2>&1 || true)"
  UV_VER="$(awk '{print $2}' <<<"${UV_VER_LINE}")"
  if [[ "${UV_VER}" != "${PINNED_UV}" ]]; then
    refuse UV_VERSION_MISMATCH "${UV_BIN} reports '${UV_VER_LINE}', the kits pin uv ${PINNED_UV}; install uv ${PINNED_UV} or point UV_BIN at it"
  fi

  COMPILE_LOG="$(mktemp)"
  CUSTOM_CMD="uv pip compile --generate-hashes --only-binary :all: --python-platform x86_64-manylinux_2_28 --python-version ${PY_VER} --extra-index-url https://download.pytorch.org/whl/cu130 --index-strategy unsafe-best-match ${IN_REL} -o ${LOCK_REL}"
  if ! (
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
      -o "${TMP_LOCK}" >"${COMPILE_LOG}" 2>&1
  ); then
    echo "REFUSED: LOCK_COMPILE_FAILED: uv pip compile failed for ${LANE} (python ${PY_VER}); last lines:" >&2
    tail -n 15 "${COMPILE_LOG}" >&2 || true
    exit 1
  fi
fi

NORM_COMMITTED="$(mktemp)"
NORM_COMPILED="$(mktemp)"
tr -d '\r' < "${LOCK_FILE}" > "${NORM_COMMITTED}"
tr -d '\r' < "${TMP_LOCK}" > "${NORM_COMPILED}"

if ! diff -u "${NORM_COMMITTED}" "${NORM_COMPILED}" >/dev/null 2>&1; then
  echo "REFUSED: LOCK_DRIFT: compiled output for ${LANE} differs from committed ${LOCK_FILE}" >&2
  diff -u "${NORM_COMMITTED}" "${NORM_COMPILED}" | head -n 40 >&2 || true
  exit 1
fi

PIN_COUNT="$(grep -c '^[a-zA-Z0-9_-]*==' "${NORM_COMMITTED}")"
echo "PREFLIGHT_OK lane=${LANE} python=${PY_VER} pins=${PIN_COUNT}"
