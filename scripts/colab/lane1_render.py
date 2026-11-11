#!/usr/bin/env python3
"""Lane 1 (render) VM bootstrap and durable ComfyUI queue driver (DESIGN-v3 §3.1, §3.5, §4.4, §7, G1-G3, G8).

Drives headless ComfyUI on loopback (127.0.0.1) via the `comfy_headless` library
(never launching the Gradio UI). Enforces CPython 3.14.9 in a uv venv, stages
weights by sha256 + cleared SPDX licence from a manifest, writes `window.json`,
executes `jobs.jsonl` -> `renders.jsonl` with idempotent resume after kill,
periodic copy-back, and PNG `tEXt` provenance stamping + immediate read-back
verification via `comfy_headless.read_png_text_chunks`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from lane3_rung import (  # noqa: E402
    GIB,
    REPO_ID_RE,
    REVISION_RE,
    Refusal,
    classify_hub_error,
    count_throttle_signals,
    dir_bytes,
    evaluate_probe,
    mask_log_text,
    measure_disk,
    measure_host_ram,
    measure_shm,
    parse_positive_number,
    query_driver,
    refuse_line,
    repo_cache_dir,
    safetensors_complete,
    sha256_file as hex_sha256_file,
    write_json,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PY_VERSION_EXPECTED = "3.14.9"
UV_PIN = "uv==0.13.5"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
CLEARED_LICENCES = {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0", "CC-BY-4.0"}
VALID_WEIGHT_DESTS = ("diffusion_models", "text_encoders", "vae", "loras")
REAL_MODEL_TEMPLATES = {"qwen_txt2img_lora", "qwen_image"}
FORBIDDEN_RENDER_TEMPLATES = {"stub_fixture_64"}
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MIB = 1024**2


@dataclass
class _WorkflowMetadataFallback:
    has_prompt: bool
    prompt: dict[str, Any] | None = None


def _read_png_text_chunks_fallback(png_source: Path | bytes) -> dict[str, str]:
    data = png_source.read_bytes() if isinstance(png_source, Path) else bytes(png_source)
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("PNG_INVALID: bad PNG signature")
    chunks: dict[str, str] = {}
    offset = len(PNG_SIGNATURE)
    size = len(data)
    while offset + 8 <= size:
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        ctype = data[offset + 4 : offset + 8]
        chunk_end = offset + 8 + length + 4
        if chunk_end > size:
            break
        payload = data[offset + 8 : offset + 8 + length]
        offset = chunk_end
        if ctype == b"tEXt":
            kw, sep, val = payload.partition(b"\x00")
            if sep:
                chunks[kw.decode("latin-1", errors="replace")] = val.decode("latin-1", errors="replace")
        elif ctype == b"IEND":
            break
    return chunks


def _read_workflow_metadata_fallback(png_source: Path | bytes) -> _WorkflowMetadataFallback:
    chunks = _read_png_text_chunks_fallback(png_source)
    raw_prompt = chunks.get("prompt")
    if not raw_prompt:
        return _WorkflowMetadataFallback(has_prompt=False, prompt=None)
    try:
        parsed = json.loads(raw_prompt)
        return _WorkflowMetadataFallback(has_prompt=isinstance(parsed, dict) and bool(parsed), prompt=parsed)
    except Exception:
        return _WorkflowMetadataFallback(has_prompt=False, prompt=None)


try:
    from comfy_headless import (
        ComfyClient,
        __version__ as COMFY_HEADLESS_VERSION,
        read_png_text_chunks,
        read_workflow_metadata,
    )
except ImportError:
    ComfyClient = None  # type: ignore[assignment]
    COMFY_HEADLESS_VERSION = "0.1.0-fallback"
    read_png_text_chunks = _read_png_text_chunks_fallback
    read_workflow_metadata = _read_workflow_metadata_fallback

STAMP_KEYS = {
    "owner": "sdlab:owner",
    "licence": "sdlab:licence",
    "canon_sha": "sdlab:canon_sha",
    "entry_id": "sdlab:entry_id",
    "entry_sha256": "sdlab:entry_sha256",
    "run_id": "sdlab:run_id",
    "workflow_sha": "sdlab:workflow_sha",
    "window_id": "sdlab:window_id",
}
REQUIRED_STAMP_FIELDS = ("owner", "licence", "canon_sha", "entry_id", "entry_sha256", "run_id")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def normalize_sha256(val: str | None) -> str | None:
    if not val or not isinstance(val, str):
        return None
    s = val.strip().lower()
    if s.startswith("sha256:"):
        s = s[7:]
    if len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        return None
    return f"sha256:{s}"


def assert_loopback_url(comfy_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(comfy_url)
    host = (parsed.hostname or "").lower()
    port = parsed.port or 8188
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"LANE1_NON_LOOPBACK_BIND: ComfyUI URL {comfy_url!r} is not loopback-only (127.0.0.1)")
    return host, port


def parse_proc_net_tcp_records(text: str, ipv6: bool = False) -> list[dict[str, str]]:
    """Parse Linux /proc/net/tcp or /proc/net/tcp6 and return TCP_LISTEN (st=0A) records with inode."""
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if len(parts) < 4 or ":" not in parts[1]:
            continue
        state = parts[3].upper()
        if state != "0A":
            continue
        addr_hex, port_hex = parts[1].split(":", 1)
        try:
            port = int(port_hex, 16)
            if ipv6 and len(addr_hex) == 32:
                words = [int(addr_hex[i : i + 8], 16) for i in range(0, 32, 8)]
                raw_ip = struct.pack("<IIII", *words)
                host = f"[{socket.inet_ntop(socket.AF_INET6, raw_ip)}]"
            elif not ipv6 and len(addr_hex) == 8:
                raw_ip = struct.pack("<I", int(addr_hex, 16))
                host = socket.inet_ntop(socket.AF_INET, raw_ip)
            else:
                continue
        except (ValueError, OSError):
            continue
        inode = parts[9] if len(parts) >= 10 else ""
        address = f"{host}:{port}"
        key = (address, inode)
        if key not in seen:
            seen.add(key)
            out.append({"address": address, "inode": inode})
    return out


def parse_proc_net_tcp(text: str, ipv6: bool = False) -> list[str]:
    """Parse Linux /proc/net/tcp or /proc/net/tcp6 and return TCP_LISTEN (st=0A) sockets."""
    out: list[str] = []
    for rec in parse_proc_net_tcp_records(text, ipv6=ipv6):
        addr = rec["address"]
        if addr not in out:
            out.append(addr)
    return out


def parse_ss_tln(text: str) -> list[str]:
    """Parse `ss -tln` output and return LISTEN local address:port strings."""
    out: list[str] = []
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if len(parts) < 4 or parts[0].upper() != "LISTEN":
            continue
        local_addr = parts[3].strip()
        if ":" in local_addr and local_addr not in out:
            out.append(local_addr)
    return out


def probe_pid_socket_inodes(
    comfy_pid: int | None = None,
    *,
    proc_root: Path | None = None,
    allow_host_proc: bool = True,
) -> tuple[set[str], str]:
    """Read `socket:[inode]` entries from `/proc/<pid>/fd` (symlink or fixture file)."""
    if comfy_pid is None:
        return set(), "port"

    fd_dir: Path | None = None
    if proc_root is not None:
        fd_dir = proc_root / str(comfy_pid) / "fd"
    elif allow_host_proc:
        fd_dir = Path(f"/proc/{comfy_pid}/fd")

    if fd_dir is None or not fd_dir.exists() or not fd_dir.is_dir():
        raise ValueError(
            f"LANE1_COMFY_PID_FD_UNREADABLE: fd directory for comfy_pid={comfy_pid} is absent or not a directory ({fd_dir})"
        )

    try:
        entries = sorted(fd_dir.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        raise ValueError(
            f"LANE1_COMFY_PID_FD_UNREADABLE: failed to read fd directory for comfy_pid={comfy_pid} ({fd_dir}): {exc}"
        ) from exc

    inodes: set[str] = set()
    for entry in entries:
        target = ""
        try:
            target = os.readlink(entry)
        except OSError:
            if proc_root is not None and entry.is_file():
                target = entry.read_text(encoding="utf-8", errors="replace").strip()
        if target.startswith("socket:[") and target.endswith("]"):
            inode = target[len("socket:[") : -1].strip()
            if inode.isdigit():
                inodes.add(inode)
    return inodes, "inode"


def inspect_comfy_listeners(
    sockets: list[str] | list[dict[str, str]],
    comfy_port: int = 8188,
    *,
    comfy_pid: int | None = None,
    proc_root: Path | None = None,
    allow_host_proc: bool = True,
) -> tuple[list[str], list[str], str]:
    """Partition listening sockets into ComfyUI sockets and other_listeners, verifying ComfyUI is loopback-only."""
    parsed_records: list[tuple[str, str, int, str]] = []
    for item in sockets:
        if isinstance(item, dict):
            raw_addr = str(item.get("address", "")).strip()
            inode = str(item.get("inode", "")).strip()
        else:
            raw_addr = str(item).strip()
            inode = ""
        if ":" not in raw_addr:
            continue
        host_part, port_str = raw_addr.rsplit(":", 1)
        try:
            port_num = int(port_str)
        except ValueError:
            continue
        parsed_records.append((raw_addr, host_part.strip(), port_num, inode))

    if not parsed_records:
        raise ValueError("LANE1_COMFY_SOCKET_NOT_FOUND: listening_sockets list has no valid address:port entries")

    inode_set, socket_match = probe_pid_socket_inodes(
        comfy_pid,
        proc_root=proc_root,
        allow_host_proc=allow_host_proc,
    )

    comfy_sockets: list[str] = []
    other_listeners: list[str] = []
    for addr, _host_part, port_num, inode in parsed_records:
        is_comfy = (bool(inode) and inode in inode_set) if socket_match == "inode" else (port_num == comfy_port)
        target_list = comfy_sockets if is_comfy else other_listeners
        if addr not in target_list:
            target_list.append(addr)

    if not comfy_sockets:
        raise ValueError(
            f"LANE1_COMFY_SOCKET_NOT_FOUND: no listening socket found for ComfyUI "
            f"(pid={comfy_pid}, port={comfy_port}) in {[r[0] for r in parsed_records]!r}"
        )

    for addr in comfy_sockets:
        host_part, _ = addr.rsplit(":", 1)
        host_clean = host_part.strip().lower()
        if host_clean.startswith("[") and host_clean.endswith("]"):
            host_clean = host_clean[1:-1]
        if host_clean not in ("127.0.0.1", "::1"):
            raise ValueError(
                f"LANE1_NON_LOOPBACK_SOCKET: ComfyUI socket {addr!r} is bound to non-loopback address "
                "(must be 127.0.0.1 or ::1)"
            )

    return comfy_sockets, other_listeners, socket_match


def verify_loopback_sockets(
    sockets: list[str] | list[dict[str, str]],
    comfy_port: int = 8188,
    *,
    comfy_pid: int | None = None,
    proc_root: Path | None = None,
) -> list[str]:
    comfy_sockets, _, _ = inspect_comfy_listeners(
        sockets,
        comfy_port,
        comfy_pid=comfy_pid,
        proc_root=proc_root,
        allow_host_proc=False,
    )
    return comfy_sockets


def probe_listening_socket_records(
    *,
    proc_root: Path | None = None,
    proc_net_tcp: Path | None = None,
    proc_net_tcp6: Path | None = None,
    ss_runner: Any | None = None,
) -> list[dict[str, str]]:
    """Read listening TCP socket records (address:port + inode) from /proc/net/tcp* or `ss -tln`."""
    any_proc_override = any(x is not None for x in (proc_root, proc_net_tcp, proc_net_tcp6))
    if any_proc_override:
        tcp_v4 = proc_net_tcp if proc_net_tcp is not None else (proc_root / "net" / "tcp" if proc_root is not None else None)
        tcp_v6 = proc_net_tcp6 if proc_net_tcp6 is not None else (proc_root / "net" / "tcp6" if proc_root is not None else None)
    else:
        tcp_v4 = Path("/proc/net/tcp")
        tcp_v6 = Path("/proc/net/tcp6")

    found: list[dict[str, str]] = []
    if tcp_v4 is not None and tcp_v4.exists():
        found.extend(parse_proc_net_tcp_records(tcp_v4.read_text(encoding="utf-8", errors="replace"), ipv6=False))
    if tcp_v6 is not None and tcp_v6.exists():
        found.extend(parse_proc_net_tcp_records(tcp_v6.read_text(encoding="utf-8", errors="replace"), ipv6=True))
    if not found:
        if ss_runner is not None:
            ss_out = ss_runner()
        elif not any_proc_override:
            try:
                proc = subprocess.run(["ss", "-tln"], capture_output=True, text=True, timeout=5, check=False)
                ss_out = proc.stdout or ""
            except Exception:
                ss_out = ""
        else:
            ss_out = ""
        for s in parse_ss_tln(ss_out):
            found.append({"address": s, "inode": ""})
    return found


def probe_listening_sockets(
    *,
    proc_root: Path | None = None,
    proc_net_tcp: Path | None = None,
    proc_net_tcp6: Path | None = None,
    ss_runner: Any | None = None,
) -> list[str]:
    """Read listening TCP sockets from /proc/net/tcp* or `ss -tln` without synthetic fallback."""
    out: list[str] = []
    for rec in probe_listening_socket_records(
        proc_root=proc_root,
        proc_net_tcp=proc_net_tcp,
        proc_net_tcp6=proc_net_tcp6,
        ss_runner=ss_runner,
    ):
        addr = rec["address"]
        if addr not in out:
            out.append(addr)
    return out


def probe_system_python(
    python_bin: str | Path = "/usr/bin/python3",
    runner: Any | None = None,
) -> str:
    """Measure the VM's system Python version via `<python_bin> --version` with no hardcoded default."""
    cmd = [str(python_bin), "--version"]
    if runner is not None:
        raw = str(runner(cmd) or "").strip()
    else:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            raw = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        except Exception as exc:
            raise ValueError(f"LANE1_NO_MEASURED_SYSTEM_PYTHON: failed to run {cmd!r}: {exc}") from exc
    for token in raw.replace("\n", " ").split():
        parts = token.strip().split(".")
        if len(parts) >= 2 and all(p.isdigit() for p in parts[:2]):
            return token.strip()
    raise ValueError(f"LANE1_NO_MEASURED_SYSTEM_PYTHON: could not parse version from {raw!r}")


