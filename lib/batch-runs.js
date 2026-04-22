/**
 * Batch runs — create batch directories, execute coordinated runs, save manifests.
 *
 * A batch groups multiple runs under one artifact:
 *   batch_YYYY-MM-DD_NNN/
 *     manifest.json
 *     summary.json / summary.md
 *     sheets/
 *     runs/   (symlinks or copies to project-level runs)
 *     briefs/ (slot briefs)
 */

import { writeFile, mkdir, copyFile, rename, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { getProjectRoot, getRunsDir } from './paths.js';
import { executeRun } from './adapters/comfyui-runner.js';
import { saveRunSummary } from './run-summary.js';
import { log, info, warn, verbose } from './log.js';
import { inputError } from './errors.js';

/**
 * PB-002 / PB-005: atomic write helper — write temp + rename.
 * Rename is atomic on a single filesystem, so a crash mid-write cannot
 * corrupt an existing manifest.
 */
async function atomicWriteJson(targetPath, obj) {
  const tmpPath = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  const body = JSON.stringify(obj, null, 2) + '\n';
  try {
    await writeFile(tmpPath, body);
    await rename(tmpPath, targetPath);
  } catch (err) {
    try { await unlink(tmpPath); } catch { /* ignore */ }
    throw err;
  }
}

/**
 * Return the batches directory for a project.
 */
export function getBatchesDir(projectRoot) {
  return join(projectRoot, 'batches');
}

/**
 * Generate batch ID: batch_YYYY-MM-DD_NNN
 */
// PB-008: tighten regex so stray directories like 'batch_<date>_001_wip'
// don't inflate the sequence via lenient parseInt.
const BATCH_SEQ_RE = /^(\d{3})$/;

export function generateBatchId(batchesDir) {
  const today = new Date().toISOString().slice(0, 10);
  const prefix = `batch_${today}_`;

  let maxSeq = 0;
  if (existsSync(batchesDir)) {
    const existing = readdirSync(batchesDir, { withFileTypes: true })
      .filter(e => e.isDirectory() && e.name.startsWith(prefix));
    for (const e of existing) {
      const seqStr = e.name.slice(prefix.length);
      const match = BATCH_SEQ_RE.exec(seqStr);
      if (!match) continue;
      const seq = parseInt(match[1], 10);
      if (seq > maxSeq) maxSeq = seq;
    }
  }

  const seq = String(maxSeq + 1).padStart(3, '0');
  return `${prefix}${seq}`;
}

/**
 * Create a batch directory and prepare its structure.
 */
export async function createBatchDir(projectRoot) {
  const batchesDir = getBatchesDir(projectRoot);
  const batchId = generateBatchId(batchesDir);
  const batchDir = join(batchesDir, batchId);

  await mkdir(join(batchDir, 'sheets'), { recursive: true });
  await mkdir(join(batchDir, 'briefs'), { recursive: true });

  return { batchId, batchDir };
}

/**
 * Execute all slot briefs as coordinated runs.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot
 * @param {string} opts.projectName
 * @param {string} opts.batchDir
 * @param {Object} opts.mode — batch mode definition
 * @param {Object[]} opts.slotBriefs — one brief per slot
 * @param {boolean} [opts.dryRun]
 * @returns {Promise<Object[]>} — array of { slot, brief, manifest }
 */
export async function executeBatchRuns({
  projectRoot,
  projectName,
  batchDir,
  mode,
  slotBriefs,
  dryRun = false,
}) {
  // PB-005: fail fast on length mismatch instead of crashing deep in the loop.
  if (!Array.isArray(mode?.variant_plan) || mode.variant_plan.length !== slotBriefs.length) {
    throw inputError(
      'BATCH_SLOT_PLAN_MISMATCH',
      `Batch variant_plan has ${mode?.variant_plan?.length ?? 0} slots but ` +
      `${slotBriefs.length} brief(s) were compiled`,
      'This is an internal invariant — rebuild the batch from the mode definition.'
    );
  }

  const results = [];
  // PB-005: incremental batch-progress manifest — written after every slot
  // so a crash never orphans the batch dir without a record of what ran.
  const progressPath = join(batchDir, 'manifest.json');

  for (let i = 0; i < slotBriefs.length; i++) {
    const slot = mode.variant_plan[i];
    const brief = slotBriefs[i];
    const slotLabel = slot.label || slot.slot_id;

    info(`[${i + 1}/${slotBriefs.length}] Slot: ${slotLabel}`);

    // Save brief into batch/briefs/
    const briefFilename = `${slot.slot_id}.json`;
    await writeFile(
      join(batchDir, 'briefs', briefFilename),
      JSON.stringify(brief, null, 2) + '\n'
    );

    // PB-005: per-slot try/catch — one slot failure no longer throws out of
    // the whole batch. Record the error and keep going so the user doesn't
    // lose already-completed slots.
    try {
      // Execute the run through the existing 4B pipeline
      const manifest = await executeRun({
        projectRoot,
        projectName,
        brief,
        dryRun,
      });

      // Save run summary
      const runDir = join(getRunsDir(projectRoot), manifest.run_id);
      await saveRunSummary(runDir, manifest);

      results.push({
        slot_id: slot.slot_id,
        label: slotLabel,
        brief_id: brief.brief_id,
        run_id: manifest.run_id,
        manifest,
        status: 'ok',
        // Pick the first successful output as the selected one
        selected_output: manifest.outputs.find(o =>
          o.status === 'ok' || o.status === 'dry_run'
        )?.filename || null,
      });
    } catch (err) {
      warn(`  ✗ slot ${slotLabel} failed: ${err.message}`);
      results.push({
        slot_id: slot.slot_id,
        label: slotLabel,
        brief_id: brief.brief_id,
        run_id: null,
        manifest: null,
        status: 'error',
        error: err.message,
        selected_output: null,
      });
    }

    // PB-005: checkpoint after every slot (atomic write).
    try {
      await atomicWriteJson(progressPath, {
        batch_dir: batchDir,
        mode_id: mode?.mode_id ?? mode?.id ?? null,
        incremental: true,
        last_checkpoint_at: new Date().toISOString(),
        completed: i + 1,
        total: slotBriefs.length,
        slots: results,
      });
      verbose(`batch checkpoint: ${i + 1}/${slotBriefs.length} slots`);
    } catch (err) {
      warn(`  batch checkpoint write failed: ${err.message}`);
    }
  }

  return results;
}

/**
 * Save a batch manifest.
 */
export async function saveBatchManifest(batchDir, manifest) {
  // PB-002: atomic write — safe to overwrite an in-progress checkpoint
  // because rename is atomic on a single filesystem.
  await atomicWriteJson(join(batchDir, 'manifest.json'), manifest);
}

/**
 * Load a batch manifest by ID.
 */
export function loadBatchManifest(projectRoot, batchId) {
  const batchDir = join(getBatchesDir(projectRoot), batchId);
  const manifestPath = join(batchDir, 'manifest.json');

  if (!existsSync(manifestPath)) {
    throw inputError(
      'BATCH_NOT_FOUND',
      `Batch "${batchId}" not found`,
      'Check the batch ID or run: sdlab batch generate --mode <id>'
    );
  }

  return JSON.parse(readFileSync(manifestPath, 'utf-8'));
}

/**
 * List all batches for a project.
 */
export function listBatches(projectRoot) {
  const batchesDir = getBatchesDir(projectRoot);
  if (!existsSync(batchesDir)) return [];

  return readdirSync(batchesDir, { withFileTypes: true })
    .filter(e => e.isDirectory() && e.name.startsWith('batch_'))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(e => e.name);
}
