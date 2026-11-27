"""Tests for bounded `colab usage` retry, blind-window margin gate, and live guard continuity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "colab"))

import fake_colab as fc  # noqa: E402


def _find_bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    import shutil

    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _to_posix(p: Path) -> str:
    return fc._to_posix(p)


def _run_lane1(args: list[str], env: dict[str, str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_find_bash(), _to_posix(LAUNCHER), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _calls(state_dir: Path) -> list[dict]:
    return [
        json.loads(ln)
        for ln in (state_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _kill_escaped(state_dir: Path) -> None:
    pids_f = state_dir / "escaped_pids.txt"
    if not pids_f.is_file():
        return
    import signal

    for raw in pids_f.read_text(encoding="utf-8").split():
        try:
            os.kill(int(raw), signal.SIGKILL)
        except (OSError, ValueError):
            pass


def _parse_json_lines(text: str) -> list[dict]:
    records: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def test_one_rc124_then_success_carries_on_and_logs_retry_and_recovered(tmp_path: Path) -> None:
    """Test 1: one `rc=124` timeout on `colab usage` then success -> window completes ok and logs both
    `USAGE_POLL_RETRY` and `USAGE_POLL_RECOVERED` in `guards.log`."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_rc124_recover"
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "3.0"
    env["GUARD_POLL_INTERVAL_S"] = "0.4"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    # First post-open `colab usage` hangs -> killed by `colab_run_bounded` timeout with rc=124; second succeeds.
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "hang;ok"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-retry-rc124-ok",
            "--cap",
            "0.10",
            "--margin",
            "0.02",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )

    assert res.returncode == 0, f"expected recovery after one rc=124, got rc={res.returncode}\nstderr={res.stderr}"
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "ok"
    assert window["refusal_code"] is None
    assert window["usage_parse_error"] is None
    assert (out_dir / "lane1_stub_bundle.tar.gz").is_file()
    assert "STOP_COMPLETED" in (out_dir / "stop.log").read_text(encoding="utf-8")

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    retry_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RETRY ")]
    recovered_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RECOVERED ")]
    assert len(retry_lines) == 1, f"expected 1 USAGE_POLL_RETRY line, got: {retry_lines}"
    assert "rc=124" in retry_lines[0]
    assert len(recovered_lines) == 1, f"expected 1 USAGE_POLL_RECOVERED line, got: {recovered_lines}"
    assert "attempt=2/3" in recovered_lines[0]
    assert "REFUSED: COLAB_USAGE_PARSE_FAILED" not in guards_log
    assert all(
        r["cap"].get("code") != "COLAB_USAGE_PARSE_FAILED"
        for r in _parse_json_lines(guards_log)
        if isinstance(r.get("cap"), dict)
    )
    # The closing poll after `colab stop` read the balance, so the end balance is its reading.
    assert window["end_balance_source"] == "closing_poll"
    assert window["closing_usage_error"] is None


def test_three_failures_log_warning_and_window_continues(tmp_path: Path) -> None:
    """Mid-run `colab usage` 3-attempt retry failure is logged cleanly and never kills the window."""
    _, _, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_three_fail"
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "11.0"
    env["GUARD_POLL_INTERVAL_S"] = "0.4"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,2"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "hang;rc=7;hang_ignore_term;ok"
    env["FAKE_COLAB_USAGE_CLOSING"] = "rc=5"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-retry-3fail",
            "--cap",
            "0.10",
            "--margin",
            "0.02",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )

    assert res.returncode == 0, f"expected completion despite usage failure, got rc={res.returncode}\nstderr={res.stderr}"
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "ok" and window["refusal_code"] is None
    assert window.get("usage_retry_bound_s") == 9

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "REFUSED: COLAB_USAGE_PARSE_FAILED" not in guards_log
    assert "MIDRUN_USAGE_WARNING code=COLAB_USAGE_PARSE_FAILED action=logged_continue" in guards_log
    retry_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RETRY ")]
    assert len(retry_lines) == 2, f"expected 2 USAGE_POLL_RETRY lines, got {retry_lines}"
    records = _parse_json_lines(guards_log)
    assert any("cap" in r and "wall" in r for r in records)


