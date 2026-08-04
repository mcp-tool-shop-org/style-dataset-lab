/**
 * SDL-M6: `sdlab init` scaffolded inbox/generated/ + six outputs/ subdirs with
 * no .gitignore. The generate -> curate -> reingest loop fills those with
 * PNGs (lib/reingest-selected.js copies images into inbox/generated), and the
 * repo-root .gitignore that masks this in local dev is not in the npm
 * `files` allow-list — it never ships to an installed user. Measured cost in
 * this repo: 55 MB of untracked, unignored PNGs staged for commit. Every
 * downstream `sdlab init` user reproduced it by construction.
 *
 * Fix: init now writes a per-project .gitignore covering the regenerable
 * paths, unless one already exists.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { run as initRun } from '../../scripts/init.js';
import { REPO_ROOT } from '../../lib/paths.js';

const PROJECTS_DIR = join(REPO_ROOT, 'projects');

test('init: scaffolds a .gitignore covering inbox/outputs/exports/snapshots/splits/canon-build', async () => {
  const name = 'sdl-init-gitignore-test';
  const projectDir = join(PROJECTS_DIR, name);
  assert.equal(existsSync(projectDir), false, 'fixture project must not already exist');
  try {
    await initRun([name, '--domain', 'generic']);

    const gitignorePath = join(projectDir, '.gitignore');
    assert.ok(existsSync(gitignorePath), '.gitignore was not created by sdlab init');

    const content = readFileSync(gitignorePath, 'utf-8');
    for (const expected of [
      'inbox/**/*.png',
      'inbox/**/*.jpg',
      'inbox/**/*.jpeg',
      'inbox/**/*.webp',
      'outputs/**',
      'exports/',
      'snapshots/',
      'splits/',
      'canon-build/*/',
    ]) {
      assert.ok(content.includes(expected), `.gitignore missing expected pattern: ${expected}\n\nfull content:\n${content}`);
    }
  } finally {
    rmSync(projectDir, { recursive: true, force: true });
  }
});
