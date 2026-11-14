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


def _run_lane1(args: list[str], env: dict[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
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
        timeout=60,
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


def test_three_failures_trip_parse_failed_within_t_retry_and_keep_last_error(tmp_path: Path) -> None:
    """Test 2: three consecutive failed reads -> trips `COLAB_USAGE_PARSE_FAILED` within `T_retry` and
    preserves the 3rd attempt's error in `usage_parse_error.txt` (not overwritten by post-stop closing poll)."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_three_fail"
    env["FAKE_COLAB_MODE"] = "stall"
    env["GUARD_POLL_INTERVAL_S"] = "0.4"
    # T_retry = 3 * (1 + 1) + 1 + 2 = 9 s
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,2"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "hang;rc=7;hang_ignore_term"
    # The closing poll after `colab stop` fails as well (rc=5), so the check below that it does not
    # clobber the live error is a real one: the fake ignores FAKE_COLAB_USAGE_POST_OPEN_SEQ once
    # stops.log exists, which made the closing poll always succeed before.
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
        timeout=60,
    )

    assert res.returncode != 0
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "COLAB_USAGE_PARSE_FAILED"
    assert window["refusal_code"] == "COLAB_USAGE_PARSE_FAILED"
    assert window.get("usage_retry_bound_s") == 9
    # Blind interval reported: T_retry 9 + 2 * poll_s 0.4 + slack 2 = 11.8 s; deadline 9 + 2 = 11 s.
    assert window["usage_blind_interval_s"] == 11.8
    assert window["usage_poll_deadline_s"] == 11
    assert window["guard_poll_interval_s"] == 0.4
    assert window["usage_decision_slack_s"] == 2

    # Verify the 3-attempt sequence completed and tripped cleanup within T_retry = 9 s (allowing <=1.5s rig poll jitter).
    calls = [
        json.loads(ln)
        for ln in (state_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    new_ts = next(c["ts"] for c in calls if c["subcmd"] == "new")
    post_open_usage_calls = [c for c in calls if c["subcmd"] == "usage" and c["ts"] >= new_ts]
    # 3 live retry attempts + 1 best-effort closing poll after `colab stop`
    stop_ts = next(c["ts"] for c in calls if c["subcmd"] == "stop")
    live_usage_calls = [c for c in post_open_usage_calls if c["ts"] < stop_ts]
    assert len(live_usage_calls) == 3, f"expected 3 live usage attempts, got {len(live_usage_calls)}"
    cleanup_started_ts = float((out_dir / "cleanup_started.txt").read_text(encoding="utf-8").strip())
    blind_duration_s = cleanup_started_ts - live_usage_calls[0]["ts"]
    assert blind_duration_s <= 9.0 + 1.5, f"expected trip within T_retry=9s (+poll), got {blind_duration_s:.3f}s"

    # Last error (attempt 3: SIGKILL rc=137) is kept in usage_parse_error.txt and window.json.
    err_txt = (out_dir / "usage_parse_error.txt").read_text(encoding="utf-8").strip()
    assert "status 137" in err_txt, f"expected last attempt error (status 137), got {err_txt!r}"
    assert window["usage_parse_error"] == err_txt

    # The closing poll really ran after `colab stop` and really failed (rc=5). Its error is kept in
    # its own file and did not overwrite the live one.
    closing_calls = [c for c in calls if c["subcmd"] == "usage" and c["ts"] > stop_ts]
    assert len(closing_calls) == 1, f"expected 1 closing usage call after stop, got {closing_calls}"
    assert (state_dir / "closing_usage_calls.log").read_text(encoding="utf-8").split() == ["rc=5"]
    closing_err = (out_dir / "closing_usage_error.txt").read_text(encoding="utf-8").strip()
    assert "status 5" in closing_err, f"expected the closing error (status 5), got {closing_err!r}"
    assert window["closing_usage_error"] == closing_err
    assert "status 5" not in err_txt
    # The final live failure unlinked end_balance.txt, so there is no reading to mark stale.
    assert window["end_balance"] is None
    assert window["end_balance_source"] is None

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    retry_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RETRY ")]
    recovered_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_RECOVERED ")]
    assert len(retry_lines) == 2, f"expected 2 USAGE_POLL_RETRY lines, got {retry_lines}"
    assert "attempt=1/3" in retry_lines[0] and "rc=124" in retry_lines[0]
    assert "attempt=2/3" in retry_lines[1] and "rc=7" in retry_lines[1]
    assert len(recovered_lines) == 0

    # No stale cap pass while retrying during live mode, and local wall/RAM/vitals guards kept running.
    records = _parse_json_lines(guards_log)
    live_cap_passes = [
        r for r in records if isinstance(r.get("cap"), dict) and r["cap"].get("mode") == "live" and not r["cap"].get("tripped")
    ]
    assert live_cap_passes == [], f"expected zero live cap passes during failed retries, got {live_cap_passes}"
    wall_only_checks = [r for r in records if r.get("check") == "wall_only"]
    assert len(wall_only_checks) >= 2, f"expected local wall guard ticks during retries, got {wall_only_checks}"


def test_real_breach_while_retrying_has_no_stale_pass_and_trips_cap_under_budget(tmp_path: Path) -> None:
    """Test 3: balance burns across `effective_trip` while `colab usage` retries -> zero stale cap passes
    during retries, and the first good reading (`attempt=3/3`) immediately trips `CAP_GUARD_TRIPPED` with
    total spend strictly within `cap`."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_breach_during_retry"
    env["FAKE_COLAB_MODE"] = "stall"
    env["FAKE_COLAB_PRE_OPEN_RATE_STR"] = "0.00/hr"
    env["FAKE_COLAB_GPU_RATE_STR"] = "10.05/hr"
    env["FAKE_COLAB_BALANCE"] = "10.00"
    env["FAKE_COLAB_BURN_BALANCE"] = "1"
    # 0.08 CCU/s burn so ~3.5 s of retries burns ~0.28 CCU (> effective_trip ~0.23, well below cap=0.80).
    env["FAKE_COLAB_BURN_RATE_CCU_PER_H"] = "288.0"
    env["GUARD_POLL_INTERVAL_S"] = "0.35"
    env["SDLAB_TEST_RATE_READ_INTERVAL_S"] = "0.2"
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    env["SDLAB_TEST_DOWNLOAD_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_UPLOAD_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    # Post-open usage calls 1 & 2 are `colab_read_post_open_rate` (both ok -> stable 10.05/hr).
    # Live poll 1 makes attempts 1 (hang -> rc=124), 2 (rc=1), and 3 (ok -> reads burned balance).
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "ok;ok;hang;rc=1;ok"

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
            "0.80",
            "--margin",
            "0.50",
            "--wall-s",
            "120",
            "--grace-s",
            "10",
        ],
        env,
        timeout=60,
    )

    assert res.returncode != 0
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "CAP_GUARD_TRIPPED"
    assert window["refusal_code"] == "CAP_GUARD_TRIPPED"
    assert "STOP_COMPLETED" in (out_dir / "stop.log").read_text(encoding="utf-8")

    total_spend = round(float(window["start_balance"]) - float(window["end_balance"]), 6)
    assert total_spend >= float(window["effective_trip_units"]), (
        f"expected spend {total_spend} >= effective_trip {window['effective_trip_units']}"
    )
    assert total_spend <= float(window["cap"]), (
        f"spend {total_spend} exceeded cap {window['cap']}"
    )

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    lines = guards_log.splitlines()
    first_retry_idx = next(i for i, ln in enumerate(lines) if ln.startswith("USAGE_POLL_RETRY "))
    recovered_idx = next(i for i, ln in enumerate(lines) if ln.startswith("USAGE_POLL_RECOVERED "))
    assert "attempt=3/3" in lines[recovered_idx]
    # The blind window opens when the live poll is launched, not at its first RETRY line: attempt 1
    # hangs for its whole timeout before that line is written.
    launch_idx = max(
        i for i, ln in enumerate(lines[:first_retry_idx]) if ln.startswith("USAGE_POLL_LAUNCHED ")
    )
    assert launch_idx < first_retry_idx

    # From poll launch to recovered_idx, NO cap check may pass on stale data.
    between_records = _parse_json_lines("\n".join(lines[launch_idx:recovered_idx]))
    stale_cap_records = [r for r in between_records if "cap" in r]
    assert stale_cap_records == [], f"stale cap record emitted during retry blind window: {stale_cap_records}"
    # The window held the wall-only ticks of the hung attempt (the loop kept running).
    assert any(r.get("check") == "wall_only" for r in between_records)

    # And the very first live cap record after USAGE_POLL_RECOVERED trips CAP_GUARD_TRIPPED.
    after_records = [r for r in _parse_json_lines("\n".join(lines[recovered_idx + 1 :])) if "cap" in r]
    assert after_records, "expected cap evaluation immediately after USAGE_POLL_RECOVERED"
    assert after_records[0]["cap"]["tripped"] is True
    assert after_records[0]["cap"]["code"] == "CAP_GUARD_TRIPPED"


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
        timeout=60,
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
    """Test 5: the gate prices the blind interval `T_retry + 2 * poll_s + slack_s = 111 + 4 + 2 = 117` s,
    not `T_retry` alone. On G4 at `10.05/hr`, `rate * (117 / 3600) = 0.326625` CCU.
    `--margin 0.60` (`margin / 2 = 0.30 < 0.326625`) refuses at launch before any `colab` call, whereas
    `--margin 1.0` (`margin / 2 = 0.50 >= 0.326625`) passes. A card at `16.0/hr` fitted margin 1.0 under
    `T_retry` alone (`0.493333`) but not under the blind interval (`0.52`), so it refuses."""
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
        timeout=30,
    )

    assert res.returncode == 2, f"expected exit 2 launch refusal, got rc={res.returncode}\nstderr={res.stderr}"
    combined = res.stdout + res.stderr
    assert "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY" in combined
    assert "0.326625" in combined
    assert not (state_dir / "calls.log").exists(), "window must refuse before any colab CLI call"

    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY"
    assert window["refusal_code"] == "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY"

    # At margin 1.0 on G4 10.05/hr, 0.309875 <= 0.50 passes --dry.
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
            "--margin",
            "1.0",
        ],
        env,
        timeout=30,
    )
    assert dry_res.returncode == 0, f"expected --margin 1.0 --dry to pass, got: {dry_res.stderr}"
    assert "usage_retry_bound_s (T_retry): 111" in dry_res.stdout
    assert "usage_blind_interval_s (T_retry + 2 * poll_s + slack_s): 117" in dry_res.stdout
    assert "usage_retry_blind_bound: 0.326625 (117 / 3600 * 10.05 <= margin/2 0.5)" in dry_res.stdout

    # 16.0/hr at margin 1.0: 16.0 * 117 / 3600 = 0.52 > 0.5 refuses (it fitted at 111 s: 0.493333).
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
        timeout=30,
    )
    assert dry_16.returncode == 2, f"expected 16.0/hr at margin 1.0 to refuse, got rc={dry_16.returncode}"
    assert "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY" in dry_16.stderr
    assert "0.52 units > margin / 2 = 0.5 units" in dry_16.stderr
    assert "need --margin >= 1.04" in dry_16.stderr


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
        timeout=30,
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
        timeout=60,
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