def build_text_chunk(keyword: str, text: str) -> bytes:
    payload = keyword.encode("latin-1") + b"\x00" + text.encode("latin-1")
    ctype = b"tEXt"
    crc = zlib.crc32(ctype + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)


def write_png_text_chunks(png_bytes: bytes, text_map: dict[str, str]) -> bytes:
    if not png_bytes.startswith(PNG_SIGNATURE):
        raise ValueError("PNG_INVALID: bad PNG signature")
    replace_keys = set(text_map.keys())
    kept: list[bytes] = [PNG_SIGNATURE]
    iend_chunk: bytes | None = None
    offset = len(PNG_SIGNATURE)
    size = len(png_bytes)

    while offset + 8 <= size:
        (length,) = struct.unpack(">I", png_bytes[offset : offset + 4])
        ctype = png_bytes[offset + 4 : offset + 8]
        chunk_end = offset + 8 + length + 4
        if chunk_end > size:
            raise ValueError(f"PNG_INVALID: truncated {ctype!r} chunk")
        raw_chunk = png_bytes[offset:chunk_end]
        payload = png_bytes[offset + 8 : offset + 8 + length]
        offset = chunk_end

        if ctype == b"tEXt":
            kw, _, _ = payload.partition(b"\x00")
            if kw.decode("latin-1", errors="replace") in replace_keys:
                continue
        if ctype == b"IEND":
            iend_chunk = raw_chunk
            break
        kept.append(raw_chunk)

    for k, v in text_map.items():
        if v is not None:
            kept.append(build_text_chunk(k, str(v)))

    kept.append(iend_chunk or b"\x00\x00\x00\x00IEND\xaeB`\x82")
    return b"".join(kept)


