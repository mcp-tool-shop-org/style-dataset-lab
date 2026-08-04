/**
 * H3: lib/training-packages.js called recordToRow() in a bare loop with no
 * try/catch. recordToRow() can throw CAPTION_SUBJECT_MISSING
 * (lib/captions.js's buildSubjectNaturalLanguageCaption, added in Stage A —
 * see tests/lib-canon/captions-subject-natural-language.test.js for that
 * throw's own unit coverage) once per record. The throw itself is correct;
 * the granularity at THIS layer was not: the bare loop meant the FIRST
 * offending record aborted the whole build — before claimIdDir (snapshot.js)
 * ever reserved a package id — naming exactly one offender. A 400-record
 * build with several bad records died having written nothing, and had to be
 * rerun once per offender to discover the next one.
 *
 * lib/canon-build/build.js already solves exactly this for
 * contextLimitFailures: collect failures across the WHOLE loop, throw ONE
 * summary error naming every offender. This ports that pattern.
 *
 * Fixture note: makeRecord() (tests/lib-dataset/fixtures/make-project.js)
 * never populates canon.subject, so under caption_strategy
 * 'subject-natural-language' every record in this fixture fails to caption
 * — which is exactly what's needed to prove the aggregation collects ALL
 * offenders, not just the first.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { buildTrainingPackage } from '../../lib/training-packages.js';
import { createTrainingPackageProject } from '../lib-dataset/fixtures/make-training-package-project.js';

async function useSubjectNaturalLanguageProfile(proj) {
  const profilePath = join(proj.projectRoot, 'training', 'profiles', `${proj.profileId}.json`);
  const profile = JSON.parse(await readFile(profilePath, 'utf-8'));
  profile.caption_strategy = 'subject-natural-language';
  await writeFile(profilePath, JSON.stringify(profile, null, 2));
}

/** Assert no directory under `parentDir` contains a manifest.json — i.e. an aborted build left no usable artifact behind (mirrors F3's assertNoManifestUnder). */
async function assertNoManifestUnder(parentDir) {
  if (!existsSync(parentDir)) return;
  for (const d of await readdir(parentDir)) {
    assert.ok(
      !existsSync(join(parentDir, d, 'manifest.json')),
      `aborted build must not leave a usable manifest.json in ${join(parentDir, d)}`
    );
  }
}

test('H3: buildTrainingPackage aggregates ALL caption failures into one TRAINING_PACKAGE_CAPTION_FAILURES error, not just the first', async () => {
  const proj = await createTrainingPackageProject({ count: 4 });
  try {
    await useSubjectNaturalLanguageProfile(proj);

    await assert.rejects(
      () => buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true }),
      (err) => {
        assert.equal(err.code, 'TRAINING_PACKAGE_CAPTION_FAILURES');
        // ALL FOUR offenders must be named — not just pkgtest_0, the one a
        // bare-loop-with-no-try/catch would have died on first.
        for (let i = 0; i < 4; i++) {
          assert.match(
            err.message,
            new RegExp(`pkgtest_${i}\\b`),
            `expected offender "pkgtest_${i}" to be named in the aggregated error:\n${err.message}`
          );
        }
        return true;
      }
    );

    // F3 precedent: a hard-fail here must not have reserved a package id or
    // written a partial artifact — checked before claimIdDir runs.
    await assertNoManifestUnder(join(proj.projectRoot, 'training', 'packages'));
  } finally {
    proj.cleanup();
  }
});

test('H3: buildTrainingPackage still succeeds normally when captions build cleanly — explicit PASS branch for contrast', async () => {
  const proj = await createTrainingPackageProject({ count: 3 });
  try {
    // Fixture default profile uses caption_strategy 'filename' (falls
    // through to buildLegacyCaption, which never throws) — unaffected
    // control case, confirming the fix didn't break the happy path.
    const result = await buildTrainingPackage(proj.projectRoot, proj.manifestId, { copy: true });
    assert.equal(result.records, 3);
  } finally {
    proj.cleanup();
  }
});
