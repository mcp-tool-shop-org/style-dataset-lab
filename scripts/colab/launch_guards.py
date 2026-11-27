#!/usr/bin/env python3
"""C2 Colab launcher guards (DESIGN-v3 section 9.2 item 6 — lessons v4k, v4p, v4q).

Provides:
  1. evaluate_wall_guard (v4k: WALL_S and GRACE_S honoured in stub and live modes)
  2. evaluate_cap_guard (v4k: CAP and MARGIN honoured in stub and live modes)
  3. parse_vitals_log & evaluate_vitals_and_stall_guard (v4p: DEAD_HARNESS_TRIPPED on
     cgroup OOM or 2 consecutive phase: run samples with 0 worker procs, STALL_GUARD_TRIPPED on stall)
  4. check_host_ram_projection & run_between_item_fetch (v4q: pre-load cgroup/host RAM
     check against kernel SIGKILL rc=-9, plus between-item fetch before current.json reset)
  5. verify_input_shas & scrub_colab_tokens (pre-open sha256 gate and log token scrubber)
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

WORKER_PROC_RE = re.compile(
    r"\b(comfy|main\.py|ai-toolkit|run\.py|llama-server|ollama|lane1_render\.py)\b",
    re.I,
)
OOM_KILL_RE = re.compile(r"\boom_kill\s+([1-9]\d*)\b|\bOut of memory: Killed process\b", re.I)

TOKEN_SCRUB_PATTERNS = [
    (re.compile(r"(colab-runtime-proxy-token=)[^\s&\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(access_token=)[^\s&\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED]"),
    (re.compile(r"\bhf_[A-Za-z0-9]{16,}\b"), "hf_[REDACTED]"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


SELF_PIN_LINE_RE = re.compile(rb'^(PINNED_SELF_SHA=")[0-9a-fA-F]{64}(")', flags=re.M)


def sha256_self_normalized(path: Path) -> tuple[str | None, str]:
    raw = Path(path).read_bytes()
    m = re.search(rb'^PINNED_SELF_SHA="([0-9a-fA-F]{64})"', raw, flags=re.M)
    embedded_pin = m.group(1).decode("ascii").lower() if m else None
    norm_bytes = SELF_PIN_LINE_RE.sub(rb"\1\2", raw, count=1)
    return embedded_pin, hashlib.sha256(norm_bytes).hexdigest()


def normalize_hex_sha(val: str) -> str:
    s = str(val).strip().lower()
    if s.startswith("sha256:"):
        s = s[7:]
    return s


def verify_input_shas(expected_shas: dict[str, str]) -> dict[str, str]:
    verified: dict[str, str] = {}
    for file_str, exp_raw in expected_shas.items():
        p = Path(file_str)
        if not p.exists():
            raise ValueError(f"REFUSED: INPUT_FILE_MISSING: {p} does not exist")
        exp = normalize_hex_sha(exp_raw)
        got = sha256_file(p)
        if got != exp:
            embedded_pin, norm_got = sha256_self_normalized(p)
            if embedded_pin is not None and exp == norm_got and embedded_pin == norm_got:
                got = norm_got
            else:
                raise ValueError(
                    f"REFUSED: INPUT_SHA_MISMATCH for {p}: got {got}, expected {exp}"
                )
        verified[file_str] = got
    return verified


def scrub_colab_tokens(text: str) -> str:
    out = text
    for pattern, repl in TOKEN_SCRUB_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def scrub_file_in_place(path: Path) -> None:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return
    raw = p.read_text(encoding="utf-8", errors="replace")
    scrubbed = scrub_colab_tokens(raw)
    if scrubbed != raw:
        p.write_text(scrubbed, encoding="utf-8", newline="\n")


def evaluate_wall_guard(
    *,
    mode: str = "live",
    elapsed_s: float,
    wall_s: float = 3000.0,
    grace_s: float = 60.0,
) -> dict[str, Any]:
    threshold_s = round(max(0.0, float(wall_s) - float(grace_s)), 6)
    elapsed_val = round(float(elapsed_s), 6)
    remaining_s = round(threshold_s - elapsed_val, 6)
    tripped = elapsed_val >= threshold_s
    return {
        "mode": mode,
        "tripped": tripped,
        "code": "WALL_GUARD_TRIPPED" if tripped else None,
        "remaining_s": remaining_s,
        "threshold_s": threshold_s,
    }


CURRENT_BALANCE_RE = re.compile(
    r"^\s*Current\s+balance:\s*([+-]?\d+(?:\.\d+)?)\s*(?:compute\s+units)?\s*$",
    re.I | re.M,
)
USAGE_RATE_RE = re.compile(
    r"^\s*Usage\s+rate:\s*([+-]?\d+(?:\.\d+)?)\s*/\s*hr?\s*$",
    re.I | re.M,
)
ACTIVE_ASSIGNMENTS_RE = re.compile(
    r"^\s*Active\s+assignments:\s*(\d+)\s*$",
    re.I | re.M,
)


class RateUnread(Exception):
    """A GPU window has no positive live post-open rate. `partial` carries what the usage text did
    give (balance, the readings), so a caller can record it; the caller decides whether this
    means "not yet" (polling right after open) or a refusal (RATE_UNREAD)."""

    code = "RATE_UNREAD"

    def __init__(self, partial: dict[str, Any]) -> None:
        super().__init__("RATE_UNREAD: no positive live post-open rate for a GPU window")
        self.partial = partial


CARD_CLASSES = ("gpu", "cpu")

# The window rate. `colab usage` reports the ACCOUNT's rate (docs/colab-cli-contract.md): a window's
# own rate is the account reading minus the neighbour baseline (at first the pre-open reading). It
# counts only when it is stable (two reads at least RATE_STABLE_GAP_S apart agreeing within
# RATE_STABLE_TOLERANCE) and at or above GPU_RATE_FLOOR. The floor is below the cheapest GPU
# measured, the T4 at 1.07/hr (16 reads, receipt windowC2-12-t4-s1a-20261027), and above the highest
# CPU rate, 0.26/hr. A GPU window is priced on max(--max-rate, the highest stable window rate seen),
# never on a window or account rate alone.
#
# "Active assignments" is recorded with every reading. When it changes, another window opened or
# closed. Nothing is judged until the count settles: two counted reads at the new count, at least
# RATE_STABLE_GAP_S apart, whose account rates agree within the tolerance (the count can arrive a
# read before the neighbour's rate). Then the neighbour is re-baselined: baseline = account - the
# highest stable rate of ours seen (not the last one: a low stable read taken while a neighbour's
# rate led its count would otherwise inflate the baseline and hide our later rise). Pending or settling reads are never judged against the max and never raise our
# priced rate, which stays max(--max-rate, highest stable seen). Only a read at an unchanged count
# may raise our rate or trip the max. Known limit: a neighbour opening on the same read our own rate
# rises folds that rise into the baseline; pricing at max(--max-rate, seen) bounds the cost.
#
# Before our window's first stable read, a missing count or 0 means "not yet registered": the
# receipts show the rate and the count arriving together (windowC2-12-t4-s1a-20261027 reads 0.00
# with 0 assignments until the session registers, then 1.07 with 1). Such a read is recorded,
# uncounted, and spends only the RATE_UNREAD poll budget. Mid-run, bad assignment counts or reads
# below GPU_RATE_FLOOR are logged in rate_window.json only and never kill the running window.
GPU_RATE_FLOOR = 1.00
RATE_STABLE_TOLERANCE = 0.01
RATE_STABLE_GAP_S = 5.0


def parse_active_assignments(raw_usage: str) -> int | None:
    m = re.search(r"^\s*Active\s+assignments:\s*(\d+)\s*$", raw_usage or "", re.I | re.M)
    return int(m.group(1)) if m else None


def update_window_rate(state: dict[str, Any], *, account_rate: float | None, pre_open_rate: float | None,
                       at: str, epoch: float, assignments: int | None,
                       min_gap_s: float = RATE_STABLE_GAP_S, floor: float = GPU_RATE_FLOOR,
                       tolerance: float = RATE_STABLE_TOLERANCE) -> dict[str, Any]:
    """Fold one post-open `colab usage` reading into the window-rate state (kept in the out dir).
    Every reading is recorded. Mid-run missing/0 assignment counts or reads below floor are recorded
    for logging only and never trigger a kill. A read less than `min_gap_s` after the last counted
    one is recorded as `counted: false`. A changed count starts a pending re-baseline that settles on
    two agreeing reads at the new count; `best_stable` is the highest stable rate at or above floor."""
    readings = state.setdefault("readings", [])
    state["floor"] = floor
    if "neighbour_baseline" not in state:
        state["neighbour_baseline"] = float(pre_open_rate) if pre_open_rate is not None else 0.0
    base = float(state["neighbour_baseline"])
    rec: dict[str, Any] = {"at": at, "epoch": round(float(epoch), 3), "account_rate": account_rate,
                           "pre_open_rate": pre_open_rate, "assignments": assignments,
                           "neighbour_baseline": base, "window_rate": None, "stable": False}
    if assignments is None or int(assignments) <= 0:
        tag = "not_registered" if state.get("best_stable") is None else "assignments_bad"
        rec.update({"counted": False, tag: True})
        readings.append(rec)
        return state
    last_epoch = state.get("last_counted_epoch")
    if last_epoch is not None and float(epoch) - float(last_epoch) < float(min_gap_s):
        rec["counted"] = False
        readings.append(rec)
        return state
    rec["counted"] = True
    state["last_counted_epoch"] = float(epoch)
    known = "last_assignments" in state
    prev_count = state.get("last_assignments")
    state["last_assignments"] = assignments
    pending = state.get("rebaseline_pending")
    if known and assignments != prev_count:
        # A new count: start (or restart) the pending re-baseline. Judge nothing.
        state["rebaseline_pending"] = {"count": assignments, "from": prev_count, "last_account": account_rate}
        rec.update({"rebaseline_pending": True, "assignments_before": prev_count})
        readings.append(rec)
        return state
    if pending is not None:
        last_acc = pending.get("last_account")
        if (account_rate is None or last_acc is None
                or abs(float(account_rate) - float(last_acc)) > tolerance):
            pending["last_account"] = account_rate
            rec["rebaseline_pending"] = True
            readings.append(rec)
            return state
        # Settled: two agreeing reads at the new count. The neighbour is what the account reads above
        # the highest stable rate of ours seen: the conservative direction (our later reads can only
        # come out higher, never hidden under an inflated baseline).
        ours = state.get("best_stable")
        if ours is not None:
            base = round(max(float(account_rate) - float(ours), 0.0), 4)
            state["neighbour_baseline"] = base
        state["last_window"] = ours
        state.pop("rebaseline_pending", None)
        rec.update({"rebaselined": True, "window_rate": ours, "neighbour_baseline": base,
                    "assignments_before": pending.get("from")})
        readings.append(rec)
        return state
    window = None if account_rate is None else round(max(float(account_rate) - base, 0.0), 4)
    prev = state.get("last_window")
    stable = (window is not None and window >= floor and prev is not None
              and abs(window - float(prev)) <= tolerance)
    below_floor = (window is not None and window < floor and prev is not None
                   and abs(window - float(prev)) <= tolerance and state.get("best_stable") is not None)
    rec.update({"window_rate": window, "stable": stable})
    if below_floor:
        rec["below_floor"] = True
    readings.append(rec)
    state["last_window"] = window
    if stable:
        state.setdefault("open_stable", window)
        state["last_stable"] = window
        if state.get("best_stable") is None or window > state["best_stable"]:
            state["best_stable"] = window
    return state


def gpu_projection_rate(state: dict[str, Any], max_rate: float) -> float:
    """The rate a GPU window's cap is projected with: max(--max-rate, open stable window rate)."""
    ref = state.get("open_stable", state.get("best_stable"))
    return max(float(max_rate), float(ref)) if ref is not None else float(max_rate)


def window_rate_decision(state: dict[str, Any], max_rate: float) -> str:
    """`unread` (no stable window rate at or above the floor yet), `above_max` or `ok`."""
    best = state.get("best_stable")
    if best is None:
        return "unread"
    return "above_max" if float(best) > float(max_rate) else "ok"


