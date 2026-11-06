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
    ck.write_bytes(b"A" * 10)
    (watch / "_latent_cache" / "x.safetensors").write_bytes(b"L")
    (watch / "notes.yaml").write_text("x", encoding="utf-8")
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # first sight: size not yet settled
    ck.write_bytes(b"A" * 20)
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # still growing
    assert lr.copy_off_once(watch, bundle, manifest, state) == 1
    assert lr.copy_off_once(watch, bundle, manifest, state) == 0  # once only
    (watch / "samples" / "s.jpg").write_bytes(b"J")
    assert lr.copy_off_once(watch, bundle, manifest, state, final=True) == 1
    lines = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines()]
    assert [x["path"] for x in lines] == ["job_000000020.safetensors", "samples/s.jpg"]
    assert lines[0]["sha256"] == hashlib.sha256(b"A" * 20).hexdigest() and lines[0]["bytes"] == 20
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


def _rung_env(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
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
    for f in out_dir.rglob("*"):
        if f.is_file():
            assert TOKEN.encode() not in f.read_bytes(), f
    if (out_dir / "lane3_stub_bundle.tar.gz").exists():
        for name, data in _bundle(out_dir).items():
            assert TOKEN.encode() not in data, name


def _launch(tmp_path: Path, env: dict[str, str], src: Path, *extra: str, out: str = "out") -> tuple[subprocess.CompletedProcess[str], Path]:
    out_dir = tmp_path / out
    args = [_bash(), fc._to_posix(LAUNCHER), "--train", "--card", "A100", "--session", "sdlab-l3-gpu-rung",
            "--out-dir", fc._to_posix(out_dir), "--dataset-dir", fc._to_posix(src), "--model", "Qwen/Qwen-Image",
            "--model-revision", REVISION, "--host-ram-required-gib", "96.5", "--download-max-seconds", "1800", *extra]
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
    assert members["rung_outputs/rustline_style_v5/rustline_style_v5_000000020.safetensors"].startswith(b"FAKE-LORA-STEP-20")
    assert b"CUDA out of memory" in members["train.log"]
    _assert_token_nowhere(out_dir)


@pytest.mark.parametrize(
    ("drop", "code"),
    [("--model-revision", "TRAIN_MODEL_REVISION_REQUIRED"), ("--host-ram-required-gib", "HOST_RAM_THRESHOLD_MISSING"),
     ("--download-max-seconds", "DOWNLOAD_LIMIT_MISSING"), ("--dataset-dir", "TRAIN_DATASET_REQUIRED"),
     ("--model", "TRAIN_MODEL_REQUIRED"), ("token", "HF_READ_TOKEN_MISSING")],
)
def test_kit_refuses_a_rung_request_missing_a_value_before_any_colab_call(tmp_path: Path, drop: str, code: str) -> None:
    state_dir, env, src = _rung_env(tmp_path)
    args = {"--model": "Qwen/Qwen-Image", "--model-revision": REVISION, "--host-ram-required-gib": "96.5",
            "--download-max-seconds": "1800", "--dataset-dir": fc._to_posix(src)}
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
