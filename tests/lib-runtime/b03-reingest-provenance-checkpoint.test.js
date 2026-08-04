/**
 * Unit tests for B03 in lib/reingest-selected.js.
 *
 * `provenanceLines` used to accumulate in memory and get written ONCE at
 * the end with a full-overwrite writeFile(). Items whose record already
 * existed (the `existsSync(recordPath)` early `continue`) never pushed a
 * provenance line — in that run OR any future rerun, because the skip
 * branch returned before `prov` was ever computed.
 *
 * Two concrete, deterministic failure modes this produces (both
 * reproduced below without needing to fake a real process crash):
 *
 *   1. A record that exists on disk with NO corresponding provenance.jsonl
 *      entry (e.g. from an interrupted prior run) stays that way forever —
 *      every subsequent rerun skips it via existsSync and never backfills.
 *   2. Worse: because the final write was a full OVERWRITE of only the
 *      CURRENT call's in-memory accumulator (not an append, not seeded
 *      from what's already on disk), a second partial call could actively
 *      ERASE provenance lines a previous call had already written for
 *      items that get skipped this time around.
 *
 * The fix: append each provenance line immediately after its record write
 * (checkpointing, like lib/batch-runs.js's per-slot manifest checkpoint),
 * seeded from whatever is already on disk, and backfill a line for
 * skipped items instead of dropping it.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { reingestSelection } from '../../lib/reingest-selected.js';

async function makeProjectWithRun({ items }) {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b03-'));
  const runId = 'run_2026-01-01_001';
  const selectionId = 'selection_2026-01-01_001';

  await mkdir(join(projectRoot, 'runs', runId), { recursive: true });
  await writeFile(
    join(projectRoot, 'runs', runId, 'manifest.json'),
    JSON.stringify({
      run_id: runId,
      brief_id: 'brief_1',
      workflow_template_id: 'portrait_set',
      created_at: '2026-01-01T00:00:00.000Z',
      outputs: items.map((it) => ({ filename: it.filename, seed: it.seed })),
    }),
  );

  const selectionDir = join(projectRoot, 'selections', selectionId);
  await mkdir(join(selectionDir, 'chosen'), { recursive: true });
  for (const it of items) {
    await writeFile(join(selectionDir, 'chosen', it.filename), Buffer.from([1, 2, 3, 4]));
  }
  await writeFile(
    join(selectionDir, 'manifest.json'),
    JSON.stringify({
      selection_id: selectionId,
      project_id: 'p1',
      source_type: 'run',
      source_id: runId,
      workflow_id: 'portrait_set',
      created_at: '2026-01-01T00:00:00.000Z',
      items,
      reingest_ready: true,
    }),
  );

  return { projectRoot, selectionId, selectionDir };
}

function readProvenanceLines(selectionDir) {
  const path = join(selectionDir, 'provenance.jsonl');
  if (!existsSync(path)) return null;
  return readFileSync(path, 'utf-8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l));
}

// ─── 1. Backfill: a record that exists with no provenance entry ──────

test('reingestSelection backfills a provenance line for a record that already exists on disk with none (B03)', async () => {
  const items = [{ slot_or_output: '001.png', filename: 'sel_001.png', seed: 111, reason: 'selected', tags: [] }];
  const { projectRoot, selectionId, selectionDir } = await makeProjectWithRun({ items });
  try {
    // Simulate "an earlier, interrupted run already wrote this record but
    // crashed before appending its provenance line" — pre-create the
    // record by hand, and make sure NO provenance.jsonl exists at all.
    const recordId = `gen_${selectionId}_001`;
    await mkdir(join(projectRoot, 'records'), { recursive: true });
    await writeFile(
      join(projectRoot, 'records', `${recordId}.json`),
      JSON.stringify({ id: recordId, schema_version: '2.2.0' }),
    );
    assert.equal(existsSync(join(selectionDir, 'provenance.jsonl')), false, 'sanity: no provenance.jsonl yet');

    const result = await reingestSelection({ projectRoot, projectId: 'p1', selectionId, dryRun: false });

    assert.deepEqual(result.created, [], 'the record already existed — must not be recreated');
    assert.deepEqual(result.skipped, [recordId]);

    const lines = readProvenanceLines(selectionDir);
    assert.ok(lines, 'expected provenance.jsonl to now exist — the defect is that it never got created for a skipped item, in this run or any future one');
    assert.equal(lines.length, 1);
    assert.equal(lines[0].record_id, recordId);
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

// ─── 2. No erasure: a second partial call must not destroy prior lines ─

test('reingestSelection does not erase previously-written provenance lines on a second (resuming) call (B03)', async () => {
  const items = [
    { slot_or_output: '001.png', filename: 'sel_001.png', seed: 111, reason: 'selected', tags: [] },
    { slot_or_output: '002.png', filename: 'sel_002.png', seed: 222, reason: 'selected', tags: [] },
    { slot_or_output: '003.png', filename: 'sel_003.png', seed: 333, reason: 'selected', tags: [] },
  ];
  const { projectRoot, selectionId, selectionDir } = await makeProjectWithRun({ items });
  try {
    // First "run": only item 1 is in the selection (simulating a selection
    // that, at the time, only had one approved item).
    await writeFile(
      join(selectionDir, 'manifest.json'),
      JSON.stringify({
        selection_id: selectionId, project_id: 'p1', source_type: 'run', source_id: 'run_2026-01-01_001',
        workflow_id: 'portrait_set', created_at: '2026-01-01T00:00:00.000Z',
        items: [items[0]], reingest_ready: true,
      }),
    );
    const first = await reingestSelection({ projectRoot, projectId: 'p1', selectionId, dryRun: false });
    assert.equal(first.created.length, 1);
    let lines = readProvenanceLines(selectionDir);
    assert.equal(lines.length, 1, 'first call must persist its one provenance line');
    const firstRecordId = lines[0].record_id;

    // "Resume": the selection is now the full 3-item set. Item 1 already
    // has a record + provenance line; items 2 and 3 are new.
    await writeFile(
      join(selectionDir, 'manifest.json'),
      JSON.stringify({
        selection_id: selectionId, project_id: 'p1', source_type: 'run', source_id: 'run_2026-01-01_001',
        workflow_id: 'portrait_set', created_at: '2026-01-01T00:00:00.000Z',
        items, reingest_ready: true,
      }),
    );
    const second = await reingestSelection({ projectRoot, projectId: 'p1', selectionId, dryRun: false });
    assert.equal(second.created.length, 2, 'items 2 and 3 are newly created');
    assert.equal(second.skipped.length, 1, 'item 1 is skipped (already exists)');

    lines = readProvenanceLines(selectionDir);
    assert.equal(lines.length, 3, 'all three records must have a provenance line — item 1\'s line from the FIRST call must survive, not be erased by the second call\'s overwrite');
    const ids = lines.map((l) => l.record_id);
    assert.ok(ids.includes(firstRecordId), 'item 1\'s original provenance line must still be present');
    assert.equal(new Set(ids).size, 3, 'no duplicate record_id lines');
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

// ─── 3. Baseline: a normal, uninterrupted run still works end to end ──

test('reingestSelection produces one correct provenance line per created record in a normal run (no false positive)', async () => {
  const items = [
    { slot_or_output: '001.png', filename: 'sel_001.png', seed: 111, reason: 'selected', tags: [] },
    { slot_or_output: '002.png', filename: 'sel_002.png', seed: 222, reason: 'selected', tags: [] },
  ];
  const { projectRoot, selectionId, selectionDir } = await makeProjectWithRun({ items });
  try {
    const result = await reingestSelection({ projectRoot, projectId: 'p1', selectionId, dryRun: false });
    assert.equal(result.created.length, 2);
    assert.equal(result.skipped.length, 0);

    const lines = readProvenanceLines(selectionDir);
    assert.equal(lines.length, 2);
    for (const line of lines) {
      assert.equal(line.run_id, 'run_2026-01-01_001');
      assert.ok(line.record_id.startsWith(`gen_${selectionId}_`));
    }
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

// ─── 4. dryRun still writes nothing (unchanged contract) ──────────────

test('reingestSelection with dryRun writes neither records nor provenance.jsonl (unchanged contract)', async () => {
  const items = [{ slot_or_output: '001.png', filename: 'sel_001.png', seed: 111, reason: 'selected', tags: [] }];
  const { projectRoot, selectionId, selectionDir } = await makeProjectWithRun({ items });
  try {
    const result = await reingestSelection({ projectRoot, projectId: 'p1', selectionId, dryRun: true });
    assert.equal(result.created.length, 1, 'dry run still reports what WOULD be created');
    assert.equal(existsSync(join(selectionDir, 'provenance.jsonl')), false);
    assert.equal(existsSync(join(projectRoot, 'records', `gen_${selectionId}_001.json`)), false);
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});
