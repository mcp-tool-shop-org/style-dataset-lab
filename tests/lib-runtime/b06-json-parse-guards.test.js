/**
 * Unit tests for B06 — unguarded JSON.parse + inconsistent list resilience
 * in lib/workflow-profiles.js and lib/batch-modes.js.
 *
 * getWorkflowProfile() (workflow-profiles.js:110) and getBatchMode()
 * (batch-modes.js:66) both called JSON.parse with no try/catch, so a
 * malformed profile/mode file threw a raw, uncaught SyntaxError instead of
 * a structured inputError naming the file (the pattern lib/config.js's
 * loadJsonFile already established). getWorkflowProfile also threw bare
 * `new Error(...)` for its not-found/invalid-shape cases instead of the
 * structured errors used everywhere else in this codebase.
 *
 * Separately: listWorkflowProfiles() already skips a malformed file
 * per-entry (try/catch inside its loop), but the structurally identical
 * listBatchModes() had no such guard — one bad batch-mode file threw
 * uncaught and hid EVERY batch mode, not just the broken one.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { getWorkflowProfile, listWorkflowProfiles } from '../../lib/workflow-profiles.js';
import { getBatchMode, listBatchModes } from '../../lib/batch-modes.js';

async function makeProjectDir(prefix) {
  return await mkdtemp(join(tmpdir(), prefix));
}

// ─── getWorkflowProfile: unguarded JSON.parse ─────────────────────

test('getWorkflowProfile raises a structured error naming the file for malformed JSON, not a raw SyntaxError (B06)', async () => {
  const dir = await makeProjectDir('sdl-b06-wfprofile-badjson-');
  try {
    const profilesDir = join(dir, 'workflows', 'profiles');
    await mkdir(profilesDir, { recursive: true });
    await writeFile(join(profilesDir, 'broken.json'), '{ this is not valid json');

    await assert.rejects(
      () => getWorkflowProfile(dir, 'broken'),
      (err) => {
        assert.equal(err.code, 'INPUT_INVALID_JSON');
        assert.match(err.message, /broken\.json/);
        assert.ok(!(err instanceof SyntaxError), 'must not be a raw SyntaxError');
        return true;
      },
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('getWorkflowProfile still loads a well-formed profile (no false positive)', async () => {
  const dir = await makeProjectDir('sdl-b06-wfprofile-ok-');
  try {
    const profilesDir = join(dir, 'workflows', 'profiles');
    await mkdir(profilesDir, { recursive: true });
    const profile = {
      workflow_id: 'good', label: 'Good', lane_id: 'concept', output_mode: 'portrait_set',
      output_count: 4, prompt_strategy: { style_prefix: [], structure: 's', must_include: [] },
      negative_strategy: { must_avoid: [] }, canon_focus: [], drift_guards: [],
      runtime_defaults: { adapter_target: 'comfyui' },
    };
    await writeFile(join(profilesDir, 'good.json'), JSON.stringify(profile));
    const loaded = await getWorkflowProfile(dir, 'good');
    assert.equal(loaded.workflow_id, 'good');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

// ─── getBatchMode: unguarded JSON.parse ───────────────────────────

test('getBatchMode raises a structured error naming the file for malformed JSON, not a raw SyntaxError (B06)', async () => {
  const dir = await makeProjectDir('sdl-b06-batchmode-badjson-');
  try {
    const modesDir = join(dir, 'workflows', 'batch-modes');
    await mkdir(modesDir, { recursive: true });
    await writeFile(join(modesDir, 'broken.json'), '{ not json at all');

    assert.throws(
      () => getBatchMode(dir, 'broken'),
      (err) => {
        assert.equal(err.code, 'INPUT_INVALID_JSON');
        assert.match(err.message, /broken\.json/);
        assert.ok(!(err instanceof SyntaxError), 'must not be a raw SyntaxError');
        return true;
      },
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('getBatchMode still loads a well-formed mode (no false positive)', async () => {
  const dir = await makeProjectDir('sdl-b06-batchmode-ok-');
  try {
    const modesDir = join(dir, 'workflows', 'batch-modes');
    await mkdir(modesDir, { recursive: true });
    await writeFile(join(modesDir, 'good.json'), JSON.stringify({ mode_id: 'good', label: 'Good' }));
    const loaded = getBatchMode(dir, 'good');
    assert.equal(loaded.mode_id, 'good');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

// ─── listBatchModes: one bad file must not hide every mode ────────

test('listBatchModes skips ONE malformed file and still lists the healthy ones — matching listWorkflowProfiles\' existing resilience (B06)', async () => {
  const dir = await makeProjectDir('sdl-b06-listbatch-');
  try {
    const modesDir = join(dir, 'workflows', 'batch-modes');
    await mkdir(modesDir, { recursive: true });
    await writeFile(join(modesDir, 'good-a.json'), JSON.stringify({ mode_id: 'good-a', label: 'A', batch_type: 'moodboard', base_workflow_id: 'w', variant_plan: [{ slot_id: 's1' }] }));
    await writeFile(join(modesDir, 'zzz-broken.json'), '{ totally not json');
    await writeFile(join(modesDir, 'good-b.json'), JSON.stringify({ mode_id: 'good-b', label: 'B', batch_type: 'moodboard', base_workflow_id: 'w', variant_plan: [{ slot_id: 's1' }] }));

    // Before the fix, this call throws (uncaught SyntaxError) and the
    // caller never sees good-a or good-b either — one bad file hides
    // EVERY batch mode, not just the broken one.
    const modes = listBatchModes(dir);
    const ids = modes.map((m) => m.mode_id).sort();
    assert.deepEqual(ids, ['good-a', 'good-b'], 'the two healthy modes must still be listed despite the broken third file');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('listWorkflowProfiles already has this resilience — regression guard, not a new behavior', async () => {
  const dir = await makeProjectDir('sdl-b06-listwf-');
  try {
    const profilesDir = join(dir, 'workflows', 'profiles');
    await mkdir(profilesDir, { recursive: true });
    await writeFile(join(profilesDir, 'good.json'), JSON.stringify({ workflow_id: 'good', label: 'Good' }));
    await writeFile(join(profilesDir, 'broken.json'), '{ nope');

    const profiles = await listWorkflowProfiles(dir);
    assert.deepEqual(profiles.map((p) => p.workflow_id), ['good']);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
