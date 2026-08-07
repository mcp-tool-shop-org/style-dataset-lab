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
| EXTERNAL_VERIFIER | 2 | Implementation-diverse rather than model-diverse, and it has now fired twice on real data: this lane's JS palette gate (`lib/asset-masks.js`) reproduced facet's independent Python gate digit-for-digit — largest off-palette blobs **1738 / 1495 / 263 px** on the galleon's `y000_e00` / `y000_e40` / `y180_e40` — first from the staged manifest (facet E11 Ruling 1 credits it) and again 2026-08-06 from the dense tree. Two codebases, one formula, same integers. Not 3: no model-family verifier and no replay harness; the eventual experiment's verifier is the pre-registered ΔE measurement (below) against a baseline recorded before any training exists — a measurement, not a model grading itself. |

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

> **Status 2026-08-06.** Two of those three are answered by E11's dense turnarounds: 28 and
> 26 views (inside the 30–50 target's spirit, one subject just under), and the galleon ships
> the first native per-texel `view_owner.npy`. Lighting variation stays open and is ruled
> augmentation-side for now (E11 Ruling 5 ratifies flat-only export). Schema 1.1.0 below
> makes the owner channel *declarable*; note that declaring it is not yet *consuming* it —
> owner-seam exclusion remains unbuilt, and the channel rides as proven, hashed provenance.

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

## The contract — `asset-source.json` (schema_version 1.2.0)

One manifest per exported asset, living in the export directory. All paths are relative to
the manifest's directory and must resolve inside it (containment is enforced; the export
dir is untrusted input).

The block below is the 1.0.0 core, unchanged. The 1.1.0 and 1.2.0 additions follow it.

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

### Schema 1.1.0 additions (facet E11 Ruling 6, authored 2026-08-06)

