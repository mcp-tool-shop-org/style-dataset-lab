/**
 * Unit tests for SDL-H7 — unvalidated ids joined into paths.
 *
 * loadRun() (lib/runtime-runs.js), openBatchDirForResume()/loadBatchManifest()
 * (lib/batch-runs.js), and reingestSelection() (lib/reingest-selected.js) all
 * used to join a caller-supplied id straight into a path with only an
 * existsSync check. `--resume ../../../../some/dir/leftover` could open (and,
 * for batch resume, repeatedly overwrite via checkpointing) a manifest.json
 * OUTSIDE the project sandbox.
 *
 * Each test here plants a real file OUTSIDE the relevant project
 * subdirectory (runs/, batches/, selections/) and proves a traversal-shaped
 * id can no longer reach it — the call must reject before ever touching that
 * file, not merely fail to find something.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadRun } from '../../lib/runtime-runs.js';
import { openBatchDirForResume, loadBatchManifest } from '../../lib/batch-runs.js';
import { reingestSelection } from '../../lib/reingest-selected.js';

async function makeSandbox(prefix) {
  return await mkdtemp(join(tmpdir(), prefix));
}

// ─── loadRun ───────────────────────────────────────────────────────

test('loadRun rejects a traversal-shaped run id instead of reading outside runs/ (SDL-H7)', async () => {
  const root = await makeSandbox('sdl-idtrav-run-');
  try {
    await mkdir(join(root, 'runs'), { recursive: true });
    // Plant a "leaked" manifest OUTSIDE runs/, directly under the project
    // root, one hop up from where a traversal id would land.
    await mkdir(join(root, 'secret-outside-runs'), { recursive: true });
    await writeFile(
      join(root, 'secret-outside-runs', 'manifest.json'),
      JSON.stringify({ run_id: 'LEAKED', outputs: ['should-not-be-readable'] })
    );

    await assert.rejects(
      () => loadRun(root, '../secret-outside-runs'),
      (err) => err.code === 'RUN_NOT_FOUND'
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('loadRun still loads a real, well-shaped run id (no false positive)', async () => {
  const root = await makeSandbox('sdl-idtrav-run-ok-');
  try {
    const runDir = join(root, 'runs', 'run_2026-01-01_001');
    await mkdir(runDir, { recursive: true });
    await writeFile(join(runDir, 'manifest.json'), JSON.stringify({ run_id: 'run_2026-01-01_001', outputs: [] }));

    const manifest = await loadRun(root, 'run_2026-01-01_001');
    assert.equal(manifest.run_id, 'run_2026-01-01_001');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

// ─── openBatchDirForResume / loadBatchManifest ─────────────────────

test('openBatchDirForResume rejects a traversal-shaped batch id instead of reading outside batches/ (SDL-H7)', async () => {
  const root = await makeSandbox('sdl-idtrav-batch-');
  try {
    await mkdir(join(root, 'batches'), { recursive: true });
    await mkdir(join(root, 'secret-outside-batches'), { recursive: true });
    await writeFile(
      join(root, 'secret-outside-batches', 'manifest.json'),
      JSON.stringify({ batch_id: 'LEAKED', slots: [{ slot_id: 'x', status: 'ok' }] })
    );

    assert.throws(
      () => openBatchDirForResume(root, '../secret-outside-batches'),
      (err) => err.code === 'BATCH_NOT_FOUND'
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('loadBatchManifest rejects a traversal-shaped batch id instead of reading outside batches/ (SDL-H7)', async () => {
  const root = await makeSandbox('sdl-idtrav-batch2-');
  try {
    await mkdir(join(root, 'batches'), { recursive: true });
    await mkdir(join(root, 'secret-outside-batches2'), { recursive: true });
    await writeFile(
      join(root, 'secret-outside-batches2', 'manifest.json'),
      JSON.stringify({ batch_id: 'LEAKED' })
    );

    assert.throws(
      () => loadBatchManifest(root, '../secret-outside-batches2'),
      (err) => err.code === 'BATCH_NOT_FOUND'
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('openBatchDirForResume/loadBatchManifest still load a real, well-shaped batch id (no false positive)', async () => {
  const root = await makeSandbox('sdl-idtrav-batch-ok-');
  try {
    const batchDir = join(root, 'batches', 'batch_2026-01-01_001');
    await mkdir(batchDir, { recursive: true });
    await writeFile(
      join(batchDir, 'manifest.json'),
      JSON.stringify({ batch_id: 'batch_2026-01-01_001', slots: [{ slot_id: 'a', status: 'ok' }] })
    );

    const opened = openBatchDirForResume(root, 'batch_2026-01-01_001');
    assert.equal(opened.batchId, 'batch_2026-01-01_001');
    assert.equal(opened.priorResults.length, 1);

    const manifest = loadBatchManifest(root, 'batch_2026-01-01_001');
    assert.equal(manifest.batch_id, 'batch_2026-01-01_001');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

// The existing tests/lib-pipeline/batch-resume.test.js asserts
// `openBatchDirForResume(root, 'batch_does_not_exist')` throws
// BATCH_NOT_FOUND. That id has no separators/".." so it is not a traversal
// payload, but it also doesn't match the generator's date/seq shape — this
// documents that the id-shape check and the not-found check are designed to
// be indistinguishable to the caller (same code either way).
test('openBatchDirForResume: a malformed-but-non-traversing id reads the SAME BATCH_NOT_FOUND as missing (compat with existing shape check)', async () => {
  const root = await makeSandbox('sdl-idtrav-batch-shape-');
  try {
    await mkdir(join(root, 'batches'), { recursive: true });
    assert.throws(
      () => openBatchDirForResume(root, 'batch_does_not_exist'),
      (err) => err.code === 'BATCH_NOT_FOUND'
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

// ─── reingestSelection ───────────────────────────────────────────────

test('reingestSelection rejects a traversal-shaped selection id instead of reading outside selections/ (SDL-H7)', async () => {
  const root = await makeSandbox('sdl-idtrav-sel-');
  try {
    await mkdir(join(root, 'selections'), { recursive: true });
    const outsideSel = join(root, 'secret-outside-selections');
    await mkdir(join(outsideSel, 'chosen'), { recursive: true });
    await writeFile(
      join(outsideSel, 'manifest.json'),
      JSON.stringify({ selection_id: 'LEAKED', reingest_ready: true, items: [{ filename: 'x.png' }] })
    );

    await assert.rejects(
      () => reingestSelection({ projectRoot: root, projectId: 'p', selectionId: '../secret-outside-selections', dryRun: true }),
      (err) => err.code === 'SELECTION_NOT_FOUND'
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
