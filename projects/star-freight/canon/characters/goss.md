---
id: goss
role_class: station-resident
species: terran
faction_primary: null
tech_literacy: merchant-grade
combat_training: none
visual:
  silhouette_cue: "fuel-vendor with station kiosk"
  palette: ["#4a3c28", "#c8a878", "#2a1c14", "#d8b856", "#8a6a4a"]
  attire: "utility jumpsuit with fuel-grade chem tags, utility cap"
  build: compact-athletic
  hair: "greasy brown, short"
  eyes: "brown, cheerful"
  distinguishing_marks:
    - "fuel-grade chem tags on the jumpsuit"
    - "wrench earring"
  posture_default: "behind the kiosk counter, leaning elbow-down"
  signature_prop: "fuel-grade data-slate + chem-tag lanyard"
  age_description: "mid-twenties, cheerful, underfed-lean"
  art_lane: portrait
narrative:
  role: "Fuel vendor. Player's first Freeport economic interaction. Tutorial-as-NPC."
  voice: ["cheerful", "practiced", "sell-you-something"]
  motivation: "move fuel; keep the kiosk lights on"
  arc_beats:
    - "Act 2: first fuel sale, tutorial"
    - "Acts 2-3: recurring trade partner"
  relationships:
    - target_id: freeport-station
      edge_type: grew-up-at
  speech_register: "casual-Reach, salesy"
mechanical:
  combat_role: scout
  loyalty_starting: 0
forbidden_inputs:
  - "glamorous framing"
signature_features:
  - "fuel-grade chem tags"
  - "utility jumpsuit"
  - "kiosk-leaning posture"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §121, §243"
---

## Goss

Fuel vendor. The first Freeport NPC the player transacts with. Tutorial-as-NPC: Goss explains Freeport economics through a sales pitch.
