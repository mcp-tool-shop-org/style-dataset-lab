# Asset lane — design (skeleton session, 2026-08-04)

Status: **skeleton** — contracts, commands, gates, fixtures. Branch `feat/asset-lane-skeleton`.
Spec: [asset-lane-kickoff.md](asset-lane-kickoff.md) (committed first, with its step-0
verification addendum). This document locks the architecture after Phase 0 (study-swarm,
five parallel research agents, all findings source-verified).

## Standards compliance (this design + the code it specifies)

| standard | score | evidence |
|---|---|---|
| PIN_PER_STEP | 2 | Every referenced file's sha256 recorded in the ingest receipt; manifest itself hashed; measurement tool ids + schema versions stamped on records; Phase 0 findings pinned with DOIs below. Not 3: no replay harness yet — arrives with the first training run session. |
| ANDON_AUTHORITY | 3 | Ingest is collect-all-then-refuse on contract violations (nothing registers on a bad manifest); per-render palette-gate failures reject the render loudly and are reported, never silently admitted; `verdict !== "accepted"` halts at the door; encoding proofs compare declared vs actual bytes. |
| NAMED_COMPENSATORS | 2 | No irreversible action: branch-only commits, local writes only. Compensator per ingest: delete `projects/<p>/assets/<asset_id>/` + the `<asset_id>__*` records + copied candidates (receipt lists every written path); undo is `git clean`/`git revert` once committed. Owner: user. |
| DECOMPOSE_BY_SECRETS | 3 | Module boundaries are the design: `png-meta` (PNG format) / `npy-meta` (NPY format) / `asset-masks` (color math, ported gate) / `asset-source` (contract) / `asset-ingest` (registration side-effects). The manifest carries all semantics; sdlab carries none. |
| UNCERTAINTY_GATED_HUMANS | 2 | Admission is gated on the Director's recorded Gate verdict (the acceptance block is mandatory); records land uncurated (`judgment: null`) so human curation still gates dataset entry; the session ends in a report, not a merge. |
| EXTERNAL_VERIFIER | 1 | skip: deterministic validation only in the skeleton. The eventual experiment's verifier is the pre-registered ΔE measurement (below) against a baseline recorded before any training exists — a measurement, not a model grading itself. |

## The seam (restated because everything hangs on it)

**sdlab supplies mechanism, the asset supplies semantics.** sdlab never raycasts, never
renders, never learns that a channel called "provenance" is special. The manifest declares
channels, palettes, classes, tolerances, gates; sdlab proves declarations against bytes,
computes declared measurements, registers records, and packages. Texture-space channels are
hashed and carried but never projected into render space — projection is rendering, and
rendering is the asset's side of the line.

## Research grounding (Phase 0 → architectural consequences)

Five questions, five parallel agents, findings verified against Crossref/OpenReview/
publisher pages (arXiv fetched sparingly — the RG01 rate-limit lesson). Full agent reports
are session artifacts; the load-bearing findings and their consequences:

### Q1 — masked loss: works, but admission is the primary lever

- Avrahami et al. 2023, *Break-A-Scene* (SIGGRAPH Asia, DOI 10.1145/3610548.3618154): loss
  computed only inside concept masks learns per-region concepts — spatial loss masking
  demonstrably controls what is learned from where.
- Tang et al. 2024, *RealFill* (SIGGRAPH/TOG, DOI 10.1145/3658237): masked-objective LoRA
  fine-tuning on a handful of images beats all baselines — proven at exactly our scale.
- Wang et al. 2023, *Imagen Editor / EditBench* (CVPR, DOI 10.1109/CVPR52729.2023.01761):
  meaningful (object) masks beat random masks 68% in human comparisons — mask *semantics*
  carry the value, which is what provenance classes are.
- Dai et al. 2023, *Emu* (arXiv:2309.15807): a few thousand *curated* images beat scale —
  admission-side curation is the strongest-evidenced fine-tuning lever.
