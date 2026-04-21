/**
 * Unified CLI argument parser.
 *
 * Supports:
 *   --flag value       (space-separated)
 *   --flag=value       (equals form)
 *   --boolean-flag     (boolean)
 *   positional args    (collected in order)
 *   deprecated aliases (warns once, maps to canonical name)
 */

import { warnDeprecated } from './deprecation.js';
import { inputError } from './errors.js';

/**
 * @typedef {Object} ArgSpec
 * @property {Object<string, {type: 'string'|'boolean', default?: any, alias?: string}>} flags
 * @property {string[]} [positionals] - names for positional args (in order)
 * @property {Object<string, string>} [deprecated] - old flag name → new flag name
 * @property {boolean} [allowUnknown] - permit unknown flags (default false)
 */

/**
 * Parse CLI arguments.
 * @param {string[]} argv — typically process.argv.slice(2)
 * @param {ArgSpec} spec
 * @returns {{ flags: Object, positionals: string[], rest: string[] }}
 */
export function parseArgs(argv, spec = {}) {
  const flagDefs = spec.flags || {};
  const deprecated = spec.deprecated || {};
  const positionalNames = spec.positionals || [];
  const allowUnknown = spec.allowUnknown === true;

  // Build alias index once; detect duplicate aliases.
  const aliasIndex = {};
  for (const [name, def] of Object.entries(flagDefs)) {
    if (def && def.alias) {
      if (aliasIndex[def.alias]) {
        throw inputError(
          'INPUT_DUPLICATE_ALIAS',
          `Duplicate CLI alias "-${def.alias}" (on both "${aliasIndex[def.alias]}" and "${name}")`,
          'Fix the flag spec: each alias must be unique.'
        );
      }
      aliasIndex[def.alias] = name;
    }
  }

  const flags = {};
  const positionals = [];

  // Set defaults
  for (const [name, def] of Object.entries(flagDefs)) {
    if (def.default !== undefined) flags[name] = def.default;
    else if (def.type === 'boolean') flags[name] = false;
    else flags[name] = undefined;
  }

  let i = 0;
  while (i < argv.length) {
    const arg = argv[i];

    if (arg.startsWith('--')) {
      let key, value;

      if (arg.includes('=')) {
        const eqIdx = arg.indexOf('=');
        key = arg.slice(2, eqIdx);
        value = arg.slice(eqIdx + 1);
      } else {
        key = arg.slice(2);
        value = undefined;
      }

      // Handle deprecated aliases
      if (deprecated[key]) {
        warnDeprecated(key, deprecated[key]);
        key = deprecated[key];
      }

      // Handle short aliases defined in flagDefs (O(1) via prebuilt index)
      if (aliasIndex[key]) key = aliasIndex[key];

      // Normalize kebab-case to camelCase for lookup
      const camelKey = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      const def = flagDefs[key] || flagDefs[camelKey];

      if (!def && !allowUnknown) {
        throw inputError(
          'UNKNOWN_FLAG',
          `Unknown flag: --${key}`,
          'Run with --help to see supported flags.'
        );
      }

      const storeKey = key in flagDefs ? key : camelKey;

      if (def?.type === 'boolean') {
        flags[storeKey] = true;
      } else if (value !== undefined) {
        flags[storeKey] = value;
      } else if (i + 1 < argv.length && !argv[i + 1].startsWith('--')) {
        flags[storeKey] = argv[++i];
      } else if (def && def.type === 'string') {
        // String flag with no value — that's a user error.
        throw inputError(
          'INPUT_MISSING_VALUE',
          `Flag --${key} requires a value.`,
          `Pass a value after --${key}.`
        );
      } else {
        // Unknown flag in allowUnknown mode (no def), treat as boolean-style.
        flags[storeKey] = true;
      }
    } else {
      positionals.push(arg);
    }
    i++;
  }

  // Map positionals to named keys
  const named = {};
  for (let j = 0; j < positionalNames.length && j < positionals.length; j++) {
    named[positionalNames[j]] = positionals[j];
  }

  return { flags, positionals, named, rest: positionals.slice(positionalNames.length) };
}

