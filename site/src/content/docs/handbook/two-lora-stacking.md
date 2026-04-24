---
title: Two-LoRA Stacking Contract
description: Domain-scoped World LoRAs plus per-character identity LoRAs — trained separately, composed at inference. Weight bands, load order, failure modes, and the schema surface that makes pairing deterministic.
sidebar:
  order: 7
---

This handbook page documents the two-LoRA stacking contract for Flux training and inference. It pairs a **domain-scoped World LoRA** (style / material / palette) with a **per-character identity LoRA** (a specific face, body, costume language). The two LoRAs are trained separately and composed at inference time — they are **never merged**.

The full research deliverable and the D1–D4 scoping decisions live in `memory/two-lora-stack-research-2026-04-23.md`. This page is the how-to; that file is the why.

## When to use this

Use stacked two-LoRA workflows when:

- You have an approved visual style baseline for a domain (character, environment, monster), and
- You have ≥15 approved images of a specific named character, and
- You want that character to appear rendered in the house style without re-training the style per character.

Skip stacking when:

- You don't have an approved baseline yet — train the World LoRA first and validate, *then* start characters.
- You have <15 records of the character — the character LoRA will overfit.
- You're rendering generic shots where no specific character appears — the domain World LoRA alone is enough.

## The domain-scoped World LoRA pattern

Star Freight has two domain-scoped World LoRAs today; a third (monster) is a future slice.

| Profile | `eligible_lanes` | Role |
|---|---|---|
| `character-style-lora-flux` | `costume`, `equipment` | Character-domain World |
| `environment-mood-lora-flux` | `environment`, `interior`, `station`, `ship` | Environment-domain World |
| *(future)* `monster-family-lora-flux` | tbd | Monster-domain World |

**Domain-scoped, not unified.** Star Freight's approved baselines are already organized into non-overlapping lane sets with distinct data shapes. Mixing costume and environment imagery into a single "project World" LoRA would soften both. If a future project starts from a single undifferentiated baseline pile, the default is still one unified World LoRA — domain-scoping is only the default when the baselines are already separated on disk.

## Per-character identity LoRAs

A per-character LoRA teaches a single subject's face structure, body language, costume specifics, and age read — not style. It is cloned from the template at `projects/star-freight/training/profiles/per-character-lora-flux.json`.

Each concrete instance sets:

- `profile_id` — unique per character (e.g. `sf-kael-maren-lora`)
- `trigger_override` — game-slug-prefixed, `^[a-z0-9_]+$`, never a bare generic suffix like `style` or `character` (e.g. `sf_kael_maren`)
- `subject_requirements.min_subjects: 1` — the one character
- All other fields inherited from the template

The template declares `training_hyperparameters: { rank: 16, alpha: 8, steps: 2000 }`, which the ai-toolkit adapter emits into the YAML config. Rank 16 with alpha 8 (rank/2) is inside the contract band of rank 16–32, alpha = rank/2 or rank/4.

## Triggers — format, collisions, and the override field

Triggers are the text tokens that select the LoRA's learned behavior at inference. Two rules:

