"""Remote directories, upload/download refusals, refusal-code parsing, volatile out dirs, live pin
overrides and interpreter identity: the defects two real Colab CPU stub windows exposed."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
WINDOW_SH = COLAB_DIR / "colab_window.sh"
LANE1 = COLAB_DIR / "launch_lane1_stub.sh"
LANE3 = COLAB_DIR / "launch_lane3_stub.sh"
FIXTURES = REPO_ROOT / "tests" / "colab" / "fixtures"
sys.path.insert(0, str(FIXTURES))

import fake_colab as fc  # noqa: E402

# The real shape of the `ps` row that made window sdlab-l1-stub-5 report VENV_IMPORT_OUTSIDE_VENV
# on a good run: the import gate's own `python -c` source, refusal codes included.
PS_GATE_ROW = (
    "root        2216    2101 21 19:01 ?        00:00:02 /content/venv-lane1/bin/python -c  "
    "import importlib import sys  REQUIRED = (\"comfy_headless\", \"torch\") for mod_name in REQUIRED: "
    "    try:         mod = importlib.import_module(mod_name)     except Exception as exc: "
    "        sys.stderr.write(f\"REFUSED: VENV_IMPORT_FAILED {mod_name}: {exc}\")         raise SystemExit(1) "
    "    if not mod_file.startswith(\"/content/venv-lane1/\"): "
    "        sys.stderr.write(f\"REFUSED: VENV_IMPORT_OUTSIDE_VENV {mod_name}: {mod_file}\")"
)


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found
    return found


def _p(p: Path) -> str:
    return fc._to_posix(p)


def _run(cmd: list[str], env: dict[str, str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, check=False
    )


def _window_fn(env: dict[str, str], body: str) -> subprocess.CompletedProcess[str]:
    """Source colab_window.sh and run `body` in the same shell."""
    return _run([_bash(), "-c", f'source "{_p(WINDOW_SH)}"\n{body}'], env)


def _fake(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(FIXTURES / "fake_colab.py"), *args], env)


# --- items 1 and 2: the fake enforces the contents-API contract -----------------------------------


def test_fake_upload_into_missing_remote_dir_fails_500_and_never_creates_it(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    src = tmp_path / "x.whl"
    src.write_bytes(b"wheel")
    bad = _fake(env, "upload", "-s", "s1", str(src), "/content/wheels/x.whl")
    assert bad.returncode == 1
    assert "[colab] Upload failed: 500 Server Error" in bad.stdout
    assert not (state / "content" / "wheels").exists(), "an upload must never create a remote directory"
    assert "UPLOAD_FAILED_500" in (state / "uploads.log").read_text(encoding="utf-8")

    ok = _fake(env, "upload", "-s", "s1", str(src), "/content/x.whl")
    assert ok.returncode == 0
    assert f"[colab] Uploaded '{src}' to '/content/x.whl'" in ok.stdout

    missing = _fake(env, "upload", "-s", "s1", str(tmp_path / "nope.whl"), "/content/nope.whl")
    assert missing.returncode == 1 and "Local file" in missing.stdout and "not found" in missing.stdout


def test_fake_download_needs_remote_file_and_local_dir(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    gone = _fake(env, "download", "-s", "s1", "/content/none.tar.gz", str(tmp_path / "none.tar.gz"))
    assert gone.returncode == 1
    assert "[colab] Download failed: File or directory not found: /content/none.tar.gz" in gone.stdout
    assert not (tmp_path / "none.tar.gz").exists()

    (state / "content" / "b.tar.gz").write_bytes(b"bundle")
    no_dir = _fake(env, "download", "-s", "s1", "/content/b.tar.gz", str(tmp_path / "missing_dir" / "b.tar.gz"))
    assert no_dir.returncode == 1 and "No such file or directory" in no_dir.stdout
    assert not (tmp_path / "missing_dir").exists(), "a download must never create a local directory"

    ok = _fake(env, "download", "-s", "s1", "/content/b.tar.gz", str(tmp_path / "b.tar.gz"))
    assert ok.returncode == 0 and "[colab] Downloaded '/content/b.tar.gz'" in ok.stdout
    assert (tmp_path / "b.tar.gz").read_bytes() == b"bundle"


def test_contract_refuses_a_contents_api_block_that_creates_directories(tmp_path: Path) -> None:
    contract = json.loads((FIXTURES / "colab-cli-contract.json").read_text(encoding="utf-8"))
    assert contract["contents_api"]["upload_creates_parent_dirs"] is False
    for key, val, msg in (
        ("upload_creates_parent_dirs", True, "upload_creates_parent_dirs"),
        ("download_creates_local_parent_dirs", True, "download_creates_local_parent_dirs"),
        ("upload_missing_parent_http_status", 404, "500"),
    ):
        bad = json.loads(json.dumps(contract))
        bad["contents_api"][key] = val
        p = tmp_path / f"contract_{key}.json"
        p.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match=msg):
            fc.load_and_verify_contract(contract_path=p)
    missing = json.loads(json.dumps(contract))
    del missing["contents_api"]["upload_ok_line"]
    p = tmp_path / "contract_missing.json"
    p.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(ValueError, match="upload_ok_line"):
        fc.load_and_verify_contract(contract_path=p)
    del missing["contents_api"]
    p.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(ValueError, match="contents_api block missing"):
        fc.load_and_verify_contract(contract_path=p)


def test_old_lane3_upload_sequence_fails_against_the_fake(tmp_path: Path) -> None:
    """The pre-fix lane 3 kit's upload calls, replayed in order: the first wheel upload into
    /content/wheels/ fails with HTTP 500 exactly as in window sdlab-l3-stub-3."""
    _, _, env = fc.make_fake_colab_env(tmp_path)
    manifest = json.loads(Path(env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"]).read_text(encoding="utf-8"))
    wheel = manifest["wheels"][0]["filename"]
    seq = [
        (str(COLAB_DIR / "locks" / "lane3.lock"), "/content/lane3.lock", 0),
        (env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"], "/content/lane3-local-wheels.json", 0),
        (str(Path(env["SDLAB_WHEEL_DIR"]) / wheel), f"/content/wheels/{wheel}", 1),
    ]
    res = None
    for src, dst, want_rc in seq:
        res = _fake(env, "upload", "-s", "sdlab-l3-old", src, dst)
        assert res.returncode == want_rc, (dst, res.stdout, res.stderr)
    assert res is not None and "500 Server Error" in res.stdout


# --- items 1 and 3: kits upload flat into /content; the remote script makes its directories ------


def test_lane3_uploads_flat_and_the_kits_own_block_moves_wheels_into_place(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / "out_flat"
    res = _run([_bash(), _p(LANE3), "--out-dir", _p(out_dir), "--session", "sdlab-l3-flat"], env)
    assert res.returncode == 0, res.stdout + res.stderr

    uploads = (state / "uploads.log").read_text(encoding="utf-8")
    assert "/content/wheels/" not in uploads
    for line in uploads.splitlines():
        remote = line.split()[-1]
        assert remote.count("/") == 2 and remote.startswith("/content/"), line
    manifest = json.loads(Path(env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"]).read_text(encoding="utf-8"))
    content = state / "content"
    for w in manifest["wheels"]:
        assert (content / "wheels" / w["filename"]).is_file(), "the kit's block must move each wheel into /content/wheels"
        assert not (content / w["filename"]).exists()
    assert (content / "lane3_out" / "checkpoints").is_dir()

    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok" and win["refusal_code"] is None
    assert win["python_identity"]["build"] == "20261021"
    assert win["python_identity"]["pinned_build"] == "20261021"
    assert win["python_identity"]["binary_sha256"].startswith("sha256:")
    assert "cpython-3.12.15" in win["python_identity"]["download_url"]

    # The generated remote script's block, run against a scratch /content, refuses by name.
    remote_sh = (out_dir / "remote_lane3_stub.sh").read_text(encoding="utf-8")
    block = re.search(r"^# >>> sdlab-remote-dirs$.*?^# <<< sdlab-remote-dirs$", remote_sh, re.S | re.M)
    assert block
    assert "PINNED_PYTHON_BUILD" in remote_sh and "PYTHON_IDENTITY " in remote_sh

    def run_block(root: Path) -> subprocess.CompletedProcess[str]:
        script = root / "block.sh"
        script.write_text(block.group(0).replace("/content", _p(root)), encoding="utf-8", newline="\n")
        return _run([_bash(), _p(script)], env)

    blocked = tmp_path / "vm_blocked"
    blocked.mkdir()
    (blocked / "lane3-local-wheels.json").write_text(json.dumps(manifest), encoding="utf-8")
    (blocked / "wheels").write_text("a file where the directory should be", encoding="utf-8")
    r1 = run_block(blocked)
    assert r1.returncode == 1 and "REFUSED: REMOTE_DIR_CREATE_FAILED:" in r1.stderr

    not_uploaded = tmp_path / "vm_missing"
    not_uploaded.mkdir()
    (not_uploaded / "lane3-local-wheels.json").write_text(json.dumps(manifest), encoding="utf-8")
    r2 = run_block(not_uploaded)
    assert r2.returncode == 1 and "REFUSED: LOCAL_WHEEL_MISSING on VM:" in r2.stderr


def test_lane1_remote_script_makes_its_own_out_dir(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / "out_l1"
    res = _run([_bash(), _p(LANE1), "--out-dir", _p(out_dir), "--session", "sdlab-l1-dirs"], env)
    assert res.returncode == 0, res.stdout + res.stderr
    uploads = (state / "uploads.log").read_text(encoding="utf-8")
    assert all(line.split()[-1].count("/") == 2 for line in uploads.splitlines())
    remote_sh = (out_dir / "remote_lane1_stub.sh").read_text(encoding="utf-8")
    assert "sdlab_remote_mkdir /content/lane1_out" in remote_sh
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["python_identity"]["key"] == "cpython-3.14.9-linux-x86_64-gnu"


def test_upload_failure_is_upload_failed_with_http_status_and_no_token(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["FAKE_COLAB_UPLOAD_HTTP_500_FOR"] = "classify_install_log.py"
    out_dir = tmp_path / "out_upfail"
    res = _run([_bash(), _p(LANE3), "--out-dir", _p(out_dir), "--session", "sdlab-l3-upfail"], env)
    assert res.returncode != 0
    assert "REFUSED: UPLOAD_FAILED:" in res.stderr and "http=500" in res.stderr
    assert fc.FAKE_CONTENTS_TOKEN not in res.stderr
    calls = (state / "calls.log").read_text(encoding="utf-8")
    assert "CALL exec" not in calls
    assert "STOP -s sdlab-l3-upfail" in (state / "stops.log").read_text(encoding="utf-8")
    for f in out_dir.rglob("*"):
        if f.is_file() and f.suffix in (".log", ".json", ".txt"):
            assert fc.FAKE_CONTENTS_TOKEN not in f.read_text(encoding="utf-8", errors="replace"), f
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "UPLOAD_FAILED" and win["refusal_code"] == "UPLOAD_FAILED"


def test_upload_and_download_helpers_refuse_by_name(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out_helpers"
    out_dir.mkdir()
    src = tmp_path / "f.txt"
    src.write_text("x", encoding="utf-8")
    o = _p(out_dir)

    nested = _window_fn(env, f'colab_upload_checked s1 "{_p(src)}" /content/wheels/f.txt "{o}"')
    assert nested.returncode == 1 and "REFUSED: REMOTE_PARENT_UNVERIFIED: /content/wheels/f.txt" in nested.stderr
    no_name = _window_fn(env, f'colab_upload_checked s1 "{_p(src)}" /content/ "{o}"')
    assert no_name.returncode == 1 and "REMOTE_PARENT_UNVERIFIED" in no_name.stderr
    no_src = _window_fn(env, f'colab_upload_checked s1 "{_p(tmp_path / "nope")}" /content/nope "{o}"')
    assert no_src.returncode == 1 and "UPLOAD_FAILED" in no_src.stderr and "local file missing" in no_src.stderr
    assert not (state / "calls.log").exists(), "no refused upload may reach the CLI"

    ok = _window_fn(env, f'colab_upload_checked s1 "{_p(src)}" /content/f.txt "{o}"')
    assert ok.returncode == 0, ok.stderr

    gone = _window_fn(env, f'colab_download_checked s1 /content/none.tar.gz "{o}/none.tar.gz" "{o}"')
    assert gone.returncode == 1 and "REFUSED: DOWNLOAD_FAILED:" in gone.stderr and "http=404" in gone.stderr
    calls_before = (state / "calls.log").read_text(encoding="utf-8")
    no_dir = _window_fn(env, f'colab_download_checked s1 /content/f.txt "{o}/missing/f.txt" "{o}"')
    assert no_dir.returncode == 1 and "does not exist" in no_dir.stderr
    assert (state / "calls.log").read_text(encoding="utf-8") == calls_before
    got = _window_fn(env, f'colab_download_checked s1 /content/f.txt "{o}/f.txt" "{o}"')
    assert got.returncode == 0 and (out_dir / "f.txt").read_text(encoding="utf-8") == "x"
    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert guards.count("REFUSED: ") == 5

    status = _window_fn(env, '_colab_http_status "[colab] Upload failed: 413 Client Error: x"; echo; _colab_http_status "other"')
    assert status.stdout.split() == ["413", "none"]


# --- item 4: refusal codes come only from real REFUSED lines --------------------------------------


def _write_window(env: dict[str, str], out_dir: Path, exit_code: int) -> dict:
    res = _window_fn(
        env,
        f'colab_write_window_and_outcome "{_p(Path(sys.executable))}" "{_p(out_dir)}" render s1 CPU-high-mem '
        f"0.05 900 60 0.01 2026-11-05T00:00:00Z 2026-11-05T00:01:00Z {exit_code} '{{}}'",
    )
    assert res.returncode == 0, res.stderr
    return json.loads((out_dir / "window.json").read_text(encoding="utf-8"))


def _vitals_block(phase: str, proc_rows: list[str]) -> str:
    return "\n".join(
        ["=== VITALS 2026-11-05T19:01:00Z ===", "SETUP_BYTES: 10", "PROC:", *proc_rows, f'HARNESS: {{"phase": "{phase}"}}']
    )


def test_ps_row_with_refusal_codes_is_not_a_refusal(tmp_path: Path) -> None:
    env = os.environ.copy()
    out_dir = tmp_path / "w_ok"
    out_dir.mkdir()
    (out_dir / "vitals.log").write_text(
        _vitals_block("setup", [PS_GATE_ROW]) + "\nVENV_IMPORT torch /content/venv-lane1/x\nSDLAB_REMOTE_RC=0\n",
        encoding="utf-8",
    )
    (out_dir / "guards.log").write_text("preflight ok; checked VENV_IMPORT_OUTSIDE_VENV gate\n", encoding="utf-8")
    (out_dir / "colab.log").write_text("REFUSED: VENV_IMPORT_FAILED: CLI text never counts\n", encoding="utf-8")
    win = _write_window(env, out_dir, 0)
    assert win["status"] == "ok"
    assert win["refusal_code"] is None


def test_real_refusal_lines_are_found_and_proc_sections_skipped(tmp_path: Path) -> None:
    env = os.environ.copy()
    # A refusal from the remote script in the exec stream, after a vitals block whose PROC rows
    # name a different code (skipped).
    out_a = tmp_path / "w_vitals"
    out_a.mkdir()
    (out_a / "vitals.log").write_text(
        _vitals_block("setup", [PS_GATE_ROW, "REFUSED: VENV_IMPORT_FAILED: inside PROC is skipped"])
        + "\nREFUSED: VENV_IMPORT_OUTSIDE_VENV torch: /usr/local/lib/python3.13/dist-packages/torch/__init__.py\r\n"
        + "SDLAB_REMOTE_RC=1\n",
        encoding="utf-8",
    )
    win_a = _write_window(env, out_a, 1)
    assert win_a["refusal_code"] == "VENV_IMPORT_OUTSIDE_VENV" and win_a["status"] == "VENV_IMPORT_OUTSIDE_VENV"

    # guards.log comes first; unlisted codes and lowercase reasons are not codes.
    out_b = tmp_path / "w_guards"
    out_b.mkdir()
    (out_b / "guards.log").write_text(
        "REFUSED: SOMETHING_UNLISTED: x\nREFUSED: remote runner reported SDLAB_REMOTE_RC=1\n"
        "REFUSED: UPLOAD_FAILED: a -> /content/a rc=1 http=500\n",
        encoding="utf-8",
    )
    (out_b / "vitals.log").write_text("REFUSED: INSTALL_FAILED during lane1 lock install\n", encoding="utf-8")
    assert _write_window(env, out_b, 1)["refusal_code"] == "UPLOAD_FAILED"

    # setup.log inside a downloaded bundle; a failed run with no code is plain "failed".
    out_c = tmp_path / "w_bundle"
    out_c.mkdir()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"uv ok\nREFUSED: PYTHON_BUILD_MISMATCH: cpython-3.14.9 build='x' pinned=20261021\n"
        info = tarfile.TarInfo("./setup.log")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    (out_c / "lane1_stub_bundle.tar.gz").write_bytes(buf.getvalue())
    (out_c / "not_a_tar.tar.gz").write_bytes(b"junk")
    assert _write_window(env, out_c, 1)["refusal_code"] == "PYTHON_BUILD_MISMATCH"

    out_d = tmp_path / "w_none"
    out_d.mkdir()
    win_d = _write_window(env, out_d, 3)
    assert win_d["refusal_code"] is None and win_d["status"] == "failed"


def test_lane1_good_run_with_gate_ps_row_reports_ok(tmp_path: Path) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / "out_psrow"
    res = _run([_bash(), _p(LANE1), "--out-dir", _p(out_dir), "--session", "sdlab-l1-psrow"], env)
    assert res.returncode == 0, res.stdout + res.stderr
    vitals = (out_dir / "vitals.log").read_text(encoding="utf-8")
    assert "VENV_IMPORT_OUTSIDE_VENV {mod_name}" in vitals, "the fake must emit the gate's ps row"
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok" and win["refusal_code"] is None
    assert json.loads((out_dir / "outcome.draft.json").read_text(encoding="utf-8"))["refusal_code"] is None


# --- item 5: volatile out dirs ---------------------------------------------------------------------


def _live_env(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Fake CLI first on PATH (nothing real is reachable) but test mode off: a live run's rules."""
    _, state, env = fc.make_fake_colab_env(tmp_path)
    for k in list(env):
        if k == "SDLAB_TEST_FAKE_COLAB" or k.startswith("SDLAB_PREFLIGHT_") or k.startswith("EXPECTED_"):
            env.pop(k)
    return state, env


