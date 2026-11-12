"""Fake-CLI tests for Addendum 1:
- Part 1: `scripts/colab/probe_upload_limit.sh` (upload + download size-limit sweeps, sha256 checks,
  stop-at-first-failure in each direction, token scrubbing, penny cap/wall, guaranteed `colab stop`).
- Part 2: chunked upload in `scripts/colab/colab_window.sh` (`COLAB_UPLOAD_CHUNK_BYTES`, N-part split,
  per-part 1x 5xx retry, named refusal on 2x 500 with session stop, VM whole-file sha256 verification
  catching corrupted parts before use, VM part cleanup, single-upload fast path below chunk size,
  per-part upload timeout check in `lane3_rung.py plan-run`).
- Part 2b: chunked download in `scripts/colab/colab_window.sh` (`COLAB_DOWNLOAD_CHUNK_BYTES`, VM split
  + sha256 manifest on normal and salvage paths, per-part 1x 5xx retry, named failure + exact arrived
  parts list in `window.json` / `outcome.draft.json`, whole-file sha256 check before `colab stop`).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
WINDOW_SH = COLAB_DIR / "colab_window.sh"
LANE1_SH = COLAB_DIR / "launch_lane1_stub.sh"
LANE3_SH = COLAB_DIR / "launch_lane3_stub.sh"
PROBE_SH = COLAB_DIR / "probe_upload_limit.sh"
RUNG_PY = COLAB_DIR / "lane3_rung.py"
FIXTURES = REPO_ROOT / "tests" / "colab" / "fixtures"
sys.path.insert(0, str(FIXTURES))
sys.path.insert(0, str(COLAB_DIR))

import fake_colab as fc  # noqa: E402
import lane3_bundle_now as lbn  # noqa: E402
import lane3_rung as lr  # noqa: E402
import remote_runner as rr  # noqa: E402


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found
    return found


def _p(path: Path) -> str:
    return fc._to_posix(path)


def _run(cmd: list[str], env: dict[str, str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, check=False
    )


def _window_fn(env: dict[str, str], body: str) -> subprocess.CompletedProcess[str]:
    return _run([_bash(), "-c", f'source "{_p(WINDOW_SH)}"\n{body}'], env)


def _assert_no_tokens(out_dir: Path) -> None:
    for fp in out_dir.rglob("*"):
        if fp.is_file() and fp.suffix in (".log", ".json", ".jsonl", ".txt"):
            txt = fp.read_text(encoding="utf-8", errors="replace")
            assert fc.FAKE_CONTENTS_TOKEN not in txt, fp
            assert "secret_proxy_tok_" not in txt, fp
            assert "ya29.secret_oauth_" not in txt, fp


def test_file_under_chunk_size_is_still_one_single_upload(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["COLAB_UPLOAD_CHUNK_BYTES"] = "65536"
    out_dir = tmp_path / "out_single"
    out_dir.mkdir()
    payload = os.urandom(12_345)
    src = tmp_path / "small.bin"
    src.write_bytes(payload)

    res = _window_fn(env, f'colab_upload_checked s1 "{_p(src)}" /content/small.bin "{_p(out_dir)}"')
    assert res.returncode == 0, res.stderr
    assert (state / "content" / "small.bin").read_bytes() == payload

    uploads = [ln for ln in (state / "uploads.log").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(uploads) == 1
    calls = (state / "calls.log").read_text(encoding="utf-8")
    assert "CALL exec" not in calls

    receipts = [
        json.loads(ln)
        for ln in (out_dir / "upload_receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(receipts) == 1
    assert receipts[0]["mode"] == "single"
    assert receipts[0]["chunk_bytes"] == 65536
    assert receipts[0]["part_count"] == 1
    assert receipts[0]["bytes"] == 12_345
    assert receipts[0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipts[0]["ok"] is True


def test_chunked_upload_reassembles_verifies_sha_deletes_parts_and_retries_500_once(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["COLAB_UPLOAD_CHUNK_BYTES"] = "65536"
    # Inject one transient HTTP 500 on part K=1 (the second of 3 parts).
    env["FAKE_COLAB_UPLOAD_HTTP_500_ONCE_FOR"] = ".part.0001"

    out_dir = tmp_path / "out_chunk_up"
    out_dir.mkdir()
    payload = os.urandom(65536 * 2 + 19_999)
    want_sha = hashlib.sha256(payload).hexdigest()
    src = tmp_path / "synth_server.bin"
    src.write_bytes(payload)

    res = _window_fn(
        env,
        f'colab_upload_checked s1 "{_p(src)}" /content/synth_server.bin "{_p(out_dir)}"\n'
        f'colab_scrub_all_logs "$(colab_resolve_python)" "{_p(COLAB_DIR / "launch_guards.py")}" "{_p(out_dir)}"',
    )
    assert res.returncode == 0, res.stderr

    vm_target = state / "content" / "synth_server.bin"
    assert vm_target.is_file()
    assert hashlib.sha256(vm_target.read_bytes()).hexdigest() == want_sha
    # Every temporary `.sdlab_up_*` part and manifest must be deleted on the VM after reassembly.
    leftover = [p.name for p in (state / "content").iterdir() if p.name.startswith(".sdlab_up_")]
    assert leftover == [], leftover

    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "UPLOAD_PART_RETRY" in guards and "part=2/3" in guards and "http=500" in guards

    uploads = (state / "uploads.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for ln in uploads if ln.startswith("UPLOAD_FAILED_500") and ".part.0001" in ln) == 1
    assert sum(1 for ln in uploads if ln.startswith("UPLOAD_OK") and ".part." in ln) == 3

    win_res = _window_fn(
        env,
        f'colab_write_window_and_outcome "$(colab_resolve_python)" "{_p(out_dir)}" render s1 CPU-high-mem '
        f"0.10 900 60 0.01 2026-11-11T00:00:00Z 2026-11-11T00:01:00Z 0 '{{}}'",
    )
    assert win_res.returncode == 0, win_res.stderr
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    outcome = json.loads((out_dir / "outcome.draft.json").read_text(encoding="utf-8"))
    for doc in (win, outcome):
        assert doc["upload_chunk_bytes"] == 65536
        assert len(doc["upload_transfers"]) == 1
        tr = doc["upload_transfers"][0]
        assert tr["mode"] == "chunked"
        assert tr["part_count"] == 3
        assert tr["chunk_bytes"] == 65536
        assert tr["retries"] == 1
        assert tr["sha256"] == want_sha
        assert tr["ok"] is True
    _assert_no_tokens(out_dir)


def test_chunked_upload_500_twice_on_part_k_refuses_by_name_and_stops_session(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    # `remote_lane3_stub.sh` (~44 KB) splits into 3 parts under `--upload-chunk-bytes 16384`;
    # force persistent HTTP 500 on part K=1 (`.part.0001`).
    env["FAKE_COLAB_UPLOAD_HTTP_500_FOR"] = ".part.0001"
    out_dir = tmp_path / "out_up_2x500"

    res = _run(
        [
            _bash(), _p(LANE3_SH),
            "--out-dir", _p(out_dir),
            "--session", "sdlab-l3-uppart500",
            "--upload-chunk-bytes", "16384",
        ],
        env,
    )
    assert res.returncode != 0
    assert "REFUSED: UPLOAD_PART_FAILED:" in res.stderr
    assert "part 2/" in res.stderr and "http=500" in res.stderr and "attempts=2" in res.stderr

    # Session must STILL stop via cleanup_on_exit, and remote_runner.py must never have executed.
    assert "STOP -s sdlab-l3-uppart500" in (state / "stops.log").read_text(encoding="utf-8")
    calls = (state / "calls.log").read_text(encoding="utf-8")
    assert "remote_runner.py" not in calls
    leftover = [p.name for p in (state / "content").iterdir() if p.name.startswith(".sdlab_up_")]
    assert leftover == [], leftover

    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "UPLOAD_PART_FAILED"
    assert win["refusal_code"] == "UPLOAD_PART_FAILED"
    assert win["upload_chunk_bytes"] == 16384
    failed_tr = [t for t in win["upload_transfers"] if not t["ok"]]
    assert len(failed_tr) == 1
    assert failed_tr[0]["failed_part"] == 1
    assert failed_tr[0]["retries"] == 1
    _assert_no_tokens(out_dir)


def test_corrupted_upload_part_is_caught_by_vm_whole_file_sha_before_use_and_stops_session(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    env["FAKE_COLAB_CORRUPT_UPLOAD_PART_FOR"] = ".part.0001"
    out_dir = tmp_path / "out_up_corrupt"

    res = _run(
        [
            _bash(), _p(LANE3_SH),
            "--out-dir", _p(out_dir),
            "--session", "sdlab-l3-upcorrupt",
            "--upload-chunk-bytes", "16384",
        ],
        env,
    )
    assert res.returncode != 0
    assert "REFUSED: UPLOAD_SHA_MISMATCH:" in res.stderr
    assert "VM whole-file sha256=" in res.stderr

    # Refuses BEFORE remote_runner.py runs, removes target + parts on VM, and stops the session.
    calls = (state / "calls.log").read_text(encoding="utf-8")
    assert "remote_runner.py" not in calls
    assert not (state / "content" / "remote_lane3_stub.sh").exists()
    leftover = [p.name for p in (state / "content").iterdir() if p.name.startswith(".sdlab_up_")]
    assert leftover == [], leftover
    assert "STOP -s sdlab-l3-upcorrupt" in (state / "stops.log").read_text(encoding="utf-8")

    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "UPLOAD_SHA_MISMATCH"
    assert win["refusal_code"] == "UPLOAD_SHA_MISMATCH"
    _assert_no_tokens(out_dir)


def test_chunked_download_over_chunk_size_retries_500_once_verifies_sha_and_cleans_vm_parts(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    # Force an incompressible ~180 KB payload inside lane3_stub_bundle.tar.gz so it splits into 3 parts
    # under `--download-chunk-bytes 65536`, and inject one HTTP 500 on part K=1.
    env["FAKE_VM_EXTRA_BUNDLE_BYTES"] = "180000"
    env["FAKE_COLAB_DOWNLOAD_HTTP_500_ONCE_FOR"] = ".part.0001"
    out_dir = tmp_path / "out_dl_chunk_ok"

    res = _run(
        [
            _bash(), _p(LANE3_SH),
            "--out-dir", _p(out_dir),
            "--session", "sdlab-l3-dlchunk-ok",
            "--upload-chunk-bytes", "16384",
            "--download-chunk-bytes", "65536",
        ],
        env,
    )
    assert res.returncode == 0, res.stdout + res.stderr

    vm_bundle = state / "content" / "lane3_stub_bundle.tar.gz"
    rig_bundle = out_dir / "lane3_stub_bundle.tar.gz"
    assert rig_bundle.is_file()
    want_sha = hashlib.sha256(vm_bundle.read_bytes()).hexdigest()
    assert hashlib.sha256(rig_bundle.read_bytes()).hexdigest() == want_sha
    assert rig_bundle.stat().st_size > 131_072

    # N4 bullet 3: no post-download VM `cleanup_dl.py` exec is run (`colab stop` wipes `/content`).
    calls_log = (state / "calls.log").read_text(encoding="utf-8")
    assert "cleanup_dl.py" not in calls_log
    assert "SDLAB_DL_PREFIX=" not in calls_log

    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "DOWNLOAD_PART_RETRY" in guards and "http=500" in guards

    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    outcome = json.loads((out_dir / "outcome.draft.json").read_text(encoding="utf-8"))
    for doc in (win, outcome):
        assert doc["status"] == "ok"
        assert doc["upload_chunk_bytes"] == 16384
        assert doc["download_chunk_bytes"] == 65536
        bd = doc["bundle_download"]
        assert bd["mode"] == "chunked"
        assert bd["part_count"] >= 3
        assert bd["arrived_parts"] == list(range(bd["part_count"]))
        assert bd["retries"] == 1
        assert bd["verified"] is True
        assert bd["whole_sha256_actual"] == want_sha
    assert "STOP -s sdlab-l3-dlchunk-ok" in (state / "stops.log").read_text(encoding="utf-8")
    _assert_no_tokens(out_dir)


def test_chunked_download_two_500s_on_part_k_names_failure_lists_arrived_parts_and_stops_session(
    tmp_path: Path,
) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    # Seed a 3-part bundle (> 131072 bytes under 65536-byte chunks) and force HTTP 500 on part K=2
    # so parts 0 and 1 arrive, part 2 fails twice, no partial bundle is kept, and arrived_parts == [0, 1].
    env["FAKE_COLAB_DOWNLOAD_HTTP_500_FOR"] = ".part.0002"
    out_dir = tmp_path / "out_dl_2x500"
    out_dir.mkdir()
    big_bundle = os.urandom(65536 * 2 + 12_000)
    (state / "content" / "big_bundle.tar.gz").write_bytes(big_bundle)

    # Also test through a full Lane 1 window by having `.fake_remote_lane1_stub.sh` emit > 131 KB bundle.
    fake_l1 = state / "content" / ".fake_remote_lane1_stub.sh"
    fake_l1.write_text(
        fake_l1.read_text(encoding="utf-8").replace(
            "tar -czf lane1_stub_bundle.tar.gz -C lane1_out .",
            '"${SDLAB_PYTHON:-python3}" -c \'import os, pathlib; pathlib.Path("lane1_out/extra.bin").write_bytes(os.urandom(150000))\'\n'
            "tar -czf lane1_stub_bundle.tar.gz -C lane1_out .",
        ),
        encoding="utf-8",
        newline="\n",
    )
    win_dir = tmp_path / "out_l1_dl_fail"
    res = _run(
        [
            _bash(), _p(LANE1_SH),
            "--out-dir", _p(win_dir),
            "--session", "sdlab-l1-dlpart500",
            "--download-chunk-bytes", "65536",
        ],
        env,
    )
    assert res.returncode != 0
    assert "REFUSED: DOWNLOAD_PART_FAILED:" in res.stderr
    assert "part 3/3" in res.stderr and "http=500" in res.stderr and "attempts=2" in res.stderr
    assert "arrived_parts=[0,1]" in res.stderr
    assert not (win_dir / "lane1_stub_bundle.tar.gz").exists(), "never leave a silent partial bundle"

    # Session is NOT stopped until after the download attempts finish, and IS stopped in cleanup.
    calls = [
        ln for ln in (state / "calls.log").read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    last_dl_idx = max(i for i, ln in enumerate(calls) if ln.startswith("CALL download"))
    stop_idx = next(i for i, ln in enumerate(calls) if ln.startswith("CALL stop"))
    assert stop_idx > last_dl_idx
    assert "STOP -s sdlab-l1-dlpart500" in (state / "stops.log").read_text(encoding="utf-8")

    win = json.loads((win_dir / "window.json").read_text(encoding="utf-8"))
    outcome = json.loads((win_dir / "outcome.draft.json").read_text(encoding="utf-8"))
    for doc in (win, outcome):
        assert doc["status"] == "DOWNLOAD_PART_FAILED"
        assert doc["refusal_code"] == "DOWNLOAD_PART_FAILED"
        bd = doc["bundle_download"]
        assert bd["mode"] == "chunked"
        assert bd["part_count"] == 3
        assert bd["arrived_parts"] == [0, 1]
        assert bd["failed_part"] == 2
        assert bd["verified"] is False
    _assert_no_tokens(win_dir)

    # Also verify a corrupted download part is refused as DOWNLOAD_SHA_MISMATCH with exact arrived_parts.
    _, state2, env2 = fc.make_fake_colab_env(tmp_path / "corrupt_dl")
    env2["COLAB_DOWNLOAD_CHUNK_BYTES"] = "65536"
    env2["FAKE_COLAB_CORRUPT_DOWNLOAD_FOR"] = ".part.0001"
    (state2 / "content" / "b.tar.gz").write_bytes(big_bundle)
    c_dir = tmp_path / "corrupt_dl" / "out"
    c_dir.mkdir()
    c_res = _window_fn(env2, f'colab_download_checked s1 /content/b.tar.gz "{_p(c_dir / "b.tar.gz")}" "{_p(c_dir)}"')
    assert c_res.returncode != 0
    assert "REFUSED: DOWNLOAD_SHA_MISMATCH:" in c_res.stderr
    assert not (c_dir / "b.tar.gz").exists()
    bd2 = json.loads((c_dir / "bundle_download.json").read_text(encoding="utf-8"))
    assert bd2["arrived_parts"] == [0]
    assert bd2["failed_part"] == 1
    assert bd2["verified"] is False


def test_salvage_path_uses_chunked_download_above_chunk_size(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["COLAB_DOWNLOAD_CHUNK_BYTES"] = "65536"
    env["FAKE_COLAB_DOWNLOAD_HTTP_500_ONCE_FOR"] = ".part.0001"
    # Seed `/content/lane3_out` with > 150 KB of incompressible output so `lane3_bundle_now.py`
    # writes a > 150 KB `lane3_stub_bundle.tar.gz`, then invoke `colab_salvage_bundle_after_failure`.
    lane3_out = state / "content" / "lane3_out"
    (lane3_out / "rung_outputs").mkdir(parents=True)
    (lane3_out / "rung_outputs" / "ckpt_blob.bin").write_bytes(os.urandom(160_000))
    shutil.copyfile(COLAB_DIR / "launch_guards.py", state / "content" / "launch_guards.py")
    shutil.copyfile(COLAB_DIR / "lane3_rung.py", state / "content" / "lane3_rung.py")

    out_dir = tmp_path / "out_salvage_chunk"
    out_dir.mkdir()
    bundle_now_py = COLAB_DIR / "lane3_bundle_now.py"
    dst = out_dir / "lane3_stub_bundle.tar.gz"
    res = _window_fn(
        env,
        f'colab_salvage_bundle_after_failure s1 "{_p(bundle_now_py)}" '
        f'/content/lane3_stub_bundle.tar.gz "{_p(dst)}" "{_p(out_dir)}" 143',
    )
    assert res.returncode == 0, res.stderr
    assert dst.is_file()
    vm_sha = hashlib.sha256((state / "content" / "lane3_stub_bundle.tar.gz").read_bytes()).hexdigest()
    assert hashlib.sha256(dst.read_bytes()).hexdigest() == vm_sha

    sbd = json.loads((out_dir / "salvage_bundle_download.json").read_text(encoding="utf-8"))
    assert sbd["mode"] == "chunked"
    assert sbd["part_count"] >= 3
    assert sbd["arrived_parts"] == list(range(sbd["part_count"]))
    assert sbd["retries"] == 1
    assert sbd["verified"] is True
    assert "BUNDLE_AFTER_FAILURE: downloaded lane3_stub_bundle.tar.gz" in (out_dir / "guards.log").read_text(
        encoding="utf-8"
    )


def test_chunk_size_validation_and_per_part_plan_run_timeouts(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)

    bad_up = _run([_bash(), _p(LANE1_SH), "--upload-chunk-bytes", "0", "--dry"], env)
    assert bad_up.returncode == 2 and "REFUSED: UPLOAD_CHUNK_BYTES_INVALID:" in bad_up.stderr

    bad_dl = _run([_bash(), _p(LANE1_SH), "--download-chunk-bytes", "abc", "--dry"], env)
    assert bad_dl.returncode == 2 and "REFUSED: DOWNLOAD_CHUNK_BYTES_INVALID:" in bad_dl.stderr
    assert not (state / "calls.log").exists()

    # Verify `lane3_rung.py plan-run` applies upload & download timeouts PER PART.
    job_plan = tmp_path / "job_plan.json"
    job_plan.write_text(
        json.dumps({
            "steps": 40,
            "save_every": 20,
            "sample_every": 20,
            "meta": {
                "seconds_per_step": 1.0,
                "checkpoint_size_bytes": 200_000_000,
                "optimizer_size_bytes": 100_000_000,
                "optimizer_size_source": "estimate: fixture value, no run behind it",
                "samples_and_logs_bytes": 50_000_000,
                "copy_tar_overhead": 2.0,
                "expected_model_bytes": 1_000_000_000,
            },
        }),
        encoding="utf-8",
    )
    archive = tmp_path / "dataset.tar"
    archive.write_bytes(b"a" * 200_000)  # 200 KB total -> 4 parts of 50 KB under --upload-chunk-bytes 50000

    # At 0.001 MB/s (1000 B/s), whole archive would take 200 s, but each 50 KB part takes 50 s <= 60 s!
    # Expected keep-all bundle = 2 * 200 MB + 100 MB optimizer + 50 MB samples/logs = 550 MB;
    # under 150 MB download chunks (4 parts), each part at 10 MB/s takes ceil(150 MB / 10 MB/s) = 15 s.
    out_plan = tmp_path / "run_plan.json"
    rc_ok = lr.main([
        "plan-run",
        "--job-plan", str(job_plan),
        "--is-real-job", "1",
        "--explicit-download-timeout-s", "",
        "--download-timeout-source", "default",
        "--default-download-timeout-s", "300",
        "--download-floor-mb-s", "10.0",
        "--download-chunk-bytes", "150000000",
        "--upload-timeout-s", "60",
        "--upload-timeout-source", "cli",
        "--upload-floor-mb-s", "0.001",
        "--upload-chunk-bytes", "50000",
        "--dataset-archive", str(archive),
        "--download-max-seconds", "100",
        "--setup-allowance-s", "100",
        "--wall-s", "500",
        "--grace-s", "30",
        "--out", str(out_plan),
    ])
    assert rc_ok == 0
    plan = json.loads(out_plan.read_text(encoding="utf-8"))
    assert plan["download_timeout_s"] == 15
    assert plan["bundle_projection"]["expected_bundle_bytes"] == 550_000_000
    assert plan["download_timeout_basis"]["part_count"] == 4
    assert plan["upload_timeout_check"]["part_count"] == 4
    assert plan["upload_timeout_check"]["projected_upload_seconds"] == 50.0
    assert plan["upload_timeout_check"]["projected_total_upload_seconds"] == 200.0
    assert plan["wall_allowance"]["fetch_allowance_s"] == 60  # 4 parts * 15 s/part

    # Lowering per-part upload timeout to 40 s (< 50 s/part) refuses UPLOAD_TIMEOUT_TOO_SHORT.
    rc_short = lr.main([
        "plan-run",
        "--job-plan", str(job_plan),
        "--is-real-job", "1",
        "--download-floor-mb-s", "10.0",
        "--download-chunk-bytes", "150000000",
        "--upload-timeout-s", "40",
        "--upload-timeout-source", "cli",
        "--upload-floor-mb-s", "0.001",
        "--upload-chunk-bytes", "50000",
        "--dataset-archive", str(archive),
        "--download-max-seconds", "100",
        "--setup-allowance-s", "100",
        "--wall-s", "500",
        "--grace-s", "30",
    ])
    assert rc_short == 1


def test_probe_upload_limit_sweeps_both_directions_stops_at_first_500_and_stops_session(
    tmp_path: Path,
) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    # Pre-open refusals and --dry open no session.
    gpu_refused = _run([_bash(), _p(PROBE_SH), "--card", "G4", "--out-dir", _p(tmp_path / "bad_gpu")], env)
    assert gpu_refused.returncode == 2 and "REFUSED: PROBE_CPU_ONLY:" in gpu_refused.stderr
    bad_sizes = _run([_bash(), _p(PROBE_SH), "--upload-sizes-mb", "16,-1", "--out-dir", _p(tmp_path / "bad_sz")], env)
    assert bad_sizes.returncode == 2 and "REFUSED: PROBE_SIZES_INVALID:" in bad_sizes.stderr
    dry = _run([_bash(), _p(PROBE_SH), "--dry"], env)
    assert dry.returncode == 0 and '"cap": 0.2' in dry.stdout
    assert not (state / "calls.log").exists()

    # Upload limit set to 2.5 MiB (1, 2 pass; 3 fails HTTP 500; 4 skipped).
    # Download limit set to 5.0 MiB (2, 4 pass; 6 fails HTTP 500; 8 skipped).
    env["FAKE_COLAB_UPLOAD_MAX_BYTES"] = str(int(2.5 * 1024 * 1024))
    env["FAKE_COLAB_DOWNLOAD_MAX_BYTES"] = str(5 * 1024 * 1024)
    out_dir = tmp_path / "out_probe"

    res = _run(
        [
            _bash(), _p(PROBE_SH),
            "--out-dir", _p(out_dir),
            "--session", "sdlab-probe-limit-1",
            "--cap", "0.20",
            "--wall-s", "600",
            "--grace-s", "30",
            "--upload-sizes-mb", "1,2,3,4",
            "--download-sizes-mb", "2,4,6,8",
        ],
        env,
    )
    assert res.returncode == 0, res.stdout + res.stderr

    # One CPU-high-mem session opened under the open lock and stopped in EXIT trap.
    assert (state / "lock.log").read_text(encoding="utf-8").strip() == "LOCK_HELD=1"
    calls = [ln for ln in (state / "calls.log").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert sum(1 for ln in calls if ln.startswith("CALL new ")) == 1
    assert "STOP -s sdlab-probe-limit-1" in (state / "stops.log").read_text(encoding="utf-8")

    # Neither VM nor rig retains temporary probe binaries.
    assert not (state / "content" / "probe_up.bin").exists()
    assert not (state / "content" / "probe_dl.bin").exists()
    assert not (out_dir / ".probe_work").exists()

    receipt = json.loads((out_dir / "probe_upload_limit.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "ok"
    assert receipt["requested_upload_sizes_mb"] == [1, 2, 3, 4]
    assert receipt["requested_download_sizes_mb"] == [2, 4, 6, 8]

    assert [r["size_mb"] for r in receipt["uploads"]] == [1, 2, 3]
    assert [r["passed"] for r in receipt["uploads"]] == [True, True, False]
    assert all(r["sha256_match"] is True and isinstance(r["seconds"], float) for r in receipt["uploads"][:2])
    assert receipt["uploads"][2]["http_status"] == 500
    assert "500 Server Error" in receipt["uploads"][2]["error_text"]

    assert [r["size_mb"] for r in receipt["downloads"]] == [2, 4, 6]
    assert [r["passed"] for r in receipt["downloads"]] == [True, True, False]
    assert all(r["sha256_match"] is True and isinstance(r["seconds"], float) for r in receipt["downloads"][:2])
    assert receipt["downloads"][2]["http_status"] == 500
    assert "500 Server Error" in receipt["downloads"][2]["error_text"]

    summary = receipt["summary"]
    assert summary == {
        "max_passed_upload_mb": 2,
        "first_failed_upload_mb": 3,
        "upload_stopped_at_first_failure": True,
        "max_passed_download_mb": 4,
        "first_failed_download_mb": 6,
        "download_stopped_at_first_failure": True,
    }

    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok"
    assert win["card"] == "CPU-high-mem"
    _assert_no_tokens(out_dir)


def test_in_process_remote_download_prep_salvage_and_single_download_sha_guards(tmp_path: Path) -> None:
    # 1. Direct in-process coverage of `remote_runner.prepare_content_downloads` & `run_remote_script`
    assert rr.prepare_content_downloads(tmp_path / "missing_dir", 1024) == []
    content_rr = tmp_path / "rr_content"
    content_rr.mkdir()
    assert rr.prepare_content_downloads(content_rr, 0) == []

    small_bytes = b"small-bundle-payload"
    big_bytes = os.urandom(70_000)
    (content_rr / "a_small.tar.gz").write_bytes(small_bytes)
    (content_rr / "b_big.tar.gz").write_bytes(big_bytes)
    (content_rr / ".sdlab_dl_b_big.tar.gz.part.0099").write_bytes(b"stale")
    (content_rr / "notes.txt").write_text("ignored", encoding="utf-8")

    recs = rr.prepare_content_downloads(content_rr, 32_768)
    assert [r["rel"] for r in recs] == ["a_small.tar.gz", "b_big.tar.gz"]
    assert recs[0]["split"] is False and recs[0]["whole_sha256"] == hashlib.sha256(small_bytes).hexdigest()
    assert recs[1]["split"] is True and recs[1]["part_count"] == 3
    assert recs[1]["whole_sha256"] == hashlib.sha256(big_bytes).hexdigest()
    assert not (content_rr / ".sdlab_dl_b_big.tar.gz.part.0099").exists()
    man_rr = json.loads((content_rr / ".sdlab_dl_b_big.tar.gz.manifest.json").read_text(encoding="utf-8"))
    assert man_rr["part_count"] == 3 and man_rr["whole_bytes"] == 70_000

    echo_sh = tmp_path / "rr_ok.sh"
    echo_sh.write_text("#!/usr/bin/env bash\necho RR_OK\n", encoding="utf-8", newline="\n")
    rc_rr = rr.run_remote_script(
        _p(echo_sh),
        env={**os.environ, "SDLAB_CONTENT": str(content_rr), "SDLAB_DL_CHUNK_BYTES": "32768"},
    )
    assert rc_rr == 0

    # 2. Direct in-process coverage of `lane3_bundle_now.bundle_now` (missing env, unsplit, and split)
    assert lbn.bundle_now({}) == 2
    lbn._prepare_salvage_downloads(str(tmp_path / "no_dir"), 1024)

    content_bn = tmp_path / "bn_content"
    (content_bn / "lane3_out").mkdir(parents=True)
    (content_bn / "lane3_train").mkdir(parents=True)
    (content_bn / "lane3_train" / "step_1.txt").write_text("saved", encoding="utf-8")
    shutil.copyfile(COLAB_DIR / "lane3_rung.py", content_bn / "lane3_rung.py")
    shutil.copyfile(COLAB_DIR / "launch_guards.py", content_bn / "launch_guards.py")

    assert lbn.bundle_now({
        **os.environ,
        "SDLAB_CONTENT": str(content_bn),
        "SDLAB_BUNDLE_RC": "91",
        "SDLAB_DL_CHUNK_BYTES": "1048576",
    }) == 0
    assert (content_bn / "lane3_stub_bundle.tar.gz").is_file()

    # Now enlarge `lane3_train` and re-run `bundle_now` with small chunk size so `_prepare_salvage_downloads` splits it.
    (content_bn / "lane3_stub_bundle.tar.gz").unlink()
    (content_bn / ".sdlab_dl_lane3_stub_bundle.tar.gz.part.0099").write_bytes(b"stale")
    (content_bn / "lane3_train" / "blob.bin").write_bytes(os.urandom(90_000))
    assert lbn.bundle_now({
        **os.environ,
        "SDLAB_CONTENT": str(content_bn),
        "SDLAB_BUNDLE_RC": "91",
        "SDLAB_DL_CHUNK_BYTES": "32768",
    }) == 0
    assert not (content_bn / ".sdlab_dl_lane3_stub_bundle.tar.gz.part.0099").exists()
    man_bn = json.loads(
        (content_bn / ".sdlab_dl_lane3_stub_bundle.tar.gz.manifest.json").read_text(encoding="utf-8")
    )
    assert man_bn["part_count"] >= 3

    # 3. Single-file download corruption -> DOWNLOAD_SHA_MISMATCH, and chunked manifest 1x HTTP 500 retry -> ok.
    _, state_s, env_s = fc.make_fake_colab_env(tmp_path / "single_corrupt")
    env_s["COLAB_DOWNLOAD_CHUNK_BYTES"] = "262144"
    env_s["FAKE_COLAB_CORRUPT_DOWNLOAD_FOR"] = "small_b.tar.gz"
    (state_s / "content" / "small_b.tar.gz").write_bytes(b"unsplit-bundle-data")
    out_s = tmp_path / "single_corrupt" / "out"
    out_s.mkdir()
    res_s = _window_fn(
        env_s,
        f'colab_download_checked s1 /content/small_b.tar.gz "{_p(out_s / "small_b.tar.gz")}" "{_p(out_s)}"',
    )
    assert res_s.returncode != 0 and "REFUSED: DOWNLOAD_SHA_MISMATCH:" in res_s.stderr
    assert not (out_s / "small_b.tar.gz").exists()

    _, state_m, env_m = fc.make_fake_colab_env(tmp_path / "man_retry")
    env_m["COLAB_DOWNLOAD_CHUNK_BYTES"] = "32768"
    env_m["FAKE_COLAB_DOWNLOAD_HTTP_500_ONCE_FOR"] = ".manifest.json"
    m_payload = os.urandom(80_000)
    (state_m / "content" / "m_bundle.tar.gz").write_bytes(m_payload)
    out_m = tmp_path / "man_retry" / "out"
    out_m.mkdir()
    res_m = _window_fn(
        env_m,
        f'colab_download_checked s1 /content/m_bundle.tar.gz "{_p(out_m / "m_bundle.tar.gz")}" "{_p(out_m)}"',
    )
    assert res_m.returncode == 0, res_m.stderr
    assert hashlib.sha256((out_m / "m_bundle.tar.gz").read_bytes()).hexdigest() == hashlib.sha256(m_payload).hexdigest()
    bd_m = json.loads((out_m / "bundle_download.json").read_text(encoding="utf-8"))
    assert bd_m["retries"] == 1 and bd_m["verified"] is True


def test_n4_big_archive_upload_reassembly_scales_with_size_and_rate_where_old_bound_times_out(
    tmp_path: Path,
) -> None:
    """N4 bullet 1: VM reassembly exec scales by file size and rate (or explicit setting) instead of
    the per-part `upload_timeout` (120 s at df9a1b3b `colab_window.sh:938` / `:1014`).
    """
    payload = os.urandom(600_000)
    src_archive = tmp_path / "big_dataset.tar"
    src_archive.write_bytes(payload)

    # 1. Invalid reassembly flags refuse UPLOAD_TIMEOUT_INVALID before any colab call.
    _, state_bad, env_bad = fc.make_fake_colab_env(tmp_path / "bad_reass")
    res_bad_t = _run(
        [_bash(), _p(LANE1_SH), "--upload-reassemble-timeout-s", "0", "--out-dir", _p(tmp_path / "bad_t")],
        env_bad,
    )
    assert res_bad_t.returncode == 2 and "REFUSED: UPLOAD_TIMEOUT_INVALID:" in res_bad_t.stderr
    res_bad_r = _run(
        [_bash(), _p(LANE1_SH), "--upload-reassemble-mb-s", "0", "--out-dir", _p(tmp_path / "bad_r")],
        env_bad,
    )
    assert res_bad_r.returncode == 2 and "REFUSED: UPLOAD_TIMEOUT_INVALID:" in res_bad_r.stderr
    assert not (state_bad / "calls.log").exists()

    # 2. Per-part upload timeout is 2 s, while VM reassembly takes 3.2 s (`FAKE_VM_UPLOAD_REASSEMBLE_SLEEP_S=3.2`).
    # At 0.1 MB/s (`COLAB_UPLOAD_REASSEMBLE_MB_S=0.1`), 600,000 B budgets `ceil(600000 / 100000) + 30 = 36 s`
    # (whereas at df9a1b3b `colab_window.sh:1014` bounded reassembly by `upload_timeout = 2 s` and timed out).
    _, state_ok, env_ok = fc.make_fake_colab_env(tmp_path / "reass_ok")
    env_ok.update({
        "COLAB_UPLOAD_CHUNK_BYTES": "200000",
        "COLAB_UPLOAD_TIMEOUT_S": "2",
        "COLAB_UPLOAD_REASSEMBLE_MB_S": "0.1",
        "COLAB_KILL_GRACE_S": "1",
        "FAKE_VM_UPLOAD_REASSEMBLE_SLEEP_S": "3.2",
    })
    out_ok = tmp_path / "reass_ok" / "out"
    out_ok.mkdir()
    res_ok = _window_fn(
        env_ok,
        f'export COLAB_KILL_GRACE_S=1 && '
        f'colab_configure_upload_timeout "" && '
        f'colab_configure_upload_reassemble_timeout "" "0.1" && '
        f'colab_upload_checked s1 "{_p(src_archive)}" /content/big_dataset.tar "{_p(out_ok)}"',
    )
    assert res_ok.returncode == 0, res_ok.stdout + res_ok.stderr
    assert hashlib.sha256((state_ok / "content" / "big_dataset.tar").read_bytes()).hexdigest() == hashlib.sha256(
        payload
    ).hexdigest()
    up_rec = json.loads((out_ok / "upload_receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert up_rec["ok"] is True
    assert up_rec["part_count"] == 3
    assert up_rec["reassemble_timeout_s"] == 36
    assert up_rec["reassemble_timeout_source"] == "size_and_rate"
    assert up_rec["reassemble_mb_s"] == 0.1

    # 3. Forcing an explicit reassemble bound of 1 s (`--upload-reassemble-timeout-s 1`) proves timeout is named.
    _, _, env_to = fc.make_fake_colab_env(tmp_path / "reass_to")
    env_to.update({
        "COLAB_UPLOAD_CHUNK_BYTES": "200000",
        "COLAB_UPLOAD_TIMEOUT_S": "2",
        "COLAB_KILL_GRACE_S": "1",
        "FAKE_VM_UPLOAD_REASSEMBLE_SLEEP_S": "3.0",
    })
    out_to = tmp_path / "reass_to" / "out"
    out_to.mkdir()
    res_to = _window_fn(
        env_to,
        f'export COLAB_KILL_GRACE_S=1 && '
        f'colab_configure_upload_timeout "" && '
        f'colab_configure_upload_reassemble_timeout "1" "" && '
        f'colab_upload_checked s1 "{_p(src_archive)}" /content/big_dataset.tar "{_p(out_to)}"',
    )
    assert res_to.returncode != 0
    assert "REFUSED: UPLOAD_PART_FAILED:" in res_to.stderr
    assert "UPLOAD_TIMEOUT" in (out_to / "guards.log").read_text(encoding="utf-8")
    assert "step=reassemble timeout_s=1" in (out_to / "guards.log").read_text(encoding="utf-8")


def test_n4_download_split_out_of_disk_refuses_named_code_without_single_get_fallthrough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N4 bullet 2: running out of disk during VM download split refuses `DOWNLOAD_SPLIT_DISK_LOW`
    cleanly without crashing into a single `colab download` GET (which happened at df9a1b3b
    `colab_window.sh:1399-1400`).
    """
    big_blob = os.urandom(90_000)

    # Case A: Pre-split free-disk check (`FAKE_VM_DL_SPLIT_FREE_BYTES=40000 < 90000 + 16 MiB`) via
    # standalone `prepare_download.py` exec (`colab_download_checked` with no prior `vitals.log`).
    _, state_a, env_a = fc.make_fake_colab_env(tmp_path / "split_pre_low")
    env_a["COLAB_DOWNLOAD_CHUNK_BYTES"] = "32768"
    env_a["FAKE_VM_DL_SPLIT_FREE_BYTES"] = "40000"
    (state_a / "content" / "huge_bundle.tar.gz").write_bytes(big_blob)
    out_a = tmp_path / "split_pre_low" / "out"
    out_a.mkdir()
    res_a = _window_fn(
        env_a,
        f'colab_download_checked s1 /content/huge_bundle.tar.gz "{_p(out_a / "huge_bundle.tar.gz")}" "{_p(out_a)}"',
    )
    assert res_a.returncode != 0
    assert "REFUSED: DOWNLOAD_SPLIT_DISK_LOW:" in res_a.stderr
    assert not (out_a / "huge_bundle.tar.gz").exists()
    calls_a = (state_a / "calls.log").read_text(encoding="utf-8")
    assert "CALL download " not in calls_a, f"must never fall through to single GET: {calls_a}"
    bd_a = json.loads((out_a / "bundle_download.json").read_text(encoding="utf-8"))
    assert bd_a["status"] == "split_disk_low" and bd_a["error_code"] == "DOWNLOAD_SPLIT_DISK_LOW"

    # Case B: Mid-split `OSError(errno.ENOSPC)` on part 1 (`FAKE_VM_DL_SPLIT_ENOSPC_ON_PART=1`) during
    # `remote_runner.py` pre-split (`vitals.log` carries `SDLAB_DOWNLOAD_PREPARE_JSON`), verifying
    # partial `.sdlab_dl_*` files are unlinked and `colab_download_checked` refuses `DOWNLOAD_SPLIT_DISK_LOW`
    # with zero `colab download` calls.
    _, state_b, env_b = fc.make_fake_colab_env(tmp_path / "split_mid_enospc")
    env_b["COLAB_DOWNLOAD_CHUNK_BYTES"] = "32768"
    env_b["FAKE_VM_DL_SPLIT_ENOSPC_ON_PART"] = "1"
    content_b = state_b / "content"
    (content_b / "lane3_stub_bundle.tar.gz").write_bytes(big_blob)
    out_b = tmp_path / "split_mid_enospc" / "out"
    out_b.mkdir()
    monkeypatch.setenv("FAKE_VM_SITE", "1")
    monkeypatch.setenv("FAKE_VM_DL_SPLIT_ENOSPC_ON_PART", "1")
    recs_b = rr.prepare_content_downloads(content_b, 32_768)
    monkeypatch.delenv("FAKE_VM_DL_SPLIT_ENOSPC_ON_PART", raising=False)
    monkeypatch.delenv("FAKE_VM_SITE", raising=False)
    assert len(recs_b) == 1 and recs_b[0]["split_failed"] is True
    assert recs_b[0]["error_code"] == "DOWNLOAD_SPLIT_DISK_LOW"
    assert [p.name for p in content_b.iterdir() if p.name.startswith(".sdlab_dl_")] == []
    (out_b / "vitals.log").write_text(
        "SDLAB_DOWNLOAD_PREPARE_JSON " + json.dumps(recs_b[0]) + "\nSDLAB_DOWNLOAD_PREPARE_DONE chunk_bytes=32768\n",
        encoding="utf-8",
        newline="\n",
    )
    res_b = _window_fn(
        env_b,
        f'colab_download_checked s1 /content/lane3_stub_bundle.tar.gz "{_p(out_b / "lane3_stub_bundle.tar.gz")}" "{_p(out_b)}"',
    )
    assert res_b.returncode != 0
    assert "REFUSED: DOWNLOAD_SPLIT_DISK_LOW:" in res_b.stderr
    assert not (state_b / "calls.log").exists()


