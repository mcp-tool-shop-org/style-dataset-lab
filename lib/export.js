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
import { loadSnapshot, loadSnapshotIncluded, computeConfigFingerprint, SCHEMA_VERSION, checkManifestVersion, claimIdDir } from './snapshot.js';
import { loadSplit, loadSplitPartition } from './split.js';
import { loadRecord } from './records.js';
import { generateCard } from './card.js';
import { inputError } from './errors.js';
import { warn } from './log.js';

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
 * SDL-H6: validate that a record-relative asset_path does not escape
 * projectRoot. Rejects absolute paths outright (ASSET_PATH_INVALID) and
 * rejects any relative path that resolves outside projectRoot
 * (ASSET_PATH_TRAVERSAL — e.g. "../../../../Users/victim/.ssh/id_rsa").
 * Returns the resolved absolute path on success.
 *
 * This was previously inlined here only (D-007) and never ported to the
 * training-package adapters, which checked only `existsSync` — a
 * traversal path satisfies existsSync just as well as a legitimate one.
 * lib/training-packages.js and the adapters import this so the exact same
 * guard (same error codes) applies on every path that turns asset_path
 * into a filesystem read.
 */
export function assertSafeAssetPath(assetPath, projectRoot, recordId) {
  if (isAbsolute(assetPath)) {
    throw inputError(
      'ASSET_PATH_INVALID',
      `Record "${recordId}" has absolute asset_path: ${assetPath}`,
      'asset_path must be relative to the project root.',
    );
  }
  const projectRootResolved = resolve(projectRoot);
  const resolvedSource = resolve(projectRootResolved, assetPath);
  if (resolvedSource !== projectRootResolved &&
      !resolvedSource.startsWith(projectRootResolved + sep)) {
    throw inputError(
      'ASSET_PATH_TRAVERSAL',
      `Record "${recordId}" asset_path escapes projectRoot: ${assetPath}`,
      'Reject path traversal segments (e.g. "../") in asset_path.',
    );
  }
  return resolvedSource;
}

/**
 * SDL-H5: allowlist model for an id destined to become a filename or path
 * segment (letters, digits, dot, underscore, hyphen only — no `/`, `\`,
 * or `..`, so no traversal is expressible). Mirrors the character class
 * lib/selections.js's SAFE_FILENAME_RE uses for approved-output filenames;
 * that constant isn't exported and additionally requires an image
 * extension suffix that doesn't apply to a bare record/entity id, so this
 * is a parallel definition over the same allowlist model rather than a
 * copy of a differently-shaped regex.
 */
export const SAFE_ID_RE = /^[A-Za-z0-9._-]+$/;

