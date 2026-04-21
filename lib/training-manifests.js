/**
 * Training manifest management.
 *
 * A training manifest is a frozen, versioned contract for one training attempt.
 * It captures the exact export package, split, profile, and config fingerprint
 * so the training run is fully reproducible.
 */

import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
import { loadExport } from './export.js';
import { loadTrainingProfile } from './training-profiles.js';
import { computeConfigFingerprint } from './snapshot.js';
import { listEvalPacks } from './eval-pack.js';
import { inputError } from './errors.js';

/**
 * Generate a training manifest ID: tm-YYYYMMDD-HHMMSS-XXXX
 */
function generateManifestId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = randomBytes(2).toString('hex');
  return `tm-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

/**
 * Compute SHA-256 of a file's contents.
 */
async function hashFile(filePath) {
  const data = await readFile(filePath);
  return createHash('sha256').update(data).digest('hex');
}

/**
 * Create a training manifest from an export package and training profile.
 *
 * @param {string} projectRoot
 * @param {string} exportId
 * @param {string} profileId
 * @param {Object} options — { baseModel?, adapterTarget?, hyperparameters?, captionMode? }
 * @returns {Promise<{manifestId: string, exportId: string, profileId: string}>}
 */
export async function createTrainingManifest(projectRoot, exportId, profileId, options = {}) {
  const profile = await loadTrainingProfile(projectRoot, profileId);
  const exportManifest = await loadExport(projectRoot, exportId);

  // Hash the export manifest for integrity
  const exportManifestPath = join(projectRoot, 'exports', exportId, 'manifest.json');
  const exportManifestHash = await hashFile(exportManifestPath);

  // Determine adapter target
  const adapterTarget = options.adapterTarget || profile.adapter_targets[0];
  if (!profile.adapter_targets.includes(adapterTarget)) {
    throw new Error(
      `Adapter target "${adapterTarget}" not in profile's adapter_targets: [${profile.adapter_targets.join(', ')}]`
    );
  }

  // Find linked eval packs
  const evalPacks = await listEvalPacks(projectRoot);
  const linkedEvalPackIds = evalPacks.map(p => p.id);

  const manifestId = generateManifestId();
  const manifest = {
    training_manifest_id: manifestId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-training-manifest-v1',
    project_id: exportManifest.project,
    training_profile_id: profileId,
    source_export_id: exportId,
    source_snapshot_id: exportManifest.snapshot_id,
    source_split_id: exportManifest.split_id,
    config_fingerprint: computeConfigFingerprint(projectRoot),
    export_manifest_hash: exportManifestHash,
    dataset_counts: exportManifest.counts,
    base_model: options.baseModel || profile.base_model_recommendations?.[0] || null,
    adapter_target: adapterTarget,
    hyperparameters: options.hyperparameters || {},
    caption_mode: options.captionMode || profile.caption_strategy || 'filename',
    expected_outputs: {
      asset_type: profile.asset_type,
      target_family: profile.target_family,
    },
    linked_eval_pack_ids: linkedEvalPackIds,
  };

  // Write manifest
  const dir = join(projectRoot, 'training', 'manifests');
  await mkdir(dir, { recursive: true });
  const manifestPath = join(dir, `${manifestId}.json`);
  // D-005: refuse to silently overwrite on ID collision.
  if (existsSync(manifestPath)) {
    throw inputError(
      'TRAINING_MANIFEST_ID_COLLISION',
      `Training manifest file already exists: ${manifestPath}`,
      'Retry to generate a fresh manifest ID.',
    );
  }
  await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');

  return { manifestId, exportId, profileId };
}

/**
 * Validate a training manifest against current project state.
 * Checks that referenced artifacts still exist and fingerprints match.
 *
 * @returns {{ valid: boolean, issues: string[] }}
 */
export async function validateTrainingManifest(projectRoot, manifestId) {
  const manifest = await loadTrainingManifest(projectRoot, manifestId);
  const issues = [];

  // Check export exists
  const exportPath = join(projectRoot, 'exports', manifest.source_export_id, 'manifest.json');
  if (!existsSync(exportPath)) {
    issues.push(`source export "${manifest.source_export_id}" not found`);
  } else {
    // Check export hash
    const currentHash = await hashFile(exportPath);
    if (currentHash !== manifest.export_manifest_hash) {
      issues.push(`export manifest hash mismatch — export may have been modified`);
    }
  }

  // Check config fingerprint
  const currentFingerprint = computeConfigFingerprint(projectRoot);
  if (currentFingerprint !== manifest.config_fingerprint) {
    issues.push(`config fingerprint mismatch — project config has changed since manifest creation`);
  }

  // Check training profile exists
  const profilePath = join(projectRoot, 'training', 'profiles', `${manifest.training_profile_id}.json`);
  if (!existsSync(profilePath)) {
    issues.push(`training profile "${manifest.training_profile_id}" not found`);
  }

  return { valid: issues.length === 0, issues };
}

/**
 * Load a training manifest.
 */
export async function loadTrainingManifest(projectRoot, manifestId) {
  const path = join(projectRoot, 'training', 'manifests', `${manifestId}.json`);
  if (!existsSync(path)) {
    throw new Error(`Training manifest "${manifestId}" not found at ${path}`);
  }
  return JSON.parse(await readFile(path, 'utf-8'));
}

/**
 * List all training manifests in a project.
 */
export async function listTrainingManifests(projectRoot) {
  const dir = join(projectRoot, 'training', 'manifests');
  if (!existsSync(dir)) return [];

  const files = (await readdir(dir)).filter(f => f.endsWith('.json')).sort();
  const manifests = [];

  for (const file of files) {
    try {
      const data = JSON.parse(await readFile(join(dir, file), 'utf-8'));
      manifests.push({
        id: data.training_manifest_id,
        created_at: data.created_at,
        profile: data.training_profile_id,
        export_id: data.source_export_id,
        adapter: data.adapter_target,
        records: data.dataset_counts?.records || 0,
      });
    } catch {
      // Skip malformed
    }
  }

  return manifests.sort((a, b) => a.created_at.localeCompare(b.created_at));
}
