/**
 * SDL-H12: canon-build.js, canon-freeze.js, canon-unfreeze.js,
 * canon-freeze-status.js and canon-drift.js resolved their project root via
 * `join(process.cwd(), 'projects', projectName)`. For a globally-installed
 * `sdlab` the user is never inside the package directory, so this pointed at
 * the wrong place. canon-build.js at least guarded with an existsSync check
 * and an accurate "not found" hint; the other four had no guard and failed
 * DEEPER inside loadBuildConfig() with CANON_BUILD_CONFIG_NOT_FOUND — a hint
 * that tells the user to create a config file that already exists, just
 * under the real (correct) project root. That's the opposite failure mode
 * from the C3-completion bug (missing validation vs. wrong base path), and
 * getProjectRoot() is the single fix for both: it resolves from the
 * workspace root (SDLAB_ROOT env / walk-up-for-projects/ / module root),
 * never from cwd, so both the "not found" case AND the "wrong cwd" case now
 * produce the SAME accurate INPUT_UNKNOWN_PROJECT diagnosis every other
 * command uses.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..', '..');
const BIN = join(REPO_ROOT, 'bin', 'sdlab.js');

const MISSING_PROJECT = '__sdl_h12_no_such_project__';

const CASES = [
  { name: 'canon-build.js', mod: '../../scripts/canon-build.js', argv: ['--project', MISSING_PROJECT] },
  { name: 'canon-freeze.js', mod: '../../scripts/canon-freeze.js', argv: ['some-entity', '--project', MISSING_PROJECT, '--reason', 'test'] },
  { name: 'canon-unfreeze.js', mod: '../../scripts/canon-unfreeze.js', argv: ['some-entity', '--project', MISSING_PROJECT, '--reason', 'test'] },
  { name: 'canon-freeze-status.js', mod: '../../scripts/canon-freeze-status.js', argv: ['some-entity', '--project', MISSING_PROJECT] },
  { name: 'canon-drift.js', mod: '../../scripts/canon-drift.js', argv: ['--project', MISSING_PROJECT] },
];

test('canon scripts: a nonexistent project is diagnosed as INPUT_UNKNOWN_PROJECT, not CANON_BUILD_CONFIG_NOT_FOUND', async (t) => {
  for (const { name, mod, argv } of CASES) {
    await t.test(name, async () => {
      const { run } = await import(mod);
      await assert.rejects(
        () => run(argv),
        (err) => {
          assert.equal(err.code, 'INPUT_UNKNOWN_PROJECT', `${name}: expected INPUT_UNKNOWN_PROJECT, got ${err.code} (${err.message})`);
          return true;
        }
      );
    });
  }
});

test('canon drift: resolves the REAL star-freight project when invoked from a cwd with no projects/ in its ancestry (SDL-H12 positive case)', () => {
  const dir = mkdtempSync(join(tmpdir(), 'sdlab-h12-cwd-'));
  try {
    const res = spawnSync(process.execPath, [BIN, 'canon', 'drift', '--project', 'star-freight', '--json'], {
      encoding: 'utf-8',
      cwd: dir, // NOT the repo — old process.cwd()-based resolution would look for <dir>/projects/star-freight
      env: { ...process.env, SDLAB_QUIET_FALLBACK: '1' },
    });
    assert.equal(res.status, 0, `expected exit 0, got ${res.status}\nstdout: ${res.stdout}\nstderr: ${res.stderr}`);
    const report = JSON.parse(res.stdout);
    assert.equal(report.project_id, 'star-freight');
    assert.ok(report.entities_total > 0, 'expected a real drift report with entities, not an empty/wrong-project result');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
