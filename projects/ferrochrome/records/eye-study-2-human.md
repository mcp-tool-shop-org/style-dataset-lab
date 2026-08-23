# Eye study 2 — the human-like direction (2026-08-22)

**Director's call, after seeing the v4 role set:** *"Maybe we can go with more human-like eyes for
the outcasts, because these all look frightening and they're the good guys. If the humans were
advanced enough to make the androids then there's no reason why the eyes couldn't look almost
indistinguishable from humans."*

## Why the lens direction was wrong

It satisfied OPT-004 by defeating OPT-002. OPT-002 states outcast optics are ones **"you can see
into, which is why the outcasts read as sympathetic."** A machined bezel around a dark well is
precisely what you cannot see into. The two rules were in tension and the cure for one was
breaking the purpose of the other — on the faction that is supposed to be the good guys.

The canon settles it: empathy was a **design requirement** for these units, and makers capable of
building them could certainly build a convincing eye. A human eye on an outcast is not a failure of
the register, it is the register working.

## What is being tested

The axis is **how human, and at what cost to CLS-001.** The face stays composite in every variant —
that separation is the whole experiment, because v3 failed by letting human eyes drag the entire
face human with them. Only the eye paragraph changes.

**A** is fully human including lashes and brows. **B** removes the hair, which CLS-001 forbids on
the faceplate, keeping only human eye *structure*. **C** keeps the hair and adds a single hairline
orbital seam — "almost indistinguishable," with one tell for anyone close enough to look. **D**
tests whether warmth is carried by iris proportion rather than by hair at all.

The negative is rebuilt around the actual failure this time: `menacing, sinister, hostile, uncanny,
creepy, dark empty socket, machined bezel, camera lens eye`. The previous study's negative was
aimed at human-ness; this one is aimed at frighteningness.

## Recipe

Identical to eye study 1 — Qwen-2512 / shift 3.1 / euler / simple / 30 steps / cfg 2.5 /
1024×1280 / `SaveImage`, no RMBG. **Seed `770422` pinned across all four** so the eye paragraph is
the only variable.

## Prediction to check

The v4 chest lens should disappear on its own once this propagates. The vocabulary that leaked onto
the torso *was* the lens language; with no lens in the prompt there is nothing to leak.

## Shared body text

> ferrochrome. Cinematic-real close-up head-and-shoulders portrait of a decades-old colonial
> service android, facing the camera, head turned very slightly. It was built as a companion and it
> reads as gentle.
>
> The head is a moulded synthetic shell of matte off-white composite. Fine panel seams trace the crown, the temple and the line of the jaw. No hair on the scalp, no skin pores, no stubble. The nose and lips are sculpted in the same composite, smooth and matte.
>
> **‹EYE PARAGRAPH — varies per item›**
>
> Decades of field service: one replacement cheek panel in a paler off-white, slightly brighter than the shell around it, fine scratches through the finish along the jaw, a hairline crack sealed at the temple. Below the jaw the neck opens into machined vertebrae and bundled cable looms.
>
> Warm sodium light rakes gently from the left, soft shadow on the right, low-key. A small bright catchlight in each eye.

## The four eye paragraphs

### a_full_human  —  full human eyes — lashes and brows

> The eyes are warm and human. Each has a clear white sclera, a soft brown iris with fine radial fibres and a darker limbal ring, and a round black pupil, glossy and wet-looking. Soft moulded eyelids sit naturally over them with a gentle upper lid crease, fine dark eyelashes on both lids, and a soft natural eyebrow above each. The gaze is direct, calm and kind, with the faint softening at the outer corners of a person about to smile.

### b_no_hair  —  human structure, no lashes or brows

> The eyes are warm and human. Each has a clear white sclera, a soft brown iris with fine radial fibres and a darker limbal ring, and a round black pupil, glossy and wet-looking. Soft moulded eyelids sit naturally over them with a gentle upper lid crease. There are no eyelashes and no eyebrows — the brow above each eye is smooth sculpted composite. The gaze is direct, calm and kind.

### c_hairline_tell  —  human eyes + one faint manufactured seam

