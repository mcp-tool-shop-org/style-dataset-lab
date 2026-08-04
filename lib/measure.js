/**
 * Measure — orchestration for `sdlab measure`: resolve which images to
 * measure, shell out to scripts/measure_image.py for the actual pixel math,
 * and write the resulting numbers onto records.
 *
 * MEASUREMENT, NOT VERDICT (same spirit as lib/critique-engine.js's H2 fix):
 * this module attaches a `measurements` block to a record. It never touches
 * `judgment`, `canon`, or any pass/fail/approved/rejected field, and it
 * never invents one. See scripts/measure_image.py's module docstring for
 * the full port rationale (ported from the salt-road measure-palette.py /
 * measure-texture.py instruments; DISTS/StyleLoss perceptual distance is
 * deliberately out of scope — needs torch+piq).
 *
 * Python is an OPTIONAL runtime dependency of this ONE feature, not of the
 * package (mirrors scripts/qwen_generate.py's relationship to the rest of
 * sdlab, and tests/cli-scripts/qwen-python-parity.test.js's detection
 * pattern, adopted here as findPython()/checkPythonDeps() so both
 * scripts/measure.js and tests/lib-dataset/measure.test.js share one
 * implementation instead of each hand-rolling their own).
 */

import { spawnSync } from 'node:child_process';
import {
  existsSync, readFileSync, statSync, readdirSync, writeFileSync, mkdtempSync, rmSync,
} from 'node:fs';
import { readFile, writeFile, rename, unlink } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { tmpdir } from 'node:os';
import { getPackageRoot, resolveSafeProjectPath } from './paths.js';
import { inputError, runtimeError } from './errors.js';

// ─── Identity / provenance constants (mirrors lib/verifier.js's
// RULE_BASED_JUDGE / HUMAN_JUDGE naming discipline — "who produced this
// number" gets a stable id the same way "who judged this" does) ──────────

export const MEASURE_TOOL_ID = 'sdlab-measure-v1';
export const MEASURE_SCHEMA_VERSION = '1.0.0';

const IMAGE_EXT_RE = /\.(png|jpe?g)$/i;

// Ported verbatim from measure-palette.py's saturated-pixel gate — see
// scripts/measure_image.py's module docstring for the "ignore greys/darks"
// rationale. Kept in sync with the Python-side defaults by hand (both files
// document the same origin; there is no cross-language pinning contract
// here the way there is for comfy_workflow_sha, since these are STATIC
// defaults, not per-run computed values).
const DEFAULT_SAT_MIN = 0.22;
const DEFAULT_VAL_MIN = 0.18;
const DEFAULT_HUE_TOLERANCE_DEG = 20;

const REQUIRED_PY_MODULES = ['PIL', 'numpy', 'scipy'];

const MEASURE_SCRIPT = join(getPackageRoot(), 'scripts', 'measure_image.py');

// ─── Python environment detection ──────────────────────────────────────

/**
 * Locate a working Python interpreter. Precedence mirrors the rest of this
 * codebase's env-var-override convention (paths.js's SDLAB_ROOT resolution:
 * cheapest/most-explicit signal first): SDLAB_PYTHON env var if set, else
 * try "python" then "python3" on PATH. Returns the command string to spawn,
 * or null if nothing worked.
 * @param {NodeJS.ProcessEnv} [env]
 * @returns {string|null}
 */
export function findPython(env = process.env) {
  const candidates = env.SDLAB_PYTHON ? [env.SDLAB_PYTHON] : ['python', 'python3'];
  for (const cmd of candidates) {
    const res = spawnSync(cmd, ['--version'], { encoding: 'utf-8' });
    if (res.status === 0) return cmd;
  }
  return null;
}

/**
 * Probe whether `pythonCmd` has the packages measure_image.py needs.
 * Reports EVERY missing module in one pass (not just the first import
 * failure) so the resulting error names all of them at once.
 * @param {string} pythonCmd
 * @param {{modules?: string[]}} [opts] — override the probed module list (tests use this)
 * @returns {{ok: boolean, missing: string[]}}
 */
