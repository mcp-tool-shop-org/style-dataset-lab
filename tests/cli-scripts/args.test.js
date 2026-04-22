import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseArgs, parseNumberFlag, takeFlagValue, sliceAfterSubcommand } from '../../lib/args.js';

test('parseArgs handles kebab-case flags and maps to camelCase', () => {
  const { flags } = parseArgs(['--dry-run', '--max-count', '5'], {
    flags: {
      'dry-run': { type: 'boolean' },
      'max-count': { type: 'string' },
    },
  });
  assert.equal(flags['dry-run'], true);
  assert.equal(flags['max-count'], '5');
});

test('parseArgs resolves short aliases (flag-style --alias) via prebuilt index', () => {
  const { flags } = parseArgs(['--p', 'my-proj'], {
    flags: { project: { type: 'string', alias: 'p' } },
  });
  assert.equal(flags.project, 'my-proj');
});

test('parseArgs rejects unknown flags when allowUnknown is false', () => {
  assert.throws(
    () => parseArgs(['--bogus-flag'], { flags: { project: { type: 'string' } } }),
    (err) => err.code === 'UNKNOWN_FLAG'
  );
});

test('parseArgs accepts unknown flags when allowUnknown=true', () => {
  const { flags } = parseArgs(['--passthrough', 'ok'], {
    flags: { project: { type: 'string' } },
    allowUnknown: true,
  });
  assert.equal(flags.passthrough, 'ok');
});

test('parseArgs throws on duplicate alias definitions', () => {
  assert.throws(
    () =>
      parseArgs([], {
        flags: {
          project: { type: 'string', alias: 'p' },
          pack: { type: 'string', alias: 'p' },
        },
      }),
    (err) => err.code === 'INPUT_DUPLICATE_ALIAS'
  );
});

test('parseNumberFlag rejects NaN', () => {
  assert.throws(
    () => parseNumberFlag('limit', 'abc', { int: true }),
    (err) => err.code === 'INPUT_BAD_NUMBER'
  );
});

test('parseNumberFlag enforces min/max', () => {
  assert.throws(
    () => parseNumberFlag('weight', '2.5', { max: 1 }),
    (err) => err.code === 'INPUT_OUT_OF_RANGE'
  );
  assert.equal(parseNumberFlag('seeds', '3', { int: true, min: 1 }), 3);
});

test('takeFlagValue refuses a flag-like token', () => {
  assert.throws(
    () => takeFlagValue(['--source', '--manifest', 'tm-1'], 'source'),
    (err) => err.code === 'INPUT_MISSING_VALUE'
  );
});

test('sliceAfterSubcommand slices by first occurrence', () => {
  const argv = ['show', 'show', '--project', 'x'];
  assert.deepEqual(sliceAfterSubcommand(argv, 'show'), ['show', '--project', 'x']);
});

test('parseArgs collects positionals separately from flag values', () => {
  const { positionals, flags } = parseArgs(['show', 'snap-001', '--project', 'x'], {
    flags: { project: { type: 'string' } },
  });
  assert.deepEqual(positionals, ['show', 'snap-001']);
  assert.equal(flags.project, 'x');
});
