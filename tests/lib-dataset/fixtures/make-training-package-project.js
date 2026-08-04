/**
 * Fixture helper for training-package tests (SDL-C5 / SDL-H5 / SDL-H6).
 *
 * buildTrainingPackage needs: records, a real split (train/val/test.jsonl),
 * a training profile, and a training manifest — plus actual image bytes on
 * disk so copy/symlink operations have a real source to act on.
 * createTmpProject (make-project.js) only writes record JSON, not image
 * bytes or the training/ scaffolding, so this fixture layers that on top.
 *
 * buildTrainingPackage never reads the export directory (only
 * manifest.source_split_id / training_profile_id), so the training
 * manifest is hand-written directly rather than routed through a real
 * buildExport call — that's an intentional simplification, not a gap in
 * the fixture's realism (loadTrainingManifest doesn't cross-validate
 * against a real export either).
 */

import { writeFileSync, mkdirSync } from 'node:fs';
import { writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { createTmpProject, makeRecord } from './make-project.js';
import { createSnapshot } from '../../../lib/snapshot.js';
import { createSplit } from '../../../lib/split.js';

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

const SELECTION_PROFILE = {
  profile_id: 'pkgtest-selection',
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
};

/**
 * Build a tmp project with real records + real split + training profile +
 * training manifest, ready to pass straight into buildTrainingPackage.
 *
 * @param {Object} opts
 * @param {Array<{id:string, assetPath?:string}>} [opts.records] — explicit
 *   record specs; each gets a real tiny PNG written at its assetPath
 *   (default `inputs/<id>.png`) unless `noFile: true`.
 * @param {number} [opts.count] — if `records` is omitted, generate this
 *   many default records instead.
 * @param {string} [opts.adapterTarget]
 * @param {string[]} [opts.eligibleLanes]
 */
export async function createTrainingPackageProject({
  records: recordSpecs = null,
  count = 3,
  adapterTarget = 'generic-image-caption',
  eligibleLanes = [],
} = {}) {
  const specs = recordSpecs || Array.from({ length: count }, (_, i) => ({ id: `pkgtest_${i}` }));
  const records = specs.map(s => makeRecord({ id: s.id, assetPath: s.assetPath || `inputs/${s.id}.png` }));
  const proj = createTmpProject({ records });

  mkdirSync(join(proj.projectRoot, 'inputs'), { recursive: true });
  for (const spec of specs) {
    if (spec.noFile) continue;
    // Only write the default inputs/<id>.png location — specs with a
    // custom (e.g. traversal or missing) assetPath are deliberately NOT
    // materialized here; callers write those themselves if needed.
    if (!spec.assetPath) {
      writeFileSync(join(proj.projectRoot, 'inputs', `${spec.id}.png`), PNG_MAGIC);
    }
  }

  const snap = await createSnapshot(proj.projectRoot, SELECTION_PROFILE);
  const split = await createSplit(proj.projectRoot, snap.snapshotId, {
    profile_id: 'pkgtest-split',
    train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1,
  });

  const profileId = 'pkgtest-profile';
  const profilesDir = join(proj.projectRoot, 'training', 'profiles');
  await mkdir(profilesDir, { recursive: true });
  await writeFile(join(profilesDir, `${profileId}.json`), JSON.stringify({
    profile_id: profileId,
    label: 'Package test profile',
    asset_type: 'concept',
    target_family: adapterTarget === 'ai-toolkit' ? 'flux' : 'sdxl',
    adapter_targets: [adapterTarget],
    eligible_lanes: eligibleLanes,
    caption_strategy: 'filename',
  }, null, 2));

  const manifestId = 'pkgtest-manifest';
  const manifestsDir = join(proj.projectRoot, 'training', 'manifests');
  await mkdir(manifestsDir, { recursive: true });
  await writeFile(join(manifestsDir, `${manifestId}.json`), JSON.stringify({
    schema_version: '2.3.0',
    training_manifest_id: manifestId,
    created_at: new Date().toISOString(),
    training_profile_id: profileId,
    source_export_id: 'export-fake-00000000-000000-0000',
    source_snapshot_id: snap.snapshotId,
    source_split_id: split.splitId,
    config_fingerprint: 'fake-fingerprint',
    adapter_target: adapterTarget,
  }, null, 2));

  return {
    ...proj,
    snapshotId: snap.snapshotId,
    splitId: split.splitId,
    profileId,
    manifestId,
  };
}

export { PNG_MAGIC };
