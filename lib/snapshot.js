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
import { warn } from './log.js';

/**
 * DB-001 / DB-006: Manifest schema version. Every manifest.json written by
 * snapshot/split/export/eval-pack/eval-run/training-manifest/training-package/
 * impl-pack stamps this version; readers log a WARNING on version mismatch
 * (best-effort compatibility).
 *
 * 2.3.0 (v3.3.0): PIN_PER_STEP — the ComfyUI run manifest now also stamps this
 * version and carries a `pinning` block (comfy_workflow_sha + model/LoRA content
 * hashes + seed_policy; see lib/run-manifest.js). The block is additive and
 * optional, so a legacy manifest with no schema_version / no pinning still loads
 * (checkManifestVersion only warns; it never throws).
 */
export const SCHEMA_VERSION = '2.3.0';

/**
 * Warn if a loaded manifest's schema_version does not match the reader.
 * Non-fatal — continues with best-effort compatibility. No warning when
 * manifest is missing the field (legacy unstamped artifacts).
 */
export function checkManifestVersion(manifest, kind) {
  if (manifest?.schema_version && manifest.schema_version !== SCHEMA_VERSION) {
    warn(
      `${kind} schema v${manifest.schema_version} loaded by v${SCHEMA_VERSION} reader — continuing with best-effort compatibility`,
    );
  }
}

/**
 * SDL-M10: atomically claim a fresh, unused SUBDIRECTORY of `parentDir`.
 *
 * The pattern this replaces — `existsSync(dir)` then throw-if-true,
 * followed later by `mkdir(dir, {recursive:true})` — is check-then-act: a
 * second concurrent process can create the same directory in the window
 * between the check and the mkdir, and recursive mkdir never throws on an
 * already-existing directory, so the race is silently invisible (two
 * builders interleave writes into one snapshot/split/export/etc. dir —
 * Law 1 exposure: "snapshots frozen").
 *
 * Mirrors lib/selections.js's claimSelectionId: a non-recursive `mkdir`
 * is atomic at the filesystem level (POSIX and Windows both guarantee
 * this) — it either creates the directory and returns, or fails with
 * EEXIST if something else claimed that exact name first. On EEXIST we
 * regenerate a fresh id and retry; for the timestamp+random ids used
 * throughout this module, two consecutive real collisions is already
 * vanishingly unlikely.
 *
 * Creating `parentDir` itself (e.g. "snapshots/") is NOT part of the race
 * being closed here — two processes racing to create the same shared
 * parent with {recursive:true} is harmless (both succeed; no caller's
 * data lives directly in the parent, only under their own distinctly
 * named leaf directory).
 *
 * @param {string} parentDir — parent directory, created recursively if missing
 * @param {() => string} generateId — produces a candidate leaf id; called
 *   again on every retry so concurrent claimants converge on different ids
 * @param {{code: string, message: string, hint: string, maxAttempts?: number}} onExhausted
 *   — error identity thrown if every attempt collides (kept caller-specific
 *   so existing codes like SNAPSHOT_ID_COLLISION stay externally stable)
 * @returns {Promise<{id: string, dir: string}>}
 */
export async function claimIdDir(parentDir, generateId, onExhausted) {
  const maxAttempts = onExhausted.maxAttempts ?? 25;
  if (!existsSync(parentDir)) {
    await mkdir(parentDir, { recursive: true });
  }
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const id = generateId();
    const dir = join(parentDir, id);
    try {
      await mkdir(dir); // non-recursive — throws EEXIST if already claimed
      return { id, dir };
    } catch (err) {
      if (err.code === 'EEXIST') continue;
      throw err;
    }
  }
  throw inputError(onExhausted.code, onExhausted.message, onExhausted.hint);
}

/**
 * SDL-M10: atomically claim a fresh, unused FILE `<parentDir>/<id>.json`.
 *
 * Same TOCTOU problem as claimIdDir, but for the one artifact in this
 * domain stored as a flat file rather than a directory (training
 * manifests: `training/manifests/<id>.json`). The atomic primitive here
 * is `writeFile(..., {flag: 'wx'})` — exclusive create, which fails with
 * EEXIST rather than silently overwriting — so claim-and-write happen in
 * one step instead of racing a separate existsSync check against it.
 *
 * @param {string} parentDir — parent directory, created recursively if missing
 * @param {() => string} generateId — produces a candidate id; called again
 *   on every retry
 * @param {(id: string) => string} buildContent — renders the file content
 *   for a given candidate id (called fresh per attempt since the content
 *   embeds the id)
 * @param {{code: string, message: string, hint: string, maxAttempts?: number}} onExhausted
 * @returns {Promise<{id: string, filePath: string}>}
 */
