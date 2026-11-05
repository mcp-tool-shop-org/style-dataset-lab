# Portlight Ships — Review Rubric

Reviewers (`human:director` or an Apache-2.0 VLM judge distinct from the generator model) score each candidate across the 10 constitution dimensions (`silhouette`, `scale_cues`, `surface_detail`, `propulsion_clarity`, `functional_design`, `material_contrast`, `palette`, `weathering`, `composition`, `structural_logic`).

## Thresholds

- **Approved (`>= 0.70`)**: Eligible for canon binding and CC-BY-4.0 dataset snapshots when all provenance links pass `sdlab verify`.
- **Borderline (`0.50 – 0.69`)**: Hold for targeted refinement brief; do not bind into training snapshots.
- **Rejected (`< 0.50` or any critical failure mode)**: Exclude with tagged failure mode (`generic_silhouette`, `scale_ambiguity`, `greeble_spam`, `unclear_propulsion`, `form_without_function`, `uniform_material`, `palette_violation`, `uniform_weathering`, `cropped_subject`, `floating_parts`).
