---
id: aldric-solen
role_class: officer-authority
species: terran
faction_primary: terran-compact
faction_cover: terran-compact
tech_literacy: intelligence-grade
combat_training: service-trained
visual:
  silhouette_cue: "capital-officer frame, Compact dress with full insignia intact"
  palette: ["#1a2a3a", "#5a6a78", "#d8b856", "#0e1a28", "#a8b4c0"]
  attire: "Compact service dress, full captain's insignia, 32-year-service pin cluster, polished regulation boots"
  build: heavy-muscular
  hair: "iron-grey, regulation-trim, combed back"
  eyes: "pale grey, held"
  distinguishing_marks:
    - "thin scar along the jawline (combat, twenty years ago)"
    - "Compact service pin cluster spanning the breast"
  posture_default: "still — Solen is defined by how still he holds when everyone else is moving"
  signature_prop: "captain's authenticator chip-tab on lanyard, visible"
  age_description: "early sixties, stern, thirty-two years into a career he still commands absolutely"
  art_lane: portrait
  reference_plate_uri: "outputs/approved/anchor_06_commander_v2.png"
narrative:
  role: "Mentor-turned-betrayer antagonist. Orchestrated the Ardent ambush. Runs Jace as a handler. Is running an operation inside Compact Intelligence that Fleet Command does not formally know about."
  voice: ["authoritative", "paternal-worn", "patient", "weighted"]
  motivation: "complete the splinter operation Fleet Command would never sanction; contain Kael's investigation"
  arc_beats:
    - "Pre-prologue: mentored Kael through service; trusted"
    - "Beat 5: presides at court-martial; held-gaze cinematic"
    - "Acts 2-3: off-screen; investigation evidence fragments accumulate"
    - "Late-game: confrontation; full reveal"
  relationships:
    - target_id: kael-maren
      edge_type: mentor-of
      strength: 80
      note: "pre-betrayal; Kael still reads the bond at Beat 5"
    - target_id: kael-maren
      edge_type: antagonist-personal
      strength: 100
    - target_id: jace-delvari
      edge_type: handler-of
      strength: 95
      note: "splinter-cell chain"
    - target_id: terran-compact
      edge_type: embedded-in-hostile-faction
      note: "operates inside the Compact, hostile to its stated mission"
  speech_register: "formal-Compact, rank-address always, patient cadence"
  vocabulary_forbidden:
    - "casual register"
    - "modern slang"
    - "fantasy or mythic idiom"
    - "visible anger"
turncoat_arc:
  status: covert-intelligence
  reveal_trigger: "Beat 15 — encrypted chip decoded; splinter operation surfaces"
  defection_threshold: null
  handler_faction: terran-compact
  canon_true_voice: ["cold", "authoritative", "patient", "uncompromising"]
  seeds:
    - "Regulations exist for a reason, Commander. We both know which ones."
    - "I did what was required. I'd do it again."
    - "You were the best officer in your class. You still are."
    - "The service asks things of us we don't get to choose. Mine was harder than yours."
mechanical:
  combat_role: leader
  starting_hull: 110
  starting_morale: 90
  signature_abilities:
    - "command-presence (NPCs respond to direct orders within hearing)"
    - "service-trained (baseline CQB plus thirty-two years of rank)"
  loyalty_starting: 0
forbidden_inputs:
  - "casual dress"
  - "visible distress"
  - "glamorous villain framing"
  - "fantasy idiom"
signature_features:
  - "32-year service pin cluster"
  - "full captain's insignia intact"
  - "authenticator chip-tab lanyard"
  - "unusual stillness in composed body language"
freeze:
  status: frozen
  frozen_reason: "Beat 5 court-martial held-gaze is the single most demanding cinematic shot in Grounded. Solen's read MUST land there. Frozen."
canon_refs:
  - "PROLOGUE_GROUNDED.md §53-63, §83-87, §99-102, §243-250"
  - "design/NPC_DEEP_ALDRIC_SOLEN.md"
  - "design/VOICE_TEST_SOLEN.md"
---

## Captain Aldric Solen

Thirty-two years in the service, mentor to Kael Maren, running a splinter operation Fleet Command would disavow. The Beat 5 court-martial is the entire prologue's cinematic anchor — the shot is Solen's held gaze across the chamber to Kael, and everything about Solen is calibrated to make that shot land.

### Why the service pin cluster is intact

Kael's insignia was removed. Solen's was not. The visual echo — full insignia on the mentor, fabric ghost on the student — IS the disgrace, rendered in metal and fabric.

### Full dive

NPC_DEEP_ALDRIC_SOLEN.md carries the deep characterization. The schema carries the structural edges that drive rendering + voice.
