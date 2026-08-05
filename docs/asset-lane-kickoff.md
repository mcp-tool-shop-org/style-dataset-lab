# Kickoff — sdlab asset lane: provenance-gated datasets from accepted 3D assets

> Written 2026-08-04 by the facet advisor, on the Director's instruction, the evening facet's
> first asset passed Gate 1. Committed into the repo per its own Step 0 — spec before work.
> A Step-0 verification addendum recording what the builder session found on disk (including
> one correction to this spec's claims) is at the bottom. Per studio law, disk beats spec.

You are a builder session in `E:\AI\style-dataset-lab`. Your deliverable is the skeleton —
contracts, commands, gates, and one fixture ingest. Not a training run.

## Step 0 — orient, and trust nothing inherited

`cd E:\AI\style-dataset-lab && git pull`

Read the repo's own CLAUDE.md, README, and package.json before anything. Worked example of
why: my own context holds two conflicting versions for this repo (v2.3.0 in one record,
v3.3.0 in another). Verify version, CLI surface (`sdlab --help`), project layout
(`projects/<game>/`), and the existing concepts — constitution/lanes/rubric/terminology,
briefs, curation, snapshots, training packages, eval packs — against the repo, not against
this document. An inherited claim is a hypothesis wearing a fact's clothes, including every
claim below. Commit this kickoff into the repo as `docs/asset-lane-kickoff.md` first — spec
before work.

Global rules that bind you: repo-first (verify `git remote -v`) · tests ship with code ·
shipcheck standards for any new command · the six workflow standards (block at the bottom) ·
GitHub Actions rules if CI changes.

## What this is

The flywheel: facet's pipeline now produces Gate-1-accepted 3D assets whose textures carry
per-texel provenance (reference / brush / dilation) and per-texel camera ownership. A
finished asset re-rendered from N angles is perfectly view-consistent by construction — one
texture, one mesh, it cannot disagree with itself. That is exactly the property per-view
diffusion lacks: facet measured two twins disagreeing about one bald scalp by ΔE 17.97 (the
"owner seam" defect class, E04 Ruling 1). Train LoRAs on asset-derived, provenance-gated
render sets and each accepted asset improves the generator that builds the next one — fewer
seams, higher reference share, better assets, more training data. sdlab is the studio's
canon-bound dataset pipeline; this lane is that idea made a product surface.

The seam that governs everything (learned twice this week, in facet's profiles and brand's
viewer): **sdlab supplies mechanism, the asset supplies semantics.** sdlab never learns the
word "provenance" as a special case, never raycasts, never renders. The asset's home repo
exports renders + masks + a manifest; sdlab ingests, curates, gates, and packages. If you
find yourself teaching sdlab about meshes, stop — that's facet's side of the line.

## What exists to build against (verify each on disk)

- **The W3 fixture** — facet's accepted warrior, `E:\AI\training\facet_E08\ARMB\out\`:
  `W3_final.glb` + `atlas_final.png` (4096², 68.8% reference / 4.2% brush / 27.0% dilation,
  measured), `provenance_atlas.png` (3 classes + background, indexed-PNG discipline per facet
  E09 Amendment 1), the `_owner.npy` standing sidecar (which view won each texel, int8, −1
  unstyled), 8 flat renders + 3 clay renders + provenance renders, exact silhouettes, the
  palette JSON with chroma floor, `profiles/character.json` in the facet repo.
- **Conditioning pairs** — every clay render ↔ styled twin pair facet has made, with
  silhouette masks: ControlNet-class training pairs, already on disk.
- **The measured baseline** for the eventual experiment: co-visible twin disagreement
  ΔE 17.97 / median 17.56 (facet `E04-task4d-report.md`, `e04_seam_sources.py`).

## Phase 0 — study-swarm (mandated; the studio protocol requires it for a new product layer)

Dispatch parallel research agents on these five, then lock architecture. Source standard:
author + year + title + URL + one-sentence finding; 6–8 well-sourced findings beat 20 vague
gestures. Run the citation gate through Crossref DOIs first — facet's RG01 lost 28 of 32
citations to arXiv rate-limiting by running the swarm and gate from one IP in one window.

1. **Masked/weighted loss in diffusion fine-tuning** — is per-pixel loss masking measured to
   work (inpainting-finetune and attention-masking literature)? This decides whether
   provenance masks gate admission (crop selection) or loss (per-pixel weights) — different
   package schemas.
2. **Multi-view consistency from turnaround training data** — what do MVDream/Zero123-class
   results say about teaching view consistency via finetuning, and at what dataset scale?
3. **Dataset composition for style-vs-subject LoRAs** — size, dedup, caption strategy, and
   the measured overfit risk of single-subject sets (one warrior = a warrior generator; the
   "pipeline, not a dwarf generator" trap in training form).
4. **Synthetic-render domain gap** — measured effects of training diffusion on rendered
   (flat-lit, clean-backdrop) images.
5. **Conditioning-pair value** — evidence on ControlNet/adapter finetuning from
   geometry↔styled pairs at small scale.

Findings go in a "Research grounding" section of your design doc, each connected to a
specific schema or gate decision. Citations without architectural consequence are noise.

## The skeleton — what you build this session

- **`asset-source.json`** — the ingest contract, schema first. One manifest per exported
  asset: mesh ref, atlas, channel files with `{id, role, encoding, palette?, filter}`
  (categorical channels: indexed PNG, PLTE = declared palette — the brand/E09 contract,
  reuse it), render set with per-render `{camera, light: "flat", silhouette_mask,
  loss_mask?}`, the asset's palette + chroma floor, and its acceptance provenance: the Gate
  verdict, date, and record link. Only Director-accepted assets are admissible — dataset
  admission is gated on his eye, which is the most canon-bound gate the studio has.
- **`sdlab asset ingest <project> <dir>`** — validates the manifest (every referenced file
  exists, hashes recorded, categorical PLTE ⊆ declared palette — port the proof-style
  check, not a pixel sample), registers into the project under the existing lane/snapshot
  machinery. Refuses loudly on schema violations; a wrong manifest that looks right is the
  failure class both facet and brand hit this week.
- **Admission masks** — per render, computed from the channels at ingest: reference-share
  per crop, and owner-seam-aware exclusion (the crown seam is reference-class paint —
  provenance alone cannot see it; distance-to-owner-boundary can; the `_owner.npy` sidecar
  exists precisely for this). Store masks beside samples in the training-package format;
  whether they gate admission or weight loss is Phase 0's Q1 decision — schema must allow
  both.
- **Curation gates, ported not invented**: palette conformance per render (bands come with
  the asset, never derived from the dataset — non-circularity); angular-stride dedup policy
  for turnaround neighbours (a knob with a why, not a magic number); view-conditioned
  captions (facet E01: a front-facing phrase on a rear view makes the text fight the image —
  captions must carry facing).
- **The eval-pack stub** — pre-register the consistency experiment now, run it never (this
  session): twins generated with the asset-LoRA vs without, co-visible ΔE on a new subject;
  baseline 17.97. Falsifiable, with the number already in the record.
- **Ingest the W3 fixture end to end** as fixture #1, against the renders that exist today.
  A second, degenerate fixture (a trivial asset with two channels) proves the schema isn't
  W3-shaped — the brand lesson: two subjects from birth, or the schema grows a bump you sand
  off later.

## Out of scope — refuse these even if momentum invites them

Any training run (needs the galleon landed, dataset volume, and its own watchdog-disciplined
session) · generating new renders (the dense-turnaround exporter is a facet-side spec,
later — consume what exists) · touching facet's live E04 line or its repo · reviving RG01 ·
GPU or cloud spend of any kind · publishing/version-bumping sdlab (skeleton lands on a
branch per repo convention; shipping is a later, gated step).

## Standards compliance (this kickoff)

| standard | score | evidence |
|---|---|---|
| PIN_PER_STEP | 2 | Schema-first with hashes recorded at ingest; fixture ingest is replayable; Phase 0 findings pinned with DOIs |
| ANDON_AUTHORITY | 2 | Ingest refuses loudly on schema/palette violations; the acceptance-provenance requirement halts unaccepted assets at the door |
| NAMED_COMPENSATORS | 2 | No irreversible action in scope: branch-only commits, no publish, no spend; undo is git |
| DECOMPOSE_BY_SECRETS | 3 | The seam is the design: asset semantics in the manifest, mechanism in sdlab; two fixtures prove it from birth |
| UNCERTAINTY_GATED_HUMANS | 2 | Admission gated on the Director's Gate verdict; the skeleton ends in a report to him, not a merged feature |
| EXTERNAL_VERIFIER | 1 | skip: for a skeleton — deterministic validation; the eventual experiment's verifier is the pre-registered ΔE measurement against a recorded baseline |

## Calibration

The facet arc that produced this idea falsified its advisor fourteen times in one day —
always by a session checking a claim against source or disk before building on it. Do that
here: verify sdlab's real surface before designing against my description of it, hash
predictions before artifacts exist where anything is measurable, and when a check's passing
is already known before you write it, that is precisely the check you may not adopt. A
negative Phase 0 finding — "masked loss doesn't work at LoRA scale" — is a full success: it
changes the schema before the schema exists, which is the cheapest correction there is.

---

## Step-0 verification addendum (2026-08-04, builder session)

Every claim above was checked against disk before work began. Results:

**Repo.** Version on disk is **v3.4.0** (released 2026-08-04, the dogfood-swarm release,
791 tests) — both inherited records the kickoff warned about were indeed stale (skill:
v2.3.0; canonical memory: v3.3.0). There is **no repo-level CLAUDE.md** — that Step-0
instruction resolves to the workspace-level rules. The v3.4.0 surface already includes a
plain `sdlab ingest <dir>` (bare uncurated candidates, `provenance.source: "external"`),
`sdlab measure` (deterministic palette/texture instruments via a Python bridge), and
`sdlab sheet` — the asset lane builds beside these, not over them.

**Fixture, verified present.** `W3_final.glb` (21.8 MB), `W3_prov.glb`, `atlas_final.png`
(4096²), `provenance_atlas.png`, 8 flat renders (`renders_flat/final_0..7.png`), 3 clay
renders (`renders_clay/clay_{0,4,6}.png`), 8 provenance renders
(`renders_prov/prov_0..7.png`), per-stroke workflow JSONs for all 8 cameras, exact
silhouettes at `masks/w3clay_0..7.png` + `masks/silhouettes.json`, `gate1_dE.json`. The
facet repo is at `E:\AI\facet` (located via the palette gate's own pointer);
`docs/experiments/E08-W3-palette.json` and `profiles/character.json` both exist there, as
does `E04-task4d-report.md` — the ΔE 17.97 baseline's source. The palette-gate contract
shape is confirmed: `min_chroma: 12.0` + named hue bands (`palette_gate_final.json`).

**Correction — the owner sidecar does not exist as described.** The spec claims an
`_owner.npy` sidecar, "which view won each texel, int8, −1 unstyled." No such artifact
exists anywhere under `facet_E08`. What exists is `ARMB\state\styled_mask.npy` — **bool**,
4096², styled/unstyled only. It carries the styled/unstyled distinction but not per-texel
view identity, and view identity is exactly what owner-seam-aware exclusion needs.
Reconstructing ownership from the stroke JSONs would require raycasting — facet's side of
the seam, forbidden here. **Consequence for the schema:** `view_owner` becomes an
*optional* channel role in `asset-source.json`; the owner-seam exclusion gate activates
only when an asset declares that channel; the W3 fixture ingests honestly without it. The
dense-turnaround exporter spec (facet-side, later) is where per-texel view ownership must
be emitted. Flag to facet when that spec is written.

**Boundary note.** Per-render admission masks are computed from *render-space* channel
images only (e.g. `renders_prov/prov_N.png`, silhouette masks) — pure pixel arithmetic.
Texture-space channels (`provenance_atlas.png`, a future owner atlas) are validated,
hashed, and carried, but never projected into render space by sdlab: projection is
rendering, and rendering is the asset's side of the seam.