def unwrap_text_val(val: str | None) -> str | None:
    if val is None:
        return None
    t = val.strip()
    if len(t) >= 2 and t.startswith('"') and t.endswith('"'):
        try:
            parsed = json.loads(t)
            if isinstance(parsed, str):
                return parsed
        except Exception:
            return val
    return val


def stamp_png_provenance(png_bytes: bytes, stamp: dict[str, Any]) -> bytes:
    for req in REQUIRED_STAMP_FIELDS:
        v = stamp.get(req)
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"PNG_STAMP_MISSING: missing required field {req!r}")
    text_map: dict[str, str] = {}
    for field_name, chunk_key in STAMP_KEYS.items():
        v = stamp.get(field_name)
        if isinstance(v, str) and v.strip():
            text_map[chunk_key] = v
    return write_png_text_chunks(png_bytes, text_map)


def verify_png_provenance(png_source: Path | bytes, expected: dict[str, Any]) -> dict[str, str]:
    chunks = read_png_text_chunks(png_source)
    parsed: dict[str, str] = {}
    for field_name, chunk_key in STAMP_KEYS.items():
        raw_val = chunks.get(chunk_key)
        unwrapped = unwrap_text_val(raw_val)
        if unwrapped is not None:
            parsed[field_name] = unwrapped
    for req in REQUIRED_STAMP_FIELDS:
        if not parsed.get(req):
            raise ValueError(f"PNG_STAMP_MISSING: chunk {STAMP_KEYS[req]!r} missing on read-back")
    for field_name, exp_val in expected.items():
        if exp_val is None or field_name not in STAMP_KEYS:
            continue
        if parsed.get(field_name) != str(exp_val):
            raise ValueError(
                f"PNG_STAMP_MISMATCH: {field_name} got {parsed.get(field_name)!r}, expected {exp_val!r}"
            )
    return parsed


def build_qwen_lora_graph(job: dict[str, Any]) -> dict[str, Any]:
    """Build the Qwen-Image LoRA-aware API graph (G3: LoraLoaderModelOnly chain 40.. between 37 and 66)."""
    pins = job.get("model_pins") or {}
    unet = (pins.get("base") or {}).get("name") or "qwen_image_fp8_e4m3fn.safetensors"
    clip = (pins.get("text_encoder") or {}).get("name") or "qwen_2.5_vl_7b_fp8_scaled.safetensors"
    vae = (pins.get("vae") or {}).get("name") or "qwen_image_vae.safetensors"
    loras = job.get("loras") or pins.get("loras") or []

    nodes: dict[str, Any] = {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip, "type": "qwen_image"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("prompt", ""), "clip": ["38", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("negative", ""), "clip": ["38", 0]}},
    }
    model_out = ["37", 0]
    for idx, lora in enumerate(loras):
        lid = str(40 + idx)
        weight = lora.get("weight", lora.get("strength_model", 1.0))
        nodes[lid] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "lora_name": lora.get("name") or lora.get("lora_name"),
                "strength_model": 1.0 if weight is None else float(weight),
                "model": model_out,
            },
        }
        model_out = [lid, 0]

    nodes.update(
        {
            "66": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": float(job.get("shift", 3.1)), "model": model_out}},
            "5": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {"width": int(job.get("width", 1024)), "height": int(job.get("height", 1024)), "batch_size": 1},
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(job.get("seed", 0)),
                    "steps": int(job.get("steps", 22)),
                    "cfg": float(job.get("cfg", 3.5)),
                    "sampler_name": job.get("sampler", "euler"),
                    "scheduler": job.get("scheduler", "simple"),
                    "denoise": 1.0,
                    "model": ["66", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": f"sdl_{job.get('job_id', 'job')}", "images": ["8", 0]},
            },
        }
    )
    return nodes


def build_stub_fixture_graph(job: dict[str, Any]) -> dict[str, Any]:
    """Minimal 64x64 no-weights ComfyUI fixture graph (EmptyImage -> ImageInvert -> SaveImage)."""
    seed = int(job.get("seed", 0))
    color = abs(seed) & 0xFFFFFF
    width = int(job.get("width", 64))
    height = int(job.get("height", 64))
    return {
        "1": {"class_type": "EmptyImage", "inputs": {"width": width, "height": height, "batch_size": 1, "color": color}},
        "2": {"class_type": "ImageInvert", "inputs": {"image": ["1", 0]}},
        "3": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": f"sdl_{job.get('job_id', 'stub')}", "images": ["2", 0]},
        },
    }


def stage_weights(manifest_path: Path, staging_dir: Path | None = None) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("LANE1_WEIGHT_MANIFEST_EMPTY: manifest must be a non-empty list")
    staged = []
    for item in manifest:
        name = item.get("name")
        exp_sha = normalize_sha256(item.get("sha256"))
        lic = item.get("licence_id")
        if not name or not exp_sha:
            raise ValueError(f"LANE1_WEIGHT_SHA_MISSING: invalid name or sha256 in {item!r}")
        if lic not in CLEARED_LICENCES or not item.get("licence_url") or not item.get("date_read"):
            raise ValueError(f"LANE1_WEIGHT_LICENCE_INVALID: {name} has uncleared licence {lic!r}")
        local_path = Path(item["local_path"]) if item.get("local_path") else (staging_dir / name if staging_dir else None)
        verified = False
        if local_path is not None:
            if not local_path.exists():
                raise ValueError(f"LANE1_WEIGHT_FILE_MISSING: {local_path} does not exist")
            got_sha = sha256_file(local_path)
            if got_sha != exp_sha:
                raise ValueError(f"LANE1_WEIGHT_SHA_MISMATCH: {name} got {got_sha}, expected {exp_sha}")
            verified = True
        staged.append({**item, "sha256": exp_sha, "verified": verified})
    return staged


def write_window_json(
    window_json_path: Path,
    *,
    window_id: str,
    comfy_url: str,
    system_python: str | None = None,
    sockets: list[str] | None = None,
    comfyui_commit: str | None = None,
    card: str = "CPU",
    cap: float = 0.05,
    wall_s: int = 3000,
    margin: float = 0.01,
    expected_python: str | None = None,
    comfy_pid: int | None = None,
    proc_root: Path | None = None,
    proc_net_tcp: Path | None = None,
    proc_net_tcp6: Path | None = None,
    ss_runner: Any | None = None,
    system_python_bin: str | Path = "/usr/bin/python3",
    system_python_runner: Any | None = None,
) -> dict[str, Any]:
    host, port = assert_loopback_url(comfy_url)
    py_ver = sys.version.split()[0]
    exp_py = expected_python or os.environ.get("SDLAB_EXPECTED_PYTHON", PY_VERSION_EXPECTED)
    if py_ver != exp_py:
        raise ValueError(f"LANE1_PYTHON_VERSION_MISMATCH: venv python is {py_ver}, expected {exp_py}")
    py_sha = sha256_file(Path(sys.executable))
    try:
        uv_out = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=10, check=False).stdout.strip()
    except Exception:
        uv_out = UV_PIN
    measured_sys_py = (
        system_python.strip()
        if isinstance(system_python, str) and system_python.strip()
        else probe_system_python(python_bin=system_python_bin, runner=system_python_runner)
    )
    raw_records: list[str] | list[dict[str, str]] = (
        list(sockets)
        if sockets is not None
        else probe_listening_socket_records(
            proc_root=proc_root,
            proc_net_tcp=proc_net_tcp,
            proc_net_tcp6=proc_net_tcp6,
            ss_runner=ss_runner,
        )
    )
    if not raw_records:
        raise ValueError(
            "LANE1_NO_MEASURED_SOCKETS: no listening TCP sockets found in /proc/net/tcp* or ss -tln"
        )
    allow_host_proc = all(x is None for x in (proc_root, proc_net_tcp, proc_net_tcp6, sockets))
    comfy_sockets, other_listeners, socket_match = inspect_comfy_listeners(
        raw_records,
        port,
        comfy_pid=comfy_pid,
        proc_root=proc_root,
        allow_host_proc=allow_host_proc,
    )

    record = {
        "window_id": window_id,
        "lane": "render",
        "card": card,
        "vm_gate": {
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
            "platform": sys.platform,
        },
        "system_python": measured_sys_py,
        "python": py_ver,
        "python_sha256": py_sha,
        "uv": uv_out or UV_PIN,
        "comfyui_commit": comfyui_commit,
        "comfy_headless_version": COMFY_HEADLESS_VERSION,
        "comfy_bind": f"{host}:{port}",
        "comfy_pid": comfy_pid,
        "socket_match": socket_match,
        "listening_sockets": comfy_sockets,
        "other_listeners": other_listeners,
        "override_sha256": None,
        "cap": cap,
        "wall_s": wall_s,
        "margin": margin,
        "start_balance": None,
        "end_balance": None,
        "rate_measured": None,
        "opened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "closed_at": None,
    }
    window_json_path.parent.mkdir(parents=True, exist_ok=True)
    window_json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def download_comfy_image(comfy_url: str, filename: str, subfolder: str = "", img_type: str = "output") -> bytes:
    qs = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": img_type})
    url = f"{comfy_url.rstrip('/')}/view?{qs}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def pick_history_image(history_entry: dict[str, Any]) -> dict[str, str]:
    outputs = history_entry.get("outputs") or {}
    for node_id in sorted(outputs.keys(), key=lambda k: int(k) if str(k).isdigit() else 0, reverse=True):
        images = (outputs.get(node_id) or {}).get("images") or []
        if images:
            return images[0]
    raise RuntimeError(f"No output images in ComfyUI history entry: {history_entry!r}")


