/**
 * Re-ingest engine for generated outputs.
 *
 * Accepted generated outputs re-enter the project as new records
 * with provenance fields linking back to the training manifest.
 * No bypass around review — generated work must be curated and
 * canon-bound like everything else.
 */

import { readFile, writeFile, readdir, stat } from 'node:fs/promises';
import { join, basename, extname } from 'node:path';
import { existsSync } from 'node:fs';
import { loadTrainingManifest } from './training-manifests.js';
import { buildBaseRecord } from './records.js';

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp']);

/**
 * Re-ingest generated outputs from a directory into the project.
 *
 * Each image in the source directory becomes a new record with:
 * - provenance.source = "generated"
 * - provenance.training_manifest_id = <manifest-id>
 * - judgment = null (must be reviewed)
 * - canon = null (must be bound)
 *
 * @param {string} projectRoot
 * @param {string} sourcePath — directory containing generated images
 * @param {string} manifestId — training manifest that produced them
 * @param {Object} options — { dryRun? }
 * @returns {Promise<{created: number, skipped: number, records: string[]}>}
 */
export async function reingestGenerated(projectRoot, sourcePath, manifestId, options = {}) {
  const manifest = await loadTrainingManifest(projectRoot, manifestId);
  const recordsDir = join(projectRoot, 'records');

  // Find image files in source directory
  const entries = await readdir(sourcePath);
  const imageFiles = entries
    .filter(f => IMAGE_EXTENSIONS.has(extname(f).toLowerCase()))
    .sort();

  const created = [];
  const skipped = [];

  for (const file of imageFiles) {
    const stem = basename(file, extname(file));
    const recordId = `gen_${stem}`;
    const recordPath = join(recordsDir, `${recordId}.json`);

    // Skip if record already exists
    if (existsSync(recordPath)) {
      skipped.push(recordId);
      continue;
    }

    const filePath = join(sourcePath, file);
    const fileStat = await stat(filePath);

    // Relative asset path from project root
    const assetPath = `outputs/candidates/${file}`;

    const provenance = {
      source: 'generated',
      training_manifest_id: manifestId,
      training_profile_id: manifest.training_profile_id,
      adapter_target: manifest.adapter_target,
      base_model: manifest.base_model || null,
      source_export_id: manifest.source_export_id,
      generated_at: new Date().toISOString(),
      original_path: filePath,
    };

    const record = buildBaseRecord(recordId, assetPath, {
      width: null,
      height: null,
      bytes: fileStat.size,
    }, provenance);

    record.schema_version = '2.1.0';

    if (!options.dryRun) {
      await writeFile(recordPath, JSON.stringify(record, null, 2) + '\n');
    }

    created.push(recordId);
  }

  return { created: created.length, skipped: skipped.length, records: created };
}

/**
 * Audit re-ingested records — check that they've been properly reviewed.
 *
 * @param {string} projectRoot
 * @returns {Promise<{total: number, reviewed: number, unreviewed: number, bound: number, unbound: number}>}
 */
export async function auditReingest(projectRoot) {
  const recordsDir = join(projectRoot, 'records');
  const files = (await readdir(recordsDir))
    .filter(f => f.startsWith('gen_') && f.endsWith('.json'))
    .sort();

  let reviewed = 0;
  let unreviewed = 0;
  let bound = 0;
  let unbound = 0;

  for (const file of files) {
    const record = JSON.parse(await readFile(join(recordsDir, file), 'utf-8'));

    if (record.judgment) {
      reviewed++;
      if (record.canon?.assertions?.length > 0) {
        bound++;
      } else {
        unbound++;
      }
    } else {
      unreviewed++;
    }
  }

  return {
    total: files.length,
    reviewed,
    unreviewed,
    bound,
    unbound,
  };
}
