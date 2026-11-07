"""Tests for scripts/colab/launch_lane3_stub.sh against the contract-checked fake colab CLI."""

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
LAUNCHER = REPO_ROOT / "scripts" / "colab" / "launch_lane3_stub.sh"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))

import fake_colab as fc  # noqa: E402


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
    env["SDLAB_WHEEL_DIR"] = _to_posix(tmp_path)
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
    assert outcome["train"] == "skipped_cpu_stub" and outcome["trained"] is False


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
    out_wall = tmp_path / "out_wall"

    res_wall = subprocess.run(
        [
            _find_bash(),
            _to_posix(LAUNCHER),
            "--out-dir",
            _to_posix(out_wall),
            "--session",
            "sdlab-l3-wall",
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
    assert "STOP -s sdlab-l3-wall" in (state_dir_wall / "stops.log").read_text(encoding="utf-8")


def test_trainer_kit_pins_and_keeps_the_train_step_behind_train_mode(tmp_path: Path) -> None:
    kit_text = LAUNCHER.read_text(encoding="utf-8")
    for required_var in (
        "PINNED_UV_VERSION=",
        "PINNED_UV_WHEEL_SHA256=",
        "PINNED_INSTALL_CLASSIFIER_SHA=",
        "PINNED_PYTHON_VERSION=",
        "PINNED_PYTORCH_INDEX_URL=",
        "PINNED_AI_TOOLKIT_REPO=",
        "PINNED_AI_TOOLKIT_COMMIT=",
        "PINNED_OVERRIDE_SHA=",
        "PINNED_LAUNCH_GUARDS_SHA=",
        "PINNED_REMOTE_RUNNER_SHA=",
        "PINNED_COLAB_WINDOW_SHA=",
        "PINNED_SELF_SHA=",
    ):
        assert required_var in kit_text, f"Missing top-of-kit pin variable {required_var}"

    # Installs from hash-locked lane3.lock and local-wheels.lock with --require-hashes --only-binary :all:
    assert "/content/lane3.lock" in kit_text
    assert "/content/lane3_out/local-wheels.lock" in kit_text
    assert "https://download.pytorch.org/whl/cu130" in kit_text
    assert "git -C /content/ai-toolkit checkout" in kit_text
    assert "beb94824c51480a04d3c86c718603676fdef6938" in kit_text
    # The CPU stub stops at the import gate; the GPU rung (the committed rung YAML, run by
    # ai-toolkit's run.py, with its checkpoints copied off) stays behind LANE3_MODE=train.
    assert 'echo "TRAIN_SKIPPED: cpu stub; training needs a GPU rung"' in kit_text
    assert 'LANE3_MODE="\\${LANE3_MODE:-install}"' in kit_text
    assert "TRAIN_REQUIRES_GPU" in kit_text and "TRAIN_MODEL_REQUIRED" in kit_text
    assert "/content/lane3_out/rung_job.yaml" in kit_text
    assert "/content/rung-qwen-image.yaml" in kit_text
    assert "synth_job.yaml" not in kit_text and "synth_lora" not in kit_text
    for pin in ("PINNED_LANE3_RUNG_SHA=", "PINNED_RUNG_YAML_SHA=", "PINNED_RUNG500_YAML_SHA=", "PINNED_RUNG_DATASET_SHA="):
        assert pin in kit_text, pin

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

    # 3. CAP_GUARD_TRIPPED during live colab exec kills EXEC_PID and stops session (in text format)
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
    usage_log_cap = (out_cap / "usage.log").read_text(encoding="utf-8")
    assert "Current balance: 9.85 compute units" in usage_log_cap
    assert "Current balance: 9.75 compute units" in usage_log_cap
    assert "balance_ccu" not in usage_log_cap

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
    assert win["python"] == "3.12.15"
    assert win["checkpoint_path"] is None
    assert win["train"] == "skipped_cpu_stub" and win["trained"] is False
    assert win["start_balance"] == 9.85
    assert win["end_balance"] == 9.85
    assert win["rate_measured"] == 0.26
    assert win["rate_measured_pre_open"] == 0.26
    assert win["rate_measured_post_open"] == 0.26
    assert win["rate_used_for_cap_and_projection"] == 0.26
    assert win["rate_source"] == "post_open_measured"
    assert win["usage_parse_error"] is None
    assert "lane3_stub_bundle.tar.gz" in win["downloaded_files"]
    assert (state_ok / "sessions.log").exists()
    remote_sh = (out_ok / "remote_lane3_stub.sh").read_text(encoding="utf-8")
    assert "--scrub-file" in remote_sh


def test_lane3_exec_call_passes_contract_py_file_and_timeout_gt_wall(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_contract"
    res = subprocess.run(
        [
            _find_bash(),
            _to_posix(LAUNCHER),
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l3-contract",
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
    assert any(kv.endswith("/content/remote_lane3_stub.sh") and kv.startswith("SDLAB_REMOTE_SCRIPT=") for kv in env_kv)
    assert any(kv.startswith("PINNED_AI_TOOLKIT_COMMIT=") for kv in env_kv)


def test_lane3_unparseable_usage_refuses_before_new_and_stops_midrun_with_no_10_0(tmp_path: Path) -> None:
    _, state_start, env_start = _make_fake_colab_env(tmp_path / "usage_start_case")
    env_start["FAKE_COLAB_MODE"] = "usage_fail_start"
    out_start = tmp_path / "out_usage_start"
    res_start = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_start), "--session", "sdlab-l3-ustart"],
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
    assert "10.0" not in (out_start / "window.json").read_text(encoding="utf-8")

    _, state_mid, env_mid = _make_fake_colab_env(tmp_path / "usage_mid_case")
    env_mid["FAKE_COLAB_MODE"] = "usage_fail_midrun"
    env_mid["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_mid = tmp_path / "out_usage_mid"
    res_mid = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_mid), "--session", "sdlab-l3-umid"],
        env=env_mid,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_mid.returncode != 0
    assert "COLAB_USAGE_PARSE_FAILED" in (out_mid / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-umid" in (state_mid / "stops.log").read_text(encoding="utf-8")
    assert "10.0" not in (out_mid / "window.json").read_text(encoding="utf-8")


def test_lane3_preseeded_start_balance_in_out_dir_refuses_with_out_dir_not_empty_before_new(tmp_path: Path) -> None:
    _, state_dir, env = _make_fake_colab_env(tmp_path / "nonempty_case")
    env["FAKE_COLAB_MODE"] = "cap_burn"
    out_dir = tmp_path / "out_nonempty"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "start_balance.txt").write_text("9.75\n", encoding="utf-8")

    res = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_dir), "--session", "sdlab-l3-nonempty"],
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


