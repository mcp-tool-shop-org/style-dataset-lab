"""Shared fixtures for the Colab kit tests."""

from __future__ import annotations

import shutil
import sys
import uuid
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

from slow_runner_shim import install_slow_runner_shim  # noqa: E402

LIVE_OUT_ROOT = REPO_ROOT / ".pytest-live-out"


@pytest.fixture
def persistent_out_root() -> Iterator[Path]:
    """A directory outside /tmp and tmpfs, for runs made without fake-colab test mode.

    A live-mode kit refuses an out dir on volatile storage (OUT_DIR_VOLATILE), and pytest's
    tmp_path is under /tmp, so tests that drive a kit outside test mode put their out dir here.
    """
    root = LIVE_OUT_ROOT / uuid.uuid4().hex
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        try:
            LIVE_OUT_ROOT.rmdir()
        except OSError:
            pass


@pytest.fixture
def slow_runner_shim(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[Path]]:
    """Install a PATH/SDLAB_PYTHON sleep shim slowing fake `colab` and rig `python`/`launch_guards.py`."""

    def _arm(
        *,
        colab_delay_s: float = 1.0,
        guard_python_delay_s: float = 1.5,
        extra_modules: Sequence[Any] = (),
    ) -> list[Path]:
        return install_slow_runner_shim(
            monkeypatch,
            colab_delay_s=colab_delay_s,
            guard_python_delay_s=guard_python_delay_s,
            extra_modules=extra_modules,
        )

    return _arm

