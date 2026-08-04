/**
 * Ingest engine — bring pre-existing images into the pipeline as bare,
 * uncurated candidate records.
 *
 * The gap this closes: there was no CLI path to get an image that was NOT
 * produced by `sdlab generate`/`run generate`/`batch generate` into the
 * project. `sdlab reingest generated` requires a trained LoRA's training
 * manifest (lib/reingest.js loadTrainingManifest() unconditionally) — it
 * exists to bring TRAINED-MODEL outputs back in, not pre-training
 * candidates. `sdlab reingest selected` requires a selection id, which only
 * the production loop can mint. Neither can take "a folder of images from
 * somewhere else" (hand-picked references, a batch rendered in external
 * Python against Comfy Cloud, salvage from a lost pipeline run) and turn it
 * into records ready for `sdlab curate`. This module is that third path.
 *
 * Non-negotiables this module holds itself to:
 *  - NEVER invents a judgment, a score, or a caption. Every record ships
 *    with judgment: null, canon: null (via buildBaseRecord, the same
 *    shared helper lib/reingest.js already uses) — uncurated, exactly like
 *    everything else that hasn't been through `sdlab curate` yet.
 *  - provenance.source is always 'external' — honestly distinguishable
 *    from provenance.source === 'generated' (lib/reingest.js) and from the
 *    flat generation_provenance shape lib/generated-provenance.js builds
 *    for selected run/batch outputs. An ingested record's generation
 *    details (prompt, seed, ...) are attached ONLY when a --wave file or a
 *    receipts.jsonl actually supplies them for that specific id — never
 *    guessed, never interpolated from a sibling.
 *  - id derivation is validated, not silently rewritten: a filename stem
 *    that fails the SAME allowlist lib/export.js already uses for every
 *    other record-id-becomes-a-filename boundary (SAFE_ID_RE / assertSafeId
 *    — SDL-H5) is rejected per-file with a reason, not coerced into
 *    something "close enough". A directory scan is bulk, externally-named
 *    input by nature (unlike an already-pipeline-produced record id), so
 *    one unsafe filename is reported and skipped rather than aborting the
 *    whole ingest — the vector is closed either way, since no path is ever
 *    built from a name that fails the check.
 *  - --dry-run performs zero filesystem writes: no mkdir, no image copy, no
 *    record write. (SDL-M11 fixed five scripts that violated exactly this.)
 *  - idempotent: an id whose record already exists is skipped, never
 *    duplicated or clobbered, and every skip is reported back to the
 *    caller (not just counted).
 *  - crash-safe: both the copied image and the written record land via
 *    temp-file-then-rename, mirroring the atomic pattern lib/runtime-runs.js
 *    (saveRunManifest/checkpointRunManifest) and lib/batch-runs.js already
 *    use. A process killed mid-write must never leave a truncated file at
 *    the FINAL path that a later run's existsSync() mistakes for "done".
 */

import { readFile, writeFile, readdir, stat, mkdir, copyFile, rename, unlink } from 'node:fs/promises';
import { join, basename, extname, relative, sep } from 'node:path';
import { existsSync } from 'node:fs';
import { buildBaseRecord } from './records.js';
import { assertSafeId } from './export.js';
import { inputError } from './errors.js';
import { warn, verbose } from './log.js';

// Mirrors lib/reingest.js's IMAGE_EXTENSIONS. Not imported from there —
// that module doesn't export the constant, and this file's ownership
// boundary for this change doesn't include editing lib/reingest.js.
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp']);

const RECEIPTS_FILENAME = 'receipts.jsonl';

/** Normalize a path to forward slashes for storage (matches asset_path style used throughout this codebase). */
function toPortablePath(p) {
  return p.split(sep).join('/');
}

// ─── Atomic write helpers ──────────────────────────────────────────
//
// Same temp-file-then-rename shape as lib/runtime-runs.js's
// atomicWriteJson / lib/batch-runs.js's atomicWriteJson / lib/reingest-
// selected.js's atomicWriteText. None of those three are exported (each
// module keeps its own copy — that is the established convention in this
// codebase for this exact ~10-line helper, not an oversight to "fix" by
// centralizing here), so this is a fourth copy of the same pattern rather
// than a new invention.

