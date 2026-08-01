# SALT ROAD — Visual Art Contract

> The art contract required before any generation ([[feedback_art_contract]]). Salt Road
> defines its **own house style** — it does not consume `rustline` (grimy sodium-lit
> cyberpunk, wrong century and wrong weather for a trading port). This is a
> style-TRAINING project, the way rustline was.
>
> **Director's brief (2026-07-30):** *"a modern New Horizons (1990's SNES game)"* —
> a modern rendering of **Uncharted Waters: New Horizons** (Koei, 大航海時代II,
> PC-9801 1993 / Super Famicom 25 Feb 1994).
>
> Status: **DRAFT — awaiting the Director's ruling.** Nothing generates until he rules.

---

## 0. The correction this contract is built on

**The painted harbour is not an SNES screen.** New Horizons' ports are walkable tiled
towns; the official screen inventory (Koei/Nintendo 電子説明書 §5「港画面の見かた」, 2013)
names exactly seven elements — 宿屋 inn, 酒場 tavern, 港 harbour, 町の人 townspeople,
主人公 protagonist, 年月日 date, 時間 clock. No full-screen harbour painting appears
anywhere. The painterly register lived in the box art and in the PlayStation/Saturn FMV
openings the Super Famicom version never had.

So this contract is not reconstruction. **It builds the thing the game promised and the
hardware could not deliver** — which is also the entire documented method of the tier
we're aiming at: Matthias Linda on Chained Echoes, *"how I remember them to look like."*
**Memory-accurate, not hardware-accurate.** That sentence governs every rule below.

---

## 1. The look, stated

A fixed, walkable oblique port town — the counting house, the weighing floor, the bonded
warehouse, the customs shed and the long quay all legible on one screen under a running
clock — painted at the fidelity memory insists the 1994 game had. SNES palette discipline
is kept as a **rule, not a limit**: roughly fifteen values per material family, so tarred
timber, weathered oak, oxide-red brick, sailcloth and hemp each stay one legible ramp.
The silhouettes stay flat and readable. Exactly **one axis is added** — real-time
directional light: low harbour sun raking along the quay, lantern and window glow at
night, cast shadows under projecting hoist beams and warehouse fronts that lean out over
the water. Detail density lives in **stuff, not in pixel count** — marked casks stacked
three deep, coiled rope, tackle blocks, beam-scales hung from roof timbers, cart ruts,
bollard wear. Shore is dense, warm and cluttered; open water is cool, wide and empty, and
the contrast between the two is the emotional engine.

---

## 2. Style binding

- **Base:** Qwen-Image (Apache-2.0, NON-ANIME — never an anime checkpoint, ever;
  [[feedback_no_anime]]).
- **House style:** `saltroad` — a NEW trained LoRA, trigger-first prompting
  (`saltroad style, a <subject>, <scene>`). Style vocabulary belongs to the trigger, not
  the caption.

> **Director ruling 2026-08-01 — the surface clause is part of the recipe.** Production
> prompts close with **`, visible brushstrokes, painterly worked surface`**:
>
> `saltroad style, <subject>, visible brushstrokes, painterly worked surface`
>
> The trigger alone does not carry the plates' surface. The 73 plates were generated
> with a ~60-word preamble naming *"painterly gouache texture with visible brushwork"*;
> every evaluation sweep dropped it, so the LoRA was being asked to do a preamble's job
> from one token. Measured at n=8 fixed seeds, this clause moves stroke coherence
> 0.489 → 0.611 against a 0.689 plate target while landing within ~1% of the plates on
> texture amount (7.50 vs 7.42), edge crispness (3.40 vs 3.36) **and** the colour gate
> (10.9% yellow vs 11.0%). It generalises to interiors and material studies.
>
> Ruled from a four-rung ladder. **Not** the full preamble (19.1% yellow — its palette
> directives fight the LoRA that already solved colour) and **not** impasto/palette-knife
> wording (overshoots to 10.50 texture, and reads as oil, not gouache). The clause is
> generation-time only — it never enters training captions.
- **Training set:** 15–20 curated plates, locked BEFORE asset one. This is the single
  highest-risk step in the whole pipeline — style drift across a 50+ asset set is the
  documented failure mode, not seams.
