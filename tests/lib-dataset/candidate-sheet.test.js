/**
 * Candidate sheet — HTML contact sheet over an arbitrary directory of
 * images, no batch manifest required.
 *
 * Covers:
 *  - lib/candidate-sheet.js: recursive image walk (deterministic sort),
 *    asset_path-based record matching (NOT id/filename-guessing),
 *    pre-ingest degrade-to-filename, relative (non-base64) image src,
 *    HTML escaping, slug/output-path helpers.
 *  - scripts/sheet.js: --dry-run is genuinely side-effect-free, stable
 *    deterministic output path (regenerating overwrites, doesn't
 *    accumulate), path-traversal containment on both --project and <dir>,
 *    missing-directory and empty-directory handling.
 *  - Regression: lib/batch-sheet-render.js's renderSheetHTML/saveSheet (the
 *    existing `sdlab batch sheet` path) still works after exporting
 *    escapeHtml/computeColumns/generateCSS for reuse here.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdirSync, writeFileSync, rmSync, existsSync, readFileSync, readdirSync, mkdtempSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, relative, resolve } from 'node:path';

import { REPO_ROOT, getRunsDir } from '../../lib/paths.js';
import { renderSheetHTML, saveSheet } from '../../lib/batch-sheet-render.js';
import {
  walkImages,
  buildAssetPathIndex,
  buildCandidateSheetItems,
  renderCandidateSheetHTML,
  saveCandidateSheet,
  slugifyRelPath,
  defaultSheetOutputPath,
} from '../../lib/candidate-sheet.js';
import { createTmpProject, makeRecord } from './fixtures/make-project.js';

// ─── helpers ────────────────────────────────────────────────────────

/** A minimal (non-decoded) stand-in image file — nothing here parses bytes. */
const STUB_PNG = Buffer.from('stub-image-bytes');

function posix(p) {
  return p.replace(/\\/g, '/');
}

/** Real fixture project under REPO_ROOT/projects/<name> — needed for scripts/sheet.js's getProjectRoot() resolution. */
function makeCliFixture(name, files = {}) {
  const dir = join(REPO_ROOT, 'projects', name);
  mkdirSync(dir, { recursive: true });
  for (const [rel, content] of Object.entries(files)) {
    const full = join(dir, rel);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, content);
  }
  return dir;
}

function removeCliFixture(name) {
  rmSync(join(REPO_ROOT, 'projects', name), { recursive: true, force: true });
}

/** Extract ordered cand-id / cand-id--missing text content from rendered HTML, in tile order. */
function extractTileLabels(html) {
  const out = [];
  const re = /<span class="cand-id[^"]*">([^<]*)<\/span>/g;
  let m;
  while ((m = re.exec(html))) out.push(m[1]);
  return out;
}

// ─── lib: walkImages ───────────────────────────────────────────────

test('walkImages: recurses into subdirectories and filters to known image extensions', async () => {
  const proj = createTmpProject({ records: [] });
  try {
    const root = join(proj.projectRoot, 'outputs', 'candidates');
    mkdirSync(join(root, 'w1'), { recursive: true });
    mkdirSync(join(root, 'w2'), { recursive: true });
    // Written in a scrambled, non-sorted order on purpose.
    writeFileSync(join(root, 'w2', 'c.png'), STUB_PNG);
    writeFileSync(join(root, 'top.jpg'), STUB_PNG);
    writeFileSync(join(root, 'w1', 'b.webp'), STUB_PNG);
    writeFileSync(join(root, 'w1', 'a.png'), STUB_PNG);
    // Noise that must be ignored: non-image files.
    writeFileSync(join(root, 'notes.txt'), 'not an image');
    writeFileSync(join(root, 'w1', 'manifest.json'), '{}');

    const images = await walkImages(root);
    const rels = images.map((p) => posix(relative(root, p)));

    assert.deepEqual(rels, ['top.jpg', 'w1/a.png', 'w1/b.webp', 'w2/c.png'],
      'expected deterministic sorted order across nested directories, images only');
  } finally {
    proj.cleanup();
  }
});

