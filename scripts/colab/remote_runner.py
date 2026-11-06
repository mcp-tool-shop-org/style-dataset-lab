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
    print(f"SDLAB_REMOTE_RC={rc}", flush=True)
    return rc


if __name__ == "__main__":
    run_remote_script()
