"""Regression tests for atomic phase.txt writers, last-known-phase vitals readers, and PR #74 B2."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
LANE1_LAUNCHER = COLAB_DIR / "launch_lane1_stub.sh"
LANE3_LAUNCHER = COLAB_DIR / "launch_lane3_stub.sh"
PROBE_LAUNCHER = COLAB_DIR / "probe_upload_limit.sh"
TESTS_COLAB_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_COLAB_DIR / "fixtures"

for _p in (COLAB_DIR, FIXTURES_DIR, TESTS_COLAB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fake_colab as fc  # noqa: E402
import launch_guards as lg  # noqa: E402
import test_launch_lane1_stub as t_l1  # noqa: E402


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _p(path: Path) -> str:
    return fc._to_posix(path)


def _emit_remote_lane1(tmp_dir: Path) -> str:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = LANE1_LAUNCHER.read_text(encoding="utf-8")
    start_marker = 'cat > "${REMOTE_RUNNER}" << REMOTEEOF\n'
    end_marker = "\nREMOTEEOF\n"
    assert start_marker in src and end_marker in src
    heredoc = src.split(start_marker, 1)[1].split(end_marker, 1)[0]
    out_sh = tmp_dir / "emitted_remote_lane1_stub.sh"
    gen_sh = tmp_dir / "gen_lane1_remote.sh"
    gen_sh.write_text(
        f'set -euo pipefail\nREMOTE_RUNNER="{_p(out_sh)}"\n'
        + start_marker
        + heredoc
        + end_marker,
        encoding="utf-8",
        newline="\n",
    )
    res = subprocess.run(
        [_bash(), _p(gen_sh)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    return out_sh.read_text(encoding="utf-8")


def _emit_remote_lane3(tmp_dir: Path) -> str:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_sh = tmp_dir / "emitted_remote_lane3_stub.sh"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SDLAB_", "FAKE_COLAB", "EXPECTED_"))}
    res = subprocess.run(
        [_bash(), _p(LANE3_LAUNCHER), "--emit-remote-script", _p(out_sh)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    return out_sh.read_text(encoding="utf-8")


def _extract_vitals_loop(remote_script: str, lane: str) -> str:
    setup_marker = f": > /content/{lane}_out/setup.log\n"
    end_marker = '\nVITALS_PID="$!"'
    assert setup_marker in remote_script and end_marker in remote_script
    subshell = remote_script.split(setup_marker, 1)[1].split(end_marker, 1)[0]
    assert subshell.endswith(") &"), f"Unexpected vitals subshell tail: {subshell[-80:]!r}"
    assert "\n    sleep 15\n" in subshell
    subshell = subshell[:-2].rstrip()  # strip background `&` so outer script waits cleanly
    return subshell.replace("\n    sleep 15\n", "\n    _sdlab_tick_gate\n")


def _wait_for_file(path: Path, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {path}")


@pytest.mark.parametrize("lane", ["lane1", "lane3"])
def test_real_vitals_readers_keep_last_known_phase_on_mid_tick_truncate_and_partial_write(
    tmp_path: Path, lane: str
) -> None:
    remote_script = _emit_remote_lane1(tmp_path) if lane == "lane1" else _emit_remote_lane3(tmp_path)
    vitals_body = _extract_vitals_loop(remote_script, lane)

    vm_root = tmp_path / "vm_content"
    out_dir = vm_root / f"{lane}_out"
    gate_dir = tmp_path / "gates"
    out_dir.mkdir(parents=True)
    gate_dir.mkdir(parents=True)
    (out_dir / "setup.log").write_text("setup ok\n", encoding="utf-8")
    phase_file = out_dir / "phase.txt"
    vitals_log = out_dir / "vitals.log"

    # Dummy worker script matching launch_guards.WORKER_PROC_RE during phase=run ticks.
    worker_name = "main.py" if lane == "lane1" else "run.py"
    worker_py = tmp_path / "w" / worker_name
    worker_py.parent.mkdir(parents=True)
    worker_py.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")

    driver_sh = tmp_path / f"run_{lane}_vitals.sh"
    driver_sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'GATE_DIR="{_p(gate_dir)}"\n'
        "_TICK=0\n"
        "_sdlab_tick_gate() {\n"
        "  _TICK=$(( _TICK + 1 ))\n"
        '  : > "${GATE_DIR}/.tick_done_${_TICK}"\n'
        '  while [ ! -f "${GATE_DIR}/.tick_allow_$(( _TICK + 1 ))" ]; do\n'
        '    if [ -f "${GATE_DIR}/.stop" ]; then\n'
        "      exit 0\n"
        "    fi\n"
        "    sleep 0.01\n"
        "  done\n"
        "}\n"
        'while [ ! -f "${GATE_DIR}/.tick_allow_1" ]; do\n'
        '  if [ -f "${GATE_DIR}/.stop" ]; then\n'
        "    exit 0\n"
        "  fi\n"
        "  sleep 0.01\n"
        "done\n"
        + vitals_body.replace("/content", _p(vm_root))
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    proc = subprocess.Popen(
        [_bash(), _p(driver_sh)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    worker_proc: subprocess.Popen[str] | None = None
    try:
        steps: list[tuple[str, bytes | None, str, bool]] = [
            ("setup", b"setup\n", "setup", False),
            ("start_run", b"run\n", "run", True),
            ("mid_tick_truncate", b"", "run", True),
            ("partial_no_newline", b"bun", "run", True),
            ("partial_with_newline", b"bun\n", "run", True),
            ("enter_bundle", b"bundle\n", "bundle", False),
            ("bundle_truncate", b"", "bundle", False),
            ("missing_file", None, "bundle", False),
        ]

        for tick_idx, (label, payload, expected_phase, want_worker) in enumerate(steps, start=1):
            if want_worker and worker_proc is None:
                worker_proc = subprocess.Popen(
                    [sys.executable, str(worker_py)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif not want_worker and worker_proc is not None:
                worker_proc.terminate()
                worker_proc.wait(timeout=10)
                worker_proc = None

            if payload is None:
                phase_file.unlink(missing_ok=True)
            else:
                phase_file.write_bytes(payload)

            (gate_dir / f".tick_allow_{tick_idx}").touch()
            _wait_for_file(gate_dir / f".tick_done_{tick_idx}")

            vitals_text = vitals_log.read_text(encoding="utf-8")
            samples = lg.parse_vitals_log(vitals_text)
            assert len(samples) == tick_idx, f"{lane} {label}: expected {tick_idx} samples, got {len(samples)}"
            guard = lg.evaluate_vitals_and_stall_guard(
                vitals_text=vitals_text,
                idle_seconds=0.0,
                setup_idle_seconds=0.0,
                stall_s=300.0,
                setup_stall_s=600.0,
            )
            assert guard["tripped"] is False, f"{lane} {label}: unexpected trip {guard}"
            assert guard["code"] is None, f"{lane} {label}: unexpected code {guard}"
            assert samples[-1]["phase"] == expected_phase, (
                f"{lane} {label}: expected phase {expected_phase!r}, got {samples[-1]['phase']!r}"
            )

        (gate_dir / ".stop").touch()
        stdout_txt, stderr_txt = proc.communicate(timeout=20)
        assert proc.returncode == 0, f"STDERR:\n{stderr_txt}\nSTDOUT:\n{stdout_txt}"
        assert stderr_txt == "", f"Expected clean stderr even on missing phase.txt, got:\n{stderr_txt}"
    finally:
        if worker_proc is not None:
            worker_proc.terminate()
            try:
                worker_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker_proc.kill()
        if proc.poll() is None:
            (gate_dir / ".stop").touch()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_all_phase_txt_writers_are_atomic_and_concurrent_writes_never_tear(tmp_path: Path) -> None:
    remote_l1 = _emit_remote_lane1(tmp_path / "l1")
    remote_l3 = _emit_remote_lane3(tmp_path / "l3")

    # 1. Static check across production scripts and fake_colab fixture: zero direct truncating writers.
    bad_l1 = [ln.strip() for ln in remote_l1.splitlines() if re.search(r'>\s*/content/lane1_out/phase\.txt\b', ln)]
    assert bad_l1 == [], f"Found truncating redirect in remote_lane1_stub.sh: {bad_l1}"
    bad_l3 = [ln.strip() for ln in remote_l3.splitlines() if re.search(r'>\s*/content/lane3_out/phase\.txt\b', ln)]
    assert bad_l3 == [], f"Found truncating redirect in remote_lane3_stub.sh: {bad_l3}"

    l1_atomic = [ln.strip() for ln in remote_l1.splitlines() if 'mv -f "/content/lane1_out/.phase.txt.tmp.$$" /content/lane1_out/phase.txt' in ln]
    l3_atomic = [ln.strip() for ln in remote_l3.splitlines() if 'mv -f "/content/lane3_out/.phase.txt.tmp.$$" /content/lane3_out/phase.txt' in ln]
    assert len(l1_atomic) == 6, f"Expected 6 atomic writers in remote_lane1_stub.sh, got {len(l1_atomic)}"
    assert len(l3_atomic) == 3, f"Expected 3 atomic writers in remote_lane3_stub.sh, got {len(l3_atomic)}"

    bundle_now_src = (COLAB_DIR / "lane1_bundle_now.py").read_text(encoding="utf-8")
    assert '(out / "phase.txt").write_' not in bundle_now_src
    assert 'os.replace(phase_tmp, out / "phase.txt")' in bundle_now_src

    fake_src = (FIXTURES_DIR / "fake_colab.py").read_text(encoding="utf-8")
    assert "> lane1_out/phase.txt" not in fake_src
    assert "> lane3_out/phase.txt" not in fake_src

    # 2. Drive the real extracted shell atomic writer lines concurrently under tight Python observation.
    vm_root = tmp_path / "stress_vm"
    (vm_root / "lane1_out").mkdir(parents=True)
    (vm_root / "lane3_out").mkdir(parents=True)
    l1_phase = vm_root / "lane1_out" / "phase.txt"
    l1_phase.write_bytes(b"setup\n")
    l3_phase = vm_root / "lane3_out" / "phase.txt"
    l3_phase.write_bytes(b"setup\n")

    stress_cmds = [ln.replace("/content", _p(vm_root)) for ln in (*l1_atomic, *l3_atomic)]
    stress_sh = tmp_path / "stress_writers.sh"
    stress_sh.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nfor _ in $(seq 1 40); do\n"
        + "\n".join(f"  {cmd}" for cmd in stress_cmds)
        + "\ndone\n",
        encoding="utf-8",
        newline="\n",
    )

    observed_bad: list[tuple[str, bytes]] = []
    reads_done = 0
    stop_readers = threading.Event()

    def _tight_reader() -> None:
        nonlocal reads_done
        valid = {b"setup\n", b"run\n", b"bundle\n"}
        while not stop_readers.is_set():
            for name, pf in (("lane1", l1_phase), ("lane3", l3_phase)):
                try:
                    data = pf.read_bytes()
                except FileNotFoundError as exc:
                    observed_bad.append((name, repr(exc).encode()))
                    continue
                reads_done += 1
                if data not in valid:
                    observed_bad.append((name, data))

    reader_thread = threading.Thread(target=_tight_reader, daemon=True)
    reader_thread.start()
    try:
        res = subprocess.run(
            [_bash(), _p(stress_sh)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        stop_readers.set()
        reader_thread.join(timeout=5)

    assert res.returncode == 0, res.stderr
    assert reads_done > 0
    assert observed_bad == [], f"Observed non-atomic phase.txt reads: {observed_bad[:5]}"
    leftover_tmp = [p.name for p in (vm_root / "lane1_out").iterdir() if p.name.startswith(".phase.txt.tmp")]
    leftover_tmp += [p.name for p in (vm_root / "lane3_out").iterdir() if p.name.startswith(".phase.txt.tmp")]
    assert leftover_tmp == [], f"Leftover temp phase files: {leftover_tmp}"


def test_b2_fake_colab_empty_phase_window_reproduces_rc_93_on_d00ecbd_and_passes_at_head(tmp_path: Path) -> None:
    fx = t_l1._make_render_fixture(tmp_path / "fx_b2_phase")
    env = fx["env"]
    env["FAKE_VM_RENDER_ARCHIVE_S"] = "2.5"
    env["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.05"
    env["GUARD_POLL_INTERVAL_S"] = "0.1"

    content_dir = fx["state_dir"] / "content"
    archiving_flag = content_dir / ".fake-vm-archiving"
    phase_file = content_dir / "lane1_out" / "phase.txt"
    stop_injector = threading.Event()
    injected = threading.Event()

    def _inject_empty_phase() -> None:
        while not stop_injector.is_set():
            if archiving_flag.is_file() and phase_file.is_file():
                # Allow one initial tick after archive starts, then hold phase.txt empty across several ticks.
                time.sleep(0.15)
                if not stop_injector.is_set():
                    phase_file.write_bytes(b"")
                    injected.set()
                    time.sleep(0.60)
                    if not stop_injector.is_set():
                        phase_file.write_bytes(b"bundle\n")
                return
            time.sleep(0.02)

    injector = threading.Thread(target=_inject_empty_phase, daemon=True)
    injector.start()
    out_dir = tmp_path / "out_b2_phase"
    try:
        res = t_l1._run_launcher(
            [*fx["base_args"], "--out-dir", _p(out_dir), "--session", "sdlab-b2-empty-phase"],
            env,
            timeout=300,
        )
    finally:
        stop_injector.set()
        injector.join(timeout=5)

    assert injected.is_set(), "empty-phase injector never fired during archive window"
    guards_txt = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert res.returncode == 0, f"RC={res.returncode}\nSTDERR:\n{res.stderr[-2000:]}\nGUARDS:\n{guards_txt[-2000:]}"
    assert "VITALS_PHASE_UNREADABLE" not in guards_txt


def test_b2_fake_colab_spawn_detached_fast_exec_and_probe_under_single_core_contention(tmp_path: Path) -> None:
    bin_dir, state_dir, env = fc.make_fake_colab_env(tmp_path / "fx_spawn")
    noop_py = tmp_path / "noop.py"
    noop_py.write_text("pass\n", encoding="utf-8")
    colab_bin = str(bin_dir / "colab")

    old_affinity: set[int] | None = None
    if hasattr(os, "sched_getaffinity") and hasattr(os, "sched_setaffinity"):
        cur = os.sched_getaffinity(0)
        if len(cur) > 1:
            old_affinity = cur
            os.sched_setaffinity(0, {min(cur)})

    stop_spinners = threading.Event()
    spinners: list[threading.Thread] = []

    def _burn_cpu() -> None:
        x = 0
        while not stop_spinners.is_set():
            x = (x + 1) & 0xFFFF

    for _ in range(4):
        t = threading.Thread(target=_burn_cpu, daemon=True)
        t.start()
        spinners.append(t)

    try:
        new_res = subprocess.run(
            [colab_bin, "new", "-s", "sdlab-b2-fast"],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
        )
        assert new_res.returncode == 0, new_res.stderr

        for i in range(25):
            ex = subprocess.run(
                [colab_bin, "exec", "-s", "sdlab-b2-fast", "-f", str(noop_py), "--timeout", "30"],
                env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
            )
            assert ex.returncode == 0, f"fast exec #{i} failed rc={ex.returncode}: {ex.stderr}"
            assert "FileNotFoundError" not in ex.stderr and "ProcessLookupError" not in ex.stderr

        stop_res = subprocess.run(
            [colab_bin, "stop", "-s", "sdlab-b2-fast"],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
        )
        assert stop_res.returncode == 0, stop_res.stderr

        _, probe_state, probe_env = fc.make_fake_colab_env(tmp_path / "fx_probe")
        probe_env["GUARD_POLL_INTERVAL_S"] = "0.5"
        probe_env["FAKE_COLAB_UPLOAD_MAX_BYTES"] = str(int(2.5 * 1024 * 1024))
        probe_env["FAKE_COLAB_DOWNLOAD_MAX_BYTES"] = str(5 * 1024 * 1024)
        probe_out = tmp_path / "out_probe"
        probe_res = subprocess.run(
            [
                _bash(), _p(PROBE_LAUNCHER),
                "--out-dir", _p(probe_out),
                "--session", "sdlab-b2-probe",
                "--cap", "0.20",
                "--wall-s", "600",
                "--grace-s", "30",
                "--upload-sizes-mb", "3",
                "--download-sizes-mb", "6",
            ],
            env=probe_env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert probe_res.returncode == 0, f"probe failed:\nSTDOUT:\n{probe_res.stdout}\nSTDERR:\n{probe_res.stderr}"
        receipt = json.loads((probe_out / "probe_upload_limit.json").read_text(encoding="utf-8"))
        assert receipt["uploads"][0]["http_status"] == 500
        assert receipt["downloads"][0]["http_status"] == 500
        assert "STOP -s sdlab-b2-probe" in (probe_state / "stops.log").read_text(encoding="utf-8")
    finally:
        stop_spinners.set()
        for t in spinners:
            t.join(timeout=2)
        if old_affinity is not None:
            os.sched_setaffinity(0, old_affinity)
