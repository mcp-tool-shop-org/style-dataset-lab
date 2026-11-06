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
import hashlib
import json
import re
import shutil
import sys
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
# read before the neighbour's rate). Then the neighbour is re-baselined: baseline = account - our
# last stable rate. Pending or settling reads are never judged against the max and never raise our
# priced rate, which stays max(--max-rate, highest stable seen). Only a read at an unchanged count
# may raise our rate or trip the max. Known limit: a neighbour opening on the same read our own rate
# rises folds that rise into the baseline; pricing at max(--max-rate, seen) bounds the cost.
#
# A missing count, or 0 while our window is open, is a bad read: recorded, the rate not judged, and
# ASSIGNMENTS_UNREADABLE after ASSIGNMENTS_BAD_LIMIT consecutive bad reads.
GPU_RATE_FLOOR = 1.00
RATE_STABLE_TOLERANCE = 0.01
RATE_STABLE_GAP_S = 5.0
ASSIGNMENTS_BAD_LIMIT = 3


def parse_active_assignments(raw_usage: str) -> int | None:
    m = re.search(r"^\s*Active\s+assignments:\s*(\d+)\s*$", raw_usage or "", re.I | re.M)
    return int(m.group(1)) if m else None


def update_window_rate(state: dict[str, Any], *, account_rate: float | None, pre_open_rate: float | None,
                       at: str, epoch: float, assignments: int | None,
                       min_gap_s: float = RATE_STABLE_GAP_S, floor: float = GPU_RATE_FLOOR,
                       tolerance: float = RATE_STABLE_TOLERANCE) -> dict[str, Any]:
    """Fold one post-open `colab usage` reading into the window-rate state (kept in the out dir).
    Every reading is recorded. A bad count (missing, or 0) is recorded and judged nothing; three in
    a row set `assignments_unreadable`. A read less than `min_gap_s` after the last counted one is
    recorded as `counted: false`. A changed count starts a pending re-baseline that settles on two
    agreeing reads at the new count. Otherwise the window rate is `stable` when it is at or above
    the floor and agrees with the last counted window rate within the tolerance; `best_stable` is
    the highest stable one."""
    readings = state.setdefault("readings", [])
    state["floor"] = floor
    if "neighbour_baseline" not in state:
        state["neighbour_baseline"] = float(pre_open_rate) if pre_open_rate is not None else 0.0
    base = float(state["neighbour_baseline"])
    rec: dict[str, Any] = {"at": at, "epoch": round(float(epoch), 3), "account_rate": account_rate,
                           "pre_open_rate": pre_open_rate, "assignments": assignments,
                           "neighbour_baseline": base, "window_rate": None, "stable": False}
    if assignments is None or int(assignments) <= 0:
        state["assignments_bad_streak"] = int(state.get("assignments_bad_streak", 0)) + 1
        if state["assignments_bad_streak"] >= ASSIGNMENTS_BAD_LIMIT:
            state["assignments_unreadable"] = True
        rec.update({"counted": False, "assignments_bad": True})
        readings.append(rec)
        return state
    state["assignments_bad_streak"] = 0
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
        # Settled: two agreeing reads at the new count.
        ours = state.get("last_stable")
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
    rec.update({"window_rate": window, "stable": stable})
    readings.append(rec)
    state["last_window"] = window
    if stable:
        state["last_stable"] = window
        if state.get("best_stable") is None or window > state["best_stable"]:
            state["best_stable"] = window
    return state


def gpu_projection_rate(state: dict[str, Any], max_rate: float) -> float:
    """The rate a GPU window's cap is projected with: max(--max-rate, highest stable window rate)."""
    best = state.get("best_stable")
    return max(float(max_rate), float(best)) if best is not None else float(max_rate)


def window_rate_decision(state: dict[str, Any], max_rate: float) -> str:
    """`assignments_unreadable`, `unread` (no stable window rate at or above the floor yet),
    `above_max` or `ok`."""
    if state.get("assignments_unreadable"):
        return "assignments_unreadable"
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


def evaluate_cap_guard(
    *,
    mode: str = "live",
    cap: float = 0.05,
    margin: float = 0.01,
    start_balance: float | None = None,
    current_balance: float | None = None,
    rate_ccu_per_hour: float = 0.0,
    elapsed_s: float = 0.0,
    usage_parse_error: str | None = None,
) -> dict[str, Any]:
    ceiling = round(max(0.0, float(cap) - float(margin)), 6)
    if usage_parse_error:
        return {
            "mode": mode,
            "tripped": True,
            "code": "COLAB_USAGE_PARSE_FAILED",
            "spend_ccu": None,
            "ceiling_ccu": ceiling,
            "usage_parse_error": usage_parse_error,
        }
    if (start_balance is not None and float(start_balance) < 0.0) or (
        current_balance is not None and float(current_balance) < 0.0
    ):
        return {
            "mode": mode,
            "tripped": True,
            "code": "COLAB_USAGE_PARSE_FAILED",
            "spend_ccu": None,
            "ceiling_ccu": ceiling,
            "usage_parse_error": "COLAB_USAGE_PARSE_FAILED: negative balance is impossible",
        }
    if mode not in ("fake", "dry_run", "offline") and (start_balance is None or current_balance is None):
        return {
            "mode": mode,
            "tripped": True,
            "code": "COLAB_USAGE_PARSE_FAILED",
            "spend_ccu": None,
            "ceiling_ccu": ceiling,
            "usage_parse_error": "COLAB_USAGE_PARSE_FAILED: missing start_balance or current_balance in non-fake mode",
        }
    drop = (
        round(max(0.0, float(start_balance) - float(current_balance)), 6)
        if start_balance is not None and current_balance is not None
        else 0.0
    )
    rate_est = round(max(0.0, (float(rate_ccu_per_hour) * float(elapsed_s)) / 3600.0), 6)
    spend = round(max(drop, rate_est), 6)
    tripped = spend >= ceiling
    return {
        "mode": mode,
        "tripped": tripped,
        "code": "CAP_GUARD_TRIPPED" if tripped else None,
        "spend_ccu": spend,
        "ceiling_ccu": ceiling,
    }


