/**
 * lib/asset-masks.js — the ported palette gate and class-share measurement.
 *
 * The gate port is formula-faithful to facet's tools/palette_gate.py; these
 * tests hold the port to the properties that made the original load-bearing:
 * the chroma floor (hue is undefined at low chroma), wraparound hue bands,
 * the two-number report (diagnostic % vs load-bearing blob), 4-connectivity,
 * and measurement inside the EXACT silhouette only.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  srgbToLab,
  paletteGate,
  classShares,
  largestComponent4,
  silhouetteToMask,
} from '../../lib/asset-masks.js';

// ─── tiny decoded-image constructors (the lib/png-meta.js output shape) ──

function rgbImage(width, height, pixels /* [[r,g,b],...] row-major */) {
  const data = new Uint8Array(width * height * 3);
  pixels.forEach((p, i) => { data[i * 3] = p[0]; data[i * 3 + 1] = p[1]; data[i * 3 + 2] = p[2]; });
  return { width, height, colorType: 2, bitDepth: 8, channels: 3, data, palette: null };
}

function rgbaImage(width, height, pixels /* [[r,g,b,a],...] */) {
  const data = new Uint8Array(width * height * 4);
  pixels.forEach((p, i) => { data.set(p, i * 4); });
  return { width, height, colorType: 6, bitDepth: 8, channels: 4, data, palette: null };
}

function grayImage(width, height, values) {
  return { width, height, colorType: 0, bitDepth: 8, channels: 1, data: Uint8Array.from(values), palette: null };
}

const GRAY = [120, 120, 120];   // C* ≈ 0 — below any sane floor
const BLUE = [40, 60, 200];     // high chroma, far from the warm band
const RED = [180, 40, 40];      // high chroma, inside a [0,100]° band

const WARM_PALETTE = {
  min_chroma: 12.0,
  allowed_bands: [{ name: 'warm', hue_deg: [0, 100] }],
  gate: { max_offpalette_pct: null, max_offpalette_blob_px: 4 },
};

test('srgbToLab: white is L≈100 with a,b≈0; black is L=0', () => {
  const [L, a, b] = srgbToLab(255, 255, 255);
  assert.ok(Math.abs(L - 100) < 0.1, `white L was ${L}`);
  assert.ok(Math.abs(a) < 0.5 && Math.abs(b) < 0.5, `white a/b were ${a}/${b}`);
  const [L0] = srgbToLab(0, 0, 0);
  assert.ok(Math.abs(L0) < 0.001);
});

test('the chroma floor is load-bearing: neutral gray never counts as off-palette', () => {
  const img = rgbImage(4, 4, Array(16).fill(GRAY));
  const sil = grayImage(4, 4, Array(16).fill(255));
  const r = paletteGate(img, sil, WARM_PALETTE, 'gray');
  assert.equal(r.offpalette_px, 0);
  assert.equal(r.largest_blob_px, 0);
  assert.equal(r.pass, true);
  assert.equal(r.figure_px, 16);
  assert.equal(r.dominant, null);
});

test('an off-palette blob is measured by its largest 4-connected component and gates on it', () => {
  // 6x4 gray figure with a 2x3 blue block (6 px, one blob) at rows 1-2, cols 1-3.
  const pixels = [];
  for (let y = 0; y < 4; y++) {
    for (let x = 0; x < 6; x++) {
      const inBlob = y >= 1 && y <= 2 && x >= 1 && x <= 3;
      pixels.push(inBlob ? BLUE : GRAY);
    }
  }
  const img = rgbImage(6, 4, pixels);
  const sil = grayImage(6, 4, Array(24).fill(255));

  const r = paletteGate(img, sil, WARM_PALETTE, 'blob');
  assert.equal(r.offpalette_px, 6);
  assert.equal(r.largest_blob_px, 6);
  assert.equal(r.offpalette_pct, 25);
  assert.equal(r.pass, false, 'blob 6 must fail a max_blob of 4');
  assert.equal(r.withdrawn_pct_bound, true, 'null pct bound is reported as withdrawn');
  assert.ok(r.dominant, 'a failure must be diagnosable, not just flagged');
  const [mr, mg, mb] = r.dominant.median_rgb;
  assert.ok(mb > mr && mb > mg, `dominant median_rgb should be blue-ish, got ${r.dominant.median_rgb}`);

  const loose = { ...WARM_PALETTE, gate: { max_offpalette_pct: null, max_offpalette_blob_px: 8 } };
  assert.equal(paletteGate(img, sil, loose, 'blob').pass, true, 'blob 6 passes a max_blob of 8');
});

test('the withdrawn %-bound gates nothing, but an explicitly declared one gates', () => {
  const pixels = Array(8).fill(GRAY);
  pixels[0] = BLUE; // 1 of 8 figure px off-palette = 12.5%
  const img = rgbImage(8, 1, pixels);
  const sil = grayImage(8, 1, Array(8).fill(255));

  const withdrawn = { ...WARM_PALETTE, gate: { max_offpalette_pct: null, max_offpalette_blob_px: 4 } };
  assert.equal(paletteGate(img, sil, withdrawn).pass, true);

  const bounded = { ...WARM_PALETTE, gate: { max_offpalette_pct: 10, max_offpalette_blob_px: 4 } };
  const r = paletteGate(img, sil, bounded);
  assert.equal(r.withdrawn_pct_bound, false);
  assert.equal(r.pass, false, '12.5% must fail an explicit 10% bound');
});

