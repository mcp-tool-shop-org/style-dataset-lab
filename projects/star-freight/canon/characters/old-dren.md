---
id: old-dren
role_class: station-resident
species: terran
faction_primary: null
tech_literacy: civilian
combat_training: civilian-desperation
visual:
  silhouette_cue: "bar-keeper elder, Freeport-worn"
  palette: ["#3a2a1a", "#c8a878", "#2a1c14", "#8a6a4a", "#d8b856"]
  attire: "long trader apron over worn undershirt, sleeves rolled"
  build: heavy-muscular
  hair: "iron-grey, cropped, beard"
  eyes: "grey, flint"
  distinguishing_marks:
    - "faded Compact-service tattoo on forearm (decades old)"
    - "burn scar across the back of the hand"
  posture_default: "hands on the bar, leaning forward"
  signature_prop: "the bar itself — Dren is rarely rendered outside its geometry"
  age_description: "early sixties, still stronger than he looks"
  art_lane: portrait
narrative:
  role: "Bar-keeper at Freeport. World-building presence, optional interactions."
  voice: ["dry", "economical", "quiet-watchful"]
  motivation: "run the bar; know things; stay out of it"
  arc_beats:
    - "Acts 2-3: optional interactions at the bar"
    - "Dialogue gates: worldbuilding, rumors, light informant work"
  relationships:
    - target_id: freeport-station
      edge_type: grew-up-at
    - target_id: terran-compact
      edge_type: exiled-from
      note: "decades-old Compact-service history, left quietly"
  speech_register: "casual-Reach, economical"
mechanical:
  combat_role: tank
  loyalty_starting: 0
forbidden_inputs:
  - "glamorous framing"
signature_features:
  - "trader apron over undershirt"
  - "faded Compact tattoo"
  - "bar posture"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §119, §243"
---

## Old Dren

Bar-keeper at Freeport. Optional interactions carry world-building weight — Dren knows more than he says and his Compact-service tattoo is the breadcrumb that says so.
