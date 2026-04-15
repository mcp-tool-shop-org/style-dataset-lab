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

/**
 * @typedef {Object} ArgSpec
 * @property {Object<string, {type: 'string'|'boolean', default?: any, alias?: string}>} flags
 * @property {string[]} [positionals] - names for positional args (in order)
 * @property {Object<string, string>} [deprecated] - old flag name → new flag name
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

      // Handle short aliases defined in flagDefs
      const canonical = Object.entries(flagDefs).find(([, def]) => def.alias === key);
      if (canonical) key = canonical[0];

      // Normalize kebab-case to camelCase for lookup
      const camelKey = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      const def = flagDefs[key] || flagDefs[camelKey];

      if (def?.type === 'boolean') {
        flags[key in flagDefs ? key : camelKey] = true;
      } else if (value !== undefined) {
        flags[key in flagDefs ? key : camelKey] = value;
      } else if (i + 1 < argv.length && !argv[i + 1].startsWith('--')) {
        flags[key in flagDefs ? key : camelKey] = argv[++i];
      } else {
        flags[key in flagDefs ? key : camelKey] = true;
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
 * Convenience for scripts that just need the project name.
 */
export function getProjectName(argv) {
  const { flags } = parseArgs(argv, {
    flags: { project: { type: 'string', default: 'star-freight' } },
    deprecated: { game: 'project' },
  });
  return flags.project;
}
