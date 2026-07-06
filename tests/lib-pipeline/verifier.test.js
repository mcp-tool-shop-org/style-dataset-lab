/**
 * Unit tests for lib/verifier.js — the EXTERNAL_VERIFIER fields + self-verify
 * warning — plus the critique-engine field wiring and manifest backward-compat.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  RULE_BASED_JUDGE,
  HUMAN_JUDGE,
  deriveGeneratorModel,
  generatorModelFromManifest,
  warnIfSelfVerification,
} from '../../lib/verifier.js';
import { critiqueCandidate } from '../../lib/critique-engine.js';
import { checkManifestVersion, SCHEMA_VERSION } from '../../lib/snapshot.js';

// ─── deriveGeneratorModel ────────────────────────────────────────

test('deriveGeneratorModel builds <base>:<model> for Qwen and SDXL', () => {
  assert.equal(
    deriveGeneratorModel({ base: 'qwen-image', unet: 'qwen_image_fp8_e4m3fn.safetensors' }),
    'qwen-image:qwen_image_fp8_e4m3fn',
  );
  assert.equal(
    deriveGeneratorModel({ base: 'sdxl', checkpoint: 'dreamshaperXL.safetensors' }),
    'sdxl:dreamshaperXL',
  );
});

test('deriveGeneratorModel degrades gracefully on partial/absent provenance', () => {
  assert.equal(deriveGeneratorModel({ base: 'qwen-image' }), 'qwen-image');
  assert.equal(deriveGeneratorModel({ unet: 'x.safetensors' }), 'x');
  assert.equal(deriveGeneratorModel({}), null);
  assert.equal(deriveGeneratorModel(null), null);
});

// ─── generatorModelFromManifest ──────────────────────────────────

test('generatorModelFromManifest reads the pinning block (qwen) or checkpoint (sdxl)', () => {
  const qwen = { pinning: { models: { unet: { name: 'qwen_image_fp8_e4m3fn.safetensors' } } } };
  assert.equal(generatorModelFromManifest(qwen), 'qwen-image:qwen_image_fp8_e4m3fn');
  const sdxl = { checkpoint: 'dreamshaperXL.safetensors' };
  assert.equal(generatorModelFromManifest(sdxl), 'sdxl:dreamshaperXL');
});

test('generatorModelFromManifest returns null for a legacy manifest (no pinning/checkpoint)', () => {
  assert.equal(generatorModelFromManifest({ run_id: 'run_x' }), null);
  assert.equal(generatorModelFromManifest(null), null);
});

// ─── warnIfSelfVerification ──────────────────────────────────────

test('warnIfSelfVerification fires only when judge === generator', () => {
  assert.equal(warnIfSelfVerification('qwen-image:foo', 'qwen-image:foo', 'ctx'), true);
  assert.equal(warnIfSelfVerification('human', 'qwen-image:foo'), false);
  assert.equal(warnIfSelfVerification('rule-based:sdlab-critique-v1', null), false);
  assert.equal(warnIfSelfVerification(null, 'qwen-image:foo'), false);
});

// ─── critique-engine field wiring ────────────────────────────────

test('critiqueCandidate stamps judged_by_model + generator_model', () => {
  const c = critiqueCandidate({
    brief: { negative_prompt: 'a, b' },
    workflow: { drift_guards: [], canon_focus: [] },
    candidate: { filename: '001.png', seed: 5 },
    activeDimensions: [],
    generatorModel: 'qwen-image:foo',
  });
  assert.equal(c.judged_by_model, RULE_BASED_JUDGE);
  assert.equal(c.generator_model, 'qwen-image:foo');
});

test('critiqueCandidate defaults generator_model to null when unknown', () => {
  const c = critiqueCandidate({
    brief: { negative_prompt: '' },
    workflow: { drift_guards: [], canon_focus: [] },
    candidate: { filename: '002.png', seed: 6 },
    activeDimensions: [],
  });
  assert.equal(c.generator_model, null);
});

test('judge ids are the expected constants', () => {
  assert.equal(HUMAN_JUDGE, 'human');
  assert.equal(RULE_BASED_JUDGE, 'rule-based:sdlab-critique-v1');
});

// ─── backward-compat: legacy manifests still load ────────────────

test('checkManifestVersion never throws — legacy manifests load (warn-and-continue)', () => {
  // No schema_version (legacy unstamped) → silent, no throw.
  assert.doesNotThrow(() => checkManifestVersion({}, 'run'));
  assert.doesNotThrow(() => checkManifestVersion({ run_id: 'r' }, 'run'));
  // Older stamped version → warns but does not throw.
  assert.doesNotThrow(() => checkManifestVersion({ schema_version: '2.2.0' }, 'run'));
  // Current version → no warn, no throw.
  assert.doesNotThrow(() => checkManifestVersion({ schema_version: SCHEMA_VERSION }, 'run'));
});
