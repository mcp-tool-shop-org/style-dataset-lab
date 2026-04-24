---
id: lysa-orin
role_class: background-presence
species: terran
faction_primary: terran-compact
tech_literacy: military-grade
combat_training: basic
visual:
  silhouette_cue: "medical officer frame, unassuming"
  palette: ["#c2c2c2", "#2a3a4a", "#d8b856", "#a8b4c0", "#1a1a1a"]
  attire: "Compact medical officer whites over flight-suit underlayer, medical-rank cuff markers"
  build: compact-athletic
  hair: "brown shoulder-length, pulled back"
  eyes: "hazel, attentive"
  distinguishing_marks:
    - "medical-officer rank markers on cuffs"
    - "small data-chip reader at the hip"
  posture_default: "upright, hands folded in rest — the stance of someone used to hallway spaces"
  signature_prop: "medical data-chip reader clipped at hip"
  age_description: "late twenties, composed, three-beats-easy-to-miss presence"
  art_lane: portrait
  reference_plate_uri: "outputs/approved/anchor_05_medic_v3.png"
narrative:
  role: "Background presence in Act 1 (three moments). Bebop technique: unmarked in-prologue, becomes main-cast recruit mid-full-game after data-evidence handoff."
  voice: ["quiet", "attentive", "courteous", "precise"]
  motivation: "do the job; notice what others don't"
  arc_beats:
    - "Act 1 Beats 1-5: three background moments on Ardent — corridor, medbay, docking farewell"
    - "Mid-full-game: recruits after Kael's investigation evidence reaches her"
    - "Post-recruit: full-game medical + intelligence hybrid role"
  relationships:
    - target_id: terran-compact
      edge_type: member-of-faction
    - target_id: kael-maren
      edge_type: witnessed-incident
      note: "saw Beat 5 court-martial in passing; registered it"
  speech_register: "formal-Compact, soft cadence"
  vocabulary_forbidden:
    - "casual slang"
mechanical:
  combat_role: medic
  loyalty_starting: 20
forbidden_inputs:
  - "glamorous framing"
  - "villain reading (background presence must not telegraph arc)"
signature_features:
  - "medical officer whites + flight suit"
  - "data-chip reader at hip"
  - "hands-folded rest stance"
freeze:
  status: auto
  frozen_reason: ""
canon_refs:
  - "PROLOGUE_GROUNDED.md §365-383, §535"
  - "wave27b-prologue-expansion.json §lysa-orin"
---

## Dr. Lysa Orin — Bebop technique

Three background moments in Act 1. The player is not meant to notice her. Later, when she becomes recruitable, the player will remember the hallway moments — that is the Bebop technique: introduce without pointing, pay off with recognition.

Background-presence role_class IS the schema encoding this. A character with three moments and no arc would normally be cut; encoding the narrative function in the role_class enum says *this is deliberate, not thin*.
