"""The lane 3 GPU rung: train-mode guards, the model download probe, the fixture dataset, the rung
job, copy-off of checkpoints and samples, and the kit's failure-path download.

Unit tests drive scripts/colab/lane3_rung.py directly (stand-ins for torch, bitsandbytes and
huggingface_hub live in tests/colab/fixtures/fake_vm_site). End-to-end tests run the kit with
--train on a GPU card against the fake colab CLI, whose fake GPU VM runs the uploaded script's own
sdlab-lane3-train and sdlab-lane3-window blocks.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import threading
import importlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from collections import namedtuple
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
LAUNCHER = COLAB_DIR / "launch_lane3_stub.sh"
FIXTURES = REPO_ROOT / "tests" / "colab" / "fixtures"
FAKE_SITE = FIXTURES / "fake_vm_site"
sys.path.insert(0, str(FIXTURES))
sys.path.insert(0, str(COLAB_DIR))

import fake_colab as fc  # noqa: E402
import lane3_rung as lr  # noqa: E402

REVISION = "75e0b4be04f60ec59a75f475837eced720f823b6"
TOKEN = "hf_" + "Zq7" * 12  # a planted fake read token
GIB = 1024**3
Usage = namedtuple("Usage", "total used free")


def _fake_mod(name: str):
    """Import one of the fake VM site modules under a private name (never shadowing a real one)."""
    spec = importlib.util.spec_from_file_location(f"_fakevm_{name}", FAKE_SITE / name / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# --- guards ------------------------------------------------------------------------------------


def test_parse_positive_number_refuses_missing_and_bad_values() -> None:
    assert lr.parse_positive_number("96.5", "X", "V") == 96.5
    for raw in (None, "", "  ", "abc", "0", "-1", "nan", "inf"):
        with pytest.raises(lr.Refusal) as exc:
            lr.parse_positive_number(raw, "HOST_RAM_THRESHOLD_MISSING", "V")
        assert exc.value.code == "HOST_RAM_THRESHOLD_MISSING"


def test_meminfo_and_host_ram_measurement() -> None:
    text = "MemTotal:       175000000 kB\nMemFree: 1 kB\nMemAvailable:   104857600 kB\nbogus line\n"
    mem = lr.parse_meminfo(text)
    assert mem["MemTotal"] == 175000000 * 1024 and mem["MemAvailable"] == 104857600 * 1024
    ok = lr.measure_host_ram(text, 100.0)
    assert ok["ok"] is True and ok["mem_available_gib"] == 100.0 and ok["mem_total_bytes"] == 175000000 * 1024
    low = lr.measure_host_ram(text, 100.5)
    assert low["ok"] is False and low["required_available_gib"] == 100.5
    assert lr.measure_host_ram("", 1.0)["ok"] is False


def test_disk_measures_each_filesystem_once_from_the_nearest_existing_ancestor(tmp_path: Path) -> None:
    a, b = tmp_path / "hf" / "not-yet", tmp_path / "train"
    b.mkdir()
    usage = {str(tmp_path): Usage(500 * GIB, 0, 80 * GIB), str(b): Usage(500 * GIB, 0, 80 * GIB)}
    rec = lr.measure_disk([a, b], 75.0, usage_fn=lambda p: usage[p], dev_fn=lambda p: 7)
    assert rec["ok"] is True and len(rec["filesystems"]) == 1
    assert rec["filesystems"][0]["measured_at"] == str(tmp_path) and len(rec["filesystems"][0]["paths"]) == 2
    rec2 = lr.measure_disk([a, b], 75.0, usage_fn=lambda p: Usage(500 * GIB, 0, (70 if p == str(b) else 90) * GIB),
                           dev_fn=lambda p: hash(p))
    assert rec2["ok"] is False and len(rec2["filesystems"]) == 2


def test_shm_record_and_its_error(tmp_path: Path) -> None:
    assert lr.measure_shm(tmp_path, usage_fn=lambda p: Usage(16 * GIB, 0, 15 * GIB))["total_gib"] == 16.0

    def boom(_p: str) -> Usage:
        raise OSError("no shm")

    assert lr.measure_shm(tmp_path, usage_fn=boom)["error"] == "no shm"


def test_query_driver_reads_nvidia_smi_or_records_why_not() -> None:
    Res = namedtuple("Res", "returncode stdout")
    good = lr.query_driver(run=lambda *a, **k: Res(0, "580.82.07, NVIDIA A100-SXM4-80GB, 81920 MiB\n"))
    assert good == {"driver_version": "580.82.07", "nvidia_smi_name": "NVIDIA A100-SXM4-80GB", "memory_total": "81920 MiB"}
    assert lr.query_driver(run=lambda *a, **k: Res(9, ""))["error"] == "nvidia-smi rc=9"

    def missing(*_a: object, **_k: object) -> Res:
        raise FileNotFoundError("nvidia-smi")

    assert "nvidia-smi" in lr.query_driver(run=missing)["error"]


def test_gpu_smoke_matmul_and_adamw8bit_step(monkeypatch: pytest.MonkeyPatch) -> None:
    torch, bnb = _fake_mod("torch"), _fake_mod("bitsandbytes")
    ticks = iter(range(0, 1000))
    rec = lr.gpu_smoke(torch, bnb, clock=lambda: next(ticks) * 0.1, target_s=0.5)
    assert rec["device_name"] == "NVIDIA A100-SXM4-80GB" and rec["torch_cuda"] == "13.0"
    assert rec["bitsandbytes_version"] == "0.50.2" and rec["adamw8bit_step"] == "ok"
    assert rec["matmul_iters"] == 320 and rec["matmul_seconds"] > 0
    monkeypatch.setenv("FAKE_VM_GPU_SMOKE", "bnb_fail")
    with pytest.raises(RuntimeError, match="no kernel image"):
        lr.gpu_smoke(torch, bnb, clock=lambda: 99.0, target_s=0.0)
    monkeypatch.setenv("FAKE_VM_GPU_SMOKE", "no_cuda")
    with pytest.raises(RuntimeError, match="is_available"):
        lr.gpu_smoke(torch, bnb)


def test_gpu_smoke_refuses_a_step_that_changes_nothing_and_a_non_finite_matmul() -> None:
    torch, bnb = _fake_mod("torch"), _fake_mod("bitsandbytes")

    class StillOpt:
        def __init__(self, params: list, lr: float = 0.0) -> None:
            pass

        def step(self) -> None:
            return None

    bnb.optim.AdamW8bit = StillOpt
    with pytest.raises(RuntimeError, match="unchanged"):
        lr.gpu_smoke(torch, bnb, clock=lambda: 99.0, target_s=0.0)
    torch.isfinite = lambda _t: torch._Bool(False)
    with pytest.raises(RuntimeError, match="not finite"):
        lr.gpu_smoke(torch, _fake_mod("bitsandbytes"), clock=lambda: 99.0, target_s=0.0)


def _guards_args(tmp_path: Path, ram: str | None, avail_kb: int = 170_000_000, disk_gib: float = 75.0) -> argparse.Namespace:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemTotal: 175000000 kB\nMemAvailable: {avail_kb} kB\n", encoding="utf-8")
    return argparse.Namespace(hf_home=str(tmp_path / "hf"), training_folder=str(tmp_path / "train"),
                              disk_required_gib=disk_gib, smoke_seconds=0.1, ram_required_gib=ram,
                              meminfo=str(meminfo), shm=str(tmp_path), out=str(tmp_path / "g.json"))


GOOD_SMOKE = {"device_name": "A100", "torch_cuda": "13.0", "bitsandbytes_version": "0.50.2", "adamw8bit_step": "ok"}
DRIVER = {"driver_version": "580.82.07"}


def _run_guards(tmp_path: Path, capsys: pytest.CaptureFixture[str], ram: str | None = "96", avail_kb: int = 170_000_000,
                free_gib: float = 200.0, smoke: object = None) -> tuple[int, dict, str]:
    def smoke_fn(target_s: float) -> dict:
        if isinstance(smoke, Exception):
            raise smoke
        return dict(GOOD_SMOKE)

    rc = lr.run_guards(_guards_args(tmp_path, ram, avail_kb), smoke_fn=smoke_fn, driver_fn=lambda: dict(DRIVER),
                       disk_usage_fn=lambda p: Usage(500 * GIB, 0, int(free_gib * GIB)))
    return rc, json.loads((tmp_path / "g.json").read_text(encoding="utf-8")), capsys.readouterr().err


def test_guards_pass_and_record_every_measurement(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc, rec, err = _run_guards(tmp_path, capsys)
    assert rc == 0 and err == "" and rec["refusals"] == []
    assert rec["gpu"]["ok"] is True and rec["gpu"]["driver_version"] == "580.82.07" and rec["gpu"]["torch_cuda"] == "13.0"
    assert rec["disk"]["ok"] is True and rec["disk"]["filesystems"][0]["free_gib"] == 200.0
    assert rec["host_ram"]["mem_total_bytes"] == 175000000 * 1024 and rec["host_ram"]["ok"] is True
    assert rec["shm"]["total_gib"] == 500.0


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"smoke": RuntimeError("CUDA error: no kernel image is available\nsecond line")}, "GPU_SMOKE_FAILED"),
        ({"free_gib": 74.9}, "DISK_FREE_LOW"),
        ({"avail_kb": 90_000_000}, "HOST_RAM_LOW"),
        ({"ram": None}, "HOST_RAM_THRESHOLD_MISSING"),
    ],
)
def test_guards_refuse_by_name_and_still_record_all_three(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                          kwargs: dict, code: str) -> None:
    rc, rec, err = _run_guards(tmp_path, capsys, **kwargs)
    assert rc == 1 and rec["refusals"] == [code]
    assert f"REFUSED: {code}: " in err
    for key in ("gpu", "disk", "host_ram", "shm"):
        assert key in rec
    assert rec["host_ram"]["mem_available_bytes"] is not None and rec["disk"]["filesystems"]
    if code == "GPU_SMOKE_FAILED":
        assert rec["gpu"]["error"] == "RuntimeError: CUDA error: no kernel image is available"


# --- download ----------------------------------------------------------------------------------


def test_probe_projection() -> None:
    slow = lr.evaluate_probe(60 * 10**6, 60.0, 57_700_000_000, 1800)
    assert slow["probe_rate_mb_s"] == 1.0 and slow["too_slow"] is True
    fast = lr.evaluate_probe(2 * GIB, 20.0, 57_700_000_000, 1800)
    assert fast["too_slow"] is False and fast["projected_total_seconds"] < 1800
    assert lr.evaluate_probe(0, 60.0, 10, 1800)["projected_total_seconds"] is None
    assert lr.evaluate_probe(0, 0.0, 0, 1800)["too_slow"] is False


def test_throttle_signals_are_counted() -> None:
    lines = ["HTTP Error 429 thrown ... Retrying in 1s", "ok", "retry 2", "429"]
    assert lr.count_throttle_signals(lines) == {"http_429_lines": 2, "retry_lines": 2}


def _dl_args(tmp_path: Path, **over: object) -> argparse.Namespace:
    base = dict(repo="Qwen/Qwen-Image", revision=REVISION, hf_home=str(tmp_path / "hf"), max_seconds="600",
                probe_seconds=1.0, probe_bytes=2 * GIB, poll_s=0.05, log=str(tmp_path / "dl.log"),
                out=str(tmp_path / "dl.json"))
    base.update(over)
    return argparse.Namespace(**base)


def _dl_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    monkeypatch.setenv("PYTHONPATH", str(FAKE_SITE))
    monkeypatch.delenv("HF_TOKEN_GGUF_READ", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("FAKE_HF_TOTAL_BYTES", str(64 * 1024**2))
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_download_fast_passes_and_records_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    _dl_env(monkeypatch, FAKE_HF_429="1")
    rc = lr.run_download(_dl_args(tmp_path), expected_fn=lambda r, v, t: 64 * 1024**2)
    rec = json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))
    assert rc == 0, capsys.readouterr().err
    assert rec["token_used"] is False and rec["downloaded_bytes"] == 64 * 1024**2
    assert rec["snapshot_path"].endswith(f"snapshots/{REVISION}") and Path(rec["snapshot_path"]).is_dir()
    assert rec["http_429_lines"] == 1 and rec["retry_lines"] == 1 and rec["rate_mb_s"] is not None
    # A second run finds everything cached: nothing new, no probe refusal.
    assert lr.run_download(_dl_args(tmp_path), expected_fn=lambda r, v, t: 64 * 1024**2) == 0
    assert json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))["downloaded_bytes"] == 0


def test_download_too_slow_is_stopped_after_the_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    _dl_env(monkeypatch, FAKE_HF_RATE_BPS="2000000")
    rc = lr.run_download(_dl_args(tmp_path, max_seconds="5"), expected_fn=lambda r, v, t: 64 * 1024**2)
    err = capsys.readouterr().err
    rec = json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))
    assert rc == 1 and rec["refusal"] == "DOWNLOAD_TOO_SLOW" and "REFUSED: DOWNLOAD_TOO_SLOW: " in err
    assert rec["probe"]["too_slow"] is True and rec["snapshot_path"] is None
    assert rec["probe"]["projected_total_seconds"] > 5


def test_download_failure_and_bad_request_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    _dl_env(monkeypatch, FAKE_HF_FAIL="1")
    assert lr.run_download(_dl_args(tmp_path), expected_fn=lambda r, v, t: 1) == 1
    assert "REFUSED: MODEL_DOWNLOAD_FAILED: " in capsys.readouterr().err
    for over, code in (({"max_seconds": None}, "DOWNLOAD_LIMIT_MISSING"), ({"revision": "main"}, "TRAIN_MODEL_REVISION_REQUIRED"),
                       ({"repo": "not a repo"}, "TRAIN_MODEL_REQUIRED")):
        assert lr.run_download(_dl_args(tmp_path, **over), expected_fn=lambda r, v, t: 1) == 1
        assert f"REFUSED: {code}: " in capsys.readouterr().err
        assert json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))["refusal"] == code


def test_download_hands_a_present_read_token_to_the_child_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token = "hf_" + "Q" * 34
    _dl_env(monkeypatch, HF_TOKEN_GGUF_READ=token, FAKE_HF_EXPECT_TOKEN=token)
    seen: list[object] = []
    rc = lr.run_download(_dl_args(tmp_path), expected_fn=lambda r, v, t: seen.append(t) or 64 * 1024**2)
    rec_text = (tmp_path / "dl.json").read_text(encoding="utf-8")
    assert rc == 0 and seen == [token]
    assert json.loads(rec_text)["token_used"] is True and token not in rec_text


def test_repo_cache_dir_and_dir_bytes(tmp_path: Path) -> None:
    assert lr.repo_cache_dir(tmp_path, "a/b") == tmp_path / "hub" / "models--a--b"
    assert lr.dir_bytes(tmp_path / "missing") == 0
    (tmp_path / "f").write_bytes(b"x" * 10)
    os.symlink(tmp_path / "f", tmp_path / "link")
    assert lr.dir_bytes(tmp_path) == 10


def test_expected_repo_bytes_uses_the_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_mod("huggingface_hub"))
    monkeypatch.setenv("FAKE_HF_TOTAL_BYTES", "400")
    assert lr.expected_repo_bytes("Qwen/Qwen-Image", REVISION) == 400


# --- dataset and job ---------------------------------------------------------------------------


def _png(i: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes([i]) * 64


def make_dataset(root: Path, n: int = 3) -> tuple[Path, Path]:
    src = root / "dataset_src"
    src.mkdir(parents=True)
    items = []
    for i in range(n):
        name = f"plate_{i:02d}.png"
        (src / name).write_bytes(_png(i))
        items.append({"image": name, "sha256": hashlib.sha256(_png(i)).hexdigest(), "caption": f"saltroad style, plate {i}"})
    manifest = root / "rung-dataset.json"
    manifest.write_text(json.dumps({"schema_version": "1.0", "items": items}, indent=2) + "\n", encoding="utf-8")
    return src, manifest


def test_dataset_verify_place_and_refusals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src, manifest = make_dataset(tmp_path)
    ns = argparse.Namespace(manifest=str(manifest), src=str(src), dest=None)
    assert lr.run_dataset(ns) == 0 and (src / "plate_00.png").exists()
    dest = tmp_path / "placed"
    assert lr.run_dataset(argparse.Namespace(manifest=str(manifest), src=str(src), dest=str(dest))) == 0
    assert (dest / "plate_01.png").read_bytes() == _png(1)
    assert (dest / "plate_01.txt").read_text(encoding="utf-8") == "saltroad style, plate 1\n"
    capsys.readouterr()
    assert lr.run_dataset(ns) == 1 and "REFUSED: DATASET_FILE_MISSING: " in capsys.readouterr().err
    shutil.copy(dest / "plate_00.png", src / "plate_00.png")
    shutil.copy(dest / "plate_00.png", src / "plate_01.png")
    shutil.copy(dest / "plate_02.png", src / "plate_02.png")
    assert lr.run_dataset(ns) == 1 and "REFUSED: DATASET_SHA_MISMATCH: " in capsys.readouterr().err
    empty = tmp_path / "empty.json"
    empty.write_text('{"items": []}', encoding="utf-8")
    assert lr.run_dataset(argparse.Namespace(manifest=str(empty), src=str(src), dest=None)) == 1


def test_committed_rung_dataset_hits_all_three_buckets() -> None:
    man = json.loads((COLAB_DIR / "lane3" / "rung-dataset.json").read_text(encoding="utf-8"))
    assert len(man["items"]) == 12 and man["source"]["licence"] == "cc-by-4.0"
    for item in man["items"]:
        # ai-toolkit copies the dataset once per resolution (512, 768, 1024) and buckets each copy by
        # area, min(w*h, res^2): an image whose area reaches 1024^2 is in every set at its own bucket.
        assert item["width"] * item["height"] >= 1000 * 1000 and item["caption"]
        assert len(item["sha256"]) == 64


def test_render_job_fills_the_committed_rung_yaml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "job.yaml"
    ns = argparse.Namespace(template=str(COLAB_DIR / "lane3" / "rung-qwen-image.yaml"), out=str(out),
                            training_folder="/content/lane3_train", dataset_dir="/content/lane3_dataset",
                            model_path=f"/content/hf_home/hub/models--Qwen--Qwen-Image/snapshots/{REVISION}")
    assert lr.run_render_job(ns) == 0
    job = out.read_text(encoding="utf-8")
    assert "__LANE3_" not in job.split("job: extension", 1)[1]
    assert f'name_or_path: "/content/hf_home/hub/models--Qwen--Qwen-Image/snapshots/{REVISION}"' in job
    for line in ("steps: 20", "save_every: 20", "sample_every: 20", "skip_first_sample: true", "num_workers: 0",
                 "max_step_saves_to_keep: 8", "low_vram: false", "quantize: false", "optimizer: adamw8bit",
                 "linear: 16", "cache_text_embeddings: true", "guidance_scale: 3", "sample_steps: 25"):
        assert line in job, line
    bad = argparse.Namespace(**{**vars(ns), "model_path": 'x"y'})
    assert lr.run_render_job(bad) == 1 and "JOB_TEMPLATE_INVALID" in capsys.readouterr().err
    tmpl = tmp_path / "t.yaml"
    tmpl.write_text('a: "__LANE3_TRAINING_FOLDER__"\n', encoding="utf-8")
    assert lr.run_render_job(argparse.Namespace(**{**vars(ns), "template": str(tmpl)})) == 1


def test_rung_yaml_differs_from_the_trained_config_only_where_stated() -> None:
    rung = (COLAB_DIR / "lane3" / "rung-qwen-image.yaml").read_text(encoding="utf-8")
    body = [ln for ln in rung.split("job: extension", 1)[1].splitlines()]
    # The trained run's values that a 20-step rung keeps.
    for line in ("      linear_alpha: 16", "      dtype: float16", "      caption_dropout_rate: 0.05",
                 "      cache_latents_to_disk: true", "      lr: 0.0001", "      dtype: bf16", "      arch: qwen_image",
                 "      quantize_te: false", "      seed: 42", "      walk_seed: true", "      width: 1024"):
        assert line in body, line
    assert sum(1 for ln in body if ln.strip().startswith("- rustline style") or "wooden chair" in ln) == 6


# --- copy-off and finish -----------------------------------------------------------------------


def test_copy_off_copies_settled_files_once_with_sha(tmp_path: Path) -> None:
    watch, bundle = tmp_path / "train" / "job", tmp_path / "bundle"
    (watch / "samples").mkdir(parents=True)
    (watch / "_latent_cache").mkdir()
    manifest = bundle / "manifest.jsonl"
    bundle.mkdir()
    state: dict = {}
    ck = watch / "job_000000020.safetensors"
    ck.write_bytes(_st(b"A" * 10))
    (watch / "_latent_cache" / "x.safetensors").write_bytes(b"L")
    (watch / "notes.yaml").write_text("x", encoding="utf-8")
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # first sight: size not yet settled
    ck.write_bytes(_st(b"A" * 20))
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # still growing
    assert lr.copy_off_once(watch, bundle, manifest, state) == 1
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # once only
    (watch / "samples" / "s.jpg").write_bytes(b"J")
    assert lr.copy_off_once(watch, bundle, manifest, state, final=True) == 1
    lines = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines()]
    assert [x["path"] for x in lines] == ["job_000000020.safetensors", "samples/s.jpg"]
    assert lines[0]["sha256"] == hashlib.sha256(_st(b"A" * 20)).hexdigest() and lines[0]["bytes"] == len(_st(b"A" * 20))
    assert lines[0]["partial"] is False
    assert not (bundle / "_latent_cache").exists()
    assert lr.copy_off_once(tmp_path / "missing", bundle, manifest, {}) == 0


def test_run_copy_off_follows_the_trainer_and_reports_log_growth(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    watch = tmp_path / "train"
    watch.mkdir()
    log = tmp_path / "train.log"
    log.write_text("a", encoding="utf-8")
    calls = iter([True, True, False])

    def tick(_s: float) -> None:
        log.write_text("ab", encoding="utf-8")
        (watch / "x.safetensors").write_bytes(b"Z")

    ns = argparse.Namespace(watch=str(watch), bundle=str(tmp_path / "b"), manifest=str(tmp_path / "b" / "m.jsonl"),
                            pid=1, train_log=str(log), interval=0.0)
    assert lr.run_copy_off(ns, alive=lambda _p: next(calls), sleep=tick) == 0
    out = capsys.readouterr().out
    assert "RUNG_PROGRESS train_log_bytes=1" in out and "RUNG_PROGRESS train_log_bytes=2" in out
    assert (tmp_path / "b" / "x.safetensors").read_bytes() == b"Z"
    assert lr.pid_alive(os.getpid()) is True and lr.pid_alive(2**22 + 12345) is False


def test_finish_gathers_records_and_marks_a_failed_run(tmp_path: Path) -> None:
    out = tmp_path / "lane3_out"
    (out / "rung_outputs").mkdir(parents=True)
    (out / "train_guards.json").write_text('{"refusals": []}', encoding="utf-8")
    (out / "model_download.json").write_text('{"token_used": false}', encoding="utf-8")
    (out / "rung_outputs" / "manifest.jsonl").write_text(
        '{"path": "j_000000020.safetensors"}\nnot json\n{"path": "samples/a.jpg"}\n', encoding="utf-8")
    assert lr.main(["finish", "--lane3-out", str(out)]) == 0
    facts = json.loads((out / "train_facts.json").read_text(encoding="utf-8"))
    assert facts["hf_token_used"] is False and facts["rung_outputs"]["checkpoints"] == ["j_000000020.safetensors"]
    assert facts["rung_outputs"]["samples"] == ["samples/a.jpg"]
    assert not (out / "vm_window.json").exists()
    assert lr.main(["finish", "--lane3-out", str(out), "--failed-rc", "1"]) == 0
    win = json.loads((out / "vm_window.json").read_text(encoding="utf-8"))
    assert win["train"] == "failed" and win["train_exit_code"] == 1 and win["lane3_mode"] == "train"
    empty = tmp_path / "empty_out"
    empty.mkdir()
    assert lr.main(["finish", "--lane3-out", str(empty)]) == 0
    assert json.loads((empty / "train_facts.json").read_text(encoding="utf-8"))["model_download"] is None


def test_cli_dispatches_every_subcommand(tmp_path: Path) -> None:
    src, manifest = make_dataset(tmp_path)
    assert lr.main(["dataset", "--manifest", str(manifest), "--src", str(src)]) == 0
    with pytest.raises(SystemExit):
        lr.main([])
    res = subprocess.run([sys.executable, str(COLAB_DIR / "lane3_rung.py"), "dataset", "--manifest", str(manifest),
                          "--src", str(src)], capture_output=True, text=True, check=False)
    assert res.returncode == 0 and "DATASET_OK items=3" in res.stdout


# --- end to end: the kit with --train on a GPU card, against the fake ---------------------------


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found
    return found


class _HubAPI(http.server.BaseHTTPRequestHandler):
    """GET /api/models/<repo>/revision/<rev>: 200 for the pinned revision with the right bearer,
    401 for any other bearer, 404 (revision) for any other revision."""

    def do_GET(self) -> None:  # noqa: N802 - http.server's name
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, {"error": "Invalid credentials in Authorization header"})
        elif not self.path.endswith(f"/revision/{REVISION}"):
            self._send(404, {"error": "Invalid rev id: not found"})
        else:
            self._send(200, {"id": "Qwen/Qwen-Image", "sha": REVISION})

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_a: object) -> None:
        return None


@pytest.fixture(scope="module")
def hub_api() -> str:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HubAPI)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


HUB_API: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _hub_api_url(hub_api: str) -> None:
    HUB_API["url"] = hub_api


def _rung_env(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    (tmp_path / "xdg").mkdir(mode=0o700)
    env["XDG_RUNTIME_DIR"] = str(tmp_path / "xdg")
    env["SDLAB_TEST_HF_ENDPOINT"] = HUB_API["url"]
    src, manifest = make_dataset(tmp_path)
    env.update({
        "GUARD_POLL_INTERVAL_S": "0.2",
        "SDLAB_TEST_RUNG_DATASET_MANIFEST": fc._to_posix(manifest),
        "EXPECTED_RUNG_DATASET_SHA": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "SDLAB_TEST_DOWNLOAD_PROBE_SECONDS": "2",
        "SDLAB_TEST_DISK_REQUIRED_GIB": "0.001",
        "SDLAB_TEST_GPU_SMOKE_SECONDS": "0.05",
        "FAKE_HF_TOTAL_BYTES": str(256 * 1024**2),
        "FAKE_VM_MEM_TOTAL_KB": "175000000",
        "FAKE_VM_MEM_AVAILABLE_KB": "170000000",
    })
    env.pop("HF_TOKEN", None)
    env["HF_TOKEN_GGUF_READ"] = TOKEN
    env["FAKE_HF_EXPECT_TOKEN"] = TOKEN
    return state_dir, env, src


def _assert_token_nowhere(out_dir: Path) -> None:
    """The planted token is in no out-dir file, no bundle member, and none of the fake CLI's records:
    its exec history (the code with --env lines, as google-colab-cli writes it) and its argv log."""
    for f in out_dir.rglob("*"):
        if f.is_file():
            assert TOKEN.encode() not in f.read_bytes(), f
    if (out_dir / "lane3_stub_bundle.tar.gz").exists():
        for name, data in _bundle(out_dir).items():
            assert TOKEN.encode() not in data, name
    state = out_dir.parent / "colab_state"
    histories = list((state / "history").glob("*.jsonl"))
    assert histories, "the fake CLI wrote no exec history"
    for f in [*histories, state / "argv.log"]:
        assert TOKEN.encode() not in f.read_bytes(), f
    # The token file was shredded on the VM, and the rig's private copy is gone.
    assert not (state / "content" / "lane3_hf_read_token").exists()
    assert not list((out_dir.parent / "xdg").glob("sdlab-l3-tok.*"))


def _launch(tmp_path: Path, env: dict[str, str], src: Path, *extra: str, out: str = "out") -> tuple[subprocess.CompletedProcess[str], Path]:
    out_dir = tmp_path / out
    args = [_bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--session", "sdlab-l3-gpu-rung",
            "--out-dir", fc._to_posix(out_dir), "--dataset-dir", fc._to_posix(src), "--model", "Qwen/Qwen-Image",
            "--model-revision", REVISION, "--host-ram-required-gib", "96.5", "--download-max-seconds", "60",
            "--wall-s", "2900", "--cap", "5", "--max-rate", "9.5", *extra]
    res = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=240, check=False)
    return res, out_dir


def _bundle(out_dir: Path) -> dict[str, bytes]:
    with tarfile.open(out_dir / "lane3_stub_bundle.tar.gz", "r:gz") as tf:
        return {m.name.removeprefix("./"): tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}  # type: ignore[union-attr]


def test_rung_success_trains_copies_off_and_records_the_guards(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok" and win["refusal_code"] is None
    assert win["train"] == "trained" and win["trained"] is True and win["lane3_mode"] == "train"
    gpu = win["train_guards"]["gpu"]
    assert gpu["device_name"] == "NVIDIA A100-SXM4-80GB" and gpu["driver_version"] == "580.82.07"
    assert gpu["torch_cuda"] == "13.0" and gpu["bitsandbytes_version"] == "0.50.2" and gpu["adamw8bit_step"] == "ok"
    assert win["train_guards"]["host_ram"]["mem_total_bytes"] == 175000000 * 1024
    assert win["train_guards"]["host_ram"]["required_available_gib"] == 96.5
    assert win["train_guards"]["disk"]["ok"] is True and "total_bytes" in win["train_guards"]["shm"]
    dl = win["model_download"]
    assert dl["revision"] == REVISION and dl["downloaded_bytes"] == 256 * 1024**2 and dl["token_used"] is True
    assert win["hf_token_used"] is True and dl["rate_mb_s"] is not None and "http_429_lines" in dl
    _assert_token_nowhere(out_dir)
    assert win["rung_outputs"]["checkpoints"] == ["rustline_style_v5/rustline_style_v5.safetensors",
                                                  "rustline_style_v5/rustline_style_v5_000000020.safetensors"]
    assert win["rung_outputs"]["samples"] == ["rustline_style_v5/samples/1762400000000__000000020_0.jpg"]
    assert win["checkpoint_path"].endswith("rung_outputs/rustline_style_v5/rustline_style_v5_000000020.safetensors")
    members = _bundle(out_dir)
    manifest = [json.loads(x) for x in members["rung_outputs/manifest.jsonl"].decode().splitlines()]
    for line in manifest:
        assert hashlib.sha256(members["rung_outputs/" + line["path"]]).hexdigest() == line["sha256"]
    job = members["rung_job.yaml"].decode()
    assert f'snapshots/{REVISION}"' in job and "steps: 20" in job
    vitals = (out_dir / "vitals.log").read_text(encoding="utf-8")
    assert "COPY_OFF " in vitals and "TRAIN_GUARDS " in vitals and "MODEL_DOWNLOAD " in vitals


@pytest.mark.parametrize(
    ("env_over", "code", "downloaded"),
    [
        ({"FAKE_VM_GPU_SMOKE": "bnb_fail"}, "GPU_SMOKE_FAILED", False),
        ({"SDLAB_TEST_DISK_REQUIRED_GIB": "1000000"}, "DISK_FREE_LOW", False),
        ({"FAKE_VM_MEM_AVAILABLE_KB": "50000000"}, "HOST_RAM_LOW", False),
        ({"FAKE_HF_RATE_BPS": "1000000", "FAKE_HF_TOTAL_BYTES": str(4 * GIB)}, "DOWNLOAD_TOO_SLOW", True),
    ],
)
def test_rung_refusals_stop_before_training_and_still_bundle(tmp_path: Path, env_over: dict, code: str, downloaded: bool) -> None:
    _, env, src = _rung_env(tmp_path)
    env.update(env_over)
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == code and win["refusal_code"] == code
    assert win["trained"] is False and win["train"] is None
    assert win["train_guards"]["host_ram"]["mem_available_bytes"] is not None
    assert (win.get("model_download") is not None) is downloaded
    if code == "DOWNLOAD_TOO_SLOW":
        assert win["model_download"]["probe"]["too_slow"] is True
    members = _bundle(out_dir)
    assert "train_guards.json" in members and "train.log" not in members
    assert "BUNDLE_AFTER_FAILURE: downloaded" in (out_dir / "guards.log").read_text(encoding="utf-8")
    _assert_token_nowhere(out_dir)


def test_rung_mid_run_failure_downloads_what_was_copied_off(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    env["FAKE_VM_TRAIN"] = "fail_after_save"
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "TRAIN_FAILED" and win["trained"] is False
    assert win["rung_outputs"]["checkpoints"] == ["rustline_style_v5/rustline_style_v5_000000020.safetensors"]
    members = _bundle(out_dir)
    assert b"FAKE-LORA-STEP-20" in members["rung_outputs/rustline_style_v5/rustline_style_v5_000000020.safetensors"]
    assert b"CUDA out of memory" in members["train.log"]
    _assert_token_nowhere(out_dir)


@pytest.mark.parametrize(
    ("drop", "code"),
    [("--model-revision", "TRAIN_MODEL_REVISION_REQUIRED"), ("--host-ram-required-gib", "HOST_RAM_THRESHOLD_MISSING"),
     ("--download-max-seconds", "DOWNLOAD_LIMIT_MISSING"), ("--dataset-dir", "TRAIN_DATASET_REQUIRED"),
     ("--model", "TRAIN_MODEL_REQUIRED"), ("token", "HF_READ_TOKEN_MISSING"),
     ("--wall-s", "TRAIN_WALL_REQUIRED"), ("--cap", "TRAIN_CAP_REQUIRED"),
     ("--max-rate", "TRAIN_MAX_RATE_REQUIRED")],
)
def test_kit_refuses_a_rung_request_missing_a_value_before_any_colab_call(tmp_path: Path, drop: str, code: str) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    args = {"--model": "Qwen/Qwen-Image", "--model-revision": REVISION, "--host-ram-required-gib": "96.5",
            "--download-max-seconds": "60", "--dataset-dir": fc._to_posix(src), "--wall-s": "2900", "--cap": "5",
            "--max-rate": "9.5"}
    if drop == "token":
        env.pop("HF_TOKEN_GGUF_READ")
    else:
        del args[drop]
    flat = [x for kv in args.items() for x in kv]
    res = subprocess.run([_bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--out-dir",
                          fc._to_posix(tmp_path / "out"), *flat], env=env, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=60, check=False)
    assert res.returncode == 2 and f"REFUSED: {code}:" in res.stderr
    assert not (state_dir / "calls.log").exists() and not (state_dir / "card.txt").exists()


def test_kit_refuses_a_dataset_that_does_not_match_its_manifest(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    (src / "plate_01.png").write_bytes(b"changed")
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    assert "REFUSED: DATASET_SHA_MISMATCH: " in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert not (state_dir / "card.txt").exists()


def test_read_token_reaches_only_the_download_and_appears_in_no_file(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert json.loads((out_dir / "window.json").read_text(encoding="utf-8"))["hf_token_used"] is True
    _assert_token_nowhere(out_dir)
    # The fake download printed the token: the VM-side scrub replaced it before the bundle was made.
    assert b"hf_[REDACTED]" in _bundle(out_dir)["model_download.log"]
    # The emitted .env never carries it, and emit does not need it.
    emitted = tmp_path / "emit.sh"
    em = subprocess.run([_bash(), fc._to_posix(LAUNCHER), "--emit-remote-script", fc._to_posix(emitted), "--train",
                         "--model", "Qwen/Qwen-Image", "--model-revision", REVISION, "--host-ram-required-gib", "1",
                         "--download-max-seconds", "60"], env=env, capture_output=True, text=True, check=False)
    assert em.returncode == 0 and TOKEN not in (tmp_path / "emit.sh.env").read_text(encoding="utf-8")


# --- fix round 2 -------------------------------------------------------------------------------


def test_kit_refuses_a_wall_that_cannot_cover_the_rung(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    res, _ = _launch(tmp_path, env, src, "--wall-s", "1200")
    assert res.returncode == 2 and "REFUSED: TRAIN_WALL_TOO_SHORT: --wall-s 1200 minus grace 60 must cover 2760 s" in res.stderr
    assert not (state_dir / "card.txt").exists()


def test_rung_without_a_sample_image_is_refused(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    env["FAKE_VM_TRAIN"] = "no_sample"
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "TRAIN_SAMPLE_MISSING" and win["trained"] is False
    _assert_token_nowhere(out_dir)


def _rung_processes(root: Path) -> list[int]:
    return lr.rung_pids(root, skip=(os.getpid(),))


def test_rig_side_kill_still_brings_back_the_outputs(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_VM_TRAIN": "hang_after_save", "STALL_S": "4", "SETUP_STALL_S": "4"})
    res, out_dir = _launch(tmp_path, env, src)
    content = state_dir / "content"
    try:
        assert res.returncode != 0
        guards = (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "BUNDLE_AFTER_FAILURE: downloaded" in guards, guards[-2000:]
        assert "BUNDLE_NOW: killed" in (out_dir / "bundle_now.log").read_text(encoding="utf-8")
        members = _bundle(out_dir)
        assert b"FAKE-LORA-STEP-20" in members["rung_outputs/rustline_style_v5/rustline_style_v5_000000020.safetensors"]
        # The killed exec's cell still held the session's one kernel: the kit restarted it first.
        assert "RESTART -s sdlab-l3-gpu-rung" in (state_dir / "restarts.log").read_text(encoding="utf-8")
        assert "rung_outputs/rustline_style_v5/samples/1762400000000__000000020_0.jpg" in members
        assert json.loads(members["vm_window.json"])["train"] == "failed"
        assert _rung_processes(content) == []
        _assert_token_nowhere(out_dir)
    finally:
        for pid in _rung_processes(content):
            os.kill(pid, 9)


def test_kit_model_check_refuses_a_dead_token_before_any_spend(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env["HF_TOKEN_GGUF_READ"] = "hf_" + "Dead" * 9
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    assert "REFUSED: MODEL_AUTH_FAILED: Qwen/Qwen-Image@" in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert not (state_dir / "card.txt").exists()
    res2, out2 = _launch(tmp_path, env | {"HF_TOKEN_GGUF_READ": TOKEN}, src, "--model-revision", "f" * 40, out="out2")
    assert "REFUSED: MODEL_REVISION_NOT_FOUND: " in (out2 / "guards.log").read_text(encoding="utf-8")


def test_check_model_api_names_each_failure() -> None:
    import io
    import urllib.error

    def http_err(code: int, body: str):
        def opener(req, timeout):  # noqa: ANN001
            assert "hf_" not in req.full_url
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(body.encode()))
        return opener

    for code, body, name in ((401, "", "MODEL_AUTH_FAILED"), (403, "", "MODEL_AUTH_FAILED"),
                             (404, '{"error": "Invalid rev id"}', "MODEL_REVISION_NOT_FOUND"),
                             (404, '{"error": "Repository not found"}', "MODEL_METADATA_FAILED"),
                             (502, "", "MODEL_METADATA_FAILED")):
        with pytest.raises(lr.Refusal) as exc:
            lr.check_model_api("Qwen/Qwen-Image", REVISION, TOKEN, opener=http_err(code, body))
        assert exc.value.code == name and TOKEN not in str(exc.value)

    def down(req, timeout):  # noqa: ANN001
        raise urllib.error.URLError("Name or service not known")

    with pytest.raises(lr.Refusal) as exc:
        lr.check_model_api("a/b", REVISION, None, opener=down)
    assert exc.value.code == "MODEL_METADATA_FAILED"

    class Resp(io.BytesIO):
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *a: object) -> None:
            return None

    with pytest.raises(lr.Refusal) as exc:
        lr.check_model_api("a/b", REVISION, TOKEN, opener=lambda r, timeout: Resp(b'{"sha": "other"}'))
    assert exc.value.code == "MODEL_REVISION_NOT_FOUND"
    assert lr.check_model_api("a/b", REVISION, TOKEN, opener=lambda r, timeout: Resp(json.dumps({"sha": REVISION}).encode()))["ok"]


def test_model_check_cli_reads_the_token_from_the_environment(monkeypatch: pytest.MonkeyPatch,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SDLAB_TEST_HF_ENDPOINT", HUB_API["url"])
    monkeypatch.setenv("HF_TOKEN_GGUF_READ", TOKEN)
    assert lr.main(["model-check", "--repo", "Qwen/Qwen-Image", "--revision", REVISION]) == 0
    assert "MODEL_CHECK_OK" in capsys.readouterr().out
    monkeypatch.delenv("HF_TOKEN_GGUF_READ")
    assert lr.main(["model-check", "--repo", "Qwen/Qwen-Image", "--revision", REVISION]) == 1
    assert "REFUSED: MODEL_AUTH_FAILED" in capsys.readouterr().err


@pytest.mark.parametrize(("mode", "code"), [("401", "MODEL_AUTH_FAILED"), ("404rev", "MODEL_REVISION_NOT_FOUND"),
                                            ("net", "MODEL_METADATA_FAILED")])
def test_vm_metadata_failures_are_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str], mode: str, code: str) -> None:
    hub = _fake_mod("huggingface_hub")
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    _dl_env(monkeypatch, FAKE_HF_INFO_ERROR=mode)
    assert lr.run_download(_dl_args(tmp_path)) == 1
    err = capsys.readouterr().err
    assert f"REFUSED: {code}: " in err and "Traceback" not in err
    assert json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))["refusal"] == code


def test_download_hard_limit_kills_a_stalled_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    _dl_env(monkeypatch, FAKE_HF_STALL="1")
    rc = lr.run_download(_dl_args(tmp_path, max_seconds="2", probe_seconds=100.0, probe_bytes=10 * GIB),
                         expected_fn=lambda r, v, t: 64 * 1024**2)
    rec = json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))
    assert rc == 1 and rec["refusal"] == "DOWNLOAD_TOO_SLOW" and rec["hard_limit_hit"] is True
    assert "hard limit" in capsys.readouterr().err


def test_download_offline_reads_only_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _dl_env(monkeypatch, HF_HUB_OFFLINE="1")

    def no_metadata(*_a: object) -> int:
        raise AssertionError("no metadata call when the hub is offline")

    assert lr.run_download(_dl_args(tmp_path), expected_fn=no_metadata) == 0
    rec = json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))
    assert rec["offline"] is True and rec["probe"] is None and rec["snapshot_path"]


def test_copy_off_survives_a_vanished_file_and_the_final_sweep_catches_up(tmp_path: Path,
                                                                           monkeypatch: pytest.MonkeyPatch,
                                                                           capsys: pytest.CaptureFixture[str]) -> None:
    watch, bundle = tmp_path / "train", tmp_path / "bundle"
    watch.mkdir()
    bundle.mkdir()
    (watch / "a_000000020.safetensors").write_bytes(b"A")
    (watch / "b.jpg").write_bytes(b"B")
    real_copy = shutil.copy2
    calls = {"n": 0}

    def flaky(src, dst):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            raise FileNotFoundError(f"{src} vanished")
        return real_copy(src, dst)

    monkeypatch.setattr(lr.shutil, "copy2", flaky)
    manifest = bundle / "manifest.jsonl"
    assert lr.copy_off_once(watch, bundle, manifest, {}, final=True) == 1
    assert "COPY_OFF_SKIPPED a_000000020.safetensors: FileNotFoundError" in capsys.readouterr().out
    # The final sweep, in its own process run (--final-only), takes what is missing and nothing twice.
    assert lr.main(["copy-off", "--final-only", "--watch", str(watch), "--bundle", str(bundle),
                    "--manifest", str(manifest)]) == 0
    paths = sorted(json.loads(x)["path"] for x in manifest.read_text(encoding="utf-8").splitlines())
    assert paths == ["a_000000020.safetensors", "b.jpg"]
    assert lr.main(["copy-off", "--watch", str(watch), "--bundle", str(bundle), "--manifest", str(manifest)]) == 2


def test_bundle_now_kills_sweeps_and_tars(tmp_path: Path) -> None:
    root = tmp_path / "content"
    out = root / "lane3_out"
    out.mkdir(parents=True)
    (out / "setup.log").write_text("x\n", encoding="utf-8")
    (root / "lane3_train" / "job").mkdir(parents=True)
    (root / "lane3_train" / "job" / "job_000000020.safetensors").write_bytes(b"CK")
    proc = tmp_path / "proc"
    for pid, cmd in ((11, f"bash {root}/remote_lane3_stub.sh"), (12, f"python {root}/ai-toolkit/run.py job.yaml"),
                     (13, "python unrelated.py"), (14, f"python {root}/lane3_rung.py copy-off --pid 12")):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "cmdline").write_bytes(cmd.replace(" ", "\0").encode())
    (proc / "15").mkdir()
    (proc / "self").mkdir()
    killed: list[int] = []

    def kill(pid: int, _sig: int) -> None:
        killed.append(pid)
        if pid == 14:
            raise ProcessLookupError

    ns = argparse.Namespace(content=str(root), rc=93, settle_s=0.0)
    assert lr.run_bundle_now(ns, kill=kill, proc=proc) == 0
    assert sorted(killed) == [11, 12, 14]
    with tarfile.open(root / "lane3_stub_bundle.tar.gz") as tf:
        names = {m.name.removeprefix("./") for m in tf.getmembers()}
    assert "rung_outputs/job/job_000000020.safetensors" in names and "vm_window.json" in names
    assert json.loads((out / "vm_window.json").read_text(encoding="utf-8"))["train_exit_code"] == 93
    # A finished script already bundled: nothing to kill, the bundle is kept.
    assert lr.run_bundle_now(ns, kill=kill, proc=tmp_path / "empty") == 0
    assert lr.run_bundle_now(argparse.Namespace(content=str(tmp_path / "nothing"), rc=1, settle_s=0.0),
                             kill=kill, proc=tmp_path / "empty") == 1


def test_bundle_now_cell_needs_its_env_and_runs_lane3_rung(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sys.path.insert(0, str(COLAB_DIR))
    import lane3_bundle_now as bn

    assert bn.bundle_now({}) == 2
    root = tmp_path / "content"
    (root / "lane3_out").mkdir(parents=True)
    shutil.copy(COLAB_DIR / "lane3_rung.py", root / "lane3_rung.py")
    assert bn.bundle_now({**os.environ, "SDLAB_CONTENT": str(root), "SDLAB_BUNDLE_RC": "143"}) == 0
    assert "SDLAB_BUNDLE_NOW_RC=0" in capsys.readouterr().out
    assert (root / "lane3_stub_bundle.tar.gz").is_file()


# --- fix round 3 -------------------------------------------------------------------------------


def test_download_failure_tail_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    _dl_env(monkeypatch, HF_TOKEN_GGUF_READ=TOKEN)

    class FailedChild:
        def __init__(self, cmd: list, stdout, stderr, env) -> None:  # noqa: ANN001
            stdout.write(f"Fetching 4 files\nusing token {TOKEN}\nOSError: 401 Client Error\n")
            stdout.flush()

        def poll(self) -> int:
            return 1

        def wait(self) -> int:
            return 1

    assert lr.run_download(_dl_args(tmp_path), expected_fn=lambda r, v, t: 1, popen=FailedChild) == 1
    out = capsys.readouterr()
    assert "REFUSED: MODEL_DOWNLOAD_FAILED: " in out.err and "using token hf_[REDACTED]" in out.err
    assert TOKEN not in out.err
    assert TOKEN not in out.out
    assert TOKEN not in (tmp_path / "dl.json").read_text(encoding="utf-8")


def test_metadata_exception_text_never_reaches_any_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]) -> None:
    _dl_env(monkeypatch, HF_TOKEN_GGUF_READ=TOKEN)

    class Echo(Exception):
        def __init__(self) -> None:
            super().__init__(f"401 Unauthorized for GET with headers Authorization: Bearer {TOKEN} token={TOKEN}")
            self.response = type("R", (), {"status_code": 401})()

    def boom(*_a: object) -> int:
        raise Echo()

    assert lr.run_download(_dl_args(tmp_path), expected_fn=boom) == 1
    out = capsys.readouterr()
    assert "REFUSED: MODEL_AUTH_FAILED: " in out.err and "http=401" in out.err
    for text in (out.err, out.out, (tmp_path / "dl.json").read_text(encoding="utf-8")):
        assert TOKEN not in text and "Bearer" not in text
    assert lr.mask_log_text(f"Authorization: Bearer abc.def {TOKEN}") == "Authorization: Bearer [REDACTED] hf_[REDACTED]"


def test_remote_runner_scrubs_relayed_lines() -> None:
    import remote_runner as rr

    assert rr.scrub_line(f"Authenticated download with token {TOKEN}\n") == "Authenticated download with token hf_[REDACTED]\n"
    assert lr.mask_log_text("x hf_short y") == "x hf_short y"


def test_failed_download_prints_no_token_into_exec_history(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    env["FAKE_HF_FAIL"] = "1"
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    assert json.loads((out_dir / "window.json").read_text(encoding="utf-8"))["refusal_code"] == "MODEL_DOWNLOAD_FAILED"
    history = (tmp_path / "colab_state" / "history" / "sdlab-l3-gpu-rung.jsonl").read_text(encoding="utf-8")
    assert '"outputs"' in history and "MODEL_DOWNLOAD_FAILED" in history
    _assert_token_nowhere(out_dir)


def test_token_file_is_removed_when_its_upload_fails(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    env["FAKE_COLAB_UPLOAD_HTTP_500_FOR"] = "lane3_hf_read_token"
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    assert "REFUSED: UPLOAD_FAILED: " in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert not list((tmp_path / "xdg").glob("sdlab-l3-tok.*")), "the trap left the rig's token file behind"


def test_token_staging_failure_refuses_before_the_window_opens(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env["XDG_RUNTIME_DIR"] = str(tmp_path / "no-such-runtime-dir")
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    assert "REFUSED: HF_TOKEN_STAGING_FAILED: " in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert not (state_dir / "card.txt").exists(), "the session was opened before the token was staged"


def test_truncated_checkpoint_is_partial_and_does_not_count(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    env["FAKE_VM_TRAIN"] = "truncated_save"
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "TRAIN_CHECKPOINT_MISSING" and win["trained"] is False
    manifest = [json.loads(x) for x in _bundle(out_dir)["rung_outputs/manifest.jsonl"].decode().splitlines()]
    cks = [m for m in manifest if m["path"].endswith(".safetensors")]
    assert cks and all(m["partial"] is True for m in cks)


def _st(data: bytes = b"0123456789") -> bytes:
    import struct

    hdr = json.dumps({"w": {"dtype": "U8", "shape": [len(data)], "data_offsets": [0, len(data)]},
                      "__metadata__": {"format": "pt"}}).encode()
    return struct.pack("<Q", len(hdr)) + hdr + data


def test_safetensors_completeness_and_checkpoint_pick(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good, short, junk, tiny = (tmp_path / n for n in ("g.safetensors", "s.safetensors", "j.safetensors", "t.safetensors"))
    good.write_bytes(_st())
    short.write_bytes(_st()[:-3])
    junk.write_bytes(b"\xff" * 16)
    tiny.write_bytes(b"1234")
    assert lr.safetensors_complete(good) is True
    assert not any(lr.safetensors_complete(p) for p in (short, junk, tiny, tmp_path / "missing.safetensors"))
    bundle = tmp_path / "b"
    manifest = bundle / "manifest.jsonl"
    bundle.mkdir()
    manifest.write_text('{"path": "job_000000020.safetensors", "bytes": 9, "partial": true}\n'
                        '{"path": "samples/a.jpg", "bytes": 1}\nnot json\n', encoding="utf-8")
    ns = argparse.Namespace(bundle=str(bundle), manifest=str(manifest))
    assert lr.run_checkpoint(ns) == 1
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write('{"path": "job_000000010.safetensors", "bytes": 9, "partial": false}\n')
    capsys.readouterr()
    assert lr.run_checkpoint(ns) == 0
    assert capsys.readouterr().out.strip() == str(bundle / "job_000000010.safetensors")
    assert lr.run_checkpoint(argparse.Namespace(bundle=str(bundle), manifest=str(tmp_path / "none.jsonl"))) == 1


REDIRECT_PATH = f"/api/models/Qwen/Qwen-Image/revision/{REVISION}"


def test_model_check_refuses_a_cross_host_redirect_and_keeps_the_token(tmp_path: Path) -> None:
    seen: list[str | None] = []

    class Other(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen.append(self.headers.get("Authorization"))
            data = json.dumps({"sha": REVISION}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_a: object) -> None:
            return None

    other = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Other)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    target = f"http://localhost:{other.server_address[1]}"

    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header("Location", target + REDIRECT_PATH)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_a: object) -> None:
            return None

    redir = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=redir.serve_forever, daemon=True).start()
    try:
        with pytest.raises(lr.Refusal) as exc:
            lr.check_model_api("Qwen/Qwen-Image", REVISION, TOKEN, base=f"http://127.0.0.1:{redir.server_address[1]}")
        assert exc.value.code == "MODEL_METADATA_FAILED" and "http=302" in exc.value.detail
        assert seen == [], f"the redirect target received a request (Authorization={seen})"
    finally:
        other.shutdown()
        redir.shutdown()


# --- fix round 4 -------------------------------------------------------------------------------


def test_a_partial_copy_is_copied_again_until_complete(tmp_path: Path) -> None:
    watch, bundle = tmp_path / "train", tmp_path / "b"
    watch.mkdir()
    bundle.mkdir()
    manifest = bundle / "manifest.jsonl"
    ck = watch / "job_000000020.safetensors"
    full = _st(b"x" * 300)
    ck.write_bytes(full[:-100])  # the save paused part-way
    state: dict = {}
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # first sight
    assert lr.copy_off_once(watch, bundle, manifest, state) == 1  # size held: copied, partial
    ck.write_bytes(full)  # the save finishes
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # size changed: wait
    assert lr.copy_off_once(watch, bundle, manifest, state) == 1  # copied again, complete
    assert lr.copy_off_once(watch, bundle, manifest, state, final=True) == 0  # now done
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines()]
    assert [r["partial"] for r in rows] == [True, False]
    ns = argparse.Namespace(bundle=str(bundle), manifest=str(manifest))
    assert lr.run_checkpoint(ns) == 0
    out = bundle.parent / "lane3_out"
    (out / "rung_outputs").mkdir(parents=True)
    shutil.copy(manifest, out / "rung_outputs" / "manifest.jsonl")
    assert lr.main(["finish", "--lane3-out", str(out)]) == 0
    facts = json.loads((out / "train_facts.json").read_text(encoding="utf-8"))
    assert facts["rung_outputs"]["checkpoints"] == ["job_000000020.safetensors"]
    assert facts["rung_outputs"]["partial_checkpoints"] == []
    # A copy-off restarted from this manifest does not take the complete file again.
    assert "job_000000020.safetensors" in lr.load_done(manifest)


def test_final_sweep_recopies_a_partial_file(tmp_path: Path) -> None:
    watch, bundle = tmp_path / "train", tmp_path / "b"
    watch.mkdir()
    bundle.mkdir()
    manifest = bundle / "manifest.jsonl"
    ck = watch / "job.safetensors"
    full = _st(b"y" * 300)
    ck.write_bytes(full[:-50])
    state: dict = {}
    assert lr.copy_off_once(watch, bundle, manifest, state, final=True) == 1
    ck.write_bytes(full)
    assert lr.copy_off_once(watch, bundle, manifest, state, final=True) == 1
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines()]
    assert [r["partial"] for r in rows] == [True, False]
    assert "job.safetensors" not in lr.load_done(bundle / "none.jsonl")


def _run_token_and_download_blocks(tmp_path: Path, with_token: bool) -> str:
    tmp_path.mkdir(parents=True, exist_ok=True)
    script = tmp_path / "remote.sh"
    res = subprocess.run([_bash(), fc._to_posix(LAUNCHER), "--emit-remote-script", fc._to_posix(script)],
                         capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    text = script.read_text(encoding="utf-8")
    lines = text.split("\n")

    def block(name: str) -> str:
        a = lines.index(f"# >>> {name}")
        b = lines.index(f"# <<< {name}", a)
        return "\n".join(lines[a:b + 1]) + "\n"

    vm = tmp_path / "vm"
    (vm / "lane3_out").mkdir(parents=True)
    if with_token:
        (vm / "lane3_hf_read_token").write_text(TOKEN, encoding="utf-8")
    probe = tmp_path / "probe.sh"
    probe.write_text('#!/usr/bin/env bash\nif [ "${HF_TOKEN_GGUF_READ+set}" = set ]; then echo TOKEN_VAR_SET; else echo TOKEN_VAR_UNSET; fi\n',
                     encoding="utf-8")
    probe.chmod(0o755)
    run = tmp_path / "run.sh"
    run.write_text("set -euo pipefail\nLANE3_MODEL_NAME_OR_PATH=a/b LANE3_HF_HOME=/x LANE3_DOWNLOAD_PROBE_SECONDS=1 LANE3_DOWNLOAD_PROBE_BYTES=1\n" + (block("sdlab-hf-token") + 'LANE3_PY="' + str(probe) + '"\n'
                   + block("sdlab-lane3-download")).replace("/content", str(vm)), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "HF_TOKEN_GGUF_READ"}
    out = subprocess.run([_bash(), str(run)], env=env, capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    assert not (vm / "lane3_hf_read_token").exists()
    return out.stdout


def test_token_variable_reaches_the_download_only_when_a_token_was_staged(tmp_path: Path) -> None:
    assert "TOKEN_VAR_SET" in _run_token_and_download_blocks(tmp_path / "with", with_token=True)
    assert "TOKEN_VAR_UNSET" in _run_token_and_download_blocks(tmp_path / "without", with_token=False)


def test_download_records_token_used_from_the_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _dl_env(monkeypatch)
    assert lr.run_download(_dl_args(tmp_path), expected_fn=lambda r, v, t: 64 * 1024**2) == 0
    assert json.loads((tmp_path / "dl.json").read_text(encoding="utf-8"))["token_used"] is False


def test_bundle_now_also_finds_the_download_grandchild(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    (proc / "21").mkdir(parents=True)
    (proc / "21" / "cmdline").write_bytes(
        b"python\0-c\0import os, sys\nfrom huggingface_hub import snapshot_download\npath = snapshot_download(repo_id=sys.argv[1], revision=x)\0a/b\0")
    assert lr.rung_pids(tmp_path / "content", proc) == [21]


# --- live rate guard (rung 1 was stopped by hand at 8.88/h; the kit read 0.0 and projected 0.26) -


def test_gpu_window_with_no_post_open_rate_refuses_rate_unread(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_STR": "0.00/hr",
                "SDLAB_TEST_RATE_READ_INTERVAL_S": "0.05"})
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "RATE_UNREAD"
    assert win["rate_check"]["live_rate"] is None and win["rate_check"]["polls"] == 24
    uploads = state_dir / "uploads.log"
    assert not uploads.exists() or "UPLOAD_OK" not in uploads.read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")
    assert win["rate_source"] == "live_rate_unread" and win["rate_used_for_cap_and_projection"] == 0.0


def test_gpu_window_above_max_rate_refuses_before_any_upload(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_SEQ": "0.00/hr,8.88/hr",
                "SDLAB_TEST_RATE_READ_INTERVAL_S": "0.05"})
    res, out_dir = _launch(tmp_path, env, src, "--max-rate", "8.0")
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "RATE_ABOVE_MAX"
    assert win["rate_check"] == {"live_rate": 8.88, "pre_open_rate": 0.0, "window_rate": 8.88, "max_rate": 8.0, "polls": 2}
    uploads = state_dir / "uploads.log"
    assert not uploads.exists() or "UPLOAD_OK" not in uploads.read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")


def test_gpu_window_under_max_rate_proceeds_on_the_live_rate(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_SEQ": "0.00/hr,8.88/hr",
                "SDLAB_TEST_RATE_READ_INTERVAL_S": "0.05"})
    res, out_dir = _launch(tmp_path, env, src, "--max-rate", "9.5")
    assert res.returncode == 0, res.stderr
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok" and win["trained"] is True
    assert win["rate_check"]["live_rate"] == 8.88 and win["rate_check"]["max_rate"] == 9.5
    assert win["rate_source"] == "post_open_measured" and win["rate_used_for_cap_and_projection"] == 8.88


def test_gpu_window_at_8_88_trips_the_cap_on_time(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_SEQ": "0.00/hr,8.88/hr",
                "SDLAB_TEST_RATE_READ_INTERVAL_S": "0.05", "FAKE_VM_TRAIN": "hang_after_save",
                "GUARD_POLL_INTERVAL_S": "0.5"})
    res, out_dir = _launch(tmp_path, env, src, "--cap", "0.06", "--margin", "0.01")
    content = state_dir / "content"
    try:
        assert res.returncode != 0
        win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
        assert win["refusal_code"] is None or win["status"] != "ok"
        trips = [json.loads(ln)["cap"] for ln in (out_dir / "guards.log").read_text(encoding="utf-8").splitlines()
                 if ln.startswith("{") and '"cap"' in ln]
        tripped = [c for c in trips if c["tripped"]]
        assert tripped, "the cap never tripped"
        # 0.05 units at 8.88/h is 20.3 s; with 0.5 s polls the trip lands within a few seconds of it.
        elapsed = tripped[0]["spend_ccu"] / 8.88 * 3600
        assert 20.2 <= elapsed <= 30, elapsed
        assert all(c["spend_ccu"] < 0.05 for c in trips if not c["tripped"])
    finally:
        for pid in _rung_processes(content):
            os.kill(pid, 9)


def test_live_rate_policy_never_falls_back_to_the_configured_rate() -> None:
    import launch_guards as lg

    text0 = "Current balance: 1812.22 compute units\nUsage rate: 0.00/hr\nActive assignments: 1\n"
    gpu = lg.parse_usage_text(text0, configured_rate=0.26, session_opened=True, pre_open_rate=0.0,
                              live_rate_required=True)
    assert gpu["rate_for_projection"] == 0.0 and gpu["rate_source"] == "live_rate_unread"
    gpu2 = lg.parse_usage_text(text0.replace("0.00/hr", "8.88/hr"), configured_rate=0.26, session_opened=True,
                               pre_open_rate=0.0, live_rate_required=True)
    assert gpu2["rate_for_projection"] == 8.88 and gpu2["rate_source"] == "post_open_measured"
    # The CPU stub is unchanged: a 0.00 post-open reading still projects with the labelled configured rate.
    cpu = lg.parse_usage_text(text0, configured_rate=0.26, session_opened=True, pre_open_rate=0.0)
    assert cpu["rate_for_projection"] == 0.26 and cpu["rate_source"] == "configured_pending_post_open_rate"


def test_cap_at_8_88_per_hour_trips_at_20_3_seconds() -> None:
    import launch_guards as lg

    kw = dict(mode="live", cap=0.06, margin=0.01, start_balance=100.0, current_balance=100.0, rate_ccu_per_hour=8.88)
    assert lg.evaluate_cap_guard(elapsed_s=20.0, **kw)["tripped"] is False
    assert lg.evaluate_cap_guard(elapsed_s=20.3, **kw)["tripped"] is True
    # The balance drop counts too: the larger of the drop and the projection is the spend.
    assert lg.evaluate_cap_guard(elapsed_s=0.0, **{**kw, "current_balance": 99.94})["tripped"] is True