def test_lane3_midrun_poll_helper_crash_and_negative_balance_stop_window_rc_91(tmp_path: Path) -> None:
    _, state_crash, env_crash = _make_fake_colab_env(tmp_path / "helper_crash")
    env_crash["FAKE_COLAB_MODE"] = "stall"
    env_crash["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_crash["SDLAB_FAULT_POLL_HELPER_MIDRUN"] = "crash"
    out_crash = tmp_path / "out_helper_crash"
    res_crash = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_crash), "--session", "sdlab-l3-hcrash"],
        env=env_crash,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_crash.returncode == 91
    assert "COLAB_USAGE_PARSE_FAILED" in (out_crash / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-hcrash" in (state_crash / "stops.log").read_text(encoding="utf-8")

    _, state_neg, env_neg = _make_fake_colab_env(tmp_path / "neg_mid")
    env_neg["FAKE_COLAB_MODE"] = "negative_balance_midrun"
    env_neg["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_neg = tmp_path / "out_neg_mid"
    res_neg = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_neg), "--session", "sdlab-l3-negmid"],
        env=env_neg,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_neg.returncode == 91
    assert "COLAB_USAGE_PARSE_FAILED" in (out_neg / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-negmid" in (state_neg / "stops.log").read_text(encoding="utf-8")


def test_lane3_setup_phase_and_silent_setup_stall_and_post_open_rate(tmp_path: Path) -> None:
    # 1. Setup phase with no workers and steady output succeeds, then switches to run; post-open 0.00/hr then 0.29/hr
    _, state_ok, env_ok = _make_fake_colab_env(tmp_path / "l3_setup_ok")
    env_ok["FAKE_COLAB_MODE"] = "setup_phase"
    env_ok["FAKE_COLAB_SETUP_DURATION_S"] = "8"
    env_ok["FAKE_COLAB_SETUP_SCALE"] = "0.2"
    env_ok["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env_ok["FAKE_COLAB_POST_OPEN_RATE_SEQ"] = "0.00/hr,0.29/hr"
    env_ok["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_ok["SETUP_STALL_S"] = "3"
    out_ok = tmp_path / "out_l3_setup_ok"
    res_ok = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_ok), "--session", "sdlab-l3-setup-ok"],
        env=env_ok,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_ok.returncode == 0, f"STDERR:\n{res_ok.stderr}"
    vitals_txt = (out_ok / "vitals.log").read_text(encoding="utf-8")
    assert '"phase": "setup"' in vitals_txt
    # The CPU install-path stub ends at the import gate: it never enters the run phase.
    assert '"phase": "run"' not in vitals_txt
    win_ok = json.loads((out_ok / "window.json").read_text(encoding="utf-8"))
    assert win_ok["rate_measured_pre_open"] == 0.0
    assert win_ok["rate_measured_post_open"] == 0.29
    assert win_ok["rate_used_for_cap_and_projection"] == 0.29
    assert win_ok["rate_source"] == "post_open_measured"
    assert "STOP -s sdlab-l3-setup-ok" in (state_ok / "stops.log").read_text(encoding="utf-8")

    # 2. Silent setup trips SETUP_STALL_TRIPPED while vitals blocks continue, and trap stops session
    _, state_stall, env_stall = _make_fake_colab_env(tmp_path / "l3_setup_stall")
    env_stall["FAKE_COLAB_MODE"] = "setup_stall"
    env_stall["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.2"
    env_stall["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_stall["SETUP_STALL_S"] = "3"
    out_stall = tmp_path / "out_l3_setup_stall"
    res_stall = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_stall), "--session", "sdlab-l3-setup-stall"],
        env=env_stall,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_stall.returncode == 93
    vitals_stall = (out_stall / "vitals.log").read_text(encoding="utf-8")
    assert vitals_stall.count("=== VITALS ") >= 3
    assert "SETUP_STALL_TRIPPED" in (out_stall / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-setup-stall" in (state_stall / "stops.log").read_text(encoding="utf-8")


def test_lane3_uv_system_python_env_explicit_venv_python_and_gates(tmp_path: Path) -> None:
    # With UV_SYSTEM_PYTHON=1 set, the kit unsets UV_SYSTEM_PYTHON, sets UV_PYTHON_INSTALL_DIR under /content,
    # names /content/venv-lane3/bin/python on every uv pip install and python invocation, and the window passes.
    _, state_ok, env_ok = _make_fake_colab_env(tmp_path / "l3_uv_sys_ok")
    env_ok["UV_SYSTEM_PYTHON"] = "1"
    env_ok["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_ok = tmp_path / "out_l3_uv_sys_ok"
    res_ok = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_ok), "--session", "sdlab-l3-uvsys-ok"],
        env=env_ok,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_ok.returncode == 0, f"STDERR:\n{res_ok.stderr}"
    remote_sh = (out_ok / "remote_lane3_stub.sh").read_text(encoding="utf-8")
    assert "unset UV_SYSTEM_PYTHON" in remote_sh
    assert 'export UV_PYTHON_INSTALL_DIR="/content/.sdlab_python_312/install"' in remote_sh
    assert "source /content/venv-lane3/bin/activate" not in remote_sh
    assert "uv venv --python \"${PINNED_PYTHON_VERSION}\" /content/venv-lane3" in remote_sh
    assert "--seed" not in remote_sh
    assert (
        "/content/venv-lane3/bin/python -c 'import sys; assert sys.version.startswith(\"3.12.15\"), sys.version; "
        "assert sys.prefix.startswith(\"/content/venv-lane\"), sys.prefix'"
    ) in remote_sh
    assert "uv pip install --python /content/venv-lane3/bin/python" in remote_sh
    uv_pip_lines = [
        line.strip()
        for line in remote_sh.splitlines()
        if line.strip().startswith("uv pip install")
    ]
    assert len(uv_pip_lines) == 2
    assert all("--require-hashes" in line and "--only-binary :all:" in line for line in uv_pip_lines)
    assert any("--no-index" in line and "--find-links /content/wheels" in line for line in uv_pip_lines)
    assert "/content/venv-lane3/bin/python /content/ai-toolkit/run.py" in remote_sh
    assert "/content/venv-lane3/bin/python /content/launch_guards.py" in remote_sh
    vitals_ok = (out_ok / "vitals.log").read_text(encoding="utf-8")
    assert "VENV_IMPORT sentencepiece /content/venv-lane3/" in vitals_ok
    assert "STOP -s sdlab-l3-uvsys-ok" in (state_ok / "stops.log").read_text(encoding="utf-8")


def test_lane3_venv_python_version_mismatch_refuses_with_venv_python_mismatch(tmp_path: Path) -> None:
    for bad_ver, tag in (("3.13.18 (main, Oct 2026)", "313"), ("3.15.1 (main, Oct 2026)", "315")):
        _, state_mis, env_mis = _make_fake_colab_env(tmp_path / f"l3_venv_mismatch_{tag}")
        env_mis["UV_SYSTEM_PYTHON"] = "1"
        env_mis["FAKE_COLAB_VENV_PYTHON_VERSION"] = bad_ver
        env_mis["GUARD_POLL_INTERVAL_S"] = "0.2"
        out_mis = tmp_path / f"out_l3_venv_mismatch_{tag}"
        res_mis = subprocess.run(
            [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_mis), "--session", f"sdlab-l3-vmis-{tag}"],
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
        assert f"STOP -s sdlab-l3-vmis-{tag}" in (state_mis / "stops.log").read_text(encoding="utf-8")


def test_lane3_local_wheels_and_preflight_refusals_before_any_colab_call(tmp_path: Path) -> None:
    # 1. LOCAL_WHEEL_MISSING refuses before any colab call
    _, state_wmiss, env_wmiss = _make_fake_colab_env(tmp_path / "l3_wmiss")
    empty_wheels = tmp_path / "empty_wheels"
    empty_wheels.mkdir(parents=True, exist_ok=True)
    out_wmiss = tmp_path / "out_l3_wmiss"
    res_wmiss = subprocess.run(
        [
            _find_bash(),
            _to_posix(LAUNCHER),
            "--out-dir",
            _to_posix(out_wmiss),
            "--wheel-dir",
            _to_posix(empty_wheels),
            "--session",
            "sdlab-l3-wmiss",
        ],
        env=env_wmiss,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_wmiss.returncode != 0
    assert "LOCAL_WHEEL_MISSING" in (res_wmiss.stdout + res_wmiss.stderr)
    assert not (state_wmiss / "calls.log").exists(), "LOCAL_WHEEL_MISSING must make no colab call"

    # 2. LOCAL_WHEEL_SHA_MISMATCH refuses before any colab call
    _, state_wsha, env_wsha = _make_fake_colab_env(tmp_path / "l3_wsha")
    bad_wheels = tmp_path / "bad_wheels"
    bad_wheels.mkdir(parents=True, exist_ok=True)
    fixture_manifest = json.loads(Path(env_wsha["SDLAB_PREFLIGHT_WHEELS_MANIFEST"]).read_text(encoding="utf-8"))
    for idx, entry in enumerate(fixture_manifest["wheels"]):
        (bad_wheels / entry["filename"]).write_bytes(f"corrupted_wheel_bytes_{idx}".encode())
    out_wsha = tmp_path / "out_l3_wsha"
    res_wsha = subprocess.run(
        [
            _find_bash(),
            _to_posix(LAUNCHER),
            "--out-dir",
            _to_posix(out_wsha),
            "--wheel-dir",
            _to_posix(bad_wheels),
            "--session",
            "sdlab-l3-wsha",
        ],
        env=env_wsha,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_wsha.returncode != 0
    assert "LOCAL_WHEEL_SHA_MISMATCH" in (res_wsha.stdout + res_wsha.stderr)
    assert not (state_wsha / "calls.log").exists(), "LOCAL_WHEEL_SHA_MISMATCH must make no colab call"

    # 3. LOCK_DRIFT refuses before any colab call
    _, state_drift, env_drift = _make_fake_colab_env(tmp_path / "l3_drift")
    tampered_lock = tmp_path / "tampered_lane3.lock"
    tampered_lock.write_text("# drifted lane3 lock\n", encoding="utf-8")
    env_drift["SDLAB_PREFLIGHT_MOCK_COMPILE_OUT"] = _to_posix(tampered_lock)
    out_drift = tmp_path / "out_l3_drift"
    res_drift = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_drift), "--session", "sdlab-l3-drift"],
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

    # 4. PIN_NOT_FOUND refuses before any colab call (e.g. old bogus sha 73ebae13...)
    _, state_pin, env_pin = _make_fake_colab_env(tmp_path / "l3_pin")
    env_pin["SDLAB_PREFLIGHT_PIN_SHA"] = "73ebae1334d2c98089f1b90f8cb19257825f891a"
    out_pin = tmp_path / "out_l3_pin"
    res_pin = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_pin), "--session", "sdlab-l3-pin"],
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

    # 5. WHEEL_MISSING and LOCK_HASH_MISMATCH on VM surface in setup.log and final status
    for mode, expected_code in (
        ("wheel_missing", "WHEEL_MISSING"),
        ("lock_hash_mismatch", "LOCK_HASH_MISMATCH"),
        ("install_network_failure", "INSTALL_NETWORK_FAILURE"),
        ("install_failed", "INSTALL_FAILED"),
    ):
        _, state_vm, env_vm = _make_fake_colab_env(tmp_path / f"l3_{mode}")
        env_vm["FAKE_COLAB_MODE"] = mode
        env_vm["GUARD_POLL_INTERVAL_S"] = "0.2"
        out_vm = tmp_path / f"out_l3_{mode}"
        res_vm = subprocess.run(
            [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_vm), "--session", f"sdlab-l3-{mode}"],
            env=env_vm,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert res_vm.returncode != 0
        setup_vm = (state_vm / "content" / "lane3_out" / "setup.log").read_text(encoding="utf-8")
        assert f"REFUSED: {expected_code} during lane3 lock install" in setup_vm
        assert "--- last " in setup_vm, "the refusal keeps the tail of the uv log"
        win_vm = json.loads((out_vm / "window.json").read_text(encoding="utf-8"))
        out_draft_vm = json.loads((out_vm / "outcome.draft.json").read_text(encoding="utf-8"))
        assert win_vm["status"] == expected_code
        assert out_draft_vm["status"] == expected_code


