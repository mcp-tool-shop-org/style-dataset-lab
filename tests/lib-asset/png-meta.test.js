/**
 * lib/png-meta.js — the structural PNG reader every asset-lane proof rests
 * on. If this lies about a file, every downstream "proof" is theater, so it
 * is tested against an independent encoder (fixtures/make-png.js), including
 * every scanline filter and every refusal path.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parsePngMeta, decodePng } from '../../lib/png-meta.js';
import { encodePng, forwardFilter } from './fixtures/make-png.js';

test('parsePngMeta reads IHDR + PLTE without decoding pixels', () => {
  const palette = [[10, 20, 30], [200, 100, 50]];
  const buf = encodePng({ width: 4, height: 2, colorType: 3, data: [0, 1, 0, 1, 1, 0, 1, 0], palette });
  const meta = parsePngMeta(buf, 'zones.png');
  assert.equal(meta.width, 4);
  assert.equal(meta.height, 2);
  assert.equal(meta.colorType, 3);
  assert.equal(meta.colorTypeName, 'indexed');
  assert.equal(meta.interlaced, false);
  assert.deepEqual(meta.palette, palette);
});

test('decodePng roundtrips an RGBA image byte-for-byte', () => {
  const data = new Uint8Array([
    255, 0, 0, 255,   0, 255, 0, 128,
    0, 0, 255, 0,     7, 8, 9, 10,
  ]);
  const buf = encodePng({ width: 2, height: 2, colorType: 6, data });
  const img = decodePng(buf, 't.png');
  assert.equal(img.channels, 4);
  assert.deepEqual([...img.data], [...data]);
});

test('decodePng roundtrips grayscale and RGB', () => {
  const gray = encodePng({ width: 3, height: 1, colorType: 0, data: [0, 127, 255] });
  assert.deepEqual([...decodePng(gray).data], [0, 127, 255]);

  const rgbData = [1, 2, 3, 4, 5, 6];
  const rgb = encodePng({ width: 2, height: 1, colorType: 2, data: rgbData });
  assert.deepEqual([...decodePng(rgb).data], rgbData);
});

test('decodePng returns palette INDICES for indexed images, plus the PLTE', () => {
  const palette = [[9, 9, 9], [1, 2, 3], [4, 5, 6]];
  const indices = [2, 1, 0, 1];
  const buf = encodePng({ width: 2, height: 2, colorType: 3, data: indices, palette });
  const img = decodePng(buf);
  assert.deepEqual([...img.data], indices);
  assert.deepEqual(img.palette, palette);
});

test('decodePng unpacks sub-byte indexed bit depths (4-bit)', () => {
  const palette = [[0, 0, 0], [255, 255, 255], [7, 7, 7]];
  const indices = [0, 1, 2, 1, 2, 0]; // width 3 → 2 bytes per row at 4bpp
  const buf = encodePng({ width: 3, height: 2, colorType: 3, bitDepth: 4, data: indices, palette });
  const img = decodePng(buf);
  assert.deepEqual([...img.data], indices);
});

test('decodePng unpacks 1-bit indexed images', () => {
  const palette = [[0, 0, 0], [255, 255, 255]];
  const indices = [1, 0, 1, 0, 1, 0, 1, 0, 0, 1]; // width 10 → 2 bytes per row
  const buf = encodePng({ width: 10, height: 1, colorType: 3, bitDepth: 1, data: indices, palette });
  assert.deepEqual([...decodePng(buf).data], indices);
});

test('decodePng inverts every scanline filter (Sub, Up, Average, Paeth)', () => {
  // A gradient-ish RGB image where each filter produces distinct residuals.
  const width = 4, height = 5, channels = 3;
  const samples = new Uint8Array(width * height * channels);
  for (let i = 0; i < samples.length; i++) samples[i] = (i * 37 + (i % 7) * 11) & 0xff;
  const scanlines = forwardFilter(samples, width, height, channels, [1, 2, 3, 4, 0]);
  const buf = encodePng({ width, height, colorType: 2, scanlines });
  const img = decodePng(buf, 'filters.png');
  assert.deepEqual([...img.data], [...samples], 'unfiltered pixels must equal the originals for filters 1/2/3/4/0');
});

test('decodePng refuses interlaced PNGs with a structured error', () => {
  const buf = encodePng({ width: 2, height: 2, colorType: 6, data: new Uint8Array(16), interlace: 1 });
  assert.throws(() => decodePng(buf, 'i.png'), (err) => err.code === 'PNG_UNSUPPORTED' && /interlaced/i.test(err.message));
});

test('decodePng refuses 16-bit color with a structured error', () => {
  // Hand-build: encoder only does 8-bit, so lie in the IHDR via bitDepth.
  const buf = encodePng({ width: 1, height: 1, colorType: 2, bitDepth: 16, data: [0, 0, 0] });
  assert.throws(() => decodePng(buf), (err) => err.code === 'PNG_UNSUPPORTED' && /bit depth 16/.test(err.message));
});

test('parsePngMeta refuses a non-PNG buffer', () => {
  assert.throws(() => parsePngMeta(Buffer.from('definitely not a png')), (err) => err.code === 'PNG_INVALID');
});

test('decodePng reports truncated pixel data instead of returning garbage', () => {
  const good = encodePng({ width: 4, height: 4, colorType: 6, data: new Uint8Array(64).fill(9) });
  const truncated = good.subarray(0, good.length - 24); // clip into IDAT/IEND
  assert.throws(() => decodePng(truncated), (err) => err.code === 'PNG_INVALID');
});