def parse_vitals_log(vitals_text: str) -> list[dict[str, Any]]:
    blocks = [b.strip() for b in re.split(r"^===\s*VITALS\s+", vitals_text, flags=re.M) if b.strip()]
    samples: list[dict[str, Any]] = []
    for block in blocks:
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


def evaluate_vitals_and_stall_guard(
    *,
    vitals_text: str,
    idle_seconds: float = 0.0,
    setup_idle_seconds: float | None = None,
    stall_s: float = 300.0,
    setup_stall_s: float = 600.0,
) -> dict[str, Any]:
    samples = parse_vitals_log(vitals_text)
    current_phase = "setup"
    if samples:
        last = samples[-1]
        if isinstance(last["phase"], str) and last["phase"].strip():
            current_phase = last["phase"].strip()
        if (
            isinstance(last["phase"], str)
            and (last["phase"].startswith("run") or last["phase"].startswith("setup"))
            and last["worker_proc_count"] == 0
            and last.get("oom_kill")
        ):
            return {
                "tripped": True,
                "code": "DEAD_HARNESS_TRIPPED",
                "cgroup_oom": True,
                "reason": f"cgroup OOM kill detected in phase={last['phase']} with 0 active worker processes",
                "samples_count": len(samples),
            }
    if len(samples) >= 2:
        last_two = samples[-2:]
        if all(
            isinstance(s["phase"], str) and s["phase"].startswith("run") and s["worker_proc_count"] == 0
            for s in last_two
        ):
            return {
                "tripped": True,
                "code": "DEAD_HARNESS_TRIPPED",
                "cgroup_oom": any(bool(s.get("oom_kill")) for s in last_two),
                "reason": "2 consecutive vitals samples in phase=run with 0 active worker processes",
                "samples_count": len(samples),
            }
    if current_phase.startswith("setup"):
        eff_setup_idle = float(setup_idle_seconds if setup_idle_seconds is not None else idle_seconds)
        if eff_setup_idle >= float(setup_stall_s):
            return {
                "tripped": True,
                "code": "SETUP_STALL_TRIPPED",
                "cgroup_oom": False,
                "reason": f"No new setup.log output (SETUP_BYTES unchanged) in phase=setup for {eff_setup_idle}s (setup_stall_s={setup_stall_s}s)",
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


def check_host_ram_projection(
    *,
    current_anon_mb: float,
    projected_delta_mb: float,
    mem_total_mb: float,
    cgroup_max_mb: float | None = None,
    safety_factor: float = 1.05,
) -> dict[str, Any]:
    limits = [float(mem_total_mb)]
    if cgroup_max_mb is not None:
        limits.append(float(cgroup_max_mb))
    limit_mb = min(limits)
    projected_mb = round((float(current_anon_mb) + float(projected_delta_mb)) * float(safety_factor), 1)
    if projected_mb > limit_mb:
        raise ValueError(
            f"HOST_RAM_PROJECTION_EXCEEDED: projected {projected_mb:.1f} MB > ceiling {limit_mb:.1f} MB"
        )
    return {"ok": True, "projected_mb": projected_mb, "limit_mb": limit_mb}


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sdlab C2 launcher guards CLI")
    parser.add_argument("--mode", default="stub")
    parser.add_argument("--elapsed-s", type=float, default=0.0)
    parser.add_argument("--wall-s", type=float, default=3000.0)
    parser.add_argument("--grace-s", type=float, default=60.0)
    parser.add_argument("--cap", type=float, default=0.05)
    parser.add_argument("--margin", type=float, default=0.01)
    parser.add_argument("--rate", type=float, default=0.0)
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
    args = parser.parse_args(argv)

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

    if args.check_ram:
        try:
            res = check_host_ram_projection(
                current_anon_mb=args.current_anon_mb,
                projected_delta_mb=args.projected_delta_mb,
                mem_total_mb=args.mem_total_mb,
                cgroup_max_mb=args.cgroup_max_mb,
            )
            print(json.dumps(res))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.vitals_file is not None:
        txt = args.vitals_file.read_text(encoding="utf-8", errors="replace") if args.vitals_file.exists() else ""
        vit = evaluate_vitals_and_stall_guard(
            vitals_text=txt,
            idle_seconds=args.idle_seconds,
            setup_idle_seconds=args.setup_idle_seconds,
            stall_s=args.stall_s,
            setup_stall_s=args.setup_stall_s,
        )
        print(json.dumps(vit))
        return 1 if vit["tripped"] else 0

    wall = evaluate_wall_guard(mode=args.mode, elapsed_s=args.elapsed_s, wall_s=args.wall_s, grace_s=args.grace_s)
    cap = evaluate_cap_guard(
        mode=args.mode,
        cap=args.cap,
        margin=args.margin,
        start_balance=args.start_balance,
        current_balance=args.current_balance,
        rate_ccu_per_hour=args.rate,
        elapsed_s=args.elapsed_s,
        usage_parse_error=args.usage_parse_error,
    )
    print(json.dumps({"wall": wall, "cap": cap}))
    return 1 if (wall["tripped"] or cap["tripped"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
