---
id: caravel
display_name: Caravel
ship_class: caravel
tonnage_class: pinnace-scale
era: "1500s"
faction_of_origin: unassigned
current_operator: independent

visual:
  silhouette_cue: >-
    Small, narrow and quick. High length-to-beam ratio — a slender ellipsoidal hull with a fine
    entry, almost no belly, and a modest raised deck aft rather than a true castle. Three masts on
    a very small hull, which is the odd proportion that identifies her: the rig looks slightly too
    big for the ship. The FOREMAST is square-rigged with one bulging course; the MAIN and MIZZEN
    both carry triangular lateen sails on long angled yards. That mixed square-forward,
    lateen-aft arrangement is the caravela redonda. At sprite size: a small slim hull under one
    square sail forward and two leaning triangles aft.
  palette:
    - "#e8dcc0"
    - "#a08050"
    - "#3c2c1c"
    - "#181818"
    - "#9c3428"
  material_dominant: light unpainted planking with a red-ochre sheer band, bright unbleached canvas, minimal ornament
  hull_markings:
    - red-ochre band along the sheer
    - painted cross or house device on the square fore course
    - plain low transom with a modest raised afterdeck
  rig_plan:
    bowsprit: true
    masts:
      - { id: foremast,   position: fore,   relative_height: short,   sections: [lower] }
      - { id: mainmast,   position: main,   relative_height: tallest, sections: [lower] }
      - { id: mizzenmast, position: mizzen, relative_height: tall,    sections: [lower] }
    sails:
      - { id: fore-course,   mast: foremast,   sail_type: course }
      - { id: main-lateen,   mast: mainmast,   sail_type: lateen }
      - { id: mizzen-lateen, mast: mizzenmast, sail_type: lateen }
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
  role: The scout and the explorer. Fast, weatherly, shallow, and carries almost nothing — she finds the route that the fat hulls then exploit.
  trade_capacity: very small hold; her value is reach, not volume
  current_status: in-service-playable

forbidden_inputs:
  - lateen rig on the foremast — the caravela redonda carries a SQUARE course forward and lateens aft
  - square sails on the main or mizzen — those two masts are lateen
  - a broad-bellied cargo hull — she is slender, high length-to-beam, with a fine entry
  - a tall stern castle or forecastle — she has at most a modest raised afterdeck
  - gun decks or rows of gun ports
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
  - three masts on a very small hull — the rig looks slightly oversized for the ship
  - square course on the foremast, lateen sails on main and mizzen
  - slender high length-to-beam hull with a fine entry and almost no belly
  - modest raised afterdeck instead of a true stern castle
  - red-ochre sheer band on light unpainted planking

freeze:
  status: auto
  watch_fields: [visual.silhouette_cue, visual.palette, visual.rig_plan, visual.material_dominant, damage_ladder, signature_features, forbidden_inputs, ship_class, era]
  frozen_reason: DRAFT — awaiting Director ratification.

sources:
  - "https://en.wikipedia.org/wiki/Caravel — early caravels had one mast with lateen sails, later versions two or three; the caravela latina used exclusively triangular lateen sails; the caravela redonda, developed in the late 15th century, featured a square-rigged foremast with the other masts bearing lateen rig, the bulging square sail on the front mast distinguishing it. Typical 15th-century caravel 12–18 m long, displacement around 50–75 tons; high length-to-beam ratio of around 3.5:1 with a narrow ellipsoidal frame giving speed and handling at the cost of cargo capacity. Portuguese and Spanish exploration, 15th–16th centuries. THIS ENTRY USES THE CARAVELA REDONDA FORM."

canon_refs:
  - portlight-ships/canon/damage-tiers.md
---

# Caravel

The one that finds the route. A caravel carries almost nothing and goes almost anywhere — fast,
close-winded, shallow enough for a river mouth, and small enough that losing one is survivable.

## Reading the shape

Slender. Her length-to-beam ratio is around three and a half to one, which on a small hull reads
as *narrow* — a fine entry, almost no belly, and a plain sheer with only a modest raised deck aft.
No castles.

Three masts on that small hull, and the proportion is the identifying oddity: the rig looks a
size too large for the ship. Forward, a **square** course, often with a painted device. Main and
mizzen both carry **lateens** — triangular sails on long angled yards. That square-forward,
lateen-aft mix is the caravela redonda, and it is a rig no other hull in the fleet uses.

She is easy to confuse with a xebec at a glance, so the distinction matters: a xebec is long, low,
oared, with overhanging ends and *three* lateens. A caravel is small, higher-sided, has no oars,
and carries a square sail forward.

## How damage reads on her

She is small and thin-skinned, so damage looks disproportionate on her — a breach that a galleon
would absorb takes out a meaningful fraction of a caravel. Her rig is her value, and a caravel
that has lost spars has lost the only thing she was for.

Severity tiers are defined once in `canon/damage-tiers.md`. Which spar comes down is the model's
call from her anatomy, and ours to curate.

## Rig

Furled, she shows one horizontal bundle forward on the square yard and two long *diagonal*
bundles aft along the lateen yards — a mixed stow that matches her mixed rig, and one more way to
tell her from the all-diagonal xebec.
