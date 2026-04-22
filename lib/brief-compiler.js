/**
 * Brief compiler — merges project truth into a deterministic generation contract.
 *
 * Merge order (lowest to highest precedence):
 *   1. Project canon (constitution rules, global negatives)
 *   2. Lane config (lane-specific constraints)
 *   3. Subject config (identity anchors from records)
 *   4. Training asset / implementation pack hints
 *   5. Workflow profile (prompt strategy, output shape, runtime defaults)
 *   6. CLI overrides (output count, dimensions, sampler, etc.)
 *
 * Rule: same inputs → same brief body (deterministic except brief_id + compiled_at)
 */

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
import { loadProjectConfig } from './config.js';
import { getWorkflowProfile } from './workflow-profiles.js';
import { getBriefsDir } from './paths.js';
import { inputError, runtimeError } from './errors.js';
import { renderBriefMarkdown } from './brief-render.js';

// ─── Brief ID generation ─────────────────────────────────────────

/**
 * Generate a brief ID: brief_YYYY-MM-DD_NNN
 * NNN is a zero-padded sequence within the day, based on existing briefs.
 */
function generateBriefId(briefsDir) {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const prefix = `brief_${today}_`;

  let maxSeq = 0;
  if (existsSync(briefsDir)) {
    const existing = readdirSync(briefsDir)
      .filter(f => f.startsWith(prefix) && f.endsWith('.json'));
    for (const f of existing) {
      const seqStr = f.slice(prefix.length, -5); // strip prefix and .json
      const seq = parseInt(seqStr, 10);
      if (!isNaN(seq) && seq > maxSeq) maxSeq = seq;
    }
  }

  const seq = String(maxSeq + 1).padStart(3, '0');
  return `${prefix}${seq}`;
}

// ─── Canonical JSON ──────────────────────────────────────────────

/**
 * Recursively canonicalize an object: sort keys at every nesting level.
 * Arrays retain their order (order is semantically meaningful for arrays).
 * Primitives pass through untouched.
 */
