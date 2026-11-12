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
  dataset       verify the dataset images against their manifest (sha256), optionally pack a
                deterministic tar archive on the rig before `colab new`, and on the VM verify the
                archive sha256 + every extracted image sha256 and place captions
                (DATASET_MANIFEST_MISSING, DATASET_MANIFEST_SHA_MISMATCH, DATASET_MANIFEST_INVALID,
                DATASET_ARCHIVE_SHA_MISMATCH, DATASET_FILE_MISSING, DATASET_SHA_MISMATCH).
  check-job     rig side, before a window opens: verify the job YAML's sha256, pinned 40-hex base
                model revision, active `__LANE3_*__` placeholders, pinned 40-hex + cleared-licence
                hub references across metadata string values, refusal of runtime `config.*` hub refs
                ai-toolkit@beb94824 cannot parse (`qtype`, `assistant_lora_path`, `vae_path`, etc.),
                save/sample cadences, trigger_word vs cache_text_embeddings compatibility, and
                explicit caption_dropout_rate + source
                (JOB_FILE_MISSING, JOB_SHA_MISMATCH, TRAIN_MODEL_REVISION_REQUIRED,
                JOB_TEMPLATE_INVALID, JOB_UNPINNED_HUB_REF, JOB_MODEL_LICENCE_NOT_ALLOWED,
                JOB_UNSUPPORTED_HUB_REF, JOB_SAVE_CADENCE_INVALID, JOB_SAMPLE_CADENCE_INVALID,
                JOB_TRIGGER_WITH_CACHED_EMBEDDINGS, JOB_CAPTION_DROPOUT_INVALID).
  plan-run      rig side, before a window opens: resolve and verify keep-all bundle projection
                (checkpoints + optimizer state + samples/logs/config + auxiliary keep-all files),
                bundle download timeout + salvage part count, dataset archive upload timeout,
                job-derived wall allowance, and projected VM output disk budget including chunked
                download split overhead (DOWNLOAD_TIMEOUT_INVALID, DOWNLOAD_TIMEOUT_REQUIRED,
                DOWNLOAD_TIMEOUT_TOO_SHORT, UPLOAD_TIMEOUT_INVALID, UPLOAD_TIMEOUT_TOO_SHORT,
                TRAIN_STEP_TIME_REQUIRED, TRAIN_WALL_TOO_SHORT, TRAIN_OUTPUT_PROJECTION_REQUIRED,
                OPTIMIZER_SIZE_SOURCE_REQUIRED, TRAIN_OUTPUT_DISK_LOW).
  render-job    verify (when --template-sha is given) and fill the job YAML's __LANE3_*__
                placeholders (JOB_FILE_MISSING, JOB_SHA_MISMATCH, JOB_TEMPLATE_INVALID).
  copy-off      while ai-toolkit runs (and on final sweep), copy every file in the training folder
                (checkpoints, optimizer state, resolved config, loss/other logs, samples, and `_*`
                subdirectories) into the bundle directory and append a manifest line with its sha256.
  check-output-disk   VM side, before run.py: verify projected training output fits free disk.
  write-train-manifest VM side, after run.py and before final copy-off: record relative path,
                bytes, and sha256 of every file in the training folder.
  check-bundle-disk   VM side, before tar: verify lane3_out total bytes fit free disk.
  verify-bundle rig side, after colab download: verify every file in training_folder_manifest.json
                arrived in rung_outputs/ with matching byte count and sha256, enumerating all
                missing and mismatched files (TRAIN_OUTPUT_MANIFEST_MISMATCH).
  repair-bundle rig side, after per-file VM refetch on verify-bundle failure: merge recovered
                training-folder files into rung_outputs/ and manifest.jsonl inside the bundle tar.
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
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

GIB = 1024**3
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_IMAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
PLACEHOLDERS = ("__LANE3_TRAINING_FOLDER__", "__LANE3_DATASET_DIR__", "__LANE3_MODEL_PATH__")
SAMPLE_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_UPLOAD_FLOOR_MB_S = 1.0
DEFAULT_UPLOAD_CHUNK_BYTES = 33_554_432
DEFAULT_DOWNLOAD_CHUNK_BYTES = 268_435_456
DEFAULT_OUTPUT_COPY_TAR_OVERHEAD = 3.0
DEFAULT_VM_DISK_BUDGET_GIB = 75.0
# Cleared SPDX model and LoRA repositories matching lib/model-licences.js (G4, §5.2-§5.3).
LANE3_MODEL_LICENCE_ALLOWLIST: dict[str, dict[str, str]] = {
    "Qwen/Qwen-Image": {
        "spdx_id": "Apache-2.0",
        "url": "https://github.com/QwenLM/Qwen-Image/blob/main/LICENSE",
    },
    "Qwen/Qwen2.5-VL-7B-Instruct": {
        "spdx_id": "Apache-2.0",
        "url": "https://github.com/QwenLM/Qwen2.5-VL/blob/main/LICENSE",
    },
    "Qwen/Qwen2.5-VL-32B-Instruct": {
        "spdx_id": "Apache-2.0",
        "url": "https://github.com/QwenLM/Qwen2.5-VL/blob/main/LICENSE",
    },
    "Qwen/Qwen3-VL-30B-A3B-Instruct": {
        "spdx_id": "Apache-2.0",
        "url": "https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Instruct/blob/main/LICENSE",
    },
    "black-forest-labs/FLUX.2-klein-4B": {
        "spdx_id": "Apache-2.0",
        "url": "https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md",
    },
    "black-forest-labs/FLUX.2-klein-base-4B": {
        "spdx_id": "Apache-2.0",
        "url": "https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md",
    },
    "mcp-tool-shop/portlight-ships-anatomy": {
        "spdx_id": "MIT",
        "url": "https://huggingface.co/mcp-tool-shop/portlight-ships-anatomy-lora",
    },
    "mcp-tool-shop/portlight-ships-anatomy-lora": {
        "spdx_id": "MIT",
        "url": "https://huggingface.co/mcp-tool-shop/portlight-ships-anatomy-lora",
    },
}
HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")
BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")


def mask_log_text(text: str) -> str:
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

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        missing_files: list[str] | None = None,
        mismatched_files: list[str] | None = None,
        bad_entries: list[dict[str, Any]] | None = None,
        checked_files: int = 0,
    ) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.missing_files = list(missing_files) if missing_files is not None else []
        self.mismatched_files = list(mismatched_files) if mismatched_files is not None else []
        self.bad_entries = list(bad_entries) if bad_entries is not None else []
        self.checked_files = int(checked_files)


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
    # A label from a fixed table, so nothing of the failed call's own data reaches the message.
    http = {401: "401", 403: "403", 404: "404", 429: "429", 500: "500", 502: "502", 503: "503"}.get(
        status if isinstance(status, int) else -1, "other")
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
        tail = mask_log_text(" | ".join(log_lines[-3:]))
        if token is not None and token in tail:
            tail = "[the download log tail is withheld: it held the read token]"
        return _fail(out_path, rec, "MODEL_DOWNLOAD_FAILED", f"snapshot_download rc={rc}: {tail}")
    write_json(out_path, rec)
    print("MODEL_DOWNLOAD " + json.dumps(rec), flush=True)
    return 0


# ---------------------------------------------------------------------------------------------
# dataset and job
# ---------------------------------------------------------------------------------------------


def normalize_sha256(raw: str | None, code: str, label: str) -> str:
    s = (raw or "").strip().lower()
    if s.startswith("sha256:"):
        s = s[7:]
    if not HEX64_RE.match(s):
        raise Refusal(code, f"{label}={raw!r} is not a 64-hex sha256")
    return s


def _validate_manifest_items(manifest_path: Path, manifest: Any) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("items", []), list):
        raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path} must be a JSON object with an items list")
    items = manifest.get("items", [])
    if not items:
        raise Refusal("DATASET_FILE_MISSING", f"{manifest_path} lists no items")
    seen_names: set[str] = set()
    seen_stems: set[str] = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path} item[{idx}] is not an object")
        img_name = item.get("image")
        sha_raw = item.get("sha256")
        caption = item.get("caption")
        if not isinstance(img_name, str) or not SAFE_IMAGE_NAME_RE.match(img_name):
            raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path} item[{idx}].image={img_name!r} is not a plain filename")
        suffix = Path(img_name).suffix.lower()
        stem = Path(img_name).stem
        if not suffix or suffix == ".txt":
            raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path} item[{idx}].image={img_name!r} needs an image suffix")
        if img_name in seen_names or stem in seen_stems:
            raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path} duplicate image or caption stem {img_name!r}")
        if not isinstance(sha_raw, str) or not HEX64_RE.match(sha_raw.lower()):
            raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path} item[{idx}].sha256={sha_raw!r} is not 64-hex")
        if not isinstance(caption, str):
            raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path} item[{idx}].caption must be a string")
        seen_names.add(img_name)
        seen_stems.add(stem)
    return items


def pack_dataset_archive(src: Path, items: list[dict[str, Any]], archive_path: Path) -> str:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w") as tf:
        for item in items:
            img = src / item["image"]
            info = tarfile.TarInfo(name=item["image"])
            info.size = img.stat().st_size
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with img.open("rb") as fh:
                tf.addfile(info, fh)
    return sha256_file(archive_path)


def unpack_and_verify_dataset_archive(
    archive_path: Path, expected_archive_sha: str | None, items: list[dict[str, Any]], dest: Path
) -> str:
    if not archive_path.is_file():
        raise Refusal("DATASET_FILE_MISSING", str(archive_path))
    exp_sha = normalize_sha256(expected_archive_sha, "DATASET_ARCHIVE_SHA_MISMATCH", "archive_sha")
    got_sha = sha256_file(archive_path)
    if got_sha != exp_sha:
        raise Refusal("DATASET_ARCHIVE_SHA_MISMATCH", f"{archive_path} sha256={got_sha} expected={exp_sha}")
    expected_names = {it["image"] for it in items}
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:") as tf:
            members = tf.getmembers()
            seen_members: set[str] = set()
            for m in members:
                if not m.isfile() or not SAFE_IMAGE_NAME_RE.match(m.name) or m.name not in expected_names or m.name in seen_members:
                    raise Refusal("DATASET_ARCHIVE_SHA_MISMATCH", f"unexpected tar member {m.name!r} in {archive_path}")
                seen_members.add(m.name)
            missing = sorted(expected_names - seen_members)
            if missing:
                raise Refusal("DATASET_FILE_MISSING", f"{missing[0]} missing from {archive_path}")
            for m in members:
                src_fh = tf.extractfile(m)
                if src_fh is None:
                    raise Refusal("DATASET_FILE_MISSING", f"{m.name} unreadable in {archive_path}")
                with src_fh, (dest / m.name).open("wb") as dst_fh:
                    shutil.copyfileobj(src_fh, dst_fh)
    except (tarfile.TarError, OSError) as exc:
        raise Refusal("DATASET_ARCHIVE_SHA_MISMATCH", f"{archive_path}: {type(exc).__name__}: {exc}") from None
    for item in items:
        placed = dest / item["image"]
        if not placed.is_file():
            raise Refusal("DATASET_FILE_MISSING", str(placed))
        got_item = sha256_file(placed)
        if got_item != item["sha256"].lower():
            raise Refusal("DATASET_SHA_MISMATCH", f"{placed} sha256={got_item} expected={item['sha256']}")
        stem = Path(item["image"]).stem
        (dest / f"{stem}.txt").write_text(item["caption"].strip() + "\n", encoding="utf-8", newline="\n")
    return got_sha


