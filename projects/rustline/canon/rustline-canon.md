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
  Described as an **effect** (warm amber highlights, deep shadow) — never a light-source object, and
  **never neon**.
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

> **Dataset-craft notes:** (1) **NO neon** — put neon/holograms/glowing-signage/saturated-colour in
> every negative. (2) Light is an EFFECT ("warm amber highlights, deep shadow"), never a source noun
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

## Global must-not
**neon / holograms / glowing signage / saturated colour** · **headless or skeletal androids / exposed
ribcages** · sleek clean sci-fi robots / plastic androids · anime / chibi / cel-shaded · brass /
clockwork / Victorian dieselpunk · glossy photoreal 3D-render · modern bright daylight · humans (the
cast is androids).
