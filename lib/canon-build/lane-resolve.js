/**
 * Lane resolution for canon entries (D3 + D9).
 *
 * The build config declares, per schema, how to resolve an entry's lane:
 *   - { source: "constant", value: "creature" } → always that value
 *   - { source: "field", field: "visual.art_lane" } → read that dotted path
 *     from the entry's frontmatter
 *
 * Unmapped entries throw a structured error so an operator can fix the
 * source of truth rather than letting the build silently drop a row.
 */

import { inputError } from '../errors.js';
import { getByPath } from './load-config.js';

/**
 * Resolve the lane for a single entry.
 *
 * @param {Object} entry — loaded canon entry ({ frontmatter, filePath, ... })
 * @param {string} schemaName — e.g. "monster.schema.json"
 * @param {Object} schemaToLane — config.schema_to_lane rule object
 * @returns {string} resolved lane
 * @throws SdlabError CANON_LANE_UNMAPPED when resolution fails
 */
export function resolveLane(entry, schemaName, schemaToLane) {
  const rule = schemaToLane[schemaName];
  if (!rule) {
    throw inputError(
      'CANON_LANE_UNMAPPED',
      `canon-build config has no schema_to_lane rule for "${schemaName}" (entry ${entry.filePath})`,
      `Add a rule to canon-build/config.json — e.g. { "source": "field", "field": "visual.art_lane" } or { "source": "constant", "value": "<lane>" }.`,
    );
  }

  if (rule.source === 'constant') {
    return rule.value;
  }

  if (rule.source === 'field') {
    const value = getByPath(entry.frontmatter, rule.field);
    if (value === undefined || value === null || value === '') {
      throw inputError(
        'CANON_LANE_UNMAPPED',
        `entry ${entry.filePath} has no value at "${rule.field}" (required to resolve lane for schema "${schemaName}")`,
        `Add ${rule.field} to the entry's frontmatter, or switch the config rule to source: "constant" if the schema should use a fixed lane.`,
      );
    }
    if (typeof value !== 'string') {
      throw inputError(
        'CANON_LANE_UNMAPPED',
        `entry ${entry.filePath} value at "${rule.field}" is not a string (got ${typeof value})`,
        'Lane resolution expects a string. Check the schema definition for this field.',
      );
    }
    return value;
  }

  // load-config.js already rejects unknown sources; this is defense-in-depth.
  throw inputError(
    'CANON_LANE_UNMAPPED',
    `schema_to_lane rule for "${schemaName}" has unsupported source "${rule.source}"`,
    'Valid sources: "field" or "constant".',
  );
}
