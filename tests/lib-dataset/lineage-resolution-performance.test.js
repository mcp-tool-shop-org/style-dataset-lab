/**
 * F7 (MEDIUM): lib/split.js's buildAncestorMap() called findRoot() once
 * per record, and findRoot() walked the parent chain with a FRESH
 * per-call `visited` Set — no memoization shared across calls. For a
 * linear derivation chain of length k (this pipeline's wave-over-wave
 * iteration model produces exactly that shape — record 2 derived from
 * record 1, record 3 derived from record 2, ...), resolving all k
 * records cost ~k^2/2 lookups instead of k.
 *
 * While calibrating a fix, profiling the ORIGINAL recursive walk also
 * turned up a related, strictly worse failure mode: recursion depth
 * equals chain length on every top-level call, so a long enough chain
 * crashes outright ("RangeError: Maximum call stack size exceeded")
 * before the O(n^2) cost even has a chance to matter — empirically,
 * chains of ~12,000+ records crash the original implementation on this
 * machine. The fix (memoize resolved roots into a map shared across every
 * findRoot() call, written as an explicit loop rather than recursion)
 * closes both at once.
 *
 * buildAncestorMap() is exported (previously module-private) specifically
 * so these tests can measure it directly — it is a pure function of
 * `records` (no I/O, no side effects) — rather than paying for a full
 * createSnapshot+createSplit round trip's file I/O on every record just
 * to exercise it. That distinction matters here: measured directly, the
 * fixed implementation resolves an 8,000-record chain in ~8ms versus the
 * original's ~1,760ms for the SAME input (a ~200x difference on this
 * machine) — a gap wide enough that a generous timing bound carries no
 * meaningful flakiness risk.
 *
 * This file:
 *   1. Proves multi-hop correctness through the real createSplit()
 *      pipeline (a 6-hop chain must resolve every descendant to the SAME
 *      true root family, not just its immediate parent) — a cheap
 *      integration-level check that the wiring into createSplit is intact.
 *   2. Proves the O(n) complexity directly via buildAncestorMap(), with a
 *      wide-margin wall-clock bound.
 *   3. Proves the crash is gone directly via buildAncestorMap() at a scale
 *      well past the empirically-observed crash threshold.
 *   4. Proves a pathological lineage cycle (which should never
 *      legitimately occur, but the code still has to survive one) still
 *      terminates safely after the recursive-to-iterative rewrite.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createSnapshot } from '../../lib/snapshot.js';
import { createSplit, buildAncestorMap } from '../../lib/split.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

const PROFILE = {
  profile_id: 'f7-lineage',
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
};
const SPLIT_PROFILE = { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1 };

/**
 * Build a linear derivation chain of `n` bare records — id + lineage
 * only. buildAncestorMap() only ever reads `record.id` and
 * `record.lineage?.derived_from_record_id`, so these deliberately skip
 * the rest of makeRecord()'s fields to keep large-N construction cheap.
 */
function buildLinearChainStubs(n) {
  const records = [];
  let parentId = null;
  for (let i = 0; i < n; i++) {
    const id = `chain_${i}`;
    records.push({ id, ...(parentId ? { lineage: { derived_from_record_id: parentId } } : {}) });
    parentId = id;
  }
  return records;
}

// ─── Correctness (integration): multi-hop chains resolve to the TRUE root ─

test('F7: a 6-hop linear lineage chain resolves every descendant to the single true root family, not just its immediate parent', async () => {
  const records = [
    makeRecord({ id: 'hero_v1', identity: { subject_name: 'hero' } }), // root — the ONLY one with authored identity
    makeRecord({ id: 'hero_v2', lineage: { derived_from_record_id: 'hero_v1' } }),
    makeRecord({ id: 'hero_v3', lineage: { derived_from_record_id: 'hero_v2' } }),
    makeRecord({ id: 'hero_v4', lineage: { derived_from_record_id: 'hero_v3' } }),
    makeRecord({ id: 'hero_v5', lineage: { derived_from_record_id: 'hero_v4' } }),
    makeRecord({ id: 'hero_v6', lineage: { derived_from_record_id: 'hero_v5' } }),
    // Two unrelated filler families so the ratios have something to allocate.
    makeRecord({ id: 'filler_a', identity: { subject_name: 'filler_a' } }),
    makeRecord({ id: 'filler_b', identity: { subject_name: 'filler_b' } }),
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT_PROFILE);
    const audit = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));

    // 3 families total: the merged 6-hop hero chain + 2 fillers — NOT 8,
    // which is what a broken multi-hop walk (e.g. one that only resolved
    // one level of lineage) would produce.
    assert.equal(audit.family_count, 3, `expected the 6-hop chain to merge into 1 family (+2 fillers = 3 total), got family_count=${audit.family_count}`);
    assert.equal(audit.leakage_check.passed, true, 'the 6-hop chain must never split across partitions');

    const [train, val, testP] = await Promise.all(
      ['train', 'val', 'test'].map(p =>
        readFile(join(proj.projectRoot, 'splits', r.splitId, `${p}.jsonl`), 'utf-8')));
    const heroIds = ['hero_v1', 'hero_v2', 'hero_v3', 'hero_v4', 'hero_v5', 'hero_v6'];
    const allIn = (partitionText) => heroIds.every(id => partitionText.includes(id));
    assert.ok(
      allIn(train) || allIn(val) || allIn(testP),
      'all 6 hops of the lineage chain must land in the same partition together',
    );
  } finally {
    proj.cleanup();
  }
});

