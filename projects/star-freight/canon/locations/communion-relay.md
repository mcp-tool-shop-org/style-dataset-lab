---
id: communion-relay
location_type: station-cultural
scale_context:
  parent_ship: null
  parent_station: null
  parent_sector: "Keth Communion space"
  parent_system: null
controlled_by_faction: keth-communion
controlling_species: keth
environment_class: pressurized-humid
access_class: credentialed
architectural_style: "Keth bio-resin organic — bioluminescent veined walls, arched light-tubes following fiber lines, no sharp corners; grown not built"
visual:
  silhouette_cue: "organic station silhouette — rounded bioluminescent forms, no welded angles"
  palette: ["#f5eed6", "#c8932b", "#3d6a4b", "#2a1c0a", "#82705a"]
  lighting_mood: warm-bioluminescent
  material_language: "resin-substrate walls glowing soft amber, organic light-tubes following internal fiber lines, glyph-substrate signage grown into surfaces"
  scale_logic: concourse
  signature_props:
    - "wall-song resin panels (readable to Keth)"
    - "antenna-cross greeting posts at district thresholds"
    - "trade-seal crystal pedestals in the trade hall"
    - "elder-watch observation alcoves"
  art_lane: establishing
  reference_plate_uri: ""
narrative:
  role: "Act 3 first-contact location. Cultural mechanics, investigation fragment (Tessik), trading, Naia introduction."
  cultural_weight: pivotal-site
  notable_events:
    - event: "Naia-of-Threesong encounter, navigation office"
      era: "Act 3 mid"
      participants: [kael-maren, naia-of-threesong]
      canon_ref: "PROLOGUE_GROUNDED.md §347-363"
    - event: "Tessik investigation fragment handoff (archive district)"
      era: "Act 3 mid-late"
      participants: [kael-maren, tessik]
      canon_ref: "PROLOGUE_GROUNDED.md §175-187"
  forbidden_acts:
    - "defacing wall-song resin"
    - "interrupting an elder's pheromone-statement"
    - "trading in bad faith"
  relationships:
    - target_id: keth-communion
      edge_type: controlled-by
mechanical:
  accessible_at_start: false
  save_point: true
  combat_allowed: false
  trade_allowed: true
forbidden_inputs:
  - "industrial welded-angle architecture"
  - "Compact military aesthetic"
  - "cold sterile white lighting"
  - "medieval or fantasy framing"
signature_features:
  - "bioluminescent resin architecture"
  - "warm-bioluminescent lighting"
  - "glyph-substrate signage grown into walls"
  - "organic rounded forms, no sharp corners"
freeze:
  status: soft-advisory
  frozen_reason: "First on-screen alien station. Any drift toward industrial or human architecture breaks the first-contact read."
canon_refs:
  - "PROLOGUE_GROUNDED.md §24, §159-187, §272-274"
  - "STATION_BIBLE.md §2 COMMUNION RELAY"
  - "Communion_Mood_Anchors.json"
  - "wave28-prologue-locations.json §communion_relay"
---

## Communion Relay — the first alien station

The player's first on-screen alien station. The architecture is literally grown — bio-resin substrate cultivated over decades into bioluminescent walls, organic light-tubes, glyph-substrate signage. There are no welded angles in the entire station. The contrast with Freeport is the point.

### Districts

Grounded routes the player through three sub-locations under this parent:
- Navigation office (Naia's post, censured-Keth under elder-watch)
- Trade hall (cultural-mechanics trading)
- Archive corridor (Tessik, investigation)

A fourth — the outer ring where censured Keth live — is referenced in canon but not visited in Grounded; full-game content.

### Cultural mechanics at the threshold

Access is credentialed: the player earns entry at the docking threshold by correctly returning the antenna-cross bow from a greeter. Misread it, access delays (not denied — the Keth are patient). This is the first teachable cultural mechanic in the game and the aesthetic of the station is the frame that carries it.
