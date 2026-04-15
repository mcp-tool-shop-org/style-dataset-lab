/**
 * Per-project config loader.
 *
 * Loads JSON config files from a project root directory.
 * Falls back to sensible defaults when files don't exist,
 * so unmigrated projects (pre-v2.0) still work.
 */

import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

function loadJsonFile(filePath) {
  if (!existsSync(filePath)) return null;
  try {
    return JSON.parse(readFileSync(filePath, 'utf-8'));
  } catch (err) {
    throw new Error(`Failed to parse ${filePath}: ${err.message}`);
  }
}

/**
 * Load project.json — project identity and generation defaults.
 */
export function loadProjectMeta(projectRoot) {
  const data = loadJsonFile(join(projectRoot, 'project.json'));
  if (!data) {
    return {
      name: 'unknown',
      display_name: 'Unknown Project',
      domain: 'generic',
      version: '0.0.0',
      defaults: {},
    };
  }
  return data;
}

/**
 * Load constitution.json — array of rule objects.
 */
export function loadConstitution(projectRoot) {
  const data = loadJsonFile(join(projectRoot, 'constitution.json'));
  if (!data) return { rules: [] };
  if (Array.isArray(data)) return { rules: data };
  if (!data.rules) throw new Error(`constitution.json must have a "rules" array`);
  return data;
}

/**
 * Load lanes.json — lane definitions with detection patterns.
 */
export function loadLanes(projectRoot) {
  const data = loadJsonFile(join(projectRoot, 'lanes.json'));
  if (!data) {
    return { default_lane: 'default', lanes: [] };
  }
  if (!data.lanes) throw new Error(`lanes.json must have a "lanes" array`);
  return data;
}

/**
 * Load rubric.json — scoring dimensions, thresholds, failure modes.
 */
export function loadRubric(projectRoot) {
  const data = loadJsonFile(join(projectRoot, 'rubric.json'));
  if (!data) {
    return {
      dimensions: [],
      thresholds: { pass: 0.7, partial: 0.5, fail_ceiling: 0.4 },
      failure_to_rules: {},
    };
  }
  return data;
}

/**
 * Load terminology.json — group vocabulary and detection patterns.
 */
export function loadTerminology(projectRoot) {
  const data = loadJsonFile(join(projectRoot, 'terminology.json'));
  if (!data) {
    return {
      group_label: 'group',
      groups: {},
      cross_group_patterns: {},
      edge_defaults: {},
      prompt_fallbacks: {},
    };
  }
  return data;
}

/**
 * Load all project config files at once.
 */
export function loadProjectConfig(projectRoot) {
  return {
    meta: loadProjectMeta(projectRoot),
    constitution: loadConstitution(projectRoot),
    lanes: loadLanes(projectRoot),
    rubric: loadRubric(projectRoot),
    terminology: loadTerminology(projectRoot),
  };
}
