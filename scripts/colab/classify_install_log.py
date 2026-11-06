#!/usr/bin/env python3
"""Classify a failed `uv pip install` log into one named refusal code.

The Colab kits run this on the VM after a lock install exits non-zero, so the
refusal they record says what uv actually reported:

- ``LOCK_HASH_MISMATCH``: uv computed a different sha256 than the lock pins.
- ``WHEEL_MISSING``: uv found no matching wheel or distribution for the platform.
- ``INSTALL_NETWORK_FAILURE``: uv could not reach the index (retries, refused, DNS).
- ``INSTALL_FAILED``: anything else; the log tail in the refusal says what.

Usage: classify_install_log.py --lane <lane1|lane3> --log <wheels.log> [--tail N]
Prints ``REFUSED: <CODE> during <lane> lock install`` and the last lines of the log.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LOCK_HASH_MISMATCH = "LOCK_HASH_MISMATCH"
WHEEL_MISSING = "WHEEL_MISSING"
INSTALL_NETWORK_FAILURE = "INSTALL_NETWORK_FAILURE"
INSTALL_FAILED = "INSTALL_FAILED"

# Checked in this order; the first code with a matching pattern wins.
_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        LOCK_HASH_MISMATCH,
        (
            re.compile(r"hash mismatch for", re.I),
            re.compile(r"hashes do not match", re.I),
        ),
    ),
    (
        WHEEL_MISSING,
        (
            re.compile(r"has no usable wheels", re.I),
            re.compile(r"has no wheels with a matching", re.I),
            re.compile(r"was not found in the (package registry|provided package locations)", re.I),
            re.compile(r"no matching distribution found", re.I),
        ),
    ),
    (
        INSTALL_NETWORK_FAILURE,
        (
            re.compile(r"request failed after \d+ retr", re.I),
            re.compile(r"error sending request for url", re.I),
            re.compile(r"connection refused", re.I),
            re.compile(r"tcp connect error", re.I),
            re.compile(r"dns error|failed to lookup address", re.I),
            re.compile(r"network is unreachable", re.I),
            re.compile(r"operation timed out", re.I),
        ),
    ),
)


def classify(log_text: str) -> str:
    """Return the refusal code for a failed uv install log."""
    for code, patterns in _PATTERNS:
        if any(p.search(log_text) for p in patterns):
            return code
    return INSTALL_FAILED


def tail_lines(log_text: str, n: int) -> list[str]:
    lines = [line for line in log_text.splitlines() if line.strip()]
    return lines[-n:] if n > 0 else []


def refusal_text(log_text: str, lane: str, log_name: str, tail: int = 20) -> str:
    code = classify(log_text)
    out = [f"REFUSED: {code} during {lane} lock install"]
    last = tail_lines(log_text, tail)
    if last:
        out.append(f"--- last {len(last)} lines of {log_name} ---")
        out.extend(last)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lane", required=True, choices=("lane1", "lane3"))
    ap.add_argument("--log", required=True)
    ap.add_argument("--tail", type=int, default=20)
    args = ap.parse_args(argv)
    log_path = Path(args.log)
    if not log_path.is_file():
        sys.stdout.write(f"REFUSED: {INSTALL_FAILED} during {args.lane} lock install (no log at {log_path})\n")
        return 0
    text = log_path.read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(refusal_text(text, args.lane, log_path.name, args.tail))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
