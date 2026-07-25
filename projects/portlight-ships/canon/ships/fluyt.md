---
id: fluyt
display_name: Fluyt
ship_class: fluyt
tonnage_class: ship-scale
era: "1600s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    The purpose-built cargo hull. Pear-shaped in section — very broad at the waterline, tumbling
    home hard above it to a narrow weather deck — with a high rounded stern. Shallow draught for
    her size. Three tall masts, taller in proportion than a warship's, carrying a modest sail
    plan worked by a small crew. Effectively unarmed: no gun decks, no ports, a plain unbroken
    run of planking where a galleon shows two rows of muzzles. At sprite size she reads as a fat
    rounded belly, a tall narrow stern, and three thin very tall verticals.
  palette:
    - "#d8c0a8"
    - "#b49878"
    - "#3a2418"
    - "#181818"
    - "#8a6a3c"
  material_dominant: pale scrubbed pine and oak planking, tarred topsides, aged off-white canvas, almost no gilding
  hull_markings:
    - plain unbroken topside planking with no gun ports
    - simple painted transom name-board on the rounded stern
    - single stern lantern
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast,   position: fore,   relative_height: tall,    sections: [lower, top] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower, top, topgallant] }
      - { id: mizzenmast, position: mizzen, relative_height: short,   sections: [lower] }
    sails:
      - { id: spritsail,     mast: bowsprit,   sail_type: spritsail }
      - { id: fore-course,   mast: foremast,   sail_type: course }
      - { id: fore-topsail,  mast: foremast,   sail_type: topsail }
      - { id: main-course,   mast: mainmast,   sail_type: course }
      - { id: main-topsail,  mast: mainmast,   sail_type: topsail }
      - { id: mizzen-lateen, mast: mizzenmast, sail_type: lateen }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - state_id: 01-pristine
    order: 1
    condition: Flawless. Canvas whole and drawing. Planking sound and freshly scrubbed. Rigging taut.
    masts_broken: []
    sails_lost: []
    hull_condition: pristine-new
    rig_states: [sails-open, sails-closed]
  - state_id: 02-light
    order: 2
    condition: Working wear. Sewn patches in the canvas, salt staining along the broad topsides, a rope or two adrift. All three masts upright and whole.
    masts_broken: []
    sails_lost: []
    hull_condition: well-maintained
    rig_states: [sails-open, sails-closed]
  - state_id: 03-moderate
    order: 3
    condition: >-
      Caught and mauled. Canvas holed. Splintered planking and scorching along the broad run of
      the topsides — the damage shows badly on a hull with no gun ports to hide it. One yard
      hanging. All three masts still upright and whole.
    masts_broken: []
    sails_lost: [mizzen-lateen]
    hull_condition: field-patched
    rig_states: [sails-open, sails-closed]
  - state_id: 04-heavy
    order: 4
    condition: >-
      Crippled. The FOREMAST is snapped above the lower section — jagged stump standing, upper
      mast down and hanging in its rigging. Remaining canvas in strips. The broad topsides
      breached in two places, blackened and splintered. Still afloat and cannot sail.
    masts_broken: [foremast]
    sails_lost: [spritsail, fore-course, fore-topsail, mizzen-lateen]
    hull_condition: breached-scorched
    rig_states: [sails-open]
  - state_id: 05-destroyed
    order: 5
    condition: >-
      Burnt-out hulk. FOREMAST still down and the MAINMAST gone too — both broken stumps. Only
      the short mizzen stands. No canvas but blackened rags. The rounded stern stove in, hull
      holed through, ribs showing, timbers charred grey.
    masts_broken: [foremast, mainmast]
    sails_lost: [spritsail, fore-course, fore-topsail, main-course, main-topsail, mizzen-lateen]
    hull_condition: derelict-burnt
    rig_states: [sails-none]

narrative:
  role: The workhorse merchantman — the hull that actually moves the cargo of the age. Carries more for less crew than anything afloat and cannot defend itself.
  trade_capacity: exceptional hold for her tonnage; shallow draught reaches ports and rivers deeper hulls cannot
  current_status: in-service-playable

forbidden_inputs:
  - gun ports or gun decks anywhere on the hull — the fluyt is an unarmed merchantman and that is her defining read
  - a warship's fine entry or lean run — the hull is deliberately fat and rounded
  - heavy gilding or carved stern gallery — she is plain and cheap by design
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
  - pear-shaped hull, very broad at the waterline tumbling home to a narrow weather deck
  - high rounded stern with a plain painted transom
  - no gun ports — an unbroken run of topside planking
  - three masts taller in proportion than a warship's, on a modest sail plan
  - scrubbed pale planking with tarred topsides and almost no gilding

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, era]
  frozen_reason: DRAFT — awaiting Director ratification.

sources:
  - "https://en.wikipedia.org/wiki/Fluyt — three-masted configuration carries square rig on fore and main with a lateen mizzen; pear-shaped profile; shallow draught; armament minimised or eliminated to maximise cargo; small crew; 16th-century Dutch origin, dominant through the 17th–18th centuries"

canon_refs:
  - portlight-ships/docs/adding-a-hull.md
---

# Fluyt

The ship that actually won the trade. A fluyt is not impressive and is not meant to be: she is a
hold with masts on it, built cheap, crewed thin, and carrying roughly twice what a comparable
armed merchantman could stow. Where a galleon is a statement, a fluyt is an argument about
margins.

## Reading the shape

Fat. She is broad at the waterline and tumbles home hard above it, so from bow or stern she reads
as a pear. The weather deck is narrow, the belly is enormous. Shallow draught lets her work up
rivers and into ports that turn away deeper hulls, which is half her commercial value.

Three masts, and they are *tall* — proportionally taller than a warship's — because tall masts on
a modest sail plan let a small crew move a heavy hull. Fore and main square-rigged, a lateen on
the short mizzen.

The defining feature is a negative one: **no gun ports.** An unbroken run of planking where a
galleon shows two rows of muzzles. She carries cargo where guns would go, and she runs rather
than fights.

## How she comes apart

Because she has no gun ports to break up the topsides, damage reads badly on her — a scorched,
splintered patch on that long plain run of planking is unmistakable. Through **02** and **03**
she stays whole aloft. **04** takes the foremast; **05** takes the mainmast too and stoves in the
rounded stern.

## Rig

Sails-closed means furled: canvas rolled and lashed along the yards, present as pale bundles. She
is often drawn at anchor, because a fluyt in a harbour discharging cargo is what this ship is
*for*.