async function atomicWriteFile(targetPath, body) {
  const tmpPath = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  try {
    await writeFile(tmpPath, body);
    await rename(tmpPath, targetPath);
  } catch (err) {
    try { await unlink(tmpPath); } catch { /* best-effort cleanup */ }
    throw err;
  }
}

/**
 * Copy a file atomically: copy to a temp path in the SAME directory as
 * destPath, then rename. A process killed mid-copy leaves only the
 * uniquely-named temp file behind — never a partial file sitting at
 * destPath that a later run's `existsSync(destPath)` would mistake for a
 * complete, already-ingested image and skip re-copying forever.
 */
async function atomicCopyFile(srcPath, destPath) {
  const tmpPath = `${destPath}.tmp-${process.pid}-${Date.now()}`;
  try {
    await copyFile(srcPath, tmpPath);
    await rename(tmpPath, destPath);
  } catch (err) {
    try { await unlink(tmpPath); } catch { /* best-effort cleanup */ }
    throw err;
  }
}

// ─── Wave / receipts loaders ────────────────────────────────────────

/**
 * Load a wave pack (the shape of projects/salt-road/inputs/prompts/
 * wave-v2.json: `{ formula_ref?, wave?, items: [{ id, seed, subject, ... }] }`)
 * into a Map<id, item>. Falls back to a `subjects` array (the
 * `sdlab generate` prompt-pack shape) if `items` is absent, so a wave file
 * authored either way is still usable.
 *
 * Returns an empty index when wavePath is falsy — --wave is opt-in
 * enrichment, not a requirement. A wavePath that IS given but cannot be
 * read/parsed is a user error worth stopping for (they asked for that
 * file specifically), not a silent "provenance unknown" fallback.
 *
 * @param {string|null|undefined} wavePath — absolute, already-validated path
 * @returns {Promise<{index: Map<string,Object>, formulaRef: string|null, waveName: string|null}>}
 */
export async function loadWaveIndex(wavePath) {
  const index = new Map();
  if (!wavePath) return { index, formulaRef: null, waveName: null };

  if (!existsSync(wavePath)) {
    throw inputError(
      'INPUT_WAVE_NOT_FOUND',
      `--wave file not found: ${wavePath}`,
      'Check the path. Wave files live under inputs/prompts/*.json — see projects/salt-road/inputs/prompts/wave-v2.json for the shape.'
    );
  }

  let raw;
  try {
    raw = JSON.parse(await readFile(wavePath, 'utf-8'));
  } catch (err) {
    throw inputError(
      'INPUT_INVALID_JSON',
      `Failed to parse --wave file ${wavePath}: ${err.message}`,
      'Check the file for JSON syntax errors.'
    );
  }

  const items = Array.isArray(raw.items) ? raw.items
    : Array.isArray(raw.subjects) ? raw.subjects
    : null;

  if (!items) {
    warn(`ingest: --wave file ${wavePath} has no "items" or "subjects" array — no entries will be attached.`);
    return { index, formulaRef: raw.formula_ref || null, waveName: raw.wave || raw.name || null };
  }

  for (const item of items) {
    if (item && typeof item.id === 'string') index.set(item.id, item);
  }

  return { index, formulaRef: raw.formula_ref || null, waveName: raw.wave || raw.name || null };
}

/**
 * Load a receipts.jsonl (the shape of projects/salt-road/inbox/generated/
 * set-v2-2026-07-30/receipts.jsonl: one `{id, status, prompt_id, seed, secs}`
 * object per line) into a Map<id, receipt>.
 *
 * Best-effort by design: a missing file yields an empty Map (this is
 * opportunistic enrichment co-located with the images, not a requirement),
 * and a malformed INDIVIDUAL line is skipped with a warning rather than
 * failing the whole load — one corrupt trailing line from an interrupted
 * write must not blank out every other real receipt in the file.
 *
 * @param {string} receiptsPath — absolute path
 * @returns {Promise<Map<string,Object>>}
 */
