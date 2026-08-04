/**
 * Coordinator addendum (folded into the H4/H5 dispatch, caught by a
 * clean-room walkthrough after commit 27c42c6): `sdlab init`'s "Next steps"
 * block prints workspace-relative paths for the "Edit <file>" lines — correct,
 * since those are opened from wherever the user ran `init`. But the
 * `sdlab generate <pack> --project <name>` line's argument is resolved by
 * scripts/generate.js via resolveSafeProjectPath(GAME_ROOT, packPath), which
 * is relative to the PROJECT root (GAME_ROOT === projects/<name>), not the
 * workspace root. Printing the workspace-relative form there doubles the
 * path (projects/<name>/projects/<name>/...) and generate.js 404s with
 * INPUT_FILE_NOT_FOUND — reproduced live in a clean-room npm install:
 *
 *   $ sdlab init demo --domain character-design
 *     sdlab generate projects/demo/inputs/prompts/example-wave.json --project demo
 *   $ sdlab generate projects/demo/inputs/prompts/example-wave.json --project demo
 *   Error [INPUT_FILE_NOT_FOUND]: File not found:
 *     ...\projects\demo\projects\demo\inputs\prompts\example-wave.json
 *
 * This test does NOT just check the printed line contains the word
 * "generate" — that assertion would pass against the doubled-path bug too.
 * It extracts the pack argument init actually prints and resolves it EXACTLY
 * the way generate.js does (relative to the project root), then asserts a
 * real file exists there.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { REPO_ROOT } from '../../lib/paths.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, '..', '..', 'bin', 'sdlab.js');
const PROJECTS_DIR = join(REPO_ROOT, 'projects');

function runInit(args) {
  const res = spawnSync(process.execPath, [BIN, 'init', ...args], {
    encoding: 'utf-8',
    cwd: REPO_ROOT,
    env: { ...process.env, SDLAB_QUIET_FALLBACK: '1' },
  });
  return { stdout: res.stdout || '', stderr: res.stderr || '', status: res.status };
}

test('init: the printed "sdlab generate <pack>" line resolves to a real file under the scaffolded project (not doubled)', () => {
  const name = 'sdl-init-genline-test';
  const projectDir = join(PROJECTS_DIR, name);
  assert.equal(existsSync(projectDir), false, 'fixture project must not already exist');
  try {
    const { stdout, status } = runInit([name, '--domain', 'character-design']);
    assert.equal(status, 0, `init exited ${status}\nstdout: ${stdout}`);

    const genLineMatch = stdout.match(/^\s*(sdlab generate \S+ --project \S+)\s*$/m);
    assert.ok(genLineMatch, `expected a "sdlab generate <pack> --project <name>" line in init's output:\n${stdout}`);
    const genLine = genLineMatch[1];

    const packMatch = genLine.match(/^sdlab generate (\S+) --project/);
    assert.ok(packMatch, `could not extract the pack path argument from: "${genLine}"`);
    const packArg = packMatch[1];

    // Resolve EXACTLY the way scripts/generate.js's
    // resolveSafeProjectPath(GAME_ROOT, packPath) does: relative to the
    // PROJECT root, not the workspace root init itself ran from. A test
    // that only checked the line contains "generate" (it does, even when
    // broken) would not catch a doubled path — this checks the path the
    // line actually names resolves to a real file.
    const resolvedPath = join(projectDir, packArg);
    assert.ok(
      existsSync(resolvedPath),
      `init printed "${genLine}" but "${packArg}" does not resolve under the project root ` +
      `(resolved: ${resolvedPath}). Running that exact command would 404 with INPUT_FILE_NOT_FOUND ` +
      `— this is the doubled-path regression from 27c42c6.`
    );

    // Confirm it is genuinely NOT the doubled form (belt-and-suspenders —
    // the existsSync check above is the real proof, this documents intent).
    assert.ok(!packArg.startsWith('projects/'), `pack arg "${packArg}" looks workspace-relative, not project-relative`);
  } finally {
    rmSync(projectDir, { recursive: true, force: true });
  }
});
