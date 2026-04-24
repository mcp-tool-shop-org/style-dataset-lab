/**
 * Generic image+caption adapter.
 *
 * Consumes canonical rows (per D6) and emits:
 *   dataset/<partition>/<entity_id>.<ext>  — image (copied or symlinked)
 *   metadata/<partition>.jsonl             — per-row audit (caption inline)
 *
 * No caption sidecar files — this adapter keeps metadata flat and
 * machine-readable. Use diffusers-lora or ai-toolkit for trainer-specific
 * caption-file conventions.
 */

import { writeFile, mkdir, symlink, copyFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { existsSync } from 'node:fs';
import { groupRowsByPartition } from '../rows.js';

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

      metadataRows.push({
        file: `dataset/${partition}/${filename}`,
        record_id: row.entity_id,
        caption: row.caption,
        lane: row.lane,
        group: row.group ?? null,
        pass_ratio: row.pass_ratio ?? null,
      });
    }

    await writeFile(
      join(metadataDir, `${partition}.jsonl`),
      metadataRows.map(r => JSON.stringify(r)).join('\n') + (metadataRows.length ? '\n' : '')
    );
  }

  return { imageCount };
}
