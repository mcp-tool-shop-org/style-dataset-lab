"""Tests for scripts/colab/launch_lane3_stub.sh against a fake colab CLI (Part C)."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "colab" / "launch_lane3_stub.sh"


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
    count_file="${STATE_DIR}/usage_count.txt"
    c=0
    if [ -f "${count_file}" ]; then
      c="$(cat "${count_file}")"
    fi
    c=$((c + 1))
    echo "${c}" > "${count_file}"
    if [ "${FAKE_COLAB_MODE:-success}" = "cap_burn" ] && [ "${c}" -ge 2 ]; then
      echo '{"balance_ccu": 9.75, "rate_ccu_per_hour": 0.26}'
    else
      echo '{"balance_ccu": 9.85, "rate_ccu_per_hour": 0.26}'
    fi
    ;;
  sessions)
    echo "SESSION_LIST_AFTER_STOP" >> "${STATE_DIR}/sessions.log"
    echo "No active sessions."
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
    echo "Opened tunnel https://colab.research.google.com/tun?colab-runtime-proxy-token=secret_proxy_tok_lane3_999&port=8188"
    echo "OAuth access_token=ya29.secret_oauth_lane3_888"
    ;;
  upload)
    echo "UPLOAD_OK $*" >> "${STATE_DIR}/uploads.log"
    ;;
  exec)
    if [ "${FAKE_COLAB_MODE:-success}" = "fail" ]; then
      echo "Simulated remote failure with colab-runtime-proxy-token=secret_proxy_tok_lane3_999" >&2
      exit 42
    elif [ "${FAKE_COLAB_MODE:-success}" = "wall" ]; then
      echo "Simulated hung child ignoring inner timeout"
      for _ in $(seq 1 40); do
        sleep 0.2
      done
      exit 0
    elif [ "${FAKE_COLAB_MODE:-success}" = "dead_harness" ]; then
      echo "=== VITALS 2026-11-05T12:01:00Z ==="
      echo "CGROUP_MEM: oom_kill 0"
      echo "MEM: MemTotal: 13290000 kB"
      echo "PROC:"
      echo 'HARNESS: {"phase": "run", "step": 1}'
      echo "=== VITALS 2026-11-05T12:01:15Z ==="
      echo "CGROUP_MEM: oom_kill 0"
      echo "MEM: MemTotal: 13290000 kB"
      echo "PROC:"
      echo 'HARNESS: {"phase": "run", "step": 1}'
      for _ in $(seq 1 60); do
        sleep 0.2
      done
      exit 0
    elif [ "${FAKE_COLAB_MODE:-success}" = "stall" ]; then
      echo "=== VITALS 2026-11-05T12:00:00Z ==="
      echo "MEM: MemTotal: 13290000 kB"
      echo "PROC:"
      echo "101 python3 /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml"
      echo 'HARNESS: {"phase": "run", "step": 1}'
      for _ in $(seq 1 60); do
        sleep 0.2
      done
      exit 0
    elif [ "${FAKE_COLAB_MODE:-success}" = "cap_burn" ]; then
      echo "=== VITALS 2026-11-05T12:00:00Z ==="
      echo "MEM: MemTotal: 13290000 kB"
      echo "PROC:"
      echo "101 python3 /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml"
      echo 'HARNESS: {"phase": "run", "step": 1}'
      for _ in $(seq 1 60); do
        sleep 0.2
      done
      exit 0
    fi
    echo "=== VITALS 2026-11-05T12:00:00Z ==="
    echo "CGROUP_MEM_CURRENT: 536870912"
    echo "CGROUP_MEM_MAX: 12884901888"
    echo "MEM: MemTotal: 12582912 kB"
    echo "PROC:"
    echo "101 python3 /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml"
    echo 'HARNESS: {"phase": "run", "step": 1}'
    echo 'WINDOW_JSON {"system_python": "3.13.16", "python": "3.15.1", "python_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "uv": "uv 0.13.5", "ai_toolkit_commit": "73ebae1334d2c98089f1b90f8cb19257825f891a", "override_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "checkpoint_path": "/content/lane3_out/checkpoints/synth_lora.safetensors"}'
    echo "LANE3_STUB_OK python=3.15.1 sentencepiece=0.2.1 checkpoint_written=true"
    ;;
  download)
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
    env["EXPECTED_OVERRIDE_SHA"] = "0" * 64

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
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", "sdlab-l3-test-ok"],
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
    assert "CALL new --high-mem -s sdlab-l3-test-ok" in calls_log

    # 3. Trap stops its own session on success
    stops_log = (state_dir / "stops.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-test-ok" in stops_log

    # 4. Token scrubbed from every kept log in out_dir
    kept_logs = list(out_dir.rglob("*.log")) + list(out_dir.rglob("*.json"))
    assert kept_logs, "Expected logs and JSON artifacts in out_dir"
    for f in kept_logs:
        txt = f.read_text(encoding="utf-8")
        assert "secret_proxy_tok_lane3_999" not in txt, f"Unscrubbed proxy token in {f}"
        assert "ya29.secret_oauth_lane3_888" not in txt, f"Unscrubbed oauth token in {f}"

    # 5. window.json and outcome.draft.json written
    win_json = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win_json["session"] == "sdlab-l3-test-ok"
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
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_fail), "--session", "sdlab-l3-fail"],
        env=env_fail,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_fail.returncode != 0
    assert "STOP -s sdlab-l3-fail" in (state_dir_fail / "stops.log").read_text(encoding="utf-8")

    # Independent wall guard stops session even when child sleeps past wall
    _, state_dir_wall, env_wall = _make_fake_colab_env(tmp_path / "wall_case")
    env_wall["FAKE_COLAB_MODE"] = "wall"
    env_wall["WALL_S"] = "2"
    env_wall["GRACE_S"] = "1"
    out_wall = tmp_path / "out_wall"

    res_wall = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_wall), "--session", "sdlab-l3-wall"],
        env=env_wall,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_wall.returncode != 0
    assert "STOP -s sdlab-l3-wall" in (state_dir_wall / "stops.log").read_text(encoding="utf-8")


def test_trainer_kit_pins_filters_av_torchcodec_generates_synth_job_yaml_and_verifies_checkpoint(tmp_path: Path) -> None:
    kit_text = LAUNCHER.read_text(encoding="utf-8")
    for required_var in (
        "PINNED_UV_VERSION=",
        "PINNED_PYTHON_VERSION=",
        "PINNED_PYTORCH_INDEX_URL=",
        "PINNED_AI_TOOLKIT_REPO=",
        "PINNED_AI_TOOLKIT_COMMIT=",
        "PINNED_OVERRIDE_SHA=",
        "PINNED_LAUNCH_GUARDS_SHA=",
        "PINNED_COLAB_WINDOW_SHA=",
        "PINNED_SELF_SHA=",
    ):
        assert required_var in kit_text, f"Missing top-of-kit pin variable {required_var}"

    # Filters av and torchcodec before uv pip install --override with PyTorch cp315 index
    assert "grep -Ev '^(av|torchcodec)" in kit_text
    assert "https://download.pytorch.org/whl/cu130" in kit_text
    assert "git -C /content/ai-toolkit checkout" in kit_text
    # Generates synth_job.yaml for a 1-step CPU run and verifies .safetensors checkpoint exists
    assert "/content/lane3_out/synth_job.yaml" in kit_text
    assert "steps: 1" in kit_text
    assert "device: cpu" in kit_text
    assert "synth_lora.safetensors" in kit_text

    # Self-sha refusal when EXPECTED_LAUNCH_LANE3_STUB_SHA mismatches
    _, state_dir_self, env_self = _make_fake_colab_env(tmp_path / "self_sha_case")
    env_self["EXPECTED_LAUNCH_LANE3_STUB_SHA"] = "0" * 64
    out_self = tmp_path / "out_self_sha"
    res_self = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_self)],
        env=env_self,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_self.returncode != 0
    assert "INPUT_SHA_MISMATCH" in (res_self.stdout + res_self.stderr)
    assert not (state_dir_self / "calls.log").exists()


def test_live_guards_trip_dead_harness_stall_and_cap_during_exec_and_merge_window_json(tmp_path: Path) -> None:
    # 1. DEAD_HARNESS_TRIPPED during live colab exec kills EXEC_PID and stops session
    _, state_dh, env_dh = _make_fake_colab_env(tmp_path / "dh_case")
    env_dh["FAKE_COLAB_MODE"] = "dead_harness"
    env_dh["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dh = tmp_path / "out_dh"
    res_dh = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dh), "--session", "sdlab-l3-dh"],
        env=env_dh,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_dh.returncode != 0
    assert "DEAD_HARNESS_TRIPPED" in (out_dh / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-dh" in (state_dh / "stops.log").read_text(encoding="utf-8")

    # 2. STALL_GUARD_TRIPPED during live colab exec kills EXEC_PID and stops session
    _, state_st, env_st = _make_fake_colab_env(tmp_path / "stall_case")
    env_st["FAKE_COLAB_MODE"] = "stall"
    env_st["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_st["STALL_S"] = "1"
    out_st = tmp_path / "out_stall"
    res_st = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_st), "--session", "sdlab-l3-stall"],
        env=env_st,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_st.returncode != 0
    assert "STALL_GUARD_TRIPPED" in (out_st / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-stall" in (state_st / "stops.log").read_text(encoding="utf-8")

    # 3. CAP_GUARD_TRIPPED during live colab exec kills EXEC_PID and stops session
    _, state_cap, env_cap = _make_fake_colab_env(tmp_path / "cap_case")
    env_cap["FAKE_COLAB_MODE"] = "cap_burn"
    env_cap["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_cap = tmp_path / "out_cap"
    res_cap = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_cap), "--session", "sdlab-l3-cap", "--cap", "0.05", "--margin", "0.01"],
        env=env_cap,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_cap.returncode != 0
    assert "CAP_GUARD_TRIPPED" in (out_cap / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-cap" in (state_cap / "stops.log").read_text(encoding="utf-8")

    # 4. Normal success merges VM facts (including checkpoint_path), balances, rate_measured, downloaded_files sha, and logs sessions + closing usage
    _, state_ok, env_ok = _make_fake_colab_env(tmp_path / "merge_case")
    env_ok["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_ok = tmp_path / "out_merge"
    res_ok = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_ok), "--session", "sdlab-l3-merge"],
        env=env_ok,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_ok.returncode == 0
    win = json.loads((out_ok / "window.json").read_text(encoding="utf-8"))
    assert win["system_python"] == "3.13.16"
    assert win["python"] == "3.15.1"
    assert win["checkpoint_path"] == "/content/lane3_out/checkpoints/synth_lora.safetensors"
    assert win["start_balance"] == 9.85
    assert win["end_balance"] == 9.85
    assert win["rate_measured"] == 0.26
    assert "lane3_stub_bundle.tar.gz" in win["downloaded_files"]
    assert (state_ok / "sessions.log").exists()
    remote_sh = (out_ok / "remote_lane3_stub.sh").read_text(encoding="utf-8")
    assert "--scrub-file" in remote_sh

