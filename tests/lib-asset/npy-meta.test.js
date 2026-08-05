/**
 * lib/npy-meta.js — .npy header proofs for declared-array channels.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseNpyHeader } from '../../lib/npy-meta.js';
import { encodeNpyBool } from './fixtures/make-asset.js';

test('parseNpyHeader reads dtype/shape/order from a v1 bool array', () => {
  const buf = encodeNpyBool([8, 8], new Array(64).fill(0));
  const h = parseNpyHeader(buf, 'coverage.npy');
  assert.equal(h.dtype, '|b1');
  assert.equal(h.fortranOrder, false);
  assert.deepEqual(h.shape, [8, 8]);
  assert.equal(h.version, '1.0');
  assert.equal(buf.length, h.dataOffset + 64, 'declared header length must land exactly at the data');
});

test('parseNpyHeader handles 1-D shapes with trailing commas', () => {
  const buf = encodeNpyBool([5], [1, 0, 1, 0, 1]);
  assert.deepEqual(parseNpyHeader(buf).shape, [5]);
});

test('parseNpyHeader reads a v2 header (4-byte length)', () => {
  const dict = "{'descr': '<i2', 'fortran_order': True, 'shape': (3, 2), }\n";
  const buf = Buffer.alloc(12 + dict.length);
  buf.write('\x93NUMPY', 0, 'latin1');
  buf[6] = 2; buf[7] = 0;
  buf.writeUInt32LE(dict.length, 8);
  buf.write(dict, 12, 'latin1');
  const h = parseNpyHeader(buf);
  assert.equal(h.dtype, '<i2');
  assert.equal(h.fortranOrder, true);
  assert.deepEqual(h.shape, [3, 2]);
});

test('parseNpyHeader refuses a bad magic', () => {
  assert.throws(() => parseNpyHeader(Buffer.from('NOTNUMPYxxxx')), (err) => err.code === 'NPY_INVALID');
});

test('parseNpyHeader refuses a truncated header', () => {
  const buf = encodeNpyBool([8, 8], new Array(64).fill(0)).subarray(0, 20);
  assert.throws(() => parseNpyHeader(buf), (err) => err.code === 'NPY_INVALID');
});

test('parseNpyHeader refuses an unsupported format version', () => {
  const buf = Buffer.from(`\x93NUMPY${String.fromCharCode(9)}${String.fromCharCode(0)}xx`, 'latin1');
  assert.throws(() => parseNpyHeader(buf), (err) => err.code === 'NPY_INVALID' && /version 9/.test(err.message));
});
