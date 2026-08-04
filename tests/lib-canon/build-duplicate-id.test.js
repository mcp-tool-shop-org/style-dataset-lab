/**
 * SDL-M1 — runBuild() must detect duplicate entity ids and refuse BEFORE any
 * output is written, instead of letting two entries silently collide.
 *
 * Before this fix, the discovery loop pushed {entry, schemaName, id} with no
 * collision check. Two entries sharing an id would overwrite each other's
 * prompts/<id>.j2 and context/<id>.md (path collision), collide in
 * manifest.per_entity_hashes (last write wins, silently), while
 * dataset/all.jsonl kept BOTH rows under the one id — so one row permanently
 * points at the other entry's content. This is a realistic authoring mistake
 * in this repo: canon is visibly authored by cloning an existing file (see
 * projects/portlight-ships/canon/ships/*.md, near-identical structure across
 * files), so a forgotten `id:` edit after cloning triggers it directly.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runBuild } from '../../lib/canon-build/build.js';

async function scaffoldProject() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-dup-'));
  const projectRoot = join(tmp, 'proj');
  const canonRoot = join(tmp, 'canon');

  await mkdir(projectRoot, { recursive: true });
  await mkdir(join(projectRoot, 'canon-build'), { recursive: true });
  await writeFile(join(projectRoot, 'project.json'), JSON.stringify({ project_id: 'test' }));

  await mkdir(join(canonRoot, 'schemas'), { recursive: true });
  await mkdir(join(canonRoot, 'monsters'), { recursive: true });
  await mkdir(join(canonRoot, 'characters'), { recursive: true });

  await writeFile(
    join(canonRoot, 'schemas', 'monster.schema.json'),
    JSON.stringify({ $id: 'monster', version: '1.0.0', type: 'object' }, null, 2),
  );
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
      entity_dirs: {
        'monster.schema.json': 'monsters',
        'character.schema.json': 'characters',
      },
      schema_to_lane: {
        'monster.schema.json': { source: 'constant', value: 'creature' },
        'character.schema.json': { source: 'field', field: 'visual.art_lane' },
      },
    }, null, 2),
  );

  return { tmp, projectRoot, canonRoot };
}

function monsterYaml(id, notable) {
  return [
    '---',
    `id: ${id}`,
    'species_tag: quadruped',
    'signature_features:',
    '  - impenetrable golden hide',
    '  - maned head',
    'anatomy_descriptor:',
    '  heads: 1',
    '  limbs: 4',
    `  notable: [${JSON.stringify(notable)}]`,
    'forbidden_inputs:',
    '  - generic lion',
    'lineage_reference: typhon-echidna',
    'scale_indicator: larger',
    'sources:',
    '  - Apollodorus II.5.1',
    '---',
    `Narrative prose for ${notable}.`,
    '',
  ].join('\n');
}

function characterYaml(id) {
  return [
    '---',
    `id: ${id}`,
    'kind: hero',
    'visual:',
    '  silhouette_cue: club-and-lion-hide',
    '  attire: lion-skin cloak',
    '  build: heroic-muscular',
    '  hair: sun-streaked long hair',
    '  eyes: dark, brooding',
    '  age_band: young-adult',
    '  art_lane: full-body',
    '  palette:',
    '    - "#c2a179"',
    'narrative:',
    '  role: Protagonist',
    '  voice:',
    '    - blunt',
    '    - wry',
    '  motivation: Atonement',
    '  arc_beats:',
    '    - Birth',
    '    - Labors',
    '    - Apotheosis',
    'sources:',
    '  - Apollodorus',
    '---',
    'Character narrative prose.',
    '',
  ].join('\n');
}

async function fileExists(p) {
  try {
    await readdir(p);
    return true;
  } catch {
    return false;
  }
}

// --- RED-branch coverage: duplicate id within the same schema dir ---

test('runBuild: two monster entries sharing an id throws CANON_DUPLICATE_ENTITY_ID naming both files', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'nemean-lion.md'), monsterYaml('shared-id', 'golden-hide'));
    await writeFile(join(canonRoot, 'monsters', 'nemean-lion-clone.md'), monsterYaml('shared-id', 'golden-hide-2'));

    await assert.rejects(
      () => runBuild({ projectRoot }),
      (err) => {
        assert.equal(err.code, 'CANON_DUPLICATE_ENTITY_ID');
        assert.match(err.message, /shared-id/);
        assert.match(err.message, /nemean-lion\.md/);
        assert.match(err.message, /nemean-lion-clone\.md/);
        return true;
      },
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- RED-branch coverage: duplicate id ACROSS schema types (global uniqueness) ---

test('runBuild: a monster and a character sharing an id throws (ids are global, not per-schema)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'nemean-lion.md'), monsterYaml('heracles', 'golden-hide'));
    await writeFile(join(canonRoot, 'characters', 'heracles.md'), characterYaml('heracles'));

    await assert.rejects(
      () => runBuild({ projectRoot }),
      (err) => err.code === 'CANON_DUPLICATE_ENTITY_ID' && /heracles/.test(err.message),
      'ids collide across prompts/, context/, and manifest.per_entity_hashes regardless of schema kind',
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- Refuses BEFORE any output is written ---

test('runBuild: duplicate-id failure writes nothing (no partial output dir left behind)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'a.md'), monsterYaml('dup', 'x'));
    await writeFile(join(canonRoot, 'monsters', 'b.md'), monsterYaml('dup', 'y'));

    await assert.rejects(() => runBuild({ projectRoot }), (err) => err.code === 'CANON_DUPLICATE_ENTITY_ID');

    // No canon-build output directories (real output or .tmp staging) should
    // exist — the throw happens during discovery, well before the write phase.
    const canonBuildContents = await readdir(join(projectRoot, 'canon-build'));
    const nonConfigEntries = canonBuildContents.filter((n) => n !== 'config.json');
    assert.deepEqual(nonConfigEntries, [], `expected no build output, found: ${nonConfigEntries.join(', ')}`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- Regression guard: distinct ids never false-positive ---

test('REGRESSION GUARD: entries with distinct ids across schema types build successfully (no false positive)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'nemean-lion.md'), monsterYaml('nemean-lion', 'golden-hide'));
    await writeFile(join(canonRoot, 'characters', 'heracles.md'), characterYaml('heracles'));

    const result = await runBuild({ projectRoot });
    assert.equal(result.entities_total, 2);
    assert.equal(result.rows, 2);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- --only filter interacts correctly: a duplicate OUTSIDE the filter is not flagged ---

test('runBuild: --only filter skips duplicate ids that are filtered out before the check', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeFile(join(canonRoot, 'monsters', 'a.md'), monsterYaml('dup', 'x'));
    await writeFile(join(canonRoot, 'monsters', 'b.md'), monsterYaml('dup', 'y'));
    await writeFile(join(canonRoot, 'characters', 'heracles.md'), characterYaml('heracles'));

    // --only heracles never touches the duplicated "dup" id at all.
    const result = await runBuild({ projectRoot, only: ['heracles'] });
    assert.equal(result.entities_total, 1);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