def test_n5_download_prep_has_single_source_in_launch_guards_without_copy_drift(tmp_path: Path) -> None:
    """N5: download-prep logic lives in one source (`launch_guards.py` `# >>> sdlab-download-prep`),
    with `remote_runner.py`, `lane3_bundle_now.py`, and `colab_window.sh` delegating to it instead of
    duplicating split implementations (which existed at df9a1b3b `remote_runner.py:29-121`,
    `lane3_bundle_now.py:27-119`, and `colab_window.sh:1087-1196`).
    """
    import launch_guards as lg

    guards_src = (COLAB_DIR / "launch_guards.py").read_text(encoding="utf-8")
    rr_src = (COLAB_DIR / "remote_runner.py").read_text(encoding="utf-8")
    bn_src = (COLAB_DIR / "lane3_bundle_now.py").read_text(encoding="utf-8")
    win_src = (COLAB_DIR / "colab_window.sh").read_text(encoding="utf-8")

    assert "# >>> sdlab-download-prep" in guards_src and "# <<< sdlab-download-prep" in guards_src
    # Neither `remote_runner.py` nor `lane3_bundle_now.py` carries its own `.part.%04d` writer or manifest writer,
    # and `colab_window.sh` carries zero `.sdlab_dl_` download-split or `SDLAB_DOWNLOAD_PREPARE_JSON` emitter code
    # (its single `.part.{idx:04d}` occurrence is rig-side upload splitting `.sdlab_up_`).
    for other_name, other_src in (
        ("remote_runner.py", rr_src),
        ("lane3_bundle_now.py", bn_src),
    ):
        assert ".part.{idx:04d}" not in other_src, f"{other_name} still duplicates download split code"
        assert "manifest_payload = {" not in other_src, f"{other_name} still duplicates manifest writer"
    assert 'f".sdlab_dl_{' not in win_src, "colab_window.sh still duplicates download split prefix writer"
    assert 'print("SDLAB_DOWNLOAD_PREPARE_JSON "' not in win_src, "colab_window.sh still duplicates download prep emitter"
    assert win_src.count(".part.{idx:04d}") == 1, "colab_window.sh must only have rig-side upload part writer"

    # Verify `_colab_write_download_prepare_py` emits the exact `launch_guards.py` block and runs without `__file__`.
    _, _, env = fc.make_fake_colab_env(tmp_path / "prep_emit")
    emitted_py = tmp_path / "emitted_prepare.py"
    res = _window_fn(env, f'_colab_write_download_prepare_py "{_p(emitted_py)}"')
    assert res.returncode == 0, res.stderr
    emitted_text = emitted_py.read_text(encoding="utf-8")
    start_m = "# >>> sdlab-download-prep"
    end_m = "# <<< sdlab-download-prep"
    expected_block = guards_src[guards_src.index(start_m) : guards_src.index(end_m) + len(end_m)]
    assert emitted_text.startswith(expected_block)
    assert "__file__" not in emitted_text
    assert lg.prepare_content_downloads is not None