test('walkImages: a missing directory returns an empty array, does not throw', async () => {
  const bareDir = mkdtempSync(join(tmpdir(), 'sdlab-bare-'));
  try {
    const images = await walkImages(join(bareDir, 'does-not-exist'));
    assert.deepEqual(images, []);
  } finally {
    rmSync(bareDir, { recursive: true, force: true });
  }
});

// ─── lib: buildAssetPathIndex ──────────────────────────────────────

test('buildAssetPathIndex: indexes records by asset_path and skips malformed record files', async () => {
  const proj = createTmpProject({
    records: [
      makeRecord({ id: 'good_one', assetPath: 'outputs/candidates/good.png' }),
    ],
  });
  try {
    // A malformed record file must not abort the whole scan.
    writeFileSync(join(proj.projectRoot, 'records', 'broken.json'), '{ this is not valid json');

    const index = await buildAssetPathIndex(proj.projectRoot);
    assert.equal(index.size, 1, 'malformed record should be skipped, not counted or fatal');
    assert.ok(index.has('outputs/candidates/good.png'));
    assert.equal(index.get('outputs/candidates/good.png').id, 'good_one');
  } finally {
    proj.cleanup();
  }
});

test('buildAssetPathIndex: a project with no records/ directory yields an empty index, not a throw', async () => {
  const bareDir = mkdtempSync(join(tmpdir(), 'sdlab-bare-'));
  try {
    const index = await buildAssetPathIndex(bareDir);
    assert.equal(index.size, 0);
  } finally {
    rmSync(bareDir, { recursive: true, force: true });
  }
});

// ─── lib: buildCandidateSheetItems ─────────────────────────────────

test('buildCandidateSheetItems: matches by asset_path even when record id does NOT match the filename convention', async () => {
  // The whole point of asset_path-keyed matching: lib/reingest.js prefixes
  // ids with "gen_", hand-curated records use the bare stem — asset_path is
  // the one field both conventions agree on.
  const proj = createTmpProject({
    records: [
      makeRecord({
        id: 'gen_totally_unrelated_name',
        status: 'approved',
        assetPath: 'outputs/candidates/mismatched-file.png',
      }),
    ],
  });
  try {
    const dir = join(proj.projectRoot, 'outputs', 'candidates');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'mismatched-file.png'), STUB_PNG);

    const items = await buildCandidateSheetItems(proj.projectRoot, dir);
    assert.equal(items.length, 1);
    const [item] = items;
    assert.equal(item.hasRecord, true);
    assert.equal(item.id, 'gen_totally_unrelated_name', 'id must come from the matched record, not be guessed from the filename');
    assert.equal(item.status, 'approved');
    assert.equal(item.filename, 'mismatched-file.png');
  } finally {
    proj.cleanup();
  }
});

test('buildCandidateSheetItems: an image with no matching record degrades to filename, does not crash (pre-ingest state)', async () => {
  const proj = createTmpProject({ records: [] });
  try {
    const dir = join(proj.projectRoot, 'outputs', 'candidates');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'never_ingested.png'), STUB_PNG);

    const items = await buildCandidateSheetItems(proj.projectRoot, dir);
    assert.equal(items.length, 1);
    const [item] = items;
    assert.equal(item.hasRecord, false);
    assert.equal(item.id, null);
    assert.equal(item.status, null);
    assert.equal(item.prompt, null);
    assert.equal(item.filename, 'never_ingested.png');
  } finally {
    proj.cleanup();
  }
});

