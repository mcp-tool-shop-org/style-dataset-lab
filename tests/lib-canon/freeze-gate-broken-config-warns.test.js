/**
 * SDL-M3 — loadAllCanonEntries() must not silently disable the freeze gate
 * project-wide when canon-build/config.json is broken.
 *
 * The degrade-to-"no gate" behavior on an invalid config is INTENTIONAL and
 * kept as-is (a config typo should not turn into "no one can generate,
 * curate, or paint anything in this project"). The defect was that this
 * degrade-open happened with zero operator signal: no warn(), just a code
 * comment. The fix adds a loud stderr warning naming the config error, so
 * "freeze gate is off" is never silent.
 *
 * This is NOT a REFUSE-branch fix (the gate is deliberately designed to stay
 * open here) — so this file proves two things instead:
 *   1. The warning actually fires, with the underlying config error named,
 *      whenever the gate degrades open due to a broken config.
 *   2. The gate's real REFUSE branch (a frozen entry, valid config) still
 *      works after this change — i.e. touching loadAllCanonEntries's catch
 *      block did not regress the success path that everything else in
 *      freeze-gate.js depends on.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  loadAllCanonEntries,
  resolveEntryBySubject,
  assertNotFrozenBySubject,
} from '../../lib/freeze-gate.js';

function captureStderr(fn) {
  const orig = console.error;
  const err = [];
  console.error = (...a) => err.push(a.join(' '));
  return Promise.resolve(fn())
    .then((result) => ({ result, err }))
    .finally(() => { console.error = orig; });
}

async function scaffoldWithBrokenConfig(configContents) {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-m3-'));
  const projectRoot = join(tmp, 'proj');
  await mkdir(join(projectRoot, 'canon-build'), { recursive: true });
  await writeFile(join(projectRoot, 'canon-build', 'config.json'), configContents);
  return { tmp, projectRoot };
}

// --- Malformed JSON ---

test('loadAllCanonEntries: invalid JSON in config.json warns loudly and degrades to []', async () => {
  const { tmp, projectRoot } = await scaffoldWithBrokenConfig('{ this is not valid json');
  try {
    const { result, err } = await captureStderr(() => loadAllCanonEntries(projectRoot));
    assert.deepEqual(result, [], 'still degrades to no-gate (intentional, unchanged)');
    assert.ok(err.length >= 1, 'must print at least one warning to stderr');
    const joined = err.join('\n');
    assert.match(joined, /canon-build\/config\.json/, 'names the config file');
    assert.match(joined, /invalid|not valid JSON/i, 'surfaces the underlying error');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- Structurally invalid config (valid JSON, missing required fields) ---

test('loadAllCanonEntries: structurally invalid config (missing entity_dirs) warns loudly', async () => {
  const { tmp, projectRoot } = await scaffoldWithBrokenConfig(
    JSON.stringify({ project_id: 'test' }), // missing canon_root, schema_dir, entity_dirs, schema_to_lane
  );
  try {
    const { result, err } = await captureStderr(() => loadAllCanonEntries(projectRoot));
    assert.deepEqual(result, []);
    assert.ok(err.length >= 1, 'must warn even though config.json IS valid JSON');
    assert.match(err.join('\n'), /canon-build\/config\.json/);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- The warning propagates through the higher-level gate helpers too ---

test('resolveEntryBySubject: broken config warns AND returns null (silent-but-now-audible degrade)', async () => {
  const { tmp, projectRoot } = await scaffoldWithBrokenConfig('{ broken');
  try {
    const { result, err } = await captureStderr(() => resolveEntryBySubject(projectRoot, 'anyone'));
    assert.equal(result, null);
    assert.ok(err.length >= 1, 'resolveEntryBySubject must surface the warning via loadAllCanonEntries');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('assertNotFrozenBySubject: broken config warns AND does not block the write (unchanged degrade-open)', async () => {
  const { tmp, projectRoot } = await scaffoldWithBrokenConfig('{ broken');
  try {
    const { result, err } = await captureStderr(() =>
      assertNotFrozenBySubject(projectRoot, 'anyone', { action: 'generate' }),
    );
    // No throw — assertNotFrozenBySubject resolves to undefined when it does
    // not block. The important assertion is that it did NOT reject.
    assert.equal(result, undefined);
    assert.ok(err.length >= 1, 'the caller must see the warning even though the write proceeds');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- No config file at all is a DIFFERENT, still-silent case (not the defect) ---

test('loadAllCanonEntries: NO config.json at all stays silent (project simply is not canon-integrated yet)', async () => {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-m3-'));
  try {
    const projectRoot = join(tmp, 'proj');
    await mkdir(projectRoot, { recursive: true }); // no canon-build/ dir at all
    const { result, err } = await captureStderr(() => loadAllCanonEntries(projectRoot));
    assert.deepEqual(result, []);
    assert.equal(err.length, 0, 'a project that never opted into canon-build must stay silent — only a BROKEN config warns');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- REFUSE-branch regression guard: valid config + frozen entry still blocks ---

async function scaffoldValidProjectWithFrozenEntry() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-m3-valid-'));
  const projectRoot = join(tmp, 'proj');
  const canonRoot = join(tmp, 'canon');
  await mkdir(join(projectRoot, 'canon-build'), { recursive: true });
  await mkdir(join(canonRoot, 'schemas'), { recursive: true });
  await mkdir(join(canonRoot, 'characters'), { recursive: true });

  await writeFile(
    join(canonRoot, 'schemas', 'character.schema.json'),
    JSON.stringify({ $id: 'character', version: '1.0.0', type: 'object' }, null, 2),
  );
  await writeFile(
    join(projectRoot, 'canon-build', 'config.json'),
    JSON.stringify({
      project_id: 'test',
      canon_root: canonRoot,
      schema_dir: join(canonRoot, 'schemas'),
      entity_dirs: { 'character.schema.json': 'characters' },
      schema_to_lane: { 'character.schema.json': { source: 'field', field: 'visual.art_lane' } },
    }, null, 2),
  );
  const yaml = [
    'id: heracles',
    'kind: hero',
    'visual:',
    '  silhouette_cue: x',
    '  attire: y',
    '  build: athletic',
    '  hair: z',
    '  eyes: a',
    '  age_band: young-adult',
    '  art_lane: portrait',
    '  palette:',
    '    - "#ffffff"',
    'narrative:',
    '  role: r',
    '  voice:',
    '    - a',
    '    - b',
    '  motivation: x',
    '  arc_beats:',
    '    - a',
    '    - b',
    '    - c',
    'sources:',
    '  - x',
    'freeze:',
    '  status: frozen',
    '  frozen_by: mike',
    '  frozen_reason: "hero moment"',
  ].join('\n');
  await writeFile(join(canonRoot, 'characters', 'heracles.md'), `---\n${yaml}\n---\n`);
  return { tmp, projectRoot };
}

test('REGRESSION GUARD: valid config + frozen entry still refuses (warn() addition did not break the success path)', async () => {
  const { tmp, projectRoot } = await scaffoldValidProjectWithFrozenEntry();
  try {
    const { result, err } = await captureStderr(() => loadAllCanonEntries(projectRoot));
    assert.equal(result.length, 1, 'valid config still loads the one entry');
    assert.equal(err.length, 0, 'a valid config must never warn');

    await assert.rejects(
      () => assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'generate' }),
      (e) => e.code === 'CANON_ENTRY_FROZEN',
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
