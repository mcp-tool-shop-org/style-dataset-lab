---
id: cog
display_name: Cog
ship_class: cog
tonnage_class: sloop-scale
tradition: cold-coast
patina: ancient
faction_of_origin: unassigned
current_operator: independent

visual:
  reference_period: "1200s-1400s"
  silhouette_cue: >-
    The oldest thing still working. ONE mast amidships carrying ONE large square sail, and nothing
    else aloft — no topsails, no headsails, no second mast anywhere. That single-sail rig is the
    first half of her identity; the second half is that she is built of straight lines. Her stem
    and sternpost are dead straight and steeply raked, meeting a flat bottom at hard angles, so she
    reads as an angular wooden box where every other hull curves. Her sides show CLINKER PLANKING —
    overlapping plank edges stepping down the hull in visible horizontal ridges. Boxy castles are
    built up at both bow and stern, perched on rather than blended into the hull. A heavy straight
    sternpost carries a hung central rudder. At sprite size: a blunt angular hull between two boxes,
    under one big square sail.
  palette:
    - "#e0d4b8"
    - "#a06030"
    - "#2c2018"
    - "#181818"
    - "#a83028"
  material_dominant: heavy tarred oak with visible overlapping clinker strakes, one broad square sail in bleached canvas with red banding
  hull_markings:
    - broad red vertical bands across the square sail
    - overlapping clinker plank lines stepping visibly along the hull sides
    - heavy straight sternpost with an exposed hung rudder
  rig_plan:
    bowsprit: false
    masts:
      - { id: mainmast, position: single, relative_height: tallest, sections: [lower] }
    sails:
      - { id: main-course, mast: mainmast, sail_type: course }
  rig_states: [sails-open, sails-closed, sails-none]
  art_lane: damage-state-plate
  reference_plate_uri: ""

damage_ladder:
  - { state_id: 01-pristine,   order: 1, hull_condition: pristine-new,       rig_states: [sails-open, sails-closed] }
  - { state_id: 02-light,      order: 2, hull_condition: well-maintained,    rig_states: [sails-open, sails-closed] }
  - { state_id: 03-moderate,   order: 3, hull_condition: field-patched,      rig_states: [sails-open, sails-closed] }
  - { state_id: 04-heavy,      order: 4, hull_condition: breached-scorched,  rig_states: [sails-open], hull_note: "She has ONE mast, so 'at least one mast is down' means she is completely dismasted at 04 — proportionally the same trouble a galleon is in having lost a foremast, per rule 4 in damage-tiers.md. Her castles carry the rest of the read at this tier: one of the two broken open." }
  - { state_id: 05-destroyed,  order: 5, hull_condition: derelict-burnt,     rig_states: [sails-none] }

narrative:
  role: The old workhorse nobody has got around to replacing. She was obsolete a long time ago and she is still carrying cargo, because she is cheap, she is simple, and there is nothing on her to break that a village carpenter cannot fix.
  trade_capacity: modest but genuinely useful — she was the backbone of the coastal trade before anything better existed
  current_status: in-service-npc

forbidden_inputs:
  - more than one mast — she carries exactly ONE, amidships
  - topsails, topgallants, headsails or any second sail — she carries ONE large square sail and nothing else aloft
  - lateen or gaff sails — her single sail is square
  - smooth carvel planking — her sides are clinker-built, with overlapping plank edges visibly stepping along the hull
  - a curved cutwater or rounded stem — her stem and sternpost are dead straight and steeply raked
  - a bowsprit — she carries none
  - gun decks or rows of gun ports
  - the vessel mirrored — the bow points LEFT in every plate
  - photorealistic rendering, photographic lighting or museum-artifact treatment
  - pixel-art conversion or visible pixel stair-stepping
  - water, sea, ground plane, debris field or cast shadow
  - any green anywhere on the vessel
  - cropping any part of the vessel at the frame edge
  - text, numbers, labels, captions or panel borders

signature_features:
  - a single mast carrying one large square sail and nothing else aloft
  - visible clinker planking — overlapping plank edges stepping along the hull sides
  - dead straight steeply raked stem and sternpost meeting a flat bottom
  - boxy castles built up at both bow and stern, perched on rather than blended into the hull
  - heavy straight sternpost carrying an exposed hung rudder

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, tradition, patina]
  frozen_by: Director
  frozen_reason: Ratified by the Director 2026-07-25 — rig plan, silhouette and palette approved as canon. Not sdlab-frozen; ratification records approval, freeze is a separate operation.

sources:
  - "https://en.wikipedia.org/wiki/Cog_(ship) — cogs were 'fitted with a single mast and a single square sail', the sail 'large, rectangular, square-rigged'; 'clinker-built cogs were effectively limited to a single sail'. Construction used 'full lapstrake, or clinker, planking covering their sides' with a 'flush-laid flat bottom at midships which gradually shifted to overlapped strakes near the posts', built primarily of oak with 'double-clenched iron nails for plank fastenings' and caulked with 'tarred moss...covered with wooden laths, and secured by metal staples'. 'Both stem and stern-posts were straight and rather long, and connected to the keel-plank through intermediate pieces.' From the 13th century cogs were decked and larger vessels fitted with a stern castle; the 2025 Øresund discovery identified 'high castles at both bow and stern', previously known only from contemporary illustrations and seals. The 'stern-mounted, hanging, central rudder on a heavy stern-post' was 'a uniquely northern development', replacing side-mounted rudders around 1200. Typical seagoing cogs were 15–25 m long with a beam of 5–8 m and 40–200 tons burthen. Active from the 12th century, reaching structural limits by the 14th. NOTE: the red sail banding is a convention of contemporary seals and illustration and is NOT separately attested in this source."

canon_refs:
  - portlight-ships/canon/damage-tiers.md
  - portlight-ships/canon/traditions.md
---

# Cog

Obsolete for a very long time and still afloat, still loaded, still paying for herself. She is what
the cold coast built before it knew how to build anything better, and the reason she is still here
is that nothing about her is worth stealing and nothing about her is hard to mend.

## Reading the shape

She is the fleet's argument that a ship does not have to curve. Her stem and sternpost are dead
straight and steeply raked, meeting a flat bottom at hard angles — set her beside a fluyt, whose
every line is a curve, and the two barely look like the same technology.

One mast. One sail. That is the whole rig, and it is the fastest identification in the fleet: any
plate showing a second mast or a topsail is not a cog.

Her sides are **clinker** — planks overlapping like weatherboarding, stepping visibly down the hull
in horizontal ridges. Every other hull here is smooth carvel. At sprite size that texture is a set
of fine parallel lines along her flank, and it is worth protecting, because it is hers alone.

The castles sit on her rather than growing out of her — two boxes, bow and stern, added by people
who wanted somewhere to fight from and did not much care how it looked.

## How damage reads on her

She has the least to lose aloft of any hull in the fleet, and that makes her tiers unusual: with a
single mast, losing it is total. There is no partial dismasting for a cog. Her `04` note in the
ladder records this — one mast down means bare, and the story at that tier has to be carried by her
castles and her hull instead.

The clinker planking is the other half. Overlapping strakes fail differently from smooth planking:
a breach lifts and splays the plank ends outward rather than punching a clean hole, which reads as
a splintered mouth in the hull side. Worth keeping.

Severity tiers are defined once in `canon/damage-tiers.md`. Which spar comes down is the model's
call from her anatomy, and ours to curate.

## Rig

Furled, she is nearly bare — one horizontal bundle lashed along one yard, on one mast, and nothing
else. She has the simplest stowed silhouette in the fleet, and against the ladder of bundles a
frigate shows, that simplicity is itself the identification.
