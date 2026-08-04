/**
 * F5 (MEDIUM): categorizeExclusions() bucketed by free-text `r.includes(...)`
 * across eight branches with NO trailing else. Rewording a reason string in
 * evaluateEligibility(), or adding a ninth reason without a matching
 * branch, meant those exclusions were counted in NO category at all — a
 * gap invisible in the output, with no assertion anywhere that the
 * categorized total matched the true number of reasons processed.
 *
 * Fix: an `uncategorized` bucket (+ warn() when non-zero, naming sample
 * reason strings) closes the silent-loss gap. Additionally,
 * evaluateEligibility() now also returns a parallel `reason_codes` array
 * (one stable code per reason, in REASON_CODES) so categorizeExclusions
 * can categorize by code instead of depending on prose matching at all —
 * purely additive: `reasons` keeps its exact original shape/text, and
 * `categorizeExclusions` falls back to prose matching whenever
 * `reason_codes` is absent (old on-disk excluded.jsonl, or a caller that
 * only forwards `reasons`), so nothing that read the old shape breaks.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { evaluateEligibility, categorizeExclusions, REASON_CODES } from '../../lib/eligibility.js';
import { createSnapshot } from '../../lib/snapshot.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

// ─── categorizeExclusions: the uncategorized catch-all ──────────────────

test('F5: a reworded/unmatched reason string lands in "uncategorized", not silently nowhere — RED branch driven explicitly', () => {
  const excluded = [
    { record_id: 'rec-1', reasons: ['this reason text matches none of the eight known free-text patterns'] },
  ];
  const categories = categorizeExclusions(excluded);
  assert.equal(categories.uncategorized, 1);
  for (const [cat, count] of Object.entries(categories)) {
    if (cat !== 'uncategorized') assert.equal(count, 0, `category "${cat}" must stay at 0, got ${count}`);
  }
});

test('F5: the category sum always equals the total number of reasons processed (never silently short)', () => {
  const excluded = [
    { record_id: 'rec-1', reasons: [
      'no judgment (record has not been reviewed)',
      'a brand-new ninth reason nobody wrote a matching branch for',
    ] },
    { record_id: 'rec-2', reasons: ['status "borderline" not in [approved]'] },
  ];
  const categories = categorizeExclusions(excluded);
  const totalReasons = excluded.reduce((sum, e) => sum + e.reasons.length, 0);
  const categorizedSum = Object.values(categories).reduce((a, b) => a + b, 0);
  assert.equal(categorizedSum, totalReasons, 'every reason must land in exactly one bucket, none lost');
  assert.equal(categories.uncategorized, 1);
  assert.equal(categories.no_judgment, 1);
  assert.equal(categories.wrong_status, 1);
});

test('F5: no false positives — a normal, fully-matchable exclusion set has zero uncategorized — explicit PASS branch for contrast', () => {
  const excluded = [
    { record_id: 'rec-1', reasons: ['no judgment (record has not been reviewed)'] },
    { record_id: 'rec-2', reasons: ['not canon-bound (no assertions)'] },
    { record_id: 'rec-3', reasons: ['lane "concept" is excluded'] },
  ];
  const categories = categorizeExclusions(excluded);
  assert.equal(categories.uncategorized, 0);
  assert.equal(categories.no_judgment, 1);
  assert.equal(categories.not_canon_bound, 1);
  assert.equal(categories.excluded_lane, 1);
});

// ─── evaluateEligibility: reason_codes parallel array, one per branch ───

test('F5: evaluateEligibility reason_codes — no_judgment', () => {
  const result = evaluateEligibility({ id: 'r1' }, { require_judgment: true }, {}, {});
  assert.equal(result.reasons.length, result.reason_codes.length);
  assert.deepEqual(result.reason_codes, [REASON_CODES.NO_JUDGMENT]);
});

test('F5: evaluateEligibility reason_codes — wrong_status', () => {
  const record = { id: 'r2', judgment: { status: 'borderline' } };
  const result = evaluateEligibility(record, { require_status: ['approved'] }, {}, {});
  assert.deepEqual(result.reason_codes, [REASON_CODES.WRONG_STATUS]);
});

test('F5: evaluateEligibility reason_codes — not_canon_bound', () => {
  const record = { id: 'r3', judgment: { status: 'approved' } };
  const result = evaluateEligibility(record, { require_canon_bound: true }, {}, {});
  assert.deepEqual(result.reason_codes, [REASON_CODES.NOT_CANON_BOUND]);
});

test('F5: evaluateEligibility reason_codes — unmeasured_pass_count', () => {
  const record = { id: 'r4', canon: { assertion_count: 5 } }; // pass_count absent
  const result = evaluateEligibility(record, { minimum_pass_ratio: 0.5 }, {}, {});
  assert.deepEqual(result.reason_codes, [REASON_CODES.UNMEASURED_PASS_COUNT]);
});

test('F5: evaluateEligibility reason_codes — low_pass_ratio', () => {
  const record = { id: 'r5', canon: { assertion_count: 10, pass_count: 1 } };
  const result = evaluateEligibility(record, { minimum_pass_ratio: 0.5 }, {}, {});
  assert.deepEqual(result.reason_codes, [REASON_CODES.LOW_PASS_RATIO]);
});

test('F5: evaluateEligibility reason_codes — excluded_lane', () => {
  const record = { id: 'concept_9', provenance: { prompt: 'a concept piece' } };
  const lanesConfig = { default_lane: 'other', lanes: [{ id: 'concept', id_patterns: ['concept'] }] };
  const result = evaluateEligibility(record, { exclude_lanes: ['concept'] }, lanesConfig, {});
  assert.deepEqual(result.reason_codes, [REASON_CODES.EXCLUDED_LANE]);
});

test('F5: evaluateEligibility reason_codes — rights_filter', () => {
  const record = { id: 'r7', rights_status: 'unknown' };
  const result = evaluateEligibility(record, { rights_filter: 'cleared' }, {}, {});
  assert.deepEqual(result.reason_codes, [REASON_CODES.RIGHTS_FILTER]);
});

test('F5: evaluateEligibility reason_codes — excluded_tags', () => {
  const record = { id: 'r8', dataset_tags: ['nsfw'] };
  const result = evaluateEligibility(record, { exclude_tags: ['nsfw'] }, {}, {});
  assert.deepEqual(result.reason_codes, [REASON_CODES.EXCLUDED_TAGS]);
});

test('F5: evaluateEligibility on a fully eligible record returns empty reasons AND empty reason_codes', () => {
  const record = { id: 'r9', judgment: { status: 'approved' }, canon: { assertion_count: 5, pass_count: 5, assertions: [{}] } };
  const result = evaluateEligibility(record, { require_judgment: true, require_status: ['approved'] }, {}, {});
  assert.equal(result.eligible, true);
  assert.deepEqual(result.reasons, []);
  assert.deepEqual(result.reason_codes, []);
});

// ─── categorizeExclusions: reason_codes take priority, prose fallback preserved ───

test('F5: categorizeExclusions uses reason_codes when present, even if the reworded prose would not match any pattern', () => {
  const excluded = [
    {
      record_id: 'rec-1',
      reasons: ['a totally reworded human sentence with no matching keywords at all'],
      reason_codes: [REASON_CODES.LOW_PASS_RATIO],
    },
  ];
  const categories = categorizeExclusions(excluded);
  assert.equal(categories.low_pass_ratio, 1, 'reason_codes must be used even though the prose alone would not match');
  assert.equal(categories.uncategorized, 0);
});

test('F5: categorizeExclusions falls back to prose matching when reason_codes is absent — backward compatible with pre-F5 excluded.jsonl', () => {
  const excluded = [
    { record_id: 'rec-1', reasons: ['no judgment (record has not been reviewed)'] }, // no reason_codes key at all
  ];
  const categories = categorizeExclusions(excluded);
  assert.equal(categories.no_judgment, 1);
  assert.equal(categories.uncategorized, 0);
});

// ─── Integration: createSnapshot actually writes reason_codes end-to-end ───

test('F5: createSnapshot writes reason_codes into excluded.jsonl, and categorizeExclusions on the real output has zero uncategorized', async () => {
  const records = [
    makeRecord({ id: 'ok_1' }),
    makeRecord({ id: 'bad_1', status: 'rejected' }),
  ];
  const proj = createTmpProject({ records });
  try {
    const profile = {
      profile_id: 'f5-selection',
      require_judgment: true,
      require_status: ['approved'],
      require_canon_bound: true,
      minimum_pass_ratio: 0.5,
    };
    const snap = await createSnapshot(proj.projectRoot, profile);
    assert.equal(snap.excluded, 1);

    const raw = await readFile(
      join(proj.projectRoot, 'snapshots', snap.snapshotId, 'excluded.jsonl'), 'utf-8');
    const excluded = raw.trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
    assert.equal(excluded.length, 1);
    assert.ok(Array.isArray(excluded[0].reason_codes), 'excluded.jsonl entries must carry reason_codes');
    assert.equal(excluded[0].reason_codes.length, excluded[0].reasons.length);
    assert.deepEqual(excluded[0].reason_codes, [REASON_CODES.WRONG_STATUS]);

    const categories = categorizeExclusions(excluded);
    assert.equal(categories.wrong_status, 1);
    assert.equal(categories.uncategorized, 0);
  } finally {
    proj.cleanup();
  }
});
