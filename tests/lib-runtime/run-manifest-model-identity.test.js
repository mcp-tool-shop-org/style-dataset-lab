/**
 * Unit tests for SDL-M8 (cross-kind model resolution) and SDL-M9 (stale
 * hash cache) in lib/run-manifest.js.
 *
 * SDL-M8: resolveModelPath used to fall back to searching every OTHER
 * kind's subdirs after its own came up empty. A missing unet could
 * silently resolve to a same-named file under checkpoints/ and get pinned
 * as though it were the unet ComfyUI actually loaded — a clean-looking
 * wrong identity. ComfyUI's own loaders never search across kinds.
 *
 * SDL-M9: the hash cache key was name:size:round(mtimeMs) with no content
 * check. On a coarse-mtime mount, a same-size in-place replacement (e.g.
 * swapping a LoRA) can round to the SAME mtime as the file it replaced, so
 * the cache would silently serve the sha256 of the OLD content forever.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { resolveModelPath, hashModelFile, sha256File } from '../../lib/run-manifest.js';

async function makeSandbox(prefix) {
  return await mkdtemp(join(tmpdir(), prefix));
}

// ─── SDL-M8: cross-kind resolution ────────────────────────────────

test('resolveModelPath does not resolve a unet name to a same-named file under checkpoints/ (SDL-M8)', async () => {
  const dir = await makeSandbox('sdl-modelid-crosskind-');
  try {
    await mkdir(join(dir, 'checkpoints'), { recursive: true });
    await mkdir(join(dir, 'diffusion_models'), { recursive: true }); // unet's own dir — left empty
    await writeFile(join(dir, 'checkpoints', 'shared-name.safetensors'), 'CHECKPOINT-BYTES');

    // The file exists ONLY under checkpoints/ (a different kind's subdir),
    // never under diffusion_models/ or unet/ (unet's own subdirs).
    const resolved = resolveModelPath('shared-name.safetensors', 'unet', dir);
    assert.equal(resolved, null, `expected no cross-kind resolution, got: ${resolved}`);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('resolveModelPath still resolves a model correctly placed in its own kind subdir (no false negative)', async () => {
  const dir = await makeSandbox('sdl-modelid-crosskind-ok-');
  try {
    await mkdir(join(dir, 'diffusion_models'), { recursive: true });
    await writeFile(join(dir, 'diffusion_models', 'real-unet.safetensors'), 'UNET-BYTES');
    const resolved = resolveModelPath('real-unet.safetensors', 'unet', dir);
    assert.ok(resolved && resolved.endsWith('real-unet.safetensors'), `expected a resolved path, got: ${resolved}`);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('hashModelFile reports an honest unresolved instead of a cross-kind wrong identity (SDL-M8)', async () => {
  const dir = await makeSandbox('sdl-modelid-crosskind-hash-');
  try {
    await mkdir(join(dir, 'checkpoints'), { recursive: true });
    await writeFile(join(dir, 'checkpoints', 'ambiguous.safetensors'), 'CHECKPOINT-BYTES');

    const r = hashModelFile('ambiguous.safetensors', { kind: 'unet', modelsDir: dir, doHash: true });
    assert.equal(r.size_bytes, null);
    assert.equal(r.sha256, null);
    assert.match(r.hash_note, /unresolved/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

// ─── SDL-M9: stale hash cache ──────────────────────────────────────

test('hashModelFile does not reuse a cache entry keyed the OLD way (name:size:mtime, no content sample) when content differs (SDL-M9)', async () => {
  const dir = await makeSandbox('sdl-modelid-stalecache-');
  try {
    await mkdir(join(dir, 'loras'), { recursive: true });
    const filePath = join(dir, 'loras', 'x.safetensors');
    // This IS the "after in-place replacement" file — same size class as
    // whatever used to be there, new content.
    await writeFile(filePath, 'NEW-CONTENT-AFTER-REPLACE');
    const st = statSync(filePath);

    // Poison the cache under the pre-SDL-M9 key shape (name:size:mtime —
    // no content sample) that a same-size in-place replacement on a
    // coarse-mtime mount would collide into for the file that used to be
    // here. This is the exact staleness the finding describes.
    const staleKey = `x.safetensors:${st.size}:${Math.round(st.mtimeMs)}`;
    const staleHash = 'sha256:' + 'deadbeef'.repeat(8);
    const cache = { map: new Map([[staleKey, staleHash]]), dirty: false };

    const r = hashModelFile('x.safetensors', { kind: 'lora', modelsDir: dir, doHash: true, cache });
    const trueHash = sha256File(filePath);

    assert.equal(r.sha256, trueHash, 'expected the real content hash, not the stale/poisoned entry');
    assert.notEqual(r.sha256, staleHash);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('hashModelFile cache still hits for genuinely unchanged content on a second call (no false negative)', async () => {
  const dir = await makeSandbox('sdl-modelid-cachehit-');
  try {
    await mkdir(join(dir, 'loras'), { recursive: true });
    await writeFile(join(dir, 'loras', 'stable.safetensors'), 'STABLE-CONTENT');
    const cache = { map: new Map(), dirty: false };

    const r1 = hashModelFile('stable.safetensors', { kind: 'lora', modelsDir: dir, doHash: true, cache });
    assert.equal(cache.dirty, true);
    assert.equal(cache.map.size, 1);

    const r2 = hashModelFile('stable.safetensors', { kind: 'lora', modelsDir: dir, doHash: true, cache });
    assert.equal(r2.sha256, r1.sha256);
    assert.equal(cache.map.size, 1, 'expected the second call to hit the cache, not add a new entry');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