@pytest.mark.skipif(sys.platform == "win32", reason="Linux filesystem types")
def test_live_run_refuses_volatile_out_dir_before_any_colab_call(tmp_path: Path) -> None:
    state, env = _live_env(tmp_path)
    for target in ("/tmp/sdlab-volatile-test/out", "/var/tmp/sdlab-volatile-test", "/dev/shm/sdlab-volatile-test"):
        res = _run([_bash(), _p(LANE1), "--out-dir", target, "--session", "sdlab-l1-vol"], env)
        assert res.returncode == 96, res.stderr
        assert "REFUSED: OUT_DIR_VOLATILE:" in res.stderr
        assert not Path(target).exists()
    tmpfs = []
    for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[2] in ("tmpfs", "ramfs") and not parts[1].startswith(("/tmp", "/var/tmp", "/dev/shm")):
            tmpfs.append(parts[1])
    if tmpfs:
        target = f"{tmpfs[0].rstrip('/')}/sdlab-volatile-test/out"
        res = _run([_bash(), _p(LANE3), "--out-dir", target, "--wheel-dir", _p(tmp_path), "--session", "sdlab-l3-vol"], env)
        assert res.returncode == 96, res.stderr
        assert "REFUSED: OUT_DIR_VOLATILE:" in res.stderr and "is on " in res.stderr
    assert not (state / "calls.log").exists()


