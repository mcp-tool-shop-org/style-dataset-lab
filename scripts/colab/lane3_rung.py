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
  model-check   rig side, before a window opens: the model at the pinned revision answers the
                request's read token (MODEL_AUTH_FAILED, MODEL_REVISION_NOT_FOUND,
                MODEL_METADATA_FAILED; the same names for the VM's metadata call).
  bundle-now    the kit's failure path after a rig-side kill: stop the VM-side rung, sweep the
                training folder, write the failure record and tar lane3_out.
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
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

GIB = 1024**3
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
PLACEHOLDERS = ("__LANE3_TRAINING_FOLDER__", "__LANE3_DATASET_DIR__", "__LANE3_MODEL_PATH__")
COPY_OFF_SUFFIXES = (".safetensors", ".png", ".jpg", ".jpeg", ".webp")
HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")
BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")


def scrub_secrets(text: str) -> str:
    """Remove every Hugging Face token and every bearer value from text that is printed (exec
    output reaches the CLI history)."""
    return BEARER_RE.sub("Bearer [REDACTED]", HF_TOKEN_RE.sub("hf_[REDACTED]", text))


def safetensors_complete(path: Path) -> bool:
    """True when the file's header parses and its size is exactly 8 + header + the end of the last
    tensor's data offsets; a checkpoint copied while it was still being written fails this."""
    import struct  # noqa: PLC0415

    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            raw = fh.read(8)
            if len(raw) != 8:
                return False
            (n,) = struct.unpack("<Q", raw)
            if n <= 0 or 8 + n > size:
                return False
            header = json.loads(fh.read(n).decode("utf-8"))
        ends = [int(v["data_offsets"][1]) for k, v in header.items() if k != "__metadata__"]
        return size == 8 + n + (max(ends) if ends else 0)
    except (OSError, ValueError, KeyError, TypeError, IndexError, UnicodeDecodeError):
        return False


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


def classify_hub_error(exc: BaseException) -> tuple[str, str]:
    """Name a failed model-metadata call: a bad or expired token (401/403, gated) is MODEL_AUTH_FAILED,
    an unknown revision (404 on the revision) MODEL_REVISION_NOT_FOUND, anything else (network,
    5xx, a repo that is missing) MODEL_METADATA_FAILED. The message never carries the token."""
    name = type(exc).__name__
    status = getattr(getattr(exc, "response", None), "status_code", None)
    status = status if isinstance(status, int) else getattr(exc, "code", None)
    # The detail is the status code and a fixed message only: never the exception's text, which can
    # echo the request (and so the token).
    http = str(status) if isinstance(status, int) else "none"
    if "RevisionNotFound" in name or (status == 404 and "revision" in str(exc).lower()):
        return "MODEL_REVISION_NOT_FOUND", f"the pinned revision was not found (http={http})"
    if status in (401, 403) or "Gated" in name:
        return "MODEL_AUTH_FAILED", f"the read token was refused (http={http})"
    return "MODEL_METADATA_FAILED", f"the model metadata call failed (http={http})"


HF_API_BASE = "https://huggingface.co"


