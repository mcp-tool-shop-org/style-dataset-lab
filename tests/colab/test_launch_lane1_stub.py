"""Tests for scripts/colab/launch_lane1_stub.sh against the contract-checked fake colab CLI."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

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
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_cap), "--session", "sdlab-l1-cap", "--cap", "0.05", "--margin", "0.01"],
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
    assert "uv venv --python \"${PINNED_PYTHON_VERSION}\" --seed /content/venv-lane1" in remote_sh
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


def test_lane1_preflight_and_lock_refusals_and_no_bare_uv_pip_install(tmp_path: Path) -> None:
    # 1. Static check: no bare `uv pip install` without `--require-hashes` in either kit
    for kit_path in (
        REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh",
        REPO_ROOT / "scripts" / "colab" / "launch_lane3_stub.sh",
    ):
        txt = kit_path.read_text(encoding="utf-8")
        uv_lines = [line.strip() for line in txt.splitlines() if line.strip().startswith("uv pip install")]
        assert uv_lines, f"Expected uv pip install lines in {kit_path}"
        for line in uv_lines:
            assert "--require-hashes" in line, f"Bare uv pip install without --require-hashes in {kit_path}: {line}"
            assert "--only-binary :all:" in line, f"uv pip install without --only-binary :all: in {kit_path}: {line}"

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
    env_pin["SDLAB_PREFLIGHT_LS_REMOTE_OVERRIDE"] = "158419f3a0017c2ce123484b14b6c527716d6ec8\trefs/tags/v0.3.34"
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

