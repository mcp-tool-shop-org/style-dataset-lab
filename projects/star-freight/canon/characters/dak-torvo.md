---
id: dak-torvo
role_class: crew-wingmate
species: terran
faction_primary: terran-compact
tech_literacy: military-grade
combat_training: service-trained
visual:
  silhouette_cue: "ensign wingmate, younger, flight-suit"
  palette: ["#2a3a4a", "#a88878", "#1a1a1a", "#c2a888", "#d8b856"]
  attire: "Compact flight suit, ensign rank markers, regulation boots"
  build: youthful
  hair: "light brown, short"
  eyes: "hazel, earnest"
  distinguishing_marks:
    - "ensign rank marker (new)"
  posture_default: "upright, slightly eager posture — newer to wing"
  signature_prop: "Compact-issue flight helmet"
  age_description: "early twenties, new-commission, still learning the wing"
  art_lane: portrait
narrative:
  role: "Act 1 wingmate. Save-carry consequence — may die in the ambush."
  voice: ["earnest", "respectful", "alert"]
  motivation: "prove himself to his wing"
  arc_beats:
    - "Beats 1-5: wing with Kael, Risa, Petra"
    - "Ambush: survival depends on player hold-vs-retreat choice"
    - "If alive post-Grounded: full-game Compact subplot seed"
  relationships:
    - target_id: terran-compact
      edge_type: member-of-faction
    - target_id: kael-maren
      edge_type: close-bond-nonromantic
      note: "same wing; Kael's responsibility"
    - target_id: tcs-ardent
      edge_type: crew-of-ship
  speech_register: "formal-Compact, rank-up register"
mechanical:
  combat_role: striker
  loyalty_starting: 50
forbidden_inputs:
  - "glamorous framing"
  - "fantasy register"
signature_features:
  - "Compact ensign rank markers"
  - "flight helmet"
  - "newer-to-service posture"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §73-96, §243"
---

## Ensign Dak Torvo

New to the wing. Grounded: his survival depends on Kael's hold-vs-retreat call at the ambush. Save-carry: dak-torvo-alive (Y/N) affects Risa's late-game dialogue and Compact subplot.
