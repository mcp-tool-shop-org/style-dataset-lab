/**
 * Ostris ai-toolkit adapter (Flux + Qwen-Image target families, DESIGN-v3 §3.3, §3.5, G12).
 *
 * Consumes canonical rows (per D6) and emits a training package ai-toolkit
 * can consume directly:
 *
 *   <package_dir>/
 *     dataset/<partition>/<entity_id>.png
 *     dataset/<partition>/<entity_id>.txt          (caption sidecar)
 *     metadata/<partition>.jsonl                   (audit rows)
 *     ai-toolkit-config.yaml                       (training config)
 *
 * Precondition: profile.target_family must be 'flux' or 'qwen-image'.
 * Callers using SDXL should use diffusers-lora instead.
 */

import { createHash } from 'node:crypto';
import { writeFile, mkdir, symlink, copyFile } from 'node:fs/promises';
import { join, relative, dirname } from 'node:path';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';
import { deriveStyleTrigger } from '../captions.js';
import { groupRowsByPartition } from '../rows.js';
import { inputError } from '../errors.js';
import { assertSafeAssetPath, assertSafeId } from '../export.js';
import { warn } from '../log.js';

export const AI_TOOLKIT_UPSTREAM_ISSUE = 'https://github.com/ostris/ai-toolkit/issues/1087';

export const SUPPORTED_AI_TOOLKIT_FAMILIES = Object.freeze(['flux', 'qwen-image']);

const OVERRIDE_RELATIVE_PATH = 'scripts/colab/ai-toolkit-override-py315.txt';

const HELD_DATA_TOKENS = Object.freeze([
  'pls' + 'vessel',
  'nano' + '_banana',
  'nano' + '-banana',
]);

/**
 * Load metadata and sha256 for `scripts/colab/ai-toolkit-override-py315.txt` (§3.5, G12).
 *
 * @returns {{ override_file: string, override_sha256: string, upstream_issue: string, packages: string[] }}
 */
export function getAiToolkitOverrideMetadata() {
  const here = dirname(fileURLToPath(import.meta.url));
  const fullPath = join(here, '..', '..', 'scripts', 'colab', 'ai-toolkit-override-py315.txt');
  const raw = readFileSync(fullPath, 'utf-8');
  const normalized = raw.replace(/\r\n/g, '\n');
  const sha = 'sha256:' + createHash('sha256').update(normalized, 'utf-8').digest('hex');
  const packages = normalized
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'));
  return {
    override_file: OVERRIDE_RELATIVE_PATH,
    override_sha256: sha,
    upstream_issue: AI_TOOLKIT_UPSTREAM_ISSUE,
    packages,
  };
}

/**
 * Enforce that held Portlight training data (the 336 Nano Banana-derived pairs)
 * is never packaged or trained on (§1.2, §5.2, G12).
 *
 * @param {Object} opts
 * @param {Object} [opts.profile]
 * @param {Array<Object>} [opts.rows]
 * @param {Object} [opts.manifest]
 */
export function assertNotHeldTrainingData({ profile = {}, rows = [], manifest = {} } = {}) {
  const haystacks = [
    profile?.profile_id,
    profile?.trigger_override,
    profile?.label,
    manifest?.source_export_id,
    ...(Array.isArray(rows)
      ? rows.flatMap((r) => [r?.entity_id, r?.caption, r?.asset_path])
      : []),
  ]
    .filter(Boolean)
    .map((s) => String(s).toLowerCase());

  for (const text of haystacks) {
    for (const token of HELD_DATA_TOKENS) {
      if (text.includes(token)) {
        throw inputError(
          'AI_TOOLKIT_HELD_DATA_FORBIDDEN',
          `AI_TOOLKIT_HELD_DATA_FORBIDDEN: Refusing to build training package or config referencing held dataset token "${token}".`
        );
      }
    }
  }
}

/**
 * Build training package in ai-toolkit format from canonical rows.
 */