test('buildCandidateSheetItems: a record with no judgment yet reports status "uncurated" (distinct from "no record at all")', async () => {
  const proj = createTmpProject({ records: [] });
  try {
    // Write a record directly (bypassing makeRecord's default judgment) so judgment is null.
    const rec = {
      id: 'waiting_for_review',
      schema_version: '2.0.0',
      created_at: '2026-01-01T00:00:00.000Z',
      asset_path: 'outputs/candidates/waiting.png',
      image: { format: 'png', width: 10, height: 10, bytes: 10 },
      provenance: { prompt: 'a test prompt for an uncurated candidate' },
      judgment: null,
      canon: null,
      iteration: null,
    };
    writeFileSync(join(proj.projectRoot, 'records', `${rec.id}.json`), JSON.stringify(rec));

    const dir = join(proj.projectRoot, 'outputs', 'candidates');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'waiting.png'), STUB_PNG);

    const items = await buildCandidateSheetItems(proj.projectRoot, dir);
    const [item] = items;
    assert.equal(item.hasRecord, true, 'a record exists, even though it has not been judged yet');
    assert.equal(item.status, 'uncurated');
    assert.equal(item.prompt, 'a test prompt for an uncurated candidate');
  } finally {
    proj.cleanup();
  }
});

test('buildCandidateSheetItems: ordering is deterministic across repeated calls (stable regeneration)', async () => {
  const proj = createTmpProject({ records: [] });
  try {
    const dir = join(proj.projectRoot, 'outputs', 'candidates');
    mkdirSync(join(dir, 'sub'), { recursive: true });
    writeFileSync(join(dir, 'zzz.png'), STUB_PNG);
    writeFileSync(join(dir, 'aaa.png'), STUB_PNG);
    writeFileSync(join(dir, 'sub', 'mmm.png'), STUB_PNG);

    const first = await buildCandidateSheetItems(proj.projectRoot, dir);
    const second = await buildCandidateSheetItems(proj.projectRoot, dir);

    const firstOrder = first.map((i) => i.relFromRoot);
    const secondOrder = second.map((i) => i.relFromRoot);
    assert.deepEqual(firstOrder, secondOrder, 'two calls over an unchanged directory must yield the same order');
    assert.deepEqual(firstOrder, [
      'outputs/candidates/aaa.png',
      'outputs/candidates/sub/mmm.png',
      'outputs/candidates/zzz.png',
    ]);
  } finally {
    proj.cleanup();
  }
});

// ─── lib: renderCandidateSheetHTML ─────────────────────────────────

test('renderCandidateSheetHTML: image src is a relative path that resolves to the real file — never base64/data URI', async () => {
  const proj = createTmpProject({
    records: [makeRecord({ id: 'quay_01', status: 'borderline', assetPath: 'outputs/candidates/w1/quay-01.png' })],
  });
  try {
    const dir = join(proj.projectRoot, 'outputs', 'candidates', 'w1');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'quay-01.png'), STUB_PNG);

    const items = await buildCandidateSheetItems(proj.projectRoot, dir);
    const sheetOutputDir = join(proj.projectRoot, 'outputs', 'sheets');
    const html = renderCandidateSheetHTML({
      items,
      title: 'Test sheet',
      sourceLabel: 'outputs/candidates/w1',
      sheetOutputDir,
      generatedAt: '2026-01-01T00:00:00.000Z',
    });

    assert.ok(!/data:image/.test(html), 'must not embed images as data URIs');
    assert.ok(!/base64/.test(html), 'must not base64-encode images');

    const match = html.match(/<img src="([^"]+)"/);
    assert.ok(match, 'expected an <img src="..."> tag');
    const src = match[1];
    assert.ok(!src.startsWith('/') && !/^[A-Za-z]:[\\/]/.test(src), `src must be a relative path, got: ${src}`);
    const resolved = resolve(sheetOutputDir, src);
    assert.equal(resolved, resolve(items[0].absPath), 'the relative src must resolve to the actual image file from where the sheet is written');
  } finally {
    proj.cleanup();
  }
});

