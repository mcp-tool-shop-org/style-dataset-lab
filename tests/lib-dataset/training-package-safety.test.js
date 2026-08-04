/**
 * SDL-C5 / SDL-H5 / SDL-H6: training-package Windows guard, per-row
 * failure visibility, and id/path safety.
 *
 * SDL-C5: buildTrainingPackage had no platform check before dispatching to
 * an adapter, while export.js refuses symlink mode on Windows
 * (SYMLINK_UNSUPPORTED_WINDOWS). Each adapter's bare `catch { continue; }`
 * meant a Windows build without Developer Mode silently produced an empty
 * package (imageCount 0, empty metadata) and still exited 0.
 *
 * SDL-H5: record.id / row.entity_id became part of a DESTINATION filename
 * with no validation, unlike the source asset_path (which export.js does
 * validate). SDL-H6: the three adapters checked only existsSync on
 * asset_path, no traversal/absolute-path rejection — export.js has this
 * guard (D-007) but it was never ported.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  buildTrainingPackage,
  loadTrainingPackage,
} from '../../lib/training-packages.js';
import { buildExport, assertSafeAssetPath, assertSafeId, SAFE_ID_RE } from '../../lib/export.js';
import { createSnapshot } from '../../lib/snapshot.js';
import { createSplit } from '../../lib/split.js';
import { buildPackage as buildGenericPackage } from '../../lib/adapters/generic-image-caption.js';
import { buildPackage as buildDiffusersPackage } from '../../lib/adapters/diffusers-lora.js';
import { buildPackage as buildAiToolkitPackage } from '../../lib/adapters/ai-toolkit.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';
import { createTrainingPackageProject, PNG_MAGIC } from './fixtures/make-training-package-project.js';

/** Recursively count regular files (not directories) under `dir`. */
async function countFiles(dir) {
  const { readdir } = await import('node:fs/promises');
  let count = 0;
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) count += await countFiles(join(dir, entry.name));
    else count++;
  }
  return count;
}

// ─── SDL-H5 / SDL-H6: pure-function unit proof ───────────────────────────

test('SDL-H5: assertSafeId / SAFE_ID_RE reject traversal and unsafe characters', () => {
  assert.throws(() => assertSafeId('../../../evil', 'ctx'), err => err.code === 'UNSAFE_RECORD_ID');
  assert.throws(() => assertSafeId('evil/id', 'ctx'), err => err.code === 'UNSAFE_RECORD_ID');
  assert.throws(() => assertSafeId('evil\\id', 'ctx'), err => err.code === 'UNSAFE_RECORD_ID');
  assert.throws(() => assertSafeId('evil id', 'ctx'), err => err.code === 'UNSAFE_RECORD_ID');
  assert.throws(() => assertSafeId('', 'ctx'), err => err.code === 'UNSAFE_RECORD_ID');
  assert.throws(() => assertSafeId(null, 'ctx'), err => err.code === 'UNSAFE_RECORD_ID');
  // Legitimate ids pass through untouched.
  assert.doesNotThrow(() => assertSafeId('styleset_p04_crane_tower_v1', 'ctx'));
  assert.doesNotThrow(() => assertSafeId('anchor_01.v2', 'ctx'));
  assert.ok(SAFE_ID_RE.test('anchor_01'));
  assert.ok(!SAFE_ID_RE.test('../evil'));
});

test('SDL-H6: assertSafeAssetPath rejects absolute paths and traversal, accepts safe relative paths', () => {
  const root = join('C:', 'fake', 'project') || '/fake/project';
  assert.throws(
    () => assertSafeAssetPath('../../../../Users/victim/.ssh/id_rsa', root, 'rec1'),
    err => err.code === 'ASSET_PATH_TRAVERSAL',
  );
  assert.throws(
    () => assertSafeAssetPath('/etc/passwd', root, 'rec1'),
    err => err.code === 'ASSET_PATH_INVALID',
  );
  const resolved = assertSafeAssetPath('inputs/foo.png', root, 'rec1');
  assert.ok(resolved.endsWith(join('inputs', 'foo.png')));
});

// ─── SDL-C5: Windows guard ────────────────────────────────────────────────

test('SDL-C5: buildTrainingPackage refuses symlink mode on Windows with SYMLINK_UNSUPPORTED_WINDOWS', async (t) => {
  if (process.platform !== 'win32') {
    t.skip('this environment is not win32 — the guard is win32-specific, like export.js D-008');
    return;
  }
  const proj = await createTrainingPackageProject({ count: 2 });
  try {
    await assert.rejects(
      () => buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: false }),
      err => err.code === 'SYMLINK_UNSUPPORTED_WINDOWS',
    );
  } finally {
    proj.cleanup();
  }
});