> The eyes are warm and human. Each has a clear white sclera, a soft brown iris with fine radial fibres and a darker limbal ring, and a round black pupil, glossy and wet-looking. Soft moulded eyelids sit naturally over them with a gentle upper lid crease, fine dark eyelashes and a soft natural eyebrow above each. The single sign that the face was built is a hairline seam in the composite tracing the orbital rim around each eye, so fine it is only visible this close. The gaze is direct, calm and kind.

### d_soft_gaze  —  human eyes, larger iris, softer gaze

> The eyes are warm and human, and a little larger and softer than average. Each has a clear white sclera, a wide soft hazel iris with fine radial fibres and a gentle limbal ring, and a large round black pupil, glossy and wet-looking. Soft moulded eyelids sit naturally over them with a gentle upper lid crease, fine eyelashes and a soft brow. The lower lids sit a little high, the way they do on a face that is listening. The gaze is warm, patient and unmistakably kind.

## Shared negative

> glowing eye, emissive eye, lamp eye, camera lens eye, machined bezel, metal ring around the eye, iris blades, dark empty socket, black void eye, hollow eye, third eye, extra optic, single eye, one eye, dead eyes, blank stare, menacing, sinister, hostile, uncanny, creepy, horror, skull, gaunt, sunken eyes, dark eye circles, neon, glowing panel lines, product shot, studio sweep, even fill, anime, cel shading, flat vector, blurry, low detail

## Findings

All four looked at full-size. Outputs in `outputs/candidates/eye-study-2/`. 4 submitted, 0 failed.

### The Director was right, and it is not close

Every variant reads warm, trustworthy and unmistakably like a good guy. The frightening quality is
gone completely. Crucially the faces did **not** collapse into "pale human with panel lines" — the
v3 failure — because the composite head is described separately from the eyes and the wear does the
rest: panel seams across crown, temple and jaw, the paler replacement cheek panel, fine scratches,
and machined vertebrae with cable looms at the neck. **The eyes can be fully human as long as
everything around them is honestly a machine.**

That is the real lesson, and it inverts the assumption behind both prior eye rules. Manufacturedness
was never the eyes' job. It is carried by the seams, the wear and the neck — and once those are
doing the work, the eyes are free to be entirely sympathetic.

### ⭐ B is the surprise

**B carries no eyelashes and no eyebrows and it is still warm.** It is also the most obviously
*built* of the four: a smooth composite brow with no hair on it reads as a made face immediately,
while the eyes underneath are as human and as kind as any of the others. It is the only variant
that satisfies both the Director's brief and the art contract's face material line ("no hair, no
skin, no pores") at the same time.

A, C and D are warmer still, but all three carry visible eyebrows and eyelashes — **hair on the
faceplate**, which the face material spec forbids. Adopting one of them means amending that line,
which is a legitimate call but should be a deliberate one rather than a side effect.

### Per variant

| | Eyes | Hair on face | Read |
|---|---|---|---|
| **A** | warm brown, sclera, iris fibres, catchlight | lashes + soft brows | Gentle half-smile. Gracious and calm. |
| **B** ⭐ | same human structure | **none** — smooth composite brow | Warm *and* the most legibly manufactured. Best balance. |
| **C** | same, most human of the four | lashes + clearly hairy brows | Warmest. The orbital seam did not resolve as a distinct feature. |
| **D** | larger hazel iris, high lower lid | lashes + soft brows | Softest, most "listening." Slightly youngest. |

### Notes

- The orbital hairline seam in **C** did not render as a readable feature. If a manufactured tell is
  wanted at close range it needs a stronger description than "so fine it is only visible this close."
- All four skew somewhat feminine and youthful at this seed. Since ROLE-001 makes this one face the
  species marker across all six roles, that is worth a deliberate look before it propagates.
- The negative rebuilt around *frighteningness* (`menacing, sinister, hostile, uncanny, creepy,
  dark empty socket`) rather than around human-ness did its job. Aim the negative at the failure you
  actually got, not the one you were guarding against last round.

### Consequence for the constitution

OPT-004 was amended earlier this session toward bezel-and-socket. That amendment is now **superseded
by this direction** and must be rewritten to match whichever variant is chosen. OPT-002 does not
need to change — this direction serves it better than the lens direction ever did.

### Prediction, still unverified

The v4 chest lens should vanish once this propagates, since the leaking vocabulary was the lens
language itself. Confirm it on the v5 role set rather than assuming it.
