---
title: Reference
description: CLI commands, config files, and pipeline scripts.
sidebar:
  order: 3
---

Style Dataset Lab v2.1 ships the `sdlab` CLI, 12 shared library modules, and pipeline scripts. All commands accept `--project <name>` to target a project under `projects/`. The default is `star-freight`. The deprecated `--game` flag still works with a warning.

## CLI Commands

### sdlab init

Scaffold a new project from a domain template.

```bash
sdlab init <project-name> [--domain <domain>]
sdlab init my-project --domain character-design
sdlab init                                       # list available domains
```

### sdlab project doctor

Validate project config completeness and correctness.

```bash
sdlab project doctor --project <name>
```

### sdlab generate

Drive ComfyUI to produce candidate images from a prompt pack.

```bash
sdlab generate <prompt-pack-path> --project <name> [--dry-run]
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

## Dataset Commands

### sdlab snapshot

Create, list, show, and diff frozen dataset snapshots.

```bash
sdlab snapshot create [--profile <name>] [--project <name>]
sdlab snapshot list [--project <name>]
sdlab snapshot show <snapshot-id> [--project <name>]
sdlab snapshot diff <id-a> <id-b> [--project <name>]
```

### sdlab eligibility

Audit training eligibility for all project records.

```bash
sdlab eligibility audit [--profile <name>] [--project <name>]
```

### sdlab split

Build, list, show, and audit dataset splits.

```bash
sdlab split build [--snapshot <id>] [--profile <name>] [--project <name>]
sdlab split list [--project <name>]
sdlab split show <split-id> [--project <name>]
sdlab split audit <split-id> [--project <name>]
```

### sdlab card

Generate dataset cards (markdown + JSON twin).

```bash
sdlab card generate [--snapshot <id>] [--split <id>] [--project <name>]
```

### sdlab export

Build and list versioned export packages.

```bash
sdlab export build [--snapshot <id>] [--split <id>] [--profile <name>] [--copy] [--project <name>]
sdlab export list [--project <name>]
```

Use `--copy` to copy images instead of symlinking them.

### sdlab eval-pack

Build and inspect canon-aware eval packs.

```bash
sdlab eval-pack build [--project <name>]
sdlab eval-pack list [--project <name>]
sdlab eval-pack show <eval-id> [--project <name>]
```

See [Dataset Workflow](./dataset-workflow/) for the full end-to-end walkthrough.

---

## Training Commands

### sdlab training-profile

List and inspect training profiles.

```bash
sdlab training-profile list [--project <name>]
sdlab training-profile show <profile-id> [--project <name>]
```

### sdlab training-manifest

Create, validate, and inspect frozen training contracts.

```bash
sdlab training-manifest create --export <id> --profile <id> [--adapter <target>] [--base-model <name>] [--project <name>]
sdlab training-manifest validate <manifest-id> [--project <name>]
sdlab training-manifest show <manifest-id> [--project <name>]
sdlab training-manifest list [--project <name>]
```

### sdlab training-package

Build trainer-ready packages from manifests.

```bash
sdlab training-package build --manifest <id> [--adapter <target>] [--copy] [--project <name>]
sdlab training-package show <package-id> [--project <name>]
sdlab training-package list [--project <name>]
```

Available adapters: `generic-image-caption`, `diffusers-lora`.

### sdlab eval-run

Score generated outputs against eval packs.

```bash
sdlab eval-run create --manifest <id> --eval-pack <id> [--project <name>]
sdlab eval-run score <eval-run-id> --outputs <path> [--project <name>]
sdlab eval-run show <eval-run-id> [--project <name>]
sdlab eval-run list [--project <name>]
```

### sdlab implementation-pack

Build implementation example packs.

```bash
sdlab implementation-pack build --manifest <id> [--project <name>]
sdlab implementation-pack show <impl-id> [--project <name>]
sdlab implementation-pack list [--project <name>]
```

### sdlab reingest

Re-ingest generated outputs as new project records.

```bash
sdlab reingest generated --source <dir> --manifest <id> [--dry-run] [--project <name>]
sdlab reingest audit [--project <name>]
```

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
