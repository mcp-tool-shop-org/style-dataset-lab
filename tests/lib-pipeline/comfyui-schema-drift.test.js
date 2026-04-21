/**
 * Unit tests for lib/comfyui.js submitAndWait — PB-004 schema-drift bail
 * and PB-001 heartbeat plumbing.
 *
 * Stubs global fetch to simulate ComfyUI responses.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { submitAndWait } from '../../lib/comfyui.js';

function makeFetchStub(responses) {
  let i = 0;
  return async function stubbedFetch(url, _init) {
    const res = responses[Math.min(i, responses.length - 1)];
    i++;
    if (typeof res === 'function') return res(url);
    return {
      ok: res.ok ?? true,
      status: res.status ?? 200,
      async json() { return res.body; },
      async text() { return JSON.stringify(res.body); },
    };
  };
}

test('submitAndWait returns entry when status.completed === true', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeFetchStub([
      { body: { prompt_id: 'p1' } },                     // POST /prompt
      { body: { p1: { status: { completed: true }, outputs: { 9: { images: [{ filename: 'a.png' }] } } } } },
    ]);
    const out = await submitAndWait({ some: 'graph' }, 'http://fake', { timeoutMs: 5000 });
    assert.equal(out.status.completed, true);
  } finally { globalThis.fetch = origFetch; }
});

test('submitAndWait accepts status_str === "success" as completion (PB-004 future-proof)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeFetchStub([
      { body: { prompt_id: 'p2' } },
      { body: { p2: { status: { status_str: 'success' }, outputs: {} } } },
    ]);
    const out = await submitAndWait({}, 'http://fake', { timeoutMs: 5000 });
    assert.equal(out.status.status_str, 'success');
  } finally { globalThis.fetch = origFetch; }
});

test('submitAndWait bails on execution_error at top level (PB-004)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeFetchStub([
      { body: { prompt_id: 'p3' } },
      { body: { p3: { status: { status_str: 'running' }, execution_error: { node_id: 7, message: 'CUDA OOM' } } } },
    ]);
    await assert.rejects(
      () => submitAndWait({}, 'http://fake', { timeoutMs: 5000 }),
      /execution error.*p3/i,
    );
  } finally { globalThis.fetch = origFetch; }
});

test('submitAndWait bails on status.execution_error (PB-004)', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeFetchStub([
      { body: { prompt_id: 'p4' } },
      { body: { p4: { status: { execution_error: { message: 'bad node' } } } } },
    ]);
    await assert.rejects(
      () => submitAndWait({}, 'http://fake', { timeoutMs: 5000 }),
      /execution error/i,
    );
  } finally { globalThis.fetch = origFetch; }
});

test('submitAndWait bails on unrecognized status shape within UNKNOWN_STATUS_BAIL_POLLS (PB-004)', async () => {
  const origFetch = globalThis.fetch;
  try {
    // Respond with a brand-new schema shape forever: status object exists but
    // has neither completed nor status_str error nor execution_error.
    let calls = 0;
    globalThis.fetch = async (url) => {
      calls++;
      if (calls === 1) {
        return {
          ok: true,
          async json() { return { prompt_id: 'p5' }; },
          async text() { return ''; },
        };
      }
      return {
        ok: true,
        async json() { return { p5: { status: { progress: 'halfway', messages: [] } } }; },
        async text() { return ''; },
      };
    };
    await assert.rejects(
      () => submitAndWait({}, 'http://fake', { timeoutMs: 60_000 }),
      /unrecognized status shape.*p5/i,
    );
  } finally { globalThis.fetch = origFetch; }
});

test('submitAndWait still surfaces status_str === "error"', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = makeFetchStub([
      { body: { prompt_id: 'p6' } },
      { body: { p6: { status: { status_str: 'error', messages: ['kaboom'] } } } },
    ]);
    await assert.rejects(
      () => submitAndWait({}, 'http://fake', { timeoutMs: 5000 }),
      /generation failed/i,
    );
  } finally { globalThis.fetch = origFetch; }
});
