"""Unit tests for scripts/colab/classify_install_log.py, the kits' install-failure classifier.

The samples in fixtures/uv_logs/ are captured stderr of uv 0.13.5
`uv pip install --require-hashes --only-binary :all:` failures, made locally on CPU:
a throwaway wheel pinned to a wrong hash, an sdist-only package, an absent package,
an unreachable index (127.0.0.1:9) and a requirement with no hash.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = REPO_ROOT / "scripts" / "colab" / "classify_install_log.py"
SAMPLES = Path(__file__).resolve().parent / "fixtures" / "uv_logs"

_spec = importlib.util.spec_from_file_location("classify_install_log", CLASSIFIER)
assert _spec is not None and _spec.loader is not None
cil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cil)


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        ("hash_mismatch.txt", "LOCK_HASH_MISMATCH"),
        ("no_wheel.txt", "WHEEL_MISSING"),
        ("not_found.txt", "WHEEL_MISSING"),
        ("network_retry.txt", "INSTALL_NETWORK_FAILURE"),
        ("no_hash.txt", "INSTALL_FAILED"),
    ],
)
def test_classify_real_uv_samples(sample: str, expected: str) -> None:
    text = (SAMPLES / sample).read_text(encoding="utf-8")
    assert cil.classify(text) == expected


def test_classify_platform_tag_and_dns_and_other() -> None:
    assert cil.classify("Because torch==2.9.0 has no wheels with a matching platform tag") == "WHEEL_MISSING"
    assert cil.classify("error: dns error: failed to lookup address information") == "INSTALL_NETWORK_FAILURE"
    assert cil.classify("error: Failed to install: permission denied") == "INSTALL_FAILED"
    assert cil.classify("") == "INSTALL_FAILED"


def test_hash_mismatch_wins_over_other_patterns() -> None:
    text = "Request failed after 3 retries\nHash mismatch for `x==1`\n"
    assert cil.classify(text) == "LOCK_HASH_MISMATCH"


def test_refusal_text_keeps_log_tail() -> None:
    text = (SAMPLES / "no_wheel.txt").read_text(encoding="utf-8")
    out = cil.refusal_text(text, "lane3", "wheels.log", tail=2)
    lines = out.splitlines()
    assert lines[0] == "REFUSED: WHEEL_MISSING during lane3 lock install"
    assert lines[1] == "--- last 2 lines of wheels.log ---"
    assert "has no usable wheels" in lines[2]
    assert lines[3].startswith("hint: Wheels are required")
    assert cil.refusal_text("", "lane1", "wheels.log") == "REFUSED: INSTALL_FAILED during lane1 lock install\n"
    assert cil.tail_lines("a\nb", 0) == []


def test_main_prints_refusal_and_handles_missing_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "wheels.log"
    log.write_text((SAMPLES / "network_retry.txt").read_text(encoding="utf-8"), encoding="utf-8")
    assert cil.main(["--lane", "lane1", "--log", str(log), "--tail", "3"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: INSTALL_NETWORK_FAILURE during lane1 lock install\n")
    assert "Connection refused (os error 111)" in out

    assert cil.main(["--lane", "lane3", "--log", str(tmp_path / "absent.log")]) == 0
    assert "REFUSED: INSTALL_FAILED during lane3 lock install (no log at" in capsys.readouterr().out


def test_cli_entry_point_runs(tmp_path: Path) -> None:
    log = tmp_path / "wheels.log"
    log.write_text((SAMPLES / "hash_mismatch.txt").read_text(encoding="utf-8"), encoding="utf-8")
    res = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--lane", "lane3", "--log", str(log)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert res.stdout.startswith("REFUSED: LOCK_HASH_MISMATCH during lane3 lock install")
