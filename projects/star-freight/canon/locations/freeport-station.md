---
id: freeport-station
location_type: station-public
scale_context:
  parent_ship: null
  parent_station: null
  parent_sector: "Sable Reach"
  parent_system: null
controlled_by_faction: contested
environment_class: pressurized-breathable
access_class: open
architectural_style: "Reach salvaged chaotic — welded-together modules from decommissioned Compact, trader-guild, and independent hull sections; exposed power conduits run like vines"
visual:
  silhouette_cue: "asymmetric station silhouette — welded modules at angles, docking arms jutting"
  palette: ["#4a3c28", "#c8a878", "#2a1c14", "#d8b856", "#8a6a4a"]
  lighting_mood: harsh-station-yellow
  material_language: "mismatched hull panels, exposed conduits, hand-stenciled signage, ad-hoc lighting fixtures"
  scale_logic: concourse
  signature_props:
    - "hand-stenciled vendor signage"
    - "ad-hoc market tables in the concourse"
    - "docking-arm cradles with repair scaffolds"
    - "makeshift bunk-rental kiosks"
  art_lane: establishing
  reference_plate_uri: ""
narrative:
  role: "Acts 2-3 home base. The rock-bottom setting where Kael starts the post-disgrace arc. Market, contracts, repair, NPCs."
  cultural_weight: home-base
  notable_events:
    - event: "Kael arrives post-disgrace, establishes operations base"
      era: "Act 2 open"
      participants: [kael-maren]
      canon_ref: "PROLOGUE_GROUNDED.md §110-157"
    - event: "Renna recruited at Beat 9"
      era: "Act 2 mid"
      participants: [kael-maren, renna-vasik]
      canon_ref: "PROLOGUE_GROUNDED.md §120-146"
  forbidden_acts: []
  relationships:
    - target_id: sable-reach
      edge_type: controlled-by
      note: "nominal, not formal jurisdiction"
    - target_id: terran-compact
      edge_type: nominal-jurisdiction-contested
mechanical:
  accessible_at_start: true
  save_point: true
  combat_allowed: false
  trade_allowed: true
forbidden_inputs:
  - "clean Compact military aesthetic"
  - "organic or bioluminescent architecture"
  - "pristine corporate station rendering"
signature_features:
  - "asymmetric welded-module silhouette"
  - "harsh station-yellow lighting"
  - "hand-stenciled signage"
  - "exposed power conduits as visual texture"
freeze:
  status: soft-advisory
  frozen_reason: "Freeport is the home-base silhouette for Acts 2-3. Drift reads as a different station — breaks the rock-bottom Act 2 frame."
canon_refs:
  - "PROLOGUE_GROUNDED.md §24, §110-157, §267-269"
  - "Freeport_Mood_Anchors.json"
  - "wave28-prologue-locations.json §freeport"
---

## Freeport — Reach neutral ground

Not in STATION_BIBLE's 9-station canon; Freeport is Grounded-bespoke. A Reach-sector trade station welded together from decommissioned hull sections of half a dozen other ships, stations, and platforms. The aesthetic is *salvage made permanent* — nothing matches, nothing was designed, but it works and it has been working for decades.

### Act 2 rock-bottom

Kael arrives at Freeport disgraced, broke, and without a crew. The station's physical texture — harsh yellow lighting, hand-stenciled signage, ad-hoc market tables — is the visual register of that arc point. The same palette carries through Acts 2-3 until the player either earns the Corrigan's operational standing back or leaves for the Communion Relay.

### Sub-locations

Four Grounded sub-locations grow from the Freeport parent:
- Old Dren's bar (dim-bar-warm lighting; optional interactions)
- Market concourse (harsh-station-yellow; primary trade + Mika Shan contracts)
- Docking bay (station-yellow + shadows; Beat 9 Renna recruitment)
- Bunk-rental deck (harsh-station-yellow; save point + rest)

Sub-location entries reference this parent via `scale_context.parent_station: freeport-station`.
