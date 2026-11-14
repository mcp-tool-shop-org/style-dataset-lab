#!/usr/bin/env python3
"""Remote kernel runner executed via `colab exec -s <session> -f remote_runner.py`.

Supports two execution modes controlled by `SDLAB_RUNNER_MODE`:
  - `stream` (default when unset, preserving direct caller compatibility): runs
    `SDLAB_REMOTE_SCRIPT` synchronously, streaming scrubbed lines to kernel stdout
    and finishing with `SDLAB_REMOTE_RC=<rc>`.
  - `start` / `poll` / `kill` (detached mode used by `colab_run_exec_with_live_guards`):
    `start` spawns the background worker via `launch_guards.py` (writing scrubbed output,
    bundle download preparation, and exit rc to `/content/.sdlab_live.*`) and exits
    immediately so transient host NIC/WebSocket resets never wedge the run; `poll`
    reads complete newline-bounded chunks from `SDLAB_POLL_OFFSET`; `kill` terminates
    recorded worker/child PIDs.
"""

from __future__ import annotations

import json
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
    mode = effective_env.get("SDLAB_RUNNER_MODE", "").strip().lower()
    content_root = effective_env.get("SDLAB_CONTENT", "").strip() or "/content"

    if mode == "poll":
        lg = _load_launch_guards(content_root)
        offset_raw = effective_env.get("SDLAB_POLL_OFFSET", "0").strip()
        max_raw = effective_env.get("SDLAB_POLL_MAX_BYTES", "").strip()
        offset_val = int(offset_raw) if offset_raw.lstrip("-").isdigit() else 0
        max_val = int(max_raw) if max_raw.isdigit() and int(max_raw) > 0 else lg.DETACHED_POLL_MAX_BYTES_DEFAULT
        poll_rec = lg.poll_detached_output(content_root, offset=offset_val, max_bytes=max_val)
        print(f"{lg.DETACHED_POLL_PREFIX}{json.dumps(poll_rec)}", flush=True)
        return 0

    if mode == "kill":
        lg = _load_launch_guards(content_root)
        kill_rec = lg.stop_detached_worker(content_root)
        print(f"{lg.DETACHED_KILLED_PREFIX}{json.dumps(kill_rec)}", flush=True)
        return 0

    if mode not in ("", "stream", "start"):
        print(f"REFUSED: unknown SDLAB_RUNNER_MODE={mode!r}", file=sys.stderr, flush=True)
        print("SDLAB_REMOTE_RC=2", flush=True)
        return 2

    target_script = script_path or effective_env.get("SDLAB_REMOTE_SCRIPT", "").strip()
    if not target_script:
        print("REFUSED: SDLAB_REMOTE_SCRIPT is required", file=sys.stderr, flush=True)
        print("SDLAB_REMOTE_RC=2", flush=True)
        return 2

    if mode == "start":
        lg = _load_launch_guards(content_root)
        start_rec = lg.start_detached_worker(content_root, script_path=target_script, env=effective_env)
        print(f"{lg.DETACHED_STARTED_PREFIX}{json.dumps(start_rec)}", flush=True)
        return 0

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
    dl_chunk_raw = effective_env.get("SDLAB_DL_CHUNK_BYTES", "").strip()
    if effective_env.get("SDLAB_CONTENT", "").strip() and dl_chunk_raw.isdigit() and int(dl_chunk_raw) > 0:
        prepare_content_downloads(content_root, int(dl_chunk_raw))
    print(f"SDLAB_REMOTE_RC={rc}", flush=True)
    return rc


if __name__ == "__main__":
    run_remote_script()
