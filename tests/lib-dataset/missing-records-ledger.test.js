/**
 * F3 (HIGH): a record referenced by a Law-1 frozen snapshot (or a split
 * built from one) whose underlying JSON file is later deleted from
 * records/ must never vanish silently. loadRecord() returns null on ENOENT
 * (lib/records.js); four consumers treated that null as a silent skip with
 * no counter, no warning, no id recorded:
 *
 *   - lib/split.js (createSplit)                        -> WARN + ledger
 *   - lib/export.js (buildExport)                        -> HARD-FAIL
 *   - lib/training-packages.js (buildTrainingPackage)     -> HARD-FAIL
 *   - lib/implementation-packs.js (buildImplementationPack,
 *     both the prompt-examples AND subject-continuity loops) -> WARN + ledger
 *
 * export.js and training-packages.js hard-fail rather than warn because
 * Law 4 ("exports are reproducible — rebuildable from snapshot + split +
 * profile") makes completeness of THOSE two artifacts an actual contract.
 * split.js and implementation-packs.js are intermediate / illustrative
 * artifacts and get the warn()-and-ledger treatment mirroring the
 * images_failed pattern export.js's own DB-002 fix already established.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, rm, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { createSnapshot } from '../../lib/snapshot.js';
import { createSplit, loadSplitPartition } from '../../lib/split.js';
import { buildExport } from '../../lib/export.js';
import { buildTrainingPackage } from '../../lib/training-packages.js';
import { buildImplementationPack, loadImplementationPack } from '../../lib/implementation-packs.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';
import { createTrainingPackageProject } from './fixtures/make-training-package-project.js';

const SELECTION = {
  profile_id: 'f3-selection',
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
};
const SPLIT_PROFILE = { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1 };

/** Capture console.error calls (warn() writes here) for the duration of fn. */
async function captureWarnings(fn) {
  const original = console.error;
  const calls = [];
  console.error = (...args) => { calls.push(args.join(' ')); };
  try {
    const result = await fn();
    return { result, calls };
  } finally {
    console.error = original;
  }
}

/** Assert no directory under `parentDir` contains a manifest.json — i.e. an aborted build left no usable artifact behind. */
async function assertNoManifestUnder(parentDir) {
  if (!existsSync(parentDir)) return;
  for (const d of await readdir(parentDir)) {
    assert.ok(
      !existsSync(join(parentDir, d, 'manifest.json')),
      `aborted build must not leave a usable manifest.json in ${join(parentDir, d)}`,
    );
  }
}

// ─── split.js: WARN + ledger ─────────────────────────────────────────────

test('F3/split: a snapshot-included record deleted before createSplit is warned on and recorded in missing_records, not silently dropped', async () => {
  const records = Array.from({ length: 6 }, (_, i) => makeRecord({ id: `rec_${i}` }));
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, SELECTION);
    assert.equal(snap.included, 6);

    // Delete a record AFTER the snapshot froze its inclusion (Law 1) — the
    // snapshot's included.jsonl still names it; records/ no longer has it.
    await rm(join(proj.projectRoot, 'records', 'rec_3.json'));

    const { result: r, calls } = await captureWarnings(() =>
      createSplit(proj.projectRoot, snap.snapshotId, SPLIT_PROFILE));

    assert.equal(r.train + r.val + r.test, 5, 'the missing record must not silently inflate or otherwise be counted');

    const manifest = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'split.json'), 'utf-8'));
    assert.equal(manifest.counts.missing_records, 1);
    assert.deepEqual(manifest.missing_records, [{ record_id: 'rec_3', stage: 'split' }]);
    assert.ok(
      manifest.warnings.some(w => /rec_3/.test(w) && /could not be loaded/.test(w)),
      `expected a missing-record warning naming rec_3, got: ${JSON.stringify(manifest.warnings)}`,
    );
    assert.ok(calls.some(c => /rec_3/.test(c)), 'warn() must actually fire (visible at default verbosity)');
  } finally {
    proj.cleanup();
  }
});

test('F3/split: missing_records ledger is empty when every snapshot-included record is present — explicit PASS branch for contrast', async () => {
  const records = Array.from({ length: 5 }, (_, i) => makeRecord({ id: `clean_${i}` }));
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, SELECTION);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT_PROFILE);
    const manifest = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'split.json'), 'utf-8'));
    assert.equal(manifest.counts.missing_records, 0);
    assert.deepEqual(manifest.missing_records, []);
    assert.equal(r.train + r.val + r.test, 5);
  } finally {
    proj.cleanup();
  }
});

// ─── export.js: HARD-FAIL ────────────────────────────────────────────────

async function buildExportProfile(projectRoot) {
  const exportProfilesDir = join(projectRoot, 'export-profiles');
  await mkdir(exportProfilesDir, { recursive: true });
  await writeFile(join(exportProfilesDir, 'default.json'), JSON.stringify({
    profile_id: 'default',
    metadata_fields: ['id', 'asset_path'],
    // include_images:false — this test is about the missing-RECORD guard,
    // not image placement; keeps the fixture from needing real PNGs on disk.
    include_images: false,
    include_splits: false,
    include_card: false,
    include_checksums: false,
  }));
}

