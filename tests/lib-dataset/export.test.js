/**
 * Export fingerprint + path traversal tests.
 *
 * Covers D-001 (inherit snapshot fingerprint / drift detection) and
 * D-007 (path traversal rejection).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createSnapshot } from '../../lib/snapshot.js';
import { createSplit } from '../../lib/split.js';
import { buildExport } from '../../lib/export.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

const SELECTION = {
  profile_id: 'sel',
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
};

const SPLIT = { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 3 };

function manyFamilies(n) {
  const recs = [];
  for (let i = 0; i < n; i++) {
    recs.push(makeRecord({
      id: `subj_${i}_v1`,
      identity: { subject_name: `subj_${i}` },
      assetPath: `inputs/subj_${i}.png`,
      lane: i % 2 === 0 ? 'concept' : 'portrait',
    }));
  }
  return recs;
}

test('export embeds snapshot.config_fingerprint (not recomputed at export time)', async () => {
  const proj = createTmpProject({ records: manyFamilies(20) });
  try {
    const snap = await createSnapshot(proj.projectRoot, SELECTION);
    const split = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT);

    // Build export with --copy to satisfy Windows symlink refusal.
    const out = await buildExport(proj.projectRoot, snap.snapshotId, split.splitId, { copy: true });
    const manifest = JSON.parse(await readFile(
      join(proj.projectRoot, 'exports', out.exportId, 'manifest.json'), 'utf-8'));
    const snapManifest = JSON.parse(await readFile(
      join(proj.projectRoot, 'snapshots', snap.snapshotId, 'snapshot.json'), 'utf-8'));

    assert.equal(
      manifest.config_fingerprint, snapManifest.config_fingerprint,
      'export fingerprint must equal snapshot fingerprint',
    );
  } finally {
    proj.cleanup();
  }
});

test('export fails loudly with FINGERPRINT_DRIFT when config changed post-snapshot', async () => {
  const proj = createTmpProject({ records: manyFamilies(20) });
  try {
    const snap = await createSnapshot(proj.projectRoot, SELECTION);
    const split = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT);

    // Edit the constitution to change fingerprint
    await writeFile(
      join(proj.projectRoot, 'constitution.json'),
      JSON.stringify({ version: '1.0.1', rules: [{ id: 'new' }] }, null, 2),
    );

    await assert.rejects(
      () => buildExport(proj.projectRoot, snap.snapshotId, split.splitId, { copy: true }),
      err => err && err.code === 'FINGERPRINT_DRIFT',
    );
  } finally {
    proj.cleanup();
  }
});

test('path traversal in record.asset_path is rejected', async () => {
  // Build a record whose asset_path escapes projectRoot
  const evilRecord = makeRecord({ id: 'evil_v1', assetPath: '../../etc/passwd' });
  evilRecord.identity = { subject_name: 'evil' };

  const records = manyFamilies(10);
  records.push(evilRecord);

  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, SELECTION);
    const split = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT);

    await assert.rejects(
      () => buildExport(proj.projectRoot, snap.snapshotId, split.splitId, { copy: true }),
      err => err && (err.code === 'ASSET_PATH_TRAVERSAL' || err.code === 'ASSET_PATH_INVALID'),
    );
  } finally {
    proj.cleanup();
  }
});
