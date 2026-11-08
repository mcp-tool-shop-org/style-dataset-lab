import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, '..', '..', 'bin', 'sdlab.js');

function runCli(args) {
  const res = spawnSync(process.execPath, [BIN, ...args], {
    encoding: 'utf-8',
    env: { ...process.env, SDLAB_QUIET_FALLBACK: '1', CUDA_VISIBLE_DEVICES: '' },
  });
  return { stdout: res.stdout || '', stderr: res.stderr || '', status: res.status };
}

test('sdlab checkpoint-eval --help prints checkpoint evaluation help', () => {
  const { stdout, status } = runCli(['checkpoint-eval', '--help']);
  assert.equal(status, 0);
  assert.match(stdout, /sdlab checkpoint-eval/);
  assert.match(stdout, /--training-dir <dir>/);
  assert.match(stdout, /--device <cpu\|openvino>/);
});

test('root --help lists checkpoint-eval', () => {
  const { stdout, status } = runCli(['--help']);
  assert.equal(status, 0);
  assert.match(stdout, /checkpoint-eval/);
});
