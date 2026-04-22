/**
 * Stage C humanization amends — schema stamping, graceful parse degradation,
 * export failure accounting, split balance deviation, eval-pack coverage,
 * eval-run failure drill-down.
 *
 * Covers: DB-001, DB-002, DB-003, DB-005, DB-006, DB-008, DB-014.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createSnapshot, loadSnapshot, SCHEMA_VERSION } from '../../lib/snapshot.js';
import { createSplit, loadSplit } from '../../lib/split.js';
import { buildExport, loadExport } from '../../lib/export.js';
import { buildEvalPack, loadEvalPack } from '../../lib/eval-pack.js';
import { createEvalRun, scoreEvalRun } from '../../lib/eval-runs.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

const SELECTION_PROFILE = {
  profile_id: 'humanization-test',
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
};

const SPLIT_PROFILE = {
  profile_id: 'humanization-split',
  seed: 42,
  train_ratio: 0.6,
  val_ratio: 0.2,
  test_ratio: 0.2,
};

test('DB-001/DB-006: snapshot manifest is stamped with SCHEMA_VERSION', async () => {
  const proj = createTmpProject({
    records: [makeRecord({ id: 'r1' }), makeRecord({ id: 'r2' })],
  });
  try {
    const { snapshotId } = await createSnapshot(proj.projectRoot, SELECTION_PROFILE);
    const manifest = await loadSnapshot(proj.projectRoot, snapshotId);
    assert.equal(manifest.schema_version, SCHEMA_VERSION);
    assert.equal(SCHEMA_VERSION, '2.2.0');
  } finally {
    proj.cleanup();
  }
});

test('DB-003: one malformed record JSON does not abort snapshot', async () => {
  const proj = createTmpProject({
    records: [makeRecord({ id: 'good1' }), makeRecord({ id: 'good2' })],
  });
  try {
    // Drop a deliberately broken JSON into records/
    writeFileSync(join(proj.projectRoot, 'records', 'bad1.json'), '{ this is not valid json ');

    const result = await createSnapshot(proj.projectRoot, SELECTION_PROFILE);
    // Snapshot must still complete
    assert.ok(result.snapshotId, 'snapshot should be created despite bad record');
    const manifest = await loadSnapshot(proj.projectRoot, result.snapshotId);
    assert.equal(manifest.counts.unreadable, 1);
    assert.ok(Array.isArray(manifest.errors));
    assert.equal(manifest.errors.length, 1);
    assert.equal(manifest.errors[0].file, 'bad1.json');
    assert.ok(manifest.errors[0].error, 'error message captured');
    // Good records still evaluated
    assert.ok(manifest.counts.included >= 2, 'good records included');
  } finally {
    proj.cleanup();
  }
});

test('DB-002: export reports expected vs actual vs failed when sources are missing', async () => {
  const proj = createTmpProject({
    records: [
      makeRecord({ id: 'r1', assetPath: 'inputs/r1.png' }),
      makeRecord({ id: 'r2', assetPath: 'inputs/r2.png' }),
    ],
  });
  try {
    // Neither image actually exists on disk — exercise source_missing path.
    const { snapshotId } = await createSnapshot(proj.projectRoot, SELECTION_PROFILE);
    const { splitId } = await createSplit(proj.projectRoot, snapshotId, SPLIT_PROFILE);

    // Write a minimal export profile that includes images
    const exportProfilesDir = join(proj.projectRoot, 'export-profiles');
    await mkdir(exportProfilesDir, { recursive: true });
    await writeFile(join(exportProfilesDir, 'default.json'), JSON.stringify({
      profile_id: 'default',
      metadata_fields: ['id', 'asset_path'],
      include_images: true,
      include_splits: false,
      include_card: false,
      include_checksums: false,
    }));

    const { exportId } = await buildExport(proj.projectRoot, snapshotId, splitId, { copy: true });
    const manifest = await loadExport(proj.projectRoot, exportId);

    assert.equal(manifest.schema_version, SCHEMA_VERSION, 'DB-001: export stamped');
    assert.equal(manifest.counts.images_expected, 2, 'expected tracks attempts');
    assert.equal(manifest.counts.images_actual, 0, 'actual reflects placement');
    assert.equal(manifest.counts.images_failed, 2, 'failures counted');
    assert.ok(Array.isArray(manifest.images_failed));
    assert.equal(manifest.images_failed.length, 2);
    // Each failed entry carries a reason so operators can triage.
    for (const f of manifest.images_failed) {
      assert.ok(f.record_id);
      assert.ok(f.reason);
    }
    // Warning surfaces in the manifest.
    assert.ok(manifest.warnings.some(w => w.includes('failed to place')));
  } finally {
    proj.cleanup();
  }
});

test('DB-005: split audit reports deviation-from-profile per lane + overall score', async () => {
  const records = [];
  // Mostly concept lane → heavily imbalanced vs 60/20/20 profile
  for (let i = 0; i < 10; i++) {
    records.push(makeRecord({ id: `concept_${i}`, lane: 'concept' }));
  }
  const proj = createTmpProject({ records });
  try {
    const { snapshotId } = await createSnapshot(proj.projectRoot, SELECTION_PROFILE);
    const { splitId } = await createSplit(proj.projectRoot, snapshotId, SPLIT_PROFILE);

    const auditPath = join(proj.projectRoot, 'splits', splitId, 'audit.json');
    const audit = JSON.parse(await readFile(auditPath, 'utf-8'));
    assert.ok(audit.lane_balance, 'lane_balance present');
    assert.ok(audit.lane_balance._summary, 'summary present');
    assert.ok(
      typeof audit.lane_balance._summary.overall_deviation_score === 'number',
      'overall_deviation_score is numeric',
    );
    assert.ok(audit.lane_balance._summary.target_ratios_pct, 'target ratios echoed');
    // Each lane should carry deviation_from_target
    for (const lane of Object.keys(audit.lane_balance)) {
      if (lane === '_summary') continue;
      assert.ok(audit.lane_balance[lane].deviation_from_target, `lane ${lane} has deviation`);
      assert.ok(
        typeof audit.lane_balance[lane].deviation_from_target.total === 'number',
      );
    }
    // Split manifest is schema-stamped too
    const split = await loadSplit(proj.projectRoot, splitId);
    assert.equal(split.schema_version, SCHEMA_VERSION);
  } finally {
    proj.cleanup();
  }
});

test('DB-014: eval pack manifest reports records_sampled and records_available', async () => {
  const records = [];
  for (let i = 0; i < 8; i++) {
    records.push(makeRecord({ id: `concept_${i}`, lane: 'concept' }));
  }
  for (let i = 0; i < 4; i++) {
    records.push(makeRecord({ id: `portrait_${i}`, lane: 'portrait' }));
  }
  const proj = createTmpProject({ records });
  try {
    const { evalId } = await buildEvalPack(proj.projectRoot, { maxPerLane: 2 });
    const manifest = await loadEvalPack(proj.projectRoot, evalId);
    assert.equal(manifest.schema_version, SCHEMA_VERSION, 'eval pack stamped');
    assert.ok(manifest.records_sampled, 'records_sampled present');
    assert.ok(manifest.records_available, 'records_available present');
    assert.equal(typeof manifest.records_sampled.lane_coverage, 'number');
    assert.equal(typeof manifest.records_available.lane_coverage, 'number');
    // With maxPerLane=2 and >2 records per lane, available must exceed sampled.
    assert.ok(
      manifest.records_available.lane_coverage >= manifest.records_sampled.lane_coverage,
      'available >= sampled',
    );
    assert.ok(manifest.caps, 'cap values echoed');
    assert.equal(manifest.caps.max_per_lane, 2);
  } finally {
    proj.cleanup();
  }
});

test('DB-008: eval-run scorecard includes sample record_ids per failure bucket', async () => {
  const records = [
    makeRecord({ id: 'approved_1' }),
    makeRecord({ id: 'approved_2' }),
    // Rejected records enter forbidden-drift eval task
    {
      ...makeRecord({ id: 'rejected_1' }),
      judgment: { status: 'rejected', failure_modes: ['wrong_species'], explanation: 'off-canon' },
    },
    {
      ...makeRecord({ id: 'rejected_2' }),
      judgment: { status: 'rejected', failure_modes: ['wrong_palette'], explanation: 'bad' },
    },
  ];
  const proj = createTmpProject({ records });
  try {
    // Build an eval pack (includes a forbidden-drift task for the rejected records).
    const { evalId } = await buildEvalPack(proj.projectRoot, {});

    // Build the training manifest chain so createEvalRun can link.
    const { snapshotId } = await createSnapshot(proj.projectRoot, SELECTION_PROFILE);
    const { splitId } = await createSplit(proj.projectRoot, snapshotId, SPLIT_PROFILE);

    // Minimal export profile
    const exportProfilesDir = join(proj.projectRoot, 'export-profiles');
    await mkdir(exportProfilesDir, { recursive: true });
    await writeFile(join(exportProfilesDir, 'default.json'), JSON.stringify({
      profile_id: 'default',
      metadata_fields: ['id'],
      include_images: false,
      include_splits: false,
      include_card: false,
      include_checksums: false,
    }));
    const { exportId } = await buildExport(proj.projectRoot, snapshotId, splitId, { copy: true });

    // Training profile
    const tpDir = join(proj.projectRoot, 'training', 'profiles');
    await mkdir(tpDir, { recursive: true });
    await writeFile(join(tpDir, 'tp1.json'), JSON.stringify({
      profile_id: 'tp1',
      label: 'test',
      asset_type: 'concept',
      target_family: 'sdxl',
      adapter_targets: ['generic-image-caption'],
      eligible_lanes: [],
      caption_strategy: 'filename',
    }));

    const { createTrainingManifest } = await import('../../lib/training-manifests.js');
    const { manifestId } = await createTrainingManifest(proj.projectRoot, exportId, 'tp1', {});

    const { evalRunId } = await createEvalRun(proj.projectRoot, manifestId, evalId);

    // Outputs that FALSELY ACCEPT the rejected records — triggers false_acceptances.
    const outputsPath = join(proj.projectRoot, 'outputs.jsonl');
    await writeFile(outputsPath, [
      { record_id: 'rejected_1', accept: true },
      { record_id: 'rejected_2', accept: true },
    ].map(o => JSON.stringify(o)).join('\n') + '\n');

    const { scorecard } = await scoreEvalRun(proj.projectRoot, evalRunId, outputsPath);
    assert.ok(scorecard.tasks.forbidden_drift, 'forbidden_drift scored');
    const fd = scorecard.tasks.forbidden_drift;
    assert.ok(fd.false_acceptances >= 2, 'both false acceptances counted');
    assert.ok(
      Array.isArray(fd.false_acceptance_sample_record_ids),
      'sample ids array present',
    );
    assert.ok(fd.false_acceptance_sample_record_ids.length >= 1, 'at least one sample id');
    assert.ok(
      fd.false_acceptance_sample_record_ids.includes('rejected_1') ||
        fd.false_acceptance_sample_record_ids.includes('rejected_2'),
      'sample ids name actual failing records',
    );
  } finally {
    proj.cleanup();
  }
});