def test_real_breach_while_retrying_trips_cap_by_own_rate_elapsed(tmp_path: Path) -> None:
    """While `colab usage` is hung/retrying, local own_rate * elapsed still trips CAP_GUARD_TRIPPED on budget."""
    _, _, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_breach_during_retry"
    env["FAKE_COLAB_MODE"] = "stall"
    env["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env["FAKE_COLAB_GPU_RATE_STR"] = "10.05/hr"
    env["FAKE_COLAB_BALANCE"] = "10.00"
    env["GUARD_POLL_INTERVAL_S"] = "0.35"
    env["SDLAB_TEST_RATE_READ_INTERVAL_S"] = "0.2"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "2"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "2,2"
    env["SDLAB_TEST_DOWNLOAD_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_UPLOAD_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    # Post-open calls 1 & 2 succeed; live poll hangs so in-flight local cap check must trip CAP_GUARD_TRIPPED.
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "ok;ok;hang;hang;ok"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-retry-breach",
            "--card",
            "G4",
            "--shape",
            "standard",
            "--max-rate",
            "10.05",
            "--cap",
            "1.34",
            "--margin",
            "1.25",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )

    assert res.returncode != 0
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "CAP_GUARD_TRIPPED"
    assert window["refusal_code"] == "CAP_GUARD_TRIPPED"
    assert "STOP_COMPLETED" in (out_dir / "stop.log").read_text(encoding="utf-8")
    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "REFUSED: CAP_GUARD_TRIPPED" in guards_log


def test_unparseable_output_then_success_recovers_and_completes_window(tmp_path: Path) -> None:
    """Test 4: `colab usage` exits 0 with unparseable text on attempt 1, then valid text on attempt 2 ->
    logs `USAGE_POLL_RETRY` + `USAGE_POLL_RECOVERED` and completes the window ok."""
    _, _, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_unparseable_recover"
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "3.0"
    env["GUARD_POLL_INTERVAL_S"] = "0.4"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "2"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "unparseable;ok"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-retry-unparseable-ok",
            "--cap",
            "0.10",
            "--margin",
            "0.02",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )

    assert res.returncode == 0, f"expected recovery after unparseable output, got rc={res.returncode}\nstderr={res.stderr}"
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "ok"
    assert window["refusal_code"] is None
    assert window["usage_parse_error"] is None

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    retry_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RETRY ")]
    recovered_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RECOVERED ")]
    assert len(retry_lines) == 1
    assert "rc=0" in retry_lines[0]
    assert len(recovered_lines) == 1
    assert "attempt=2/3" in recovered_lines[0]
    assert "REFUSED: COLAB_USAGE_PARSE_FAILED" not in guards_log
    assert all(
        r["cap"].get("code") != "COLAB_USAGE_PARSE_FAILED"
        for r in _parse_json_lines(guards_log)
        if isinstance(r.get("cap"), dict)
    )


