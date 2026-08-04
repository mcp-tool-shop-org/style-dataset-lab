/**
 * SDL-L2: a bare namespace verb ("sdlab workflow", "sdlab batch") fell
 * through to the generic unknown-command handler, which called
 * findClosest(command, allKnownCommands()) — a corpus that includes the
 * namespace head itself, so it matched itself at distance 0 and printed
 * 'Unknown command: workflow' / 'Did you mean "workflow"?': a hint that
 * echoes exactly what the user just typed, useless at the one moment it
 * fires. Fixed to list the namespace's real subcommands instead (bare verb
 * or --help: print the list, exit 0; a genuinely wrong subcommand: throw
 * with a hint built from THAT namespace's subcommands via findClosest).
 *
 * SDL-L8: allKnownCommands()'s hardcoded `heads` array omitted 'canon' even
 * though it's a real two-word namespace (CANON_COMMANDS) — so a typo like
 * "sdlab cannon build" had no candidate to match against and got the
 * generic "Run sdlab --help" fallback while every other namespace typo got
 * a "Did you mean ...?" hint. Fixed by adding 'canon' to the heads list.
 *
 * SDL-M7: the --help Examples section's three --project examples all named
 * "star-freight", a project that ships in this git checkout but NOT in the
 * npm package (projects/ is not in package.json's `files` allow-list) — an
 * npm user copying any example got INPUT_UNKNOWN_PROJECT for a project they
 * never heard of. Fixed to a neutral "my-project" placeholder (matching the
 * `sdlab init my-project` example already above them).
 */
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

// ─── SDL-L2 ─────────────────────────────────────────────────────────────

for (const head of ['workflow', 'brief', 'run', 'batch', 'selection', 'project', 'canon']) {
  test(`sdlab ${head} (bare) lists real subcommands instead of "Did you mean \\"${head}\\"?"`, () => {
    const { stdout, stderr, status } = runCli([head]);
    assert.equal(status, 0, `expected exit 0 for a bare namespace listing, got ${status}\nstderr: ${stderr}`);
    assert.match(stdout, new RegExp(`sdlab ${head} <`));
    assert.doesNotMatch(stdout + stderr, new RegExp(`Did you mean "${head}"`), 'must not suggest the input verbatim');
    assert.doesNotMatch(stdout + stderr, /^Unknown command:/m);
  });
}

test('sdlab workflow bogus reports an unknown SUBCOMMAND with real subcommand names, not a self-referential top-level suggestion', () => {
  const { stderr, status } = runCli(['workflow', 'bogus']);
  assert.equal(status, 1);
  assert.match(stderr, /Unknown workflow subcommand: bogus/);
  assert.match(stderr, /sdlab workflow list/);
  assert.match(stderr, /sdlab workflow show/);
});

test('sdlab batch --help (bare namespace + --help) lists subcommands rather than erroring', () => {
  const { stdout, status } = runCli(['batch', '--help']);
  assert.equal(status, 0);
  assert.match(stdout, /sdlab batch </);
  assert.match(stdout, /generate/);
});

// ─── SDL-L8 ─────────────────────────────────────────────────────────────

test('sdlab cannon build (typo on the canon namespace head) suggests "canon"', () => {
  const { stderr, status } = runCli(['cannon', 'build']);
  assert.equal(status, 1);
  assert.match(stderr, /Unknown command: cannon/);
  assert.match(stderr, /Did you mean "canon"/);
});

// ─── SDL-M7 ─────────────────────────────────────────────────────────────

test('--help Examples section does not name star-freight (a project that does not ship in the npm package)', () => {
  const { stdout } = runCli(['--help']);
  const examplesSection = stdout.slice(stdout.indexOf('Examples:'));
  assert.doesNotMatch(examplesSection, /star-freight/, 'Examples section should use a neutral placeholder project, not star-freight');
  assert.match(examplesSection, /my-project/);
});
