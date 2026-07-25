---
id: brigantine
display_name: Brigantine
ship_class: brigantine
tonnage_class: brig-scale
era: "1600s-1700s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    Two masts, lean and fast, low in the water with a fine entry. The rig is MIXED and asymmetric,
    and that asymmetry is the whole read: the FOREMAST is fully square-rigged, carrying stacked
    horizontal yards like a miniature warship, while the taller MAINMAST aft carries a four-cornered
    fore-and-aft GAFF sail slung behind the mast on an angled upper spar, with a square topsail
    above it. So one mast reads as horizontal bars and the other as a big angled quadrilateral.
    Long bowsprit with headsails. At sprite size: two masts, square forward, gaff aft, and a hull
    that looks built to run.
  palette:
    - "#dcd0b8"
    - "#8c6440"
    - "#241814"
    - "#181818"
    - "#7c1c20"
  material_dominant: dark tarred planking with a narrow blood-red sheer stripe, weathered cream canvas, minimal ornament
  hull_markings:
    - narrow blood-red stripe along the sheer
    - a short row of gun ports amidships only
    - plain unlit transom with no gallery
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast, position: fore, relative_height: tall,    sections: [lower, top, topgallant] }
      - { id: mainmast, position: main, relative_height: tallest, sections: [lower, top] }
    sails:
      - { id: jib,             mast: bowsprit, sail_type: jib }
      - { id: fore-staysail,   mast: bowsprit, sail_type: staysail }
      - { id: fore-course,     mast: foremast, sail_type: course }
      - { id: fore-topsail,    mast: foremast, sail_type: topsail }
      - { id: fore-topgallant, mast: foremast, sail_type: topgallant }
      - { id: main-gaff,       mast: mainmast, sail_type: course }
      - { id: main-topsail,    mast: mainmast, sail_type: topsail }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - state_id: 01-pristine
    order: 1
    condition: Flawless. Square canvas stacked and drawing on the foremast, the gaff mainsail hard aft. Tarred topsides black and clean, red stripe crisp.
    masts_broken: []
    sails_lost: []
    hull_condition: pristine-new
    rig_states: [sails-open, sails-closed]
  - state_id: 02-light
    order: 2
    condition: Working wear. Patches in the canvas, the gaff sail's leech frayed, salt bloom on the tarred sides, stripe chipped. Both masts standing.
    masts_broken: []
    sails_lost: []
    hull_condition: well-maintained
    rig_states: [sails-open, sails-closed]
  - state_id: 03-moderate
    order: 3
    condition: >-
      Fought and got away. Square canvas holed on the foremast, the gaff spar cracked and its sail
      hanging slack. Scorching and splintering around the small gun battery amidships. Both masts
      still standing.
    masts_broken: []
    sails_lost: [fore-topgallant]
    hull_condition: field-patched
    rig_states: [sails-open, sails-closed]
  - state_id: 04-heavy
    order: 4
    condition: >-
      Crippled. The FOREMAST is snapped above the lower section — jagged stump, upper mast with its
      stacked yards come down over the bow and hanging in the rigging. All square canvas forward is
      gone or in strips. The gaff mainsail survives in tatters. Hull breached, tarred planking
      blackened and split.
    masts_broken: [foremast]
    sails_lost: [jib, fore-staysail, fore-course, fore-topsail, fore-topgallant]
    hull_condition: breached-scorched
    rig_states: [sails-open]
  - state_id: 05-destroyed
    order: 5
    condition: >-
      Burnt out. FOREMAST still down and the MAINMAST snapped too — the gaff spar fallen across the
      wreck with it. Two stumps, no standing mast. No canvas but charred rags. Hull holed through
      at the waterline, ribs showing, the red stripe burnt away.
    masts_broken: [foremast, mainmast]
    sails_lost: [jib, fore-staysail, fore-course, fore-topsail, fore-topgallant, main-gaff, main-topsail]
    hull_condition: derelict-burnt
    rig_states: [sails-none]

narrative:
  role: Privateer and raider. Fast, handy and lightly armed — the hull that runs down a merchantman and outsails anything strong enough to punish it.
  trade_capacity: modest hold; she carries prize crews and plunder, not freight
  current_status: in-service-npc

forbidden_inputs:
  - square sails on the mainmast in place of the gaff — that would make her a BRIG, which is a different vessel
  - fore-and-aft rig on the foremast — the foremast is fully square-rigged; the asymmetry is the defining read
  - three masts — a brigantine has exactly two
  - a tall stern castle or carved gallery — she is flush-decked and plain
  - two continuous gun decks — she carries a short battery amidships only
  - all masts standing upright at 04-heavy or 05-destroyed
  - any mast whole at a later state than one where it is listed broken — damage never runs backwards
  - sails still set, full or drawing when the rig state is sails-closed
  - the vessel mirrored — the bow points LEFT in every damage-state plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow in a damage-state plate
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - asymmetric rig — square-rigged foremast, gaff-rigged taller mainmast
  - four-cornered gaff mainsail slung behind the mainmast on an angled upper spar
  - exactly two masts, flush deck, no castles
  - lean fast hull with a fine entry and low freeboard
  - short gun battery amidships and a narrow red sheer stripe

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, era]
  frozen_reason: DRAFT — awaiting Director ratification.

sources:
  - "https://en.wikipedia.org/wiki/Brigantine — two masts; foremast fully square-rigged; mainmast (the taller, aft mast) carries a square topsail and a gaff mainsail behind the mast; by the 18th century could also carry square topgallants above the gaff mainsail. Distinguished from a BRIG, which is principally square-rigged on both masts. Burden typically 30–150 tons. Prominent in Atlantic maritime nations from the 17th century; second-most popular rig built in British North America before 1775; employed for piracy, espionage and reconnoitering."

canon_refs:
  - portlight-ships/docs/adding-a-hull.md
---

# Brigantine

The hull that takes prizes. Fast enough to run down a loaded merchantman, handy enough to work in
close, and quick enough on her heel to leave anything that could actually hurt her.

## Reading the shape

Two masts and — this is the part that matters — **they are rigged differently from each other.**
The foremast is fully square-rigged: stacked horizontal yards, a small warship's rig in miniature.
The mainmast, taller and aft, carries a **gaff sail** — a big four-cornered fore-and-aft sail slung
*behind* the mast from an angled spar — with a square topsail above it.

So one mast reads as horizontal bars and the other as a large angled quadrilateral. That asymmetry
is the identifying feature and it is exactly what separates her from a brig, which is square on
both masts and is a different ship.

The hull is lean and low with a fine entry, flush-decked, no castles, a short battery of guns
amidships and a narrow red stripe along the sheer.

## How she comes apart

The square foremast is the vulnerable one — all that stacked canvas and top-hamper. **03** cracks
the gaff spar and holes the square canvas. **04** snaps the foremast and drops the whole stack of
yards over the bow, leaving her with only a tattered gaff sail aft. **05** takes the mainmast too,
and a brigantine with both masts down is a very small, very dark wreck.

## Rig

Furled, the two masts stow differently: the square yards carry horizontal bundles, while the gaff
sail gathers down onto its boom in a long fore-and-aft roll. Even with everything stowed you can
still tell which mast is which, and the plate should show that.
