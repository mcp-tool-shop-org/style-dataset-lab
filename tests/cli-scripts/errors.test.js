import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SdlabError, inputError, runtimeError, handleCliError } from '../../lib/errors.js';

test('inputError has exit code 1', () => {
  const err = inputError('INPUT_MISSING_FLAG', 'msg', 'hint');
  assert.ok(err instanceof SdlabError);
  assert.equal(err.exitCode, 1);
  assert.equal(err.code, 'INPUT_MISSING_FLAG');
  assert.equal(err.message, 'msg');
  assert.equal(err.hint, 'hint');
});

test('runtimeError has exit code 2 and preserves cause', () => {
  const cause = new Error('inner');
  const err = runtimeError('RUNTIME_COMFY_UNREACHABLE', 'msg', null, cause);
  assert.equal(err.exitCode, 2);
  assert.equal(err.cause, cause);
});

test('SdlabError serializes to the expected JSON shape', () => {
  const err = inputError('INPUT_X', 'msg', 'hint');
  const json = err.toJSON();
  assert.deepEqual(json, { code: 'INPUT_X', message: 'msg', hint: 'hint' });
});

test('handleCliError exits 1 for input errors, 2 for runtime', () => {
  const origExit = process.exit;
  const origError = console.error;
  const calls = [];
  console.error = () => {};
  process.exit = (code) => { calls.push(code); throw new Error('exited'); };
  try {
    try { handleCliError(inputError('A', 'b')); } catch {}
    try { handleCliError(runtimeError('R', 'c')); } catch {}
    try { handleCliError(new Error('raw')); } catch {}
    assert.deepEqual(calls, [1, 2, 2]);
  } finally {
    process.exit = origExit;
    console.error = origError;
  }
});

test('handleCliError preserves SdlabError structure on serialization', () => {
  const err = inputError('INPUT_MISSING_FLAG', 'source is required', 'Pass --source <dir>');
  assert.equal(err.name, 'SdlabError');
  assert.equal(err.code, 'INPUT_MISSING_FLAG');
  assert.equal(err.hint, 'Pass --source <dir>');
});
