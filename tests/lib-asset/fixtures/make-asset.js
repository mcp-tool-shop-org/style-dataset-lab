/**
 * Degenerate asset fixture — the second subject the schema is born with.
 *
 * The brand lesson (docs/asset-lane-kickoff.md): two subjects from birth,
 * or the schema grows a W3-shaped bump you sand off later. This builder
 * materializes a trivial-but-complete asset export — a 12x12 "totem" with
 * two renders, one texture-space categorical channel, one render-space
 * categorical channel, silhouettes, and one conditioning pair — into a tmp
 * directory, with a mutator hook so tests can produce every violation class
 * from the same valid baseline.
 *
 * Geometry (12x12, background alpha 0):
 *   - figure: rows 2..9, cols 3..8 — low-chroma gray rgb(120,120,120)
 *     (C* ~0, below any sane chroma floor → never off-palette)
 *   - accent: rows 4..5, cols 5..6 — rgb(180,40,40), high chroma, hue well
 *     inside the declared [0,100]° band → in-palette
 *   - optional blue patch (bluePatchOn): rows 6..8, cols 4..5 —
 *     rgb(40,60,200), high chroma, hue far outside the band → a 6px
 *     off-palette 4-connected blob, for gate-failure tests
 */

import { mkdirSync, writeFileSync } from 'node:fs';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { encodePng } from './make-png.js';

export const TOTEM = {
  W: 12,
  H: 12,
  FIGURE: { r0: 2, r1: 9, c0: 3, c1: 8 },
  ACCENT: { r0: 4, r1: 5, c0: 5, c1: 6 },
  BLUE: { r0: 6, r1: 8, c0: 4, c1: 5 },
  GRAY: [120, 120, 120],
  RED: [180, 40, 40],
  BLUE_RGB: [40, 60, 200],
  CLASS_A: [0, 255, 0],
  CLASS_B: [255, 0, 255],
  ZONES_PALETTE: [[10, 20, 30], [200, 100, 50]],
};

function inRect(rect, y, x) {
  return y >= rect.r0 && y <= rect.r1 && x >= rect.c0 && x <= rect.c1;
}

function renderRgba({ bluePatch = false } = {}) {
  const { W, H, FIGURE, ACCENT, BLUE, GRAY, RED, BLUE_RGB } = TOTEM;
  const data = new Uint8Array(W * H * 4);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const o = (y * W + x) * 4;
      if (!inRect(FIGURE, y, x)) continue; // transparent background
      let rgb = GRAY;
      if (inRect(ACCENT, y, x)) rgb = RED;
      if (bluePatch && inRect(BLUE, y, x)) rgb = BLUE_RGB;
      data[o] = rgb[0]; data[o + 1] = rgb[1]; data[o + 2] = rgb[2]; data[o + 3] = 255;
    }
  }
  return encodePng({ width: W, height: H, colorType: 6, data });
}

function silhouetteGray() {
  const { W, H, FIGURE } = TOTEM;
  const data = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      data[y * W + x] = inRect(FIGURE, y, x) ? 255 : 0;
    }
  }
  return encodePng({ width: W, height: H, colorType: 0, data });
}

function matclassRgba() {
  const { W, H, FIGURE, ACCENT, CLASS_A, CLASS_B } = TOTEM;
  const data = new Uint8Array(W * H * 4);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const o = (y * W + x) * 4;
      if (!inRect(FIGURE, y, x)) continue;
      const rgb = inRect(ACCENT, y, x) ? CLASS_B : CLASS_A;
      data[o] = rgb[0]; data[o + 1] = rgb[1]; data[o + 2] = rgb[2]; data[o + 3] = 255;
    }
  }
  return encodePng({ width: W, height: H, colorType: 6, data });
}

function clayGray() {
  const { W, H, FIGURE } = TOTEM;
  const data = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      data[y * W + x] = inRect(FIGURE, y, x) ? 128 : 0;
    }
  }
  return encodePng({ width: W, height: H, colorType: 0, data });
}

function zonesIndexed({ extraPlteEntry = false } = {}) {
  const palette = extraPlteEntry
    ? [...TOTEM.ZONES_PALETTE, [9, 9, 9]]
    : TOTEM.ZONES_PALETTE;
  const data = new Uint8Array(8 * 8);
  for (let i = 0; i < 64; i++) data[i] = i < 32 ? 0 : 1;
  return encodePng({ width: 8, height: 8, colorType: 3, bitDepth: 8, data, palette });
}

/** Minimal .npy v1 writer (bool array). */
export function encodeNpyBool(shape, values) {
  const dictBody = `{'descr': '|b1', 'fortran_order': False, 'shape': (${shape.join(', ')}${shape.length === 1 ? ',' : ''}), }`;
  let header = dictBody;
  const baseLen = 10; // magic(6) + version(2) + len(2)
  const pad = 64 - ((baseLen + header.length + 1) % 64);
  header = header + ' '.repeat(pad) + '\n';
  const buf = Buffer.alloc(baseLen + header.length + values.length);
  buf.write('\x93NUMPY', 0, 'latin1');
  buf[6] = 1; buf[7] = 0;
  buf.writeUInt16LE(header.length, 8);
  buf.write(header, 10, 'latin1');
  for (let i = 0; i < values.length; i++) buf[10 + header.length + i] = values[i] ? 1 : 0;
  return buf;
}

