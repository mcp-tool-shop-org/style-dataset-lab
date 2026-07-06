# HESPERIA — Visual Art Contract (world plates)

> The art contract required before any generation (feedback_art_contract). Hesperia does NOT define its own
> style — it **consumes the studio rustline house style**. This contract binds Hesperia's world/region concept
> art to that style and to the world bible. Phase-0 seed; generation is GATED (see README).

## Style binding
- **House style:** rustline (Qwen-Image base, trigger `rustline`). The locked descriptor + trained LoRA live in
  `projects/rustline/`. Production prompts are **trigger-first** ("rustline style, a <subject>, <scene>") off the
  trained rustline LoRA — style vocabulary belongs to the trigger, not the caption.
- **Base:** Qwen-Image (NON-ANIME — never an anime checkpoint). LoRA is model-only (DiT), weight ~1.5.
- **Master palette:** concrete-grey #6b6e70 · rust-brown #7a4a2b · sodium-amber #c8862f · soot #16140f ·
  synth-bone #cbc6b6 · toxic-green #5b6b4a.

## The visual law (load-bearing)
- **Towers = clean / everything below = corroded.** Cleanliness reads as menace — the enemy aesthetic (the
  rustline canon's "NOT THAT" column, used deliberately). Rust, grime, wet concrete, sodium light = home.
- **Light is an effect, never a source noun** ("warm amber highlights, deep low-key chiaroscuro"), never a
  lamp/gaslight object.
- **Neon rule (per the rustline NEON AMENDMENT):** ENVIRONMENT plates MAY use restrained electric neon-noir
  (towers, distant signage). The CHARACTER cast stays grounded warm-sodium (no neon on bodies). World plates are
  environments, so low-key neon-noir is allowed — never bright, clean, or utopian.
- **Mood:** gritty painterly-cinematic, heavy low-key chiaroscuro, film grain, rain-wet grime, smog haze,
  lived-in dystopian squalor. Matte, desaturated. Non-anime, non-vector, non-glossy-3d.

## What to depict (the plates)
See `inputs/prompts/hesperia-world-plates-w1.json` — 11 establishing/region plates: the vertical city, the
towers, the under-city hub, the Rust Communion shrine, the failing lattice, the toxic basin, the radiation
reaches, the polar front, the landed ark, the dead sky with Hesperos, and Sam's road. Each is keyed to the world
bible (`mcp-tool-shop-org/hesperia → docs/world-bible.md`).

## Composition seeds (i2i / ControlNet — follow-on)
`inputs/composition-seeds/` holds the rough world maps (the two Claude Design vector exports + the studio
cross-section SVG). They are **structure references only** — region layout and vertical strata. Claude Design's
vector look is NOT the target finish; the rustline LoRA supplies the paint. The current generator
(`qwen_generate.py`) is txt2img, so wave 1 describes composition in the prompts; using the maps as literal
i2i / ControlNet inputs is a tooling follow-on (qwen_generate has no i2i path yet).

## Gates (do not skip)
- **Look at every image** (feedback_look_at_images) — never describe or curate unopened output.
- **ai-eyes-mcp** (SigLIP2, a different model family from the generator) is the external verifier with **veto
  power** — run `image_score_batch` / `image_contains` over the batch before curation.
- First run establishes the `outputs/approved/` baseline (empty until then — no plate-comparison gate yet).
