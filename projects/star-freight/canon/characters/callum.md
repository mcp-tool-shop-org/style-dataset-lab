---
id: callum
role_class: station-resident
species: terran
faction_primary: null
tech_literacy: civilian
combat_training: civilian-desperation
visual:
  silhouette_cue: "rescued civilian, derelict-exposure worn"
  palette: ["#4a2e18", "#a88878", "#2a1a14", "#8a5a3a", "#d8b856"]
  attire: "civilian flight jacket torn at the shoulder, utility undershirt, scuffed boots"
  build: underfed-lean
  hair: "dark, matted from exposure"
  eyes: "hazel, haunted"
  distinguishing_marks:
    - "torn shoulder on the jacket"
    - "derelict-exposure pallor"
  posture_default: "hunched, forward-facing"
  signature_prop: "torn civilian flight jacket"
  age_description: "early twenties, derelict-exposure drawn"
  art_lane: portrait
narrative:
  role: "Beat 15 derelict rescue target. Recurring in full game."
  voice: ["quiet", "shocked", "grateful"]
  motivation: "survive; find what he saw on the derelict"
  arc_beats:
    - "Beat 15: extracted from derelict"
    - "Post-rescue: Freeport recovery; owes the Corrigan"
    - "Full-game: informant potential"
  relationships:
    - target_id: freeport-station
      edge_type: grew-up-at
    - target_id: kael-maren
      edge_type: owes-favor-to
      strength: 70
      note: "Beat 15 rescue"
  speech_register: "casual-Reach, post-trauma cadence"
mechanical:
  combat_role: support
  loyalty_starting: 30
forbidden_inputs:
  - "glamorous framing"
  - "pristine attire"
signature_features:
  - "torn shoulder on jacket"
  - "derelict-exposure pallor"
  - "hunched posture"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §199-210, §243"
---

## Callum

Beat 15 derelict rescue target. Not a character in the Acts 2-3 sense — the rescue is the interaction. His presence afterward at Freeport is recovery, not arc. Full-game informant seed.
