/**
 * Selection engine — approve outputs from runs or batches into
 * durable selection artifacts.
 *
 * A selection is a creative decision: what was chosen, why, and
 * where it came from. Re-ingest consumes selections; this module
 * only builds and stores the artifact.
 */

import { readFileSync, existsSync, readdirSync, mkdirSync, copyFileSync } from 'node:fs';
import { writeFile, mkdir, readFile } from 'node:fs/promises';
import { join, basename } from 'node:path';
import { getRunsDir } from './paths.js';
import { getBatchesDir } from './batch-runs.js';
import { inputError } from './errors.js';

// ─── Filename validation ─────────────────────────────────────────

const SAFE_FILENAME_RE = /^[A-Za-z0-9._-]+\.(png|webp|jpg|jpeg)$/i;

function assertSafeFilename(filename, context) {
  if (typeof filename !== 'string' || !SAFE_FILENAME_RE.test(filename)) {
    throw inputError(
      'UNSAFE_FILENAME',
      `Invalid filename "${filename}" in ${context}`,
      `Filenames must match letters/digits/dot/underscore/hyphen and end in .png/.webp/.jpg/.jpeg`,
    );
  }
}

// ─── Selection ID generation ─────────────────────────────────────

export function getSelectionsDir(projectRoot) {
  return join(projectRoot, 'selections');
}

// PB-008: tighten regex so partial matches (e.g. 'selection_<date>_001_wip')
// don't inflate the sequence. We require exactly 3 digits.
const SELECTION_SEQ_RE = /^(\d{3})$/;

export function generateSelectionId(selectionsDir) {
  const today = new Date().toISOString().slice(0, 10);
  const prefix = `selection_${today}_`;

  let maxSeq = 0;
  if (existsSync(selectionsDir)) {
    const existing = readdirSync(selectionsDir, { withFileTypes: true })
      .filter(e => e.isDirectory() && e.name.startsWith(prefix));
    for (const e of existing) {
      const seqStr = e.name.slice(prefix.length);
      const match = SELECTION_SEQ_RE.exec(seqStr);
      if (!match) continue;
      const seq = parseInt(match[1], 10);
      if (seq > maxSeq) maxSeq = seq;
    }
  }

  return `${prefix}${String(maxSeq + 1).padStart(3, '0')}`;
}

/**
 * PB-008: atomically claim the next selection ID by mkdir retry-on-EEXIST.
 * Races safely against a concurrent sdlab process — each one will land on
 * a unique sequence. Returns { selectionId, selectionDir }.
 *
 * Callers that already create the directory themselves can keep using
 * generateSelectionId; the atomic path is opt-in.
 */
export async function claimSelectionId(selectionsDir) {
  if (!existsSync(selectionsDir)) {
    mkdirSync(selectionsDir, { recursive: true });
  }
  for (let attempt = 0; attempt < 25; attempt++) {
    const candidate = generateSelectionId(selectionsDir);
    const dir = join(selectionsDir, candidate);
    try {
      mkdirSync(dir); // throws EEXIST if a concurrent process already claimed it
      return { selectionId: candidate, selectionDir: dir };
    } catch (err) {
      if (err.code === 'EEXIST') continue;
      throw err;
    }
  }
  throw inputError(
    'SELECTION_ID_CLAIM_FAILED',
    'Could not claim a unique selection ID after 25 attempts',
    'Another sdlab process may be writing selections in a tight loop. Try again.'
  );
}

// ─── Run selection ───────────────────────────────────────────────

/**
 * Create a selection from a single run.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot
 * @param {string} opts.projectId
 * @param {string} opts.runId
 * @param {string[]} opts.approvedFiles — filenames to approve (e.g. ['001.png', '003.png'])
 * @param {string} [opts.reason]
 * @param {string[]} [opts.tags]
 * @returns {Promise<Object>} selection manifest
 */
