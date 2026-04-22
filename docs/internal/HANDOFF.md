# Session Handoff — 2026-04-13 (Universe Expansion + Painterly Pass)

## What Happened This Session

Expanded the Star Freight universe with new species, customs, stations, and visual identities. Then ran the full 887-image painterly post-processing pass.

### Deliverables

1. **SPECIES_CANON.md v0.2** — 12 new customs for core aliens (Keth molting/hive-song/pheromone libraries/seasonal debt, Veshan forge-trials/scale-reading/cold-debt/battle-opera, Orryn drift parliament/crystal inheritance/dark trade/tentacle autonomy). 3 minor species (Thresh silicon filter-feeders, Mire colonial aggregates, Vaelk gaseous proxy-traders). Extinct Architects. Station fauna (void lice, drift kelp, faction vermin). Cross-species trade protocols (pidgin trade-sign, station protocols, smuggler cant).

2. **VISUAL_BIBLE.md v0.3** — Added anatomy specs for Thresh, Mire, Vaelk proxy. Architect ruins visual language. Drift kelp spec.

3. **STATION_BIBLE.md v0.1** — 9 stations with full visual identity (thesis, architecture, lighting, sound, smell, commerce infrastructure, wear patterns, key landmarks). New station: Burn Gate (Veshan border toll — needs code implementation).

4. **Wave 25** (expanded universe) — 60 images, 48 approved / 12 rejected
5. **Wave 25b** (species regen) — 18 images, fixed SDXL human-default with negative prompt trick
6. **Wave 26** (station identities) — 46 images, 23 subjects × 2 variations
7. **Painterly post-processing pass** — 887 approved images through img2img at denoise 0.5, ClassipeintXL LoRA 1.0

### Key Discovery: Alien Negative Prompt

SDXL defaults all figures to human anatomy. Adding `human, person, man, woman` to the negative prompt + frontloading species anatomy in the prompt text solved this immediately. This is the single biggest lever for non-human species accuracy.

### Key Discovery: Painterly Denoise Sweet Spot

- **0.38** — barely visible difference (too subtle)
- **0.50** — visible brushwork, composition preserved, content intact (sweet spot)
- **0.60** — faces change, phantom figures appear (too much)
- **0.70** — completely different image (content destroyed)

---

## Current State

```
887 approved originals + 124 new candidates (waves 25/25b/26)
887 painterly versions (in progress, ~9s/image)
18 visual categories across 26 waves
```

### Pipeline Architecture

```
Canon (species, factions, world lore)
  → Visual Style Bible (art rules, prompt fragments, validation checklist)
    → Style Dataset Lab (ComfyUI txt2img + painterly img2img + curation)
      → repo-dataset (training JSONL export)
        → Fine-tuned VLM (consistent style generation + judgment)
```

### Generation Setup

```yaml
# txt2img (base generation)
checkpoint: dreamshaperXL_v21TurboDPMSDE.safetensors
lora: classipeintxl_v21.safetensors (weight: 1.0)
resolution: 1024x1024
steps: 8, cfg: 2.0, sampler: dpmpp_sde, scheduler: karras

# img2img (painterly post-processing)
same checkpoint + lora at 1.0
denoise: 0.50, steps: 10, cfg: 2.5, seed: 42
prompt: "oil painting, visible brushstrokes, painterly concept art..."
negative: "photorealistic, photograph, 3d render, smooth CG..."
```

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/generate.js` | txt2img ComfyUI automation |
| `scripts/painterly.js` | img2img painterly post-processing |
| `scripts/painterly-test.js` | A/B test denoise levels |
| `scripts/curate.js` | Individual curation |
| `scripts/curate-wave25.js` | Bulk curation for wave 25 |
| `scripts/compare.js` | Pairwise A-vs-B preference |
| `scripts/bulk-curate-waves11-18.js` | Bulk curation waves 11-24 |
| `scripts/canon-bind.js` | Canon binding (25 rules) |
| `canon/constitution.md` | Style rules |
| `canon/species-canon.md` | Species cultural depth |
| `canon/review-rubric.md` | Curation protocol |

### Companion Files

| File | Purpose |
|------|---------|
| `F:/AI/star-freight-ue5/VISUAL_BIBLE.md` | v0.3 — design authority |
| `F:/AI/star-freight-ue5/SPECIES_CANON.md` | v0.2 — species/culture |
| `F:/AI/star-freight-ue5/STATION_BIBLE.md` | v0.1 — 9 stations |

---

## Commands

```bash
# Start ComfyUI
cd F:/AI-Models/ComfyUI-runtime && python main.py --listen 127.0.0.1 --port 8188

