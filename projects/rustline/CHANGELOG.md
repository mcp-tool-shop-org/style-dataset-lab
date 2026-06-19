# Changelog — rustline (2nd house style)

Grounded grimy cyberpunk (SNES-Shadowrun register). Base **Qwen-Image**, identical pinned LoRA
recipe to tallow_fen (single-lever discipline: only the dataset changes between versions). Trigger
word `rustline`. The visual canon for the game **Hesperia**.

All versions trained on the RTX 5090 via ai-toolkit; ship checkpoints chosen by looked-at review +
vector-caliper geometry (NOT auto-final, NOT CMMD-alone) + cross-family cloud-crew verdicts.

## [1.0.0] — 2026-06-19 — v3 PRODUCTION DEFAULT

**`rustline_style_v3` is the production default: ckpt-1500 @ LoRA weight 1.0.** Trained-LoRA gate
passed (Mike, 2026-06-19) after a seed-aligned weight A/B (1.0 vs 1.5): both hold canon; **1.0 binds
cleanly** (a v3 win — v1/v2 needed 1.5) and reads most matte-painterly. Usable per-shot range 1.0–1.5.

### Cast reshaped to fit the Hesperia canon (the reason for v3)
- **Gen-1 grounded system**: the 10 androids stay all-in grounded (warm-sodium, matte industrial).
  The sleek "NOT THAT" enemy register (**Gen-2**) is deferred to a **separate future LoRA** — the v2
  Ironclad sleek-bleed was the evidence against mixing registers in one model.
- **New grounded categories folded in**: **humans** (tower-born, fragile — the `humans` must-not was
  lifted) and **Welded cyborgs** (flesh↔machine spectrum: rank-file flesh+scrap → corroded
  cold-machine overlord; Welded keep a **human face** = the line vs androids). Class-tagged captions
  enforce the human↔android flesh line (android seams = mechanical, never flesh).
- **Gristle RECAST** android → **Welded cyborg**. Muscle is *canon* for a cyborg, which dissolved the
  stubborn strongman bare-torso prior (the v2 bare-arms / v3-android broken-mech failures); renders
  clean first-try in the Welded register. Arc enriched (they welded a person's jaw shut).
- **Ironclad fixed in-place** (stays Gen-1) via an anti-sleek / anti-symmetric prompt → corroded
  broken-plate brute, no Halo-Spartan.

### Rules earned (now canon)
- **Two-optic default**: single-eye only as visible *damage* or a deliberate centered cyclops; the
  cyclops mono-optic is a **Gen-2 enemy trait**, not Gen-1 (a lone side-optic on a smooth face was the defect).
- **Literalism watch**: the model renders structural nouns literally — "synth-bone torso" → ribcage,
  "excised cavity in skull" → skull-face, "needle-driver fingers" → syringes, "steel-drum torso" →
  drum, "light" → lamp. Fixes: name structure as solid plate; `skull, skeletal, syringes` are now
  standard negatives.
- **Framing = portrait 832×1216** + a full-body clause (square 1024 cropped feet to fog).
- **Strict looked-at anatomy QC** (head attached / limbs complete / proportions / full-body, at full
  resolution, BEFORE category and style) — no thumbnail-trust calls.

### Dataset
- `dataset_rustline_v3` = 81 png+txt: 8 cast androids ×6 + Gristle 6 + Ironclad 6 + human 5 +
  welded 5 + welded_overlord 5 + neutrals 6. 75 sdlab provenance records (`records/v3_*.json`),
  class-tagged captions (android / welded cyborg / human), trigger-first `rustline style, …`.
- Caliper geometry baseline: `E:/AI/training/caliper_rustline_v3_states.json` (8 ckpts; ckpt-1500
  effdim 4.79 / aniso 12.33 / loss 0.168 — no late embedding-cloud collapse).

### Proven
- All cast classes on-canon at the bare prompt; human↔android line holds; humans render human, Welded
  = human+machine augment distinct from androids. Gating clean (LoRA + no-trigger ≈ base; dummy
  `xylophone style` carries zero rustline styling → the `rustline` token specifically). **neon-noir
  ENV register learned** (the Phase-A call). Cross-family verifiers (gpt-oss:120b + mistral-large-3:675b):
  on-canon; caveats logged (RUSTLINE chest-stencil on Ironclad → v3.1 candidate, suppressible with a
  text-negative at inference).

## [0.3.0] — 2026-06-18 — neon amendment (Phase A)
Mike reversed the founding militant NO-neon rule after the positive-neon probe ("neon can look great
if done well"). **Register = neon-noir ENVIRONMENTS, grounded cast**; v2 dataset gains a small curated
neon-noir env-plate set (neon-on-characters forbidden at train time). Canon amended (`⚡ NEON AMENDMENT`).

## [0.2.0] — 2026-06-19 — v2 targeted reinforcement (HELD at gate)
`rustline_style_v2` trained on `dataset_rustline_v2` (97 imgs): Gristle 14 (masked-inpaint closed
garment), Ironclad 8 (all-new matte; v1's sleek exemplars dropped — they *were* the prior's source),
neon_env 5 (new class). **Verdict: improved but not a clean fix** — the v2 fixes were texture not
structure (chest-only inpaint left arms unconstrained; Ironclad surface-swap didn't change the sleek
silhouette). Cross-family → iterate to v3, do not ship. Earned: when a class still fails, diff the
actual training *exemplars* — the dataset may be teaching the wrong thing.

## [0.1.0] — 2026-06-18 — v1 baseline
`rustline_style_v1` on `dataset_rustline_v1` (86 imgs). Working baseline; ~8/10 androids
production-usable at weight ~1.5 + prompt hygiene + the NO-neon negative. Ship ckpt 1500 (1500
painterly; 2000 over-cooked to photoreal). Earned: light is an *effect* not a source noun; the
skeleton prior on small/doll frames and the strongman prior on heavy archetypes; a stubborn base prior
is solved by masked i2i inpaint, not more txt2img. Detached-launch ops rule earned (a tool-bg train
died at the compaction boundary; relaunched detached, auto-resumed from `optimizer.pt`).