test('renderCandidateSheetHTML: escapes HTML-significant characters in id and prompt', async () => {
  const items = [{
    absPath: join(process.cwd(), 'fake.png'),
    relFromRoot: 'outputs/candidates/fake.png',
    filename: 'fake.png',
    id: '<script>alert(1)</script>',
    status: 'approved',
    prompt: 'a "quoted" & <b>bold</b> prompt',
    hasRecord: true,
  }];
  const html = renderCandidateSheetHTML({
    items,
    title: 'Escaping test',
    sourceLabel: 'outputs/candidates',
    sheetOutputDir: process.cwd(),
    generatedAt: '2026-01-01T00:00:00.000Z',
  });

  assert.ok(!html.includes('<script>alert(1)</script>'), 'raw script tag must not appear unescaped');
  assert.ok(html.includes('&lt;script&gt;'), 'id must be HTML-escaped');
  assert.ok(html.includes('&amp;'), 'ampersand in prompt must be escaped');
});

test('renderCandidateSheetHTML: a pre-ingest tile (no record) shows the filename and a "no record" marker instead of crashing', async () => {
  const items = [{
    absPath: join(process.cwd(), 'mystery_007.png'),
    relFromRoot: 'outputs/candidates/mystery_007.png',
    filename: 'mystery_007.png',
    id: null,
    status: null,
    prompt: null,
    hasRecord: false,
  }];
  const html = renderCandidateSheetHTML({
    items,
    title: 'Pre-ingest test',
    sourceLabel: 'outputs/candidates',
    sheetOutputDir: process.cwd(),
    generatedAt: '2026-01-01T00:00:00.000Z',
  });

  assert.ok(html.includes('mystery_007.png'));
  assert.ok(html.includes('cand-status--none'));
  assert.ok(/no record/.test(html));
});

test('renderCandidateSheetHTML: zero items still renders a valid document without throwing', () => {
  const html = renderCandidateSheetHTML({
    items: [],
    title: 'Empty sheet',
    sourceLabel: 'outputs/candidates',
    sheetOutputDir: process.cwd(),
    generatedAt: '2026-01-01T00:00:00.000Z',
  });
  assert.match(html, /<!DOCTYPE html>/);
  assert.match(html, /0 images/);
});

// ─── lib: saveCandidateSheet / slugifyRelPath / defaultSheetOutputPath ─

