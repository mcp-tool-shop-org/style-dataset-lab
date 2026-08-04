/**
 * M1: scripts/doctor.js's fail() was a bare console.log — none of its ~40
 * call sites carried a hint, and the terminal runtimeError('PROJECT_UNHEALTHY',
 * ...) omitted the third hint argument, so the one error doctor can exit
 * non-zero on printed with no "Hint:" line, unlike every other command.
 * Two checks that already computed a location threw it away: "rule missing
 * id" never named the index, and "duplicate rule ID" named the id but not
 * the two rules[] indices that collided.
 *
 * Doctor is the tool people run when confused; its output IS the
 * error-recovery story.
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

function makeFixture(name, files) {
  const dir = join(PROJECTS_DIR, name);
  assert.equal(existsSync(dir), false, `fixture "${name}" must not already exist`);
  mkdirSync(dir, { recursive: true });
  for (const [file, content] of Object.entries(files)) {
    writeFileSync(join(dir, file), content);
  }
  return dir;
}

function removeFixture(name) {
  rmSync(join(PROJECTS_DIR, name), { recursive: true, force: true });
}

const BASE_CONFIGS = {
  'project.json': JSON.stringify({ name: 'doctor-hints-fixture', domain: 'test' }),
  'lanes.json': JSON.stringify({ default_lane: 'default', lanes: [] }),
  'rubric.json': JSON.stringify({ dimensions: ['quality'], thresholds: { approved: { pass: 0.7 } } }),
  'terminology.json': JSON.stringify({ groups: {} }),
};

test('doctor: PROJECT_UNHEALTHY carries a real, non-empty hint pointing back at doctor', async () => {
  const name = '__sdl_doctor_hint_missing_cfg__';
  makeFixture(name, {}); // no config files at all — guaranteed failures
  try {
    await assert.rejects(
      () => doctorRun(['--project', name]),
      (err) => {
        assert.equal(err.code, 'PROJECT_UNHEALTHY');
        assert.ok(err.hint && err.hint.length > 0, 'PROJECT_UNHEALTHY must carry a non-empty hint');
        assert.match(err.hint, /doctor/i, 'hint should point back at re-running doctor after fixing the issues');
        return true;
      }
    );
  } finally {
    removeFixture(name);
  }
});

test('doctor: a missing config file failure line carries a concrete Hint:', () => {
  const name = '__sdl_doctor_hint_missing_file_cli__';
  makeFixture(name, {}); // missing every required config file
  try {
    const { stdout } = runCli(['project', 'doctor', '--project', name]);
    assert.match(stdout, /Missing: project\.json/);
    assert.match(stdout, /Hint:.*sdlab init/i, `expected a Hint: line naming "sdlab init" near the missing-file failure:\n${stdout}`);
  } finally {
    removeFixture(name);
  }
});

test('doctor: duplicate rule ID failure names BOTH colliding rules[] indices, not just the id', () => {
  const name = '__sdl_doctor_hint_dup_rule__';
  makeFixture(name, {
    ...BASE_CONFIGS,
    'constitution.json': JSON.stringify({
      rules: [
        { id: 'R1', dims: ['quality'] },
        { id: 'R1', dims: ['quality'] },
      ],
    }),
  });
  try {
    const { stdout } = runCli(['project', 'doctor', '--project', name]);
    assert.match(stdout, /duplicate rule ID "R1"/);
    // Before the fix: only the id was named. After: both colliding indices are.
    assert.match(stdout, /rules\[0\]/, `expected the first colliding location (rules[0]) to be named:\n${stdout}`);
    assert.match(stdout, /rules\[1\]/, `expected the second colliding location (rules[1]) to be named:\n${stdout}`);
  } finally {
    removeFixture(name);
  }
});

test('doctor: "rule missing id" failure names which rules[] index is missing it', () => {
  const name = '__sdl_doctor_hint_missing_rule_id__';
  makeFixture(name, {
    ...BASE_CONFIGS,
    'constitution.json': JSON.stringify({
      rules: [
        { id: 'R1', dims: ['quality'] },
        { dims: ['quality'] }, // no id — this is rules[1]
      ],
    }),
  });
  try {
    const { stdout } = runCli(['project', 'doctor', '--project', name]);
    assert.match(stdout, /rule missing "id"/);
    assert.match(stdout, /rules\[1\]/, `expected the offending index (rules[1]) to be named:\n${stdout}`);
  } finally {
    removeFixture(name);
  }
});

test('doctor: the known-good in-repo project (star-freight) is unaffected — still reports HEALTHY end to end (backward compatibility)', () => {
  const { status, stdout } = runCli(['project', 'doctor', '--project', 'star-freight']);
  assert.equal(status, 0);
  assert.match(stdout, /HEALTHY/);
});
