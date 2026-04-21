/**
 * Split determinism + leakage + seed + empty-partition tests.
 *
 * Covers D-002 (deterministic family lane), D-003 (no silent fallback),
 * D-004 (empty-partition warnings), D-011 (seed:0 honored), D-023 (baseline tests).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createSnapshot } from '../../lib/snapshot.js';
import { createSplit } from '../../lib/split.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

function syntheticFamilies(count, recordsPerFamily = 2) {
  const records = [];
  for (let f = 0; f < count; f++) {
    const subject = `subject_${String(f).padStart(3, '0')}`;
    const baseId = `${subject}_v1`;
    records.push(makeRecord({
      id: baseId,
      identity: { subject_name: subject },
      lane: f % 2 === 0 ? 'concept' : 'portrait',
    }));
    for (let r = 1; r < recordsPerFamily; r++) {
      records.push(makeRecord({
        id: `${subject}_v${r + 1}`,
        identity: { subject_name: subject },
        lineage: { derived_from_record_id: baseId },
        lane: f % 2 === 0 ? 'concept' : 'portrait',
      }));
    }
  }
  return records;
}

const PROFILE = {
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
  exclude_lanes: [],
};

async function snapshotAndSplit(projectRoot, splitProfile) {
  const snap = await createSnapshot(projectRoot, PROFILE);
  return createSplit(projectRoot, snap.snapshotId, splitProfile);
}

test('split is deterministic — same seed + input yields identical assignment', async () => {
  const records = syntheticFamilies(20, 2);

  const p1 = createTmpProject({ records });
  const p2 = createTmpProject({ records });

  try {
    const splitProfile = { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 7 };
    const r1 = await snapshotAndSplit(p1.projectRoot, splitProfile);
    const r2 = await snapshotAndSplit(p2.projectRoot, splitProfile);

    const train1 = await readFile(join(p1.projectRoot, 'splits', r1.splitId, 'train.jsonl'), 'utf-8');
    const train2 = await readFile(join(p2.projectRoot, 'splits', r2.splitId, 'train.jsonl'), 'utf-8');
    const val1 = await readFile(join(p1.projectRoot, 'splits', r1.splitId, 'val.jsonl'), 'utf-8');
    const val2 = await readFile(join(p2.projectRoot, 'splits', r2.splitId, 'val.jsonl'), 'utf-8');

    assert.equal(train1, train2, 'train partitions must match');
    assert.equal(val1, val2, 'val partitions must match');
  } finally {
    p1.cleanup();
    p2.cleanup();
  }
});

test('no subject appears in two partitions across 5 random seeds', async () => {
  const records = syntheticFamilies(20, 3);
  const proj = createTmpProject({ records });
  try {
    for (const seed of [0, 1, 17, 99, 12345]) {
      const splitProfile = { train_ratio: 0.7, val_ratio: 0.15, test_ratio: 0.15, seed };
      const snap = await createSnapshot(proj.projectRoot, PROFILE);
      const r = await createSplit(proj.projectRoot, snap.snapshotId, splitProfile);

      const audit = JSON.parse(await readFile(
        join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));
      assert.equal(
        audit.leakage_check.passed, true,
        `seed ${seed}: leakage detected: ${JSON.stringify(audit.leakage_check.issues)}`,
      );
    }
  } finally {
    proj.cleanup();
  }
});

test('seed:0 is honored (not silently replaced by 42)', async () => {
  const records = syntheticFamilies(20, 2);
  const a = createTmpProject({ records });
  const b = createTmpProject({ records });
  try {
    const snapA = await createSnapshot(a.projectRoot, PROFILE);
    const rA = await createSplit(a.projectRoot, snapA.snapshotId,
      { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 0 });
    const snapB = await createSnapshot(b.projectRoot, PROFILE);
    const rB = await createSplit(b.projectRoot, snapB.snapshotId,
      { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 42 });

    const trainA = await readFile(join(a.projectRoot, 'splits', rA.splitId, 'train.jsonl'), 'utf-8');
    const trainB = await readFile(join(b.projectRoot, 'splits', rB.splitId, 'train.jsonl'), 'utf-8');

    assert.notEqual(trainA, trainB, 'seed 0 must not produce same split as seed 42');
  } finally {
    a.cleanup();
    b.cleanup();
  }
});

test('min-1-per-partition is guaranteed when total >= 3 (largest-remainder rebalance)', async () => {
  // 6 families concentrated in one lane under extreme 0.95/0.04/0.01 ratios
  // — naive Math.round would zero val and test. Verify all three partitions
  // receive at least 1 family.
  const records = [];
  for (let i = 0; i < 6; i++) {
    const subject = `subject_00${i * 2}`; // all even → concept
    records.push(makeRecord({
      id: `${subject}_v1`,
      identity: { subject_name: subject },
      lane: 'concept',
    }));
  }
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.95, val_ratio: 0.04, test_ratio: 0.01, seed: 1,
    });
    assert.ok(r.train >= 1 && r.val >= 1 && r.test >= 1,
      `each partition must have >=1 record: train=${r.train}, val=${r.val}, test=${r.test}`);

    const manifest = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'split.json'), 'utf-8'));
    assert.ok(Array.isArray(manifest.warnings), 'manifest must have warnings array');
  } finally {
    proj.cleanup();
  }
});

test('lane groups with <3 families emit small-lane warning', async () => {
  // Build 2 concept families — the "<3 families" branch should trigger.
  const records = [
    makeRecord({ id: 'subject_000_v1', identity: { subject_name: 'subject_000' }, lane: 'concept' }),
    makeRecord({ id: 'subject_002_v1', identity: { subject_name: 'subject_002' }, lane: 'concept' }),
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1,
    });
    const manifest = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'split.json'), 'utf-8'));
    const smallLaneWarnings = manifest.warnings.filter(w => /only \d+ families/.test(w));
    assert.ok(smallLaneWarnings.length > 0,
      `expected small-lane warnings, got: ${JSON.stringify(manifest.warnings)}`);
  } finally {
    proj.cleanup();
  }
});

test('family_lane_decisions recorded in audit (D-002)', async () => {
  const records = syntheticFamilies(6, 2);
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 5,
    });
    const audit = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));
    assert.ok(Array.isArray(audit.family_lane_decisions));
    assert.equal(audit.family_lane_decisions.length, 6);
    for (const dec of audit.family_lane_decisions) {
      assert.ok(dec.family && dec.chosen_lane && dec.lane_counts);
    }
  } finally {
    proj.cleanup();
  }
});
