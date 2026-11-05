/**
 * Lane 1 (render) kit — VM bootstrap guards, weight manifest staging by sha256
 * + cleared SPDX licence, Qwen LoRA-aware job compiler, durable queue with
 * idempotent resume after kill, periodic copy-back, and PNG tEXt provenance
 * stamping + immediate read-back verification (DESIGN-v3 §3.1, §3.5, §4.4, §7,
 * G1–G3, G8).
 */

import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  appendFileSync,
  copyFileSync,
} from 'node:fs';
import { dirname, join } from 'node:path';
import { inputError } from './errors.js';
import { comfyWorkflowSha } from './run-manifest.js';
import {
  QWEN_DEFAULTS,
  buildQwenGraph,
  buildStubFixtureGraph,
} from './adapters/comfyui-workflows.js';
import { stampPngProvenance, verifyPngProvenance } from './png-meta.js';

export const LANE1_PYTHON_VERSION = '3.14.9';
export const LANE1_UV_PIN = 'uv==0.13.5';
export const STUDIO_OWNER = 'mcp-tool-shop';
export const STUDIO_LICENCE = 'CC-BY-4.0';

export const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

export const CLEARED_LANE1_LICENCES = new Set([
  'Apache-2.0',
  'MIT',
  'BSD-2-Clause',
  'BSD-3-Clause',
  'CC0-1.0',
  'CC-BY-4.0',
]);

function normalizeSha256(val) {
  if (typeof val !== 'string') return null;
  const trimmed = val.trim().toLowerCase();
  const hex = trimmed.startsWith('sha256:') ? trimmed.slice(7) : trimmed;
  if (!/^[0-9a-f]{64}$/.test(hex)) return null;
  return `sha256:${hex}`;
}

function sha256Buffer(buf) {
  return 'sha256:' + createHash('sha256').update(buf).digest('hex');
}

/**
 * Enforce that ComfyUI is bound to loopback only (§3.1, §6).
 *
 * @param {string} comfyUrl
 * @returns {URL}
 */
export function assertLoopbackComfyUrl(comfyUrl) {
  let parsed;
  try {
    parsed = new URL(comfyUrl);
  } catch {
    throw inputError(
      'LANE1_NON_LOOPBACK_BIND',
      `Invalid ComfyUI URL "${comfyUrl}". Must be http://127.0.0.1:<port>.`
    );
  }
  const host = parsed.hostname.toLowerCase();
  if (!LOOPBACK_HOSTS.has(host)) {
    throw inputError(
      'LANE1_NON_LOOPBACK_BIND',
      `ComfyUI URL "${comfyUrl}" binds to non-loopback host "${host}". Colab terms require loopback-only (127.0.0.1).`
    );
  }
  return parsed;
}

/**
 * Inspect listening sockets and verify that the ComfyUI port (and any listed
 * service port) is bound strictly to loopback (127.0.0.1 / ::1).
 *
 * @param {Array<string|{address: string, port?: number}>} listeningSockets
 * @param {number} [comfyPort=8188]
 * @returns {{ ok: true, sockets: string[] }}
 */
