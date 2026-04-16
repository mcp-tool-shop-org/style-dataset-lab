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

Turn approved visual work into versioned, review-backed datasets, splits, export packages, and eval packs.

## What this is

A **visual canon and dataset production pipeline**. Define what your project looks like. Curate against constitution rules. Produce reproducible dataset packages with leakage-safe splits. Generate eval packs for future model verification.

The pipeline produces four artifacts:

| Artifact | What it is |
|----------|-----------|
| **Snapshot** | Frozen, fingerprinted selection of eligible records. Every inclusion has an explicit reason trace. |
| **Split** | Leakage-safe train/val/test partition. Records sharing a subject family always land in the same split. |
| **Export package** | Self-contained dataset: manifest, metadata, images, splits, dataset card, and checksums. |
| **Eval pack** | Canon-aware verification tasks: lane coverage, forbidden drift, anchor/gold, subject continuity. |

Every asset in the pipeline carries three things:

1. **Provenance** -- full generation history (checkpoint, LoRA, seed, sampler, cfg, timing)
2. **Canon binding** -- which constitution rules this asset passes, fails, or partially meets
3. **Quality judgment** -- approved/rejected/borderline with per-dimension scores

Works for game art, character design, creature design, architecture, vehicle/mech concepts, and any domain where visual production needs to stay on-model.

## Quick start

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

Available domains: `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech`, or `generic`.

## CLI

```bash
sdlab init <name> [--domain <domain>]     # Scaffold a new project
sdlab project doctor [--project <name>]   # Validate project config

sdlab generate <pack> [--project <name>]  # Generate candidates via ComfyUI
sdlab generate:identity <packet>          # Named-subject identity images
sdlab generate:controlnet                 # ControlNet-guided generation
sdlab generate:ipadapter                  # IP-Adapter reference-guided

sdlab curate <id> <status> <explanation>  # Record review judgment
sdlab compare <a> <b> <winner> <reason>   # Pairwise A-vs-B comparison
sdlab bind [--project <name>]             # Bind records to constitution rules
sdlab painterly [--project <name>]        # Post-processing style pass

sdlab snapshot create [--profile <name>]  # Create frozen dataset snapshot
sdlab snapshot list                       # List all snapshots
sdlab snapshot diff <a> <b>               # Compare two snapshots
sdlab eligibility audit                   # Audit record training eligibility
sdlab split build [--snapshot <id>]       # Build train/val/test split
sdlab split audit <id>                    # Audit split for leakage + balance
sdlab card generate                       # Generate dataset card (md + JSON)
sdlab export build [--snapshot <id>]      # Build versioned export package
sdlab eval-pack build                     # Build canon-aware eval pack

sdlab training-profile list               # List training profiles
sdlab training-manifest create            # Create frozen training contract
sdlab training-manifest validate <id>     # Validate manifest integrity
sdlab training-package build              # Build trainer-ready package
sdlab eval-run create                     # Create eval run
sdlab eval-run score <id> --outputs <p>   # Score against eval pack
sdlab implementation-pack build           # Build implementation examples
sdlab reingest generated --source <dir>   # Re-ingest generated outputs
sdlab reingest audit                      # Audit re-ingested records
```

All commands accept `--project <name>` (default: `star-freight`).

## Project model

Each project is a self-contained directory under `projects/` with its own canon, config, and data:

```
projects/
  my-project/
    project.json            Project identity + generation defaults
    constitution.json       Rules array with rationale templates
    lanes.json              Subject lanes with detection patterns
    rubric.json             Scoring dimensions + thresholds
    terminology.json        Group vocabulary + detection order
    canon/                  Style constitution (markdown)
    records/                Per-asset JSON (provenance + judgment + canon)
    inputs/prompts/         Prompt packs (JSON)
    outputs/                Generated images (gitignored)
    comparisons/            A-vs-B preference judgments
    snapshots/              Frozen dataset snapshots
    splits/                 Train/val/test partitions
    exports/                Versioned export packages
    eval-packs/             Canon-aware eval instruments
```

## Pipeline

```
canon → generate → curate → bind → snapshot → split → export → eval
  |        |          |        |        |         |        |       |
rules   ComfyUI   judgment  rules   frozen    subject  package  verify
                                    selection isolation
```

1. **Define canon** -- write your style constitution and review rubric
2. **Generate** -- ComfyUI produces candidates with full provenance
3. **Curate** -- approve/reject with per-dimension scores and failure modes
4. **Bind** -- link each asset to constitution rules with pass/fail/partial verdicts
5. **Snapshot** -- freeze eligible records into a deterministic, fingerprinted selection
6. **Split** -- partition into train/val/test with subject isolation and lane balance
7. **Export** -- build a self-contained package with manifest, metadata, images, and checksums
8. **Eval** -- generate canon-aware test instruments for model verification

