---
title: Architecture
description: Record schemas, canon constitution, curation workflow, and export pipeline.
sidebar:
  order: 3
---

## Record schema

Every asset in the dataset is represented by a JSON file in `records/`. Records accumulate data over time as the asset moves through the pipeline.

### Standard record (curated + canon-bound)

```json
{
  "id": "wave3_compact_officer_bridge_s42",
  "asset_path": "outputs/approved/wave3_compact_officer_bridge_s42.png",
  "provenance": {
    "checkpoint": "dreamshaperXL_v21TurboDPMSDE.safetensors",
    "loras": [{ "name": "classipeintxl_v21.safetensors", "weight": 1.0 }],
    "prompt": "concept art of a Compact military officer...",
    "negative_prompt": "photorealistic, photograph...",
    "seed": 42,
    "steps": 8,
    "cfg": 2.0,
    "sampler": "dpmpp_sde",
    "scheduler": "karras",
    "width": 1024,
    "height": 1024,
    "generated_at": "2026-03-15T10:30:00.000Z"
  },
  "judgment": {
    "status": "approved",
    "reviewer": "human:mike",
    "reviewed_at": "2026-03-15T11:00:00.000Z",
    "explanation": "Clean silhouette, correct palette, good material read",
    "criteria_scores": {
      "silhouette_clarity": 0.9,
      "palette_adherence": 0.85,
      "material_fidelity": 0.8,
      "faction_read": 0.9,
      "wear_level": 0.75,
      "style_consistency": 0.85,
      "clothing_logic": 0.8,
      "composition": 0.9
    },
    "failure_modes": [],
    "improvement_notes": null,
    "confidence": 0.9
  },
  "canon": {
    "assertions": [
      { "rule": "RND-001", "verdict": "pass", "rationale": "Painterly style, visible texture" },
      { "rule": "MAT-001", "verdict": "pass", "rationale": "Surfaces read as pressed/stamped" },
      { "rule": "COL-001", "verdict": "pass", "rationale": "Steel blue dominant, charcoal secondary" }
    ]
  }
}
```

### Identity record (named subjects)

Identity records extend the standard schema with two additional blocks:

```json
{
  "identity": {
    "subject_name": "renna_vasik",
    "subject_type": "named_character",
    "faction": "reach",
    "role": "crew",
    "view_type": "anchor_portrait",
    "shot_type": "portrait",
    "identity_anchor": true,
    "location_name": null,
    "ship_name": null,
    "scene_function": "establish face and costume truth"
  },
  "lineage": {
    "generation_phase": "discovery",
    "anchor_source_image": null,
    "anchor_subject_version": null,
    "identity_persistence_score": null,
    "derived_from_record_id": null
  }
}
```

The `identity` block tracks who or what the image depicts. The `lineage` block tracks how it was generated -- discovery (txt2img from scratch), anchor (promoted discovery), or follow-on (img2img derived from an anchor).

Follow-on records must reference their anchor via `anchor_source_image` and `derived_from_record_id`. The generate-identity script enforces this with a hard validation failure.

## Canon constitution

The style constitution lives in `canon/constitution.md`. It defines every rule that judgments can cite.

### Rule categories

| Category | Prefix | Scope |
|----------|--------|-------|
| Rendering | `RND-*` | Universal -- applies to all images |
| Material | `MAT-*` | Faction-specific material vocabulary |
| Shape | `SHP-*` | Faction-specific shape language |
| Color | `COL-*` | Faction-specific palette and saturation |
| Clothing | `CLO-*` | Faction-specific construction logic |
| Ship exterior | `SHP-EXT-*` | Ship hull and exterior design |
| Ship interior | `SHP-INT-*` | Interior spaces and habitation |
| Equipment | `EQP-*` | Weapons, tools, props |
| Environment | `ENV-*` | Scene atmosphere and faction footprint |

### Scoring dimensions

