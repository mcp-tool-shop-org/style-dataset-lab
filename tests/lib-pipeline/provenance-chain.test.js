/**
 * Provenance-gate tests for Stage 0 Part A (§2 and §1.2 G4, G5, G6, G9, G14).
 *
 * Written test-first: one test per link in the chain
 *   image -> record (G5 owner + CC-BY-4.0) -> canon (G6 canon_sha + entry_sha256)
 *   -> model licence (G4 SPDX id + url + date_read) -> run manifest (G9 workflow sha)
 * plus G14 (portlight-ships configured as a real project, no held data).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, cp } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import {
  hashModelFile,
  buildPinning,
  resolveModelLicence,
  isClearedLicenceEntry,
  assertClearedPinningLicences,
} from '../../lib/run-manifest.js';
import { hasModelSha256, normalizeModelFamilyKey } from '../../lib/model-licences.js';
import { buildBaseRecord } from '../../lib/records.js';
import { buildGeneratedProvenance, resolveCanonLink } from '../../lib/generated-provenance.js';
import { reingestSelection } from '../../lib/reingest-selected.js';
import { reingestGenerated } from '../../lib/reingest.js';
import { verifyProvenanceChain, verifyRecordProvenance } from '../../lib/verify-chain.js';
import { runBuild } from '../../lib/canon-build/build.js';
import { REPO_ROOT } from '../../lib/paths.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, '..', '..', 'bin', 'sdlab.js');

function runCli(args, envOverrides = {}) {
  const res = spawnSync(process.execPath, [BIN, ...args], {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    env: { ...process.env, SDLAB_QUIET_FALLBACK: '1', ...envOverrides },
  });
  return { stdout: res.stdout || '', stderr: res.stderr || '', status: res.status };
}

/**
 * Build a complete, valid temporary project with a canon-build manifest,
 * a run manifest with cleared Apache-2.0 Qwen-Image pinning, a selection,
 * and a reingested record so each test can break exactly one link and
 * prove the provenance gate catches it.
 */