def test_launch_refuses_when_rate_times_blind_interval_exceeds_half_margin(tmp_path: Path) -> None:
    """Test 5: the gate prices the detached loop's cap-check interval, the blind interval
    `T_retry + 2 * poll_s + slack_s = 117` s plus the detached poll lag `2 * (5 + 30) + 10 = 80` s = 197 s
    (sdlab#82). On G4 at `10.05/hr`, `rate * (197 / 3600) = 0.549958` CCU. `--margin 0.60` and `--margin 1.0`
    (`margin / 2 = 0.50 < 0.549958`) refuse at launch before any `colab` call, whereas the GPU default margin
    `1.25` (`0.625 >= 0.549958`) passes. A card at `16.0/hr` refuses at margin 1.0 (`0.875556`)."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_margin_refusal"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-margin-refuse",
            "--card",
            "G4",
            "--shape",
            "standard",
            "--max-rate",
            "10.05",
            "--cap",
            "5.0",
            "--margin",
            "0.60",
            "--wall-s",
            "900",
            "--grace-s",
            "60",
        ],
        env,
        timeout=180,
    )

    assert res.returncode == 2, f"expected exit 2 launch refusal, got rc={res.returncode}\nstderr={res.stderr}"
    combined = res.stdout + res.stderr
    assert "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY" in combined
    assert "0.549958" in combined
    assert not (state_dir / "calls.log").exists(), "window must refuse before any colab CLI call"

    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY"
    assert window["refusal_code"] == "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY"

    # At the old GPU default margin 1.0 on G4 10.05/hr, 0.549958 > 0.50 refuses --dry.
    dry_old = _run_lane1(
        ["--dry", "--card", "G4", "--shape", "standard", "--max-rate", "10.05", "--cap", "5.0", "--margin", "1.0"],
        env,
        timeout=180,
    )
    assert dry_old.returncode == 2, f"expected --margin 1.0 --dry to refuse, got rc={dry_old.returncode}"
    assert "0.549958 units > margin / 2 = 0.5 units" in dry_old.stderr

    # With no --margin a GPU card gets the default 1.25: 0.549958 <= 0.625 passes --dry.
    dry_res = _run_lane1(
        [
            "--dry",
            "--card",
            "G4",
            "--shape",
            "standard",
            "--max-rate",
            "10.05",
            "--cap",
            "5.0",
        ],
        env,
        timeout=180,
    )
    assert dry_res.returncode == 0, f"expected the default-margin --dry to pass, got: {dry_res.stderr}"
    assert "margin: 1.25" in dry_res.stdout
    assert "usage_retry_bound_s (T_retry): 111" in dry_res.stdout
    assert "usage_blind_interval_s (T_retry + 2 * poll_s + slack_s): 117" in dry_res.stdout
    assert "detached_poll_lag_s (2 * (poll_retry_sleep_s + poll_exec_timeout_s) + kill_grace_s): 80" in dry_res.stdout
    assert "cap_check_interval_s (usage_blind_interval_s + detached_poll_lag_s): 197" in dry_res.stdout
    assert "cap_check_interval_bound: 0.549958 (197 / 3600 * 10.05 <= margin/2 0.625)" in dry_res.stdout

    # 16.0/hr at margin 1.0: 16.0 * 197 / 3600 = 0.875556 > 0.5 refuses.
    dry_16 = _run_lane1(
        [
            "--dry",
            "--card",
            "G4",
            "--shape",
            "standard",
            "--max-rate",
            "16.0",
            "--cap",
            "8.0",
            "--margin",
            "1.0",
        ],
        env,
        timeout=180,
    )
    assert dry_16.returncode == 2, f"expected 16.0/hr at margin 1.0 to refuse, got rc={dry_16.returncode}"
    assert "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY" in dry_16.stderr
    assert "0.875556 units > margin / 2 = 0.5 units" in dry_16.stderr
    assert "need --margin >= 1.751112" in dry_16.stderr


def test_local_wall_guard_keeps_running_and_trips_during_hung_usage_retry(tmp_path: Path) -> None:
    """Requirement 2d: while `colab usage` is hung inside a long retry sequence (`T_retry = 70` s),
    the local wall guard in `colab_run_exec_with_live_guards` keeps running and trips immediately
    when `wall_s - grace_s` expires."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_wall_during_retry"
    env["FAKE_COLAB_MODE"] = "wall"
    env["GUARD_POLL_INTERVAL_S"] = "0.3"
    # Long usage poll timeout (15s * 3 + 25s = 70s) and long watcher escalate (30s) so ONLY a live local
    # guard loop (or non-blocked main shell) finishes in a few seconds.
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "15"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "5"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "5,5"
    env["SDLAB_TEST_WALL_ESCALATE_S"] = "30"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "hang;hang;hang"

    t0 = time.monotonic()
    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-wall-during-retry",
            "--cap",
            "0.20",
            "--margin",
            "0.05",
            "--wall-s",
            "7",
            "--grace-s",
            "4",
        ],
        env,
        timeout=180,
    )
    elapsed = time.monotonic() - t0

    assert res.returncode != 0
    assert elapsed < 12.0, f"local wall guard should trip at ~3s without waiting 15s usage timeout (took {elapsed:.2f}s)"
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "WALL_GUARD_TRIPPED"
    assert window["refusal_code"] == "WALL_GUARD_TRIPPED"
    assert window["stop_path"] == "trap"
    assert "STOP_COMPLETED" in (out_dir / "stop.log").read_text(encoding="utf-8")

    # Measured from the live poll's launch (its first `colab usage` call), not from a RETRY line: the
    # wall trip lands while attempt 1 is still hung inside its 15 s timeout, so no RETRY line exists yet.
    calls = _calls(state_dir)
    new_ts = next(c["ts"] for c in calls if c["subcmd"] == "new")
    first_live_usage_ts = next(c["ts"] for c in calls if c["subcmd"] == "usage" and c["ts"] >= new_ts)
    cleanup_started_ts = float((out_dir / "cleanup_started.txt").read_text(encoding="utf-8").strip())
    assert cleanup_started_ts - first_live_usage_ts < 15.0
    assert "USAGE_POLL_RETRY " not in (out_dir / "guards.log").read_text(encoding="utf-8")


