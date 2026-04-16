---
title: End-to-End Production Loop
description: The full workflow from canon definition through dataset production, model training, generation, selection, and re-ingest.
sidebar:
  order: 5
---

This page walks through the complete production loop — the real point of Style Dataset Lab. Not just curation. Not just datasets. The full cycle from creative rules to production outputs and back.

## The loop

```
canon → dataset → training → brief → run → critique → batch → select → re-ingest
  ↑                                                                         |
  └─────────────────────────────────────────────────────────────────────────┘
```

Every stage produces structured artifacts. Every artifact links to its predecessors. Selected outputs return as candidates, not as auto-approved canon. The review system stays in charge.

## 1. Create a project

```bash
sdlab init my-project --domain character-design
sdlab project doctor --project my-project
```

Five JSON config files define your visual rules: `constitution.json`, `lanes.json`, `rubric.json`, `terminology.json`, `project.json`.

## 2. Curate and bind

Generate candidates, review them against your rubric, and bind approved work to constitution rules.

```bash
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab curate anchor_01_deckhand_v1 approved "Strong silhouette, correct faction palette"
sdlab bind --project my-project
```

Every approved record now carries provenance, judgment, and canon binding.

## 3. Build datasets

Freeze versioned snapshots, create leakage-safe splits, and package for export.

```bash
sdlab snapshot create --project my-project
sdlab split build --project my-project
sdlab export build --project my-project
sdlab card generate --project my-project
```

## 4. Train models

Create training profiles, manifests, and trainer-ready packages.

```bash
sdlab training-profile list --project my-project
sdlab training-manifest create --profile character-style-lora
sdlab training-package build --project my-project
```

Score generated outputs against canon-aware eval packs:

```bash
sdlab eval-run create --project my-project
sdlab eval-run score <id> --outputs results.jsonl
```

## 5. Compile production briefs

Briefs are deterministic generation instructions compiled from workflow profiles and project truth.

```bash
sdlab workflow list --project my-project
sdlab brief compile --workflow character-portrait-set --subject kael_maren --project my-project
sdlab brief show brief_2026-04-16_001
```

The brief carries the full prompt, negative prompt, runtime defaults, and canon focus — all derived from your constitution and workflow profile.

## 6. Run production

Execute briefs through ComfyUI. Each run is a frozen artifact: brief + seeds + outputs + manifest.

```bash
sdlab run generate --brief brief_2026-04-16_001 --project my-project
sdlab run show run_2026-04-16_001
sdlab run list --project my-project
```

## 7. Critique and refine

Inspect run outputs against canon dimensions. Generate focused next-pass briefs.

```bash
sdlab critique --run run_2026-04-16_001 --project my-project
sdlab critique show --run run_2026-04-16_001
sdlab refine --run run_2026-04-16_001 --pick 001.png --push "stronger faction insignia"
```

## 8. Batch-produce

Coordinated multi-slot production: expression sheets, environment boards, silhouette packs, continuity variants.

```bash
sdlab batch generate --mode expression-sheet --subject kael_maren --project my-project
sdlab batch show batch_2026-04-16_001
sdlab batch sheet batch_2026-04-16_001
```

Each slot gets its own brief, run, and output. The batch sheet is an HTML review surface.

## 9. Select outputs

Choose the best outputs from runs or batches. A selection is a creative decision artifact — what was chosen, why, and where it came from.

From a run:
```bash
sdlab select --run run_2026-04-16_001 --approve 001.png,003.png --reason "best continuity" --project my-project
```

From a batch:
```bash
sdlab select --batch batch_2026-04-16_001 --approve slot_neutral:001.png,slot_anger:001.png --project my-project
```

View selections:
```bash
sdlab selection show --project my-project
sdlab selection show selection_2026-04-16_001
```

## 10. Re-ingest

Selected outputs return as new candidate records with full generation provenance. They go through the same review and canon-binding flow as everything else. No bypass.

```bash
sdlab reingest selected --selection selection_2026-04-16_001 --project my-project
```

Each re-ingested record carries:
- `source: generated` provenance
- Generation provenance linking back to run/batch → brief → workflow → seed
- Tags: `generated`, `selected`, workflow ID, subject ID
- Status: staged for review (not auto-approved)

Then review them like everything else:
```bash
sdlab curate gen_selection_2026-04-16_001_001 approved "Strong faction read, correct palette"
sdlab bind --project my-project
```

The corpus grows. The rules hold. The next snapshot, split, and training package will include them — if they pass.

## The product result

After this loop, your project can:

1. **Define** what your art looks like (canon)
2. **Build** versioned, auditable training datasets (snapshots, splits, exports)
3. **Package** trainer-ready model assets (training manifests, packages)
4. **Compile** production briefs from project truth (workflow profiles)
5. **Run** local generation workflows (ComfyUI)
6. **Critique** and refine outputs against canon (critique engine)
7. **Batch-produce** real work surfaces (expression sheets, environment boards)
8. **Select** the best results (selection artifacts)
9. **Feed them back** into the corpus (re-ingest with provenance)

That is a closed creative production system, not a one-way generator.