export function canonicalize(value) {
  if (value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map(canonicalize);
  const sortedKeys = Object.keys(value).sort();
  const out = {};
  for (const key of sortedKeys) {
    out[key] = canonicalize(value[key]);
  }
  return out;
}

// ─── Config fingerprint ──────────────────────────────────────────

/**
 * Compute fingerprint of all inputs that feed the brief.
 * Includes project config files + workflow profile content.
 */
function computeBriefFingerprint(projectRoot, workflow, subjectRecords) {
  const hash = createHash('sha256');

  // Project config files (alphabetical)
  const configFiles = ['constitution.json', 'lanes.json', 'project.json', 'rubric.json', 'terminology.json'];
  for (const file of configFiles) {
    const filePath = join(projectRoot, file);
    if (existsSync(filePath)) {
      hash.update(`--- ${file} ---\n`);
      hash.update(readFileSync(filePath, 'utf-8'));
      hash.update('\n');
    }
  }

  // Workflow profile (serialized deterministically, recursively key-sorted)
  hash.update('--- workflow ---\n');
  hash.update(JSON.stringify(canonicalize(workflow)));
  hash.update('\n');

  // Subject records (sorted by ID)
  if (subjectRecords.length > 0) {
    hash.update('--- subjects ---\n');
    for (const rec of subjectRecords) {
      hash.update(`${rec.id}\n`);
    }
  }

  return hash.digest('hex');
}

// ─── Subject resolution ──────────────────────────────────────────

/**
 * Resolve subject records — find records matching a subject ID.
 * Looks for records with identity.subject_id matching the given ID,
 * or records whose ID starts with the subject prefix.
 */
async function resolveSubject(recordsDir, subjectId) {
  if (!existsSync(recordsDir)) return [];

  const files = readdirSync(recordsDir).filter(f => f.endsWith('.json'));
  const matches = [];
  const lowerSubject = subjectId.toLowerCase().replace(/-/g, '_');

  for (const file of files) {
    try {
      const data = JSON.parse(readFileSync(join(recordsDir, file), 'utf-8'));

      // Match by identity.subject_id
      if (data.identity?.subject_id) {
        const recordSubject = data.identity.subject_id.toLowerCase().replace(/-/g, '_');
        if (recordSubject === lowerSubject) {
          matches.push(data);
          continue;
        }
      }

      // Match by ID prefix
      if (data.id && data.id.toLowerCase().replace(/-/g, '_').startsWith(lowerSubject)) {
        matches.push(data);
      }
    } catch {
      // Skip unparseable records
    }
  }

  // Sort deterministically by ID
  matches.sort((a, b) => a.id.localeCompare(b.id));
  return matches;
}

/**
 * Extract subject constraints from resolved records.
 */
function extractSubjectContext(subjectRecords) {
  const constraints = [];
  const negatives = [];
  const anchors = [];

  for (const rec of subjectRecords) {
    const identity = rec.identity;
    if (!identity) continue;

    // Stable traits
    if (identity.stable_traits) {
      for (const trait of identity.stable_traits) {
        if (!constraints.includes(trait)) constraints.push(trait);
      }
    }

    // Faction / role
    if (identity.faction) constraints.push(`faction: ${identity.faction}`);
    if (identity.role) constraints.push(`role: ${identity.role}`);
    if (identity.species) constraints.push(`species: ${identity.species}`);

    // Prohibited drift
    if (identity.prohibited_drift) {
      for (const drift of identity.prohibited_drift) {
        if (!negatives.includes(drift)) negatives.push(drift);
      }
    }

    // Anchor records
    if (rec.judgment?.status === 'approved') {
      anchors.push({
        record_id: rec.id,
        role: rec.lineage?.generation_role === 'anchor' ? 'anchor' : 'supporting',
        reason: 'approved subject reference',
      });
    }
  }

  return { constraints, negatives, anchors };
}

// ─── Reference resolution ────────────────────────────────────────

/**
 * Resolve explicit reference IDs to records.
 */
async function resolveReferences(recordsDir, referenceIds) {
  if (!referenceIds || referenceIds.length === 0) return [];

  const refs = [];
  const sorted = [...referenceIds].sort();

  for (const refId of sorted) {
    const filePath = join(recordsDir, `${refId}.json`);
    if (!existsSync(filePath)) {
      throw inputError(
        'BRIEF_REF_NOT_FOUND',
        `Reference record "${refId}" not found`,
        `Check the record ID exists in records/.`
      );
    }

    const data = JSON.parse(readFileSync(filePath, 'utf-8'));
    if (data.judgment?.status !== 'approved') {
      throw inputError(
        'BRIEF_REF_NOT_APPROVED',
        `Reference record "${refId}" is not approved (status: ${data.judgment?.status || 'none'})`,
        `Only approved records can be used as references.`
      );
    }

    refs.push({
      record_id: data.id,
      role: data.lineage?.generation_role === 'anchor' ? 'anchor' : 'reference',
      reason: `explicit reference selection`,
    });
  }

  return refs;
}

// ─── Prompt assembly ─────────────────────────────────────────────

/**
 * Build the prompt block from structured sections.
 * Sections are assembled per the workflow's prompt_strategy.structure field.
 */
function buildPromptBlock(workflow, config, lane, subjectContext) {
  const ps = workflow.prompt_strategy;
  const sections = {};

  // Style prefix from workflow
  sections.style_prefix = ps.style_prefix.join(', ');

  // Subject identity — from resolved subject constraints
  if (subjectContext?.constraints?.length > 0) {
    sections.subject_identity = subjectContext.constraints.join(', ');
  }

  // Lane goal
  if (lane) {
    sections.lane_goal = lane.description || lane.label || lane.id;
  }

  // Canon focus — derive prompt fragments from matching constitution rules
  const canonFragments = [];
  const constitution = config.constitution;
  if (constitution?.rules && workflow.canon_focus) {
    for (const rule of constitution.rules) {
      // Match rules whose dims overlap with canon_focus
      const ruleDims = rule.dims || [];
      const focusMatch = ruleDims.some(d => {
        // Map dimension names to canon_focus categories
        const dimMap = {
          silhouette_clarity: 'silhouette',
          material_fidelity: 'material_language',
          palette_adherence: 'palette',
          composition: 'composition',
          style_consistency: 'palette',
          faction_read: 'faction_read',
          wear_level: 'surface_wear',
        };
        return workflow.canon_focus.includes(dimMap[d] || d);
      });

      if (focusMatch && rule.desc) {
        canonFragments.push(rule.desc);
      }
    }
  }
  sections.canon_focus = canonFragments.join(', ');

  // Controlled variation — optional blocks from workflow
  if (ps.optional_blocks?.length > 0) {
    sections.controlled_variation = ps.optional_blocks.join(', ');
  }

  // Assemble in structure order
  const structureParts = ps.structure.split(',').map(s => s.trim());
  const promptParts = [];

  for (const part of structureParts) {
    const section = sections[part];
    if (section && section.length > 0) {
      promptParts.push(section);
    }
  }

  return promptParts.join(', ');
}

/**
 * Build the negative prompt block from merged sources.
 */
function buildNegativeBlock(workflow, config, subjectContext) {
  const parts = [];

  // Workflow must_avoid (highest priority — first in negative)
  if (workflow.negative_strategy?.must_avoid) {
    parts.push(...workflow.negative_strategy.must_avoid);
  }

  // Lane-specific avoid
  if (workflow.negative_strategy?.lane_specific_avoid) {
    parts.push(...workflow.negative_strategy.lane_specific_avoid);
  }

  // Subject-specific avoid (from workflow defaults)
  if (workflow.negative_strategy?.subject_specific_avoid) {
    parts.push(...workflow.negative_strategy.subject_specific_avoid);
  }

  // Subject-specific negatives from identity
  if (subjectContext?.negatives) {
    for (const neg of subjectContext.negatives) {
      if (!parts.includes(neg)) parts.push(neg);
    }
  }

  return parts.join(', ');
}

// ─── Canon constraints ───────────────────────────────────────────

/**
 * Extract relevant canon constraints based on workflow canon_focus.
 */
function buildCanonConstraints(workflow, config) {
  const constraints = [];
  const constitution = config.constitution;

  if (!constitution?.rules || !workflow.canon_focus) return constraints;

  for (const rule of constitution.rules) {
    const ruleDims = rule.dims || [];
    const dimMap = {
      silhouette_clarity: 'silhouette',
      material_fidelity: 'material_language',
      palette_adherence: 'palette',
      composition: 'composition',
      style_consistency: 'palette',
      faction_read: 'faction_read',
      wear_level: 'surface_wear',
    };

    const focusMatch = ruleDims.some(d => workflow.canon_focus.includes(dimMap[d] || d));
    if (focusMatch) {
      constraints.push(`[${rule.id}] ${rule.desc}`);
    }
  }

  return constraints.sort();
}

/**
 * Build drift warnings — merge workflow drift_guards with canon forbidden patterns.
 */
function buildDriftWarnings(workflow, config) {
  const warnings = [];

  // Workflow drift guards
  if (workflow.drift_guards) {
    warnings.push(...workflow.drift_guards);
  }

  // Constitution-level forbidden patterns (rules that define failure)
  const constitution = config.constitution;
  if (constitution?.rules) {
    for (const rule of constitution.rules) {
      if (rule.rationale_fail && workflow.canon_focus) {
        const ruleDims = rule.dims || [];
        const dimMap = {
          silhouette_clarity: 'silhouette',
          material_fidelity: 'material_language',
          palette_adherence: 'palette',
          composition: 'composition',
          style_consistency: 'palette',
          faction_read: 'faction_read',
          wear_level: 'surface_wear',
        };
        const focusMatch = ruleDims.some(d => workflow.canon_focus.includes(dimMap[d] || d));
        if (focusMatch) {
          // Extract the drift pattern from the fail rationale
          const failHint = rule.rationale_fail.replace(/\$\{[^}]+\}/g, '').trim();
          if (failHint && !warnings.includes(failHint)) {
            warnings.push(`[${rule.id}] ${failHint}`);
          }
        }
      }
    }
  }

  return warnings;
}