def parse_usage_text(
    raw_usage: str,
    card_class: str,
    *,
    usage_rc: int = 0,
    configured_rate: float = 0.26,
    session_opened: bool = True,
    post_open_rate: float | None = None,
    pre_open_rate: float | None = None,
) -> dict[str, Any]:
    """Parse `colab usage`. `card_class` ("gpu" or "cpu", required) decides the rate policy: a GPU
    window is priced only by its live post-open rate, and `_select_rate` raises RateUnread when it
    has none, so no GPU caller can reach a configured-rate branch. A CPU stub keeps the labelled
    configured rate."""
    if card_class not in CARD_CLASSES:
        raise ValueError(f"card_class must be one of {CARD_CLASSES}, got {card_class!r}")
    cfg = float(configured_rate)

    def _select_rate(
        cur_measured: float | None,
    ) -> tuple[float | None, float | None, float, str]:
        eff_pre = cur_measured if not session_opened else pre_open_rate
        existing_pos_post = post_open_rate if (post_open_rate is not None and post_open_rate > 0.0) else None
        if existing_pos_post is not None:
            eff_post: float | None = existing_pos_post
        elif session_opened and cur_measured is not None:
            eff_post = cur_measured
        elif post_open_rate is not None:
            eff_post = post_open_rate
        else:
            eff_post = None

        if eff_post is not None and eff_post > 0.0:
            return eff_pre, eff_post, float(eff_post), "post_open_measured"
        if card_class == "gpu":
            raise RateUnread({"rate_measured_pre_open": eff_pre, "rate_measured_post_open": eff_post})
        if eff_post is not None and eff_post == 0.0:
            pos_pre = float(eff_pre) if (eff_pre is not None and eff_pre > 0.0) else 0.0
            return eff_pre, eff_post, max(cfg, pos_pre), "configured_pending_post_open_rate"
        if eff_pre is not None:
            return eff_pre, None, max(float(eff_pre), cfg), "max_of_pre_open_and_configured"
        return None, None, cfg, "configured"

    def _failure_rates() -> tuple[float | None, float | None, float | None, str]:
        # A usage read that failed is COLAB_USAGE_PARSE_FAILED (the cap guard trips on it); for a
        # GPU window without a live rate it carries no projection rate at all, never a configured one.
        try:
            return _select_rate(None)
        except RateUnread as exc:
            return (exc.partial["rate_measured_pre_open"], exc.partial["rate_measured_post_open"], None,
                    "live_rate_unread")

    if usage_rc != 0:
        eff_pre, eff_post, rate_used, rate_src = _failure_rates()
        return {
            "ok": False,
            "code": "COLAB_USAGE_PARSE_FAILED",
            "balance": None,
            "rate_measured": None,
            "rate_measured_pre_open": eff_pre,
            "rate_measured_post_open": eff_post,
            "rate_for_projection": rate_used,
            "rate_used_for_cap_and_projection": rate_used,
            "rate_source": rate_src,
            "active_assignments": None,
            "error": f"COLAB_USAGE_PARSE_FAILED: colab usage exited with status {usage_rc}",
        }
    text = raw_usage or ""
    m_bal = CURRENT_BALANCE_RE.search(text)
    if not m_bal:
        eff_pre, eff_post, rate_used, rate_src = _failure_rates()
        return {
            "ok": False,
            "code": "COLAB_USAGE_PARSE_FAILED",
            "balance": None,
            "rate_measured": None,
            "rate_measured_pre_open": eff_pre,
            "rate_measured_post_open": eff_post,
            "rate_for_projection": rate_used,
            "rate_used_for_cap_and_projection": rate_used,
            "rate_source": rate_src,
            "active_assignments": None,
            "error": "COLAB_USAGE_PARSE_FAILED: missing 'Current balance: <float> compute units'",
        }
    balance = float(m_bal.group(1))
    if balance < 0.0:
        eff_pre, eff_post, rate_used, rate_src = _failure_rates()
        return {
            "ok": False,
            "code": "COLAB_USAGE_PARSE_FAILED",
            "balance": None,
            "rate_measured": None,
            "rate_measured_pre_open": eff_pre,
            "rate_measured_post_open": eff_post,
            "rate_for_projection": rate_used,
            "rate_used_for_cap_and_projection": rate_used,
            "rate_source": rate_src,
            "active_assignments": None,
            "error": f"COLAB_USAGE_PARSE_FAILED: negative balance {balance} is impossible",
        }
    m_rate = USAGE_RATE_RE.search(text)
    if m_rate:
        rate_measured: float | None = float(m_rate.group(1))
        if rate_measured < 0.0:
            eff_pre, eff_post, rate_used, rate_src = _failure_rates()
            return {
                "ok": False,
                "code": "COLAB_USAGE_PARSE_FAILED",
                "balance": None,
                "rate_measured": None,
                "rate_measured_pre_open": eff_pre,
                "rate_measured_post_open": eff_post,
                "rate_for_projection": rate_used,
                "rate_used_for_cap_and_projection": rate_used,
                "rate_source": rate_src,
                "active_assignments": None,
                "error": f"COLAB_USAGE_PARSE_FAILED: negative usage rate {rate_measured} is impossible",
            }
    else:
        rate_measured = None
    m_assign = ACTIVE_ASSIGNMENTS_RE.search(text)
    active_assignments = int(m_assign.group(1)) if m_assign else None
    try:
        eff_pre, eff_post, rate_for_projection, rate_source = _select_rate(rate_measured)
    except RateUnread as exc:
        exc.partial.update({"balance": balance, "rate_measured": rate_measured,
                            "active_assignments": active_assignments})
        raise
    return {
        "ok": True,
        "code": None,
        "balance": balance,
        "rate_measured": rate_measured,
        "rate_measured_pre_open": eff_pre,
        "rate_measured_post_open": eff_post,
        "rate_for_projection": rate_for_projection,
        "rate_used_for_cap_and_projection": rate_for_projection,
        "rate_source": rate_source,
        "active_assignments": active_assignments,
        "error": None,
    }


CAP_TRIP_FORMULA = (
    "effective_trip = cap - margin - cleanup_reserve; cleanup_reserve = (cleanup_bound_s / 3600) * priced_rate"
)

# Bounded `colab usage` poll retry rule:
#   up to 3 attempts in all, each under `colab_run_bounded 30 5 colab usage` (30 s timeout + 5 s
#   SIGKILL grace = 35 s max per attempt), with 2 s and 4 s backoffs between failed attempts:
#     T_retry = 3 * (30 + 5) + 2 + 4 = 111 s.
#   T_retry bounds one retry sequence because each attempt is bounded and the backoffs are fixed; the
#   backoff clamp in colab_window.sh only shortens a sleep and does not enforce the bound.
# Blind interval (from one live cap decision to the next; the margin gate prices this, not T_retry):
#     blind_interval_s = T_retry + 2 * poll_s + slack_s = 111 + 2 * 2 + 2 = 117 s
#   poll_s (GUARD_POLL_INTERVAL_S, default 2 s) counts twice: the tick slept before the next poll
#   launches, and up to one tick of lag before the loop sees the poll exit. slack_s (2 s) covers the
#   parse and timing Python runs (measured under 1 s per sequence on the rig) and the tick's guards.
#   The live loop fails a poll still in flight after T_retry + slack_s closed with
#   COLAB_USAGE_PARSE_FAILED (the in-flight deadline), so the interval holds even when `colab usage`
#   never returns.
#   Blind-interval spend at `priced_rate` must stay within half the cap margin:
#     priced_rate * (blind_interval_s / 3600) <= margin_ccu / 2.
#   (#84's arithmetic for a loop that polls `colab usage` every tick.)
# Detached poll lag (sdlab#82: the remote job runs detached and the rig polls it with `colab exec`):
#     detached_poll_lag_s = 2 * (poll_retry_sleep_s + poll_exec_timeout_s) + kill_grace_s = 2 * (5 + 30) + 10 = 80 s
#   A usage read is launched only on a tick after a successful remote poll, and a finished (or overdue)
#   read is reaped only at the next tick, which follows the next remote poll. So from the last cap check
#   (a fresh one, or the offline projection after a failed poll) to the next fresh one:
#     retry sleep + poll_s + a slow successful poll (<= poll_exec_timeout_s), then the read (<= its in-flight
#     deadline T_retry + slack_s), then up to a retry sleep + poll_s + a failed poll killed at
#     poll_exec_timeout_s + kill_grace_s:
#     cap_check_interval_s = (r + p + e) + (T_retry + slack_s) + (r + p + e + g)
#                          = blind_interval_s + detached_poll_lag_s = 117 + 80 = 197 s.
#   The margin gate prices cap_check_interval_s:
#     priced_rate * (cap_check_interval_s / 3600) <= margin_ccu / 2.
#   For G4 at 10.05/hr: 10.05 * 197 / 3600 = 0.549958; margin 1.0 (half 0.5) refuses, margin 1.25 (half 0.625)
#   passes with 0.075042 headroom (13.6 % of the spend). The highest rate that fits margin 1.25 is
#   0.625 * 3600 / 197 = 11.42/hr.
USAGE_POLL_ATTEMPTS = 3
USAGE_POLL_TIMEOUT_S = 30
USAGE_POLL_KILL_GRACE_S = 5
USAGE_POLL_BACKOFF_S = (2, 4)
USAGE_RETRY_BOUND_S = (
    USAGE_POLL_ATTEMPTS * (USAGE_POLL_TIMEOUT_S + USAGE_POLL_KILL_GRACE_S)
    + sum(USAGE_POLL_BACKOFF_S[: max(0, USAGE_POLL_ATTEMPTS - 1)])
)
GUARD_POLL_INTERVAL_S_DEFAULT = 2
USAGE_DECISION_SLACK_S = 2
DETACHED_POLL_RETRY_SLEEP_S = 5
DETACHED_POLL_EXEC_TIMEOUT_S = 30
DETACHED_KILL_GRACE_S = 10


def detached_poll_lag_s(
    poll_retry_sleep_s: float = DETACHED_POLL_RETRY_SLEEP_S,
    poll_exec_timeout_s: float = DETACHED_POLL_EXEC_TIMEOUT_S,
    kill_grace_s: float = DETACHED_KILL_GRACE_S,
) -> int | float:
    total = 2.0 * (max(0.0, float(poll_retry_sleep_s)) + max(0.0, float(poll_exec_timeout_s))) + max(0.0, float(kill_grace_s))
    return int(total) if total == int(total) else round(total, 6)


DETACHED_POLL_LAG_S = detached_poll_lag_s()


def usage_blind_interval_s(
    usage_retry_bound_s: float = USAGE_RETRY_BOUND_S,
    poll_s: float = GUARD_POLL_INTERVAL_S_DEFAULT,
    slack_s: float = USAGE_DECISION_SLACK_S,
) -> int | float:
    total = max(0.0, float(usage_retry_bound_s)) + 2.0 * max(0.0, float(poll_s)) + max(0.0, float(slack_s))
    return int(total) if total == int(total) else round(total, 6)


USAGE_BLIND_INTERVAL_S = usage_blind_interval_s()
CAP_CHECK_INTERVAL_S = (
    int(USAGE_BLIND_INTERVAL_S + DETACHED_POLL_LAG_S)
    if float(USAGE_BLIND_INTERVAL_S + DETACHED_POLL_LAG_S).is_integer()
    else round(USAGE_BLIND_INTERVAL_S + DETACHED_POLL_LAG_S, 6)
)


def compute_usage_retry_budget(
    *,
    priced_rate: float,
    margin: float,
    usage_retry_bound_s: float = USAGE_RETRY_BOUND_S,
    usage_blind_interval: float | None = None,
    detached_poll_lag: float | None = None,
) -> dict[str, Any]:
    bound_raw = max(0.0, float(usage_retry_bound_s))
    bound_val: int | float = int(bound_raw) if bound_raw == int(bound_raw) else round(bound_raw, 6)
    blind_val = (
        usage_blind_interval_s(bound_raw)
        if usage_blind_interval is None
        else usage_blind_interval_s(float(usage_blind_interval), 0.0, 0.0)
    )
    lag_val = (
        DETACHED_POLL_LAG_S
        if detached_poll_lag is None
        else max(0.0, float(detached_poll_lag))
    )
    lag_val = int(lag_val) if float(lag_val).is_integer() else round(float(lag_val), 6)
    interval_raw = float(blind_val) + float(lag_val)
    interval_val: int | float = int(interval_raw) if interval_raw.is_integer() else round(interval_raw, 6)
    rate_v = max(0.0, float(priced_rate))
    margin_v = round(float(margin), 6)
    spend_units = round((interval_raw / 3600.0) * rate_v, 6)
    half_margin_units = round(margin_v / 2.0, 6)
    min_margin_units = round(2.0 * spend_units, 6)
    fits = bool(margin_v > 0.0 and spend_units <= half_margin_units)
    return {
        "usage_retry_bound_s": bound_val,
        "usage_blind_interval_s": blind_val,
        "detached_poll_lag_s": lag_val,
        "cap_check_interval_s": interval_val,
        "usage_retry_spend_units": spend_units,
        "usage_retry_half_margin_units": half_margin_units,
        "usage_retry_min_margin_units": min_margin_units,
        "fits": fits,
    }


def compute_cap_trip(
    cap: float,
    margin: float,
    cleanup_bound_s: float = 0.0,
    priced_rate: float = 0.0,
) -> dict[str, Any]:
    bound_s = max(0.0, float(cleanup_bound_s))
    rate = max(0.0, float(priced_rate))
    cleanup_reserve = round((bound_s / 3600.0) * rate, 6)
    effective_trip = round(float(cap) - float(margin) - cleanup_reserve, 6)
    ceiling = round(max(0.0, effective_trip), 6)
    return {
        "cap_ccu": round(float(cap), 6),
        "margin_ccu": round(float(margin), 6),
        "cleanup_bound_s": int(bound_s) if bound_s == int(bound_s) else round(bound_s, 6),
        "priced_rate": round(rate, 6),
        "cleanup_reserve_units": cleanup_reserve,
        "effective_trip_units": effective_trip,
        "ceiling_ccu": ceiling,
        "formula": CAP_TRIP_FORMULA,
        "cap_trip_formula": CAP_TRIP_FORMULA,
    }