export async function createSelectionFromRun({
  projectRoot, projectId, runId, approvedFiles, reason, tags,
}) {
  const runsDir = getRunsDir(projectRoot);
  const runDir = join(runsDir, runId);
  const manifestPath = join(runDir, 'manifest.json');

  if (!existsSync(manifestPath)) {
    throw inputError('RUN_NOT_FOUND', `Run "${runId}" not found`, 'Check the run ID.');
  }

  const runManifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
  const outputsDir = join(runDir, 'outputs');

  // Validate all approved files exist
  for (const file of approvedFiles) {
    assertSafeFilename(file, `approvedFiles for run ${runId}`);
    if (!existsSync(join(outputsDir, file))) {
      throw inputError(
        'OUTPUT_NOT_FOUND',
        `Output "${file}" not found in ${runId}/outputs/`,
        `Available: ${readdirSync(outputsDir).filter(f => f.endsWith('.png')).join(', ') || '(none)'}`,
      );
    }
  }

  // Create selection directory
  const selectionsDir = getSelectionsDir(projectRoot);
  const selectionId = generateSelectionId(selectionsDir);
  const selectionDir = join(selectionsDir, selectionId);
  await mkdir(join(selectionDir, 'chosen'), { recursive: true });

  // Copy chosen files
  const items = [];
  for (let i = 0; i < approvedFiles.length; i++) {
    const file = approvedFiles[i];
    const destName = `sel_${String(i + 1).padStart(3, '0')}.png`;
    copyFileSync(join(outputsDir, file), join(selectionDir, 'chosen', destName));

    // Find seed from run manifest
    const outputEntry = runManifest.outputs?.find(o => o.filename === file);
    items.push({
      slot_or_output: file,
      filename: destName,
      seed: outputEntry?.seed,
      reason: reason || 'selected',
      tags: tags || [],
    });
  }

  // Build selection manifest
  const manifest = {
    selection_id: selectionId,
    project_id: projectId,
    source_type: 'run',
    source_id: runId,
    workflow_id: runManifest.workflow_template_id,
    created_at: new Date().toISOString(),
    items,
    reingest_ready: true,
  };

  // Attach subject from brief if available
  const briefPath = join(runDir, 'brief.json');
  if (existsSync(briefPath)) {
    try {
      const brief = JSON.parse(readFileSync(briefPath, 'utf-8'));
      if (brief.subject_id) manifest.subject_id = brief.subject_id;
    } catch { /* skip */ }
  }

  return { selectionId, selectionDir, manifest, runManifest };
}

// ─── Batch selection ─────────────────────────────────────────────

/**
 * Create a selection from a batch.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot
 * @param {string} opts.projectId
 * @param {string} opts.batchId
 * @param {Array<{slotId: string, filename: string}>} opts.approvedSlots
 * @param {string} [opts.reason]
 * @param {string[]} [opts.tags]
 * @returns {Promise<Object>} selection manifest
 */
export async function createSelectionFromBatch({
  projectRoot, projectId, batchId, approvedSlots, reason, tags,
}) {
  const batchesDir = getBatchesDir(projectRoot);
  const batchDir = join(batchesDir, batchId);
  const batchManifestPath = join(batchDir, 'manifest.json');

  if (!existsSync(batchManifestPath)) {
    throw inputError('BATCH_NOT_FOUND', `Batch "${batchId}" not found`, 'Check the batch ID.');
  }

  const batchManifest = JSON.parse(readFileSync(batchManifestPath, 'utf-8'));
  const runsDir = getRunsDir(projectRoot);

  // Build slot → run lookup
  const slotRunMap = new Map();
  for (const slot of batchManifest.slots || []) {
    slotRunMap.set(slot.slot_id, slot);
  }

  // Validate each approved slot
  const runManifests = new Map();
  for (const { slotId, filename } of approvedSlots) {
    assertSafeFilename(filename, `approvedSlots for batch ${batchId}`);
    const slot = slotRunMap.get(slotId);
    if (!slot) {
      throw inputError(
        'SLOT_NOT_FOUND',
        `Slot "${slotId}" not found in batch ${batchId}`,
        `Available: ${[...slotRunMap.keys()].join(', ')}`,
      );
    }

    const runDir = join(runsDir, slot.run_id);
    const outputPath = join(runDir, 'outputs', filename);
    if (!existsSync(outputPath)) {
      throw inputError(
        'OUTPUT_NOT_FOUND',
        `Output "${filename}" not found in ${slot.run_id}/outputs/`,
        `Check the filename.`,
      );
    }

    // Cache run manifests
    if (!runManifests.has(slot.run_id)) {
      const rmPath = join(runDir, 'manifest.json');
      if (existsSync(rmPath)) {
        runManifests.set(slot.run_id, JSON.parse(readFileSync(rmPath, 'utf-8')));
      }
    }
  }

  // Create selection directory
  const selectionsDir = getSelectionsDir(projectRoot);
  const selectionId = generateSelectionId(selectionsDir);
  const selectionDir = join(selectionsDir, selectionId);
  await mkdir(join(selectionDir, 'chosen'), { recursive: true });

  // Copy chosen files and build items
  const items = [];
  for (let i = 0; i < approvedSlots.length; i++) {
    const { slotId, filename } = approvedSlots[i];
    const slot = slotRunMap.get(slotId);
    const runDir = join(runsDir, slot.run_id);
    const destName = `sel_${String(i + 1).padStart(3, '0')}.png`;

    copyFileSync(join(runDir, 'outputs', filename), join(selectionDir, 'chosen', destName));

    const rm = runManifests.get(slot.run_id);
    const outputEntry = rm?.outputs?.find(o => o.filename === filename);

    items.push({
      slot_or_output: `${slotId}:${filename}`,
      filename: destName,
      seed: outputEntry?.seed,
      reason: reason || `selected from slot ${slot.label || slotId}`,
      tags: tags || [],
    });
  }

  const manifest = {
    selection_id: selectionId,
    project_id: projectId,
    source_type: 'batch',
    source_id: batchId,
    workflow_id: batchManifest.mode_id,
    created_at: new Date().toISOString(),
    items,
    reingest_ready: true,
  };

  if (batchManifest.subject_id) manifest.subject_id = batchManifest.subject_id;

  return { selectionId, selectionDir, manifest, batchManifest, runManifests };
}