export async function buildPackage({ packageDir, rows, profile, manifest, config, projectRoot, copy }) {
  if (!SUPPORTED_AI_TOOLKIT_FAMILIES.includes(profile?.target_family)) {
    throw inputError(
      'ADAPTER_TARGET_FAMILY_MISMATCH',
      `ai-toolkit adapter requires profile.target_family === 'flux' or 'qwen-image' (got "${profile?.target_family}")`,
      'Use diffusers-lora for SDXL targets, or set target_family: "flux" or "qwen-image" on the profile.',
    );
  }

  assertNotHeldTrainingData({ profile, rows, manifest });

  const partitioned = groupRowsByPartition(rows || []);

  let imageCount = 0;
  // SDL-C5: per-row failure accounting (export.js DB-002 shape) — see
  // generic-image-caption.js for the full rationale. A caught copy/symlink
  // error must not silently drop the image, caption sidecar, AND metadata
  // row together with zero logging.
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

      // SDL-H5 / SDL-H6: defense-in-depth — see generic-image-caption.js
      // for the full rationale. Throws (hard fail) on traversal/unsafe id;
      // that is a security boundary, not an operational hiccup.
      assertSafeId(row.entity_id, `row.entity_id in ai-toolkit adapter (partition "${partition}")`);
      const sourcePath = assertSafeAssetPath(row.asset_path, projectRoot, row.entity_id);

      if (!existsSync(sourcePath)) {
        imagesFailed.push({ record_id: row.entity_id, partition, reason: 'source_missing' });
        continue;
      }

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
      } catch (err) {
        imagesFailed.push({
          record_id: row.entity_id,
          partition,
          reason: copy ? 'copy_failed' : 'link_failed',
          detail: err.message,
        });
        continue;
      }

      await writeFile(join(datasetDir, `${stem}.txt`), row.caption + '\n');

      metadataRows.push({
        file: `dataset/${partition}/${filename}`,
        caption_file: `dataset/${partition}/${stem}.txt`,
        record_id: row.entity_id,
        caption: row.caption,
        lane: row.lane,
        group: row.group ?? null,
        subject: row.subject_filter_key ?? null,
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
      `ai-toolkit adapter: ${imagesFailed.length} of ${imageCount + imagesFailed.length} rows failed to place` +
      (imagesFailed.length > 10 ? ` — first 10: ${sample.join(', ')}, ...` : ` — ${sample.join(', ')}`),
    );
  }

  const aiToolkitConfig = buildAiToolkitConfig({ profile, manifest });
  await writeFile(
    join(packageDir, 'ai-toolkit-config.yaml'),
    YAML.stringify(aiToolkitConfig)
  );

  return { imageCount, imagesFailed };
}

/**
 * Build the Qwen-Image ai-toolkit YAML config object (§3.3, §3.5, G12).
 */
