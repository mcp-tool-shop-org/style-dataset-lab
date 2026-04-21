import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, '..', '..', 'bin', 'sdlab.js');

function runCli(args) {
  const res = spawnSync(process.execPath, [BIN, ...args], {
    encoding: 'utf-8',
    env: { ...process.env, SDLAB_QUIET_FALLBACK: '1' },
  });
  return { stdout: res.stdout || '', stderr: res.stderr || '', status: res.status };
}

test('root --help prints the banner', () => {
  const { stdout, status } = runCli(['--help']);
  assert.equal(status, 0);
  assert.match(stdout, /Style Dataset Lab CLI/);
});

test('sdlab generate --help prints command-specific help (not a run)', () => {
  const { stdout, status } = runCli(['generate', '--help']);
  assert.equal(status, 0);
  assert.match(stdout, /sdlab generate/);
  assert.match(stdout, /--dry-run/);
  // Must NOT have attempted a run (no "not reachable" / "online" etc).
  assert.doesNotMatch(stdout, /not reachable|ComfyUI online|Lane: /);
});

test('sdlab snapshot --help prints snapshot help (not listing snapshots)', () => {
  const { stdout, status } = runCli(['snapshot', '--help']);
  assert.equal(status, 0);
  assert.match(stdout, /sdlab snapshot/);
  assert.match(stdout, /create\|list\|show\|diff/);
});

test('sdlab batch generate --help prints two-word help', () => {
  const { stdout, status } = runCli(['batch', 'generate', '--help']);
  assert.equal(status, 0);
  assert.match(stdout, /--mode <id>/);
});

test('sdlab project doctor --help prints two-word help', () => {
  const { stdout, status } = runCli(['project', 'doctor', '--help']);
  assert.equal(status, 0);
  assert.match(stdout, /Validate project config/);
});

test('typo on command yields "did you mean" hint', () => {
  const { stderr, status } = runCli(['generat']);
  assert.equal(status, 1);
  assert.match(stderr, /Did you mean "generate"/);
});

test('unrecognized command (no near match) falls back to generic hint', () => {
  const { stderr, status } = runCli(['xyzqqq']);
  assert.equal(status, 1);
  assert.match(stderr, /Unknown command: xyzqqq/);
});

test('bind alias still works in help via shared HELP_TEXT', () => {
  const { stdout, status } = runCli(['bind', '--help']);
  assert.equal(status, 0);
  assert.match(stdout, /canon-bind/);
});

test('root help shows canon-bind (not duplicated bind entry)', () => {
  const { stdout } = runCli(['--help']);
  // canon-bind appears; the bind line should be labeled as alias footnote, not a separate command listing.
  assert.match(stdout, /canon-bind/);
  assert.match(stdout, /short alias for canon-bind/);
});
