/**
 * Refine briefs — derive a next-pass brief from critique of a previous run.
 *
 * A refined brief is NOT a brand-new brief. It is a delta layer:
 *   - Preserves: original workflow, subject, lane, canon constraints, runtime plan
 *   - Adds: preserve/push/suppress instructions derived from critique
 *   - Updates: prompt and negative prompt with targeted refinements
 *
 * This keeps the loop stable — each pass improves, never scrambles.
 */

import { writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readdirSync } from 'node:fs';
import { getRunsDir } from './paths.js';
import { inputError } from './errors.js';

// ─── Refined brief ID generation ─────────────────────────────────

/**
 * Generate refined brief ID: <parent_brief_id>_refine_NN
 */
function generateRefinedBriefId(refineDir, parentBriefId) {
  const prefix = `${parentBriefId}_refine_`;

  let maxSeq = 0;
  if (existsSync(refineDir)) {
    const existing = readdirSync(refineDir)
      .filter(f => f.startsWith(prefix) && f.endsWith('.json'));
    for (const f of existing) {
      const seqStr = f.slice(prefix.length, -5);
      const seq = parseInt(seqStr, 10);
      if (!isNaN(seq) && seq > maxSeq) maxSeq = seq;
    }
  }

  const seq = String(maxSeq + 1).padStart(2, '0');
  return `${prefix}${seq}`;
}

// ─── Prompt refinement ───────────────────────────────────────────

/**
 * Render a refined prompt from parent prompt + delta instructions.
 *
 * Strategy:
 *   - Start with the original prompt
 *   - Append preserve notes as reinforcement
 *   - Append push notes as emphasis
 *   - Do NOT remove anything from the original — only add emphasis
 */
export function renderRefinedPrompt(parentPrompt, delta) {
  const parts = [parentPrompt];

  // Preserve instructions — reinforce what worked
  if (delta.preserve?.length > 0) {
    parts.push(`[preserve: ${delta.preserve.join(', ')}]`);
  }

  // Push instructions — emphasize what needs to be stronger
  if (delta.push?.length > 0) {
    parts.push(`[emphasize: ${delta.push.join(', ')}]`);
  }

  return parts.join(', ');
}

/**
 * Render a refined negative prompt from parent negative + suppress instructions.
 *
 * Strategy:
 *   - Keep the entire original negative prompt
 *   - Append suppress items that aren't already present
 */
export function renderRefinedNegative(parentNegative, delta) {
  // PB-007: coerce missing/null/non-string negatives to '' so we don't
  // throw on legacy briefs or hand-edited JSON that dropped the field.
  const parent = typeof parentNegative === 'string' ? parentNegative : '';
  const existing = parent
    .split(',')
    .map(s => s.trim().toLowerCase())
    .filter(s => s.length > 0);
  const additions = [];

  for (const item of delta.suppress || []) {
    const lower = item.toLowerCase().trim();
    // Don't duplicate if already in negative (token-exact match)
    if (lower.length > 0 && !existing.includes(lower)) {
      additions.push(item);
    }
  }

  if (additions.length === 0) return parent;
  if (parent.length === 0) return additions.join(', ');
  return `${parent}, ${additions.join(', ')}`;
}

// ─── Delta extraction from critique ──────────────────────────────

/**
 * Extract a refine delta from a critique report + picked candidate.
 *
 * @param {Object} critique — critique report
 * @param {string} pickedFilename — filename of the picked candidate
 * @param {Object} cliOverrides — { preserve: string[], push: string[], suppress: string[] }
 * @returns {{ preserve: string[], push: string[], suppress: string[] }}
 */