def run_dataset(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest_sha = getattr(args, "manifest_sha", None)
    src_raw = getattr(args, "src", None)
    dest_raw = getattr(args, "dest", None)
    pack_raw = getattr(args, "pack_archive", None)
    sha_out_raw = getattr(args, "archive_sha_out", None)
    archive_raw = getattr(args, "archive", None)
    archive_sha = getattr(args, "archive_sha", None)
    unlink_archive = bool(getattr(args, "unlink_archive", False))
    try:
        if not manifest_path.is_file():
            raise Refusal("DATASET_MANIFEST_MISSING", str(manifest_path))
        if manifest_sha is not None:
            exp_msha = normalize_sha256(manifest_sha, "DATASET_MANIFEST_SHA_MISMATCH", "manifest_sha")
            got_msha = sha256_file(manifest_path)
            if got_msha != exp_msha:
                raise Refusal("DATASET_MANIFEST_SHA_MISMATCH", f"{manifest_path} sha256={got_msha} expected={exp_msha}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise Refusal("DATASET_MANIFEST_INVALID", f"{manifest_path}: invalid JSON ({exc})") from None
        items = _validate_manifest_items(manifest_path, manifest)

        if archive_raw is not None:
            if not dest_raw:
                raise Refusal("DATASET_MANIFEST_INVALID", "--archive requires --dest")
            arch_sha = unpack_and_verify_dataset_archive(Path(archive_raw), archive_sha, items, Path(dest_raw))
            if unlink_archive:
                Path(archive_raw).unlink(missing_ok=True)
            print(f"DATASET_OK items={len(items)} placed=yes archive_sha256={arch_sha}", flush=True)
            return 0

        if not src_raw:
            raise Refusal("DATASET_FILE_MISSING", "dataset needs --src or --archive")
        src = Path(src_raw)
        dest = Path(dest_raw) if dest_raw else None
        for item in items:
            img = src / item["image"]
            if not img.is_file():
                raise Refusal("DATASET_FILE_MISSING", str(img))
            got = sha256_file(img)
            if got != item["sha256"].lower():
                raise Refusal("DATASET_SHA_MISMATCH", f"{img} sha256={got} expected={item['sha256']}")
        arch_sha_out: str | None = None
        if pack_raw is not None:
            arch_sha_out = pack_dataset_archive(src, items, Path(pack_raw))
            if sha_out_raw is not None:
                sha_p = Path(sha_out_raw)
                sha_p.parent.mkdir(parents=True, exist_ok=True)
                sha_p.write_text(arch_sha_out + "\n", encoding="utf-8", newline="\n")
        if dest is not None:
            dest.mkdir(parents=True, exist_ok=True)
            for item in items:
                shutil.move(str(src / item["image"]), str(dest / item["image"]))
                stem = Path(item["image"]).stem
                (dest / f"{stem}.txt").write_text(item["caption"].strip() + "\n", encoding="utf-8", newline="\n")
        extra = f" archive_sha256={arch_sha_out}" if arch_sha_out else ""
        print(f"DATASET_OK items={len(items)} placed={'yes' if dest else 'no'}{extra}", flush=True)
        return 0
    except Refusal as exc:
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1


def validate_job_template(template_path: Path, text: str, *, strict_bindings: bool = False) -> None:
    active_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    active_text = "\n".join(active_lines)
    for key in PLACEHOLDERS:
        if text.count(f'"{key}"') != 1:
            raise Refusal("JOB_TEMPLATE_INVALID", f'{template_path} must hold "{key}" exactly once')
        if active_text.count(f'"{key}"') != 1 or active_text.count(key) != 1:
            raise Refusal("JOB_TEMPLATE_INVALID", f'{template_path} must hold "{key}" once as an active quoted value')
    if strict_bindings:
        expected_bindings = (
            ("training_folder", "__LANE3_TRAINING_FOLDER__"),
            ("folder_path", "__LANE3_DATASET_DIR__"),
            ("name_or_path", "__LANE3_MODEL_PATH__"),
        )
        for field, placeholder in expected_bindings:
            pat = rf'^\s*(?:-\s*)?{field}:\s*"{placeholder}"\s*(?:#.*)?$'
            if len(re.findall(pat, active_text, re.M)) != 1:
                raise Refusal("JOB_TEMPLATE_INVALID", f'{template_path} must bind {field}: "{placeholder}" once')
        for m in re.finditer(r"^\s*(?:-\s*)?([A-Za-z0-9_]*name_or_path):\s*(.+?)\s*$", active_text, re.M):
            key_name, raw_val = m.group(1), re.sub(r"\s+#.*$", "", m.group(2)).strip()
            if key_name != "name_or_path" or raw_val != '"__LANE3_MODEL_PATH__"':
                raise Refusal(
                    "JOB_TEMPLATE_INVALID",
                    f"{template_path} has unpinned model path {key_name}: {raw_val} (must use __LANE3_MODEL_PATH__)",
                )


HUB_URL_RE = re.compile(r"(?:https?://|hf://)\S+|huggingface\.co/\S+", re.I)
PINNED_HF_RESOLVE_URL_RE = re.compile(
    r"^https?://huggingface\.co/([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"/(?:resolve|blob|tree)/([0-9a-f]{40})(?:/[^\s]*)?$",
    re.I,
)
PINNED_HF_AT_URL_RE = re.compile(
    r"^(?:https?://huggingface\.co/|hf://)([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"@([0-9a-f]{40})(?:/[^\s]*)?$",
    re.I,
)
PINNED_HUB_SPEC_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)@([0-9a-f]{40})(?:/[^\s]*)?$"
)


def _strip_yaml_comment(raw: str) -> str:
    in_single = False
    in_double = False
    idx = 0
    while idx < len(raw):
        ch = raw[idx]
        if ch == "'" and not in_double:
            if in_single and idx + 1 < len(raw) and raw[idx + 1] == "'":
                idx += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single:
            if in_double and idx > 0 and raw[idx - 1] == "\\":
                idx += 1
                continue
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (idx == 0 or raw[idx - 1].isspace()):
            return raw[:idx].rstrip()
        idx += 1
    return raw.rstrip()


def _split_top_level_commas(inner: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    in_single = False
    in_double = False
    depth = 0
    idx = 0
    while idx < len(inner):
        ch = inner[idx]
        if ch == "'" and not in_double:
            if in_single and idx + 1 < len(inner) and inner[idx + 1] == "'":
                cur.append("''")
                idx += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single:
            if not (in_double and idx > 0 and inner[idx - 1] == "\\"):
                in_double = not in_double
        elif not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}" and depth > 0:
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
                idx += 1
                continue
        cur.append(ch)
        idx += 1
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _split_yaml_kv(line: str) -> tuple[str, str] | None:
    stripped = _strip_yaml_comment(line)
    in_single = False
    in_double = False
    for idx, ch in enumerate(stripped):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            if idx == 0 or stripped[idx - 1] != "\\":
                in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            if idx + 1 == len(stripped) or stripped[idx + 1].isspace():
                raw_key = stripped[:idx].strip()
                val_rest = stripped[idx + 1 :].strip()
                if len(raw_key) >= 2 and raw_key[0] == raw_key[-1] and raw_key[0] in ("'", '"'):
                    raw_key = raw_key[1:-1]
                if re.match(r"^[A-Za-z0-9_.-]+$", raw_key):
                    return raw_key, val_rest
                return None
    return None


def _parse_yaml_scalar(raw: str) -> Any:
    s = _strip_yaml_comment(raw).strip()
    if s == "" or s in ("null", "Null", "NULL", "~"):
        return None
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return json.loads(s)
        except ValueError:
            return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_parse_yaml_scalar(item) for item in _split_top_level_commas(inner)] if inner else []
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        if not inner:
            return {}
        out: dict[str, Any] = {}
        for item in _split_top_level_commas(inner):
            kv = _split_yaml_kv(item)
            if kv is not None:
                out[kv[0]] = _parse_yaml_scalar(kv[1])
        return out
    if re.match(r"^[+-]?\d+$", s):
        return int(s)
    if re.match(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+[eE][+-]?\d+|\d+\.\d*[eE][+-]?\d+)$", s):
        val = float(s)
        if math.isfinite(val):
            return val
    return s


def parse_job_yaml(text: str, template_path: Path = Path("<job.yaml>")) -> dict[str, Any]:
    """Stdlib indentation-aware YAML subset parser for ai-toolkit job configs (no PyYAML required)."""
    lines: list[tuple[int, str, int]] = []
    for lno, raw in enumerate(text.splitlines(), start=1):
        clean = raw.rstrip("\r")
        stripped = clean.lstrip(" \t")
        if "\t" in clean[: len(clean) - len(stripped)]:
            raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}:{lno}: tabs are not valid YAML indentation")
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(clean) - len(stripped)
        lines.append((indent, stripped, lno))
    if not lines:
        raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}: YAML document is empty")

    def _parse_sequence(idx: int, seq_indent: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        while idx < len(lines):
            ind, content, _lno = lines[idx]
            if ind != seq_indent or not (content == "-" or content.startswith("- ")):
                break
            rest = content[1:].lstrip(" ")
            idx += 1
            if rest == "":
                if idx < len(lines) and lines[idx][0] > seq_indent:
                    child, idx = _parse_node(idx)
                    items.append(child)
                else:
                    items.append(None)
                continue
            kv = _split_yaml_kv(rest)
            if kv is not None:
                k, v_rest = kv
                item_dict: dict[str, Any] = {}
                first_key_indent = seq_indent + 2
                if v_rest != "":
                    item_dict[k] = _parse_yaml_scalar(v_rest)
                elif idx < len(lines) and (
                    lines[idx][0] > first_key_indent
                    or (
                        lines[idx][0] == first_key_indent
                        and (lines[idx][1] == "-" or lines[idx][1].startswith("- "))
                    )
                ):
                    child, idx = _parse_node(idx)
                    item_dict[k] = child
                else:
                    item_dict[k] = None
                if idx < len(lines) and lines[idx][0] > seq_indent and not (
                    lines[idx][1] == "-" or lines[idx][1].startswith("- ")
                ):
                    more, idx = _parse_mapping(idx, lines[idx][0])
                    item_dict.update(more)
                items.append(item_dict)
                continue
            parts = [_strip_yaml_comment(rest).strip()]
            if not parts[0].startswith(('"', "'", "[", "{")):
                while idx < len(lines) and lines[idx][0] > seq_indent:
                    cont = _strip_yaml_comment(lines[idx][1]).strip()
                    if cont:
                        parts.append(cont)
                    idx += 1
                items.append(_parse_yaml_scalar(" ".join(p for p in parts if p)))
            else:
                items.append(_parse_yaml_scalar(parts[0]))
        return items, idx

    def _parse_mapping(idx: int, map_indent: int) -> tuple[dict[str, Any], int]:
        out: dict[str, Any] = {}
        while idx < len(lines):
            ind, content, lno = lines[idx]
            if ind < map_indent:
                break
            if ind > map_indent:
                raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}:{lno}: unexpected indentation ({ind} > {map_indent})")
            if content == "-" or content.startswith("- "):
                break
            kv = _split_yaml_kv(content)
            if kv is None:
                raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}:{lno}: invalid YAML mapping line {content!r}")
            k, v_rest = kv
            idx += 1
            if v_rest != "":
                if not v_rest.startswith(('"', "'", "[", "{")):
                    parts = [_strip_yaml_comment(v_rest).strip()]
                    while (
                        idx < len(lines)
                        and lines[idx][0] > map_indent
                        and _split_yaml_kv(lines[idx][1]) is None
                        and not (lines[idx][1] == "-" or lines[idx][1].startswith("- "))
                    ):
                        cont = _strip_yaml_comment(lines[idx][1]).strip()
                        if cont:
                            parts.append(cont)
                        idx += 1
                    out[k] = _parse_yaml_scalar(" ".join(p for p in parts if p))
                else:
                    out[k] = _parse_yaml_scalar(v_rest)
            elif idx < len(lines) and (
                lines[idx][0] > map_indent
                or (lines[idx][0] == map_indent and (lines[idx][1] == "-" or lines[idx][1].startswith("- ")))
            ):
                child, idx = _parse_node(idx)
                out[k] = child
            else:
                out[k] = None
        return out, idx

    def _parse_node(idx: int) -> tuple[Any, int]:
        ind, content, _lno = lines[idx]
        if content == "-" or content.startswith("- "):
            return _parse_sequence(idx, ind)
        return _parse_mapping(idx, ind)

    root, next_idx = _parse_node(0)
    if next_idx < len(lines):
        _ind, content, lno = lines[next_idx]
        raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}:{lno}: trailing unparsed YAML content {content!r}")
    if not isinstance(root, dict):
        raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}: top-level YAML value must be a mapping")
    return root