export function checkPythonDeps(pythonCmd, { modules = REQUIRED_PY_MODULES } = {}) {
  const probe =
    'import json\n' +
    'mods = {}\n' +
    `for m in ${JSON.stringify(modules)}:\n` +
    '    try:\n' +
    '        __import__(m)\n' +
    '        mods[m] = True\n' +
    '    except ImportError:\n' +
    '        mods[m] = False\n' +
    'print(json.dumps(mods))\n';
  const res = spawnSync(pythonCmd, ['-c', probe], { encoding: 'utf-8' });
  if (res.status !== 0) {
    return { ok: false, missing: [...modules], raw: (res.stderr || res.error?.message || 'probe failed').trim() };
  }
  let parsed;
  try {
    parsed = JSON.parse((res.stdout || '').trim());
  } catch {
    return { ok: false, missing: [...modules], raw: (res.stdout || '').trim() };
  }
  const missing = modules.filter((m) => !parsed[m]);
  return { ok: missing.length === 0, missing };
}

/**
 * Throwing convenience wrapper for the CLI boundary: locate Python and
 * verify its deps, or fail with a clear, actionable SdlabError naming
 * exactly what is missing. This is the ONLY function in this module that
 * throws on a missing/incomplete Python environment — findPython() and
 * checkPythonDeps() stay pure so tests can drive every branch directly.
 * @param {NodeJS.ProcessEnv} [env]
 * @returns {string} the python command to use
 */
export function assertMeasurementPrereqs(env = process.env) {
  const python = findPython(env);
  if (!python) {
    throw runtimeError(
      'RUNTIME_PYTHON_MISSING',
      'Python was not found on PATH (tried "python", "python3").',
      'sdlab measure needs Python 3.9+ with Pillow, numpy, and scipy for image measurement ' +
        '(see scripts/measure_image.py). Install Python and ensure it is on PATH, or set ' +
        'SDLAB_PYTHON to an explicit interpreter path.'
    );
  }
  const deps = checkPythonDeps(python);
  if (!deps.ok) {
    throw runtimeError(
      'RUNTIME_PYTHON_DEPS_MISSING',
      `Python found (${python}) but missing required package(s): ${deps.missing.join(', ')}.`,
      `Install them: pip install pillow numpy scipy${deps.raw ? ` (probe said: ${deps.raw})` : ''}`
    );
  }
  return python;
}

// ─── Target resolution ──────────────────────────────────────────────────

/**
 * Minimal `*`/`?` glob-to-RegExp. No npm glob dependency exists in this
 * package (checked before writing this — lib/ and scripts/ have none) and
 * this file may not add one (package.json is outside this feature's
 * exclusive file ownership), so record-id matching gets a small hand-rolled
 * matcher instead of a library.
 */