test('F3/export: a snapshot-included record deleted before buildExport hard-fails with EXPORT_MISSING_RECORDS naming the record — RED branch driven explicitly', async () => {
  const records = Array.from({ length: 5 }, (_, i) => makeRecord({ id: `exp_${i}` }));
  const proj = createTmpProject({ records });
  try {
    await buildExportProfile(proj.projectRoot);
    const snap = await createSnapshot(proj.projectRoot, SELECTION);
    const split = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT_PROFILE);

    // Delete a record referenced by the frozen (Law 1) snapshot.
    await rm(join(proj.projectRoot, 'records', 'exp_2.json'));

    await assert.rejects(
      () => buildExport(proj.projectRoot, snap.snapshotId, split.splitId, { copy: true, profileId: 'default' }),
      (err) => {
        assert.equal(err.code, 'EXPORT_MISSING_RECORDS');
        assert.ok(err.message.includes('exp_2'), `error message must name the missing record: ${err.message}`);
        assert.ok(err.message.includes(snap.snapshotId));
        return true;
      },
    );

    // Nothing usable should have been written — export is Law 4's contract.
    await assertNoManifestUnder(join(proj.projectRoot, 'exports'));
  } finally {
    proj.cleanup();
  }
});

test('F3/export: buildExport succeeds normally when every record is present — explicit PASS branch for contrast', async () => {
  const records = Array.from({ length: 5 }, (_, i) => makeRecord({ id: `expok_${i}` }));
  const proj = createTmpProject({ records });
  try {
    await buildExportProfile(proj.projectRoot);
    const snap = await createSnapshot(proj.projectRoot, SELECTION);
    const split = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT_PROFILE);

    const result = await buildExport(proj.projectRoot, snap.snapshotId, split.splitId, { copy: true, profileId: 'default' });
    assert.equal(result.recordCount, 5);
  } finally {
    proj.cleanup();
  }
});

// ─── training-packages.js: HARD-FAIL ────────────────────────────────────

test('F3/training-package: a split-referenced record deleted before buildTrainingPackage hard-fails with TRAINING_PACKAGE_MISSING_RECORDS — RED branch driven explicitly', async () => {
  const proj = await createTrainingPackageProject({ count: 5 });
  try {
    // Delete a record the split's train/val/test partitions reference.
    const missingId = 'pkgtest_2';
    await rm(join(proj.projectRoot, 'records', `${missingId}.json`));

    await assert.rejects(
      () => buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true, profileId: 'default' }),
      (err) => {
        assert.equal(err.code, 'TRAINING_PACKAGE_MISSING_RECORDS');
        assert.ok(err.message.includes(missingId), `error message must name the missing record: ${err.message}`);
        return true;
      },
    );

    await assertNoManifestUnder(join(proj.projectRoot, 'training', 'packages'));
  } finally {
    proj.cleanup();
  }
});

test('F3/training-package: buildTrainingPackage succeeds normally when every record is present — explicit PASS branch for contrast', async () => {
  const proj = await createTrainingPackageProject({ count: 5 });
  try {
    const result = await buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true });
    assert.equal(result.records, 5);
  } finally {
    proj.cleanup();
  }
});

// ─── implementation-packs.js: WARN + ledger (two loops) ─────────────────

test('F3/implementation-pack: a split-referenced record deleted before buildImplementationPack is warned on and recorded in missing_records from BOTH loops', async () => {
  const proj = await createTrainingPackageProject({ count: 6 });
  try {
    // Pick a record that is actually in train or test (buildImplementationPack
    // never looks at val) so deleting it is guaranteed to be observed by
    // both the prompt-examples and subject-continuity loops, regardless of
    // exactly how the split algorithm assigned families to partitions.
    const trainEntries = await loadSplitPartition(proj.projectRoot, proj.splitId, 'train');
    const testEntries = await loadSplitPartition(proj.projectRoot, proj.splitId, 'test');
    const candidate = (trainEntries[0] || testEntries[0])?.record_id;
    assert.ok(candidate, 'fixture must produce at least one train or test entry to delete');

    await rm(join(proj.projectRoot, 'records', `${candidate}.json`));

    const { result, calls } = await captureWarnings(() =>
      buildImplementationPack(proj.projectRoot, proj.manifestId));

    const manifest = await loadImplementationPack(proj.projectRoot, result.implId);
    assert.equal(manifest.counts.missing_records, 2, 'both loops independently hit the same missing id');
    assert.ok(manifest.missing_records.some(m => m.record_id === candidate && m.source === 'prompt-examples'));
    assert.ok(manifest.missing_records.some(m => m.record_id === candidate && m.source === 'subject-continuity'));
    assert.ok(manifest.missing_records.every(m => m.stage === 'implementation-pack'));

    assert.ok(calls.some(c => c.includes(candidate)), 'warn() must actually fire (visible at default verbosity)');
  } finally {
    proj.cleanup();
  }
});

test('F3/implementation-pack: missing_records ledger is empty when every split-referenced record is present — explicit PASS branch for contrast', async () => {
  const proj = await createTrainingPackageProject({ count: 6 });
  try {
    const { result } = await captureWarnings(() =>
      buildImplementationPack(proj.projectRoot, proj.manifestId));
    const manifest = await loadImplementationPack(proj.projectRoot, result.implId);
    assert.equal(manifest.counts.missing_records, 0);
    assert.deepEqual(manifest.missing_records, []);
  } finally {
    proj.cleanup();
  }
});