test('SDL-C5: --copy succeeds on Windows and places every image with zero failures', async () => {
  const proj = await createTrainingPackageProject({ count: 3 });
  try {
    const result = await buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true });
    assert.equal(result.images, 3);
    const manifest = await loadTrainingPackage(proj.projectRoot, result.packageId);
    assert.equal(manifest.counts.images_actual, 3);
    assert.equal(manifest.counts.images_failed, 0);
    assert.equal(manifest.counts.images_expected, 3);
    assert.deepEqual(manifest.images_failed, []);
    assert.deepEqual(manifest.warnings, []);
  } finally {
    proj.cleanup();
  }
});

// ─── SDL-C5: partial failure must be visible, not silently dropped ──────

test('SDL-C5: a missing source image is counted, warned on, and never exits silently clean — RED branch driven explicitly', async () => {
  const proj = await createTrainingPackageProject({
    records: [
      { id: 'present_1' },
      { id: 'present_2' },
      { id: 'missing_1', noFile: true }, // record exists, image file does not
    ],
  });
  try {
    const result = await buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true });
    // 2 placed, 1 failed — this must NOT look like a clean 3/3 success.
    assert.equal(result.images, 2);

    const manifest = await loadTrainingPackage(proj.projectRoot, result.packageId);
    assert.equal(manifest.counts.images_expected, 3);
    assert.equal(manifest.counts.images_actual, 2);
    assert.equal(manifest.counts.images_failed, 1, 'the missing source must be counted as a failure');
    assert.equal(manifest.images_failed.length, 1);
    assert.equal(manifest.images_failed[0].record_id, 'missing_1');
    assert.equal(manifest.images_failed[0].reason, 'source_missing');
    assert.ok(manifest.warnings.length > 0, 'a partial failure must produce a visible warning');
    assert.ok(
      manifest.warnings.some(w => /failed to place/.test(w)),
      `expected a failed-to-place warning, got: ${JSON.stringify(manifest.warnings)}`,
    );

    // Invariant: every row is accounted for exactly once (success xor failure).
    assert.equal(manifest.counts.images_actual + manifest.counts.images_failed, manifest.counts.images_expected);
  } finally {
    proj.cleanup();
  }
});

test('SDL-C5: total failure (all sources missing) is visible in the manifest, not a silent empty success', async () => {
  const proj = await createTrainingPackageProject({
    records: [
      { id: 'ghost_1', noFile: true },
      { id: 'ghost_2', noFile: true },
    ],
  });
  try {
    // This is the exact shape of the originally-reported bug (minus the
    // Windows-symlink trigger): every row fails to place.
    const result = await buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true });
    assert.equal(result.images, 0);
    const manifest = await loadTrainingPackage(proj.projectRoot, result.packageId);
    assert.equal(manifest.counts.images_actual, 0);
    assert.equal(manifest.counts.images_failed, 2);
    assert.equal(manifest.counts.images_expected, 2);
    assert.ok(manifest.warnings.length > 0, 'total failure must still be visible, never silent');
  } finally {
    proj.cleanup();
  }
});

// ─── SDL-H5 / SDL-H6 end-to-end through buildTrainingPackage ────────────

test('SDL-H5: buildTrainingPackage rejects an unsafe record id before touching the filesystem', async () => {
  const proj = await createTrainingPackageProject({
    records: [
      { id: 'normal_1' },
      { id: 'evil id' }, // space — legal filename, illegal per SAFE_ID_RE
    ],
  });
  try {
    await assert.rejects(
      () => buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true }),
      err => err.code === 'UNSAFE_RECORD_ID',
    );
    // Nothing should have been written under training/packages/ for this
    // attempt to look like a completed (even partial) package — the guard
    // fires before the adapter runs.
  } finally {
    proj.cleanup();
  }
});

test('SDL-H6: buildTrainingPackage rejects a traversal asset_path before touching the filesystem', async () => {
  const proj = await createTrainingPackageProject({
    records: [
      { id: 'normal_1' },
      { id: 'evil_2', assetPath: '../../../../outside-secret.png' },
    ],
  });
  try {
    await assert.rejects(
      () => buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true }),
      err => err.code === 'ASSET_PATH_TRAVERSAL',
    );
  } finally {
    proj.cleanup();
  }
});

// ─── SDL-H5 end-to-end through buildExport ───────────────────────────────

test('SDL-H5: buildExport rejects an unsafe record id before writing the destination filename', async () => {
  const records = [
    makeRecord({ id: 'normal_1', identity: { subject_name: 'normal_1' } }),
    makeRecord({ id: 'evil id', identity: { subject_name: 'evil_subject' } }), // space
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, {
      profile_id: 'sel', require_judgment: true, require_status: ['approved'],
      require_canon_bound: true, minimum_pass_ratio: 0.5,
    });
    const split = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1,
    });
    await assert.rejects(
      () => buildExport(proj.projectRoot, snap.snapshotId, split.splitId, { copy: true }),
      err => err.code === 'UNSAFE_RECORD_ID',
    );
  } finally {
    proj.cleanup();
  }
});

