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
import subprocess
import sys


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
    sys.stdout.write(res.stdout + res.stderr)
    print(f"SDLAB_BUNDLE_NOW_RC={res.returncode}", flush=True)
    return res.returncode


if __name__ == "__main__":
    bundle_now()
