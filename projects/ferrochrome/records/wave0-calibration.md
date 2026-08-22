# Wave 0 — calibration run (2026-08-22)

The consult's advice, taken: measure before committing the budget.

## Pinned recipe (PIN_PER_STEP)

| | |
|---|---|
| prompt_id | `ca809aba-e87c-44a1-9047-61d7a9d08398` |
| unet | `flux-2-klein-base-4b.safetensors` (Apache 2.0) |
| clip | `qwen_3_4b_fp4_flux2.safetensors`, CLIPLoader `type: flux2` |
| vae | `flux2-vae.safetensors` |
| sampler | `euler` · `Flux2Scheduler` steps 20 · `FluxGuidance` 3.5 |
| latent | `EmptyFlux2LatentImage` 1024×1024 |
| seed | 770422 |
| venue | Comfy Cloud, `rtx_pro_6000` |
| output | `outputs/candidates/wave0-calibration/outcast_cal_770422.png` |

## Measured burn — the number the budget was missing

**7.047 `gpu_seconds`** for one 1024×1024 / 20-step image, billed as
`cloud_workflow_executed` with **no `credits_used` field at all**. Failed jobs were not billed.

Extrapolated: a 400-image wave ≈ **47 GPU-minutes**. Comfy does not publish the
credits-per-GPU-second rate, but at 7 s/image the OSS path is in a different cost class
entirely from partner APIs (~13–35 credits *per image*).

**Consequence worth naming:** the licence-safe path may be too cheap to spend 8000 credits on.
Burning the budget and building the training set are now *separate* activities — see
§Budget split.

## Three findings that cost turns

1. **Template `image_flux2_klein_text_to_image` is BROKEN as published.** Its
   `PrimitiveStringMultiline` prompt node (76) is wired into a `PrimitiveInt` inside subgraph 75:
   `return_type_mismatch ... received_type(STRING) mismatch input_type(INT)`. Reproduced with
   **zero modifications**, `error_owner: platform`. Do not use it; report upstream.
2. **Subgraph blueprints cannot be instantiated via `submit_workflow`.** `text_to_image_flux_2_dev`
   as a `class_type` fails pre-flight with `validation.reference`. They are editor-only —
   build from primitives instead.
3. **klein-4B pairs with the 4B Qwen3 encoder, NOT Mistral-Small.**
   `mistral_3_small_flux2_fp8` fails at the sampler with
   `mat1 and mat2 shapes cannot be multiplied (512x15360 and 7680x3072)` — the Mistral encoder
   emits double the expected width. This was resolved empirically rather than guessed.

## Constitution scoring — the image

**Passes:** `STY-001` strongly — a dusk film still with atmospheric haze and a real shadow side,
not a product render. `LIT-002` — wet street and standing water give the specular something to
reflect. `MAT-001`/`MAT-002` read: oxidation, pale salt bloom, pitting, wet sheen over metal.
`NEON-001` correct for outcast — zero body neon, warm sodium key from an off-frame lamp against
cold ambient. `SIL-001` reads at distance.

**Fails:**

- **`OPT-001` — the worst one.** The figure has a *single red visor band*, not two optics. That is
  cyclops grammar on an outcast body. The base model's prior for "android" leans hard toward a
  single visor, so this will be a standing fight: two-optic language must be explicit and early in
  every outcast prompt.
- **`CLS-001` drift.** The torso is an anatomically human nude form cast in metal — breasts,
  navel, musculature contour — rather than a plated machine torso. "Humanoid android" pulls the
  human body prior. Prompts need blocky mechanical mass, not anatomy.
- **`SYM-001` weak.** Some limb asymmetry, but not the "repairs happen where damage happened"
  read the contract asks for.
- **`SEAM-001` weak.** Seams read as designed panel lines, not weld scars and field splices.
- Framing: "waist up" was ignored; returned full body.

**Verdict:** the base renders the *world* convincingly and the *register* poorly. Exactly what a
calibration run is for. Register discipline has to come from much harder prompt language now, and
from the trained trigger later.

## Budget split (proposed)

Since the training path is cheap and the licensing question only binds training data:

- **Training set** → OSS checkpoints on cloud GPU. Licence-clean, ~7 s/image, unambiguously ours.
- **Remaining credits** → partner APIs (Gemini 3 Pro Image, Grok) for work that **never enters the
  dataset**: moodboards, register exploration, marketing art, key art. Burns the budget legitimately
  without tainting the LoRA's provenance.
