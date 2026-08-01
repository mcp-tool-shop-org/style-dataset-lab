#!/usr/bin/env python3
"""Content-controlled cross-check of the stroke-coherence ranking.

WHY THIS REPLACES THE WHOLE-IMAGE VERSION. crosscheck-dists.py scored every arm
against a reference corpus of whole plates, and FAILED ITS OWN SANITY CHECK: several
synthetic arms scored CLOSER to the plate corpus than real held-out plates did. A
distance-to-corpus metric on which synthetic images beat genuine members of that
corpus is not measuring membership -- it is measuring content overlap. Every arm
renders one quay scene resembling the reference quay plates, while the held-out
plates are genuinely different scenes (a bonded door, a hull, a night quay). Content
dominated both metrics, so neither ranking from that run is trustworthy, and the
agreement between DISTS and flat_coh there cannot be claimed as corroboration.

THE FIX is to strip content, not to argue about it. Both sides are reduced to the
mechanically-chosen flattest WARM 384x384 patch -- the same picker used for the 1:1
review sheets, no hand-steering. A flat limewashed wall is content-poor by
construction, so what remains for VGG to see is surface: how the paint sits, not what
is in the picture.

CALIBRATION CRITERION, declared before reading the result
([[ai-eyes-cannot-grade-fine-structure]]: a different model family is not
automatically competent at your question, so calibrate on a known answer first):
held-out REAL plates must score at or near the minimum. If synthetic arms again beat
real plates, the instrument is still content-dominated at patch level and its ranking
is reported as UNUSABLE rather than as a second opinion.

Instruments, per the scout swarm's Step-4-verified findings:
  DISTS      Ding et al. 2020, arXiv:2004.07728 -- texture/structure separation.
  StyleLoss  Gatys et al. 2015, arXiv:1505.07376 -- Gram matrices, layout-free.
Excluded: FID (sample-size bias at n=73, Chong & Forsyth 2020 / Jayasumana 2024),
DreamSim (looks past low-level texture by design, Fu 2023).
Preprocessing controlled throughout: native pixels, PNG, no resize anywhere -- resize
artifacts alone flip metric rankings (Parmar 2021, arXiv:2104.11222). The patch is a
CROP, which removes pixels but never resamples the ones it keeps.
"""
import glob
import json
import os
import random

import numpy as np
import torch
import piq
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel, uniform_filter

APPROVED = r"E:\AI\style-dataset-lab\projects\salt-road\outputs\approved"
OUT = r"E:\AI-Models\ComfyUI_windows_portable\ComfyUI\output"
TEX = r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\texture-audit.json"
REPORT = r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\crosscheck-patch.json"
DEV = "cuda" if torch.cuda.is_available() else "cpu"
W = 384

ARMS = {
    "base (no LoRA), bare":       ["saltroad_v2sweep_quay_noLoRA_s%d_00001_.png"],
    "L0 ship @0.75, bare":        ["saltroad_v3grid_1500_w075_s%d_00001_.png", "saltroad_v3seed_L0_s%d_00001_.png"],
    "L1 'visible brushwork'":     ["saltroad_v3lang_L1_s%d_00001_.png", "saltroad_v3seed_L1_s%d_00001_.png"],
    "L2 'brushstrokes+worked'":   ["saltroad_v3lang_L2_s%d_00001_.png", "saltroad_v3seed_L2_s%d_00001_.png"],
    "L3 impasto/palette-knife":   ["saltroad_v3lang_ship_s%d_00001_.png", "saltroad_v3seed_L3_s%d_00001_.png"],
    "LP  plates' gouache clause": ["saltroad_v3plate_quay_LP_s%d_00001_.png"],
    "LPF plates' full preamble":  ["saltroad_v3plate_quay_LPF_s%d_00001_.png"],
}
S1, S2 = [101, 202, 303], [404, 505, 606, 707, 808]