export function verifyLoopbackSockets(listeningSockets = [], comfyPort = 8188) {
  if (!Array.isArray(listeningSockets) || listeningSockets.length === 0) {
    throw inputError(
      'LANE1_NON_LOOPBACK_SOCKET',
      'Listening socket list is empty; window.json must record the verified loopback socket list.'
    );
  }

  const normalized = [];
  let sawComfyPortLoopback = false;

  for (const item of listeningSockets) {
    const raw =
      typeof item === 'string'
        ? item.trim()
        : `${item?.address || ''}${item?.port ? `:${item.port}` : ''}`;
    normalized.push(raw);

    // Match host:port at end of string
    const match = /^(.*):(\d+)$/.exec(raw);
    if (!match) continue;
    const hostPart = match[1].trim().toLowerCase();
    const portNum = Number(match[2]);

    const isWildcard =
      hostPart === '0.0.0.0' ||
      hostPart === '*' ||
      hostPart === '::' ||
      hostPart === '[::]' ||
      hostPart === '[::0]';
    const isLoopback = LOOPBACK_HOSTS.has(hostPart) || hostPart.startsWith('127.');

    if (portNum === Number(comfyPort)) {
      if (isWildcard || !isLoopback) {
        throw inputError(
          'LANE1_NON_LOOPBACK_SOCKET',
          `ComfyUI port ${comfyPort} is listening on non-loopback address "${raw}".`
        );
      }
      sawComfyPortLoopback = true;
    } else if (isWildcard) {
      throw inputError(
        'LANE1_NON_LOOPBACK_SOCKET',
        `Wildcard listening socket "${raw}" detected on VM.`
      );
    }
  }

  if (!sawComfyPortLoopback) {
    throw inputError(
      'LANE1_NON_LOOPBACK_SOCKET',
      `ComfyUI loopback socket 127.0.0.1:${comfyPort} was not found in listening_sockets.`
    );
  }

  return { ok: true, sockets: normalized };
}

/**
 * Stage and verify model weights by sha256 and cleared SPDX licence from a
 * manifest (§3.1, §5.6, G1, G4).
 *
 * @param {Object} opts
 * @param {Array<Object>} opts.manifest
 * @param {string} [opts.stagingDir]
 * @param {boolean} [opts.verifyFiles=true]
 * @returns {Array<Object>}
 */
export function stageWeightsFromManifest({ manifest, stagingDir, verifyFiles = true }) {
  if (!Array.isArray(manifest) || manifest.length === 0) {
    throw inputError('LANE1_WEIGHT_MANIFEST_EMPTY', 'Weight manifest must be a non-empty array.');
  }

  const results = [];
  for (const entry of manifest) {
    const name = entry?.name;
    if (typeof name !== 'string' || name.trim().length === 0) {
      throw inputError('LANE1_WEIGHT_SHA_MISSING', 'Weight entry is missing "name".');
    }
    const expectedSha = normalizeSha256(entry.sha256);
    if (!expectedSha) {
      throw inputError(
        'LANE1_WEIGHT_SHA_MISSING',
        `Weight "${name}" is missing a valid 64-hex sha256 digest.`
      );
    }
    const licenceId = entry.licence_id;
    if (
      typeof licenceId !== 'string' ||
      !CLEARED_LANE1_LICENCES.has(licenceId) ||
      typeof entry.licence_url !== 'string' ||
      !entry.licence_url.trim() ||
      typeof entry.date_read !== 'string' ||
      !entry.date_read.trim()
    ) {
      throw inputError(
        'LANE1_WEIGHT_LICENCE_INVALID',
        `Weight "${name}" must carry a cleared SPDX licence_id (${[...CLEARED_LANE1_LICENCES].join(', ')}), licence_url, and date_read (got "${licenceId}").`
      );
    }

    let verified = false;
    let resolvedPath = entry.local_path || (stagingDir ? join(stagingDir, name) : null);
    if (verifyFiles && resolvedPath) {
      if (!existsSync(resolvedPath)) {
        throw inputError(
          'LANE1_WEIGHT_FILE_MISSING',
          `Weight "${name}" not found at "${resolvedPath}".`
        );
      }
      const actualSha = sha256Buffer(readFileSync(resolvedPath));
      if (actualSha !== expectedSha) {
        throw inputError(
          'LANE1_WEIGHT_SHA_MISMATCH',
          `Weight "${name}" sha256 mismatch: got ${actualSha}, expected ${expectedSha}.`
        );
      }
      verified = true;
    }

    results.push({
      role: entry.role || 'model',
      name,
      repo: entry.repo || null,
      revision: entry.revision || null,
      sha256: expectedSha,
      licence_id: licenceId,
      licence_url: entry.licence_url,
      date_read: entry.date_read,
      local_path: resolvedPath,
      verified,
    });
  }
  return results;
}

