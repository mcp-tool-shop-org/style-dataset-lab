/**
 * Training profile management.
 *
 * A training profile defines how a project wants to turn an export package
 * into a trainable model asset. Profiles never select data directly — they
 * define eligibility rules and packaging expectations.
 */

import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { isRegisteredAdapter, listAdapters } from './training-adapters.js';

const REQUIRED_FIELDS = ['profile_id', 'label', 'target_family', 'asset_type', 'eligible_lanes', 'adapter_targets'];

/**
 * Validate a training profile object.
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateProfile(profile) {
  const errors = [];
  for (const field of REQUIRED_FIELDS) {
    if (profile[field] === undefined || profile[field] === null) {
      errors.push(`missing required field: ${field}`);
    }
  }
  if (profile.eligible_lanes && !Array.isArray(profile.eligible_lanes)) {
    errors.push('eligible_lanes must be an array');
  }
  if (profile.adapter_targets && !Array.isArray(profile.adapter_targets)) {
    errors.push('adapter_targets must be an array');
  }
  if (profile.adapter_targets?.length === 0) {
    errors.push('adapter_targets must have at least one target');
  }
  // Reject unregistered adapter targets early — surfaces typos at profile
  // load time instead of at package-build time.
  if (Array.isArray(profile.adapter_targets)) {
    for (const target of profile.adapter_targets) {
      if (!isRegisteredAdapter(target)) {
        errors.push(`adapter_targets contains unregistered adapter "${target}". Available: ${listAdapters().join(', ')}`);
      }
    }
  }
  return { valid: errors.length === 0, errors };
}

/**
 * Load a training profile from a project.
 */
export async function loadTrainingProfile(projectRoot, profileId) {
  const path = join(projectRoot, 'training', 'profiles', `${profileId}.json`);
  if (!existsSync(path)) {
    throw new Error(`Training profile "${profileId}" not found at ${path}`);
  }
  const data = JSON.parse(await readFile(path, 'utf-8'));
  const { valid, errors } = validateProfile(data);
  if (!valid) {
    throw new Error(`Training profile "${profileId}" is invalid:\n  ${errors.join('\n  ')}`);
  }
  return data;
}

/**
 * List all training profiles in a project.
 */
export async function listTrainingProfiles(projectRoot) {
  const dir = join(projectRoot, 'training', 'profiles');
  if (!existsSync(dir)) return [];

  const files = (await readdir(dir)).filter(f => f.endsWith('.json')).sort();
  const profiles = [];

  for (const file of files) {
    try {
      const data = JSON.parse(await readFile(join(dir, file), 'utf-8'));
      profiles.push({
        profile_id: data.profile_id,
        label: data.label,
        target_family: data.target_family,
        asset_type: data.asset_type,
        lanes: data.eligible_lanes?.length || 0,
        adapters: data.adapter_targets || [],
      });
    } catch {
      // Skip malformed
    }
  }

  return profiles;
}

/**
 * Save a training profile to a project.
 */
export async function saveTrainingProfile(projectRoot, profile) {
  const { valid, errors } = validateProfile(profile);
  if (!valid) {
    throw new Error(`Invalid training profile:\n  ${errors.join('\n  ')}`);
  }
  const dir = join(projectRoot, 'training', 'profiles');
  await mkdir(dir, { recursive: true });
  await writeFile(
    join(dir, `${profile.profile_id}.json`),
    JSON.stringify(profile, null, 2) + '\n'
  );
}
