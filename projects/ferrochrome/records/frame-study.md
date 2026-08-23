# Frame study — the role is the FRAME (2026-08-22)

**Director, on the v5 role set:** *"These androids are supposed to be degraded by the environment.
The heads look too clean and you have them too much into categories. The different types was
supposed to be different frames, not different outfits."*

All three criticisms are correct and they have one root cause each.

## What went wrong in v5

### 1. Naming the job produced the uniform

Every v5 prompt opened `full-body medical android` / `full-body warehouse android`. **Law #1 says
Qwen renders named things literally — and a named job comes with its costume.** The chassis
descriptions were present but buried under a coverall, so they never reached the silhouette.

**Fix: the job is never named.** Only geometry is described — proportion, mass distribution, limb
length, joint type, manipulator design. The role is left to be *inferred* from the build. If it
cannot be inferred, the frame design has failed and that is exactly what this study measures.

### 2. Clothing was a FIX and got promoted to a SIGNAL

Law #6 (worn colonial garments) was earned to kill the nudity attractor from law #5. In v5 it was
applied at full coverage, and **ROLE-001 — the chassis is the role marker — lost to it.** You
cannot read a squat low-centre-of-gravity frame through overalls.

**Fix: no garments at all.** The nudity attractor is handled positively instead, with heavy bolted
plating, exposed hydraulics and a hard rectangular torso housing with the pelvis fully enclosed.
This is already evidenced: v5's `security` had a bare chest plate and read as a machine, not a nude.
`clothing, coverall, overalls, apron, smock, coat, fabric` all go in the negative.

### 3. The wear was written onto the fabric, and the head wear was written to be invisible

v5's wear clauses put the dirt on cloth — *"cargo scuffs band the forearms," "oil soaked into the
fabric at the hips," "the apron is bleached."* A dirty outfit on a clean robot.

And the head block read *"**fine** panel seams… **fine** scratches… a **hairline** crack."* Every
one of those adjectives means *barely visible*. It was a prompt for a clean head and it produced
one. Eye-study 2's negative made it worse by carrying `gaunt, sunken eyes, horror, creepy` — actively
pushing toward pristine on units that are supposed to be decades of weather damage.

**Fix: the words are now loud** — blooming, crusted, chalked, pitted, scabbed, blistered, flaking,
bleeding rust — and **the head gets the same treatment as the body**, including a mismatched
unpainted cheek panel and rust streaking from the jaw fasteners. `clean, pristine, factory fresh,
glossy, polished, uniform, matching panels` go in the negative; the pristine-pushing terms come out.

## What is NOT changing

