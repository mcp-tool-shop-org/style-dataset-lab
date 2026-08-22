# Cyclops register — design convergence (2026-08-22)

Five rounds, four wrong. Recorded so the wrong turns are not retaken, because each failure
taught a rule the canon did not have.

## The rounds

| # | seed | Read as | Why it failed |
|---|---|---|---|
| v1 | 770422 | Egyptian cat god | "predatory like a hunting animal" pulled Bastet |
| v2 | 770422 | The Predator (film) | "predatory" + "helm" + faceplate language |
| v3a/b | 918337 / 442901 | Pixar service droid | large round optic on a round head = baby schema |
| v4 | 615508 | Warframe alien bio-mech | "gaunt skeletal" produced literal ribcage anatomy |
| **v5** | **331774** | **issued military equipment** | **accepted direction** |

## Four rules earned, none of which were in the constitution

1. **Never describe the optic as an addition to a face.** v1/v2 said "a single optic in the centre
   of its faceplate." The word *faceplate* invites a face, so the model built two eye sockets and
   put the optic above them as a forehead lamp — reading as two eyes plus a headlamp. The fix is
   not a stronger negative; it is removing the face from the description entirely: a blank
   armoured block with **no sockets, no nose, no jaw**, and one aperture set into it.

2. **The optic must be SMALL and DEEP-SET.** This is the inverse of the first assumption. A large
   round lens centred on a head is the infant signal — big eyes read as sympathetic, and v3 came
   out adorable despite immaculate materials. A small pinpoint recessed far back in a dark housing
   reads as a threat. **Encoded as OPT-003.**

3. **Creature vocabulary produces creatures.** "Predatory," "hunting animal," "skeletal," "gaunt,"
   "blade-like" each dragged the design toward an organism. The Cyclops is a **product**; it must
   be described in manufacturing language — machined panels, countersunk fasteners, inspection
   hatches, hinge pins, actuator rods. **Encoded as CLS-002.**

4. **Uniformity has to be SHOWN, not stated.** UNI-001 says cyclops are indistinguishable units,
   but a single figure cannot demonstrate that. Putting **a second identical unit out of focus
   behind the first** is what finally made the register read as mass-produced rather than bespoke.
   Every cyclops lane row should consider a second unit in frame.

## The Director's design ruling

The axis being overshot was **friendly toy ←→ industrial hardware ←→ alien organism**. Ruling
(2026-08-22): **industrial product.** Manufactured military hardware, purposeful, uniform, zero
creature reference. Menace comes from height, stillness and the dead optic — never from silhouette
drama. This follows from UNI-001: mass-produced units cannot look bespoke or grown.

## v5 scoring

**Passes:** UNI-001 (two indistinguishable units in frame — first image to actually demonstrate
it), OPT-001, OPT-002, OPT-003, CLS-002, SYM-001, SEAM-001, NEON-001 + MAT-003 (chest bar and
forearm strips visibly spill cold blue onto adjacent white panels), MAT-002 (carbon weave at
consistent panel-relative scale), LIT-002 (wet ground, sodium lamp reflection).

**Open:** height did not land — reads near-human rather than two heads taller, and slightly bulky
rather than lean. Head is a plain box: functional, arguably correct banality for issued equipment,
but worth one more pass. Fix candidates: extreme low camera, a human figure in frame for scale, or
longer shin-to-thigh ratio.

## The contrast, which is the actual deliverable

Held constant across both registers: same flooded scrapyard, same dusk, same distant warm sodium
lamp, same lighting law. The outcast **belongs** to that warm light. The cyclops brings its own,
and is colder than the world it walks through. Neither was prompted to contrast with the other —
it falls out of one dataset under one rendering law, and it is the reason the `contact` lane
exists.

## Rounds 6–8: two more rules, one of them about method

| # | Read as | Why it failed |
|---|---|---|
| v6a | tank turret with a gun barrel | "like a tank turret" rendered literally, and the barrel broke SYM-001 |
| v6b | giant telephoto lens on shoulders | "like a camera lens assembly" rendered literally |
| v7 | faceted hood, aperture migrated to the CHEST | head shape improved; optic left the head entirely and became an arc reactor |
| **head study** | **accepted** | **close-up; the head finally got the model's full capacity** |

### 5. NEVER use a simile. Describe geometry.

Qwen renders named objects literally. Every analogy became the object:
"like a hunting animal" → an animal · "skeletal" → a ribcage · "like a tank turret" → a turret
with a gun · "like a camera lens assembly" → a telephoto lens. The Director's diagnosis of the
Predator and Egyptian-cat rounds was the same mechanism seen from the outside.

**Rule: cyclops prompts describe form only** — plate count, angles, taper, what protrudes (nothing),
where the aperture sits and how deep. No "like a", no real-world object names.

### 6. Design the head at CLOSE RANGE first, then propagate.

Seven full-body attempts all drifted on the head because at full-body framing the head is roughly
8% of the frame and receives almost none of the model's capacity. One tight head-and-shoulders
study resolved it immediately. **Any hard-surface design question gets its own close-up study
before it is asked for inside a full-body composition.** This is a method rule, not a canon rule,
and it applies to the outcast's repair grammar and the welded register's seams too.

## 🔒 LOCKED cyclops head — `cyclops_head_v3.png`, seed 208844

**Director: "Take v3 as-is and lock it." (2026-08-22).** `cyclops_head_v3.png` is THE cyclops
head. Every ferrochrome cyclops carries it. This supersedes headstudy_v2, which held the lock
briefly and is retained below as the intermediate step.

**The two changes that made v3 the answer:**

1. **No jaw.** The Iron Man read came from a lower chin panel plus defined cheek edges plus chrome
   side discs — that combination is a mask silhouette. The front of the head is now ONE continuous
   unbroken plate from crown to base, with **no horizontal seam crossing it anywhere**, and nothing
   on the sides.
2. **The eye is a WELL, not a dot.** The aperture is roughly a third of the plate's width, sunk
   into a dark shroud, with overlapping iris blades inside its mouth and a hard concentrated cyan
   point burning at the bottom of the shaft. This forced the OPT-003 correction below.

### The OPT-003 correction (important — the first version measured the wrong thing)

The rule originally read "the aperture is SMALL", earned from v3a/b where a large bright flush lens
on a round head came out adorable. That case still fails, but **scale was the wrong variable.**
What makes an optic threatening is **depth and shrouding**: a dark recess, blades inside it, and
the emitter at the bottom of the shaft rather than flush with the surface. Recessed reads
predatory at almost any diameter; flush and bright reads friendly at almost any diameter. And a
pinpoint too small reads inert — it has to be big enough to read as *attention*.

### headstudy_v2 (intermediate — aperture raised, still centred-scale)

The aperture sits in the **upper third** of the front plate, at roughly the height a person's
eyes would sit — NOT centred. The lower two thirds of the plate stay smooth and empty. Raising it
also made the aperture read smaller and deeper, which strengthens OPT-003 rather than weakening it.

Every ferrochrome cyclops from here carries this head. It is no longer an open question.

### Original head study (seed 208844, aperture centred) — superseded

A tapered faceted shell, wider at the crown, with a single smooth blank bone-white front plate.
Black carbon twill in the flanking recesses, chrome edging the panel joins, countersunk fasteners
throughout. The ONLY feature is one circular aperture at centre, sunk deep so the opening reads as
a dark pit, with a small hard cyan pinpoint at the bottom of it.

It is head-SHAPED, which is what makes it work: the silhouette invites you to look for a face and
there is nothing there but a hole with a light in it. Non-negotiable going forward — the aperture
stays on the head and never migrates to the chest.
