"""Slowed-runner proof tests for the fake-Colab probe and Lane 1 rate-guard suites."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

COLAB_TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = COLAB_TESTS_DIR / "fixtures"
for _p in (FIXTURES_DIR, COLAB_TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import test_chunked_transfer_and_probe as t_probe  # noqa: E402
import test_launch_lane1_stub as t_l1  # noqa: E402


def _assert_shim_recorded_both(state_dirs: list[Path]) -> None:
    assert state_dirs, "expected at least one fake_colab state directory under slow_runner_shim"
    combined = "\n".join(
        (sd / "slow_shim.log").read_text(encoding="utf-8")
        for sd in state_dirs
        if (sd / "slow_shim.log").is_file()
    )
    assert "FAKE_COLAB " in combined, f"slow shim never wrapped `colab`: {combined!r}"
    assert "GUARD_PY " in combined, f"slow shim never wrapped guard/rig python: {combined!r}"


# Per-call delays are calibrated against each named test's d00ecbdc subprocess timeout:
# the single-window probe runs 20 fake-colab + 23 guard calls against timeout=120 (~143 s at 4.0/2.5 s),
# while the 6-window Lane 1 rate test exceeds timeout=30 per window at 1.0/1.5 s (~44 s on Sub-run 1).
def test_slow_runner_shim_probe_upload_limit(
    tmp_path: Path, slow_runner_shim: Callable[..., list[Path]]
) -> None:
    states = slow_runner_shim(colab_delay_s=4.0, guard_python_delay_s=2.5)
    t_probe.test_probe_upload_limit_sweeps_both_directions_stops_at_first_500_and_stops_session(tmp_path)
    _assert_shim_recorded_both(states)


def test_slow_runner_shim_pre_open_zero_rate_and_post_open_rate(
    tmp_path: Path, slow_runner_shim: Callable[..., list[Path]]
) -> None:
    states = slow_runner_shim(colab_delay_s=1.0, guard_python_delay_s=1.5, extra_modules=(t_l1,))
    t_l1.test_pre_open_zero_rate_does_not_lower_configured_and_post_open_rate_is_used(tmp_path)
    _assert_shim_recorded_both(states)
