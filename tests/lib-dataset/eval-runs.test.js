/**
 * F2 (HIGH): lib/eval-runs.js had ZERO test coverage anywhere in this repo
 * before this file. scoreEvalRun() rebuilt evalPackDir from the eval run's
 * stored eval_pack_id without ever re-checking the pack still exists on
 * disk. Each of the four task-file checks was a bare
 * `if (!existsSync(taskPath)) continue`, so when the pack directory was
 * gone, all four silently skipped, `scores` stayed `{}`, and
 * `Object.values({}).every(s => s.passed)` is vacuously `true` in
 * JavaScript — producing `overall_verdict: 'pass'`, `overall_score: 0.000`
 * for a model that was never actually evaluated against anything.
 *
 * This file covers:
 *   1. The normal path — a real eval pack, real task files, a genuine
 *      (non-empty, non-vacuous) scorecard.
 *   2. The missing-pack path — the eval pack directory is deleted after
 *      the eval run was created (createEvalRun only stores the id string;
 *      it never copies or re-verifies the pack). scoreEvalRun must throw a
 *      structured, directory-naming error instead of rubber-stamping a pass.
 *   3. The pack-directory-survives-but-every-task-file-is-gone variant,
 *      which the directory-existence check alone cannot see.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFile, mkdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';
import { buildEvalPack } from '../../lib/eval-pack.js';
import { createEvalRun, scoreEvalRun, loadEvalRun, listEvalRuns } from '../../lib/eval-runs.js';

const TASK_FILE_NAMES = [
  'lane-coverage.jsonl',
  'forbidden-drift.jsonl',
  'anchor-gold.jsonl',
  'subject-continuity.jsonl',
];

/**
 * Build a tmp project with real records, a real eval pack (via the actual
 * buildEvalPack — not hand-written JSON, so the task files reflect genuine
 * detection logic), and a hand-written training manifest.
 *
 * createEvalRun only reads manifest.source_export_id / training_profile_id /
 * adapter_target off the training manifest and never cross-validates them
 * against a real export — same simplification
 * fixtures/make-training-package-project.js already relies on for
 * buildTrainingPackage, so hand-writing the manifest here (rather than
 * running the full snapshot -> split -> export -> training-manifest chain)
 * is a faithful shortcut, not a gap in realism.
 *
 * Records: two share `identity.subject_name` (drives a real
 * subject-continuity task), the rest are unnamed (drive lane-coverage /
 * anchor-gold). All are approved + canon-bound so buildEvalPack's
 * lane-coverage and anchor-gold tasks are non-empty.
 */
async function buildEvalRunFixture() {
  const records = [
    makeRecord({ id: 'concept_0', identity: { subject_name: 'shared_subj' } }),
    makeRecord({ id: 'concept_1', identity: { subject_name: 'shared_subj' } }),
    makeRecord({ id: 'concept_2' }),
    makeRecord({ id: 'concept_3' }),
  ];
  const proj = createTmpProject({ records });

  const { evalId } = await buildEvalPack(proj.projectRoot, {});

  const profileId = 'evaltest-profile';
  const profilesDir = join(proj.projectRoot, 'training', 'profiles');
  await mkdir(profilesDir, { recursive: true });
  await writeFile(join(profilesDir, `${profileId}.json`), JSON.stringify({
    profile_id: profileId,
    label: 'Eval test profile',
    asset_type: 'concept',
    target_family: 'sdxl',
    adapter_targets: ['generic-image-caption'],
    eligible_lanes: [],
    caption_strategy: 'filename',
  }, null, 2));

  const manifestId = 'evaltest-manifest';
  const manifestsDir = join(proj.projectRoot, 'training', 'manifests');
  await mkdir(manifestsDir, { recursive: true });
  await writeFile(join(manifestsDir, `${manifestId}.json`), JSON.stringify({
    schema_version: '2.3.0',
    training_manifest_id: manifestId,
    created_at: new Date().toISOString(),
    training_profile_id: profileId,
    source_export_id: 'export-fake-00000000-000000-0000',
    source_snapshot_id: 'snap-fake-00000000-000000-0000',
    source_split_id: 'split-fake-00000000-000000-0000',
    config_fingerprint: 'fake-fingerprint',
    adapter_target: 'generic-image-caption',
  }, null, 2));

  return { ...proj, evalId, manifestId, records };
}

function writeOutputsAcceptingAll(projectRoot, records) {
  const outputsPath = join(projectRoot, 'outputs.jsonl');
  const outputs = records.map(r => ({
    record_id: r.id,
    generated_path: `generated/${r.id}.png`,
    accept: true,
  }));
  return writeFile(outputsPath, outputs.map(o => JSON.stringify(o)).join('\n') + '\n')
    .then(() => outputsPath);
}

// ─── Normal path: genuine, non-vacuous scoring ──────────────────────────

