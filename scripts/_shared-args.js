/**
 * _shared-args.js — internal helper module (NOT a CLI command; underscore
 * prefix matches the existing scripts/_batch_cut.py / _seam_cutout.py
 * convention for "helper, not dispatched by bin/sdlab.js").
 *
 * H4 (second half): the five canon-*.js scripts (canon-build.js,
 * canon-drift.js, canon-freeze.js, canon-freeze-status.js,
 * canon-unfreeze.js) all use Node's built-in `util.parseArgs({strict:
 * false})`. strict:false is there deliberately, so a bare positional
 * argument (the entity id) isn't rejected — but it has a side effect: ANY
 * unrecognized `--flag` is silently accepted too. A misspelled OPTIONAL
 * flag (`--staus follow` instead of `--status follow`, `--jsn` instead of
 * `--json`) produces no error and no warning — the option you meant to set
 * just quietly keeps its default, and Node's parser stores the typo under
 * ITS OWN key in `parsed.values`, never touching the one you meant.
 *
 * assertKnownOptions() closes that gap without giving up strict:false's
 * positional leniency: after parsing, walk `parsed.values`'s keys — since
 * every DECLARED option (default or explicit) and every UNDECLARED flag
 * alike lands there — and reject any key outside the known option set.
 * Mirrors lib/args.js's own UNKNOWN_FLAG shape (same code, same
 * "Did you mean" hint via findClosest) so a typo on a canon-*.js flag reads
 * identically to a typo anywhere else in the CLI.
 */
import { inputError } from '../lib/errors.js';
import { findClosest } from '../lib/args.js';

/**
 * @param {Object} parsedValues — the `.values` object returned by
 *   node:util's parseArgs({strict:false, ...})
 * @param {Object} optionsSpec — the SAME `options` object passed to parseArgs
 * @param {{ command?: string }} [opts] — command label for the hint text
 */
export function assertKnownOptions(parsedValues, optionsSpec, opts = {}) {
  const known = new Set(Object.keys(optionsSpec));
  for (const key of Object.keys(parsedValues || {})) {
    if (known.has(key)) continue;
    const suggestion = findClosest(key, [...known]);
    const hint = suggestion
      ? `Did you mean --${suggestion}? (Run "sdlab ${opts.command ? opts.command + ' ' : ''}--help" to see all supported flags.)`
      : `Run "sdlab ${opts.command ? opts.command + ' ' : ''}--help" to see supported flags.`;
    throw inputError('UNKNOWN_FLAG', `Unknown flag: --${key}`, hint);
  }
}
