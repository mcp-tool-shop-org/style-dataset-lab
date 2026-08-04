---
title: Reviewing candidates
description: Bring images in, triage them visually, and measure what the pixels actually are — before you spend a curation session on them.
---

Three commands sit between "images exist" and "a human has judged them": `ingest`, `sheet`, and `measure`. None of them makes a judgment. They exist so that when you do, you are looking at the right things.

## `sdlab ingest` — images that came from somewhere else

The pipeline can generate its own candidates through ComfyUI. Often it doesn't. A wave gets rendered on a cloud GPU, a freelancer delivers a folder, an older project has work worth reviewing under current canon. Those images had no way in: `reingest generated` needs a trained LoRA's manifest, and `reingest selected` needs a selection only the production loop can mint.

```bash
sdlab ingest ~/renders/wave-v2 --project salt-road
```

Each image becomes a bare record — `judgment: null`, `canon: null`, `provenance.source: "external"` — sitting in `outputs/candidates/`, ready for `sdlab curate` exactly like a generated one.

It will not invent anything. No judgment, no score, no caption. An ingested record is honestly empty until a person fills it in, and `eligibility audit` counts it as uncurated because it is.

If you have the wave JSON that produced the images, pass it and real provenance comes with them:

```bash
sdlab ingest ~/renders/wave-v2 --project salt-road --wave inputs/prompts/wave-v2.json
```

Filename stems are matched to item ids. Where a match exists you get the seed, the prompt and the model that made it. Where one doesn't, the record says provenance is unknown rather than guessing.

Re-running is safe — existing records are skipped, not overwritten or duplicated.

## `sdlab sheet` — see fifty images at once

Curation is deliberate, full-resolution work. Triage isn't. Before you decide anything, you want to know which of eighty candidates are even worth opening.

```bash
sdlab sheet outputs/candidates --project salt-road
# → outputs/sheets/outputs-candidates.html
```

An HTML grid: image, record id, current curation status, and the prompt if there is one. Images with no record yet fall back to their filename rather than breaking the sheet, so it works on a directory you have not ingested.

Images are referenced by relative path, not embedded. A 99-image sheet is about 110 KB and opens instantly. It is a review surface, not an artifact — regenerate it whenever, and it is gitignored for that reason.

It works on any directory, so the approved/rejected/borderline trees are fair game too:

```bash
sdlab sheet outputs/approved --project salt-road
```

That one is worth doing periodically. A wall of everything you have approved is the fastest way to notice your own drift.

## `sdlab measure` — what the pixels actually are

Everything else in the tool reasons about text: prompts, briefs, drift-guard keywords, constitution rules. `measure` opens the image.

```bash
sdlab measure outputs/candidates --project salt-road
```

It attaches two families of numbers to each record.

**Palette** — the share of pixels that clear a saturation/value gate (ignoring greys, shadow, tar), their mean saturation and value, and — when you supply anchors — how much of the image sits outside your anchor hues.

**Texture** — Laplacian variance and high-frequency ratio (how much fine detail is present), edge density and hardness, structure-tensor coherence in flat regions (whether brushwork has direction or is mush), and luminance spread.

These are ported from instruments built and validated against real production waves, not invented for this command.

### It does not judge

`measure` never sets `judgment`, never sets `overall_fit`, never approves or rejects anything. It gives you numbers; the decision stays yours. That line is deliberate: a tool that scores images and then acts on its own scores stops being a record of what a person decided.

Where a measure is undefined for an image, it records `null` — not zero. A perfectly flat image has no luminance variance, so anything normalizing by it is genuinely undefined, and `0` would read as a real measurement of a real property. The same applies to palette conformance with no anchors supplied: `off_anchor_pct` is `null`, because the question was never asked.

### Anchors

Anchor-free measures always run. Conformance needs to know what the palette *should* be:

```bash
sdlab measure outputs/candidates --project salt-road --anchors canon/anchors.json
```

```json
{
  "anchors": [
    { "name": "ochre-warm", "hex": "#c9a877" },
    { "name": "rust-deep",  "hex": "#a86b4c" }
  ],
  "hue_tolerance_deg": 20
}
```

Each gated pixel is assigned to whichever anchor's hue is circularly nearest, if it falls within tolerance; everything else counts as off-anchor.

### Python

`measure` needs Python 3.9+ with Pillow, numpy and scipy — the same shell-out pattern `sdlab generate` already uses for the Qwen bridge. Without them the command fails immediately with a structured error naming exactly what is missing. Pin an interpreter with `SDLAB_PYTHON` if you have several.

```bash
pip install pillow numpy scipy
```

Nothing else in `sdlab` requires Python. If you never run `measure`, you never need it.

## Where these fit

```
generate ─┐
          ├─→ sheet (triage) ─→ measure (numbers) ─→ curate (judgment) ─→ bind
ingest ───┘
```

`sheet` and `measure` are both optional and both re-runnable. Neither changes a curation decision; they change how much you know before making one.