async function makeValidProvenanceProject() {
  const root = await mkdtemp(join(tmpdir(), 'sdl-prov-chain-'));
  const projectName = '__sdl_prov_test_proj__';
  const projectRoot = join(root, 'projects', projectName);
  const canonSha = 'a881cb5ba656e0618080d2269498fda7f36ac93a';
  const entryId = 'ships/brig';
  const entrySha256 = 'sha256:' + '11'.repeat(32);
  const runId = 'run_2026-11-05_001';
  const selectionId = 'selection_2026-11-05_001';

  await mkdir(join(projectRoot, 'canon-build', canonSha), { recursive: true });
  await writeFile(join(projectRoot, 'canon-build', 'CURRENT'), canonSha + '\n');
  await writeFile(
    join(projectRoot, 'canon-build', canonSha, 'manifest.json'),
    JSON.stringify({
      schema_version: '1.0',
      project_id: projectName,
      generated_from: canonSha,
      built_at: '2026-11-05T00:00:00.000Z',
      entity_counts: { ships: 1, total: 1 },
      dataset_row_count: 1,
      per_entity_hashes: {
        [entryId]: entrySha256,
      },
    }, null, 2),
  );

  const modelsDir = join(root, 'models');
  await mkdir(modelsDir, { recursive: true });
  await writeFile(join(modelsDir, 'qwen_image_fp8_e4m3fn.safetensors'), 'fake-unet-weights');
  await writeFile(join(modelsDir, 'qwen_2.5_vl_7b_fp8_scaled.safetensors'), 'fake-clip-weights');
  await writeFile(join(modelsDir, 'qwen_image_vae.safetensors'), 'fake-vae-weights');

  const sampleGraph = {
    37: { class_type: 'UNETLoader', inputs: { unet_name: 'qwen_image_fp8_e4m3fn.safetensors', weight_dtype: 'default' } },
    38: { class_type: 'CLIPLoader', inputs: { clip_name: 'qwen_2.5_vl_7b_fp8_scaled.safetensors', type: 'qwen_image' } },
    39: { class_type: 'VAELoader', inputs: { vae_name: 'qwen_image_vae.safetensors' } },
    3: { class_type: 'KSampler', inputs: { seed: 1001, steps: 22, cfg: 3.5, sampler_name: 'euler', scheduler: 'simple', denoise: 1 } },
  };
  const pinning = buildPinning({
    graph: sampleGraph,
    models: {
      unet: 'qwen_image_fp8_e4m3fn.safetensors',
      clip: 'qwen_2.5_vl_7b_fp8_scaled.safetensors',
      vae: 'qwen_image_vae.safetensors',
    },
    loras: [],
    seedPolicy: 'explicit-per-item',
    modelsDir,
    hashModels: true,
  });

  await mkdir(join(projectRoot, 'runs', runId), { recursive: true });
  await writeFile(
    join(projectRoot, 'runs', runId, 'manifest.json'),
    JSON.stringify({
      schema_version: '2.3.0',
      run_id: runId,
      brief_id: 'brief_brig_01',
      workflow_template_id: 'damage_state_plate',
      canon_sha: canonSha,
      entry_id: entryId,
      entry_sha256: entrySha256,
      created_at: '2026-11-05T00:00:00.000Z',
      pinning,
      outputs: [{ filename: 'sel_001.png', seed: 1001, prompt: 'Portlight brig in profile' }],
    }, null, 2),
  );

  const selectionDir = join(projectRoot, 'selections', selectionId);
  await mkdir(join(selectionDir, 'chosen'), { recursive: true });
  await writeFile(join(selectionDir, 'chosen', 'sel_001.png'), Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  await writeFile(
    join(selectionDir, 'manifest.json'),
    JSON.stringify({
      selection_id: selectionId,
      project_id: projectName,
      source_type: 'run',
      source_id: runId,
      workflow_id: 'damage_state_plate',
      canon_sha: canonSha,
      created_at: '2026-11-05T00:00:00.000Z',
      items: [
        {
          slot_or_output: '001.png',
          filename: 'sel_001.png',
          seed: 1001,
          entry_id: entryId,
          prompt: 'Portlight brig in profile',
          reason: 'approved silhouette',
          tags: ['ship', 'brig'],
        },
      ],
      reingest_ready: true,
    }, null, 2),
  );

  await reingestSelection({
    projectRoot,
    projectId: projectName,
    selectionId,
    dryRun: false,
  });

  const recordId = `gen_${selectionId}_001`;
  const recordPath = join(projectRoot, 'records', `${recordId}.json`);

  return {
    root,
    projectName,
    projectRoot,
    canonSha,
    entryId,
    entrySha256,
    runId,
    selectionId,
    recordId,
    recordPath,
    cleanup: () => rm(root, { recursive: true, force: true }),
  };
}

// ─── G4: Model licences in run manifest and records ─────────────────

test('G4: hashModelFile and buildPinning attach licence_id, licence_url, and date_read for cleared models and flag excluded models', () => {
  const qwenUnet = hashModelFile('qwen_image_fp8_e4m3fn.safetensors', {
    kind: 'unet',
    modelsDir: '/nonexistent',
    doHash: false,
  });
  assert.equal(qwenUnet.licence_id, 'Apache-2.0');
  assert.equal(qwenUnet.licence_url, 'https://github.com/QwenLM/Qwen-Image/blob/main/LICENSE');
  assert.equal(qwenUnet.date_read, '2026-10-25');
  assert.equal(qwenUnet.licence?.spdx_id, 'Apache-2.0');
  assert.equal(qwenUnet.licence?.cc_by_4_eligible, true);

  const klein = hashModelFile('flux-2-klein-4b.safetensors', {
    kind: 'unet',
    modelsDir: '/nonexistent',
    doHash: false,
  });
  assert.equal(klein.licence_id, 'Apache-2.0');
  assert.match(klein.licence_url, /FLUX\.2-klein-4B/);
  assert.equal(klein.date_read, '2026-10-25');

  const customLora = resolveModelLicence('studio_hull_v1.safetensors', null, {
    'studio_hull_v1.safetensors': {
      spdx_id: 'CC-BY-4.0',
      url: 'https://github.com/mcp-tool-shop-org/style-dataset-lab/blob/main/LICENSE',
      verified_at: '2026-11-05',
    },
  });
  assert.equal(customLora.cc_by_4_eligible, true);
  assert.equal(
    isClearedLicenceEntry({
      name: 'studio_hull_v1.safetensors',
      sha256: 'sha256:' + 'cc'.repeat(32),
      ...customLora,
      licence: customLora,
    }),
    true,
  );
  assert.equal(
    isClearedLicenceEntry({
      name: 'studio_hull_v1.safetensors',
      sha256: null,
      ...customLora,
      licence: customLora,
    }),
    false,
  );
  assert.equal(isClearedLicenceEntry(null), false);

  const excludedPin = buildPinning({
    graph: null,
    models: { checkpoint: 'flux1-dev.safetensors' },
    loras: [],
    seedPolicy: 'fixed',
    modelsDir: '/nonexistent',
    doHash: false,
  });
  assert.equal(excludedPin.cc_by_4_eligible, false);
  assert.equal(excludedPin.models.checkpoint.licence?.cc_by_4_eligible, false);
  assert.equal(excludedPin.models.checkpoint.licence?.excluded, true);

  // allowUnlicensedResearch permits the research call while marking cc_by_4_eligible: false
  assert.doesNotThrow(() =>
    assertClearedPinningLicences(excludedPin.models, excludedPin.loras, { allowUnlicensedResearch: true }),
  );

  assert.throws(
    () =>
      buildPinning({
        graph: null,
        models: { checkpoint: 'flux1-dev.safetensors' },
        loras: [],
        seedPolicy: 'fixed',
        modelsDir: '/nonexistent',
        doHash: false,
        enforceLicence: true,
      }),
    (err) => err.code === 'MODEL_LICENCE_REJECTED',
  );
});

// ─── G5: Owner and CC-BY-4.0 licence stamp on records ───────────────

test('G5: buildBaseRecord, buildGeneratedProvenance, and reingestSelection stamp owner="mcp-tool-shop" and licence="CC-BY-4.0"', async () => {
  const base = buildBaseRecord({
    id: 'rec_1',
    project: 'portlight-ships',
    assetPath: 'outputs/candidates/rec_1.png',
    lane: 'damage-state-plate',
    dimensions: { width: 1024, height: 1024 },
  });
  assert.equal(base.owner, 'mcp-tool-shop');
  assert.equal(base.licence, 'CC-BY-4.0');
  assert.equal(base.rights?.owner, 'mcp-tool-shop');
  assert.equal(base.rights?.licence, 'CC-BY-4.0');
  assert.equal(base.rights?.ai_assisted_disclosure, true);

  const prov = buildGeneratedProvenance({
    sourceType: 'run',
    sourceId: 'run_1',
    runManifest: { run_id: 'run_1', brief_id: 'brief_1', workflow_template_id: 'wf_1', created_at: '2026-11-05T00:00:00Z' },
    item: { filename: '001.png', seed: 1001, prompt_sha256: 'sha256:' + 'aa'.repeat(32) },
    projectRoot: '/nonexistent',
  });
  assert.equal(prov.owner, 'mcp-tool-shop');
  assert.equal(prov.licence, 'CC-BY-4.0');
  assert.equal(prov.prompt_sha256, 'sha256:' + 'aa'.repeat(32));

  const fx = await makeValidProvenanceProject();
  try {
    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    assert.equal(rec.owner, 'mcp-tool-shop');
    assert.equal(rec.licence, 'CC-BY-4.0');
    assert.equal(rec.rights?.owner, 'mcp-tool-shop');
    assert.equal(rec.rights?.licence, 'CC-BY-4.0');
    assert.equal(rec.rights?.ai_assisted_disclosure, true);
  } finally {
    await fx.cleanup();
  }
});

// ─── G6: Canon entry sha and build's canon_sha on generated records ─

test('G6: reingestSelection, resolveCanonLink, and reingestGenerated stamp canon_sha, entry_id, and entry_sha256 from canon-build manifest', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    assert.equal(rec.canon?.canon_sha, fx.canonSha);
    assert.equal(rec.canon?.entry_id, fx.entryId);
    assert.equal(rec.canon?.entry_sha256, fx.entrySha256);
    assert.equal(rec.generation_provenance?.canon_sha, fx.canonSha);
    assert.equal(rec.generation_provenance?.entry_id, fx.entryId);
    assert.equal(rec.generation_provenance?.entry_sha256, fx.entrySha256);

    // Suffix resolution via CURRENT pointer ('brig' -> 'ships/brig')
    const suffixLink = resolveCanonLink(fx.projectRoot, { entryId: 'brig' });
    assert.equal(suffixLink?.canon_sha, fx.canonSha);
    assert.equal(suffixLink?.entry_id, 'ships/brig');
    assert.equal(suffixLink?.entry_sha256, fx.entrySha256);

    // Single-entity fallback when entryId omitted
    const singleLink = resolveCanonLink(fx.projectRoot, {});
    assert.equal(singleLink?.entry_id, 'ships/brig');

    // reingestGenerated stamps owner, licence, canon, and base_model licence
    const manifestId = 'tm_test_001';
    await mkdir(join(fx.projectRoot, 'training', 'manifests'), { recursive: true });
    await writeFile(
      join(fx.projectRoot, 'training', 'manifests', `${manifestId}.json`),
      JSON.stringify({
        manifest_id: manifestId,
        training_profile_id: 'qwen_lora',
        adapter_target: 'ai-toolkit',
        base_model: 'qwen_image_fp8_e4m3fn.safetensors',
        source_export_id: 'exp_001',
      }),
    );
    const genSrcDir = join(fx.root, 'gen-src');
    await mkdir(genSrcDir, { recursive: true });
    await writeFile(join(genSrcDir, 'brig.png'), Buffer.from([1, 2, 3, 4]));

    const rg = await reingestGenerated(fx.projectRoot, genSrcDir, manifestId);
    assert.equal(rg.created, 1);
    const rgRec = JSON.parse(await readFile(join(fx.projectRoot, 'records', 'gen_brig.json'), 'utf-8'));
    assert.equal(rgRec.owner, 'mcp-tool-shop');
    assert.equal(rgRec.licence, 'CC-BY-4.0');
    assert.equal(rgRec.canon?.canon_sha, fx.canonSha);
    assert.equal(rgRec.canon?.entry_id, 'ships/brig');
    assert.equal(rgRec.provenance?.licence_id, 'Apache-2.0');
  } finally {
    await fx.cleanup();
  }
});

