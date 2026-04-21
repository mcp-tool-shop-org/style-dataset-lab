/**
 * Snapshot creation and management.
 *
 * A snapshot is a frozen, versioned selection of records from a project
 * at a point in time. Once created, it never silently changes.
 */

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { createHash, randomBytes } from 'node:crypto';
import { loadProjectConfig, loadSelectionProfile, detectLane, detectGroup } from './config.js';
import { evaluateEligibility } from './eligibility.js';
import { inputError } from './errors.js';

/**
 * Derive which rule names were evaluated against a record for a given profile.
 * Mirrors the order of checks in evaluateEligibility() so the trace is stable.
 */
function rulesCheckedForProfile(profile) {
  const rules = [];
  if (profile.require_judgment) rules.push('require_judgment');
  if (profile.require_status?.length > 0) rules.push('require_status');
  if (profile.require_canon_bound) rules.push('require_canon_bound');
  if (profile.minimum_pass_ratio != null) rules.push('minimum_pass_ratio');
  if (profile.exclude_lanes?.length > 0) rules.push('exclude_lanes');
  if (profile.rights_filter != null) rules.push('rights_filter');
  if (profile.exclude_tags?.length > 0) rules.push('exclude_tags');
  return rules;
}

/**
 * Generate a snapshot ID: snap-YYYYMMDD-HHMMSS-XXXX
 */