The constitution defines 8 scoring dimensions (0.0 to 1.0) that apply to all image types. Identity records add 4 more for subject-specific evaluation.

**Approval:** all dimensions >= 0.6, average >= 0.7.
**Rejection:** any dimension < 0.4, or average < 0.5.

### Supporting documents

| File | Purpose |
|------|---------|
| `canon/constitution.md` | Full style rules with faction details |
| `canon/review-rubric.md` | Quick review protocol and common failure modes |
| `canon/identity-gates.md` | Named-subject acceptance criteria and lineage schema |
| `canon/species-canon.md` | Alien species anatomy and design specifications |

## Curation workflow

```
candidate (uncurated)
    |
    v
curate.js --> judgment block written to record
    |            |            |
    v            v            v
approved    rejected    borderline
    |
    v
canon-bind.js --> canon.assertions written to record
    |
    v
compare.js --> pairwise comparison records (optional)
    |
    v
ready for export
```

Key design decisions:

1. **Record before move.** The curate script writes the judgment to the record file before moving the image. This prevents orphaned images if the process crashes mid-operation.

2. **Scores are human-entered.** Per-dimension scores come from the curator, not from automated analysis. This is intentional -- the dataset trains models to replicate human aesthetic judgment.

3. **Canon binding is automated.** The canon-bind script maps scores and failure modes to constitution rules deterministically. A low `material_fidelity` score maps to `MAT-001`. A `wrong_palette` failure mode maps to `COL-001`.

4. **Comparisons are separate.** Pairwise preferences live in `comparisons/`, not inside records. This allows comparing images across different waves and categories.

## Export pipeline

The export is handled by the external `@mcptoolshop/repo-dataset` CLI, which scans the repository structure and produces multimodal training data.

### What it scans

| Source | What it reads |
|--------|--------------|
| `records/*.json` | Provenance, judgment, canon assertions |
| `outputs/approved/*.png` | Approved images (classification + critique) |
| `outputs/rejected/*.png` | Rejected images (classification + critique) |
| `comparisons/*.json` | Pairwise preferences (DPO/ORPO pairs) |

### Training unit types

| Type | Input | Output | Use case |
|------|-------|--------|----------|
| Classification | Image | approved/rejected label | Train binary quality classifier |
| Critique | Image | Explanation + scores + failures | Train grounded evaluation |
| Preference | Image pair + winner | Reasoning for preference | DPO/ORPO alignment training |

### Supported formats

TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, OpenAI, DPO, ORPO, KTO.

## Identity packet system

Identity packets handle named subjects -- specific characters, ships, and locations that must be visually recognizable across multiple images.

### Generation phases

1. **Discovery** -- txt2img from composed prompts, 3 seeds per shot. Purpose: find the face, silhouette, and costume truth.
2. **Anchoring** -- curate discovery outputs, promote the strongest to anchor status. The anchor is the recurring truth source.
3. **Follow-on** -- img2img from the anchor at low denoise (0.30-0.45). Purpose: prove identity persists across views, lighting, and context.

### Acceptance gates

Identity images must pass both the standard constitution gates AND identity-specific gates:

| Gate | What it checks |
|------|---------------|
| IC-1 | Silhouette distinction from other characters in the same faction |
| IC-2 | Faction legibility through character-specific expression |
| IC-3 | Identity persistence across 2+ images of the same character |
| IC-4 | Costume integrity -- no drift into other factions |
| IC-5 | Spec compliance with identity lock non-negotiable details |
| IC-6 | No generic drift -- must read as this person, not an archetype |

Locations and ships have their own parallel gates (IL-1 through IL-5) focused on structural repeatability, material language, and lived-in proof.

### Directory structure

```
inputs/identity-packets/    Identity packet definitions (JSON)
records/                    Extended records with identity + lineage blocks
outputs/candidates/         Discovery outputs (uncurated)
outputs/approved/           Curated approved (anchors + follow-ons)
```
