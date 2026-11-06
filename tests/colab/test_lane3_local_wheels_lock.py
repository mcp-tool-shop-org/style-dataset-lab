"""The lane 3 kit's generated local-wheels.lock, checked with real uv, and --emit-remote-script.

Window sdlab-l3-stub-4 died after a full lock install because the remote script wrote
lane3_out/local-wheels.lock with a literal backslash-n where a newline belonged, and uv refused
the file. The fake never parsed it, so the suite passed. These tests run the kit's own
lock-generation step, exactly as the kit uploads it, and hand the file it writes to real uv.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
LAUNCHER = COLAB_DIR / "launch_lane3_stub.sh"
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


def _p(p: Path) -> str:
    return fc._to_posix(p)


def _host_python() -> str:
    return fc._resolve_python()


def _run_kit_and_get_uploaded_script(tmp_path: Path, launcher: Path = LAUNCHER, extra_env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, str]]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    env.update(extra_env or {})
    out_dir = tmp_path / "out"
    res = subprocess.run(
        [_bash(), _p(launcher), "--out-dir", _p(out_dir), "--session", "sdlab-l3-lockcheck"],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return res, state_dir / "content" / "remote_lane3_stub.sh.uploaded", env


def _extract_lock_step(script_text: str) -> str:
    """The lock-generation step as the kit emits it: the venv python's WHEELPYEOF heredoc."""
    lines = script_text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.rstrip().endswith("<< 'WHEELPYEOF'")]
    assert len(starts) == 1, "the uploaded script must hold exactly one WHEELPYEOF lock step"
    end = lines.index("WHEELPYEOF", starts[0])
    return "\n".join(lines[starts[0]:end + 1]) + "\n"


def _fake_vm_with_wheels(vm: Path, manifest: Path, wheels_dir: Path) -> None:
    (vm / "lane3_out").mkdir(parents=True)
    (vm / "wheels").mkdir()
    shutil.copyfile(manifest, vm / "lane3-local-wheels.json")
    for whl in wheels_dir.glob("*.whl"):
        shutil.copyfile(whl, vm / "wheels" / whl.name)
    venv_bin = vm / "venv-lane3" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text(
        f'#!/usr/bin/env bash\nexec "{_p(Path(_host_python()))}" "$@"\n', encoding="utf-8", newline="\n"
    )
    (venv_bin / "python").chmod(0o755)


