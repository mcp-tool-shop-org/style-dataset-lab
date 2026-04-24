/**
 * End-to-end orchestrator tests for `sdlab canon build`.
 *
 * Spins up a temp project + canon tree, runs the build, and verifies
 * the three projections land with the right shape. Also exercises
 * cache hit/miss, dry-run, --only filter, and schema-change full rebuild.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, readdir, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runBuild } from '../../lib/canon-build/build.js';
import { readDatasetJsonl } from '../../lib/rows.js';

// ─── Fixture helpers ───────────────────────────────────────────────

async function scaffoldProject() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-build-'));
  const projectRoot = join(tmp, 'proj');
  const canonRoot = join(tmp, 'canon');

  // Project-side layout
  await mkdir(projectRoot, { recursive: true });
  await mkdir(join(projectRoot, 'canon-build'), { recursive: true });
  await mkdir(join(projectRoot, 'training', 'profiles'), { recursive: true });
  // project config files (empty is fine — computeConfigFingerprint tolerates absence)
  await writeFile(join(projectRoot, 'project.json'), JSON.stringify({ project_id: 'test' }));

  // Canon-side layout
  await mkdir(join(canonRoot, 'schemas'), { recursive: true });
  await mkdir(join(canonRoot, 'monsters'), { recursive: true });
  await mkdir(join(canonRoot, 'characters'), { recursive: true });

  return { tmp, projectRoot, canonRoot };
}

async function writeMinSchemas(canonRoot) {
  // Minimal schemas that carry version + additionalProperties:false would be
  // overkill for the build step (we don't validate entries here); the build
  // only reads version + file bytes for hashing.
  await writeFile(
    join(canonRoot, 'schemas', 'monster.schema.json'),
    JSON.stringify({ $id: 'monster', version: '1.0.0', type: 'object' }, null, 2)
  );
  await writeFile(
    join(canonRoot, 'schemas', 'character.schema.json'),
    JSON.stringify({ $id: 'character', version: '1.0.0', type: 'object' }, null, 2)
  );
}

async function writeConfig(projectRoot, canonRoot, overrides = {}) {
  const config = {
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
    ...overrides,
  };
  await writeFile(
    join(projectRoot, 'canon-build', 'config.json'),
    JSON.stringify(config, null, 2)
  );
}

async function writeMinEntries(canonRoot) {
  const lion = [
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

  const heracles = [
    '---',
    'id: heracles',
    'kind: hero',
    'visual:',
    '  silhouette_cue: club-and-lion-hide',
    '  attire: lion-skin cloak over naked torso',
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
    'Heracles narrative prose.',
    '',
  ].join('\n');

  await writeFile(join(canonRoot, 'monsters', 'nemean-lion.md'), lion);
  await writeFile(join(canonRoot, 'characters', 'heracles.md'), heracles);
}

async function fileExists(p) {
  try { await stat(p); return true; } catch { return false; }
}

// ─── Tests ─────────────────────────────────────────────────────────

test('runBuild: emits dataset.jsonl + prompts + context from two canon entries', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    await writeConfig(projectRoot, canonRoot);
    await writeMinEntries(canonRoot);

    const result = await runBuild({ projectRoot });
    assert.equal(result.entities_total, 2);
    assert.equal(result.rows, 2);
    assert.ok(result.generated_from, 'generated_from is stamped');

    const outputDir = result.output_dir;

    // dataset/all.jsonl with 2 rows
    const all = await readDatasetJsonl(join(outputDir, 'dataset', 'all.jsonl'));
    assert.equal(all.length, 2);
    const lion = all.find((r) => r.entity_id === 'nemean-lion');
    const hera = all.find((r) => r.entity_id === 'heracles');
    assert.equal(lion.lane, 'creature', 'monster → creature via constant lane rule');
    assert.equal(hera.lane, 'full-body', 'character → visual.art_lane');

    // Per-lane × partition jsonl
    assert.ok(await fileExists(join(outputDir, 'dataset', 'creature-train.jsonl')));
    assert.ok(await fileExists(join(outputDir, 'dataset', 'full-body-train.jsonl')));

    // Prompt templates, one per entity
    assert.ok(await fileExists(join(outputDir, 'prompts', 'nemean-lion.j2')));
    assert.ok(await fileExists(join(outputDir, 'prompts', 'heracles.j2')));

    // Context markdown, one per entity
    assert.ok(await fileExists(join(outputDir, 'context', 'nemean-lion.md')));
    assert.ok(await fileExists(join(outputDir, 'context', 'heracles.md')));

    // Manifest carries audit fields
    const manifest = JSON.parse(await readFile(join(outputDir, 'manifest.json'), 'utf-8'));
    assert.equal(manifest.stats.entities_total, 2);
    assert.equal(manifest.stats.dataset_rows, 2);
    assert.ok(manifest.per_entity_hashes['nemean-lion']);
    assert.ok(manifest.per_entity_hashes['heracles']);
    assert.equal(manifest.schema_versions['monster.schema.json'], '1.0.0');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: dry-run writes nothing', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    await writeConfig(projectRoot, canonRoot);
    await writeMinEntries(canonRoot);

    const result = await runBuild({ projectRoot, dryRun: true });
    assert.equal(result.dryRun, true);
    assert.equal(result.entities_total, 2);

    // Output dir should NOT exist after dry-run
    const outputContents = await readdir(join(projectRoot, 'canon-build'));
    assert.ok(!outputContents.some((name) => name === result.generated_from),
      `dry-run must not write to ${result.output_dir}`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: --only filter limits entities to named ids', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    await writeConfig(projectRoot, canonRoot);
    await writeMinEntries(canonRoot);

    const result = await runBuild({ projectRoot, only: ['heracles'] });
    assert.equal(result.entities_total, 1);
    assert.equal(result.rows, 1);
    assert.ok(await fileExists(join(result.output_dir, 'prompts', 'heracles.j2')));
    assert.ok(!(await fileExists(join(result.output_dir, 'prompts', 'nemean-lion.j2'))));
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: second run hits cache (entities_cached > 0)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    await writeConfig(projectRoot, canonRoot);
    await writeMinEntries(canonRoot);

    const first = await runBuild({ projectRoot });
    assert.equal(first.entities_rebuilt, 2, 'first run rebuilds everything');

    // Second run with no input changes: cache hits expected.
    const second = await runBuild({ projectRoot });
    assert.equal(second.entities_cached, 2, 'second run should cache-hit both entries');
    assert.equal(second.entities_rebuilt, 0);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: --full forces rebuild even when cache would hit', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    await writeConfig(projectRoot, canonRoot);
    await writeMinEntries(canonRoot);

    await runBuild({ projectRoot });
    const second = await runBuild({ projectRoot, full: true });
    assert.equal(second.entities_rebuilt, 2);
    assert.equal(second.entities_cached, 0);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: schema version bump triggers full rebuild on next run', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    await writeConfig(projectRoot, canonRoot);
    await writeMinEntries(canonRoot);

    await runBuild({ projectRoot });
    // Bump monster schema version — should invalidate that entry's cache.
    await writeFile(
      join(canonRoot, 'schemas', 'monster.schema.json'),
      JSON.stringify({ $id: 'monster', version: '2.0.0', type: 'object' }, null, 2)
    );
    const second = await runBuild({ projectRoot });
    // A schema change is a full-rebuild trigger per D4.
    assert.equal(second.entities_rebuilt, 2);
    assert.equal(second.entities_cached, 0);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: context length cap failure aborts with CANON_CONTEXT_LENGTH_EXCEEDED', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    // Force a very low cap so any entry exceeds it.
    await writeConfig(projectRoot, canonRoot, {
      context_limits: {
        default: { max_lines: 3 },
      },
    });
    await writeMinEntries(canonRoot);

    await assert.rejects(
      () => runBuild({ projectRoot }),
      (err) => err.code === 'CANON_CONTEXT_LENGTH_EXCEEDED'
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: monster schema without art_lane uses constant lane from config (D9)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffoldProject();
  try {
    await writeMinSchemas(canonRoot);
    await writeConfig(projectRoot, canonRoot);
    await writeMinEntries(canonRoot);

    const result = await runBuild({ projectRoot });
    const rows = await readDatasetJsonl(join(result.output_dir, 'dataset', 'all.jsonl'));
    const monsterRow = rows.find((r) => r.schema_kind === 'monster');
    assert.equal(monsterRow.lane, 'creature', 'D9: monster schema maps constant → creature');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('runBuild: missing canon-build/config.json surfaces structured error', async () => {
  const { tmp, projectRoot } = await scaffoldProject();
  try {
    await assert.rejects(
      () => runBuild({ projectRoot }),
      (err) => err.code === 'CANON_BUILD_CONFIG_NOT_FOUND'
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
