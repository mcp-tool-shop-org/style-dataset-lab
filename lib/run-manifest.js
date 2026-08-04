/**
 * Run-manifest pinning contract (PIN_PER_STEP).
 *
 * ONE source of truth for the fields that make a generation wave byte-for-byte
 * replayable. Three writers emit provenance today — `scripts/generate.js`
 * (record `provenance`), `lib/adapters/comfyui-runner.js` (run `manifest.json`),
 * and `scripts/qwen_generate.py` (the wave `generation.json` receipt) — and they
 * MUST all pin the same way. This module is the field-name authority; the
 * Python receipt mirrors the identical field contract (see qwen_generate.py).
 *
 * Design (DECOMPOSE_BY_SECRETS, Parnas 1972): the pinning field names + the
 * best-effort model hasher live here so the writers can never drift apart
 * silently. When the model changes, this secret-hiding boundary survives.
 *
 * The pinning block closes three PIN_PER_STEP gaps that the pre-3.3.0 manifests
 * left open (base/sampler/scheduler/shift/seed/steps/cfg were already recorded):
 *   1. comfy_workflow_sha — the exact ComfyUI graph that ran, as a hash.
 *   2. model/LoRA content identity — filenames upgraded to {name,size_bytes,sha256}.
 *   3. seed_policy — HOW seeds were chosen (intent), not just the values.
 *
 * Every field is optional and additive. Legacy manifests with no `pinning`
 * block load fine; readers nullish-coalesce (`m.pinning?.comfy_workflow_sha ?? null`).
 */

import { createHash } from 'node:crypto';
import { openSync, readSync, closeSync, statSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { warn } from './log.js';

/**
 * Contract version for the `pinning` block itself. Bump when the block's shape
 * changes (a new field, a renamed field). Independent of the manifest
 * SCHEMA_VERSION (lib/snapshot.js) — that versions the snapshot/split/export
 * manifest family; this versions the generation-provenance pin. Mirrored as a
 * literal in scripts/qwen_generate.py — keep the two in lockstep.
 */
export const PINNING_VERSION = '1.0.0';

/**
 * The ONE hash_note value that means "hashing was never attempted because
 * --hash-models wasn't passed" — NOT a failure. buildPinning() (B07) needs
 * to tell this apart from every other hash_note (unresolved/stat
 * failed/read error/no filename), all of which ARE failures worth warning
 * about. Shared as a constant so hashModelFile's own note and buildPinning's
 * filter can never drift apart.
 */
const HASH_SKIPPED_NOTE = 'hash skipped (pass --hash-models)';

/**
 * Seed policies — the INTENT behind seed selection, recorded alongside the
 * concrete per-item seed values so a reader knows how to regenerate.
 */
export const SEED_POLICIES = Object.freeze({
  EXPLICIT_PER_ITEM: 'explicit-per-item', // each item's seed is recorded verbatim (qwen_generate.py wave receipt)
  BASE_INCREMENT: 'base+increment',        // seed = base_seed + job_index (generate.js / batch path)
  FIXED: 'fixed',                          // every item shares one seed
  RANDOM: 'random',                        // first seed fixed, rest sampled
});

/**
 * Map a runtime seed_mode ('increment' | 'fixed' | 'random') to a seed_policy.
 * `increment` is the base+index scheme; unknown modes fall back to base+increment.
 */
export function seedPolicyFromMode(seedMode) {
  switch (seedMode) {
    case 'fixed': return SEED_POLICIES.FIXED;
    case 'random': return SEED_POLICIES.RANDOM;
    case 'increment':
    default: return SEED_POLICIES.BASE_INCREMENT;
  }
}

// ─── Stable serialization ────────────────────────────────────────

/**
 * Deterministic JSON: object keys sorted, arrays kept in order (arrays are
 * meaningful sequences — a LoRA chain, a node's input wiring). Guarantees the
 * same semantic graph hashes identically regardless of key insertion order.
 */
export function stableStringify(value) {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort();
    const parts = [];
    for (const k of keys) {
      if (value[k] === undefined) continue;
      parts.push(JSON.stringify(k) + ':' + stableStringify(value[k]));
    }
    return '{' + parts.join(',') + '}';
  }
  return 'null';
}