def test_out_dir_is_required_and_persistent_dirs_pass(tmp_path: Path, persistent_out_root: Path) -> None:
    state, env = _live_env(tmp_path)
    res = _run([_bash(), _p(LANE1), "--session", "sdlab-l1-noout"], env)
    assert res.returncode == 2 and "REFUSED: OUT_DIR_REQUIRED" in res.stderr
    res3 = _run([_bash(), _p(LANE3), "--wheel-dir", _p(tmp_path), "--session", "sdlab-l3-noout"], env)
    assert res3.returncode == 2 and "REFUSED: OUT_DIR_REQUIRED" in res3.stderr
    ok = _window_fn(env, f'colab_refuse_volatile_out_dir "{_p(persistent_out_root / "a" / "b")}" 0 && echo PASS')
    assert ok.returncode == 0 and "PASS" in ok.stdout
    exempt = _window_fn(env, "colab_refuse_volatile_out_dir /tmp/x 1 && echo PASS")
    assert "PASS" in exempt.stdout
    assert not (state / "calls.log").exists()


# --- item 6: pin overrides only in test mode ------------------------------------------------------


@pytest.mark.parametrize(
    ("lane", "var"),
    [("1", "EXPECTED_LANE1_RENDER_SHA"), ("1", "EXPECTED_LAUNCH_LANE1_STUB_SHA"),
     ("3", "EXPECTED_INSTALL_CLASSIFIER_SHA"), ("3", "EXPECTED_LOCAL_WHEELS_MANIFEST_SHA")],
)
def test_pin_override_in_live_run_is_refused(tmp_path: Path, persistent_out_root: Path, lane: str, var: str) -> None:
    state, env = _live_env(tmp_path)
    env[var] = "0" * 64
    out_dir = persistent_out_root / "out_pin"
    cmd = [_bash(), _p(LANE1 if lane == "1" else LANE3), "--out-dir", _p(out_dir), "--session", "sdlab-pin"]
    if lane == "3":
        cmd += ["--wheel-dir", _p(tmp_path)]
    res = _run(cmd, env)
    assert res.returncode == 1
    assert f"REFUSED: PIN_OVERRIDE_IN_LIVE_RUN: {var} set" in res.stderr
    assert "PIN_OVERRIDE_IN_LIVE_RUN" in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert not (state / "calls.log").exists()