def flat_patch(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im, dtype=np.float64)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    g = np.hypot(sobel(gaussian_filter(lum, 6.0), 1), sobel(gaussian_filter(lum, 6.0), 0))
    gm, bm = uniform_filter(g, W), uniform_filter(lum, W)
    warm = uniform_filter(a[..., 0] - a[..., 2], W)
    h, w = lum.shape
    half = W // 2
    valid = np.full(gm.shape, np.inf)
    sl = (slice(half, h - half), slice(half, w - half))
    v = gm[sl].copy()
    v[bm[sl] < 90] = np.inf
    v[warm[sl] < 25] = np.inf
    valid[sl] = v
    if not np.isfinite(valid).any():          # no warm lit region (night, sea)
        return None
    cy, cx = np.unravel_index(np.argmin(valid), valid.shape)
    c = np.asarray(im.crop((cx - half, cy - half, cx + half, cy + half)), np.float32) / 255.0
    return torch.from_numpy(c).permute(2, 0, 1).unsqueeze(0).to(DEV)


tex = json.load(open(TEX))
ext = [r["plate"] for r in tex["plates"]["rows"]
       if r.get("subject") == "exterior" and not r["finished"]]
rng = random.Random(20260801)
ref_names = sorted(rng.sample(ext, 12))
held_names = sorted(rng.sample(sorted(set(ext) - set(ref_names)), 8))

refs = [p for p in (flat_patch(os.path.join(APPROVED, f"styleset_{n}.png")) for n in ref_names)
        if p is not None]
print(f"reference plate patches: {len(refs)}   held-out plates: {len(held_names)}\n")

dists = piq.DISTS(reduction="none").to(DEV)
style = piq.StyleLoss(reduction="none").to(DEV)


@torch.no_grad()
def score(img):
    d = [float(dists(img, r).item()) for r in refs]
    s = [float(style(img, r).item()) for r in refs]
    return float(np.mean(d)), float(np.mean(s))


rows = {}
fd, fs = [], []
for n in held_names:
    p = flat_patch(os.path.join(APPROVED, f"styleset_{n}.png"))
    if p is None:
        continue
    a, b = score(p)
    fd.append(a)
    fs.append(b)
floor_d, floor_s = float(np.mean(fd)), float(np.mean(fs))
rows["FLOOR — held-out real plates"] = {"n": len(fd), "dists": floor_d, "style": floor_s}

for label, pats in ARMS.items():
    ds, ss = [], []
    for pat, seeds in zip(pats, (S1, S2)):
        for s in seeds:
            p = os.path.join(OUT, pat % s)
            if not os.path.exists(p):
                continue
            q = flat_patch(p)
            if q is None:
                continue
            a, b = score(q)
            ds.append(a)
            ss.append(b)
    if ds:
        rows[label] = {"n": len(ds), "dists": float(np.mean(ds)), "style": float(np.mean(ss))}

print(f"{'arm':30s} {'n':>3s} {'DISTS':>8s} {'StyleLoss':>11s}   (lower = surface closer to plates)")
for k, v in rows.items():
    tag = "  <-- FLOOR: what a real plate scores" if k.startswith("FLOOR") else ""
    print(f"{k:30s} {v['n']:3d} {v['dists']:8.4f} {v['style']:11.4e}{tag}")

beat_d = [k for k, v in rows.items() if not k.startswith("FLOOR") and v["dists"] < floor_d]
beat_s = [k for k, v in rows.items() if not k.startswith("FLOOR") and v["style"] < floor_s]
print(f"\nCALIBRATION — synthetic arms scoring below the real-plate floor:")
print(f"  DISTS     : {len(beat_d)}/{len(rows)-1}  {'USABLE' if len(beat_d) <= 1 else 'CONTENT-DOMINATED -> ranking UNUSABLE'}")
print(f"  StyleLoss : {len(beat_s)}/{len(rows)-1}  {'USABLE' if len(beat_s) <= 1 else 'CONTENT-DOMINATED -> ranking UNUSABLE'}")

json.dump({"reference": ref_names, "heldout": held_names, "rows": rows,
           "calibration": {"dists_below_floor": beat_d, "style_below_floor": beat_s}},
          open(REPORT, "w"), indent=2)
print(f"\nwrote {REPORT}")