/**
 * Extract the --project (or deprecated --game) value from argv.
 *
 * Returns the explicit value if given. If missing, falls back to
 * 'star-freight' with a stderr warning (for backward compatibility
 * with v2.x scripts). Callers should prefer passing --project explicitly.
 */
export function getProjectName(argv) {
  // Manual parse (avoids triggering UNKNOWN_FLAG on caller's sibling flags)
  let explicit = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--project' || a === '--game') {
      if (a === '--game') warnDeprecated('game', 'project');
      explicit = argv[i + 1];
      break;
    }
    if (a.startsWith('--project=')) { explicit = a.slice('--project='.length); break; }
    if (a.startsWith('--game=')) { warnDeprecated('game', 'project'); explicit = a.slice('--game='.length); break; }
  }
  if (explicit) return explicit;

  // Backward compat: fall back to star-freight but warn loudly
  if (process.env.SDLAB_QUIET_FALLBACK !== '1') {
    console.error('\x1b[33mwarn:\x1b[0m --project not specified; falling back to "star-freight". Pass --project explicitly.');
  }
  return 'star-freight';
}

/**
 * Parse a CLI value as a number with NaN validation.
 * @param {string} name - flag name, for error messages
 * @param {string|number|undefined} value - the raw flag value
 * @param {{min?:number,max?:number,int?:boolean,default?:number}} opts
 */
export function parseNumberFlag(name, value, opts = {}) {
  if (value === undefined || value === null || value === '') {
    if (opts.default !== undefined) return opts.default;
    throw inputError(
      'INPUT_MISSING_VALUE',
      `Flag --${name} requires a numeric value.`,
      `Example: --${name} 4`
    );
  }
  const n = opts.int ? Number.parseInt(String(value), 10) : Number.parseFloat(String(value));
  if (!Number.isFinite(n)) {
    throw inputError(
      'INPUT_BAD_NUMBER',
      `Flag --${name} expected a number, got "${value}".`,
      `Pass a ${opts.int ? 'whole number' : 'number'} instead.`
    );
  }
  if (opts.min !== undefined && n < opts.min) {
    throw inputError('INPUT_OUT_OF_RANGE', `--${name} must be ≥ ${opts.min}, got ${n}.`);
  }
  if (opts.max !== undefined && n > opts.max) {
    throw inputError('INPUT_OUT_OF_RANGE', `--${name} must be ≤ ${opts.max}, got ${n}.`);
  }
  return n;
}

/**
 * Read an indexed-next-arg value from argv but refuse to consume a flag-like token.
 * Useful for legacy scripts still using indexOf/argv[idx+1] patterns — wraps the access
 * with a safety check so `--source --manifest` doesn't silently treat `--manifest` as a path.
 */
export function takeFlagValue(argv, flagName) {
  const idx = argv.indexOf(`--${flagName}`);
  if (idx < 0) {
    // Try --flag=value form
    const eq = argv.find(a => a.startsWith(`--${flagName}=`));
    if (eq) return eq.slice(`--${flagName}=`.length);
    return undefined;
  }
  const nxt = argv[idx + 1];
  if (nxt === undefined) {
    throw inputError('INPUT_MISSING_VALUE', `Flag --${flagName} requires a value.`);
  }
  if (typeof nxt === 'string' && nxt.startsWith('--')) {
    throw inputError(
      'INPUT_MISSING_VALUE',
      `Flag --${flagName} is missing its value (got another flag: ${nxt}).`,
      `Pass a value after --${flagName}.`
    );
  }
  return nxt;
}

/**
 * Strip the subcommand token at position argv[firstPositionalIndex] by slicing,
 * avoiding the value-based filter bug where a project/id that matches the
 * subcommand string would be stripped too.
 *
 * Returns the args AFTER the first non-flag token. If no non-flag token is
 * found, returns a copy of argv.
 */
export function sliceAfterSubcommand(argv, subcommand) {
  if (subcommand == null) return argv.slice();
  const idx = argv.indexOf(subcommand);
  if (idx < 0) return argv.slice();
  return argv.slice(idx + 1);
}
