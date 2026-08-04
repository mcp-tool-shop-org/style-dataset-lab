/**
 * Training manifest management.
 *
 * A training manifest is a frozen, versioned contract for one training attempt.
 * It captures the exact export package, split, profile, and config fingerprint
 * so the training run is fully reproducible.
 */

import { readFile, writeFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
import { loadExport } from './export.js';
import { loadTrainingProfile } from './training-profiles.js';
import { computeConfigFingerprint, SCHEMA_VERSION, checkManifestVersion, claimIdFile } from './snapshot.js';
import { listEvalPacks } from './eval-pack.js';

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
 * SDL-H9: parse a BSD-style checksums.txt (`SHA256 (path) = hash` per
 * line, as written by export.js and training-packages.js) into
 * {relPath, hash} entries. Tolerates stray/blank lines rather than
 * throwing, since this file is meant to be human-readable too.
 */
function parseChecksumsFile(text) {
  const entries = [];
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const match = /^SHA256 \((.+)\) = ([0-9a-fA-F]{64})$/.exec(trimmed);
    if (!match) continue;
    entries.push({ relPath: match[1], hash: match[2].toLowerCase() });
  }
  return entries;
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

  // SDL-H9: export_manifest_hash above covers ONLY manifest.json — a file
  // that does not include image bytes. checksums.txt (written by
  // export.js after the manifest, D-015) covers every file in the export,
  // including images, so bind to it too when present. `include_checksums`
  // is a profile-controlled export option — an export built without it
  // simply has nothing to bind here, which is not itself an error.
  const exportChecksumsPath = join(projectRoot, 'exports', exportId, 'checksums.txt');
  const exportChecksumsHash = existsSync(exportChecksumsPath)
    ? await hashFile(exportChecksumsPath)
    : null;

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

  // Deferred so the id can be plugged in per-attempt by claimIdFile below
  // (a training manifest is a flat file, not a directory — see claimIdFile
  // in snapshot.js for why the atomic primitive differs from the other
  // artifacts in this domain).
  const buildContent = (id) => JSON.stringify({
    // DB-001 / DB-006: stamp manifest schema version
    schema_version: SCHEMA_VERSION,
    training_manifest_id: id,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-training-manifest-v1',
    project_id: exportManifest.project,
    training_profile_id: profileId,
    source_export_id: exportId,
    source_snapshot_id: exportManifest.snapshot_id,
    source_split_id: exportManifest.split_id,
    config_fingerprint: computeConfigFingerprint(projectRoot),
    export_manifest_hash: exportManifestHash,
    // SDL-H9: the binding hash that actually covers image bytes. null
    // when the source export was built with include_checksums: false.
    export_checksums_hash: exportChecksumsHash,
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
  }, null, 2) + '\n';

  // SDL-M10: atomically claim the manifest file — closes the
  // check-then-act race the old existsSync+writeFile pattern had (D-005's
  // intent, now actually race-proof).
  const { id: manifestId } = await claimIdFile(
    join(projectRoot, 'training', 'manifests'),
    generateManifestId,
    buildContent,
    {
      code: 'TRAINING_MANIFEST_ID_COLLISION',
      message: 'Could not claim a unique training-manifest ID — every candidate collided with an existing manifest file.',
      hint: 'Retry; if this persists, another sdlab process may be creating training manifests in a tight loop.',
    },
  );

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
    // Check export hash — NOTE: manifest.json alone does not include image
    // bytes (SDL-H9); see the checksums.txt re-verification below for the
    // check that actually catches a replaced image.
    const currentHash = await hashFile(exportPath);
    if (currentHash !== manifest.export_manifest_hash) {
      issues.push(`export manifest hash mismatch — export may have been modified`);
    }
  }

  // SDL-H9: export_manifest_hash (above) never covered image bytes —
  // checksums.txt does. Re-verify it two ways:
  //   1. binding check — checksums.txt's own hash still matches what was
  //      captured at training-manifest creation time (only meaningful for
  //      manifests created after SDL-H9, when export_checksums_hash was
  //      first captured).
  //   2. full re-verification — every individual file checksums.txt
  //      records is re-hashed against its CURRENT on-disk content. This is
  //      the check that actually catches "an image was silently replaced
  //      after export": checksums.txt's own bytes don't change just
  //      because a file it lists was overwritten, so step 1 alone cannot
  //      see it. Runs whenever checksums.txt exists, independent of
  //      whether this manifest predates export_checksums_hash, so it also
  //      retroactively protects manifests created before this fix.
  const exportChecksumsPath = join(projectRoot, 'exports', manifest.source_export_id, 'checksums.txt');
  if (manifest.export_checksums_hash && !existsSync(exportChecksumsPath)) {
    issues.push(`export checksums.txt not found at ${exportChecksumsPath} — export may have been modified (checksums.txt removed)`);
  } else if (existsSync(exportChecksumsPath)) {
    if (manifest.export_checksums_hash) {
      const currentChecksumsHash = await hashFile(exportChecksumsPath);
      if (currentChecksumsHash !== manifest.export_checksums_hash) {
        issues.push(`export checksums.txt hash mismatch — the checksum manifest itself has changed since this training manifest was created`);
      }
    }

    const exportDir = join(projectRoot, 'exports', manifest.source_export_id);
    const checksumsText = await readFile(exportChecksumsPath, 'utf-8');
    const entries = parseChecksumsFile(checksumsText);
    const missing = [];
    const mismatched = [];
    for (const entry of entries) {
      const filePath = join(exportDir, entry.relPath);
      if (!existsSync(filePath)) {
        missing.push(entry.relPath);
        continue;
      }
      const currentFileHash = await hashFile(filePath);
      if (currentFileHash !== entry.hash) {
        mismatched.push(entry.relPath);
      }
    }
    if (missing.length > 0) {
      const sample = missing.slice(0, 5).join(', ');
      issues.push(
        `export file(s) referenced by checksums.txt are missing: ${sample}` +
        (missing.length > 5 ? `, ... (${missing.length} total)` : ''),
      );
    }
    if (mismatched.length > 0) {
      const sample = mismatched.slice(0, 5).join(', ');
      issues.push(
        `export file(s) modified since export — content hash no longer matches checksums.txt: ${sample}` +
        (mismatched.length > 5 ? `, ... (${mismatched.length} total)` : ''),
      );
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
  const manifest = JSON.parse(await readFile(path, 'utf-8'));
  checkManifestVersion(manifest, 'training-manifest');
  return manifest;
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
