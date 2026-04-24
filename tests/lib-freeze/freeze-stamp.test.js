/**
 * Unit tests for lib/freeze-stamp.js.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  FREEZE_STATUSES,
  readFreezeStatus,
  freezeBlocksAction,
  freezeIsAdvisory,
  canonicalize,
  computeWatchHash,
  resolveWatchFields,
  buildFreezeBlock,
  appendOverrideToFreezeBlock,
} from '../../lib/freeze-stamp.js';

// --- readFreezeStatus ---

test('readFreezeStatus: missing block defaults to auto', () => {
  assert.equal(readFreezeStatus({}), 'auto');
  assert.equal(readFreezeStatus(null), 'auto');
  assert.equal(readFreezeStatus(undefined), 'auto');
});

test('readFreezeStatus: invalid status falls back to auto', () => {
  assert.equal(readFreezeStatus({ freeze: { status: 'nonsense' } }), 'auto');
  assert.equal(readFreezeStatus({ freeze: { status: 42 } }), 'auto');
});

test('readFreezeStatus: reads each legal status', () => {
  for (const status of FREEZE_STATUSES) {
    assert.equal(readFreezeStatus({ freeze: { status } }), status);
  }
});

// --- freezeBlocksAction / freezeIsAdvisory ---

test('freezeBlocksAction: only frozen blocks outright', () => {
  assert.equal(freezeBlocksAction('frozen'), true);
  assert.equal(freezeBlocksAction('soft-advisory'), false);
  assert.equal(freezeBlocksAction('auto'), false);
  assert.equal(freezeBlocksAction('on-canon-change'), false);
});

test('freezeIsAdvisory: only soft-advisory is advisory', () => {
  assert.equal(freezeIsAdvisory('soft-advisory'), true);
  assert.equal(freezeIsAdvisory('frozen'), false);
  assert.equal(freezeIsAdvisory('auto'), false);
});

// --- canonicalize ---

test('canonicalize: object key order is deterministic', () => {
  const a = canonicalize({ b: 1, a: 2 });
  const b = canonicalize({ a: 2, b: 1 });
  assert.equal(a, b);
  assert.equal(a, '{"a":2,"b":1}');
});

test('canonicalize: arrays preserve order', () => {
  assert.equal(canonicalize([3, 1, 2]), '[3,1,2]');
});

test('canonicalize: nulls and undefined collapse to null', () => {
  assert.equal(canonicalize(null), 'null');
  assert.equal(canonicalize(undefined), 'null');
  assert.equal(canonicalize({ a: undefined }), '{}'); // undefined values omitted
});

test('canonicalize: strings are JSON-encoded', () => {
  assert.equal(canonicalize('x"y'), '"x\\"y"');
});

// --- computeWatchHash ---

test('computeWatchHash: deterministic across runs', () => {
  const fm = { visual: { silhouette_cue: 'club-and-lion-hide' }, signature_features: ['hide', 'maned'] };
  const a = computeWatchHash(fm, ['visual.silhouette_cue', 'signature_features'], '1.0.0');
  const b = computeWatchHash(fm, ['visual.silhouette_cue', 'signature_features'], '1.0.0');
  assert.equal(a, b);
  assert.equal(a.length, 64);
});

test('computeWatchHash: changes when a watched field changes', () => {
  const fm1 = { visual: { silhouette_cue: 'club-and-lion-hide' } };
  const fm2 = { visual: { silhouette_cue: 'bow-and-dog' } };
  const h1 = computeWatchHash(fm1, ['visual.silhouette_cue'], '1.0.0');
  const h2 = computeWatchHash(fm2, ['visual.silhouette_cue'], '1.0.0');
  assert.notEqual(h1, h2);
});

test('computeWatchHash: changes when schema version changes', () => {
  const fm = { visual: { silhouette_cue: 'x' } };
  const h1 = computeWatchHash(fm, ['visual.silhouette_cue'], '1.0.0');
  const h2 = computeWatchHash(fm, ['visual.silhouette_cue'], '2.0.0');
  assert.notEqual(h1, h2);
});

test('computeWatchHash: unchanged when a non-watched field changes', () => {
  const fm1 = { visual: { silhouette_cue: 'x' }, narrative: { role: 'A' } };
  const fm2 = { visual: { silhouette_cue: 'x' }, narrative: { role: 'B' } };
  const h1 = computeWatchHash(fm1, ['visual.silhouette_cue'], '1.0.0');
  const h2 = computeWatchHash(fm2, ['visual.silhouette_cue'], '1.0.0');
  assert.equal(h1, h2);
});

test('computeWatchHash: missing watched field hashes as null', () => {
  const fm = { visual: {} };
  const h = computeWatchHash(fm, ['visual.silhouette_cue'], '1.0.0');
  // Should still produce a hash, not throw.
  assert.equal(h.length, 64);
});

// --- resolveWatchFields ---

test('resolveWatchFields: entry override wins', () => {
  const fm = { freeze: { watch_fields: ['visual.silhouette_cue'] } };
  const resolved = resolveWatchFields(fm, 'monster.schema.json', {
    freeze_watch_defaults: { 'monster.schema.json': ['signature_features'] },
  });
  assert.deepEqual(resolved, ['visual.silhouette_cue']);
});

test('resolveWatchFields: config default when no entry override', () => {
  const fm = { freeze: { status: 'frozen' } };
  const resolved = resolveWatchFields(fm, 'monster.schema.json', {
    freeze_watch_defaults: { 'monster.schema.json': ['signature_features'] },
  });
  assert.deepEqual(resolved, ['signature_features']);
});

test('resolveWatchFields: empty array when neither is present', () => {
  assert.deepEqual(resolveWatchFields({}, 'monster.schema.json', {}), []);
});

// --- buildFreezeBlock ---

test('buildFreezeBlock: writes required and optional fields', () => {
  const block = buildFreezeBlock({
    status: 'frozen',
    lockedAtBuild: 'abc123',
    frozenBy: 'mike',
    frozenReason: 'hero moment',
    watchFields: ['visual.silhouette_cue'],
  });
  assert.equal(block.status, 'frozen');
  assert.equal(block.locked_at_build, 'abc123');
  assert.equal(block.frozen_by, 'mike');
  assert.equal(block.frozen_reason, 'hero moment');
  assert.deepEqual(block.watch_fields, ['visual.silhouette_cue']);
});

test('buildFreezeBlock: preserves existing overrides[] history', () => {
  const prior = [{ at: 'x', by: 'y', reason: 'z' }];
  const block = buildFreezeBlock({ status: 'frozen', overrides: prior });
  assert.deepEqual(block.overrides, prior);
});

// --- appendOverrideToFreezeBlock ---

test('appendOverrideToFreezeBlock: appends to empty history', () => {
  const next = appendOverrideToFreezeBlock({ status: 'frozen' }, { at: 'x', by: 'y', reason: 'z' });
  assert.equal(next.overrides.length, 1);
  assert.equal(next.overrides[0].by, 'y');
});

test('appendOverrideToFreezeBlock: preserves prior overrides', () => {
  const prior = { status: 'frozen', overrides: [{ at: 'a', by: 'b', reason: 'c' }] };
  const next = appendOverrideToFreezeBlock(prior, { at: 'x', by: 'y', reason: 'z' });
  assert.equal(next.overrides.length, 2);
  assert.equal(next.overrides[0].by, 'b');
  assert.equal(next.overrides[1].by, 'y');
});
