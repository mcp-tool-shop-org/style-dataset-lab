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

Write your visual rules. Generate art. Judge every image against those rules. Ship the results as versioned, auditable training data.

Style Dataset Lab connects the thing you wrote down about your art style to the dataset you actually train from. You define a constitution — silhouette rules, palette constraints, material language, whatever matters for your project. The pipeline generates candidates, scores them against those rules, and packages the approved work into reproducible datasets where every record explains why it was included.

The loop closes: train a model, generate new outputs, score them against the same canon, re-ingest what passes. The dataset grows and the rules hold.

## The pipeline

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Bind approved work to constitution rules
sdlab bind --project my-project

# Freeze a versioned dataset
sdlab snapshot create --project my-project
sdlab split build
sdlab export build

# Build a training package and close the loop
sdlab training-manifest create --profile character-style-lora
sdlab training-package build
sdlab eval-run create && sdlab eval-run score <id> --outputs results.jsonl
sdlab reingest generated --source ./outputs --manifest <id>
```

That last command is the point. Generated outputs come back through the same review process as everything else. The loop closes.

## What it produces

Seven versioned, checksummed artifacts. Each links to its predecessors so you can trace any training record back to the rule that approved it.

| Artifact | What it is |
|----------|-----------|
| **Snapshot** | Frozen record selection with config fingerprint. Every inclusion has an explicit reason. |
| **Split** | Train/val/test partition where subject families never cross boundaries. |
| **Export package** | Self-contained dataset: manifest, metadata, images, splits, dataset card, checksums. |
| **Eval pack** | Canon-aware test tasks: lane coverage, forbidden drift, anchor/gold, subject continuity. |
| **Training package** | Trainer-ready layout via adapters (`diffusers-lora`, `generic-image-caption`). Same truth, different format. |
| **Eval scorecard** | Per-task pass/fail from scoring generated outputs against eval packs. |
| **Implementation pack** | Prompt examples, known failures, continuity tests, and re-ingest guidance. |

## Why this exists

Training data is the highest-leverage artifact in any visual AI pipeline. But most training data is a folder of images with no history, no judgment trail, and no connection to the style rules it was supposed to follow.

Style Dataset Lab makes the connection explicit. Your constitution defines the rules. Your rubric defines the scoring dimensions. Your curation records the judgment. Your canon binding proves the connection. And your dataset carries all of that forward as structured, queryable, reproducible truth.

The practical result: when your LoRA drifts, you can ask *why*. When your next training round needs better data, you know exactly which records are near-misses and what single rule they failed. When a new team member asks what the project's visual language is, the answer isn't a Figma board — it's a searchable constitution with 1,182 graded examples.

## Five domains, real rules

Not placeholder templates. Each domain ships with production-grade constitution rules, lane definitions, scoring rubrics, and group vocabulary.

| Domain | Lanes | What gets judged |
|--------|-------|-----------------|
| **game-art** | character, environment, prop, UI, ship, interior, equipment | Silhouette at gameplay scale, faction read, wear and aging |
| **character-design** | portrait, full_body, turnaround, expression_sheet, action_pose | Proportions, costume logic, personality, gesture clarity |
| **creature-design** | concept, orthographic, detail_study, action, scale_reference, habitat | Anatomy, evolutionary logic, silhouette distinction |
| **architecture** | exterior, interior, streetscape, structural_detail, ruin, landscape | Structure, material consistency, perspective, era coherence |
| **vehicle-mech** | exterior, cockpit, component, schematic, silhouette_sheet, damage_variant | Mechanical logic, design language, access points, damage narrative |

## Project structure

Each project is self-contained. Five JSON config files define the rules; everything else is data.

```
projects/my-project/
  project.json           Identity + generation defaults
  constitution.json      Rules with rationale templates
  lanes.json             Subject lanes with detection patterns
  rubric.json            Scoring dimensions + thresholds
  terminology.json       Group vocabulary + detection order
  records/               Per-asset JSON (provenance + judgment + canon)
  snapshots/             Frozen dataset snapshots
  splits/                Train/val/test partitions
  exports/               Versioned export packages
  training/              Profiles, manifests, packages, eval runs, implementations
```

## Trust properties

These are not aspirational. They are enforced.

- **Snapshots are immutable.** Config fingerprint (SHA-256) proves nothing changed.
- **Splits prevent leakage.** Subject families (by identity, lineage, or ID suffix) never cross partition boundaries.
- **Manifests are frozen contracts.** Export hash + config fingerprint. If anything changes, create a new one.
- **Adapters cannot mutate truth.** Different layout, same records. No additions, no removals, no reclassification.
- **Generated outputs re-enter through review.** No bypass. Curate and bind like everything else.

## Star Freight

The repo includes a complete working example: 1,182 records, 5 factions, 7 lanes, 24 constitution rules, 892 approved assets, 2 training profiles. A gritty sci-fi RPG visual canon, fully curated.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Downstream formats

`sdlab` owns the dataset. Format conversion is handled by [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet, and more. `repo-dataset` renders; it never decides inclusion.

## Install

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Requires Node.js 20+ and [ComfyUI](https://github.com/comfyanonymous/ComfyUI) on localhost:8188 for generation.

## Security

Local-only. No telemetry, no analytics, no external requests. Images stay on your GPU and filesystem.

## License

MIT

---

Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