def evaluate_cap_budget(
    *,
    cap: float,
    margin: float,
    cleanup_bound_s: float,
    priced_rate: float,
    max_rate: float | None = None,
    min_runtime_s: float | None = None,
    usage_retry_bound_s: float = USAGE_RETRY_BOUND_S,
    usage_blind_interval: float | None = None,
    detached_poll_lag: float | None = None,
) -> dict[str, Any]:
    trip = compute_cap_trip(cap=cap, margin=margin, cleanup_bound_s=cleanup_bound_s, priced_rate=priced_rate)
    eff_max_rate = round(float(max_rate), 6) if max_rate is not None else trip["priced_rate"]
    effective_trip = trip["effective_trip_units"]
    cleanup_reserve = trip["cleanup_reserve_units"]
    p_rate = trip["priced_rate"]
    bound_s = trip["cleanup_bound_s"]
    cap_v = trip["cap_ccu"]
    margin_v = trip["margin_ccu"]
    retry_budget = compute_usage_retry_budget(
        priced_rate=p_rate,
        margin=margin_v,
        usage_retry_bound_s=usage_retry_bound_s,
        usage_blind_interval=usage_blind_interval,
        detached_poll_lag=detached_poll_lag,
    )

    runtime_at_priced_rate_s = round((effective_trip / p_rate) * 3600.0, 2) if p_rate > 0.0 else 0.0
    runtime_at_max_rate_s = (
        round((effective_trip / eff_max_rate) * 3600.0, 2) if eff_max_rate > 0.0 else runtime_at_priced_rate_s
    )
    death_time_exact_s = max(0.0, (effective_trip / p_rate) * 3600.0) if p_rate > 0.0 else 0.0
    death_time_max_s = max(0.0, runtime_at_priced_rate_s)
    worst_case_cap_path = round(effective_trip + margin_v + cleanup_reserve, 6)
    worst_case_launcher_death_path = round(((death_time_exact_s + bound_s) / 3600.0) * p_rate, 6)
    worst_case_total_spend = round(max(worst_case_cap_path, worst_case_launcher_death_path), 6)
    assumptions = {
        "cap_path": "live launcher trips cap guard and runs cleanup_on_exit",
        "launcher_death_path": (
            "wall watcher survives launcher death to poll kill -0 every 1 s and run bounded colab stop"
        ),
    }

    tripped = False
    code: str | None = None
    why: str | None = None
    if effective_trip <= 0.0:
        tripped = True
        code = "CAP_TOO_SMALL_FOR_CLEANUP"
        why = (
            f"effective_trip = cap {cap_v} - margin {margin_v} - cleanup_reserve {cleanup_reserve} "
            f"(cleanup_bound_s {bound_s} / 3600 * priced_rate {p_rate}/h) = {effective_trip} <= 0"
        )
    elif min_runtime_s is not None and runtime_at_priced_rate_s < float(min_runtime_s):
        min_rt = (
            int(min_runtime_s)
            if float(min_runtime_s) == int(float(min_runtime_s))
            else round(float(min_runtime_s), 2)
        )
        tripped = True
        code = "CAP_TOO_SMALL_FOR_CLEANUP"
        why = (
            f"effective_trip = cap {cap_v} - margin {margin_v} - cleanup_reserve {cleanup_reserve} "
            f"(cleanup_bound_s {bound_s} / 3600 * priced_rate {p_rate}/h) = {effective_trip} units "
            f"leaves {runtime_at_priced_rate_s} s at {p_rate}/h < --min-runtime-s {min_rt} s"
        )
    elif not retry_budget["fits"]:
        tripped = True
        code = "CAP_MARGIN_TOO_SMALL_FOR_USAGE_RETRY"
        why = (
            f"usage_retry_spend = priced_rate {p_rate}/h * (cap_check_interval {retry_budget['cap_check_interval_s']} s / 3600; "
            f"cap_check_interval = blind_interval {retry_budget['usage_blind_interval_s']} s (T_retry "
            f"{retry_budget['usage_retry_bound_s']} s + 2 * poll_s + slack_s) + detached_poll_lag "
            f"{retry_budget['detached_poll_lag_s']} s) "
            f"= {retry_budget['usage_retry_spend_units']} units > margin / 2 = "
            f"{retry_budget['usage_retry_half_margin_units']} units "
            f"(margin {margin_v}; need --margin >= {retry_budget['usage_retry_min_margin_units']})"
        )

    rec: dict[str, Any] = {
        "check": "cap_budget",
        "ok": not tripped,
        "tripped": tripped,
        "code": code,
        "why": why,
        "cap": cap_v,
        "cap_ccu": cap_v,
        "margin": margin_v,
        "margin_ccu": margin_v,
        "cleanup_bound_s": bound_s,
        "priced_rate": p_rate,
        "max_rate": eff_max_rate,
        "usage_retry_bound_s": retry_budget["usage_retry_bound_s"],
        "usage_blind_interval_s": retry_budget["usage_blind_interval_s"],
        "detached_poll_lag_s": retry_budget["detached_poll_lag_s"],
        "cap_check_interval_s": retry_budget["cap_check_interval_s"],
        "usage_retry_spend_units": retry_budget["usage_retry_spend_units"],
        "usage_retry_half_margin_units": retry_budget["usage_retry_half_margin_units"],
        "usage_retry_min_margin_units": retry_budget["usage_retry_min_margin_units"],
        "reserve": cleanup_reserve,
        "cleanup_reserve": cleanup_reserve,
        "cleanup_reserve_units": cleanup_reserve,
        "effective_trip": effective_trip,
        "effective_trip_units": effective_trip,
        "runtime_to_trip_s": runtime_at_priced_rate_s,
        "runtime_at_priced_rate_s": runtime_at_priced_rate_s,
        "runtime_at_max_rate_s": runtime_at_max_rate_s,
        "death_time_max_s": death_time_max_s,
        "min_runtime_s": (
            None
            if min_runtime_s is None
            else (
                int(min_runtime_s)
                if float(min_runtime_s) == int(float(min_runtime_s))
                else round(float(min_runtime_s), 2)
            )
        ),
        "worst_case_cap_path": worst_case_cap_path,
        "worst_case_launcher_death_path": worst_case_launcher_death_path,
        "worst_case_total_spend": worst_case_total_spend,
        "worst_case_total_spend_units": worst_case_total_spend,
        "assumptions": assumptions,
        "formula": CAP_TRIP_FORMULA,
        "cap_trip_formula": CAP_TRIP_FORMULA,
    }
    if tripped and code and why:
        rec["refusal"] = {"code": code, "why": why}
    return rec


def format_dry_cap_budget(rec: dict[str, Any]) -> str:
    assumptions = rec.get("assumptions") or {}
    lines = [
        f"formula: {rec['formula']}",
        f"cap: {rec['cap']}",
        f"margin: {rec['margin']}",
        f"cleanup_bound_s: {rec['cleanup_bound_s']}",
        f"priced_rate: {rec['priced_rate']}/h",
        f"max_rate: {rec['max_rate']}/h",
        f"usage_retry_bound_s (T_retry): {rec['usage_retry_bound_s']}",
        f"usage_blind_interval_s (T_retry + 2 * poll_s + slack_s): {rec['usage_blind_interval_s']}",
        f"detached_poll_lag_s (2 * (poll_retry_sleep_s + poll_exec_timeout_s) + kill_grace_s): {rec['detached_poll_lag_s']}",
        f"cap_check_interval_s (usage_blind_interval_s + detached_poll_lag_s): {rec['cap_check_interval_s']}",
        (
            f"cap_check_interval_bound: {rec['usage_retry_spend_units']} "
            f"({rec['cap_check_interval_s']} / 3600 * {rec['priced_rate']} <= margin/2 {rec['usage_retry_half_margin_units']})"
        ),
        f"reserve (cleanup_reserve): {rec['cleanup_reserve_units']} ({rec['cleanup_bound_s']} / 3600 * {rec['priced_rate']})",
        f"effective_trip: {rec['effective_trip_units']} ({rec['cap']} - {rec['margin']} - {rec['cleanup_reserve_units']})",
        f"runtime_to_trip (priced_rate {rec['priced_rate']}/h): {rec['runtime_at_priced_rate_s']} s",
        f"runtime_to_trip (--max-rate {rec['max_rate']}/h): {rec['runtime_at_max_rate_s']} s",
        f"worst_case_cap_path: {rec['worst_case_cap_path']} (= cap {rec['cap']})",
        (
            f"worst_case_launcher_death_path: {rec['worst_case_launcher_death_path']} "
            f"((death_time <= {rec['death_time_max_s']} s + cleanup_bound_s {rec['cleanup_bound_s']} s) / 3600 * {rec['priced_rate']}/h)"
        ),
        (
            f"worst_case_total_spend: {rec['worst_case_total_spend']} "
            f"(= max(cap_path {rec['worst_case_cap_path']}, launcher_death_path {rec['worst_case_launcher_death_path']}) = cap {rec['cap']})"
        ),
        (
            f"assumptions: cap_path assumes {assumptions.get('cap_path', '')}; "
            f"launcher_death_path assumes {assumptions.get('launcher_death_path', '')}"
        ),
        json.dumps(rec),
    ]
    return "\n".join(lines)


def evaluate_cap_guard(
    *,
    mode: str = "live",
    cap: float = 0.05,
    margin: float = 0.01,
    cleanup_bound_s: float = 0.0,
    start_balance: float | None = None,
    current_balance: float | None = None,
    rate_ccu_per_hour: float = 0.0,
    elapsed_s: float = 0.0,
    usage_parse_error: str | None = None,
    phase: str | None = None,
    checkpoint: str | None = None,
) -> dict[str, Any]:
    trip = compute_cap_trip(
        cap=cap, margin=margin, cleanup_bound_s=cleanup_bound_s, priced_rate=rate_ccu_per_hour
    )
    ceiling = trip["ceiling_ccu"]
    extra: dict[str, Any] = {
        "cap_ccu": trip["cap_ccu"],
        "margin_ccu": trip["margin_ccu"],
        "cleanup_bound_s": trip["cleanup_bound_s"],
        "priced_rate": trip["priced_rate"],
        "cleanup_reserve_units": trip["cleanup_reserve_units"],
        "effective_trip_units": trip["effective_trip_units"],
        "formula": CAP_TRIP_FORMULA,
        "cap_trip_formula": CAP_TRIP_FORMULA,
    }
    if phase is not None:
        extra["phase"] = phase
    if checkpoint is not None:
        extra["checkpoint"] = checkpoint
    rate_est = round(max(0.0, (float(rate_ccu_per_hour) * float(elapsed_s)) / 3600.0), 6)
    neg_bal = (start_balance is not None and float(start_balance) < 0.0) or (
        current_balance is not None and float(current_balance) < 0.0
    )
    if mode == "stub":
        parse_err = usage_parse_error or (
            "COLAB_USAGE_PARSE_FAILED: negative balance is impossible" if neg_bal
            else "COLAB_USAGE_PARSE_FAILED: missing start_balance or current_balance in non-fake mode"
            if (start_balance is None or current_balance is None) else None
        )
        if parse_err:
            return {
                "mode": mode, "tripped": True, "code": "COLAB_USAGE_PARSE_FAILED",
                "spend_ccu": None, "ceiling_ccu": ceiling, **extra, "usage_parse_error": parse_err,
            }
        drop = round(max(0.0, float(start_balance) - float(current_balance)), 6)
        spend = round(max(drop, rate_est), 6)
    else:
        # Running paid windows price spend strictly as own_rate * elapsed; flaky/missing/negative
        # colab usage reads or shared account drops are logged only and never trip a running window.
        if usage_parse_error:
            extra["usage_warning"] = usage_parse_error
        elif neg_bal:
            extra["usage_warning"] = "negative_balance_ignored"
        elif start_balance is None or current_balance is None:
            extra["usage_warning"] = "missing_balance_ignored"
        if start_balance is not None and current_balance is not None and not neg_bal:
            extra["account_balance_drop_ccu"] = round(max(0.0, float(start_balance) - float(current_balance)), 6)
        spend = rate_est
    tripped = spend >= ceiling
    return {
        "mode": mode,
        "tripped": tripped,
        "code": "CAP_GUARD_TRIPPED" if tripped else None,
        "spend_ccu": spend,
        "ceiling_ccu": ceiling,
        **extra,
    }


OFFLINE_CAP_MODE = "live_offline"


