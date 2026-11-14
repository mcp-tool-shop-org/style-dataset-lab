"""Unit tests for scripts/colab/launch_guards.py (Part B.2)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "colab"))

import launch_guards as lg  # noqa: E402


def test_wall_guard_trips_on_fixture_and_stays_quiet_just_under() -> None:
    # Live default: wall_s=3000, grace_s=60 -> threshold=2940.0
    quiet = lg.evaluate_wall_guard(mode="live", elapsed_s=2939.9, wall_s=3000.0, grace_s=60.0)
    assert quiet["tripped"] is False
    assert quiet["code"] is None
    assert pytest.approx(quiet["remaining_s"], rel=1e-3) == 0.1

    tripped = lg.evaluate_wall_guard(mode="live", elapsed_s=2940.0, wall_s=3000.0, grace_s=60.0)
    assert tripped["tripped"] is True
    assert tripped["code"] == "WALL_GUARD_TRIPPED"
    assert tripped["remaining_s"] <= 0.0

    # Stub window: wall_s=900, grace_s=60 -> threshold=840.0
    stub_quiet = lg.evaluate_wall_guard(mode="stub", elapsed_s=839.5, wall_s=900.0, grace_s=60.0)
    assert stub_quiet["tripped"] is False
    stub_tripped = lg.evaluate_wall_guard(mode="stub", elapsed_s=840.0, wall_s=900.0, grace_s=60.0)
    assert stub_tripped["tripped"] is True
    assert stub_tripped["code"] == "WALL_GUARD_TRIPPED"


def test_cap_guard_trips_on_fixture_and_stays_quiet_just_under() -> None:
    # Balance drop fixture: cap=0.05, margin=0.01 -> ceiling=0.04
    quiet_bal = lg.evaluate_cap_guard(
        mode="stub",
        cap=0.05,
        margin=0.01,
        start_balance=10.0,
        current_balance=9.9601,
    )
    assert quiet_bal["tripped"] is False
    assert quiet_bal["code"] is None

    tripped_bal = lg.evaluate_cap_guard(
        mode="stub",
        cap=0.05,
        margin=0.01,
        start_balance=10.0,
        current_balance=9.96,
    )
    assert tripped_bal["tripped"] is True
    assert tripped_bal["code"] == "CAP_GUARD_TRIPPED"

    # Burn-rate fixture without balance poll (in fake mode): 0.24 CCU/hr * 600s = 0.04 CCU
    quiet_rate = lg.evaluate_cap_guard(
        mode="fake",
        cap=0.05,
        margin=0.01,
        rate_ccu_per_hour=0.24,
        elapsed_s=599.0,
    )
    assert quiet_rate["tripped"] is False

    tripped_rate = lg.evaluate_cap_guard(
        mode="fake",
        cap=0.05,
        margin=0.01,
        rate_ccu_per_hour=0.24,
        elapsed_s=600.0,
    )
    assert tripped_rate["tripped"] is True
    assert tripped_rate["code"] == "CAP_GUARD_TRIPPED"

    # Burn-rate conservative floor in live mode when balances do not drop yet:
    live_rate_tripped = lg.evaluate_cap_guard(
        mode="live",
        cap=0.05,
        margin=0.01,
        start_balance=10.0,
        current_balance=10.0,
        rate_ccu_per_hour=0.24,
        elapsed_s=600.0,
    )
    assert live_rate_tripped["tripped"] is True
    assert live_rate_tripped["code"] == "CAP_GUARD_TRIPPED"

    # Missing start or current balance in live/stub (non-fake) mode fails closed as COLAB_USAGE_PARSE_FAILED
    missing_start = lg.evaluate_cap_guard(
        mode="live",
        cap=0.05,
        margin=0.01,
        start_balance=None,
        current_balance=9.85,
    )
    assert missing_start["tripped"] is True
    assert missing_start["code"] == "COLAB_USAGE_PARSE_FAILED"

    missing_current = lg.evaluate_cap_guard(
        mode="live",
        cap=0.05,
        margin=0.01,
        start_balance=9.85,
        current_balance=None,
    )
    assert missing_current["tripped"] is True
    assert missing_current["code"] == "COLAB_USAGE_PARSE_FAILED"

    # Negative start or current balance fails closed as COLAB_USAGE_PARSE_FAILED
    neg_bal = lg.evaluate_cap_guard(
        mode="live",
        cap=0.05,
        margin=0.01,
        start_balance=9.85,
        current_balance=-5.0,
    )
    assert neg_bal["tripped"] is True
    assert neg_bal["code"] == "COLAB_USAGE_PARSE_FAILED"

    # Usage parse failure trips cap guard immediately with COLAB_USAGE_PARSE_FAILED
    tripped_parse = lg.evaluate_cap_guard(
        mode="stub",
        cap=0.05,
        margin=0.01,
        usage_parse_error="COLAB_USAGE_PARSE_FAILED: missing 'Current balance: <float> compute units'",
    )
    assert tripped_parse["tripped"] is True
    assert tripped_parse["code"] == "COLAB_USAGE_PARSE_FAILED"
    assert tripped_parse["spend_ccu"] is None


def test_parse_usage_text_anchored_regexes_and_rate_fallback() -> None:
    ok_hr = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.85 compute units\nUsage rate: 0.26/hr\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.50,
    )
    assert ok_hr["ok"] is True
    assert ok_hr["balance"] == 9.85
    assert ok_hr["rate_measured"] == 0.26
    assert ok_hr["rate_measured_post_open"] == 0.26
    assert ok_hr["rate_for_projection"] == 0.26
    assert ok_hr["rate_source"] == "post_open_measured"
    assert ok_hr["active_assignments"] == 1

    # Accepts /h as well, and falls back to configured RATE_CCU_PER_HOUR only when rate is absent
    ok_h = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 12.5 compute units\nUsage rate: 0.08/h\n",
        usage_rc=0,
        configured_rate=0.50,
    )
    assert ok_h["ok"] is True
    assert ok_h["balance"] == 12.5
    assert ok_h["rate_measured"] == 0.08
    assert ok_h["rate_source"] == "post_open_measured"

    fallback_rate = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 7.25 compute units\nActive assignments: 0\n",
        usage_rc=0,
        configured_rate=0.33,
    )
    assert fallback_rate["ok"] is True
    assert fallback_rate["balance"] == 7.25
    assert fallback_rate["rate_measured"] is None
    assert fallback_rate["rate_for_projection"] == 0.33
    assert fallback_rate["rate_source"] == "configured"

    # Pre-open measured 0.00/hr must never lower configured rate; uses max(pre_open, configured)
    pre_zero = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.85 compute units\nUsage rate: 0.00/hr\nActive assignments: 0\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=False,
    )
    assert pre_zero["ok"] is True
    assert pre_zero["rate_measured_pre_open"] == 0.0
    assert pre_zero["rate_measured_post_open"] is None
    assert pre_zero["rate_used_for_cap_and_projection"] == 0.26
    assert pre_zero["rate_source"] == "max_of_pre_open_and_configured"

    pre_higher = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.85 compute units\nUsage rate: 0.80/hr\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=False,
    )
    assert pre_higher["ok"] is True
    assert pre_higher["rate_measured_pre_open"] == 0.80
    assert pre_higher["rate_used_for_cap_and_projection"] == 0.80
    assert pre_higher["rate_source"] == "max_of_pre_open_and_configured"

    post_after_pre = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.80 compute units\nUsage rate: 0.24/hr\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=True,
        pre_open_rate=0.0,
    )
    assert post_after_pre["ok"] is True
    assert post_after_pre["rate_measured_pre_open"] == 0.0
    assert post_after_pre["rate_measured_post_open"] == 0.24
    assert post_after_pre["rate_used_for_cap_and_projection"] == 0.24
    assert post_after_pre["rate_source"] == "post_open_measured"

    # A post-open 0.00/hr rate is not yet measured: uses max(configured, positive measured) and configured_pending_post_open_rate
    post_zero = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.85 compute units\nUsage rate: 0.00/hr\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=True,
        pre_open_rate=0.0,
    )
    assert post_zero["ok"] is True
    assert post_zero["rate_measured_pre_open"] == 0.0
    assert post_zero["rate_measured_post_open"] == 0.0
    assert post_zero["rate_used_for_cap_and_projection"] == 0.26
    assert post_zero["rate_source"] == "configured_pending_post_open_rate"

    post_zero_with_pos_pre = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.85 compute units\nUsage rate: 0.00/hr\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=True,
        pre_open_rate=0.45,
    )
    assert post_zero_with_pos_pre["ok"] is True
    assert post_zero_with_pos_pre["rate_measured_post_open"] == 0.0
    assert post_zero_with_pos_pre["rate_used_for_cap_and_projection"] == 0.45
    assert post_zero_with_pos_pre["rate_source"] == "configured_pending_post_open_rate"

    # Once a later post-open read becomes positive, it replaces the earlier 0.0 post-open read
    post_later_positive = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.83 compute units\nUsage rate: 0.34/hr\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=True,
        post_open_rate=0.0,
        pre_open_rate=0.0,
    )
    assert post_later_positive["ok"] is True
    assert post_later_positive["rate_measured_post_open"] == 0.34
    assert post_later_positive["rate_used_for_cap_and_projection"] == 0.34
    assert post_later_positive["rate_source"] == "post_open_measured"

    # Once a positive post_open_rate is established, a subsequent omitted rate keeps the positive post_open_rate
    post_keep_positive = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.82 compute units\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=True,
        post_open_rate=0.34,
        pre_open_rate=0.0,
    )
    assert post_keep_positive["ok"] is True
    assert post_keep_positive["rate_measured_post_open"] == 0.34
    assert post_keep_positive["rate_used_for_cap_and_projection"] == 0.34
    assert post_keep_positive["rate_source"] == "post_open_measured"

    # Subsequent omitted rate when post_open_rate was 0.0 keeps configured_pending_post_open_rate
    post_keep_pending = lg.parse_usage_text(card_class="cpu", raw_usage=
        "Current balance: 9.82 compute units\nActive assignments: 1\n",
        usage_rc=0,
        configured_rate=0.26,
        session_opened=True,
        post_open_rate=0.0,
        pre_open_rate=0.0,
    )
    assert post_keep_pending["ok"] is True
    assert post_keep_pending["rate_measured_post_open"] == 0.0
    assert post_keep_pending["rate_used_for_cap_and_projection"] == 0.26
    assert post_keep_pending["rate_source"] == "configured_pending_post_open_rate"

    # Rejects JSON or unparseable output or non-zero exit code without any 10.0 fallback
    bad_json = lg.parse_usage_text(card_class="cpu", raw_usage='{"balance_ccu": 10.0, "rate_ccu_per_hour": 0.26}', usage_rc=0)
    assert bad_json["ok"] is False
    assert bad_json["code"] == "COLAB_USAGE_PARSE_FAILED"
    assert bad_json["balance"] is None

    bad_rc = lg.parse_usage_text(card_class="cpu", raw_usage="Current balance: 9.85 compute units\n", usage_rc=1)
    assert bad_rc["ok"] is False
    assert bad_rc["code"] == "COLAB_USAGE_PARSE_FAILED"
    assert bad_rc["balance"] is None

    # Rejects negative balance and negative usage rate as COLAB_USAGE_PARSE_FAILED
    neg_bal = lg.parse_usage_text(card_class="cpu", raw_usage="Current balance: -5.00 compute units\nUsage rate: 0.26/hr\n", usage_rc=0)
    assert neg_bal["ok"] is False
    assert neg_bal["code"] == "COLAB_USAGE_PARSE_FAILED"
    assert neg_bal["balance"] is None

    neg_rate = lg.parse_usage_text(card_class="cpu", raw_usage="Current balance: 5.00 compute units\nUsage rate: -0.26/hr\n", usage_rc=0)
    assert neg_rate["ok"] is False
    assert neg_rate["code"] == "COLAB_USAGE_PARSE_FAILED"
    assert neg_rate["balance"] is None


def test_vitals_parsing_and_stall_guard_trips_and_stays_quiet_just_under() -> None:
    vitals_fixture = """=== VITALS 2026-11-05T12:00:00Z ===
