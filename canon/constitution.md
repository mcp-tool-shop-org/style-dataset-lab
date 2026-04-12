# RPG Item Icon Style Constitution

## Purpose

This document defines what "on-style" means for RPG item icons in this dataset.
Every approved/rejected judgment must cite rules from this constitution.

---

## Global Style Lock

**Target aesthetic:** Hand-painted fantasy RPG icons. Think classic JRPG inventory screens — Suikoden, Vagrant Story, Final Fantasy Tactics item art. Not photorealistic. Not pixel art. Not 3D rendered. Painterly with visible brushwork at full resolution, but clean silhouettes at 64px scale.

**Color philosophy:** Rich but not saturated. Earth tones + jewel accents. No neon. No pastel. Dark backgrounds (near-black or deep blue-grey) to unify the set.

---

## Rules

### SIL-001: Silhouette Readability
The item must be identifiable from its silhouette alone at 64x64 pixels. If you can't tell a sword from a staff by outline, it fails.

### SIL-002: Single Object
One item per icon. No paired items, no scatter, no scene composition. The icon IS the item.

### PAL-001: Palette Restraint
Maximum 5 dominant hues per icon (excluding background). No rainbow items. Color should serve material identity: steel = cool grey-blue, gold = warm amber, leather = warm brown, glass = translucent blue-green.

### PAL-002: Background
Solid dark background (#1a1a2e to #16213e range). No gradients, no patterns, no environmental context. The item floats.

### FRM-001: Centering and Framing
Item centered in frame. No more than 15% margin on any side. Item should fill 70-85% of the canvas area. No cropping.

### FRM-002: Consistent Scale
Similar items should appear at similar scales. A dagger should be noticeably smaller than a greatsword. A ring should be smaller than a gauntlet. Scale communicates item class.

### MAT-001: Material Readability
Surfaces must communicate their material. Metal needs specular highlights. Wood needs grain direction. Glass needs transparency cues. Cloth needs drape. If you can't tell what it's made of, it fails.

### MAT-002: Lighting Consistency
Single light source, top-left (10 o'clock). Consistent across all icons in the set. No dramatic rim lighting. No multiple shadows.

### DET-001: Detail Appropriate to Scale
Detail should serve readability, not impress at zoom. Fine engravings that disappear at 64px are wasted. Bold forms and clear material boundaries matter more than surface detail.

### DET-002: No Text or Symbols
No runes, letters, numbers, or readable text on items. Decorative patterns are fine if they don't resolve as text.

### STY-001: Painterly Execution
Visible brushwork, soft edges on organic materials, harder edges on metal/crystal. NOT photorealistic rendering. NOT cel-shaded. NOT pixel art. The style sits between concept art and finished illustration.

### STY-002: No 3D Render Artifacts
No ambient occlusion halos, no shader banding, no perfectly smooth gradients that scream "rendered." If it looks like it came out of Blender without a paintover, it fails.

### ART-001: Alpha Cleanliness
Clean alpha edges. No white/black halos from poor masking. No semi-transparent fringe. The edge between item and background must be sharp and artifact-free.

---

## Scoring Dimensions

When judging an icon, score these dimensions 0.0 to 1.0:

| Dimension | What it measures |
|-----------|-----------------|
| silhouette_clarity | Identifiable at 64px from outline alone |
| palette_adherence | Colors follow material logic, ≤5 hues, no neon |
| framing | Centered, correct fill ratio, no crop |
| material_fidelity | Surfaces read as their intended material |
| style_consistency | Matches painterly target, not 3D/photo/pixel |
| background_cleanliness | Solid dark bg, clean alpha, no artifacts |
| detail_level | Appropriate to scale, no wasted micro-detail |
| lighting_consistency | Single top-left source, consistent shadows |

**Approval threshold:** All dimensions ≥ 0.6, average ≥ 0.7.
**Rejection threshold:** Any dimension < 0.4, or average < 0.5.
**Borderline:** Everything else.
