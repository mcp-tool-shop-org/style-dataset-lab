/**
 * Unit tests for runtime-runs atomic manifest save + run-id regex tightening.
 * Covers PB-002 (atomic write, checkpoint) and PB-008 (regex tightening).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { saveRunManifest, checkpointRunManifest, generateRunId } from '../../lib/runtime-runs.js';

async function makeDir() {
  return await mkdtemp(join(tmpdir(), 'sdl-runtime-runs-'));
}

test('saveRunManifest writes valid JSON via atomic rename', async () => {
  const dir = await makeDir();
  const manifest = { run_id: 'run_X', outputs: [{ index: 0, status: 'ok' }] };
  await saveRunManifest(dir, manifest);
  const body = await readFile(join(dir, 'manifest.json'), 'utf-8');
  assert.deepEqual(JSON.parse(body), manifest);

  // No leftover tmp files.
  const entries = await readdir(dir);
  assert.ok(!entries.some(e => e.includes('.tmp-')), `no tmp leftover, got: ${entries.join(',')}`);
});

test('checkpointRunManifest stamps incremental + last_checkpoint_at', async () => {
  const dir = await makeDir();
  const manifest = { run_id: 'run_Y', outputs: [] };
  await checkpointRunManifest(dir, manifest);
  const body = JSON.parse(await readFile(join(dir, 'manifest.json'), 'utf-8'));
  assert.equal(body.incremental, true);
  assert.match(body.last_checkpoint_at, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(body.run_id, 'run_Y');
});

test('checkpointRunManifest does not corrupt existing manifest on repeated writes', async () => {
  const dir = await makeDir();
  for (let i = 0; i < 5; i++) {
    await checkpointRunManifest(dir, { run_id: 'run_Z', outputs: new Array(i + 1).fill({}) });
    const body = JSON.parse(await readFile(join(dir, 'manifest.json'), 'utf-8'));
    assert.equal(body.outputs.length, i + 1);
    assert.equal(body.incremental, true);
  }
});

test('generateRunId ignores stray suffixed directories (PB-008)', async () => {
  const dir = await makeDir();
  const today = new Date().toISOString().slice(0, 10);
  // Create one legit run_..._007 and one stray run_..._001_wip
  await mkdir(join(dir, `run_${today}_007`));
  await mkdir(join(dir, `run_${today}_001_wip`));
  await mkdir(join(dir, `run_${today}_abc`));
  const next = generateRunId(dir);
  assert.equal(next, `run_${today}_008`);
});

test('generateRunId returns 001 for empty dir', async () => {
  const dir = await makeDir();
  const today = new Date().toISOString().slice(0, 10);
  assert.equal(generateRunId(dir), `run_${today}_001`);
});
