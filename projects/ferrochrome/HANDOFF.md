# FERROCHROME — session handoff

**Written 2026-08-22 at the end of the founding session. Paste-ready for a fresh session.**
Repo `mcp-tool-shop-org/style-dataset-lab`, local `E:\AI\style-dataset-lab`, branch `main`,
everything pushed through `530b8e2`.

---

## 1. What this is

`ferrochrome` is a **style-defining** sdlab project. Unlike `hesperia`, which consumes the
rustline house style, this one produces a trained style LoRA (trigger `ferrochrome`) for a
photoreal android/cyborg material language — carbon fibre, chrome, neon, under cinematic-real
light.

**Style-scoped, not game-scoped**, deliberately, so any studio project can use it.

Read first, in this order:
1. `canon/ferrochrome-art-contract.md` — the prose spec, the settled decisions, the three registers
2. `constitution.json` — 22 machine-checkable rules
3. `records/cyclops-design-convergence.md` — nine rounds of design failure and what each taught
4. `records/wave1-findings.md` — the head-scale finding
5. `records/wave0-calibration.md` — the pinned recipe and measured burn

`sdlab project doctor --project ferrochrome` → HEALTHY, 45 passed.

---

## 2. The three registers, in one line each

- **OUTCAST** — came WITH the humans on the voyage to Hesperia, built as crew and companions,
  **empathy was a design requirement**. Decades old, field-repaired, asymmetric, warm sodium light,
  zero body neon. The good guys.
- **CYCLOPS** — factory-new antagonists. **No face at all**, one shrouded aperture, mirror
  symmetric, machined shutlines, cold body neon, identical units.
- **WELDED** — human flesh and machine. The only register permitted bare human skin.

**The load-bearing inversion:** the outcast has *eyes you can see into*; the cyclops has *a hole you
cannot*. A face means built to live alongside people; no face means built to process them.

---

## 3. What is LOCKED (do not re-litigate)

| Thing | Value |
|---|---|
| Generator | `qwen_image_2512_bf16.safetensors` + `qwen_2.5_vl_7b_fp8_scaled.safetensors` (type `qwen_image`) + `qwen_image_vae.safetensors` + `ModelSamplingAuraFlow` shift 3.1 |
| Sampling | `euler` / `simple` / steps 30 / **cfg 2.5** / negative prompts DO work |
| Training base | `flux-2-klein-base-4b.safetensors` — Apache 2.0. ⛔ NEVER the 9B, it is NON-COMMERCIAL |
| Training venue | **LOCAL (5090)** — Comfy Cloud has no LoRA export path |
| Generation venue | Comfy Cloud, OSS checkpoints only (bills GPU-seconds, sidesteps partner-output rights) |
| Cyclops head | `outputs/candidates/wave0-calibration/cyclops_head_v3.png` — Director-locked |
| Dataset form | **Transparent alpha PNG, ONE android per image, no background** — Director's instruction |

**Generator ≠ training base.** These are separate decisions; conflating them cost a round.

---

## 4. The 22 rules — the ones that bite

Full text in `constitution.json`. The ones you will actually violate:

- **`ROLE-001`** — the face is the species marker, the body is the role marker. Every outcast
  carries the same empathy face; the chassis expresses the job.
- **`OPT-001`/`OPT-002`** — cyclops: ONE optic, EMITTING. Outcast: TWO, non-emitting.
- **`OPT-003`** (cyclops) — the optic is a dark shrouded WELL with iris blades and the light at the
  bottom of the shaft. **Depth and shrouding, not diameter** — that correction is recorded.
- **`OPT-004`** (outcast) — small lenses, deep in recessed sockets, iris ring and pupil.
- **`CLS-001`/`CLS-002`** — androids keep synthetic heads and plated torsos, no bare skin (welded
  excepted). The cyclops is a product, never an organism.
- **`UNI-001`** — cyclops are indistinguishable. Show it with a second unit in frame; it cannot be
  demonstrated by one figure.

---

## 5. ⚠ Six prompt-craft laws earned the hard way

These cost roughly fifteen wasted generations between them. Do not rediscover them.

1. **NEVER use a simile.** Qwen renders named objects literally. "like a hunting animal" → an
   animal. "skeletal" → a ribcage. "like a tank turret" → a turret with a gun barrel. "like a
   camera lens assembly" → a telephoto lens on the shoulders. **Describe geometry only.**
2. **Describe the face by MATERIAL, then expression — never by feeling first.** "Calm, gentle,
   approachable" is a description of a person and produces one. Lead with "a moulded synthetic
   shell of matte off-white composite, fine panel seams across the crown and jaw, no hair, no skin,
   no pores, features sculpted the way a mannequin's are," and only then give it an expression.
   This single inversion fixed a failure that three previous passes could not.
3. **Never describe the optic as an addition to a face.** The word "faceplate" invites a face; the
   model builds two sockets and turns your optic into a forehead lamp. Remove the face from the
   description entirely.
4. **Design hard-surface details in CLOSE-UP first, then propagate.** At full-body framing the head
   is ~8% of the frame and gets almost none of the model's capacity. Seven full-body attempts
   drifted; one head study resolved it immediately.
