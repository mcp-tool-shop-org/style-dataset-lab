/**
 * SDL-M12: scripts/bulk-curate-waves11-18.js matched records on a broad
 * generic prefix regex (env_, veh_, prop_, arch_, int_, ...) and wrote a
 * FABRICATED judgment block — canned explanation, criteria_scores keyed only
 * by prefix, reviewer "bulk_curate_v2", confidence 0.75-0.95 — asserting
 * nothing about which project or asset it actually applied to. Recording a
 * curation rationale unrelated to the asset it's stamped on is a Law 2
 * violation ("inclusion is explainable"). Its two siblings
 * (bulk-curate-wave2-5.js, curate-wave25.js) did the same thing for earlier
 * waves. All three were one-off historical scripts, already excluded from
 * the npm package (package.json `files`: "!scripts/bulk-curate-*.js",
 * "!scripts/curate-wave*.js") and never wired into bin/sdlab.js's COMMANDS
 * table — so deletion has zero surface area. This test guards against them
 * reappearing.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..', '..');
const SCRIPTS_DIR = join(REPO_ROOT, 'scripts');

const REMOVED = [
  'bulk-curate-wave2-5.js',
  'bulk-curate-waves11-18.js',
  'curate-wave25.js',
];

test('the three fabricated-judgment bulk-curate scripts no longer exist', () => {
  for (const file of REMOVED) {
    assert.equal(existsSync(join(SCRIPTS_DIR, file)), false, `${file} should have been deleted (SDL-M12)`);
  }
});

test('bin/sdlab.js does not register any of the removed scripts as a command', () => {
  const dispatcherSrc = readFileSync(join(REPO_ROOT, 'bin', 'sdlab.js'), 'utf-8');
  for (const file of REMOVED) {
    assert.doesNotMatch(dispatcherSrc, new RegExp(file.replace('.', '\\.')), `bin/sdlab.js still references ${file}`);
  }
});