function globToRegExp(pattern) {
  let out = '';
  for (const ch of pattern) {
    if (ch === '*') out += '.*';
    else if (ch === '?') out += '.';
    else out += ch.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${out}$`);
}

/**
 * Resolve the `<dir-or-record-glob>` positional into a concrete list of
 * {id, recordPath, imagePath} targets.
 *
 *   - If it resolves to an existing directory (inside the project — see
 *     resolveSafeProjectPath), every *.png/*.jpg/*.jpeg inside is paired
 *     with records/<stem>.json by filename stem. Images with no matching
 *     record are reported in `skipped`, never silently dropped (mirrors
 *     lib/runtime-runs.js listRuns()'s B01 fix: always report a count,
 *     detail under --verbose).
 *   - Otherwise it is treated as a glob PATTERN matched against record ids
 *     under <project>/records/*.json; each match's image comes from that
 *     record's own `asset_path` (a trusted, already-on-disk field — joined
 *     plainly, same as curate.js does with record.asset_path, not run
 *     through resolveSafeProjectPath a second time).
 *
 * @param {string} projectRoot
 * @param {string} targetArg
 * @returns {{targets: Array<{id:string, recordPath:string, imagePath:string}>, skipped: Array<{id:string, reason:string}>}}
 */
export function resolveMeasureTargets(projectRoot, targetArg) {
  if (!targetArg) {
    throw inputError(
      'INPUT_MISSING_ARGS',
      'sdlab measure requires a <dir-or-record-glob> positional argument.',
      'Example: sdlab measure outputs/approved --project salt-road, or ' +
        'sdlab measure "styleset_p*" --project salt-road (quote glob patterns so your shell does not expand them).'
    );
  }

  const recordsDir = join(projectRoot, 'records');
  // Security boundary FIRST: whether targetArg turns out to be a directory
  // or a glob pattern, an escape attempt (`..`, an absolute path outside
  // the project) is rejected before either interpretation is considered.
  const asPath = resolveSafeProjectPath(projectRoot, targetArg, { flagName: 'target' });

  const targets = [];
  const skipped = [];
  const isDir = existsSync(asPath) && statSync(asPath).isDirectory();

  if (isDir) {
    const files = readdirSync(asPath, { withFileTypes: true })
      .filter((e) => e.isFile() && IMAGE_EXT_RE.test(e.name))
      .map((e) => e.name)
      .sort();
    for (const file of files) {
      const id = file.replace(IMAGE_EXT_RE, '');
      const recordPath = join(recordsDir, `${id}.json`);
      if (existsSync(recordPath)) {
        targets.push({ id, recordPath, imagePath: join(asPath, file) });
      } else {
        skipped.push({ id, reason: `no matching record at records/${id}.json` });
      }
    }
  } else {
    const re = globToRegExp(targetArg);
    const files = existsSync(recordsDir) ? readdirSync(recordsDir).filter((f) => f.endsWith('.json')) : [];
    for (const file of files) {
      const id = file.slice(0, -'.json'.length);
      if (!re.test(id)) continue;
      const recordPath = join(recordsDir, file);
      const record = JSON.parse(readFileSync(recordPath, 'utf-8'));
      if (!record.asset_path) {
        skipped.push({ id, reason: 'record has no asset_path' });
        continue;
      }
      targets.push({ id, recordPath, imagePath: join(projectRoot, record.asset_path) });
    }
  }

  if (targets.length === 0) {
    throw inputError(
      'INPUT_NO_MATCHES',
      `No records matched "${targetArg}" under ${recordsDir}.`,
      isDir
        ? 'The directory exists but no image inside it has a matching records/<id>.json.'
        : 'Check the glob pattern (quote it so your shell does not expand it), or pass an existing directory of images instead.'
    );
  }

  return { targets, skipped };
}

// ─── Anchors ─────────────────────────────────────────────────────────────

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/**
 * Load a palette anchor config from `--anchors <path>`.
 *
 * constitution.json carries no hex/numeric palette data for either salt-road
 * or star-freight (checked directly before building this — both files are
 * qualitative rule descriptions with rationale templates, not colour
 * values; the actual hex anchors salt-road uses live in prose in
 * canon/salt-road-art-contract.md, not in machine-readable config). So this
 * is a real `--anchors` flag, not a schema invented to route around a
 * missing feature.
 *
 * Unlike --source/--outputs elsewhere in this codebase (which legitimately
 * reference shared cross-project directories, hence their REPO_ROOT-scoped
 * containment), --anchors is scoped to the PROJECT root: anchor definitions
 * are project-specific canon data, same as constitution.json/lanes.json.
 *
 * @param {string|undefined} anchorsFlag — raw --anchors value, or undefined
 * @param {string} projectRoot
 * @returns {{anchors: Array<{name:string,hex:string}>, hue_tolerance_deg: number, sat_min: number, val_min: number, source: string|null}}
 */
export function loadAnchors(anchorsFlag, projectRoot) {
  if (!anchorsFlag) {
    return {
      anchors: [],
      hue_tolerance_deg: DEFAULT_HUE_TOLERANCE_DEG,
      sat_min: DEFAULT_SAT_MIN,
      val_min: DEFAULT_VAL_MIN,
      source: null,
    };
  }

  const absPath = resolveSafeProjectPath(projectRoot, anchorsFlag, { flagName: 'anchors' });
  if (!existsSync(absPath)) {
    throw inputError('INPUT_ANCHORS_NOT_FOUND', `--anchors file not found: ${absPath}`);
  }
  let data;
  try {
    data = JSON.parse(readFileSync(absPath, 'utf-8'));
  } catch (err) {
    throw inputError('INPUT_INVALID_JSON', `--anchors file is not valid JSON: ${absPath} (${err.message})`);
  }
  const anchors = Array.isArray(data) ? data : data.anchors;
  if (!Array.isArray(anchors) || anchors.length === 0) {
    throw inputError(
      'INPUT_BAD_ANCHORS',
      `${absPath} must contain a non-empty "anchors" array of {name, hex}.`,
      'Example: { "anchors": [{"name":"ochre-warm","hex":"#c9a877"}] }'
    );
  }
  for (const a of anchors) {
    if (!a || typeof a.name !== 'string' || !a.name || typeof a.hex !== 'string' || !HEX_RE.test(a.hex)) {
      throw inputError(
        'INPUT_BAD_ANCHORS',
        `Invalid anchor entry in ${absPath}: ${JSON.stringify(a)}`,
        'Each anchor needs a "name" string and a "hex" color like "#c9a877".'
      );
    }
  }
  return {
    anchors,
    hue_tolerance_deg: data.hue_tolerance_deg ?? DEFAULT_HUE_TOLERANCE_DEG,
    sat_min: data.sat_min ?? DEFAULT_SAT_MIN,
    val_min: data.val_min ?? DEFAULT_VAL_MIN,
    source: relative(projectRoot, absPath),
  };
}

// ─── Python invocation ───────────────────────────────────────────────────

/**
 * Spawn scripts/measure_image.py once for a whole batch of images (one
 * process, not one-per-image — keeps interpreter-startup overhead off the
 * per-image cost). Writes the request to a temp file, mirroring
 * scripts/qwen_generate.py's `--wave <path>` handoff shape.
 *
 * @param {string} pythonCmd
 * @param {{images: Array<{id:string,path:string}>, anchors?: Array, hue_tolerance_deg?: number, sat_min?: number, val_min?: number}} request
 * @returns {{schema_version, tool, results: Array, errors: Array, ok_count: number, error_count: number}}
 */
export function runPythonMeasurement(pythonCmd, request) {
  const dir = mkdtempSync(join(tmpdir(), 'sdlab-measure-'));
  try {
    const requestPath = join(dir, 'request.json');
    const outPath = join(dir, 'result.json');
    writeFileSync(requestPath, JSON.stringify(request, null, 2));

    const res = spawnSync(pythonCmd, [MEASURE_SCRIPT, '--request', requestPath, '--out', outPath], {
      encoding: 'utf-8',
    });

    if (!existsSync(outPath)) {
      throw runtimeError(
        'RUNTIME_MEASURE_FAILED',
        `measure_image.py did not produce a result (exit ${res.status ?? 'unknown'}).`,
        (res.stderr || res.stdout || '').trim().slice(0, 2000) || 'Run with --debug for detail.'
      );
    }
    return JSON.parse(readFileSync(outPath, 'utf-8'));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

// ─── Record writing (atomic) ─────────────────────────────────────────────

/**
 * Temp-file-in-same-dir + rename — the exact pattern documented in
 * lib/runtime-runs.js's atomicWriteJson (that function is module-private
 * there, and is duplicated ad hoc in lib/batch-runs.js and
 * lib/reingest-selected.js too — this file cannot import a shared version
 * because none is exported anywhere in the codebase; extracting one would
 * mean editing those files, which sit outside this feature's exclusive file
 * ownership). Same tmp-name scheme as all three existing copies, for
 * consistency: `${targetPath}.tmp-${pid}-${timestamp}`.
 */
async function atomicWriteJson(targetPath, obj) {
  const tmpPath = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  const body = JSON.stringify(obj, null, 2) + '\n';
  try {
    await writeFile(tmpPath, body);
    await rename(tmpPath, targetPath);
  } catch (err) {
    try {
      await unlink(tmpPath);
    } catch {
      /* ignore */
    }
    throw err;
  }
}

/**
 * Build the `measurements` block and (unless dryRun) write it onto each
 * matched record. Idempotent by design — an unchanged image + unchanged
 * code reproduces the exact same palette/texture numbers on every run;
 * only `measured_at` moves forward, the same way re-running `sdlab curate`
 * or `sdlab bind` overwrites the prior judgment/binding rather than
 * appending to a history log (see the sdlab compensators table).
 *
 * @param {Array<{id:string, recordPath:string}>} targets
 * @param {{results: Array, errors: Array}} pyResult
 * @param {{anchorsSource: string|null, dryRun: boolean}} opts
 * @returns {Promise<{applied: Array<{id:string, measurements:Object}>, failed: Array<{id:string, error:string}>}>}
 */
export async function applyMeasurements(targets, pyResult, { anchorsSource = null, dryRun = false } = {}) {
  const byId = new Map((pyResult.results || []).map((r) => [r.id, r]));
  const errById = new Map((pyResult.errors || []).map((e) => [e.id, e]));
  const applied = [];
  const failed = [];

  for (const t of targets) {
    const ok = byId.get(t.id);
    if (!ok) {
      const err = errById.get(t.id);
      failed.push({ id: t.id, error: err?.error || 'no result returned for this image' });
      continue;
    }

    const measurements = {
      measured_at: new Date().toISOString(),
      tool: MEASURE_TOOL_ID,
      schema_version: MEASURE_SCHEMA_VERSION,
      anchors_source: anchorsSource,
      image: ok.image,
      palette: ok.palette,
      texture: ok.texture,
    };
    applied.push({ id: t.id, measurements });

    if (!dryRun) {
      const record = JSON.parse(await readFile(t.recordPath, 'utf-8'));
      record.measurements = measurements;
      await atomicWriteJson(t.recordPath, record);
    }
  }

  return { applied, failed };
}