def _iter_yaml_strings(node: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(node, dict):
        for k, v in node.items():
            sub = f"{prefix}.{k}" if prefix else str(k)
            yield from _iter_yaml_strings(v, sub)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            yield from _iter_yaml_strings(item, f"{prefix}[{idx}]")
    elif isinstance(node, str):
        yield prefix, node


def _require_allowed_repo(repo_id: str, context: str) -> None:
    if repo_id not in LANE3_MODEL_LICENCE_ALLOWLIST:
        raise Refusal(
            "JOB_MODEL_LICENCE_NOT_ALLOWED",
            f"{context}: {repo_id!r} is not on the kit's cleared model licence allow-list "
            f"(allowed: {', '.join(sorted(LANE3_MODEL_LICENCE_ALLOWLIST))})",
        )


AI_TOOLKIT_PIN_REF = "ostris/ai-toolkit@beb94824c51480a04d3c86c718603676fdef6938"
_CONFIG_HUB_REF_CITATIONS: dict[str, str] = {
    "qtype": (
        f"{AI_TOOLKIT_PIN_REF} toolkit/config_modules.py:752-753 splits qtype on '|' into "
        "accuracy_recovery_adapter and toolkit/util/quantize.py:527-540 calls hf_hub_download(repo_id, "
        "filename=...) without parsing '@<40hex>' revisions (and run.py runs under HF_HUB_OFFLINE=1)"
    ),
    "accuracy_recovery_adapter": (
        f"{AI_TOOLKIT_PIN_REF} toolkit/config_modules.py:752-753 and toolkit/util/quantize.py:527-540 "
        "call hf_hub_download(repo_id, filename=...) without parsing '@<40hex>' revisions "
        "(and run.py runs under HF_HUB_OFFLINE=1)"
    ),
    "assistant_lora_path": (
        f"{AI_TOOLKIT_PIN_REF} toolkit/config_modules.py:662, toolkit/stable_diffusion_model.py:775-784,1147-1148 "
        "and toolkit/assistant_lora.py:16 call hf_hub_download/safetensors.torch.load_file without parsing "
        "'@<40hex>' revisions (and run.py runs under HF_HUB_OFFLINE=1)"
    ),
    "inference_lora_path": (
        f"{AI_TOOLKIT_PIN_REF} toolkit/config_modules.py:663 and toolkit/stable_diffusion_model.py:775-784 "
        "call hf_hub_download without parsing '@<40hex>' revisions (and run.py runs under HF_HUB_OFFLINE=1)"
    ),
    "lora_path": (
        f"{AI_TOOLKIT_PIN_REF} toolkit/config_modules.py:664 and toolkit/stable_diffusion_model.py:775-784 "
        "call hf_hub_download without parsing '@<40hex>' revisions (and run.py runs under HF_HUB_OFFLINE=1)"
    ),
    "vae_path": (
        f"{AI_TOOLKIT_PIN_REF} toolkit/config_modules.py:656, toolkit/util/vae.py:4-18 "
        "(AutoencoderKL.from_pretrained(vae_path)) and extensions_built_in/diffusion_models/flux2/flux2_model.py:150-171 "
        "do not parse '@<40hex>' revisions (and run.py runs under HF_HUB_OFFLINE=1)"
    ),
}


def _refuse_if_runtime_config_hub_ref(template_path: Path, key_path: str, val: str) -> None:
    if not (key_path == "config" or key_path.startswith("config.")):
        return
    leaf = key_path.rsplit(".", 1)[-1]
    leaf = re.sub(r"\[\d+\]$", "", leaf)
    citation = _CONFIG_HUB_REF_CITATIONS.get(
        leaf,
        (
            f"{AI_TOOLKIT_PIN_REF} (toolkit/config_modules.py:656,662,752-753; "
            "toolkit/util/quantize.py:527-540; toolkit/stable_diffusion_model.py:775-784; "
            "toolkit/util/vae.py:4-18) does not parse 'org/name@<40hex>' or hub URLs and run.py runs "
            "under HF_HUB_OFFLINE=1"
        ),
    )
    raise Refusal(
        "JOB_UNSUPPORTED_HUB_REF",
        f"{template_path} {key_path}={val!r}: runtime config.* keys cannot use hub references because "
        f"{citation}; stage a local VM path instead (provenance hub refs belong under meta.*)",
    )


def _check_job_string_for_hub_refs(
    template_path: Path, key_path: str, val: str, pinned_refs: list[dict[str, str]]
) -> None:
    s = val.strip()
    if not s or s in PLACEHOLDERS:
        return
    url_matches = list(HUB_URL_RE.finditer(s))
    if url_matches:
        for um in url_matches:
            u = um.group(0).rstrip(".,;)")
            m_res = PINNED_HF_RESOLVE_URL_RE.match(u) or PINNED_HF_AT_URL_RE.match(u)
            if m_res is None:
                raise Refusal(
                    "JOB_UNPINNED_HUB_REF",
                    f"{template_path} {key_path}={val!r} contains URL {u!r} not pinned to a 40-hex revision",
                )
            repo_id, rev = m_res.group(1), m_res.group(2).lower()
            _require_allowed_repo(repo_id, f"{template_path} {key_path}={val!r}")
            _refuse_if_runtime_config_hub_ref(template_path, key_path, val)
            pinned_refs.append({"path": key_path, "repo_id": repo_id, "revision": rev})
        return

    if "|" in s:
        pipe_parts = [p.strip() for p in s.split("|") if "/" in p]
        if pipe_parts:
            for part in pipe_parts:
                m_pipe = PINNED_HUB_SPEC_RE.match(part)
                if m_pipe is None:
                    raise Refusal(
                        "JOB_UNPINNED_HUB_REF",
                        f"{template_path} {key_path}={val!r} has unpinned hub reference '{part}' (must pin to @<40-hex>)",
                    )
                repo_id, rev = m_pipe.group(1), m_pipe.group(2).lower()
                _require_allowed_repo(repo_id, f"{template_path} {key_path}={val!r}")
            _refuse_if_runtime_config_hub_ref(template_path, key_path, val)
            for part in pipe_parts:
                m_pipe = PINNED_HUB_SPEC_RE.match(part)
                assert m_pipe is not None
                pinned_refs.append(
                    {"path": key_path, "repo_id": m_pipe.group(1), "revision": m_pipe.group(2).lower()}
                )
            return

    if not any(ch.isspace() for ch in s) and "/" in s:
        if s.startswith(("/", "./", "../")) or re.match(r"^[A-Za-z]:[\\/]", s):
            return
        m_hub = PINNED_HUB_SPEC_RE.match(s)
        if m_hub is None:
            raise Refusal(
                "JOB_UNPINNED_HUB_REF",
                f"{template_path} {key_path}={val!r} is a hub-style reference not pinned to @<40-hex>",
            )
        repo_id, rev = m_hub.group(1), m_hub.group(2).lower()
        _require_allowed_repo(repo_id, f"{template_path} {key_path}={val!r}")
        _refuse_if_runtime_config_hub_ref(template_path, key_path, val)
        pinned_refs.append({"path": key_path, "repo_id": repo_id, "revision": rev})


def validate_job_semantics(
    template_path: Path, parsed: dict[str, Any], *, model_repo: str | None = None
) -> dict[str, Any]:
    """Verify hub references + licence allow-list across all job string values, save/sample cadences,
    trigger_word vs cache_text_embeddings compatibility, and explicit caption_dropout_rate + source."""
    if model_repo is not None and model_repo.strip():
        _require_allowed_repo(model_repo.strip(), "--model")

    pinned_refs: list[dict[str, str]] = []
    for key_path, str_val in _iter_yaml_strings(parsed):
        _check_job_string_for_hub_refs(template_path, key_path, str_val, pinned_refs)

    cfg = parsed.get("config")
    if not isinstance(cfg, dict):
        raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}: missing top-level config mapping")
    procs = cfg.get("process")
    if not isinstance(procs, list) or not procs or not all(isinstance(p, dict) for p in procs):
        raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}: config.process must be a non-empty list of mappings")
    meta = parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {}

    primary_summary: dict[str, Any] | None = None
    for p_idx, proc in enumerate(procs):
        train = proc.get("train")
        if not isinstance(train, dict):
            raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}: config.process[{p_idx}].train must be a mapping")
        steps = train.get("steps")
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
            raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}: train.steps={steps!r} must be a positive integer")

        save = proc.get("save")
        if not isinstance(save, dict) or save.get("disable_saving") is True:
            raise Refusal("JOB_SAVE_CADENCE_INVALID", f"{template_path}: save block is missing or saving is disabled")
        save_every = save.get("save_every")
        if isinstance(save_every, bool) or not isinstance(save_every, int) or save_every < 1 or save_every > steps:
            raise Refusal(
                "JOB_SAVE_CADENCE_INVALID",
                f"{template_path}: save.save_every={save_every!r} must be an integer in 1..{steps} (train.steps={steps})",
            )

        sample = proc.get("sample")
        if (
            train.get("disable_sampling") is True
            or not isinstance(sample, dict)
            or sample.get("disable_sampling") is True
            or sample.get("enabled") is False
        ):
            raise Refusal(
                "JOB_SAMPLE_CADENCE_INVALID",
                f"{template_path}: sampling is off or sample block is missing (the VM refuses TRAIN_SAMPLE_MISSING after training)",
            )
        sample_every = sample.get("sample_every")
        if (
            isinstance(sample_every, bool)
            or not isinstance(sample_every, int)
            or sample_every < 1
            or sample_every > steps
        ):
            raise Refusal(
                "JOB_SAMPLE_CADENCE_INVALID",
                f"{template_path}: sample.sample_every={sample_every!r} must be an integer in 1..{steps} (train.steps={steps})",
            )
        prompts = sample.get("prompts")
        if not isinstance(prompts, list) or not prompts or not all(isinstance(pr, str) and pr.strip() for pr in prompts):
            raise Refusal(
                "JOB_SAMPLE_CADENCE_INVALID",
                f"{template_path}: sample.prompts must be a non-empty list of non-empty strings",
            )
        sample_steps = sample.get("sample_steps")
        if sample_steps is not None and (isinstance(sample_steps, bool) or not isinstance(sample_steps, int) or sample_steps < 1):
            raise Refusal(
                "JOB_SAMPLE_CADENCE_INVALID",
                f"{template_path}: sample.sample_steps={sample_steps!r} must be a positive integer",
            )

        datasets = proc.get("datasets")
        if not isinstance(datasets, list) or not datasets or not all(isinstance(d, dict) for d in datasets):
            raise Refusal("JOB_TEMPLATE_INVALID", f"{template_path}: config.process[{p_idx}].datasets must be a non-empty list")

        cache_te = bool(
            train.get("cache_text_embeddings") is True
            or proc.get("cache_text_embeddings") is True
            or any(d.get("cache_text_embeddings") is True for d in datasets)
        )
        trigger_candidates = [
            proc.get("trigger_word"),
            train.get("trigger_word"),
            *(d.get("trigger_word") for d in datasets),
        ]
        active_triggers = [str(t).strip() for t in trigger_candidates if t is not None and str(t).strip()]
        if cache_te and active_triggers:
            raise Refusal(
                "JOB_TRIGGER_WITH_CACHED_EMBEDDINGS",
                f"{template_path}: trigger_word={active_triggers[0]!r} cannot be set with cache_text_embeddings: true "
                "(ostris/ai-toolkit@beb94824 config/examples/train_lora_qwen_image_24gb.yaml:15: "
                "'Trigger words will not work when caching text embeddings')",
            )

        meta_dropout_src = meta.get("caption_dropout_source")
        dropout_records: list[dict[str, Any]] = []
        for ds_idx, ds in enumerate(datasets):
            if "caption_dropout_rate" not in ds or ds["caption_dropout_rate"] is None:
                raise Refusal(
                    "JOB_CAPTION_DROPOUT_INVALID",
                    f"{template_path}: datasets[{ds_idx}].caption_dropout_rate must be explicit "
                    "(ostris/ai-toolkit@beb94824 toolkit/config_modules.py:968 defaults to 0.0 while "
                    "config/examples/train_lora_qwen_image_24gb.yaml:34 uses 0.05)",
                )
            raw_cdr = ds["caption_dropout_rate"]
            if isinstance(raw_cdr, bool) or not isinstance(raw_cdr, (int, float)) or not math.isfinite(float(raw_cdr)):
                raise Refusal(
                    "JOB_CAPTION_DROPOUT_INVALID",
                    f"{template_path}: datasets[{ds_idx}].caption_dropout_rate={raw_cdr!r} must be a number in [0.0, 1.0]",
                )
            cdr = float(raw_cdr)
            if cdr < 0.0 or cdr > 1.0:
                raise Refusal(
                    "JOB_CAPTION_DROPOUT_INVALID",
                    f"{template_path}: datasets[{ds_idx}].caption_dropout_rate={cdr} must be in [0.0, 1.0]",
                )
            src_note = ds.get("caption_dropout_source") if ds.get("caption_dropout_source") is not None else meta_dropout_src
            if not isinstance(src_note, str) or not src_note.strip():
                raise Refusal(
                    "JOB_CAPTION_DROPOUT_INVALID",
                    f"{template_path}: caption_dropout_source is required alongside caption_dropout_rate={cdr} "
                    "to name where the value came from (ostris/ai-toolkit@beb94824 toolkit/config_modules.py:968 "
                    "default 0.0 vs config/examples/train_lora_qwen_image_24gb.yaml:34 0.05)",
                )
            dropout_records.append({"dataset_index": ds_idx, "rate": cdr, "source": src_note.strip()})

        if primary_summary is None:
            primary_summary = {
                "job_name": cfg.get("name"),
                "steps": steps,
                "save_every": save_every,
                "sample_every": sample_every,
                "caption_dropout": dropout_records,
                "pinned_hub_refs": pinned_refs,
                "meta": {
                    k: meta.get(k)
                    for k in (
                        "caption_dropout_source",
                        "seconds_per_step",
                        "checkpoint_size_bytes",
                        "optimizer_size_bytes",
                        "optimizer_size_source",
                        "samples_and_logs_bytes",
                        "auxiliary_keep_all_bytes",
                        "download_floor_mb_s",
                        "upload_floor_mb_s",
                        "copy_tar_overhead",
                        "expected_model_bytes",
                    )
                    if k in meta
                },
            }
    assert primary_summary is not None
    return primary_summary


