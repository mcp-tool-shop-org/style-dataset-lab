---
title: Reference
description: All 13 pipeline scripts, templates, flags, and arguments.
sidebar:
  order: 2
---

Style Dataset Lab v1.2.0 ships 13 scripts and a `templates/` directory. All scripts accept `--game <name>` to target a specific game directory under `games/`. The default is `star-freight`.

## Templates

The `templates/` directory provides a blank starting point for new games:

| Path | Purpose |
|------|---------|
| `templates/canon/constitution.md` | Blank style constitution -- fill in your rules |
| `templates/canon/review-rubric.md` | Blank review rubric -- define scoring criteria |
| `templates/inputs/prompts/example-wave.json` | Example prompt pack structure |

Copy these into a new `games/<name>/` directory to bootstrap a game without writing boilerplate from scratch.

## Scripts

## generate.js

Drive ComfyUI to produce candidate images from a prompt pack.

```bash
node scripts/generate.js --game <name> <prompt-pack-path> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--game <name>` | `star-freight` | Target game directory under `games/` |
| `--dry-run` | -- | Print what would be generated without calling ComfyUI |
| `--subject <name>` | all | Only generate for one subject |
| `--seeds <n>` | 3 | Number of random seeds per subject-variation pair |

**Prompt pack format** (`inputs/prompts/*.json`):

```json
{
  "defaults": {
    "checkpoint": "dreamshaperXL_v21TurboDPMSDE.safetensors",
    "loras": [{ "name": "classipeintxl_v21.safetensors", "weight": 1.0 }],
    "steps": 8, "cfg": 2.0,
    "sampler": "dpmpp_sde", "scheduler": "karras",
    "width": 1024, "height": 1024,
    "negative_prompt": "photorealistic, photograph, 3d render..."
  },
  "subjects": [
    {
      "id": "compact_officer",
      "prompt": "concept art of a Compact military officer...",
      "variations": [
        { "suffix": "bridge", "prompt_append": "on the bridge..." }
      ]
    }
  ]
}
```

**Outputs:** Images to `games/<name>/outputs/candidates/`, records to `games/<name>/records/`.

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI server URL |

---

## curate.js

Move a candidate to approved/rejected/borderline and record the judgment.

```bash
node scripts/curate.js --game <name> <asset_id> <status> <explanation> [options]
node scripts/curate.js --game <name> --list
```

| Argument | Required | Description |
|----------|----------|-------------|
| `asset_id` | yes | Record ID (filename without extension) |
| `status` | yes | `approved`, `rejected`, or `borderline` |
| `explanation` | yes | Free-text rationale for the judgment |

| Flag | Default | Description |
|------|---------|-------------|
| `--game <name>` | `star-freight` | Target game directory under `games/` |
| `--list` | -- | Show uncurated candidates (no other args needed) |
| `--scores <k:v,...>` | -- | Per-dimension scores, e.g. `silhouette:0.9,palette:0.8` |
| `--failures <f1,f2>` | -- | Named failure modes, e.g. `too_clean,wrong_material` |
| `--notes <text>` | -- | Improvement notes for borderline or rejected images |

**Behavior:** Updates the record's `judgment` block, moves the image file from `outputs/candidates/` to the status directory within the game folder. The record is written before the file move to prevent orphaned images.

---

## compare.js

Record a pairwise A-vs-B style comparison.

