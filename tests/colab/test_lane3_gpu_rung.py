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
import time
import sys
import tarfile
from collections import namedtuple
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
FIXTURES = REPO_ROOT / "tests" / "colab" / "fixtures"
FAKE_SITE = FIXTURES / "fake_vm_site"
sys.path.insert(0, str(FIXTURES))
sys.path.insert(0, str(COLAB_DIR))

import lane3_rung as lr  # noqa: E402

REVISION = "75e0b4be04f60ec59a75f475837eced720f823b6"

def _png(seed: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + f"plate-{seed}".encode()


def _st(data: bytes = b"0123456789") -> bytes:
    import struct

    hdr = json.dumps({"w": {"dtype": "U8", "shape": [len(data)], "data_offsets": [0, len(data)]},
                      "__metadata__": {"format": "pt"}}).encode()
    return struct.pack("<Q", len(hdr)) + hdr + data
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
    rung500 = (COLAB_DIR / "lane3" / "rung-qwen-image-500.yaml").read_text(encoding="utf-8")
    body500 = [ln for ln in rung500.split("job: extension", 1)[1].splitlines()]
    diff_20_500 = [(a.strip(), b.strip()) for a, b in zip(body, body500, strict=True) if a != b]
    assert diff_20_500 == [
        ("save_every: 20", "save_every: 250"),
        ("steps: 20", "steps: 500"),
        ("sample_every: 20", "sample_every: 250"),
    ]
    assert "      skip_first_sample: true" in body500 and "      num_workers: 0" in body500


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
    (watch / "_latent_cache" / "x.safetensors").write_bytes(_st(b"L"))
    (watch / "notes.yaml").write_text("x", encoding="utf-8")
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # first sight: size not yet settled
    ck.write_bytes(_st(b"A" * 20))
    # _latent_cache/x.safetensors and notes.yaml settled; ck is still growing.
    assert lr.copy_off_once(watch, bundle, manifest, state) == 2
    assert lr.copy_off_once(watch, bundle, manifest, state) == 1  # ck settled
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # once only
    (watch / "samples" / "s.jpg").write_bytes(b"J")
    (watch / "notes.yaml").write_text("updated", encoding="utf-8")
    assert lr.copy_off_once(watch, bundle, manifest, state, final=True) == 2
    lines = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines()]
    assert [x["path"] for x in lines] == [
        "_latent_cache/x.safetensors",
        "notes.yaml",
        "job_000000020.safetensors",
        "notes.yaml",
        "samples/s.jpg",
    ]
    ck_line = next(x for x in lines if x["path"] == "job_000000020.safetensors")
    assert ck_line["sha256"] == hashlib.sha256(_st(b"A" * 20)).hexdigest() and ck_line["bytes"] == len(_st(b"A" * 20))
    assert ck_line["partial"] is False
    assert (bundle / "_latent_cache" / "x.safetensors").read_bytes() == _st(b"L")
    assert (bundle / "notes.yaml").read_text(encoding="utf-8") == "updated"
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


# --- real-run job, dataset manifest, batched archive, and download timeout ---------------------


