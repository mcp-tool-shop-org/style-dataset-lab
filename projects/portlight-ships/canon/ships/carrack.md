---
id: carrack
display_name: Carrack
ship_class: carrack
tonnage_class: great-ship-scale
era: "1500s-1600s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    The old great ship, and the galleon's ancestor. Round-bellied hull with heavy tumblehome, and
    castles at BOTH ends — a towering aftcastle over a high rounded stern AND a tall forecastle
    built up over the bow, overhanging the stem. That double-castle profile is the whole read: she
    dips deeply amidships between two raised blocks, where a galleon has only one. Three masts,
    fore and main square-rigged, a lateen mizzen. Bowsprit steeved out from under the forecastle.
    At sprite size she is a swaybacked hull with a tower at each end.
  palette:
    - "#d8c0a8"
    - "#9c6c40"
    - "#3a2010"
    - "#181818"
    - "#a8302c"
  material_dominant: heavy dark oak with painted red and ochre castle panels, aged off-white canvas, weathered gilding
  hull_markings:
    - painted heraldic panels on the forecastle and aftcastle faces
    - large cross or house device on the main course
    - carved rail along both castles
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast,   position: fore,   relative_height: short,   sections: [lower, top] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower, top] }
      - { id: mizzenmast, position: mizzen, relative_height: tall,    sections: [lower] }
    sails:
      - { id: spritsail,    mast: bowsprit,   sail_type: spritsail }
      - { id: fore-course,  mast: foremast,   sail_type: course }
      - { id: main-course,  mast: mainmast,   sail_type: course }
      - { id: main-topsail, mast: mainmast,   sail_type: topsail }
      - { id: fore-topsail, mast: foremast,   sail_type: topsail }
      - { id: mizzen-lateen, mast: mizzenmast, sail_type: lateen }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - state_id: 01-pristine
    order: 1
    condition: Flawless. Canvas whole, the great main course drawing full with its device bright. Castle panels freshly painted, carved rails sharp.
    masts_broken: []
    sails_lost: []
    hull_condition: pristine-new
    rig_states: [sails-open, sails-closed]
  - state_id: 02-light
    order: 2
    condition: Working wear. Patched canvas, the device on the main course faded, salt staining up the tumblehome, castle paint chipped. All three masts standing.
    masts_broken: []
    sails_lost: []
    hull_condition: well-maintained
    rig_states: [sails-open, sails-closed]
  - state_id: 03-moderate
    order: 3
    condition: >-
      Fought and survived. Canvas holed. Scorching and splintering across the forecastle face —
      the castles take the fire first because they stand highest. A rail section shot away. All
      three masts still standing.
    masts_broken: []
    sails_lost: [spritsail]
    hull_condition: field-patched
    rig_states: [sails-open, sails-closed]
  - state_id: 04-heavy
    order: 4
    condition: >-
      Crippled. The FOREMAST is snapped above the lower section, stump jagged, upper mast down and
      hanging over the forecastle in its rigging. The forecastle itself is half shot away, its
      painted panels blackened. Remaining canvas in strips. Hull breached amidships.
    masts_broken: [foremast]
    sails_lost: [spritsail, fore-course, fore-topsail]
    hull_condition: breached-scorched
    rig_states: [sails-open]
  - state_id: 05-destroyed
    order: 5
    condition: >-
      Burnt-out hulk. FOREMAST still down and the MAINMAST gone too — two broken stumps. Both
      castles are gutted and open to the sky, the aftcastle collapsed inward. Only the lateen
      mizzen leans. No canvas but blackened rags. Hull holed through, ribs exposed, timbers charred.
    masts_broken: [foremast, mainmast]
    sails_lost: [spritsail, fore-course, fore-topsail, main-course, main-topsail, mizzen-lateen]
    hull_condition: derelict-burnt
    rig_states: [sails-none]

narrative:
  role: The old great ship still in service. Enormous capacity, wretched handling, and a shape half a century out of date — the hull a poorer or more traditional operator still sails because it carries more than it has any right to.
  trade_capacity: very large hold; the tall castles cost her weatherliness and make her a poor sailer to windward
  current_status: in-service-playable

forbidden_inputs:
  - a low forecastle — the carrack's forecastle is TALL and built up over the bow; that double castle is what separates her from a galleon
  - a lean or fine-lined hull — she is round-bellied with heavy tumblehome
  - two continuous gun decks with regular square ports — that is the galleon's read, not hers
  - all masts standing upright at 04-heavy or 05-destroyed
  - any mast whole at a later state than one where it is listed broken — damage never runs backwards
  - sails still set, full or drawing when the rig state is sails-closed — furled means rolled and lashed along the yard
  - bare masts with no canvas at all when the rig state is sails-closed
  - the vessel mirrored — the bow points LEFT in every damage-state plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow in a damage-state plate
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - castles at BOTH ends — a tall forecastle overhanging the bow and a towering aftcastle
  - deeply dipped waist amidships between the two raised castles
  - round-bellied hull with heavy tumblehome
  - painted heraldic panels on the castle faces
  - a large device on the main course

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, era]
  frozen_reason: DRAFT — awaiting Director ratification.

sources:
  - "https://en.wikipedia.org/wiki/Carrack — three or four masts; later carracks square-rigged on foremast and mainmast, lateen-rigged on the mizzen; a typical three-masted carrack carried bowsprit, foresail, mainsail, mizzensail and two topsails; high rounded stern with aftcastle, plus forecastle and bowsprit at the stem; 14th–15th century origin, dominant in oceanic trade through the 16th century and still in use into the mid-17th; Portuguese carracks often over 1000 tons; direct predecessor of the galleon."

canon_refs:
  - portlight-ships/docs/adding-a-hull.md
---

# Carrack

The galleon's grandmother, and still afloat. A carrack carries an enormous amount and sails
badly, which is a trade every cash-poor operator in the world has made at some point.

## Reading the shape

The one thing to get right: **she has castles at both ends.** A tall forecastle built up over
and overhanging the bow, and a towering aftcastle over a high rounded stern. Between them the
waist dips deeply. That swaybacked, tower-at-each-end profile is the entire silhouette, and it is
exactly what a galleon gave up — a galleon dropped the forecastle low and kept only the stern
castle.

The hull is round-bellied with heavy tumblehome. Three masts: a short foremast and a tall
mainmast, both square-rigged, with a lateen on the mizzen. A large painted device on the main
course, and heraldic panels on the castle faces.

## How she comes apart

The castles stand highest, so they take fire first. **03** chews up the forecastle face. **04**
snaps the foremast and brings it down across the wrecked forecastle. **05** guts both castles —
open to the sky, aftcastle collapsed inward — and takes the mainmast with them.

A gutted carrack is one of the most distinctive wrecks in the fleet, because the two towers
becoming two ruins is such a specific shape.

## Rig

Sails-closed means furled — canvas rolled and lashed along the yards. A carrack at anchor with
her castles rising over bare yards is the classic harbour silhouette of the older age.