- Ju et al. 2024, *BrushNet* (ECCV, DOI 10.1007/978-3-031-72661-3_9): mask-specialized
  fine-tunes "frequently suffer semantic inconsistencies" — masks should modulate, not
  dominate.
- kohya sd-scripts masked-loss doc (practitioner): masks act at **1/8 latent resolution**;
  fine structures are invisible to loss masking. OneTrainer defaults: unmasked weight 0.1,
  10% unmasked steps — soft weights, never hard zeros.

**Consequences.** (1) The schema carries **both**: per-render `loss_mask` (grayscale
soft-weight image, first-class field) *and* per-render admission measurements (per-class
coverage shares within the silhouette). (2) **Admission-primary default**: packages select
on coverage stats; loss masks export as optional trainer inputs. (3) The dilation-fill seam
class is **sub-resolution for loss masking** — only admission stats can police it; that is
now the *measured* reason the per-render class-share computation exists. (4) No published
ablation compares the two levers directly — the eventual experiment should not claim one.

### Q2 — multi-view consistency: scope the claim honestly

- Liu et al. 2023, *Zero-1-to-3* (ICCV, arXiv:2303.11328): pose-conditioned fine-tuning at
  800K-object scale yields view *control*, not consistency — views sampled independently
  still disagree.
- Liu et al. 2024, *SyncDreamer* (ICLR, OpenReview MN3yH2ovHb): the ablation is decisive —
  identical multi-view data *without* cross-view attention machinery stays inconsistent.
- Long et al. 2024, *Wonder3D* (CVPR): smallest recorded full-model consistency scale is
  ~30K objects. Deitke et al. 2023, *Objaverse-XL* (NeurIPS D&B): quality rises
  monotonically with scale to ~100M renders.
- Kumari et al. 2024, *Customizing Text-to-Image Diffusion with Object Viewpoint Control*
  (SIGGRAPH Asia, DOI 10.1145/3680528.3687564): ONE object + ~50 posed views gives
  per-object viewpoint control; fails far from trained poses.
- Cheng et al. 2024, *Continuous 3D Words* (CVPR, arXiv:2402.08654): renders of a SINGLE
  mesh + LoRA + dedicated per-view tokens teach viewpoint control that transfers across
  prompts — **view tokens are load-bearing** at LoRA scale.
- Shi et al. 2023, *Zero123++* (arXiv:2310.15110): tiling fixed canonical views into one
  training image lets ordinary self-attention model the joint distribution — the one
  LoRA-compatible consistency trick, and independent validation that fixed canonical yaw
  sets (our 8) are the right export shape.

**Consequences.** (1) The eval pre-registration claims **appearance-lock for trained/
near-canon subjects**, not general consistency machinery — a per-view LoRA cannot install
cross-view attention, and the pre-registration says so. (2) **Per-view facing tokens are
mandatory caption material** (the facet E01 lesson is now literature-backed): records carry
a derived, deterministic `facing` field; manifests may override. (3) Camera fields take
arbitrary yaw/elevation strides — the future dense exporter should target 30–50 views/asset
(8 is a floor, per Kumari et al.). (4) A `tiled-views` package variant is noted as a future
training-profile option, not built now.

### Q3 — composition: one asset is a subject, never a style

- Ruiz et al. 2023, *DreamBooth* (CVPR, arXiv:2208.12242): 3–5 images bind an identity;
  small sets overfit without prior-preservation. Gal et al. 2023, *Textual Inversion*
  (ICLR): same regime. Eight renders of one warrior is identity-capture territory.
- Somepalli et al. 2023 (CVPR, arXiv:2212.03860) + Carlini et al. 2023 (USENIX,
  arXiv:2301.13188): duplication drives memorization; tiny datasets replicate near-verbatim;
  turnaround neighbours a few degrees apart function as near-duplicates.
- Somepalli et al. 2023, *Understanding and Mitigating Copying* (NeurIPS): **identical
  captions measurably increase copying**; caption diversity is an anti-memorization control.