// ─── G9: Provenance chain verification (one test per broken link) ───

test('G9-pass: verifyProvenanceChain passes when all links (record -> canon -> model licence -> run manifest) are intact', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const report = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report.ok, true, `expected ok:true, got failures: ${JSON.stringify(report.failures)}`);
    assert.equal(report.records_checked, 1);
    assert.equal(report.failures.length, 0);

    // Scoped by recordId
    const singleReport = await verifyProvenanceChain(fx.projectRoot, { recordId: fx.recordId });
    assert.equal(singleReport.ok, true);

    // Missing recordId fails with RECORD_NOT_FOUND
    const missingRec = await verifyProvenanceChain(fx.projectRoot, { recordId: 'nonexistent_rec' });
    assert.equal(missingRec.ok, false);
    assert.equal(missingRec.failures[0].code, 'RECORD_NOT_FOUND');

    // Scoped by snapshotId
    const snapId = 'snap_001';
    await mkdir(join(fx.projectRoot, 'snapshots', snapId), { recursive: true });
    await writeFile(
      join(fx.projectRoot, 'snapshots', snapId, 'included.jsonl'),
      JSON.stringify({ record_id: fx.recordId }) + '\n',
    );
    const snapReport = await verifyProvenanceChain(fx.projectRoot, { snapshotId: snapId });
    assert.equal(snapReport.ok, true);

    // Missing snapshotId fails with SNAPSHOT_NOT_FOUND
    const missingSnap = await verifyProvenanceChain(fx.projectRoot, { snapshotId: 'missing_snap' });
    assert.equal(missingSnap.ok, false);
    assert.equal(missingSnap.failures[0].code, 'SNAPSHOT_NOT_FOUND');

    // Snapshot referencing a missing record fails with RECORD_NOT_FOUND
    await writeFile(
      join(fx.projectRoot, 'snapshots', snapId, 'included.jsonl'),
      JSON.stringify({ record_id: 'deleted_rec' }) + '\n',
    );
    const snapMissingRec = await verifyProvenanceChain(fx.projectRoot, { snapshotId: snapId });
    assert.equal(snapMissingRec.ok, false);
    assert.equal(snapMissingRec.failures[0].code, 'RECORD_NOT_FOUND');

    // Empty project fails with NO_RECORDS_IN_SCOPE unless allowEmpty:true
    const emptyDir = join(fx.root, 'empty-proj');
    await mkdir(emptyDir, { recursive: true });
    const emptyFail = await verifyProvenanceChain(emptyDir);
    assert.equal(emptyFail.ok, false);
    assert.equal(emptyFail.failures[0].code, 'NO_RECORDS_IN_SCOPE');
    const emptyOk = await verifyProvenanceChain(emptyDir, { allowEmpty: true });
    assert.equal(emptyOk.ok, true);
  } finally {
    await fx.cleanup();
  }
});

