---
id: sloop
display_name: Sloop
ship_class: sloop
tonnage_class: pinnace-scale
era: "1600s-1700s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    ONE mast, and everything follows from that. A single tall mast stepped well forward of amidships,
    raked slightly aft, carrying one large four-cornered fore-and-aft GAFF mainsail slung behind it
    on an angled upper spar with a long boom running aft over the stern. A square topsail may sit
    above the gaff on a yard. Forward of the mast, a long bowsprit with a single headsail. Small
    shallow hull, low freeboard, open or lightly-decked waist, no castles and no ornament. At sprite
    size she is the simplest shape in the fleet: one leaning spar, one big quadrilateral, one
    triangle forward, over a low hull.
  palette:
    - "#e8e0cc"
    - "#9c7c54"
    - "#3c2c1c"
    - "#181818"
    - "#4a6470"
  material_dominant: bare oiled planking with a pale boot stripe, bright unbleached canvas, no gilding whatsoever
  hull_markings:
    - pale boot stripe at the waterline
    - plain low transom
    - no gun ports
  rig_plan:
    bowsprit: true
    masts:
      - { id: mainmast, position: single, relative_height: tallest, sections: [lower, top] }
    sails:
      - { id: jib,          mast: bowsprit, sail_type: jib }
      - { id: main-gaff,    mast: mainmast, sail_type: course }
      - { id: main-topsail, mast: mainmast, sail_type: topsail }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - state_id: 01-pristine
    order: 1
    condition: Flawless. Gaff mainsail hard and drawing, boom out over the stern, square topsail set, jib full. Oiled planking bright.
    masts_broken: []
    sails_lost: []
    hull_condition: pristine-new
    rig_states: [sails-open, sails-closed]
  - state_id: 02-light
    order: 2
    condition: Working wear. A patch or two in the mainsail, frayed leech, salt bloom along the low topsides. Mast whole and standing.
    masts_broken: []
    sails_lost: []
    hull_condition: well-maintained
    rig_states: [sails-open, sails-closed]
  - state_id: 03-moderate
    order: 3
    condition: >-
      Chased and hit. Mainsail holed, jib shot away, boom cracked and drooping aft. Splintering
      along the low rail. Mast whole and still standing.
    masts_broken: []
    sails_lost: [jib]
    hull_condition: field-patched
    rig_states: [sails-open, sails-closed]
  - state_id: 04-heavy
    order: 4
    condition: >-
      Crippled. The MAINMAST is snapped above the lower section — the topmast and its square topsail
      yard have come down and hang alongside in the rigging, leaving a jagged stump with the gaff
      sail still bent to it in strips. With one mast, losing the top is losing most of her drive.
      Hull breached at the waterline, planking split and blackened.
    masts_broken: [mainmast]
    sails_lost: [jib, main-topsail]
    hull_condition: breached-scorched
    rig_states: [sails-open]
  - state_id: 05-destroyed
    order: 5
    condition: >-
      Burnt out. The MAINMAST is gone entirely — a short charred stump at the partners and the whole
      spar down across the hull with the boom, tangled in its own rigging. No canvas but blackened
      rags. Hull holed through, transom stove in, timbers charred grey.
    masts_broken: [mainmast]
    sails_lost: [jib, main-gaff, main-topsail]
    hull_condition: derelict-burnt
    rig_states: [sails-none]

narrative:
  role: The starter hull and the smuggler's hull. Cheap, shallow, crewed by a handful — she works the coast, slips into water nothing else can reach, and is the first deck most captains ever own.
  trade_capacity: minimal hold; one good cargo or one bad decision
  current_status: in-service-playable

forbidden_inputs:
  - more than one mast — a sloop has exactly ONE
  - a square course sail — her driving sail is a fore-and-aft gaff behind the mast; only a small square TOPSAIL may sit above it
  - any castle, quarter gallery, carved work or gilding — she is the plainest hull in the fleet
  - gun ports
  - a deep-bellied or high-sided hull — she is small, shallow and low
  - the mast stepped amidships — it is stepped well FORWARD of amidships
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
  - a single mast stepped well forward of amidships and raked slightly aft
  - one large gaff mainsail behind the mast with a long boom running aft over the stern
  - a single headsail on a long bowsprit
  - small shallow low-freeboard hull with no castles, no ornament and no gun ports
  - bare oiled planking with a pale boot stripe

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, era]
  frozen_reason: DRAFT — awaiting Director ratification.

sources:
  - "https://en.wikipedia.org/wiki/Sloop — a single-masted sailboat generally carrying one headsail forward of the mast and one mainsail abaft it; in the Age of Sail, before Bermuda rig became widespread, a non-Bermudian sloop might carry one or more square-rigged topsails hung from a topsail yard, indicating gaff rig with supplementary square topsails; the name is of Dutch origin. NOTE: 'sloop-of-war' is a naval term describing the purpose of a warship, not a rig, and must not be confused with the sloop rig used here."

canon_refs:
  - portlight-ships/docs/adding-a-hull.md
---

# Sloop

The first deck you own, and for a lot of captains the only one. A sloop is cheap, shallow, and
worked by a handful of hands. She carries almost nothing, goes almost anywhere, and is the reason
the shallow-water routes exist at all.

## Reading the shape

**One mast.** That is the whole identity and it makes her the maximum contrast to everything else
in the fleet. It is stepped well forward of amidships and rakes slightly aft, carrying a single
large gaff mainsail slung behind it, with a long boom running aft over the stern. A small square
topsail may sit above the gaff. Forward, a long bowsprit and one headsail.

The hull is small, shallow and low, with no castles, no gallery, no carving, no gilding and no
gun ports. She is the plainest thing afloat, and drawn honestly that plainness is her character.

## How she comes apart

She has one mast, so the ladder has to work differently from the three-masted hulls: **04** snaps
the *topmast*, bringing the square topsail yard down alongside and leaving a jagged stump with the
gaff sail still bent to it in rags. **05** takes the whole spar — stump at the partners, mast and
boom down across the hull in a tangle of its own rigging.

A dismasted sloop is barely a ship. That is the point of her as a damage state: there is nothing
left to lose.

## Rig

Furled, the gaff mainsail gathers **down onto its boom** in one long fore-and-aft roll lying above
the deck, running bow-to-stern rather than across. One mast, one long low bundle. She is the
easiest ship in the fleet to read at anchor and the hardest to mistake for anything else.
