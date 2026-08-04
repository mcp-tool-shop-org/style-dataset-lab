/**
 * Unit tests for B04 in lib/comfyui.js.
 *
 * comfyHealth() collapsed EVERY failure mode into a bare `false` via
 * `catch { return false }` with no bound error. A 503 while a custom node
 * loads, a refused connection, a DNS typo, and a genuine timeout all
 * produced the identical "ComfyUI not reachable — start ComfyUI" message
 * from comfyui-runner.js — factually wrong for the 503 (ComfyUI IS
 * reachable) and useless for the others (starting ComfyUI does not fix a
 * DNS typo).
 *
 * Fix: `comfyHealthDetailed()` surfaces a `reason` (`timeout` / `refused` /
 * `dns` / `http-<status>`) alongside `ok`, so the caller's error message can
 * name the actual cause. `comfyHealth()` itself keeps returning a PLAIN
 * BOOLEAN — unchanged — because 5 scripts (scripts/generate.js,
 * generate-identity.js, generate-controlnet.js, generate-ipadapter.js,
 * painterly.js — none owned by this fix) call `if (!(await comfyHealth(...)))`
 * and are not part of this change; comfyHealthDetailed is an ADDITIVE export,
 * not a signature change.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { comfyHealth, comfyHealthDetailed } from '../../lib/comfyui.js';

function makeHangingFetchStub() {
  return function hangingFetch(_url, init) {
    return new Promise((_resolve, reject) => {
      const signal = init?.signal;
      if (signal) {
        if (signal.aborted) {
          const err = new Error('The operation was aborted.');
          err.name = 'AbortError';
          reject(err);
          return;
        }
        signal.addEventListener('abort', () => {
          const err = new Error('The operation was aborted.');
          err.name = 'AbortError';
          reject(err);
        });
      }
    });
  };
}

function withGuard(promise, ms = 2000, label = 'operation') {
  return Promise.race([
    promise,
    new Promise((_resolve, reject) =>
      setTimeout(() => reject(new Error(`TEST GUARD: ${label} did not settle within ${ms}ms`)), ms)
    ),
  ]);
}

test('comfyHealthDetailed reports reason "timeout" for a hanging server (B04)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeHangingFetchStub();
    const result = await withGuard(comfyHealthDetailed('http://hangs.invalid', { timeoutMs: 100 }), 2000);
    assert.equal(result.ok, false);
    assert.equal(result.reason, 'timeout');
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('comfyHealthDetailed reports reason "refused" for a connection-refused error (B04)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => {
      const err = new TypeError('fetch failed');
      err.cause = { code: 'ECONNREFUSED', errno: -4078 };
      throw err;
    };
    const result = await comfyHealthDetailed('http://127.0.0.1:9999');
    assert.equal(result.ok, false);
    assert.equal(result.reason, 'refused');
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('comfyHealthDetailed reports reason "dns" for an ENOTFOUND error (B04)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => {
      const err = new TypeError('fetch failed');
      err.cause = { code: 'ENOTFOUND', hostname: 'typo-host.invalid' };
      throw err;
    };
    const result = await comfyHealthDetailed('http://typo-host.invalid:8188');
    assert.equal(result.ok, false);
    assert.equal(result.reason, 'dns');
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('comfyHealthDetailed reports reason "http-503" when ComfyUI responds but is not ready — this is the factually-wrong case from the finding (B04)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({ ok: false, status: 503, async text() { return 'loading custom node'; } });
    const result = await comfyHealthDetailed('http://127.0.0.1:8188');
    assert.equal(result.ok, false);
    assert.equal(result.reason, 'http-503');
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('comfyHealthDetailed reports ok:true reason:null when ComfyUI is actually reachable (no false positive)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({ ok: true, status: 200, async text() { return ''; } });
    const result = await comfyHealthDetailed('http://127.0.0.1:8188');
    assert.equal(result.ok, true);
    assert.equal(result.reason, null);
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('comfyHealth() itself remains a PLAIN BOOLEAN for every reason — unchanged contract for existing callers (B04 backward compat)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeHangingFetchStub();
    const timeoutResult = await withGuard(comfyHealth('http://hangs.invalid', { timeoutMs: 100 }), 2000);
    assert.equal(typeof timeoutResult, 'boolean');
    assert.equal(timeoutResult, false);

    globalThis.fetch = async () => ({ ok: false, status: 503, async text() { return ''; } });
    const httpResult = await comfyHealth('http://127.0.0.1:8188');
    assert.equal(typeof httpResult, 'boolean');
    assert.equal(httpResult, false);

    globalThis.fetch = async () => ({ ok: true, status: 200, async text() { return ''; } });
    const okResult = await comfyHealth('http://127.0.0.1:8188');
    assert.equal(typeof okResult, 'boolean');
    assert.equal(okResult, true);
  } finally {
    globalThis.fetch = origFetch;
  }
});
