/**
 * Path resolution — single source of truth for repo root and project paths.
 */

import { fileURLToPath } from 'node:url';
import { dirname, join, resolve, relative, isAbsolute } from 'node:path';
import { existsSync } from 'node:fs';
import { inputError } from './errors.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ─── Workspace root resolution (SDL-C1) ───────────────────────────
//
// `REPO_ROOT` used to be `join(__dirname, '..')` — always the directory
// this module happens to live in. That is correct for an in-repo checkout,
// but for an npm-installed consumer it resolves to
// `node_modules/@mcptoolshop/style-dataset-lab`, so `sdlab init demo`
// silently wrote the user's whole project tree into node_modules — gone on
// the next `npm ci`.
//
// The fix is a 4-step search, cheapest/most-explicit signal first:
//   1. SDLAB_ROOT env var, if set and it exists.
//   2. Walk up from process.cwd() looking for a directory containing
//      `projects/`. First hit wins — this is how a user's own workspace
//      (wherever it lives) gets found.
//   3. The module's own root, IF it already has a `projects/` dir — this is
//      what preserves every existing in-repo dev/test workflow, where cwd
//      already resolves via step 2 anyway, but is kept as an explicit
//      fallback for callers with an unusual cwd.
//   4. process.cwd() itself — a fresh workspace where `init` will create
//      `projects/`.
//
// Whatever step wins, the result is never allowed to sit inside a
// node_modules directory — that is the exact shape of the original bug, so
// it is a hard error instead of a silent write into someone's
// node_modules tree.

/**
 * True if any path segment of `absPath` is literally `node_modules`.
 */
function isInsideNodeModules(absPath) {
  return resolve(absPath)
    .split(/[\\/]+/)
    .some((seg) => seg.toLowerCase() === 'node_modules');
}

function assertNotInNodeModules(absPath, label) {
  if (isInsideNodeModules(absPath)) {
    throw inputError(
      'INPUT_ROOT_IN_NODE_MODULES',
      `Resolved workspace root (${label}) sits inside a node_modules directory: ${absPath}`,
      'Run sdlab from your own project directory, or set SDLAB_ROOT to your workspace path.'
    );
  }
  return absPath;
}

/**
 * Walk up from `startDir` looking for a directory that contains a
 * `projects/` subdirectory. Returns the first hit, or null if the walk
 * reaches the filesystem root without finding one.
 */
function walkUpForProjectsDir(startDir) {
  let dir = resolve(startDir);
  while (true) {
    if (existsSync(join(dir, 'projects'))) return dir;
    const parent = dirname(dir);
    if (parent === dir) return null; // reached the filesystem root
    dir = parent;
  }
}

/**
 * Pure resolution logic for the workspace root, taking every input
 * explicitly (cwd, env, module root) rather than reading global process
 * state directly. This is what makes it possible to unit-test all four
 * branches deterministically without mutating the real process.cwd() or
 * environment (which are shared, global, and unsafe to mutate across a
 * concurrently-run test suite).
 *
 * Production callers should use `getWorkspaceRoot()` instead, which
 * supplies the real process.cwd()/env and memoizes the result.
 *
 * @param {string} cwd
 * @param {{env?: Object, moduleRoot?: string}} [opts]
 * @returns {string} absolute workspace root
 */
export function resolveWorkspaceRootFrom(cwd, opts = {}) {
  const env = opts.env || process.env;
  const moduleRoot = opts.moduleRoot || join(__dirname, '..');

  // 1. SDLAB_ROOT env var, if set and it exists.
  const envRoot = env.SDLAB_ROOT;
  if (envRoot && existsSync(envRoot)) {
    return assertNotInNodeModules(resolve(envRoot), 'from SDLAB_ROOT');
  }

  // 2. Walk up from cwd looking for projects/.
  const fromCwd = walkUpForProjectsDir(cwd);
  if (fromCwd) {
    return assertNotInNodeModules(fromCwd, 'found by walking up from the current directory');
  }

  // 3. The module root itself is the repo checkout.
  if (existsSync(join(moduleRoot, 'projects'))) {
    return assertNotInNodeModules(resolve(moduleRoot), 'the style-dataset-lab install directory');
  }

  // 4. Fresh workspace — init will create projects/ here.
  return assertNotInNodeModules(resolve(cwd), 'the current directory');
}

let _workspaceRootCache = null;

/**
 * Resolve (and memoize) the workspace root using the real process.cwd()
 * and process.env. Safe to call repeatedly — it only walks the filesystem
 * once per process, unless reset.
 * @returns {string}
 */
