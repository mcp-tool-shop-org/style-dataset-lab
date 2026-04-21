# AI Eye Test

**A domain-neutral VLM vision benchmark dataset with exact ground truth by construction.**

Tests cognitive capabilities that differ in their sensitivity to input resolution — independent of subject matter. Built inside style-dataset-lab; consumed by `ai-eyes-mcp/evals/opus_4_7_vision/` and any other harness that wants a clean, labeled counting benchmark.

Updated **2026-04-16** after the end-to-end dense-count build + cross-vendor eval (Opus 4.7, GPT-4o, GPT-5, Gemini 2.5 Pro). See [Current state](#current-state-2026-04-16) for what's in the repo right now.

## Why this exists

Public VLM evaluations often conflate "subject" with "task." A test of "find the knight's sword" measures both weapon recognition *and* sprite-art comprehension — two different things. This dataset separates them: each subcategory is a **cognitive task**, and subject matter is varied *within* each subcategory so the task generalizes across domains (game art, web UI, documents, photos, diagrams).

It also uses **synthetic composition** (cut-paste-jitter) to eliminate labeling ambiguity — every pasted instance is known exactly, so ground truth counts and bboxes are emitted at generation time, not approximated by human labeling.

## Subcategories (lanes)

| ID | Task | Status |
|---|---|---|
| `dense-count` | Count many instances | **✅ Populated** (160 images, 2 variants) |
| `fine-detail` | Localize sub-object features | Scaffolded only |
| `small-target-wide-frame` | Find a small target in a dense scene | Scaffolded only |
| `small-text-numeric` | Read small printed text | Scaffolded only |
| `labeled-grid` | Parse per-cell labels in a grid | Scaffolded only |
| `ab-compare` | Name differences between near-duplicate images | Scaffolded only |
| `layout-hierarchy` | Comprehend structural composition | Scaffolded only |
| `chart-read` | Extract values from data viz | Scaffolded only |

Each subcategory has `lanes.json`, `constitution.json` rules, `rubric.json` dimensions, and a slot in `terminology.json`. Prompts + images are what's missing for the other 7 — the infrastructure is there.

## Current state (2026-04-16)

### Dataset — `dense-count` subcategory

| Variant | Location | Canvas | Images | Counts |
|---|---|---:|---:|---|
| Phase 1 | `outputs/synthetic/phase1/` | 1024² | 4 | {1, 5, 10, 20} — n=1 per count |
| **Phase 2** (primary) | `outputs/synthetic/phase2/` | **2048²** | **96** | {1, 5, 10, 20, 50, 100} × 16 seeds |
| Phase 2b | `outputs/synthetic/phase2b/` | 1024² | 64 | {1, 5, 10, 20} × 16 seeds (scale ablation) |
| Phase 2 no-shadow | `outputs/synthetic/phase2_noshadow/` | 2048² | 16 | 100 × 16 (shadow ablation) |

Each phase has a `manifest.json` plus per-image `.json` with exact count, seed, and `bboxes_xywh` list.

**Dataset card:** [outputs/synthetic/phase2/DATASET_CARD.md](outputs/synthetic/phase2/DATASET_CARD.md) documents pipeline, gotchas (notably the `seamlessClone` color-kill), and recommended use.

### Compositor — `compositor/`

| File | Purpose |
|---|---|
| `compositor.py` | Phase 1 MVP — alpha cutout, rejection placement, jitter, alpha paste, save |
| `phase2.py` | Phase 2 additions — **Bridson Poisson-disk**, drop shadows, HSV color jitter, `BackgroundPool` |
| `test_compositor.py` + `test_phase2.py` | 26 unit tests — bbox overlap, placement density, determinism, shadow/jitter behavior |
| `phase1_smoke.py` | 4-image demo (counts 1/5/10/20) |
| `phase2_build.py` | 96-image multi-seed build for `dense-count` |
| `phase2b_build.py` | 64-image scale-ablation build (1024² canvas) |
| `phase2_noshadow_build.py` | 16-image shadow-ablation build |

Run any of the build scripts from the `compositor/` directory: `python phase2_build.py`. Output lands under `outputs/synthetic/<phase>/` with both images and labels.

### Prompts & hero assets

- `inputs/prompts/hero-instances.json` — 3 SDXL hero objects (green apple, brown box, white mug). Only the apple has been used for composites so far.
- `inputs/prompts/backgrounds.json` — 4 SDXL neutral surfaces (wood, concrete, cloth, marble). All in the `backgrounds/` pool directory.
- `inputs/prompts/dense-count.json` — original aspirational-count prompts (v1, pre-density-descriptor).
- `inputs/prompts/dense-count-v2.json` — density-descriptor prompts that work around SDXL's inability to hit exact counts. Used for the early SDXL-only generation phase (superseded by the compositor for exact-count work).

## Generate

### SDXL hero instances and backgrounds

```bash
# From style-dataset-lab repo root, with ComfyUI running at 127.0.0.1:8188
node bin/sdlab.js generate inputs/prompts/hero-instances.json --project ai-eye-test
node bin/sdlab.js generate inputs/prompts/backgrounds.json --project ai-eye-test
cp outputs/candidates/bg_*.png backgrounds/   # copy backgrounds into the pool dir
```

### Compositor builds (exact-count datasets)

```bash
cd compositor/
python phase2_build.py           # 96 images at 2048² — ~50s
python phase2b_build.py          # 64 images at 1024² (scale ablation) — ~10s
python phase2_noshadow_build.py  # 16 n=100 images, shadows off — ~10s
```

All three produce `manifest.json` + per-image labels under `outputs/synthetic/<phase>/`.

### Consumed by the eval harness

The eval project at `F:/AI/ai-eyes-mcp/evals/opus_4_7_vision/` loads from `outputs/synthetic/phase2/manifest.json` (and phase2b). See `datasets.py::_load_manifest_dataset` for the loader shape — copy that pattern if building a new consumer.

## Eval results linked from this project

Full analyses in `F:/AI/ai-eyes-mcp/evals/opus_4_7_vision/results/`:

| Analysis | Focus |
|---|---|
| `README.md` | Consolidated top-level summary (10 findings) |
| `ANALYSIS_2026-04-16.md` | Phase 1 + resolution curve + resize-method + interventions |
| `PHASE2_ANALYSIS_2026-04-16.md` | Phase 2 at n=96 |
| `PHASE2_COMBINED_ANALYSIS_2026-04-16.md` | + shadow + Phase 2b scale ablation |
| `CROSSMODEL_ANALYSIS_2026-04-16.md` | Opus 4.7 / GPT-4o / Gemini 2.5 Pro |
| `TOOLLOOP_ANALYSIS_2026-04-16.md` | Agentic crop-zoom intervention (+64% MAE recovery) |

## Known issues and gotchas

### SDXL cannot produce exact counts
Early runs showed SDXL systematically generates 2–7× more objects than prompted, and **inverts density adjectives** ("sparse" → packed, "handful" → dense). This is why we moved to programmatic composition for exact-count work. Hero-instance SDXL (one object centered) works reliably.

### `cv2.seamlessClone(MIXED_CLONE)` destroys object color on textured backgrounds
First Phase 2 build used MIXED_CLONE per the research-swarm recommendation. Apples on wood-grain acquired the wood coloration and became nearly invisible — n=100 looked like a wood texture, not 100 apples. **Use alpha paste + drop shadows.** Documented in DATASET_CARD.md. `cv2.NORMAL_CLONE` is untested and might give seam-softening without color destruction — worth 5 minutes of smoke testing.

### Existing `scripts/generate.js` does not support HiRes fix
The `project.json` declares a `hires_fix` block targeting 3072px long edge, but `lib/brief-compiler.js` doesn't render HiRes nodes. Current Phase 2 compositor outputs are 2048² native via SDXL → rembg → PIL compositor, bypassing HiRes entirely. If you want true 3072px native content for resolution testing above 2048, either patch the generator or upscale via external tools.

### Eval API gotchas (hit during the 2026-04-16 session)
Documented in `~/.claude/projects/F--AI/memory/feedback_vlm_api_gotchas.md`. Briefly:
- Opus 4.7 rejects `temperature` parameter
- Anthropic API caps base64 at 5 MB (need JPEG fallback for dense 2048²)
- Gemini wraps JSON in markdown fences + is verbose (need `max_tokens ≥1024` or tolerant regex)
- GPT-5 needs `max_tokens ≥2048` for reasoning headroom
- GPT-4o's self-reported confidence is flat (~0.97) — don't use it
- Windows default `write_text()` is cp1252 — use `encoding="utf-8"` explicitly

## Natural next work

1. **Swap hero class** — `phase2_build.py` is one line from generating a full 96-image box or mug dataset. Validates cross-class signal.
2. **Populate `fine-detail` or `labeled-grid`** — the compositor patterns generalize; those two subcategories are the easiest to author next because they can use the same `BackgroundPool` pattern with different hero classes.
3. **Test `cv2.NORMAL_CLONE`** — 5-minute smoke before dismissing Poisson blending entirely.
4. **Document snapshot/export path** — we never exercised `sdlab snapshot` or `sdlab export` against ai-eye-test because the eval harness reads manifests directly. A formal export step would make the dataset shippable as an external artifact (HuggingFace, etc).

## File index

```
projects/ai-eye-test/
├── README.md                         (this file)
├── project.json                      (sdlab config)
├── lanes.json                        (8 subcategories)
├── constitution.json                 (7 TST-* rules)
├── rubric.json                       (6 scoring dimensions)
├── terminology.json                  (synonym groups)
├── inputs/
│   └── prompts/
│       ├── hero-instances.json       (3 single-object prompts)
│       ├── backgrounds.json          (4 neutral surfaces)
│       ├── dense-count.json          (v1 aspirational)
│       └── dense-count-v2.json       (density descriptors)
├── backgrounds/                      (4 PNG backgrounds for the compositor pool)
├── compositor/                       (Python — primary tool)
│   ├── compositor.py
│   ├── test_compositor.py
│   ├── phase2.py
│   ├── test_phase2.py
│   ├── phase1_smoke.py
│   ├── phase2_build.py
│   ├── phase2b_build.py
│   └── phase2_noshadow_build.py
├── outputs/
│   ├── candidates/                   (SDXL outputs — heroes + backgrounds)
│   ├── cutouts/                      (rembg-extracted RGBA)
│   ├── labels-smoke.json             (v1 SDXL batch labels)
│   ├── labels-smoke-v2.json          (v2 SDXL batch labels)
│   └── synthetic/
│       ├── phase1/                   (4 images)
│       ├── phase2/                   (96 images + manifest + DATASET_CARD)
│       ├── phase2b/                  (64 images + manifest)
│       └── phase2_noshadow/          (16 images + manifest)
├── records/                          (sdlab generation records)
├── batches/, runs/                   (empty — reserved for multi-wave runs)
└── workflows/profiles/
    └── hires-neutral-3072.json       (declarative HiRes profile — not wired)
```