test('saveCandidateSheet: writes the file, creating parent directories as needed', async () => {
  const tmp = mkdtempSync(join(tmpdir(), 'sdlab-save-'));
  try {
    const outPath = join(tmp, 'outputs', 'sheets', 'sheet.html');
    const written = await saveCandidateSheet(outPath, '<p>hello</p>');
    assert.equal(written, outPath);
    assert.ok(existsSync(outPath));
    assert.equal(readFileSync(outPath, 'utf-8'), '<p>hello</p>');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('slugifyRelPath: stable, filesystem-safe slug for common source directories', () => {
  assert.equal(slugifyRelPath('outputs/candidates'), 'outputs-candidates');
  assert.equal(slugifyRelPath('outputs/approved'), 'outputs-approved');
  assert.equal(slugifyRelPath('outputs\\candidates'), 'outputs-candidates', 'backslashes normalize the same as forward slashes');
  assert.equal(slugifyRelPath(''), 'sheet', 'empty input falls back to a safe default rather than an empty filename');
});

test('defaultSheetOutputPath: same source dir always maps to the same output path (regeneration overwrites, does not accumulate)', () => {
  const a = defaultSheetOutputPath('/proj', 'outputs/candidates');
  const b = defaultSheetOutputPath('/proj', 'outputs/candidates');
  assert.equal(a, b);
});

// ─── scripts/sheet.js — CLI integration ────────────────────────────

test('sheet.js --dry-run is genuinely side-effect-free', async () => {
  const name = 'sheet-test-dry-run';
  makeCliFixture(name, {
    'outputs/candidates/only.png': STUB_PNG,
  });
  try {
    const { run } = await import('../../scripts/sheet.js');
    await run(['--project', name, '--dry-run']);
    assert.equal(existsSync(join(REPO_ROOT, 'projects', name, 'outputs', 'sheets')), false,
      'outputs/sheets must not be created by a dry run');
  } finally {
    removeCliFixture(name);
  }
});

test('sheet.js: writes a deterministic HTML sheet with matched + pre-ingest tiles, no base64', async () => {
  const name = 'sheet-test-write';
  const record = {
    id: 'gen_hero_pose_01',
    schema_version: '2.0.0',
    created_at: '2026-01-01T00:00:00.000Z',
    asset_path: 'outputs/candidates/hero-pose-01.png',
    image: { format: 'png', width: 10, height: 10, bytes: 10 },
    provenance: { prompt: 'a hero in a dynamic pose, painterly style' },
    judgment: { status: 'approved', reviewer: 'human:mike' },
    canon: null,
    iteration: null,
  };
  makeCliFixture(name, {
    'records/gen_hero_pose_01.json': JSON.stringify(record),
    'outputs/candidates/hero-pose-01.png': STUB_PNG,
    'outputs/candidates/mystery-002.png': STUB_PNG, // pre-ingest — no record
  });
  try {
    const { run } = await import('../../scripts/sheet.js');
    await run(['--project', name]);

    const sheetPath = join(REPO_ROOT, 'projects', name, 'outputs', 'sheets', 'outputs-candidates.html');
    assert.ok(existsSync(sheetPath), 'expected the default deterministic sheet path to exist');
    const html = readFileSync(sheetPath, 'utf-8');

    assert.ok(html.includes('gen_hero_pose_01'), 'matched record id should appear');
    assert.ok(html.includes('cand-status--approved'), 'matched record status should appear');
    assert.ok(html.includes('mystery-002.png'), 'pre-ingest image should degrade to filename, not vanish');
    assert.ok(html.includes('cand-status--none'), 'pre-ingest image should show a no-record marker');
    assert.ok(!/data:image|base64/.test(html), 'must reference images by path, not embed them');
    assert.ok(html.includes('../candidates/hero-pose-01.png'.replace('/', '/')) || html.includes('candidates/hero-pose-01.png'),
      'image src should be a relative path into outputs/candidates');
  } finally {
    removeCliFixture(name);
  }
});

test('sheet.js: regenerating overwrites the same deterministic path — no duplicate/timestamped files', async () => {
  const name = 'sheet-test-idempotent';
  makeCliFixture(name, {
    'outputs/candidates/a.png': STUB_PNG,
    'outputs/candidates/b.png': STUB_PNG,
  });
  try {
    const { run } = await import('../../scripts/sheet.js');
    await run(['--project', name]);
    const sheetsDir = join(REPO_ROOT, 'projects', name, 'outputs', 'sheets');
    const firstListing = readdirSync(sheetsDir);
    const firstHtml = readFileSync(join(sheetsDir, firstListing[0]), 'utf-8');

    await run(['--project', name]);
    const secondListing = readdirSync(sheetsDir);
    const secondHtml = readFileSync(join(sheetsDir, secondListing[0]), 'utf-8');

    assert.equal(firstListing.length, 1, 'exactly one sheet file — regeneration overwrites, does not accumulate');
    assert.deepEqual(firstListing, secondListing, 'same filename both times');
    assert.deepEqual(extractTileLabels(firstHtml), extractTileLabels(secondHtml), 'tile order must be stable across regenerations');
  } finally {
    removeCliFixture(name);
  }
});

test('sheet.js: --out overrides the output location (still contained within the project)', async () => {
  const name = 'sheet-test-out-override';
  makeCliFixture(name, {
    'outputs/candidates/a.png': STUB_PNG,
  });
  try {
    const { run } = await import('../../scripts/sheet.js');
    await run(['--project', name, '--out', 'custom/review.html']);
    const customPath = join(REPO_ROOT, 'projects', name, 'custom', 'review.html');
    assert.ok(existsSync(customPath));
    assert.equal(existsSync(join(REPO_ROOT, 'projects', name, 'outputs', 'sheets')), false,
      'the default outputs/sheets/ path should not be created when --out is given');
  } finally {
    removeCliFixture(name);
  }
});

test('sheet.js: rejects a <dir> that escapes the project root (path traversal)', async () => {
  const name = 'sheet-test-traversal';
  makeCliFixture(name, {});
  try {
    const { run } = await import('../../scripts/sheet.js');
    await assert.rejects(
      () => run(['../../../etc', '--project', name]),
      (err) => err.code === 'INPUT_PATH_TRAVERSAL'
    );
    assert.equal(existsSync(join(REPO_ROOT, 'projects', name, 'outputs', 'sheets')), false);
  } finally {
    removeCliFixture(name);
  }
});

test('sheet.js: rejects a --project value containing ".." (matches the repo-wide traversal guard)', async () => {
  const { run } = await import('../../scripts/sheet.js');
  await assert.rejects(
    () => run(['--project', '../../ai-eyes-mcp']),
    (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME'
  );
});

test('sheet.js: a nonexistent source directory raises a clear input error instead of crashing', async () => {
  const name = 'sheet-test-missing-dir';
  makeCliFixture(name, {});
  try {
    const { run } = await import('../../scripts/sheet.js');
    await assert.rejects(
      () => run(['outputs/does-not-exist', '--project', name]),
      (err) => err.code === 'INPUT_DIR_NOT_FOUND'
    );
  } finally {
    removeCliFixture(name);
  }
});

test('sheet.js: an existing but empty directory does not throw and writes nothing', async () => {
  const name = 'sheet-test-empty-dir';
  makeCliFixture(name, {});
  mkdirSync(join(REPO_ROOT, 'projects', name, 'outputs', 'candidates'), { recursive: true });
  try {
    const { run } = await import('../../scripts/sheet.js');
    await run(['--project', name]); // must not throw
    assert.equal(existsSync(join(REPO_ROOT, 'projects', name, 'outputs', 'sheets')), false,
      'nothing to render — no sheet file should be written');
  } finally {
    removeCliFixture(name);
  }
});

// ─── regression: the existing `sdlab batch sheet` path ─────────────

test('regression: renderSheetHTML/saveSheet (the existing sdlab batch sheet path) still works after exporting shared helpers', async () => {
  const proj = createTmpProject({ records: [] });
  try {
    const runId = 'run_test_001';
    const runOutputsDir = join(getRunsDir(proj.projectRoot), runId, 'outputs');
    mkdirSync(runOutputsDir, { recursive: true });
    writeFileSync(join(runOutputsDir, 'out.png'), STUB_PNG);

    const batchDir = join(proj.projectRoot, 'batches', 'batch_2025-01-01_001');
    mkdirSync(join(batchDir, 'sheets'), { recursive: true });

    const manifest = {
      batch_id: 'batch_2025-01-01_001',
      project_id: 'testproj',
      mode_id: 'expression-sheet',
      created_at: '2025-01-01T00:00:00.000Z',
      subject_id: 'test-subject',
      slots: [
        { slot_id: 's1', label: 'Neutral', run_id: runId, selected_output: 'out.png' },
      ],
    };
    const mode = { batch_type: 'expression_sheet', assembly: { layout: 'grid' } };

    const html = renderSheetHTML({ manifest, mode, projectRoot: proj.projectRoot, batchDir });

    assert.match(html, /<!DOCTYPE html>/);
    assert.match(html, /batch_2025-01-01_001/);
    assert.match(html, /Neutral/);

    const expectedImgRel = posix(relative(join(batchDir, 'sheets'), join(runOutputsDir, 'out.png')));
    assert.ok(html.includes(`src="${expectedImgRel}"`), `expected image src "${expectedImgRel}" to resolve — the batch path must still find its images`);
    assert.ok(!html.includes('no output'), 'should render the real image, not the missing-output placeholder');

    const sheetPath = await saveSheet(batchDir, 'primary-sheet.html', html);
    assert.ok(existsSync(sheetPath));
    assert.equal(readFileSync(sheetPath, 'utf-8'), html);
  } finally {
    proj.cleanup();
  }
});