export async function loadReceiptsIndex(receiptsPath) {
  const index = new Map();
  if (!receiptsPath || !existsSync(receiptsPath)) return index;

  const raw = await readFile(receiptsPath, 'utf-8');
  const lines = raw.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed) continue;
    try {
      const entry = JSON.parse(trimmed);
      if (entry && typeof entry.id === 'string') index.set(entry.id, entry);
    } catch (err) {
      warn(`ingest: ${receiptsPath}:${i + 1} is not valid JSON — line skipped (${err.message})`);
    }
  }
  return index;
}

// ─── Provenance builder ─────────────────────────────────────────────

/**
 * Build the provenance block for one ingested image. Additive-only: a
 * field is set exactly when a real source (the --wave entry or the
 * receipts.jsonl entry for this id) supplied it. Nothing here is ever
 * synthesized, interpolated, or defaulted from another record.
 */
function buildExternalProvenance({ file, sourcePath, waveEntry, waveMeta, receiptEntry, receiptsRelPath }) {
  const prov = {
    source: 'external',
    ingested_at: new Date().toISOString(),
    original_filename: file,
    original_path: sourcePath,
  };

  const notes = [];

  if (waveEntry) {
    prov.wave_file = waveMeta.waveRelPath;
    if (waveMeta.waveName) prov.wave_name = waveMeta.waveName;
    if (waveMeta.formulaRef) {
      prov.formula_ref = waveMeta.formulaRef;
      notes.push(
        'preamble_ref/negative_ref are keys into the wave\'s formula_ref file, not literal prompt/negative text.'
      );
    }
    if (waveEntry.seed !== undefined) prov.seed = waveEntry.seed;
    const promptText = waveEntry.subject ?? waveEntry.prompt;
    if (promptText !== undefined) prov.prompt = promptText;
    if (waveEntry.preamble !== undefined) prov.preamble_ref = waveEntry.preamble;
    if (waveEntry.neg !== undefined) prov.negative_ref = waveEntry.neg;
    if (waveEntry.negExtra !== undefined) prov.negative_extra = waveEntry.negExtra;
    if (waveEntry.cn !== undefined) prov.controlnet = waveEntry.cn;
    if (waveEntry.enriched_by !== undefined) prov.enriched_by = waveEntry.enriched_by;
  } else if (waveMeta.wavePath) {
    notes.push(`No entry for this id was found in --wave file ${waveMeta.waveRelPath}.`);
  }

  if (receiptEntry) {
    prov.receipts_file = receiptsRelPath;
    if (receiptEntry.prompt_id !== undefined) prov.prompt_id = receiptEntry.prompt_id;
    // Wave seed wins if both are present and disagree; a receipt seed is
    // still useful when the wave lacked one — never overwritten if already set.
    if (receiptEntry.seed !== undefined && prov.seed === undefined) prov.seed = receiptEntry.seed;
    if (receiptEntry.secs !== undefined) prov.generation_seconds = receiptEntry.secs;
    if (receiptEntry.status !== undefined) prov.receipt_status = receiptEntry.status;
  }

  prov.generation_provenance_known = Boolean(waveEntry || receiptEntry);
  if (!waveEntry && !receiptEntry) {
    notes.push(
      waveMeta.wavePath
        ? 'No matching wave or receipts.jsonl entry for this id — generation details are unknown.'
        : 'No --wave file supplied and no receipts.jsonl found alongside the source images — generation details are unknown.'
    );
  }
  if (notes.length) prov.provenance_note = notes.join(' ');

  return prov;
}

// ─── Main entry point ────────────────────────────────────────────────

/**
 * Ingest a directory of pre-existing images into a project as bare,
 * uncurated candidate records ready for `sdlab curate`.
 *
 * @param {string} projectRoot — absolute project root (already resolved by the caller)
 * @param {string} sourceDir — absolute path to a directory of images (already validated by the caller)
 * @param {Object} [options]
 * @param {string} [options.wavePath] — absolute, already-validated path to a wave JSON file
 * @param {boolean} [options.dryRun]
 * @returns {Promise<{created: string[], skipped: string[], rejected: {file:string, reason:string}[], receiptsFile: string|null}>}
 */
