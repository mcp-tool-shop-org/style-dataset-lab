/**
 * Canon-aware eval pack builder.
 *
 * Eval packs are curated test instruments that verify a model's
 * relationship with project canon. Four task types:
 *
 * 1. Lane coverage — representative approved records per lane
 * 2. Forbidden drift — rejected/borderline records paired with violated rules
 * 3. Anchor/gold — highest pass-ratio records per faction
 * 4. Subject continuity — same-subject records for identity testing
 */

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { loadProjectConfig, detectLane, detectGroup } from './config.js';
import { loadRecord } from './records.js';

/**
 * Generate an eval-pack ID: eval-YYYYMMDD-HHMMSS-XXXX
 */
function generateEvalId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = randomBytes(2).toString('hex');
  return `eval-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

/**
 * Build an eval pack from project records.
 *
 * @param {string} projectRoot
 * @param {Object} options — { maxPerLane?, maxPerFaction?, maxDrift?, maxContinuity? }
 * @returns {Promise<{evalId: string, tasks: Object}>}
 */
export async function buildEvalPack(projectRoot, options = {}) {
  const config = loadProjectConfig(projectRoot);
  const recordsDir = join(projectRoot, 'records');
  const files = (await readdir(recordsDir)).filter(f => f.endsWith('.json')).sort();

  const maxPerLane = options.maxPerLane || 5;
  const maxPerFaction = options.maxPerFaction || 3;
  const maxDrift = options.maxDrift || 20;
  const maxContinuity = options.maxContinuity || 10;

  // Load all records
  const records = [];
  for (const file of files) {
    const record = JSON.parse(await readFile(join(recordsDir, file), 'utf-8'));
    records.push(record);
  }

  // Task 1: Lane coverage
  const laneCoverage = buildLaneCoverage(records, config, maxPerLane);

  // Task 2: Forbidden drift
  const forbiddenDrift = buildForbiddenDrift(records, config, maxDrift);

  // Task 3: Anchor/gold
  const anchorGold = buildAnchorGold(records, config, maxPerFaction);

  // Task 4: Subject continuity
  const subjectContinuity = buildSubjectContinuity(records, maxContinuity);

  // Write eval pack
  const evalId = generateEvalId();
  const evalDir = join(projectRoot, 'eval-packs', evalId);
  await mkdir(evalDir, { recursive: true });

  const manifest = {
    eval_id: evalId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-eval-v1',
    project: config.meta.name,
    task_counts: {
      lane_coverage: laneCoverage.length,
      forbidden_drift: forbiddenDrift.length,
      anchor_gold: anchorGold.length,
      subject_continuity: subjectContinuity.length,
    },
    total_records: laneCoverage.length + forbiddenDrift.length +
      anchorGold.length + subjectContinuity.length,
  };

  await writeFile(join(evalDir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  await writeFile(join(evalDir, 'lane-coverage.jsonl'), laneCoverage.map(r => JSON.stringify(r)).join('\n') + '\n');
  await writeFile(join(evalDir, 'forbidden-drift.jsonl'), forbiddenDrift.map(r => JSON.stringify(r)).join('\n') + '\n');
  await writeFile(join(evalDir, 'anchor-gold.jsonl'), anchorGold.map(r => JSON.stringify(r)).join('\n') + '\n');
  await writeFile(join(evalDir, 'subject-continuity.jsonl'), subjectContinuity.map(r => JSON.stringify(r)).join('\n') + '\n');

  return {
    evalId,
    tasks: manifest.task_counts,
  };
}

/**
 * Task 1: Lane coverage — best approved record per lane.
 */
function buildLaneCoverage(records, config, maxPerLane) {
  const byLane = new Map();

  for (const record of records) {
    if (record.judgment?.status !== 'approved') continue;
    if (!record.canon?.assertions?.length) continue;

    const prompt = record.provenance?.prompt || '';
    const lane = detectLane(record.id, prompt, config.lanes);
    if (!byLane.has(lane)) byLane.set(lane, []);
    byLane.get(lane).push(record);
  }

  const result = [];
  for (const [lane, recs] of [...byLane].sort((a, b) => a[0].localeCompare(b[0]))) {
    // Sort by pass ratio descending
    const sorted = recs.sort((a, b) => {
      const ratioA = a.canon.assertion_count > 0 ? a.canon.pass_count / a.canon.assertion_count : 0;
      const ratioB = b.canon.assertion_count > 0 ? b.canon.pass_count / b.canon.assertion_count : 0;
      return ratioB - ratioA;
    });

    for (const record of sorted.slice(0, maxPerLane)) {
      result.push({
        task: 'lane_coverage',
        record_id: record.id,
        lane,
        pass_ratio: record.canon.assertion_count > 0
          ? +(record.canon.pass_count / record.canon.assertion_count).toFixed(3) : 0,
        asset_path: record.asset_path,
      });
    }
  }

  return result;
}

/**
 * Task 2: Forbidden drift — rejected/borderline records with violated rules.
 */
function buildForbiddenDrift(records, config, maxDrift) {
  const candidates = [];

  for (const record of records) {
    const status = record.judgment?.status;
    if (status !== 'rejected' && status !== 'borderline') continue;

    // Collect failure modes from judgment
    const failureModes = record.judgment?.failure_modes || [];
    // Collect failed canon assertions
    const failedAssertions = (record.canon?.assertions || [])
      .filter(a => a.verdict === 'fail')
      .map(a => a.rule_id || a.rule);

    const violations = [...new Set([...failureModes, ...failedAssertions])];
    if (violations.length === 0 && !record.judgment?.explanation) continue;

    candidates.push({
      task: 'forbidden_drift',
      record_id: record.id,
      status,
      violations,
      explanation: record.judgment?.explanation || null,
      asset_path: record.asset_path,
    });
  }

  // Sort by number of violations descending (most instructive first)
  candidates.sort((a, b) => b.violations.length - a.violations.length);
  return candidates.slice(0, maxDrift);
}

/**
 * Task 3: Anchor/gold — highest pass-ratio records per faction.
 */
function buildAnchorGold(records, config, maxPerFaction) {
  const byFaction = new Map();

  for (const record of records) {
    if (record.judgment?.status !== 'approved') continue;
    if (!record.canon?.assertions?.length) continue;

    const prompt = record.provenance?.prompt || '';
    const faction = detectGroup(record.id, prompt, config.terminology) || 'unknown';
    if (!byFaction.has(faction)) byFaction.set(faction, []);
    byFaction.get(faction).push(record);
  }

  const result = [];
  for (const [faction, recs] of [...byFaction].sort((a, b) => a[0].localeCompare(b[0]))) {
    const sorted = recs.sort((a, b) => {
      const ratioA = a.canon.assertion_count > 0 ? a.canon.pass_count / a.canon.assertion_count : 0;
      const ratioB = b.canon.assertion_count > 0 ? b.canon.pass_count / b.canon.assertion_count : 0;
      return ratioB - ratioA;
    });

    for (const record of sorted.slice(0, maxPerFaction)) {
      result.push({
        task: 'anchor_gold',
        record_id: record.id,
        faction,
        pass_ratio: record.canon.assertion_count > 0
          ? +(record.canon.pass_count / record.canon.assertion_count).toFixed(3) : 0,
        assertion_count: record.canon.assertion_count,
        asset_path: record.asset_path,
      });
    }
  }

  return result;
}

/**
 * Task 4: Subject continuity — groups of same-subject records for identity testing.
 */
function buildSubjectContinuity(records, maxGroups) {
  const bySubject = new Map();

  for (const record of records) {
    const subject = record.identity?.subject_name;
    if (!subject) continue;
    if (!bySubject.has(subject)) bySubject.set(subject, []);
    bySubject.get(subject).push(record);
  }

  const result = [];
  // Sort subjects by record count descending (richest clusters first)
  const sorted = [...bySubject].sort((a, b) => b[1].length - a[1].length);

  for (const [subject, recs] of sorted.slice(0, maxGroups)) {
    result.push({
      task: 'subject_continuity',
      subject_name: subject,
      record_count: recs.length,
      record_ids: recs.map(r => r.id).sort(),
      subject_type: recs[0].identity?.subject_type || 'unknown',
      faction: recs[0].identity?.faction || null,
    });
  }

  return result;
}

/**
 * List all eval packs in a project.
 */
export async function listEvalPacks(projectRoot) {
  const evalDir = join(projectRoot, 'eval-packs');
  if (!existsSync(evalDir)) return [];

  const entries = await readdir(evalDir, { withFileTypes: true });
  const packs = [];

  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('eval-')) continue;
    const manifestPath = join(evalDir, entry.name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const manifest = JSON.parse(await readFile(manifestPath, 'utf-8'));
      packs.push({
        id: manifest.eval_id,
        created_at: manifest.created_at,
        total: manifest.total_records,
        tasks: manifest.task_counts,
      });
    } catch {
      // Skip malformed
    }
  }

  return packs.sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/**
 * Load an eval pack manifest.
 */
export async function loadEvalPack(projectRoot, evalId) {
  const path = join(projectRoot, 'eval-packs', evalId, 'manifest.json');
  if (!existsSync(path)) {
    throw new Error(`Eval pack "${evalId}" not found at ${path}`);
  }
  return JSON.parse(await readFile(path, 'utf-8'));
}