E11's dense turnarounds ship per-view sidecars that rode **undeclared** beside the declared
channels: `owner_id_*.npy` (which stage-1 view owns each texel, int8, −1 unowned),
`admission_*.json` (facet's own per-view admission measurements) and `cam.json`. Undeclared
means uncontained, unproven, unhashed and absent from the record. 1.1.0 makes them
declarable. It does **not** make sdlab interpret them.

```jsonc
{
  "schema_version": "1.1.0",
  "identity": { "subject_name": "w3_warrior" },   // NEW — see below
  "channels": [
    {
      "id": "owner_id",
      "space": "render",            // NEW: npy is no longer texture-only
      "encoding": "npy",
      "categorical": true,          // NEW: categorical npy is supported
      "dtype": "|i1",               // must be readable: |i1, |u1, |b1
      "classes": [                  // NEW: integer classes, not an rgb palette
        { "name": "unowned", "value": -1 },
        { "name": "view_0",  "value":  0 }
      ]
      // NO channel-level "shape": each instance is proven against ITS render
    },
    {
      "id": "admission",
      "space": "render",
      "encoding": "json",           // NEW encoding
      "required_keys": ["view", "figure_px"]   // optional presence contract
    }
  ]
}
```

**What each addition proves.**

- **render-space `npy`** — header dtype matches the declaration, and the shape opens
  `[height, width]` against that render's own decoded dimensions. numpy is row-major, so a
  `[width, height]` export is a transpose; on a non-square render that is exactly the bug a
  shape check catches and a byte-count check does not. Rank 2 or 3 (a trailing channel axis
  is allowed). A channel-level `shape` is **refused** — one declaration cannot describe
  instances across differently sized renders, and declaring one invites the two to disagree.
- **categorical `npy`** — exhaustive value scan: every element must be a declared class
  value, and the first offending value is named with its flat index. The array analogue of
  the `filter: "nearest"` pixel proof: a class map has no antialiasing to forgive. Restricted
  to single-byte dtypes, and a categorical channel declaring a dtype the reader cannot decode
  is refused at declaration time rather than silently left unproven.
- **`json`** — parses, is an object, carries every declared `required_key`. **This proof is
  deliberately weak and the contract says so out loud**: sdlab does not read the values. A
  number in an admission sidecar means what the asset says it means; verifying semantics the
  lane does not own would be worse than declaring the boundary. `categorical: true` on a json
  channel is refused for the same reason — there is nothing sdlab could prove.
- **`identity.subject_name`** — the split engine's only *authored* subject-family key.
  `lib/split.js` resolves families by `identity.subject_name` first and otherwise **guesses**
  from the record-id stem. Two ingests of one subject under different asset ids (a re-export,
  a superseded generation) strip to different stems, read as two families, and let the same
  subject sit in train and test. Declaring it closes that. It is optional, and when absent
  nothing is invented — the record simply has no identity block.

**Why 1.1.0 and not 2.0.0.** Every addition is optional, so 1.0.0 manifests validate
unchanged — verified against all three field manifests (both E11 dense trees and the staged
W3). A major bump would refuse the very manifests E11 Ruling 2 named as the training input.
The gate is minor-aware in the other direction: a manifest declaring a **higher** minor than
the running sdlab is refused loudly, because accepting it would silently drop declared
channels this build cannot see — and an asset lane that quietly discards provenance is the
failure class the module exists to stop.

**Still undeclared, by choice:** nothing. `cam.json` is declarable as a `json` channel on
the same footing as `admission`. Whether a given export declares it is the exporter's call.

### Schema 1.2.0 additions (facet E12 Rulings 10b / 23f / 20a / 24b, authored 2026-08-07)

Where 1.1.0 declared **sidecars that already existed**, 1.2.0 declares **decisions and
measurements that were previously invisible to the lane** — three of them, each bought by a
specific finding in facet's E12/E13 arc.

```jsonc
{
  "schema_version": "1.2.0",
  "asset": {
    "id": "e12_dragon_dense",
    "style": {                                    // NEW — E12 Ruling 10b
      "register": {
        "terms": ["ultra-realistic", "menacing"],
        "ruling": "E12 Ruling 10b",
        "record": "docs/experiments/E12-ruling.md#ruling-10"
      },
      "lora": { "declared": "none" }              // or {"declared":"card","card":"<live name>","weight":0.85}
    },
    "tone_transform": {                           // NEW — E12 Ruling 23f
      "kind": "lab-stats-transfer",
      "space": "CIELAB",
      "scope": "figure-mask",
      "reference": "y000_e00",                    // MUST be a render id in this manifest
      "operands": "harmonize/operands_v3r.json",
      "reversible": true,
      "record": "docs/experiments/E12-ruling.md#ruling-23"
    }
  },
  "renders": [{
    "id": "y000_e00",
    "generation": {                               // NEW — E12 Rulings 20a + 24b
      "frame": "full",                            // closed enum: "full" | "crop"
      "frame_detail": "route camera, yaw 0",
      "seed": 770701,
      "stem": "v9",
      "reroll_of": "y000_e00_770700"
    }
    // "tone_transform": false  — optional per-render opt-out
  }]
}
```

#### `asset.style` — the register is subject data

E12 Ruling 10b was bought by a rejection. The saltroad painterly register, which two
subjects had *earned* acceptance under, was applied to a third that should read
ultra-realistic — and the Director rejected it. In the ruling's words it was *"a style
decision nobody made"*: it arrived by inheritance. The ruling: **the style register is
subject data**, every fixture names its register and its LoRA (or names none), and *"no
fixture may leave the section implicit again."*

That last clause is the whole design of this block. `style.lora` carries a required
`declared` discriminator with exactly two legal values:

| declared | meaning | extra fields |
|---|---|---|
| `"none"` | this subject runs with **NO LoRA** — a ruled decision | `card` refused; `weight` must be absent or `0` |
| `"card"` | this subject runs a named card | `card` required (the **live** library name); `weight` optional |

A missing `lora` key is **refused**, not read as "no LoRA." The difference matters
mechanically: a serializer that drops nulls, or an author who simply forgets, would
otherwise turn a ruled NONE into silence — and silence is exactly what the ruling was
bought to eliminate. `none` is a positive declaration.

The block itself stays **optional** (1.0.0/1.1.0 manifests validate unchanged), but it is
all-or-nothing once present: a register with no LoRA answer is the implicit section the
ruling forbids. When absent, records carry `provenance.style: null` — a value that is
*distinguishable from* a ruled no-LoRA register — and the ingest reports a **gap notice**.

The class roadmap now splits classes **by register** (`docs/style-registers.md` in facet):
a creature-companion is a different class from the beast because its register is tamer, not
menacing. The lane does not model that taxonomy; it carries the terms each asset declares,
which is what makes filtering a training pool by register possible at all.

#### `asset.tone_transform` — declaring what sits under the colours

Ruling 23f adopted facet's harmonization: a deterministic Lab colour-statistics transfer
inside the figure mask, toward a reference view, applied per view **before projection**.
Projection consumes the harmonized set; raw twins are retained beside it. The transfer is
generation-free and reversible, and its identity test held at 0 of 1,835,008 elements.

**The lane-side decision: yes, declare it.** The reason is not completeness — it is that
this lane *measures colour*. The palette gate, the class shares and the pre-registered ΔE
experiment all produce numbers that sit downstream of any upstream tone map. Pooling
harmonized-source and raw-source assets in one training set is a legitimate choice; making
it without knowing is not, and neither is comparing a ΔE from one against a ΔE from the
other.

The proof is structural and the boundary is stated out loud, exactly as with `json`:

- **Checked:** `reference` names a render **this manifest declares** (a reference view
  absent from the export is dangling provenance, and that is checkable); the `operands`
  path is contained inside the export, parses as a JSON object, and is hashed.
- **Not checked, deliberately:** that the transform was applied, that the operands are
  correct, that the arithmetic is reversible. sdlab records the asset's claims; it does not
  verify semantics it does not own.

The operands sidecar is **materialized** into the project — unlike the mesh, atlas and
texture channels beside it, which are hashed in place. It is small, and it is the only
record of what the transform did to these colours; leaving it as a pointer would make the
audit trail depend on the export tree surviving.

Per-render, `tone_transform: false` opts a render out. The ingest **resolves** the boolean
once and writes the answer into every record (`applied`, plus `reference_is_self` for the
reference view, whose transfer toward itself is identity), so nothing downstream re-derives
a default.

#### `renders[].generation` — two measured phenomena need two fields

Both of these were measured, not theorised, and both are **per-image**:

1. **Bust/crop-framed generation drifts register** — three independent instances (Ruling
   24b: companion orange → crop gloss → crop1 scarlet). Crop-owned regions read off-register
   against the body they sit on.
2. **Term binding is seed-dependent** — one seed resisted a prompt term across **three**
   independent stem versions (unnamed, compound, split) while 82.23% of the image's pixels
   moved, and the next seed bound it completely (Ruling 20a). Separately, one view's
   flat-black limb reproduced three times at that same seed across three stem versions and
   cured all three times at the next (Ruling 23d).

A curator who cannot ask *"which records came from a crop frame"* or *"which came from that
seed"* cannot act on either finding. Hence:

- **`frame`** is a **closed two-value enum** — `"full"` (the whole subject in frame) or
  `"crop"` (a sub-region at higher pixel density: bust, head-crop, detail). It is closed for
  the same reason `facing` is a derived vocabulary: this is the axis the phenomenon was
  measured on, and a free-text field where one asset writes `"bust"` and another
  `"head-crop"` cannot be grouped. Everything finer rides in `frame_detail`, which is the
  asset's own business.
- **`seed`** accepts a safe integer **or a string of digits**. The string form is legal
  because a seed too large for an exact JSON number would silently lose its low bits — and a
  seed that cannot be grouped on exactly is useless for the purpose it is here for.
- **`reroll_of`** names a superseded render. The bounded re-roll is the *lever* for
  seed-resistance, so a record that is a re-roll is itself a marker that a seed resisted.
  It is not required to resolve within the manifest: superseded artifacts are commonly
  retained upstream rather than exported.

#### Provenance notices — reported, never gated

None of the above is enforced at the door, because E11 Ruling 2 named the existing 1.0.0
dense manifests as the training input and refusing them is not on the table. What the ingest
does instead is **refuse to be quiet**. Every ingest now returns `notices[]`, carried in the
receipt and printed by the CLI, in two kinds:

| kind | meaning |
|---|---|
| `gap` | the manifest did **not** declare something a curator needs. Closing it is export-side work. |
| `info` | the manifest **did** declare something that changes how these records read. Nothing to fix. |

| code | kind | fires when |
|---|---|---|
| `ASSET_STYLE_UNDECLARED` | gap | no `asset.style` — the register is unknown to the lane |
| `ASSET_SUBJECT_NAME_ABSENT` | gap | no `identity.subject_name` — `lib/split.js` will guess families from id stems |
| `ASSET_GENERATION_PROVENANCE_ABSENT` | gap | some/all admitted renders declare no `generation` (counted: *n* of *m*) |
| `ASSET_TONE_TRANSFORM_DECLARED` | info | a tone transform sits under every colour measurement on these records |

Notices replay from the stored receipt on a re-run rather than being recomputed, so a
re-ingest reports the same gaps the original did — and a pre-1.2.0 receipt honestly has none.

**Why 1.2.0 and not 2.0.0.** Same discipline as 1.1.0, same reason: every addition is
optional, all three field manifests still validate, and a major bump would refuse the
manifests E11 ruled to be the training input. The gate stays minor-aware upward — a higher
declared minor is refused loudly rather than silently dropping channels this build cannot
see.

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
   must match declaration — texture-space against the declared `shape`, render-space
   against its render's `[height, width]` (1.1.0), plus a payload-length check that catches
   a file truncated below its declared shape. JSON (1.1.0): parses as an object and carries
   every declared `required_key`. A declared encoding that disagrees with the actual bytes is
   `ASSET_ENCODING_MISMATCH` — the "wrong manifest that looks right" failure class.
4. **Categorical proofs** — indexed: PLTE ⊆ declared palette (structural chunk proof, no
   pixel decode; the brand/E09 contract). Non-indexed + `filter: "nearest"`: exhaustive
   full-decode proof — every non-transparent pixel's color ∈ declared palette
   (`ASSET_PALETTE_PROOF_FAILED` names the first offending color). Non-indexed +
   `filter: "linear"`: no admission proof; classification happens at ingest as a
   *measurement* with an honest `unclassified_share`. npy (1.1.0): exhaustive value scan
   against declared integer `classes`, naming the first offending value and its flat index.

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
