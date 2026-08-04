/**
 * SDL-M2 — the dataset row must carry the RESOLVED entity id (frontmatter.id,
 * falling back to the filename stem — see entryId() in load-entry.js), not
 * the raw, possibly-absent frontmatter.id.
 *
 * Before this fix, runBuild() computed `const id = entryId(entry)` (with the
 * filename-stem fallback) and used it correctly for prompts/<id>.j2 and
 * context/<id>.md, but then passed `entry: entry.frontmatter` — the RAW
 * object — into canonEntryToRow(), which reads `entry.id` for `entity_id`.
 * An entry with no explicit `id:` field therefore produced `entity_id:
 * undefined`, which serializeRow() drops from the JSON line entirely — the
 * row silently lost its own identity and was orphaned from the prompt/context
 * files that WERE named correctly via the fallback.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runBuild } from '../../lib/canon-build/build.js';
import { readDatasetJsonl } from '../../lib/rows.js';

async function scaffoldProject() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-m2-'));
  const projectRoot = join(tmp, 'proj');
  const canonRoot = join(tmp, 'canon');

  await mkdir(projectRoot, { recursive: true });
  await mkdir(join(projectRoot, 'canon-build'), { recursive: true });
  await writeFile(join(projectRoot, 'project.json'), JSON.stringify({ project_id: 'test' }));

  await mkdir(join(canonRoot, 'schemas'), { recursive: true });
  await mkdir(join(canonRoot, 'monsters'), { recursive: true });

  await writeFile(
    join(canonRoot, 'schemas', 'monster.schema.json'),
    JSON.stringify({ $id: 'monster', version: '1.0.0', type: 'object' }, null, 2),
  );

  await writeFile(
    join(projectRoot, 'canon-build', 'config.json'),
    JSON.stringify({
      project_id: 'test',
      canon_root: canonRoot,
      schema_dir: join(canonRoot, 'schemas'),
      entity_dirs: { 'monster.schema.json': 'monsters' },
      schema_to_lane: { 'monster.schema.json': { source: 'constant', value: 'creature' } },
    }, null, 2),
  );

  return { tmp, projectRoot, canonRoot };
}

// Deliberately NO `id:` field — this entry relies entirely on the
// filename-stem fallback in entryId().
const NO_ID_MONSTER_YAML = [
  '---',
  'species_tag: serpent',
  'signature_features:',
  '  - unblinking eyes',
  '  - coiled bulk',
  'anatomy_descriptor:',
  '  heads: 1',
  '  limbs: 0',
  '  notable: []',
  'forbidden_inputs:',
  '  - generic snake',
  'lineage_reference: none',
  'scale_indicator: larger',
  'sources:',
  '  - Apollodorus',
  '---',
  'A serpent with no explicit id field — must fall back to the filename stem.',
  '',
].join('\n');

async function fileExists(p) {
  try { await stat(p); return true; } catch { return false; }
}

test('runBuild: entry with no explicit id: gets entity_id = filename stem in the row (not undefined/dropped)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'unnamed-serpent.md'), NO_ID_MONSTER_YAML);

    const result = await runBuild({ projectRoot });
    assert.equal(result.entities_total, 1);

    const rows = await readDatasetJsonl(join(result.output_dir, 'dataset', 'all.jsonl'));
    assert.equal(rows.length, 1);
    const row = rows[0];

    // The core defect: entity_id must be the resolved filename-stem id, not
    // missing/undefined.
    assert.equal(row.entity_id, 'unnamed-serpent');
    assert.ok('entity_id' in row, 'entity_id key must survive serialization, not be dropped as undefined');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: subject_filter_key also carries the resolved id (same field, same fallback path)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'unnamed-serpent.md'), NO_ID_MONSTER_YAML);

    const result = await runBuild({ projectRoot });
    const rows = await readDatasetJsonl(join(result.output_dir, 'dataset', 'all.jsonl'));
    assert.equal(rows[0].subject_filter_key, 'unnamed-serpent');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: row entity_id matches the actual prompts/ and context/ filenames (no orphaning)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'unnamed-serpent.md'), NO_ID_MONSTER_YAML);

    const result = await runBuild({ projectRoot });
    const rows = await readDatasetJsonl(join(result.output_dir, 'dataset', 'all.jsonl'));
    const row = rows[0];

    // Before the fix, prompts/unnamed-serpent.j2 and context/unnamed-serpent.md
    // existed (they were always written using the resolved `id` variable),
    // but the row's entity_id was undefined — orphaning the row from these
    // very files. Confirm both exist AND match row.entity_id exactly.
    const promptPath = join(result.output_dir, 'prompts', `${row.entity_id}.j2`);
    const contextPath = join(result.output_dir, 'context', `${row.entity_id}.md`);
    assert.ok(await fileExists(promptPath), `expected ${promptPath} to exist`);
    assert.ok(await fileExists(contextPath), `expected ${contextPath} to exist`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: manifest.per_entity_hashes is keyed by the same resolved id as the row', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'unnamed-serpent.md'), NO_ID_MONSTER_YAML);

    const result = await runBuild({ projectRoot });
    const rows = await readDatasetJsonl(join(result.output_dir, 'dataset', 'all.jsonl'));

    const { readFile } = await import('node:fs/promises');
    const manifest = JSON.parse(await readFile(join(result.output_dir, 'manifest.json'), 'utf-8'));
    assert.ok(manifest.per_entity_hashes['unnamed-serpent'], 'manifest keys by the resolved id');
    assert.equal(rows[0].entity_id, 'unnamed-serpent');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- Regression guard: entries WITH an explicit id are unaffected ---

test('REGRESSION GUARD: entry with an explicit id: still resolves entity_id to that value (not the filename)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    const withId = [
      '---',
      'id: nemean-lion',
      'species_tag: quadruped',
      'signature_features:',
      '  - impenetrable golden hide',
      '  - maned head',
      'anatomy_descriptor:',
      '  heads: 1',
      '  limbs: 4',
      '  notable: []',
      'forbidden_inputs:',
      '  - generic lion',
      'lineage_reference: typhon-echidna',
      'scale_indicator: larger',
      'sources:',
      '  - Apollodorus II.5.1',
      '---',
      'Nemean Lion narrative prose.',
      '',
    ].join('\n');
    // Filename deliberately differs from the id, to prove the explicit id wins.
    await writeFile(join(canonRoot, 'monsters', 'some-other-filename.md'), withId);

    const result = await runBuild({ projectRoot });
    const rows = await readDatasetJsonl(join(result.output_dir, 'dataset', 'all.jsonl'));
    assert.equal(rows[0].entity_id, 'nemean-lion');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