// ─── Performance: O(n), not O(n^2) — measured directly, wide margin ─────

test('F7: buildAncestorMap resolves an 8,000-record linear chain in well under a second (O(n), not O(n^2)) — RED branch driven explicitly', () => {
  const records = buildLinearChainStubs(8000);

  const t0 = performance.now();
  const map = buildAncestorMap(records);
  const elapsedMs = performance.now() - t0;

  assert.equal(map.size, 7999, 'every record except the root has a lineage entry');

  // Calibrated on this machine: the O(n) (memoized, iterative)
  // implementation resolves this input in ~8ms; the O(n^2) (original —
  // unmemoized, per-call-fresh-visited-Set) implementation takes ~1,760ms
  // for the SAME input — roughly a 200x gap. 300ms leaves enormous margin
  // on both sides (~37x the fixed baseline, ~6x below the unfixed one),
  // so this is not a timing test that can plausibly flake from ordinary
  // machine variance.
  assert.ok(
    elapsedMs < 300,
    `buildAncestorMap on an 8,000-record linear chain took ${elapsedMs.toFixed(1)}ms — ` +
    'expected well under 300ms for O(n) lineage resolution. A regression back to O(n^2) ' +
    '(an unmemoized or per-call-fresh-cache findRoot) is the most likely cause.',
  );
});

// ─── Robustness: no stack overflow on a long chain (recursion-depth fix) ─

test('F7: buildAncestorMap resolves a 50,000-record linear chain without a stack overflow — RED branch driven explicitly', () => {
  // Empirically, the ORIGINAL recursive (unmemoized) walk crashes with
  // "RangeError: Maximum call stack size exceeded" on chains of roughly
  // 12,000+ records on this machine. 50,000 sits with wide margin past
  // that threshold, while still resolving in well under a second with the
  // fix (iteration, not recursion, plus memoization).
  const records = buildLinearChainStubs(50000);
  const map = buildAncestorMap(records); // must not throw
  assert.equal(map.size, 49999);
});

// ─── Cycle safety: pathological input still terminates cleanly ──────────

test('F7: a pathological lineage cycle terminates safely (no infinite loop / stack overflow) after the iterative rewrite', () => {
  // a -> c -> b -> a: a cycle. lineage.derived_from_record_id should
  // never legitimately contain a cycle, but the walk still has to
  // survive one without hanging or crashing.
  const records = [
    { id: 'cyc_a', lineage: { derived_from_record_id: 'cyc_c' } },
    { id: 'cyc_b', lineage: { derived_from_record_id: 'cyc_a' } },
    { id: 'cyc_c', lineage: { derived_from_record_id: 'cyc_b' } },
    { id: 'filler_1' }, // no lineage — not part of the cycle
  ];
  const map = buildAncestorMap(records); // must not throw / hang
  // The exact family label a cycle resolves to is not a meaningful
  // contract (a cycle has no true root) — completing at all, with every
  // cyclic member accounted for exactly once, is the property under test.
  assert.equal(map.size, 3);
  assert.ok(map.has('cyc_a'));
  assert.ok(map.has('cyc_b'));
  assert.ok(map.has('cyc_c'));
  assert.ok(!map.has('filler_1'), 'a record with no lineage never gets an ancestorMap entry');
  // All three cyclic members must resolve to the SAME family — the cycle
  // must be treated as one group, not silently scattered.
  const families = new Set([
    map.get('cyc_a').family,
    map.get('cyc_b').family,
    map.get('cyc_c').family,
  ]);
  assert.equal(families.size, 1, `all cyclic members must share one family, got: ${[...families]}`);
});

// ─── Cycle safety (integration): the real createSplit pipeline survives it ──

test('F7: a pathological lineage cycle does not break createSplit end-to-end', async () => {
  const records = [
    makeRecord({ id: 'cyc_a', lineage: { derived_from_record_id: 'cyc_c' } }),
    makeRecord({ id: 'cyc_b', lineage: { derived_from_record_id: 'cyc_a' } }),
    makeRecord({ id: 'cyc_c', lineage: { derived_from_record_id: 'cyc_b' } }),
    makeRecord({ id: 'filler_1', identity: { subject_name: 'filler_1' } }),
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT_PROFILE);
    assert.equal(r.train, 4);
    assert.equal(r.val, 0);
    assert.equal(r.test, 0);
  } finally {
    proj.cleanup();
  }
});
