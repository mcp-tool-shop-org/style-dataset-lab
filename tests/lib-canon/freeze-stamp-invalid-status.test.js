/**
 * SDL-H2 — readFreezeStatus() must not conflate "absent" with "present but
 * malformed". A `freeze` block that IS present with a `status` value outside
 * FREEZE_STATUSES (e.g. a hand-edited case typo: `status: Frozen` against
 * the lowercase-only enum) must throw, not silently coerce to 'auto'.
 *
 * Before this fix, `auto` fell through lib/freeze-gate.js's assertNotFrozen
 * with no block, no warning, and no bypass event (the bypass path is never
 * entered for 'auto') — a single capital letter silently disabled hard-freeze
 * protection on a hand-edited canon entry. Canon files in this repo ARE
 * hand-edited (see e.g. projects/portlight-ships/canon/ships/*.md).
 *
 * This file covers both layers:
 *   1. Unit: readFreezeStatus() itself throws on the malformed-but-present case.
 *   2. Integration: the REFUSE branch through the real gate stack
 *      (assertNotFrozenBySubject) — a gate proven only on the happy path is
 *      untested, so this drives a hand-typo'd frozen entry through the full
 *      resolve → gate path and asserts the refusal actually surfaces.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { FREEZE_STATUSES, readFreezeStatus } from '../../lib/freeze-stamp.js';
import { assertNotFrozenBySubject, resolveEntryBySubject } from '../../lib/freeze-gate.js';

// ─── Layer 1: unit coverage on readFreezeStatus ────────────────────────

test('readFreezeStatus: case-typo of a legal status throws (the motivating real-world case)', () => {
  // "Frozen" (capital F) is a non-empty string outside FREEZE_STATUSES
  // (which is lowercase-only) — this is the exact hand-edit typo from the
  // finding.
  assert.throws(
    () => readFreezeStatus({ freeze: { status: 'Frozen' } }),
    (err) => {
      assert.equal(err.code, 'CANON_FREEZE_STATUS_INVALID');
      assert.match(err.message, /Frozen/);
      return true;
    },
  );
});

test('readFreezeStatus: throws for any non-empty string outside the enum, not just case-typos', () => {
  assert.throws(
    () => readFreezeStatus({ freeze: { status: 'nonsense' } }),
    (err) => err.code === 'CANON_FREEZE_STATUS_INVALID',
  );
});

test('readFreezeStatus: error message includes the entry id when present, for operator triage', () => {
  assert.throws(
    () => readFreezeStatus({ id: 'nemean-lion', freeze: { status: 'Frozen' } }),
    (err) => {
      assert.match(err.message, /nemean-lion/);
      return true;
    },
  );
});

test('readFreezeStatus: hint names the valid enum values', () => {
  assert.throws(
    () => readFreezeStatus({ freeze: { status: 'Frozen' } }),
    (err) => {
      for (const s of FREEZE_STATUSES) assert.match(err.message, new RegExp(s));
      return true;
    },
  );
});

test('readFreezeStatus: still permissive for genuinely absent cases (unchanged D8 default)', () => {
  // No freeze block at all.
  assert.equal(readFreezeStatus({}), 'auto');
  assert.equal(readFreezeStatus(null), 'auto');
  // freeze block present but no status key at all.
  assert.equal(readFreezeStatus({ freeze: {} }), 'auto');
  assert.equal(readFreezeStatus({ freeze: { watch_fields: ['x'] } }), 'auto');
  // Explicit empty string is treated as "not set", not as a bad value.
  assert.equal(readFreezeStatus({ freeze: { status: '' } }), 'auto');
});

test('readFreezeStatus: all four legal statuses still read through cleanly (no false positives)', () => {
  for (const status of FREEZE_STATUSES) {
    assert.equal(readFreezeStatus({ freeze: { status } }), status);
  }
});

// ─── Layer 2: integration — drive the real gate to its REFUSE branch ──

async function scaffold() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-h2-gate-'));
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

  return { tmp, projectRoot, canonRoot };
}

// Hand-write the raw YAML directly (not JSON.stringify) so we can inject the
// exact unquoted-bareword typo a human editor would actually produce:
// `status: Frozen` — which YAML parses as the JS string "Frozen", not a
// special/boolean value.
async function writeTypoFrozenEntry(canonRoot, id) {
  const yaml = [
    `id: ${id}`,
    `kind: hero`,
    `visual:`,
    `  silhouette_cue: x`,
    `  attire: y`,
    `  build: athletic`,
    `  hair: z`,
    `  eyes: a`,
    `  age_band: young-adult`,
    `  art_lane: portrait`,
    `  palette:`,
    `    - "#ffffff"`,
    `narrative:`,
    `  role: r`,
    `  voice:`,
    `    - a`,
    `    - b`,
    `  motivation: x`,
    `  arc_beats:`,
    `    - a`,
    `    - b`,
    `    - c`,
    `sources:`,
    `  - x`,
    `freeze:`,
    `  status: Frozen`, // <-- the typo: capital F, unquoted YAML bareword string
    `  frozen_by: mike`,
    `  frozen_reason: "hero moment"`,
  ].join('\n');
  await writeFile(join(canonRoot, 'characters', `${id}.md`), `---\n${yaml}\n---\n`);
}

test('gate integration: a hand-typo\'d freeze.status ("Frozen") now REFUSES instead of silently passing as auto', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeTypoFrozenEntry(canonRoot, 'heracles');
    // Before the fix: this would resolve status to 'auto' and return silently
    // (no block, no warning, no bypass event — freeze protection just off).
    // After the fix: the malformed status must surface as a thrown error
    // instead of a silent pass-through.
    await assert.rejects(
      () => assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'generate' }),
      (err) => {
        assert.equal(err.code, 'CANON_FREEZE_STATUS_INVALID');
        assert.match(err.message, /Frozen/);
        return true;
      },
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('gate integration: resolveEntryBySubject itself surfaces the malformed status (not swallowed upstream)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    await writeTypoFrozenEntry(canonRoot, 'heracles');
    // resolveEntryBySubject calls entryId() (safe) but readFreezeStatus is
    // invoked downstream by assertNotFrozen, not by resolve itself — confirm
    // resolve succeeds (finds the entry) so we know the throw specifically
    // comes from the freeze-status read, not from entry loading generally.
    const resolved = await resolveEntryBySubject(projectRoot, 'heracles');
    assert.ok(resolved, 'entry with a typo\'d freeze status must still be discoverable/loadable');
    assert.equal(resolved.entry.frontmatter.id, 'heracles');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('gate integration: a CORRECTLY-cased frozen entry still refuses normally (fix does not regress the working REFUSE path)', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    const yaml = [
      `id: heracles`,
      `kind: hero`,
      `visual:`,
      `  silhouette_cue: x`,
      `  attire: y`,
      `  build: athletic`,
      `  hair: z`,
      `  eyes: a`,
      `  age_band: young-adult`,
      `  art_lane: portrait`,
      `  palette:`,
      `    - "#ffffff"`,
      `narrative:`,
      `  role: r`,
      `  voice:`,
      `    - a`,
      `    - b`,
      `  motivation: x`,
      `  arc_beats:`,
      `    - a`,
      `    - b`,
      `    - c`,
      `sources:`,
      `  - x`,
      `freeze:`,
      `  status: frozen`, // correctly lowercase
      `  frozen_by: mike`,
      `  frozen_reason: "hero moment"`,
    ].join('\n');
    await writeFile(join(canonRoot, 'characters', 'heracles.md'), `---\n${yaml}\n---\n`);

    await assert.rejects(
      () => assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'generate' }),
      (err) => err.code === 'CANON_ENTRY_FROZEN',
    );
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('gate integration: an auto-status entry (genuinely absent freeze intent) still proceeds without throwing', async () => {
  const { tmp, projectRoot, canonRoot } = await scaffold();
  try {
    const yaml = [
      `id: heracles`,
      `kind: hero`,
      `visual:`,
      `  silhouette_cue: x`,
      `  attire: y`,
      `  build: athletic`,
      `  hair: z`,
      `  eyes: a`,
      `  age_band: young-adult`,
      `  art_lane: portrait`,
      `  palette:`,
      `    - "#ffffff"`,
      `narrative:`,
      `  role: r`,
      `  voice:`,
      `    - a`,
      `    - b`,
      `  motivation: x`,
      `  arc_beats:`,
      `    - a`,
      `    - b`,
      `    - c`,
      `sources:`,
      `  - x`,
    ].join('\n'); // no freeze block at all
    await writeFile(join(canonRoot, 'characters', 'heracles.md'), `---\n${yaml}\n---\n`);

    await assertNotFrozenBySubject(projectRoot, 'heracles', { action: 'generate' });
    // no throw = pass
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
