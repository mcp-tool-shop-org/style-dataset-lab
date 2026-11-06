"""Unit tests for scripts/colab/launch_guards.py (Part B.2)."""

from __future__ import annotations

import json
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
