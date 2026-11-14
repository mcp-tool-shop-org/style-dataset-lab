"""The shared GPU rate gate (colab_window.sh): lane 1 on a GPU card, and the structure that keeps
every lane behind it. Lane 3's own gate tests are in test_lane3_gpu_rung.py."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
LANE1 = COLAB_DIR / "launch_lane1_stub.sh"
WINDOW_SH = COLAB_DIR / "colab_window.sh"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))

import fake_colab as fc  # noqa: E402


def _bash() -> str:
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _lane1(tmp_path: Path, extra_env: dict[str, str], *extra: str, mode: str = "setup_phase",
           max_rate: str | None = "9.5", cap: str = "3") -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    env.update({"SDLAB_TEST_RATE_READ_INTERVAL_S": "0.05", "GUARD_POLL_INTERVAL_S": "0.3",
                "FAKE_COLAB_MODE": mode, "FAKE_COLAB_SETUP_DURATION_S": "3", "SETUP_STALL_S": "60",
                "STALL_S": "600"})
    env.update(extra_env)
    out_dir = tmp_path / "out"
    args = [_bash(), fc._to_posix(LANE1), "--card", "A100", "--session", "sdlab-l1-gpu",
            "--out-dir", fc._to_posix(out_dir), "--cap", cap, "--shape", "high-mem"]
    if max_rate is not None:
        args += ["--max-rate", max_rate]
    res = subprocess.run([*args, *extra], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                         timeout=120, check=False)
    return res, out_dir, state_dir


def _win(out_dir: Path) -> dict:
    return json.loads((out_dir / "window.json").read_text(encoding="utf-8"))


def _no_uploads(state_dir: Path) -> bool:
    uploads = state_dir / "uploads.log"
    return not uploads.exists() or "UPLOAD_OK" not in uploads.read_text(encoding="utf-8")


def _calls(state_dir: Path) -> str:
    f = state_dir / "calls.log"
    return f.read_text(encoding="utf-8") if f.exists() else ""


# Lane 1 on a GPU card: the same gate as lane 3.

def test_lane1_gpu_card_without_max_rate_refuses_before_open(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, {}, max_rate=None)
    assert res.returncode == 2 and "MAX_RATE_REQUIRED" in res.stderr
    assert "CALL new" not in _calls(state_dir)


def test_lane1_parallel_neighbour_reproducer_refuses_above_max(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.26/hr",
                                                "FAKE_COLAB_POST_OPEN_RATE_SEQ": "0.26/hr,9.14/hr"},
                                     "--max-rate", "8.0")
    assert res.returncode != 0
    win = _win(out_dir)
    assert win["refusal_code"] == "RATE_ABOVE_MAX" and _no_uploads(state_dir)
    assert win["rate_check"]["window_rate"] == 8.88 and win["rate_check"]["pre_open_rate"] == 0.26
    assert "STOP -s sdlab-l1-gpu" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_lane1_rate_waits_for_stability_and_prices_at_the_max(tmp_path: Path) -> None:
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                        "FAKE_COLAB_POST_OPEN_RATE_SEQ": "4.00/hr,8.88/hr"})
    assert res.returncode == 0, res.stderr[-3000:]
    win = _win(out_dir)
    assert win["status"] == "ok" and win["card"] == "A100"
    assert win["rate_check"]["window_rate"] == 8.88 and win["rate_check"]["polls"] == 3
    assert win["rate_check"]["priced_at"] == 9.5 and win["rate_used_for_cap_and_projection"] == 9.5
    assert win["cap_clock_started_at"]


def test_lane1_gpu_window_with_no_rate_refuses_rate_unread(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                                "FAKE_COLAB_POST_OPEN_RATE_STR": "0.00/hr"})
    assert res.returncode != 0
    win = _win(out_dir)
    assert win["refusal_code"] == "RATE_UNREAD" and win["rate_check"]["polls"] == 24
    assert _no_uploads(state_dir) and "STOP -s sdlab-l1-gpu" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_lane1_a_low_window_rate_is_priced_at_max_rate_so_the_cap_trips_on_time(tmp_path: Path) -> None:
    # Priced at max(9.5, 2.15): 0.05 units last 18.9 s (at 2.15/h they would last 84 s).
    # On Lane 1 (cleanup_bound_s = 450 s) at 9.5/h, cleanup_reserve = (450 / 3600) * 9.5 = 1.1875 units;
    # cap 2.2375 minus margin 1.0 minus reserve 1.1875 leaves effective_trip = 0.05 units (~18.95 s).
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                        "FAKE_COLAB_POST_OPEN_RATE_STR": "2.15/hr",
                                        "FAKE_COLAB_VITALS_INTERVAL_S": "1.0"},
                             "--margin", "1.0", mode="stall", cap="2.2375")
    assert res.returncode != 0
    lines = [json.loads(ln) for ln in (out_dir / "guards.log").read_text(encoding="utf-8").splitlines()
             if ln.startswith("{") and '"cap"' in ln and '"live"' in ln]
    tripped = [r for r in lines if r["cap"]["tripped"]]
    assert tripped, "the cap never tripped"
    elapsed = tripped[0]["wall"]["threshold_s"] - tripped[0]["wall"]["remaining_s"]
    assert 18.9 <= elapsed <= 30, elapsed
    assert _win(out_dir)["rate_check"]["window_rate"] == 2.15


@pytest.mark.parametrize("rise", ["9.80", "12.00"])
def test_lane1_a_midrun_rise_above_max_rate_refuses(tmp_path: Path, rise: str) -> None:
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                        "FAKE_COLAB_POST_OPEN_RATE_SEQ": f"8.88/hr,8.88/hr,8.88/hr,8.88/hr,{rise}/hr"},
                             mode="stall")
    assert res.returncode == 91, res.stderr[-2000:]
    win = _win(out_dir)
    assert win["refusal_code"] == "RATE_ABOVE_MAX"
    assert "mid-run" in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert max(r["window_rate"] or 0 for r in win["rate_readings"]) == float(rise)


def test_lane1_a_neighbour_opening_midrun_rebaselines_and_runs_on(tmp_path: Path) -> None:
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                        "FAKE_COLAB_POST_OPEN_RATE_SEQ": "8.88/hr,8.88/hr,8.88/hr,8.88/hr,17.76/hr",
                                        "FAKE_COLAB_ASSIGNMENTS_SEQ": "1,1,1,1,2"})
    assert res.returncode == 0, res.stderr[-3000:]
    win = _win(out_dir)
    assert win["status"] == "ok" and win["refusal_code"] is None
    reb = [r for r in win["rate_readings"] if r.get("rebaselined")]
    assert reb and reb[0]["neighbour_baseline"] == 8.88 and reb[0]["assignments"] == 2
    assert all((r["window_rate"] or 0) <= 8.88 for r in win["rate_readings"])
    assert win["rate_used_for_cap_and_projection"] == 9.5


def test_lane1_a_neighbour_closing_midrun_is_not_an_under_read(tmp_path: Path) -> None:
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "8.88/hr",
                                        "FAKE_COLAB_POST_OPEN_RATE_SEQ": "17.76/hr,17.76/hr,17.76/hr,17.76/hr,8.88/hr",
                                        "FAKE_COLAB_ASSIGNMENTS_SEQ": "2,2,2,2,1"})
    assert res.returncode == 0, res.stderr[-3000:]
    readings = _win(out_dir)["rate_readings"]
    after = [r for r in readings if r["counted"] and r.get("assignments") == 1 and not r.get("rebaseline_pending")]
    assert after and all(r["window_rate"] == 8.88 for r in after), after


@pytest.mark.parametrize("bad", ["OMITLINE", "0"])
def test_lane1_a_bad_assignments_count_for_three_cycles_ends_the_window(tmp_path: Path, bad: str) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                                "FAKE_COLAB_ASSIGNMENTS_SEQ": f"1,1,1,1,{bad}"}, mode="stall")
    assert res.returncode == 91, res.stderr[-2000:]
    win = _win(out_dir)
    assert win["refusal_code"] == "ASSIGNMENTS_UNREADABLE"
    assert "mid-run" in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert sum(1 for r in win["rate_readings"] if r.get("assignments_bad")) >= 3
    assert "STOP -s sdlab-l1-gpu" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_lane1_count_0_until_the_session_registers_proceeds(tmp_path: Path) -> None:
    # The fake's registration fixture (receipt windowC2-12-t4-s1a-20261027): 0.00 with 0 assignments
    # for three reads, then the card's rate (8.88 for the A100) with 1.
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                        "FAKE_COLAB_OPEN_REGISTERING": "1"})
    assert res.returncode == 0, res.stderr[-2000:]
    win = _win(out_dir)
    assert win["status"] == "ok" and win["rate_check"]["window_rate"] == 8.88
    regs = [r for r in win["rate_readings"] if r.get("not_registered")]
    assert len(regs) == 3 and all(r["account_rate"] == 0.0 and r["assignments"] == 0 for r in regs)


def test_lane1_count_0_for_the_whole_open_budget_is_rate_unread(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                                "FAKE_COLAB_POST_OPEN_RATE_STR": "0.00/hr",
                                                "FAKE_COLAB_ASSIGNMENTS_SEQ": "0"})
    assert res.returncode != 0
    win = _win(out_dir)
    assert win["refusal_code"] == "RATE_UNREAD" and win["rate_check"]["polls"] == 24
    assert _no_uploads(state_dir)


def test_lane1_count_0_at_open_then_mid_run_still_ends(tmp_path: Path) -> None:
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                        "FAKE_COLAB_POST_OPEN_RATE_SEQ": "0.00/hr,0.00/hr,0.00/hr,8.88/hr",
                                        "FAKE_COLAB_ASSIGNMENTS_SEQ": "0,0,0,1,1,1,1,0"}, mode="stall")
    assert res.returncode == 91, res.stderr[-2000:]
    win = _win(out_dir)
    assert win["refusal_code"] == "ASSIGNMENTS_UNREADABLE" and win["rate_check"]["window_rate"] == 8.88
    assert "REFUSED: ASSIGNMENTS_UNREADABLE: mid-run" in (out_dir / "guards.log").read_text(encoding="utf-8")


def test_lane1_a_single_missing_count_is_recorded_only(tmp_path: Path) -> None:
    res, out_dir, _ = _lane1(tmp_path, {"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                                        "FAKE_COLAB_ASSIGNMENTS_SEQ": "1,1,1,OMITLINE,1"})
    assert res.returncode == 0, res.stderr[-2000:]
    win = _win(out_dir)
    assert win["status"] == "ok"
    assert [r for r in win["rate_readings"] if r.get("assignments_bad")] and win["refusal_code"] is None


def test_lane1_cpu_stub_is_unchanged(tmp_path: Path) -> None:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out"
    res = subprocess.run([_bash(), fc._to_posix(LANE1), "--out-dir", fc._to_posix(out_dir), "--session", "sdlab-l1-cpu"],
                         env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False)
    assert res.returncode == 0, res.stderr[-2000:]
    assert "CALL new --high-mem -s sdlab-l1-cpu" in _calls(state_dir)
    assert not (out_dir / "max_rate.txt").exists() and not (out_dir / "rate_window.json").exists()
    assert not (out_dir / "gpu_rate_gate_armed.txt").exists()


# Structure: no lane can open a GPU window without the gate.

def _source(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([_bash(), "-c", f"set -euo pipefail; source {fc._to_posix(WINDOW_SH)}; {script}"],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False)


def test_open_refuses_a_gpu_card_that_was_not_armed(tmp_path: Path) -> None:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    env["PY_BIN"] = sys.executable
    for pre in ("", "export COLAB_CARD_CLASS=gpu; "):
        res = _source(f"{pre}colab_open_session_locked s1 A100 {fc._to_posix(out)}", env)
        assert res.returncode == 2 and "GPU_RATE_GATE_NOT_ARMED" in res.stderr, res.stderr
    assert "CALL new" not in _calls(state_dir)


def test_the_gate_arms_five_second_reads_and_refuses_the_test_hook_live(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    env.pop("SDLAB_TEST_RATE_READ_INTERVAL_S", None)
    res = _source(f"colab_gpu_rate_gate_arm {fc._to_posix(out)} A100 9.5 0; echo \"I=$COLAB_RATE_READ_INTERVAL_S\"", env)
    assert res.returncode == 0 and "I=5" in res.stdout
    assert (out / "max_rate.txt").read_text(encoding="utf-8").strip() == "9.5"
    env["SDLAB_TEST_RATE_READ_INTERVAL_S"] = "0.05"
    res = _source(f"colab_gpu_rate_gate_arm {fc._to_posix(out)} A100 9.5 0", env)
    assert res.returncode != 0 and "PIN_OVERRIDE_IN_LIVE_RUN" in res.stderr
    for bad in ("", "0", "0.0", "abc"):
        res = _source(f"colab_gpu_rate_gate_arm {fc._to_posix(out)} T4 '{bad}' 1", env)
        assert res.returncode == 2 and "MAX_RATE_REQUIRED" in res.stderr


def test_every_lane_arms_the_gate_before_it_opens_and_only_colab_window_calls_new() -> None:
    kits = sorted(COLAB_DIR.glob("launch_*.sh"))
    assert {k.name for k in kits} >= {"launch_lane1_stub.sh", "launch_lane3_stub.sh"}
    for kit in kits:
        text = kit.read_text(encoding="utf-8")
        if "colab_open_session_locked" not in text:
            continue
        arm = text.find("colab_gpu_rate_gate_arm \"")
        opened = text.find("colab_open_session_locked \"")
        assert 0 <= arm < opened, f"{kit.name} opens a window without arming the GPU rate gate first"
    for script in COLAB_DIR.rglob("*.sh"):
        if script.name == "colab_window.sh":
            continue
        code = "\n".join(ln for ln in script.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))
        assert not re.search(r"(^|[\s;(\"'])colab\s+\"?new\b", code, re.M), script