def test_live_poll_in_flight_past_deadline_fails_closed(tmp_path: Path) -> None:
    """F3: the live `colab usage` spawns a child that escapes `timeout` (its own session) and holds
    stdout, so the poll's `$(...)` never returns. Once the poll has been in flight past
    `T_retry + slack` (8 + 2 = 10 s), the cap guard fails closed with `COLAB_USAGE_PARSE_FAILED`
    and the window stops its own session only. Without the deadline the cap would never be read again
    and the window would run on until the wall guard (20 s here)."""
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_poll_deadline"
    env["FAKE_COLAB_MODE"] = "stall"
    env["GUARD_POLL_INTERVAL_S"] = "0.3"
    # T_retry = 3 * (1 + 1) + 1 + 1 = 8 s; deadline = 8 + 2 = 10 s.
    env["SDLAB_TEST_USAGE_POLL_TIMEOUT_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_KILL_GRACE_S"] = "1"
    env["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "1,1"
    env["SDLAB_TEST_STOP_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_SESSIONS_TIMEOUT_S"] = "5"
    env["SDLAB_TEST_KILL_GRACE_S"] = "1"
    env["FAKE_COLAB_USAGE_POST_OPEN_SEQ"] = "escape_hold"
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
                "30",
                "--grace-s",
                "10",
            ],
            env,
            timeout=60,
        )

        # The escaped child really escaped: it outlived the poll, the window and its kill tree.
        escaped = [int(x) for x in (state_dir / "escaped_pids.txt").read_text(encoding="utf-8").split()]
        assert len(escaped) == 1
        os.kill(escaped[0], 0)

        assert res.returncode != 0
        window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
        assert window["status"] == "COLAB_USAGE_PARSE_FAILED", f"got {window['status']}"
        assert window["refusal_code"] == "COLAB_USAGE_PARSE_FAILED"
        assert window["usage_poll_deadline_s"] == 10
        assert "past its deadline of 10 s" in window["usage_parse_error"]

        guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
        deadline_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_DEADLINE_EXCEEDED ")]
        assert len(deadline_lines) == 1, deadline_lines
        assert "deadline_s=10 " in deadline_lines[0]
        # Attempt 1 never returned, so no RETRY line and no live cap pass.
        assert "USAGE_POLL_RETRY " not in guards_log
        records = _parse_json_lines(guards_log)
        live_cap = [r for r in records if isinstance(r.get("cap"), dict) and r["cap"].get("mode") == "live"]
        assert live_cap and all(r["cap"]["tripped"] for r in live_cap), live_cap
        assert live_cap[-1]["cap"]["code"] == "COLAB_USAGE_PARSE_FAILED"

        # It tripped at the deadline measured from poll launch (the first live usage call), not later.
        calls = _calls(state_dir)
        new_ts = next(c["ts"] for c in calls if c["subcmd"] == "new")
        stop_calls = [c for c in calls if c["subcmd"] == "stop"]
        live_usage = [c for c in calls if c["subcmd"] == "usage" and new_ts <= c["ts"] < stop_calls[0]["ts"]]
        assert len(live_usage) == 1, f"expected the one hung live usage call, got {len(live_usage)}"
        # The launcher's own clock: in flight past the 10 s deadline, measured from the poll's launch.
        in_flight_s = float(deadline_lines[0].split("in_flight_s=", 1)[1].split()[0])
        assert 10.0 < in_flight_s <= 10.0 + 1.5, f"in flight {in_flight_s:.3f}s at the trip"
        # The fake's clock: its call record lands a Python start-up after the launch (about 0.15 s on
        # the rig), so allow 0.5 s below the deadline; above it, one tick plus the trip's guard runs.
        cleanup_started_ts = float((out_dir / "cleanup_started.txt").read_text(encoding="utf-8").strip())
        tripped_after_s = cleanup_started_ts - live_usage[0]["ts"]
        assert 10.0 - 0.5 <= tripped_after_s <= 10.0 + 2.5, f"tripped {tripped_after_s:.3f}s after poll launch"

        # Only its own session was stopped.
        assert {c["parsed_opts"]["-s"][-1] for c in stop_calls} == {"sdlab-l1-poll-deadline"}
        assert "STOP_COMPLETED" in (out_dir / "stop.log").read_text(encoding="utf-8")
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
        timeout=60,
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
        timeout=60,
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


