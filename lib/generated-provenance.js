/**
 * Generated provenance builder — constructs the provenance block
 * attached to records created from selected run/batch outputs.
 *
 * Normalizes source context (run vs batch) into a single shape
 * that traces back through brief → workflow → seed → config,
 * plus G4 (model licences), G5 (owner + CC-BY-4.0), and G6 (canon link).
 */

import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { warn } from './log.js';
import { STUDIO_OWNER, STUDIO_LICENCE } from './records.js';

/**
 * Resolve `{ canon_sha, entry_id, entry_sha256 }` from explicit metadata or
 * the project's `canon-build/<canon_sha>/manifest.json` (`per_entity_hashes`).
 */
export function resolveCanonLink(
  projectRoot,
  {
    canonSha = null,
    entryId = null,
    entrySha256 = null,
    subjectId = null,
    runManifest = null,
    batchManifest = null,
    item = null,
    brief = null,
  } = {},
) {
  let resolvedCanonSha =
    canonSha ||
    item?.canon_sha ||
    runManifest?.canon_sha ||
    batchManifest?.canon_sha ||
    brief?.canon_sha ||
    null;

  if (!resolvedCanonSha && projectRoot) {
    const currentPath = join(projectRoot, 'canon-build', 'CURRENT');
    if (existsSync(currentPath)) {
      try {
        const raw = readFileSync(currentPath, 'utf-8').trim();
        if (raw) resolvedCanonSha = raw;
      } catch {
        // best-effort read of CURRENT pointer
      }
    }
  }

  let resolvedEntryId =
    entryId ||
    item?.entry_id ||
    runManifest?.entry_id ||
    batchManifest?.entry_id ||
    brief?.entry_id ||
    subjectId ||
    item?.subject_id ||
    runManifest?.subject_id ||
    batchManifest?.subject_id ||
    brief?.subject_id ||
    null;

  let resolvedEntrySha =
    entrySha256 ||
    item?.entry_sha256 ||
    runManifest?.entry_sha256 ||
    batchManifest?.entry_sha256 ||
    brief?.entry_sha256 ||
    null;

  if (resolvedCanonSha && projectRoot) {
    const manifestPath = join(projectRoot, 'canon-build', resolvedCanonSha, 'manifest.json');
    if (existsSync(manifestPath)) {
      try {
        const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
        const hashes = manifest.per_entity_hashes || {};
        if (resolvedEntryId) {
          if (hashes[resolvedEntryId]) {
            resolvedEntrySha = resolvedEntrySha || hashes[resolvedEntryId];
          } else {
            const suffix = `/${resolvedEntryId}`;
            const matchKey = Object.keys(hashes).find((k) => k.endsWith(suffix));
            if (matchKey) {
              resolvedEntryId = matchKey;
              resolvedEntrySha = resolvedEntrySha || hashes[matchKey];
            }
          }
        } else {
          const keys = Object.keys(hashes);
          if (keys.length === 1) {
            resolvedEntryId = keys[0];
            resolvedEntrySha = resolvedEntrySha || hashes[keys[0]];
          }
        }
      } catch {
        // best-effort manifest lookup
      }
    }
  }

  if (!resolvedCanonSha && !resolvedEntryId && !resolvedEntrySha) {
    return null;
  }

  return {
    canon_sha: resolvedCanonSha,
    entry_id: resolvedEntryId,
    entry_sha256: resolvedEntrySha,
  };
}

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
 * @param {string} [opts.canonSha]
 * @param {string} [opts.entryId]
 * @param {string} [opts.entrySha256]
 * @returns {Object} generation_provenance block
 */
