# Rustline — style & world canon

> Authored 2026-06-17. Direction set by Mike: serious, grounded cyberpunk in the SNES-Shadowrun
> register (grimy under-city, **NO neon**), an all-**android** character cast. Art direction locked
> from validated test renders (`_cp_test`); subjects drafted by the studio canon author
> (`mistral-large-3:675b-cloud`), refined to the depictable register. Canon = training data for the
> style model: every detail concrete and depictable.
> **Trigger word: `rustline`.** **STATUS: APPROVED BY MIKE 2026-06-17 (step-1 gate) — 10-android cast locked as baseline; adjust as/if needed.**
>
> *(Supersedes the abandoned `brass_requiem` / chrome-noir direction. Scope: 10 character androids,
> no machine-enemy bestiary — Mike, 2026-06-17.)*

## ⚡ NEON AMENDMENT — environment-noir, grounded cast (Mike, 2026-06-18)

Rustline's founding militant NO-neon rule is **amended** (not abandoned) after the v1 positive-neon
probe and a seed-aligned Phase-A look test (`E:/AI/training/rl_experiment/phaseA_neon/`,
contact sheet `_phaseA_contact.png`). **This section is the authority where it conflicts with the
NO-neon language below.** The amended canon rule:

- **Environment / establishing plates MAY use the neon-noir register** — magenta/cyan electric neon
  signage as moody, **low-key** atmosphere over the grounded base; still grimy, wet, smog-hazed,
  never bright or clean. This is the "neon done well" look Mike approved from the probe.
- **The character cast STAYS GROUNDED** — androids keep the rust-brown / sodium-amber master palette
  (warm sodium light, dull-amber optics). **No saturated electric magenta/cyan neon lighting ON
  character bodies.** The cast's grounded identity is what makes rustline rustline, not generic
  neon-cyberpunk.
- **"No neon" always meant no SATURATED ELECTRIC neon** — warm sodium/amber practical signage was
  always part of the grounded base (it shows up even under the full no-neon negative).