Downstream format conversion (TRL, LLaVA, Parquet, etc.) is handled by [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset). `sdlab` owns dataset truth; `repo-dataset` renders it into specialized formats.

## Domain templates

Each domain template ships with lane definitions, constitution rules, scoring rubrics, and terminology structures designed for that production context:

| Domain | Lanes | Key concerns |
|--------|-------|-------------|
| **game-art** | character, environment, prop, UI, ship, interior, equipment | Silhouette at gameplay scale, faction differentiation, wear/aging |
| **character-design** | portrait, full_body, turnaround, expression_sheet, action_pose | Proportion accuracy, costume logic, personality read, gesture clarity |
| **creature-design** | concept, orthographic, detail_study, action, scale_reference, habitat | Anatomical plausibility, evolutionary logic, silhouette distinction |
| **architecture** | exterior, interior, streetscape, structural_detail, ruin, landscape | Structural plausibility, material consistency, perspective, era coherence |
| **vehicle-mech** | exterior, cockpit, component, schematic, silhouette_sheet, damage_variant | Mechanical logic, functional design language, access points, damage narrative |

## Dataset production

The full dataset spine: snapshot, split, export, eval.

```
snapshot  -->  split  -->  export  -->  eval-pack
   |            |            |             |
  frozen     subject      package       canon-aware
  selection  isolation    (manifest,    test instruments
             + lane       metadata,     (4 task types)
             balance      images,
                          checksums,
                          card)
```

**Snapshots** freeze a deterministic selection of eligible records. Every inclusion has a reason trace. Config fingerprints ensure reproducibility.

**Splits** assign records to train/val/test partitions with subject isolation (no subject family appears in multiple splits) and lane-balanced distribution. Seeded PRNG ensures identical results from the same seed.

**Export packages** are self-contained: manifest, metadata.jsonl, images (symlinked or copied), splits, dataset card (markdown + JSON), and BSD-format checksums. Everything needed to rebuild the dataset from scratch.

**Eval packs** are canon-aware test instruments with four task types: lane coverage, forbidden drift, anchor/gold, and subject continuity. They prove the dataset spine is feeding future model evaluation, not just dumping files.

Export to downstream formats via [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) (TRL, LLaVA, Qwen2-VL, JSONL, Parquet, and more). `repo-dataset` handles format conversion; `sdlab` owns dataset truth.

## Training + implementation spine

The model-asset pipeline: from export package to trained asset and back.

```
export → training profile → manifest → package → eval run → implementation → reingest
  |           |                |           |          |            |              |
dataset    what kind       frozen      trainer-    score       prompts +      accepted
package    of asset        contract    ready       against     examples +     outputs
                                       layout     eval pack   failures       re-enter
```

**Training profiles** define what kind of model asset to produce: target family, eligible lanes, adapter targets, eval requirements.

**Training manifests** are frozen contracts that capture the exact export, split, profile, and config fingerprint. If anything changes, a new manifest is required.

**Training packages** are trainer-ready layouts built by adapters. Two ship: `generic-image-caption` (image folders + JSONL) and `diffusers-lora` (image + caption sidecars). Adapters never mutate inclusion or split truth.

**Eval runs** score generated outputs against Phase 2 eval packs. Scorecards report per-task pass/fail with thresholds.

**Implementation packs** show how to use the trained asset: prompt examples, known failure cases, subject continuity groups, and re-ingest guidance.

**Re-ingest** brings accepted generated outputs back as new records with provenance. They must go through normal review and canon binding — no bypass.

## Star Freight example

Clone the repo for a complete working example: 1,182 records, 28 prompt waves, 5 factions, 7 lanes, 24 constitution rules, and 892 approved assets from a gritty sci-fi RPG.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab

# Validate the project
sdlab project doctor --project star-freight

# Run the full dataset spine
sdlab snapshot create --project star-freight    # 839 eligible records
sdlab split build --project star-freight        # ~80/10/10, zero leakage
sdlab export build --project star-freight       # package with checksums
sdlab eval-pack build --project star-freight    # 78 eval records
```

## Migrating from v1.x

v2.0 renames `games/` to `projects/` and `--game` to `--project`:

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## Security model

**Local-only.** Talks to ComfyUI on `localhost:8188`. No telemetry, no analytics, no external requests. Images stay on your GPU and filesystem.

## Requirements

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) running on localhost:8188
- SDXL-compatible checkpoint + style LoRA
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) for training export

## License

MIT

---

Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