test('G9-link1 (G5 break): verifyProvenanceChain fails with MISSING_OWNER_OR_LICENCE when owner or CC-BY-4.0 is stripped', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    delete rec.owner;
    delete rec.rights;
    await writeFile(fx.recordPath, JSON.stringify(rec, null, 2));

    const report = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report.ok, false);
    assert.ok(
      report.failures.some((f) => f.code === 'MISSING_OWNER_OR_LICENCE'),
      `expected MISSING_OWNER_OR_LICENCE in ${JSON.stringify(report.failures)}`,
    );
  } finally {
    await fx.cleanup();
  }
});

test('G9-link2 (G6 break): verifyProvenanceChain fails with BROKEN_CANON_LINK when entry_sha256 disagrees with canon-build manifest', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    rec.canon.entry_sha256 = 'sha256:' + 'ff'.repeat(32);
    await writeFile(fx.recordPath, JSON.stringify(rec, null, 2));

    const report = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report.ok, false);
    assert.ok(
      report.failures.some((f) => f.code === 'BROKEN_CANON_LINK'),
      `expected BROKEN_CANON_LINK in ${JSON.stringify(report.failures)}`,
    );

    // Missing canon_sha / manifest also fails with BROKEN_CANON_LINK
    const missingCanonShaRes = verifyRecordProvenance(fx.projectRoot, { ...rec, canon: null, generation_provenance: {} });
    assert.equal(missingCanonShaRes.links.canon_link, 'fail');
    const missingManifestRes = verifyRecordProvenance(fx.projectRoot, {
      ...rec,
      canon: { canon_sha: 'deadbeef', entry_id: 'ships/brig', entry_sha256: 'sha256:00' },
    });
    assert.equal(missingManifestRes.links.canon_link, 'fail');
    const emptyPinRes = verifyRecordProvenance(fx.projectRoot, {
      ...rec,
      generation_provenance: { ...rec.generation_provenance, run_id: 'missing_run' },
      asset_path: 'inbox/generated/missing.png',
    });
    assert.equal(emptyPinRes.links.run_manifest_link, 'fail');
    assert.equal(emptyPinRes.links.model_licences, 'fail');
  } finally {
    await fx.cleanup();
  }
});

