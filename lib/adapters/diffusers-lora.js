/**
 * Diffusers LoRA adapter.
 *
 * Consumes canonical rows (per D6) — either produced in memory by
 * training-packages.js from records, or read from a canon-build
 * dataset.jsonl. The row shape is defined in lib/rows.js and pinned by
 * ROW_SCHEMA_VERSION.
 *
 * Output layout (unchanged from pre-refactor):
 *   dataset/<partition>/<entity_id>.<ext>        — image (copied or symlinked)
 *   dataset/<partition>/<entity_id>.txt          — caption sidecar
 *   metadata/<partition>.jsonl                   — per-row audit
 */

import { writeFile, mkdir, symlink, copyFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { existsSync } from 'node:fs';
import { groupRowsByPartition } from '../rows.js';

/**
 * Build training package in diffusers LoRA format from canonical rows.
 *
 * @param {Object} args
 * @param {string} args.packageDir
 * @param {Array<Object>} args.rows — canonical rows; partition field groups them
 * @param {Object} args.profile
 * @param {Object} args.manifest
 * @param {Object} args.config
 * @param {string} args.projectRoot
 * @param {boolean} [args.copy]
 */
export async function buildPackage({ packageDir, rows, profile, manifest, config, projectRoot, copy }) {
  const partitioned = groupRowsByPartition(rows || []);

  let imageCount = 0;

  for (const [partition, partitionRows] of Object.entries(partitioned)) {
    const datasetDir = join(packageDir, 'dataset', partition);
    const metadataDir = join(packageDir, 'metadata');
    await mkdir(datasetDir, { recursive: true });
    await mkdir(metadataDir, { recursive: true });

    const metadataRows = [];

    for (const row of partitionRows) {
      if (!row.asset_path) continue;

      const sourcePath = join(projectRoot, row.asset_path);
      if (!existsSync(sourcePath)) continue;

      const sourceBasename = row.asset_path.split(/[\\/]/).pop();
      const extMatch = sourceBasename.match(/\.[^.]+$/);
      const ext = extMatch ? extMatch[0] : '';
      const filename = `${row.entity_id}${ext}`;
      const stem = row.entity_id;
      const destPath = join(datasetDir, filename);

      try {
        if (copy) {
          await copyFile(sourcePath, destPath);
        } else {
          await symlink(relative(datasetDir, sourcePath), destPath);
        }
        imageCount++;
      } catch {
        continue;
      }

      await writeFile(join(datasetDir, `${stem}.txt`), row.caption + '\n');

      metadataRows.push(buildMetadataRow(row, partition, filename, stem));
    }

    await writeFile(
      join(metadataDir, `${partition}.jsonl`),
      metadataRows.map(r => JSON.stringify(r)).join('\n') + (metadataRows.length ? '\n' : '')
    );
  }

  return { imageCount };
}

function buildMetadataRow(row, partition, filename, stem) {
  const out = {
    file: `dataset/${partition}/${filename}`,
    caption_file: `dataset/${partition}/${stem}.txt`,
    record_id: row.entity_id,
    caption: row.caption,
    lane: row.lane,
    group: row.group ?? null,
    subject: row.subject_filter_key ?? null,
    pass_ratio: row.pass_ratio ?? null,
  };
  return out;
}
