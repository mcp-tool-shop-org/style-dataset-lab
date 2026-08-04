/**
 * SDL-H9: training-manifest binding hash must cover image bytes.
 *
 * export_manifest_hash only ever covered exports/<id>/manifest.json — a
 * file with no image bytes in it. checksums.txt (written by both
 * export.js and training-packages.js) covers every file in the export,
 * including images, but training-manifests.js never read it. Replacing an
 * image inside a finished export used to leave `validate` reporting
 * `valid: true, issues: []`, contradicting the module's own docstring
 * claim of capturing "the exact export package … so the training run is
 * fully reproducible."
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, readdir, appendFile, rm } from 'node:fs/promises';
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { createSnapshot } from '../../lib/snapshot.js';
import { createSplit } from '../../lib/split.js';
import { buildExport } from '../../lib/export.js';
import {
  createTrainingManifest,
  validateTrainingManifest,
  loadTrainingManifest,
} from '../../lib/training-manifests.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

const SELECTION = {
  profile_id: 'sel',
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
};
const SPLIT_PROFILE = { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1 };
const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

async function buildFullChain(recordCount = 6) {
  const records = [];
  for (let i = 0; i < recordCount; i++) {
    records.push(makeRecord({ id: `r_${i}`, assetPath: `inputs/r_${i}.png` }));
  }
  const proj = createTmpProject({ records });
  mkdirSync(join(proj.projectRoot, 'inputs'), { recursive: true });
  for (let i = 0; i < recordCount; i++) {
    writeFileSync(join(proj.projectRoot, 'inputs', `r_${i}.png`), PNG_MAGIC);
  }

  const snap = await createSnapshot(proj.projectRoot, SELECTION);
  const split = await createSplit(proj.projectRoot, snap.snapshotId, SPLIT_PROFILE);

  const exportProfilesDir = join(proj.projectRoot, 'export-profiles');
  await mkdir(exportProfilesDir, { recursive: true });
  await writeFile(join(exportProfilesDir, 'default.json'), JSON.stringify({
    profile_id: 'default',
    metadata_fields: ['id', 'asset_path'],
    include_images: true,
    include_splits: false,
    include_card: false,
    include_checksums: true,
  }));

  const exp = await buildExport(proj.projectRoot, snap.snapshotId, split.splitId, { copy: true });

  const tpDir = join(proj.projectRoot, 'training', 'profiles');
  await mkdir(tpDir, { recursive: true });
  await writeFile(join(tpDir, 'tp1.json'), JSON.stringify({
    profile_id: 'tp1',
    label: 'test',
    asset_type: 'concept',
    target_family: 'sdxl',
    adapter_targets: ['generic-image-caption'],
    eligible_lanes: [],
    caption_strategy: 'filename',
  }));

  const { manifestId } = await createTrainingManifest(proj.projectRoot, exp.exportId, 'tp1', {});

  return { proj, exportId: exp.exportId, manifestId };
}

async function firstExportedImagePath(projectRoot, exportId) {
  const imagesDir = join(projectRoot, 'exports', exportId, 'images');
  const files = (await readdir(imagesDir)).filter(f => f.endsWith('.png')).sort();
  assert.ok(files.length > 0, 'export must have at least one image to tamper with');
  return join(imagesDir, files[0]);
}

test('SDL-H9: createTrainingManifest captures export_checksums_hash when the export has checksums.txt', async () => {
  const { proj, manifestId } = await buildFullChain();
  try {
    const manifest = await loadTrainingManifest(proj.projectRoot, manifestId);
    assert.ok(manifest.export_checksums_hash, 'export_checksums_hash must be captured');
    assert.match(manifest.export_checksums_hash, /^[0-9a-f]{64}$/);
  } finally {
    proj.cleanup();
  }
});

test('SDL-H9: validate reports valid:true on an untouched export — explicit PASS branch for contrast', async () => {
  const { proj, manifestId } = await buildFullChain();
  try {
    const result = await validateTrainingManifest(proj.projectRoot, manifestId);
    assert.equal(result.valid, true);
    assert.deepEqual(result.issues, []);
  } finally {
    proj.cleanup();
  }
});

test('SDL-H9: replacing an image after export flips validate to invalid — RED branch driven explicitly', async () => {
  const { proj, exportId, manifestId } = await buildFullChain();
  try {
    // Sanity: clean before tampering (prior art trap: don't only assert
    // the failing branch — prove the untouched case is clean first).
    const before = await validateTrainingManifest(proj.projectRoot, manifestId);
    assert.equal(before.valid, true, 'must be clean before tampering');

    const imagePath = await firstExportedImagePath(proj.projectRoot, exportId);
    const imageBasename = imagePath.split(/[\\/]/).pop();
    // Replace the image with different bytes — same file, same name,
    // different content. export_manifest_hash (manifest.json only) is
    // structurally blind to this.
    await writeFile(imagePath, Buffer.from([0x89, 0x50, 0x4e, 0x47, 0xff, 0xff, 0xff, 0xff, 0x00, 0x01]));

    const after = await validateTrainingManifest(proj.projectRoot, manifestId);
    assert.equal(after.valid, false, 'replacing an image must be caught');
    assert.ok(after.issues.length > 0);
    assert.ok(
      after.issues.some(i => /modified since export/.test(i) && i.includes(imageBasename)),
      `expected a "modified since export" issue naming ${imageBasename}, got: ${JSON.stringify(after.issues)}`,
    );
  } finally {
    proj.cleanup();
  }
});

test('SDL-H9: deleting a file that checksums.txt records is reported as missing', async () => {
  const { proj, exportId, manifestId } = await buildFullChain();
  try {
    const imagePath = await firstExportedImagePath(proj.projectRoot, exportId);
    await rm(imagePath);

    const result = await validateTrainingManifest(proj.projectRoot, manifestId);
    assert.equal(result.valid, false);
    assert.ok(result.issues.some(i => /missing/.test(i)));
  } finally {
    proj.cleanup();
  }
});

test('SDL-H9: tampering with checksums.txt itself (not a listed file) is caught by the binding hash', async () => {
  const { proj, exportId, manifestId } = await buildFullChain();
  try {
    const checksumsPath = join(proj.projectRoot, 'exports', exportId, 'checksums.txt');
    await appendFile(checksumsPath, '# tampered\n');

    const result = await validateTrainingManifest(proj.projectRoot, manifestId);
    assert.equal(result.valid, false);
    assert.ok(result.issues.some(i => /checksum manifest itself has changed/.test(i)));
  } finally {
    proj.cleanup();
  }
});

test('SDL-H9: old manifest without export_checksums_hash still catches a replaced image via full re-verification', async () => {
  const { proj, exportId, manifestId } = await buildFullChain();
  try {
    // Simulate a pre-SDL-H9 manifest by stripping the new field, mirroring
    // real on-disk manifests written before this fix (e.g. tallow-fen's).
    const manifestPath = join(proj.projectRoot, 'training', 'manifests', `${manifestId}.json`);
    const manifest = JSON.parse(await readFile(manifestPath, 'utf-8'));
    delete manifest.export_checksums_hash;
    await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');

    // Confirm still clean pre-tamper even without the binding field.
    const before = await validateTrainingManifest(proj.projectRoot, manifestId);
    assert.equal(before.valid, true, 'legacy manifest without the new field must not false-positive');

    const imagePath = await firstExportedImagePath(proj.projectRoot, exportId);
    await writeFile(imagePath, Buffer.from([0x00, 0x01, 0x02, 0x03, 0x04]));

    const after = await validateTrainingManifest(proj.projectRoot, manifestId);
    assert.equal(after.valid, false, 'full re-verification must still catch this without export_checksums_hash');
    assert.ok(after.issues.some(i => /modified since export/.test(i)));
  } finally {
    proj.cleanup();
  }
});