test('G9-link3 (G4 break): verifyProvenanceChain fails with UNLICENSED_OR_EXCLUDED_MODEL when run manifest uses an uncleared model or omits licence_url', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const runManifestPath = join(fx.projectRoot, 'runs', fx.runId, 'manifest.json');
    const runManifest = JSON.parse(await readFile(runManifestPath, 'utf-8'));
    runManifest.pinning.models.unet.licence_id = 'FLUX-1-DEV-NC';
    runManifest.pinning.models.unet.licence = {
      spdx_id: 'FLUX-1-DEV-NC',
      url: 'https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md',
      verified_at: '2026-10-25',
      cc_by_4_eligible: false,
      excluded: true,
    };
    await writeFile(runManifestPath, JSON.stringify(runManifest, null, 2));

    const report = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report.ok, false);
    assert.ok(
      report.failures.some((f) => f.code === 'UNLICENSED_OR_EXCLUDED_MODEL'),
      `expected UNLICENSED_OR_EXCLUDED_MODEL in ${JSON.stringify(report.failures)}`,
    );
  } finally {
    await fx.cleanup();
  }
});

test('G9-link3b (G4 model sha256 break): verifyProvenanceChain fails with MISSING_MODEL_SHA256 when a model or LoRA in pinning or generation_provenance.model_licences has no sha256', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const runManifestPath = join(fx.projectRoot, 'runs', fx.runId, 'manifest.json');
    const runManifest = JSON.parse(await readFile(runManifestPath, 'utf-8'));
    const origUnetSha = runManifest.pinning.models.unet.sha256;
    runManifest.pinning.models.unet.sha256 = null;
    await writeFile(runManifestPath, JSON.stringify(runManifest, null, 2));

    const report1 = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report1.ok, false);
    assert.ok(
      report1.failures.some((f) => f.code === 'MISSING_MODEL_SHA256'),
      `expected MISSING_MODEL_SHA256 in ${JSON.stringify(report1.failures)}`,
    );

    // Restore pinning sha256, break generation_provenance.model_licences.models.unet.sha256
    runManifest.pinning.models.unet.sha256 = origUnetSha;
    await writeFile(runManifestPath, JSON.stringify(runManifest, null, 2));

    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    rec.generation_provenance.model_licences.models.unet.sha256 = '';
    await writeFile(fx.recordPath, JSON.stringify(rec, null, 2));

    const report2 = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report2.ok, false);
    assert.ok(
      report2.failures.some((f) => f.code === 'MISSING_MODEL_SHA256'),
      `expected MISSING_MODEL_SHA256 for generation_provenance.model_licences in ${JSON.stringify(report2.failures)}`,
    );

    // LoRA without sha256 in pinning also fails with MISSING_MODEL_SHA256
    rec.generation_provenance.model_licences.models.unet.sha256 = origUnetSha;
    rec.generation_provenance.model_licences.loras = [
      {
        name: 'studio_hull_v1.safetensors',
        weight: 1.0,
        sha256: null,
        licence_id: 'CC-BY-4.0',
        licence_url: 'https://github.com/mcp-tool-shop-org/style-dataset-lab/blob/main/LICENSE',
        date_read: '2026-11-05',
      },
    ];
    await writeFile(fx.recordPath, JSON.stringify(rec, null, 2));
    runManifest.pinning.loras = [
      {
        name: 'studio_hull_v1.safetensors',
        weight: 1.0,
        sha256: null,
        licence_id: 'CC-BY-4.0',
        licence_url: 'https://github.com/mcp-tool-shop-org/style-dataset-lab/blob/main/LICENSE',
        date_read: '2026-11-05',
      },
    ];
    await writeFile(runManifestPath, JSON.stringify(runManifest, null, 2));

    const report3 = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report3.ok, false);
    assert.ok(
      report3.failures.some((f) => f.code === 'MISSING_MODEL_SHA256'),
      `expected MISSING_MODEL_SHA256 for LoRA without sha256 in ${JSON.stringify(report3.failures)}`,
    );
  } finally {
    await fx.cleanup();
  }
});