- Shah et al. 2024, *ZipLoRA* (ECCV, DOI 10.1007/978-3-031-73232-4_24): style and subject
  train best as separate LoRAs. Frenkel et al. 2024, *B-LoRA* (ECCV): style/content
  concentrate in specific SDXL blocks — block-targeting is a low-diversity mitigation.
- StyleDrop (Sohn et al. 2023, NeurIPS) + fal.ai practitioner guide: style binds via a fixed
  trigger suffix on otherwise *varied, content-describing* captions; O(10–30) diverse-subject
  images suffice for a style.

**Consequences.** (1) The lane's unit is the **asset contribution to a style pool** — a
training package is built from N assets, and the schema never pretends one asset is a style
dataset. (2) **Angular-stride dedup policy** is grounded: at 45° all 8 views are distinct;
the policy field exists for dense exports (default: keep ≥30° neighbours, cluster below —
a knob with a documented why, tunable per package). (3) **Caption rules**: every record's
caption material must differ (facing token guarantees per-view distinctness); captions
describe what varies (subject, facing) + fixed style trigger + domain tag; the style is the
undescribed constant. (4) Package profiles carry `regularization` and block-targeting hints
as recorded knobs.

### Q4 — render domain gap: mitigations with precedent, encoded not improvised

- Shi et al. 2023/2024, *MVDream* (ICLR, OpenReview FUgrjq2pbB): fine-tunes on renders mix
  **70% render / 30% LAION** batches and append **", 3d asset"** to render captions —
  verbatim precedent for a domain tag and a photo-mix field.
- Liu et al. 2023, *Zero-1-to-3*: trained solely on white-backdrop renders → the backdrop
  became a permanent input constraint. Chen et al. 2024, *DisenBooth* (ICLR): backgrounds
  entangle into few-shot embeddings.
- Shi et al. 2023, *Zero123++*: re-rendered with random HDRI lighting and **gray**
  backgrounds (the SD VAE zero). Lin et al. 2024, *Common Diffusion Noise Schedules Are
  Flawed* (WACV): bright uniform backdrops interact with the terminal-SNR flaw.
- Ruiz et al. 2023, *DreamBooth*: regularization images counter few-shot drift.

**Consequences.** (1) W3's renders are RGBA — **background is applied at package-build
time** (pure compositing, sdlab mechanism): `background_policy ∈ {solid-gray (default),
solid-color, varied, keep-alpha}`. (2) Caption material carries a **domain tag** (default
`"3d asset"`). (3) Package manifests carry `photo_mix_ratio` (guidance field, default note
70/30) and `regularization` flags. (4) **Exporter-spec flags for facet** (render-time, not
sdlab's side): lighting variation across renders; 30–50 views; view-owner channel.

### Q5 — conditioning pairs: raw material now, package type at ~1k pairs

- Zhang et al. 2023, *ControlNet* (ICCV, DOI 10.1109/ICCV51070.2023.00355): robustness floor
  "small (<50k)"; limited-data ablation converges at ~1k with reduced generalization.
- Xu et al. 2024, *CtrLoRA* (ICLR 2025, arXiv:2410.09400): cheapest measured adaptation path
  — new condition as LoRA on a multi-task ControlNet base — needs **~1,000 pairs**.
- Nguyen et al. 2025, *Universal Few-Shot Spatial Control* (NeurIPS, arXiv:2509.07530):
  30-pair few-shot control exists but only inside a specialized meta-learned harness.
- Mou et al. 2024, *T2I-Adapter* (AAAI, DOI 10.1609/aaai.v38i5.28226): parameter efficiency
  does not reduce data appetite (600K pairs).
- HF *train-your-controlnet* (practitioner): narrow synthetic pair sets lose prompt adherence
  and leak the render look — the exact risk profile of clay pairs.

**Consequences.** (1) **No conditioning-pack builder this session.** (2) Records carry
**lossless pair linkage** (`pair.clay` path + sha256, camera, silhouette already present) —
thresholds activate suddenly and unlinked pairs cannot be reassembled retroactively.
(3) Promotion trigger recorded here: **first-class conditioning package type at ~500–1,000
accumulated pairs**, or earlier only if a UFC-class few-shot harness is adopted. (4) Clay
renders already have inference-time value against pretrained depth/lineart ControlNets —
no package needed for that.

## The contract — `asset-source.json` (schema_version 1.0.0)

One manifest per exported asset, living in the export directory. All paths are relative to
the manifest's directory and must resolve inside it (containment is enforced; the export
dir is untrusted input).

