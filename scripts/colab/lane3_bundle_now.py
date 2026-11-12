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

import os
from pathlib import Path
import re
import subprocess
import sys

_HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")


def _load_launch_guards(content_root: str | Path):
    for candidate in (Path(content_root), Path.cwd()):
        if (candidate / "launch_guards.py").is_file():
            cand_str = str(candidate)
            if cand_str not in sys.path:
                sys.path.insert(0, cand_str)
            break
    else:
        g_file = globals().get("__file__")
        if g_file:
            here = str(Path(g_file).resolve().parent)
            if here not in sys.path:
                sys.path.insert(0, here)
    import launch_guards  # type: ignore[import-not-found]

    return launch_guards


def _prepare_salvage_downloads(
    content_root: str | Path,
    chunk_bytes: int,
    *,
    free_bytes_override: int | None = None,
) -> list[dict[str, object]]:
    """Delegate salvage bundle inspect/split preparation to `launch_guards.prepare_content_downloads`."""
    lg = _load_launch_guards(content_root)
    return list(
        lg.prepare_content_downloads(
            content_root, chunk_bytes, free_bytes_override=free_bytes_override
        )
    )


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