def run_check_job(args: argparse.Namespace) -> int:
    template_path = Path(args.template)
    template_sha = getattr(args, "template_sha", None)
    model_revision = getattr(args, "model_revision", None)
    model_repo = getattr(args, "model_repo", None)
    plan_out = getattr(args, "plan_out", None)
    try:
        if not template_path.is_file():
            raise Refusal("JOB_FILE_MISSING", str(template_path))
        got_sha = sha256_file(template_path)
        if template_sha is not None:
            exp_sha = normalize_sha256(template_sha, "JOB_SHA_MISMATCH", "job_sha")
            if got_sha != exp_sha:
                raise Refusal("JOB_SHA_MISMATCH", f"{template_path} sha256={got_sha} expected={exp_sha}")
        if model_revision is not None and not REVISION_RE.match(model_revision or ""):
            raise Refusal("TRAIN_MODEL_REVISION_REQUIRED", f"{model_revision!r} is not a 40-hex commit")
        text = template_path.read_text(encoding="utf-8")
        validate_job_template(template_path, text, strict_bindings=True)
        parsed = parse_job_yaml(text, template_path)
        summary = validate_job_semantics(template_path, parsed, model_repo=model_repo)
        summary["template_sha256"] = got_sha
        if plan_out:
            write_json(Path(plan_out), summary)
    except Refusal as exc:
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1
    print(f"JOB_TEMPLATE_OK {template_path} sha256={got_sha}", flush=True)
    return 0


def _parse_int_setting(raw: Any, code: str, name: str, *, allow_zero: bool = False) -> int:
    if raw is None or str(raw).strip() == "":
        raise Refusal(code, f"{name} is required (there is no default)")
    s = str(raw).strip()
    if isinstance(raw, bool) or not re.match(r"^[+-]?\d+$", s):
        raise Refusal(code, f"{name}={raw!r} must be an integer")
    val = int(s)
    if (allow_zero and val < 0) or (not allow_zero and val <= 0):
        bound = "non-negative" if allow_zero else "positive"
        raise Refusal(code, f"{name}={raw!r} must be a {bound} integer")
    return val


def _pick_setting(cli_val: Any, meta: dict[str, Any], meta_key: str) -> tuple[Any, str | None]:
    if cli_val is not None and str(cli_val).strip() != "":
        return cli_val, "cli"
    if meta_key in meta and meta[meta_key] is not None and str(meta[meta_key]).strip() != "":
        return meta[meta_key], "job_meta"
    return None, None


SPLIT_DISK_HEADROOM_BYTES = 16 * 1024 * 1024
OPTIMIZER_SIZE_SOURCE_RE = re.compile(r"^(measured|estimate):\s*\S")


def _resolve_optimizer_size_provenance(
    cli_val: Any, meta: dict[str, Any], is_real_job: bool
) -> tuple[str | None, str | None]:
    """The `--job` path must say where its optimizer_size_bytes came from: `measured: <where>` or
    `estimate: <how>` (flag --optimizer-size-source or meta.optimizer_size_source). The built-in rung
    templates (--rung-job) keep their fixed estimate and need no statement."""
    raw, origin = _pick_setting(cli_val, meta, "optimizer_size_source")
    if raw is None:
        if is_real_job:
            raise Refusal(
                "OPTIMIZER_SIZE_SOURCE_REQUIRED",
                "a --job must state optimizer_size_source together with optimizer_size_bytes "
                "(meta.optimizer_size_source or --optimizer-size-source): 'measured: <where>' or 'estimate: <how>'",
            )
        return None, None
    text = str(raw).strip()
    if not OPTIMIZER_SIZE_SOURCE_RE.match(text):
        raise Refusal(
            "OPTIMIZER_SIZE_SOURCE_REQUIRED",
            f"optimizer_size_source={text!r} must read 'measured: <where>' or 'estimate: <how>'",
        )
    return text, origin


def _resolve_download_timeout_basis(
    *,
    steps: int,
    save_every: int,
    meta: dict[str, Any],
    is_real_job: bool,
    download_chunk_bytes_raw: Any,
    explicit_download_timeout_raw: Any,
    download_timeout_source_raw: Any,
    default_download_timeout_raw: Any,
    download_floor_mb_s_arg: Any,
    checkpoint_size_bytes_arg: Any,
    optimizer_size_bytes_arg: Any,
    samples_and_logs_bytes_arg: Any,
    auxiliary_keep_all_bytes_arg: Any,
    plan_sink: dict[str, Any] | None = None,
) -> tuple[int, int, int, int | None, dict[str, Any], Any, str | None, Any, str | None]:
    ckpt_count = math.ceil(steps / save_every) if (steps > 0 and save_every > 0) else 1
    download_chunk_bytes = (
        _parse_int_setting(download_chunk_bytes_raw, "DOWNLOAD_CHUNK_BYTES_INVALID", "download_chunk_bytes")
        if download_chunk_bytes_raw is not None and str(download_chunk_bytes_raw).strip() != ""
        else DEFAULT_DOWNLOAD_CHUNK_BYTES
    )
    explicit_raw = (explicit_download_timeout_raw or "").strip()
    dl_src = (download_timeout_source_raw or "default").strip()
    explicit_dl_s: int | None = None
    if explicit_raw:
        explicit_dl_s = _parse_int_setting(explicit_raw, "DOWNLOAD_TIMEOUT_INVALID", "download_timeout_s")

    raw_dl_floor, dl_floor_src = _pick_setting(download_floor_mb_s_arg, meta, "download_floor_mb_s")
    raw_ckpt_b, ckpt_b_src = _pick_setting(checkpoint_size_bytes_arg, meta, "checkpoint_size_bytes")
    raw_opt_dl_b, opt_dl_src = _pick_setting(optimizer_size_bytes_arg, meta, "optimizer_size_bytes")
    raw_samp_b, samp_b_src = _pick_setting(samples_and_logs_bytes_arg, meta, "samples_and_logs_bytes")
    raw_aux_b, aux_b_src = _pick_setting(auxiliary_keep_all_bytes_arg, meta, "auxiliary_keep_all_bytes")

    dl_floor_val: float | None = None
    projected_dl_s: int | None = None
    expected_bundle_bytes: int | None = None
    download_part_count = 1
    max_download_part_bytes: int | None = None
    dl_ckpt_b: int | None = None
    dl_opt_b: int | None = None
    dl_samp_b: int | None = None
    dl_aux_b = 0
    if raw_dl_floor is not None:
        dl_floor_val = parse_positive_number(str(raw_dl_floor), "DOWNLOAD_TIMEOUT_INVALID", "download_floor_mb_s")
        if raw_ckpt_b is None or raw_opt_dl_b is None or raw_samp_b is None:
            raise Refusal(
                "DOWNLOAD_TIMEOUT_REQUIRED",
                "projecting bundle download timeout requires checkpoint_size_bytes, "
                "optimizer_size_bytes, and samples_and_logs_bytes",
            )
        dl_ckpt_b = _parse_int_setting(raw_ckpt_b, "DOWNLOAD_TIMEOUT_INVALID", "checkpoint_size_bytes")
        dl_opt_b = _parse_int_setting(raw_opt_dl_b, "DOWNLOAD_TIMEOUT_INVALID", "optimizer_size_bytes")
        dl_samp_b = _parse_int_setting(raw_samp_b, "DOWNLOAD_TIMEOUT_INVALID", "samples_and_logs_bytes", allow_zero=True)
        dl_aux_b = (
            _parse_int_setting(raw_aux_b, "DOWNLOAD_TIMEOUT_INVALID", "auxiliary_keep_all_bytes", allow_zero=True)
            if raw_aux_b is not None
            else 0
        )
        expected_bundle_bytes = ckpt_count * dl_ckpt_b + dl_opt_b + dl_samp_b + dl_aux_b
        download_part_count = (
            max(1, math.ceil(expected_bundle_bytes / download_chunk_bytes)) if expected_bundle_bytes > 0 else 1
        )
        max_download_part_bytes = min(expected_bundle_bytes, download_chunk_bytes)
        projected_dl_s = max(1, math.ceil(max_download_part_bytes / (dl_floor_val * 1_000_000.0)))
    elif raw_ckpt_b is not None and raw_opt_dl_b is not None:
        try:
            cand_ckpt_b = _parse_int_setting(raw_ckpt_b, "DOWNLOAD_TIMEOUT_INVALID", "checkpoint_size_bytes")
            cand_opt_b = _parse_int_setting(raw_opt_dl_b, "DOWNLOAD_TIMEOUT_INVALID", "optimizer_size_bytes")
            cand_samp_b = (
                _parse_int_setting(raw_samp_b, "DOWNLOAD_TIMEOUT_INVALID", "samples_and_logs_bytes", allow_zero=True)
                if raw_samp_b is not None
                else 0
            )
            cand_aux_b = (
                _parse_int_setting(raw_aux_b, "DOWNLOAD_TIMEOUT_INVALID", "auxiliary_keep_all_bytes", allow_zero=True)
                if raw_aux_b is not None
                else 0
            )
            dl_ckpt_b = cand_ckpt_b
            dl_opt_b = cand_opt_b
            dl_samp_b = cand_samp_b if raw_samp_b is not None else None
            dl_aux_b = cand_aux_b
            expected_bundle_bytes = ckpt_count * cand_ckpt_b + cand_opt_b + cand_samp_b + cand_aux_b
            if expected_bundle_bytes > 0:
                download_part_count = max(1, math.ceil(expected_bundle_bytes / download_chunk_bytes))
                max_download_part_bytes = min(expected_bundle_bytes, download_chunk_bytes)
        except Refusal:
            pass

    if is_real_job and explicit_dl_s is None and projected_dl_s is None:
        if plan_sink is not None:
            plan_sink["download_timeout_basis"] = {
                "mode": "missing_on_real_job",
                "is_real_job": True,
                "steps": steps,
                "save_every": save_every,
            }
        raise Refusal(
            "DOWNLOAD_TIMEOUT_REQUIRED",
            "--job must not use the 300 s default download timeout; pass --download-timeout-s <s> "
            "or project it with checkpoint_size_bytes, optimizer_size_bytes, samples_and_logs_bytes "
            "and --download-floor-mb-s <MB/s>",
        )

    if explicit_dl_s is not None and projected_dl_s is not None and explicit_dl_s < projected_dl_s:
        if plan_sink is not None:
            plan_sink["download_timeout_basis"] = {
                "mode": "explicit_below_projected",
                "source": dl_src,
                "explicit_seconds": explicit_dl_s,
                "projected_seconds": projected_dl_s,
                "expected_bundle_bytes": expected_bundle_bytes,
                "download_chunk_bytes": download_chunk_bytes,
                "part_count": download_part_count,
                "max_part_bytes": max_download_part_bytes,
                "throughput_floor_mb_s": dl_floor_val,
            }
        raise Refusal(
            "DOWNLOAD_TIMEOUT_TOO_SHORT",
            f"--download-timeout-s {explicit_dl_s} s < projected per-part {projected_dl_s} s "
            f"({max_download_part_bytes} bytes/part at {dl_floor_val} MB/s)",
        )

    if explicit_dl_s is not None:
        chosen_dl_s = explicit_dl_s
        dl_mode = "explicit"
        dl_basis_source = dl_src if dl_src in ("cli", "env") else "cli"
    elif projected_dl_s is not None:
        chosen_dl_s = projected_dl_s
        dl_mode = "projected"
        dl_basis_source = dl_floor_src or "projection"
    else:
        chosen_dl_s = _parse_int_setting(
            default_download_timeout_raw, "DOWNLOAD_TIMEOUT_INVALID", "default_download_timeout_s"
        )
        dl_mode = "rung_default"
        dl_basis_source = "default"

    basis = {
        "mode": dl_mode,
        "source": dl_basis_source,
        "is_real_job": is_real_job,
        "chosen_seconds": chosen_dl_s,
        "salvage_download_timeout_seconds": chosen_dl_s,
        "download_chunk_bytes": download_chunk_bytes,
        "part_count": download_part_count,
        "max_part_bytes": max_download_part_bytes,
        "steps": steps,
        "save_every": save_every,
        "checkpoint_count": ckpt_count,
        "checkpoint_size_bytes": dl_ckpt_b,
        "checkpoint_size_source": ckpt_b_src if dl_ckpt_b is not None else None,
        "optimizer_size_bytes": dl_opt_b,
        "optimizer_size_source": opt_dl_src if dl_opt_b is not None else None,
        "samples_and_logs_bytes": dl_samp_b,
        "samples_and_logs_source": samp_b_src if dl_samp_b is not None else None,
        "auxiliary_keep_all_bytes": dl_aux_b,
        "auxiliary_keep_all_source": aux_b_src if raw_aux_b is not None else "default_zero",
        "expected_bundle_bytes": expected_bundle_bytes,
        "throughput_floor_mb_s": dl_floor_val,
        "projected_seconds": projected_dl_s,
    }
    return (
        chosen_dl_s,
        download_chunk_bytes,
        download_part_count,
        max_download_part_bytes,
        basis,
        raw_samp_b,
        samp_b_src,
        raw_aux_b,
        aux_b_src,
    )


