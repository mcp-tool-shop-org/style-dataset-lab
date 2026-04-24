/**
 * Canonical dataset row shape.
 *
 * The single source-of-truth shape that adapters (generic-image-caption,
 * diffusers-lora, ai-toolkit) consume. Two producers feed this shape:
 *
 *   1. `canon-build` — emits rows to disk at
 *      `<project>/canon-build/<canon_sha>/dataset/<lane>-<partition>.jsonl`
 *      from the canon entity store (research D1, D2).
 *   2. `training-packages` — converts legacy records-path `{record, lane, group}`
 *      entries into rows in memory so the records flow keeps working while
 *      canon authoring catches up.
 *
 * Both paths produce rows the adapter cannot distinguish. This is D6:
 * adapters have one input contract, not two.
 *
 * The research deliverable pins the row schema. See
 * `memory/three-projection-build-research-2026-04-24.md` §Projection contracts.
 */

import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { buildCaption, deriveStyleTrigger } from './captions.js';

export const ROW_SCHEMA_VERSION = 'canon-build-dataset-1.0';

/**
 * Compute SHA-256 of a deterministic serialization of the inputs.
 * Used for `entry_hash` (cache key) when building rows from canon entries.
 */
export function hashRowInputs({ entryBody, schemaVersion, buildConfigJson, projectFingerprint }) {
  const h = createHash('sha256');
  h.update(entryBody || '');
  h.update('\0');
  h.update(schemaVersion || '');
  h.update('\0');
  h.update(buildConfigJson || '');
  h.update('\0');
  h.update(projectFingerprint || '');
  return h.digest('hex');
}

/**
 * Build a row from a legacy record object.
 *
 * The records flow (star-freight today) produces `{ record, lane, group }`
 * tuples via split + snapshot + canon-binding. Each tuple becomes one row.
 *
 * @param {Object} record — the records/<id>.json object
 * @param {string|null} lane — resolved lane (costume, environment, ...)
 * @param {string|null} group — resolved group (faction, region, ...)
 * @param {Object} profile — training profile (for caption + trigger)
 * @param {string} partition — train | val | test
 * @returns {Object|null} row, or null if the record has no asset_path
 */
export function recordToRow(record, lane, group, profile, partition) {
  if (!record?.id || !record.asset_path) return null;

  const trigger = deriveStyleTrigger(profile) || null;
  const caption = buildCaption(record, lane, group, profile);

  const row = {
    schema_version: ROW_SCHEMA_VERSION,
    generated_from: null,               // records path: no canon commit
    entity_id: record.id,
    schema_kind: 'record',              // legacy marker: not a canon entity
    entity_type: record.identity?.kind || null,
    lane,
    partition,
    asset_path: record.asset_path,
    caption,
    trigger,
    subject_filter_key: record.identity?.subject_name || record.id,
    forbidden_tokens: record.canon?.forbidden_inputs || [],
    pass_ratio: record.canon?.assertion_count > 0
      ? +(record.canon.pass_count / record.canon.assertion_count).toFixed(3)
      : null,
    group,
  };

  return row;
}

/**
 * Build a row from a canon entity + approved reference plate.
 *
 * The canon-build flow produces rows from canon entries. Each entry may
 * contribute one or more rows (one per approved reference plate × lane).
 *
 * @param {Object} args
 * @param {Object} args.entry — parsed canon entry (frontmatter object)
 * @param {string} args.schemaKind — monster | character | deity | location | relic
 * @param {string} args.assetPath — project-relative path to the approved plate
 * @param {string} args.lane — resolved lane
 * @param {string} args.caption — pre-rendered via buildCaption
 * @param {string|null} args.trigger — from the training profile that drove the plate
 * @param {string} args.partition — train | val | test (canon-build defaults to train)
 * @param {string} args.entryHash — SHA-256 of entry + schema_version + build_config + project_fingerprint
 * @param {string|null} args.generatedFrom — canon commit SHA or "content-sha:..." fallback
 */
