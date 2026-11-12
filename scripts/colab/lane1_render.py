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

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PY_VERSION_EXPECTED = "3.14.9"
UV_PIN = "uv==0.13.5"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
# Base model pin: Qwen-Image-2512 (Apache-2.0; rnd licences registry `qwen-image-2512-card`,
# https://huggingface.co/Qwen/Qwen-Image-2512/blob/25468b98e3276ca6700de15c6628e51b7de54a26/README.md#L2)
# and Comfy-Org single-file repack `Comfy-Org/Qwen-Image` (Apache-2.0,
# https://huggingface.co/Comfy-Org/Qwen-Image/blob/1f12b17be14c89b026c51a91d67c32f84bb047bc/README.md#L2).
PINNED_BASE_MODEL_REPO = "Qwen/Qwen-Image-2512"
PINNED_BASE_MODEL_REVISION = "25468b98e3276ca6700de15c6628e51b7de54a26"
PINNED_COMFY_REPACK_REPO = "Comfy-Org/Qwen-Image"
PINNED_COMFY_REPACK_REVISION = "1f12b17be14c89b026c51a91d67c32f84bb047bc"
DEFAULT_QWEN_UNET_FILE = "qwen_image_2512_fp8_e4m3fn.safetensors"
DEFAULT_QWEN_CLIP_FILE = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
DEFAULT_QWEN_VAE_FILE = "qwen_image_vae.safetensors"
# Strictly Apache-2.0 or MIT licence ids ONLY. Any other licence id is refused by name.
CLEARED_LICENCES: dict[str, str] = {
    "Apache-2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "MIT": "MIT",
    "mit": "MIT",
    "qwen-image-2512-card": "Apache-2.0",
    "qwen-image-licence": "Apache-2.0",
    "comfy-org-qwen-image-repack": "Apache-2.0",
    "taesd-madebyollin": "MIT",
    "birefnet-mit": "MIT",
}
# Never Qwen-Image 2.1 (`qwen-research`), Turbo/2-step/Lightning, or non-official distill weights.
FORBIDDEN_WEIGHT_MODEL_RE = re.compile(
    r"(?:qwen[_-]?image[_-]?2[._]1(?![0-9])|turbo|(?:^|[^0-9])2[_-]?steps(?![A-Za-z0-9])|lightning|non_official/|qwen[_-]?image[_-]?distill)",
    re.IGNORECASE,
)
# Background removal: RMBG-2.0 / BRIA is CC-BY-NC-4.0 (never). Only BiRefNet (MIT) is permitted.
FORBIDDEN_RMBG_RE = re.compile(r"(?:(?:^|[^A-Za-z0-9])rmbg(?![A-Za-z0-9])|rmbg[_-]?2|(?:^|[^A-Za-z0-9])bria(?:ai)?(?![A-Za-z0-9]))", re.IGNORECASE)
BG_REMOVAL_HINT_RE = re.compile(
    r"(?:rmbg|bria|birefnet|rembg|inspyrenet|u2net|ben2|remove[_-]?background|bg[_-]?remov|background[_-]?remov|transparent[_-]?background)",
    re.IGNORECASE,
)
BIREFNET_RE = re.compile(r"birefnet", re.IGNORECASE)
FORBIDDEN_MOUNT_FSTYPES = frozenset(
    {
        "fuse",
        "fuse.drive",
        "fuse.gcsfuse",
        "gcsfuse",
        "fuse.sshfs",
        "sshfs",
        "fuse.rclone",
        "rclone",
        "davfs",
        "davfs2",
        "nfs",
        "nfs4",
        "cifs",
        "smb3",
        "smbfs",
        "9p",
        "ceph",
        "glusterfs",
        "lustre",
    }
)
HF_429_RE = re.compile(r"(?:\b429\b|too\s+many\s+requests|rate\s*limit)", re.IGNORECASE)
HEX40_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PICTURE_LICENCE_REQUIRED = "CC-BY-4.0"
PICTURE_CREDIT_REQUIRED = "mcp-tool-shop"
VALID_WEIGHT_DESTS = ("diffusion_models", "text_encoders", "vae", "loras")
REAL_MODEL_TEMPLATES = {"qwen_txt2img_lora", "qwen_image"}
FORBIDDEN_RENDER_TEMPLATES = {"stub_fixture_64"}
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GIB = 1024**3
MIB = 1024**2