def evaluate_offline_cap_projection(
    *,
    cap: float,
    margin: float,
    cleanup_bound_s: float,
    rate_ccu_per_hour: float,
    elapsed_s: float,
    start_balance: float | None = None,
    cached_balance: float | None = None,
    balance_age_s: float | None = None,
    card_class: str | None = None,
) -> dict[str, Any]:
    """The detached loop's local cap projection when a remote poll fails: spend = own_rate * elapsed_s."""
    del card_class
    rate_raw = float(rate_ccu_per_hour)
    rate_ok = math.isfinite(rate_raw) and rate_raw > 0.0
    rate_v = rate_raw if rate_ok else 0.0
    trip = compute_cap_trip(cap=cap, margin=margin, cleanup_bound_s=cleanup_bound_s, priced_rate=rate_v)
    ceiling = trip["ceiling_ccu"]
    age_s = max(0.0, float(balance_age_s)) if balance_age_s is not None and math.isfinite(float(balance_age_s)) else float(elapsed_s)
    cached_drop = (
        round(max(0.0, float(start_balance) - float(cached_balance)), 6)
        if start_balance is not None and cached_balance is not None
        else None
    )
    projected = round(max(0.0, (rate_v * float(elapsed_s)) / 3600.0), 6)
    tripped = projected >= ceiling
    rec: dict[str, Any] = {
        "mode": OFFLINE_CAP_MODE,
        "result": "trip" if tripped else "no_trip_projection",
        "fresh_pass": False,
        "tripped": tripped,
        "code": "CAP_GUARD_TRIPPED" if tripped else None,
        "balance_source": "local_rate_only",
        "balance_age_s": round(age_s, 3),
        "elapsed_s": round(float(elapsed_s), 6),
        "projected_spend_ccu": projected,
        "cached_drop_ccu": cached_drop,
        "spend_ccu": projected,
        "ceiling_ccu": ceiling,
        "cap_ccu": trip["cap_ccu"],
        "margin_ccu": trip["margin_ccu"],
        "cleanup_bound_s": trip["cleanup_bound_s"],
        "priced_rate": trip["priced_rate"],
        "cleanup_reserve_units": trip["cleanup_reserve_units"],
        "effective_trip_units": trip["effective_trip_units"],
        "formula": CAP_TRIP_FORMULA,
        "cap_trip_formula": CAP_TRIP_FORMULA,
    }
    if not rate_ok:
        rec["rate_warning"] = f"non_positive_or_non_finite_rate_fallback:{rate_ccu_per_hour!r}"
    return rec


def parse_vitals_log(vitals_text: str) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for block in _vitals_blocks(vitals_text):
        if not _HARNESS_LINE_RE.search(block):
            continue
        lines = block.splitlines()
        header = lines[0] if lines else ""
        ts = header.split()[0] if header else ""
        phase = None
        worker_count = 0
        oom_kill = False
        setup_bytes: int | None = None
        in_proc = False
        for line in lines[1:]:
            if OOM_KILL_RE.search(line):
                oom_kill = True
            if line.startswith("SETUP_BYTES:"):
                in_proc = False
                raw_sb = line[len("SETUP_BYTES:") :].strip()
                if raw_sb.isdigit():
                    setup_bytes = int(raw_sb)
                continue
            if line.startswith("PROC:"):
                in_proc = True
                continue
            if line.startswith("HARNESS:"):
                in_proc = False
                payload = line[len("HARNESS:") :].strip()
                try:
                    phase = json.loads(payload).get("phase")
                except Exception:
                    m = re.search(r'"phase"\s*:\s*"([^"]+)"', payload) or re.search(
                        r"phase:\s*([a-z0-9_-]+)", payload, re.I
                    )
                    phase = m.group(1) if m else None
                continue
            if in_proc and WORKER_PROC_RE.search(line):
                worker_count += 1
        samples.append(
            {
                "timestamp": ts,
                "phase": phase,
                "worker_proc_count": worker_count,
                "oom_kill": oom_kill,
                "setup_bytes": setup_bytes,
            }
        )
    return samples


VALID_HARNESS_PHASES = ("setup", "run", "bundle")


def evaluate_vitals_and_stall_guard(
    *,
    vitals_text: str,
    idle_seconds: float = 0.0,
    setup_idle_seconds: float | None = None,
    stall_s: float = 300.0,
    setup_stall_s: float = 600.0,
) -> dict[str, Any]:
    raw_blocks = _vitals_blocks(vitals_text)
    samples = parse_vitals_log(vitals_text)
    current_phase: str | None = None
    if samples:
        last = samples[-1]
        raw_phase = last["phase"]
        if not isinstance(raw_phase, str) or not raw_phase.strip():
            return {
                "tripped": True,
                "code": "VITALS_PHASE_UNREADABLE",
                "cgroup_oom": False,
                "reason": "Newest complete vitals block has no HARNESS phase; refusing rather than assuming setup",
                "samples_count": len(samples),
            }
        for sample in samples:
            sp = sample["phase"]
            if isinstance(sp, str) and sp.strip() and sp.strip() not in VALID_HARNESS_PHASES:
                return {
                    "tripped": True,
                    "code": "VITALS_PHASE_INVALID",
                    "cgroup_oom": False,
                    "reason": (
                        f"Unexpected HARNESS phase {sp.strip()!r}; "
                        f"expected one of {', '.join(VALID_HARNESS_PHASES)}"
                    ),
                    "samples_count": len(samples),
                }
        current_phase = raw_phase.strip()
        if (
            current_phase in VALID_HARNESS_PHASES
            and last["worker_proc_count"] == 0
            and last.get("oom_kill")
        ):
            return {
                "tripped": True,
                "code": "DEAD_HARNESS_TRIPPED",
                "cgroup_oom": True,
                "reason": f"cgroup OOM kill detected in phase={current_phase} with 0 active worker processes",
                "samples_count": len(samples),
            }
    elif len(raw_blocks) >= 2:
        return {
            "tripped": True,
            "code": "VITALS_PHASE_UNREADABLE",
            "cgroup_oom": False,
            "reason": f"{len(raw_blocks)} vitals blocks and none is complete (missing HARNESS: line); refusing rather than assuming setup",
            "samples_count": 0,
        }
    if len(samples) >= 2:
        last_two = samples[-2:]
        if all(
            isinstance(s["phase"], str) and s["phase"].strip() == "run" and s["worker_proc_count"] == 0
            for s in last_two
        ):
            return {
                "tripped": True,
                "code": "DEAD_HARNESS_TRIPPED",
                "cgroup_oom": any(bool(s.get("oom_kill")) for s in last_two),
                "reason": "2 consecutive vitals samples in phase=run with 0 active worker processes",
                "samples_count": len(samples),
            }
    if current_phase == "setup":
        eff_setup_idle = float(setup_idle_seconds if setup_idle_seconds is not None else idle_seconds)
        if eff_setup_idle >= float(setup_stall_s):
            return {
                "tripped": True,
                "code": "SETUP_STALL_TRIPPED",
                "cgroup_oom": False,
                "reason": f"No new setup.log output (SETUP_BYTES unchanged) in phase=setup for {eff_setup_idle}s (setup_stall_s={setup_stall_s}s)",
                "samples_count": len(samples),
            }
    elif current_phase == "bundle":
        # Post-train bundling (manifest, scrub, tar -czf of multi-GiB checkpoints) emits no run output
        # while compressing; idle_seconds is reset on phase transition in colab_window.sh and allowed up
        # to setup_stall_s (default 600s) before tripping STALL_GUARD_TRIPPED.
        if float(idle_seconds) >= float(setup_stall_s):
            return {
                "tripped": True,
                "code": "STALL_GUARD_TRIPPED",
                "cgroup_oom": False,
                "reason": f"No output row or vitals progress in phase=bundle for {idle_seconds}s (bundle_stall_s={setup_stall_s}s)",
                "samples_count": len(samples),
            }
    elif float(idle_seconds) >= float(stall_s):
        return {
            "tripped": True,
            "code": "STALL_GUARD_TRIPPED",
            "cgroup_oom": False,
            "reason": f"No output row or vitals progress for {idle_seconds}s (stall_s={stall_s}s)",
            "samples_count": len(samples),
        }
    return {
        "tripped": False,
        "code": None,
        "cgroup_oom": False,
        "reason": None,
        "samples_count": len(samples),
    }


# The host-RAM guard measures PRIVATE memory: pages the kernel cannot drop to make room, so
# pages that end in an OOM kill when they outgrow the VM. That is anonymous memory plus shmem
# (tmpfs, /dev/shm, PyTorch's shared-memory tensors): Colab VMs run without swap, so shmem is
# as unreclaimable as anon. It is NOT cgroup memory.current, which also counts the page cache
# (file pages: a downloaded or mmap'd model), and the kernel reclaims that cache before it
# OOM-kills anything. Window sdlab-l3-rung-g4a (2026-11-06) tripped on memory.current: 173,117
# MiB of which AnonPages was 52,492 MiB, while MemAvailable still read 125,790 MiB.
#
# Two checks, either one trips HOST_RAM_PROJECTION_EXCEEDED:
#   1. (private + delta) x factor > ceiling, ceiling = min(MemTotal, cgroup memory.max when it is
#      a number; `max` is no cgroup limit).
#   2. MemAvailable - delta x factor < floor. MemAvailable is the kernel's own estimate of what
#      can be had without swapping, reclaimable cache included; it also falls for unreclaimable
#      memory that is not anon (kernel slab, page tables, driver-pinned buffers), which check 1
#      cannot see. The floor (2048 MiB) is the one the lane-3 walks stop at (walk_probe.py
#      HOST_RAM_CEILING: MemAvailable < 2 GiB).
MEM_AVAILABLE_FLOOR_MB = 2048.0
RAM_SAFETY_FACTOR = 1.05
# Field lines end in a newline: a number the poll caught mid-write ("anon 55" at the end of the
# buffer) is not a reading.
_KB_FIELD_RE = {
    name: re.compile(rf"^MEM:[ \t]*{name}:[ \t]*(\d+)[ \t]*kB[ \t]*\r?\n", re.M)
    for name in ("MemTotal", "MemAvailable", "AnonPages", "Shmem")
}
_CGROUP_STAT_RE = re.compile(r"^CGROUP_MEM_STAT:[ \t]*(anon|shmem|file)[ \t]+(\d+)[ \t]*\r?\n", re.M)
_CGROUP_MAX_RE = re.compile(r"^CGROUP_MEM_MAX:[ \t]*(\S+)[ \t]*\r?\n", re.M)
_CGROUP_CUR_RE = re.compile(r"^CGROUP_MEM_CURRENT:[ \t]*(\d+)[ \t]*\r?\n", re.M)
_HARNESS_LINE_RE = re.compile(r"^HARNESS:.*\r?\n", re.M)
# The newest complete sample must be the newest or the one before it; older than that and the
# guard would be steering on a stale reading (HOST_RAM_UNREADABLE).
RAM_READING_MAX_BLOCKS_BACK = 1


def _ram_from_block(block: str) -> dict[str, Any] | None:
    """The private-memory reading of ONE complete vitals sample, or None.

    Complete means the emitter reached its last line (HARNESS:) and the sample has MemTotal,
    MemAvailable and at least one private-memory source: the full cgroup memory.stat triple (anon,
    shmem, file) and/or /proc/meminfo AnonPages (+ Shmem). Both sources are recorded when present,
    and the larger private reading is selected for projection and ceiling checks so a cgroup slice
    that misses the trainer never under-reads private memory. A sample cut mid-write anywhere is
    None, so a torn tail never reads as 0 MB private or as a missing MemTotal."""
    if not _HARNESS_LINE_RE.search(block):
        return None
    kb: dict[str, float] = {}
    for name, rx in _KB_FIELD_RE.items():
        found = rx.findall(block)
        if found:
            kb[name] = round(int(found[-1]) / 1024.0, 1)
    if "MemTotal" not in kb or "MemAvailable" not in kb:
        return None
    stat = {k: int(v) for k, v in _CGROUP_STAT_RE.findall(block)}
    if {"anon", "shmem", "file"} <= stat.keys():
        cgroup_anon_mb: float | None = round(stat["anon"] / 1048576.0, 1)
        cgroup_shmem_mb: float | None = round(stat["shmem"] / 1048576.0, 1)
        cgroup_private_mb: float | None = round(cgroup_anon_mb + cgroup_shmem_mb, 1)
    else:
        cgroup_anon_mb = None
        cgroup_shmem_mb = None
        cgroup_private_mb = None
    if "AnonPages" in kb:
        meminfo_anon_mb: float | None = kb["AnonPages"]
        meminfo_shmem_mb: float | None = kb.get("Shmem", 0.0)
        meminfo_private_mb: float | None = round(meminfo_anon_mb + meminfo_shmem_mb, 1)
        meminfo_source = "meminfo:AnonPages+Shmem" if "Shmem" in kb else "meminfo:AnonPages"
    else:
        meminfo_anon_mb = None
        meminfo_shmem_mb = None
        meminfo_private_mb = None
        meminfo_source = None
    if cgroup_private_mb is None and meminfo_private_mb is None:
        return None
    if meminfo_private_mb is not None and (
        cgroup_private_mb is None or meminfo_private_mb > cgroup_private_mb
    ):
        private_mb = meminfo_private_mb
        anon_mb = meminfo_anon_mb
        shmem_mb = meminfo_shmem_mb
        source = meminfo_source
    else:
        private_mb = cgroup_private_mb
        anon_mb = cgroup_anon_mb
        shmem_mb = cgroup_shmem_mb
        source = "cgroup_memory.stat:anon+shmem"
    cg_max_raw = _CGROUP_MAX_RE.findall(block)
    cg_max_mb = None
    if cg_max_raw and cg_max_raw[-1].isdigit():
        cg_max_mb = round(int(cg_max_raw[-1]) / 1048576.0, 1)
    cg_cur = _CGROUP_CUR_RE.findall(block)
    return {
        "timestamp": block.split()[0] if block.split() else "",
        "private_mb": private_mb,
        "anon_mb": anon_mb,
        "shmem_mb": shmem_mb,
        "source": source,
        "cgroup_private_mb": cgroup_private_mb,
        "cgroup_anon_mb": cgroup_anon_mb,
        "cgroup_shmem_mb": cgroup_shmem_mb,
        "meminfo_private_mb": meminfo_private_mb,
        "meminfo_anon_mb": meminfo_anon_mb,
        "meminfo_shmem_mb": meminfo_shmem_mb,
        "mem_total_mb": kb["MemTotal"],
        "mem_available_mb": kb["MemAvailable"],
        "cgroup_max_mb": cg_max_mb,
        "cgroup_max_raw": cg_max_raw[-1] if cg_max_raw else None,
        "cgroup_current_mb_not_used": round(int(cg_cur[-1]) / 1048576.0, 1) if cg_cur else None,
    }


