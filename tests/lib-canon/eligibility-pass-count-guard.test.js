/**
 * SDL-M13 — evaluateEligibility() must not let a missing/non-numeric
 * pass_count silently pass the minimum-pass-ratio gate.
 *
 * Before this fix: `ratio = record.canon.pass_count / record.canon.assertion_count`
 * evaluates to NaN when pass_count is missing or non-numeric while
 * assertion_count > 0. `NaN < minimum_pass_ratio` is ALWAYS false in JS, so
 * the exclusion reason was never pushed — a record whose pass ratio was
 * never actually measured was silently treated as having cleared a bar it
 * never touched. Law 2 (inclusion is explainable) requires every inclusion
 * to carry a reason trace; a silently-defaulted pass has none.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { evaluateEligibility, categorizeExclusions } from '../../lib/eligibility.js';

const profile = {
  minimum_pass_ratio: 0.8,
};

const lanesConfig = {};
const termConfig = {};

// --- RED-branch coverage: missing/invalid pass_count must exclude, not silently pass ---

test('evaluateEligibility: missing pass_count under assertion_count > 0 is EXCLUDED, not silently eligible', () => {
  const record = {
    id: 'rec-1',
    canon: { assertions: [{}], assertion_count: 5 /* pass_count intentionally absent */ },
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, false, 'a record whose pass ratio was never measured must not be eligible');
  assert.ok(
    result.reasons.some((r) => r.includes('pass_count')),
    `expected a pass_count-specific reason, got: ${JSON.stringify(result.reasons)}`,
  );
});

test('evaluateEligibility: pass_count as a non-numeric type (string) is EXCLUDED', () => {
  const record = {
    id: 'rec-2',
    canon: { assertion_count: 5, pass_count: '5' }, // string, not number — a data-entry slip
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, false);
  assert.ok(result.reasons.some((r) => r.includes('pass_count')));
});

test('evaluateEligibility: pass_count explicitly NaN is EXCLUDED (Number.isFinite guard, not just typeof)', () => {
  const record = {
    id: 'rec-3',
    canon: { assertion_count: 5, pass_count: NaN },
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, false);
  assert.ok(result.reasons.some((r) => r.includes('pass_count')));
});

test('evaluateEligibility: pass_count as Infinity is EXCLUDED (Number.isFinite guard)', () => {
  const record = {
    id: 'rec-4',
    canon: { assertion_count: 5, pass_count: Infinity },
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, false);
  assert.ok(result.reasons.some((r) => r.includes('pass_count')));
});

test('evaluateEligibility: pass_count reason names the assertion_count for operator triage', () => {
  const record = {
    id: 'rec-5',
    canon: { assertion_count: 7 },
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.ok(result.reasons.some((r) => r.includes('7')), `expected assertion_count=7 in reason: ${result.reasons}`);
});

// --- Regression guards: legitimate numeric pass_count values are unaffected ---

test('REGRESSION GUARD: pass_count=0 (a real, measured zero) still excludes via the normal low-ratio path', () => {
  const record = {
    id: 'rec-6',
    canon: { assertion_count: 5, pass_count: 0 },
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, false);
  // Must be the MEASURED low-ratio reason, not the unmeasured-pass_count reason.
  assert.ok(result.reasons.some((r) => r.includes('pass ratio')));
  assert.ok(!result.reasons.some((r) => r.includes('pass_count')));
});

test('REGRESSION GUARD: valid pass_count/assertion_count meeting the minimum is still eligible', () => {
  const record = {
    id: 'rec-7',
    judgment: undefined,
    canon: { assertion_count: 10, pass_count: 9 }, // 90% >= 80% minimum
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, true);
  assert.deepEqual(result.reasons, []);
});

test('REGRESSION GUARD: valid pass_count/assertion_count below the minimum is excluded via the measured-ratio reason', () => {
  const record = {
    id: 'rec-8',
    canon: { assertion_count: 10, pass_count: 5 }, // 50% < 80% minimum
  };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, false);
  assert.ok(result.reasons.some((r) => r.includes('pass ratio 50% below minimum 80%')));
});

test('REGRESSION GUARD: assertion_count 0 (or absent) skips the pass-ratio check entirely, as before', () => {
  const record = { id: 'rec-9', canon: { assertion_count: 0 } };
  const result = evaluateEligibility(record, profile, lanesConfig, termConfig);
  assert.equal(result.eligible, true);
});

test('REGRESSION GUARD: profile without minimum_pass_ratio never triggers this check', () => {
  const record = { id: 'rec-10', canon: { assertion_count: 5 } }; // no pass_count, but no minimum set either
  const result = evaluateEligibility(record, {}, lanesConfig, termConfig);
  assert.equal(result.eligible, true);
});

// --- categorizeExclusions: the new reason gets its own bucket, not lumped into low_pass_ratio ---

test('categorizeExclusions: unmeasured pass_count buckets separately from low_pass_ratio', () => {
  const excluded = [
    { record_id: 'rec-1', reasons: ['pass_count is missing or not a number (assertion_count is 5); cannot verify pass ratio, so it is excluded rather than assumed passing'] },
    { record_id: 'rec-8', reasons: ['pass ratio 50% below minimum 80%'] },
  ];
  const categories = categorizeExclusions(excluded);
  assert.equal(categories.unmeasured_pass_count, 1, 'the unmeasured case must not be folded into low_pass_ratio');
  assert.equal(categories.low_pass_ratio, 1, 'the genuinely-measured-and-low case is unaffected');
});
