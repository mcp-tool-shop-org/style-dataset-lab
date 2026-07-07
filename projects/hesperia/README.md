# HESPERIA — world & cast concept art (sdlab)

First-class sdlab project (domain `concept-design`) for Hesperia's world, cast, and NPC concept art,
rendered in the studio **rustline** house style (Qwen-Image base, trained rustline LoRA). This project
**CONSUMES** the rustline style; it is not a style-training project.

## The house style it consumes
- **LoRA:** `rustline_v3ckpt_1500.safetensors` @ **weight 1.0** (installed in
  `E:/AI-Models/ComfyUI_windows_portable/ComfyUI/models/loras/`; the shipped production rustline v3).
- **Base:** Qwen-Image (NON-ANIME — never an anime checkpoint). Trigger-first prompts (`rustline style, a <subject>, <scene>`).
- On BASE (no LoRA) the `rustline` trigger renders nothing styled — the LoRA is mandatory.
- The visual law + palette + register live in `canon/hesperia-art-contract.md` (REQUIRED reading) and the
  rustline canon (`projects/rustline/canon/rustline-canon.md` + `rustline-hesperia-reconciliation.md`).

## Config (5/5, doctor-green)
- `project.json` — identity + Qwen-Image defaults (landscape 1344x768; `consumes_style: rustline`)
- `constitution.json` — 11 rules encoding the art contract (style / palette / lighting / silhouette /
  material / world-law / neon register / class-integrity / optics / canon)
- `lanes.json` — 5 lanes: `world_plate`, `cast_android`, `cast_welded_human`, `npc`, `symbol`
- `rubric.json` — 5 dimensions (silhouette_read, palette_mood, material_logic, on_canon, style_consistency)
- `terminology.json` — 4 factions (Communion / Scrip / Decommissioned / keeper), separate id/prompt detection orders

Validate: `sdlab project doctor --project hesperia` → HEALTHY.

## Layout
- `canon/hesperia-art-contract.md` — the visual design bible / art contract
- `inputs/prompts/*.json` — the generation briefs (world plates w1, cast androids, cast welded/human,
  NPC waves 1-3, symbols, rerolls)
- `inputs/composition-seeds/` — rough world maps (structure references for a future i2i/ControlNet pass)
- `outputs/<wave>/` — generated candidate images (git-ignored) + a committed `generation.json` provenance receipt per wave
- `records/*.json` — curated dataset records (tracked)

## Pipeline (per wave)
1. Generate (only when the GPU is free, or via Comfy Cloud) with `defaults.loras` set to
   `[{"name":"rustline_v3ckpt_1500.safetensors","weight":1.0}]`.
2. **Look at every image** (feedback_look_at_images) — full-res, per wave. Never curate from a montage.
3. External verifier: ai-eyes-mcp `image_score_batch` over the batch (SigLIP2, veto power) when available.
4. `sdlab curate <id> approved|rejected|borderline "<reason>"` → records + moves the image to `outputs/<status>/`.
5. A `generation.json` provenance receipt (PIN_PER_STEP) lands in each out dir; fresh waves carry the S3 pinning block.

## Compensators (irreversible actions — from the visual-pipeline contract)
- ComfyUI/Comfy-Cloud batch write → `rm -rf outputs/<batch>/`
- ai-eyes eval persisted → delete the batch eval rows / `evaluations.json` (idempotent; re-run replaces)
- `sdlab curate` flips status → re-run curate with the corrected status (or `git revert <sha>` — records are tracked)
- any `git push` of records/manifests → `git revert <sha> && git push`

## Status
Formalized 2026-07-06 (S4): 5/5 configs, `project doctor` GREEN, first curated records committed from the
existing generated waves. Images stay git-ignored; `generation.json` + `records/*.json` are tracked.
