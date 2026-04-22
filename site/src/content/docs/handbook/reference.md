---
title: Reference
description: CLI commands, config files, and pipeline scripts.
sidebar:
  order: 3
---

Style Dataset Lab v3.0.0 ships the `sdlab` CLI, 12 shared library modules, and pipeline scripts. All commands accept `--project <name>` to target a project under `projects/`. The default is `star-freight`.

> **Legacy flag.** The `--game <name>` flag is a deprecated alias for `--project <name>`. It still works with a warning and will be removed in v4.

## CLI Commands

### sdlab init

Scaffold a new project from a domain template.

```bash
sdlab init <project-name> [--domain <domain>]
sdlab init my-project --domain character-design
sdlab init                                       # list available domains
```

Available domains: `generic`, `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech`.

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
| `--project <name>` | `star-freight` | Target project directory under `projects/` |
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

**Outputs:** Images to `projects/<name>/outputs/candidates/`, records to `projects/<name>/records/`.

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI server URL |

---

### sdlab curate

Move a candidate to approved/rejected/borderline and record the judgment.

```bash
sdlab curate <asset_id> <status> <explanation> [options] --project <name>
sdlab curate --list --project <name>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `asset_id` | yes | Record ID (filename without extension) |
| `status` | yes | `approved`, `rejected`, or `borderline` |
| `explanation` | yes | Free-text rationale for the judgment |

| Flag | Default | Description |
|------|---------|-------------|
| `--project <name>` | `star-freight` | Target project directory under `projects/` |
| `--list` | -- | Show uncurated candidates (no other args needed) |
| `--scores <k:v,...>` | -- | Per-dimension scores, e.g. `silhouette:0.9,palette:0.8` |
| `--failures <f1,f2>` | -- | Named failure modes, e.g. `too_clean,wrong_material` |
| `--notes <text>` | -- | Improvement notes for borderline or rejected images |

**Behavior:** Updates the record's `judgment` block, moves the image file from `outputs/candidates/` to the status directory within the project folder. The record is written before the file move to prevent orphaned images.

---

### sdlab compare

Record a pairwise A-vs-B style comparison.

```bash
sdlab compare <asset_a_id> <asset_b_id> <winner> <reasoning> --project <name>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `asset_a_id` | yes | Record ID of the first image |
| `asset_b_id` | yes | Record ID of the second image |
| `winner` | yes | `a`, `b`, or `tie` |
| `reasoning` | yes | Why the winner is better |

| Flag | Default | Description |
|------|---------|-------------|
| `--project <name>` | `star-freight` | Target project directory under `projects/` |
| `--scores <k:v/v,...>` | -- | Per-dimension comparison, e.g. `silhouette:0.9/0.6` |

**Outputs:** Comparison record to `projects/<name>/comparisons/`. Used by repo-dataset to produce preference training pairs.

---

### sdlab bind (canon-bind)

Populate canon assertions in all records based on judgment scores and failure modes.

```bash
sdlab bind --project <name> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--project <name>` | `star-freight` | Target project directory under `projects/` |
| `--dry-run` | -- | Preview bindings without writing to records |
| `--stats` | -- | Print coverage statistics |

**Behavior:** For each curated record, maps judgment scores and failure modes to constitution rules (e.g., `RND-001`, `MAT-002`) and writes `canon.assertions` with pass/fail/partial verdicts. Each assertion includes the rule ID, category, description, and a one-line rationale derived from the scores.

---

### sdlab painterly

Post-process images through an img2img painterly pass via ComfyUI.

```bash
sdlab painterly --project <name> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--project <name>` | `star-freight` | Target project directory under `projects/` |
| `--source <dir>` | `outputs/approved` | Source directory for images (relative to project dir) |
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

**Outputs:** Processed images to `projects/<name>/outputs/painterly/`.

---

### sdlab generate:identity

Generate named-subject identity images with lineage tracking.

```bash
sdlab generate:identity <identity-packet-path> --project <name> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--project <name>` | `star-freight` | Target project directory under `projects/` |
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

### sdlab generate:controlnet

Generate candidates using ControlNet (pose/depth-guided generation).

```bash
sdlab generate:controlnet <prompt-pack-path> --project <name> [options]
```

### sdlab generate:ipadapter

Generate candidates using IP-Adapter (reference-image-driven generation).

```bash
sdlab generate:ipadapter <prompt-pack-path> --project <name> [options]
```

### sdlab migrate / sdlab project migrate

Migrate records from older schema versions to the current format.

```bash
sdlab migrate --project <name> [--dry-run]
sdlab project migrate --project <name> [--dry-run]
```

### sdlab painterly:test

Test the painterly pipeline on a single image before running a full batch.

```bash
sdlab painterly:test --project <name>
```

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
sdlab reingest selected --selection <id> [--project <name>]
sdlab reingest audit [--project <name>]
```

---

## Production Loop Commands

### sdlab workflow

List and inspect workflow profiles.

```bash
sdlab workflow list --project <name>
sdlab workflow show <workflow-id> --project <name>
```

### sdlab brief

Compile briefs from workflow profiles and project truth.

```bash
sdlab brief compile --workflow <id> [--subject <id>] --project <name>
sdlab brief show <brief-id> --project <name>
```

### sdlab run

Execute briefs through ComfyUI.

```bash
sdlab run generate --brief <id> --project <name>
sdlab run show <run-id> --project <name>
sdlab run list --project <name>
```

### sdlab critique

Critique a run and optionally show the saved critique.

```bash
sdlab critique --run <id> --project <name>
sdlab critique show --run <id> --project <name>
```

### sdlab refine

Generate a refined next-pass brief from a run pick.

```bash
sdlab refine --run <id> --pick <file> [--push "<guidance>"] --project <name>
```

### sdlab batch

Coordinated multi-slot production.

```bash
sdlab batch generate --mode <id> [--subject <id>] --project <name>
sdlab batch show [batch-id] --project <name>
sdlab batch sheet <batch-id> --project <name>
```

### sdlab select / sdlab selection

Select approved outputs and view selections.

```bash
sdlab select --run <id> --approve <files> --reason "<why>" --project <name>
sdlab select --batch <id> --approve slot_a:<file>,slot_b:<file> --project <name>
sdlab selection show [selection-id] --project <name>
```

---

## Export (via repo-dataset)

Export is handled by the separate `@mcptoolshop/repo-dataset` CLI. Point it at the specific project directory:

```bash
# Generate training data
repo-dataset visual generate ./projects/star-freight --format trl --output projects/star-freight/exports

# With embedded images (base64 in JSONL)
repo-dataset visual generate ./projects/star-freight --format trl --embed

# Inspect scanner results
repo-dataset visual inspect ./projects/star-freight

# Validate output
repo-dataset visual validate projects/star-freight/exports/dataset.jsonl
```

Supported formats: TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, OpenAI, DPO, ORPO, KTO.

---

## Global Options

| Flag | Description |
|------|-------------|
| `--project <name>` | Project to operate on (default: `star-freight`) |
| `--game <name>` | Deprecated alias for `--project`. Emits a warning. Removed in v4. |
| `--debug` | Show stack traces on error |
| `--verbose` | Verbose output |
| `--quiet` | Suppress non-essential output |
| `--dry-run` | Preview changes without writing (where supported) |
| `--help` | Show help |