def _write_synthetic_job(root: Path, *, name: str = "synthetic_style_v1", steps: int = 40) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    job_path = root / f"{name}.yaml"
    body = (
        "# Synthetic generic LoRA training job for kit tests\n"
        "job: extension\n"
        "config:\n"
        f"  name: {name}\n"
        "  process:\n"
        "  - type: sd_trainer\n"
        '    training_folder: "__LANE3_TRAINING_FOLDER__"\n'
        "    device: cuda:0\n"
        "    network:\n"
        "      type: lora\n"
        "      linear: 16\n"
        "      linear_alpha: 16\n"
        "    save:\n"
        "      dtype: float16\n"
        f"      save_every: {steps}\n"
        "      max_step_saves_to_keep: 4\n"
        "    datasets:\n"
        '    - folder_path: "__LANE3_DATASET_DIR__"\n'
        "      caption_ext: txt\n"
        "      caption_dropout_rate: 0.05\n"
        "      num_workers: 0\n"
        "      resolution:\n"
        "      - 512\n"
        "      - 768\n"
        "      - 1024\n"
        "    train:\n"
        "      batch_size: 1\n"
        "      cache_text_embeddings: true\n"
        f"      steps: {steps}\n"
        "      skip_first_sample: true\n"
        "      optimizer: adamw8bit\n"
        "      lr: 0.0001\n"
        "      dtype: bf16\n"
        "    model:\n"
        '      name_or_path: "__LANE3_MODEL_PATH__"\n'
        "      arch: qwen_image\n"
        "      quantize: false\n"
        "      quantize_te: false\n"
        "      low_vram: false\n"
        "    sample:\n"
        "      sampler: flowmatch\n"
        f"      sample_every: {steps}\n"
        "      width: 1024\n"
        "      height: 1024\n"
        "      prompts:\n"
        "      - synthetic studio still life, ceramic bowl on linen cloth\n"
        "      neg: ''\n"
        "      seed: 42\n"
        "      guidance_scale: 3\n"
        "      sample_steps: 20\n"
        "meta:\n"
        "  caption_dropout_source: ostris/ai-toolkit@beb94824 config/examples/train_lora_qwen_image_24gb.yaml:34\n"
        "  seconds_per_step: 3.0\n"
        "  checkpoint_size_bytes: 104857600\n"
        "  optimizer_size_bytes: 104857600\n"
        "  optimizer_size_source: 'estimate: synthetic test fixture, no training run behind it'\n"
        "  samples_and_logs_bytes: 16777216\n"
    )
    job_path.write_text(body, encoding="utf-8", newline="\n")
    return job_path, hashlib.sha256(job_path.read_bytes()).hexdigest()


def _write_synthetic_dataset(root: Path, n: int = 4) -> tuple[Path, Path, str]:
    ds_dir = root / "real_dataset_src"
    ds_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for idx in range(n):
        fname = f"studio_plate_{idx:02d}.png"
        payload = _png(100 + idx)
        (ds_dir / fname).write_bytes(payload)
        items.append({
            "image": fname,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "caption": f"synthetic studio plate {idx}, neutral daylight study",
        })
    manifest = root / "real-dataset-manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": "1.0", "items": items}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return ds_dir, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()


