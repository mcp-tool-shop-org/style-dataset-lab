---
id: terran-compact
faction_class: governmental
visual:
  palette: ["#2a3a4a", "#5a6a78", "#0e1a28", "#a8b4c0", "#d8b856"]
  aesthetic_markers:
    - "stenciled registry numbers on hull and uniform"
    - "removed-insignia fabric ghost outlines on disgraced personnel"
    - "regulation flight boots across ranks"
    - "amber instrument glow in cockpits and corridors"
    - "sanctioned Compact-blue underlines on rank markers"
  silhouette_convention: "columns with rank hierarchy visible in stance — ranking officer always forward-center in group compositions"
  typography_style: "blocky sans-serif with underline rank markers; registry numerals stencil-block"
  uniform_or_attire_description: "charcoal flight jackets with removed-insignia fabric ghosts, regulation boots, underline-rank cuffs"
  architectural_style: "Compact military functional — welded steel plates, exposed cable runs, amber instrument glow, institutional white corridor lighting"
  faction_prop_signatures:
    - "pulse pistols (Compact standard-issue)"
    - "data slates with blue backlit displays"
    - "authenticator chip-tabs on lanyards"
  reference_plate_uri: "outputs/approved/anchor_06_commander_v1.png"
narrative:
  voice: ["formal", "procedural", "invoking-regulation", "rank-explicit"]
  values:
    - "discipline"
    - "chain-of-command"
    - "frontier expansion"
    - "institutional memory"
  taboos:
    - "fraternization with Reach criminals"
    - "questioning Fleet Command publicly"
    - "discussing Compact Intelligence operations outside secure channels"
  speech_register: "hierarchical — address-by-rank always, first-name only among equals of same service branch"
  vocabulary_forbidden:
    - "sir/ma'am off-duty (civilian vocabulary)"
    - "slang terms for other species"
    - "casual profanity in mixed-rank contexts"
  internal_tensions:
    - "old guard vs reformists"
    - "core worlds vs frontier wings"
    - "Fleet proper vs Compact Intelligence splinter"
stance:
  toward_player_at_start: hostile-containment
  toward_player_trajectory: "from hostile-containment toward open-hostile or toward internal-split, depending on whether the player exposes the splinter or pushes back against Fleet directly"
  faction_edges:
    - target_id: keth-communion
      edge_type: formal-treaty
      note: "trade permitted, military restricted"
      strength: 60
    - target_id: sable-reach
      edge_type: nominal-jurisdiction-contested
      note: "Compact claims patrol authority in Reach-adjacent lanes; Reach does not recognize"
      strength: 75
mechanical:
  reputation_starting_value: -30
  standing_deltas_by_action:
    - { action: "dishonor-confrontation", delta: -20 }
    - { action: "comply-with-patrol", delta: 0 }
    - { action: "expose-splinter-evidence", delta: 10 }
    - { action: "kill-compact-patrol", delta: -40 }
  skill_bonuses_for_member:
    - "+1 to military-system hacks"
    - "ship-repair discount at Compact ports"
forbidden_inputs:
  - "clean pristine glamorized rendering"
  - "fantasy armor"
  - "medieval weapons"
signature_features:
  - "removed-insignia fabric ghost"
  - "Compact-blue rank underline"
  - "stenciled registry numerals"
  - "amber instrument glow + institutional white corridors"
freeze:
  status: soft-advisory
  frozen_reason: "Compact aesthetic is a core World LoRA target; Maren's disgraced-Compact silhouette depends on the removed-insignia fabric ghost reading as Compact at a glance. Drift is expensive."
canon_refs:
  - "PROLOGUE_GROUNDED.md §24-26, throughout"
  - "style-dataset-lab/projects/star-freight/canon/constitution.md"
  - "wave27a-identity-spine.json §kael-maren, §lysa-orin, §aldric-solen"
---

## Terran Compact — Fleet and Government

The player's origin and disgrace. Kael Maren wears the removed-insignia fabric ghost throughout Grounded; it is the single most load-bearing visual anchor in the prologue. Every Compact character references this faction — Compact discipline, Compact palette, Compact prop language.

### The visible Compact vs the splinter

Compact Intelligence is a legitimate sub-branch. The Solen / Jace operation is a *splinter* operating inside Compact Intelligence — a splinter-cell faction modeled separately for the full game. In Grounded the player never directly interacts with the splinter as a faction; they interact with its operators (Solen, Jace post-reveal) who present as Compact. The faction_cover mechanic on character entries expresses this: Jace's faction_cover is "independent" in Grounded, his faction_primary is the splinter, and his in-world appearance is Compact Intelligence.

### Stance trajectory

Hostile-containment at Grounded start means: Maren is under watch but not actively targeted. The trajectory turns on whether the player exposes the splinter (internal-split outcome — Fleet proper separates from the compromised apparatus) or pushes back directly (open-hostile outcome — Maren becomes an active Compact target).