# A sample header is split on wherever it appears, not only at column 0: job output without a
# trailing newline (a "\r" progress bar) can put "=== VITALS" mid-line. Each block is then cut
# at the end of its first HARNESS: line, so no block can combine fields of two samples.
_VITALS_HEADER_RE = re.compile(r"===[ \t]*VITALS[ \t]+")


def _vitals_blocks(vitals_text: str) -> list[str]:
    blocks = []
    for part in _VITALS_HEADER_RE.split(vitals_text)[1:]:
        m = _HARNESS_LINE_RE.search(part)
        if m:
            part = part[: m.end()]
        if part.strip():
            blocks.append(part)
    return blocks


def host_ram_reading(vitals_text: str) -> dict[str, Any] | None:
    """The newest COMPLETE vitals sample's private-memory reading (see _ram_from_block), or None.

    Private memory records both cgroup memory.stat anon + shmem and /proc/meminfo AnonPages + Shmem
    from that one sample and selects the larger of the two. cgroup memory.current is recorded for
    the record only and never used. `blocks_back` is how many samples older than the newest it is."""
    blocks = _vitals_blocks(vitals_text)
    for back, block in enumerate(reversed(blocks)):
        reading = _ram_from_block(block)
        if reading is not None:
            reading["blocks_back"] = back
            reading["blocks_seen"] = len(blocks)
            return reading
    return None


def host_ram_status(vitals_text: str | None) -> dict[str, Any]:
    """What the live RAM guard can do with this vitals stream. No default value ever stands in for
    a reading:
      - "no_vm": no vitals stream yet (the pre-open check, or before the exec starts): skip.
      - "waiting": fewer than two samples and none complete (the first one is still being
        written): skip this poll.
      - "ok": a complete sample that is the newest or the one before it (a torn newest sample
        falls back to the previous one).
      - "unreadable": two or more samples and neither the newest nor the one before is complete.
        Samples come 15 s apart and each is written in milliseconds, so this is an emitter that
        does not print what the guard needs, not a race: the guard is blind, and the window stops
        (HOST_RAM_UNREADABLE) rather than run unguarded."""
    if vitals_text is None:
        return {"state": "no_vm", "reading": None, "blocks_seen": 0}
    blocks = _vitals_blocks(vitals_text)
    reading = host_ram_reading(vitals_text)
    if reading is not None and reading["blocks_back"] <= RAM_READING_MAX_BLOCKS_BACK:
        return {"state": "ok", "reading": reading, "blocks_seen": len(blocks)}
    if len(blocks) < 2 and reading is None:
        return {"state": "waiting", "reading": None, "blocks_seen": len(blocks)}
    newest = "none" if reading is None else f"the newest is {reading['blocks_back']} samples back"
    return {
        "state": "unreadable",
        "reading": None,
        "blocks_seen": len(blocks),
        "why": (f"{len(blocks)} vitals samples and neither of the last two is complete ({newest}); a complete "
                "sample has MemTotal, MemAvailable and AnonPages or memory.stat anon/shmem/file before HARNESS:"),
    }


# Every line the vitals emitters print (the `=== VITALS` loop in launch_lane1_stub.sh and
# launch_lane3_stub.sh, and the fake CLI's emit_vitals). The stall guard counts only run output,
# so these lines must never count as progress; tests/colab/test_host_ram_guard.py checks every
# emitter against this list, so a line added to an emitter cannot slip past it.
VITALS_LINE_PREFIXES = (
    "=== VITALS",
    "CGROUP_MEM_CURRENT:",
    "CGROUP_MEM_MAX:",
    "CGROUP_MEM:",
    "CGROUP_MEM_STAT:",
    "MEM:",
    "SETUP_BYTES:",
    "PROC:",
    "HARNESS:",
)
# A `ps -ef` row for a worker in a PROC: section ("root  2216  2101 21 19:01 ? 00:00:02 ...run.py
# ..."), or the fake's shorter "<pid> <cmd>" row. The old shell filter matched only rows that
# start with a number, so every real `ps -ef` row (it starts with the user) counted as progress.
_PS_WORKER_ROW_RE = re.compile(r"^\s*(?:[A-Za-z_][\w.+-]*\s+)?\d+\s+.*" + WORKER_PROC_RE.pattern, re.I)


def is_vitals_line(line: str) -> bool:
    stripped = line.rstrip("\r\n")
    if stripped.startswith(VITALS_LINE_PREFIXES[1:]) or re.match(r"^===\s*VITALS", stripped):
        return True
    return bool(_PS_WORKER_ROW_RE.match(stripped))


def run_output_bytes(vitals_text: str) -> int:
    """Bytes of the exec stream that are not vitals lines: what the stall guard counts as progress."""
    return sum(len(line.encode("utf-8", errors="replace")) for line in vitals_text.splitlines(keepends=True)
               if not is_vitals_line(line))


def evaluate_host_ram_projection(
    *,
    current_anon_mb: float,
    projected_delta_mb: float,
    mem_total_mb: float,
    cgroup_max_mb: float | None = None,
    mem_available_mb: float | None = None,
    mem_available_floor_mb: float = MEM_AVAILABLE_FLOOR_MB,
    safety_factor: float = RAM_SAFETY_FACTOR,
    source: str | None = None,
) -> dict[str, Any]:
    """Both host-RAM checks (see the comment above MEM_AVAILABLE_FLOOR_MB). The record carries every
    number either check used, tripped or not, so guards.log shows why a window stopped."""
    limit_mb = float(mem_total_mb)
    limit_source = "MemTotal"
    if cgroup_max_mb is not None and float(cgroup_max_mb) < limit_mb:
        limit_mb = float(cgroup_max_mb)
        limit_source = "cgroup memory.max"
    factor = float(safety_factor)
    delta = float(projected_delta_mb)
    projected_mb = round((float(current_anon_mb) + delta) * factor, 1)
    tripped_on: list[str] = []
    why: list[str] = []
    if projected_mb > limit_mb:
        tripped_on.append("private_projection")
        why.append(f"private {float(current_anon_mb):.1f} MB ({source or 'unknown source'}) + delta {delta:.1f} MB "
                   f"x {factor} = {projected_mb:.1f} MB > ceiling {limit_mb:.1f} MB ({limit_source})")
    avail_after = None
    if mem_available_mb is not None:
        avail_after = round(float(mem_available_mb) - delta * factor, 1)
        if avail_after < float(mem_available_floor_mb):
            tripped_on.append("mem_available_floor")
            why.append(f"MemAvailable {float(mem_available_mb):.1f} MB - delta {delta:.1f} MB x {factor} = "
                       f"{avail_after:.1f} MB < floor {float(mem_available_floor_mb):.1f} MB")
    tripped = bool(tripped_on)
    return {
        "check": "host_ram",
        "ok": not tripped,
        "tripped": tripped,
        "code": "HOST_RAM_PROJECTION_EXCEEDED" if tripped else None,
        "tripped_on": tripped_on,
        "source": source,
        "private_mb": round(float(current_anon_mb), 1),
        "delta_mb": round(delta, 1),
        "factor": factor,
        "projected_mb": projected_mb,
        "limit_mb": limit_mb,
        "limit_source": limit_source,
        "mem_total_mb": float(mem_total_mb),
        "cgroup_max_mb": None if cgroup_max_mb is None else float(cgroup_max_mb),
        "mem_available_mb": None if mem_available_mb is None else float(mem_available_mb),
        "mem_available_after_delta_mb": avail_after,
        "mem_available_floor_mb": float(mem_available_floor_mb),
        "why": "; ".join(why) if why else None,
    }


def check_host_ram_projection(
    *,
    current_anon_mb: float,
    projected_delta_mb: float,
    mem_total_mb: float,
    cgroup_max_mb: float | None = None,
    safety_factor: float = RAM_SAFETY_FACTOR,
    mem_available_mb: float | None = None,
    mem_available_floor_mb: float = MEM_AVAILABLE_FLOOR_MB,
    source: str | None = None,
) -> dict[str, Any]:
    """evaluate_host_ram_projection, raising ValueError (HOST_RAM_PROJECTION_EXCEEDED: <why>) on a trip."""
    rec = evaluate_host_ram_projection(
        current_anon_mb=current_anon_mb,
        projected_delta_mb=projected_delta_mb,
        mem_total_mb=mem_total_mb,
        cgroup_max_mb=cgroup_max_mb,
        mem_available_mb=mem_available_mb,
        mem_available_floor_mb=mem_available_floor_mb,
        safety_factor=safety_factor,
        source=source,
    )
    if rec["tripped"]:
        raise ValueError(f"HOST_RAM_PROJECTION_EXCEEDED: {rec['why']}")
    return rec


