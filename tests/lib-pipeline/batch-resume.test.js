/**
 * Unit tests for --resume support on `sdlab batch generate`.
 * Covers buildCompletedSlotMap (success classification) and
 * openBatchDirForResume (manifest loading + error shapes).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  buildCompletedSlotMap,
  openBatchDirForResume,
} from '../../lib/batch-runs.js';

async function makeProject() {
  const root = await mkdtemp(join(tmpdir(), 'sdl-resume-'));
  await mkdir(join(root, 'batches'), { recursive: true });
  return root;
}

async function writeBatchManifest(projectRoot, batchId, manifest) {
  const dir = join(projectRoot, 'batches', batchId);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  return dir;
}

test('buildCompletedSlotMap accepts status==="ok"', () => {
  const map = buildCompletedSlotMap([
    { slot_id: 'a', status: 'ok', selected_output: 'a.png' },
    { slot_id: 'b', status: 'error', error: 'boom' },
    { slot_id: 'c', status: 'ok', selected_output: 'c.png' },
  ]);
  assert.equal(map.size, 2);
  assert.ok(map.has('a'));
  assert.ok(map.has('c'));
  assert.ok(!map.has('b'));
});

test('buildCompletedSlotMap falls back to selected_output for legacy manifests', () => {
  const map = buildCompletedSlotMap([
    { slot_id: 'a', selected_output: 'a.png' },        // legacy: no status, has output
    { slot_id: 'b', selected_output: null },           // legacy: no output → not done
    { slot_id: 'c' },                                  // truly empty
  ]);
  assert.equal(map.size, 1);
  assert.ok(map.has('a'));
});

test('buildCompletedSlotMap tolerates malformed entries', () => {
  const map = buildCompletedSlotMap([
    null,
    undefined,
    { /* no slot_id */ status: 'ok' },
    { slot_id: 'good', status: 'ok' },
  ]);
  assert.equal(map.size, 1);
  assert.ok(map.has('good'));
});

test('buildCompletedSlotMap returns empty map for non-arrays', () => {
  assert.equal(buildCompletedSlotMap(null).size, 0);
  assert.equal(buildCompletedSlotMap(undefined).size, 0);
  assert.equal(buildCompletedSlotMap('nope').size, 0);
});

test('openBatchDirForResume loads manifest + prior results', async () => {
  const root = await makeProject();
  await writeBatchManifest(root, 'batch_2026-04-22_001', {
    batch_id: 'batch_2026-04-22_001',
    mode_id: 'expression-sheet',
    subject_id: 'captain-orryn',
    slots: [
      { slot_id: 'happy', status: 'ok', selected_output: 'happy.png' },
      { slot_id: 'angry', status: 'error', error: 'comfy 500' },
    ],
  });

  const opened = openBatchDirForResume(root, 'batch_2026-04-22_001');
  assert.equal(opened.batchId, 'batch_2026-04-22_001');
  assert.equal(opened.priorResults.length, 2);
  assert.equal(opened.priorManifest.mode_id, 'expression-sheet');
  assert.equal(opened.priorManifest.subject_id, 'captain-orryn');
});

test('openBatchDirForResume throws BATCH_NOT_FOUND for missing dir', async () => {
  const root = await makeProject();
  assert.throws(
    () => openBatchDirForResume(root, 'batch_does_not_exist'),
    err => err.code === 'BATCH_NOT_FOUND'
  );
});

test('openBatchDirForResume throws BATCH_NO_PROGRESS when slots missing', async () => {
  const root = await makeProject();
  await writeBatchManifest(root, 'batch_2026-04-22_002', {
    batch_id: 'batch_2026-04-22_002',
    mode_id: 'expression-sheet',
    // no slots field
  });
  assert.throws(
    () => openBatchDirForResume(root, 'batch_2026-04-22_002'),
    err => err.code === 'BATCH_NO_PROGRESS'
  );
});
