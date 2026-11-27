"""Lane 3 local-wheels lock generation tested directly from `scripts/colab/lane3/vm_job.sh` with real uv."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
VM_JOB = COLAB_DIR / "lane3" / "vm_job.sh"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))
import fake_colab as fc  # noqa: E402

UV = shutil.which("uv")
needs_uv = pytest.mark.skipif(UV is None, reason="real uv is not on PATH (CI installs uv 0.13.5)")


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _extract_lock_step(script_text: str) -> str:
    lines = script_text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.rstrip().endswith("<< 'WHEELPYEOF'")]
    assert len(starts) == 1, "vm_job.sh must hold exactly one WHEELPYEOF lock step"
    end = lines.index("WHEELPYEOF", starts[0])
    return "\n".join(lines[starts[0]:end + 1]) + "\n"


@needs_uv
def test_vm_job_lock_step_writes_a_lock_real_uv_installs(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    vm = tmp_path / "vm"
    (vm / "lane3_out").mkdir(parents=True)
    (vm / "wheels").mkdir()
    manifest_p = Path(env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"])
    shutil.copyfile(manifest_p, vm / "lane3-local-wheels.json")
    manifest_sha = hashlib.sha256(manifest_p.read_bytes()).hexdigest()
    for whl in Path(env["SDLAB_WHEEL_DIR"]).glob("*.whl"):
        shutil.copyfile(whl, vm / "wheels" / whl.name)
    venv_bin = vm / "venv-lane3" / "bin"
    venv_bin.mkdir(parents=True)
    py_posix = fc._to_posix(Path(fc._resolve_python()))
    (venv_bin / "python").write_text(f'#!/usr/bin/env bash\nexec "{py_posix}" "$@"\n', encoding="utf-8", newline="\n")
    (venv_bin / "python").chmod(0o755)

    step = _extract_lock_step(VM_JOB.read_text(encoding="utf-8"))
    step_sh = tmp_path / "lock_step.sh"
    step_sh.write_text(
        f'PINNED_LOCAL_WHEELS_MANIFEST_SHA="{manifest_sha}"\n' + step.replace("/content", fc._to_posix(vm)),
        encoding="utf-8", newline="\n",
    )
    gen = subprocess.run([_bash(), fc._to_posix(step_sh)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, check=False)
    assert gen.returncode == 0, gen.stderr

    lock = vm / "lane3_out" / "local-wheels.lock"
    text = lock.read_text(encoding="utf-8")
    assert "\\n" not in text and text.endswith("\n") and text.count("\n") == 2
    assert UV is not None
    check_venv = vm / "check-venv"
    subprocess.run([UV, "venv", "--quiet", "--python", fc._resolve_python(), str(check_venv)], check=True, stdin=subprocess.DEVNULL, timeout=120)
    venv_py = check_venv / "bin" / "python"
    if not venv_py.exists():
        venv_py = check_venv / "Scripts" / "python.exe"
    inst = subprocess.run(
        [UV, "pip", "install", "--python", str(venv_py), "--require-hashes", "--only-binary", ":all:", "--no-index",
         "--find-links", str(vm / "wheels"), "--no-deps", "-r", str(lock)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, check=False,
    )
    assert inst.returncode == 0, f"{inst.stdout}\n{inst.stderr}"


def test_lane3_lock_and_import_gate_carry_torchaudio() -> None:
    lane3_in = (COLAB_DIR / "locks" / "lane3.in").read_text(encoding="utf-8")
    lock = (COLAB_DIR / "locks" / "lane3.lock").read_text(encoding="utf-8")
    vm_src = VM_JOB.read_text(encoding="utf-8")
    assert "\ntorchaudio==2.11.1\n" in lane3_in
    assert "\ntorchaudio==2.11.1 \\\n" in lock
    assert 'REQUIRED = ("sentencepiece", "torch", "torchaudio",' in vm_src