test('hue bands wrap around 0° when lo > hi (the palette_gate.py band semantics)', () => {
  // Blue sits near hue ~306°; a wraparound band [296, 20] contains it,
  // while green (~136°) stays outside.
  const GREEN = [40, 200, 40];
  const img = rgbImage(2, 1, [BLUE, GREEN]);
  const sil = grayImage(2, 1, [255, 255]);
  const palette = {
    min_chroma: 12.0,
    allowed_bands: [{ name: 'wrap', hue_deg: [296, 20] }],
    gate: { max_offpalette_pct: null, max_offpalette_blob_px: 0 },
  };
  const r = paletteGate(img, sil, palette, 'wrap');
  assert.equal(r.offpalette_px, 1, 'only green is off-palette; blue is inside the wrapped band');
});

test('pixels outside the exact silhouette are never measured (E01/E08-A2)', () => {
  // Blue everywhere, but the silhouette covers only 2 px.
  const img = rgbImage(4, 1, [BLUE, BLUE, BLUE, BLUE]);
  const sil = grayImage(4, 1, [255, 255, 0, 0]);
  const r = paletteGate(img, sil, WARM_PALETTE);
  assert.equal(r.figure_px, 2);
  assert.equal(r.offpalette_px, 2, 'off-palette counts only inside the silhouette');
});

test('paletteGate refuses a silhouette whose dimensions do not match the render', () => {
  const img = rgbImage(2, 2, Array(4).fill(GRAY));
  const sil = grayImage(3, 1, [255, 255, 255]);
  assert.throws(() => paletteGate(img, sil, WARM_PALETTE, 'mismatch'), (err) => err.code === 'ASSET_MASK_MISMATCH');
});

test('silhouetteToMask refuses a non-grayscale mask and binarizes at >127', () => {
  assert.throws(() => silhouetteToMask(rgbImage(1, 1, [GRAY])), (err) => err.code === 'ASSET_ENCODING_MISMATCH');
  const mask = silhouetteToMask(grayImage(4, 1, [0, 127, 128, 255]));
  assert.deepEqual([...mask], [0, 0, 1, 1]);
});

test('largestComponent4 does not connect diagonals (4-connectivity, like scipy label defaults)', () => {
  // Two pixels touching only diagonally are two components of size 1.
  const mask = Uint8Array.from([1, 0, 0, 1]);
  assert.equal(largestComponent4(mask, 2, 2), 1);
  // An L of 3 connected orthogonally is one component.
  const ell = Uint8Array.from([1, 0, 1, 1]);
  assert.equal(largestComponent4(ell, 2, 2), 3);
});

test('classShares: exact matching under filter "nearest", honest unclassified for anything else', () => {
  const A = [0, 255, 0];
  const B = [255, 0, 255];
  const NEAR_A = [2, 253, 1];
  const img = rgbaImage(4, 1, [[...A, 255], [...A, 255], [...B, 255], [...NEAR_A, 255]]);
  const sil = grayImage(4, 1, [255, 255, 255, 255]);
  const decl = { palette: [{ name: 'a', rgb: A }, { name: 'b', rgb: B }], filter: 'nearest' };

  const r = classShares(img, sil, decl, 'matclass');
  assert.equal(r.figure_px, 4);
  assert.equal(r.classes.a.px, 2);
  assert.equal(r.classes.b.px, 1);
  assert.equal(r.unclassified.px, 1, 'a nearly-right color is NOT a class under nearest — no silent tolerance');
  assert.equal(r.classes.a.share, 50);
});

test('classShares: linear filter classifies within the declared tolerance and no further', () => {
  const A = [0, 255, 0];
  const NEAR_A = [2, 253, 1];
  const FAR = [90, 90, 90];
  const img = rgbaImage(3, 1, [[...A, 255], [...NEAR_A, 255], [...FAR, 255]]);
  const sil = grayImage(3, 1, [255, 255, 255]);

  const tolerant = { palette: [{ name: 'a', rgb: A }], filter: 'linear', classification_tolerance: 5 };
  const r1 = classShares(img, sil, tolerant);
  assert.equal(r1.classes.a.px, 2, 'NEAR_A is within tolerance 5');
  assert.equal(r1.unclassified.px, 1, 'FAR is beyond it');

  const strict = { palette: [{ name: 'a', rgb: A }], filter: 'linear', classification_tolerance: 1 };
  const r2 = classShares(img, sil, strict);
  assert.equal(r2.classes.a.px, 1);
  assert.equal(r2.unclassified.px, 2);
});

test('classShares excludes fully transparent pixels (background, not class)', () => {
  const A = [0, 255, 0];
  const img = rgbaImage(3, 1, [[...A, 255], [...A, 0], [0, 0, 0, 0]]);
  const sil = grayImage(3, 1, [255, 255, 255]);
  const decl = { palette: [{ name: 'a', rgb: A }], filter: 'nearest' };
  const r = classShares(img, sil, decl);
  assert.equal(r.figure_px, 1, 'alpha-0 pixels are not figure even inside the silhouette');
  assert.equal(r.classes.a.px, 1);
});
