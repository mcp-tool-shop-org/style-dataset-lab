#!/usr/bin/env python3
"""Lane 3 GPU rung helpers, run on the VM by the remote script's train mode (and rig side by the kit).

Subcommands (each refusal is one `REFUSED: <CODE>: <detail>` line on stderr and exit 1):

  guards        before any model download: a GPU smoke check through the lane's own torch (a timed
                bf16 1024x1024 matmul on cuda plus one bitsandbytes AdamW8bit step,
                GPU_SMOKE_FAILED), free disk on every filesystem holding the HF cache or the
                training folder (DISK_FREE_LOW), host RAM from /proc/meminfo against a threshold
                the request passes in (HOST_RAM_LOW; HOST_RAM_THRESHOLD_MISSING without one), and a
                /dev/shm size record. All measurements are written even when every check passes.
  download      the model snapshot at a pinned revision, unauthenticated unless the request put a
                read token in HF_TOKEN_GGUF_READ (then it is handed to the download child as
                HF_TOKEN, and only `token_used: true` is recorded), with a probe: after the first PROBE_SECONDS or PROBE_BYTES of new bytes,
                whichever comes first, the full download time is projected from the measured
                rate and the download is stopped with DOWNLOAD_TOO_SLOW when the projection
                exceeds the request's limit (DOWNLOAD_LIMIT_MISSING without one).
  dataset       verify the fixture images against rung-dataset.json (sha256) and, on the VM,
                place them with their captions (DATASET_FILE_MISSING, DATASET_SHA_MISMATCH).
  render-job    fill the rung YAML's __LANE3_*__ placeholders (JOB_TEMPLATE_INVALID).
  copy-off      while ai-toolkit runs, copy each finished checkpoint and sample image into the
                bundle directory and append a manifest line with its sha256.
  finish        gather the train-mode records into lane3_out/train_facts.json (and, after a
                failure, into vm_window.json) so the bundle carries them either way.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

GIB = 1024**3
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
PLACEHOLDERS = ("__LANE3_TRAINING_FOLDER__", "__LANE3_DATASET_DIR__", "__LANE3_MODEL_PATH__")
COPY_OFF_SUFFIXES = (".safetensors", ".png", ".jpg", ".jpeg", ".webp")


class Refusal(Exception):
    """A named refusal: printed as `REFUSED: <code>: <detail>`."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def refuse_line(code: str, detail: str) -> str:
    return f"REFUSED: {code}: {detail}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def parse_positive_number(raw: str | None, code: str, name: str) -> float:
    """A required positive number from the request; missing or malformed is the named refusal."""
    if raw is None or not str(raw).strip():
        raise Refusal(code, f"{name} is not set; the request must set it (there is no default)")
    try:
        val = float(str(raw).strip())
    except ValueError:
        raise Refusal(code, f"{name}={raw!r} is not a number") from None
    if not val > 0 or val != val or val == float("inf"):
        raise Refusal(code, f"{name}={raw!r} must be a positive number")
    return val


# ---------------------------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------------------------


