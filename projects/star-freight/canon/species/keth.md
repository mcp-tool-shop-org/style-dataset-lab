---
id: keth
biology_class: arthropod-humanoid
communication_modality:
  primary_language: "thorax-resonance hum with pheromone counterpoint"
  nonverbal_channel: "pheromone emission (involuntary — cannot be fully suppressed in emotionally high-load states)"
  can_lie: partial-suppressible
  signal_incompatibility_with_humans: "pheromone channel invisible to humans; humans reading a Keth rely on antenna stance + wing-casing flare cues they have to be taught"
cultural_stance:
  time_horizon: multi-generational
  core_value: "patience and cultivation — the colony's memory outlives any one Keth"
  death_rite: "recycled to growth-vats, body chitin shaved and rendered into resin for next-generation wall-song"
  trade_idiom: "seasonal-debt — contracts measure in molts, not credits"
  greeting_protocol: "antenna-cross toward the elder, wing-casings held at rest; returning the bow in full is reserved for kin-rank"
visual:
  body_plan: "bipedal 4-armed chelicerate humanoid, segmented chitin carapace with amber-edged plates"
  anatomy_descriptors:
    locomotion: "digitigrade legs with wall-grip channel pads; secondary stabilizing gait when on resin surfaces"
    arm_count: 4
    sensory_organs: "two compound dark amber eyes + two segmented antennae, both expressive"
    skin_or_integument: "pale ivory chitin with amber-edged segment seams; joint membranes translucent with bioluminescent vein traces"
    signature_appendages: "wing-casings folded flat at rest, mandible plates framing the speech pharynx, twin resin-beads on upper arms"
  palette: ["#f5eed6", "#c8932b", "#2a1c0a", "#3d6a4b", "#82705a"]
  involuntary_expression_channel: "bioluminescent vein traces at joints intensify with emotional load; antenna lean angle telegraphs attention and deference"
  sexual_dimorphism: "minimal — chitin plate edging slightly thicker on one morph; visual read requires elder-level cultural coaching"
  forbidden_morphology_drift:
    - "Earth insect, bug, ant, spider, mantis, beetle"
    - "cute, chibi, human proportions, anime-stylized"
    - "two arms only"
    - "uncovered mammalian torso, breasts, navel"
    - "humanoid jaw or lips"
  art_lane: species-anatomy-spec
  reference_plate_uri: "outputs/approved/anchor_keth_anatomy_reference_pending.png"
relation_to_humans:
  baseline_stance: formally-allied
  narrative_framing: "first-contact recent (within two Keth elder generations); formal treaty permits trade; military cooperation restricted; human body-language unreadable to most Keth without coaching"
  gameplay_integration: in-grounded
narrative:
  role: "First alien species the player encounters in person (Act 3, Communion Relay). Cultural mechanics teach the player that unfamiliar does not mean hostile."
  canonical_practices:
    - "molt ceremonial — a Keth's shed chitin is sung back into resin-wall"
    - "wall-song (collective memory stored in resin substrate of each colony)"
    - "seasonal-debt accounting (contracts mature at next molt)"
    - "greeting antenna-cross (reciprocal; misreading the bow is forgivable, failing to return it is not)"
    - "censure mark etched into wing-casings (permanent; Naia carries one)"
  relationships:
    - target_id: keth-communion
      edge_type: species-member
    - target_id: terran-compact
      edge_type: formally-allied-faction
      note: "treaty era, trade permitted, military restricted"
forbidden_inputs:
  - "Earth-insect anatomy"
  - "chibi or anime stylization"
  - "exposed mammalian features"
signature_features:
  - "four arms (upper + lower pair)"
  - "segmented chitin carapace, amber-edged seams"
  - "two antennae and compound dark amber eyes"
  - "bioluminescent joint-vein glow"
  - "folded wing-casings"
freeze:
  status: soft-advisory
  frozen_reason: "Keth anatomy is the densest alien-biology signal in Grounded and the World LoRA's alien-visual anchor. Drift here ripples into every Keth character entry."
canon_refs:
  - "style-dataset-lab/projects/star-freight/canon/species-canon.md §Keth"
  - "PROLOGUE_GROUNDED.md §24-26, §159-187, §347-363"
  - "wave27a-identity-spine.json (Naia-of-Threesong anatomy spec)"
---

## Keth Communion arthropods

The Keth are the first alien species the player encounters on-screen in Grounded. They are **arthropod-humanoid** — four-armed, chitin-plated, compound-eyed — and the visual read must be instantaneous and unambiguous. The silhouette alone should carry the alien read at thumbnail scale.

### Cultural substrate

The Keth Communion is a species-polity whose memory is stored externally: the bioluminescent resin walls of each colony are literal wall-song, a cumulative record of what the colony has learned, witnessed, and grieved. A Keth who returns to their home-relay greets the wall first, their elders second. This is not metaphor — the resin encodes pheromonal phrases that younger Keth can *read*.

Censure is physical. A censured Keth (Naia-of-Threesong, in Grounded Act 3) carries the elder council's mark etched into their wing-casings. The mark is permanent and visible; fellow Keth read it before they read the censured Keth's face. Cultural mechanics in Act 3 teach the player to recognize the mark.

### Why they are canon-first here

Keth anatomy is the single densest alien-biology signal in Grounded. Trained correctly, a SDXL model rendering a Keth produces the Communion's entire aesthetic — palette, architecture, prop language, even posture. Trained incorrectly (Earth-insect drift, chibi anime drift, mammalian softening), the model's read of every Keth scene is ruined.

The species entry encodes the forbidden_morphology_drift at the species level, not per-character. Every Keth character inherits these negatives. This is the schema-level home for the feedback_alien_negative_prompt rule — SDXL needs `human` in the negative prompt for alien species; the Keth entry's forbidden_inputs + visual.forbidden_morphology_drift supplies that instruction structurally.
