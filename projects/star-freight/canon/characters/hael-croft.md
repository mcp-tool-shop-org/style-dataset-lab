---
id: hael-croft
role_class: patrol-operator
species: terran
faction_primary: terran-compact
tech_literacy: military-grade
combat_training: service-trained
visual:
  silhouette_cue: "patrol officer, corvette-issue kit"
  palette: ["#2a3a4a", "#5a6a78", "#0e1a28", "#c2a888", "#d8b856"]
  attire: "Compact patrol officer uniform, lieutenant rank markers, holstered sidearm"
  build: athletic
  hair: "dark, regulation-trim"
  eyes: "grey, measuring"
  distinguishing_marks:
    - "lieutenant rank markers"
    - "patrol-detail pin"
  posture_default: "upright, weight forward, inspection stance"
  signature_prop: "patrol data-slate with blue backlit display"
  age_description: "early thirties, career-patrol"
  art_lane: portrait
narrative:
  role: "Compact patrol officer. Acts 2-3 encounter gate. Potential defector seed (full-game)."
  voice: ["procedural", "measuring", "reserved"]
  motivation: "do the patrol job; see more than he is allowed to say"
  arc_beats:
    - "Acts 2-3: patrol encounter(s); outcome shapes Compact standing"
    - "Post-Grounded: defector seed — Croft has seen enough to question"
  relationships:
    - target_id: terran-compact
      edge_type: member-of-faction
    - target_id: kael-maren
      edge_type: antagonist-operational
      strength: 40
    - target_id: terran-compact
      edge_type: potential-defector-of
      strength: 20
      note: "full-game branch; Grounded is seed"
  speech_register: "formal-Compact, rank-address-preferred"
mechanical:
  combat_role: skirmisher
  loyalty_starting: 60
forbidden_inputs:
  - "glamorous villain framing"
  - "fantasy register"
signature_features:
  - "lieutenant rank markers"
  - "patrol data-slate"
  - "patrol-detail pin"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §189-196, §243"
---

## Lieutenant Hael Croft

Patrol officer. Grounded: Acts 2-3 encounter. Full-game: defector seed — he has seen enough patrol operations on the Reach lane to question Fleet Command's narrative.
