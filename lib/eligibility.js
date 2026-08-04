/**
 * Eligibility evaluation engine.
 *
 * Determines whether each record qualifies for inclusion in a dataset
 * snapshot, with explicit reason traces for every decision.
 */

import { detectLane, detectGroup } from './config.js';
import { warn } from './log.js';

/**
 * F5: stable, machine-readable codes — one per exclusion reason, in the
 * exact same order/count as the human-readable `reasons` strings pushed
 * below. Added so categorizeExclusions() can categorize by code instead
 * of depending on prose matching (rewording a `reasons` string used to
 * silently break categorization). Purely additive: `reasons` keeps its
 * exact original shape and text, this is a NEW parallel field
 * (`reason_codes` on the returned object) — any existing caller that only
 * reads `.eligible` / `.reasons` sees no change at all.
 */
export const REASON_CODES = {
  NO_JUDGMENT: 'no_judgment',
  WRONG_STATUS: 'wrong_status',
  NOT_CANON_BOUND: 'not_canon_bound',
  UNMEASURED_PASS_COUNT: 'unmeasured_pass_count',
  LOW_PASS_RATIO: 'low_pass_ratio',
  EXCLUDED_LANE: 'excluded_lane',
  RIGHTS_FILTER: 'rights_filter',
  EXCLUDED_TAGS: 'excluded_tags',
};

/**
 * Evaluate a single record against a selection profile.
 * @param {Object} record — full record object
 * @param {Object} profile — selection profile
 * @param {Object} lanesConfig — from lanes.json
 * @param {Object} termConfig — from terminology.json
 * @returns {{ eligible: boolean, reasons: string[], reason_codes: string[] }}
 */
export function evaluateEligibility(record, profile, lanesConfig, termConfig) {
  const reasons = [];
  // F5: parallel array — reasonCodes[i] is the stable code for reasons[i].
  const reasonCodes = [];

  // 1. Judgment required
  if (profile.require_judgment) {
    if (!record.judgment) {
      reasons.push('no judgment (record has not been reviewed)');
      reasonCodes.push(REASON_CODES.NO_JUDGMENT);
    }
  }

  // 2. Status filter
  if (profile.require_status?.length > 0 && record.judgment) {
    if (!profile.require_status.includes(record.judgment.status)) {
      reasons.push(`status "${record.judgment.status}" not in [${profile.require_status.join(', ')}]`);
      reasonCodes.push(REASON_CODES.WRONG_STATUS);
    }
  }

  // 3. Canon bound
  if (profile.require_canon_bound) {
    if (!record.canon?.assertions || record.canon.assertions.length === 0) {
      reasons.push('not canon-bound (no assertions)');
      reasonCodes.push(REASON_CODES.NOT_CANON_BOUND);
    }
  }

  // 4. Minimum pass ratio
  if (profile.minimum_pass_ratio != null && record.canon?.assertion_count > 0) {
    const passCount = record.canon.pass_count;
    // pass_count missing/non-numeric while assertion_count > 0 must NOT
    // silently compute NaN: `NaN < minimum_pass_ratio` is always false, so
    // the exclusion would never fire and a record whose pass ratio was never
    // actually measured would be treated as having cleared a bar it never
    // touched. Law 2 (inclusion is explainable) requires this be its own
    // named reason, not a silent pass.
    if (typeof passCount !== 'number' || !Number.isFinite(passCount)) {
      reasons.push(
        `pass_count is missing or not a number (assertion_count is ${record.canon.assertion_count}); ` +
          `cannot verify pass ratio, so it is excluded rather than assumed passing`
      );
      reasonCodes.push(REASON_CODES.UNMEASURED_PASS_COUNT);
    } else {
      const ratio = passCount / record.canon.assertion_count;
      if (ratio < profile.minimum_pass_ratio) {
        reasons.push(`pass ratio ${(ratio * 100).toFixed(0)}% below minimum ${(profile.minimum_pass_ratio * 100).toFixed(0)}%`);
        reasonCodes.push(REASON_CODES.LOW_PASS_RATIO);
      }
    }
  }

  // 5. Lane exclusion
  if (profile.exclude_lanes?.length > 0) {
    const prompt = record.provenance?.prompt || '';
    const lane = detectLane(record.id, prompt, lanesConfig);
    if (profile.exclude_lanes.includes(lane)) {
      reasons.push(`lane "${lane}" is excluded`);
      reasonCodes.push(REASON_CODES.EXCLUDED_LANE);
    }
  }

  // 6. Rights filter
  if (profile.rights_filter != null) {
    const rights = record.rights_status || record.training_rights_status || null;
    if (rights !== profile.rights_filter) {
      reasons.push(`rights "${rights || 'unknown'}" does not match required "${profile.rights_filter}"`);
      reasonCodes.push(REASON_CODES.RIGHTS_FILTER);
    }
  }

  // 7. Tag exclusion
  if (profile.exclude_tags?.length > 0 && record.dataset_tags) {
    const excluded = record.dataset_tags.filter(t => profile.exclude_tags.includes(t));
    if (excluded.length > 0) {
      reasons.push(`has excluded tags: ${excluded.join(', ')}`);
      reasonCodes.push(REASON_CODES.EXCLUDED_TAGS);
    }
  }

  return {
    eligible: reasons.length === 0,
    reasons,
    reason_codes: reasonCodes,
  };
}