/**
 * Build the runtime plan — merge workflow defaults with CLI overrides.
 */
export function buildRuntimePlan(workflow, overrides = {}) {
  const rd = workflow.runtime_defaults || {};
  return {
    adapter_target: overrides.adapter_target ?? rd.adapter_target ?? 'comfyui',
    width: overrides.width ?? rd.width ?? 1024,
    height: overrides.height ?? rd.height ?? 1024,
    steps: overrides.steps ?? rd.steps ?? 30,
    cfg: overrides.cfg ?? rd.cfg ?? 6.5,
    sampler: overrides.sampler ?? rd.sampler ?? 'dpmpp_2m',
    seed_mode: overrides.seed_mode ?? rd.seed_mode ?? 'increment',
  };
}

// ─── Main compiler ───────────────────────────────────────────────

/**
 * Compile a generation brief from project truth.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot — absolute path to project
 * @param {string} opts.projectId — project name
 * @param {string} opts.workflowId — workflow profile ID
 * @param {string} [opts.subjectId] — optional subject ID
 * @param {string} [opts.assetRef] — optional training asset reference
 * @param {string} [opts.implementationPackRef] — optional implementation pack reference
 * @param {string[]} [opts.referenceIds] — optional explicit reference record IDs
 * @param {Object} [opts.overrides] — CLI overrides (output_count, width, height, etc.)
 * @returns {Promise<Object>} compiled brief
 */
