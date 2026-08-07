/**
 * Schema 1.2.0 — the register, the tone transform, and per-image generation
 * provenance.
 *
 * These three additions all exist because facet's E12/E13 arc MEASURED
 * something the lane could not previously express:
 *
 *   - Ruling 10b: a painterly register two subjects earned was inherited by a
 *     third that should read ultra-realistic. The register is subject data,
 *     and NO-LoRA is a decision a manifest must state, not omit. The tests
 *     below hold that line mechanically: a style block that ducks the LoRA
 *     question is refused, and so is one that answers it two ways at once.
 *
 *   - Rulings 23c/23f: projection consumes a Lab-statistics-harmonized set.
 *     Every colour number this lane measures sits downstream of that
 *     transform, so it is declared — with sdlab's boundary (structure yes,
 *     semantics no) enforced rather than merely documented.
 *
 *   - Rulings 20a/24b: crop-framed generation drifts register (3 instances);
 *     term binding is seed-dependent. Both are per-image curation axes, so
 *     frame and seed must survive into the record.
 *
 * Fixtures are the degenerate second asset, as with the rest of the suite —
 * the schema's standing proof that it is not W3-shaped.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rmSync, writeFileSync, readFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import {
  validateAssetSource,
  validateManifestShape,
  ASSET_MANIFEST_FILENAME,
  ASSET_SCHEMA_VERSION,
} from '../../lib/asset-source.js';
import { ingestAssetSource } from '../../lib/asset-ingest.js';
import { writeDegenerateAsset } from './fixtures/make-asset.js';
import { createTmpProject } from '../lib-dataset/fixtures/make-project.js';

const manifestPathOf = (dir) => join(dir, ASSET_MANIFEST_FILENAME);
const readJson = (p) => JSON.parse(readFileSync(p, 'utf-8'));

const STYLE_CARD = {
  register: { terms: ['painterly', 'visible brushstrokes'], ruling: 'E12 Ruling 10b', record: 'test://rulings/10b' },
  lora: { declared: 'card', card: 'saltroad_style_v2_lowlr_000001500', weight: 0.85 },
};
const STYLE_NONE = {
  register: { terms: ['ultra-realistic', 'menacing'], ruling: 'E12 Ruling 10b', record: 'test://rulings/10b' },
  lora: { declared: 'none' },
};

/** Shape-only violations for a manifest built by mutating the fixture. */
function shapeViolations(mutate) {
  const { dir } = writeDegenerateAsset({ mutate });
  try {
    return validateManifestShape(readJson(manifestPathOf(dir)));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const hasViolation = (violations, path, pattern) =>
  violations.some((v) => v.path === path && (!pattern || pattern.test(v.message)));

// ── The register (E12 Ruling 10b) ────────────────────────────────────

test('a style block naming a card validates and carries the live card name', () => {
  const violations = shapeViolations((m) => { m.asset.style = STYLE_CARD; });
  assert.deepEqual(violations, [], 'a complete style block is legal');
});

test('a style block declaring NO LoRA validates — "none" is a positive declaration', () => {
  const violations = shapeViolations((m) => { m.asset.style = STYLE_NONE; });
  assert.deepEqual(violations, [], 'the ruled no-LoRA register is expressible');
});

test('a style block with no lora key is REFUSED — the implicit section Ruling 10b forbids', () => {
  const violations = shapeViolations((m) => { m.asset.style = { register: STYLE_CARD.register }; });
  assert.ok(hasViolation(violations, 'asset.style.lora', /answer the LoRA question explicitly/),
    'omitting the LoRA answer must not read as "no LoRA"');
});

test('lora.declared must be exactly "none" or "card"', () => {
  for (const declared of ['NONE', 'null', '', 'saltroad', true]) {
    const violations = shapeViolations((m) => {
      m.asset.style = { register: STYLE_CARD.register, lora: { declared } };
    });
    assert.ok(hasViolation(violations, 'asset.style.lora.declared'),
      `declared: ${JSON.stringify(declared)} must be refused`);
  }
});

test('declared "card" without a card name is refused — a nickname is not a live card', () => {
  const violations = shapeViolations((m) => {
    m.asset.style = { register: STYLE_CARD.register, lora: { declared: 'card' } };
  });
  assert.ok(hasViolation(violations, 'asset.style.lora.card', /LIVE card name/));
});

test('declared "none" WITH a card is refused — a no-LoRA register that names a card contradicts itself', () => {
  const violations = shapeViolations((m) => {
    m.asset.style = { register: STYLE_NONE.register, lora: { declared: 'none', card: 'saltroad_v2' } };
  });
  assert.ok(hasViolation(violations, 'asset.style.lora.card', /contradicts itself/),
    'the contradiction is refused rather than silently resolved one way');
});

test('declared "none" with a nonzero weight is refused', () => {
  const violations = shapeViolations((m) => {
    m.asset.style = { register: STYLE_NONE.register, lora: { declared: 'none', weight: 0.8 } };
  });
  assert.ok(hasViolation(violations, 'asset.style.lora.weight'));
  // weight 0 is the mechanical expression of "none" and stays legal
  const ok = shapeViolations((m) => {
    m.asset.style = { register: STYLE_NONE.register, lora: { declared: 'none', weight: 0 } };
  });
  assert.deepEqual(ok, [], 'lora-w 0.0 is how "none" is expressed in a profile');
});

test('a register with no terms is refused — the block exists to name the register', () => {
  for (const register of [{}, { terms: [] }, { terms: ['ok', ''] }, { terms: 'painterly' }]) {
    const violations = shapeViolations((m) => {
      m.asset.style = { register, lora: { declared: 'none' } };
    });
    assert.ok(hasViolation(violations, 'asset.style.register.terms') || hasViolation(violations, 'asset.style.register'),
      `register ${JSON.stringify(register)} must be refused`);
  }
});

test('the style block stays OPTIONAL — 1.0.0 and 1.1.0 manifests validate unchanged', () => {
  const violations = shapeViolations(() => {});
  assert.deepEqual(violations, [], 'no style block is legal; the ingest reports it as a notice, not a refusal');
});

// ── The tone transform (E12 Rulings 23c/23f) ─────────────────────────

const TONE = {
  kind: 'lab-stats-transfer',
  space: 'CIELAB',
  scope: 'figure-mask',
  reference: 'r0',
  operands: 'harmonize/operands.json',
  reversible: true,
  record: 'test://rulings/23f',
};

/** Fixture + a real operands sidecar on disk at the declared path. */
function withToneTransform(extraMutate) {
  const { dir } = writeDegenerateAsset({
    mutate: (m) => {
      m.asset.tone_transform = { ...TONE };
      if (extraMutate) extraMutate(m);
    },
  });
  const opDir = join(dir, 'harmonize');
  mkdirSync(opDir, { recursive: true });
  writeFileSync(join(opDir, 'operands.json'), JSON.stringify({
    r0: { mean_L: 0, std_L: 1 },
    r180: { mean_L: -3.16, std_L: 1.02 },
  }));
  return dir;
}

test('a declared tone transform validates and its operands sidecar is contained + resolved', async () => {
  const dir = withToneTransform();
  try {
    const { resolved } = await validateAssetSource(manifestPathOf(dir));
    assert.ok(resolved.toneOperands, 'the operands sidecar resolves');
    assert.equal(resolved.toneOperands.relPath, 'harmonize/operands.json');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a reference view this manifest does not declare is REFUSED as dangling provenance', () => {
  const violations = shapeViolations((m) => {
    m.asset.tone_transform = { ...TONE, reference: 'view_1_that_is_not_here' };
  });
  assert.ok(hasViolation(violations, 'asset.tone_transform.reference', /not a render id declared in this manifest/),
    'sdlab cannot check the arithmetic, but it CAN check the reference resolves');
});

test('a tone transform with no kind or no operands is refused', () => {
  const noKind = shapeViolations((m) => {
    const tt = { ...TONE }; delete tt.kind; m.asset.tone_transform = tt;
  });
  assert.ok(hasViolation(noKind, 'asset.tone_transform.kind'));
  const noOperands = shapeViolations((m) => {
    const tt = { ...TONE }; delete tt.operands; m.asset.tone_transform = tt;
  });
  assert.ok(hasViolation(noOperands, 'asset.tone_transform.operands', /audited or replayed/));
});

test('a per-render tone_transform must be a boolean, and must have an asset-level block to opt out of', () => {
  const notBool = shapeViolations((m) => {
    m.asset.tone_transform = { ...TONE };
    m.renders[1].tone_transform = { applied: false };
  });
  assert.ok(hasViolation(notBool, 'renders[1].tone_transform', /must be a boolean/));

  const orphan = shapeViolations((m) => { m.renders[1].tone_transform = false; });
  assert.ok(hasViolation(orphan, 'renders[1].tone_transform', /no asset.tone_transform/),
    'an opt-out with nothing to opt out of is a manifest error, not a no-op');
});

// ── Generation provenance (E12 Rulings 20a / 24b) ────────────────────

test('generation.frame is a closed enum — the axis the register-drift phenomenon was measured on', () => {
  for (const frame of ['full', 'crop']) {
    const violations = shapeViolations((m) => { m.renders[0].generation = { frame }; });
    assert.deepEqual(violations, [], `frame "${frame}" is legal`);
  }
  for (const frame of ['bust', 'head-crop', 'FULL', '', undefined]) {
    const violations = shapeViolations((m) => { m.renders[0].generation = { frame }; });
    assert.ok(hasViolation(violations, 'renders[0].generation.frame'),
      `frame ${JSON.stringify(frame)} must be refused — free text cannot be queried`);
  }
});

test('a seed is a safe integer or a digit-string; a float or a non-numeric string is refused', () => {
  for (const seed of [770700, 42, '770700', '18446744073709551615']) {
    const violations = shapeViolations((m) => { m.renders[0].generation = { frame: 'full', seed }; });
    assert.deepEqual(violations, [], `seed ${JSON.stringify(seed)} is legal`);
  }
  for (const seed of [770700.5, 'seed-770700', '', {}, Number.MAX_VALUE]) {
    const violations = shapeViolations((m) => { m.renders[0].generation = { frame: 'full', seed }; });
    assert.ok(hasViolation(violations, 'renders[0].generation.seed'),
      `seed ${JSON.stringify(seed)} must be refused — a seed that cannot be grouped on is useless here`);
  }
});

test('frame_detail, stem, model and reroll_of ride as free strings', () => {
  const violations = shapeViolations((m) => {
    m.renders[0].generation = {
      frame: 'crop',
      frame_detail: 'head-crop yaw 0, ortho-scale 0.31',
      seed: 770701,
      stem: 'v9',
      model: 'test-model',
      reroll_of: 'r0_770700',
    };
  });
  assert.deepEqual(violations, [], 'asset-specific detail is the asset\'s business');
});

// ── The version gate ─────────────────────────────────────────────────

test('the version gate accepts every minor up to the current one, and refuses a higher one loudly', () => {
  assert.equal(ASSET_SCHEMA_VERSION, '1.3.0');
  for (const v of ['1.0.0', '1.1.0', '1.2.0', '1.3.0']) {
    assert.deepEqual(shapeViolations((m) => { m.schema_version = v; }), [], `${v} validates`);
  }
  const tooNew = shapeViolations((m) => { m.schema_version = '1.4.0'; });
  assert.ok(hasViolation(tooNew, 'schema_version', /newer minor/),
    'a manifest declaring channels this build cannot see is refused, never silently stripped');
});

// ── Render derivation (E11 Ruling 2, schema 1.3.0) ───────────────────
//
// The defect 1.3.0 closes: a dense turnaround's renders are deterministic
// derivations of an already-accepted asset, so they carry no generation block
// and are RIGHT not to. 1.2.0 could not tell that apart from an export that
// simply lost its seeds, and reported a gap on both — telling an operator to
// go fix an export that was correct by ruling.

const EMIT_DERIVATION = { kind: 'emit', generated: false, record: 'E11 Ruling 2' };

test('a render_derivation block validates, and generated must be an explicit boolean', () => {
  assert.deepEqual(shapeViolations((m) => { m.asset.render_derivation = EMIT_DERIVATION; }), []);
  assert.deepEqual(
    shapeViolations((m) => { m.asset.render_derivation = { kind: 'txt2img', generated: true }; }), []);

  for (const rd of [{ kind: 'emit' }, { kind: 'emit', generated: 'false' }, { kind: 'emit', generated: null }]) {
    assert.ok(hasViolation(shapeViolations((m) => { m.asset.render_derivation = rd; }),
      'asset.render_derivation.generated'),
      `${JSON.stringify(rd)} must be refused — this is a declaration, not an inference`);
  }
  assert.ok(hasViolation(shapeViolations((m) => { m.asset.render_derivation = { generated: false }; }),
    'asset.render_derivation.kind'));
});

test('a generation block on a declared NON-generated render is refused as a category error', () => {
  const violations = shapeViolations((m) => {
    m.asset.render_derivation = EMIT_DERIVATION;
    m.renders[0].generation = { frame: 'full', seed: 770700 };
  });
  assert.ok(hasViolation(violations, 'renders[0].generation', /no seed of their own/),
    'a deterministic derivation has no seed; declaring one attributes a seed to an image no seed produced');
});

test('generated: true keeps generation blocks fully validated', () => {
  assert.deepEqual(shapeViolations((m) => {
    m.asset.render_derivation = { kind: 'txt2img', generated: true };
    m.renders[0].generation = { frame: 'crop', seed: 770701 };
  }), []);
  // and the enum is still enforced underneath the declaration
  assert.ok(hasViolation(shapeViolations((m) => {
    m.asset.render_derivation = { kind: 'txt2img', generated: true };
    m.renders[0].generation = { frame: 'bust' };
  }), 'renders[0].generation.frame'));
});

test('a declared derivation SUPPRESSES the generation gap and reports info instead', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({ mutate: (m) => { m.asset.render_derivation = EMIT_DERIVATION; } });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    assert.ok(!report.notices.some((n) => n.code === 'ASSET_GENERATION_PROVENANCE_ABSENT'),
      'an export that is correct by ruling must not be reported as needing a fix');
    const info = report.notices.find((n) => n.code === 'ASSET_RENDERS_ARE_DERIVATIONS');
    assert.ok(info && info.kind === 'info', 'the fact is still recorded, as information');

    const rec = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json')).provenance;
    assert.deepEqual(rec.render_derivation, { kind: 'emit', generated: false, record: 'E11 Ruling 2' });
    assert.equal(rec.generation, null,
      'null by DECLARATION — the record carries render_derivation beside it so a consumer can tell which kind of null this is');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('an UNDECLARED manifest still gets the gap — saying nothing is not saying "these are derivations"', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    const gap = report.notices.find((n) => n.code === 'ASSET_GENERATION_PROVENANCE_ABSENT');
    assert.ok(gap, '1.2.0 behaviour is preserved exactly where nothing was declared');
    assert.match(gap.message, /declare asset\.render_derivation with generated: false/,
      'the notice names its own remedy');
    const rec = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json')).provenance;
    assert.equal(rec.render_derivation, null);
    assert.equal(rec.generation, null, 'null by OMISSION — indistinguishable from the declared case without render_derivation');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('a generated: true manifest missing its seeds still reports the gap', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({
    mutate: (m) => { m.asset.render_derivation = { kind: 'txt2img', generated: true }; },
  });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    assert.ok(report.notices.some((n) => n.code === 'ASSET_GENERATION_PROVENANCE_ABSENT'),
      'declaring renders GENERATED and then not saying how is exactly the gap the notice is for');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

// ── Carry-through into records ───────────────────────────────────────

test('the register lands on every record, with "none" distinguishable from undeclared', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({ mutate: (m) => { m.asset.style = STYLE_NONE; } });
  try {
    await ingestAssetSource(proj.projectRoot, dir);
    const rec = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json'));
    assert.deepEqual(rec.provenance.style, {
      register_terms: ['ultra-realistic', 'menacing'],
      register_ruling: 'E12 Ruling 10b',
      register_record: 'test://rulings/10b',
      lora: { declared: 'none', card: null, weight: 0 },
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('an undeclared register lands as style: null — silence is recorded, not guessed', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    const rec = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json'));
    assert.equal(rec.provenance.style, null, 'null is meaningful and always written');
    assert.ok(report.notices.some((n) => n.code === 'ASSET_STYLE_UNDECLARED'),
      'the gap is reported at ingest, not discovered later by a training run');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('a card register carries the live card name and weight into the record', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({ mutate: (m) => { m.asset.style = STYLE_CARD; } });
  try {
    await ingestAssetSource(proj.projectRoot, dir);
    const rec = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json'));
    assert.deepEqual(rec.provenance.style.lora, {
      declared: 'card', card: 'saltroad_style_v2_lowlr_000001500', weight: 0.85,
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('the tone transform resolves PER RECORD: applied, opted-out, and reference-is-self', async () => {
  const proj = createTmpProject();
  const dir = withToneTransform((m) => { m.renders[1].tone_transform = false; });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);

    const r0 = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json')).provenance.tone_transform;
    assert.equal(r0.applied, true, 'a render inherits the asset-level transform');
    assert.equal(r0.reference_is_self, true, 'r0 IS the reference view — transferring it toward itself is identity');
    assert.equal(r0.kind, 'lab-stats-transfer');
    assert.equal(r0.reversible, true, "the asset's claim, recorded not verified");
    assert.match(r0.operands.sha256, /^[0-9a-f]{64}$/, 'the operands are hashed');

    const r180 = readJson(join(proj.projectRoot, 'records', 'test_totem__r180.json')).provenance.tone_transform;
    assert.equal(r180.applied, false, 'the per-render opt-out is RESOLVED at ingest, never re-derived downstream');
    assert.equal(r180.reference_is_self, false);

    // Materialized, not left as a pointer into the export tree.
    const opRel = r0.operands.path;
    assert.ok(opRel.startsWith('assets/test_totem/'), `operands materialized into the project (${opRel})`);
    const receipt = readJson(join(proj.projectRoot, report.receiptPath));
    assert.ok(receipt.files.some((f) => f.role === 'tone_operands' && f.materialized === true),
      'the operands appear in the receipt ledger as a materialized file');
    assert.ok(report.notices.some((n) => n.code === 'ASSET_TONE_TRANSFORM_DECLARED'),
      'a colour transform under every colour measurement is announced');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('records with no tone transform carry tone_transform: null, not a fabricated identity transform', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    await ingestAssetSource(proj.projectRoot, dir);
    const rec = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json'));
    assert.equal(rec.provenance.tone_transform, null);
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('frame and seed survive into the record — the two measured curation axes', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({
    mutate: (m) => {
      m.renders[0].generation = { frame: 'full', seed: 770700, stem: 'v9' };
      m.renders[1].generation = { frame: 'crop', frame_detail: 'bust, yaw 180', seed: '770701', reroll_of: 'r180_770700' };
    },
  });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    const r0 = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json')).provenance.generation;
    assert.deepEqual(r0, { frame: 'full', frame_detail: null, seed: 770700, stem: 'v9', model: null, reroll_of: null });

    const r180 = readJson(join(proj.projectRoot, 'records', 'test_totem__r180.json')).provenance.generation;
    assert.equal(r180.frame, 'crop', 'the crop frame is queryable — Ruling 24b needs exactly this');
    assert.equal(r180.seed, '770701', 'a digit-string seed survives as declared, with no numeric coercion');
    assert.equal(r180.reroll_of, 'r180_770700', 'the bounded re-roll marks a seed that resisted');

    assert.ok(!report.notices.some((n) => n.code === 'ASSET_GENERATION_PROVENANCE_ABSENT'),
      'nothing to report when every render declares its generation');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('missing generation provenance is counted and reported, not silently accepted', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset({
    mutate: (m) => { m.renders[0].generation = { frame: 'full', seed: 42 }; },
  });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    const notice = report.notices.find((n) => n.code === 'ASSET_GENERATION_PROVENANCE_ABSENT');
    assert.ok(notice, 'the partial declaration is reported');
    assert.match(notice.message, /1 of 2 admitted render\(s\)/);
    const r180 = readJson(join(proj.projectRoot, 'records', 'test_totem__r180.json'));
    assert.equal(r180.provenance.generation, null);
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('the standing errand: a missing identity.subject_name is reported as a split-leakage risk', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    const notice = report.notices.find((n) => n.code === 'ASSET_SUBJECT_NAME_ABSENT');
    assert.ok(notice, 'the leakage risk is named at ingest — the only moment it is cheap to fix');
    assert.match(notice.message, /train and test/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('a fully-declared 1.2.0 manifest produces NO gap notices — only the informational one', async () => {
  const proj = createTmpProject();
  const dir = withToneTransform((m) => {
    m.schema_version = '1.2.0';
    m.identity = { subject_name: 'test_totem' };
    m.asset.style = STYLE_NONE;
    m.renders[0].generation = { frame: 'full', seed: 770700 };
    m.renders[1].generation = { frame: 'full', seed: 770700 };
  });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);
    assert.deepEqual(report.notices.filter((n) => n.kind === 'gap'), [],
      'a manifest that declares everything is told of no gaps');
    // The tone notice is NOT a gap — a declared transform is a fact about how
    // these colours must be read, and it is reported precisely BECAUSE the
    // manifest declared it. Closing it is not possible and not wanted.
    assert.deepEqual(report.notices.map((n) => [n.code, n.kind]),
      [['ASSET_TONE_TRANSFORM_DECLARED', 'info']]);
    const rec = readJson(join(proj.projectRoot, 'records', 'test_totem__r0.json'));
    assert.equal(rec.identity.subject_name, 'test_totem', 'the split engine has its authored family key');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('THE DRAGON SHAPE: the export requirements recorded in facet E11 addenda 3 ingest with zero gaps', async () => {
  // This is the acceptance test for asset #3's manifest, built to the shape the
  // addendum records for the on-acceptance dispatch:
  //   style register ultra-realistic + menacing, lora declared none (Ruling 10b)
  //   tone_transform toward the view-1 camera's emit-render id, operands materialized
  //   render_derivation emit / generated false, and therefore NO generation blocks
  //   identity.subject_name, so the split engine never guesses this subject's family
  // If this test ever fails, the lane has drifted from what facet was told it accepts.
  const proj = createTmpProject();
  const dir = withToneTransform((m) => {
    m.schema_version = '1.3.0';
    m.asset.id = 'dragon_totem';
    m.identity = { subject_name: 'dragon' };
    m.asset.style = {
      register: { terms: ['ultra-realistic', 'menacing'], ruling: 'E12 Ruling 10b', record: 'test://rulings/10b' },
      lora: { declared: 'none' },
    };
    m.asset.render_derivation = { kind: 'emit', generated: false, record: 'E11 Ruling 2' };
    // tone_transform.reference is 'r0' from the helper — standing in for the
    // view-1 camera's emit-render id, resolved at dispatch time from the
    // recorded frame derivation rather than asserted from memory.
    for (const r of m.renders) delete r.generation;
  });
  try {
    const report = await ingestAssetSource(proj.projectRoot, dir);

    assert.deepEqual(report.notices.filter((n) => n.kind === 'gap'), [],
      'a correctly-formed dragon export must produce NO gap notices — this is the defect 1.3.0 closed');
    assert.deepEqual(report.notices.map((n) => n.code).sort(),
      ['ASSET_RENDERS_ARE_DERIVATIONS', 'ASSET_TONE_TRANSFORM_DECLARED'],
      'both facts are still reported, as information');

    const prov = readJson(join(proj.projectRoot, 'records', 'dragon_totem__r0.json')).provenance;
    assert.deepEqual(prov.style.register_terms, ['ultra-realistic', 'menacing']);
    assert.deepEqual(prov.style.lora, { declared: 'none', card: null, weight: 0 });
    assert.equal(prov.render_derivation.generated, false);
    assert.equal(prov.generation, null, 'null by declaration, with render_derivation beside it to say so');
    assert.equal(prov.tone_transform.applied, true);
    assert.match(prov.tone_transform.operands.sha256, /^[0-9a-f]{64}$/);
    assert.ok(prov.tone_transform.operands.path.startsWith('assets/dragon_totem/'),
      'the operands are materialized into the project, not left pointing at the export tree');

    const rec = readJson(join(proj.projectRoot, 'records', 'dragon_totem__r0.json'));
    assert.equal(rec.identity.subject_name, 'dragon',
      'the standing errand is satisfied in the DATA, before any split exists');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});

test('notices replay from the receipt on a re-run rather than being recomputed', async () => {
  const proj = createTmpProject();
  const { dir } = writeDegenerateAsset();
  try {
    const first = await ingestAssetSource(proj.projectRoot, dir);
    const again = await ingestAssetSource(proj.projectRoot, dir);
    assert.equal(again.alreadyIngested, true);
    assert.deepEqual(again.notices.map((n) => n.code).sort(), first.notices.map((n) => n.code).sort(),
      'a re-run reports the same provenance gaps the original ingest did');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    proj.cleanup();
  }
});
