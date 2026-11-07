#!/usr/bin/env python3
"""Paired early-checkpoint evaluation for style LoRAs (CSD, CLIP-T, DINOv2, DreamSim, LoRA stable rank).

Hard invariants:
- Never touches an NVIDIA GPU (`CUDA_VISIBLE_DEVICES=""` enforced on import and run).
- Pairs sample images by `(prompt_index, step)` from filenames (`<ts>__<step>_<prompt_idx>.<ext>`).
- Verifies that run A and run B share identical `seed`, `walk_seed`, and `prompts`, refusing with
  a named error (`SEED_MISMATCH`, `PROMPT_MISMATCH`, `PAIRING_MISMATCH`) otherwise.
- Writes `corridors.md` from run A's numbers before any run B exists, carrying its own sha256 and
  creation timestamp, and refuses with `CORRIDORS_TAMPERED` if modified before scoring run B.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import time
from typing import Any, Callable, Sequence
import zlib

# Hard limit: disable CUDA in every process before any ML library can be imported.
os.environ["CUDA_VISIBLE_DEVICES"] = ""

SAMPLE_FILENAME_RE = re.compile(
    r"^(?:(?P<ts>\d+)__)?0*(?P<step>\d+)_(?P<prompt_idx>\d+)\.(?P<ext>jpg|jpeg|png|webp|ppm)$",
    re.IGNORECASE,
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".ppm"}
CORRIDORS_SHA_PLACEHOLDER = "__CORRIDORS_BODY_SHA256__"
CORRIDORS_JSON_BEGIN = "<!-- CORRIDORS_JSON_BEGIN"
CORRIDORS_JSON_END = "CORRIDORS_JSON_END -->"

MODEL_LICENCE_TABLE = [
    {
        "model": "tomg-group-umd/CSD-ViT-L (learn2phoenix/CSD)",
        "role": "CSD style descriptor (ViT-L/14)",
        "licence": "CC-BY-4.0 (weights) / MIT (code & OpenAI CLIP ViT-L/14 architecture)",
        "source_url": "https://huggingface.co/tomg-group-umd/CSD-ViT-L/raw/main/README.md ; https://raw.githubusercontent.com/learn2phoenix/CSD/main/LICENSE",
        "date_read": "2026-11-07",
    },
    {
        "model": "openai/clip-vit-base-patch32",
        "role": "Content-only CLIP-T (trigger words stripped)",
        "licence": "MIT",
        "source_url": "https://raw.githubusercontent.com/openai/CLIP/main/LICENSE ; https://huggingface.co/openai/clip-vit-base-patch32/raw/main/README.md",
        "date_read": "2026-11-07",
    },
    {
        "model": "facebook/dinov2-base (facebookresearch/dinov2)",
        "role": "DINOv2 nearest-neighbour memorization & content-leakage guard",
        "licence": "Apache-2.0",
        "source_url": "https://raw.githubusercontent.com/facebookresearch/dinov2/main/LICENSE ; https://huggingface.co/facebook/dinov2-base/raw/main/README.md",
        "date_read": "2026-11-07",
    },
    {
        "model": "ssundaram21/dreamsim (open_clip_vitb32, v0.2.1)",
        "role": "DreamSim perceptual distance (seed-matched B vs A and step vs step 0)",
        "licence": "MIT (DreamSim & OpenCLIP ViT-B/32) / Apache-2.0 (DINO backbone)",
        "source_url": "https://raw.githubusercontent.com/ssundaram21/dreamsim/main/LICENSE ; https://raw.githubusercontent.com/mlfoundations/open_clip/main/LICENSE",
        "date_read": "2026-11-07",
    },
]


class CheckpointEvalRefusal(RuntimeError):
    """Named refusal raised on invalid inputs, seed/prompt mismatch, or tampered corridors."""

    def __init__(self, code: str, why: str) -> None:
        self.code = code
        self.why = why
        super().__init__(f"REFUSED: {code}: {why}")


# ---------------------------------------------------------------------------
# Pure-Python math & statistical helpers (zero third-party deps required)
# ---------------------------------------------------------------------------


def _mean(vals: Sequence[float]) -> float:
    if not vals:
        return 0.0
    return float(sum(vals) / len(vals))


def _sample_sd(vals: Sequence[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    m = _mean(vals)
    var = sum((x - m) ** 2 for x in vals) / (n - 1)
    return float(math.sqrt(max(0.0, var)))


def _median(vals: Sequence[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(float(x) for x in vals)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for incomplete beta function I_x(a, b) (Numerical Recipes / Lentz)."""
    max_iter = 200
    eps = 3.0e-14
    fpmin = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    bt = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _student_t_cdf(t_val: float, df: int) -> float:
    """Exact cumulative distribution function P(T <= t_val) for Student's t with df > 0."""
    if df <= 0:
        return 0.5
    if math.isnan(t_val):
        return float("nan")
    if math.isinf(t_val):
        return 1.0 if t_val > 0 else 0.0
    x = df / (df + t_val * t_val)
    ib = 0.5 * _regularized_incomplete_beta(0.5 * df, 0.5, x)
    return 1.0 - ib if t_val >= 0.0 else ib


def _student_t_ppf(p: float, df: int) -> float:
    """Inverse CDF (quantile) of Student's t via bisection + Halley refinement."""
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    if abs(p - 0.5) < 1e-15:
        return 0.0
    sign = 1.0 if p > 0.5 else -1.0
    target = p if p > 0.5 else 1.0 - p
    lo, hi = 0.0, 1000.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _student_t_cdf(mid, df) < target:
            lo = mid
        else:
            hi = mid
    return sign * 0.5 * (lo + hi)


def _wilcoxon_signed_rank(diffs: Sequence[float]) -> dict[str, float]:
    """Exact Wilcoxon signed-rank test on paired differences (zero_method='wilcox')."""
    nz = [float(d) for d in diffs if abs(d) > 0.0]
    n_nz = len(nz)
    if n_nz == 0:
        return {
            "n_nonzero": 0,
            "w_plus": 0.0,
            "w_minus": 0.0,
            "statistic": 0.0,
            "p_two_sided": 1.0,
            "p_less": 1.0,
            "p_greater": 1.0,
        }
    abs_With_idx = sorted(enumerate(abs(d) for d in nz), key=lambda t: t[1])
    ranks = [0.0] * n_nz
    i = 0
    while i < n_nz:
        j = i
        while j + 1 < n_nz and abs(abs_With_idx[j + 1][1] - abs_With_idx[i][1]) <= 1e-15:
            j += 1
        avg_rank = 0.5 * ((i + 1) + (j + 1))
        for k in range(i, j + 1):
            ranks[abs_With_idx[k][0]] = avg_rank
        i = j + 1

    w_plus = sum(r for r, d in zip(ranks, nz) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, nz) if d < 0)
    stat = min(w_plus, w_minus)

    total_outcomes = 1 << n_nz
    le_count = 0
    ge_count = 0
    for mask in range(total_outcomes):
        s = 0.0
        for bit_idx in range(n_nz):
            if (mask >> bit_idx) & 1:
                s += ranks[bit_idx]
        if s <= w_plus + 1e-12:
            le_count += 1
        if s >= w_plus - 1e-12:
            ge_count += 1
    p_less = le_count / total_outcomes
    p_greater = ge_count / total_outcomes
    p_two = min(1.0, 2.0 * min(p_less, p_greater))
    return {
        "n_nonzero": n_nz,
        "w_plus": round(w_plus, 6),
        "w_minus": round(w_minus, 6),
        "statistic": round(stat, 6),
        "p_two_sided": round(p_two, 8),
        "p_less": round(p_less, 8),
        "p_greater": round(p_greater, 8),
    }


def compute_paired_stats(values_b: Sequence[float], values_a: Sequence[float]) -> dict[str, Any]:
    """Compute paired (B - A) statistics: mean, SD, SE, one- and two-sided paired t, and Wilcoxon."""
    if len(values_b) != len(values_a):
        raise CheckpointEvalRefusal(
            "PAIRING_MISMATCH",
            f"paired stat lengths differ: len(B)={len(values_b)} vs len(A)={len(values_a)}",
        )
    n = len(values_b)
    if n == 0:
        raise CheckpointEvalRefusal("PAIRING_MISMATCH", "cannot compute paired statistics on empty series")
    diffs = [float(b) - float(a) for b, a in zip(values_b, values_a)]
    mean_d = _mean(diffs)
    sd_d = _sample_sd(diffs)
    se_d = sd_d / math.sqrt(n) if n > 1 else 0.0
    df = max(1, n - 1)
    if n > 1 and se_d > 0.0:
        t_stat = mean_d / se_d
        p_less = _student_t_cdf(t_stat, df)
        p_greater = 1.0 - p_less
        p_two = 2.0 * min(p_less, p_greater)
    elif mean_d == 0.0:
        t_stat = 0.0
        p_less = 0.5
        p_greater = 0.5
        p_two = 1.0
    else:
        t_stat = float("inf") if mean_d > 0 else float("-inf")
        p_less = 1.0 if mean_d > 0 else 0.0
        p_greater = 0.0 if mean_d > 0 else 1.0
        p_two = 0.0

    wilcoxon = _wilcoxon_signed_rank(diffs)
    return {
        "n": n,
        "differences": [round(d, 8) for d in diffs],
        "mean": round(mean_d, 6),
        "sd": round(sd_d, 6),
        "se": round(se_d, 6),
        "t_stat": round(t_stat, 6) if math.isfinite(t_stat) else str(t_stat),
        "df": df,
        "t_p_less": round(p_less, 8),
        "t_p_greater": round(p_greater, 8),
        "t_p_two_sided": round(p_two, 8),
        "wilcoxon": wilcoxon,
    }


def compute_mde_one_sided(sd: float, n: int, alpha: float = 0.05, power: float = 0.80) -> float:
    """Compute one-sided minimum detectable effect at given SD, sample size n, alpha, and power."""
    if n <= 1 or sd <= 0.0:
        return 0.0
    df = n - 1
    t_alpha = _student_t_ppf(1.0 - alpha, df)
    t_beta = _student_t_ppf(power, df)
    return float((t_alpha + t_beta) * sd / math.sqrt(n))


# ---------------------------------------------------------------------------
# Config & prompt / trigger-word loading
# ---------------------------------------------------------------------------


def _minimal_yaml_parse(text: str) -> dict[str, Any]:
    """Fallback parser for ai-toolkit / sdlab YAML configs when PyYAML is unavailable."""
    result: dict[str, Any] = {}
    prompts: list[str] = []
    in_prompts = False
    prompts_indent: int | None = None
    current_prompt_lines: list[str] = []

    def _flush_prompt() -> None:
        nonlocal current_prompt_lines
        if current_prompt_lines:
            joined = " ".join(current_prompt_lines).strip()
            if (joined.startswith('"') and joined.endswith('"')) or (
                joined.startswith("'") and joined.endswith("'")
            ):
                joined = joined[1:-1]
            prompts.append(joined)
            current_prompt_lines = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if in_prompts:
            if prompts_indent is not None and indent >= prompts_indent and stripped.startswith("- "):
                _flush_prompt()
                prompts_indent = indent
                current_prompt_lines.append(stripped[2:].strip())
                continue
            if prompts_indent is not None and indent > prompts_indent and current_prompt_lines:
                current_prompt_lines.append(stripped)
                continue
            _flush_prompt()
            in_prompts = False
            prompts_indent = None

        if stripped == "prompts:":
            in_prompts = True
            prompts_indent = indent
            continue

        m_kv = re.match(r"^([A-Za-z0-9_]+):\s*(.+)$", stripped)
        if m_kv:
            k, v = m_kv.group(1), m_kv.group(2).strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k == "seed" and re.match(r"^-?\d+$", v):
                result["seed"] = int(v)
            elif k == "walk_seed":
                result["walk_seed"] = v.lower() in ("true", "yes", "1")
            elif k in ("name", "trigger_word") and k not in result:
                result[k] = v
    _flush_prompt()
    result["prompts"] = prompts
    return result


