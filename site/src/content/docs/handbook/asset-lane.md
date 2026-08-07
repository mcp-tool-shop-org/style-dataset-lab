---
title: The Asset Lane
description: Admitting accepted 3D asset exports as provenance-carrying training data — the asset-source.json contract, the validation ladder, and what the lane refuses to guess.
sidebar:
  order: 11
---

`sdlab ingest` takes bare images on trust. `sdlab asset ingest` takes a **contract**.

When a 3D asset passes its acceptance gate, re-rendering it from N angles produces a
turnaround that is view-consistent *by construction* — the property per-view diffusion
cannot guarantee. The asset lane admits those exports as training data without losing the
provenance that makes them trustworthy.

## The seam

**sdlab supplies mechanism; the asset supplies semantics.**

sdlab never raycasts, never renders, and never learns that a channel called "provenance" is
special. The manifest declares channels, palettes, classes, tolerances and gates; sdlab
proves those declarations against actual bytes, computes the declared measurements,
registers records and builds packages. What the numbers *mean* stays with the asset.

This line is why texture-space channels are hashed and carried but never projected into
render space — projection is rendering, and rendering is the asset's side of the seam.

## Running an ingest

```bash
# Validate the manifest end to end, run the gates, write nothing
sdlab asset ingest ~/exports/dragon_dense --project my-project --dry-run

# Register it
sdlab asset ingest ~/exports/dragon_dense --project my-project
```

The export directory may live outside the workspace — asset exports live where the asset
pipeline puts them. The source is read-only; every path the manifest references is
contained to the export directory, and every write stays inside the project.

## What lands

| path | contents |
|---|---|
| `records/<asset>__<render>.json` | uncurated records (`judgment: null`), `provenance.source: "asset"` |
| `outputs/candidates/<asset>__<render>.png` | the render, materialized |
| `assets/<asset>/` | manifest copy, silhouettes, channel instances, pairs, loss masks |
| `assets/<asset>/ingest-receipt.json` | every written path, every file hash — **the undo checklist** |

Records land uncurated on purpose. Admission to the lane is gated on the asset's recorded
acceptance verdict; admission to the *dataset* is still gated on your curation, exactly as
for every other record.

## The validation ladder

Every violation is collected and refused in **one** loud error. Nothing registers on a bad
manifest.

1. **Schema** — required blocks present, ids safe, palette bands well-formed, and an
   acceptance verdict that is literally `"accepted"`.
2. **Containment** — every referenced path resolves *inside* the manifest's directory and
   exists. The export directory is untrusted input.
3. **Encoding** — a PNG's IHDR must match its declared encoding; an NPY header must match
   its declared dtype and shape. *A manifest that looks right but disagrees with its bytes
   is the failure class this lane exists to stop.*
4. **Categorical proofs** — indexed PNGs prove PLTE ⊆ declared palette (structural, no pixel
   decode); `nearest`-filtered channels get an **exhaustive** pixel decode; categorical NPYs
   get an exhaustive value scan. `linear`-filtered channels are classified at ingest as a
   measurement with an honest unclassified share.
5. **Gates** — the palette gate runs per render using the manifest's own bands and
   thresholds. A failing render is rejected and reported; it never registers.

## Declaring the subject's style register

The manifest declares `asset.style`, and its shape encodes a hard-won rule: **the style
register is subject data.**

The rule was bought by a rejection. A painterly LoRA that two subjects had *earned*
acceptance under was applied to a third that should have read ultra-realistic. Nobody chose
that — it arrived by inheritance. So the register is now an authored property of the
subject, declared beside the palette bands, never derived from the dataset.

```jsonc
"style": {
  "register": {
    "terms": ["ultra-realistic", "menacing"],
    "ruling": "E12 Ruling 10b"
  },
  "lora": { "declared": "none" }
}
```

`style.lora` carries a required `declared` discriminator:

| `declared` | meaning | other fields |
|---|---|---|
| `"none"` | this subject runs with **no LoRA** — a decision, positively stated | `card` refused; `weight` absent or `0` |
| `"card"` | this subject runs a named card | `card` required (the **live** library name); `weight` optional |

**A missing `lora` key is refused, not read as "no LoRA."** That is the whole point: a
serializer that drops nulls, or an author who forgets, would otherwise turn a ruled *none*
into silence — and silence is what the rule exists to eliminate.

The block is optional (older manifests validate unchanged) but all-or-nothing once present.
When absent, records carry `provenance.style: null`, which is distinguishable from a ruled
no-LoRA register, and the ingest reports a gap notice.

## Declaring an upstream tone transform

If the generated views were tone-mapped before becoming projection sources — a colour
harmonization toward a reference view, say — declare it:

```jsonc
"tone_transform": {
  "kind": "lab-stats-transfer",
  "space": "CIELAB",
  "scope": "figure-mask",
  "reference": "y000_e00",
  "operands": "harmonize/operands.json",
  "reversible": true
}
```

**Why this must be declared:** this lane *measures colour*. The palette gate, the class
shares and the ΔE evaluation all produce numbers that sit downstream of any upstream tone
map. Pooling harmonized-source and raw-source assets in one training set is a legitimate
choice; making it unknowingly is not — and neither is comparing a ΔE from one against a ΔE
from the other.

