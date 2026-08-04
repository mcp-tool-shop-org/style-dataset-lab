/**
 * Critique engine — inspect run outputs and produce structured feedback.
 *
 * A critique is NOT a scorecard. It answers:
 *   - Which candidates are closest to the brief?
 *   - What each candidate did well.
 *   - What drifted.
 *   - What to preserve into the next pass.
 *   - What to explicitly correct.
 *
 * The engine is rule-based and brief-driven — the brief determines the lens.
 */

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { getProjectRoot, getRunsDir } from './paths.js';
import { loadRun } from './runtime-runs.js';
import { getWorkflowProfile } from './workflow-profiles.js';
import { loadProjectConfig } from './config.js';
import { inputError } from './errors.js';
import { RULE_BASED_JUDGE, generatorModelFromManifest, warnIfSelfVerification } from './verifier.js';

// ─── Dimension catalogue ─────────────────────────────────────────

/**
 * All known critique dimensions.
 * Each dimension maps to brief/workflow features that activate it.
 */
const DIMENSION_CATALOGUE = {
  subject_continuity: {
    label: 'Subject Continuity',
    activatedBy: { hasSubject: true },
    driftGuardKeywords: ['face structure', 'identity', 'subject'],
    description: 'Does the candidate preserve the subject identity across outputs?',
  },
  lane_fit: {
    label: 'Lane Fit',
    activatedBy: { always: true },
    driftGuardKeywords: ['lane', 'role'],
    description: 'Does the candidate fit the lane purpose?',
  },
  silhouette_read: {
    label: 'Silhouette Read',
    activatedBy: { canonFocus: ['silhouette'] },
    driftGuardKeywords: ['silhouette'],
    description: 'Is the silhouette clean and recognizable?',
  },
  material_costume_logic: {
    label: 'Material / Costume Logic',
    activatedBy: { canonFocus: ['costume_logic', 'material_language'] },
    driftGuardKeywords: ['material', 'costume', 'cloth', 'metal', 'fabric'],
    description: 'Are materials and costume elements canon-correct?',
  },
  palette_mood: {
    label: 'Palette / Mood Fidelity',
    activatedBy: { canonFocus: ['palette', 'lighting'] },
    driftGuardKeywords: ['palette', 'mood', 'lighting', 'color'],
    description: 'Does the palette and mood match the brief?',
  },
  composition_framing: {
    label: 'Composition / Framing',
    activatedBy: { canonFocus: ['composition'] },
    driftGuardKeywords: ['composition', 'framing', 'crop'],
    description: 'Is the composition appropriate for the output mode?',
  },
  ornamental_drift: {
    label: 'Ornamental Drift',
    activatedBy: { canonFocus: ['costume_logic', 'faction_read'] },
    driftGuardKeywords: ['ornament', 'accessori', 'extra'],
    description: 'Has the candidate added non-canon decorative elements?',
  },
  era_faction_drift: {
    label: 'Era / Faction Drift',
    activatedBy: { canonFocus: ['era_logic', 'faction_read'] },
    driftGuardKeywords: ['era', 'faction', 'wrong'],
    description: 'Are there wrong-era or wrong-faction elements?',
  },
  identity_stability: {
    label: 'Identity Stability',
    activatedBy: { hasSubject: true },
    driftGuardKeywords: ['identity', 'face', 'hairstyle', 'age'],
    description: 'Has the candidate maintained stable identity features?',
  },
  readability: {
    label: 'Readability',
    activatedBy: { always: true },
    driftGuardKeywords: ['read', 'clarity', 'muddy', 'clean'],
    description: 'Is the output clearly readable at a glance?',
  },
};

// ─── Workflow-specific emphasis maps ─────────────────────────────

/**
 * Output mode → dimensions to emphasize.
 * These get boosted in critique output ordering.
 */
const MODE_EMPHASIS = {
  portrait_set: [
    'subject_continuity', 'identity_stability', 'silhouette_read',
    'material_costume_logic', 'ornamental_drift',
  ],
  expression_sheet: [
    'identity_stability', 'subject_continuity',
    'material_costume_logic', 'readability',
  ],
  moodboard: [
    'palette_mood', 'material_costume_logic', 'era_faction_drift',
    'composition_framing', 'readability',
  ],
  variant_pack: [
    'silhouette_read', 'material_costume_logic', 'palette_mood',
    'ornamental_drift',
  ],
  silhouette_sheet: [
    'silhouette_read', 'composition_framing', 'readability',
  ],
  turnaround: [
    'subject_continuity', 'identity_stability', 'silhouette_read',
    'material_costume_logic',
  ],
};

