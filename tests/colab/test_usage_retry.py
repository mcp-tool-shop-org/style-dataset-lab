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

    # Between first_retry_idx and recovered_idx, NO cap check may pass on stale data.
    between_records = _parse_json_lines("\n".join(lines[first_retry_idx:recovered_idx]))
    stale_cap_records = [r for r in between_records if "cap" in r]
    assert stale_cap_records == [], f"stale cap record emitted during retry blind window: {stale_cap_records}"

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


def test_launch_refuses_when_rate_times_t_retry_exceeds_half_margin(tmp_path: Path) -> None:
    """Test 5: at production `T_retry = 111` s on G4 at `10.05/hr`, `rate * (T_retry / 3600) = 0.309875` CCU.
    `--margin 0.60` (`margin / 2 = 0.30 < 0.309875`) refuses at launch before any `colab` call, whereas
    `--margin 1.0` (`margin / 2 = 0.50 >= 0.309875`) passes."""
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
    assert "0.309875" in combined
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
    dry_rec = _parse_json_lines(dry_res.stdout)[-1]
    assert dry_rec["usage_retry_bound_s"] == 111
    assert dry_rec["usage_retry_spend_units"] == 0.309875
    assert dry_rec["usage_retry_half_margin_units"] == 0.5


def test_local_wall_guard_keeps_running_and_trips_during_hung_usage_retry(tmp_path: Path) -> None:
    """Requirement 2d: while `colab usage` is hung inside a long retry sequence (`T_retry = 70` s),
    the local wall guard in `colab_run_exec_with_live_guards` keeps running and trips immediately
    when `wall_s - grace_s` expires."""
    _, _, env = fc.make_fake_colab_env(tmp_path)
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