def test_pin_overrides_still_work_in_test_mode(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["EXPECTED_INSTALL_CLASSIFIER_SHA"] = "0" * 64
    res = _run([_bash(), _p(LANE1), "--out-dir", _p(tmp_path / "o"), "--session", "sdlab-l1-tpin"], env)
    assert res.returncode != 0 and "INPUT_SHA_MISMATCH" in res.stderr
    assert not (state / "calls.log").exists()


# --- item 7: interpreter identity -----------------------------------------------------------------


def test_python_build_mismatch_refuses_by_name(tmp_path: Path) -> None:
    _, state, env = fc.make_fake_colab_env(tmp_path)
    env["FAKE_COLAB_MODE"] = "python_build_mismatch"
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / "out_pybuild"
    res = _run([_bash(), _p(LANE3), "--out-dir", _p(out_dir), "--session", "sdlab-l3-pybuild"], env)
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "PYTHON_BUILD_MISMATCH"
    assert win["python_identity"]["build"] == "20250101"
    assert "STOP -s sdlab-l3-pybuild" in (state / "stops.log").read_text(encoding="utf-8")


def test_remote_identity_snippet_records_and_gates_the_build(tmp_path: Path) -> None:
    text = LANE1.read_text(encoding="utf-8")
    snippet = re.search(r"<< 'PYIDEOF'\n(.*?)\nPYIDEOF\n", text, re.S)
    assert snippet
    script = tmp_path / "pyid.py"
    script.write_text(snippet.group(1), encoding="utf-8")
    install = tmp_path / "install"
    inst = install / "cpython-3.14.9-linux-x86_64-gnu"
    (inst / "bin").mkdir(parents=True)
    (inst / "bin" / "python3.14").write_bytes(b"interpreter bytes")
    (inst / "BUILD").write_text("20261021", encoding="utf-8")
    out_json = tmp_path / "identity.json"
    env = os.environ.copy()
    ok = _run([sys.executable, str(script), "3.14.9", "20261021", str(install), str(out_json)], env)
    assert ok.returncode == 0, ok.stderr
    rec = json.loads(out_json.read_text(encoding="utf-8"))
    assert rec["build"] == "20261021" and rec["sys_version"] == sys.version
    assert rec["binary_sha256"] == "sha256:" + hashlib.sha256(b"interpreter bytes").hexdigest()
    assert ok.stdout.startswith("PYTHON_IDENTITY ")

    (inst / "BUILD").write_text("20250101", encoding="utf-8")
    bad = _run([sys.executable, str(script), "3.14.9", "20261021", str(install), str(out_json)], env)
    assert bad.returncode == 1 and "REFUSED: PYTHON_BUILD_MISMATCH:" in bad.stderr
    shutil.rmtree(inst)
    gone = _run([sys.executable, str(script), "3.14.9", "20261021", str(install), str(out_json)], env)
    assert gone.returncode == 1 and "build=None" in gone.stderr
