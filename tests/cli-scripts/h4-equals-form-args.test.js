/**
 * H4: three argument-parsing regimes coexisted in this repo. lib/args.js
 * exports takeFlagValue() — hardened for both `--flag value` and
 * `--flag=value`, and it refuses to swallow a following flag as a value —
 * but zero scripts imported it. generate-identity.js, generate-controlnet.js,
 * generate-ipadapter.js and init.js hand-rolled
 * `argv.includes("--x") ? argv[argv.indexOf("--x")+1] : default`, which is
 * FALSE for the single token "--phase=follow_on" (no argv entry is EXACTLY
 * "--phase"), so the equals form silently fell back to the default with no
 * error, no warning. For generate-identity that meant `--phase=follow_on`
 * ran the discovery (txt2img) workflow instead of follow_on (img2img) —
 * silently, on an hours-long GPU job. Separately, the five canon-*.js
 * scripts used node:util parseArgs({strict:false}), which accepts any
 * misspelled flag with no feedback.
 *
 * Every case below drives the EQUALS FORM specifically (per the dispatch
 * requirement) — a test using only the space form would pass against the
 * broken code and prove nothing.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { REPO_ROOT } from '../../lib/paths.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, '..', '..', 'bin', 'sdlab.js');
const PROJECTS_DIR = join(REPO_ROOT, 'projects');

function runCli(args) {
  const res = spawnSync(process.execPath, [BIN, ...args], {
    encoding: 'utf-8',
    env: { ...process.env, SDLAB_QUIET_FALLBACK: '1' },
  });
  return { stdout: res.stdout || '', stderr: res.stderr || '', status: res.status };
}

function makeFixture(name, files) {
  const dir = join(PROJECTS_DIR, name);
  mkdirSync(dir, { recursive: true });
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

// ─── generate-identity.js: --phase=, --anchor=, --seeds=, --denoise= ──────

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

test('H4: generate-identity.js --phase=follow_on (equals form) actually selects follow_on, not silently discovery', () => {
  const name = 'sdl-h4-identity-phase';
  try {
    makeFixture(name, {
      'project.json': PROJECT_JSON,
      'identity-packet.json': IDENTITY_PACKET,
      'anchor.png': '',
    });

    const { stdout, status } = runCli([
      'generate:identity', 'identity-packet.json',
      '--project', name,
      '--dry-run',
      '--phase=follow_on',
      '--anchor=anchor.png',
      '--seeds=2',
      '--denoise=0.5',
    ]);

    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /Phase:\s*follow_on/, `expected resolved phase "follow_on", got:\n${stdout}`);
    // The "Anchor:" / "Denoise:" lines only print when phase actually
    // resolved to follow_on — a second, independent signal the equals form
    // was read (before the fix neither of these printed: phase silently
    // stayed "discovery" and the follow_on-only block never ran).
    assert.match(stdout, /Anchor:\s*anchor\.png/, `expected the Anchor: line (only prints under real follow_on):\n${stdout}`);
    assert.match(stdout, /Denoise:\s*0\.5/, `expected --denoise=0.5 (equals form) to be respected:\n${stdout}`);
    assert.match(stdout, /Seeds per shot:\s*2/, `expected --seeds=2 (equals form) to be respected:\n${stdout}`);
  } finally {
    removeFixture(name);
  }
});

test('H4: generate-identity.js --subject=NAME (equals form) filters to the named subject', () => {
  const name = 'sdl-h4-identity-subject';
  try {
    const twoSubjects = JSON.parse(IDENTITY_PACKET);
    twoSubjects.subjects.push({
      ...twoSubjects.subjects[0],
      subject_name: 'other_subject',
    });
    makeFixture(name, {
      'project.json': PROJECT_JSON,
      'identity-packet.json': JSON.stringify(twoSubjects),
    });

    const { stdout, status } = runCli([
      'generate:identity', 'identity-packet.json',
      '--project', name,
      '--dry-run',
      '--subject=other_subject',
    ]);

    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /Subjects:\s*1/, `expected the --subject= filter to narrow to exactly one subject:\n${stdout}`);
    assert.match(stdout, /other_subject/, `expected the filtered subject's name to appear:\n${stdout}`);
  } finally {
    removeFixture(name);
  }
});

// ─── generate-controlnet.js: --seeds=, --weight=, --guidance-end= ─────────

test('H4: generate-controlnet.js --seeds= / --weight= / --guidance-end= (equals form) are respected, not silently defaulted', () => {
  const name = 'sdl-h4-controlnet-equals';
  try {
    makeFixture(name, {
      'project.json': PROJECT_JSON,
      'guide.png': '',
    });

    const { stdout, status } = runCli([
      'generate:controlnet',
      '--project', name,
      '--subject', 'test_subject',
      '--guide', 'guide.png',
      '--prompt', 'a test prompt',
      '--dry-run',
      '--seeds=2',
      '--weight=1.1',
      '--guidance-end=0.4',
    ]);

    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /Seeds:\s*2/, `expected --seeds=2 (equals form) to be respected, not the default 4:\n${stdout}`);
    assert.match(stdout, /Weight:\s*1\.1, Guidance end:\s*0\.4/, `expected --weight=/--guidance-end= (equals form) to be respected:\n${stdout}`);
  } finally {
    removeFixture(name);
  }
});

// ─── generate-ipadapter.js: --seeds=, --weight=, --start=, --end= ─────────

test('H4: generate-ipadapter.js --seeds= / --weight= / --start= / --end= (equals form) are respected, not silently defaulted', () => {
  const name = 'sdl-h4-ipadapter-equals';
  try {
    makeFixture(name, {
      'project.json': PROJECT_JSON,
      'ref.png': '',
    });

    const { stdout, status } = runCli([
      'generate:ipadapter',
      '--project', name,
      '--subject', 'test_subject',
      '--ref', 'ref.png',
      '--prompt', 'a test prompt',
      '--dry-run',
      '--seeds=2',
      '--weight=0.8',
      '--start=0.1',
      '--end=0.9',
    ]);

    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /Seeds:\s*2/, `expected --seeds=2 (equals form) to be respected, not the default 4:\n${stdout}`);
    assert.match(stdout, /Weight:\s*0\.8, Range:\s*0\.1-0\.9/, `expected --weight=/--start=/--end= (equals form) to be respected:\n${stdout}`);
  } finally {
    removeFixture(name);
  }
});

// ─── init.js: --domain= ────────────────────────────────────────────────

test('H4: sdlab init NAME --domain=character-design (equals form) actually scaffolds the named domain, not "generic"', () => {
  const name = 'sdl-h4-init-domain-equals';
  const projectDir = join(PROJECTS_DIR, name);
  try {
    const { stdout, status } = runCli(['init', name, '--domain=character-design']);
    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /Domain:\s*character-design/, `expected --domain= (equals form) to select character-design, not fall back to generic:\n${stdout}`);

    const projectJson = JSON.parse(spawnSync(process.execPath, ['-e', `process.stdout.write(require('fs').readFileSync(${JSON.stringify(join(projectDir, 'project.json'))}, 'utf-8'))`]).stdout);
    assert.equal(projectJson.domain, 'character-design');
  } finally {
    rmSync(projectDir, { recursive: true, force: true });
  }
});

// ─── canon-*.js: post-validation of parseArgs({strict:false}) ─────────────

function scaffoldCanonProject(name) {
  const projectDir = join(PROJECTS_DIR, name);
  const canonDir = join(projectDir, 'canon');
  mkdirSync(join(canonDir, 'schemas'), { recursive: true });
  mkdirSync(join(canonDir, 'monsters'), { recursive: true });
  mkdirSync(join(projectDir, 'canon-build'), { recursive: true });
  writeFileSync(join(projectDir, 'project.json'), PROJECT_JSON);

  writeFileSync(
    join(canonDir, 'schemas', 'monster.schema.json'),
    JSON.stringify({ $id: 'monster', version: '1.0.0', type: 'object' }, null, 2)
  );
  writeFileSync(
    join(projectDir, 'canon-build', 'config.json'),
    JSON.stringify({
      project_id: name,
      canon_root: canonDir,
      schema_dir: join(canonDir, 'schemas'),
      entity_dirs: { 'monster.schema.json': 'monsters' },
      schema_to_lane: { 'monster.schema.json': { source: 'constant', value: 'creature' } },
    }, null, 2)
  );
  const yaml = [
    'id: nemean-lion',
    'species_tag: quadruped',
    'anatomy_descriptor:',
    '  heads: 1',
    '  limbs: 4',
    '  notable: []',
    'lineage_reference: none',
    'scale_indicator: larger',
    'forbidden_inputs:',
    '  - generic',
    'signature_features:',
    '  - feature-a',
    'sources:',
    '  - X',
  ].join('\n');
  writeFileSync(join(canonDir, 'monsters', 'nemean-lion.md'), `---\n${yaml}\n---\n`);
  return projectDir;
}

test('H4: sdlab canon freeze rejects a misspelled optional flag instead of silently keeping the default', () => {
  const name = 'sdl-h4-canon-freeze-typo';
  try {
    scaffoldCanonProject(name);

    // --staus (typo of --status) with a real build hash provided so the
    // "no build witness" precondition doesn't mask this — the point under
    // test is the flag-name typo, not the witness-chain requirement.
    const { stderr, status } = runCli([
      'canon', 'freeze', 'nemean-lion',
      '--project', name,
      '--reason', 'test freeze',
      '--build', 'fake-build-hash-for-test',
      '--staus', 'soft-advisory',
    ]);

    assert.notEqual(status, 0, `expected a nonzero exit for an unknown flag, got 0`);
    assert.match(stderr, /Unknown flag: --staus/, `expected the typo to be rejected by name:\n${stderr}`);
  } finally {
    removeFixture(name);
  }
});

test('H4: sdlab canon freeze --status (correctly spelled) still works normally — explicit PASS branch for contrast', () => {
  const name = 'sdl-h4-canon-freeze-ok';
  try {
    scaffoldCanonProject(name);

    const { stdout, status } = runCli([
      'canon', 'freeze', 'nemean-lion',
      '--project', name,
      '--reason', 'test freeze',
      '--build', 'fake-build-hash-for-test',
      '--status', 'soft-advisory',
    ]);

    assert.equal(status, 0, `expected exit 0 for a correctly-spelled flag, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /soft-advisory/);
  } finally {
    removeFixture(name);
  }
});

test('H4: sdlab canon build rejects a misspelled optional flag instead of silently keeping the default', () => {
  const name = 'sdl-h4-canon-build-typo';
  try {
    scaffoldCanonProject(name);

    const { stderr, status } = runCli(['canon', 'build', '--project', name, '--ful']); // typo of --full
    assert.notEqual(status, 0);
    assert.match(stderr, /Unknown flag: --ful/);
  } finally {
    removeFixture(name);
  }
});