def parse_meminfo(text: str) -> dict[str, int]:
    """Bytes for each `Key: <n> kB` line of /proc/meminfo."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"^(\w+):\s+(\d+)\s*kB\s*$", line.strip())
        if m:
            out[m.group(1)] = int(m.group(2)) * 1024
    return out


def measure_host_ram(meminfo_text: str, required_gib: float) -> dict[str, Any]:
    mem = parse_meminfo(meminfo_text)
    total = mem.get("MemTotal")
    avail = mem.get("MemAvailable")
    rec: dict[str, Any] = {
        "mem_total_bytes": total,
        "mem_available_bytes": avail,
        "mem_total_gib": round(total / GIB, 2) if total is not None else None,
        "mem_available_gib": round(avail / GIB, 2) if avail is not None else None,
        "required_available_gib": required_gib,
        "ok": bool(avail is not None and avail >= required_gib * GIB),
    }
    return rec


def measure_disk(paths: Iterable[Path], required_gib: float, usage_fn: Callable[[str], Any] = shutil.disk_usage,
                 dev_fn: Callable[[str], int] | None = None) -> dict[str, Any]:
    """Free bytes on every distinct filesystem holding one of `paths` (nearest existing ancestor)."""
    dev_fn = dev_fn or (lambda p: os.stat(p).st_dev)
    seen: dict[int, dict[str, Any]] = {}
    for p in paths:
        probe = Path(p)
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        dev = dev_fn(str(probe))
        if dev in seen:
            seen[dev]["paths"].append(str(p))
            continue
        usage = usage_fn(str(probe))
        seen[dev] = {
            "paths": [str(p)],
            "measured_at": str(probe),
            "free_bytes": int(usage.free),
            "total_bytes": int(usage.total),
            "free_gib": round(usage.free / GIB, 2),
        }
    filesystems = list(seen.values())
    ok = all(fs["free_bytes"] >= required_gib * GIB for fs in filesystems)
    return {"required_free_gib": required_gib, "filesystems": filesystems, "ok": ok}


def measure_shm(shm_path: Path, usage_fn: Callable[[str], Any] = shutil.disk_usage) -> dict[str, Any]:
    try:
        usage = usage_fn(str(shm_path))
    except OSError as exc:
        return {"path": str(shm_path), "error": str(exc)}
    return {
        "path": str(shm_path),
        "total_bytes": int(usage.total),
        "free_bytes": int(usage.free),
        "total_gib": round(usage.total / GIB, 2),
    }


def query_driver(run: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    try:
        res = run(
            ["nvidia-smi", "--query-gpu=driver_version,name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": str(exc)}
    line = (res.stdout or "").strip().splitlines()[:1]
    if res.returncode != 0 or not line:
        return {"error": f"nvidia-smi rc={res.returncode}"}
    parts = [p.strip() for p in line[0].split(",")]
    return {
        "driver_version": parts[0] if parts else None,
        "nvidia_smi_name": parts[1] if len(parts) > 1 else None,
        "memory_total": parts[2] if len(parts) > 2 else None,
    }


def gpu_smoke(torch_mod: Any = None, bnb_mod: Any = None, clock: Callable[[], float] = time.perf_counter,
              target_s: float = 5.0) -> dict[str, Any]:
    """A timed bf16 1024x1024 matmul loop on cuda (about target_s seconds), then one
    bitsandbytes AdamW8bit step on a 1024x1024 bf16 Parameter. Raises on any failure."""
    if torch_mod is None:
        import torch as torch_mod  # noqa: PLC0415 - imported on the VM only
    if bnb_mod is None:
        import bitsandbytes as bnb_mod  # noqa: PLC0415
    rec: dict[str, Any] = {
        "torch_version": getattr(torch_mod, "__version__", None),
        "torch_cuda": getattr(getattr(torch_mod, "version", None), "cuda", None),
        "bitsandbytes_version": getattr(bnb_mod, "__version__", None),
    }
    if not torch_mod.cuda.is_available():
        raise RuntimeError("torch.cuda.is_available() is False")
    dev = torch_mod.device("cuda")
    rec["device_name"] = torch_mod.cuda.get_device_name(0)
    a = torch_mod.randn(1024, 1024, device=dev, dtype=torch_mod.bfloat16)
    b = torch_mod.randn(1024, 1024, device=dev, dtype=torch_mod.bfloat16)
    torch_mod.cuda.synchronize()
    start = clock()
    iters = 0
    while True:
        c = a @ b
        iters += 1
        if iters % 64 == 0:
            torch_mod.cuda.synchronize()
            if clock() - start >= target_s:
                break
    torch_mod.cuda.synchronize()
    elapsed = clock() - start
    if not bool(torch_mod.isfinite(c).all()):
        raise RuntimeError("matmul result is not finite")
    rec.update({"matmul_iters": iters, "matmul_seconds": round(elapsed, 3),
                "matmul_tflops": round(iters * 2 * 1024**3 / max(elapsed, 1e-9) / 1e12, 2)})
    param = torch_mod.nn.Parameter(torch_mod.randn(1024, 1024, device=dev, dtype=torch_mod.bfloat16))
    before = param.detach().clone()
    loss = (param.float() ** 2).mean()
    loss.backward()
    opt = bnb_mod.optim.AdamW8bit([param], lr=1e-3)
    opt.step()
    torch_mod.cuda.synchronize()
    changed = bool((param.detach() != before).any())
    if not changed:
        raise RuntimeError("AdamW8bit step left the parameter unchanged")
    rec["adamw8bit_step"] = "ok"
    return rec


def run_guards(args: argparse.Namespace, *, smoke_fn: Callable[..., dict[str, Any]] = gpu_smoke,
               driver_fn: Callable[[], dict[str, Any]] = query_driver,
               disk_usage_fn: Callable[[str], Any] = shutil.disk_usage) -> int:
    out_path = Path(args.out)
    rec: dict[str, Any] = {}
    refusals: list[tuple[str, str]] = []

    try:
        ram_required = parse_positive_number(args.ram_required_gib, "HOST_RAM_THRESHOLD_MISSING", "LANE3_HOST_RAM_REQUIRED_GIB")
    except Refusal as exc:
        ram_required = None
        refusals.append((exc.code, exc.detail))

    gpu: dict[str, Any] = dict(driver_fn())
    try:
        gpu.update(smoke_fn(target_s=float(args.smoke_seconds)))
        gpu["ok"] = True
    except Exception as exc:  # noqa: BLE001 - every failure is the one named refusal
        gpu["ok"] = False
        gpu["error"] = f"{type(exc).__name__}: {exc}".splitlines()[0]
        refusals.append(("GPU_SMOKE_FAILED", gpu["error"]))
    rec["gpu"] = gpu

    disk = measure_disk([Path(args.hf_home), Path(args.training_folder)], float(args.disk_required_gib), disk_usage_fn)
    rec["disk"] = disk
    if not disk["ok"]:
        low = [fs for fs in disk["filesystems"] if fs["free_bytes"] < float(args.disk_required_gib) * GIB]
        refusals.append(("DISK_FREE_LOW", "; ".join(
            f"{fs['measured_at']} free {fs['free_gib']} GiB < {args.disk_required_gib} GiB" for fs in low)))

    meminfo_text = Path(args.meminfo).read_text(encoding="utf-8", errors="replace")
    ram = measure_host_ram(meminfo_text, ram_required if ram_required is not None else 0.0)
    if ram_required is None:
        ram["required_available_gib"] = None
        ram["ok"] = False
    elif not ram["ok"]:
        refusals.append(("HOST_RAM_LOW", f"MemAvailable {ram['mem_available_gib']} GiB < required {ram_required} GiB "
                                         f"(MemTotal {ram['mem_total_gib']} GiB)"))
    rec["host_ram"] = ram
    rec["shm"] = measure_shm(Path(args.shm), disk_usage_fn)
    rec["refusals"] = [code for code, _ in refusals]
    write_json(out_path, rec)
    print("TRAIN_GUARDS " + json.dumps(rec), flush=True)
    for code, detail in refusals:
        print(refuse_line(code, detail), file=sys.stderr, flush=True)
    return 1 if refusals else 0


# ---------------------------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------------------------

DOWNLOAD_CHILD = (
    "import os, sys\n"
    "from huggingface_hub import snapshot_download\n"
    "path = snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], token=os.environ.get('HF_TOKEN') or False)\n"
    "print('SNAPSHOT_PATH ' + path, flush=True)\n"
)


def repo_cache_dir(hf_home: Path, repo_id: str) -> Path:
    return hf_home / "hub" / ("models--" + repo_id.replace("/", "--"))


def dir_bytes(path: Path) -> int:
    """Apparent bytes of regular files under `path` (blobs and in-progress .incomplete files)."""
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            try:
                if not os.path.islink(fp):
                    total += os.stat(fp).st_size
            except OSError:
                continue
    return total


def expected_repo_bytes(repo_id: str, revision: str, token: str | None = None) -> int:
    from huggingface_hub import HfApi  # noqa: PLC0415 - VM venv only

    info = HfApi().model_info(repo_id, revision=revision, files_metadata=True, token=token or False)
    return sum(int(s.size or 0) for s in (info.siblings or []))


def evaluate_probe(new_bytes: int, elapsed_s: float, remaining_bytes: int, max_seconds: float) -> dict[str, Any]:
    """Project the time for the bytes still to come from the probe's rate."""
    rate = new_bytes / elapsed_s if elapsed_s > 0 else 0.0
    if remaining_bytes <= 0:
        projected = 0.0
    else:
        projected = (remaining_bytes / rate) if rate > 0 else float("inf")
    return {
        "probe_bytes": new_bytes,
        "probe_seconds": round(elapsed_s, 2),
        "probe_rate_mb_s": round(rate / 1e6, 2),
        "projected_total_seconds": None if projected == float("inf") else round(projected, 1),
        "max_seconds": max_seconds,
        "too_slow": projected > max_seconds,
    }


