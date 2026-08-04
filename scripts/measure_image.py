#!/usr/bin/env python3
"""measure_image — numeric palette + texture measurement for candidate images.

MEASUREMENT, NOT VERDICT. Every number this script produces is a signal to
attach to a record — nothing here classifies, thresholds, or emits a
pass/fail/approved/rejected verdict. That judgment stays with a human (or a
future LLM judge). This repo deleted three scripts in Stage A for fabricating
judgments from keyword matching instead of looking at the pixels; this script
exists to give the human (or a future judge) real pixels to look at, not to
replace them.

PORTED FROM (read these for the full rationale before touching the math):
  projects/salt-road/inputs/prompts/measure-palette.py
  projects/salt-road/inputs/prompts/measure-texture.py
These are the Director-validated, production-used salt-road audit
instruments. This script ports their MEASUREMENT CORE (the per-image pixel
math) — not the one-off audit drivers those files also contain (sweep-
directory globbing, filename-regex config classification, cross-run
comparison tables). sdlab measure operates per-record; the salt-road scripts
audit a specific sweep. Both are left untouched by this port and remain
available for that project-specific work.

DELIBERATELY NOT PORTED: the DISTS/StyleLoss perceptual cross-check in
projects/salt-road/inputs/prompts/crosscheck-dists.py. That instrument needs
torch+piq — a GPU-class dependency this CLI does not take on. Briefly, for
context (see that file for the full citations): it uses DISTS (Ding, Ma, Wang
& Simoncelli 2020, arXiv:2004.07728, TPAMI — separates texture similarity
from structure similarity, tolerant of texture resampling) and StyleLoss
(Gatys et al. 2015, arXiv:1505.07376 — Gram-matrix distance over VGG
features, legitimate for comparing scenes with different content), and it
explicitly rejects FID (poor sample complexity at small n — Jayasumana 2024,
arXiv:2401.09603; Chong & Forsyth 2020, arXiv:1911.07023) and DreamSim
(engineered to look past low-level colour/texture — Fu 2023, arXiv:2306.09344
— which would be blind to the thing under test here). A future `--perceptual`
mode should start from that file, not from scratch.

Deliberate changes from the ported originals (see also the sdlab feature
report for the full list):
  - The two hardcoded salt-road ochre anchors (measure-palette.py's
    `#c9a877` / `#a86b4c`, with hand-picked disjoint hue bands 8-42/42-70)
    become an N-anchor system driven by the caller's `anchors` list (project
    canon has no numeric palette data to read this from automatically — see
    the sdlab feature report). Each gated pixel is assigned to whichever
    anchor's hue is circularly nearest, provided that distance is within
    `hue_tolerance_deg`; otherwise it is "off_anchor". This is a
    generalization, not a re-derivation: for salt-road's own two anchors
    (hue ~19deg and ~33deg) at the default 20deg tolerance it reproduces
    materially the same combined catchment the original hand-tuned 8-42deg
    band covered, while working for any project's own anchor set.
  - measure-texture.py's `yellow_pct`/`ochre_pct`/`green_pct` (a second,
    duplicate hue-binning pass baked into the texture measurer so "every
    image measured for texture is measured for colour in the same pass") is
    replaced by calling the SAME hue/anchor code the palette measurer uses.
    Same discipline (one image load, texture + colour measured together),
    without a second hardcoded hue-band implementation living in two files.
  - `facade_rep` (row-of-identical-facades autocorrelation) is intentionally
    NOT ported. It is a composition/repetition detector conditioned on
    subject ("only meaningful on wide exteriors... meaningless for an
    interior or a close stone study" — measure-texture.py), not a palette or
    texture measure in the sense this CLI is scoped to (palette + texture,
    per the feature's approved scope). Left out; see the feature report.
  - The vectorised numpy hue/sat/val computation is adopted from
    measure-texture.py's `hue_bands()` (itself a numerically-verified,
    vectorised reproduction of measure-palette.py's slower colorsys
    per-pixel loop — see that function's docstring) rather than
    reimplementing the slow loop a second time. One hue/sat/val
    implementation, used by both this script's palette and texture passes.

    python measure_image.py --request <request.json> --out <result.json>

Request JSON shape (written by lib/measure.js):
  {
    "images": [{"id": "...", "path": "..."}, ...],
    "anchors": [{"name": "ochre-warm", "hex": "#c9a877"}, ...],   # optional, [] or omitted is fine
    "hue_tolerance_deg": 20,    # optional
    "sat_min": 0.22,            # optional — ported default, see measure_palette()
    "val_min": 0.18             # optional — ported default, see measure_palette()
  }

Result JSON shape (written to --out):
  {
    "schema_version": "1.0.0", "tool": "measure_image.py", "generated_at": "...",
    "results": [{"id", "path", "status": "ok", "image": {...}, "palette": {...}, "texture": {...}}],
    "errors": [{"id", "path", "error"}],
    "ok_count": N, "error_count": N
  }
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel

MEASURE_SCHEMA_VERSION = "1.0.0"

# Ported verbatim from measure-palette.py's saturated-pixel gate: "ignore
# greys/darks — stone, tar, shadow". Comparability with that instrument's
# published numbers depends on these two values, so they are the default
# rather than something re-derived here.
DEFAULT_SAT_MIN = 0.22
DEFAULT_VAL_MIN = 0.18

# Not from either original (neither had a per-anchor tolerance concept — see
# module docstring). A deliberate new default: half-width, in degrees, of the
# circular-hue catchment around each anchor's own hue. Project owners tune
# this via the anchors JSON's "hue_tolerance_deg" field.
DEFAULT_HUE_TOLERANCE_DEG = 20.0

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _json_safe(obj):
    """Replace non-finite floats with None, recursively.

    Python's json.dumps emits bare `NaN` / `Infinity` for these — a
    non-standard extension that RFC 8259 does not allow and that JavaScript's
    JSON.parse rejects outright, taking the WHOLE result down with it, not
    just the offending field. The Node caller (lib/measure.js) then reports
    `Unexpected token 'N'` and the operator learns nothing about which image
    or which measure produced it.

    Non-finite values are legitimate here rather than a bug to prevent: a
    perfectly flat image has zero luminance variance, so a measure that
    normalizes by it is genuinely undefined. Found in Phase 9 by measuring
    three solid-colour images, which every unit test had missed because they
    all paired a flat image with a textured one.

    `null` is the honest encoding of "this measure is undefined for this
    image" — the same choice palette conformance already makes when no
    anchors are supplied. It is emphatically not 0, which would read as a
    real measurement of a real property.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _atomic_write_json(path: Path, obj) -> None:
    """Temp file in the same dir + os.replace — the Python-side mirror of
    lib/runtime-runs.js's atomicWriteJson (temp+rename): a crash mid-write
    can never leave a half-written result.json in place of a good one.
    os.replace (not os.rename) because it atomically overwrites the
    destination on Windows too, matching Node's fs.rename semantics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}"
    try:
        # allow_nan=False makes a leaked non-finite value a loud Python-side
        # ValueError here rather than a bare `NaN` token that only explodes
        # later in the Node caller's JSON.parse, where the message names no
        # image and no measure. _json_safe should have caught them all; this
        # is the assertion that it did.
        tmp.write_text(
            json.dumps(_json_safe(obj), indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# ─── Anchor validation ─────────────────────────────────────────────────────

def _validate_anchors(anchors) -> None:
    if anchors is None:
        return
    if not isinstance(anchors, list):
        raise ValueError("anchors must be a list of {name, hex} objects")
    for a in anchors:
        if not isinstance(a, dict) or "name" not in a or "hex" not in a:
            raise ValueError(f"invalid anchor entry (needs name + hex): {a!r}")
        if not _HEX_RE.match(str(a["hex"])):
            raise ValueError(
                f"anchor {a.get('name')!r} has invalid hex color {a.get('hex')!r} (expected #rrggbb)"
            )


# ─── Shared hue/sat/val (ported from measure-texture.py's hue_bands) ──────

def _hsv_arrays(im: Image.Image, size=(240, 137)):
    """Vectorised hue(deg)/saturation/value over a resized copy.

    Adopted from measure-texture.py's hue_bands() — itself a numerically
    verified, vectorised reproduction of measure-palette.py's per-pixel
    colorsys loop (see that function's docstring: "reproducing
    measure-palette.py EXACTLY -- same 240x137 downscale, same s>=0.22 /
    v>=0.18 gate ... Vectorised, but deliberately not 'improved'"). Returns
    raw (hue_deg, sat, val) arrays instead of pre-binned percentages so the
    caller can bucket by an arbitrary, project-supplied anchor list instead
    of the two hardcoded salt-road bands.

    The downscale is the same deliberate choice as the original: palette is
    a low-frequency, gross-color-mass question, so shrinking first is fine
    (contrast measure_texture below, which explicitly does NOT resize).
    """
    a = np.asarray(im.convert("RGB").resize(size), dtype=np.float64) / 255.0
    mx, mn = a.max(2), a.min(2)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-12), 0.0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    h = np.zeros_like(mx)
    nz = d > 1e-12
    with np.errstate(invalid="ignore"):
        h = np.where(nz & (mx == r), ((g - b) / np.where(nz, d, 1)) % 6, h)
        h = np.where(nz & (mx == g), (b - r) / np.where(nz, d, 1) + 2, h)
        h = np.where(nz & (mx == b), (r - g) / np.where(nz, d, 1) + 4, h)
    hd = (h * 60.0) % 360.0
    return hd, s, mx  # mx doubles as V in HSV


def _anchor_hue_deg(hex_color: str) -> float:
    """Ported verbatim from measure-palette.py's anchor_hue()."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360.0


def _circular_hue_distance(a, b):
    d = np.abs(a - b) % 360.0
    return np.minimum(d, 360.0 - d)


# ─── Palette measurement ────────────────────────────────────────────────

def measure_palette(im: Image.Image, anchors, hue_tolerance_deg=DEFAULT_HUE_TOLERANCE_DEG,
                     sat_min=DEFAULT_SAT_MIN, val_min=DEFAULT_VAL_MIN) -> dict:
    """Numeric palette signal. `anchors` is a (possibly empty) list of
    {name, hex}; with no anchors, only the gate stats are returned (still
    useful signal: how much of the frame is "colorful" at all, and its mean
    saturation/value) — this lets sdlab measure run on a project with no
    authored anchor file yet instead of refusing outright.

    Percentages are relative to the GATED pixel count (pixels that passed
    the saturation/value gate), not the whole frame — ported from
    measure-palette.py's `tot = yellow + redochre + other` (a sum of gated
    bins only). A sky or a shadow dominating raw pixel count would otherwise
    dilute the signal this measure exists to read.
    """
    hd, s, v = _hsv_arrays(im)
    keep = (s >= sat_min) & (v >= val_min)
    gated = int(keep.sum())
    frame_total = int(hd.size)

    result = {
        "gated_pct": round(100.0 * gated / frame_total, 2) if frame_total else 0.0,
        "mean_saturation": round(float(s[keep].mean()), 4) if gated else 0.0,
        "mean_value": round(float(v[keep].mean()), 4) if gated else 0.0,
        "hue_tolerance_deg": hue_tolerance_deg,
        "anchors": {},
        "off_anchor_pct": None,
    }
    if not anchors or gated == 0:
        return result

    hd_gated = hd[keep]
    names = [a["name"] for a in anchors]
    anchor_hues = [_anchor_hue_deg(a["hex"]) for a in anchors]

    # Nearest-anchor assignment within tolerance — see module docstring for
    # why this generalizes measure-palette.py's two hand-picked bands.
    dists = np.stack([_circular_hue_distance(hd_gated, hue) for hue in anchor_hues], axis=0)
    nearest_idx = np.argmin(dists, axis=0)
    nearest_dist = np.min(dists, axis=0)
    within = nearest_dist <= hue_tolerance_deg

    for i, name in enumerate(names):
        count = int(((nearest_idx == i) & within).sum())
        result["anchors"][name] = round(100.0 * count / gated, 2)
    result["off_anchor_pct"] = round(100.0 * int((~within).sum()) / gated, 2)
    return result


# ─── Texture measurement (ported from measure-texture.py's measure()) ────

def measure_texture(im: Image.Image) -> dict:
    """Numeric texture/impasto signal, ported from measure-texture.py's
    measure(). Deliberately kept at NATIVE resolution — no resize, no
    re-encode: per that file's docstring, "downscaling is the exact
    operation that destroys the signal we are looking for". See that file
    for the full rationale on why each measure exists (flat_hf is the
    headline: impasto is texture that survives into nominally flat regions,
    which is what separates "the surface is painted" from "the frame has a
    lot of stuff in it").

    Excludes facade_rep and the yellow/ochre/green hue bands — see the
    module docstring's "Deliberate changes" section.
    """
    if im.mode not in ("RGB", "RGBA"):
        raise ValueError(f"unexpected image mode {im.mode!r} (expected RGB or RGBA)")
    if im.width < 8 or im.height < 8:
        # Not present in the original (real 1344x768 salt-road plates never
        # underflowed the percentile windows below) — added defensively so a
        # tiny/degenerate image fails with a clear message instead of a
        # cryptic numpy exception from np.percentile on a near-empty array.
        raise ValueError(f"image too small to measure ({im.width}x{im.height}); minimum 8x8")

    a = np.asarray(im.convert("RGB"), dtype=np.float64)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]

    # --- high-pass residual: everything finer than ~1.5px ---
    hp = lum - gaussian_filter(lum, sigma=1.5)

    # --- large-scale structure gradient: where are the object edges? ---
    struct = gaussian_filter(lum, sigma=6.0)
    gx, gy = sobel(struct, axis=1), sobel(struct, axis=0)
    sgrad = np.hypot(gx, gy)

    # flattest 40% of the frame by large-scale gradient
    flat = sgrad <= np.percentile(sgrad, 40)

    # --- laplacian variance ---
    lap = (-4 * lum
           + np.roll(lum, 1, 0) + np.roll(lum, -1, 0)
           + np.roll(lum, 1, 1) + np.roll(lum, -1, 1))[1:-1, 1:-1]

    # --- edge density on the raw luminance, fixed absolute threshold ---
    ex, ey = sobel(lum, axis=1), sobel(lum, axis=0)
    egrad = np.hypot(ex, ey) / 4.0  # sobel kernel gain

    # --- acutance: how much do the strongest edges survive a sigma-2 blur? ---
    blur = gaussian_filter(lum, 2.0)
    bgrad = np.hypot(sobel(blur, axis=1), sobel(blur, axis=0)) / 4.0
    strong = egrad >= np.percentile(egrad, 98)
    edge_hard = float(egrad[strong].mean() / max(bgrad[strong].mean(), 1e-9)) if strong.any() else 0.0

    # --- directionality of the fine residual inside the flat mask ---
    hx, hy = sobel(hp, axis=1), sobel(hp, axis=0)
    Jxx = gaussian_filter(hx * hx, 4.0)
    Jyy = gaussian_filter(hy * hy, 4.0)
    Jxy = gaussian_filter(hx * hy, 4.0)
    disc = np.sqrt(((Jxx - Jyy) / 2.0) ** 2 + Jxy ** 2)
    tr = (Jxx + Jyy) / 2.0
    coh = 2.0 * disc / np.maximum(tr * 2.0, 1e-9)

    # --- radial power spectrum ---
    win = np.hanning(lum.shape[0])[:, None] * np.hanning(lum.shape[1])[None, :]
    F = np.fft.fftshift(np.abs(np.fft.fft2((lum - lum.mean()) * win)) ** 2)
    cy, cx = (np.array(F.shape) - 1) / 2.0
    yy, xx = np.ogrid[:F.shape[0], :F.shape[1]]
    r = np.hypot((yy - cy) / (F.shape[0] / 2.0), (xx - cx) / (F.shape[1] / 2.0))
    tot = F.sum()

    return {
        "lap_var": round(float(lap.var()), 6),
        "hf_ratio": round(float(hp.std() / max(lum.std(), 1e-9)), 6),
        "flat_hf": round(float(hp[flat].std()), 6),
        "edge_dens": round(float((egrad > 12.0).mean()), 6),
        "band_hi": round(float(F[r > 0.30].sum() / tot), 6),
        "band_mid": round(float(F[(r > 0.10) & (r <= 0.30)].sum() / tot), 6),
        "edge_hard": round(edge_hard, 6),
        "flat_coh": round(float(coh[flat].mean()), 6),
        "lum_std": round(float(lum.std()), 6),
    }


