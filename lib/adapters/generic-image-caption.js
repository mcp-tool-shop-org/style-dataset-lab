/**
 * Generic image+caption adapter.
 *
 * Simple, inspectable, durable baseline:
 * - dataset/<partition>/ with image files
 * - metadata/<partition>.jsonl with one row per image
 *
 * Does not mutate inclusion or split truth.
 */

import { writeFile, mkdir, symlink, copyFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { existsSync } from 'node:fs';

/**
 * Build a caption string from a record and profile.
 */
function buildCaption(record, lane, group, profile) {
  const parts = [];

  if (profile.prompt_strategy === 'trigger-word' && profile.profile_id) {
    parts.push(profile.profile_id.replace(/-/g, '_'));
  }

  if (group) parts.push(group);
  if (lane) parts.push(lane);

  // Add key provenance if available
  const prompt = record.provenance?.prompt;
  if (prompt) {
    // Use first 200 chars of prompt as caption body
    parts.push(prompt.slice(0, 200));
  } else {
    parts.push(record.id.replace(/_/g, ' '));
  }

  return parts.join(', ');
}

/**
 * Build training package in generic image+caption format.
 */
export async function buildPackage({ packageDir, partitions, profile, manifest, config, projectRoot, copy }) {
  let imageCount = 0;

  for (const [partition, records] of Object.entries(partitions)) {
    const datasetDir = join(packageDir, 'dataset', partition);
    const metadataDir = join(packageDir, 'metadata');
    await mkdir(datasetDir, { recursive: true });
    await mkdir(metadataDir, { recursive: true });

    const metadataRows = [];

    for (const { record, lane, group } of records) {
      if (!record.asset_path) continue;

      const sourcePath = join(projectRoot, record.asset_path);
      if (!existsSync(sourcePath)) continue;

      const filename = record.asset_path.split('/').pop();
      const destPath = join(datasetDir, filename);

      try {
        if (copy) {
          await copyFile(sourcePath, destPath);
        } else {
          await symlink(relative(datasetDir, sourcePath), destPath);
        }
        imageCount++;
      } catch {
        continue; // skip duplicates or broken links
      }

      const caption = buildCaption(record, lane, group, profile);

      metadataRows.push({
        file: `dataset/${partition}/${filename}`,
        record_id: record.id,
        caption,
        lane,
        group,
        pass_ratio: record.canon?.assertion_count > 0
          ? +(record.canon.pass_count / record.canon.assertion_count).toFixed(3) : null,
      });
    }

    await writeFile(
      join(metadataDir, `${partition}.jsonl`),
      metadataRows.map(r => JSON.stringify(r)).join('\n') + '\n'
    );
  }

  return { imageCount };
}
