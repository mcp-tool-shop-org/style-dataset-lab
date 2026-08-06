/**
 * lib/asset-source.js — the ingest contract. These tests hold it to the
 * design's promise: a wrong manifest that LOOKS right is refused loudly,
 * with every violation collected into one structured error, and nothing
 * survives on vibes — encodings are proven against bytes, categorical
 * palettes against PLTE chunks or exhaustive decodes, acceptance against
 * the literal verdict.
 *
 * All fixtures come from the degenerate second asset (fixtures/make-asset.js)
 * — the schema's proof that it is not W3-shaped.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rmSync, writeFileSync, unlinkSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  validateAssetSource,
  validateManifestShape,
  facingFromCamera,
  ASSET_MANIFEST_FILENAME,
} from '../../lib/asset-source.js';
import { writeDegenerateAsset, TOTEM } from './fixtures/make-asset.js';
import { encodePng } from './fixtures/make-png.js';

const manifestPathOf = (dir) => join(dir, ASSET_MANIFEST_FILENAME);

async function expectRefusal(dir, code, pattern) {
  await assert.rejects(
    () => validateAssetSource(manifestPathOf(dir)),
    (err) => {
      assert.equal(err.code, code, `expected code ${code}, got ${err.code}: ${err.message}\n${err.hint}`);
      if (pattern) assert.match(err.hint || err.message, pattern);
      return true;
    },
  );
}

test('a valid degenerate asset passes the full contract and resolves every file', async () => {
  const { dir } = writeDegenerateAsset({ withNpy: true });
  try {
    const { manifest, resolved } = await validateAssetSource(manifestPathOf(dir));
    assert.equal(manifest.asset.id, 'test_totem');
    assert.equal(resolved.renders.size, 2);
    const r0 = resolved.renders.get('r0');
    assert.ok(r0.meta.width === TOTEM.W && r0.meta.height === TOTEM.H);
    assert.ok(r0.silhouette, 'silhouette resolved');
    assert.ok(r0.instances.has('matclass'), 'render-space channel instance resolved');
    assert.ok(r0.pairs.has('clay'), 'conditioning pair resolved');
    const r180 = resolved.renders.get('r180');
    assert.equal(r180.pairs.size, 0, 'pairs are per-render, not assumed');
    assert.ok(resolved.textureChannels.has('zones'), 'texture channel resolved');
    assert.ok(resolved.textureChannels.has('coverage'), 'npy channel resolved');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a verdict other than "accepted" refuses at the door (ASSET_NOT_ACCEPTED)', async () => {
  const { dir } = writeDegenerateAsset({ mutate: (m) => { m.acceptance.verdict = 'pending'; } });
  try {
    await expectRefusal(dir, 'ASSET_NOT_ACCEPTED', /only verdict "accepted"/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a missing acceptance block refuses at the door', async () => {
  const { dir } = writeDegenerateAsset({ mutate: (m) => { delete m.acceptance; } });
  try {
    await expectRefusal(dir, 'ASSET_NOT_ACCEPTED', /acceptance/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('schema violations are collected, not first-error-only', () => {
  const violations = validateManifestShape({
    schema_version: '1.0.0',
    asset: { id: '../evil' },
    acceptance: { gate: 'g', verdict: 'accepted', date: '2026-08-04', record: 'r' },
    palette: { min_chroma: -1, allowed_bands: [], gate: { max_offpalette_blob_px: 8 } },
    renders: [],
  });
  const paths = violations.map((x) => x.path);
  assert.ok(paths.includes('asset.id'), `missing asset.id in ${paths}`);
  assert.ok(paths.includes('palette.min_chroma'));
  assert.ok(paths.includes('palette.allowed_bands'));
  assert.ok(paths.includes('renders'));
});

test('a referenced file that does not exist refuses with ASSET_FILE_MISSING', async () => {
  const { dir } = writeDegenerateAsset();
  try {
    unlinkSync(join(dir, 'renders', 'r180.png'));
    await expectRefusal(dir, 'ASSET_FILE_MISSING', /r180\.png/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('absolute and escaping manifest paths refuse with ASSET_PATH_ESCAPE', async () => {
  const abs = writeDegenerateAsset({ mutate: (m) => { m.renders[0].path = join(tmpdir(), 'x.png'); } });
  try {
    await expectRefusal(abs.dir, 'ASSET_PATH_ESCAPE', /absolute/);
  } finally {
    rmSync(abs.dir, { recursive: true, force: true });
  }

  const esc = writeDegenerateAsset({ mutate: (m) => { m.renders[0].silhouette_mask = '../outside.png'; } });
  try {
    await expectRefusal(esc.dir, 'ASSET_PATH_ESCAPE', /outside the export directory/);
  } finally {
    rmSync(esc.dir, { recursive: true, force: true });
  }
});

test('a declared encoding that disagrees with the actual bytes refuses (ASSET_ENCODING_MISMATCH)', async () => {
  // zones.png is indexed on disk; declare it rgb.
  const { dir } = writeDegenerateAsset({ mutate: (m) => {
    const zones = m.channels.find((c) => c.id === 'zones');
    zones.encoding = 'rgb';
    zones.categorical = false;
    delete zones.palette;
    delete zones.filter;
  } });
  try {
    await expectRefusal(dir, 'ASSET_ENCODING_MISMATCH', /color type 3/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('E09 PLTE discipline: an undeclared (padded) PLTE entry refuses (ASSET_PALETTE_PROOF_FAILED)', async () => {
  const { dir } = writeDegenerateAsset({ extraPlteEntry: true });
  try {
    await expectRefusal(dir, 'ASSET_PALETTE_PROOF_FAILED', /PLTE entry rgb\(9, 9, 9\)/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('the nearest-filter categorical proof is exhaustive: one off-class pixel refuses', async () => {
  const { dir } = writeDegenerateAsset();
  try {
    // Overwrite the r0 matclass instance with one wrong pixel inside the figure.
    const { W, H, FIGURE, CLASS_A } = TOTEM;
    const data = new Uint8Array(W * H * 4);
    for (let y = FIGURE.r0; y <= FIGURE.r1; y++) {
      for (let x = FIGURE.c0; x <= FIGURE.c1; x++) {
        const o = (y * W + x) * 4;
        data[o] = CLASS_A[0]; data[o + 1] = CLASS_A[1]; data[o + 2] = CLASS_A[2]; data[o + 3] = 255;
      }
    }
    const off = ((FIGURE.r0 + 1) * W + FIGURE.c0 + 1) * 4;
    data[off] = 1; data[off + 1] = 2; data[off + 2] = 3; // rgb(1,2,3): not a class
    writeFileSync(join(dir, 'matclass', 'r0.png'), encodePng({ width: W, height: H, colorType: 6, data }));
    await expectRefusal(dir, 'ASSET_PALETTE_PROOF_FAILED', /rgb\(1, 2, 3\)/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a silhouette whose dimensions differ from its render refuses (parallel masks)', async () => {
  const { dir } = writeDegenerateAsset();
  try {
    writeFileSync(join(dir, 'sil', 'r0.png'), encodePng({ width: 8, height: 8, colorType: 0, data: new Uint8Array(64).fill(255) }));
    await expectRefusal(dir, 'ASSET_ENCODING_MISMATCH', /masks are parallel to renders/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('npy declarations are proven against the actual header', async () => {
  const { dir } = writeDegenerateAsset({ withNpy: true, mutate: (m) => {
    m.channels.find((c) => c.id === 'coverage').shape = [4, 4];
  } });
  try {
    await expectRefusal(dir, 'ASSET_ENCODING_MISMATCH', /shape \[8,8\], manifest declares \[4,4\]/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a render channel entry referencing an undeclared channel id is a shape violation', async () => {
  const { dir } = writeDegenerateAsset({ mutate: (m) => {
    m.renders[0].channels.bogus = 'matclass/r0.png';
  } });
  try {
    await expectRefusal(dir, 'ASSET_MANIFEST_INVALID', /undeclared channel id "bogus"/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('multiple violations are all reported in one refusal, loudest class first', async () => {
  const { dir } = writeDegenerateAsset({ mutate: (m) => { m.acceptance.verdict = 'nope'; m.renders[0].id = 'has space'; } });
  try {
    await assert.rejects(
      () => validateAssetSource(manifestPathOf(dir)),
      (err) => {
        assert.equal(err.code, 'ASSET_NOT_ACCEPTED', 'the acceptance violation names the error');
        assert.match(err.hint, /acceptance\.verdict/);
        assert.match(err.hint, /renders\[0\]\.id/);
        return true;
      },
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a missing manifest and invalid JSON each refuse with their own codes', async () => {
  const empty = mkdtempSync(join(tmpdir(), 'sdlab-asset-nomanifest-'));
  try {
    await assert.rejects(
      () => validateAssetSource(manifestPathOf(empty)),
      (err) => err.code === 'ASSET_MANIFEST_NOT_FOUND',
    );
    writeFileSync(manifestPathOf(empty), '{ not json');
    await assert.rejects(
      () => validateAssetSource(manifestPathOf(empty)),
      (err) => err.code === 'ASSET_MANIFEST_INVALID' && /not valid JSON/.test(err.message),
    );
  } finally {
    rmSync(empty, { recursive: true, force: true });
  }
});

test('facingFromCamera: deterministic 8-way vocabulary + elevation clauses', () => {
  assert.equal(facingFromCamera({ yaw_deg: 0 }), 'front');
  assert.equal(facingFromCamera({ yaw_deg: 45 }), 'three-quarter front-right');
  assert.equal(facingFromCamera({ yaw_deg: 90 }), 'right profile');
  assert.equal(facingFromCamera({ yaw_deg: 135 }), 'three-quarter back-right');
  assert.equal(facingFromCamera({ yaw_deg: 180 }), 'back');
  assert.equal(facingFromCamera({ yaw_deg: 225 }), 'three-quarter back-left');
  assert.equal(facingFromCamera({ yaw_deg: 270 }), 'left profile');
  assert.equal(facingFromCamera({ yaw_deg: 315 }), 'three-quarter front-left');
  assert.equal(facingFromCamera({ yaw_deg: 350 }), 'front', 'buckets are centered — 350° is front');
  assert.equal(facingFromCamera({ yaw_deg: -45 }), 'three-quarter front-left', 'negative yaw normalizes');
  assert.equal(facingFromCamera({ yaw_deg: 0, elevation_deg: 55 }), 'front, viewed from above');
  assert.equal(facingFromCamera({ yaw_deg: 180, elevation_deg: -40 }), 'back, viewed from below');
  assert.equal(facingFromCamera({ yaw_deg: 180, elevation_deg: 10 }), 'back', 'small elevations add nothing');
});

// ── Schema 1.1.0 — the E11 Ruling 6 sidecars become declarable ─────────
//
// The lane's promise does not change: declarations are proven against bytes.
// What changes is that owner maps, admission sidecars and camera json can be
// DECLARED, so they are contained, proven, hashed and carried into the record
// instead of riding invisibly beside the export.

const V11_BASE = () => ({
  schema_version: '1.1.0',
  asset: { id: 'x' },
  acceptance: { gate: 'g', verdict: 'accepted', date: '2026-08-06', record: 'r' },
  palette: {
    min_chroma: 1,
    allowed_bands: [{ name: 'w', hue_deg: [0, 10] }],
    gate: { max_offpalette_blob_px: 1, max_offpalette_pct: null },
  },
  renders: [{ id: 'r0', path: 'r.png', camera: { yaw_deg: 0 }, silhouette_mask: 's.png' }],
});

test('1.1.0: render-space npy + json channels resolve, and identity is carried', async () => {
  const { dir } = writeDegenerateAsset({ withOwnerId: true, withSidecar: true, subjectName: 'test_totem_subject' });
  try {
    const { manifest, resolved } = await validateAssetSource(manifestPathOf(dir));
    assert.equal(manifest.identity.subject_name, 'test_totem_subject');
    const r0 = resolved.renders.get('r0');
    assert.ok(r0.instances.has('owner_id'), 'npy instance resolved into the render entry');
    assert.equal(r0.instances.get('owner_id').meta.dtype, '|i1');
    assert.deepEqual(r0.instances.get('owner_id').meta.shape, [TOTEM.H, TOTEM.W],
      'the header shape is [height, width] — numpy is row-major');
    assert.ok(r0.instances.has('admission'), 'json instance resolved into the render entry');
    assert.deepEqual(r0.instances.get('admission').meta.keys, ['view', 'figure_px', 'owner_values_present']);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('1.1.0: a TRANSPOSED render-space npy is refused — the axis proof is the point', async () => {
  const { dir } = writeDegenerateAsset({ withOwnerId: true, transposedOwnerId: true });
  try {
    await expectRefusal(dir, 'ASSET_ENCODING_MISMATCH', /must open \[height, width\] = \[10, 12\]/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('1.1.0: an undeclared value in a categorical npy is refused exhaustively', async () => {
  // Drop 'view_a' (value 0) from the declared classes. r0's owner map is full
  // of 0s inside the figure, so the scan must find one and name it.
  const { dir } = writeDegenerateAsset({
    withOwnerId: true,
    mutate: (m) => {
      const c = m.channels.find((x) => x.id === 'owner_id');
      c.classes = c.classes.filter((k) => k.value !== 0);
    },
  });
  try {
    await expectRefusal(dir, 'ASSET_PALETTE_PROOF_FAILED', /value 0 at flat index \d+ is not a declared class value/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('1.1.0: a categorical npy on an unreadable dtype is refused at declaration time', () => {
  const m = V11_BASE();
  m.channels = [{ id: 'owner', space: 'render', encoding: 'npy', categorical: true, dtype: '<i4', classes: [{ name: 'a', value: 0 }] }];
  const violations = validateManifestShape(m);
  assert.ok(violations.some((v) => /dtype/.test(v.path) && /values can be read/.test(v.message)),
    'an unprovable dtype is refused rather than silently left unproven');
});

test('1.1.0: a json channel missing a declared required key is refused', async () => {
  const { dir } = writeDegenerateAsset({
    withSidecar: true,
    mutate: (m) => {
      m.channels.find((c) => c.id === 'admission').required_keys = ['view', 'figure_px', 'owner_boundary_px'];
    },
  });
  try {
    await expectRefusal(dir, 'ASSET_ENCODING_MISMATCH', /missing declared required key\(s\): owner_boundary_px/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('1.1.0: a json channel cannot be categorical — sdlab reads no values there', () => {
  const m = V11_BASE();
  m.channels = [{ id: 'side', space: 'render', encoding: 'json', categorical: true }];
  assert.ok(validateManifestShape(m).some((v) => /cannot be categorical/.test(v.message)));
});

test('1.1.0: render-space npy declaring a channel-level shape is refused', () => {
  const m = V11_BASE();
  m.channels = [{ id: 'owner', space: 'render', encoding: 'npy', dtype: '|i1', shape: [10, 12] }];
  const violations = validateManifestShape(m);
  assert.ok(violations.some((v) => v.path === 'channels[0].shape' && /against its own render/.test(v.message)),
    'one channel-level shape cannot describe instances across differently sized renders');
});

test('1.1.0: a 1.0.0 manifest still validates unchanged — every addition is optional', async () => {
  const { dir, manifest } = writeDegenerateAsset({ withNpy: true });
  try {
    assert.equal(manifest.schema_version, '1.0.0');
    const { resolved } = await validateAssetSource(manifestPathOf(dir));
    assert.equal(resolved.renders.size, 2);
    assert.ok(resolved.textureChannels.has('coverage'));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('1.1.0: a manifest declaring a NEWER minor is refused, not silently stripped', () => {
  const m = V11_BASE();
  m.schema_version = '1.9.0';
  const violations = validateManifestShape(m);
  assert.ok(violations.some((v) => v.path === 'schema_version' && /newer minor/.test(v.message)),
    'accepting it would drop declared channels this build cannot see');
});

test('1.1.0: identity.subject_name must be a safe id — it is a split-family key', () => {
  const m = V11_BASE();
  m.identity = { subject_name: 'not a safe id!' };
  assert.ok(validateManifestShape(m).some((v) => v.path === 'identity.subject_name'));
});
