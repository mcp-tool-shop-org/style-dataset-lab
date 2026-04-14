---
title: Getting Started
description: Prerequisites, first generation, first curation, and first export.
sidebar:
  order: 1
---

## Prerequisites

You need three things running before you start:

1. **ComfyUI** -- a local Stable Diffusion backend. Install from [github.com/comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI). Style Dataset Lab drives it over HTTP on `localhost:8188`.

2. **Node.js 20+** -- all scripts are ESM JavaScript. No build step, no TypeScript compilation.

3. **repo-dataset** (optional, for export) -- the `@mcptoolshop/repo-dataset` CLI reads your records and images to produce training data. Install from [github.com/mcp-tool-shop-org/repo-dataset](https://github.com/mcp-tool-shop-org/repo-dataset).

### Model weights

The default generation setup uses:

| Asset | Purpose |
|-------|---------|
| `dreamshaperXL_v21TurboDPMSDE.safetensors` | SDXL checkpoint (turbo variant for fast iteration) |
| `classipeintxl_v21.safetensors` | LoRA for painterly style shift |

Place these in your ComfyUI `models/checkpoints/` and `models/loras/` directories respectively.

## Clone the repo

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab.git
cd style-dataset-lab
```

No `npm install` needed for the core scripts -- they use only Node built-ins and `fetch`.

## Start ComfyUI

```bash
cd /path/to/ComfyUI
python main.py --listen 127.0.0.1 --port 8188
```

Verify it is running:

```bash
curl http://127.0.0.1:8188/system_stats
```

You should get a JSON response with GPU and queue information.

## Generate your first wave

A prompt pack is a JSON file in `inputs/prompts/` that defines subjects, variations, and generation defaults. To generate images from one:

```bash
# Preview what would be generated (no ComfyUI calls)
node scripts/generate.js inputs/prompts/wave1.json --dry-run

# Generate for real
node scripts/generate.js inputs/prompts/wave1.json
```

Each generated image lands in `outputs/candidates/` with a matching record in `records/`. The record captures full provenance: checkpoint, LoRA, seed, steps, cfg, sampler, scheduler, resolution, and the exact prompt used.

## Curate

Once you have candidates, curate them one at a time:

```bash
# List uncurated candidates
node scripts/curate.js --list

# Approve with per-dimension scores
node scripts/curate.js wave1_compact_officer_s42 approved \
  "Clean silhouette, correct palette, good material read" \
  --scores silhouette:0.9,palette:0.85,material:0.8,faction:0.9

# Reject with failure modes
node scripts/curate.js wave1_compact_officer_s43 rejected \
  "Too clean, photorealistic rendering, no wear" \
  --failures too_clean,photorealistic
```

Curation moves the image from `outputs/candidates/` to `outputs/approved/`, `outputs/rejected/`, or `outputs/borderline/` and writes the judgment into the record.

### Scoring dimensions

Each image is scored on 8 dimensions (0.0 to 1.0):

| Dimension | What it measures |
|-----------|-----------------|
| `silhouette_clarity` | Faction-identifiable from outline at 64px |
| `palette_adherence` | Correct faction colors at correct ratios |
| `material_fidelity` | Surfaces read as the faction's material vocabulary |
| `faction_read` | Can you tell which faction at a glance |
| `wear_level` | Appropriate aging and damage for the faction |
| `style_consistency` | Matches painterly target, not photo or 3D |
| `clothing_logic` | Layers follow faction construction rules |
| `composition` | Full body, centered, correct fill ratio |

**Approval threshold:** all dimensions >= 0.6, average >= 0.7.

## Bind to canon

After curation, run the canon binding pass to link each record to specific constitution rules:

```bash
# Bind all records
node scripts/canon-bind.js

# Preview without writing
node scripts/canon-bind.js --dry-run

# Print coverage stats
node scripts/canon-bind.js --stats
```

Each record gets `canon.assertions` -- an array of rule citations with pass/fail/partial verdicts and one-line rationale.

## Export training data

Use `repo-dataset` to produce training data from your curated, canon-bound records:

```bash
# Generate TRL-format training data
npx repo-dataset visual generate . --format trl --output exports

# Inspect what the scanner found
npx repo-dataset visual inspect .

# Validate the output
npx repo-dataset visual validate exports/dataset.jsonl
```

The export produces classification, preference, and critique training units depending on the judgments and comparisons in your dataset.
