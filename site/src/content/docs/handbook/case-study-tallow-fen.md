---
title: "Case Study: The Tallow Fen"
description: A from-scratch creature-design bestiary taken end-to-end through Style Dataset Lab into a shipped style-LoRA — the hard-won, high-rejection production profile.
sidebar:
  order: 10
  label: "Proven: Tallow Fen (creatures)"
---

**The Tallow Fen** is a from-scratch creature-design canon — a sunless peat-bog frontier of "mires," bodies of wet peat and dripping tallow — authored to test the non-anime Qwen pipeline end to end. It went the whole distance: written canon → curated dataset → trained style-LoRA → shipped as a project's production default.

It is the pipeline's **high-rejection, exploratory** production profile. The curation gate rejected far more than it kept, and the run is stronger for it.

## The numbers (verified from the repo)

| Metric | Value |
|---|---|
| Domain | `creature-design` |
| Records | **293** |
| Approved | 99 |
| Rejected | 169 |
| Borderline | 25 |
| Approval rate | **~34%** |
| Rejection rate | **~58%** |
| Frozen snapshots | **5** |
| Provenance waves (`generation.json`) | **25** |
| Shipped style | `tallow_fen_style_v3.safetensors` @ **1.5** |
| Base model | `qwen-image` |

169 rejections against 99 approvals is not a failure — it is the gate doing its job. Every one of those 293 records carries provenance, a per-dimension judgment, and (for the approved) a canon binding. Nothing was auto-approved.

## The discipline that produced it

**Gated lanes.** The bestiary was built across five creature lanes — **Pall, Brood, Dredge, Boil, Maw** — and no lane shipped until it was filled and gated. The commit trail reads like a production board: *"bestiary v3 FULLY GATED — Maw closed (8), Dredge de-duped (8 distinct)."* A lane with near-duplicate exemplars was not "done"; it was reworked until it held distinct, on-canon shapes. Those lanes were generated across roughly a dozen booking waves, recorded as **25 `generation.json` provenance artifacts** — one frozen record per lane pass, each carrying its seeds, prompts, and wave metadata.

**The looked-at pass.** Curation here is not a thumbnail glance or a metric-only auto-final. Every candidate is inspected at full resolution against the rubric. The proof that the rubric *bites*: wave 5 came back **0 approved out of 40** on the looked-at pass — a total rejection that forced a full **wave-6 rebuild** on new formulas. A pipeline whose gate can return 0/40 and trigger a rebuild is a gate you can trust.

**Mid-run canon amendments.** The canon was allowed to learn during the run. When review surfaced that the Fen Pall's wings read wrong, the canon was amended in flight — *"Fen Pall wings are amber tallow (Mike, 2026-06-10)"* — and subsequent waves generated against the corrected rule. Canon is training data, not decoration; when it is wrong, you fix the rule and regenerate, not paper over it downstream.

## The output

The run shipped **`tallow_fen_style_v3.safetensors` at LoRA weight 1.5** on base `qwen-image` (checkpoint 1750), set as the project's default generation LoRA in `project.json`. That is a real, versioned, production style asset — trained on a leakage-safe dataset frozen across 5 snapshots, its ship checkpoint chosen by looked-at review rather than by metric alone.

## Why it matters

The Tallow Fen proves the **floor** of the pipeline: a brand-new canon, an exploratory subject where the model holds strong wrong priors, and a curation gate honest enough to reject 58% of everything generated — and it still produced a coherent, shipped style. Contrast it with the [Rustline case study](./case-study-rustline/), the converged ~96%-yield profile, to see the same pipeline at both extremes.

## Related

- [Canon Build — Three Projections](./canon-build/) — how canon becomes constitution, rubric, and terminology
- [Two-LoRA Stacking Contract](./two-lora-stacking/) — how shipped style-LoRAs compose at generation time
- [End-to-End Production Loop](./production-loop/) — the full canon → dataset → training → run → re-ingest cycle
