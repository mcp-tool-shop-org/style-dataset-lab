<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

A canon-bound visual dataset pipeline for directed image production.

Define what your project looks like. Generate candidates. Curate against your canon. Bind approved work to constitution rules. Export trustworthy datasets for training, evaluation, and production reuse.

## What this is

A **visual canon + dataset pipeline** for teams that care about style consistency, provenance, and reviewable judgment. Every asset carries three things:

1. **Provenance** -- full generation history (checkpoint, LoRA, seed, sampler, cfg, timing)
2. **Canon binding** -- which constitution rules this asset passes, fails, or partially meets
3. **Quality judgment** -- approved/rejected/borderline with per-dimension scores

The pipeline works for game art, character design, creature design, architecture, vehicle/mech concepts, and any domain where visual production needs to stay on-model.

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
    exports/                Training data output (gitignored)
```

## Pipeline

```
canon  -->  prompts  -->  generate  -->  curate  -->  bind  -->  compare  -->  export
 |            |             |              |           |            |            |
 rules      packs        ComfyUI       judgment    assertions   preferences   dataset
```

1. **Define canon** -- write your style constitution and review rubric
2. **Create prompt packs** -- structured subjects with style prefix and variations
3. **Generate** -- ComfyUI produces candidates with full provenance
4. **Curate** -- approve/reject with per-dimension scores and failure modes
5. **Bind** -- link each asset to constitution rules with pass/fail/partial verdicts
6. **Compare** -- record pairwise preferences for DPO/ranking datasets
7. **Export** -- produce training data via [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) in 10+ formats

## Domain templates

Each domain template ships with lane definitions, constitution rules, scoring rubrics, and terminology structures designed for that production context:

| Domain | Lanes | Key concerns |
|--------|-------|-------------|
| **game-art** | character, environment, prop, UI, ship, interior, equipment | Silhouette at gameplay scale, faction differentiation, wear/aging |
| **character-design** | portrait, full_body, turnaround, expression_sheet, action_pose | Proportion accuracy, costume logic, personality read, gesture clarity |
| **creature-design** | concept, orthographic, detail_study, action, scale_reference, habitat | Anatomical plausibility, evolutionary logic, silhouette distinction |
| **architecture** | exterior, interior, streetscape, structural_detail, ruin, landscape | Structural plausibility, material consistency, perspective, era coherence |
| **vehicle-mech** | exterior, cockpit, component, schematic, silhouette_sheet, damage_variant | Mechanical logic, functional design language, access points, damage narrative |

## The dataset angle

The pipeline produces more than organized images. It produces **trustworthy, structured datasets** with:

- **Full provenance** on every asset (reproducible generations)
- **Canon-bound judgments** (not just labels -- reasoned verdicts against declared rules)
- **Pairwise preferences** (for DPO and ranking-based training)
- **Per-dimension scoring** (fine-grained quality signals, not just pass/fail)
- **Failure mode tagging** (what specifically went wrong and which rules were violated)

Export via `repo-dataset` to TRL, LLaVA, Qwen2-VL, JSONL, Parquet, and more.

## Star Freight example

Clone the repo for a complete working example: 1,182 records, 28 prompt waves, 5 factions, 7 lanes, 24 constitution rules, and 892 approved assets from a gritty sci-fi RPG.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab bind --stats --project star-freight
sdlab project doctor --project star-freight
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
