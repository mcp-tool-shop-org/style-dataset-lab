/**
 * Per-project config loader.
 *
 * Loads JSON config files from a project root directory.
 * Falls back to sensible defaults when files don't exist,
 * so unmigrated projects (pre-v2.0) still work.
 */

import { readFileSync, existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { inputError, runtimeError } from './errors.js';
import { warn } from './log.js';

function loadJsonFile(filePath) {
  if (!existsSync(filePath)) return null;
  try {
    return JSON.parse(readFileSync(filePath, 'utf-8'));
  } catch (err) {
    throw runtimeError(
      'INPUT_INVALID_JSON',
      `Failed to parse ${filePath}: ${err.message}`,
      'Check the file for JSON syntax errors (trailing commas, unquoted keys, etc).',
      err
    );
  }
}

/**
 * Validate a user-authored regex pattern string at CONFIG LOAD TIME rather
 * than lazily inside detectLane()/detectGroup() on whatever record happens
 * to process first.
 *
 * B02: detectLane()/detectGroup() build `new RegExp(pattern)` from strings
 * loaded verbatim from lanes.json/terminology.json across 7 construction
 * sites, with zero validation before this. One unescaped bracket
 * (`"[freeport"`) used to abort a whole `sdlab bind` pass with a raw
 * `SyntaxError: Invalid regular expression` naming neither the file, the
 * lane/group, nor the offending pattern — finding it required manual
 * bisection of the config. This throws ONE structured error naming all
 * three, before any record is processed.
 *
 * @param {string} pattern
 * @param {{file: string, context: string}} where
 */
function validateRegexPattern(pattern, { file, context }) {
  try {
    // eslint-disable-next-line no-new -- validation only, result unused
    new RegExp(pattern);
  } catch (err) {
    throw inputError(
      'INPUT_BAD_REGEX',
      `Invalid regex pattern in ${file} (${context}): "${pattern}" — ${err.message}`,
      'Fix or escape the pattern (e.g. escape literal brackets/parens/braces) and try again.'
    );
  }
}

/**
 * Validate every id_patterns entry across all lanes in a loaded lanes.json.
 * Fails fast on the FIRST invalid pattern (not an aggregate report) so the
 * thrown error always names one concrete offending pattern.
 */
function validateLanePatterns(lanesData) {
  for (const lane of lanesData.lanes || []) {
    for (const pattern of lane.id_patterns || []) {
      validateRegexPattern(pattern, { file: 'lanes.json', context: `lane "${lane.id}"` });
    }
  }
}

/**
 * Validate every pattern site across a loaded terminology.json: per-group
 * id_patterns/prompt_patterns, plus the four dict/array pattern collections
 * detectGroup() also builds RegExp from (cross_group_patterns, edge_defaults,
 * null_faction_patterns, id_fallbacks) — the full set of 6 sites detectGroup()
 * itself constructs (the 7th is detectLane()'s single site, covered by
 * validateLanePatterns above).
 */
function validateTerminologyPatterns(termData) {
  for (const [groupName, group] of Object.entries(termData.groups || {})) {
    for (const pattern of group?.id_patterns || []) {
      validateRegexPattern(pattern, { file: 'terminology.json', context: `group "${groupName}" id_patterns` });
    }
    for (const pattern of group?.prompt_patterns || []) {
      validateRegexPattern(pattern, { file: 'terminology.json', context: `group "${groupName}" prompt_patterns` });
    }
  }
  for (const pattern of Object.keys(termData.cross_group_patterns || {})) {
    validateRegexPattern(pattern, { file: 'terminology.json', context: 'cross_group_patterns' });
  }
  for (const pattern of Object.keys(termData.edge_defaults || {})) {
    validateRegexPattern(pattern, { file: 'terminology.json', context: 'edge_defaults' });
  }
  for (const pattern of termData.null_faction_patterns || []) {
    validateRegexPattern(pattern, { file: 'terminology.json', context: 'null_faction_patterns' });
  }
  for (const pattern of Object.keys(termData.id_fallbacks || {})) {
    validateRegexPattern(pattern, { file: 'terminology.json', context: 'id_fallbacks' });
  }
}

/**
 * Async-safe readFile + JSON.parse with structured error handling.
 * Optionally validates that required top-level fields are present.
 *
 * @param {string} filePath — absolute path to a JSON file
 * @param {{requiredFields?: string[]}} [opts]
 */
export async function readJsonFile(filePath, opts = {}) {
  let raw;
  try {
    raw = await readFile(filePath, 'utf-8');
  } catch (err) {
    if (err && err.code === 'ENOENT') {
      throw inputError(
        'INPUT_FILE_NOT_FOUND',
        `File not found: ${filePath}`,
        'Check the path and try again.'
      );
    }
    throw runtimeError('RUNTIME_READ_FAILED', `Could not read ${filePath}: ${err.message}`, null, err);
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw runtimeError(
      'INPUT_INVALID_JSON',
      `Failed to parse ${filePath}: ${err.message}`,
      'Check the file for JSON syntax errors.',
      err
    );
  }
  const required = opts.requiredFields || [];
  if (required.length) {
    const missing = required.filter((f) => parsed == null || parsed[f] === undefined);
    if (missing.length) {
      throw inputError(
        'INPUT_MISSING_FIELDS',
        `${filePath} is missing required fields: ${missing.join(', ')}`,
        `Add the fields to the file, or use a valid example as template.`
      );
    }
  }
  return parsed;
}

/**
 * Load project.json — project identity and generation defaults.
 */
export function loadProjectMeta(projectRoot) {
  const filePath = join(projectRoot, 'project.json');
  if (!existsSync(filePath)) {
    // B05: this loader used to substitute its default with zero logging —
    // the module didn't even import lib/log.js. A dropped/never-created
    // project.json now names its expected path instead of degrading silently.
    warn(`project.json not found at ${filePath} — using built-in defaults (name: "unknown")`);
    return {
      name: 'unknown',
      display_name: 'Unknown Project',
      domain: 'generic',
      version: '0.0.0',
      defaults: {},
    };
  }
  return loadJsonFile(filePath);
}

/**
 * Default GPU label written into provenance when a project doesn't pin one.
 * This rig is the Robot rig (Omen 45L, RTX 5090 32GB); older records say
 * "RTX 5080" because the generator hardcoded the prior card.
 */
export const DEFAULT_GPU_MODEL = 'RTX 5090';

/**
 * Resolve the GPU label for a generation provenance record.
 * Precedence: project.json `defaults.gpu_model` → DEFAULT_GPU_MODEL.
 *
 * @param {Object} [projectDefaults] — the `defaults` block from project.json
 * @returns {string}
 */
export function resolveGpuModel(projectDefaults) {
  const v = projectDefaults?.gpu_model;
  return typeof v === 'string' && v.trim() ? v.trim() : DEFAULT_GPU_MODEL;
}

/**
 * Load constitution.json — array of rule objects.
 */
export function loadConstitution(projectRoot) {
  const filePath = join(projectRoot, 'constitution.json');
  if (!existsSync(filePath)) {
    // B05: see loadProjectMeta above — warn once, naming the expected path,
    // instead of silently substituting the empty-rules default.
    warn(`constitution.json not found at ${filePath} — using built-in defaults (no rules configured)`);
    return { rules: [] };
  }
  const data = loadJsonFile(filePath);
  if (Array.isArray(data)) return { rules: data };
  if (!data.rules) {
    throw inputError(
      'INPUT_BAD_CONFIG',
      `constitution.json must have a "rules" array`,
      'Wrap your rules in { "rules": [...] } or use an array at the top level.'
    );
  }
  return data;
}

/**
 * Load lanes.json — lane definitions with detection patterns.
 */
export function loadLanes(projectRoot) {
  const filePath = join(projectRoot, 'lanes.json');
  if (!existsSync(filePath)) {
    // B05: warn once, naming the expected path, instead of silently
    // substituting the no-lanes default.
    warn(`lanes.json not found at ${filePath} — using built-in defaults (no lanes configured)`);
    return { default_lane: 'default', lanes: [] };
  }
  const data = loadJsonFile(filePath);
  if (!data.lanes) {
    throw inputError(
      'INPUT_BAD_CONFIG',
      `lanes.json must have a "lanes" array`,
      'Top-level shape: { "default_lane": "...", "lanes": [ ... ] }.'
    );
  }
  // B02: validate every id_patterns regex now, before any record is ever
  // tested against it — see validateRegexPattern's docstring above.
  validateLanePatterns(data);
  return data;
}

/**
 * Load rubric.json — scoring dimensions, thresholds, failure modes.
 */
export function loadRubric(projectRoot) {
  const filePath = join(projectRoot, 'rubric.json');
  if (!existsSync(filePath)) {
    // B05: warn once, naming the expected path, instead of silently
    // substituting the built-in thresholds default.
    warn(`rubric.json not found at ${filePath} — using built-in defaults (pass=0.7/partial=0.5/fail_ceiling=0.4)`);
    return {
      dimensions: [],
      thresholds: { pass: 0.7, partial: 0.5, fail_ceiling: 0.4 },
      failure_to_rules: {},
    };
  }
  return loadJsonFile(filePath);
}

/**
 * Load terminology.json — group vocabulary and detection patterns.
 */
export function loadTerminology(projectRoot) {
  const filePath = join(projectRoot, 'terminology.json');
  if (!existsSync(filePath)) {
    // B05: this is the finding's own example — a dropped terminology.json
    // used to make detectGroup() return null for every record with zero
    // signal. Warn once, naming the expected path, instead of substituting
    // the empty-groups default silently.
    warn(`terminology.json not found at ${filePath} — using built-in defaults (no groups configured)`);
    return {
      group_label: 'group',
      groups: {},
      cross_group_patterns: {},
      edge_defaults: {},
      prompt_fallbacks: {},
    };
  }
  const data = loadJsonFile(filePath);
  // B02: validate every pattern site now, before any record is ever tested
  // against it — see validateRegexPattern's docstring above.
  validateTerminologyPatterns(data);
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

// ─── Profile Loaders ─────────────────────────────────────────────────

const DEFAULT_SELECTION_PROFILE = {
  require_judgment: true,
  require_status: ['approved'],
  require_canon_bound: true,
  minimum_pass_ratio: 0.5,
  rights_filter: null,
  exclude_lanes: [],
  max_per_subject: null,
  max_per_lane: null,
};

const DEFAULT_SPLIT_PROFILE = {
  profile_id: 'balanced-default',
  strategy: 'subject-isolated',
  train_ratio: 0.8,
  val_ratio: 0.1,
  test_ratio: 0.1,
  lane_balance: true,
  subject_isolation: true,
  seed: 42,
};

const DEFAULT_EXPORT_PROFILE = {
  profile_id: 'canonical-package',
  include_images: true,
  image_strategy: 'symlink',
  include_splits: true,
  include_card: true,
  include_checksums: true,
  metadata_fields: ['id', 'asset_path', 'provenance', 'judgment', 'canon', 'identity', 'lineage'],
};

/**
 * Load a selection profile from project or return built-in default.
 */
export function loadSelectionProfile(projectRoot, profileId) {
  if (!profileId) return { ...DEFAULT_SELECTION_PROFILE };
  const data = loadJsonFile(join(projectRoot, 'selection-profiles', `${profileId}.json`));
  if (!data) return { ...DEFAULT_SELECTION_PROFILE };
  return { ...DEFAULT_SELECTION_PROFILE, ...data };
}

/**
 * Load a split profile from project or return built-in default.
 */
export function loadSplitProfile(projectRoot, profileId) {
  if (!profileId) return { ...DEFAULT_SPLIT_PROFILE };
  const data = loadJsonFile(join(projectRoot, 'split-profiles', `${profileId}.json`));
  if (!data) return { ...DEFAULT_SPLIT_PROFILE };
  return { ...DEFAULT_SPLIT_PROFILE, ...data };
}

/**
 * Load an export profile from project or return built-in default.
 */
export function loadExportProfile(projectRoot, profileId) {
  if (!profileId) return { ...DEFAULT_EXPORT_PROFILE };
  const data = loadJsonFile(join(projectRoot, 'export-profiles', `${profileId}.json`));
  if (!data) return { ...DEFAULT_EXPORT_PROFILE };
  return { ...DEFAULT_EXPORT_PROFILE, ...data };
}

// ─── Detection Functions ─────────────────────────────────────────────
// Extracted from scripts/canon-bind.js for reuse in eligibility,
// snapshot, and split modules.

/**
 * Detect lane from asset ID using project lane config.
 * Tests each lane's id_patterns as regex against the lowercase ID.
 * Returns the first match, or the default_lane.
 */
export function detectLane(id, prompt, lanesConfig) {
  const lower = id.toLowerCase();
  for (const lane of lanesConfig.lanes) {
    if (!lane.id_patterns || lane.id_patterns.length === 0) continue;
    for (const pattern of lane.id_patterns) {
      if (new RegExp(pattern).test(lower)) return lane.id;
    }
  }
  return lanesConfig.default_lane;
}

/**
 * Detect group (faction) from asset ID and prompt using terminology config.
 * Uses explicit id_detection_order and prompt_detection_order when provided
 * to preserve the exact detection priority of the original implementation.
 */
export function detectGroup(id, prompt, termConfig) {
  const idOrder = termConfig.id_detection_order || Object.keys(termConfig.groups);
  const promptOrder = termConfig.prompt_detection_order || Object.keys(termConfig.groups);

  // 1. Primary ID patterns per group (id_detection_order)
  for (const groupName of idOrder) {
    const group = termConfig.groups[groupName];
    if (!group?.id_patterns) continue;
    for (const pattern of group.id_patterns) {
      if (new RegExp(pattern).test(id)) return groupName;
    }
  }

  // 2. Cross-group patterns
  for (const [pattern, behavior] of Object.entries(termConfig.cross_group_patterns || {})) {
    if (new RegExp(pattern).test(id)) {
      if (behavior === 'detect_from_id_suffix') {
        for (const groupName of idOrder) {
          if (id.includes(groupName)) return groupName;
        }
      }
      return null;
    }
  }

  // 3. Edge defaults
  for (const [pattern, groupName] of Object.entries(termConfig.edge_defaults || {})) {
    if (new RegExp(pattern).test(id)) return groupName;
  }

  // 4. Prompt-based fallback (prompt_detection_order)
  if (prompt) {
    const p = prompt.toLowerCase();
    for (const groupName of promptOrder) {
      const group = termConfig.groups[groupName];
      if (!group?.prompt_patterns || group.prompt_patterns.length === 0) continue;
      for (const keyword of group.prompt_patterns) {
        if (new RegExp(keyword).test(p)) return groupName;
      }
    }
  }

  // 5. Null-faction patterns (generic rejects — no faction)
  for (const pattern of termConfig.null_faction_patterns || []) {
    if (new RegExp(pattern).test(id)) return null;
  }

  // 6. ID fallback patterns
  for (const [pattern, groupName] of Object.entries(termConfig.id_fallbacks || {})) {
    if (new RegExp(pattern).test(id)) return groupName;
  }

  return null;
}
