/**
 * Structured error shape for Style Dataset Lab.
 *
 * Every user-facing error has: code, message, hint.
 * Exit codes: 0 ok, 1 user error, 2 runtime error.
 */

export class SdlabError extends Error {
  /**
   * @param {string} code — error code (e.g. INPUT_MISSING_FLAG)
   * @param {string} message — human-readable description
   * @param {Object} options
   * @param {string} [options.hint] — actionable fix suggestion
   * @param {Error} [options.cause] — original error
   * @param {number} [options.exitCode] — 1 (user) or 2 (runtime)
   */
  constructor(code, message, { hint, cause, exitCode } = {}) {
    super(message);
    this.name = 'SdlabError';
    this.code = code;
    this.hint = hint || null;
    this.cause = cause || null;
    this.exitCode = exitCode || 1;
  }

  toJSON() {
    return {
      code: this.code,
      message: this.message,
      hint: this.hint,
    };
  }
}

// ─── Convenience constructors ──────────────────────────────────────

export function inputError(code, message, hint) {
  return new SdlabError(code, message, { hint, exitCode: 1 });
}

export function runtimeError(code, message, hint, cause) {
  return new SdlabError(code, message, { hint, cause, exitCode: 2 });
}

// ─── CLI error handler ─────────────────────────────────────────────

let debugMode = false;

export function enableDebug() {
  debugMode = true;
}

export function isDebug() {
  return debugMode;
}

/**
 * Handle an error at the CLI boundary.
 * Shows structured output by default, stack trace with --debug.
 */
export function handleCliError(err) {
  if (err instanceof SdlabError) {
    console.error(`\x1b[31mError [${err.code}]:\x1b[0m ${err.message}`);
    if (err.hint) {
      console.error(`\x1b[33mHint:\x1b[0m ${err.hint}`);
    }
    if (debugMode && err.stack) {
      console.error('\n' + err.stack);
    }
    if (debugMode && err.cause) {
      console.error('\nCaused by:', err.cause);
    }
    process.exit(err.exitCode);
  } else {
    // Unstructured error — runtime failure
    console.error(`\x1b[31mError:\x1b[0m ${err.message || err}`);
    if (debugMode && err.stack) {
      console.error('\n' + err.stack);
    }
    process.exit(2);
  }
}
