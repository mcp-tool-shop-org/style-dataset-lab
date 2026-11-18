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


# --- the exclude-newer bound -------------------------------------------------------------------
# transformers 5.22.2 reached PyPI at 15:42:54Z on 2026-11-06, after lane1.lock pinned 5.22.1, and
# every unbounded re-resolve drifted. The fake index below models exactly that upload.

LOCKS_DIR = REPO_ROOT / "scripts" / "colab" / "locks"
RELOCK = REPO_ROOT / "scripts" / "colab" / "relock.sh"
NEWER_UPLOAD = "2026-11-06T15:42:54Z"


def _fake_uv_upstream(tmp_path: Path) -> str:
    """A stand-in uv over an index where transformers 5.22.2 was uploaded at FAKE_UV_NEWER_UPLOAD.

    It records its argv and its uv exclude-newer environment, then writes the committed lane 1
    lock's body under a header carrying its own --custom-compile-command, as uv does. Without
    --exclude-newer, or with a bound at or after the upload, the new release is visible and the
    output pins transformers 5.22.2.
    """
    p = tmp_path / "fake_uv_upstream"
    p.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "--version" ]; then echo "uv 0.13.5 (fake)"; exit 0; fi\n'
        'printf "ARGV %s\\n" "$*" >> "$FAKE_UV_ARGV_LOG"\n'
        'printf "ENV UV_EXCLUDE_NEWER=%s UV_EXCLUDE_NEWER_PACKAGE=%s\\n" '
        '"${UV_EXCLUDE_NEWER:-}" "${UV_EXCLUDE_NEWER_PACKAGE:-}" >> "$FAKE_UV_ARGV_LOG"\n'
        'out=""; bound=""; cmd=""; prev=""\n'
        'for a in "$@"; do\n'
        '  case "$prev" in -o) out="$a" ;; --exclude-newer) bound="$a" ;; --custom-compile-command) cmd="$a" ;; esac\n'
        '  prev="$a"\n'
        "done\n"
        '{ echo "# This file was autogenerated by uv via the following command:"; echo "#    $cmd";'
        ' tail -n +3 "$FAKE_UV_COPY_FROM"; } > "$out.tmp"\n'
        'if [ -z "$bound" ] || [[ ! "$bound" < "$FAKE_UV_NEWER_UPLOAD" ]]; then\n'
        '  sed -i "s/^transformers==5.22.1 /transformers==5.22.2 /" "$out.tmp"\n'
        "fi\n"
        'mv "$out.tmp" "$out"\n',
        encoding="utf-8",
        newline="\n",
    )
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return fc._to_posix(p)


def _upstream_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    env.pop("SDLAB_PREFLIGHT_FAST_COMPILE_MOCK")
    argv_log = tmp_path / "fake_uv_argv.log"
    env["FAKE_UV_ARGV_LOG"] = fc._to_posix(argv_log)
    env["FAKE_UV_COPY_FROM"] = fc._to_posix(LOCKS_DIR / "lane1.lock")
    env["FAKE_UV_NEWER_UPLOAD"] = NEWER_UPLOAD
    env["UV_BIN"] = _fake_uv_upstream(tmp_path)
    return env, argv_log


