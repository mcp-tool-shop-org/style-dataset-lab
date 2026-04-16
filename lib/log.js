/**
 * Logging levels for CLI output.
 *
 * Levels: quiet < normal < verbose
 * Set via --quiet or --verbose flags (parsed by caller).
 */

let level = 'normal'; // quiet | normal | verbose

export function setLogLevel(l) {
  level = l;
}

export function getLogLevel() {
  return level;
}

/** Always shown (errors, final results). */
export function log(...args) {
  console.log(...args);
}

/** Shown at normal and verbose levels (progress, summaries). */
export function info(...args) {
  if (level !== 'quiet') console.log(...args);
}

/** Shown only at verbose level (per-record details, debug context). */
export function verbose(...args) {
  if (level === 'verbose') console.log(...args);
}

/** Always shown on stderr. */
export function warn(...args) {
  console.error('\x1b[33m⚠\x1b[0m', ...args);
}