def test_failed_closing_poll_keeps_last_live_reading_marked_stale(tmp_path: Path) -> None:
    """F1: the live polls succeed, the window ends ok, `colab stop` runs, and the closing `colab usage`
    really fails (rc=9). window.json keeps the last live reading as `end_balance`, marks it
    `end_balance_source: "stale_after_failed_close"`, and keeps the closing error in
    `closing_usage_error.txt`, apart from the live `usage_parse_error.txt` (which stays absent)."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_closing_fail"
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "2.0"
    env["GUARD_POLL_INTERVAL_S"] = "0.4"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "2"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    env["FAKE_COLAB_USAGE_CLOSING"] = "rc=9"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-closing-fail",
            "--cap",
            "0.10",
            "--margin",
            "0.02",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )

    assert res.returncode == 0, f"expected an ok window, got rc={res.returncode}\nstderr={res.stderr}"
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "ok"

    # The closing poll ran after `colab stop`, exactly once, and failed with rc=9.
    calls = _calls(state_dir)
    stop_ts = next(c["ts"] for c in calls if c["subcmd"] == "stop")
    closing_calls = [c for c in calls if c["subcmd"] == "usage" and c["ts"] > stop_ts]
    assert len(closing_calls) == 1, f"expected 1 closing usage call after stop, got {closing_calls}"
    assert (state_dir / "closing_usage_calls.log").read_text(encoding="utf-8").split() == ["rc=9"]
    live_usage_calls = [c for c in calls if c["subcmd"] == "usage" and c["ts"] < stop_ts]
    assert live_usage_calls, "expected live usage polls before the stop"

    # The last live reading is kept as the end balance, and it is marked stale.
    assert window["end_balance"] == 9.85
    assert window["end_balance_source"] == "stale_after_failed_close"
    closing_err = (out_dir / "closing_usage_error.txt").read_text(encoding="utf-8").strip()
    assert "status 9" in closing_err, f"expected the closing error (status 9), got {closing_err!r}"
    assert window["closing_usage_error"] == closing_err
    # The live error file is separate and untouched: no live poll failed.
    assert not (out_dir / "usage_parse_error.txt").exists()
    assert window["usage_parse_error"] is None


def test_live_poll_in_flight_past_deadline_logs_and_continues(tmp_path: Path) -> None:
    """When an escaped `colab usage` poll passes its in-flight deadline, it is killed and logged
    (`USAGE_POLL_DEADLINE_EXCEEDED ... action=logged_continue`) and never kills the running window."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_poll_deadline"
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "12.0"
    env["GUARD_POLL_INTERVAL_S"] = "0.3"
    # T_retry = 3 * (1 + 1) + 1 + 1 = 8 s; deadline = 8 + 2 = 10 s.
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "escape_hold;ok"
    env["FAKE_COLAB_ESCAPE_HOLD_S"] = "45"

    try:
        res = _run_lane1(
            [
                "--out-dir",
                _to_posix(out_dir),
                "--session",
                "sdlab-l1-poll-deadline",
                "--cap",
                "0.10",
                "--margin",
                "0.02",
                "--wall-s",
                "120",
                "--grace-s",
                "10",
            ],
            env,
            timeout=240,
        )

        assert res.returncode == 0, f"expected ok despite overdue usage poll, got rc={res.returncode}\n{res.stderr}"
        window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
        assert window["status"] == "ok" and window["refusal_code"] is None
        guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
        deadline_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_DEADLINE_EXCEEDED ")]
        assert len(deadline_lines) >= 1, guards_log
        assert "action=logged_continue" in deadline_lines[0]
        assert "REFUSED: COLAB_USAGE_PARSE_FAILED" not in guards_log
    finally:
        _kill_escaped(state_dir)


