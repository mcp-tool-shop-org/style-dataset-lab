/**
 * lib/asset-ingest.js — registration of a validated asset export.
 *
 * Held to the same non-negotiables as lib/ingest.js (never invents a
 * judgment or caption; honest provenance source; dry-run purity;
 * idempotency; crash-safety) PLUS the asset lane's own: acceptance rides
 * verbatim, every file is hashed, per-render gate failures reject loudly,
 * the receipt lands last and lists everything written.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rmSync, writeFileSync, existsSync, readFileSync, unlinkSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ingestAssetSource, RECEIPT_FILENAME } from '../../lib/asset-ingest.js';
import { writeDegenerateAsset } from './fixtures/make-asset.js';
import { createTmpProject } from '../lib-dataset/fixtures/make-project.js';

const HEX64 = /^[0-9a-f]{64}$/;

function readJson(p) {
  return JSON.parse(readFileSync(p, 'utf-8'));
}

test('end to end: a degenerate asset registers as uncurated records with honest provenance, hashes, gates and shares', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({ withNpy: true });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    assert.equal(report.alreadyIngested, false);
    assert.deepEqual(report.created.sort(), ['test_totem__r0', 'test_totem__r180']);
    assert.deepEqual(report.rejected, []);

    const record = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json'));
    // Non-negotiables: uncurated, nothing invented.
    assert.equal(record.judgment, null);
    assert.equal(record.canon, null);
    assert.equal('caption' in record, false, 'no caption is ever synthesized');
    // Honest provenance.
    const prov = record.provenance;
    assert.equal(prov.source, 'asset');
    assert.equal(prov.asset_id, 'test_totem');
    assert.match(prov.manifest_sha256, HEX64);
    assert.deepEqual(prov.acceptance, {
      gate: 'gate-1', verdict: 'accepted', date: '2026-08-04',
      record: 'test://acceptance/totem-1', by: 'director',
    }, 'the acceptance block rides verbatim');
    assert.deepEqual(prov.camera, { yaw_deg: 0, elevation_deg: 0 });
    assert.equal(prov.facing, 'front');
    assert.equal(prov.generation_provenance_known, true);
    assert.match(prov.silhouette_mask.sha256, HEX64);
    assert.match(prov.channels.matclass.sha256, HEX64);
    assert.equal(prov.caption_fields.subject, 'a test totem');
    assert.equal(prov.caption_fields.domain_tag, '3d asset');
    assert.equal(prov.caption_fields.facing, 'front');
    // Pair linkage is lossless where declared, absent where not (Q5).
    assert.match(prov.pair.clay.sha256, HEX64);
    const r180 = readJson(join(proj.projectRoot, 'records', 'test_totem__r180.json'));
    assert.equal('pair' in r180.provenance, false);
    assert.equal(r180.provenance.facing, 'back');
    // Receiving-dock measurements, on their own key (survives `sdlab measure`).
    assert.equal(record.asset_measurements.palette_gate.pass, true);
    assert.equal(record.asset_measurements.palette_gate.offpalette_px, 0);
    const shares = record.asset_measurements.class_shares.matclass;
    assert.ok(shares.figure_px > 0);
    assert.ok(shares.classes.class_a.px > shares.classes.class_b.px, 'class A covers most of the totem figure');
    assert.equal(shares.unclassified.px, 0, 'a nearest-filtered exact channel classifies fully');
    // Image truth.
    assert.equal(record.image.width, 12);
    assert.equal(record.image.height, 12);
    assert.ok(record.image.bytes > 0);

    // Materialized files + receipt.
    assert.ok(existsSync(join(proj.projectRoot, 'outputs', 'candidates', 'test_totem__r0.png')));
    const assetDir = join(proj.projectRoot, 'assets', 'test_totem');
    assert.ok(existsSync(join(assetDir, 'asset-source.json')));
    const manifestCopy = readFileSync(join(assetDir, 'asset-source.json'));
    const manifestSrc = readFileSync(join(dir, 'asset-source.json'));
    assert.ok(manifestCopy.equals(manifestSrc), 'manifest copy must be byte-identical');
    assert.ok(existsSync(join(assetDir, 'masks', 'r0.png')));
    assert.ok(existsSync(join(assetDir, 'channels', 'matclass__r0.png')));
    assert.ok(existsSync(join(assetDir, 'pairs', 'clay__r0.png')));

    const receipt = readJson(join(assetDir, RECEIPT_FILENAME));
    assert.equal(receipt.asset_id, 'test_totem');
    assert.match(receipt.manifest_sha256, HEX64);
    assert.deepEqual(receipt.records_created.sort(), ['test_totem__r0', 'test_totem__r180']);
    assert.ok(receipt.written.includes('records/test_totem__r0.json'));
    assert.ok(receipt.written.includes('outputs/candidates/test_totem__r0.png'));
    // Texture-space artifacts are hashed in place, not materialized.
    const zonesRow = receipt.files.find((f) => f.role === 'channel:zones');
    assert.equal(zonesRow.materialized, false);
    assert.match(zonesRow.sha256, HEX64);
    const npyRow = receipt.files.find((f) => f.role === 'channel:coverage');
    assert.equal(npyRow.materialized, false);
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('idempotent: a second run against the same manifest is a full no-op skip', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    await ingestAssetSource(proj.projectRoot, dir);
    const before = readFileSync(join(proj.projectRoot, 'records', 'test_totem__r0.json'), 'utf-8');

    const second = await ingestAssetSource(proj.projectRoot, dir);
    assert.equal(second.alreadyIngested, true);
    assert.deepEqual(second.created, []);
    assert.deepEqual(second.skipped.sort(), ['test_totem__r0', 'test_totem__r180']);

    const after = readFileSync(join(proj.projectRoot, 'records', 'test_totem__r0.json'), 'utf-8');
    assert.equal(after, before, 'records must be byte-identical after a no-op re-run');
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a CHANGED manifest for an already-ingested asset refuses — a new truth is not an overwrite', async () => {
  const proj = createTmpProject();
  const { dir, manifest } = writeDegenerateAsset();
  try {
    await ingestAssetSource(proj.projectRoot, dir);
    manifest.captions.subject = 'a different totem';
    writeFileSync(join(dir, 'asset-source.json'), JSON.stringify(manifest, null, 2) + '\n');

    await assert.rejects(
      () => ingestAssetSource(proj.projectRoot, dir),
      (err) => err.code === 'ASSET_ALREADY_INGESTED' && /Compensator/.test(err.hint),
    );
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('crash-resume: records without a receipt are skipped, then the receipt completes the ingest', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    await ingestAssetSource(proj.projectRoot, dir);
    // Simulate the crash window: records exist, receipt never landed.
    unlinkSync(join(proj.projectRoot, 'assets', 'test_totem', RECEIPT_FILENAME));

    const resumed = await ingestAssetSource(proj.projectRoot, dir);
    assert.equal(resumed.alreadyIngested, false);
    assert.deepEqual(resumed.created, [], 'no record is rewritten');
    assert.deepEqual(resumed.skipped.sort(), ['test_totem__r0', 'test_totem__r180']);
    assert.ok(existsSync(join(proj.projectRoot, 'assets', 'test_totem', RECEIPT_FILENAME)), 'the receipt now completes the ingest');
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a record-id collision with a foreign record refuses and writes nothing', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    writeFileSync(
      join(proj.projectRoot, 'records', 'test_totem__r0.json'),
      JSON.stringify({ id: 'test_totem__r0', provenance: { source: 'external' } }, null, 2),
    );
    await assert.rejects(
      () => ingestAssetSource(proj.projectRoot, dir),
      (err) => err.code === 'ASSET_RECORD_COLLISION',
    );
    assert.equal(existsSync(join(proj.projectRoot, 'assets', 'test_totem')), false, 'nothing was written');
    assert.equal(existsSync(join(proj.projectRoot, 'records', 'test_totem__r180.json')), false);
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('--dry-run validates, gates, and plans — and writes absolutely nothing', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir, { dryRun: true });
    assert.equal(report.dryRun, true);
    assert.deepEqual(report.created.sort(), ['test_totem__r0', 'test_totem__r180']);
    assert.ok(report.gates['test_totem__r0'].pass);
    assert.ok(report.wouldWrite.includes('assets/test_totem/ingest-receipt.json'));

    assert.equal(existsSync(join(proj.projectRoot, 'assets')), false, 'dry-run must not create assets/');
    assert.equal(existsSync(join(proj.projectRoot, 'outputs')), false, 'dry-run must not create outputs/');
    assert.equal(existsSync(join(proj.projectRoot, 'records', 'test_totem__r0.json')), false);
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('ANDON per render: a render failing the asset\'s own palette gate is rejected loudly, the rest register', async () => {
  const proj = createTmpProject();
  // Blue 6px blob on r0; tighten the blob gate below it via the mutator.
  const { dir } = writeDegenerateAsset({
    bluePatchOnR0: true,
    mutate: (m) => { m.palette.gate.max_offpalette_blob_px = 4; },
  });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    assert.deepEqual(report.created, ['test_totem__r180']);
    assert.equal(report.rejected.length, 1);
    assert.equal(report.rejected[0].render_id, 'r0');
    assert.equal(report.rejected[0].reason, 'palette-gate');
    assert.equal(report.rejected[0].gate.largest_blob_px, 6);
    assert.equal(existsSync(join(proj.projectRoot, 'records', 'test_totem__r0.json')), false, 'a rejected render never registers');

    const receipt = readJson(join(proj.projectRoot, 'assets', 'test_totem', RECEIPT_FILENAME));
    assert.equal(receipt.rejected_renders.length, 1, 'the rejection is on the receipt, not just in stdout');
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('every render failing the gate fails the whole ingest', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({
    bluePatchOnBoth: true,
    mutate: (m) => { m.palette.gate.max_offpalette_blob_px = 4; },
  });
  try {
    await assert.rejects(
      () => ingestAssetSource(proj.projectRoot, dir),
      (err) => err.code === 'ASSET_ALL_RENDERS_REJECTED',
    );
    assert.equal(existsSync(join(proj.projectRoot, 'assets')), false, 'nothing registers');
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a contract violation upstream means zero writes here (refusal happens before registration)', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({ mutate: (m) => { m.acceptance.verdict = 'pending'; } });
  try {
    await assert.rejects(
      () => ingestAssetSource(proj.projectRoot, dir),
      (err) => err.code === 'ASSET_NOT_ACCEPTED',
    );
    assert.equal(existsSync(join(proj.projectRoot, 'assets')), false);
    assert.equal(existsSync(join(proj.projectRoot, 'outputs')), false);
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('facing override in the manifest wins over the derived token', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({ mutate: (m) => { m.renders[0].facing = 'hero shot'; } });
  try {
    await ingestAssetSource(proj.projectRoot, dir);
    const record = JSON.parse(await readFile(join(proj.projectRoot, 'records', 'test_totem__r0.json'), 'utf-8'));
    assert.equal(record.provenance.facing, 'hero shot');
    assert.equal(record.provenance.caption_fields.facing, 'hero shot');
  } finally {
    proj.cleanup();
    rmSync(dir, { recursive: true, force: true });
  }
});
