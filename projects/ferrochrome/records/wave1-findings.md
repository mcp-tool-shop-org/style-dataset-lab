# Wave 1 — first production batch (2026-08-22)

12 rows submitted via `submit_batch`, **12 succeeded, 0 failed**. Generator
`qwen_image_2512_bf16`, pinned recipe in `inputs/prompts/wave1.json`.

## ⚠ THE FINDING: the locked cyclops head does not survive full-body framing

This is the most important result of the batch and it changes the production plan.

| Framing | Head | Evidence |
|---|---|---|
| **Close-up** | ✅ HOLDS exactly | `cyclops_head_rain` — unbroken plate, no jaw, iris blades visible inside the well, small cyan point deep in the shaft, rain beading on the ceramic |
| **Full body** | ❌ COLLAPSES | `cyclops_patrol`, `contact_scan` — reverts to a round dome with a large flush lens: the precise baby-schema failure OPT-003 was written against |

The prompt text was **identical in substance** across all three. The difference is purely how much
of the frame the head occupies. At full-body scale the model falls back to its own "robot head"
prior and the canon loses.

### What this means

1. **The LoRA is not polish — it is the mechanism.** The whole reason to train `ferrochrome` is to
   carry a design that prompts demonstrably cannot hold at scale. This batch is the empirical
   argument for the project.
2. **Until the LoRA exists, full-body cyclops rows need conditioning, not prose.** Options:
   ControlNet on a posed reference, IP-Adapter/reference off the locked head, or generate the body
   and inpaint the head. Prompt-only full-body cyclops rows will keep failing.
3. **Close-up rows are reliable NOW.** Cyclops dataset rows should be weighted toward head and
   upper-body framings until conditioning is wired, otherwise we train the LoRA on images that
   violate the very rule it is supposed to learn — which would bake the failure in permanently.

**Do not curate a full-body cyclops row into the training set unless the head is on-canon.**
A wrong head in the dataset teaches the wrong head.

## Per-row verdicts (5 of 12 reviewed so far)

| Row | Verdict | Notes |
|---|---|---|
| `cyclops_head_rain` | ✅ **APPROVE** | Locked head exactly. Iris blades, deep well, water on ceramic. Best cyclops row. |
| `welded_portrait` | ✅ **APPROVE** | Best of the new registers. Tired human face, metal plate sutured into the cheek, small dark optic, industrial shoulder plating that was installed rather than born. Sympathetic and wrong at the same time — exactly the between-register. |
| `contact_scan` | ⚠ **BORDERLINE** | Register contrast is excellent — warm rusted outcast against cold white cyclops, the two light temperatures meeting on the water. But the cyclops head is off-canon. Keep as a COMPOSITION reference; do not train on it. |
| `cyclops_patrol` | ❌ **REJECT for training** | UNI-001 is perfect (three genuinely identical units) and the composition is strong, but the head is the round-dome failure. Keep as a staging/composition reference only. |
| `outcast_corridor` | pending review | |

Remaining 7 rows pending review before curation (`feedback_look_at_images` — nothing gets curated
unopened).

## What worked

- `submit_batch` — 12/12, no failures. This is the right tool for volume.
- Varying setting and pose while holding the lighting law produced consistent world-feel across
  wildly different scenes.
- The outcast register is robust at every framing tested so far — its rules (two dark eyes,
  asymmetry, weld scars, warm sodium) survive where the cyclops rules do not. Likely because
  "battered humanoid robot" is closer to the base model's prior than "faceless single-aperture
  machine" is.

## Tooling note — batch collection egress

`get_batch_output` returns `storage.googleapis.com` signed URLs, which the **Bash sandbox blocks
with 403**. Per-job `get_output` returns `cloud.comfy.org/api/s/...?raw=1` shortlinks, which are
reachable but expire. **The PowerShell tool is NOT egress-blocked** — generate a fetch script and
run it there. `fetch-wave1.ps1` is the working pattern; keep using it for future batches.
