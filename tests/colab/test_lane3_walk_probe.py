"""The GPU-rung walk instruments (scripts/colab/lane3/walk_probe.py) and the walk harnesses' refusals.

The walks themselves need the rig's GPU and run under a card grant; these tests drive the
instruments against a fake /proc tree, fake nvidia-smi output and recorded logs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LANE3_DIR = REPO_ROOT / "scripts" / "colab" / "lane3"
sys.path.insert(0, str(LANE3_DIR))

import walk_probe as wp  # noqa: E402

GIB = 1024**3
Res = namedtuple("Res", "returncode stdout")


def _proc(root: Path, pid: int, ppid: int, rss_kb: int, comm: str = "python") -> None:
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "stat").write_text(f"{pid} ({comm}) S {ppid} 1 1 0\n", encoding="utf-8")
    (d / "status").write_text(f"Name: {comm}\nVmRSS:\t{rss_kb} kB\nRssAnon:\t{rss_kb - 10} kB\nRssFile:\t10 kB\nVmSwap:\t0 kB\n",
                              encoding="utf-8")


def _meminfo(root: Path, avail_kb: int) -> None:
    (root / "meminfo").write_text(f"MemTotal: 28000000 kB\nMemAvailable: {avail_kb} kB\n", encoding="utf-8")


def test_gpu_busy_names_processes_and_handles_no_reading(tmp_path: Path) -> None:
    win = tmp_path / "nvidia-smi.exe"
    win.write_text("", encoding="utf-8")

    def run(cmd: list[str], **_k: object) -> Res:
        if "--query-gpu=memory.used" in cmd:
            return Res(0, "9504\n")
        if cmd[0] == str(win):
            return Res(0, "4242, C:\\job\\python.exe, 9000 MiB\n")
        return Res(0, "")

    busy, detail = wp.gpu_busy("nvidia-smi", str(win), 2048, run=run)
    assert busy is True and "memory.used 9504 MiB" in detail and "windows: 4242, C:\\job\\python.exe" in detail
    free, detail2 = wp.gpu_busy("nvidia-smi", None, 2048, run=lambda c, **k: Res(0, "512\n") if "--query-gpu=memory.used" in c else Res(0, ""))
    assert free is False and "WSL hides" in detail2
    assert wp.gpu_busy("nvidia-smi", None, 2048, run=lambda c, **k: Res(9, ""))[0] is True

    def boom(*_a: object, **_k: object) -> Res:
        raise FileNotFoundError("nvidia-smi")

    assert wp.gpu_busy("nvidia-smi", None, 2048, run=boom)[0] is True


def test_gpu_busy_cli_refuses_by_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    smi = tmp_path / "nvidia-smi"
    smi.write_text("#!/usr/bin/env bash\necho 9504\n", encoding="utf-8")
    smi.chmod(0o755)
    assert wp.main(["gpu-busy", "--nvidia-smi", str(smi), "--max-mib", "2048"]) == 3
    assert "REFUSED: GPU_BUSY: memory.used 9504 MiB" in capsys.readouterr().err
    assert wp.main(["gpu-busy", "--nvidia-smi", str(smi), "--max-mib", "20000"]) == 0
    assert "GPU_FREE" in capsys.readouterr().out


def test_tree_rss_status_and_meminfo(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _proc(proc, 100, 1, 1000)
    _proc(proc, 101, 100, 2_000_000, comm="py thon) x")
    _proc(proc, 102, 101, 3000)
    _proc(proc, 200, 1, 9)
    (proc / "self").mkdir()
    (proc / "300").mkdir()  # no stat file
    assert sorted(wp.tree_pids(proc, 100)) == [100, 101, 102]
    assert wp.read_status(proc, 101)["VmRSS"] == 2_000_000 * 1024
    assert wp.read_status(proc, 999) == {}
    _meminfo(proc, 5_000_000)
    assert wp.mem_available(proc) == 5_000_000 * 1024
    assert wp.mem_available(tmp_path / "none") is None
    (proc / "meminfo").write_text("MemTotal: 1 kB\n", encoding="utf-8")
    assert wp.mem_available(proc) is None
    assert wp.children_map(tmp_path / "nope") == {}


def test_phase_markers_follow_ai_toolkit_order() -> None:
    assert wp.phase_of("") == "setup"
    assert wp.phase_of("Loading Qwen Image model\nLoading transformer\n") == "load_transformer"
    caching = "Model Loaded\nCaching latents to disk: 100%|####| 36/36 [00:05<00:00, 6.5it/s]\r"
    assert wp.phase_of(caching) == "cache_latents"
    assert wp.phase_of(caching + "\rrustline_style_v5:  10%|#  | 2/20 [00:04<00:36, 2.0s/it]") == "train_steps"
    assert wp.phase_of("Saving at step 20\nGenerating Images: 0%|") == "sample"
    assert wp.last_line("a\r\nb\rc  \n") == "c  " and wp.last_line("") == ""


def test_sampler_records_rows_and_stops_on_each_condition(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _proc(proc, 100, 1, 1000)
    _proc(proc, 101, 100, 4_000_000)
    _meminfo(proc, 20_000_000)
    log = tmp_path / "train.log"
    killed: list[int] = []

    def kill(pid: int, _sig: int) -> None:
        killed.append(pid)
        if pid == 999:
            raise ProcessLookupError

    def args(**over: object) -> argparse.Namespace:
        base = dict(proc=str(proc), root_pid=100, train_log=str(log), out=str(tmp_path / "h.csv"), interval=0.0,
                    oom_grace_s=1.0, mem_floor_gib=2.0, wall_s=1000.0)
        base.update(over)
        return argparse.Namespace(**base)

    # OOM line seen, the run still alive past the grace: the tree is killed.
    log.write_text("Loading transformer\ntorch.OutOfMemoryError: CUDA out of memory. Tried to allocate 270.00 MiB\n",
                   encoding="utf-8")
    ticks = iter([0.0, 0.0, 0.5, 1.5, 2.0, 3.0])
    assert wp.run_sample(args(), clock=lambda: next(ticks), sleep=lambda s: None, kill=kill) == 0
    assert sorted(killed) == [100, 101]
    rows = (tmp_path / "h.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("epoch,elapsed_s,pids,vm_rss_bytes") and len(rows) == 4
    assert "load_transformer" in rows[1] and "oom line seen" in (tmp_path / "h.stop.txt").read_text(encoding="utf-8")
    # Host RAM below the floor.
    log.write_text("Loading transformer\n", encoding="utf-8")
    _meminfo(proc, 1_000_000)
    killed.clear()
    ticks = iter([0.0, 0.0, 1.0])
    wp.run_sample(args(), clock=lambda: next(ticks), sleep=lambda s: None, kill=kill)
    assert "HOST_RAM_CEILING" in (tmp_path / "h.stop.txt").read_text(encoding="utf-8") and killed
    # Wall cap.
    _meminfo(proc, 20_000_000)
    ticks = iter([0.0, 0.0, 5.0])
    wp.run_sample(args(wall_s=1.0), clock=lambda: next(ticks), sleep=lambda s: None, kill=kill)
    assert "wall cap" in (tmp_path / "h.stop.txt").read_text(encoding="utf-8")
    # The tree exits by itself.
    ticks = iter([0.0, 0.0])
    wp.run_sample(args(root_pid=4242, train_log=str(tmp_path / "missing.log")), clock=lambda: next(ticks),
                  sleep=lambda s: None, kill=kill)
    assert (tmp_path / "h.stop.txt").read_text(encoding="utf-8").strip() == "process tree exited"
    wp.kill_tree(proc, 999, kill)  # a pid that is gone is skipped


def test_summarize_reports_peaks_phases_and_the_oom_line(tmp_path: Path) -> None:
    host = tmp_path / "h.csv"
    host.write_text(
        "epoch,elapsed_s,pids,vm_rss_bytes,rss_anon_bytes,rss_file_bytes,vm_swap_bytes,max_proc_rss_bytes,mem_available_bytes,phase,last_log_line\n"
        f"1000.0,0.0,3,{2 * GIB},{2 * GIB},0,0,{2 * GIB},{20 * GIB},setup,import\n"
        f"1002.0,2.0,3,{30 * GIB},{29 * GIB},{GIB},{3 * GIB},{30 * GIB},{GIB},load_transformer,Loading transformer\n"
        f"1004.0,4.0,3,{10 * GIB},{9 * GIB},{GIB},0,{10 * GIB},,load_transformer,Traceback\n",
        encoding="utf-8")
    import time as _t

    def ts(epoch: float) -> str:
        return _t.strftime("%Y/%m/%d %H:%M:%S", _t.localtime(epoch)) + ".123"

    vram = tmp_path / "v.csv"
    vram.write_text(f"{ts(1000)}, 1200\n{ts(1003)}, 32100\nbad line\n{ts(1005)}, x\n", encoding="utf-8")
    log = tmp_path / "train.log"
    log.write_text('Loading transformer\nTraceback (most recent call last):\n'
                   '  File "/content/ai-toolkit/toolkit/models/v2/_mixin.py", line 451, in aitk_post_load\n'
                   'torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 270.00 MiB\n', encoding="utf-8")
    stop = tmp_path / "h.stop.txt"
    stop.write_text("process tree exited\n", encoding="utf-8")
    assert wp.main(["summarize", "--host-csv", str(host), "--vram-csv", str(vram), "--train-log", str(log),
                    "--stop-file", str(stop), "--out", str(tmp_path / "s.json")]) == 0
    s = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert s["peak_host_rss_gib"] == 30.0 and s["peak_phase"] == "load_transformer" and s["peak_at_elapsed_s"] == 2.0
    assert s["peak_host_swap_gib"] == 3.0 and s["min_mem_available_gib"] == 1.0
    assert s["peak_vram_mib_by_phase"] == {"setup": 1200, "load_transformer": 32100}
    assert s["oom_line"].startswith("torch.OutOfMemoryError") and s["oom_phase"] == "load_transformer"
    assert s["oom_traceback_ai_toolkit_frames"] == ["_mixin.py:451 in aitk_post_load"]
    assert s["stop"] == "process tree exited" and (tmp_path / "s.txt").exists()
    empty = wp.summarize(host, tmp_path / "none.csv", tmp_path / "none.log", None)
    assert empty["oom_line"] is None and empty["peak_vram_mib_by_phase"] == {} and empty["stop"] is None


def test_derive_walk_b_swaps_only_the_model_block(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "b.yaml"
    ara = "/content/hf_home/hub/models--ostris--accuracy_recovery_adapters/snapshots/x/qwen_image_torchao_uint3.safetensors"
    assert wp.main(["derive-walk-b", "--rung-yaml", str(LANE3_DIR / "rung-qwen-image.yaml"), "--ara-path", ara,
                    "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert f'qtype: "uint3|{ara}"' in text and 'qtype_te: "qfloat8"' in text
    assert "      quantize: true\n" in text and "      quantize_te: true\n" in text and "      low_vram: true\n" in text
    rung = (LANE3_DIR / "rung-qwen-image.yaml").read_text(encoding="utf-8")
    assert text.count("\n") == rung.count("\n") + 4  # two header lines and the two qtype lines
    assert wp.main(["derive-walk-b", "--rung-yaml", str(out), "--ara-path", ara, "--out", str(out)]) == 2
    assert wp.main(["derive-walk-b", "--rung-yaml", str(out), "--ara-path", "x.bin", "--out", str(out)]) == 2
    assert capsys.readouterr().err.count("REFUSED: WALK_ARG_INVALID") == 2


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    return str(git_bash) if git_bash.exists() else (shutil.which("bash") or "bash")


@pytest.mark.parametrize("walk", ["walk_a_real_load.sh", "walk_b_quantised.sh"])
def test_walk_harnesses_refuse_missing_arguments(tmp_path: Path, walk: str) -> None:
    script = (LANE3_DIR / walk).as_posix()
    res = subprocess.run([_bash(), script, "--wheel-dir", "w", "--hf-home", "h"], capture_output=True, text=True, check=False)
    assert res.returncode == 2 and "REFUSED: WALK_ARG_MISSING: --dataset-dir is required" in res.stderr
    res = subprocess.run([_bash(), script, "--bogus"], capture_output=True, text=True, check=False)
    assert res.returncode == 2 and "REFUSED: WALK_ARG_INVALID: unknown argument --bogus" in res.stderr
    res = subprocess.run([_bash(), script, "--wheel-dir", "w", "--hf-home", str(tmp_path), "--dataset-dir", "d",
                          "--evidence-root", "e", "--wall-s", "soon"], capture_output=True, text=True, check=False)
    assert res.returncode == 2 and "REFUSED: WALK_ARG_INVALID: --wall-s soon" in res.stderr
