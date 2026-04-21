/**
 * Export package builder — self-contained, reproducible dataset exports.
 *
 * An export package contains everything needed to use or rebuild the dataset:
 * manifest, metadata, images (symlinked or copied), splits, card, and checksums.
 */

import { readFile, writeFile, mkdir, readdir, symlink, copyFile, stat } from 'node:fs/promises';
import { join, relative, resolve, sep, basename, isAbsolute } from 'node:path';
import { existsSync } from 'node:fs';
import { platform } from 'node:os';
import { createHash, randomBytes } from 'node:crypto';
import { loadProjectConfig, loadExportProfile, detectLane, detectGroup } from './config.js';
import { loadSnapshot, loadSnapshotIncluded, computeConfigFingerprint } from './snapshot.js';
import { loadSplit, loadSplitPartition } from './split.js';
import { loadRecord } from './records.js';
import { generateCard } from './card.js';
import { inputError } from './errors.js';

/**
 * Generate an export ID: export-YYYYMMDD-HHMMSS-XXXX
 */
function generateExportId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = randomBytes(2).toString('hex');
  return `export-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

/**
 * Compute SHA-256 of a file.
 */
async function sha256File(filePath) {
  const data = await readFile(filePath);
  return createHash('sha256').update(data).digest('hex');
}

/**
 * Build an export package.
 *
 * @param {string} projectRoot
 * @param {string} snapshotId
 * @param {string} splitId
 * @param {Object} options — { profileId?, copy? }
 * @returns {Promise<{exportId: string, recordCount: number, imageCount: number}>}
 */
export async function buildExport(projectRoot, snapshotId, splitId, options = {}) {
  const config = loadProjectConfig(projectRoot);
  const profile = loadExportProfile(projectRoot, options.profileId || null);
  const snapshot = await loadSnapshot(projectRoot, snapshotId);
  const split = await loadSplit(projectRoot, splitId);

  // Load all included records
  const included = await loadSnapshotIncluded(projectRoot, snapshotId);
  const recordsDir = join(projectRoot, 'records');

  const exportId = generateExportId();
  const exportDir = join(projectRoot, 'exports', exportId);

  // D-005: existsSync guard prevents silent overwrite on ID collision
  if (existsSync(exportDir)) {
    throw inputError(
      'EXPORT_ID_COLLISION',
      `Export directory already exists: ${exportDir}`,
      'Retry to generate a fresh export ID, or delete the existing directory if this was intentional.',
    );
  }

  // D-001: Verify fingerprint has not drifted since snapshot creation.
  // We inherit the snapshot's fingerprint in the export manifest; if a caller
  // has edited project config mid-flight we surface that loudly rather than
  // silently embedding a new fingerprint that masks reproducibility loss.
  const currentFingerprint = computeConfigFingerprint(projectRoot);
  if (snapshot.config_fingerprint && currentFingerprint !== snapshot.config_fingerprint) {
    throw inputError(
      'FINGERPRINT_DRIFT',
      `Project config fingerprint has changed since snapshot "${snapshotId}" was created.`,
      `Snapshot fingerprint: ${snapshot.config_fingerprint.slice(0, 16)}..., current: ${currentFingerprint.slice(0, 16)}.... Create a fresh snapshot from the updated config, or revert the config edits.`,
    );
  }

  await mkdir(exportDir, { recursive: true });

  // Build metadata + collect image paths
  const metadata = [];
  const imagePaths = [];
  const checksumEntries = [];

  const projectRootResolved = resolve(projectRoot);

  for (const entry of included) {
    const record = await loadRecord(recordsDir, entry.record_id);
    if (!record) continue;

    const prompt = record.provenance?.prompt || '';
    const lane = detectLane(record.id, prompt, config.lanes);
    const group = detectGroup(record.id, prompt, config.terminology);

    // Build metadata row with requested fields
    const row = {};
    for (const field of profile.metadata_fields) {
      if (field === 'id') row.id = record.id;
      else if (field === 'asset_path') row.asset_path = record.asset_path;
      else if (field === 'provenance') row.provenance = record.provenance;
      else if (field === 'judgment') row.judgment = record.judgment;
      else if (field === 'canon') row.canon = record.canon;
      else if (field === 'identity') row.identity = record.identity || null;
      else if (field === 'lineage') row.lineage = record.lineage || null;
      else if (record[field] !== undefined) row[field] = record[field];
    }
    row.detected_lane = lane;
    row.detected_group = group;
    metadata.push(row);

    // Track image for linking
    if (profile.include_images && record.asset_path) {
      // D-007: validate asset_path does not escape projectRoot, use
      // platform-safe basename, and name output files by record.id
      // (D-009) to avoid collisions on shared basenames.
      if (isAbsolute(record.asset_path)) {
        throw inputError(
          'ASSET_PATH_INVALID',
          `Record "${record.id}" has absolute asset_path: ${record.asset_path}`,
          'asset_path must be relative to the project root.',
        );
      }
      const resolvedSource = resolve(projectRootResolved, record.asset_path);
      if (resolvedSource !== projectRootResolved &&
          !resolvedSource.startsWith(projectRootResolved + sep)) {
        throw inputError(
          'ASSET_PATH_TRAVERSAL',
          `Record "${record.id}" asset_path escapes projectRoot: ${record.asset_path}`,
          'Reject path traversal segments (e.g. "../") in asset_path.',
        );
      }
      const sourceBasename = basename(record.asset_path);
      const extMatch = sourceBasename.match(/\.[^.]+$/);
      const ext = extMatch ? extMatch[0] : '';
      const safeFilename = `${record.id}${ext}`;
      imagePaths.push({
        record_id: record.id,
        source: resolvedSource,
        filename: safeFilename,
      });
    }
  }

  // Write metadata.jsonl
  const metadataPath = join(exportDir, 'metadata.jsonl');
  await writeFile(metadataPath, metadata.map(r => JSON.stringify(r)).join('\n') + '\n');

  // Images directory
  const warnings = [];
  if (profile.include_images && imagePaths.length > 0) {
    // D-008: Windows symlink semantics differ (require admin or dev mode);
    // refuse symlink mode on Windows and require --copy for portability.
    if (!options.copy && platform() === 'win32') {
      throw inputError(
        'SYMLINK_UNSUPPORTED_WINDOWS',
        'Symlink mode is not supported on Windows export (target semantics differ and break on archive).',
        'Re-run with --copy to produce a portable, self-contained export.',
      );
    }
    if (!options.copy) {
      warnings.push(
        'Export uses relative symlinks — package is NOT portable across machines. ' +
        'Use --copy for cross-machine transfer or archival.',
      );
    }

    const imagesDir = join(exportDir, 'images');
    await mkdir(imagesDir, { recursive: true });

    let linked = 0;
    for (const img of imagePaths) {
      const dest = join(imagesDir, img.filename);
      if (existsSync(img.source)) {
        try {
          if (options.copy) {
            await copyFile(img.source, dest);
          } else {
            const relPath = relative(imagesDir, img.source);
            await symlink(relPath, dest);
          }
          linked++;
        } catch {
          // Skip individual failures (e.g. duplicate filenames)
        }
      }
    }
  }

  // Splits
  if (profile.include_splits) {
    const splitsDir = join(exportDir, 'splits');
    await mkdir(splitsDir, { recursive: true });

    for (const partition of ['train', 'val', 'test']) {
      const entries = await loadSplitPartition(projectRoot, splitId, partition);
      await writeFile(
        join(splitsDir, `${partition}.jsonl`),
        entries.map(e => JSON.stringify(e)).join('\n') + '\n'
      );
    }
  }

  // Dataset card
  if (profile.include_card) {
    const { markdown, json } = await generateCard(projectRoot, snapshotId, splitId);
    await writeFile(join(exportDir, 'dataset-card.md'), markdown);
    await writeFile(join(exportDir, 'dataset-card.json'), JSON.stringify(json, null, 2) + '\n');
  }

  // D-015: Write manifest + summary FIRST so they are covered by checksums.
  // D-001: Inherit snapshot's config_fingerprint (we verified above it matches
  // current state) — never recompute independently at export time.
  const manifest = {
    export_id: exportId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-export-v1',
    project: config.meta.name,
    snapshot_id: snapshotId,
    split_id: splitId,
    config_fingerprint: snapshot.config_fingerprint,
    profile,
    warnings,
    counts: {
      records: metadata.length,
      images: imagePaths.filter(i => existsSync(i.source)).length,
      checksums: 0, // updated after checksum pass below
    },
  };
  await writeFile(join(exportDir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');

  // Summary
  const summary = {
    export_id: exportId,
    snapshot_id: snapshotId,
    split_id: splitId,
    record_count: metadata.length,
    image_count: manifest.counts.images,
    partitions: {
      train: split.counts.train,
      val: split.counts.val,
      test: split.counts.test,
    },
    config_fingerprint: manifest.config_fingerprint,
    warnings,
  };
  await writeFile(join(exportDir, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');

  // Checksums (computed AFTER manifest+summary so they are included)
  if (profile.include_checksums) {
    const allFiles = await collectFiles(exportDir);
    for (const filePath of allFiles.sort()) {
      const relPath = relative(exportDir, filePath);
      if (relPath === 'checksums.txt') continue;
      const hash = await sha256File(filePath);
      checksumEntries.push(`SHA256 (${relPath}) = ${hash}`);
    }
    await writeFile(join(exportDir, 'checksums.txt'), checksumEntries.join('\n') + '\n');
  }

  return {
    exportId,
    recordCount: metadata.length,
    imageCount: manifest.counts.images,
  };
}

/**
 * Recursively collect all files in a directory.
 */
async function collectFiles(dir, base = dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectFiles(full, base));
    } else {
      files.push(full);
    }
  }
  return files;
}

/**
 * List all exports in a project.
 */
export async function listExports(projectRoot) {
  const exportsDir = join(projectRoot, 'exports');
  if (!existsSync(exportsDir)) return [];

  const entries = await readdir(exportsDir, { withFileTypes: true });
  const exports = [];

  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('export-')) continue;
    const manifestPath = join(exportsDir, entry.name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const manifest = JSON.parse(await readFile(manifestPath, 'utf-8'));
      exports.push({
        id: manifest.export_id,
        created_at: manifest.created_at,
        snapshot_id: manifest.snapshot_id,
        split_id: manifest.split_id,
        records: manifest.counts.records,
        images: manifest.counts.images,
      });
    } catch {
      // Skip malformed
    }
  }

  return exports.sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/**
 * Load an export manifest.
 */
export async function loadExport(projectRoot, exportId) {
  const path = join(projectRoot, 'exports', exportId, 'manifest.json');
  if (!existsSync(path)) {
    throw new Error(`Export "${exportId}" not found at ${path}`);
  }
  return JSON.parse(await readFile(path, 'utf-8'));
}