// ─── Active dimension resolution ─────────────────────────────────

/**
 * Determine which critique dimensions are active for this brief + workflow.
 */
export function getActiveDimensions({ brief, workflow }) {
  const active = [];
  const hasSubject = !!brief.subject_id;
  const canonFocus = workflow.canon_focus || [];
  const driftGuards = workflow.drift_guards || [];
  const driftText = driftGuards.join(' ').toLowerCase();

  for (const [dimId, dim] of Object.entries(DIMENSION_CATALOGUE)) {
    const cond = dim.activatedBy;

    // Always-on dimensions
    if (cond.always) {
      active.push(dimId);
      continue;
    }

    // Subject-dependent
    if (cond.hasSubject && hasSubject) {
      active.push(dimId);
      continue;
    }

    // Canon focus match
    if (cond.canonFocus) {
      const match = cond.canonFocus.some(cf => canonFocus.includes(cf));
      if (match) {
        active.push(dimId);
        continue;
      }
    }

    // Drift guard keyword match (catch dimensions invoked by guard language)
    if (dim.driftGuardKeywords) {
      const kwMatch = dim.driftGuardKeywords.some(kw => driftText.includes(kw));
      if (kwMatch) {
        active.push(dimId);
        continue;
      }
    }
  }

  // Deduplicate and order by mode emphasis
  const outputMode = workflow.output_mode || brief.expected_outputs?.output_mode;
  const emphasis = MODE_EMPHASIS[outputMode] || [];
  const ordered = [
    ...emphasis.filter(d => active.includes(d)),
    ...active.filter(d => !emphasis.includes(d)),
  ];

  return [...new Set(ordered)];
}

// ─── Candidate critique ──────────────────────────────────────────

/**
 * Generate structured notes for a single candidate.
 *
 * In this first version, the engine uses the brief's drift guards,
 * canon constraints, and negative prompt to produce rule-based notes.
 * A human or LLM fills in the actual per-image observations via
 * `sdlab critique --run <id>` which creates a template to complete.
 */
export function critiqueCandidate({ brief, workflow, candidate, activeDimensions, generatorModel = null }) {
  const strengths = [];
  const driftIssues = [];
  const preserveNextPass = [];
  const correctNextPass = [];

  const driftGuards = workflow.drift_guards || [];
  const canonFocus = workflow.canon_focus || [];
  const negatives = (brief.negative_prompt || '').split(',').map(s => s.trim()).filter(Boolean);

  // Map active dimensions to structured notes
  for (const dimId of activeDimensions) {
    const dim = DIMENSION_CATALOGUE[dimId];
    if (!dim) continue;

    // For each dimension, generate a review prompt based on what the brief requires.
    // Strengths: what should be achieved for this dimension
    // Drift: what the drift guards warn against

    // Find drift guards relevant to this dimension
    const relevantGuards = driftGuards.filter(g => {
      const gl = g.toLowerCase();
      return dim.driftGuardKeywords?.some(kw => gl.includes(kw));
    });

    if (relevantGuards.length > 0) {
      // Add as structured review items
      for (const guard of relevantGuards) {
        driftIssues.push(`[${dim.label}] check: ${guard}`);
        correctNextPass.push(`enforce: ${guard}`);
      }
    }

    // Canon focus strengths — what we want to see
    const focusMatch = canonFocus.filter(cf => {
      const dimMap = {
        subject_continuity: ['anatomy'],
        silhouette_read: ['silhouette'],
        material_costume_logic: ['costume_logic', 'material_language'],
        palette_mood: ['palette', 'lighting'],
        composition_framing: ['composition'],
        ornamental_drift: ['costume_logic'],
        era_faction_drift: ['era_logic', 'faction_read'],
        identity_stability: ['anatomy'],
        readability: [],
        lane_fit: [],
      };
      return (dimMap[dimId] || []).includes(cf);
    });

    if (focusMatch.length > 0) {
      strengths.push(`[${dim.label}] brief targets: ${focusMatch.join(', ')}`);
      preserveNextPass.push(`maintain ${dim.label.toLowerCase()} from this candidate`);
    }
  }

  // Negative prompt items become potential drift issues
  const topNegatives = negatives.slice(0, 5);
  for (const neg of topNegatives) {
    driftIssues.push(`negative check: ${neg}`);
  }

  return {
    filename: candidate.filename,
    seed: candidate.seed,
    overall_fit: 'usable', // Default — human or LLM overrides
    // H2: this is the ONLY assignment site for overall_fit anywhere in the
    // codebase — nothing currently overrides it, so every candidate in
    // every critique report is uniformly 'usable' by construction. That is
    // a non-judgment ("nobody has looked at the image yet"), not a judgment
    // ("looked, and they're all fine") — `reviewed: false` records which one
    // this is so recommendAction() (below) and the CLI can tell the two
    // apart instead of presenting keyword-drift tiebreaking as a considered
    // recommendation. Flip to true at the (future, NOT built here — see the
    // finding's explicit scoping note) point where a human or LLM judge
    // actually assesses fit and overrides overall_fit.
    reviewed: false,
    // EXTERNAL_VERIFIER: this rule-based engine is a different artifact class
    // from the image generator, so it is a legitimate cross-artifact verifier.
    judged_by_model: RULE_BASED_JUDGE,
    generator_model: generatorModel,
    strengths,
    drift_issues: driftIssues,
    preserve_next_pass: preserveNextPass,
    correct_next_pass: correctNextPass,
  };
}

