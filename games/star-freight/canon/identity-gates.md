# Identity Gates — Named Subject Recognizability

> **Purpose:** Acceptance criteria for named characters, ships, and locations.
> The style constitution (constitution.md) gates archetype quality.
> This document gates **individual recognizability** — the difference between
> "a Reach mechanic" and "Renna Vasik."

---

## Record Schema Extension

Every identity-packet record adds an `identity` block and a `lineage` block
alongside the existing `provenance`, `judgment`, and `canon` blocks:

```json
{
  "identity": {
    "subject_name": "renna_vasik",
    "subject_type": "named_character",
    "faction": "reach",
    "role": "crew",
    "view_type": "anchor_portrait",
    "shot_type": "portrait",
    "identity_anchor": true,
    "location_name": null,
    "ship_name": null,
    "scene_function": "establish face and costume truth"
  },
  "lineage": {
    "generation_phase": "discovery",
    "anchor_source_image": null,
    "anchor_subject_version": null,
    "identity_persistence_score": null,
    "derived_from_record_id": null
  }
}
```

### Ontology Fields

| Field | Values | Required |
|-------|--------|----------|
| `subject_name` | snake_case canonical name | always |
| `subject_type` | `named_character`, `named_location`, `named_ship` | always |
| `faction` | `compact`, `keth`, `veshan`, `orryn`, `reach`, `none` | always |
| `role` | `protagonist`, `crew`, `antagonist`, `supporting`, `location`, `ship` | always |
| `view_type` | `anchor_portrait`, `full_body`, `context`, `expression_variant`, `establishing`, `signature_interior`, `functional_detail`, `lived_in_proof` | always |
| `shot_type` | `portrait`, `standing`, `working`, `variant`, `wide`, `interior`, `detail`, `proof` | always |
| `identity_anchor` | `true` / `false` | always |
| `location_name` | snake_case if applicable | if location/ship |
| `ship_name` | snake_case if applicable | if ship |
| `scene_function` | free text — what this image proves | always |

### Lineage Fields

The generation method is explicitly phased (discovery → anchor → follow-on).
If the records do not preserve lineage, the most valuable truth this wave
creates — which image is the source of identity — is lost.

| Field | Values | Required |
|-------|--------|----------|
| `generation_phase` | `discovery`, `anchor`, `follow_on` | always |
| `anchor_source_image` | asset path to the anchor image this was derived from | follow_on only |
| `anchor_subject_version` | version tag for the anchor (e.g. `kael_maren_v1`) | follow_on only |
| `identity_persistence_score` | 0.0-1.0 — how well this image matches the anchor | follow_on only |
| `derived_from_record_id` | record ID of the anchor this was img2img'd from | follow_on only |

**Phase values:**
- `discovery` — txt2img from prompt, no prior image input. All Phase 1 outputs.
- `anchor` — a discovery image promoted to anchor status after curation. The record
  is updated in place: `generation_phase` changes from `discovery` to `anchor`,
  and `identity_anchor` is set to `true`.
- `follow_on` — img2img or IP-Adapter output derived from an anchor. Must reference
  the anchor via `anchor_source_image` and `derived_from_record_id`.

**Validation rule:** The script MUST fail hard if a `follow_on` record is missing
`anchor_source_image` or `derived_from_record_id`. Discovery and anchor records
MUST have those fields set to `null`.

---

## Character Acceptance Gates

A named character image is approved ONLY if ALL gates pass:

### Gate IC-1: Silhouette Distinction
The character's outline reads as distinct from other characters in the same faction.
Kael must not look like generic Compact soldier. Renna must not look like generic Reach outlaw.

### Gate IC-2: Faction Legibility
Faction affiliation is legible without labels — but through the SPECIFIC
expression of that faction defined in the identity lock, not generic faction costume.

### Gate IC-3: Identity Persistence
Recurring identity traits survive across at least 2 images of the same character.
The anchor portrait establishes truth. Follow-on shots must read as the same person.