test('G9-link4 (run manifest break): verifyProvenanceChain fails with BROKEN_RUN_MANIFEST_LINK when comfy_workflow_sha mismatches', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const runManifestPath = join(fx.projectRoot, 'runs', fx.runId, 'manifest.json');
    const runManifest = JSON.parse(await readFile(runManifestPath, 'utf-8'));
    runManifest.pinning.comfy_workflow_sha = 'sha256:' + 'ab'.repeat(32);
    await writeFile(runManifestPath, JSON.stringify(runManifest, null, 2));

    const report = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report.ok, false);
    assert.ok(
      report.failures.some((f) => f.code === 'BROKEN_RUN_MANIFEST_LINK'),
      `expected BROKEN_RUN_MANIFEST_LINK in ${JSON.stringify(report.failures)}`,
    );
  } finally {
    await fx.cleanup();
  }
});

test('G9-link5 (quarantine break): verifyProvenanceChain fails with QUARANTINED_SOURCE_REFERENCED when held plsvessel LoRA is present', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    rec.generation_provenance.lora_ids = ['plsvessel_v1.safetensors'];
    await writeFile(fx.recordPath, JSON.stringify(rec, null, 2));

    const report = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report.ok, false);
    assert.ok(
      report.failures.some((f) => f.code === 'QUARANTINED_SOURCE_REFERENCED'),
      `expected QUARANTINED_SOURCE_REFERENCED in ${JSON.stringify(report.failures)}`,
    );
  } finally {
    await fx.cleanup();
  }
});

test('G9-link6 (verdict separation break): verifyProvenanceChain fails with INVALID_VERDICT_PROVENANCE when judge equals generator or shares Qwen family', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    rec.judgment = {
      status: 'approved',
      judged_by_model: 'qwen-image:qwen_image_fp8_e4m3fn',
      generator_model: 'qwen-image:qwen_image_fp8_e4m3fn',
    };
    await writeFile(fx.recordPath, JSON.stringify(rec, null, 2));

    const report = await verifyProvenanceChain(fx.projectRoot);
    assert.equal(report.ok, false);
    assert.ok(
      report.failures.some((f) => f.code === 'INVALID_VERDICT_PROVENANCE'),
      `expected INVALID_VERDICT_PROVENANCE in ${JSON.stringify(report.failures)}`,
    );

    // Same-family Qwen VLM judge (DESIGN-v3 §12.5) must also fail verdict_separation
    rec.judgment = {
      status: 'approved',
      judged_by_model: 'qwen3-vl-30b-a3b-instruct',
      generator_model: 'qwen-image:qwen_image_fp8_e4m3fn',
    };
    const sameFamilyRes = verifyRecordProvenance(fx.projectRoot, rec);
    assert.equal(sameFamilyRes.links.verdict_separation, 'fail');
    assert.ok(sameFamilyRes.failures.some((f) => f.code === 'INVALID_VERDICT_PROVENANCE'));

    // Distinct independent-family VLM judge passes verdict_separation
    rec.judgment = {
      status: 'approved',
      judged_by_model: 'gemma-4-31b-it',
      generator_model: 'qwen-image:qwen_image_fp8_e4m3fn',
    };
    const distinctRes = verifyRecordProvenance(fx.projectRoot, rec);
    assert.equal(distinctRes.links.verdict_separation, 'pass');

    assert.equal(hasModelSha256(null), false);
    assert.equal(hasModelSha256({ sha256: '' }), false);
    assert.equal(hasModelSha256({ sha256: 'sha256:' + '11'.repeat(32) }), true);
    assert.equal(normalizeModelFamilyKey(''), '');
    assert.equal(normalizeModelFamilyKey('   '), '');
    assert.equal(normalizeModelFamilyKey('human:director'), 'human');
    assert.equal(normalizeModelFamilyKey('rule-based:sdlab-critique-v1'), 'rule-based');
    assert.equal(normalizeModelFamilyKey('Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf'), 'family:muse-glimmer-30b');
    assert.equal(normalizeModelFamilyKey('qwen-image:qwen_image_fp8_e4m3fn'), 'family:qwen');
    assert.equal(normalizeModelFamilyKey('qwen3-vl-30b-a3b-instruct'), 'family:qwen');
    assert.equal(normalizeModelFamilyKey('gemma-4-31b-it'), 'family:gemma');
    assert.equal(normalizeModelFamilyKey('CapRL-InternVL3.5-8B'), 'family:internvl');
    assert.equal(normalizeModelFamilyKey('siglip2-so400m-patch14-384'), 'family:siglip2');
    assert.equal(normalizeModelFamilyKey('flux-2-klein-4b.safetensors'), 'family:flux');
    assert.equal(normalizeModelFamilyKey('sd3.5-large'), 'family:sd3');
    assert.equal(normalizeModelFamilyKey('sdxl:dreamshaperXL'), 'family:sdxl');
    assert.equal(normalizeModelFamilyKey('custom-verifier-v1'), 'custom-verifier-v1');
  } finally {
    await fx.cleanup();
  }
});

