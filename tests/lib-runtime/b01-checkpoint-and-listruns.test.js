/**
 * Unit tests for B01 — checkpointRunManifest() had zero production callers.
 *
 * checkpointRunManifest() existed with a docstring saying it should be
 * called "after each completed output in long-running loops so a
 * crash/interruption leaves a partial record instead of an orphan dir",
 * but comfyui-runner.js only ever called saveRunManifest() ONCE, after the
 * whole loop finished. A run killed partway through wrote NO manifest at
 * all, and listRuns() silently `continue`d past the resulting
 * no-manifest directory — invisible to `sdlab run list`/`run show`.
 *
 * These tests prove:
 *   1. executeRun() actually invokes the checkpoint helper DURING the loop
 *      (not just that the helper exists — a test that only asserts the
 *      helper is importable/callable would miss the exact defect, since
 *      the helper already existed and worked in isolation).
 *   2. listRuns() no longer hides run directories with a missing or
 *      unreadable manifest.json — it reports them via warn()/verbose().
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises';
import { existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { executeRun } from '../../lib/adapters/comfyui-runner.js';
import { listRuns } from '../../lib/runtime-runs.js';

async function makeProject() {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b01-'));
  await mkdir(join(projectRoot, 'briefs'), { recursive: true });
  await mkdir(join(projectRoot, 'runs'), { recursive: true });
  await writeFile(join(projectRoot, 'project.json'), JSON.stringify({ defaults: {} }));
  return projectRoot;
}

function findRunDir(projectRoot) {
  const runsDir = join(projectRoot, 'runs');
  const entries = existsSync(runsDir) ? readdirSync(runsDir).filter((n) => n.startsWith('run_')) : [];
  return entries.length ? join(runsDir, entries[0]) : null;
}

function makeBrief(outputCount) {
  return {
    brief_id: 'b1',
    project_id: 'p1',
    prompt: 'a scene',
    negative_prompt: 'bad',
    expected_outputs: { output_mode: 'portrait_set', output_count: outputCount },
    runtime_plan: { seed_mode: 'increment' },
  };
}

// ─── 1. checkpoint fires mid-loop, not just at the end ────────────────

test('executeRun() checkpoints manifest.json DURING the loop, before the run finishes (B01)', async () => {
  const projectRoot = await makeProject();
  const origFetch = globalThis.fetch;
  let promptCalls = 0;
  let midLoopManifest = null;
  let midLoopExisted = null;

  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u.endsWith('/system_stats')) {
      return { ok: true, async json() { return {}; }, async text() { return ''; } };
    }
    if (u.includes('/prompt') && init?.method === 'POST') {
      promptCalls++;
      if (promptCalls === 2) {
        // Item 1 has already fully completed — INCLUDING its post-item
        // checkpoint write, which executeRun must `await` before starting
        // item 2 — by the time this second submit request is sent. This is
        // the moment that proves the checkpoint fires mid-loop rather than
        // only once at the very end (a test that waits for executeRun to
        // resolve and only then reads manifest.json cannot distinguish
        // "checkpointed every item" from "saved once at the end").
        const runDir = findRunDir(projectRoot);
        midLoopExisted = runDir && existsSync(join(runDir, 'manifest.json'));
        if (midLoopExisted) {
          midLoopManifest = JSON.parse(await readFile(join(runDir, 'manifest.json'), 'utf-8'));
        }
      }
      return { ok: true, async json() { return { prompt_id: `p-${promptCalls}` }; }, async text() { return ''; } };
    }
    if (u.includes('/history/')) {
      const id = u.split('/history/')[1];
      return {
        ok: true,
        async json() {
          return {
            [id]: {
              status: { completed: true },
              outputs: { 9: { images: [{ filename: `${id}.png`, subfolder: '' }] } },
            },
          };
        },
        async text() { return ''; },
      };
    }
    if (u.includes('/view')) {
      return { ok: true, async arrayBuffer() { return new Uint8Array([1, 2, 3]).buffer; } };
    }
    throw new Error(`unexpected fetch in test: ${u}`);
  };

  try {
    const manifest = await executeRun({ projectRoot, projectName: 'p1', brief: makeBrief(3) });

    assert.equal(promptCalls, 3, 'expected 3 submissions for output_count 3');
    assert.ok(midLoopExisted, 'expected a checkpointed manifest.json to already exist on disk before item 2 submitted — this is the exact defect: comfyui-runner.js only called saveRunManifest() once, after the whole loop');
    assert.ok(midLoopManifest, 'expected to have read a manifest snapshot mid-loop');
    assert.equal(midLoopManifest.incremental, true, 'a mid-run checkpoint must be stamped incremental (checkpointRunManifest\'s own contract)');
    assert.equal(midLoopManifest.outputs.length, 1, 'expected exactly 1 output recorded before item 2 was submitted');
    assert.equal(midLoopManifest.outputs[0].status, 'ok');

    // Final state, once the whole run completes.
    assert.equal(manifest.outputs.length, 3);
    assert.equal(manifest.success_count, 3);
    const finalOnDisk = JSON.parse(await readFile(join(findRunDir(projectRoot), 'manifest.json'), 'utf-8'));
    assert.equal(finalOnDisk.outputs.length, 3, 'final on-disk manifest must reflect all 3 outputs');
  } finally {
    globalThis.fetch = origFetch;
    await rm(projectRoot, { recursive: true, force: true });
  }
});

test('executeRun() leaves a readable partial manifest if the process stops after the first of several outputs (B01 — the actual failure mode)', async () => {
  // Simulates "killed at image 150 of 200": we only let ONE output complete
  // by throwing out of executeRun after its first checkpoint lands, then
  // assert the run directory is NOT an orphan — listRuns() (tested below)
  // depends on this manifest existing.
  const projectRoot = await makeProject();
  const origFetch = globalThis.fetch;
  let promptCalls = 0;

  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u.endsWith('/system_stats')) {
      return { ok: true, async json() { return {}; }, async text() { return ''; } };
    }
    if (u.includes('/prompt') && init?.method === 'POST') {
      promptCalls++;
      if (promptCalls === 2) {
        // Simulate the process dying right as item 2 starts submitting —
        // executeRun() itself keeps running (per-item errors are caught),
        // but we can still verify the ON-DISK state left behind by item 1's
        // checkpoint reflects a genuine partial run.
        throw Object.assign(new Error('simulated crash'), { code: 'ECONNRESET' });
      }
      return { ok: true, async json() { return { prompt_id: `p-${promptCalls}` }; }, async text() { return ''; } };
    }
    if (u.includes('/history/')) {
      const id = u.split('/history/')[1];
      return {
        ok: true,
        async json() {
          return { [id]: { status: { completed: true }, outputs: { 9: { images: [{ filename: `${id}.png`, subfolder: '' }] } } } };
        },
        async text() { return ''; },
      };
    }
    if (u.includes('/view')) {
      return { ok: true, async arrayBuffer() { return new Uint8Array([1, 2, 3]).buffer; } };
    }
    throw new Error(`unexpected fetch in test: ${u}`);
  };

  try {
    const manifest = await executeRun({ projectRoot, projectName: 'p1', brief: makeBrief(5) });
    // executeRun's own per-item try/catch absorbs the item-2 failure, so
    // the call still resolves — but the point of this test is the ON-DISK
    // artifact, not the return value.
    assert.equal(manifest.outputs[0].status, 'ok');
    assert.equal(manifest.outputs[1].status, 'error');

    const runDir = findRunDir(projectRoot);
    assert.ok(existsSync(join(runDir, 'manifest.json')), 'run directory must have a manifest.json (the defect: it had NONE until the whole loop finished)');
  } finally {
    globalThis.fetch = origFetch;
    await rm(projectRoot, { recursive: true, force: true });
  }
});

// ─── 2. listRuns() reports skipped/unreadable run dirs ────────────────

function captureConsole() {
  const origError = console.error;
  const origLog = console.log;
  const errLines = [];
  const logLines = [];
  console.error = (...a) => errLines.push(a.join(' '));
  console.log = (...a) => logLines.push(a.join(' '));
  return {
    errLines,
    logLines,
    restore() { console.error = origError; console.log = origLog; },
  };
}

test('listRuns() no longer silently hides a run directory with no manifest.json (B01)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b01-listruns-'));
  try {
    const runsDir = join(projectRoot, 'runs');
    await mkdir(join(runsDir, 'run_2026-01-01_001'), { recursive: true });
    await writeFile(
      join(runsDir, 'run_2026-01-01_001', 'manifest.json'),
      JSON.stringify({ run_id: 'run_2026-01-01_001', brief_id: 'b', output_count: 1, created_at: 't', adapter_target: 'comfyui' }),
    );
    // The orphan: a run dir with NO manifest.json at all (exactly what a
    // pre-fix crashed run left behind).
    await mkdir(join(runsDir, 'run_2026-01-01_002'), { recursive: true });

    const cap = captureConsole();
    let runs;
    try {
      runs = listRuns(projectRoot);
    } finally {
      cap.restore();
    }

    assert.equal(runs.length, 1, 'the orphan directory must still not be returned as a usable run');
    assert.equal(runs[0].run_id, 'run_2026-01-01_001');

    const allOutput = [...cap.errLines, ...cap.logLines].join('\n');
    assert.match(allOutput, /1/, 'expected the skip report to mention a count');
    assert.match(allOutput.toLowerCase(), /skip/, 'expected listRuns to report the skip instead of staying silent');
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

test('listRuns() reports an unreadable (malformed JSON) manifest.json too, not just a missing one (B01)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b01-listruns-bad-'));
  try {
    const runsDir = join(projectRoot, 'runs');
    await mkdir(join(runsDir, 'run_2026-01-01_001'), { recursive: true });
    await writeFile(join(runsDir, 'run_2026-01-01_001', 'manifest.json'), '{ not valid json');

    const cap = captureConsole();
    let runs;
    try {
      runs = listRuns(projectRoot);
    } finally {
      cap.restore();
    }

    assert.equal(runs.length, 0);
    const allOutput = [...cap.errLines, ...cap.logLines].join('\n');
    assert.match(allOutput.toLowerCase(), /skip/, 'a malformed manifest.json must also be reported, not silently dropped');
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});

test('listRuns() stays silent when every run directory is healthy (no false positives)', async () => {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdl-b01-listruns-ok-'));
  try {
    const runsDir = join(projectRoot, 'runs');
    await mkdir(join(runsDir, 'run_2026-01-01_001'), { recursive: true });
    await writeFile(
      join(runsDir, 'run_2026-01-01_001', 'manifest.json'),
      JSON.stringify({ run_id: 'run_2026-01-01_001', output_count: 1 }),
    );

    const cap = captureConsole();
    let runs;
    try {
      runs = listRuns(projectRoot);
    } finally {
      cap.restore();
    }

    assert.equal(runs.length, 1);
    assert.equal(cap.errLines.length, 0, 'a fully healthy runs/ dir must not warn about anything');
  } finally {
    await rm(projectRoot, { recursive: true, force: true });
  }
});
