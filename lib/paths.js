/**
 * Path resolution — single source of truth for repo root and project paths.
 */

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { existsSync } from 'node:fs';

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
  const root = join(REPO_ROOT, 'projects', name);
  if (!existsSync(root)) {
    throw new Error(
      `Project "${name}" not found at ${root}.\n` +
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
