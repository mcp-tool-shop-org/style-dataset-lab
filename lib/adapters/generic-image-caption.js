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
import { assertSafeAssetPath, assertSafeId } from '../export.js';
import { warn } from '../log.js';

export async function buildPackage({ packageDir, rows, profile, manifest, config, projectRoot, copy }) {
  const partitioned = groupRowsByPartition(rows || []);

  let imageCount = 0;
  // SDL-C5: per-row failure accounting (export.js DB-002 shape). The old
  // bare `catch { continue; }` silently dropped the image, the caption
  // sidecar, AND the metadata row together with no logging — on Windows
  // without Developer Mode this fired on every row, so imageCount stayed
  // 0 and the build still reported success. Every drop is now accounted
  // for and returned to the caller.
  const imagesFailed = [];

  for (const [partition, partitionRows] of Object.entries(partitioned)) {
    const datasetDir = join(packageDir, 'dataset', partition);
    const metadataDir = join(packageDir, 'metadata');
    await mkdir(datasetDir, { recursive: true });
    await mkdir(metadataDir, { recursive: true });

    const metadataRows = [];

    for (const row of partitionRows) {
      if (!row.asset_path) {
        imagesFailed.push({ record_id: row.entity_id, partition, reason: 'missing_asset_path' });
        continue;
      }

      // SDL-H5 / SDL-H6: defense-in-depth. buildTrainingPackage validates
      // every row before dispatching here, but this adapter is also
      // unit-tested (and documented in lib/rows.js as a future direct
      // canon-build target) independent of that caller, so the guard
      // lives here too. A traversal / unsafe id is a security boundary,
      // not an operational hiccup — it throws (hard fail) rather than
      // joining the soft imagesFailed accounting below.
      assertSafeId(row.entity_id, `row.entity_id in generic-image-caption adapter (partition "${partition}")`);
      const sourcePath = assertSafeAssetPath(row.asset_path, projectRoot, row.entity_id);

      if (!existsSync(sourcePath)) {
        imagesFailed.push({ record_id: row.entity_id, partition, reason: 'source_missing' });
        continue;
      }

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
      } catch (err) {
        imagesFailed.push({
          record_id: row.entity_id,
          partition,
          reason: copy ? 'copy_failed' : 'link_failed',
          detail: err.message,
        });
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

  if (imagesFailed.length > 0) {
    const sample = imagesFailed.slice(0, 10).map(f => `${f.record_id} (${f.reason})`);
    warn(
      `generic-image-caption adapter: ${imagesFailed.length} of ${imageCount + imagesFailed.length} rows failed to place` +
      (imagesFailed.length > 10 ? ` — first 10: ${sample.join(', ')}, ...` : ` — ${sample.join(', ')}`),
    );
  }

  return { imageCount, imagesFailed };
}
