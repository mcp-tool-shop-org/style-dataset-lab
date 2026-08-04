/**
 * Training package builder.
 *
 * Builds trainer-ready dataset packages from training manifests.
 * Adapters transform the canonical layout for specific training targets
 * but never mutate inclusion or split truth.
 */

import { readFile, writeFile, readdir } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { existsSync } from 'node:fs';
import { platform } from 'node:os';
import { createHash, randomBytes } from 'node:crypto';
import { loadTrainingManifest } from './training-manifests.js';
import { loadTrainingProfile } from './training-profiles.js';
import { loadSplitPartition } from './split.js';
import { loadRecord } from './records.js';
import { loadProjectConfig, detectLane, detectGroup } from './config.js';
import { inputError, SdlabError } from './errors.js';
import { SCHEMA_VERSION, checkManifestVersion, claimIdDir } from './snapshot.js';
import { loadAdapter } from './training-adapters.js';
import { recordToRow, filterRowsForProfile } from './rows.js';
import { assertSafeAssetPath, assertSafeId } from './export.js';

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

  // Convert split partitions → canonical rows (D6 adapter input shape).
  // Adapters only understand rows — records-flow callers go through this
  // converter, canon-build-flow callers produce rows directly. One input
  // contract, two producers.
  const rows = [];
  const partitionCounts = { train: 0, val: 0, test: 0 };
  // F3: same contract as export.js's identical guard — a record the split
  // promised (via source_split_id's train/val/test.jsonl) whose file was
  // later deleted from records/ must never silently shrink the training
  // package below what the split counted. loadRecord() returns null on
  // ENOENT; previously that was a silent `continue` with no counter, no
  // warning, no id recorded. Accumulated across all three partitions so
  // one thrown error names every missing id instead of discovering them
  // one rebuild at a time.
  const missingRecords = [];
  // H3: recordToRow() can throw CAPTION_SUBJECT_MISSING (lib/captions.js's
  // buildSubjectNaturalLanguageCaption) per-record. That throw is correct —
  // the granularity of handling it here was not: a bare loop with no
  // try/catch meant the FIRST offending record aborted the whole build,
  // before claimIdDir (below) ever reserved a package id, so a 400-record
  // build died having written nothing, named exactly one offender, and had
  // to be rerun in full for each subsequent one. Mirrors the aggregation
  // pattern lib/canon-build/build.js already uses for contextLimitFailures:
  // collect across the WHOLE loop, throw one summary naming every offender.
  const captionFailures = [];

  for (const partition of ['train', 'val', 'test']) {
    const entries = await loadSplitPartition(projectRoot, manifest.source_split_id, partition);

    for (const entry of entries) {
      const record = await loadRecord(recordsDir, entry.record_id);
      if (!record) {
        missingRecords.push({ record_id: entry.record_id, stage: 'training-package', partition });
        continue;
      }

      const prompt = record.provenance?.prompt || '';
      const lane = detectLane(record.id, prompt, config.lanes);
      const group = detectGroup(record.id, prompt, config.terminology);

      let row;
      try {
        row = recordToRow(record, lane, group, profile, partition);
      } catch (err) {
        // Only batch STRUCTURED/expected failures (SdlabError) — an
        // unexpected bug should still crash loud with its real stack
        // instead of being swallowed into a friendly summary.
        if (!(err instanceof SdlabError)) throw err;
        captionFailures.push({ record_id: entry.record_id, partition, message: err.message });
        continue;
      }
      if (row) rows.push(row);
    }
  }

  // F3: hard-fail — training packages sit on the same Law 4 ("exports are
  // reproducible") contract export.js does, one layer further downstream;
  // see export.js's EXPORT_MISSING_RECORDS guard for the full rationale on
  // why this escalates to a thrown error rather than the warn()-and-ledger
  // pattern used in split.js / implementation-packs.js. Checked before the
  // Windows symlink guard, row-safety validation, and claimIdDir below, so
  // a doomed build never reserves a package id or touches the filesystem.
  if (missingRecords.length > 0) {
    const sample = missingRecords.slice(0, 10).map(m => `${m.record_id} (${m.partition})`);
    throw inputError(
      'TRAINING_PACKAGE_MISSING_RECORDS',
      `${missingRecords.length} record(s) referenced by split "${manifest.source_split_id}" could not be loaded from ${recordsDir} — this training package would silently contain fewer rows than the split promised.` +
      (missingRecords.length > 10
        ? ` First 10: ${sample.join(', ')}, ...`
        : ` Missing: ${sample.join(', ')}.`),
      'Record file(s) were likely deleted after the split was created. Restore the missing file(s), or create a fresh snapshot/split reflecting current on-disk records before building a training package.',
    );
  }

  // H3: aggregated caption-failure report — see the captionFailures
  // declaration above. Checked alongside missingRecords, before claimIdDir,
  // so this also never reserves a package id or touches the filesystem.
  if (captionFailures.length > 0) {
    const sample = captionFailures.slice(0, 10).map(f => `${f.record_id} (${f.partition}): ${f.message}`);
    throw inputError(
      'TRAINING_PACKAGE_CAPTION_FAILURES',
      `${captionFailures.length} record(s) failed to caption while building this training package.\n` +
      sample.join('\n') +
      (captionFailures.length > 10 ? `\n...and ${captionFailures.length - 10} more.` : ''),
      'Fix the offending record(s) — commonly: populate canon.subject on records using caption_strategy ' +
      '"subject-natural-language" — then retry. Every failure is listed above so this can be fixed in one ' +
      'pass instead of one rerun per offender.',
    );
  }

  // Apply profile filters (eligible_lanes + entity_id_scope — D8).
  // filterRowsForProfile returns rows where lane ∈ eligible_lanes AND
  // entity_id === entity_id_scope (when set). Zero filters = identity.
  const filteredRows = filterRowsForProfile(rows, profile);
  for (const row of filteredRows) {
    if (partitionCounts[row.partition] !== undefined) partitionCounts[row.partition]++;
  }
  const totalRecords = filteredRows.length;
  let totalImages = 0;

  // SDL-C5: mirror export.js's D-008 Windows guard. Symlink mode on
  // Windows without admin/Developer Mode fails on every single row
  // (EPERM) — unguarded, that meant imageCount stayed 0, every
  // metadata/<partition>.jsonl came out empty, and the command still
  // exited 0 printing "Images: 0". Refuse upfront instead of limping
  // through an all-rows-fail package that LOOKS like success.
  if (!options.copy && platform() === 'win32' && filteredRows.length > 0) {
    throw inputError(
      'SYMLINK_UNSUPPORTED_WINDOWS',
      'Symlink mode is not supported on Windows training-package builds (target semantics differ and break on archive/transfer).',
      'Re-run with --copy to produce a portable, self-contained training package.',
    );
  }

  // SDL-H5 / SDL-H6: validate every row BEFORE any adapter touches the
  // filesystem. export.js already guards asset_path against traversal
  // (D-007) and now guards the id that becomes the destination filename
  // (SDL-H5); this ports the exact same checks (same error codes) to the
  // training-package path, which previously only checked existsSync — a
  // traversal path satisfies existsSync just as well as a legitimate one.
  // Centralized here once, per the finding's own suggestion, rather than
  // duplicated per-adapter — though each adapter ALSO carries the same
  // guard directly (see lib/adapters/*.js) as defense-in-depth for a
  // caller that invokes adapter.buildPackage without going through this
  // function (e.g. the adapters' own unit tests, or a future canon-build
  // caller — see lib/rows.js's documented second row producer).
  for (const row of filteredRows) {
    assertSafeId(row.entity_id, `row.entity_id for training package (asset_path "${row.asset_path}")`);
    assertSafeAssetPath(row.asset_path, projectRoot, row.entity_id);
  }

  // SDL-M10: atomically claim the training-package id/dir — closes the
  // check-then-act race the old existsSync+recursive-mkdir pattern had
  // (D-005's intent, now actually race-proof; see claimIdDir in
  // snapshot.js). Deferred to here (rather than claimed at the top of the
  // function) since nothing above this point actually needs packageId —
  // no point reserving one before the Windows guard / row validation have
  // had a chance to reject the build outright.
  const { id: packageId, dir: packageDir } = await claimIdDir(
    join(projectRoot, 'training', 'packages'),
    generatePackageId,
    {
      code: 'TRAINING_PACKAGE_ID_COLLISION',
      message: 'Could not claim a unique training-package ID — every candidate collided with an existing package directory.',
      hint: 'Retry; if this persists, another sdlab process may be creating training packages in a tight loop.',
    },
  );

  // Let the adapter build the package layout from the canonical rows.
  const adapterResult = await adapter.buildPackage({
    packageDir,
    rows: filteredRows,
    profile,
    manifest,
    config,
    projectRoot,
    copy: options.copy || false,
  });

  totalImages = adapterResult.imageCount || 0;
  // SDL-C5: DB-002-style accounting, ported from export.js — a caught
  // per-row copy/symlink failure must be visible, not silently dropped
  // alongside its metadata row and caption sidecar via a bare
  // `catch { continue; }`. The adapter itself already emitted a warn()
  // (it has the precise per-row context); this builds the PERSISTED
  // record on the package manifest so the failure survives after the
  // terminal scrolls, without re-printing the same stderr line twice.
  const imagesFailed = adapterResult.imagesFailed || [];
  const warnings = [];
  if (imagesFailed.length > 0) {
    const sample = imagesFailed.slice(0, 10).map(f => `${f.record_id} (${f.reason})`);
    const msg =
      `training-package: ${imagesFailed.length} of ${filteredRows.length} rows failed to place` +
      (imagesFailed.length > 10 ? ` — first 10: ${sample.join(', ')}, ...` : ` — ${sample.join(', ')}`);
    warnings.push(msg);
  }

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
    warnings,
    counts: {
      total_records: totalRecords,
      train: partitionCounts.train,
      val: partitionCounts.val,
      test: partitionCounts.test,
      images: totalImages,
      // SDL-C5: expected/actual/failed breakdown (export.js DB-002 shape)
      // so a partially- or totally-failed placement is visible in the
      // manifest, not just inferable from a suspiciously-low `images`.
      images_expected: filteredRows.length,
      images_actual: totalImages,
      images_failed: imagesFailed.length,
      checksums: 0, // updated after checksum pass below
    },
    // SDL-C5: record-level failure detail for operator triage.
    images_failed: imagesFailed,
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