/**
 * Return a copy of a ComfyUI graph with per-ITEM nondeterminism removed, so the
 * whole wave shares ONE comfy_workflow_sha. Normalized out (recorded elsewhere,
 * per item): KSampler seed / noise_seed, CLIPTextEncode prompt text, SaveImage
 * filename_prefix. What SURVIVES the hash is the pipeline skeleton — node
 * topology, model loaders, sampler/scheduler/shift, LoRA chain + weights,
 * dims/steps/cfg — i.e. exactly the part that must match to replay the wave.
 */
export function normalizeGraphForHash(graph) {
  const out = {};
  for (const [id, node] of Object.entries(graph || {})) {
    const inputs = { ...(node?.inputs || {}) };
    const cls = node?.class_type;
    if (cls === 'KSampler' || cls === 'KSamplerAdvanced') {
      if ('seed' in inputs) inputs.seed = 0;
      if ('noise_seed' in inputs) inputs.noise_seed = 0;
    } else if (cls === 'CLIPTextEncode') {
      if ('text' in inputs) inputs.text = '';
    } else if (cls === 'SaveImage') {
      if ('filename_prefix' in inputs) inputs.filename_prefix = '';
    }
    out[id] = { class_type: cls, inputs };
  }
  return out;
}

/**
 * SHA-256 of the exact ComfyUI graph submitted for the wave (per-item seed +
 * prompt normalized out — see normalizeGraphForHash). Returns a `sha256:`-prefixed
 * digest, or null for an empty/absent graph.
 */
export function comfyWorkflowSha(graph) {
  if (!graph || Object.keys(graph).length === 0) return null;
  const normalized = normalizeGraphForHash(graph);
  return 'sha256:' + createHash('sha256').update(stableStringify(normalized)).digest('hex');
}

// ─── Model file resolution + hashing (best-effort) ───────────────

/**
 * Default ComfyUI models directory on the rig. Override with SDLAB_MODELS_DIR.
 * Hashing is opt-in and best-effort, so a wrong/absent path degrades cleanly to
 * `sha256: null` — it never fails a generation.
 */
export function defaultModelsDir() {
  return process.env.SDLAB_MODELS_DIR
    || 'E:/AI-Models/ComfyUI_windows_portable/ComfyUI/models';
}

// Kind → candidate subdirectories under the models dir, in search order.
const KIND_SUBDIRS = {
  unet: ['diffusion_models', 'unet'],
  clip: ['text_encoders', 'clip'],
  vae: ['vae'],
  checkpoint: ['checkpoints'],
  lora: ['loras'],
};

/**
 * Resolve a model filename to an absolute path under the models dir. Searches
 * ONLY the kind-appropriate subdirs (plus the modelsDir root itself, which is
 * kind-agnostic, not another kind's territory) — mirroring ComfyUI's own
 * loaders, which never search across kinds (a UNETLoader never looks in
 * checkpoints/, a VAELoader never looks in loras/, etc).
 *
 * SDL-M8: this used to also fall back to every OTHER kind's subdirs, so a
 * missing unet could silently resolve to a same-named file under
 * checkpoints/ and get pinned as though it were the unet ComfyUI actually
 * loaded — a clean-looking wrong identity. An honest `null` (unresolved →
 * sha256 null + a note, see hashModelFile) is the correct outcome when the
 * kind-specific subdirs don't have the file.
 *
 * Returns null when nothing matches.
 */
