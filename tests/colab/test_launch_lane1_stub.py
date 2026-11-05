"""Tests for scripts/colab/launch_lane1_stub.sh against a fake colab CLI (Part C)."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"


def _find_bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _to_posix(p: Path) -> str:
    s = p.resolve().as_posix()
    if len(s) >= 2 and s[1] == ":":
        return f"/{s[0].lower()}{s[2:]}"
    return s


def _make_fake_colab_env(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    bin_dir = tmp_path / "fake_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / "colab_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_file = tmp_path / "colab-window-open.lock"

    fake_colab = bin_dir / "colab"
    fake_colab.write_text(
        """#!/usr/bin/env bash
#SDLAB_FAKE_COLAB_CLI=1
set -euo pipefail

STATE_DIR="${FAKE_COLAB_STATE_DIR:?missing FAKE_COLAB_STATE_DIR}"
LOCK_FILE="${COLAB_OPEN_LOCK:-/tmp/colab-window-open.lock}"
echo "CALL $*" >> "${STATE_DIR}/calls.log"

sub="${1:-}"
shift || true

case "${sub}" in
  usage)
    echo '{"balance_ccu": 9.85, "rate_ccu_per_hour": 0.08}'
    ;;
  new)
    if command -v flock >/dev/null 2>&1; then
      if flock -n "${LOCK_FILE}" -c "true" 2>/dev/null; then
        echo "LOCK_HELD=0" >> "${STATE_DIR}/lock.log"
      else
        echo "LOCK_HELD=1" >> "${STATE_DIR}/lock.log"
      fi
    else
      if [ -d "${LOCK_FILE}.lockdir" ] || [ -f "${LOCK_FILE}.held" ]; then
        echo "LOCK_HELD=1" >> "${STATE_DIR}/lock.log"
      else
        echo "LOCK_HELD=0" >> "${STATE_DIR}/lock.log"
      fi
    fi
    echo "Opened tunnel https://colab.research.google.com/tun?colab-runtime-proxy-token=secret_proxy_tok_lane1_999&port=8188"
    echo "OAuth access_token=ya29.secret_oauth_lane1_888"
    ;;
  upload)
    echo "UPLOAD_OK $*" >> "${STATE_DIR}/uploads.log"
    ;;
  exec)
    if [ "${FAKE_COLAB_MODE:-success}" = "fail" ]; then
      echo "Simulated remote failure with colab-runtime-proxy-token=secret_proxy_tok_lane1_999" >&2
      exit 42
    elif [ "${FAKE_COLAB_MODE:-success}" = "wall" ]; then
      echo "Simulated hung child ignoring inner timeout"
      for _ in $(seq 1 40); do
        sleep 0.2
      done
      exit 0
    fi
    echo "=== VITALS 2026-11-05T12:00:00Z ==="
    echo "PROC:"
    echo "101 python3 /content/ComfyUI/main.py --cpu --listen 127.0.0.1"
    echo 'HARNESS: {"phase": "run", "step": 1}'
    echo "LANE1_STUB_OK python=3.15.1 comfy_bind=127.0.0.1:8188 resume_hash_match=true"
    ;;
  download)
    # Last arg is local destination path
    dest="${@: -1}"
    mkdir -p "$(dirname "${dest}")"
    printf 'FAKE_TAR_BYTES' > "${dest}"
    ;;
  stop)
    echo "STOP $*" >> "${STATE_DIR}/stops.log"
    ;;
  *)
    echo "UNKNOWN_SUBCOMMAND ${sub}" >&2
    exit 2
    ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_colab.chmod(fake_colab.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{_to_posix(bin_dir)}:{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_COLAB_STATE_DIR"] = _to_posix(state_dir)
    env["COLAB_OPEN_LOCK"] = _to_posix(lock_file)
    env["SDLAB_TEST_FAKE_COLAB"] = "1"
    return bin_dir, state_dir, env


def test_real_colab_cli_guard_refuses_when_not_fake(tmp_path: Path) -> None:
    assert LAUNCHER.exists(), f"Missing {LAUNCHER}"
    unmarked_bin = tmp_path / "unmarked_bin"
    unmarked_bin.mkdir()
    unmarked_colab = unmarked_bin / "colab"
    unmarked_colab.write_text("#!/usr/bin/env bash\necho real\n", encoding="utf-8", newline="\n")
    unmarked_colab.chmod(unmarked_colab.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{_to_posix(unmarked_bin)}:{unmarked_bin}{os.pathsep}{env.get('PATH', '')}"
    env["SDLAB_TEST_FAKE_COLAB"] = "1"
    out_dir = tmp_path / "out_guard"

    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode != 0
    assert "REAL_COLAB_FORBIDDEN" in (res.stdout + res.stderr)


def test_sha_refusal_before_opening_session(tmp_path: Path) -> None:
    assert LAUNCHER.exists(), f"Missing {LAUNCHER}"
    _, state_dir, env = _make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_sha"
    env["EXPECTED_LANE1_RENDER_SHA"] = "0" * 64

    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode != 0
    assert "REFUSED" in (res.stdout + res.stderr) or "INPUT_SHA_MISMATCH" in (res.stdout + res.stderr)
    assert not (state_dir / "calls.log").exists(), "colab must never be called when input sha mismatches"


def test_success_holds_lock_scrubs_tokens_and_stops_session_in_trap(tmp_path: Path) -> None:
    assert LAUNCHER.exists(), f"Missing {LAUNCHER}"
    _, state_dir, env = _make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_ok"

    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-test-ok"],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res.returncode == 0, f"Launcher failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    # 1. Lock held during `colab new`
    lock_log = (state_dir / "lock.log").read_text(encoding="utf-8")
    assert "LOCK_HELD=1" in lock_log

    # 2. Default CPU `--high-mem` passed to `colab new`
    calls_log = (state_dir / "calls.log").read_text(encoding="utf-8")
    assert "CALL new --high-mem -s sdlab-l1-test-ok" in calls_log

    # 3. Trap stops its own session on success
    stops_log = (state_dir / "stops.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l1-test-ok" in stops_log

    # 4. Token scrubbed from every kept log in out_dir
    kept_logs = list(out_dir.rglob("*.log")) + list(out_dir.rglob("*.json"))
    assert kept_logs, "Expected logs and JSON artifacts in out_dir"
    for f in kept_logs:
        txt = f.read_text(encoding="utf-8")
        assert "secret_proxy_tok_lane1_999" not in txt, f"Unscrubbed proxy token in {f}"
        assert "ya29.secret_oauth_lane1_888" not in txt, f"Unscrubbed oauth token in {f}"

    # 5. window.json and outcome.draft.json written
    win_json = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win_json["session"] == "sdlab-l1-test-ok"
    assert win_json["card"] == "CPU-high-mem"
    assert "input_shas" in win_json

    outcome = json.loads((out_dir / "outcome.draft.json").read_text(encoding="utf-8"))
    assert outcome["status"] == "ok"


def test_trap_stops_session_on_command_failure_and_wall(tmp_path: Path) -> None:
    assert LAUNCHER.exists(), f"Missing {LAUNCHER}"
    _, state_dir_fail, env_fail = _make_fake_colab_env(tmp_path / "fail_case")
    env_fail["FAKE_COLAB_MODE"] = "fail"
    out_fail = tmp_path / "out_fail"

    res_fail = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_fail), "--session", "sdlab-l1-fail"],
        env=env_fail,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_fail.returncode != 0
    assert "STOP -s sdlab-l1-fail" in (state_dir_fail / "stops.log").read_text(encoding="utf-8")

    # Independent wall guard stops session even when child sleeps past wall
    _, state_dir_wall, env_wall = _make_fake_colab_env(tmp_path / "wall_case")
    env_wall["FAKE_COLAB_MODE"] = "wall"
    env_wall["WALL_S"] = "2"
    env_wall["GRACE_S"] = "1"
    out_wall = tmp_path / "out_wall"

    res_wall = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_wall), "--session", "sdlab-l1-wall"],
        env=env_wall,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_wall.returncode != 0
    assert "STOP -s sdlab-l1-wall" in (state_dir_wall / "stops.log").read_text(encoding="utf-8")