/**
 * Build and validate the §7 `window.json` record for a Lane 1 (or Lane 3) window.
 *
 * @param {Object} opts
 * @returns {Object}
 */
export function buildWindowRecord(opts = {}) {
  const {
    window_id,
    lane = 'render',
    card = 'CPU',
    vm_gate = {},
    system_python = '3.13.16',
    python = LANE1_PYTHON_VERSION,
    python_sha256,
    uv = 'uv 0.13.5',
    comfyui_commit = null,
    comfy_headless_version = '3.1.0',
    comfy_bind = '127.0.0.1:8188',
    listening_sockets = ['127.0.0.1:8188'],
    override_sha256 = null,
    cap = 0.05,
    wall_s = 3000,
    margin = 0.01,
    start_balance = null,
    end_balance = null,
    rate_measured = null,
    opened_at = new Date().toISOString(),
    closed_at = null,
    allowNonPinnedPython = false,
  } = opts;

  if (!window_id || typeof window_id !== 'string') {
    throw inputError('LANE1_WINDOW_INVALID', 'window.json requires a non-empty "window_id".');
  }
  if (!allowNonPinnedPython && python !== LANE1_PYTHON_VERSION) {
    throw inputError(
      'LANE1_PYTHON_VERSION_MISMATCH',
      `window.json venv python must be "${LANE1_PYTHON_VERSION}", got "${python}".`
    );
  }
  assertLoopbackComfyUrl(comfy_bind.startsWith('http') ? comfy_bind : `http://${comfy_bind}`);
  const portMatch = /:(\d+)$/.exec(comfy_bind);
  const comfyPort = portMatch ? Number(portMatch[1]) : 8188;
  const checkedSockets = verifyLoopbackSockets(listening_sockets, comfyPort);

  return {
    window_id,
    lane,
    card,
    vm_gate,
    system_python,
    python,
    python_sha256: normalizeSha256(python_sha256) || python_sha256 || null,
    uv,
    comfyui_commit,
    comfy_headless_version,
    comfy_bind,
    listening_sockets: checkedSockets.sockets,
    override_sha256: normalizeSha256(override_sha256) || override_sha256 || null,
    cap,
    wall_s,
    margin,
    start_balance,
    end_balance,
    rate_measured,
    opened_at,
    closed_at,
  };
}

function validatePinComponent(comp, label) {
  if (!comp || typeof comp !== 'object') {
    throw inputError('LANE1_PIN_INVALID', `Missing model pin for "${label}".`);
  }
  const sha = normalizeSha256(comp.sha256);
  if (!sha) {
    throw inputError('LANE1_PIN_INVALID', `Model pin "${label}" is missing a valid sha256.`);
  }
  if (!comp.licence_id || !CLEARED_LANE1_LICENCES.has(comp.licence_id)) {
    throw inputError(
      'LANE1_PIN_INVALID',
      `Model pin "${label}" has uncleared licence_id "${comp.licence_id}".`
    );
  }
  if (!comp.licence_url || !comp.date_read) {
    throw inputError(
      'LANE1_PIN_INVALID',
      `Model pin "${label}" must include licence_url and date_read.`
    );
  }
  return {
    name: comp.name,
    sha256: sha,
    licence_id: comp.licence_id,
    licence_url: comp.licence_url,
    date_read: comp.date_read,
    ...(comp.weight !== undefined ? { weight: Number(comp.weight) } : {}),
  };
}

/**
 * Compile `jobs.jsonl` rows for a Lane 1 render window (§7).
 *
 * @param {Object} opts
 * @returns {{ jobs: Array<Object>, jobs_sha256: string }}
 */
