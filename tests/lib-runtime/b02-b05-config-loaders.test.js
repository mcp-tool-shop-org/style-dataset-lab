/**
 * Unit tests for B02 and B05 in lib/config.js.
 *
 * B02: detectLane()/detectGroup() build `new RegExp(pattern)` from strings
 * loaded verbatim from hand-authored lanes.json/terminology.json, with
 * ZERO validation at load time across all 7 construction sites. The first
 * validation was the lazy `new RegExp()` call on whatever record happened
 * to be processed first — one unescaped bracket aborted a whole
 * `sdlab bind` pass with a raw `SyntaxError: Invalid regular expression`
 * naming neither the file, the lane/group, nor the offending pattern.
 * Fix: validate every pattern at LOAD time and raise one structured
 * inputError naming the file, the lane/group id, and the pattern.
 *
 * B05: the five config loaders (loadProjectMeta, loadConstitution,
 * loadLanes, loadRubric, loadTerminology) silently substituted hardcoded
 * empty defaults when their file was missing — the module didn't even
 * import lib/log.js. A dropped terminology.json made detectGroup() return
 * null for every record; a 300-record bind exited 0 with every group
 * silently "unknown", discovered days later. Fix: warn() once per loader
 * when it substitutes a default, naming the expected path.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  loadProjectMeta,
  loadConstitution,
  loadLanes,
  loadRubric,
  loadTerminology,
  detectLane,
  detectGroup,
} from '../../lib/config.js';

async function makeProjectDir(prefix) {
  return await mkdtemp(join(tmpdir(), prefix));
}

function captureStderr(fn) {
  const orig = console.error;
  const lines = [];
  console.error = (...a) => lines.push(a.join(' '));
  try {
    return { result: fn(), lines };
  } finally {
    console.error = orig;
  }
}

// ─── B02: regex validation at load time ───────────────────────────

test('loadLanes throws a structured error naming the file, lane id, and pattern for a bad regex (B02)', async () => {
  const dir = await makeProjectDir('sdl-b02-lanes-');
  try {
    await writeFile(
      join(dir, 'lanes.json'),
      JSON.stringify({
        default_lane: 'default',
        lanes: [{ id: 'freeport-lane', id_patterns: ['ok_pattern', '[freeport'] }],
      }),
    );

    assert.throws(
      () => loadLanes(dir),
      (err) => {
        assert.equal(err.code, 'INPUT_BAD_REGEX');
        assert.match(err.message, /lanes\.json/);
        assert.match(err.message, /freeport-lane/);
        assert.match(err.message, /\[freeport/);
        return true;
      },
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadLanes rejects the bad pattern BEFORE any record is processed — not lazily inside detectLane (B02)', async () => {
  // This is the actual defect: previously the bad regex only blew up the
  // first time detectLane() happened to test a record against it. Proving
  // the throw happens at loadLanes() time (never reaching detectLane) is
  // the point — a test that only checked detectLane's behavior would miss
  // that loadLanes was ever supposed to be the gate.
  const dir = await makeProjectDir('sdl-b02-lanes-early-');
  try {
    await writeFile(
      join(dir, 'lanes.json'),
      JSON.stringify({ default_lane: 'default', lanes: [{ id: 'bad', id_patterns: ['(unclosed'] }] }),
    );
    assert.throws(() => loadLanes(dir), (err) => err.code === 'INPUT_BAD_REGEX');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadLanes still loads a well-formed lanes.json (no false positive)', async () => {
  const dir = await makeProjectDir('sdl-b02-lanes-ok-');
  try {
    await writeFile(
      join(dir, 'lanes.json'),
      JSON.stringify({ default_lane: 'default', lanes: [{ id: 'concept', id_patterns: ['concept_.*', 'subj_[0-9]+'] }] }),
    );
    const lanes = loadLanes(dir);
    assert.equal(lanes.lanes.length, 1);
    assert.equal(detectLane('concept_001', '', lanes), 'concept');
    assert.equal(detectLane('unrelated', '', lanes), 'default');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadTerminology throws a structured error for a bad pattern in a group\'s id_patterns (B02)', async () => {
  const dir = await makeProjectDir('sdl-b02-term-group-');
  try {
    await writeFile(
      join(dir, 'terminology.json'),
      JSON.stringify({ groups: { pirates: { id_patterns: ['pirate_', '[unclosed'] } } }),
    );
    assert.throws(
      () => loadTerminology(dir),
      (err) => {
        assert.equal(err.code, 'INPUT_BAD_REGEX');
        assert.match(err.message, /terminology\.json/);
        assert.match(err.message, /pirates/);
        return true;
      },
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadTerminology throws for a bad pattern in cross_group_patterns/edge_defaults/null_faction_patterns/id_fallbacks keys too (B02 — all 7 sites)', async () => {
  const cases = [
    { field: 'cross_group_patterns', value: { '[bad': 'detect_from_id_suffix' } },
    { field: 'edge_defaults', value: { '[bad': 'somegroup' } },
    { field: 'null_faction_patterns', value: ['[bad'] },
    { field: 'id_fallbacks', value: { '[bad': 'somegroup' } },
  ];
  for (const { field, value } of cases) {
    const dir = await makeProjectDir(`sdl-b02-term-${field}-`);
    try {
      await writeFile(join(dir, 'terminology.json'), JSON.stringify({ groups: {}, [field]: value }));
      assert.throws(
        () => loadTerminology(dir),
        (err) => err.code === 'INPUT_BAD_REGEX',
        `expected loadTerminology to reject a bad pattern in ${field}`,
      );
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  }
});

test('loadTerminology still loads well-formed terminology.json and detectGroup works (no false positive)', async () => {
  const dir = await makeProjectDir('sdl-b02-term-ok-');
  try {
    await writeFile(
      join(dir, 'terminology.json'),
      JSON.stringify({
        groups: { pirates: { id_patterns: ['pirate_'], prompt_patterns: ['pirate'] } },
        id_detection_order: ['pirates'],
        prompt_detection_order: ['pirates'],
      }),
    );
    const term = loadTerminology(dir);
    assert.equal(detectGroup('pirate_001', '', term), 'pirates');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

// ─── B05: warn once per loader on default substitution ────────────

test('loadProjectMeta warns and names project.json\'s expected path when the file is missing (B05)', async () => {
  const dir = await makeProjectDir('sdl-b05-meta-');
  try {
    const { result, lines } = captureStderr(() => loadProjectMeta(dir));
    assert.equal(result.name, 'unknown', 'still substitutes the built-in default (unchanged behavior)');
    assert.equal(lines.length, 1, 'expected exactly one warn() call');
    assert.match(lines[0], /project\.json/);
    assert.match(lines[0].toLowerCase(), /not found|missing/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadConstitution warns when constitution.json is missing (B05)', async () => {
  const dir = await makeProjectDir('sdl-b05-constitution-');
  try {
    const { result, lines } = captureStderr(() => loadConstitution(dir));
    assert.deepEqual(result, { rules: [] });
    assert.equal(lines.length, 1);
    assert.match(lines[0], /constitution\.json/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadLanes warns when lanes.json is missing (B05)', async () => {
  const dir = await makeProjectDir('sdl-b05-lanes-');
  try {
    const { result, lines } = captureStderr(() => loadLanes(dir));
    assert.deepEqual(result, { default_lane: 'default', lanes: [] });
    assert.equal(lines.length, 1);
    assert.match(lines[0], /lanes\.json/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadRubric warns when rubric.json is missing (B05)', async () => {
  const dir = await makeProjectDir('sdl-b05-rubric-');
  try {
    const { result, lines } = captureStderr(() => loadRubric(dir));
    assert.equal(result.thresholds.pass, 0.7);
    assert.equal(lines.length, 1);
    assert.match(lines[0], /rubric\.json/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('loadTerminology warns when terminology.json is missing — this is the exact scenario from the finding (B05)', async () => {
  const dir = await makeProjectDir('sdl-b05-term-');
  try {
    const { result, lines } = captureStderr(() => loadTerminology(dir));
    assert.deepEqual(result.groups, {});
    assert.equal(lines.length, 1, 'expected exactly one warn() call, not zero (the defect) and not one per detectGroup call');
    assert.match(lines[0], /terminology\.json/);

    // The actual downstream symptom the finding describes: detectGroup()
    // returns null for every record once terminology.json is gone. Proves
    // the warn actually corresponds to the condition that causes silent
    // "unknown" factions — not an unrelated code path.
    assert.equal(detectGroup('anything', 'a prompt', result), null);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('all five loaders stay silent when their files are present and well-formed (no false positives)', async () => {
  const dir = await makeProjectDir('sdl-b05-healthy-');
  try {
    await writeFile(join(dir, 'project.json'), JSON.stringify({ name: 'p' }));
    await writeFile(join(dir, 'constitution.json'), JSON.stringify({ rules: [] }));
    await writeFile(join(dir, 'lanes.json'), JSON.stringify({ default_lane: 'd', lanes: [] }));
    await writeFile(join(dir, 'rubric.json'), JSON.stringify({ dimensions: [] }));
    await writeFile(join(dir, 'terminology.json'), JSON.stringify({ groups: {} }));

    const { lines: l1 } = captureStderr(() => loadProjectMeta(dir));
    const { lines: l2 } = captureStderr(() => loadConstitution(dir));
    const { lines: l3 } = captureStderr(() => loadLanes(dir));
    const { lines: l4 } = captureStderr(() => loadRubric(dir));
    const { lines: l5 } = captureStderr(() => loadTerminology(dir));

    for (const lines of [l1, l2, l3, l4, l5]) {
      assert.equal(lines.length, 0);
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
