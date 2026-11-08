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
    env["SDLAB_TEST_RATE_READ_INTERVAL_S"] = "0.05"
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


def _launch(
    tmp_path: Path, env: dict[str, str], src: Path, *extra: str, out: str = "out", timeout_s: int = 240
) -> tuple[subprocess.CompletedProcess[str], Path]:
    out_dir = tmp_path / out
    args = [_bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--session", "sdlab-l3-gpu-rung",
            "--out-dir", fc._to_posix(out_dir), "--dataset-dir", fc._to_posix(src), "--model", "Qwen/Qwen-Image",
            "--model-revision", REVISION, "--host-ram-required-gib", "96.5", "--download-max-seconds", "60",
            "--wall-s", "2900", "--cap", "5", "--max-rate", "9.5", *extra]
    if "--shape" not in extra:
        args += ["--shape", "high-mem"]
    if "--rung-job" not in extra:
        args += ["--rung-job", "20"]
    res = subprocess.run(
        args, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout_s, check=False
    )
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
    expected_20_sha = hashlib.sha256((COLAB_DIR / "lane3" / "rung-qwen-image.yaml").read_bytes()).hexdigest()
    assert win["rung_job"] == "20" and win["rung_job_sha256"] == expected_20_sha
    # The machine shape: --shape high-mem reaches `colab new` as --high-mem and the row matches.
    calls = (out_dir.parent / "colab_state" / "calls.log").read_text(encoding="utf-8")
    assert "CALL new --gpu A100 --high-mem -s sdlab-l3-gpu-rung" in calls
    assert win["shape_requested"] == "high-mem" and win["shape_check"]["match"] is True
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
     ("--max-rate", "TRAIN_MAX_RATE_REQUIRED"), ("--rung-job", "RUNG_JOB_REQUIRED")],
)
def test_kit_refuses_a_rung_request_missing_a_value_before_any_colab_call(tmp_path: Path, drop: str, code: str) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    args = {"--model": "Qwen/Qwen-Image", "--model-revision": REVISION, "--host-ram-required-gib": "96.5",
            "--download-max-seconds": "60", "--dataset-dir": fc._to_posix(src), "--wall-s": "2900", "--cap": "5",
            "--max-rate": "9.5", "--rung-job": "20"}
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


