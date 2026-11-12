#!/usr/bin/env python3
"""Run on the VM by the lane 3 kit's failure path (`colab exec -f lane3_bundle_now.py`).

After a rig-side kill (wall, cap, stall or dead harness) the kit has stopped only its own exec; the
remote script is still running on the VM and its EXIT trap never fires, so there is no bundle to
download. This cell runs `lane3_rung.py bundle-now`, which stops the rung's processes, sweeps the
training folder into lane3_out/rung_outputs, writes the failure record, scrubs the logs and tars
lane3_out, so the kit's download that follows gets whatever the run had saved. Paths come from
`--env` (SDLAB_CONTENT, SDLAB_BUNDLE_RC); the cell prints a SDLAB_BUNDLE_NOW_RC=<rc> marker.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

_HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")


def _prepare_salvage_downloads(content_root: str, chunk_bytes: int) -> None:
    root = Path(content_root)
    if not root.is_dir() or chunk_bytes <= 0:
        return
    for vm_file in sorted(root.iterdir()):
        if not vm_file.is_file() or vm_file.name.startswith(".sdlab_") or not vm_file.name.endswith(".tar.gz"):
            continue
        rel = vm_file.name
        size = vm_file.stat().st_size
        if size <= chunk_bytes:
            h = hashlib.sha256()
            with vm_file.open("rb") as fh:
                for blk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(blk)
            rec: dict[str, object] = {
                "rel": rel,
                "exists": True,
                "split": False,
                "whole_bytes": size,
                "whole_sha256": h.hexdigest(),
                "chunk_bytes": chunk_bytes,
                "part_count": 1,
            }
            print("SDLAB_DOWNLOAD_PREPARE_JSON " + json.dumps(rec), flush=True)
            continue

        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", rel)[:48]
        prefix = f".sdlab_dl_{safe_name}"
        for stale in root.iterdir():
            if stale.name.startswith(prefix + ".") and stale.is_file():
                stale.unlink(missing_ok=True)
        whole_h = hashlib.sha256()
        parts: list[dict[str, object]] = []
        idx = 0
        with vm_file.open("rb") as fh:
            while True:
                remaining = chunk_bytes
                part_name = f"{prefix}.part.{idx:04d}"
                part_path = root / part_name
                part_h = hashlib.sha256()
                part_b = 0
                first_blk = fh.read(min(1 << 20, remaining))
                if not first_blk:
                    break
                with part_path.open("wb") as pfh:
                    pfh.write(first_blk)
                    part_h.update(first_blk)
                    whole_h.update(first_blk)
                    part_b += len(first_blk)
                    remaining -= len(first_blk)
                    while remaining > 0:
                        blk = fh.read(min(1 << 20, remaining))
                        if not blk:
                            break
                        pfh.write(blk)
                        part_h.update(blk)
                        whole_h.update(blk)
                        part_b += len(blk)
                        remaining -= len(blk)
                parts.append({
                    "index": idx,
                    "remote_path": f"/content/{part_name}",
                    "bytes": part_b,
                    "sha256": part_h.hexdigest(),
                })
                idx += 1
        whole_sha = whole_h.hexdigest()
        manifest_name = f"{prefix}.manifest.json"
        manifest_payload = {
            "remote": f"/content/{rel}",
            "prefix": prefix,
            "split": True,
            "whole_bytes": size,
            "whole_sha256": whole_sha,
            "chunk_bytes": chunk_bytes,
            "part_count": len(parts),
            "parts": parts,
        }
        (root / manifest_name).write_text(
            json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        rec = {
            "rel": rel,
            "exists": True,
            "split": True,
            "prefix": prefix,
            "manifest_remote": f"/content/{manifest_name}",
            "whole_bytes": size,
            "whole_sha256": whole_sha,
            "chunk_bytes": chunk_bytes,
            "part_count": len(parts),
        }
        print("SDLAB_DOWNLOAD_PREPARE_JSON " + json.dumps(rec), flush=True)
    print(f"SDLAB_DOWNLOAD_PREPARE_DONE chunk_bytes={chunk_bytes}", flush=True)


def bundle_now(env: dict[str, str] | None = None) -> int:
    env = dict(os.environ if env is None else env)
    root = env.get("SDLAB_CONTENT", "").strip()
    rc = env.get("SDLAB_BUNDLE_RC", "").strip()
    if not root or not rc.lstrip("-").isdigit():
        print("SDLAB_BUNDLE_NOW_RC=2 (SDLAB_CONTENT and SDLAB_BUNDLE_RC are required)", flush=True)
        return 2
    venv_py = os.path.join(root, "venv-lane3", "bin", "python")
    py = venv_py if os.path.exists(venv_py) else sys.executable
    res = subprocess.run([py, os.path.join(root, "lane3_rung.py"), "bundle-now", "--content", root, "--rc", rc],
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, env=env)
    sys.stdout.write(_HF_TOKEN_RE.sub("hf_[REDACTED]", res.stdout + res.stderr))
    dl_chunk_raw = env.get("SDLAB_DL_CHUNK_BYTES", "").strip()
    if res.returncode == 0 and dl_chunk_raw.isdigit() and int(dl_chunk_raw) > 0:
        _prepare_salvage_downloads(root, int(dl_chunk_raw))
    print(f"SDLAB_BUNDLE_NOW_RC={res.returncode}", flush=True)
    return res.returncode


if __name__ == "__main__":
    bundle_now()
