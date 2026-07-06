# Hellenic Bestiary — Canon Law, Wave 1 (Biped)

> Authored 2026-07-01. Photoreal Greek-mythology creature line — a new, dedicated LoRA/sprite line,
> separate from the pirate-raiders line. Source-grounded via a dedicated research pass (Hesiod, Homer,
> Aeschylus, Apollonius Rhodius, Apollodorus, Ovid, Pausanias, Diodorus Siculus, Euripides, and the
> corroborating vase-painting/sculptural record). Canon = training data for the subject LoRA: every
> detail concrete and depictable, every claim source-cited.
> **STATUS: APPROVED BY MIKE 2026-07-01 — 17-creature Wave-1 roster locked.**

## 0. Premise

The mission is mythological accuracy to primary classical sources, not the flattened, modern
fantasy-game version of these creatures. Every design decision in this document is traceable to a
cited primary source or a named, dated art-historical convention. Where "everybody knows" a creature
looks a certain way and that popular image contradicts the classical sources, **this document names
the popular misconception explicitly and locks the classical version as canon instead.** No
exceptions, no split-the-difference compromises.

This document is LAW. Every future generation prompt, every caption written for training data, every
character design decision for this pack traces back to an entry here. If a prompt or design choice
isn't justified by an entry below, it doesn't ship.

**Known corrections this canon makes against popular assumption (memorize these — they are the whole
point of the pack):**

- **Satyrs are horse-featured (horse ears, horse tail, human legs), not goat-legged.** The goat-legged
  satyr is a Hellenistic-era (post-323 BCE) innovation that later fused with Pan's iconography.
  Classical-period (5th–4th c. BCE) satyrs have human legs.