def test_kit_refuses_invalid_rung_job_or_rung_job_without_train(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    res_bad, _ = _launch(tmp_path, env, src, "--rung-job", "100", out="out_bad_job")
    assert res_bad.returncode == 2 and "REFUSED: RUNG_JOB_REQUIRED:" in res_bad.stderr
    assert not (state_dir / "calls.log").exists()
    res_notrain = subprocess.run(
        [_bash(), fc._to_posix(LAUNCHER), "--out-dir", fc._to_posix(tmp_path / "out_notrain"), "--rung-job", "20"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )
    assert res_notrain.returncode == 2 and "REFUSED: TRAIN_OPTION_WITHOUT_TRAIN:" in res_notrain.stderr
    assert not (state_dir / "calls.log").exists()


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


def _no_uploads(state_dir: Path) -> bool:
    uploads = state_dir / "uploads.log"
    return not uploads.exists() or "UPLOAD_OK" not in uploads.read_text(encoding="utf-8")


def _win(out_dir: Path) -> dict:
    return json.loads((out_dir / "window.json").read_text(encoding="utf-8"))


def _cap_records(out_dir: Path) -> list[dict]:
    return [json.loads(ln)["cap"] for ln in (out_dir / "guards.log").read_text(encoding="utf-8").splitlines()
            if ln.startswith("{") and '"cap"' in ln and '"live"' in ln]


def test_gpu_window_with_no_post_open_rate_refuses_rate_unread(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_STR": "0.00/hr"})
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    win = _win(out_dir)
    assert win["refusal_code"] == "RATE_UNREAD" and win["rate_check"]["polls"] == 24
    # 24 open-time polls; the stop path's last usage read is recorded too.
    assert win["rate_check"]["window_rate"] is None and len(win["rate_readings"]) >= 24
    assert _no_uploads(state_dir) and "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("seq", ["0.50/hr", "2.15/hr,8.88/hr,2.16/hr,8.89/hr,2.15/hr,8.88/hr"])
def test_a_window_rate_below_the_floor_or_never_stable_is_unread(tmp_path: Path, seq: str) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    alternating = ",".join(seq.split(",") * 5)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_SEQ": alternating})
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0 and _win(out_dir)["refusal_code"] == "RATE_UNREAD" and _no_uploads(state_dir)


def test_parallel_neighbour_reproducer_refuses_above_max(tmp_path: Path) -> None:
    # The reviewer's case: a neighbour already bills 0.26/h, this window reads 0.26 then 9.14.
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.26/hr", "FAKE_COLAB_POST_OPEN_RATE_SEQ": "0.26/hr,9.14/hr"})
    res, out_dir = _launch(tmp_path, env, src, "--max-rate", "8.0")
    assert res.returncode != 0
    win = _win(out_dir)
    assert win["refusal_code"] == "RATE_ABOVE_MAX" and _no_uploads(state_dir)
    assert win["rate_check"]["window_rate"] == 8.88 and win["rate_check"]["account_rate"] == 9.14
    assert win["rate_check"]["pre_open_rate"] == 0.26 and win["rate_check"]["polls"] == 3
    assert [r["account_rate"] for r in win["rate_readings"][:3]] == [0.26, 9.14, 9.14]


def test_rate_waits_for_stability_and_prices_at_the_max(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_SEQ": "4.00/hr,8.88/hr"})
    res, out_dir = _launch(tmp_path, env, src, "--max-rate", "9.5")
    assert res.returncode == 0, res.stderr
    win = _win(out_dir)
    assert win["status"] == "ok" and win["trained"] is True
    assert win["rate_check"]["window_rate"] == 8.88 and win["rate_check"]["polls"] == 3
    assert win["rate_check"]["priced_at"] == 9.5 and win["rate_used_for_cap_and_projection"] == 9.5
    assert win["rate_source"] == "max_of_max_rate_and_stable_window"
    assert [r["stable"] for r in win["rate_readings"][:3]] == [False, False, True]


def test_a_low_window_rate_is_priced_at_max_rate_so_the_cap_trips_on_time(tmp_path: Path) -> None:
    # A stable 2.15/h reading must not stretch the cap: priced at max(9.5, 2.15) = 9.5, 0.05 units
    # last 18.9 s (at 2.15/h they would last 84 s). With cleanup_bound_s = 1290 s at 9.5/h,
    # cleanup_reserve = (1290 / 3600) * 9.5 = 3.404167 units, so cap 3.464167 minus margin 0.01
    # minus reserve 3.404167 leaves effective_trip = 0.05 units (~18.95 s).
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr", "FAKE_COLAB_POST_OPEN_RATE_STR": "2.15/hr",
                "FAKE_VM_TRAIN": "hang_after_save", "GUARD_POLL_INTERVAL_S": "0.5"})
    res, out_dir = _launch(tmp_path, env, src, "--cap", "3.464167", "--margin", "0.01")
    content = state_dir / "content"
    try:
        assert res.returncode != 0
        # Wall-clock seconds from the cap clock's start to the trip, read off the wall record.
        lines = [json.loads(ln) for ln in (out_dir / "guards.log").read_text(encoding="utf-8").splitlines()
                 if ln.startswith("{") and '"cap"' in ln and '"live"' in ln]
        tripped = [r for r in lines if r["cap"]["tripped"]]
        assert tripped, "the cap never tripped"
        elapsed = tripped[0]["wall"]["threshold_s"] - tripped[0]["wall"]["remaining_s"]
        assert 18.9 <= elapsed <= 30, elapsed
        assert _win(out_dir)["rate_check"]["window_rate"] == 2.15
    finally:
        for pid in _rung_processes(content):
            os.kill(pid, 9)


@pytest.mark.parametrize("rise", ["9.80", "12.00"])
def test_a_midrun_rise_above_max_rate_refuses_and_bundles(tmp_path: Path, rise: str) -> None:
    # Our own rise, the assignment count unchanged (the fake's default 1): it trips the max.
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                "FAKE_COLAB_POST_OPEN_RATE_SEQ": f"8.88/hr,8.88/hr,8.88/hr,8.88/hr,{rise}/hr",
                "FAKE_VM_TRAIN": "hang_after_save", "GUARD_POLL_INTERVAL_S": "0.5"})
    res, out_dir = _launch(tmp_path, env, src, "--max-rate", "9.5")
    content = state_dir / "content"
    try:
        assert res.returncode != 0
        win = _win(out_dir)
        assert win["refusal_code"] == "RATE_ABOVE_MAX"
        assert "mid-run" in (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "BUNDLE_AFTER_FAILURE: downloaded" in (out_dir / "guards.log").read_text(encoding="utf-8")
        assert max(r["window_rate"] or 0 for r in win["rate_readings"]) == float(rise)
    finally:
        for pid in _rung_processes(content):
            os.kill(pid, 9)


def test_cap_clock_starts_at_open_success_and_counts_the_rate_polls(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({"FAKE_COLAB_NEW_DELAY_S": "3", "SDLAB_TEST_RATE_READ_INTERVAL_S": "1",
                "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
                "FAKE_COLAB_POST_OPEN_RATE_SEQ": "0.00/hr,0.00/hr,8.88/hr,8.88/hr",
                "FAKE_VM_TRAIN": "hang_after_save", "GUARD_POLL_INTERVAL_S": "0.5"})
    res, out_dir = _launch(tmp_path, env, src, "--cap", "3.464167", "--margin", "0.01")
    content = state_dir / "content"
    try:
        win = _win(out_dir)
        new_done = float((state_dir / "new_done_epoch.txt").read_text(encoding="utf-8"))
        import datetime as _dt

        started = _dt.datetime.strptime(win["cap_clock_started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc).timestamp()
        opened = _dt.datetime.strptime(win["opened_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
        # The clock starts when `colab new` returns (after its 3 s), not when the kit started.
        assert started >= int(new_done) and started - opened >= 3
        # The 3 rate polls (1 s apart) after open are counted: the first live cap reading already
        # holds at least their time, priced at 9.5/h.
        first = _cap_records(out_dir)[0]
        assert first["spend_ccu"] / 9.5 * 3600 >= 2.0
    finally:
        for pid in _rung_processes(content):
            os.kill(pid, 9)


def _fold(st: dict, rates, *, pre, counts=None, start=0.0, step=5.0) -> dict:
    import launch_guards as lg

    for k, r in enumerate(rates):
        lg.update_window_rate(st, account_rate=r, pre_open_rate=pre, at="t", epoch=start + k * step,
                              assignments=1 if counts is None else counts[k])
    return st


def test_window_rate_state_unit() -> None:
    import launch_guards as lg

    st = _fold({}, (0.26, 9.14, 9.14), pre=0.26)
    assert st["best_stable"] == 8.88 and [x["stable"] for x in st["readings"]] == [False, False, True]
    assert lg.window_rate_decision(st, 8.0) == "above_max" and lg.window_rate_decision(st, 9.5) == "ok"
    assert lg.gpu_projection_rate(st, 9.5) == 9.5 and lg.gpu_projection_rate(st, 8.0) == 8.88
    low = _fold({}, (0.5, 0.5, 0.5), pre=None)
    assert lg.window_rate_decision(low, 9.5) == "unread" and lg.gpu_projection_rate(low, 9.5) == 9.5
    gone = _fold({}, (None,), pre=0.0)
    assert gone["readings"][0]["window_rate"] is None and lg.GPU_RATE_FLOOR == 1.0
    assert lg.parse_active_assignments("Current balance: 1 compute units\nActive assignments: 2\n") == 2
    assert lg.parse_active_assignments("Usage rate: 1/hr") is None


def test_the_stability_pair_is_five_seconds_apart() -> None:
    import launch_guards as lg

    assert lg.RATE_STABLE_GAP_S == 5.0
    # Mid-run cycles poll every 2 s: a read 2 s after the last counted one is recorded, uncounted.
    st = _fold({}, (8.88, 8.88), pre=0.0, step=2.0)
    assert [r["counted"] for r in st["readings"]] == [True, False] and st.get("best_stable") is None
    st = _fold(st, (8.88,), pre=0.0, start=5.0)
    assert st["readings"][-1]["stable"] is True and st["best_stable"] == 8.88


def test_a_count_change_rebaselines_the_neighbour_once_it_settles() -> None:
    import launch_guards as lg

    # A neighbour opens mid-run: 8.88 -> 17.76 with the count 1 -> 2. Two agreeing reads at the new
    # count settle it; neither is judged; then the window reads 8.88 again.
    st = _fold({}, (8.88, 8.88, 17.76, 17.76, 17.76, 17.76), pre=0.0, counts=(1, 1, 2, 2, 2, 2))
    r = st["readings"]
    assert r[2]["rebaseline_pending"] is True and r[2]["window_rate"] is None
    assert r[3]["rebaselined"] is True and r[3]["neighbour_baseline"] == 8.88
    assert [x["window_rate"] for x in r[4:]] == [8.88, 8.88]
    assert st["best_stable"] == 8.88 and lg.gpu_projection_rate(st, 9.5) == 9.5
    assert lg.window_rate_decision(st, 9.5) == "ok"
    # A neighbour closes: pre-open 8.88, then 17.76 at count 2, then 8.88 at count 1; afterwards our
    # own rise to 12.00 (count unchanged) is seen at full size and trips 9.5.
    st = _fold({}, (17.76, 17.76, 8.88, 8.88, 8.88, 12.0, 12.0), pre=8.88, counts=(2, 2, 1, 1, 1, 1, 1))
    assert st["readings"][3]["rebaselined"] is True and st["readings"][3]["neighbour_baseline"] == 0.0
    assert [x["window_rate"] for x in st["readings"]] == [8.88, 8.88, None, 8.88, 8.88, 12.0, 12.0]
    assert st["best_stable"] == 12.0 and lg.window_rate_decision(st, 9.5) == "above_max"


def test_the_count_leading_the_rate_by_one_read_does_not_trip() -> None:
    import launch_guards as lg

    # The count reads 2 one read before the neighbour's rate arrives: 8.88 (count 2), then 17.76.
    st = _fold({}, (8.88, 8.88, 8.88, 17.76, 17.76, 17.76, 17.76), pre=0.0, counts=(1, 1, 2, 2, 2, 2, 2))
    assert lg.window_rate_decision(st, 9.5) == "ok" and st["best_stable"] == 8.88
    reb = [x for x in st["readings"] if x.get("rebaselined")]
    assert len(reb) == 1 and reb[0]["neighbour_baseline"] == 8.88
    assert max(x["window_rate"] or 0 for x in st["readings"]) == 8.88


def test_the_reviewers_sequence_a_neighbour_closing_with_the_rate_two_reads_ahead_then_our_rise_trips() -> None:
    import launch_guards as lg

    # rdlab re-reads review: pre-open 8.88 (a neighbour), our 8.88 at count 2; the neighbour closes and
    # its rate drop leads the count by 2 reads (0.00 own, twice, at the unchanged count); the count
    # settles at 1; then our own rise to 12.00 must trip --max-rate 9.5.
    st = _fold({}, (17.76, 17.76, 8.88, 8.88, 8.88, 8.88, 12.0, 12.0),
               pre=8.88, counts=(2, 2, 2, 2, 1, 1, 1, 1))
    r = st["readings"]
    assert r[3]["below_floor"] is True and r[3]["stable"] is False
    reb = [x for x in r if x.get("rebaselined")]
    assert len(reb) == 1 and reb[0]["neighbour_baseline"] == 0.0
    assert st["best_stable"] == 12.0 and lg.window_rate_decision(st, 9.5) == "above_max"


def test_the_rebaseline_uses_the_highest_stable_rate_seen() -> None:
    import launch_guards as lg

    # A T4 neighbour (1.07) closes; its drop leads the count by 2, so our stable read at the old
    # count is 7.81 (above the floor), not our real 8.88. Re-baselining on that last stable read
    # left a 1.07 neighbour that is gone, and our rise to 10.50 read 9.43 under --max-rate 9.5.
    # On the highest stable rate seen (8.88) the baseline is 0.00 and the rise trips.
    st = _fold({}, (9.95, 9.95, 8.88, 8.88, 8.88, 8.88, 10.5, 10.5),
               pre=1.07, counts=(2, 2, 2, 2, 1, 1, 1, 1))
    r = st["readings"]
    assert r[3]["stable"] is True and r[3]["window_rate"] == 7.81
    reb = [x for x in r if x.get("rebaselined")]
    assert len(reb) == 1 and reb[0]["neighbour_baseline"] == 0.0 and reb[0]["window_rate"] == 8.88
    assert [x["window_rate"] for x in r[-2:]] == [10.5, 10.5]
    assert lg.window_rate_decision(st, 9.5) == "above_max"


def test_a_stable_mid_run_rate_below_the_floor_is_a_bad_read() -> None:
    import launch_guards as lg

    # After our first stable 8.88, the account drops to 0.50 at an unchanged count: the stable pair
    # below the floor is recorded below_floor and counts as bad; three in a row end the window.
    one = _fold({}, (8.88, 8.88, 0.5, 0.5, 8.88), pre=0.0)
    r = one["readings"]
    assert r[2].get("below_floor") is None and r[3]["below_floor"] is True and r[3]["stable"] is False
    assert one["best_stable"] == 8.88 and not one.get("assignments_unreadable")
    assert one["assignments_bad_streak"] == 0 and lg.window_rate_decision(one, 9.5) == "ok"
    three = _fold({}, (8.88, 8.88, 0.5, 0.5, 0.5, 0.5), pre=0.0)
    assert [x.get("below_floor", False) for x in three["readings"]] == [False, False, False, True, True, True]
    assert lg.window_rate_decision(three, 9.5) == "assignments_unreadable"
    # Before the first stable read a sub-floor rate stays "unread" (the RATE_UNREAD budget), not bad.
    low = _fold({}, (0.5, 0.5, 0.5, 0.5), pre=0.0)
    assert not any(x.get("below_floor") for x in low["readings"]) and lg.window_rate_decision(low, 9.5) == "unread"


@pytest.mark.parametrize("bad", [None, 0])
def test_a_bad_count_for_three_reads_is_unreadable_and_one_is_recorded_only(bad) -> None:
    import launch_guards as lg

    one = _fold({}, (8.88, 8.88, 8.88, 8.88), pre=0.0, counts=(1, 1, bad, 1))
    assert one["readings"][2]["assignments_bad"] is True
    assert lg.window_rate_decision(one, 9.5) == "ok" and not one.get("assignments_unreadable")
    three = _fold({}, (8.88, 8.88, 8.88, 8.88, 8.88), pre=0.0, counts=(1, 1, bad, bad, bad))
    assert lg.window_rate_decision(three, 9.5) == "assignments_unreadable"
    assert lg.parse_active_assignments("Current balance: 1 compute units\nUsage rate: 8.88/hr\n") is None


def test_no_count_before_the_first_stable_read_is_not_registered_yet() -> None:
    import launch_guards as lg

    # The receipt shape: 0.00 with 0 assignments until the session registers, then the rate.
    st = _fold({}, (0.0, 0.0, 0.0, 8.88, 8.88), pre=0.0, counts=(0, 0, None, 1, 1))
    assert [r.get("not_registered", False) for r in st["readings"]] == [True, True, True, False, False]
    assert not st.get("assignments_unreadable") and lg.window_rate_decision(st, 9.5) == "ok"
    never = _fold({}, (0.0,) * 24, pre=0.0, counts=(0,) * 24)
    assert lg.window_rate_decision(never, 9.5) == "unread"


def _rate_env(env: dict, seq: str, counts: str, pre: str = "0.00/hr") -> None:
    env.update({"FAKE_COLAB_PRE_OPEN_RATE_STR": pre, "FAKE_COLAB_POST_OPEN_RATE_SEQ": seq,
                "FAKE_COLAB_ASSIGNMENTS_SEQ": counts, "FAKE_VM_TRAIN_SLEEP_S": "4",
                "GUARD_POLL_INTERVAL_S": "0.3"})


def test_a_neighbour_opening_midrun_rebaselines_and_our_window_runs_on(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    _rate_env(env, "8.88/hr,8.88/hr,8.88/hr,8.88/hr,17.76/hr", "1,1,1,1,2")
    res, out_dir = _launch(tmp_path, env, src, "--max-rate", "9.5")
    assert res.returncode == 0, res.stderr[-3000:]
    win = _win(out_dir)
    assert win["status"] == "ok" and win["refusal_code"] is None
    reb = [r for r in win["rate_readings"] if r.get("rebaselined")]
    assert reb and reb[0]["assignments_before"] == 1 and reb[0]["assignments"] == 2
    assert any(r.get("rebaseline_pending") for r in win["rate_readings"])
    assert reb[0]["neighbour_baseline"] == 8.88
    assert all((r["window_rate"] or 0) <= 8.88 for r in win["rate_readings"])
    assert win["rate_used_for_cap_and_projection"] == 9.5


def test_a_neighbour_closing_midrun_is_not_an_under_read(tmp_path: Path) -> None:
    _, env, src = _rung_env(tmp_path)
    _rate_env(env, "17.76/hr,17.76/hr,17.76/hr,17.76/hr,8.88/hr", "2,2,2,2,1", pre="8.88/hr")
    res, out_dir = _launch(tmp_path, env, src, "--max-rate", "9.5")
    assert res.returncode == 0, res.stderr[-3000:]
    readings = _win(out_dir)["rate_readings"]
    after = [r for r in readings if r["counted"] and r.get("assignments") == 1 and not r.get("rebaseline_pending")]
    assert after and all(r["window_rate"] == 8.88 for r in after), after
    assert any(r.get("rebaselined") and r["neighbour_baseline"] == 0.0 for r in readings)


USAGE_0 = "Current balance: 1812.22 compute units\nUsage rate: 0.00/hr\nActive assignments: 1\n"


def test_gpu_rate_selection_raises_rate_unread_without_a_live_rate() -> None:
    import launch_guards as lg

    for text in (USAGE_0, "Current balance: 1812.22 compute units\nActive assignments: 1\n"):
        with pytest.raises(lg.RateUnread) as exc:
            lg.parse_usage_text(text, "gpu", configured_rate=0.26, session_opened=True, pre_open_rate=0.0)
        assert exc.value.code == "RATE_UNREAD" and exc.value.partial["balance"] == 1812.22
    # Before the open there is no post-open rate either: still the raise, never a configured rate.
    with pytest.raises(lg.RateUnread):
        lg.parse_usage_text(USAGE_0, "gpu", configured_rate=0.26, session_opened=False)
    # A failed usage read stays COLAB_USAGE_PARSE_FAILED, and carries no projection rate at all.
    bad = lg.parse_usage_text("garbage", "gpu", configured_rate=0.26, session_opened=True)
    assert bad["code"] == "COLAB_USAGE_PARSE_FAILED" and bad["rate_for_projection"] is None
    assert bad["rate_source"] == "live_rate_unread"
    with pytest.raises(ValueError):
        lg.parse_usage_text(USAGE_0, "tpu")


def test_gpu_rate_selection_uses_the_live_8_88_and_keeps_it() -> None:
    import launch_guards as lg

    live = lg.parse_usage_text(USAGE_0.replace("0.00/hr", "8.88/hr"), "gpu", configured_rate=0.26,
                               session_opened=True, pre_open_rate=0.0)
    assert live["rate_for_projection"] == 8.88 and live["rate_source"] == "post_open_measured"
    # A later 0.00 reading keeps the last good live rate.
    later = lg.parse_usage_text(USAGE_0, "gpu", configured_rate=0.26, session_opened=True, pre_open_rate=0.0,
                                post_open_rate=8.88)
    assert later["rate_for_projection"] == 8.88 and later["rate_source"] == "post_open_measured"


def test_cpu_rate_selection_is_unchanged() -> None:
    import launch_guards as lg

    pending = lg.parse_usage_text(USAGE_0, "cpu", configured_rate=0.26, session_opened=True, pre_open_rate=0.0)
    assert pending["rate_for_projection"] == 0.26 and pending["rate_source"] == "configured_pending_post_open_rate"
    pre = lg.parse_usage_text(USAGE_0.replace("0.00/hr", "0.08/hr"), "cpu", configured_rate=0.26, session_opened=False)
    assert pre["rate_for_projection"] == 0.26 and pre["rate_source"] == "max_of_pre_open_and_configured"
    none = lg.parse_usage_text("Current balance: 1.0 compute units\n", "cpu", configured_rate=0.26, session_opened=False)
    assert none["rate_for_projection"] == 0.26 and none["rate_source"] == "configured"


def test_cap_at_8_88_per_hour_trips_at_20_3_seconds() -> None:
    import launch_guards as lg

    kw = dict(mode="live", cap=0.06, margin=0.01, start_balance=100.0, current_balance=100.0, rate_ccu_per_hour=8.88)
    assert lg.evaluate_cap_guard(elapsed_s=20.0, **kw)["tripped"] is False
    assert lg.evaluate_cap_guard(elapsed_s=20.3, **kw)["tripped"] is True
    # The balance drop counts too: the larger of the drop and the projection is the spend.
    assert lg.evaluate_cap_guard(elapsed_s=0.0, **{**kw, "current_balance": 99.94})["tripped"] is True


# The machine shape gate (colab_window.sh) on lane 3: required for the GPU rung, checked after open.

def test_rung_without_shape_refuses_before_any_colab_call(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    out_dir = tmp_path / "out"
    args = [_bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--session", "sdlab-l3-gpu-rung",
            "--out-dir", fc._to_posix(out_dir), "--dataset-dir", fc._to_posix(src), "--model", "Qwen/Qwen-Image",
            "--model-revision", REVISION, "--host-ram-required-gib", "96.5", "--download-max-seconds", "60",
            "--wall-s", "2900", "--cap", "5", "--max-rate", "9.5", "--rung-job", "20"]
    res = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=240, check=False)
    assert res.returncode == 2 and "REFUSED: SHAPE_REQUIRED:" in res.stderr, res.stderr[-2000:]
    assert not (state_dir / "calls.log").exists() and not (state_dir / "card.txt").exists()
    assert json.loads((out_dir / "window.json").read_text(encoding="utf-8"))["refusal_code"] == "SHAPE_REQUIRED"


def test_rung_shape_mismatch_refuses_after_open_and_stops(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env["FAKE_COLAB_SESSION_SHAPE"] = "High-RAM"
    res, out_dir = _launch(tmp_path, env, src, "--shape", "standard")
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "SHAPE_MISMATCH" and win["shape_requested"] == "standard"
    assert win["shape_check"] == {"requested": "standard", "expected": "Standard", "observed": "High-RAM",
                                  "match": False}
    assert "CALL new --gpu A100 -s sdlab-l3-gpu-rung" in (state_dir / "calls.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")
    assert _no_uploads(state_dir)


def _assert_r500_stopped_bundle_keeps_step_250_and_marks_step_500_partial(
    out_dir: Path, state_dir: Path, expected_refusal: str
) -> None:
    expected_500_sha = hashlib.sha256((COLAB_DIR / "lane3" / "rung-qwen-image-500.yaml").read_bytes()).hexdigest()
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == expected_refusal and win["refusal_code"] == expected_refusal
    assert win["train"] is None and win["trained"] is False and win["lane3_mode"] == "train"
    assert win["rung_job"] == "500" and win["rung_job_sha256"] == expected_500_sha
    assert win.get("checkpoint_path") is None
    expected_samples = [f"rustline_style_v5/samples/1762400000000__000000250_{i}.jpg" for i in range(6)]
    assert win["rung_outputs"]["checkpoints"] == ["rustline_style_v5/rustline_style_v5_000000250.safetensors"]
    assert win["rung_outputs"]["partial_checkpoints"] == ["rustline_style_v5/rustline_style_v5_000000500.safetensors"]
    assert win["rung_outputs"]["samples"] == expected_samples

    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert f"REFUSED: {expected_refusal}" in guards
    assert "BUNDLE_AFTER_FAILURE: downloaded" in guards, guards[-2000:]
    assert "RESTART -s sdlab-l3-gpu-rung" in (state_dir / "restarts.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")

    members = _bundle(out_dir)
    job = members["rung_job.yaml"].decode()
    assert "steps: 500" in job and "save_every: 250" in job and "sample_every: 250" in job
    ck_250 = members["rung_outputs/rustline_style_v5/rustline_style_v5_000000250.safetensors"]
    assert b"FAKE-LORA-STEP-250" in ck_250
    for s in expected_samples:
        assert f"rung_outputs/{s}" in members
        assert members[f"rung_outputs/{s}"].startswith(b"\xff\xd8FAKEJPEG")

    manifest_rows = [json.loads(x) for x in members["rung_outputs/manifest.jsonl"].decode().splitlines() if x.strip()]
    by_path = {r["path"]: r for r in manifest_rows}
    assert by_path["rustline_style_v5/rustline_style_v5_000000250.safetensors"]["partial"] is False
    assert by_path["rustline_style_v5/rustline_style_v5_000000250.safetensors"]["sha256"] == hashlib.sha256(ck_250).hexdigest()
    assert by_path["rustline_style_v5/rustline_style_v5_000000500.safetensors"]["partial"] is True
    for s in expected_samples:
        assert by_path[s]["sha256"] == hashlib.sha256(members[f"rung_outputs/{s}"]).hexdigest()

    vm_win = json.loads(members["vm_window.json"])
    assert vm_win["train"] == "failed" and vm_win["lane3_mode"] == "train"
    _assert_token_nowhere(out_dir)


def test_rung_500_stopped_by_cap_guard_keeps_step_250_and_marks_step_500_partial(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({
        "FAKE_VM_TRAIN": "hang_after_step_250",
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "8.88/hr",
        "GUARD_POLL_INTERVAL_S": "0.5",
    })
    # Priced at max(9.5, 8.88) = 9.5/h with cleanup_bound_s = 1290 s -> cleanup_reserve = (1290 / 3600) * 9.5 = 3.404167 units.
    # Adding 3.404167 to the old 0.03 cap gives cap = 3.434167 (effective_trip = 3.434167 - 0.01 - 3.404167 = 0.02 units,
    # ~7.58 s at 9.5/h): gives the VM time to download, write step 250 + 6 samples + half-written step 500, and hang
    # before the cap guard trips.
    res, out_dir = _launch(tmp_path, env, src, "--rung-job", "500", "--cap", "3.434167", "--margin", "0.01")
    content = state_dir / "content"
    try:
        assert res.returncode != 0
        _assert_r500_stopped_bundle_keeps_step_250_and_marks_step_500_partial(out_dir, state_dir, "CAP_GUARD_TRIPPED")
        assert _rung_processes(content) == []
    finally:
        for pid in _rung_processes(content):
            os.kill(pid, 9)


def test_rung_500_stopped_by_wall_guard_keeps_step_250_and_marks_step_500_partial(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({
        "FAKE_VM_TRAIN": "hang_after_step_250",
        "SDLAB_TEST_INSTALL_ALLOWANCE_S": "1",
        "SDLAB_TEST_TRAIN_ALLOWANCE_S": "1",
        "GUARD_POLL_INTERVAL_S": "0.5",
    })
    # wall 10s - grace 2s = 8s wall limit (>= download 5 + install 1 + train 1 = 7s): the independent wall
    # watcher fires after 8s while the VM hangs after step 250.
    res, out_dir = _launch(
        tmp_path, env, src, "--rung-job", "500", "--download-max-seconds", "5", "--wall-s", "10", "--grace-s", "2"
    )
    content = state_dir / "content"
    try:
        assert res.returncode != 0
        _assert_r500_stopped_bundle_keeps_step_250_and_marks_step_500_partial(out_dir, state_dir, "WALL_GUARD_TRIPPED")
        assert _rung_processes(content) == []
    finally:
        for pid in _rung_processes(content):
            os.kill(pid, 9)


def _kill_hung_test_pids(state_dir: Path) -> None:
    content = state_dir / "content"
    for pid in _rung_processes(content):
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    hung_f = state_dir / "hung_pids.txt"
    if hung_f.is_file():
        for line in hung_f.read_text(encoding="utf-8").splitlines():
            if line.strip().isdigit():
                try:
                    os.kill(int(line.strip()), 9)
                except OSError:
                    pass


def _assert_children_had_default_signals(state_dir: Path, *subcmds: str) -> None:
    sig_f = state_dir / "child_signals.jsonl"
    assert sig_f.is_file(), "child_signals.jsonl missing"
    rows = [json.loads(x) for x in sig_f.read_text(encoding="utf-8").splitlines() if x.strip()]
    seen = {r["subcmd"] for r in rows}
    for subcmd in subcmds:
        assert subcmd in seen, (subcmd, seen)
    # In cleanup/salvage (from restart-kernel onwards, plus download/stop), commands run synchronously
    # in a subshell with `trap - TERM INT`, so both SIGTERM and SIGINT are SIG_DFL. (The main run's
    # `colab exec ... &` is backgrounded with `&`, which in POSIX non-interactive shells sets SIGINT
    # to SIG_IGN while keeping SIGTERM as SIG_DFL.)
    in_cleanup = False
    for r in rows:
        if r["subcmd"] in ("restart-kernel", "download", "stop"):
            in_cleanup = True
        if r["subcmd"] in subcmds:
            assert r["sigterm_ign"] is False, r
            if in_cleanup or r["subcmd"] != "exec":
                assert r["sigint_ign"] is False, r


def test_window_json_records_cleanup_bounds_equal_to_configured_sum(tmp_path: Path) -> None:
    # Default configured sum for lane 3 (train), measured from the trip:
    # in-flight (300 + 10 = 310 s) + restart (180 + 10) + bundle-now exec (330 + 10) + download (300 + 10) = 1150 s;
    # plus 2 stop attempts (2 * (60 + 10) = 140 s) -> cleanup_bound_s = 1290 s.
    _, env3, src = _rung_env(tmp_path / "l3_def")
    res3, out3 = _launch(tmp_path / "l3_def", env3, src)
    assert res3.returncode == 0, res3.stderr
    win3 = json.loads((out3 / "window.json").read_text(encoding="utf-8"))
    assert win3["cleanup_stop_attempted_by_s"] == (300 + 10) + (180 + 10) + (330 + 10) + (300 + 10) == 1150
    assert win3["cleanup_bound_s"] == 1150 + 2 * (60 + 10) == 1290

    # Default configured sum for lane 1 (render), measured from the trip:
    # in-flight (300 + 10 = 310 s) + 0 salvage -> cleanup_stop_attempted_by_s = 310 s;
    # plus 2 stop attempts (2 * (60 + 10) = 140 s) -> cleanup_bound_s = 450 s.
    _, _, env1 = fc.make_fake_colab_env(tmp_path / "l1_def")
    env1["GUARD_POLL_INTERVAL_S"] = "0.2"
    out1 = tmp_path / "l1_def" / "out"
    lane1_sh = COLAB_DIR / "launch_lane1_stub.sh"
    res1 = subprocess.run(
        [_bash(), fc._to_posix(lane1_sh), "--out-dir", fc._to_posix(out1), "--session", "sdlab-l1-bounds"],
        env=env1, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )
    assert res1.returncode == 0, res1.stderr
    win1 = json.loads((out1 / "window.json").read_text(encoding="utf-8"))
    assert win1["cleanup_stop_attempted_by_s"] == 300 + 10 == 310
    assert win1["cleanup_bound_s"] == 310 + 2 * (60 + 10) == 450

    # Custom configured sums in test mode reflect the overridden step timeouts and deadline.
    _, env3_custom, src_custom = _rung_env(tmp_path / "l3_custom")
    env3_custom.update({
        "SDLAB_TEST_KILL_GRACE_S": "2",
        "SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S": "10",
        "SDLAB_TEST_SALVAGE_EXEC_TIMEOUT_S": "20",
        "SDLAB_TEST_DOWNLOAD_TIMEOUT_S": "15",
        "SDLAB_TEST_STOP_TIMEOUT_S": "8",
    })
    res3_c, out3_c = _launch(tmp_path / "l3_custom", env3_custom, src_custom)
    assert res3_c.returncode == 0, res3_c.stderr
    win3_c = json.loads((out3_c / "window.json").read_text(encoding="utf-8"))
    expected_in_flight_c = 15 + 2
    expected_salvage_c = (10 + 2) + (20 + 2) + (15 + 2)
    assert win3_c["cleanup_stop_attempted_by_s"] == expected_in_flight_c + expected_salvage_c == 68
    assert win3_c["cleanup_bound_s"] == expected_in_flight_c + expected_salvage_c + 2 * (8 + 2) == 88


def test_rung_500_salvage_hung_download_ignoring_term_reaches_stop_within_bound(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({
        "FAKE_VM_TRAIN": "hang_after_step_250",
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "8.88/hr",
        "GUARD_POLL_INTERVAL_S": "0.5",
        "FAKE_COLAB_DOWNLOAD_HANG": "ignore_term",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_UPLOAD_TIMEOUT_S": "2",
        "SDLAB_TEST_SESSIONS_TIMEOUT_S": "2",
        "SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S": "5",
        "SDLAB_TEST_SALVAGE_EXEC_TIMEOUT_S": "5",
        "SDLAB_TEST_DOWNLOAD_TIMEOUT_S": "2",
        "SDLAB_TEST_STOP_TIMEOUT_S": "3",
    })
    # Configured bounds: in-flight (2+1=3) + restart (5+1=6) + exec (5+1=6) + download (2+1=3) = 18 s;
    # stop (2 * (3+1) = 8 s) -> total cleanup_bound_s = 26 s.
    # At 9.5/h, cleanup_reserve = (26 / 3600) * 9.5 = 0.068611 units; cap 0.098611 keeps effective_trip = 0.02 units.
    try:
        res, out_dir = _launch(
            tmp_path, env, src, "--rung-job", "500", "--cap", "0.098611", "--margin", "0.01", timeout_s=28
        )
        assert res.returncode != 0
        guards = (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "REFUSED: CAP_GUARD_TRIPPED" in guards
        assert "SALVAGE_STEP_TIMEOUT download timeout_s=2 kill_grace_s=1 rc=137" in guards, guards
        assert "BUNDLE_AFTER_FAILURE: none on the VM" in guards

        calls = (state_dir / "calls.log").read_text(encoding="utf-8")
        assert "CALL stop -s sdlab-l3-gpu-rung" in calls
        assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")
        assert not (state_dir / "open_sessions" / "sdlab-l3-gpu-rung.json").exists()

        calls_rows = [
            json.loads(x) for x in (state_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()
        ]
        restart_ts = next(r["ts"] for r in calls_rows if r["subcmd"] == "restart-kernel")
        stop_ts = next(r["ts"] for r in calls_rows if r["subcmd"] == "stop")
        assert stop_ts - restart_ts <= 15.0, (restart_ts, stop_ts)

        win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
        assert win["refusal_code"] == "CAP_GUARD_TRIPPED"
        assert win["cleanup_stop_attempted_by_s"] == 18
        assert win["cleanup_bound_s"] == 26
        _assert_children_had_default_signals(state_dir, "restart-kernel", "exec", "download", "stop")
        _assert_token_nowhere(out_dir)
    finally:
        _kill_hung_test_pids(state_dir)


def test_rung_500_stop_hangs_once_then_retries_and_stops_session(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({
        "FAKE_VM_TRAIN": "hang_after_step_250",
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "8.88/hr",
        "GUARD_POLL_INTERVAL_S": "0.5",
        "FAKE_COLAB_STOP_HANG_ONCE": "ignore_term",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_STOP_TIMEOUT_S": "2",
    })
    try:
        # cleanup_bound_s = 301 + (181 + 331 + 301) + 2 * (2 + 1) = 1120 s -> cleanup_reserve = (1120 / 3600) * 9.5 = 2.955556 units;
        # cap 2.985556 minus margin 0.01 minus reserve 2.955556 keeps effective_trip = 0.02 units (~7.58 s).
        res, out_dir = _launch(
            tmp_path, env, src, "--rung-job", "500", "--cap", "2.985556", "--margin", "0.01", timeout_s=28
        )
        assert res.returncode != 0
        _assert_r500_stopped_bundle_keeps_step_250_and_marks_step_500_partial(out_dir, state_dir, "CAP_GUARD_TRIPPED")
        guards = (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "STOP_TIMEOUT attempt=1/2 session=sdlab-l3-gpu-rung timeout_s=2 kill_grace_s=1 rc=137" in guards
        assert "STOP_RETRY attempt=2/2 session=sdlab-l3-gpu-rung" in guards
        calls = (state_dir / "calls.log").read_text(encoding="utf-8").splitlines()
        assert calls.count("CALL stop -s sdlab-l3-gpu-rung") == 2
        assert not (state_dir / "open_sessions" / "sdlab-l3-gpu-rung.json").exists()
        _assert_children_had_default_signals(state_dir, "restart-kernel", "exec", "download", "stop")
    finally:
        _kill_hung_test_pids(state_dir)


def test_rung_500_term_during_salvage_still_completes_salvage_and_runs_stop(tmp_path: Path) -> None:
    import signal as _signal
    import time as _time

    # 1. A single TERM sent to the launcher during salvage is recorded, does not abort salvage halfway,
    # and still runs `colab stop`.
    state_dir, env, src = _rung_env(tmp_path / "sig1")
    env.update({
        "FAKE_VM_TRAIN": "hang_after_step_250",
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "8.88/hr",
        "GUARD_POLL_INTERVAL_S": "0.5",
        "FAKE_COLAB_RESTART_DELAY_S": "1.2",
    })
    out_dir = tmp_path / "sig1" / "out"
    args = [
        _bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--session", "sdlab-l3-gpu-rung",
        "--out-dir", fc._to_posix(out_dir), "--dataset-dir", fc._to_posix(src), "--model", "Qwen/Qwen-Image",
        "--model-revision", REVISION, "--host-ram-required-gib", "96.5", "--download-max-seconds", "60",
        "--wall-s", "2900", "--cap", "3.434167", "--margin", "0.01", "--max-rate", "9.5",
        "--shape", "high-mem", "--rung-job", "500",
    ]
    try:
        proc = subprocess.Popen(
            args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        restarts_f = state_dir / "restarts.log"
        deadline = _time.monotonic() + 25.0
        sent_term = False
        while _time.monotonic() < deadline:
            if restarts_f.is_file() and not sent_term:
                proc.send_signal(_signal.SIGTERM)
                sent_term = True
                break
            if proc.poll() is not None:
                break
            _time.sleep(0.05)
        assert sent_term, "launcher never reached restart-kernel in salvage"
        proc.communicate(timeout=20)
        assert proc.returncode != 0
        _assert_r500_stopped_bundle_keeps_step_250_and_marks_step_500_partial(out_dir, state_dir, "CAP_GUARD_TRIPPED")
        guards = (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "CLEANUP_SIGNAL count=1 action=continue_bounded_cleanup" in guards, guards
        assert "CALL stop -s sdlab-l3-gpu-rung" in (state_dir / "calls.log").read_text(encoding="utf-8")
        _assert_children_had_default_signals(state_dir, "restart-kernel", "exec", "download", "stop")
    finally:
        _kill_hung_test_pids(state_dir)

    # 2. Past SALVAGE_DEADLINE_S (here after a hung restart-kernel that ignores TERM is killed by timeout -k),
    # cleanup skips any remaining salvage step and goes straight to `colab stop`.
    state_dir2, env2, src2 = _rung_env(tmp_path / "deadline")
    env2.update({
        "FAKE_VM_TRAIN": "hang_after_step_250",
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "8.88/hr",
        "GUARD_POLL_INTERVAL_S": "0.5",
        "FAKE_COLAB_RESTART_HANG": "ignore_term",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S": "1",
        "SDLAB_TEST_SALVAGE_DEADLINE_S": "1",
    })
    try:
        # cleanup_bound_s = 301 + 1 + 2 * (60 + 1) = 424 s -> cleanup_reserve = (424 / 3600) * 9.5 = 1.118889 units;
        # cap 1.148889 minus margin 0.01 minus reserve 1.118889 keeps effective_trip = 0.02 units (~7.58 s).
        res2, out2 = _launch(
            tmp_path / "deadline", env2, src2, "--rung-job", "500", "--cap", "1.148889", "--margin", "0.01", timeout_s=25
        )
        assert res2.returncode != 0
        guards2 = (out2 / "guards.log").read_text(encoding="utf-8")
        assert "SALVAGE_STEP_TIMEOUT restart-kernel timeout_s=1 kill_grace_s=1 rc=137" in guards2, guards2
        assert "SALVAGE_DEADLINE_EXCEEDED bundle-now" in guards2, guards2
        assert "SALVAGE_DEADLINE_EXCEEDED download" in guards2, guards2
        calls2 = (state_dir2 / "calls.log").read_text(encoding="utf-8")
        assert "CALL download" not in calls2
        assert "CALL stop -s sdlab-l3-gpu-rung" in calls2
        assert "STOP -s sdlab-l3-gpu-rung" in (state_dir2 / "stops.log").read_text(encoding="utf-8")
    finally:
        _kill_hung_test_pids(state_dir2)


def test_lane1_hung_download_and_hung_stop_reach_colab_stop_within_bound(tmp_path: Path) -> None:
    lane1_sh = COLAB_DIR / "launch_lane1_stub.sh"

    # 1. Lane 1 hung `colab download` that ignores TERM: bounded by timeout -k, logs timeout, runs `colab stop`.
    _, state1, env1 = fc.make_fake_colab_env(tmp_path / "l1_dl")
    env1.update({
        "GUARD_POLL_INTERVAL_S": "0.2",
        "FAKE_COLAB_DOWNLOAD_HANG": "ignore_term",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_DOWNLOAD_TIMEOUT_S": "2",
        "SDLAB_TEST_STOP_TIMEOUT_S": "2",
    })
    out1 = tmp_path / "l1_dl" / "out"
    try:
        res1 = subprocess.run(
            [_bash(), fc._to_posix(lane1_sh), "--out-dir", fc._to_posix(out1), "--session", "sdlab-l1-dlhang"],
            env=env1, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20, check=False,
        )
        assert res1.returncode != 0
        guards1 = (out1 / "guards.log").read_text(encoding="utf-8")
        assert "SALVAGE_STEP_TIMEOUT download timeout_s=2 kill_grace_s=1 rc=137" in guards1, guards1
        assert "REFUSED: DOWNLOAD_FAILED:" in guards1
        calls1 = (state1 / "calls.log").read_text(encoding="utf-8")
        assert "CALL stop -s sdlab-l1-dlhang" in calls1
        assert "STOP -s sdlab-l1-dlhang" in (state1 / "stops.log").read_text(encoding="utf-8")
        win1 = json.loads((out1 / "window.json").read_text(encoding="utf-8"))
        assert win1["refusal_code"] == "DOWNLOAD_FAILED"
        assert win1["cleanup_stop_attempted_by_s"] == 2 + 1 == 3
        assert win1["cleanup_bound_s"] == 3 + 2 * (2 + 1) == 9
        _assert_children_had_default_signals(state1, "download", "stop")
    finally:
        _kill_hung_test_pids(state1)

    # 2. Lane 1 `colab stop` hangs once (ignoring TERM) then succeeds on retry, and closing `colab sessions`
    # hangs and times out cleanly.
    _, state2, env2 = fc.make_fake_colab_env(tmp_path / "l1_stop")
    env2.update({
        "GUARD_POLL_INTERVAL_S": "0.2",
        "FAKE_COLAB_STOP_HANG_ONCE": "ignore_term",
        "FAKE_COLAB_SESSIONS_CLOSE_HANG": "ignore_term",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_STOP_TIMEOUT_S": "1",
        "SDLAB_TEST_SESSIONS_TIMEOUT_S": "1",
    })
    out2 = tmp_path / "l1_stop" / "out"
    try:
        res2 = subprocess.run(
            [_bash(), fc._to_posix(lane1_sh), "--out-dir", fc._to_posix(out2), "--session", "sdlab-l1-stophang"],
            env=env2, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20, check=False,
        )
        assert res2.returncode == 0, res2.stderr
        guards2 = (out2 / "guards.log").read_text(encoding="utf-8")
        assert "STOP_TIMEOUT attempt=1/2 session=sdlab-l1-stophang timeout_s=1 kill_grace_s=1 rc=137" in guards2
        assert "STOP_RETRY attempt=2/2 session=sdlab-l1-stophang" in guards2
        assert "SESSIONS_TIMEOUT session=sdlab-l1-stophang timeout_s=1 kill_grace_s=1 rc=137" in guards2
        calls2 = (state2 / "calls.log").read_text(encoding="utf-8").splitlines()
        assert calls2.count("CALL stop -s sdlab-l1-stophang") == 2
        assert "STOP -s sdlab-l1-stophang" in (state2 / "stops.log").read_text(encoding="utf-8")
        assert not (state2 / "open_sessions" / "sdlab-l1-stophang.json").exists()
        win2 = json.loads((out2 / "window.json").read_text(encoding="utf-8"))
        assert win2["status"] == "ok" and win2["cleanup_bound_s"] == (300 + 1) + 2 * (1 + 1) == 305
    finally:
        _kill_hung_test_pids(state2)


# --- PR #66 fix round 2: cap guard reserves cleanup, up-front refusal, and --dry ---------------

CAP_FORMULA_STR = (
    "effective_trip = cap - margin - cleanup_reserve; cleanup_reserve = (cleanup_bound_s / 3600) * priced_rate"
)


def test_cap_guard_reserves_cleanup_and_trips_earlier_matching_hand_computed_window_json(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "8.88/hr",
        "FAKE_VM_TRAIN": "hang_after_save",
        "GUARD_POLL_INTERVAL_S": "0.5",
    })
    # Hand-computed for Lane 3 (cleanup_bound_s = 1290 s) on G4 priced at max(10.5, 8.88) = 10.5/h:
    # cleanup_reserve = (1290 / 3600) * 10.5 = 3.7625 units.
    # With cap = 3.80, margin = 0.01:
    # effective_trip = 3.80 - 0.01 - 3.7625 = 0.0275 units (~9.43 s at 10.5/h).
    # Without cleanup_reserve, ceiling was 3.79 units (~1299.43 s) and would not trip within this window.
    try:
        res, out_dir = _launch(
            tmp_path, env, src,
            "--card", "G4", "--shape", "standard",
            "--max-rate", "10.5", "--cap", "3.80", "--margin", "0.01",
            timeout_s=40,
        )
        assert res.returncode != 0
        win = _win(out_dir)
        assert win["refusal_code"] == "CAP_GUARD_TRIPPED"
        assert win["cleanup_bound_s"] == 1290
        assert win["rate_used_for_cap_and_projection"] == 10.5
        assert win["cleanup_reserve_units"] == round((1290 / 3600) * 10.5, 6) == 3.7625
        assert win["effective_trip_units"] == round(3.80 - 0.01 - 3.7625, 6) == 0.0275
        assert win["cap_trip_formula"] == CAP_FORMULA_STR
        tripped = [r for r in _cap_records(out_dir) if r["tripped"]]
        assert tripped, "cap guard never tripped"
        assert tripped[0]["cleanup_reserve_units"] == 3.7625
        assert tripped[0]["effective_trip_units"] == 0.0275
        assert tripped[0]["ceiling_ccu"] == 0.0275
        assert tripped[0]["formula"] == CAP_FORMULA_STR
    finally:
        _kill_hung_test_pids(state_dir)


def test_rising_rate_reprices_cleanup_reserve_and_lowers_effective_trip(tmp_path: Path) -> None:
    import launch_guards as lg

    # 1. Unit: as the stable window rate rises from 8.88/h to 10.50/h under --max-rate 9.5,
    # priced_rate rises from 9.5 to 10.5, re-pricing cleanup_reserve from 3.404167 to 3.7625
    # and lowering effective_trip (for cap 4.9, margin 0.01) from 1.485833 to 1.1275.
    # A spend of 1.30 units (start 100.0 -> current 98.7) is below 1.485833 before the rise,
    # and trips CAP_GUARD_TRIPPED once the rising rate re-prices the reserve.
    st = _fold({}, (8.88, 8.88), pre=0.0)
    rate_initial = lg.gpu_projection_rate(st, 9.5)
    assert rate_initial == 9.5
    before = lg.evaluate_cap_guard(
        mode="live", cap=4.9, margin=0.01, cleanup_bound_s=1290,
        start_balance=100.0, current_balance=98.7, rate_ccu_per_hour=rate_initial, elapsed_s=0.0,
    )
    assert before["cleanup_reserve_units"] == 3.404167
    assert before["effective_trip_units"] == 1.485833
    assert before["tripped"] is False

    st = _fold(st, (10.5, 10.5), pre=0.0, start=10.0)
    rate_risen = lg.gpu_projection_rate(st, 9.5)
    assert rate_risen == 10.5
    after = lg.evaluate_cap_guard(
        mode="live", cap=4.9, margin=0.01, cleanup_bound_s=1290,
        start_balance=100.0, current_balance=98.7, rate_ccu_per_hour=rate_risen, elapsed_s=0.0,
    )
    assert after["cleanup_reserve_units"] == 3.7625
    assert after["effective_trip_units"] == 1.1275
    assert after["tripped"] is True and after["code"] == "CAP_GUARD_TRIPPED"

    # 2. End-to-end through the launcher: pre-open rate is 0.26/hr (reserve = 0.093167, effective_trip = 0.396833
    # for cap 0.50, margin 0.01); post-open rate rises to 1.80/hr, re-pricing cleanup_reserve to
    # (1290 / 3600) * 1.80 = 0.645 units and effective_trip to 0.0, tripping CAP_GUARD_TRIPPED mid-run.
    _, state_cpu, env_cpu = fc.make_fake_colab_env(tmp_path / "cpu_rise")
    env_cpu.update({
        "FAKE_COLAB_MODE": "setup_phase",
        "FAKE_COLAB_SETUP_DURATION_S": "10",
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.26/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "1.80/hr",
        "GUARD_POLL_INTERVAL_S": "0.3",
    })
    out_cpu = tmp_path / "cpu_rise" / "out"
    res_cpu = subprocess.run(
        [
            _bash(), fc._to_posix(LAUNCHER),
            "--out-dir", fc._to_posix(out_cpu), "--session", "sdlab-l3-rise-cpu",
            "--cap", "0.50", "--margin", "0.01",
        ],
        env=env_cpu, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=40, check=False,
    )
    assert res_cpu.returncode != 0
    win_cpu = _win(out_cpu)
    assert win_cpu["refusal_code"] == "CAP_GUARD_TRIPPED"
    assert win_cpu["cleanup_reserve_units"] == round((1290 / 3600) * 1.80, 6) == 0.645
    assert win_cpu["effective_trip_units"] == round(0.50 - 0.01 - 0.645, 6) == -0.155
    assert "STOP -s sdlab-l3-rise-cpu" in (state_cpu / "stops.log").read_text(encoding="utf-8")


def test_cap_too_small_for_cleanup_or_min_runtime_refuses_before_any_colab_call(tmp_path: Path) -> None:
    # 1. Lane 3 GPU rung: cap - margin - cleanup_reserve <= 0 (3.70 - 0.01 - 3.7625 = -0.0725 <= 0).
    state1, env1, src1 = _rung_env(tmp_path / "l3_no_room")
    res1, out1 = _launch(
        tmp_path / "l3_no_room", env1, src1,
        "--card", "G4", "--shape", "standard", "--max-rate", "10.5", "--cap", "3.70", "--margin", "0.01",
    )
    assert res1.returncode == 2 and "REFUSED: CAP_TOO_SMALL_FOR_CLEANUP:" in res1.stderr
    assert not (state1 / "calls.log").exists() and not (state1 / "card.txt").exists()
    win1 = _win(out1)
    assert win1["refusal_code"] == "CAP_TOO_SMALL_FOR_CLEANUP"
    assert "3.7625" in win1["why"] and "-0.0725" in win1["why"]
    assert win1["cleanup_reserve_units"] == 3.7625 and win1["effective_trip_units"] == -0.0725

    # 2. Lane 3 GPU rung with --min-runtime-s: cap 4.9 leaves 1.1275 units = 386.57 s at 10.5/h < 900 s.
    state2, env2, src2 = _rung_env(tmp_path / "l3_min_rt")
    res2, out2 = _launch(
        tmp_path / "l3_min_rt", env2, src2,
        "--card", "G4", "--shape", "standard", "--max-rate", "10.5", "--cap", "4.9", "--margin", "0.01",
        "--min-runtime-s", "900",
    )
    assert res2.returncode == 2 and "REFUSED: CAP_TOO_SMALL_FOR_CLEANUP:" in res2.stderr
    assert not (state2 / "calls.log").exists() and not (state2 / "card.txt").exists()
    win2 = _win(out2)
    assert win2["refusal_code"] == "CAP_TOO_SMALL_FOR_CLEANUP"
    assert "386.57" in win2["why"] and "900" in win2["why"]

    # 3. Lane 1 GPU window: cleanup_bound_s = 450 s at 10.5/h -> reserve = 1.3125; cap 1.30 -> -0.0225 <= 0.
    _, state3, env3 = fc.make_fake_colab_env(tmp_path / "l1_no_room")
    out3 = tmp_path / "l1_no_room" / "out"
    lane1_sh = COLAB_DIR / "launch_lane1_stub.sh"
    res3 = subprocess.run(
        [
            _bash(), fc._to_posix(lane1_sh),
            "--card", "G4", "--shape", "standard", "--out-dir", fc._to_posix(out3),
            "--session", "sdlab-l1-smallcap", "--max-rate", "10.5", "--cap", "1.30", "--margin", "0.01",
        ],
        env=env3, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False,
    )
    assert res3.returncode == 2 and "REFUSED: CAP_TOO_SMALL_FOR_CLEANUP:" in res3.stderr
    assert not (state3 / "calls.log").exists()
    win3 = _win(out3)
    assert win3["refusal_code"] == "CAP_TOO_SMALL_FOR_CLEANUP"
    assert win3["cleanup_reserve_units"] == 1.3125 and win3["effective_trip_units"] == -0.0225


def test_dry_prints_trip_arithmetic_for_guard_and_launchers_without_colab_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import launch_guards as lg

    # 1. Direct guard call with --dry where priced_rate (12.0/h) > --max-rate (10.5/h):
    rc = lg.main([
        "--dry", "--cap", "4.9", "--margin", "0.01", "--cleanup-bound-s", "1290",
        "--rate", "12.0", "--max-rate", "10.5",
    ])
    out_guard = capsys.readouterr().out
    assert rc == 0
    rec_guard = json.loads(out_guard.strip().splitlines()[-1])
    # reserve = (1290 / 3600) * 12.0 = 4.3; effective_trip = 4.9 - 0.01 - 4.3 = 0.59
    assert rec_guard["cap"] == 4.9 and rec_guard["margin"] == 0.01
    assert rec_guard["cleanup_bound_s"] == 1290
    assert rec_guard["priced_rate"] == 12.0 and rec_guard["max_rate"] == 10.5
    assert rec_guard["reserve"] == 4.3 and rec_guard["effective_trip"] == 0.59
    assert rec_guard["runtime_at_priced_rate_s"] == round((0.59 / 12.0) * 3600, 2) == 177.0
    assert rec_guard["runtime_at_max_rate_s"] == round((0.59 / 10.5) * 3600, 2) == 202.29
    assert rec_guard["worst_case_total_spend"] == 4.9

    # 2. Lane 3 launcher with --dry on G4 at --max-rate 10.5, --cap 4.9, --margin 0.01:
    state_l3, env_l3, src_l3 = _rung_env(tmp_path / "dry_l3")
    res_l3, _ = _launch(
        tmp_path / "dry_l3", env_l3, src_l3,
        "--card", "G4", "--shape", "standard", "--max-rate", "10.5", "--cap", "4.9", "--margin", "0.01", "--dry",
    )
    assert res_l3.returncode == 0, res_l3.stderr
    assert not (state_l3 / "calls.log").exists()
    for token in (
        "cap: 4.9", "margin: 0.01", "cleanup_bound_s: 1290", "priced_rate: 10.5/h",
        "3.7625", "1.1275", "386.57 s", "worst_case_total_spend: 4.9",
    ):
        assert token in res_l3.stdout, (token, res_l3.stdout)
    rec_l3 = json.loads(res_l3.stdout.strip().splitlines()[-1])
    assert rec_l3["reserve"] == 3.7625 and rec_l3["effective_trip"] == 1.1275
    assert rec_l3["runtime_at_priced_rate_s"] == 386.57 and rec_l3["runtime_at_max_rate_s"] == 386.57
    assert rec_l3["worst_case_total_spend"] == 4.9

    # 3. Lane 1 launcher with --dry on G4 at --max-rate 10.5, --cap 2.0, --margin 0.01:
    _, state_l1, env_l1 = fc.make_fake_colab_env(tmp_path / "dry_l1")
    lane1_sh = COLAB_DIR / "launch_lane1_stub.sh"
    res_l1 = subprocess.run(
        [
            _bash(), fc._to_posix(lane1_sh),
            "--card", "G4", "--shape", "standard", "--max-rate", "10.5", "--cap", "2.0", "--margin", "0.01", "--dry",
        ],
        env=env_l1, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False,
    )
    assert res_l1.returncode == 0, res_l1.stderr
    assert not (state_l1 / "calls.log").exists()
    rec_l1 = json.loads(res_l1.stdout.strip().splitlines()[-1])
    assert rec_l1["cleanup_bound_s"] == 450
    assert rec_l1["reserve"] == 1.3125 and rec_l1["effective_trip"] == 0.6775
    assert rec_l1["runtime_at_priced_rate_s"] == 232.29 and rec_l1["worst_case_total_spend"] == 2.0


# --- PR #66 fix round 3: bound every step from the trip ---------------------------------------


def test_hung_upload_is_cut_at_bound_and_session_is_stopped(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env.update({
        "FAKE_COLAB_UPLOAD_HANG": "ignore_term",
        "FAKE_COLAB_UPLOAD_HANG_FOR": "classify_install_log.py",
        "SDLAB_TEST_UPLOAD_TIMEOUT_S": "1",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_STOP_TIMEOUT_S": "2",
    })
    try:
        res, out_dir = _launch(tmp_path, env, src, timeout_s=10)
        assert res.returncode != 0
        guards = (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "UPLOAD_TIMEOUT" in guards and "timeout_s=1 kill_grace_s=1 rc=137" in guards, guards
        assert "REFUSED: UPLOAD_FAILED:" in guards
        calls = (state_dir / "calls.log").read_text(encoding="utf-8")
        assert "CALL exec" not in calls
        assert "CALL stop -s sdlab-l3-gpu-rung" in calls
        assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")
        assert not (state_dir / "open_sessions" / "sdlab-l3-gpu-rung.json").exists()
        win = _win(out_dir)
        assert win["refusal_code"] == "UPLOAD_FAILED"
        assert win["stop_path"] == "trap"
        _assert_children_had_default_signals(state_dir, "upload", "stop")
    finally:
        _kill_hung_test_pids(state_dir)


def test_hung_new_and_open_lock_wait_are_cut_at_bound(tmp_path: Path) -> None:
    # 1. Hung `colab new` (ignoring TERM) is cut at SDLAB_TEST_NEW_TIMEOUT_S + SDLAB_TEST_KILL_GRACE_S
    # and the session is stopped by cleanup_on_exit.
    state1, env1, src1 = _rung_env(tmp_path / "new_hang")
    env1.update({
        "FAKE_COLAB_NEW_HANG": "ignore_term",
        "SDLAB_TEST_NEW_TIMEOUT_S": "1",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_STOP_TIMEOUT_S": "2",
    })
    try:
        res1, out1 = _launch(tmp_path / "new_hang", env1, src1, timeout_s=10)
        assert res1.returncode != 0
        guards1 = (out1 / "guards.log").read_text(encoding="utf-8")
        assert "NEW_TIMEOUT session=sdlab-l3-gpu-rung timeout_s=1 kill_grace_s=1 rc=137" in guards1, guards1
        assert "REFUSED: SESSION_OPEN_FAILED:" in guards1, guards1
        assert "STOP -s sdlab-l3-gpu-rung" in (state1 / "stops.log").read_text(encoding="utf-8")
        assert not (state1 / "open_sessions" / "sdlab-l3-gpu-rung.json").exists()
        win1 = _win(out1)
        assert win1["refusal_code"] == "SESSION_OPEN_FAILED"
        assert win1["stop_path"] == "trap"
        _assert_children_had_default_signals(state1, "new", "stop")
    finally:
        _kill_hung_test_pids(state1)

    # 2. Hung open-lock wait (another process holds COLAB_OPEN_LOCK) is cut at
    # SDLAB_TEST_OPEN_LOCK_TIMEOUT_S + SDLAB_TEST_KILL_GRACE_S before `colab new` is called.
    state2, env2, src2 = _rung_env(tmp_path / "lock_hang")
    env2.update({
        "SDLAB_TEST_OPEN_LOCK_TIMEOUT_S": "1",
        "SDLAB_TEST_KILL_GRACE_S": "1",
    })
    lock_file = env2["COLAB_OPEN_LOCK"]
    holder = subprocess.Popen(
        [_bash(), "-c", f'exec 9>"{lock_file}"; flock -x 9; sleep 30'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        import time as _time
        _time.sleep(0.2)
        res2, out2 = _launch(tmp_path / "lock_hang", env2, src2, timeout_s=10)
        assert res2.returncode != 0
        guards2 = (out2 / "guards.log").read_text(encoding="utf-8")
        assert "OPEN_LOCK_TIMEOUT" in guards2 and "timeout_s=1 kill_grace_s=1" in guards2, guards2
        assert "REFUSED: OPEN_LOCK_TIMEOUT:" in guards2, guards2
        calls2 = (state2 / "calls.log").read_text(encoding="utf-8") if (state2 / "calls.log").exists() else ""
        assert "CALL new" not in calls2
        win2 = _win(out2)
        assert win2["refusal_code"] == "OPEN_LOCK_TIMEOUT"
    finally:
        holder.kill()
        holder.wait()
        _kill_hung_test_pids(state2)


def test_wall_trip_during_hung_foreground_step_reaches_stop_by_watcher_path(tmp_path: Path) -> None:
    lane1_sh = COLAB_DIR / "launch_lane1_stub.sh"
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    env.update({
        "GUARD_POLL_INTERVAL_S": "0.2",
        "FAKE_COLAB_UPLOAD_HANG": "ignore_term",
        "SDLAB_TEST_UPLOAD_TIMEOUT_S": "30",
        "SDLAB_TEST_WALL_ESCALATE_S": "2",
        "SDLAB_TEST_STOP_TIMEOUT_S": "2",
        "SDLAB_TEST_KILL_GRACE_S": "1",
    })
    out_dir = tmp_path / "out_watcher"
    try:
        # WALL_LIMIT_S = 4 - 2 = 2 s. Foreground `colab upload` hangs for 30 s, so bash cannot run
        # MAIN_PID's TERM trap when the wall watcher sends TERM at 2 s. After SDLAB_TEST_WALL_ESCALATE_S=2 s,
        # the watcher escalates, runs `colab stop -s sdlab-l1-watcher` itself, records stop_path="watcher",
        # and SIGKILLs the launcher.
        res = subprocess.run(
            [
                _bash(), fc._to_posix(lane1_sh),
                "--out-dir", fc._to_posix(out_dir), "--session", "sdlab-l1-watcher",
                "--wall-s", "4", "--grace-s", "2",
            ],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=12, check=False,
        )
        assert res.returncode != 0
        guards = (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "REFUSED: WALL_GUARD_TRIPPED: independent wall watcher" in guards
        assert "WALL_WATCHER_ESCALATED session=sdlab-l1-watcher escalate_s=2" in guards, guards
        assert "STOP -s sdlab-l1-watcher" in (state_dir / "stops.log").read_text(encoding="utf-8")
        assert not (state_dir / "open_sessions" / "sdlab-l1-watcher.json").exists()
        win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
        assert win["refusal_code"] == "WALL_GUARD_TRIPPED"
        assert win["stop_path"] == "watcher"
        trip_ts = float((out_dir / "wall_trip_epoch.txt").read_text(encoding="utf-8").strip())
        stop_done_ts = json.loads((state_dir / "stops.jsonl").read_text(encoding="utf-8").splitlines()[-1])["done_ts"]
        assert stop_done_ts - trip_ts <= win["cleanup_bound_s"], (stop_done_ts - trip_ts, win["cleanup_bound_s"])
    finally:
        _kill_hung_test_pids(state_dir)


def test_wall_trip_during_post_exec_download_keeps_total_time_within_cleanup_bound(tmp_path: Path) -> None:
    lane1_sh = COLAB_DIR / "launch_lane1_stub.sh"
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    env.update({
        "GUARD_POLL_INTERVAL_S": "0.2",
        "FAKE_COLAB_DOWNLOAD_HANG": "ignore_term",
        "SDLAB_TEST_DOWNLOAD_TIMEOUT_S": "6",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_STOP_TIMEOUT_S": "1",
        "SDLAB_TEST_WALL_ESCALATE_S": "30",
    })
    out_dir = tmp_path / "out_dl_wall"
    try:
        # WALL_LIMIT_S = 6 - 2 = 4 s: `colab exec` finishes in ~1 s and enters the post-exec
        # `colab download`, which hangs for 6 + 1 = 7 s while the wall watcher trips at 4 s.
        # Measured from the trip: in_flight_bound_s = 6 + 1 = 7 s, stop_bound_s = 2 * (1 + 1) = 4 s,
        # so cleanup_stop_attempted_by_s = 7 s and cleanup_bound_s = 11 s.
        res = subprocess.run(
            [
                _bash(), fc._to_posix(lane1_sh),
                "--out-dir", fc._to_posix(out_dir), "--session", "sdlab-l1-dlwall",
                "--wall-s", "6", "--grace-s", "2",
            ],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25, check=False,
        )
        assert res.returncode != 0
        win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
        assert win["cleanup_stop_attempted_by_s"] == 7
        assert win["cleanup_bound_s"] == 11
        assert win["stop_path"] == "trap"
        trip_ts = float((out_dir / "wall_trip_epoch.txt").read_text(encoding="utf-8").strip())
        calls_rows = [
            json.loads(x) for x in (state_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()
        ]
        stop_start_ts = next(r["ts"] for r in calls_rows if r["subcmd"] == "stop")
        stop_done_ts = json.loads((state_dir / "stops.jsonl").read_text(encoding="utf-8").splitlines()[-1])["done_ts"]
        assert stop_start_ts - trip_ts <= win["cleanup_stop_attempted_by_s"], (
            stop_start_ts - trip_ts, win["cleanup_stop_attempted_by_s"]
        )
        assert stop_done_ts - trip_ts <= win["cleanup_bound_s"], (stop_done_ts - trip_ts, win["cleanup_bound_s"])
    finally:
        _kill_hung_test_pids(state_dir)


def test_failed_normal_download_still_salvages_bundle(tmp_path: Path) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    env["FAKE_COLAB_DOWNLOAD_FAIL_ONCE"] = "1"
    res, out_dir = _launch(tmp_path, env, src)
    assert res.returncode != 0
    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "REFUSED: DOWNLOAD_FAILED:" in guards
    assert "BUNDLE_AFTER_FAILURE: downloaded lane3_stub_bundle.tar.gz" in guards, guards
    assert int((state_dir / "download_attempts.txt").read_text(encoding="utf-8").strip()) == 2
    assert (out_dir / "lane3_stub_bundle.tar.gz").is_file()
    members = _bundle(out_dir)
    assert "rung_outputs/rustline_style_v5/rustline_style_v5_000000020.safetensors" in members
    assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")
    win = _win(out_dir)
    assert win["refusal_code"] == "DOWNLOAD_FAILED"
    assert win["stop_path"] == "trap"
    _assert_token_nowhere(out_dir)


def test_second_term_during_salvage_aborts_salvage_and_reaches_stop(tmp_path: Path) -> None:
    import signal as _signal
    import time as _time

    state_dir, env, src = _rung_env(tmp_path)
    env.update({
        "FAKE_VM_TRAIN": "hang_after_step_250",
        "FAKE_COLAB_PRE_OPEN_RATE_STR": "0.00/hr",
        "FAKE_COLAB_POST_OPEN_RATE_STR": "8.88/hr",
        "GUARD_POLL_INTERVAL_S": "0.5",
        "FAKE_COLAB_RESTART_DELAY_S": "15",
        "SDLAB_TEST_DOWNLOAD_TIMEOUT_S": "5",
        "SDLAB_TEST_KILL_GRACE_S": "1",
        "SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S": "20",
        "SDLAB_TEST_SALVAGE_EXEC_TIMEOUT_S": "5",
        "SDLAB_TEST_STOP_TIMEOUT_S": "2",
    })
    out_dir = tmp_path / "out_sig2"
    # wall 10s - grace 2s = 8s wall limit (>= download 5 + install 1 + train 1 = 7s): the independent wall
    # watcher fires after 8s while the VM hangs after step 250.
    env.update({
        "SDLAB_TEST_INSTALL_ALLOWANCE_S": "1",
        "SDLAB_TEST_TRAIN_ALLOWANCE_S": "1",
    })
    args = [
        _bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--session", "sdlab-l3-gpu-rung",
        "--out-dir", fc._to_posix(out_dir), "--dataset-dir", fc._to_posix(src), "--model", "Qwen/Qwen-Image",
        "--model-revision", REVISION, "--host-ram-required-gib", "96.5", "--download-max-seconds", "5",
        "--wall-s", "10", "--grace-s", "2", "--cap", "5", "--margin", "0.01", "--max-rate", "9.5",
        "--shape", "high-mem", "--rung-job", "500",
    ]
    try:
        proc = subprocess.Popen(
            args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        restarts_f = state_dir / "restarts.log"
        deadline = _time.monotonic() + 25.0
        sent_two_terms = False
        while _time.monotonic() < deadline:
            if restarts_f.is_file():
                proc.send_signal(_signal.SIGTERM)
                _time.sleep(0.15)
                proc.send_signal(_signal.SIGTERM)
                sent_two_terms = True
                break
            if proc.poll() is not None:
                break
            _time.sleep(0.05)
        assert sent_two_terms, "launcher never reached restart-kernel in salvage"
        # Because the second TERM aborts the in-flight 15 s restart-kernel and skips remaining salvage,
        # the launcher must finish and run `colab stop` within 6 s (not waiting the 15 s restart delay).
        proc.communicate(timeout=6)
        assert proc.returncode != 0
        guards = (out_dir / "guards.log").read_text(encoding="utf-8")
        assert "CLEANUP_SIGNAL count=1 action=continue_bounded_cleanup" in guards, guards
        assert "CLEANUP_SIGNAL count=2 action=skip_remaining_salvage" in guards, guards
        assert "SALVAGE_DEADLINE_EXCEEDED bundle-now" in guards, guards
        assert "SALVAGE_DEADLINE_EXCEEDED download" in guards, guards
        calls = (state_dir / "calls.log").read_text(encoding="utf-8")
        assert "CALL download" not in calls
        assert "CALL stop -s sdlab-l3-gpu-rung" in calls
        assert "STOP -s sdlab-l3-gpu-rung" in (state_dir / "stops.log").read_text(encoding="utf-8")
    finally:
        _kill_hung_test_pids(state_dir)


def test_lane1_ignores_salvage_timeout_overrides_in_cleanup_bounds(tmp_path: Path) -> None:
    lane1_sh = COLAB_DIR / "launch_lane1_stub.sh"
    _, _, env1 = fc.make_fake_colab_env(tmp_path)
    env1.update({
        "GUARD_POLL_INTERVAL_S": "0.2",
        "SDLAB_TEST_SALVAGE_RESTART_TIMEOUT_S": "5",
        "SDLAB_TEST_SALVAGE_EXEC_TIMEOUT_S": "5",
        "SDLAB_TEST_SALVAGE_DEADLINE_S": "12",
    })
    out1 = tmp_path / "out_l1_ignore_salvage"
    res1 = subprocess.run(
        [_bash(), fc._to_posix(lane1_sh), "--out-dir", fc._to_posix(out1), "--session", "sdlab-l1-ign-salvage"],
        env=env1, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )
    assert res1.returncode == 0, res1.stderr
    win1 = json.loads((out1 / "window.json").read_text(encoding="utf-8"))
    # Lane 1 has no salvage step: its from-trip cleanup_stop_attempted_by_s is the longest in-flight
    # bounded step (download: 300 + 10 = 310 s), and cleanup_bound_s is 310 + 2 * (60 + 10) = 450 s,
    # completely unaffected by the three SDLAB_TEST_SALVAGE_* overrides.
    assert win1["cleanup_stop_attempted_by_s"] == 310
    assert win1["cleanup_bound_s"] == 450