// ─── Triage (UNCERTAINTY_GATED_HUMANS) ───────────────────────────

/**
 * Default drift-issue count at/above which a candidate is flagged for human
 * attention. Tunable per invocation via `sdlab critique --triage --drift-threshold N`.
 */
export const DEFAULT_DRIFT_THRESHOLD = 3;

/**
 * Split candidates into the ones a human should look at vs the ones the
 * rule-based pass cleared — so attention gates on UNCERTAINTY, not on every item
 * (Buçinca et al. arXiv:2410.04253). A candidate is flagged when it is
 * `off-model` (a human/LLM downgraded its fit) OR carries >= driftThreshold
 * drift issues. The full report is unchanged; triage is a VIEW over it.
 *
 * @param {Array} candidates — report.candidates
 * @param {Object} [opts]
 * @param {number} [opts.driftThreshold=DEFAULT_DRIFT_THRESHOLD]
 * @returns {{ flagged: Array, suppressed: Array, driftThreshold: number }}
 */
export function triageCandidates(candidates, { driftThreshold = DEFAULT_DRIFT_THRESHOLD } = {}) {
  const flagged = [];
  const suppressed = [];
  for (const c of candidates || []) {
    const driftCount = c.drift_issues?.length ?? 0;
    const uncertain = c.overall_fit === 'off-model' || driftCount >= driftThreshold;
    (uncertain ? flagged : suppressed).push(c);
  }
  return { flagged, suppressed, driftThreshold };
}

// ─── Run-level recommendation ────────────────────────────────────

/**
 * Derive a run-level recommended action from candidate notes.
 *
 * H2: `overall_fit: 'usable'` (critiqueCandidate's default, and — today —
 * its ONLY assignment anywhere in the codebase) means "nobody has assessed
 * fit yet", not "assessed and found uniformly usable". Before this fix,
 * recommendAction() could not tell those two states apart, so an unreviewed
 * run always took the same `usable.length > 0` branch a genuinely-reviewed
 * run would, picking a "preferred" candidate by brief-keyword drift count —
 * not by looking at the image — and presenting it with the same confidence
 * either way. `reviewed` on the returned recommendation lets the CLI (see
 * scripts/critique.js) qualify or suppress the auto "Next:" suggestion when
 * nothing has actually been reviewed, without changing `mode` /
 * `preferred_candidate` semantics for callers that don't look at it —
 * critique.json's shape stays backward-compatible (additive field only).
 */
