/**
 * Unit tests for batch-compiler.applySlotDelta:
 *   - token-exact negative-prompt dedup (no substring false-positives)
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applySlotDelta } from '../../lib/batch-compiler.js';

function baseBrief(negative = 'blur, lowres') {
  return {
    prompt: 'a portrait',
    negative_prompt: negative,
    runtime_plan: { steps: 30 },
  };
}

test('applySlotDelta: adding "motion blur" when "blur" is already present does NOT suppress it', () => {
  const slot = {
    slot_id: 's1',
    label: 'test',
    negative_additions: ['motion blur'],
  };
  const out = applySlotDelta(baseBrief('blur, lowres'), slot);
  assert.match(out.negative_prompt, /motion blur/, 'motion blur must be appended even when blur is present');
});

test('applySlotDelta: exact-match duplicate is deduped', () => {
  const slot = {
    slot_id: 's1',
    label: 'test',
    negative_additions: ['blur'],
  };
  const out = applySlotDelta(baseBrief('blur, lowres'), slot);
  // Count tokens equal to "blur" (trimmed, case-insensitive)
  const tokens = out.negative_prompt.split(',').map(s => s.trim().toLowerCase());
  const blurCount = tokens.filter(t => t === 'blur').length;
  assert.equal(blurCount, 1, 'exact duplicate "blur" must not be appended a second time');
});

test('applySlotDelta: case-insensitive exact dedup', () => {
  const slot = {
    slot_id: 's1',
    label: 'test',
    negative_additions: ['BLUR'],
  };
  const out = applySlotDelta(baseBrief('blur, lowres'), slot);
  assert.equal(out.negative_prompt, 'blur, lowres', 'BLUR should dedup against existing blur');
});

test('applySlotDelta: empty-string tokens in existing negative do not poison dedup', () => {
  const slot = {
    slot_id: 's1',
    label: 'test',
    negative_additions: ['motion blur', 'watermark'],
  };
  // Trailing comma produces an empty token after split
  const out = applySlotDelta(baseBrief('blur, lowres,'), slot);
  assert.match(out.negative_prompt, /motion blur/);
  assert.match(out.negative_prompt, /watermark/);
});

test('applySlotDelta: base brief is not mutated', () => {
  const base = baseBrief('blur');
  const slot = { slot_id: 's1', label: 'test', negative_additions: ['motion blur'] };
  applySlotDelta(base, slot);
  assert.equal(base.negative_prompt, 'blur', 'applySlotDelta must not mutate the base brief');
});
