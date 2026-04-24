---
id: communion-relay-trade-hall
location_type: station-cultural
scale_context:
  parent_ship: null
  parent_station: communion-relay
  parent_sector: "Keth Communion space"
  parent_system: null
controlled_by_faction: keth-communion
controlling_species: keth
environment_class: pressurized-humid
access_class: open
architectural_style: "Keth bio-resin organic — large cultural chamber with trade-seal crystal pedestals and visible wall-song"
visual:
  silhouette_cue: "open cultural chamber with trade-seal pedestals around the perimeter"
  palette: ["#f5eed6", "#c8932b", "#3d6a4b", "#d8b856", "#82705a"]
  lighting_mood: pulse-bioluminescent
  material_language: "bio-resin substrate walls pulsing softly, trade-seal crystal pedestals at the perimeter, central greeting dais"
  scale_logic: concourse
  signature_props:
    - "trade-seal crystal pedestals"
    - "central greeting dais"
    - "resin-bead exchange racks"
    - "seasonal-debt contract tables"
  art_lane: interior-inhabited
narrative:
  role: "Primary trading venue. Cultural-mechanics: seasonal-debt contracts mature in molts. Player learns Keth economic idiom here."
  cultural_weight: recurring-site
  notable_events:
    - event: "First Communion trade handshake via antenna-cross + trade-seal"
      era: "Act 3 mid"
      participants: [kael-maren]
      canon_ref: "PROLOGUE_GROUNDED.md §159-175"
  relationships:
    - target_id: communion-relay
      edge_type: controlled-by
      note: "sub-district of the parent station"
forbidden_inputs:
  - "haggling market aesthetic"
  - "Compact institutional framing"
signature_features:
  - "trade-seal crystal pedestals"
  - "pulse-bioluminescent chamber lighting"
  - "central greeting dais"
  - "perimeter resin-bead exchange"
canon_refs:
  - "PROLOGUE_GROUNDED.md §159-175"
  - "STATION_BIBLE.md §2 COMMUNION RELAY trade hall"
---

## Trade hall — Communion economic ground

Where the player learns Keth trade idiom. A seasonal-debt contract here does not resolve until the next molt; the economic time-horizon is the gameplay teaching moment.
