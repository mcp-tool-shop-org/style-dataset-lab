"""The detached poll loop's guards during a remote-poll outage (sdlab#82 fix 2).

Most cases drive the real `colab_run_exec_with_live_guards` loop from `scripts/colab/colab_window.sh`
through a small bash driver, with the fake `colab` CLI and a fake VM worker: the out dir's balance and
rate files can then be set exactly, and no independent wall watcher races the loop's own wall check.
The lost-start-reply crash and the exported-knob cases run the real Lane 1 launcher.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
sys.path.insert(0, str(COLAB_DIR))

import fake_colab as fc  # noqa: E402
import launch_guards as lg  # noqa: E402

DRIVER = r"""#!/usr/bin/env bash
set -euo pipefail
source "${DRV_COLAB_DIR}/colab_window.sh"
colab_apply_test_cleanup_overrides 1
colab_compute_cleanup_bounds render
printf '%s\n' "${COLAB_CAP_CHECK_INTERVAL_S}" > "${DRV_OUT_DIR}/drv_cap_check_interval_s.txt"
if [ "${DRV_CARD_CLASS}" = "__unset__" ]; then unset COLAB_CARD_CLASS; else export COLAB_CARD_CLASS="${DRV_CARD_CLASS}"; fi
if [ "${DRV_UNSET_CLEANUP_BOUND:-0}" = "1" ]; then unset COLAB_CLEANUP_BOUND_S; fi
colab_run_exec_with_live_guards \
  "${DRV_PY}" "${DRV_COLAB_DIR}/launch_guards.py" drv-session "${DRV_COLAB_DIR}/remote_runner.py" \
  "$(date -u +%s)" "${DRV_WALL_S}" "${DRV_GRACE_S}" "${DRV_CAP}" "${DRV_MARGIN}" "${DRV_OUT_DIR}" \
  "SDLAB_REMOTE_SCRIPT=/content/drv_worker.sh"
echo "DRV_LOOP_RETURNED_0"
"""

WORKER = r"""#!/usr/bin/env bash
for i in $(seq 1 600); do
  echo "=== VITALS $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "CGROUP_MEM_CURRENT: 536870912"
  echo "CGROUP_MEM_MAX: 12884901888"
  echo "CGROUP_MEM: oom_kill 0"
  echo "CGROUP_MEM_STAT: anon 268435456"
  echo "CGROUP_MEM_STAT: file 268435456"
  echo "CGROUP_MEM_STAT: shmem 0"
  echo "MEM: MemTotal:       12582912 kB"
  echo "MEM: MemAvailable:   11534336 kB"
  echo "MEM: AnonPages:        262144 kB"
  echo "MEM: Shmem:                 0 kB"
  echo "SETUP_BYTES: ${i}"
  echo "PROC:"
  echo 'HARNESS: {"phase": "setup"}'
  echo "DRV_ROW ${i}"
  sleep 0.1
