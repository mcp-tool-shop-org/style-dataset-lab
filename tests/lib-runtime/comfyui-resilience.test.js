/**
 * Unit tests for SDL-H8 (per-request fetch timeout) and SDL-L3 (unguarded
 * JSON parse) in lib/comfyui.js.
 *
 * SDL-H8: none of the 5 fetch() calls carried a timeout. A ComfyUI that
 * accepts the TCP connection and never responds hangs `await fetch()`
 * forever — a hang never rejects, so no catch/retry logic downstream ever
 * fires. Every test below races the call against a short LOCAL guard
 * timeout (via Promise.race) rather than letting a truly unfixed call hang
 * the test process forever — that keeps the RED proof safe (fails fast in
 * ~1-2s) instead of hanging the whole suite.
 *
 * SDL-L3: histRes.json() sat outside the retry block that guards fetch
 * failures/non-OK statuses, so a 200-OK non-JSON body threw immediately and
 * permanently failed the run instead of being retried like any other
 * history-endpoint hiccup.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { comfyHealth, submitAndWait, downloadImage, uploadImage } from '../../lib/comfyui.js';

/** A fetch stub that never resolves on its own, but rejects with a real
 * AbortError as soon as the passed-in AbortSignal fires — mirroring real
 * fetch()/undici behavior under an AbortController timeout. */
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
      // Otherwise: never settles — simulates a server that accepted the
      // connection and never responded.
    });
  };
}

/** Races `promise` against a short local guard so an unfixed (truly
 * hanging) implementation fails the test in ~2s instead of hanging the
 * whole suite forever. */
function withGuard(promise, ms = 2000, label = 'operation') {
  return Promise.race([
    promise,
    new Promise((_resolve, reject) =>
      setTimeout(
        () => reject(new Error(`TEST GUARD: ${label} did not settle within ${ms}ms — fetch is not bounded by a per-request timeout`)),
        ms
      )
    ),
  ]);
}

// ─── SDL-H8: per-request timeout ──────────────────────────────────

test('comfyHealth resolves false quickly against a hanging ComfyUI instead of hanging forever (SDL-H8)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeHangingFetchStub();
    const start = Date.now();
    const result = await withGuard(comfyHealth('http://hangs.invalid', { timeoutMs: 100 }), 2000, 'comfyHealth');
    const elapsed = Date.now() - start;
    assert.equal(result, false);
    assert.ok(elapsed < 1500, `expected comfyHealth to settle via its 100ms request timeout, took ${elapsed}ms`);
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('submitAndWait rejects quickly (not hangs) when the initial submit POST never responds (SDL-H8)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeHangingFetchStub();
    await assert.rejects(
      () => withGuard(
        submitAndWait({ some: 'graph' }, 'http://hangs.invalid', { timeoutMs: 60_000, requestTimeoutMs: 100 }),
        2000,
        'submitAndWait (submit POST)'
      ),
      /timed out.*http:\/\/hangs\.invalid/i
    );
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('submitAndWait absorbs transient per-request timeouts on /history polls via the existing retry path, then completes (SDL-H8)', async () => {
  const origFetch = globalThis.fetch;
  try {
    let historyCalls = 0;
    globalThis.fetch = async (url, init) => {
      if (url.includes('/prompt')) {
        return { ok: true, async json() { return { prompt_id: 'p-retry' }; }, async text() { return ''; } };
      }
      // /history/:id — hang (respecting abort) on the first two attempts,
      // then succeed on the third.
      historyCalls++;
      if (historyCalls <= 2) {
        return makeHangingFetchStub()(url, init);
      }
      return {
        ok: true,
        async json() { return { 'p-retry': { status: { completed: true }, outputs: {} } }; },
        async text() { return ''; },
      };
    };

    const result = await withGuard(
      submitAndWait({}, 'http://hangs.invalid', { timeoutMs: 60_000, requestTimeoutMs: 50 }),
      8000,
      'submitAndWait (history retry)'
    );
    assert.equal(result.status.completed, true);
    assert.ok(historyCalls >= 3, `expected at least 3 history polls (2 timeouts + 1 success), got ${historyCalls}`);
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('downloadImage rejects quickly (not hangs) against a server that never responds (SDL-H8)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeHangingFetchStub();
    await assert.rejects(
      () => withGuard(
        downloadImage('a.png', '', 'http://hangs.invalid', 'output', { timeoutMs: 100 }),
        2000,
        'downloadImage'
      ),
      /timed out/i
    );
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('uploadImage rejects quickly (not hangs) against a server that never responds (SDL-H8)', async () => {
  const origFetch = globalThis.fetch;
  const dir = await mkdtemp(join(tmpdir(), 'sdl-comfy-upload-'));
  try {
    const filePath = join(dir, 'in.png');
    await writeFile(filePath, 'fake-png-bytes');
    globalThis.fetch = makeHangingFetchStub();
    await assert.rejects(
      () => withGuard(
        uploadImage(filePath, 'in.png', 'http://hangs.invalid', { timeoutMs: 100 }),
        2000,
        'uploadImage'
      ),
      /timed out/i
    );
  } finally {
    globalThis.fetch = origFetch;
    await rm(dir, { recursive: true, force: true });
  }
});

// ─── SDL-L3: unguarded JSON parse on the history poll ─────────────

test('submitAndWait tolerates a 200-OK non-JSON history response (proxy error page) instead of dying immediately (SDL-L3)', async () => {
  const origFetch = globalThis.fetch;
  try {
    let historyCalls = 0;
    globalThis.fetch = async (url) => {
      if (url.includes('/prompt')) {
        return { ok: true, async json() { return { prompt_id: 'p-badjson' }; }, async text() { return ''; } };
      }
      historyCalls++;
      if (historyCalls === 1) {
        // A 200-OK response whose body is NOT valid JSON (e.g. an HTML
        // proxy error page) — .json() throws a SyntaxError.
        return {
          ok: true,
          async json() { throw new SyntaxError('Unexpected token < in JSON at position 0'); },
          async text() { return '<html>502 Bad Gateway</html>'; },
        };
      }
      return {
        ok: true,
        async json() { return { 'p-badjson': { status: { completed: true }, outputs: {} } }; },
        async text() { return ''; },
      };
    };

    const result = await submitAndWait({}, 'http://fake', { timeoutMs: 20_000 });
    assert.equal(result.status.completed, true);
    assert.ok(historyCalls >= 2, `expected the bad-JSON poll to be retried, got ${historyCalls} call(s)`);
  } finally {
    globalThis.fetch = origFetch;
  }
});