def test_lane3_import_resolved_outside_venv_or_missing_python_flag_refuses(tmp_path: Path) -> None:
    # 1. An import resolved outside the venv refuses with VENV_IMPORT_OUTSIDE_VENV
    _, state_out, env_out = _make_fake_colab_env(tmp_path / "l3_import_outside")
    env_out["UV_SYSTEM_PYTHON"] = "1"
    env_out["FAKE_COLAB_MODE"] = "venv_import_outside"
    env_out["FAKE_COLAB_OUTSIDE_IMPORT_PACKAGE"] = "sentencepiece"
    env_out["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_outside = tmp_path / "out_l3_import_outside"
    res_out = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_outside), "--session", "sdlab-l3-impout"],
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
    assert "STOP -s sdlab-l3-impout" in (state_out / "stops.log").read_text(encoding="utf-8")

    # 2. A regression where uv pip install omits --python /content/venv-lane3/bin/python lands outside the venv and fails
    _, state_nopy, env_nopy = _make_fake_colab_env(tmp_path / "l3_uv_nopy")
    env_nopy["UV_SYSTEM_PYTHON"] = "1"
    env_nopy["FAKE_COLAB_MODE"] = "uv_no_python_flag"
    env_nopy["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_nopy = tmp_path / "out_l3_uv_nopy"
    res_nopy = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_nopy), "--session", "sdlab-l3-uvnopy"],
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
    assert "STOP -s sdlab-l3-uvnopy" in (state_nopy / "stops.log").read_text(encoding="utf-8")