export async function claimIdFile(parentDir, generateId, buildContent, onExhausted) {
  const maxAttempts = onExhausted.maxAttempts ?? 25;
  if (!existsSync(parentDir)) {
    await mkdir(parentDir, { recursive: true });
  }
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const id = generateId();
    const filePath = join(parentDir, `${id}.json`);
    try {
      await writeFile(filePath, buildContent(id), { flag: 'wx' }); // exclusive create — atomic
      return { id, filePath };
    } catch (err) {
      if (err.code === 'EEXIST') continue;
      throw err;
    }
  }
  throw inputError(onExhausted.code, onExhausted.message, onExhausted.hint);
}

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

  const configFingerprint = computeConfigFingerprint(projectRoot);
  const profileId = profile.profile_id || profile.id || 'unknown';
  const rulesChecked = rulesCheckedForProfile(profile);

  // Load all records (sorted for deterministic output)
  const files = (await readdir(recordsDir))
    .filter(f => f.endsWith('.json'))
    .sort();

  const included = [];
  const excluded = [];
  const unreadable = []; // DB-003: collect per-record parse errors, continue
  const laneDistribution = {};
  const factionDistribution = {};
  const verdictDistribution = { pass: 0, fail: 0, partial: 0 };

  for (const file of files) {
    // DB-003: wrap per-record JSON.parse in try/catch so one bad file does
    // not abort the entire snapshot. The operator sees an `unreadable` list
    // in the manifest + a WARNING count on stderr.
    let record;
    try {
      const raw = await readFile(join(recordsDir, file), 'utf-8');
      record = JSON.parse(raw);
    } catch (err) {
      unreadable.push({
        record_id: file.replace(/\.json$/, ''),
        file,
        error: err.message,
      });
      continue;
    }

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

  // DB-003: surface unreadable records loudly so partial parse failures
  // are not silent. Manifest also carries the full list for drill-down.
  if (unreadable.length > 0) {
    const sample = unreadable.slice(0, 5).map(u => u.file).join(', ');
    warn(
      `snapshot: ${unreadable.length} record file(s) were unreadable and skipped` +
      (unreadable.length > 5 ? ` (first 5: ${sample}, ...)` : ` (${sample})`),
    );
  }

  // Write snapshot files (skip if dry run)
  if (options.dryRun) {
    // Dry run never touches disk, so there is nothing to atomically claim —
    // a fresh preview id is enough to characterize the shape of the result.
    const snapshotId = generateSnapshotId();
    return { snapshotId, included: included.length, excluded: excluded.length, unreadable: unreadable.length };
  }

  // SDL-M10: atomically claim the snapshot id/dir — closes the
  // check-then-act race the old existsSync+recursive-mkdir pattern had
  // (D-005's intent, now actually race-proof; see claimIdDir above).
  const { id: snapshotId, dir: snapshotDir } = await claimIdDir(
    join(projectRoot, 'snapshots'),
    generateSnapshotId,
    {
      code: 'SNAPSHOT_ID_COLLISION',
      message: 'Could not claim a unique snapshot ID — every candidate collided with an existing snapshot directory.',
      hint: 'Retry; if this persists, another sdlab process may be creating snapshots in a tight loop.',
    },
  );

  const manifest = {
    // DB-001 / DB-006: stamp manifest schema version (reader checks on load)
    schema_version: SCHEMA_VERSION,
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
      // DB-003: evaluated reflects records actually parsed (excludes unreadable)
      evaluated: files.length - unreadable.length,
      included: included.length,
      excluded: excluded.length,
      unreadable: unreadable.length,
    },
    // DB-003: preserve the unreadable list so operators can investigate
    errors: unreadable,
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
  const manifest = JSON.parse(await readFile(path, 'utf-8'));
  checkManifestVersion(manifest, 'snapshot');
  return manifest;
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
