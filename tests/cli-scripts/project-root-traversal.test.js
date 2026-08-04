/**
 * SDL-C3-completion: lib/paths.js's getProjectRoot() was hardened to reject a
 * --project value containing "/", "\" or ".." — but 27 scripts never called
 * it. Each did its own `join(REPO_ROOT, 'projects', projectName)` (or, for 5
 * canon-*.js scripts, `join(process.cwd(), 'projects', projectName)` — see
 * canon-cwd-independence.test.js for those), bypassing the guard entirely.
 * Reproduced live before the fix:
 *
 *   $ sdlab project doctor --project "../../ai-eyes-mcp"
 *     Path: E:\AI\ai-eyes-mcp
 *     ✓ Project directory exists
 *
 * doctor.js has its own dedicated test file (doctor.test.js) with the exact
 * reproduction above. This file spot-checks the SAME fix (route through
 * getProjectRoot()) across a representative sample spanning every distinct
 * shape the fix took:
 *   - scripts that only needed REPO_ROOT dropped entirely
 *   - scripts that also use resolveSafeProjectPath
 *   - scripts that keep REPO_ROOT for an unrelated baseRoot use (reingest,
 *     eval-run)
 * All 27 fixed files are mechanically identical at the call site
 * (`getProjectRoot(projectName)` replacing a raw join) — this suite proves
 * the pattern actually closes the hole rather than asserting it by
 * inspection.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

const PAYLOADS = ['../../ai-eyes-mcp', '..\\..\\ai-eyes-mcp'];

async function assertRejectsTraversal(t, label, modPath, argvFor) {
  for (const payload of PAYLOADS) {
    await t.test(`${label} — rejects --project "${payload}"`, async () => {
      const mod = await import(modPath);
      await assert.rejects(
        () => mod.run(argvFor(payload)),
        (err) => err.code === 'INPUT_UNSAFE_PROJECT_NAME',
        `${label} did not reject traversal payload "${payload}" with INPUT_UNSAFE_PROJECT_NAME`
      );
    });
  }
}

test('project-root resolution: representative sample of the 27 fixed scripts', async (t) => {
  // Group A — REPO_ROOT dropped entirely, minimal argv.
  await assertRejectsTraversal(t, 'curate.js', '../../scripts/curate.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'snapshot.js', '../../scripts/snapshot.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'eligibility.js', '../../scripts/eligibility.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'card.js', '../../scripts/card.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'split.js', '../../scripts/split.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'canon-bind.js', '../../scripts/canon-bind.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'export.js', '../../scripts/export.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'eval-pack.js', '../../scripts/eval-pack.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'training-manifest.js', '../../scripts/training-manifest.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'training-package.js', '../../scripts/training-package.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'training-profile.js', '../../scripts/training-profile.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'migrate-records.js', '../../scripts/migrate-records.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'compare.js', '../../scripts/compare.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'implementation-pack.js', '../../scripts/implementation-pack.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'painterly-test.js', '../../scripts/painterly-test.js', (p) => ['--project', p]);

  // Group B — resolveSafeProjectPath kept alongside the swap to getProjectRoot.
  await assertRejectsTraversal(t, 'generate.js', '../../scripts/generate.js', (p) => ['--project', p, '--dry-run']);
  await assertRejectsTraversal(t, 'painterly.js', '../../scripts/painterly.js', (p) => ['--project', p, '--dry-run']);
  await assertRejectsTraversal(t, 'generate-identity.js', '../../scripts/generate-identity.js', (p) => ['pack.json', '--project', p, '--dry-run']);
  await assertRejectsTraversal(t, 'generate-controlnet.js', '../../scripts/generate-controlnet.js', (p) => ['--project', p, '--guide', 'x.png', '--dry-run']);
  await assertRejectsTraversal(t, 'generate-ipadapter.js', '../../scripts/generate-ipadapter.js', (p) => ['--project', p, '--ref', 'x.png', '--prompt', 'x', '--dry-run']);

  // Group C — REPO_ROOT kept for an unrelated resolveSafeProjectPath baseRoot,
  // getProjectRoot added alongside it.
  await assertRejectsTraversal(t, 'reingest.js', '../../scripts/reingest.js', (p) => ['--project', p]);
  await assertRejectsTraversal(t, 'eval-run.js', '../../scripts/eval-run.js', (p) => ['--project', p]);
});

test('init.js: already safe by construction — its own isValidName() whitelist runs before any path join, so a traversal payload never reaches the filesystem', async () => {
  // init.js is the one script in the C3-completion list that legitimately
  // can't call getProjectRoot() (the project doesn't exist yet — that's the
  // whole point of `init`). It already had its own guard: isValidName()
  // (scripts/init.js) is a WHITELIST (^[a-z0-9][a-z0-9-]*[a-z0-9]$) checked
  // before the first join(PROJECTS_DIR, projectName) — strictly stricter
  // than getProjectRoot()'s blacklist (rejects only ".." and "/"/"\\"), since
  // it also rejects uppercase, underscores, spaces, etc. This test locks
  // that claim in as a regression guard rather than leaving it as an
  // unverified read of the source.
  const mod = await import('../../scripts/init.js');
  for (const payload of PAYLOADS) {
    await assert.rejects(
      () => mod.run([payload, '--domain', 'generic']),
      (err) => err.code === 'INPUT_BAD_NAME',
      `init.js did not reject traversal payload "${payload}" with INPUT_BAD_NAME`
    );
  }
});

test('project-root resolution: a VALID project name is unaffected (no false positive)', async () => {
  const mod = await import('../../scripts/eligibility.js');
  // A real, existing project must not throw INPUT_UNSAFE_PROJECT_NAME. It may
  // still throw/behave per its normal business logic (missing snapshot, etc.)
  // — this only asserts the traversal guard itself doesn't false-positive on
  // an ordinary name.
  try {
    await mod.run(['--project', 'star-freight']);
  } catch (err) {
    assert.notEqual(err.code, 'INPUT_UNSAFE_PROJECT_NAME', 'a valid project name must not trip the traversal guard');
    assert.notEqual(err.code, 'INPUT_UNKNOWN_PROJECT', 'star-freight exists in this repo and must resolve');
  }
});