// ─── Save / Load / List ──────────────────────────────────────────

/**
 * Save a selection manifest + summary to disk.
 */
export async function saveSelection(selectionDir, manifest) {
  await writeFile(
    join(selectionDir, 'manifest.json'),
    JSON.stringify(manifest, null, 2) + '\n',
  );

  // Summary JSON
  await writeFile(
    join(selectionDir, 'summary.json'),
    JSON.stringify({
      selection_id: manifest.selection_id,
      source_type: manifest.source_type,
      source_id: manifest.source_id,
      workflow_id: manifest.workflow_id,
      subject_id: manifest.subject_id,
      items: manifest.items.length,
      reingest_ready: manifest.reingest_ready,
      created_at: manifest.created_at,
    }, null, 2) + '\n',
  );

  // Summary markdown
  const lines = [
    `# Selection: ${manifest.selection_id}`,
    '',
    `**Source:** ${manifest.source_type} \`${manifest.source_id}\``,
    `**Workflow:** ${manifest.workflow_id || '—'}`,
  ];
  if (manifest.subject_id) lines.push(`**Subject:** ${manifest.subject_id}`);
  lines.push(`**Created:** ${manifest.created_at}`);
  lines.push(`**Re-ingest ready:** ${manifest.reingest_ready ? 'yes' : 'no'}`);
  lines.push('');
  lines.push('## Chosen outputs');
  lines.push('');
  lines.push('| # | Source | File | Seed | Reason |');
  lines.push('|---|--------|------|------|--------|');
  for (let i = 0; i < manifest.items.length; i++) {
    const item = manifest.items[i];
    lines.push(
      `| ${i + 1} | ${item.slot_or_output} | ${item.filename} | ${item.seed ?? '—'} | ${item.reason} |`,
    );
  }
  lines.push('');
  if (manifest.items.some(it => it.tags?.length)) {
    lines.push('## Tags');
    for (const item of manifest.items) {
      if (item.tags?.length) {
        lines.push(`- ${item.filename}: ${item.tags.join(', ')}`);
      }
    }
    lines.push('');
  }
  await writeFile(join(selectionDir, 'summary.md'), lines.join('\n'));
}

/**
 * Load a selection manifest by ID.
 */
export function loadSelection(projectRoot, selectionId) {
  const selectionDir = join(getSelectionsDir(projectRoot), selectionId);
  const manifestPath = join(selectionDir, 'manifest.json');
  if (!existsSync(manifestPath)) {
    throw inputError(
      'SELECTION_NOT_FOUND',
      `Selection "${selectionId}" not found`,
      'Check the selection ID or run: sdlab select --run <id> --approve <files>',
    );
  }
  return JSON.parse(readFileSync(manifestPath, 'utf-8'));
}

/**
 * List all selections in a project.
 */
export function listSelections(projectRoot) {
  const dir = getSelectionsDir(projectRoot);
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter(e => e.isDirectory() && e.name.startsWith('selection_'))
    .map(e => e.name)
    .sort();
}
