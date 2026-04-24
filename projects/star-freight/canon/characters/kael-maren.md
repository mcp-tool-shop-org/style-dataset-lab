---
id: kael-maren
role_class: protagonist
species: terran
faction_primary: terran-compact
tech_literacy: military-grade
combat_training: elite-service-trained
visual:
  silhouette_cue: "removed-insignia fabric ghost and deckhand layer"
  palette: ["#2a3a4a", "#8a5a3a", "#1a1a1a", "#c2a888", "#d8b856"]
  attire: "charcoal flight jacket with removed-insignia fabric ghost, utilitarian deckhand underlayer, scuffed regulation boots"
  build: athletic
  hair: "dark short, Compact-regulation cut grown out a few weeks"
  eyes: "grey, keen, circles under them"
  distinguishing_marks:
    - "removed-insignia fabric ghost on jacket breast"
    - "faded Compact service tattoo on inner forearm"
    - "grease-stained hands — constant, from post-disgrace ship work"
  posture_default: "front-facing braced, weight slightly back, watching before speaking"
  signature_prop: "Compact-era logbook, handwritten, carried in an inner jacket pocket"
  age_description: "early thirties, worn by grief and grief's work"
  art_lane: portrait
  reference_plate_uri: "outputs/approved/anchor_01_deckhand_v3.png"
narrative:
  role: "Protagonist — disgraced Compact officer rebuilding from rock bottom; investigates the Solen conspiracy that cost him his wing"
  voice: ["blunt", "wry", "withheld", "steady"]
  motivation: "clear his wing's name — his own, after"
  arc_beats:
    - "Beat 1-5: Ardent flashback — wing ambush, Beat 5 court-martial, Solen's held gaze"
    - "Act 2 open: Freeport rock-bottom, Corrigan operational, first contract"
    - "Beat 9: Renna recruited; crew established"
    - "Beats 10-13: Communion Relay diplomacy and investigation-fragment acquisition"
    - "Beat 15: derelict rescue; Callum extracted; first encrypted chip recovered"
    - "Beat 16: horizon moment — the Threshold zoom-out; case unresolved, trajectory set"
  relationships:
    - target_id: aldric-solen
      edge_type: mentored-by
      strength: 70
      note: "framed by mentor; relationship now adversarial-personal"
    - target_id: aldric-solen
      edge_type: framed-by
      strength: 95
    - target_id: renna-vasik
      edge_type: crew-trust-bond
      strength: 50
      note: "builds across Acts 2-3"
    - target_id: the-corrigan
      edge_type: captain-of-ship
    - target_id: tcs-ardent
      edge_type: departed-from
      note: "disgrace"
    - target_id: terran-compact
      edge_type: exiled-from
      note: "nominally disgraced, not formally expelled — investigation alive"
  speech_register: "formal-Compact underneath, colloquial on top; reverts to rank-formal under stress"
  vocabulary_forbidden:
    - "modern slang"
    - "mythic idiom"
    - "fantasy register"
mechanical:
  combat_role: leader
  starting_hull: 100
  starting_morale: 60
  signature_abilities:
    - "compact-boarding-stance (service-trained CQB)"
    - "hardpoint-reading (identifies installed ship systems at a glance)"
  skill_tree_hints:
    - "investigation branch"
    - "diplomacy-under-suspicion branch"
  loyalty_starting: 100
forbidden_inputs:
  - "visible rank insignia (rank stripped)"
  - "clean pristine uniform"
  - "glamorous superhero framing"
  - "fantasy armor"
signature_features:
  - "removed-insignia fabric ghost"
  - "Compact-era logbook"
  - "grease-stained hands"
  - "circles under the eyes"
freeze:
  status: frozen
  frozen_reason: "Kael is the hero-5 anchor and Beat 16 horizon-moment subject. The removed-insignia fabric ghost + Compact-era logbook + grease-stained hands read is load-bearing for every establishing shot of the player. Frozen, not soft-advisory."
canon_refs:
  - "PROLOGUE_GROUNDED.md §53-63, §99-102, §243-244"
  - "design/VOICE_TEST_KAEL.md"
  - "wave27a-identity-spine.json §kael-maren"
---

## Commander Kael Maren

The player. Disgraced. Watched. Investigating the mentor who framed his wing.

### Why he carries the logbook

Compact officers carry digital service records. Kael carries a handwritten logbook — the one thing he took with him from the Ardent that Compact regulation did not forbid. It is how he remembers Beat 5 in his own handwriting, not the court-martial record's.

### Why the fabric ghost stays

Regulation allows discharged personnel to remove their insignia. It does not require sanding smooth the fabric beneath. Kael's fabric ghost is deliberate — not pride, not defiance, something closer to *I was this, and removing the pin doesn't change that I was.* Every approved reference plate shows the ghost. Never render Kael without it.
