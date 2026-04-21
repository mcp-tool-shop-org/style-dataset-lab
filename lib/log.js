/**
 * Logging levels for CLI output.
 *
 * Levels: quiet < normal < verbose
 * Set via --quiet or --verbose flags (parsed by caller).
 *
 * Context prefix:
 *   info('generate', 'starting wave 1')  → '[generate] starting wave 1'
 *   info('starting wave 1')               → 'starting wave 1' (no prefix)
 * The first argument is treated as a command/context label when it is a
 * short single-token string with no whitespace; otherwise the call is
 * prefix-less and backwards-compatible.
 */

let level = 'normal'; // quiet | normal | verbose

export function setLogLevel(l) {
  level = l;
}

export function getLogLevel() {
  return level;
}

// Accept a leading short-token context label as the first arg.
// Heuristic: string, no whitespace, ≤ 32 chars, and there is at least
// one additional argument after it. This keeps existing call sites
// (where args is typically a full message) unchanged.
function applyContextPrefix(args) {
  if (args.length < 2) return args;
  const first = args[0];
  if (typeof first !== 'string') return args;
  if (first.length > 32) return args;
  if (/\s/.test(first)) return args;
  // Avoid treating a message that happens to start with a format token as
  // a context: require it to look like an identifier (word chars, dots, dashes).
  if (!/^[A-Za-z][\w.:-]*$/.test(first)) return args;
  return [`[${first}]`, ...args.slice(1)];
}

/** Always shown (errors, final results). */
export function log(...args) {
  console.log(...applyContextPrefix(args));
}

/**
 * Artifact / final-output path helper.
 * Always prints regardless of verbosity (survives --quiet) so scripts
 * that produce files have a machine-parseable path on stdout.
 */
export function result(...args) {
  console.log(...applyContextPrefix(args));
}

/** Always shown (used for final success lines). */
export function success(...args) {
  console.log(...applyContextPrefix(args));
}

/** Shown at normal and verbose levels (progress, summaries). */
export function info(...args) {
  if (level !== 'quiet') console.log(...applyContextPrefix(args));
}

/** Shown only at verbose level (per-record details, debug context). */
export function verbose(...args) {
  if (level === 'verbose') console.log(...applyContextPrefix(args));
}

/** Always shown on stderr. */
export function warn(...args) {
  console.error('\x1b[33m⚠\x1b[0m', ...applyContextPrefix(args));
}
