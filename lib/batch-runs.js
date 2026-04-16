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

import { writeFile, mkdir, copyFile } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { getProjectRoot, getRunsDir } from './paths.js';
import { executeRun } from './adapters/comfyui-runner.js';
import { saveRunSummary } from './run-summary.js';
import { log, info, warn } from './log.js';
import { inputError } from './errors.js';

/**
 * Return the batches directory for a project.
 */
export function getBatchesDir(projectRoot) {
  return join(projectRoot, 'batches');
}

/**
 * Generate batch ID: batch_YYYY-MM-DD_NNN
 */
export function generateBatchId(batchesDir) {
  const today = new Date().toISOString().slice(0, 10);
  const prefix = `batch_${today}_`;

  let maxSeq = 0;
  if (existsSync(batchesDir)) {
    const existing = readdirSync(batchesDir, { withFileTypes: true })
      .filter(e => e.isDirectory() && e.name.startsWith(prefix));
    for (const e of existing) {
      const seqStr = e.name.slice(prefix.length);
      const seq = parseInt(seqStr, 10);
      if (!isNaN(seq) && seq > maxSeq) maxSeq = seq;
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
  const results = [];

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
      // Pick the first successful output as the selected one
      selected_output: manifest.outputs.find(o =>
        o.status === 'ok' || o.status === 'dry_run'
      )?.filename || null,
    });
  }

  return results;
}

/**
 * Save a batch manifest.
 */
export async function saveBatchManifest(batchDir, manifest) {
  await writeFile(
    join(batchDir, 'manifest.json'),
    JSON.stringify(manifest, null, 2) + '\n'
  );
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
