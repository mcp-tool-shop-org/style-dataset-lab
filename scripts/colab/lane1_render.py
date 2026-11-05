#!/usr/bin/env python3
"""Lane 1 (render) VM bootstrap and durable ComfyUI queue driver (DESIGN-v3 §3.1, §3.5, §4.4, §7, G1-G3, G8).

Drives headless ComfyUI on loopback (127.0.0.1) via the `comfy_headless` library
(never launching the Gradio UI). Enforces CPython 3.15.1 in a uv venv, stages
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
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PY_VERSION_EXPECTED = "3.15.1"
UV_PIN = "uv==0.13.5"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
CLEARED_LICENCES = {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0", "CC-BY-4.0"}


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
) -> tuple[set[str], bool]:
    """Read `socket:[inode]` entries from `/proc/<pid>/fd` (symlink or fixture file)."""
    fd_dir: Path | None = None
    if comfy_pid is not None and proc_root is not None:
        fd_dir = proc_root / str(comfy_pid) / "fd"
    elif comfy_pid is not None and allow_host_proc:
        fd_dir = Path(f"/proc/{comfy_pid}/fd")

    if fd_dir is None or not fd_dir.exists() or not fd_dir.is_dir():
        return set(), False

    inodes: set[str] = set()
    for entry in sorted(fd_dir.iterdir(), key=lambda p: p.name):
        target = ""
        try:
            target = os.readlink(entry)
        except OSError:
            if entry.is_file():
                target = entry.read_text(encoding="utf-8", errors="replace").strip()
        if target.startswith("socket:[") and target.endswith("]"):
            inode = target[len("socket:[") : -1].strip()
            if inode.isdigit():
                inodes.add(inode)
    return inodes, True


def inspect_comfy_listeners(
    sockets: list[str] | list[dict[str, str]],
    comfy_port: int = 8188,
    *,
    comfy_pid: int | None = None,
    proc_root: Path | None = None,
    allow_host_proc: bool = True,
) -> tuple[list[str], list[str]]:
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

    inode_set, match_by_inode = probe_pid_socket_inodes(
        comfy_pid,
        proc_root=proc_root,
        allow_host_proc=allow_host_proc,
    )

    comfy_sockets: list[str] = []
    other_listeners: list[str] = []
    for addr, _host_part, port_num, inode in parsed_records:
        is_comfy = (bool(inode) and inode in inode_set) if match_by_inode else (port_num == comfy_port)
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

    return comfy_sockets, other_listeners


def verify_loopback_sockets(
    sockets: list[str] | list[dict[str, str]],
    comfy_port: int = 8188,
    *,
    comfy_pid: int | None = None,
    proc_root: Path | None = None,
) -> list[str]:
    comfy_sockets, _ = inspect_comfy_listeners(
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
            "LANE1_NO_MEASURED_SOCKETS: LANE1_COMFY_SOCKET_NOT_FOUND: no listening TCP sockets found in /proc/net/tcp* or ss -tln"
        )
    allow_host_proc = all(x is None for x in (proc_root, proc_net_tcp, proc_net_tcp6, sockets))
    comfy_sockets, other_listeners = inspect_comfy_listeners(
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
) -> dict[str, Any]:
    assert_loopback_url(comfy_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    renders_path.parent.mkdir(parents=True, exist_ok=True)
    current_json = renders_path.parent / "current.json"

    # Query /system_stats to log device & prove CPU execution
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
        wall_ms = round((time.time() - t0) * 1000)

        row = {
            "job_id": job_id,
            "run_id": job["run_id"],
            "status": "ok",
            "output_file": output_file,
            "png_sha256": png_sha,
            "workflow_sha": job.get("workflow_sha"),
            "seed": job.get("seed"),
            "wall_ms": wall_ms,
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
        print(f"RENDERED {job_id} -> {output_file} ({png_sha}, {wall_ms}ms, stamp_verified=True)", flush=True)

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

    if copy_back_dir and not killed_early and rendered_count > 0 and rendered_count % copy_back_every != 0:
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
    parser.add_argument("--renders", type=Path, help="Path to renders.jsonl")
    parser.add_argument("--out-dir", type=Path, help="Directory for rendered PNG files")
    parser.add_argument("--copy-back-dir", type=Path, help="Optional periodic copy-back directory")
    parser.add_argument("--copy-back-every", type=int, default=2, help="Copy-back interval (number of renders)")
    parser.add_argument("--kill-after", type=int, default=None, help="Stop after K rendered jobs to test resume")
    args = parser.parse_args(argv)

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

    if args.bootstrap and args.window_json:
        rec = write_window_json(
            args.window_json,
            window_id=args.window_id,
            comfy_url=args.comfy_url,
            system_python=args.system_python,
            comfyui_commit=args.comfyui_commit,
            comfy_pid=args.comfy_pid,
            proc_root=args.proc_root,
            proc_net_tcp=args.proc_net_tcp,
            proc_net_tcp6=args.proc_net_tcp6,
            system_python_bin=args.system_python_bin,
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
