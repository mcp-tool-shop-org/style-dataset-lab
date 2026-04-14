# Naia Prompt Reframe — Appearance-First

## The Problem

Previous prompts described Naia from the inside out:
- "pale ivory chitin exoskeleton"
- "segmented chitin torso with three plate divisions"
- "compound amber eyes"
- "mandible plates"
- "bioluminescent veins at joints"

These are anatomical terms. SDXL reads them as instructions to render
exposed biological structure. The result: skeletal anatomical figures,
not a clothed alien person.

## The Fix

Describe Naia the way you'd describe Renna:
- What she's WEARING (harness, tool loops, bio-film layer)
- What her SURFACE looks like (smooth pale ivory, warm-toned edges)
- What her FACE reads as (large dark eyes, calm antennae, quiet)
- What MOOD she carries (competent, diminished, dignified)

Let the ControlNet guide handle the four-arm body plan.
Let the prompt handle how she looks and feels.

## Reframed Prompt (v3)

```
oil painting, semi-realistic painterly character concept art, muted dusty
palette, subtle dark edges, soft upper-left directional lighting, visible
brushstrokes, full body front-facing view,

alien worker standing upright wearing a bone-white woven utility harness
with tool loops across the torso, four arms with the upper pair resting
at sides and the lower pair holding small tools, smooth pale ivory skin
with warm amber edges at the joints, faint amber glow at wrists and
elbows, narrow diminished frame, elongated oval head with two large dark
glassy eyes, two thin antennae held carefully still, small folded
wing-structures flat against the back, dressed in a translucent amber
under-layer beneath the harness, faded marking on the chest, quiet
dignity, a worker not a warrior, isolated on plain dark background
```

## What Changed

| Old token | New token | Why |
|-----------|-----------|-----|
| chitin exoskeleton | smooth pale ivory skin | "exoskeleton" = render the skeleton |
| segmented chitin torso | narrow diminished frame | anatomy → silhouette impression |
| compound amber eyes | large dark glassy eyes | compound = faceted = insect specimen |
| mandible plates | (dropped) | too anatomical, guide handles face shape |
| bioluminescent veins | faint amber glow at wrists | veins = render vascular system |
| wing-casings folded | small folded wing-structures flat against back | casings = mechanical/insect |
| digitigrade legs | (dropped — guide handles this) | the prompt doesn't need to say it |
| arthropod alien | alien worker | arthropod = insect/specimen |
| chitin-fiber harness | bone-white woven utility harness | what it LOOKS like, not what it's MADE of |

## Negative Prompt (v3)

```
photorealistic, photograph, 3d render, smooth CG, anime, cartoon,
bright saturated colors, text, watermark, blurry, low quality,
human, person, man, woman,
skeleton, anatomical, medical illustration, bone, skull, exposed anatomy,
muscles, tendons, veins visible, biological diagram, specimen,
insect, bug, ant, beetle, spider, mantis, grasshopper,
robotic, mechanical, cyborg, Giger, biomechanical,
naked, nude, unclothed,
spread wings, flying, bright glowing,
statue, sculpture, figurine, action figure, toy
```

## ControlNet Strategy

- Try both canny (0.55 weight) and union/scribble mode
- Guidance end: 0.55 (release earlier so SDXL has more surface freedom)
- The guide locks WHERE the arms are. The prompt locks WHAT they look like.
- If scribble loses the four-arm plan, raise weight to 0.65