def test_failed_salvage_part_keeps_every_arrived_part_with_a_receipt_and_deletes_nothing_verified(
    tmp_path: Path,
) -> None:
    # fix3 Part 2: part 2 of a 3-part salvage fails (HTTP 500 on every attempt). Parts 0 and 1 had arrived and
    # verified, so they are moved into <out_dir>/salvage_partial/ with the arrived-parts receipt and the VM's
    # split manifest, never deleted. At 310232f4 the failure path ran `rm -rf "${tmp_dl_dir}"`
    # (colab_window.sh:1703) and the verified bytes were gone.
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["COLAB_DOWNLOAD_CHUNK_BYTES"] = "65536"
    env["FAKE_COLAB_DOWNLOAD_HTTP_500_FOR"] = ".part.0002"
    lane3_out = state / "content" / "lane3_out"
    (lane3_out / "rung_outputs").mkdir(parents=True)
    (lane3_out / "rung_outputs" / "ckpt_blob.bin").write_bytes(os.urandom(160_000))
    shutil.copyfile(COLAB_DIR / "launch_guards.py", state / "content" / "launch_guards.py")
    shutil.copyfile(COLAB_DIR / "lane3_rung.py", state / "content" / "lane3_rung.py")

    out_dir = tmp_path / "out_salvage_partial"
    out_dir.mkdir()
    dst = out_dir / "lane3_stub_bundle.tar.gz"
    res = _window_fn(
        env,
        f'colab_salvage_bundle_after_failure s1 "{_p(COLAB_DIR / "lane3_bundle_now.py")}" '
        f'/content/lane3_stub_bundle.tar.gz "{_p(dst)}" "{_p(out_dir)}" 143',
    )
    assert res.returncode == 0, res.stderr
    assert not dst.exists()
    assert "BUNDLE_AFTER_FAILURE: none on the VM" in (out_dir / "guards.log").read_text(encoding="utf-8")

    kept_dirs = sorted((out_dir / "salvage_partial").iterdir())
    assert [d.name for d in kept_dirs] == ["salvage_lane3_stub_bundle.tar.gz"]
    kept = kept_dirs[0]
    receipt = json.loads((kept / "arrived_parts_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "part_failed" and receipt["failed_part"] == 2
    assert receipt["arrived_parts"] == [0, 1]
    assert sorted(receipt["kept_files"]) == ["part.0000", "part.0001", "vm_split_manifest.json"]
    vm_manifest = json.loads((kept / "vm_split_manifest.json").read_text(encoding="utf-8"))
    assert vm_manifest["whole_sha256"] == receipt["whole_sha256_expected"]
    for detail in receipt["arrived_part_details"]:
        blob = (kept / f"part.{detail['index']:04d}").read_bytes()
        assert len(blob) == detail["bytes"] == 65536
        assert hashlib.sha256(blob).hexdigest() == detail["sha256"] == vm_manifest["parts"][detail["index"]]["sha256"]
    assert not (kept / "part.0002").exists()
    assert not [d for d in out_dir.iterdir() if d.name.startswith(".sdlab_dl_tmp_")], "no temp directory left behind"
    sbd = json.loads((out_dir / "salvage_bundle_download.json").read_text(encoding="utf-8"))
    assert sbd["arrived_parts"] == [0, 1] and sbd["status"] == "part_failed"

    # A second failed salvage into the same out dir keeps its parts in a new directory (nothing is overwritten).
    res2 = _window_fn(
        env,
        f'colab_salvage_bundle_after_failure s1 "{_p(COLAB_DIR / "lane3_bundle_now.py")}" '
        f'/content/lane3_stub_bundle.tar.gz "{_p(dst)}" "{_p(out_dir)}" 143',
    )
    assert res2.returncode == 0, res2.stderr
    assert sorted(d.name for d in (out_dir / "salvage_partial").iterdir()) == [
        "salvage_lane3_stub_bundle.tar.gz",
        "salvage_lane3_stub_bundle.tar.gz_2",
    ]


def test_part_failing_its_own_check_is_not_kept_but_the_verified_parts_before_it_are(tmp_path: Path) -> None:
    # fix3 Part 2: a corrupted part 1 (sha mismatch) is not verified bytes and is dropped; verified part 0 stays.
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["COLAB_DOWNLOAD_CHUNK_BYTES"] = "65536"
    env["FAKE_COLAB_CORRUPT_DOWNLOAD_FOR"] = ".part.0001"
    (state / "content" / "b.tar.gz").write_bytes(os.urandom(65536 * 2 + 5000))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = _window_fn(env, f'colab_download_checked s1 /content/b.tar.gz "{_p(out_dir / "b.tar.gz")}" "{_p(out_dir)}"')
    assert res.returncode != 0 and "REFUSED: DOWNLOAD_SHA_MISMATCH:" in res.stderr
    kept = out_dir / "salvage_partial" / "normal_b.tar.gz"
    assert sorted(p.name for p in kept.iterdir()) == ["arrived_parts_receipt.json", "part.0000", "vm_split_manifest.json"]
    assert json.loads((kept / "arrived_parts_receipt.json").read_text(encoding="utf-8"))["arrived_parts"] == [0]
    assert not (out_dir / "b.tar.gz").exists()


def _bounds(env: dict[str, str], setup: str) -> dict[str, int]:
    res = _window_fn(
        env,
        setup + '\ncolab_compute_cleanup_bounds train\n'
        'echo "salvage_deadline=${SALVAGE_DEADLINE_S} in_flight=${COLAB_IN_FLIGHT_BOUND_S} '
        'reassemble=${COLAB_REASSEMBLE_BOUND_S} prep=${COLAB_PREP_EXEC_BOUND_S} '
        'stop_by=${COLAB_CLEANUP_STOP_ATTEMPTED_BY_S} cleanup=${COLAB_CLEANUP_BOUND_S}"',
    )
    assert res.returncode == 0, res.stderr
    line = res.stdout.strip().splitlines()[-1]
    return {k: int(v) for k, v in (kv.split("=") for kv in line.split())}


def test_salvage_deadline_counts_the_split_manifest_fetch_and_every_5xx_retry(tmp_path: Path) -> None:
    # fix3 Part 4. A one-part bundle is one GET. A multi-part salvage also fetches the VM's split manifest and each
    # part, and every one of those steps may be retried once on HTTP 5xx: 2 + 2 * parts download steps. At
    # 310232f4 (colab_window.sh:155-157) the deadline counted only `parts` steps.
    _, _, env = fc.make_fake_colab_env(tmp_path)
    env.pop("COLAB_UPLOAD_MAX_BYTES", None)
    step = 300 + 10  # download timeout + kill grace
    one = _bounds(env, 'colab_configure_download_timeout "" "" 1')
    assert one["salvage_deadline"] == (180 + 10) + (330 + 10) + 1 * step == 840
    assert one["cleanup"] == one["in_flight"] + 840 + 2 * (60 + 10) == 1290
    four = _bounds(env, 'colab_configure_download_timeout "" "" 4')
    assert four["salvage_deadline"] == (180 + 10) + (330 + 10) + (2 + 2 * 4) * step == 3630
    assert four["cleanup"] == four["in_flight"] + 3630 + 2 * (60 + 10) == 4080
    two = _bounds(env, 'colab_configure_download_timeout "" "" 2')
    assert two["salvage_deadline"] == (180 + 10) + (330 + 10) + 6 * step == 2390
    # The window.json figures come from the same formula.
    res = _window_fn(
        env,
        'colab_configure_download_timeout "" "" 4; colab_compute_cleanup_bounds train; '
        'echo "${COLAB_SALVAGE_DOWNLOAD_PARTS} ${SALVAGE_DEADLINE_S}"',
    )
    assert res.stdout.split() == ["4", "3630"]


def test_in_flight_bound_counts_the_reassembly_exec_and_the_prep_exec(tmp_path: Path) -> None:
    # fix3 Part 4. The cap gate's in-flight step is the longest single bounded step a guard trip can interrupt. It now
    # includes the VM download-prepare exec (min(download timeout, 180 s)) and the VM upload-reassembly exec (an
    # explicit timeout, or max(upload timeout, ceil(max bytes / (MB/s * 1e6)) + 30)). At 310232f4
    # (colab_window.sh:360-367) neither was counted.
    _, _, env = fc.make_fake_colab_env(tmp_path)
    for k in ("COLAB_UPLOAD_MAX_BYTES", "COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S", "COLAB_UPLOAD_REASSEMBLE_MB_S"):
        env.pop(k, None)
    plain = _bounds(env, "")
    assert plain["reassemble"] == 0 and plain["prep"] == 180 and plain["in_flight"] == 300 + 10
    # An explicit reassembly timeout counts when an upload can chunk (largest upload unknown, or above the chunk size).
    explicit = _bounds(env, "export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S=900")
    assert explicit["reassemble"] == 900 and explicit["in_flight"] == 900 + 10
    assert explicit["stop_by"] == explicit["in_flight"] + (180 + 10) + (330 + 10) + (300 + 10)
    big = _bounds(env, "export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S=900 COLAB_UPLOAD_MAX_BYTES=100000000")
    assert big["reassemble"] == 900
    # ...and not when the largest upload fits one request.
    small = _bounds(env, "export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S=900 COLAB_UPLOAD_MAX_BYTES=1000")
    assert small["reassemble"] == 0 and small["in_flight"] == 300 + 10
    # Size and rate: 40 GB at 25 MB/s is 1600 s, plus 30 s; never below the upload timeout.
    sized = _bounds(env, "export COLAB_UPLOAD_MAX_BYTES=40000000000")
    assert sized["reassemble"] == 1630 and sized["in_flight"] == 1640
    rated = _bounds(env, "export COLAB_UPLOAD_MAX_BYTES=40000000000 COLAB_UPLOAD_REASSEMBLE_MB_S=100")
    assert rated["reassemble"] == 430
    floor = _bounds(env, "export COLAB_UPLOAD_MAX_BYTES=100000000")
    assert floor["reassemble"] == 120, "100 MB at 25 MB/s is 34 s: floored at the 120 s upload timeout"
    # The prep exec is min(download timeout, 180): a short download timeout shortens it too.
    short = _bounds(env, 'export COLAB_DOWNLOAD_TIMEOUT_S=100 COLAB_UPLOAD_TIMEOUT_S=50 COLAB_SESSIONS_TIMEOUT_S=20')
    assert short["prep"] == 100 and short["in_flight"] == 100 + 10
    # window.json uses the exported figure, so the dry record, the gate and window.json agree.
    res = _window_fn(
        env,
        "export COLAB_UPLOAD_REASSEMBLE_TIMEOUT_S=900; colab_compute_cleanup_bounds train; "
        'echo "${COLAB_REASSEMBLE_BOUND_S} ${COLAB_IN_FLIGHT_BOUND_S}"',
    )
    assert res.stdout.split() == ["900", "910"]