export function extractDelta(critique, pickedFilename, cliOverrides = {}) {
  // Find the picked candidate in the critique
  const picked = critique.candidates.find(c => c.filename === pickedFilename);
  if (!picked) {
    throw inputError(
      'REFINE_CANDIDATE_NOT_FOUND',
      `Candidate "${pickedFilename}" not found in critique for run "${critique.run_id}"`,
      `Available candidates: ${critique.candidates.map(c => c.filename).join(', ')}`
    );
  }

  // Start with critique-derived instructions
  const preserve = [...(picked.preserve_next_pass || [])];
  const push = [];
  const suppress = [];

  // Derive push from drift issues that need correction
  for (const issue of picked.correct_next_pass || []) {
    push.push(issue);
  }

  // Derive suppress from drift issues
  for (const drift of picked.drift_issues || []) {
    // Strip "check:" and "negative check:" prefixes for cleaner suppress
    const cleaned = drift
      .replace(/^\[.*?\]\s*check:\s*/i, '')
      .replace(/^negative check:\s*/i, '')
      .trim();
    if (cleaned) suppress.push(cleaned);
  }

  // CLI overrides — append without duplicating
  if (cliOverrides.preserve) {
    for (const p of cliOverrides.preserve) {
      if (!preserve.includes(p)) preserve.push(p);
    }
  }
  if (cliOverrides.push) {
    for (const p of cliOverrides.push) {
      if (!push.includes(p)) push.push(p);
    }
  }
  if (cliOverrides.suppress) {
    for (const s of cliOverrides.suppress) {
      if (!suppress.includes(s)) suppress.push(s);
    }
  }

  return { preserve, push, suppress };
}

// ─── Build refined brief ─────────────────────────────────────────

/**
 * Build a refined brief from parent brief, critique, and delta.
 *
 * @param {Object} opts
 * @param {Object} opts.parentBrief — original compiled brief
 * @param {Object} opts.critique — critique report
 * @param {string} opts.pickedCandidate — filename of selected candidate
 * @param {Object} opts.delta — { preserve, push, suppress }
 * @param {string} opts.runId — source run ID
 * @param {string} opts.refineDir — path to write refined brief
 * @returns {Object} refined brief
 */
export function buildRefinedBrief({ parentBrief, critique, pickedCandidate, delta, runId, refineDir }) {
  const briefId = generateRefinedBriefId(refineDir, parentBrief.brief_id);

  // Render updated prompts — PB-007 guards missing fields upstream.
  const prompt = renderRefinedPrompt(parentBrief.prompt ?? '', delta);
  const negativePrompt = renderRefinedNegative(parentBrief.negative_prompt ?? '', delta);

  const refined = {
    brief_id: briefId,
    parent_brief_id: parentBrief.brief_id,
    source_run_id: runId,
    source_candidate: pickedCandidate,

    project_id: parentBrief.project_id,
    workflow_id: parentBrief.workflow_id,
    lane_id: parentBrief.lane_id,
    compiled_at: new Date().toISOString(),
    config_fingerprint: parentBrief.config_fingerprint,

    prompt,
    negative_prompt: negativePrompt,

    refine_delta: delta,

    // Carry forward from parent
    canon_constraints: parentBrief.canon_constraints || [],
    drift_warnings: parentBrief.drift_warnings || [],
    runtime_plan: { ...parentBrief.runtime_plan },
    expected_outputs: { ...parentBrief.expected_outputs },
  };

  // Optional fields
  if (parentBrief.subject_id) refined.subject_id = parentBrief.subject_id;
  if (parentBrief.subject_constraints) refined.subject_constraints = parentBrief.subject_constraints;
  if (parentBrief.reference_selection) refined.reference_selection = parentBrief.reference_selection;

  return refined;
}

// ─── Markdown renderer ──────────────────────────────────────────

/**
 * Render a refined brief as Markdown.
 */
