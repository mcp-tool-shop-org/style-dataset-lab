# Review Rubric

## Quick Decision Tree

1. Does the image pass the **style test**? (Would it look at home next to approved assets?)
   - No → REJECT with cited rule violations
2. Does it pass **all constitution rules** at ≥0.6 score?
   - No → Check if fixable with img2img → BORDERLINE or REJECT
3. Does it add **new signal** the dataset doesn't have?
   - Yes → APPROVE
   - No (duplicate composition/subject) → REJECT as redundant

## Approval Criteria

- All scoring dimensions ≥ 0.6
- No critical rule violations
- Adds value to the dataset (new subject, angle, or variation)

## Rejection Criteria

- Any scoring dimension < 0.4
- Violates a core constitution rule
- Too similar to existing approved assets
- Generic/stock-art quality (no distinctive style)

## Borderline Criteria

- One or two dimensions between 0.4–0.6
- Fixable with img2img post-processing
- Strong composition but weak on style details