class _LocalRefusal(Exception):
    """Fallback refusal used only when `lane3_rung.py` is absent (e.g. CPU stub mode)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _load_lane3_rung() -> Any:
    """Import `lane3_rung` lazily inside `--render` / `--render-cpu-stub` paths; CPU stub windows do not upload it."""
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import lane3_rung  # noqa: PLC0415

    return lane3_rung


def _refusal_cls() -> type[Exception]:
    try:
        return _load_lane3_rung().Refusal
    except ModuleNotFoundError:
        return _LocalRefusal


def __getattr__(name: str) -> Any:
    if name == "Refusal":
        return _refusal_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    "credit": "sdlab:credit",
    "canon_sha": "sdlab:canon_sha",
    "entry_id": "sdlab:entry_id",
    "entry_sha256": "sdlab:entry_sha256",
    "run_id": "sdlab:run_id",
    "workflow_sha": "sdlab:workflow_sha",
    "window_id": "sdlab:window_id",
}
REQUIRED_STAMP_FIELDS = ("owner", "licence", "credit", "canon_sha", "entry_id", "entry_sha256", "run_id")


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


def _iter_strings(obj: Any) -> list[str]:
    found: list[str] = []
    if isinstance(obj, str):
        found.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                found.append(k)
            found.extend(_iter_strings(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found.extend(_iter_strings(item))
    return found


def check_background_removal_allowed(
    workflow: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Refuse any background-removal step unless it is explicitly BiRefNet (MIT).

    RMBG-2.0 (`briaai/RMBG-2.0`) is CC-BY-NC-4.0 and is NEVER permitted anywhere in Lane 1.
    Returns a normalized BiRefNet spec dict when BiRefNet is requested on `job`, else `None`.
    """
    refusal_cls = _refusal_cls()
    birefnet_spec: dict[str, Any] | None = None

    if isinstance(job, dict):
        for bg_key in ("background_removal", "bg_removal", "remove_background"):
            raw_bg = job.get(bg_key)
            if raw_bg is None or raw_bg is False or (isinstance(raw_bg, str) and raw_bg.strip().lower() in ("", "none")):
                continue
            if isinstance(raw_bg, str):
                s_val = raw_bg.strip()
                if FORBIDDEN_RMBG_RE.search(s_val) or not BIREFNET_RE.search(s_val):
                    raise refusal_cls(
                        "BG_REMOVAL_FORBIDDEN",
                        f"{bg_key}={s_val!r} is barred; background removal must stay out of the graph unless BiRefNet (MIT) — RMBG-2.0 is CC-BY-NC-4.0 (never)",
                    )
                birefnet_spec = {"model_name": s_val, "licence_id": "MIT"}
            elif isinstance(raw_bg, dict):
                model_str = str(raw_bg.get("model") or raw_bg.get("model_name") or raw_bg.get("name") or "").strip()
                lic_str = str(raw_bg.get("licence_id") or "MIT").strip()
                if FORBIDDEN_RMBG_RE.search(model_str) or not BIREFNET_RE.search(model_str):
                    raise refusal_cls(
                        "BG_REMOVAL_FORBIDDEN",
                        f"{bg_key} model {model_str!r} is barred; only BiRefNet (MIT) is permitted — RMBG-2.0 is CC-BY-NC-4.0 (never)",
                    )
                if CLEARED_LICENCES.get(lic_str) != "MIT":
                    raise refusal_cls(
                        "BG_REMOVAL_FORBIDDEN",
                        f"{bg_key} BiRefNet licence_id {lic_str!r} must be MIT",
                    )
                birefnet_spec = {"model_name": model_str, "licence_id": "MIT"}
            else:
                raise refusal_cls("BG_REMOVAL_FORBIDDEN", f"{bg_key}={raw_bg!r} must be omitted or BiRefNet (MIT)")

        pins_strs = _iter_strings(job.get("model_pins"))
        for p_str in pins_strs:
            if FORBIDDEN_RMBG_RE.search(p_str):
                raise refusal_cls(
                    "BG_REMOVAL_FORBIDDEN",
                    f"model_pins references {p_str!r}; RMBG-2.0 / BRIA is CC-BY-NC-4.0 and never allowed",
                )

    if isinstance(workflow, dict):
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            ctype = str(node.get("class_type") or "")
            inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
            input_values = [v for v in _iter_strings(inputs) if v not in inputs]
            combined = " ".join([ctype, *input_values])
            if FORBIDDEN_RMBG_RE.search(combined):
                raise refusal_cls(
                    "BG_REMOVAL_FORBIDDEN",
                    f"node {node_id} ({ctype}) uses RMBG/BRIA ({combined!r}); RMBG-2.0 is CC-BY-NC-4.0 and never allowed",
                )
            if BG_REMOVAL_HINT_RE.search(ctype) and not BIREFNET_RE.search(combined):
                raise refusal_cls(
                    "BG_REMOVAL_FORBIDDEN",
                    f"node {node_id} ({ctype}) performs non-BiRefNet background removal; only BiRefNet (MIT) is allowed",
                )

    return birefnet_spec


def build_qwen_lora_graph(job: dict[str, Any]) -> dict[str, Any]:
    """Build the Qwen-Image-2512 LoRA-aware API graph (G3: LoraLoaderModelOnly chain 40.. between 37 and 66)."""
    birefnet_spec = check_background_removal_allowed(None, job)
    pins = job.get("model_pins") or {}
    unet = (pins.get("base") or pins.get("unet") or {}).get("name") or DEFAULT_QWEN_UNET_FILE
    clip = (pins.get("text_encoder") or pins.get("clip") or {}).get("name") or DEFAULT_QWEN_CLIP_FILE
    vae = (pins.get("vae") or {}).get("name") or DEFAULT_QWEN_VAE_FILE
    for candidate in (unet, clip, vae):
        if FORBIDDEN_WEIGHT_MODEL_RE.search(str(candidate)):
            raise _refusal_cls()(
                "WEIGHTS_MODEL_EXCLUDED",
                f"model file {candidate!r} is barred (Qwen-Image 2.1, Turbo and distill weights are non-commercial/excluded)",
            )
    loras = job.get("loras") or pins.get("loras") or []

    nodes: dict[str, Any] = {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip, "type": "qwen_image"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("prompt", ""), "clip": ["38", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("negative", job.get("negative_prompt", "")), "clip": ["38", 0]}},
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

    image_out = ["8", 0]
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
        }
    )
    if birefnet_spec is not None:
        nodes["90"] = {
            "class_type": "BiRefNetRemoveBackground",
            "inputs": {"image": image_out, "model_name": birefnet_spec["model_name"]},
        }
        image_out = ["90", 0]
    nodes["9"] = {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": f"sdl_{job.get('job_id', 'job')}", "images": image_out},
    }
    check_background_removal_allowed(nodes, job)
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
            raise ValueError(
                f"LANE1_WEIGHT_LICENCE_INVALID: {name} has uncleared licence {lic!r} (only Apache-2.0 or MIT allowed)"
            )
        if FORBIDDEN_WEIGHT_MODEL_RE.search(str(name)) or FORBIDDEN_RMBG_RE.search(str(name)):
            raise ValueError(f"LANE1_WEIGHT_LICENCE_INVALID: {name} is an excluded model")
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


