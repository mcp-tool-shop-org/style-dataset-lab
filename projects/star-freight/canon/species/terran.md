---
id: terran
biology_class: terran-baseline
communication_modality:
  primary_language: "spoken Terran Standard"
  nonverbal_channel: "facial expression, posture, gesture — readable across most Terran cultures with minor variation"
  can_lie: yes
  signal_incompatibility_with_humans: "none (baseline)"
cultural_stance:
  time_horizon: season-scale
  core_value: "varies — compact discipline, reach solidarity, or private grievance, depending on origin"
  death_rite: "varies by polity — Compact funeral with rank honors; Reach cremation and scatter; civilian interment"
  trade_idiom: "contract-and-invoice"
  greeting_protocol: "verbal greeting plus gesture; rank-marked salutes in Compact service"
visual:
  body_plan: "bipedal four-limbed humanoid, two arms"
  anatomy_descriptors:
    locomotion: "upright bipedal"
    arm_count: 2
    sensory_organs: "two forward-facing eyes, external ears, facial features within human range"
    skin_or_integument: "skin tone spans the full baseline range"
    signature_appendages: "none beyond baseline"
  palette: ["#4a2e18", "#c2a888", "#2a2a2a", "#8a5a3a"]
  involuntary_expression_channel: "micro-expressions, blush, tearing, pupil dilation — readable to other Terrans, invisible to most alien species"
  sexual_dimorphism: "baseline Terran — varied"
  forbidden_morphology_drift:
    - "anime-stylized"
    - "chibi or cartoon"
    - "glamorized fantasy armor"
    - "superhero musculature"
  art_lane: species-anatomy-spec
relation_to_humans:
  baseline_stance: formally-allied
  narrative_framing: "baseline — the player's species"
  gameplay_integration: in-grounded
narrative:
  role: "Baseline species. Most named characters in Grounded are Terran. Canon entry exists so character entries can reference a species record."
  canonical_practices:
    - "Compact rank salutes"
    - "Reach informal address — first name or nickname regardless of rank"
  relationships:
    - target_id: terran-compact
      edge_type: species-member
forbidden_inputs:
  - "anime stylization"
  - "chibi proportions"
  - "clean pristine glamorized rendering"
signature_features:
  - "bipedal four-limbed humanoid"
  - "two arms, two eyes"
  - "baseline human proportions"
canon_refs:
  - "PROLOGUE_GROUNDED.md (baseline throughout)"
  - "style-dataset-lab/projects/star-freight/canon/species-canon.md §Terran"
---

## Terran baseline

Every Terran character in Grounded references this entry via `species: terran`. The species entry carries forbidden_morphology_drift so that the SDXL rendering path consistently suppresses anime / chibi / glamorized drift at the species level, not per-character.

Visual variance is encoded at the character level (Kael's early-thirties lean frame, Risa's veteran-NCO build, Jace's intelligence-field stance). The species entry does not constrain visual variance; it constrains stylization drift.
