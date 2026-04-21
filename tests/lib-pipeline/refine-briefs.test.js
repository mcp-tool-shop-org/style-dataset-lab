/**
 * Unit tests for refine-briefs — PB-007 defensive negative coercion.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderRefinedNegative } from '../../lib/refine-briefs.js';

test('renderRefinedNegative: undefined parentNegative does not throw', () => {
  const out = renderRefinedNegative(undefined, { suppress: ['blur'] });
  assert.equal(out, 'blur');
});

test('renderRefinedNegative: null parentNegative does not throw', () => {
  const out = renderRefinedNegative(null, { suppress: ['blur', 'lowres'] });
  assert.equal(out, 'blur, lowres');
});

test('renderRefinedNegative: empty string parent is preserved when no additions', () => {
  const out = renderRefinedNegative('', { suppress: [] });
  assert.equal(out, '');
});

test('renderRefinedNegative: non-string parent coerces to empty', () => {
  const out = renderRefinedNegative(42, { suppress: ['x'] });
  assert.equal(out, 'x');
});

test('renderRefinedNegative: existing parent extended with new suppressions', () => {
  const out = renderRefinedNegative('blur, lowres', { suppress: ['extra fingers'] });
  assert.equal(out, 'blur, lowres, extra fingers');
});

test('renderRefinedNegative: duplicate token skipped case-insensitively', () => {
  const out = renderRefinedNegative('blur, lowres', { suppress: ['BLUR'] });
  assert.equal(out, 'blur, lowres');
});