export function recommendAction({ candidates }) {
  if (candidates.length === 0) {
    return { mode: 'discard_run', reason: 'No candidates in run', reviewed: false };
  }

  const anyReviewed = candidates.some(c => c.reviewed === true);

  const strong = candidates.filter(c => c.overall_fit === 'strong');
  const usable = candidates.filter(c => c.overall_fit === 'usable');
  const offModel = candidates.filter(c => c.overall_fit === 'off-model');

  // If any are strong, accept the best
  if (strong.length > 0) {
    return {
      mode: 'accept_one',
      preferred_candidate: strong[0].filename,
      reason: `${strong.length} strong candidate(s) — ${strong[0].filename} is the best fit`,
      reviewed: anyReviewed,
    };
  }

  // If mostly usable, refine from the best one
  if (usable.length > 0) {
    // Pick the one with fewest drift issues
    const sorted = [...usable].sort((a, b) => a.drift_issues.length - b.drift_issues.length);
    return {
      mode: 'refine_from_one',
      preferred_candidate: sorted[0].filename,
      reason: anyReviewed
        ? `${usable.length} usable candidate(s) — ${sorted[0].filename} has fewest drift issues`
        : `${usable.length} candidate(s) at the unreviewed default "usable" — nobody has assessed fit yet. ` +
          `${sorted[0].filename} has the fewest rule-based drift issues, which is a tiebreaker, not a ` +
          `judgment of the image.`,
      reviewed: anyReviewed,
    };
  }

  // All off-model
  if (offModel.length === candidates.length) {
    return {
      mode: 'discard_run',
      reason: 'All candidates are off-model — brief may need fundamental revision',
      reviewed: anyReviewed,
    };
  }

  // Mixed bag — rerun
  return {
    mode: 'rerun_broader',
    reason: 'No clear winner — try broader seed range or adjusted parameters',
    reviewed: anyReviewed,
  };
}

// ─── Main critique function ──────────────────────────────────────

/**
 * Generate a full critique report for a completed run.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot — absolute project path
 * @param {string} opts.projectId — project name
 * @param {string} opts.runId — run ID to critique
 * @returns {Promise<Object>} critique report
 */
export async function critiqueRun({ projectRoot, projectId, runId }) {
  // Load run manifest
  const manifest = await loadRun(projectRoot, runId);
  const runDir = join(getRunsDir(projectRoot), runId);

  // Load the brief from the run directory
  const briefPath = join(runDir, 'brief.json');
  if (!existsSync(briefPath)) {
    throw inputError(
      'CRITIQUE_NO_BRIEF',
      `Run "${runId}" has no brief.json`,
      'The run must have a brief artifact to critique against.'
    );
  }
  const brief = JSON.parse(readFileSync(briefPath, 'utf-8'));

  // Load workflow profile
  const workflow = await getWorkflowProfile(projectRoot, brief.workflow_id);

  // Determine active dimensions
  const activeDimensions = getActiveDimensions({ brief, workflow });

  // Build candidate list from manifest outputs
  const successfulOutputs = (manifest.outputs || []).filter(
    o => o.status === 'ok' || o.status === 'dry_run'
  );

  if (successfulOutputs.length === 0) {
    throw inputError(
      'CRITIQUE_NO_OUTPUTS',
      `Run "${runId}" has no successful outputs to critique`,
      'Run must have at least one successful output.'
    );
  }

  // EXTERNAL_VERIFIER: derive the generator model id from the run manifest and
  // warn once if the rule-based judge ever coincides with it (it never does
  // today — the rule engine is a different artifact class from the generator).
  const generatorModel = generatorModelFromManifest(manifest);
  warnIfSelfVerification(RULE_BASED_JUDGE, generatorModel, `run ${runId}`);

  // Critique each candidate
  const candidates = successfulOutputs.map(output =>
    critiqueCandidate({
      brief,
      workflow,
      candidate: { filename: output.filename, seed: output.seed },
      activeDimensions,
      generatorModel,
    })
  );

  // Derive recommendation
  const recommended = recommendAction({ candidates });

  // Build report
  const report = {
    run_id: runId,
    project_id: projectId,
    brief_id: brief.brief_id,
    workflow_id: brief.workflow_id,
    created_at: new Date().toISOString(),
    active_dimensions: activeDimensions,
    judged_by_model: RULE_BASED_JUDGE,
    generator_model: generatorModel,
    candidates,
    recommended_action: recommended,
  };

  if (brief.subject_id) {
    report.subject_id = brief.subject_id;
  }

  return report;
}

/**
 * Save a critique report to the run directory.
 */
export async function saveCritique(projectRoot, runId, report, markdown) {
  const runDir = join(getRunsDir(projectRoot), runId);
  await writeFile(join(runDir, 'critique.json'), JSON.stringify(report, null, 2) + '\n');
  await writeFile(join(runDir, 'critique.md'), markdown);
}

/**
 * Load a saved critique from a run directory.
 */
export function loadCritique(projectRoot, runId) {
  const critiquePath = join(getRunsDir(projectRoot), runId, 'critique.json');
  if (!existsSync(critiquePath)) {
    throw inputError(
      'CRITIQUE_NOT_FOUND',
      `No critique found for run "${runId}"`,
      `Run: sdlab critique --run ${runId}`
    );
  }
  return JSON.parse(readFileSync(critiquePath, 'utf-8'));
}
