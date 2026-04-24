---
id: petra-wynn
role_class: crew-wingmate
species: terran
faction_primary: terran-compact
tech_literacy: military-grade
combat_training: service-trained
visual:
  silhouette_cue: "compact wingmate frame, flight-suit with wing insignia"
  palette: ["#2a3a4a", "#8a5a3a", "#1a1a1a", "#c2a888", "#d8b856"]
  attire: "Compact flight suit, wing insignia at shoulder, regulation boots"
  build: athletic
  hair: "dark short, regulation-trim"
  eyes: "brown, focused"
  distinguishing_marks:
    - "wing-leader pip at collar"
    - "service callus on the trigger hand"
  posture_default: "upright, military rest"
  signature_prop: "Compact-issue flight helmet carried under the arm in corridor shots"
  age_description: "late twenties, crisp, alert"
  art_lane: portrait
narrative:
  role: "Act 1 wingmate. Combat presence during Beats 1-5. Full-game Compact-subplot hook."
  voice: ["crisp", "alert", "direct"]
  motivation: "fly clean; serve"
  arc_beats:
    - "Beats 1-5: wing with Kael, Risa, Dak"
    - "Ambush: wing takes losses; Petra's condition is save-carry"
    - "Post-Grounded: full-game Compact subplot seed"
  relationships:
    - target_id: terran-compact
      edge_type: member-of-faction
    - target_id: kael-maren
      edge_type: close-bond-nonromantic
      note: "same wing"
    - target_id: tcs-ardent
      edge_type: crew-of-ship
  speech_register: "formal-Compact"
mechanical:
  combat_role: striker
  loyalty_starting: 40
forbidden_inputs:
  - "glamorous framing"
  - "fantasy register"
signature_features:
  - "Compact wing insignia"
  - "wing-leader pip"
  - "flight helmet under arm"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §73-96, §243"
---

## Lieutenant Petra Wynn

Act 1 wingmate. Grounded scope: tutorial-as-story wing presence. Her condition after the ambush is a save-carry variable feeding Compact subplot at full-game scope.
