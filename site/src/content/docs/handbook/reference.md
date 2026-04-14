---
title: Reference
description: All scripts with flags, arguments, and behavior.
sidebar:
  order: 2
---

## generate.js

Drive ComfyUI to produce candidate images from a prompt pack.

```bash
node scripts/generate.js <prompt-pack-path> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
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

**Outputs:** Images to `outputs/candidates/`, records to `records/`.

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI server URL |

---

## curate.js

Move a candidate to approved/rejected/borderline and record the judgment.

```bash
node scripts/curate.js <asset_id> <status> <explanation> [options]
node scripts/curate.js --list
```

| Argument | Required | Description |
|----------|----------|-------------|
| `asset_id` | yes | Record ID (filename without extension) |
| `status` | yes | `approved`, `rejected`, or `borderline` |
| `explanation` | yes | Free-text rationale for the judgment |

| Flag | Description |
|------|-------------|
| `--list` | Show uncurated candidates (no other args needed) |
| `--scores <k:v,...>` | Per-dimension scores, e.g. `silhouette:0.9,palette:0.8` |
| `--failures <f1,f2>` | Named failure modes, e.g. `too_clean,wrong_material` |
| `--notes <text>` | Improvement notes for borderline or rejected images |

**Behavior:** Updates the record's `judgment` block, moves the image file from `outputs/candidates/` to the status directory. The record is written before the file move to prevent orphaned images.

---

## compare.js

Record a pairwise A-vs-B style comparison.

```bash
node scripts/compare.js <asset_a_id> <asset_b_id> <winner> <reasoning>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `asset_a_id` | yes | Record ID of the first image |
| `asset_b_id` | yes | Record ID of the second image |
| `winner` | yes | `a`, `b`, or `tie` |
| `reasoning` | yes | Why the winner is better |

| Flag | Description |
|------|-------------|
| `--scores <k:v/v,...>` | Per-dimension comparison, e.g. `silhouette:0.9/0.6` |

**Outputs:** Comparison record to `comparisons/`. Used by repo-dataset to produce preference training pairs.

---

## canon-bind.js

Populate canon assertions in all records based on judgment scores and failure modes.

```bash
node scripts/canon-bind.js [options]
```

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview bindings without writing to records |
| `--stats` | Print coverage statistics |

**Behavior:** For each curated record, maps judgment scores and failure modes to constitution rules (e.g., `RND-001`, `MAT-002`) and writes `canon.assertions` with pass/fail/partial verdicts. Each assertion includes the rule ID, category, description, and a one-line rationale derived from the scores.

---

## painterly.js

Post-process images through an img2img painterly pass via ComfyUI.

```bash
node scripts/painterly.js [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--source <dir>` | `outputs/approved` | Source directory for images |
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

**Outputs:** Processed images to `outputs/painterly/`.

---

## generate-identity.js

Generate named-subject identity images with lineage tracking.

```bash
node scripts/generate-identity.js <identity-packet-path> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
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

Export is handled by the separate `@mcptoolshop/repo-dataset` CLI:

```bash
# Generate training data
npx repo-dataset visual generate . --format trl --output exports

# With embedded images (base64 in JSONL)
npx repo-dataset visual generate . --format trl --embed

# Inspect scanner results
npx repo-dataset visual inspect .

# Validate output
npx repo-dataset visual validate exports/dataset.jsonl
```

Supported formats: TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, OpenAI, DPO, ORPO, KTO.