def check_model_api(repo_id: str, revision: str, token: str | None, *, base: str = HF_API_BASE,
                    opener: Callable[..., Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Rig-side check before a window opens: the model at the pinned revision is reachable with the
    request's read token (stdlib only; the token goes in a header, never in argv or a URL)."""
    import urllib.error  # noqa: PLC0415
    import urllib.parse  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    url = f"{base.rstrip('/')}/api/models/{repo_id}/revision/{revision}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    if opener is None:
        origin = urllib.parse.urlsplit(url).netloc

        class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
            # urllib copies every header but Content-* onto a redirect (urllib/request.py:647-649),
            # the bearer token included, whatever the new host is: refuse a cross-host redirect.
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
                if urllib.parse.urlsplit(newurl).netloc != origin:
                    raise urllib.error.HTTPError(newurl, code, "cross-host redirect refused", headers, fp)
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(_SameHostRedirects).open
    try:
        with opener(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        if exc.code in (401, 403):
            raise Refusal("MODEL_AUTH_FAILED", f"{repo_id}@{revision}: http={exc.code}") from None
        if exc.code == 404:
            code = "MODEL_REVISION_NOT_FOUND" if re.search(r"\brev(ision)?\b", body, re.I) else "MODEL_METADATA_FAILED"
            raise Refusal(code, f"{repo_id}@{revision}: http=404") from None
        raise Refusal("MODEL_METADATA_FAILED", f"{repo_id}@{revision}: http={exc.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Refusal("MODEL_METADATA_FAILED", f"{repo_id}@{revision}: {type(exc).__name__}") from None
    if data.get("sha") != revision:
        raise Refusal("MODEL_REVISION_NOT_FOUND", f"{repo_id}: the API answered sha {data.get('sha')!r}")
    return {"repo_id": repo_id, "revision": revision, "ok": True}


def run_model_check(args: argparse.Namespace) -> int:
    token = os.environ.get("HF_TOKEN_GGUF_READ") or None
    base = os.environ.get("SDLAB_TEST_HF_ENDPOINT") or HF_API_BASE
    try:
        rec = check_model_api(args.repo, args.revision, token, base=base)
    except Refusal as exc:
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1
    print("MODEL_CHECK_OK " + json.dumps(rec), flush=True)
    return 0


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


def _fail(out_path: Path, rec: dict[str, Any], code: str, detail: str) -> int:
    rec["refusal"] = code
    write_json(out_path, rec)
    print("MODEL_DOWNLOAD " + json.dumps(rec), flush=True)
    print(refuse_line(code, detail), file=sys.stderr, flush=True)
    return 1


def run_download(args: argparse.Namespace, *, expected_fn: Callable[..., int] = expected_repo_bytes,
                 popen: Callable[..., Any] = subprocess.Popen, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> int:
    out_path = Path(args.out)
    # A read token only when the request put one in HF_TOKEN_GGUF_READ; its value is never written.
    token = os.environ.get("HF_TOKEN_GGUF_READ") or None
    offline = os.environ.get("HF_HUB_OFFLINE") == "1"
    # Whether a token was used is read from the variable's presence, not from its value.
    rec: dict[str, Any] = {"repo_id": args.repo, "revision": args.revision,
                           "token_used": "HF_TOKEN_GGUF_READ" in os.environ, "offline": offline}
    try:
        max_seconds = parse_positive_number(args.max_seconds, "DOWNLOAD_LIMIT_MISSING", "LANE3_DOWNLOAD_MAX_SECONDS")
        if not REPO_ID_RE.match(args.repo or ""):
            raise Refusal("TRAIN_MODEL_REQUIRED", f"{args.repo!r} is not a Hugging Face repo id")
        if not REVISION_RE.match(args.revision or ""):
            raise Refusal("TRAIN_MODEL_REVISION_REQUIRED", f"{args.revision!r} is not a 40-hex commit")
    except Refusal as exc:
        return _fail(out_path, rec, exc.code, exc.detail)

    hf_home = Path(args.hf_home)
    cache = repo_cache_dir(hf_home, args.repo)
    baseline = dir_bytes(cache)
    if offline:
        # Hub offline (the rig walks): only the cache is read, so there is nothing to project.
        expected = baseline
    else:
        try:
            expected = int(expected_fn(args.repo, args.revision, token))
        except Exception as exc:  # noqa: BLE001 - every metadata failure is one named refusal
            code, detail = classify_hub_error(exc)
            return _fail(out_path, rec, code, f"model_info {args.repo}@{args.revision}: {detail}")
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
    hard_stop = threading.Event()
    with log_path.open("w", encoding="utf-8", newline="\n") as log_fh:
        proc = popen([sys.executable, "-c", DOWNLOAD_CHILD, args.repo, args.revision],
                     stdout=log_fh, stderr=subprocess.STDOUT, env=env)

        # The hard limit lives in its own thread: it kills the child at max_seconds even when the
        # loop below is busy, and a stalled download that still prints lines cannot outlive it.
        def _hard_limit() -> None:
            if proc.poll() is None:
                hard_stop.set()
                proc.kill()

        timer = threading.Timer(max_seconds, _hard_limit)
        timer.daemon = True
        timer.start()
        probe: dict[str, Any] | None = None
        last_print = start
        try:
            while proc.poll() is None:
                sleep(float(args.poll_s))
                now = clock()
                elapsed = now - start
                new_bytes = max(dir_bytes(cache) - baseline, 0)
                if now - last_print >= 10:
                    last_print = now
                    print(f"MODEL_DOWNLOAD_PROGRESS bytes={new_bytes} seconds={elapsed:.0f}", flush=True)
                if not offline and probe is None and (elapsed >= float(args.probe_seconds) or new_bytes >= int(args.probe_bytes)):
                    probe = evaluate_probe(new_bytes, elapsed, remaining, max_seconds)
                    print("MODEL_DOWNLOAD_PROBE " + json.dumps(probe), flush=True)
                    if probe["too_slow"]:
                        proc.kill()
                        proc.wait()
                        break
            rc = proc.wait()
        finally:
            timer.cancel()
    elapsed = clock() - start
    log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    new_bytes = max(dir_bytes(cache) - baseline, 0)
    rec.update({
        "downloaded_bytes": new_bytes,
        "seconds": round(elapsed, 2),
        "rate_mb_s": round(new_bytes / elapsed / 1e6, 2) if elapsed > 0 else None,
        "probe": probe,
        "hard_limit_hit": hard_stop.is_set(),
        **count_throttle_signals(log_lines),
    })
    snapshot = next((ln.split(" ", 1)[1].strip() for ln in log_lines if ln.startswith("SNAPSHOT_PATH ")), None)
    rec["snapshot_path"] = snapshot
    if hard_stop.is_set():
        return _fail(out_path, rec, "DOWNLOAD_TOO_SLOW",
                     f"hard limit: the download was still running after {max_seconds} s ({new_bytes} bytes)")
    if probe is not None and probe["too_slow"]:
        return _fail(out_path, rec, "DOWNLOAD_TOO_SLOW",
                     f"probe {probe['probe_rate_mb_s']} MB/s over {probe['probe_seconds']} s projects "
                     f"{probe['projected_total_seconds']} s for {remaining} bytes > limit {max_seconds} s")
    if rc != 0 or not snapshot:
        tail = scrub_secrets(" | ".join(log_lines[-3:]))
        if token is not None and token in tail:
            tail = "[the download log tail is withheld: it held the read token]"
        return _fail(out_path, rec, "MODEL_DOWNLOAD_FAILED", f"snapshot_download rc={rc}: {tail}")
    write_json(out_path, rec)
    print("MODEL_DOWNLOAD " + json.dumps(rec), flush=True)
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
    pass) into bundle/<relative path>, once, appending a manifest line with its sha256. A file that
    vanishes or cannot be read is logged (COPY_OFF_SKIPPED) and retried next pass, never fatal."""
    pending: dict[str, int] = state.setdefault("pending", {})
    done: set[str] = state.setdefault("done", set())
    copied = 0
    if not watch.is_dir():
        return 0
    for fp in sorted(watch.rglob("*")):
        try:
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
            line = {"path": rel, "bytes": dest.stat().st_size, "sha256": sha256_file(dest),
                    "copied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            if rel.endswith(".safetensors"):
                line["partial"] = not safetensors_complete(dest)
            with manifest.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(line) + "\n")
            print("COPY_OFF " + json.dumps(line), flush=True)
            done.add(rel)
            copied += 1
        except OSError as exc:
            print(f"COPY_OFF_SKIPPED {fp.name}: {type(exc).__name__}: {exc}", flush=True)
            continue
    return copied


def load_done(manifest: Path) -> set[str]:
    done: set[str] = set()
    if manifest.exists():
        for ln in manifest.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(ln)["path"])
            except (ValueError, KeyError, TypeError):
                continue
    return done


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
    # Files a previous copy-off already took (a crashed watcher, the final sweep) are not copied twice.
    state: dict[str, Any] = {"done": load_done(manifest)}
    final_only = bool(getattr(args, "final_only", False))
    if not final_only and int(args.pid) <= 0:
        print("copy-off needs --pid <trainer pid> unless --final-only", file=sys.stderr, flush=True)
        return 2
    if not final_only:
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


def run_checkpoint(args: argparse.Namespace) -> int:
    """Print the bundle path of the newest complete checkpoint the manifest lists (exit 1 if none)."""
    good = []
    mp = Path(args.manifest)
    if mp.exists():
        for ln in mp.read_text(encoding="utf-8").splitlines():
            try:
                m = json.loads(ln)
            except ValueError:
                continue
            if m.get("path", "").endswith(".safetensors") and not m.get("partial") and m.get("bytes", 0) > 0:
                good.append(m["path"])
    if not good:
        return 1
    print(str(Path(args.bundle) / sorted(good)[-1]), flush=True)
    return 0


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
            "checkpoints": [m["path"] for m in manifest_lines
                            if m["path"].endswith(".safetensors") and not m.get("partial")],
            "partial_checkpoints": [m["path"] for m in manifest_lines
                                    if m["path"].endswith(".safetensors") and m.get("partial")],
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
# bundle-now (the kit's failure path, after a rig-side kill)
# ---------------------------------------------------------------------------------------------

BUNDLE_NAME = "lane3_stub_bundle.tar.gz"


def rung_pids(root: Path, proc: Path = Path("/proc"), skip: Iterable[int] = ()) -> list[int]:
    """Processes of the rung on this VM: the remote script (and its subshells), ai-toolkit's run.py
    and the lane3_rung.py helpers, found by their command lines under `root`."""
    marks = (f"{root}/remote_lane3_stub.sh", f"{root}/ai-toolkit/run.py", f"{root}/lane3_rung.py copy-off",
             f"{root}/lane3_rung.py download")
    skip_set = set(skip)
    found = []
    for entry in proc.iterdir() if proc.is_dir() else []:
        if not entry.name.isdigit() or int(entry.name) in skip_set:
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")
        except OSError:
            continue
        if any(m in cmd for m in marks):
            found.append(int(entry.name))
    return found


def run_bundle_now(args: argparse.Namespace, *, kill: Callable[[int, int], None] = os.kill,
                   proc: Path = Path("/proc")) -> int:
    """After the kit killed its exec (wall, cap, stall, dead harness), the VM-side script is still
    running and its EXIT trap never fires. Stop it (SIGKILL, so no trap races this), sweep the
    training folder into the bundle directory, write the failure record, scrub, and tar lane3_out."""
    import signal  # noqa: PLC0415

    root = Path(args.content)
    out = root / "lane3_out"
    bundle = root / BUNDLE_NAME
    pids = rung_pids(root, proc, skip=(os.getpid(), os.getppid()))
    for pid in pids:
        try:
            kill(pid, signal.SIGKILL)
        except OSError:
            continue
    if not pids and bundle.is_file() and bundle.stat().st_size > 0:
        print(f"BUNDLE_NOW: the remote script already bundled {bundle}", flush=True)
        return 0
    if not out.is_dir():
        print(f"BUNDLE_NOW: no {out} on this VM; nothing to bundle", flush=True)
        return 1
    time.sleep(float(args.settle_s))
    rung_dir = out / "rung_outputs"
    rung_dir.mkdir(parents=True, exist_ok=True)
    manifest = rung_dir / "manifest.jsonl"
    copy_off_once(root / "lane3_train", rung_dir, manifest, {"done": load_done(manifest)}, final=True)
    run_finish(argparse.Namespace(lane3_out=str(out), failed_rc=int(args.rc)))
    guards = root / "launch_guards.py"
    for f in out.rglob("*"):
        if f.is_file() and f.suffix in (".log", ".json", ".jsonl", ".txt") and guards.is_file():
            subprocess.run([sys.executable, str(guards), "--scrub-file", str(f)], check=False,
                           stdin=subprocess.DEVNULL)
    bundle.unlink(missing_ok=True)
    import tarfile  # noqa: PLC0415

    with tarfile.open(bundle, "w:gz") as tf:
        tf.add(str(out), arcname=".")
    print(f"BUNDLE_NOW: killed {len(pids)} rung process(es) and bundled {bundle}", flush=True)
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
    c.add_argument("--pid", default=0, type=int)
    c.add_argument("--final-only", action="store_true", help="one final sweep, no watching")
    c.add_argument("--train-log", default=None)
    c.add_argument("--interval", default=10.0, type=float)

    mc = sub.add_parser("model-check")
    mc.add_argument("--repo", required=True)
    mc.add_argument("--revision", required=True)

    ck = sub.add_parser("checkpoint")
    ck.add_argument("--bundle", required=True)
    ck.add_argument("--manifest", required=True)

    bn = sub.add_parser("bundle-now")
    bn.add_argument("--content", required=True)
    bn.add_argument("--rc", required=True, type=int)
    bn.add_argument("--settle-s", default=2.0, type=float)

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
        "model-check": run_model_check,
        "bundle-now": run_bundle_now,
        "checkpoint": run_checkpoint,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
