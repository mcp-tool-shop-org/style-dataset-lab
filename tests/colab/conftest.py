"""Shared fixtures for the Colab kit tests."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
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
