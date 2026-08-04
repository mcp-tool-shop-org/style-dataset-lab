/**
 * SDL-C2 / SDL-C2b: subject-family normalization + independent leakage
 * cross-check.
 *
 * SDL-C2: resolveSubjectFamily's id-stripping fallback used
 * `.replace(/_[vs]\d+$/, '')`, which is case-sensitive and only strips a
 * TRAILING version/seed marker. Real id schemes embed the marker as an
 * INFIX token on one segment (`styleset_p04v2_crane_tower`), which the old
 * regex left untouched — splitting one real subject into two families.
 *
 * SDL-C2b: the pre-existing leakage audit (auditLeakage) iterates the
 * SAME familyMap the assignment used, so it structurally cannot detect a
 * bad family RESOLUTION — only a bad ASSIGNMENT given a family map it
 * already trusts. auditStemCollisions is an independent cross-check that
 * never reads familyMap/ancestorMap.
 *
 * Per the assignment brief: existing tests in this repo have a known prior
 * trap — collision/leakage tests that only ever assert the PASS branch.
 * These tests deliberately drive the RED/failing branch, not just the
 * happy path.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createSnapshot } from '../../lib/snapshot.js';
import { createSplit, normalizeIdStem, GUESSED_FAMILY_MEANINGFUL_SHARE } from '../../lib/split.js';
import { generateCard } from '../../lib/card.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

const PROFILE = {
  profile_id: 'family-resolution-test',
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
};

// ─── normalizeIdStem: pure-function proof of the exact SDL-C2 defect ─────

test('SDL-C2: normalizeIdStem merges a trailing suffix marker and an infix marker onto the same stem', () => {
  // Exact example from the finding: real id scheme uses v2 as an INFIX
  // token on the "p04" segment, not a trailing "_v2" suffix.
  const suffixForm = normalizeIdStem('styleset_p04_crane_tower_v1');
  const infixForm = normalizeIdStem('styleset_p04v2_crane_tower');
  assert.equal(suffixForm, 'styleset_p04_crane_tower');
  assert.equal(infixForm, 'styleset_p04_crane_tower');
  assert.equal(suffixForm, infixForm, 'suffix and infix variant markers must normalize to the same stem');
});

test('SDL-C2: normalizeIdStem is case-insensitive', () => {
  assert.equal(normalizeIdStem('fooV2'), 'foo');
  assert.equal(normalizeIdStem('foo_V2'), 'foo');
  assert.equal(normalizeIdStem('fooV2'), normalizeIdStem('foo_V2'));
});

test('SDL-C2: normalizeIdStem leaves ids with no version marker unchanged (lowercased)', () => {
  assert.equal(normalizeIdStem('Renna_Vasik'), 'renna_vasik');
});

// ─── End-to-end: the two example ids must land in the same partition ────

test('SDL-C2: infix + suffix variant-marker ids merge into one family and never split across partitions', async () => {
  // Pigeonhole construction: exactly 3 families under FIXED resolution
  // (the merged crane-tower family + 2 authored fillers), near-even
  // ratios force an exact 1/1/1 allocation — so whichever partition the
  // merged family lands in, BOTH member ids land there deterministically,
  // for every seed, with no probability involved.
  const records = [
    makeRecord({ id: 'styleset_p04_crane_tower_v1' }), // no identity/lineage -> fallback
    makeRecord({ id: 'styleset_p04v2_crane_tower' }),  // no identity/lineage -> fallback, INFIX marker
    makeRecord({ id: 'filler_alpha', identity: { subject_name: 'filler_alpha' } }),
    makeRecord({ id: 'filler_beta', identity: { subject_name: 'filler_beta' } }),
  ];
  const proj = createTmpProject({ records });
  try {
    for (const seed of [1, 2, 3, 42]) {
      const snap = await createSnapshot(proj.projectRoot, PROFILE);
      const r = await createSplit(proj.projectRoot, snap.snapshotId, {
        train_ratio: 0.34, val_ratio: 0.33, test_ratio: 0.33, seed,
      });

      const [train, val, testP] = await Promise.all(
        ['train', 'val', 'test'].map(p =>
          readFile(join(proj.projectRoot, 'splits', r.splitId, `${p}.jsonl`), 'utf-8')));

      const inSamePartition = (part) =>
        part.includes('styleset_p04_crane_tower_v1') && part.includes('styleset_p04v2_crane_tower');
      const together = inSamePartition(train) || inSamePartition(val) || inSamePartition(testP);
      assert.ok(together, `seed ${seed}: both crane-tower variants must land in the same partition`);

      // 3 families total post-merge (not 4) — confirms they actually
      // merged rather than coincidentally landing together as 2 families.
      assert.equal(r.train + r.val + r.test, 4);
      const audit = JSON.parse(await readFile(
        join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));
      assert.equal(audit.family_count, 3, `seed ${seed}: expected 3 merged families`);
      assert.equal(audit.stem_collision_check.passed, true,
        `seed ${seed}: no stem collision expected once merged correctly`);
    }
  } finally {
    proj.cleanup();
  }
});

// ─── SDL-C2: guessing must be counted and surfaced, not silent ──────────

test('SDL-C2: id-stripping fallback usage is counted, warned on, and reaches the audit (mirrors salt-road: 0 authored subject_name)', async () => {
  const records = [];
  for (let i = 0; i < 12; i++) {
    // No identity, no lineage — every record takes the id-stripping
    // fallback, exactly like all 99 live salt-road records.
    records.push(makeRecord({ id: `subject_${String(i).padStart(3, '0')}_v1` }));
  }
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 5,
    });
    const audit = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));

    assert.ok(audit.family_resolution, 'family_resolution must be present on the audit');
    assert.equal(audit.family_resolution.total_families, 12);
    assert.equal(audit.family_resolution.guessed_families, 12, 'all 12 families used the fallback');
    assert.equal(audit.family_resolution.guessed_family_ratio, 1);
    assert.equal(audit.family_resolution.meaningful_guess_share, true);
    assert.ok(
      audit.family_resolution.guessed_family_ratio > GUESSED_FAMILY_MEANINGFUL_SHARE,
      'ratio must exceed the documented threshold for meaningful_guess_share to be true',
    );

    const manifest = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'split.json'), 'utf-8'));
    assert.ok(
      manifest.warnings.some(w => /inferred by stripping/.test(w)),
      `expected a guessed-family warning, got: ${JSON.stringify(manifest.warnings)}`,
    );
  } finally {
    proj.cleanup();
  }
});

test('SDL-C2: a small, non-meaningful guessed share does not trip meaningful_guess_share', async () => {
  // 1 guessed family out of ~15 authored ones — below the 10% threshold.
  const records = [makeRecord({ id: 'guessed_only_v1' })];
  for (let i = 0; i < 14; i++) {
    records.push(makeRecord({ id: `named_${i}`, identity: { subject_name: `named_${i}` } }));
  }
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 5,
    });
    const audit = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));
    assert.equal(audit.family_resolution.guessed_families, 1);
    assert.equal(audit.family_resolution.total_families, 15);
    assert.ok(audit.family_resolution.guessed_family_ratio < GUESSED_FAMILY_MEANINGFUL_SHARE);
    assert.equal(audit.family_resolution.meaningful_guess_share, false);
  } finally {
    proj.cleanup();
  }
});

// ─── SDL-C2b: independent cross-check catches what leakage_check cannot ──

test('SDL-C2b: stem-collision cross-check fires when leakage_check cannot — RED branch driven explicitly', async () => {
  // Two records share a canonical id stem ("crane_tower") but carry
  // DIFFERENT authored identity.subject_name values (a realistic metadata
  // inconsistency) — so the real assignment treats them as two distinct,
  // internally-consistent SINGLETON families. leakage_check can never fire
  // on a singleton family (it never spans a partition by definition).
  //
  // Pigeonhole: exactly 3 singleton families + near-even ratios force an
  // exact 1/1/1 split — the two target families are GUARANTEED to land in
  // different partitions, for every seed, no probability involved.
  const records = [
    makeRecord({ id: 'crane_tower_v1', identity: { subject_name: 'tower_alpha' } }),
    makeRecord({ id: 'crane_towerv2', identity: { subject_name: 'tower_beta' } }),
    makeRecord({ id: 'filler_1', identity: { subject_name: 'filler_1' } }),
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.34, val_ratio: 0.33, test_ratio: 0.33, seed: 3,
    });

    // Confirm the pigeonhole actually landed as designed.
    assert.equal(r.train, 1);
    assert.equal(r.val, 1);
    assert.equal(r.test, 1);

    const audit = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));

    // The ORIGINAL check is blind here: each family is an internally
    // consistent singleton, so it never spans a partition.
    assert.equal(audit.leakage_check.passed, true,
      'leakage_check cannot see this — both families are singletons by construction');
    assert.equal(audit.leakage_check.issues.length, 0);

    // The independent cross-check catches it — this is the RED branch:
    // must NOT just assert the pass case like the prior-art leakage test.
    assert.equal(audit.stem_collision_check.passed, false,
      'stem_collision_check must fire where leakage_check cannot');
    assert.equal(audit.stem_collision_check.issues.length, 1);
    const issue = audit.stem_collision_check.issues[0];
    assert.equal(issue.canonical_stem, 'crane_tower');
    assert.deepEqual(issue.record_ids, ['crane_tower_v1', 'crane_towerv2']);
    assert.equal(issue.spans_partitions.length, 2);
    assert.deepEqual(issue.assigned_families, ['tower_alpha', 'tower_beta']);
  } finally {
    proj.cleanup();
  }
});

test('SDL-C2b: stem_collision_check passes clean (empty issues) on a leakage-free split — explicit PASS branch for contrast', async () => {
  const records = [
    makeRecord({ id: 'alpha_v1', identity: { subject_name: 'alpha' } }),
    makeRecord({ id: 'alpha_v2', identity: { subject_name: 'alpha' } }),
    makeRecord({ id: 'beta_v1', identity: { subject_name: 'beta' } }),
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1,
    });
    const audit = JSON.parse(await readFile(
      join(proj.projectRoot, 'splits', r.splitId, 'audit.json'), 'utf-8'));
    assert.equal(audit.stem_collision_check.passed, true);
    assert.deepEqual(audit.stem_collision_check.issues, []);
  } finally {
    proj.cleanup();
  }
});

// ─── card.js: "None (verified)" must be withheld, not just flipped ──────

test('SDL-C2b: dataset card cannot print "None (verified)" when stem_collision_check has findings', async () => {
  const records = [
    makeRecord({ id: 'crane_tower_v1', identity: { subject_name: 'tower_alpha' } }),
    makeRecord({ id: 'crane_towerv2', identity: { subject_name: 'tower_beta' } }),
    makeRecord({ id: 'filler_1', identity: { subject_name: 'filler_1' } }),
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.34, val_ratio: 0.33, test_ratio: 0.33, seed: 3,
    });
    const { markdown, json } = await generateCard(proj.projectRoot, snap.snapshotId, r.splitId);
    assert.equal(json.split.leakage_free, false);
    assert.ok(!markdown.includes('None (verified)'), 'card must not claim verified leakage-free status');
    assert.ok(markdown.includes('DETECTED'), 'card must surface the detected stem collision');
  } finally {
    proj.cleanup();
  }
});

test('SDL-C2: dataset card cannot print "None (verified)" when a meaningful share of families were guessed', async () => {
  const records = [];
  for (let i = 0; i < 12; i++) {
    records.push(makeRecord({ id: `subject_${String(i).padStart(3, '0')}_v1` }));
  }
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 5,
    });
    const { markdown, json } = await generateCard(proj.projectRoot, snap.snapshotId, r.splitId);
    // Structurally clean (no actual collisions) — but NOT verified, because
    // every family's resolution rests on the unauthored id-guess.
    assert.equal(json.split.leakage_free, true, 'no structural collision was found');
    assert.equal(json.split.leakage_verified, false, 'but it must not be marked verified');
    assert.ok(!markdown.includes('None (verified)'),
      'card must not claim "None (verified)" when guessed-family share is meaningful');
    assert.ok(markdown.includes('UNVERIFIED'), 'card must render the unverified caveat');
  } finally {
    proj.cleanup();
  }
});

test('card.js gracefully defaults when loading a pre-SDL-C2b audit.json that lacks the new fields', async () => {
  const records = [
    makeRecord({ id: 'alpha_v1', identity: { subject_name: 'alpha' } }),
    makeRecord({ id: 'beta_v1', identity: { subject_name: 'beta' } }),
    makeRecord({ id: 'gamma_v1', identity: { subject_name: 'gamma' } }),
  ];
  const proj = createTmpProject({ records });
  try {
    const snap = await createSnapshot(proj.projectRoot, PROFILE);
    const r = await createSplit(proj.projectRoot, snap.snapshotId, {
      train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 1,
    });
    // Simulate a legacy on-disk audit.json (pre-SDL-C2b) by stripping the
    // new keys, mirroring what real projects/ artifacts look like today.
    const auditPath = join(proj.projectRoot, 'splits', r.splitId, 'audit.json');
    const audit = JSON.parse(await readFile(auditPath, 'utf-8'));
    delete audit.stem_collision_check;
    delete audit.family_resolution;
    const { writeFile } = await import('node:fs/promises');
    await writeFile(auditPath, JSON.stringify(audit, null, 2) + '\n');

    const { markdown, json } = await generateCard(proj.projectRoot, snap.snapshotId, r.splitId);
    assert.equal(json.split.leakage_free, true);
    assert.equal(json.split.leakage_verified, true);
    assert.ok(markdown.includes('None (verified)'));
  } finally {
    proj.cleanup();
  }
});
