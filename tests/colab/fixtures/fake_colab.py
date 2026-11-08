#!/usr/bin/env python3
"""Contract-checked fake Colab CLI for offline sdlab launcher tests.

Enforces the recorded Colab CLI v0.7.4 contract against `colab_help.txt` and
`colab-cli-contract.json`:
- subcommands and flags checked against saved `colab --help` output at startup;
- refuses with a non-zero exit any subcommand, flag or positional count the real
  help does not allow (`exec` with a positional command fails);
- `usage` prints the real text format (`Current balance: <float> compute units`,
  `Usage rate: <float>/hr`, `Active assignments: <int>`);
- `exec -f` executes the given local `.py` file's source with cwd set to a fake
  `/content` directory, `__file__` undefined, and the `--env` values applied;
- `upload` and `download` follow the contents-API facts in the contract's `contents_api`
  block: an upload never creates a remote directory and one into a missing directory fails
  with HTTP 500 and exit 1; a download of a missing remote file fails (404) and one into a
  missing local directory fails; both print the real CLI's success and failure lines.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent
CONTRACT_PATH = FIXTURES_DIR / "colab-cli-contract.json"
HELP_FIXTURE_PATH = FIXTURES_DIR / "colab_help.txt"

SESSION_ROW_SHAPE = (
    "[<SESSION>] <TOKEN> | <TOKEN>: <TOKEN> | <TOKEN>: <TOKEN> | <TOKEN>: <TOKEN>"
)
EMPTY_SESSIONS_LINE = "[colab] No active sessions found on server."
DEFAULT_SESSION_ROW_TEMPLATE = (
    "[{sid}] m-s-fake-{sid} | hw: {gpu} | status: READY | age: 1m"
)
# A `colab sessions` row as google-colab-cli 0.7.4 prints it (colab_cli/commands/session.py:41-63,
# _format_session_line; the Shape label from shape_display_label, colab_cli/client.py:114-118).
SESSIONS_ROW_TEMPLATE = "[{sid}] m-s-fake-{sid} | Hardware: {hw} | Shape: {shape} | Variant: {variant}"
# Accelerators google-colab-cli 0.7.4 sends no shape for (colab_cli/client.py:90-95): they exist in a
# single high-memory shape, so the fake's server reports High-RAM for them whatever was asked.
SINGLE_SHAPE_ACCELERATORS = frozenset({"L4", "V5E1", "V6E1"})


def _open_sessions_dir(state_dir: Path) -> Path:
    d = state_dir / "open_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_shape_label(card: str | None, high_mem: bool) -> str:
    """The Shape the fake's server reports for a `colab new`.

    FAKE_COLAB_SESSION_SHAPE overrides it (a mismatch fixture); OMIT drops the Shape field.
    """
    forced = os.environ.get("FAKE_COLAB_SESSION_SHAPE")
    if forced:
        return forced
    if card and card.upper() in SINGLE_SHAPE_ACCELERATORS:
        return "High-RAM"
    return "High-RAM" if high_mem else "Standard"

CONTENTS_API_KEYS = (
    "source",
    "remote_root",
    "upload_creates_parent_dirs",
    "upload_missing_parent_http_status",
    "download_creates_local_parent_dirs",
    "upload_ok_line",
    "upload_failed_prefix",
    "upload_local_missing_line",
    "download_ok_line",
    "download_failed_prefix",
    "download_missing_remote_error",
)
# The query string the real CLI's failed-request message carries (contents.py:36): the session's
# proxy token, which the kit must keep out of everything but the scrubbed colab.log.
FAKE_CONTENTS_TOKEN = "secret_proxy_tok_contents_777"

GLOBAL_VALUE_FLAGS: frozenset[str] = frozenset(
    {"--auth", "--client-oauth-config", "-c", "--config"}
)
VALUE_OPTS_BY_CMD: dict[str, frozenset[str]] = {
    "new": frozenset({"-s", "--session", "--gpu", "--tpu"}),
    "exec": frozenset(
        {"-s", "--session", "-f", "--file", "--timeout", "--env", "--output-image"}
    ),
    "upload": frozenset({"-s", "--session"}),
    "download": frozenset({"-s", "--session"}),
    "stop": frozenset({"-s", "--session"}),
    "restart-kernel": frozenset({"-s", "--session"}),
    "sessions": frozenset(),
    "usage": frozenset(),
}
POSITIONAL_COUNTS_BY_CMD: dict[str, int] = {
    "sessions": 0,
    "new": 0,
    "upload": 2,
    "exec": 0,
    "download": 2,
    "stop": 0,
    "restart-kernel": 0,
    "usage": 0,
}


def parse_help_fixture(help_text: str) -> dict[str, set[str]]:
    """Parse subcommand sections and options from saved `colab --help` fixture text."""
    sections: dict[str, str] = {}
    current_name = "top"
    buf: list[str] = []
    for line in help_text.splitlines():
        m = re.match(r"^=== colab(?:\s+([a-z0-9-]+))?\s+--help ===$", line.strip())
        if m:
            sections[current_name] = "\n".join(buf)
            current_name = m.group(1) or "top"
            buf = []
        else:
            buf.append(line)
    sections[current_name] = "\n".join(buf)

    parsed: dict[str, set[str]] = {}
    for sec_name, body in sections.items():
        opts = set(re.findall(r"(?<!\w)(--[a-z0-9-]+|-[a-zA-Z])(?!\w)", body))
        parsed[sec_name] = opts
    return parsed


def load_and_verify_contract(
    contract_path: Path = CONTRACT_PATH,
    help_path: Path = HELP_FIXTURE_PATH,
) -> dict[str, Any]:
    """Load `colab-cli-contract.json` and verify all subcommands and flags against `colab_help.txt`."""
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    help_text = help_path.read_text(encoding="utf-8")
    parsed_help = parse_help_fixture(help_text)

    if contract.get("session_row_shape") != SESSION_ROW_SHAPE:
        raise ValueError(
            f"Contract session_row_shape mismatch: {contract.get('session_row_shape')!r}"
        )
    if contract.get("empty_sessions_line") != EMPTY_SESSIONS_LINE:
        raise ValueError(
            f"Contract empty_sessions_line mismatch: {contract.get('empty_sessions_line')!r}"
        )

    contents_api = contract.get("contents_api")
    if not isinstance(contents_api, dict):
        raise ValueError("Contract contents_api block missing")
    for key in CONTENTS_API_KEYS:
        if key not in contents_api:
            raise ValueError(f"Contract contents_api.{key} missing")
    if contents_api["upload_creates_parent_dirs"] is not False:
        raise ValueError("Contract contents_api.upload_creates_parent_dirs must be false (one PUT, no mkdir)")
    if contents_api["download_creates_local_parent_dirs"] is not False:
        raise ValueError("Contract contents_api.download_creates_local_parent_dirs must be false (plain open)")
    if contents_api["upload_missing_parent_http_status"] != 500:
        raise ValueError("Contract contents_api.upload_missing_parent_http_status must be 500")

    top_opts = parsed_help.get("top", set())
    for gopt in contract.get("global_options", []):
        if gopt not in top_opts:
            raise ValueError(f"Global option {gopt!r} missing from colab --help fixture")

    for subcmd, spec in contract.get("commands", {}).items():
        if subcmd not in parsed_help:
            raise ValueError(f"Subcommand {subcmd!r} missing from colab_help.txt fixture")
        sub_opts = parsed_help[subcmd]
        for opt in spec.get("options", []):
            if opt not in sub_opts:
                raise ValueError(
                    f"Option {opt!r} for subcommand {subcmd!r} missing from colab_help.txt"
                )
    return contract


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


def make_fake_colab_env(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """Create the executable `colab` shim (with `#SDLAB_FAKE_COLAB_CLI=1`) and fake remote scripts."""
    bin_dir = tmp_path / "fake_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / "colab_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    content_dir = state_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    wheels_dir = tmp_path / "fake_wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)
    lock_file = tmp_path / "colab-window-open.lock"

    # Lane 3 inputs the tests build for themselves: two tiny valid wheels, a matching
    # manifest, and a local git repo whose commits stand in for the upstream pins.
    pin_repo, pin_tip, pin_parent = make_fixture_git_repo(tmp_path / "pin_repo")
    manifest_p = make_fixture_wheels(wheels_dir, tmp_path / "lane3-local-wheels.json", pin_repo, pin_parent)

    py_posix = _to_posix(Path(_resolve_python()))
    fake_py_posix = _to_posix(Path(__file__).resolve())

    fake_colab = bin_dir / "colab"
    fake_colab.write_text(
        "#!/usr/bin/env bash\n"
        "#SDLAB_FAKE_COLAB_CLI=1\n"
        "set -euo pipefail\n"
        f"exec '{py_posix}' '{fake_py_posix}' \"$@\"\n",
        encoding="utf-8",
        newline="\n",
    )
    fake_colab.chmod(fake_colab.stat().st_mode | stat.S_IEXEC)

    # Pre-seed simulated remote scripts inside the fake /content directory for stub modes
    _write_fake_remote_scripts(content_dir)

    env = os.environ.copy()
    git_bash_bin = Path("C:/Program Files/Git/bin")
    git_usr_bin = Path("C:/Program Files/Git/usr/bin")
    extra_bins = [f"{_to_posix(bin_dir)}", str(bin_dir)]
    if git_bash_bin.is_dir():
        extra_bins.extend([_to_posix(git_bash_bin), str(git_bash_bin)])
    if git_usr_bin.is_dir():
        extra_bins.extend([_to_posix(git_usr_bin), str(git_usr_bin)])
    env["PATH"] = os.pathsep.join(extra_bins) + os.pathsep + env.get("PATH", "")
    env["FAKE_COLAB_STATE_DIR"] = _to_posix(state_dir)
    env["COLAB_OPEN_LOCK"] = _to_posix(lock_file)
    env["SDLAB_TEST_FAKE_COLAB"] = "1"
    env["SDLAB_WHEEL_DIR"] = _to_posix(wheels_dir)
    # Pre-flight test hooks; the pre-flight honours them only under this fake CLI.
    env["SDLAB_PREFLIGHT_WHEELS_MANIFEST"] = _to_posix(manifest_p)
    env["EXPECTED_LOCAL_WHEELS_MANIFEST_SHA"] = hashlib.sha256(manifest_p.read_bytes()).hexdigest()
    env["SDLAB_PREFLIGHT_FAST_COMPILE_MOCK"] = "1"
    env["SDLAB_PREFLIGHT_PIN_REPO"] = pin_repo
    env["SDLAB_PREFLIGHT_PIN_SHA"] = pin_tip
    env["FAKE_FIXTURE_PIN_PARENT"] = pin_parent
    return bin_dir, state_dir, env


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=sdlab-test", "-c", "user.email=sdlab-test@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        capture_output=True,
        text=True,
        check=True,
        stdin=subprocess.DEVNULL,
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
            # The parent commit, not the tip: the pin check must accept a non-tip commit.
            entry.update({"git_repo": git_repo, "git_commit": git_commit})
        entries.append(entry)
    manifest = {"schema_version": "1.0", "lane": "lane3", "python_version": "3.12.15", "wheels": entries}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest_path


# ---------------------------------------------------------------------------------------------------
# One kernel per session (docs/colab-cli-contract.md, section 4). google-colab-cli runs every exec on
# the session's stored kernel (colab_cli/commands/execution.py:198-210) and Jupyter runs one cell at a
# time, so the fake runs each exec's cell as a detached process (it outlives the local `colab exec`,
# as a VM cell outlives a killed client), queues a second exec behind a running cell, ends the cell's
# kernel process on `restart-kernel` (the processes the cell spawned are left running; what the real
# server does to them is not visible from the CLI), and ends everything on `stop` (the VM is gone).
# ---------------------------------------------------------------------------------------------------


def _kernel_file(state_dir: Path, sid: str, kind: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)
    return state_dir / "kernels" / f"{safe}.{kind}"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[-1].split()[0]
    except OSError:
        return True
    return state != "Z"


def _running_cell(state_dir: Path, sid: str) -> int | None:
    pid_f = _kernel_file(state_dir, sid, "pid")
    try:
        pid = int(pid_f.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if _pid_alive(pid) else None


def _spawn_detached(argv: list[str], env: dict[str, str], cwd: Path, out_path: Path) -> int:
    """Start argv in its own session, reparented away from this process (double fork), with stdout
    and stderr to out_path. Returns the cell's pid; its process group is its own."""
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - child
        try:
            os.close(r)
            os.setsid()
            pid2 = os.fork()
            if pid2 == 0:
                fd = os.open(str(out_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                os.dup2(fd, 1)
                os.dup2(fd, 2)
                null = os.open(os.devnull, os.O_RDONLY)
                os.dup2(null, 0)
                os.chdir(str(cwd))
                os.execve(argv[0], argv, env)
            os.write(w, str(pid2).encode())
        finally:
            os._exit(0)
    os.close(w)
    data = b""
    while True:
        chunk = os.read(r, 64)
        if not chunk:
            break
        data += chunk
    os.close(r)
    os.waitpid(pid, 0)
    return int(data.decode())


def _kill_recorded_groups(state_dir: Path, sid: str) -> None:
    pg_f = _kernel_file(state_dir, sid, "pgids")
    if not pg_f.exists():
        return
    import signal as _signal

    for line in pg_f.read_text(encoding="utf-8").split():
        try:
            os.killpg(int(line), _signal.SIGKILL)
        except (OSError, ValueError):
            continue
    pg_f.unlink(missing_ok=True)


def _record_inherited_signals(state_dir: Path, subcmd: str) -> None:
    import signal as _signal

    rec = {
        "subcmd": subcmd,
        "pid": os.getpid(),
        "sigterm_ign": _signal.getsignal(_signal.SIGTERM) == _signal.SIG_IGN,
        "sigint_ign": _signal.getsignal(_signal.SIGINT) == _signal.SIG_IGN,
    }
    with (state_dir / "child_signals.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec) + "\n")


def _hang_process(state_dir: Path, ignore_term: bool) -> None:
    import signal as _signal

    if ignore_term:
        _signal.signal(_signal.SIGTERM, _signal.SIG_IGN)
        _signal.signal(_signal.SIGINT, _signal.SIG_IGN)
    with (state_dir / "hung_pids.txt").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{os.getpid()}\n")
    time.sleep(3600)


def _write_fake_remote_scripts(content_dir: Path) -> None:
    uv_logs_dst = content_dir / ".uv_logs"
    uv_logs_dst.mkdir(parents=True, exist_ok=True)
    for sample in (FIXTURES_DIR / "uv_logs").glob("*.txt"):
        shutil.copyfile(sample, uv_logs_dst / sample.name)
    venv_check_helper = """verify_uploaded_venv_script() {
  local uploaded_sh="$1"
  local lane_num="$2"
  local expected_venv="/content/venv-lane${lane_num}"
  local expected_py="${expected_venv}/bin/python"
  local expected_ver="3.14.9"
  if [ "${lane_num}" = "3" ]; then
    expected_ver="3.12.15"
  fi

  local sim_ver="${FAKE_COLAB_VENV_PYTHON_VERSION:-${expected_ver} (main, Oct 21 2026)}"
  local sim_prefix="${FAKE_COLAB_VENV_PREFIX:-${expected_venv}}"
  if [[ "${sim_ver}" != "${expected_ver}"* ]] || [[ "${sim_prefix}" != /content/venv-lane* ]]; then
    if ! grep -Fq "VENV_PYTHON_MISMATCH" "${uploaded_sh}" && ! grep -Fq "${expected_py} -c 'import sys; assert sys.version.startswith(\\"${expected_ver}\\"), sys.version; assert sys.prefix.startswith(\\"/content/venv-lane\\"), sys.prefix'" "${uploaded_sh}"; then
      echo "WARN: VENV_PYTHON_GATE_BYPASSED version=${sim_ver} prefix=${sim_prefix} (no pre-install venv gate in ${uploaded_sh})" >&2
      return 0
    fi
    echo "REFUSED: VENV_PYTHON_MISMATCH version=${sim_ver} prefix=${sim_prefix}" >&2
    exit 1
  fi

  if [ "${FAKE_COLAB_MODE:-}" = "venv_python_mismatch" ]; then
    if ! grep -Fq "VENV_PYTHON_MISMATCH" "${uploaded_sh}" && ! grep -Fq "${expected_py} -c 'import sys; assert sys.version.startswith(\\"${expected_ver}\\"), sys.version; assert sys.prefix.startswith(\\"/content/venv-lane\\"), sys.prefix'" "${uploaded_sh}"; then
      echo "WARN: VENV_PYTHON_GATE_BYPASSED (no pre-install venv gate in ${uploaded_sh})" >&2
      return 0
    fi
    echo "REFUSED: VENV_PYTHON_MISMATCH version=3.13.18 prefix=/usr" >&2
    exit 1
  fi
  # Install failures: a real uv log sample goes through the kit's own uploaded classifier.
  local uv_sample=""
  case "${FAKE_COLAB_MODE:-}" in
    wheel_missing) uv_sample="no_wheel.txt" ;;
    lock_hash_mismatch) uv_sample="hash_mismatch.txt" ;;
    install_network_failure) uv_sample="network_retry.txt" ;;
    install_failed) uv_sample="no_hash.txt" ;;
  esac
  if [ -n "${uv_sample}" ]; then
    if ! grep -Fq "/content/classify_install_log.py --lane lane${lane_num}" "${uploaded_sh}" || [ ! -f classify_install_log.py ]; then
      echo "REFUSED: INSTALL_CLASSIFIER_MISSING: ${uploaded_sh} does not run the uploaded classify_install_log.py" >&2
      exit 1
    fi
    cp ".uv_logs/${uv_sample}" "lane${lane_num}_out/wheels.log"
    cat "lane${lane_num}_out/wheels.log"
    "${SDLAB_PYTHON:-python3}" classify_install_log.py --lane "lane${lane_num}" --log "lane${lane_num}_out/wheels.log" >&2
    exit 1
  fi
  if [ "${FAKE_COLAB_MODE:-}" = "venv_import_outside" ] || [ -n "${FAKE_COLAB_OUTSIDE_IMPORT_PACKAGE:-}" ]; then
    local pkg="${FAKE_COLAB_OUTSIDE_IMPORT_PACKAGE:-torch}"
    if ! grep -Fq "VENV_IMPORT_OUTSIDE_VENV" "${uploaded_sh}"; then
      echo "WARN: VENV_IMPORT_GATE_BYPASSED ${pkg} /usr/local/lib/python3.13/dist-packages/${pkg}/__init__.py (no post-install import gate in ${uploaded_sh})" >&2
      return 0
    fi
    echo "VENV_IMPORT ${pkg} /usr/local/lib/python3.13/dist-packages/${pkg}/__init__.py"
    echo "REFUSED: VENV_IMPORT_OUTSIDE_VENV ${pkg}: /usr/local/lib/python3.13/dist-packages/${pkg}/__init__.py" >&2
    exit 1
  fi
  if [ "${FAKE_COLAB_MODE:-}" = "venv_import_failed" ]; then
    if ! grep -Fq "VENV_IMPORT_FAILED" "${uploaded_sh}"; then
      return 0
    fi
    echo "REFUSED: VENV_IMPORT_FAILED comfy_headless: No module named 'comfy_headless'" >&2
    exit 1
  fi
  if [ "${FAKE_COLAB_MODE:-}" = "uv_no_python_flag" ]; then
    if ! grep -Fq "VENV_IMPORT_OUTSIDE_VENV" "${uploaded_sh}"; then
      return 0
    fi
    echo "REFUSED: VENV_IMPORT_OUTSIDE_VENV: uv pip install without --python ${expected_py} landed in /usr/local/lib/python3.13/dist-packages" >&2
    exit 1
  fi

  if [ ! -f "${uploaded_sh}" ]; then
    echo "REFUSED: uploaded script missing: ${uploaded_sh}" >&2
    exit 2
  fi
  if grep -Eq '^[[:space:]]*source[[:space:]]+.*/activate' "${uploaded_sh}"; then
    echo "REFUSED: VENV_ACTIVATE_RELIANCE: uploaded script relies on activate instead of explicit --python" >&2
    exit 1
  fi
  if ! grep -Eq '^[[:space:]]*unset[[:space:]]+UV_SYSTEM_PYTHON([[:space:]]|$)' "${uploaded_sh}"; then
    echo "REFUSED: UV_SYSTEM_PYTHON_NOT_UNSET: uploaded script did not unset UV_SYSTEM_PYTHON before uv" >&2
    exit 1
  fi
  if ! grep -Eq 'UV_PYTHON_INSTALL_DIR=.*/content/' "${uploaded_sh}"; then
    echo "REFUSED: UV_PYTHON_INSTALL_DIR_MISSING: uploaded script did not set UV_PYTHON_INSTALL_DIR under /content" >&2
    exit 1
  fi

  local uv_pip_lines
  uv_pip_lines="$(grep -E '^[[:space:]]*uv[[:space:]]+pip[[:space:]]+install\\b' "${uploaded_sh}" || true)"
  if [ -z "${uv_pip_lines}" ]; then
    echo "REFUSED: UV_PIP_INSTALL_MISSING: no uv pip install found in ${uploaded_sh}" >&2
    exit 1
  fi
  while IFS= read -r line; do
    [ -z "${line}" ] && continue
    if ! printf '%s\\n' "${line}" | grep -Fq -- "--python ${expected_py}"; then
      echo "REFUSED: VENV_IMPORT_OUTSIDE_VENV: uv pip install without --python ${expected_py} landed in /usr/local/lib/python3.13/dist-packages (UV_SYSTEM_PYTHON=${UV_SYSTEM_PYTHON:-1}): ${line}" >&2
      exit 1
    fi
    if ! printf '%s\\n' "${line}" | grep -Fq -- "--require-hashes" || ! printf '%s\\n' "${line}" | grep -Fq -- "--only-binary :all:"; then
      echo "REFUSED: UNLOCKED_INSTALL: uv pip install missing --require-hashes or --only-binary :all:: ${line}" >&2
      exit 1
    fi
  done <<< "${uv_pip_lines}"

  if ! grep -Fq "${expected_py} -c 'import sys; assert sys.version.startswith(\\"${expected_ver}\\"), sys.version; assert sys.prefix.startswith(\\"/content/venv-lane\\"), sys.prefix'" "${uploaded_sh}"; then
    echo "REFUSED: VENV_PYTHON_GATE_MISSING: pre-install venv interpreter gate missing in ${uploaded_sh}" >&2
    exit 1
  fi
  if ! grep -Fq "VENV_IMPORT_OUTSIDE_VENV" "${uploaded_sh}" || ! grep -Fq "VENV_IMPORT_FAILED" "${uploaded_sh}"; then
    echo "REFUSED: VENV_IMPORT_GATE_MISSING: post-install import gate missing in ${uploaded_sh}" >&2
    exit 1
  fi
  if ! grep -Fq "PYTHON_IDENTITY " "${uploaded_sh}" || ! grep -Fq "PYTHON_BUILD_MISMATCH" "${uploaded_sh}"; then
    echo "REFUSED: PYTHON_IDENTITY_GATE_MISSING: interpreter identity record and build gate missing in ${uploaded_sh}" >&2
    exit 1
  fi
}
"""
    lane1_body = (
        """#!/usr/bin/env bash
set -euo pipefail
: "${PINNED_UV_VERSION:?missing PINNED_UV_VERSION}"
: "${PINNED_PYTHON_VERSION:?missing PINNED_PYTHON_VERSION}"
: "${PINNED_PYTHON_BUILD:?missing PINNED_PYTHON_BUILD}"
: "${PINNED_PYTORCH_INDEX_URL:?missing PINNED_PYTORCH_INDEX_URL}"
: "${PINNED_COMFYUI_REPO:?missing PINNED_COMFYUI_REPO}"
: "${PINNED_COMFYUI_COMMIT:?missing PINNED_COMFYUI_COMMIT}"
: "${PINNED_COMFY_HEADLESS_SPEC:?missing PINNED_COMFY_HEADLESS_SPEC}"


# The uploaded script's sdlab-remote-dirs block is real kit code: run it here, with /content mapped
# to this fake /content, so the lane's directories exist only if the kit's own block made them.
run_uploaded_remote_dirs_block() {
  local uploaded_sh="$1"
  if [ ! -f "${uploaded_sh}" ] || ! grep -q '^# >>> sdlab-remote-dirs$' "${uploaded_sh}" || ! grep -q '^# <<< sdlab-remote-dirs$' "${uploaded_sh}"; then
    echo "REFUSED: REMOTE_DIRS_BLOCK_MISSING: ${uploaded_sh} makes none of its remote directories" >&2
    exit 1
  fi
  sed -n '/^# >>> sdlab-remote-dirs$/,/^# <<< sdlab-remote-dirs$/p' "${uploaded_sh}" | sed "s#/content#${PWD}#g" > .remote_dirs_block.sh
  bash .remote_dirs_block.sh
}
run_uploaded_remote_dirs_block "remote_lane1_stub.sh.uploaded"
[ -d lane1_out ] || { echo "REFUSED: REMOTE_DIR_CREATE_FAILED: lane1_out not made by the kit" >&2; exit 1; }
: > lane1_out/setup.log
echo "setup" > lane1_out/phase.txt
vitals_interval="${FAKE_COLAB_VITALS_INTERVAL_S:-0.2}"

emit_vitals() {
  local phase_val="$1"
  local worker_line="$2"
  local setup_sz
  setup_sz="$(wc -c < lane1_out/setup.log 2>/dev/null | tr -d '[:space:]' || echo 0)"
  echo "=== VITALS $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "CGROUP_MEM_CURRENT: 536870912"
  echo "CGROUP_MEM_MAX: 12884901888"
  echo "CGROUP_MEM: oom_kill 0"
  echo "CGROUP_MEM_STAT: anon 268435456"
  echo "CGROUP_MEM_STAT: file 268435456"
  echo "CGROUP_MEM_STAT: shmem 0"
  echo "MEM: MemTotal:       12582912 kB"
  echo "MEM: MemAvailable:   11534336 kB"
  echo "MEM: AnonPages:        262144 kB"
  echo "MEM: Shmem:                 0 kB"
  echo "SETUP_BYTES: ${setup_sz:-0}"
  echo "PROC:"
  if [ -n "${worker_line}" ]; then
    echo "${worker_line}"
  fi
  printf 'HARNESS: {"phase": "%s"}\\n' "${phase_val}"
}
"""
        + venv_check_helper
        + """
mode="${FAKE_COLAB_MODE:-success}"
if [ "${mode}" = "fail" ]; then
  emit_vitals "setup" ""
  echo "Simulated remote failure with colab-runtime-proxy-token=secret_proxy_tok_lane1_999" >&2
  exit 42
elif [ "${mode}" = "wall" ]; then
  echo "Simulated hung child ignoring inner timeout" | tee -a lane1_out/setup.log
  for _ in $(seq 1 40); do
    emit_vitals "setup" ""
    sleep "${vitals_interval}"
  done
  exit 0
elif [ "${mode}" = "dead_harness" ]; then
  echo "run" > lane1_out/phase.txt
  for _ in $(seq 1 60); do
    emit_vitals "run" ""
    sleep "${vitals_interval}"
  done
  exit 0
elif [ "${mode}" = "setup_phase" ]; then
  setup_total="${FAKE_COLAB_SETUP_DURATION_S:-60}"
  scale="${FAKE_COLAB_SETUP_SCALE:-1.0}"
  step_sleep="$(awk -v t="${setup_total}" -v s="${scale}" 'BEGIN { printf "%.4f", (t * s) / 4.0 }')"
  for idx in 1 2 3 4; do
    echo "SETUP_PROGRESS step=${idx}/4" | tee -a lane1_out/setup.log
    emit_vitals "setup" ""
    sleep "${step_sleep}"
  done
elif [ "${mode}" = "setup_stall" ]; then
  printf 'initial_setup_line\\n' > lane1_out/setup.log
  for _ in $(seq 1 60); do
    emit_vitals "setup" ""
    sleep "${vitals_interval}"
  done
  exit 0
elif [ "${mode}" = "stall" ] || [ "${mode}" = "cap_burn" ] || [ "${mode}" = "usage_fail_midrun" ] || [ "${mode}" = "negative_balance_midrun" ]; then
  echo "run" > lane1_out/phase.txt
  for _ in $(seq 1 60); do
    emit_vitals "run" "101 /content/venv-lane1/bin/python /content/ComfyUI/main.py --cpu --listen 127.0.0.1"
    sleep "${vitals_interval}"
  done
  exit 0
fi

verify_uploaded_venv_script "remote_lane1_stub.sh.uploaded" "1" 2>&1 | tee -a lane1_out/setup.log
identity_build="20261021"
if [ "${mode}" = "python_build_mismatch" ]; then
  identity_build="20250101"
fi
echo 'PYTHON_IDENTITY {"key": "cpython-3.14.9-linux-x86_64-gnu", "build": "'"${identity_build}"'", "pinned_build": "'"${PINNED_PYTHON_BUILD}"'", "download_url": "https://releases.astral.sh/github/python-build-standalone/releases/download/20261021/cpython-3.14.9%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz", "sys_version": "3.14.9 (main, Oct 21 2026)", "binary": "/content/.sdlab_python_314/install/cpython-3.14.9-linux-x86_64-gnu/bin/python3.14", "binary_sha256": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}' | tee -a lane1_out/setup.log
if [ "${identity_build}" != "${PINNED_PYTHON_BUILD}" ]; then
  echo "REFUSED: PYTHON_BUILD_MISMATCH: cpython-3.14.9-linux-x86_64-gnu build=${identity_build} pinned=${PINNED_PYTHON_BUILD}" >&2
  exit 1
fi
emit_vitals "setup" 'root        2216    2101 21 19:01 ?        00:00:02 /content/venv-lane1/bin/python -c  import importlib import sys  REQUIRED = ("comfy_headless", "torch", "safetensors", "PIL", "yaml", "aiohttp") for mod_name in REQUIRED:     try:         mod = importlib.import_module(mod_name)     except Exception as exc:         sys.stderr.write(f"REFUSED: VENV_IMPORT_FAILED {mod_name}: {exc}")         raise SystemExit(1)     mod_file = getattr(mod, "__file__", None) or ""     if not mod_file.startswith("/content/venv-lane1/"):         sys.stderr.write(f"REFUSED: VENV_IMPORT_OUTSIDE_VENV {mod_name}: {mod_file}")         raise SystemExit(1)'
for mod_name in comfy_headless torch safetensors PIL yaml aiohttp; do
  echo "VENV_IMPORT ${mod_name} /content/venv-lane1/lib/python3.14/site-packages/${mod_name}/__init__.py" | tee -a lane1_out/setup.log
done
printf 'setup_complete\\n' >> lane1_out/setup.log
echo "run" > lane1_out/phase.txt
emit_vitals "run" "101 /content/venv-lane1/bin/python /content/ComfyUI/main.py --cpu --listen 127.0.0.1"
echo 'WINDOW_JSON {"system_python": "3.13.16", "python": "3.14.9", "python_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "uv": "uv 0.13.5", "comfyui_commit": "158419f3a0017c2ce123484b14b6c527716d6ec8", "comfy_headless_version": "3.1.0", "comfy_bind": "127.0.0.1:8188", "listening_sockets": ["127.0.0.1:8188"]}'
echo "LANE1_STUB_OK python=3.14.9 comfy_bind=127.0.0.1:8188 resume_hash_match=true"
printf 'FAKE_TAR_BYTES' > lane1_stub_bundle.tar.gz
"""
    )
    lane3_body = (
        """#!/usr/bin/env bash
set -euo pipefail
: "${PINNED_UV_VERSION:?missing PINNED_UV_VERSION}"
: "${PINNED_PYTHON_VERSION:?missing PINNED_PYTHON_VERSION}"
: "${PINNED_PYTHON_BUILD:?missing PINNED_PYTHON_BUILD}"
: "${PINNED_PYTORCH_INDEX_URL:?missing PINNED_PYTORCH_INDEX_URL}"
: "${PINNED_AI_TOOLKIT_REPO:?missing PINNED_AI_TOOLKIT_REPO}"
: "${PINNED_AI_TOOLKIT_COMMIT:?missing PINNED_AI_TOOLKIT_COMMIT}"


# The uploaded script's sdlab-remote-dirs block is real kit code: run it here, with /content mapped
# to this fake /content, so the lane's directories exist only if the kit's own block made them.
run_uploaded_remote_dirs_block() {
  local uploaded_sh="$1"
  if [ ! -f "${uploaded_sh}" ] || ! grep -q '^# >>> sdlab-remote-dirs$' "${uploaded_sh}" || ! grep -q '^# <<< sdlab-remote-dirs$' "${uploaded_sh}"; then
    echo "REFUSED: REMOTE_DIRS_BLOCK_MISSING: ${uploaded_sh} makes none of its remote directories" >&2
    exit 1
  fi
  sed -n '/^# >>> sdlab-remote-dirs$/,/^# <<< sdlab-remote-dirs$/p' "${uploaded_sh}" | sed "s#/content#${PWD}#g" > .remote_dirs_block.sh
  bash .remote_dirs_block.sh
}
# The uploaded script's sdlab-lane3-mode block is real kit code: run it on this fake VM. On a CPU
# card nvidia-smi finds no GPU (a stand-in shadows any on the rig's PATH), so a kit that passed
# LANE3_MODE=train fails here with the same refusal as on a real CPU card. On a GPU card (the kit's
# `colab new --gpu <card>`, recorded in card.txt) the stand-in lists one A100.
fake_card="$(cat "${FAKE_COLAB_STATE_DIR:-..}/card.txt" 2>/dev/null || echo CPU)"
mkdir -p .fake-vm-bin
if [ "${fake_card}" = "CPU" ]; then
  printf '#!/usr/bin/env bash\\necho "NVIDIA-SMI has failed because it could not communicate with the NVIDIA driver." >&2\\nexit 9\\n' > .fake-vm-bin/nvidia-smi
else
  cat > .fake-vm-bin/nvidia-smi << 'NVSMIEOF'
#!/usr/bin/env bash
case "$*" in
  *-L*) echo "GPU 0: NVIDIA A100-SXM4-80GB (UUID: GPU-00000000-fake)" ;;
  *--query-gpu*) echo "580.82.07, NVIDIA A100-SXM4-80GB, 81920 MiB" ;;
  *) echo "fake nvidia-smi" ;;
esac
NVSMIEOF
fi
chmod +x .fake-vm-bin/nvidia-smi
run_uploaded_lane3_mode_block() {
  local uploaded_sh="$1"
  if ! grep -q '^# >>> sdlab-lane3-mode$' "${uploaded_sh}" || ! grep -q '^# <<< sdlab-lane3-mode$' "${uploaded_sh}"; then
    echo "REFUSED: LANE3_MODE_BLOCK_MISSING: ${uploaded_sh} has no sdlab-lane3-mode gate" >&2
    exit 1
  fi
  sed -n '/^# >>> sdlab-lane3-mode$/,/^# <<< sdlab-lane3-mode$/p' "${uploaded_sh}" > .lane3_mode_block.sh
  PATH="${PWD}/.fake-vm-bin:${PATH}" bash -c 'set -euo pipefail; source .lane3_mode_block.sh; echo "LANE3_MODE=${LANE3_MODE} CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES-unset}"'
}
# Train mode on the fake GPU VM: the uploaded script's sdlab-lane3-train and sdlab-lane3-window
# blocks are real kit code. They run with /content mapped to this fake /content, /proc/meminfo and
# /dev/shm mapped to fake ones (FAKE_VM_MEM_TOTAL_KB / FAKE_VM_MEM_AVAILABLE_KB), stand-ins for the
# lane's torch, bitsandbytes and huggingface_hub (tests/colab/fixtures/fake_vm_site) and a stand-in
# ai-toolkit run.py that saves a checkpoint and a sample (FAKE_VM_TRAIN=fail_after_save: it saves,
# then dies with a CUDA OOM; =hang_after_save: it saves, then hangs; =no_sample: no sample image).
# The block runs as <content>/remote_lane3_stub.sh.trainblock, so its command line names the
# remote script the way the real VM's does (bundle-now finds it by that).
run_uploaded_train_and_window_blocks() {
  local uploaded_sh="$1"
  local blk
  for blk in sdlab-hf-token sdlab-lane3-train sdlab-lane3-window; do
    if ! grep -q "^# >>> ${blk}$" "${uploaded_sh}" || ! grep -q "^# <<< ${blk}$" "${uploaded_sh}"; then
      echo "REFUSED: TRAIN_BLOCK_MISSING: ${uploaded_sh} has no ${blk} block" >&2
      exit 1
    fi
  done
  {
    printf '%s\\n' "${FAKE_VM_MEM_TOTAL_KB:-175000000}" "${FAKE_VM_MEM_AVAILABLE_KB:-170000000}"
  } | awk 'NR==1{print "MemTotal:       " $1 " kB"} NR==2{print "MemFree:        " $1 " kB"; print "MemAvailable:   " $1 " kB"}' > .fake-vm-meminfo
  mkdir -p .fake-vm-shm ai-toolkit
  cat > ai-toolkit/run.py << 'RUNPYEOF'
import os, re, sys, time
from pathlib import Path
job = Path(sys.argv[1]).read_text(encoding="utf-8")
tf = re.search(r'training_folder: "([^"]+)"', job).group(1)
model = re.search(r'name_or_path: "([^"]+)"', job).group(1)
name = re.search(r"^  name: (\\S+)$", job, re.M).group(1)
steps = int(re.search(r"^\\s+steps: (\\d+)$", job, re.M).group(1))
save_every = int(re.search(r"^\\s+save_every: (\\d+)$", job, re.M).group(1))
sample_every = int(re.search(r"^\\s+sample_every: (\\d+)$", job, re.M).group(1))
assert os.environ.get("HF_HUB_OFFLINE") == "1", "run.py must run with the hub offline"
assert Path(model).is_dir(), f"model path {model} is not the local snapshot"
out = Path(tf) / name
(out / "samples").mkdir(parents=True, exist_ok=True)
print("Loading Qwen Image model", flush=True)
import json, struct
def st(tag, truncate=False):
    # A real safetensors layout: 8-byte header length, JSON header, data; truncate cuts the tail.
    data = tag * 64
    hdr = json.dumps({"lora": {"dtype": "U8", "shape": [len(data)], "data_offsets": [0, len(data)]}}).encode()
    blob = struct.pack("<Q", len(hdr)) + hdr + data
    return blob[:-100] if (truncate or os.environ.get("FAKE_VM_TRAIN") == "truncated_save") else blob
time.sleep(0.3)
if os.environ.get("FAKE_VM_TRAIN") == "hang_after_step_250":
    assert (steps, save_every, sample_every) == (500, 250, 250), (steps, save_every, sample_every)
    (out / f"{name}_000000250.safetensors").write_bytes(st(b"FAKE-LORA-STEP-250"))
    for idx in range(6):
        (out / "samples" / f"1762400000000__000000250_{idx}.jpg").write_bytes(b"\\xff\\xd8FAKEJPEG" * 32)
    (out / f"{name}_000000500.safetensors").write_bytes(st(b"FAKE-LORA-STEP-500", truncate=True))
    time.sleep(600)
if steps == 500:
    assert (save_every, sample_every) == (250, 250), (save_every, sample_every)
    (out / f"{name}_000000250.safetensors").write_bytes(st(b"FAKE-LORA-STEP-250"))
    for idx in range(6):
        (out / "samples" / f"1762400000000__000000250_{idx}.jpg").write_bytes(b"\\xff\\xd8FAKEJPEG" * 32)
    time.sleep(0.3)
    (out / f"{name}_000000500.safetensors").write_bytes(st(b"FAKE-LORA-STEP-500"))
    for idx in range(6):
        (out / "samples" / f"1762400000000__000000500_{idx}.jpg").write_bytes(b"\\xff\\xd8FAKEJPEG" * 32)
    (out / f"{name}.safetensors").write_bytes(st(b"FAKE-LORA-FINAL"))
    print("Done", flush=True)
    sys.exit(0)
(out / f"{name}_000000020.safetensors").write_bytes(st(b"FAKE-LORA-STEP-20"))
time.sleep(0.3)
if os.environ.get("FAKE_VM_TRAIN") == "fail_after_save":
    print("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB", flush=True)
    time.sleep(0.3)
    sys.exit(1)
if os.environ.get("FAKE_VM_TRAIN") == "hang_after_save":
    (out / "samples" / "1762400000000__000000020_0.jpg").write_bytes(b"\\xff\\xd8FAKEJPEG" * 32)
    time.sleep(600)
time.sleep(float(os.environ.get("FAKE_VM_TRAIN_SLEEP_S", "0")))
if os.environ.get("FAKE_VM_TRAIN") != "no_sample":
    (out / "samples" / "1762400000000__000000020_0.jpg").write_bytes(b"\\xff\\xd8FAKEJPEG" * 32)
(out / f"{name}.safetensors").write_bytes(st(b"FAKE-LORA-FINAL"))
print("Done", flush=True)
RUNPYEOF
  {
    echo 'set -euo pipefail'
    echo 'LANE3_TRAIN_STATE="trained"'
    echo 'CHECKPOINT_PATH=""'
    echo 'OVERRIDE_SHA="$(sha256sum lane3.lock | awk '"'"'{print $1}'"'"')"'
    sed -n '/^# >>> sdlab-hf-token$/,/^# <<< sdlab-hf-token$/p' "${uploaded_sh}"
    sed -n '/^# >>> sdlab-lane3-train$/,/^# <<< sdlab-lane3-train$/p' "${uploaded_sh}"
    sed -n '/^# >>> sdlab-lane3-window$/,/^# <<< sdlab-lane3-window$/p' "${uploaded_sh}"
  } | sed -e "s#/content#${PWD}#g" -e "s#/proc/meminfo#${PWD}/.fake-vm-meminfo#g" -e "s#/dev/shm#${PWD}/.fake-vm-shm#g" > remote_lane3_stub.sh.trainblock
  PATH="${PWD}/.fake-vm-bin:${PATH}" PYTHONPATH="${FAKE_VM_SITE}${PYTHONPATH:+:${PYTHONPATH}}" \\
    bash "${PWD}/remote_lane3_stub.sh.trainblock"
}
run_uploaded_lane3_mode_block "remote_lane3_stub.sh.uploaded"
run_uploaded_remote_dirs_block "remote_lane3_stub.sh.uploaded"
[ -d lane3_out ] || { echo "REFUSED: REMOTE_DIR_CREATE_FAILED: lane3_out not made by the kit" >&2; exit 1; }
: > lane3_out/setup.log
echo "setup" > lane3_out/phase.txt
vitals_interval="${FAKE_COLAB_VITALS_INTERVAL_S:-0.2}"

emit_vitals() {
  local phase_val="$1"
  local worker_line="$2"
  local setup_sz
  setup_sz="$(wc -c < lane3_out/setup.log 2>/dev/null | tr -d '[:space:]' || echo 0)"
  echo "=== VITALS $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "CGROUP_MEM_CURRENT: 536870912"
  echo "CGROUP_MEM_MAX: 12884901888"
  echo "CGROUP_MEM: oom_kill 0"
  echo "CGROUP_MEM_STAT: anon 268435456"
  echo "CGROUP_MEM_STAT: file 268435456"
  echo "CGROUP_MEM_STAT: shmem 0"
  echo "MEM: MemTotal:       12582912 kB"
  echo "MEM: MemAvailable:   11534336 kB"
  echo "MEM: AnonPages:        262144 kB"
  echo "MEM: Shmem:                 0 kB"
  echo "SETUP_BYTES: ${setup_sz:-0}"
  echo "PROC:"
  if [ -n "${worker_line}" ]; then
    echo "${worker_line}"
  fi
  printf 'HARNESS: {"phase": "%s"}\\n' "${phase_val}"
}
"""
        + venv_check_helper
        + """
mode="${FAKE_COLAB_MODE:-success}"
if [ "${mode}" = "fail" ]; then
  emit_vitals "setup" ""
  echo "Simulated remote failure with colab-runtime-proxy-token=secret_proxy_tok_lane3_999" >&2
  exit 42
elif [ "${mode}" = "wall" ]; then
  echo "Simulated hung child ignoring inner timeout" | tee -a lane3_out/setup.log
  for _ in $(seq 1 40); do
    emit_vitals "setup" ""
    sleep "${vitals_interval}"
  done
  exit 0
elif [ "${mode}" = "dead_harness" ]; then
  echo "run" > lane3_out/phase.txt
  for _ in $(seq 1 60); do
    emit_vitals "run" ""
    sleep "${vitals_interval}"
  done
  exit 0
elif [ "${mode}" = "setup_phase" ]; then
  setup_total="${FAKE_COLAB_SETUP_DURATION_S:-60}"
  scale="${FAKE_COLAB_SETUP_SCALE:-1.0}"
  step_sleep="$(awk -v t="${setup_total}" -v s="${scale}" 'BEGIN { printf "%.4f", (t * s) / 4.0 }')"
  for idx in 1 2 3 4; do
    echo "SETUP_PROGRESS step=${idx}/4" | tee -a lane3_out/setup.log
    emit_vitals "setup" ""
    sleep "${step_sleep}"
  done
elif [ "${mode}" = "setup_stall" ]; then
  printf 'initial_setup_line\\n' > lane3_out/setup.log
  for _ in $(seq 1 60); do
    emit_vitals "setup" ""
    sleep "${vitals_interval}"
  done
  exit 0
elif [ "${mode}" = "ram_replay" ]; then
  # Replays a real VM's memory readings: FAKE_COLAB_RAM_REPLAY names a file with one sample per
  # line, "<cgroup memory.current bytes> <MemTotal kB> <MemAvailable kB> <AnonPages kB>", printed
  # in the order and format of the kit's vitals emitter (cgroup memory.max "max", as on Colab).
  # The replayed run's emitter predates the memory.stat and Shmem lines, so they are derived:
  # anon = AnonPages, shmem = 0, file = memory.current - anon (Shmem 0 kB). The last sample is
  # held so the live guards read it more than once; FAKE_COLAB_RAM_TORN then ends the stream on a
  # sample cut mid-write (after_stat: after anon/file; number: inside "anon <n>"; meminfo:
  # inside the MEM: lines) and goes quiet.
  echo "run" > lane3_out/phase.txt
  emit_ram_head() {
    echo "=== VITALS $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    echo "CGROUP_MEM_CURRENT: $1"
    echo "CGROUP_MEM_MAX: max"
    echo "CGROUP_MEM: oom_kill 0"
  }
  emit_ram_sample() {
    local anon_b=$(( $4 * 1024 ))
    local file_b=$(( $1 > anon_b ? $1 - anon_b : 0 ))
    emit_ram_head "$1"
    echo "CGROUP_MEM_STAT: anon ${anon_b}"
    echo "CGROUP_MEM_STAT: file ${file_b}"
    echo "CGROUP_MEM_STAT: shmem 0"
    echo "MEM: MemTotal:       $2 kB"
    echo "MEM: MemAvailable:   $3 kB"
    echo "MEM: AnonPages:      $4 kB"
    echo "MEM: Shmem:          0 kB"
    echo "SETUP_BYTES: 0"
    echo "PROC:"
    echo "101 /content/venv-lane3/bin/python /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml"
    printf 'HARNESS: {"phase": "run"}\\n'
  }
  last=""
  while read -r cg tot avail anon; do
    [ -n "${anon:-}" ] || continue
    emit_ram_sample "${cg}" "${tot}" "${avail}" "${anon}"
    last="${cg} ${tot} ${avail} ${anon}"
    sleep "${vitals_interval}"
  done < "${FAKE_COLAB_RAM_REPLAY:?ram_replay needs FAKE_COLAB_RAM_REPLAY}"
  for _ in $(seq 1 "${FAKE_COLAB_RAM_HOLD:-40}"); do
    emit_ram_sample ${last}
    sleep "${vitals_interval}"
  done
  if [ -n "${FAKE_COLAB_RAM_TORN:-}" ]; then
    set -- ${last}
    emit_ram_head "$1"
    case "${FAKE_COLAB_RAM_TORN}" in
      after_stat) printf 'CGROUP_MEM_STAT: anon %s\nCGROUP_MEM_STAT: file %s\n' "$(( $4 * 1024 ))" "0" ;;
      number) printf 'CGROUP_MEM_STAT: anon 55' ;;
      meminfo) printf 'CGROUP_MEM_STAT: anon %s\nCGROUP_MEM_STAT: file 0\nCGROUP_MEM_STAT: shmem 0\nMEM: MemTotal:       %s kB\nMEM: MemAvail' "$(( $4 * 1024 ))" "$2" ;;
    esac
    sleep "${FAKE_COLAB_RAM_TORN_QUIET_S:-6}"
  fi
  exit 0
elif [ "${mode}" = "stall" ] || [ "${mode}" = "cap_burn" ] || [ "${mode}" = "usage_fail_midrun" ] || [ "${mode}" = "negative_balance_midrun" ]; then
  echo "run" > lane3_out/phase.txt
  for _ in $(seq 1 60); do
    emit_vitals "run" "101 /content/venv-lane3/bin/python /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml"
    sleep "${vitals_interval}"
  done
  exit 0
fi

verify_uploaded_venv_script "remote_lane3_stub.sh.uploaded" "3" 2>&1 | tee -a lane3_out/setup.log
identity_build="20261021"
if [ "${mode}" = "python_build_mismatch" ]; then
  identity_build="20250101"
fi
echo 'PYTHON_IDENTITY {"key": "cpython-3.12.15-linux-x86_64-gnu", "build": "'"${identity_build}"'", "pinned_build": "'"${PINNED_PYTHON_BUILD}"'", "download_url": "https://releases.astral.sh/github/python-build-standalone/releases/download/20261021/cpython-3.12.15%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz", "sys_version": "3.12.15 (main, Oct 21 2026)", "binary": "/content/.sdlab_python_312/install/cpython-3.12.15-linux-x86_64-gnu/bin/python3.12", "binary_sha256": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}' | tee -a lane3_out/setup.log
if [ "${identity_build}" != "${PINNED_PYTHON_BUILD}" ]; then
  echo "REFUSED: PYTHON_BUILD_MISMATCH: cpython-3.12.15-linux-x86_64-gnu build=${identity_build} pinned=${PINNED_PYTHON_BUILD}" >&2
  exit 1
fi

# The uploaded script's sdlab-local-wheels-lock block is real kit code too: run it here, with /content
# mapped to this fake /content and a stand-in for the venv's python, then hand the lock it wrote to
# real uv (when uv is on PATH), so a lock uv cannot parse fails this stub as it fails a real VM.
run_uploaded_local_wheels_lock_block() {
  local uploaded_sh="$1"
  if ! grep -q '^# >>> sdlab-local-wheels-lock$' "${uploaded_sh}" || ! grep -q '^# <<< sdlab-local-wheels-lock$' "${uploaded_sh}"; then
    echo "REFUSED: LOCAL_WHEELS_LOCK_BLOCK_MISSING: ${uploaded_sh} has no sdlab-local-wheels-lock block" >&2
    exit 1
  fi
  local host_py
  host_py="${SDLAB_PYTHON:-$(command -v python3 || command -v python)}"
  mkdir -p venv-lane3/bin
  {
    echo '#!/usr/bin/env bash'
    echo 'exec "'"${host_py}"'" "$@"'
  } > venv-lane3/bin/python
  chmod +x venv-lane3/bin/python
  sed -n '/^# >>> sdlab-local-wheels-lock$/,/^# <<< sdlab-local-wheels-lock$/p' "${uploaded_sh}" | sed "s#/content#${PWD}#g" > .local_wheels_lock_block.sh
  bash .local_wheels_lock_block.sh
  if [ ! -s lane3_out/local-wheels.lock ]; then
    echo "REFUSED: LOCAL_WHEELS_LOCK_MISSING: the kit's block wrote no lane3_out/local-wheels.lock" >&2
    exit 1
  fi
  if ! command -v uv >/dev/null 2>&1; then
    echo "LOCAL_WHEELS_LOCK_UV_CHECK_SKIPPED: uv is not on PATH"
    return 0
  fi
  rm -rf .lock-check-venv
  # uv runs in the background while this stub keeps emitting vitals and setup lines, so a cold uv
  # never reads as a silent setup (SETUP_STALL) to the kit's live guards.
  (
    uv venv --quiet --python "${host_py}" .lock-check-venv || exit 1
    venv_py=".lock-check-venv/bin/python"
    [ -e "${venv_py}" ] || venv_py=".lock-check-venv/Scripts/python.exe"
    uv pip install --python "${venv_py}" --require-hashes --only-binary :all: --no-index --find-links wheels --no-deps -r lane3_out/local-wheels.lock
  ) > lane3_out/local-wheels-check.log 2>&1 &
  local uv_pid="$!"
  while kill -0 "${uv_pid}" 2>/dev/null; do
    echo "LOCAL_WHEELS_LOCK_UV_CHECK running"
    emit_vitals "setup" ""
    sleep 0.2
  done
  if ! wait "${uv_pid}"; then
    cat lane3_out/local-wheels-check.log >&2
    echo "REFUSED: LOCAL_WHEELS_LOCK_REJECTED: uv refused lane3_out/local-wheels.lock" >&2
    exit 1
  fi
  echo "LOCAL_WHEELS_LOCK_UV_OK"
}
run_uploaded_local_wheels_lock_block "remote_lane3_stub.sh.uploaded" 2>&1 | tee -a lane3_out/setup.log
emit_vitals "setup" 'root        2216    2101 21 19:01 ?        00:00:02 /content/venv-lane3/bin/python -c  import importlib import sys  REQUIRED = ("sentencepiece", "torch", "torchaudio", "safetensors", "yaml", "oyaml", "PIL", "diffusers", "lycoris") for mod_name in REQUIRED:     try:         mod = importlib.import_module(mod_name)     except Exception as exc:         sys.stderr.write(f"REFUSED: VENV_IMPORT_FAILED {mod_name}: {exc}")         raise SystemExit(1)     mod_file = getattr(mod, "__file__", None) or ""     if not mod_file.startswith("/content/venv-lane3/"):         sys.stderr.write(f"REFUSED: VENV_IMPORT_OUTSIDE_VENV {mod_name}: {mod_file}")         raise SystemExit(1)'
for mod_name in sentencepiece torch torchaudio safetensors yaml oyaml PIL diffusers lycoris; do
  echo "VENV_IMPORT ${mod_name} /content/venv-lane3/lib/python3.12/site-packages/${mod_name}/__init__.py" | tee -a lane3_out/setup.log
done
printf 'setup_complete\\n' >> lane3_out/setup.log
if [ "${LANE3_MODE:-install}" = "train" ]; then
  run_uploaded_train_and_window_blocks "remote_lane3_stub.sh.uploaded"
  exit 0
fi
# The CPU install-path stub stops at the import gate: the uploaded script must say so and keep its
# training step behind LANE3_MODE=train.
if ! grep -Fq 'TRAIN_SKIPPED: cpu stub; training needs a GPU rung' "remote_lane3_stub.sh.uploaded" \\
  || ! grep -Fq 'LANE3_TRAIN_STATE="skipped_cpu_stub"' "remote_lane3_stub.sh.uploaded"; then
  echo "REFUSED: TRAIN_SKIP_MISSING: the uploaded script does not stop at the import gate" >&2
  exit 1
fi
echo "TRAIN_SKIPPED: cpu stub; training needs a GPU rung" | tee -a lane3_out/setup.log
printf 'SENTENCEPIECE_OK 0.2.1\\n' > lane3_out/sentencepiece.txt
printf 'Installed 158 packages\\n' > lane3_out/wheels.log
printf '{"key": "cpython-3.12.15-linux-x86_64-gnu", "build": "20261021"}\\n' > lane3_out/python_identity.json
train_state="skipped_cpu_stub"
window_rec='{"system_python": "3.13.16", "python": "3.12.15", "python_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "uv": "uv 0.13.5", "ai_toolkit_commit": "beb94824c51480a04d3c86c718603676fdef6938", "override_sha256": "09d15fae7473fd76131bb01578a6b060b20c3b10e91eccd8133377ea17b03286", "lane3_mode": "install", "train": "'"${train_state}"'", "checkpoint_path": null}'
printf '%s\\n' "${window_rec}" > lane3_out/vm_window.json
echo "WINDOW_JSON ${window_rec}"
echo "LANE3_STUB_OK python=3.12.15 sentencepiece=0.2.1 train=${train_state}"
tar -czf lane3_stub_bundle.tar.gz -C lane3_out .
"""
    )
    (content_dir / ".fake_remote_lane1_stub.sh").write_text(lane1_body, encoding="utf-8", newline="\n")
    (content_dir / ".fake_remote_lane3_stub.sh").write_text(lane3_body, encoding="utf-8", newline="\n")


def _normalize_remote_content_path(raw: str) -> str:
    s = raw.replace("\\", "/")
    idx = s.find("/content/")
    if idx > 0 and re.match(r"^[A-Za-z]:/", s[: idx + 1]):
        return s[idx:]
    if s.endswith("/content") and re.match(r"^[A-Za-z]:/", s):
        return "/content"
    return s


def _normalize_host_path(raw: str) -> Path:
    m = re.match(r"^/([a-zA-Z])/(.*)$", raw)
    if m and os.name == "nt":
        return Path(f"{m.group(1).upper()}:/{m.group(2)}")
    return Path(raw)


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Validate contract against colab_help.txt at startup
    contract = load_and_verify_contract()
    commands_contract: dict[str, Any] = contract["commands"]
    global_options: set[str] = set(contract.get("global_options", []))

    state_dir_raw = os.environ.get("FAKE_COLAB_STATE_DIR")
    if not state_dir_raw:
        sys.stderr.write("missing FAKE_COLAB_STATE_DIR\n")
        return 2
    state_dir = _normalize_host_path(state_dir_raw)
    state_dir.mkdir(parents=True, exist_ok=True)
    # Every call's argv, as `ps` shows it on the rig (the token tests scan this).
    with (state_dir / "argv.log").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(["colab", *raw_args]) + "\n")
    content_dir = state_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    if not (content_dir / ".fake_remote_lane1_stub.sh").exists():
        _write_fake_remote_scripts(content_dir)

    lock_file = _normalize_host_path(
        os.environ.get("COLAB_OPEN_LOCK", "/tmp/colab-window-open.lock")
    )

    idx = 0
    top_help_requested = False
    while idx < len(raw_args) and raw_args[idx].startswith("-"):
        gopt = raw_args[idx].split("=", 1)[0]
        if gopt not in global_options:
            sys.stderr.write(f"No such global option: {raw_args[idx]}\n")
            return 2
        if gopt in ("-h", "--help"):
            top_help_requested = True
        if gopt in GLOBAL_VALUE_FLAGS and "=" not in raw_args[idx]:
            if idx + 1 >= len(raw_args):
                sys.stderr.write(f"Option '{gopt}' requires an argument.\n")
                return 2
            idx += 2
        else:
            idx += 1

    if top_help_requested and idx >= len(raw_args):
        print("Usage: colab [OPTIONS] COMMAND [ARGS]...")
        return 0

    if idx >= len(raw_args):
        sys.stderr.write("Missing command.\n")
        return 2

    subcmd = raw_args[idx]
    args = raw_args[idx + 1 :]

    if subcmd not in commands_contract:
        sys.stderr.write(
            f"No such command '{subcmd}' in {contract['cli']} {contract['version']}.\n"
        )
        return 2

    allowed_opts = set(commands_contract[subcmd]["options"])
    value_opts = VALUE_OPTS_BY_CMD.get(subcmd, frozenset())

    parsed_opts: dict[str, list[str]] = {}
    positionals: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            sys.stderr.write(
                f"colab {subcmd} --: not an option of {contract['cli']} {contract['version']}\n"
            )
            return 2
        if tok.startswith("-") and len(tok) > 1:
            if "=" in tok:
                opt_name, opt_val = tok.split("=", 1)
                if opt_name not in allowed_opts:
                    sys.stderr.write(
                        f"colab {subcmd} {opt_name}: not an option of {contract['cli']} {contract['version']} "
                        f"(allowed: {' '.join(sorted(allowed_opts))})\n"
                    )
                    return 2
                parsed_opts.setdefault(opt_name, []).append(opt_val)
                i += 1
            else:
                opt_name = tok
                if opt_name not in allowed_opts:
                    sys.stderr.write(
                        f"colab {subcmd} {opt_name}: not an option of {contract['cli']} {contract['version']} "
                        f"(allowed: {' '.join(sorted(allowed_opts))})\n"
                    )
                    return 2
                if opt_name in value_opts:
                    if i + 1 >= len(args):
                        sys.stderr.write(f"Option '{opt_name}' requires an argument.\n")
                        return 2
                    parsed_opts.setdefault(opt_name, []).append(args[i + 1])
                    i += 2
                else:
                    parsed_opts.setdefault(opt_name, []).append("true")
                    i += 1
        else:
            positionals.append(tok)
            i += 1

    if "-h" in parsed_opts or "--help" in parsed_opts:
        print(commands_contract[subcmd]["usage"])
        return 0

    expected_pos = POSITIONAL_COUNTS_BY_CMD[subcmd]
    if len(positionals) != expected_pos:
        sys.stderr.write(
            f"colab {subcmd}: expected {expected_pos} positional arguments, got {len(positionals)} ({positionals!r})\n"
        )
        return 2

    def _get_opt(*names: str) -> str | None:
        for n in names:
            vals = parsed_opts.get(n)
            if vals:
                return vals[-1]
        return None

    # Record validated call in calls.log and calls.jsonl
    _record_inherited_signals(state_dir, subcmd)
    with (state_dir / "calls.log").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"CALL {' '.join(raw_args)}\n")
    with (state_dir / "calls.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(
            json.dumps(
                {
                    "subcmd": subcmd,
                    "args": args,
                    "parsed_opts": parsed_opts,
                    "positionals": positionals,
                    "ts": time.time(),
                }
            )
            + "\n"
        )

    mode = os.environ.get("FAKE_COLAB_MODE", "success")

    if subcmd == "usage":
        count_file = state_dir / "usage_count.txt"
        c = int(count_file.read_text(encoding="utf-8").strip()) if count_file.is_file() else 0
        c += 1
        count_file.write_text(f"{c}\n", encoding="utf-8", newline="\n")

        if os.environ.get("FAKE_COLAB_USAGE_FAIL") == "1":
            sys.stderr.write("colab usage failed\n")
            return 1
        if mode == "usage_fail_start" and c == 1:
            print("UNPARSEABLE_USAGE_TEXT_WITHOUT_BALANCE")
            return 0
        if mode == "usage_fail_midrun" and c >= 2:
            print("UNPARSEABLE_USAGE_TEXT_MIDRUN")
            return 0
        if mode == "negative_balance_start" and c == 1:
            print("Current balance: -5.00 compute units\nUsage rate: 0.26/hr\nActive assignments: 1")
            return 0
        if mode == "negative_balance_midrun" and c >= 2:
            print("Current balance: -5.00 compute units\nUsage rate: 0.26/hr\nActive assignments: 1")
            return 0
        raw_override = os.environ.get("FAKE_COLAB_USAGE_TEXT")
        if raw_override is not None:
            print(raw_override)
            return 0
        bal = "9.75" if (mode == "cap_burn" and c >= 2) else os.environ.get("FAKE_COLAB_BALANCE", "9.85")
        session_opened = (state_dir / "session_opened.txt").is_file()
        post_count = 0
        if session_opened:
            post_count_file = state_dir / "post_open_usage_count.txt"
            post_count = (
                int(post_count_file.read_text(encoding="utf-8").strip())
                if post_count_file.is_file()
                else 0
            )
            post_count += 1
            post_count_file.write_text(f"{post_count}\n", encoding="utf-8", newline="\n")
        pre_rate_str = os.environ.get("FAKE_COLAB_PRE_OPEN_RATE_STR")
        post_rate_seq_raw = os.environ.get("FAKE_COLAB_POST_OPEN_RATE_SEQ")
        post_rate_str = os.environ.get("FAKE_COLAB_POST_OPEN_RATE_STR")
        if not session_opened and pre_rate_str is not None:
            rate_str = pre_rate_str
        elif session_opened and post_rate_seq_raw:
            seq = [x.strip() for x in post_rate_seq_raw.split(",") if x.strip()]
            rate_str = seq[min(post_count - 1, len(seq) - 1)]
        elif session_opened and post_rate_str is not None:
            rate_str = post_rate_str
        elif session_opened and (state_dir / "card.txt").is_file() and                 (state_dir / "card.txt").read_text(encoding="utf-8").strip() != "CPU":
            # A GPU session bills at its card's rate once open (an A100 High-RAM read 8.88/hr on
            # 2026-11-06): the account rate the fake reports once a GPU session is open.
            rate_str = os.environ.get("FAKE_COLAB_GPU_RATE_STR", "8.88/hr")
        else:
            rate_str = os.environ.get("FAKE_COLAB_RATE_STR", "0.26/hr")
        # FAKE_COLAB_ASSIGNMENTS_SEQ: the post-open "Active assignments" counts, one per post-open
        # usage call (the last repeats), stepped with FAKE_COLAB_POST_OPEN_RATE_SEQ. Default 1;
        # OMITLINE drops the line.
        assignments = "1"
        assign_seq_raw = os.environ.get("FAKE_COLAB_ASSIGNMENTS_SEQ")
        if session_opened and assign_seq_raw:
            aseq = [x.strip() for x in assign_seq_raw.split(",") if x.strip()]
            assignments = aseq[min(post_count - 1, len(aseq) - 1)]
        # FAKE_COLAB_OPEN_REGISTERING=1: the session-registration fixture. The first three post-open
        # reads print "Usage rate: 0.00/hr" with "Active assignments: 0", then the card's rate with
        # count 1. Source: receipt windowC2-12-t4-s1a-20261027, whose post-open reads show 0.00 with
        # 0 assignments until the session registered, then 1.07/hr with 1.
        if session_opened and os.environ.get("FAKE_COLAB_OPEN_REGISTERING") == "1":
            if post_count <= 3:
                rate_str, assignments = "0.00/hr", "0"
            elif not assign_seq_raw:
                assignments = "1"
        count_line = "" if assignments == "OMITLINE" else f"Active assignments: {assignments}"
        if rate_str == "OMIT":
            print(f"Current balance: {bal} compute units")
            print(count_line)
            return 0
        print(f"Current balance: {bal} compute units")
        print(f"Usage rate: {rate_str}")
        print(count_line)
        return 0

    if subcmd == "sessions":
        if (state_dir / "stops.log").exists() and os.environ.get("FAKE_COLAB_SESSIONS_CLOSE_HANG") in ("1", "ignore_term"):
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_SESSIONS_CLOSE_HANG") == "ignore_term")
        with (state_dir / "sessions.log").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("SESSION_LIST_AFTER_STOP\n")
        # FAKE_COLAB_SESSIONS_EMPTY=1: the server lists nothing, even for an open session.
        rows = []
        if os.environ.get("FAKE_COLAB_SESSIONS_EMPTY") != "1":
            for f in sorted(_open_sessions_dir(state_dir).glob("*.json")):
                rec = json.loads(f.read_text(encoding="utf-8"))
                row = SESSIONS_ROW_TEMPLATE.format(**rec)
                if rec["shape"] == "OMIT":
                    row = row.replace(" | Shape: OMIT", "")
                rows.append(row)
        if not rows:
            print(EMPTY_SESSIONS_LINE)
        for row in rows:
            print(row)
        return 0

    if subcmd == "new":
        sid = _get_opt("-s", "--session")
        if not sid:
            sys.stderr.write("colab new requires -s/--session\n")
            return 2
        held = False
        if Path(f"{lock_file}.held").exists() or Path(f"{lock_file}.lockdir").is_dir():
            held = True
        elif shutil.which("flock") and lock_file.exists():
            res = subprocess.run(["flock", "-n", str(lock_file), "-c", "true"], check=False)
            held = res.returncode != 0
        with (state_dir / "lock.log").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"LOCK_HELD={1 if held else 0}\n")
        (state_dir / "session_opened.txt").write_text("1\n", encoding="utf-8", newline="\n")
        (state_dir / "card.txt").write_text((_get_opt("--gpu") or "CPU") + "\n", encoding="utf-8", newline="\n")
        gpu = _get_opt("--gpu")
        (_open_sessions_dir(state_dir) / f"{sid}.json").write_text(
            json.dumps({
                "sid": sid,
                "hw": gpu.upper() if gpu else "CPU",
                "shape": _session_shape_label(gpu, "--high-mem" in parsed_opts),
                "variant": "GPU" if gpu else "DEFAULT",
            }) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        # FAKE_COLAB_NEW_DELAY_S: the open takes this long; the moment it succeeds is logged.
        if os.environ.get("FAKE_COLAB_NEW_HANG") in ("1", "ignore_term"):
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_NEW_HANG") == "ignore_term")
        time.sleep(float(os.environ.get("FAKE_COLAB_NEW_DELAY_S", "0")))
        (state_dir / "new_done_epoch.txt").write_text(f"{time.time()}\n", encoding="utf-8", newline="\n")
        lane_tag = "lane3" if "l3" in sid or "lane3" in sid else "lane1"
        print(
            f"Opened tunnel https://colab.research.google.com/tun?colab-runtime-proxy-token=secret_proxy_tok_{lane_tag}_999&port=8188"
        )
        print(f"OAuth access_token=ya29.secret_oauth_{lane_tag}_888")
        return 0

    if subcmd == "upload":
        sid = _get_opt("-s", "--session")
        if not sid:
            sys.stderr.write("colab upload requires -s/--session\n")
            return 2
        upload_hang = os.environ.get("FAKE_COLAB_UPLOAD_HANG", "")
        upload_hang_for = os.environ.get("FAKE_COLAB_UPLOAD_HANG_FOR", "")
        if upload_hang in ("1", "ignore_term") and (not upload_hang_for or upload_hang_for in positionals[1]):
            _hang_process(state_dir, upload_hang == "ignore_term")
        api = contract["contents_api"]
        local_src, remote_dst = positionals[0], _normalize_remote_content_path(positionals[1])
        src_path = _normalize_host_path(local_src)
        if not src_path.is_file():
            print(api["upload_local_missing_line"].format(local=local_src))
            return 1
        if not remote_dst.startswith("/content/"):
            sys.stderr.write(f"Remote path must be under /content/: {remote_dst}\n")
            return 1
        rel = remote_dst.removeprefix("/content/")
        dst_path = content_dir / rel
        # One contents-API PUT, as the real CLI does: no parent directory is ever created, and a PUT
        # into one that does not exist fails on the server (HTTP 500), exit 1.
        # FAKE_COLAB_UPLOAD_HTTP_500_FOR=<substring>: the same server error for a matching remote path.
        forced_500 = os.environ.get("FAKE_COLAB_UPLOAD_HTTP_500_FOR", "")
        if not dst_path.parent.is_dir() or (forced_500 and forced_500 in remote_dst):
            status = api["upload_missing_parent_http_status"]
            print(
                api["upload_failed_prefix"]
                + f"{status} Server Error: Internal Server Error for url: "
                + f"https://colab.fake.invalid/api/contents/{remote_dst.strip('/')}"
                + f"?authuser=0&colab-runtime-proxy-token={FAKE_CONTENTS_TOKEN}"
            )
            with (state_dir / "uploads.log").open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"UPLOAD_FAILED_{status} {' '.join(args)}\n")
            return 1
        shutil.copyfile(src_path, dst_path)
        # Keep the uploaded script at `<name>.uploaded` and install the fake stub runner at `<name>`
        # unless `FAKE_COLAB_RUN_UPLOADED_SCRIPT=1` is requested.
        if rel in ("remote_lane1_stub.sh", "remote_lane3_stub.sh") and os.environ.get("FAKE_COLAB_RUN_UPLOADED_SCRIPT") != "1":
            shutil.copyfile(src_path, content_dir / f"{rel}.uploaded")
            fake_stub = content_dir / f".fake_{rel}"
            if fake_stub.is_file():
                shutil.copyfile(fake_stub, dst_path)
        with (state_dir / "uploads.log").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"UPLOAD_OK {' '.join(args)}\n")
        print(api["upload_ok_line"].format(local=local_src, remote=positionals[1]))
        return 0

    if subcmd == "download":
        sid = _get_opt("-s", "--session")
        if not sid:
            sys.stderr.write("colab download requires -s/--session\n")
            return 2
        dl_cnt_f = state_dir / "download_attempts.txt"
        dl_cnt = int(dl_cnt_f.read_text(encoding="utf-8").strip()) if dl_cnt_f.is_file() else 0
        dl_cnt += 1
        dl_cnt_f.write_text(f"{dl_cnt}\n", encoding="utf-8", newline="\n")
        if os.environ.get("FAKE_COLAB_DOWNLOAD_HANG_ONCE") in ("1", "ignore_term") and dl_cnt == 1:
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_DOWNLOAD_HANG_ONCE") == "ignore_term")
        if os.environ.get("FAKE_COLAB_DOWNLOAD_FAIL_ONCE") == "1" and dl_cnt == 1:
            api = contract["contents_api"]
            print(
                api["download_failed_prefix"]
                + "500 Server Error: Internal Server Error for url: "
                + f"https://colab.fake.invalid/api/contents/{positionals[0].strip('/')}"
                + f"?authuser=0&colab-runtime-proxy-token={FAKE_CONTENTS_TOKEN}"
            )
            return 1
        if os.environ.get("FAKE_COLAB_DOWNLOAD_HANG") in ("1", "ignore_term"):
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_DOWNLOAD_HANG") == "ignore_term")
        remote_src, local_dst = _normalize_remote_content_path(positionals[0]), positionals[1]
        if not remote_src.startswith("/content/"):
            sys.stderr.write(f"Remote path must be under /content/: {remote_src}\n")
            return 1
        api = contract["contents_api"]
        rel = remote_src.removeprefix("/content/")
        vm_src = content_dir / rel
        dst_path = _normalize_host_path(local_dst)
        if not vm_src.is_file():
            print(api["download_failed_prefix"] + api["download_missing_remote_error"].format(remote=positionals[0]))
            return 1
        # The real CLI writes with a plain open(): no local directory is created.
        if not dst_path.parent.is_dir():
            print(api["download_failed_prefix"] + f"[Errno 2] No such file or directory: '{local_dst}'")
            return 1
        shutil.copyfile(vm_src, dst_path)
        print(api["download_ok_line"].format(remote=positionals[0], local=local_dst))
        return 0

    if subcmd == "stop":
        sid = _get_opt("-s", "--session")
        if not sid:
            sys.stderr.write("colab stop requires -s/--session\n")
            return 2
        stop_cnt_f = state_dir / "stop_attempts.txt"
        stop_cnt = int(stop_cnt_f.read_text(encoding="utf-8").strip()) if stop_cnt_f.is_file() else 0
        stop_cnt += 1
        stop_cnt_f.write_text(f"{stop_cnt}\n", encoding="utf-8", newline="\n")
        if os.environ.get("FAKE_COLAB_STOP_HANG_ONCE") in ("1", "ignore_term") and stop_cnt == 1:
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_STOP_HANG_ONCE") == "ignore_term")
        if os.environ.get("FAKE_COLAB_STOP_HANG_ALWAYS") in ("1", "ignore_term"):
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_STOP_HANG_ALWAYS") == "ignore_term")
        with (state_dir / "stops.log").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"STOP {' '.join(args)}\n")
        with (state_dir / "stops.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"sid": sid, "attempt": stop_cnt, "done_ts": time.time()}) + "\n")
        (_open_sessions_dir(state_dir) / f"{sid}.json").unlink(missing_ok=True)
        _kill_recorded_groups(state_dir, sid)
        _kernel_file(state_dir, sid, "pid").unlink(missing_ok=True)
        return 0

    if subcmd == "restart-kernel":
        sid = _get_opt("-s", "--session")
        if not sid:
            sys.stderr.write("colab restart-kernel requires -s/--session\n")
            return 2
        if os.environ.get("FAKE_COLAB_RESTART_HANG") in ("1", "ignore_term"):
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_RESTART_HANG") == "ignore_term")
        # The kernel process ends (and with it the running cell); processes the cell spawned in
        # its own process group are left alone. stop() still ends them with the VM.
        import signal as _signal

        cell = _running_cell(state_dir, sid)
        if cell is not None:
            try:
                os.kill(cell, _signal.SIGKILL)
            except OSError:
                pass
            for _ in range(100):
                if not _pid_alive(cell):
                    break
                time.sleep(0.05)
        _kernel_file(state_dir, sid, "pid").unlink(missing_ok=True)
        with (state_dir / "restarts.log").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"RESTART -s {sid} cell={cell}\n")
        if os.environ.get("FAKE_COLAB_RESTART_DELAY_S"):
            time.sleep(float(os.environ["FAKE_COLAB_RESTART_DELAY_S"]))
        return 0

    if subcmd == "exec":
        sid = _get_opt("-s", "--session")
        py_file = _get_opt("-f", "--file")
        if not sid or not py_file:
            sys.stderr.write("colab exec requires -s/--session and -f/--file\n")
            return 2
        if "lane3_bundle_now.py" in py_file and os.environ.get("FAKE_COLAB_BUNDLE_NOW_HANG") in ("1", "ignore_term"):
            _hang_process(state_dir, os.environ.get("FAKE_COLAB_BUNDLE_NOW_HANG") == "ignore_term")
        py_path = _normalize_host_path(py_file)
        if not py_path.is_file() or py_path.suffix != ".py":
            sys.stderr.write(f"colab exec -f must be an existing .py file: {py_file}\n")
            return 2
        timeout_raw = _get_opt("--timeout")
        try:
            timeout_s = float(timeout_raw) if timeout_raw is not None else 30.0
        except ValueError:
            sys.stderr.write(f"Invalid --timeout: {timeout_raw}\n")
            return 2
        if timeout_s <= 0:
            sys.stderr.write(f"Invalid --timeout: {timeout_raw}\n")
            return 2

        env_vars: dict[str, str] = {}
        for kv in parsed_opts.get("--env", []):
            if "=" not in kv:
                sys.stderr.write(f"Invalid --env (expected KEY=VALUE): {kv}\n")
                return 2
            k, v = kv.split("=", 1)
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
                sys.stderr.write(f"Invalid --env key: {k}\n")
                return 2
            v_norm = _normalize_remote_content_path(v)
            if v_norm.startswith("/content/"):
                rel_v = v_norm.removeprefix("/content/")
                mapped = content_dir / rel_v
                env_vars[k] = _to_posix(mapped) if k == "SDLAB_REMOTE_SCRIPT" else str(mapped)
            elif v_norm == "/content":
                env_vars[k] = str(content_dir)
            else:
                env_vars[k] = v

        # Build isolated kernel environment: strip rig-side PINNED_*, LANE3_* and SDLAB_* (except
        # SDLAB_PYTHON) so the remote runner only sees what was passed via --env, and set
        # UV_SYSTEM_PYTHON=1 to match Colab.
        kernel_env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("PINNED_")
            and not k.startswith("LANE3_")
            and (not k.startswith("SDLAB_") or k == "SDLAB_PYTHON")
            and k not in ("HF_TOKEN", "HF_TOKEN_GGUF_READ", "HUGGING_FACE_HUB_TOKEN")
        }
        kernel_env.setdefault("UV_SYSTEM_PYTHON", "1")
        # The fake GPU VM's stand-ins for the lane's torch, bitsandbytes and huggingface_hub.
        kernel_env["FAKE_VM_SITE"] = str(FIXTURES_DIR / "fake_vm_site")
        kernel_env.update(env_vars)

        env_lines = "".join(f"os.environ[{k!r}] = {v!r}\n" for k, v in env_vars.items())
        code_logged = "import os\n" + env_lines + py_path.read_text(encoding="utf-8")

        # Execute the local .py file's source in a simulated IPython kernel cell:
        # cwd is the fake /content directory, __file__ is undefined, and --env values are applied.
        kernel_code = (
            "import os, pathlib, sys\n"
            "sys.argv = ['colab_kernel_launcher.py']\n"
            f"src = pathlib.Path({str(py_path.resolve())!r}).read_text(encoding='utf-8')\n"
            "ns = {'__name__': '__main__'}\n"
            "assert '__file__' not in ns\n"
            "rc = 0\n"
            "try:\n"
            "    exec(compile(src, '<colab-cell>', 'exec'), ns)\n"
            "except SystemExit as exc:\n"
            "    rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)\n"
            "except BaseException:\n"
            "    import traceback; traceback.print_exc(); rc = 1\n"
            "finally:\n"
            "    pathlib.Path(os.environ['RC_PATH']).write_text(str(rc))\n"
        )
        (state_dir / "kernels").mkdir(exist_ok=True)
        (state_dir / "cells").mkdir(exist_ok=True)
        deadline = time.monotonic() + timeout_s
        # One kernel per session: wait for a running cell to finish (or for restart-kernel/stop).
        while _running_cell(state_dir, sid) is not None:
            if time.monotonic() > deadline:
                sys.stderr.write(f"Execution timed out after {timeout_s}s (a cell is still running on the kernel)\n")
                return 124
            time.sleep(0.05)
        cell_n = len(list((state_dir / "cells").glob("*.out")))
        out_path = state_dir / "cells" / f"{cell_n:04d}.out"
        rc_path = state_dir / "cells" / f"{cell_n:04d}.rc"
        py = _resolve_python()
        argv = [py, "-u", "-c", kernel_code]
        cell_env = dict(kernel_env)
        cell_env["RC_PATH"] = str(rc_path)
        cell = _spawn_detached(argv, cell_env, content_dir, out_path)
        _kernel_file(state_dir, sid, "pid").write_text(f"{cell}\n", encoding="utf-8")
        with _kernel_file(state_dir, sid, "pgids").open("a", encoding="utf-8") as fh:
            fh.write(f"{os.getpgid(cell)}\n")

        pos = 0
        timed_out = False
        with out_path.open("rb") as fh:
            while True:
                chunk = fh.read()
                if chunk:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.flush()
                    pos += len(chunk)
                if not _pid_alive(cell):
                    rest = fh.read()
                    if rest:
                        sys.stdout.buffer.write(rest)
                        sys.stdout.flush()
                    break
                if time.monotonic() > deadline:
                    timed_out = True
                    break
                time.sleep(0.05)
        if timed_out:
            # As the real client: the local call gives up, the cell keeps running on the kernel.
            sys.stderr.write(f"Execution timed out after {timeout_s}s\n")
            return 124
        if _running_cell(state_dir, sid) == cell:
            _kernel_file(state_dir, sid, "pid").unlink(missing_ok=True)
        # History keeps the code (with the --env lines) and the outputs (execution.py:262-272).
        outputs = out_path.read_text(encoding="utf-8", errors="replace")
        history = state_dir / "history"
        history.mkdir(exist_ok=True)
        with (history / f"{sid}.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"code": code_logged, "outputs": [{"output_type": "stream", "text": outputs}]}) + "\n")

        # On the real Colab CLI, cell execution exit codes are not reliably propagated as CLI exit code
        if os.environ.get("FAKE_COLAB_FORCE_EXEC_RC_ZERO", "1") == "1":
            return 0
        try:
            return int(rc_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
