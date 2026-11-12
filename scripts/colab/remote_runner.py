#!/usr/bin/env python3
"""Remote kernel runner executed via `colab exec -s <session> -f remote_runner.py`.

Runs the uploaded remote shell script (`SDLAB_REMOTE_SCRIPT`, e.g.
`/content/remote_lane1_stub.sh` or `/content/remote_lane3_stub.sh`) via
`subprocess.Popen`, streaming each stdout/stderr line to the IPython kernel's
stdout as it arrives so the rig's vitals and DEAD HARNESS watcher read it in
real time, and finishes by printing a `SDLAB_REMOTE_RC=<rc>` marker line.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

# Exec outputs land in google-colab-cli's history (docs/colab-cli-contract.md, section 3), so no line
# that could carry a Hugging Face token is relayed as it is.
_HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")


def scrub_line(line: str) -> str:
    return _HF_TOKEN_RE.sub("hf_[REDACTED]", line)


def _resolve_bash(env: dict[str, str]) -> str:
    git_bash = "C:/Program Files/Git/bin/bash.exe"
    if os.name == "nt" and os.path.exists(git_bash):
        return git_bash
    found = shutil.which("bash", path=env.get("PATH"))
    return found or "bash"


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


def prepare_content_downloads(
    content_root: str | Path,
    chunk_bytes: int,
    *,
    free_bytes_override: int | None = None,
) -> list[dict[str, object]]:
    """Delegate bundle inspect/split preparation to the single source in `launch_guards.py`."""
    lg = _load_launch_guards(content_root)
    return list(
        lg.prepare_content_downloads(
            content_root, chunk_bytes, free_bytes_override=free_bytes_override
        )
    )


def run_remote_script(
    script_path: str | None = None,
    *,
    env: dict[str, str] | None = None,
) -> int:
    effective_env = dict(os.environ if env is None else env)
    target_script = script_path or effective_env.get("SDLAB_REMOTE_SCRIPT", "").strip()
    if not target_script:
        print("REFUSED: SDLAB_REMOTE_SCRIPT is required", file=sys.stderr, flush=True)
        print("SDLAB_REMOTE_RC=2", flush=True)
        return 2

    cmd = [_resolve_bash(effective_env), target_script]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=effective_env,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(scrub_line(line))
        sys.stdout.flush()
    rc = int(proc.wait())
    content_root = effective_env.get("SDLAB_CONTENT", "").strip()
    dl_chunk_raw = effective_env.get("SDLAB_DL_CHUNK_BYTES", "").strip()
    if content_root and dl_chunk_raw.isdigit() and int(dl_chunk_raw) > 0:
        prepare_content_downloads(content_root, int(dl_chunk_raw))
    print(f"SDLAB_REMOTE_RC={rc}", flush=True)
    return rc


if __name__ == "__main__":
    run_remote_script()
