/**
 * judgment-provenance.js — tell a judgment somebody MADE from one a script MINTED.
 *
 * Law 2 of this product is "inclusion is explainable": every record carries a
 * reason it was included or excluded. That law is only worth anything if the
 * reason describes the actual image.
 *
 * It currently doesn't, at scale. Measured on `projects/star-freight`
 * (1,182 records) on 2026-08-04:
 *
 *   reviewer          records   distinct explanations   max reuse
 *   bulk_curate_v2        566   ) 82 across both              x144
 *   bulk_curate_v1        322   )
 *   wave25-script          60     8                            x32
 *   human:mike            110   110                             x1
 *   (no judgment)         124     —                              —
 *
 * 948 of 1,182 records — 80% — carry a rationale that was selected by matching
 * the record id against a prefix regex, not by looking at the image. One string
 * ("On-style gritty space costume. Faction-appropriate material vocabulary and
 * wear level…") appears verbatim on 144 different images. The three scripts
 * that wrote them (`bulk-curate-wave2-5.js`, `bulk-curate-waves11-18.js`,
 * `curate-wave25.js`) were deleted in this repo's Stage A health pass for
 * exactly this reason — but deleting the tool did not retract its output, and
 * that output still flows into eligibility, snapshots, splits, exports and
 * training packages.
 *
 * The `human:mike` row is the control that makes this a finding rather than a
 * guess: 110 records, 110 distinct explanations, nothing reused. Genuine
 * curation in this corpus looks like one rationale per image.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * THIS MODULE READS. IT NEVER WRITES.
 *
 * The Director's ruling (2026-08-04) was "mark, don't touch": make the
 * distinction visible everywhere it matters, and leave the records alone. So
 * there is no migration here, no backfilled flag, no rewritten judgment. The
 * signal is derived at read time from data already on disk, which also means
 * it cannot drift out of sync with the records and needs no re-run when they
 * change.
 * ─────────────────────────────────────────────────────────────────────────
 */

/**
 * Reviewer ids known to have been written by a bulk script rather than a
 * person. Matched against `judgment.reviewer`.
 *
 * Deliberately a conservative allowlist of OBSERVED offenders, not a clever
 * heuristic like /script|bot|auto/. A false positive here defames a real
 * human judgment, which is worse than missing one: the corpus-level reuse
 * statistic below catches anything this list doesn't, without needing to
 * guess from a name.
 */
export const SCRIPT_REVIEWER_PATTERNS = Object.freeze([
  /^bulk_curate(_v\d+)?$/i,
  /^wave\d+-script$/i,
]);

/** A judgment is machine-minted, human-made, or absent. */
export const JUDGMENT_ORIGIN = Object.freeze({
  HUMAN: 'human',
  SCRIPT: 'script',
  UNKNOWN: 'unknown',
  NONE: 'none',
});

/**
 * Classify a single record's judgment origin from its reviewer id.
 *
 * @param {object} record
 * @returns {'human'|'script'|'unknown'|'none'}
 */
export function classifyJudgmentOrigin(record) {
  const judgment = record?.judgment;
  if (!judgment || typeof judgment !== 'object') return JUDGMENT_ORIGIN.NONE;

  const reviewer = judgment.reviewer;
  if (typeof reviewer !== 'string' || reviewer.trim() === '') {
    return JUDGMENT_ORIGIN.UNKNOWN;
  }
  if (SCRIPT_REVIEWER_PATTERNS.some((re) => re.test(reviewer))) {
    return JUDGMENT_ORIGIN.SCRIPT;
  }
  // `human:<name>` is this corpus's convention for a person.
  if (/^human(:|$)/i.test(reviewer)) return JUDGMENT_ORIGIN.HUMAN;

  // A reviewer id we don't recognise. NOT assumed human — that assumption is
  // how 948 fabricated rationales passed as curation for months.
  return JUDGMENT_ORIGIN.UNKNOWN;
}

/**
 * Corpus-level rationale-reuse audit.
 *
 * This is the evidence the reviewer-name check cannot give you, and it is the
 * part that generalises: a rationale reused verbatim across many images did
 * not describe any one of them, whoever or whatever wrote it. It catches a
 * future bulk script under a reviewer id nobody has added to the list above.
 *
 * `reuseThreshold` is the count at which sharing stops being coincidence.
 * Two records can legitimately share a terse reason ("out of focus"); 144
 * cannot.
 *
 * @param {object[]} records
 * @param {{reuseThreshold?: number}} [opts]
 */
