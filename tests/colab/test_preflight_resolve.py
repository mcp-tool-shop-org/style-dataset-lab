"""Tests for scripts/colab/preflight_resolve.sh: pin checks by sha, test-hook gating, honest failure codes.

Nothing here reaches the network: upstream pins are stood in for by a local two-commit git repo,
and the compile by a fake `uv` script passed as UV_BIN.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPO_ROOT / "scripts" / "colab" / "preflight_resolve.sh"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))

import fake_colab as fc  # noqa: E402

MISSING_SHA = "73ebae1334d2c98089f1b90f8cb19257825f891a"


def _bash() -> str:
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_bash(), fc._to_posix(PREFLIGHT), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _fake_uv(tmp_path: Path, version: str, mode: str) -> str:
    """A stand-in uv: `--version` prints `version`; `pip compile` copies the lock, drifts or fails."""
    p = tmp_path / f"fake_uv_{mode}"
    p.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "$1" = "--version" ]; then echo "uv {version} (fake)"; exit 0; fi\n'
        'out=""; prev=""; for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done\n'
        f'mode="{mode}"\n'
        'case "$mode" in\n'
        '  fail) echo "error: No solution found when resolving dependencies" >&2; exit 1 ;;\n'
        '  drift) echo "# drifted" > "$out" ;;\n'
        '  copy) cp "$FAKE_UV_COPY_FROM" "$out" ;;\n'
        "esac\n",
        encoding="utf-8",
        newline="\n",
    )
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return fc._to_posix(p)


def test_non_tip_commit_passes_and_missing_commit_is_pin_not_found(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    env["SDLAB_PREFLIGHT_PIN_SHA"] = env["FAKE_FIXTURE_PIN_PARENT"]
    ok = _run(env, "lane1")
    assert ok.returncode == 0, ok.stderr
    assert f"PIN_OK ComfyUI {env['FAKE_FIXTURE_PIN_PARENT']}" in ok.stdout
    assert "PREFLIGHT_OK lane=lane1 python=3.14.9" in ok.stdout

    env["SDLAB_PREFLIGHT_PIN_SHA"] = MISSING_SHA
    miss = _run(env, "lane1")
    assert miss.returncode == 1
    assert f"PIN_NOT_FOUND: ComfyUI commit {MISSING_SHA} not found" in miss.stderr

    env["SDLAB_PREFLIGHT_PIN_SHA"] = "not-a-sha"
    bad = _run(env, "lane1")
    assert bad.returncode == 1
    assert "PIN_NOT_FOUND: invalid sha 'not-a-sha'" in bad.stderr


def test_unreachable_repo_is_pin_check_unavailable(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    env["SDLAB_PREFLIGHT_PIN_REPO"] = fc._to_posix(tmp_path / "no_such_repo")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "PIN_CHECK_UNAVAILABLE: cannot reach" in res.stderr
    assert "PIN_NOT_FOUND" not in res.stderr


def test_lane3_checks_manifest_git_commit_and_local_wheels(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    ok = _run(env, "lane3")
    assert ok.returncode == 0, ok.stderr
    # The manifest's git pin is the fixture repo's parent commit, a non-tip commit
    assert f"PIN_OK fixture-b {env['FAKE_FIXTURE_PIN_PARENT']}" in ok.stdout
    assert "PREFLIGHT_OK lane=lane3 python=3.12.15" in ok.stdout

    manifest_p = Path(env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"])
    data = json.loads(manifest_p.read_text(encoding="utf-8"))
    data["wheels"][1]["git_commit"] = MISSING_SHA
    bad_manifest = tmp_path / "bad-manifest.json"
    bad_manifest.write_text(json.dumps(data), encoding="utf-8")
    env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"] = fc._to_posix(bad_manifest)
    miss = _run(env, "lane3", "--skip-local-wheels")
    assert miss.returncode == 1
    assert f"PIN_NOT_FOUND: fixture-b commit {MISSING_SHA} not found" in miss.stderr

    # No wheel directory: a named refusal, never a default
    env.pop("SDLAB_WHEEL_DIR")
    nodir = _run(env, "lane3")
    assert nodir.returncode == 1
    assert "WHEEL_DIR_REQUIRED" in nodir.stderr

    empty = tmp_path / "empty_wheels"
    empty.mkdir()
    env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"] = fc._to_posix(manifest_p)
    gone = _run(env, "lane3", "--wheel-dir", fc._to_posix(empty))
    assert gone.returncode == 1
    assert "LOCAL_WHEEL_MISSING: fixture_a-1.0-py3-none-any.whl not found" in gone.stderr


def test_test_hooks_refused_in_a_live_run(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    # Hooks set but no fake-colab flag
    env.pop("SDLAB_TEST_FAKE_COLAB")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "PREFLIGHT_TEST_HOOK_IN_LIVE_RUN" in res.stderr
    for name in ("SDLAB_PREFLIGHT_FAST_COMPILE_MOCK", "SDLAB_PREFLIGHT_PIN_REPO", "SDLAB_PREFLIGHT_PIN_SHA"):
        assert name in res.stderr

    # Flag set, but `colab` on PATH is not the fake CLI
    _, _, env2 = fc.make_fake_colab_env(tmp_path / "notfake")
    other_bin = tmp_path / "other_bin"
    other_bin.mkdir()
    impostor = other_bin / "colab"
    impostor.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n")
    impostor.chmod(impostor.stat().st_mode | stat.S_IEXEC)
    env2["PATH"] = fc._to_posix(other_bin) + ":" + env2["PATH"]
    res2 = _run(env2, "lane1")
    assert res2.returncode == 1
    assert "PREFLIGHT_TEST_HOOK_IN_LIVE_RUN" in res2.stderr


def test_uv_version_compile_failure_drift_and_ok(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    env.pop("SDLAB_PREFLIGHT_FAST_COMPILE_MOCK")
    env["FAKE_UV_COPY_FROM"] = fc._to_posix(REPO_ROOT / "scripts" / "colab" / "locks" / "lane1.lock")

    env["UV_BIN"] = _fake_uv(tmp_path, "0.11.18", "copy")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "UV_VERSION_MISMATCH" in res.stderr and "0.13.5" in res.stderr

    env["UV_BIN"] = _fake_uv(tmp_path, "0.13.5", "fail")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "LOCK_COMPILE_FAILED" in res.stderr
    assert "No solution found" in res.stderr
    assert "LOCK_DRIFT" not in res.stderr

    env["UV_BIN"] = _fake_uv(tmp_path, "0.13.5", "drift")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "LOCK_DRIFT: compiled output for lane1 differs" in res.stderr

    env["UV_BIN"] = _fake_uv(tmp_path, "0.13.5", "copy")
    res = _run(env, "lane1")
    assert res.returncode == 0, res.stderr
    assert "PREFLIGHT_OK lane=lane1 python=3.14.9 pins=" in res.stdout

    env["UV_BIN"] = fc._to_posix(tmp_path / "no_uv_here")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "PREFLIGHT_TOOL_MISSING: uv not found" in res.stderr


def test_missing_lock_input_and_usage(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    env["SDLAB_PREFLIGHT_IN_FILE"] = fc._to_posix(tmp_path / "absent.in")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "LOCK_INPUT_MISSING" in res.stderr

    assert _run(env).returncode == 2
    assert _run(env, "lane9").returncode == 2
    assert _run(env, "lane1", "--bogus").returncode == 2
