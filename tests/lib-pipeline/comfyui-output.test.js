/**
 * Unit tests for pickOutputImage — deterministic SaveImage selection
 * across multi-save-node ComfyUI workflows.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pickOutputImage } from '../../lib/comfyui-output.js';

function makeOutputs(entries) {
  // entries: array of [nodeId, filename] tuples — order matters
  const out = {};
  for (const [nodeId, filename, subfolder = ''] of entries) {
    out[nodeId] = { images: [{ filename, subfolder }] };
  }
  return out;
}

test('returns null for empty / missing outputs', () => {
  assert.equal(pickOutputImage(null), null);
  assert.equal(pickOutputImage(undefined), null);
  assert.equal(pickOutputImage({}), null);
  assert.equal(pickOutputImage({ '5': { images: [] } }), null);
});

test('honors preferNodeId when that node produced an image', () => {
  const outputs = makeOutputs([['3', 'preview.png'], ['9', 'final.png']]);
  const picked = pickOutputImage(outputs, { preferNodeId: '9' });
  assert.equal(picked.filename, 'final.png');
  assert.equal(picked.nodeId, '9');
});

test('preferNodeId accepts numeric input', () => {
  const outputs = makeOutputs([['3', 'preview.png'], ['9', 'final.png']]);
  const picked = pickOutputImage(outputs, { preferNodeId: 9 });
  assert.equal(picked.filename, 'final.png');
});

test('falls back to highest numeric node id when hint does not match', () => {
  const outputs = makeOutputs([['3', 'preview.png'], ['9', 'final.png']]);
  const picked = pickOutputImage(outputs, { preferNodeId: '99' });
  assert.equal(picked.filename, 'final.png');
  assert.equal(picked.nodeId, '9');
});

test('falls back to highest numeric node id with no hint', () => {
  const outputs = makeOutputs([['9', 'final.png'], ['3', 'preview.png']]);
  const picked = pickOutputImage(outputs);
  assert.equal(picked.filename, 'final.png');
  assert.equal(picked.nodeId, '9');
});

test('does not depend on insertion order of outputs', () => {
  const a = makeOutputs([['3', 'preview.png'], ['9', 'final.png']]);
  const b = makeOutputs([['9', 'final.png'], ['3', 'preview.png']]);
  assert.equal(pickOutputImage(a).nodeId, pickOutputImage(b).nodeId);
});

test('preserves subfolder', () => {
  const outputs = makeOutputs([['9', 'final.png', 'my/subdir']]);
  const picked = pickOutputImage(outputs);
  assert.equal(picked.subfolder, 'my/subdir');
});

test('non-numeric ids fall back to first iteration entry', () => {
  const outputs = {
    save_a: { images: [{ filename: 'a.png', subfolder: '' }] },
    save_b: { images: [{ filename: 'b.png', subfolder: '' }] },
  };
  const picked = pickOutputImage(outputs);
  assert.ok(['a.png', 'b.png'].includes(picked.filename));
});

test('skips nodes without images even if listed first', () => {
  const outputs = {
    '1': { images: [] },
    '2': { /* no images field */ },
    '7': { images: [{ filename: 'real.png', subfolder: '' }] },
  };
  const picked = pickOutputImage(outputs);
  assert.equal(picked.filename, 'real.png');
  assert.equal(picked.nodeId, '7');
});
