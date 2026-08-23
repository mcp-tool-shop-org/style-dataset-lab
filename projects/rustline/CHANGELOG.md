# Changelog — rustline (2nd house style)

Grounded grimy cyberpunk (SNES-Shadowrun register). Base **Qwen-Image**, identical pinned LoRA
recipe to tallow_fen (single-lever discipline: only the dataset changes between versions). Trigger
word `rustline`. The visual canon for the game **Hesperia**.

**v1–v3** trained on the RTX 5090 via ai-toolkit against a uint3-quantised base; **v4–v5** on a
>32 GB cloud GPU against the full bf16 base. Ship checkpoints are chosen by looked-at review +
vector-caliper geometry (NOT auto-final, NOT CMMD-alone) + cross-family cloud-crew verdicts — a gate
that **has not been run for v4 or v5**, see the UNRELEASED section below.

## ⚠ UNRELEASED — v4 and v5 exist, TRAINED BUT NEVER GATED

**Reconstructed 2026-08-22 from on-disk artifacts.** Both versions were trained, produced full
checkpoint series and progression sheets, and then **the proof harness their own configs prescribe
was never run.** That is why neither appeared here: nothing was ever blessed, so nothing was ever
written down. **`rustline_v3ckpt_1500 @ 1.0` remains the last gated production default.**

**⚠ CORRECTED 2026-08-22 (same day).** An earlier version of this section claimed neither version
had A/B waves or cross-family verdicts. **That was wrong for v4** — `E:/AI/training/ab_rustline/`
holds `v4_ab/` (81 files), `_v4_jury_1500.json` (81 cross-family verdicts), `_v3_vs_v4_1500.jpg`,
a `_FACES` crop of the same, and `_v4_weight_sweep.jpg`. v4 got most of the harness. What v4 lacks
is `ckpt_grids_rustline_v4/` and a caliper capture. **v5 has none of it — there is no `v5_ab/`.**

### The v4 jury result, previously undocumented — and why v4 was never blessed

81 verdicts, v3ckpt-1500 vs v4ckpt-1500, three model families:

| | v4 | v3 | tie |
|---|---|---|---|
| **overall** | **37** | 32 | 12 |
| gemini-3-flash-preview | 13 | 5 | 9 |
| minimax-m3 | 15 | 9 | 3 |
| **kimi-k2.6** | 9 | **18** | 0 |

Two families prefer v4, one strongly prefers v3, and kimi never ties. **46% / 40% / 15% with the
families split is not a gate pass**, which is the real reason v4 was never promoted.

Per character it is sharper than the totals suggest. v4 clearly wins **gutterjack 7–1**,
**hearthframe 5–2**, **hushwire 5–3**. v4 clearly LOSES **ironclad 2–7** and **scrap_saint 2–6** —
and ironclad is the character v3 had just fixed in place with an anti-sleek prompt.

**What the jury was actually measuring, in its own words:** *"more mechanical head/body, less human
face"* · *"more fully mechanical body; Image 1 has a clearly human face"* · *"hood obscures humanoid
face."* Every reason scores the human↔android flesh line — the distinction the canon calls
load-bearing.

**The finding: the full-precision base bought FIDELITY and cost MECHANICAL-NESS.** Visible directly
in `_v3_vs_v4_1500_FACES.jpg` — v4's ironclad is sleeker, cleaner and legibly branded where v3's is
a corroded broken-plate brute, and v4's hearthframe and rustblood drift toward human female faces.
Both are canon violations: sleek is the **Gen-2** register that rustline must not learn, and a human
face belongs to the **Welded**, not to androids.

**This is why v5 exists.** v5's config states its goal as a *"tighter human↔android separation"* and
a higher clean-face yield, with the dataset thickened by *"keep only clean synthetic-faced
exemplars."* v5 is the corrective for a measured regression, not just more rows.

⚠ Do not cite `E:/AI/training/_contact_ab_v4.png` or `_contact_ab_v5.png` as evidence for either.
`E:/AI/training/` is a shared flat workspace across projects and those two files belong to a
different project entirely (sailing ships / locomotives). Only **path-scoped** artifacts —
`ab_rustline/`, `rustline_v4_ckpts/`, `rustline_v5_ckpts/`, `dataset_rustline_v4|v5/` — are
trustworthy for rustline.

### v5 — 2026-06-27 — expanded dataset, full-precision  *(ungated)*
- **Single lever vs v4: the DATASET only**, 81 → **195 rows**, all captioned (195/195). Recipe
  byte-identical to v4.
- Built by the **volume + curation flywheel**: generate with v4 → cross-family jury → keep only
  clean synthetic-faced exemplars. Intent was a tighter human↔android separation and a higher
  clean-face yield.
- **Same cast, deeper** — no new subjects. The 10 androids + welded + welded_overlord + human + 3
  neutral objects, thickened with a/b/c/d/g series per character.
- ⚠ **The sample-monitor prompts were also rewritten** (more canon-specific: *"a plated mask-face
  with two optics one a smashed dark socket, full body"*). Training signal is still single-lever,
  but this **breaks the cross-version sample comparability** v3 deliberately preserved — v5's
  progression sheet cannot be compared like-for-like against v1–v4's.
- Artifacts: `rustline_v5_ckpts/` (250→2000 @ 250), `_v5_progression.jpg`, `dataset_rustline_v5/`.

### v4 — 2026-06-27 — full-precision base retrain  *(ungated)*
- **Single lever vs v3: BASE PRECISION.** Dataset byte-identical to v3's 81 exemplars.
- v1→v3 were all trained against Qwen-Image crushed to **uint3 (3-bit) + qfloat8 text encoder** — a
  hard 32 GB necessity on the 5090. The config names that 3-bit base as *"the real quality ceiling
  (NOT the dataset, NOT fp8 inference)."*
- v4 moved to the **full bf16 base, no quantisation**, on a >32 GB cloud GPU. **The studio's first
  full-precision house-style LoRA.** `quantize: false`, `quantize_te: false`, `low_vram: false`.
- Artifacts: `rustline_v4_ckpts/`, `_progression_sheet.jpg`, `dataset_rustline_v4/`.

### Also found: an uncaptioned row in the v3 training set
`dataset_rustline_v3/` holds **82 images against 81 captions** — `_v3_STAGED_full.png` is a staging
artifact with no `.txt`, sitting in the dataset behind the current production default. v4 inherited
the clean 81. v5 is clean at 195/195.

---

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
