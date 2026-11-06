#!/usr/bin/env python3
"""Instruments for the lane 3 GPU-rung local walks on the rig (walk_a_real_load.sh, walk_b_quantised.sh).

Subcommands:
  gpu-busy      refuse (exit 3, `REFUSED: GPU_BUSY: ...`) when the GPU already holds more than
                --max-mib of memory, naming the processes nvidia-smi lists (WSL's nvidia-smi
                hides them; the Windows nvidia-smi.exe is asked too when it exists).
  sample        every second, the host RSS of a process tree (VmRSS, RssAnon, RssFile, VmSwap from
                /proc/<pid>/status) and the phase ai-toolkit's train.log has reached, to a CSV. It
                stops the tree itself on a CUDA OOM line that is not followed by an exit within
                --oom-grace-s, on MemAvailable below --mem-floor-gib, and at --wall-s.
  summarize     peak host RSS (and where in the log it happened), peak VRAM per phase (joined
                from nvidia-smi's CSV by time), the furthest phase reached and the exact OOM line,
                into summary.json and summary.txt.
  derive-walk-b the quantised stand-in YAML for walk (b) from the rung YAML (ai-toolkit's documented
                Qwen-Image quantisation at beb94824, config/examples/train_lora_qwen_image_24gb.yaml:
                quantize + qtype uint3 with its accuracy recovery adapter, quantize_te + qtype_te
                qfloat8, low_vram true).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

GIB = 1024**3
# ai-toolkit's own progress lines at beb94824 (extensions_built_in/diffusion_models/qwen_image/
# qwen_image.py, toolkit/dataloader_mixins.py, jobs/process/BaseSDTrainProcess.py), in run order.
PHASES = (
    ("load_transformer", r"Loading transformer"),
    ("load_text_encoder", r"^Text Encoder"),
    ("load_vae", r"Loading VAE"),
    ("making_pipe", r"Making pipe"),
    ("preparing_model", r"Preparing Model"),
    ("model_loaded", r"Model Loaded"),
    ("cache_latents", r"Caching latents"),
    ("cache_text_embeddings", r"Caching text_embeddings|Caching text embeddings"),
    ("unload_text_encoder", r"Caching embeddings and unloading text encoder"),
    # the training bar is tqdm with desc=<job name> (BaseSDTrainProcess.py:2495-2497); caching bars'
    # descriptions hold spaces, the job name does not
    ("train_steps", r"^[A-Za-z0-9_.-]+:\s+\d+%\|"),
    ("save", r"Saving at step|Saved checkpoint to"),
    ("sample", r"Generating Images"),
)
OOM_RE = re.compile(r"(CUDA out of memory|OutOfMemoryError|CUBLAS_STATUS_ALLOC_FAILED)")


def refuse(code: str, detail: str) -> None:
    print(f"REFUSED: {code}: {detail}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------
# gpu-busy
# ---------------------------------------------------------------------------------------------


def _query(cmd: list[str], run: Callable[..., Any]) -> list[str]:
    try:
        res = run(cmd, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if res.returncode != 0:
        return []
    return [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]


def gpu_busy(nvidia_smi: str, windows_smi: str | None, max_mib: int, run: Callable[..., Any] = subprocess.run) -> tuple[bool, str]:
    used_lines = _query([nvidia_smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"], run)
    if not used_lines:
        return True, f"{nvidia_smi} reported no GPU memory figure"
    used = int(float(used_lines[0].split(",")[0]))
    apps = _query([nvidia_smi, "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"], run)
    if windows_smi and os.path.exists(windows_smi):
        apps += [f"windows: {a}" for a in _query(
            [windows_smi, "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"], run)]
    named = "; ".join(apps) if apps else "no process listed (WSL hides GPU processes)"
    detail = f"memory.used {used} MiB (limit {max_mib} MiB); processes: {named}"
    return used > max_mib, detail


# ---------------------------------------------------------------------------------------------
# sample
# ---------------------------------------------------------------------------------------------


def read_status(proc: Path, pid: int) -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        text = (proc / str(pid) / "status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        m = re.match(r"^(VmRSS|RssAnon|RssFile|VmSwap):\s+(\d+)\s*kB", line)
        if m:
            out[m.group(1)] = int(m.group(2)) * 1024
    return out


def children_map(proc: Path) -> dict[int, list[int]]:
    kids: dict[int, list[int]] = {}
    for entry in proc.iterdir() if proc.is_dir() else []:
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # comm may hold spaces and parentheses: the ppid is the 2nd field after the last ')'.
        rest = stat.rsplit(")", 1)[-1].split()
        if len(rest) >= 2:
            kids.setdefault(int(rest[1]), []).append(int(entry.name))
    return kids


def tree_pids(proc: Path, root: int) -> list[int]:
    kids = children_map(proc)
    out, todo = [], [root]
    while todo:
        pid = todo.pop()
        if (proc / str(pid)).exists():
            out.append(pid)
        todo.extend(kids.get(pid, []))
    return out


def mem_available(proc: Path) -> int | None:
    try:
        for line in (proc / "meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def phase_of(log_text: str) -> str:
    """The latest phase whose marker the log holds (phases are in run order)."""
    text = log_text.replace(chr(13), chr(10))
    phase = "setup"
    for name, marker in PHASES:
        if re.search(marker, text, flags=re.M):
            phase = name
    return phase


def last_line(log_text: str) -> str:
    lines = [ln for ln in re.split(r"[\r\n]+", log_text) if ln.strip()]
    return lines[-1][-200:] if lines else ""


def kill_tree(proc: Path, root: int, kill: Callable[[int, int], None] = os.kill) -> None:
    for pid in reversed(tree_pids(proc, root)):
        try:
            kill(pid, signal.SIGKILL)
        except OSError:
            continue


def run_sample(args: argparse.Namespace, *, clock: Callable[[], float] = time.time,
               sleep: Callable[[float], None] = time.sleep, kill: Callable[[int, int], None] = os.kill) -> int:
    proc = Path(args.proc)
    root = int(args.root_pid)
    train_log = Path(args.train_log)
    start = clock()
    oom_seen_at: float | None = None
    stop_reason = ""
    with Path(args.out).open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["epoch", "elapsed_s", "pids", "vm_rss_bytes", "rss_anon_bytes", "rss_file_bytes", "vm_swap_bytes",
                    "max_proc_rss_bytes", "mem_available_bytes", "phase", "last_log_line"])
        while (proc / str(root)).exists():
            now = clock()
            pids = tree_pids(proc, root)
            stats = [read_status(proc, p) for p in pids]
            log_text = train_log.read_text(encoding="utf-8", errors="replace") if train_log.exists() else ""
            avail = mem_available(proc)
            w.writerow([round(now, 2), round(now - start, 1), len(pids),
                        sum(s.get("VmRSS", 0) for s in stats), sum(s.get("RssAnon", 0) for s in stats),
                        sum(s.get("RssFile", 0) for s in stats), sum(s.get("VmSwap", 0) for s in stats),
                        max((s.get("VmRSS", 0) for s in stats), default=0), avail, phase_of(log_text),
                        last_line(log_text)])
            fh.flush()
            if OOM_RE.search(log_text) and oom_seen_at is None:
                oom_seen_at = now
            if oom_seen_at is not None and now - oom_seen_at >= float(args.oom_grace_s):
                stop_reason = f"oom line seen and the run still alive after {args.oom_grace_s} s"
            elif avail is not None and avail < float(args.mem_floor_gib) * GIB:
                stop_reason = f"HOST_RAM_CEILING: MemAvailable {avail / GIB:.2f} GiB < floor {args.mem_floor_gib} GiB"
            elif now - start >= float(args.wall_s):
                stop_reason = f"wall cap {args.wall_s} s reached"
            if stop_reason:
                kill_tree(proc, root, kill)
                break
            sleep(float(args.interval))
    Path(args.out).with_suffix(".stop.txt").write_text((stop_reason or "process tree exited") + "\n", encoding="utf-8")
    print(f"SAMPLER_STOP {stop_reason or 'process tree exited'}", flush=True)
    return 0


# ---------------------------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------------------------


def _parse_vram(path: Path) -> list[tuple[float, int]]:
    """(epoch, MiB) rows from `nvidia-smi --query-gpu=timestamp,memory.used --format=csv,noheader,nounits -lms 1000`."""
    rows: list[tuple[float, int]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            ts = time.mktime(time.strptime(parts[0].split(".")[0], "%Y/%m/%d %H:%M:%S"))
            rows.append((ts, int(float(parts[1]))))
        except ValueError:
            continue
    return rows


def summarize(host_csv: Path, vram_csv: Path, train_log: Path, stop_file: Path | None) -> dict[str, Any]:
    with host_csv.open(encoding="utf-8") as fh:
        host = list(csv.DictReader(fh))
    log_text = train_log.read_text(encoding="utf-8", errors="replace") if train_log.exists() else ""
    peak = max(host, key=lambda r: int(r["vm_rss_bytes"]), default=None)
    timeline = [(float(r["epoch"]), r["phase"]) for r in host]

    def phase_at(ts: float) -> str:
        cur = timeline[0][1] if timeline else "setup"
        for t, ph in timeline:
            if t <= ts:
                cur = ph
        return cur

    vram_by_phase: dict[str, int] = {}
    for ts, mib in _parse_vram(vram_csv):
        ph = phase_at(ts)
        vram_by_phase[ph] = max(vram_by_phase.get(ph, 0), mib)
    oom_lines = [ln.strip() for ln in re.split(r"[\r\n]+", log_text) if OOM_RE.search(ln)]
    frames = re.findall(r'File "([^"]*ai-toolkit[^"]*)", line (\d+), in (\w+)', log_text)
    reached = phase_of(log_text)
    summary: dict[str, Any] = {
        "samples": len(host),
        "peak_host_rss_gib": round(int(peak["vm_rss_bytes"]) / GIB, 2) if peak else None,
        "peak_host_rss_anon_gib": round(max((int(r["rss_anon_bytes"]) for r in host), default=0) / GIB, 2),
        "peak_host_swap_gib": round(max((int(r["vm_swap_bytes"]) for r in host), default=0) / GIB, 2),
        "peak_at_elapsed_s": float(peak["elapsed_s"]) if peak else None,
        "peak_phase": peak["phase"] if peak else None,
        "peak_last_log_line": peak["last_log_line"] if peak else None,
        "min_mem_available_gib": round(min((int(r["mem_available_bytes"]) for r in host if r["mem_available_bytes"]),
                                           default=0) / GIB, 2),
        "peak_vram_mib_by_phase": vram_by_phase,
        "furthest_phase": reached,
        "oom_line": oom_lines[0] if oom_lines else None,
        "oom_phase": reached if oom_lines else None,
        "oom_traceback_ai_toolkit_frames": [f"{Path(f).name}:{ln} in {fn}" for f, ln, fn in frames][-6:],
        "stop": stop_file.read_text(encoding="utf-8").strip() if stop_file and stop_file.exists() else None,
    }
    return summary


def run_summarize(args: argparse.Namespace) -> int:
    s = summarize(Path(args.host_csv), Path(args.vram_csv), Path(args.train_log),
                  Path(args.stop_file) if args.stop_file else None)
    out = Path(args.out)
    out.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    lines = [f"{k}: {json.dumps(v)}" for k, v in s.items()]
    out.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)
    return 0


# ---------------------------------------------------------------------------------------------
# derive-walk-b
# ---------------------------------------------------------------------------------------------


def derive_walk_b(rung_text: str, ara_path: str) -> str:
    swaps = (
        ("      quantize: false\n", f'      quantize: true\n      qtype: "uint3|{ara_path}"\n'),
        ("      quantize_te: false\n", '      quantize_te: true\n      qtype_te: "qfloat8"\n'),
        ("      low_vram: false\n", "      low_vram: true\n"),
    )
    out = rung_text
    for old, new in swaps:
        if out.count(old) != 1:
            raise ValueError(f"rung YAML must hold {old.strip()!r} exactly once")
        out = out.replace(old, new)
    header = ("# Walk (b) stand-in, derived from rung-qwen-image.yaml by walk_probe.py derive-walk-b: "
              "ai-toolkit's documented\n# Qwen-Image quantisation (config/examples/train_lora_qwen_image_24gb.yaml at "
              "beb94824). Not the rung config.\n")
    return header + out


def run_derive(args: argparse.Namespace) -> int:
    if '"' in args.ara_path or not args.ara_path.endswith(".safetensors"):
        refuse("WALK_ARG_INVALID", f"--ara-path {args.ara_path!r} is not a .safetensors path")
        return 2
    try:
        text = derive_walk_b(Path(args.rung_yaml).read_text(encoding="utf-8"), args.ara_path)
    except ValueError as exc:
        refuse("WALK_ARG_INVALID", str(exc))
        return 2
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    return 0


def run_gpu_busy(args: argparse.Namespace) -> int:
    busy, detail = gpu_busy(args.nvidia_smi, args.windows_smi, int(args.max_mib))
    if busy:
        refuse("GPU_BUSY", detail)
        return 3
    print(f"GPU_FREE {detail}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gpu-busy")
    g.add_argument("--nvidia-smi", required=True)
    g.add_argument("--windows-smi", default=None)
    g.add_argument("--max-mib", required=True, type=int)
    s = sub.add_parser("sample")
    s.add_argument("--root-pid", required=True, type=int)
    s.add_argument("--train-log", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--proc", default="/proc")
    s.add_argument("--interval", default=1.0, type=float)
    s.add_argument("--oom-grace-s", required=True, type=float)
    s.add_argument("--mem-floor-gib", required=True, type=float)
    s.add_argument("--wall-s", required=True, type=float)
    m = sub.add_parser("summarize")
    m.add_argument("--host-csv", required=True)
    m.add_argument("--vram-csv", required=True)
    m.add_argument("--train-log", required=True)
    m.add_argument("--stop-file", default=None)
    m.add_argument("--out", required=True)
    d = sub.add_parser("derive-walk-b")
    d.add_argument("--rung-yaml", required=True)
    d.add_argument("--ara-path", required=True)
    d.add_argument("--out", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {"gpu-busy": run_gpu_busy, "sample": run_sample, "summarize": run_summarize,
            "derive-walk-b": run_derive}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
