# FERROCHROME — Visual Art Contract

> The art contract required before any generation (`feedback_art_contract`). Unlike `hesperia`,
> which consumes a house style, **ferrochrome DEFINES a style** — this project's output is a
> trained style LoRA, and this contract is the specification that LoRA is trained toward.
> Phase-0 seed. Generation is **GATED** — see §Gates.

## What this style is

A **photoreal android and cyborg material language**: carbon fibre, chrome, and neon, rendered
with real optics and real physics under cinematic light.

The name is the specification. **Ferro** (the corroded, field-repaired outcasts) and **chrome**
(the factory-new antagonists) are the two poles of one world, and the whole point of this
contract is that they obey **one rendering law** while reading as opposites at silhouette
distance.

**Style-scoped, not game-scoped.** `ferrochrome` names a material register, not a title. It is
intended to be reusable by any project in the studio that needs this look.

## ⚠ The word "photorealistic" is a trap — the target is CINEMATIC-REAL

"Photorealistic" pulls generation toward product-render lighting: three-point lit, seamless
white sweep, even key, no shadow side. The Apple-keynote look. That is the **opposite** of what
this style wants.

- **Take:** real materials, real specular physics, real lens behaviour — lit like a film.
- **Reject:** press-kit product shots, studio sweeps, featureless void backdrops, even fill.

Say **cinematic-real**. Never write "photorealistic" into a prompt or a caption.

## The three registers

All three share one lighting law, one grain, one palette floor. They differ only in surface
condition, symmetry, seam grammar, and neon.

### 1. OUTCAST (`ferro`) — the degraded, the good guys

**Origin (Director, 2026-08-22):** the outcasts **came with the humans on the voyage to
Hesperia**. They were built as crew and companions for a long trip, and **empathy was a design
requirement** — they were meant to be lived with. That is the whole reason they have faces at
all, and it is what makes them read as sympathetic before the audience knows anything else about
them.

They are decades past their service life, field-repaired, and weathered by the planet. Their
bodies are **a record of their own history**.

- **Asymmetric** — because repairs happen where damage happened. Never mirror-symmetric.
- **Accidental seams** — weld scars, mismatched replacement panels, field splices, exposed harness.
- Oxidation, salt bloom, UV chalking, mud, pitting, heat discolouration.
- **Warm sodium light. ZERO neon on the body, ever.**
- Reads as **individual**. Any two outcasts are obviously different units.

#### The face is the species marker. The body is the role marker. (`ROLE-001`)

Every outcast carries the **same empathy-designed face** whatever job it was built for: a calm,
gentle, approachable expression sculpted into the faceplate, and **two SMALL glass lenses set deep
into recessed sockets** under a shallow brow — noticeably smaller than human eyes, each with a
visible iris ring and dark pupil, unlit, catching light only as a small highlight.

**Small and inset, not large and forward.** Large forward discs on a smooth pale skull read as an
alien grey, which is a hard failure — the face must read as *designed to be looked at by a person*,
not as an inhuman prior.

This inverts exactly against the cyclops, which has **no face at all**. Face = built to live
alongside people. No face = built to process them.

The **chassis** is where the role shows:

| Role | Chassis |
|---|---|
| **Companion** | Slender lightweight frame, softly rounded panels, slim delicate hands, minimal armour, warm off-white original finish |
| **Warehouse / cargo** | Heavy squat load-bearing frame, low centre of gravity, very wide reinforced shoulders, spine truss, oversized padded gripping hands, stubby powerful legs |
| **Security** | Tall and upright, broad chest, thicker impact plating on torso and forearms, utility belt, **no weapon** — and the same gentle open face, because it was built to keep order without frightening anyone |
| **Medical** | Slim, smooth sealed seams built to be sterilised, very fine articulated fingers with extra joints, folded instrument mounts on the forearms, original clean white now yellowed |
| **Maintenance** | Wiry practical frame, heavy utility harness with tool clips, a folded multi-tool cluster replacing one hand, thick forearm guards, worn-through kneepads, scorch and oil staining |
| **Agricultural** | Tall lean frame on broad flat stabiliser feet for soft ground, long reaching arms, splayed gentle manipulators, folded spray nozzles on the forearms, pale green chemical-resist coating now blistered and peeling |

