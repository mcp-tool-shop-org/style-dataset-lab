/**
 * Freeze block helpers — read/write the `freeze` block on a canon entry,
 * compute watch-field hashes for the witness chain (D1).
 *
 * The `freeze` block (schema v2.0.0+) is the sole freeze surface on canon
 * entries; the legacy `visual_locked_at` + `regen_policy` fields have been
 * removed per post-research D10. See
 * memory/freeze-tooling-research-2026-04-24.md for the full contract.
 */

import { createHash } from 'node:crypto';
import { getByPath } from './canon-build/load-config.js';

/**
 * The four legal freeze statuses. Entries without a `freeze` block behave
 * as `auto` (permissive default — see post-research D8).
 */
export const FREEZE_STATUSES = Object.freeze(['auto', 'frozen', 'soft-advisory', 'on-canon-change']);

/**
 * Read the normalized freeze status for an entry frontmatter.
 * Missing block / missing status / invalid value all collapse to `auto`.
 */
export function readFreezeStatus(frontmatter) {
  const status = frontmatter?.freeze?.status;
  if (typeof status !== 'string') return 'auto';
  if (!FREEZE_STATUSES.includes(status)) return 'auto';
  return status;
}

/**
 * Whether an entry's freeze status blocks a regen-like action outright.
 * `frozen` blocks. `soft-advisory` blocks unless the caller overrides via
 * --i-know + --reason. `auto` / `on-canon-change` do not block.
 */
export function freezeBlocksAction(status) {
  return status === 'frozen';
}

/**
 * Whether an entry's freeze status warrants a soft-advisory bypass path.
 */
export function freezeIsAdvisory(status) {
  return status === 'soft-advisory';
}

/**
 * Stable canonical JSON serialization for an object used as hash input.
 *
 * Sorts object keys; arrays preserve order (arrays are meaningful sequences).
 * Normalizes `undefined` → omitted. Bit-stability matters because the witness
 * chain compares hashes across builds — the same semantic value must hash
 * identically regardless of key insertion order or JSON formatting drift.
 */
export function canonicalize(value) {
  if (value === null) return 'null';
  if (value === undefined) return 'null';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalize).join(',') + ']';
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort();
    const parts = [];
    for (const k of keys) {
      if (value[k] === undefined) continue;
      parts.push(JSON.stringify(k) + ':' + canonicalize(value[k]));
    }
    return '{' + parts.join(',') + '}';
  }
  return 'null';
}

/**
 * Compute the watch-hash for an entry given its frontmatter, the list of
 * watched fields, and the schema version.
 *
 * The hash is sha256 of a canonical JSON representation of the watched
 * field values + the schema version. Any change to a watched field, or a
 * schema version bump, invalidates the hash.
 *
 * @param {Object} frontmatter — entry frontmatter object
 * @param {Array<string>} watchFields — dotted paths (e.g. "visual.silhouette_cue")
 * @param {string} schemaVersion — schema `version` string
 * @returns {string} 64-char hex sha256 digest
 */
export function computeWatchHash(frontmatter, watchFields, schemaVersion) {
  const payload = {
    schema_version: schemaVersion,
    watched: {},
  };
  for (const field of watchFields) {
    payload.watched[field] = getByPath(frontmatter, field) ?? null;
  }
  return createHash('sha256').update(canonicalize(payload)).digest('hex');
}

/**
 * Resolve the effective watch-field list for an entry.
 *
 * Precedence (entry override wins over build-config default):
 *   1. `frontmatter.freeze.watch_fields` if present + non-empty
 *   2. `buildConfig.freeze_watch_defaults[schemaName]` if present
 *   3. [] (empty — a freeze with no watch-fields stamps only the schema
 *      version, useful for "freeze but don't drift-check" intent)
 */
export function resolveWatchFields(frontmatter, schemaName, buildConfig) {
  const entryOverride = frontmatter?.freeze?.watch_fields;
  if (Array.isArray(entryOverride) && entryOverride.length > 0) {
    return entryOverride;
  }
  const defaults = buildConfig?.freeze_watch_defaults?.[schemaName];
  if (Array.isArray(defaults) && defaults.length > 0) {
    return defaults;
  }
  return [];
}

/**
 * Build a fresh freeze block for writing to an entry (canon freeze command).
 *
 * @param {Object} args
 * @param {string} args.status — 'frozen' | 'soft-advisory' | 'on-canon-change'
 * @param {string} args.lockedAtBuild — generated_from of the witness build
 * @param {string} [args.lockedAtCanonVersion]
 * @param {string} args.frozenBy
 * @param {string} args.frozenReason
 * @param {Array<string>} [args.watchFields]
 * @param {Array} [args.overrides] — existing override history (preserved on re-freeze)
 */
export function buildFreezeBlock({
  status,
  lockedAtBuild,
  lockedAtCanonVersion,
  frozenBy,
  frozenReason,
  watchFields,
  overrides,
}) {
  const block = { status };
  if (lockedAtBuild) block.locked_at_build = lockedAtBuild;
  if (lockedAtCanonVersion) block.locked_at_canon_version = lockedAtCanonVersion;
  if (frozenBy) block.frozen_by = frozenBy;
  if (frozenReason) block.frozen_reason = frozenReason;
  if (Array.isArray(watchFields) && watchFields.length) block.watch_fields = watchFields;
  if (Array.isArray(overrides) && overrides.length) block.overrides = overrides;
  return block;
}

/**
 * Append an override record to an entry's freeze.overrides[] list.
 * Denormalizes the event into the entry for glance-reading; the authoritative
 * source of truth is the append-only log at canon-build/freeze-events.jsonl.
 */
export function appendOverrideToFreezeBlock(freeze, override) {
  const next = { ...freeze };
  next.overrides = Array.isArray(freeze?.overrides) ? [...freeze.overrides, override] : [override];
  return next;
}
