---
id: junk
display_name: Junk
ship_class: junk
tonnage_class: ship-scale
tradition: far-trade
patina: seasoned
faction_of_origin: unassigned
current_operator: independent

visual:
  reference_period: "1400s-1600s"
  silhouette_cue: >-
    Built on none of the logic the rest of the fleet shares. Three masts, each carrying ONE broad
    battened lugsail — a four-cornered sail stiffened by full-length horizontal battens running its
    whole width, so it reads as a ribbed panel rather than a bag of canvas. The battens are the
    whole identity: every sail is crossed by five or six hard horizontal lines. NO BOWSPRIT and no
    headsails, so nothing projects forward of the bow at all. The bow itself is a blunt flat
    transom, not a pointed stem. Aft she rises into a high horseshoe-shaped stern under a raised
    poop deck, far taller than her waist. Flat-bottomed, with the hull divided internally by
    watertight bulkheads. At sprite size: a high-sterned hull with a chopped-off bow and three
    ribbed rectangular sails.
  palette:
    - "#d2b483"
    - "#8c4a2c"
    - "#3a2418"
    - "#181818"
    - "#c8a038"
  material_dominant: dark tung-oiled timber, tanbark-brown battened canvas, red and gold trim on the transom stern
  hull_markings:
    - a painted eye (oculus) on each bow cheek
    - red and gold painted panel across the high transom stern
    - full-length horizontal battens picked out darker than the sail cloth
  rig_plan:
    bowsprit: false
    masts:
      - { id: foremast,   position: fore,   relative_height: short,   sections: [lower] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower] }
      - { id: mizzenmast, position: mizzen, relative_height: tall,    sections: [lower] }
    sails:
      - { id: fore-lug,   mast: foremast,   sail_type: lugsail }
      - { id: main-lug,   mast: mainmast,   sail_type: lugsail }
      - { id: mizzen-lug, mast: mizzenmast, sail_type: lugsail }
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
  role: The outsider. She comes from water nobody local has charted, trades on terms nobody local set, and leaves before anyone works out where she went. The only hull in the fleet built on a different idea of what a ship is.
  trade_capacity: large and compartmented — her watertight bulkheads mean a holed junk keeps floating and keeps most of her cargo
  current_status: in-service-npc

forbidden_inputs:
  - a bowsprit, jib-boom, or any spar projecting forward of the bow — she carries none, and no headsails
  - European square sails or triangular lateen sails — every sail is a battened lugsail crossed by full-length horizontal battens
  - sails without visible battens — the horizontal ribs are the identifying feature and must read at sprite size
  - a pointed stem or curved cutwater — her bow is a blunt flat transom
  - a low European counter stern — hers is a high horseshoe transom beneath a raised poop
  - gun decks or rows of gun ports
  - the vessel mirrored — the bow points LEFT in every plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - three battened lugsails, each crossed by full-length horizontal battens
  - no bowsprit and nothing projecting forward of the bow
  - blunt flat transom bow instead of a pointed stem
  - high horseshoe-shaped stern under a raised poop deck
  - a painted eye on each bow cheek

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, tradition, patina]
  frozen_by: Director
  frozen_reason: Ratified by the Director 2026-07-25 — rig plan, silhouette and palette approved as canon. Not sdlab-frozen; ratification records approval, freeze is a separate operation.

sources:
  - "https://en.wikipedia.org/wiki/Junk_(ship) — seagoing trading junks carried multiple masts, sources describing 'twelve down to three sails'. The junk rig uses battened lugsails: 'full-length battens of the junk sail keep the sail flatter than ideal in all wind conditions', and sails are 'never lowered, but turned according to the direction of the wind'. Hull features a 'horseshoe-shaped stern supporting a high poop deck', 'watertight bulkheads' dividing the interior into compartments, a flat-bottomed design, and a central stern rudder large enough to need 'up to twenty members of the crew to control in strong weather'. Song-dynasty large junks were approximately 30–34 m by shipwreck archaeology; claims of 71 m are considered exaggerated. Built of softwoods, teak after the 17th century in Guangdong, waterproofed with tung oil and putty. Ocean-going forms emerged 10th–13th centuries, peaked during the Ming dynasty (15th–17th centuries). NOTE: the article does not detail bowsprits, and no bowsprit is specified — the absence is treated here as canon for this hull. The painted bow oculus is standard practice on Chinese working craft and is NOT attested in this source."

canon_refs:
  - portlight-ships/canon/damage-tiers.md
  - portlight-ships/canon/traditions.md
---

# Junk

The outsider, and the only hull in the fleet that argues with the others about what a ship is.
Everything the rest of the fleet takes as given — a pointed bow, a spar out front, canvas that
bellies — she simply does differently, and does it well enough to have crossed open water to get
here.

## Reading the shape

Start at the bow, because that is where she is strangest: there is nothing there. No bowsprit, no
jib-boom, no headsails, no projecting spar of any kind. The stem is a blunt flat transom, chopped
square. Every other hull in the fleet reaches forward; she does not.

Then the sails. Three masts, one broad four-cornered sail each, and every sail is crossed by five
or six **full-length horizontal battens** that hold it flat. At any distance this reads as three
ribbed panels rather than three sails, and that is the correct read — it is what tells her apart
from everything else afloat before any other detail resolves.

Aft she climbs. The stern is a high horseshoe transom under a raised poop, standing well above her
waist, painted in red and gold. A painted eye on each bow cheek watches the water ahead.

## How damage reads on her

Her battens are a gift here. A holed European sail is a ragged hole; a holed lugsail tears
*between* battens, so damage reads as clean horizontal gaps in a ribbed panel — legible instantly,
and unlike any other hull's damage in the fleet.

Below the waterline she is the hardest ship here to sink. Watertight bulkheads mean a breach floods
one compartment and no more, so a badly holed junk stays up and stays trading when a fluyt of the
same tonnage would be on the bottom. That is a canon fact with gameplay consequences, and it should
survive into how her `04` and `05` states read: broken, but still stubbornly afloat.

Severity tiers are defined once in `canon/damage-tiers.md`. Which spar comes down is the model's
call from her anatomy, and ours to curate.

## Rig

Furled, she is unlike anything else in the fleet. A junk sail does not roll up — it **concertinas**,
folding down flat on itself batten against batten into a thick horizontal stack along the boom. So
her stowed state shows three dense ribbed bundles sitting low, not the thin lashed rolls aloft that
every European hull here shows.