/**
 * Materialize the degenerate asset export into a fresh tmp directory.
 *
 * @param {Object} [opts]
 * @param {boolean} [opts.bluePatchOnR0] — off-palette blob on render r0
 * @param {boolean} [opts.bluePatchOnBoth] — off-palette blob on both renders
 * @param {boolean} [opts.withNpy] — add a texture-space npy channel
 * @param {Function} [opts.mutate] — (manifest) => void, applied before write
 * @returns {{dir:string, manifest:Object}}
 */
export function writeDegenerateAsset(opts = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'sdlab-asset-fixture-'));
  mkdirSync(join(dir, 'renders'), { recursive: true });
  mkdirSync(join(dir, 'sil'), { recursive: true });
  mkdirSync(join(dir, 'channels'), { recursive: true });
  mkdirSync(join(dir, 'matclass'), { recursive: true });
  mkdirSync(join(dir, 'clay'), { recursive: true });

  const blueR0 = Boolean(opts.bluePatchOnR0 || opts.bluePatchOnBoth);
  const blueR180 = Boolean(opts.bluePatchOnBoth);

  writeFileSync(join(dir, 'renders', 'r0.png'), renderRgba({ bluePatch: blueR0 }));
  writeFileSync(join(dir, 'renders', 'r180.png'), renderRgba({ bluePatch: blueR180 }));
  writeFileSync(join(dir, 'sil', 'r0.png'), silhouetteGray());
  writeFileSync(join(dir, 'sil', 'r180.png'), silhouetteGray());
  writeFileSync(join(dir, 'channels', 'zones.png'), zonesIndexed(opts));
  writeFileSync(join(dir, 'matclass', 'r0.png'), matclassRgba());
  writeFileSync(join(dir, 'matclass', 'r180.png'), matclassRgba());
  writeFileSync(join(dir, 'clay', 'r0.png'), clayGray());
  if (opts.withNpy) {
    writeFileSync(join(dir, 'coverage.npy'), encodeNpyBool([8, 8], new Array(64).fill(1)));
  }

  const manifest = {
    schema_version: '1.0.0',
    asset: {
      id: 'test_totem',
      source: 'degenerate-fixture',
    },
    acceptance: {
      gate: 'gate-1',
      verdict: 'accepted',
      date: '2026-08-04',
      record: 'test://acceptance/totem-1',
      by: 'director',
    },
    palette: {
      min_chroma: 12.0,
      allowed_bands: [{ name: 'warm', hue_deg: [0, 100] }],
      gate: { max_offpalette_pct: null, max_offpalette_blob_px: 8 },
    },
    channels: [
      {
        id: 'zones',
        space: 'texture',
        encoding: 'indexed',
        categorical: true,
        palette: [
          { name: 'zone_dark', rgb: TOTEM.ZONES_PALETTE[0] },
          { name: 'zone_warm', rgb: TOTEM.ZONES_PALETTE[1] },
        ],
        filter: 'nearest',
        path: 'channels/zones.png',
      },
      {
        id: 'matclass',
        space: 'render',
        encoding: 'rgba',
        categorical: true,
        palette: [
          { name: 'class_a', rgb: TOTEM.CLASS_A },
          { name: 'class_b', rgb: TOTEM.CLASS_B },
        ],
        filter: 'nearest',
      },
    ],
    renders: [
      {
        id: 'r0',
        path: 'renders/r0.png',
        camera: { yaw_deg: 0, elevation_deg: 0 },
        light: 'flat',
        silhouette_mask: 'sil/r0.png',
        channels: { matclass: 'matclass/r0.png' },
        pair: { clay: 'clay/r0.png' },
      },
      {
        id: 'r180',
        path: 'renders/r180.png',
        camera: { yaw_deg: 180, elevation_deg: 0 },
        light: 'flat',
        silhouette_mask: 'sil/r180.png',
        channels: { matclass: 'matclass/r180.png' },
      },
    ],
    captions: {
      subject: 'a test totem',
      domain_tag: '3d asset',
    },
  };

  if (opts.withNpy) {
    manifest.channels.push({
      id: 'coverage',
      space: 'texture',
      encoding: 'npy',
      categorical: false,
      path: 'coverage.npy',
      dtype: '|b1',
      shape: [8, 8],
    });
  }

  if (opts.mutate) opts.mutate(manifest);
  writeFileSync(join(dir, 'asset-source.json'), JSON.stringify(manifest, null, 2) + '\n');
  return { dir, manifest };
}