# ─── Per-image measurement + CLI driver ────────────────────────────────

def measure_one(path: str, anchors, hue_tolerance_deg, sat_min, val_min) -> dict:
    """Open the image ONCE and run both passes over it — mirrors
    measure-texture.py's own discipline ("every image measured for texture
    is measured for colour in the same pass"), generalized to palette+texture
    instead of texture+yellow-band."""
    with Image.open(path) as im:
        im.load()
        texture = measure_texture(im)
        palette = measure_palette(im, anchors, hue_tolerance_deg, sat_min, val_min)
        return {
            "image": {"width": im.width, "height": im.height, "mode": im.mode},
            "palette": palette,
            "texture": texture,
        }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--request", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"request file not found: {args.request}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"request file is not valid JSON: {args.request}: {exc}")

    images = request.get("images", [])
    anchors = request.get("anchors") or []
    hue_tolerance_deg = request.get("hue_tolerance_deg", DEFAULT_HUE_TOLERANCE_DEG)
    sat_min = request.get("sat_min", DEFAULT_SAT_MIN)
    val_min = request.get("val_min", DEFAULT_VAL_MIN)

    try:
        _validate_anchors(anchors)
    except ValueError as exc:
        raise SystemExit(f"invalid anchors in request: {exc}")

    results = []
    errors = []
    for item in images:
        iid = item.get("id")
        path = item.get("path")
        try:
            measured = measure_one(path, anchors, hue_tolerance_deg, sat_min, val_min)
            results.append({"id": iid, "path": path, "status": "ok", **measured})
            print(f"  {iid} -> ok", flush=True)
        except Exception as exc:  # noqa: BLE001 — one bad image must not sink the batch
            errors.append({"id": iid, "path": path, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  {iid} -> ERROR: {exc}", flush=True)

    payload = {
        "schema_version": MEASURE_SCHEMA_VERSION,
        "tool": "measure_image.py",
        "generated_at": _utc_now_iso(),
        "results": results,
        "errors": errors,
        "ok_count": len(results),
        "error_count": len(errors),
    }
    _atomic_write_json(args.out, payload)

    summary = f"\n{len(results)}/{len(images)} image(s) measured -> {args.out}"
    if errors:
        summary += f"  ({len(errors)} error(s) - see {args.out} for per-item detail)"
    print(summary)

    # Mirror qwen_generate.py's convention: a run where EVERY item failed
    # exits non-zero (nothing to salvage); a partial failure still exits 0 —
    # per-item errors are visible above and in the written result file, and
    # individual item failure is tolerated everywhere else in this pipeline.
    if images and len(errors) == len(images):
        raise SystemExit(f"all {len(errors)} measurement attempt(s) failed - see {args.out} for per-item errors")


if __name__ == "__main__":
    main()
