/**
 * canon-build/config.json loader + validator.
 *
 * The build config declares:
 *   - canon_root: absolute (or project-relative) path to the canon directory
 *   - schema_dir: absolute path to the schemas directory
 *   - entity_dirs: schema filename → subdirectory under canon_root
 *   - schema_to_lane: per-schema lane resolution (D3 / D9)
 *   - context_limits: per-schema max_lines (default 300)
 *   - profile_id: training profile id that supplies trigger + caption strategy
 *     (canon-build delegates to captions.js just like the adapters do).
 */

import { readFile } from 'node:fs/promises';
import { isAbsolute, resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { inputError } from '../errors.js';

/**
 * Load and validate a canon-build config.
 *
 * @param {string} configPath — absolute path to canon-build/config.json
 * @param {string} projectRoot — for resolving project-relative paths
 */
export async function loadBuildConfig(configPath, projectRoot) {
  if (!existsSync(configPath)) {
    throw inputError(
      'CANON_BUILD_CONFIG_NOT_FOUND',
      `canon-build config not found at ${configPath}`,
      `Create the file with a project_id, canon_root, schema_dir, entity_dirs, and schema_to_lane map. See the handbook page "Canon Build" for the schema.`,
    );
  }

  const raw = await readFile(configPath, 'utf-8');
  let config;
  try {
    config = JSON.parse(raw);
  } catch (err) {
    throw inputError(
      'CANON_BUILD_CONFIG_INVALID_JSON',
      `canon-build config at ${configPath} is not valid JSON (${err.message})`,
      'Fix the JSON syntax; this file is the lane-resolution source of truth for the build.',
    );
  }

  const errors = [];

  if (!config.project_id) errors.push('missing required field: project_id');
  if (!config.canon_root) errors.push('missing required field: canon_root');
  if (!config.schema_dir) errors.push('missing required field: schema_dir');
  if (!config.entity_dirs || typeof config.entity_dirs !== 'object') {
    errors.push('missing or invalid entity_dirs (expected object mapping schema filename to subdirectory)');
  }
  if (!config.schema_to_lane || typeof config.schema_to_lane !== 'object') {
    errors.push('missing or invalid schema_to_lane (expected object)');
  } else {
    for (const [schemaName, rule] of Object.entries(config.schema_to_lane)) {
      if (!rule || typeof rule !== 'object') {
        errors.push(`schema_to_lane["${schemaName}"] must be an object`);
        continue;
      }
      if (rule.source === 'field') {
        if (!rule.field || typeof rule.field !== 'string') {
          errors.push(`schema_to_lane["${schemaName}"].source="field" requires a "field" string (dot-path)`);
        }
      } else if (rule.source === 'constant') {
        if (!rule.value || typeof rule.value !== 'string') {
          errors.push(`schema_to_lane["${schemaName}"].source="constant" requires a "value" string`);
        }
      } else {
        errors.push(`schema_to_lane["${schemaName}"].source must be "field" or "constant" (got "${rule.source}")`);
      }
    }
  }

  if (errors.length) {
    throw inputError(
      'CANON_BUILD_CONFIG_INVALID',
      `canon-build config at ${configPath} is invalid:\n  ${errors.join('\n  ')}`,
      'Fix the listed fields and retry.',
    );
  }

  // Resolve relative paths against the project root.
  const canonRoot = isAbsolute(config.canon_root) ? config.canon_root : resolve(projectRoot, config.canon_root);
  const schemaDir = isAbsolute(config.schema_dir) ? config.schema_dir : resolve(projectRoot, config.schema_dir);

  return {
    project_id: config.project_id,
    canon_root: canonRoot,
    schema_dir: schemaDir,
    entity_dirs: config.entity_dirs,
    schema_to_lane: config.schema_to_lane,
    context_limits: config.context_limits || {},
    profile_id: config.profile_id || null,
    // Preserve raw text for hashing — any change to the config invalidates cache.
    raw_text: raw,
  };
}

/**
 * Read a nested value from an object via a dot-path (e.g. "visual.art_lane").
 * Returns undefined if any segment is missing.
 */
export function getByPath(obj, path) {
  if (!obj || !path) return undefined;
  const parts = path.split('.');
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = cur[p];
  }
  return cur;
}
