/**
 * Package root vs workspace root — the distinction that in-repo tests cannot see.
 *
 * There are two roots, and collapsing them into one is a shipping bug:
 *
 *   - workspace root — where the user's `projects/` live (cwd-relative)
 *   - package root   — where `templates/` and `runtime/` live (module-relative,
 *                      shipped inside the npm tarball)
 *
 * In a repo checkout the two are the same directory, so every in-repo test
 * passes either way. The failure only appears in an installed package, where
 * the workspace is the user's cwd and the assets are in node_modules.
 *
 * Measured before this guard existed, in a clean-room tarball install:
 *   $ sdlab init demo --domain character-design
 *   Error [INPUT_UNKNOWN_DOMAIN]: Domain "character-design" not found.
 *   Hint: Available: generic,
 * The five domain packs were in the package the whole time; `init` was looking
 * for them in the user's empty cwd.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';

import {
  getPackageRoot,
  getRuntimeDir,
  getWorkspaceRoot,
  resetWorkspaceRootCache,
  resolveWorkspaceRootFrom,
} from '../../lib/paths.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const ACTUAL_PACKAGE_ROOT = resolve(join(HERE, '..', '..'));

/**
 * Run `fn` with the workspace root forced somewhere OTHER than the package
 * root, then restore. Without this the whole file is untestable: in a repo
 * checkout the two roots are the same directory, so a package-relative and a
 * workspace-relative implementation return identical strings and no assertion
 * can tell them apart. (The first version of this file made exactly that
 * mistake — it stayed green against the reverted, buggy implementation.)
 */
function withForeignWorkspaceRoot(fn) {
  const tmp = mkdtempSync(join(tmpdir(), 'sdlab-ws-'));
  mkdirSync(join(tmp, 'projects'), { recursive: true });
  const prev = process.env.SDLAB_ROOT;
  process.env.SDLAB_ROOT = tmp;
  resetWorkspaceRootCache();
  try {
    return fn(resolve(tmp));
  } finally {
    if (prev === undefined) delete process.env.SDLAB_ROOT;
    else process.env.SDLAB_ROOT = prev;
    resetWorkspaceRootCache();
    rmSync(tmp, { recursive: true, force: true });
  }
}

test('getPackageRoot() resolves to the module’s own install directory', () => {
  assert.equal(getPackageRoot(), ACTUAL_PACKAGE_ROOT);
});

test('getPackageRoot() ignores SDLAB_ROOT and cwd — it is not the workspace root', () => {
  // The workspace resolver honours SDLAB_ROOT; the package root must not.
  // This is the exact confusion that broke `init` for installed users.
  const elsewhere = resolve(join(ACTUAL_PACKAGE_ROOT, '..'));
  const workspace = resolveWorkspaceRootFrom(elsewhere, {
    env: { SDLAB_ROOT: elsewhere },
    moduleRoot: ACTUAL_PACKAGE_ROOT,
  });

  assert.equal(workspace, elsewhere, 'workspace root should follow SDLAB_ROOT');
  assert.equal(
    getPackageRoot(),
    ACTUAL_PACKAGE_ROOT,
    'package root must stay pinned to the install directory regardless of SDLAB_ROOT',
  );
  assert.notEqual(
    getPackageRoot(),
    workspace,
    'the two roots must be independently resolvable — collapsing them is the bug',
  );
});

test('shipped assets resolve against the package root, and are actually there', () => {
  // templates/ and runtime/ are both in package.json "files" — they ship.
  // If either of these resolves workspace-relative, an installed user gets
  // an empty domain list / empty workflow-template list.
  const templates = join(getPackageRoot(), 'templates');
  assert.ok(existsSync(templates), 'templates/ must resolve under the package root');
  assert.ok(
    existsSync(join(templates, 'domains')),
    'templates/domains/ holds the five domain starter packs init depends on',
  );

  assert.equal(getRuntimeDir(), join(getPackageRoot(), 'runtime'));
  assert.ok(existsSync(getRuntimeDir()), 'runtime/ must resolve under the package root');
});

test('getRuntimeDir() stays package-relative when the workspace root differs', () => {
  // THE discriminating test. Everything above passes against a
  // workspace-relative implementation too, because in a repo checkout the two
  // roots are the same path. Only by forcing them apart does the difference
  // become observable — which is precisely the installed-package situation.
  withForeignWorkspaceRoot((foreignRoot) => {
    assert.equal(
      getWorkspaceRoot(),
      foreignRoot,
      'precondition: the workspace root really did move',
    );
    assert.notEqual(
      foreignRoot,
      getPackageRoot(),
      'precondition: the two roots are now genuinely different directories',
    );

    assert.equal(
      getRuntimeDir(),
      join(getPackageRoot(), 'runtime'),
      'runtime/ must follow the PACKAGE, not the workspace — a workspace-relative ' +
        'implementation returns <workspace>/runtime here and returns [] from ' +
        'listWorkflowTemplates() for every installed user',
    );
    assert.ok(
      existsSync(getRuntimeDir()),
      'and the directory it points at must actually exist',
    );
  });
});

test('every advertised init domain is present under the package root', () => {
  // `sdlab init --domain <x>` enumerates this directory. The clean-room
  // failure reported "Available: generic," — one entry and a trailing comma —
  // because it was enumerating a directory that did not exist.
  const domainsDir = join(getPackageRoot(), 'templates', 'domains');
  const expected = [
    'game-art',
    'character-design',
    'creature-design',
    'architecture',
    'vehicle-mech',
  ];
  for (const domain of expected) {
    assert.ok(
      existsSync(join(domainsDir, domain)),
      `domain pack "${domain}" must exist under the package root`,
    );
  }
});
