/**
 * Re-ingest selected outputs as new candidate records.
 *
 * Selected outputs re-enter the project as generated candidates
 * with full provenance. They go through the same review and
 * canon-binding flow as everything else. No bypass.
 */

import { writeFile, mkdir, copyFile, rename, unlink } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { getRunsDir } from './paths.js';
import { getBatchesDir } from './batch-runs.js';
import { getSelectionsDir, loadSelection } from './selections.js';
import { buildGeneratedProvenance } from './generated-provenance.js';
import { buildBaseRecord } from './records.js';
import { inputError } from './errors.js';

// SDL-H7: the only shape a selection id can ever legitimately have,
// mirroring generateSelectionId() in lib/selections.js (selection_<date>_<seq>,
// same prefix/date/seq scheme as run/batch ids). Validated BEFORE the id is
// used anywhere — including before loadSelection(), which does its own
// unguarded join — so a traversal payload never reaches the filesystem, and
// before the join at `selectionDir` below, which this module writes
// provenance.jsonl into. A mismatch reuses loadSelection's own
// SELECTION_NOT_FOUND shape (not a distinct code) because no real selection
// can ever have an id outside this shape.
const SELECTION_ID_RE = /^selection_\d{4}-\d{2}-\d{2}_\d{3}$/;

/**
 * B03: atomic write helper — write temp + rename, mirroring the same
 * temp-file-then-rename checkpoint pattern lib/batch-runs.js uses for its
 * per-slot manifest checkpoint. Rename is atomic on a single filesystem, so
 * a crash mid-write can never leave a half-written provenance.jsonl in
 * place of a good one.
 */
async function atomicWriteText(targetPath, text) {
  const tmpPath = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  try {
    await writeFile(tmpPath, text);
    await rename(tmpPath, targetPath);
  } catch (err) {
    try { await unlink(tmpPath); } catch { /* ignore */ }
    throw err;
  }
}

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
  if (typeof selectionId !== 'string' || !SELECTION_ID_RE.test(selectionId)) {
    throw inputError(
      'SELECTION_NOT_FOUND',
      `Selection "${selectionId}" not found`,
      'Check the selection ID or run: sdlab select --run <id> --approve <files>',
    );
  }

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

  // B03: provenance.jsonl is now built incrementally — checkpointed (atomic
  // full-rewrite, temp+rename) after every item — instead of accumulated in
  // memory and overwritten once at the end. `provenanceLines` seeds from
  // whatever is ALREADY on disk (e.g. left by an interrupted prior run of
  // this same selection) so: (a) a rerun never duplicates a line for a
  // record it already logged, and (b) a partial rerun can never ERASE lines
  // a previous call already committed — the old end-of-run `writeFile`
  // overwrote with only the CURRENT call's accumulator, so a second call
  // touching fewer items than the first could silently wipe out provenance
  // the first call had already written to disk.
  const provenancePath = join(selectionDir, 'provenance.jsonl');
  const provenanceLines = [];
  const seenProvenanceIds = new Set();
  if (existsSync(provenancePath)) {
    for (const line of readFileSync(provenancePath, 'utf-8').split('\n')) {
      if (!line.trim()) continue;
      provenanceLines.push(line);
      try {
        const parsed = JSON.parse(line);
        if (parsed?.record_id) seenProvenanceIds.add(parsed.record_id);
      } catch {
        // Tolerate a corrupt/partial trailing line from a prior crash —
        // keep it verbatim rather than dropping it, just don't index it.
      }
    }
  }

  /**
   * Checkpoint one provenance line: skips dryRun, and skips a record_id
   * that's already logged (idempotent — safe to call on both the fresh-write
   * path and the skip/backfill path below).
   */
  async function checkpointProvenance(recordId, prov) {
    if (dryRun) return;
    if (seenProvenanceIds.has(recordId)) return;
    provenanceLines.push(JSON.stringify({ record_id: recordId, ...prov }));
    seenProvenanceIds.add(recordId);
    await atomicWriteText(provenancePath, provenanceLines.join('\n') + '\n');
  }

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

    // Resolve the run manifest for this item + build its provenance BEFORE
    // the existsSync check below — B03: a skipped (already-created) item
    // still needs its provenance backfilled if an earlier interrupted run
    // stopped short of appending it, so this can't be gated behind "the
    // record is new".
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

    if (existsSync(recordPath)) {
      // B03: the record already landed on disk (this item was completed by
      // a prior, possibly-interrupted run of this same re-ingest). Backfill
      // its provenance line if that prior run never got to append one —
      // never let a record exist with no corresponding provenance entry.
      await checkpointProvenance(recordId, prov);
      skipped.push(recordId);
      continue;
    }

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
      // B03: checkpoint immediately after the record write (per-item,
      // matching lib/batch-runs.js's per-slot checkpoint pattern) — NOT
      // batched to the end of the run. A crash on item 120 of 200 must
      // leave provenance for 1-119 durably on disk, not lose it because
      // item 200 never finished.
      await checkpointProvenance(recordId, prov);
    }

    created.push(recordId);
  }

  return { created, skipped };
}
