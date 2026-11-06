"""The live host-RAM guard measures private memory (anon + shmem), never cgroup memory.current.

Window sdlab-l3-rung-g4a (2026-11-06, a G4 VM) stopped during latent caching on
HOST_RAM_PROJECTION_EXCEEDED: the kit projected from cgroup memory.current, which counted the
page cache of the 57.7 GB model download. fixtures/vitals_ram_sdlab-l3-rung-g4a.txt holds that
run's 17 vitals samples, numbers only, one per line:
    <cgroup memory.current bytes> <MemTotal kB> <MemAvailable kB> <AnonPages kB>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
LAUNCHER = COLAB_DIR / "launch_lane3_stub.sh"
FIXTURES = REPO_ROOT / "tests" / "colab" / "fixtures"
REPLAY = FIXTURES / "vitals_ram_sdlab-l3-rung-g4a.txt"
sys.path.insert(0, str(COLAB_DIR))
sys.path.insert(0, str(FIXTURES))

import fake_colab as fc  # noqa: E402
import launch_guards as lg  # noqa: E402

MIB = 1048576.0


def _samples() -> list[tuple[int, int, int, int]]:
    rows = [tuple(int(x) for x in line.split()) for line in REPLAY.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 17 and all(len(r) == 4 for r in rows)
    return rows  # type: ignore[return-value]


def _vitals_block(cg: int, tot: int, avail: int, anon: int, *, extra: str = "", cg_max: str = "max") -> str:
    return (
        "=== VITALS 2026-11-06T18:42:54Z ===\n"
        f"CGROUP_MEM_CURRENT: {cg}\nCGROUP_MEM_MAX: {cg_max}\nCGROUP_MEM: oom_kill 0\n"
        f"MEM: MemTotal:       {tot} kB\nMEM: MemAvailable:   {avail} kB\nMEM: AnonPages:      {anon} kB\n"
        f"{extra}SETUP_BYTES: 0\nPROC:\nHARNESS: {{\"phase\": \"run\"}}\n"
    )


def _check(reading: dict) -> dict:
    return lg.evaluate_host_ram_projection(
        current_anon_mb=reading["private_mb"],
        projected_delta_mb=2048,
        mem_total_mb=reading["mem_total_mb"],
        cgroup_max_mb=reading["cgroup_max_mb"],
        mem_available_mb=reading["mem_available_mb"],
        source=reading["source"],
    )


# (a) unit: the real run's sequence, sample by sample, as the live guard reads it.
def test_replay_of_rung_g4a_passes_on_private_memory_and_would_trip_on_memory_current() -> None:
    text = ""
    projected = []
    for cg, tot, avail, anon in _samples():
        text += _vitals_block(cg, tot, avail, anon)
        reading = lg.host_ram_reading(text)
        assert reading is not None and reading["source"] == "meminfo:AnonPages"
        assert reading["private_mb"] == round(anon / 1024.0, 1) and reading["cgroup_max_mb"] is None
        rec = _check(reading)
        assert rec["tripped"] is False, rec
        projected.append(rec["projected_mb"])
        # What the kit used to do: memory.current as "anon". It trips on the last sample only.
        old = (reading["cgroup_current_mb_not_used"] + 2048) * 1.05 > reading["mem_total_mb"]
        assert old is (cg == _samples()[-1][0])
    last = _check(lg.host_ram_reading(text))
    assert last["private_mb"] == 52492.8 and last["limit_mb"] == 181130.0 and last["limit_source"] == "MemTotal"
    assert last["projected_mb"] == max(projected) == 57267.8
    assert last["mem_available_after_delta_mb"] == 123640.3


# (b) a real anon-growth case still trips, on either check.
def test_real_private_growth_still_trips() -> None:
    tot_kb = 185477132
    anon_kb = int(tot_kb * 0.97)
    reading = lg.host_ram_reading(_vitals_block(anon_kb * 1024, tot_kb, tot_kb - anon_kb, anon_kb))
    rec = _check(reading)
    assert rec["tripped"] is True and rec["code"] == "HOST_RAM_PROJECTION_EXCEEDED"
    # (175696.1 + 2048) x 1.05 = 186631.3 > 181130; MemAvailable 5433.9 - 2150.4 is still above the floor.
    assert rec["tripped_on"] == ["private_projection"] and rec["projected_mb"] == 186631.3
    with pytest.raises(ValueError, match="HOST_RAM_PROJECTION_EXCEEDED: private 175696.1 MB"):
        lg.check_host_ram_projection(current_anon_mb=reading["private_mb"], projected_delta_mb=2048,
                                     mem_total_mb=reading["mem_total_mb"])


def test_mem_available_floor_trips_when_unreclaimable_memory_is_not_anon() -> None:
    # Low anon, but MemAvailable is nearly gone (driver-pinned buffers, slab): check 2 trips alone.
    rec = lg.evaluate_host_ram_projection(current_anon_mb=4000, projected_delta_mb=2048, mem_total_mb=181130,
                                          mem_available_mb=4000, source="meminfo:AnonPages")
    assert rec["tripped_on"] == ["mem_available_floor"] and rec["mem_available_after_delta_mb"] == 1849.6
    assert "MemAvailable 4000.0 MB - delta 2048.0 MB x 1.05 = 1849.6 MB < floor 2048.0 MB" in rec["why"]


def test_cgroup_memory_stat_is_preferred_and_shmem_counts_and_numeric_max_is_the_ceiling() -> None:
    extra = "CGROUP_MEM_STAT: anon 10737418240\nCGROUP_MEM_STAT: file 99999999999\nCGROUP_MEM_STAT: shmem 2147483648\n"
    block = _vitals_block(150 * 1024**3, 185477132, 170000000, 9000000, extra=extra, cg_max=str(16 * 1024**3))
    reading = lg.host_ram_reading(block)
    assert reading["source"] == "cgroup_memory.stat:anon+shmem"
    assert (reading["anon_mb"], reading["shmem_mb"], reading["private_mb"]) == (10240.0, 2048.0, 12288.0)
    assert reading["cgroup_max_mb"] == 16384.0
    rec = _check(reading)
    # (12288 + 2048) x 1.05 = 15052.8 <= 16384 (the cgroup max, below MemTotal).
    assert rec["tripped"] is False and rec["limit_source"] == "cgroup memory.max" and rec["projected_mb"] == 15052.8
    meminfo = lg.host_ram_reading(_vitals_block(1, 185477132, 170000000, 1048576, extra="MEM: Shmem:          524288 kB\n"))
    assert meminfo["source"] == "meminfo:AnonPages+Shmem" and meminfo["private_mb"] == 1536.0


def test_reading_uses_one_sample_and_skips_samples_without_private_memory() -> None:
    assert lg.host_ram_reading("") is None
    assert lg.host_ram_reading("=== VITALS t ===\nCGROUP_MEM_CURRENT: 5\nMEM: MemTotal: 12582912 kB\n") is None
    good = _vitals_block(1, 185477132, 180000000, 2048000)
    truncated = "=== VITALS 2026-11-06T18:43:09Z ===\nCGROUP_MEM_CURRENT: 181527310336\n"
    reading = lg.host_ram_reading(good + truncated)
    assert reading["private_mb"] == 2000.0 and reading["timestamp"] == "2026-11-06T18:42:54Z"


# (d) unit: the CLI writes the tripping numbers to stdout (guards.log), not only to stderr.
def test_check_ram_cli_prints_the_tripping_record(capsys: pytest.CaptureFixture[str]) -> None:
    rc = lg.main(["--check-ram", "--current-anon-mb", "175000", "--projected-delta-mb", "2048", "--mem-total-mb", "181130",
                  "--mem-available-mb", "6000", "--ram-source", "meminfo:AnonPages"])
    out, err = capsys.readouterr()
    rec = json.loads(out.strip().splitlines()[-1])
    assert rc == 1 and rec["tripped"] is True and rec["refusal"]["code"] == "HOST_RAM_PROJECTION_EXCEEDED"
    for key, want in (("private_mb", 175000.0), ("delta_mb", 2048.0), ("factor", 1.05), ("limit_mb", 181130.0),
                      ("mem_available_mb", 6000.0), ("source", "meminfo:AnonPages")):
        assert rec[key] == want
    assert err.startswith("HOST_RAM_PROJECTION_EXCEEDED: private 175000.0 MB (meminfo:AnonPages)")
    assert lg.main(["--check-ram", "--current-anon-mb", "500", "--mem-total-mb", "8000", "--mem-available-mb", "7000"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_wall_cap_and_vitals_records_carry_a_refusal(capsys: pytest.CaptureFixture[str]) -> None:
    assert lg.main(["--mode", "fake", "--elapsed-s", "100", "--wall-s", "100", "--grace-s", "10"]) == 1
    rec = json.loads(capsys.readouterr().out)
    assert rec["refusal"] == {"code": "WALL_GUARD_TRIPPED", "why": "wall guard: -10.0 s remaining of threshold 90.0 s (wall - grace)"}
    assert lg.main(["--mode", "live", "--cap", "1", "--margin", "0.1", "--start-balance", "10", "--current-balance", "9"]) == 1
    assert json.loads(capsys.readouterr().out)["refusal"] == {"code": "CAP_GUARD_TRIPPED", "why": "cap guard: spend 1.0 ccu >= ceiling 0.9 ccu"}
    assert lg.main(["--mode", "live", "--usage-parse-error", "COLAB_USAGE_PARSE_FAILED: x"]) == 1
    assert json.loads(capsys.readouterr().out)["refusal"]["code"] == "COLAB_USAGE_PARSE_FAILED"
    assert lg.main(["--mode", "fake"]) == 0
    assert "refusal" not in json.loads(capsys.readouterr().out)
    assert lg.wall_cap_refusal({"tripped": False}, {"tripped": False}) is None


# ---- through the kit and the fake colab CLI ---------------------------------------------------


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found
    return found


def _replay_window(tmp_path: Path, replay: Path, name: str) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path / f"{name}_case")
    env["FAKE_COLAB_MODE"] = "ram_replay"
    env["FAKE_COLAB_RAM_REPLAY"] = fc._to_posix(replay)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / f"out_{name}"
    res = subprocess.run(
        [_bash(), fc._to_posix(LAUNCHER), "--out-dir", fc._to_posix(out_dir), "--session", f"sdlab-l3-{name}"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, check=False,
    )
    return res, out_dir, state_dir


def _ram_records(out_dir: Path) -> list[dict]:
    recs = []
    for line in (out_dir / "guards.log").read_text(encoding="utf-8").splitlines():
        if line.startswith("{") and '"check": "host_ram"' in line:
            recs.append(json.loads(line))
    return recs


# (a) e2e: the real sequence through the kit's live guards. It tripped the old kit on sample 17.
def test_kit_replay_of_rung_g4a_does_not_trip_host_ram(tmp_path: Path) -> None:
    res, out_dir, _ = _replay_window(tmp_path, REPLAY, "g4a")
    guards = (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "HOST_RAM_PROJECTION_EXCEEDED" not in guards + res.stderr
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] != "HOST_RAM_PROJECTION_EXCEEDED"
    recs = _ram_records(out_dir)
    assert recs and all(r["tripped"] is False for r in recs)
    assert any(r["private_mb"] == 52492.8 and r["source"] == "meminfo:AnonPages" and r["mem_available_mb"] == 125790.7
               for r in recs)


# (c) + (d) e2e: a real private-memory climb trips as a named refusal, numbers in guards.log.
def test_kit_ram_trip_is_a_named_refusal_with_its_numbers_in_guards_log(tmp_path: Path) -> None:
    tot_kb = 185477132
    rows = [(2 * 1024**3, tot_kb, tot_kb - 2097152, 2097152), (50 * 1024**3, tot_kb, 80000000, 100000000),
            (178 * 1024**3, tot_kb, 3000000, 180000000)]
    replay = tmp_path / "climb.txt"
    replay.write_text("".join(f"{a} {b} {c} {d}\n" for a, b, c, d in rows), encoding="utf-8", newline="\n")
    res, out_dir, state_dir = _replay_window(tmp_path, replay, "climb")
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == "HOST_RAM_PROJECTION_EXCEEDED" and win["status"] == "HOST_RAM_PROJECTION_EXCEEDED"
    assert "private 175781.2 MB (meminfo:AnonPages) + delta 2048.0 MB x 1.05" in win["why"]
    draft = json.loads((out_dir / "outcome.draft.json").read_text(encoding="utf-8"))
    assert draft["refusal_code"] == "HOST_RAM_PROJECTION_EXCEEDED" and draft["why"] == win["why"]
    tripped = [r for r in _ram_records(out_dir) if r["tripped"]]
    assert tripped, (out_dir / "guards.log").read_text(encoding="utf-8")
    rec = tripped[0]
    assert (rec["private_mb"], rec["delta_mb"], rec["factor"], rec["limit_mb"], rec["mem_available_mb"], rec["source"]) == (
        175781.2, 2048.0, 1.05, 181130.0, 2929.7, "meminfo:AnonPages")
    assert rec["tripped_on"] == ["private_projection", "mem_available_floor"]
    assert "REFUSED: HOST_RAM_PROJECTION_EXCEEDED: private 175781.2 MB" in (out_dir / "guards.log").read_text(encoding="utf-8")
    assert "STOP -s sdlab-l3-climb" in (state_dir / "stops.log").read_text(encoding="utf-8")


# The other live-guard trips also land as named refusals (they used to leave refusal_code null).
@pytest.mark.parametrize(
    ("mode", "extra", "code"),
    [
        ("cap_burn", ["--cap", "0.05", "--margin", "0.01"], "CAP_GUARD_TRIPPED"),
        ("dead_harness", [], "DEAD_HARNESS_TRIPPED"),
    ],
)
def test_kit_other_live_guard_trips_are_named_refusals(tmp_path: Path, mode: str, extra: list[str], code: str) -> None:
    _, _, env = fc.make_fake_colab_env(tmp_path / f"{mode}_case")
    env["FAKE_COLAB_MODE"] = mode
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    out_dir = tmp_path / f"out_{mode}"
    res = subprocess.run(
        [_bash(), fc._to_posix(LAUNCHER), "--out-dir", fc._to_posix(out_dir), "--session", f"sdlab-l3-{mode}", *extra],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )
    assert res.returncode != 0
    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["refusal_code"] == code and win["status"] == code and win["why"]
    assert f"REFUSED: {code}: " in (out_dir / "guards.log").read_text(encoding="utf-8")