### Gate IC-4: Costume Integrity
Costume details do not drift into other factions. Renna's mismatched Reach gear
must not become clean Compact uniform. Jace's forgettable civilian must not
become obvious military.

### Gate IC-5: Spec Compliance
Prompt-spec essentials from Visual Bible Section 11 are visibly present.
Each character has 2-3 non-negotiable details. If they are absent, reject.

### Gate IC-6: No Generic Drift
The image must not read as "concept art of a sci-fi character." It must read
as "this specific person." If you could swap the name and it would fit equally
well, it fails this gate.

---

## Location/Ship Acceptance Gates

A named location or ship image is approved ONLY if ALL gates pass:

### Gate IL-1: Structural Repeatability
The structural identity (hull shape, room proportions, material palette) is
consistent enough that a follow-up image of the same place reads as the same place.

### Gate IL-2: Faction Material Language
The faction/material language is obvious and correct per constitution.
Freeport = Reach stripped. Communion Relay = Keth grown. Ardent = Compact pressed.

### Gate IL-3: Lived-In Proof
Lived-in detail supports the story role of this place. Freeport feels rough but
alive. The Ardent feels institutional. Communion Relay feels ancient and warm.

### Gate IL-4: Interior/Exterior Coherence
Interiors and exteriors feel like the same place or system. The Corrigan's
battered hull and cramped cockpit must share the same repair history.

### Gate IL-5: Spec Compliance
Key features from Visual Bible Section 11 are visibly present.
Each location has non-negotiable structural cues. If absent, reject.

---

## Allowed Shot Intents

Every shot in an identity packet must declare one of the following intents.
No other intent is valid. This prevents the variant slot from becoming
aesthetic wandering.

### Character Shots

| Intent | view_type | Purpose | Constraint |
|--------|-----------|---------|------------|
| **establish_identity** | `anchor_portrait` | Lock face, costume, and silhouette truth | Plain background, front-facing, identity-defining |
| **establish_silhouette** | `full_body` | Lock full-body costume and proportion truth | Plain background, full body, front-facing |
| **prove_in_context** | `context` | Prove the identity survives in a scene | Character in environment, must pass IC-3 |
| **persistence_under_shift** | `expression_variant` | Prove identity persists when expression or lighting changes | Same person, different internal state or light condition |
| **role_read_shift** | `expression_variant` | Prove identity persists when the character's social role shifts | Same person, different read (e.g. Jace friendly vs dangerous) |

**The variant slot is restricted.** An `expression_variant` shot MUST declare
one of exactly two allowed sub-intents:

1. **`persistence_under_shift`** — identity survives changed expression or lighting.
   The image must be unmistakably the same person as the anchor. Used for Kael
   (Freeport harsh lighting), Renna (assessment expression), Naia (curiosity flash).

2. **`role_read_shift`** — identity survives when the character's social presentation
   changes without silhouette drift. Used for Jace (friendly→dangerous). The
   dangerous version MUST be unmistakably the same man as the friendly anchor,
   not a second character. If you could imagine this is a different person, it fails.

**Variant gate (IC-V):** A variant shot is rejected if the subject's silhouette,
costume, or face structure drifts from the anchor. The ONLY things allowed to
change are expression, lighting, and the viewer's read of the character's intent.

### Location/Ship Shots

| Intent | view_type | Purpose | Constraint |
|--------|-----------|---------|------------|
| **establish_macro** | `establishing` | Lock overall form, material, and atmosphere | Wide or exterior shot, identity-defining |
| **establish_interior** | `signature_interior` | Lock the signature interior space | Interior shot of the most story-relevant room |
| **prove_function** | `functional_detail` | Prove the space works as described | Close functional detail, shows how the place is used |
| **prove_habitation** | `lived_in_proof` | Prove the space is lived in, not a set | Detail showing wear, use, and human/alien presence |

---

## Identity Lock Schema