test('G9-cli: `sdlab verify` exits 0 on valid chain and exits non-zero when any link is broken', async () => {
  const fx = await makeValidProvenanceProject();
  try {
    const okRes = runCli(['verify', '--project', fx.projectName, '--json'], { SDLAB_ROOT: fx.root });
    assert.equal(okRes.status, 0, `expected exit 0, stderr: ${okRes.stderr}`);
    const parsed = JSON.parse(okRes.stdout);
    assert.equal(parsed.ok, true);

    // Human-readable output also exits 0
    const humanOk = runCli(['verify', '--project', fx.projectName], { SDLAB_ROOT: fx.root });
    assert.equal(humanOk.status, 0);
    assert.match(humanOk.stdout, /Provenance chain intact/);

    // Break canon link and re-run CLI -> must exit non-zero
    const rec = JSON.parse(await readFile(fx.recordPath, 'utf-8'));
    rec.canon.entry_sha256 = 'sha256:' + '00'.repeat(32);
    await writeFile(fx.recordPath, JSON.stringify(rec, null, 2));

    const failRes = runCli(['verify', '--project', fx.projectName], { SDLAB_ROOT: fx.root });
    assert.notEqual(failRes.status, 0, 'sdlab verify must exit non-zero on a broken link');
    assert.match(failRes.stderr + failRes.stdout, /BROKEN_CANON_LINK|PROVENANCE_VERIFY_FAILED/);
  } finally {
    await fx.cleanup();
  }
});

// ─── G14 + Part A: projects/portlight-ships has no invented canon and walks G9 offline ──

const TODO_CANON_MARKER = 'TODO-canon: import the Director-ratified Portlight canon (portlight-ships, 2026-07-25)';