def run_dry_download_bounds(args: argparse.Namespace) -> int:
    """Resolve download_timeout_s, source, and projected salvage part_count for `launch_lane3_stub.sh --dry`."""
    try:
        job_p = Path(args.job_yaml)
        if not job_p.is_file():
            raise Refusal("JOB_TEMPLATE_INVALID", f"missing job file {job_p}")
        doc = parse_job_yaml(job_p.read_text(encoding="utf-8"))
        cfg = doc.get("config") if isinstance(doc.get("config"), dict) else {}
        procs = cfg.get("process") if isinstance(cfg.get("process"), list) else []
        proc = procs[0] if procs and isinstance(procs[0], dict) else {}
        train_cfg = proc.get("train") if isinstance(proc.get("train"), dict) else {}
        save_cfg = proc.get("save") if isinstance(proc.get("save"), dict) else {}
        steps = int(train_cfg.get("steps") or 0)
        save_every = int(save_cfg.get("save_every") or 0)
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        chosen_dl_s, _, part_count, _, basis, _, _, _, _ = _resolve_download_timeout_basis(
            steps=steps,
            save_every=save_every,
            meta=meta,
            is_real_job=str(args.is_real_job).strip() == "1",
            download_chunk_bytes_raw=args.download_chunk_bytes,
            explicit_download_timeout_raw=args.explicit_download_timeout_s,
            download_timeout_source_raw=args.download_timeout_source,
            default_download_timeout_raw=args.default_download_timeout_s,
            download_floor_mb_s_arg=args.download_floor_mb_s,
            checkpoint_size_bytes_arg=args.checkpoint_size_bytes,
            optimizer_size_bytes_arg=args.optimizer_size_bytes,
            samples_and_logs_bytes_arg=args.samples_and_logs_bytes,
            auxiliary_keep_all_bytes_arg=args.auxiliary_keep_all_bytes,
        )
        src_out = "projected" if basis["mode"] == "projected" else str(basis["source"])
        print(f"{chosen_dl_s}\t{src_out}\t{int(part_count)}", flush=True)
        return 0
    except Refusal as exc:
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 2