def test_pre_open_poll_recovers_on_attempt_2(tmp_path: Path) -> None:
    """F5: the pre-open `colab usage` (before `colab new`) fails once (rc=1) and recovers on attempt 2;
    the window opens and completes ok."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_pre_open_recover"
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "2.0"
    env["GUARD_POLL_INTERVAL_S"] = "0.4"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "2"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    # FAKE_COLAB_USAGE_SEQ counts every usage call: call 1 is the pre-open poll's attempt 1.
    env["FAKE_COLAB_USAGE_SEQ"] = "rc=1;ok"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-pre-open-recover",
            "--cap",
            "0.10",
            "--margin",
            "0.02",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )

    assert res.returncode == 0, f"expected recovery, got rc={res.returncode}\nstderr={res.stderr}"
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "ok"
    assert window["usage_parse_error"] is None
    assert window["start_balance"] == 9.85

    calls = _calls(state_dir)
    new_ts = next(c["ts"] for c in calls if c["subcmd"] == "new")
    pre_open_usage = [c for c in calls if c["subcmd"] == "usage" and c["ts"] < new_ts]
    assert len(pre_open_usage) == 2, f"expected the failed attempt and its retry before open, got {len(pre_open_usage)}"

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    retry_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RETRY ")]
    recovered_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RECOVERED ")]
    assert len(retry_lines) == 1 and "attempt=1/3" in retry_lines[0] and "rc=1 " in retry_lines[0]
    assert len(recovered_lines) == 1 and "attempt=2/3" in recovered_lines[0]
    assert "REFUSED:" not in guards_log


def test_post_open_rate_read_recovers_on_attempt_2(tmp_path: Path) -> None:
    """F5: on a GPU window, the first post-open rate read (`colab_read_post_open_rate`) fails once
    (rc=1) and recovers on attempt 2, before any upload or exec; the rate gate reads a stable rate and
    the window completes ok."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_rate_read_recover"
    env["FAKE_COLAB_MODE"] = "setup_phase"
    env["FAKE_COLAB_SETUP_DURATION_S"] = "2.0"
    env["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env["FAKE_COLAB_GPU_RATE_STR"] = "10.05/hr"
    env["GUARD_POLL_INTERVAL_S"] = "0.35"
    env["SDLAB_TEST_RATE_READ_INTERVAL_S"] = "0.2"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "2"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    env["SDLAB_TEST_DOWNLOAD_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_UPLOAD_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    # Post-open usage call 1 is the first rate read's attempt 1.
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "rc=1;ok"

    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            "sdlab-l1-rate-read-recover",
            "--card",
            "G4",
            "--shape",
            "standard",
            "--max-rate",
            "10.05",
            "--cap",
            "2.0",
            "--margin",
            "0.50",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )

    assert res.returncode == 0, f"expected recovery, got rc={res.returncode}\nstderr={res.stderr}"
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "ok"
    assert window["usage_parse_error"] is None

    calls = _calls(state_dir)
    new_ts = next(c["ts"] for c in calls if c["subcmd"] == "new")
    first_exec_ts = next(c["ts"] for c in calls if c["subcmd"] == "exec" and c["ts"] > new_ts)
    first_upload_ts = min((c["ts"] for c in calls if c["subcmd"] == "upload"), default=first_exec_ts)
    post_open_usage = [c for c in calls if c["subcmd"] == "usage" and c["ts"] > new_ts]
    # The failed attempt and its retry are both rate reads: before any upload and before exec.
    assert post_open_usage[1]["ts"] < min(first_exec_ts, first_upload_ts)

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    lines = guards_log.splitlines()
    retry_idx = [i for i, ln in enumerate(lines) if ln.startswith("USAGE_POLL_RETRY ")]
    recovered_idx = [i for i, ln in enumerate(lines) if ln.startswith("USAGE_POLL_RECOVERED ")]
    assert len(retry_idx) == 1 and "attempt=1/3" in lines[retry_idx[0]] and "rc=1 " in lines[retry_idx[0]]
    assert len(recovered_idx) == 1 and "attempt=2/3" in lines[recovered_idx[0]]
    # Both precede the first live guard tick (wall_only or live cap record): the recovery was in the rate read.
    first_live_idx = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("{")
        and (
            '"check": "wall_only"' in ln
            or ('"mode": "live"' in ln and '"cap"' in ln)
        )
    )
    assert recovered_idx[0] < first_live_idx
    assert "REFUSED:" not in guards_log


