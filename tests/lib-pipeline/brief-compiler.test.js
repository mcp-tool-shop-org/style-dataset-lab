/**
 * Unit tests for brief-compiler pure helpers:
 *   - canonicalize (recursive key sort → fingerprint determinism)
 *   - buildRuntimePlan (?? honors 0 / empty string overrides)
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canonicalize, buildRuntimePlan } from '../../lib/brief-compiler.js';

test('canonicalize: same input → same stringified output', () => {
  const a = { b: 1, a: 2, c: { y: 'y', x: 'x' } };
  const b = { a: 2, b: 1, c: { y: 'y', x: 'x' } };
  assert.equal(JSON.stringify(canonicalize(a)), JSON.stringify(canonicalize(b)));
});

test('canonicalize: nested key reorder produces identical fingerprint', () => {
  const a = { prompt_strategy: { structure: 's', style_prefix: ['a'] }, runtime_defaults: { steps: 30, cfg: 6.5 } };
  const b = { runtime_defaults: { cfg: 6.5, steps: 30 }, prompt_strategy: { style_prefix: ['a'], structure: 's' } };
  assert.equal(JSON.stringify(canonicalize(a)), JSON.stringify(canonicalize(b)));
});

test('canonicalize: arrays keep their order', () => {
  const a = { list: [3, 1, 2] };
  const out = canonicalize(a);
  assert.deepEqual(out.list, [3, 1, 2]);
});

test('canonicalize: primitives and null pass through', () => {
  assert.equal(canonicalize(null), null);
  assert.equal(canonicalize(42), 42);
  assert.equal(canonicalize('x'), 'x');
});

test('buildRuntimePlan: overrides of 0 are preserved (not coerced to defaults)', () => {
  const workflow = { runtime_defaults: { steps: 30, cfg: 6.5 } };
  const plan = buildRuntimePlan(workflow, { steps: 0, cfg: 0 });
  assert.equal(plan.steps, 0, 'steps=0 override must be honored');
  assert.equal(plan.cfg, 0, 'cfg=0 override must be honored');
});

test('buildRuntimePlan: empty string override is preserved', () => {
  const workflow = { runtime_defaults: { sampler: 'dpmpp_2m' } };
  const plan = buildRuntimePlan(workflow, { sampler: '' });
  assert.equal(plan.sampler, '', 'empty-string sampler override must be honored');
});

test('buildRuntimePlan: undefined override falls through to default', () => {
  const workflow = { runtime_defaults: { steps: 30 } };
  const plan = buildRuntimePlan(workflow, { steps: undefined });
  assert.equal(plan.steps, 30);
});

test('buildRuntimePlan: missing override and default uses hardcoded fallback', () => {
  const plan = buildRuntimePlan({}, {});
  assert.equal(plan.width, 1024);
  assert.equal(plan.sampler, 'dpmpp_2m');
});
