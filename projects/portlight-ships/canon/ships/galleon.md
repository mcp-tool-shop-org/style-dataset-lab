---
id: galleon
display_name: Galleon
ship_class: galleon
tonnage_class: great-ship-scale
era: "1600s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    High-sterned three-masted great ship. Deep curved hull with a pronounced sheer rising
    aft to a tall square stern castle; low forecastle; long bowsprit steeved well up. Two
    continuous gun decks. Fore and main masts square-rigged on crossed yards; mizzen
    carries a fore-and-aft lateen. Read at sprite size the shape is a long low hull, a tall
    stern block, three verticals of descending height fore-to-aft, and a forward spike.
  palette:
    - "#d8c0a8"
    - "#c0a890"
    - "#301818"
    - "#181818"
    - "#c9a227"
  material_dominant: dark seasoned oak planking with aged off-white canvas and warm gilt carving
  hull_markings:
    - gilt scrollwork along the sheer strake
    - carved and gilded stern gallery with twin quarter lanterns
    - gilded figurehead beneath the bowsprit
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast,   position: fore,   relative_height: tall,    sections: [lower, top, topgallant] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower, top, topgallant] }
      - { id: mizzenmast, position: mizzen, relative_height: short,   sections: [lower, top] }
    sails:
      - { id: spritsail,       mast: bowsprit,   sail_type: spritsail }
      - { id: fore-course,     mast: foremast,   sail_type: course }
      - { id: fore-topsail,    mast: foremast,   sail_type: topsail }
      - { id: main-course,     mast: mainmast,   sail_type: course }
      - { id: main-topsail,    mast: mainmast,   sail_type: topsail }
      - { id: main-topgallant, mast: mainmast,   sail_type: topgallant }
      - { id: mizzen-lateen,   mast: mizzenmast, sail_type: lateen }
      - { id: fore-staysail,   mast: foremast,   sail_type: staysail }
      - { id: jib,             mast: bowsprit,   sail_type: jib }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: portlight-ships/hulls/galleon/plates-raw/galleon__01-pristine__sails-open.png

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
  role: >-
    Great-ship trader and the heaviest hull a player can command on the long routes; also
    sails as a prize, a wreck and an enemy.
  trade_capacity: great-ship-scale hold; the widest cargo range in the fleet at the cost of handling and draught
  current_status: in-service-playable

forbidden_inputs:
  - all masts standing upright at 04-heavy or 05-destroyed — the named broken masts must read as broken
  - any mast whole at a later state than one where it is listed broken — damage never runs backwards
  - sails still set, full or drawing when the rig state is sails-closed — furled means rolled and lashed along the yard
  - bare masts with no canvas at all when the rig state is sails-closed — furled canvas is present as thick bundles, not absent
  - the vessel mirrored — the bow points LEFT in every damage-state plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow in a damage-state plate
  - any green anywhere on the vessel — the plate background is chroma key and despill would desaturate it
  - cool grey-blue canvas — the canvas is aged off-white
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - carved and gilded stern gallery with twin quarter lanterns
  - gilded figurehead beneath a steeply steeved bowsprit
  - two continuous gun decks with square ports
  - gilt scrollwork running the length of the sheer
  - three masts of descending height fore-to-aft, mizzen lateen-rigged

freeze:
  status: auto
  watch_fields:
    - visual.silhouette_cue
    - visual.palette
    - visual.rig_plan
    - visual.material_dominant
    - damage_ladder
    - signature_features
    - forbidden_inputs
    - ship_class
    - era
  frozen_reason: >-
    DRAFT — awaiting Director ratification. Freeze once the rig plan and damage ladder are
    correct; after that canon drift reports any change to a watched field.

sources:
  - portlight-ships 2026-07-25 generation run — the 8-subject galleon set, its meshes, and the four documented failure modes now recorded in forbidden_inputs
  - portlight brand mark (mcp-tool-shop-org/brand logos/portlight) — palette family
  - palette hex sampled from hulls/galleon/plates-raw/galleon__01-pristine__sails-open.png; "#c9a227" gold is an estimate, the gilt area was too small to sample reliably

canon_refs:
  - portlight-ships/docs/adding-a-hull.md
  - portlight-ships/pipeline/build_ladder_workflow.py — the two prompt laws earned 2026-07-25
---

# Galleon

The heaviest hull on the long routes. A galleon is the ship a merchant graduates into rather
than starts with: it carries more than anything else afloat, and it handles like the great
box of oak it is. Deep draught, slow to answer the helm, and worth the trouble only when the
cargo justifies the risk.

## Reading the shape

Three masts of descending height fore-to-aft, a long low hull, and a stern castle that stands
up like a building. The forecastle is low; the weight of the silhouette is all aft. The
bowsprit runs out and up at a steep angle, which at sprite size reads as a spike off the bow
and is the fastest way to tell a galleon's heading at a glance.

Two continuous gun decks run the length of her. Gilt scrollwork follows the sheer, and the
stern gallery is carved and gilded with a lantern at each quarter. A gilded figurehead sits
beneath the bowsprit. These survive every damage state until the fire takes them, and they
are what makes a wrecked galleon still recognisably *this* galleon.

## How damage reads on her

Severity tiers are defined once in `canon/damage-tiers.md` and are the same for every
hull in the fleet. What is specific to this ship is where damage *shows*: which parts of
her are exposed, which are structural, and what a viewer notices first when she has been
hit. Which particular spar comes down is not scripted here — that is the model's call
from her anatomy, and ours to curate.

## Rig

She is drawn under sail and at anchor. **Sails-closed does not mean bare poles** — the canvas
is furled: rolled tight and lashed along the top of each yard, present and visible as thick
pale bundles. A galleon with no canvas at all is not at anchor, she is stripped, and that only
happens at 05 when the sails have burnt.

States 04 and 05 have no furled variant, and the reason is physical rather than arbitrary:
you cannot stow canvas that is no longer there.