def probe_colab_runtime_and_cuda(
    *,
    env: dict[str, str] | None = None,
    release_path: Path | None = None,
    cuda_parent: Path | None = None,
) -> dict[str, Any]:
    """Record the Colab runtime version string and the `/usr/local/cuda*` directory listing."""
    active_env = os.environ if env is None else env
    rel_file = release_path or Path(active_env.get("SDLAB_COLAB_RELEASE_FILE", "/etc/colab-release"))
    parent_dir = cuda_parent or Path(active_env.get("SDLAB_CUDA_PARENT_DIR", "/usr/local"))

    runtime_version = "unknown"
    if rel_file.is_file():
        raw_rel = rel_file.read_text(encoding="utf-8", errors="replace").strip()
        if raw_rel:
            kv: dict[str, str] = {}
            for ln in raw_rel.splitlines():
                if "=" in ln:
                    k, v = ln.split("=", 1)
                    kv[k.strip()] = v.strip().strip("\"'")
            runtime_version = (
                kv.get("COLAB_RELEASE_TAG")
                or kv.get("RELEASE_TAG")
                or kv.get("VERSION")
                or raw_rel.splitlines()[0].strip()
            )
    if runtime_version == "unknown":
        for env_key in ("COLAB_RELEASE_TAG", "COLAB_BACKEND_VERSION", "COLAB_RUNTIME_VERSION"):
            val = (active_env.get(env_key) or "").strip()
            if val:
                runtime_version = val
                break

    cuda_entries: list[dict[str, Any]] = []
    if parent_dir.is_dir():
        for entry in sorted(parent_dir.glob("cuda*"), key=lambda p: p.name):
            is_link = entry.is_symlink()
            target_str: str | None = None
            if is_link:
                try:
                    target_str = os.readlink(entry)
                except OSError:
                    target_str = None
            cuda_ver: str | None = None
            ver_json = entry / "version.json"
            ver_txt = entry / "version.txt"
            if ver_json.is_file():
                try:
                    vj = json.loads(ver_json.read_text(encoding="utf-8"))
                    cuda_ver = str(((vj.get("cuda") or {}).get("version")) or vj.get("version") or "") or None
                except (OSError, ValueError):
                    cuda_ver = None
            elif ver_txt.is_file():
                try:
                    cuda_ver = ver_txt.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip() or None
                except OSError:
                    cuda_ver = None
            cuda_entries.append(
                {
                    "name": entry.name,
                    "path": entry.as_posix(),
                    "is_symlink": is_link,
                    "target": target_str,
                    "cuda_version": cuda_ver,
                }
            )

    return {
        "colab_runtime_version": runtime_version,
        "cuda_paths": cuda_entries,
    }


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
    colab_release_path: Path | None = None,
    cuda_parent: Path | None = None,
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
    rt_cuda = probe_colab_runtime_and_cuda(release_path=colab_release_path, cuda_parent=cuda_parent)

    record = {
        "window_id": window_id,
        "lane": "render",
        "card": card,
        "vm_gate": {
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
            "platform": sys.platform,
        },
        "colab_runtime_version": rt_cuda["colab_runtime_version"],
        "cuda_paths": rt_cuda["cuda_paths"],
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE") == "1",
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
                            "credit": row.get("credit"),
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
    rung = _load_lane3_rung()
    refusal_cls = rung.Refusal
    if not manifest_path.is_file():
        raise refusal_cls("WEIGHTS_MANIFEST_INVALID", f"{manifest_path} does not exist")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise refusal_cls("WEIGHTS_MANIFEST_INVALID", f"{manifest_path}: invalid JSON ({type(exc).__name__})") from None
    if not isinstance(raw, list) or not raw:
        raise refusal_cls("WEIGHTS_MANIFEST_INVALID", f"{manifest_path} must be a non-empty JSON list")

    entries: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise refusal_cls("WEIGHTS_MANIFEST_INVALID", f"row {idx}: manifest row must be an object")
        lic = item.get("licence_id")
        if not isinstance(lic, str) or not lic.strip():
            raise refusal_cls("WEIGHTS_LICENCE_INVALID", f"row {idx}: missing licence_id")
        lic_clean = lic.strip()
        if lic_clean not in CLEARED_LICENCES:
            raise refusal_cls(
                "WEIGHTS_LICENCE_INVALID",
                f"row {idx}: licence_id {lic_clean!r} is not allowed (only Apache-2.0 or MIT ids are cleared)",
            )
        repo = item.get("repo")
        if not isinstance(repo, str) or not rung.REPO_ID_RE.match(repo.strip()):
            raise refusal_cls("WEIGHTS_MANIFEST_INVALID", f"row {idx}: {repo!r} is not a Hugging Face repo id")
        repo_clean = repo.strip()
        revision = item.get("revision")
        if not isinstance(revision, str) or not rung.REVISION_RE.match(revision.strip()):
            raise refusal_cls("WEIGHTS_REVISION_INVALID", f"row {idx}: revision {revision!r} is not a 40-hex commit")
        rel_file = item.get("file")
        if (
            not isinstance(rel_file, str)
            or not rel_file.strip()
            or "\\" in rel_file
            or rel_file.startswith("/")
            or any(part in ("", ".", "..") for part in rel_file.strip().split("/"))
        ):
            raise refusal_cls("WEIGHTS_MANIFEST_INVALID", f"row {idx}: invalid relative file {rel_file!r}")
        rel_clean = rel_file.strip()
        for target_str in (repo_clean, rel_clean):
            if FORBIDDEN_RMBG_RE.search(target_str):
                raise refusal_cls(
                    "BG_REMOVAL_FORBIDDEN",
                    f"row {idx}: {target_str!r} is barred; RMBG-2.0 / BRIA is CC-BY-NC-4.0 and never allowed (only BiRefNet MIT)",
                )
            if FORBIDDEN_WEIGHT_MODEL_RE.search(target_str):
                raise refusal_cls(
                    "WEIGHTS_MODEL_EXCLUDED",
                    f"row {idx}: {target_str!r} is barred (Qwen-Image 2.1, Turbo and distill weights are non-commercial/excluded)",
                )
        dest = item.get("dest")
        if dest not in VALID_WEIGHT_DESTS:
            raise refusal_cls("WEIGHTS_DEST_INVALID", f"row {idx}: dest {dest!r} must be one of {VALID_WEIGHT_DESTS}")
        norm_sha = normalize_sha256(item.get("sha256"))
        if norm_sha is None:
            raise refusal_cls("WEIGHTS_MANIFEST_INVALID", f"row {idx}: sha256 must be a 64-hex digest")
        entries.append(
            {
                "repo": repo_clean,
                "revision": revision.strip(),
                "file": rel_clean,
                "dest": dest,
                "sha256": norm_sha[7:],
                "licence_id": lic_clean,
                "spdx_id": CLEARED_LICENCES[lic_clean],
                "hf_token_required": bool(item.get("hf_token_required", False)),
            }
        )
    return entries


def validate_render_jobs(jobs_path: Path, expected_jobs_sha256: str | None) -> dict[str, Any]:
    """Check `jobs.jsonl` against `--jobs-sha256` and validate every row without logging prompt text."""
    refusal_cls = _load_lane3_rung().Refusal
    exp_norm = normalize_sha256(expected_jobs_sha256)
    if exp_norm is None:
        raise refusal_cls("RENDER_JOBS_SHA_REQUIRED", "--jobs-sha256 must be a 64-hex sha256")
    if not jobs_path.is_file():
        raise refusal_cls("JOBS_FILE_MISSING", f"{jobs_path} does not exist")
    exp_hex = exp_norm[7:]
    actual_hex = sha256_file(jobs_path)[7:]
    if actual_hex != exp_hex:
        raise refusal_cls("JOBS_SHA_MISMATCH", f"{jobs_path} sha256={actual_hex} expected={exp_hex}")

    raw_lines = [ln for ln in jobs_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not raw_lines:
        raise refusal_cls("RENDER_JOB_INVALID", f"{jobs_path} contains no jobs")

    seen_ids: set[str] = set()
    first_job_id: str | None = None
    for idx, line in enumerate(raw_lines):
        try:
            row = json.loads(line)
        except ValueError:
            raise refusal_cls("RENDER_JOB_INVALID", f"row {idx}: malformed JSON") from None
        if not isinstance(row, dict):
            raise refusal_cls("RENDER_JOB_INVALID", f"row {idx}: job row must be a JSON object")
        job_id = row.get("job_id")
        if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id) or job_id in seen_ids:
            raise refusal_cls("RENDER_JOB_INVALID", f"row {idx}: missing, unsafe or duplicate job_id")
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
            raise refusal_cls(
                "JOB_TEMPLATE_INVALID",
                f"job {job_id}: template_id {template_id!r} must be a real-model template (never stub_fixture_64)",
            )
        for req_str in ("run_id", "canon_sha", "entry_id", "entry_sha256"):
            val = row.get(req_str)
            if not isinstance(val, str) or not val.strip():
                raise refusal_cls("RENDER_JOB_INVALID", f"job {job_id}: missing {req_str}")
        canon_sha_val = str(row["canon_sha"]).strip()
        if not HEX40_COMMIT_RE.match(canon_sha_val):
            raise refusal_cls("RENDER_JOB_INVALID", f"job {job_id}: canon_sha must be a 40-hex git commit")
        if normalize_sha256(str(row["entry_sha256"])) is None:
            raise refusal_cls("RENDER_JOB_INVALID", f"job {job_id}: entry_sha256 must be a 64-hex sha256")
        lic_val = row.get("licence")
        if lic_val != PICTURE_LICENCE_REQUIRED:
            raise refusal_cls(
                "RENDER_JOB_INVALID",
                f"job {job_id}: licence {lic_val!r} must be {PICTURE_LICENCE_REQUIRED!r} (portlight-bounty picture terms)",
            )
        credit_val = row.get("credit")
        if credit_val != PICTURE_CREDIT_REQUIRED:
            raise refusal_cls(
                "RENDER_JOB_INVALID",
                f"job {job_id}: credit {credit_val!r} must be {PICTURE_CREDIT_REQUIRED!r} (portlight-bounty picture terms)",
            )
        prompt = row.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise refusal_cls("RENDER_JOB_INVALID", f"job {job_id}: missing prompt")
        seed = row.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise refusal_cls("RENDER_JOB_INVALID", f"job {job_id}: missing or non-integer seed")
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
            raise refusal_cls("RENDER_JOB_INVALID", f"job {job_id}: missing or non-positive width/height")
        steps = row.get("steps")
        if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
            raise refusal_cls("RENDER_JOB_INVALID", f"job {job_id}: missing or non-positive steps")

        check_background_removal_allowed(row.get("workflow"), row)
        if not row.get("workflow"):
            build_qwen_lora_graph({**row, "prompt": "<redacted>"})

    return {"jobs_sha256": actual_hex, "job_count": len(seen_ids), "first_job_id": first_job_id}


def run_validate_inputs(
    *,
    manifest_path: Path,
    jobs_path: Path | None = None,
    jobs_sha256: str | None = None,
    allow_no_jobs: bool = False,
) -> dict[str, Any]:
    refusal_cls = _load_lane3_rung().Refusal
    entries = validate_weights_manifest(manifest_path)
    needs_token = any(e["hf_token_required"] for e in entries)
    if needs_token:
        tok = os.environ.get("HF_TOKEN_GGUF_READ", "")
        if not tok or any(ch.isspace() for ch in tok):
            raise refusal_cls(
                "HF_READ_TOKEN_MISSING",
                "manifest marks hf_token_required=true; pass token via HF_TOKEN_GGUF_READ environment variable",
            )
    jobs_info: dict[str, Any] | None = None
    if not allow_no_jobs or jobs_path is not None:
        if jobs_path is None:
            raise refusal_cls("RENDER_JOBS_REQUIRED", "--render needs --jobs <jobs.jsonl>")
        jobs_info = validate_render_jobs(jobs_path, jobs_sha256)
    return {
        "manifest_entries": len(entries),
        "hf_token_required": needs_token,
        "jobs": jobs_info,
    }


def _unescape_mount_field(raw: str) -> str:
    return raw.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def verify_local_disk_staging(path: Path, *, mounts_path: Path | None = None) -> dict[str, Any]:
    """Verify `path` is on local VM disk rather than a FUSE / Drive / network mount (never mmap over a mount)."""
    refusal_cls = _refusal_cls()
    active_mounts = mounts_path or Path(os.environ.get("SDLAB_PROC_MOUNTS", "/proc/mounts"))
    raw_posix = path.as_posix()
    resolved_posix = path.resolve().as_posix()

    for check_p in (raw_posix, resolved_posix):
        if check_p == "/content/drive" or check_p.startswith("/content/drive/"):
            raise refusal_cls(
                "WEIGHTS_MOUNT_FORBIDDEN",
                f"{path} points into /content/drive; stage weights on local disk, never mmap over a Drive/FUSE mount",
            )

    best_mp = ""
    best_fstype = "local"
    if active_mounts.is_file():
        for ln in active_mounts.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = ln.split()
            if len(parts) < 3:
                continue
            mp = _unescape_mount_field(parts[1]).rstrip("/") or "/"
            fstype = parts[2].lower()
            for candidate in (resolved_posix, raw_posix):
                cand_norm = candidate.rstrip("/") or "/"
                if mp == "/" or cand_norm == mp or cand_norm.startswith(mp + "/"):
                    if len(mp) >= len(best_mp):
                        best_mp = mp
                        best_fstype = fstype

    if best_fstype in FORBIDDEN_MOUNT_FSTYPES or best_fstype.startswith("fuse."):
        raise refusal_cls(
            "WEIGHTS_MOUNT_FORBIDDEN",
            f"{path} resides on mount {best_mp!r} (fstype={best_fstype!r}); stage weights on local disk, never mmap over a mount",
        )

    return {
        "path": raw_posix,
        "resolved": resolved_posix,
        "mountpoint": best_mp or "/",
        "fstype": best_fstype,
        "local_disk": True,
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
    driver_fn: Callable[[], dict[str, Any]] | None = None,
    disk_usage_fn: Callable[[str], Any] = shutil.disk_usage,
    mounts_path: Path | None = None,
) -> int:
    rung = _load_lane3_rung()
    active_driver_fn = driver_fn if driver_fn is not None else rung.query_driver
    rec: dict[str, Any] = {"cpu_stub": cpu_stub}
    refusals: list[tuple[str, str]] = []

    local_mounts: list[dict[str, Any]] = []
    for stage_p in (hf_home, models_dir):
        try:
            local_mounts.append(verify_local_disk_staging(stage_p, mounts_path=mounts_path))
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", "WEIGHTS_MOUNT_FORBIDDEN")
            detail = getattr(exc, "detail", str(exc))
            refusals.append((code, detail))
    rec["local_disk_staging"] = local_mounts

    try:
        ram_req = rung.parse_positive_number(ram_required_gib, "HOST_RAM_THRESHOLD_MISSING", "LANE1_HOST_RAM_REQUIRED_GIB")
    except rung.Refusal as exc:
        ram_req = None
        refusals.append((exc.code, exc.detail))

    if cpu_stub:
        rec["gpu"] = {"skipped_cpu_stub": True, "ok": True}
    else:
        gpu: dict[str, Any] = dict(active_driver_fn())
        try:
            gpu.update(smoke_fn(target_s=float(smoke_seconds)))
            gpu["ok"] = True
        except Exception as exc:  # noqa: BLE001
            gpu["ok"] = False
            gpu["error"] = f"{type(exc).__name__}: {exc}".splitlines()[0]
            refusals.append(("GPU_SMOKE_FAILED", gpu["error"]))
        rec["gpu"] = gpu

    disk = rung.measure_disk([hf_home, models_dir, lane1_out], float(disk_required_gib), disk_usage_fn)
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
    ram = rung.measure_host_ram(meminfo_text, ram_req if ram_req is not None else 0.0)
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
    rec["shm"] = rung.measure_shm(shm_path, disk_usage_fn)
    rec["refusals"] = [code for code, _ in refusals]
    rung.write_json(out_path, rec)
    print("RENDER_GUARDS " + json.dumps(rec), flush=True)
    for code, detail in refusals:
        print(rung.refuse_line(code, detail), file=sys.stderr, flush=True)
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
    for sib in info.siblings or []:
        if getattr(sib, "rfilename", None) == filename:
            return int(sib.size or 0)
    raise FileNotFoundError(f"{filename} not found in {repo_id}@{revision}")


def _is_hf_429(exc_or_text: BaseException | str) -> bool:
    if isinstance(exc_or_text, BaseException):
        resp = getattr(exc_or_text, "response", None)
        if getattr(resp, "status_code", None) == 429:
            return True
        return bool(HF_429_RE.search(str(exc_or_text)))
    return bool(HF_429_RE.search(str(exc_or_text)))


def _fail_weights(out_path: Path, rec: dict[str, Any], code: str, detail: str) -> int:
    rung = _load_lane3_rung()
    rec["refusal"] = code
    rung.write_json(out_path, rec)
    print("WEIGHTS_DOWNLOAD " + json.dumps(rec), flush=True)
    print(rung.refuse_line(code, detail), file=sys.stderr, flush=True)
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
    backoff_base_s: float | None = None,
    max_429_retries: int = 6,
    mounts_path: Path | None = None,
    log_path: Path,
    out_path: Path,
    expected_fn: Callable[..., int] = expected_file_bytes,
    popen: Callable[..., Any] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    rung = _load_lane3_rung()
    token = os.environ.get("HF_TOKEN_GGUF_READ") or None
    offline = os.environ.get("HF_HUB_OFFLINE") == "1"
    eff_backoff_base = (
        float(backoff_base_s)
        if backoff_base_s is not None
        else float(os.environ.get("SDLAB_HF_429_BACKOFF_BASE_S", "1.0"))
    )
    rec: dict[str, Any] = {
        "token_used": "HF_TOKEN_GGUF_READ" in os.environ,
        "offline": offline,
        "http_429_retries": 0,
        "http_429_backoff_seconds": 0.0,
        "files": [],
    }
    try:
        max_seconds = rung.parse_positive_number(max_seconds_raw, "DOWNLOAD_LIMIT_MISSING", "LANE1_DOWNLOAD_MAX_SECONDS")
        entries = validate_weights_manifest(manifest_path)
        rec["local_disk_staging"] = {
            "hf_home": verify_local_disk_staging(hf_home, mounts_path=mounts_path),
            "models_dir": verify_local_disk_staging(models_dir, mounts_path=mounts_path),
        }
    except Exception as exc:  # noqa: BLE001
        if hasattr(exc, "code") and hasattr(exc, "detail"):
            return _fail_weights(out_path, rec, exc.code, exc.detail)
        raise

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

        cache = rung.repo_cache_dir(hf_home, repo)
        snap_file = cache / "snapshots" / revision / filename
        file_baseline = snap_file.stat().st_size if snap_file.is_file() else 0
        file_429_retries = 0
        file_429_backoff_s = 0.0

        if offline:
            expected = file_baseline
        else:
            info_attempt = 0
            while True:
                try:
                    expected = int(expected_fn(repo, revision, filename, token))
                    break
                except Exception as exc:  # noqa: BLE001
                    if _is_hf_429(exc):
                        rem_bound = float(max_seconds) - max(clock() - overall_start, 0.0)
                        if info_attempt < max_429_retries and rem_bound > 0.0:
                            delay = min(eff_backoff_base * (2**info_attempt), rem_bound)
                            sleep(delay)
                            info_attempt += 1
                            file_429_retries += 1
                            file_429_backoff_s += delay
                            rec["http_429_retries"] = int(rec["http_429_retries"]) + 1
                            rec["http_429_backoff_seconds"] = round(float(rec["http_429_backoff_seconds"]) + delay, 4)
                            continue
                        return _fail_weights(
                            out_path,
                            rec,
                            "DOWNLOAD_TOO_SLOW",
                            f"HTTP 429 rate-limit backoff on model_info {repo}@{revision} exhausted download bound ({max_seconds}s)",
                        )
                    code, detail = rung.classify_hub_error(exc)
                    return _fail_weights(out_path, rec, code, f"model_info {repo}@{revision}: {detail}")

        dl_attempt = 0
        while True:
            cache_start_bytes = rung.dir_bytes(cache)
            cur_snap_bytes = snap_file.stat().st_size if snap_file.is_file() else file_baseline
            remaining = max(expected - cur_snap_bytes, 0)
            spent = max(clock() - overall_start, 0.0)
            if spent >= float(max_seconds):
                return _fail_weights(
                    out_path,
                    rec,
                    "DOWNLOAD_TOO_SLOW",
                    f"download bound ({max_seconds}s) exhausted before staging {repo}:{filename}",
                )
            budget_s = max(float(max_seconds) - spent, 0.01)

            file_start = clock()
            hard_stop = threading.Event()
            item_log = log_path.parent / f".dl_{len(rec['files'])}_{dl_attempt}.log"
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
                        new_bytes = max(rung.dir_bytes(cache) - cache_start_bytes, 0)
                        if not offline and probe is None and (elapsed >= float(probe_seconds) or new_bytes >= int(probe_bytes)):
                            probe = rung.evaluate_probe(new_bytes, elapsed, remaining, budget_s)
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
            scrubbed_log = rung.mask_log_text(raw_log)
            if token is not None and token in scrubbed_log:
                scrubbed_log = scrubbed_log.replace(token, "[REDACTED]")
            with log_path.open("a", encoding="utf-8", newline="\n") as main_log:
                main_log.write(scrubbed_log)
            log_lines = raw_log.splitlines()
            new_bytes = max(rung.dir_bytes(cache) - cache_start_bytes, 0)
            downloaded_path = next((ln.split(" ", 1)[1].strip() for ln in log_lines if ln.startswith("FILE_PATH ")), None)

            if (
                rc != 0
                and not hard_stop.is_set()
                and _is_hf_429(raw_log)
            ):
                rem_bound = float(max_seconds) - max(clock() - overall_start, 0.0)
                if dl_attempt < max_429_retries and rem_bound > 0.0:
                    delay = min(eff_backoff_base * (2**dl_attempt), rem_bound)
                    sleep(delay)
                    dl_attempt += 1
                    file_429_retries += 1
                    file_429_backoff_s += delay
                    rec["http_429_retries"] = int(rec["http_429_retries"]) + 1
                    rec["http_429_backoff_seconds"] = round(float(rec["http_429_backoff_seconds"]) + delay, 4)
                    continue
                file_rec_429 = {
                    "repo": repo,
                    "revision": revision,
                    "file": filename,
                    "dest": dest,
                    "licence_id": entry["licence_id"],
                    "expected_bytes": expected,
                    "cached_bytes_at_start": file_baseline,
                    "downloaded_bytes": new_bytes,
                    "seconds": round(elapsed, 2),
                    "probe": probe,
                    "hard_limit_hit": False,
                    "http_429_retries": file_429_retries,
                    "http_429_backoff_seconds": round(file_429_backoff_s, 4),
                    **rung.count_throttle_signals(log_lines),
                }
                rec["files"].append(file_rec_429)
                return _fail_weights(
                    out_path,
                    rec,
                    "DOWNLOAD_TOO_SLOW",
                    f"HTTP 429 rate-limit backoff on {repo}:{filename} exhausted download bound ({max_seconds}s)",
                )
            break

        file_rec: dict[str, Any] = {
            "repo": repo,
            "revision": revision,
            "file": filename,
            "dest": dest,
            "licence_id": entry["licence_id"],
            "expected_bytes": expected,
            "cached_bytes_at_start": file_baseline,
            "downloaded_bytes": new_bytes,
            "seconds": round(elapsed, 2),
            "probe": probe,
            "hard_limit_hit": hard_stop.is_set(),
            "http_429_retries": file_429_retries,
            "http_429_backoff_seconds": round(file_429_backoff_s, 4),
            **rung.count_throttle_signals(log_lines),
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
            tail = rung.mask_log_text(" | ".join(log_lines[-3:]))
            if token is not None and token in tail:
                tail = "[the download log tail is withheld: it held the read token]"
            return _fail_weights(out_path, rec, "MODEL_DOWNLOAD_FAILED", f"hf_hub_download {repo}:{filename} rc={rc}: {tail}")

        target_dir = models_dir / dest
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / Path(filename).name
        if target_path.is_symlink():
            target_path.unlink()
        shutil.copyfile(downloaded_path, target_path)
        if target_path.is_symlink():
            target_path.unlink(missing_ok=True)
            return _fail_weights(out_path, rec, "WEIGHTS_MOUNT_FORBIDDEN", f"{target_path} must be a regular local file, not a symlink")
        got_sha = sha256_file(target_path)[7:]
        file_rec["staged_path"] = str(target_path)
        file_rec["staged_on_local_disk"] = True
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
            if not rung.safetensors_complete(target_path):
                target_path.unlink(missing_ok=True)
                return _fail_weights(
                    out_path,
                    rec,
                    "WEIGHTS_CORRUPT",
                    f"{dest}/{target_path.name} failed safetensors header/offset unpack check",
                )
            file_rec["safetensors_verified"] = True

    os.environ["HF_HUB_OFFLINE"] = "1"
    rec["hf_hub_offline_after_stage"] = True
    rung.write_json(out_path, rec)
    print("WEIGHTS_DOWNLOAD " + json.dumps(rec), flush=True)
    return 0


def merge_render_facts(lane1_out: Path, *, render_state: str | None = None, failed_rc: int | None = None) -> dict[str, Any]:
    """Merge `render_guards.json`, `weights_download.json` and `render_heartbeat.json` into `vm_window.json`."""
    vm_win_path = lane1_out / "vm_window.json"
    rec: dict[str, Any] = {}
    if vm_win_path.is_file():
        try:
            rec.update(json.loads(vm_win_path.read_text(encoding="utf-8")))
        except ValueError:
            pass
    if "colab_runtime_version" not in rec or "cuda_paths" not in rec:
        rt_cuda = probe_colab_runtime_and_cuda()
        rec.setdefault("colab_runtime_version", rt_cuda["colab_runtime_version"])
        rec.setdefault("cuda_paths", rt_cuda["cuda_paths"])
    guards_p = lane1_out / "render_guards.json"
    if guards_p.is_file():
        rec["render_guards"] = json.loads(guards_p.read_text(encoding="utf-8"))
    dl_p = lane1_out / "weights_download.json"
    if dl_p.is_file():
        dl = json.loads(dl_p.read_text(encoding="utf-8"))
        rec["weights_download"] = dl
        rec["hf_token_used"] = bool(dl.get("token_used"))
        if dl.get("hf_hub_offline_after_stage"):
            rec["hf_hub_offline"] = True
    hb_p = lane1_out / "render_heartbeat.json"
    if hb_p.is_file():
        rec["render_heartbeat"] = json.loads(hb_p.read_text(encoding="utf-8"))
    if "hf_hub_offline" not in rec:
        rec["hf_hub_offline"] = os.environ.get("HF_HUB_OFFLINE") == "1"
    if render_state is not None:
        rec["render"] = render_state
    if failed_rc is not None:
        rec["failed_rc"] = failed_rc
    vm_win_path.parent.mkdir(parents=True, exist_ok=True)
    vm_win_path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
    return rec


def write_render_heartbeat(
    heartbeat_path: Path,
    *,
    window_id: str,
    state: str,
    total_jobs: int,
    skipped_jobs: int,
    images_rendered: int,
    heartbeat_seq: int,
    started_at_epoch: float,
    last_image_at_epoch: float | None,
    last_job_id: str | None,
) -> dict[str, Any]:
    """Write `render_heartbeat.json` whose sequence/timestamp advances ONLY when an image is rendered."""
    rec = {
        "window_id": window_id,
        "state": state,
        "total_jobs": int(total_jobs),
        "skipped_jobs": int(skipped_jobs),
        "images_rendered": int(images_rendered),
        "heartbeat_seq": int(heartbeat_seq),
        "started_at_epoch": round(float(started_at_epoch), 6),
        "last_image_at_epoch": round(float(last_image_at_epoch), 6) if last_image_at_epoch is not None else None,
        "last_job_id": last_job_id,
    }
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
    return rec


def evaluate_render_heartbeat(
    heartbeat: dict[str, Any],
    *,
    now_epoch: float,
    max_idle_s: float,
) -> dict[str, Any]:
    """Evaluate an image-tied `render_heartbeat.json` record against `max_idle_s`."""
    anchor = heartbeat.get("last_image_at_epoch")
    if anchor is None:
        anchor = heartbeat.get("started_at_epoch") or 0.0
    idle_s = round(max(0.0, float(now_epoch) - float(anchor)), 3)
    state = str(heartbeat.get("state") or "running")
    stale = state == "running" and idle_s > float(max_idle_s)
    return {
        "ok": not stale,
        "tripped": stale,
        "code": "RENDER_HEARTBEAT_STALE" if stale else None,
        "idle_seconds": idle_s,
        "max_idle_seconds": float(max_idle_s),
        "images_rendered": int(heartbeat.get("images_rendered") or 0),
        "heartbeat_seq": int(heartbeat.get("heartbeat_seq") or 0),
    }


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
    window_id: str = "win_default",
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
    heartbeat_path = renders_path.parent / "render_heartbeat.json"

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
    heartbeat_seq = 0
    copy_back_count = 0
    killed_early = False
    started_at_epoch = time.time()
    last_image_at_epoch: float | None = None
    last_rendered_job_id: str | None = None

    write_render_heartbeat(
        heartbeat_path,
        window_id=window_id,
        state="running",
        total_jobs=len(jobs),
        skipped_jobs=0,
        images_rendered=0,
        heartbeat_seq=0,
        started_at_epoch=started_at_epoch,
        last_image_at_epoch=None,
        last_job_id=None,
    )

    for job in jobs:
        job_id = job["job_id"]
        if job_id in completed:
            print(f"SKIP {job_id} (already in renders.jsonl with verified PNG stamp and sha256)", flush=True)
            skipped_count += 1
            write_render_heartbeat(
                heartbeat_path,
                window_id=window_id,
                state="running",
                total_jobs=len(jobs),
                skipped_jobs=skipped_count,
                images_rendered=rendered_count,
                heartbeat_seq=heartbeat_seq,
                started_at_epoch=started_at_epoch,
                last_image_at_epoch=last_image_at_epoch,
                last_job_id=last_rendered_job_id,
            )
            continue

        t0 = time.time()
        workflow = job.get("workflow")
        if not workflow:
            if job.get("template_id") == "stub_fixture_64":
                workflow = build_stub_fixture_graph(job)
            else:
                workflow = build_qwen_lora_graph(job)
        check_background_removal_allowed(workflow, job)

        stamp_meta = {
            "owner": job.get("owner", "mcp-tool-shop"),
            "licence": job.get("licence", PICTURE_LICENCE_REQUIRED),
            "credit": job.get("credit", PICTURE_CREDIT_REQUIRED),
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
        now_done = time.time()
        elapsed_s = max(0.0, now_done - t0)
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
            "credit": verified_stamp["credit"],
            "model_pins": job.get("model_pins"),
            "stamp_verified": True,
        }
        with renders_path.open("a", encoding="utf-8") as rf:
            rf.write(json.dumps(row) + "\n")

        completed_files.add(output_file)
        rendered_count += 1
        heartbeat_seq += 1
        last_image_at_epoch = now_done
        last_rendered_job_id = job_id
        hb_rec = write_render_heartbeat(
            heartbeat_path,
            window_id=window_id,
            state="running",
            total_jobs=len(jobs),
            skipped_jobs=skipped_count,
            images_rendered=rendered_count,
            heartbeat_seq=heartbeat_seq,
            started_at_epoch=started_at_epoch,
            last_image_at_epoch=last_image_at_epoch,
            last_job_id=last_rendered_job_id,
        )
        print(
            f"RENDERED {job_id} -> {output_file} ({png_sha}, {wall_s}s, peak_vram_mib={peak_vram_mib}, stamp_verified=True)",
            flush=True,
        )
        print(f"RENDER_HEARTBEAT {json.dumps(hb_rec)}", flush=True)

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

    write_render_heartbeat(
        heartbeat_path,
        window_id=window_id,
        state="killed_early" if killed_early else "completed",
        total_jobs=len(jobs),
        skipped_jobs=skipped_count,
        images_rendered=rendered_count,
        heartbeat_seq=heartbeat_seq,
        started_at_epoch=started_at_epoch,
        last_image_at_epoch=last_image_at_epoch,
        last_job_id=last_rendered_job_id,
    )

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
        "heartbeat_seq": heartbeat_seq,
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
        rung = _load_lane3_rung()
        if args.weights_manifest is None:
            print(rung.refuse_line("RENDER_MANIFEST_REQUIRED", "--render needs --weights-manifest <json>"), file=sys.stderr, flush=True)
            return 1
        try:
            checked = run_validate_inputs(
                manifest_path=args.weights_manifest,
                jobs_path=args.jobs,
                jobs_sha256=args.jobs_sha256,
                allow_no_jobs=args.allow_no_jobs,
            )
        except rung.Refusal as exc:
            print(rung.refuse_line(exc.code, exc.detail), file=sys.stderr, flush=True)
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
        rung = _load_lane3_rung()
        if args.weights_manifest is None:
            print(rung.refuse_line("RENDER_MANIFEST_REQUIRED", "--download-weights needs --weights-manifest <json>"), file=sys.stderr, flush=True)
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
