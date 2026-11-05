#!/usr/bin/env python3
"""C2 Colab launcher guards (DESIGN-v3 section 9.2 item 6 — lessons v4k, v4p, v4q).

Provides:
  1. evaluate_wall_guard (v4k: WALL_S and GRACE_S honoured in stub and live modes)
  2. evaluate_cap_guard (v4k: CAP and MARGIN honoured in stub and live modes)
  3. parse_vitals_log & evaluate_vitals_and_stall_guard (v4p: DEAD_HARNESS_TRIPPED on
     2 consecutive phase: run samples with 0 worker procs, STALL_GUARD_TRIPPED on stall)
  4. check_host_ram_projection & run_between_item_fetch (v4q: pre-load cgroup/host RAM
     check against kernel SIGKILL rc=-9, plus between-item fetch before current.json reset)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

WORKER_PROC_RE = re.compile(r"\b(comfy|main\.py|ai-toolkit|run\.py|llama-server|ollama|lane1_render\.py)\b", re.I)


def evaluate_wall_guard(
    *,
    mode: str = "live",
    elapsed_s: float,
    wall_s: float = 3000.0,
    grace_s: float = 60.0,
) -> dict[str, Any]:
    threshold_s = max(0.0, float(wall_s) - float(grace_s))
    remaining_s = threshold_s - float(elapsed_s)
    tripped = float(elapsed_s) >= threshold_s
    return {
        "mode": mode,
        "tripped": tripped,
        "code": "WALL_GUARD_TRIPPED" if tripped else None,
        "remaining_s": remaining_s,
        "threshold_s": threshold_s,
    }


def evaluate_cap_guard(
    *,
    mode: str = "live",
    cap: float = 0.05,
    margin: float = 0.01,
    start_balance: float | None = None,
    current_balance: float | None = None,
    rate_ccu_per_hour: float = 0.0,
    elapsed_s: float = 0.0,
) -> dict[str, Any]:
    drop = (
        max(0.0, float(start_balance) - float(current_balance))
        if start_balance is not None and current_balance is not None
        else 0.0
    )
    rate_est = max(0.0, (float(rate_ccu_per_hour) * float(elapsed_s)) / 3600.0)
    spend = max(drop, rate_est)
    ceiling = max(0.0, float(cap) - float(margin))
    tripped = spend >= ceiling
    return {
        "mode": mode,
        "tripped": tripped,
        "code": "CAP_GUARD_TRIPPED" if tripped else None,
        "spend_ccu": round(spend, 6),
        "ceiling_ccu": round(ceiling, 6),
    }


def parse_vitals_log(vitals_text: str) -> list[dict[str, Any]]:
    blocks = [b.strip() for b in re.split(r"^===\s*VITALS\s+", vitals_text, flags=re.M) if b.strip()]
    samples: list[dict[str, Any]] = []
    for block in blocks:
        lines = block.splitlines()
        header = lines[0] if lines else ""
        ts = header.split()[0] if header else ""
        phase = None
        worker_count = 0
        in_proc = False
        for line in lines[1:]:
            if line.startswith("PROC:"):
                in_proc = True
                continue
            if line.startswith("HARNESS:"):
                in_proc = False
                payload = line[len("HARNESS:") :].strip()
                try:
                    phase = json.loads(payload).get("phase")
                except Exception:
                    m = re.search(r'"phase"\s*:\s*"([^"]+)"', payload) or re.search(r"phase:\s*([a-z0-9_-]+)", payload, re.I)
                    phase = m.group(1) if m else None
                continue
            if in_proc and WORKER_PROC_RE.search(line):
                worker_count += 1
        samples.append({"timestamp": ts, "phase": phase, "worker_proc_count": worker_count})
    return samples


def evaluate_vitals_and_stall_guard(
    *,
    vitals_text: str,
    idle_seconds: float = 0.0,
    stall_s: float = 300.0,
) -> dict[str, Any]:
    samples = parse_vitals_log(vitals_text)
    if len(samples) >= 2:
        last_two = samples[-2:]
        if all(isinstance(s["phase"], str) and s["phase"].startswith("run") and s["worker_proc_count"] == 0 for s in last_two):
            return {
                "tripped": True,
                "code": "DEAD_HARNESS_TRIPPED",
                "reason": "2 consecutive vitals samples in phase=run with 0 active worker processes",
                "samples_count": len(samples),
            }
    if float(idle_seconds) >= float(stall_s):
        return {
            "tripped": True,
            "code": "STALL_GUARD_TRIPPED",
            "reason": f"No output row or vitals progress for {idle_seconds}s (stall_s={stall_s}s)",
            "samples_count": len(samples),
        }
    return {"tripped": False, "code": None, "reason": None, "samples_count": len(samples)}


def check_host_ram_projection(
    *,
    current_anon_mb: float,
    projected_delta_mb: float,
    mem_total_mb: float,
    cgroup_max_mb: float | None = None,
    safety_factor: float = 1.05,
) -> dict[str, Any]:
    limits = [float(mem_total_mb)]
    if cgroup_max_mb is not None:
        limits.append(float(cgroup_max_mb))
    limit_mb = min(limits)
    projected_mb = (float(current_anon_mb) + float(projected_delta_mb)) * float(safety_factor)
    if projected_mb > limit_mb:
        raise ValueError(
            f"HOST_RAM_PROJECTION_EXCEEDED: projected {projected_mb:.1f} MB > ceiling {limit_mb:.1f} MB"
        )
    return {"ok": True, "projected_mb": round(projected_mb, 1), "limit_mb": limit_mb}


def run_between_item_fetch(
    *,
    remote_dir: Path,
    local_dir: Path,
    next_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    local_dir.mkdir(parents=True, exist_ok=True)
    current_json = remote_dir / "current.json"
    copied: list[str] = []
    previous_item = None
    if current_json.exists():
        previous_item = json.loads(current_json.read_text(encoding="utf-8"))
        for rel in previous_item.get("files") or []:
            src = remote_dir / rel
            if src.exists():
                dst = local_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(rel)
        shutil.copy2(current_json, local_dir / "current.json")
    if next_item is not None:
        current_json.write_text(json.dumps(next_item, indent=2) + "\n", encoding="utf-8")
    return {"copied_files": copied, "previous_item": previous_item}


def main() -> int:
    parser = argparse.ArgumentParser(description="sdlab C2 launcher guards CLI")
    parser.add_argument("--mode", default="stub")
    parser.add_argument("--elapsed-s", type=float, default=0.0)
    parser.add_argument("--wall-s", type=float, default=3000.0)
    parser.add_argument("--grace-s", type=float, default=60.0)
    parser.add_argument("--cap", type=float, default=0.05)
    parser.add_argument("--margin", type=float, default=0.01)
    parser.add_argument("--rate", type=float, default=0.21)
    args = parser.parse_args()

    wall = evaluate_wall_guard(mode=args.mode, elapsed_s=args.elapsed_s, wall_s=args.wall_s, grace_s=args.grace_s)
    cap = evaluate_cap_guard(mode=args.mode, cap=args.cap, margin=args.margin, rate_ccu_per_hour=args.rate, elapsed_s=args.elapsed_s)
    print(json.dumps({"wall": wall, "cap": cap}))
    return 1 if (wall["tripped"] or cap["tripped"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