- **Perspective is locked in Blender, never in the prompt.** A template `.blend` with a
  fixed orthographic camera supplies depth + normal + lineart passes per module; the LoRA
  supplies the paint. This is the studio's proven character path (concept → 3D → render →
  restyle) aimed at buildings.

## 3. Palette — material ramps, not a colour list

Fifteen-ish values per family, each family one legible ramp. The SNES 16-colour
sub-palette constraint (Copetti, *Super Nintendo Architecture*) is the discipline that
makes a scene read; it is not nostalgia.

| Family | Anchor | Note |
|---|---|---|
| Limewash façade | ochre-warm `#c9a877` · ochre-red `#a86b4c` | **Batch-variable by law** — see §4 |
| Quay stone | wet grey-blue `#5f6b70` · dry pale `#a99e8c` | The wet lip is a different ramp, not a darker one |
| Tarred timber | `#2b2521` | Pitch black-brown; the harbour's darkest structural value |
| Weathered oak | `#8a6f4e` | Doors, hoist beams, cart beds |
| Oxide brick | `#8c4a35` | Warehouse and crane towers |
| Sailcloth | `#d8cfba` | Canvas, awnings, bales — the scene's off-white |
| Hemp / rope | `#b09468` | Rope, netting, sacking |
| Sea | cool `#2f4a52` → `#1b2f38` | Deliberately PLAINER than the land |

**Ochre is the only pigment class used on façades** — red and yellow ochres are the
mineral pigments least likely to fade, and they are what a 16th-century port actually
wore (Bennett, *Awash with Colour*, Building Conservation Directory 1997).

> **Director ruling 2026-07-30 — exposed timber framing ADMITTED.** On the wave-2
> evidence (the alley, the laundry courtyard, the cat on the wool bales) the Director
> admitted half-timber construction to the material table: tarred structural frame
> with brick or limewash infill, worked and industrial, never Tudor-decorative.
> Ramp: tarred frame `#2b2521` + infill from the limewash/brick families above.

## 4. The visual laws (load-bearing)

1. **Limewash is never flat.** It dries many shades lighter than it goes on and cannot be
   re-matched batch to batch. A harbour front is a **patchwork of near-miss tones** with a
   faint calcite surface glow. A row of identical façades is the tell of a fake port.
2. **Vertical logistics is the subject.** Hoist beams project 75–90 cm from the façade
   with ship-rigging tackle; façades are built **op de vlucht — leaning forward** so loads
   clear the wall (Vereniging Vrienden van de Amsterdamse Binnenstad). If a warehouse does
   not lean over the quay, it is a house.
3. **The crane is a building, not a prop.** Two masonry towers with the timber hoist slung
   between them, treadwheels inside (National Maritime Museum Gdańsk). Draw it as
   architecture.
4. **Cargo is marked, and the marks are graphic design.** Four mark systems — cooper's,
   quality, ownership, accounting — plus merchants' marks as initials intertwined with
   crosses and abstract line-figures, legible to an illiterate workforce (Oosterbaan,
   Leiden 2026). Unmarked barrels read as furniture; marked ones read as someone's money.
5. **A working quay is chokingly undersized.** London's Legal Quays: 1,775 vessels
   competing for berthing built for 545. Crowd it.
6. **Light is the ONE added axis** — and it is added as light, then geometry. Octopath's
   own 2D artist tried faking dramatic lighting in the art and was told it wasn't enough;
   3D elements entered only after. Light first, geometry second, never texture-painted
   fake shadow.
7. **Density is stuff, not resolution.** *"If you just make your pixels thicker then all
   you're doing is creating the same look as back then"* (Takahashi, Octopath) — and its
   twin, *"making the graphics too finely detailed lost what makes the pixel art great"*
   (Miyauchi). Add objects, not pixels.
