# Damage tiers

Defined **once, for every hull in the fleet.** A ship's own canon entry declares which
tiers it supports and what rig variants each tier produces — it does not redefine them,
and it does not script them.

## Why these are definitions and not scripts

An earlier draft of this canon named, per hull, exactly which mast broke at which tier and
which sails were lost. That was hand-authoring the judgement the anatomy training exists to
produce. A model that has learned a xebec's three enormous lateen yards from pristine
turnarounds should be able to work out how they come down — and if it can't, we need to
know that, which we never will if the answer is scripted.

So these tiers say **how bad**, not **what specifically**. Which spar goes is the model's
call, made from anatomy, and ours to curate.

## The five tiers

| Tier | Severity | Can she sail? |
|---|---|---|
| `01-pristine` | Flawless. Nothing to remark on. | Yes |
| `02-light` | Working wear. Patched canvas, staining, a rope adrift. Nothing structural. | Yes |
| `03-moderate` | Fought and survived. Holed canvas, scorched and splintered planking, a broken spar. **All masts still standing.** | Yes, poorly |
| `04-heavy` | Crippled. **At least one mast is down.** Canvas mostly destroyed. Hull breached. Still afloat. | **No** |
| `05-destroyed` | A burnt-out derelict. **Strictly more mast loss than 04.** Canvas gone but for rags. Hull holed through, timbers charred. | No |

## The rules that bind every hull

1. **Damage never runs backwards.** Anything broken at a tier is still broken at every
   later tier. The failed 2026-07-25 run had a mast snapped at `04-heavy` and standing
   again at `05-destroyed`; that is the specific defect this rule exists to prevent.

2. **`03` is the last tier with every mast standing.** The line between "damaged" and
   "crippled" is structural, not cosmetic. Below `04` the damage is to surfaces; at `04`
   and beyond it is to the ship.

3. **`04` and `05` offer no furled variant.** Not an arbitrary omission — you cannot stow
   canvas that has been destroyed. Any hull declaring `sails-closed` at those tiers is
   wrong.

4. **Severity is comparable across hulls.** `04-heavy` on a sloop and `04-heavy` on a
   galleon should read as the same amount of trouble, not the same number of broken spars.
   A sloop has one mast; losing its topmast is proportionally what losing a foremast is to
   a galleon.

5. **The hull stays recognisable through `05`.** A wrecked galleon must still read as
   *that* galleon — its stern gallery, its figurehead, its proportions. Damage removes
   things; it does not replace the ship with a generic wreck.

## What a hull entry may add

Only a `hull_note`, and only where a tier genuinely departs from the above — a
single-masted vessel being the obvious case, since "a mast is down" means something
different when there is only one. It is not a place to re-script the damage.
