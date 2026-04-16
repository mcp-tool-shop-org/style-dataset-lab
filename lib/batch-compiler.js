/**
 * Batch compiler — expand a batch mode into multiple coordinated briefs.
 *
 * Takes a batch mode + subject/theme inputs and produces one brief per
 * variant slot, each with controlled prompt/negative/runtime deltas
 * on top of a base compiled brief from 4A.
 */

import { compileBrief, saveCompiledBrief } from './brief-compiler.js';
import { getBatchMode } from './batch-modes.js';
import { getWorkflowProfile } from './workflow-profiles.js';
import { inputError } from './errors.js';

/**
 * Apply slot-level deltas to a base brief.
 *
 * @param {Object} baseBrief — compiled brief from brief-compiler
 * @param {Object} slot — variant_plan slot definition
 * @returns {Object} — modified brief (new object, base untouched)
 */
export function applySlotDelta(baseBrief, slot) {
  const modified = JSON.parse(JSON.stringify(baseBrief));

  // Prompt additions — append to the end
  if (slot.prompt_additions?.length > 0) {
    modified.prompt = `${modified.prompt}, ${slot.prompt_additions.join(', ')}`;
  }

  // Negative additions — append without duplicating
  if (slot.negative_additions?.length > 0) {
    const existingLower = modified.negative_prompt.toLowerCase().split(',').map(s => s.trim());
    const additions = slot.negative_additions.filter(
      n => !existingLower.some(e => e.includes(n.toLowerCase()))
    );
    if (additions.length > 0) {
      modified.negative_prompt = `${modified.negative_prompt}, ${additions.join(', ')}`;
    }
  }

  // Runtime overrides
  if (slot.runtime_overrides) {
    for (const [key, val] of Object.entries(slot.runtime_overrides)) {
      if (modified.runtime_plan && val !== undefined) {
        modified.runtime_plan[key] = val;
      }
    }
  }

  // Tag the slot
  modified._batch_slot_id = slot.slot_id;
  modified._batch_slot_label = slot.label;

  return modified;
}

/**
 * Compile a full batch — one brief per variant slot.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot — absolute project path
 * @param {string} opts.projectId — project name
 * @param {string} opts.modeId — batch mode ID
 * @param {string} [opts.subjectId] — subject for subject-driven modes
 * @param {string} [opts.theme] — theme label for environment modes
 * @param {string} [opts.assetRef] — optional training asset reference
 * @param {Object} [opts.overrides] — CLI runtime overrides
 * @returns {Promise<{ mode: Object, baseBrief: Object, slotBriefs: Object[] }>}
 */
export async function compileBatch({
  projectRoot,
  projectId,
  modeId,
  subjectId,
  theme,
  assetRef,
  overrides = {},
}) {
  // Load batch mode
  const mode = getBatchMode(projectRoot, modeId);

  // Enforce subject mode
  const subjectMode = mode.subject_mode || 'optional';
  if (subjectMode === 'required' && !subjectId) {
    throw inputError(
      'BATCH_SUBJECT_REQUIRED',
      `Batch mode "${modeId}" requires a subject`,
      'Add --subject <id> to the command.'
    );
  }
  if (subjectMode === 'forbidden' && subjectId) {
    throw inputError(
      'BATCH_SUBJECT_FORBIDDEN',
      `Batch mode "${modeId}" does not accept a subject`,
      'Remove --subject from the command.'
    );
  }

  // Compile the base brief using the mode's base workflow
  // Force output_count to 1 — each slot produces one primary candidate
  const baseBrief = await compileBrief({
    projectRoot,
    projectId,
    workflowId: mode.base_workflow_id,
    subjectId,
    assetRef,
    overrides: { ...overrides, output_count: 1 },
  });

  // Add theme to prompt if provided
  if (theme) {
    baseBrief.prompt = `${baseBrief.prompt}, ${theme}`;
  }

  // Expand into slot briefs
  const slotBriefs = mode.variant_plan.map(slot => applySlotDelta(baseBrief, slot));

  return { mode, baseBrief, slotBriefs };
}
