---
title: Getting Started
description: Install the pipeline, scaffold a project, generate, curate, and export.
sidebar:
  order: 1
---

## Prerequisites

You need three things running before you start:

1. **ComfyUI** -- a local Stable Diffusion backend. Install from [github.com/comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI). Style Dataset Lab drives it over HTTP on `localhost:8188`.

2. **Node.js 20+** -- all scripts are ESM JavaScript. No build step, no TypeScript compilation.

3. **repo-dataset** (optional, for export) -- the `@mcptoolshop/repo-dataset` CLI reads your records and images to produce training data. Install from [github.com/mcp-tool-shop-org/repo-dataset](https://github.com/mcp-tool-shop-org/repo-dataset).

### Model weights

The default generation setup uses an SDXL checkpoint and a style LoRA. Configure these in your project's `project.json` under `defaults.checkpoint` and `defaults.loras`. Place model files in your ComfyUI `models/checkpoints/` and `models/loras/` directories.

## Install

```bash
# Install globally for the sdlab CLI
npm install -g @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
```

## Scaffold a project

```bash
# Create a project from a domain template
sdlab init my-project --domain character-design

# See available domains
sdlab init
```

Available domains: `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech`, or omit `--domain` for a generic starter.

This creates `projects/my-project/` with config files, canon templates, directory structure, and a starter prompt pack.

## Validate the project

```bash
sdlab project doctor --project my-project
```

Doctor checks config files, lane patterns, rubric dimensions, constitution rules, and directory structure. Fix any failures before generating.

## Customize your canon

Edit the config files in your project root:

- **`constitution.json`** -- add or modify rules that define your visual law
- **`lanes.json`** -- define subject categories (portrait, full_body, etc.)
- **`rubric.json`** -- set scoring dimensions and approval thresholds
- **`terminology.json`** -- define style groups/factions with detection patterns
- **`canon/constitution.md`** -- human-readable style rules for the team

## Start ComfyUI

```bash
cd /path/to/ComfyUI
python main.py --listen 127.0.0.1 --port 8188
```

Verify it is running:

```bash
curl http://127.0.0.1:8188/system_stats
```

## Generate your first wave

Edit `projects/my-project/inputs/prompts/example-wave.json` with your subjects, style prefix, and generation defaults. Then:

```bash
# Preview what would be generated (no ComfyUI calls)
sdlab generate inputs/prompts/example-wave.json --project my-project --dry-run

# Generate for real
sdlab generate inputs/prompts/example-wave.json --project my-project
```

Each generated image lands in `outputs/candidates/` with a matching record in `records/`. The record captures full provenance: checkpoint, LoRA, seed, steps, cfg, sampler, scheduler, resolution, and the exact prompt used.

## Curate

Once you have candidates, curate them:

```bash
# List uncurated candidates
sdlab curate --list --project my-project

# Approve with per-dimension scores
sdlab curate my_subject_v1 approved "Clean proportions, good gesture" \
  --scores proportion_accuracy:0.9,gesture_clarity:0.85 --project my-project

# Reject with failure modes
sdlab curate my_subject_v2 rejected "Broken anatomy, stiff pose" \
  --failures broken_anatomy,stiff_pose --project my-project
```

Curation moves the image from `outputs/candidates/` to `outputs/approved/` (or `rejected/`, `borderline/`) and writes the judgment into the record.

## Bind to canon

After curation, bind records to constitution rules:

```bash
# Bind all curated records
sdlab bind --project my-project

# Preview without writing
sdlab bind --project my-project --dry-run

# Print coverage stats
sdlab bind --project my-project --stats
```

Each record gets `canon.assertions` -- an array of rule citations with pass/fail/partial verdicts and rationale strings.

## Export training data

Use `repo-dataset` to produce training data from your curated, canon-bound records:

```bash
repo-dataset visual generate ./projects/my-project --format trl
repo-dataset visual inspect ./projects/my-project
```

## Explore the Star Freight example

If you cloned the repo, the Star Freight project has 1,182 records ready to explore:

```bash
sdlab bind --stats --project star-freight
sdlab project doctor --project star-freight
```
