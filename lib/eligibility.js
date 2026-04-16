/**
 * Eligibility evaluation engine.
 *
 * Determines whether each record qualifies for inclusion in a dataset
 * snapshot, with explicit reason traces for every decision.
 */

import { detectLane, detectGroup } from './config.js';

/**
 * Evaluate a single record against a selection profile.
 * @param {Object} record — full record object
 * @param {Object} profile — selection profile
 * @param {Object} lanesConfig — from lanes.json
 * @param {Object} termConfig — from terminology.json
 * @returns {{ eligible: boolean, reasons: string[] }}
 */
export function evaluateEligibility(record, profile, lanesConfig, termConfig) {
  const reasons = [];

  // 1. Judgment required
  if (profile.require_judgment) {
    if (!record.judgment) {
      reasons.push('no judgment (record has not been reviewed)');
    }
  }

  // 2. Status filter
  if (profile.require_status?.length > 0 && record.judgment) {
    if (!profile.require_status.includes(record.judgment.status)) {
      reasons.push(`status "${record.judgment.status}" not in [${profile.require_status.join(', ')}]`);
    }
  }

  // 3. Canon bound
  if (profile.require_canon_bound) {
    if (!record.canon?.assertions || record.canon.assertions.length === 0) {
      reasons.push('not canon-bound (no assertions)');
    }
  }

  // 4. Minimum pass ratio
  if (profile.minimum_pass_ratio != null && record.canon?.assertion_count > 0) {
    const ratio = record.canon.pass_count / record.canon.assertion_count;
    if (ratio < profile.minimum_pass_ratio) {
      reasons.push(`pass ratio ${(ratio * 100).toFixed(0)}% below minimum ${(profile.minimum_pass_ratio * 100).toFixed(0)}%`);
    }
  }

  // 5. Lane exclusion
  if (profile.exclude_lanes?.length > 0) {
    const prompt = record.provenance?.prompt || '';
    const lane = detectLane(record.id, prompt, lanesConfig);
    if (profile.exclude_lanes.includes(lane)) {
      reasons.push(`lane "${lane}" is excluded`);
    }
  }

  // 6. Rights filter
  if (profile.rights_filter != null) {
    const rights = record.rights_status || record.training_rights_status || null;
    if (rights !== profile.rights_filter) {
      reasons.push(`rights "${rights || 'unknown'}" does not match required "${profile.rights_filter}"`);
    }
  }

  // 7. Tag exclusion
  if (profile.exclude_tags?.length > 0 && record.dataset_tags) {
    const excluded = record.dataset_tags.filter(t => profile.exclude_tags.includes(t));
    if (excluded.length > 0) {
      reasons.push(`has excluded tags: ${excluded.join(', ')}`);
    }
  }

  return {
    eligible: reasons.length === 0,
    reasons,
  };
}

/**
 * Categorize exclusion reasons for a set of records.
 * @param {Array<{record_id: string, reasons: string[]}>} excluded
 * @returns {Object} — category → count mapping
 */
export function categorizeExclusions(excluded) {
  const categories = {
    no_judgment: 0,
    wrong_status: 0,
    not_canon_bound: 0,
    low_pass_ratio: 0,
    excluded_lane: 0,
    rights_filter: 0,
    excluded_tags: 0,
  };

  for (const { reasons } of excluded) {
    for (const r of reasons) {
      if (r.includes('no judgment')) categories.no_judgment++;
      else if (r.includes('status')) categories.wrong_status++;
      else if (r.includes('canon-bound')) categories.not_canon_bound++;
      else if (r.includes('pass ratio')) categories.low_pass_ratio++;
      else if (r.includes('lane')) categories.excluded_lane++;
      else if (r.includes('rights')) categories.rights_filter++;
      else if (r.includes('tags')) categories.excluded_tags++;
    }
  }

  return categories;
}
