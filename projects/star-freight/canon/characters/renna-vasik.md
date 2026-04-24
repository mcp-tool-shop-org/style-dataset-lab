---
id: renna-vasik
role_class: crew-recruitable
species: terran
faction_primary: null
tech_literacy: merchant-grade
combat_training: civilian-desperation
visual:
  silhouette_cue: "tool-belt-and-braced-stance engineer"
  palette: ["#4a2e18", "#c8a878", "#2a1a14", "#8a5a3a", "#d8b856"]
  attire: "heavy work coveralls rolled to the elbows, tool belt over a utility harness, scuffed Reach boots"
  build: compact-athletic
  hair: "dark brown, short braid tucked under a work cap when on-shift"
  eyes: "brown, alert"
  distinguishing_marks:
    - "grease and resin burns across the forearms"
    - "Reach-salvage serial tattoo on the back of the neck (small)"
  posture_default: "braced three-quarter stance, one hand at the tool belt"
  signature_prop: "multitool-rig with Ironjaw-era marking scratched off"
  age_description: "late twenties, weather-worn, moves like someone who has worked on her feet since she was a child"
  art_lane: portrait
  reference_plate_uri: "outputs/approved/anchor_02_mechanic_v3.png"
narrative:
  role: "Primary recruitable crew (Beat 9). Reach native. Debt to Ironjaw syndicate drives her side of the arc."
  voice: ["direct", "dry", "practical", "reach-informal"]
  motivation: "buy down the Ironjaw debt; find a crew that treats her as crew, not as leverage"
  arc_beats:
    - "Beat 9: recruited at Freeport; crew-trust-bond opens"
    - "Acts 2-3: ship operations + Ironjaw debt looming"
    - "Beat 15 derelict: she's the reason boarding works"
    - "Endgame trajectory: debt collected by Ironjaw at full-game open"
  relationships:
    - target_id: kael-maren
      edge_type: crew-trust-bond
      strength: 50
    - target_id: the-corrigan
      edge_type: crew-of-ship
    - target_id: freeport-station
      edge_type: grew-up-at
    - target_id: sable-reach
      edge_type: member-of-faction
      note: "Reach native, not formally affiliated"
    - target_id: ironjaw-syndicate
      edge_type: owes-debt-to
      strength: 85
      note: "debt not yet callable; creditor aware but not collecting"
  speech_register: "casual-Reach — first name, no rank"
  vocabulary_forbidden:
    - "Compact military jargon"
    - "formal-service register"
    - "mythic or fantasy idiom"
mechanical:
  combat_role: engineer
  starting_hull: 80
  starting_morale: 65
  signature_abilities:
    - "jury-rig (turns scrap into a working component)"
    - "salvage-eye (reads repair history of a ship at a glance)"
  skill_tree_hints:
    - "engineering branch"
    - "trade-logistics branch"
  loyalty_starting: 40
forbidden_inputs:
  - "glamorous framing"
  - "pristine clean attire"
  - "fantasy or medieval idiom"
  - "Compact military styling"
signature_features:
  - "tool-belt-and-utility-harness"
  - "grease and resin forearm burns"
  - "Reach-salvage neck serial"
  - "multitool with scratched-off Ironjaw marking"
freeze:
  status: soft-advisory
  frozen_reason: "Hero-5 Renna. The anchor_02 mechanic plates are the established reference; drift here rewrites a recruitable character's silhouette."
canon_refs:
  - "PROLOGUE_GROUNDED.md §120-146, §243"
  - "design/VOICE_TEST_RENNA.md"
  - "wave27a-identity-spine.json §renna-vasik"
---

## Renna Vasik — recruitable engineer

A Reach native who grew up on Freeport's docking arms. The tool belt is the silhouette anchor — she is never rendered without it, even in downtime. The multitool's scratched-off Ironjaw marking is visible in full-body shots; it is the piece of her debt she carries deliberately.

### Why the debt is still open

Ironjaw knows who she is and where she works. They are not collecting — which is worse than collecting. Renna and Kael both understand that the debt's cost will be named at full-game scope. In Grounded, it is setup.