export function renderRefinedBriefMarkdown(brief) {
  const lines = [];

  lines.push(`# Refined Brief: ${brief.brief_id}`);
  lines.push('');
  lines.push(`**Parent Brief:** ${brief.parent_brief_id}`);
  lines.push(`**Source Run:** ${brief.source_run_id}`);
  lines.push(`**Picked Candidate:** ${brief.source_candidate}`);
  lines.push('');
  lines.push(`**Workflow:** ${brief.workflow_id}`);
  lines.push(`**Project:** ${brief.project_id}`);
  lines.push(`**Lane:** ${brief.lane_id}`);
  if (brief.subject_id) lines.push(`**Subject:** ${brief.subject_id}`);
  lines.push('');

  // Refine delta — the key section
  lines.push('## Refine Delta');
  lines.push('');

  if (brief.refine_delta?.preserve?.length > 0) {
    lines.push('### Preserve');
    for (const p of brief.refine_delta.preserve) lines.push(`- ✓ ${p}`);
    lines.push('');
  }

  if (brief.refine_delta?.push?.length > 0) {
    lines.push('### Push');
    for (const p of brief.refine_delta.push) lines.push(`- → ${p}`);
    lines.push('');
  }

  if (brief.refine_delta?.suppress?.length > 0) {
    lines.push('### Suppress');
    for (const s of brief.refine_delta.suppress) lines.push(`- ✗ ${s}`);
    lines.push('');
  }

  // Prompt
  lines.push('## Prompt');
  lines.push('');
  lines.push('```');
  lines.push(brief.prompt);
  lines.push('```');
  lines.push('');

  // Negative prompt
  lines.push('## Negative Prompt');
  lines.push('');
  lines.push('```');
  lines.push(brief.negative_prompt);
  lines.push('```');
  lines.push('');

  // Canon constraints
  if (brief.canon_constraints?.length > 0) {
    lines.push('## Canon Constraints');
    lines.push('');
    for (const c of brief.canon_constraints) lines.push(`- ${c}`);
    lines.push('');
  }

  // Drift warnings
  if (brief.drift_warnings?.length > 0) {
    lines.push('## Drift Warnings');
    lines.push('');
    for (const w of brief.drift_warnings) lines.push(`- ⚠ ${w}`);
    lines.push('');
  }

  // Runtime plan
  lines.push('## Runtime Plan');
  lines.push('');
  lines.push('| Parameter | Value |');
  lines.push('|-----------|-------|');
  const rp = brief.runtime_plan || {};
  lines.push(`| Adapter | ${rp.adapter_target || '?'} |`);
  lines.push(`| Width | ${rp.width || '?'} |`);
  lines.push(`| Height | ${rp.height || '?'} |`);
  lines.push(`| Steps | ${rp.steps || '?'} |`);
  lines.push(`| CFG | ${rp.cfg || '?'} |`);
  lines.push(`| Sampler | ${rp.sampler || '?'} |`);
  lines.push(`| Seed Mode | ${rp.seed_mode || '?'} |`);
  lines.push('');

  // Expected outputs
  lines.push('## Expected Outputs');
  lines.push('');
  const eo = brief.expected_outputs || {};
  lines.push(`- **Mode:** ${eo.output_mode || '?'}`);
  lines.push(`- **Count:** ${eo.output_count || '?'}`);
  lines.push('');

  // Metadata
  lines.push('---');
  lines.push('');
  lines.push(`Compiled: ${brief.compiled_at}`);
  lines.push(`Config fingerprint: \`${brief.config_fingerprint || '—'}\``);
  lines.push('');

  return lines.join('\n');
}

// ─── Save ────────────────────────────────────────────────────────

/**
 * Save a refined brief to the run's refine directory.
 */
export async function saveRefinedBrief(projectRoot, runId, refinedBrief) {
  const refineDir = join(getRunsDir(projectRoot), runId, 'refine');
  await mkdir(refineDir, { recursive: true });

  const jsonPath = join(refineDir, `${refinedBrief.brief_id}.json`);
  await writeFile(jsonPath, JSON.stringify(refinedBrief, null, 2) + '\n');

  const md = renderRefinedBriefMarkdown(refinedBrief);
  const mdPath = join(refineDir, `${refinedBrief.brief_id}.md`);
  await writeFile(mdPath, md);

  return { jsonPath, mdPath, refineDir };
}
