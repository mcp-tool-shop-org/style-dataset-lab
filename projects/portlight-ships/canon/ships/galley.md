---
id: galley
display_name: Galley
ship_class: galley
tonnage_class: brig-scale
tradition: sunward-sea
patina: seasoned
faction_of_origin: unassigned
current_operator: independent

visual:
  reference_period: "1500s-1600s"
  silhouette_cue: >-
    The only hull in the fleet that does not need wind. Extremely long and extremely narrow — a
    length-to-beam ratio around eight to one, against four to one for a merchant hull — and so low
    in the water that her deck sits barely above it. LONG BANKS OF OARS project from both sides
    along most of her length, angled down to the water, and they are the identifying feature before
    any sail is. Forward, a heavy metal-sheathed spur juts out at the waterline. Two masts carry
    triangular lateen sails on long angled yards, the forward one much the larger. Raised fighting
    platforms at bow and stern break an otherwise flat, almost deckless profile. At sprite size: a
    dark splinter lying flat on the water with a comb of oars down each side.
  palette:
    - "#e8dcc8"
    - "#8c2820"
    - "#2c2018"
    - "#181818"
    - "#c8a038"
  material_dominant: dark oiled timber with a scarlet and gold painted stern, bare pale oars, bright unbleached lateen canvas
  hull_markings:
    - scarlet and gold painted panel across the stern platform
    - a painted or gilded device on the spur at the bow
    - pale unpainted oar looms against the dark hull
  rig_plan:
    bowsprit: false
    masts:
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower] }
      - { id: mizzenmast, position: mizzen, relative_height: short,   sections: [lower] }
    sails:
      - { id: main-lateen,   mast: mainmast,   sail_type: lateen }
      - { id: mizzen-lateen, mast: mizzenmast, sail_type: lateen }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - { state_id: 01-pristine,   order: 1, hull_condition: pristine-new,       rig_states: [sails-open, sails-closed] }
  - { state_id: 02-light,      order: 2, hull_condition: well-maintained,    rig_states: [sails-open, sails-closed] }
  - { state_id: 03-moderate,   order: 3, hull_condition: field-patched,      rig_states: [sails-open, sails-closed], hull_note: "Oars are structure, not rigging. Broken and missing oars along one side belong at 03 and above, and once gone they stay gone — a galley that has lost oars has lost the thing she is for, exactly as a caravel that has lost spars has." }
  - { state_id: 04-heavy,      order: 4, hull_condition: breached-scorched,  rig_states: [sails-open] }
  - { state_id: 05-destroyed,  order: 5, hull_condition: derelict-burnt,     rig_states: [sails-none] }

narrative:
  role: The hunter that does not wait for weather. In a flat calm, when every square-rigger in sight is a stationary target, she is the only thing on the water still moving — and she is moving toward you.
  trade_capacity: almost none; every metre of her length is oars, rowers and provisions for them
  current_status: in-service-npc

forbidden_inputs:
  - no oars, or oars stowed out of sight — the banks of oars along both sides are her identity and must be visible in every plate
  - square sails — both her masts carry triangular lateen sails on long angled yards
  - a tall freeboard or a deep-bellied hull — she is extremely low and extremely narrow, sitting almost at water level
  - fore or stern castles — she has low raised fighting platforms, not built-up castles
  - rows of gun ports along the side — her sides are given over to oars
  - a bowsprit — she carries none; the spur at her bow is a ram, not a spar for sails
  - the vessel mirrored — the bow points LEFT in every plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - long banks of oars projecting from both sides along most of her length
  - extreme length-to-beam ratio with very low freeboard, sitting almost at water level
  - heavy metal-sheathed spur projecting forward at the waterline
  - two lateen sails on long angled yards, the forward one much the larger
  - low raised fighting platforms at bow and stern

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, tradition, patina]
  frozen_by: Director
  frozen_reason: Ratified by the Director 2026-07-25 — rig plan, silhouette and palette approved as canon. Not sdlab-frozen; ratification records approval, freeze is a separate operation.

sources:
  - "https://en.wikipedia.org/wiki/Galley — war galleys maintained extreme elongation at length-to-breadth ratios of 8:1 to 10:1, against 4:1 for sailing merchant ships, with shallow draft and low freeboard; Carthaginian trade galley wrecks fell between at 6:1. Galleys mounted 'a heavy projection at the foot of the bow, sheathed with metal, usually bronze' for ramming. Mediterranean war galleys carried single or dual masts with 'basic square sails until the Early Middle Ages and later lateen sails'. Later oar systems used alla sensile — 'up to three rowers sharing a single bench, handling one oar each' — or more commonly 'rowers sharing a bench but using just a single large oar, sometimes with up to seven or more rowers per oar'. Raised structures existed fore and aft. Great merchant galleys reached 'up to 46 m'. In use from antiquity through the early 19th century. NOTE: the source does not state whether masts were struck while rowing; this canon keeps both masts standing in every plate."

canon_refs:
  - portlight-ships/canon/damage-tiers.md
  - portlight-ships/canon/traditions.md
---

# Galley

Every other hull in this fleet is a negotiation with the wind. The galley is not. She is the answer
to a question the others cannot answer: what do you do when there is no weather at all?

## Reading the shape

She is a splinter. Around eight times as long as she is wide — the merchant hulls run four to one —
and she sits so low that her deck is nearly at the waterline. Where a fluyt is a shape with volume,
a galley is a line.

The oars are the read. Long banks of them project from both sides down most of her length, angled
to the water, and at any distance they form a comb along each flank that nothing else in the fleet
produces. If a plate of her shows no oars, the plate is wrong.

Forward, a heavy metal-sheathed spur runs out at the waterline — not a bowsprit, and it carries no
sail. It is there to go through something. Her two lateen sails are real and used, but they are
secondary; she is a rowing vessel that also sails, and she should read that way.

## How damage reads on her

She is uniquely legible when hurt, because her oars are a **repeating pattern** and the eye finds a
gap in a pattern instantly. A galley missing four oars from one bank reads as damaged from across
the screen — no other hull in the fleet has a feature that fails so visibly.

She is also fragile in a way the deep hulls are not. Low freeboard means a breach is at the
waterline by definition, and there is very little ship between her deck and the sea.

Severity tiers are defined once in `canon/damage-tiers.md`. Which spar comes down is the model's
call from her anatomy, and ours to curate — but see the `hull_note` on her `03` tier: oars are
structure, not rigging, and they do not grow back.

## Rig

Furled, she shows two long *diagonal* bundles along her lateen yards, the same stow as the xebec —
which makes sense, as they come from the same yards and the same water. With canvas stowed she is
at her most characteristic: a bare low line with two raked spars and a comb of oars, which is
exactly how she looks when she is working.
