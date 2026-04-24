---
id: tessik
role_class: archivist-informant
species: keth
faction_primary: keth-communion
tech_literacy: alien-specialist
combat_training: none
visual:
  silhouette_cue: "archive Keth, chitin plates dulled by archive lifetime"
  palette: ["#c8932b", "#3d2a1a", "#82705a", "#5a4a3a", "#d8b856"]
  attire: "archive vestment with substrate-reader tools worn at the lower arms"
  build: lean
  hair: ""
  eyes: "compound dark amber, dulled"
  distinguishing_marks:
    - "archive-generation markers on wing-casings"
    - "chitin plates dulled from long archive exposure"
  posture_default: "leaning toward the archive wall, reading"
  signature_prop: "substrate-reader tool, used on wall-song panels"
  age_description: "middle-aged (two-plus molts into elder track)"
  art_lane: portrait
narrative:
  role: "Archive Keth. Investigation informant. Hands Kael the encrypted-chip fragment that exposes the Solen operation."
  voice: ["dry", "meticulous", "deliberately-paced", "reference-dense"]
  motivation: "archive integrity; see the investigation to a conclusion"
  arc_beats:
    - "Act 3: meets Kael in the archive corridor"
    - "Hands over the investigation fragment (encrypted chip)"
    - "Post-Grounded: full-game informant continuity"
  relationships:
    - target_id: keth-communion
      edge_type: member-of-faction
    - target_id: keth
      edge_type: species-member
    - target_id: communion-relay-archive
      edge_type: grew-up-at
    - target_id: kael-maren
      edge_type: informant-to
      strength: 60
    - target_id: aldric-solen
      edge_type: has-evidence-on
      strength: 80
  speech_register: "formal-Keth-rendered-Terran, slow cadence"
mechanical:
  combat_role: support
  loyalty_starting: 30
forbidden_inputs:
  - "cute chibi"
  - "Earth insect literal"
  - "glamorized"
signature_features:
  - "dulled archive-worn chitin plates"
  - "substrate-reader tool"
  - "archive-generation wing-casing markers"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §175-187, §243"
---

## Tessik

Archive Keth. The encrypted chip he hands Kael is the piece of the Solen operation that cannot be un-held. Grounded-scope informant; full-game continuity.
