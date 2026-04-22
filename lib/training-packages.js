/**
 * Training package builder.
 *
 * Builds trainer-ready dataset packages from training manifests.
 * Adapters transform the canonical layout for specific training targets
 * but never mutate inclusion or split truth.
 */

import { readFile, writeFile, mkdir, readdir, symlink, copyFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { existsSync } from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
import { loadTrainingManifest } from './training-manifests.js';
import { loadTrainingProfile } from './training-profiles.js';
import { loadSplitPartition } from './split.js';
import { loadRecord } from './records.js';
import { loadProjectConfig, detectLane, detectGroup } from './config.js';
import { inputError } from './errors.js';
import { SCHEMA_VERSION, checkManifestVersion } from './snapshot.js';
import { loadAdapter } from './training-adapters.js';

/**
 * Generate a training package ID: tp-YYYYMMDD-HHMMSS-XXXX
 */
function generatePackageId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = randomBytes(2).toString('hex');
  return `tp-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

async function sha256File(filePath) {
  const data = await readFile(filePath);
  return createHash('sha256').update(data).digest('hex');
}

/**
 * Build a training package from a manifest.
 *
 * @param {string} projectRoot
 * @param {string} manifestId
 * @param {Object} options — { copy?, adapterOverride? }
 * @returns {Promise<{packageId: string, records: number, images: number}>}
 */
export async function buildTrainingPackage(projectRoot, manifestId, options = {}) {
  const manifest = await loadTrainingManifest(projectRoot, manifestId);
  const profile = await loadTrainingProfile(projectRoot, manifest.training_profile_id);
  const config = loadProjectConfig(projectRoot);
  const adapterTarget = options.adapterOverride || manifest.adapter_target;
  const adapter = await loadAdapter(adapterTarget);

  const recordsDir = join(projectRoot, 'records');
  const packageId = generatePackageId();
  const packageDir = join(projectRoot, 'training', 'packages', packageId);
  // D-005: refuse to silently overwrite on ID collision.
  if (existsSync(packageDir)) {
    throw inputError(
      'TRAINING_PACKAGE_ID_COLLISION',
      `Training package directory already exists: ${packageDir}`,
      'Retry to generate a fresh package ID.',
    );
  }

  // Load split partitions
  const partitions = {};
  let totalRecords = 0;
  let totalImages = 0;

  for (const partition of ['train', 'val', 'test']) {
    const entries = await loadSplitPartition(projectRoot, manifest.source_split_id, partition);
    const records = [];

    for (const entry of entries) {
      const record = await loadRecord(recordsDir, entry.record_id);
      if (!record) continue;

      // Filter by profile's eligible lanes
      const prompt = record.provenance?.prompt || '';
      const lane = detectLane(record.id, prompt, config.lanes);
      if (profile.eligible_lanes.length > 0 && !profile.eligible_lanes.includes(lane)) {
        continue;
      }

      const group = detectGroup(record.id, prompt, config.terminology);
      records.push({ record, lane, group });
    }

    partitions[partition] = records;
    totalRecords += records.length;
  }

  // Let the adapter build the package layout
  const adapterResult = await adapter.buildPackage({
    packageDir,
    partitions,
    profile,
    manifest,
    config,
    projectRoot,
    copy: options.copy || false,
  });

  totalImages = adapterResult.imageCount || 0;

  // D-015: Write manifest + README FIRST so they are covered by checksums.
  const packageManifest = {
    // DB-001 / DB-006: stamp manifest schema version
    schema_version: SCHEMA_VERSION,
    training_package_id: packageId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-training-package-v1',
    training_manifest_id: manifestId,
    training_profile_id: manifest.training_profile_id,
    adapter_target: adapterTarget,
    source_export_id: manifest.source_export_id,
    source_snapshot_id: manifest.source_snapshot_id,
    source_split_id: manifest.source_split_id,
    config_fingerprint: manifest.config_fingerprint,
    counts: {
      total_records: totalRecords,
      train: partitions.train.length,
      val: partitions.val.length,
      test: partitions.test.length,
      images: totalImages,
      checksums: 0, // updated after checksum pass below
    },
  };
  await writeFile(join(packageDir, 'manifest.json'), JSON.stringify(packageManifest, null, 2) + '\n');

  // Write README
  const readme = generatePackageReadme(packageManifest, profile, manifest, adapterTarget);
  await writeFile(join(packageDir, 'README.md'), readme);

  // Generate checksums AFTER manifest+README are on disk so they are included.
  const checksumEntries = [];
  const allFiles = await collectFiles(packageDir);
  for (const filePath of allFiles.sort()) {
    const relPath = relative(packageDir, filePath);
    if (relPath === 'checksums.txt') continue;
    const hash = await sha256File(filePath);
    checksumEntries.push(`SHA256 (${relPath}) = ${hash}`);
  }
  await writeFile(join(packageDir, 'checksums.txt'), checksumEntries.join('\n') + '\n');

  return { packageId, records: totalRecords, images: totalImages };
}

function generatePackageReadme(pkg, profile, manifest, adapter) {
  return `# Training Package: ${pkg.training_package_id}

**Profile:** ${profile.label} (${profile.profile_id})
**Adapter:** ${adapter}
**Target:** ${profile.target_family} / ${profile.asset_type}
**Created:** ${pkg.created_at}

## Source chain

- Training manifest: \`${manifest.training_manifest_id}\`
- Export: \`${manifest.source_export_id}\`
- Snapshot: \`${manifest.source_snapshot_id}\`
- Split: \`${manifest.source_split_id}\`
- Config fingerprint: \`${manifest.config_fingerprint.slice(0, 16)}...\`

## Counts

| Partition | Records |
|-----------|---------|
| Train | ${pkg.counts.train} |
| Val | ${pkg.counts.val} |
| Test | ${pkg.counts.test} |
| **Total** | **${pkg.counts.total_records}** |

Images: ${pkg.counts.images}

## Checksums

All files in this package are checksummed in \`checksums.txt\` (BSD format).

## Provenance

This package was produced by [Style Dataset Lab](https://github.com/mcp-tool-shop-org/style-dataset-lab).
Every included record has been human-reviewed, canon-bound, and verified against project constitution rules.
The dataset split ensures no subject family appears in multiple partitions.
`;
}

async function collectFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectFiles(full));
    } else {
      files.push(full);
    }
  }
  return files;
}

/**
 * List all training packages.
 */
export async function listTrainingPackages(projectRoot) {
  const dir = join(projectRoot, 'training', 'packages');
  if (!existsSync(dir)) return [];

  const entries = await readdir(dir, { withFileTypes: true });
  const packages = [];

  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('tp-')) continue;
    const manifestPath = join(dir, entry.name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const data = JSON.parse(await readFile(manifestPath, 'utf-8'));
      packages.push({
        id: data.training_package_id,
        created_at: data.created_at,
        profile: data.training_profile_id,
        adapter: data.adapter_target,
        records: data.counts.total_records,
        images: data.counts.images,
      });
    } catch { /* skip */ }
  }

  return packages.sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/**
 * Load a training package manifest.
 */
export async function loadTrainingPackage(projectRoot, packageId) {
  const path = join(projectRoot, 'training', 'packages', packageId, 'manifest.json');
  if (!existsSync(path)) {
    throw new Error(`Training package "${packageId}" not found at ${path}`);
  }
  const manifest = JSON.parse(await readFile(path, 'utf-8'));
  checkManifestVersion(manifest, 'training-package');
  return manifest;
}