export function canonEntryToRow({
  entry,
  schemaKind,
  assetPath,
  lane,
  caption,
  trigger,
  partition,
  entryHash,
  generatedFrom,
}) {
  const entityType = entry.kind
    || entry.species_tag
    || entry.location_type
    || entry.relic_type
    || entry.generation
    || null;

  return {
    schema_version: ROW_SCHEMA_VERSION,
    generated_from: generatedFrom,
    entity_id: entry.id,
    schema_kind: schemaKind,
    entity_type: entityType,
    lane,
    partition,
    asset_path: assetPath,
    caption,
    trigger,
    subject_filter_key: entry.id,
    forbidden_tokens: entry.forbidden_inputs || [],
    entry_hash: entryHash,
  };
}

/**
 * Read rows from a dataset.jsonl file.
 *
 * Parses each non-empty line as JSON; rejects the file if any row's
 * `schema_version` does not match ROW_SCHEMA_VERSION.
 *
 * @param {string} path — absolute path to dataset.jsonl
 * @returns {Promise<Array<Object>>} rows
 */
export async function readDatasetJsonl(path) {
  const text = await readFile(path, 'utf-8');
  const rows = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    let row;
    try {
      row = JSON.parse(line);
    } catch (err) {
      throw new Error(`readDatasetJsonl: line ${i + 1} of ${path} is not valid JSON (${err.message})`);
    }
    if (row.schema_version !== ROW_SCHEMA_VERSION) {
      throw new Error(
        `readDatasetJsonl: line ${i + 1} of ${path} has schema_version "${row.schema_version}" (expected "${ROW_SCHEMA_VERSION}")`
      );
    }
    rows.push(row);
  }
  return rows;
}

/**
 * Group rows by partition (train | val | test).
 * Rows with missing/unknown partition are grouped under an "other" key.
 */
export function groupRowsByPartition(rows) {
  const out = { train: [], val: [], test: [] };
  for (const row of rows) {
    const p = row.partition || 'other';
    if (!out[p]) out[p] = [];
    out[p].push(row);
  }
  return out;
}

/**
 * Filter rows for a training profile.
 *
 * Two filter axes:
 *   - lane-based: include row if row.lane ∈ profile.eligible_lanes
 *   - entity-based: include row if row.entity_id === profile.entity_id_scope
 *     (when entity_id_scope is set — per-character LoRA case, D8)
 *
 * Both filters compose: a per-character profile with both eligible_lanes and
 * entity_id_scope set applies both as AND. Zero filters = pass everything.
 */
export function filterRowsForProfile(rows, profile) {
  const eligibleLanes = profile.eligible_lanes;
  const entityScope = profile.entity_id_scope;

  return rows.filter((row) => {
    if (Array.isArray(eligibleLanes) && eligibleLanes.length > 0) {
      if (!eligibleLanes.includes(row.lane)) return false;
    }
    if (entityScope) {
      if (row.entity_id !== entityScope && row.subject_filter_key !== entityScope) {
        return false;
      }
    }
    return true;
  });
}

/**
 * Serialize a row to a stable JSONL line.
 * Key order is enforced by emitting known fields first, then alphabetized extras.
 */
export function serializeRow(row) {
  const knownOrder = [
    'schema_version', 'generated_from', 'entity_id', 'schema_kind', 'entity_type',
    'lane', 'partition', 'asset_path', 'caption', 'trigger',
    'subject_filter_key', 'forbidden_tokens', 'entry_hash', 'pass_ratio', 'group',
  ];
  const ordered = {};
  for (const key of knownOrder) {
    if (row[key] !== undefined) ordered[key] = row[key];
  }
  for (const key of Object.keys(row).sort()) {
    if (!knownOrder.includes(key)) ordered[key] = row[key];
  }
  return JSON.stringify(ordered);
}