test('F2: scoreEvalRun produces a genuine non-vacuous scorecard against a real eval pack', async () => {
  const proj = await buildEvalRunFixture();
  try {
    const { evalRunId } = await createEvalRun(proj.projectRoot, proj.manifestId, proj.evalId);
    const outputsPath = await writeOutputsAcceptingAll(proj.projectRoot, proj.records);

    const { scorecard } = await scoreEvalRun(proj.projectRoot, evalRunId, outputsPath);

    // The bug this finding describes produces an EMPTY tasks object that
    // still reports 'pass' — assert we actually have populated task data,
    // not just a verdict string that happens to say the right thing.
    assert.ok(Object.keys(scorecard.tasks).length > 0, 'at least one task type must have been scored');
    assert.equal(Object.keys(scorecard.tasks).length, 4, 'all four task types resolved from a real eval pack');

    assert.equal(scorecard.tasks.lane_coverage.total, 4);
    assert.equal(scorecard.tasks.lane_coverage.covered, 4);
    assert.equal(scorecard.tasks.lane_coverage.passed, true);

    // anchor_gold is capped at maxPerFaction (3 by default) even though 4
    // records qualify — proves real candidate-selection logic ran, not a
    // stubbed/empty task list.
    assert.equal(scorecard.tasks.anchor_gold.total, 3);
    assert.equal(scorecard.tasks.anchor_gold.matched, 3);

    assert.equal(scorecard.tasks.subject_continuity.total_subjects, 1);
    assert.equal(scorecard.tasks.subject_continuity.subjects_with_coverage, 1);

    assert.equal(scorecard.overall_verdict, 'pass');
    assert.equal(scorecard.overall_score, 1);
    assert.equal(scorecard.output_count, 4);
    assert.equal(scorecard.accepted_count, 4);

    // Manifest + summary side effects still land correctly.
    const runManifest = await loadEvalRun(proj.projectRoot, evalRunId);
    assert.equal(runManifest.status, 'scored');
    assert.equal(runManifest.scorecard.overall_verdict, 'pass');

    const runs = await listEvalRuns(proj.projectRoot);
    assert.ok(runs.some(r => r.id === evalRunId && r.verdict === 'pass'));
  } finally {
    proj.cleanup();
  }
});

// ─── Missing-pack path: directory gone entirely ─────────────────────────

test('F2: scoreEvalRun throws EVAL_PACK_DIR_MISSING instead of a vacuous pass when the eval pack directory is gone — RED branch driven explicitly', async () => {
  const proj = await buildEvalRunFixture();
  try {
    const { evalRunId } = await createEvalRun(proj.projectRoot, proj.manifestId, proj.evalId);

    // Simulate the pack being deleted after the run was created —
    // createEvalRun stores only the id string, never a copy of the pack.
    await rm(join(proj.projectRoot, 'eval-packs', proj.evalId), { recursive: true, force: true });

    const outputsPath = await writeOutputsAcceptingAll(proj.projectRoot, proj.records);

    await assert.rejects(
      () => scoreEvalRun(proj.projectRoot, evalRunId, outputsPath),
      (err) => {
        assert.equal(err.code, 'EVAL_PACK_DIR_MISSING');
        assert.ok(err.message.includes(proj.evalId), `error message must name the missing pack: ${err.message}`);
        return true;
      },
    );

    // A failed scoring attempt must not silently flip the run to scored/pass.
    const runManifest = await loadEvalRun(proj.projectRoot, evalRunId);
    assert.equal(runManifest.status, 'created', 'run must still read as unscored after the throw');
    assert.equal(runManifest.scorecard, null);
  } finally {
    proj.cleanup();
  }
});

// ─── Missing-pack path, variant B: dir survives, every task file gone ───

test('F2: scoreEvalRun throws EVAL_PACK_NO_TASK_FILES when the pack directory exists but every task file is gone', async () => {
  const proj = await buildEvalRunFixture();
  try {
    const { evalRunId } = await createEvalRun(proj.projectRoot, proj.manifestId, proj.evalId);

    // The directory-existence check alone cannot see this shape — the
    // directory is still there, but every individual task file underneath
    // it is gone. This is the "belt-and-suspenders" second guard.
    const packDir = join(proj.projectRoot, 'eval-packs', proj.evalId);
    for (const fileName of TASK_FILE_NAMES) {
      await rm(join(packDir, fileName), { force: true });
    }

    const outputsPath = await writeOutputsAcceptingAll(proj.projectRoot, proj.records);

    await assert.rejects(
      () => scoreEvalRun(proj.projectRoot, evalRunId, outputsPath),
      (err) => {
        assert.equal(err.code, 'EVAL_PACK_NO_TASK_FILES');
        assert.ok(err.message.includes(proj.evalId));
        return true;
      },
    );
  } finally {
    proj.cleanup();
  }
});

test('F2: scoreEvalRun still succeeds when only SOME task files are missing (partial coverage is not the bug being guarded against)', async () => {
  const proj = await buildEvalRunFixture();
  try {
    const { evalRunId } = await createEvalRun(proj.projectRoot, proj.manifestId, proj.evalId);

    // Remove just one task file — the guard is specifically about ZERO
    // resolved task files, not partial coverage, which is pre-existing,
    // intentional, per-task behavior.
    const packDir = join(proj.projectRoot, 'eval-packs', proj.evalId);
    await rm(join(packDir, 'forbidden-drift.jsonl'), { force: true });

    const outputsPath = await writeOutputsAcceptingAll(proj.projectRoot, proj.records);
    const { scorecard } = await scoreEvalRun(proj.projectRoot, evalRunId, outputsPath);

    assert.equal(Object.keys(scorecard.tasks).length, 3, 'the three surviving task files must still be scored');
    assert.ok(!('forbidden_drift' in scorecard.tasks));
  } finally {
    proj.cleanup();
  }
});
