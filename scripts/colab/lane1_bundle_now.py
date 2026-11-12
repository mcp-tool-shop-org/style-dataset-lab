#!/usr/bin/env python3
"""Run on the VM by the lane 1 kit's failure path (`colab exec -f lane1_bundle_now.py`).

After a rig-side kill (wall, cap, stall or dead harness) the kit has stopped only its own exec; the remote
render script is still running on the VM and its EXIT trap never fires, so there is no bundle to download.
This cell stops the render processes, merges the render facts, scrubs the logs and tars `lane1_out` (the
stamped PNGs in `pngs/`, `renders.jsonl`, the copy-back folder, the logs) into
`/content/lane1_render_bundle.tar.gz`, then splits it for download the way the train lane's salvage does, so
the kit's keep-all download that follows gets everything the run had rendered.

Paths come from `--env` (SDLAB_CONTENT, SDLAB_BUNDLE_RC, SDLAB_DL_CHUNK_BYTES); the cell prints a
SDLAB_BUNDLE_NOW_RC=<rc> marker.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

_HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")
# Paths under the content root, so only this VM's render processes match.
_PROCESS_SUFFIXES = ("ComfyUI/main.py", "lane1_render.py", "remote_lane1_stub.sh")


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


def _run(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, env=env)


def bundle_now(env: dict[str, str] | None = None) -> int:
    env = dict(os.environ if env is None else env)
    root = env.get("SDLAB_CONTENT", "").strip()
    rc = env.get("SDLAB_BUNDLE_RC", "").strip()
    if not root or not rc.lstrip("-").isdigit():
        print("SDLAB_BUNDLE_NOW_RC=2 (SDLAB_CONTENT and SDLAB_BUNDLE_RC are required)", flush=True)
        return 2
    out = Path(root) / "lane1_out"
    venv_py = os.path.join(root, "venv-lane1", "bin", "python")
    py = venv_py if os.path.exists(venv_py) else sys.executable

    # 1. stop whatever is still rendering (the restart-kernel before this cell may have left children running).
    for suffix in _PROCESS_SUFFIXES:
        _run(["pkill", "-f", "--", re.escape(f"{root.rstrip('/')}/{suffix}")], env)

    if not out.is_dir():
        print(f"SDLAB_BUNDLE_NOW_RC=1 ({out} does not exist: nothing was rendered)", flush=True)
        return 1

    # 2. merge the render facts so vm_window.json names the failure (best effort).
    res = _run([py, os.path.join(root, "lane1_render.py"), "--merge-render-facts", "--lane1-out", str(out), "--failed-rc", rc], env)
    sys.stdout.write(_HF_TOKEN_RE.sub("hf_[REDACTED]", res.stdout + res.stderr))

    # 3. scrub every log, json and text file before it is tarred.
    scrub_args: list[str] = []
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.suffix in (".log", ".json", ".jsonl", ".txt"):
            scrub_args += ["--scrub-file", str(f)]
    if scrub_args:
        _run([py, os.path.join(root, "launch_guards.py"), *scrub_args], env)

    # 4. tar everything, PNGs and renders.jsonl included.
    bundle = Path(root) / "lane1_render_bundle.tar.gz"
    tar = _run(["tar", "-czf", str(bundle), "-C", str(out), "."], env)
    sys.stdout.write(_HF_TOKEN_RE.sub("hf_[REDACTED]", tar.stdout + tar.stderr))
    final_rc = 0 if bundle.is_file() and bundle.stat().st_size > 0 else 1
    print(f"RENDER_BUNDLE_NOW rc={rc} bundle={bundle} bytes={bundle.stat().st_size if bundle.is_file() else 0}", flush=True)

    # 5. split for download exactly as the train lane's salvage does.
    dl_chunk_raw = env.get("SDLAB_DL_CHUNK_BYTES", "").strip()
    if final_rc == 0 and dl_chunk_raw.isdigit() and int(dl_chunk_raw) > 0:
        lg = _load_launch_guards(root)
        list(lg.prepare_content_downloads(root, int(dl_chunk_raw)))
    print(f"SDLAB_BUNDLE_NOW_RC={final_rc}", flush=True)
    return final_rc


if __name__ == "__main__":
    bundle_now()