def _uv_install_lock(vm: Path, lock: Path) -> subprocess.CompletedProcess[str]:
    assert UV is not None
    check_venv = vm / "check-venv"
    subprocess.run([UV, "venv", "--quiet", "--python", _host_python(), str(check_venv)], check=True, timeout=120)
    venv_py = check_venv / "bin" / "python"
    if not venv_py.exists():
        venv_py = check_venv / "Scripts" / "python.exe"
    return subprocess.run(
        [
            UV, "pip", "install", "--python", str(venv_py),
            "--require-hashes", "--only-binary", ":all:", "--no-index",
            "--find-links", str(vm / "wheels"), "--no-deps", "-r", str(lock),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@needs_uv
def test_kit_lock_step_writes_a_lock_real_uv_installs(tmp_path: Path) -> None:
    res, uploaded, env = _run_kit_and_get_uploaded_script(tmp_path / "kit")
    assert uploaded.is_file(), f"kit uploaded no remote script\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    step = _extract_lock_step(uploaded.read_text(encoding="utf-8"))

    vm = tmp_path / "vm"
    _fake_vm_with_wheels(vm, Path(env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"]), Path(env["SDLAB_WHEEL_DIR"]))
    step_sh = tmp_path / "lock_step.sh"
    step_sh.write_text(step.replace("/content", _p(vm)), encoding="utf-8", newline="\n")
    gen = subprocess.run([_bash(), _p(step_sh)], capture_output=True, text=True, timeout=60, check=False)
    assert gen.returncode == 0, gen.stderr

    lock = vm / "lane3_out" / "local-wheels.lock"
    text = lock.read_text(encoding="utf-8")
    inst = _uv_install_lock(vm, lock)
    assert inst.returncode == 0, f"uv refused the kit's generated lock:\n{inst.stdout}\n{inst.stderr}\nLOCK:\n{text!r}"
    assert "fixture-a==1.0" in inst.stderr and "fixture-b==2.0" in inst.stderr, inst.stderr
    assert "\\n" not in text, f"literal backslash-n in the generated lock: {text!r}"
    assert text.endswith("\n") and text.count("\n") == 2, repr(text)


@needs_uv
def test_fake_runs_the_kit_lock_step_and_uv_accepts_it(tmp_path: Path) -> None:
    res, _, _ = _run_kit_and_get_uploaded_script(tmp_path)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    setup = (tmp_path / "colab_state" / "content" / "lane3_out" / "setup.log").read_text(encoding="utf-8")
    assert "LOCAL_WHEELS_LOCK_UV_OK" in setup


@needs_uv
def test_fake_fails_the_stub_when_uv_rejects_the_kit_lock(tmp_path: Path) -> None:
    # A copy of the kit with the sdlab-l3-stub-4 line put back: the fake must fail the stub.
    kit_dir = tmp_path / "kit" / "scripts" / "colab"
    shutil.copytree(COLAB_DIR, kit_dir)
    launcher = kit_dir / "launch_lane3_stub.sh"
    src = launcher.read_text(encoding="utf-8")
    good = '    lines.append(f"{pkg}=={ver} --hash=sha256:{exp_sha}" + chr(10))'
    bad = '    lines.append(f"{pkg}=={ver} \\\\\\n    --hash=sha256:{exp_sha}\\n")'
    assert good in src
    launcher.write_text(src.replace(good, bad), encoding="utf-8", newline="\n")
    sha = hashlib.sha256(launcher.read_bytes()).hexdigest()

    res, _, _ = _run_kit_and_get_uploaded_script(
        tmp_path / "run", launcher=launcher, extra_env={"EXPECTED_LAUNCH_LANE3_STUB_SHA": sha}
    )
    out = res.stdout + res.stderr
    assert res.returncode != 0, out
    vitals = (tmp_path / "run" / "out" / "vitals.log").read_text(encoding="utf-8")
    assert "REFUSED: LOCAL_WHEELS_LOCK_REJECTED" in vitals
    assert "SDLAB_REMOTE_RC=1" in vitals


def test_fake_refuses_an_uploaded_script_without_the_lock_block(tmp_path: Path) -> None:
    kit_dir = tmp_path / "kit" / "scripts" / "colab"
    shutil.copytree(COLAB_DIR, kit_dir)
    launcher = kit_dir / "launch_lane3_stub.sh"
    src = launcher.read_text(encoding="utf-8")
    assert "# >>> sdlab-local-wheels-lock\n" in src
    launcher.write_text(src.replace("# >>> sdlab-local-wheels-lock\n", ""), encoding="utf-8", newline="\n")
    sha = hashlib.sha256(launcher.read_bytes()).hexdigest()
    res, _, _ = _run_kit_and_get_uploaded_script(
        tmp_path / "run", launcher=launcher, extra_env={"EXPECTED_LAUNCH_LANE3_STUB_SHA": sha}
    )
    assert res.returncode != 0
    vitals = (tmp_path / "run" / "out" / "vitals.log").read_text(encoding="utf-8")
    assert "REFUSED: LOCAL_WHEELS_LOCK_BLOCK_MISSING" in vitals


def test_emit_remote_script_matches_the_uploaded_script_and_calls_no_colab(tmp_path: Path) -> None:
    res, uploaded, env = _run_kit_and_get_uploaded_script(tmp_path / "kit")
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    _, state_dir, emit_env = fc.make_fake_colab_env(tmp_path / "emit")
    emitted = tmp_path / "emitted" / "remote_lane3_stub.sh"
    emitted.parent.mkdir()
    em = subprocess.run(
        [_bash(), _p(LAUNCHER), "--emit-remote-script", _p(emitted)],
        env=emit_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert em.returncode == 0, em.stderr
    assert "REMOTE_SCRIPT_EMITTED" in em.stdout
    assert emitted.read_bytes() == uploaded.read_bytes()
    assert not (state_dir / "calls.log").exists(), "--emit-remote-script must make no colab call"

    env_lines = Path(f"{emitted}.env").read_text(encoding="utf-8").splitlines()
    keys = [line.split("=", 1)[0] for line in env_lines]
    assert keys == [
        "PINNED_UV_VERSION", "PINNED_UV_WHEEL_SHA256", "PINNED_PYTHON_VERSION", "PINNED_PYTHON_BUILD",
        "PINNED_PYTORCH_INDEX_URL", "PINNED_AI_TOOLKIT_REPO", "PINNED_AI_TOOLKIT_COMMIT", "PINNED_OVERRIDE_SHA",
    ]
    lock_sha = hashlib.sha256((COLAB_DIR / "locks" / "lane3.lock").read_bytes()).hexdigest()
    assert f"PINNED_OVERRIDE_SHA={lock_sha}" in env_lines
    # The live exec passes the same values (the fake records each --env it was given).
    calls = (tmp_path / "kit" / "colab_state" / "calls.log").read_text(encoding="utf-8")
    for line in env_lines[:-1]:
        assert line in calls, line


@pytest.mark.parametrize(
    "extra",
    [
        ["--out-dir", "x"],
        ["--session", "s"],
        ["--card", "CPU"],
        ["--wheel-dir", "w"],
        ["--cap", "0.1"],
        ["--wall-s", "60"],
        ["--grace-s", "5"],
        ["--margin", "0.01"],
    ],
)
def test_emit_remote_script_refuses_beside_any_window_option(tmp_path: Path, extra: list[str]) -> None:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    target = tmp_path / "r.sh"
    res = subprocess.run(
        [_bash(), _p(LAUNCHER), *extra, "--emit-remote-script", _p(target)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 2
    assert "REFUSED: EMIT_REMOTE_SCRIPT_EXCLUSIVE" in res.stderr
    assert extra[0] in res.stderr
    assert not target.exists()
    assert not (state_dir / "calls.log").exists()


def test_emit_remote_script_needs_a_path_and_works_without_any_colab_on_path(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SDLAB_", "FAKE_COLAB", "EXPECTED_"))}
    res = subprocess.run(
        [_bash(), _p(LAUNCHER), "--emit-remote-script"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False,
    )
    assert res.returncode == 2
    assert "REFUSED: EMIT_REMOTE_SCRIPT_PATH_REQUIRED" in res.stderr

    target = tmp_path / "r.sh"
    ok = subprocess.run(
        [_bash(), _p(LAUNCHER), "--emit-remote-script", _p(target)],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False,
    )
    assert ok.returncode == 0, ok.stderr
    text = target.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "# >>> sdlab-local-wheels-lock\n" in text and "# <<< sdlab-local-wheels-lock\n" in text


def test_lane3_lock_and_import_gate_carry_torchaudio() -> None:
    # The local walk (2026-11-06) found ai-toolkit's run.py failing with "No module named
    # 'torchaudio'" (toolkit/config_modules.py imports it; upstream installs it beside torch).
    lane3_in = (COLAB_DIR / "locks" / "lane3.in").read_text(encoding="utf-8")
    lock = (COLAB_DIR / "locks" / "lane3.lock").read_text(encoding="utf-8")
    assert "\ntorchaudio==2.11.1\n" in lane3_in
    assert "\ntorchaudio==2.11.1 \\\n" in lock
    kit = LAUNCHER.read_text(encoding="utf-8")
    assert 'REQUIRED = ("sentencepiece", "torch", "torchaudio",' in kit


def _extract_block(script_text: str, name: str) -> str:
    lines = script_text.split("\n")
    start = lines.index(f"# >>> {name}")
    end = lines.index(f"# <<< {name}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


@pytest.mark.parametrize("train_rc", [0, 3])
def test_train_step_names_its_failure_on_the_exec_stream(tmp_path: Path, train_rc: int) -> None:
    emitted = tmp_path / "r.sh"
    em = subprocess.run(
        [_bash(), _p(LAUNCHER), "--emit-remote-script", _p(emitted)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False,
    )
    assert em.returncode == 0, em.stderr
    block = _extract_block(emitted.read_text(encoding="utf-8"), "sdlab-train-step")
    vm = tmp_path / "vm"
    (vm / "lane3_out").mkdir(parents=True)
    venv_bin = vm / "venv-lane3" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text(
        f"#!/usr/bin/env bash\necho 'trainer line one'\necho 'ModuleNotFoundError: no torchaudio'\nexit {train_rc}\n",
        encoding="utf-8", newline="\n",
    )
    (venv_bin / "python").chmod(0o755)
    step = tmp_path / "train_step.sh"
    step.write_text("set -euo pipefail\n" + block.replace("/content", _p(vm)), encoding="utf-8", newline="\n")
    res = subprocess.run([_bash(), _p(step)], capture_output=True, text=True, timeout=30, check=False)
    if train_rc == 0:
        assert res.returncode == 0, res.stderr
        assert "TRAIN_FAILED" not in res.stdout + res.stderr
    else:
        assert res.returncode == 1
        assert "ModuleNotFoundError: no torchaudio" in res.stdout
        assert "REFUSED: TRAIN_FAILED: ai-toolkit run.py exited 3" in res.stderr
