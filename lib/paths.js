/**
 * Path resolution — single source of truth for repo root and project paths.
 */

import { fileURLToPath } from 'node:url';
import { dirname, join, resolve, relative, isAbsolute } from 'node:path';
import { existsSync } from 'node:fs';
import { inputError } from './errors.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** Absolute path to the repository root. */
export const REPO_ROOT = join(__dirname, '..');

/**
 * Resolve the root directory for a named project.
 * @param {string} name — project name (e.g. 'star-freight')
 * @returns {string} absolute path to projects/<name>/
 */
export function getProjectRoot(name) {
  if (!name || typeof name !== 'string') {
    throw inputError(
      'INPUT_MISSING_PROJECT',
      'Project name is required.',
      'Pass --project <name>.'
    );
  }
  const root = join(REPO_ROOT, 'projects', name);
  if (!existsSync(root)) {
    throw inputError(
      'INPUT_UNKNOWN_PROJECT',
      `Project "${name}" not found at ${root}.`,
      `Run: sdlab init ${name} --domain <domain>`
    );
  }
  return root;
}

/**
 * Join segments onto a project root.
 * @param {string} name — project name
 * @param {...string} segments — path segments
 */
export function resolveProjectPath(name, ...segments) {
  return join(getProjectRoot(name), ...segments);
}

/**
 * Resolve a user-supplied path relative to a project root and verify
 * it does not escape the root (no `..` traversal, no absolute-path escapes
 * out of root). Returns the absolute resolved path.
 *
 * @param {string} projectRoot — absolute project root (trusted)
 * @param {string} userPath — user-supplied, possibly malicious path
 * @param {{baseRoot?:string, flagName?:string}} [opts]
 * @returns {string} absolute path guaranteed to be within baseRoot
 */
export function resolveSafeProjectPath(projectRoot, userPath, opts = {}) {
  const flagName = opts.flagName || 'path';
  if (userPath == null || userPath === '') {
    throw inputError('INPUT_MISSING_VALUE', `Flag --${flagName} requires a path.`);
  }
  const baseRoot = opts.baseRoot || projectRoot;
  const absBase = resolve(baseRoot);
  const resolved = isAbsolute(userPath) ? resolve(userPath) : resolve(absBase, userPath);
  const rel = relative(absBase, resolved);
  if (rel.startsWith('..') || (isAbsolute(rel) && rel !== '')) {
    throw inputError(
      'INPUT_PATH_TRAVERSAL',
      `Path "${userPath}" resolves outside of ${absBase}.`,
      `Paths passed via --${flagName} must stay within the project tree.`
    );
  }
  return resolved;
}

/**
 * Return the workflow profiles directory for a project root.
 * @param {string} projectRoot — absolute path to project
 */
export function getWorkflowProfilesDir(projectRoot) {
  return join(projectRoot, 'workflows', 'profiles');
}

/**
 * Return the briefs directory for a project root.
 * @param {string} projectRoot — absolute path to project
 */
export function getBriefsDir(projectRoot) {
  return join(projectRoot, 'briefs');
}

/**
 * Return the runs directory for a project root.
 * @param {string} projectRoot — absolute path to project
 */
export function getRunsDir(projectRoot) {
  return join(projectRoot, 'runs');
}

/**
 * Return the runtime templates directory (repo-level).
 */
export function getRuntimeDir() {
  return join(REPO_ROOT, 'runtime');
}
