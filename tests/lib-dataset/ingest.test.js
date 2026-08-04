/**
 * lib/ingest.js — bringing pre-existing images into the pipeline as bare,
 * uncurated candidate records.
 *
 * Before this module, there was no CLI path to get an image that wasn't
 * produced by `sdlab generate`/`run generate`/`batch generate` into the
 * project: `sdlab reingest generated` requires a trained LoRA's training
 * manifest, and `sdlab reingest selected` requires a selection id only the
 * production loop can mint. These tests hold `ingestDirectory` to the
 * non-negotiables the feature was built against:
 *   - never fabricates a judgment, score, or caption (judgment: null, and
 *     no invented field at all)
 *   - provenance.source is honestly 'external', distinguishable from a
 *     'generated' record
 *   - --wave enrichment is additive and honest — known when matched,
 *     explicitly "unknown" (never guessed) when not
 *   - id derivation rejects unsafe filenames (SDL-H5 allowlist) without
 *     aborting the rest of the batch
 *   - --dry-run is genuinely side-effect-free
 *   - idempotent: re-running skips, never duplicates or clobbers
 *   - crash-safe: atomic temp+rename for both the record and the image copy
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ingestDirectory, loadWaveIndex, loadReceiptsIndex } from '../../lib/ingest.js';
import { createTmpProject } from './fixtures/make-project.js';

async function makeSourceDir(prefix, files) {
  const dir = await mkdtemp(join(tmpdir(), prefix));
  for (const [name, content] of Object.entries(files)) {
    await writeFile(join(dir, name), content ?? 'fake-image-bytes');
  }
  return dir;
}

// ─── Basic ingest: bare, honest, uncurated records ──────────────────

test('ingestDirectory creates bare candidate records: judgment:null, canon:null, provenance.source:"external"', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-basic-', { 'quay_01.png': 'a', 'quay_02.jpg': 'b' });
  try {
    const res = await ingestDirectory(proj.projectRoot, src);
    assert.deepEqual(res.created.sort(), ['quay_01', 'quay_02']);
    assert.deepEqual(res.skipped, []);
    assert.deepEqual(res.rejected, []);

    const record = JSON.parse(await readFile(join(proj.projectRoot, 'records', 'quay_01.json'), 'utf-8'));
    assert.equal(record.id, 'quay_01');
    assert.equal(record.judgment, null);
    assert.equal(record.canon, null);
    assert.equal(record.provenance.source, 'external');
    assert.equal(record.asset_path, 'outputs/candidates/quay_01.png');
    assert.ok(record.provenance.ingested_at, 'ingested_at must be stamped');
    assert.equal(record.provenance.generation_provenance_known, false);
    assert.match(record.provenance.provenance_note, /No --wave file supplied/);

    assert.ok(existsSync(join(proj.projectRoot, 'outputs', 'candidates', 'quay_01.png')));
    assert.ok(existsSync(join(proj.projectRoot, 'outputs', 'candidates', 'quay_02.jpg')));
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

test('ingestDirectory never invents a judgment, score, or caption', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-honest-', { 'a.png': 'x' });
  try {
    await ingestDirectory(proj.projectRoot, src);
    const record = JSON.parse(await readFile(join(proj.projectRoot, 'records', 'a.json'), 'utf-8'));
    assert.equal(record.judgment, null);
    assert.equal('caption' in record, false, 'no caption field must be synthesized');
    assert.equal('score' in record, false, 'no score field must be synthesized');
    assert.equal('criteria_scores' in record, false);
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

// ─── Idempotency ─────────────────────────────────────────────────────

test('ingestDirectory is idempotent: re-running skips existing records instead of duplicating or clobbering', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-idem-', { 'a.png': 'original-bytes' });
  try {
    const first = await ingestDirectory(proj.projectRoot, src);
    assert.deepEqual(first.created, ['a']);
    assert.deepEqual(first.skipped, []);

    const beforeRecord = await readFile(join(proj.projectRoot, 'records', 'a.json'), 'utf-8');

    const second = await ingestDirectory(proj.projectRoot, src);
    assert.deepEqual(second.created, [], 'nothing new should be created on the second pass');
    assert.deepEqual(second.skipped, ['a'], 'the skip must be reported, not merely counted');

    const afterRecord = await readFile(join(proj.projectRoot, 'records', 'a.json'), 'utf-8');
    assert.equal(afterRecord, beforeRecord, 'record must be byte-identical after a no-op re-run (never clobbered)');
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

// ─── --dry-run is genuinely side-effect-free (SDL-M11 discipline) ───

test('ingestDirectory --dry-run creates no directories, copies no images, writes no records', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-dry-', { 'a.png': 'x', 'b.png': 'y' });
  try {
    const res = await ingestDirectory(proj.projectRoot, src, { dryRun: true });
    assert.deepEqual(res.created.sort(), ['a', 'b'], 'dry-run still reports what WOULD be created');

    assert.equal(existsSync(join(proj.projectRoot, 'outputs')), false, 'dry-run must not create outputs/candidates');
    assert.equal(existsSync(join(proj.projectRoot, 'records', 'a.json')), false, 'dry-run must not write a.json');
    assert.equal(existsSync(join(proj.projectRoot, 'records', 'b.json')), false, 'dry-run must not write b.json');
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

test('ingestDirectory --dry-run does not even create the records/ directory when it does not already exist', async () => {
  const proj = createTmpProject();
  // createTmpProject() already makes records/ — remove it to prove dry-run
  // truly never mkdir's it back, matching the SDL-M11 fixtures' pattern of
  // asserting on a directory that does not yet exist.
  await rm(join(proj.projectRoot, 'records'), { recursive: true, force: true });
  const src = await makeSourceDir('sdlab-ingest-dry-nodir-', { 'a.png': 'x' });
  try {
    assert.equal(existsSync(join(proj.projectRoot, 'records')), false, 'fixture setup error');
    await ingestDirectory(proj.projectRoot, src, { dryRun: true });
    assert.equal(existsSync(join(proj.projectRoot, 'records')), false, 'dry-run created records/');
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

// ─── Id safety (SDL-H5 allowlist, lib/export.js's assertSafeId) ─────

test('ingestDirectory rejects a filename that produces an unsafe id and keeps ingesting the rest of the directory', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-unsafe-', {
    'good_one.png': 'a',
    'evil name with spaces.png': 'b',
    'good_two.png': 'c',
  });
  try {
    const res = await ingestDirectory(proj.projectRoot, src);
    assert.deepEqual(res.created.sort(), ['good_one', 'good_two'], 'good files must still be ingested');
    assert.equal(res.rejected.length, 1);
    assert.equal(res.rejected[0].file, 'evil name with spaces.png');
    assert.equal(res.rejected[0].reason.includes('evil name with spaces'), true);

    // Never even attempted: no record, no copied image landed for it.
    const recordFiles = await readdir(join(proj.projectRoot, 'records'));
    assert.ok(!recordFiles.some((f) => f.includes('evil')), 'an unsafe id must never reach a record filename');
    const candidateFiles = await readdir(join(proj.projectRoot, 'outputs', 'candidates'));
    assert.ok(!candidateFiles.some((f) => f.includes('evil')), 'an unsafe id must never reach a copied filename');
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

test('ingestDirectory rejects a realistic messy filename (parentheses + space, e.g. a Downloads-folder duplicate) via the same allowlist as lib/export.js', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-parens-', {});
  await writeFile(join(src, 'IMG (1).png'), 'x');
  try {
    const res = await ingestDirectory(proj.projectRoot, src);
    assert.equal(res.created.length, 0);
    assert.equal(res.rejected.length, 1);
    assert.equal(res.rejected[0].file, 'IMG (1).png');
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

// ─── --wave enrichment: honest when matched, honest when not ────────

test('ingestDirectory attaches real provenance from a matching --wave entry, and stays honest for an unmatched one', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-wave-', { 'w2_r04_crane_tower.png': 'x', 'unrelated.png': 'y' });
  const waveDir = join(proj.projectRoot, 'inputs', 'prompts');
  await mkdir(waveDir, { recursive: true });
  const wavePath = join(waveDir, 'wave-v2.json');
  await writeFile(
    wavePath,
    JSON.stringify({
      formula_ref: 'formula.json',
      items: [
        { id: 'w2_r04_crane_tower', seed: 730404, preamble: 'ctl', neg: 'ctl', subject: 'the great harbour crane' },
      ],
    }),
  );
  try {
    const res = await ingestDirectory(proj.projectRoot, src, { wavePath });
    assert.deepEqual(res.created.sort(), ['unrelated', 'w2_r04_crane_tower']);

    const matched = JSON.parse(
      await readFile(join(proj.projectRoot, 'records', 'w2_r04_crane_tower.json'), 'utf-8'),
    );
    assert.equal(matched.provenance.generation_provenance_known, true);
    assert.equal(matched.provenance.seed, 730404);
    assert.equal(matched.provenance.prompt, 'the great harbour crane');
    assert.equal(matched.provenance.preamble_ref, 'ctl');
    assert.equal(matched.provenance.negative_ref, 'ctl');
    assert.equal(matched.provenance.formula_ref, 'formula.json');
    assert.match(matched.provenance.provenance_note, /not literal prompt\/negative text/);
    assert.equal(matched.provenance.wave_file, 'inputs/prompts/wave-v2.json');

    // No entry for THIS id in the wave — must stay honestly unknown, never
    // guessed or interpolated from the matched sibling above.
    const unmatched = JSON.parse(await readFile(join(proj.projectRoot, 'records', 'unrelated.json'), 'utf-8'));
    assert.equal(unmatched.provenance.generation_provenance_known, false);
    assert.equal('seed' in unmatched.provenance, false);
    assert.equal('prompt' in unmatched.provenance, false);
    assert.match(unmatched.provenance.provenance_note, /No entry for this id/);
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

test('ingestDirectory --wave pointing at a missing file throws instead of silently ignoring the flag', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-wave-missing-', { 'a.png': 'x' });
  try {
    await assert.rejects(
      () => ingestDirectory(proj.projectRoot, src, { wavePath: join(proj.projectRoot, 'nope.json') }),
      (err) => err.code === 'INPUT_WAVE_NOT_FOUND',
    );
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

test('loadWaveIndex falls back to a "subjects" array when "items" is absent (the sdlab-generate pack shape)', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-ingest-wave-subjects-'));
  try {
    const path = join(dir, 'example-wave.json');
    await writeFile(path, JSON.stringify({ wave: 'wave1', subjects: [{ id: 'char_hero', prompt: 'a hero' }] }));
    const { index, waveName } = await loadWaveIndex(path);
    assert.equal(waveName, 'wave1');
    assert.equal(index.get('char_hero').prompt, 'a hero');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadWaveIndex returns an empty index when no wavePath is given (--wave is opt-in)', async () => {
  const { index, formulaRef, waveName } = await loadWaveIndex(null);
  assert.equal(index.size, 0);
  assert.equal(formulaRef, null);
  assert.equal(waveName, null);
});

// ─── receipts.jsonl auto-discovery ───────────────────────────────────

test('ingestDirectory attaches prompt_id/seconds/status from a sibling receipts.jsonl, independent of --wave', async () => {
  const proj = createTmpProject();
  const src = join(proj.projectRoot, 'inbox', 'generated', 'batch1');
  await mkdir(src, { recursive: true });
  await writeFile(join(src, 'w2_001.png'), 'x');
  await writeFile(
    join(src, 'receipts.jsonl'),
    JSON.stringify({ id: 'w2_001', status: 'ok', prompt_id: 'be246bf6-55b6', seed: 730501, secs: 21 }) + '\n',
  );
  try {
    const res = await ingestDirectory(proj.projectRoot, src);
    assert.equal(res.receiptsFile, 'inbox/generated/batch1/receipts.jsonl');

    const record = JSON.parse(await readFile(join(proj.projectRoot, 'records', 'w2_001.json'), 'utf-8'));
    assert.equal(record.provenance.generation_provenance_known, true);
    assert.equal(record.provenance.prompt_id, 'be246bf6-55b6');
    assert.equal(record.provenance.seed, 730501);
    assert.equal(record.provenance.generation_seconds, 21);
    assert.equal(record.provenance.receipt_status, 'ok');
    assert.equal(record.provenance.receipts_file, 'inbox/generated/batch1/receipts.jsonl');
    // No --wave was given at all for this run — prompt must stay absent.
    assert.equal('prompt' in record.provenance, false);
  } finally {
    proj.cleanup();
  }
});

test('loadReceiptsIndex tolerates one malformed line without losing the other valid receipts', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-ingest-receipts-bad-'));
  try {
    const path = join(dir, 'receipts.jsonl');
    await writeFile(
      path,
      [
        JSON.stringify({ id: 'good_1', status: 'ok', secs: 10 }),
        'not-json-at-all{{{',
        JSON.stringify({ id: 'good_2', status: 'ok', secs: 20 }),
      ].join('\n') + '\n',
    );

    const index = await loadReceiptsIndex(path);
    assert.equal(index.size, 2, 'the one bad line must not blank out the two good ones');
    assert.equal(index.get('good_1').secs, 10);
    assert.equal(index.get('good_2').secs, 20);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadReceiptsIndex returns an empty Map when the file does not exist (best-effort, not fatal)', async () => {
  const index = await loadReceiptsIndex(join(tmpdir(), 'sdlab-does-not-exist-receipts.jsonl'));
  assert.equal(index.size, 0);
});

// ─── Crash safety: atomic temp+rename for both record and image copy ─

test('a successful ingest leaves no .tmp- leftover files behind (atomic write via temp+rename)', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-atomic-', { 'a.png': 'x' });
  try {
    await ingestDirectory(proj.projectRoot, src);
    const recordEntries = await readdir(join(proj.projectRoot, 'records'));
    assert.ok(!recordEntries.some((f) => f.includes('.tmp-')), `no tmp leftover in records/, got: ${recordEntries.join(',')}`);
    const candidateEntries = await readdir(join(proj.projectRoot, 'outputs', 'candidates'));
    assert.ok(
      !candidateEntries.some((f) => f.includes('.tmp-')),
      `no tmp leftover in outputs/candidates/, got: ${candidateEntries.join(',')}`,
    );
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

test('a leftover .tmp- file from a simulated crash does not block a later ingest, and is never mistaken for the finished record', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-crash-', { 'a.png': 'x' });
  try {
    // Simulate a process killed mid-write on a PRIOR attempt: a temp file
    // exists, but the final record path does not — this is exactly the
    // state a killed atomicWriteFile() leaves behind (temp written,
    // rename never happened).
    await writeFile(join(proj.projectRoot, 'records', 'a.json.tmp-99999-123'), '{truncated');
    assert.equal(existsSync(join(proj.projectRoot, 'records', 'a.json')), false, 'fixture setup error');

    const res = await ingestDirectory(proj.projectRoot, src);
    assert.deepEqual(res.created, ['a'], 'the killed-process leftover must not be mistaken for "already done"');

    const record = JSON.parse(await readFile(join(proj.projectRoot, 'records', 'a.json'), 'utf-8'));
    assert.equal(record.id, 'a');
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});

// ─── Misc ─────────────────────────────────────────────────────────────

test('ingestDirectory throws a structured error for a source directory that does not exist', async () => {
  const proj = createTmpProject();
  try {
    await assert.rejects(
      () => ingestDirectory(proj.projectRoot, join(proj.projectRoot, 'does-not-exist')),
      (err) => err.code === 'INPUT_SOURCE_NOT_FOUND',
    );
  } finally {
    proj.cleanup();
  }
});

test('ingestDirectory ignores non-image files in the source directory', async () => {
  const proj = createTmpProject();
  const src = await makeSourceDir('sdlab-ingest-nonimage-', {
    'a.png': 'x',
    'notes.txt': 'not an image',
    'metadata.json': '{}',
  });
  try {
    const res = await ingestDirectory(proj.projectRoot, src);
    assert.deepEqual(res.created, ['a']);
  } finally {
    proj.cleanup();
    await rm(src, { recursive: true, force: true });
  }
});