def test_lane3_wheel_dir_required_and_test_hooks_refused_in_live_run(tmp_path: Path, persistent_out_root: Path) -> None:
    # No --wheel-dir and no SDLAB_WHEEL_DIR: named refusal, no default path, no colab call
    _, state_nd, env_nd = _make_fake_colab_env(tmp_path / "l3_nodir")
    env_nd.pop("SDLAB_WHEEL_DIR")
    res_nd = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(tmp_path / "out_l3_nodir"), "--session", "sdlab-l3-nodir"],
        env=env_nd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_nd.returncode == 2
    assert "REFUSED: WHEEL_DIR_REQUIRED" in res_nd.stderr
    assert not (state_nd / "calls.log").exists()

    # A pre-flight test hook in a run without the fake-colab flag: PREFLIGHT_TEST_HOOK_IN_LIVE_RUN,
    # before any colab call (`colab` on PATH is still the fake, so nothing real can be reached).
    _, state_live, env_live = _make_fake_colab_env(tmp_path / "l3_live_hook")
    env_live.pop("SDLAB_TEST_FAKE_COLAB")
    env_live.pop("EXPECTED_LOCAL_WHEELS_MANIFEST_SHA")
    real_names_dir = tmp_path / "unused_wheels"
    real_names_dir.mkdir()
    env_live["SDLAB_WHEEL_DIR"] = _to_posix(real_names_dir)
    out_live = persistent_out_root / "out_l3_live_hook"
    res_live = subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), "--out-dir", _to_posix(out_live), "--session", "sdlab-l3-livehook"],
        env=env_live,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_live.returncode != 0
    assert "PREFLIGHT_TEST_HOOK_IN_LIVE_RUN" in res_live.stderr
    assert "SDLAB_PREFLIGHT_FAST_COMPILE_MOCK" in res_live.stderr
    assert not (state_live / "calls.log").exists(), "a refused test hook must make no colab call"
    assert json.loads((out_live / "window.json").read_text(encoding="utf-8"))["status"] == "PREFLIGHT_TEST_HOOK_IN_LIVE_RUN"