```jsonc
{
  "schema_version": "1.0.0",
  "asset": {
    "id": "w3_warrior",                    // assertSafeId — becomes the record-id prefix
    "source": "facet",                     // origin label, free-form
    "mesh":  { "path": "W3_final.glb" },   // optional; hashed when present
    "atlas": { "path": "atlas_final.png" } // optional; hashed when present
  },
  "acceptance": {                          // REQUIRED — the Director's gate, verbatim
    "gate": "gate-1",
    "verdict": "accepted",                 // anything else refuses ingest (ANDON)
    "date": "2026-08-04",
    "record": "link-or-path-to-the-ruling",
    "by": "director"                       // optional
  },
  "palette": {                             // facet palette-JSON shape, embedded verbatim
    "source": "docs/experiments/E08-W3-palette.json",   // optional provenance pointer
    "min_chroma": 12.0,                    // Lab C* floor — hue is undefined below it
    "allowed_bands": [ { "name": "warm", "hue_deg": [0, 105] } ],   // wraparound ok (lo>hi)
    "gate": { "max_offpalette_pct": null,  // null = WITHDRAWN (diagnostic only)
              "max_offpalette_blob_px": 800 }
  },
  "channels": [                            // channel TYPE declarations
    {
      "id": "provenance",
      "space": "render",                   // "texture" | "render"
      "encoding": "rgba",                  // "indexed"|"rgb"|"rgba"|"grayscale"|"npy"
      "categorical": true,
      "palette": [ { "name": "reference", "rgb": [64, 160, 64] } ],  // iff categorical
      "filter": "linear",                  // "nearest" ⇒ exact-color proof at ingest
      "classification_tolerance": 24,      // linear+categorical: max RGB distance
      "path": null,                        // texture-space only: the single file
      "dtype": null, "shape": null,        // npy only: proven against the actual header
      "note": "free text"
    }
  ],
  "renders": [
    {
      "id": "final_0",                     // assertSafeId
      "path": "renders_flat/final_0.png",
      "camera": { "yaw_deg": 0, "elevation_deg": 0 },
      "light": "flat",
      "silhouette_mask": "masks/w3clay_0.png",   // REQUIRED — exact silhouette (E08-A2)
      "channels": { "provenance": "renders_prov/prov_0.png" },  // type-id → instance path
      "loss_mask": null,                   // optional grayscale soft-weight PNG (Q1)
      "facing": null,                      // optional override of derived facing token
      "pair": { "clay": "renders_clay/clay_0.png" }             // optional (Q5 linkage)
    }
  ],
  "captions": {                            // caption MATERIAL (semantics), never captions
    "subject": "an armored warrior",
    "style_trigger": null,                 // optional fixed trigger token (Q3)
    "domain_tag": "3d asset"               // default; MVDream precedent (Q4)
  }
}
```

## Validation ladder (all violations collected, one loud refusal)

1. **Schema** — required blocks present, types correct, ids pass `assertSafeId`, verdict
   is literally `"accepted"`, palette bands well-formed, channel declarations coherent
   (categorical ⇒ palette; texture ⇒ path; npy ⇒ dtype+shape), render channel keys refer
   to declared render-space channel ids. Error: `ASSET_MANIFEST_INVALID` listing every
   violation with its JSON path.
2. **Containment + existence** — every referenced path resolves inside the manifest dir
   and exists. Errors: `ASSET_PATH_ESCAPE`, `ASSET_FILE_MISSING`.
3. **Encoding proofs** — PNG: IHDR color type must match the declared encoding
   (indexed=3, rgb=2, rgba=6, grayscale=0; interlace refused). NPY: header dtype/shape
   must match declaration. A declared encoding that disagrees with the actual bytes is
   `ASSET_ENCODING_MISMATCH` — the "wrong manifest that looks right" failure class.
