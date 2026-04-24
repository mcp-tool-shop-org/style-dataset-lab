---
id: keth-communion
faction_class: species-polity
visual:
  palette: ["#f5eed6", "#c8932b", "#3d6a4b", "#2a1c0a", "#82705a"]
  aesthetic_markers:
    - "organic bioluminescent architecture grown into resin substrate"
    - "amber-edged chitin plate uniform-analogues"
    - "antenna-cross greeting stance in group compositions"
    - "wall-song resin-substrate panels with pheromone-readable phrases"
    - "seasonal markers etched into non-censured wing-casings"
  silhouette_convention: "four-armed stance with lower arms at rest; antennae forward for attention, flat for deference"
  typography_style: "glyph-substrate — Communion glyphs grown directly into resin walls, not applied on top"
  uniform_or_attire_description: null
  architectural_style: "Keth bio-resin organic — bioluminescent veined walls, arched light-tubes following fiber lines, no sharp corners"
  faction_prop_signatures:
    - "resin-beads worn on upper arms (rank/season markers)"
    - "trade-seal chitin tokens"
    - "wall-song panels glowing soft amber"
reference_plate_uri: ""
narrative:
  voice: ["layered", "patient", "multi-register", "dense-with-indirect-reference"]
  values:
    - "patience and cultivation"
    - "communal memory over individual credit"
    - "respect for the elder council"
    - "reciprocal hospitality"
  taboos:
    - "defacing wall-song resin"
    - "interrupting an elder's pheromone-statement"
    - "failing to return the antenna-cross bow in kind"
    - "trading in bad faith — seasonal-debt that cannot be reciprocated"
  speech_register: "formal-layered — verbal clauses braided with pheromone counterpoint; humans hear only the verbal track"
  vocabulary_forbidden:
    - "individualist claims ('I alone', 'my personal')"
    - "immediate-urgency language not warranted by the situation"
    - "trade-haggling language below the seasonal-contract minimum"
  internal_tensions:
    - "elder-council orthodoxy vs censured-individual reform"
    - "colony independence vs Communion-wide coordination"
    - "trade-opening factions vs isolationist factions"
stance:
  toward_player_at_start: cordial
  toward_player_trajectory: "from cordial toward trading-partner as cultural-interaction depth grows; adversarial only if the player defaces wall-song or attacks Communion vessels"
  faction_edges:
    - target_id: terran-compact
      edge_type: formally-allied-faction
      note: "formal treaty; trade permitted"
      strength: 60
mechanical:
  reputation_starting_value: 0
  standing_deltas_by_action:
    - { action: "correct-antenna-cross-return", delta: 5 }
    - { action: "cultural-coaching-accepted", delta: 3 }
    - { action: "wall-song-defaced", delta: -40 }
    - { action: "trade-contract-honored-at-next-molt", delta: 10 }
  skill_bonuses_for_member:
    - "+1 to resin-lane hacks (grown infrastructure yields to Keth handling)"
    - "trade-access at Communion trade halls"
forbidden_inputs:
  - "fantasy medieval aesthetic"
  - "sharp-angled industrial Compact styling"
  - "photorealistic CGI"
signature_features:
  - "bioluminescent resin architecture"
  - "amber-chitin palette"
  - "antenna-cross greeting"
  - "wall-song panels"
freeze:
  status: soft-advisory
  frozen_reason: "Communion aesthetic is the alien-architecture anchor for the World LoRA. Any Keth-hosted scene — Communion Relay, Naia interactions, Tessik investigation — reads through this palette + architecture."
canon_refs:
  - "PROLOGUE_GROUNDED.md §24-26, §159-187, §347-363"
  - "style-dataset-lab/projects/star-freight/canon/species-canon.md §Keth"
  - "Communion_Mood_Anchors.json"
---

## Keth Communion — first alien society

The Communion is not one station, it is a distributed species-polity spanning multiple colony-stations linked by trade lanes and by wall-song synchronization rituals. Grounded shows the player one: Communion Relay.

### First-contact logic

Recent (on Keth timescales — two elder generations). The formal treaty with the Compact permits trade; military cooperation is restricted. Individual Keth are cordial toward respectful Terrans and patient with cultural missteps. Defacing wall-song or attacking Communion vessels flips the stance permanently.

### Elder council and censure

Naia-of-Threesong is a censured Keth — mark etched into wing-casings, visible to every Communion member. The censure is political as well as personal; the player's Act 3 interactions with Naia take place under elder-watch. Syratha is on the elder council that issued the censure. Grounded does not require the player to reconcile this; the full game does.
