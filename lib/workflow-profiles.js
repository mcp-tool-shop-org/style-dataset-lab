/**
 * Workflow profile management.
 *
 * A workflow profile is a production recipe — it defines how to generate
 * a specific kind of output set (portrait pack, expression sheet, moodboard, etc.)
 * using project canon and trained assets.
 *
 * Workflow profiles are NOT training profiles. They drive generation, not training.
 */

import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { getWorkflowProfilesDir } from './paths.js';

const REQUIRED_FIELDS = [
  'workflow_id', 'label', 'lane_id', 'output_mode', 'output_count',
  'prompt_strategy', 'negative_strategy', 'canon_focus', 'drift_guards',
  'runtime_defaults',
];

const VALID_SUBJECT_MODES = ['required', 'optional', 'forbidden'];

const VALID_OUTPUT_MODES = [
  'portrait_set', 'expression_sheet', 'variant_pack',
  'moodboard', 'silhouette_sheet', 'turnaround',
];

const VALID_CANON_FOCUS = [
  'silhouette', 'material_language', 'palette', 'anatomy',
  'costume_logic', 'era_logic', 'scale_logic', 'lighting',
  'surface_wear', 'gesture', 'composition', 'faction_read',
];

/**
 * Validate a workflow profile object.
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateWorkflowProfile(profile) {
  const errors = [];

  for (const field of REQUIRED_FIELDS) {
    if (profile[field] === undefined || profile[field] === null) {
      errors.push(`missing required field: ${field}`);
    }
  }

  if (profile.subject_mode && !VALID_SUBJECT_MODES.includes(profile.subject_mode)) {
    errors.push(`invalid subject_mode "${profile.subject_mode}" — must be one of: ${VALID_SUBJECT_MODES.join(', ')}`);
  }

  if (profile.output_mode && !VALID_OUTPUT_MODES.includes(profile.output_mode)) {
    errors.push(`invalid output_mode "${profile.output_mode}" — must be one of: ${VALID_OUTPUT_MODES.join(', ')}`);
  }

  if (!Number.isInteger(profile.output_count) || profile.output_count < 1) {
    errors.push('output_count must be a positive integer');
  }

  // Prompt strategy structure
  const ps = profile.prompt_strategy;
  if (ps) {
    if (!Array.isArray(ps.style_prefix)) errors.push('prompt_strategy.style_prefix must be an array');
    if (typeof ps.structure !== 'string') errors.push('prompt_strategy.structure must be a string');
    if (!Array.isArray(ps.must_include)) errors.push('prompt_strategy.must_include must be an array');
  }

  // Negative strategy structure
  const ns = profile.negative_strategy;
  if (ns) {
    if (!Array.isArray(ns.must_avoid)) errors.push('negative_strategy.must_avoid must be an array');
  }

  // Canon focus items
  if (Array.isArray(profile.canon_focus)) {
    for (const item of profile.canon_focus) {
      if (!VALID_CANON_FOCUS.includes(item)) {
        errors.push(`invalid canon_focus item "${item}" — must be one of: ${VALID_CANON_FOCUS.join(', ')}`);
      }
    }
  } else if (profile.canon_focus !== undefined) {
    errors.push('canon_focus must be an array');
  }

  if (profile.drift_guards && !Array.isArray(profile.drift_guards)) {
    errors.push('drift_guards must be an array');
  }

  // Runtime defaults
  const rd = profile.runtime_defaults;
  if (rd) {
    if (!rd.adapter_target) errors.push('runtime_defaults.adapter_target is required');
    if (rd.seed_mode && !['fixed', 'increment', 'random'].includes(rd.seed_mode)) {
      errors.push(`invalid runtime_defaults.seed_mode "${rd.seed_mode}" — must be fixed, increment, or random`);
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Load a single workflow profile by ID.
 */
export async function getWorkflowProfile(projectRoot, workflowId) {
  const dir = getWorkflowProfilesDir(projectRoot);
  const path = join(dir, `${workflowId}.json`);
  if (!existsSync(path)) {
    throw new Error(`Workflow profile "${workflowId}" not found at ${path}`);
  }
  const data = JSON.parse(await readFile(path, 'utf-8'));
  const { valid, errors } = validateWorkflowProfile(data);
  if (!valid) {
    throw new Error(`Workflow profile "${workflowId}" is invalid:\n  ${errors.join('\n  ')}`);
  }
  return data;
}

/**
 * List all workflow profiles in a project.
 */
export async function listWorkflowProfiles(projectRoot) {
  const dir = getWorkflowProfilesDir(projectRoot);
  if (!existsSync(dir)) return [];

  const files = (await readdir(dir)).filter(f => f.endsWith('.json')).sort();
  const profiles = [];

  for (const file of files) {
    try {
      const data = JSON.parse(await readFile(join(dir, file), 'utf-8'));
      profiles.push({
        workflow_id: data.workflow_id,
        label: data.label,
        lane_id: data.lane_id,
        subject_mode: data.subject_mode || 'optional',
        output_mode: data.output_mode,
        output_count: data.output_count,
      });
    } catch {
      // Skip malformed
    }
  }

  return profiles;
}

/**
 * Save a workflow profile to a project.
 */
export async function saveWorkflowProfile(projectRoot, profile) {
  const { valid, errors } = validateWorkflowProfile(profile);
  if (!valid) {
    throw new Error(`Invalid workflow profile:\n  ${errors.join('\n  ')}`);
  }
  const dir = getWorkflowProfilesDir(projectRoot);
  await mkdir(dir, { recursive: true });
  await writeFile(
    join(dir, `${profile.workflow_id}.json`),
    JSON.stringify(profile, null, 2) + '\n'
  );
}
