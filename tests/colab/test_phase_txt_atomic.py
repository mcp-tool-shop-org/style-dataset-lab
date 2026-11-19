"""Regression tests for atomic phase.txt writers, last-known-phase vitals readers, and PR #74 B2."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import threading
import time
import unittest.mock
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
import lane1_bundle_now as lbn  # noqa: E402
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
            ("partial_setup_no_newline", b"set", "run", True),
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


def _extract_phase_writer_lines(remote_script: str, lane: str) -> list[str]:
    target = f"/content/{lane}_out/phase.txt"
    return [
        ln.strip()
        for ln in remote_script.splitlines()
        if target in ln and ("mv -f " in ln or re.search(rf">\s*{re.escape(target)}\b", ln))
    ]


def test_all_phase_txt_writers_are_atomic_and_concurrent_writes_never_tear(tmp_path: Path) -> None:
    remote_l1 = _emit_remote_lane1(tmp_path / "l1")
    remote_l3 = _emit_remote_lane3(tmp_path / "l3")

    l1_writers = _extract_phase_writer_lines(remote_l1, "lane1")
    l3_writers = _extract_phase_writer_lines(remote_l3, "lane3")
    assert len(l1_writers) == 6, f"Expected 6 writers in remote_lane1_stub.sh, got {len(l1_writers)}"
    assert len(l3_writers) == 3, f"Expected 3 writers in remote_lane3_stub.sh, got {len(l3_writers)}"

    # 1. Drive all 9 extracted shell writers truly concurrently in parallel bash processes under
    # tight Python observation (run first so a regression fails the dynamic stress check too).
    vm_root = tmp_path / "stress_vm"
    (vm_root / "lane1_out").mkdir(parents=True)
    (vm_root / "lane3_out").mkdir(parents=True)
    l1_phase = vm_root / "lane1_out" / "phase.txt"
    l1_phase.write_bytes(b"setup\n")
    l3_phase = vm_root / "lane3_out" / "phase.txt"
    l3_phase.write_bytes(b"setup\n")

    start_gate = tmp_path / "stress_start.gate"
    writer_procs: list[tuple[int, subprocess.Popen[str]]] = []
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

    reader_threads = [threading.Thread(target=_tight_reader, daemon=True) for _ in range(2)]
    for rt in reader_threads:
        rt.start()
    try:
        for idx, raw_ln in enumerate((*l1_writers, *l3_writers)):
            cmd = raw_ln.replace("/content", _p(vm_root))
            w_sh = tmp_path / f"stress_writer_{idx}.sh"
            w_sh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f'while [ ! -f "{_p(start_gate)}" ]; do sleep 0.005; done\n'
                "for _ in $(seq 1 40); do\n"
                f"  {cmd}\n"
                "done\n",
                encoding="utf-8",
                newline="\n",
            )
            writer_procs.append(
                (
                    idx,
                    subprocess.Popen(
                        [_bash(), _p(w_sh)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    ),
                )
            )
        start_gate.touch()
        for idx, wp in writer_procs:
            _, w_err = wp.communicate(timeout=60)
            assert wp.returncode == 0, f"writer #{idx} failed rc={wp.returncode}: {w_err}"
    finally:
        start_gate.touch()
        stop_readers.set()
        for _, wp in writer_procs:
            if wp.poll() is None:
                wp.kill()
        for rt in reader_threads:
            rt.join(timeout=5)

    assert reads_done > 0
    assert observed_bad == [], f"Observed non-atomic phase.txt reads: {observed_bad[:5]}"
    leftover_tmp = [p.name for p in (vm_root / "lane1_out").iterdir() if p.name.startswith(".phase.txt.tmp")]
    leftover_tmp += [p.name for p in (vm_root / "lane3_out").iterdir() if p.name.startswith(".phase.txt.tmp")]
    assert leftover_tmp == [], f"Leftover temp phase files: {leftover_tmp}"

    # 2. Static check across production scripts and fake_colab fixture: zero direct truncating writers,
    # explicit loud-fail handling on every writer, and exact match between written phases and reader case.
    bad_l1 = [ln.strip() for ln in remote_l1.splitlines() if re.search(r'>\s*/content/lane1_out/phase\.txt\b', ln)]
    assert bad_l1 == [], f"Found truncating redirect in remote_lane1_stub.sh: {bad_l1}"
    bad_l3 = [ln.strip() for ln in remote_l3.splitlines() if re.search(r'>\s*/content/lane3_out/phase\.txt\b', ln)]
    assert bad_l3 == [], f"Found truncating redirect in remote_lane3_stub.sh: {bad_l3}"

    l1_atomic = [ln.strip() for ln in remote_l1.splitlines() if 'mv -f "/content/lane1_out/.phase.txt.tmp.$$" /content/lane1_out/phase.txt' in ln]
    l3_atomic = [ln.strip() for ln in remote_l3.splitlines() if 'mv -f "/content/lane3_out/.phase.txt.tmp.$$" /content/lane3_out/phase.txt' in ln]
    assert len(l1_atomic) == 6, f"Expected 6 atomic writers in remote_lane1_stub.sh, got {len(l1_atomic)}"
    assert len(l3_atomic) == 3, f"Expected 3 atomic writers in remote_lane3_stub.sh, got {len(l3_atomic)}"

    l1_salvage = [ln for ln in l1_atomic if "best-effort on-exit write" in ln]
    l1_strict = [ln for ln in l1_atomic if "best-effort on-exit write" not in ln]
    assert len(l1_salvage) == 1
    assert "PHASE_WRITE_FAILED: best-effort on-exit write" in l1_salvage[0] and "preserving rc=" in l1_salvage[0]
    assert len(l1_strict) == 5
    for ln in (*l1_strict, *l3_atomic):
        assert "REFUSED: PHASE_WRITE_FAILED" in ln and "exit 77" in ln, f"Writer missing loud fail: {ln}"

    written_words: set[str] = set()
    for ln in (*l1_atomic, *l3_atomic):
        m_word = re.search(r"printf '([a-z]+)\\n'", ln)
        assert m_word, f"Could not parse phase word from writer: {ln}"
        written_words.add(m_word.group(1))

    bundle_now_src = (COLAB_DIR / "lane1_bundle_now.py").read_text(encoding="utf-8")
    assert '(out / "phase.txt").write_' not in bundle_now_src
    assert 'os.replace(phase_tmp, out / "phase.txt")' in bundle_now_src
    assert "REFUSED: PHASE_WRITE_FAILED" in bundle_now_src
    for m_bw in re.finditer(r'write_bytes\(b"([a-z]+)\\n"\)', bundle_now_src):
        written_words.add(m_bw.group(1))
    assert written_words == set(lg.VALID_HARNESS_PHASES)

    case_arm = "|".join(lg.VALID_HARNESS_PHASES) + ")"
    assert case_arm in remote_l1 and "REFUSED: VITALS_PHASE_INVALID" in remote_l1 and "exit 78" in remote_l1
    assert case_arm in remote_l3 and "REFUSED: VITALS_PHASE_INVALID" in remote_l3 and "exit 78" in remote_l3

    fake_src = (FIXTURES_DIR / "fake_colab.py").read_text(encoding="utf-8")
    assert "> lane1_out/phase.txt" not in fake_src
    assert "> lane3_out/phase.txt" not in fake_src


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


def test_b2_fake_colab_spawn_detached_ongoing_coverage_does_not_reproduce_d00ecbd(tmp_path: Path) -> None:
    """Ongoing coverage for fake_colab._spawn_detached + probe_upload_limit under single-core contention.

    Labelled explicitly (PR #85 review C4): this test ALSO passes on d00ecbd's fixture (where
    os.waitpid(pid1, 0) in _spawn_detached gives grandchild pid2 enough scheduling slack on Linux
    ext4 to open out_path before the parent reads it) and therefore does NOT reproduce the d00ecbd
    race; it provides ongoing stress coverage under single-CPU pinning.
    """
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


def test_b1_launcher_stops_with_phase_write_failed_on_readonly_out_dir(tmp_path: Path) -> None:
    # 1. Stub mode: making lane1_out read-only after scrub stops the bundle phase write loudly (rc=77),
    # never producing a tar or leaving a silent stale phase.
    _, state_stub, env_stub = fc.make_fake_colab_env(tmp_path / "fx_b1_stub")
    env_stub["FAKE_VM_READONLY_OUT_AFTER_SCRUB"] = "1"
    env_stub["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_stub = tmp_path / "out_b1_stub"
    vm_out_stub = state_stub / "content" / "lane1_out"
    try:
        res_stub = t_l1._run_launcher(
            ["--out-dir", _p(out_stub), "--session", "sdlab-b1-stub-ro"],
            env_stub,
            timeout=300,
        )
    finally:
        if vm_out_stub.is_dir():
            vm_out_stub.chmod(0o755)

    assert res_stub.returncode == 77, f"STDERR:\n{res_stub.stderr[-2000:]}\nSTDOUT:\n{res_stub.stdout[-2000:]}"
    win_stub = json.loads((out_stub / "window.json").read_text(encoding="utf-8"))
    assert win_stub["status"] == "PHASE_WRITE_FAILED"
    assert win_stub["refusal_code"] == "PHASE_WRITE_FAILED"
    assert "REFUSED: PHASE_WRITE_FAILED" in (out_stub / "vitals.log").read_text(encoding="utf-8")
    assert not (out_stub / "lane1_stub_bundle.tar.gz").exists()

    # 2. --render mode (plus salvage kept read-only): primary bundle write fails loudly (rc=77),
    # best-effort on-exit write logs PHASE_WRITE_FAILED while preserving rc=77, and lane1_bundle_now.py
    # during salvage also fails loudly with PHASE_WRITE_FAILED / SDLAB_BUNDLE_NOW_RC=77.
    fx = t_l1._make_render_fixture(tmp_path / "fx_b1_render")
    env_ren = fx["env"]
    env_ren["FAKE_VM_READONLY_OUT_AFTER_SCRUB"] = "1"
    env_ren["FAKE_VM_KEEP_READONLY_FOR_SALVAGE"] = "1"
    env_ren["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.2"
    env_ren["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_ren = tmp_path / "out_b1_render"
    vm_out_ren = fx["state_dir"] / "content" / "lane1_out"
    try:
        res_ren = t_l1._run_launcher(
            [*fx["base_args"], "--out-dir", _p(out_ren), "--session", "sdlab-b1-render-ro"],
            env_ren,
            timeout=300,
        )
    finally:
        if vm_out_ren.is_dir():
            vm_out_ren.chmod(0o755)

    assert res_ren.returncode == 77, f"STDERR:\n{res_ren.stderr[-2000:]}\nSTDOUT:\n{res_ren.stdout[-2000:]}"
    win_ren = json.loads((out_ren / "window.json").read_text(encoding="utf-8"))
    assert win_ren["status"] == "PHASE_WRITE_FAILED"
    assert win_ren["refusal_code"] == "PHASE_WRITE_FAILED"
    vitals_ren = (out_ren / "vitals.log").read_text(encoding="utf-8")
    guards_ren = (out_ren / "guards.log").read_text(encoding="utf-8")
    bundle_now_ren = (out_ren / "bundle_now.log").read_text(encoding="utf-8")
    assert "REFUSED: PHASE_WRITE_FAILED" in vitals_ren
    assert "PHASE_WRITE_FAILED: best-effort on-exit write" in vitals_ren
    assert "DEAD_HARNESS_TRIPPED" not in guards_ren
    assert "REFUSED: PHASE_WRITE_FAILED" in bundle_now_ren
    assert "SDLAB_BUNDLE_NOW_RC=77" in bundle_now_ren


def test_b1_every_writer_and_lane1_bundle_now_fail_loudly_on_temp_write_and_rename_failure(tmp_path: Path) -> None:
    remote_l1 = _emit_remote_lane1(tmp_path / "emit_l1")
    remote_l3 = _emit_remote_lane3(tmp_path / "emit_l3")
    l1_writers = _extract_phase_writer_lines(remote_l1, "lane1")
    l3_writers = _extract_phase_writer_lines(remote_l3, "lane3")

    def _is_salvage(ln: str) -> bool:
        return "best-effort on-exit write" in ln or ln.startswith("(")

    salvage_writers = [("lane1", ln) for ln in l1_writers if _is_salvage(ln)]
    strict_writers = [
        *(("lane1", ln) for ln in l1_writers if not _is_salvage(ln)),
        *(("lane3", ln) for ln in l3_writers),
    ]
    assert len(salvage_writers) == 1
    assert len(strict_writers) == 8

    # 1. All 8 strict writers fail loudly (rc=77, REFUSED: PHASE_WRITE_FAILED, zero leftover temp)
    # under both `set -euo pipefail` and `set +e`, on both temp-write failure and rename failure.
    for idx, (lane, raw_ln) in enumerate(strict_writers):
        for set_opts in ("set -euo pipefail", "set +e"):
            # (a) Temp write failure (read-only output dir)
            vm_ro = tmp_path / f"strict_{idx}_{set_opts.replace(' ', '_')}_ro"
            out_ro = vm_ro / f"{lane}_out"
            out_ro.mkdir(parents=True)
            pf_ro = out_ro / "phase.txt"
            pf_ro.write_bytes(b"run\n")
            sh_ro = vm_ro / "run.sh"
            sh_ro.write_text(
                f"#!/usr/bin/env bash\n{set_opts}\n{raw_ln.replace('/content', _p(vm_ro))}\necho REACHED_AFTER\n",
                encoding="utf-8",
                newline="\n",
            )
            out_ro.chmod(0o555)
            try:
                res_ro = subprocess.run(
                    [_bash(), _p(sh_ro)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            finally:
                out_ro.chmod(0o755)
            assert res_ro.returncode == 77, f"{lane} strict #{idx} ({set_opts}) ro rc={res_ro.returncode}: {res_ro.stderr}"
            assert "REFUSED: PHASE_WRITE_FAILED" in res_ro.stderr
            assert "REACHED_AFTER" not in res_ro.stdout
            assert pf_ro.read_bytes() == b"run\n"
            assert [p.name for p in out_ro.iterdir() if p.name.startswith(".phase.txt.tmp")] == []

            # (b) Rename failure (printf succeeds writing temp file, then mv fails)
            vm_mv = tmp_path / f"strict_{idx}_{set_opts.replace(' ', '_')}_mv"
            out_mv = vm_mv / f"{lane}_out"
            out_mv.mkdir(parents=True)
            pf_mv = out_mv / "phase.txt"
            pf_mv.write_bytes(b"run\n")
            mv_bin = vm_mv / "bin"
            mv_bin.mkdir()
            real_mv = shutil.which("mv")
            assert real_mv
            mv_wrap = mv_bin / "mv"
            mv_wrap.write_text(
                "#!/usr/bin/env bash\n"
                'case " $* " in\n'
                '  *phase.txt*) echo "mv: simulated rename failure" >&2; exit 1 ;;\n'
                "esac\n"
                f'exec "{real_mv}" "$@"\n',
                encoding="utf-8",
                newline="\n",
            )
            mv_wrap.chmod(0o755)
            sh_mv = vm_mv / "run.sh"
            sh_mv.write_text(
                f"#!/usr/bin/env bash\n{set_opts}\n{raw_ln.replace('/content', _p(vm_mv))}\necho REACHED_AFTER\n",
                encoding="utf-8",
                newline="\n",
            )
            mv_env = {**os.environ, "PATH": f"{_p(mv_bin)}:{os.environ.get('PATH', '')}"}
            res_mv = subprocess.run(
                [_bash(), _p(sh_mv)],
                env=mv_env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert res_mv.returncode == 77, f"{lane} strict #{idx} ({set_opts}) mv rc={res_mv.returncode}: {res_mv.stderr}"
            assert "REFUSED: PHASE_WRITE_FAILED" in res_mv.stderr
            assert "REACHED_AFTER" not in res_mv.stdout
            assert pf_mv.read_bytes() == b"run\n"
            assert [p.name for p in out_mv.iterdir() if p.name.startswith(".phase.txt.tmp")] == []

    # 2. The on-exit salvage writer remains best-effort while still logging PHASE_WRITE_FAILED and cleaning temp.
    sal_lane, sal_ln = salvage_writers[0]
    vm_sal_ro = tmp_path / "sal_ro"
    out_sal_ro = vm_sal_ro / f"{sal_lane}_out"
    out_sal_ro.mkdir(parents=True)
    sh_sal_ro = vm_sal_ro / "run.sh"
    sh_sal_ro.write_text(
        f"#!/usr/bin/env bash\nset -euo pipefail\nrc=76\n{sal_ln.replace('/content', _p(vm_sal_ro))}\n",
        encoding="utf-8",
        newline="\n",
    )
    out_sal_ro.chmod(0o555)
    try:
        res_sal_ro = subprocess.run(
            [_bash(), _p(sh_sal_ro)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        out_sal_ro.chmod(0o755)
    assert res_sal_ro.returncode == 0, res_sal_ro.stderr
    assert "PHASE_WRITE_FAILED: best-effort on-exit write" in res_sal_ro.stderr
    assert "preserving rc=76" in res_sal_ro.stderr
    assert [p.name for p in out_sal_ro.iterdir() if p.name.startswith(".phase.txt.tmp")] == []

    vm_sal_mv = tmp_path / "sal_mv"
    out_sal_mv = vm_sal_mv / f"{sal_lane}_out"
    out_sal_mv.mkdir(parents=True)
    sal_mv_bin = vm_sal_mv / "bin"
    sal_mv_bin.mkdir()
    real_mv_sal = shutil.which("mv")
    assert real_mv_sal
    sal_mv_wrap = sal_mv_bin / "mv"
    sal_mv_wrap.write_text(
        "#!/usr/bin/env bash\n"
        'case " $* " in\n'
        '  *phase.txt*) echo "mv: simulated rename failure" >&2; exit 1 ;;\n'
        "esac\n"
        f'exec "{real_mv_sal}" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    sal_mv_wrap.chmod(0o755)
    sh_sal_mv = vm_sal_mv / "run.sh"
    sh_sal_mv.write_text(
        f"#!/usr/bin/env bash\nset -euo pipefail\nrc=76\n{sal_ln.replace('/content', _p(vm_sal_mv))}\n",
        encoding="utf-8",
        newline="\n",
    )
    sal_mv_env = {**os.environ, "PATH": f"{_p(sal_mv_bin)}:{os.environ.get('PATH', '')}"}
    res_sal_mv = subprocess.run(
        [_bash(), _p(sh_sal_mv)],
        env=sal_mv_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res_sal_mv.returncode == 0, res_sal_mv.stderr
    assert "PHASE_WRITE_FAILED: best-effort on-exit write" in res_sal_mv.stderr
    assert [p.name for p in out_sal_mv.iterdir() if p.name.startswith(".phase.txt.tmp")] == []

    # 3. lane1_bundle_now.py (__main__) fails loudly (rc=77, REFUSED: PHASE_WRITE_FAILED, SDLAB_BUNDLE_NOW_RC=77)
    # on both read-only lane1_out and os.replace failure, never creating a tar with a stale phase.
    bundle_now_py = COLAB_DIR / "lane1_bundle_now.py"
    for mode_tag in ("ro", "mv"):
        content = tmp_path / f"bn_{mode_tag}"
        out_bn = content / "lane1_out"
        out_bn.mkdir(parents=True)
        (out_bn / "renders.jsonl").write_text('{"job_id":"r1","status":"ok"}\n', encoding="utf-8")
        shutil.copyfile(COLAB_DIR / "lane1_render.py", content / "lane1_render.py")
        shutil.copyfile(COLAB_DIR / "lane3_rung.py", content / "lane3_rung.py")
        shutil.copyfile(COLAB_DIR / "launch_guards.py", content / "launch_guards.py")
        if mode_tag == "ro":
            (out_bn / "phase.txt").write_bytes(b"run\n")
            out_bn.chmod(0o555)
        else:
            (out_bn / "phase.txt" / "blocker").mkdir(parents=True)
        bn_env = {**os.environ, "SDLAB_CONTENT": str(content), "SDLAB_BUNDLE_RC": "143"}
        try:
            bn_res = subprocess.run(
                [sys.executable, str(bundle_now_py)],
                env=bn_env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                inproc_rc = lbn.bundle_now(bn_env)
            assert inproc_rc == 77
            assert "SDLAB_BUNDLE_NOW_RC=77" in buf_out.getvalue()
            assert "REFUSED: PHASE_WRITE_FAILED" in buf_err.getvalue()
            if mode_tag == "ro":
                main_out = io.StringIO()
                main_err = io.StringIO()
                with (
                    unittest.mock.patch.dict(os.environ, bn_env, clear=False),
                    contextlib.redirect_stdout(main_out),
                    contextlib.redirect_stderr(main_err),
                    pytest.raises(SystemExit) as exc_info,
                ):
                    runpy.run_path(str(bundle_now_py), run_name="__main__")
                assert exc_info.value.code == 77
                assert "SDLAB_BUNDLE_NOW_RC=77" in main_out.getvalue()
                assert "REFUSED: PHASE_WRITE_FAILED" in main_err.getvalue()
        finally:
            if mode_tag == "ro":
                out_bn.chmod(0o755)
        assert bn_res.returncode == 77, f"bundle_now ({mode_tag}) rc={bn_res.returncode}: {bn_res.stderr}"
        assert "REFUSED: PHASE_WRITE_FAILED" in bn_res.stderr
        assert "SDLAB_BUNDLE_NOW_RC=77" in bn_res.stdout
        assert not (content / "lane1_render_bundle.tar.gz").exists()
        assert [p.name for p in out_bn.iterdir() if p.name.startswith(".phase.txt.tmp")] == []


def _leftover_vitals_loops(fx_root: Path, *, settle_s: float = 5.0) -> list[str]:
    """Processes still running the fake's extracted vitals script (`.real_vitals_lane<N>.sh`) from under `fx_root`,
    after waiting up to `settle_s` for them to go. Identified by command line and working directory, read from /proc;
    on a host without /proc (not Linux) there is nothing to read and the list is empty."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    want = str(fx_root.resolve())

    def _scan() -> list[str]:
        found: list[str] = []
        for d in proc_root.iterdir():
            if not d.name.isdigit():
                continue
            try:
                cmd = (d / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
                if ".real_vitals_lane" not in cmd:
                    continue
                cwd = os.readlink(d / "cwd")
            except OSError:
                continue
            if cwd.startswith(want):
                found.append(f"{d.name}: {cmd.strip()} (cwd {cwd})")
        return found

    deadline = time.monotonic() + settle_s
    left = _scan()
    while left and time.monotonic() < deadline:
        time.sleep(0.1)
        left = _scan()
    return left


@pytest.mark.parametrize("lane", ["lane1", "lane3"])
def test_b2_stuck_run_and_stuck_setup_with_empty_reads_interleaved_trip_on_time_via_real_launchers(
    tmp_path: Path, lane: str
) -> None:
    launcher = LANE1_LAUNCHER if lane == "lane1" else LANE3_LAUNCHER

    # 1. Phase stuck at `run` with empty and partial reads interleaved still trips STALL_GUARD_TRIPPED on time.
    _, _, env_run = fc.make_fake_colab_env(tmp_path / f"fx_{lane}_run")
    env_run["FAKE_COLAB_MODE"] = "real_vitals_stuck_run"
    env_run["STALL_S"] = "4"
    env_run["SETUP_STALL_S"] = "30"
    env_run["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_run["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.15"
    out_run = tmp_path / f"out_{lane}_run"
    t0_run = time.monotonic()
    res_run = subprocess.run(
        [_bash(), _p(launcher), "--out-dir", _p(out_run), "--session", f"sdlab-b2-{lane}-stuck-run", "--wall-s", "60", "--grace-s", "10"],
        env=env_run,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    elapsed_run = time.monotonic() - t0_run
    assert res_run.returncode == 93, f"STDERR:\n{res_run.stderr[-2000:]}\nSTDOUT:\n{res_run.stdout[-2000:]}"
    win_run = json.loads((out_run / "window.json").read_text(encoding="utf-8"))
    guards_run = (out_run / "guards.log").read_text(encoding="utf-8")
    vitals_run = (out_run / "vitals.log").read_text(encoding="utf-8")
    assert win_run["status"] == "STALL_GUARD_TRIPPED"
    assert win_run["refusal_code"] == "STALL_GUARD_TRIPPED"
    assert "VITALS_PHASE_UNREADABLE" not in guards_run
    assert "DEAD_HARNESS_TRIPPED" not in guards_run
    samples_run = lg.parse_vitals_log(vitals_run)
    run_samples = [s for s in samples_run if s["phase"] == "run"]
    assert any(s["phase"] == "setup" for s in samples_run)
    assert len(run_samples) >= 5
    assert all(s["phase"] in lg.VALID_HARNESS_PHASES for s in samples_run)
    assert all(s["worker_proc_count"] >= 1 for s in run_samples)
    trip_recs_run = [json.loads(ln) for ln in guards_run.splitlines() if ln.startswith("{") and '"STALL_GUARD_TRIPPED"' in ln]
    assert trip_recs_run
    m_idle_run = re.search(r"for\s+([0-9.]+)s\b", trip_recs_run[-1]["reason"])
    assert m_idle_run and float(m_idle_run.group(1)) >= 4.0
    assert 3.0 <= elapsed_run < 30.0
    # No vitals loop of this run outlives the launcher. (The PR #87 review asked whether the fake's EXIT trap, which
    # signals only the wrapper shell, leaves the forked loop behind. It does not on these paths: the loops are seen
    # running during the window and are gone when the launcher returns. This pins that.)
    assert _leftover_vitals_loops(tmp_path / f"fx_{lane}_run") == []

    # 2. Phase stuck at `setup` with empty and partial reads interleaved still trips SETUP_STALL_TRIPPED on time.
    _, _, env_setup = fc.make_fake_colab_env(tmp_path / f"fx_{lane}_setup")
    env_setup["FAKE_COLAB_MODE"] = "real_vitals_stuck_setup"
    env_setup["SETUP_STALL_S"] = "4"
    env_setup["STALL_S"] = "30"
    env_setup["GUARD_POLL_INTERVAL_S"] = "0.2"
    env_setup["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.15"
    out_setup = tmp_path / f"out_{lane}_setup"
    t0_setup = time.monotonic()
    res_setup = subprocess.run(
        [_bash(), _p(launcher), "--out-dir", _p(out_setup), "--session", f"sdlab-b2-{lane}-stuck-setup", "--wall-s", "60", "--grace-s", "10"],
        env=env_setup,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    elapsed_setup = time.monotonic() - t0_setup
    assert res_setup.returncode == 93, f"STDERR:\n{res_setup.stderr[-2000:]}\nSTDOUT:\n{res_setup.stdout[-2000:]}"
    win_setup = json.loads((out_setup / "window.json").read_text(encoding="utf-8"))
    guards_setup = (out_setup / "guards.log").read_text(encoding="utf-8")
    vitals_setup = (out_setup / "vitals.log").read_text(encoding="utf-8")
    assert win_setup["status"] == "SETUP_STALL_TRIPPED"
    assert win_setup["refusal_code"] == "SETUP_STALL_TRIPPED"
    assert "VITALS_PHASE_UNREADABLE" not in guards_setup
    samples_setup = lg.parse_vitals_log(vitals_setup)
    setup_samples = [s for s in samples_setup if s["phase"] == "setup"]
    assert len(setup_samples) >= 5
    assert all(s["phase"] == "setup" for s in samples_setup)
    trip_recs_setup = [json.loads(ln) for ln in guards_setup.splitlines() if ln.startswith("{") and '"SETUP_STALL_TRIPPED"' in ln]
    assert trip_recs_setup
    m_idle_setup = re.search(r"for\s+([0-9.]+)s\b", trip_recs_setup[-1]["reason"])
    assert m_idle_setup and float(m_idle_setup.group(1)) >= 4.0
    assert 3.0 <= elapsed_setup < 30.0
    assert _leftover_vitals_loops(tmp_path / f"fx_{lane}_setup") == []


def test_c3_readers_refuse_unknown_phase_word_with_vitals_phase_invalid(tmp_path: Path) -> None:
    # 1. Both real VM vitals readers refuse any complete phase word other than setup/run/bundle (rc=78).
    for lane in ("lane1", "lane3"):
        for bad_word in (b"train\n", b"bun\n"):
            sub = tmp_path / f"vm_{lane}_{bad_word.decode().strip()}"
            remote_script = _emit_remote_lane1(sub / "emit") if lane == "lane1" else _emit_remote_lane3(sub / "emit")
            vitals_body = _extract_vitals_loop(remote_script, lane)
            vm_root = sub / "vm_content"
            out_dir = vm_root / f"{lane}_out"
            gate_dir = sub / "gates"
            out_dir.mkdir(parents=True)
            gate_dir.mkdir(parents=True)
            (out_dir / "setup.log").write_text("setup ok\n", encoding="utf-8")
            phase_file = out_dir / "phase.txt"
            vitals_log = out_dir / "vitals.log"
            driver_sh = sub / "driver.sh"
            driver_sh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f'GATE_DIR="{_p(gate_dir)}"\n'
                "_TICK=0\n"
                "_sdlab_tick_gate() {\n"
                "  _TICK=$(( _TICK + 1 ))\n"
                '  : > "${GATE_DIR}/.tick_done_${_TICK}"\n'
                '  while [ ! -f "${GATE_DIR}/.tick_allow_$(( _TICK + 1 ))" ]; do\n'
                '    [ -f "${GATE_DIR}/.stop" ] && exit 0\n'
                "    sleep 0.01\n"
                "  done\n"
                "}\n"
                'while [ ! -f "${GATE_DIR}/.tick_allow_1" ]; do\n'
                '  [ -f "${GATE_DIR}/.stop" ] && exit 0\n'
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
            try:
                phase_file.write_bytes(b"setup\n")
                (gate_dir / ".tick_allow_1").touch()
                _wait_for_file(gate_dir / ".tick_done_1")
                phase_file.write_bytes(bad_word)
                (gate_dir / ".tick_allow_2").touch()
                deadline_t2 = time.monotonic() + 10.0
                while time.monotonic() < deadline_t2:
                    if proc.poll() is not None:
                        break
                    if (gate_dir / ".tick_done_2").is_file():
                        (gate_dir / ".stop").touch()
                        break
                    time.sleep(0.01)
                out_txt, err_txt = proc.communicate(timeout=20)
            finally:
                if proc.poll() is None:
                    (gate_dir / ".stop").touch()
                    proc.kill()
            assert proc.returncode == 78, f"{lane} {bad_word!r}: rc={proc.returncode} err={err_txt} out={out_txt}"
            assert "REFUSED: VITALS_PHASE_INVALID" in err_txt
            vitals_txt = vitals_log.read_text(encoding="utf-8")
            assert "REFUSED: VITALS_PHASE_INVALID" in vitals_txt
            guard = lg.evaluate_vitals_and_stall_guard(
                vitals_text=vitals_txt,
                idle_seconds=0.0,
                setup_idle_seconds=0.0,
                stall_s=300.0,
                setup_stall_s=600.0,
            )
            assert guard["tripped"] is True and guard["code"] == "VITALS_PHASE_INVALID"

    # 2. Rig-side launch_guards refuses unknown phase words (including suffix words and earlier samples).
    for bad_phase in ("train", "eval", "bun", "setup_extra"):
        v_txt = f"=== VITALS 2026-11-19T00:00:00Z ===\nSETUP_BYTES: 10\nPROC:\nHARNESS: {{\"phase\": \"{bad_phase}\"}}\n"
        res = lg.evaluate_vitals_and_stall_guard(vitals_text=v_txt, idle_seconds=0.0, setup_idle_seconds=0.0)
        assert res["tripped"] is True and res["code"] == "VITALS_PHASE_INVALID"

        v_hist = v_txt + '=== VITALS 2026-11-19T00:00:15Z ===\nSETUP_BYTES: 10\nPROC:\nHARNESS: {"phase": "bundle"}\n'
        res_hist = lg.evaluate_vitals_and_stall_guard(vitals_text=v_hist, idle_seconds=0.0, setup_idle_seconds=0.0)
        assert res_hist["tripped"] is True and res_hist["code"] == "VITALS_PHASE_INVALID"

        vf = tmp_path / f"vitals_{bad_phase}.log"
        vf.write_text(v_txt, encoding="utf-8")
        assert lg.main(["--vitals-file", str(vf), "--idle-seconds", "0", "--setup-idle-seconds", "0"]) == 1

    # 3. Full launchers on fake CLI refuse an unknown phase word and record VITALS_PHASE_INVALID in window.json.
    for lane, launcher in (("lane1", LANE1_LAUNCHER), ("lane3", LANE3_LAUNCHER)):
        _, _, env_inv = fc.make_fake_colab_env(tmp_path / f"fx_{lane}_inv")
        env_inv["FAKE_COLAB_MODE"] = "real_vitals_invalid_phase"
        env_inv["FAKE_INVALID_PHASE_WORD"] = "train"
        env_inv["GUARD_POLL_INTERVAL_S"] = "0.2"
        env_inv["FAKE_COLAB_VITALS_INTERVAL_S"] = "0.1"
        # bash prints "unbound variable" through gettext; pin the locale so the check below reads the same text everywhere.
        env_inv["LC_ALL"] = "C"
        out_inv = tmp_path / f"out_{lane}_inv"
        res_inv = subprocess.run(
            [_bash(), _p(launcher), "--out-dir", _p(out_inv), "--session", f"sdlab-c3-{lane}-invalid", "--wall-s", "60", "--grace-s", "10"],
            env=env_inv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res_inv.returncode in (78, 93), f"{lane} invalid phase rc={res_inv.returncode}: {res_inv.stderr}"
        # Either refusal may end this run: 78 from the VM-side reader or 93 from the rig-side guard. Part 1 above is
        # the check that the VM-side reader alone refuses (it runs the reader with no rig guard and asserts 78).
        # The fake VM's own log must exist, and up to the moment the launcher returned it must not show its EXIT trap
        # dying under `set -u` (that turned 78 into 1 on main) or its wait budget running out.
        live_log = tmp_path / f"fx_{lane}_inv" / "colab_state" / "content" / ".sdlab_live.log"
        assert live_log.is_file(), f"{lane}: the fake VM wrote no log at {live_log}"
        live_txt = live_log.read_text(encoding="utf-8", errors="replace")
        assert "unbound variable" not in live_txt, f"{lane}: fake remote trap failed under set -u: {live_txt[-400:]}"
        assert "FAKE_INVALID_PHASE_NOT_REFUSED" not in live_txt, f"{lane}: reader never refused: {live_txt[-400:]}"
        win_inv = json.loads((out_inv / "window.json").read_text(encoding="utf-8"))
        assert win_inv["status"] == "VITALS_PHASE_INVALID"
        assert win_inv["refusal_code"] == "VITALS_PHASE_INVALID"
        combined_logs = (out_inv / "vitals.log").read_text(encoding="utf-8") + (out_inv / "guards.log").read_text(encoding="utf-8")
        assert "VITALS_PHASE_INVALID" in combined_logs
