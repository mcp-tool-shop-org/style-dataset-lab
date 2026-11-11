"""Tests for scripts/colab/launch_lane1_stub.sh against the contract-checked fake colab CLI."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
RUNNER_PY = REPO_ROOT / "scripts" / "colab" / "remote_runner.py"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "colab"))

import fake_colab as fc  # noqa: E402
import remote_runner as rr  # noqa: E402


def _find_bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _to_posix(p: Path) -> str:
    return fc._to_posix(p)


def _make_fake_colab_env(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    return fc.make_fake_colab_env(tmp_path)


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
    out_wall = tmp_path / "out_wall"

    res_wall = subprocess.run(
        [
            _find_bash(),
            _to_posix(LAUNCHER),
            "--out-dir",
            _to_posix(out_wall),
            "--session",
            "sdlab-l1-wall",
            "--wall-s",
            "2",
            "--grace-s",
            "1",
        ],
        env=env_wall,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_wall.returncode != 0
    assert "STOP -s sdlab-l1-wall" in (state_dir_wall / "stops.log").read_text(encoding="utf-8")


def test_kit_pins_self_sha_comfyui_commit_comfy_headless_and_pytorch_index(tmp_path: Path) -> None:
    kit_text = LAUNCHER.read_text(encoding="utf-8")
    for required_var in (
        "PINNED_UV_VERSION=",
        "PINNED_UV_WHEEL_SHA256=",
        "PINNED_INSTALL_CLASSIFIER_SHA=",
        "PINNED_PYTHON_VERSION=",
        "PINNED_PYTORCH_INDEX_URL=",
        "PINNED_COMFYUI_REPO=",
        "PINNED_COMFYUI_COMMIT=",
        "PINNED_COMFY_HEADLESS_SPEC=",
        "PINNED_LANE1_RENDER_SHA=",
        "PINNED_LAUNCH_GUARDS_SHA=",
        "PINNED_REMOTE_RUNNER_SHA=",
        "PINNED_COLAB_WINDOW_SHA=",
        "PINNED_SELF_SHA=",
    ):
        assert required_var in kit_text, f"Missing top-of-kit pin variable {required_var}"

    assert "comfy-headless==" in kit_text
    assert "https://download.pytorch.org/whl/cu130" in kit_text
    assert "git -C /content/ComfyUI checkout" in kit_text

    # Self-sha refusal when EXPECTED_LAUNCH_LANE1_STUB_SHA mismatches
    _, state_dir_self, env_self = _make_fake_colab_env(tmp_path / "self_sha_case")
    env_self["EXPECTED_LAUNCH_LANE1_STUB_SHA"] = "0" * 64
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
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dh), "--session", "sdlab-l1-dh"],
        env=env_dh,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_dh.returncode != 0
    assert "DEAD_HARNESS_TRIPPED" in (out_dh / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l1-dh" in (state_dh / "stops.log").read_text(encoding="utf-8")

    # 2. STALL_GUARD_TRIPPED during live colab exec kills EXEC_PID and stops session
    _, state_st, env_st = _make_fake_colab_env(tmp_path / "stall_case")
    env_st["FAKE_COLAB_MODE"] = "stall"
    env_st["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_st["STALL_S"] = "1"
    out_st = tmp_path / "out_stall"
    res_st = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_st), "--session", "sdlab-l1-stall"],
        env=env_st,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_st.returncode != 0
    assert "STALL_GUARD_TRIPPED" in (out_st / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l1-stall" in (state_st / "stops.log").read_text(encoding="utf-8")

    # 3. CAP_GUARD_TRIPPED during live colab exec kills EXEC_PID and stops session (in text format)
    _, state_cap, env_cap = _make_fake_colab_env(tmp_path / "cap_case")
    env_cap["FAKE_COLAB_MODE"] = "cap_burn"
    env_cap["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_cap = tmp_path / "out_cap"
    res_cap = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_cap), "--session", "sdlab-l1-cap", "--cap", "0.10", "--margin", "0.01"],
        env=env_cap,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_cap.returncode != 0
    assert "CAP_GUARD_TRIPPED" in (out_cap / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l1-cap" in (state_cap / "stops.log").read_text(encoding="utf-8")
    usage_log_cap = (out_cap / "usage.log").read_text(encoding="utf-8")
    assert "Current balance: 9.85 compute units" in usage_log_cap
    assert "Current balance: 9.75 compute units" in usage_log_cap
    assert "balance_ccu" not in usage_log_cap

    # 4. Normal success merges VM facts, balances, rate_measured, downloaded_files sha, and logs sessions + closing usage
    _, state_ok, env_ok = _make_fake_colab_env(tmp_path / "merge_case")
    env_ok["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_ok = tmp_path / "out_merge"
    res_ok = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_ok), "--session", "sdlab-l1-merge"],
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
    assert win["python"] == "3.14.9"
    assert win["listening_sockets"] == ["127.0.0.1:8188"]
    assert win["start_balance"] == 9.85
    assert win["end_balance"] == 9.85
    assert win["rate_measured"] == 0.26
    assert win["rate_measured_pre_open"] == 0.26
    assert win["rate_measured_post_open"] == 0.26
    assert win["rate_source"] == "post_open_measured"
    assert win["usage_parse_error"] is None
    assert "lane1_stub_bundle.tar.gz" in win["downloaded_files"]
    assert (state_ok / "sessions.log").exists()
    remote_sh = (out_ok / "remote_lane1_stub.sh").read_text(encoding="utf-8")
    assert "--scrub-file" in remote_sh


def test_fake_colab_refuses_positional_exec_command(tmp_path: Path) -> None:
    _, _, env = _make_fake_colab_env(tmp_path)
    os.environ["FAKE_COLAB_STATE_DIR"] = env["FAKE_COLAB_STATE_DIR"]
    rc = fc.main(["exec", "-s", "X", "bash /content/remote_lane1_stub.sh"])
    assert rc != 0


def test_fake_colab_refuses_unknown_flag_on_each_subcommand(tmp_path: Path) -> None:
    _, _, env = _make_fake_colab_env(tmp_path)
    os.environ["FAKE_COLAB_STATE_DIR"] = env["FAKE_COLAB_STATE_DIR"]
    for subcmd in ("sessions", "new", "upload", "exec", "download", "stop", "usage"):
        rc = fc.main([subcmd, "--not-a-real-colab-flag"])
        assert rc != 0, f"Expected fake_colab to refuse unknown flag on {subcmd}"


def test_lane1_exec_call_passes_contract_py_file_and_timeout_gt_wall(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_contract"
    res = subprocess.run(
        [
            _find_bash(),
            _to_posix(LAUNCHER),
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-contract",
            "--wall-s",
            "900",
            "--grace-s",
            "60",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res.returncode == 0, f"STDERR:\n{res.stderr}"
    calls = [
        json.loads(line)
        for line in (state_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    exec_calls = [c for c in calls if c["subcmd"] == "exec"]
    assert len(exec_calls) == 1
    ec = exec_calls[0]
    assert ec["positionals"] == []
    f_vals = ec["parsed_opts"].get("-f") or ec["parsed_opts"].get("--file")
    assert f_vals and f_vals[-1].endswith(".py")
    timeout_val = float(ec["parsed_opts"]["--timeout"][-1])
    assert timeout_val > 900.0
    assert timeout_val == 1020.0
    env_kv = ec["parsed_opts"].get("--env", [])
    assert any(kv.endswith("/content/remote_lane1_stub.sh") and kv.startswith("SDLAB_REMOTE_SCRIPT=") for kv in env_kv)
    assert any(kv.startswith("PINNED_COMFYUI_COMMIT=") for kv in env_kv)


def test_remote_runner_py_streams_output_and_prints_sdlab_remote_rc(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, env = _make_fake_colab_env(tmp_path)
    script = tmp_path / "sample_remote.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'LINE_ONE_FROM_SH'\n"
        "echo 'LINE_TWO_STDERR' >&2\n"
        "exit 7\n",
        encoding="utf-8",
        newline="\n",
    )
    rc = rr.run_remote_script(_to_posix(script), env=env)
    captured = capsys.readouterr()
    assert rc == 7
    assert "LINE_ONE_FROM_SH" in captured.out
    assert "LINE_TWO_STDERR" in captured.out
    assert "SDLAB_REMOTE_RC=7" in captured.out.splitlines()[-1]

    # Missing SDLAB_REMOTE_SCRIPT returns 2 and prints SDLAB_REMOTE_RC=2
    rc_missing = rr.run_remote_script("", env={})
    cap_missing = capsys.readouterr()
    assert rc_missing == 2
    assert "SDLAB_REMOTE_RC=2" in cap_missing.out

    # Direct CLI invocation of remote_runner.py covers __main__ entrypoint
    cli_env = dict(env)
    cli_env["SDLAB_REMOTE_SCRIPT"] = _to_posix(script)
    cli_res = subprocess.run(
        [sys.executable, str(RUNNER_PY)],
        env=cli_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli_res.returncode == 0
    assert "SDLAB_REMOTE_RC=7" in cli_res.stdout


def test_usage_text_parsed_into_live_balance_and_rate_in_window_json(tmp_path: Path) -> None:
    _, _, env = _make_fake_colab_env(tmp_path)
    env["FAKE_COLAB_USAGE_TEXT"] = (
        "Current balance: 14.32 compute units\n"
        "Usage rate: 0.42/hr\n"
        "Active assignments: 2"
    )
    out_dir = tmp_path / "out_usage_ok"
    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-usage"],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res.returncode == 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["start_balance"] == 14.32
    assert win["end_balance"] == 14.32
    assert win["rate_measured"] == 0.42
    assert win["rate_measured_pre_open"] == 0.42
    assert win["rate_measured_post_open"] == 0.42
    assert win["rate_used_for_cap_and_projection"] == 0.42
    assert win["rate_for_projection"] == 0.42
    assert win["rate_source"] == "post_open_measured"
    assert win["usage_parse_error"] is None


def test_unparseable_usage_refuses_before_new_and_stops_midrun_with_no_10_0(tmp_path: Path) -> None:
    # 1. Refuses to START (before `colab new`, so no session is opened) when first usage read fails to parse
    _, state_start, env_start = _make_fake_colab_env(tmp_path / "usage_start_case")
    env_start["FAKE_COLAB_MODE"] = "usage_fail_start"
    out_start = tmp_path / "out_usage_start"
    res_start = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_start), "--session", "sdlab-l1-ustart"],
        env=env_start,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_start.returncode != 0
    guards_start = (out_start / "guards.log").read_text(encoding="utf-8")
    assert "COLAB_USAGE_PARSE_FAILED" in guards_start
    calls_start = (state_start / "calls.log").read_text(encoding="utf-8")
    assert "CALL new" not in calls_start, "colab new must not be called when initial usage read fails"
    assert not (state_start / "stops.log").exists()

    win_start_raw = (out_start / "window.json").read_text(encoding="utf-8")
    win_start = json.loads(win_start_raw)
    assert win_start["start_balance"] is None
    assert win_start["end_balance"] is None
    assert "COLAB_USAGE_PARSE_FAILED" in (win_start["usage_parse_error"] or "")
    assert "10.0" not in win_start_raw

    # 2. Stops mid-run on a later failed usage read and closes the session
    _, state_mid, env_mid = _make_fake_colab_env(tmp_path / "usage_mid_case")
    env_mid["FAKE_COLAB_MODE"] = "usage_fail_midrun"
    env_mid["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_mid = tmp_path / "out_usage_mid"
    res_mid = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_mid), "--session", "sdlab-l1-umid"],
        env=env_mid,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_mid.returncode != 0
    guards_mid = (out_mid / "guards.log").read_text(encoding="utf-8")
    assert "COLAB_USAGE_PARSE_FAILED" in guards_mid
    assert "STOP -s sdlab-l1-umid" in (state_mid / "stops.log").read_text(encoding="utf-8")
    win_mid_raw = (out_mid / "window.json").read_text(encoding="utf-8")
    win_mid = json.loads(win_mid_raw)
    assert win_mid["start_balance"] == 9.85
    assert win_mid["end_balance"] is None
    assert "COLAB_USAGE_PARSE_FAILED" in (win_mid["usage_parse_error"] or "")
    assert "10.0" not in win_mid_raw


def test_preseeded_start_balance_in_out_dir_refuses_with_out_dir_not_empty_before_new(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path / "nonempty_case")
    env["FAKE_COLAB_MODE"] = "cap_burn"
    out_dir = tmp_path / "out_nonempty"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "start_balance.txt").write_text("9.75\n", encoding="utf-8")

    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-nonempty"],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode != 0
    assert "OUT_DIR_NOT_EMPTY" in (res.stdout + res.stderr)
    assert not (state_dir / "calls.log").exists(), "colab must never be called when --out-dir is not empty"


def test_midrun_poll_helper_crash_or_empty_stops_window_rc_91_and_trap_stops_session(tmp_path: Path) -> None:
    for fault in ("crash", "empty"):
        _, state_dir, env = _make_fake_colab_env(tmp_path / f"helper_{fault}")
        env["FAKE_COLAB_MODE"] = "stall"
        env["GUARD_POLL_INTERVAL_S"] = "0.2"
        env["SDLAB_FAULT_POLL_HELPER_MIDRUN"] = fault
        out_dir = tmp_path / f"out_helper_{fault}"
        sid = f"sdlab-l1-h{fault}"
        res = subprocess.run(
            [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", sid],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert res.returncode == 91, f"Expected rc 91 for {fault}, got {res.returncode}:\n{res.stderr}"
        assert "COLAB_USAGE_PARSE_FAILED" in (out_dir / "guards.log").read_text(encoding="utf-8")
        assert f"STOP -s {sid}" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_negative_balance_refuses_at_start_and_stops_midrun(tmp_path: Path) -> None:
    _, state_start, env_start = _make_fake_colab_env(tmp_path / "neg_start")
    env_start["FAKE_COLAB_MODE"] = "negative_balance_start"
    out_start = tmp_path / "out_neg_start"
    res_start = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_start), "--session", "sdlab-l1-negstart"],
        env=env_start,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_start.returncode != 0
    assert "COLAB_USAGE_PARSE_FAILED" in (out_start / "guards.log").read_text(encoding="utf-8")
    assert "CALL new" not in (state_start / "calls.log").read_text(encoding="utf-8")

    _, state_mid, env_mid = _make_fake_colab_env(tmp_path / "neg_mid")
    env_mid["FAKE_COLAB_MODE"] = "negative_balance_midrun"
    env_mid["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_mid = tmp_path / "out_neg_mid"
    res_mid = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_mid), "--session", "sdlab-l1-negmid"],
        env=env_mid,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_mid.returncode == 91
    assert "COLAB_USAGE_PARSE_FAILED" in (out_mid / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l1-negmid" in (state_mid / "stops.log").read_text(encoding="utf-8")


def test_setup_phase_with_no_workers_and_steady_output_succeeds_then_switches_to_run(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path / "setup_ok")
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "8"
    env["FAKE_COLAB_SETUP_SCALE"] = "0.2"
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    env["SETUP_STALL_S"] = "1"
    out_dir = tmp_path / "out_setup_ok"
    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-setup-ok"],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 0, f"STDERR:\n{res.stderr}"
    vitals_txt = (out_dir / "vitals.log").read_text(encoding="utf-8")
    assert '"phase": "setup"' in vitals_txt
    assert '"phase": "run"' in vitals_txt
    setup_bytes_vals = [
        int(line.split(":", 1)[1].strip())
        for line in vitals_txt.splitlines()
        if line.startswith("SETUP_BYTES:")
    ]
    assert len(setup_bytes_vals) >= 4
    assert setup_bytes_vals[-1] > setup_bytes_vals[0]
    guards_txt = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "DEAD_HARNESS_TRIPPED" not in guards_txt
    assert "SETUP_STALL_TRIPPED" not in guards_txt
    assert "STOP -s sdlab-l1-setup-ok" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_silent_setup_trips_setup_stall_tripped_and_trap_stops_session(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path / "setup_stall")
    env["FAKE_COLAB_MODE"] = "setup_stall"
    env["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.2"
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    env["SETUP_STALL_S"] = "1"
    out_dir = tmp_path / "out_setup_stall"
    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-setup-stall"],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 93
    vitals_txt = (out_dir / "vitals.log").read_text(encoding="utf-8")
    assert vitals_txt.count("=== VITALS ") >= 3, "Vitals blocks must continue arriving during silent setup"
    setup_bytes_vals = [
        int(line.split(":", 1)[1].strip())
        for line in vitals_txt.splitlines()
        if line.startswith("SETUP_BYTES:")
    ]
    assert len(setup_bytes_vals) >= 3
    assert len(set(setup_bytes_vals)) == 1, "SETUP_BYTES must stay constant while vitals blocks continue"
    guards_txt = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "SETUP_STALL_TRIPPED" in guards_txt
    assert "DEAD_HARNESS_TRIPPED" not in guards_txt
    assert "STOP -s sdlab-l1-setup-stall" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_pre_open_zero_rate_does_not_lower_configured_and_post_open_rate_is_used(tmp_path: Path) -> None:
    # 1. Pre-open 0.00/hr with post-open 0.38/hr uses post-open 0.38/hr for cap & projection
    _, _, env_post = _make_fake_colab_env(tmp_path / "rate_post")
    env_post["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env_post["FAKE_COLAB_POST_OPEN_RATE_STR"] = "0.38/hr"
    env_post["RATE_CCU_PER_HOUR"] = "0.26"
    env_post["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_post = tmp_path / "out_rate_post"
    res_post = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_post), "--session", "sdlab-l1-rpost"],
        env=env_post,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_post.returncode == 0, f"STDERR:\n{res_post.stderr}"
    win_post = json.loads((out_post / "window.json").read_text(encoding="utf-8"))
    assert win_post["rate_measured_pre_open"] == 0.0
    assert win_post["rate_measured_post_open"] == 0.38
    assert win_post["rate_used_for_cap_and_projection"] == 0.38
    assert win_post["rate_source"] == "post_open_measured"

    # 2. When no post-open rate line is present, pre-open 0.00/hr uses max(0.0, configured=0.26) = 0.26
    _, _, env_pre_only = _make_fake_colab_env(tmp_path / "rate_pre_only")
    env_pre_only["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env_pre_only["FAKE_COLAB_POST_OPEN_RATE_STR"] = "OMIT"
    env_pre_only["RATE_CCU_PER_HOUR"] = "0.26"
    out_pre_only = tmp_path / "out_rate_pre_only"
    res_pre_only = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_pre_only), "--session", "sdlab-l1-rpre"],
        env=env_pre_only,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_pre_only.returncode == 0
    win_pre_only = json.loads((out_pre_only / "window.json").read_text(encoding="utf-8"))
    assert win_pre_only["rate_measured_pre_open"] == 0.0
    assert win_pre_only["rate_measured_post_open"] is None
    assert win_pre_only["rate_used_for_cap_and_projection"] == 0.26
    assert win_pre_only["rate_source"] == "max_of_pre_open_and_configured"

    # 3. When neither pre-open nor post-open has a rate line, rate_source is "configured"
    _, _, env_cfg = _make_fake_colab_env(tmp_path / "rate_cfg")
    env_cfg["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "OMIT"
    env_cfg["FAKE_COLAB_POST_OPEN_RATE_STR"] = "OMIT"
    env_cfg["RATE_CCU_PER_HOUR"] = "0.31"
    out_cfg = tmp_path / "out_rate_cfg"
    res_cfg = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_cfg), "--session", "sdlab-l1-rcfg"],
        env=env_cfg,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_cfg.returncode == 0
    win_cfg = json.loads((out_cfg / "window.json").read_text(encoding="utf-8"))
    assert win_cfg["rate_measured_pre_open"] is None
    assert win_cfg["rate_measured_post_open"] is None
    assert win_cfg["rate_used_for_cap_and_projection"] == 0.31
    assert win_cfg["rate_source"] == "configured"

    # 4. High post-open rate trips time-based cap guard even when balance has not dropped yet
    _, state_cap_rate, env_cap_rate = _make_fake_colab_env(tmp_path / "rate_cap_trip")
    env_cap_rate["FAKE_COLAB_MODE"] = "stall"
    env_cap_rate["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env_cap_rate["FAKE_COLAB_POST_OPEN_RATE_STR"] = "360.00/hr"
    env_cap_rate["GUARD_POLL_INTERVAL_S"] = "1"
    out_cap_rate = tmp_path / "out_rate_cap_trip"
    res_cap_rate = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_cap_rate), "--session", "sdlab-l1-rcap", "--cap", "0.05", "--margin", "0.01"],
        env=env_cap_rate,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_cap_rate.returncode == 91
    assert "CAP_GUARD_TRIPPED" in (out_cap_rate / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l1-rcap" in (state_cap_rate / "stops.log").read_text(encoding="utf-8")

    # 5. Post-open 0.00/hr rate is NOT used as the cap rate: uses configured_pending_post_open_rate, then updates when positive
    _, _, env_post_zero = _make_fake_colab_env(tmp_path / "rate_post_zero")
    env_post_zero["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env_post_zero["FAKE_COLAB_POST_OPEN_RATE_STR"] = "0.00/hr"
    env_post_zero["RATE_CCU_PER_HOUR"] = "0.26"
    env_post_zero["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_post_zero = tmp_path / "out_rate_post_zero"
    res_post_zero = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_post_zero), "--session", "sdlab-l1-rpzero"],
        env=env_post_zero,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_post_zero.returncode == 0
    win_post_zero = json.loads((out_post_zero / "window.json").read_text(encoding="utf-8"))
    assert win_post_zero["rate_measured_pre_open"] == 0.0
    assert win_post_zero["rate_measured_post_open"] == 0.0
    assert win_post_zero["rate_used_for_cap_and_projection"] == 0.26
    assert win_post_zero["rate_for_projection"] == 0.26
    assert win_post_zero["rate_source"] == "configured_pending_post_open_rate"

    # 6. First post-open read is 0.00/hr, later post-open read is positive (0.41/hr) -> window.json records 0.41 and post_open_measured
    _, _, env_seq = _make_fake_colab_env(tmp_path / "rate_post_seq")
    env_seq["FAKE_COLAB_MODE"] = "setup_phase"
    env_seq["FAKE_COLAB_SETUP_DURATION_S"] = "4"
    env_seq["FAKE_COLAB_SETUP_SCALE"] = "0.1"
    env_seq["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env_seq["FAKE_COLAB_POST_OPEN_RATE_SEQ"] = "0.00/hr,0.41/hr"
    env_seq["RATE_CCU_PER_HOUR"] = "0.26"
    env_seq["GUARD_POLL_INTERVAL_S"] = "0.15"
    out_seq = tmp_path / "out_rate_post_seq"
    res_seq = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_seq), "--session", "sdlab-l1-rpseq"],
        env=env_seq,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_seq.returncode == 0
    win_seq = json.loads((out_seq / "window.json").read_text(encoding="utf-8"))
    assert win_seq["rate_measured_pre_open"] == 0.0
    assert win_seq["rate_measured_post_open"] == 0.41
    assert win_seq["rate_used_for_cap_and_projection"] == 0.41
    assert win_seq["rate_source"] == "post_open_measured"


def test_lane1_uv_system_python_env_explicit_venv_python_and_gates(tmp_path: Path) -> None:
    # 1. With UV_SYSTEM_PYTHON=1 set, the kit unsets UV_SYSTEM_PYTHON, sets UV_PYTHON_INSTALL_DIR under /content,
    # names /content/venv-lane1/bin/python on every uv pip install and python invocation, and the window passes.
    _, state_ok, env_ok = _make_fake_colab_env(tmp_path / "uv_sys_ok")
    env_ok["UV_SYSTEM_PYTHON"] = "1"
    env_ok["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_ok = tmp_path / "out_uv_sys_ok"
    res_ok = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_ok), "--session", "sdlab-l1-uvsys-ok"],
        env=env_ok,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_ok.returncode == 0, f"STDERR:\n{res_ok.stderr}"
    remote_sh = (out_ok / "remote_lane1_stub.sh").read_text(encoding="utf-8")
    assert "unset UV_SYSTEM_PYTHON" in remote_sh
    assert 'export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_314/install"' in remote_sh
    assert "source /content/venv-lane1/bin/activate" not in remote_sh
    assert "uv venv --python \"${PINNED_PYTHON_VERSION}\" /content/venv-lane1" in remote_sh
    assert "--seed" not in remote_sh
    assert (
        "/content/venv-lane1/bin/python -c 'import sys; assert sys.version.startswith(\"3.14.9\"), sys.version; "
        "assert sys.prefix.startswith(\"/content/venv-lane\"), sys.prefix'"
    ) in remote_sh
    uv_pip_lines = [
        line.strip()
        for line in remote_sh.splitlines()
        if line.strip().startswith("uv pip install")
    ]
    assert len(uv_pip_lines) == 1
    assert all("--python /content/venv-lane1/bin/python" in line for line in uv_pip_lines)
    assert all("--require-hashes" in line and "--only-binary :all:" in line for line in uv_pip_lines)
    assert "/content/venv-lane1/bin/python /content/ComfyUI/main.py" in remote_sh
    assert "/content/venv-lane1/bin/python /content/lane1_render.py" in remote_sh
    assert "/content/venv-lane1/bin/python /content/launch_guards.py" in remote_sh
    vitals_ok = (out_ok / "vitals.log").read_text(encoding="utf-8")
    assert "VENV_IMPORT comfy_headless /content/venv-lane1/" in vitals_ok
    assert "STOP -s sdlab-l1-uvsys-ok" in (state_ok / "stops.log").read_text(encoding="utf-8")


def test_lane1_venv_python_version_mismatch_refuses_with_venv_python_mismatch(tmp_path: Path) -> None:
    for bad_ver, tag in (("3.13.18 (main, Oct 2026)", "313"), ("3.15.1 (main, Oct 2026)", "315")):
        _, state_mis, env_mis = _make_fake_colab_env(tmp_path / f"venv_mismatch_{tag}")
        env_mis["UV_SYSTEM_PYTHON"] = "1"
        env_mis["FAKE_COLAB_VENV_PYTHON_VERSION"] = bad_ver
        env_mis["GUARD_POLL_INTERVAL_S"] = "0.2"
        out_mis = tmp_path / f"out_venv_mismatch_{tag}"
        res_mis = subprocess.run(
            [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_mis), "--session", f"sdlab-l1-vmis-{tag}"],
            env=env_mis,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert res_mis.returncode != 0
        vitals_mis = (out_mis / "vitals.log").read_text(encoding="utf-8")
        assert "REFUSED: VENV_PYTHON_MISMATCH" in vitals_mis
        assert f"STOP -s sdlab-l1-vmis-{tag}" in (state_mis / "stops.log").read_text(encoding="utf-8")


_INSTALL_RE = re.compile(r"(^|[\s;&|(])(pip3?|python3?\s+-m\s+pip|uv\s+pip)\s+(install|sync)\b")


def _unhashed_install_lines(text: str) -> list[str]:
    """Install lines without --require-hashes/--only-binary :all:, and any `uv venv --seed`."""
    bad: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if re.search(r"\buv\s+venv\b", line) and "--seed" in line:
            bad.append(line)
            continue
        if _INSTALL_RE.search(line):
            if "--require-hashes" not in line or "--only-binary :all:" not in line:
                bad.append(line)
    return bad


def test_lane1_preflight_and_lock_refusals_and_no_bare_uv_pip_install(tmp_path: Path) -> None:
    # 1. Static check: every install line in either kit is hash-pinned and wheel-only
    for kit_path in (
        REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh",
        REPO_ROOT / "scripts" / "colab" / "launch_lane3_stub.sh",
    ):
        problems = _unhashed_install_lines(kit_path.read_text(encoding="utf-8"))
        assert problems == [], f"Unhashed installs in {kit_path}: {problems}"
        txt = kit_path.read_text(encoding="utf-8")
        assert [ln for ln in txt.splitlines() if ln.strip().startswith("uv pip install")], kit_path
        assert [ln for ln in txt.splitlines() if ln.strip().startswith("pip install")], kit_path
    # The scanner itself catches each unhashed shape
    assert _unhashed_install_lines('  pip install --quiet "uv==0.13.5"\n')
    assert _unhashed_install_lines("  python -m pip install torch\n")
    assert _unhashed_install_lines("  uv pip install --python /v/bin/python -r x.lock\n")
    assert _unhashed_install_lines("  uv pip sync x.lock\n")
    assert _unhashed_install_lines('  uv venv --python "3.12.15" --seed /content/venv-lane3\n')
    assert not _unhashed_install_lines("  pip install --require-hashes --only-binary :all: --no-deps -r u.txt\n")

    # 2. LOCK_DRIFT refuses before any colab call
    _, state_drift, env_drift = _make_fake_colab_env(tmp_path / "l1_drift")
    tampered_lock = tmp_path / "tampered_lane1.lock"
    tampered_lock.write_text("# drifted lock\n", encoding="utf-8")
    env_drift["SDLAB_PREFLIGHT_MOCK_COMPILE_OUT"] = _to_posix(tampered_lock)
    out_drift = tmp_path / "out_l1_drift"
    res_drift = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_drift), "--session", "sdlab-l1-drift"],
        env=env_drift,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_drift.returncode != 0
    assert "LOCK_DRIFT" in (res_drift.stdout + res_drift.stderr)
    assert not (state_drift / "calls.log").exists(), "LOCK_DRIFT must make no colab call"

    # 3. PIN_NOT_FOUND refuses before any colab call
    _, state_pin, env_pin = _make_fake_colab_env(tmp_path / "l1_pin")
    env_pin["SDLAB_PREFLIGHT_PIN_SHA"] = "73ebae1334d2c98089f1b90f8cb19257825f891a"
    out_pin = tmp_path / "out_l1_pin"
    res_pin = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_pin), "--session", "sdlab-l1-pin"],
        env=env_pin,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_pin.returncode != 0
    assert "PIN_NOT_FOUND" in (res_pin.stdout + res_pin.stderr)
    assert not (state_pin / "calls.log").exists(), "PIN_NOT_FOUND must make no colab call"

    # 4. WHEEL_MISSING on VM surfaces in setup.log and final status (window.json + outcome.draft.json)
    _, state_wm, env_wm = _make_fake_colab_env(tmp_path / "l1_wm")
    env_wm["FAKE_COLAB_MODE"] = "wheel_missing"
    env_wm["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_wm = tmp_path / "out_l1_wm"
    res_wm = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_wm), "--session", "sdlab-l1-wm"],
        env=env_wm,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_wm.returncode != 0
    setup_wm = (state_wm / "content" / "lane1_out" / "setup.log").read_text(encoding="utf-8")
    assert "WHEEL_MISSING" in setup_wm
    win_wm = json.loads((out_wm / "window.json").read_text(encoding="utf-8"))
    out_draft_wm = json.loads((out_wm / "outcome.draft.json").read_text(encoding="utf-8"))
    assert win_wm["status"] == "WHEEL_MISSING"
    assert out_draft_wm["status"] == "WHEEL_MISSING"

    # 5. LOCK_HASH_MISMATCH on VM surfaces in setup.log and final status (window.json + outcome.draft.json)
    _, state_hm, env_hm = _make_fake_colab_env(tmp_path / "l1_hm")
    env_hm["FAKE_COLAB_MODE"] = "lock_hash_mismatch"
    env_hm["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_hm = tmp_path / "out_l1_hm"
    res_hm = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_hm), "--session", "sdlab-l1-hm"],
        env=env_hm,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_hm.returncode != 0
    setup_hm = (state_hm / "content" / "lane1_out" / "setup.log").read_text(encoding="utf-8")
    assert "LOCK_HASH_MISMATCH" in setup_hm
    win_hm = json.loads((out_hm / "window.json").read_text(encoding="utf-8"))
    out_draft_hm = json.loads((out_hm / "outcome.draft.json").read_text(encoding="utf-8"))
    assert win_hm["status"] == "LOCK_HASH_MISMATCH"
    assert out_draft_hm["status"] == "LOCK_HASH_MISMATCH"
    # The refusal is the kit's classifier output and keeps the uv log tail
    assert "REFUSED: LOCK_HASH_MISMATCH during lane1 lock install" in setup_hm
    assert "--- last " in setup_hm and "Computed:" in setup_hm

    # 6. Network and other install failures get their own codes, not WHEEL_MISSING
    for mode, code in (("install_network_failure", "INSTALL_NETWORK_FAILURE"), ("install_failed", "INSTALL_FAILED")):
        _, state_nf, env_nf = _make_fake_colab_env(tmp_path / f"l1_{mode}")
        env_nf["FAKE_COLAB_MODE"] = mode
        env_nf["GUARD_POLL_INTERVAL_S"] = "0.2"
        out_nf = tmp_path / f"out_l1_{mode}"
        res_nf = subprocess.run(
            [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_nf), "--session", f"sdlab-l1-{mode}"],
            env=env_nf,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert res_nf.returncode != 0
        setup_nf = (state_nf / "content" / "lane1_out" / "setup.log").read_text(encoding="utf-8")
        assert f"REFUSED: {code} during lane1 lock install" in setup_nf
        assert "WHEEL_MISSING" not in setup_nf
        assert json.loads((out_nf / "window.json").read_text(encoding="utf-8"))["status"] == code


def test_lane1_import_resolved_outside_venv_or_missing_python_flag_refuses(tmp_path: Path) -> None:
    # 1. An import resolved outside /content/venv-lane1 refuses with VENV_IMPORT_OUTSIDE_VENV
    _, state_out, env_out = _make_fake_colab_env(tmp_path / "import_outside")
    env_out["UV_SYSTEM_PYTHON"] = "1"
    env_out["FAKE_COLAB_MODE"] = "venv_import_outside"
    env_out["FAKE_COLAB_OUTSIDE_IMPORT_PACKAGE"] = "comfy_headless"
    env_out["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_outside = tmp_path / "out_import_outside"
    res_out = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_outside), "--session", "sdlab-l1-impout"],
        env=env_out,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_out.returncode != 0
    vitals_out = (out_outside / "vitals.log").read_text(encoding="utf-8")
    assert "REFUSED: VENV_IMPORT_OUTSIDE_VENV" in vitals_out
    assert "STOP -s sdlab-l1-impout" in (state_out / "stops.log").read_text(encoding="utf-8")

    # 2. A regression where uv pip install omits --python /content/venv-lane1/bin/python lands outside the venv and fails
    _, state_nopy, env_nopy = _make_fake_colab_env(tmp_path / "uv_nopy")
    env_nopy["UV_SYSTEM_PYTHON"] = "1"
    env_nopy["FAKE_COLAB_MODE"] = "uv_no_python_flag"
    env_nopy["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_nopy = tmp_path / "out_uv_nopy"
    res_nopy = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_nopy), "--session", "sdlab-l1-uvnopy"],
        env=env_nopy,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_nopy.returncode != 0
    vitals_nopy = (out_nopy / "vitals.log").read_text(encoding="utf-8")
    assert "REFUSED: VENV_IMPORT_OUTSIDE_VENV" in vitals_nopy
    assert "STOP -s sdlab-l1-uvnopy" in (state_nopy / "stops.log").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Lane 1 --render and --render-cpu-stub tests
# ---------------------------------------------------------------------------


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_safetensors_bytes(tag: bytes) -> bytes:
    payload = tag * 16
    hdr = json.dumps(
        {"weight": {"dtype": "U8", "shape": [len(payload)], "data_offsets": [0, len(payload)]}},
        separators=(",", ":"),
    ).encode("utf-8")
    return struct.pack("<Q", len(hdr)) + hdr + payload


def _make_render_fixture(root: Path, *, hf_token_required: bool = False) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    _, state_dir, env = _make_fake_colab_env(root)
    xdg_dir = root / "xdg_runtime"
    xdg_dir.mkdir(parents=True, exist_ok=True)
    blobs_dir = root / "hf_blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)

    specs = [
        ("Qwen/Qwen-Image", "a" * 40, "qwen_image_fp8.safetensors", "diffusion_models", b"UNET_FP8", False),
        ("Comfy-Org/Qwen-Image_ComfyUI", "b" * 40, "qwen_2.5_vl_7b.safetensors", "text_encoders", b"CLIP_QWN", False),
        ("Comfy-Org/Qwen-Image_ComfyUI", "b" * 40, "qwen_image_vae.safetensors", "vae", b"VAE_QWEN", False),
        ("mcp-tool-shop/style-r1", "c" * 40, "style_r1.safetensors", "loras", b"LORA_R01", hf_token_required),
    ]
    manifest_rows: list[dict[str, Any]] = []
    for repo_id, rev, fname, dest, tag, tok_req in specs:
        blob = _build_safetensors_bytes(tag)
        (blobs_dir / fname).write_bytes(blob)
        row: dict[str, Any] = {
            "repo": repo_id,
            "revision": rev,
            "file": fname,
            "dest": dest,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "licence_id": "Apache-2.0",
        }
        if tok_req:
            row["hf_token_required"] = True
        manifest_rows.append(row)

    manifest_path = root / "weights_manifest.json"
    manifest_path.write_text(json.dumps(manifest_rows, indent=2) + "\n", encoding="utf-8", newline="\n")

    model_pins = {
        "unet": {"name": "qwen_image_fp8.safetensors"},
        "clip": {"name": "qwen_2.5_vl_7b.safetensors", "type": "qwen_image"},
        "vae": {"name": "qwen_image_vae.safetensors"},
        "loras": [{"name": "style_r1.safetensors", "strength_model": 0.8}],
    }
    jobs_rows = [
        {
            "job_id": f"render_{idx:02d}",
            "run_id": "run_render_01",
            "template_id": "qwen_txt2img_lora",
            "prompt": f"ink wash study {idx}",
            "negative_prompt": "blurry",
            "seed": 1000 + idx,
            "width": 512,
            "height": 512,
            "steps": 20,
            "cfg": 2.5,
            "canon_sha": "a881cb5ba656e0618080d2269498fda7f36ac93a",
            "entry_id": f"ships/brig_{idx}",
            "entry_sha256": "sha256:" + (f"{idx}" * 64)[:64],
            "workflow_sha": "sha256:" + "d" * 64,
            "model_pins": model_pins,
        }
        for idx in (1, 2, 3)
    ]
    jobs_path = root / "jobs.jsonl"
    jobs_path.write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in jobs_rows),
        encoding="utf-8",
        newline="\n",
    )
    jobs_sha = hashlib.sha256(jobs_path.read_bytes()).hexdigest()
    port = _free_loopback_port()

    env["XDG_RUNTIME_DIR"] = _to_posix(xdg_dir)
    env["FAKE_HF_BLOBS_DIR"] = str(blobs_dir)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    env["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.2"
    env["SDLAB_TEST_SMOKE_SECONDS"] = "0.05"
    env["SDLAB_TEST_DISK_REQUIRED_GIB"] = "0.001"
    env["SDLAB_TEST_PROBE_SECONDS"] = "0.1"
    env["SDLAB_TEST_PROBE_BYTES"] = "1024"
    env["SDLAB_TEST_COMFY_PORT"] = str(port)

    base_args = [
        "--render",
        "--card",
        "A100",
        "--shape",
        "high-mem",
        "--weights-manifest",
        _to_posix(manifest_path),
        "--jobs",
        _to_posix(jobs_path),
        "--jobs-sha256",
        jobs_sha,
        "--copy-back-every",
        "2",
        "--host-ram-required-gib",
        "12",
        "--download-max-seconds",
        "300",
        "--cap",
        "5.0",
        "--max-rate",
        "10.5",
    ]
    return {
        "state_dir": state_dir,
        "env": env,
        "xdg_dir": xdg_dir,
        "blobs_dir": blobs_dir,
        "manifest_path": manifest_path,
        "manifest_rows": manifest_rows,
        "jobs_path": jobs_path,
        "jobs_rows": jobs_rows,
        "jobs_sha": jobs_sha,
        "port": port,
        "base_args": base_args,
    }


def _run_launcher(args: list[str], env: dict[str, str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _strip_arg(args: list[str], flag: str, *, takes_value: bool = True) -> list[str]:
    out: list[str] = []
    idx = 0
    while idx < len(args):
        if args[idx] == flag:
            idx += 2 if takes_value else 1
        else:
            out.append(args[idx])
            idx += 1
    return out


def _replace_arg(args: list[str], flag: str, new_val: str) -> list[str]:
    out = list(args)
    pos = out.index(flag)
    out[pos + 1] = new_val
    return out


def _assert_secret_nowhere(secret: str, state_dir: Path, out_dir: Path, res: subprocess.CompletedProcess[str]) -> None:
    assert secret not in (res.stdout + res.stderr), "secret leaked to launcher stdout/stderr"
    for sf in ("argv.log", "calls.log", "exec_code.py"):
        sp = state_dir / sf
        if sp.is_file():
            assert secret not in sp.read_text(encoding="utf-8", errors="replace"), f"secret leaked in {sp}"
    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.name.endswith(".tar.gz") and tarfile.is_tarfile(p):
            with tarfile.open(p, "r:gz") as tf:
                for member in tf.getmembers():
                    if member.isfile():
                        ext = tf.extractfile(member)
                        if ext is not None:
                            txt = ext.read().decode("utf-8", errors="replace")
                            assert secret not in txt, f"secret leaked in bundle member {member.name}"
        else:
            assert secret not in p.read_text(encoding="utf-8", errors="replace"), f"secret leaked in {p}"


def test_lane1_render_required_options_refused_by_name_before_any_colab_call(tmp_path: Path) -> None:
    fx = _make_render_fixture(tmp_path / "base")
    base = fx["base_args"]

    cases: list[tuple[str, list[str], str]] = [
        ("cpu_default", _strip_arg(_strip_arg(base, "--card"), "--shape"), "RENDER_REQUIRES_GPU"),
        ("cpu_explicit", _replace_arg(_strip_arg(base, "--shape"), "--card", "CPU"), "RENDER_REQUIRES_GPU"),
        ("no_shape", _strip_arg(base, "--shape"), "SHAPE_REQUIRED"),
        ("bad_shape", _replace_arg(base, "--shape", "bogus"), "SHAPE_INVALID"),
        ("no_manifest", _strip_arg(base, "--weights-manifest"), "RENDER_MANIFEST_REQUIRED"),
        ("no_jobs", _strip_arg(base, "--jobs"), "RENDER_JOBS_REQUIRED"),
        ("no_jobs_sha", _strip_arg(base, "--jobs-sha256"), "RENDER_JOBS_SHA_REQUIRED"),
        ("bad_jobs_sha_fmt", _replace_arg(base, "--jobs-sha256", "not-a-hex-sha"), "RENDER_JOBS_SHA_REQUIRED"),
        ("no_copy_back", _strip_arg(base, "--copy-back-every"), "RENDER_COPY_BACK_REQUIRED"),
        ("zero_copy_back", _replace_arg(base, "--copy-back-every", "0"), "RENDER_COPY_BACK_REQUIRED"),
        ("no_ram", _strip_arg(base, "--host-ram-required-gib"), "HOST_RAM_THRESHOLD_MISSING"),
        ("zero_ram", _replace_arg(base, "--host-ram-required-gib", "0"), "HOST_RAM_THRESHOLD_MISSING"),
        ("no_dl_max", _strip_arg(base, "--download-max-seconds"), "DOWNLOAD_LIMIT_MISSING"),
        ("zero_dl_max", _replace_arg(base, "--download-max-seconds", "0"), "DOWNLOAD_LIMIT_MISSING"),
        ("no_cap", _strip_arg(base, "--cap"), "RENDER_CAP_REQUIRED"),
        ("zero_cap", _replace_arg(base, "--cap", "0"), "RENDER_CAP_REQUIRED"),
        ("no_max_rate", _strip_arg(base, "--max-rate"), "RENDER_MAX_RATE_REQUIRED"),
        ("zero_max_rate", _replace_arg(base, "--max-rate", "0"), "RENDER_MAX_RATE_REQUIRED"),
    ]
    for label, cli_args, expected_code in cases:
        _, state_c, env_c = _make_fake_colab_env(tmp_path / f"req_{label}")
        out_c = tmp_path / f"out_req_{label}"
        res = _run_launcher([*cli_args, "--out-dir", _to_posix(out_c), "--session", f"sdlab-req-{label}"], env_c)
        assert res.returncode != 0, f"{label} unexpectedly succeeded"
        assert f"REFUSED: {expected_code}:" in res.stderr, f"{label} missing {expected_code}: {res.stderr}"
        assert not (state_c / "calls.log").exists(), f"{label} made a colab call before refusing"


def test_lane1_render_options_without_render_refused_before_any_colab_call(tmp_path: Path) -> None:
    fx = _make_render_fixture(tmp_path / "opt_base")
    single_option_cases = [
        ("manifest", ["--weights-manifest", _to_posix(fx["manifest_path"])]),
        ("jobs", ["--jobs", _to_posix(fx["jobs_path"])]),
        ("jobs_sha", ["--jobs-sha256", fx["jobs_sha"]]),
        ("copy_back", ["--copy-back-every", "2"]),
        ("host_ram", ["--host-ram-required-gib", "8"]),
        ("dl_max", ["--download-max-seconds", "120"]),
        ("both_modes", ["--render", "--render-cpu-stub"]),
        ("cpu_stub_with_jobs", ["--render-cpu-stub", "--jobs", _to_posix(fx["jobs_path"])]),
        ("cpu_stub_with_copy_back", ["--render-cpu-stub", "--copy-back-every", "2"]),
    ]
    for label, extra_args in single_option_cases:
        _, state_c, env_c = _make_fake_colab_env(tmp_path / f"opt_{label}")
        out_c = tmp_path / f"out_opt_{label}"
        res = _run_launcher([*extra_args, "--out-dir", _to_posix(out_c), "--session", f"sdlab-opt-{label}"], env_c)
        assert res.returncode != 0, f"{label} unexpectedly succeeded"
        assert "REFUSED: RENDER_OPTION_WITHOUT_RENDER:" in res.stderr, f"{label} stderr: {res.stderr}"
        assert not (state_c / "calls.log").exists(), f"{label} made a colab call"


def test_lane1_render_rig_input_validation_refusals_before_any_colab_call(tmp_path: Path) -> None:
    fx = _make_render_fixture(tmp_path / "val_base")
    base = fx["base_args"]

    # 1. Bad jobs sha256 -> JOBS_SHA_MISMATCH before any colab call
    _, st_sha, env_sha = _make_fake_colab_env(tmp_path / "bad_jsha")
    out_sha = tmp_path / "out_bad_jsha"
    res_sha = _run_launcher(
        [*_replace_arg(base, "--jobs-sha256", "f" * 64), "--out-dir", _to_posix(out_sha), "--session", "sdlab-bad-jsha"],
        env_sha,
    )
    assert res_sha.returncode != 0
    assert "REFUSED: JOBS_SHA_MISMATCH:" in res_sha.stderr
    assert not (st_sha / "calls.log").exists()
    assert json.loads((out_sha / "window.json").read_text(encoding="utf-8"))["refusal_code"] == "JOBS_SHA_MISMATCH"

    # 2. Fixture template stub_fixture_64 in a render job -> JOB_TEMPLATE_INVALID before any colab call
    bad_tpl_jobs = tmp_path / "fixture_tpl_jobs.jsonl"
    row_tpl = dict(fx["jobs_rows"][0], template_id="stub_fixture_64")
    bad_tpl_jobs.write_text(json.dumps(row_tpl) + "\n", encoding="utf-8", newline="\n")
    bad_tpl_sha = hashlib.sha256(bad_tpl_jobs.read_bytes()).hexdigest()
    _, st_tpl, env_tpl = _make_fake_colab_env(tmp_path / "bad_tpl")
    out_tpl = tmp_path / "out_bad_tpl"
    args_tpl = _replace_arg(_replace_arg(base, "--jobs", _to_posix(bad_tpl_jobs)), "--jobs-sha256", bad_tpl_sha)
    res_tpl = _run_launcher([*args_tpl, "--out-dir", _to_posix(out_tpl), "--session", "sdlab-bad-tpl"], env_tpl)
    assert res_tpl.returncode != 0
    assert "REFUSED: JOB_TEMPLATE_INVALID:" in res_tpl.stderr
    assert not (st_tpl / "calls.log").exists()
    assert json.loads((out_tpl / "window.json").read_text(encoding="utf-8"))["refusal_code"] == "JOB_TEMPLATE_INVALID"

    # 3. Malformed render job (missing steps) -> RENDER_JOB_INVALID without echoing prompt content
    secret_prompt = "SECRET_PROMPT_CONTENT_NEVER_LOG_7741"
    bad_job_file = tmp_path / "bad_row_jobs.jsonl"
    bad_row = {k: v for k, v in fx["jobs_rows"][0].items() if k != "steps"}
    bad_row["prompt"] = secret_prompt
    bad_job_file.write_text(json.dumps(bad_row) + "\n", encoding="utf-8", newline="\n")
    bad_job_sha = hashlib.sha256(bad_job_file.read_bytes()).hexdigest()
    _, st_job, env_job = _make_fake_colab_env(tmp_path / "bad_job")
    out_job = tmp_path / "out_bad_job"
    args_job = _replace_arg(_replace_arg(base, "--jobs", _to_posix(bad_job_file)), "--jobs-sha256", bad_job_sha)
    res_job = _run_launcher([*args_job, "--out-dir", _to_posix(out_job), "--session", "sdlab-bad-job"], env_job)
    assert res_job.returncode != 0
    assert "REFUSED: RENDER_JOB_INVALID:" in res_job.stderr
    assert not (st_job / "calls.log").exists()
    _assert_secret_nowhere(secret_prompt, st_job, out_job, res_job)

    # 4. Manifest row without licence_id -> WEIGHTS_LICENCE_INVALID before any colab call
    no_lic_manifest = tmp_path / "no_licence_manifest.json"
    no_lic_row = {k: v for k, v in fx["manifest_rows"][0].items() if k != "licence_id"}
    no_lic_manifest.write_text(json.dumps([no_lic_row], indent=2) + "\n", encoding="utf-8", newline="\n")
    _, st_lic, env_lic = _make_fake_colab_env(tmp_path / "no_lic")
    out_lic = tmp_path / "out_no_lic"
    args_lic = _replace_arg(base, "--weights-manifest", _to_posix(no_lic_manifest))
    res_lic = _run_launcher([*args_lic, "--out-dir", _to_posix(out_lic), "--session", "sdlab-no-lic"], env_lic)
    assert res_lic.returncode != 0
    assert "REFUSED: WEIGHTS_LICENCE_INVALID:" in res_lic.stderr
    assert not (st_lic / "calls.log").exists()
    assert json.loads((out_lic / "window.json").read_text(encoding="utf-8"))["refusal_code"] == "WEIGHTS_LICENCE_INVALID"

    # 5. Manifest row with non-40-hex revision -> WEIGHTS_REVISION_INVALID before any colab call
    bad_rev_manifest = tmp_path / "bad_rev_manifest.json"
    bad_rev_manifest.write_text(
        json.dumps([{**fx["manifest_rows"][0], "revision": "main"}], indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _, st_rev, env_rev = _make_fake_colab_env(tmp_path / "bad_rev")
    out_rev = tmp_path / "out_bad_rev"
    args_rev = _replace_arg(base, "--weights-manifest", _to_posix(bad_rev_manifest))
    res_rev = _run_launcher([*args_rev, "--out-dir", _to_posix(out_rev), "--session", "sdlab-bad-rev"], env_rev)
    assert res_rev.returncode != 0
    assert "REFUSED: WEIGHTS_REVISION_INVALID:" in res_rev.stderr
    assert not (st_rev / "calls.log").exists()

    # 6. Manifest row with invalid dest -> WEIGHTS_DEST_INVALID before any colab call
    bad_dest_manifest = tmp_path / "bad_dest_manifest.json"
    bad_dest_manifest.write_text(
        json.dumps([{**fx["manifest_rows"][0], "dest": "checkpoints"}], indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _, st_dst, env_dst = _make_fake_colab_env(tmp_path / "bad_dest")
    out_dst = tmp_path / "out_bad_dest"
    args_dst = _replace_arg(base, "--weights-manifest", _to_posix(bad_dest_manifest))
    res_dst = _run_launcher([*args_dst, "--out-dir", _to_posix(out_dst), "--session", "sdlab-bad-dest"], env_dst)
    assert res_dst.returncode != 0
    assert "REFUSED: WEIGHTS_DEST_INVALID:" in res_dst.stderr
    assert not (st_dst / "calls.log").exists()


def test_lane1_render_weights_sha_mismatch_on_vm_stops_before_comfy_starts(tmp_path: Path) -> None:
    # 1. Corrupted downloaded weights refuse WEIGHTS_SHA_MISMATCH before ComfyUI starts, bundle partial evidence, and stop
    fx_sha = _make_render_fixture(tmp_path / "vm_sha")
    env_sha = fx_sha["env"]
    env_sha["FAKE_HF_CORRUPT_SHA"] = "1"
    out_sha = tmp_path / "out_vm_sha"
    res_sha = _run_launcher([*fx_sha["base_args"], "--out-dir", _to_posix(out_sha), "--session", "sdlab-vm-wsha"], env_sha)
    assert res_sha.returncode != 0
    assert not (fx_sha["state_dir"] / "comfy_started.json").exists(), "ComfyUI must not start on WEIGHTS_SHA_MISMATCH"
    win_sha = json.loads((out_sha / "window.json").read_text(encoding="utf-8"))
    assert win_sha["status"] == "WEIGHTS_SHA_MISMATCH"
    assert win_sha["refusal_code"] == "WEIGHTS_SHA_MISMATCH"
    assert "lane1_render_bundle.tar.gz" in win_sha["downloaded_files"]
    assert "STOP -s sdlab-vm-wsha" in (fx_sha["state_dir"] / "stops.log").read_text(encoding="utf-8")

    # 2. GPU smoke failure before download refuses GPU_SMOKE_FAILED before ComfyUI starts
    fx_gpu = _make_render_fixture(tmp_path / "vm_gpu")
    env_gpu = fx_gpu["env"]
    env_gpu["FAKE_VM_GPU_SMOKE"] = "no_cuda"
    out_gpu = tmp_path / "out_vm_gpu"
    res_gpu = _run_launcher([*fx_gpu["base_args"], "--out-dir", _to_posix(out_gpu), "--session", "sdlab-vm-gpu"], env_gpu)
    assert res_gpu.returncode != 0
    assert not (fx_gpu["state_dir"] / "comfy_started.json").exists()
    win_gpu = json.loads((out_gpu / "window.json").read_text(encoding="utf-8"))
    assert win_gpu["status"] == "GPU_SMOKE_FAILED"
    assert "lane1_render_bundle.tar.gz" in win_gpu["downloaded_files"]
    assert "STOP -s sdlab-vm-gpu" in (fx_gpu["state_dir"] / "stops.log").read_text(encoding="utf-8")


def test_lane1_render_runs_comfy_without_cpu_on_loopback_and_stub_keeps_cpu(tmp_path: Path) -> None:
    # 1. --render starts ComfyUI without --cpu on 127.0.0.1, runs bootstrap kill + resume, stamps PNGs, records wall_s & peak_vram_mib
    secret_tok = "hf_secretLane1RenderReadTok9876543210abcd"
    fx = _make_render_fixture(tmp_path / "render_ok", hf_token_required=True)
    env = fx["env"]
    env["HF_TOKEN_GGUF_READ"] = secret_tok
    env["FAKE_HF_EXPECT_TOKEN"] = secret_tok
    out_dir = tmp_path / "out_render_ok"
    res = _run_launcher([*fx["base_args"], "--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-render-ok"], env)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    started = json.loads((fx["state_dir"] / "comfy_started.json").read_text(encoding="utf-8"))
    assert started["cpu"] is False
    assert "--cpu" not in started["argv"]
    assert started["listen"] == "127.0.0.1"
    assert started["port"] == fx["port"]
    assert started["cuda_visible_devices"] != ""

    workflows = json.loads((fx["state_dir"] / "comfy_workflows.json").read_text(encoding="utf-8"))
    assert len(workflows) == 3, "job 1 rendered before kill-after=1, then skipped on resume while jobs 2 and 3 rendered"
    for wf in workflows:
        assert {"CLIPLoader", "KSampler", "LoraLoaderModelOnly", "UNETLoader", "VAELoader"}.issubset(set(wf["class_types"]))

    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok" and win["refusal_code"] is None
    assert win["render"] == "rendered"
    assert win["hf_token_used"] is True
    assert win["comfy_bind"] == f"127.0.0.1:{fx['port']}"
    assert win["listening_sockets"] == [f"127.0.0.1:{fx['port']}"]
    assert "lane1_render_bundle.tar.gz" in win["downloaded_files"]
    assert "lane1_stub_bundle.tar.gz" not in win["downloaded_files"]
    assert not (fx["state_dir"] / "content" / "lane1_hf_read_token").exists()
    assert list(fx["xdg_dir"].iterdir()) == []
    _assert_secret_nowhere(secret_tok, fx["state_dir"], out_dir, res)

    bundle_extract = tmp_path / "extracted_render_bundle"
    bundle_extract.mkdir()
    with tarfile.open(out_dir / "lane1_render_bundle.tar.gz", "r:gz") as tf:
        tf.extractall(bundle_extract, filter="data")
    render_rows = [
        json.loads(ln)
        for ln in (bundle_extract / "renders.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert [r["job_id"] for r in render_rows] == ["render_01", "render_02", "render_03"]
    for row in render_rows:
        assert row["status"] == "ok"
        assert row["stamp_verified"] is True
        assert isinstance(row["wall_s"], (int, float)) and 0.0 <= row["wall_s"] < 60.0
        assert row["wall_ms"] == round(row["wall_s"] * 1000)
        assert isinstance(row["peak_vram_mib"], (int, float)) and row["peak_vram_mib"] == 14336.0
        assert (bundle_extract / "pngs" / row["output_file"]).is_file()
        assert (bundle_extract / "copy_back" / row["output_file"]).is_file()
    assert (bundle_extract / "copy_back" / "renders.jsonl").is_file()

    models_root = fx["state_dir"] / "content" / "ComfyUI" / "models"
    assert (models_root / "diffusion_models" / "qwen_image_fp8.safetensors").is_file()
    assert (models_root / "text_encoders" / "qwen_2.5_vl_7b.safetensors").is_file()
    assert (models_root / "vae" / "qwen_image_vae.safetensors").is_file()
    assert (models_root / "loras" / "style_r1.safetensors").is_file()

    # 2. Stub mode still starts ComfyUI with --cpu on loopback and bundles lane1_stub_bundle.tar.gz
    _, state_stub, env_stub = _make_fake_colab_env(tmp_path / "stub_pair")
    env_stub["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_stub = tmp_path / "out_stub_pair"
    res_stub = _run_launcher(["--out-dir", _to_posix(out_stub), "--session", "sdlab-l1-stub-pair"], env_stub)
    assert res_stub.returncode == 0, res_stub.stderr
    remote_stub_sh = (out_stub / "remote_lane1_stub.sh").read_text(encoding="utf-8")
    assert "/content/ComfyUI/main.py --cpu --listen 127.0.0.1" in remote_stub_sh
    win_stub = json.loads((out_stub / "window.json").read_text(encoding="utf-8"))
    assert win_stub["listening_sockets"] == ["127.0.0.1:8188"]
    assert "lane1_stub_bundle.tar.gz" in win_stub["downloaded_files"]


def test_lane1_render_planned_colab_calls_in_order_and_stop(tmp_path: Path) -> None:
    fx = _make_render_fixture(tmp_path / "calls_order")
    out_dir = tmp_path / "out_calls_order"
    session = "sdlab-l1-order"
    res = _run_launcher([*fx["base_args"], "--out-dir", _to_posix(out_dir), "--session", session], fx["env"])
    assert res.returncode == 0, f"STDERR:\n{res.stderr}"

    calls = [
        ln.strip()
        for ln in (fx["state_dir"] / "calls.log").read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith("CALL ")
    ]
    assert calls[0] == "CALL usage"
    assert calls[1] == f"CALL new --gpu A100 --high-mem -s {session}"
    assert calls[2] == "CALL usage"
    assert calls[3] == "CALL sessions"

    upload_targets = [ln.split()[-1] for ln in calls if ln.startswith(f"CALL upload -s {session} ")]
    assert upload_targets == [
        "/content/lane1.lock",
        "/content/lane1_render.py",
        "/content/launch_guards.py",
        "/content/classify_install_log.py",
        "/content/lane3_rung.py",
        "/content/weights_manifest.json",
        "/content/jobs.jsonl",
        "/content/remote_lane1_stub.sh",
    ]

    first_upload_idx = next(i for i, ln in enumerate(calls) if ln.startswith(f"CALL upload -s {session} "))
    last_upload_idx = max(i for i, ln in enumerate(calls) if ln.startswith(f"CALL upload -s {session} "))
    exec_idx = next(i for i, ln in enumerate(calls) if ln.startswith(f"CALL exec -s {session} "))
    dl_idx = next(
        i
        for i, ln in enumerate(calls)
        if ln.startswith(f"CALL download -s {session} /content/lane1_render_bundle.tar.gz ")
    )
    stop_idx = next(i for i, ln in enumerate(calls) if ln == f"CALL stop -s {session}")

    assert 3 < first_upload_idx < last_upload_idx < exec_idx < dl_idx < stop_idx
    assert calls[-3:] == [f"CALL stop -s {session}", "CALL sessions", "CALL usage"]


def test_lane1_render_cpu_stub_route_and_committed_fixture_manifest(tmp_path: Path) -> None:
    import lane1_render as l1r

    committed_manifest = REPO_ROOT / "scripts" / "colab" / "lane1" / "render-cpu-stub-manifest.json"
    assert committed_manifest.is_file(), f"Missing committed CPU stub manifest: {committed_manifest}"
    parsed = l1r.validate_weights_manifest(committed_manifest)
    assert len(parsed) == 1
    assert parsed[0]["repo"] == "madebyollin/taesd"
    assert parsed[0]["revision"] == "614f76814bbe30edbe2e627ace1c2234c81a2c0e"
    assert parsed[0]["file"] == "taesd_decoder.safetensors"
    assert parsed[0]["dest"] == "vae"
    assert parsed[0]["licence_id"] == "MIT"

    # --render-cpu-stub refuses a GPU card before any colab call
    _, st_gpu, env_gpu = _make_fake_colab_env(tmp_path / "cpu_stub_gpu")
    out_gpu = tmp_path / "out_cpu_stub_gpu"
    res_gpu = _run_launcher(
        ["--render-cpu-stub", "--card", "A100", "--shape", "standard", "--out-dir", _to_posix(out_gpu)],
        env_gpu,
    )
    assert res_gpu.returncode != 0
    assert "REFUSED: RENDER_CPU_STUB_REQUIRES_CPU:" in res_gpu.stderr
    assert not (st_gpu / "calls.log").exists()

    # End-to-end --render-cpu-stub on CPU: install, download, sha256 check and safetensors unpack without starting ComfyUI
    _, st_ok, env_ok = _make_fake_colab_env(tmp_path / "cpu_stub_ok")
    blobs_dir = tmp_path / "cpu_stub_blobs"
    blobs_dir.mkdir()
    tiny_vae = _build_safetensors_bytes(b"TAESD_TINY_FIXTURE")
    (blobs_dir / "taesd_decoder.safetensors").write_bytes(tiny_vae)
    local_manifest = tmp_path / "cpu_stub_manifest.json"
    local_manifest.write_text(
        json.dumps(
            [
                {
                    "repo": "madebyollin/taesd",
                    "revision": "614f76814bbe30edbe2e627ace1c2234c81a2c0e",
                    "file": "taesd_decoder.safetensors",
                    "dest": "vae",
                    "sha256": hashlib.sha256(tiny_vae).hexdigest(),
                    "licence_id": "MIT",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    env_ok["FAKE_HF_BLOBS_DIR"] = str(blobs_dir)
    env_ok["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_ok["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.2"
    env_ok["SDLAB_TEST_DISK_REQUIRED_GIB"] = "0.001"
    env_ok["SDLAB_TEST_PROBE_SECONDS"] = "0.1"
    env_ok["SDLAB_TEST_PROBE_BYTES"] = "512"
    out_ok = tmp_path / "out_cpu_stub_ok"
    res_ok = _run_launcher(
        [
            "--render-cpu-stub",
            "--weights-manifest",
            _to_posix(local_manifest),
            "--out-dir",
            _to_posix(out_ok),
            "--session",
            "sdlab-l1-render-cpustub",
        ],
        env_ok,
    )
    assert res_ok.returncode == 0, f"STDOUT:\n{res_ok.stdout}\nSTDERR:\n{res_ok.stderr}"
    assert not (st_ok / "comfy_started.json").exists(), "CPU stub of --render must not start ComfyUI"
    assert (st_ok / "content" / "ComfyUI" / "models" / "vae" / "taesd_decoder.safetensors").is_file()
    win_ok = json.loads((out_ok / "window.json").read_text(encoding="utf-8"))
    assert win_ok["status"] == "ok"
    assert win_ok["render"] == "skipped_cpu_stub"
    assert win_ok["weights_download"]["probe_window"] == {"seconds": 0.1, "bytes": 512}
    assert win_ok["weights_download"]["files"][0]["safetensors_verified"] is True
    assert "lane1_render_bundle.tar.gz" in win_ok["downloaded_files"]
    assert "STOP -s sdlab-l1-render-cpustub" in (st_ok / "stops.log").read_text(encoding="utf-8")


def test_lane1_stub_path_unchanged(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path / "stub_unchanged")
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / "out_stub_unchanged"
    res = _run_launcher(["--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-stub-unchanged"], env)
    assert res.returncode == 0, f"STDERR:\n{res.stderr}"
    calls_log = (state_dir / "calls.log").read_text(encoding="utf-8")
    assert "CALL new --high-mem -s sdlab-l1-stub-unchanged" in calls_log
    remote_sh = (out_dir / "remote_lane1_stub.sh").read_text(encoding="utf-8")
    assert "/content/ComfyUI/main.py --cpu --listen 127.0.0.1" in remote_sh
    assert '"template_id":"stub_fixture_64"' in remote_sh
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok"
    assert win["listening_sockets"] == ["127.0.0.1:8188"]
    assert "lane1_stub_bundle.tar.gz" in win["downloaded_files"]
    assert "STOP -s sdlab-l1-stub-unchanged" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_lane1_render_dry_on_gpu_card_prints_effective_trip(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path / "render_dry")
    res = _run_launcher(
        [
            "--render",
            "--card",
            "A100",
            "--shape",
            "high-mem",
            "--cap",
            "5.0",
            "--max-rate",
            "10.5",
            "--dry",
        ],
        env,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert not (state_dir / "calls.log").exists()
    assert "effective_trip:" in res.stdout
    assert "runtime_to_trip" in res.stdout
    rec = json.loads(res.stdout.strip().splitlines()[-1])
    assert rec["cleanup_bound_s"] == 450
    assert rec["cleanup_reserve_units"] == pytest.approx(1.3125)
    assert rec["effective_trip"] == pytest.approx(3.6775)
    assert rec["runtime_to_trip_s"] == pytest.approx(round((3.6775 / 10.5) * 3600.0, 2))

    # --render --dry on CPU card is refused with RENDER_REQUIRES_GPU
    _, state_cpu, env_cpu = _make_fake_colab_env(tmp_path / "render_dry_cpu")
    res_cpu = _run_launcher(["--render", "--cap", "5.0", "--max-rate", "10.5", "--dry"], env_cpu)
    assert res_cpu.returncode != 0
    assert "REFUSED: RENDER_REQUIRES_GPU:" in res_cpu.stderr
    assert not (state_cpu / "calls.log").exists()


def _override_worktree_input_shas(env: dict[str, str]) -> None:
    colab_dir = REPO_ROOT / "scripts" / "colab"
    pin_files = {
        "EXPECTED_LANE1_LOCK_SHA": colab_dir / "locks" / "lane1.lock",
        "EXPECTED_LANE1_RENDER_SHA": colab_dir / "lane1_render.py",
        "EXPECTED_LANE3_RUNG_SHA": colab_dir / "lane3_rung.py",
        "EXPECTED_INSTALL_CLASSIFIER_SHA": colab_dir / "classify_install_log.py",
        "EXPECTED_LAUNCH_GUARDS_SHA": colab_dir / "launch_guards.py",
        "EXPECTED_REMOTE_RUNNER_SHA": colab_dir / "remote_runner.py",
        "EXPECTED_COLAB_WINDOW_SHA": colab_dir / "colab_window.sh",
        "EXPECTED_LAUNCH_LANE1_STUB_SHA": colab_dir / "launch_lane1_stub.sh",
    }
    for key, path in pin_files.items():
        env[key] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_lane1_render_and_render_cpu_stub_together_refused_before_any_colab_call(tmp_path: Path) -> None:
    for label, cli_args in (
        ("live_cpu", ["--render", "--render-cpu-stub", "--out-dir", _to_posix(tmp_path / "out_both_live")]),
        ("dry_cpu", ["--render", "--render-cpu-stub", "--dry"]),
        (
            "dry_gpu",
            ["--render", "--render-cpu-stub", "--card", "A100", "--shape", "high-mem", "--cap", "5.0", "--max-rate", "10.5", "--dry"],
        ),
    ):
        _, state_dir, env = _make_fake_colab_env(tmp_path / f"both_{label}")
        _override_worktree_input_shas(env)
        res = _run_launcher(cli_args, env)
        assert res.returncode != 0, f"{label} unexpectedly succeeded"
        assert "REFUSED: RENDER_OPTION_WITHOUT_RENDER:" in res.stderr, f"{label} stderr: {res.stderr}"
        assert not (state_dir / "calls.log").exists(), f"{label} made a colab call before refusing"
    assert not (tmp_path / "out_both_live").exists()


def test_lane1_render_launcher_arms_download_probe_from_test_env(tmp_path: Path) -> None:
    # 1. _make_render_fixture sets the SDLAB_TEST_PROBE_* variables launch_lane1_stub.sh actually reads
    fx = _make_render_fixture(tmp_path / "probe_arm")
    env = dict(fx["env"])
    _override_worktree_input_shas(env)
    out_arm = tmp_path / "out_probe_arm"
    res_arm = _run_launcher(
        [
            "--render-cpu-stub",
            "--weights-manifest",
            _to_posix(fx["manifest_path"]),
            "--out-dir",
            _to_posix(out_arm),
            "--session",
            "sdlab-l1-probe-arm",
        ],
        env,
    )
    assert res_arm.returncode == 0, f"STDOUT:\n{res_arm.stdout}\nSTDERR:\n{res_arm.stderr}"
    win_arm = json.loads((out_arm / "window.json").read_text(encoding="utf-8"))
    assert win_arm["weights_download"]["probe_window"] == {"seconds": 0.1, "bytes": 1024}

    # 2. Armed probe trips DOWNLOAD_TOO_SLOW on a slow second file from the same repo even after a larger cached file
    _, st_trip, env_trip = _make_fake_colab_env(tmp_path / "probe_trip")
    _override_worktree_input_shas(env_trip)
    blobs_trip = tmp_path / "blobs_trip"
    blobs_trip.mkdir()
    big_enc = _build_safetensors_bytes(b"E" * 8192)
    small_vae = _build_safetensors_bytes(b"V" * 2048)
    (blobs_trip / "big_encoder.safetensors").write_bytes(big_enc)
    (blobs_trip / "small_vae.safetensors").write_bytes(small_vae)
    two_file_manifest = tmp_path / "two_file_same_repo.json"
    two_file_manifest.write_text(
        json.dumps(
            [
                {
                    "repo": "Qwen/Qwen-Image",
                    "revision": "8" * 40,
                    "file": "big_encoder.safetensors",
                    "dest": "text_encoders",
                    "sha256": hashlib.sha256(big_enc).hexdigest(),
                    "licence_id": "Apache-2.0",
                },
                {
                    "repo": "Qwen/Qwen-Image",
                    "revision": "8" * 40,
                    "file": "small_vae.safetensors",
                    "dest": "vae",
                    "sha256": hashlib.sha256(small_vae).hexdigest(),
                    "licence_id": "Apache-2.0",
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    env_trip["FAKE_HF_BLOBS_DIR"] = str(blobs_trip)
    env_trip["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_trip["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.2"
    env_trip["SDLAB_TEST_DISK_REQUIRED_GIB"] = "0.001"
    env_trip["SDLAB_TEST_PROBE_SECONDS"] = "0.1"
    env_trip["SDLAB_TEST_PROBE_BYTES"] = "32"
    env_trip["FAKE_HF_SLOW_FILE"] = "small_vae.safetensors"
    env_trip["FAKE_HF_PROBE_PAUSE_S"] = "0.4"
    out_trip = tmp_path / "out_probe_trip"
    res_trip = _run_launcher(
        [
            "--render-cpu-stub",
            "--weights-manifest",
            _to_posix(two_file_manifest),
            "--download-max-seconds",
            "5",
            "--out-dir",
            _to_posix(out_trip),
            "--session",
            "sdlab-l1-probe-trip",
        ],
        env_trip,
    )
    assert res_trip.returncode != 0
    win_trip = json.loads((out_trip / "window.json").read_text(encoding="utf-8"))
    assert win_trip["status"] == "DOWNLOAD_TOO_SLOW"
    assert "STOP -s sdlab-l1-probe-trip" in (st_trip / "stops.log").read_text(encoding="utf-8")


def test_fake_colab_stub_runs_real_lane1_render_without_lane3_rung(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path / "real_stub")
    _override_worktree_input_shas(env)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / "out_real_stub"
    res = _run_launcher(["--out-dir", _to_posix(out_dir), "--session", "sdlab-l1-real-stub"], env)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert (state_dir / "content" / "lane1_render.py").is_file()
    assert not (state_dir / "content" / "lane3_rung.py").exists()

    bundle_path = out_dir / "lane1_stub_bundle.tar.gz"
    assert tarfile.is_tarfile(bundle_path), "stub mode must produce a real tar.gz bundle from lane1_render.py"
    extract_dir = tmp_path / "extracted_stub_bundle"
    extract_dir.mkdir()
    with tarfile.open(bundle_path, "r:gz") as tf:
        tf.extractall(extract_dir, filter="data")
    renders_file = extract_dir / "renders.jsonl"
    assert renders_file.is_file()
    rows = [json.loads(ln) for ln in renders_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [r["job_id"] for r in rows] == ["stub_01", "stub_02"]
    for row in rows:
        assert row["status"] == "ok"
        assert row["stamp_verified"] is True
        assert (extract_dir / "pngs" / row["output_file"]).is_file()
        assert (extract_dir / "copy_back" / row["output_file"]).is_file()

