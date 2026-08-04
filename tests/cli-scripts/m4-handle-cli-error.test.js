/**
 * M4: brief-compile.js, brief-show.js, painterly-test.js, workflow-list.js,
 * workflow-show.js each hand-rolled their own direct-execution-guard catch
 * (`run().catch(err => { console.error(err.message); process.exit(1); })`)
 * instead of the standard `run().catch(handleCliError)` every other script
 * in scripts/** uses. That hand-rolled catch drops the error's structured
 * code prefix, drops the hint entirely, and always exits 1 even for a
 * runtimeError that should exit 2.
 *
 * This bug is invisible when the CLI is invoked through `sdlab <cmd>` —
 * bin/sdlab.js's dispatcher imports each script's run() and awaits it
 * directly (never through the module's own bottom-of-file guard, since
 * `process.argv[1]` is bin/sdlab.js in that path, not the script file), so
 * bin/sdlab.js's own `main().catch(handleCliError)` was always the real
 * handler there. The bug only manifests when a script is invoked directly —
 * `node scripts/<name>.js ...` — exactly as every one of these files' own
 * usage docstring documents as a supported invocation (e.g. painterly-test.js:
 * "node scripts/painterly-test.js"). This test drives that direct path.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCRIPTS_DIR = join(__dirname, '..', '..', 'scripts');

function runScriptDirect(scriptName, args) {
  const res = spawnSync(process.execPath, [join(SCRIPTS_DIR, scriptName), ...args], {
    encoding: 'utf-8',
    env: { ...process.env, SDLAB_QUIET_FALLBACK: '1' },
  });
  return { stdout: res.stdout || '', stderr: res.stderr || '', status: res.status };
}

const MISSING_PROJECT = '__m4_no_such_project__';

// Each case is crafted to reach getProjectRoot(MISSING_PROJECT) — which
// throws INPUT_UNKNOWN_PROJECT (inputError, exitCode 1, WITH a hint) — as
// the first thing that can fail, so every case exercises the identical
// error path regardless of the script's own business logic.
const CASES = [
  { name: 'brief-compile.js', args: ['--workflow', 'x', '--project', MISSING_PROJECT] },
  { name: 'brief-show.js', args: ['some-brief-id', '--project', MISSING_PROJECT] },
  { name: 'painterly-test.js', args: ['--project', MISSING_PROJECT] },
  { name: 'workflow-list.js', args: ['--project', MISSING_PROJECT] },
  { name: 'workflow-show.js', args: ['some-workflow-id', '--project', MISSING_PROJECT] },
];

test('M4: scripts run directly (node scripts/X.js) route errors through handleCliError — structured code + hint, not a bare message', () => {
  for (const { name, args } of CASES) {
    const { stdout, stderr, status } = runScriptDirect(name, args);
    assert.match(
      stderr,
      /Error \[INPUT_UNKNOWN_PROJECT\]:/,
      `${name}: expected handleCliError's structured "Error [CODE]:" prefix in stderr.\nstdout: ${stdout}\nstderr: ${stderr}`
    );
    assert.match(
      stderr,
      /Hint:/,
      `${name}: expected a "Hint:" line in stderr (handleCliError prints one whenever the error carries a hint, and INPUT_UNKNOWN_PROJECT always does).\nstderr: ${stderr}`
    );
    assert.equal(status, 1, `${name}: INPUT_UNKNOWN_PROJECT is a user error (exitCode 1)`);
  }
});
