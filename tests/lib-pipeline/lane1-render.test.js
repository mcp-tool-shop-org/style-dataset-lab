/**
 * Part B — Lane 1 (render) kit tests (§3.1, §3.5, §4.4, §7, G1–G3, G8).
 *
 * Tests:
 *   1. G8: PNG tEXt chunk provenance stamp + immediate read-back verification
 *      (owner, licence, canon_sha, entry_id, entry_sha256, run_id), plus zTXt
 *      and iTXt chunk decoding.
 *   2. G8 refusal paths: missing stamp (PNG_STAMP_MISSING) and tampered stamp
 *      (PNG_STAMP_MISMATCH), plus JSON-encoded extra_pnginfo roundtrip.
 *   3. G3: Qwen LoRA-aware graph (LoraLoaderModelOnly chain between UNETLoader
 *      and ModelSamplingAuraFlow) across buildQwenGraph, buildWorkflowGraph,
 *      resolveQwenLoras, and scripts/generate.js normalizeGenerationInput,
 *      plus 64x64 no-weights buildStubFixtureGraph.
 *   4. G1 & §3.1/§3.5/§7: VM bootstrap guards — loopback-only ComfyUI bind
 *      check, listening socket verification, weight staging by sha256 + SPDX
 *      licence from manifest, and window.json contract builder.
 *   5. G2 & §7: Durable job queue (jobs.jsonl -> renders.jsonl), deliberate
 *      kill after job 1 + idempotent resume for jobs 2..3 with matching sha256
 *      hashes, periodic copy-back every N images, and H7 stripped-stamp refusal.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { deflateSync } from 'node:zlib';

import {
  decodePng,
  crc32Png,
  PNG_STAMP_KEYS,
  REQUIRED_PNG_STAMP_FIELDS,
  writePngTextChunks,
  readPngTextChunks,
  stampPngProvenance,
  readPngProvenance,
  verifyPngProvenance,
} from '../../lib/png-meta.js';
import { encodePng } from '../lib-asset/fixtures/make-png.js';
import {
  buildQwenGraph,
  buildWorkflowGraph,
  resolveQwenLoras,
  buildStubFixtureGraph,
} from '../../lib/adapters/comfyui-workflows.js';
import { normalizeGenerationInput } from '../../scripts/generate.js';
import {
  LANE1_PYTHON_VERSION,
  LANE1_UV_PIN,
  assertLoopbackComfyUrl,
  verifyLoopbackSockets,
  stageWeightsFromManifest,
  buildWindowRecord,
  compileLane1Jobs,
  writeJobsJsonl,
  readJobsJsonl,
  runLane1Queue,
} from '../../lib/lane1-render.js';

function make64x64Png(seed = 1) {
  const width = 64;
  const height = 64;
  const data = new Uint8Array(width * height * 3);
  const r = (seed >> 16) & 0xff;
  const g = (seed >> 8) & 0xff;
  const b = seed & 0xff;
  for (let i = 0; i < width * height; i++) {
    data[i * 3] = (r + (i & 0x1f)) & 0xff;
    data[i * 3 + 1] = (g + ((i >> 5) & 0x1f)) & 0xff;
    data[i * 3 + 2] = (b + ((i >> 10) & 0x1f)) & 0xff;
  }
  return encodePng({ width, height, colorType: 2, data });
}

function makeCustomChunk(type, payload) {
  const out = Buffer.alloc(12 + payload.length);
  out.writeUInt32BE(payload.length, 0);
  out.write(type, 4, 'latin1');
  payload.copy(out, 8);
  out.writeUInt32BE(crc32Png(out.subarray(4, 8 + payload.length)), 8 + payload.length);
  return out;
}

const SAMPLE_STAMP = Object.freeze({
  owner: 'mcp-tool-shop',
  licence: 'CC-BY-4.0',
  canon_sha: 'sha256:' + 'a'.repeat(64),
  entry_id: 'ship_brig_hull',
  entry_sha256: 'sha256:' + 'b'.repeat(64),
  run_id: 'run_20261105_lane1',
  workflow_sha: 'sha256:' + 'c'.repeat(64),
  window_id: 'win_lane1_stub_01',
});

const SAMPLE_MODEL_PINS = Object.freeze({
  base: {
    name: 'qwen_image_fp8_e4m3fn.safetensors',
    sha256: 'sha256:' + '1'.repeat(64),
    licence_id: 'Apache-2.0',
    licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
    date_read: '2026-10-25',
  },
  text_encoder: {
    name: 'qwen_2.5_vl_7b_fp8_scaled.safetensors',
    sha256: 'sha256:' + '2'.repeat(64),
    licence_id: 'Apache-2.0',
    licence_url: 'https://raw.githubusercontent.com/QwenLM/Qwen2.5-VL/main/LICENSE',
    date_read: '2026-10-28',
  },
  vae: {
    name: 'qwen_image_vae.safetensors',
    sha256: 'sha256:' + '3'.repeat(64),
    licence_id: 'Apache-2.0',
    licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
    date_read: '2026-10-25',
  },
  loras: [
    {
      name: 'saltroad_style_v2.safetensors',
      weight: 0.75,
      sha256: 'sha256:' + '4'.repeat(64),
      licence_id: 'Apache-2.0',
      licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
      date_read: '2026-10-25',
    },
  ],
});

test('G8: stampPngProvenance writes sdlab:* tEXt chunks and verifyPngProvenance reads them back without altering pixels', () => {
  const rawPng = make64x64Png(42);
  const beforePixels = decodePng(rawPng);

  assert.equal(REQUIRED_PNG_STAMP_FIELDS.length, 6);
  assert.equal(PNG_STAMP_KEYS.owner, 'sdlab:owner');

  const stamped = stampPngProvenance(rawPng, SAMPLE_STAMP);
  const afterPixels = decodePng(stamped);
  assert.equal(afterPixels.width, 64);
  assert.equal(afterPixels.height, 64);
  assert.deepEqual([...afterPixels.data], [...beforePixels.data]);

  // Re-stamping replaces existing keys idempotently
  const restamped = stampPngProvenance(stamped, {
    ...SAMPLE_STAMP,
    window_id: 'win_lane1_stub_02',
  });
  const readBack = readPngProvenance(restamped);
  assert.equal(readBack.owner, 'mcp-tool-shop');
  assert.equal(readBack.licence, 'CC-BY-4.0');
  assert.equal(readBack.canon_sha, SAMPLE_STAMP.canon_sha);
  assert.equal(readBack.entry_id, SAMPLE_STAMP.entry_id);
  assert.equal(readBack.entry_sha256, SAMPLE_STAMP.entry_sha256);
  assert.equal(readBack.run_id, SAMPLE_STAMP.run_id);
  assert.equal(readBack.workflow_sha, SAMPLE_STAMP.workflow_sha);
  assert.equal(readBack.window_id, 'win_lane1_stub_02');

  const verified = verifyPngProvenance(restamped, {
    ...SAMPLE_STAMP,
    window_id: 'win_lane1_stub_02',
  });
  assert.equal(verified.ok, true);
  assert.equal(verified.stamp.owner, 'mcp-tool-shop');

  // Also test zTXt and iTXt reading in readPngTextChunks
  const iendOffset = rawPng.length - 12;
  const ztxtPayload = Buffer.concat([
    Buffer.from('zkey\x00\x00', 'latin1'),
    deflateSync(Buffer.from('compressed-val', 'latin1')),
  ]);
  const itxtPayloadUncomp = Buffer.from('ikey1\x00\x00\x00en\x00\x00utf8-val', 'utf8');
  const itxtPayloadComp = Buffer.concat([
    Buffer.from('ikey2\x00\x01\x00en\x00\x00', 'utf8'),
    deflateSync(Buffer.from('utf8-comp-val', 'utf8')),
  ]);
  const withZtxtItxt = Buffer.concat([
    rawPng.subarray(0, iendOffset),
    makeCustomChunk('zTXt', ztxtPayload),
    makeCustomChunk('iTXt', itxtPayloadUncomp),
    makeCustomChunk('iTXt', itxtPayloadComp),
    rawPng.subarray(iendOffset),
  ]);
  const parsedChunks = readPngTextChunks(withZtxtItxt);
  assert.equal(parsedChunks.zkey, 'compressed-val');
  assert.equal(parsedChunks.ikey1, 'utf8-val');
  assert.equal(parsedChunks.ikey2, 'utf8-comp-val');
});

test('G8: verifyPngProvenance refuses unstamped or mismatched PNGs and unwraps JSON-quoted extra_pnginfo chunks', () => {
  const rawPng = make64x64Png(7);

  // Unstamped PNG -> PNG_STAMP_MISSING
  assert.throws(
    () => verifyPngProvenance(rawPng, SAMPLE_STAMP),
    (err) => err.code === 'PNG_STAMP_MISSING'
  );

  // Incomplete stamp at write time -> PNG_STAMP_MISSING
  assert.throws(
    () => stampPngProvenance(rawPng, null),
    (err) => err.code === 'PNG_STAMP_MISSING'
  );
  assert.throws(
    () => stampPngProvenance(rawPng, { owner: 'mcp-tool-shop' }),
    (err) => err.code === 'PNG_STAMP_MISSING'
  );

  // Mismatched expected field -> PNG_STAMP_MISMATCH
  const stamped = stampPngProvenance(rawPng, SAMPLE_STAMP);
  assert.throws(
    () => verifyPngProvenance(stamped, { ...SAMPLE_STAMP, canon_sha: 'sha256:' + 'f'.repeat(64) }),
    (err) => err.code === 'PNG_STAMP_MISMATCH' && /canon_sha/.test(err.message)
  );

  // ComfyUI SaveImage serializes extra_pnginfo values with json.dumps(...)
  const jsonQuoted = writePngTextChunks(rawPng, {
    'sdlab:owner': JSON.stringify(SAMPLE_STAMP.owner),
    'sdlab:licence': JSON.stringify(SAMPLE_STAMP.licence),
    'sdlab:canon_sha': JSON.stringify(SAMPLE_STAMP.canon_sha),
    'sdlab:entry_id': JSON.stringify(SAMPLE_STAMP.entry_id),
    'sdlab:entry_sha256': JSON.stringify(SAMPLE_STAMP.entry_sha256),
    'sdlab:run_id': JSON.stringify(SAMPLE_STAMP.run_id),
  });
  const unwrapped = verifyPngProvenance(jsonQuoted, {
    owner: SAMPLE_STAMP.owner,
    licence: SAMPLE_STAMP.licence,
    canon_sha: SAMPLE_STAMP.canon_sha,
    entry_id: SAMPLE_STAMP.entry_id,
    entry_sha256: SAMPLE_STAMP.entry_sha256,
    run_id: SAMPLE_STAMP.run_id,
  });
  assert.equal(unwrapped.ok, true);
  assert.equal(unwrapped.stamp.owner, 'mcp-tool-shop');
});

test('G3: Qwen LoRA-aware graph chains LoraLoaderModelOnly between UNETLoader and ModelSamplingAuraFlow across brief, wave, and defaults', () => {
  const brief = {
    prompt: 'brig hull in silhouette, timber planking',
    negative_prompt: 'blurry, modern',
    loras: [{ name: 'hull_lora_a.safetensors', weight: 0.8 }],
    runtime_plan: {
      width: 1024,
      height: 1024,
      steps: 22,
      cfg: 3.5,
      loras: [{ lora_name: 'hull_lora_b.safetensors', strength_model: 0.5 }],
    },
  };
  const projectDefaults = {
    base: 'qwen-image',
    loras: [{ name: 'base_style.safetensors', weight: 0.65 }],
  };

  const resolvedLoras = resolveQwenLoras({ brief, projectDefaults });
  assert.equal(resolvedLoras.length, 3);
  assert.deepEqual(resolvedLoras, [
    { name: 'base_style.safetensors', weight: 0.65 },
    { name: 'hull_lora_a.safetensors', weight: 0.8 },
    { name: 'hull_lora_b.safetensors', weight: 0.5 },
  ]);

  const { nodes, saveNodeId } = buildWorkflowGraph({
    brief,
    projectDefaults,
    seed: 12345,
  });
  assert.equal(saveNodeId, '9');
  assert.equal(nodes['37'].class_type, 'UNETLoader');
  assert.equal(nodes['40'].class_type, 'LoraLoaderModelOnly');
  assert.deepEqual(nodes['40'].inputs.model, ['37', 0]);
  assert.equal(nodes['40'].inputs.lora_name, 'base_style.safetensors');
  assert.equal(nodes['40'].inputs.strength_model, 0.65);

  assert.equal(nodes['41'].class_type, 'LoraLoaderModelOnly');
  assert.deepEqual(nodes['41'].inputs.model, ['40', 0]);
  assert.equal(nodes['41'].inputs.lora_name, 'hull_lora_a.safetensors');
  assert.equal(nodes['41'].inputs.strength_model, 0.8);

  assert.equal(nodes['42'].class_type, 'LoraLoaderModelOnly');
  assert.deepEqual(nodes['42'].inputs.model, ['41', 0]);
  assert.equal(nodes['42'].inputs.lora_name, 'hull_lora_b.safetensors');
  assert.equal(nodes['42'].inputs.strength_model, 0.5);

  // ModelSamplingAuraFlow takes the final LoRA output ['42', 0]
  assert.equal(nodes['66'].class_type, 'ModelSamplingAuraFlow');
  assert.deepEqual(nodes['66'].inputs.model, ['42', 0]);

  // Wave schema in scripts/generate.js preserves per-subject and defaults loras
  const waveNorm = normalizeGenerationInput(
    {
      wave: 'wave1',
      defaults: { base: 'qwen-image', loras: [{ name: 'wave_default.safetensors', weight: 0.7 }] },
      subjects: [
        { id: 'brig', prompt: 'brig ship', variations: 1, loras: [{ name: 'brig_specific.safetensors', weight: 0.9 }] },
        { id: 'sloop', prompt: 'sloop ship', variations: 1 },
      ],
    },
    { defaults: { base: 'qwen-image' } }
  );
  assert.deepEqual(waveNorm.jobs[0].loras, [{ name: 'brig_specific.safetensors', weight: 0.9 }]);
  assert.deepEqual(waveNorm.jobs[1].loras, [{ name: 'wave_default.safetensors', weight: 0.7 }]);

  // Stub fixture graph is 64x64 and requires zero model weights
  const stubGraph = buildStubFixtureGraph({ seed: 99, width: 64, height: 64 });
  assert.equal(stubGraph.saveNodeId, '3');
  assert.equal(stubGraph.nodes['1'].class_type, 'EmptyImage');
  assert.equal(stubGraph.nodes['1'].inputs.width, 64);
  assert.equal(stubGraph.nodes['1'].inputs.height, 64);
  assert.equal(stubGraph.nodes['2'].class_type, 'ImageInvert');
  assert.equal(stubGraph.nodes['3'].class_type, 'SaveImage');
});

test('G1 & §3.1/§3.5/§7: VM bootstrap enforces loopback-only ComfyUI bind, verifies weight sha256 + licence, and builds window.json', () => {
  // Loopback URL guard
  assert.equal(assertLoopbackComfyUrl('http://127.0.0.1:8188').hostname, '127.0.0.1');
  assert.equal(assertLoopbackComfyUrl('http://localhost:8188').hostname, 'localhost');
  assert.throws(
    () => assertLoopbackComfyUrl('not-a-url'),
    (err) => err.code === 'LANE1_NON_LOOPBACK_BIND'
  );
  assert.throws(
    () => assertLoopbackComfyUrl('http://0.0.0.0:8188'),
    (err) => err.code === 'LANE1_NON_LOOPBACK_BIND'
  );
  assert.throws(
    () => assertLoopbackComfyUrl('https://tunnel.example.com:8188'),
    (err) => err.code === 'LANE1_NON_LOOPBACK_BIND'
  );

  // Listening sockets guard
  const okSockets = verifyLoopbackSockets(['127.0.0.1:8188', { address: '127.0.0.1', port: 22 }], 8188);
  assert.equal(okSockets.ok, true);
  assert.throws(
    () => verifyLoopbackSockets([], 8188),
    (err) => err.code === 'LANE1_NON_LOOPBACK_SOCKET'
  );
  assert.throws(
    () => verifyLoopbackSockets(['0.0.0.0:8188'], 8188),
    (err) => err.code === 'LANE1_NON_LOOPBACK_SOCKET'
  );
  assert.throws(
    () => verifyLoopbackSockets(['*:8188'], 8188),
    (err) => err.code === 'LANE1_NON_LOOPBACK_SOCKET'
  );
  assert.throws(
    () => verifyLoopbackSockets(['127.0.0.1:8188', '0.0.0.0:9000'], 8188),
    (err) => err.code === 'LANE1_NON_LOOPBACK_SOCKET'
  );
  assert.throws(
    () => verifyLoopbackSockets(['127.0.0.1:22'], 8188),
    (err) => err.code === 'LANE1_NON_LOOPBACK_SOCKET'
  );

  // Weight manifest staging by sha256 + licence
  const tmpDir = mkdtempSync(join(tmpdir(), 'sdlab-lane1-weights-'));
  try {
    const fakeWeightBytes = Buffer.from('synthetic-fixture-weight-bytes');
    const fakeSha = createHash('sha256').update(fakeWeightBytes).digest('hex');
    const weightPath = join(tmpDir, 'fixture_unet.safetensors');
    writeFileSync(weightPath, fakeWeightBytes);

    assert.throws(
      () => stageWeightsFromManifest({ stagingDir: tmpDir, manifest: [] }),
      (err) => err.code === 'LANE1_WEIGHT_MANIFEST_EMPTY'
    );

    const staged = stageWeightsFromManifest({
      stagingDir: tmpDir,
      manifest: [
        {
          role: 'base',
          name: 'fixture_unet.safetensors',
          repo: 'Qwen/Qwen-Image',
          revision: 'main',
          sha256: `sha256:${fakeSha}`,
          licence_id: 'Apache-2.0',
          licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
          date_read: '2026-10-25',
        },
      ],
    });
    assert.equal(staged.length, 1);
    assert.equal(staged[0].verified, true);
    assert.equal(staged[0].sha256, `sha256:${fakeSha}`);

    // Wrong sha256 -> LANE1_WEIGHT_SHA_MISMATCH
    assert.throws(
      () =>
        stageWeightsFromManifest({
          stagingDir: tmpDir,
          manifest: [
            {
              role: 'base',
              name: 'fixture_unet.safetensors',
              sha256: 'sha256:' + '0'.repeat(64),
              licence_id: 'Apache-2.0',
              licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
              date_read: '2026-10-25',
            },
          ],
        }),
      (err) => err.code === 'LANE1_WEIGHT_SHA_MISMATCH'
    );

    // Missing file -> LANE1_WEIGHT_FILE_MISSING
    assert.throws(
      () =>
        stageWeightsFromManifest({
          stagingDir: tmpDir,
          manifest: [
            {
              role: 'base',
              name: 'missing_unet.safetensors',
              sha256: `sha256:${fakeSha}`,
              licence_id: 'Apache-2.0',
              licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
              date_read: '2026-10-25',
            },
          ],
        }),
      (err) => err.code === 'LANE1_WEIGHT_FILE_MISSING'
    );

    // Non-cleared licence -> LANE1_WEIGHT_LICENCE_INVALID
    assert.throws(
      () =>
        stageWeightsFromManifest({
          stagingDir: tmpDir,
          manifest: [
            {
              role: 'base',
              name: 'fixture_unet.safetensors',
              sha256: `sha256:${fakeSha}`,
              licence_id: 'FLUX-NonCommercial',
              licence_url: 'https://example.com/nc',
              date_read: '2026-10-25',
            },
          ],
        }),
      (err) => err.code === 'LANE1_WEIGHT_LICENCE_INVALID'
    );
  } finally {
    rmSync(tmpDir, { recursive: true, force: true });
  }

  // window.json contract (§7)
  const win = buildWindowRecord({
    window_id: 'win_lane1_01',
    card: 'CPU',
    vm_gate: { nproc: 8, free_m: 12300, gpu: 'none' },
    system_python: '3.13.16',
    python: LANE1_PYTHON_VERSION,
    python_sha256: 'sha256:' + '9'.repeat(64),
    uv: 'uv 0.13.5',
    comfyui_commit: 'a'.repeat(40),
    comfy_headless_version: '3.1.0',
    comfy_bind: '127.0.0.1:8188',
    listening_sockets: ['127.0.0.1:8188'],
    override_sha256: null,
    cap: 0.05,
    wall_s: 3000,
    margin: 0.01,
    start_balance: 2512.75,
    end_balance: 2512.73,
    rate_measured: 0.08,
  });
  assert.equal(win.python, '3.14.9');
  assert.equal(win.system_python, '3.13.16');
  assert.deepEqual(win.listening_sockets, ['127.0.0.1:8188']);
  assert.equal(LANE1_UV_PIN, 'uv==0.13.5');

  // Non-3.14.9 python refused
  assert.throws(
    () =>
      buildWindowRecord({
        window_id: 'win_bad_py',
        card: 'CPU',
        system_python: '3.13.16',
        python: '3.12.9',
        python_sha256: 'sha256:' + '9'.repeat(64),
        uv: 'uv 0.13.5',
        comfy_bind: '127.0.0.1:8188',
        listening_sockets: ['127.0.0.1:8188'],
      }),
    (err) => err.code === 'LANE1_PYTHON_VERSION_MISMATCH'
  );
});

test('G2 & §7: durable queue compiles jobs.jsonl, kills after job 1, resumes for jobs 2..3 with matching sha256s, runs periodic copy-back, and refuses stripped stamps (H7)', async () => {
  const tmpDir = mkdtempSync(join(tmpdir(), 'sdlab-lane1-queue-'));
  try {
    const jobsPath = join(tmpDir, 'jobs.jsonl');
    const rendersPath = join(tmpDir, 'renders.jsonl');
    const outDir = join(tmpDir, 'renders');
    const copyBackDir = join(tmpDir, 'copyback');

    const entries = [
      { entry_id: 'ship_brig', entry_sha256: 'sha256:' + '1'.repeat(64), prompt: 'brig hull port view', negative: 'blurry', seed: 101 },
      { entry_id: 'ship_sloop', entry_sha256: 'sha256:' + '2'.repeat(64), prompt: 'sloop hull port view', negative: 'blurry', seed: 102 },
      { entry_id: 'ship_carrack', entry_sha256: 'sha256:' + '3'.repeat(64), prompt: 'carrack hull port view', negative: 'blurry', seed: 103 },
    ];

    // Also test Qwen mode compilation
    const qwenCompiled = compileLane1Jobs({
      runId: 'run_stage0_b_qwen',
      canonSha: SAMPLE_STAMP.canon_sha,
      entries,
      modelPins: SAMPLE_MODEL_PINS,
      mode: 'qwen',
    });
    assert.equal(qwenCompiled.jobs[0].template_id, 'qwen_txt2img_lora');
    assert.equal(qwenCompiled.jobs[0].workflow['40'].class_type, 'LoraLoaderModelOnly');

    const compiled = compileLane1Jobs({
      runId: 'run_stage0_b',
      canonSha: SAMPLE_STAMP.canon_sha,
      entries,
      modelPins: SAMPLE_MODEL_PINS,
      mode: 'stub',
      width: 64,
      height: 64,
    });
    assert.equal(compiled.jobs.length, 3);
    assert.equal(compiled.jobs[0].owner, 'mcp-tool-shop');
    assert.equal(compiled.jobs[0].licence, 'CC-BY-4.0');
    assert.equal(compiled.jobs[0].canon_sha, SAMPLE_STAMP.canon_sha);
    assert.equal(compiled.jobs[0].model_pins.base.licence_id, 'Apache-2.0');

    writeJobsJsonl(jobsPath, compiled.jobs);
    const loadedJobs = readJobsJsonl(jobsPath);
    assert.equal(loadedJobs.length, 3);

    // Tampered jobs.jsonl.sha256 refused
    const badJobsPath = join(tmpDir, 'bad-jobs.jsonl');
    writeJobsJsonl(badJobsPath, compiled.jobs);
    writeFileSync(`${badJobsPath}.sha256`, 'sha256:' + '0'.repeat(64) + '\n');
    assert.throws(
      () => readJobsJsonl(badJobsPath),
      (err) => err.code === 'LANE1_JOBS_SHA_MISMATCH'
    );

    const renderCalls = [];
    const renderFn = async (job) => {
      renderCalls.push(job.job_id);
      return make64x64Png(job.seed);
    };

    // H7: if stamp is stripped before save, read-back verification refuses with PNG_STAMP_MISSING
    await assert.rejects(
      () =>
        runLane1Queue({
          jobsPath,
          rendersPath,
          outDir: join(tmpDir, 'stripped-out'),
          windowId: 'win_stripped',
          renderFn,
          stripStampBeforeSave: true,
        }),
      (err) => err.code === 'PNG_STAMP_MISSING'
    );
    renderCalls.length = 0;

    // Run 1: deliberate kill after 1 job
    const run1 = await runLane1Queue({
      jobsPath,
      rendersPath,
      outDir,
      copyBackDir,
      copyBackEvery: 2,
      windowId: 'win_stub_1',
      renderFn,
      stopAfterJobs: 1,
    });
    assert.equal(run1.renderedCount, 1);
    assert.equal(run1.skippedCount, 0);
    assert.equal(run1.haltedEarly, true);
    assert.deepEqual(renderCalls, ['job_001']);

    const job1PngPath = join(outDir, 'job_001.png');
    assert.equal(existsSync(job1PngPath), true);
    const job1ShaBeforeResume =
      'sha256:' + createHash('sha256').update(readFileSync(job1PngPath)).digest('hex');

    // Run 2: resume after kill — job_001 must be skipped, job_002 and job_003 rendered
    const run2 = await runLane1Queue({
      jobsPath,
      rendersPath,
      outDir,
      copyBackDir,
      copyBackEvery: 2,
      windowId: 'win_stub_1',
      renderFn,
    });
    assert.equal(run2.skippedCount, 1);
    assert.equal(run2.renderedCount, 2);
    assert.equal(run2.haltedEarly, false);
    assert.equal(run2.copyBackCount, 1);
    assert.deepEqual(renderCalls, ['job_001', 'job_002', 'job_003']);

    // Verify job_001 hash is untouched and all 3 rows in renders.jsonl match disk & carry stamps
    const job1ShaAfterResume =
      'sha256:' + createHash('sha256').update(readFileSync(job1PngPath)).digest('hex');
    assert.equal(job1ShaAfterResume, job1ShaBeforeResume);

    const renderRows = readFileSync(rendersPath, 'utf-8')
      .trim()
      .split('\n')
      .map((l) => JSON.parse(l));
    assert.equal(renderRows.length, 3);
    for (const row of renderRows) {
      assert.equal(row.status, 'ok');
      assert.equal(row.owner, 'mcp-tool-shop');
      assert.equal(row.licence, 'CC-BY-4.0');
      assert.equal(row.canon_sha, SAMPLE_STAMP.canon_sha);
      assert.equal(row.stamp_verified, true);
      const diskBytes = readFileSync(join(outDir, row.output_file));
      const diskSha = 'sha256:' + createHash('sha256').update(diskBytes).digest('hex');
      assert.equal(diskSha, row.png_sha256);
      const v = verifyPngProvenance(diskBytes, {
        owner: row.owner,
        licence: row.licence,
        canon_sha: row.canon_sha,
        entry_id: row.entry_id,
        entry_sha256: row.entry_sha256,
        run_id: row.run_id,
      });
      assert.equal(v.ok, true);
    }

    // Verify copy-back directory has renders.jsonl and rendered PNGs
    assert.equal(existsSync(join(copyBackDir, 'renders.jsonl')), true);
    assert.equal(existsSync(join(copyBackDir, 'job_001.png')), true);
    assert.equal(existsSync(join(copyBackDir, 'job_002.png')), true);
    assert.equal(existsSync(join(copyBackDir, 'job_003.png')), true);
  } finally {
    rmSync(tmpDir, { recursive: true, force: true });
  }
});
