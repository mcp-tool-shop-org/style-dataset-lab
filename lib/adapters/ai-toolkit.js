/**
 * Ostris ai-toolkit adapter.
 *
 * Produces a training package ai-toolkit (https://github.com/ostris/ai-toolkit)
 * can consume directly:
 *
 *   <package_dir>/
 *     dataset/<partition>/<record_id>.png
 *     dataset/<partition>/<record_id>.txt          (caption sidecar)
 *     metadata/<partition>.jsonl                   (audit rows)
 *     ai-toolkit-config.yaml                       (training config)
 *
 * Precondition: profile.target_family must be 'flux'. ai-toolkit does support
 * SDXL, but this adapter only emits Flux-shaped configs — callers using SDXL
 * should use diffusers-lora instead. Rejecting here keeps config output honest.
 *
 * Does not mutate inclusion or split truth.
 */

import { writeFile, mkdir, symlink, copyFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { existsSync } from 'node:fs';
import YAML from 'yaml';
import { buildCaption, deriveStyleTrigger } from '../captions.js';
import { inputError } from '../errors.js';

/**
 * Build training package in ai-toolkit format.
 */
export async function buildPackage({ packageDir, partitions, profile, manifest, config, projectRoot, copy }) {
  if (profile?.target_family !== 'flux') {
    throw inputError(
      'ADAPTER_TARGET_FAMILY_MISMATCH',
      `ai-toolkit adapter requires profile.target_family === 'flux' (got "${profile?.target_family}")`,
      'Use diffusers-lora for SDXL targets, or set target_family: "flux" on the profile.'
    );
  }

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

      // D-009: Name output files by record.id (not source basename) to
      // avoid silent collisions when two records share a filename stem.
      const sourceBasename = record.asset_path.split(/[\\/]/).pop();
      const extMatch = sourceBasename.match(/\.[^.]+$/);
      const ext = extMatch ? extMatch[0] : '';
      const filename = `${record.id}${ext}`;
      const stem = record.id;
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

  const aiToolkitConfig = buildAiToolkitConfig({ profile, manifest });
  await writeFile(
    join(packageDir, 'ai-toolkit-config.yaml'),
    YAML.stringify(aiToolkitConfig)
  );

  return { imageCount };
}

/**
 * Build the ai-toolkit YAML config object from a profile + manifest.
 *
 * Defaults follow ai-toolkit's published Flux examples and the 16GB-VRAM
 * ceiling documented in the slice-3 handoff. Users can override any field
 * by editing the emitted YAML before running ai-toolkit.
 */
export function buildAiToolkitConfig({ profile, manifest }) {
  const trigger = deriveStyleTrigger(profile) || profile.profile_id;
  const baseModel = profile.base_model_recommendations?.[0] || 'black-forest-labs/FLUX.1-dev';
  const sourceExportId = manifest?.source_export_id || 'unknown';

  // Per-profile training_hyperparameters override the World-LoRA-tuned defaults.
  // World LoRAs: rank 32, steps 2500 (style absorption across a domain).
  // Per-character LoRAs: rank 16, alpha 8, steps 2000 (identity on a single
  // subject — higher rank just overfits face details). See the two-LoRA stack
  // contract in the handbook + memory/two-lora-stack-research-2026-04-23.md.
  //
  // TODO (normalization): the implicit World-LoRA fallback is a transition-era
  // convenience for existing profiles that pre-date training_hyperparameters.
  // Once every shipping profile declares training_hyperparameters explicitly,
  // the ?? fallbacks can be removed in favor of a required block — preventing
  // the "is this World-tuned by omission or by intent?" ambiguity that grows
  // once a second World project exists.
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
          // ai-toolkit's is_style flag: true for world/style LoRAs that teach
          // aesthetics broadly; false (default) for subject LoRAs that teach a
          // specific character or object. Drives ai-toolkit's training
          // regularization — wrong value silently mistrains. See the two-LoRA
          // stack research (memory/two-lora-stack-research-2026-04-23.md) for
          // the World LoRA vs per-character LoRA convention.
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
