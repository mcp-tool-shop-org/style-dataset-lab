/**
 * Re-ingest selected outputs as new candidate records.
 *
 * Selected outputs re-enter the project as generated candidates
 * with full provenance. They go through the same review and
 * canon-binding flow as everything else. No bypass.
 */

import { writeFile, mkdir, copyFile } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { getRunsDir } from './paths.js';
import { getBatchesDir } from './batch-runs.js';
import { getSelectionsDir, loadSelection } from './selections.js';
import { buildGeneratedProvenance } from './generated-provenance.js';
import { buildBaseRecord } from './records.js';
import { inputError } from './errors.js';

/**
 * Re-ingest a selection — creates candidate records from chosen outputs.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot
 * @param {string} opts.projectId
 * @param {string} opts.selectionId
 * @param {boolean} [opts.dryRun]
 * @returns {Promise<{created: string[], skipped: string[]}>}
 */
export async function reingestSelection({ projectRoot, projectId, selectionId, dryRun }) {
  const manifest = loadSelection(projectRoot, selectionId);

  if (!manifest.reingest_ready) {
    throw inputError(
      'SELECTION_NOT_READY',
      `Selection "${selectionId}" is not marked reingest_ready`,
      'Set reingest_ready: true in the selection manifest.',
    );
  }

  const selectionDir = join(getSelectionsDir(projectRoot), selectionId);
  const recordsDir = join(projectRoot, 'records');
  const inboxDir = join(projectRoot, 'inbox', 'generated');

  if (!dryRun) {
    await mkdir(recordsDir, { recursive: true });
    await mkdir(inboxDir, { recursive: true });
  }

  // Load source manifests for provenance
  const runsDir = getRunsDir(projectRoot);
  const runManifestCache = new Map();

  function getRunManifest(runId) {
    if (runManifestCache.has(runId)) return runManifestCache.get(runId);
    const mPath = join(runsDir, runId, 'manifest.json');
    if (!existsSync(mPath)) return null;
    const m = JSON.parse(readFileSync(mPath, 'utf-8'));
    runManifestCache.set(runId, m);
    return m;
  }

  let batchManifest = null;
  if (manifest.source_type === 'batch') {
    const bmPath = join(getBatchesDir(projectRoot), manifest.source_id, 'manifest.json');
    if (existsSync(bmPath)) {
      batchManifest = JSON.parse(readFileSync(bmPath, 'utf-8'));
    }
  }

  const created = [];
  const skipped = [];
  const provenanceLines = [];

  // D-010: use entries() — not indexOf() — to avoid O(n^2) behavior and
  // silent duplicate-ID bugs when manifest.items contains structurally
  // equal or repeated references. Assert uniqueness of generated IDs.
  const seenIds = new Set();
  for (const [i, item] of manifest.items.entries()) {
    const idx = String(i + 1).padStart(3, '0');
    const recordId = `gen_${selectionId}_${idx}`;
    if (seenIds.has(recordId)) {
      throw inputError(
        'REINGEST_DUPLICATE_RECORD_ID',
        `Duplicate record ID generated during re-ingest: ${recordId}`,
        'This indicates a bug in record ID derivation; report this along with the selection manifest.',
      );
    }
    seenIds.add(recordId);
    const recordPath = join(recordsDir, `${recordId}.json`);

    if (existsSync(recordPath)) {
      skipped.push(recordId);
      continue;
    }

    // Resolve the run manifest for this item
    let runManifest;
    if (manifest.source_type === 'run') {
      runManifest = getRunManifest(manifest.source_id);
    } else if (manifest.source_type === 'batch' && batchManifest) {
      // Find which run this slot belongs to
      const slotId = item.slot_or_output.split(':')[0];
      const slot = batchManifest.slots?.find(s => s.slot_id === slotId);
      if (slot) {
        runManifest = getRunManifest(slot.run_id);
      }
    }

    if (!runManifest) {
      // Fallback: minimal provenance
      runManifest = {
        run_id: manifest.source_id,
        brief_id: 'unknown',
        workflow_template_id: manifest.workflow_id || 'unknown',
        created_at: manifest.created_at,
      };
    }

    // Build provenance
    const prov = buildGeneratedProvenance({
      sourceType: manifest.source_type,
      sourceId: manifest.source_id,
      runManifest,
      batchManifest,
      item,
      projectRoot,
    });

    // Image source in selection/chosen/
    const srcImage = join(selectionDir, 'chosen', item.filename);
    const ext = extname(item.filename) || '.png';
    const destImage = `${recordId}${ext}`;
    const inboxPath = join(inboxDir, destImage);
    const assetPath = `inbox/generated/${destImage}`;

    // Get file size
    let fileBytes = 0;
    if (existsSync(srcImage)) {
      fileBytes = statSync(srcImage).size;
    }

    // Build record
    const record = buildBaseRecord(recordId, assetPath, {
      width: null,
      height: null,
      bytes: fileBytes,
    }, {
      source: 'generated',
      selection_id: selectionId,
      generation_provenance: prov,
    });

    record.schema_version = '2.2.0';

    // Tags
    const recordTags = ['generated', 'selected'];
    if (manifest.workflow_id) recordTags.push(manifest.workflow_id);
    if (manifest.subject_id) recordTags.push(manifest.subject_id);
    if (item.tags?.length) recordTags.push(...item.tags);
    record.tags = [...new Set(recordTags)];

    if (!dryRun) {
      // Copy image into inbox
      if (existsSync(srcImage)) {
        await copyFile(srcImage, inboxPath);
      }
      // Write record
      await writeFile(recordPath, JSON.stringify(record, null, 2) + '\n');
    }

    created.push(recordId);
    provenanceLines.push(JSON.stringify({ record_id: recordId, ...prov }));
  }

  // Write provenance log
  if (!dryRun && provenanceLines.length > 0) {
    await writeFile(
      join(selectionDir, 'provenance.jsonl'),
      provenanceLines.join('\n') + '\n',
    );
  }

  return { created, skipped };
}
