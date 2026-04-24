---
id: naia-of-threesong
role_class: crew-recruitable
species: keth
faction_primary: keth-communion
tech_literacy: alien-specialist
combat_training: basic
visual:
  silhouette_cue: "censured Keth, antennae forward, wing-casings marked"
  palette: ["#f5eed6", "#c8932b", "#3d6a4b", "#2a1c0a", "#82705a"]
  attire: "navigation-office resin vestment, rank resin-beads at upper arms (reduced count per censure)"
  build: lean
  hair: ""
  eyes: "compound dark amber"
  distinguishing_marks:
    - "censure mark etched into wing-casings (permanent)"
    - "seasonal markers on non-censured wing-casing portion"
  posture_default: "upright four-armed, lower arms at rest; antennae forward when speaking to off-world visitors"
  signature_prop: "navigation-office resin-seal token"
  age_description: "young-adult in Keth generational terms (one-and-a-half molts post-majority)"
  art_lane: portrait
  reference_plate_uri: ""
narrative:
  role: "Main-cast seed: recruitable in full game; in Grounded, 3-4 optional Communion Relay interactions, taught cultural-coaching mechanic"
  voice: ["measured", "patient", "carefully-rendered-Terran", "dense-with-reference"]
  motivation: "honor the censure she cannot fight; serve the Communion in the reduced role she has been given"
  arc_beats:
    - "Act 3: first encounter in navigation office"
    - "Optional interactions: cultural coaching, wall-song listening, elder-moment witness"
    - "Post-Grounded: recruitment path opens after investigation fragments"
  relationships:
    - target_id: keth-communion
      edge_type: member-of-faction
    - target_id: keth-communion
      edge_type: censured-by-faction
      strength: 100
      note: "elder council censure; permanent wing-casing mark"
    - target_id: keth
      edge_type: species-member
    - target_id: communion-relay-nav-office
      edge_type: grew-up-at
    - target_id: kael-maren
      edge_type: recognized-competence-from
      note: "Act 3 optional interactions build this edge"
  speech_register: "formal-carefully-rendered — Terran as second language, chosen words deliberately"
  vocabulary_forbidden:
    - "Terran idiom"
    - "casual slang"
    - "contractions under stress"
mechanical:
  combat_role: support
  starting_hull: 70
  starting_morale: 60
  signature_abilities:
    - "wall-song-read (reads Keth archive substrate)"
    - "cultural-coach (teaches Kael culturally-appropriate behavior)"
  loyalty_starting: 30
forbidden_inputs:
  - "cute chibi anime"
  - "Earth insect literalism"
  - "two-armed depiction"
  - "human-proportioned jaw or lips"
  - "glamorized rendering"
signature_features:
  - "censure-mark etched wing-casings"
  - "four arms at rest-pose"
  - "reduced resin-bead count (censure-specific)"
  - "antennae forward in speech"
freeze:
  status: soft-advisory
  frozen_reason: "First on-screen named alien. Read quality determines whether first-contact cultural-mechanics land."
canon_refs:
  - "PROLOGUE_GROUNDED.md §347-363"
  - "design/VOICE_TEST_NAIA.md"
  - "wave27a-identity-spine.json §naia-of-threesong"
---

## Naia-of-Threesong

Censured Keth. Navigation officer. The first named alien the player speaks with. Cultural-coaching mechanic is centered on her.

### Why the censure is visible

Censure mark is required to be visible. Keth cultural law — a censured individual cannot hide the mark without compounding the offense. Visual reads: wing-casings are marked; some seasonal markers on the non-censured portion remain, which says her full identity is layered, not erased.