export async function ingestDirectory(projectRoot, sourceDir, options = {}) {
  const dryRun = Boolean(options.dryRun);

  if (!existsSync(sourceDir)) {
    throw inputError(
      'INPUT_SOURCE_NOT_FOUND',
      `Source directory not found: ${sourceDir}`,
      'Check the path passed to "sdlab ingest <dir>".'
    );
  }

  const recordsDir = join(projectRoot, 'records');
  const candidatesDir = join(projectRoot, 'outputs', 'candidates');

  // Wave + receipts are loaded up front, once, before touching any output
  // directory — reading is safe under --dry-run (no mutation).
  const wavePath = options.wavePath || null;
  const { index: waveIndex, formulaRef, waveName } = await loadWaveIndex(wavePath);
  const waveMeta = {
    wavePath,
    waveRelPath: wavePath ? toPortablePath(relative(projectRoot, wavePath)) : null,
    formulaRef,
    waveName,
  };

  const receiptsPath = join(sourceDir, RECEIPTS_FILENAME);
  const receiptsIndex = await loadReceiptsIndex(receiptsPath);
  const receiptsFound = receiptsIndex.size > 0;
  const receiptsRelPath = receiptsFound ? toPortablePath(relative(projectRoot, receiptsPath)) : null;
  if (receiptsFound) {
    verbose(`ingest: loaded ${receiptsIndex.size} receipt(s) from ${receiptsPath}`);
  }

  // SDL-M11 discipline: a --dry-run preview must be side-effect-free. Only
  // create output directories on a real run.
  if (!dryRun) {
    await mkdir(recordsDir, { recursive: true });
    await mkdir(candidatesDir, { recursive: true });
  }

  const entries = (await readdir(sourceDir)).sort();
  const imageFiles = entries.filter((f) => IMAGE_EXTENSIONS.has(extname(f).toLowerCase()));

  const created = [];
  const skipped = [];
  const rejected = [];

  for (const file of imageFiles) {
    const ext = extname(file);
    const stem = basename(file, ext);

    // SDL-H5-style boundary: a filename becoming a record id (and later a
    // path segment for the copied image / record file) is a path-traversal
    // vector. Reuses the exact allowlist lib/export.js already applies at
    // every other record-id-becomes-a-filename boundary in this codebase.
    // Unlike that adapter-layer call site (which hard-throws because an
    // unsafe id THERE means a pipeline-internal invariant already broke),
    // this is a first-touch scan of an arbitrary, externally-named
    // directory — one badly-named file (spaces, unicode, an accidental
    // "..") is the normal case, not an attack. It is rejected and reported
    // so the other 99 files in the same directory still get ingested; the
    // vector is closed identically either way, since no path is ever built
    // from a name that fails this check.
    try {
      assertSafeId(stem, `filename "${file}" in ${sourceDir}`);
    } catch (err) {
      rejected.push({ file, reason: err.message });
      continue;
    }

    const id = stem;
    const recordPath = join(recordsDir, `${id}.json`);

    if (existsSync(recordPath)) {
      skipped.push(id);
      continue;
    }

    if (dryRun) {
      // Preview only — no stat(), no copy, no write. Report what WOULD be
      // created without touching the filesystem beyond the read-only
      // listing/existence checks already done above.
      created.push(id);
      continue;
    }

    const sourcePath = join(sourceDir, file);
    const destPath = join(candidatesDir, file);
    const assetPath = toPortablePath(join('outputs', 'candidates', file));

    const fileStat = await stat(sourcePath);

    if (!existsSync(destPath)) {
      await atomicCopyFile(sourcePath, destPath);
    }

    const waveEntry = waveIndex.get(id) || null;
    const receiptEntry = receiptsIndex.get(id) || null;
    const provenance = buildExternalProvenance({
      file,
      sourcePath,
      waveEntry,
      waveMeta,
      receiptEntry,
      receiptsRelPath,
    });

    const record = buildBaseRecord(
      id,
      assetPath,
      { width: null, height: null, bytes: fileStat.size },
      provenance
    );

    await atomicWriteFile(recordPath, JSON.stringify(record, null, 2) + '\n');
    created.push(id);
  }

  return {
    created,
    skipped,
    rejected,
    receiptsFile: receiptsFound ? receiptsRelPath : null,
  };
}
