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

    # Burn-rate fixture without balance poll: 0.24 CCU/hr * 600s = 0.04 CCU
    quiet_rate = lg.evaluate_cap_guard(
        mode="live",
        cap=0.05,
        margin=0.01,
        rate_ccu_per_hour=0.24,
        elapsed_s=599.0,
    )
    assert quiet_rate["tripped"] is False

    tripped_rate = lg.evaluate_cap_guard(
        mode="live",
        cap=0.05,
        margin=0.01,
        rate_ccu_per_hour=0.24,
        elapsed_s=600.0,
    )
    assert tripped_rate["tripped"] is True
    assert tripped_rate["code"] == "CAP_GUARD_TRIPPED"


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

    rc_ok = lg.main(["--mode", "stub", "--elapsed-s", "10", "--wall-s", "900", "--grace-s", "60"])
    assert rc_ok == 0

    rc_trip = lg.main(["--mode", "stub", "--elapsed-s", "850", "--wall-s", "900", "--grace-s", "60"])
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
