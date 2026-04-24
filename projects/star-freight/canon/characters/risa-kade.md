---
id: risa-kade
role_class: crew-wingmate
species: terran
faction_primary: terran-compact
tech_literacy: military-grade
combat_training: veteran-nco
visual:
  silhouette_cue: "veteran-NCO frame, hands clasped behind the back"
  palette: ["#2a3a4a", "#5a6a78", "#1a1a1a", "#c2a888", "#d8b856"]
  attire: "Compact flight-suit with NCO cuff-bars, veteran-service pin cluster at the breast, regulation boots"
  build: athletic
  hair: "iron-grey short, regulation-trim, beginning to thread white"
  eyes: "pale blue, level"
  distinguishing_marks:
    - "veteran-service pin cluster (five+ campaign rows)"
    - "scar across the back of the right hand (knife-fight, pre-service)"
  posture_default: "hands clasped behind the back in military rest; forward-center when speaking to her wing"
  signature_prop: "service-issue coin worn on a lanyard, always visible"
  age_description: "forty, weathered, moves with economy"
  art_lane: portrait
  reference_plate_uri: ""
narrative:
  role: "Act 1 wingmate who calls retreat. Survives. Re-enters post-prologue as LCDR Kade — late-game sub-boss, with a potential stand-down path."
  voice: ["grave", "procedural", "controlled", "economical"]
  motivation: "keep her wing alive; later — finish the mission she was given and cannot question"
  arc_beats:
    - "Acts 1 Beats 1-5: wingmate. Calls retreat at ambush. Survives."
    - "Post-Grounded mid-game: promoted/reassigned; the reassignment IS the turn"
    - "Late-game: appears as patrol commander. Sub-boss fight OR stand-down path if evidence"
  relationships:
    - target_id: kael-maren
      edge_type: close-bond-nonromantic
      strength: 80
      note: "wing-NCO bond, Act 1 reference"
    - target_id: terran-compact
      edge_type: member-of-faction
    - target_id: petra-wynn
      edge_type: close-bond-nonromantic
      note: "same wing, Act 1"
    - target_id: dak-torvo
      edge_type: close-bond-nonromantic
      note: "same wing, Act 1"
    - target_id: kael-maren
      edge_type: potential-stand-down-of
      strength: 30
      note: "late-game branch, evidence-gated"
  speech_register: "formal-Compact, rank-explicit even with familiar officers"
  vocabulary_forbidden:
    - "modern slang"
    - "fantasy register"
turncoat_arc:
  status: reluctant-betrayer
  reveal_trigger: "late-game confrontation when Kael arrives with the Solen-splinter evidence"
  defection_threshold: null
  handler_faction: terran-compact
  canon_true_voice: ["tired", "procedural", "regretful", "controlled"]
  seeds:
    - "We did the job, Captain. That's what wings do."
    - "Orders clean up their own messes. Ours don't."
    - "Retreat was the call. It still is."
    - "You're not the only one who lost something that day."
    - "I don't answer what I was told not to answer."
    - "Stand down isn't weakness. It's a cost you pay."
mechanical:
  combat_role: leader
  starting_hull: 95
  starting_morale: 70
  signature_abilities:
    - "wing-coordination (NCO rally)"
    - "retreat-discipline (clean withdrawal under fire)"
  loyalty_starting: 60
forbidden_inputs:
  - "glamorous framing"
  - "fantasy armor"
  - "rank insignia inconsistent with NCO"
signature_features:
  - "veteran-service pin cluster"
  - "NCO cuff-bars"
  - "service-issue coin on lanyard"
  - "hands clasped behind back default"
freeze:
  status: soft-advisory
  frozen_reason: "Hero-5 Risa. Late-game confrontation is a cinematic beat; her silhouette and voice must read as the Act 1 NCO for the recognition to land."
canon_refs:
  - "PROLOGUE_GROUNDED.md §73-104, §438-470, §536"
  - "design/VOICE_TEST_RISA.md"
  - "design/VOICE_TEST_RISA_TALKDOWN_ADDENDUM.md"
  - "design/STATE_MACHINE_RISA_TALKDOWN.md"
---

## Chief Risa Kade

Act 1 wingmate. Post-Grounded late-game sub-boss. The turncoat arc here is *reluctant* — she is not handling Kael, she is following orders she cannot question, carrying the weight. The stand-down path is gated on evidence: if the player arrives at the late-game confrontation with Solen-splinter proof, Risa can stand down. Without it, she completes her orders.

### Why the service coin stays visible

Regulation does not require the coin to be visible. Risa wears it out. It is the only sentimentality she allows herself and it reads, across the late-game reveal, as a thing she kept for a reason she never explained.
