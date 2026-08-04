/**
 * Split engine — subject-isolated, lane-balanced dataset splitting.
 *
 * Laws:
 * 1. Records sharing a subject family always land in the same split
 * 2. Lane balance is maintained within defined tolerances
 * 3. Splits are deterministic (seeded PRNG, sorted inputs)
 * 4. Every split produces an audit trail proving no leakage
 */

import { readFile, writeFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
import { loadProjectConfig, loadSplitProfile, detectLane } from './config.js';
import { loadSnapshot, loadSnapshotIncluded, SCHEMA_VERSION, checkManifestVersion, claimIdDir } from './snapshot.js';
import { loadRecord } from './records.js';

/**
 * SDL-C2: share of subject families (0–1) resolved via the id-stripping
 * fallback above which the guess is considered "meaningful" enough that
 * lib/card.js must withhold its "None (verified)" leakage claim. Chosen
 * conservatively low — even a modest guessed share means confidence rests
 * on an unverified naming heuristic, not authored identity.
 */
export const GUESSED_FAMILY_MEANINGFUL_SHARE = 0.1;

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
 * SDL-C2: normalize a record ID into a canonical subject stem.
 *
 * Used by the id-stripping fallback (resolveSubjectFamily case 3) and by
 * the independent leakage cross-check (auditStemCollisions). The naive
 * `.replace(/_[vs]\d+$/, '')` regex it replaces had two gaps that let one
 * real subject split into two families:
 *
 *   - case sensitivity: "fooV2" and "foo_V2" normalized to two different
 *     stems instead of one.
 *   - suffix-only matching: real id schemes embed the version/seed marker
 *     as an INFIX token on one segment (`styleset_p04v2_crane_tower`), not
 *     only as a trailing suffix (`styleset_p04_crane_tower_v1`). The old
 *     regex only ever matched the latter shape.
 *
 * Approach: lowercase, split on `_`, strip a trailing `v<digits>` /
 * `s<digits>` marker from EACH segment individually (not just the whole
 * id), drop any segment that normalizes to empty (a segment that WAS only
 * the marker), and rejoin. Both example ids above reduce to
 * "styleset_p04_crane_tower".
 */
export function normalizeIdStem(id) {
  const segments = String(id).toLowerCase().split('_');
  const cleaned = segments
    .map(seg => seg.replace(/[vs]\d+$/, ''))
    .filter(seg => seg.length > 0);
  // Every segment stripped to nothing (pathological all-marker id) — fall
  // back to the lowercased original rather than collapsing to ''.
  return cleaned.length > 0 ? cleaned.join('_') : String(id).toLowerCase();
}

/**
 * Determine the subject family for a record.
 *
 * Priority:
 * 1. identity.subject_name (named characters like renna_vasik)
 * 2. lineage.derived_from_record_id (walk chain to root ancestor)
 * 3. Strip version/seed markers from record ID (normalizeIdStem)
 *
 * SDL-C2: case 3 is a GUESS, not an authored fact — on real data (every
 * salt-road record has zero identity.subject_name) it fires for 100% of
 * records. Callers must not treat a guessed resolution as equivalent in
 * confidence to an authored one; the `guessed` flag lets them track and
 * surface that distinction instead of guessing silently.
 *
 * @returns {{family: string, guessed: boolean}}
 */
function resolveSubjectFamily(record) {
  // 1. Named subject
  if (record.identity?.subject_name) {
    return { family: record.identity.subject_name, guessed: false };
  }

  // 2. Lineage chain — use root ancestor ID as family. Authored data (the
  // pipeline recorded this derivation), not a guess.
  if (record.lineage?.derived_from_record_id) {
    // We return the ancestor ID; the caller's ancestor map handles chain walking
    return { family: record.lineage.derived_from_record_id, guessed: false };
  }

  // 3. Strip version/seed markers from record ID — case-insensitive,
  // infix-aware. Nothing authored says these records share a subject;
  // we are inferring it from a naming convention.
  return { family: normalizeIdStem(record.id), guessed: true };
}

/**
 * Walk lineage chains to find root ancestors.
 * Returns a map: recordId → {family, guessed}
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
        // Root not in dataset — strip markers from root ID (SDL-C2: same
        // case-insensitive, infix-aware normalization as case 3 above;
        // this is a guess too).
        ancestorMap.set(record.id, { family: normalizeIdStem(rootId), guessed: true });
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

  // Assign each record to a subject family. Resolution is cached per
  // record-id (recordResolution) so the second assignment pass below reuses
  // the exact same {family, guessed} decision rather than re-deriving it —
  // the two passes must never be able to disagree.
  const familyMap = new Map(); // family → [record]
  const familyGuessed = new Map(); // family → true if ANY member arrived via id-stripping fallback
  const recordResolution = new Map(); // record.id → {family, guessed}
  for (const record of records) {
    const resolution = ancestorMap.has(record.id)
      ? ancestorMap.get(record.id)
      : resolveSubjectFamily(record);
    recordResolution.set(record.id, resolution);
    const { family, guessed } = resolution;
    if (!familyMap.has(family)) familyMap.set(family, []);
    familyMap.get(family).push(record);
    if (guessed) familyGuessed.set(family, true);
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
    // Reuse the exact resolution cached during the family-map build pass
    // above — recomputing here would risk the two passes silently
    // disagreeing (D-003's whole point is to catch that class of bug).
    const { family } = recordResolution.get(record.id);

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

  // Leakage audit — checks whether the assignment's OWN family map spans
  // partitions. By construction this can never fire (the assignment loop
  // groups by family before splitting) unless there's a bug in the
  // assignment step itself; it cannot see a bad family RESOLUTION (SDL-C2).
  const leakageIssues = auditLeakage(familyMap, trainRecords, valRecords, testRecords);

  // SDL-C2b: independent cross-check. Never reads familyMap/ancestorMap —
  // re-derives a canonical id stem per record from scratch and flags any
  // case where records sharing a stem (i.e. very likely one real subject)
  // ended up placed in more than one partition. This is the only check
  // that can catch SDL-C2-shaped bugs, including future regressions of
  // resolveSubjectFamily/normalizeIdStem that the leakage_check above
  // would stay blind to.
  const stemCollisionIssues = auditStemCollisions(records, trainRecords, valRecords, testRecords);

  // SDL-C2: surface how much of the split's leakage-freedom claim rests on
  // guessed (id-stripped) family resolution vs. authored subject_name /
  // lineage. On real project data (salt-road: 99/99 records, zero
  // identity.subject_name) this is 100% — silent guessing is how SDL-C2
  // stayed invisible. Never silent again: counted here, warned on below,
  // and consumed by lib/card.js to gate the "None (verified)" claim.
  let guessedFamilies = 0;
  for (const family of familyMap.keys()) {
    if (familyGuessed.get(family)) guessedFamilies++;
  }
  let guessedRecords = 0;
  for (const resolution of recordResolution.values()) {
    if (resolution.guessed) guessedRecords++;
  }
  const totalFamilies = familyMap.size;
  const guessedFamilyRatio = totalFamilies > 0 ? guessedFamilies / totalFamilies : 0;
  // Conservatively low: even a modest guessed share means the leakage-free
  // claim is resting on an unverified naming-convention heuristic rather
  // than authored identity, which is worth a caveat rather than silence.
  const meaningfulGuessShare = guessedFamilyRatio > GUESSED_FAMILY_MEANINGFUL_SHARE;
  const familyResolution = {
    total_families: totalFamilies,
    guessed_families: guessedFamilies,
    guessed_family_ratio: +guessedFamilyRatio.toFixed(3),
    total_records: records.length,
    guessed_records: guessedRecords,
    guessed_record_ratio: records.length > 0 ? +(guessedRecords / records.length).toFixed(3) : 0,
    meaningful_guess_share_threshold: GUESSED_FAMILY_MEANINGFUL_SHARE,
    meaningful_guess_share: meaningfulGuessShare,
  };
  if (meaningfulGuessShare) {
    warnings.push(
      `${guessedFamilies} of ${totalFamilies} subject families ` +
      `(${(guessedFamilyRatio * 100).toFixed(1)}%) were inferred by stripping version/seed ` +
      `markers from record IDs — no identity.subject_name or lineage authored. ` +
      `Verify subject grouping manually; the leakage-free claim on this split is unverified for these families.`,
    );
  }
  if (stemCollisionIssues.length > 0) {
    warnings.push(
      `subject-stem cross-check found ${stemCollisionIssues.length} case(s) where records sharing ` +
      `a canonical id stem were resolved to different families — see audit.json stem_collision_check.`,
    );
  }

  // Lane balance audit (DB-005: includes deviation from profile ratios)
  const laneBalance = auditLaneBalance(
    records, trainRecords, valRecords, testRecords, config.lanes, profile
  );

  // Write output (skip if dry run)
  if (options.dryRun) {
    // Dry run never touches disk — nothing to atomically claim; a fresh
    // preview id is enough to characterize the shape of the result.
    const splitId = generateSplitId();
    return { splitId, train: trainRecords.length, val: valRecords.length, test: testRecords.length };
  }
  // SDL-M10: atomically claim the split id/dir — closes the check-then-act
  // race the old existsSync+recursive-mkdir pattern had (D-005's intent,
  // now actually race-proof; see claimIdDir in snapshot.js).
  const { id: splitId, dir: splitDir } = await claimIdDir(
    join(projectRoot, 'splits'),
    generateSplitId,
    {
      code: 'SPLIT_ID_COLLISION',
      message: 'Could not claim a unique split ID — every candidate collided with an existing split directory.',
      hint: 'Retry; if this persists, another sdlab process may be creating splits in a tight loop.',
    },
  );

  const manifest = {
    // DB-001 / DB-006: stamp manifest schema version
    schema_version: SCHEMA_VERSION,
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
    // SDL-C2b: distinct from leakage_check above — independently re-derived,
    // does not reuse familyMap, and is the only check that can detect a
    // SDL-C2-shaped family-resolution bug. Read this key (not
    // leakage_check) to know whether the independent cross-check fired.
    stem_collision_check: {
      passed: stemCollisionIssues.length === 0,
      issues: stemCollisionIssues,
    },
    // SDL-C2: how much of family resolution rests on the id-stripping
    // guess vs. authored identity/lineage. lib/card.js reads this to
    // decide whether "None (verified)" is honest to print.
    family_resolution: familyResolution,
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
 * SDL-C2b: independent leakage cross-check.
 *
 * auditLeakage() above can only ever confirm that the assignment loop's OWN
 * familyMap is internally consistent — by construction every record with a
 * given family key was grouped and placed together, so that check can never
 * observe a case where family RESOLUTION itself was wrong (two records that
 * are really the same subject but got resolved to two different family
 * keys — SDL-C2). This function never reads familyMap or ancestorMap.
 *
 * It re-derives a canonical id stem for every record directly from the
 * record's own id (normalizeIdStem — the same normalization the fixed
 * resolveSubjectFamily now uses), independent of whatever family label the
 * assignment computed. It then asks a question the assignment's own audit
 * structurally cannot ask: did records that share a canonical stem (i.e.
 * are very likely one real subject) end up placed in more than one
 * partition? A "yes" is real, unambiguous leakage regardless of what family
 * label the assignment used internally — including if a future regression
 * reintroduces a SDL-C2-shaped bug in family resolution.
 *
 * Returns an array of issues (empty = clean). Each issue also carries
 * `assigned_families` — the (possibly multiple) family labels the members
 * were actually resolved to, purely as an operator diagnostic; it is never
 * consulted for the pass/fail decision above.
 */
function auditStemCollisions(records, trainIds, valIds, testIds) {
  const trainSet = new Set(trainIds);
  const valSet = new Set(valIds);
  const testSet = new Set(testIds);

  const byStem = new Map(); // canonical stem → [record]
  for (const record of records) {
    const stem = normalizeIdStem(record.id);
    if (!byStem.has(stem)) byStem.set(stem, []);
    byStem.get(stem).push(record);
  }

  const issues = [];
  for (const [stem, recs] of byStem) {
    if (recs.length < 2) continue; // nothing to collide with

    const partitions = new Set();
    for (const r of recs) {
      if (trainSet.has(r.id)) partitions.add('train');
      if (valSet.has(r.id)) partitions.add('val');
      if (testSet.has(r.id)) partitions.add('test');
    }
    if (partitions.size <= 1) continue; // same stem, same partition — fine

    const assignedFamilies = [...new Set(recs.map(r => resolveSubjectFamily(r).family))].sort();

    issues.push({
      canonical_stem: stem,
      record_ids: recs.map(r => r.id).sort(),
      spans_partitions: [...partitions].sort(),
      assigned_families: assignedFamilies,
    });
  }

  issues.sort((a, b) => a.canonical_stem.localeCompare(b.canonical_stem));
  return issues;
}

/**
 * Audit lane balance across splits.
 *
 * DB-005: includes deviation-from-profile metric per lane + overall score.
 * A lane that shows train=100/val=0/test=0 and another at 33/33/33 look
 * equally "balanced" by percentage alone — deviation makes the real gap
 * between intent and reality visible at a glance.
 */
function auditLaneBalance(records, trainIds, valIds, testIds, lanesConfig, profile) {
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

  // Compute percentages + deviation from profile ratios (DB-005)
  const targetTrain = (profile?.train_ratio ?? 0) * 100;
  const targetVal = (profile?.val_ratio ?? 0) * 100;
  const targetTest = (profile?.test_ratio ?? 0) * 100;

  let overallDeviation = 0;
  const deviations = {};

  for (const lane of Object.keys(balance)) {
    const b = balance[lane];
    b.train_pct = b.total > 0 ? +(b.train / b.total * 100).toFixed(1) : 0;
    b.val_pct = b.total > 0 ? +(b.val / b.total * 100).toFixed(1) : 0;
    b.test_pct = b.total > 0 ? +(b.test / b.total * 100).toFixed(1) : 0;

    // DB-005: absolute deviation from profile target per partition
    const devTrain = Math.abs(b.train_pct - targetTrain);
    const devVal = Math.abs(b.val_pct - targetVal);
    const devTest = Math.abs(b.test_pct - targetTest);
    // Lane deviation: sum of per-partition absolute deviations (max ~200)
    const laneDev = +(devTrain + devVal + devTest).toFixed(1);
    b.deviation_from_target = {
      train: +devTrain.toFixed(1),
      val: +devVal.toFixed(1),
      test: +devTest.toFixed(1),
      total: laneDev,
    };
    deviations[lane] = laneDev;
    overallDeviation += laneDev;
  }

  // Attach a summary so the operator sees the signal without scanning per-lane rows.
  balance._summary = {
    target_ratios_pct: {
      train: +targetTrain.toFixed(1),
      val: +targetVal.toFixed(1),
      test: +targetTest.toFixed(1),
    },
    overall_deviation_score: +overallDeviation.toFixed(1),
    worst_lane: Object.keys(deviations).length > 0
      ? Object.entries(deviations).sort((a, b) => b[1] - a[1])[0][0]
      : null,
  };

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
  const manifest = JSON.parse(await readFile(path, 'utf-8'));
  checkManifestVersion(manifest, 'split');
  return manifest;
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
