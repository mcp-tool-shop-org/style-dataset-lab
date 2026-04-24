---
id: communion-relay-nav-office
location_type: station-interior
scale_context:
  parent_ship: null
  parent_station: communion-relay
  parent_sector: "Keth Communion space"
  parent_system: null
controlled_by_faction: keth-communion
controlling_species: keth
environment_class: pressurized-humid
access_class: credentialed
architectural_style: "Keth bio-resin organic — interior chamber with resin-channel navigation displays and wall-song panels"
visual:
  silhouette_cue: "rounded nav chamber with central console, resin-display walls"
  palette: ["#f5eed6", "#c8932b", "#3d6a4b", "#82705a", "#2a1c0a"]
  lighting_mood: warm-bioluminescent
  material_language: "bio-resin walls, crystal-display nav console, glow-softened instrument pedestals"
  scale_logic: cabin
  signature_props:
    - "central nav console with crystal display"
    - "wall-song panels flanking the chamber"
    - "elder-watch alcove at the rear"
    - "Naia's personal resin-bead rack"
  art_lane: interior-inhabited
narrative:
  role: "Where Naia-of-Threesong works. Primary Act 3 interaction site, 3-4 optional conversations, cultural-coaching teaching moments."
  cultural_weight: pivotal-site
  notable_events:
    - event: "Player first encounters Naia"
      era: "Act 3 mid"
      participants: [kael-maren, naia-of-threesong]
      canon_ref: "PROLOGUE_GROUNDED.md §347-363"
  relationships:
    - target_id: communion-relay
      edge_type: controlled-by
      note: "sub-district of the parent station"
    - target_id: naia-of-threesong
      edge_type: grew-up-at
forbidden_inputs:
  - "cold sterile lighting"
  - "industrial sharp angles"
signature_features:
  - "bio-resin wall panels"
  - "crystal nav display"
  - "warm-bioluminescent interior"
canon_refs:
  - "PROLOGUE_GROUNDED.md §347-363"
  - "STATION_BIBLE.md §2 COMMUNION RELAY nav-office"
---

## Navigation office — where Naia works

A chamber off the Communion Relay main concourse. Naia-of-Threesong's post — she handles nav-lane approvals for incoming traders. She is censured; the elder-watch alcove at the rear of the chamber is occupied during every player conversation.
