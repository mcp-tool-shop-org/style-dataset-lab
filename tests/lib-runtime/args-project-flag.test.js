/**
 * Unit tests for SDL-L1 — getProjectName's value-flag swallow.
 *
 * getProjectName took argv[i+1] as the project name with no
 * startsWith('--') guard, unlike takeFlagValue in the same file.
 * `--project --dry-run` silently yielded the project name "--dry-run"
 * instead of erroring. The fix mirrors takeFlagValue's guard.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getProjectName } from '../../lib/args.js';

test('getProjectName throws INPUT_MISSING_VALUE when --project is immediately followed by another flag (SDL-L1)', () => {
  assert.throws(
    () => getProjectName(['--project', '--dry-run']),
    (err) => err.code === 'INPUT_MISSING_VALUE' && err.message.includes('--dry-run')
  );
});

test('getProjectName throws INPUT_MISSING_VALUE when --project is the last token (no value at all)', () => {
  assert.throws(
    () => getProjectName(['run', '--project']),
    (err) => err.code === 'INPUT_MISSING_VALUE'
  );
});

test('getProjectName throws INPUT_MISSING_VALUE for the deprecated --game alias too', () => {
  assert.throws(
    () => getProjectName(['--game', '--verbose']),
    (err) => err.code === 'INPUT_MISSING_VALUE' && err.message.includes('--verbose')
  );
});

test('getProjectName still returns a real value when one is given (no false positive)', () => {
  assert.equal(getProjectName(['--project', 'my-project']), 'my-project');
  assert.equal(getProjectName(['--project', 'my-project', '--dry-run']), 'my-project');
});

test('getProjectName still supports the --project=value equals form', () => {
  assert.equal(getProjectName(['--project=my-project']), 'my-project');
});

test('getProjectName still falls back to star-freight when no --project is given at all', () => {
  const savedEnv = process.env.SDLAB_QUIET_FALLBACK;
  try {
    process.env.SDLAB_QUIET_FALLBACK = '1';
    assert.equal(getProjectName(['--dry-run']), 'star-freight');
  } finally {
    if (savedEnv === undefined) delete process.env.SDLAB_QUIET_FALLBACK;
    else process.env.SDLAB_QUIET_FALLBACK = savedEnv;
  }
});