def count_throttle_signals(lines: Iterable[str]) -> dict[str, int]:
    http_429 = 0
    retries = 0
    for line in lines:
        if re.search(r"\b429\b", line):
            http_429 += 1
        if re.search(r"(?i)\bretr(y|ying|ies)\b", line):
            retries += 1
    return {"http_429_lines": http_429, "retry_lines": retries}


def run_download(args: argparse.Namespace, *, expected_fn: Callable[..., int] = expected_repo_bytes,
                 popen: Callable[..., Any] = subprocess.Popen, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> int:
    out_path = Path(args.out)
    # A read token only when the request put one in HF_TOKEN_GGUF_READ; its value is never written.
    token = os.environ.get("HF_TOKEN_GGUF_READ") or None
    rec: dict[str, Any] = {"repo_id": args.repo, "revision": args.revision, "token_used": token is not None}
    try:
        max_seconds = parse_positive_number(args.max_seconds, "DOWNLOAD_LIMIT_MISSING", "LANE3_DOWNLOAD_MAX_SECONDS")
        if not REPO_ID_RE.match(args.repo or ""):
            raise Refusal("TRAIN_MODEL_REQUIRED", f"{args.repo!r} is not a Hugging Face repo id")
        if not REVISION_RE.match(args.revision or ""):
            raise Refusal("TRAIN_MODEL_REVISION_REQUIRED", f"{args.revision!r} is not a 40-hex commit")
    except Refusal as exc:
        rec["refusal"] = exc.code
        write_json(out_path, rec)
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1

    hf_home = Path(args.hf_home)
    cache = repo_cache_dir(hf_home, args.repo)
    expected = int(expected_fn(args.repo, args.revision, token))
    baseline = dir_bytes(cache)
    remaining = max(expected - baseline, 0)
    rec.update({"expected_bytes": expected, "cached_bytes_at_start": baseline, "max_seconds": max_seconds,
                "probe_window": {"seconds": float(args.probe_seconds), "bytes": int(args.probe_bytes)}})

    env = {k: v for k, v in os.environ.items()
           if k not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HF_TOKEN_GGUF_READ")}
    env.update({"HF_HOME": str(hf_home), "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "PYTHONUNBUFFERED": "1"})
    if token is not None:
        env["HF_TOKEN"] = token
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = clock()
    with log_path.open("w", encoding="utf-8", newline="\n") as log_fh:
        proc = popen([sys.executable, "-c", DOWNLOAD_CHILD, args.repo, args.revision],
                     stdout=log_fh, stderr=subprocess.STDOUT, env=env)
        probe: dict[str, Any] | None = None
        last_print = start
        while proc.poll() is None:
            sleep(float(args.poll_s))
            now = clock()
            elapsed = now - start
            new_bytes = max(dir_bytes(cache) - baseline, 0)
            if now - last_print >= 10:
                last_print = now
                print(f"MODEL_DOWNLOAD_PROGRESS bytes={new_bytes} seconds={elapsed:.0f}", flush=True)
            if probe is None and (elapsed >= float(args.probe_seconds) or new_bytes >= int(args.probe_bytes)):
                probe = evaluate_probe(new_bytes, elapsed, remaining, max_seconds)
                print("MODEL_DOWNLOAD_PROBE " + json.dumps(probe), flush=True)
                if probe["too_slow"]:
                    proc.kill()
                    proc.wait()
                    break
        rc = proc.wait()
    elapsed = clock() - start
    log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    new_bytes = max(dir_bytes(cache) - baseline, 0)
    rec.update({
        "downloaded_bytes": new_bytes,
        "seconds": round(elapsed, 2),
        "rate_mb_s": round(new_bytes / elapsed / 1e6, 2) if elapsed > 0 else None,
        "probe": probe,
        **count_throttle_signals(log_lines),
    })
    snapshot = next((ln.split(" ", 1)[1].strip() for ln in log_lines if ln.startswith("SNAPSHOT_PATH ")), None)
    rec["snapshot_path"] = snapshot
    refusal: tuple[str, str] | None = None
    if probe is not None and probe["too_slow"]:
        refusal = ("DOWNLOAD_TOO_SLOW", f"probe {probe['probe_rate_mb_s']} MB/s over {probe['probe_seconds']} s projects "
                                        f"{probe['projected_total_seconds']} s for {remaining} bytes > limit {max_seconds} s")
    elif rc != 0 or not snapshot:
        tail = " | ".join(log_lines[-3:])
        refusal = ("MODEL_DOWNLOAD_FAILED", f"snapshot_download rc={rc}: {tail}")
    if refusal:
        rec["refusal"] = refusal[0]
    write_json(out_path, rec)
    print("MODEL_DOWNLOAD " + json.dumps(rec), flush=True)
    if refusal:
        print(refuse_line(*refusal), file=sys.stderr, flush=True)
        return 1
    return 0


# ---------------------------------------------------------------------------------------------
# dataset and job
# ---------------------------------------------------------------------------------------------


def run_dataset(args: argparse.Namespace) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    src = Path(args.src)
    dest = Path(args.dest) if args.dest else None
    items = manifest.get("items", [])
    if not items:
        print(refuse_line("DATASET_FILE_MISSING", f"{args.manifest} lists no items"), file=sys.stderr, flush=True)
        return 1
    for item in items:
        img = src / item["image"]
        if not img.is_file():
            print(refuse_line("DATASET_FILE_MISSING", str(img)), file=sys.stderr, flush=True)
            return 1
        got = sha256_file(img)
        if got != item["sha256"]:
            print(refuse_line("DATASET_SHA_MISMATCH", f"{img} sha256={got} expected={item['sha256']}"),
                  file=sys.stderr, flush=True)
            return 1
    if dest is not None:
        dest.mkdir(parents=True, exist_ok=True)
        for item in items:
            shutil.move(str(src / item["image"]), str(dest / item["image"]))
            stem = Path(item["image"]).stem
            (dest / f"{stem}.txt").write_text(item["caption"].strip() + "\n", encoding="utf-8", newline="\n")
    print(f"DATASET_OK items={len(items)} placed={'yes' if dest else 'no'}", flush=True)
    return 0


def run_render_job(args: argparse.Namespace) -> int:
    text = Path(args.template).read_text(encoding="utf-8")
    values = {
        "__LANE3_TRAINING_FOLDER__": args.training_folder,
        "__LANE3_DATASET_DIR__": args.dataset_dir,
        "__LANE3_MODEL_PATH__": args.model_path,
    }
    for key in PLACEHOLDERS:
        if text.count(f'"{key}"') != 1:
            print(refuse_line("JOB_TEMPLATE_INVALID", f"{args.template} must hold \"{key}\" exactly once"),
                  file=sys.stderr, flush=True)
            return 1
        val = values[key] or ""
        if not val or '"' in val or "\\" in val or "\n" in val:
            print(refuse_line("JOB_TEMPLATE_INVALID", f"value for {key} is empty or not a plain path"),
                  file=sys.stderr, flush=True)
            return 1
        text = text.replace(f'"{key}"', json.dumps(val))
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"JOB_RENDERED {args.out}", flush=True)
    return 0


# ---------------------------------------------------------------------------------------------
# copy-off and finish
# ---------------------------------------------------------------------------------------------


def copy_off_once(watch: Path, bundle: Path, manifest: Path, state: dict[str, Any], *, final: bool = False) -> int:
    """Copy each output file whose size held still since the last pass (or every file, on the final
    pass) into bundle/<relative path>, once, appending a manifest line with its sha256."""
    pending: dict[str, int] = state.setdefault("pending", {})
    done: set[str] = state.setdefault("done", set())
    copied = 0
    if not watch.is_dir():
        return 0
    for fp in sorted(watch.rglob("*")):
        if not fp.is_file() or fp.suffix.lower() not in COPY_OFF_SUFFIXES:
            continue
        rel = fp.relative_to(watch).as_posix()
        if rel in done or any(part.startswith("_") for part in Path(rel).parts[:-1]):
            continue
        size = fp.stat().st_size
        if not final and pending.get(rel) != size:
            pending[rel] = size
            continue
        dest = bundle / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fp, dest)
        line = {"path": rel, "bytes": size, "sha256": sha256_file(dest),
                "copied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with manifest.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(line) + "\n")
        print("COPY_OFF " + json.dumps(line), flush=True)
        done.add(rel)
        copied += 1
    return copied


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def run_copy_off(args: argparse.Namespace, *, alive: Callable[[int], bool] = pid_alive,
                 sleep: Callable[[float], None] = time.sleep) -> int:
    watch, bundle, manifest = Path(args.watch), Path(args.bundle), Path(args.manifest)
    bundle.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {}
    train_log = Path(args.train_log) if args.train_log else None
    last_log = -1
    while alive(int(args.pid)):
        copy_off_once(watch, bundle, manifest, state)
        if train_log is not None and train_log.exists():
            size = train_log.stat().st_size
            if size != last_log:
                last_log = size
                print(f"RUNG_PROGRESS train_log_bytes={size}", flush=True)
        sleep(float(args.interval))
    copy_off_once(watch, bundle, manifest, state, final=True)
    return 0


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run_finish(args: argparse.Namespace) -> int:
    out = Path(args.lane3_out)
    manifest_lines = []
    mp = out / "rung_outputs" / "manifest.jsonl"
    if mp.exists():
        for ln in mp.read_text(encoding="utf-8").splitlines():
            try:
                manifest_lines.append(json.loads(ln))
            except ValueError:
                continue
    download = read_json(out / "model_download.json")
    facts = {
        "hf_token_used": bool(download.get("token_used")) if isinstance(download, dict) else False,
        "train_guards": read_json(out / "train_guards.json"),
        "model_download": download,
        "rung_outputs": {
            "manifest": "rung_outputs/manifest.jsonl" if mp.exists() else None,
            "checkpoints": [m["path"] for m in manifest_lines if m["path"].endswith(".safetensors")],
            "samples": [m["path"] for m in manifest_lines if not m["path"].endswith(".safetensors")],
        },
    }
    write_json(out / "train_facts.json", facts)
    if args.failed_rc is not None:
        base = read_json(out / "vm_window.json") or {}
        base.update({"lane3_mode": "train", "train": "failed", "train_exit_code": int(args.failed_rc), **facts})
        write_json(out / "vm_window.json", base)
        print("WINDOW_JSON " + json.dumps(base), flush=True)
    return 0


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("guards")
    g.add_argument("--hf-home", required=True)
    g.add_argument("--training-folder", required=True)
    g.add_argument("--disk-required-gib", required=True, type=float)
    g.add_argument("--smoke-seconds", required=True, type=float)
    g.add_argument("--ram-required-gib", default=None)
    g.add_argument("--meminfo", default="/proc/meminfo")
    g.add_argument("--shm", default="/dev/shm")
    g.add_argument("--out", required=True)

    d = sub.add_parser("download")
    d.add_argument("--repo", required=True)
    d.add_argument("--revision", default=None)
    d.add_argument("--hf-home", required=True)
    d.add_argument("--max-seconds", default=None)
    d.add_argument("--probe-seconds", required=True, type=float)
    d.add_argument("--probe-bytes", required=True, type=int)
    d.add_argument("--poll-s", default=1.0, type=float)
    d.add_argument("--log", required=True)
    d.add_argument("--out", required=True)

    ds = sub.add_parser("dataset")
    ds.add_argument("--manifest", required=True)
    ds.add_argument("--src", required=True)
    ds.add_argument("--dest", default=None, help="place images and captions here; omit to verify only")

    r = sub.add_parser("render-job")
    r.add_argument("--template", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--training-folder", required=True)
    r.add_argument("--dataset-dir", required=True)
    r.add_argument("--model-path", required=True)

    c = sub.add_parser("copy-off")
    c.add_argument("--watch", required=True)
    c.add_argument("--bundle", required=True)
    c.add_argument("--manifest", required=True)
    c.add_argument("--pid", required=True, type=int)
    c.add_argument("--train-log", default=None)
    c.add_argument("--interval", default=10.0, type=float)

    f = sub.add_parser("finish")
    f.add_argument("--lane3-out", required=True)
    f.add_argument("--failed-rc", default=None, type=int)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "guards": run_guards,
        "download": run_download,
        "dataset": run_dataset,
        "render-job": run_render_job,
        "copy-off": run_copy_off,
        "finish": run_finish,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
