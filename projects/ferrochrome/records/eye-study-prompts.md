# Eye study — pinned prompts (2026-08-22)

The v3 role prompts were never written to disk. They lived only in the previous session's
conversation, so the exact text that produced `outputs/candidates/roles-v3/` is **unrecoverable**
and the set cannot be re-rolled at a new seed or amended by diff. Every generation from here
records its prompt here first. See PIN_PER_STEP in `.claude/rules/workflow-standards.md`.

## Recipe (identical across all four items)

| | |
|---|---|
| UNET | `qwen_image_2512_bf16.safetensors`, weight_dtype `default` |
| Sampling patch | `ModelSamplingAuraFlow` shift `3.1` |
| CLIP | `qwen_2.5_vl_7b_fp8_scaled.safetensors`, type `qwen_image` |
| VAE | `qwen_image_vae.safetensors` |
| Latent | `EmptySD3LatentImage` 1024×1280 |
| KSampler | `euler` / `simple` / steps `30` / cfg `2.5` / denoise `1.0` |
| **Seed** | **`770422` — pinned identical across A–D so the eye paragraph is the only variable** |
| Output | `SaveImage` (no RMBG — these are design studies, not training data) |

Batch `batch_eyJ2IjoxLCJpdGVtcyI6…` — 4 submitted, 0 failed.

## The question being tested

OPT-004 was amended this session: **the bezel and the socket are load-bearing, not the diameter.**
A–C escalate the socket's machined depth. **D is the control** — it holds the bezel seam and iris
ring but makes the socket shallow and near-flush. If D reads as manufactured, the bezel alone
carries the rule and socket depth is decoration. If only B/C read as manufactured, depth is
doing the work and the amendment should say so.

## Shared body text

> ferrochrome. Cinematic-real close-up head-and-shoulders study of a decades-old colonial service
> android, facing the camera, head turned very slightly.
>
> The head is a moulded synthetic shell of matte off-white composite. Fine panel seams trace the
> crown, the temple and the line of the jaw. No hair, no skin, no pores. The features are sculpted
> the way a mannequin's are: a smooth unbroken brow plate, a narrow moulded nose, closed composite
> lips, a shallow moulded chin.
>
> **‹EYE PARAGRAPH — varies per item›**
>
> Decades of field service: one replacement cheek panel in a slightly different off-white, fine
> scratches through the finish along the jaw, a hairline crack sealed at the temple. Below the jaw
> the neck opens into machined vertebrae and bundled cable looms.
>
> Warm sodium light rakes across from the left. The right side falls into deep shadow. Low-key.

Every variant closes its eye paragraph with the same clause, because the v3 failure was hair and
skin tells, not geometry:

> Smooth bare composite above each socket: no eyebrow, no eyelash, no eyelid, no crease, no white
> of the eye.

## The four eye paragraphs

### A — machined bezel ring, moderate socket
> Each eye is a dark glass lens seated in a socket cut into the faceplate. A fine bright machined
> bezel ring of bare metal runs around the rim of each socket where the lens meets the composite,
> catching a thin hard highlight. Inside the lens sits a segmented iris ring of overlapping metal
> blades around a black pupil. The lenses are unlit and reflect the room.

### B — deep socket, hard shadow across the upper lens
> Each eye is a dark glass lens set deep into a socket cut into the faceplate, sunk far enough back
> that the upper rim of the socket casts a hard shadow across the top third of the lens. A fine
> machined bezel ring of bare metal lines the rim of the socket. Inside the lens a segmented iris
> ring of overlapping metal blades surrounds a black pupil. The lenses are unlit and reflect the
> room.

### C — counterbored two-tier socket
> Each eye is a dark glass lens at the bottom of a counterbored socket: the opening steps down in
> two machined tiers, a wide shallow outer recess and then a narrower inner ring, before it reaches
> the lens. Bare metal on the step edges catches a thin hard highlight. Inside the lens a segmented
> iris ring of overlapping metal blades surrounds a black pupil. The lenses are unlit and reflect
> the room.

