#!/usr/bin/env python3
"""C2 Colab launcher guards (DESIGN-v3 section 9.2 item 6 — lessons v4k, v4p, v4q).

Provides:
  1. evaluate_wall_guard (v4k: WALL_S and GRACE_S honoured in stub and live modes)
  2. evaluate_cap_guard (v4k: CAP and MARGIN honoured in stub and live modes)
  3. parse_vitals_log & evaluate_vitals_and_stall_guard (v4p: DEAD_HARNESS_TRIPPED on
     cgroup OOM or 2 consecutive phase: run samples with 0 worker procs, STALL_GUARD_TRIPPED on stall)
  4. check_host_ram_projection & run_between_item_fetch (v4q: pre-load cgroup/host RAM
     check against kernel SIGKILL rc=-9, plus between-item fetch before current.json reset)
  5. verify_input_shas & scrub_colab_tokens (pre-open sha256 gate and log token scrubber)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

WORKER_PROC_RE = re.compile(
    r"\b(comfy|main\.py|ai-toolkit|run\.py|llama-server|ollama|lane1_render\.py)\b",
    re.I,
)
OOM_KILL_RE = re.compile(r"\boom_kill\s+([1-9]\d*)\b|\bOut of memory: Killed process\b", re.I)

TOKEN_SCRUB_PATTERNS = [
    (re.compile(r"(colab-runtime-proxy-token=)[^\s&\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(access_token=)[^\s&\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED]"),
    (re.compile(r"\bhf_[A-Za-z0-9]{16,}\b"), "hf_[REDACTED]"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_hex_sha(val: str) -> str:
    s = str(val).strip().lower()
    if s.startswith("sha256:"):
        s = s[7:]
    return s


def verify_input_shas(expected_shas: dict[str, str]) -> dict[str, str]:
    verified: dict[str, str] = {}
    for file_str, exp_raw in expected_shas.items():
        p = Path(file_str)
        if not p.exists():
            raise ValueError(f"REFUSED: INPUT_FILE_MISSING: {p} does not exist")
        exp = normalize_hex_sha(exp_raw)
        got = sha256_file(p)
        if got != exp:
            raise ValueError(
                f"REFUSED: INPUT_SHA_MISMATCH for {p}: got {got}, expected {exp}"
            )
        verified[file_str] = got
    return verified


def scrub_colab_tokens(text: str) -> str:
    out = text
    for pattern, repl in TOKEN_SCRUB_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def scrub_file_in_place(path: Path) -> None:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return
    raw = p.read_text(encoding="utf-8", errors="replace")
    scrubbed = scrub_colab_tokens(raw)
    if scrubbed != raw:
        p.write_text(scrubbed, encoding="utf-8", newline="\n")


def evaluate_wall_guard(
    *,
    mode: str = "live",
    elapsed_s: float,
    wall_s: float = 3000.0,
    grace_s: float = 60.0,
) -> dict[str, Any]:
    threshold_s = round(max(0.0, float(wall_s) - float(grace_s)), 6)
    elapsed_val = round(float(elapsed_s), 6)
    remaining_s = round(threshold_s - elapsed_val, 6)
    tripped = elapsed_val >= threshold_s
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
        round(max(0.0, float(start_balance) - float(current_balance)), 6)
        if start_balance is not None and current_balance is not None
        else 0.0
    )
    rate_est = round(max(0.0, (float(rate_ccu_per_hour) * float(elapsed_s)) / 3600.0), 6)
    spend = round(max(drop, rate_est), 6)
    ceiling = round(max(0.0, float(cap) - float(margin)), 6)
    tripped = spend >= ceiling
    return {
        "mode": mode,
        "tripped": tripped,
        "code": "CAP_GUARD_TRIPPED" if tripped else None,
        "spend_ccu": spend,
        "ceiling_ccu": ceiling,
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
        oom_kill = False
        in_proc = False
        for line in lines[1:]:
            if OOM_KILL_RE.search(line):
                oom_kill = True
            if line.startswith("PROC:"):
                in_proc = True
                continue
            if line.startswith("HARNESS:"):
                in_proc = False
                payload = line[len("HARNESS:") :].strip()
                try:
                    phase = json.loads(payload).get("phase")
                except Exception:
                    m = re.search(r'"phase"\s*:\s*"([^"]+)"', payload) or re.search(
                        r"phase:\s*([a-z0-9_-]+)", payload, re.I
                    )
                    phase = m.group(1) if m else None
                continue
            if in_proc and WORKER_PROC_RE.search(line):
                worker_count += 1
        samples.append(
            {
                "timestamp": ts,
                "phase": phase,
                "worker_proc_count": worker_count,
                "oom_kill": oom_kill,
            }
        )
    return samples


def evaluate_vitals_and_stall_guard(
    *,
    vitals_text: str,
    idle_seconds: float = 0.0,
    stall_s: float = 300.0,
) -> dict[str, Any]:
    samples = parse_vitals_log(vitals_text)
    if samples:
        last = samples[-1]
        if (
            isinstance(last["phase"], str)
            and last["phase"].startswith("run")
            and last["worker_proc_count"] == 0
            and last.get("oom_kill")
        ):
            return {
                "tripped": True,
                "code": "DEAD_HARNESS_TRIPPED",
                "cgroup_oom": True,
                "reason": "cgroup OOM kill detected in phase=run with 0 active worker processes",
                "samples_count": len(samples),
            }
    if len(samples) >= 2:
        last_two = samples[-2:]
        if all(
            isinstance(s["phase"], str) and s["phase"].startswith("run") and s["worker_proc_count"] == 0
            for s in last_two
        ):
            return {
                "tripped": True,
                "code": "DEAD_HARNESS_TRIPPED",
                "cgroup_oom": any(bool(s.get("oom_kill")) for s in last_two),
                "reason": "2 consecutive vitals samples in phase=run with 0 active worker processes",
                "samples_count": len(samples),
            }
    if float(idle_seconds) >= float(stall_s):
        return {
            "tripped": True,
            "code": "STALL_GUARD_TRIPPED",
            "cgroup_oom": False,
            "reason": f"No output row or vitals progress for {idle_seconds}s (stall_s={stall_s}s)",
            "samples_count": len(samples),
        }
    return {
        "tripped": False,
        "code": None,
        "cgroup_oom": False,
        "reason": None,
        "samples_count": len(samples),
    }


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
    projected_mb = round((float(current_anon_mb) + float(projected_delta_mb)) * float(safety_factor), 1)
    if projected_mb > limit_mb:
        raise ValueError(
            f"HOST_RAM_PROJECTION_EXCEEDED: projected {projected_mb:.1f} MB > ceiling {limit_mb:.1f} MB"
        )
    return {"ok": True, "projected_mb": projected_mb, "limit_mb": limit_mb}


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sdlab C2 launcher guards CLI")
    parser.add_argument("--mode", default="stub")
    parser.add_argument("--elapsed-s", type=float, default=0.0)
    parser.add_argument("--wall-s", type=float, default=3000.0)
    parser.add_argument("--grace-s", type=float, default=60.0)
    parser.add_argument("--cap", type=float, default=0.05)
    parser.add_argument("--margin", type=float, default=0.01)
    parser.add_argument("--rate", type=float, default=0.0)
    parser.add_argument("--start-balance", type=float, default=None)
    parser.add_argument("--current-balance", type=float, default=None)
    parser.add_argument("--verify-sha", action="append", default=[], help="Verify PATH=SHA256 before opening window")
    parser.add_argument("--scrub-file", action="append", default=[], help="Scrub Colab/OAuth tokens from file in place")
    parser.add_argument("--vitals-file", type=Path, default=None, help="Evaluate vitals.log and stall guard")
    parser.add_argument("--idle-seconds", type=float, default=0.0)
    parser.add_argument("--stall-s", type=float, default=300.0)
    parser.add_argument("--check-ram", action="store_true", help="Run host/cgroup RAM projection check")
    parser.add_argument("--current-anon-mb", type=float, default=512.0)
    parser.add_argument("--projected-delta-mb", type=float, default=1024.0)
    parser.add_argument("--mem-total-mb", type=float, default=12288.0)
    parser.add_argument("--cgroup-max-mb", type=float, default=None)
    args = parser.parse_args(argv)

    if args.verify_sha:
        pairs: dict[str, str] = {}
        for item in args.verify_sha:
            if "=" not in item:
                print(f"REFUSED: invalid --verify-sha argument {item!r}", file=sys.stderr)
                return 2
            k, v = item.split("=", 1)
            pairs[k] = v
        try:
            verified = verify_input_shas(pairs)
            print(json.dumps({"verified_shas": verified}))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.scrub_file:
        for fpath in args.scrub_file:
            scrub_file_in_place(Path(fpath))
        return 0

    if args.check_ram:
        try:
            res = check_host_ram_projection(
                current_anon_mb=args.current_anon_mb,
                projected_delta_mb=args.projected_delta_mb,
                mem_total_mb=args.mem_total_mb,
                cgroup_max_mb=args.cgroup_max_mb,
            )
            print(json.dumps(res))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.vitals_file is not None:
        txt = args.vitals_file.read_text(encoding="utf-8", errors="replace") if args.vitals_file.exists() else ""
        vit = evaluate_vitals_and_stall_guard(
            vitals_text=txt,
            idle_seconds=args.idle_seconds,
            stall_s=args.stall_s,
        )
        print(json.dumps(vit))
        return 1 if vit["tripped"] else 0

    wall = evaluate_wall_guard(mode=args.mode, elapsed_s=args.elapsed_s, wall_s=args.wall_s, grace_s=args.grace_s)
    cap = evaluate_cap_guard(
        mode=args.mode,
        cap=args.cap,
        margin=args.margin,
        start_balance=args.start_balance,
        current_balance=args.current_balance,
        rate_ccu_per_hour=args.rate,
        elapsed_s=args.elapsed_s,
    )
    print(json.dumps({"wall": wall, "cap": cap}))
    return 1 if (wall["tripped"] or cap["tripped"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