export async function compileBrief({
  projectRoot,
  projectId,
  workflowId,
  subjectId,
  assetRef,
  implementationPackRef,
  referenceIds,
  overrides = {},
}) {
  // Load workflow profile
  const workflow = await getWorkflowProfile(projectRoot, workflowId);

  // Validate required workflow fields
  if (typeof workflow.output_mode !== 'string' || workflow.output_mode.length === 0) {
    throw inputError(
      'WORKFLOW_INVALID',
      `Workflow "${workflowId}" is missing a non-empty "output_mode"`,
      `Check the workflow profile JSON — output_mode must be a non-empty string.`
    );
  }

  // Enforce subject_mode
  const subjectMode = workflow.subject_mode || 'optional';
  if (subjectMode === 'required' && !subjectId) {
    throw inputError(
      'BRIEF_SUBJECT_REQUIRED',
      `Workflow "${workflowId}" requires a subject (subject_mode: required)`,
      `Add --subject <id> to the command.`
    );
  }
  if (subjectMode === 'forbidden' && subjectId) {
    throw inputError(
      'BRIEF_SUBJECT_FORBIDDEN',
      `Workflow "${workflowId}" forbids a subject (subject_mode: forbidden)`,
      `Remove --subject from the command.`
    );
  }

  // Load project config
  const config = loadProjectConfig(projectRoot);

  // Resolve lane
  const lane = (config.lanes.lanes || []).find(l => l.id === workflow.lane_id) || null;

  // Resolve subject
  const recordsDir = join(projectRoot, 'records');
  let subjectRecords = [];
  let subjectContext = { constraints: [], negatives: [], anchors: [] };

  if (subjectId) {
    subjectRecords = await resolveSubject(recordsDir, subjectId);
    subjectContext = extractSubjectContext(subjectRecords);
  }

  // Resolve explicit references
  const referenceSelection = await resolveReferences(recordsDir, referenceIds);

  // Add subject anchors to reference selection
  for (const anchor of subjectContext.anchors) {
    if (!referenceSelection.find(r => r.record_id === anchor.record_id)) {
      referenceSelection.push(anchor);
    }
  }

  // Sort references deterministically
  referenceSelection.sort((a, b) => a.record_id.localeCompare(b.record_id));

  // Compute fingerprint
  const configFingerprint = computeBriefFingerprint(projectRoot, workflow, subjectRecords);

  // Build brief sections
  const prompt = buildPromptBlock(workflow, config, lane, subjectContext);
  const negativePrompt = buildNegativeBlock(workflow, config, subjectContext);
  const canonConstraints = buildCanonConstraints(workflow, config);
  const driftWarnings = buildDriftWarnings(workflow, config);
  const runtimePlan = buildRuntimePlan(workflow, overrides);

  // Expected outputs
  const expectedOutputs = {
    output_mode: workflow.output_mode,
    output_count: overrides.output_count ?? workflow.output_count,
    review_surface: workflow.output_mode.replace(/_/g, ' '),
  };

  // Generate brief ID
  const briefsDir = getBriefsDir(projectRoot);
  const briefId = generateBriefId(briefsDir);

  // Assemble the brief
  const brief = {
    brief_id: briefId,
    project_id: projectId,
    workflow_id: workflowId,
    lane_id: workflow.lane_id,
    compiled_at: new Date().toISOString(),
    config_fingerprint: configFingerprint,
  };

  // Optional fields — only include when present
  if (subjectId) brief.subject_id = subjectId;
  if (assetRef) brief.training_asset_ref = assetRef;
  if (implementationPackRef) brief.implementation_pack_ref = implementationPackRef;

  // Reference selection
  if (referenceSelection.length > 0) {
    brief.reference_selection = referenceSelection;
  }

  // Core content
  brief.prompt = prompt;
  brief.negative_prompt = negativePrompt;
  brief.canon_constraints = canonConstraints;

  if (subjectContext.constraints.length > 0) {
    brief.subject_constraints = subjectContext.constraints;
  }

  brief.drift_warnings = driftWarnings;
  brief.runtime_plan = runtimePlan;
  brief.expected_outputs = expectedOutputs;

  return brief;
}

