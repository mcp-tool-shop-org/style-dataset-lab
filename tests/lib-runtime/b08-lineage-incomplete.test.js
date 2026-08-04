/**
 * Unit tests for B08 in lib/generated-provenance.js.
 *
 * The subject_id/parent_brief_id fallback wrapped a brief read in
 * `try { } catch { /* skip *\/ }` with no logging — the module didn't
 * import lib/log.js. A missing OR mid-write (concurrently-being-written,
 * so JSON.parse throws) brief silently yielded provenance with no
 * lineage, unlinking the record from subject grouping in a pipeline whose
 * stated purpose is source-attested canon.
 *
 * Fix: warn() the brief path on failure and set an explicit
 * `lineage_incomplete: true` marker rather than omitting fields silently.
 * Critically, a brief that legitimately has no subject_id (read fine, just
 * doesn't carry that field) must NOT be flagged incomplete — that's a
 * normal state, not a failure to determine lineage.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildGeneratedProvenance } from '../../lib/generated-provenance.js';

function captureStderr(fn) {
  const orig = console.error;
  const lines = [];
  console.error = (...a) => lines.push(a.join(' '));
  try {
    return { result: fn(), lines };
  } finally {
    console.error = orig;
  }
}

function makeRunManifest(overrides = {}) {
  return {
    run_id: 'run_2026-01-01_001',
    brief_id: 'brief_1',
    workflow_template_id: 'portrait_set',
    adapter_target: 'comfyui',
    created_at: '2026-01-01T00:00:00.000Z',
    outputs: [{ filename: 'sel_001.png', seed: 111 }],
    ...overrides,
  };
}

const ITEM = { filename: 'sel_001.png' };

test('buildGeneratedProvenance warns and sets lineage_incomplete when the brief file is missing entirely (B08)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b08-missing-'));
  try {
    await mkdir(join(projectRoot, 'briefs'), { recursive: true }); // dir exists, file does not
    const runManifest = makeRunManifest();

    const { result: prov, lines } = captureStderr(() =>
      buildGeneratedProvenance({ sourceType: 'run', sourceId: runManifest.run_id, runManifest, item: ITEM, projectRoot }),
    );

    assert.equal(prov.lineage_incomplete, true, 'a missing brief means lineage is genuinely unknown, not merely absent');
    assert.equal(prov.subject_id, undefined);
    assert.equal(lines.length, 1);
    assert.match(lines[0], /brief_1\.json/, 'expected the warning to name the brief path');
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

test('buildGeneratedProvenance warns and sets lineage_incomplete when the brief exists but is unreadable/mid-write (B08)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b08-corrupt-'));
  try {
    await mkdir(join(projectRoot, 'briefs'), { recursive: true });
    // Simulates a concurrent writer that hasn't finished — the file exists
    // but is not valid JSON yet.
    await writeFile(join(projectRoot, 'briefs', 'brief_1.json'), '{ "subject_id": "her', 'utf-8');
    const runManifest = makeRunManifest();

    const { result: prov, lines } = captureStderr(() =>
      buildGeneratedProvenance({ sourceType: 'run', sourceId: runManifest.run_id, runManifest, item: ITEM, projectRoot }),
    );

    assert.equal(prov.lineage_incomplete, true);
    assert.equal(prov.subject_id, undefined);
    assert.equal(lines.length, 1);
    assert.match(lines[0], /brief_1\.json/);
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

test('buildGeneratedProvenance does NOT set lineage_incomplete when the brief reads fine but legitimately has no subject_id (B08 — no false positive)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b08-nosubject-'));
  try {
    await mkdir(join(projectRoot, 'briefs'), { recursive: true });
    await writeFile(join(projectRoot, 'briefs', 'brief_1.json'), JSON.stringify({ prompt: 'a scene, no subject' }));
    const runManifest = makeRunManifest();

    const { result: prov, lines } = captureStderr(() =>
      buildGeneratedProvenance({ sourceType: 'run', sourceId: runManifest.run_id, runManifest, item: ITEM, projectRoot }),
    );

    assert.equal(prov.lineage_incomplete, undefined, 'a brief with no subject_id is a normal state, not an incomplete-lineage failure');
    assert.equal(prov.subject_id, undefined);
    assert.equal(lines.length, 0, 'must not warn when the brief was read successfully');
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

test('buildGeneratedProvenance still resolves subject_id/parent_brief_id normally from a healthy brief (no false positive)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b08-healthy-'));
  try {
    await mkdir(join(projectRoot, 'briefs'), { recursive: true });
    await writeFile(
      join(projectRoot, 'briefs', 'brief_1.json'),
      JSON.stringify({ subject_id: 'heracles', parent_brief_id: 'brief_0' }),
    );
    const runManifest = makeRunManifest();

    const { result: prov, lines } = captureStderr(() =>
      buildGeneratedProvenance({ sourceType: 'run', sourceId: runManifest.run_id, runManifest, item: ITEM, projectRoot }),
    );

    assert.equal(prov.subject_id, 'heracles');
    assert.equal(prov.parent_brief_id, 'brief_0');
    assert.equal(prov.lineage_incomplete, undefined);
    assert.equal(lines.length, 0);
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

test('buildGeneratedProvenance does not even look at the brief when batchManifest already supplies subject_id (unchanged behavior)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b08-batch-'));
  try {
    // No briefs/ dir at all — proves the brief path is never consulted.
    const runManifest = makeRunManifest();
    const batchManifest = { subject_id: 'from-batch' };

    const { result: prov, lines } = captureStderr(() =>
      buildGeneratedProvenance({ sourceType: 'batch', sourceId: 'batch_1', runManifest, batchManifest, item: ITEM, projectRoot }),
    );

    assert.equal(prov.subject_id, 'from-batch');
    assert.equal(prov.lineage_incomplete, undefined);
    assert.equal(lines.length, 0);
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});