export function resolveModelPath(name, kind, modelsDir = defaultModelsDir()) {
  if (!name || !modelsDir) return null;
  const subdirs = [...(KIND_SUBDIRS[kind] || []), '.'];
  const tried = new Set();
  for (const sub of subdirs) {
    const candidate = join(modelsDir, sub, name);
    if (tried.has(candidate)) continue;
    tried.add(candidate);
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

/**
 * Streaming SHA-256 of a file — 1 MiB chunks, synchronous, never loads the whole
 * (multi-GB) file into memory. Returns a `sha256:`-prefixed digest.
 */
export function sha256File(path) {
  const hash = createHash('sha256');
  const fd = openSync(path, 'r');
  try {
    const buf = Buffer.allocUnsafe(1 << 20);
    let bytes;
    while ((bytes = readSync(fd, buf, 0, buf.length, null)) > 0) {
      hash.update(bytes === buf.length ? buf : buf.subarray(0, bytes));
    }
  } finally {
    closeSync(fd);
  }
  return 'sha256:' + hash.digest('hex');
}

// SDL-M9: a cheap partial-content fingerprint folded into the cache key
// alongside name/size/mtime. The key used to be bare name:size:round(mtime)
// with no content check — on a coarse-mtime mount (network shares, some
// FAT/exFAT mounts), a same-size in-place replacement (e.g. swapping a
// LoRA) can round to the SAME mtime as the file it replaced, so the cache
// would silently serve the sha256 of the OLD content forever. Sampling the
// first/last few KB — not hashing the whole multi-GB file, which would
// defeat the point of caching — is enough to catch almost any real
// replacement while staying cheap on every call (including cache hits).
const SAMPLE_BYTES = 4096;

/**
 * Cheap content fingerprint: sha256 of the first + last SAMPLE_BYTES of the
 * file (or the whole file if smaller). Synchronous, bounded I/O — a few KB
 * regardless of file size, unlike sha256File's full-content streaming read.
 */
function sampleFingerprint(path, size) {
  const fd = openSync(path, 'r');
  try {
    const hash = createHash('sha256');
    const headLen = Math.min(SAMPLE_BYTES, size);
    if (headLen > 0) {
      const head = Buffer.allocUnsafe(headLen);
      readSync(fd, head, 0, headLen, 0);
      hash.update(head);
    }
    if (size > SAMPLE_BYTES) {
      const tailLen = Math.min(SAMPLE_BYTES, size - headLen);
      const tail = Buffer.allocUnsafe(tailLen);
      readSync(fd, tail, 0, tailLen, size - tailLen);
      hash.update(tail);
    }
    return hash.digest('hex').slice(0, 16);
  } finally {
    closeSync(fd);
  }
}

/**
 * Best-effort content identity for one model/LoRA file: {name, size_bytes, sha256}
 * (+ a short `hash_note` when sha256 can't be produced). size_bytes is always
 * filled when the file resolves (a cheap stat); sha256 is gated behind
 * `doHash` (the --hash-models opt-in) and cached by (name, size, mtime,
 * partial-content sample) so multi-GB checkpoints aren't re-hashed every
 * wave (SDL-M9: the sample is what keeps a same-size in-place replacement
 * from reusing a stale cache entry).
 *
 * @param {string} name — model filename as it appears in the graph
 * @param {Object} [opts]
 * @param {'unet'|'clip'|'vae'|'checkpoint'|'lora'} [opts.kind]
 * @param {string} [opts.modelsDir]
 * @param {boolean} [opts.doHash=false] — compute sha256 (else record name+size only)
 * @param {{map: Map, cacheFile?: string, dirty: boolean}} [opts.cache]
 */
export function hashModelFile(name, { kind, modelsDir = defaultModelsDir(), doHash = false, cache } = {}) {
  if (!name) return { name: name ?? null, size_bytes: null, sha256: null, hash_note: 'no filename' };
  const resolved = resolveModelPath(name, kind, modelsDir);
  if (!resolved) return { name, size_bytes: null, sha256: null, hash_note: `unresolved under ${modelsDir}` };
  let size_bytes = null;
  let mtimeMs = 0;
  try {
    const st = statSync(resolved);
    size_bytes = st.size;
    mtimeMs = st.mtimeMs;
  } catch {
    return { name, size_bytes: null, sha256: null, hash_note: 'stat failed' };
  }
  if (!doHash) return { name, size_bytes, sha256: null, hash_note: HASH_SKIPPED_NOTE };
  let sample = '';
  try {
    sample = sampleFingerprint(resolved, size_bytes);
  } catch {
    // Best-effort — if sampling fails, fall back to the coarser
    // name:size:mtime key; the sha256File() attempt below will surface any
    // real read error anyway.
  }
  const key = `${name}:${size_bytes}:${Math.round(mtimeMs)}:${sample}`;
  if (cache?.map?.has(key)) return { name, size_bytes, sha256: cache.map.get(key) };
  let sha256;
  try {
    sha256 = sha256File(resolved);
  } catch {
    return { name, size_bytes, sha256: null, hash_note: 'hash failed (read error)' };
  }
  if (cache?.map) {
    cache.map.set(key, sha256);
    cache.dirty = true;
  }
  return { name, size_bytes, sha256 };
}

/**
 * Content-identity block for the model loaders of a wave. `modelSpec` maps a
 * role to a filename — {unet, clip, vae} for the Qwen DiT path, {checkpoint}
 * for the SDXL path. Only provided roles appear in the result.
 */
export function buildModelHashes(modelSpec = {}, opts = {}) {
  const roleKind = { unet: 'unet', clip: 'clip', vae: 'vae', checkpoint: 'checkpoint' };
  const out = {};
  for (const [role, kind] of Object.entries(roleKind)) {
    const name = modelSpec[role];
    if (!name) continue;
    out[role] = hashModelFile(name, { ...opts, kind });
  }
  return out;
}

// ─── Persistent hash cache (best-effort) ─────────────────────────

/**
 * Create a hash cache. Loads the on-disk JSON map (name:size:mtime → sha256) if
 * present, so hashes survive across waves. `cacheFile` defaults to a dotfile in
 * the models dir; override with SDLAB_HASH_CACHE. All I/O is best-effort — a
 * missing/unwritable cache never fails a run.
 */
export function createHashCache(cacheFile) {
  const file = cacheFile
    || process.env.SDLAB_HASH_CACHE
    || join(defaultModelsDir(), '.sdlab-hash-cache.json');
  const map = new Map();
  try {
    if (existsSync(file)) {
      const obj = JSON.parse(readFileSync(file, 'utf-8'));
      for (const [k, v] of Object.entries(obj)) map.set(k, v);
    }
  } catch { /* best-effort: ignore a corrupt/unreadable cache */ }
  return { map, cacheFile: file, dirty: false };
}

/**
 * Persist a hash cache to disk if it grew. Best-effort — swallows write errors.
 */
export function flushHashCache(cache) {
  if (!cache || !cache.dirty || !cache.cacheFile) return;
  try {
    const obj = Object.fromEntries(cache.map);
    writeFileSync(cache.cacheFile, JSON.stringify(obj, null, 2));
    cache.dirty = false;
  } catch { /* best-effort: ignore */ }
}

// ─── The pinning block ───────────────────────────────────────────

/**
 * Build the pinning block for a wave/item. Identical shape across all three
 * writers (see module header). Every writer calls this so the contract is
 * enforced in ONE place.
 *
 * @param {Object} args
 * @param {Object} [args.graph] — the ComfyUI node graph submitted (for comfy_workflow_sha)
 * @param {Object} [args.models] — {unet?, clip?, vae?, checkpoint?} filenames
 * @param {Array<{name:string, weight?:number}>} [args.loras]
 * @param {string} [args.seedPolicy] — one of SEED_POLICIES
 * @param {boolean} [args.hashModels=false] — opt-in sha256 of model/LoRA files
 * @param {string} [args.modelsDir]
 * @param {{map: Map, cacheFile?: string, dirty: boolean}} [args.cache]
 * @returns {Object} pinning block
 */
export function buildPinning({ graph, models = {}, loras = [], seedPolicy = null, hashModels = false, modelsDir = defaultModelsDir(), cache } = {}) {
  const opts = { modelsDir, doHash: hashModels, cache };
  const modelHashes = buildModelHashes(models, opts);
  const loraHashes = (loras || []).map((l) => ({
    ...hashModelFile(l.name, { ...opts, kind: 'lora' }),
    weight: l.weight ?? 1.0,
  }));

  // B07: hash_note silently encoded a hashing FAILURE (unresolved file,
  // stat failed, read error, no filename) with nothing reading it —
  // buildPinning() never aggregated or logged, and this file imported no
  // logger at all. A typo'd SDLAB_MODELS_DIR produced a wave where every
  // model has sha256: null + a note, with zero console signal — PIN_PER_STEP's
  // whole purpose (byte-for-byte replayability) lost silently. Warn ONCE per
  // wave with a count, but never on HASH_SKIPPED_NOTE — that note means
  // "hashing wasn't requested" (the default, --hash-models omitted), which
  // is expected behavior, not a failure, and would make every ordinary run
  // noisy if it warned too.
  const allEntries = [...Object.values(modelHashes), ...loraHashes];
  const failed = allEntries.filter((e) => e && e.hash_note != null && e.hash_note !== HASH_SKIPPED_NOTE);
  if (failed.length > 0) {
    const detail = failed.map((e) => `${e.name ?? '(unnamed)'} (${e.hash_note})`).join(', ');
    warn(`buildPinning: ${failed.length}/${allEntries.length} model(s)/lora(s) failed to hash: ${detail}`);
  }

  return {
    pinning_version: PINNING_VERSION,
    comfy_workflow_sha: comfyWorkflowSha(graph),
    seed_policy: seedPolicy,
    models: modelHashes,
    loras: loraHashes,
  };
}