export function buildGeneratedProvenance({
  sourceType,
  sourceId,
  runManifest,
  batchManifest,
  item,
  projectRoot,
  canonSha = null,
  entryId = null,
  entrySha256 = null,
}) {
  const prov = {
    owner: STUDIO_OWNER,
    licence: STUDIO_LICENCE,
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

  const matchedOutput = runManifest.outputs
    ? runManifest.outputs.find((o) => o.filename === item.filename)
    : null;

  // Seed from the item or from the run manifest outputs
  if (item.seed !== undefined) {
    prov.seed = item.seed;
  } else if (matchedOutput?.seed !== undefined) {
    prov.seed = matchedOutput.seed;
  }

  // Prompt and prompt_sha256 when available on the item or output
  const promptText = item.prompt ?? matchedOutput?.prompt ?? null;
  if (typeof promptText === 'string' && promptText.length > 0) {
    prov.prompt = promptText;
    prov.prompt_sha256 = 'sha256:' + createHash('sha256').update(promptText).digest('hex');
  } else if (item.prompt_sha256 || matchedOutput?.prompt_sha256) {
    prov.prompt_sha256 = item.prompt_sha256 || matchedOutput.prompt_sha256;
  }

  // Comfy workflow sha and model licences from run manifest pinning (G4, G9)
  const wfSha = runManifest.pinning?.comfy_workflow_sha ?? runManifest.comfy_workflow_sha ?? null;
  if (wfSha) {
    prov.comfy_workflow_sha = wfSha;
  }
  if (runManifest.pinning?.models || runManifest.pinning?.loras) {
    prov.model_licences = {
      cc_by_4_eligible: runManifest.pinning.cc_by_4_eligible ?? null,
      models: Object.fromEntries(
        Object.entries(runManifest.pinning.models || {}).map(([role, m]) => [
          role,
          {
            name: m.name,
            sha256: m.sha256 ?? null,
            licence_id: m.licence_id ?? m.licence?.spdx_id ?? null,
            licence_url: m.licence_url ?? m.licence?.url ?? null,
            date_read: m.date_read ?? m.licence?.verified_at ?? null,
          },
        ]),
      ),
      loras: (runManifest.pinning.loras || []).map((l) => ({
        name: l.name,
        weight: l.weight ?? 1.0,
        sha256: l.sha256 ?? null,
        licence_id: l.licence_id ?? l.licence?.spdx_id ?? null,
        licence_url: l.licence_url ?? l.licence?.url ?? null,
        date_read: l.date_read ?? l.licence?.verified_at ?? null,
      })),
    };
  }

  // Adapter target from run manifest
  if (runManifest.adapter_target) {
    prov.adapter_target = runManifest.adapter_target;
  }

  let parsedBrief = null;
  // Subject from run brief or batch manifest
  if (batchManifest?.subject_id) {
    prov.subject_id = batchManifest.subject_id;
  } else if (projectRoot && runManifest.brief_id) {
    // Try to read subject from brief
    const briefPath = join(projectRoot, 'briefs', `${runManifest.brief_id}.json`);
    if (existsSync(briefPath)) {
      try {
        const brief = JSON.parse(readFileSync(briefPath, 'utf-8'));
        parsedBrief = brief;
        if (brief.subject_id) prov.subject_id = brief.subject_id;
        if (brief.parent_brief_id) prov.parent_brief_id = brief.parent_brief_id;
      } catch (err) {
        // B08: the brief exists but couldn't be read/parsed (e.g. a
        // concurrent mid-write) — lineage is genuinely UNKNOWN here, not
        // merely absent. Surface it instead of silently shipping
        // provenance with no lineage and no signal that anything failed.
        warn(`generated-provenance: brief ${briefPath} could not be read (${err.message}) — lineage_incomplete`);
        prov.lineage_incomplete = true;
      }
    } else {
      // B08: no brief on disk at all for this run — the same "genuinely
      // unknown" lineage state as an unreadable brief, not a normal
      // "this brief simply has no subject_id" case (that one is NOT
      // flagged — see the brief-read-fine-but-no-subject_id branch above).
      warn(`generated-provenance: brief not found at ${briefPath} — lineage_incomplete`);
      prov.lineage_incomplete = true;
    }
  }

  const canonLink = resolveCanonLink(projectRoot, {
    canonSha,
    entryId,
    entrySha256,
    subjectId: prov.subject_id,
    runManifest,
    batchManifest,
    item,
    brief: parsedBrief,
  });
  if (canonLink) {
    prov.canon_sha = canonLink.canon_sha;
    prov.entry_id = canonLink.entry_id;
    prov.entry_sha256 = canonLink.entry_sha256;
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