export function compileLane1Jobs({
  runId,
  canonSha,
  entries,
  modelPins,
  mode = 'qwen',
  width = QWEN_DEFAULTS.width,
  height = QWEN_DEFAULTS.height,
  steps = QWEN_DEFAULTS.steps,
  cfg = QWEN_DEFAULTS.cfg,
  sampler = QWEN_DEFAULTS.sampler,
  scheduler = QWEN_DEFAULTS.scheduler,
  shift = QWEN_DEFAULTS.shift,
  loras = [],
}) {
  if (!runId || typeof runId !== 'string') {
    throw inputError('LANE1_JOBS_INVALID', 'compileLane1Jobs requires a non-empty runId.');
  }
  const normCanonSha = normalizeSha256(canonSha);
  if (!normCanonSha) {
    throw inputError('LANE1_JOBS_INVALID', 'compileLane1Jobs requires a 64-hex canonSha.');
  }
  if (!Array.isArray(entries) || entries.length === 0) {
    throw inputError('LANE1_JOBS_INVALID', 'compileLane1Jobs requires a non-empty entries array.');
  }

  const normalizedPins = {
    base: validatePinComponent(modelPins?.base, 'base'),
    text_encoder: validatePinComponent(modelPins?.text_encoder, 'text_encoder'),
    vae: validatePinComponent(modelPins?.vae, 'vae'),
    loras: (modelPins?.loras || loras || []).map((l, i) => validatePinComponent(l, `loras[${i}]`)),
  };

  const jobs = entries.map((entry, idx) => {
    const jobId = entry.job_id || `job_${String(idx + 1).padStart(3, '0')}`;
    const entryId = entry.entry_id;
    const entrySha = normalizeSha256(entry.entry_sha256);
    if (!entryId || !entrySha) {
      throw inputError(
        'LANE1_JOBS_INVALID',
        `Entry at index ${idx} is missing entry_id or valid entry_sha256.`
      );
    }
    const seed = Number.isFinite(entry.seed) ? entry.seed : idx + 1;
    const prompt = entry.prompt || '';
    const negative = entry.negative ?? entry.negative_prompt ?? '';
    const jobLoras = entry.loras || normalizedPins.loras;

    const { nodes: workflow, saveNodeId } =
      mode === 'stub'
        ? buildStubFixtureGraph({
            seed,
            width: entry.width || width || 64,
            height: entry.height || height || 64,
            filenamePrefix: `sdl_${jobId}`,
          })
        : buildQwenGraph({
            prompt,
            negativePrompt: negative,
            seed,
            width: entry.width || width,
            height: entry.height || height,
            steps: entry.steps || steps,
            cfg: entry.cfg ?? cfg,
            sampler: entry.sampler || sampler,
            scheduler: entry.scheduler || scheduler,
            shift: entry.shift ?? shift,
            unet: normalizedPins.base.name,
            clip: normalizedPins.text_encoder.name,
            vae: normalizedPins.vae.name,
            loras: jobLoras,
            filenamePrefix: `sdl_${jobId}`,
          });

    const workflowSha = comfyWorkflowSha(workflow);

    return {
      job_id: jobId,
      run_id: runId,
      class: entry.class || 'default',
      prompt,
      negative,
      seed,
      width: entry.width || width,
      height: entry.height || height,
      steps: entry.steps || steps,
      cfg: entry.cfg ?? cfg,
      sampler: entry.sampler || sampler,
      scheduler: entry.scheduler || scheduler,
      shift: entry.shift ?? shift,
      template_id: mode === 'stub' ? 'stub_fixture_64' : 'qwen_txt2img_lora',
      loras: jobLoras,
      save_node_id: saveNodeId,
      workflow_sha: workflowSha,
      workflow,
      canon_sha: normCanonSha,
      entry_id: entryId,
      entry_sha256: entrySha,
      owner: STUDIO_OWNER,
      licence: STUDIO_LICENCE,
      model_pins: normalizedPins,
    };
  });

  const payload = jobs.map((j) => JSON.stringify(j)).join('\n') + '\n';
  const jobsSha256 = sha256Buffer(Buffer.from(payload, 'utf-8'));
  return { jobs, jobs_sha256: jobsSha256 };
}

