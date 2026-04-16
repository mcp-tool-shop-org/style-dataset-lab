<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

Define visual canon. Curate approved work. Produce versioned datasets. Build training packages. Score outputs against canon. Re-ingest accepted results. Repeat.

## What this does

Style Dataset Lab is a production pipeline for visual datasets. It takes a project from written canon through curation, dataset packaging, model training preparation, evaluation, and back again as a closed loop.

Every asset in the system carries full provenance, canon-bound judgments, and per-dimension quality scores. Nothing is a label without a reason.

```
canon → curate → bind → snapshot → split → export → train → eval → reingest
```

## The artifacts

The pipeline produces seven first-class artifacts. Each is versioned, checksummed, and linked to its predecessors.

| Artifact | What it is |
|----------|-----------|
| **Snapshot** | Frozen, fingerprinted record selection. Every inclusion has an explicit reason trace. |
| **Split** | Leakage-safe train/val/test partition. Subject families never cross split boundaries. |
| **Export package** | Self-contained dataset: manifest, metadata, images, splits, dataset card, checksums. |
| **Eval pack** | Canon-aware test tasks: lane coverage, forbidden drift, anchor/gold, subject continuity. |
| **Training package** | Trainer-ready layout built by adapters. Same truth, different format. |
| **Eval scorecard** | Per-task pass/fail verdict from scoring generated outputs against eval packs. |
| **Implementation pack** | Prompt examples, known failures, subject continuity tests, re-ingest guide. |

## Quick start

```bash
npm install -g @mcptoolshop/style-dataset-lab

sdlab init my-project --domain character-design
sdlab project doctor --project my-project
```

Available domains: `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech`.

## End-to-end example

```bash
# 1. Curate and bind records to constitution rules
sdlab curate <id> approved "Strong silhouette, correct palette"
sdlab bind --project my-project

# 2. Produce a versioned dataset
sdlab snapshot create --project my-project
sdlab split build --project my-project
sdlab export build --project my-project

# 3. Build a training package
sdlab training-manifest create --profile character-style-lora
sdlab training-package build --project my-project

# 4. Evaluate and close the loop
sdlab eval-pack build --project my-project
sdlab eval-run create --project my-project
sdlab eval-run score <id> --outputs results.jsonl
sdlab reingest generated --source ./outputs --manifest <id>
```

## Project structure

Each project is self-contained under `projects/<name>/`:

```
project.json            Identity + generation defaults
constitution.json       Rules with rationale templates
lanes.json              Subject lanes with detection patterns
rubric.json             Scoring dimensions + thresholds
terminology.json        Group vocabulary + detection order
canon/                  Style constitution (markdown)
records/                Per-asset JSON (provenance + judgment + canon)
snapshots/              Frozen dataset snapshots
splits/                 Train/val/test partitions
exports/                Versioned export packages
eval-packs/             Canon-aware eval instruments
training/
  profiles/             What kind of model asset to produce
  manifests/            Frozen training contracts
  packages/             Trainer-ready layouts
  eval-runs/            Scored output evaluations
  implementations/      Usage examples + re-ingest guides
```

## Key properties

**Snapshots are frozen.** Once created, a snapshot never silently changes. The config fingerprint (SHA-256 of all project config files) proves reproducibility.

**Splits prevent leakage.** Records sharing a subject family (by identity name, lineage chain, or ID suffix) always land in the same partition. Lane balance is maintained across train/val/test.

**Manifests are immutable contracts.** A training manifest captures the exact export, split, profile, and config fingerprint. If anything changes, a new manifest is required.

**Adapters never mutate truth.** Trainer-specific adapters (`generic-image-caption`, `diffusers-lora`) transform layout but cannot add, remove, or reclassify records.

**Generated outputs re-enter through review.** Re-ingested work gets a new record with full provenance and must be curated and canon-bound like everything else. No bypass.

## Domain templates

Five starter templates with real production rules, lane definitions, and scoring rubrics:

| Domain | Lanes | Key concerns |
|--------|-------|-------------|
| **game-art** | character, environment, prop, UI, ship, interior, equipment | Silhouette at gameplay scale, faction read, wear/aging |
| **character-design** | portrait, full_body, turnaround, expression_sheet, action_pose | Proportions, costume logic, personality, gesture |
| **creature-design** | concept, orthographic, detail_study, action, scale_reference, habitat | Anatomy, evolutionary logic, silhouette distinction |
| **architecture** | exterior, interior, streetscape, structural_detail, ruin, landscape | Structure, material consistency, perspective, era |
| **vehicle-mech** | exterior, cockpit, component, schematic, silhouette_sheet, damage_variant | Mechanical logic, design language, access points |

## Downstream formats

`sdlab` defines and owns the dataset. Downstream format conversion is handled by [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet, and more. `repo-dataset` renders formats; it never decides inclusion.

## Star Freight

Clone the repo for a complete working example: 1,182 records, 5 factions, 7 lanes, 24 constitution rules, 2 training profiles.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight
sdlab split build --project star-freight
sdlab training-manifest create --profile character-style-lora --project star-freight
```

## Security

Local-only. Talks to ComfyUI on `localhost:8188`. No telemetry, no analytics, no external requests. Images stay on your GPU and filesystem.

## Requirements

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) running on localhost:8188
- SDXL-compatible checkpoint + style LoRA
- Node.js 20+

## License

MIT

---

Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
