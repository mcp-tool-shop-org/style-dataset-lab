---
id: communion-relay-archive
location_type: station-restricted
scale_context:
  parent_ship: null
  parent_station: communion-relay
  parent_sector: "Keth Communion space"
  parent_system: null
controlled_by_faction: keth-communion
controlling_species: keth
environment_class: pressurized-humid
access_class: covert-only
architectural_style: "Keth bio-resin organic — long dim corridor lined with wall-song archive panels"
visual:
  silhouette_cue: "long dim corridor, archive panels lining the walls"
  palette: ["#c8932b", "#3d2a1a", "#82705a", "#5a4a3a", "#d8b856"]
  lighting_mood: archive-amber-dim
  material_language: "deep bio-resin archive panels, subdued glow, older substrate generations visible in the deepest layers"
  scale_logic: corridor
  signature_props:
    - "wall-song archive panels (multiple generations of substrate)"
    - "Tessik's handoff nook"
    - "censure-mark transcription kiosks"
  art_lane: interior-inhabited
narrative:
  role: "Tessik's operating ground. Investigation-fragment handoff happens here. The archive is cultural memory — Tessik is one of the Keth who maintains it."
  cultural_weight: pivotal-site
  notable_events:
    - event: "Tessik transmits investigation fragment"
      era: "Act 3 mid-late"
      participants: [kael-maren, tessik]
      canon_ref: "PROLOGUE_GROUNDED.md §175-187"
  forbidden_acts:
    - "removing archive resin fragments"
    - "rendering transcriptions in non-Keth substrate"
  relationships:
    - target_id: communion-relay
      edge_type: controlled-by
      note: "sub-district of the parent station"
    - target_id: tessik
      edge_type: grew-up-at
forbidden_inputs:
  - "brightly lit clean interior"
  - "industrial shelving"
signature_features:
  - "dim archive-amber lighting"
  - "layered bio-resin archive panels"
  - "narrow corridor scale"
canon_refs:
  - "PROLOGUE_GROUNDED.md §175-187"
  - "STATION_BIBLE.md §2 COMMUNION RELAY archive"
---

## Archive corridor — where Tessik operates

Deep in the Communion Relay, a long dim corridor whose walls ARE the Communion's memory. Multiple generations of bio-resin substrate are visible in cross-section — the oldest layers closest to the floor, most recent near the ceiling. Tessik reads and maintains the archive; the player meets him here for the investigation handoff.
