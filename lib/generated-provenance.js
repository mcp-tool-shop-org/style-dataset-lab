/**
 * Generated provenance builder — constructs the provenance block
 * attached to records created from selected run/batch outputs.
 *
 * Normalizes source context (run vs batch) into a single shape
 * that traces back through brief → workflow → seed → config.
 */

import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

/**
 * Build a generation provenance payload for a selected output.
 *
 * @param {Object} opts
 * @param {'run'|'batch'} opts.sourceType
 * @param {string} opts.sourceId — run_id or batch_id
 * @param {Object} opts.runManifest — the run manifest containing this output
 * @param {Object} [opts.batchManifest] — batch manifest if source is batch
 * @param {Object} opts.item — the selection item (slot_or_output, filename, seed)
 * @param {string} opts.projectRoot
 * @returns {Object} generation_provenance block
 */
export function buildGeneratedProvenance({
  sourceType,
  sourceId,
  runManifest,
  batchManifest,
  item,
  projectRoot,
}) {
  const prov = {
    source_type: sourceType,
    source_id: sourceId,
    run_id: runManifest.run_id,
    brief_id: runManifest.brief_id,
    workflow_id: runManifest.workflow_template_id,
    selected_filename: item.filename,
    generated_at: runManifest.created_at,
  };

  if (sourceType === 'batch' && batchManifest) {
    prov.batch_id = batchManifest.batch_id;
  }

  // Seed from the item or from the run manifest outputs
  if (item.seed !== undefined) {
    prov.seed = item.seed;
  } else if (runManifest.outputs) {
    const match = runManifest.outputs.find(o => o.filename === item.filename);
    if (match?.seed !== undefined) prov.seed = match.seed;
  }

  // Adapter target from run manifest
  if (runManifest.adapter_target) {
    prov.adapter_target = runManifest.adapter_target;
  }

  // Subject from run brief or batch manifest
  if (batchManifest?.subject_id) {
    prov.subject_id = batchManifest.subject_id;
  } else {
    // Try to read subject from brief
    const briefPath = join(projectRoot, 'briefs', `${runManifest.brief_id}.json`);
    if (existsSync(briefPath)) {
      try {
        const brief = JSON.parse(readFileSync(briefPath, 'utf-8'));
        if (brief.subject_id) prov.subject_id = brief.subject_id;
        if (brief.parent_brief_id) prov.parent_brief_id = brief.parent_brief_id;
      } catch { /* skip */ }
    }
  }

  // Config fingerprint — hash the run manifest for reproducibility tracing
  prov.config_fingerprint = createHash('sha256')
    .update(JSON.stringify({
      brief_id: runManifest.brief_id,
      workflow_template_id: runManifest.workflow_template_id,
      adapter_target: runManifest.adapter_target,
      seed_plan: runManifest.seed_plan,
    }))
    .digest('hex')
    .slice(0, 16);

  return prov;
}
