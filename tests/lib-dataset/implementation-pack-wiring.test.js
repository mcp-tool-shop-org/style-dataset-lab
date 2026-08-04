/**
 * SDL-M10 wiring sanity for lib/implementation-packs.js.
 *
 * This module had zero prior test coverage — buildImplementationPack was
 * never exercised by any existing test. Confirms the atomic-claim refactor
 * (claimIdDir, shared with the other six SDL-M10 call sites) didn't break
 * the happy path, and that two back-to-back builds never collide.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  buildImplementationPack,
  loadImplementationPack,
  listImplementationPacks,
} from '../../lib/implementation-packs.js';
import { loadSplitPartition } from '../../lib/split.js';
import { createTrainingPackageProject } from './fixtures/make-training-package-project.js';

test('SDL-M10: buildImplementationPack works end-to-end after the atomic-claim refactor', async () => {
  const proj = await createTrainingPackageProject({ count: 4 });
  try {
    const result = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    assert.ok(result.implId);
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'implementations', result.implId, 'manifest.json')));

    const manifest = await loadImplementationPack(proj.projectRoot, result.implId);
    assert.equal(manifest.implementation_pack_id, result.implId);
    assert.equal(manifest.training_manifest_id, proj.manifestId);

    const list = await listImplementationPacks(proj.projectRoot);
    assert.ok(list.some(p => p.id === result.implId));
  } finally {
    proj.cleanup();
  }
});

test('SDL-M10: two back-to-back buildImplementationPack calls never collide (atomic claim wiring)', async () => {
  const proj = await createTrainingPackageProject({ count: 3 });
  try {
    const a = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    const b = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    assert.notEqual(a.implId, b.implId);
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'implementations', a.implId, 'manifest.json')));
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'implementations', b.implId, 'manifest.json')));
  } finally {
    proj.cleanup();
  }
});

// ─── F4 (HIGH): known-failures scan no longer aborts on one bad file ────

test('F4: one truncated/corrupt record file does not abort buildImplementationPack — RED branch driven explicitly', async () => {
  const proj = await createTrainingPackageProject({ count: 6 });
  try {
    // Corrupt a record that lands in the split's VAL partition specifically.
    // buildImplementationPack's OTHER two loops (prompt-examples,
    // subject-continuity) only ever read the test/train partitions — never
    // val — so this guarantees ONLY the known-failures scan (which walks
    // every file in records/ directly via readdir, independent of split
    // membership) ever touches the corrupted file. Picking a record that's
    // also in train/test would instead exercise loadRecord()'s own
    // unrelated, pre-existing re-throw-on-non-ENOENT behavior in those
    // other loops — a different code path than the one this finding is
    // about (lib/implementation-packs.js's bare JSON.parse in the
    // known-failures scan specifically).
    const valEntries = await loadSplitPartition(proj.projectRoot, proj.splitId, 'val');
    assert.ok(valEntries.length > 0, 'fixture must produce a non-empty val partition to isolate the corruption safely');
    const corruptedId = valEntries[0].record_id;
    const corruptedFile = `${corruptedId}.json`;
    await writeFile(join(proj.projectRoot, 'records', corruptedFile), '{ this is not valid json, truncated mid-w');

    // Must not throw — a single bad record file must never discard the
    // prompt-examples / subject-continuity work the other two loops in
    // this function already computed (everything is written to disk only
    // at the very end of buildImplementationPack).
    const result = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    assert.ok(result.implId);

    const manifest = await loadImplementationPack(proj.projectRoot, result.implId);
    assert.equal(manifest.counts.unreadable_records, 1);
    assert.equal(manifest.unreadable_records.length, 1);
    assert.equal(manifest.unreadable_records[0].file, corruptedFile);
    assert.equal(manifest.unreadable_records[0].record_id, corruptedId);
    assert.ok(manifest.unreadable_records[0].error, 'the JSON.parse error message must be preserved');

    // The prompt-examples loop's work (computed BEFORE the known-failures
    // scan reaches the corrupted file) must have actually landed on disk.
    assert.ok(result.prompts > 0, 'prompt examples computed by the earlier loop must survive to disk');
    const promptsRaw = await readFile(
      join(proj.projectRoot, 'training', 'implementations', result.implId, 'prompts.jsonl'), 'utf-8');
    assert.ok(promptsRaw.trim().length > 0);
  } finally {
    proj.cleanup();
  }
});

test('F4: unreadable_records ledger is empty when every record file is valid JSON — explicit PASS branch for contrast', async () => {
  const proj = await createTrainingPackageProject({ count: 4 });
  try {
    const result = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    const manifest = await loadImplementationPack(proj.projectRoot, result.implId);
    assert.equal(manifest.counts.unreadable_records, 0);
    assert.deepEqual(manifest.unreadable_records, []);
  } finally {
    proj.cleanup();
  }
});
