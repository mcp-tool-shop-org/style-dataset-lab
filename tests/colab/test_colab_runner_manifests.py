"""Manifest schema, pinned SHA parity, and offline VM job execution tests for colab-runner migration."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"

ALLOWED_TOP = frozenset({"schema_version", "project", "compute", "inputs", "job", "outputs"})
ALLOWED_SECTION_KEYS = {
    "project": frozenset({"repo", "study", "job", "description", "purpose", "line"}),
    "compute": frozenset({
        "card", "shape", "max_rate", "cap", "wall_s", "margin", "cleanup_bound_s", "poll_s",
        "setup_stall_s", "progress_stall_s", "unreachable_polls", "unreachable_s", "resident",
        "omp_num_threads", "min_vram_mib", "min_vram_mib_by_card",
    }),
    "inputs": frozenset({"root", "files", "deny_globs", "sealed"}),
    "job": frozenset({"setup", "run", "cpu_dry_run", "progress_glob", "units_glob", "env"}),
    "outputs": frozenset({"collect", "salvage", "download_parts"}),
}


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _p(p: Path) -> str:
    s = p.resolve().as_posix()
    return f"/{s[0].lower()}{s[2:]}" if (len(s) >= 2 and s[1] == ":") else s


@pytest.mark.parametrize(
    ("lane_dir", "lock_name", "pin_var"),
    [("lane1", "lane1.lock", "PINNED_LOCK_SHA"), ("lane3", "lane3.lock", "PINNED_OVERRIDE_SHA")],
)
def test_colab_window_toml_matches_strict_schema_and_pinned_lock_sha(lane_dir: str, lock_name: str, pin_var: str) -> None:
    spec_path = COLAB_DIR / lane_dir / "colab-window.toml"
    raw = tomllib.loads(spec_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert set(raw) <= ALLOWED_TOP
    for sec, allowed in ALLOWED_SECTION_KEYS.items():
        if sec in raw:
            assert set(raw[sec]) <= allowed, (lane_dir, sec, set(raw[sec]) - allowed)

    root = (spec_path.parent / raw["inputs"]["root"]).resolve()
    wheel_entries: dict[str, str] = {}
    for item in raw["inputs"]["files"]:
        src = item["src"] if isinstance(item, dict) else item
        dst = item["dst"] if isinstance(item, dict) else item
        if src.startswith("locks/wheels/"):
            wheel_entries[src] = dst
        else:
            assert (root / src).is_file(), f"missing staged input: {src}"
    if lane_dir == "lane3":
        wheels_meta = json.loads((COLAB_DIR / "locks" / "lane3-local-wheels.json").read_text(encoding="utf-8"))
        expected_wheels = {
            f"locks/wheels/{w['filename']}": f"wheels/{w['filename']}" for w in wheels_meta["wheels"]
        }
        assert wheel_entries == expected_wheels

    vm_job = (COLAB_DIR / lane_dir / "vm_job.sh").read_text(encoding="utf-8")
    pin_line = next(ln for ln in vm_job.splitlines() if ln.startswith(f"{pin_var}="))
    pinned_sha = pin_line.split('"', 2)[1]
    actual_sha = hashlib.sha256((COLAB_DIR / "locks" / lock_name).read_bytes()).hexdigest()
    assert pinned_sha == actual_sha


def test_lane1_vm_job_local_fast_and_mode_refusals(tmp_path: Path) -> None:
    work = tmp_path / "work"
    out = tmp_path / "out"
    work.mkdir()
    shutil.copyfile(COLAB_DIR / "lane1" / "vm_job.sh", work / "vm_job.sh")
    shutil.copyfile(COLAB_DIR / "locks" / "lane1.lock", work / "lane1.lock")

    ok = subprocess.run(
        [_bash(), _p(work / "vm_job.sh")],
        env={"PATH": "/usr/bin:/bin", "CR_WORK_DIR": _p(work), "CR_OUT_DIR": _p(out),
             "LANE1_MODE": "stub", "LANE1_LOCAL_FAST": "1"},
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )
    assert ok.returncode == 0, ok.stderr
    assert (out / "phase.txt").read_text(encoding="utf-8").strip() == "run"
    assert (out / "lane1_out" / "pngs" / "local_01.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    win = json.loads((out / "lane1_out" / "vm_window.json").read_text(encoding="utf-8"))
    assert win["synthetic_proof"] is True and win["rendered"] == 2

    bad = subprocess.run(
        [_bash(), _p(work / "vm_job.sh")],
        env={"PATH": "/usr/bin:/bin", "CR_WORK_DIR": _p(work), "CR_OUT_DIR": _p(tmp_path / "out_bad"), "LANE1_MODE": "bogus"},
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )
    assert bad.returncode == 1 and "REFUSED: LANE1_MODE_INVALID" in bad.stderr


def test_lane3_vm_job_local_fast_and_token_shred(tmp_path: Path) -> None:
    work = tmp_path / "work"
    out = tmp_path / "out"
    work.mkdir()
    shutil.copyfile(COLAB_DIR / "lane3" / "vm_job.sh", work / "vm_job.sh")
    shutil.copyfile(COLAB_DIR / "locks" / "lane3.lock", work / "lane3.lock")
    tok = work / "lane3_hf_read_token"
    tok.write_text("hf_dummy_test_token_value", encoding="utf-8")

    ok = subprocess.run(
        [_bash(), _p(work / "vm_job.sh")],
        env={"PATH": "/usr/bin:/bin", "CR_WORK_DIR": _p(work), "CR_OUT_DIR": _p(out),
             "LANE3_MODE": "install", "LANE3_LOCAL_FAST": "1"},
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )
    assert ok.returncode == 0, ok.stderr
    assert not tok.exists()
    assert "TRAIN_SKIPPED" in (out / "setup.log").read_text(encoding="utf-8")
    win = json.loads((out / "lane3_out" / "vm_window.json").read_text(encoding="utf-8"))
    assert win["train"] == "skipped_cpu_stub" and win["checkpoint_path"] is None
