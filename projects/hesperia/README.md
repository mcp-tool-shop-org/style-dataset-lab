# HESPERIA — visual seed (sdlab)

Phase-0 seed for Hesperia's world concept art. **Zero-GPU, staged.** Generation is GATED — see below.

## What this is
Production concept-art briefs for Hesperia's world and regions, rendered in the studio **rustline** house style
(Qwen-Image base, trained rustline LoRA). This project CONSUMES the rustline style; it is not a style-training
project. Built so that the moment the box is free and the style is ready, generation is one command.

## The two gates (BOTH must clear before any GPU run)
1. **GPU free** — the 5090 must NOT be mid-training (rustline v2). Long GPU runs launch detached + watched
   (memory: gpu-run-detached-launch).
2. **rustline production LoRA ready** — the trained rustline LoRA (v2) installed in
   `E:/AI-Models/ComfyUI_windows_portable/ComfyUI/models/loras/`, and its filename set in the wave's
   `defaults.loras`. On BASE (no LoRA) the `rustline` trigger renders nothing styled — the LoRA is mandatory.

## Files
- `project.json` — project config (consumes rustline; Qwen-Image defaults; landscape 1344x768)
- `canon/hesperia-art-contract.md` — the visual design bible / art contract (REQUIRED reading)
- `inputs/prompts/hesperia-world-plates-w1.json` — wave 1: 11 world plates (the runnable brief)
- `inputs/composition-seeds/` — rough world maps (structure references for a future i2i/ControlNet pass)

## To run (ONLY when both gates clear)
1. Set `defaults.loras` in the wave to the production rustline LoRA, e.g.
   `[{"name":"rustline_style_v2.safetensors","weight":1.5}]`.
2. Start the watchdog (`E:/AI/training/_watchdog.ps1`), start ComfyUI (port 8188), `ollama stop` residents.
3. Generate (ComfyUI embedded python):
   ```
   python E:/AI/style-dataset-lab/scripts/qwen_generate.py \
     --wave E:/AI/style-dataset-lab/projects/hesperia/inputs/prompts/hesperia-world-plates-w1.json \
     --out  E:/AI/style-dataset-lab/projects/hesperia/outputs/world-plates-w1
   ```
4. **Look at every image.** Then run ai-eyes-mcp `image_score_batch` over the batch (external verifier, veto power).
5. Curate keepers → `outputs/approved/`. A `generation.json` provenance receipt (PIN_PER_STEP) lands in the out dir.

## Compensators (irreversible actions — from the visual-pipeline contract)
- ComfyUI batch write → `rm -rf outputs/<batch>/`
- ai-eyes eval persisted → delete the batch eval rows / `evaluations.json` (idempotent; re-run replaces)
- `sdlab curate` flips status → `sdlab curate --revert --batch <id>` (or git revert if records under git)
- any `git push` of this seed → `git revert <sha> && git push`

## Status
Zero-GPU seed staged locally (untracked in style-dataset-lab). NOT committed/pushed yet. NOT generated.
Gated on GPU-free + rustline-v2-ready.
