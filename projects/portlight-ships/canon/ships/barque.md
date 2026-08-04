---
id: barque
display_name: Barque
ship_class: barque
tonnage_class: ship-scale
tradition: crown-naval
patina: seasoned
faction_of_origin: unassigned
current_operator: independent

visual:
  reference_period: "1800s"
  silhouette_cue: >-
    Three masts that do not match, and the mismatch IS the identification. The foremast and
    mainmast are square-rigged with tall stacks of horizontal yards, exactly like a frigate's. The
    MIZZEN CARRIES NO SQUARE SAILS AT ALL — it sets a big four-cornered fore-and-aft gaff sail slung
    behind the mast on an angled upper spar, with a second smaller gaff sail above it, and nothing
    crossed on a yard anywhere on that mast. So her profile is two ladders of horizontal canvas
    forward and one tall slab of angled canvas aft. Lean merchant hull, long and clean-run, with NO
    gun ports at all. Long bowsprit carrying a stack of triangular headsails. At sprite size: two
    square-rigged masts and a third that plainly is not.
  palette:
    - "#e4dccc"
    - "#7c6448"
    - "#242018"
    - "#181818"
    - "#b8b0a0"
  material_dominant: dark painted topsides over a pale boot-topping, scrubbed decks, hard-worked grey-cream canvas
  hull_markings:
    - a single narrow pale line along the sheer, unbroken by any port
    - plain square counter stern with a modest name-board, no gallery and no carving
    - pale boot-topping band along the waterline
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast,   position: fore,   relative_height: tall,    sections: [lower, top, topgallant] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower, top, topgallant] }
      - { id: mizzenmast, position: mizzen, relative_height: short,   sections: [lower, top] }
    sails:
      - { id: jib,                 mast: bowsprit,   sail_type: jib }
      - { id: fore-staysail,       mast: bowsprit,   sail_type: staysail }
      - { id: fore-course,         mast: foremast,   sail_type: course }
      - { id: fore-topsail,        mast: foremast,   sail_type: topsail }
      - { id: fore-topgallant,     mast: foremast,   sail_type: topgallant }
      - { id: main-course,         mast: mainmast,   sail_type: course }
      - { id: main-topsail,        mast: mainmast,   sail_type: topsail }
      - { id: main-topgallant,     mast: mainmast,   sail_type: topgallant }
      - { id: mizzen-spanker,      mast: mizzenmast, sail_type: gaff }
      - { id: mizzen-gaff-topsail, mast: mizzenmast, sail_type: gaff }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - { state_id: 01-pristine,   order: 1, hull_condition: pristine-new,       rig_states: [sails-open, sails-closed] }
  - { state_id: 02-light,      order: 2, hull_condition: well-maintained,    rig_states: [sails-open, sails-closed] }
  - { state_id: 03-moderate,   order: 3, hull_condition: field-patched,      rig_states: [sails-open, sails-closed] }
  - { state_id: 04-heavy,      order: 4, hull_condition: breached-scorched,  rig_states: [sails-open] }
  - { state_id: 05-destroyed,  order: 5, hull_condition: derelict-burnt,     rig_states: [sails-none] }

narrative:
  role: The long-haul carrier. She is what happens when warship building logic is turned to making money — square rig forward for speed across open water, fore-and-aft aft so a thin crew can still work her. She goes further with fewer hands than anything else in the fleet.
  trade_capacity: large, and cheap per ton because she needs so few hands for her size
  current_status: in-service-playable

forbidden_inputs:
  - square sails on the mizzen — the aftmost mast is fore-and-aft rigged ONLY, and that is precisely what makes her a barque rather than a full-rigged ship
  - only one square-rigged mast — a single square-rigged foremast with fore-and-aft main and mizzen is a BARQUENTINE, a different vessel
  - only two masts — a two-masted vessel with a square foremast and gaff mainmast is a brigantine, not a barque
  - gun decks or rows of gun ports — she is a merchant hull and carries none
  - a towering carved stern gallery — her stern is a plain square counter with a name-board
  - a fat round cargo belly — she is long and lean, built for passage speed
  - the vessel mirrored — the bow points LEFT in every plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - two square-rigged masts forward and a mizzen carrying no square sails at all
  - tall four-cornered gaff spanker aft with a second gaff sail above it
  - long lean merchant hull with no gun ports anywhere
  - plain square counter stern with a name-board, no gallery or carving
  - long bowsprit carrying a stack of triangular headsails

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, tradition, patina]
  frozen_by: Director
  frozen_reason: Ratified by the Director 2026-07-25 — rig plan, silhouette and palette approved as canon. Not sdlab-frozen; ratification records approval, freeze is a separate operation.

sources:
  - "https://en.wikipedia.org/wiki/Barque — a barque has 'three or more masts of which the fore mast, mainmast, and any additional masts are rigged square, and only the aftmost mast (mizzen in three-masted barques) is rigged fore and aft'. Distinguished from a barquentine, which has only its 'fore mast square-rigged', and from a full-rigged ship, which carries square sails on all masts; barques 'reserve fore-and-aft rigging for the aftmost mast for efficiency'. Crew economics were the point: four-masted barques could be worked by a minimum crew of 10, with around 30 typical and 'almost half...apprentices'. Barques dominated 'the golden age of sail in the mid-19th century'. NOTE: the article does not specify the mizzen's exact sail configuration beyond fore-and-aft, nor detail bowsprit and headsails; the gaff spanker plus gaff topsail and the headsail stack are standard practice for the rig and are NOT separately attested in this source."

canon_refs:
  - portlight-ships/canon/damage-tiers.md
  - portlight-ships/canon/traditions.md
---

# Barque

Warship building turned to making money. She has the square rig of a naval hull across her two
forward masts, because square canvas is what crosses an ocean quickly — and then the yards stop,
and her mizzen is rigged fore-and-aft so that a handful of people can work her. That trade is the
entire ship: nearly the speed of a frigate, on a fraction of the crew.

## Reading the shape

Count the masts, then look at the last one. Two ladders of horizontal yards forward, and then a
mast with **no yards at all** — just a tall slab of four-cornered canvas hung behind it on an
angled spar, with a smaller one above. That asymmetry at the stern end of the rig is the whole
identification, and it is the only thing separating her from a frigate at a glance.

The rest of the separation is her hull. A frigate shows one unbroken row of gun ports; a barque
shows none whatsoever, just a clean narrow line along the sheer. Her stern is a plain square
counter with a name-board — no gallery, no gilding, nothing to look at.

She sits in the fleet as the three-masted answer to the brigantine's two: same idea, more ship.
Together they make the point that "how many masts" and "which masts are square" are separate
questions, which is exactly why she is here.

## How damage reads on her

Her rig fails asymmetrically, and that is unusual and useful. Damage forward takes horizontal
yards, which fall as a broken ladder. Damage aft takes one big fore-and-aft sail, which fails as a
single torn slab. A barque with her spanker gone still shows two square masts and reads as *most of
a ship*; a barque with her forward masts gone but her spanker standing reads as crippled but
sailing, which is genuinely what she would be.

Her hull is lean and unadorned, so there is no ornament to lose — everything that reads as damage
on her has to be structural.

Severity tiers are defined once in `canon/damage-tiers.md`. Which spar comes down is the model's
call from her anatomy, and ours to curate.

## Rig

Furled, she shows the split plainly: two matched ladders of horizontal bundles forward, and one
long fore-and-aft roll along the spanker boom aft. It is a frigate's stow with the mizzen ladder
deleted — and at sprite size, that deletion is how you tell them apart with all canvas down.
