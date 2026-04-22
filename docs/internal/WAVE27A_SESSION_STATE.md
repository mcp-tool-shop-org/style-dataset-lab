# Wave 27A Session State — 2026-04-14

## What's Done — ALL 5 ANCHORS PROMOTED

### Human Lane (txt2img)
- **Kael Maren** — anchor: `outputs/approved/kael_maren_anchor_s1.png` (seed 27001)
- **Renna Vasik** — anchor: `outputs/approved/renna_vasik_anchor_s2.png` (seed 27014)
- **Jace Delvari** — anchor: `outputs/approved/jace_delvari_anchor_s1.png` (seed 27025)

### Structural Lane
- **Naia-of-Threesong** — anchor: `outputs/approved/naia_anchor.png` (ControlNet v3 + clothing prompt)
  - Guide: `inputs/control-guides/naia_structural_guide_v3.png` (filled silhouette, wide lower arms)
  - Method: ControlNet canny 0.68 + appearance-first prompt ("alien worker wearing a fitted work suit")
  - Key lesson: describe CLOTHING not BIOLOGY. ControlNet handles body plan, prompt handles surface.
  - Remaining: legs slightly skeletal, box artifact. Fixable in follow-on pass.

- **The Corrigan** — anchor: `outputs/approved/corrigan_anchor.png` (IP-Adapter v5 s2)
  - Reference: `inputs/references/corrigan_reference.jpg`
  - Method: IP-Adapter 0.60, end 0.85 + reference-matched prompt describing two-tone hull, wide flat angular hull extension, three clustered engines
  - Shape is right. Color needs darkening + weathering in img2img post-processing.
  - Key lesson: actually LOOK at the reference and describe what you SEE. Describe COLOR explicitly.

## Scripts Created
- `scripts/generate-identity.js` — identity packet generator (txt2img + img2img phases)
- `scripts/generate-controlnet.js` — ControlNet structural discovery
- `scripts/generate-ipadapter.js` — IP-Adapter reference-guided generation

## Files Created
- `canon/identity-gates.md` — acceptance gates + ontology schema + lineage fields
- `inputs/identity-packets/wave27a-identity-spine.json` — 5 subjects x 4 shots
- `inputs/identity-packets/wave27b-prologue-expansion.json` — 3 subjects x 3 shots
- `inputs/identity-packets/wave28-prologue-locations.json` — 3 locations x 4 shots
- `inputs/identity-packets/naia-prompt-reframe.md` — prompt analysis doc
- `inputs/control-guides/naia_structural_guide_v3.png` — working Naia guide
- `inputs/control-guides/corrigan_structural_guide_v6.png` — silhouette from reference
- `inputs/references/corrigan_reference.jpg` — Corrigan shape reference

## Key Lessons Learned
1. Human characters land from txt2img alone — SDXL knows human anatomy and costumes
2. Non-human anatomy needs ControlNet with a filled silhouette guide (not wireframe)
3. Describe CLOTHING not BIOLOGY for alien characters — ControlNet handles body plan
4. Four-arm guide needs wide lower arm spread to prevent collapse to two arms
5. Ship scale needs composition framing (dock bay) not size words
6. IP-Adapter preserves shape from reference but overrides color — need to describe color explicitly
7. "No wings" in negative prompt suppresses features that ARE in the reference — don't negate what exists
8. Compare every output to the reference image before declaring success

## Resume Point
- All 5 anchors promoted to `outputs/approved/`
- Corrigan needs color/weathering in img2img post-processing (shape is locked)
- Naia needs one surface refinement pass (legs + box artifact)
- Then: follow-on pass for identity persistence across all 5 subjects
- Then: Wave 27B (Aldric, Risa, Lysa) + Wave 28 (locations)
