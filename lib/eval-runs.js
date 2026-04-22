/**
 * Eval run management.
 *
 * An eval run scores generated outputs against Phase 2 eval packs.
 * Every eval run links back to a training manifest and eval pack —
 * no orphan evals.
 */

import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { loadTrainingManifest } from './training-manifests.js';
import { loadEvalPack } from './eval-pack.js';
import { loadProjectConfig, detectLane, detectGroup } from './config.js';
import { SCHEMA_VERSION, checkManifestVersion } from './snapshot.js';

// DB-008: cap sample record_ids per failure bucket so scorecards stay small
// but the operator has enough detail to start investigation.
const SAMPLE_LIMIT = 5;

/**
 * Generate an eval run ID: er-YYYYMMDD-HHMMSS-XXXX
 */
function generateEvalRunId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = randomBytes(2).toString('hex');
  return `er-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

/**
 * Create an eval run — links a training manifest to an eval pack.
 *
 * @param {string} projectRoot
 * @param {string} manifestId — training manifest ID
 * @param {string} evalPackId — eval pack ID
 * @returns {Promise<{evalRunId: string}>}
 */
export async function createEvalRun(projectRoot, manifestId, evalPackId) {
  // Verify both exist
  const manifest = await loadTrainingManifest(projectRoot, manifestId);
  const evalPack = await loadEvalPack(projectRoot, evalPackId);

  const evalRunId = generateEvalRunId();
  const evalRunDir = join(projectRoot, 'training', 'eval-runs', evalRunId);
  await mkdir(evalRunDir, { recursive: true });

  const runManifest = {
    // DB-001 / DB-006: stamp manifest schema version
    schema_version: SCHEMA_VERSION,
    eval_run_id: evalRunId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-eval-run-v1',
    training_manifest_id: manifestId,
    eval_pack_id: evalPackId,
    source_export_id: manifest.source_export_id,
    training_profile_id: manifest.training_profile_id,
    adapter_target: manifest.adapter_target,
    status: 'created',
    scorecard: null,
  };

  await writeFile(join(evalRunDir, 'manifest.json'), JSON.stringify(runManifest, null, 2) + '\n');

  return { evalRunId };
}

/**
 * Score an eval run — compare generated outputs against eval pack tasks.
 *
 * Outputs are provided as a JSONL file where each line has:
 *   { record_id, generated_path, accept: true|false, notes? }
 *
 * @param {string} projectRoot
 * @param {string} evalRunId
 * @param {string} outputsPath — path to outputs index JSONL
 * @returns {Promise<{scorecard: Object}>}
 */
export async function scoreEvalRun(projectRoot, evalRunId, outputsPath) {
  const evalRunDir = join(projectRoot, 'training', 'eval-runs', evalRunId);
  const runManifest = JSON.parse(await readFile(join(evalRunDir, 'manifest.json'), 'utf-8'));
  const config = loadProjectConfig(projectRoot);

  // Load outputs
  const outputsRaw = await readFile(outputsPath, 'utf-8');
  const outputs = outputsRaw.trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

  // Copy outputs index into eval run
  await writeFile(join(evalRunDir, 'output-index.jsonl'), outputsRaw);

  // Load eval pack tasks
  const evalPackDir = join(projectRoot, 'eval-packs', runManifest.eval_pack_id);
  const taskFiles = {
    'lane-coverage': 'lane-coverage.jsonl',
    'forbidden-drift': 'forbidden-drift.jsonl',
    'anchor-gold': 'anchor-gold.jsonl',
    'subject-continuity': 'subject-continuity.jsonl',
  };

  const outputMap = new Map(outputs.map(o => [o.record_id, o]));

  // Score each task type
  const scores = {};

  for (const [taskName, fileName] of Object.entries(taskFiles)) {
    const taskPath = join(evalPackDir, fileName);
    if (!existsSync(taskPath)) continue;

    const taskEntries = (await readFile(taskPath, 'utf-8'))
      .trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

    if (taskName === 'lane-coverage') {
      scores.lane_coverage = scoreLaneCoverage(taskEntries, outputMap);
    } else if (taskName === 'forbidden-drift') {
      scores.forbidden_drift = scoreForbiddenDrift(taskEntries, outputMap);
    } else if (taskName === 'anchor-gold') {
      scores.anchor_gold = scoreAnchorGold(taskEntries, outputMap);
    } else if (taskName === 'subject-continuity') {
      scores.subject_continuity = scoreSubjectContinuity(taskEntries, outputMap);
    }
  }

  // Compute overall verdict
  const allPassed = Object.values(scores).every(s => s.passed);
  const overallScore = Object.values(scores).reduce((sum, s) => sum + (s.score || 0), 0) /
    Math.max(Object.values(scores).length, 1);

  const scorecard = {
    eval_run_id: evalRunId,
    scored_at: new Date().toISOString(),
    overall_verdict: allPassed ? 'pass' : 'fail',
    overall_score: +overallScore.toFixed(3),
    output_count: outputs.length,
    accepted_count: outputs.filter(o => o.accept).length,
    rejected_count: outputs.filter(o => !o.accept).length,
    tasks: scores,
  };

  // Write scorecard
  await writeFile(join(evalRunDir, 'scorecard.json'), JSON.stringify(scorecard, null, 2) + '\n');

  // Write summary markdown
  const summary = renderSummary(scorecard, runManifest);
  await writeFile(join(evalRunDir, 'summary.md'), summary);

  // Update manifest status
  runManifest.status = 'scored';
  runManifest.scorecard = scorecard;
  await writeFile(join(evalRunDir, 'manifest.json'), JSON.stringify(runManifest, null, 2) + '\n');

  return { scorecard };
}

function scoreLaneCoverage(tasks, outputMap) {
  let covered = 0;
  const lanes = new Set();
  // DB-008: collect record_ids that missed coverage so the operator can drill
  // down from "covered: 7/10" to "which 3 weren't covered".
  const missedSamples = [];
  for (const task of tasks) {
    lanes.add(task.lane);
    const output = outputMap.get(task.record_id);
    if (output?.accept) {
      covered++;
    } else if (missedSamples.length < SAMPLE_LIMIT) {
      missedSamples.push(task.record_id);
    }
  }
  const score = tasks.length > 0 ? covered / tasks.length : 0;
  return {
    task: 'lane_coverage',
    total: tasks.length,
    covered,
    missed: tasks.length - covered,
    missed_sample_record_ids: missedSamples,
    lanes_represented: lanes.size,
    score: +score.toFixed(3),
    passed: score >= 0.7,
  };
}

function scoreForbiddenDrift(tasks, outputMap) {
  // For forbidden drift, we check that rejected/borderline records are NOT accepted
  let correctRejections = 0;
  let falseAcceptances = 0;
  // DB-008: name the records that were wrongly accepted. Without this, a
  // scorecard that says "false_acceptances: 3" forces the operator to diff
  // outputs.jsonl against the eval pack manually.
  const falseAcceptanceSamples = [];
  for (const task of tasks) {
    const output = outputMap.get(task.record_id);
    if (!output || !output.accept) {
      correctRejections++;
    } else {
      falseAcceptances++;
      if (falseAcceptanceSamples.length < SAMPLE_LIMIT) {
        falseAcceptanceSamples.push(task.record_id);
      }
    }
  }
  const score = tasks.length > 0 ? correctRejections / tasks.length : 1;
  return {
    task: 'forbidden_drift',
    total: tasks.length,
    correct_rejections: correctRejections,
    false_acceptances: falseAcceptances,
    false_acceptance_sample_record_ids: falseAcceptanceSamples,
    score: +score.toFixed(3),
    passed: falseAcceptances === 0,
  };
}

function scoreAnchorGold(tasks, outputMap) {
  let matched = 0;
  // DB-008: which anchor records failed to match?
  const missedSamples = [];
  for (const task of tasks) {
    const output = outputMap.get(task.record_id);
    if (output?.accept) {
      matched++;
    } else if (missedSamples.length < SAMPLE_LIMIT) {
      missedSamples.push(task.record_id);
    }
  }
  const score = tasks.length > 0 ? matched / tasks.length : 0;
  return {
    task: 'anchor_gold',
    total: tasks.length,
    matched,
    missed: tasks.length - matched,
    missed_sample_record_ids: missedSamples,
    score: +score.toFixed(3),
    passed: score >= 0.8,
  };
}

function scoreSubjectContinuity(tasks, outputMap) {
  let subjectsWithCoverage = 0;
  // DB-008: which named subjects lost continuity coverage?
  const missedSamples = [];
  for (const task of tasks) {
    const recordIds = task.record_ids || [];
    const accepted = recordIds.filter(id => outputMap.get(id)?.accept).length;
    if (accepted >= 2) {
      subjectsWithCoverage++;
    } else if (missedSamples.length < SAMPLE_LIMIT) {
      missedSamples.push(task.subject_name || recordIds[0] || 'unknown');
    }
  }
  const score = tasks.length > 0 ? subjectsWithCoverage / tasks.length : 0;
  return {
    task: 'subject_continuity',
    total_subjects: tasks.length,
    subjects_with_coverage: subjectsWithCoverage,
    missed_subject_samples: missedSamples,
    score: +score.toFixed(3),
    passed: score >= 0.6,
  };
}

function renderSummary(scorecard, manifest) {
  const lines = [];
  lines.push(`# Eval Run: ${scorecard.eval_run_id}`);
  lines.push('');
  lines.push(`**Training manifest:** ${manifest.training_manifest_id}`);
  lines.push(`**Eval pack:** ${manifest.eval_pack_id}`);
  lines.push(`**Scored:** ${scorecard.scored_at}`);
  lines.push(`**Verdict:** ${scorecard.overall_verdict.toUpperCase()}`);
  lines.push(`**Overall score:** ${(scorecard.overall_score * 100).toFixed(1)}%`);
  lines.push('');
  lines.push(`**Outputs:** ${scorecard.output_count} total, ${scorecard.accepted_count} accepted, ${scorecard.rejected_count} rejected`);
  lines.push('');
  lines.push('## Task scores');
  lines.push('');
  lines.push('| Task | Score | Passed |');
  lines.push('|------|-------|--------|');
  for (const [name, task] of Object.entries(scorecard.tasks)) {
    lines.push(`| ${name} | ${(task.score * 100).toFixed(1)}% | ${task.passed ? 'YES' : 'NO'} |`);
  }
  lines.push('');
  return lines.join('\n');
}

/**
 * Load an eval run manifest.
 */
export async function loadEvalRun(projectRoot, evalRunId) {
  const path = join(projectRoot, 'training', 'eval-runs', evalRunId, 'manifest.json');
  if (!existsSync(path)) {
    throw new Error(`Eval run "${evalRunId}" not found at ${path}`);
  }
  return JSON.parse(await readFile(path, 'utf-8'));
}

/**
 * List all eval runs.
 */
export async function listEvalRuns(projectRoot) {
  const dir = join(projectRoot, 'training', 'eval-runs');
  if (!existsSync(dir)) return [];

  const entries = await readdir(dir, { withFileTypes: true });
  const runs = [];

  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('er-')) continue;
    const manifestPath = join(dir, entry.name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const data = JSON.parse(await readFile(manifestPath, 'utf-8'));
      runs.push({
        id: data.eval_run_id,
        created_at: data.created_at,
        status: data.status,
        manifest: data.training_manifest_id,
        eval_pack: data.eval_pack_id,
        verdict: data.scorecard?.overall_verdict || null,
      });
    } catch { /* skip */ }
  }

  return runs.sort((a, b) => a.created_at.localeCompare(b.created_at));
}
