# Asset lane — pre-registered consistency experiment

**Status: PRE-REGISTERED, NEVER RUN.** Registered 2026-08-04, in the skeleton session,
before any training data volume, any trained LoRA, or any result exists. Standards
compliance for the lane is scored in [asset-lane-design.md](asset-lane-design.md);
this document is the EXTERNAL_VERIFIER of the lane's eventual first claim — a
measurement specified before the artifact it judges.

## Baseline (recorded before anything can be tuned toward it)

Co-visible twin disagreement, per-view diffusion without an asset-trained LoRA:

- **ΔE mean 17.97 / median 17.56** — two twins disagreeing about one bald scalp,
  the "owner seam" defect class (facet E04 Ruling 1).
- Source of record: `E:/AI/facet/docs/experiments/E04-task4d-report.md`, measured by
  `e04_seam_sources.py`. The instrument, not this document, defines the measurement.

## Hypothesis (scoped by Phase 0, Q2 — see the design doc's research grounding)

A LoRA fine-tuned on provenance-gated, asset-derived turnaround render sets reduces
co-visible ΔE between independently generated views of a **new, near-canon subject**,
relative to the identical generation pipeline without that LoRA.

**Scope honesty, stated up front:** the literature (SyncDreamer's ablation; Zero-1-to-3
at 800K objects; Wonder3D at ~30K) says cross-view consistency machinery comes from
cross-view attention at dataset scales three to four orders of magnitude above ours. A
per-view LoRA cannot install that machinery. The claim under test is **appearance
lock + view-token vocabulary** (Kumari et al. 2024; Cheng et al. 2024): the LoRA makes
independently sampled views agree more because each view is pulled toward the same
learned appearance — for subjects near the training distribution, evaluated near
trained poses. This experiment does NOT test, and its success would NOT establish,
generalized view consistency.

## Method (frozen now)

1. Train the asset LoRA on the lane's provenance-gated packages (multi-asset style
   pool per Q3 — never a single asset), captions carrying facing tokens + domain tag.
2. Pick a new subject inside the trained style (not any training asset).
3. Generate twin view pairs with the SAME pipeline, seeds policy, and prompts,
   with and without the asset LoRA — the only variable is the LoRA.
4. Measure co-visible ΔE with facet's E04 instrument, unchanged.
5. Compare against the 17.97 / 17.56 baseline AND against the no-LoRA arm run in
   the same session (the live control matters more than the historical number).

## Falsifiable prediction

- **Support:** with-LoRA co-visible ΔE (median) is lower than the same-session
  no-LoRA arm's, on the majority of view pairs.
- **Falsified:** ΔE is not reduced, or worsens. That outcome kills the flywheel
  premise at its first link — the lane remains a packaging/provenance surface, and
  the consistency story is dropped, not re-argued.

## Preconditions before anyone runs this

Dataset volume per the Q3 composition rules (a multi-subject style pool, not one
warrior) · a watchdog-disciplined training session (its own session, GPU protected) ·
the Director's go. None of these existed in the skeleton session, which is why this
file exists and no result does.