export function assertSafeId(id, context) {
  if (typeof id !== 'string' || !SAFE_ID_RE.test(id)) {
    throw inputError(
      'UNSAFE_RECORD_ID',
      `Invalid id "${id}" in ${context}`,
      'ids must match [A-Za-z0-9._-]+ — letters, digits, dot, underscore, hyphen only.',
    );
  }
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

  // D-001: Verify fingerprint has not drifted since snapshot creation.
  // We inherit the snapshot's fingerprint in the export manifest; if a caller
  // has edited project config mid-flight we surface that loudly rather than
  // silently embedding a new fingerprint that masks reproducibility loss.
  // (Checked BEFORE claiming an export id/dir below — no point reserving
  // one if we're about to abort.)
  const currentFingerprint = computeConfigFingerprint(projectRoot);
  if (snapshot.config_fingerprint && currentFingerprint !== snapshot.config_fingerprint) {
    throw inputError(
      'FINGERPRINT_DRIFT',
      `Project config fingerprint has changed since snapshot "${snapshotId}" was created.`,
      `Snapshot fingerprint: ${snapshot.config_fingerprint.slice(0, 16)}..., current: ${currentFingerprint.slice(0, 16)}.... Create a fresh snapshot from the updated config, or revert the config edits.`,
    );
  }

  // SDL-M10: atomically claim the export id/dir — closes the
  // check-then-act race the old existsSync+recursive-mkdir pattern had
  // (D-005's intent, now actually race-proof; see claimIdDir in snapshot.js).
  const { id: exportId, dir: exportDir } = await claimIdDir(
    join(projectRoot, 'exports'),
    generateExportId,
    {
      code: 'EXPORT_ID_COLLISION',
      message: 'Could not claim a unique export ID — every candidate collided with an existing export directory.',
      hint: 'Retry; if this persists, another sdlab process may be creating exports in a tight loop.',
    },
  );

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
      // D-007 / SDL-H6: validate asset_path does not escape projectRoot.
      const resolvedSource = assertSafeAssetPath(record.asset_path, projectRootResolved, record.id);
      const sourceBasename = basename(record.asset_path);
      const extMatch = sourceBasename.match(/\.[^.]+$/);
      const ext = extMatch ? extMatch[0] : '';
      // SDL-H5: the block above only validated the SOURCE asset_path —
      // record.id becomes part of the DESTINATION filename below and was
      // completely unvalidated despite the variable being named
      // "safeFilename". A record id of "../../../evil" would escape the
      // export dir on write. Reachable without hand-authoring: reingest
      // derives ids from generated-output filenames.
      assertSafeId(record.id, `record.id for export image filename (record "${record.id}")`);
      // D-009: name output files by record.id to avoid collisions on
      // shared basenames.
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
  // DB-002: separate accounting for expected vs. actually placed vs. failed.
  // Previously `counts.images` reported `sources_that_existed`, which hid
  // per-file symlink/copy failures and made partial exports look complete.
  let imagesExpected = 0;
  let imagesActual = 0;
  const imagesFailed = []; // [{record_id, reason}]
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

    imagesExpected = imagePaths.length;
    for (const img of imagePaths) {
      const dest = join(imagesDir, img.filename);
      if (!existsSync(img.source)) {
        // DB-002: source-missing is a distinct failure mode from link/copy error.
        imagesFailed.push({ record_id: img.record_id, reason: 'source_missing' });
        continue;
      }
      try {
        if (options.copy) {
          await copyFile(img.source, dest);
        } else {
          const relPath = relative(imagesDir, img.source);
          await symlink(relPath, dest);
        }
        imagesActual++;
      } catch (err) {
        // DB-002: capture the specific placement failure for operator triage.
        imagesFailed.push({
          record_id: img.record_id,
          reason: options.copy ? 'copy_failed' : 'link_failed',
          detail: err.message,
        });
      }
    }

    // DB-002: surface partial placement failures loudly — silent `catch {}`
    // previously hid this and made exports appear complete when 20% of
    // images had actually been dropped.
    if (imagesFailed.length > 0) {
      const sample = imagesFailed.slice(0, 10).map(f => `${f.record_id} (${f.reason})`);
      const msg =
        `export: ${imagesFailed.length} of ${imagesExpected} images failed to place` +
        (imagesFailed.length > 10 ? ` — first 10: ${sample.join(', ')}, ...` : ` — ${sample.join(', ')}`);
      warn(msg);
      warnings.push(msg);
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
    // DB-001 / DB-006: stamp manifest schema version
    schema_version: SCHEMA_VERSION,
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
      // DB-002: images count is the actual placed count (not source-exists).
      // Keep top-level `images` for backward compat with older manifest readers
      // that indexed it as the summary number, but add structured detail.
      images: imagesActual,
      images_expected: imagesExpected,
      images_actual: imagesActual,
      images_failed: imagesFailed.length,
      checksums: 0, // updated after checksum pass below
    },
    // DB-002: record-level failure detail so operators can investigate
    // without re-opening the directory to discover what's missing.
    images_failed: imagesFailed,
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
  const manifest = JSON.parse(await readFile(path, 'utf-8'));
  checkManifestVersion(manifest, 'export');
  return manifest;
}
