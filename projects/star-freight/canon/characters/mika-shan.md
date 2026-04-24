---
id: mika-shan
role_class: station-resident
species: terran
faction_primary: null
tech_literacy: merchant-grade
combat_training: civilian-desperation
visual:
  silhouette_cue: "contract broker, layered trader coat"
  palette: ["#4a3c28", "#c8a878", "#2a1c14", "#d8b856", "#8a6a4a"]
  attire: "layered trader coat, utility vest, scuffed boots, a data-slate always in hand"
  build: lean
  hair: "black, tied back"
  eyes: "dark, calculating"
  distinguishing_marks:
    - "trader-guild pin (minor)"
    - "faint scar along the left cheek"
  posture_default: "one hand on the data-slate, one hand gesturing"
  signature_prop: "contract data-slate, always open"
  age_description: "mid-thirties, weathered-but-sharp"
  art_lane: portrait
narrative:
  role: "Contract broker at Freeport. Primary quest-giver Acts 2-3."
  voice: ["quick", "transactional", "wry", "practiced"]
  motivation: "clear the contract board; take her cut"
  arc_beats:
    - "Act 2: first contract handoff"
    - "Acts 2-3: recurring contracts and reputation gating"
  relationships:
    - target_id: freeport-station
      edge_type: grew-up-at
    - target_id: kael-maren
      edge_type: owes-favor-to
      strength: 30
      note: "depending on first-contract outcome"
  speech_register: "casual-Reach, transactional"
mechanical:
  combat_role: scout
  loyalty_starting: 0
forbidden_inputs:
  - "glamorous framing"
signature_features:
  - "contract data-slate always in hand"
  - "layered trader coat"
  - "trader-guild pin"
freeze:
  status: auto
canon_refs:
  - "PROLOGUE_GROUNDED.md §118, §243"
---

## Mika Shan

Freeport contract broker. Primary quest-giver Acts 2-3. Transactional — the player's relationship with her is measured in cleared contracts, not trust.