Every named subject in a packet has an identity lock that defines hard visual anchors.
This is what separates "Renna-like" from Renna.

### Character Identity Lock

```yaml
identity_lock:
  face_shape: <age band, build, skin tone, distinguishing features>
  hair_head_structure: <hair color, style, length, head shape>
  body_language: <default posture, hand behavior, stance>
  costume_silhouette: <the outline that defines the character at 64px>
  non_negotiable_details:
    - <detail 1 — if absent, this is not the character>
    - <detail 2>
    - <detail 3>
  forbidden_drift_cues:
    - <visual element that would break the character>
```

### Named Ship/Vehicle Identity Lock

Ships that function as story-bearing identity anchors (The Corrigan, TCS Ardent
as exterior) use character-grade identity locks with visual personality fields,
not just structural description. A named ship IS a character.

```yaml
identity_lock:
  silhouette: <overall hull outline, proportions, asymmetry — what reads at distance>
  wear_pattern: <how damage and repair are distributed, what the history looks like>
  patch_logic: <the visual philosophy of repairs — what materials, how they layer>
  modification_philosophy: <what has been changed and why — functional not aesthetic>
  material_language: <faction origin + post-faction decay>
  non_negotiable_details:
    - <detail 1 — if absent, this is not the ship>
    - <detail 2>
    - <detail 3>
  recurring_identity_cues:
    - <cue that must appear in every image of this ship>
  forbidden_drift_cues:
    - <visual element that would break the ship's identity>
```

### Location Identity Lock

```yaml
identity_lock:
  structural_shape: <overall form, proportions, asymmetry>
  material_language: <faction material vocabulary + specific variants>
  signature_elements:
    - <element 1 — if absent, this is not the place>
    - <element 2>
    - <element 3>
  lighting_mood: <the default light temperature and quality>
  forbidden_drift_cues:
    - <visual element that would break the location>
```

---

## Scoring Extension

Identity-packet records use the constitution's 8 scoring dimensions PLUS
4 identity-specific dimensions:

| Dimension | What It Measures |
|-----------|-----------------|
| `identity_fidelity` | Does this read as the named subject, not just the archetype? |
| `anchor_consistency` | Does this match the anchor image for this subject? (N/A for anchors) |
| `spec_compliance` | Are non-negotiable details from the identity lock present? |
| `narrative_legibility` | Does this image tell you something about this character's story? |

**Identity approval threshold:** All identity dimensions >= 0.6, average >= 0.7.
Combined with constitution dimensions, both must pass independently.

---

## Generation Method

### Phase 1: Discovery (txt2img)
Generate 3-4 seeds per subject from composed prompt.
Purpose: find the face, silhouette, and costume truth.

### Phase 2: Anchoring (curation)
Select the strongest image as anchor. It becomes `identity_anchor: true`.
This image is the recurring truth source for all follow-on shots.

### Phase 3: Consistency (img2img or IP-Adapter)
Use the anchor as input for 1-2 follow-on shots (context, variant).
Light denoise (0.30-0.45) to preserve identity while changing pose/context.
Purpose: prove that the identity persists across views.

### Phase 4: Acceptance
Apply both constitution gates AND identity gates.
Both must pass independently. A stylistically correct image of the wrong person fails.

---

## Wave Assignment

| Wave | Phase | Subjects | Shot budget |
|------|-------|----------|-------------|
| 27A | Identity proof | Kael, Renna, Jace, Naia, Corrigan | 5 subjects x 4 shots = 20 images |
| 27B | Prologue expansion | Aldric, Risa, Lysa | 3 subjects x 4 shots = 12 images |
| 28 | Named locations | Freeport, Communion Relay, TCS Ardent | 3 locations x 4 shots = 12 images |

**Total generation budget:** 44 images across 11 subjects.
**Minimum approved:** 2 per subject (1 anchor + 1 follow-on) = 22 approved images.
**Target approved:** 3 per subject = 33 approved images.