done
exit 0
"""


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    return str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")


def _records(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        if line.startswith("{"):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def _live_within_cap_passes(guards: str) -> list[dict]:
    """Cap records that read as a fresh within-cap pass: `"mode": "live"` and not tripped."""
    return [
        r for r in _records(guards)
        if isinstance(r.get("cap"), dict) and r["cap"].get("mode") == "live" and r["cap"].get("tripped") is False
    ]


def _drive(
    tmp_path: Path,
    *,
    card_class: str = "cpu",
    open_ago_s: float = 5.0,
    start_balance: str | None = "9.85",
    end_balance: str | None = "9.85",
    rate: str | None = "0.26",
    wall_s: float = 3000.0,
    grace_s: float = 60.0,
    cap: float = 5.0,
    margin: float = 0.02,
    extra_env: dict[str, str] | None = None,
    timeout: int = 180,
    end_balance_age_s: float | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path / "drv")
    content_dir = state_dir / "content"
    shutil.copyfile(COLAB_DIR / "launch_guards.py", content_dir / "launch_guards.py")
    (content_dir / "drv_worker.sh").write_text(WORKER, encoding="utf-8", newline="\n")
    (state_dir / "session_opened.txt").write_text("1\n", encoding="utf-8", newline="\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "guards.log").write_text("", encoding="utf-8")
    (out_dir / "session_opened.txt").write_text("1\n", encoding="utf-8", newline="\n")
    (out_dir / "session_open_epoch.txt").write_text(f"{time.time() - open_ago_s:.6f}\n", encoding="utf-8", newline="\n")
    for name, val in (("start_balance.txt", start_balance), ("end_balance.txt", end_balance),
                      ("rate_for_projection.txt", rate)):
        if val is not None:
            (out_dir / name).write_text(f"{val}\n", encoding="utf-8", newline="\n")
    if end_balance_age_s is not None and end_balance is not None:
        aged = time.time() - end_balance_age_s
        os.utime(out_dir / "end_balance.txt", (aged, aged))
    driver = tmp_path / "drv_loop.sh"
    driver.write_text(DRIVER, encoding="utf-8", newline="\n")
    env.update({
        "DRV_COLAB_DIR": fc._to_posix(COLAB_DIR),
        "DRV_PY": fc._to_posix(Path(sys.executable)),
        "DRV_CARD_CLASS": card_class,
        "DRV_OUT_DIR": fc._to_posix(out_dir),
        "DRV_WALL_S": str(wall_s),
        "DRV_GRACE_S": str(grace_s),
        "DRV_CAP": str(cap),
        "DRV_MARGIN": str(margin),
        "GUARD_POLL_INTERVAL_S": "0.2",
        "SDLAB_TEST_POLL_RETRY_SLEEP_S": "0.2",
        "SDLAB_TEST_POLL_MAX_RETRIES": "1000",
        "STALL_S": "60",
    })
    env.update(extra_env or {})
    try:
        res = subprocess.run(
            [_bash(), fc._to_posix(driver)],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        lg.stop_detached_worker(content_dir, sig=9)
    return res, out_dir, state_dir


def _guards(out_dir: Path) -> str:
    return (out_dir / "guards.log").read_text(encoding="utf-8")


def test_offline_cap_trip_during_outage_is_trip_only_and_never_a_live_pass(tmp_path: Path) -> None:
    # Every poll fails, so no usage read is ever launched: only the offline guard runs. Priced at 36/h
    # (0.01 units/s) with the ceiling at 1.2 units, the projection trips at elapsed 120 s; the session
    # opened 116 s ago. reserve = 450 s * 36/h = 4.5, so cap = 0.02 + 4.5 + 1.2.
    res, out_dir, _ = _drive(
        tmp_path,
        open_ago_s=116.0,
        rate="36",
        cap=5.72,
        extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all"},
    )
    guards = _guards(out_dir)
    assert res.returncode == 91, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    recs = _records(guards)
    offline = [r for r in recs if r.get("check") == "offline_cap"]
    assert offline, guards
    assert offline[-1]["cap"]["tripped"] is True
    assert offline[-1]["cap"]["code"] == "CAP_GUARD_TRIPPED"
    assert offline[-1]["cap"]["projected_spend_ccu"] >= offline[-1]["cap"]["ceiling_ccu"] == 1.2
    for r in offline[:-1]:
        assert r["cap"]["mode"] == "live_offline"
        assert r["cap"]["balance_source"] == "cached"
        assert r["cap"]["fresh_pass"] is False
        assert r["cap"]["result"] == "no_trip_projection"
        assert isinstance(r["cap"]["balance_age_s"], float)
    assert _live_within_cap_passes(guards) == []
    assert re.search(r"^REFUSED: CAP_GUARD_TRIPPED: offline cap projection: ", guards, re.M), guards
    # Every failed poll is followed by the wall, then the cap projection, then RAM, before the next poll.
    lines = guards.splitlines()
    retry_idx = [i for i, ln in enumerate(lines) if ln.startswith("DETACHED_POLL_RETRY ")]
    assert len(retry_idx) >= 2
    for a, b in zip(retry_idx, retry_idx[1:] + [len(lines)]):
        block = _records("\n".join(lines[a + 1 : b]))
        kinds = [r.get("check") for r in block]
        assert kinds[:2] == ["wall_only", "offline_cap"], (kinds, lines[a:b])
        assert block[0].get("checkpoint") == "offline"
        if not block[1]["cap"]["tripped"]:
            assert kinds[2] == "host_ram", kinds


def test_offline_wall_trip_uses_a_clock_read_after_the_failed_poll(tmp_path: Path) -> None:
    # Each failed poll takes 1.5 s. The wall threshold (wall - grace = 30 s) is crossed during a poll:
    # the trip must come on the first failed poll that ENDS past the threshold, on a clock read after it.
    res, out_dir, state_dir = _drive(
        tmp_path,
        open_ago_s=26.0,
        wall_s=40.0,
        grace_s=10.0,
        extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "FAKE_COLAB_POLL_FAIL_DELAY_S": "1.5"},
    )
    guards = _guards(out_dir)
    assert res.returncode == 91, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    assert re.search(r"^REFUSED: WALL_GUARD_TRIPPED: ", guards, re.M), guards
    open_epoch = float((out_dir / "session_open_epoch.txt").read_text(encoding="utf-8").strip())
    events = [json.loads(ln) for ln in (state_dir / "poll_events.jsonl").read_text(encoding="utf-8").splitlines()]
    # The first wall record after each failed poll (`DETACHED_POLL_RETRY`) is that pass's wall check.
    lines = guards.splitlines()
    retry_idx = [i for i, ln in enumerate(lines) if ln.startswith("DETACHED_POLL_RETRY ")]
    walls = []
    for a, b in zip(retry_idx, retry_idx[1:] + [len(lines)]):
        walls.append(next(r for r in _records("\n".join(lines[a + 1 : b])) if isinstance(r.get("wall"), dict)))
    assert len(walls) == len(events), (len(walls), len(events), guards)
    for ev, w in zip(events, walls):
        clock_epoch = open_epoch + (w["wall"]["threshold_s"] - w["wall"]["remaining_s"])
        assert clock_epoch >= ev["end"] - 0.05, ("wall clock read before the failed poll ended", ev, w)
    assert all(w.get("check") == "wall_only" and w.get("checkpoint") == "offline" for w in walls), walls
    first_past = next(i for i, ev in enumerate(events) if ev["end"] - open_epoch >= 30.0)
    assert walls[first_past]["wall"]["tripped"] is True
    assert len(events) == first_past + 1, "the wall tripped one poll late"


def test_usage_read_followed_during_outage_trips_cap_on_its_own_result(tmp_path: Path) -> None:
    # Poll 1 succeeds and launches a usage read that takes 1.5 s; polls 2+ fail. The read finishes during
    # the outage and is reaped by the launch=0 follow tick: its own balance (8.0 against 9.85) trips the cap.
    res, out_dir, _ = _drive(
        tmp_path,
        cap=1.0525,
        extra_env={
            "FAKE_COLAB_POLL_FAIL_CALLS": ",".join(str(n) for n in range(2, 400)),
            "FAKE_COLAB_USAGE_DELAY_S": "1.5",
            "FAKE_COLAB_BALANCE": "8.0",
        },
    )
    guards = _guards(out_dir)
    assert res.returncode == 91, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    lines = guards.splitlines()
    first_retry = next(i for i, ln in enumerate(lines) if ln.startswith("DETACHED_POLL_RETRY attempt=1/"))
    after = _records("\n".join(lines[first_retry:]))
    trips = [r for r in after if isinstance(r.get("cap"), dict) and r["cap"].get("mode") == "live" and r["cap"]["tripped"]]
    assert trips, guards
    assert trips[0]["cap"]["code"] == "CAP_GUARD_TRIPPED"
    assert trips[0]["cap"]["spend_ccu"] == 1.85
    # While the read was in flight the outage passes were wall-only: no offline projection, no live pass.
    assert not [r for r in after if r.get("check") == "offline_cap"], guards
    assert [r for r in after if r.get("check") == "wall_only"], guards
    assert _live_within_cap_passes("\n".join(lines[first_retry:])) == []
    assert re.search(r"^REFUSED: CAP_GUARD_TRIPPED: ", guards, re.M), guards


def test_offline_guard_missing_balance_files_fail_closed(tmp_path: Path) -> None:
    res, out_dir, _ = _drive(
        tmp_path,
        end_balance=None,
        extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "STALL_S": "30"},
    )
    guards = _guards(out_dir)
    assert res.returncode == 91, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    assert re.search(r"^REFUSED: COLAB_USAGE_PARSE_FAILED: offline guard: start_balance.txt or end_balance.txt missing", guards, re.M), guards
    assert "POLL_RECONNECT_EXHAUSTED" not in guards
    recs = _records(guards)
    assert recs and recs[-1].get("check") == "wall_only" and recs[-1].get("checkpoint") == "offline"
    assert "offline guard" in (out_dir / "usage_parse_error.txt").read_text(encoding="utf-8")


def test_offline_guard_gpu_window_without_rate_file_refuses_rate_unread(tmp_path: Path) -> None:
    res, out_dir, _ = _drive(
        tmp_path,
        card_class="gpu",
        rate=None,
        extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "STALL_S": "30"},
    )
    guards = _guards(out_dir)
    assert res.returncode == 91, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    assert re.search(r"^REFUSED: RATE_UNREAD: offline guard: ", guards, re.M), guards
    assert "POLL_RECONNECT_EXHAUSTED" not in guards
    assert not [r for r in _records(guards) if isinstance(r.get("cap"), dict)], guards


def test_lost_start_reply_with_worker_crashed_without_done_never_reruns_and_fails_closed(tmp_path: Path) -> None:
    launcher = COLAB_DIR / "launch_lane1_stub.sh"
    _, state_dir, env = fc.make_fake_colab_env(tmp_path / "crash_case")
    env["FAKE_COLAB_START_LOST_AFTER_RUN_ONCE"] = "1"
    env["FAKE_COLAB_CRASH_WORKER_BEFORE_START_N"] = "2"
    env["FAKE_RUN_ROWS_N"] = "40"
    env["FAKE_RUN_ROW_SLEEP_S"] = "0.2"
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    env["SDLAB_TEST_DETACHED_START_RETRY_SLEEP_S"] = "0.1"
    out_dir = tmp_path / "out_crash"
    try:
        res = subprocess.run(
            [_bash(), fc._to_posix(launcher), "--out-dir", fc._to_posix(out_dir), "--session", "sdlab-l1-crash-token"],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    finally:
        lg.stop_detached_worker(state_dir / "content", sig=9)
    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert (state_dir / "worker_crashed.txt").is_file()
    assert res.returncode != 0, guards
    assert int((state_dir / "start_calls.txt").read_text(encoding="utf-8").strip()) == 2
    runs = [ln for ln in (state_dir / "remote_script_runs.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(runs) == 1, runs
    assert "DETACHED_START_RETRY attempt=1/3 rc=1" in guards
    assert "DETACHED_START_ALREADY_RUNNING attempt=2/3" in guards
    assert "REFUSED: SDLAB_REMOTE_RC marker missing from vitals.log" in guards
    assert "STOP -s sdlab-l1-crash-token" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_exported_poll_knobs_do_not_lift_the_outage_bound(tmp_path: Path) -> None:
    launcher = COLAB_DIR / "launch_lane1_stub.sh"
    _, state_dir, env = fc.make_fake_colab_env(tmp_path / "knob_case")
    env["FAKE_COLAB_MODE"] = "stall"
    env["FAKE_COLAB_POLL_FAIL_CALLS"] = "all"
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    env["STALL_S"] = "4"
    env["SDLAB_TEST_POLL_RETRY_SLEEP_S"] = "0.1"
    # A caller's shell exports these; they must not reach the loop (only SDLAB_TEST_* do, in test mode).
    env["COLAB_POLL_OUTAGE_MAX_S"] = "100000"
    env["COLAB_POLL_MAX_RETRIES"] = "100000"
    env["COLAB_POLL_EXEC_TIMEOUT_S"] = "250"
    out_dir = tmp_path / "out_knobs"
    t0 = time.monotonic()
    try:
        res = subprocess.run(
            [_bash(), fc._to_posix(launcher), "--out-dir", fc._to_posix(out_dir), "--session", "sdlab-l1-knobs",
             "--wall-s", "45", "--grace-s", "5"],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    finally:
        lg.stop_detached_worker(state_dir / "content", sig=9)
    took = time.monotonic() - t0
    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "POLL_RECONNECT_EXHAUSTED", guards
    assert "max_retries=12, max_outage_s=4," in guards, guards
    assert re.search(r"^DETACHED_POLL_RETRY attempt=1/12 .* outage_s=\d+/4$", guards, re.M), guards
    assert took < 40.0, took


def test_offline_cap_projection_cli_records_and_refusals(capsys) -> None:
    base = ["--check-offline-cap", "--cap", "5.72", "--margin", "0.02", "--cleanup-bound-s", "450",
            "--rate", "36", "--start-balance", "9.85", "--current-balance", "9.85", "--balance-age-s", "42.5"]
    assert lg.main([*base, "--elapsed-s", "100", "--checkpoint", "offline"]) == 0
    rec = json.loads(capsys.readouterr().out.strip())
    assert rec["check"] == "offline_cap" and rec["checkpoint"] == "offline" and "refusal" not in rec
    assert rec["cap"]["mode"] == "live_offline"
    assert rec["cap"]["tripped"] is False and rec["cap"]["fresh_pass"] is False
    assert rec["cap"]["result"] == "no_trip_projection"
    assert rec["cap"]["balance_source"] == "cached" and rec["cap"]["balance_age_s"] == 42.5
    assert rec["cap"]["projected_spend_ccu"] == 1.0 and rec["cap"]["ceiling_ccu"] == 1.2

    assert lg.main([*base, "--elapsed-s", "120"]) == 1
    rec_trip = json.loads(capsys.readouterr().out.strip())
    assert rec_trip["cap"]["tripped"] is True and rec_trip["cap"]["result"] == "trip"
    assert rec_trip["refusal"]["code"] == "CAP_GUARD_TRIPPED"
    assert rec_trip["refusal"]["why"].startswith("offline cap projection: spend 1.2 ccu")

    # A cached drop at or above the ceiling also trips (trip-only: old data may refuse, never pass).
    drop = ["--check-offline-cap", "--cap", "5.72", "--margin", "0.02", "--cleanup-bound-s", "450",
            "--rate", "36", "--start-balance", "9.85", "--current-balance", "8.5", "--balance-age-s", "1",
            "--elapsed-s", "1"]
    assert lg.main(drop) == 1
    assert json.loads(capsys.readouterr().out.strip())["cap"]["cached_drop_ccu"] == 1.35

    assert lg.main(["--check-offline-cap", "--elapsed-s", "1", "--rate", "1"]) == 2
    assert "requires --start-balance" in capsys.readouterr().err


def test_cap_check_interval_matches_a_measured_worst_case_on_a_dead_link(tmp_path: Path) -> None:
    # Small knobs: r (poll retry sleep) 0.3, p (tick) 0.2, e (poll exec timeout) 2, g (kill grace) 1,
    # T_retry = 1 * (10 + 1) = 11, slack 2, so the in-flight deadline is 13 s and
    # cap_check_interval_s = (r + p + e) + (T_retry + slack) + (r + p + e + g) = 2.5 + 13 + 3.5 = 19 s.
    # Poll 1 fails (the offline projection is the last cap check), poll 2 succeeds slowly (1.8 s) and
    # launches the usage read, polls 3+ hang past their timeout (a dead link). The read finishes just
    # after the liveness check on the 2nd failed poll after the launch; it is reaped at the next failed poll's tick.
    r, p, e, g, t_retry, slack, slow = 0.3, 0.2, 2.0, 1.0, 11.0, 2.0, 1.8
    formula = (r + p + e) + (t_retry + slack) + (r + p + e + g)
    out_guards = tmp_path / "out" / "guards.log"
    res, out_dir, state_dir = _drive(
        tmp_path,
        extra_env={
            "GUARD_POLL_INTERVAL_S": str(p),
            "SDLAB_TEST_POLL_RETRY_SLEEP_S": str(r),
            "SDLAB_TEST_POLL_EXEC_TIMEOUT_S": str(int(e)),
            "SDLAB_TEST_KILL_GRACE_S": str(int(g)),
            "SDLAB_TEST_POLL_MAX_RETRIES": "4",
            "SDLAB_TEST_USAGE_POLL_ATTEMPTS": "1",
            "SDLAB_TEST_USAGE_POLL_TIMEOUT_S": "10",
            "SDLAB_TEST_USAGE_POLL_KILL_GRACE_S": "1",
            "FAKE_COLAB_POLL_FAIL_CALLS": "1",
            "FAKE_COLAB_POLL_SLOW_OK_CALLS": "2",
            "FAKE_COLAB_POLL_SLOW_OK_S": str(slow),
            "FAKE_COLAB_POLL_HANG_CALLS": ",".join(str(n) for n in range(3, 40)),
            "FAKE_COLAB_USAGE_HOLD_AFTER_RETRY": "3",
            "FAKE_COLAB_USAGE_HOLD_LOG": fc._to_posix(out_guards),
        },
        timeout=240,
    )
    guards = _guards(out_dir)
    assert res.returncode == 94, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    assert "POLL_RECONNECT_EXHAUSTED" in guards
    # The shell's interval (what the gate prices) is the formula's.
    assert float((out_dir / "drv_cap_check_interval_s.txt").read_text(encoding="utf-8").strip()) == formula == 19.0
    assert lg.compute_usage_retry_budget(priced_rate=1.0, margin=1.0, usage_blind_interval=t_retry + 2 * p + slack,
                                         detached_poll_lag=2 * (r + e) + g)["cap_check_interval_s"] == 19

    open_epoch = float((out_dir / "session_open_epoch.txt").read_text(encoding="utf-8").strip())
    usage = [json.loads(ln) for ln in (state_dir / "usage_events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(usage) == 1
    launch_el = usage[0]["start"] - open_epoch
    read_end_el = usage[0]["end"] - open_epoch

    def elapsed(rec: dict) -> float:
        if rec.get("check") == "offline_cap":
            return float(rec["cap"]["elapsed_s"])
        return float(rec["wall"]["threshold_s"]) - float(rec["wall"]["remaining_s"])

    cap_checks = [r_ for r_ in _records(guards)
                  if r_.get("check") == "offline_cap" or (isinstance(r_.get("cap"), dict) and r_["cap"].get("mode") == "live")]
    before = [c for c in cap_checks if elapsed(c) < launch_el]
    after = [c for c in cap_checks if elapsed(c) > launch_el]
    assert before and after, guards
    c0, c1 = before[-1], after[0]
    assert c0.get("check") == "offline_cap"
    assert c1["cap"]["mode"] == "live" and c1["cap"]["tripped"] is False
    pre_leg = launch_el - elapsed(c0)
    read_leg = read_end_el - launch_el
    reap_leg = elapsed(c1) - read_end_el
    measured = elapsed(c1) - elapsed(c0)
    print(f"MEASURED pre_leg={pre_leg:.3f} read_leg={read_leg:.3f} reap_leg={reap_leg:.3f} "
          f"interval={measured:.3f} formula={formula:.3f}")
    # Each leg against its term: the launch waits r + p + a slow poll; the read is inside its deadline; the
    # reap waits r + p + a failed poll killed at e + g (less the 0.05 s the read ended after the check).
    assert r + p + slow - 0.1 <= pre_leg <= r + p + e + 1.0, pre_leg
    assert read_leg <= t_retry + slack, read_leg
    assert (r + p + e + g) - 0.2 <= reap_leg <= (r + p + e + g) + 1.0, reap_leg
    assert measured <= formula + 1.5, (measured, formula)
    # What the run leaves short of the formula is the read finishing before its deadline and the slow
    # poll finishing before its timeout, plus overhead.
    assert measured >= formula - ((t_retry + slack) - read_leg) - (e - slow) - 1.0, (measured, formula)


# --- sdlab#82 fix 3 ------------------------------------------------------------------------------


def test_fix3_offline_projection_grows_from_the_cached_balance(tmp_path: Path) -> None:
    # Other sessions on the account already drew 1.10 units, far above priced_rate * elapsed (36/h for
    # 5 s = 0.05). The ceiling is 1.2 (cap 5.72 - margin 0.02 - reserve 4.5). The cached reading is 2 s old
    # when the outage starts; this window's own burn since it (0.01 units/s) must be added, so the cap
    # trips when the balance is about 10 s old. A frozen projection (max(drop, rate * elapsed)) would
    # stay at 1.10 until elapsed 120 s and never trip inside the outage.
    res, out_dir, _ = _drive(
        tmp_path,
        open_ago_s=5.0,
        end_balance="8.75",
        end_balance_age_s=2.0,
        rate="36",
        cap=5.72,
        extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "STALL_S": "25"},
        timeout=240,
    )
    guards = _guards(out_dir)
    assert res.returncode == 91, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    offline = [r["cap"] for r in _records(guards) if r.get("check") == "offline_cap"]
    assert len(offline) >= 3, guards
    for rec in offline:
        assert rec["cached_drop_ccu"] == 1.1
        assert rec["aged_drop_ccu"] == round(1.1 + 36.0 * rec["balance_age_s"] / 3600.0, 6)
        assert rec["spend_ccu"] == max(rec["projected_spend_ccu"], rec["aged_drop_ccu"])
    ages = [rec["balance_age_s"] for rec in offline]
    spends = [rec["spend_ccu"] for rec in offline]
    assert ages == sorted(ages) and spends == sorted(spends) and spends[-1] > spends[0]
    assert all(not rec["tripped"] for rec in offline[:-1]) and offline[-1]["tripped"] is True
    assert offline[-1]["code"] == "CAP_GUARD_TRIPPED"
    # It trips on the first check whose balance is at least 10 s old (aged drop >= 1.2), not later.
    assert offline[-1]["balance_age_s"] >= 10.0 and offline[-2]["balance_age_s"] < 10.0, ages
    assert re.search(r"^REFUSED: CAP_GUARD_TRIPPED: offline cap projection: ", guards, re.M), guards


def test_fix3_gpu_rate_written_as_zero_or_not_finite_refuses_rate_unread(tmp_path: Path) -> None:
    for i, bad in enumerate(("0e0", "0.0e-5", "1e-400")):
        res, out_dir, _ = _drive(
            tmp_path / f"r{i}",
            card_class="gpu",
            rate=bad,
            extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "STALL_S": "30"},
        )
        guards = _guards(out_dir)
        assert res.returncode == 91, f"{bad}: rc={res.returncode}\n{guards}\n{res.stderr}"
        assert re.search(r"^REFUSED: RATE_UNREAD: offline guard: ", guards, re.M), (bad, guards)
        assert not [r for r in _records(guards) if isinstance(r.get("cap"), dict)], (bad, guards)
    # The Python function refuses the same rates on its own, and a NaN or infinite one too.
    for bad_rate in (0.0, float("nan"), float("inf"), -1.0):
        for cls in ("gpu", None, ""):
            rec = lg.evaluate_offline_cap_projection(
                cap=5.0, margin=1.25, cleanup_bound_s=450, rate_ccu_per_hour=bad_rate, elapsed_s=10.0,
                start_balance=9.85, cached_balance=9.85, balance_age_s=1.0, card_class=cls,
            )
            assert rec["tripped"] is True and rec["code"] == "RATE_UNREAD", (bad_rate, cls, rec)
    cpu = lg.evaluate_offline_cap_projection(
        cap=5.0, margin=0.05, cleanup_bound_s=450, rate_ccu_per_hour=0.26, elapsed_s=10.0,
        start_balance=9.85, cached_balance=9.85, balance_age_s=1.0, card_class="cpu",
    )
    assert cpu["tripped"] is False and cpu["code"] is None


def test_fix3_unset_or_empty_card_class_fails_closed_as_gpu(tmp_path: Path) -> None:
    for i, cls in enumerate(("__unset__", "")):
        res, out_dir, _ = _drive(
            tmp_path / f"c{i}",
            card_class=cls,
            rate=None,
            extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "STALL_S": "30"},
        )
        guards = _guards(out_dir)
        assert res.returncode == 91, f"{cls!r}: rc={res.returncode}\n{guards}\n{res.stderr}"
        assert re.search(r"^REFUSED: RATE_UNREAD: offline guard: ", guards, re.M), (cls, guards)
        assert "POLL_RECONNECT_EXHAUSTED" not in guards


def test_fix3_unset_cleanup_bound_refuses(tmp_path: Path) -> None:
    res, out_dir, _ = _drive(
        tmp_path,
        extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "STALL_S": "30", "DRV_UNSET_CLEANUP_BOUND": "1"},
    )
    guards = _guards(out_dir)
    assert res.returncode == 91, f"rc={res.returncode}\n{guards}\n{res.stderr}"
    assert re.search(r"^REFUSED: GUARD_FAILED: offline guard: COLAB_CLEANUP_BOUND_S is unset", guards, re.M), guards
    assert not [r for r in _records(guards) if r.get("check") == "offline_cap"], guards


def test_fix3_outage_bound_is_clamped_to_300_s(tmp_path: Path) -> None:
    def bound_for(sub: str, extra: dict[str, str]) -> str:
        res, out_dir, _ = _drive(
            tmp_path / sub,
            extra_env={"FAKE_COLAB_POLL_FAIL_CALLS": "all", "SDLAB_TEST_POLL_MAX_RETRIES": "1", **extra},
        )
        guards = _guards(out_dir)
        assert res.returncode == 94 and "POLL_RECONNECT_EXHAUSTED" in guards, (sub, res.returncode, guards)
        m = re.search(r"^DETACHED_POLL_RETRY attempt=1/1 .* outage_s=\d+/(\d+)$", guards, re.M)
        assert m, guards
        return m.group(1)

    assert bound_for("stall900", {"STALL_S": "900"}) == "300"
    assert bound_for("stall6", {"STALL_S": "6"}) == "6"
    # The fake-CLI test override still works (and is clamped the same way).
    assert bound_for("override5", {"STALL_S": "900", "SDLAB_TEST_POLL_OUTAGE_MAX_S": "5"}) == "5"
    assert bound_for("override900", {"STALL_S": "900", "SDLAB_TEST_POLL_OUTAGE_MAX_S": "900"}) == "300"