def _real_run_env(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    state_dir, env, _ = _rung_env(tmp_path)
    # Real-run path uses --dataset-manifest directly and keeps committed rung pins intact.
    env.pop("SDLAB_TEST_RUNG_DATASET_MANIFEST", None)
    env.pop("EXPECTED_RUNG_DATASET_SHA", None)
    return state_dir, env


def _launch_real(
    tmp_path: Path,
    env: dict[str, str],
    ds_dir: Path,
    *extra: str,
    out: str = "out_real",
    timeout_s: int = 240,
    omit_download_timeout: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    out_dir = tmp_path / out
    extra_list = list(extra)
    if (
        not omit_download_timeout
        and "--download-timeout-s" not in extra_list
        and "--download-floor-mb-s" not in extra_list
        and "COLAB_DOWNLOAD_TIMEOUT_S" not in env
    ):
        extra_list += ["--download-timeout-s", "420"]
    args = [
        _bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--shape", "high-mem",
        "--session", "sdlab-l3-real-run", "--out-dir", fc._to_posix(out_dir),
        "--dataset-dir", fc._to_posix(ds_dir), "--model", "Qwen/Qwen-Image",
        "--model-revision", REVISION, "--host-ram-required-gib", "96.5",
        "--download-max-seconds", "60", "--wall-s", "2900", "--cap", "6", "--max-rate", "9.5",
        *extra_list,
    ]
    res = subprocess.run(
        args, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout_s, check=False
    )
    return res, out_dir


def test_real_run_job_check_unit_and_placeholder_guards(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    job_path, job_sha = _write_synthetic_job(tmp_path)
    assert lr.main([
        "check-job", "--template", str(job_path), "--template-sha", job_sha, "--model-revision", REVISION
    ]) == 0
    assert "JOB_TEMPLATE_OK" in capsys.readouterr().out

    # Missing file
    assert lr.main([
        "check-job", "--template", str(tmp_path / "missing.yaml"), "--template-sha", job_sha,
        "--model-revision", REVISION,
    ]) == 1
    assert "REFUSED: JOB_FILE_MISSING:" in capsys.readouterr().err

    # Sha mismatch & malformed sha
    assert lr.main([
        "check-job", "--template", str(job_path), "--template-sha", "0" * 64, "--model-revision", REVISION
    ]) == 1
    assert "REFUSED: JOB_SHA_MISMATCH:" in capsys.readouterr().err
    assert lr.main([
        "check-job", "--template", str(job_path), "--template-sha", "not-a-sha", "--model-revision", REVISION
    ]) == 1
    assert "REFUSED: JOB_SHA_MISMATCH:" in capsys.readouterr().err

    # Unpinned model revision (branch name instead of 40-hex commit)
    assert lr.main([
        "check-job", "--template", str(job_path), "--template-sha", f"sha256:{job_sha}", "--model-revision", "main"
    ]) == 1
    assert "REFUSED: TRAIN_MODEL_REVISION_REQUIRED:" in capsys.readouterr().err

    # Placeholder missing, commented out, duplicated, or extra unpinned name_or_path
    base_text = job_path.read_text(encoding="utf-8")
    for idx, bad_text in enumerate([
        base_text.replace('"__LANE3_MODEL_PATH__"', '"Qwen/Qwen-Image"'),
        base_text.replace('    model:\n      name_or_path: "__LANE3_MODEL_PATH__"',
                          '    # name_or_path: "__LANE3_MODEL_PATH__"'),
        base_text + '\n# extra: "__LANE3_DATASET_DIR__"\n',
        base_text.replace('      arch: qwen_image', '      arch: qwen_image\n      te_name_or_path: "Qwen/Unpinned"'),
        base_text.replace('training_folder: "__LANE3_TRAINING_FOLDER__"',
                          'other_folder: "__LANE3_TRAINING_FOLDER__"'),
    ]):
        bad_p = tmp_path / f"bad_{idx}.yaml"
        bad_p.write_text(bad_text, encoding="utf-8", newline="\n")
        bad_sha = hashlib.sha256(bad_p.read_bytes()).hexdigest()
        assert lr.main([
            "check-job", "--template", str(bad_p), "--template-sha", bad_sha, "--model-revision", REVISION
        ]) == 1
        assert "REFUSED: JOB_TEMPLATE_INVALID:" in capsys.readouterr().err

    # render-job --template-sha guard on VM
    rendered = tmp_path / "rendered.yaml"
    assert lr.main([
        "render-job", "--template", str(job_path), "--template-sha", "f" * 64, "--out", str(rendered),
        "--training-folder", "/content/lane3_train", "--dataset-dir", "/content/lane3_dataset",
        "--model-path", f"/content/hf_home/snapshots/{REVISION}",
    ]) == 1
    assert "REFUSED: JOB_SHA_MISMATCH:" in capsys.readouterr().err
    assert lr.main([
        "render-job", "--template", str(job_path), "--template-sha", job_sha, "--out", str(rendered),
        "--training-folder", "/content/lane3_train", "--dataset-dir", "/content/lane3_dataset",
        "--model-path", f"/content/hf_home/snapshots/{REVISION}",
    ]) == 0
    capsys.readouterr()


def test_dataset_archive_pack_unpack_and_vm_integrity_refusals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ds_dir, manifest, m_sha = _write_synthetic_dataset(tmp_path, n=3)
    archive_p = tmp_path / "packed" / "lane3_dataset.tar"
    sha_out_p = tmp_path / "packed" / "dataset_archive_sha256.txt"

    # Rig-side verify + deterministic tar pack
    assert lr.main([
        "dataset", "--manifest", str(manifest), "--manifest-sha", m_sha,
        "--src", str(ds_dir), "--pack-archive", str(archive_p), "--archive-sha-out", str(sha_out_p),
    ]) == 0
    out_line = capsys.readouterr().out
    arch_sha = sha_out_p.read_text(encoding="utf-8").strip()
    assert len(arch_sha) == 64 and arch_sha == hashlib.sha256(archive_p.read_bytes()).hexdigest()
    assert f"archive_sha256={arch_sha}" in out_line

    # Missing manifest and manifest sha mismatch
    assert lr.main(["dataset", "--manifest", str(tmp_path / "nope.json"), "--src", str(ds_dir)]) == 1
    assert "REFUSED: DATASET_MANIFEST_MISSING:" in capsys.readouterr().err
    assert lr.main(["dataset", "--manifest", str(manifest), "--manifest-sha", "a" * 64, "--src", str(ds_dir)]) == 1
    assert "REFUSED: DATASET_MANIFEST_SHA_MISMATCH:" in capsys.readouterr().err

    # Malformed manifests (invalid JSON, traversal name, .txt image, duplicate stem, bad sha)
    for idx, payload in enumerate([
        "{not-json",
        json.dumps({"items": [{"image": "../escape.png", "sha256": "b" * 64, "caption": "x"}]}),
        json.dumps({"items": [{"image": "note.txt", "sha256": "b" * 64, "caption": "x"}]}),
        json.dumps({"items": [
            {"image": "dup.png", "sha256": "b" * 64, "caption": "x"},
            {"image": "dup.jpg", "sha256": "c" * 64, "caption": "y"},
        ]}),
        json.dumps({"items": [{"image": "ok.png", "sha256": "short", "caption": "x"}]}),
    ]):
        bad_m = tmp_path / f"bad_manifest_{idx}.json"
        bad_m.write_text(payload, encoding="utf-8")
        assert lr.main(["dataset", "--manifest", str(bad_m), "--src", str(ds_dir)]) == 1
        assert "REFUSED: DATASET_MANIFEST_INVALID:" in capsys.readouterr().err

    # VM-side archive sha mismatch
    corrupt_tar = tmp_path / "corrupt.tar"
    corrupt_tar.write_bytes(archive_p.read_bytes() + b"tamper")
    assert lr.main([
        "dataset", "--manifest", str(manifest), "--manifest-sha", m_sha,
        "--archive", str(corrupt_tar), "--archive-sha", arch_sha, "--dest", str(tmp_path / "vm_bad1"),
    ]) == 1
    assert "REFUSED: DATASET_ARCHIVE_SHA_MISMATCH:" in capsys.readouterr().err

    # VM-side per-item sha mismatch even when outer archive sha matches --archive-sha
    tampered_src = tmp_path / "tampered_src"
    shutil.copytree(ds_dir, tampered_src)
    (tampered_src / "studio_plate_01.png").write_bytes(b"\x89PNG\r\n\x1a\ncorrupted-plate")
    tampered_tar = tmp_path / "tampered_item.tar"
    items_raw = json.loads(manifest.read_text(encoding="utf-8"))["items"]
    tampered_tar_sha = lr.pack_dataset_archive(tampered_src, items_raw, tampered_tar)
    assert lr.main([
        "dataset", "--manifest", str(manifest), "--manifest-sha", m_sha,
        "--archive", str(tampered_tar), "--archive-sha", tampered_tar_sha, "--dest", str(tmp_path / "vm_bad2"),
    ]) == 1
    assert "REFUSED: DATASET_SHA_MISMATCH:" in capsys.readouterr().err

    # VM-side archive missing an expected item
    partial_tar = tmp_path / "partial_item.tar"
    partial_tar_sha = lr.pack_dataset_archive(ds_dir, items_raw[:2], partial_tar)
    assert lr.main([
        "dataset", "--manifest", str(manifest), "--manifest-sha", m_sha,
        "--archive", str(partial_tar), "--archive-sha", partial_tar_sha, "--dest", str(tmp_path / "vm_bad3"),
    ]) == 1
    assert "REFUSED: DATASET_FILE_MISSING:" in capsys.readouterr().err

    # VM-side clean unpack + per-item sha verify + caption write + --unlink-archive
    vm_dest = tmp_path / "vm_placed"
    assert lr.main([
        "dataset", "--manifest", str(manifest), "--manifest-sha", m_sha,
        "--archive", str(archive_p), "--archive-sha", arch_sha, "--dest", str(vm_dest), "--unlink-archive",
    ]) == 0
    assert not archive_p.exists()
    for idx in range(3):
        assert (vm_dest / f"studio_plate_{idx:02d}.png").read_bytes() == _png(100 + idx)
        assert (vm_dest / f"studio_plate_{idx:02d}.txt").read_text(encoding="utf-8") == (
            f"synthetic studio plate {idx}, neutral daylight study\n"
        )
    capsys.readouterr()



def test_in_process_check_job_plan_run_dataset_and_bundle_verification_branches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 1. YAML subset parser branches + check-job semantic refusals & --plan-out
    parsed_yaml = lr.parse_job_yaml(
        "job: extension # comment\n"
        "'quoted_key': 'it''s fine'\n"
        'escaped: "line \\"q\\""\n'
        "empty_val:\n"
        "null_val: ~\n"
        "bools: [true, false, 12, -3.5e2, []]\n"
        "inline_map: {a: 1, b: 'two'}\n"
        "empty_map: {}\n"
        "multiline_val: first part\n"
        "  second part\n"
        "seq:\n"
        "  -\n"
        "  - multi item\n"
        "    continued\n"
        "  - k1:\n"
        "      nested: ok\n"
        "    k2: 9\n"
    )
    assert parsed_yaml["quoted_key"] == "it's fine"
    assert parsed_yaml["inline_map"] == {"a": 1, "b": "two"}
    assert parsed_yaml["empty_map"] == {}
    assert parsed_yaml["multiline_val"] == "first part second part"
    assert parsed_yaml["seq"][0] is None
    assert parsed_yaml["seq"][1] == "multi item continued"
    assert parsed_yaml["seq"][2] == {"k1": {"nested": "ok"}, "k2": 9}

    for bad_yaml in (
        "# only comment\n",
        "\tjob: extension\n",
        "  \tjob: extension\n",
        "a: 1\n  b: 2\n",
        "not_a_kv_line\n",
        "- item1\n- item2\n",
    ):
        with pytest.raises(lr.Refusal) as y_exc:
            lr.parse_job_yaml(bad_yaml)
        assert y_exc.value.code == "JOB_TEMPLATE_INVALID"

    base_p, base_sha = _write_synthetic_job(tmp_path / "ip_job", steps=40)
    base_txt = base_p.read_text(encoding="utf-8")
    plan_out_p = tmp_path / "ip_job" / "job_plan.json"
    assert lr.main([
        "check-job",
        "--template", str(base_p),
        "--template-sha", base_sha,
        "--model-revision", REVISION,
        "--model-repo", "Qwen/Qwen-Image",
        "--plan-out", str(plan_out_p),
    ]) == 0
    assert json.loads(plan_out_p.read_text(encoding="utf-8"))["steps"] == 40

    assert lr.main(["check-job", "--template", str(tmp_path / "no_job.yaml")]) == 1
    assert lr.main(["check-job", "--template", str(base_p), "--template-sha", "0" * 64]) == 1
    assert lr.main(["check-job", "--template", str(base_p), "--model-revision", "not40hex"]) == 1
    assert lr.main(["check-job", "--template", str(base_p), "--model-repo", "untrusted/model"]) == 1

    def _check_mutated(label: str, mutated_txt: str, expected_code: str) -> None:
        assert mutated_txt != base_txt, label
        capsys.readouterr()
        p = tmp_path / "ip_job" / f"{label}.yaml"
        p.write_text(mutated_txt, encoding="utf-8", newline="\n")
        rc = lr.main(["check-job", "--template", str(p), "--model-revision", REVISION])
        err = capsys.readouterr().err
        assert rc == 1 and f"REFUSED: {expected_code}:" in err, (label, err)

    _check_mutated(
        "unpinned_url",
        base_txt + "  note: https://huggingface.co/Qwen/Qwen-Image/resolve/main/model.safetensors\n",
        "JOB_UNPINNED_HUB_REF",
    )
    _check_mutated(
        "unpinned_pipe",
        base_txt + f"  loras: Qwen/Qwen-Image@{REVISION}|Qwen/Qwen-Image\n",
        "JOB_UNPINNED_HUB_REF",
    )
    _check_mutated(
        "unpinned_spec",
        base_txt + "  extra_repo: Qwen/Qwen-Image\n",
        "JOB_UNPINNED_HUB_REF",
    )
    _check_mutated(
        "bad_licence_url",
        base_txt + f"  note: https://huggingface.co/other-org/bad-model/resolve/{REVISION}/w.safetensors\n",
        "JOB_MODEL_LICENCE_NOT_ALLOWED",
    )
    _check_mutated(
        "save_disabled",
        base_txt.replace("      dtype: float16\n", "      dtype: float16\n      disable_saving: true\n"),
        "JOB_SAVE_CADENCE_INVALID",
    )
    _check_mutated(
        "save_gt_steps",
        base_txt.replace("      save_every: 40\n", "      save_every: 80\n"),
        "JOB_SAVE_CADENCE_INVALID",
    )
    _check_mutated(
        "sample_disabled",
        base_txt.replace("      sample_every: 40\n", "      sample_every: 40\n      disable_sampling: true\n"),
        "JOB_SAMPLE_CADENCE_INVALID",
    )
    _check_mutated(
        "sample_gt_steps",
        base_txt.replace("      sample_every: 40\n", "      sample_every: 80\n"),
        "JOB_SAMPLE_CADENCE_INVALID",
    )
    _check_mutated(
        "sample_bad_steps",
        base_txt.replace("      sample_steps: 20\n", "      sample_steps: 0\n"),
        "JOB_SAMPLE_CADENCE_INVALID",
    )
    _check_mutated(
        "trigger_cached",
        base_txt.replace("    device: cuda:0\n", '    device: cuda:0\n    trigger_word: "tok"\n'),
        "JOB_TRIGGER_WITH_CACHED_EMBEDDINGS",
    )
    _check_mutated(
        "dropout_missing",
        base_txt.replace("      caption_dropout_rate: 0.05\n", ""),
        "JOB_CAPTION_DROPOUT_INVALID",
    )
    _check_mutated(
        "dropout_range",
        base_txt.replace("      caption_dropout_rate: 0.05\n", "      caption_dropout_rate: 1.5\n"),
        "JOB_CAPTION_DROPOUT_INVALID",
    )
    _check_mutated(
        "dropout_src_missing",
        base_txt.replace(
            "  caption_dropout_source: ostris/ai-toolkit@beb94824 config/examples/train_lora_qwen_image_24gb.yaml:34\n",
            "",
        ),
        "JOB_CAPTION_DROPOUT_INVALID",
    )

    # Positive hub URL + pipe check with cleared repo & 40-hex revision
    pinned_urls_p = tmp_path / "ip_job" / "pinned_urls.yaml"
    pinned_urls_p.write_text(
        base_txt
        + f"  ref_url: https://huggingface.co/Qwen/Qwen-Image/resolve/{REVISION}/transformer/config.json\n"
        + f"  ref_pipe: Qwen/Qwen-Image@{REVISION}|Qwen/Qwen2.5-VL-7B-Instruct@{REVISION}\n",
        encoding="utf-8",
        newline="\n",
    )
    assert lr.main(["check-job", "--template", str(pinned_urls_p), "--model-revision", REVISION]) == 0

    # 2. `plan-run` branches (missing download timeout, explicit < projected, rung wall vs real wall, disk refusals)
    arch_p = tmp_path / "ip_ds.tar"
    arch_p.write_bytes(b"x" * 4096)
    base_plan_args = [
        "plan-run",
        "--job-plan", str(plan_out_p),
        "--upload-timeout-s", "120",
        "--dataset-archive", str(arch_p),
        "--download-max-seconds", "60",
        "--setup-allowance-s", "900",
        "--wall-s", "3600",
        "--grace-s", "60",
        "--out", str(tmp_path / "ip_run_plan.json"),
    ]
    # Real job with no explicit download timeout and no floor -> DOWNLOAD_TIMEOUT_REQUIRED
    capsys.readouterr()
    assert lr.main([*base_plan_args, "--is-real-job", "1"]) == 1
    assert "DOWNLOAD_TIMEOUT_REQUIRED" in capsys.readouterr().err

    # Explicit download timeout below projected -> DOWNLOAD_TIMEOUT_TOO_SHORT
    assert lr.main([
        *base_plan_args,
        "--is-real-job", "1",
        "--explicit-download-timeout-s", "1",
        "--download-timeout-source", "cli",
        "--download-floor-mb-s", "1.0",
    ]) == 1
    assert "DOWNLOAD_TIMEOUT_TOO_SHORT" in capsys.readouterr().err

    # Explicit download timeout >= projected -> ok
    assert lr.main([
        *base_plan_args,
        "--is-real-job", "1",
        "--explicit-download-timeout-s", "600",
        "--download-timeout-source", "cli",
        "--download-floor-mb-s", "10.0",
    ]) == 0

    # Rung mode (`--is-real-job 0`) uses fixed 1800 s train allowance (60 + 900 + 1800 = 2760 s)
    capsys.readouterr()
    assert lr.main([
        "plan-run",
        "--job-plan", str(plan_out_p),
        "--is-real-job", "0",
        "--upload-timeout-s", "120",
        "--dataset-archive", str(arch_p),
        "--download-max-seconds", "60",
        "--setup-allowance-s", "900",
        "--wall-s", "1200",
        "--grace-s", "60",
    ]) == 1
    assert "must cover 2760 s" in capsys.readouterr().err

    # Invalid overhead < 1.0 -> TRAIN_OUTPUT_PROJECTION_REQUIRED; overflowing disk -> TRAIN_OUTPUT_DISK_LOW
    assert lr.main([
        *base_plan_args, "--is-real-job", "0", "--output-overhead-factor", "0.5"
    ]) == 1
    assert "TRAIN_OUTPUT_PROJECTION_REQUIRED" in capsys.readouterr().err

    assert lr.main([
        *base_plan_args, "--is-real-job", "0", "--checkpoint-size-bytes", str(40 * GIB)
    ]) == 1
    assert "TRAIN_OUTPUT_DISK_LOW" in capsys.readouterr().err

    # 3. `dataset` archive pack & unpack + error branches in-process
    ds_src, ds_man, ds_man_sha = _write_synthetic_dataset(tmp_path / "ip_ds", n=2)
    packed_tar = tmp_path / "ip_ds" / "packed.tar"
    packed_sha_f = tmp_path / "ip_ds" / "packed.sha256"
    assert lr.main([
        "dataset",
        "--manifest", str(ds_man),
        "--manifest-sha", ds_man_sha,
        "--src", str(ds_src),
        "--pack-archive", str(packed_tar),
        "--archive-sha-out", str(packed_sha_f),
    ]) == 0
    packed_sha = packed_sha_f.read_text(encoding="utf-8").strip()
    unpack_dst = tmp_path / "ip_ds" / "unpacked"
    assert lr.main([
        "dataset",
        "--manifest", str(ds_man),
        "--manifest-sha", ds_man_sha,
        "--archive", str(packed_tar),
        "--archive-sha", packed_sha,
        "--dest", str(unpack_dst),
        "--unlink-archive",
    ]) == 0
    assert not packed_tar.exists()
    assert (unpack_dst / "studio_plate_00.png").is_file() and (unpack_dst / "studio_plate_00.txt").is_file()
    assert lr.main(["dataset", "--manifest", str(ds_man), "--archive", str(tmp_path / "missing.tar"), "--dest", str(unpack_dst)]) == 1

    # 4. `write-train-manifest`, `check-output-disk`, `check-bundle-disk`, and `verify-bundle` branches in-process
    tf_dir = tmp_path / "ip_train_folder"
    (tf_dir / "sub").mkdir(parents=True)
    (tf_dir / "sub" / "loss.log").write_bytes(b"step=1 loss=0.4\n")
    tf_man_out = tmp_path / "ip_bundle_dir" / "training_folder_manifest.json"
    assert lr.main(["write-train-manifest", "--watch", str(tf_dir), "--out", str(tf_man_out)]) == 0

    cod_out = tmp_path / "cod.json"
    assert lr.main([
        "check-output-disk",
        "--training-folder", str(tmp_path / "nonexistent_child" / "train"),
        "--projected-bytes", "1024",
        "--out", str(cod_out),
    ]) == 0
    assert lr.main([
        "check-output-disk",
        "--training-folder", str(tf_dir),
        "--projected-bytes", "not-an-int",
        "--out", str(cod_out),
    ]) == 1
    assert lr.run_check_output_disk(
        lr.argparse.Namespace(training_folder=str(tf_dir), projected_bytes="5000", out=str(cod_out)),
        usage_fn=lambda _p: type("U", (), {"free": 100})(),
    ) == 1

    cbd_out = tmp_path / "cbd.json"
    bundle_dir = tmp_path / "ip_bundle_dir"
    (bundle_dir / "rung_outputs" / "sub").mkdir(parents=True)
    (bundle_dir / "rung_outputs" / "sub" / "loss.log").write_bytes(b"step=1 loss=0.4\n")
    assert lr.main(["check-bundle-disk", "--bundle-dir", str(bundle_dir), "--out", str(cbd_out)]) == 0
    assert lr.run_check_bundle_disk(
        lr.argparse.Namespace(bundle_dir=str(bundle_dir), out=str(cbd_out)),
        usage_fn=lambda _p: type("U", (), {"free": 1})(),
    ) == 1

    good_bundle_tar = tmp_path / "good_bundle.tar.gz"
    with tarfile.open(good_bundle_tar, "w:gz") as tf:
        tf.add(str(bundle_dir), arcname=".")
    vb_ok_json = tmp_path / "vb_ok.json"
    assert lr.main(["verify-bundle", "--bundle-tar", str(good_bundle_tar), "--out", str(vb_ok_json)]) == 0
    assert json.loads(vb_ok_json.read_text(encoding="utf-8")) == {"ok": True, "checked_files": 1, "total_bytes": 16}

    # Corrupted content with identical byte count -> sha256 mismatch in verify-bundle
    (bundle_dir / "rung_outputs" / "sub" / "loss.log").write_bytes(b"step=1 loss=9.9\n")
    sha_bad_tar = tmp_path / "sha_bad_bundle.tar.gz"
    with tarfile.open(sha_bad_tar, "w:gz") as tf:
        tf.add(str(bundle_dir), arcname=".")
    capsys.readouterr()
    assert lr.main(["verify-bundle", "--bundle-tar", str(sha_bad_tar)]) == 1
    assert "sha256 mismatch" in capsys.readouterr().err


