/**
 * Unit tests for canon-build loaders — frontmatter, load-entry,
 * load-schema, load-config, lane-resolve.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { parseFrontmatter } from '../../lib/canon-build/frontmatter.js';
import { loadCanonEntry, loadCanonEntriesInDir, entryId } from '../../lib/canon-build/load-entry.js';
import { loadSchema } from '../../lib/canon-build/load-schema.js';
import { loadBuildConfig, getByPath } from '../../lib/canon-build/load-config.js';
import { resolveLane } from '../../lib/canon-build/lane-resolve.js';

// --- parseFrontmatter ---

test('parseFrontmatter splits YAML frontmatter from body', () => {
  const text = '---\nid: heracles\nkind: hero\n---\nBody prose goes here.\n';
  const parsed = parseFrontmatter(text, 'heracles.md');
  assert.equal(parsed.frontmatter.id, 'heracles');
  assert.equal(parsed.frontmatter.kind, 'hero');
  assert.equal(parsed.body, 'Body prose goes here.\n');
});

test('parseFrontmatter handles CRLF line endings', () => {
  const text = '---\r\nid: x\r\n---\r\nbody\r\n';
  const parsed = parseFrontmatter(text, 'x.md');
  assert.equal(parsed.frontmatter.id, 'x');
});

test('parseFrontmatter throws when fence is missing', () => {
  assert.throws(() => parseFrontmatter('no fence here', 'bad.md'), /frontmatter fence/);
});

test('parseFrontmatter throws when closing fence is missing', () => {
  assert.throws(() => parseFrontmatter('---\nid: x\nbody\n', 'bad.md'), /closing "---" fence/);
});

test('parseFrontmatter throws on invalid YAML', () => {
  assert.throws(
    () => parseFrontmatter('---\nkey: [invalid\n---\nbody', 'bad.md'),
    /not valid YAML/
  );
});

test('parseFrontmatter throws when frontmatter is not a YAML object', () => {
  assert.throws(
    () => parseFrontmatter('---\n- item1\n- item2\n---\nbody', 'bad.md'),
    /must be a YAML object/
  );
});

// --- loadCanonEntry / loadCanonEntriesInDir ---

test('loadCanonEntry reads a file and parses frontmatter + body', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-entry-'));
  try {
    const path = join(dir, 'nemean-lion.md');
    await writeFile(path, '---\nid: nemean-lion\nspecies_tag: quadruped\n---\nNemean lion lives at Nemea.\n');
    const entry = await loadCanonEntry(path);
    assert.equal(entry.frontmatter.id, 'nemean-lion');
    assert.equal(entry.body.trim(), 'Nemean lion lives at Nemea.');
    assert.equal(entry.filePath, path);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadCanonEntriesInDir skips non-.md files and sorts', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-entry-'));
  try {
    await writeFile(join(dir, 'b.md'), '---\nid: b\n---\nbody\n');
    await writeFile(join(dir, 'a.md'), '---\nid: a\n---\nbody\n');
    await writeFile(join(dir, 'README.txt'), 'ignore me');
    const entries = await loadCanonEntriesInDir(dir);
    assert.equal(entries.length, 2);
    assert.equal(entries[0].frontmatter.id, 'a');
    assert.equal(entries[1].frontmatter.id, 'b');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadCanonEntriesInDir returns empty list for missing directory', async () => {
  const entries = await loadCanonEntriesInDir('/definitely/not/real/path');
  assert.deepEqual(entries, []);
});

test('entryId prefers frontmatter.id', () => {
  assert.equal(entryId({ frontmatter: { id: 'x' }, filePath: '/tmp/y.md' }), 'x');
});

test('entryId falls back to filename stem when frontmatter.id missing', () => {
  assert.equal(entryId({ frontmatter: {}, filePath: '/tmp/y.md' }), 'y');
});

// --- loadSchema ---

test('loadSchema resolves version from the explicit field when present', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-schema-'));
  try {
    const path = join(dir, 'foo.schema.json');
    await writeFile(path, JSON.stringify({ $id: 'foo', version: '2.3.1', type: 'object' }));
    const { schema, version } = await loadSchema(path);
    assert.equal(schema.$id, 'foo');
    assert.equal(version, '2.3.1');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadSchema falls back to content-sha when version field is absent', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-schema-'));
  try {
    const path = join(dir, 'bar.schema.json');
    await writeFile(path, JSON.stringify({ $id: 'bar', type: 'object' }));
    const { version } = await loadSchema(path);
    assert.ok(version.startsWith('content-sha:'));
    assert.ok(version.length > 'content-sha:'.length + 10);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadSchema throws structured error on invalid JSON', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-schema-'));
  try {
    const path = join(dir, 'broken.schema.json');
    await writeFile(path, '{ not valid json');
    await assert.rejects(
      () => loadSchema(path),
      (err) => err.code === 'CANON_SCHEMA_INVALID_JSON'
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

// --- loadBuildConfig ---

const MIN_CONFIG = {
  project_id: 'greek-rpg',
  canon_root: '/tmp/greek-rpg/canon',
  schema_dir: '/tmp/greek-rpg/canon/schemas',
  entity_dirs: {
    'monster.schema.json': 'monsters',
  },
  schema_to_lane: {
    'monster.schema.json': { source: 'constant', value: 'creature' },
  },
};

test('loadBuildConfig accepts a minimal valid config', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-bcfg-'));
  try {
    const path = join(dir, 'config.json');
    await writeFile(path, JSON.stringify(MIN_CONFIG));
    const cfg = await loadBuildConfig(path, dir);
    assert.equal(cfg.project_id, 'greek-rpg');
    assert.equal(cfg.schema_to_lane['monster.schema.json'].source, 'constant');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadBuildConfig throws CANON_BUILD_CONFIG_NOT_FOUND when missing', async () => {
  await assert.rejects(
    () => loadBuildConfig('/does/not/exist.json', '/tmp'),
    (err) => err.code === 'CANON_BUILD_CONFIG_NOT_FOUND'
  );
});

test('loadBuildConfig rejects config with missing required fields', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-bcfg-'));
  try {
    const path = join(dir, 'config.json');
    await writeFile(path, JSON.stringify({ project_id: 'x' }));
    await assert.rejects(
      () => loadBuildConfig(path, dir),
      (err) => err.code === 'CANON_BUILD_CONFIG_INVALID'
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadBuildConfig rejects schema_to_lane with unknown source', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-bcfg-'));
  try {
    const path = join(dir, 'config.json');
    await writeFile(path, JSON.stringify({
      ...MIN_CONFIG,
      schema_to_lane: { 'monster.schema.json': { source: 'mystery' } },
    }));
    await assert.rejects(
      () => loadBuildConfig(path, dir),
      (err) => err.code === 'CANON_BUILD_CONFIG_INVALID'
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

// --- getByPath ---

test('getByPath walks a dotted path', () => {
  assert.equal(getByPath({ a: { b: { c: 42 } } }, 'a.b.c'), 42);
});

test('getByPath returns undefined for missing segments', () => {
  assert.equal(getByPath({ a: { b: {} } }, 'a.b.c'), undefined);
  assert.equal(getByPath(null, 'a'), undefined);
});

// --- resolveLane ---

test('resolveLane: constant rule returns the declared value', () => {
  const entry = { frontmatter: {}, filePath: 'x.md' };
  const lane = resolveLane(entry, 'monster.schema.json', {
    'monster.schema.json': { source: 'constant', value: 'creature' },
  });
  assert.equal(lane, 'creature');
});

test('resolveLane: field rule reads the dotted path from frontmatter', () => {
  const entry = { frontmatter: { visual: { art_lane: 'portrait' } }, filePath: 'x.md' };
  const lane = resolveLane(entry, 'character.schema.json', {
    'character.schema.json': { source: 'field', field: 'visual.art_lane' },
  });
  assert.equal(lane, 'portrait');
});

test('resolveLane: throws CANON_LANE_UNMAPPED when rule is missing', () => {
  const entry = { frontmatter: {}, filePath: 'x.md' };
  assert.throws(
    () => resolveLane(entry, 'unknown.schema.json', {}),
    (err) => err.code === 'CANON_LANE_UNMAPPED'
  );
});

test('resolveLane: throws when field rule targets an absent path', () => {
  const entry = { frontmatter: { visual: {} }, filePath: 'x.md' };
  assert.throws(
    () => resolveLane(entry, 'character.schema.json', {
      'character.schema.json': { source: 'field', field: 'visual.art_lane' },
    }),
    (err) => err.code === 'CANON_LANE_UNMAPPED'
  );
});
