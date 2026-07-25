---
id: xebec
display_name: Xebec
ship_class: xebec
tonnage_class: brig-scale
era: "1600s-1700s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    Low, long and sharp. Pronounced overhanging bow AND overhanging stern, both projecting well
    beyond the waterline, giving a hull that looks slung between two points. Very low freeboard.
    A run of oar ports along the side beneath the rail. Three masts, raked forward, each carrying
    an enormous triangular LATEEN sail on a long angled yard that crosses the mast diagonally and
    reaches down almost to the deck forward. At sprite size she reads as a low dark sliver under
    three vast leaning triangles — nothing else in the fleet has that shape.
  palette:
    - "#e0d2b4"
    - "#a8703c"
    - "#2a1a12"
    - "#181818"
    - "#b03028"
  material_dominant: oiled reddish hardwood with a painted red sheer stripe, sun-bleached cream lateen canvas
  hull_markings:
    - painted red stripe along the sheer
    - row of oar ports below the rail
    - carved and painted head at the overhanging bow
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast,   position: fore,   relative_height: tall,    sections: [lower] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower] }
      - { id: mizzenmast, position: mizzen, relative_height: short,   sections: [lower] }
    sails:
      - { id: fore-lateen,   mast: foremast,   sail_type: lateen }
      - { id: main-lateen,   mast: mainmast,   sail_type: lateen }
      - { id: mizzen-lateen, mast: mizzenmast, sail_type: lateen }
      - { id: jib,           mast: bowsprit,   sail_type: jib }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - state_id: 01-pristine
    order: 1
    hull_condition: pristine-new
    rig_states: [sails-open, sails-closed]
  - state_id: 02-light
    order: 2
    hull_condition: well-maintained
    rig_states: [sails-open, sails-closed]
  - state_id: 03-moderate
    order: 3
    hull_condition: field-patched
    rig_states: [sails-open, sails-closed]
  - state_id: 04-heavy
    order: 4
    hull_condition: breached-scorched
    rig_states: [sails-open]
  - state_id: 05-destroyed
    order: 5
    hull_condition: derelict-burnt
    rig_states: [sails-none]

narrative:
  role: Mediterranean corsair. Fast under sail, and able to row down a becalmed prize when the wind dies — the reason a merchant fears flat water in the inner sea.
  trade_capacity: small hold; she is built to take cargo, not carry it
  current_status: in-service-npc

forbidden_inputs:
  - square sails on any mast — every sail on this vessel is a triangular lateen on a long angled yard
  - a high stern castle or raised forecastle — the xebec is deliberately low and flush
  - a deep-bellied hull — she is long, lean and shallow with overhanging ends
  - omitting the oar ports along the side
  - all masts standing upright at 04-heavy or 05-destroyed
  - any mast whole at a later state than one where it is listed broken — damage never runs backwards
  - sails still set, full or drawing when the rig state is sails-closed — a furled lateen is bundled along its angled yard
  - the vessel mirrored — the bow points LEFT in every damage-state plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow in a damage-state plate
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - three enormous triangular lateen sails on long angled yards crossing the masts diagonally
  - pronounced overhanging bow and stern projecting past the waterline
  - very low freeboard with a row of oar ports beneath the rail
  - forward-raked masts
  - painted red sheer stripe on oiled reddish hardwood

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, era]
  frozen_reason: DRAFT — awaiting Director ratification.

sources:
  - "https://en.wikipedia.org/wiki/Xebec — later xebecs carried three masts (early ones two); lateen sails on angled yards; pronounced overhanging bow and stern; rarely displaced more than 200 tons; carried both lateen sails and oars, allowing them to close on becalmed vessels; Algerian origin, dominant in Mediterranean and Barbary waters 16th to mid-19th century. The polacre-xebec variant carried square rig on the foremast with lateens on the others plus a bowsprit and two headsails — NOT used for this entry, which is the pure lateen form."

canon_refs:
  - portlight-ships/docs/adding-a-hull.md
---

# Xebec

The reason a becalmed merchant in the inner sea is a dead merchant. A xebec sails fast and, when
the wind dies, runs out her oars and comes on anyway. Nothing else in the fleet can do that.

## Reading the shape

She is the anti-galleon. Where a galleon is tall, deep and heavy, a xebec is long, low and slung —
a shallow hull with a bow and a stern that both overhang well past the waterline, so the whole
vessel looks stretched between its ends. Freeboard is minimal, and a row of oar ports runs the
length of her beneath the rail.

Three masts, raked forward, and this is the part that makes her unmistakable: every sail is a
**lateen** — a vast triangle bent to a long yard that crosses its mast diagonally and sweeps down
almost to the deck at the forward end. Three of those leaning triangles over a low dark hull is a
silhouette no other rig produces.

## How damage reads on her

Severity tiers are defined once in `canon/damage-tiers.md` and are the same for every
hull in the fleet. What is specific to this ship is where damage *shows*: which parts of
her are exposed, which are structural, and what a viewer notices first when she has been
hit. Which particular spar comes down is not scripted here — that is the model's call
from her anatomy, and ours to curate.

## Rig

A furled lateen does not look like a furled square sail. The canvas gathers along the *angled*
yard, so a xebec at anchor shows three long diagonal bundles rather than horizontal ones. She is
still unmistakably herself with her canvas stowed.
