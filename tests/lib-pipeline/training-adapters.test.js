/**
 * Unit tests for the training-adapter registry.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ADAPTER_REGISTRY,
  listAdapters,
  isRegisteredAdapter,
  loadAdapter,
} from '../../lib/training-adapters.js';
import { validateProfile } from '../../lib/training-profiles.js';

test('listAdapters returns all registered adapter ids', () => {
  const adapters = listAdapters();
  assert.ok(adapters.includes('generic-image-caption'));
  assert.ok(adapters.includes('diffusers-lora'));
  assert.ok(adapters.includes('ai-toolkit'));
  assert.equal(adapters.length, Object.keys(ADAPTER_REGISTRY).length);
});

test('isRegisteredAdapter is true for registered ids', () => {
  assert.equal(isRegisteredAdapter('generic-image-caption'), true);
  assert.equal(isRegisteredAdapter('diffusers-lora'), true);
  assert.equal(isRegisteredAdapter('ai-toolkit'), true);
});

test('loadAdapter("ai-toolkit") returns module with buildPackage', async () => {
  const adapter = await loadAdapter('ai-toolkit');
  assert.equal(typeof adapter.buildPackage, 'function');
});

test('isRegisteredAdapter is false for unknown ids', () => {
  assert.equal(isRegisteredAdapter('kohya-lora'), false);
  assert.equal(isRegisteredAdapter('typo'), false);
  assert.equal(isRegisteredAdapter(''), false);
  assert.equal(isRegisteredAdapter(undefined), false);
});

test('loadAdapter returns a module with buildPackage', async () => {
  const adapter = await loadAdapter('generic-image-caption');
  assert.equal(typeof adapter.buildPackage, 'function');
});

test('loadAdapter throws ADAPTER_NOT_REGISTERED with helpful message', async () => {
  await assert.rejects(
    () => loadAdapter('nonexistent-trainer'),
    err => {
      assert.equal(err.code, 'ADAPTER_NOT_REGISTERED');
      assert.match(err.message, /nonexistent-trainer/);
      assert.match(err.message, /generic-image-caption/);
      return true;
    }
  );
});

test('ADAPTER_REGISTRY is frozen', () => {
  assert.ok(Object.isFrozen(ADAPTER_REGISTRY));
  assert.throws(
    () => { ADAPTER_REGISTRY['evil-adapter'] = {}; },
    TypeError
  );
});

test('validateProfile rejects profiles citing unregistered adapters', () => {
  const result = validateProfile({
    profile_id: 'p1',
    label: 'p1',
    target_family: 'sdxl',
    asset_type: 'lora',
    eligible_lanes: ['portrait'],
    adapter_targets: ['diffusers-lora', 'mystery-trainer'],
  });
  assert.equal(result.valid, false);
  assert.ok(result.errors.some(e => e.includes('mystery-trainer')));
});

test('validateProfile accepts profiles with only registered adapters', () => {
  const result = validateProfile({
    profile_id: 'p1',
    label: 'p1',
    target_family: 'sdxl',
    asset_type: 'lora',
    eligible_lanes: ['portrait'],
    adapter_targets: ['diffusers-lora', 'generic-image-caption'],
  });
  assert.equal(result.valid, true);
  assert.equal(result.errors.length, 0);
});
