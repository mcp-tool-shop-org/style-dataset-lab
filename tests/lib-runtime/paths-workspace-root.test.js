/**
 * Unit tests for SDL-C1 (workspace-root resolution) and SDL-C3
 * (project-name traversal guard) in lib/paths.js.
 *
 * SDL-C1: REPO_ROOT used to be `join(__dirname, '..')` — always this
 * module's own location. For an npm-installed consumer that resolves to
 * node_modules/@mcptoolshop/style-dataset-lab, so `sdlab init demo` wrote
 * the user's project tree into node_modules — gone on the next `npm ci`.
 * These tests drive resolveWorkspaceRootFrom's four branches directly
 * (rather than mutating the real process.cwd()/env, which are shared
 * global state unsafe to touch in a concurrently-run suite) and reproduce
 * the exact bug shape: a module root sitting inside node_modules with a
 * leftover projects/ dir from a prior buggy run.
 *
 * SDL-C3: getProjectRoot(name) used to join name into a path with only an
 * existsSync check — `--project "../../ai-eyes-mcp"` escaped the sandbox
 * entirely (demonstrated live against a real sibling repo).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import {
  resolveWorkspaceRootFrom,
  getWorkspaceRoot,
  resetWorkspaceRootCache,
  REPO_ROOT,
  getProjectRoot,
} from '../../lib/paths.js';

async function makeSandbox(prefix) {
  return await mkdtemp(join(tmpdir(), prefix));
}

// ─── SDL-C1: workspace root resolution ────────────────────────────

test('resolveWorkspaceRootFrom: SDLAB_ROOT env wins when set and exists', async () => {
  const root = await makeSandbox('sdl-wsroot-env-');
  const cwd = await makeSandbox('sdl-wsroot-envcwd-'); // unrelated, no projects/
  try {
    const resolved = resolveWorkspaceRootFrom(cwd, { env: { SDLAB_ROOT: root }, moduleRoot: cwd });
    assert.equal(resolved, resolve(root));
  } finally {
    await rm(root, { recursive: true, force: true });
    await rm(cwd, { recursive: true, force: true });
  }
});

test('resolveWorkspaceRootFrom: SDLAB_ROOT is ignored when it does not exist on disk', async () => {
  const cwd = await makeSandbox('sdl-wsroot-cwd-');
  const moduleRoot = await makeSandbox('sdl-wsroot-cwdmod-'); // deliberately NOT cwd, and has no projects/
  try {
    const bogusRoot = join(cwd, 'does-not-exist-anywhere');
    // Neither cwd nor moduleRoot has projects/, so this falls all the way
    // through to step 4: cwd itself — NOT moduleRoot, and NOT the bogus
    // SDLAB_ROOT path (which must never be returned since it doesn't exist).
    const resolved = resolveWorkspaceRootFrom(cwd, { env: { SDLAB_ROOT: bogusRoot }, moduleRoot });
    assert.equal(resolved, resolve(cwd));
    assert.notEqual(resolved, resolve(moduleRoot));
  } finally {
    await rm(cwd, { recursive: true, force: true });
    await rm(moduleRoot, { recursive: true, force: true });
  }
});

test('resolveWorkspaceRootFrom: walks up from a nested cwd to find an ancestor with projects/', async () => {
  const root = await makeSandbox('sdl-wsroot-walk-');
  try {
    await mkdir(join(root, 'projects'), { recursive: true });
    const nested = join(root, 'a', 'b', 'c');
    await mkdir(nested, { recursive: true });
    const resolved = resolveWorkspaceRootFrom(nested, { env: {}, moduleRoot: nested });
    assert.equal(resolved, resolve(root));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('resolveWorkspaceRootFrom: falls back to moduleRoot when cwd-walk finds nothing but moduleRoot has projects/', async () => {
  const cwd = await makeSandbox('sdl-wsroot-cwd2-');
  const moduleRoot = await makeSandbox('sdl-wsroot-mod-');
  try {
    await mkdir(join(moduleRoot, 'projects'), { recursive: true });
    const resolved = resolveWorkspaceRootFrom(cwd, { env: {}, moduleRoot });
    assert.equal(resolved, resolve(moduleRoot));
  } finally {
    await rm(cwd, { recursive: true, force: true });
    await rm(moduleRoot, { recursive: true, force: true });
  }
});

test('resolveWorkspaceRootFrom: falls back to cwd itself when nothing else matches (fresh workspace)', async () => {
  const cwd = await makeSandbox('sdl-wsroot-fresh-');
  const moduleRoot = await makeSandbox('sdl-wsroot-modempty-'); // also has no projects/
  try {
    const resolved = resolveWorkspaceRootFrom(cwd, { env: {}, moduleRoot });
    assert.equal(resolved, resolve(cwd));
  } finally {
    await rm(cwd, { recursive: true, force: true });
    await rm(moduleRoot, { recursive: true, force: true });
  }
});

test('resolveWorkspaceRootFrom: refuses a module root buried in node_modules — the exact npm-install bug shape (SDL-C1)', async () => {
  // Reproduces the reported defect. A clean npm install puts this package
  // at .../node_modules/@mcptoolshop/style-dataset-lab. A prior buggy
  // `sdlab init demo` run (old REPO_ROOT = join(__dirname,'..'),
  // unconditional) would have created
  // .../node_modules/@mcptoolshop/style-dataset-lab/projects/demo — so on
  // a later run, step 3 (module root has projects/) would otherwise
  // silently "win" and hand back a path inside node_modules. The user's
  // own cwd is unrelated and has no projects/ anywhere up its chain.
  const fakeInstall = await makeSandbox('sdl-wsroot-nm-');
  const cwd = await makeSandbox('sdl-wsroot-nmcwd-');
  try {
    const moduleRoot = join(fakeInstall, 'node_modules', '@mcptoolshop', 'style-dataset-lab');
    await mkdir(join(moduleRoot, 'projects', 'demo'), { recursive: true });

    assert.throws(
      () => resolveWorkspaceRootFrom(cwd, { env: {}, moduleRoot }),
      (err) => err.code === 'INPUT_ROOT_IN_NODE_MODULES'
    );
  } finally {
    await rm(fakeInstall, { recursive: true, force: true });
    await rm(cwd, { recursive: true, force: true });
  }
});

test('resolveWorkspaceRootFrom: refuses SDLAB_ROOT itself when it points inside node_modules', async () => {
  const fakeInstall = await makeSandbox('sdl-wsroot-nm2-');
  const cwd = await makeSandbox('sdl-wsroot-nm2cwd-');
  try {
    const badRoot = join(fakeInstall, 'node_modules', 'somepkg');
    await mkdir(badRoot, { recursive: true });
    assert.throws(
      () => resolveWorkspaceRootFrom(cwd, { env: { SDLAB_ROOT: badRoot }, moduleRoot: cwd }),
      (err) => err.code === 'INPUT_ROOT_IN_NODE_MODULES'
    );
  } finally {
    await rm(fakeInstall, { recursive: true, force: true });
    await rm(cwd, { recursive: true, force: true });
  }
});

test('getWorkspaceRoot memoizes across calls; resetWorkspaceRootCache lets it pick up a new SDLAB_ROOT', async () => {
  const before = getWorkspaceRoot();
  assert.equal(getWorkspaceRoot(), before, 'memoized: repeated calls return the identical cached value');
  assert.equal(before, REPO_ROOT, 'REPO_ROOT should match the initial resolution');

  const altRoot = await makeSandbox('sdl-wsroot-alt-');
  const savedEnv = process.env.SDLAB_ROOT;
  try {
    process.env.SDLAB_ROOT = altRoot;
    // Without a reset, the memoized value must NOT change — proves it is
    // really cached, not re-walked on every call.
    assert.equal(getWorkspaceRoot(), before);

    resetWorkspaceRootCache();
    const afterReset = getWorkspaceRoot();
    assert.equal(afterReset, resolve(altRoot), 'expected the reset call to pick up the new SDLAB_ROOT');
    assert.notEqual(afterReset, before);
  } finally {
    if (savedEnv === undefined) delete process.env.SDLAB_ROOT;
    else process.env.SDLAB_ROOT = savedEnv;
    resetWorkspaceRootCache(); // restore real resolution for the rest of this process
    await rm(altRoot, { recursive: true, force: true });
  }
});

// ─── SDL-C3: project name traversal guard ─────────────────────────

test('getProjectRoot rejects the demonstrated live exploit payload', () => {
  assert.throws(
    () => getProjectRoot('../../ai-eyes-mcp'),
    (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME' && err.message.includes('../../ai-eyes-mcp')
  );
});

test('getProjectRoot rejects a name containing a forward slash even when it would not escape the projects dir', () => {
  assert.throws(
    () => getProjectRoot('foo/bar'),
    (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME'
  );
});

test('getProjectRoot rejects a name containing a backslash', () => {
  assert.throws(
    () => getProjectRoot('foo\\bar'),
    (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME'
  );
});

test('getProjectRoot rejects a bare ".." with no separator', () => {
  assert.throws(
    () => getProjectRoot('..'),
    (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME'
  );
});

test('getProjectRoot still resolves a legitimate existing project (no false positive)', () => {
  const root = getProjectRoot('star-freight');
  assert.ok(root.endsWith(join('projects', 'star-freight')), `expected project path, got: ${root}`);
});
