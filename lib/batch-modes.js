/**
 * Batch modes — load, validate, list batch production mode definitions.
 *
 * A batch mode is a production recipe above the single-brief level.
 * It defines what deliverable is being made, how many coordinated briefs
 * are needed, and how results should be assembled.
 */

import { join } from 'node:path';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { getProjectRoot } from './paths.js';
import { inputError } from './errors.js';

const VALID_BATCH_TYPES = [
  'expression_sheet', 'variant_board', 'moodboard',
  'silhouette_grid', 'continuity_pack',
];
const VALID_LAYOUTS = ['grid', 'moodboard', 'sheet', 'strip'];
const VALID_SUBJECT_MODES = ['required', 'optional', 'forbidden'];

/**
 * Return the batch modes directory for a project.
 */
export function getBatchModesDir(projectRoot) {
  return join(projectRoot, 'workflows', 'batch-modes');
}

/**
 * List all batch modes for a project.
 *
 * B06: listWorkflowProfiles() (its structurally identical sibling in
 * workflow-profiles.js) already skips a malformed file per-entry via
 * try/catch. This function had no such guard, so one bad batch-mode file
 * threw an uncaught SyntaxError out of Array.prototype.map and hid EVERY
 * batch mode, not just the broken one.
 */
export function listBatchModes(projectRoot) {
  const dir = getBatchModesDir(projectRoot);
  if (!existsSync(dir)) return [];

  const modes = [];
  for (const f of readdirSync(dir).filter(f => f.endsWith('.json'))) {
    try {
      const data = JSON.parse(readFileSync(join(dir, f), 'utf-8'));
      modes.push({
        mode_id: data.mode_id,
        label: data.label,
        batch_type: data.batch_type,
        base_workflow_id: data.base_workflow_id,
        subject_mode: data.subject_mode || 'optional',
        slot_count: data.variant_plan?.length || 0,
      });
    } catch {
      // Skip malformed — matches listWorkflowProfiles' existing resilience.
    }
  }

  return modes.sort((a, b) => a.mode_id.localeCompare(b.mode_id));
}

/**
 * Load a batch mode by ID.
 */
export function getBatchMode(projectRoot, modeId) {
  const dir = getBatchModesDir(projectRoot);
  const filePath = join(dir, `${modeId}.json`);

  if (!existsSync(filePath)) {
    throw inputError(
      'BATCH_MODE_NOT_FOUND',
      `Batch mode "${modeId}" not found`,
      `Check workflows/batch-modes/ or run: sdlab batch list`
    );
  }

  // B06: JSON.parse used to run unguarded here, so a malformed mode file
  // threw a raw, uncaught SyntaxError naming nothing. Wrapped in the same
  // structured-error pattern lib/config.js's loadJsonFile already uses.
  try {
    return JSON.parse(readFileSync(filePath, 'utf-8'));
  } catch (err) {
    throw inputError(
      'INPUT_INVALID_JSON',
      `Failed to parse ${filePath}: ${err.message}`,
      'Check the file for JSON syntax errors (trailing commas, unquoted keys, etc).'
    );
  }
}

/**
 * Validate a batch mode definition.
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateBatchMode(mode) {
  const errors = [];

  if (!mode.mode_id) errors.push('missing mode_id');
  if (!mode.label) errors.push('missing label');
  if (!mode.base_workflow_id) errors.push('missing base_workflow_id');

  if (!mode.batch_type || !VALID_BATCH_TYPES.includes(mode.batch_type)) {
    errors.push(`invalid batch_type "${mode.batch_type}" — must be one of: ${VALID_BATCH_TYPES.join(', ')}`);
  }

  if (mode.subject_mode && !VALID_SUBJECT_MODES.includes(mode.subject_mode)) {
    errors.push(`invalid subject_mode "${mode.subject_mode}"`);
  }

  if (!Array.isArray(mode.variant_plan) || mode.variant_plan.length === 0) {
    errors.push('variant_plan must be a non-empty array');
  } else {
    const slotIds = new Set();
    for (const slot of mode.variant_plan) {
      if (!slot.slot_id) errors.push('variant slot missing slot_id');
      if (!slot.label) errors.push('variant slot missing label');
      if (slot.slot_id && slotIds.has(slot.slot_id)) {
        errors.push(`duplicate slot_id "${slot.slot_id}"`);
      }
      slotIds.add(slot.slot_id);
    }
  }

  if (!mode.assembly) {
    errors.push('missing assembly');
  } else {
    if (!mode.assembly.layout || !VALID_LAYOUTS.includes(mode.assembly.layout)) {
      errors.push(`invalid assembly.layout "${mode.assembly?.layout}" — must be one of: ${VALID_LAYOUTS.join(', ')}`);
    }
  }

  return { valid: errors.length === 0, errors };
}
