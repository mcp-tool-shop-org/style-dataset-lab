/**
 * Unit tests for lib/freeze-gate.js — the enforcement gate (D3).
 *
 * Builds a minimal in-tmpdir project + canon tree, writes a canon-build
 * config, then exercises each gate path: auto no-op, frozen block,
 * soft-advisory-without-bypass block, soft-advisory-with-bypass log.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  assertNotFrozen,
  assertNotFrozenBySubject,
  assertNotFrozenByAssetPath,
  resolveEntryBySubject,
  resolveEntryByAssetPath,
} from '../../lib/freeze-gate.js';
import { eventsPath, readEvents } from '../../lib/freeze-events.js';

async function scaffold() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-gate-'));
  const projectRoot = join(tmp, 'proj');
  const canonRoot = join(tmp, 'canon');
  await mkdir(join(projectRoot, 'canon-build'), { recursive: true });
  await mkdir(join(canonRoot, 'schemas'), { recursive: true });
  await mkdir(join(canonRoot, 'characters'), { recursive: true });

  // Minimal schema
  await writeFile(
    join(canonRoot, 'schemas', 'character.schema.json'),
    JSON.stringify({ $id: 'character', version: '1.0.0', type: 'object' }, null, 2),
  );

  // Minimal build config
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

  return { tmp, projectRoot, canonRoot };
}

async function writeCharacterEntry(canonRoot, id, freezeStatus, extra = {}) {
  const freeze = freezeStatus ? { status: freezeStatus, ...(extra.freezeFields || {}) } : null;
  const fm = {
    id,
    kind: 'hero',
    visual: { silhouette_cue: 'x', attire: 'y', build: 'athletic', hair: 'z', eyes: 'a', age_band: 'young-adult', art_lane: 'portrait', palette: ['#ffffff'], reference_plate_uri: extra.assetPath || null },
    narrative: { role: 'r', voice: ['a', 'b'], motivation: 'x', arc_beats: ['a', 'b', 'c'] },
    sources: ['x'],
  };
  if (freeze) fm.freeze = freeze;
  const body = extra.body || '';
  const yaml = Object.entries(fm)
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join('\n');
  await writeFile(
    join(canonRoot, 'characters', `${id}.md`),
    `---\n${yaml}\n---\n${body}`,
  );
}

// --- auto (permissive default) ---

test('gate: auto-status entry never blocks', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', null);
    await assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'test' });
    // no throw = pass
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('gate: no canon-build config = no-op (returns without throwing)', async () => {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-gate-'));
  try {
    const projectRoot = join(tmp, 'proj');
    await mkdir(projectRoot, { recursive: true });
    await assertNotFrozenBySubject(projectRoot, 'anyone', { action: 'test' });
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- frozen (hard block) ---

test('gate: frozen-status entry throws CANON_ENTRY_FROZEN', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', 'frozen');
    await assert.rejects(
      () => assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'generate' }),
      (err) => err.code === 'CANON_ENTRY_FROZEN',
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('gate: frozen cannot be bypassed even with --i-know + --reason', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', 'frozen');
    await assert.rejects(
      () => assertNotFrozenBySubject(projectRoot, 'heracles', {
        action: 'generate',
        allowSoftAdvisoryBypass: true,
        bypassReason: 'I insist',
      }),
      (err) => err.code === 'CANON_ENTRY_FROZEN',
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- soft-advisory ---

test('gate: soft-advisory blocks by default (no --i-know)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', 'soft-advisory');
    await assert.rejects(
      () => assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'generate' }),
      (err) => err.code === 'CANON_ENTRY_FROZEN',
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('gate: soft-advisory blocks with --i-know but no --reason', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', 'soft-advisory');
    await assert.rejects(
      () => assertNotFrozenBySubject(projectRoot, 'heracles', {
        action: 'generate',
        allowSoftAdvisoryBypass: true,
        bypassReason: null,
      }),
      (err) => err.code === 'CANON_ENTRY_FROZEN' && /requires --i-know AND --reason/.test(err.message),
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('gate: soft-advisory bypass with --i-know + --reason proceeds AND logs a bypass event', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', 'soft-advisory');
    await assertNotFrozenBySubject(projectRoot, 'heracles', {
      action: 'generate',
      allowSoftAdvisoryBypass: true,
      bypassReason: 'iterating palette',
    });
    const events = await readEvents(projectRoot);
    assert.equal(events.length, 1);
    assert.equal(events[0].type, 'bypass');
    assert.equal(events[0].entity_id, 'heracles');
    assert.equal(events[0].reason, 'iterating palette');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- on-canon-change ---

test('gate: on-canon-change does NOT block at write time (drift is a build concern)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', 'on-canon-change');
    await assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'generate' });
    // No block, no event.
    const events = await readEvents(projectRoot);
    assert.equal(events.length, 0);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- reverse-map helpers ---

test('resolveEntryBySubject: matches on entry.id', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', null);
    const resolved = await resolveEntryBySubject(projectRoot, 'heracles');
    assert.ok(resolved);
    assert.equal(resolved.entry.frontmatter.id, 'heracles');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('resolveEntryBySubject: returns null for unknown subject', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    const resolved = await resolveEntryBySubject(projectRoot, 'ghost');
    assert.equal(resolved, null);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('resolveEntryByAssetPath: matches visual.reference_plate_uri', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', null, { assetPath: 'outputs/approved/heracles.png' });
    const resolved = await resolveEntryByAssetPath(projectRoot, 'outputs/approved/heracles.png');
    assert.ok(resolved);
    assert.equal(resolved.entry.frontmatter.id, 'heracles');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('resolveEntryByAssetPath: returns null when no entry claims the path', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeCharacterEntry(canonRoot, 'heracles', null, { assetPath: 'outputs/approved/heracles.png' });
    const resolved = await resolveEntryByAssetPath(projectRoot, 'outputs/approved/elsewhere.png');
    assert.equal(resolved, null);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- bare assertNotFrozen with preloaded resolved ---

test('assertNotFrozen: null resolved = no-op', async () => {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-gate-'));
  try {
    await assertNotFrozen({ projectRoot: tmp, resolved: null, action: 'test' });
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
