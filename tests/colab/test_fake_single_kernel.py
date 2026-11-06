"""The fake colab CLI models one kernel per session (docs/colab-cli-contract.md, section 4)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))

import fake_colab as fc  # noqa: E402


def _colab(env: dict[str, str], bin_dir: Path, *args: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(bin_dir / "colab"), *args], env=env, capture_output=True, text=True, timeout=timeout,
                          check=False)


def test_exec_queues_behind_a_running_cell_and_restart_kernel_ends_it(tmp_path: Path) -> None:
    bin_dir, state_dir, env = fc.make_fake_colab_env(tmp_path)
    slow = tmp_path / "slow.py"
    slow.write_text("import time\nprint('slow started', flush=True)\ntime.sleep(60)\n", encoding="utf-8")
    quick = tmp_path / "quick.py"
    quick.write_text("print('quick ran', flush=True)\n", encoding="utf-8")
    assert _colab(env, bin_dir, "new", "-s", "s1").returncode == 0
    # The local exec gives up after 1 s; the cell keeps running on the kernel.
    first = _colab(env, bin_dir, "exec", "-s", "s1", "-f", str(slow), "--timeout", "1")
    assert first.returncode == 124 and "slow started" in first.stdout
    # A second exec on the same session queues behind it (and times out waiting).
    t0 = time.monotonic()
    second = _colab(env, bin_dir, "exec", "-s", "s1", "-f", str(quick), "--timeout", "2")
    assert second.returncode == 124 and "quick ran" not in second.stdout and time.monotonic() - t0 >= 2
    # restart-kernel ends the running cell; the next exec runs at once.
    assert _colab(env, bin_dir, "restart-kernel", "-s", "s1").returncode == 0
    third = _colab(env, bin_dir, "exec", "-s", "s1", "-f", str(quick), "--timeout", "20")
    assert third.returncode == 0 and "quick ran" in third.stdout
    # History keeps the code and the outputs of completed execs.
    rows = [json.loads(x) for x in (state_dir / "history" / "s1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["code"].endswith("print('quick ran', flush=True)\n")
    assert "quick ran" in rows[-1]["outputs"][0]["text"]
    assert "RESTART -s s1" in (state_dir / "restarts.log").read_text(encoding="utf-8")
    assert _colab(env, bin_dir, "stop", "-s", "s1").returncode == 0


def test_uploads_do_not_wait_for_the_kernel_and_stop_ends_the_cell(tmp_path: Path) -> None:
    bin_dir, state_dir, env = fc.make_fake_colab_env(tmp_path)
    slow = tmp_path / "slow.py"
    marker = state_dir / "content" / "cell_alive"
    slow.write_text(f"import pathlib, time\npathlib.Path({str(marker)!r}).write_text('x')\ntime.sleep(60)\n",
                    encoding="utf-8")
    src = tmp_path / "f.txt"
    src.write_text("data", encoding="utf-8")
    _colab(env, bin_dir, "new", "-s", "s2")
    assert _colab(env, bin_dir, "exec", "-s", "s2", "-f", str(slow), "--timeout", "1").returncode == 124
    t0 = time.monotonic()
    up = _colab(env, bin_dir, "upload", "-s", "s2", str(src), "/content/f.txt")
    assert up.returncode == 0 and time.monotonic() - t0 < 10
    assert fc._running_cell(state_dir, "s2") is not None
    assert _colab(env, bin_dir, "stop", "-s", "s2").returncode == 0
    for _ in range(100):
        if fc._running_cell(state_dir, "s2") is None:
            break
        time.sleep(0.05)
    assert fc._running_cell(state_dir, "s2") is None
