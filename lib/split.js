/**
 * Split engine — subject-isolated, lane-balanced dataset splitting.
 *
 * Laws:
 * 1. Records sharing a subject family always land in the same split
 * 2. Lane balance is maintained within defined tolerances
 * 3. Splits are deterministic (seeded PRNG, sorted inputs)
 * 4. Every split produces an audit trail proving no leakage
 */

import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
import { loadProjectConfig, loadSplitProfile, detectLane } from './config.js';
import { loadSnapshot, loadSnapshotIncluded } from './snapshot.js';
import { loadRecord } from './records.js';
import { inputError } from './errors.js';

/**
 * Mulberry32 — deterministic 32-bit PRNG.
 * Same seed always produces the same sequence.
 */
function mulberry32(seed) {
  let t = seed >>> 0;
  return function () {
    t = (t + 0x6d2b79f5) | 0;
    let v = t;
    v = Math.imul(v ^ (v >>> 15), v | 1);
    v ^= v + Math.imul(v ^ (v >>> 7), v | 61);
    return ((v ^ (v >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Fisher-Yates shuffle with seeded PRNG.
 */
function seededShuffle(arr, rng) {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/**
 * Generate a split ID: split-YYYYMMDD-HHMMSS-XXXX
 */
function generateSplitId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = randomBytes(2).toString('hex');
  return `split-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

/**
 * Determine the subject family for a record.
 *
 * Priority:
 * 1. identity.subject_name (named characters like renna_vasik)
 * 2. lineage.derived_from_record_id (walk chain to root ancestor)
 * 3. Strip _v\d+$, _s\d+$ suffixes from record ID
 */
function resolveSubjectFamily(record) {
  // 1. Named subject
  if (record.identity?.subject_name) {
    return record.identity.subject_name;
  }

  // 2. Lineage chain — use root ancestor ID as family
  if (record.lineage?.derived_from_record_id) {
    // We return the ancestor ID; the caller's ancestor map handles chain walking
    return record.lineage.derived_from_record_id;
  }

  // 3. Strip version/seed suffixes from record ID
  return record.id.replace(/_[vs]\d+$/, '');
}

/**
 * Walk lineage chains to find root ancestors.
 * Returns a map: recordId → rootAncestorFamily
 */
function buildAncestorMap(records) {
  const parentOf = new Map();
  const idToRecord = new Map();

  for (const record of records) {
    idToRecord.set(record.id, record);
    if (record.lineage?.derived_from_record_id) {
      parentOf.set(record.id, record.lineage.derived_from_record_id);
    }
  }

  // Walk each chain to root (with cycle protection)
  function findRoot(id, visited = new Set()) {
    if (visited.has(id)) return id; // cycle — stop
    visited.add(id);
    const parent = parentOf.get(id);
    if (!parent) return id;
    return findRoot(parent, visited);
  }

  const ancestorMap = new Map();
  for (const record of records) {
    if (record.lineage?.derived_from_record_id) {
      const rootId = findRoot(record.id);
      // Use the root's subject family
      const rootRecord = idToRecord.get(rootId);
      if (rootRecord) {
        ancestorMap.set(record.id, resolveSubjectFamily(rootRecord));
      } else {
        // Root not in dataset — strip suffixes from root ID
        ancestorMap.set(record.id, rootId.replace(/_[vs]\d+$/, ''));
      }
    }
  }

  return ancestorMap;
}

/**
 * Allocate `total` items across train/val/test using largest-remainder rounding,
 * guaranteeing each partition receives at least 1 when total >= 3.
 */
function allocateLargestRemainder(total, profile) {
  if (total <= 0) return { train: 0, val: 0, test: 0 };

  const ratios = {
    train: profile.train_ratio,
    val: profile.val_ratio,
    test: profile.test_ratio,
  };

  // Ideal fractional counts
  const ideal = {
    train: total * ratios.train,
    val: total * ratios.val,
    test: total * ratios.test,
  };

  // Floor + sort by fractional remainder desc (tie-break by partition name)
  const base = {
    train: Math.floor(ideal.train),
    val: Math.floor(ideal.val),
    test: Math.floor(ideal.test),
  };
  let assigned = base.train + base.val + base.test;

  const remainders = [
    ['train', ideal.train - base.train],
    ['val', ideal.val - base.val],
    ['test', ideal.test - base.test],
  ].sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1];
    return a[0].localeCompare(b[0]);
  });

  let ri = 0;
  while (assigned < total) {
    base[remainders[ri % remainders.length][0]]++;
    assigned++;
    ri++;
  }

  // Min-1 rebalance: if total >= 3 and any partition is 0, take from the
  // largest partition. Deterministic — always steal from 'train' first when tied.
  if (total >= 3) {
    const partitionOrder = ['train', 'val', 'test'];
    for (const part of partitionOrder) {
      if (base[part] === 0) {
        // find largest (ties broken by name asc to stay deterministic)
        const donor = partitionOrder
          .filter(p => p !== part && base[p] > 1)
          .sort((a, b) => {
            if (base[b] !== base[a]) return base[b] - base[a];
            return a.localeCompare(b);
          })[0];
        if (donor) {
          base[donor]--;
          base[part]++;
        }
      }
    }
  }

  return base;
}

/**
 * Create a split from a snapshot.
 *
 * @param {string} projectRoot — absolute path to project
 * @param {string} snapshotId — snapshot to split
 * @param {Object} profile — split profile (from loadSplitProfile)
 * @returns {Promise<{splitId: string, train: number, val: number, test: number}>}
 */
export async function createSplit(projectRoot, snapshotId, profile, options = {}) {
  const config = loadProjectConfig(projectRoot);
  const snapshot = await loadSnapshot(projectRoot, snapshotId);
  const includedEntries = await loadSnapshotIncluded(projectRoot, snapshotId);
  const recordsDir = join(projectRoot, 'records');

  // Load full records for included entries
  const records = [];
  for (const entry of includedEntries) {
    const record = await loadRecord(recordsDir, entry.record_id);
    if (record) records.push(record);
  }

  // Build ancestor map for lineage chain resolution
  const ancestorMap = buildAncestorMap(records);

  // Assign each record to a subject family
  const familyMap = new Map(); // family → [record]
  for (const record of records) {
    let family;
    if (ancestorMap.has(record.id)) {
      family = ancestorMap.get(record.id);
    } else {
      family = resolveSubjectFamily(record);
    }
    if (!familyMap.has(family)) familyMap.set(family, []);
    familyMap.get(family).push(record);
  }

  // D-002: Deterministic primary lane per family = majority vote; ties
  // broken by lexicographic lane name. Record the per-family decision
  // for the audit so the chosen lane is explainable.
  const familyLane = new Map();
  const familyLaneDecisions = [];
  for (const [family, recs] of familyMap) {
    const laneCounts = new Map();
    for (const rec of recs) {
      const prompt = rec.provenance?.prompt || '';
      const recLane = detectLane(rec.id, prompt, config.lanes);
      laneCounts.set(recLane, (laneCounts.get(recLane) || 0) + 1);
    }
    // Sort: count desc, then lane name asc. Deterministic winner.
    const ranked = [...laneCounts.entries()].sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1];
      return a[0].localeCompare(b[0]);
    });
    const [chosenLane, chosenCount] = ranked[0];
    familyLane.set(family, chosenLane);
    familyLaneDecisions.push({
      family,
      chosen_lane: chosenLane,
      chosen_count: chosenCount,
      record_count: recs.length,
      lane_counts: Object.fromEntries(laneCounts),
    });
  }
  familyLaneDecisions.sort((a, b) => a.family.localeCompare(b.family));

  // Group families by lane
  const laneGroups = new Map(); // lane → [family]
  for (const [family, lane] of familyLane) {
    if (!laneGroups.has(lane)) laneGroups.set(lane, []);
    laneGroups.get(lane).push(family);
  }

  // Split families per lane using seeded PRNG
  // D-011: seed:0 is a valid seed; use nullish coalescing so 0 is honored.
  const rng = mulberry32(profile.seed ?? 42);
  const trainFamilies = new Set();
  const valFamilies = new Set();
  const testFamilies = new Set();
  const warnings = [];

  const sortedLanes = [...laneGroups.keys()].sort();
  for (const lane of sortedLanes) {
    const families = laneGroups.get(lane).sort(); // sort for determinism before shuffle
    const shuffled = seededShuffle(families, rng);

    if (shuffled.length < 3) {
      // Too few families — all to train
      for (const f of shuffled) trainFamilies.add(f);
      warnings.push(`lane "${lane}": only ${shuffled.length} families — all assigned to train`);
      continue;
    }

    // D-004: Largest-remainder allocation guarantees min-1 per partition
    // when total >= 3, and emits a warning if any partition ends up at 0.
    const total = shuffled.length;
    const { train: trainCount, val: valCount, test: testCount } =
      allocateLargestRemainder(total, profile);

    if (total >= 3 && (trainCount === 0 || valCount === 0 || testCount === 0)) {
      warnings.push(
        `lane "${lane}": partition size hit 0 after allocation (train=${trainCount}, val=${valCount}, test=${testCount}) — ratios may be extreme`,
      );
    }

    let idx = 0;
    for (let i = 0; i < trainCount && idx < total; i++, idx++) {
      trainFamilies.add(shuffled[idx]);
    }
    for (let i = 0; i < valCount && idx < total; i++, idx++) {
      valFamilies.add(shuffled[idx]);
    }
    while (idx < total) {
      testFamilies.add(shuffled[idx]);
      idx++;
    }
  }

  // Build record → split assignment
  const trainRecords = [];
  const valRecords = [];
  const testRecords = [];

  for (const record of records) {
    let family;
    if (ancestorMap.has(record.id)) {
      family = ancestorMap.get(record.id);
    } else {
      family = resolveSubjectFamily(record);
    }

    if (trainFamilies.has(family)) trainRecords.push(record.id);
    else if (valFamilies.has(family)) valRecords.push(record.id);
    else if (testFamilies.has(family)) testRecords.push(record.id);
    else {
      // D-003: unassigned family means the familyMap build pass disagreed
      // with the assignment pass — never silently rescue; surface the bug.
      throw new Error(
        `unassigned family for record ${record.id} (family=${family}) — ` +
        `this indicates a bug in family resolution; the record was not placed in train/val/test`,
      );
    }
  }

  // Sort for deterministic output
  trainRecords.sort();
  valRecords.sort();
  testRecords.sort();

  // Leakage audit
  const leakageIssues = auditLeakage(familyMap, trainRecords, valRecords, testRecords);

  // Lane balance audit
  const laneBalance = auditLaneBalance(
    records, trainRecords, valRecords, testRecords, config.lanes
  );

  // Write output (skip if dry run)
  const splitId = generateSplitId();
  if (options.dryRun) {
    return { splitId, train: trainRecords.length, val: valRecords.length, test: testRecords.length };
  }
  const splitDir = join(projectRoot, 'splits', splitId);
  // D-005: refuse to silently overwrite on ID collision.
  if (existsSync(splitDir)) {
    throw inputError(
      'SPLIT_ID_COLLISION',
      `Split directory already exists: ${splitDir}`,
      'Retry to generate a fresh split ID.',
    );
  }
  await mkdir(splitDir, { recursive: true });

  const manifest = {
    split_id: splitId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-split-v1',
    snapshot_id: snapshotId,
    snapshot_fingerprint: snapshot.config_fingerprint,
    profile,
    counts: {
      total_records: records.length,
      total_families: familyMap.size,
      train: trainRecords.length,
      val: valRecords.length,
      test: testRecords.length,
    },
    warnings,
  };

  const audit = {
    split_id: splitId,
    leakage_check: {
      passed: leakageIssues.length === 0,
      issues: leakageIssues,
    },
    lane_balance: laneBalance,
    family_count: familyMap.size,
    families_per_split: {
      train: trainFamilies.size,
      val: valFamilies.size,
      test: testFamilies.size,
    },
    // D-002: record the deterministic per-family lane decision for replay.
    family_lane_decisions: familyLaneDecisions,
    warnings,
  };

  await writeFile(join(splitDir, 'split.json'), JSON.stringify(manifest, null, 2) + '\n');
  await writeFile(join(splitDir, 'train.jsonl'), trainRecords.map(id => JSON.stringify({ record_id: id })).join('\n') + '\n');
  await writeFile(join(splitDir, 'val.jsonl'), valRecords.map(id => JSON.stringify({ record_id: id })).join('\n') + '\n');
  await writeFile(join(splitDir, 'test.jsonl'), testRecords.map(id => JSON.stringify({ record_id: id })).join('\n') + '\n');
  await writeFile(join(splitDir, 'audit.json'), JSON.stringify(audit, null, 2) + '\n');

  return { splitId, train: trainRecords.length, val: valRecords.length, test: testRecords.length };
}

/**
 * Audit for subject leakage across splits.
 * Returns an array of issues (empty = clean).
 */
function auditLeakage(familyMap, trainIds, valIds, testIds) {
  const trainSet = new Set(trainIds);
  const valSet = new Set(valIds);
  const testSet = new Set(testIds);
  const issues = [];

  for (const [family, records] of familyMap) {
    const splits = new Set();
    for (const r of records) {
      if (trainSet.has(r.id)) splits.add('train');
      if (valSet.has(r.id)) splits.add('val');
      if (testSet.has(r.id)) splits.add('test');
    }
    if (splits.size > 1) {
      issues.push({
        family,
        record_count: records.length,
        leaked_to: [...splits],
      });
    }
  }

  return issues;
}

/**
 * Audit lane balance across splits.
 */
function auditLaneBalance(records, trainIds, valIds, testIds, lanesConfig) {
  const trainSet = new Set(trainIds);
  const valSet = new Set(valIds);
  const testSet = new Set(testIds);
  const balance = {};

  for (const record of records) {
    const prompt = record.provenance?.prompt || '';
    const lane = detectLane(record.id, prompt, lanesConfig);
    if (!balance[lane]) balance[lane] = { total: 0, train: 0, val: 0, test: 0 };
    balance[lane].total++;
    if (trainSet.has(record.id)) balance[lane].train++;
    else if (valSet.has(record.id)) balance[lane].val++;
    else if (testSet.has(record.id)) balance[lane].test++;
  }

  // Compute percentages
  for (const lane of Object.keys(balance)) {
    const b = balance[lane];
    b.train_pct = b.total > 0 ? +(b.train / b.total * 100).toFixed(1) : 0;
    b.val_pct = b.total > 0 ? +(b.val / b.total * 100).toFixed(1) : 0;
    b.test_pct = b.total > 0 ? +(b.test / b.total * 100).toFixed(1) : 0;
  }

  return balance;
}

/**
 * Load a split manifest.
 */
export async function loadSplit(projectRoot, splitId) {
  const path = join(projectRoot, 'splits', splitId, 'split.json');
  if (!existsSync(path)) {
    throw new Error(`Split "${splitId}" not found at ${path}`);
  }
  return JSON.parse(await readFile(path, 'utf-8'));
}

/**
 * Load split record IDs for a partition.
 */
export async function loadSplitPartition(projectRoot, splitId, partition) {
  const path = join(projectRoot, 'splits', splitId, `${partition}.jsonl`);
  const raw = await readFile(path, 'utf-8');
  return raw.trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
}

/**
 * Load split audit.
 */
export async function loadSplitAudit(projectRoot, splitId) {
  const path = join(projectRoot, 'splits', splitId, 'audit.json');
  return JSON.parse(await readFile(path, 'utf-8'));
}

/**
 * List all splits in a project.
 */
export async function listSplits(projectRoot) {
  const splitsDir = join(projectRoot, 'splits');
  if (!existsSync(splitsDir)) return [];

  const entries = await readdir(splitsDir, { withFileTypes: true });
  const splits = [];

  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('split-')) continue;
    try {
      const manifest = JSON.parse(
        await readFile(join(splitsDir, entry.name, 'split.json'), 'utf-8')
      );
      splits.push({
        id: manifest.split_id,
        created_at: manifest.created_at,
        snapshot_id: manifest.snapshot_id,
        train: manifest.counts.train,
        val: manifest.counts.val,
        test: manifest.counts.test,
        families: manifest.counts.total_families,
      });
    } catch {
      // Skip malformed
    }
  }

  return splits.sort((a, b) => a.created_at.localeCompare(b.created_at));
}