```bash
node scripts/compare.js --game <name> <asset_a_id> <asset_b_id> <winner> <reasoning>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `asset_a_id` | yes | Record ID of the first image |
| `asset_b_id` | yes | Record ID of the second image |
| `winner` | yes | `a`, `b`, or `tie` |
| `reasoning` | yes | Why the winner is better |

| Flag | Default | Description |
|------|---------|-------------|
| `--game <name>` | `star-freight` | Target game directory under `games/` |
| `--scores <k:v/v,...>` | -- | Per-dimension comparison, e.g. `silhouette:0.9/0.6` |

**Outputs:** Comparison record to `games/<name>/comparisons/`. Used by repo-dataset to produce preference training pairs.

---

## canon-bind.js

Populate canon assertions in all records based on judgment scores and failure modes.

```bash
node scripts/canon-bind.js --game <name> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--game <name>` | `star-freight` | Target game directory under `games/` |
| `--dry-run` | -- | Preview bindings without writing to records |
| `--stats` | -- | Print coverage statistics |

**Behavior:** For each curated record, maps judgment scores and failure modes to constitution rules (e.g., `RND-001`, `MAT-002`) and writes `canon.assertions` with pass/fail/partial verdicts. Each assertion includes the rule ID, category, description, and a one-line rationale derived from the scores.

---

## painterly.js

Post-process images through an img2img painterly pass via ComfyUI.

```bash
node scripts/painterly.js --game <name> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--game <name>` | `star-freight` | Target game directory under `games/` |
| `--source <dir>` | `outputs/approved` | Source directory for images (relative to game dir) |
| `--limit <n>` | all | Maximum number of images to process |
| `--offset <n>` | `0` | Skip the first n images |
| `--dry-run` | -- | Preview without processing |

**Defaults:**

| Parameter | Value |
|-----------|-------|
| Denoise | 0.50 |
| Steps | 10 |
| CFG | 2.5 |
| Seed | 42 (fixed for reproducibility) |

**Outputs:** Processed images to `games/<name>/outputs/painterly/`.

---

## generate-identity.js

Generate named-subject identity images with lineage tracking.

```bash
node scripts/generate-identity.js --game <name> <identity-packet-path> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--game <name>` | `star-freight` | Target game directory under `games/` |
| `--dry-run` | -- | Preview without generating |
| `--subject <name>` | all | Only generate for one subject |
| `--seeds <n>` | `3` | Discovery seeds per shot |
| `--phase <mode>` | `discovery` | Generation phase: `discovery` or `follow_on` |
| `--anchor <path>` | -- | Anchor source image (required for `follow_on`) |
| `--denoise <n>` | `0.38` | Denoise strength for `follow_on` phase |

**Phases:**

1. **Discovery** -- txt2img from prompt, multiple seeds. No prior image input.
2. **Follow-on** -- img2img from anchor image. Requires `--anchor` and `--denoise`. Anchor curation happens between phases (manual step).

**Identity packet format** (`inputs/identity-packets/*.json`): Defines subjects with identity locks, shot intents, and lineage metadata per `canon/identity-gates.md`.

**Record extensions:** Adds `identity` block (subject name, faction, role, view type, shot type) and `lineage` block (generation phase, anchor references, persistence scores).

---

## Export (via repo-dataset)

Export is handled by the separate `@mcptoolshop/repo-dataset` CLI. Point it at the specific game directory:

```bash
# Generate training data
repo-dataset visual generate ./games/star-freight --format trl --output games/star-freight/exports

# With embedded images (base64 in JSONL)
repo-dataset visual generate ./games/star-freight --format trl --embed

# Inspect scanner results
repo-dataset visual inspect ./games/star-freight

# Validate output
repo-dataset visual validate games/star-freight/exports/dataset.jsonl
```

Supported formats: TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, OpenAI, DPO, ORPO, KTO.

---

## Additional scripts

### generate-controlnet.js

Generate candidates using ControlNet (pose/depth-guided generation).

```bash
node scripts/generate-controlnet.js --game <name> <prompt-pack-path> [options]
```

### generate-ipadapter.js

Generate candidates using IP-Adapter (reference-image-driven generation).

```bash
node scripts/generate-ipadapter.js --game <name> <prompt-pack-path> [options]
```

### bulk-curate-wave2-5.js / bulk-curate-waves11-18.js

Batch curation scripts for processing multiple assets from specific waves.

### curate-wave25.js

Specialized curation for wave 25 (alien species) with species-specific scoring.

### migrate-records.js

Migrate records from older schema versions to the current format.

```bash
node scripts/migrate-records.js --game <name> [--dry-run]
```

### painterly-test.js

Test the painterly pipeline on a single image before running a full batch.