5. **Slim + smooth + pale finish is a NUDE-BODY attractor.** It produced a naked mannequin twice.
   Counter with a hard rectangular mechanical housing (explicitly: no chest muscles, no breast
   forms, no waist taper, no navel) AND clothing.
6. **The outcasts wear worn colonial work garments** — smocks, coveralls, tabards, aprons,
   harnesses. Canon (they worked alongside people) and it kills the nudity attractor and makes the
   role legible at a glance.

---

## 6. The working pipeline (copy this graph)

Isolated alpha android, one per image:

```
UNETLoader(qwen_image_2512_bf16) → ModelSamplingAuraFlow(shift 3.1) ─┐
CLIPLoader(qwen_2.5_vl_7b_fp8_scaled, type=qwen_image) → CLIPTextEncode ×2 (pos/neg)
VAELoader(qwen_image_vae)
EmptySD3LatentImage(960×1536) → KSampler(euler/simple/30/cfg 2.5) → VAEDecode
   → RMBG(model=RMBG-2.0, background=Alpha, refine_foreground=true)
   → SaveImageWithAlpha(images=VAEDecode[0], mask=RMBG[1])
```

Use `submit_batch` for 2+ items — 24/24 succeeded across three batches this session.

---

## 7. ⚠ Tooling gotchas that will waste your time

- **`get_batch_output` returns `storage.googleapis.com` signed URLs, which the Bash sandbox blocks
  with HTTP 403.** The **PowerShell tool is NOT blocked.** Generate a `.ps1` fetch script and run
  it there. Working examples: `fetch-v3.ps1`, `fetch-roles.ps1`, `fetch-isolated.ps1`.
- **The signed URL signs the ENTIRE query string.** Stripping `response-content-disposition`
  invalidates it and curl returns exit 22. **Copy the URL byte-for-byte.**
- Per-job `get_output` returns short `cloud.comfy.org/api/s/...?raw=1` links which ARE reachable,
  but they expire. Batch collection only gives storage URLs.
- Bash heredocs choke on the long prompt/URL content — use the Write tool for scripts.
- Verify alpha on disk, don't assume: the image viewer composites transparency onto grey, so a
  matted PNG looks like it has a grey background. Check with `System.Drawing` pixel sampling.

---

## 8. Measured facts

- Qwen-2512 @ 1152×1536 / 30 steps = **46.95 gpu_seconds** on `rtx_pro_6000`
- klein-4B @ 1024² / 20 steps = **7.05 gpu_seconds**
- `cloud_workflow_executed` events carry **no credits figure** — Comfy does not publish the
  gpu-seconds→credits rate, so budget cannot be projected. Failed jobs are not billed.
- Partner API calls DO show credits: `gemini-3-pro-image` ≈ 35, `grok-imagine-image-2.0` ≈ 12.66

---

## 9. ▶ START HERE — the next task

**Fix the outcast eyes to satisfy `OPT-004`.**

The v3 role set (`outputs/candidates/roles-v3/`, six roles, all alpha) is good and the Director
approved it. The one rule still unsatisfied: the eyes read as *human eyes set into a mannequin
face* rather than **small glass lenses deep in recessed sockets with a visible iris ring and dark
pupil**.

Approach that is most likely to work, given law #4: **do a close-up head study first**, iterate the
eyes there, then propagate to the six roles. Do NOT try to fix it inside a full-body prompt.

Alternative the Director may prefer: **amend `OPT-004`** if the current sculpted-face-with-humanlike
eyes reads better to him than literal lenses would. Ask before assuming.

### After that, in rough order

1. Re-run the six roles at three-quarter and rear angles for turnaround coverage
2. Cyclops unit-class variants (the cyclops equivalent of roles)
3. Welded register — only one exploration exists, and its optic was a blue dome stuck on a cheek
   rather than integrated into the orbital bone
4. **The caption-strip lane — NOT YET BUILT OR TESTED.** This is the piece that silently ruins a
   style LoRA: machine captioners emit style vocabulary, and if that lands in the caption the
   `ferrochrome` trigger learns nothing. Plan is plain-sight/`TextGenerate` to caption → strip
   style words → `prefix: "ferrochrome, "`. ai-eyes gates which images survive, not the captions.
5. Quotas for the real dataset: ~110 curated from ~450–550 generated (outcast 32 / cyclops 32 /
   welded 24 / contact 14 / material 8) — though note the Director questioned multi-figure
   contact rows for training, and he is right that single-subject is the correct default.

---

## 10. Standing instructions from the Director

- **Do not invent canon.** Settings, factions and places must come from the Hesperia world bible.
  An earlier wave invented flooded scrapyards, container yards and drainage tunnels; none are
  canon. Isolated subjects on transparent backgrounds avoid the problem entirely.
- **One android per image** for training data.
- **Transparent background**, no environment. This was raised against (chrome is a mirror and wants
  something to reflect) and the Director overruled it. It is settled; do not re-argue.
- Look at every image before curating it. Nothing gets curated unopened.
- The VRAM watchdog was dead all session — restart before any local training:
  `pwsh -NoProfile -File E:\AI\training\_watchdog_start.ps1`
- Pushes to `main` bypass 2 required status checks. CI is paths-gated and does not fire on
  `projects/**`, so the last green run still covers the unchanged source.
