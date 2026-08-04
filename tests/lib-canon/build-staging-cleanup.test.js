/**
 * M2: lib/canon-build/build.js writes to a staging directory
 * (`<sha>.tmp-<pid>`), populates it (dataset/prompts/context, then the
 * freeze-drift pass), and only then atomically renames it to the real
 * output dir. The freeze-drift pass calls readFreezeStatus() (lib/freeze-
 * stamp.js) per entry, which throws CANON_FREEZE_STATUS_INVALID on a
 * malformed freeze.status (a hand-edited case typo, e.g. "Frozen" instead
 * of "frozen" — see tests/lib-canon/freeze-stamp-invalid-status.test.js for
 * that throw's own coverage).
 *
 * Before this fix, a throw anywhere in that write-through-rename block left
 * the ALREADY-POPULATED staging directory orphaned on disk forever: the
 * only cleanup is the `rm(stagingDir, ...)` at the very top of runBuild(),
 * and that runs against a NEW `${generatedFromDir}.tmp-${process.pid}` path
 * on the NEXT invocation (a different pid) — it can never match a
 * previously-orphaned directory from a different pid.
 *
 * This drives a real throw through the real staging path (no mocking) and
 * asserts no `*.tmp-*` directory survives under canon-build/ afterward.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runBuild } from '../../lib/canon-build/build.js';

async function scaffold() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-m2-orphan-'));
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

/** A monster entry with a hand-typo'd freeze.status ("Frozen", capital F) —
 * readFreezeStatus() throws CANON_FREEZE_STATUS_INVALID on this, AFTER the
 * staging directory has already been populated with dataset/prompts/context
 * by the time the freeze-drift pass runs. */
async function writeInvalidFreezeStatusEntry(canonRoot, id) {
  const yaml = [
    `id: ${id}`,
    `species_tag: quadruped`,
    `anatomy_descriptor:`,
    `  heads: 1`,
    `  limbs: 4`,
    `  notable: []`,
    `lineage_reference: none`,
    `scale_indicator: larger`,
    `forbidden_inputs:`,
    `  - generic`,
    `signature_features:`,
    `  - feature-a`,
    `sources:`,
    `  - X`,
    `freeze:`,
    `  status: Frozen`, // <-- the typo: capital F, unquoted YAML bareword string
  ].join('\n');
  await writeFile(join(canonRoot, 'monsters', `${id}.md`), `---\n${yaml}\n---\n`);
}

async function listOrphanedStagingDirs(projectRoot) {
  const canonBuildDir = join(projectRoot, 'canon-build');
  const entries = await readdir(canonBuildDir);
  return entries.filter((name) => name.includes('.tmp-'));
}

test('M2: a throw during the freeze-drift pass does not leave an orphaned staging directory behind', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeInvalidFreezeStatusEntry(canonRoot, 'nemean-lion');

    await assert.rejects(
      () => runBuild({ projectRoot }),
      (err) => err.code === 'CANON_FREEZE_STATUS_INVALID',
    );

    const orphans = await listOrphanedStagingDirs(projectRoot);
    assert.deepEqual(orphans, [], `expected no orphaned staging directories under canon-build/, found: ${orphans.join(', ')}`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('M2: a normal successful build still produces a real output dir and no leftover staging dir — explicit PASS branch for contrast', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    // Same entry, correctly-cased status this time — must not throw.
    const yaml = [
      `id: nemean-lion`,
      `species_tag: quadruped`,
      `anatomy_descriptor:`,
      `  heads: 1`,
      `  limbs: 4`,
      `  notable: []`,
      `lineage_reference: none`,
      `scale_indicator: larger`,
      `forbidden_inputs:`,
      `  - generic`,
      `signature_features:`,
      `  - feature-a`,
      `sources:`,
      `  - X`,
      `freeze:`,
      `  status: frozen`,
    ].join('\n');
    await writeFile(join(canonRoot, 'monsters', 'nemean-lion.md'), `---\n${yaml}\n---\n`);

    const result = await runBuild({ projectRoot });
    assert.equal(result.entities_total, 1);

    const orphans = await listOrphanedStagingDirs(projectRoot);
    assert.deepEqual(orphans, [], `a successful build must not leave any staging directory behind either, found: ${orphans.join(', ')}`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