def _ts_file(tmp_path: Path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return fc._to_posix(p)


def test_committed_timestamp_files_are_well_formed() -> None:
    for lane in ("lane1", "lane3"):
        lines = [
            ln
            for ln in (LOCKS_DIR / f"{lane}.exclude-newer").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        assert lines == ["2026-11-06T15:00:00Z"], lane
        # The bound sits before the release that drifted lane 1.
        assert lines[0] < NEWER_UPLOAD


def test_bound_hides_a_newer_upstream_release(tmp_path: Path) -> None:
    env, argv_log = _upstream_env(tmp_path)
    # Ambient uv settings must not widen or narrow the committed bound.
    env["UV_EXCLUDE_NEWER"] = "2030-01-01T00:00:00Z"
    env["UV_EXCLUDE_NEWER_PACKAGE"] = "transformers=2030-01-01T00:00:00Z"
    res = _run(env, "lane1")
    assert res.returncode == 0, res.stderr
    assert "PREFLIGHT_OK lane=lane1 python=3.14.9 pins=109 exclude_newer=2026-11-06T15:00:00Z" in res.stdout
    log = argv_log.read_text(encoding="utf-8")
    assert "--exclude-newer 2026-11-06T15:00:00Z" in log
    assert "ENV UV_EXCLUDE_NEWER= UV_EXCLUDE_NEWER_PACKAGE=\n" in log
    # The compile's header records the bounded command, unlike the committed lock's: headers never drift.
    assert "--custom-compile-command uv pip compile" in log

    # A bound after the upload sees 5.22.2: that is drift, as an unbounded resolve was.
    env["SDLAB_PREFLIGHT_EXCLUDE_NEWER_FILE"] = _ts_file(tmp_path, "late.exclude-newer", "2026-11-06T16:00:00Z\n")
    late = _run(env, "lane1")
    assert late.returncode == 1
    assert "REFUSED: LOCK_DRIFT: compiled output for lane1 differs" in late.stderr
    assert "+transformers==5.22.2" in late.stderr


def test_body_drift_is_still_caught_under_the_bound(tmp_path: Path) -> None:
    env, _ = _upstream_env(tmp_path)
    edited = tmp_path / "edited.lock"
    edited.write_bytes(
        (LOCKS_DIR / "lane1.lock").read_bytes().replace(b"transformers==5.22.1 ", b"transformers==5.22.0 ")
    )
    env["SDLAB_PREFLIGHT_LOCK_FILE"] = fc._to_posix(edited)
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "LOCK_DRIFT" in res.stderr


def test_missing_or_malformed_timestamp_refuses_before_any_compile(tmp_path: Path) -> None:
    env, argv_log = _upstream_env(tmp_path)
    env["SDLAB_PREFLIGHT_EXCLUDE_NEWER_FILE"] = fc._to_posix(tmp_path / "absent.exclude-newer")
    res = _run(env, "lane1")
    assert res.returncode == 1
    assert "REFUSED: LOCK_TIMESTAMP_MISSING:" in res.stderr

    malformed = {
        "empty": "",
        "comments-only": "# nothing here\n\n",
        "two-lines": "2026-11-06T15:00:00Z\n2026-11-05T15:00:00Z\n",
        "date-only": "2026-11-06\n",
        "space-separated": "2026-11-06 15:00:00Z\n",
        "offset": "2026-11-06T15:00:00+00:00\n",
        "fractional": "2026-11-06T15:00:00.5Z\n",
        "not-a-date": "2026-13-40T15:00:00Z\n",
        "words": "yesterday\n",
        "future": "2999-01-01T00:00:00Z\n",
    }
    for name, text in malformed.items():
        env["SDLAB_PREFLIGHT_EXCLUDE_NEWER_FILE"] = _ts_file(tmp_path, f"{name}.exclude-newer", text)
        res = _run(env, "lane1")
        assert res.returncode == 1, name
        assert "REFUSED: LOCK_TIMESTAMP_MALFORMED:" in res.stderr, (name, res.stderr)
    assert not argv_log.exists(), "the compile ran despite a bad timestamp file"

    # CRLF and the comment header are accepted.
    env["SDLAB_PREFLIGHT_EXCLUDE_NEWER_FILE"] = _ts_file(
        tmp_path, "crlf.exclude-newer", "# bound\r\n2026-11-06T15:00:00Z\r\n"
    )
    ok = _run(env, "lane1")
    assert ok.returncode == 0, ok.stderr

    # The check also runs when the compile is mocked, so every lane-3 path needs the file.
    _, _, env3 = fc.make_fake_colab_env(tmp_path / "lane3")
    env3["SDLAB_PREFLIGHT_EXCLUDE_NEWER_FILE"] = fc._to_posix(tmp_path / "absent.exclude-newer")
    res3 = _run(env3, "lane3")
    assert res3.returncode == 1
    assert "REFUSED: LOCK_TIMESTAMP_MISSING:" in res3.stderr


def _run_relock(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_bash(), fc._to_posix(RELOCK), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_relock_writes_lock_and_timestamp_together(tmp_path: Path) -> None:
    env, _ = _upstream_env(tmp_path)
    out = tmp_path / "locks_out"
    out.mkdir()
    res = _run_relock(env, "lane1", "--exclude-newer", "2026-11-06T15:00:00Z", "--locks-dir", fc._to_posix(out))
    assert res.returncode == 0, res.stderr
    assert "RELOCK_OK lane=lane1 exclude_newer=2026-11-06T15:00:00Z pins=109" in res.stdout
    lock_text = (out / "lane1.lock").read_text(encoding="utf-8")
    assert "--exclude-newer 2026-11-06T15:00:00Z scripts/colab/locks/lane1.in" in lock_text.splitlines()[1]
    assert "transformers==5.22.1 " in lock_text
    assert (out / "lane1.exclude-newer").read_text(encoding="utf-8").splitlines()[-1] == "2026-11-06T15:00:00Z"
    assert sorted(p.name for p in out.iterdir()) == ["lane1.exclude-newer", "lane1.lock"]

    # The pre-flight accepts what relock wrote.
    env["SDLAB_PREFLIGHT_LOCK_FILE"] = fc._to_posix(out / "lane1.lock")
    env["SDLAB_PREFLIGHT_EXCLUDE_NEWER_FILE"] = fc._to_posix(out / "lane1.exclude-newer")
    pre = _run(env, "lane1")
    assert pre.returncode == 0, pre.stderr

    # `now` takes the current UTC second, which is after the fake upload.
    now = _run_relock(env, "lane1", "--exclude-newer", "now", "--locks-dir", fc._to_posix(out))
    assert now.returncode == 0, now.stderr
    assert "transformers==5.22.2 " in (out / "lane1.lock").read_text(encoding="utf-8")


def test_relock_refusals_leave_files_untouched(tmp_path: Path) -> None:
    env, _ = _upstream_env(tmp_path)
    out = tmp_path / "locks_out"
    out.mkdir()
    (out / "lane1.lock").write_bytes(b"old lock\n")
    (out / "lane1.exclude-newer").write_bytes(b"2026-11-01T00:00:00Z\n")
    d = fc._to_posix(out)

    cases = [
        (("lane1", "--locks-dir", d), "LOCK_TIMESTAMP_MISSING"),
        (("lane1", "--exclude-newer", "2026-11-06", "--locks-dir", d), "LOCK_TIMESTAMP_MALFORMED"),
        (("lane1", "--exclude-newer", "2999-01-01T00:00:00Z", "--locks-dir", d), "LOCK_TIMESTAMP_MALFORMED"),
    ]
    for args, code in cases:
        res = _run_relock(env, *args)
        assert res.returncode == 1, args
        assert f"REFUSED: {code}:" in res.stderr, (args, res.stderr)

    env["UV_BIN"] = _fake_uv(tmp_path, "0.11.18", "copy")
    res = _run_relock(env, "lane1", "--exclude-newer", "2026-11-06T15:00:00Z", "--locks-dir", d)
    assert res.returncode == 1 and "UV_VERSION_MISMATCH" in res.stderr

    env["UV_BIN"] = _fake_uv(tmp_path, "0.13.5", "fail")
    res = _run_relock(env, "lane1", "--exclude-newer", "2026-11-06T15:00:00Z", "--locks-dir", d)
    assert res.returncode == 1 and "LOCK_COMPILE_FAILED" in res.stderr

    env["UV_BIN"] = fc._to_posix(tmp_path / "no_uv_here")
    res = _run_relock(env, "lane1", "--exclude-newer", "2026-11-06T15:00:00Z", "--locks-dir", d)
    assert res.returncode == 1 and "PREFLIGHT_TOOL_MISSING" in res.stderr

    env["UV_BIN"] = _fake_uv_upstream(tmp_path)
    res = _run_relock(env, "lane1", "--exclude-newer", "now", "--locks-dir", fc._to_posix(tmp_path / "nope"))
    assert res.returncode == 1 and "LOCK_INPUT_MISSING" in res.stderr

    assert (out / "lane1.lock").read_bytes() == b"old lock\n"
    assert (out / "lane1.exclude-newer").read_bytes() == b"2026-11-01T00:00:00Z\n"
    assert sorted(p.name for p in out.iterdir()) == ["lane1.exclude-newer", "lane1.lock"]

    assert _run_relock(env).returncode == 2
    assert _run_relock(env, "lane9", "--exclude-newer", "now").returncode == 2
    assert _run_relock(env, "lane1", "--bogus").returncode == 2
    assert _run_relock(env, "lane1", "--exclude-newer").returncode == 2