def run_plan_run(args: argparse.Namespace) -> int:
    """Rig-side pre-open planner for Parts 1, 2, 4, and 5: resolves download/upload timeouts,
    wall allowance from steps * seconds_per_step, and projected VM output disk fit."""
    out_path = Path(args.out) if getattr(args, "out", None) else None
    plan: dict[str, Any] = {}
    try:
        job_plan = read_json(Path(args.job_plan))
        if not isinstance(job_plan, dict):
            raise Refusal("JOB_TEMPLATE_INVALID", f"unreadable job plan {args.job_plan}")
        steps = int(job_plan["steps"])
        save_every = int(job_plan["save_every"])
        meta = job_plan.get("meta") if isinstance(job_plan.get("meta"), dict) else {}
        ckpt_count = math.ceil(steps / save_every)
        is_real_job = str(args.is_real_job).strip() == "1"

        # 1. Bundle download timeout (Part 1; per-part under COLAB_DOWNLOAD_CHUNK_BYTES in Addendum 1 Part 2b)
        (
            chosen_dl_s,
            download_chunk_bytes,
            download_part_count,
            max_download_part_bytes,
            dl_basis,
            raw_samp_b,
            samp_b_src,
            raw_aux_b,
            aux_b_src,
        ) = _resolve_download_timeout_basis(
            steps=steps,
            save_every=save_every,
            meta=meta,
            is_real_job=is_real_job,
            download_chunk_bytes_raw=getattr(args, "download_chunk_bytes", None),
            explicit_download_timeout_raw=args.explicit_download_timeout_s,
            download_timeout_source_raw=args.download_timeout_source,
            default_download_timeout_raw=args.default_download_timeout_s,
            download_floor_mb_s_arg=args.download_floor_mb_s,
            checkpoint_size_bytes_arg=args.checkpoint_size_bytes,
            optimizer_size_bytes_arg=args.optimizer_size_bytes,
            samples_and_logs_bytes_arg=args.samples_and_logs_bytes,
            auxiliary_keep_all_bytes_arg=getattr(args, "auxiliary_keep_all_bytes", None),
            plan_sink=plan,
        )
        plan["download_timeout_s"] = chosen_dl_s
        plan["salvage_download_timeout_s"] = chosen_dl_s
        plan["download_chunk_bytes"] = download_chunk_bytes
        plan["download_timeout_basis"] = dl_basis

        # 2. Dataset archive upload timeout (Part 2; per-part under COLAB_UPLOAD_CHUNK_BYTES in Addendum 1 Part 2)
        upload_timeout_s = _parse_int_setting(args.upload_timeout_s, "UPLOAD_TIMEOUT_INVALID", "upload_timeout_s")
        upload_chunk_bytes = (
            _parse_int_setting(args.upload_chunk_bytes, "UPLOAD_CHUNK_BYTES_INVALID", "upload_chunk_bytes")
            if getattr(args, "upload_chunk_bytes", None) is not None and str(args.upload_chunk_bytes).strip() != ""
            else DEFAULT_UPLOAD_CHUNK_BYTES
        )
        raw_up_floor, up_floor_src = _pick_setting(args.upload_floor_mb_s, meta, "upload_floor_mb_s")
        if raw_up_floor is None:
            up_floor_val = DEFAULT_UPLOAD_FLOOR_MB_S
            up_floor_src = "default"
        else:
            up_floor_val = parse_positive_number(str(raw_up_floor), "UPLOAD_TIMEOUT_INVALID", "upload_floor_mb_s")

        archive_p = Path(args.dataset_archive)
        if not archive_p.is_file():
            raise Refusal("DATASET_FILE_MISSING", str(archive_p))
        archive_bytes = archive_p.stat().st_size
        upload_part_count = max(1, math.ceil(archive_bytes / upload_chunk_bytes)) if archive_bytes > 0 else 1
        max_upload_part_bytes = min(archive_bytes, upload_chunk_bytes)
        projected_upload_s = max_upload_part_bytes / (up_floor_val * 1_000_000.0)
        projected_total_upload_s = archive_bytes / (up_floor_val * 1_000_000.0)
        upload_ok = projected_upload_s <= float(upload_timeout_s)
        plan["upload_timeout_s"] = upload_timeout_s
        plan["upload_chunk_bytes"] = upload_chunk_bytes
        plan["upload_timeout_check"] = {
            "upload_timeout_s": upload_timeout_s,
            "source": (args.upload_timeout_source or "default").strip(),
            "upload_chunk_bytes": upload_chunk_bytes,
            "part_count": upload_part_count,
            "max_part_bytes": max_upload_part_bytes,
            "dataset_archive_bytes": archive_bytes,
            "throughput_floor_mb_s": up_floor_val,
            "floor_source": up_floor_src,
            "projected_upload_seconds": round(projected_upload_s, 4),
            "projected_total_upload_seconds": round(projected_total_upload_s, 4),
            "ok": upload_ok,
        }
        if not upload_ok:
            raise Refusal(
                "UPLOAD_TIMEOUT_TOO_SHORT",
                f"dataset archive part ({max_upload_part_bytes} bytes of {archive_bytes} total) "
                f"at {up_floor_val} MB/s needs {projected_upload_s:.2f} s > upload timeout {upload_timeout_s} s",
            )

        # 3. Keep-all bundle breakdown + output disk projection (checked before wall allowance so a
        # job that cannot physically fit on the VM disk refuses TRAIN_OUTPUT_DISK_LOW regardless of --wall-s)
        raw_out_ckpt_b, out_ckpt_src = _pick_setting(args.checkpoint_size_bytes, meta, "checkpoint_size_bytes")
        raw_opt_b, opt_src = _pick_setting(args.optimizer_size_bytes, meta, "optimizer_size_bytes")
        raw_overhead, overhead_src = _pick_setting(args.output_overhead_factor, meta, "copy_tar_overhead")
        raw_model_b, model_b_src = _pick_setting(args.expected_model_bytes, meta, "expected_model_bytes")

        ckpt_size_b = _parse_int_setting(
            raw_out_ckpt_b, "TRAIN_OUTPUT_PROJECTION_REQUIRED", "checkpoint_size_bytes"
        )
        opt_size_b = _parse_int_setting(
            raw_opt_b, "TRAIN_OUTPUT_PROJECTION_REQUIRED", "optimizer_size_bytes"
        )
        opt_provenance, _opt_prov_origin = _resolve_optimizer_size_provenance(
            getattr(args, "optimizer_size_source", None), meta, is_real_job
        )
        samp_size_b = (
            _parse_int_setting(
                raw_samp_b, "TRAIN_OUTPUT_PROJECTION_REQUIRED", "samples_and_logs_bytes", allow_zero=True
            )
            if raw_samp_b is not None
            else 0
        )
        aux_size_b = (
            _parse_int_setting(
                raw_aux_b, "TRAIN_OUTPUT_PROJECTION_REQUIRED", "auxiliary_keep_all_bytes", allow_zero=True
            )
            if raw_aux_b is not None
            else 0
        )
        if raw_overhead is None:
            overhead = DEFAULT_OUTPUT_COPY_TAR_OVERHEAD
            overhead_src = "default"
        else:
            overhead = parse_positive_number(str(raw_overhead), "TRAIN_OUTPUT_PROJECTION_REQUIRED", "copy_tar_overhead")
            if overhead < 1.0:
                raise Refusal("TRAIN_OUTPUT_PROJECTION_REQUIRED", f"copy_tar_overhead={overhead} must be >= 1.0")
        expected_model_b = (
            _parse_int_setting(raw_model_b, "TRAIN_OUTPUT_PROJECTION_REQUIRED", "expected_model_bytes", allow_zero=True)
            if raw_model_b is not None
            else 0
        )
        vm_budget_gib = (
            parse_positive_number(str(args.vm_disk_budget_gib), "TRAIN_OUTPUT_PROJECTION_REQUIRED", "vm_disk_budget_gib")
            if args.vm_disk_budget_gib is not None and str(args.vm_disk_budget_gib).strip() != ""
            else DEFAULT_VM_DISK_BUDGET_GIB
        )

        checkpoints_total_b = ckpt_count * ckpt_size_b
        full_bundle_bytes = checkpoints_total_b + opt_size_b + samp_size_b + aux_size_b
        expected_bundle_bytes = full_bundle_bytes
        download_part_count = max(1, math.ceil(full_bundle_bytes / download_chunk_bytes))
        max_download_part_bytes = min(full_bundle_bytes, download_chunk_bytes)

        bundle_projection = {
            "formula": (
                "expected_bundle_bytes = checkpoint_count * checkpoint_size_bytes "
                "+ optimizer_size_bytes + samples_and_logs_bytes + auxiliary_keep_all_bytes"
            ),
            "keep_all_sources": {
                "checkpoints": (
                    f"{AI_TOOLKIT_PIN_REF} jobs/process/BaseSDTrainProcess.py:518-526,2727,2830 "
                    "(live copy-off retains every saved step checkpoint plus final safetensors)"
                ),
                "optimizer_state": (
                    f"{AI_TOOLKIT_PIN_REF} jobs/process/BaseSDTrainProcess.py:704-713 "
                    "(single overwritten {name}/optimizer.pt)"
                ),
                "samples_logs_and_config": (
                    f"{AI_TOOLKIT_PIN_REF} jobs/process/BaseSDTrainProcess.py:286, "
                    "jobs/process/BaseTrainProcess.py:48-49,75-79, toolkit/logging_aitk.py:341-342"
                ),
                "auxiliary_keep_all": "lane3_rung.py copy-off underscore subdirectories (e.g. _latent_cache)",
            },
            "steps": steps,
            "save_every": save_every,
            "checkpoint_count": ckpt_count,
            "checkpoint_size_bytes": ckpt_size_b,
            "checkpoint_size_source": out_ckpt_src,
            "checkpoints_bytes": checkpoints_total_b,
            "optimizer_size_bytes": opt_size_b,
            "optimizer_size_source": opt_src,
            "optimizer_size_provenance": opt_provenance,
            "optimizer_state_bytes": opt_size_b,
            "samples_and_logs_bytes": samp_size_b,
            "samples_and_logs_source": samp_b_src if raw_samp_b is not None else "default_zero",
            "samples_logs_and_config_bytes": samp_size_b,
            "auxiliary_keep_all_bytes": aux_size_b,
            "auxiliary_keep_all_source": aux_b_src if raw_aux_b is not None else "default_zero",
            "expected_bundle_bytes": full_bundle_bytes,
            "download_chunk_bytes": download_chunk_bytes,
            "part_count": download_part_count,
            "max_part_bytes": max_download_part_bytes,
        }
        plan["bundle_projection"] = bundle_projection
        plan["download_timeout_basis"].update({
            "part_count": download_part_count,
            "max_part_bytes": max_download_part_bytes,
            "checkpoint_size_bytes": ckpt_size_b,
            "checkpoint_size_source": out_ckpt_src,
            "optimizer_size_bytes": opt_size_b,
            "optimizer_size_source": opt_src,
            "optimizer_size_provenance": opt_provenance,
            "samples_and_logs_bytes": samp_size_b,
            "samples_and_logs_source": samp_b_src if raw_samp_b is not None else "default_zero",
            "auxiliary_keep_all_bytes": aux_size_b,
            "auxiliary_keep_all_source": aux_b_src if raw_aux_b is not None else "default_zero",
            "expected_bundle_bytes": full_bundle_bytes,
            "keep_all_breakdown": {
                "checkpoints_bytes": checkpoints_total_b,
                "optimizer_state_bytes": opt_size_b,
                "samples_logs_and_config_bytes": samp_size_b,
                "auxiliary_keep_all_bytes": aux_size_b,
            },
        })

        raw_output_bytes = full_bundle_bytes
        split_copy_overhead = 1.0 if raw_output_bytes > download_chunk_bytes else 0.0
        effective_overhead = round(overhead + split_copy_overhead, 6)
        # the VM split check needs size + 16 MiB free (launch_guards.prepare_single_content_download)
        split_disk_headroom_bytes = SPLIT_DISK_HEADROOM_BYTES if raw_output_bytes > download_chunk_bytes else 0
        projected_output_bytes = math.ceil(raw_output_bytes * effective_overhead) + split_disk_headroom_bytes
        vm_budget_bytes = int(vm_budget_gib * GIB)
        avail_for_output_bytes = vm_budget_bytes - expected_model_b
        disk_ok = projected_output_bytes <= avail_for_output_bytes
        plan["output_disk_projection"] = {
            "steps": steps,
            "save_every": save_every,
            "checkpoint_count": ckpt_count,
            "checkpoint_size_bytes": ckpt_size_b,
            "checkpoint_size_source": out_ckpt_src,
            "optimizer_size_bytes": opt_size_b,
            "optimizer_size_source": opt_src,
            "optimizer_size_provenance": opt_provenance,
            "samples_and_logs_bytes": samp_size_b,
            "samples_and_logs_source": samp_b_src if raw_samp_b is not None else "default_zero",
            "auxiliary_keep_all_bytes": aux_size_b,
            "auxiliary_keep_all_source": aux_b_src if raw_aux_b is not None else "default_zero",
            "raw_output_bytes": raw_output_bytes,
            "base_copy_tar_overhead": overhead,
            "split_copy_overhead": split_copy_overhead,
            "split_disk_headroom_bytes": split_disk_headroom_bytes,
            "chunked_download_split_required": raw_output_bytes > download_chunk_bytes,
            "download_chunk_bytes": download_chunk_bytes,
            "copy_tar_overhead": effective_overhead,
            "overhead_source": overhead_src,
            "projected_output_bytes": projected_output_bytes,
            "expected_model_bytes": expected_model_b,
            "expected_model_source": model_b_src if raw_model_b is not None else "none",
            "vm_disk_budget_gib": vm_budget_gib,
            "vm_disk_budget_bytes": vm_budget_bytes,
            "available_for_output_bytes": avail_for_output_bytes,
            "ok": disk_ok,
        }
        if not disk_ok:
            raise Refusal(
                "TRAIN_OUTPUT_DISK_LOW",
                f"projected output {projected_output_bytes} bytes "
                f"({raw_output_bytes} * {effective_overhead} [base {overhead} + split {split_copy_overhead}] "
                f"+ {split_disk_headroom_bytes} headroom) "
                f"cannot fit within {avail_for_output_bytes} bytes "
                f"(VM disk guard {vm_budget_gib} GiB minus model {expected_model_b} bytes)",
            )

        # 4. Wall allowance (`--rung-job` keeps its fixed rung allowance; `--job` derives from steps * seconds_per_step)
        download_max_s = _parse_int_setting(args.download_max_seconds, "DOWNLOAD_LIMIT_MISSING", "download_max_seconds")
        setup_allowance_s = _parse_int_setting(args.setup_allowance_s, "TRAIN_WALL_TOO_SHORT", "setup_allowance_s")
        wall_s = _parse_int_setting(args.wall_s, "TRAIN_WALL_TOO_SHORT", "wall_s")
        grace_s = _parse_int_setting(args.grace_s, "TRAIN_WALL_TOO_SHORT", "grace_s", allow_zero=True)

        test_train_raw = (args.test_train_allowance_s or "").strip()
        test_fetch_raw = (args.test_fetch_allowance_s or "").strip()
        raw_sps, sps_src = _pick_setting(args.seconds_per_step, meta, "seconds_per_step")
        seconds_per_step: float | None = None
        computed_train_s: int | None = None

        if not is_real_job:
            if raw_sps is not None:
                seconds_per_step = parse_positive_number(str(raw_sps), "TRAIN_STEP_TIME_REQUIRED", "seconds_per_step")
                computed_train_s = max(1, math.ceil(steps * seconds_per_step))
            rung_train_raw = (getattr(args, "rung_train_allowance_s", "") or "").strip() or "1800"
            train_allowance_s = _parse_int_setting(
                test_train_raw or rung_train_raw, "TRAIN_WALL_TOO_SHORT", "train_allowance_s"
            )
            fetch_allowance_s = (
                _parse_int_setting(test_fetch_raw, "TRAIN_WALL_TOO_SHORT", "SDLAB_TEST_FETCH_ALLOWANCE_S", allow_zero=True)
                if test_fetch_raw
                else 0
            )
            wall_mode = "test_override" if test_train_raw else "rung_fixed"
        else:
            seconds_per_step = parse_positive_number(
                str(raw_sps) if raw_sps is not None else None, "TRAIN_STEP_TIME_REQUIRED", "seconds_per_step"
            )
            computed_train_s = max(1, math.ceil(steps * seconds_per_step))
            if test_train_raw:
                train_allowance_s = _parse_int_setting(test_train_raw, "TRAIN_WALL_TOO_SHORT", "SDLAB_TEST_TRAIN_ALLOWANCE_S")
                fetch_allowance_s = (
                    _parse_int_setting(test_fetch_raw, "TRAIN_WALL_TOO_SHORT", "SDLAB_TEST_FETCH_ALLOWANCE_S", allow_zero=True)
                    if test_fetch_raw
                    else 0
                )
                wall_mode = "test_override"
            else:
                train_allowance_s = computed_train_s
                fetch_allowance_s = download_part_count * chosen_dl_s
                wall_mode = "job_step_time"

        required_wall_s = download_max_s + setup_allowance_s + train_allowance_s + fetch_allowance_s
        effective_wall_s = wall_s - grace_s
        wall_ok = effective_wall_s >= required_wall_s
        plan["wall_allowance"] = {
            "mode": wall_mode,
            "is_real_job": is_real_job,
            "steps": steps,
            "seconds_per_step": seconds_per_step,
            "seconds_per_step_source": sps_src,
            "computed_train_seconds": computed_train_s,
            "download_max_seconds": download_max_s,
            "setup_allowance_s": setup_allowance_s,
            "train_allowance_s": train_allowance_s,
            "fetch_allowance_s": fetch_allowance_s,
            "required_wall_s": required_wall_s,
            "total_required_seconds": required_wall_s,
            "wall_s": wall_s,
            "grace_s": grace_s,
            "effective_wall_s": effective_wall_s,
            "ok": wall_ok,
        }
        if not wall_ok:
            if not is_real_job:
                raise Refusal(
                    "TRAIN_WALL_TOO_SHORT",
                    f"--wall-s {wall_s} minus grace {grace_s} must cover {required_wall_s} s "
                    f"(download limit {download_max_s} + install {setup_allowance_s} + train {train_allowance_s})",
                )
            raise Refusal(
                "TRAIN_WALL_TOO_SHORT",
                f"--wall-s {wall_s} minus grace {grace_s} must cover {required_wall_s} s "
                f"(download limit {download_max_s} + setup {setup_allowance_s} + "
                f"train {train_allowance_s} [{steps} steps * {seconds_per_step} s/step] + fetch {fetch_allowance_s})",
            )
    except Refusal as exc:
        plan["refusal"] = {"code": exc.code, "why": exc.detail}
        if out_path is not None:
            write_json(out_path, plan)
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1

    if out_path is not None:
        write_json(out_path, plan)
    print("RUN_PLAN_OK " + json.dumps(plan), flush=True)
    return 0


def run_render_job(args: argparse.Namespace) -> int:
    template_path = Path(args.template)
    template_sha = getattr(args, "template_sha", None)
    try:
        if not template_path.is_file():
            raise Refusal("JOB_FILE_MISSING", str(template_path))
        if template_sha is not None:
            exp_sha = normalize_sha256(template_sha, "JOB_SHA_MISMATCH", "template_sha")
            got_sha = sha256_file(template_path)
            if got_sha != exp_sha:
                raise Refusal("JOB_SHA_MISMATCH", f"{template_path} sha256={got_sha} expected={exp_sha}")
        text = template_path.read_text(encoding="utf-8")
        validate_job_template(template_path, text, strict_bindings=False)
        values = {
            "__LANE3_TRAINING_FOLDER__": args.training_folder,
            "__LANE3_DATASET_DIR__": args.dataset_dir,
            "__LANE3_MODEL_PATH__": args.model_path,
        }
        for key in PLACEHOLDERS:
            val = values[key] or ""
            if not val or '"' in val or "\\" in val or "\n" in val:
                raise Refusal("JOB_TEMPLATE_INVALID", f"value for {key} is empty or not a plain path")
            text = text.replace(f'"{key}"', json.dumps(val))
    except Refusal as exc:
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"JOB_RENDERED {args.out}", flush=True)
    return 0