def run_between_item_fetch(
    *,
    remote_dir: Path,
    local_dir: Path,
    next_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    local_dir.mkdir(parents=True, exist_ok=True)
    current_json = remote_dir / "current.json"
    copied: list[str] = []
    previous_item = None
    if current_json.exists():
        previous_item = json.loads(current_json.read_text(encoding="utf-8"))
        for rel in previous_item.get("files") or []:
            src = remote_dir / rel
            if src.exists():
                dst = local_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(rel)
        shutil.copy2(current_json, local_dir / "current.json")
    if next_item is not None:
        current_json.write_text(json.dumps(next_item, indent=2) + "\n", encoding="utf-8")
    return {"copied_files": copied, "previous_item": previous_item}


# >>> sdlab-download-prep
import errno as _dl_errno  # noqa: E402
import hashlib as _dl_hashlib  # noqa: E402
import json as _dl_json  # noqa: E402
import os as _dl_os  # noqa: E402
import re as _dl_re  # noqa: E402
import shutil as _dl_shutil  # noqa: E402
from pathlib import Path as _DlPath  # noqa: E402
from typing import Any as _DlAny  # noqa: E402


def _dl_split_free_bytes(root: _DlPath, free_bytes_override: int | None = None) -> int:
    if free_bytes_override is not None:
        return int(free_bytes_override)
    if _dl_os.environ.get("FAKE_VM_SITE") and _dl_os.environ.get("FAKE_VM_DL_SPLIT_FREE_BYTES", "").strip():
        return int(_dl_os.environ["FAKE_VM_DL_SPLIT_FREE_BYTES"].strip())
    probe = _DlPath(root)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return int(_dl_shutil.disk_usage(str(probe)).free)


def _unlink_dl_prefix_files(root: _DlPath, prefix: str) -> None:
    if not root.is_dir():
        return
    for fp in root.iterdir():
        if fp.name.startswith(prefix + ".") and fp.is_file():
            try:
                fp.unlink(missing_ok=True)
            except OSError:
                pass


def _dl_safe_prefix(rel: str) -> str:
    cleaned = _dl_re.sub(r"[^A-Za-z0-9._-]", "_", rel)
    if len(cleaned) <= 48:
        safe_name = cleaned
    else:
        digest = _dl_hashlib.sha256(rel.encode("utf-8")).hexdigest()[:8]
        safe_name = f"{cleaned[:39]}_{digest}"
    return f".sdlab_dl_{safe_name}"


def prepare_single_content_download(
    content_root: str | _DlPath,
    rel: str,
    chunk_bytes: int,
    *,
    free_bytes_override: int | None = None,
    emit: bool = True,
) -> dict[str, _DlAny]:
    """Prepare one `/content/<rel>` file for verified rig download.

    Single canonical implementation shared by `remote_runner.py`, `lane3_bundle_now.py`, and
    `colab_window.sh` (`_colab_write_download_prepare_py`). When `size > chunk_bytes`, verifies free
    disk before splitting and catches `OSError` (`ENOSPC`) during part/manifest writes, unlinking
    partial `.sdlab_dl_*` files and returning `split_failed: True` (`DOWNLOAD_SPLIT_DISK_LOW`) so a
    disk-full split never crashes or falls through to an unchunked single GET.
    """
    root = _DlPath(content_root)
    vm_file = root / rel
    if not vm_file.is_file():
        rec: dict[str, _DlAny] = {"rel": rel, "exists": False, "chunk_bytes": int(chunk_bytes)}
        if emit:
            print("SDLAB_DOWNLOAD_PREPARE_JSON " + _dl_json.dumps(rec), flush=True)
        return rec

    size = vm_file.stat().st_size
    if size <= chunk_bytes:
        h = _dl_hashlib.sha256()
        with vm_file.open("rb") as fh:
            for blk in iter(lambda: fh.read(1 << 20), b""):
                h.update(blk)
        rec = {
            "rel": rel,
            "exists": True,
            "split": False,
            "whole_bytes": size,
            "whole_sha256": h.hexdigest(),
            "chunk_bytes": int(chunk_bytes),
            "part_count": 1,
        }
        if emit:
            print("SDLAB_DOWNLOAD_PREPARE_JSON " + _dl_json.dumps(rec), flush=True)
        return rec

    prefix = _dl_safe_prefix(rel)
    _unlink_dl_prefix_files(root, prefix)

    free_b = _dl_split_free_bytes(root, free_bytes_override)
    headroom = 16 * 1024 * 1024
    if free_b < size + headroom:
        why = (
            f"/content/{rel} ({size} bytes > chunk_bytes={chunk_bytes}) needs {size} free bytes plus "
            f"{headroom} bytes of headroom on {root} for the VM split copy, but only {free_b} bytes are free"
        )
        rec = {
            "rel": rel,
            "exists": True,
            "split": True,
            "split_failed": True,
            "error_code": "DOWNLOAD_SPLIT_DISK_LOW",
            "why": why,
            "whole_bytes": size,
            "free_bytes": free_b,
            "chunk_bytes": int(chunk_bytes),
        }
        if emit:
            print("SDLAB_DOWNLOAD_PREPARE_JSON " + _dl_json.dumps(rec), flush=True)
        return rec

    whole_h = _dl_hashlib.sha256()
    parts: list[dict[str, _DlAny]] = []
    idx = 0
    inject_enospc_raw = (
        _dl_os.environ.get("FAKE_VM_DL_SPLIT_ENOSPC_ON_PART", "").strip()
        if _dl_os.environ.get("FAKE_VM_SITE")
        else ""
    )
    inject_enospc_part = int(inject_enospc_raw) if inject_enospc_raw.isdigit() else -1
    try:
        with vm_file.open("rb") as fh:
            while True:
                remaining = int(chunk_bytes)
                part_name = f"{prefix}.part.{idx:04d}"
                part_path = root / part_name
                part_h = _dl_hashlib.sha256()
                part_b = 0
                first_blk = fh.read(min(1 << 20, remaining))
                if not first_blk:
                    break
                if idx == inject_enospc_part:
                    raise OSError(_dl_errno.ENOSPC, "No space left on device")
                with part_path.open("wb") as pfh:
                    pfh.write(first_blk)
                    part_h.update(first_blk)
                    whole_h.update(first_blk)
                    part_b += len(first_blk)
                    remaining -= len(first_blk)
                    while remaining > 0:
                        blk = fh.read(min(1 << 20, remaining))
                        if not blk:
                            break
                        pfh.write(blk)
                        part_h.update(blk)
                        whole_h.update(blk)
                        part_b += len(blk)
                        remaining -= len(blk)
                parts.append({
                    "index": idx,
                    "remote_path": f"/content/{part_name}",
                    "bytes": part_b,
                    "sha256": part_h.hexdigest(),
                })
                idx += 1

        whole_sha = whole_h.hexdigest()
        manifest_name = f"{prefix}.manifest.json"
        manifest_payload = {
            "remote": f"/content/{rel}",
            "prefix": prefix,
            "split": True,
            "whole_bytes": size,
            "whole_sha256": whole_sha,
            "chunk_bytes": int(chunk_bytes),
            "part_count": len(parts),
            "parts": parts,
        }
        (root / manifest_name).write_text(
            _dl_json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    except OSError as exc:
        _unlink_dl_prefix_files(root, prefix)
        free_after = _dl_split_free_bytes(root, free_bytes_override)
        why = (
            f"splitting /content/{rel} ({size} bytes) into {chunk_bytes}-byte parts failed at part {idx} "
            f"({exc}; free_bytes={free_after})"
        )
        rec = {
            "rel": rel,
            "exists": True,
            "split": True,
            "split_failed": True,
            "error_code": "DOWNLOAD_SPLIT_DISK_LOW",
            "why": why,
            "whole_bytes": size,
            "free_bytes": free_after,
            "chunk_bytes": int(chunk_bytes),
        }
        if emit:
            print("SDLAB_DOWNLOAD_PREPARE_JSON " + _dl_json.dumps(rec), flush=True)
        return rec

    rec = {
        "rel": rel,
        "exists": True,
        "split": True,
        "prefix": prefix,
        "manifest_remote": f"/content/{manifest_name}",
        "whole_bytes": size,
        "whole_sha256": whole_sha,
        "chunk_bytes": int(chunk_bytes),
        "part_count": len(parts),
    }
    if emit:
        print("SDLAB_DOWNLOAD_PREPARE_JSON " + _dl_json.dumps(rec), flush=True)
    return rec


def prepare_content_downloads(
    content_root: str | _DlPath,
    chunk_bytes: int,
    *,
    free_bytes_override: int | None = None,
    emit: bool = True,
) -> list[dict[str, _DlAny]]:
    """Record whole-file sha256 (and split into `chunk_bytes` parts + manifest when larger) for any
    `*.tar.gz` bundle in `content_root` inside the single remote `colab exec` cell."""
    root = _DlPath(content_root)
    records: list[dict[str, _DlAny]] = []
    if not root.is_dir() or chunk_bytes <= 0:
        return records
    for vm_file in sorted(root.iterdir()):
        if not vm_file.is_file() or vm_file.name.startswith(".sdlab_") or not vm_file.name.endswith(".tar.gz"):
            continue
        rec = prepare_single_content_download(
            root,
            vm_file.name,
            int(chunk_bytes),
            free_bytes_override=free_bytes_override,
            emit=emit,
        )
        records.append(rec)
    if emit:
        print(f"SDLAB_DOWNLOAD_PREPARE_DONE chunk_bytes={chunk_bytes}", flush=True)
    return records
# <<< sdlab-download-prep


DETACHED_LIVE_LOG = ".sdlab_live.log"
DETACHED_LIVE_ERR = ".sdlab_live.err.log"
DETACHED_LIVE_META = ".sdlab_live.meta.json"
DETACHED_LIVE_RC = ".sdlab_live.rc"
DETACHED_LIVE_DONE = ".sdlab_live.done"
DETACHED_STARTED_PREFIX = "SDLAB_DETACHED_STARTED "
DETACHED_POLL_PREFIX = "SDLAB_POLL_ENVELOPE "
DETACHED_KILLED_PREFIX = "SDLAB_DETACHED_KILLED "
DETACHED_POLL_MAX_BYTES_DEFAULT = 262144
DETACHED_STDERR_TAIL_BYTES = 262144


def _atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _resolve_bash_bin(env: dict[str, str]) -> str:
    git_bash = "C:/Program Files/Git/bin/bash.exe"
    if os.name == "nt" and os.path.exists(git_bash):
        return git_bash
    found = shutil.which("bash", path=env.get("PATH"))
    return found or "bash"


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover - Windows host fallback
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return int(code.value) == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover
        return True
    proc_stat = Path(f"/proc/{int(pid)}/stat")
    if proc_stat.exists():
        try:
            state = proc_stat.read_text(encoding="utf-8").rsplit(")", 1)[-1].split()[0]
            if state == "Z":
                return False
        except (OSError, IndexError):  # pragma: no cover
            pass
    return True


def clear_detached_state(content_root: str | Path) -> None:
    root = Path(content_root)
    for rel in (DETACHED_LIVE_LOG, DETACHED_LIVE_ERR, DETACHED_LIVE_META, DETACHED_LIVE_RC, DETACHED_LIVE_DONE):
        p = root / rel
        if p.exists() or p.is_symlink():
            p.unlink(missing_ok=True)


def _pgid_has_live_member(pgid: int) -> bool:
    if pgid <= 1 or os.name == "nt" or pgid == os.getpgrp():
        return False
    proc_root = Path("/proc")
    if proc_root.is_dir():
        for stat_p in proc_root.glob("[0-9]*/stat"):
            try:
                pid_val = int(stat_p.parent.name)
                if pid_val == os.getpid():
                    continue
                fields = stat_p.read_text(encoding="utf-8").rsplit(")", 1)[-1].split()
                if fields[0] == "Z":
                    continue
                if int(fields[2]) == pgid or int(fields[3]) == pgid:
                    return True
            except (OSError, ValueError, IndexError):
                continue
        return False
    try:  # pragma: no cover - non-procfs POSIX fallback
        os.kill(-int(pgid), 0)
        return True
    except OSError:
        return False


def _scan_proc_for_detached_worker(root: Path) -> int:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return 0
    root_str = str(root)
    root_resolved = str(root.resolve())
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid_val = int(entry.name)
        if pid_val == os.getpid() or not _pid_is_alive(pid_val):
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        parts = [tok.decode("utf-8", errors="replace") for tok in raw.split(b"\0") if tok]
        if "--detached-worker" in parts and (root_str in parts or root_resolved in parts):
            return pid_val
    return 0


def _find_existing_detached_worker(root: Path, *, start_token: str = "") -> dict[str, Any] | None:
    meta_path = root / DETACHED_LIVE_META
    done_path = root / DETACHED_LIVE_DONE
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except (ValueError, OSError):
            meta = {}

    wpid = int(meta.get("worker_pid") or 0) if isinstance(meta.get("worker_pid"), int) else 0
    cpid = int(meta.get("child_pid") or 0) if isinstance(meta.get("child_pid"), int) else 0
    wpgid = int(meta.get("worker_pgid") or 0) if isinstance(meta.get("worker_pgid"), int) else 0
    meta_token = str(meta.get("start_token") or "")

    if not done_path.is_file():
        if (
            (wpid > 0 and _pid_is_alive(wpid))
            or (cpid > 0 and _pid_is_alive(cpid))
            or (wpgid > 1 and _pgid_has_live_member(wpgid))
        ):
            return {
                "worker_pid": wpid or cpid,
                "worker_pgid": wpgid or None,
                "child_pid": cpid or None,
                "script": meta.get("script"),
                "started_epoch": meta.get("started_epoch"),
                "start_token": meta_token or start_token,
            }

    if start_token and meta_token == start_token and (done_path.is_file() or (root / DETACHED_LIVE_LOG).is_file()):
        return {
            "worker_pid": wpid,
            "worker_pgid": wpgid or None,
            "child_pid": cpid or None,
            "script": meta.get("script"),
            "started_epoch": meta.get("started_epoch"),
            "start_token": start_token,
        }

    proc_pid = _scan_proc_for_detached_worker(root)
    if proc_pid > 0:
        proc_pgid: int | None = None
        if os.name != "nt":
            try:
                proc_pgid = os.getpgid(proc_pid)
            except OSError:
                proc_pgid = None
        return {
            "worker_pid": proc_pid,
            "worker_pgid": proc_pgid,
            "child_pid": None,
            "script": meta.get("script"),
            "started_epoch": meta.get("started_epoch") or round(time.time(), 6),
            "start_token": meta_token or start_token,
        }
    return None


class _ScrubbingLogStream:
    """File-like wrapper that scrubs tokens from every write and flushes immediately."""

    def __init__(self, fh: Any) -> None:
        self._fh = fh

    def write(self, text: str) -> int:
        if not text:
            return 0
        cleaned = scrub_colab_tokens(text)
        n = self._fh.write(cleaned)
        self._fh.flush()
        return int(n)

    def flush(self) -> None:
        self._fh.flush()


def run_detached_worker(
    content_root: str | Path,
    *,
    env: dict[str, str] | None = None,
) -> int:
    """Execute `SDLAB_REMOTE_SCRIPT` on the VM, writing scrubbed live output, stderr, and exit rc to files."""
    root = Path(content_root)
    root.mkdir(parents=True, exist_ok=True)
    effective_env = dict(os.environ if env is None else env)
    target_script = effective_env.get("SDLAB_REMOTE_SCRIPT", "").strip()
    start_token = effective_env.get("SDLAB_START_TOKEN", "").strip()
    log_path = root / DETACHED_LIVE_LOG
    err_path = root / DETACHED_LIVE_ERR
    meta_path = root / DETACHED_LIVE_META
    rc_path = root / DETACHED_LIVE_RC
    done_path = root / DETACHED_LIVE_DONE

    orig_stderr = sys.stderr
    scrubbed_stderr = _ScrubbingLogStream(orig_stderr)
    sys.stderr = scrubbed_stderr  # type: ignore[assignment]
    try:
        if not target_script:
            with log_path.open("a", encoding="utf-8", newline="\n") as log_fh:
                log_fh.write("REFUSED: SDLAB_REMOTE_SCRIPT is required\nSDLAB_REMOTE_RC=2\n")
                log_fh.flush()
            _atomic_write_text(rc_path, "2\n")
            _atomic_write_text(
                done_path,
                json.dumps({"rc": 2, "finished_epoch": round(time.time(), 6), "start_token": start_token}) + "\n",
            )
            return 2

        cmd = [_resolve_bash_bin(effective_env), target_script]
        started_epoch = round(time.time(), 6)
        worker_pgid = os.getpgrp() if os.name != "nt" else None
        _atomic_write_text(
            meta_path,
            json.dumps(
                {
                    "worker_pid": os.getpid(),
                    "worker_pgid": worker_pgid,
                    "child_pid": None,
                    "script": target_script,
                    "started_epoch": started_epoch,
                    "start_token": start_token,
                }
            )
            + "\n",
        )
        with log_path.open("a", encoding="utf-8", newline="\n") as log_fh:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                env=effective_env,
            )
            _atomic_write_text(
                meta_path,
                json.dumps(
                    {
                        "worker_pid": os.getpid(),
                        "worker_pgid": worker_pgid,
                        "child_pid": proc.pid,
                        "script": target_script,
                        "started_epoch": started_epoch,
                        "start_token": start_token,
                    }
                )
                + "\n",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log_fh.write(scrub_colab_tokens(line))
                log_fh.flush()
            rc = int(proc.wait())
            dl_chunk_raw = effective_env.get("SDLAB_DL_CHUNK_BYTES", "").strip()
            if dl_chunk_raw.isdigit() and int(dl_chunk_raw) > 0:
                stream = _ScrubbingLogStream(log_fh)
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):  # type: ignore[arg-type]
                    prepare_content_downloads(root, int(dl_chunk_raw))
            log_fh.write(f"SDLAB_REMOTE_RC={rc}\n")
            log_fh.flush()

        _atomic_write_text(rc_path, f"{rc}\n")
        _atomic_write_text(
            done_path,
            json.dumps({"rc": rc, "finished_epoch": round(time.time(), 6), "start_token": start_token}) + "\n",
        )
        return rc
    except Exception:
        scrubbed_stderr.write(traceback.format_exc())
        scrubbed_stderr.flush()
        raise
    finally:
        scrubbed_stderr.flush()
        sys.stderr = orig_stderr
        scrub_file_in_place(err_path)


def start_detached_worker(
    content_root: str | Path,
    *,
    script_path: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Idempotently start `run_detached_worker` in the background, returning an existing live worker on retry."""
    root = Path(content_root)
    root.mkdir(parents=True, exist_ok=True)
    effective_env = dict(os.environ if env is None else env)
    target_script = (script_path or effective_env.get("SDLAB_REMOTE_SCRIPT", "")).strip()
    if not target_script:
        raise ValueError("REFUSED: SDLAB_REMOTE_SCRIPT is required")

    start_token = effective_env.get("SDLAB_START_TOKEN", "").strip()
    meta_path = root / DETACHED_LIVE_META
    existing = _find_existing_detached_worker(root, start_token=start_token)
    if existing is not None:
        if not meta_path.is_file():
            _atomic_write_text(
                meta_path,
                json.dumps(
                    {
                        "worker_pid": existing["worker_pid"],
                        "worker_pgid": existing.get("worker_pgid"),
                        "child_pid": existing.get("child_pid"),
                        "script": existing.get("script") or target_script,
                        "started_epoch": existing.get("started_epoch") or round(time.time(), 6),
                        "start_token": existing.get("start_token") or start_token,
                    }
                )
                + "\n",
            )
        return {
            "ok": True,
            "worker_pid": existing["worker_pid"],
            "already_running": True,
            "content_root": str(root),
            "script": existing.get("script") or target_script,
        }

    clear_detached_state(root)
    (root / DETACHED_LIVE_LOG).write_bytes(b"")
    err_path = root / DETACHED_LIVE_ERR
    worker_env = dict(effective_env)
    worker_env["SDLAB_REMOTE_SCRIPT"] = target_script
    worker_env["SDLAB_CONTENT"] = str(root)

    started_epoch = round(time.time(), 6)
    with err_path.open("wb") as err_fh:
        worker = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).resolve()), "--detached-worker", "--content-root", str(root)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err_fh,
            env=worker_env,
            start_new_session=(os.name != "nt"),
        )
    worker_pgid = worker.pid if os.name != "nt" else None
    if not meta_path.is_file():
        _atomic_write_text(
            meta_path,
            json.dumps(
                {
                    "worker_pid": worker.pid,
                    "worker_pgid": worker_pgid,
                    "child_pid": None,
                    "script": target_script,
                    "started_epoch": started_epoch,
                    "start_token": start_token,
                }
            )
            + "\n",
        )
    return {
        "ok": True,
        "worker_pid": worker.pid,
        "already_running": False,
        "content_root": str(root),
        "script": target_script,
    }


def poll_detached_output(
    content_root: str | Path,
    offset: int = 0,
    max_bytes: int = DETACHED_POLL_MAX_BYTES_DEFAULT,
) -> dict[str, Any]:
    """Read new complete lines from `.sdlab_live.log` starting at `offset` without tearing lines."""
    root = Path(content_root)
    safe_offset = max(0, int(offset))
    cap_bytes = max(1024, int(max_bytes))
    done_path = root / DETACHED_LIVE_DONE
    rc_path = root / DETACHED_LIVE_RC
    meta_path = root / DETACHED_LIVE_META
    log_path = root / DETACHED_LIVE_LOG
    err_path = root / DETACHED_LIVE_ERR

    done_before = done_path.is_file()
    worker_dead_without_done = False
    if not done_before and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            wpid = int(meta.get("worker_pid") or 0)
        except (ValueError, OSError):
            wpid = 0
        if wpid > 0 and not _pid_is_alive(wpid):
            if done_path.is_file():
                done_before = True
            else:
                worker_dead_without_done = True

    rc_val: int | None = None
    if done_before and rc_path.is_file():
        raw_rc = rc_path.read_text(encoding="utf-8", errors="replace").strip()
        if raw_rc.lstrip("-").isdigit():
            rc_val = int(raw_rc)

    is_terminal = done_before or worker_dead_without_done
    total_bytes = 0
    raw_slice = b""
    if log_path.is_file():
        total_bytes = log_path.stat().st_size
        if safe_offset < total_bytes:
            with log_path.open("rb") as fh:
                fh.seek(safe_offset)
                raw_slice = fh.read(cap_bytes)

    hit_cap = (safe_offset + len(raw_slice)) < total_bytes
    if raw_slice and (not is_terminal or hit_cap):
        last_nl = raw_slice.rfind(b"\n")
        if last_nl >= 0:
            raw_slice = raw_slice[: last_nl + 1]
        elif not is_terminal:
            raw_slice = b""

    next_offset = safe_offset + len(raw_slice)
    chunk_text = scrub_colab_tokens(raw_slice.decode("utf-8", errors="replace")) if raw_slice else ""
    eof = bool(is_terminal and next_offset >= total_bytes)
    res: dict[str, Any] = {
        "ok": True,
        "offset": safe_offset,
        "next_offset": next_offset,
        "done": is_terminal,
        "worker_dead": worker_dead_without_done,
        "eof": eof,
        "rc": rc_val,
        "chunk": chunk_text,
    }
    if eof:
        worker_stderr = ""
        if err_path.is_file():
            scrub_file_in_place(err_path)
            raw_err = err_path.read_bytes()
            if len(raw_err) > DETACHED_STDERR_TAIL_BYTES:
                raw_err = raw_err[-DETACHED_STDERR_TAIL_BYTES:]
            worker_stderr = scrub_colab_tokens(raw_err.decode("utf-8", errors="replace"))
        res["worker_stderr"] = worker_stderr
    return res


def stop_detached_worker(content_root: str | Path, *, sig: int | None = None) -> dict[str, Any]:
    """Best-effort terminate recorded worker + child PIDs (worker first so child EOF cannot trigger download prep)."""
    root = Path(content_root)
    meta_path = root / DETACHED_LIVE_META
    eff_sig = int(signal.SIGTERM if sig is None else sig)
    signaled: list[int] = []
    candidate_pids: list[int] = []
    wpgid = 0
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            meta = {}
        if isinstance(meta.get("worker_pgid"), int):
            wpgid = int(meta["worker_pgid"])
        for key in ("worker_pid", "child_pid"):
            raw_pid = meta.get(key)
            if isinstance(raw_pid, int) and raw_pid > 0 and raw_pid != os.getpid() and raw_pid not in candidate_pids:
                candidate_pids.append(raw_pid)
    proc_pid = _scan_proc_for_detached_worker(root)
    if proc_pid > 0 and proc_pid not in candidate_pids:
        candidate_pids.insert(0, proc_pid)
    for raw_pid in candidate_pids:
        try:
            os.kill(raw_pid, eff_sig)
            signaled.append(raw_pid)
        except OSError:
            pass
        if os.name != "nt":
            try:
                pgid = os.getpgid(raw_pid)
                if pgid > 1 and pgid != os.getpgrp():
                    os.killpg(pgid, eff_sig)
            except OSError:
                pass
    if os.name != "nt" and wpgid > 1 and wpgid != os.getpgrp():
        try:
            os.killpg(wpgid, eff_sig)
        except OSError:
            pass
    return {"ok": True, "signaled_pids": signaled}


def apply_detached_poll_response(raw_poll_stdout: str, vitals_path: Path) -> dict[str, Any]:
    """Parse `SDLAB_POLL_ENVELOPE {...}` from `colab exec` stdout and append new chunk to `vitals.log`."""
    envelope: dict[str, Any] | None = None
    for raw_line in reversed(raw_poll_stdout.splitlines()):
        line = raw_line.strip()
        if line.startswith(DETACHED_POLL_PREFIX):
            payload = line[len(DETACHED_POLL_PREFIX) :].strip()
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                envelope = parsed
                break
    if envelope is None or envelope.get("ok") is not True:
        raise ValueError("missing or non-ok SDLAB_POLL_ENVELOPE in poll output")
    offset = envelope.get("offset")
    next_offset = envelope.get("next_offset")
    chunk = envelope.get("chunk")
    if not isinstance(offset, int) or not isinstance(next_offset, int) or next_offset < offset or not isinstance(chunk, str):
        raise ValueError(f"malformed SDLAB_POLL_ENVELOPE fields: offset={offset!r}, next_offset={next_offset!r}")

    cleaned = scrub_colab_tokens(chunk)
    if cleaned:
        vitals_path.parent.mkdir(parents=True, exist_ok=True)
        with vitals_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(cleaned)
            fh.flush()
    if bool(envelope.get("eof")) and isinstance(envelope.get("worker_stderr"), str):
        vitals_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_out = vitals_path.parent / "detached_worker_stderr.log"
        stderr_out.write_text(scrub_colab_tokens(envelope["worker_stderr"]), encoding="utf-8", newline="\n")
    return {
        "offset": offset,
        "next_offset": next_offset,
        "done": bool(envelope.get("done")),
        "eof": bool(envelope.get("eof")),
        "rc": envelope.get("rc"),
        "bytes_appended": len(cleaned.encode("utf-8")),
    }


def wall_cap_refusal(wall: dict[str, Any], cap: dict[str, Any]) -> dict[str, Any] | None:
    """The kit's named refusal for a wall/cap trip, with the numbers that tripped it. When both trip,
    the cap's code is the one named (a failed usage read or a spent cap is the costlier finding)."""
    if cap.get("tripped"):
        phase = cap.get("phase")
        prefix = f"cap guard (phase={phase}):" if phase else "cap guard:"
        if cap.get("code") == "COLAB_USAGE_PARSE_FAILED":
            why = f"{prefix} {cap.get('usage_parse_error')} (ceiling {cap.get('ceiling_ccu')} ccu)"
        elif cap.get("cleanup_bound_s", 0):
            why = (
                f"{prefix} spend {cap.get('spend_ccu')} ccu >= ceiling {cap.get('ceiling_ccu')} ccu "
                f"(effective_trip {cap.get('effective_trip_units')} = cap {cap.get('cap_ccu')} "
                f"- margin {cap.get('margin_ccu')} - cleanup_reserve {cap.get('cleanup_reserve_units')})"
            )
        else:
            why = f"{prefix} spend {cap.get('spend_ccu')} ccu >= ceiling {cap.get('ceiling_ccu')} ccu"
        ref: dict[str, Any] = {"code": cap.get("code"), "why": why}
        if phase is not None:
            ref["phase"] = phase
        if cap.get("checkpoint") is not None:
            ref["checkpoint"] = cap.get("checkpoint")
        return ref
    if wall.get("tripped"):
        return {
            "code": wall.get("code"),
            "why": f"wall guard: {wall.get('remaining_s')} s remaining of threshold {wall.get('threshold_s')} s (wall - grace)",
        }
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sdlab C2 launcher guards CLI")
    parser.add_argument("--mode", default="stub")
    parser.add_argument("--phase", default=None, help="Execution phase (e.g. pre_exec or live)")
    parser.add_argument("--checkpoint", default=None, help="Pre-exec or live check point name")
    parser.add_argument("--elapsed-s", type=float, default=0.0)
    parser.add_argument("--wall-s", type=float, default=3000.0)
    parser.add_argument("--grace-s", type=float, default=60.0)
    parser.add_argument("--cap", type=float, default=0.08)
    parser.add_argument("--margin", type=float, default=0.05)
    parser.add_argument("--cleanup-bound-s", type=float, default=0.0)
    parser.add_argument(
        "--usage-retry-bound-s",
        type=float,
        default=USAGE_RETRY_BOUND_S,
        help="Worst-case duration T_retry of one bounded colab usage retry sequence, in seconds",
    )
    parser.add_argument(
        "--usage-blind-interval-s",
        type=float,
        default=None,
        help="Blind interval of one usage sequence (T_retry + 2 * poll_s + slack_s); the margin gate prices "
        "the cap-check interval, this plus --detached-poll-lag-s; default T_retry + 2 * 2 + 2",
    )
    parser.add_argument(
        "--detached-poll-lag-s",
        type=float,
        default=None,
        help="Detached-loop lag that, added to the blind interval, gives the cap-check interval the margin "
        "gate prices (2 * (poll_retry_sleep_s + poll_exec_timeout_s) + kill_grace_s); default 2 * (5 + 30) + 10",
    )
    parser.add_argument("--rate", type=float, default=0.0)
    parser.add_argument("--max-rate", type=float, default=None)
    parser.add_argument("--min-runtime-s", type=float, default=None)
    parser.add_argument("--check-cap-budget", action="store_true", help="Check cap budget against cleanup reserve and --min-runtime-s")
    parser.add_argument("--check-wall-only", action="store_true", help="Evaluate only the local wall guard while usage poll retries are in flight")
    parser.add_argument("--check-offline-cap", action="store_true",
                        help="Trip-only cap projection on cached balances (failed remote poll, no usage read in flight)")
    parser.add_argument("--balance-age-s", type=float, default=None,
                        help="Age in seconds of the cached balance (--check-offline-cap)")
    parser.add_argument("--card-class", default=None,
                        help="gpu or cpu (--check-offline-cap); unset counts as gpu, so a bad rate refuses")
    parser.add_argument("--dry", action="store_true", help="Print cap trip arithmetic and exit")
    parser.add_argument("--start-balance", type=float, default=None)
    parser.add_argument("--current-balance", type=float, default=None)
    parser.add_argument("--usage-parse-error", default=None, help="Usage parse failure message causing cap guard to trip")
    parser.add_argument("--verify-sha", action="append", default=[], help="Verify PATH=SHA256 before opening window")
    parser.add_argument("--scrub-file", action="append", default=[], help="Scrub Colab/OAuth tokens from file in place")
    parser.add_argument("--vitals-file", type=Path, default=None, help="Evaluate vitals.log and stall guard")
    parser.add_argument("--idle-seconds", type=float, default=0.0)
    parser.add_argument("--setup-idle-seconds", type=float, default=None)
    parser.add_argument("--stall-s", type=float, default=300.0)
    parser.add_argument("--setup-stall-s", type=float, default=600.0)
    parser.add_argument("--check-ram", action="store_true", help="Run host/cgroup RAM projection check")
    parser.add_argument("--current-anon-mb", type=float, default=512.0)
    parser.add_argument("--projected-delta-mb", type=float, default=1024.0)
    parser.add_argument("--mem-total-mb", type=float, default=12288.0)
    parser.add_argument("--cgroup-max-mb", type=float, default=None)
    parser.add_argument("--mem-available-mb", type=float, default=None)
    parser.add_argument("--mem-available-floor-mb", type=float, default=MEM_AVAILABLE_FLOOR_MB)
    parser.add_argument("--ram-source", default=None, help="Where --current-anon-mb was read (recorded in guards.log)")
    parser.add_argument("--ram-vitals-file", type=Path, default=None,
                        help="With --check-ram: read private memory from this vitals.log (host_ram_status)")
    parser.add_argument("--run-output-bytes", type=Path, default=None,
                        help="Print the bytes of this vitals.log that are not vitals lines (stall guard progress)")
    parser.add_argument("--detached-worker", action="store_true",
                        help="Internal VM background worker mode for detached remote_runner")
    parser.add_argument("--content-root", type=Path, default=Path("/content"),
                        help="VM content directory for --detached-worker")
    parser.add_argument("--apply-poll-file", type=Path, default=None,
                        help="Parse SDLAB_POLL_ENVELOPE from this file and append chunk to --apply-poll-vitals")
    parser.add_argument("--apply-poll-vitals", type=Path, default=None,
                        help="Destination vitals.log for --apply-poll-file")
    args = parser.parse_args(argv)

    if args.detached_worker:
        run_detached_worker(args.content_root)
        return 0

    if args.apply_poll_file is not None:
        if args.apply_poll_vitals is None or not args.apply_poll_file.is_file():
            print("REFUSED: --apply-poll-file requires an existing file and --apply-poll-vitals", file=sys.stderr)
            return 2
        try:
            res_poll = apply_detached_poll_response(
                args.apply_poll_file.read_text(encoding="utf-8", errors="replace"),
                args.apply_poll_vitals,
            )
        except (ValueError, OSError) as exc:
            print(f"POLL_PARSE_ERROR: {exc}", file=sys.stderr)
            return 1
        rc_str = "none" if res_poll["rc"] is None else str(res_poll["rc"])
        done_flag = 1 if res_poll["done"] else 0
        eof_flag = 1 if res_poll["eof"] else 0
        run_bytes = (
            run_output_bytes(args.apply_poll_vitals.read_text(encoding="utf-8", errors="replace"))
            if args.apply_poll_vitals.exists()
            else 0
        )
        print(f"{res_poll['next_offset']}\t{done_flag}\t{eof_flag}\t{rc_str}\t{run_bytes}")
        return 0

    if args.dry or args.check_cap_budget:
        eff_rate = (
            float(args.rate)
            if float(args.rate) > 0.0
            else (float(args.max_rate) if args.max_rate is not None else 0.26)
        )
        if args.max_rate is not None:
            priced_rate = max(eff_rate, float(args.max_rate))
            max_rate_val = float(args.max_rate)
        else:
            priced_rate = eff_rate
            max_rate_val = eff_rate
        rec = evaluate_cap_budget(
            cap=args.cap,
            margin=args.margin,
            cleanup_bound_s=args.cleanup_bound_s,
            priced_rate=priced_rate,
            max_rate=max_rate_val,
            min_runtime_s=args.min_runtime_s,
            usage_retry_bound_s=args.usage_retry_bound_s,
            usage_blind_interval=args.usage_blind_interval_s,
            detached_poll_lag=args.detached_poll_lag_s,
        )
        if args.dry:
            print(format_dry_cap_budget(rec))
        else:
            print(json.dumps(rec))
        if rec["tripped"]:
            print(f"REFUSED: {rec['code']}: {rec['why']}", file=sys.stderr)
            return 2
        return 0

    if args.run_output_bytes is not None:
        f = args.run_output_bytes
        print(run_output_bytes(f.read_text(encoding="utf-8", errors="replace")) if f.exists() else 0)
        return 0

    if args.verify_sha:
        pairs: dict[str, str] = {}
        for item in args.verify_sha:
            if "=" not in item:
                print(f"REFUSED: invalid --verify-sha argument {item!r}", file=sys.stderr)
                return 2
            k, v = item.split("=", 1)
            pairs[k] = v
        try:
            verified = verify_input_shas(pairs)
            print(json.dumps({"verified_shas": verified}))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.scrub_file:
        for fpath in args.scrub_file:
            scrub_file_in_place(Path(fpath))
        return 0

    if args.check_ram and args.ram_vitals_file is not None:
        f = args.ram_vitals_file
        status = host_ram_status(f.read_text(encoding="utf-8", errors="replace") if f.exists() else None)
        if status["state"] in ("no_vm", "waiting"):
            print(json.dumps({"check": "host_ram", "state": status["state"], "ok": True, "tripped": False,
                              "skipped": True, "blocks_seen": status["blocks_seen"]}))
            return 0
        if status["state"] == "unreadable":
            rec = {"check": "host_ram", "state": "unreadable", "ok": False, "tripped": True,
                   "code": "HOST_RAM_UNREADABLE", "blocks_seen": status["blocks_seen"], "why": status["why"]}
            rec["refusal"] = {"code": rec["code"], "why": rec["why"]}
            print(json.dumps(rec))
            print(f"HOST_RAM_UNREADABLE: {status['why']}", file=sys.stderr)
            return 1
        r = status["reading"]
        res = evaluate_host_ram_projection(
            current_anon_mb=r["private_mb"],
            projected_delta_mb=args.projected_delta_mb,
            mem_total_mb=r["mem_total_mb"],
            cgroup_max_mb=r["cgroup_max_mb"],
            mem_available_mb=r["mem_available_mb"],
            mem_available_floor_mb=args.mem_available_floor_mb,
            source=r["source"],
        )
        res.update({
            "state": "ok",
            "sample": r["timestamp"],
            "blocks_back": r["blocks_back"],
            "cgroup_private_mb": r["cgroup_private_mb"],
            "cgroup_anon_mb": r["cgroup_anon_mb"],
            "cgroup_shmem_mb": r["cgroup_shmem_mb"],
            "meminfo_private_mb": r["meminfo_private_mb"],
            "meminfo_anon_mb": r["meminfo_anon_mb"],
            "meminfo_shmem_mb": r["meminfo_shmem_mb"],
            "cgroup_current_mb_not_used": r["cgroup_current_mb_not_used"],
        })
        if res["tripped"]:
            res["refusal"] = {"code": res["code"], "why": res["why"]}
            print(json.dumps(res))
            print(f"{res['code']}: {res['why']}", file=sys.stderr)
            return 1
        print(json.dumps(res))
        return 0

    if args.check_ram:
        # The record goes to stdout (guards.log) whether or not it trips, so the tripping numbers
        # reach the rig; a trip also names itself on stderr and carries `refusal` for the kit.
        res = evaluate_host_ram_projection(
            current_anon_mb=args.current_anon_mb,
            projected_delta_mb=args.projected_delta_mb,
            mem_total_mb=args.mem_total_mb,
            cgroup_max_mb=args.cgroup_max_mb,
            mem_available_mb=args.mem_available_mb,
            mem_available_floor_mb=args.mem_available_floor_mb,
            source=args.ram_source,
        )
        if res["tripped"]:
            res["refusal"] = {"code": res["code"], "why": res["why"]}
            print(json.dumps(res))
            print(f"{res['code']}: {res['why']}", file=sys.stderr)
            return 1
        print(json.dumps(res))
        return 0

    if args.vitals_file is not None:
        txt = args.vitals_file.read_text(encoding="utf-8", errors="replace") if args.vitals_file.exists() else ""
        vit = evaluate_vitals_and_stall_guard(
            vitals_text=txt,
            idle_seconds=args.idle_seconds,
            setup_idle_seconds=args.setup_idle_seconds,
            stall_s=args.stall_s,
            setup_stall_s=args.setup_stall_s,
        )
        if vit["tripped"]:
            vit["refusal"] = {"code": vit["code"], "why": vit["reason"]}
        print(json.dumps(vit))
        return 1 if vit["tripped"] else 0

    if args.check_offline_cap:
        offline_cap = evaluate_offline_cap_projection(
            cap=args.cap,
            margin=args.margin,
            cleanup_bound_s=args.cleanup_bound_s,
            rate_ccu_per_hour=args.rate,
            elapsed_s=args.elapsed_s,
            start_balance=args.start_balance,
            cached_balance=args.current_balance,
            balance_age_s=args.balance_age_s,
            card_class=args.card_class,
        )
        out_off: dict[str, Any] = {"check": "offline_cap", "cap": offline_cap}
        if args.phase is not None:
            out_off["phase"] = args.phase
        if args.checkpoint is not None:
            out_off["checkpoint"] = args.checkpoint
        if offline_cap["tripped"]:
            why_off = (
                f"offline cap projection: spend {offline_cap['spend_ccu']} ccu "
                f"(priced_rate {offline_cap['priced_rate']}/h * elapsed {offline_cap['elapsed_s']} s) "
                f">= ceiling {offline_cap['ceiling_ccu']} ccu"
            )
            out_off["refusal"] = {"code": offline_cap["code"], "why": why_off}
        print(json.dumps(out_off))
        return 1 if offline_cap["tripped"] else 0

    if args.check_wall_only:
        wall = evaluate_wall_guard(mode=args.mode, elapsed_s=args.elapsed_s, wall_s=args.wall_s, grace_s=args.grace_s)
        out_wall: dict[str, Any] = {"check": "wall_only", "wall": wall}
        if args.phase is not None:
            out_wall["phase"] = args.phase
        if args.checkpoint is not None:
            out_wall["checkpoint"] = args.checkpoint
        if wall["tripped"]:
            out_wall["refusal"] = {
                "code": wall["code"],
                "why": f"wall guard: {wall['remaining_s']} s remaining of threshold {wall['threshold_s']} s (wall - grace)",
            }
        print(json.dumps(out_wall))
        return 1 if wall["tripped"] else 0

    wall = evaluate_wall_guard(mode=args.mode, elapsed_s=args.elapsed_s, wall_s=args.wall_s, grace_s=args.grace_s)
    cap = evaluate_cap_guard(
        mode=args.mode,
        cap=args.cap,
        margin=args.margin,
        cleanup_bound_s=args.cleanup_bound_s,
        start_balance=args.start_balance,
        current_balance=args.current_balance,
        rate_ccu_per_hour=args.rate,
        elapsed_s=args.elapsed_s,
        usage_parse_error=args.usage_parse_error,
        phase=args.phase,
        checkpoint=args.checkpoint,
    )
    out: dict[str, Any] = {"wall": wall, "cap": cap}
    if args.phase is not None:
        out["phase"] = args.phase
    if args.checkpoint is not None:
        out["checkpoint"] = args.checkpoint
    refusal = wall_cap_refusal(wall, cap)
    if refusal is not None:
        out["refusal"] = refusal
    print(json.dumps(out))
    return 1 if (wall["tripped"] or cap["tripped"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
