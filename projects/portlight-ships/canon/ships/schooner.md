---
id: schooner
display_name: Topsail Schooner
ship_class: schooner
tonnage_class: sloop-scale
tradition: longshore
patina: seasoned
faction_of_origin: unassigned
current_operator: independent

visual:
  reference_period: "1700s"
  silhouette_cue: >-
    Two masts, both FORE-AND-AFT rigged, with the FOREMAST SHORTER than the mainmast — that height
    order is the identifying fact and it is the reverse of what most people draw. Each mast carries
    a four-cornered gaff sail slung behind it on an angled upper spar, so the rig reads as two big
    angled quadrilaterals stepped up in size from bow to stern. A square topsail (and topgallant
    above it) sits on the foremast only. Masts noticeably raked aft. Long low flush-decked hull,
    shallow, with a fine entry and a long bowsprit carrying two headsails. At sprite size: a low
    sleek hull under two raked, aft-leaning quadrilaterals, the aft one taller.
  palette:
    - "#e4dcc4"
    - "#7c6248"
    - "#1e1a18"
    - "#181818"
    - "#2c4658"
  material_dominant: light scrubbed decks over dark blue-black topsides, bright white-cream canvas, no gilding
  hull_markings:
    - dark blue-black topsides over a pale boot stripe
    - plain low transom
    - no gun ports
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast, position: fore, relative_height: short,   sections: [lower, top] }
      - { id: mainmast, position: main, relative_height: tallest, sections: [lower, top] }
    sails:
      - { id: jib,             mast: bowsprit, sail_type: jib }
      - { id: fore-staysail,   mast: bowsprit, sail_type: staysail }
      - { id: fore-gaff,       mast: foremast, sail_type: gaff }
      - { id: fore-topsail,    mast: foremast, sail_type: topsail }
      - { id: fore-topgallant, mast: foremast, sail_type: topgallant }
      - { id: main-gaff,       mast: mainmast, sail_type: gaff }
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
  role: The fast coastal trader — weatherly, close-winded and cheap to crew. Runs the short legs and the shallow water, and outpoints anything square-rigged trying to catch her.
  trade_capacity: small hold, but she works to windward where bigger hulls cannot and reaches ports they cannot enter
  current_status: in-service-playable

forbidden_inputs:
  - a foremast TALLER than the mainmast — on a schooner the foremast is the SHORTER of the two; this is the single most commonly drawn error
  - square course sails on either mast — only a square TOPSAIL and topgallant on the foremast, above the gaff
  - three or more masts
  - a stern castle, quarter gallery or carved ornament — she is low, flush and plain
  - gun ports
  - the vessel mirrored — the bow points LEFT in every plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - fore-and-aft gaff sails on both masts, the foremast shorter than the mainmast
  - square topsail and topgallant on the foremast only
  - both masts noticeably raked aft
  - long low flush-decked hull with a fine entry and no gun ports
  - dark blue-black topsides over pale scrubbed decks

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, tradition, patina]
  frozen_by: Director
  frozen_reason: Ratified by the Director 2026-07-25 — rig plan, silhouette and palette approved as canon. Not sdlab-frozen; ratification records approval, freeze is a separate operation.

sources:
  - "https://en.wikipedia.org/wiki/Schooner — fore-and-aft rig on all of two or more masts, with the FOREMAST GENERALLY SHORTER THAN THE MAINMAST; gaff-rigged the most common variant; the topsail schooner adds a square topsail on the foremast, to which a topgallant may be added; term emerged in eastern North America in the early 1700s, though schooners appear in Dutch paintings by 1600, further developed in British North America from around 1713; used for coastal trading, privateering, fishing and passenger work; valued for good ability to windward."

canon_refs:
  - portlight-ships/docs/adding-a-hull.md
---

# Topsail Schooner

The close-winded one. A schooner will sail nearer the wind than anything square-rigged in the
fleet, which means she takes routes the big hulls cannot and gets out of trouble in directions
they cannot follow.

## Reading the shape

Two masts, both **fore-and-aft** gaff-rigged: a big four-cornered sail slung behind each mast from
an angled upper spar. Both masts rake noticeably aft, which gives her a leaning, eager look even
at anchor.

The detail that gets drawn wrong more than any other: **the foremast is the SHORTER of the two.**
Not the taller. If the forward mast is bigger, it is not a schooner. She steps up in size from bow
to stern, and that ascending profile is the identity.

She carries a square topsail — and a topgallant above it — on the **foremast only**, which is what
makes her a *topsail* schooner rather than a plain one. Long low flush-decked hull, fine entry,
shallow, no gun ports, no ornament.

## How damage reads on her

Severity tiers are defined once in `canon/damage-tiers.md` and are the same for every
hull in the fleet. What is specific to this ship is where damage *shows*: which parts of
her are exposed, which are structural, and what a viewer notices first when she has been
hit. Which particular spar comes down is not scripted here — that is the model's call
from her anatomy, and ours to curate.

## Rig

Furled, a schooner does not look like a square-rigger at anchor. The gaff sails gather **down onto
their booms** in long horizontal rolls running fore-and-aft along the deck, not across it — only
the small square topsail on the foremast stows athwartships. Two long low bundles and one short
crossed one.
