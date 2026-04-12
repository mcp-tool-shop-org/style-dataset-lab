# Review Rubric — RPG Item Icons

## How to Review

For each candidate icon:

1. **First impression (2 seconds):** Can you tell what the item is? If not → likely reject.
2. **Silhouette test:** Squint or mentally shrink to 64px. Does the shape read? [SIL-001]
3. **Style check:** Does it look painted or rendered? Rendered → reject. [STY-001, STY-002]
4. **Background check:** Solid dark? Clean alpha edges? Any halos? [PAL-002, ART-001]
5. **Material check:** Can you name the materials? Metal/wood/glass/cloth? [MAT-001]
6. **Framing check:** Centered? Fills 70-85% of canvas? No crop? [FRM-001]
7. **Score all 8 dimensions** 0.0-1.0.
8. **Write explanation** citing specific rule IDs.

## Common Failure Modes

| Failure | Rule | How to spot |
|---------|------|-------------|
| alpha_halo | ART-001 | White/grey fringe around item edge |
| 3d_render_look | STY-002 | Too-smooth gradients, AO banding |
| off_palette | PAL-001 | Neon colors, > 5 hues, clashing tones |
| gradient_background | PAL-002 | Background isn't solid dark |
| lost_silhouette | SIL-001 | Can't identify item at 64px |
| multiple_items | SIL-002 | More than one object in frame |
| bad_framing | FRM-001 | Off-center, too much margin, cropped |
| unreadable_material | MAT-001 | Can't tell metal from wood |
| wrong_lighting | MAT-002 | Multiple light sources, bottom-lit |
| text_on_item | DET-002 | Runes or letters that read as text |
| micro_detail | DET-001 | Fine detail that vanishes at game scale |
| photorealistic | STY-001 | Looks like a photo, not painterly |

## Pairwise Comparison Protocol

When comparing A vs B:
1. Both must be same item type (don't compare a sword to a potion)
2. Judge which better matches the constitution, not personal preference
3. Cite the specific dimension(s) where one wins
4. If genuinely equal, mark as tie (but tries to avoid ties)
