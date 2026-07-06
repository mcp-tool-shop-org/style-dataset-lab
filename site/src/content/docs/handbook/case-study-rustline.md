---
title: "Case Study: Rustline"
description: A dense concept-design canon taken end-to-end through Style Dataset Lab into a shipped two-LoRA Qwen production default — the converged, high-yield production profile, reused downstream by a second project.
sidebar:
  order: 11
  label: "Proven: Rustline (concept)"
---

**Rustline** is a grounded, grimy-cyberpunk concept-design canon — the visual house style for the game **Hesperia** — carried the whole distance through Style Dataset Lab: dense written canon → curated dataset → trained style-LoRA → shipped as a project's production default, then **reused by a downstream project**.

It is the pipeline's **converged, high-yield** production profile. Where [the Tallow Fen](./case-study-tallow-fen/) rejected ~58% of everything on an exploratory creature run, Rustline approved ~96% — because the canon was well-formed *before* generation started.

## The numbers (verified from the repo)

| Metric | Value |
|---|---|
| Domain | `concept-design` |
| Records | **180** |
| Approved | 172 |
| Rejected | 8 |
| Borderline | 0 |
| Approval rate | **~96%** |
| Provenance waves (`generation.json`) | **46** |
| Shipped style | `rustline_v3ckpt_1500.safetensors` @ **1.0** |
| Base model | `qwen-image` |

172 approvals against 8 rejections is the other face of the same gate. The Tallow Fen shows the gate rejecting hard on an open-ended subject; Rustline shows what disciplined, pre-formed canon buys you — a converged run where nearly everything generated lands on-canon.

## The story

**Dense canon first.** Rustline's canon doc runs 272 lines before a single image is generated — a fully specified world (grounded painterly, warm-sodium, matte-industrial), with a `rustline` trigger word and an explicit "NOT THAT" column. Same pinned Qwen LoRA recipe as the Tallow Fen: single-lever discipline, where only the dataset changes between versions.

**Cast → recast to serve the game.** The canon grew a 10-android cast, then reshaped to fit the Hesperia canon before v3 trained, so the style would not drift from the game it serves. The enemy "Gen-2" sleek register was deferred to a separate future LoRA (mixing grounded and sleek in one model bled); grounded **humans** and **Welded cyborgs** were folded in; the Gristle character was recast from android to Welded cyborg, which dissolved a stubborn base-model prior and rendered clean first-try. That reconciliation is recorded in the canon as `rustline-hesperia-reconciliation.md`.

**Shipped by looked-at review, not metric alone.** All versions trained on the RTX 5090 via ai-toolkit; ship checkpoints were chosen by looked-at review plus vector-caliper geometry plus cross-family cloud-crew verdicts — never auto-final, never CMMD alone. v3 landed on **checkpoint 1500 at weight 1.0** — a genuine win, since v1 and v2 needed weight 1.5; 1.0 binds cleanly and reads most matte-painterly.

## Downstream reuse

Rustline is not a one-project style. The **Hesperia** project consumes `rustline_v3ckpt_1500.safetensors` @ 1.0 as its base style across its production prompt packs — cross-project style reuse is a pipeline strength: a canon-bound, curation-gated style asset trained in one project becomes a dependable production default in another.

## Contrast with the Tallow Fen

| | Tallow Fen | Rustline |
|---|---|---|
| Domain | creature-design | concept-design |
| Records | 293 | 180 |
| Approval rate | ~34% | ~96% |
| Profile | exploratory, high-rejection | converged, high-yield |
| Canon | authored + amended mid-run | dense, pre-formed |
| Shipped style | `tallow_fen_style_v3` @ 1.5 | `rustline_v3ckpt_1500` @ 1.0 |

**Same pipeline, two production profiles.** One shipped a coherent style through a brutal ~58%-rejection exploratory creature run; the other shipped through a ~96%-yield converged concept run. That is the proof on both ends: the curation gate is real (it rejects hard when the subject is open), and disciplined canon yields high acceptance (when the rules are formed before generation). Two shipped LoRAs, one pipeline.

## Related

- [Canon Build — Three Projections](./canon-build/) — how dense canon becomes machine-readable rules
- [Two-LoRA Stacking Contract](./two-lora-stacking/) — the contract Rustline's shipped style honors
- [End-to-End Production Loop](./production-loop/) — the full canon → dataset → training → run → re-ingest cycle
