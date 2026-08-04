# Shipbuilding traditions

Defined **once, for every hull in the fleet.** A ship's own canon entry declares which
tradition built her. It does not redefine them.

## Why this field exists

The fleet used to carry `era` — `"1500s"`, `"1700s"` and so on. That field was doing real
work: it explained *why these hulls look different from each other*, which is the thing a
player has to be able to read at sprite size. But it made a claim about a real historical
timeline, and the fleet as assembled spans two centuries. A caravel and a frigate cannot
both be current in the same year. Either three quarters of the fleet is anachronistic or
the world is not tied to a date.

The world is not tied to a date. So `era` is replaced by `tradition`: the same job, done by
an axis that belongs to this world rather than to ours.

**The anatomy stays real.** Every rig plan still traces to a documented vessel, and it must —
that grounding is why the anatomy is trainable at all. A lateen yard sits where lateen
yards sit. What is invented is the context: who builds them, what they are for, what they
mean. Invent the flag, not the ship.

## The reference period is art direction, not lore

Each hull keeps its old period string as `visual.reference_period`, and it is used in
exactly one place: the generation prompt. The image model knows what "a 1600s sailing
vessel" looks like and does not know what a Cold Coast vessel looks like, so the prompt
speaks the model's language while canon speaks the world's.

`reference_period` is **never** a statement about when the game is set, and nothing in the
game should surface it. If it ever needs to appear in player-facing text, it is the wrong
field.

## The five traditions

Working names. **These are placeholders for the Director to rename** — the structure is the
canon claim, the labels are not.

| Tradition | Builds | Reads at sprite size |
|---|---|---|
| `cold-coast` | Deep-hold cargo carriers. Fat, slow, enormously profitable. | Rounded pear hulls, narrow decks, high sterns, castles |
| `sunward-sea` | Fast raiders and scouts for shallow, island water. | Low and sharp, overhanging ends, lateen triangles, oars |
| `crown-naval` | State warships and prestige flagships. | Tall square rig, gun decks, heavy ornament, gilded sterns |
| `longshore` | Working craft — coastal trade, fishing, courier runs. | Small, fore-and-aft, few masts, no ornament |
| `far-trade` | Foreign merchants from beyond the charted water. | Battened lugsails, slab sterns, no bowsprit |

## The rules that bind every hull

1. **Tradition explains silhouette, not quality.** A `longshore` sloop is not a worse ship
   than a `crown-naval` frigate; it is built for a different job. Nothing in this axis
   ranks hulls.

2. **A tradition is a family, not a uniform.** Hulls within one tradition share a
   construction logic and read as related at a glance. They are not required to share a
   palette, and they must remain individually distinguishable — the fleet's whole value is
   that no two hulls are confusable.

3. **Anatomy is never invented to fit a tradition.** If a hull's rig plan cannot be traced
   to a real vessel, it does not go in the fleet. A tradition may explain *why* a builder
   favours lateens; it may not produce a rig that no one ever sailed.

4. **`far-trade` is currently unpopulated.** Defined ahead of its first hull, deliberately:
   it reserves the space for a vessel built on none of the other four logics, and gives the
   world an outside. It stays empty until a hull earns it — the junk is the intended first,
   and until then this row is a promise, not a claim.

## Patina

Orthogonal to both tradition and damage. A vessel is described by **(class, patina, damage
tier)**, and all three vary independently.

| Patina | Means |
|---|---|
| `new` | Fresh from the yard or lately refitted. Bright paint, unbleached canvas. |
| `seasoned` | In steady service and well kept. The working default. |
| `weathered` | Long in service and still sound. Sun-bleached canvas, greyed planking, paint worn thin at the wear points. |
| `ancient` | An old ship kept alive past her time. Visibly of an older fashion. |

**Patina is not damage.** This is the distinction the axis exists to protect. Damage says
*this ship just had a bad day*; patina says *this ship has a history*. A `weathered` hull at
`01-pristine` is a veteran in good order — nothing is broken, nothing needs repair, and she
has plainly been somewhere. That combination is not reachable on the damage ladder alone,
which is why folding age into `01-pristine` was rejected.

Three consequences that bind:

1. **Patina never implies structural loss.** No missing spars, no holed canvas, no breached
   planking. Those are damage tiers and they are counted separately.

2. **Patina does not alter severity.** `03-moderate` means the same amount of trouble on an
   `ancient` carrack as on a `new` frigate. If age made damage read worse, the ladder would
   stop being comparable across the fleet — see rule 4 in `damage-tiers.md`.

3. **Patina is applied at generation time, never baked into a mesh.** A mesh takes its
   texture from its plate; weather the plate and every instance of that hull is weathered
   forever, which costs the well-kept flagship and the newly-launched trader for no saving.
   The pristine mesh stays neutral and patina is a treatment over it.

A hull's `patina` field is its **default** — what she usually looks like — not a constraint.
Any hull can be rendered at any patina.

## Allegiance

`faction_of_origin` stays reserved for named powers, houses and companies, and stays
`unassigned` until those exist. Tradition answers *what yard-logic built her*; faction will
answer *whose flag she flies*. They are different questions and a hull will eventually carry
both — a `cold-coast` fluyt can fly any colours, and a captured one flies the wrong ones.

## Pirates

Not a tradition and not a hull class. Historically pirates sailed captured vessels — sloops,
schooners, brigantines, the occasional taken merchantman — altered after the fact: bulwarks
cut down, mismatched guns added, canvas patched, name painted over.

So `pirate` is a **treatment applied over an existing hull**, in the same family as patina,
and it yields a pirate version of the whole fleet rather than one pirate ship. A named hero
vessel with a silhouette players learn to recognise is the exception and earns her own canon
entry.