8. **70:30.** At least 70% of any plate stays flat, filler or negative space; detail
   concentrates in 2–3 focal clusters per screen. Every prop needs scale/rotation variants.

## 5. NOT THAT

- ❌ **Anime.** Any register, any weight, any checkpoint. Non-negotiable.
- ❌ **Fantasy.** No magic, no dragons, no glowing runes. This is a trade port in the real
  early-modern world; the drama is money, weather and someone's name on a register.
- ❌ **Pirate-romantic.** No skulls, no tricorn swagger, no treasure chests. The bonded
  warehouse is scarier than a cutlass.
- ❌ **Grimdark / rustline.** Not grimy-for-its-own-sake, not sodium-lit, not dystopian.
  Salt Road is *worn and working*, which is a different thing from ruined.
- ❌ **Glossy 3D render, vector flat, or airbrushed "HD remaster" smoothness.**
- ❌ **Uniform façades, unmarked cargo, an empty quay, a decorative crane.** Each is a
  named law above, inverted.

## 6. Projection and camera

- **Oblique, fixed, viewer-facing** — the New Horizons town grammar: buildings face the
  camera with visible doors you walk into. Not isometric, not true top-down.
- **48px tiles authored at 96px** (the painterly band); characters **2–3 tiles tall**.
- **Sea and any map layer stay flat top-down and deliberately plainer than the land** —
  the original's Mercator world map is the reference, and the plainness is intentional.

## 7. What to depict — Salt Road's own plates

Keyed to the frozen world ([[2p5d-c4-reference-diorama-complete]]; the prose is
Director-frozen and the art bends to it, never the reverse):

| Plate | Zone | The thing that must read |
|---|---|---|
| The Counting House | `counting-house` | A standing desk, a ledger, a wax jack burned to a stub; the window faces the water |
| The Weighing Floor | `weighing-floor` | Six brass beam-scales, only the third one trusted; a queue that forms before the doors open |
| The Bonded Warehouse | `bonded-warehouse` | The door that does not open without a seal — a lean-forward façade, hoist beam, someone's name on the register |
| The Long Quay | `long-quay` | The crane as a two-towered building; a wet stone lip that does not look wet; hawsers coiled chest-high |
| The Customs Shed | `customs-shed` | The stamp, the tally, the marks on every cask |
| The Crooked Stair | `crooked-stair` | Twenty-two steps, not one the same height as the last |

## 8. Gates (do not skip)

- **Look at every image** ([[feedback_look_at_images]]) — never curate or describe
  unopened output. Judge at FULL RES, never off a montage thumbnail
  ([[feedback_judge_concepts_at_full_res]]).
- **ai-eyes has veto** ([[feedback_vision_veto_doctrine]]) — with the standing caveat that
  it cannot grade fine structure ([[ai-eyes-cannot-grade-fine-structure]]); calibrate on a
  known-answer pair before trusting it on anything.
- **Director taste gate.** Look and content voice are his
  ([[feedback_the_discriminator_means_play]]). The style set is ruled on before the LoRA
  trains; the LoRA is ruled on before assets generate.
- **Human finishing pass on anything the camera rests on.** Across three years of Steam
  data, AI *art* is the disclosure category worst-correlated with commercial outcome, and
  the detection threshold is one unfixed artifact. This is a commercial requirement, not
  polish.

---

**Sources** — Koei/Nintendo 大航海時代II 電子説明書 (2013) · Koei US manual (1994, archive.org)
· Werkema, *New Horizons: A Hidden Gem on the SNES* (2026) · Copetti, *Super Nintendo
Architecture* · Koei Tecmo 大航海時代 Origin press release (2023-03-07) · Linda interview,
Turn Based Lovers (2022) · Boulanger interview, ScreenRant (2023) · Takahashi & Miyauchi
via Nintendo Everything (2018/2022) · Vereniging Vrienden van de Amsterdamse Binnenstad,
*Hijsbalken* · National Maritime Museum Gdańsk · Oosterbaan, Leiden University (2026) ·
Bennett, *Awash with Colour*, Building Conservation Directory (1997).