export function buildQwenAiToolkitConfig({ profile, manifest }) {
  assertNotHeldTrainingData({ profile, manifest });
  const trigger = deriveStyleTrigger(profile) || profile.profile_id;
  const baseModel = profile.base_model_recommendations?.[0] || 'Qwen/Qwen-Image';
  const sourceExportId = manifest?.source_export_id || 'unknown';
  const overrideMeta = getAiToolkitOverrideMetadata();

  const hp = profile.training_hyperparameters || {};
  const linear = hp.rank ?? 16;
  const linearAlpha = hp.alpha ?? linear;
  const trainSteps = hp.steps ?? 1000;
  const lr = hp.lr ?? 1e-4;

  return {
    job: 'extension',
    config: {
      name: `${profile.profile_id}-${sourceExportId}`,
      process: [
        {
          type: 'sd_trainer',
          training_folder: 'output',
          device: 'cuda:0',
          trigger_word: trigger,
          network: {
            type: 'lora',
            linear: linear,
            linear_alpha: linearAlpha,
          },
          save: {
            dtype: 'float16',
            save_every: 250,
            max_step_saves_to_keep: 4,
          },
          datasets: [
            {
              folder_path: './dataset/train',
              caption_ext: 'txt',
              caption_dropout_rate: 0.05,
              shuffle_tokens: false,
              cache_latents_to_disk: true,
              resolution: [512, 768, 1024],
            },
          ],
          train: {
            batch_size: 1,
            steps: trainSteps,
            gradient_accumulation_steps: 1,
            train_unet: true,
            train_text_encoder: false,
            gradient_checkpointing: true,
            noise_scheduler: 'flowmatch',
            optimizer: 'adamw8bit',
            lr: lr,
            ema_config: {
              use_ema: true,
              ema_decay: 0.99,
            },
            dtype: 'bf16',
          },
          model: {
            name_or_path: baseModel,
            arch: 'qwen_image',
            quantize: true,
            qtype: 'qfloat8',
            quantize_te: true,
            qtype_te: 'qfloat8',
            low_vram: true,
          },
          is_style: profile.is_style_lora === true,
          sample: {
            sampler: 'flowmatch',
            sample_every: 250,
            width: 1024,
            height: 1024,
            prompts: [`${trigger} style sample prompt`],
            neg: '',
            seed: 42,
            walk_seed: true,
            guidance_scale: 3.5,
            sample_steps: 22,
          },
        },
      ],
    },
    meta: {
      name: profile.profile_id,
      version: '1.0',
      target_family: 'qwen-image',
      base_licence_id: 'Apache-2.0',
      override_file: overrideMeta.override_file,
      override_sha256: overrideMeta.override_sha256,
      upstream_issue: overrideMeta.upstream_issue,
    },
  };
}

/**
 * Build the ai-toolkit YAML config object from a profile + manifest.
 *
 * Dispatches to `buildQwenAiToolkitConfig` when `profile.target_family === 'qwen-image'`;
 * otherwise emits the Flux-shaped config.
 */
export function buildAiToolkitConfig({ profile, manifest }) {
  assertNotHeldTrainingData({ profile, manifest });
  if (profile?.target_family === 'qwen-image') {
    return buildQwenAiToolkitConfig({ profile, manifest });
  }

  const trigger = deriveStyleTrigger(profile) || profile.profile_id;
  const baseModel = profile.base_model_recommendations?.[0] || 'black-forest-labs/FLUX.1-dev';
  const sourceExportId = manifest?.source_export_id || 'unknown';

  const hp = profile.training_hyperparameters || {};
  const linear = hp.rank ?? 32;
  const linearAlpha = hp.alpha ?? linear;
  const trainSteps = hp.steps ?? 2500;

  return {
    job: 'extension',
    config: {
      name: `${profile.profile_id}-${sourceExportId}`,
      process: [
        {
          type: 'sd_trainer',
          training_folder: 'output',
          device: 'cuda:0',
          network: {
            type: 'lora',
            linear: linear,
            linear_alpha: linearAlpha,
          },
          save: {
            dtype: 'float16',
            save_every: 250,
            max_step_saves_to_keep: 4,
          },
          datasets: [
            {
              folder_path: './dataset/train',
              caption_ext: 'txt',
              caption_dropout_rate: 0.05,
              shuffle_tokens: false,
              cache_latents_to_disk: true,
              resolution: [512, 768, 1024],
            },
          ],
          train: {
            batch_size: 1,
            steps: trainSteps,
            gradient_accumulation_steps: 1,
            train_unet: true,
            train_text_encoder: false,
            gradient_checkpointing: true,
            noise_scheduler: 'flowmatch',
            optimizer: 'adamw8bit',
            lr: 4e-4,
            ema_config: {
              use_ema: true,
              ema_decay: 0.99,
            },
            dtype: 'bf16',
          },
          model: {
            name_or_path: baseModel,
            is_flux: true,
            quantize: true,
          },
          is_style: profile.is_style_lora === true,
          sample: {
            sampler: 'flowmatch',
            sample_every: 250,
            width: 1024,
            height: 1024,
            prompts: [`${trigger} style sample prompt`],
            neg: '',
            seed: 42,
            walk_seed: true,
            guidance_scale: 4,
            sample_steps: 20,
          },
        },
      ],
    },
    meta: {
      name: profile.profile_id,
      version: '1.0',
    },
  };
}