test('G14: projects/portlight-ships keeps Apache-2.0 Qwen-Image project config, restores template files with TODO-canon marker, contains zero invented canon or held data, and walks G9 sdlab verify offline', async () => {
  const portlightDir = join(REPO_ROOT, 'projects', 'portlight-ships');
  const proj = JSON.parse(readFileSync(join(portlightDir, 'project.json'), 'utf-8'));

  assert.notEqual(proj.display_name, 'TEMPLATE', 'portlight-ships display_name must not be TEMPLATE');
  assert.equal(proj.display_name, 'Portlight Ships');
  assert.equal(proj.rights?.owner, 'mcp-tool-shop');
  assert.equal(proj.rights?.licence, 'CC-BY-4.0');
  assert.equal(proj.generation?.base, 'qwen-image');
  assert.equal(proj.generation?.unet, 'qwen_image_fp8_e4m3fn.safetensors');
  assert.equal(proj.generation?.clip, 'qwen_2.5_vl_7b_fp8_scaled.safetensors');
  assert.equal(proj.generation?.vae, 'qwen_image_vae.safetensors');
  assert.equal('checkpoint' in (proj.generation || {}), false, 'must not default to SDXL dreamshaper checkpoint');

  // Restored template files must carry the TODO-canon marker and zero builder-invented canon
  const templateFiles = [
    'README.md',
    'canon/constitution.md',
    'canon/review-rubric.md',
    'constitution.json',
    'rubric.json',
    'terminology.json',
    'inputs/prompts/example-wave.json',
  ];
  for (const rel of templateFiles) {
    const text = readFileSync(join(portlightDir, rel), 'utf-8');
    assert.ok(
      text.includes(TODO_CANON_MARKER),
      `${rel} must carry "${TODO_CANON_MARKER}" instead of builder-invented canon`,
    );
    assert.doesNotMatch(
      text,
      /Distinct Hull & Rig Silhouette|Cold-Coast Shipwrights|Sunward-Sea Yards|Crown Naval Dockyards|greeble_spam/i,
      `${rel} still contains builder-invented canon prose`,
    );
    assert.doesNotMatch(text, /plsvessel|nano[-_ ]banana/i, `${rel} must not reference held Portlight data`);
  }

  // Configuration files must have no invented creative prose or held data
  for (const rel of [
    'project.json',
    'lanes.json',
    'workflows/profiles/variant-pack.json',
    'workflows/profiles/vehicle-silhouette-pack.json',
  ]) {
    const text = readFileSync(join(portlightDir, rel), 'utf-8');
    assert.doesNotMatch(
      text,
      /age-of-sail|shipwright tradition|gunport|taffrail|maintruck/i,
      `${rel} must not contain invented creative prose`,
    );
    assert.doesNotMatch(text, /plsvessel|nano[-_ ]banana/i, `${rel} must not reference held Portlight data`);
  }

  // Verify lanes include damage-state-plate referenced by canon/ships/*.md
  const lanes = JSON.parse(readFileSync(join(portlightDir, 'lanes.json'), 'utf-8'));
  const laneIds = lanes.lanes.map((l) => l.id);
  assert.ok(laneIds.includes('damage-state-plate'), 'lanes.json must include damage-state-plate used by canon/ships/*.md');

  // Doctor + canon build --dry-run both exit 0
  const docRes = runCli(['project', 'doctor', '--project', 'portlight-ships']);
  assert.equal(docRes.status, 0, `doctor failed: ${docRes.stderr}\n${docRes.stdout}`);
  assert.match(docRes.stdout, /HEALTHY/);

  const buildRes = runCli(['canon', 'build', '--project', 'portlight-ships', '--dry-run']);
  assert.equal(buildRes.status, 0, `canon build --dry-run failed: ${buildRes.stderr}`);
  assert.match(buildRes.stdout, /14 entities/);

  // Part A.4: G9 `sdlab verify` walks the chain on a copy of portlight-ships offline
  const tmpRoot = await mkdtemp(join(tmpdir(), 'sdl-portlight-verify-'));
  try {
    const tmpProjectRoot = join(tmpRoot, 'projects', 'portlight-ships');
    await mkdir(join(tmpRoot, 'projects'), { recursive: true });
    await cp(portlightDir, tmpProjectRoot, { recursive: true });

    const buildSummary = await runBuild({ projectRoot: tmpProjectRoot });
    const currentSha = buildSummary.generated_from;
    const canonManifest = JSON.parse(
      await readFile(join(buildSummary.output_dir, 'manifest.json'), 'utf-8'),
    );
    const brigSha = canonManifest.per_entity_hashes['brig'] || canonManifest.per_entity_hashes['ships/brig'];
    assert.match(brigSha, /^(sha256:)?[0-9a-f]{64}$/);

    const modelsDir = join(tmpRoot, 'models');
    await mkdir(modelsDir, { recursive: true });
    await writeFile(join(modelsDir, proj.generation.unet), 'fake-unet-weights');
    await writeFile(join(modelsDir, proj.generation.clip), 'fake-clip-weights');
    await writeFile(join(modelsDir, proj.generation.vae), 'fake-vae-weights');

    const sampleGraph = {
      37: { class_type: 'UNETLoader', inputs: { unet_name: proj.generation.unet, weight_dtype: 'default' } },
      38: { class_type: 'CLIPLoader', inputs: { clip_name: proj.generation.clip, type: 'qwen_image' } },
      39: { class_type: 'VAELoader', inputs: { vae_name: proj.generation.vae } },
    };
    const pinning = buildPinning({
      graph: sampleGraph,
      models: {
        unet: proj.generation.unet,
        clip: proj.generation.clip,
        vae: proj.generation.vae,
      },
      loras: [],
      seedPolicy: 'explicit-per-item',
      modelsDir,
      hashModels: true,
    });

    const runId = 'run_2026-11-05_001';
    const selectionId = 'selection_2026-11-05_001';
    await mkdir(join(tmpProjectRoot, 'runs', runId), { recursive: true });
    await writeFile(
      join(tmpProjectRoot, 'runs', runId, 'manifest.json'),
      JSON.stringify({
        schema_version: '2.3.0',
        run_id: runId,
        brief_id: 'brief_brig_01',
        workflow_template_id: 'damage_state_plate',
        canon_sha: currentSha,
        entry_id: 'ships/brig',
        entry_sha256: brigSha,
        created_at: '2026-11-05T00:00:00.000Z',
        pinning,
        outputs: [{ filename: 'sel_001.png', seed: 1001, prompt: 'brig plate' }],
      }, null, 2),
    );

    const selectionDir = join(tmpProjectRoot, 'selections', selectionId);
    await mkdir(join(selectionDir, 'chosen'), { recursive: true });
    await writeFile(join(selectionDir, 'chosen', 'sel_001.png'), Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
    await writeFile(
      join(selectionDir, 'manifest.json'),
      JSON.stringify({
        selection_id: selectionId,
        project_id: 'portlight-ships',
        source_type: 'run',
        source_id: runId,
        workflow_id: 'damage_state_plate',
        canon_sha: currentSha,
        created_at: '2026-11-05T00:00:00.000Z',
        items: [
          {
            slot_or_output: '001.png',
            filename: 'sel_001.png',
            seed: 1001,
            entry_id: 'ships/brig',
            prompt: 'brig plate',
            reason: 'approved silhouette',
            tags: ['ship', 'brig'],
          },
        ],
        reingest_ready: true,
      }, null, 2),
    );

    await reingestSelection({
      projectRoot: tmpProjectRoot,
      projectId: 'portlight-ships',
      selectionId,
      dryRun: false,
    });

    const verifyRes = runCli(['verify', '--project', 'portlight-ships', '--json'], { SDLAB_ROOT: tmpRoot });
    assert.equal(verifyRes.status, 0, `sdlab verify failed on portlight-ships: ${verifyRes.stderr}\n${verifyRes.stdout}`);
    const verifyReport = JSON.parse(verifyRes.stdout);
    assert.equal(verifyReport.ok, true);
    assert.equal(verifyReport.records_checked, 1);
  } finally {
    await rm(tmpRoot, { recursive: true, force: true });
  }
});
