---
id: frigate
display_name: Frigate
ship_class: frigate
tonnage_class: ship-scale
era: "1700s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    The fast cruiser. Long, low and sleek — a fine-lined warship hull with a markedly lower
    freeboard than a galleon or carrack, because her lower deck carries no guns and could be built
    down. ONE continuous row of gun ports along a single upper gun deck, running almost her whole
    length: that single unbroken row is the identifying feature, against a galleon's two rows and
    a merchantman's none. Three masts, all square-rigged with tall stacks of yards; the mizzen
    additionally carries a fore-and-aft gaff spanker on a boom aft. Long bowsprit with headsails.
    At sprite size: a long low dark hull with one bright line of ports, under three matched
    square-rigged masts.
  palette:
    - "#e0d8c4"
    - "#8c6c48"
    - "#242018"
    - "#181818"
    - "#c8b06c"
  material_dominant: black topsides broken by a single pale ochre gun strake, scrubbed decks, weathered cream canvas
  hull_markings:
    - single pale ochre strake running the length of the gun deck, ports picked out along it
    - modest carved stern with a row of windows, no towering gallery
    - figurehead at the stem
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast,   position: fore,   relative_height: tall,    sections: [lower, top, topgallant] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower, top, topgallant] }
      - { id: mizzenmast, position: mizzen, relative_height: short,   sections: [lower, top] }
    sails:
      - { id: jib,             mast: bowsprit,   sail_type: jib }
      - { id: fore-staysail,   mast: bowsprit,   sail_type: staysail }
      - { id: fore-course,     mast: foremast,   sail_type: course }
      - { id: fore-topsail,    mast: foremast,   sail_type: topsail }
      - { id: fore-topgallant, mast: foremast,   sail_type: topgallant }
      - { id: main-course,     mast: mainmast,   sail_type: course }
      - { id: main-topsail,    mast: mainmast,   sail_type: topsail }
      - { id: main-topgallant, mast: mainmast,   sail_type: topgallant }
      - { id: mizzen-topsail,  mast: mizzenmast, sail_type: topsail }
      - { id: mizzen-spanker,  mast: mizzenmast, sail_type: gaff }
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
  role: The cruiser. Independent, fast, and strong enough to take anything that can catch her — the hull that patrols the lanes, runs down raiders, and makes a merchant captain glad or very sorry depending on whose flag she wears.
  trade_capacity: minimal; her hold carries powder and provisions, not freight
  current_status: in-service-npc

forbidden_inputs:
  - two or more rows of gun ports — a frigate carries ONE continuous gun deck; two rows is a galleon or a ship-of-the-line
  - no gun ports at all — the single unbroken row is her identity
  - a high stern castle or towering gallery — her stern is modest and low
  - a fat round merchant belly — she is long, low and fine-lined
  - a lateen mizzen course — her mizzen carries a gaff spanker, and square topsails above
  - all masts standing upright at 04-heavy or 05-destroyed
  - sails still set, full or drawing when the rig state is sails-closed
  - the vessel mirrored — the bow points LEFT in every plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - one continuous row of gun ports along a single upper gun deck
  - long low fine-lined hull with markedly lower freeboard than a galleon
  - three square-rigged masts with a gaff spanker on the mizzen
  - single pale ochre gun strake against black topsides
  - modest carved stern with a row of windows, no towering gallery

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, era]
  frozen_reason: DRAFT — awaiting Director ratification.

sources:
  - "https://en.wikipedia.org/wiki/Frigate — the true frigate of the 18th century was square-rigged and carried all its main guns on a SINGLE continuous upper deck, the lower gun deck being unarmed crew quarters below the waterline; this single-deck armament distinguished frigates from ships-of-the-line carrying guns on multiple decks. Long sleek design, roughly 135 ft hull with a 13 ft draft; removing guns from the lower deck let designers lower the hull, giving superior sailing qualities and speeds up to 14 knots. French frigates carried 28–36 cannon on the main deck. Role: cruisers — independent fast scouts, commerce raiding, patrol, reconnaissance and message conveyance. NOTE: the gaff spanker on the mizzen is standard practice for the period rig and is not separately attested in this source."

canon_refs:
  - portlight-ships/canon/damage-tiers.md
---

# Frigate

The cruiser. Fast enough to catch anything worth catching, strong enough to beat anything that
can catch her, and cheap enough to send out alone. She is the reason the trade lanes are policed
and the reason a raider watches the horizon.

## Reading the shape

Long, low and fine-lined. Her lower deck carries no guns — it is crew space, below the waterline —
which let her builders drop the whole hull and gave her the speed that defines her.

The identifying feature is a count: **one** continuous row of gun ports, running nearly her full
length along a single upper gun deck. A galleon shows two rows. A fluyt shows none. A frigate
shows exactly one, picked out along a pale ochre strake against black topsides.

Three masts, all square-rigged with tall matched stacks, and a gaff spanker on the boom aft of
the mizzen. Her stern is modest — a row of windows and some carving, but nothing like a galleon's
towering gilded gallery.

## How damage reads on her

Everything about her is long horizontal lines — the gun strake, the low sheer, the row of ports —
so damage to the hull breaks a line that the eye is already following. A frigate with a bite out
of her gun strake reads as hurt instantly.

Aloft she is all top-hamper: three tall matched stacks of square canvas and very little else.
There is a lot to come down.

Severity tiers are defined once in `canon/damage-tiers.md`. Which spar comes down is the model's
call from her anatomy, and ours to curate.

## Rig

Furled, she shows three matched ladders of horizontal bundles with one long fore-and-aft roll aft
on the spanker boom — the same stow as a brig, scaled up by a mast.