export function getWorkspaceRoot() {
  if (_workspaceRootCache === null) {
    _workspaceRootCache = resolveWorkspaceRootFrom(process.cwd());
  }
  return _workspaceRootCache;
}

/**
 * Clear the memoized workspace root so the next getWorkspaceRoot() call
 * re-resolves from scratch. Exists for tests that need to exercise the
 * resolver under different SDLAB_ROOT/cwd conditions within one process.
 */
export function resetWorkspaceRootCache() {
  _workspaceRootCache = null;
}

/**
 * Absolute path to the workspace root — the directory that contains (or
 * will contain) `projects/`. Kept as a plain exported constant for
 * backward compatibility with the ~30 existing call sites that do
 * `join(REPO_ROOT, ...)`, but its VALUE now comes from the resolver above
 * rather than being hardcoded to this module's own location.
 */
export const REPO_ROOT = getWorkspaceRoot();

/**
 * Absolute path to the INSTALLED PACKAGE's own root — always module-relative,
 * never the user's workspace.
 *
 * There are two distinct roots and conflating them is a shipping bug:
 *
 *   - **workspace root** (`getWorkspaceRoot()`) — where the user's `projects/`
 *     live. Correctly cwd-relative, so an npm-installed user's data lands in
 *     their own directory instead of inside `node_modules`.
 *   - **package root** (this) — where assets that SHIP IN THE TARBALL live:
 *     `templates/` (domain starter packs) and `runtime/` (ComfyUI workflow
 *     graphs). These belong to the install, not to the workspace.
 *
 * In a repo checkout the two coincide, which is exactly why the distinction
 * is easy to lose and impossible to catch with in-repo tests. Measured in a
 * clean-room tarball install: with `templates/` resolved against the
 * workspace root, `sdlab init demo --domain character-design` failed with
 * `INPUT_UNKNOWN_DOMAIN: Available: generic,` — the five domain packs were
 * sitting in the package the whole time, being looked for in the user's cwd.
 */
export function getPackageRoot() {
  return resolve(join(__dirname, '..'));
}

// ─── Project name / path safety (SDL-C3) ──────────────────────────

// A project name must be a single path segment: no separators, no `..`.
// This is deliberately a blacklist (not the stricter creation-time
// `/^[a-z0-9][a-z0-9-]*[a-z0-9]$/` from scripts/init.js) so existing
// project directories keep resolving; it is paired with the
// resolveSafeProjectPath() containment check below as defense in depth.
const UNSAFE_PROJECT_NAME_RE = /\.\.|[\\/]/;

/**
 * Resolve the root directory for a named project.
 * @param {string} name — a single path segment, e.g. 'my-project'
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
  if (UNSAFE_PROJECT_NAME_RE.test(name)) {
    throw inputError(
      'INPUT_UNSAFE_PROJECT_NAME',
      `Project name "${name}" is not valid — it contains a path separator or "..".`,
      `--project takes a name, not a path: it names a directory under projects/. ` +
      `Try --project my-project. Run "sdlab init <name>" to create one.`
    );
  }
  const projectsDir = join(getWorkspaceRoot(), 'projects');
  // Defense in depth: even though the blacklist above already rejects the
  // characters needed to escape projectsDir, reuse the same containment
  // pattern as every other user-path entry point in this file so a future
  // change to the blacklist can't silently reopen the traversal.
  const root = resolveSafeProjectPath(projectsDir, name, { flagName: 'project' });
  if (!existsSync(root)) {
    throw inputError(
      'INPUT_UNKNOWN_PROJECT',
      `Project "${name}" not found at ${root}.`,
      // Two different causes land here and they need opposite responses, so
      // name both rather than assuming the project is missing. Since the
      // workspace root is resolved from the current directory, running from
      // the wrong place produces this same error — and blindly following
      // "run init" would then scaffold a duplicate project somewhere else.
      `Looking under ${projectsDir} (workspace resolved from the current directory).\n` +
      `  · Wrong directory? cd to your workspace, or set SDLAB_ROOT to it.\n` +
      `  · New project?     sdlab init ${name} --domain character-design`
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
 * Return the ComfyUI runtime workflow templates directory.
 *
 * PACKAGE-relative, deliberately — see `getPackageRoot()`. `runtime/` ships
 * inside the npm tarball; it is not workspace content. Resolving it against
 * the workspace root made `listWorkflowTemplates()` return `[]` for every
 * installed user, which is the bug `getPackageRoot()` exists to prevent.
 */
export function getRuntimeDir() {
  return join(getPackageRoot(), 'runtime');
}