// ─── SDL-H5 / SDL-H6: adapter-level defense-in-depth (direct buildPackage) ─

const adapters = [
  ['generic-image-caption', buildGenericPackage],
  ['diffusers-lora', buildDiffusersPackage],
  ['ai-toolkit', buildAiToolkitPackage],
];

for (const [name, buildPackage] of adapters) {
  test(`SDL-H5: ${name} adapter rejects an unsafe entity_id (row-level, no training-packages.js in front)`, async () => {
    const { mkdtemp, rm } = await import('node:fs/promises');
    const { tmpdir } = await import('node:os');
    const projectRoot = await mkdtemp(join(tmpdir(), 'sdlab-adapter-src-'));
    const packageDir = await mkdtemp(join(tmpdir(), 'sdlab-adapter-pkg-'));
    try {
      await mkdir(join(projectRoot, 'inputs'), { recursive: true });
      await writeFile(join(projectRoot, 'inputs', 'anchor.png'), PNG_MAGIC);

      const profile = name === 'ai-toolkit'
        ? { target_family: 'flux', profile_id: 'p', base_model_recommendations: [] }
        : { target_family: 'sdxl', profile_id: 'p' };

      const row = {
        entity_id: '../../../evil',
        lane: 'concept',
        partition: 'train',
        asset_path: 'inputs/anchor.png',
        caption: 'a caption',
      };

      await assert.rejects(
        () => buildPackage({
          packageDir, rows: [row], profile, manifest: {}, config: {}, projectRoot, copy: true,
        }),
        err => err.code === 'UNSAFE_RECORD_ID',
      );
      // No FILE should exist inside packageDir — the guard must fire
      // before any write is attempted. (The empty dataset/<partition> and
      // metadata/ skeleton directories are a harmless side effect of the
      // per-partition mkdir that runs before per-row validation; only
      // files matter for the traversal-write claim. Deliberately not
      // checking a path outside packageDir — every mkdtemp'd sibling dir
      // in this file shares the same OS tmp root one level up, so a check
      // like `join(packageDir, '..', 'evil.png')` would alias across
      // tests.)
      assert.deepEqual(await countFiles(packageDir), 0);
    } finally {
      await rm(projectRoot, { recursive: true, force: true });
      await rm(packageDir, { recursive: true, force: true });
    }
  });

  test(`SDL-H6: ${name} adapter rejects a traversal asset_path (row-level, no training-packages.js in front)`, async () => {
    const { mkdtemp, rm } = await import('node:fs/promises');
    const { tmpdir } = await import('node:os');
    const projectRoot = await mkdtemp(join(tmpdir(), 'sdlab-adapter-src-'));
    const packageDir = await mkdtemp(join(tmpdir(), 'sdlab-adapter-pkg-'));
    try {
      const profile = name === 'ai-toolkit'
        ? { target_family: 'flux', profile_id: 'p', base_model_recommendations: [] }
        : { target_family: 'sdxl', profile_id: 'p' };

      const row = {
        entity_id: 'safe_id',
        lane: 'concept',
        partition: 'train',
        asset_path: '../../../../Users/victim/.ssh/id_rsa',
        caption: 'a caption',
      };

      await assert.rejects(
        () => buildPackage({
          packageDir, rows: [row], profile, manifest: {}, config: {}, projectRoot, copy: true,
        }),
        err => err.code === 'ASSET_PATH_TRAVERSAL',
      );
    } finally {
      await rm(projectRoot, { recursive: true, force: true });
      await rm(packageDir, { recursive: true, force: true });
    }
  });
}

// ─── Adapter-level SDL-C5 visibility (direct buildPackage, PASS contrast) ──

test('SDL-C5: generic-image-caption adapter returns imagesFailed (not just imageCount) for a missing source', async () => {
  const { mkdtemp, rm } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdlab-adapter-src-'));
  const packageDir = await mkdtemp(join(tmpdir(), 'sdlab-adapter-pkg-'));
  try {
    const row = {
      entity_id: 'ghost',
      lane: 'concept',
      partition: 'train',
      asset_path: 'inputs/does-not-exist.png',
      caption: 'a caption',
    };
    const result = await buildGenericPackage({
      packageDir, rows: [row], profile: { profile_id: 'p' }, manifest: {}, config: {}, projectRoot, copy: true,
    });
    assert.equal(result.imageCount, 0);
    assert.equal(result.imagesFailed.length, 1);
    assert.equal(result.imagesFailed[0].record_id, 'ghost');
    assert.equal(result.imagesFailed[0].reason, 'source_missing');
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
    await rm(packageDir, { recursive: true, force: true });
  }
});
