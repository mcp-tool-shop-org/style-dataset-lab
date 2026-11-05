/**
 * Trained-LoRA provenance record (`train-run.json`) contract (DESIGN-v3 §7, G13).
 *
 * Links every trained LoRA checkpoint back to:
 *   - dataset_package_id + dataset_manifest_sha256
 *   - config_sha256 (ai-toolkit-config.yaml)
 *   - override_file + override_sha256 + upstream_issue (#1087)
 *   - base_model pin with cleared Apache-2.0 SPDX licence
 *   - window_id
 *   - steps, checkpoint_sha256s, sample_grid_sha256s
 *   - eval_pack_sha (attached once the eval pack runs)
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import {
  AI_TOOLKIT_UPSTREAM_ISSUE,
  assertNotHeldTrainingData,
  getAiToolkitOverrideMetadata,
} from './adapters/ai-toolkit.js';
import { inputError as rawInputError } from './errors.js';

function inputError(code, msg) {
  return rawInputError(code, `${code}: ${msg}`);
}

export const CLEARED_TRAIN_BASE_LICENCES = new Set([
  'Apache-2.0',
  'MIT',
  'BSD-2-Clause',
  'BSD-3-Clause',
  'CC0-1.0',
  'CC-BY-4.0',
]);

function normalizeSha256(val) {
  if (typeof val !== 'string') return null;
  const trimmed = val.trim().toLowerCase();
  const hex = trimmed.startsWith('sha256:') ? trimmed.slice(7) : trimmed;
  if (!/^[0-9a-f]{64}$/.test(hex)) return null;
  return `sha256:${hex}`;
}

/**
 * Build and validate a `train-run.json` record (§7, G13).
 *
 * @param {Object} opts
 * @returns {Object}
 */
