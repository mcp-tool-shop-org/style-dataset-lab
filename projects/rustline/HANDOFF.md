# RUSTLINE — session handoff

**Written 2026-08-23. Paste-ready for a fresh session.**
Repo `mcp-tool-shop-org/style-dataset-lab`, local `E:\AI\style-dataset-lab`, branch `main`.
Training artifacts live OUTSIDE the repo at `E:\AI\training\`.

---

## 1. What rustline is

The studio's **live, trained house-style LoRA** — grounded grimy cyberpunk (SNES-Shadowrun
register), base **Qwen-Image**, trigger word **`rustline`**. It is the visual canon for the game
**Hesperia**.

Cast: **10 androids** (dockrat, dustwhisper, gristle, gutterjack, hearthframe, hushwire, ironclad,
rustblood, rustgrave, scrap_saint) **+ welded + welded_overlord + human + 3 neutral objects**.

Read first, in order:
1. `canon/rustline-canon.md` — the canon. Trigger word, neon amendment, Hesperia alignment.
2. `CHANGELOG.md` — v1→v5 history, including the v4 jury verdict that explains why v4 was never shipped.
3. `records/comfy-cloud-model-import-resolution.md` — how Cloud resolves imported LoRA names.
4. Memory `rustline-bare-prompt-rule.md` — **THE generation rule.**
5. Memory `comfy-cloud-run.md` — the Cloud procedure and its eight gotchas.

⚠ `sdlab project doctor --project rustline` **FAILS** — no `constitution.json` / `lanes.json` /
`rubric.json` / `terminology.json`. Rich prose canon and 180+ records, nothing machine-checkable.
Not blocking generation; worth fixing.

---

## 2. ⭐ SHIP CHECKPOINT: `rustline_v5ckpt_1000`

**Director's call, 2026-08-23**, from a 4-way matched-seed bracket (`ab_rustline/v5_ab/`).

The evidence, and the reasoning — because the naive metric says the opposite:

| criterion | ckpt 1000 | ckpt 1500 |
|---|---|---|
| **FLESH flags** | **52%** | 70% |
| **ANATOMY flags** | **19%** | 48% |
| FRAMING flags | 74% | **63%** |

**Framing is fixable in the prompt; flesh drift is baked into the weights.** 1000's only weakness
is the one you can fix for free. Higher checkpoints drift cleaner, whiter and more human-bodied —
the same regression that killed v4.

⚠ **Do NOT decide this on jury pass-counts.** Two runs over identical images flipped the ordering
(1000: 2→5, 1500: 7→3). At n=27 with a stochastic panel, run-to-run variance exceeds the
between-checkpoint difference. **Only the reason breakdown is stable** — use
`scripts/jury_reason_breakdown.py`.

---

## 3. Where v6 stands

Goal: **density, not new subjects.** v5's expansion was lopsided — dock-laborer got 26 rows while
**welded 5, welded_overlord 5, human 5, rustblood 7**, and those three carry the human↔android
flesh line the canon calls load-bearing. The v6 kickoff flags exactly this as open item 3.

| round | dir | status |
|---|---|---|
| v6 (round 1) | `out_v6_cloud/` | **BINNED** — see its `_WHY_BINNED.md`. Renders deleted, evidence kept. |
| v6b (round 2) | `out_v6b_cloud/` | 288/288 rendered on ckpt_1000. Three defects fixed, two remain. |
| v6c (round 3) | not yet fired | Waves rebuilt with the cast direction below. **NEXT ACTION.** |

### Round-2 result (looked at, all four class sheets)
- ✅ `rustblood` holds the flesh line — plated arms/torso, no bare human skin
- ✅ `human` shows bare human faces — the class finally teaches its distinction
- ✅ Real variety — six visibly different people per class
- ⚠ `welded` female rows drifted to **glamour** (midriff crop-tops, tidy augments) vs canon's
  "crude jury-rigged survival augment ... rust + grime"
- ⚠ `human` doesn't read "fragile, pale, tower-born" — reads hardened. Suspected **LoRA prior**
  fighting the prompt (rustline is trained on weathered figures), not fixable by another negative.
  May need reference images, or acceptance.

### ⭐ Cast direction (Director, 2026-08-23) — applied in the v6c waves
**Welded is MOSTLY MALE with tank-like builds to offset. Female welded exist but must not dominate
the dataset.** Now 5 male (2 explicit TANK builds) + 1 female. **Humans get wider character
variety** — age, build, health, dress, role.
`pin-up, glamour, midriff crop top, bare navel, posed fashion model, sexualised` added to the
welded negative.

---

## 4. ⚠ Prompt laws (each cost a wave)

1. **THE BARE-PROMPT RULE governs the FACE ONLY.** For synthetic-faced androids the head must
   contain **zero face-anatomy words** — naming a nose/mouth/cheek *even to negate it* summons a
   human face. Yield: verbose ~4–25%, bare ~57–66%. Use **w1.25**.
2. **The BODY needs its own constraint.** Round 1 produced androids with clean synthetic heads and
   **human arms and midriffs**, because nothing said the torso was plated. Every android body
   string must name **closed plating on torso AND limbs**, and the word **"bare" is banned from
   android prompts** (it was in "one arm bare hydraulics"). Body-flesh terms belong in the negative.
3. **The `human` class must be UNMASKED.** Round 1 sealed every human behind a hood + rebreather,
   hiding the visible human face that is the entire feature separating the class from an android.
   `gas mask, respirator covering the face, hood over the face` go in the human negative.
4. **Variety comes from INDIVIDUALS, not poses.** One subject × 12 poses × 6 seeds = 72
   near-identical images worth roughly one row. Canon: outcasts "read as INDIVIDUAL — any two are
   obviously different units." Use 6 distinct individuals × 4 poses × 3 seeds.
5. **The negatives are CLASS-INVERTED** — one wave carries one negative, so classes need separate
   waves: android forbids human flesh; welded requires flesh + augments; human requires flesh and
   forbids augments.
6. **Literalism watch** (rustline canon): structural nouns render literally. "rake-like
   manipulators" → garden rakes. Describe geometry, never simile.
7. **⚠ CHECK THE LAWS PER CLASS, NEVER WITH A GLOBAL GREP.** Laws 1 and 2 are *android-scoped* —
   they govern synthetic-faced androids only. A repo-wide grep for face-anatomy words or for
   "bare" lights up red on `human`, `welded` and `overlord` and looks like a halt, when those
   classes exist **precisely to show human faces and flesh**. `"a bare human face"` in the human
   prompts IS Law 3's fix; `"bare human-flesh back and shoulders"` in welded is the class's
   defining feature. Build a per-class law matrix; a global check produces false alarms on exactly
   the classes whose defining trait is the thing it flags. (Earned 2026-08-23 — a global check
   printed red on three of four classes and nearly stopped a correct wave.)

---

## 5. ⚠ Operational gotchas — all cost real time this session

### Comfy Cloud
- **Headless `/api/prompt` ACCEPTS imported LoRAs that are NOT in the node combo.** Submission
  returns `succeeded_with_warnings` ("not found in the bundled node index") and **runs fine**. The
  empty-combo problem is **browser-UI only**. This unblocked the whole evening after being treated
  as a hard wall.
- **Resolver name = `<hf-owner>__<repo>__<filename>`, double underscore.** Ours:
  `mikeyfrilot__rustline-lora__rustline_v5ckpt_1000.safetensors`. NOT the bare filename, NOT
  slash-namespaced. Note the owner is whatever the import used — we have both a `mikeyfrilot__` set
  (the live v5 ones) and an older `SaintEloi__` v3 entry.
- **Terminal status is `success`.** `executed` is **TRANSIENT** — treating it as terminal reads
  `/api/jobs/{id}` before outputs register and silently loses renders (cost 12/288). The docs'
  `completed` also hangs forever.
- **Model import is BROWSER-ONLY** — no API endpoint, no MCP tool. Must be done in the Cloud UI.
- **Cloud CANNOT train** — hard 30-min per-workflow cap plus no Qwen trainer on the managed box.
  Render only.
- `search_models` is a **discoverable-models catalog, NOT the workspace registry.** Presence there
  does not mean imported. The real check is `/api/experiment/models/loras`.

### The jury
- **A dead panel prints `PASS=0` and looks exactly like a real verdict.** Two of three jurors had
  died (`kimi-k2.6:cloud` 403, `gemini-3-flash-preview:cloud` 410 Gone); with <2 decisions every
  image becomes INCONCLUSIVE → counted as fail. Nearly reported "v5 produces zero clean androids."
  A degradation guard now aborts if <2 jurors are live.
- **Live panel:** `minimax-m3:cloud`, `gemma4:31b`, `qwen3.6:27b`. Dead/no-vision: kimi, gemini,
  glm-4.6, deepseek-v3.1, gpt-oss, mistral-small, granite4.1, aya-expanse.
- ⚠ `qwen3.6` shares a lab with the Qwen-Image base that generated the renders. Tiebreak with
  `ai-eyes` (SigLIP2 — architecturally independent of every LLM).
- **Pass a class PREFIX** when several classes share an output dir, or android criteria reject
  every welded/human row for having flesh.
- **DEFER TO THE JURY on face-material** — but only via the reason breakdown, not pass-counts.

---

## 6. Tooling

`E:\AI\training\rustline_thicken\scripts\`

| script | purpose |
|---|---|
| `build_v6_density_waves_v2.py` | the v6c wave builder (individuals, class-inverted negatives) |
| `cloud_density_batch.py` | wave JSON → Cloud API graphs. Mirrors the local graph EXACTLY. |
| `cloud_run_density.py` | submit/poll/download, 8 in flight, resumable (skips existing) |
| `thicken_curate_jury.py` | cross-family jury — `<android\|welded\|human> <dir> [prefix]` |
| `jury_reason_breakdown.py` | decompose rejects by FLESH/FRAMING/ANATOMY/ARTIFACT |
| `v6b_class_sheet.py` | contact sheet, rows = individual |
| `v5_ckpt_ab.py`, `v5_ckpt_compare_sheet.py` | checkpoint bracket + comparison sheets |

**The graph must match the local one exactly** or the LoRA won't bind to the trained style:
`UNETLoader(qwen_image_fp8_e4m3fn)` → `LoraLoaderModelOnly` (**DiT-only, between UNET and the
sampling patch**) → `ModelSamplingAuraFlow(shift 3.1)`; CLIP `qwen_2.5_vl_7b_fp8_scaled` type
`qwen_image`; 832×1216; euler/simple; steps 22; cfg 3.5; weight 1.25.

---

## 7. ▶ NEXT ACTIONS

1. ~~Fire v6c~~ — **DONE 2026-08-23 03:29**, rendering into `out_v6c_cloud/`.
   ⚠ **The items JSON MUST be rebuilt first** — this was nearly missed. A stale
   `cloud_density_items_v6b.json` (02:38) predated the cast-direction wave rebuild (03:16) and
   contained ZERO of `pin-up` / `TANK`. Running against it would have submitted a duplicate of
   round 2 into a v6c directory and looked like it worked. **Verify the direction survives into
   the items file before submitting** (`grep -c pin-up`, `grep -c TANK`).
   ⚠ **Pass `v6b` as the WAVE_SET arg, never `v6c`** — it selects wave FILENAMES, and anything
   other than `"v6b"` also silently drops the **overlord** class via the `NAMES` ternary.
   ⚠ **Pass all three runner args explicitly** — the default out_dir is `out_v6_cloud` (binned),
   and because filenames carry no round marker, pointing at the wrong dir makes `dst.exists()`
   skip all 288 and exit clean having done nothing.
2. **Look at all four class sheets** before curating. Nothing is curated unopened.
3. **Curate** with the repaired jury per class + prefix, then the reason breakdown.
4. **Build the v6 dataset** — v5's 195 rows + the survivors. Target ~20 rows each for
   welded/overlord/human/rustblood. Captions are trigger-first content-only prose:
   `rustline style, a <class> <subject>, <scene>` — style vocabulary belongs to the trigger, NEVER
   the caption. Class must be tagged unambiguously.
5. **Train v6 on RunPod** — Cloud can't. RTX PRO 6000 Blackwell 96 GB ~$1.69/hr community,
   ~2000 steps ≈ 55 min + ~10 min base download ≈ **under $2**. `$RUNPOD_API_KEY` is on the rig.
   ⚠ Use `mounts.persistent`, NOT the console's "Network volume — Automatically create" (it
   survives the pod and bills monthly). Compensator: `DELETE /v2/pods/{id}`.
   ⚠ Poll **checkpoint files**, never the tqdm bar — a finished run reads `1999/2000`.
6. **Gate v6** properly — the harness v4/v5 never got: ckpt grids → caliper → A/B → cross-family →
   looked-at. Then write the CHANGELOG entry.

### Budget
**$7 for RunPod training** (Director). Comfy Cloud credits were expiring — **7000 credits, 3 days
from 2026-08-22** — which is why generation moved to Cloud.

### Also open
- `dataset_rustline_v3` has **82 images / 81 captions** — `_v3_STAGED_full.png` is an uncaptioned
  staging artifact inside the current production default's training set.
- **Sere (protagonist) finalization** — leather-longcoat wanderer direction picked; 10 variants at
  `rustline_thicken/out_sere_wander/`. Final design is the Director's.
- v4/v5 still ungated; `v3ckpt_1500 @ 1.0` remains the last *blessed* production default.

---

## 8. Standing rules
- **Look at every image before curating it.** Nothing curated unopened.
- **Aesthetic decisions are the Director's.** Surface variants; do not auto-judge a winner.
- **`E:/AI/training/` is a SHARED FLAT workspace** across projects — `_contact_ab_v4.png` /
  `_contact_ab_v5.png` belong to a DIFFERENT project. Only path-scoped dirs (`ab_rustline/`,
  `rustline_v5_ckpts/`, `dataset_rustline_v5/`) are trustworthy.
- **ferrochrome is RETIRED** (`56804ce`) — a from-scratch rebuild of a style rustline already had.
  Do not resurrect. Its cyclops work survives as **Gen-2 reference only** in
  `records/gen2-cyclops-design-convergence.md` + `outputs/gen2-cyclops-ref/`.
- Restart the VRAM watchdog before local GPU work:
  `pwsh -NoProfile -File E:\AI\training\_watchdog_start.ps1`