def load_completed(renders_path: Path, out_dir: Path) -> dict[str, dict[str, Any]]:
    done: dict[str, dict[str, Any]] = {}
    if not renders_path.exists():
        return done
    for line in renders_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("status") == "ok" and row.get("job_id") and row.get("output_file"):
            png_path = out_dir / row["output_file"]
            if png_path.exists() and sha256_file(png_path) == row.get("png_sha256"):
                try:
                    verify_png_provenance(
                        png_path,
                        {
                            "owner": row.get("owner"),
                            "licence": row.get("licence"),
                            "canon_sha": row.get("canon_sha"),
                            "entry_id": row.get("entry_id"),
                            "entry_sha256": row.get("entry_sha256"),
                            "run_id": row.get("run_id"),
                        },
                    )
                    done[row["job_id"]] = row
                except Exception:
                    pass
    return done


def sync_copy_back(renders_path: Path, current_json: Path, out_dir: Path, copy_back_dir: Path, files: set[str]) -> None:
    copy_back_dir.mkdir(parents=True, exist_ok=True)
    if renders_path.exists():
        shutil.copy2(renders_path, copy_back_dir / "renders.jsonl")
    if current_json.exists():
        shutil.copy2(current_json, copy_back_dir / "current.json")
    for fname in sorted(files):
        src = out_dir / fname
        if src.exists():
            shutil.copy2(src, copy_back_dir / fname)


def validate_weights_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    """Validate a `--weights-manifest` JSON list: `{repo, revision, file, dest, sha256, licence_id}`."""
    if not manifest_path.is_file():
        raise Refusal("WEIGHTS_MANIFEST_INVALID", f"{manifest_path} does not exist")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("WEIGHTS_MANIFEST_INVALID", f"{manifest_path}: invalid JSON ({type(exc).__name__})") from None
    if not isinstance(raw, list) or not raw:
        raise Refusal("WEIGHTS_MANIFEST_INVALID", f"{manifest_path} must be a non-empty JSON list")

    entries: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise Refusal("WEIGHTS_MANIFEST_INVALID", f"row {idx}: manifest row must be an object")
        lic = item.get("licence_id")
        if not isinstance(lic, str) or not lic.strip():
            raise Refusal("WEIGHTS_LICENCE_INVALID", f"row {idx}: missing licence_id")
        lic_clean = lic.strip()
        if lic_clean not in CLEARED_LICENCES:
            raise Refusal("WEIGHTS_LICENCE_INVALID", f"row {idx}: licence_id {lic_clean!r} is not cleared")
        repo = item.get("repo")
        if not isinstance(repo, str) or not REPO_ID_RE.match(repo.strip()):
            raise Refusal("WEIGHTS_MANIFEST_INVALID", f"row {idx}: {repo!r} is not a Hugging Face repo id")
        revision = item.get("revision")
        if not isinstance(revision, str) or not REVISION_RE.match(revision.strip()):
            raise Refusal("WEIGHTS_REVISION_INVALID", f"row {idx}: revision {revision!r} is not a 40-hex commit")
        rel_file = item.get("file")
        if (
            not isinstance(rel_file, str)
            or not rel_file.strip()
            or "\\" in rel_file
            or rel_file.startswith("/")
            or any(part in ("", ".", "..") for part in rel_file.strip().split("/"))
        ):
            raise Refusal("WEIGHTS_MANIFEST_INVALID", f"row {idx}: invalid relative file {rel_file!r}")
        dest = item.get("dest")
        if dest not in VALID_WEIGHT_DESTS:
            raise Refusal("WEIGHTS_DEST_INVALID", f"row {idx}: dest {dest!r} must be one of {VALID_WEIGHT_DESTS}")
        norm_sha = normalize_sha256(item.get("sha256"))
        if norm_sha is None:
            raise Refusal("WEIGHTS_MANIFEST_INVALID", f"row {idx}: sha256 must be a 64-hex digest")
        entries.append(
            {
                "repo": repo.strip(),
                "revision": revision.strip(),
                "file": rel_file.strip(),
                "dest": dest,
                "sha256": norm_sha[7:],
                "licence_id": lic_clean,
                "hf_token_required": bool(item.get("hf_token_required", False)),
            }
        )
    return entries


def validate_render_jobs(jobs_path: Path, expected_jobs_sha256: str | None) -> dict[str, Any]:
    """Check `jobs.jsonl` against `--jobs-sha256` and validate every row without logging prompt text."""
    exp_norm = normalize_sha256(expected_jobs_sha256)
    if exp_norm is None:
        raise Refusal("RENDER_JOBS_SHA_REQUIRED", "--jobs-sha256 must be a 64-hex sha256")
    if not jobs_path.is_file():
        raise Refusal("JOBS_FILE_MISSING", f"{jobs_path} does not exist")
    exp_hex = exp_norm[7:]
    actual_hex = hex_sha256_file(jobs_path)
    if actual_hex != exp_hex:
        raise Refusal("JOBS_SHA_MISMATCH", f"{jobs_path} sha256={actual_hex} expected={exp_hex}")

    raw_lines = [ln for ln in jobs_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not raw_lines:
        raise Refusal("RENDER_JOB_INVALID", f"{jobs_path} contains no jobs")

    seen_ids: set[str] = set()
    first_job_id: str | None = None
    for idx, line in enumerate(raw_lines):
        try:
            row = json.loads(line)
        except ValueError:
            raise Refusal("RENDER_JOB_INVALID", f"row {idx}: malformed JSON") from None
        if not isinstance(row, dict):
            raise Refusal("RENDER_JOB_INVALID", f"row {idx}: job row must be a JSON object")
        job_id = row.get("job_id")
        if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id) or job_id in seen_ids:
            raise Refusal("RENDER_JOB_INVALID", f"row {idx}: missing, unsafe or duplicate job_id")
        seen_ids.add(job_id)
        if first_job_id is None:
            first_job_id = job_id

        template_id = row.get("template_id")
        if (
            not isinstance(template_id, str)
            or not template_id.strip()
            or template_id.strip() in FORBIDDEN_RENDER_TEMPLATES
            or template_id.strip() not in REAL_MODEL_TEMPLATES
        ):
            raise Refusal(
                "JOB_TEMPLATE_INVALID",
                f"job {job_id}: template_id {template_id!r} must be a real-model template (never stub_fixture_64)",
            )
        for req_str in ("run_id", "canon_sha", "entry_id", "entry_sha256"):
            val = row.get(req_str)
            if not isinstance(val, str) or not val.strip():
                raise Refusal("RENDER_JOB_INVALID", f"job {job_id}: missing {req_str}")
        prompt = row.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise Refusal("RENDER_JOB_INVALID", f"job {job_id}: missing prompt")
        seed = row.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise Refusal("RENDER_JOB_INVALID", f"job {job_id}: missing or non-integer seed")
        width = row.get("width")
        height = row.get("height")
        if (
            not isinstance(width, int)
            or isinstance(width, bool)
            or width <= 0
            or not isinstance(height, int)
            or isinstance(height, bool)
            or height <= 0
        ):
            raise Refusal("RENDER_JOB_INVALID", f"job {job_id}: missing or non-positive width/height")
        steps = row.get("steps")
        if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
            raise Refusal("RENDER_JOB_INVALID", f"job {job_id}: missing or non-positive steps")

    return {"jobs_sha256": actual_hex, "job_count": len(seen_ids), "first_job_id": first_job_id}


