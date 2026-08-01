#!/usr/bin/env python3
"""measure-texture — quantify surface texture (impasto / visible brushwork).

Companion to measure-palette.py, same discipline on a new axis. Colour is solved;
the open question is whether the LoRA's outputs genuinely carry less high-frequency
surface energy than the 73 approved plates -- and than the bare base model. A
confident visual read is not evidence; the palette cycle proved that.

Everything is measured at NATIVE resolution on the PNG as written. No resize, no
re-encode: downscaling is the exact operation that destroys the signal we are
looking for, and it is how you end up measuring your own pipeline.

Five measures per image, on luminance:

  lap_var    variance of the Laplacian. Classic sharpness proxy. Contrast-sensitive,
             so it rises with global contrast as well as with brushwork -- reported
             for completeness, not as the headline.
  hf_ratio   std(high-pass) / std(image). Contrast-NORMALISED, so a darker or flatter
             image is not punished. "What share of this image's variation is fine?"
  flat_hf    THE HEADLINE. std of the high-pass residual measured only inside the
             flattest 40% of the frame (lowest large-scale gradient). Impasto is
             texture that survives into nominally flat regions -- a limewashed wall,
             open water, a warehouse door. A cluttered quay scores high on lap_var
             purely by having more stuff in it; it only scores high on flat_hf if the
             paint itself is textured. This is the measure that separates "density is
             stuff" (contract law 7) from "the surface is painted."
  edge_dens  fraction of pixels above a fixed absolute Sobel threshold. Separates
             "many small marks" from "few large smooth shapes."
  band_hi    share of radial power spectrum energy above 0.30 of Nyquist.
  edge_hard  acutance. Ratio of raw gradient to sigma-2 gradient at the strongest 2%
             of edges. A hard graphic edge collapses when blurred; a soft painted
             edge barely moves. This is the OTHER axis "cleaner and smoother" could
             have meant -- crispness of line rather than texture of surface -- and it
             is measured separately so the two cannot be conflated again.
  flat_coh   structure-tensor coherence of the high-pass residual inside the flat
             mask. Brush strokes are DIRECTIONAL: ridges run one way and score high.
             Isotropic film grain or sampler noise scores low. Without this, a metric
             cannot tell "textured paint" from "noisy render," and the whole question
             turns on that distinction.

Content is the dominant confound on every one of these. The sweep grids are fixed
seed and fixed prompt across configs, so config-vs-config within one prompt is a
clean comparison; plates-vs-outputs is not, and is reported as a distribution to be
read alongside the eye, never as a verdict on its own.
"""
import glob
import json
import os
import re
from collections import defaultdict

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel

APPROVED = r"E:\AI\style-dataset-lab\projects\salt-road\outputs\approved"
COMFY_OUT = r"E:\AI-Models\ComfyUI_windows_portable\ComfyUI\output"
REPORT = r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\texture-audit.json"

