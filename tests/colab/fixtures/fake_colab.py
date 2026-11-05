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
  `/content` directory, `__file__` undefined, and the `--env` values applied.
"""

from __future__ import annotations

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
    lock_file = tmp_path / "colab-window-open.lock"

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
    return bin_dir, state_dir, env


def _write_fake_remote_scripts(content_dir: Path) -> None:
    lane1_body = """#!/usr/bin/env bash
set -euo pipefail
: "${PINNED_UV_VERSION:?missing PINNED_UV_VERSION}"
: "${PINNED_PYTHON_VERSION:?missing PINNED_PYTHON_VERSION}"
: "${PINNED_PYTORCH_INDEX_URL:?missing PINNED_PYTORCH_INDEX_URL}"
: "${PINNED_COMFYUI_REPO:?missing PINNED_COMFYUI_REPO}"
: "${PINNED_COMFYUI_COMMIT:?missing PINNED_COMFYUI_COMMIT}"
: "${PINNED_COMFY_HEADLESS_SPEC:?missing PINNED_COMFY_HEADLESS_SPEC}"

mode="${FAKE_COLAB_MODE:-success}"
if [ "${mode}" = "fail" ]; then
  echo "Simulated remote failure with colab-runtime-proxy-token=secret_proxy_tok_lane1_999" >&2
  exit 42
elif [ "${mode}" = "wall" ]; then
  echo "Simulated hung child ignoring inner timeout"
  for _ in $(seq 1 40); do
    sleep 0.2
  done
  exit 0
elif [ "${mode}" = "dead_harness" ]; then
  echo "=== VITALS 2026-11-05T12:01:00Z ==="
  echo "CGROUP_MEM: oom_kill 0"
  echo "MEM: MemTotal: 13290000 kB"
  echo "PROC:"
  echo 'HARNESS: {"phase": "run", "step": 1}'
  echo "=== VITALS 2026-11-05T12:01:15Z ==="
  echo "CGROUP_MEM: oom_kill 0"
  echo "MEM: MemTotal: 13290000 kB"
  echo "PROC:"
  echo 'HARNESS: {"phase": "run", "step": 1}'
  for _ in $(seq 1 60); do
    sleep 0.2
  done
  exit 0
elif [ "${mode}" = "stall" ] || [ "${mode}" = "cap_burn" ] || [ "${mode}" = "usage_fail_midrun" ]; then
  echo "=== VITALS 2026-11-05T12:00:00Z ==="
  echo "MEM: MemTotal: 13290000 kB"
  echo "PROC:"
  echo "101 python3 /content/ComfyUI/main.py --cpu --listen 127.0.0.1"
  echo 'HARNESS: {"phase": "run", "step": 1}'
  for _ in $(seq 1 60); do
    sleep 0.2
  done
  exit 0
fi

echo "=== VITALS 2026-11-05T12:00:00Z ==="
echo "CGROUP_MEM_CURRENT: 536870912"
echo "CGROUP_MEM_MAX: 12884901888"
echo "MEM: MemTotal: 12582912 kB"
echo "PROC:"
echo "101 python3 /content/ComfyUI/main.py --cpu --listen 127.0.0.1"
echo 'HARNESS: {"phase": "run", "step": 1}'
echo 'WINDOW_JSON {"system_python": "3.13.16", "python": "3.15.1", "python_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "uv": "uv 0.13.5", "comfyui_commit": "158419f3a0017c2ce123484b14b6c527716d6ec8", "comfy_headless_version": "3.1.0", "comfy_bind": "127.0.0.1:8188", "listening_sockets": ["127.0.0.1:8188"]}'
echo "LANE1_STUB_OK python=3.15.1 comfy_bind=127.0.0.1:8188 resume_hash_match=true"
printf 'FAKE_TAR_BYTES' > lane1_stub_bundle.tar.gz
"""
    lane3_body = """#!/usr/bin/env bash
set -euo pipefail
: "${PINNED_UV_VERSION:?missing PINNED_UV_VERSION}"
: "${PINNED_PYTHON_VERSION:?missing PINNED_PYTHON_VERSION}"
: "${PINNED_PYTORCH_INDEX_URL:?missing PINNED_PYTORCH_INDEX_URL}"
: "${PINNED_AI_TOOLKIT_REPO:?missing PINNED_AI_TOOLKIT_REPO}"
: "${PINNED_AI_TOOLKIT_COMMIT:?missing PINNED_AI_TOOLKIT_COMMIT}"

mode="${FAKE_COLAB_MODE:-success}"
if [ "${mode}" = "fail" ]; then
  echo "Simulated remote failure with colab-runtime-proxy-token=secret_proxy_tok_lane3_999" >&2
  exit 42
elif [ "${mode}" = "wall" ]; then
  echo "Simulated hung child ignoring inner timeout"
  for _ in $(seq 1 40); do
    sleep 0.2
  done
  exit 0
elif [ "${mode}" = "dead_harness" ]; then
  echo "=== VITALS 2026-11-05T12:01:00Z ==="
  echo "CGROUP_MEM: oom_kill 0"
  echo "MEM: MemTotal: 13290000 kB"
  echo "PROC:"
  echo 'HARNESS: {"phase": "run", "step": 1}'
  echo "=== VITALS 2026-11-05T12:01:15Z ==="
  echo "CGROUP_MEM: oom_kill 0"
  echo "MEM: MemTotal: 13290000 kB"
  echo "PROC:"
  echo 'HARNESS: {"phase": "run", "step": 1}'
  for _ in $(seq 1 60); do
    sleep 0.2
  done
  exit 0