1. **Format: `^[a-z0-9_]+$`.** Lowercase, digits, underscores. No hyphens (T5's SentencePiece Unigram tokenizer fragments them unpredictably), no uppercase (not canonicalized), no spaces or punctuation.
2. **Game-prefix the generic suffixes.** `style`, `character`, `anime`, `realistic` — these are the four most-reused tokens in published LoRAs. A bare `style` trigger collides across projects. `sf_character_style` does not.

### `trigger_override` — decouple trigger from profile_id

The default trigger is derived from `profile_id` by swapping hyphens for underscores: `character-style-lora-flux` → `character_style_lora_flux`. That keeps profile IDs descriptive but makes triggers verbose and bound to the filename.

Set `trigger_override` to decouple them:

```json
{
  "profile_id": "character-style-lora-flux",
  "trigger_override": "sf_character_style"
}
```

The override is validated against the rules above at profile load time. If you set `trigger_override: "style"`, validation rejects it with a hint to prefix with a game slug. The override flows through the caption builder and the ai-toolkit sample-prompt emitter unchanged — no other wiring needed.

**Backward compat:** profiles without `trigger_override` emit bit-identical captions to the pre-override implementation. This is test-pinned in `captions.test.js` (search "backward-compat snapshot").

## Training order

**Train the World LoRA first.** Validate on unseen prompts. Only then start training per-character LoRAs against the frozen World.

The reason: a per-character LoRA's held-out validation is "does the character look right in the house style?" — you cannot answer that question if the style isn't stable. Inverting the order turns a two-LoRA stack into a four-way variance search.

## Inference stacking

Stacked workflow profiles carry a `stacking` block that declares the World-LoRA pairing explicitly. Example from `character-portrait-stacked-flux.json`:

```json
{
  "stacking": {
    "default_world_lora_profile": "character-style-lora-flux",
    "requires_character_lora": true,
    "allow_extra_lora": false,
    "max_loras": 3,
    "default_weights": {
      "world":     { "strength_model": 0.5, "strength_clip": 0.5 },
      "character": { "strength_model": 0.9, "strength_clip": 0.7 }
    },
    "load_order": ["world", "character"]
  }
}
```

Tooling reads `default_world_lora_profile` to pair the correct World with the stacker **by contract**, not by inferring from lane overlap. `allow_extra_lora: false` is the default — if you genuinely need a third LoRA (object / prop), set it true explicitly and stay under the cap.

### Weight bands

| Role | `strength_model` | `strength_clip` |
|---|---|---|
| Style / World | 0.3 – 0.6 | 0.3 – 0.7 |
| Character | 0.7 – 1.1 | 0.5 – 0.9 |
| Object / prop | 0.2 – 0.6 | 0.2 – 0.6 |

The defaults (world 0.5/0.5, character 0.9/0.7) sit mid-band for the world and toward the top of the character band — the character is the discriminator, so bias it strong. When stacked captures show texture artifacts or identity drift, the first move is to lower `strength_clip` on the dominating LoRA rather than touch `strength_model`. For three-LoRA stacks that add an object/prop LoRA, lower the world by 0.1 first before reducing the character, per neurocanvas's 2026 diary.

### LoRA count cap

- **Flux 1 dev: ≤ 3 LoRAs** before quality degrades predictably.
- **Flux 2: ≤ 4** (MindStudio's published ceiling for FLUX.2 [dev] LoRA).

Above 2 distinct characters in one call, quality degrades noticeably even within the cap. Composite separately in post for 3+ characters.

## Failure modes

| Symptom | Likely cause | First move |
|---|---|---|
| Character face generic / style-washed | World LoRA dominance | Drop world `strength_model` by 0.1; keep character ≥ 0.9 |
| Texture artifacts / halos | Conflicting style frequencies | Disable one style LoRA or reduce both to 0.3 – 0.4 |
| Muddy output | Too many LoRAs or excessive weights | Stay ≤ 3 (Flux 1) / ≤ 4 (Flux 2); keep weights in 0.3 – 0.7 band |
| Prompts ignored | Excessive CLIP strength | Reduce `strength_clip`; nudge CFG up slightly |
| Character bleeds into other characters | Shared / non-unique trigger | Game-prefix each character's trigger — enforced by the deny-list |
| Two Worlds fighting on color | Co-loading two domain Worlds at equal strength | Pick the dominant domain; other at 0.2 – 0.3 or disabled |
| Prop appears in unrelated scenes | Object LoRA context mismatch | Reduce object `strength_clip`; add negative-prompt exclusions |
| (Flux 2 only) Over-training cliff | Training steps > 1500 on Flux 2 base | Cap at 1500 steps; most runs complete by ~1200 |

## Naming checklist for new character LoRAs

When adding a concrete per-character profile:

1. Clone `projects/<game>/training/profiles/per-character-lora-flux.json` to a new file named after the character.
2. Update `profile_id` to a unique slug (e.g. `sf-kael-maren-lora`).
3. Set `trigger_override` to `<game_slug>_<character_slug>` in snake_case (e.g. `sf_kael_maren`). Validate it doesn't equal `style`, `character`, `anime`, or `realistic`.
4. Narrow `subject_requirements.min_records_per_subject` upward if you have the data (20+ is better than the 15 floor).
5. Drop the profile into its project's training profiles directory; `loadTrainingProfile` will validate it the next time it's invoked.
6. Run the World LoRA's eval pack on the combined stack, not just the character — the regression surface is the pair, not either one alone.

## References

- Research deliverable + D1–D4 decisions: `memory/two-lora-stack-research-2026-04-23.md`
- Contract test suite: `tests/lib-pipeline/flux-profiles.test.js`, `tests/lib-pipeline/flux-workflow-profiles.test.js`, `tests/lib-pipeline/captions.test.js`, `tests/lib-pipeline/training-profiles.test.js`
- Adapter emitting training YAML: `lib/adapters/ai-toolkit.js`
- Caption builder: `lib/captions.js`
