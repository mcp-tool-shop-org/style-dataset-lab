"""Minimal fake Colab CLI marker and git/wheel fixture builders for offline preflight_resolve tests."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


def _to_posix(p: Path) -> str:
    s = p.resolve().as_posix()
    if len(s) >= 2 and s[1] == ":":
        return f"/{s[0].lower()}{s[2:]}"
    return s


def _resolve_python() -> str:
    sdlab_py = os.environ.get("SDLAB_PYTHON", "").strip()
    if sdlab_py and Path(sdlab_py).exists():
        return sdlab_py
    return sys.executable


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=sdlab-test", "-c", "user.email=sdlab-test@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL,
    )
    return res.stdout.strip()


def make_fixture_git_repo(repo: Path) -> tuple[str, str, str]:
    """A two-commit local repo: returns (file:// URL, tip sha, parent sha)."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "fixture parent")
    parent = _git(repo, "rev-parse", "HEAD")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "fixture tip")
    tip = _git(repo, "rev-parse", "HEAD")
    return f"file://{_to_posix(repo)}", tip, parent


def _wheel_bytes(name: str, version: str) -> bytes:
    import base64
    import io
    import zipfile

    dist = f"{name}-{version}.dist-info"
    files = {
        f"{name}/__init__.py": b"",
        f"{dist}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode(),
        f"{dist}/WHEEL": b"Wheel-Version: 1.0\nGenerator: sdlab-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = [
        f"{k},sha256={base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b'=').decode()},{len(v)}"
        for k, v in files.items()
    ]
    files[f"{dist}/RECORD"] = ("\n".join(record + [f"{dist}/RECORD,,"]) + "\n").encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for k, v in files.items():
            zf.writestr(zipfile.ZipInfo(k, date_time=(2026, 1, 1, 0, 0, 0)), v)
    return buf.getvalue()


def make_fixture_wheels(wheels_dir: Path, manifest_path: Path, git_repo: str, git_commit: str) -> Path:
    """Write two small valid wheels and a lane3-local-wheels.json that lists them."""
    wheels_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for pkg, name, version in (("fixture-a", "fixture_a", "1.0"), ("fixture-b", "fixture_b", "2.0")):
        fname = f"{name}-{version}-py3-none-any.whl"
        data = _wheel_bytes(name, version)
        (wheels_dir / fname).write_bytes(data)
        entry = {"package": pkg, "version": version, "filename": fname, "sha256": hashlib.sha256(data).hexdigest()}
        if pkg == "fixture-b":
            entry.update({"git_repo": git_repo, "git_commit": git_commit})
        entries.append(entry)
    manifest = {"schema_version": "1.0", "lane": "lane3", "python_version": "3.12.15", "wheels": entries}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest_path


def make_fake_colab_env(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """Create the executable `colab` marker shim (`#SDLAB_FAKE_COLAB_CLI=1`) and fixture pins."""
    bin_dir = tmp_path / "fake_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / "colab_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    wheels_dir = tmp_path / "fake_wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    pin_repo, pin_tip, pin_parent = make_fixture_git_repo(tmp_path / "pin_repo")
    manifest_p = make_fixture_wheels(wheels_dir, tmp_path / "lane3-local-wheels.json", pin_repo, pin_parent)

    fake_colab = bin_dir / "colab"
    fake_colab.write_text("#!/usr/bin/env bash\n#SDLAB_FAKE_COLAB_CLI=1\nexit 0\n", encoding="utf-8", newline="\n")
    fake_colab.chmod(fake_colab.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.pop("CUDA_VISIBLE_DEVICES", None)
    git_bash_bin = Path("C:/Program Files/Git/bin")
    git_usr_bin = Path("C:/Program Files/Git/usr/bin")
    extra_bins = [_to_posix(bin_dir), str(bin_dir)]
    if git_bash_bin.is_dir():
        extra_bins.extend([_to_posix(git_bash_bin), str(git_bash_bin)])
    if git_usr_bin.is_dir():
        extra_bins.extend([_to_posix(git_usr_bin), str(git_usr_bin)])
    env["PATH"] = os.pathsep.join(extra_bins) + os.pathsep + env.get("PATH", "")
    env["SDLAB_TEST_FAKE_COLAB"] = "1"
    env["SDLAB_WHEEL_DIR"] = _to_posix(wheels_dir)
    env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"] = _to_posix(manifest_p)
    env["SDLAB_PREFLIGHT_FAST_COMPILE_MOCK"] = "1"
    env["SDLAB_PREFLIGHT_PIN_REPO"] = pin_repo
    env["SDLAB_PREFLIGHT_PIN_SHA"] = pin_tip
    env["FAKE_FIXTURE_PIN_PARENT"] = pin_parent
    return bin_dir, state_dir, env
