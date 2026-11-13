"""Addendum 3 for lane 1 `--render`: per-job timeouts and failed rows (N2), consecutive-failure stop, the weights disk
projection (N3), the VRAM peak (N5), the licence alias check (N4) and the BiRefNet refusal."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "colab"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab"))

import lane1_render as l1  # noqa: E402
from test_lane1_render import FakeComfyClient  # noqa: E402

SYS_STATS = lambda _url: {"system": {"os": "posix"}, "devices": [{"type": "cpu"}]}  # noqa: E731


def _jobs(path: Path, specs: list[dict[str, Any]]) -> Path:
    rows = []
    for i, extra in enumerate(specs, start=1):
        rows.append(
            {
                "job_id": f"job_{i:02d}",
                "run_id": "run_a3",
                "template_id": "stub_fixture_64",
                "seed": 100 + i,
                "width": 64,
                "height": 64,
                "steps": 20,
                "canon_sha": "a881cb5ba656e0618080d2269498fda7f36ac93a",
                "entry_id": "ships/brig",
                "entry_sha256": "sha256:" + f"{i:02x}" * 32,
                "workflow_sha": "sha256:" + "ab" * 32,
                **extra,
            }
        )
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _run(tmp_path: Path, client: Any, jobs_path: Path, **kw: Any) -> dict[str, Any]:
    return l1.run_queue(
        jobs_path=jobs_path,
        renders_path=tmp_path / "renders.jsonl",
        out_dir=tmp_path / "pngs",
        comfy_url="http://127.0.0.1:8188",
        window_id="win_a3",
        client=client,
        image_downloader=client.download_image,
        system_stats_fetcher=SYS_STATS,
        **kw,
    )


class TimeoutRecordingClient(FakeComfyClient):
    """Records the timeout each wait gets. `raise_on_queue` and `timeout_on_wait` are 1-based call numbers: a queue call
    that raises, and a wait that returns nothing (a job that never finished)."""

    def __init__(self, raise_on_queue: set[int] | None = None, timeout_on_wait: set[int] | None = None) -> None:
        super().__init__()
        self.timeouts: list[float] = []
        self.queue_calls = 0
        self.raise_on_queue = raise_on_queue or set()
        self.timeout_on_wait = timeout_on_wait or set()

    def queue_prompt(self, workflow: dict[str, Any], extra_pnginfo: dict[str, str] | None = None) -> str:
        self.queue_calls += 1
        if self.queue_calls in self.raise_on_queue:
            raise ConnectionError("ComfyUI went away")
        return super().queue_prompt(workflow, extra_pnginfo)

    def wait_for_completion(self, prompt_id: str, timeout: float = 120.0, poll_interval: float = 0.2) -> Any:
        self.timeouts.append(timeout)
        if len(self.timeouts) in self.timeout_on_wait:
            return None
        return super().wait_for_completion(prompt_id, timeout, poll_interval)


def test_wait_timeout_comes_from_steps_resolution_and_first_job_allowance_and_is_recorded(tmp_path: Path) -> None:
    jobs = _jobs(
        tmp_path / "jobs.jsonl",
        [
            {"steps": 22, "width": 1024, "height": 1024},
            {"steps": 40, "width": 2048, "height": 1024},
            {"steps": 4, "width": 64, "height": 64},
        ],
    )
    client = TimeoutRecordingClient()
    _run(tmp_path, client, jobs)
    first = l1.derive_job_timeout_s({"steps": 22, "width": 1024, "height": 1024}, first_job=True)
    second = l1.derive_job_timeout_s({"steps": 40, "width": 2048, "height": 1024})
    assert first == 60.0 + 22 * 3.0 + l1.FIRST_JOB_ALLOWANCE_S == client.timeouts[0]
    assert second == 60.0 + 40 * 3.0 * 2 == client.timeouts[1]
    assert client.timeouts[2] == l1.JOB_TIMEOUT_MIN_S  # a tiny job never gets under the floor
    assert client.timeouts[1] > 120.0, "the old hard-coded 120 s would have killed this job"
    assert [r["timeout_s"] for r in _rows(tmp_path / "renders.jsonl")] == client.timeouts


def test_explicit_job_timeout_option_wins_over_the_derived_one(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path / "jobs.jsonl", [{}, {}])
    client = TimeoutRecordingClient()
    _run(tmp_path, client, jobs, job_timeout_s=777.0)
    assert client.timeouts == [777.0, 777.0]
    assert {r["timeout_s"] for r in _rows(tmp_path / "renders.jsonl")} == {777.0}


def test_a_raising_job_and_a_timed_out_job_get_failed_rows_and_the_queue_goes_on(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path / "jobs.jsonl", [{}, {}, {}, {}])
    interrupted: list[str] = []
    # job 2 raises when queued; job 3 (the 2nd wait, since job 2 never reached one) never finishes; jobs 1 and 4 render.
    client = TimeoutRecordingClient(raise_on_queue={2}, timeout_on_wait={2})
    summary = _run(tmp_path, client, jobs, max_consecutive_failures=3, interrupter=interrupted.append)
    rows = _rows(tmp_path / "renders.jsonl")
    assert [(r["job_id"], r["status"]) for r in rows] == [
        ("job_01", "ok"),
        ("job_02", "failed"),
        ("job_03", "failed"),
        ("job_04", "ok"),
    ]
    raised, timed_out = rows[1], rows[2]
    assert raised["code"] == "RENDER_JOB_FAILED" and "ConnectionError" in raised["why"]
    assert timed_out["code"] == "RENDER_JOB_TIMEOUT"
    for failed in (raised, timed_out):
        assert isinstance(failed["wall_s"], float) and failed["wall_s"] >= 0.0
        assert failed["timeout_s"] > 0
    assert interrupted == ["http://127.0.0.1:8188"], "only the timed-out job is interrupted on the server"
    assert summary["rendered"] == 2 and summary["failed"] == 2
    assert summary["stopped_consecutive_failures"] is False
    # Only the two good PNGs exist, and a resume retries the failed jobs (a failed row is never "done").
    assert sorted(p.name for p in (tmp_path / "pngs").glob("*.png")) == ["job_01.png", "job_04.png"]
    assert set(l1.load_completed(tmp_path / "renders.jsonl", tmp_path / "pngs")) == {"job_01", "job_04"}


def test_consecutive_failures_stop_the_queue_with_a_named_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    jobs = _jobs(tmp_path / "jobs.jsonl", [{}, {}, {}, {}, {}])

    class FailingAfterFirst(FakeComfyClient):
        def queue_prompt(self, workflow: dict[str, Any], extra_pnginfo: dict[str, str] | None = None) -> str:
            if self.queued:
                self.queued.append(("x", workflow, {}))
                raise RuntimeError("boom")
            return super().queue_prompt(workflow, extra_pnginfo)

    client = FailingAfterFirst()
    summary = _run(tmp_path, client, jobs)  # default: stop after 2 in a row
    rows = _rows(tmp_path / "renders.jsonl")
    assert [(r["job_id"], r["status"]) for r in rows] == [("job_01", "ok"), ("job_02", "failed"), ("job_03", "failed")]
    assert summary["stopped_consecutive_failures"] is True and summary["failed"] == 2 and summary["rendered"] == 1
    assert len(client.queued) == 3, "jobs 4 and 5 were never tried"
    assert (tmp_path / "pngs" / "job_01.png").is_file(), "what rendered before the run of failures is kept"
    hb = json.loads((tmp_path / "render_heartbeat.json").read_text(encoding="utf-8"))
    assert hb["state"] == "failed_consecutive"

    # The CLI turns that into exit 76 and a REFUSED line the kit recognises.
    capsys.readouterr()
    jobs_cli = _jobs(tmp_path / "cli_jobs.jsonl", [{}, {}])
    monkey_client = FailingAfterFirst()
    monkey_client.queued.append(("seed", {}, {}))  # every queue call raises
    orig = l1.run_queue

    def fake_run_queue(**kw: Any) -> dict[str, Any]:
        return orig(**{**kw, "client": monkey_client, "image_downloader": monkey_client.download_image, "system_stats_fetcher": SYS_STATS})

    l1.run_queue, saved = fake_run_queue, l1.run_queue  # type: ignore[assignment]
    try:
        rc = l1.main(
            [
                "--jobs", str(jobs_cli), "--renders", str(tmp_path / "cli_renders.jsonl"), "--out-dir", str(tmp_path / "cli_pngs"),
                "--max-consecutive-failures", "2",
            ]
        )
    finally:
        l1.run_queue = saved  # type: ignore[assignment]
    assert rc == l1.EXIT_RENDER_CONSECUTIVE_FAILURES == 76
    assert "REFUSED: RENDER_CONSECUTIVE_FAILURES:" in capsys.readouterr().err


def test_a_success_resets_the_failure_count(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path / "jobs.jsonl", [{}, {}, {}, {}, {}])
    client = TimeoutRecordingClient(timeout_on_wait={1, 3})  # fail, ok, fail, ok, ok: never two in a row
    summary = _run(tmp_path, client, jobs, interrupter=lambda _u: None)
    assert summary["failed"] == 2 and summary["rendered"] == 3 and summary["stopped_consecutive_failures"] is False
    with pytest.raises(ValueError):
        _run(tmp_path, TimeoutRecordingClient(), jobs, max_consecutive_failures=0)


def test_peak_vram_is_the_highest_reading_during_the_job_not_the_use_after_the_image(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path / "jobs.jsonl", [{}])
    readings = iter([2000.0, 9000.0, 21000.0, 5000.0])
    lock = threading.Lock()

    def smi(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        with lock:
            val = next(readings, 3000.0)
        return subprocess.CompletedProcess(["nvidia-smi"], 0, f"{val}\n", "")

    class SlowClient(FakeComfyClient):
        def wait_for_completion(self, prompt_id: str, timeout: float = 120.0, poll_interval: float = 0.2) -> Any:
            time.sleep(0.4)
            return super().wait_for_completion(prompt_id, timeout, poll_interval)

    client = SlowClient()
    _run(tmp_path, client, jobs, smi_runner=smi, vram_sample_interval_s=0.05)
    row = _rows(tmp_path / "renders.jsonl")[0]
    assert row["peak_vram_mib"] == 21000.0
    assert row["peak_vram_source"] == "sampled_during_job"
    assert row["vram_samples"] >= 3


def test_derive_render_wall_counts_every_job(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path / "jobs.jsonl", [{"steps": 22, "width": 1024, "height": 1024}] * 3)
    per = l1.derive_job_timeout_s({"steps": 22, "width": 1024, "height": 1024})
    got = l1.derive_render_wall_s(jobs, setup_s=1200)
    assert got == int(-(-((1200 + l1.FIRST_JOB_ALLOWANCE_S + 3 * per) * 1.1) // 1))
    assert got > 900, "a real queue is not held to the old 900 s default"
    five = _jobs(tmp_path / "five.jsonl", [{"steps": 22, "width": 1024, "height": 1024}] * 5)
    assert l1.derive_render_wall_s(five, setup_s=1200) > got
    assert l1.main(["--derive-wall-s", "--jobs", str(jobs), "--setup-s", "1200"]) == 0
    assert l1.main(["--derive-wall-s", "--jobs", str(tmp_path / "missing.jsonl")]) == 1


# ---- N3: the weights are linked out of the HF cache, not copied ------------------------------------------------------


def test_stage_weight_file_hardlinks_through_the_cache_symlink_and_projects_one_copy(tmp_path: Path) -> None:
    blob = tmp_path / "cache" / "blobs" / "abc"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"W" * 4096)
    snap = tmp_path / "cache" / "snapshots" / "rev" / "w.safetensors"
    snap.parent.mkdir(parents=True)
    snap.symlink_to(blob)
    target = tmp_path / "models" / "w.safetensors"
    target.parent.mkdir()
    assert l1.stage_weight_file(snap, target) == "hardlink"
    assert not target.is_symlink() and target.stat().st_ino == blob.stat().st_ino and blob.stat().st_nlink == 2
    assert target.read_bytes() == blob.read_bytes()
    assert l1.project_weights_disk_bytes(28 * l1.GIB, linked=True) == 28 * l1.GIB
    assert l1.project_weights_disk_bytes(28 * l1.GIB, linked=False) == 56 * l1.GIB


def test_stage_weight_file_falls_back_to_a_copy_only_when_the_disk_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * 2048)
    monkeypatch.setattr(os, "link", lambda *_a, **_k: (_ for _ in ()).throw(OSError(18, "Invalid cross-device link")))
    out = tmp_path / "out"
    out.mkdir()
    assert l1.stage_weight_file(src, out / "ok.bin") == "copy"
    assert (out / "ok.bin").stat().st_ino != src.stat().st_ino
    monkeypatch.setattr(l1.shutil, "disk_usage", lambda _p: type("U", (), {"free": 10})())
    with pytest.raises(OSError, match="a copy needs"):
        l1.stage_weight_file(src, out / "low.bin")
    assert not (out / "low.bin").exists()


def _safetensors(tag: bytes) -> bytes:
    payload = tag * 16
    hdr = json.dumps({"w": {"dtype": "U8", "shape": [len(payload)], "data_offsets": [0, len(payload)]}}, separators=(",", ":")).encode()
    return struct.pack("<Q", len(hdr)) + hdr + payload


def test_weights_download_links_models_to_the_cache_blob_and_records_the_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_site = REPO_ROOT / "tests" / "colab" / "fixtures" / "fake_vm_site"
    monkeypatch.syspath_prepend(str(fake_site))
    monkeypatch.setenv("PYTHONPATH", str(fake_site))
    for k in ("HF_HOME", "HF_TOKEN", "HF_TOKEN_GGUF_READ", "HUGGING_FACE_HUB_TOKEN", "HF_HUB_OFFLINE", "FAKE_HF_EXPECT_TOKEN"):
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k, raising=False)
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    data = _safetensors(b"LINKED_VAE")
    (blobs / "vae.safetensors").write_bytes(data)
    monkeypatch.setenv("FAKE_HF_BLOBS_DIR", str(blobs))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [{"repo": "madebyollin/taesd", "revision": "6" * 40, "file": "vae.safetensors", "dest": "vae",
              "sha256": hashlib.sha256(data).hexdigest(), "licence_id": "MIT"}]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "dl.json"
    try:
        rc = l1.run_weights_download(
            manifest_path=manifest, hf_home=tmp_path / "hf", models_dir=tmp_path / "models", max_seconds_raw="60",
            poll_s=0.02, log_path=tmp_path / "dl.log", out_path=out,
        )
    finally:
        os.environ.pop("HF_HUB_OFFLINE", None)
    assert rc == 0
    rec = json.loads(out.read_text(encoding="utf-8"))
    staged = tmp_path / "models" / "vae" / "vae.safetensors"
    assert rec["files"][0]["staged_how"] == "hardlink"
    assert rec["files"][0]["sha256"] == hashlib.sha256(data).hexdigest(), "the sha check still runs after the link"
    assert staged.stat().st_nlink >= 2, "the staged file is the cache's bytes, not a second copy"
    assert rec["disk_projection"] == {
        "weights_bytes": len(data), "linked": True, "projected_bytes": len(data),
    }


# ---- N4 and BiRefNet --------------------------------------------------------------------------------------------------


def _manifest(tmp_path: Path, repo: str, lic: str) -> Path:
    p = tmp_path / "m.json"
    p.write_text(
        json.dumps([{"repo": repo, "revision": "a" * 40, "file": "w.safetensors", "dest": "vae", "sha256": "1" * 64, "licence_id": lic}]),
        encoding="utf-8",
    )
    return p


def test_a_licence_alias_is_good_only_for_its_own_repo(tmp_path: Path) -> None:
    assert l1.validate_weights_manifest(_manifest(tmp_path, l1.PINNED_COMFY_REPACK_REPO, "comfy-org-qwen-image-repack"))
    with pytest.raises(Exception) as exc:
        l1.validate_weights_manifest(_manifest(tmp_path, "someone/else-model", "comfy-org-qwen-image-repack"))
    assert getattr(exc.value, "code", None) == "WEIGHTS_LICENCE_INVALID"
    assert "someone/else-model" in str(getattr(exc.value, "detail", ""))
    # A plain SPDX id names a licence, not a repo.
    assert l1.validate_weights_manifest(_manifest(tmp_path, "someone/else-model", "Apache-2.0"))


def test_birefnet_jobs_are_refused_at_validate_render_inputs_with_a_named_code(tmp_path: Path) -> None:
    base = {
        "job_id": "job_01", "run_id": "run_a3", "template_id": "qwen_txt2img_lora", "prompt": "a brig", "seed": 1,
        "width": 512, "height": 512, "steps": 20, "canon_sha": "a" * 40, "entry_id": "ships/brig",
        "entry_sha256": "sha256:" + "1" * 64, "licence": "CC-BY-4.0", "credit": "mcp-tool-shop",
    }
    for variant in (
        {"bg_removal": "BiRefNet"},
        {"background_removal": {"model": "BiRefNet", "licence_id": "MIT"}},
        {"workflow": {"1": {"class_type": "BiRefNet_Hugo", "inputs": {"image": ["2", 0]}}}},
    ):
        p = tmp_path / "jobs.jsonl"
        p.write_text(json.dumps({**base, **variant}) + "\n", encoding="utf-8")
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        with pytest.raises(Exception) as exc:
            l1.validate_render_jobs(p, sha)
        assert getattr(exc.value, "code", None) == "BIREFNET_NODE_NOT_INSTALLED"
    p_wf = tmp_path / "jobs_wf_plain.jsonl"
    p_wf.write_text(
        json.dumps({**base, "workflow": {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}}}}) + "\n",
        encoding="utf-8",
    )
    assert l1.validate_render_jobs(p_wf, hashlib.sha256(p_wf.read_bytes()).hexdigest())["job_count"] == 1
    p = tmp_path / "jobs_plain.jsonl"
    p.write_text(json.dumps(base) + "\n", encoding="utf-8")
    assert l1.validate_render_jobs(p, hashlib.sha256(p.read_bytes()).hexdigest())["job_count"] == 1


def test_weights_download_reports_weights_disk_low_and_sampler_ignores_smi_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_site = REPO_ROOT / "tests" / "colab" / "fixtures" / "fake_vm_site"
    monkeypatch.syspath_prepend(str(fake_site))
    monkeypatch.setenv("PYTHONPATH", str(fake_site))
    for k in ("HF_HOME", "HF_TOKEN", "HF_TOKEN_GGUF_READ", "HUGGING_FACE_HUB_TOKEN", "HF_HUB_OFFLINE", "FAKE_HF_EXPECT_TOKEN"):
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k, raising=False)
    blobs = tmp_path / "blobs_low"
    blobs.mkdir()
    data = _safetensors(b"LOW_DISK_VAE")
    (blobs / "vae.safetensors").write_bytes(data)
    monkeypatch.setenv("FAKE_HF_BLOBS_DIR", str(blobs))
    manifest = tmp_path / "manifest_low.json"
    manifest.write_text(
        json.dumps(
            [{"repo": "madebyollin/taesd", "revision": "6" * 40, "file": "vae.safetensors", "dest": "vae",
              "sha256": hashlib.sha256(data).hexdigest(), "licence_id": "MIT"}]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(l1, "stage_weight_file", lambda *_a, **_k: (_ for _ in ()).throw(OSError("no space")))
    out = tmp_path / "dl_low.json"
    try:
        rc = l1.run_weights_download(
            manifest_path=manifest, hf_home=tmp_path / "hf_low", models_dir=tmp_path / "models_low", max_seconds_raw="60",
            poll_s=0.02, log_path=tmp_path / "dl_low.log", out_path=out,
        )
    finally:
        os.environ.pop("HF_HUB_OFFLINE", None)
    assert rc == 1
    assert json.loads(out.read_text(encoding="utf-8"))["refusal"] == "WEIGHTS_DISK_LOW"

    # Best-effort interrupt and nvidia-smi OSError do not raise.
    l1._interrupt_comfy("http://127.0.0.1:1")
    sampler = l1.VramSampler(lambda *_a, **_k: (_ for _ in ()).throw(OSError("no nvidia-smi")), interval_s=0.02)
    sampler.start()
    sampler.stop()
    assert sampler.samples == 0 and sampler.peak_mib == 0.0


def test_lane1_bundle_now_cell_merges_scrubs_tars_and_splits_on_salvage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil
    import tarfile
    import lane1_bundle_now as lbn

    assert lbn.bundle_now({}) == 2
    assert "SDLAB_BUNDLE_NOW_RC=2" in capsys.readouterr().out

    no_out = tmp_path / "empty_content"
    no_out.mkdir()
    assert lbn.bundle_now({**os.environ, "SDLAB_CONTENT": str(no_out), "SDLAB_BUNDLE_RC": "143"}) == 1
    assert "SDLAB_BUNDLE_NOW_RC=1" in capsys.readouterr().out

    # Fallback loader when launch_guards.py is not in content_root.
    assert hasattr(lbn._load_launch_guards(no_out), "prepare_content_downloads")

    content = tmp_path / "content"
    (content / "lane1_out" / "pngs").mkdir(parents=True)
    (content / "lane1_out" / "pngs" / "render_01.png").write_bytes(os.urandom(90_000))
    fake_tok = "hf_" + "Zq7" * 12
    (content / "lane1_out" / "renders.jsonl").write_text(
        json.dumps({"job_id": "render_01", "status": "ok", "note": fake_tok}) + "\n", encoding="utf-8"
    )
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "lane1_render.py", content / "lane1_render.py")
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "lane3_rung.py", content / "lane3_rung.py")
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "launch_guards.py", content / "launch_guards.py")

    rc = lbn.bundle_now(
        {
            **os.environ,
            "SDLAB_CONTENT": str(content),
            "SDLAB_BUNDLE_RC": "143",
            "SDLAB_DL_CHUNK_BYTES": "32768",
        }
    )
    assert rc == 0
    out_text = capsys.readouterr().out
    assert "SDLAB_BUNDLE_NOW_RC=0" in out_text and fake_tok not in out_text
    bundle = content / "lane1_render_bundle.tar.gz"
    assert bundle.is_file()
    with tarfile.open(bundle, "r:gz") as tf:
        renders_txt = tf.extractfile("./renders.jsonl").read().decode("utf-8")  # type: ignore[union-attr]
        assert fake_tok not in renders_txt and "hf_[REDACTED]" in renders_txt
        vm_win = json.loads(tf.extractfile("./vm_window.json").read().decode("utf-8"))  # type: ignore[union-attr]
        assert vm_win["failed_rc"] == 143
    man = json.loads((content / ".sdlab_dl_lane1_render_bundle.tar.gz.manifest.json").read_text(encoding="utf-8"))
    assert man["part_count"] >= 2

