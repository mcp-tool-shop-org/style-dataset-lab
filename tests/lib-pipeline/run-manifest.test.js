/**
 * Unit tests for lib/run-manifest.js — the PIN_PER_STEP pinning contract.
 *
 * Covers: comfy_workflow_sha determinism + normalization (per-item seed/prompt
 * do NOT change it, but the pipeline skeleton does); seed_policy mapping;
 * best-effort model hashing against a temp models dir (unresolved → null+note,
 * resolved w/o --hash-models → size only, resolved w/ hashing → sha + cache);
 * the assembled pinning block shape; and the persistent hash cache round-trip.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  PINNING_VERSION,
  SEED_POLICIES,
  seedPolicyFromMode,
  stableStringify,
  normalizeGraphForHash,
  comfyWorkflowSha,
  resolveModelPath,
  sha256File,
  hashModelFile,
  buildModelHashes,
  buildPinning,
  createHashCache,
  flushHashCache,
} from '../../lib/run-manifest.js';
import { buildQwenGraph } from '../../lib/adapters/comfyui-workflows.js';

// ─── comfy_workflow_sha ──────────────────────────────────────────

test('comfyWorkflowSha is deterministic and sha256-prefixed', () => {
  const { nodes } = buildQwenGraph({ prompt: 'p', negativePrompt: 'n', seed: 1 });
  const a = comfyWorkflowSha(nodes);
  const b = comfyWorkflowSha(nodes);
  assert.equal(a, b);
  assert.match(a, /^sha256:[0-9a-f]{64}$/);
});

test('comfyWorkflowSha ignores per-item seed and prompt (wave-level pin)', () => {
  const g1 = buildQwenGraph({ prompt: 'a bog creature', negativePrompt: 'anime', seed: 1000 }).nodes;
  const g2 = buildQwenGraph({ prompt: 'a totally different subject', negativePrompt: 'anime', seed: 424242 }).nodes;
  // Same pipeline skeleton, different prompt + seed → SAME workflow sha.
  assert.equal(comfyWorkflowSha(g1), comfyWorkflowSha(g2));
});

test('comfyWorkflowSha changes when the pipeline skeleton changes', () => {
  const base = buildQwenGraph({ prompt: 'p', negativePrompt: 'n', seed: 1 }).nodes;
  const diffShift = buildQwenGraph({ prompt: 'p', negativePrompt: 'n', seed: 1, shift: 2.0 }).nodes;
  const diffLora = buildQwenGraph({ prompt: 'p', negativePrompt: 'n', seed: 1, loras: [{ name: 'x.safetensors', weight: 0.8 }] }).nodes;
  assert.notEqual(comfyWorkflowSha(base), comfyWorkflowSha(diffShift));
  assert.notEqual(comfyWorkflowSha(base), comfyWorkflowSha(diffLora));
});

test('comfyWorkflowSha returns null for an empty/absent graph', () => {
  assert.equal(comfyWorkflowSha({}), null);
  assert.equal(comfyWorkflowSha(null), null);
});

test('normalizeGraphForHash blanks seed, prompt text, and filename_prefix', () => {
  const { nodes } = buildQwenGraph({ prompt: 'secret prompt', negativePrompt: 'neg', seed: 777, filenamePrefix: 'run42' });
  const norm = normalizeGraphForHash(nodes);
  assert.equal(norm['3'].inputs.seed, 0);           // KSampler seed zeroed
  assert.equal(norm['6'].inputs.text, '');          // positive prompt blanked
  assert.equal(norm['7'].inputs.text, '');          // negative prompt blanked
  assert.equal(norm['9'].inputs.filename_prefix, ''); // SaveImage prefix blanked
});

// ─── stableStringify ─────────────────────────────────────────────

test('stableStringify sorts object keys and preserves array order', () => {
  assert.equal(stableStringify({ b: 1, a: 2 }), '{"a":2,"b":1}');
  assert.equal(stableStringify([3, 1, 2]), '[3,1,2]');
  assert.equal(stableStringify({ z: [2, 1], a: 'x' }), '{"a":"x","z":[2,1]}');
});

// ─── seed policy ─────────────────────────────────────────────────

test('seedPolicyFromMode maps runtime modes to policies', () => {
  assert.equal(seedPolicyFromMode('increment'), SEED_POLICIES.BASE_INCREMENT);
  assert.equal(seedPolicyFromMode('fixed'), SEED_POLICIES.FIXED);
  assert.equal(seedPolicyFromMode('random'), SEED_POLICIES.RANDOM);
  assert.equal(seedPolicyFromMode('anything-else'), SEED_POLICIES.BASE_INCREMENT);
});

// ─── model resolution + hashing (temp models dir) ────────────────

async function makeModelsDir() {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-models-'));
  await mkdir(join(dir, 'diffusion_models'), { recursive: true });
  await mkdir(join(dir, 'loras'), { recursive: true });
  await writeFile(join(dir, 'diffusion_models', 'fake_unet.safetensors'), 'UNET-BYTES');
  await writeFile(join(dir, 'loras', 'fake_lora.safetensors'), 'LORA-BYTES');
  return dir;
}

test('resolveModelPath finds a file in the kind-appropriate subdir', async () => {
  const dir = await makeModelsDir();
  try {
    const p = resolveModelPath('fake_unet.safetensors', 'unet', dir);
    assert.ok(p && p.endsWith('fake_unet.safetensors'));
    assert.equal(resolveModelPath('missing.safetensors', 'unet', dir), null);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('hashModelFile: unresolved file → size/sha null with a note', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-empty-'));
  try {
    const r = hashModelFile('nope.safetensors', { kind: 'unet', modelsDir: dir, doHash: true });
    assert.equal(r.name, 'nope.safetensors');
    assert.equal(r.size_bytes, null);
    assert.equal(r.sha256, null);
    assert.match(r.hash_note, /unresolved/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('hashModelFile: resolvable without --hash-models records size but not sha', async () => {
  const dir = await makeModelsDir();
  try {
    const r = hashModelFile('fake_unet.safetensors', { kind: 'unet', modelsDir: dir, doHash: false });
    assert.equal(r.size_bytes, 'UNET-BYTES'.length);
    assert.equal(r.sha256, null);
    assert.match(r.hash_note, /hash skipped/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('hashModelFile: --hash-models computes a real sha and caches it', async () => {
  const dir = await makeModelsDir();
  try {
    const cache = { map: new Map(), dirty: false };
    const r = hashModelFile('fake_unet.safetensors', { kind: 'unet', modelsDir: dir, doHash: true, cache });
    assert.equal(r.size_bytes, 'UNET-BYTES'.length);
    assert.match(r.sha256, /^sha256:[0-9a-f]{64}$/);
    assert.equal(r.sha256, sha256File(resolveModelPath('fake_unet.safetensors', 'unet', dir)));
    assert.equal(cache.dirty, true);
    assert.equal(cache.map.size, 1);
    // A second call hits the cache (still returns the same sha).
    const r2 = hashModelFile('fake_unet.safetensors', { kind: 'unet', modelsDir: dir, doHash: true, cache });
    assert.equal(r2.sha256, r.sha256);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('buildModelHashes only includes provided roles', async () => {
  const dir = await makeModelsDir();
  try {
    const out = buildModelHashes({ unet: 'fake_unet.safetensors' }, { modelsDir: dir, doHash: false });
    assert.ok(out.unet);
    assert.equal(out.clip, undefined);
    assert.equal(out.checkpoint, undefined);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

// ─── the pinning block ───────────────────────────────────────────

test('buildPinning assembles the full contract shape', async () => {
  const dir = await makeModelsDir();
  try {
    const { nodes } = buildQwenGraph({ prompt: 'p', negativePrompt: 'n', seed: 1, loras: [{ name: 'fake_lora.safetensors', weight: 0.9 }] });
    const pin = buildPinning({
      graph: nodes,
      models: { unet: 'fake_unet.safetensors' },
      loras: [{ name: 'fake_lora.safetensors', weight: 0.9 }],
      seedPolicy: SEED_POLICIES.BASE_INCREMENT,
      hashModels: true,
      modelsDir: dir,
    });
    assert.equal(pin.pinning_version, PINNING_VERSION);
    assert.match(pin.comfy_workflow_sha, /^sha256:/);
    assert.equal(pin.seed_policy, 'base+increment');
    assert.match(pin.models.unet.sha256, /^sha256:/);
    assert.equal(pin.loras.length, 1);
    assert.equal(pin.loras[0].weight, 0.9);
    assert.match(pin.loras[0].sha256, /^sha256:/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('buildPinning defaults LoRA weight to 1.0 when omitted', () => {
  const pin = buildPinning({ graph: {}, loras: [{ name: 'x.safetensors' }], modelsDir: '/nonexistent-models-dir' });
  assert.equal(pin.loras[0].weight, 1.0);
  assert.equal(pin.comfy_workflow_sha, null); // empty graph
});

// ─── persistent hash cache ───────────────────────────────────────

test('createHashCache / flushHashCache round-trips to disk', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-cache-'));
  try {
    const cacheFile = join(dir, 'cache.json');
    const c1 = createHashCache(cacheFile);
    c1.map.set('foo:1:2', 'sha256:deadbeef');
    c1.dirty = true;
    flushHashCache(c1);
    const c2 = createHashCache(cacheFile);
    assert.equal(c2.map.get('foo:1:2'), 'sha256:deadbeef');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