**What sdlab checks:** that `reference` names a render this manifest actually declares (a
reference view missing from the export is dangling provenance), and that the operands file
is contained, parses, and hashes. The operands are *materialized* into the project rather
than left as a pointer — they are the only record of what the transform did to these
colours.

**What sdlab does not check, deliberately:** that the transform was applied, that the
operands are correct, or that the arithmetic is reversible. The lane records the asset's
claims; it does not verify semantics it does not own.

A render may opt out with `"tone_transform": false`. The ingest resolves that boolean once
and writes the answer into every record, so nothing downstream re-derives a default.

## Declaring how the renders came to exist

Not every render is a generated image. A dense turnaround is a set of **deterministic
derivations** of an already-accepted asset — re-renders by a fixed path. They have no seed
and no generation frame, and an export that omits `generation` for that reason is *correct*.

An export that omits it because nobody recorded the seeds is not. Only the manifest can tell
those apart, so it says which:

```jsonc
"render_derivation": {
  "kind": "emit",
  "generated": false,
  "record": "E11 Ruling 2"
}
```

| `generated` | effect |
|---|---|
| `false` | a per-render `generation` block is **refused** as a category error; the missing-generation notice is replaced by an informational one |
| `true` | `generation` blocks are validated normally; their absence is reported as a gap |
| block absent | same as `true` — saying nothing is not the same as saying "these are derivations" |

The refusal under `generated: false` is deliberate. A deterministic derivation has no seed
of its own, so declaring one attributes a seed to an image no seed produced. The generating
provenance of the twins a render was *projected from* is real and matters — but it belongs
to those twins, not to this record.

Records carry `render_derivation` beside `generation`, which is what makes the two kinds of
`null` distinguishable: a curator filtering for unknown-seed records must not sweep up
derivations that never had one.

## Declaring per-image generation provenance

```jsonc
"generation": {
  "frame": "full",
  "frame_detail": "route camera, yaw 0",
  "seed": 770701,
  "stem": "v9",
  "reroll_of": "y000_e00_770700"
}
```

Two measured phenomena make these fields load-bearing for curation:

- **Frame changes register.** Bust- and crop-framed generation drifts the style register
  away from the body it belongs to — observed three independent times.
- **Term binding is seed-dependent.** One seed resisted a prompt term across three
  independent stem versions while most of the image's pixels moved; the next seed bound it
  completely. Separately, one view's black-limb defect reproduced three times at that seed
  and cured all three times at the next.

A curator who cannot ask *"which records came from a crop frame"* or *"which came from that
seed"* cannot act on either finding.

`frame` is a **closed enum** — `"full"` or `"crop"` — for the same reason `facing` is a
derived vocabulary: it is the axis these phenomena were measured on, and a free-text field
where one asset writes `"bust"` and another `"head-crop"` cannot be grouped. Asset-specific
naming rides in `frame_detail`.

`seed` accepts a safe integer **or a digit-string**, because a seed too large for an exact
JSON number would silently lose its low bits — and a seed you cannot group on exactly is
useless for the purpose it is here for.

## Provenance notices

The lane reports what a manifest did not declare, without refusing it:

| code | kind | fires when |
|---|---|---|
| `ASSET_STYLE_UNDECLARED` | gap | no `asset.style` — the register is unknown |
| `ASSET_SUBJECT_NAME_ABSENT` | gap | no `identity.subject_name` — splits will guess subject families from id stems |
| `ASSET_GENERATION_PROVENANCE_ABSENT` | gap | some or all renders declare no `generation` |
| `ASSET_TONE_TRANSFORM_DECLARED` | info | a tone transform sits under every colour measurement on these records |
| `ASSET_RENDERS_ARE_DERIVATIONS` | info | renders are declared deterministic derivations, so a null `generation` is correct by declaration |

A **gap** is something the export could close. **Info** is something the manifest correctly
told you, which changes how the records should be read.

These are not gates. Existing manifests are legitimate training input and refusing them is
not on the table — but a gap nobody is told about is a gap nobody can close. Notices ride
in the receipt and replay on a re-ingest.

## Declare `identity.subject_name` before you cut a split

This one deserves its own warning.

`lib/split.js` resolves subject families by `identity.subject_name` first, and otherwise
**guesses** from the record-id stem. Two ingests of one subject under different asset ids —
a re-export, a superseded generation, a full-figure set and a crop set — strip to different
stems, read as **two families**, and let the same subject sit in both train and test.

Declaring `identity.subject_name` closes that. It is optional in the schema and nothing is
invented when it is absent, so the responsibility is real: **get it into the data before any
split exists.** Fixing it afterwards means re-cutting every split built without it.

## Idempotency and undo

Re-running an ingest with the same manifest is a no-op — the receipt's manifest hash is the
key. Re-running with a *changed* manifest refuses loudly: a changed export is a new truth,
not an overwrite.

The receipt lists every path the ingest created. That list is the compensator: deleting
those paths undoes the ingest completely.

## Reference

The full contract, the research grounding behind each decision, and the reasoning for every
schema version live in `docs/asset-lane-design.md` in the repository.
