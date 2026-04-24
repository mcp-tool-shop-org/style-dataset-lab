---
id: tcs-ardent
location_type: ship-interior
scale_context:
  parent_ship: null
  parent_station: null
  parent_sector: "Compact core worlds"
  parent_system: null
controlled_by_faction: terran-compact
environment_class: pressurized-breathable
access_class: credentialed
architectural_style: "Compact military functional — welded steel plates, exposed cable runs, institutional white corridor lighting, amber instrument glow"
visual:
  silhouette_cue: "capital carrier interior corridor framing ready-room and docking bay"
  palette: ["#e4e4e4", "#2a3a4a", "#d8b856", "#5a6a78", "#0e1a28"]
  lighting_mood: military-white
  material_language: "welded steel bulkheads, matte-finish flooring, exposed cable conduits, backlit amber console panels"
  scale_logic: corridor
  signature_props:
    - "rank-marker plaques at corridor junctions"
    - "authenticator pedestals at restricted-access doorways"
    - "fold-down crew station chairs along wall seams"
    - "mounted Compact banner in the ready-room"
  art_lane: establishing
  reference_plate_uri: ""
narrative:
  role: "Kael Maren's former posting. Act 1 is flashback — tutorial-as-story showing the disgrace. Acts 2-3 revisit only in memory."
  cultural_weight: central-to-prologue
  notable_events:
    - event: "Kael's Beat 5 court-martial held-gaze cinematic"
      era: "six months pre-prologue"
      participants: [kael-maren, aldric-solen]
      canon_ref: "PROLOGUE_GROUNDED.md §83-104"
    - event: "Beat 3 wingmate ambush staging — Dak / Petra / Risa in wing formation"
      era: "six months pre-prologue"
      participants: [kael-maren, risa-kade, petra-wynn, dak-torvo]
      canon_ref: "PROLOGUE_GROUNDED.md §73-96"
  forbidden_acts:
    - "unauthorized access to classified ops quarters"
    - "visible insubordination in the ready-room"
  relationships:
    - target_id: terran-compact
      edge_type: controlled-by
    - target_id: kael-maren
      edge_type: departed-from
      note: "Kael's last posting before disgrace"
mechanical:
  accessible_at_start: false
  save_point: false
  combat_allowed: false
  trade_allowed: false
forbidden_inputs:
  - "civilian station aesthetic"
  - "bioluminescent or organic architecture"
  - "fantasy or medieval framing"
  - "warm-colored lighting (breaks institutional-white cue)"
signature_features:
  - "institutional-white corridor lighting"
  - "amber instrument glow"
  - "rank-marker plaques at junctions"
  - "welded steel bulkheads"
freeze:
  status: frozen
  frozen_reason: "Beat 5 court-martial held-gaze is the most demanding cinematic shot in Grounded. The Ardent ready-room reads THIS WAY in that shot or the scene doesn't land."
canon_refs:
  - "PROLOGUE_GROUNDED.md §24, §71-104, §260-265"
  - "Ardent_Mood_Anchors.json"
  - "wave28-prologue-locations.json §tcs_ardent"
---

## TCS Ardent — Compact carrier

A capital-scale carrier. The player sees her interiors in Act 1 only — ready-room, corridor, docking bay, and the court-martial chamber. She is the world Kael loses.

### The court-martial

Beat 5 happens in the ready-room with Solen's held gaze as the decisive shot. The ready-room's lighting, composition, and palette are the cinematic frame for that moment. It is the single most important shot in the prologue and the only Grounded location entry frozen.

### Why she reappears as memory

Acts 2-3 do not revisit the Ardent on-screen but dialogue + investigation flashbacks reference her. The architectural_style and lighting_mood fields drive any memory-render consistently.