# Generate a wave
cd F:/AI/style-dataset-lab
node scripts/generate.js inputs/prompts/wave26-station-identities.json

# Painterly pass (auto-skips already processed)
node scripts/painterly.js --limit 100
node scripts/painterly.js --source outputs/candidates --limit 50

# Curate wave 25
node scripts/curate-wave25.js

# Canon bind all records
node scripts/canon-bind.js --force

# Export dataset
node F:/AI/repo-dataset/dist/cli.js visual generate . --format trl --output exports
```

---

## What's Next

1. **Painterly pass completion** — 887 images running
2. **Painterly the new waves** — run waves 25/25b/26 through painterly after curation
3. **Pairwise comparisons** — original vs painterly pairs for DPO preference data
4. **Export** — training JSONL with both original and painterly variants
5. **Blank pipeline template** — extract reusable starter kit from this workflow
6. **Crew character concepts** — 6 named crew as individuals
7. **Ship fleet sheets** — faction ship design language rendered

---

*The pipeline is now: canon informs bible, bible informs generation, generation produces training data, training data teaches the model to maintain the style. Each new game starts with a blank template and fills it in.*

---

# Session Handoff — 2026-04-16 (AI Eye Test: VLM Counting Benchmark)

## What happened this session

Built a **domain-neutral VLM vision benchmark** as a new project inside style-dataset-lab: `projects/ai-eye-test/`. Purpose: test whether Claude Opus 4.7's 3× resolution bump actually helps on real tasks, expanded into a cross-vendor counting eval comparing Opus 4.7 / GPT-4o / GPT-5 / Gemini 2.5 Pro with exact ground truth.

### Deliverables

1. **`projects/ai-eye-test/` — new standalone project** with lanes / constitution / rubric / terminology / workflow-profiles for 8 planned subcategories. Only `dense-count` populated so far; the other 7 are scaffolded and ready for content.

2. **Compositor — `projects/ai-eye-test/compositor/`** (~350 LOC Python, 26/26 tests passing):
   - Alpha cutout via `rembg` (U-2-Net)
   - Bridson Poisson-disk placement (O(n), scales to 100+ instances)
   - Per-instance rotation + scale + HSV color jitter
   - Drop shadows (Gaussian-blurred alpha offset)
   - `BackgroundPool` rotation across SDXL-generated neutral surfaces
   - Ground truth emitted by construction: `{image, count, seed, bboxes_xywh}`

3. **Datasets (all in `projects/ai-eye-test/outputs/synthetic/`):**
   - `phase1/` — 4 images (n=4 per cell, deprecated — below noise floor)
   - `phase2/` — 96 images × 2048² canvas, 6 counts × 16 seeds. **Primary artifact.**
   - `phase2b/` — 64 images × 1024² canvas (scale ablation)
   - `phase2_noshadow/` — 16 images (shadow ablation)

4. **Hero instances + backgrounds:**
   - 3 SDXL hero instances (green apple, brown box, white mug) in `outputs/candidates/hero_*.png`
   - Cleaned apple cutout via rembg in `outputs/cutouts/hero_green_apple_v1.png`
   - 4 SDXL neutral backgrounds (wood, concrete, white cloth, marble) in `backgrounds/`

5. **Eval harness — lives in `F:/AI/ai-eyes-mcp/evals/opus_4_7_vision/`** (separate repo, consumes this project's data). Reusable runners for Anthropic-direct + OpenRouter cross-vendor.

### Key findings (brief; full writeups in the eval repo)

- **Bias direction is vendor-specific.** Same image at 256/n=100: GPT-4o +48, Opus 4.7 −32, Gemini −19.
- **Opus 4.7 confidence is 8× better calibrated** than GPT-4o on this task (right/wrong gap 0.30 vs 0.04).
- **Gemini 2.5 Pro @ 768px is the single best cell** for n=100 accuracy (MAE 9.1 at $0.002/call).
- **Tool-use recovers 64% of Opus 4.7's n=100 failure** (MAE 44.3 → 15.8 with 8 `crop_image` calls).
- **GPT-5 reasoning is worse than GPT-4o** on dense counting — it snaps to round grid numbers.
- **Nearest-neighbor downscaling beats Lanczos 3×** at 256px. Free one-line preprocessor fix.

### Key SDXL discovery (for future compositor work)

**`cv2.seamlessClone(MIXED_CLONE)` is NOT safe for compositor pipelines on textured backgrounds.** It blends gradients from both foreground and background, which desaturated our apples into wood-grain invisibility. Alpha paste + drop shadows gives acceptable realism without destroying object color. Documented in `outputs/synthetic/phase2/DATASET_CARD.md` as a "known issues / gotchas" section.

---

## Current state of `ai-eye-test`

```
projects/ai-eye-test/
├── project.json, lanes.json, constitution.json, rubric.json, terminology.json
├── inputs/prompts/
│   ├── dense-count.json             (v1, deprecated)
│   ├── dense-count-v2.json          (density descriptors, 12 subjects)
│   ├── hero-instances.json          (3 hero objects)
│   └── backgrounds.json             (4 neutral backgrounds)
├── backgrounds/                     (4 PNGs from inputs/prompts/backgrounds.json)
├── compositor/                      (Python — primary asset)
│   ├── compositor.py + test_compositor.py      (Phase 1 MVP)
│   ├── phase2.py + test_phase2.py              (Bridson + shadows + bg pool)
│   ├── phase1_smoke.py                          (demo runner)
│   ├── phase2_build.py                          (96-image build)
│   ├── phase2_noshadow_build.py                 (ablation)
│   └── phase2b_build.py                         (scale ablation)
├── outputs/
│   ├── candidates/                  (hero instances + backgrounds)
│   ├── cutouts/                     (rembg output)
│   └── synthetic/
│       ├── phase1/    (4 images)
│       ├── phase2/    (96 images + manifest.json + DATASET_CARD.md)
│       ├── phase2b/   (64 images + manifest.json)
│       └── phase2_noshadow/ (16 images + manifest.json)
└── records/           (generated records from sdlab)
```

### Pending work in ai-eye-test

1. **7 subcategories empty** — `fine-detail`, `small-target-wide-frame`, `small-text-numeric`, `labeled-grid`, `ab-compare`, `layout-hierarchy`, `chart-read`. Each needs a prompt pack and a build recipe.
2. **Box / mug hero instances unused** — we only ran the apple. One line swap in `phase2_build.py` regenerates the full 96-image set with boxes or mugs.
3. **Poisson blending (`cv2.NORMAL_CLONE`) untested** — MIXED_CLONE failed; NORMAL_CLONE might give seam-softening without color destruction. Worth a 5-minute smoke before dismissing.
4. **Cross-class evaluations not done** — we know apples work; is the signal class-invariant?

---

## What the eval harness enables for future style-dataset-lab work

Any dataset produced by the compositor can be fed to 4+ VLMs cross-vendor with one-line changes to `scripts/run_crossmodel_sweep.py` in the eval repo. Useful for:

- Measuring how well downstream VLMs evaluate a new style lane (visual scoring of outputs)
- Validating that dataset images have unambiguous ground truth before training
- Finding the resolution threshold where VLM-as-judge breaks down for a given lane

---

## What's Next (updated)

1. ~~Painterly pass completion~~ — done in prior session
2. **Populate remaining 7 ai-eye-test subcategories** — each gives us cross-vendor data on a different cognitive task type
3. **Swap hero class in `phase2_build.py`** — same 96-image pipeline with boxes/mugs, validates class invariance
4. **Test NORMAL_CLONE blending** — 5-minute follow-up to the MIXED_CLONE failure
5. **Publish the benchmark** — the analyses in `F:/AI/ai-eyes-mcp/evals/opus_4_7_vision/results/` are blog/arXiv-ready with light editing
6. **Intra-Anthropic tier comparison** — Opus 4.6 / Sonnet 4.6 / Haiku 4.5 on the same 96 images (~$2 budget, uses existing Anthropic API key)

---

## Replicator warnings (new)

Before doing any VLM evaluation work with this dataset:

1. **Anthropic API caps base64 images at 5 MB.** Our 2048² n=100 PNGs hit 7.4 MB. Runner has JPEG q=92 fallback above 3.8 MB raw.
2. **Opus 4.7 rejects `temperature` parameter.** 4.6 still takes it. Skip conditionally.
3. **Gemini wraps JSON in markdown fences** + verbose — set `max_tokens ≥1024`.
4. **GPT-5 reasoning needs `max_tokens ≥2048`** for reasoning headroom.
5. **GPT-4o self-reported confidence is flat** — don't use it for abstention.
6. **Minimum 16 seeds per cell** for any direction-of-bias claim. Phase 1's n=4 gave us the wrong answer direction before Phase 2's n=16 corrected it.
7. **On Windows: `write_text(..., encoding="utf-8")`** — cp1252 default crashes on U+2212 etc.

Details + fix code in `F:/AI/ai-eyes-mcp/evals/opus_4_7_vision/results/README.md` Replicator Notes section and `memory/feedback_vlm_api_gotchas.md`.
