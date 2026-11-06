#!/usr/bin/env bash
# Regenerate a Colab kit lock and its exclude-newer timestamp file, together.
# Usage: bash scripts/colab/relock.sh <lane1|lane3|1|3> --exclude-newer <YYYY-MM-DDTHH:MM:SSZ|now>
#                                     [--locks-dir <dir>]
#
# Runs the same `uv pip compile` the pre-flight's drift check runs (scripts/colab/lock_common.sh),
# bounded by `--exclude-newer`, and writes scripts/colab/locks/<lane>.lock and
# scripts/colab/locks/<lane>.exclude-newer only after the compile succeeds. `now` takes the current
# UTC second. The bound is required: a re-lock is a deliberate change that moves it (a bump PR;
# docs/colab-locks.md). --locks-dir writes both files to another directory instead (the tests use it).
#
# Refusals are one `REFUSED: <CODE>: <detail>` line on stderr, exit 1: `LOCK_TIMESTAMP_MISSING`
# (no bound given), `LOCK_TIMESTAMP_MALFORMED`, `PREFLIGHT_TOOL_MISSING` (no uv),
# `LOCK_INPUT_MISSING`, `UV_VERSION_MISMATCH`, `LOCK_COMPILE_FAILED`. It makes no `colab` call.
# A lane-1 change also moves PINNED_LOCK_SHA in launch_lane1_stub.sh, and a lane-3 change
# PINNED_OVERRIDE_SHA in launch_lane3_stub.sh; this script prints the new sha256 and edits neither.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=scripts/colab/lock_common.sh
source "${SCRIPT_DIR}/lock_common.sh"

refuse() {
  local code="$1"
  shift
  echo "REFUSED: ${code}: $*" >&2
  exit 1
}

usage() {
  echo "Usage: $0 <lane1|lane3> --exclude-newer <YYYY-MM-DDTHH:MM:SSZ|now> [--locks-dir <dir>]" >&2
  exit 2
}

LANE_RAW="${1:-}"
[[ -n "${LANE_RAW}" ]] || usage
shift
EXCLUDE_NEWER=""
LOCKS_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --exclude-newer)
      [[ $# -ge 2 ]] || usage
      EXCLUDE_NEWER="$2"
      shift 2
      ;;
    --locks-dir)
      [[ $# -ge 2 ]] || usage
      LOCKS_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done
if ! lock_lane_config "${LANE_RAW}"; then
  echo "Unknown lane: ${LANE_RAW} (expected lane1 or lane3)" >&2
  exit 2
fi

[[ -n "${EXCLUDE_NEWER}" ]] || refuse LOCK_TIMESTAMP_MISSING "relock needs --exclude-newer <YYYY-MM-DDTHH:MM:SSZ|now>"
if [[ "${EXCLUDE_NEWER}" == "now" ]]; then
  EXCLUDE_NEWER="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi
lock_check_exclude_newer "${EXCLUDE_NEWER}" || refuse LOCK_TIMESTAMP_MALFORMED "--exclude-newer ${LOCK_TS_REASON}"

UV_BIN="${UV_BIN:-$(command -v uv || true)}"
[[ -n "${UV_BIN}" && -x "${UV_BIN}" ]] || refuse PREFLIGHT_TOOL_MISSING "uv not found (PATH or UV_BIN)"
IN_FILE="${REPO_ROOT}/${IN_REL}"
[[ -f "${IN_FILE}" ]] || refuse LOCK_INPUT_MISSING "${IN_FILE} not found"
lock_check_uv "${UV_BIN}"

OUT_DIR="${LOCKS_DIR:-${REPO_ROOT}/scripts/colab/locks}"
[[ -d "${OUT_DIR}" ]] || refuse LOCK_INPUT_MISSING "locks directory ${OUT_DIR} not found"
LOCK_OUT="${OUT_DIR}/${LANE}.lock"
TS_OUT="${OUT_DIR}/${LANE}.exclude-newer"

TMP_LOCK="$(mktemp "${OUT_DIR}/.${LANE}.lock.XXXXXX")"
TMP_TS="$(mktemp "${OUT_DIR}/.${LANE}.exclude-newer.XXXXXX")"
COMPILE_LOG="$(mktemp)"
trap 'rm -f "${TMP_LOCK}" "${TMP_TS}" "${COMPILE_LOG}"' EXIT

if ! lock_run_compile "${UV_BIN}" "${IN_FILE}" "${TMP_LOCK}" "${EXCLUDE_NEWER}" >"${COMPILE_LOG}" 2>&1; then
  echo "REFUSED: LOCK_COMPILE_FAILED: uv pip compile failed for ${LANE} (python ${PY_VER}, exclude-newer ${EXCLUDE_NEWER}); last lines:" >&2
  tail -n 15 "${COMPILE_LOG}" >&2 || true
  exit 1
fi

cat > "${TMP_TS}" <<EOF
# uv --exclude-newer bound for ${LANE}.lock: the resolver sees only files uploaded before this
# instant (RFC 3339, UTC, whole seconds). Written with the lock by scripts/colab/relock.sh; it
# moves only in a deliberate re-lock PR (docs/colab-locks.md).
${EXCLUDE_NEWER}
EOF

chmod 644 "${TMP_LOCK}" "${TMP_TS}"
mv -f "${TMP_LOCK}" "${LOCK_OUT}"
mv -f "${TMP_TS}" "${TS_OUT}"

LOCK_SHA="$(sha256sum "${LOCK_OUT}" | awk '{print $1}')"
PIN_COUNT="$(grep -c '^[a-zA-Z0-9_-]*==' "${LOCK_OUT}" || true)"
echo "RELOCK_OK lane=${LANE} exclude_newer=${EXCLUDE_NEWER} pins=${PIN_COUNT} lock_sha256=${LOCK_SHA}"