The wear tells the same story as the chassis: cargo units are scuffed to bare metal where freight
rubbed; agricultural units corrode upward from the soles; maintenance units are scorched and
oil-soaked; medical units stain chemically down the forearms.

### 2. CYCLOPS (`chrome`) — the factory-new, the antagonists

Top-of-the-line single-optic units. They have **no history** — they came off a line last week.

- **Perfectly symmetric** — nothing has happened to them yet.
- **Designed seams** — deliberate shutlines, panel gaps consistent to the millimetre.
- Unmarked chrome and carbon fibre, zero wear.
- **Single optic, always.** This is the faction's name and its most reliable tell.
- **Cold neon on the body, always** — status and branding, not decoration.
- Reads as **product**. Any two cyclops in frame must be indistinguishable.

### 3. WELDED (`cyborg`) — the between

Human flesh and machine, neither fully. The bridge register.

- Human face and flesh base — this is the only register permitted bare skin.
- Partial, intermittent, or failing neon — they are between the two poles and it shows.
- Mixed seam grammar: surgical where installed, accidental where survived.

## The material law (this is what "done right" means)

Four rules. Each one is the difference between this style and every generic cyberpunk LoRA.

### 1. Neon is a LIGHT SOURCE, never a decal

The failure mode is glowing racing stripes stuck onto a body like glow-tape, with the
surrounding surface lit normally. Wrong.

Real emission **spills**: it tints the panels adjacent to it, colours the shadow side of the
body, blooms in the lens, and the surface directly beneath the emitter is the brightest thing in
frame with a visible falloff. If the training image does not contain the spill, the model learns
stickers — permanently.

### 2. Chrome is a MIRROR, not a colour

Chrome has no local colour. It is one hundred percent environment.

This means **the environment is part of the material, not the background.** A chrome figure on a
grey backdrop teaches "grey gradient with a highlight." A chrome figure under defined
surroundings teaches actual specular behaviour: the horizon line bending across the curve, the
dark band where the surface reflects nothing, the pinched highlight at the panel edge.

**Every frame must specify its lighting world.** Never "on a black background."

### 3. Carbon fibre has a SCALE

Its signature is 2×2 twill weave held at a **consistent scale relative to panel size**, plus
anisotropic sheen that shifts as the surface curves away from the viewer. Inconsistent weave
scale across the dataset teaches "vague dark crosshatch."

### 4. Light is an EFFECT, never a source noun

Write "cold rim light raking the shoulder," never "a lamp." Inherited from the rustline canon and
still correct here.

## Palette

Anchored by register, sharing one desaturated floor.

- **Shared floor:** soot `#16140f` · concrete-grey `#6b6e70` · synth-bone `#cbc6b6`
- **Ferro pole:** rust-brown `#7a4a2b` · sodium-amber `#c8862f` · oxide-green `#5b6b4a`
- **Chrome pole:** cold-steel `#9aa6ad` · cyan-arc `#4fd6e0` · violet-arc `#8b6cf0`

The arc colours are **emitters only** — they appear as light, never as paint.

## Caption law (load-bearing for training)

Captions are **content-only prose, trigger-first**:

```
ferrochrome, a <subject>, <what it is doing>, <what is in frame>
```

Style vocabulary belongs to the trigger, **never** to the caption. If words like "chrome,"
"glossy," "neon-lit," "cinematic," "highly detailed," or "photorealistic" land in the caption,
the trigger learns nothing and the LoRA only fires when the full descriptive prompt is written —
which defeats the entire purpose.

Machine captioners (Florence-2 via plain-sight, or `TextGenerate` on Comfy) **will** emit style
vocabulary by default. A strip pass between captioner and sidecar is mandatory, not optional.

Trigger token: **`ferrochrome`** — single lowercase token, no hyphen (hyphens fragment under
SentencePiece), not a common English concept word.

## Dataset composition (~110 curated)

Balanced quotas are the discipline that makes one dataset serve three registers. If the set
drifts toward grime, the prior collapses and clean chrome becomes unreachable.

| Register | Target | Why |
|---|---|---|
| Outcast | ~32 | |
| Cyclops | ~32 | |
| Welded | ~24 | Smaller — bridge register, less prompt surface |
| **Contact** (both factions in frame) | ~14 | **The highest-value rows.** Proves chrome and rust obey one lighting law. Impossible to express with separate datasets. |
| Material macro | ~8 | Weave scale, chrome curvature, emitter falloff — teaches the physics directly |