_PY_WRAPPER = """#!/usr/bin/env bash
# Test wrapper for SDLAB_PYTHON: fails one named Python call made by the launcher and passes the rest
# through. PYWRAP_FAIL=clock fails the live-poll deadline clock check (the -c program that prints
# "OVERDUE "/"OK "); PYWRAP_FAIL=t0 fails the live-poll launch-time read ("# live poll T0").
for a in "$@"; do
  case "$a" in
    *'"OVERDUE "'*) if [ "${PYWRAP_FAIL:-}" = clock ]; then echo clock >> "${PYWRAP_LOG}"; exit 3; fi ;;
    *'# live poll T0'*) if [ "${PYWRAP_FAIL:-}" = t0 ]; then echo t0 >> "${PYWRAP_LOG}"; exit 3; fi ;;
  esac
done
exec "__REAL_PY__" "$@"
"""


def _run_deadline_log_only(tmp_path: Path, fail_mode: str, session: str) -> tuple[Path, Path, Path, subprocess.CompletedProcess[str]]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / f"out_{fail_mode}"
    wrapper = tmp_path / "pywrap.sh"
    wrapper.write_text(_PY_WRAPPER.replace("__REAL_PY__", fc._to_posix(Path(fc._resolve_python()))), encoding="utf-8", newline="\n")
    wrapper.chmod(0o755)
    wrap_log = tmp_path / "pywrap.log"
    env["SDLAB_PYTHON"] = fc._to_posix(wrapper)
    env["PYWRAP_FAIL"] = fail_mode
    env["PYWRAP_LOG"] = fc._to_posix(wrap_log)
    env["FAKE_COLAB_MODE"] = "stall"
    env["GUARD_POLL_INTERVAL_S"] = "0.3"
    # T_retry = 3 * (1 + 1) + 1 + 1 = 8 s; deadline = 10 s.
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "hang;ok"
    res = _run_lane1(
        [
            "--out-dir",
            _to_posix(out_dir),
            "--session",
            session,
            "--cap",
            "0.10",
            "--margin",
            "0.02",
            "--wall-s",
            "18",
            "--grace-s",
            "10",
        ],
        env,
        timeout=240,
    )
    return state_dir, out_dir, wrap_log, res


def _assert_deadline_logged_continued(out_dir: Path, res: subprocess.CompletedProcess[str], reason: str) -> None:
    assert res.returncode != 0
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    # Window runs until WALL_GUARD_TRIPPED rather than failing closed on COLAB_USAGE_PARSE_FAILED.
    assert window["refusal_code"] == "WALL_GUARD_TRIPPED", window
    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "REFUSED: COLAB_USAGE_PARSE_FAILED" not in guards_log
    deadline_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_DEADLINE_EXCEEDED ")]
    assert deadline_lines and f"reason={reason}" in deadline_lines[0] and "action=logged_continue" in deadline_lines[0], deadline_lines


def test_deadline_check_clock_fail_logs_and_continues_to_wall(tmp_path: Path) -> None:
    session = "sdlab-l1-deadline-clock-fail"
    _, out_dir, wrap_log, res = _run_deadline_log_only(tmp_path, "clock", session)
    _assert_deadline_logged_continued(out_dir, res, "clock_check_failed")
    assert "clock" in wrap_log.read_text(encoding="utf-8").split()


def test_deadline_check_missing_launch_time_logs_and_continues_to_wall(tmp_path: Path) -> None:
    session = "sdlab-l1-deadline-no-t0"
    _, out_dir, wrap_log, res = _run_deadline_log_only(tmp_path, "t0", session)
    _assert_deadline_logged_continued(out_dir, res, "launch_time_missing")
    assert "t0" in wrap_log.read_text(encoding="utf-8").split()
