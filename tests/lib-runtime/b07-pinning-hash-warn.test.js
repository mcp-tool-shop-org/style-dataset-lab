/**
 * Unit tests for B07 in lib/run-manifest.js.
 *
 * hashModelFile() correctly never throws and encodes failures as
 * `hash_note`. Nothing read it: buildPinning() didn't aggregate or log,
 * and the file imported no logger at all. A typo'd SDLAB_MODELS_DIR (or a
 * model genuinely missing from disk) produced a wave where every model has
 * `sha256: null` + a note — with NO console signal. PIN_PER_STEP's whole
 * purpose (byte-for-byte replayability) is lost silently.
 *
 * Fix: buildPinning() counts non-null, non-"skipped" hash_notes and warns
 * once per wave. Critically, the DEFAULT path (hashModels: false, meaning
 * every model legitimately has a "hash skipped (pass --hash-models)" note)
 * must NOT warn — that is expected behavior, not a failure, and warning on
 * it would make every ordinary run noisy.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildPinning } from '../../lib/run-manifest.js';

function captureStderr(fn) {
  const orig = console.error;
  const lines = [];
  console.error = (...a) => lines.push(a.join(' '));
  try {
    return { result: fn(), lines };
  } finally {
    console.error = orig;
  }
}

async function makeModelsDir() {
  const dir = await mkdtemp(join(tmpdir(), 'sdl-b07-models-'));
  await mkdir(join(dir, 'checkpoints'), { recursive: true });
  await mkdir(join(dir, 'loras'), { recursive: true });
  return dir;
}

test('buildPinning warns with a count when a model fails to hash under --hash-models (B07)', async () => {
  const modelsDir = await makeModelsDir();
  try {
    // "checkpoint" resolves and hashes fine; a typo'd/missing filename does not.
    await writeFile(join(modelsDir, 'checkpoints', 'real.safetensors'), 'CONTENT');

    const { result, lines } = captureStderr(() =>
      buildPinning({
        graph: { 1: { class_type: 'CheckpointLoaderSimple', inputs: {} } },
        models: { checkpoint: 'typo-checkpoint.safetensors' },
        loras: [],
        hashModels: true,
        modelsDir,
      }),
    );

    assert.equal(result.models.checkpoint.sha256, null);
    assert.match(result.models.checkpoint.hash_note, /unresolved/);
    assert.equal(lines.length, 1, 'expected exactly one warn() call for the wave, not zero (the defect) and not one per model');
    assert.match(lines[0], /1/, 'expected the warning to mention a count');
    assert.match(lines[0].toLowerCase(), /fail/, 'expected the warning to name this as a hashing failure');
  } finally {
    await rm(modelsDir, { recursive: true, force: true });
  }
});

test('buildPinning does NOT warn on the default path where hashing was simply not requested (B07 — no false positive on the common case)', async () => {
  const modelsDir = await makeModelsDir();
  try {
    // Both files genuinely exist and resolve — only hashing itself is
    // skipped (hashModels omitted). An unresolved file would be a REAL
    // failure regardless of hashModels, so it must exist here for this to
    // be a clean "skipped, not failed" test.
    await writeFile(join(modelsDir, 'checkpoints', 'real.safetensors'), 'CONTENT');
    await writeFile(join(modelsDir, 'loras', 'style.safetensors'), 'LORA-CONTENT');

    const { result, lines } = captureStderr(() =>
      buildPinning({
        graph: {},
        models: { checkpoint: 'real.safetensors' },
        loras: [{ name: 'style.safetensors' }],
        // hashModels omitted — defaults to false, the ordinary/default run.
        modelsDir,
      }),
    );

    assert.equal(result.models.checkpoint.sha256, null);
    assert.match(result.models.checkpoint.hash_note, /hash skipped/);
    assert.equal(result.loras[0].sha256, null);
    assert.match(result.loras[0].hash_note, /hash skipped/);
    assert.equal(lines.length, 0, 'the default "hashing not requested" path must stay silent — it is not a failure');
  } finally {
    await rm(modelsDir, { recursive: true, force: true });
  }
});

test('buildPinning does not warn when every model hashes successfully (B07 — no false positive on success)', async () => {
  const modelsDir = await makeModelsDir();
  try {
    await writeFile(join(modelsDir, 'checkpoints', 'real.safetensors'), 'CONTENT');
    await writeFile(join(modelsDir, 'loras', 'style.safetensors'), 'LORA-CONTENT');

    const { result, lines } = captureStderr(() =>
      buildPinning({
        graph: {},
        models: { checkpoint: 'real.safetensors' },
        loras: [{ name: 'style.safetensors' }],
        hashModels: true,
        modelsDir,
      }),
    );

    assert.ok(result.models.checkpoint.sha256);
    assert.ok(result.loras[0].sha256);
    assert.equal(lines.length, 0);
  } finally {
    await rm(modelsDir, { recursive: true, force: true });
  }
});

test('buildPinning counts BOTH a failed model AND a failed lora in the same warning (B07)', async () => {
  const modelsDir = await makeModelsDir();
  try {
    // Nothing on disk at all — checkpoint and lora both fail to resolve.
    const { result, lines } = captureStderr(() =>
      buildPinning({
        graph: {},
        models: { checkpoint: 'missing-checkpoint.safetensors' },
        loras: [{ name: 'missing-lora.safetensors' }],
        hashModels: true,
        modelsDir,
      }),
    );

    assert.equal(result.models.checkpoint.sha256, null);
    assert.equal(result.loras[0].sha256, null);
    assert.equal(lines.length, 1, 'still exactly ONE warn() call for the whole wave, not one per failed file');
    assert.match(lines[0], /2/, 'expected the count to include both failures');
  } finally {
    await rm(modelsDir, { recursive: true, force: true });
  }
});