/**
 * Categorize exclusion reasons for a set of records.
 *
 * F5: every reason is guaranteed to land in exactly one bucket — the
 * mutually-exclusive if/else-if chain below now ends in a trailing `else`
 * that increments `uncategorized` instead of silently matching nothing.
 * Previously, rewording a `reasons` string in evaluateEligibility(), or
 * adding a ninth reason with no matching branch, meant those exclusions
 * were counted in NO category at all — a gap invisible in the output
 * (the category sum would just quietly fall short of the true count).
 *
 * When an `excluded` entry carries `reason_codes` (evaluateEligibility's
 * new parallel array — see REASON_CODES above), categorization uses the
 * stable code directly instead of prose-matching `reasons`. Entries
 * without `reason_codes` (older excluded.jsonl written before F5, or a
 * caller that only forwards `reasons`) fall back to the original
 * free-text matching, unchanged.
 *
 * @param {Array<{record_id: string, reasons: string[], reason_codes?: string[]}>} excluded
 * @returns {Object} — category → count mapping (includes `uncategorized`)
 */
export function categorizeExclusions(excluded) {
  const categories = {
    no_judgment: 0,
    wrong_status: 0,
    not_canon_bound: 0,
    unmeasured_pass_count: 0,
    low_pass_ratio: 0,
    excluded_lane: 0,
    rights_filter: 0,
    excluded_tags: 0,
    uncategorized: 0,
  };
  const KNOWN_CODES = new Set(Object.values(REASON_CODES));

  // F5: sample of the actual uncategorized reason strings, surfaced via
  // warn() below so an operator sees WHAT needs a new branch/code instead
  // of just a suspicious gap in the numbers.
  const uncategorizedSamples = [];
  let totalReasons = 0;

  for (const { reasons, reason_codes: reasonCodes } of excluded) {
    reasons.forEach((r, i) => {
      totalReasons++;
      const code = reasonCodes?.[i];
      if (code && KNOWN_CODES.has(code)) {
        categories[code]++;
        return;
      }
      if (r.includes('no judgment')) categories.no_judgment++;
      else if (r.includes('status')) categories.wrong_status++;
      else if (r.includes('canon-bound')) categories.not_canon_bound++;
      // Order matters: "pass_count missing" must be checked before the
      // generic "pass ratio" match below, since an unmeasured pass_count
      // is a distinct exclusion reason from a measured-and-low ratio (Law 2
      // — inclusion must be explainable, so "never measured" cannot be
      // folded into "measured and failed").
      else if (r.includes('pass_count')) categories.unmeasured_pass_count++;
      else if (r.includes('pass ratio')) categories.low_pass_ratio++;
      else if (r.includes('lane')) categories.excluded_lane++;
      else if (r.includes('rights')) categories.rights_filter++;
      else if (r.includes('tags')) categories.excluded_tags++;
      else {
        categories.uncategorized++;
        if (uncategorizedSamples.length < 10) uncategorizedSamples.push(r);
      }
    });
  }

  if (categories.uncategorized > 0) {
    const shown = uncategorizedSamples.slice(0, 5);
    warn(
      `eligibility: ${categories.uncategorized} exclusion reason(s) matched no known category ` +
      `(first ${shown.length}: ${shown.join(' | ')})` +
      (uncategorizedSamples.length > shown.length ? ', ...' : '') +
      ' — add a matching reason_code/branch, or these will keep landing in "uncategorized".',
    );
  }

  // F5: defensive tripwire, not a normal-path check — the if/else-if chain
  // above is mutually exclusive and the trailing else always catches
  // anything unmatched, so this sum is mathematically guaranteed to equal
  // totalReasons for any input. A mismatch would mean a future edit broke
  // that mutual-exclusivity guarantee (e.g. turned an `else if` into a
  // bare `if`, allowing one reason to double-count).
  const categorizedSum = Object.values(categories).reduce((a, b) => a + b, 0);
  if (categorizedSum !== totalReasons) {
    warn(
      `eligibility: categorization invariant violated — categorized ${categorizedSum} reason(s) but ` +
      `${totalReasons} were processed. This indicates a bug in categorizeExclusions itself.`,
    );
  }

  return categories;
}