4. **Categorical proofs** — indexed: PLTE ⊆ declared palette (structural chunk proof, no
   pixel decode; the brand/E09 contract). Non-indexed + `filter: "nearest"`: exhaustive
   full-decode proof — every non-transparent pixel's color ∈ declared palette
   (`ASSET_PALETTE_PROOF_FAILED` names the first offending color). Non-indexed +
   `filter: "linear"`: no admission proof; classification happens at ingest as a
   *measurement* with an honest `unclassified_share`.

## Registration (what `sdlab asset ingest` writes)

- `projects/<p>/assets/<asset_id>/asset-source.json` — manifest copy, byte-identical.
- `projects/<p>/assets/<asset_id>/ingest-receipt.json` — `{ingested_at, tool, schema
  versions, manifest_sha256, files: {relpath → sha256}, written: [every path this ingest
  created], rejected_renders: [...]}` — written last, atomically; the receipt is the
  compensator's checklist and the replay pin.
- `projects/<p>/assets/<asset_id>/{masks,channels,pairs}/…` — silhouettes, channel
  instances, loss masks, clay pairs (copied; hashed).
- `outputs/candidates/<asset_id>__<render_id>.png` — the trainable renders, atomic copy.
- `records/<asset_id>__<render_id>.json` — via the same `buildBaseRecord` as every other
  record: `judgment: null`, `canon: null`, **`provenance.source: "asset"`** (a third honest
  source alongside `generated`/`external`) carrying the acceptance block, camera, facing,
  hashes, channel/pair refs, and a `measurements` block (palette-gate numbers, class
  shares) stamped with tool ids. Captions are **not** invented; caption *material* rides
  in `provenance.caption_fields`.

Per-render palette-gate failures (against the asset's own declared gate) **reject that
render** — reported loudly, never registered; the receipt records the rejection. If every
render fails, the ingest fails.

## Ported gates (formula-faithful, cited)

- **Palette conformance** — ported from `E:\AI\facet\tools\palette_gate.py` (read-only):
  sRGB → linear → XYZ(D65) → Lab; C\* = hypot(a\*,b\*); hue = atan2(b\*,a\*) in degrees;
  in-band supports wraparound (lo>hi); off-palette = (C\* > min_chroma) ∧ ¬in-band ∧
  silhouette; **two numbers** — off-palette % (diagnostic; its bound is WITHDRAWN per
  facet 2026-08-04, it gates nothing) and largest 4-connected blob (the gate). Same
  constants, same mask threshold (>0.5), same semantics.
- **Class shares** — per categorical render channel: exact-match when `filter: "nearest"`;
  nearest-declared-color within `classification_tolerance` (RGB euclidean) when
  `"linear"`, with `unclassified_share` reported. Shares are computed for *every* declared
  class — sdlab never knows which class is "the good one"; the manifest's consumers do.
- **Angular-stride dedup** — recorded policy knob (`min_stride_deg`, default 30) with the
  Q3 memorization grounding as its why; enforcement bites at package-build (selection),
  not at ingest (records are truth; packages are choices).

## Pre-registered experiment (run later, never this session)

`docs/asset-lane-eval-preregistration.md` + a machine-readable stub registered with the
fixture project. Baseline recorded before any training exists: co-visible twin disagreement
**ΔE 17.97 mean / 17.56 median** (facet `E04-task4d-report.md`, `e04_seam_sources.py`).
Hypothesis (Q2-scoped): a LoRA trained on provenance-gated asset turnaround sets reduces
co-visible ΔE on a **new near-canon subject** vs the same pipeline without the LoRA —
appearance-lock, not consistency machinery. Falsifier: ΔE not reduced (or worsened) →
the flywheel premise fails at the first link and the lane stays a packaging surface.

## Out of scope this session (from the kickoff, unchanged)

Training runs · new renders · facet's live E04 line / repo writes · RG01 · GPU/cloud spend
· publish/version bump.
