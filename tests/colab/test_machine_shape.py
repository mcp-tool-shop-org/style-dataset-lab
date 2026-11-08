"""The machine shape gate (colab_window.sh: colab_shape_gate_arm, colab_open_session_locked,
colab_check_session_shape). A GPU card names its shape with --shape standard|high-mem, with no
default; --high-mem reaches `colab new` only for high-mem; the session row's Shape must match after
open. A CPU card keeps its fixed `colab new --high-mem`. Lane 3's own shape tests are in
test_lane3_gpu_rung.py."""

from __future__ import annotations

import json
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


def _lane1(tmp_path: Path, card: str, shape: str | None, extra_env: dict[str, str] | None = None,
           session: str = "sdlab-l1-shape") -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    env.update({"SDLAB_TEST_RATE_READ_INTERVAL_S": "0.05", "GUARD_POLL_INTERVAL_S": "0.3",
                "FAKE_COLAB_MODE": "setup_phase", "FAKE_COLAB_SETUP_DURATION_S": "3", "SETUP_STALL_S": "60",
                "STALL_S": "600", "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr"})
    env.update(extra_env or {})
    out_dir = tmp_path / "out"
    args = [_bash(), fc._to_posix(LANE1), "--card", card, "--session", session,
            "--out-dir", fc._to_posix(out_dir), "--cap", "2", "--max-rate", "9.5"]
    if shape is not None:
        args += ["--shape", shape]
    res = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                         timeout=120, check=False)
    return res, out_dir, state_dir


def _win(out_dir: Path) -> dict:
    return json.loads((out_dir / "window.json").read_text(encoding="utf-8"))


def _calls(state_dir: Path) -> str:
    f = state_dir / "calls.log"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _new_lines(state_dir: Path) -> list[str]:
    return [ln for ln in _calls(state_dir).splitlines() if ln.startswith("CALL new ")]


def _no_uploads(state_dir: Path) -> bool:
    uploads = state_dir / "uploads.log"
    return not uploads.exists() or "UPLOAD_OK" not in uploads.read_text(encoding="utf-8")


def test_a100_shape_high_mem_passes_high_mem_and_records_the_check(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, "A100", "high-mem")
    assert res.returncode == 0, res.stderr[-3000:]
    assert _new_lines(state_dir) == ["CALL new --gpu A100 --high-mem -s sdlab-l1-shape"]
    win = _win(out_dir)
    assert win["status"] == "ok" and win["shape_requested"] == "high-mem"
    assert win["shape_check"] == {"requested": "high-mem", "expected": "High-RAM", "observed": "High-RAM",
                                  "match": True}


def test_g4_shape_standard_does_not_pass_high_mem(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, "G4", "standard")
    assert res.returncode == 0, res.stderr[-3000:]
    assert _new_lines(state_dir) == ["CALL new --gpu G4 -s sdlab-l1-shape"]
    win = _win(out_dir)
    assert win["shape_requested"] == "standard" and win["card"] == "G4"
    assert win["shape_check"]["observed"] == "Standard" and win["shape_check"]["match"] is True


def test_a_gpu_card_without_shape_refuses_before_any_colab_call(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, "G4", None)
    assert res.returncode == 2 and "REFUSED: SHAPE_REQUIRED:" in res.stderr
    assert _calls(state_dir) == "" and not (state_dir / "card.txt").exists()
    assert _win(out_dir)["refusal_code"] == "SHAPE_REQUIRED"


@pytest.mark.parametrize(("bad", "code"), [("High-RAM", "SHAPE_INVALID"), ("hm", "SHAPE_INVALID"),
                                           ("", "SHAPE_REQUIRED")])
def test_a_bad_shape_value_refuses_before_any_colab_call(tmp_path: Path, bad: str, code: str) -> None:
    res, _, state_dir = _lane1(tmp_path, "A100", bad)
    assert res.returncode == 2 and f"REFUSED: {code}:" in res.stderr
    assert _calls(state_dir) == ""


