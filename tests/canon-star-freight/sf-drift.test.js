/**
 * Star Freight witness-chain drift substrate tests.
 *
 * Proves the freeze witness chain end-to-end:
 *   1. First build has no prior manifest → drift = [].
 *   2. Editing a watched field on a frozen entry → drift surfaces on next build.
 *   3. Editing a non-watched field (body prose, canon_refs) → drift does NOT surface.
 *   4. The `canon drift` CLI correctly pulls `.watch_hash` from the rich
 *      manifest stamp object and compares against the current watch-hash.
 *   5. `freeze-events.jsonl` append-only log records override events.
 *
 * Sessions A+B+C landed the substrate; this file closes the loop — if it
 * passes, the "first drift event is the real test" gate Mike flagged is
 * covered by CI, not by a one-off manual experiment.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile, writeFile, mkdir, cp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runBuild } from '../../lib/canon-build/build.js';
import { appendEvent, readEvents, eventsPath } from '../../lib/freeze-events.js';
import { existsSync } from 'node:fs';

const SRC_PROJECT = join(process.cwd(), 'projects', 'star-freight');

async function scaffold() {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-sf-drift-'));
  const projectRoot = join(tmp, 'star-freight');
  await mkdir(projectRoot, { recursive: true });
  for (const sub of ['canon', 'canon-build']) {
    await cp(join(SRC_PROJECT, sub), join(projectRoot, sub), { recursive: true });
  }
  return { tmp, projectRoot };
}

// ── basic witness-chain ────────────────────────────────────────────────

test('drift: first build after scaffold has empty drift[] (witness-chain origin)', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    assert.deepEqual(result.drift, []);
    assert.ok(result.frozen_entries >= 10);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('drift: identical second build stays clean (no edit → no drift)', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });
    const second = await runBuild({ projectRoot, noCache: true });
    assert.deepEqual(second.drift, []);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// ── edits INSIDE watch_fields trigger drift ────────────────────────────

test('drift: narrative.voice edit on a frozen character surfaces drift', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    // narrative.voice is in character.schema.json freeze_watch_defaults.
    // Kael is frozen (hard). Editing one adjective should trip drift.
    const kaelPath = join(projectRoot, 'canon', 'characters', 'kael-maren.md');
    const before = await readFile(kaelPath, 'utf-8');
    const after = before.replace(
      'voice: ["blunt", "wry", "withheld", "steady"]',
      'voice: ["blunt", "wry", "withheld", "hardened"]',
    );
    assert.notEqual(after, before, 'test setup: edit must actually change the text');
    await writeFile(kaelPath, after, 'utf-8');

    const second = await runBuild({ projectRoot, noCache: true });
    const kaelDrift = second.drift.find((d) => d.entity_id === 'kael-maren');
    assert.ok(kaelDrift, 'Kael drift must surface');
    assert.equal(kaelDrift.status, 'frozen');
    assert.equal(typeof kaelDrift.current_hash, 'string');
    assert.equal(typeof kaelDrift.prior_hash, 'string');
    assert.notEqual(kaelDrift.current_hash, kaelDrift.prior_hash);
    // Only Kael should drift — no other entries edited.
    assert.equal(second.drift.length, 1, `expected 1 drift entry, got ${second.drift.length}: ${second.drift.map((d) => d.entity_id).join(', ')}`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('drift: turncoat_arc.seeds edit on Jace (soft-advisory) surfaces drift', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    const jacePath = join(projectRoot, 'canon', 'characters', 'jace-delvari.md');
    const before = await readFile(jacePath, 'utf-8');
    // Rewrite one seed — this field is in the character watch_fields.
    const after = before.replace(
      'Nice ship. The kind that gets noticed when it shouldn\'t.',
      'Nice ship. The kind that attracts the wrong attention.',
    );
    assert.notEqual(after, before, 'test setup: seed edit must land');
    await writeFile(jacePath, after, 'utf-8');

    const second = await runBuild({ projectRoot, noCache: true });
    const jaceDrift = second.drift.find((d) => d.entity_id === 'jace-delvari');
    assert.ok(jaceDrift, 'Jace drift must surface on seeds[] change');
    assert.equal(jaceDrift.status, 'soft-advisory');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('drift: species forbidden_morphology_drift edit on Keth surfaces drift', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    const kethPath = join(projectRoot, 'canon', 'species', 'keth.md');
    const before = await readFile(kethPath, 'utf-8');
    // species.visual.forbidden_morphology_drift is in the species watch_fields.
    const after = before.replace(
      '    - "Earth insect, bug, ant, spider, mantis, beetle"',
      '    - "Earth insect, bug, ant, spider, mantis, beetle, scorpion"',
    );
    assert.notEqual(after, before);
    await writeFile(kethPath, after, 'utf-8');

    const second = await runBuild({ projectRoot, noCache: true });
    const kethDrift = second.drift.find((d) => d.entity_id === 'keth');
    assert.ok(kethDrift, 'Keth species drift must surface on forbidden_morphology_drift edit');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// ── edits OUTSIDE watch_fields stay clean ──────────────────────────────

test('drift: body-prose edit on a frozen entry does NOT trigger drift', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    const kaelPath = join(projectRoot, 'canon', 'characters', 'kael-maren.md');
    const before = await readFile(kaelPath, 'utf-8');
    // Edit prose BELOW the second `---` fence (body), not frontmatter.
    const after = before.replace(
      '## Commander Kael Maren',
      '## Commander Kael Maren — player character',
    );
    assert.notEqual(after, before);
    await writeFile(kaelPath, after, 'utf-8');

    const second = await runBuild({ projectRoot, noCache: true });
    const kaelDrift = second.drift.find((d) => d.entity_id === 'kael-maren');
    assert.equal(kaelDrift, undefined, 'body prose is not in watch_fields — must not drift');
    assert.deepEqual(second.drift, []);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('drift: canon_refs edit on a frozen entry does NOT trigger drift', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    const kaelPath = join(projectRoot, 'canon', 'characters', 'kael-maren.md');
    const before = await readFile(kaelPath, 'utf-8');
    // Rewrite an existing canon_ref — not in watch_fields.
    const after = before.replace(
      'PROLOGUE_GROUNDED.md §53-63, §99-102, §243-244',
      'PROLOGUE_GROUNDED.md §53-63, §99-102, §243-244, §260-265',
    );
    assert.notEqual(after, before, 'test setup: canon_refs edit must land');
    await writeFile(kaelPath, after, 'utf-8');

    const second = await runBuild({ projectRoot, noCache: true });
    assert.deepEqual(second.drift, [], 'canon_refs is not in watch_fields — must not drift');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// ── manifest stamp shape (the bug that prompted this slice) ────────────

test('drift: manifest stamps watch_hash per frozen entry as a hex string on .watch_hash', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    const result = await runBuild({ projectRoot, noCache: true });
    const manifest = JSON.parse(await readFile(join(result.output_dir, 'manifest.json'), 'utf-8'));
    const stamp = manifest.frozen_entries_hashes['kael-maren'];
    assert.ok(stamp, 'Kael must have a stamp');
    // The stamp is an object, not a bare hash string. This is the shape the
    // `canon drift` CLI must read `.watch_hash` from.
    assert.equal(typeof stamp, 'object');
    assert.equal(typeof stamp.watch_hash, 'string');
    assert.equal(stamp.watch_hash.length, 64, 'watch_hash is sha-256 hex');
    assert.equal(stamp.status, 'frozen');
    assert.ok(Array.isArray(stamp.watch_fields));
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// ── override / bypass event log ────────────────────────────────────────

test('drift: override event appends to freeze-events.jsonl and readEvents round-trips', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    // Simulate the operator overriding a freeze (e.g., approved regen).
    await appendEvent(projectRoot, {
      type: 'override',
      entity_id: 'kael-maren',
      schema_kind: 'character',
      by: 'mike',
      reason: 'director approved voice-pass for Beat 5 cinematic',
      prior_status: 'frozen',
      new_status: 'frozen',
      build_hash: '49f9c72fc037e3d22152b02d8256af5205524465',
    });

    const log = await readEvents(projectRoot);
    assert.equal(log.length, 1);
    assert.equal(log[0].type, 'override');
    assert.equal(log[0].entity_id, 'kael-maren');
    assert.equal(log[0].by, 'mike');
    assert.ok(log[0].at, 'event must carry an ISO timestamp');

    // File must exist where drift CLI expects.
    assert.ok(existsSync(eventsPath(projectRoot)));
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('drift: multiple overrides append in order (audit log)', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    await appendEvent(projectRoot, { type: 'override', entity_id: 'kael-maren', by: 'mike', reason: 'r1' });
    await appendEvent(projectRoot, { type: 'override', entity_id: 'aldric-solen', by: 'mike', reason: 'r2' });
    await appendEvent(projectRoot, { type: 'bypass', entity_id: 'jace-delvari', by: 'mike', reason: 'iterating seeds' });

    const log = await readEvents(projectRoot);
    assert.equal(log.length, 3);
    assert.deepEqual(log.map((e) => e.entity_id), ['kael-maren', 'aldric-solen', 'jace-delvari']);
    assert.deepEqual(log.map((e) => e.type), ['override', 'override', 'bypass']);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// ── soft-advisory vs frozen distinction surfaces ───────────────────────

test('drift: drifted entries preserve status so frozen vs soft-advisory are distinguishable', async () => {
  const { tmp, projectRoot } = await scaffold();
  try {
    await runBuild({ projectRoot, noCache: true });

    // Edit BOTH Kael (frozen) and Jace (soft-advisory) watched fields.
    const kaelPath = join(projectRoot, 'canon', 'characters', 'kael-maren.md');
    await writeFile(
      kaelPath,
      (await readFile(kaelPath, 'utf-8')).replace('"steady"]', '"hardened"]'),
      'utf-8',
    );
    const jacePath = join(projectRoot, 'canon', 'characters', 'jace-delvari.md');
    await writeFile(
      jacePath,
      (await readFile(jacePath, 'utf-8')).replace(
        'voice: ["warm", "disarming", "good-humored", "careful"]',
        'voice: ["warm", "disarming", "good-humored", "evaluative"]',
      ),
      'utf-8',
    );

    const second = await runBuild({ projectRoot, noCache: true });
    const byId = Object.fromEntries(second.drift.map((d) => [d.entity_id, d]));
    assert.equal(byId['kael-maren']?.status, 'frozen', 'Kael must surface as frozen drift (hard block)');
    assert.equal(byId['jace-delvari']?.status, 'soft-advisory', 'Jace must surface as soft-advisory drift');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