# ---------------------------------------------------------------------------------------------
# copy-off, training-folder manifest, disk checks, and finish
# ---------------------------------------------------------------------------------------------


def _is_underscore_subpath(rel: str) -> bool:
    return any(part.startswith("_") for part in Path(rel).parts[:-1])


def copy_off_once(watch: Path, bundle: Path, manifest: Path, state: dict[str, Any], *, final: bool = False) -> int:
    """Copy every regular file in `watch` whose `(size, mtime_ns)` held still since the last pass
    (or every new/modified file on `final=True`) into `bundle/<relative path>`, appending a manifest
    line with its sha256. Nothing is filtered out by suffix or `_*` directory."""
    pending: dict[str, tuple[int, int]] = state.setdefault("pending", {})
    raw_done = state.setdefault("done", {})
    if isinstance(raw_done, set):
        done: dict[str, tuple[int, str]] = {p: (-1, "") for p in raw_done}
        state["done"] = done
    else:
        done = raw_done
    done_mtime: dict[str, tuple[int, int]] = state.setdefault("done_mtime", {})
    copied = 0
    if not watch.is_dir():
        return 0
    for fp in sorted(watch.rglob("*")):
        try:
            if fp.is_symlink() or not fp.is_file():
                continue
            rel = fp.relative_to(watch).as_posix()
            st_info = fp.stat()
            size = st_info.st_size
            sig = (size, st_info.st_mtime_ns)
            prev = done.get(rel)
            if not final:
                if prev is not None and (prev[0] == -1 or (prev[0] == size and done_mtime.get(rel, sig) == sig)):
                    continue
                if pending.get(rel) != sig:
                    pending[rel] = sig
                    continue
            else:
                src_sha = sha256_file(fp)
                dest_existing = bundle / rel
                if (
                    prev is not None
                    and prev == (size, src_sha)
                    and dest_existing.is_file()
                    and dest_existing.stat().st_size == size
                ):
                    continue
            dest = bundle / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fp, dest)
            dest_bytes = dest.stat().st_size
            dest_sha = sha256_file(dest)
            line: dict[str, Any] = {
                "path": rel,
                "bytes": dest_bytes,
                "sha256": dest_sha,
                "copied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if rel.endswith(".safetensors"):
                line["partial"] = not safetensors_complete(dest)
            manifest.parent.mkdir(parents=True, exist_ok=True)
            with manifest.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(line) + "\n")
            print("COPY_OFF " + json.dumps(line), flush=True)
            copied += 1
            if line.get("partial"):
                # Still being written: copy it again on a later pass (and the final sweep) until
                # it is complete; the newest manifest line for a path is the one that counts.
                pending[rel] = (-1, -1)
            else:
                done[rel] = (dest_bytes, dest_sha)
                done_mtime[rel] = sig
        except FileNotFoundError as exc:
            print(f"COPY_OFF_SKIPPED {fp.name}: {type(exc).__name__}: {exc}", flush=True)
            continue
        except OSError as exc:
            if final:
                raise Refusal("COPY_OFF_FAILED", f"{fp}: {type(exc).__name__}: {exc}") from None
            print(f"COPY_OFF_SKIPPED {fp.name}: {type(exc).__name__}: {exc}", flush=True)
            continue
    return copied


def load_done(manifest: Path) -> dict[str, tuple[int, str]]:
    done: dict[str, tuple[int, str]] = {}
    if manifest.exists():
        for ln in manifest.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("path"), str):
                if rec.get("partial"):
                    done.pop(rec["path"], None)
                elif "bytes" in rec and "sha256" in rec:
                    done[rec["path"]] = (int(rec["bytes"]), str(rec["sha256"]).lower())
    return done


def build_training_folder_manifest(watch: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    if watch.is_dir():
        for fp in sorted(watch.rglob("*")):
            if fp.is_symlink() or not fp.is_file():
                continue
            rel = fp.relative_to(watch).as_posix()
            size = fp.stat().st_size
            files.append({"path": rel, "bytes": size, "sha256": sha256_file(fp)})
    total_bytes = sum(int(f["bytes"]) for f in files)
    return {"files": files, "file_count": len(files), "total_bytes": total_bytes}


def run_write_train_manifest(args: argparse.Namespace) -> int:
    rec = build_training_folder_manifest(Path(args.watch))
    write_json(Path(args.out), rec)
    print(f"TRAIN_FOLDER_MANIFEST files={rec['file_count']} total_bytes={rec['total_bytes']}", flush=True)
    return 0


def _vm_free_bytes(target: Path, fake_env_var: str, usage_fn: Callable[[str], Any] = shutil.disk_usage) -> int:
    if os.environ.get("FAKE_VM_SITE") and os.environ.get(fake_env_var, "").strip():
        return int(os.environ[fake_env_var].strip())
    probe = Path(target)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return int(usage_fn(str(probe)).free)


def run_check_output_disk(
    args: argparse.Namespace, *, usage_fn: Callable[[str], Any] = shutil.disk_usage
) -> int:
    out_path = Path(args.out)
    try:
        projected = _parse_int_setting(args.projected_bytes, "TRAIN_OUTPUT_PROJECTION_REQUIRED", "projected_bytes")
    except Refusal as exc:
        write_json(out_path, {"ok": False, "refusal": exc.code})
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1
    free_b = _vm_free_bytes(Path(args.training_folder), "FAKE_VM_FREE_DISK_BYTES", usage_fn)
    ok = free_b >= projected
    rec = {
        "training_folder": str(args.training_folder),
        "projected_output_bytes": projected,
        "free_bytes": free_b,
        "ok": ok,
    }
    write_json(out_path, rec)
    print("OUTPUT_DISK_CHECK " + json.dumps(rec), flush=True)
    if not ok:
        print(
            refuse_line(
                "TRAIN_OUTPUT_DISK_LOW",
                f"projected output {projected} bytes exceeds free disk {free_b} bytes on {args.training_folder}",
            ),
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


def run_check_bundle_disk(
    args: argparse.Namespace, *, usage_fn: Callable[[str], Any] = shutil.disk_usage
) -> int:
    bundle_dir = Path(args.bundle_dir)
    out_path = Path(args.out)
    total_b = dir_bytes(bundle_dir)
    free_b = _vm_free_bytes(bundle_dir.parent, "FAKE_VM_BUNDLE_FREE_DISK_BYTES", usage_fn)
    ok = free_b >= total_b
    rec = {
        "bundle_dir": str(bundle_dir),
        "bundle_dir_bytes": total_b,
        "free_bytes": free_b,
        "ok": ok,
    }
    write_json(out_path, rec)
    print("BUNDLE_DISK_CHECK " + json.dumps(rec), flush=True)
    if not ok:
        print(
            refuse_line(
                "BUNDLE_DISK_LOW",
                f"lane3_out holds {total_b} bytes before tarring, exceeding free disk {free_b} bytes",
            ),
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


def verify_bundle_against_manifest(
    bundle_tar: Path, *, recovered_files: list[str] | None = None
) -> dict[str, Any]:
    if not bundle_tar.is_file() or not tarfile.is_tarfile(bundle_tar):
        raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"downloaded bundle {bundle_tar} is missing or not a tar archive")
    member_map: dict[str, tarfile.TarInfo] = {}
    with tarfile.open(bundle_tar, "r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            rel = m.name.lstrip("/")
            while rel.startswith("./"):
                rel = rel[2:]
            member_map[rel] = m
        tf_man_info = member_map.get("training_folder_manifest.json")
        if tf_man_info is None:
            raise Refusal(
                "TRAIN_OUTPUT_MANIFEST_MISMATCH",
                f"training_folder_manifest.json is missing from {bundle_tar.name}",
            )
        ext_man = tf.extractfile(tf_man_info)
        if ext_man is None:
            raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", "training_folder_manifest.json is unreadable in bundle")
        try:
            manifest = json.loads(ext_man.read().decode("utf-8"))
        except ValueError as exc:
            raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"invalid training_folder_manifest.json: {exc}") from None
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(files, list):
            raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", "training_folder_manifest.json has no files list")

        checked = 0
        total_bytes = 0
        missing_files: list[str] = []
        mismatched_files: list[str] = []
        bad_entries: list[dict[str, Any]] = []
        reasons: list[str] = []
        for entry in files:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"malformed manifest entry {entry!r}")
            rel_path = entry["path"]
            exp_bytes = int(entry.get("bytes", -1))
            exp_sha = str(entry.get("sha256", "")).lower()
            tar_rel = f"rung_outputs/{rel_path}"
            m_info = member_map.get(tar_rel)
            if m_info is None:
                missing_files.append(rel_path)
                bad_entries.append({
                    "path": rel_path,
                    "tar_path": tar_rel,
                    "expected_bytes": exp_bytes,
                    "expected_sha256": exp_sha,
                    "actual_bytes": None,
                    "actual_sha256": None,
                    "reason": "missing",
                })
                reasons.append(
                    f"missing training output in bundle: {tar_rel} (expected {exp_bytes} bytes, sha256={exp_sha})"
                )
                continue
            fh = tf.extractfile(m_info)
            if fh is None:
                mismatched_files.append(rel_path)
                bad_entries.append({
                    "path": rel_path,
                    "tar_path": tar_rel,
                    "expected_bytes": exp_bytes,
                    "expected_sha256": exp_sha,
                    "actual_bytes": None,
                    "actual_sha256": None,
                    "reason": "unreadable",
                })
                reasons.append(f"unreadable bundle member {tar_rel}")
                continue
            h = hashlib.sha256()
            got_bytes = 0
            with fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    got_bytes += len(chunk)
                    h.update(chunk)
            got_sha = h.hexdigest()
            if got_bytes != exp_bytes:
                mismatched_files.append(rel_path)
                bad_entries.append({
                    "path": rel_path,
                    "tar_path": tar_rel,
                    "expected_bytes": exp_bytes,
                    "expected_sha256": exp_sha,
                    "actual_bytes": got_bytes,
                    "actual_sha256": got_sha,
                    "reason": "size_mismatch",
                })
                reasons.append(f"size mismatch for {tar_rel}: got {got_bytes} bytes, expected {exp_bytes} bytes")
                continue
            if got_sha != exp_sha:
                mismatched_files.append(rel_path)
                bad_entries.append({
                    "path": rel_path,
                    "tar_path": tar_rel,
                    "expected_bytes": exp_bytes,
                    "expected_sha256": exp_sha,
                    "actual_bytes": got_bytes,
                    "actual_sha256": got_sha,
                    "reason": "sha256_mismatch",
                })
                reasons.append(f"sha256 mismatch for {tar_rel}: got {got_sha}, expected {exp_sha}")
                continue
            checked += 1
            total_bytes += got_bytes
        if bad_entries:
            raise Refusal(
                "TRAIN_OUTPUT_MANIFEST_MISMATCH",
                "; ".join(reasons),
                missing_files=missing_files,
                mismatched_files=mismatched_files,
                bad_entries=bad_entries,
                checked_files=checked,
            )
    ok_rec: dict[str, Any] = {"ok": True, "checked_files": checked, "total_bytes": total_bytes}
    if recovered_files:
        ok_rec["recovered_files"] = list(recovered_files)
    return ok_rec


def run_verify_bundle(args: argparse.Namespace) -> int:
    out_path = Path(args.out) if getattr(args, "out", None) else None
    recovered = list(getattr(args, "recovered_file", None) or [])
    try:
        rec = verify_bundle_against_manifest(Path(args.bundle_tar), recovered_files=recovered)
    except Refusal as exc:
        fail_rec: dict[str, Any] = {
            "ok": False,
            "refusal_code": exc.code,
            "why": exc.detail,
            "checked_files": exc.checked_files,
            "missing_files": exc.missing_files,
            "mismatched_files": exc.mismatched_files,
            "bad_entries": exc.bad_entries,
        }
        if recovered:
            fail_rec["recovered_files"] = recovered
        if out_path is not None:
            write_json(out_path, fail_rec)
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1
    if out_path is not None:
        write_json(out_path, rec)
    print("BUNDLE_MANIFEST_OK " + json.dumps(rec), flush=True)
    return 0


def repair_bundle_with_files(bundle_tar: Path, stage_dir: Path, rel_files: list[str]) -> dict[str, Any]:
    """Merge refetched training-folder files from `stage_dir/<rel>` into `bundle_tar`'s `rung_outputs/`
    and `rung_outputs/manifest.jsonl` (and refresh `train_facts.json` when present)."""
    if not bundle_tar.is_file() or not tarfile.is_tarfile(bundle_tar):
        raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"bundle {bundle_tar} is missing or not a tar archive")
    extract_dir = bundle_tar.parent / f".sdlab_repair_{os.getpid()}_{int(time.time() * 1000)}"
    tmp_tar = bundle_tar.with_suffix(bundle_tar.suffix + ".repaired.tmp")
    extract_root = extract_dir.resolve()
    repaired: list[str] = []
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(bundle_tar, "r:gz") as tf:
            for member in tf.getmembers():
                rel = member.name.lstrip("/")
                while rel.startswith("./"):
                    rel = rel[2:]
                if not rel or rel == ".":
                    continue
                parts = Path(rel).parts
                if ".." in parts:
                    raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"unsafe member path {member.name!r} in bundle")
                target = (extract_dir / rel).resolve()
                if extract_root not in target.parents and target != extract_root:
                    raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"unsafe member target {member.name!r} in bundle")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    src_fh = tf.extractfile(member)
                    if src_fh is not None:
                        with src_fh, target.open("wb") as out_fh:
                            shutil.copyfileobj(src_fh, out_fh)

        rung_dir = extract_dir / "rung_outputs"
        rung_dir.mkdir(parents=True, exist_ok=True)
        man_jsonl = rung_dir / "manifest.jsonl"
        for rel_path in rel_files:
            clean_rel = rel_path.strip().lstrip("/")
            if not clean_rel or ".." in Path(clean_rel).parts:
                raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"invalid repair path {rel_path!r}")
            staged = stage_dir / clean_rel
            if not staged.is_file():
                raise Refusal("TRAIN_OUTPUT_MANIFEST_MISMATCH", f"staged repair file missing: {staged}")
            dst = rung_dir / clean_rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged, dst)
            size = dst.stat().st_size
            sha = sha256_file(dst)
            is_partial = (
                dst.suffix == ".safetensors"
                and not _is_underscore_subpath(clean_rel)
                and not safetensors_complete(dst)
            )
            man_line = {
                "path": clean_rel,
                "bytes": size,
                "sha256": sha,
                "partial": is_partial,
                "recovered_by_refetch": True,
            }
            with man_jsonl.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(man_line) + "\n")
            repaired.append(clean_rel)

        if (extract_dir / "train_facts.json").is_file():
            run_finish(argparse.Namespace(lane3_out=str(extract_dir), failed_rc=None))

        tmp_tar.unlink(missing_ok=True)
        with tarfile.open(tmp_tar, "w:gz") as out_tf:
            out_tf.add(str(extract_dir), arcname=".")
        os.replace(tmp_tar, bundle_tar)
    finally:
        tmp_tar.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
    return {"ok": True, "repaired_files": repaired}


