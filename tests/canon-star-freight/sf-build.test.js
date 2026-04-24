/**
 * Star Freight end-to-end canon-build integration test.
 *
 * Runs the real build against an isolated tmpdir copy of projects/star-freight,
 * asserts that the three projections (dataset.jsonl + prompts/ + context/)
 * land correctly, and confirms that the novel structural features from
 * Session A are observable in the build output.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile, mkdir, cp } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runBuild } from '../../lib/canon-build/build.js';

const SRC_PROJECT = join(process.cwd(), 'projects', 'star-freight');

async function scaffoldTmpProject() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-sf-'));
  const projectRoot = join(tmp, 'star-freight');
  await mkdir(projectRoot, { recursive: true });

  // Copy canon tree + canon-build config.
  for (const sub of ['canon', 'canon-build']) {
    await cp(join(SRC_PROJECT, sub), join(projectRoot, sub), { recursive: true });
  }
  return { tmp, projectRoot };
}

test('SF canon build: emits 28 entities across all 5 schemas', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    assert.equal(result.dryRun, false);
    assert.equal(result.entities_total, 28, 'Grounded scope is 27-28 entries; expect 28');
    assert.equal(result.rows, 28);
    assert.ok(result.frozen_entries >= 10, `expect 10+ frozen/soft-advisory entries, got ${result.frozen_entries}`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('SF canon build: first-run drift is empty (witness chain origin)', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    assert.deepEqual(result.drift, [], 'first build has no prior manifest to diff against');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('SF canon build: every entity emits a prompts/<id>.j2 and context/<id>.md', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    const expected = [
      // characters (15)
      'kael-maren', 'renna-vasik', 'jace-delvari', 'risa-kade', 'aldric-solen',
      'naia-of-threesong', 'lysa-orin', 'petra-wynn', 'dak-torvo', 'hael-croft',
      'tessik', 'mika-shan', 'old-dren', 'goss', 'callum',
      // locations (6)
      'tcs-ardent', 'freeport-station', 'communion-relay',
      'communion-relay-nav-office', 'communion-relay-archive', 'communion-relay-trade-hall',
      // factions (2)
      'terran-compact', 'keth-communion',
      // ships (1)
      'the-corrigan',
      // species (4)
      'terran', 'keth', 'veshan', 'orryn',
    ];
    for (const id of expected) {
      assert.ok(existsSync(join(result.output_dir, 'prompts', `${id}.j2`)), `prompts/${id}.j2 missing`);
      assert.ok(existsSync(join(result.output_dir, 'context', `${id}.md`)), `context/${id}.md missing`);
    }
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('SF canon build: Keth species prompt injects forbidden_morphology_drift after negative_base', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    const prompt = await readFile(join(result.output_dir, 'prompts', 'keth.j2'), 'utf-8');
    assert.ok(prompt.includes('{{ negative_base }}'));
    // Species-level alien-negative guard lands in the prompt
    assert.ok(/Earth insect/i.test(prompt), 'Keth prompt must forbid Earth-insect read');
    assert.ok(/chibi|anime/i.test(prompt), 'Keth prompt must forbid chibi / anime stylization');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('SF canon build: faction lane resolves to faction-aesthetic constant', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    const allText = await readFile(join(result.output_dir, 'dataset', 'all.jsonl'), 'utf-8');
    const factionRows = allText.split('\n')
      .filter(Boolean)
      .map(JSON.parse)
      .filter((r) => r.schema_kind === 'faction');
    assert.equal(factionRows.length, 2, 'expect 2 faction rows');
    for (const row of factionRows) {
      assert.equal(row.lane, 'faction-aesthetic', `faction ${row.entity_id} lane must be faction-aesthetic`);
    }
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('SF canon build: frozen entries get watch-hashes stamped in manifest', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    const manifest = JSON.parse(await readFile(join(result.output_dir, 'manifest.json'), 'utf-8'));
    // The 3 frozen hero-5 entries must be stamped.
    for (const id of ['kael-maren', 'aldric-solen', 'tcs-ardent']) {
      const stamp = manifest.frozen_entries_hashes[id];
      assert.ok(stamp, `${id} should have a frozen_entries_hashes stamp`);
      assert.equal(stamp.status, 'frozen');
      assert.equal(typeof stamp.watch_hash, 'string');
      assert.equal(stamp.watch_hash.length, 64, 'watch_hash is sha-256 hex');
    }
    // Jace is soft-advisory — still stamped.
    assert.equal(manifest.frozen_entries_hashes['jace-delvari']?.status, 'soft-advisory');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('SF canon build: turncoat_arc lands in context for Jace, Risa, Solen', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    for (const id of ['jace-delvari', 'risa-kade', 'aldric-solen']) {
      const ctx = await readFile(join(result.output_dir, 'context', `${id}.md`), 'utf-8');
      assert.ok(ctx.includes('Turncoat arc'), `${id} context must render the Turncoat arc section`);
      assert.ok(ctx.includes('seeds'), `${id} context must carry the seeds[] field`);
    }
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('SF canon build: second run caches all entries (idempotency)', async () => {
  const { tmp, projectRoot } = await scaffoldTmpProject();
  try {
    await runBuild({ projectRoot });
    const second = await runBuild({ projectRoot });
    assert.equal(second.entities_cached, 28, 'second run should cache all 28');
    assert.equal(second.entities_rebuilt, 0);
    assert.deepEqual(second.drift, [], 'identical canon yields no drift');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