The human eyes are settled (Director's ruling, this session) and stay exactly as they are. What
changes is everything around them.

## The test

Four frames spanning the widest silhouette range in the role set. **The question is whether the
role reads from the build with no clothing and no job word in the prompt.** Judge these at
thumbnail size first — if the silhouettes are not obviously different units doing different work,
the frame vocabulary is still too weak and no amount of costume will save it.

Seeds `883100 + index`. Recipe otherwise unchanged.

## The four frames

### `squat_hauler` — warehouse — squat, wide, low CoG  (seed `883100`)

**Frame:** The frame is short and enormously broad: a low centre of gravity, a deep barrel torso sitting close to the ground, and shoulders nearly as wide as the figure is tall, built up with thick slabbed counterweight plating. The arms are long and heavy and hang past the knees, ending in oversized four-fingered gripping claws bigger than the head. The legs are short, thick and bowed, on wide flat pads. The head sits low between the shoulders with almost no neck showing.

**Wear:** The shoulder and forearm plating is worn down to bright bare metal in wide bands where decades of freight rubbed against it, and rust weeps from every bolt below those bands.

<details><summary>full positive prompt</summary>

> ferrochrome. Cinematic-real full-body photograph of a single derelict service robot, decades past its service life and never retired, standing facing the camera in a wide shot. The frame is short and enormously broad: a low centre of gravity, a deep barrel torso sitting close to the ground, and shoulders nearly as wide as the figure is tall, built up with thick slabbed counterweight plating. The arms are long and heavy and hang past the knees, ending in oversized four-fingered gripping claws bigger than the head. The legs are short, thick and bowed, on wide flat pads. The head sits low between the shoulders with almost no neck showing. The torso is a hard rectangular armoured housing of overlapping bolted plates over visible hydraulic lines and cable runs: no chest muscles, no breast forms, no waist taper, no navel, no skin anywhere. The hips and pelvis are fully enclosed in heavy mechanical plating. The head is a moulded synthetic shell. The eyes are warm and human: a clear white sclera, an iris with fine radial fibres and a darker limbal ring, a round black pupil with a wet gloss and a catchlight, under soft moulded eyelids. There are no eyelashes and no eyebrows and no hair. The gaze is direct and calm. The head is badly weathered by decades outdoors. Its off-white finish is chalked and faded unevenly, yellowed on one side and grey-green with oxidation on the other. Rust bleeds in streaks from the fasteners along the jaw and down the neck. A crust of dried salt whitens the recesses around the sockets and under the chin. The composite is deeply pitted and scarred across one cheek and the crown, one whole cheek panel has been replaced in a mismatched darker grey that was never repainted, and a long old crack across the temple is sealed with a visible ridge of grey filler. Dirt is ground into every seam. Below the jaw the neck is exposed machined vertebrae and bundled cable, tarnished and stiff with grime. The shoulder and forearm plating is worn down to bright bare metal in wide bands where decades of freight rubbed against it, and rust weeps from every bolt below those bands. Every surface of the machine is weathered by decades of planetary weather: oxidation blooming through the finish, salt crust in the recesses, mud dried into the joints, heat discolouration, deep pitting, and mismatched replacement panels in colours that do not match. It is obviously an individual with its own repair history, not one of a matching set. Cinematic-real, warm sodium light raking from the left, deep shadow on the right, low-key. No neon anywhere. Standing on a plain grey studio floor against a plain grey wall, the entire figure from the top of the head to both feet flat on the floor inside the frame.

</details>

### `tall_stilt` — agricultural — tall, lean, long reach  (seed `883101`)

**Frame:** The frame is extremely tall and thin, with a narrow shallow torso and disproportionately long spindly limbs. The legs are double-jointed with a backward-bending lower joint and end in very broad flat circular stabiliser pads for soft ground. The arms reach far below the knees and end in wide splayed rake-like manipulators. Slim nozzle and tank fittings are bolted along both forearms.

**Wear:** Corrosion has eaten upward from the pads across the entire lower leg, leaving the metal scabbed and blistered, and a pale green chemical coating is peeling off the shins in large curling flakes.

<details><summary>full positive prompt</summary>

> ferrochrome. Cinematic-real full-body photograph of a single derelict service robot, decades past its service life and never retired, standing facing the camera in a wide shot. The frame is extremely tall and thin, with a narrow shallow torso and disproportionately long spindly limbs. The legs are double-jointed with a backward-bending lower joint and end in very broad flat circular stabiliser pads for soft ground. The arms reach far below the knees and end in wide splayed rake-like manipulators. Slim nozzle and tank fittings are bolted along both forearms. The torso is a hard rectangular armoured housing of overlapping bolted plates over visible hydraulic lines and cable runs: no chest muscles, no breast forms, no waist taper, no navel, no skin anywhere. The hips and pelvis are fully enclosed in heavy mechanical plating. The head is a moulded synthetic shell. The eyes are warm and human: a clear white sclera, an iris with fine radial fibres and a darker limbal ring, a round black pupil with a wet gloss and a catchlight, under soft moulded eyelids. There are no eyelashes and no eyebrows and no hair. The gaze is direct and calm. The head is badly weathered by decades outdoors. Its off-white finish is chalked and faded unevenly, yellowed on one side and grey-green with oxidation on the other. Rust bleeds in streaks from the fasteners along the jaw and down the neck. A crust of dried salt whitens the recesses around the sockets and under the chin. The composite is deeply pitted and scarred across one cheek and the crown, one whole cheek panel has been replaced in a mismatched darker grey that was never repainted, and a long old crack across the temple is sealed with a visible ridge of grey filler. Dirt is ground into every seam. Below the jaw the neck is exposed machined vertebrae and bundled cable, tarnished and stiff with grime. Corrosion has eaten upward from the pads across the entire lower leg, leaving the metal scabbed and blistered, and a pale green chemical coating is peeling off the shins in large curling flakes. Every surface of the machine is weathered by decades of planetary weather: oxidation blooming through the finish, salt crust in the recesses, mud dried into the joints, heat discolouration, deep pitting, and mismatched replacement panels in colours that do not match. It is obviously an individual with its own repair history, not one of a matching set. Cinematic-real, warm sodium light raking from the left, deep shadow on the right, low-key. No neon anywhere. Standing on a plain grey studio floor against a plain grey wall, the entire figure from the top of the head to both feet flat on the floor inside the frame.

</details>

### `slight_domestic` — companion — slender, light, fine hands  (seed `883102`)

**Frame:** The frame is small, slender and lightly built, close to a human in proportion but narrower: a shallow torso, thin limbs with visibly exposed cable bundles at the elbows and knees, and slim five-fingered hands with delicate finely articulated fingers. There is almost no armour, and the plating is thin and smoothly rounded.

**Wear:** The thin plating is rubbed through to bare metal along the forearms and the front of the thighs from decades of being touched and leaned against, and the exposed metal beneath has gone brown with oxidation.

<details><summary>full positive prompt</summary>

> ferrochrome. Cinematic-real full-body photograph of a single derelict service robot, decades past its service life and never retired, standing facing the camera in a wide shot. The frame is small, slender and lightly built, close to a human in proportion but narrower: a shallow torso, thin limbs with visibly exposed cable bundles at the elbows and knees, and slim five-fingered hands with delicate finely articulated fingers. There is almost no armour, and the plating is thin and smoothly rounded. The torso is a hard rectangular armoured housing of overlapping bolted plates over visible hydraulic lines and cable runs: no chest muscles, no breast forms, no waist taper, no navel, no skin anywhere. The hips and pelvis are fully enclosed in heavy mechanical plating. The head is a moulded synthetic shell. The eyes are warm and human: a clear white sclera, an iris with fine radial fibres and a darker limbal ring, a round black pupil with a wet gloss and a catchlight, under soft moulded eyelids. There are no eyelashes and no eyebrows and no hair. The gaze is direct and calm. The head is badly weathered by decades outdoors. Its off-white finish is chalked and faded unevenly, yellowed on one side and grey-green with oxidation on the other. Rust bleeds in streaks from the fasteners along the jaw and down the neck. A crust of dried salt whitens the recesses around the sockets and under the chin. The composite is deeply pitted and scarred across one cheek and the crown, one whole cheek panel has been replaced in a mismatched darker grey that was never repainted, and a long old crack across the temple is sealed with a visible ridge of grey filler. Dirt is ground into every seam. Below the jaw the neck is exposed machined vertebrae and bundled cable, tarnished and stiff with grime. The thin plating is rubbed through to bare metal along the forearms and the front of the thighs from decades of being touched and leaned against, and the exposed metal beneath has gone brown with oxidation. Every surface of the machine is weathered by decades of planetary weather: oxidation blooming through the finish, salt crust in the recesses, mud dried into the joints, heat discolouration, deep pitting, and mismatched replacement panels in colours that do not match. It is obviously an individual with its own repair history, not one of a matching set. Cinematic-real, warm sodium light raking from the left, deep shadow on the right, low-key. No neon anywhere. Standing on a plain grey studio floor against a plain grey wall, the entire figure from the top of the head to both feet flat on the floor inside the frame.

</details>

### `asym_wrench` — maintenance — wiry, asymmetric, tool-armed  (seed `883103`)

**Frame:** The frame is wiry and visibly asymmetric: one arm is a normal slim manipulator, the other is heavier and ends in a folded cluster of tools and grippers instead of a hand. Thick cable looms run openly along the outside of both arms and both legs. Heavy scarred kneepads and a broad utility belt of clips and pouches are bolted directly to the frame.

**Wear:** The forearms and the front of the torso are blackened and blistered by heat, oil has soaked black into every joint and hinge, and the plating is a patchwork of mismatched replacement panels in four different greys that were never repainted to match.

<details><summary>full positive prompt</summary>

> ferrochrome. Cinematic-real full-body photograph of a single derelict service robot, decades past its service life and never retired, standing facing the camera in a wide shot. The frame is wiry and visibly asymmetric: one arm is a normal slim manipulator, the other is heavier and ends in a folded cluster of tools and grippers instead of a hand. Thick cable looms run openly along the outside of both arms and both legs. Heavy scarred kneepads and a broad utility belt of clips and pouches are bolted directly to the frame. The torso is a hard rectangular armoured housing of overlapping bolted plates over visible hydraulic lines and cable runs: no chest muscles, no breast forms, no waist taper, no navel, no skin anywhere. The hips and pelvis are fully enclosed in heavy mechanical plating. The head is a moulded synthetic shell. The eyes are warm and human: a clear white sclera, an iris with fine radial fibres and a darker limbal ring, a round black pupil with a wet gloss and a catchlight, under soft moulded eyelids. There are no eyelashes and no eyebrows and no hair. The gaze is direct and calm. The head is badly weathered by decades outdoors. Its off-white finish is chalked and faded unevenly, yellowed on one side and grey-green with oxidation on the other. Rust bleeds in streaks from the fasteners along the jaw and down the neck. A crust of dried salt whitens the recesses around the sockets and under the chin. The composite is deeply pitted and scarred across one cheek and the crown, one whole cheek panel has been replaced in a mismatched darker grey that was never repainted, and a long old crack across the temple is sealed with a visible ridge of grey filler. Dirt is ground into every seam. Below the jaw the neck is exposed machined vertebrae and bundled cable, tarnished and stiff with grime. The forearms and the front of the torso are blackened and blistered by heat, oil has soaked black into every joint and hinge, and the plating is a patchwork of mismatched replacement panels in four different greys that were never repainted to match. Every surface of the machine is weathered by decades of planetary weather: oxidation blooming through the finish, salt crust in the recesses, mud dried into the joints, heat discolouration, deep pitting, and mismatched replacement panels in colours that do not match. It is obviously an individual with its own repair history, not one of a matching set. Cinematic-real, warm sodium light raking from the left, deep shadow on the right, low-key. No neon anywhere. Standing on a plain grey studio floor against a plain grey wall, the entire figure from the top of the head to both feet flat on the floor inside the frame.

</details>

## Shared blocks

### TORSO

> The torso is a hard rectangular armoured housing of overlapping bolted plates over visible hydraulic lines and cable runs: no chest muscles, no breast forms, no waist taper, no navel, no skin anywhere. The hips and pelvis are fully enclosed in heavy mechanical plating.

### FACE

> The head is a moulded synthetic shell. The eyes are warm and human: a clear white sclera, an iris with fine radial fibres and a darker limbal ring, a round black pupil with a wet gloss and a catchlight, under soft moulded eyelids. There are no eyelashes and no eyebrows and no hair. The gaze is direct and calm.

### HEAD_WEAR

> The head is badly weathered by decades outdoors. Its off-white finish is chalked and faded unevenly, yellowed on one side and grey-green with oxidation on the other. Rust bleeds in streaks from the fasteners along the jaw and down the neck. A crust of dried salt whitens the recesses around the sockets and under the chin. The composite is deeply pitted and scarred across one cheek and the crown, one whole cheek panel has been replaced in a mismatched darker grey that was never repainted, and a long old crack across the temple is sealed with a visible ridge of grey filler. Dirt is ground into every seam. Below the jaw the neck is exposed machined vertebrae and bundled cable, tarnished and stiff with grime.

## Shared negative

> clean, pristine, new, factory fresh, showroom, glossy, polished, uniform, matching panels, freshly painted, undamaged, clothing, clothes, coverall, overalls, apron, smock, coat, shirt, trousers, fabric, uniform costume, machined bezel, metal ring around the eye, camera lens eye, lens on the chest, chest aperture, dark empty socket, glowing eye, emissive eye, third eye, extra optic, single eye, one eye, eyelashes, eyebrows, hair, skin, skin pores, nude, naked, chest muscles, breast forms, waist taper, navel, weapon, gun, rifle, neon, glowing stripes, two figures, group, crowd, product shot, studio sweep, even fill, anime, cel shading, flat vector, blurry, low detail, cropped, close-up, cut off legs, cut off feet

## Findings

All four looked at full-size. Outputs in `outputs/candidates/frame-study/`. 4 submitted, 0 failed,
alpha polarity correct out of the graph.

### ✅ The frames read, and it is not close

Four unmistakably different machines. `squat_hauler` is genuinely short and wide with long heavy
claw-arms hanging past the knee and a head sunk between the shoulders. `tall_stilt` is a spindly
thing on broad oval pads. `slight_domestic` is light and thin with exposed cable bundles at every
joint. `asym_wrench` is visibly lopsided — a slim pale left arm against a heavy blackened right one
ending in a wrench hand. **You could tell all four apart from silhouette alone at thumbnail size.**

Dropping the job noun is what did it. As soon as the prompt stopped saying *"warehouse android"* and
started describing mass, limb length and joint geometry, the model built a machine for the job
instead of dressing an actor as one.

### ✅ No clothing, and nothing reads nude

The nudity attractor never appeared. Heavy bolted plating with exposed hydraulics and an enclosed
pelvis handles it completely — law #6's garments were never needed for that job, only for the
*slim smooth pale* bodies that triggered it. **Law #6 is downgraded: clothing is optional set
dressing, never the role signal.**

### ✅ The degradation is real now

Rust bleeding from fasteners, mismatched unpainted replacement panels in yellow/green/grey, chalked
and faded finish, salt crust in the recesses and on the foot pads, deep pitting, heat blackening.
The heads are weathered to the same degree as the bodies — half-yellowed, cracked, chipped at the
crown, rust streaking down the jaw.

Swapping the minimising adjectives (*fine, hairline*) for loud ones (*blooming, crusted, chalked,
scabbed, blistered, bleeding*) and putting `clean, pristine, factory fresh, glossy, polished` into
the negative is the whole fix.

## ⚠ Three things still wrong — do not treat this as finished

### 1. The heads are IDENTICAL, which is the same failure one level up

All four carry the same damage: the same half-white/half-grey vertical split, the same crack, the
same yellow patch, rust in the same places. That is because `HEAD_WEAR` is a single fixed block
shared by every unit — **so the set is uniform in exactly the way the Director objected to, just at
the head instead of the outfit.** `ROLE-001` wants any two outcasts to be obviously different units.

Fix: `HEAD_WEAR` must be per-unit. Vary which side is faded, where the replacement panel sits,
whether the damage is a crack or a chip or a burn, which fasteners bleed.

### 2. The faces drifted toward FLESH, which is the wrong register

`asym_wrench` in particular reads as an elderly human man's face — wrinkles, skin texture, organic
modelling — bolted to a machine. That is the **WELDED** register, not OUTCAST. `slight_domestic` is
heading the same way.

The human-eye ruling was about the **eyes**. The face around them must stay *moulded composite* —
the material-first description from law #2 got cut down to one short line here ("a moulded synthetic
shell") and that was not enough to hold it. Restore the full material description and add `human
skin, wrinkles, aged skin, flesh` to the negative.

### 3. Law #1 bit again — `tall_stilt` has literal garden rakes for hands

*"wide splayed rake-like manipulators"* produced two actual garden rakes. Same failure as
"like a tank turret" → a turret. **Describe the geometry: "wide splayed manipulators with four long
thin tines."** `squat_hauler`'s fingers also came out as talons rather than freight grippers.

### Verdict

The direction is right and the frame vocabulary works. The set is **not** ready to propagate — fix
the per-unit head variation and the flesh drift first, then extend to the remaining frames.
