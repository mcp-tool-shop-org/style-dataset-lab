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

A prompt pack is a JSON file in `games/<name>/inputs/prompts/` that defines subjects, variations, and generation defaults. All scripts accept `--game <name>` to target a specific game (defaults to `star-freight`).

```bash
# Preview what would be generated (no ComfyUI calls)
npm run generate -- --game star-freight inputs/prompts/wave1.json --dry-run

# Generate for real
npm run generate -- --game star-freight inputs/prompts/wave1.json
```

Each generated image lands in `games/star-freight/outputs/candidates/` with a matching record in `games/star-freight/records/`. The record captures full provenance: checkpoint, LoRA, seed, steps, cfg, sampler, scheduler, resolution, and the exact prompt used.

## Curate

Once you have candidates, curate them one at a time:

```bash
# List uncurated candidates
npm run curate -- --game star-freight --list

# Approve with per-dimension scores
npm run curate -- --game star-freight wave1_compact_officer_s42 approved \
  "Clean silhouette, correct palette, good material read" \
  --scores silhouette:0.9,palette:0.85,material:0.8,faction:0.9

# Reject with failure modes
npm run curate -- --game star-freight wave1_compact_officer_s43 rejected \
  "Too clean, photorealistic rendering, no wear" \
  --failures too_clean,photorealistic
```

Curation moves the image from `outputs/candidates/` to `outputs/approved/`, `outputs/rejected/`, or `outputs/borderline/` within the game directory, and writes the judgment into the record.

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
# Bind all records for a game
npm run canon-bind -- --game star-freight

# Preview without writing
npm run canon-bind -- --game star-freight --dry-run

# Print coverage stats
npm run canon-bind -- --game star-freight --stats
```

Each record gets `canon.assertions` -- an array of rule citations with pass/fail/partial verdicts and one-line rationale.

## Export training data

Use `repo-dataset` to produce training data from your curated, canon-bound records. Point it at the specific game directory:

```bash
# Generate TRL-format training data
repo-dataset visual generate ./games/star-freight --format trl --output games/star-freight/exports

# Inspect what the scanner found
repo-dataset visual inspect ./games/star-freight

# Validate the output
repo-dataset visual validate games/star-freight/exports/dataset.jsonl
```

The export produces classification, preference, and critique training units depending on the judgments and comparisons in your dataset.

## Adding a new game

Create the directory structure for your new game and write its canon files:

```bash
mkdir -p games/my-game/{canon,records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
```

Then write `games/my-game/canon/constitution.md` and `games/my-game/canon/review-rubric.md` to define your style rules. Once the canon is in place, use `--game my-game` with all scripts:

```bash
npm run generate -- --game my-game inputs/prompts/wave1.json
npm run curate -- --game my-game <id> approved "explanation"
npm run canon-bind -- --game my-game
```
