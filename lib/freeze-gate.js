/**
 * Freeze enforcement gate (D3).
 *
 * Called from CLI commands before any write to a canon-bound asset or record.
 * Semantics:
 *   - frozen         → block outright (CANON_ENTRY_FROZEN)
 *   - soft-advisory  → block unless --i-know + --reason; on override, append
 *                      a 'bypass' event to freeze-events.jsonl and proceed
 *   - auto           → no block
 *   - on-canon-change → no block at write time; canon-build surfaces drift
 *                      in its summary output (enforcement lives at the build
 *                      boundary, not the CLI boundary, because drift is a
 *                      build-observable condition)
 *
 * The canon reverse-map helpers resolve an action's identifier (subject id,
 * asset path) to a canon entry so the gate can look up its freeze state.
 * Actions without a canon binding (prompt-pack-driven generate, reingest of
 * un-bound generated outputs) skip the gate naturally: no entry = nothing
 * to protect.
 */

import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { loadBuildConfig } from './canon-build/load-config.js';
import { loadCanonEntriesInDir, entryId } from './canon-build/load-entry.js';
import { readFreezeStatus } from './freeze-stamp.js';
import { appendEvent } from './freeze-events.js';
import { inputError } from './errors.js';

/**
 * Load every canon entry in a project, keyed by schema.
 *
 * Returns a flat array of `{ entry, schemaName }` objects.
 * Returns [] (no-op) when the project has no canon-build config — meaning
 * the project isn't canon-integrated yet, so the gate has nothing to enforce.
 */
export async function loadAllCanonEntries(projectRoot) {
  const configPath = join(projectRoot, 'canon-build', 'config.json');
  if (!existsSync(configPath)) return [];
  let config;
  try {
    config = await loadBuildConfig(configPath, projectRoot);
  } catch {
    // Invalid config → degrade to "no gate" rather than blocking every write.
    // The operator will hit the config error on `sdlab canon build`.
    return [];
  }
  const entries = [];
  for (const [schemaName, subdir] of Object.entries(config.entity_dirs)) {
    const dir = join(config.canon_root, subdir);
    const loaded = await loadCanonEntriesInDir(dir);
    for (const entry of loaded) {
      entries.push({ entry, schemaName });
    }
  }
  return entries;
}

/**
 * Find the canon entry whose `id` matches the given subject identifier.
 * Returns { entry, schemaName } or null.
 */
export async function resolveEntryBySubject(projectRoot, subjectId) {
  if (!subjectId) return null;
  const all = await loadAllCanonEntries(projectRoot);
  const hit = all.find(({ entry }) => entryId(entry) === subjectId);
  return hit || null;
}

/**
 * Find the canon entry whose `visual.reference_plate_uri` (or top-level
 * `reference_plate_uri`, for monsters) equals the given asset path.
 * Returns { entry, schemaName } or null.
 */
export async function resolveEntryByAssetPath(projectRoot, assetPath) {
  if (!assetPath) return null;
  const all = await loadAllCanonEntries(projectRoot);
  const normalized = assetPath.replace(/\\/g, '/');
  const hit = all.find(({ entry }) => {
    const fm = entry.frontmatter;
    const plate = (fm.visual?.reference_plate_uri || fm.reference_plate_uri || '').replace(/\\/g, '/');
    return plate && plate === normalized;
  });
  return hit || null;
}

/**
 * Core gate. Throws CANON_ENTRY_FROZEN on block; on soft-advisory bypass,
 * appends a 'bypass' event and returns without throwing.
 *
 * @param {Object} args
 * @param {string} args.projectRoot
 * @param {Object|null} args.resolved — { entry, schemaName } or null
 * @param {string} args.action — short verb for error context ("generate", "painterly", "curate", ...)
 * @param {boolean} [args.allowSoftAdvisoryBypass] — the command supports --i-know
 * @param {string} [args.bypassReason] — value of --reason when bypassing
 * @param {string} [args.by] — who is invoking (default 'mike')
 */
export async function assertNotFrozen({
  projectRoot,
  resolved,
  action,
  allowSoftAdvisoryBypass = false,
  bypassReason = null,
  by = 'mike',
}) {
  if (!resolved || !resolved.entry) return; // nothing canon-bound; no gate
  const fm = resolved.entry.frontmatter;
  const status = readFreezeStatus(fm);
  const id = entryId(resolved.entry);

  if (status === 'frozen') {
    throw inputError(
      'CANON_ENTRY_FROZEN',
      `Canon entry "${id}" is frozen; "${action}" refuses to proceed.`,
      `Unfreeze with: sdlab canon unfreeze ${id} --reason "<why>". The override will be appended to canon-build/freeze-events.jsonl as an audit record.`,
    );
  }

  if (status === 'soft-advisory') {
    if (!allowSoftAdvisoryBypass) {
      throw inputError(
        'CANON_ENTRY_FROZEN',
        `Canon entry "${id}" is soft-advisory frozen; "${action}" refuses to proceed.`,
        `This command does not support a --i-know bypass. Run "sdlab canon unfreeze ${id} --reason \\"<why>\\"" for a proper unfreeze, or pick a command that accepts --i-know.`,
      );
    }
    if (!bypassReason) {
      throw inputError(
        'CANON_ENTRY_FROZEN',
        `Canon entry "${id}" is soft-advisory frozen; "${action}" requires --i-know AND --reason to bypass.`,
        `Re-run with: --i-know --reason "<short reason>". The bypass will be logged to canon-build/freeze-events.jsonl.`,
      );
    }
    // Bypass allowed — log and proceed.
    await appendEvent(projectRoot, {
      type: 'bypass',
      entity_id: id,
      schema_kind: resolved.schemaName?.replace('.schema.json', ''),
      by,
      reason: bypassReason,
      prior_status: 'soft-advisory',
      new_status: 'soft-advisory',
    });
    return;
  }

  // auto and on-canon-change: no write-side block.
}

/**
 * Convenience wrapper: resolve by subject id, then gate.
 */
export async function assertNotFrozenBySubject(projectRoot, subjectId, options = {}) {
  const resolved = await resolveEntryBySubject(projectRoot, subjectId);
  return assertNotFrozen({ projectRoot, resolved, ...options });
}

/**
 * Convenience wrapper: resolve by asset_path, then gate.
 */
export async function assertNotFrozenByAssetPath(projectRoot, assetPath, options = {}) {
  const resolved = await resolveEntryByAssetPath(projectRoot, assetPath);
  return assertNotFrozen({ projectRoot, resolved, ...options });
}
