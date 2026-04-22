import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setLogLevel, log, info, result, success, verbose, warn } from '../../lib/log.js';

function capture(fn) {
  const origLog = console.log;
  const origErr = console.error;
  const out = [];
  const err = [];
  console.log = (...a) => out.push(a.join(' '));
  console.error = (...a) => err.push(a.join(' '));
  try { fn(); } finally {
    console.log = origLog;
    console.error = origErr;
  }
  return { out, err };
}

test('info respects --quiet (suppressed)', () => {
  setLogLevel('quiet');
  const { out } = capture(() => info('hidden message'));
  assert.equal(out.length, 0);
  setLogLevel('normal');
});

test('result() always prints — survives --quiet', () => {
  setLogLevel('quiet');
  const { out } = capture(() => result('final-path.png'));
  assert.equal(out.length, 1);
  assert.match(out[0], /final-path\.png/);
  setLogLevel('normal');
});

test('success() always prints', () => {
  setLogLevel('quiet');
  const { out } = capture(() => success('done'));
  assert.equal(out.length, 1);
  setLogLevel('normal');
});

test('context prefix applied when first arg is a short identifier + second arg exists', () => {
  setLogLevel('normal');
  const { out } = capture(() => info('generate', 'starting wave 1'));
  assert.equal(out.length, 1);
  assert.equal(out[0], '[generate] starting wave 1');
});

test('no context prefix for single-argument calls', () => {
  setLogLevel('normal');
  const { out } = capture(() => info('starting wave 1'));
  assert.equal(out.length, 1);
  assert.equal(out[0], 'starting wave 1');
});

test('no context prefix when first arg contains whitespace', () => {
  setLogLevel('normal');
  const { out } = capture(() => info('two words', 'more text'));
  assert.equal(out.length, 1);
  // First arg has a space so it is a message, not a context label.
  assert.equal(out[0], 'two words more text');
});

test('no context prefix for non-string first arg', () => {
  setLogLevel('normal');
  const { out } = capture(() => info(42, 'something'));
  assert.equal(out.length, 1);
  assert.equal(out[0], '42 something');
});

test('verbose respects level', () => {
  setLogLevel('normal');
  let { out } = capture(() => verbose('details'));
  assert.equal(out.length, 0);
  setLogLevel('verbose');
  ({ out } = capture(() => verbose('details')));
  assert.equal(out.length, 1);
  setLogLevel('normal');
});