@pytest.mark.parametrize(("card", "shape", "forced", "expected"), [
    # The defect: a G4 asked for Standard and the machine came up High-RAM.
    ("G4", "standard", "High-RAM", "Standard"),
    ("A100", "high-mem", "Standard", "High-RAM"),
])
def test_a_session_row_shape_mismatch_refuses_after_open_and_stops(tmp_path: Path, card: str, shape: str,
                                                                    forced: str, expected: str) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, card, shape, {"FAKE_COLAB_SESSION_SHAPE": forced})
    assert res.returncode != 0
    assert len(_new_lines(state_dir)) == 1
    win = _win(out_dir)
    assert win["refusal_code"] == "SHAPE_MISMATCH" and win["status"] == "SHAPE_MISMATCH"
    assert win["shape_requested"] == shape
    assert win["shape_check"] == {"requested": shape, "expected": expected, "observed": forced, "match": False}
    assert "STOP -s sdlab-l1-shape" in (state_dir / "stops.log").read_text(encoding="utf-8")
    assert _no_uploads(state_dir) and win["rate_check"] is None
    assert f"Shape: {forced}" in (out_dir / "guards.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("fixture", [{"FAKE_COLAB_SESSIONS_EMPTY": "1"}, {"FAKE_COLAB_SESSION_SHAPE": "OMIT"}])
def test_a_session_row_with_no_shape_is_a_mismatch(tmp_path: Path, fixture: dict[str, str]) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, "A100", "high-mem", fixture)
    assert res.returncode != 0
    win = _win(out_dir)
    assert win["refusal_code"] == "SHAPE_MISMATCH" and win["shape_check"]["observed"] is None
    assert "STOP -s sdlab-l1-shape" in (state_dir / "stops.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("card", ["L4", "l4", "V5E1", "V6E1"])
def test_a_single_shape_card_refuses_standard_before_any_colab_call(tmp_path: Path, card: str) -> None:
    res, _, state_dir = _lane1(tmp_path, card, "standard")
    assert res.returncode == 2 and "REFUSED: SHAPE_STANDARD_UNAVAILABLE:" in res.stderr
    assert "client.py:90-95" in res.stderr and _calls(state_dir) == ""


def test_l4_high_mem_expects_high_ram(tmp_path: Path) -> None:
    res, out_dir, state_dir = _lane1(tmp_path, "L4", "high-mem")
    assert res.returncode == 0, res.stderr[-3000:]
    assert _new_lines(state_dir) == ["CALL new --gpu L4 --high-mem -s sdlab-l1-shape"]
    assert _win(out_dir)["shape_check"]["expected"] == "High-RAM"


def test_the_cpu_stub_is_unchanged_and_takes_no_shape(tmp_path: Path) -> None:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out"
    res = subprocess.run([_bash(), fc._to_posix(LANE1), "--out-dir", fc._to_posix(out_dir), "--session", "sdlab-l1-cpu"],
                         env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False)
    assert res.returncode == 0, res.stderr[-2000:]
    assert _new_lines(state_dir) == ["CALL new --high-mem -s sdlab-l1-cpu"]
    win = _win(out_dir)
    assert "shape_requested" in win and win["shape_requested"] is None and win["shape_check"] is None
    assert not (out_dir / "shape_requested.txt").exists() and not (out_dir / "sessions_after_open.txt").exists()

    out2 = tmp_path / "out2"
    res = subprocess.run([_bash(), fc._to_posix(LANE1), "--out-dir", fc._to_posix(out2), "--session", "sdlab-l1-cpu2",
                          "--shape", "standard"],
                         env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False)
    assert res.returncode == 2 and "REFUSED: SHAPE_NOT_FOR_CPU:" in res.stderr
    assert len(_new_lines(state_dir)) == 1


def _source(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([_bash(), "-c", f"set -euo pipefail; source {fc._to_posix(WINDOW_SH)}; {script}"],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False)


def test_open_refuses_a_gpu_card_whose_shape_was_not_armed(tmp_path: Path) -> None:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    env["PY_BIN"] = sys.executable
    res = _source(f"colab_gpu_rate_gate_arm {fc._to_posix(out)} A100 9.5 1; "
                  f"colab_open_session_locked s1 A100 {fc._to_posix(out)}", env)
    assert res.returncode == 2 and "REFUSED: SHAPE_REQUIRED:" in res.stderr, res.stderr
    assert "CALL new" not in _calls(state_dir)


def test_every_lane_arms_the_shape_gate_before_it_opens() -> None:
    for kit in sorted(COLAB_DIR.glob("launch_*.sh")):
        text = kit.read_text(encoding="utf-8")
        if "colab_open_session_locked" not in text:
            continue
        arm = text.find("colab_shape_gate_arm \"")
        opened = text.find("colab_open_session_locked \"")
        assert 0 <= arm < opened, f"{kit.name} opens a window without arming the shape gate first"
        assert "--shape)" in text, f"{kit.name} takes no --shape"