export function buildTrainRunRecord(opts = {}) {
  const {
    run_id,
    window_id,
    dataset_package_id,
    dataset_manifest_sha256,
    config_sha256,
    override_file,
    override_sha256,
    upstream_issue = AI_TOOLKIT_UPSTREAM_ISSUE,
    base_model,
    steps = [],
    checkpoint_sha256s = {},
    sample_grid_sha256s = {},
    eval_pack_sha = null,
    created_at = new Date().toISOString(),
  } = opts;

  if (!run_id || typeof run_id !== 'string') {
    throw inputError('TRAIN_RUN_INVALID', 'train-run.json requires a non-empty "run_id".');
  }
  if (!window_id || typeof window_id !== 'string') {
    throw inputError('TRAIN_RUN_INVALID', 'train-run.json requires a non-empty "window_id".');
  }
  if (!dataset_package_id || typeof dataset_package_id !== 'string') {
    throw inputError('TRAIN_RUN_INVALID', 'train-run.json requires a non-empty "dataset_package_id".');
  }

  assertNotHeldTrainingData({
    profile: { profile_id: dataset_package_id },
    manifest: { source_export_id: run_id },
  });

  const normDatasetSha = normalizeSha256(dataset_manifest_sha256);
  const normConfigSha = normalizeSha256(config_sha256);
  const defaultOverride = getAiToolkitOverrideMetadata();
  const normOverrideSha = normalizeSha256(override_sha256 || defaultOverride.override_sha256);

  if (!normDatasetSha || !normConfigSha || !normOverrideSha) {
    throw inputError(
      'TRAIN_RUN_SHA_INVALID',
      'train-run.json requires valid 64-hex dataset_manifest_sha256, config_sha256, and override_sha256.'
    );
  }

  if (!base_model || typeof base_model !== 'object' || !base_model.name) {
    throw inputError('TRAIN_RUN_BASE_MODEL_INVALID', 'train-run.json requires a base_model object with name.');
  }
  const normBaseSha = normalizeSha256(base_model.sha256);
  if (!normBaseSha) {
    throw inputError('TRAIN_RUN_SHA_INVALID', 'base_model.sha256 must be a valid 64-hex sha256 digest.');
  }
  if (
    !base_model.licence_id ||
    !CLEARED_TRAIN_BASE_LICENCES.has(base_model.licence_id) ||
    !base_model.licence_url ||
    !base_model.date_read
  ) {
    throw inputError(
      'TRAIN_RUN_LICENCE_INVALID',
      `base_model "${base_model.name}" must carry a cleared commercial SPDX licence_id (${[...CLEARED_TRAIN_BASE_LICENCES].join(', ')}), licence_url, and date_read (got "${base_model.licence_id}").`
    );
  }

  if (!Array.isArray(steps) || steps.length === 0) {
    throw inputError('TRAIN_RUN_STEPS_EMPTY', 'train-run.json requires at least one checkpoint step.');
  }

  const normalizedCheckpoints = {};
  const normalizedSamples = {};
  for (const step of steps) {
    const key = String(step);
    const ckptSha = normalizeSha256(checkpoint_sha256s[key] ?? checkpoint_sha256s[step]);
    if (!ckptSha) {
      throw inputError(
        'TRAIN_RUN_SHA_INVALID',
        `Missing or invalid checkpoint_sha256 for step ${key}.`
      );
    }
    normalizedCheckpoints[key] = ckptSha;

    const gridRaw = sample_grid_sha256s[key] ?? sample_grid_sha256s[step];
    if (gridRaw !== undefined && gridRaw !== null) {
      const gridSha = normalizeSha256(gridRaw);
      if (!gridSha) {
        throw inputError(
          'TRAIN_RUN_SHA_INVALID',
          `Invalid sample_grid_sha256 for step ${key}.`
        );
      }
      normalizedSamples[key] = gridSha;
    }
  }

  const normEvalSha = eval_pack_sha ? normalizeSha256(eval_pack_sha) : null;
  if (eval_pack_sha && !normEvalSha) {
    throw inputError('TRAIN_RUN_SHA_INVALID', 'eval_pack_sha must be null or a valid 64-hex sha256 digest.');
  }

  return {
    run_id,
    window_id,
    lane: 'train',
    dataset_package_id,
    dataset_manifest_sha256: normDatasetSha,
    config_sha256: normConfigSha,
    override_file: override_file || defaultOverride.override_file,
    override_sha256: normOverrideSha,
    upstream_issue,
    base_model: {
      name: base_model.name,
      repo: base_model.repo || base_model.name,
      revision: base_model.revision || 'main',
      sha256: normBaseSha,
      licence_id: base_model.licence_id,
      licence_url: base_model.licence_url,
      date_read: base_model.date_read,
    },
    steps: steps.map(Number),
    checkpoint_sha256s: normalizedCheckpoints,
    sample_grid_sha256s: normalizedSamples,
    eval_pack_sha: normEvalSha,
    created_at,
  };
}

/**
 * Write `train-run.json` to disk.
 *
 * @param {string} trainRunPath
 * @param {Object} record
 * @returns {Object}
 */
export function writeTrainRunJson(trainRunPath, record) {
  const validated = buildTrainRunRecord(record);
  mkdirSync(dirname(trainRunPath), { recursive: true });
  writeFileSync(trainRunPath, JSON.stringify(validated, null, 2) + '\n', 'utf-8');
  return validated;
}

/**
 * Read and validate `train-run.json` from disk.
 *
 * @param {string} trainRunPath
 * @returns {Object}
 */
export function readTrainRunJson(trainRunPath) {
  const parsed = JSON.parse(readFileSync(trainRunPath, 'utf-8'));
  return buildTrainRunRecord(parsed);
}

/**
 * Attach `eval_pack_sha` to an existing `train-run.json` once the eval pack runs (G13).
 *
 * @param {string} trainRunPath
 * @param {string} evalPackSha
 * @returns {Object}
 */
export function attachEvalPackSha(trainRunPath, evalPackSha) {
  const current = readTrainRunJson(trainRunPath);
  return writeTrainRunJson(trainRunPath, {
    ...current,
    eval_pack_sha: evalPackSha,
  });
}
