---
id: jace-delvari
role_class: crew-recruitable
species: terran
faction_primary: terran-compact
faction_cover: independent-freelancer
tech_literacy: intelligence-grade
combat_training: intelligence-field
visual:
  silhouette_cue: "friendly-cover gunslinger, holster forward"
  palette: ["#3a2a1a", "#a88878", "#1a1a1a", "#c8a878", "#d8b856"]
  attire: "weathered pilot jacket, shoulder holster worn forward and visible, dark utility trousers, worn spacer boots"
  build: lean
  hair: "dusty brown medium-length, slightly unkempt"
  eyes: "hazel, warm in greeting register; flat and evaluating when he thinks no one's reading him"
  distinguishing_marks:
    - "small service tattoo partially hidden under the jacket cuff (never fully visible — deliberate)"
    - "faint callus pattern on the trigger hand that reads field-trained"
  posture_default: "relaxed three-quarter, open palms forward until he's cornered"
  signature_prop: "shoulder holster with a pistol that reads civilian but is not"
  age_description: "late twenties, physically fit, watchful without performing watchfulness"
  art_lane: portrait
  reference_plate_uri: ""
narrative:
  role: "Second recruitable crew (Beat 8-9). Presents as freelance pilot; is deep-cover Compact Intelligence handling Kael as an asset."
  voice: ["warm", "disarming", "good-humored", "careful"]
  motivation: "complete the handling op without Kael realizing until it's too late"
  arc_beats:
    - "Beat 8: first contact at Freeport; recruitment pitch lands easy"
    - "Beat 9: joins crew; cover holds"
    - "Acts 2-3: observes Kael's investigation, reports back off-screen"
    - "Mid-game (post-Grounded): reveal — cover identity shed, handler named"
    - "Late-game defection branch: if high-trust, defects; otherwise confronted as antagonist"
  relationships:
    - target_id: kael-maren
      edge_type: crew-trust-bond
      strength: 60
      note: "cover relationship; true edge is targeted-by-handler"
    - target_id: kael-maren
      edge_type: targeted-by-handler
      strength: 100
      note: "true allegiance — kael is the asset"
    - target_id: terran-compact
      edge_type: works-covertly-for
      strength: 100
    - target_id: aldric-solen
      edge_type: reports-to
      strength: 90
      note: "splinter-cell chain"
  speech_register: "casual-spacer — matches Kael's register to build rapport; reverts to intelligence-handler register after reveal"
  vocabulary_forbidden:
    - "Compact military jargon (cover leak)"
    - "fantasy or mythic idiom"
turncoat_arc:
  status: covert-intelligence
  reveal_trigger: "mid-game, when Kael's investigation connects Solen to the splinter cell handling Jace"
  defection_threshold: 80
  handler_faction: terran-compact
  canon_true_voice: ["evaluative", "procedural", "cold-warm", "efficient"]
  seeds:
    - "Nice ship. The kind that gets noticed when it shouldn't."
    - "You ask good questions, Captain. Careful who you ask."
    - "I'm with you on this one. I am."
    - "Plans are easier than people think. People are the hard part."
    - "If I ever left, it'd be fast. Just — gone. You'd understand."
    - "My last captain? He made it back. Most of him."
    - "I like the quiet hours. The cargo doesn't ask."
    - "Loyalty is a line you draw. I just draw it where I see it."
    - "You're not what Compact thinks you are. That's worth something."
    - "Any handler would kill for crew like this. Lucky captain."
mechanical:
  combat_role: gunslinger
  starting_hull: 85
  starting_morale: 70
  signature_abilities:
    - "quick-draw-disarm (intelligence-field CQB)"
    - "cold-read (assesses a room's intent in under two seconds)"
  skill_tree_hints:
    - "gunslinger branch"
    - "covert-operations branch (revealed post-reveal)"
  loyalty_starting: 40
forbidden_inputs:
  - "glamorous framing"
  - "fantasy or mythic idiom"
  - "obvious-spy visual cues (trench coat, shades)"
  - "Compact military styling (cover leak)"
signature_features:
  - "shoulder holster worn forward"
  - "warm-then-flat eye register"
  - "civilian-reading pistol that isn't"
  - "service tattoo partially hidden under cuff"
freeze:
  status: soft-advisory
  frozen_reason: "Hero-5 Jace. Turncoat-seeds are the re-readable foreshadow of the whole reveal arc. Drift on voice or silhouette breaks the double-read on every Grounded Jace scene."
canon_refs:
  - "PROLOGUE_GROUNDED.md §392-416, §528-569"
  - "design/VOICE_TEST_JACE.md"
  - "design/DIALOGUE_SPEC_JACE.md"
  - "wave27a-identity-spine.json §jace-delvari"
---

## Jace Delvari — covert handler (Grounded: freelance pilot cover)

The single most important canon entry in Grounded from a schema-design perspective: Jace is the reason the turncoat_arc block exists. Every seed line above is re-readable — the surface reading is a spacer-captain bonding with his crew; the canon-true reading is a handler tracking an asset.

### The Kreia rule

*He never lies, he withholds.* Every line in seeds[] is true. *Nice ship. The kind that gets noticed when it shouldn't.* — his cover captain means it as a compliment; his handler self means it as a surveillance note. That this is a single sentence carrying both readings is the double-read doctrine the voice test documents.

### Cover mechanics

`faction_cover: independent-freelancer` — Jace's in-world presentation is an independent pilot-for-hire. This is not a formal faction; it is a labelled cover identity that Role OS caption-time dispatch reads to render him as a spacer. Reveal-scene dispatch branches on `faction_primary: terran-compact` + `turncoat_arc.handler_faction`, rendering him as Compact Intelligence operative after the reveal.