def load_prompts_config(config_path: str | Path) -> dict[str, Any]:
    """Load `prompts`, `seed`, `walk_seed`, and trigger words from a YAML or JSON config file."""
    path = Path(config_path)
    if not path.is_file():
        raise CheckpointEvalRefusal("CONFIG_NOT_FOUND", f"prompts config not found: {path}")
    raw = path.read_text(encoding="utf-8")
    data: Any = None
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
    else:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(raw)
        except ImportError:
            try:
                data = json.loads(raw)
            except Exception:
                data = _minimal_yaml_parse(raw)

    if not isinstance(data, dict):
        raise CheckpointEvalRefusal("INVALID_CONFIG", f"expected mapping in {path}")

    # Navigate nested ai-toolkit structure (`config.process[0].sample`) or flat JSON/YAML
    cfg_block = data.get("config") if isinstance(data.get("config"), dict) else data
    proc_list = cfg_block.get("process") if isinstance(cfg_block, dict) else None
    proc0 = proc_list[0] if isinstance(proc_list, list) and proc_list and isinstance(proc_list[0], dict) else {}
    sample_block = proc0.get("sample") if isinstance(proc0.get("sample"), dict) else (
        cfg_block.get("sample") if isinstance(cfg_block, dict) and isinstance(cfg_block.get("sample"), dict) else data
    )

    prompts = sample_block.get("prompts") if isinstance(sample_block, dict) else None
    if prompts is None and isinstance(data.get("prompts"), list):
        prompts = data["prompts"]
    if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) for p in prompts):
        raise CheckpointEvalRefusal("INVALID_CONFIG", f"no non-empty prompts list found in {path}")

    seed = sample_block.get("seed", data.get("seed", 42))
    walk_seed = sample_block.get("walk_seed", data.get("walk_seed", True))
    name = (
        (cfg_block.get("name") if isinstance(cfg_block, dict) else None)
        or (data.get("meta", {}).get("name") if isinstance(data.get("meta"), dict) else None)
        or data.get("name")
        or ""
    )

    explicit_triggers: list[str] = []
    for src in (data, cfg_block, proc0, sample_block):
        if not isinstance(src, dict):
            continue
        for key in ("trigger_words", "trigger_word"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                explicit_triggers.append(val.strip())
            elif isinstance(val, list):
                explicit_triggers.extend(str(x).strip() for x in val if str(x).strip())

    trigger_words = extract_trigger_words(prompts, config_name=str(name), explicit=explicit_triggers)
    content_prompts = [strip_trigger_words(p, trigger_words) for p in prompts]
    ood_prompt_indices = [
        idx for idx, (orig, stripped) in enumerate(zip(prompts, content_prompts)) if orig.strip() == stripped.strip()
    ]

    return {
        "path": str(path.resolve()),
        "name": str(name),
        "seed": int(seed),
        "walk_seed": bool(walk_seed),
        "prompts": [str(p) for p in prompts],
        "trigger_words": trigger_words,
        "content_prompts": content_prompts,
        "ood_prompt_indices": ood_prompt_indices,
    }


def extract_trigger_words(
    prompts: Sequence[str],
    config_name: str = "",
    explicit: Sequence[str] | None = None,
) -> list[str]:
    """Extract style trigger phrase(s) and tokens from explicit config fields, config name, and prompts."""
    phrases: list[str] = []
    if explicit:
        for item in explicit:
            cleaned = item.strip().strip(",")
            if cleaned and cleaned not in phrases:
                phrases.append(cleaned)

    # Check derived phrase from config_name (e.g. "rustline_style_v5" -> "rustline style")
    if config_name:
        base_name = re.sub(r"[_-]v\d+[a-z]*$", "", config_name.strip(), flags=re.IGNORECASE)
        candidate = base_name.replace("_", " ").replace("-", " ").strip()
        if candidate and any(p.lower().startswith(candidate.lower()) for p in prompts):
            if candidate not in phrases:
                phrases.append(candidate)

    # Check common leading comma-separated clause shared by >= 2 prompts
    first_clauses: dict[str, int] = {}
    for p in prompts:
        if "," in p:
            clause = p.split(",", 1)[0].strip()
            if clause and len(clause.split()) <= 5:
                first_clauses[clause] = first_clauses.get(clause, 0) + 1
    for clause, count in sorted(first_clauses.items(), key=lambda kv: (-kv[1], kv[0])):
        if count >= 2 and clause not in phrases:
            phrases.append(clause)

    return phrases


def strip_trigger_words(prompt: str, trigger_words: Sequence[str]) -> str:
    """Remove trigger phrase(s) from a sample prompt to produce the content-only prompt."""
    out = prompt.strip()
    for trig in trigger_words:
        if not trig:
            continue
        pattern = re.compile(r"^\s*" + re.escape(trig) + r"\s*,\s*", re.IGNORECASE)
        out = pattern.sub("", out)
        pattern_inline = re.compile(r"\b" + re.escape(trig) + r"\b\s*,?\s*", re.IGNORECASE)
        out = pattern_inline.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip().strip(",").strip()
    return out if out else prompt.strip()


# ---------------------------------------------------------------------------
# Sample pairing and seed/prompt validation
# ---------------------------------------------------------------------------


def pair_run_samples(
    samples_dir: str | Path,
    num_prompts: int,
    requested_steps: Sequence[int] | None = None,
    run_label: str = "A",
) -> dict[int, dict[int, Path]]:
    """Scan a run's samples directory and pair files by `(step, prompt_idx)`."""
    sdir = Path(samples_dir)
    if not sdir.is_dir():
        raise CheckpointEvalRefusal("RUN_DIR_NOT_FOUND", f"run {run_label} samples directory not found: {sdir}")

    by_step: dict[int, dict[int, Path]] = {}
    for entry in sorted(sdir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        m = SAMPLE_FILENAME_RE.match(entry.name)
        if not m:
            continue
        step = int(m.group("step"))
        pidx = int(m.group("prompt_idx"))
        if pidx < 0 or pidx >= num_prompts:
            raise CheckpointEvalRefusal(
                "PAIRING_MISMATCH",
                f"run {run_label} file {entry.name} has prompt index {pidx} outside 0..{num_prompts - 1}",
            )
        step_map = by_step.setdefault(step, {})
        if pidx in step_map:
            raise CheckpointEvalRefusal(
                "PAIRING_MISMATCH",
                f"run {run_label} has duplicate sample for step={step}, prompt_idx={pidx}: "
                f"{step_map[pidx].name} and {entry.name}",
            )
        step_map[pidx] = entry

    if not by_step:
        raise CheckpointEvalRefusal("PAIRING_MISMATCH", f"no matching sample files found in run {run_label}: {sdir}")

    steps_to_check = list(requested_steps) if requested_steps is not None else sorted(by_step.keys())
    if 0 not in steps_to_check:
        steps_to_check = [0] + steps_to_check

    selected: dict[int, dict[int, Path]] = OrderedDict()
    for step in sorted(set(steps_to_check)):
        if step not in by_step:
            raise CheckpointEvalRefusal(
                "PAIRING_MISMATCH",
                f"run {run_label} is missing step {step} in {sdir} (available: {sorted(by_step.keys())})",
            )
        step_map = by_step[step]
        missing = [idx for idx in range(num_prompts) if idx not in step_map]
        if missing:
            raise CheckpointEvalRefusal(
                "PAIRING_MISMATCH",
                f"run {run_label} at step {step} is missing prompt indices {missing}",
            )
        selected[step] = OrderedDict((idx, step_map[idx]) for idx in range(num_prompts))

    return selected


def verify_configs_match(config_a: dict[str, Any], config_b: dict[str, Any]) -> None:
    """Verify that run A and run B share the exact same seed, walk_seed, and prompt list."""
    if config_a["seed"] != config_b["seed"] or config_a["walk_seed"] != config_b["walk_seed"]:
        raise CheckpointEvalRefusal(
            "SEED_MISMATCH",
            f"run A (seed={config_a['seed']}, walk_seed={config_a['walk_seed']}) != "
            f"run B (seed={config_b['seed']}, walk_seed={config_b['walk_seed']})",
        )
    if config_a["prompts"] != config_b["prompts"]:
        raise CheckpointEvalRefusal(
            "PROMPT_MISMATCH",
            f"run A and run B prompt lists do not match ({len(config_a['prompts'])} vs {len(config_b['prompts'])} prompts)",
        )


# ---------------------------------------------------------------------------
# Weight-space LoRA safetensors reader & stable-rank computation
# ---------------------------------------------------------------------------


def _bf16_bytes_to_floats(raw: bytes) -> list[float]:
    count = len(raw) // 2
    u16s = struct.unpack(f"<{count}H", raw)
    packed = struct.pack(f"<{count}I", *[u << 16 for u in u16s])
    return list(struct.unpack(f"<{count}f", packed))


def _f16_bytes_to_floats(raw: bytes) -> list[float]:
    count = len(raw) // 2
    return [float(x) for x in struct.unpack(f"<{count}e", raw)]


def _f32_bytes_to_floats(raw: bytes) -> list[float]:
    count = len(raw) // 4
    return [float(x) for x in struct.unpack(f"<{count}f", raw)]


def _jacobi_eigenvalues_symmetric(mat: list[list[float]], max_sweeps: int = 60) -> list[float]:
    """Pure-Python cyclic Jacobi eigenvalue solver for small (r x r) symmetric matrices."""
    n = len(mat)
    a = [[float(mat[i][j]) for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off_diag = 0.0
        for p in range(n):
            for q in range(p + 1, n):
                off_diag += a[p][q] * a[p][q]
        if off_diag < 1e-28:
            break
        for p in range(n):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) < 1e-15:
                    continue
                app = a[p][p]
                aqq = a[q][q]
                tau = (aqq - app) / (2.0 * apq)
                t = math.copysign(1.0 / (abs(tau) + math.sqrt(1.0 + tau * tau)), tau) if tau != 0 else 1.0
                c = 1.0 / math.sqrt(1.0 + t * t)
                s = t * c
                a[p][p] = app - t * apq
                a[q][q] = aqq + t * apq
                a[p][q] = 0.0
                a[q][p] = 0.0
                for k in range(n):
                    if k != p and k != q:
                        akp = a[k][p]
                        akq = a[k][q]
                        a[k][p] = a[p][k] = c * akp - s * akq
                        a[k][q] = a[q][k] = s * akp + c * akq
    return sorted([max(0.0, a[i][i]) for i in range(n)], reverse=True)


def _jacobi_eigh_symmetric(mat: list[list[float]], max_sweeps: int = 60) -> tuple[list[float], list[list[float]]]:
    """Pure-Python cyclic Jacobi eigenvalues and eigenvectors for an r x r symmetric matrix."""
    n = len(mat)
    a = [[float(mat[i][j]) for j in range(n)] for i in range(n)]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off_diag = sum(a[p][q] * a[p][q] for p in range(n) for q in range(p + 1, n))
        if off_diag < 1e-28:
            break
        for p in range(n):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) < 1e-15:
                    continue
                app, aqq = a[p][p], a[q][q]
                tau = (aqq - app) / (2.0 * apq)
                t = math.copysign(1.0 / (abs(tau) + math.sqrt(1.0 + tau * tau)), tau) if tau != 0 else 1.0
                c = 1.0 / math.sqrt(1.0 + t * t)
                s = t * c
                a[p][p] = app - t * apq
                a[q][q] = aqq + t * apq
                a[p][q] = a[q][p] = 0.0
                for k in range(n):
                    if k != p and k != q:
                        akp, akq = a[k][p], a[k][q]
                        a[k][p] = a[p][k] = c * akp - s * akq
                        a[k][q] = a[q][k] = s * akp + c * akq
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    evals = [max(0.0, a[i][i]) for i in range(n)]
    return evals, v


def compute_stable_rank_from_lora_pair(
    b_matrix: Any,
    a_matrix: Any,
) -> dict[str, Any]:
    """Compute singular values, stable rank, top singular value, and Frobenius norm of ΔW = B @ A."""
    try:
        import numpy as np  # type: ignore

        b_arr = np.asarray(b_matrix, dtype=np.float64)
        a_arr = np.asarray(a_matrix, dtype=np.float64)
        if b_arr.ndim != 2 or a_arr.ndim != 2 or b_arr.shape[1] != a_arr.shape[0]:
            raise ValueError(f"incompatible LoRA shapes: B={b_arr.shape}, A={a_arr.shape}")
        gb = b_arr.T @ b_arr
        ga = a_arr @ a_arr.T
        evals_b, evecs_b = np.linalg.eigh(gb)
        evals_b = np.clip(evals_b, 0.0, None)
        sb = (evecs_b * np.sqrt(evals_b)) @ evecs_b.T
        m = sb @ ga @ sb
        evals, _ = np.linalg.eigh(m)
        svals = np.sqrt(np.clip(evals[::-1], 0.0, None))
        svals_list = [float(x) for x in svals]
        out_shape = [int(b_arr.shape[0]), int(a_arr.shape[1])]
        rank = int(b_arr.shape[1])
    except ImportError:
        b_rows = [[float(x) for x in row] for row in b_matrix]
        a_rows = [[float(x) for x in row] for row in a_matrix]
        m_dim = len(b_rows)
        r_dim = len(b_rows[0]) if m_dim else 0
        n_dim = len(a_rows[0]) if a_rows else 0
        if len(a_rows) != r_dim:
            raise ValueError(f"incompatible LoRA shapes: B=({m_dim}, {r_dim}), A=({len(a_rows)}, {n_dim})")
        gb = [[sum(b_rows[k][i] * b_rows[k][j] for k in range(m_dim)) for j in range(r_dim)] for i in range(r_dim)]
        ga = [[sum(a_rows[i][k] * a_rows[j][k] for k in range(n_dim)) for j in range(r_dim)] for i in range(r_dim)]
        evals_b, evecs_b = _jacobi_eigh_symmetric(gb)
        sqrt_eb = [math.sqrt(max(0.0, ev)) for ev in evals_b]
        sb = [
            [sum(evecs_b[i][k] * sqrt_eb[k] * evecs_b[j][k] for k in range(r_dim)) for j in range(r_dim)]
            for i in range(r_dim)
        ]
        temp = [[sum(sb[i][k] * ga[k][j] for k in range(r_dim)) for j in range(r_dim)] for i in range(r_dim)]
        m_mat = [[sum(temp[i][k] * sb[k][j] for k in range(r_dim)) for j in range(r_dim)] for i in range(r_dim)]
        evals = _jacobi_eigenvalues_symmetric(m_mat)
        svals_list = [math.sqrt(max(0.0, ev)) for ev in evals]
        out_shape = [m_dim, n_dim]
        rank = r_dim

    frob_sq = sum(s * s for s in svals_list)
    frob = math.sqrt(frob_sq)
    top_sv = svals_list[0] if svals_list else 0.0
    stable_rank = (frob_sq / (top_sv * top_sv)) if top_sv > 1e-15 else 0.0
    return {
        "rank": rank,
        "shape": out_shape,
        "singular_values": [round(s, 8) for s in svals_list],
        "top_singular_value": round(top_sv, 8),
        "frobenius_norm": round(frob, 8),
        "stable_rank": round(stable_rank, 6),
    }


def _lora_inner_product_and_norms(b1: Any, a1: Any, b2: Any, a2: Any) -> tuple[float, float, float]:
    """Compute (||B1 A1||_F, ||B2 A2||_F, <B1 A1, B2 A2>_F) via r x r trace without forming m x n."""
    try:
        import numpy as np  # type: ignore

        b1_arr = np.asarray(b1, dtype=np.float64)
        a1_arr = np.asarray(a1, dtype=np.float64)
        b2_arr = np.asarray(b2, dtype=np.float64)
        a2_arr = np.asarray(a2, dtype=np.float64)
        norm1 = float(np.sqrt(max(0.0, np.trace((b1_arr.T @ b1_arr) @ (a1_arr @ a1_arr.T)))))
        norm2 = float(np.sqrt(max(0.0, np.trace((b2_arr.T @ b2_arr) @ (a2_arr @ a2_arr.T)))))
        inner = float(np.trace((b1_arr.T @ b2_arr) @ (a2_arr @ a1_arr.T)))
        return norm1, norm2, inner
    except ImportError:
        m = len(b1)
        r = len(b1[0])
        n = len(a1[0])
        b1t_b1 = [[sum(b1[k][i] * b1[k][j] for k in range(m)) for j in range(r)] for i in range(r)]
        a1_a1t = [[sum(a1[i][k] * a1[j][k] for k in range(n)) for j in range(r)] for i in range(r)]
        b2t_b2 = [[sum(b2[k][i] * b2[k][j] for k in range(m)) for j in range(r)] for i in range(r)]
        a2_a2t = [[sum(a2[i][k] * a2[j][k] for k in range(n)) for j in range(r)] for i in range(r)]
        b1t_b2 = [[sum(b1[k][i] * b2[k][j] for k in range(m)) for j in range(r)] for i in range(r)]
        a2_a1t = [[sum(a2[i][k] * a1[j][k] for k in range(n)) for j in range(r)] for i in range(r)]
        tr1 = sum(b1t_b1[i][j] * a1_a1t[j][i] for i in range(r) for j in range(r))
        tr2 = sum(b2t_b2[i][j] * a2_a2t[j][i] for i in range(r) for j in range(r))
        inner = sum(b1t_b2[i][j] * a2_a1t[j][i] for i in range(r) for j in range(r))
        return math.sqrt(max(0.0, tr1)), math.sqrt(max(0.0, tr2)), inner


def _load_safetensors_tensors(path: Path) -> dict[str, Any]:
    """Load tensors from a `.safetensors` file (uses `safetensors`+`numpy` when available, pure-Python fallback)."""
    try:
        from safetensors import safe_open  # type: ignore

        tensors: dict[str, Any] = {}
        with safe_open(str(path), framework="numpy") as f:
            for k in f.keys():
                tensors[k] = f.get_tensor(k)
        return tensors
    except ImportError:
        raw = path.read_bytes()
        if len(raw) < 8:
            raise CheckpointEvalRefusal("INVALID_SAFETENSORS", f"safetensors file too short: {path}")
        header_len = struct.unpack("<Q", raw[:8])[0]
        header_bytes = raw[8 : 8 + header_len]
        header = json.loads(header_bytes.decode("utf-8"))
        body = raw[8 + header_len :]
        tensors = {}
        for k, meta in header.items():
            if k == "__metadata__":
                continue
            dtype = meta["dtype"]
            shape = meta["shape"]
            start, end = meta["data_offsets"]
            chunk = body[start:end]
            if dtype == "F16":
                vals = _f16_bytes_to_floats(chunk)
            elif dtype == "BF16":
                vals = _bf16_bytes_to_floats(chunk)
            elif dtype == "F32":
                vals = _f32_bytes_to_floats(chunk)
            else:
                raise CheckpointEvalRefusal("INVALID_SAFETENSORS", f"unsupported dtype {dtype} in {path}")
            if len(shape) == 2:
                rows, cols = shape
                tensors[k] = [vals[r * cols : (r + 1) * cols] for r in range(rows)]
            else:
                tensors[k] = vals
        return tensors


def _block_and_submodule(layer_key: str) -> tuple[str, str]:
    m = re.match(r"^(?:diffusion_model\.)?(transformer_blocks\.\d+)\.([^.]+)", layer_key)
    if m:
        return m.group(1), m.group(2)
    parts = layer_key.split(".")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "root", layer_key


def read_safetensors_weight_space(
    checkpoint_paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Read LoRA weight-space singular values, stable rank, Frobenius norm, and pairwise comparison."""
    t0 = time.perf_counter()
    loaded: list[tuple[str, Path, dict[str, Any]]] = []
    for cp in checkpoint_paths:
        p = Path(cp)
        if not p.is_file():
            raise CheckpointEvalRefusal("CHECKPOINT_NOT_FOUND", f"checkpoint not found: {p}")
        loaded.append((p.name, p, _load_safetensors_tensors(p)))

    per_checkpoint: dict[str, Any] = OrderedDict()
    layer_tensors_by_ckpt: list[dict[str, tuple[Any, Any]]] = []

    for ckpt_name, ckpt_path, tensors in loaded:
        ckpt_t0 = time.perf_counter()
        pairs: dict[str, tuple[Any, Any]] = OrderedDict()
        a_suffixes = (".lora_A.weight", ".lora_down.weight")
        for key in sorted(tensors.keys()):
            for a_sfx in a_suffixes:
                if key.endswith(a_sfx):
                    base = key[: -len(a_sfx)]
                    b_sfx = ".lora_B.weight" if a_sfx == ".lora_A.weight" else ".lora_up.weight"
                    b_key = base + b_sfx
                    if b_key in tensors:
                        pairs[base] = (tensors[b_key], tensors[key])
        if not pairs:
            raise CheckpointEvalRefusal("INVALID_SAFETENSORS", f"no LoRA A/B layer pairs found in {ckpt_path}")

        layer_tensors_by_ckpt.append(pairs)
        layers_out: dict[str, Any] = OrderedDict()
        by_block: dict[str, list[dict[str, Any]]] = OrderedDict()
        by_submodule: dict[str, list[dict[str, Any]]] = OrderedDict()

        for base_key, (b_mat, a_mat) in pairs.items():
            stats = compute_stable_rank_from_lora_pair(b_mat, a_mat)
            block_name, submod_name = _block_and_submodule(base_key)
            stats["block"] = block_name
            stats["submodule"] = submod_name
            layers_out[base_key] = stats
            by_block.setdefault(block_name, []).append(stats)
            by_submodule.setdefault(submod_name, []).append(stats)

        def _summarize_group(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
            sr = [float(x["stable_rank"]) for x in items]
            tsv = [float(x["top_singular_value"]) for x in items]
            fn = [float(x["frobenius_norm"]) for x in items]
            return {
                "num_layers": len(items),
                "stable_rank_mean": round(_mean(sr), 4),
                "stable_rank_sd": round(_sample_sd(sr), 4),
                "stable_rank_min": round(min(sr), 4) if sr else 0.0,
                "stable_rank_median": round(_median(sr), 4),
                "stable_rank_max": round(max(sr), 4) if sr else 0.0,
                "layers_below_stable_rank_2": sum(1 for v in sr if v < 2.0),
                "top_singular_value_mean": round(_mean(tsv), 6),
                "top_singular_value_max": round(max(tsv), 6) if tsv else 0.0,
                "frobenius_norm_mean": round(_mean(fn), 6),
                "frobenius_norm_max": round(max(fn), 6) if fn else 0.0,
            }

        block_summary = OrderedDict((blk, _summarize_group(items)) for blk, items in by_block.items())
        submodule_summary = OrderedDict((sub, _summarize_group(items)) for sub, items in by_submodule.items())
        overall = _summarize_group(list(layers_out.values()))
        per_checkpoint[ckpt_name] = {
            "path": str(ckpt_path.resolve()),
            "wall_time_s": round(time.perf_counter() - ckpt_t0, 4),
            "overall": overall,
            "by_submodule": submodule_summary,
            "by_block": block_summary,
            "layers": layers_out,
        }

    pairwise_comparison: dict[str, Any] | None = None
    if len(loaded) >= 2:
        name1, _, _ = loaded[0]
        name2, _, _ = loaded[1]
        pairs1 = layer_tensors_by_ckpt[0]
        pairs2 = layer_tensors_by_ckpt[1]
        common_keys = [k for k in pairs1.keys() if k in pairs2]
        per_layer_cmp: dict[str, Any] = OrderedDict()
        by_block_cmp: dict[str, list[dict[str, float]]] = OrderedDict()
        by_submod_cmp: dict[str, list[dict[str, float]]] = OrderedDict()

        for k in common_keys:
            b1, a1 = pairs1[k]
            b2, a2 = pairs2[k]
            n1, n2, inner = _lora_inner_product_and_norms(b1, a1, b2, a2)
            ratio = (n2 / n1) if n1 > 1e-15 else 0.0
            cos = (inner / (n1 * n2)) if (n1 > 1e-15 and n2 > 1e-15) else 0.0
            cos = max(-1.0, min(1.0, cos))
            sr1 = per_checkpoint[name1]["layers"][k]["stable_rank"]
            sr2 = per_checkpoint[name2]["layers"][k]["stable_rank"]
            rec = {
                "norm_1": round(n1, 6),
                "norm_2": round(n2, 6),
                "norm_ratio": round(ratio, 6),
                "cosine": round(cos, 6),
                "delta_stable_rank": round(sr2 - sr1, 6),
            }
            per_layer_cmp[k] = rec
            blk, sub = _block_and_submodule(k)
            by_block_cmp.setdefault(blk, []).append(rec)
            by_submod_cmp.setdefault(sub, []).append(rec)

        def _summarize_cmp(items: Sequence[dict[str, float]]) -> dict[str, Any]:
            ratios = [x["norm_ratio"] for x in items]
            cosines = [x["cosine"] for x in items]
            dsr = [x["delta_stable_rank"] for x in items]
            return {
                "num_layers": len(items),
                "norm_ratio_mean": round(_mean(ratios), 6),
                "norm_ratio_sd": round(_sample_sd(ratios), 6),
                "norm_ratio_min": round(min(ratios), 6) if ratios else 0.0,
                "norm_ratio_max": round(max(ratios), 6) if ratios else 0.0,
                "cosine_mean": round(_mean(cosines), 6),
                "cosine_sd": round(_sample_sd(cosines), 6),
                "cosine_min": round(min(cosines), 6) if cosines else 0.0,
                "cosine_max": round(max(cosines), 6) if cosines else 0.0,
                "delta_stable_rank_mean": round(_mean(dsr), 6),
            }

        pairwise_comparison = {
            "checkpoint_1": name1,
            "checkpoint_2": name2,
            "overall": _summarize_cmp(list(per_layer_cmp.values())),
            "by_submodule": OrderedDict((s, _summarize_cmp(v)) for s, v in by_submod_cmp.items()),
            "by_block": OrderedDict((b, _summarize_cmp(v)) for b, v in by_block_cmp.items()),
            "layers": per_layer_cmp,
        }

    return {
        "wall_time_s": round(time.perf_counter() - t0, 4),
        "checkpoints": per_checkpoint,
        "pairwise_comparison": pairwise_comparison,
    }


# ---------------------------------------------------------------------------
# Embedder backends: FakeEmbedder (synthetic tests) & RealEmbedder (CPU/OpenVINO)
# ---------------------------------------------------------------------------


def _read_small_image_bytes(path: Path) -> bytes:
    """Read pixel/file bytes from a synthetic image for deterministic fake embedding."""
    return path.read_bytes()


def _unit_vec_from_seed_bytes(seed_bytes: bytes, dim: int = 16) -> list[float]:
    vals: list[float] = []
    counter = 0
    while len(vals) < dim:
        digest = hashlib.sha256(seed_bytes + counter.to_bytes(4, "little")).digest()
        for i in range(0, len(digest), 4):
            if len(vals) >= dim:
                break
            u = struct.unpack("<I", digest[i : i + 4])[0]
            vals.append((u / 2147483647.5) - 1.0)
        counter += 1
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


def _cosine(u: Sequence[float], v: Sequence[float]) -> float:
    return float(sum(a * b for a, b in zip(u, v)))


class FakeEmbedder:
    """Deterministic lightweight embedder for unit tests on synthetic fixtures (no network or weights)."""

    device_description = "cpu (synthetic fake embedder)"
    models_used = MODEL_LICENCE_TABLE

    def __init__(self, dim: int = 16) -> None:
        self.dim = dim

    def embed_csd_images(self, paths: Sequence[Path]) -> list[list[float]]:
        return [_unit_vec_from_seed_bytes(b"CSD:" + _read_small_image_bytes(p), self.dim) for p in paths]

    def embed_dino_images(self, paths: Sequence[Path]) -> list[list[float]]:
        return [_unit_vec_from_seed_bytes(b"DINO:" + _read_small_image_bytes(p), self.dim) for p in paths]

    def embed_dreamsim_images(self, paths: Sequence[Path]) -> list[list[float]]:
        return [_unit_vec_from_seed_bytes(b"DREAMSIM:" + _read_small_image_bytes(p), self.dim) for p in paths]

    def embed_clip_images(self, paths: Sequence[Path]) -> list[list[float]]:
        return [_unit_vec_from_seed_bytes(b"CLIP_IMG:" + _read_small_image_bytes(p), self.dim) for p in paths]

    def embed_clip_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [_unit_vec_from_seed_bytes(b"CLIP_TXT:" + t.encode("utf-8"), self.dim) for t in texts]


def _build_csd_vit_large(checkpoint_path: str | Path) -> Any:  # pragma: no cover
    """Construct CSD_CLIP ViT-L/14 architecture and load `tomg-group-umd/CSD-ViT-L` weights on CPU."""
    import torch
    from torch import nn
    import torch.nn.functional as F

    class LayerNorm(nn.LayerNorm):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            orig_type = x.dtype
            return super().forward(x.type(torch.float32)).type(orig_type)

    class QuickGELU(nn.Module):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return x * torch.sigmoid(1.702 * x)

    class ResidualAttentionBlock(nn.Module):
        def __init__(self, d_model: int, n_head: int) -> None:
            super().__init__()
            self.attn = nn.MultiheadAttention(d_model, n_head)
            self.ln_1 = LayerNorm(d_model)
            self.mlp = nn.Sequential(
                OrderedDict(
                    [
                        ("c_fc", nn.Linear(d_model, d_model * 4)),
                        ("gelu", QuickGELU()),
                        ("c_proj", nn.Linear(d_model * 4, d_model)),
                    ]
                )
            )
            self.ln_2 = LayerNorm(d_model)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = x + self.attn(self.ln_1(x), self.ln_1(x), self.ln_1(x), need_weights=False)[0]
            x = x + self.mlp(self.ln_2(x))
            return x

    class Transformer(nn.Module):
        def __init__(self, width: int, layers: int, heads: int) -> None:
            super().__init__()
            self.resblocks = nn.Sequential(*[ResidualAttentionBlock(width, heads) for _ in range(layers)])

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.resblocks(x)

    class VisionTransformer(nn.Module):
        def __init__(self, input_resolution: int, patch_size: int, width: int, layers: int, heads: int) -> None:
            super().__init__()
            self.conv1 = nn.Conv2d(3, width, kernel_size=patch_size, stride=patch_size, bias=False)
            self.class_embedding = nn.Parameter(torch.zeros(width))
            self.positional_embedding = nn.Parameter(torch.zeros((input_resolution // patch_size) ** 2 + 1, width))
            self.ln_pre = LayerNorm(width)
            self.transformer = Transformer(width, layers, heads)
            self.ln_post = LayerNorm(width)
            self.proj = None

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = self.conv1(x)
            x = x.reshape(x.shape[0], x.shape[1], -1).permute(0, 2, 1)
            cls_tok = self.class_embedding.to(x.dtype) + torch.zeros(
                x.shape[0], 1, x.shape[-1], dtype=x.dtype, device=x.device
            )
            x = torch.cat([cls_tok, x], dim=1)
            x = x + self.positional_embedding.to(x.dtype)
            x = self.ln_pre(x)
            x = x.permute(1, 0, 2)
            x = self.transformer(x)
            x = x.permute(1, 0, 2)
            return self.ln_post(x[:, 0, :])

    class CSDViTL(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = VisionTransformer(224, 14, 1024, 24, 16)
            self.last_layer_style = nn.Parameter(torch.zeros(1024, 768))
            self.last_layer_content = nn.Parameter(torch.zeros(1024, 768))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            feat = self.backbone(x)
            style = feat @ self.last_layer_style
            return F.normalize(style, dim=-1, p=2)

    model = CSDViTL()
    ckpt = torch.load(str(checkpoint_path), map_location="cpu", weights_only=False)
    raw_sd = ckpt.get("model_state_dict", ckpt.get("state_dict", ckpt))
    clean_sd = {k.removeprefix("module."): v for k, v in raw_sd.items()}
    model.load_state_dict(clean_sd, strict=True)
    model.eval().requires_grad_(False)
    return model


class RealEmbedder:  # pragma: no cover
    """Real model embedder running strictly on CPU or Intel OpenVINO (never NVIDIA GPU)."""

    models_used = MODEL_LICENCE_TABLE

    def __init__(self, device: str = "cpu", batch_size: int = 16) -> None:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore
        import torch  # type: ignore
        import torch.nn.functional as F  # type: ignore
        from torchvision import transforms  # type: ignore
        from huggingface_hub import hf_hub_download  # type: ignore
        from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor  # type: ignore
        from dreamsim import dreamsim  # type: ignore

        if torch.cuda.is_available():
            raise CheckpointEvalRefusal("NVIDIA_GPU_FORBIDDEN", "CUDA must not be visible during checkpoint-eval")

        self.np = np
        self.Image = Image
        self.torch = torch
        self.F = F
        self.device_mode = device.lower()
        self.batch_size = batch_size

        # 1. CSD-ViT-L
        csd_ckpt = hf_hub_download(
            "tomg-group-umd/CSD-ViT-L",
            "pytorch_model.bin",
            revision="5bc26a6fb0487f3f00a2a7313135103a005b1b67",
        )
        self.csd_model = _build_csd_vit_large(csd_ckpt)
        self.csd_preprocess = transforms.Compose(
            [
                transforms.Resize(size=224, interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize((0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711)),
            ]
        )

        # 2. Content-only CLIP-T (openai/clip-vit-base-patch32)
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to("cpu").eval()
        self.clip_proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        # 3. DINOv2 (facebook/dinov2-base)
        self.dino_model = AutoModel.from_pretrained("facebook/dinov2-base").to("cpu").eval()
        self.dino_proc = AutoImageProcessor.from_pretrained("facebook/dinov2-base")

        # 4. DreamSim (open_clip_vitb32, v0.2.1)
        orig_load = torch.load

        def _cpu_load(*args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("map_location", "cpu")
            return orig_load(*args, **kwargs)

        torch.load = _cpu_load
        try:
            hf_home = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
            ds_cache = str(Path(hf_home) / "dreamsim")
            self.dreamsim_model, self.dreamsim_preprocess = dreamsim(
                pretrained=True,
                device="cpu",
                cache_dir=ds_cache,
                dreamsim_type="open_clip_vitb32",
            )
        finally:
            torch.load = orig_load

        self.ov_dino_compiled = None
        if self.device_mode == "openvino":
            import openvino as ov  # type: ignore

            core = ov.Core()
            intel_devices = []
            for d in core.available_devices:
                full_name = core.get_property(d, "FULL_DEVICE_NAME")
                if "NVIDIA" in full_name.upper():
                    continue
                if "INTEL" in full_name.upper():
                    intel_devices.append((d, full_name))
            if not intel_devices:
                raise CheckpointEvalRefusal("OPENVINO_NO_INTEL_DEVICE", "no Intel OpenVINO device found")
            # Prefer Intel iGPU (GPU.0) or NPU or Intel CPU
            target_dev = next((d for d, _ in intel_devices if d.startswith("GPU")), intel_devices[0][0])
            target_name = dict(intel_devices)[target_dev]

            class _DinoWrapper(torch.nn.Module):
                def __init__(self, mod: Any) -> None:
                    super().__init__()
                    self.mod = mod

                def forward(self, pixel_values: Any) -> Any:
                    return self.mod(pixel_values=pixel_values).pooler_output

            dummy = torch.zeros(1, 3, 224, 224, dtype=torch.float32)
            ov_model = ov.convert_model(_DinoWrapper(self.dino_model), example_input=dummy)
            self.ov_dino_compiled = core.compile_model(ov_model, target_dev)
            self.device_description = f"openvino:{target_dev} ({target_name}) + cpu (Intel Core Ultra 9 285K, CUDA_VISIBLE_DEVICES='')"
        else:
            self.device_description = "cpu (PyTorch CPU, CUDA_VISIBLE_DEVICES='')"

    @staticmethod
    def _extract_tensor(feat_out: Any, torch_mod: Any) -> Any:
        if torch_mod.is_tensor(feat_out):
            return feat_out
        for attr in ("image_embeds", "text_embeds", "pooler_output", "last_hidden_state"):
            val = getattr(feat_out, attr, None)
            if torch_mod.is_tensor(val):
                return val
        raise TypeError(f"Unrecognized feature output type: {type(feat_out)}")

    def embed_csd_images(self, paths: Sequence[Path]) -> list[list[float]]:
        out: list[list[float]] = []
        with self.torch.no_grad():
            for i in range(0, len(paths), self.batch_size):
                batch_paths = paths[i : i + self.batch_size]
                tensors = [self.csd_preprocess(self.Image.open(p).convert("RGB")) for p in batch_paths]
                batch = self.torch.stack(tensors, dim=0)
                feats = self.csd_model(batch)
                feats = self.F.normalize(feats, dim=-1, p=2).cpu().numpy()
                out.extend( row.tolist() for row in feats )
        return out

    def embed_dino_images(self, paths: Sequence[Path]) -> list[list[float]]:
        out: list[list[float]] = []
        with self.torch.no_grad():
            for i in range(0, len(paths), self.batch_size):
                batch_paths = paths[i : i + self.batch_size]
                imgs = [self.Image.open(p).convert("RGB") for p in batch_paths]
                inp = self.dino_proc(images=imgs, return_tensors="pt")
                if self.ov_dino_compiled is not None:
                    vecs = []
                    for j in range(inp["pixel_values"].shape[0]):
                        single = inp["pixel_values"][j : j + 1].numpy()
                        res = self.ov_dino_compiled(single)[0]
                        vecs.append(self.torch.from_numpy(res))
                    raw = self.torch.cat(vecs, dim=0)
                else:
                    raw = self.dino_model(**inp).pooler_output
                normed = self.F.normalize(raw, dim=-1, p=2).cpu().numpy()
                out.extend(row.tolist() for row in normed)
        return out

    def embed_dreamsim_images(self, paths: Sequence[Path]) -> list[list[float]]:
        out: list[list[float]] = []
        with self.torch.no_grad():
            for i in range(0, len(paths), self.batch_size):
                batch_paths = paths[i : i + self.batch_size]
                tensors = [self.dreamsim_preprocess(self.Image.open(p).convert("RGB")).squeeze(0) for p in batch_paths]
                batch = self.torch.stack(tensors, dim=0)
                embeds = self.dreamsim_model.embed(batch)
                normed = self.F.normalize(embeds, dim=-1, p=2).cpu().numpy()
                out.extend(row.tolist() for row in normed)
        return out

    def embed_clip_images(self, paths: Sequence[Path]) -> list[list[float]]:
        out: list[list[float]] = []
        with self.torch.no_grad():
            for i in range(0, len(paths), self.batch_size):
                batch_paths = paths[i : i + self.batch_size]
                imgs = [self.Image.open(p).convert("RGB") for p in batch_paths]
                inp = self.clip_proc(images=imgs, return_tensors="pt")
                raw = self._extract_tensor(self.clip_model.get_image_features(**inp), self.torch)
                normed = self.F.normalize(raw, dim=-1, p=2).cpu().numpy()
                out.extend(row.tolist() for row in normed)
        return out

    def embed_clip_texts(self, texts: Sequence[str]) -> list[list[float]]:
        with self.torch.no_grad():
            inp = self.clip_proc(text=list(texts), return_tensors="pt", padding=True, truncation=True)
            raw = self._extract_tensor(self.clip_model.get_text_features(**inp), self.torch)
            normed = self.F.normalize(raw, dim=-1, p=2).cpu().numpy()
            return [row.tolist() for row in normed]


# ---------------------------------------------------------------------------
# Training-set embedding cache under `--out`
# ---------------------------------------------------------------------------


def _training_dir_fingerprint(training_files: Sequence[Path]) -> str:
    h = hashlib.sha256()
    for p in training_files:
        st = p.stat()
        h.update(f"{p.name}:{st.st_size}\n".encode("utf-8"))
    return h.hexdigest()


def get_or_create_training_embeddings(
    training_dir: str | Path,
    out_dir: str | Path,
    embedder: Any,
) -> dict[str, Any]:
    """Embed the training set once with CSD and DINOv2 and cache under `<out>/cache/training_embeddings.json`."""
    tdir = Path(training_dir)
    if not tdir.is_dir():
        raise CheckpointEvalRefusal("TRAINING_DIR_NOT_FOUND", f"training directory not found: {tdir}")
    training_files = sorted(
        [p for p in tdir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: p.name,
    )
    if not training_files:
        raise CheckpointEvalRefusal("TRAINING_DIR_EMPTY", f"no images found in training directory: {tdir}")

    fingerprint = _training_dir_fingerprint(training_files)
    cache_dir = Path(out_dir) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "training_embeddings.json"

    if cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if (
                cached.get("fingerprint") == fingerprint
                and cached.get("num_images") == len(training_files)
                and len(cached.get("csd_embeddings", [])) == len(training_files)
                and len(cached.get("dino_embeddings", [])) == len(training_files)
            ):
                cached["cache_hit"] = True
                return cached
        except Exception:
            pass

    t0 = time.perf_counter()
    csd_embeds = embedder.embed_csd_images(training_files)
    dino_embeds = embedder.embed_dino_images(training_files)
    wall_s = round(time.perf_counter() - t0, 4)

    payload = {
        "fingerprint": fingerprint,
        "num_images": len(training_files),
        "filenames": [p.name for p in training_files],
        "csd_embeddings": csd_embeds,
        "dino_embeddings": dino_embeds,
        "embed_wall_time_s": wall_s,
        "cache_hit": False,
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# Corridors file (`corridors.md`) generation & tamper verification
# ---------------------------------------------------------------------------


def _compute_corridors_body_sha256(text_with_placeholder: str) -> str:
    return hashlib.sha256(text_with_placeholder.encode("utf-8")).hexdigest()


def build_corridors_payload(run_a_summary: dict[str, Any], topk: int = 5) -> dict[str, Any]:
    """Build run-A-anchored decision corridors for steps 250, 500, and pooled 250+500 (n=12)."""
    steps_map = run_a_summary["steps"]
    step250 = steps_map.get("250") or steps_map.get(250)
    step500 = steps_map.get("500") or steps_map.get(500)
    if not step250 or not step500:
        # Fallback if synthetic test uses different step numbers: pick first two non-zero steps
        nz_keys = [k for k in steps_map.keys() if int(k) != 0]
        if len(nz_keys) >= 2:
            step250 = steps_map[nz_keys[0]]
            step500 = steps_map[nz_keys[1]]
        elif len(nz_keys) == 1:
            step250 = step500 = steps_map[nz_keys[0]]
        else:
            step250 = step500 = next(iter(steps_map.values()))

    n_per_step = int(run_a_summary["num_prompts"])
    n_pooled = 2 * n_per_step
    sd_est = float(run_a_summary["paired_diff_sd_estimate"]["value"])
    mde_pooled_one_sided = round(compute_mde_one_sided(sd_est, n_pooled, alpha=0.05, power=0.80), 6)
    mde_single_one_sided = round(compute_mde_one_sided(sd_est, n_per_step, alpha=0.05, power=0.80), 6)

    a_csd_250 = float(step250["csd_topk"]["mean"])
    a_csd_500 = float(step500["csd_topk"]["mean"])
    a_dcsd_250 = float(step250["delta_csd"]["mean"])
    a_dcsd_500 = float(step500["delta_csd"]["mean"])
    a_dclip_250 = float(step250["delta_clip_t"]["mean"])
    a_dclip_500 = float(step500["delta_clip_t"]["mean"])
    a_ddino_250 = float(step250["delta_dino_nn"]["mean"])
    a_ddino_500 = float(step500["delta_dino_nn"]["mean"])
    a_ds0_250 = float(step250["dreamsim_to_step0"]["mean"])
    a_ds0_500 = float(step500["dreamsim_to_step0"]["mean"])

    return {
        "schema_version": "1.0",
        "anchored_to_run": "A",
        "topk": topk,
        "sample_size": {
            "per_step_n": n_per_step,
            "pooled_250_500_n": n_pooled,
        },
        "measured_sd": {
            "paired_diff_sd_estimate": round(sd_est, 6),
            "estimator": run_a_summary["paired_diff_sd_estimate"]["estimator"],
            "step_250_delta_csd_sd": float(step250["delta_csd"]["sd"]),
            "step_500_delta_csd_sd": float(step500["delta_csd"]["sd"]),
            "report_assumed_sd_replaced": 0.035,
            "mde_one_sided_alpha05_power80_pooled_n12": mde_pooled_one_sided,
            "mde_one_sided_alpha05_power80_single_n6": mde_single_one_sided,
        },
        "run_a_anchors": {
            "step_250": {
                "csd_topk_mean": round(a_csd_250, 6),
                "delta_csd_mean": round(a_dcsd_250, 6),
                "delta_clip_t_mean": round(a_dclip_250, 6),
                "delta_dino_nn_mean": round(a_ddino_250, 6),
                "dreamsim_to_step0_mean": round(a_ds0_250, 6),
            },
            "step_500": {
                "csd_topk_mean": round(a_csd_500, 6),
                "delta_csd_mean": round(a_dcsd_500, 6),
                "delta_clip_t_mean": round(a_dclip_500, 6),
                "delta_dino_nn_mean": round(a_ddino_500, 6),
                "dreamsim_to_step0_mean": round(a_ds0_500, 6),
            },
        },
        "bands": {
            "velocity_ratio_rho": {
                "promote_min": 0.85,
                "kill_below": 0.70,
                "step_250_promote_min_delta_csd": round(0.85 * a_dcsd_250, 6),
                "step_250_kill_below_delta_csd": round(0.70 * a_dcsd_250, 6),
                "step_500_promote_min_delta_csd": round(0.85 * a_dcsd_500, 6),
                "step_500_kill_below_delta_csd": round(0.70 * a_dcsd_500, 6),
            },
            "b_minus_a_csd": {
                "promote_min": -0.020,
                "kill_below": -0.035,
                "step_250_promote_min_csd": round(a_csd_250 - 0.020, 6),
                "step_250_kill_below_csd": round(a_csd_250 - 0.035, 6),
                "step_500_promote_min_csd": round(a_csd_500 - 0.020, 6),
                "step_500_kill_below_csd": round(a_csd_500 - 0.035, 6),
            },
            "delta_clip_t_guard": {
                "relative_promote_min": -0.012,
                "relative_kill_below": -0.025,
                "step_250_promote_min_delta_clip_t": round(a_dclip_250 - 0.012, 6),
                "step_250_kill_below_delta_clip_t": round(a_dclip_250 - 0.025, 6),
                "step_500_promote_min_delta_clip_t": round(a_dclip_500 - 0.012, 6),
                "step_500_kill_below_delta_clip_t": round(a_dclip_500 - 0.025, 6),
            },
            "delta_dino_nn_guard": {
                "relative_promote_max_above_a": 0.050,
                "relative_kill_above_a": 0.085,
                "step_250_promote_max_delta_dino_nn": round(a_ddino_250 + 0.050, 6),
                "step_250_kill_above_delta_dino_nn": round(a_ddino_250 + 0.085, 6),
                "step_500_promote_max_delta_dino_nn": round(a_ddino_500 + 0.050, 6),
                "step_500_kill_above_delta_dino_nn": round(a_ddino_500 + 0.085, 6),
                "must_not_exceed_delta_csd": True,
            },
            "dreamsim_b_vs_a": {
                "promote_max": 0.180,
                "kill_above": 0.250,
            },
        },
    }


def write_corridors_file(
    corridors_path: str | Path,
    run_a_summary: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Write `corridors.md` from run A's numbers before any run B exists, embedding its creation time and sha256."""
    cpath = Path(corridors_path)
    cpath.parent.mkdir(parents=True, exist_ok=True)
    ts = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = build_corridors_payload(run_a_summary)
    payload["created_at"] = ts

    a250 = payload["run_a_anchors"]["step_250"]
    a500 = payload["run_a_anchors"]["step_500"]
    bands = payload["bands"]
    vel = bands["velocity_ratio_rho"]
    csd_b = bands["b_minus_a_csd"]
    clip_b = bands["delta_clip_t_guard"]
    dino_b = bands["delta_dino_nn_guard"]
    ds_b = bands["dreamsim_b_vs_a"]
    msd = payload["measured_sd"]
    ssz = payload["sample_size"]

    json_block = json.dumps(payload, indent=2, sort_keys=True)

    template = f"""# Early-Checkpoint Promotion Corridors (Anchored to Run A)

- **created_at:** `{ts}`
- **body_sha256:** `{CORRIDORS_SHA_PLACEHOLDER}`
- **per_step_sample_size:** `n = {ssz['per_step_n']}` prompts per step
- **pooled_sample_size:** `n = {ssz['pooled_250_500_n']}` paired samples (steps 250 + 500 pooled)
- **measured_sd_estimate:** `{msd['paired_diff_sd_estimate']:.6f}` (`{msd['estimator']}`; replaces report's assumed `0.035`)
- **step_250_delta_csd_sd:** `{msd['step_250_delta_csd_sd']:.6f}`
- **step_500_delta_csd_sd:** `{msd['step_500_delta_csd_sd']:.6f}`
- **one_sided_mde_alpha05_power80 (pooled n={ssz['pooled_250_500_n']}):** `{msd['mde_one_sided_alpha05_power80_pooled_n12']:.6f}`

## Run A Anchor Values

| Step | CSD top-5 mean | ΔCSD vs step 0 | ΔCLIP-T vs step 0 | ΔDINO-NN vs step 0 | DreamSim vs step 0 |
|---:|---:|---:|---:|---:|---:|
| 250 | {a250['csd_topk_mean']:.6f} | {a250['delta_csd_mean']:+.6f} | {a250['delta_clip_t_mean']:+.6f} | {a250['delta_dino_nn_mean']:+.6f} | {a250['dreamsim_to_step0_mean']:.6f} |
| 500 | {a500['csd_topk_mean']:.6f} | {a500['delta_csd_mean']:+.6f} | {a500['delta_clip_t_mean']:+.6f} | {a500['delta_dino_nn_mean']:+.6f} | {a500['dreamsim_to_step0_mean']:.6f} |

## Decision Corridors (Promote / Borderline / Kill)

### Step 250 Corridors (n = {ssz['per_step_n']}, SD = {msd['step_250_delta_csd_sd']:.6f})

| Metric | Promote | Borderline | Kill |
|---|---|---|---|
| Style velocity ratio ρ₂₅₀ = ΔCSD_B(250) / ΔCSD_A(250) | ≥ {vel['promote_min']:.2f} (ΔCSD_B ≥ {vel['step_250_promote_min_delta_csd']:+.6f}) | [{vel['kill_below']:.2f}, {vel['promote_min']:.2f}) | < {vel['kill_below']:.2f} (ΔCSD_B < {vel['step_250_kill_below_delta_csd']:+.6f}) |
| Paired CSD difference (B − A) at step 250 | ≥ {csd_b['promote_min']:+.3f} (CSD_B ≥ {csd_b['step_250_promote_min_csd']:.6f}) | [{csd_b['kill_below']:+.3f}, {csd_b['promote_min']:+.3f}) | < {csd_b['kill_below']:+.3f} (CSD_B < {csd_b['step_250_kill_below_csd']:.6f}) |
| Content-only ΔCLIP-T(250) guard (anchored to A: {a250['delta_clip_t_mean']:+.6f}) | ≥ {clip_b['step_250_promote_min_delta_clip_t']:+.6f} (B−A ≥ {clip_b['relative_promote_min']:+.3f}) | [{clip_b['step_250_kill_below_delta_clip_t']:+.6f}, {clip_b['step_250_promote_min_delta_clip_t']:+.6f}) | < {clip_b['step_250_kill_below_delta_clip_t']:+.6f} (B−A < {clip_b['relative_kill_below']:+.3f}) |
| Memorization ΔDINO-NN(250) guard (anchored to A: {a250['delta_dino_nn_mean']:+.6f}) | ≤ {dino_b['step_250_promote_max_delta_dino_nn']:+.6f} and ≤ ΔCSD_B(250) | ({dino_b['step_250_promote_max_delta_dino_nn']:+.6f}, {dino_b['step_250_kill_above_delta_dino_nn']:+.6f}] | > {dino_b['step_250_kill_above_delta_dino_nn']:+.6f} or > ΔCSD_B(250) |
| Seed-matched DreamSim(B, A) at step 250 | ≤ {ds_b['promote_max']:.3f} | ({ds_b['promote_max']:.3f}, {ds_b['kill_above']:.3f}] | > {ds_b['kill_above']:.3f} with lower CSD |

### Step 500 & Pooled (250 + 500, n = {ssz['pooled_250_500_n']}, SD = {msd['paired_diff_sd_estimate']:.6f}) Corridors

| Metric | Promote | Borderline | Kill |
|---|---|---|---|
| Style velocity ratio ρ = ΔCSD_B(500) / ΔCSD_A(500) | ≥ {vel['promote_min']:.2f} (ΔCSD_B ≥ {vel['step_500_promote_min_delta_csd']:+.6f}) | [{vel['kill_below']:.2f}, {vel['promote_min']:.2f}) | < {vel['kill_below']:.2f} (ΔCSD_B < {vel['step_500_kill_below_delta_csd']:+.6f}) |
| Pooled B − A CSD difference (steps 250+500, n = {ssz['pooled_250_500_n']}) | ≥ {csd_b['promote_min']:+.3f} (step 500 CSD_B ≥ {csd_b['step_500_promote_min_csd']:.6f}) | [{csd_b['kill_below']:+.3f}, {csd_b['promote_min']:+.3f}) | < {csd_b['kill_below']:+.3f} (step 500 CSD_B < {csd_b['step_500_kill_below_csd']:.6f}) |
| Content-only ΔCLIP-T(500) guard (anchored to A: {a500['delta_clip_t_mean']:+.6f}) | ≥ {clip_b['step_500_promote_min_delta_clip_t']:+.6f} (B−A ≥ {clip_b['relative_promote_min']:+.3f}) | [{clip_b['step_500_kill_below_delta_clip_t']:+.6f}, {clip_b['step_500_promote_min_delta_clip_t']:+.6f}) | < {clip_b['step_500_kill_below_delta_clip_t']:+.6f} (B−A < {clip_b['relative_kill_below']:+.3f}) |
| Memorization ΔDINO-NN(500) guard (anchored to A: {a500['delta_dino_nn_mean']:+.6f}) | ≤ {dino_b['step_500_promote_max_delta_dino_nn']:+.6f} and ≤ ΔCSD_B(500) | ({dino_b['step_500_promote_max_delta_dino_nn']:+.6f}, {dino_b['step_500_kill_above_delta_dino_nn']:+.6f}] | > {dino_b['step_500_kill_above_delta_dino_nn']:+.6f} or > ΔCSD_B(500) |
| Seed-matched DreamSim(B, A) at step 500 | ≤ {ds_b['promote_max']:.3f} | ({ds_b['promote_max']:.3f}, {ds_b['kill_above']:.3f}] | > {ds_b['kill_above']:.3f} with lower CSD |

{CORRIDORS_JSON_BEGIN}
{json_block}
{CORRIDORS_JSON_END}
"""
    body_sha = _compute_corridors_body_sha256(template)
    final_text = template.replace(CORRIDORS_SHA_PLACEHOLDER, body_sha, 1)
    cpath.write_text(final_text, encoding="utf-8", newline="\n")
    file_sha = hashlib.sha256(cpath.read_bytes()).hexdigest()
    return {
        "path": str(cpath.resolve()),
        "created_at": ts,
        "body_sha256": body_sha,
        "file_sha256": file_sha,
        "payload": payload,
    }


def read_and_verify_corridors(corridors_path: str | Path) -> dict[str, Any]:
    """Read `corridors.md` and refuse with `CORRIDORS_TAMPERED` if modified after creation."""
    cpath = Path(corridors_path)
    if not cpath.is_file():
        raise CheckpointEvalRefusal(
            "CORRIDORS_MISSING",
            f"corridors file not found at {cpath}; generate it from run A before scoring run B",
        )
    raw_bytes = cpath.read_bytes()
    try:
        text = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise CheckpointEvalRefusal("CORRIDORS_TAMPERED", f"corridors.md is not valid UTF-8: {exc}") from exc

    m_sha = re.search(r"^- \*\*body_sha256:\*\* `([0-9a-f]{64})`$", text, flags=re.MULTILINE)
    m_ts = re.search(r"^- \*\*created_at:\*\* `([^`]+)`$", text, flags=re.MULTILINE)
    if not m_sha or not m_ts:
        raise CheckpointEvalRefusal(
            "CORRIDORS_TAMPERED",
            f"corridors.md at {cpath} is missing required created_at or body_sha256 header",
        )
    recorded_body_sha = m_sha.group(1)
    created_at = m_ts.group(1)
    reconstructed = text[: m_sha.start(1)] + CORRIDORS_SHA_PLACEHOLDER + text[m_sha.end(1) :]
    actual_body_sha = _compute_corridors_body_sha256(reconstructed)
    if actual_body_sha != recorded_body_sha:
        raise CheckpointEvalRefusal(
            "CORRIDORS_TAMPERED",
            f"corridors.md was modified after creation (recorded body_sha256={recorded_body_sha}, "
            f"computed={actual_body_sha})",
        )

    # Also extract and verify the embedded JSON block
    if CORRIDORS_JSON_BEGIN not in text or CORRIDORS_JSON_END not in text:
        raise CheckpointEvalRefusal("CORRIDORS_TAMPERED", "corridors.md is missing embedded JSON specification")
    json_part = text.split(CORRIDORS_JSON_BEGIN, 1)[1].split(CORRIDORS_JSON_END, 1)[0].strip()
    try:
        payload = json.loads(json_part)
    except Exception as exc:
        raise CheckpointEvalRefusal("CORRIDORS_TAMPERED", f"corridors.md JSON block is corrupted: {exc}") from exc

    if payload.get("created_at") != created_at:
        raise CheckpointEvalRefusal(
            "CORRIDORS_TAMPERED",
            f"corridors.md created_at mismatch between header ({created_at}) and payload ({payload.get('created_at')})",
        )

    file_sha = hashlib.sha256(raw_bytes).hexdigest()
    return {
        "path": str(cpath.resolve()),
        "created_at": created_at,
        "body_sha256": recorded_body_sha,
        "file_sha256": file_sha,
        "payload": payload,
    }


def score_run_b_against_corridors(
    corridors_payload: dict[str, Any],
    run_b_summary: dict[str, Any],
    b_vs_a_summary: dict[str, Any],
) -> dict[str, Any]:
    """Classify candidate run B into promote / borderline / kill against the locked corridors."""
    bands = corridors_payload["bands"]
    vel_band = bands["velocity_ratio_rho"]
    csd_band = bands["b_minus_a_csd"]
    clip_band = bands["delta_clip_t_guard"]
    dino_band = bands["delta_dino_nn_guard"]
    ds_band = bands["dreamsim_b_vs_a"]

    rho = b_vs_a_summary.get("velocity_ratio_rho_500")
    pooled_csd_diff = b_vs_a_summary.get("pooled_250_500", {}).get("csd_topk", {}).get("mean")
    b_steps = run_b_summary["steps"]
    b500 = b_steps.get("500") or b_steps.get(500) or next(iter(b_steps.values()))
    b500_dclip = float(b500["delta_clip_t"]["mean"])
    b500_ddino = float(b500["delta_dino_nn"]["mean"])
    b500_dcsd = float(b500["delta_csd"]["mean"])
    ds_500 = (
        b_vs_a_summary.get("by_step", {}).get("500", {}).get("dreamsim_b_vs_a_mean")
        or b_vs_a_summary.get("by_step", {}).get(500, {}).get("dreamsim_b_vs_a_mean")
        or 0.0
    )

    decisions: dict[str, str] = {}
    if rho is not None:
        if rho >= vel_band["promote_min"]:
            decisions["velocity_ratio_rho"] = "promote"
        elif rho < vel_band["kill_below"]:
            decisions["velocity_ratio_rho"] = "kill"
        else:
            decisions["velocity_ratio_rho"] = "borderline"

    if pooled_csd_diff is not None:
        if pooled_csd_diff >= csd_band["promote_min"]:
            decisions["pooled_b_minus_a_csd"] = "promote"
        elif pooled_csd_diff < csd_band["kill_below"]:
            decisions["pooled_b_minus_a_csd"] = "kill"
        else:
            decisions["pooled_b_minus_a_csd"] = "borderline"

    if b500_dclip >= clip_band["step_500_promote_min_delta_clip_t"]:
        decisions["delta_clip_t_500"] = "promote"
    elif b500_dclip < clip_band["step_500_kill_below_delta_clip_t"]:
        decisions["delta_clip_t_500"] = "kill"
    else:
        decisions["delta_clip_t_500"] = "borderline"

    if b500_ddino <= dino_band["step_500_promote_max_delta_dino_nn"] and b500_ddino <= b500_dcsd:
        decisions["delta_dino_nn_500"] = "promote"
    elif b500_ddino > dino_band["step_500_kill_above_delta_dino_nn"] or b500_ddino > b500_dcsd:
        decisions["delta_dino_nn_500"] = "kill"
    else:
        decisions["delta_dino_nn_500"] = "borderline"

    if ds_500 <= ds_band["promote_max"]:
        decisions["dreamsim_500"] = "promote"
    elif ds_500 > ds_band["kill_above"] and (pooled_csd_diff is not None and pooled_csd_diff < 0.0):
        decisions["dreamsim_500"] = "kill"
    else:
        decisions["dreamsim_500"] = "borderline"

    if "kill" in decisions.values():
        overall = "kill"
    elif all(v == "promote" for v in decisions.values()):
        overall = "promote"
    else:
        overall = "borderline"

    return {
        "overall": overall,
        "by_metric": decisions,
    }


# ---------------------------------------------------------------------------
# Full run evaluation
# ---------------------------------------------------------------------------


def _evaluate_single_run(
    run_label: str,
    paired_samples: dict[int, dict[int, Path]],
    prompts_cfg: dict[str, Any],
    training_cache: dict[str, Any],
    embedder: Any,
    topk: int = 5,
) -> dict[str, Any]:
    """Compute per-image and per-checkpoint metrics for a single run."""
    csd_train = training_cache["csd_embeddings"]
    dino_train = training_cache["dino_embeddings"]
    train_names = training_cache["filenames"]
    k_eff = min(topk, len(csd_train))

    content_prompts = prompts_cfg["content_prompts"]
    ood_indices = set(prompts_cfg["ood_prompt_indices"])
    num_prompts = len(content_prompts)
    text_embeds = embedder.embed_clip_texts(content_prompts)

    # Embed step 0 first so paired differences and DreamSim-to-step-0 have their baseline
    steps_sorted = sorted(paired_samples.keys())
    if 0 not in steps_sorted:
        raise CheckpointEvalRefusal("MISSING_STEP_ZERO", f"run {run_label} does not contain step 0 samples")

    per_step_results: dict[str, Any] = OrderedDict()
    step0_metrics_by_prompt: dict[int, dict[str, Any]] = {}
    dreamsim_embeds_by_step: dict[int, list[list[float]]] = {}

    for step in steps_sorted:
        step_t0 = time.perf_counter()
        prompt_map = paired_samples[step]
        ordered_paths = [prompt_map[i] for i in range(num_prompts)]

        csd_vecs = embedder.embed_csd_images(ordered_paths)
        clip_vecs = embedder.embed_clip_images(ordered_paths)
        dino_vecs = embedder.embed_dino_images(ordered_paths)
        ds_vecs = embedder.embed_dreamsim_images(ordered_paths)
        dreamsim_embeds_by_step[step] = ds_vecs

        step0_ds_vecs = dreamsim_embeds_by_step[0]
        per_image_list: list[dict[str, Any]] = []

        for pidx in range(num_prompts):
            # 1. CSD top-k mean cosine to training set
            csd_sims = sorted((_cosine(csd_vecs[pidx], tv) for tv in csd_train), reverse=True)
            csd_topk_val = _mean(csd_sims[:k_eff])

            # 2. Content-only CLIP-T cosine
            clip_t_val = _cosine(clip_vecs[pidx], text_embeds[pidx])

            # 3. DINOv2 nearest-neighbour cosine to training set
            dino_sims = [(_cosine(dino_vecs[pidx], tv), tname) for tv, tname in zip(dino_train, train_names)]
            best_dino_sim, best_dino_name = max(dino_sims, key=lambda item: item[0])

            # 4. DreamSim distance against step 0 of the same run and prompt index
            ds_to_step0 = 0.0 if step == 0 else max(0.0, 1.0 - _cosine(ds_vecs[pidx], step0_ds_vecs[pidx]))

            if step == 0:
                step0_metrics_by_prompt[pidx] = {
                    "csd_topk": csd_topk_val,
                    "clip_t": clip_t_val,
                    "dino_nn": best_dino_sim,
                }

            base = step0_metrics_by_prompt[pidx]
            delta_csd = csd_topk_val - base["csd_topk"]
            delta_clip_t = clip_t_val - base["clip_t"]
            delta_dino_nn = best_dino_sim - base["dino_nn"]

            per_image_list.append(
                {
                    "prompt_index": pidx,
                    "seed": int(prompts_cfg["seed"]) + (pidx if prompts_cfg["walk_seed"] else 0),
                    "is_ood_prompt": pidx in ood_indices,
                    "filename": ordered_paths[pidx].name,
                    "csd_topk": round(csd_topk_val, 6),
                    "clip_t": round(clip_t_val, 6),
                    "dino_nn": round(best_dino_sim, 6),
                    "dino_nn_match": best_dino_name,
                    "dreamsim_to_step0": round(ds_to_step0, 6),
                    "delta_csd": round(delta_csd, 6),
                    "delta_clip_t": round(delta_clip_t, 6),
                    "delta_dino_nn": round(delta_dino_nn, 6),
                }
            )

        wall_s = round(time.perf_counter() - step_t0, 4)

        def _agg(field: str, subset: Sequence[dict[str, Any]] = per_image_list) -> dict[str, float]:
            vals = [float(item[field]) for item in subset]
            return {
                "mean": round(_mean(vals), 6),
                "sd": round(_sample_sd(vals), 6),
                "values": [round(v, 6) for v in vals],
            }

        ood_subset = [item for item in per_image_list if item["is_ood_prompt"]]
        per_step_results[str(step)] = {
            "step": step,
            "n_images": len(per_image_list),
            "wall_time_s": wall_s,
            "csd_topk": _agg("csd_topk"),
            "clip_t": _agg("clip_t"),
            "dino_nn": _agg("dino_nn"),
            "dreamsim_to_step0": _agg("dreamsim_to_step0"),
            "delta_csd": _agg("delta_csd"),
            "delta_clip_t": _agg("delta_clip_t"),
            "delta_dino_nn": _agg("delta_dino_nn"),
            "ood_dino_nn": _agg("dino_nn", ood_subset) if ood_subset else None,
            "ood_delta_dino_nn": _agg("delta_dino_nn", ood_subset) if ood_subset else None,
            "per_image": per_image_list,
        }

    # Estimate per-step SD of paired differences from run's step-to-step ΔCSD across prompts
    nonzero_steps = [s for s in steps_sorted if s != 0]
    transition_sds: dict[str, float] = OrderedDict()
    all_step_to_step_diffs: list[float] = []
    for idx in range(1, len(nonzero_steps)):
        s_prev = str(nonzero_steps[idx - 1])
        s_curr = str(nonzero_steps[idx])
        prev_vals = per_step_results[s_prev]["delta_csd"]["values"]
        curr_vals = per_step_results[s_curr]["delta_csd"]["values"]
        step_diffs = [c - p for c, p in zip(curr_vals, prev_vals)]
        transition_sds[f"{s_prev}_to_{s_curr}"] = round(_sample_sd(step_diffs), 6)
        all_step_to_step_diffs.extend(step_diffs)

    if transition_sds:
        mean_transition_sd = _mean(list(transition_sds.values()))
        est_name = "mean_sd_of_step_to_step_delta_csd_across_prompts_in_run_A"
    elif nonzero_steps:
        first_nz = str(nonzero_steps[0])
        mean_transition_sd = float(per_step_results[first_nz]["delta_csd"]["sd"])
        est_name = "within_step_delta_csd_sd_across_prompts_in_run_A"
    else:
        mean_transition_sd = 0.0
        est_name = "zero_only_step"

    return {
        "run_label": run_label,
        "num_prompts": num_prompts,
        "steps_evaluated": steps_sorted,
        "total_wall_time_s": round(sum(v["wall_time_s"] for v in per_step_results.values()), 4),
        "mean_wall_time_per_checkpoint_s": round(
            _mean([v["wall_time_s"] for v in per_step_results.values()]), 4
        ),
        "paired_diff_sd_estimate": {
            "value": round(mean_transition_sd, 6),
            "estimator": est_name,
            "description": (
                "First estimate of per-step paired-difference SD from run A alone: "
                "mean across consecutive non-zero checkpoint transitions of the across-prompt sample SD "
                "of (ΔCSD(step_k) - ΔCSD(step_{k-1})). Replaces the Deep Research report's assumed 0.035 "
                "until a matched run B is available."
            ),
            "per_transition_sds": transition_sds,
        },
        "steps": per_step_results,
        "_dreamsim_embeds_by_step": dreamsim_embeds_by_step,
    }


def _compare_run_b_vs_run_a(
    run_a_res: dict[str, Any],
    run_b_res: dict[str, Any],
) -> dict[str, Any]:
    """Compute paired B - A differences per step, pooled over steps 250 and 500 (n=12), and velocity ratio ρ."""
    common_steps = sorted(set(run_a_res["steps_evaluated"]) & set(run_b_res["steps_evaluated"]))
    by_step_cmp: dict[str, Any] = OrderedDict()

    ds_a = run_a_res["_dreamsim_embeds_by_step"]
    ds_b = run_b_res["_dreamsim_embeds_by_step"]

    for step in common_steps:
        sk = str(step)
        a_step = run_a_res["steps"][sk]
        b_step = run_b_res["steps"][sk]
        ds_dists = [
            max(0.0, 1.0 - _cosine(vb, va))
            for vb, va in zip(ds_b[step], ds_a[step])
        ]
        by_step_cmp[sk] = {
            "step": step,
            "csd_topk_b_minus_a": compute_paired_stats(
                b_step["csd_topk"]["values"], a_step["csd_topk"]["values"]
            ),
            "delta_csd_b_minus_a": compute_paired_stats(
                b_step["delta_csd"]["values"], a_step["delta_csd"]["values"]
            ),
            "clip_t_b_minus_a": compute_paired_stats(
                b_step["clip_t"]["values"], a_step["clip_t"]["values"]
            ),
            "delta_clip_t_b_minus_a": compute_paired_stats(
                b_step["delta_clip_t"]["values"], a_step["delta_clip_t"]["values"]
            ),
            "dino_nn_b_minus_a": compute_paired_stats(
                b_step["dino_nn"]["values"], a_step["dino_nn"]["values"]
            ),
            "delta_dino_nn_b_minus_a": compute_paired_stats(
                b_step["delta_dino_nn"]["values"], a_step["delta_dino_nn"]["values"]
            ),
            "dreamsim_b_vs_a_mean": round(_mean(ds_dists), 6),
            "dreamsim_b_vs_a_sd": round(_sample_sd(ds_dists), 6),
            "dreamsim_b_vs_a_values": [round(x, 6) for x in ds_dists],
        }

    # Pooled over steps 250 and 500 (n = 12 for 6 prompts)
    pool_steps = [s for s in (250, 500) if str(s) in by_step_cmp]
    if not pool_steps:
        pool_steps = [s for s in common_steps if s != 0][:2]

    pooled_csd_b: list[float] = []
    pooled_csd_a: list[float] = []
    pooled_dcsd_b: list[float] = []
    pooled_dcsd_a: list[float] = []
    pooled_dclip_b: list[float] = []
    pooled_dclip_a: list[float] = []
    pooled_ddino_b: list[float] = []
    pooled_ddino_a: list[float] = []

    for s in pool_steps:
        sk = str(s)
        pooled_csd_b.extend(run_b_res["steps"][sk]["csd_topk"]["values"])
        pooled_csd_a.extend(run_a_res["steps"][sk]["csd_topk"]["values"])
        pooled_dcsd_b.extend(run_b_res["steps"][sk]["delta_csd"]["values"])
        pooled_dcsd_a.extend(run_a_res["steps"][sk]["delta_csd"]["values"])
        pooled_dclip_b.extend(run_b_res["steps"][sk]["delta_clip_t"]["values"])
        pooled_dclip_a.extend(run_a_res["steps"][sk]["delta_clip_t"]["values"])
        pooled_ddino_b.extend(run_b_res["steps"][sk]["delta_dino_nn"]["values"])
        pooled_ddino_a.extend(run_a_res["steps"][sk]["delta_dino_nn"]["values"])

    pooled_csd_stats = compute_paired_stats(pooled_csd_b, pooled_csd_a)
    pooled_dcsd_stats = compute_paired_stats(pooled_dcsd_b, pooled_dcsd_a)
    pooled_dclip_stats = compute_paired_stats(pooled_dclip_b, pooled_dclip_a)
    pooled_ddino_stats = compute_paired_stats(pooled_ddino_b, pooled_ddino_a)

    # Velocity ratio ρ = ΔCSD_B(500) / ΔCSD_A(500)
    rho_500: float | None = None
    if "500" in run_a_res["steps"] and "500" in run_b_res["steps"]:
        denom = float(run_a_res["steps"]["500"]["delta_csd"]["mean"])
        num = float(run_b_res["steps"]["500"]["delta_csd"]["mean"])
        rho_500 = round(num / denom, 6) if abs(denom) > 1e-12 else None

    rho_250: float | None = None
    if "250" in run_a_res["steps"] and "250" in run_b_res["steps"]:
        denom250 = float(run_a_res["steps"]["250"]["delta_csd"]["mean"])
        num250 = float(run_b_res["steps"]["250"]["delta_csd"]["mean"])
        rho_250 = round(num250 / denom250, 6) if abs(denom250) > 1e-12 else None

    return {
        "pooled_steps": pool_steps,
        "pooled_n": len(pooled_csd_b),
        "velocity_ratio_rho_500": rho_500,
        "velocity_ratio_rho_250": rho_250,
        "measured_per_step_paired_diff_sd": pooled_csd_stats["sd"],
        "pooled_250_500": {
            "csd_topk": pooled_csd_stats,
            "delta_csd": pooled_dcsd_stats,
            "delta_clip_t": pooled_dclip_stats,
            "delta_dino_nn": pooled_ddino_stats,
        },
        "by_step": by_step_cmp,
    }


def evaluate_runs(
    training_dir: str | Path,
    run_dirs: dict[str, str | Path],
    prompts_path: str | Path,
    out_dir: str | Path,
    steps: Sequence[int] | None = None,
    device: str = "cpu",
    prompts_b_path: str | Path | None = None,
    checkpoint_paths: Sequence[str | Path] | None = None,
    corridors_path: str | Path | None = None,
    embedder: Any | None = None,
    topk: int = 5,
) -> dict[str, Any]:
    """Run paired checkpoint evaluation for run A (and optional run B) and write outputs to `out_dir`."""
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    if "A" not in run_dirs:
        raise CheckpointEvalRefusal("MISSING_RUN_A", "--run A=<samples_dir> is required")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    corridors_file = Path(corridors_path) if corridors_path else (out_path / "corridors.md")

    # If scoring run B, verify existing corridors.md BEFORE computing or writing anything
    locked_corridors: dict[str, Any] | None = None
    if "B" in run_dirs:
        locked_corridors = read_and_verify_corridors(corridors_file)

    cfg_a = load_prompts_config(prompts_path)
    if "B" in run_dirs:
        if prompts_b_path is not None:
            cfg_b = load_prompts_config(prompts_b_path)
        else:
            b_dir = Path(run_dirs["B"])
            candidate_cfgs = [
                b_dir / "config.yaml",
                b_dir / "config.json",
                b_dir.parent / "config.yaml",
                b_dir.parent / "config.json",
            ]
            found_b = next((c for c in candidate_cfgs if c.is_file()), None)
            cfg_b = load_prompts_config(found_b) if found_b else cfg_a
        verify_configs_match(cfg_a, cfg_b)

    paired_a = pair_run_samples(run_dirs["A"], len(cfg_a["prompts"]), steps, run_label="A")
    paired_b: dict[int, dict[int, Path]] | None = None
    if "B" in run_dirs:
        target_steps = steps if steps is not None else list(paired_a.keys())
        paired_b = pair_run_samples(run_dirs["B"], len(cfg_a["prompts"]), target_steps, run_label="B")

    active_embedder = embedder if embedder is not None else RealEmbedder(device=device)
    training_cache = get_or_create_training_embeddings(training_dir, out_path, active_embedder)

    run_a_res = _evaluate_single_run("A", paired_a, cfg_a, training_cache, active_embedder, topk=topk)
    run_b_res: dict[str, Any] | None = None
    b_vs_a_res: dict[str, Any] | None = None
    corridors_verdict: dict[str, Any] | None = None

    if paired_b is not None:
        run_b_res = _evaluate_single_run("B", paired_b, cfg_a, training_cache, active_embedder, topk=topk)
        b_vs_a_res = _compare_run_b_vs_run_a(run_a_res, run_b_res)
        assert locked_corridors is not None
        corridors_info = locked_corridors
        corridors_verdict = score_run_b_against_corridors(
            locked_corridors["payload"], run_b_res, b_vs_a_res
        )
    else:
        corridors_info = write_corridors_file(corridors_file, run_a_res)

    # Clean internal embedding caches before serializing summary.json
    run_a_res.pop("_dreamsim_embeds_by_step", None)
    if run_b_res is not None:
        run_b_res.pop("_dreamsim_embeds_by_step", None)

    weight_space: dict[str, Any] | None = None
    if checkpoint_paths:
        weight_space = read_safetensors_weight_space(checkpoint_paths)

    summary = OrderedDict(
        [
            ("schema_version", "1.0"),
            ("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("device", getattr(active_embedder, "device_description", device)),
            ("cuda_visible_devices", os.environ.get("CUDA_VISIBLE_DEVICES", "")),
            ("models_and_licences", getattr(active_embedder, "models_used", MODEL_LICENCE_TABLE)),
            (
                "config",
                {
                    "path": cfg_a["path"],
                    "name": cfg_a["name"],
                    "seed": cfg_a["seed"],
                    "walk_seed": cfg_a["walk_seed"],
                    "num_prompts": len(cfg_a["prompts"]),
                    "trigger_words": cfg_a["trigger_words"],
                    "prompts": cfg_a["prompts"],
                    "content_prompts": cfg_a["content_prompts"],
                    "ood_prompt_indices": cfg_a["ood_prompt_indices"],
                },
            ),
            (
                "training_set",
                {
                    "dir": str(Path(training_dir).resolve()),
                    "num_images": training_cache["num_images"],
                    "fingerprint_sha256": training_cache["fingerprint"],
                    "embed_wall_time_s": training_cache["embed_wall_time_s"],
                    "cache_hit": training_cache["cache_hit"],
                },
            ),
            (
                "corridors",
                {
                    "path": corridors_info["path"],
                    "created_at": corridors_info["created_at"],
                    "body_sha256": corridors_info["body_sha256"],
                    "file_sha256": corridors_info["file_sha256"],
                },
            ),
            ("runs", OrderedDict([("A", run_a_res)] + ([("B", run_b_res)] if run_b_res else []))),
            ("b_vs_a", b_vs_a_res),
            ("corridors_verdict", corridors_verdict),
            ("weight_space", weight_space),
        ]
    )

    summary_path = out_path / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_run_args(raw_runs: Sequence[str]) -> tuple[dict[str, str], dict[str, str]]:
    run_dirs: dict[str, str] = OrderedDict()
    run_cfgs: dict[str, str] = OrderedDict()
    for item in raw_runs:
        if "=" not in item:
            raise CheckpointEvalRefusal("INVALID_ARGS", f"--run expects NAME=DIR (got {item!r})")
        name, val = item.split("=", 1)
        name = name.strip()
        val = val.strip()
        if not name or not val:
            raise CheckpointEvalRefusal("INVALID_ARGS", f"--run expects non-empty NAME=DIR (got {item!r})")
        run_dirs[name] = val
    return run_dirs, run_cfgs


def _parse_steps_arg(raw_steps: str | None) -> list[int] | None:
    if not raw_steps:
        return None
    out: list[int] = []
    for part in raw_steps.split(","):
        part = part.strip()
        if not part:
            continue
        if not re.match(r"^\d+$", part):
            raise CheckpointEvalRefusal("INVALID_ARGS", f"--steps expects comma-separated integers (got {raw_steps!r})")
        out.append(int(part))
    return out if out else None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="checkpoint-eval",
        description="Paired, seed-matched early-checkpoint evaluation for style LoRAs (CPU / Intel OpenVINO only).",
    )
    parser.add_argument("--training-dir", required=True, help="Directory of training set images.")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        metavar="NAME=DIR",
        help="Run sample directory mapping: --run A=<samples_dir> [--run B=<samples_dir>].",
    )
    parser.add_argument(
        "--steps",
        default=None,
        help="Comma-separated list of checkpoint steps to evaluate (e.g. 0,250,500,...).",
    )
    parser.add_argument(
        "--prompts",
        required=True,
        help="Path to trainer config.yaml or JSON containing sample prompts and seed.",
    )
    parser.add_argument(
        "--prompts-b",
        default=None,
        help="Optional separate config.yaml or JSON for run B (to verify seed/prompt parity).",
    )
    parser.add_argument("--out", required=True, help="Output directory for summary.json, corridors.md, and cache.")
    parser.add_argument(
        "--device",
        choices=["cpu", "openvino"],
        default="cpu",
        help="Compute device: cpu or Intel openvino (NVIDIA GPUs are strictly disabled).",
    )
    parser.add_argument(
        "--checkpoint",
        action="append",
        default=[],
        help="Optional LoRA .safetensors checkpoint path(s) for CPU weight-space stable-rank analysis.",
    )
    parser.add_argument(
        "--corridors",
        default=None,
        help="Optional explicit path to corridors.md (defaults to <out>/corridors.md).",
    )
    parser.add_argument(
        "--topk",
        type=int,
        default=5,
        help="Top-k nearest training images for CSD style cosine (default: 5).",
    )
    parser.add_argument(
        "--fake-embedder",
        action="store_true",
        help="Use deterministic synthetic fake embedder (for unit/CLI tests on synthetic fixtures).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        run_dirs, _ = _parse_run_args(args.run)
        steps = _parse_steps_arg(args.steps)
        embedder = FakeEmbedder() if args.fake_embedder else None
        evaluate_runs(
            training_dir=args.training_dir,
            run_dirs=run_dirs,
            prompts_path=args.prompts,
            out_dir=args.out,
            steps=steps,
            device=args.device,
            prompts_b_path=args.prompts_b,
            checkpoint_paths=args.checkpoint if args.checkpoint else None,
            corridors_path=args.corridors,
            embedder=embedder,
            topk=args.topk,
        )
        return 0
    except CheckpointEvalRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
