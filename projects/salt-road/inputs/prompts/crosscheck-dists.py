#!/usr/bin/env python3
"""Independent cross-check of the stroke-coherence ranking, using published
instruments instead of the hand-rolled ones.

WHY. measure-texture.py's flat_coh is mine: content-matched and it works, but it is
one lab's definition of "directional fine structure." The OSS scout swarm's Step-4
VERIFIED findings name two validated instruments for exactly this axis:

  DISTS      separates TEXTURE similarity from STRUCTURE similarity and tolerates
             texture resampling -- Ding, Ma, Wang & Simoncelli 2020 (arXiv:2004.07728,
             TPAMI). The published tool for "same surface character, different pixels."
  StyleLoss  Gram-matrix distance over VGG features -- Gatys et al. 2015
             (arXiv:1505.07376). Gram matrices discard spatial layout and keep texture
             statistics, which is what makes it legitimate to compare a generated quay
             against a plate of a DIFFERENT scene.

Deliberately NOT used: FID (model-dependent sample-size bias, Chong & Forsyth 2020
arXiv:1911.07023; poor sample complexity, Jayasumana 2024 arXiv:2401.09603 -- n=73 is
far too small) and DreamSim (engineered to look PAST low-level colour and texture,
Fu 2023 arXiv:2306.09344 -- it would be blind to the thing under test).

PREPROCESSING IS CONTROLLED, which is not optional: resize/JPEG artifacts alone flip
metric rankings (Parmar 2021, arXiv:2104.11222). Every image here is a native
1344x768 PNG loaded identically. Nothing is resized, re-encoded or cropped.

THE CONTROL THAT MAKES THIS READABLE. Every arm is scored against the SAME fixed
reference set of plates, so the content mismatch is a constant offset and only the
RANKING is claimed. And held-out plates are scored against that same set, giving the
FLOOR -- what a genuine approved plate scores. An arm's number means nothing on its
own; it means something against that floor.
"""
import glob
import json
import os
import random

import torch
import piq
from PIL import Image
import numpy as np

APPROVED = r"E:\AI\style-dataset-lab\projects\salt-road\outputs\approved"
OUT = r"E:\AI-Models\ComfyUI_windows_portable\ComfyUI\output"
REPORT = r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\crosscheck-dists.json"
DEV = "cuda" if torch.cuda.is_available() else "cpu"

# Quay arms. Every one is the ship recipe (v2 ckpt1500 @0.75) except where stated;
# the only thing that varies is the positive prompt's surface language.
ARMS = {
    "base (no LoRA), bare":      "saltroad_v2sweep_quay_noLoRA_s%d_00001_.png",
    "L0 ship @0.75, bare":       "saltroad_v3grid_1500_w075_s%d_00001_.png",
    "L1 'visible brushwork'":    "saltroad_v3lang_L1_s%d_00001_.png",
    "L2 'brushstrokes+worked'":  "saltroad_v3lang_L2_s%d_00001_.png",
    "L3 impasto/palette-knife":  "saltroad_v3lang_ship_s%d_00001_.png",
    "LP  plates' gouache clause": "saltroad_v3plate_quay_LP_s%d_00001_.png",
    "LPF plates' full preamble": "saltroad_v3plate_quay_LPF_s%d_00001_.png",
}
SEEDS = [101, 202, 303]

FINISHED = set(json.load(open(
    r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\finishing-uploads.json")).keys())
SUBJ = json.load(open(REPORT.replace("crosscheck-dists.json", "texture-audit.json")))


def load(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    assert a.shape[:2] == (768, 1344), f"{path}: {a.shape} -- preprocessing not controlled"
    return torch.from_numpy(a).permute(2, 0, 1).unsqueeze(0).to(DEV)


# reference = direct-generation exterior plates (finishing-pass ones were resampled,
# and a resample artifact is exactly what these metrics are sensitive to)
ext = [r["plate"] for r in SUBJ["plates"]["rows"]
       if r.get("subject") == "exterior" and not r["finished"]]
rng = random.Random(20260801)
ref_names = sorted(rng.sample(ext, 12))
held_names = sorted(set(ext) - set(ref_names))
held_names = sorted(rng.sample(held_names, 8))
print(f"reference plates (n={len(ref_names)}): {', '.join(ref_names)}")
print(f"held-out plates for the FLOOR (n={len(held_names)}): {', '.join(held_names)}\n")

refs = [load(os.path.join(APPROVED, f"styleset_{n}.png")) for n in ref_names]

dists = piq.DISTS(reduction="none").to(DEV)
style = piq.StyleLoss(reduction="none").to(DEV)


@torch.no_grad()
def score(img):
    d, s = [], []
    for r in refs:
        d.append(float(dists(img, r).item()))
        s.append(float(style(img, r).item()))
    return float(np.mean(d)), float(np.mean(s))


rows = {}
print(f"{'arm':30s} {'DISTS':>9s} {'StyleLoss':>12s}   (lower = closer to the plate corpus)")

# THE FLOOR first -- everything below is read against this
fd, fs = [], []
for n in held_names:
    a, b = score(load(os.path.join(APPROVED, f"styleset_{n}.png")))
    fd.append(a)
    fs.append(b)
rows["FLOOR — held-out real plates"] = {"n": len(held_names),
                                        "dists": float(np.mean(fd)), "style": float(np.mean(fs))}
print(f"{'FLOOR — held-out real plates':30s} {np.mean(fd):9.4f} {np.mean(fs):12.6f}  <-- what a genuine plate scores")

for label, pat in ARMS.items():
    ds, ss = [], []
    for s in SEEDS:
        p = os.path.join(OUT, pat % s)
        if not os.path.exists(p):
            continue
        a, b = score(load(p))
        ds.append(a)
        ss.append(b)
    if not ds:
        print(f"{label:30s} {'MISSING':>9s}")
        continue
    rows[label] = {"n": len(ds), "dists": float(np.mean(ds)), "style": float(np.mean(ss))}
    print(f"{label:30s} {np.mean(ds):9.4f} {np.mean(ss):12.6f}")

json.dump({"reference_plates": ref_names, "heldout_plates": held_names, "rows": rows},
          open(REPORT, "w"), indent=2)
print(f"\nwrote {REPORT}")
