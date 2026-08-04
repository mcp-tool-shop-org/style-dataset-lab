---
id: brig
display_name: Brig
ship_class: brig
tonnage_class: brig-scale
tradition: crown-naval
patina: seasoned
faction_of_origin: unassigned
current_operator: independent

visual:
  reference_period: "1700s"
  silhouette_cue: >-
    Two masts, BOTH fully square-rigged, each carrying a tall stack of horizontal yards — course,
    topsail, topgallant and often a royal above that. The rig reads as two matched ladders of
    horizontal bars, which is the immediate difference from a brigantine's mismatched pair. Behind
    the square mainsail the mainmast ALSO carries a fore-and-aft gaff spanker on a boom running
    aft — an addition to the square rig, not a replacement for it. Sturdy workmanlike hull, fuller
    than a brigantine's, flush-decked, with a short battery amidships. Long bowsprit and headsails.
  palette:
    - "#ddd2bc"
    - "#8a6a48"
    - "#2c2018"
    - "#181818"
    - "#3c4a30"
  material_dominant: tarred black topsides over a pale wale stripe, workmanlike unpainted deck furniture, weathered cream canvas
  hull_markings:
    - pale painted wale stripe along the black topsides
    - short battery of gun ports amidships
    - plain transom with a painted name-board
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast, position: fore, relative_height: tall,    sections: [lower, top, topgallant] }
      - { id: mainmast, position: main, relative_height: tallest, sections: [lower, top, topgallant] }
    sails:
      - { id: jib,              mast: bowsprit, sail_type: jib }
      - { id: fore-staysail,    mast: bowsprit, sail_type: staysail }
      - { id: fore-course,      mast: foremast, sail_type: course }
      - { id: fore-topsail,     mast: foremast, sail_type: topsail }
      - { id: fore-topgallant,  mast: foremast, sail_type: topgallant }
      - { id: main-course,      mast: mainmast, sail_type: course }
      - { id: main-topsail,     mast: mainmast, sail_type: topsail }
      - { id: main-topgallant,  mast: mainmast, sail_type: topgallant }
      - { id: main-spanker,     mast: mainmast, sail_type: gaff }
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
  role: The dependable two-master — merchant hauler and small warship both. Carries real cargo and real guns without the cost of a full ship rig.
  trade_capacity: useful hold for a two-master; the coal-and-timber workhorse of the coastal runs
  current_status: in-service-playable

forbidden_inputs:
  - a gaff sail INSTEAD OF a square mainsail on the mainmast — that makes her a BRIGANTINE, a different vessel; the brig carries the square mainsail AND a spanker behind it
  - fore-and-aft rig on the foremast — both masts are fully square-rigged
  - three masts — a brig has exactly two
  - a lean raked privateer hull — she is fuller and more workmanlike than a brigantine
  - stern castle, quarter gallery or gilded carving
  - the vessel mirrored — the bow points LEFT in every plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - two matched masts, both fully square-rigged with tall stacks of horizontal yards
  - a gaff spanker on a boom aft of the square mainsail — in addition to it, not instead
  - flush-decked workmanlike hull with a short battery amidships
  - tarred black topsides with a pale wale stripe
  - long bowsprit carrying two headsails

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, tradition, patina]
  frozen_by: Director
  frozen_reason: Ratified by the Director 2026-07-25 — rig plan, silhouette and palette approved as canon. Not sdlab-frozen; ratification records approval, freeze is a separate operation.

sources:
  - "https://en.wikipedia.org/wiki/Brig — two SQUARE-RIGGED masts (fore and main); foremast carries fore sail, fore topsail, fore topgallant and fore royal; mainmast carries mainsail, main topsail, main topgallant and occasionally a royal, PLUS a gaff-rigged fore-and-aft sail behind the square mainsail called the spanker or boom mainsail. This fore-and-aft sail on the main distinguishes brigs from brigantines, which have only the foremast fully square-rigged. Generally larger than a schooner, 75–165 ft, tonnage up to 480. Late 18th century onward; merchant vessels and small warships of 10–18 guns."

canon_refs:
  - portlight-ships/canon/damage-tiers.md
  - portlight-ships/canon/traditions.md
---

# Brig

The two-master that does actual work. Where a brigantine is built to run, a brig is built to
carry — fuller in the hull, squarer in the rig, and happy hauling coal up a coast for twenty
years.

## Reading the shape

Two masts and **both are fully square-rigged**: matched stacks of horizontal yards, course over
topsail over topgallant, often a royal above that. Two ladders of bars, and they match.

That matching is the entire distinction from a brigantine, whose two masts are rigged
*differently*. And there is a second, subtler difference that matters: a brig's mainmast carries
a gaff spanker on a boom running aft — **in addition to** its square mainsail, not instead of it.
A brigantine has the gaff *instead*. So on a brig you see square canvas on the main with a
quadrilateral tucked behind it; on a brigantine the square main is simply absent.

Get this pair right and the model learns a real distinction. Get it wrong and it learns that brig
and brigantine are the same word.

## How damage reads on her

She carries her top-hamper high and evenly — two tall matched stacks — so aloft damage is
symmetric and obvious in a way a mismatched rig's is not. Below, she is plain black topsides with
a pale wale stripe and a short battery: a breach shows as a bite out of that clean stripe.

Severity tiers are defined once in `canon/damage-tiers.md`. Which spar comes down is the model's
call from her anatomy, and ours to curate.

## Rig

Furled, both masts stow the same way — horizontal bundles along the yards — while the spanker
gathers fore-and-aft onto its boom. Two matched ladders of pale rolls with one long low roll aft.
