# AI Eye Test — Phase 2 Dense-Count Dataset

**Created:** 2026-04-16
**Objects:** 96 PNGs + 96 per-image label JSONs + 1 manifest
**Canvas:** 2048 × 2048 PNG
**Class:** green apple (single class, this phase)
**Counts:** {1, 5, 10, 20, 50, 100} × 16 independent seeds per count = 96 images
**Total bboxes:** 2,976 (= 16 × (1 + 5 + 10 + 20 + 50 + 100))

## Purpose

Multi-seed synthetic dataset for measuring Opus 4.7 (and other VLMs) counting accuracy with statistical power. Supersedes the Phase 1 n=4 set whose conclusions were swallowed by temperature=1.0 stochastic variance (documented in [ANALYSIS_2026-04-16.md](../../../../../ai-eyes-mcp/evals/opus_4_7_vision/results/ANALYSIS_2026-04-16.md)).

## Generation pipeline

1. **Hero instance**: SDXL (DreamShaperXL Turbo, 8 steps, cfg 2.0) — single green apple, centered, white backdrop.
2. **Cutout**: `rembg` (U-2-Net) → tight-cropped RGBA (456 × 606 px).
3. **Backgrounds**: 4 SDXL-generated neutral surfaces — wooden table, concrete floor, white tablecloth, grey marble counter. Rotated across composites to prevent "more texture → more objects" shortcut.
4. **Placement**: Bridson fast Poisson-disk ([Bridson 2007](https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph07-poissondisk.pdf)) with `min_dist = 150 * 1.1 = 165px`. Produces ~150-200 candidate centers on 2048² canvas; first N shuffled and used.
5. **Per-instance realism pass** (on each pasted copy):
   - Rotation jitter: ±20°
   - Scale jitter: 0.8× – 1.2×
   - Color jitter: HSV hue ±5°, saturation ×[0.85, 1.15], value ×[0.9, 1.1]
   - Drop shadow: 6×10 offset, 14-pixel Gaussian blur, opacity 0.35
6. **Composite**: alpha paste (NOT seamlessClone — see known issues below).
7. **Manifest**: `manifest.json` with per-image `{count, seed, bboxes_xywh, ...}`.

## Files

```
manifest.json                    — dataset-level schema + per-image index
apple_n001_s00.png + .json       — count=1, seed index 0
apple_n001_s01.png + .json
...
apple_n100_s15.png + .json       — count=100, seed index 15
```

## Ground truth guarantees

Ground truth is authored **by construction**. For each image:

- **Exact count** = number of pasted copies = first field of filename
- **Bboxes** = XYWH of each pasted instance after rotation/scale/shadow offset
- **Determinism**: seeding is fully deterministic; rerunning with the same seed produces byte-identical output

## Known issues discovered during build

### `cv2.seamlessClone(MIXED_CLONE)` was catastrophic for this subject/background mix

First generation pass used `seamlessClone(MIXED_CLONE)` per the research-swarm recommendation (and GrayCount250 / RarePlanes precedent). Result: apples were heavily **desaturated into the background texture** — on a wood-grain background, apples acquired the wood coloration and became nearly invisible. n=100 looked like a wood grain pattern with faint tints, not 100 apples.

The "halo-killing" benefit traded away object visibility. Root cause: `MIXED_CLONE` blends image **gradients** from both foreground and background, so a hard-edge green apple on a rapidly-textured wood surface picks up the wood gradient signature and loses its own color.

**Fix:** use alpha paste (no seamlessClone). Drop shadows alone handle enough of the "obviously pasted" tell. Seams are visible on close inspection but the dataset remains usable because (a) we're not training on it, (b) VLMs at 256-1024px can't resolve seam artifacts anyway.

### Edge-cropped instances at low counts

At n=1 and n=5, some apples are partially cropped by the canvas edge because Bridson placement uses instance-radius-based spacing but doesn't margin-pad from the edge. This matches our prompt instruction ("ignore partial/cropped instances at the frame edge") so it's a feature not a bug — adds realism. But worth flagging that exact-match scoring should tolerate ±1 for edge cases at low N.

### Fixed instance scale

All instances derive from the same source cutout at `target_instance_long_edge=150` with ±20% scale jitter. Real-world dense-count scenes have much wider scale variation (close vs far). A future Phase 2.1 should sample scale from a bimodal distribution or use perspective projection.

## Recommended use

### Running the full eval

```python
from evals.opus_4_7_vision.config import Dataset, Model, Task
from evals.opus_4_7_vision.harness import run_matrix

# 96 images × resolutions you care about × temperature=0 for determinism
run_matrix(
    models=[Model.OPUS_47],
    resolutions=[256, 768, 1024, 2576],
    tasks=[Task.OBJECT_COUNT],
    dataset=Dataset.SYNTHETIC_PHASE2,  # needs new loader — see datasets.py
    tag="phase2_resolution_sweep",
)
```

Before running you need to:
1. Add `Dataset.SYNTHETIC_PHASE2` enum value
2. Add `load_synthetic_phase2()` to [datasets.py](../../../../../ai-eyes-mcp/evals/opus_4_7_vision/datasets.py) (mirrors `load_synthetic_phase1()` but reads `manifest.json`)
3. **Set `temperature=0`** in the OpusRunner to eliminate stochastic noise. This was the biggest lesson from Phase 1 — temperature=1.0 gave us a ±25 point EM noise floor at n=4.

### Cost estimate

At Opus 4.7 input pricing ($5/Mtok) and ~1,500 tokens/image at 1024px:

| Sweep shape | Calls | Estimated spend |
|---|---:|---:|
| Full set @ 1 resolution | 96 | ~$0.80 |
| Full set × 4 resolutions | 384 | ~$3.20 |
| Full set × 4 res × 2 resize methods | 768 | ~$6.50 |

## Provenance

- SDXL workflows / prompts: [inputs/prompts/hero-instances.json](../../inputs/prompts/hero-instances.json), [inputs/prompts/backgrounds.json](../../inputs/prompts/backgrounds.json)
- Compositor source: [compositor/](../../compositor/)
- Commit: generated 2026-04-16 (pre-versioning)
