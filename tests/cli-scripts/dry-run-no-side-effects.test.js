/**
 * SDL-M11: generate.js, generate-identity.js, generate-controlnet.js,
 * generate-ipadapter.js and painterly.js all called
 * mkdir(..., {recursive:true}) OUTSIDE the `if (!dryRun)` guard, so a
 * `--dry-run` preview still created outputs/candidates/, records/, or
 * outputs/painterly/ on disk. README.md promises --dry-run "to preview the
 * effect first" — a preview that leaves directories behind is not a preview.
 *
 * Each case below builds a fresh, minimal fixture project where the target
 * output directory does NOT yet exist, runs the script with --dry-run, and
 * asserts the directory is STILL absent afterward.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { REPO_ROOT } from '../../lib/paths.js';

const PROJECTS_DIR = join(REPO_ROOT, 'projects');

function makeFixture(name, files) {
  const dir = join(PROJECTS_DIR, name);
  for (const [rel, content] of Object.entries(files)) {
    const full = join(dir, rel);
    mkdirSync(join(full, '..'), { recursive: true });
    writeFileSync(full, content);
  }
  return dir;
}

function removeFixture(name) {
  rmSync(join(PROJECTS_DIR, name), { recursive: true, force: true });
}

const PROJECT_JSON = JSON.stringify({ name: 'fixture', domain: 'test', defaults: {} });

const GENERATE_PACK = JSON.stringify({
  style_prefix: 'test style',
  negative: 'test negative',
  subjects: [{ id: 'test_subject', prompt: 'a test prompt', variations: 1 }],
});

const IDENTITY_PACKET = JSON.stringify({
  lane: 'test-lane',
  style_prefix: 'test style',
  negative_base: 'test negative',
  subjects: [{
    subject_name: 'test_subject',
    subject_type: 'named_character',
    faction: 'test',
    role: 'test',
    identity_lock: { non_negotiable_details: ['detail 1'], forbidden_drift_cues: ['cue 1'] },
    shots: [{
      id: 'shot1', view_type: 'anchor_portrait', shot_type: 'test',
      identity_anchor: 'test', scene_function: 'test', prompt: 'a test prompt',
    }],
  }],
});

test('generate.js --dry-run does not create outputs/candidates or records', async () => {
  const name = 'sdl-m11-generate';
  makeFixture(name, {
    'project.json': PROJECT_JSON,
    'inputs/prompts/pack.json': GENERATE_PACK,
  });
  try {
    const { run } = await import('../../scripts/generate.js');
    await run(['inputs/prompts/pack.json', '--project', name, '--dry-run']);
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'outputs', 'candidates')), false, 'outputs/candidates was created by a dry run');
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'records')), false, 'records/ was created by a dry run');
  } finally {
    removeFixture(name);
  }
});

test('generate-identity.js --dry-run does not create outputs/candidates or records', async () => {
  const name = 'sdl-m11-generate-identity';
  makeFixture(name, {
    'project.json': PROJECT_JSON,
    'identity-packet.json': IDENTITY_PACKET,
  });
  try {
    const { run } = await import('../../scripts/generate-identity.js');
    await run(['identity-packet.json', '--project', name, '--dry-run']);
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'outputs', 'candidates')), false, 'outputs/candidates was created by a dry run');
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'records')), false, 'records/ was created by a dry run');
  } finally {
    removeFixture(name);
  }
});

test('generate-controlnet.js --dry-run does not create outputs/candidates', async () => {
  const name = 'sdl-m11-generate-controlnet';
  makeFixture(name, {
    'project.json': PROJECT_JSON,
    'guide.png': '',
  });
  try {
    const { run } = await import('../../scripts/generate-controlnet.js');
    await run(['--project', name, '--subject', 'test_subject', '--guide', 'guide.png', '--prompt', 'a test prompt', '--dry-run']);
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'outputs', 'candidates')), false, 'outputs/candidates was created by a dry run');
  } finally {
    removeFixture(name);
  }
});

test('generate-ipadapter.js --dry-run does not create outputs/candidates', async () => {
  const name = 'sdl-m11-generate-ipadapter';
  makeFixture(name, {
    'project.json': PROJECT_JSON,
    'ref.png': '',
  });
  try {
    const { run } = await import('../../scripts/generate-ipadapter.js');
    await run(['--project', name, '--subject', 'test_subject', '--ref', 'ref.png', '--prompt', 'a test prompt', '--dry-run']);
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'outputs', 'candidates')), false, 'outputs/candidates was created by a dry run');
  } finally {
    removeFixture(name);
  }
});

test('painterly.js --dry-run does not create outputs/painterly', async () => {
  const name = 'sdl-m11-painterly';
  makeFixture(name, {
    'project.json': PROJECT_JSON,
    'outputs/approved/test.png': '',
  });
  try {
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'outputs', 'painterly')), false, 'fixture setup error: outputs/painterly should not pre-exist');
    const { run } = await import('../../scripts/painterly.js');
    await run(['--project', name, '--dry-run']);
    assert.equal(existsSync(join(PROJECTS_DIR, name, 'outputs', 'painterly')), false, 'outputs/painterly was created by a dry run');
  } finally {
    removeFixture(name);
  }
});