### D — CONTROL: shallow, near-flush, bezel seam only
> Each eye is a dark glass lens sitting almost flush in a shallow socket in the faceplate, ringed
> by a single fine machined bezel seam of bare metal. Inside the lens a segmented iris ring of
> overlapping metal blades surrounds a black pupil. The lenses are unlit and reflect the room.

## Shared negative

> eyelashes, eyebrows, eyelid, lid crease, sclera, white of the eye, human eye, tear duct, skin,
> pores, skin texture, hair, stubble, glowing eye, emissive eye, lamp eye, single eye, one eye,
> makeup, lipstick, neon, glowing stripes, product shot, studio sweep, seamless white backdrop,
> even fill, anime, cel shading, flat vector, blurry, low detail

Note the negative names no similes and no metaphors — law #1. `single eye` / `one eye` rather than
`cyclops`, which would summon the myth rather than suppress the optic count.

## Findings

All four looked at full-size and at eye magnification before anything was written here.
Outputs in `outputs/candidates/eye-study/`.

**All four satisfy amended OPT-004.** Every one produced a dark glass lens in a machined bezel with
visible iris/barrel structure, a black pupil, unlit, and — the thing v3 could not do — **no sclera,
no eyelashes, no eyebrows, no lid crease.** The v3 failure is gone in one pass. Leading the eye
paragraph with hardware and closing it with the explicit no-hair clause is what did it.

### 1. The bezel carries the rule. Socket depth is secondary.

**D is the control and D works.** It was written with an explicitly shallow, near-flush socket and
still reads unmistakably manufactured. So the amendment was right that diameter is not the variable
— but it was only half right about depth. The **bezel seam plus the iris ring** is the dominant
tell; socket depth refines the read rather than creating it. B and C are better images, not
categorically different ones.

### 2. The bezel is also what immunises against ALIEN GREY.

Every variant here has lenses at or above human eye scale — A and D visibly larger than human eyes
— and **not one reads as an alien grey.** The old rule assumed scale caused that failure and
prescribed shrinking. Wrong lever. What blocks the alien read is *mechanical structure*: concentric
machined rings say camera hardware, and a smooth black almond says grey. Large is safe as long as
it is visibly built. This is the evidence behind the amendment, now measured rather than argued.

### 3. ⚠ A and D grew a THIRD OPTIC where the ear should be.

Both variants that describe the bezel ring **without** a depth anchor propagated the ring motif to
the next round feature on the head: the ear became a concentric circular port with a lens-like
recess. That is an **OPT-001 risk** — outcasts carry two optics, and a third lens on the side of
the skull breaks the faction tell. B and C, which anchor the socket in machined depth, both kept a
plain moulded ear.

**Practical consequence: prefer a socket-depth variant when propagating.** The depth clause is not
just refinement, it is what keeps the ring language contained to the eyes.

### 4. ⚠ "A cheek panel in a slightly different off-white" renders as a BLACK RECTANGLE.

In A, B and D the mismatched replacement panel came out as a flat black rectangle on the cheek —
read as a missing panel or an open aperture, not as a mismatched repair. Another instance of law
#1: the model took "different panel" literally as "not the panel." **Fix before propagating:** name
the colour positively — "a replacement cheek panel in a *paler* off-white, slightly brighter than
the shell around it" — rather than describing it by difference.

### Per-variant read

| | Optic | Ear | Notes |
|---|---|---|---|
| **A** | bright chrome bezel, prominent, glass dome | ⚠ concentric port | Most jewellery-like. Brightest bezel. Black cheek rectangle. |
| **B** | darker bezel, socket shadow across upper lens | ✓ moulded ear | Most restrained and warmest expression. Black cheek rectangle. |
| **C** | bezel rings carry visible grime and wear | ✓ moulded ear | Best canon fit — the wear sells decades-old and field-repaired. Jaw recess reads as an access hatch. |
| **D** | flush, bright, most concentric rings | ⚠ concentric port | Proves the control. Most forward-mounted. Black cheek rectangle. |

### Cost

4 jobs, 0 failed, 1024×1280 @ 30 steps. `cloud_workflow_executed` still carries no credits figure,
so spend is unprojectable — unchanged from the wave-0 finding.