def run_repair_bundle(args: argparse.Namespace) -> int:
    try:
        rec = repair_bundle_with_files(
            Path(args.bundle_tar), Path(args.stage_dir), list(getattr(args, "rel_file", None) or [])
        )
    except Refusal as exc:
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1
    print("BUNDLE_REPAIRED " + json.dumps(rec), flush=True)
    return 0


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
    # Files a previous copy-off already took with identical size + sha256 are not copied twice.
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
    try:
        copy_off_once(watch, bundle, manifest, state, final=True)
    except Refusal as exc:
        print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
        return 1
    return 0


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run_checkpoint(args: argparse.Namespace) -> int:
    """Print the bundle path of the newest complete checkpoint the manifest lists (exit 1 if none)."""
    latest: dict[str, dict[str, Any]] = {}
    mp = Path(args.manifest)
    if mp.exists():
        for ln in mp.read_text(encoding="utf-8").splitlines():
            try:
                m = json.loads(ln)
            except ValueError:
                continue
            latest[m.get("path", "")] = m  # the newest line for a path counts
    good = [
        p
        for p, m in latest.items()
        if p.endswith(".safetensors")
        and not _is_underscore_subpath(p)
        and not m.get("partial")
        and m.get("bytes", 0) > 0
    ]
    if not good:
        return 1
    print(str(Path(args.bundle) / sorted(good)[-1]), flush=True)
    return 0


def run_finish(args: argparse.Namespace) -> int:
    out = Path(args.lane3_out)
    latest: dict[str, dict[str, Any]] = {}
    mp = out / "rung_outputs" / "manifest.jsonl"
    if mp.exists():
        for ln in mp.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            latest[rec["path"]] = rec  # a re-copied file: its newest line counts
    manifest_lines = list(latest.values())
    checkpoints = [
        m["path"]
        for m in manifest_lines
        if m["path"].endswith(".safetensors") and not _is_underscore_subpath(m["path"]) and not m.get("partial")
    ]
    partial_checkpoints = [
        m["path"]
        for m in manifest_lines
        if m["path"].endswith(".safetensors") and not _is_underscore_subpath(m["path"]) and m.get("partial")
    ]
    samples = [
        m["path"]
        for m in manifest_lines
        if Path(m["path"]).suffix.lower() in SAMPLE_IMAGE_SUFFIXES and not _is_underscore_subpath(m["path"])
    ]
    classified = set(checkpoints) | set(partial_checkpoints) | set(samples)
    other_files = [m["path"] for m in manifest_lines if m["path"] not in classified]
    tf_man_p = out / "training_folder_manifest.json"
    download = read_json(out / "model_download.json")
    facts = {
        "hf_token_used": bool(download.get("token_used")) if isinstance(download, dict) else False,
        "train_guards": read_json(out / "train_guards.json"),
        "model_download": download,
        "output_disk_check": read_json(out / "output_disk_check.json"),
        "rung_outputs": {
            "manifest": "rung_outputs/manifest.jsonl" if mp.exists() else None,
            "training_folder_manifest": "training_folder_manifest.json" if tf_man_p.is_file() else None,
            "checkpoints": checkpoints,
            "partial_checkpoints": partial_checkpoints,
            "samples": samples,
            "other_files": other_files,
            "all_files": [m["path"] for m in manifest_lines],
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
             f"{root}/lane3_rung.py download", "snapshot_download(repo_id=sys.argv[1]")
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
    train_dir = root / "lane3_train"
    if train_dir.is_dir():
        write_json(out / "training_folder_manifest.json", build_training_folder_manifest(train_dir))
    rung_dir = out / "rung_outputs"
    rung_dir.mkdir(parents=True, exist_ok=True)
    manifest = rung_dir / "manifest.jsonl"
    copy_off_once(train_dir, rung_dir, manifest, {"done": load_done(manifest)}, final=True)
    run_finish(argparse.Namespace(lane3_out=str(out), failed_rc=int(args.rc)))
    guards = root / "launch_guards.py"
    for f in out.rglob("*"):
        if f.is_file() and f.suffix in (".log", ".json", ".jsonl", ".txt") and guards.is_file():
            subprocess.run([sys.executable, str(guards), "--scrub-file", str(f)], check=False,
                           stdin=subprocess.DEVNULL)
    bundle.unlink(missing_ok=True)
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
    ds.add_argument("--manifest-sha", default=None)
    ds.add_argument("--src", default=None)
    ds.add_argument("--dest", default=None, help="place images and captions here; omit to verify only")
    ds.add_argument("--pack-archive", default=None, help="pack verified dataset images into one deterministic tar")
    ds.add_argument("--archive-sha-out", default=None, help="write packed tar sha256 here")
    ds.add_argument("--archive", default=None, help="verify tar sha256 + extract and re-verify every image on the VM")
    ds.add_argument("--archive-sha", default=None, help="expected 64-hex sha256 of --archive")
    ds.add_argument("--unlink-archive", action="store_true", help="remove --archive after extraction")

    cj = sub.add_parser("check-job")
    cj.add_argument("--template", required=True)
    cj.add_argument("--template-sha", default=None)
    cj.add_argument("--model-revision", default=None)
    cj.add_argument("--model-repo", default=None)
    cj.add_argument("--plan-out", default=None)

    pr = sub.add_parser("plan-run")
    pr.add_argument("--job-plan", required=True)
    pr.add_argument("--is-real-job", default="0")
    pr.add_argument("--optimizer-size-source", default=None)
    pr.add_argument("--explicit-download-timeout-s", default="")
    pr.add_argument("--download-timeout-source", default="default")
    pr.add_argument("--default-download-timeout-s", default="300")
    pr.add_argument("--download-floor-mb-s", default=None)
    pr.add_argument("--download-chunk-bytes", default=None)
    pr.add_argument("--upload-timeout-s", required=True)
    pr.add_argument("--upload-timeout-source", default="default")
    pr.add_argument("--upload-floor-mb-s", default=None)
    pr.add_argument("--upload-chunk-bytes", default=None)
    pr.add_argument("--dataset-archive", required=True)
    pr.add_argument("--seconds-per-step", default=None)
    pr.add_argument("--download-max-seconds", required=True)
    pr.add_argument("--setup-allowance-s", required=True)
    pr.add_argument("--rung-train-allowance-s", default="1800")
    pr.add_argument("--wall-s", required=True)
    pr.add_argument("--grace-s", required=True)
    pr.add_argument("--test-train-allowance-s", default="")
    pr.add_argument("--test-fetch-allowance-s", default="")
    pr.add_argument("--checkpoint-size-bytes", default=None)
    pr.add_argument("--optimizer-size-bytes", default=None)
    pr.add_argument("--samples-and-logs-bytes", default=None)
    pr.add_argument("--auxiliary-keep-all-bytes", default=None)
    pr.add_argument("--output-overhead-factor", default=None)
    pr.add_argument("--expected-model-bytes", default=None)
    pr.add_argument("--vm-disk-budget-gib", default=None)
    pr.add_argument("--out", default=None)

    r = sub.add_parser("render-job")
    r.add_argument("--template", required=True)
    r.add_argument("--template-sha", default=None)
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

    cod = sub.add_parser("check-output-disk")
    cod.add_argument("--training-folder", required=True)
    cod.add_argument("--projected-bytes", required=True)
    cod.add_argument("--out", required=True)

    wtm = sub.add_parser("write-train-manifest")
    wtm.add_argument("--watch", required=True)
    wtm.add_argument("--out", required=True)

    cbd = sub.add_parser("check-bundle-disk")
    cbd.add_argument("--bundle-dir", required=True)
    cbd.add_argument("--out", required=True)

    vb = sub.add_parser("verify-bundle")
    vb.add_argument("--bundle-tar", required=True)
    vb.add_argument("--out", default=None)
    vb.add_argument("--recovered-file", action="append", default=[])

    rb = sub.add_parser("repair-bundle")
    rb.add_argument("--bundle-tar", required=True)
    rb.add_argument("--stage-dir", required=True)
    rb.add_argument("--rel-file", action="append", default=[])

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

    ddb = sub.add_parser("dry-download-bounds")
    ddb.add_argument("--job-yaml", required=True)
    ddb.add_argument("--is-real-job", default="0")
    ddb.add_argument("--explicit-download-timeout-s", default="")
    ddb.add_argument("--download-timeout-source", default="default")
    ddb.add_argument("--default-download-timeout-s", default="300")
    ddb.add_argument("--download-chunk-bytes", default=None)
    ddb.add_argument("--download-floor-mb-s", default=None)
    ddb.add_argument("--checkpoint-size-bytes", default=None)
    ddb.add_argument("--optimizer-size-bytes", default=None)
    ddb.add_argument("--samples-and-logs-bytes", default=None)
    ddb.add_argument("--auxiliary-keep-all-bytes", default=None)

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
        "check-job": run_check_job,
        "plan-run": run_plan_run,
        "dry-download-bounds": run_dry_download_bounds,
        "render-job": run_render_job,
        "copy-off": run_copy_off,
        "check-output-disk": run_check_output_disk,
        "write-train-manifest": run_write_train_manifest,
        "check-bundle-disk": run_check_bundle_disk,
        "verify-bundle": run_verify_bundle,
        "repair-bundle": run_repair_bundle,
        "finish": run_finish,
        "model-check": run_model_check,
        "bundle-now": run_bundle_now,
        "checkpoint": run_checkpoint,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
