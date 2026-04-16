/**
 * Diffusers LoRA adapter.
 *
 * Produces a layout compatible with diffusers fine-tuning scripts:
 * - dataset/<partition>/ with image files
 * - dataset/<partition>/<image>.txt caption sidecar files
 * - metadata/<partition>.jsonl with structured rows
 *
 * Does not mutate inclusion or split truth.
 */

import { writeFile, mkdir, symlink, copyFile } from 'node:fs/promises';
import { join, relative, basename } from 'node:path';
import { existsSync } from 'node:fs';

/**
 * Build a diffusers-style caption from record metadata.
 */
function buildCaption(record, lane, group, profile) {
  const parts = [];

  // Trigger word for LoRA activation
  if (profile.prompt_strategy === 'trigger-word' && profile.profile_id) {
    parts.push(profile.profile_id.replace(/-/g, '_'));
  }

  // Subject identity if available
  if (record.identity?.subject_name) {
    parts.push(record.identity.subject_name.replace(/_/g, ' '));
  }

  // Faction / group
  if (group && group !== 'unknown') {
    parts.push(`${group} faction`);
  }

  // Lane context
  if (lane) parts.push(lane);

  // Use original prompt if available, otherwise build from ID
  const prompt = record.provenance?.prompt;
  if (prompt) {
    parts.push(prompt.slice(0, 300));
  } else {
    parts.push(record.id.replace(/_/g, ' '));
  }

  return parts.join(', ');
}

/**
 * Build training package in diffusers LoRA format.
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
      const stem = filename.replace(/\.[^.]+$/, '');
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

      // Write caption sidecar (.txt next to image)
      const caption = buildCaption(record, lane, group, profile);
      await writeFile(join(datasetDir, `${stem}.txt`), caption + '\n');

      metadataRows.push({
        file: `dataset/${partition}/${filename}`,
        caption_file: `dataset/${partition}/${stem}.txt`,
        record_id: record.id,
        caption,
        lane,
        group,
        subject: record.identity?.subject_name || null,
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