def _run_deadline_fail_closed(tmp_path: Path, fail_mode: str, session: str) -> tuple[Path, Path, Path, subprocess.CompletedProcess[str]]:
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
    # Live poll 1: attempt 1 hangs (in flight for about 1 s), attempt 2 reads fine. Without a fail-closed
    # deadline check the poll recovers, the cap passes, and the stalled window runs to its wall trip.
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
            "30",
            "--grace-s",
            "10",
        ],
        env,
        timeout=60,
    )
    return state_dir, out_dir, wrap_log, res


def _assert_deadline_failed_closed(state_dir: Path, out_dir: Path, res: subprocess.CompletedProcess[str], reason: str, session: str, err_part: str) -> None:
    assert res.returncode != 0
    window = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert window["status"] == "COLAB_USAGE_PARSE_FAILED", f"got {window['status']}"
    assert window["refusal_code"] == "COLAB_USAGE_PARSE_FAILED"
    assert err_part in window["usage_parse_error"], window["usage_parse_error"]

    guards_log = (out_dir / "guards.log").read_text(encoding="utf-8")
    deadline_lines = [ln for ln in guards_log.splitlines() if ln.startswith("USAGE_POLL_DEADLINE_EXCEEDED ")]
    assert len(deadline_lines) == 1, deadline_lines
    assert deadline_lines[0].endswith(f" reason={reason}"), deadline_lines[0]
    assert "in_flight_s=unknown " in deadline_lines[0]
    # The poll was failed closed while in flight: attempt 1 never came back, so no RETRY line.
    assert "USAGE_POLL_RETRY " not in guards_log
    records = _parse_json_lines(guards_log)
    live_cap = [r for r in records if isinstance(r.get("cap"), dict) and r["cap"].get("mode") == "live"]
    assert live_cap and all(r["cap"]["tripped"] for r in live_cap), live_cap
    assert live_cap[-1]["cap"]["code"] == "COLAB_USAGE_PARSE_FAILED"

    # It fired on the first in-flight tick, long before the 10 s deadline, measured from poll launch.
    calls = _calls(state_dir)
    new_ts = next(c["ts"] for c in calls if c["subcmd"] == "new")
    stop_calls = [c for c in calls if c["subcmd"] == "stop"]
    live_usage = [c for c in calls if c["subcmd"] == "usage" and new_ts <= c["ts"] < stop_calls[0]["ts"]]
    assert len(live_usage) == 1, f"expected only the hung attempt 1, got {len(live_usage)}"
    cleanup_started_ts = float((out_dir / "cleanup_started.txt").read_text(encoding="utf-8").strip())
    assert cleanup_started_ts - live_usage[0]["ts"] < 5.0

    # Only its own session was stopped.
    assert {c["parsed_opts"]["-s"][-1] for c in stop_calls} == {session}
    assert "STOP_COMPLETED" in (out_dir / "stop.log").read_text(encoding="utf-8")