MEM: MemTotal: 13290000 kB
PROC:
101 python3 /content/ComfyUI/main.py --cpu --listen 127.0.0.1
HARNESS: {"phase": "run", "step": 1}
=== VITALS 2026-11-05T12:00:30Z ===
MEM: MemTotal: 13290000 kB
PROC:
101 python3 /content/ComfyUI/main.py --cpu --listen 127.0.0.1
HARNESS: phase: run
"""
    samples = lg.parse_vitals_log(vitals_fixture)
    assert len(samples) == 2
    assert samples[0]["phase"] == "run"
    assert samples[0]["worker_proc_count"] == 1
    assert samples[1]["phase"] == "run"
    assert samples[1]["worker_proc_count"] == 1

    quiet = lg.evaluate_vitals_and_stall_guard(
        vitals_text=vitals_fixture,
        idle_seconds=299.9,
        stall_s=300.0,
    )
    assert quiet["tripped"] is False
    assert quiet["code"] is None

    tripped = lg.evaluate_vitals_and_stall_guard(
        vitals_text=vitals_fixture,
        idle_seconds=300.0,
        stall_s=300.0,
    )
    assert tripped["tripped"] is True
    assert tripped["code"] == "STALL_GUARD_TRIPPED"


def test_dead_harness_on_cgroup_oom_fixture_trips_and_stays_quiet_just_under() -> None:
    # Just under: only 1 sample has 0 worker procs (second sample not yet observed)
    single_zero_fixture = """=== VITALS 2026-11-05T12:01:00Z ===
CGROUP_MEM: oom_kill 0
PROC:
101 python3 /content/ai-toolkit/run.py job.yaml
HARNESS: {"phase": "run", "step": 1}
=== VITALS 2026-11-05T12:01:30Z ===
CGROUP_MEM: oom_kill 0
PROC:
HARNESS: {"phase": "run", "step": 1}
"""
    quiet = lg.evaluate_vitals_and_stall_guard(
        vitals_text=single_zero_fixture,
        idle_seconds=30.0,
        stall_s=300.0,
    )
    assert quiet["tripped"] is False

    # Trips on 2 consecutive phase=run samples with 0 worker procs
    two_zero_fixture = single_zero_fixture + """=== VITALS 2026-11-05T12:02:00Z ===
CGROUP_MEM: oom_kill 0
PROC:
HARNESS: {"phase": "run", "step": 1}
"""
    tripped_two = lg.evaluate_vitals_and_stall_guard(
        vitals_text=two_zero_fixture,
        idle_seconds=60.0,
        stall_s=300.0,
    )
    assert tripped_two["tripped"] is True
    assert tripped_two["code"] == "DEAD_HARNESS_TRIPPED"

    # Trips immediately when cgroup memory.events reports oom_kill > 0 with 0 worker procs
    cgroup_oom_fixture = """=== VITALS 2026-11-05T12:03:00Z ===
CGROUP_MEM: oom 1
CGROUP_MEM: oom_kill 1
PROC:
HARNESS: {"phase": "run", "step": 1}
"""
    tripped_oom = lg.evaluate_vitals_and_stall_guard(
        vitals_text=cgroup_oom_fixture,
        idle_seconds=10.0,
        stall_s=300.0,
    )
    assert tripped_oom["tripped"] is True
    assert tripped_oom["code"] == "DEAD_HARNESS_TRIPPED"
    assert tripped_oom.get("cgroup_oom") is True


def test_setup_phase_zero_workers_does_not_trip_dead_harness_and_trips_setup_stall_or_oom() -> None:
    setup_two_zero_fixture = """=== VITALS 2026-11-05T12:00:00Z ===
CGROUP_MEM: oom_kill 0
SETUP_BYTES: 120
PROC:
HARNESS: {"phase": "setup"}
=== VITALS 2026-11-05T12:00:15Z ===
CGROUP_MEM: oom_kill 0
SETUP_BYTES: 120
PROC:
HARNESS: {"phase": "setup"}
=== VITALS 2026-11-05T12:00:30Z ===
CGROUP_MEM: oom_kill 0
SETUP_BYTES: 120
PROC:
HARNESS: {"phase": "setup"}
"""
    samples = lg.parse_vitals_log(setup_two_zero_fixture)
    assert [s["setup_bytes"] for s in samples] == [120, 120, 120]

    quiet_setup = lg.evaluate_vitals_and_stall_guard(
        vitals_text=setup_two_zero_fixture,
        idle_seconds=0.0,
        setup_idle_seconds=599.9,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert quiet_setup["tripped"] is False
    assert quiet_setup["code"] is None

    # Even when idle_seconds=0.0 (vitals blocks keep arriving), setup_idle_seconds >= setup_stall_s trips SETUP_STALL_TRIPPED
    tripped_setup_stall = lg.evaluate_vitals_and_stall_guard(
        vitals_text=setup_two_zero_fixture,
        idle_seconds=0.0,
        setup_idle_seconds=600.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert tripped_setup_stall["tripped"] is True
    assert tripped_setup_stall["code"] == "SETUP_STALL_TRIPPED"

    # cgroup OOM remains active in setup phase too
    setup_oom_fixture = """=== VITALS 2026-11-05T12:00:00Z ===
