/**
 * scripts/doctor.js had ZERO tests before this file (27 checks, 495 lines) —
 * which is how two CRITICAL defects shipped and stayed shipped:
 *
 *   SDL-C3-completion — doctor.js resolved --project via a raw
 *     join(REPO_ROOT, 'projects', projectName) instead of the hardened
 *     getProjectRoot(), so `sdlab project doctor --project "../../ai-eyes-mcp"`
 *     escaped the projects/ directory entirely and reported on a SIBLING REPO.
 *
 *   SDL-C4 — the "project directory exists" check used a bare `return` on
 *     failure instead of throwing, so run() resolved successfully and
 *     `sdlab project doctor --project <missing>` exited 0. This is the exact
 *     command `npm run verify` and the CI "Smoke test — doctor" step run —
 *     an ANDON gate that always said "fine" was worse than no gate at all.
 *
 * Both are now the SAME fix: doctor.js resolves projectDir via
 * getProjectRoot(), which throws INPUT_UNSAFE_PROJECT_NAME for a traversal
 * attempt and INPUT_UNKNOWN_PROJECT (instead of returning quietly) for a
 * missing project — so reverting that one resolution line makes every test
 * below fail simultaneously.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { run as doctorRun } from '../../scripts/doctor.js';
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

/** Create projects/<name>/ with the given { filename: contentString } map. */
function makeFixture(name, files) {
  const dir = join(PROJECTS_DIR, name);
  mkdirSync(dir, { recursive: true });
  for (const [file, content] of Object.entries(files)) {
    writeFileSync(join(dir, file), content);
  }
  return dir;
}

function removeFixture(name) {
  const dir = join(PROJECTS_DIR, name);
  rmSync(dir, { recursive: true, force: true });
}

const HEALTHY_CONFIGS = {
  'project.json': JSON.stringify({ name: 'healthy-fixture', domain: 'test' }),
  'constitution.json': JSON.stringify({ rules: [{ id: 'R1', dims: ['quality'] }] }),
  'lanes.json': JSON.stringify({ default_lane: 'default', lanes: [] }),
  'rubric.json': JSON.stringify({ dimensions: ['quality'], thresholds: { approved: { pass: 0.7 } } }),
  'terminology.json': JSON.stringify({ groups: {} }),
};

// ─── SDL-C4: missing project dir → rejects (not a silent resolve) ─────────

test('doctor: missing project dir rejects run() with INPUT_UNKNOWN_PROJECT (not a silent resolve)', async () => {
  const name = '__sdl_doctor_test_missing__';
  assert.equal(existsSync(join(PROJECTS_DIR, name)), false, 'fixture must not already exist');
  await assert.rejects(
    () => doctorRun(['--project', name]),
    (err) => err.code === 'INPUT_UNKNOWN_PROJECT'
  );
});

test('doctor: missing project dir exits nonzero through the real CLI (this is what `npm run verify` and CI\'s smoke test rely on)', () => {
  const { status, stderr } = runCli(['project', 'doctor', '--project', '__sdl_doctor_test_missing_cli__']);
  assert.notEqual(status, 0, 'doctor must NOT exit 0 for a project that does not exist');
  assert.match(stderr, /INPUT_UNKNOWN_PROJECT|not found/);
});

// ─── SDL-C3-completion: path traversal via --project → rejects ────────────

test('doctor: --project "../../ai-eyes-mcp" is refused, not resolved as a sibling repo (SDL-C3-completion exploit reproduction)', async () => {
  await assert.rejects(
    () => doctorRun(['--project', '../../ai-eyes-mcp']),
    (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME'
  );
});

test('doctor: the same exploit is refused through the real CLI with a nonzero exit', () => {
  const { status, stderr } = runCli(['project', 'doctor', '--project', '../../ai-eyes-mcp']);
  assert.notEqual(status, 0);
  assert.match(stderr, /INPUT_UNSAFE_PROJECT_NAME/);
  // The old bug printed "Path: <escaped path>" then "Project directory exists"
  // — assert neither leaked to stdout/stderr combined output shape.
  assert.doesNotMatch(stderr, /Project directory exists/);
});

test('doctor: backslash traversal is refused too', async () => {
  await assert.rejects(
    () => doctorRun(['--project', '..\\..\\ai-eyes-mcp']),
    (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME'
  );
});

// ─── present but missing config files → rejects ────────────────────────────

test('doctor: project present but missing all config files rejects with PROJECT_UNHEALTHY', async () => {
  const name = '__sdl_doctor_test_empty__';
  makeFixture(name, {}); // directory exists, zero config files inside
  try {
    await assert.rejects(
      () => doctorRun(['--project', name]),
      (err) => err.code === 'PROJECT_UNHEALTHY'
    );
  } finally {
    removeFixture(name);
  }
});

// ─── invalid JSON → rejects ─────────────────────────────────────────────

test('doctor: invalid JSON in a required config file rejects with PROJECT_UNHEALTHY', async () => {
  const name = '__sdl_doctor_test_badjson__';
  makeFixture(name, {
    ...HEALTHY_CONFIGS,
    'project.json': '{ this is not valid json',
  });
  try {
    await assert.rejects(
      () => doctorRun(['--project', name]),
      (err) => err.code === 'PROJECT_UNHEALTHY'
    );
  } finally {
    removeFixture(name);
  }
});

// ─── healthy project → resolves ────────────────────────────────────────

test('doctor: a fully healthy project resolves run() without throwing', async () => {
  const name = '__sdl_doctor_test_healthy__';
  makeFixture(name, HEALTHY_CONFIGS);
  try {
    await assert.doesNotReject(() => doctorRun(['--project', name]));
  } finally {
    removeFixture(name);
  }
});

test('doctor: the known-good in-repo project (star-freight) still reports HEALTHY end to end (backward compatibility)', () => {
  const { status, stdout } = runCli(['project', 'doctor', '--project', 'star-freight']);
  assert.equal(status, 0);
  assert.match(stdout, /HEALTHY/);
});
