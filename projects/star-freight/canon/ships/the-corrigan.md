---
id: the-corrigan
ship_class: cargo-hauler-small
tonnage_class: shuttle-scale
faction_of_origin: terran-compact
current_operator: independent
visual:
  silhouette_cue: "boxy cargo hauler, asymmetric profile from three generations of repair"
  palette: ["#5a3e24", "#c0a880", "#3a2a1e", "#d8b856", "#2a1a12"]
  hull_markings:
    - "faded CORRIGAN stencil across port flank"
    - "removed Compact registry numerals visible as outline"
    - "hand-stenciled Reach-salvage serial on starboard nacelle"
  hull_repair_history: three-generation-patched
  symmetry: asymmetric-from-repair
  material_dominant: "welded steel plates with riveted patches, one replacement nacelle in mismatched alloy"
  scale_cue_object: "docking arm towering overhead at Freeport"
  interior_architecture: "cramped two-seat cockpit, exposed cable runs, amber instrument glow, fold-down crew bunk aft of the cockpit"
  cockpit_style: "two-seat cramped, toggle switches not touchscreens, map-desk with paper charts backing the nav display"
  engine_signature: "one replacement nacelle in distinctly different alloy tone from the rest of the hull"
  art_lane: exterior-establishing
  reference_plate_uri: "outputs/approved/anchor_corrigan_pending.png"
narrative:
  role: "Player's home and mobility Acts 2-3. The ship Kael bought with severance at a Reach salvage auction eight months before the prologue opens."
  history_beats:
    - "Compact-decommissioned cargo hauler, retired at age fifteen"
    - "Acquired by Kael Maren from a Reach salvage auction, eight months pre-prologue"
    - "Three generations of visible repair — Compact, intermediate Reach owner, Kael's own"
    - "Registry numerals scrubbed but still readable as outline — a deliberate Reach-era choice, not a Kael one"
  named_crew:
    - kael-maren
    - renna-vasik
  named_passengers:
    - jace-delvari
  trade_capacity: "3-4 trade goods, low volume — intended for short-haul between Freeport and adjacent stations"
  current_status: in-service-playable
  relationships:
    - target_id: kael-maren
      edge_type: captain-of-ship
    - target_id: renna-vasik
      edge_type: crew-of-ship
    - target_id: freeport-station
      edge_type: docked-at
mechanical:
  hull_integrity_starting: 80
  fuel_capacity_starting: 100
  cargo_slots: 4
  modification_slots: 2
  crew_capacity: 3
  combat_capability: evasion-only
forbidden_inputs:
  - "pristine military vessel rendering"
  - "fantasy spelljammer styling"
  - "anime mecha aesthetic"
  - "clean new-paint finish"
signature_features:
  - "asymmetric hull from accumulated repairs"
  - "mismatched replacement nacelle"
  - "removed-registry outline still legible"
  - "three-generation patch history visible at dock scale"
  - "amber cockpit glow"
freeze:
  status: soft-advisory
  frozen_reason: "The Corrigan IS Maren's Acts 2-3 — the home-base silhouette the player sees every establishing shot. Any drift away from the asymmetric three-generation-patched read cheapens the whole rock-bottom arc."
canon_refs:
  - "PROLOGUE_GROUNDED.md §112-129, §224-225"
  - "wave27a-identity-spine.json §the_corrigan"
---

## The Corrigan — Kael's ship

A small cargo hauler that was a Compact vessel, then a Reach salvage lot, and now Kael's home. The asymmetric hull — one replacement nacelle in the wrong alloy, patches layered in three visible generations — is the thing you want the player to recognize at dock scale. They look across the Freeport bay and they *see* the Corrigan, not a ship.

### Why the registry outline stays

The Reach owner scrubbed the Compact registry numerals but left the outline legible. It is a deliberate choice — either pride (we do not erase what we inherit) or caution (a fully scrubbed hull reads criminal; an outlined hull reads legal-decommission). Kael's choice not to sand the outline smooth is part of his arc: he is trying to be independent without denying his origin, and the ship wears that on its hull.

### Save-carry variables

Hull integrity, fuel state, installed upgrades, cargo manifest — all carry forward into the full game. The Corrigan's condition at the end of Grounded is the condition at the start of the full game.