def run_validate_inputs(
    *,
    manifest_path: Path,
    jobs_path: Path | None = None,
    jobs_sha256: str | None = None,
    allow_no_jobs: bool = False,
) -> dict[str, Any]:
    entries = validate_weights_manifest(manifest_path)
    needs_token = any(e["hf_token_required"] for e in entries)
    if needs_token:
        tok = os.environ.get("HF_TOKEN_GGUF_READ", "")
        if not tok or any(ch.isspace() for ch in tok):
            raise Refusal(
                "HF_READ_TOKEN_MISSING",
                "manifest marks hf_token_required=true; pass token via HF_TOKEN_GGUF_READ environment variable",
            )
    jobs_info: dict[str, Any] | None = None
    if not allow_no_jobs or jobs_path is not None:
        if jobs_path is None:
            raise Refusal("RENDER_JOBS_REQUIRED", "--render needs --jobs <jobs.jsonl>")
        jobs_info = validate_render_jobs(jobs_path, jobs_sha256)
    return {
        "manifest_entries": len(entries),
        "hf_token_required": needs_token,
        "jobs": jobs_info,
    }


def lane1_gpu_smoke(
    torch_mod: Any = None,
    clock: Callable[[], float] = time.perf_counter,
    target_s: float = 5.0,
) -> dict[str, Any]:
    """Timed bf16 1024x1024 CUDA matmul check through Lane 1's torch."""
    if torch_mod is None:
        import torch as torch_mod  # noqa: PLC0415 - imported on the VM only
    rec: dict[str, Any] = {
        "torch_version": getattr(torch_mod, "__version__", None),
        "torch_cuda": getattr(getattr(torch_mod, "version", None), "cuda", None),
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
    rec.update(
        {
            "matmul_iters": iters,
            "matmul_seconds": round(elapsed, 3),
            "matmul_tflops": round(iters * 2 * 1024**3 / max(elapsed, 1e-9) / 1e12, 2),
        }
    )
    return rec


def run_vm_guards(
    *,
    hf_home: Path,
    models_dir: Path,
    lane1_out: Path,
    disk_required_gib: float,
    smoke_seconds: float,
    ram_required_gib: str | None,
    meminfo_path: Path,
    shm_path: Path,
    out_path: Path,
    cpu_stub: bool = False,
    smoke_fn: Callable[..., dict[str, Any]] = lane1_gpu_smoke,
    driver_fn: Callable[[], dict[str, Any]] = query_driver,
    disk_usage_fn: Callable[[str], Any] = shutil.disk_usage,
) -> int:
    rec: dict[str, Any] = {"cpu_stub": cpu_stub}
    refusals: list[tuple[str, str]] = []

    try:
        ram_req = parse_positive_number(ram_required_gib, "HOST_RAM_THRESHOLD_MISSING", "LANE1_HOST_RAM_REQUIRED_GIB")
    except Refusal as exc:
        ram_req = None
        refusals.append((exc.code, exc.detail))

    if cpu_stub:
        rec["gpu"] = {"skipped_cpu_stub": True, "ok": True}
    else:
        gpu: dict[str, Any] = dict(driver_fn())
        try:
            gpu.update(smoke_fn(target_s=float(smoke_seconds)))
            gpu["ok"] = True
        except Exception as exc:  # noqa: BLE001
            gpu["ok"] = False
            gpu["error"] = f"{type(exc).__name__}: {exc}".splitlines()[0]
            refusals.append(("GPU_SMOKE_FAILED", gpu["error"]))
        rec["gpu"] = gpu

    disk = measure_disk([hf_home, models_dir, lane1_out], float(disk_required_gib), disk_usage_fn)
    rec["disk"] = disk
    if not disk["ok"]:
        low = [fs for fs in disk["filesystems"] if fs["free_bytes"] < float(disk_required_gib) * GIB]
        refusals.append(
            (
                "DISK_FREE_LOW",
                "; ".join(f"{fs['measured_at']} free {fs['free_gib']} GiB < {disk_required_gib} GiB" for fs in low),
            )
        )

    meminfo_text = meminfo_path.read_text(encoding="utf-8", errors="replace")
    ram = measure_host_ram(meminfo_text, ram_req if ram_req is not None else 0.0)
    if ram_req is None:
        ram["required_available_gib"] = None
        ram["ok"] = False
    elif not ram["ok"]:
        refusals.append(
            (
                "HOST_RAM_LOW",
                f"MemAvailable {ram['mem_available_gib']} GiB < required {ram_req} GiB (MemTotal {ram['mem_total_gib']} GiB)",
            )
        )
    rec["host_ram"] = ram
    rec["shm"] = measure_shm(shm_path, disk_usage_fn)
    rec["refusals"] = [code for code, _ in refusals]
    write_json(out_path, rec)
    print("RENDER_GUARDS " + json.dumps(rec), flush=True)
    for code, detail in refusals:
        print(refuse_line(code, detail), file=sys.stderr, flush=True)
    return 1 if refusals else 0


FILE_DOWNLOAD_CHILD = (
    "import os, sys\n"
    "from huggingface_hub import hf_hub_download\n"
    "path = hf_hub_download(repo_id=sys.argv[1], filename=sys.argv[2], revision=sys.argv[3], "
    "token=os.environ.get('HF_TOKEN') or False)\n"
    "print('FILE_PATH ' + path, flush=True)\n"
)


def expected_file_bytes(repo_id: str, revision: str, filename: str, token: str | None = None) -> int:
    from huggingface_hub import HfApi  # noqa: PLC0415

    info = HfApi().model_info(repo_id, revision=revision, files_metadata=True, token=token or False)
    siblings = list(info.siblings or [])
    for sib in siblings:
        if getattr(sib, "rfilename", None) == filename:
            return int(sib.size or 0)
    return sum(int(s.size or 0) for s in siblings)


def _fail_weights(out_path: Path, rec: dict[str, Any], code: str, detail: str) -> int:
    rec["refusal"] = code
    write_json(out_path, rec)
    print("WEIGHTS_DOWNLOAD " + json.dumps(rec), flush=True)
    print(refuse_line(code, detail), file=sys.stderr, flush=True)
    return 1


def run_weights_download(
    *,
    manifest_path: Path,
    hf_home: Path,
    models_dir: Path,
    max_seconds_raw: str | None,
    probe_seconds: float = 60.0,
    probe_bytes: int = 2 * GIB,
    poll_s: float = 0.25,
    log_path: Path,
    out_path: Path,
    expected_fn: Callable[..., int] = expected_file_bytes,
    popen: Callable[..., Any] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    token = os.environ.get("HF_TOKEN_GGUF_READ") or None
    offline = os.environ.get("HF_HUB_OFFLINE") == "1"
    rec: dict[str, Any] = {
        "token_used": "HF_TOKEN_GGUF_READ" in os.environ,
        "offline": offline,
        "files": [],
    }
    try:
        max_seconds = parse_positive_number(max_seconds_raw, "DOWNLOAD_LIMIT_MISSING", "LANE1_DOWNLOAD_MAX_SECONDS")
        entries = validate_weights_manifest(manifest_path)
    except Refusal as exc:
        return _fail_weights(out_path, rec, exc.code, exc.detail)

    rec["max_seconds"] = max_seconds
    rec["probe_window"] = {"seconds": float(probe_seconds), "bytes": int(probe_bytes)}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8", newline="\n")

    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HF_TOKEN_GGUF_READ")
    }
    env.update({"HF_HOME": str(hf_home), "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "PYTHONUNBUFFERED": "1"})
    if token is not None:
        env["HF_TOKEN"] = token

    overall_start = clock()
    for entry in entries:
        repo = entry["repo"]
        revision = entry["revision"]
        filename = entry["file"]
        dest = entry["dest"]
        exp_sha = entry["sha256"]

        cache = repo_cache_dir(hf_home, repo)
        baseline = dir_bytes(cache)
        if offline:
            expected = baseline
        else:
            try:
                expected = int(expected_fn(repo, revision, filename, token))
            except Exception as exc:  # noqa: BLE001
                code, detail = classify_hub_error(exc)
                return _fail_weights(out_path, rec, code, f"model_info {repo}@{revision}: {detail}")
        remaining = max(expected - baseline, 0)
        spent = max(clock() - overall_start, 0.0)
        budget_s = max(max_seconds - spent, 0.01)

        file_start = clock()
        hard_stop = threading.Event()
        item_log = log_path.parent / f".dl_{len(rec['files'])}.log"
        with item_log.open("w", encoding="utf-8", newline="\n") as log_fh:
            proc = popen(
                [sys.executable, "-c", FILE_DOWNLOAD_CHILD, repo, filename, revision],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=env,
            )

            def _hard_limit(p: Any = proc, hs: threading.Event = hard_stop) -> None:
                if p.poll() is None:
                    hs.set()
                    p.kill()

            timer = threading.Timer(budget_s, _hard_limit)
            timer.daemon = True
            timer.start()
            probe: dict[str, Any] | None = None
            try:
                while proc.poll() is None:
                    sleep(float(poll_s))
                    elapsed = clock() - file_start
                    new_bytes = max(dir_bytes(cache) - baseline, 0)
                    if not offline and probe is None and (elapsed >= float(probe_seconds) or new_bytes >= int(probe_bytes)):
                        probe = evaluate_probe(new_bytes, elapsed, remaining, budget_s)
                        print("WEIGHTS_DOWNLOAD_PROBE " + json.dumps(probe), flush=True)
                        if probe["too_slow"]:
                            proc.kill()
                            proc.wait()
                            break
                rc = proc.wait()
            finally:
                timer.cancel()

        elapsed = clock() - file_start
        raw_log = item_log.read_text(encoding="utf-8", errors="replace")
        item_log.unlink(missing_ok=True)
        scrubbed_log = mask_log_text(raw_log)
        if token is not None and token in scrubbed_log:
            scrubbed_log = scrubbed_log.replace(token, "[REDACTED]")
        with log_path.open("a", encoding="utf-8", newline="\n") as main_log:
            main_log.write(scrubbed_log)
        log_lines = raw_log.splitlines()
        new_bytes = max(dir_bytes(cache) - baseline, 0)
        downloaded_path = next((ln.split(" ", 1)[1].strip() for ln in log_lines if ln.startswith("FILE_PATH ")), None)

        file_rec: dict[str, Any] = {
            "repo": repo,
            "revision": revision,
            "file": filename,
            "dest": dest,
            "licence_id": entry["licence_id"],
            "expected_bytes": expected,
            "downloaded_bytes": new_bytes,
            "seconds": round(elapsed, 2),
            "probe": probe,
            "hard_limit_hit": hard_stop.is_set(),
            **count_throttle_signals(log_lines),
        }
        rec["files"].append(file_rec)

        if hard_stop.is_set():
            return _fail_weights(
                out_path,
                rec,
                "DOWNLOAD_TOO_SLOW",
                f"hard limit: {repo}:{filename} still downloading after {budget_s:.1f} s ({new_bytes} bytes)",
            )
        if probe is not None and probe["too_slow"]:
            return _fail_weights(
                out_path,
                rec,
                "DOWNLOAD_TOO_SLOW",
                f"probe {probe['probe_rate_mb_s']} MB/s over {probe['probe_seconds']} s projects "
                f"{probe['projected_total_seconds']} s for {remaining} bytes > limit {budget_s:.1f} s",
            )
        if rc != 0 or not downloaded_path or not Path(downloaded_path).is_file():
            tail = mask_log_text(" | ".join(log_lines[-3:]))
            if token is not None and token in tail:
                tail = "[the download log tail is withheld: it held the read token]"
            return _fail_weights(out_path, rec, "MODEL_DOWNLOAD_FAILED", f"hf_hub_download {repo}:{filename} rc={rc}: {tail}")

        target_dir = models_dir / dest
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / Path(filename).name
        shutil.copyfile(downloaded_path, target_path)
        got_sha = hex_sha256_file(target_path)
        file_rec["staged_path"] = str(target_path)
        file_rec["sha256"] = got_sha
        if got_sha != exp_sha:
            target_path.unlink(missing_ok=True)
            return _fail_weights(
                out_path,
                rec,
                "WEIGHTS_SHA_MISMATCH",
                f"{dest}/{target_path.name} sha256={got_sha} expected={exp_sha}",
            )
        if target_path.suffix == ".safetensors":
            if not safetensors_complete(target_path):
                target_path.unlink(missing_ok=True)
                return _fail_weights(
                    out_path,
                    rec,
                    "WEIGHTS_CORRUPT",
                    f"{dest}/{target_path.name} failed safetensors header/offset unpack check",
                )
            file_rec["safetensors_verified"] = True

    write_json(out_path, rec)
    print("WEIGHTS_DOWNLOAD " + json.dumps(rec), flush=True)
    return 0


def merge_render_facts(lane1_out: Path, *, render_state: str | None = None, failed_rc: int | None = None) -> dict[str, Any]:
    """Merge `render_guards.json` and `weights_download.json` into `vm_window.json`."""
    vm_win_path = lane1_out / "vm_window.json"
    rec: dict[str, Any] = {}
    if vm_win_path.is_file():
        try:
            rec.update(json.loads(vm_win_path.read_text(encoding="utf-8")))
        except ValueError:
            pass
    guards_p = lane1_out / "render_guards.json"
    if guards_p.is_file():
        rec["render_guards"] = json.loads(guards_p.read_text(encoding="utf-8"))
    dl_p = lane1_out / "weights_download.json"
    if dl_p.is_file():
        dl = json.loads(dl_p.read_text(encoding="utf-8"))
        rec["weights_download"] = dl
        rec["hf_token_used"] = bool(dl.get("token_used"))
    if render_state is not None:
        rec["render"] = render_state
    if failed_rc is not None:
        rec["failed_rc"] = failed_rc
    write_json(vm_win_path, rec)
    return rec


def read_peak_vram_mib(
    comfy_url: str,
    *,
    system_stats_fetcher: Any | None = None,
    smi_runner: Callable[..., Any] | None = None,
) -> float:
    """Read peak/used CUDA VRAM in MiB after an image from ComfyUI `/system_stats` (and `nvidia-smi` when live)."""
    try:
        if system_stats_fetcher is not None:
            stats = system_stats_fetcher(comfy_url)
        else:
            with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/system_stats", timeout=10) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        stats = {}

    devices = (stats or {}).get("devices") or []
    cuda_readings_mib: list[float] = []
    for dev in devices:
        if not isinstance(dev, dict):
            continue
        dev_type = str(dev.get("type", "")).lower()
        dev_name = str(dev.get("name", "")).lower()
        if dev_type == "cuda" or "cuda" in dev_name:
            for peak_key in ("vram_peak", "torch_vram_peak"):
                if dev.get(peak_key) is not None:
                    cuda_readings_mib.append(float(dev[peak_key]) / MIB)
            for tot_k, free_k in (("vram_total", "vram_free"), ("torch_vram_total", "torch_vram_free")):
                if dev.get(tot_k) is not None and dev.get(free_k) is not None:
                    used = max(0.0, float(dev[tot_k]) - float(dev[free_k]))
                    cuda_readings_mib.append(used / MIB)

    if smi_runner is not None or (system_stats_fetcher is None and os.environ.get("CUDA_VISIBLE_DEVICES", "0") != ""):
        runner = smi_runner or subprocess.run
        try:
            res = runner(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if getattr(res, "returncode", 1) == 0:
                for ln in (res.stdout or "").splitlines():
                    ln = ln.strip()
                    if ln:
                        cuda_readings_mib.append(float(ln))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    return round(max(cuda_readings_mib), 2) if cuda_readings_mib else 0.0


def run_queue(
    *,
    jobs_path: Path,
    renders_path: Path,
    out_dir: Path,
    comfy_url: str,
    window_id: str,
    copy_back_dir: Path | None = None,
    copy_back_every: int = 5,
    kill_after: int | None = None,
    client: Any | None = None,
    image_downloader: Any | None = None,
    system_stats_fetcher: Any | None = None,
    smi_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    assert_loopback_url(comfy_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    renders_path.parent.mkdir(parents=True, exist_ok=True)
    current_json = renders_path.parent / "current.json"

    # Query /system_stats to log device & prove CPU/CUDA execution
    if system_stats_fetcher is not None:
        sys_stats = system_stats_fetcher(comfy_url)
    else:
        with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/system_stats", timeout=15) as resp:
            sys_stats = json.loads(resp.read().decode("utf-8"))
    print(f"COMFY_SYSTEM_STATS {json.dumps(sys_stats)}", flush=True)

    active_client = client if client is not None else ComfyClient(base_url=comfy_url)
    active_downloader = image_downloader if image_downloader is not None else download_comfy_image
    jobs = [json.loads(line) for line in jobs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    completed = load_completed(renders_path, out_dir)
    completed_files = {r["output_file"] for r in completed.values()}

    skipped_count = 0
    rendered_count = 0
    copy_back_count = 0
    killed_early = False

    for job in jobs:
        job_id = job["job_id"]
        if job_id in completed:
            print(f"SKIP {job_id} (already in renders.jsonl with verified PNG stamp and sha256)", flush=True)
            skipped_count += 1
            continue

        t0 = time.time()
        workflow = job.get("workflow")
        if not workflow:
            if job.get("template_id") == "stub_fixture_64":
                workflow = build_stub_fixture_graph(job)
            else:
                workflow = build_qwen_lora_graph(job)

        stamp_meta = {
            "owner": job.get("owner", "mcp-tool-shop"),
            "licence": job.get("licence", "CC-BY-4.0"),
            "canon_sha": job["canon_sha"],
            "entry_id": job["entry_id"],
            "entry_sha256": job["entry_sha256"],
            "run_id": job["run_id"],
            "workflow_sha": job.get("workflow_sha", ""),
            "window_id": window_id,
        }
        extra_pnginfo = {STAMP_KEYS[k]: v for k, v in stamp_meta.items() if v}

        prompt_id = active_client.queue_prompt(workflow, extra_pnginfo=extra_pnginfo)
        if not prompt_id:
            raise RuntimeError(f"Failed to queue prompt for job {job_id}")
        history_entry = active_client.wait_for_completion(prompt_id, timeout=120.0, poll_interval=0.2)
        if not history_entry:
            raise RuntimeError(f"Timed out waiting for prompt {prompt_id} (job {job_id})")

        img_info = pick_history_image(history_entry)
        raw_png = active_downloader(
            comfy_url,
            img_info["filename"],
            img_info.get("subfolder", ""),
            img_info.get("type", "output"),
        )

        # Verify ComfyUI embedded the runnable prompt graph via comfy_headless
        wf_meta = read_workflow_metadata(raw_png)
        if not wf_meta.has_prompt:
            raise RuntimeError(f"ComfyUI output for {job_id} missing embedded prompt graph")

        # Write canonical tEXt provenance stamp and immediately read back from disk (G8, H7)
        stamped_png = stamp_png_provenance(raw_png, stamp_meta)
        output_file = f"{job_id}.png"
        out_path = out_dir / output_file
        out_path.write_bytes(stamped_png)

        verified_stamp = verify_png_provenance(out_path, stamp_meta)
        png_sha = sha256_file(out_path)
        elapsed_s = max(0.0, time.time() - t0)
        wall_s = round(elapsed_s, 3)
        wall_ms = round(elapsed_s * 1000)
        peak_vram_mib = read_peak_vram_mib(
            comfy_url,
            system_stats_fetcher=system_stats_fetcher,
            smi_runner=smi_runner,
        )

        row = {
            "job_id": job_id,
            "run_id": job["run_id"],
            "status": "ok",
            "output_file": output_file,
            "png_sha256": png_sha,
            "workflow_sha": job.get("workflow_sha"),
            "seed": job.get("seed"),
            "wall_s": wall_s,
            "wall_ms": wall_ms,
            "peak_vram_mib": peak_vram_mib,
            "window_id": window_id,
            "canon_sha": job["canon_sha"],
            "entry_id": job["entry_id"],
            "entry_sha256": job["entry_sha256"],
            "owner": verified_stamp["owner"],
            "licence": verified_stamp["licence"],
            "model_pins": job.get("model_pins"),
            "stamp_verified": True,
        }
        with renders_path.open("a", encoding="utf-8") as rf:
            rf.write(json.dumps(row) + "\n")

        completed_files.add(output_file)
        rendered_count += 1
        print(
            f"RENDERED {job_id} -> {output_file} ({png_sha}, {wall_s}s, peak_vram_mib={peak_vram_mib}, stamp_verified=True)",
            flush=True,
        )

        current_json.write_text(
            json.dumps(
                {
                    "window_id": window_id,
                    "run_id": job["run_id"],
                    "last_job_id": job_id,
                    "files": ["renders.jsonl", *sorted(completed_files)],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if copy_back_dir and copy_back_every > 0 and rendered_count % copy_back_every == 0:
            sync_copy_back(renders_path, current_json, out_dir, copy_back_dir, completed_files)
            copy_back_count += 1

        if kill_after is not None and rendered_count >= kill_after:
            print(f"DELIBERATE_KILL after {rendered_count} job(s)", flush=True)
            killed_early = True
            break

    if (
        copy_back_dir
        and not killed_early
        and completed_files
        and ((rendered_count > 0 and rendered_count % copy_back_every != 0) or not (copy_back_dir / "renders.jsonl").exists())
    ):
        sync_copy_back(renders_path, current_json, out_dir, copy_back_dir, completed_files)
        copy_back_count += 1

    summary = {
        "total_jobs": len(jobs),
        "rendered": rendered_count,
        "skipped": skipped_count,
        "copy_backs": copy_back_count,
        "killed_early": killed_early,
    }
    print(f"SUMMARY {json.dumps(summary)}", flush=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sdlab Lane 1 headless ComfyUI render driver")
    parser.add_argument("--cpu", action="store_true", help="Force CPU-only mode (CUDA_VISIBLE_DEVICES='')")
    parser.add_argument("--bootstrap", action="store_true", help="Write window.json and verify weight manifest")
    parser.add_argument("--window-json", type=Path, help="Path to write window.json")
    parser.add_argument("--window-id", default="win_lane1_stub_01", help="Window identifier")
    parser.add_argument("--system-python", default=None, help="Measured host/system Python version (probed when omitted)")
    parser.add_argument("--system-python-bin", default="/usr/bin/python3", help="System python binary to probe")
    parser.add_argument("--comfy-pid", type=int, default=None, help="PID of the ComfyUI process started by this kit")
    parser.add_argument("--proc-root", type=Path, default=None, help="Optional /proc root directory override")
    parser.add_argument("--proc-net-tcp", type=Path, default=None, help="Optional /proc/net/tcp path override")
    parser.add_argument("--proc-net-tcp6", type=Path, default=None, help="Optional /proc/net/tcp6 path override")
    parser.add_argument("--comfyui-commit", default=None, help="Pinned ComfyUI git commit SHA")
    parser.add_argument("--weight-manifest", type=Path, help="Optional weight manifest JSON to verify by sha256 + licence")
    parser.add_argument("--staging-dir", type=Path, help="Optional weight staging directory")
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188", help="Loopback ComfyUI URL")
    parser.add_argument("--jobs", type=Path, help="Path to jobs.jsonl")
    parser.add_argument("--jobs-sha256", default=None, help="Expected 64-hex sha256 of jobs.jsonl")
    parser.add_argument("--renders", type=Path, help="Path to renders.jsonl")
    parser.add_argument("--out-dir", type=Path, help="Directory for rendered PNG files")
    parser.add_argument("--copy-back-dir", type=Path, help="Optional periodic copy-back directory")
    parser.add_argument("--copy-back-every", type=int, default=2, help="Copy-back interval (number of renders)")
    parser.add_argument("--kill-after", type=int, default=None, help="Stop after K rendered jobs to test resume")
    parser.add_argument("--validate-render-inputs", action="store_true", help="Rig-side validation of jobs and weights manifest")
    parser.add_argument("--weights-manifest", type=Path, default=None, help="Weights manifest JSON for --render")
    parser.add_argument("--allow-no-jobs", action="store_true", help="Allow validating manifest without jobs (CPU stub)")
    parser.add_argument("--vm-guards", action="store_true", help="Run VM GPU smoke, disk and host-RAM guards before download")
    parser.add_argument("--cpu-stub", action="store_true", help="CPU stub of --render: skip CUDA smoke")
    parser.add_argument("--hf-home", type=Path, default=Path("/content/hf_home"), help="HF_HOME cache directory")
    parser.add_argument("--models-dir", type=Path, default=Path("/content/ComfyUI/models"), help="ComfyUI models directory")
    parser.add_argument("--lane1-out", type=Path, default=Path("/content/lane1_out"), help="Lane 1 output directory")
    parser.add_argument("--disk-required-gib", type=float, default=50.0, help="Required free GiB before weights download")
    parser.add_argument("--smoke-seconds", type=float, default=5.0, help="CUDA smoke matmul duration in seconds")
    parser.add_argument("--ram-required-gib", default=None, help="Required MemAvailable GiB")
    parser.add_argument("--meminfo", type=Path, default=Path("/proc/meminfo"), help="/proc/meminfo path")
    parser.add_argument("--shm", type=Path, default=Path("/dev/shm"), help="/dev/shm path")
    parser.add_argument("--guards-out", type=Path, default=Path("/content/lane1_out/render_guards.json"), help="Guards output JSON")
    parser.add_argument("--download-weights", action="store_true", help="Download and sha256-verify weights manifest on VM")
    parser.add_argument("--max-seconds", default=None, help="Max projected/hard download seconds")
    parser.add_argument("--probe-seconds", type=float, default=60.0, help="Download probe window seconds")
    parser.add_argument("--probe-bytes", type=int, default=2 * GIB, help="Download probe window bytes")
    parser.add_argument("--poll-s", type=float, default=0.25, help="Download poll interval seconds")
    parser.add_argument("--download-log", type=Path, default=Path("/content/lane1_out/weights_download.log"), help="Download log path")
    parser.add_argument("--download-out", type=Path, default=Path("/content/lane1_out/weights_download.json"), help="Download record JSON")
    parser.add_argument("--merge-render-facts", action="store_true", help="Merge render guards/download facts into vm_window.json")
    parser.add_argument("--render-state", default=None, help="Render state label for vm_window.json")
    parser.add_argument("--failed-rc", type=int, default=None, help="Failure exit code when bundling after failure")
    args = parser.parse_args(argv)

    if args.validate_render_inputs:
        if args.weights_manifest is None:
            print(refuse_line("RENDER_MANIFEST_REQUIRED", "--render needs --weights-manifest <json>"), file=sys.stderr, flush=True)
            return 1
        try:
            checked = run_validate_inputs(
                manifest_path=args.weights_manifest,
                jobs_path=args.jobs,
                jobs_sha256=args.jobs_sha256,
                allow_no_jobs=args.allow_no_jobs,
            )
        except Refusal as exc:
            print(refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
            return 1
        print("RENDER_INPUTS_OK " + json.dumps(checked), flush=True)
        return 0

    if args.vm_guards:
        disk_req = float(os.environ.get("SDLAB_TEST_DISK_REQUIRED_GIB", str(args.disk_required_gib)))
        return run_vm_guards(
            hf_home=args.hf_home,
            models_dir=args.models_dir,
            lane1_out=args.lane1_out,
            disk_required_gib=disk_req,
            smoke_seconds=args.smoke_seconds,
            ram_required_gib=args.ram_required_gib,
            meminfo_path=args.meminfo,
            shm_path=args.shm,
            out_path=args.guards_out,
            cpu_stub=args.cpu_stub,
        )

    if args.download_weights:
        if args.weights_manifest is None:
            print(refuse_line("RENDER_MANIFEST_REQUIRED", "--download-weights needs --weights-manifest <json>"), file=sys.stderr, flush=True)
            return 1
        return run_weights_download(
            manifest_path=args.weights_manifest,
            hf_home=args.hf_home,
            models_dir=args.models_dir,
            max_seconds_raw=args.max_seconds,
            probe_seconds=args.probe_seconds,
            probe_bytes=args.probe_bytes,
            poll_s=args.poll_s,
            log_path=args.download_log,
            out_path=args.download_out,
        )

    if args.merge_render_facts:
        merged = merge_render_facts(args.lane1_out, render_state=args.render_state, failed_rc=args.failed_rc)
        print("WINDOW_JSON " + json.dumps(merged), flush=True)
        return 0

    if args.cpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    print(
        f"LANE1_START python={sys.version.split()[0]} comfy_headless={COMFY_HEADLESS_VERSION} "
        f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '')!r}",
        flush=True,
    )

    if args.weight_manifest:
        staged = stage_weights(args.weight_manifest, args.staging_dir)
        print(f"WEIGHTS_STAGED count={len(staged)}", flush=True)

    proc_root = args.proc_root
    sys_py_bin = args.system_python_bin
    if os.environ.get("FAKE_VM_SITE"):
        if proc_root is None and os.environ.get("SDLAB_FAKE_PROC_ROOT"):
            proc_root = Path(os.environ["SDLAB_FAKE_PROC_ROOT"])
        if sys_py_bin == "/usr/bin/python3" and os.environ.get("SDLAB_FAKE_SYS_PYTHON_BIN"):
            sys_py_bin = os.environ["SDLAB_FAKE_SYS_PYTHON_BIN"]

    if args.bootstrap and args.window_json:
        rec = write_window_json(
            args.window_json,
            window_id=args.window_id,
            comfy_url=args.comfy_url,
            system_python=args.system_python,
            comfyui_commit=args.comfyui_commit,
            comfy_pid=args.comfy_pid,
            proc_root=proc_root,
            proc_net_tcp=args.proc_net_tcp,
            proc_net_tcp6=args.proc_net_tcp6,
            system_python_bin=sys_py_bin,
        )
        print(f"WINDOW_JSON {json.dumps(rec)}", flush=True)

    if args.jobs and args.renders and args.out_dir:
        summary = run_queue(
            jobs_path=args.jobs,
            renders_path=args.renders,
            out_dir=args.out_dir,
            comfy_url=args.comfy_url,
            window_id=args.window_id,
            copy_back_dir=args.copy_back_dir,
            copy_back_every=args.copy_back_every,
            kill_after=args.kill_after,
        )
        if summary["killed_early"]:
            return 75

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