/**
 * Write `jobs.jsonl` and its companion `jobs.jsonl.sha256` file.
 *
 * @param {string} jobsPath
 * @param {Array<Object>} jobs
 * @returns {{ jobsPath: string, sha256Path: string, sha256: string }}
 */
export function writeJobsJsonl(jobsPath, jobs) {
  mkdirSync(dirname(jobsPath), { recursive: true });
  const content = jobs.map((j) => JSON.stringify(j)).join('\n') + '\n';
  const sha = sha256Buffer(Buffer.from(content, 'utf-8'));
  writeFileSync(jobsPath, content, 'utf-8');
  const sha256Path = `${jobsPath}.sha256`;
  writeFileSync(sha256Path, `${sha}\n`, 'utf-8');
  return { jobsPath, sha256Path, sha256: sha };
}

/**
 * Read `jobs.jsonl` and verify its `.sha256` sidecar if present.
 *
 * @param {string} jobsPath
 * @returns {Array<Object>}
 */
export function readJobsJsonl(jobsPath) {
  const raw = readFileSync(jobsPath, 'utf-8');
  const shaPath = `${jobsPath}.sha256`;
  if (existsSync(shaPath)) {
    const expected = readFileSync(shaPath, 'utf-8').trim();
    const actual = sha256Buffer(Buffer.from(raw, 'utf-8'));
    if (expected && actual !== expected) {
      throw inputError(
        'LANE1_JOBS_SHA_MISMATCH',
        `jobs.jsonl sha256 mismatch: got ${actual}, expected ${expected}.`
      );
    }
  }
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function loadCompletedRenders(rendersPath, outDir) {
  const completed = new Map();
  if (!existsSync(rendersPath)) return completed;
  const lines = readFileSync(rendersPath, 'utf-8')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  for (const line of lines) {
    const row = JSON.parse(line);
    if (row && row.status === 'ok' && row.job_id && row.output_file) {
      const pngPath = join(outDir, row.output_file);
      if (existsSync(pngPath)) {
        const bytes = readFileSync(pngPath);
        const actualSha = sha256Buffer(bytes);
        if (actualSha === row.png_sha256) {
          try {
            verifyPngProvenance(bytes, {
              owner: row.owner,
              licence: row.licence,
              canon_sha: row.canon_sha,
              entry_id: row.entry_id,
              entry_sha256: row.entry_sha256,
              run_id: row.run_id,
            });
            completed.set(row.job_id, row);
          } catch {
            // If stamp verification fails on disk, re-render the job.
          }
        }
      }
    }
  }
  return completed;
}

function syncCopyBack({ rendersPath, currentJsonPath, outDir, copyBackDir, completedFiles }) {
  mkdirSync(copyBackDir, { recursive: true });
  if (existsSync(rendersPath)) {
    copyFileSync(rendersPath, join(copyBackDir, 'renders.jsonl'));
  }
  if (currentJsonPath && existsSync(currentJsonPath)) {
    copyFileSync(currentJsonPath, join(copyBackDir, 'current.json'));
  }
  for (const file of completedFiles) {
    const src = join(outDir, file);
    if (existsSync(src)) {
      copyFileSync(src, join(copyBackDir, file));
    }
  }
}

/**
 * Execute the durable Lane 1 render queue (`jobs.jsonl` -> `renders.jsonl`)
 * with idempotent resume, PNG tEXt stamping + immediate read-back verification,
 * and periodic copy-back (DESIGN-v3 §3.1, §4.4, §7, G2, G8, H6, H7).
 *
 * @param {Object} opts
 * @returns {Promise<Object>}
 */
export async function runLane1Queue({
  jobsPath,
  rendersPath,
  outDir,
  copyBackDir = null,
  copyBackEvery = 5,
  windowId = 'win_lane1_local',
  renderFn,
  stopAfterJobs = null,
  stripStampBeforeSave = false,
}) {
  if (typeof renderFn !== 'function') {
    throw inputError('LANE1_RENDER_FN_REQUIRED', 'runLane1Queue requires a renderFn(job) callback.');
  }
  const jobs = readJobsJsonl(jobsPath);
  mkdirSync(outDir, { recursive: true });
  mkdirSync(dirname(rendersPath), { recursive: true });

  const currentJsonPath = join(dirname(rendersPath), 'current.json');
  const completedMap = loadCompletedRenders(rendersPath, outDir);
  const completedFiles = new Set([...completedMap.values()].map((r) => r.output_file));

  let skippedCount = 0;
  let renderedCount = 0;
  let copyBackCount = 0;
  let haltedEarly = false;

  for (const job of jobs) {
    if (completedMap.has(job.job_id)) {
      skippedCount++;
      continue;
    }

    const startMs = Date.now();
    const rawPngBuf = await renderFn(job);
    const stampMeta = {
      owner: job.owner || STUDIO_OWNER,
      licence: job.licence || STUDIO_LICENCE,
      canon_sha: job.canon_sha,
      entry_id: job.entry_id,
      entry_sha256: job.entry_sha256,
      run_id: job.run_id,
      workflow_sha: job.workflow_sha,
      window_id: windowId,
    };

    const outputBytes = stripStampBeforeSave
      ? rawPngBuf
      : stampPngProvenance(rawPngBuf, stampMeta, `${job.job_id}.png`);

    const outputFile = `${job.job_id}.png`;
    const outputFullPath = join(outDir, outputFile);
    writeFileSync(outputFullPath, outputBytes);

    // H7: read back the saved PNG from disk immediately and verify its stamp!
    const savedBytes = readFileSync(outputFullPath);
    verifyPngProvenance(savedBytes, stampMeta, outputFile);

    const pngSha256 = sha256Buffer(savedBytes);
    const wallMs = Date.now() - startMs;

    const renderRow = {
      job_id: job.job_id,
      run_id: job.run_id,
      status: 'ok',
      output_file: outputFile,
      png_sha256: pngSha256,
      workflow_sha: job.workflow_sha,
      seed: job.seed,
      wall_ms: wallMs,
      window_id: windowId,
      canon_sha: job.canon_sha,
      entry_id: job.entry_id,
      entry_sha256: job.entry_sha256,
      owner: stampMeta.owner,
      licence: stampMeta.licence,
      model_pins: job.model_pins,
      stamp_verified: true,
    };

    appendFileSync(rendersPath, JSON.stringify(renderRow) + '\n', 'utf-8');
    completedFiles.add(outputFile);
    renderedCount++;

    writeFileSync(
      currentJsonPath,
      JSON.stringify(
        {
          window_id: windowId,
          run_id: job.run_id,
          last_job_id: job.job_id,
          files: ['renders.jsonl', ...completedFiles],
        },
        null,
        2
      ),
      'utf-8'
    );

    if (copyBackDir && copyBackEvery > 0 && renderedCount % copyBackEvery === 0) {
      syncCopyBack({ rendersPath, currentJsonPath, outDir, copyBackDir, completedFiles });
      copyBackCount++;
    }

    if (stopAfterJobs !== null && renderedCount >= stopAfterJobs) {
      haltedEarly = true;
      break;
    }
  }

  if (copyBackDir && !haltedEarly && renderedCount > 0 && renderedCount % copyBackEvery !== 0) {
    syncCopyBack({ rendersPath, currentJsonPath, outDir, copyBackDir, completedFiles });
    copyBackCount++;
  }

  return {
    totalJobs: jobs.length,
    renderedCount,
    skippedCount,
    copyBackCount,
    haltedEarly,
    rendersPath,
    outDir,
  };
}