# The 14 plates that went through the qwen image_edit finishing pass. That pass
# rescaled 1344x768 -> 1328x800 and was cropped/restored, so their high-frequency
# content has been resampled at least once. Kept in the pool (the Director approved
# them) but reported separately so a resample artifact cannot masquerade as impasto.
FINISHED = set(json.load(open(
    r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\finishing-uploads.json")).keys())


def hue_bands(im):
    """Yellow / red-ochre share, reproducing measure-palette.py EXACTLY -- same
    240x137 downscale, same s>=0.22 / v>=0.18 gate, same 42-70 and 8-42 degree
    bands -- so the numbers are directly comparable to the published 9.6% dataset
    target and 12.6% ship figure. Vectorised, but deliberately not 'improved':
    changing the method would silently break comparability with the colour cycle.
    A texture win that re-breaks colour is not a win, so every image measured for
    texture is measured for colour in the same pass."""
    a = np.asarray(im.convert("RGB").resize((240, 137)), dtype=np.float64) / 255.0
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
    keep = (s >= 0.22) & (mx >= 0.18)
    yellow = int(((hd >= 42) & (hd <= 70) & keep).sum())
    ochre = int(((hd >= 8) & (hd < 42) & keep).sum())
    # GREEN IS A CONTAMINATION FLAG, NOT A NEW BAND. The 42-70 deg "yellow" band was
    # defined for limewashed ochre facades, where green barely appears. On a mossy
    # subject it silently mis-reads olive as yellow: the Crooked Stair acceptance
    # render measured 48% "yellow" while containing no yellow at all -- moss steps and
    # olive-tinted timber. The yellow band is deliberately NOT changed (that would
    # break comparability with the published 9.6% dataset / 12.6% ship figures);
    # green is reported alongside so the artifact is visible instead of silent.
    # READ THE COLOUR GATE ONLY WHEN green_pct IS LOW. High green => yellow_pct is
    # contaminated and that subject needs a different read.
    green = int(((hd > 70) & (hd <= 160) & keep).sum())
    tot = int(keep.sum())
    if tot == 0:
        return 0.0, 0.0, 0.0
    return 100.0 * yellow / tot, 100.0 * ochre / tot, 100.0 * green / tot


def measure(path):
    im = Image.open(path)
    assert im.mode in ("RGB", "RGBA"), f"{path}: unexpected mode {im.mode}"
    yellow_pct, ochre_pct, green_pct = hue_bands(im)
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
    edge_hard = float(egrad[strong].mean() / max(bgrad[strong].mean(), 1e-9))

    # --- directionality of the fine residual inside the flat mask ---
    hx, hy = sobel(hp, axis=1), sobel(hp, axis=0)
    Jxx = gaussian_filter(hx * hx, 4.0)
    Jyy = gaussian_filter(hy * hy, 4.0)
    Jxy = gaussian_filter(hx * hy, 4.0)
    disc = np.sqrt(((Jxx - Jyy) / 2.0) ** 2 + Jxy ** 2)
    tr = (Jxx + Jyy) / 2.0
    coh = 2.0 * disc / np.maximum(tr * 2.0, 1e-9)

    # --- facade repetition: contract law 1 inverted ---
    # "A row of identical facades is the tell of a fake port." Both LoRA cycles
    # reported wide exteriors flattening into repeating fronts, and it was never
    # isolated from the texture question. A periodic row produces a strong peak in
    # the horizontal autocorrelation of the column profile; a patchwork of near-miss
    # tones does not. Only meaningful on wide exteriors -- reported for the quay
    # prompt, meaningless for an interior or a close stone study.
    band = lum[int(0.15 * lum.shape[0]):int(0.60 * lum.shape[0]), :]
    col = band.mean(axis=0)
    col = col - gaussian_filter(col, 60.0)
    col = col / max(col.std(), 1e-9)
    n = col.size
    ac = np.correlate(col, col, "full")[n - 1:] / n
    facade_rep = float(ac[80:500].max())

    # --- radial power spectrum ---
    win = np.hanning(lum.shape[0])[:, None] * np.hanning(lum.shape[1])[None, :]
    F = np.fft.fftshift(np.abs(np.fft.fft2((lum - lum.mean()) * win)) ** 2)
    cy, cx = (np.array(F.shape) - 1) / 2.0
    yy, xx = np.ogrid[:F.shape[0], :F.shape[1]]
    # normalised radius: 1.0 == Nyquist along the shorter axis
    r = np.hypot((yy - cy) / (F.shape[0] / 2.0), (xx - cx) / (F.shape[1] / 2.0))
    tot = F.sum()

    return {
        "lap_var": float(lap.var()),
        "hf_ratio": float(hp.std() / max(lum.std(), 1e-9)),
        "flat_hf": float(hp[flat].std()),
        "edge_dens": float((egrad > 12.0).mean()),
        "band_hi": float(F[r > 0.30].sum() / tot),
        "band_mid": float(F[(r > 0.10) & (r <= 0.30)].sum() / tot),
        "edge_hard": edge_hard,
        "flat_coh": float(coh[flat].mean()),
        "lum_std": float(lum.std()),
        "yellow_pct": yellow_pct,
        "ochre_pct": ochre_pct,
        "green_pct": green_pct,
        "facade_rep": facade_rep,
    }


KEYS = ["flat_coh", "flat_hf", "yellow_pct", "facade_rep", "hf_ratio", "edge_hard",
        "lap_var", "edge_dens", "band_hi", "lum_std"]


def classify(name):
    """(group, prompt, seed) for a sweep output filename, or None to skip."""
    m = re.match(r"saltroad_(v2)?sweep_(quay|stone|interior)_(\w+?)_s(\d+)_", name)
    if m:
        ver = "v2" if m.group(1) else "v1"
        ck = m.group(3)
        grp = "base (no LoRA)" if ck == "noLoRA" else f"{ver} ckpt{ck} @1.00"
        return grp, m.group(2), int(m.group(4))
    m = re.match(r"saltroad_v2wt_1500_w(\d+)_s(\d+)_", name)
    if m:
        w = {"05": "0.50", "075": "0.75"}[m.group(1)]
        return f"v2 ckpt1500 @{w}", "quay", int(m.group(2))
    m = re.match(r"saltroad_wt_0*(\d+)_w(\d+)_s(\d+)_", name)
    if m:
        w = {"05": "0.50", "075": "0.75"}[m.group(2)]
        return f"v1 ckpt{m.group(1)} @{w}", "quay", int(m.group(3))
    # the free texture grid (2026-08-01): full factorial ckpt x weight
    m = re.match(r"saltroad_v3grid_(\d+)_w(\d+)_s(\d+)_", name)
    if m:
        w = {"075": "0.75", "085": "0.85", "100": "1.00"}[m.group(2)]
        return f"v2 ckpt{m.group(1)} @{w}", "quay", int(m.group(3))
    # H3: prompt-side surface language, single lever = the positive text
    m = re.match(r"saltroad_v4dens_(sparse|dense)_s(\d+)_", name)
    if m:
        return f"DENSITY {m.group(1)} L2@1.00", "interior", int(m.group(2))
    m = re.match(r"saltroad_v5mod_(depth|nocn)_(L0|L2)_s(\d+)_", name)
    if m:
        return f"MODULE {m.group(1)}+{m.group(2)}", "interior", int(m.group(3))
    # v4 tracks: interiors (rung x weight), subject transfer, controlnet
    m = re.match(r"saltroad_v4int_(L0|L2|L3)_w(\d+)_s(\d+)_", name)
    if m:
        w = {"075": "0.75", "085": "0.85", "100": "1.00"}[m.group(2)]
        return f"INT {m.group(1)} @{w}", "interior", int(m.group(3))
    m = re.match(r"saltroad_v4subj_(charscene|charplain|propplain)_(L0|L2)_w(\d+)_s(\d+)_", name)
    if m:
        w = {"075": "0.75", "100": "1.00"}[m.group(3)]
        return f"{m.group(2)} @{w}", m.group(1), int(m.group(4))
    m = re.match(r"saltroad_v4cn_(L0|L2)_s(\d+)_", name)
    if m:
        return f"CONTROLNET {m.group(1)} @0.75", "quay", int(m.group(2))
    m = re.match(r"saltroad_v3plate_quay_(LP|LPF)_s(\d+)_", name)
    if m:
        return {"LP": "PLATE-CLAUSE gouache @0.75",
                "LPF": "PLATE-PREAMBLE full @0.75"}[m.group(1)], "quay", int(m.group(2))
    m = re.match(r"saltroad_v3seed_(L0|L1|L2|L3)_s(\d+)_", name)
    if m:
        return {"L0": "SURFACE L0 none  @0.75", "L1": "SURFACE L1 mild @0.75",
                "L2": "SURFACE L2 mid  @0.75", "L3": "SURFACE L3 full @0.75"}[m.group(1)], "quay", int(m.group(2))
    m = re.match(r"saltroad_v3subj_(stone|interior)_(L0|L2|L3)_s(\d+)_", name)
    if m:
        return {"L0": "SURFACE L0 none  @0.75", "L2": "SURFACE L2 mid  @0.75",
                "L3": "SURFACE L3 full @0.75"}[m.group(2)], m.group(1), int(m.group(3))
    m = re.match(r"saltroad_v3lang_(ship|base|L1|L2)_s(\d+)_", name)
    if m:
        tag = {"ship": "SURFACE L3 full @0.75", "base": "SURFACE L3 on base",
               "L1": "SURFACE L1 mild @0.75", "L2": "SURFACE L2 mid  @0.75"}[m.group(1)]
        return tag, "quay", int(m.group(2))
    # v11: the five contract §7 zone plates, Blender-locked production run
    # (interiors @1.00, exteriors @0.75; InstantX depth 0.80/0/0.45; L2 clause)
    m = re.match(r"saltroad_v11_(counting_house|weighing_floor|long_quay|customs_shed|crooked_stair)(_b)?_s(\d+)_", name)
    if m:
        bucket = {"counting_house": "interior", "weighing_floor": "interior",
                  "customs_shed": "interior", "long_quay": "quay",
                  "crooked_stair": "stone"}[m.group(1)]
        return f"ZONE {m.group(1)}{m.group(2) or ''}", bucket, int(m.group(3))
    return None


def summarise(rows, keys=KEYS):
    return {k: round(float(np.mean([r[k] for r in rows])), 4) for k in keys}


# Subject buckets, so plates can be compared against the sweep prompt that shares
# their subject. Pooling all 73 against a quay-only output set is the same content
# confound the kickoff warns about; an open-sea plate scores 1.3 and a cobbled quay
# 13.5 on identical brushwork.
SUBJECTS = {}
try:
    wave = json.load(open(
        r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\wave-v2.json"))
    for it in wave["items"]:
        SUBJECTS[it["id"]] = it["subject"].lower()
except (OSError, KeyError):
    pass

# hand map for the v1 p-series, whose subjects are in the filename
P_SERIES = {"p01": "exterior", "p02": "exterior", "p03": "exterior",
            "p06v2": "interior", "p08": "detail", "p09": "detail",
            "p10": "interior", "p11v2": "detail", "p12": "interior",
            "p13": "interior", "p15": "stone", "p18": "sea", "p20": "sea"}


def subject_of(stem):
    if stem.split("_")[0] in P_SERIES:
        return P_SERIES[stem.split("_")[0]]
    s = SUBJECTS.get(stem)
    if not s:
        return "unknown"
    if "interior of" in s or s.startswith("inside"):
        return "interior"
    if any(k in s for k in ("open sea", "open water", "seen from the water",
                            "chart", "hull of")):
        return "sea"
    if any(k in s for k in ("close study", "detail of", "still life", "close-up")):
        return "detail"
    if any(k in s for k in ("quay", "harbour", "waterfront", "dock", "wharf",
                            "warehouse front", "street", "alley", "courtyard")):
        return "exterior"
    return "other"


# ---------------------------------------------------------------- plates
plate_rows = []
for p in sorted(glob.glob(os.path.join(APPROVED, "*.png"))):
    stem = os.path.basename(p)[len("styleset_"):-len(".png")]
    r = measure(p)
    r["plate"] = stem
    r["finished"] = stem in FINISHED
    r["subject"] = subject_of(stem)
    plate_rows.append(r)

direct = [r for r in plate_rows if not r["finished"]]
finished = [r for r in plate_rows if r["finished"]]

print(f"=== TRAINING PLATES (n={len(plate_rows)}, native 1344x768) ===")
print(f"{'subset':28s} {'n':>4s} " + " ".join(f"{k:>10s}" for k in KEYS))
for label, rows in [("all approved", plate_rows),
                    ("  direct generation", direct),
                    ("  finishing-pass (resampled)", finished)]:
    s = summarise(rows)
    print(f"{label:28s} {len(rows):4d} " + " ".join(f"{s[k]:10.4f}" for k in KEYS))

# per-plate extremes, so the metric can be checked against the eye
plate_rows.sort(key=lambda r: -r["flat_hf"])
print(f"\n  roughest 5 plates by flat_hf: " +
      ", ".join(f"{r['plate']}({r['flat_hf']:.2f})" for r in plate_rows[:5]))
print(f"  smoothest 5 plates by flat_hf: " +
      ", ".join(f"{r['plate']}({r['flat_hf']:.2f})" for r in plate_rows[-5:]))

# ---------------------------------------------------------------- outputs
by_cfg = defaultdict(list)
by_cfg_prompt = defaultdict(list)
for p in sorted(glob.glob(os.path.join(COMFY_OUT, "saltroad_*.png"))):
    c = classify(os.path.basename(p))
    if not c:
        continue
    grp, prompt, seed = c
    r = measure(p)
    r.update(cfg=grp, prompt=prompt, seed=seed, file=os.path.basename(p))
    by_cfg[grp].append(r)
    by_cfg_prompt[(grp, prompt)].append(r)

plate_ref = summarise(plate_rows)

print(f"\n=== LoRA OUTPUTS vs PLATES — all prompts pooled (n={sum(len(v) for v in by_cfg.values())}) ===")
print(f"{'config':24s} {'n':>4s} " + " ".join(f"{k:>10s}" for k in KEYS))
print(f"{'TARGET — 73 plates':24s} {len(plate_rows):4d} " +
      " ".join(f"{plate_ref[k]:10.4f}" for k in KEYS))


def cfg_order(g):
    return (0 if g.startswith("base") else 1 if g.startswith("v1") else 2, g)


for grp in sorted(by_cfg, key=cfg_order):
    s = summarise(by_cfg[grp])
    print(f"{grp:24s} {len(by_cfg[grp]):4d} " + " ".join(f"{s[k]:10.4f}" for k in KEYS))

# ------------------------------------------------- the controlled comparison
SUBJ_FOR_PROMPT = {"quay": "exterior", "stone": "stone", "interior": "interior"}

print("\n=== CONTROLLED — same prompt, same 3 seeds, one lever (config) ===")
print("    each block is content-matched: the plate row uses only plates of the")
print("    same subject, so 'more texture' cannot just mean 'more stuff'.")
for prompt in ("quay", "stone", "interior"):
    cfgs = sorted([g for (g, pr) in by_cfg_prompt if pr == prompt], key=cfg_order)
    if not cfgs:
        continue
    print(f"\n  [{prompt}]  {'config':24s} " + " ".join(f"{k:>10s}" for k in KEYS[:7]))
    matched = [r for r in plate_rows if r["subject"] == SUBJ_FOR_PROMPT[prompt]]
    if matched:
        s = summarise(matched, KEYS[:7])
        print(f"  {'':10s}{'TARGET — plates n=' + str(len(matched)):24s} " +
              " ".join(f"{s[k]:10.4f}" for k in KEYS[:7]))
    for grp in cfgs:
        s = summarise(by_cfg_prompt[(grp, prompt)], KEYS[:7])
        print(f"  {'':10s}{grp:24s} " + " ".join(f"{s[k]:10.4f}" for k in KEYS[:7]))

print("\n=== PLATE POOL BY SUBJECT (the content confound, made visible) ===")
bysub = defaultdict(list)
for r in plate_rows:
    bysub[r["subject"]].append(r)
print(f"{'subject':12s} {'n':>4s} " + " ".join(f"{k:>10s}" for k in KEYS[:7]))
for sub in sorted(bysub, key=lambda s: -len(bysub[s])):
    s = summarise(bysub[sub], KEYS[:7])
    print(f"{sub:12s} {len(bysub[sub]):4d} " + " ".join(f"{s[k]:10.4f}" for k in KEYS[:7]))

json.dump({
    "plates": {"all": summarise(plate_rows), "direct": summarise(direct),
               "finishing_pass": summarise(finished), "rows": plate_rows},
    "configs": {g: {"n": len(v), **summarise(v)} for g, v in by_cfg.items()},
    "by_config_prompt": {f"{g}|{p}": {"n": len(v), **summarise(v)}
                         for (g, p), v in by_cfg_prompt.items()},
}, open(REPORT, "w"), indent=2)
print(f"\nwrote {REPORT}")