export function auditJudgmentProvenance(records, opts = {}) {
  const reuseThreshold = opts.reuseThreshold ?? 3;

  const byOrigin = { human: 0, script: 0, unknown: 0, none: 0 };
  const byReviewer = new Map();
  const byExplanation = new Map();

  for (const record of records) {
    const origin = classifyJudgmentOrigin(record);
    byOrigin[origin]++;

    const judgment = record?.judgment;
    if (!judgment) continue;

    const reviewer = typeof judgment.reviewer === 'string' ? judgment.reviewer : '(unset)';
    byReviewer.set(reviewer, (byReviewer.get(reviewer) ?? 0) + 1);

    const explanation = judgment.explanation;
    if (typeof explanation === 'string' && explanation.trim() !== '') {
      const key = explanation.trim();
      if (!byExplanation.has(key)) byExplanation.set(key, []);
      byExplanation.get(key).push(record.id);
    }
  }

  const reused = [...byExplanation.entries()]
    .filter(([, ids]) => ids.length >= reuseThreshold)
    .map(([explanation, ids]) => ({
      explanation,
      count: ids.length,
      sample_record_ids: ids.slice(0, 5),
    }))
    .sort((a, b) => b.count - a.count);

  const judgedCount = byOrigin.human + byOrigin.script + byOrigin.unknown;
  const reusedRecordCount = reused.reduce((sum, r) => sum + r.count, 0);

  return {
    total_records: records.length,
    judged: judgedCount,
    by_origin: byOrigin,
    by_reviewer: Object.fromEntries([...byReviewer.entries()].sort((a, b) => b[1] - a[1])),
    // How many judged records carry a rationale that is not unique to them.
    // This is the honest headline number — it does not depend on recognising
    // a reviewer id.
    reused_rationale_records: reusedRecordCount,
    reused_rationale_ratio: judgedCount > 0 ? reusedRecordCount / judgedCount : 0,
    reuse_threshold: reuseThreshold,
    // Worst offenders first, capped — this is for an operator to read, not a
    // full dump of a 1,182-record corpus.
    top_reused: reused.slice(0, 10),
    // True when any judged record's rationale is shared at or above the
    // threshold. Consumers gate their wording on this rather than re-deriving.
    has_reused_rationales: reusedRecordCount > 0,
  };
}

/**
 * One-line human summary for CLI output. Returns null when there is nothing
 * to report, so a clean corpus prints nothing rather than a reassuring banner
 * nobody reads.
 *
 * @param {ReturnType<typeof auditJudgmentProvenance>} audit
 * @returns {string|null}
 */
export function formatProvenanceWarning(audit) {
  // ONLY a script-minted judgment is asserted as a Law 2 problem.
  //
  // Reuse alone is NOT evidence of fabrication, and an earlier revision of
  // this function got that wrong. Measured on `projects/tallow-fen`: 54 of
  // 293 rationales are reused, and they are legitimate — two strings, ×28 and
  // ×26, each accurately describing ONE systematic defect across exactly the
  // images that have it ("style on-target but the style descriptor's
  // lantern-light noun literalized"). Reviewers there are `human:mike` and
  // `claude:fable-5`; zero scripts. That is good curation of a bad wave.
  //
  // The heuristic cannot separate "144 images share a canned category blurb
  // chosen by id-prefix" from "28 images share a true description of one
  // shared flaw" — so it must not claim to. A gate that fires when nothing is
  // wrong teaches its reader to ignore it, which is the same defect class as
  // a gate that cannot fire, pointed the other way.
  if (audit.by_origin.script === 0) return null;

  const pct = Math.round((audit.by_origin.script / Math.max(audit.judged, 1)) * 100);
  let msg =
    `Judgment provenance: ${audit.by_origin.script} of ${audit.judged} judgments (${pct}%) ` +
    `were written by a bulk script, not a reviewer. Those rationales were selected by ` +
    `matching the record id against a pattern — they do not describe the image. ` +
    `Treat them as uncurated for Law 2 purposes.`;

  if (audit.reused_rationale_records > 0) {
    msg += ` (${audit.reused_rationale_records} rationales are also reused verbatim across records.)`;
  }
  return msg;
}

/**
 * Neutral, non-accusatory reuse note — for corpora with no script reviewer but
 * heavy rationale reuse. Reuse there is usually a real systematic defect
 * described accurately across a wave, which is worth SEEING but is not a
 * finding. Returns null when there is nothing to say.
 *
 * @param {ReturnType<typeof auditJudgmentProvenance>} audit
 * @returns {string|null}
 */
export function formatReuseNote(audit) {
  if (audit.by_origin.script > 0) return null; // the warning above covers it
  if (audit.reused_rationale_records === 0) return null;

  const pct = Math.round(audit.reused_rationale_ratio * 100);
  return `${audit.reused_rationale_records} of ${audit.judged} rationales (${pct}%) are shared ` +
    `across records — often one systematic defect described across the wave it affected. ` +
    `Worth a glance, not necessarily a problem.`;
}