def test_deadline_check_fails_closed_when_its_clock_check_fails(tmp_path: Path) -> None:
    """Fail-closed (a): with a live poll in flight, the deadline's clock check exits non-zero (SDLAB_PYTHON
    is a wrapper that fails that one Python call). The check counts the poll overdue, logs
    `reason=clock_check_failed`, and the cap guard fails closed with `COLAB_USAGE_PARSE_FAILED`; only the
    window's own session is stopped. Before the fix the failed check read as "OK 0" and never fired."""
    session = "sdlab-l1-deadline-clock-fail"
    state_dir, out_dir, wrap_log, res = _run_deadline_fail_closed(tmp_path, "clock", session)
    _assert_deadline_failed_closed(state_dir, out_dir, res, "clock_check_failed", session, "deadline check on the live colab usage poll failed")
    # The wrapper really failed the clock check, at least once.
    assert "clock" in wrap_log.read_text(encoding="utf-8").split()


def test_deadline_check_fails_closed_when_poll_launch_time_is_missing(tmp_path: Path) -> None:
    """Fail-closed (b): the live poll is launched (PID set) but its launch-time read fails, so T0 is empty.
    The deadline check counts the poll overdue, logs `reason=launch_time_missing`, and the cap guard fails
    closed with `COLAB_USAGE_PARSE_FAILED`; only the window's own session is stopped. Before the fix a set
    PID with an empty T0 returned OK and the deadline never fired."""
    session = "sdlab-l1-deadline-no-t0"
    state_dir, out_dir, wrap_log, res = _run_deadline_fail_closed(tmp_path, "t0", session)
    _assert_deadline_failed_closed(state_dir, out_dir, res, "launch_time_missing", session, "no recorded launch time")
    # The wrapper really failed the launch-time read.
    assert "t0" in wrap_log.read_text(encoding="utf-8").split()