CGROUP_MEM: oom 1
CGROUP_MEM: oom_kill 1
PROC:
HARNESS: {"phase": "setup"}
"""
    tripped_setup_oom = lg.evaluate_vitals_and_stall_guard(
        vitals_text=setup_oom_fixture,
        idle_seconds=5.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert tripped_setup_oom["tripped"] is True
    assert tripped_setup_oom["code"] == "DEAD_HARNESS_TRIPPED"
    assert tripped_setup_oom["cgroup_oom"] is True


def test_host_ram_projection_trips_and_stays_quiet_just_under() -> None:
    # Limit is min(16000, 12288) = 12288 MB.
    # Just under: (7700 + 4000) * 1.05 = 12285.0 <= 12288.0
    res = lg.check_host_ram_projection(
        current_anon_mb=7700.0,
        projected_delta_mb=4000.0,
        mem_total_mb=16000.0,
        cgroup_max_mb=12288.0,
        safety_factor=1.05,
    )
    assert res["ok"] is True
    assert res["projected_mb"] == 12285.0
    assert res["limit_mb"] == 12288.0

    # Trips: (7710 + 4000) * 1.05 = 12295.5 > 12288.0
    with pytest.raises(ValueError, match="HOST_RAM_PROJECTION_EXCEEDED"):
        lg.check_host_ram_projection(
            current_anon_mb=7710.0,
            projected_delta_mb=4000.0,
            mem_total_mb=16000.0,
            cgroup_max_mb=12288.0,
            safety_factor=1.05,
        )


def test_between_item_fetch_copies_files_before_resetting_current_json(tmp_path: Path) -> None:
    remote_dir = tmp_path / "remote"
    local_dir = tmp_path / "local"
    remote_dir.mkdir(parents=True)

    (remote_dir / "renders.jsonl").write_text('{"job_id":"j1","status":"ok"}\n', encoding="utf-8")
    (remote_dir / "j1.png").write_bytes(b"PNG_DATA_1")
    prev_current = {"window_id": "w1", "last_job_id": "j1", "files": ["renders.jsonl", "j1.png", "missing.png"]}
    (remote_dir / "current.json").write_text(json.dumps(prev_current), encoding="utf-8")

    next_current = {"window_id": "w1", "last_job_id": "j2", "files": ["renders.jsonl", "j1.png", "j2.png"]}
    out = lg.run_between_item_fetch(remote_dir=remote_dir, local_dir=local_dir, next_item=next_current)

    assert sorted(out["copied_files"]) == ["j1.png", "renders.jsonl"]
    assert out["previous_item"]["last_job_id"] == "j1"
    assert (local_dir / "j1.png").read_bytes() == b"PNG_DATA_1"
    assert json.loads((local_dir / "current.json").read_text(encoding="utf-8"))["last_job_id"] == "j1"
    assert json.loads((remote_dir / "current.json").read_text(encoding="utf-8"))["last_job_id"] == "j2"


def test_verify_input_shas_and_scrub_tokens_and_cli(tmp_path: Path) -> None:
    f1 = tmp_path / "input.txt"
    f1.write_bytes(b"canon-bytes")
    digest = lg.sha256_file(f1)

    verified = lg.verify_input_shas({str(f1): digest})
    assert verified[str(f1)] == digest

    with pytest.raises(ValueError, match="INPUT_SHA_MISMATCH"):
        lg.verify_input_shas({str(f1): "0" * 64})

    with pytest.raises(ValueError, match="INPUT_FILE_MISSING"):
        lg.verify_input_shas({str(tmp_path / "nope.txt"): digest})

    raw_log = (
        "Connecting to https://colab.research.google.com/tun?colab-runtime-proxy-token=sec_tok_98765&foo=1\n"
        "Header Authorization: Bearer ya29.secret_oauth_token_12345\n"
        "access_token=my_secret_access_tok\n"
    )
    scrubbed = lg.scrub_colab_tokens(raw_log)
    assert "sec_tok_98765" not in scrubbed
    assert "ya29.secret_oauth_token_12345" not in scrubbed
    assert "my_secret_access_tok" not in scrubbed
    assert "colab-runtime-proxy-token=[REDACTED]" in scrubbed

    log_file = tmp_path / "session.log"
    log_file.write_text(raw_log, encoding="utf-8")
    rc = lg.main(["--scrub-file", str(log_file)])
    assert rc == 0
    assert "sec_tok_98765" not in log_file.read_text(encoding="utf-8")

    rc_ok = lg.main(["--mode", "stub", "--elapsed-s", "10", "--wall-s", "900", "--grace-s", "60", "--start-balance", "10.0", "--current-balance", "10.0"])
    assert rc_ok == 0

    rc_trip = lg.main(["--mode", "stub", "--elapsed-s", "850", "--wall-s", "900", "--grace-s", "60", "--start-balance", "10.0", "--current-balance", "10.0"])
    assert rc_trip == 1

    # Direct main() CLI coverage for --verify-sha, --check-ram, --vitals-file, and non-existent scrub file
    lg.scrub_file_in_place(tmp_path / "does_not_exist.log")
    assert lg.main(["--verify-sha", f"{f1}=sha256:{digest}"]) == 0
    assert lg.main(["--verify-sha", "bad_arg_without_equals"]) == 2
    assert lg.main(["--verify-sha", f"{f1}={'0' * 64}"]) == 1
    assert lg.main(["--check-ram", "--current-anon-mb", "500", "--projected-delta-mb", "1000", "--mem-total-mb", "8000"]) == 0
    assert lg.main(["--check-ram", "--current-anon-mb", "5000", "--projected-delta-mb", "5000", "--mem-total-mb", "8000"]) == 1

    v_file = tmp_path / "vitals.log"
    v_file.write_text("=== VITALS 2026-11-05T12:00:00Z ===\nCGROUP_MEM: oom_kill 1\nPROC:\nHARNESS: {\"phase\": \"run\"}\n", encoding="utf-8")
    assert lg.main(["--vitals-file", str(v_file)]) == 1
    v_file.write_text("=== VITALS 2026-11-05T12:00:00Z ===\nPROC:\n101 python main.py\nHARNESS: {\"phase\": \"run\"}\n", encoding="utf-8")
    assert lg.main(["--vitals-file", str(v_file), "--idle-seconds", "5", "--stall-s", "300"]) == 0

    # Subproc CLI check
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "colab" / "launch_guards.py"), "--verify-sha", f"{f1}={digest}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0


def test_torn_tail_vitals_block_in_run_phase_does_not_trip_setup_stall() -> None:
    vitals_with_torn_tail = (
        "=== VITALS 2026-11-11T04:14:30Z ===\n"
        "SETUP_BYTES: 120\n"
        "PROC:\n"
        "2216 /content/venv-lane3/bin/python /content/ai-toolkit/run.py /content/lane3_out/rung_job.yaml\n"
        'HARNESS: {"phase": "run"}\n'
        "=== VITALS 2026-11-11T04:14:45Z ===\n"
        "SETUP_BYTES: 120\n"
        "PROC:\n"
        "2216 /content/venv-lane3/bin/python /content/ai-toolkit/run.py /content/lane3_out/rung_job.yaml\n"
        'HARNESS: {"phase": "run"}\n'
        "=== VITALS 2026-11-11T04:15:00Z ===\n"
    )
    samples = lg.parse_vitals_log(vitals_with_torn_tail)
    assert len(samples) == 2
    assert [s["phase"] for s in samples] == ["run", "run"]

    res = lg.evaluate_vitals_and_stall_guard(
        vitals_text=vitals_with_torn_tail,
        idle_seconds=30.0,
        setup_idle_seconds=870.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert res["tripped"] is False
    assert res["code"] is None


def test_complete_setup_blocks_with_unchanged_setup_bytes_still_trips_setup_stall() -> None:
    complete_setup_vitals = (
        "=== VITALS 2026-11-11T04:14:30Z ===\n"
        "SETUP_BYTES: 120\n"
        "PROC:\n"
        'HARNESS: {"phase": "setup"}\n'
        "=== VITALS 2026-11-11T04:14:45Z ===\n"
        "SETUP_BYTES: 120\n"
        "PROC:\n"
        'HARNESS: {"phase": "setup"}\n'
        "=== VITALS 2026-11-11T04:15:00Z ===\n"
        "SETUP_BYTES: 120\n"
        "PROC:\n"
        'HARNESS: {"phase": "setup"}\n'
    )
    res = lg.evaluate_vitals_and_stall_guard(
        vitals_text=complete_setup_vitals,
        idle_seconds=30.0,
        setup_idle_seconds=870.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert res["tripped"] is True
    assert res["code"] == "SETUP_STALL_TRIPPED"


def test_missing_harness_phase_refuses_vitals_phase_unreadable_never_setup() -> None:
    missing_phase_complete = (
        "=== VITALS 2026-11-11T04:15:00Z ===\n"
        "SETUP_BYTES: 120\n"
        "PROC:\n"
        "HARNESS: {}\n"
    )
    res_no_phase = lg.evaluate_vitals_and_stall_guard(
        vitals_text=missing_phase_complete,
        idle_seconds=10.0,
        setup_idle_seconds=870.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert res_no_phase["tripped"] is True
    assert res_no_phase["code"] == "VITALS_PHASE_UNREADABLE"

    two_torn_no_harness = (
        "=== VITALS 2026-11-11T04:14:45Z ===\nSETUP_BYTES: 120\n"
        "=== VITALS 2026-11-11T04:15:00Z ===\nSETUP_BYTES: 120\n"
    )
    res_two_torn = lg.evaluate_vitals_and_stall_guard(
        vitals_text=two_torn_no_harness,
        idle_seconds=10.0,
        setup_idle_seconds=870.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert res_two_torn["tripped"] is True
    assert res_two_torn["code"] == "VITALS_PHASE_UNREADABLE"

    # First block still being written (< 2 blocks, 0 complete): waits without assuming setup.
    first_mid_write = "=== VITALS 2026-11-11T04:15:00Z ===\nSETUP_BYTES: 120\n"
    res_waiting = lg.evaluate_vitals_and_stall_guard(
        vitals_text=first_mid_write,
        idle_seconds=10.0,
        setup_idle_seconds=870.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert res_waiting["tripped"] is False
    assert res_waiting["code"] is None


def test_bundle_phase_uses_setup_stall_budget_and_keeps_oom_guard() -> None:
    bundle_two_zero = (
        "=== VITALS 2026-11-11T05:00:00Z ===\n"
        "CGROUP_MEM: oom_kill 0\n"
        "SETUP_BYTES: 500\n"
        "PROC:\n"
        'HARNESS: {"phase": "bundle"}\n'
        "=== VITALS 2026-11-11T05:00:15Z ===\n"
        "CGROUP_MEM: oom_kill 0\n"
        "SETUP_BYTES: 500\n"
        "PROC:\n"
        'HARNESS: {"phase": "bundle"}\n'
    )
    # In phase=bundle, 0 worker processes does NOT trip DEAD_HARNESS_TRIPPED, and idle_seconds
    # above stall_s (300s) but below setup_stall_s (600s) stays quiet.
    quiet = lg.evaluate_vitals_and_stall_guard(
        vitals_text=bundle_two_zero,
        idle_seconds=599.9,
        setup_idle_seconds=900.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert quiet["tripped"] is False
    assert quiet["code"] is None

    # At idle_seconds >= setup_stall_s (600s), phase=bundle trips STALL_GUARD_TRIPPED.
    tripped = lg.evaluate_vitals_and_stall_guard(
        vitals_text=bundle_two_zero,
        idle_seconds=600.0,
        setup_idle_seconds=900.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert tripped["tripped"] is True
    assert tripped["code"] == "STALL_GUARD_TRIPPED"
    assert "phase=bundle" in (tripped["reason"] or "")

    # cgroup OOM kill in phase=bundle still trips DEAD_HARNESS_TRIPPED immediately.
    bundle_oom = (
        "=== VITALS 2026-11-11T05:01:00Z ===\n"
        "CGROUP_MEM: oom_kill 1\n"
        "PROC:\n"
        'HARNESS: {"phase": "bundle"}\n'
    )
    oom_res = lg.evaluate_vitals_and_stall_guard(
        vitals_text=bundle_oom,
        idle_seconds=5.0,
        stall_s=300.0,
        setup_stall_s=600.0,
    )
    assert oom_res["tripped"] is True
    assert oom_res["code"] == "DEAD_HARNESS_TRIPPED"
    assert oom_res["cgroup_oom"] is True


def test_detached_worker_and_poll_primitives_in_process_and_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import os
    import shutil
    import tarfile
    import time
    import remote_runner as rr

    content_root = tmp_path / "vm_content"
    content_root.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "launch_guards.py", content_root / "launch_guards.py")

    # 1. Missing SDLAB_REMOTE_SCRIPT in run_detached_worker & start_detached_worker
    rc_missing = lg.run_detached_worker(content_root, env={"PATH": os.environ.get("PATH", "")})
    assert rc_missing == 2
    poll_missing = lg.poll_detached_output(content_root, offset=0)
    assert poll_missing["done"] is True
    assert poll_missing["eof"] is True
    assert poll_missing["rc"] == 2
    assert "SDLAB_REMOTE_RC=2" in poll_missing["chunk"]

    with pytest.raises(ValueError, match="SDLAB_REMOTE_SCRIPT is required"):
        lg.start_detached_worker(content_root, script_path="", env={})

    # 2. Unknown SDLAB_RUNNER_MODE in remote_runner
    rc_bad_mode = rr.run_remote_script("ignored.sh", env={"SDLAB_RUNNER_MODE": "bogus"})
    cap_bad = capsys.readouterr()
    assert rc_bad_mode == 2
    assert "SDLAB_REMOTE_RC=2" in cap_bad.out

    # 3. Partial-line truncation while running + worker_dead detection
    lg.clear_detached_state(content_root)
    log_p = content_root / lg.DETACHED_LIVE_LOG
    meta_p = content_root / lg.DETACHED_LIVE_META
    log_p.write_bytes(b"first_complete_line\npartial_tail_without_nl")
    meta_p.write_text(json.dumps({"worker_pid": os.getpid(), "child_pid": None}) + "\n", encoding="utf-8")
    p_live = lg.poll_detached_output(content_root, offset=0)
    assert p_live["done"] is False
    assert p_live["eof"] is False
    assert p_live["chunk"] == "first_complete_line\n"
    assert p_live["next_offset"] == len(b"first_complete_line\n")
    # Polling at partial tail while worker is still alive returns empty chunk and unchanged offset
    p_wait = lg.poll_detached_output(content_root, offset=p_live["next_offset"])
    assert p_wait["chunk"] == ""
    assert p_wait["next_offset"] == p_live["next_offset"]

    # Simulate dead worker PID without .sdlab_live.done -> drains remaining tail and sets worker_dead=True
    meta_p.write_text(json.dumps({"worker_pid": 99999999, "child_pid": None}) + "\n", encoding="utf-8")
    p_dead = lg.poll_detached_output(content_root, offset=p_live["next_offset"])
    assert p_dead["done"] is True
    assert p_dead["worker_dead"] is True
    assert p_dead["eof"] is True
    assert p_dead["chunk"] == "partial_tail_without_nl"

    # 4. Full start -> poll (chunked) -> download-prep -> apply_detached_poll_response -> kill lifecycle
    bundle_src = content_root / "payload.txt"
    bundle_src.write_text("hello-bundle\n", encoding="utf-8")
    with tarfile.open(content_root / "mini_bundle.tar.gz", "w:gz") as tf:
        tf.add(bundle_src, arcname="payload.txt")

    script = tmp_path / "detached_job.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'ROW_ALPHA hf_1234567890abcdefghij'\n"
        "echo 'ROW_BETA colab-runtime-proxy-token=tok_xyz_999'\n"
        "exit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    run_env = {
        "PATH": os.environ.get("PATH", ""),
        "SDLAB_CONTENT": str(content_root),
        "SDLAB_REMOTE_SCRIPT": script.resolve().as_posix(),
        "SDLAB_DL_CHUNK_BYTES": "4096",
        "SDLAB_RUNNER_MODE": "start",
    }
    rc_start = rr.run_remote_script(env=run_env)
    cap_start = capsys.readouterr()
    assert rc_start == 0
    assert lg.DETACHED_STARTED_PREFIX in cap_start.out

    # Wait for detached worker to finish
    deadline = time.monotonic() + 10.0
    while not (content_root / lg.DETACHED_LIVE_DONE).is_file():
        assert time.monotonic() < deadline, "detached worker did not finish in time"
        time.sleep(0.05)

    vitals_dest = tmp_path / "rig_vitals.log"
    poll_file = tmp_path / "poll_stdout.txt"
    offset = 0
    polls_taken = 0
    while True:
        polls_taken += 1
        rc_p = rr.run_remote_script(
            env={
                "SDLAB_CONTENT": str(content_root),
                "SDLAB_RUNNER_MODE": "poll",
                "SDLAB_POLL_OFFSET": str(offset),
                "SDLAB_POLL_MAX_BYTES": "1024",
            }
        )
        assert rc_p == 0
        poll_out = capsys.readouterr().out
        poll_file.write_text(poll_out, encoding="utf-8")
        rc_apply = lg.main(["--apply-poll-file", str(poll_file), "--apply-poll-vitals", str(vitals_dest)])
        assert rc_apply == 0
        apply_line = capsys.readouterr().out.strip()
        parts = apply_line.split("\t")
        offset = int(parts[0])
        if parts[2] == "1":
            assert parts[3] == "0"
            break
        assert polls_taken < 20

    vitals_text = vitals_dest.read_text(encoding="utf-8")
    assert "ROW_ALPHA hf_[REDACTED]" in vitals_text
    assert "hf_1234567890abcdefghij" not in vitals_text
    assert "tok_xyz_999" not in vitals_text
    assert "SDLAB_DOWNLOAD_PREPARE_JSON" in vitals_text
    assert "SDLAB_REMOTE_RC=0" in vitals_text

    # Error handling in --apply-poll-file and kill mode
    assert lg.main(["--apply-poll-file", str(tmp_path / "missing_poll.txt")]) == 2
    poll_file.write_text("NO_ENVELOPE_HERE\n", encoding="utf-8")
    assert lg.main(["--apply-poll-file", str(poll_file), "--apply-poll-vitals", str(vitals_dest)]) == 1
    capsys.readouterr()

    with pytest.raises(ValueError, match="malformed SDLAB_POLL_ENVELOPE"):
        lg.apply_detached_poll_response(
            lg.DETACHED_POLL_PREFIX + json.dumps({"ok": True, "offset": 10, "next_offset": 5, "chunk": ""}),
            vitals_dest,
        )

    rc_kill = rr.run_remote_script(env={"SDLAB_CONTENT": str(content_root), "SDLAB_RUNNER_MODE": "kill"})
    cap_kill = capsys.readouterr()
    assert rc_kill == 0
    assert lg.DETACHED_KILLED_PREFIX in cap_kill.out


def test_detached_poll_survives_transient_nic_and_usage_blip_and_refuses_when_exhausted(tmp_path: Path) -> None:
    import shutil

    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc

    launcher = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash_bin = str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")

    # 1. Transient full-NIC blip across 3 consecutive polls (both `colab exec` poll AND `colab usage` fail)
    # recovers cleanly without false STALL_GUARD_TRIPPED or COLAB_USAGE_PARSE_FAILED.
    _, state_blip, env_blip = fc.make_fake_colab_env(tmp_path / "blip_ok_case")
    env_blip["FAKE_COLAB_MODE"] = "setup_phase"
    env_blip["FAKE_COLAB_SETUP_DURATION_S"] = "1.8"
    env_blip["GUARD_POLL_INTERVAL_S"] = "0.15"
    env_blip["FAKE_COLAB_POLL_FAIL_CALLS"] = "2,3,4"
    env_blip["FAKE_COLAB_USAGE_FAIL_DURING_BLIP"] = "1"
    env_blip["SDLAB_TEST_POLL_RETRY_SLEEP_S"] = "0.1"
    env_blip["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "0.05,0.05"
    out_blip = tmp_path / "out_blip_ok"
    res_blip = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_blip), "--session", "sdlab-l1-blip-ok"],
        env=env_blip,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_blip.returncode == 0, f"STDOUT:\n{res_blip.stdout}\nSTDERR:\n{res_blip.stderr}"
    guards_blip = (out_blip / "guards.log").read_text(encoding="utf-8")
    assert "DETACHED_POLL_RETRY attempt=1/" in guards_blip
    assert "DETACHED_POLL_RETRY attempt=3/" in guards_blip
    assert "DETACHED_POLL_RECOVERED after_failures=3" in guards_blip
    assert re.search(r"^USAGE_POLL_RETRY attempt=1/3 .* rc=1 ", guards_blip, re.M)
    assert re.search(r"^USAGE_POLL_RETRY attempt=2/3 .* rc=1 ", guards_blip, re.M)
    assert "USAGE_POLL_RECOVERED attempt=3/3" in guards_blip
    assert "REFUSED: COLAB_USAGE_PARSE_FAILED" not in guards_blip
    assert '"code": "COLAB_USAGE_PARSE_FAILED"' not in guards_blip
    assert "STALL_GUARD_TRIPPED" not in guards_blip
    win_blip = json.loads((out_blip / "window.json").read_text(encoding="utf-8"))
    assert win_blip["refusal_code"] is None
    assert "LANE1_STUB_OK" in (out_blip / "vitals.log").read_text(encoding="utf-8")

    # 2. Persistent poll outage beyond max retries refuses with POLL_RECONNECT_EXHAUSTED and stops VM.
    _, state_exh, env_exh = fc.make_fake_colab_env(tmp_path / "blip_exh_case")
    env_exh["FAKE_COLAB_MODE"] = "stall"
    env_exh["GUARD_POLL_INTERVAL_S"] = "0.1"
    env_exh["FAKE_COLAB_POLL_FAIL_CALLS"] = "all"
    env_exh["FAKE_COLAB_USAGE_FAIL_DURING_BLIP"] = "1"
    env_exh["SDLAB_TEST_POLL_MAX_RETRIES"] = "2"
    env_exh["SDLAB_TEST_POLL_RETRY_SLEEP_S"] = "0.05"
    out_exh = tmp_path / "out_blip_exh"
    res_exh = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_exh), "--session", "sdlab-l1-blip-exh"],
        env=env_exh,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_exh.returncode != 0
    win_exh = json.loads((out_exh / "window.json").read_text(encoding="utf-8"))
    assert win_exh["refusal_code"] == "POLL_RECONNECT_EXHAUSTED"
    assert "STOP -s sdlab-l1-blip-exh" in (state_exh / "stops.log").read_text(encoding="utf-8")

    # 3. Transient one-shot start failure and standalone `colab usage` timeout (rc=124) retry cleanly;
    # persistent start failure refuses with DETACHED_START_FAILED.
    _, state_s1, env_s1 = fc.make_fake_colab_env(tmp_path / "start_retry_ok_case")
    env_s1["FAKE_COLAB_START_FAIL_ONCE"] = "1"
    # Calls 2 and 3 are the first post-open `colab usage` sequence (#83 polls asynchronously, so a short run
    # makes fewer live calls than a synchronous poll per tick did); call 4 recovers on attempt 3.
    env_s1["FAKE_COLAB_USAGE_FAIL_CALLS"] = "2,3"
    env_s1["SDLAB_TEST_DETACHED_START_RETRY_SLEEP_S"] = "0.05"
    env_s1["SDLAB_TEST_USAGE_POLL_BACKOFF_S"] = "0.05,0.05"
    out_s1 = tmp_path / "out_start_retry_ok"
    res_s1 = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_s1), "--session", "sdlab-l1-start-retry"],
        env=env_s1,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_s1.returncode == 0, f"STDOUT:\n{res_s1.stdout}\nSTDERR:\n{res_s1.stderr}"
    guards_s1 = (out_s1 / "guards.log").read_text(encoding="utf-8")
    assert "DETACHED_START_RETRY attempt=1/3" in guards_s1
    assert re.search(r"^USAGE_POLL_RETRY attempt=1/3 .* rc=124 ", guards_s1, re.M)
    assert re.search(r"^USAGE_POLL_RETRY attempt=2/3 .* rc=124 ", guards_s1, re.M)
    assert "USAGE_POLL_RECOVERED attempt=3/3" in guards_s1
    assert "REFUSED: COLAB_USAGE_PARSE_FAILED" not in guards_s1
    assert '"code": "COLAB_USAGE_PARSE_FAILED"' not in guards_s1

    _, state_sf, env_sf = fc.make_fake_colab_env(tmp_path / "start_fail_case")
    env_sf["FAKE_COLAB_START_FAIL"] = "1"
    env_sf["SDLAB_TEST_DETACHED_START_RETRY_SLEEP_S"] = "0.05"
    out_sf = tmp_path / "out_start_fail"
    res_sf = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_sf), "--session", "sdlab-l1-start-fail"],
        env=env_sf,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_sf.returncode != 0
    win_sf = json.loads((out_sf / "window.json").read_text(encoding="utf-8"))
    assert win_sf["refusal_code"] == "DETACHED_START_FAILED"
    assert "STOP -s sdlab-l1-start-fail" in (state_sf / "stops.log").read_text(encoding="utf-8")


def test_b1_run_phase_longer_than_stall_s_counts_run_rows_as_progress(tmp_path: Path) -> None:
    import shutil

    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc

    launcher = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash_bin = str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")

    _, state_b1, env_b1 = fc.make_fake_colab_env(tmp_path / "b1_case")
    # 26 rows * 0.25s = ~6.5s in phase=run, well past STALL_S=3s.
    env_b1["STALL_S"] = "3"
    env_b1["GUARD_POLL_INTERVAL_S"] = "0.25"
    env_b1["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.25"
    env_b1["FAKE_RUN_ROWS_N"] = "26"
    env_b1["FAKE_RUN_ROW_SLEEP_S"] = "0.25"
    out_b1 = tmp_path / "out_b1"
    res_b1 = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_b1), "--session", "sdlab-l1-b1-progress"],
        env=env_b1,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res_b1.returncode == 0, (
        f"rc={res_b1.returncode}\nGUARDS:\n{(out_b1 / 'guards.log').read_text(encoding='utf-8') if (out_b1 / 'guards.log').is_file() else ''}\n"
        f"STDERR:\n{res_b1.stderr}"
    )
    guards_b1 = (out_b1 / "guards.log").read_text(encoding="utf-8")
    assert "STALL_GUARD_TRIPPED" not in guards_b1
    win_b1 = json.loads((out_b1 / "window.json").read_text(encoding="utf-8"))
    assert win_b1["refusal_code"] is None
    vitals_b1 = (out_b1 / "vitals.log").read_text(encoding="utf-8")
    for idx in range(1, 27):
        assert f"RENDER_ROW idx={idx}/26 job=stub_{idx} status=ok" in vitals_b1
    assert "LANE1_STUB_OK" in vitals_b1
    assert "STOP -s sdlab-l1-b1-progress" in (state_b1 / "stops.log").read_text(encoding="utf-8")


def test_b2_lost_start_reply_is_idempotent_across_all_three_q1_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import os
    import shutil
    import time
    import remote_runner as rr

    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc

    launcher = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash_bin = str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")

    # Case 1 (Q1): reply lost BEFORE the fork (cell never ran) -> attempt 2 spawns the single worker.
    _, state_pre, env_pre = fc.make_fake_colab_env(tmp_path / "b2_pre_fork")
    env_pre["FAKE_COLAB_START_FAIL_ONCE"] = "1"
    env_pre["GUARD_POLL_INTERVAL_S"] = "0.15"
    env_pre["SDLAB_TEST_DETACHED_START_RETRY_SLEEP_S"] = "0.05"
    out_pre = tmp_path / "out_b2_pre"
    res_pre = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_pre), "--session", "sdlab-l1-b2-pre"],
        env=env_pre,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_pre.returncode == 0, res_pre.stderr
    assert int((state_pre / "start_calls.txt").read_text(encoding="utf-8").strip()) == 2
    runs_pre = [ln for ln in (state_pre / "remote_script_runs.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(runs_pre) == 1
    assert "DETACHED_START_RETRY attempt=1/3 rc=1" in (out_pre / "guards.log").read_text(encoding="utf-8")

    # Case 3 end-to-end (Q1): reply lost AFTER the start cell ran on the VM (`FAKE_COLAB_START_LOST_AFTER_RUN_ONCE=1`) ->
    # attempt 2 sees the already-running worker, reports SDLAB_DETACHED_STARTED with already_running=true,
    # and exactly ONE worker runs to completion.
    _, state_post, env_post = fc.make_fake_colab_env(tmp_path / "b2_post_fork_e2e")
    env_post["FAKE_COLAB_START_LOST_AFTER_RUN_ONCE"] = "1"
    env_post["FAKE_RUN_ROWS_N"] = "8"
    env_post["FAKE_RUN_ROW_SLEEP_S"] = "0.2"
    env_post["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_post["SDLAB_TEST_DETACHED_START_RETRY_SLEEP_S"] = "0.1"
    out_post = tmp_path / "out_b2_post"
    res_post = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_post), "--session", "sdlab-l1-b2-post"],
        env=env_post,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res_post.returncode == 0, res_post.stderr
    assert int((state_post / "start_calls.txt").read_text(encoding="utf-8").strip()) == 2
    runs_post = [ln for ln in (state_post / "remote_script_runs.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(runs_post) == 1, f"expected 1 remote worker run, got {len(runs_post)}: {runs_post}"
    guards_post = (out_post / "guards.log").read_text(encoding="utf-8")
    assert "DETACHED_START_RETRY attempt=1/3 rc=1" in guards_post
    assert "DETACHED_START_ALREADY_RUNNING attempt=2/3" in guards_post
    win_post = json.loads((out_post / "window.json").read_text(encoding="utf-8"))
    assert win_post["refusal_code"] is None
    vitals_post = (out_post / "vitals.log").read_text(encoding="utf-8")
    for idx in range(1, 9):
        assert f"RENDER_ROW idx={idx}/8 job=stub_{idx} status=ok" in vitals_post
    assert "LANE1_STUB_OK" in vitals_post

    # Direct VM-side verification of Q1 Case 2 (reply lost after the fork, BEFORE meta file exists)
    # and Case 3 (reply lost AFTER meta file is written, plus fast-completion under the same start_token).
    vm_root = tmp_path / "vm_idempotent"
    vm_root.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "launch_guards.py", vm_root / "launch_guards.py")
    runs_counter = tmp_path / "direct_runs.txt"
    slow_script = tmp_path / "slow_worker.sh"
    slow_script.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$$\" >> '{fc._to_posix(runs_counter)}'\n"
        "echo 'WORKER_LINE_1'\n"
        "sleep 1.2\n"
        "echo 'WORKER_LINE_2'\n"
        "exit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    start_env = {
        "PATH": os.environ.get("PATH", ""),
        "SDLAB_CONTENT": str(vm_root),
        "SDLAB_REMOTE_SCRIPT": fc._to_posix(slow_script),
        "SDLAB_RUNNER_MODE": "start",
        "SDLAB_START_TOKEN": "tok-win-1",
    }
    try:
        assert rr.run_remote_script(env=start_env) == 0
        out1 = capsys.readouterr().out.strip()
        rec1 = json.loads(out1[len(lg.DETACHED_STARTED_PREFIX) :])
        assert rec1["already_running"] is False
        wpid = rec1["worker_pid"]

        # Wait until worker has written at least its first line and meta file (Case 3: meta file written).
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if (vm_root / lg.DETACHED_LIVE_META).is_file() and (vm_root / lg.DETACHED_LIVE_LOG).stat().st_size > 0:
                break
            time.sleep(0.05)

        assert rr.run_remote_script(env=start_env) == 0
        out2 = capsys.readouterr().out.strip()
        rec2 = json.loads(out2[len(lg.DETACHED_STARTED_PREFIX) :])
        assert rec2["already_running"] is True
        assert rec2["worker_pid"] == wpid
        assert (vm_root / lg.DETACHED_LIVE_LOG).stat().st_size > 0

        # Case 2 (Q1): simulate reply lost right after Popen fork, BEFORE `.sdlab_live.meta.json` exists on disk.
        (vm_root / lg.DETACHED_LIVE_META).unlink(missing_ok=True)
        assert rr.run_remote_script(env=start_env) == 0
        out3 = capsys.readouterr().out.strip()
        rec3 = json.loads(out3[len(lg.DETACHED_STARTED_PREFIX) :])
        assert rec3["already_running"] is True
        assert rec3["worker_pid"] == wpid
        assert (vm_root / lg.DETACHED_LIVE_META).is_file()

        # Wait for worker to finish, then retry with the SAME SDLAB_START_TOKEN -> still idempotent!
        deadline = time.monotonic() + 5.0
        while not (vm_root / lg.DETACHED_LIVE_DONE).is_file():
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert rr.run_remote_script(env=start_env) == 0
        out4 = capsys.readouterr().out.strip()
        rec4 = json.loads(out4[len(lg.DETACHED_STARTED_PREFIX) :])
        assert rec4["already_running"] is True

        direct_runs = [ln for ln in runs_counter.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(direct_runs) == 1
    finally:
        lg.stop_detached_worker(vm_root)


def test_f1_bundle_now_stops_detached_worker_first_without_racing_download_prep(tmp_path: Path) -> None:
    import argparse
    import os
    import shutil
    import time

    sys.path.insert(0, str(REPO_ROOT / "scripts" / "colab"))
    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc
    import lane3_bundle_now as lbn
    import lane3_rung as lr

    # Part A: `rung_pids` & `run_bundle_now` SIGKILL `--detached-worker` strictly BEFORE child processes.
    syn_root = tmp_path / "syn_content"
    (syn_root / "lane3_out").mkdir(parents=True)
    (syn_root / "lane3_train" / "job").mkdir(parents=True)
    (syn_root / "lane3_train" / "job" / "job_000000020.safetensors").write_bytes(b"CKPT")
    proc = tmp_path / "syn_proc"
    for pid, cmd in (
        (11, f"bash {syn_root}/remote_lane3_stub.sh"),
        (12, f"python {syn_root}/ai-toolkit/run.py job.yaml"),
        (19, f"python /content/launch_guards.py --detached-worker --content-root {syn_root}"),
    ):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "cmdline").write_bytes(cmd.replace(" ", "\0").encode("utf-8"))
    killed: list[int] = []
    assert lr.run_bundle_now(
        argparse.Namespace(content=str(syn_root), rc=93, settle_s=0.0),
        kill=lambda p, _s: killed.append(p),
        proc=proc,
    ) == 0
    assert killed[0] == 19
    assert sorted(killed) == [11, 12, 19]

    # Part B: Real live `--detached-worker` running hung `remote_lane3_stub.sh` with `SDLAB_DL_CHUNK_BYTES=4096`.
    # `lane3_bundle_now.bundle_now` kills `--detached-worker` first so child EOF NEVER triggers
    # `prepare_content_downloads` inside the worker alongside salvage's own tar + split.
    vm_root = tmp_path / "live_vm"
    (vm_root / "lane3_out").mkdir(parents=True)
    (vm_root / "lane3_train" / "job").mkdir(parents=True)
    (vm_root / "lane3_train" / "job" / "job_000000020.safetensors").write_bytes(os.urandom(12_000))
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "launch_guards.py", vm_root / "launch_guards.py")
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "lane3_rung.py", vm_root / "lane3_rung.py")
    hung_stub = vm_root / "remote_lane3_stub.sh"
    hung_stub.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'HUNG_LANE3_STARTED'\n"
        "sleep 60\n",
        encoding="utf-8",
        newline="\n",
    )
    started = lg.start_detached_worker(
        vm_root,
        script_path=fc._to_posix(hung_stub),
        env={
            "PATH": os.environ.get("PATH", ""),
            "SDLAB_CONTENT": str(vm_root),
            "SDLAB_DL_CHUNK_BYTES": "4096",
        },
    )
    wpid = int(started["worker_pid"])
    cpid = 0
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if (vm_root / lg.DETACHED_LIVE_META).is_file():
                meta = json.loads((vm_root / lg.DETACHED_LIVE_META).read_text(encoding="utf-8"))
                cpid = int(meta.get("child_pid") or 0)
                if cpid > 0 and (vm_root / lg.DETACHED_LIVE_LOG).stat().st_size > 0:
                    break
            time.sleep(0.05)
        assert cpid > 0 and lg._pid_is_alive(wpid) and lg._pid_is_alive(cpid)

        bn_rc = lbn.bundle_now(
            {
                **os.environ,
                "SDLAB_CONTENT": str(vm_root),
                "SDLAB_BUNDLE_RC": "93",
                "SDLAB_DL_CHUNK_BYTES": "4096",
            }
        )
        assert bn_rc == 0
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and (lg._pid_is_alive(wpid) or lg._pid_is_alive(cpid)):
            time.sleep(0.05)
        assert not lg._pid_is_alive(wpid)
        assert not lg._pid_is_alive(cpid)
        assert not (vm_root / lg.DETACHED_LIVE_DONE).exists()
        live_log = (vm_root / lg.DETACHED_LIVE_LOG).read_text(encoding="utf-8")
        assert "SDLAB_DOWNLOAD_PREPARE_JSON" not in live_log
        assert "SDLAB_REMOTE_RC=" not in live_log
        salvage_manifest = vm_root / ".sdlab_dl_lane3_stub_bundle.tar.gz.manifest.json"
        assert salvage_manifest.is_file()
        manifest_obj = json.loads(salvage_manifest.read_text(encoding="utf-8"))
        assert manifest_obj["part_count"] >= 2
    finally:
        lg.stop_detached_worker(vm_root, sig=9)


def test_f2_poll_outage_wall_bound_trips_reconnect_exhausted_within_stall_s(tmp_path: Path) -> None:
    import re
    import shutil
    import time

    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc

    launcher = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash_bin = str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")

    _, state_f2, env_f2 = fc.make_fake_colab_env(tmp_path / "f2_outage_bound")
    env_f2["FAKE_COLAB_MODE"] = "stall"
    env_f2["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_f2["FAKE_COLAB_POLL_FAIL_CALLS"] = "all"
    env_f2["SDLAB_TEST_POLL_MAX_RETRIES"] = "30"
    env_f2["SDLAB_TEST_POLL_RETRY_SLEEP_S"] = "0.6"
    env_f2["SDLAB_TEST_POLL_OUTAGE_MAX_S"] = "2"
    out_f2 = tmp_path / "out_f2"
    t0 = time.monotonic()
    res_f2 = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_f2), "--session", "sdlab-l1-f2-bound"],
        env=env_f2,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    wall_elapsed = time.monotonic() - t0
    assert res_f2.returncode != 0
    win_f2 = json.loads((out_f2 / "window.json").read_text(encoding="utf-8"))
    assert win_f2["refusal_code"] == "POLL_RECONNECT_EXHAUSTED"
    guards_f2 = (out_f2 / "guards.log").read_text(encoding="utf-8")
    retry_attempts = [int(m) for m in re.findall(r"DETACHED_POLL_RETRY attempt=(\d+)/30", guards_f2)]
    assert 1 <= len(retry_attempts) <= 8, f"expected outage wall bound to stop well before 30 retries, got {retry_attempts}"
    assert wall_elapsed < 15.0
    assert "STOP -s sdlab-l1-f2-bound" in (state_f2 / "stops.log").read_text(encoding="utf-8")


def test_f3_detached_out_files_scrubbed_including_sigterm_during_wait(tmp_path: Path) -> None:
    import signal
    import shutil
    import time

    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc

    launcher = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
    window_sh = REPO_ROOT / "scripts" / "colab" / "colab_window.sh"
    guards_py = REPO_ROOT / "scripts" / "colab" / "launch_guards.py"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash_bin = str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")

    # Part A: `colab_scrub_all_logs` directly scrubs `.detached_start.out` and `.detached_poll.out`.
    scrub_dir = tmp_path / "scrub_unit"
    scrub_dir.mkdir(parents=True)
    fake_hf_a = "hf_" + ("AbCdEfGh" * 4)
    raw_secret = (
        "url=https://x?colab-runtime-proxy-token=tok_proxy_111&access_token=tok_acc_222\n"
        "Authorization: Bearer tok_bearer_333\n"
        f"{fake_hf_a}\n"
    )
    (scrub_dir / ".detached_start.out").write_text(raw_secret, encoding="utf-8")
    (scrub_dir / ".detached_poll.out").write_text(raw_secret, encoding="utf-8")
    res_scrub = subprocess.run(
        [
            bash_bin,
            "-c",
            f'source "{fc._to_posix(window_sh)}"; colab_scrub_all_logs "{fc._to_posix(Path(sys.executable))}" "{fc._to_posix(guards_py)}" "{fc._to_posix(scrub_dir)}"',
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert res_scrub.returncode == 0, res_scrub.stderr
    for fname in (".detached_start.out", ".detached_poll.out"):
        text = (scrub_dir / fname).read_text(encoding="utf-8")
        assert "colab-runtime-proxy-token=[REDACTED]" in text
        assert "access_token=[REDACTED]" in text
        assert "Bearer [REDACTED]" in text
        assert "hf_[REDACTED]" in text
        for leaked in ("tok_proxy_111", "tok_acc_222", "tok_bearer_333", fake_hf_a):
            assert leaked not in text

    # Part B: Real SIGTERM delivered to `launch_lane1_stub.sh` while blocked in `wait "${EXEC_PID}"`
    # on a hung poll that emitted proxy + HF tokens into `.detached_poll.out`.
    _, state_term, env_term = fc.make_fake_colab_env(tmp_path / "f3_term_wait")
    env_term["GUARD_POLL_INTERVAL_S"] = "0.15"
    env_term["FAKE_COLAB_POLL_HANG_WITH_TOKEN_AT"] = "1"
    out_term = tmp_path / "out_f3_term"
    proc = subprocess.Popen(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_term), "--session", "sdlab-l1-f3-term"],
        env=env_term,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        poll_out_p = out_term / ".detached_poll.out"
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if (state_term / "poll_hang_ready.txt").is_file() and poll_out_p.is_file() and poll_out_p.stat().st_size > 0:
                break
            assert proc.poll() is None, "launcher exited before poll hung"
            time.sleep(0.05)
        assert (state_term / "poll_hang_ready.txt").is_file() and poll_out_p.is_file() and poll_out_p.stat().st_size > 0
        proc.send_signal(signal.SIGTERM)
        _, stderr_term = proc.communicate(timeout=30)
        assert proc.returncode == 143, stderr_term
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    assert (out_term / ".detached_poll.out").is_file()
    scrubbed_poll_out = (out_term / ".detached_poll.out").read_text(encoding="utf-8")
    assert "colab-runtime-proxy-token=[REDACTED]" in scrubbed_poll_out
    assert "hf_[REDACTED]" in scrubbed_poll_out
    fake_hf_b = "hf_" + ("PollWaitTok" * 3)
    for p in out_term.rglob("*"):
        if p.is_file():
            content_str = p.read_bytes().decode("utf-8", errors="replace")
            assert "secret_poll_wait_tok_333" not in content_str, f"leaked proxy token in {p}"
            assert fake_hf_b not in content_str, f"leaked HF token in {p}"
    assert "STOP -s sdlab-l1-f3-term" in (state_term / "stops.log").read_text(encoding="utf-8")


def test_f4_worker_stderr_scrubbed_on_vm_and_fetched_on_normal_and_crash_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import shutil
    import tarfile
    import time

    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc

    # Part A: Worker started via `start_detached_worker` routes stderr to `.sdlab_live.err.log` (not DEVNULL),
    # survives invalid UTF-8 bytes from child stdout (`errors="replace"`), scrubs tokens in `.sdlab_live.err.log`,
    # and returns scrubbed `worker_stderr` on `eof=True` so `apply_detached_poll_response` writes
    # `<out_dir>/detached_worker_stderr.log`.
    vm_root = tmp_path / "f4_vm_live"
    vm_root.mkdir(parents=True)
    bad_utf8_script = tmp_path / "emit_bad_utf8.sh"
    bad_utf8_script.write_bytes(
        b"#!/usr/bin/env bash\n"
        b"printf 'BAD_UTF8_LINE:\\xff\\xfe:END\\n'\n"
        b"exit 0\n"
    )
    started = lg.start_detached_worker(
        vm_root,
        script_path=fc._to_posix(bad_utf8_script),
        env={"PATH": os.environ.get("PATH", ""), "SDLAB_CONTENT": str(vm_root)},
    )
    try:
        deadline = time.monotonic() + 5.0
        while not (vm_root / lg.DETACHED_LIVE_DONE).is_file():
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert (vm_root / lg.DETACHED_LIVE_ERR).is_file()
        # Simulate scrubbed diagnostics written to `.sdlab_live.err.log` and verify poll/apply fetches & scrubs it.
        fake_hf_err = "hf_" + ("ErrSecret" * 4)
        (vm_root / lg.DETACHED_LIVE_ERR).write_text(
            f"worker diag: colab-runtime-proxy-token=err_tok_444 {fake_hf_err}\n",
            encoding="utf-8",
        )
        poll_res = lg.poll_detached_output(vm_root, offset=0)
        assert poll_res["eof"] is True
        assert poll_res["rc"] == 0
        assert "BAD_UTF8_LINE:" in poll_res["chunk"]
        assert "err_tok_444" not in poll_res["worker_stderr"]
        assert "colab-runtime-proxy-token=[REDACTED]" in poll_res["worker_stderr"]
        assert "hf_[REDACTED]" in poll_res["worker_stderr"]
        vm_err_after = (vm_root / lg.DETACHED_LIVE_ERR).read_text(encoding="utf-8")
        assert "err_tok_444" not in vm_err_after

        rig_out = tmp_path / "f4_rig_out"
        applied = lg.apply_detached_poll_response(
            f"{lg.DETACHED_POLL_PREFIX} {json.dumps(poll_res)}\n",
            rig_out / "vitals.log",
        )
        assert applied["eof"] is True
        rig_err = (rig_out / "detached_worker_stderr.log").read_text(encoding="utf-8")
        assert "colab-runtime-proxy-token=[REDACTED]" in rig_err
        assert "hf_[REDACTED]" in rig_err
        assert "err_tok_444" not in rig_err
    finally:
        lg.stop_detached_worker(vm_root)

    # Part B: Uncaught exception inside `run_detached_worker` writes scrubbed traceback to worker stderr
    # and `poll_detached_output` + `apply_detached_poll_response` surface it on the rig.
    crash_root = tmp_path / "f4_vm_crash"
    crash_root.mkdir(parents=True)
    err_path = crash_root / lg.DETACHED_LIVE_ERR
    fake_hf_crash = "hf_" + ("CrashSecret" * 3)
    monkeypatch.setattr(
        lg,
        "_resolve_bash_bin",
        lambda _env=None: (_ for _ in ()).throw(
            RuntimeError(f"boom colab-runtime-proxy-token=crash_tok_555 {fake_hf_crash}")
        ),
    )
    with err_path.open("w", encoding="utf-8", newline="\n") as err_fh:
        monkeypatch.setattr(sys, "stderr", err_fh)
        with pytest.raises(RuntimeError):
            lg.run_detached_worker(crash_root, env={"SDLAB_REMOTE_SCRIPT": "/content/fake.sh"})
    crash_err_text = err_path.read_text(encoding="utf-8")
    assert "RuntimeError: boom colab-runtime-proxy-token=[REDACTED] hf_[REDACTED]" in crash_err_text
    assert "crash_tok_555" not in crash_err_text
    assert fake_hf_crash not in crash_err_text

    # Fake a dead worker meta file so `poll_detached_output` detects `worker_dead=True, eof=True` and fetches stderr.
    (crash_root / lg.DETACHED_LIVE_META).write_text(json.dumps({"worker_pid": 99999999}) + "\n", encoding="utf-8")
    crash_poll = lg.poll_detached_output(crash_root, offset=0)
    assert crash_poll["worker_dead"] is True and crash_poll["eof"] is True
    crash_rig = tmp_path / "f4_crash_rig"
    lg.apply_detached_poll_response(
        f"{lg.DETACHED_POLL_PREFIX} {json.dumps(crash_poll)}\n",
        crash_rig / "vitals.log",
    )
    fetched_crash = (crash_rig / "detached_worker_stderr.log").read_text(encoding="utf-8")
    assert "RuntimeError: boom colab-runtime-proxy-token=[REDACTED] hf_[REDACTED]" in fetched_crash
    assert "crash_tok_555" not in fetched_crash

    # Part C: Full end-to-end `launch_lane1_stub.sh` window brings back `detached_worker_stderr.log`
    # both in `<out_dir>/detached_worker_stderr.log` and inside `lane1_stub_bundle.tar.gz`.
    launcher = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash_bin = str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")
    _, _, env_e2e = fc.make_fake_colab_env(tmp_path / "f4_e2e")
    env_e2e["GUARD_POLL_INTERVAL_S"] = "0.15"
    out_e2e = tmp_path / "out_f4_e2e"
    res_e2e = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_e2e), "--session", "sdlab-l1-f4-e2e"],
        env=env_e2e,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert res_e2e.returncode == 0, res_e2e.stderr
    assert (out_e2e / "detached_worker_stderr.log").is_file()
    with tarfile.open(out_e2e / "lane1_stub_bundle.tar.gz", "r:gz") as tf:
        bundle_names = {m.name.removeprefix("./") for m in tf.getmembers()}
    assert "detached_worker_stderr.log" in bundle_names


def test_f6_poll_max_bytes_bounds_each_poll_and_drains_large_backlog(tmp_path: Path) -> None:
    import shutil

    sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
    import fake_colab as fc

    launcher = REPO_ROOT / "scripts" / "colab" / "launch_lane1_stub.sh"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash_bin = str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")

    _, state_f6, env_f6 = fc.make_fake_colab_env(tmp_path / "f6_case")
    env_f6["GUARD_POLL_INTERVAL_S"] = "0.15"
    env_f6["SDLAB_TEST_POLL_MAX_BYTES"] = "1024"
    env_f6["FAKE_RUN_ROWS_N"] = "60"
    env_f6["FAKE_RUN_ROW_SLEEP_S"] = "0.005"
    out_f6 = tmp_path / "out_f6"
    res_f6 = subprocess.run(
        [bash_bin, fc._to_posix(launcher), "--out-dir", fc._to_posix(out_f6), "--session", "sdlab-l1-f6-cap"],
        env=env_f6,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res_f6.returncode == 0, res_f6.stderr
    calls = [
        json.loads(ln)
        for ln in (state_f6 / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    poll_calls = [
        c for c in calls
        if c["subcmd"] == "exec" and "SDLAB_RUNNER_MODE=poll" in c["parsed_opts"].get("--env", [])
    ]
    assert len(poll_calls) >= 3
    for pc in poll_calls:
        assert "SDLAB_POLL_MAX_BYTES=1024" in pc["parsed_opts"].get("--env", [])
    vitals_f6 = (out_f6 / "vitals.log").read_text(encoding="utf-8")
    for idx in range(1, 61):
        assert f"RENDER_ROW idx={idx}/60 job=stub_{idx} status=ok" in vitals_f6
    assert "LANE1_STUB_OK" in vitals_f6


def test_usage_retry_budget_g4_arithmetic_and_wall_only_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert lg.USAGE_POLL_ATTEMPTS == 3
    assert lg.USAGE_POLL_TIMEOUT_S == 30
    assert lg.USAGE_POLL_KILL_GRACE_S == 5
    assert lg.USAGE_POLL_BACKOFF_S == (2, 4)
    assert lg.USAGE_RETRY_BOUND_S == 111
    # Blind interval the gate prices: T_retry + 2 * poll_s + slack_s = 111 + 2 * 2 + 2 = 117 s.
    assert lg.GUARD_POLL_INTERVAL_S_DEFAULT == 2
    assert lg.USAGE_DECISION_SLACK_S == 2
    assert lg.USAGE_BLIND_INTERVAL_S == 117
    assert lg.usage_blind_interval_s(9, 0.4, 2) == 11.8

    g4_ok = lg.compute_usage_retry_budget(priced_rate=10.05, margin=1.0)
    assert g4_ok == {
        "usage_retry_bound_s": 111,
        "usage_blind_interval_s": 117,
        "usage_retry_spend_units": 0.326625,
        "usage_retry_half_margin_units": 0.5,
        "usage_retry_min_margin_units": 0.65325,
        "fits": True,
    }
    # An explicit blind interval (the shell passes --usage-blind-interval-s) is priced as given.
    explicit = lg.compute_usage_retry_budget(priced_rate=10.05, margin=1.0, usage_blind_interval=120)
    assert explicit["usage_blind_interval_s"] == 120
    assert explicit["usage_retry_spend_units"] == 0.335
    # 16.0/hr fitted margin 1.0 at T_retry alone (0.493333) but not at the blind interval (0.52).
    g16 = lg.compute_usage_retry_budget(priced_rate=16.0, margin=1.0)
    assert g16["usage_retry_spend_units"] == 0.52
    assert g16["fits"] is False
    # The highest rate that fits margin 1.0: 0.5 * 3600 / 117 = 15.384615/hr.
    assert lg.compute_usage_retry_budget(priced_rate=15.38, margin=1.0)["fits"] is True
    assert lg.compute_usage_retry_budget(priced_rate=15.39, margin=1.0)["fits"] is False

    g4_refuse = lg.evaluate_cap_budget(
        cap=5.0,
        margin=0.60,
        cleanup_bound_s=450.0,
        priced_rate=10.05,
        max_rate=10.05,
    )
    assert g4_refuse["tripped"] is True
    assert g4_refuse["code"] == "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY"
    assert g4_refuse["usage_retry_spend_units"] == 0.326625
    assert g4_refuse["usage_blind_interval_s"] == 117
    assert g4_refuse["usage_retry_half_margin_units"] == 0.3
    assert g4_refuse["usage_retry_min_margin_units"] == 0.65325
    assert g4_refuse["refusal"]["code"] == "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY"

    rc_refuse = lg.main(
        [
            "--check-cap-budget",
            "--cap",
            "5.0",
            "--margin",
            "0.60",
            "--cleanup-bound-s",
            "450",
            "--rate",
            "10.05",
            "--max-rate",
            "10.05",
        ]
    )
    assert rc_refuse == 2
    captured_refuse = capsys.readouterr()
    assert "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY" in captured_refuse.err

    rc_dry_ok = lg.main(
        [
            "--dry",
            "--cap",
            "5.0",
            "--margin",
            "1.0",
            "--cleanup-bound-s",
            "450",
            "--rate",
            "10.05",
            "--max-rate",
            "10.05",
        ]
    )
    assert rc_dry_ok == 0
    captured_dry = capsys.readouterr()
    assert "usage_retry_bound_s (T_retry): 111" in captured_dry.out
    assert "usage_blind_interval_s (T_retry + 2 * poll_s + slack_s): 117" in captured_dry.out

    rc_dry_explicit = lg.main(
        [
            "--dry",
            "--cap",
            "5.0",
            "--margin",
            "1.0",
            "--cleanup-bound-s",
            "450",
            "--rate",
            "10.05",
            "--max-rate",
            "10.05",
            "--usage-blind-interval-s",
            "120",
        ]
    )
    assert rc_dry_explicit == 0
    assert "usage_blind_interval_s (T_retry + 2 * poll_s + slack_s): 120" in capsys.readouterr().out

    rc_wall_quiet = lg.main(
        [
            "--check-wall-only",
            "--mode",
            "live",
            "--phase",
            "live",
            "--checkpoint",
            "usage_retry",
            "--elapsed-s",
            "10",
            "--wall-s",
            "900",
            "--grace-s",
            "60",
        ]
    )
    assert rc_wall_quiet == 0
    wall_quiet_rec = json.loads(capsys.readouterr().out.strip())
    assert wall_quiet_rec["check"] == "wall_only"
    assert "cap" not in wall_quiet_rec
    assert wall_quiet_rec["wall"]["tripped"] is False

    rc_wall_trip = lg.main(
        [
            "--check-wall-only",
            "--mode",
            "live",
            "--elapsed-s",
            "850",
            "--wall-s",
            "900",
            "--grace-s",
            "60",
        ]
    )
    assert rc_wall_trip == 1
    wall_trip_rec = json.loads(capsys.readouterr().out.strip())
    assert wall_trip_rec["check"] == "wall_only"
    assert "cap" not in wall_trip_rec
    assert wall_trip_rec["refusal"]["code"] == "WALL_GUARD_TRIPPED"

