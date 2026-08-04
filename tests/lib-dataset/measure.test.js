/**
 * measure — does it actually SEE the image?
 *
 * The failure mode this guards against is a measurement pipeline that runs,
 * returns well-formed numbers, and reports the same thing about every image.
 * A test asserting "returns a number" would pass against exactly that, so
 * every assertion below is comparative: a flat image against a noisy one, an
 * on-anchor image against an off-anchor one. If the instrument stops
 * discriminating, these go red.
 *
 * Python is OPTIONAL for this repo — `npm test` runs Node only, and CI may
 * have no Pillow/numpy/scipy. These tests SKIP rather than fail in that case,
 * following the pattern in tests/cli-scripts/qwen-python-parity.test.js. A
 * suite that fails on a machine without an optional dependency trains people
 * to ignore it.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { deflateSync } from 'node:zlib';

import {
  findPython,
  checkPythonDeps,
  runPythonMeasurement,
} from '../../lib/measure.js';

// ── environment probe ────────────────────────────────────────────────────

const PYTHON = findPython();
const DEPS = PYTHON ? checkPythonDeps(PYTHON) : { ok: false, missing: ['python'] };
const SKIP = !DEPS.ok
  ? `python or its measurement deps unavailable (${DEPS.missing.join(', ')}) — measurement is an optional capability`
  : false;

// ── a minimal PNG encoder, so the fixtures are generated not committed ───
// Avoids adding an image dependency to a repo whose whole point is having
// almost none, and lets each test state its own pixel content in-line.

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xEDB88320 & -(c & 1));
  }
  return ~c >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

/**
 * @param {number} size
 * @param {(x:number,y:number)=>[number,number,number]} pixel
 */
function makePng(size, pixel) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8;   // bit depth
  ihdr[9] = 2;   // colour type: truecolour RGB
  const raw = Buffer.alloc(size * (1 + size * 3));
  let o = 0;
  for (let y = 0; y < size; y++) {
    raw[o++] = 0; // filter: none
    for (let x = 0; x < size; x++) {
      const [r, g, b] = pixel(x, y);
      raw[o++] = r; raw[o++] = g; raw[o++] = b;
    }
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function withFixtures(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'sdlab-measure-test-'));
  try { return fn(dir); } finally { rmSync(dir, { recursive: true, force: true }); }
}

// A deterministic pseudo-noise so "noisy" is reproducible across runs —
// Math.random() would make a failure impossible to reproduce.
function noise(x, y) {
  const n = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
  return Math.floor((n - Math.floor(n)) * 256);
}

// ── texture: flat vs noisy ───────────────────────────────────────────────

test('texture measures separate a flat image from a noisy one', { skip: SKIP }, () => {
  withFixtures((dir) => {
    const flat = join(dir, 'flat.png');
    const noisy = join(dir, 'noisy.png');
    writeFileSync(flat, makePng(64, () => [128, 120, 90]));
    writeFileSync(noisy, makePng(64, (x, y) => [noise(x, y), noise(x + 7, y), noise(x, y + 13)]));

    const res = runPythonMeasurement(PYTHON, {
      images: [{ id: 'flat', path: flat }, { id: 'noisy', path: noisy }],
      anchors: [],
    });

    const byId = Object.fromEntries(res.results.map((r) => [r.id, r]));
    assert.ok(byId.flat, 'flat image measured');
    assert.ok(byId.noisy, 'noisy image measured');

    // Laplacian variance is the headline high-frequency-energy measure. A
    // flat field has essentially none; noise has a great deal. If these come
    // back equal the instrument is not reading pixels.
    assert.ok(
      byId.noisy.texture.lap_var > byId.flat.texture.lap_var * 10,
      `noisy lap_var (${byId.noisy.texture.lap_var}) must greatly exceed flat (${byId.flat.texture.lap_var})`,
    );
    assert.ok(
      byId.noisy.texture.hf_ratio > byId.flat.texture.hf_ratio,
      'noisy high-frequency ratio must exceed flat',
    );
  });
});

// ── palette: on-anchor vs off-anchor ─────────────────────────────────────

test('palette conformance separates an on-anchor image from an off-anchor one', { skip: SKIP }, () => {
  withFixtures((dir) => {
    // Ochre ~ hue 35°, and a blue that is nowhere near it.
    const ochre = join(dir, 'ochre.png');
    const blue = join(dir, 'blue.png');
    writeFileSync(ochre, makePng(64, () => [188, 132, 48]));
    writeFileSync(blue, makePng(64, () => [48, 96, 200]));

    const res = runPythonMeasurement(PYTHON, {
      images: [{ id: 'ochre', path: ochre }, { id: 'blue', path: blue }],
      anchors: [{ name: 'ochre', hex: '#BC8430' }],
      hue_tolerance_deg: 20,
    });

    const byId = Object.fromEntries(res.results.map((r) => [r.id, r]));
    const onAnchor = byId.ochre.palette.off_anchor_pct;
    const offAnchor = byId.blue.palette.off_anchor_pct;

    assert.ok(typeof onAnchor === 'number', 'an anchored run must produce off_anchor_pct');
    assert.ok(typeof offAnchor === 'number');
    // THE assertion. An image made entirely of the anchor hue must not score
    // the same as one made entirely of its opposite.
    assert.ok(
      offAnchor > onAnchor,
      `a blue image (${offAnchor}% off-anchor) must score further from an ochre anchor than an ochre image (${onAnchor}%)`,
    );
  });
});

test('without anchors, palette conformance is null rather than invented', { skip: SKIP }, () => {
  withFixtures((dir) => {
    const img = join(dir, 'x.png');
    writeFileSync(img, makePng(32, () => [188, 132, 48]));

    const res = runPythonMeasurement(PYTHON, { images: [{ id: 'x', path: img }], anchors: [] });
    const p = res.results[0].palette;

    // Measures that need no anchor still come back...
    assert.ok(typeof p.mean_saturation === 'number', 'anchor-free measures still computed');
    // ...and the one that does is honestly absent. Returning 0 or 100 here
    // would be a fabricated number, which is the thing this whole feature is
    // built not to do.
    assert.equal(p.off_anchor_pct, null, 'anchor-dependent measure must be null, not guessed');
  });
});

// ── the environment contract ─────────────────────────────────────────────

test('a missing interpreter is reported, not silently tolerated', () => {
  // Runs with or without Python: findPython must return null for an env that
  // pins a nonexistent interpreter, so the CLI can raise a clear error rather
  // than failing later with a confusing spawn message.
  const found = findPython({ SDLAB_PYTHON: join(tmpdir(), 'definitely-not-a-python-binary') });
  assert.equal(found, null, 'a bad SDLAB_PYTHON must not resolve');
});