- **Pan alone is the goat-legged one** — goat horns, goat ears, goat hindquarters, goat tail, on a
  human torso. Don't transfer his goat legs onto satyrs, and don't strip them from him. (Pan himself
  is excluded from this wave's roster — see §1.)
- **Sirens have bird bodies, not fish tails.** The fish-tailed "Siren" is a medieval conflation of
  Sirens with mermaid/nymph imagery. Classical Sirens: bird body and legs, human female head
  (sometimes arms), wings.
- **Nereids are fully human women, not mermaids.** They ride dolphins/hippocamps and hold marine
  attributes; they do not have fish tails themselves. The fish/serpent tail in classical art belongs
  to male sea-daimones (Triton, Nereus), not to Nereids.
- **Medusa (and the Gorgons generally) have wings, bronze hands, boar tusks, and snake hair** in the
  earliest fully-described form (Aeschylus, Apollodorus, archaic vase/pediment art) — not the
  tusk-free, wingless "beautiful cursed woman" of the Ovidian/Renaissance/pop-culture tradition. The
  Ovid backstory (once-beautiful, cursed by Athena) is a Roman literary invention layered on top of an
  older monstrous image; this canon uses the monstrous archaic/classical form as the default visual.
- **The Erinyes (Furies) are wingless in their earliest full description** (Aeschylus, *Eumenides*) —
  black-robed, snake-haired, torch- and whip-bearing. Wings are a later (Euripidean/Roman/Virgilian)
  addition. This canon locks the earlier wingless form specifically to keep the Erinyes visually
  distinct from the winged Gorgons (see per-creature Forbidden lists).
- **Lamia is not a snake-woman.** The naga/serpent-tailed Lamia is a post-classical invention
  crystallized by Keats (1819) and cemented by fantasy games. The classical Lamia (Diodorus Siculus;
  Attic vase painting, e.g. the Beldam Painter lekythos) is a hairy, taloned, fanged humanoid woman —
  fully bipedal, no serpent lower body.
- **Talos is not a blocky faceless robot.** Classical vase painting (the Talos Painter krater, Ruvo,
  late 5th c. BCE) shows a handsome, anatomically normal young man rendered in bronze coloring —
  muscular, human-featured, upright. The lumbering-statue image is a modern film invention.
- **Argus Panoptes's eyes are scattered across his whole body** (torso and limbs, worn like a pattern
  over a bull hide), not clustered only on his face. The fixed "hundred eyes, face only" image is a
  flattened, incomplete read of a Roman (Ovidian) synthesis of an earlier, unstable Greek tradition
  (sources disagree from 3, to 4, to "all over the body," to Ovid's eventual 100).

---

## 1. Scope Rule (load-bearing — read before designing anything)

The studio's current mesh/render pipeline (TRELLIS.2 mesh generation → 8-direction Blender pre-render)
**only supports bipedal humanoid topology.** A creature is IN SCOPE for this wave if and only if the
source-attested classical form (or an explicitly chosen classical variant, see forks below) stands
upright on two human-proportioned legs with no more than the standard two arms and one head.

**Excluded from this wave — reserved for a future non-biped wave. Do not design, prompt, or caption
these as part of Hellenic Bestiary Wave 1:**

- **Harpies** (dominant classical form: full bird body, avian legs/talons, human head/arms grafted on
  — not a humanoid with attached wings)
- **Sirens** (bird body and bird legs; excluded outright, not force-fit as a hybrid — see Fork
  Decisions)
- **Gigantes, serpent-legged variant** (the Hellenistic/Pergamon anguipede form — snake-scaled legs
  from the waist down)
- **Hecatoncheires** (Cottus, Briareus, Gyges — one torso but 50 heads and 100 arms per individual;
  legs are biped-compatible but the head/arm topology is not)
- **Oceanus, serpent/fish-tailed variant** (the later vase-art convention; see Fork Decisions for the
  wave-1 humanoid alternative)
- **Pan** — the settled Classical type (goat horns, goat ears, goat hindquarters, cloven hooves) has
  digitigrade goat legs, not human legs. The studio's mesh pipeline hasn't been proven on hooved,
  digitigrade anatomy (same standard already applied to keep the Minotaur's legs fully human). Reserve
  Pan for the same future non-biped/hybrid-leg wave as the serpent-legged creatures above — do not
  soften his legs to human proportions to force him into this wave; that would itself be a
  non-classical invention.
- Centaurs, the Sphinx, Cerberus, the Chimera, Typhon, and any other quadruped, multi-bodied, or
  serpent-bodied creature — none of these were returned as biped-compatible by the research and none
  are to be improvised into this wave under any circumstance.

**Fork decisions locked for this wave** (creatures with two legitimate classical variants, one biped
and one not):

- **Gigantes → Archaic hoplite-giant variant ONLY** (fully human warrior giants, human legs,
  spear/shield or thrown boulders/tree trunks). The later Hellenistic serpent-legged form is excluded
  this wave per the rule above.
- **Oceanus → Hesiodic humanoid variant ONLY** (anthropomorphic Titan-god, no tail). The later
  vase-art fish/serpent-tailed convention is excluded this wave.
- **Sirens → excluded this wave entirely**, per the main exclusion list above. Do not attempt a "bird
  legs on a human torso" hybrid as a workaround; that is a studio invention, not a sourced variant.
  Revisit in the non-biped wave.

Any roster addition proposed after this document ships must pass the same test before it is designed:
does a cited primary classical source, or a named classical-art convention, put this creature on two
human-proportioned legs, one head, two arms? If the honest answer is "only if we invent a hybrid," it
is out of scope.

---

## 2. Art Direction — Locked Style Descriptor

This line is **photoreal**, full stop. It is explicitly NOT the studio's existing painterly house
style (that belongs to the pirate-raiders and fantasy-* lines). Register: gritty cinematic photoreal
creature realism — the look of a well-lit practical-effects creature suit or prosthetic makeup
photographed on a real set, not a polished game-engine render and not concept art. Skin, scale, hide,
and fur must read as physical material with pores, texture, sheen, and imperfection — not a smooth
digital sculpt.

**LOCKED STYLE DESCRIPTOR** (reusable prompt prefix — prepend to every generation in this line,
unmodified):

```
gritty cinematic photoreal creature, practical-effects creature-suit quality, real skin and material
texture with visible pores/scales/fur grain, naturalistic film lighting, physically-lit set
photography, subsurface scattering on skin, weathered and imperfect surfaces, shot on a real set —
NOT painterly, NOT anime, NOT a game-render, NOT a smooth digital sculpt, NOT concept art
```

This string is locked. Do not paraphrase it per-creature. Per-creature entries below add concrete
physical detail and props on top of this prefix; they never replace or soften it.

---

## 3. Roster — Wave 1 (Biped-Compatible, 17 creatures)

Each entry: identity, primary source, dense positive physical caption block, a unique identifying
token, and a Forbidden list. Captions are written positively (state what IS present) per the studio's
hard-won captioning lesson — vague or negated descriptions cause cross-creature feature bleed in
training.

### 3.1 Polyphemus (Cyclops)
**Role:** Solitary giant shepherd of the Cyclopes; pastoral, brutish, not martial.
**Source:** Homer, *Odyssey* Bk. 9; Hesiod, *Theogony* 139–146.
**Physical caption:** Massive inhuman giant CREATURE (Director-ratified 2026-07-02 — creature build,
NOT an oversized human man; supersedes the earlier human-build caption), one single large round eye
centered in its heavy scaled brow (no eye sockets on either side of the nose — only the one central
eye), NO engineered eyelid in source/structure images (Director-ruled 2026-07-02: the cyclops
concept-art tradition shows a bare round eye; a drawn-lid experiment produced a second hidden eye +
headwear artifacts. Homer *Od.* 9.389–390 does mention eyelids, but the visual canon wins — if the
photoreal pass adds a natural lid on its own, accept it, never force it), leathery scaled
reptilian-textured hide
in ochre and mustard-gold tones, pointed animal-like ears, heavy scaled brow ridge over the eye, a
wide mouth with lower fangs, thick bull neck and hunched mountainous shoulders, dressed in a rough
undyed hide wrap, bare clawed or heavy-nailed hands, standing among a pastoral sea-cliff cave-and-flock
setting, holding a tree-trunk-sized wooden club.
**Design lineage:** Homer, *Odyssey* 9.187–192 — "a monstrous wonder, not like a bread-eating man but
like a wooded peak of the high mountains"; creature read (Harryhausen lineage) ratified by the Director
as the truer rendering of the Homeric monster over the vase-painting big-human tradition — BUT the
film design's crown horn is REJECTED (Director, 2026-07-02): no horn appears in Homer or Hesiod; it is
a 1958 film invention, not classical canon.
**Unique token:** `one-eyed creature-giant shepherd` — the single central eye is the sole
identifying mark; no other creature in this roster has it.
**Forbidden:** No second eye anywhere on the face or body. No extra eyes scattered on the body (that
trait belongs only to Argus Panoptes). No wings. No tail. No horn — the crown horn is a 1958 Harryhausen
film invention, not in Homer/Hesiod (rejected 2026-07-02; horns in this roster belong to the Minotaur
alone). No fully-human face or human skin texture — he is a monster, not a big man (REVERSED 2026-07-02:
the old "no reptilian skin / oversized human man" rule steered generations into generic human barbarians
and is retired). No armor or metal weapons. No multiple Cyclopes fused into one body.

### 3.2 The Minotaur (Asterion)
**Role:** Bull-headed man imprisoned in the Labyrinth at Knossos.
**Source:** Apollodorus, *Bibliotheca* 3.1.4, Epitome 1.7–1.9; Ovid, *Metamorphoses* Bk. 8.
**Physical caption:** Muscular adult male human body, fully human torso/arms/legs/hands/feet, bull's
head and thick bull neck fused directly onto human shoulders, short dark bull fur on the head and neck
only, two curved bull horns, wet black bull nose, bovine eyes, standing upright on two human legs, nude
or wrapped only in a simple loincloth, positioned within rough-hewn stone labyrinth corridor walls,
sometimes gripping a broken chain or stone block.
**Unique token:** `bull-headed human body, human legs` — explicitly human from the neck down.
**Forbidden:** No bull legs or hooves — legs and feet are fully human. No wings. No cow tail hanging
from the human waist. No armor. No fur below the neckline. Do not render him digitigrade.

### 3.3 Gigas Warrior (Archaic Gigantomachy Giant — e.g. Alcyoneus/Porphyrion type)
**Role:** Earth-born giant warrior of the Gigantomachy, the war against the Olympian gods.
**Source:** Apollodorus, *Bibliotheca* 1.6.1–1.6.2 (narrative); Archaic/early-Classical vase painting
(7th–5th c. BCE) for the human-legged hoplite form (the variant locked for this wave — see §1).
**Physical caption:** Colossal overscaled human male warrior body, fully human legs and feet standing
on bare earth or broken stone, long wild hair and beard trailing past the shoulders, terrible-aspect
scowling face, heavily muscled human-proportioned torso and limbs at giant scale, bronze or leather
hoplite armor plates on torso and forearms, gripping an uprooted tree trunk or a massive jagged boulder
as a weapon, a round hoplite shield slung on one arm.
**Unique token:** `overscaled human hoplite giant with a torn-up tree trunk or boulder weapon`.
**Forbidden:** No serpent, snake, or scaled legs of any kind (the excluded anguipede variant). No
wings. No multiple heads or arms. Do not scale him identical to Polyphemus's pastoral-shepherd read —
Gigas Warrior is armored and martial, Polyphemus is unarmored and pastoral.

### 3.4 Cronus (Titan)
**Role:** King of the Titans before the Olympians; devourer of his own children.
**Source:** Hesiod, *Theogony*.
**Physical caption:** Mature, powerfully built adult male god, fully anthropomorphic human proportions
at heroic (not giant) scale, long dark or iron-grey beard and hair, severe commanding expression,
draped in a heavy dark robe or himation leaving one shoulder bare, gripping a curved sickle-shaped
harpe blade with a serrated inner edge, a broken bronze shackle on each wrist trailing short lengths
of shattered chain (Director-ratified 2026-07-02 — the "chained god-king" read: Hesiod, *Theogony*
717–735, Cronus bound in Tartarus after the Titanomachy; bound and unbowed, never decrepit), standing
on cold stone in twilight gloom at the threshold of Tartarus, ember-lit darkness, no armor.
**Unique token:** `bearded robed Titan-king gripping a curved harpe sickle, broken chains at his wrists`.
**Forbidden:** No giant/overscaled body — heroic human scale, not Gigas-Warrior giant scale. No wings,
no bull features, no animal hybridization. No skeletal/corpse-like "old god" rendering — virile and
powerful per the sources, not decrepit. No Chronos/Father-Time conflation (added 2026-07-02 after
reference-hunting showed nearly all modern "Cronus" art is actually the time god): no long-staffed
scythe (harpe sickle only), no hourglass, no clock or zodiac-wheel imagery, no feathered wings. No
lava/magma/stone-monster body (the "retold" videogame read) — he is a god in human form.

### 3.5 Atlas (Titan)
**Role:** Titan condemned to bear the weight of the celestial sky/heavens on his shoulders for
eternity.
**Source:** Hesiod, *Theogony*; Farnese Atlas (Roman marble copy of Hellenistic original) for the fixed
weight-bearing pose.
**Physical caption:** Powerfully muscled adult male body, fully human proportions and legs, bent-kneed
straining stance under an immense weight, both arms and upper back raised to support a massive stone
or star-mapped celestial globe/sphere resting across the shoulders and upper back, strained facial
expression, minimal drapery (a cloth wrap at the waist only), bare torso showing muscle strain,
standing at a rocky world's-edge setting.
**Unique token:** `straining bent-kneed pose bearing a celestial globe on the shoulders` — without the
globe he must not be used, since the pose is the entire point.
**Forbidden:** No wings. No armor. No weapon in hand (both arms are occupied bearing the globe). Do not
merge his globe with Argus's eye-covered hide or any other creature's prop.

### 3.6 The Gorgons (Medusa, Stheno, Euryale)
**Role:** Three monstrous winged sisters; Medusa alone is mortal and beheadable, her gaze turns
viewers to stone.
**Source:** Aeschylus, *Prometheus Bound* 798–799; Apollodorus, *Bibliotheca* 2.4.2; archaic vase and
pediment art (e.g. Corfu temple pediment, c. 580 BCE).
**Physical caption:** Human female torso, arms, and legs in an active running/kneeling lunge stance
(archaic Knielauf pose), head covered in a mass of living venomous snakes in place of hair, wide
grimacing face with a lolling tongue and two prominent boar-like tusks jutting from the lower jaw,
large feathered wings sprouting from the upper back, hands and forearms rendered as gleaming
bronze/brass metal rather than flesh, a thick belt at the waist tooled with snake-scale relief
(Director-ruled 2026-07-02: the classical "girdle of snakes" renders as SOLID belt geometry with snake
tooling, never a free-wrapping live snake — thin wrapped geometry is unmeshable in the 3D pre-render
pipeline and shreds in TRELLIS), scaled dragon-like texture patches on the brow.
**Unique token:** `bronze-handed, boar-tusked, snake-haired winged woman in a running lunge` — the
bronze hands + boar tusks together are the Gorgon-specific marks that must not appear on the Erinyes.
**Forbidden:** No fish tail, no scaled serpent lower body — legs are human and bare, in the archaic
running stance. No beautiful/unblemished "cursed woman" face (the Ovidian romantic Medusa). No black
robes (Erinyes). No torches or whips (Erinyes). No bird legs or talons (Harpy/Siren — out of scope
anyway, but the traits must not bleed in).

### 3.7 The Erinyes (Furies: Alecto, Megaera, Tisiphone)
**Role:** Chthonic female spirits of vengeance and retribution, especially for kin-murder.
**Source:** Aeschylus, *Eumenides* (earliest full physical description, locked as canon) — "wingless
in appearance, black, altogether disgusting."
**Physical caption:** Human female body draped head-to-foot in heavy black robes/garments stained dark
with blood at the hem and sleeves, grim disgusted expression, hateful dripping dark tears at the eyes,
live snakes twined visibly through the hair (hair is present, snakes are woven through/around it),
gripping a lit torch in one hand and a knotted scourge/whip in the other, bare feet or simple hunting
sandals beneath the robe, no wings.
**Unique token:** `wingless black-robed torch-and-whip bearer with snakes twined in the hair` —
explicitly wingless and robed, separating her at a glance from the winged, bronze-handed, tusked,
running-stance Gorgons.
**Forbidden:** No wings under any circumstance (load-bearing distinction from the Gorgons). No bronze
hands. No boar tusks. No running/lunging bare-legged stance — upright and robed. No beautiful-maiden
face — grim and disgusting per Aeschylus.

### 3.8 The Keres
**Role:** Battlefield death-spirits who swarm dying and dead warriors, fighting over the bodies like
vultures.
**Source:** Hesiod, *Shield of Heracles* ~248–257.
**Physical caption:** Dusky dark-toned human female body, mouth open showing gnashing white fangs,
hands rendered as large sharp grasping claws/talons (not human fingernails), garments and bare skin
soaked and smeared in fresh blood, grim lowering scowl, hunched aggressive scavenging posture low over
a battlefield corpse, no wings (unconfirmed in primary text — omit rather than assume).
**Unique token:** `dusky blood-drenched battlefield scavenger with fanged mouth and taloned hands,
wingless` — fangs AND clawed hands together, on a wingless body, is unique to the Keres in this roster.
**Forbidden:** No wings (unattested — do not import Valkyrie-style wings or a "solemn psychopomp"
aesthetic). No snake hair (Gorgon/Erinyes trait). No robes — battlefield-grimy, not formally dressed.
No beautiful/serene "angel of death" framing.

### 3.9 Empousa
**Role:** Shapeshifting demonic servant of Hecate; preys on travelers, often by posing as a beautiful
woman.
**Source:** Aristophanes, *Frogs* ~285–295.
**Physical caption:** Human female body and face of striking beauty in her default deceptive form, face
and eyes glowing with an inner fire-light, but with one leg made of gleaming bronze/copper metal and
the other leg ending in a shaggy donkey's leg and hoof (the two legs are visibly mismatched in material
and shape — this is her single defining trait), standing upright on both mismatched legs, otherwise
dressed as an alluring traveler or wayside woman.
**Unique token:** `one bronze leg, one donkey leg, fire-glowing eyes` — the asymmetric leg pair is
non-negotiable and must always be visible/legible in every rendered angle.
**Forbidden:** No matching human legs. No wings. No snake hair. No serpent lower body (would collapse
her into the excluded Lamia-as-naga misconception).

### 3.10 Lamia
**Role:** Child-devouring former queen, transformed into a monstrous figure by grief and curse.
**Source:** Diodorus Siculus (earliest extended literary account); Attic vase painting, e.g. the
Beldam Painter lekythos, c. 500 BCE (hairy, taloned, fanged humanoid).
**Physical caption:** Human female body and legs, fully bipedal, gaunt grief-worn face, coarse dense
body hair covering the limbs and torso in patches, large taloned claw-like hands and feet in place of
ordinary human fingers and toes, prominent sharp fangs visible in an open snarling mouth, hunched
predatory posture, minimal ragged clothing.
**Unique token:** `hairy taloned fanged humanoid woman, fully human legs, no serpent tail` — the
explicit absence of a serpent lower body is itself the load-bearing distinguishing trait.
**Forbidden:** ABSOLUTE — no snake/serpent tail, no naga lower body, no scaled skin. No wings. No
bronze hands (Gorgon trait). No mismatched legs (Empousa trait).

### 3.11 Argus Panoptes
**Role:** Hundred-eyed giant herdsman set by Hera to guard Io; all-seeing watchman.
**Source:** Apollodorus, *Bibliotheca* 2.1.3 ("eyes all over his body"); Ovid, *Metamorphoses*
1.625–723 (fixes the hundred-eye count, latest layer of the tradition).
**Physical caption:** Powerfully built giant human male body, numerous distinct open eyes distributed
across the torso, shoulders, upper arms, and thighs (not clustered on the face — the face has only the
normal two eyes), wearing a rough-cured bull hide as a garment/cloak draped over the shoulder and torso
so the eye-covered skin shows through and around it, thick beard, herdsman's staff in hand, standing in
a pastoral field setting.
**Unique token:** `eyes scattered across torso and limbs under a draped bull hide, ordinary face` — the
face is unremarkable; the body is the eye-covered surface.
**Forbidden:** No extra eyes on the face itself beyond the normal two. No wings. No peacock feathers or
peacock-tail imagery (a separate, later scene, not his own living design). No reptilian or insectoid
body.

### 3.12 Talos
**Role:** Bronze automaton giant, guardian who circled the island of Crete three times daily hurling
boulders at approaching ships.
**Source:** Apollonius Rhodius, *Argonautica* Bk. 4; Talos Painter volute-krater (Ruvo, late 5th c.
BCE, Museo Jatta).
**Physical caption:** Handsome, anatomically normal, athletically muscular young adult male body
rendered entirely in gleaming bronze-metal skin tone and sheen (smooth warm bronze coloring over
completely normal human anatomy and facial features — not blocky, not mechanical-looking, not
faceless), a single fine vein or seam line visible running from the base of the neck down to one ankle,
a small bronze nail or pin visible at that ankle, standing in an active throwing or striding stance,
nude or minimally draped to keep the bronze skin and ankle-vein detail visible.
**Unique token:** `bronze-skinned handsome young man with a neck-to-ankle vein line and ankle nail`.
**Forbidden:** No blocky, geometric, faceless, or robotic head/body. No wings (the winged Talos is a
minority Phaistos-coin numismatic variant, not used here). No visible mechanical joints, rivets, or
plating — the bronze is skin-like and smooth, not armor-like.

### 3.13 Satyr
**Role:** Wild woodland reveler in the retinue of Dionysus; earthy, lustful, mischievous, not martial
or monstrous.
**Source:** Hesiod, *Catalogue of Women* fr. 10a; Homeric Hymns; Aeschylus/Sophocles satyr plays;
Euripides' *Cyclops* (only complete surviving satyr play); Attic vase painting, Archaic–Classical
(6th–4th c. BCE).
**Physical caption:** Adult male human body with fully human legs and feet standing upright, pointed
horse-like ears set high on the head, a long horse tail extending from the lower back/tailbone, snub
broad nose, bearded or stubbled weathered face, often partially balding, lean-to-stocky build,
bare-chested or draped loosely in an animal skin or short chiton, alert reveling posture, carrying a
wineskin or a two-handled kantharos wine cup, sometimes gripping a leafy thyrsus staff.
**Unique token:** `horse-eared, horse-tailed woodland reveler with fully human legs` — the horse
features (not goat) are the load-bearing correction this canon makes.
**Forbidden:** No goat horns, no goat legs, no cloven hooves, no goat tail — that vocabulary belongs to
Pan alone, and Pan is excluded from this wave. No wings. No snake hair. Never render him as the
Hellenistic/Roman goat-man Faun type.

### 3.14 Silenus
**Role:** Eldest and wisest of the satyrs; a perpetually drunk, good-humored tutor and companion of the
young Dionysus.
**Source:** Euripides' *Cyclops*; Ovid's Midas episode, *Metamorphoses* Bk. 11.
**Physical caption:** Older adult male human body, fully human legs and feet, noticeably fat rounded
belly, balding pate with a fringe of unkempt grey-white hair, thick unkempt beard, sagging weathered
skin, the same pointed horse ears and horse tail as the generic satyr type, usually shown reclining,
slumped, or being supported in a state of drunkenness, holding or having dropped a wine cup or
wineskin, minimal or falling-open drapery.
**Unique token:** `elderly fat balding horse-eared satyr, perpetually drunk` — age, girth, and baldness
separate him from a generic young satyr in the same roster.
**Forbidden:** No goat features. No youthful lean build. No wings. No weapon of any kind — never
martial.

### 3.15 Dryad
**Role:** Tree-nymph whose life is inseparably bound to a single specific tree.
**Source:** Homeric Hymn to Aphrodite (5); general nymph tradition, Classical Attic vase painting.
**Physical caption:** Fully human adult female body and legs, standing upright, skin and hair rendered
with subtle bark-textured or leaf-toned coloring and grain worked into otherwise natural human skin
(not scaled or reptilian — a wood-grain naturalistic texture only), often shown emerging from or
standing directly against the trunk of a great oak tree, draped in simple leaf-and-vine wrapped
garments or a plain light chiton, bare feet rooted at the base of the tree.
**Unique token:** `bark-grain-skinned nymph emerging from a tree trunk`.
**Forbidden:** No wings, no animal features of any kind. No fish/marine attributes (Nereid trait) — a
Dryad is never shown near water or with sea-creatures. No visible roots replacing legs — legs are
fully human, standing at the tree's base, not merging into it.

### 3.16 Nereid
**Role:** One of the fifty sea-nymph daughters of Nereus and Doris; benevolent marine spirit attending
Poseidon and Thetis.
**Source:** Hesiod, *Theogony* 240–264 (genealogy/catalogue); Apollodorus' *Bibliotheca* (catalogue);
Classical Attic vase painting (procession scenes, e.g. Thetis's wedding).
**Physical caption:** Fully human adult female body and legs, fair-haired, youthful and lovely per the
sources, seated or reclining upon the back of a dolphin or hippocamp (sea-horse creature) as a
mount/attribute rather than possessing any fish anatomy herself, wearing a light diaphanous chiton and
a headscarf (sakkos), holding a fish, shell, or length of drifting sea-fabric, sea-foam and wave motifs
in the immediate setting.
**Unique token:** `fully human sea-nymph riding a dolphin, no fish tail of her own` — the explicit
absence of a fish tail on her own body is the load-bearing correction against the popular mermaid
image.
**Forbidden:** ABSOLUTE — no fish tail, no scaled lower body, no mermaid anatomy of any kind on the
Nereid herself; that trait belongs only to separate male sea-daimones (Triton, Nereus), not part of
this roster. No bark/leaf texture (Dryad trait). No wings.

### 3.17 Maenad
**Role:** Human woman seized by ecstatic Dionysiac frenzy (*mania*); a devoted, divinely-possessed
follower of Dionysus, not a monster.
**Source:** Euripides' *Bacchae*; Attic red-figure vase painting, 5th c. BCE.
**Physical caption:** Fully human adult female body, wild unbound flowing hair, ecstatic ranging
expression caught mid-frenzy or mid-dance, draped in a fawn-skin or panther-skin (*nebris*) worn slung
over one shoulder across ordinary drapery, a live snake held aloft in one hand or worn coiled as a
headband/belt, gripping a thyrsus (a fennel stalk staff tipped with ivy leaves and a pinecone) in the
other hand, ivy wreath in the hair, bare feet, dynamic dancing or striding pose.
**Unique token:** `ecstatic bare-footed reveler in fawn-skin with a live snake and a thyrsus` — the
thyrsus + live snake + fawn-skin combination together mark her; no other creature in this roster
carries a thyrsus.
**Forbidden:** No animal hybridization or monstrous features of any kind — entirely human, only
expression and posture read as frenzied. No over-sexualized or feral/predatory framing — Euripides
presents maenads as women in genuine divine possession, not monsters. No wings, no fangs, no talons.

---

## 4. Global Must-Not List (applies to every creature in this roster, no exceptions)

1. **No non-biped anatomy this wave.** No serpent lower bodies, no quadruped stances, no bird legs, no
   digitigrade/hooved legs (Pan is excluded, not softened), no multi-body fusions, no extra heads or
   arms beyond what an entry explicitly specifies (Argus's extra eyes are a skin/texture trait, not
   extra limbs — he still has exactly two arms and one head).
2. **No painterly, anime, or stylized game-render finish.** Every image in this line uses the locked
   photoreal style descriptor (§2) unmodified. No cel-shading, no line art, no soft painterly
   brushwork, no chibi/anime proportions.
3. **No mermaid-tailed Sirens, no naga-tailed Lamia, no goat-legged satyrs, no fish-tailed Nereids** —
   these are the specific medieval/modern conflations the source research flagged, and they are
   permanently barred from this canon, not just "avoided by default."
4. **No modern fantasy-generic monster tropes not attested in a cited source** — no glowing tribal
   tattoos, no generic "demon" horns/wings vocabulary swapped between creatures, no video-game
   ability-icon readability requirements overriding source accuracy.
5. **No cross-creature trait bleed.** Each entry's unique token (bolded per-creature above) exists
   specifically to prevent the LoRA from blurring visually similar creatures together (Gorgons vs.
   Erinyes; Empousa vs. Lamia; Polyphemus vs. Argus; Satyr vs. Silenus). When captioning training data
   or writing generation prompts, always include the unique token string.
6. **No backstory-driven softening of monstrous forms.** Where a source gives two variants — an
   earlier monstrous form and a later humanized/sympathetic form (e.g., Ovid's "once-beautiful,
   cursed" Medusa) — this canon defaults to the earlier, fuller, more monstrous classical-art form
   unless a specific entry above states otherwise. Sympathy is not a design input; source density is.
7. **No modern armor, firearms, or anachronistic materials.** Bronze, iron, wood, hide, wool, and stone
   only. No steel plate armor, no visible chainmail unless a cited source specifies it (none do in
   this roster), no gunpowder-era or later technology.
8. **No excluded creatures smuggled in under a different name.** Harpies, Sirens, serpent-legged
   Gigantes, Hecatoncheires, serpent-tailed Oceanus, and Pan are not to be reintroduced via reskins,
   "inspired by," or hybrid designs in this wave. They wait for the non-biped wave named in §1.
9. **Every generation prompt for this line must open with the exact locked style descriptor string
   from §2**, followed by the relevant creature's physical caption block and unique token. Deviation
   from the locked descriptor invalidates the output for this line.

---

## Roster summary

**17 creatures shipped this wave:** Polyphemus, the Minotaur, Gigas Warrior, Cronus, Atlas, the
Gorgons, the Erinyes, the Keres, Empousa, Lamia, Argus Panoptes, Talos, Satyr, Silenus, Dryad, Nereid,
Maenad.

**7 creatures/variants explicitly excluded**, reserved for a future non-biped wave: Harpies, Sirens,
serpent-legged Gigantes, Hecatoncheires, serpent-tailed Oceanus, Pan, plus the standing bar on
centaurs/Sphinx/Cerberus/Chimera/Typhon and any other quadruped or multi-bodied creature.

## Cross-refs
[[pirate3d-lora-state]] (the prior photoreal LoRA lineage this line follows) · study-swarm dataset spec
(5–8 images/creature floor, rank 32, HiDream-O1-Image base recommendation, single-pipeline generation)
· `sprite-mesh-from-front-pipeline` / `3d-prerender/README.md` (the downstream mesh/retexture/render
pipeline this roster's scope rule is bound to).
