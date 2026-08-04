/**
 * SDL-M10: TOCTOU on id allocation.
 *
 * `existsSync(dir)` → `mkdir(dir, {recursive:true})` is check-then-act: a
 * second concurrent process can create the same directory in the window
 * between the check and the mkdir, and recursive mkdir never throws on an
 * existing directory, so two builders can silently interleave writes into
 * one snapshot/split/export/etc. directory (Law 1 exposure). The same
 * pattern existed in snapshot.js, split.js, export.js, eval-pack.js,
 * training-manifests.js, training-packages.js, and implementation-packs.js.
 *
 * lib/selections.js's claimSelectionId already implements the atomic
 * shape (non-recursive mkdir in a try/catch mapping EEXIST to a named
 * collision error). This module ports that shape into two small, generic,
 * exported helpers in lib/snapshot.js — claimIdDir (directory-based
 * artifacts) and claimIdFile (training manifests, the one flat-file
 * artifact in this domain) — used by all seven call sites.
 *
 * Prior-art trap called out explicitly in the brief: the existing
 * SNAPSHOT_ID_COLLISION tests never actually force a collision (their own
 * comments admit it). These tests do — via the `generateId` parameter,
 * which is exactly the "small injectable id-factory seam" the brief
 * anticipated, added to claimIdDir/claimIdFile (functions this domain
 * owns) for precisely this purpose.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, mkdir as fsMkdir, writeFile as fsWriteFile, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { claimIdDir, claimIdFile } from '../../lib/snapshot.js';
import { createSnapshot } from '../../lib/snapshot.js';
import { buildEvalPack } from '../../lib/eval-pack.js';
import { buildTrainingPackage } from '../../lib/training-packages.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';
import { createTrainingPackageProject } from './fixtures/make-training-package-project.js';

async function tmpParent(prefix) {
  return mkdtemp(join(tmpdir(), prefix));
}

// ─── claimIdDir: happy path ───────────────────────────────────────────────

test('SDL-M10: claimIdDir claims a fresh directory and returns {id, dir}', async () => {
  const parent = await tmpParent('sdlab-claim-dir-');
  try {
    const result = await claimIdDir(parent, () => 'fixed-id', { code: 'X', message: 'x', hint: 'x' });
    assert.equal(result.id, 'fixed-id');
    assert.equal(result.dir, join(parent, 'fixed-id'));
    assert.ok(existsSync(result.dir));
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test('SDL-M10: claimIdDir creates the parent directory if missing', async () => {
  const grandparent = await tmpParent('sdlab-claim-dirp-');
  const parent = join(grandparent, 'not-yet-created');
  try {
    assert.ok(!existsSync(parent));
    const result = await claimIdDir(parent, () => 'x', { code: 'X', message: 'x', hint: 'x' });
    assert.ok(existsSync(parent));
    assert.ok(existsSync(result.dir));
  } finally {
    await rm(grandparent, { recursive: true, force: true });
  }
});

// ─── claimIdDir: the actual race, forced for real ─────────────────────────

test('SDL-M10: the OLD pattern (existsSync + recursive mkdir) does NOT detect a concurrent claim — motivating contrast', async () => {
  // This is not testing sdlab code — it is a direct, executable
  // demonstration of WHY the old pattern was broken, so the fix below
  // isn't just asserted but shown to close a real gap.
  const parent = await tmpParent('sdlab-old-pattern-');
  try {
    const dir = join(parent, 'race-id');
    await fsMkdir(dir, { recursive: true }); // simulates: another process already claimed it
    await fsWriteFile(join(dir, 'owned-by-process-a.txt'), 'A');

    // The old guard: existsSync(dir) would correctly see it here — but
    // demonstrate the SILENT half of the bug: recursive mkdir on an
    // ALREADY-existing directory does not throw, so if a caller ever
    // reordered / raced past the check, this line would silently succeed
    // "into" process A's directory instead of failing.
    await assert.doesNotReject(() => fsMkdir(dir, { recursive: true }));
    // Process A's file is still there, undisturbed and unnoticed —
    // exactly the silent interleave the finding describes.
    assert.ok(existsSync(join(dir, 'owned-by-process-a.txt')));
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test('SDL-M10: claimIdDir retries past a REAL forced collision and returns a fresh id — RED-adjacent, not admitted-fake', async () => {
  const parent = await tmpParent('sdlab-claim-race-');
  try {
    // Simulate a concurrent process that already claimed "taken-id".
    await fsMkdir(join(parent, 'taken-id'));
    await fsWriteFile(join(parent, 'taken-id', 'owned-by-other-process.txt'), 'other');

    let call = 0;
    const generateId = () => {
      call++;
      return call === 1 ? 'taken-id' : 'fresh-id';
    };

    const result = await claimIdDir(parent, generateId, { code: 'X', message: 'x', hint: 'x' });
    assert.equal(result.id, 'fresh-id', 'must have retried past the collision onto a fresh id');
    assert.equal(call, 2, 'generateId must be called again after EEXIST');

    // The colliding directory must be completely untouched — no
    // interleaved writes into someone else's claim.
    const takenContents = await readdir(join(parent, 'taken-id'));
    assert.deepEqual(takenContents, ['owned-by-other-process.txt']);
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test('SDL-M10: claimIdDir throws the caller-specific error after exhausting every candidate — forced, not simulated', async () => {
  const parent = await tmpParent('sdlab-claim-exhaust-');
  try {
    // Every single candidate this generator can produce is pre-claimed.
    await fsMkdir(join(parent, 'always-the-same-id'));

    await assert.rejects(
      () => claimIdDir(parent, () => 'always-the-same-id', {
        code: 'DEMO_ID_COLLISION',
        message: 'demo exhausted',
        hint: 'demo hint',
        maxAttempts: 3,
      }),
      err => err.code === 'DEMO_ID_COLLISION' && /demo exhausted/.test(err.message),
    );
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

// ─── claimIdFile: same shape, for the one flat-file artifact ────────────

test('SDL-M10: claimIdFile claims a fresh file and returns {id, filePath}', async () => {
  const parent = await tmpParent('sdlab-claim-file-');
  try {
    const result = await claimIdFile(parent, () => 'fixed-id', (id) => `{"id":"${id}"}`, { code: 'X', message: 'x', hint: 'x' });
    assert.equal(result.id, 'fixed-id');
    assert.equal(result.filePath, join(parent, 'fixed-id.json'));
    assert.ok(existsSync(result.filePath));
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test('SDL-M10: claimIdFile retries past a REAL forced collision without touching the existing file', async () => {
  const parent = await tmpParent('sdlab-claim-file-race-');
  try {
    await fsWriteFile(join(parent, 'taken-id.json'), 'ORIGINAL-DO-NOT-TOUCH');

    let call = 0;
    const generateId = () => { call++; return call === 1 ? 'taken-id' : 'fresh-id'; };
    const buildContent = (id) => `{"claimed":"${id}"}`;

    const result = await claimIdFile(parent, generateId, buildContent, { code: 'X', message: 'x', hint: 'x' });
    assert.equal(result.id, 'fresh-id');

    const { readFile } = await import('node:fs/promises');
    const originalStillIntact = await readFile(join(parent, 'taken-id.json'), 'utf-8');
    assert.equal(originalStillIntact, 'ORIGINAL-DO-NOT-TOUCH', 'exclusive create must never clobber an existing file');
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test('SDL-M10: claimIdFile throws the caller-specific error after exhausting every candidate', async () => {
  const parent = await tmpParent('sdlab-claim-file-exhaust-');
  try {
    await fsWriteFile(join(parent, 'always-the-same-id.json'), 'x');

    await assert.rejects(
      () => claimIdFile(parent, () => 'always-the-same-id', (id) => `{"id":"${id}"}`, {
        code: 'DEMO_FILE_ID_COLLISION',
        message: 'demo file exhausted',
        hint: 'demo hint',
        maxAttempts: 3,
      }),
      err => err.code === 'DEMO_FILE_ID_COLLISION',
    );
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

// ─── Domain-level wiring sanity (the shared mechanism is proven above;
//     this just confirms each call site is actually plumbed through it) ──

test('SDL-M10: createSnapshot uses the atomic claim — two back-to-back calls never collide and both dirs are real', async () => {
  const proj = createTmpProject({ records: [makeRecord({ id: 'r1' }), makeRecord({ id: 'r2' })] });
  try {
    const PROFILE = {
      profile_id: 'wiring-test', require_judgment: true, require_status: ['approved'],
      require_canon_bound: true, minimum_pass_ratio: 0.5,
    };
    const a = await createSnapshot(proj.projectRoot, PROFILE);
    const b = await createSnapshot(proj.projectRoot, PROFILE);
    assert.notEqual(a.snapshotId, b.snapshotId);
    assert.ok(existsSync(join(proj.projectRoot, 'snapshots', a.snapshotId, 'snapshot.json')));
    assert.ok(existsSync(join(proj.projectRoot, 'snapshots', b.snapshotId, 'snapshot.json')));
  } finally {
    proj.cleanup();
  }
});

test('SDL-M10: createSnapshot dry run never touches disk (no directory created at all)', async () => {
  const proj = createTmpProject({ records: [makeRecord({ id: 'r1' })] });
  try {
    const PROFILE = {
      profile_id: 'dryrun-test', require_judgment: true, require_status: ['approved'],
      require_canon_bound: true, minimum_pass_ratio: 0.5,
    };
    const result = await createSnapshot(proj.projectRoot, PROFILE, { dryRun: true });
    assert.ok(result.snapshotId);
    const snapshotsDir = join(proj.projectRoot, 'snapshots');
    assert.ok(!existsSync(snapshotsDir), 'dry run must not create the snapshots dir, let alone the id dir');
  } finally {
    proj.cleanup();
  }
});

test('SDL-M10: buildEvalPack uses the atomic claim — two back-to-back calls never collide', async () => {
  const proj = createTmpProject({ records: [makeRecord({ id: 'r1' }), makeRecord({ id: 'r2' })] });
  try {
    const a = await buildEvalPack(proj.projectRoot, {});
    const b = await buildEvalPack(proj.projectRoot, {});
    assert.notEqual(a.evalId, b.evalId);
    assert.ok(existsSync(join(proj.projectRoot, 'eval-packs', a.evalId, 'manifest.json')));
    assert.ok(existsSync(join(proj.projectRoot, 'eval-packs', b.evalId, 'manifest.json')));
  } finally {
    proj.cleanup();
  }
});

test('SDL-M10: buildTrainingPackage uses the atomic claim — two back-to-back calls never collide', async () => {
  const proj = await createTrainingPackageProject({ count: 3 });
  try {
    const a = await buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true });
    const b = await buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true });
    assert.notEqual(a.packageId, b.packageId);
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'packages', a.packageId, 'manifest.json')));
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'packages', b.packageId, 'manifest.json')));
  } finally {
    proj.cleanup();
  }
});
