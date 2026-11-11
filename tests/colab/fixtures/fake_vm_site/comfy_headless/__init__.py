"""Stand-in for comfy_headless on the fake VM for hermetic offline Lane 1 render tests."""

from __future__ import annotations

import json
import struct
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__version__ = "3.1.0"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class WorkflowMetadata:
    has_prompt: bool
    prompt: dict[str, Any] | None = None


def read_png_text_chunks(png_source: Path | bytes) -> dict[str, str]:
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


def read_workflow_metadata(png_source: Path | bytes) -> WorkflowMetadata:
    chunks = read_png_text_chunks(png_source)
    raw = chunks.get("prompt")
    if not raw:
        return WorkflowMetadata(has_prompt=False, prompt=None)
    try:
        parsed = json.loads(raw)
        return WorkflowMetadata(has_prompt=isinstance(parsed, dict) and bool(parsed), prompt=parsed)
    except ValueError:
        return WorkflowMetadata(has_prompt=False, prompt=None)


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base_url = base_url.rstrip("/")

    def queue_prompt(self, workflow: dict[str, Any], extra_pnginfo: dict[str, str] | None = None) -> str:
        body = json.dumps({"prompt": workflow, "extra_pnginfo": extra_pnginfo or {}}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data["prompt_id"])

    def wait_for_completion(
        self,
        prompt_id: str,
        timeout: float = 120.0,
        poll_interval: float = 0.2,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with urllib.request.urlopen(f"{self.base_url}/history/{prompt_id}", timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if prompt_id in data and data[prompt_id].get("outputs"):
                return data[prompt_id]
            time.sleep(min(poll_interval, 0.05))
        return {}