elif [ "${mode}" = "stall" ] || [ "${mode}" = "cap_burn" ] || [ "${mode}" = "usage_fail_midrun" ]; then
  echo "=== VITALS 2026-11-05T12:00:00Z ==="
  echo "MEM: MemTotal: 13290000 kB"
  echo "PROC:"
  echo "101 python3 /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml"
  echo 'HARNESS: {"phase": "run", "step": 1}'
  for _ in $(seq 1 60); do
    sleep 0.2
  done
  exit 0
fi

echo "=== VITALS 2026-11-05T12:00:00Z ==="
echo "CGROUP_MEM_CURRENT: 536870912"
echo "CGROUP_MEM_MAX: 12884901888"
echo "MEM: MemTotal: 12582912 kB"
echo "PROC:"
echo "101 python3 /content/ai-toolkit/run.py /content/lane3_out/synth_job.yaml"
echo 'HARNESS: {"phase": "run", "step": 1}'
echo 'WINDOW_JSON {"system_python": "3.13.16", "python": "3.15.1", "python_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "uv": "uv 0.13.5", "ai_toolkit_commit": "73ebae1334d2c98089f1b90f8cb19257825f891a", "override_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "checkpoint_path": "/content/lane3_out/checkpoints/synth_lora.safetensors"}'
echo "LANE3_STUB_OK python=3.15.1 sentencepiece=0.2.1 checkpoint_written=true"
printf 'FAKE_TAR_BYTES' > lane3_stub_bundle.tar.gz
"""
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
        raw_override = os.environ.get("FAKE_COLAB_USAGE_TEXT")
        if raw_override is not None:
            print(raw_override)
            return 0
        bal = "9.75" if (mode == "cap_burn" and c >= 2) else os.environ.get("FAKE_COLAB_BALANCE", "9.85")
        rate_str = os.environ.get("FAKE_COLAB_RATE_STR", "0.26/hr")
        print(f"Current balance: {bal} compute units")
        print(f"Usage rate: {rate_str}")
        print("Active assignments: 1")
        return 0

    if subcmd == "sessions":
        with (state_dir / "sessions.log").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("SESSION_LIST_AFTER_STOP\n")
        print(EMPTY_SESSIONS_LINE)
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
        local_src, remote_dst = positionals[0], _normalize_remote_content_path(positionals[1])
        src_path = _normalize_host_path(local_src)
        if not src_path.is_file():
            sys.stderr.write(f"Local file not found: {local_src}\n")
            return 1
        if not remote_dst.startswith("/content/"):
            sys.stderr.write(f"Remote path must be under /content/: {remote_dst}\n")
            return 1
        rel = remote_dst.removeprefix("/content/")
        dst_path = content_dir / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
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
        return 0

    if subcmd == "download":
        sid = _get_opt("-s", "--session")
        if not sid:
            sys.stderr.write("colab download requires -s/--session\n")
            return 2
        remote_src, local_dst = _normalize_remote_content_path(positionals[0]), positionals[1]
        if not remote_src.startswith("/content/"):
            sys.stderr.write(f"Remote path must be under /content/: {remote_src}\n")
            return 1
        rel = remote_src.removeprefix("/content/")
        vm_src = content_dir / rel
        dst_path = _normalize_host_path(local_dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if vm_src.is_file():
            shutil.copyfile(vm_src, dst_path)
        else:
            dst_path.write_bytes(b"FAKE_TAR_BYTES")
        return 0

    if subcmd == "stop":
        sid = _get_opt("-s", "--session")
        if not sid:
            sys.stderr.write("colab stop requires -s/--session\n")
            return 2
        with (state_dir / "stops.log").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"STOP {' '.join(args)}\n")
        return 0

    if subcmd == "exec":
        sid = _get_opt("-s", "--session")
        py_file = _get_opt("-f", "--file")
        if not sid or not py_file:
            sys.stderr.write("colab exec requires -s/--session and -f/--file\n")
            return 2
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

        # Build isolated kernel environment: strip rig-side PINNED_* and SDLAB_* (except SDLAB_PYTHON)
        # so the remote runner only sees what was passed via --env.
        kernel_env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("PINNED_")
            and (not k.startswith("SDLAB_") or k == "SDLAB_PYTHON")
        }
        kernel_env.update(env_vars)

        # Execute the local .py file's source in a simulated IPython kernel cell:
        # cwd is the fake /content directory, __file__ is undefined, and --env values are applied.
        kernel_code = (
            "import os, pathlib, sys\n"
            "sys.argv = ['colab_kernel_launcher.py']\n"
            f"src = pathlib.Path({str(py_path.resolve())!r}).read_text(encoding='utf-8')\n"
            "ns = {'__name__': '__main__'}\n"
            "assert '__file__' not in ns\n"
            "exec(compile(src, '<colab-cell>', 'exec'), ns)\n"
        )
        try:
            proc = subprocess.run(
                [_resolve_python(), "-u", "-c", kernel_code],
                stdin=subprocess.DEVNULL,
                env=kernel_env,
                cwd=str(content_dir),
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(f"Execution timed out after {timeout_s}s\n")
            return 124

        # On the real Colab CLI, cell execution exit codes are not reliably propagated as CLI exit code
        if os.environ.get("FAKE_COLAB_FORCE_EXEC_RC_ZERO", "1") == "1":
            return 0
        return int(proc.returncode)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