## Gates (do not skip)

- **Base model is NOT decided.** See §Open decisions. Do not generate until it is.
- **Look at every image** (`feedback_look_at_images`) — never curate or describe unopened output.
- **ai-eyes-mcp (SigLIP2) is the external verifier with veto power** — a different model family
  from the generator. Run `image_score_batch` over every batch before curation.
- `outputs/approved/` is empty until the first curated wave lands; there is no plate-comparison
  gate before that.

## Settled decisions

1. **Base model — `flux-2-klein-base-4b.safetensors`** (Director, 2026-08-22).

   Apache 2.0 — weights *and* outputs commercially usable. The only commercial-safe
   **non-distilled** FLUX.2 base, which is the point: full training signal for a LoRA base. ~13 GB
   VRAM. The model KB (wave 8, 2026-08-19) calls it "the ideal game-asset training base on a 32 GB
   rig."

   This supersedes visual-pipeline rule 0's "the base is Qwen-Image" (2026-06). That rule's
   purpose is **NO ANIME** — its forbidden list is Illustrious / Pony / NoobAI plus SDXL / Chroma /
   DreamShaper — and klein violates none of it. The KB row is fresher than the rule per the
   constitution's 30-day freshness rule. **NO ANIME remains absolutely binding.**

   > ⛔ **Never `flux-2-klein-base-9b*`.** The 9B klein line is **NON-COMMERCIAL** and sits
   > adjacent to the 4B in the same loader enum. It was selected by mistake once already. A LoRA
   > inherits its base licence — training on the 9B makes every downstream asset unsellable.
   > **Verify the filename says `4b` before every run.**

2. **Flux.2 prompting law — negatives are GONE.** Flux.2 **ignores negative prompts entirely**,
   and `(word:1.2)` weights are not honoured. This removes the "NOT THAT" negative-prompt
   technique the rustline/hesperia lineage depends on. Adherence is steered with a **guidance
   node (FluxGuidance)**, never by raising cfg above 1. Prompts are natural-language full
   sentences.

   Consequence for this contract: everything in the "must avoid" columns of the workflow profiles
   is now a **curation criterion** enforced by the ai-eyes gate and human review — not prompt
   text. The verifier carries the load the negative prompt used to.

3. **Training venue — LOCAL (5090).** Comfy Cloud has **no LoRA weight-export path**. `SaveLoRA`,
   `LoraSave`, and `SaveLoraNode` are all absent from the catalog (verified 2026-08-22), and
   `LORA_MODEL`'s only consumer is the in-graph LoRA model loader. Confirmed independently by
   Comfy consult #4 Q2. A Cloud training run bills GPU time and leaves nothing behind.

4. **Generation venue — Comfy Cloud, OSS checkpoints only.** Bills as `gpu_seconds` rather than
   per-image credits, and makes the unresolved partner-output rights question moot instead of
   betting a commercial product on it. Comfy consult #4 returned **UNKNOWN** on whether partner-API
   output may be used as commercial training data, and independently recommended this same path.
   **Partner-API images stay off the training set** until written vendor terms say otherwise; they
   may still be used for non-training reference and moodboarding.

5. **First training run is a CALIBRATION run** — a few hundred steps, not the full 2000. It
   measures per-step credit burn and confirms the loss curve descends before the budget is
   committed. Adopted from Comfy consult #4, which correctly noted that no one can currently quote
   a training rate.

## Still open

- **Text encoder / VAE pairing for klein.** Flux.2 does not reuse Flux.1's `DualCLIPLoader`
  wiring. Candidates on Cloud: `qwen_3_4b_fp4_flux2`, `mistral_3_small_flux2_{bf16,fp8,fp4_mixed}`.
  Deliberately **not guessed** — resolve against the `text_to_image_flux_2_dev` subgraph blueprint
  when the wave-1 workflow is built.
- **`ResolutionBucket` ordinal pairing.** Bucketing re-sorts by aspect ratio; its signature takes
  `latents` *and* `conditioning` together with a "must match length" contract, which suggests
  pairing survives — but this is untested. **Verify on a 3-image run before committing 110.**