function generateSnapshotId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14); // YYYYMMDDHHMMSS
  const rand = randomBytes(2).toString('hex');
  return `snap-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

/**
 * Compute config fingerprint — SHA-256 of all 5 config files concatenated.
 * Deterministic: files read in alphabetical order.
 */
export function computeConfigFingerprint(projectRoot) {
  const configFiles = [
    'constitution.json',
    'lanes.json',
    'project.json',
    'rubric.json',
    'terminology.json',
  ];

  const hash = createHash('sha256');
  for (const file of configFiles) {
    const filePath = join(projectRoot, file);
    if (existsSync(filePath)) {
      hash.update(`--- ${file} ---\n`);
      hash.update(readFileSync(filePath, 'utf-8'));
      hash.update('\n');
    }
  }
  return hash.digest('hex');
}

/**
 * Create a snapshot — frozen selection of eligible records.
 * @param {string} projectRoot — absolute path to project
 * @param {Object} profile — selection profile
 * @returns {Promise<{snapshotId: string, included: number, excluded: number}>}
 */
export async function createSnapshot(projectRoot, profile, options = {}) {
  const config = loadProjectConfig(projectRoot);
  const recordsDir = join(projectRoot, 'records');
  const snapshotId = generateSnapshotId();
  const snapshotDir = join(projectRoot, 'snapshots', snapshotId);

  // D-005: refuse to proceed if the generated ID has collided with an existing
  // snapshot dir — silent overwrite would break Law 1 (snapshots are frozen).
  if (!options.dryRun && existsSync(snapshotDir)) {
    throw inputError(
      'SNAPSHOT_ID_COLLISION',
      `Snapshot directory already exists: ${snapshotDir}`,
      'Retry to generate a fresh snapshot ID.',
    );
  }

  const configFingerprint = computeConfigFingerprint(projectRoot);
  const profileId = profile.profile_id || profile.id || 'unknown';
  const rulesChecked = rulesCheckedForProfile(profile);

  // Load all records (sorted for deterministic output)
  const files = (await readdir(recordsDir))
    .filter(f => f.endsWith('.json'))
    .sort();

  const included = [];
  const excluded = [];
  const laneDistribution = {};
  const factionDistribution = {};
  const verdictDistribution = { pass: 0, fail: 0, partial: 0 };

  for (const file of files) {
    const raw = await readFile(join(recordsDir, file), 'utf-8');
    const record = JSON.parse(raw);

    const { eligible, reasons } = evaluateEligibility(
      record, profile, config.lanes, config.terminology
    );

    if (eligible) {
      const prompt = record.provenance?.prompt || '';
      const lane = detectLane(record.id, prompt, config.lanes);
      const faction = detectGroup(record.id, prompt, config.terminology);

      // Build reason trace
      const passRatio = record.canon?.assertion_count > 0
        ? `${record.canon.pass_count}/${record.canon.assertion_count}`
        : 'n/a';
      const reason = `${record.judgment.status}, canon-bound, pass_ratio=${passRatio}, lane=${lane}`;

      // D-006: record the rule-trace + profile context so inclusion is
      // replayable without re-running evaluateEligibility.
      included.push({
        record_id: record.id,
        reason,
        rules_checked: rulesChecked,
        profile_id: profileId,
        config_fingerprint: configFingerprint,
      });

      // Track distributions
      laneDistribution[lane] = (laneDistribution[lane] || 0) + 1;
      factionDistribution[faction || 'unknown'] = (factionDistribution[faction || 'unknown'] || 0) + 1;
      if (record.canon?.assertions) {
        for (const a of record.canon.assertions) {
          verdictDistribution[a.verdict] = (verdictDistribution[a.verdict] || 0) + 1;
        }
      }
    } else {
      excluded.push({ record_id: record.id, reasons });
    }
  }

  // Write snapshot files (skip if dry run)
  if (options.dryRun) {
    return { snapshotId, included: included.length, excluded: excluded.length };
  }
  await mkdir(snapshotDir, { recursive: true });

  const manifest = {
    snapshot_id: snapshotId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-snapshot-v1',
    project_name: config.meta.name,
    frozen: true,
    selection_profile: profile,
    config_fingerprint: configFingerprint,
    config_versions: {
      constitution: config.constitution.version || '1.0.0',
      project: config.meta.version || '0.0.0',
    },
    counts: {
      total_records: files.length,
      evaluated: files.length,
      included: included.length,
      excluded: excluded.length,
    },
  };

  const summary = {
    snapshot_id: snapshotId,
    lane_distribution: laneDistribution,
    faction_distribution: factionDistribution,
    verdict_distribution: verdictDistribution,
  };

  await writeFile(join(snapshotDir, 'snapshot.json'), JSON.stringify(manifest, null, 2) + '\n');
  await writeFile(join(snapshotDir, 'included.jsonl'), included.map(r => JSON.stringify(r)).join('\n') + '\n');
  await writeFile(join(snapshotDir, 'excluded.jsonl'), excluded.map(r => JSON.stringify(r)).join('\n') + '\n');
  await writeFile(join(snapshotDir, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');

  return { snapshotId, included: included.length, excluded: excluded.length };
}

/**
 * Load a snapshot manifest.
 */
export async function loadSnapshot(projectRoot, snapshotId) {
  const path = join(projectRoot, 'snapshots', snapshotId, 'snapshot.json');
  if (!existsSync(path)) {
    throw new Error(`Snapshot "${snapshotId}" not found at ${path}`);
  }
  return JSON.parse(await readFile(path, 'utf-8'));
}

/**
 * Load included record IDs from a snapshot.
 */
export async function loadSnapshotIncluded(projectRoot, snapshotId) {
  const path = join(projectRoot, 'snapshots', snapshotId, 'included.jsonl');
  const raw = await readFile(path, 'utf-8');
  return raw.trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
}

/**
 * List all snapshots in a project.
 */
export async function listSnapshots(projectRoot) {
  const snapshotsDir = join(projectRoot, 'snapshots');
  if (!existsSync(snapshotsDir)) return [];

  const entries = await readdir(snapshotsDir, { withFileTypes: true });
  const snapshots = [];

  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('snap-')) continue;
    try {
      const manifest = JSON.parse(
        await readFile(join(snapshotsDir, entry.name, 'snapshot.json'), 'utf-8')
      );
      snapshots.push({
        id: manifest.snapshot_id,
        created_at: manifest.created_at,
        included: manifest.counts.included,
        excluded: manifest.counts.excluded,
        fingerprint: manifest.config_fingerprint.slice(0, 12),
      });
    } catch {
      // Skip malformed snapshots
    }
  }

  return snapshots.sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/**
 * Diff two snapshots — records added, removed, and shared.
 */
export async function diffSnapshots(projectRoot, idA, idB) {
  const includedA = await loadSnapshotIncluded(projectRoot, idA);
  const includedB = await loadSnapshotIncluded(projectRoot, idB);

  const setA = new Set(includedA.map(r => r.record_id));
  const setB = new Set(includedB.map(r => r.record_id));

  const added = [...setB].filter(id => !setA.has(id));
  const removed = [...setA].filter(id => !setB.has(id));
  const shared = [...setA].filter(id => setB.has(id));

  return { added, removed, shared, countA: setA.size, countB: setB.size };
}
