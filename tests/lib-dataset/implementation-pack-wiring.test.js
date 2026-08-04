/**
 * SDL-M10 wiring sanity for lib/implementation-packs.js.
 *
 * This module had zero prior test coverage — buildImplementationPack was
 * never exercised by any existing test. Confirms the atomic-claim refactor
 * (claimIdDir, shared with the other six SDL-M10 call sites) didn't break
 * the happy path, and that two back-to-back builds never collide.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  buildImplementationPack,
  loadImplementationPack,
  listImplementationPacks,
} from '../../lib/implementation-packs.js';
import { createTrainingPackageProject } from './fixtures/make-training-package-project.js';

test('SDL-M10: buildImplementationPack works end-to-end after the atomic-claim refactor', async () => {
  const proj = await createTrainingPackageProject({ count: 4 });
  try {
    const result = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    assert.ok(result.implId);
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'implementations', result.implId, 'manifest.json')));

    const manifest = await loadImplementationPack(proj.projectRoot, result.implId);
    assert.equal(manifest.implementation_pack_id, result.implId);
    assert.equal(manifest.training_manifest_id, proj.manifestId);

    const list = await listImplementationPacks(proj.projectRoot);
    assert.ok(list.some(p => p.id === result.implId));
  } finally {
    proj.cleanup();
  }
});

test('SDL-M10: two back-to-back buildImplementationPack calls never collide (atomic claim wiring)', async () => {
  const proj = await createTrainingPackageProject({ count: 3 });
  try {
    const a = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    const b = await buildImplementationPack(proj.projectRoot, proj.manifestId);
    assert.notEqual(a.implId, b.implId);
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'implementations', a.implId, 'manifest.json')));
    assert.ok(existsSync(join(proj.projectRoot, 'training', 'implementations', b.implId, 'manifest.json')));
  } finally {
    proj.cleanup();
  }
});