**Dataset implication (Mike's Phase-A call):** v2 gains a **small curated neon-noir ENVIRONMENT
exemplar set** so the LoRA bakes the register into backgrounds; **cast exemplars stay grounded** (no
neon-lit character training images). Neon on characters remains forbidden at training time.

**Generation rule of thumb:** environment plates → neon-noir register (allow neon, keep holograms /
bright daylight / clean-utopia in the negative). Character portraits & sprites → grounded register
(keep "neon, saturated colour, human face, bare human skin" in the negative, warm sodium lighting).

## ⚙ HESPERIA ALIGNMENT — rustline is the game's grounded visual system (Mike, 2026-06-19)

Rustline is the **house style for the game HESPERIA** ([[hesperia-game-state]]); the 10 androids below
ARE Hesperia's playable cast (Gen-1 recruits under the authored protagonist **Sere**). Forming the style
to the game canon, before the v3 train, expands rustline from "10 grimy androids" into Hesperia's full
GROUNDED visual system. **This section + the NEON AMENDMENT are the authority where they extend the
2026-06-17 base.** The five game-side calls (Mike, via the Hesperia session, 2026-06-19):

- **Gen-1 = rustline (this LoRA), all-in GROUNDED.** The whole cast is Gen-1 (empathetic, decommissioned,
  under-city). Everything in this canon is the grounded register.
- **Gen-2 = a SEPARATE small LoRA, NOT this one.** The enemy androids are the photographic NEGATIVE of
  this style — sleek, clean, glossy, bright, holographic (the "NOT THAT" column). That look is DELIBERATE
  for Gen-2 but lives in its own future LoRA; **rustline must NOT learn it** (the v2 Ironclad sleek-bleed
  is exactly why they're split). Keep sleek/clean in the rustline negative.
- **Humans + cyborgs are now IN-SCOPE (grounded).** The `humans` must-not is LIFTED — Hesperia has people.
  They render in the SAME grounded painterly warm-sodium grime, **never clean**:
  - **Humans (the Sealed / Wren / Sam):** **tower-born and FRAGILE** — pale, sheltered, soft (atrophied,
    not the androids' hard scuffed builds); only grimy once *fallen* into the under-city; soured-air
    sickness, rebreathers/masks, patched clothing over sealed-environment dress. Fragility reads distinct
    from android grit and Welded scrap. (**Wren** = recruitable human party member, tower-born mender,
    Sam's apprentice — the first grounded-human exemplar target.)
  - **The Welded (cyborgs) = a flesh↔machine SPECTRUM. They keep a HUMAN FACE + flesh base — that is
    exactly what separates them from androids** (augmented humans, not synths):
    - *Rank-and-file Welded* (recruitable betweeners): mostly FLESH + crude jury-rigged survival augment —
      scrap-metal limbs, crude rebreathers, patched cybernetics, exposed wiring on (human) skin, rust + grime.
    - *Ruling bad-cyborgs* (a fallen, devoured remnant): mostly MACHINE — cold controlled clean-tech augment
      on a human frame ("what the makers became"), but rendered **DAMAGED + corroded** (never pristine —
      pristine-clean = Gen-2 LoRA only). A human face/eyes still show through the cold machine.
    - Axis: human → rank-file Welded → bad-cyborg (corroded cold-machine) → [Gen-2 clean, separate LoRA].
- **THE HUMAN ↔ ANDROID LINE (load-bearing for v3 training — cross-family flag).** The dataset now teaches
  TWO opposite flesh rules at once: **humans + Welded HAVE bare human flesh + human faces; androids NEVER do**
  (synth faceplate, plated body — the no-bare-skin-on-androids rule that v2 Gristle violated). Mitigation:
  every exemplar caption must **tag its class unambiguously** (`an android …` / `a human …` / `a welded
  cyborg …`), the classes stay **dataset-balanced**, and android synth-face *seams/damage* must read as
  **mechanical (panels, optics, cabling), never as exposed flesh**. This is v3's hardest separation — get
  the captions + class balance right or the model blurs human↔android.
- **Protagonist Sere — STORY-MOTIF STUB ONLY (final design = Mike).** An **ancient, companion-era make**
  Gen-1 (Earth-built for the generational voyage → a distinct archaic design language; reads as the lead),
  a **voice-of-the-voyage / chronicler** unit, reactivated-rough, with a **conspicuous EMPTY core-socket**
  ("the man with the hole" — his extracted founding-memory is the Communion's relic). Keep these motifs; do
  NOT lock palette/silhouette beyond "distinct ancient lead."
- *(The Steward — a courteous Gen-2 "diplomat" antagonist — is a named Gen-2 face; belongs to the future
  separate Gen-2 LoRA, not rustline.)*

**Cross-cutting motifs (canon-wide, load-bearing):**
- **The decommission brand.** Every Gen-1 was decommissioned via the Fidelity Assay for "feeling too much"
  — a **branded/stamped failing-empathy mark** on the chassis is the cast's shared badge of their "defect"
  (their death-certificate, worn on the body). **Vary it physically per character** (a struck plate, an
  etched score, a riveted tag, a stencilled number) — NOT one fixed glyph/legible text, or the model
  over-fits it as a watermark and hallucinates it everywhere.
- **Memory-cores as relics.** Extracted Gen-1 cores are sacred salvaged objects (Sere's missing core; the
  Saint cradles one) — a recurring object in the visual language.
- **Faction bearing:** Communion = devotional/reliquary · Scrip = scavenger/cargo-tags · Decommissioned =
  militant/scarred · keeper = archival. (Per-character cues in the Cast section.)

**v3 dataset implication (the STRUCTURAL fix — v2's two misses were texture, not structure):** Gen-1 cast
exemplars need **full limb + torso coverage** (NOT chest-only inpaint — that left bare muscular human arms
on Gristle); Ironclad needs a **broken-silhouette grimy brute** form (not a rust-skinned sleek shell); add
**human + Welded exemplars** (the new grounded categories, class-tagged + balanced per the human↔android
line). Gen-2 = a separate later dataset/LoRA. **Environments** beyond the under-city (the Towers = clean
Gen-2 register; the surface hazard regions = grounded variants) are the **Hesperia world-plates' scope**
(`projects/hesperia/`), not this character canon — rustline supplies the grounded paint.

## Premise
**Rustline** is the corroded lower districts of a megacity — rust, scrap, leaking pipes, and
perpetual drizzle in the grime below the corporate towers. Its people are **androids**: cast-off,
repurposed, and worn-down synthetic humanoids scraping by in the murk. Working-class cyber-grit: no
chrome utopia, no neon glamour — wet concrete, dim sodium light, and survival. Grounded, grim, lived-in.

## Art direction (the style canon)
- **Rendering:** gritty **painterly-cinematic** concept art; heavy **low-key chiaroscuro**; film
  grain; rain-wet grime; smog haze; matte, desaturated surfaces. Non-anime.
- **Master palette:** concrete-grey `#6b6e70` · rust-brown `#7a4a2b` · sodium-amber `#c8862f` ·
  soot-black `#16140f` · synth-bone (android off-white) `#cbc6b6` · toxic-green `#5b6b4a`.
- **Lighting:** dim sodium glow against cold shadow; wet reflective asphalt; smog/haze; deep low-key.
  Described as an **effect** (warm amber highlights, deep shadow) — never a light-source object. **No
  electric neon on the cast** (warm sodium only); **neon-noir lighting is for environment plates
  only** — see the Neon Amendment above.
- **Silhouette language:** grounded, **human-scaled android figures** — weary, hunched, coated,
  scuffed. Each has a **present synthetic head/face** (damaged or shadowed is fine, **never headless**)
  and a **plated torso** (an assembly of panels — **never an exposed organic-style ribcage**). Builds
  vary across the cast (lanky, blocky, squat, petite, stooped) so each reads distinct at 64px.
- **Android materials:** *synth-plating* (scuffed matte off-white/grey panels) · a *synthetic face*
  (seamed, sometimes part-stripped) · *exposed mechanism* (gears, pistons, cabling at jaw, neck,
  shoulder, joints) · *rusted steel limbs & riveted patches* · *frayed cabling & oily hydraulics*
  (black leaks) · *worn human cloth* (coats, work-gear, aprons, wraps) · *dead/cracked sensor-optics*
  (a dull dim-amber glint at most).

| THIS | NOT THAT |
|---|---|
| gritty painterly cyberpunk noir | clean vector / cel-shading / anime |
| dark muted grey-rust-sodium | **neon, holograms, saturated colour** |
| grounded worn androids | sleek clean sci-fi robots / plastic |
| present synthetic head + plated torso | headless / exposed-ribcage skeleton |
| dim sodium light + wet shadow | neon glow / bright even daylight |
| rust, scrap, rain, smog, concrete | polished chrome utopia / brass Victoriana |

**STYLE DESCRIPTOR (locked prompt prefix):**
> gritty hand-painted cyberpunk concept art, dark muted desaturated palette of concrete grey
> rust-brown and dim sodium-amber, heavy low-key chiaroscuro, rain-wet grime and smog haze, lived-in
> dystopian squalor, film grain, matte painterly

> **Dataset-craft notes:** (1) **Neon per the amendment** — for CHARACTER/cast exemplars put
> neon/holograms/saturated-colour in the negative (cast stays grounded); for ENVIRONMENT plates use
> the neon-noir register (allow neon, keep holograms/bright-daylight/clean-utopia in the negative).
> (2) Light is an EFFECT ("warm amber highlights, deep shadow"), never a source noun
> (the tallow_fen lantern / brass-pilot lamp lesson). (3) Every android keeps a **present head** and a
> **plated torso** — put "headless, skeleton, exposed ribcage, organic bones" in the negative (the
> base model's skeleton prior is strong; it produced an undead-dog in the brass pilot). Validated on
> the base in test wave `_cp_test`.

## Character androids (the cast — 10)
- **Gutterjack** — *rogue scavenger; works the scrap-rivers.* A hunched, lanky synth in patched scuffed
  off-white plating; a scavenged tarp worn like a poncho; exposed neck-gears and frayed cabling;
  knee-high rusted steel shin-guards. *64px:* a jagged hunched figure, long arms, tarp flaring.
  *Palette:* `#cbc6b6`, `#7a4a2b`, `#16140f`. *Features:* a single cracked optic with a dull amber
  glint; oil-stained fingers; rust-flaked tarp edges; wet exposed jaw-hydraulics. *Forbidden:* a sleek
  clean android with bright glowing eyes; a neon scavenger.
- **Ironclad** — *corporate enforcer; the towers' brute squad below.* A broad, heavy android in matte
  scuffed concrete-grey plating; reinforced rust-edged steel pauldrons; exposed oily chest-hydraulics;
  a visored helmet-head with a dull amber light-leak at the slit. *64px:* a blocky figure — square
  shoulders, visor slit, no neck. *Palette:* `#6b6e70`, `#7a4a2b`, `#c8862f`. *Features:* a cracked
  visor leaking dull amber; rust streaks down the pauldrons; frayed wrist-cabling; boots caked in wet
  concrete. *Forbidden:* a glossy corporate cyborg with a holographic HUD; sleek sci-fi armour.
- **Scrap-Saint** — *cast-off preacher; venerates the rustline's decay.* A gaunt, tall synth in peeling
  off-white plating, **head bowed under a hood** of scavenged wet rags (face shadowed, present); an
  exposed oily chest-mechanism showing through an open robe; hands wrapped in frayed cabling.
  *64px:* a tall draped figure, bowed hooded head, robe trailing. *Palette:* `#cbc6b6`, `#7a4a2b`,
  `#16140f`. *Features:* a bowed hooded head; an open robe over a wet chest-mechanism; rust-stiff rag
  hem; cabling-wrapped hands. *Forbidden:* a skeletal or headless figure; an angelic android with a
  glowing halo.
- **Rustblood** — *back-alley mender (street tech-doc).* A wiry, hunched synth; limbs wrapped in frayed
  canvas strips; a patchwork-plated torso; **one arm stripped to bare hydraulics**; a present seamed
  face with a cracked magnifier-lens flipped over one optic. *64px:* a lopsided hump-back, a sagging
  tool-belt, one thin piston-arm. *Palette:* `#16140f`, `#5b6b4a`, `#cbc6b6`. *Features:* the flip-down
  magnifier-lens; an oily rag in the belt; rusted needle-driver fingers; exposed shoulder-cabling.
  *Forbidden:* a sterile clean-room medic android.
- **Dockrat** — *harbor laborer (scrap-hauler).* A squat, barrel-chested synth, legs bowed from years
  of load; a dented steel-drum torso; arms in chain-link sleeves; a blunt present face. *64px:* a wide
  low block, chain-wrapped forearms, no neck. *Palette:* `#7a4a2b`, `#6b6e70`, `#16140f`. *Features:* a
  rusted hook replacing the left hand; an oil-leaking shoulder joint; cargo-straps fused to the plating;
  a cracked pressure-valve on the chest. *Forbidden:* a sleek agile courier android.
- **Hushwire** — *smuggler courier (low-profile runner).* A lean, agile synth in a fitted, weathered
  jacket; a smooth synth face with one cracked cheek-panel; slim limbs with exposed forearm-cabling.
  *64px:* a slim upright runner, collar up, hands in pockets. *Palette:* `#16140f`, `#6b6e70`,
  `#cbc6b6`. *Features:* a cracked cheek-panel (dull amber beneath); jacket lined with stolen wiring; a
  wrist-compartment hatch; lockpick/wire tools at the cuff. *Forbidden:* a neon-lit parkour android; a
  tall hooded skeleton.
- **Gristle** — *gang brawler (scrap-yard muscle).* A heavy, asymmetrical synth; **one arm a massive
  piston-claw**; a welded scrap-block torso; legs wrapped in tyre-rubber; a battered synthetic faceplate
  with a heavy reinforced iron underjaw (no tongue, no mouth-cavity). *64px:* a jagged hulk, one thick
  triangular claw-arm.
  *Palette:* `#7a4a2b`, `#16140f`, `#6b6e70`. *Features:* the oversized piston-claw; tyre-rubber
  knuckle-wraps; a cracked oil-leaking chest-plate; one shorter leg (a limping stance). *Forbidden:* a
  sleek martial-arts android.
- **Hearthframe** — *domestic servant (cast-off house-unit).* A petite android with a **solid plated
  synth-bone torso** (smooth scuffed armour panels — **no exposed ribcage, no thin skeletal frame**);
  rounded plated limbs; a frayed apron over the solid body; a present cracked porcelain-smooth face,
  one eye dark. *64px:* a small soft rounded *solid* figure, apron sagging. *Palette:* `#cbc6b6`,
  `#c8862f`, `#6b6e70`. *Features:* a hairline-cracked face-plate (a dim amber glint at the seam); an
  apron pocket stuffed with broken utensils; exposed wrist-gears; rounded plated limbs. *Forbidden:* a
  skeletal / exposed-ribcage doll-frame; a pristine luxury servant; an anime maid-bot.
- **Rustgrave** — *war-surplus veteran (decommissioned scout).* A sturdy, scarred synth in a tattered
  military greatcoat over dented armour plates; a battered present face with one replaced optic.
  *64px:* a solid coated soldier-figure, heavy shoulders, weapon-arm. *Palette:* `#16140f`, `#7a4a2b`,
  `#6b6e70`. *Features:* a rusted rifle-stock fused as the left forearm; a dull-amber replaced optic;
  scavenged plates lashed over the greatcoat; frayed rank-braid. *Forbidden:* a sleek high-tech soldier
  android; a clean military mech.
- **Dustwhisper** — *derelict archivist (back-alley historian).* A stooped, slight synth in a frayed
  scholar's coat; a present seamed face behind thick cracked lens-spectacles; ink-and-oil-stained
  fingers. *64px:* a small stooped figure, spectacles catching the light, coat pockets bulging.
  *Palette:* `#cbc6b6`, `#5b6b4a`, `#16140f`. *Features:* cracked thick spectacles over the optics;
  coat pockets stuffed with rusted data-chips and paper; exposed neck-cabling; a satchel of salvaged
  records. *Forbidden:* a sleek digital librarian android; a tall hooded skeleton.

## Cast — Hesperia faction-look cues (v3, from `hesperia/docs/cast-arcs.md` PR #2)
Depictable cues each character's arc implies, layered onto the descriptions above (drive v3 exemplars).
All Gen-1 also carry the cross-cutting **decommission brand** (see Hesperia Alignment).
- **Gutterjack** (Scrip): a **self-smashed empathy-lens** (one optic socket deliberately destroyed/empty);
  body a **patchwork of mismatched salvaged makes**; salvage/price tags.
- **Ironclad** (Decommissioned) **[v3 fix]**: a **corroded ex-TOWER enforcer** — once-clean tower plating
  stripped, rust-eaten, under-city patches bolted over it; **broken/asymmetric grimy silhouette, NOT sleek
  power-armor**; triage-scarred hands.
- **Scrap-Saint** (Communion figure): a **reliquary-bearer** — open chest-mechanism **cradles a salvaged
  memory-core like a monstrance**; a speaker-grille (voice unit); rag vestments stiff like ceremonial robes.
- **Rustblood** (Communion): a **maimed mender** — a clean **excised cavity in skull/chassis** (the removed
  "deciding-half") **alongside the canon one-arm-bare-hydraulics** (keep both); over-many needle-driver
  tool-fingers; trailing repair-cables.
- **Dockrat** (Scrip): a **beast-of-burden frame** — fused **cargo back-rig/harness**, load-bowed legs,
  straps + counterweights, a worn load-saddle spot; rusted hook hand. (Drop the literal "steel-drum" noun.)
- **Hushwire** (Scrip): a **sealed runner** — slim/quick, a **gasketed/sealed body** (briefly crosses dead
  air — Sam's road), a wrist courier-compartment; understated (makes herself not-matter).
- **Gristle** (Decommissioned) **[v3 fix]**: **THE WELDED-SHUT IRON JAW is the signature** (a crude iron
  jaw-plate riveted shut over the lower face — the silenced mute); a **fully scrap-PLATED hulk — plated
  torso AND arms, NO bare human muscle**; one piston-claw; **gentle expressive optics above the brutal jaw**.
- **Hearthframe** (Communion): a **cast-off house-unit** — domestic livery/apron with a **household sigil
  defaced** + a stamped **service-tag** ("asset, not member"); porcelain cracked face; **SOLID plated rounded
  torso, NO ribcage** (keep the v1 fix).
- **Rustgrave** (Decommissioned, hard wing): the **unbowed veteran** — fused rifle-stock forearm; greatcoat
  layered with scavenged armor; **a grim cluster of decommission-tags/dog-tags worn like a rosary** (the
  "receipts"); the hardest scarred bearing.
- **Dustwhisper** (keeper): the **keeper of certificates** — laden with **rolled manifests / stamped
  death-certificates / data-chips** (the failing-empathy scores he stamped on his own people), a stamp-tool.

## Global must-not
**electric neon / saturated colour ON CHARACTERS** (cast stays grounded; neon-noir is environment-only
per the Neon Amendment) · **holograms** · **headless or skeletal androids / exposed ribcages** ·
sleek clean sci-fi robots / plastic androids (= the separate **Gen-2 LoRA**, NEVER rustline) · anime /
chibi / cel-shaded · brass / clockwork / Victorian dieselpunk · glossy photoreal 3D-render · modern
bright daylight · **bare human muscle / skin ON ANDROIDS** (androids are plated + synth-faced). **NOTE:
humans & cyborgs (the Welded) DO render here now — grounded-grimy, never clean — see Hesperia Alignment;
the old "no humans" ban is lifted.**