/**
 * Save a compiled brief to disk (JSON + Markdown).
 */
export async function saveCompiledBrief(projectRoot, brief) {
  const briefsDir = getBriefsDir(projectRoot);
  await mkdir(briefsDir, { recursive: true });

  // Write JSON
  const jsonPath = join(briefsDir, `${brief.brief_id}.json`);
  await writeFile(jsonPath, JSON.stringify(brief, null, 2) + '\n');

  // Write Markdown
  const md = renderBriefMarkdown(brief);
  const mdPath = join(briefsDir, `${brief.brief_id}.md`);
  await writeFile(mdPath, md);

  return { jsonPath, mdPath };
}

/**
 * Load a compiled brief from disk.
 */
export async function loadCompiledBrief(projectRoot, briefId) {
  const briefsDir = getBriefsDir(projectRoot);
  const jsonPath = join(briefsDir, `${briefId}.json`);

  if (!existsSync(jsonPath)) {
    throw inputError(
      'BRIEF_NOT_FOUND',
      `Brief "${briefId}" not found`,
      `Run: sdlab brief compile --project <name> --workflow <id>`
    );
  }

  return JSON.parse(await readFile(jsonPath, 'utf-8'));
}

/**
 * List all compiled briefs in a project.
 */
export async function listCompiledBriefs(projectRoot) {
  const briefsDir = getBriefsDir(projectRoot);
  if (!existsSync(briefsDir)) return [];

  const files = readdirSync(briefsDir).filter(f => f.endsWith('.json')).sort();
  const briefs = [];

  for (const file of files) {
    try {
      const data = JSON.parse(readFileSync(join(briefsDir, file), 'utf-8'));
      briefs.push({
        brief_id: data.brief_id,
        workflow_id: data.workflow_id,
        lane_id: data.lane_id,
        subject_id: data.subject_id || null,
        compiled_at: data.compiled_at,
        output_mode: data.expected_outputs?.output_mode,
        output_count: data.expected_outputs?.output_count,
      });
    } catch {
      // Skip malformed
    }
  }

  return briefs;
}
