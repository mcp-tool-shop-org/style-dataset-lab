/**
 * ComfyUI HTTP API client — extracted from 5 generation scripts.
 *
 * All functions take comfyUrl as a parameter so projects can override
 * the default localhost:8188 endpoint.
 */

import { readFile } from 'node:fs/promises';
import { info } from './log.js';

const DEFAULT_URL = 'http://127.0.0.1:8188';
const MAX_POLL_MS = 600_000; // 10 minutes
const HEARTBEAT_MS = 15_000; // emit a heartbeat at most every 15s
// PB-004: if we see an unfamiliar status shape for this many consecutive
// polls without completed/error, bail with a descriptive message rather
// than hang until MAX_POLL_MS.
const UNKNOWN_STATUS_BAIL_POLLS = 30; // ~30s of unrecognized shape

// SDL-H8: per-REQUEST timeout, distinct from the per-CALL poll budget
// (timeoutMs/MAX_POLL_MS above, which only bounds the interval *between*
// requests). Without this, a ComfyUI that accepts the TCP connection and
// never responds hangs `await fetch()` forever — a hang never rejects, so
// no retry/catch logic anywhere downstream ever fires. Configurable via env
// so operators can widen it for a slow/remote ComfyUI without a code change.
const DEFAULT_REQUEST_TIMEOUT_MS = Number(process.env.SDLAB_COMFY_REQUEST_TIMEOUT_MS) || 30_000;

/**
 * fetch() with a hard per-request timeout via AbortController. Guarantees
 * the returned promise always settles (resolve or reject) within
 * `timeoutMs`, even against a server that accepts the connection and then
 * never responds. On timeout, rejects with a plain Error (not a raw
 * AbortError/DOMException) naming the URL and elapsed time, so it reads
 * like any other network failure to callers' existing catch/retry logic.
 *
 * @param {string} url
 * @param {RequestInit} [init]
 * @param {number} [timeoutMs]
 * @returns {Promise<Response>}
 */
async function fetchWithTimeout(url, init = {}, timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const start = Date.now();
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err?.name === 'AbortError') {
      const elapsedSec = ((Date.now() - start) / 1000).toFixed(1);
      throw new Error(
        `ComfyUI request timed out after ${elapsedSec}s (limit ${(timeoutMs / 1000).toFixed(1)}s): ${url}`
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * B04: comfyHealth() used to collapse EVERY failure mode into a bare
 * `false` via `catch { return false }` with no bound error. A 503 while a
 * custom node loads, a refused connection, a DNS typo, and a genuine
 * timeout all produced the identical "ComfyUI not reachable — start
 * ComfyUI" message downstream — factually wrong for the 503 (ComfyUI IS
 * reachable and running) and useless for the others (starting ComfyUI does
 * not fix a DNS typo).
 *
 * Check if ComfyUI is reachable, WITH a reason when it isn't.
 *
 * @param {string} [comfyUrl]
 * @param {{timeoutMs?: number}} [opts]
 * @returns {Promise<{ok: boolean, reason: string|null}>} reason is one of
 *   'timeout' | 'refused' | 'dns' | 'http-<status>' | 'unknown' | null (when ok)
 */
export async function comfyHealthDetailed(comfyUrl = DEFAULT_URL, opts = {}) {
  try {
    const res = await fetchWithTimeout(`${comfyUrl}/system_stats`, {}, opts.timeoutMs);
    if (res.ok) return { ok: true, reason: null };
    return { ok: false, reason: `http-${res.status}` };
  } catch (err) {
    if (/timed out/i.test(err?.message || '')) return { ok: false, reason: 'timeout' };
    const code = err?.cause?.code || err?.code;
    if (code === 'ENOTFOUND' || code === 'EAI_AGAIN') return { ok: false, reason: 'dns' };
    if (code === 'ECONNREFUSED' || code === 'ECONNRESET') return { ok: false, reason: 'refused' };
    return { ok: false, reason: 'unknown' };
  }
}

/**
 * Check if ComfyUI is reachable. Thin plain-boolean wrapper over
 * comfyHealthDetailed() — kept as a SEPARATE, unchanged-signature export
 * because 5 scripts (generate.js, generate-identity.js,
 * generate-controlnet.js, generate-ipadapter.js, painterly.js) already call
 * `if (!(await comfyHealth(...)))`; returning a richer object here would
 * make every one of those checks permanently truthy (an object is always
 * truthy) and silently disable their offline handling.
 *
 * @param {string} [comfyUrl]
 * @param {{timeoutMs?: number}} [opts]
 * @returns {Promise<boolean>}
 */
export async function comfyHealth(comfyUrl = DEFAULT_URL, opts = {}) {
  const { ok } = await comfyHealthDetailed(comfyUrl, opts);
  return ok;
}

/**
 * Submit a workflow and poll until complete.
 * @param {Object} workflow — ComfyUI prompt graph
 * @param {string} [comfyUrl]
 * @param {{ clientPrefix?: string, timeoutMs?: number, requestTimeoutMs?: number }} [opts]
 *   `timeoutMs` bounds the OVERALL poll loop (unchanged, default 10 min).
 *   `requestTimeoutMs` (SDL-H8) bounds each INDIVIDUAL fetch — the submit
 *   POST and every /history poll — so a server that never responds can't
 *   hang the whole call forever.
 * @returns {Promise<Object>} — history entry
 */
export async function submitAndWait(workflow, comfyUrl = DEFAULT_URL, opts = {}) {
  const { clientPrefix = 'sdl', timeoutMs = MAX_POLL_MS, requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS } = opts;
  const clientId = `${clientPrefix}-${Date.now()}`;

  const res = await fetchWithTimeout(`${comfyUrl}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: workflow, client_id: clientId }),
  }, requestTimeoutMs);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`ComfyUI submit failed: ${res.status} ${text}`);
  }

  const { prompt_id: promptId } = await res.json();

  const MAX_CONSECUTIVE_HISTORY_FAILURES = 5;
  let consecutiveHistoryFailures = 0;
  // PB-001: heartbeats
  let lastHeartbeatAt = Date.now();
  let announcedStart = false;
  let seenEntry = false;
  // PB-004: count polls where entry exists but status shape is unfamiliar
  let unknownStatusPolls = 0;
  let lastObservedStatus = null;
  const start = Date.now();
  while (true) {
    const now = Date.now();
    if (now - start > timeoutMs) {
      throw new Error(`ComfyUI poll timeout after ${timeoutMs / 1000}s for prompt ${promptId}`);
    }
    await new Promise(r => setTimeout(r, 1000));
    let histRes;
    try {
      // SDL-H8: bounded so a server that accepts the connection and never
      // responds lands in this catch (as an AbortError → clear timeout
      // Error) instead of hanging `await fetch()` forever.
      histRes = await fetchWithTimeout(`${comfyUrl}/history/${promptId}`, {}, requestTimeoutMs);
    } catch (err) {
      consecutiveHistoryFailures++;
      if (consecutiveHistoryFailures >= MAX_CONSECUTIVE_HISTORY_FAILURES) {
        throw new Error(
          `ComfyUI history endpoint unreachable after ${MAX_CONSECUTIVE_HISTORY_FAILURES} consecutive attempts for prompt ${promptId}: ${err.message}`
        );
      }
      continue;
    }
    if (!histRes.ok) {
      consecutiveHistoryFailures++;
      if (consecutiveHistoryFailures >= MAX_CONSECUTIVE_HISTORY_FAILURES) {
        throw new Error(
          `ComfyUI history endpoint returned ${histRes.status} ${MAX_CONSECUTIVE_HISTORY_FAILURES} times in a row for prompt ${promptId}`
        );
      }
      continue;
    }
    // SDL-L3: histRes.json() used to sit outside the retry block above, so
    // a 200-OK non-JSON body (e.g. a proxy error page) threw a raw
    // SyntaxError here, uncaught, permanently failing the image the
    // adjacent 5-strike tolerance would otherwise have recovered from.
    let history;
    try {
      history = await histRes.json();
    } catch (err) {
      consecutiveHistoryFailures++;
      if (consecutiveHistoryFailures >= MAX_CONSECUTIVE_HISTORY_FAILURES) {
        throw new Error(
          `ComfyUI history endpoint returned an unparseable response ${MAX_CONSECUTIVE_HISTORY_FAILURES} times in a row for prompt ${promptId}: ${err.message}`
        );
      }
      continue;
    }
    consecutiveHistoryFailures = 0;
    const entry = history[promptId];

    // PB-001: emit heartbeats so the user knows the pipeline isn't hung.
    const elapsedSec = Math.round((Date.now() - start) / 1000);
    const heartbeatDue = Date.now() - lastHeartbeatAt >= HEARTBEAT_MS;
    if (!entry) {
      // Queued on ComfyUI but not yet visible in /history.
      if (!announcedStart) {
        info(`ComfyUI: queued (prompt ${promptId})`);
        announcedStart = true;
        lastHeartbeatAt = Date.now();
      } else if (heartbeatDue) {
        info(`ComfyUI: queued, waiting... (${elapsedSec}s)`);
        lastHeartbeatAt = Date.now();
      }
      continue;
    }

    if (!seenEntry) {
      seenEntry = true;
      info(`ComfyUI: generating... (prompt ${promptId})`);
      lastHeartbeatAt = Date.now();
    } else if (heartbeatDue) {
      info(`ComfyUI: generating... (${elapsedSec}s elapsed)`);
      lastHeartbeatAt = Date.now();
    }

    // PB-004: success signals — accept both completed===true and status_str==='success'
    // (future-proof for schema drift where one may change without the other).
    if (entry.status?.completed === true || entry.status?.status_str === 'success') {
      info(`ComfyUI: completed in ${elapsedSec}s`);
      return entry;
    }

    // PB-004: known failure signals — bail immediately.
    if (entry.status?.status_str === 'error') {
      throw new Error(`ComfyUI generation failed: ${JSON.stringify(entry.status)}`);
    }
    if (entry.status?.execution_error || entry.execution_error) {
      const errObj = entry.status?.execution_error || entry.execution_error;
      throw new Error(`ComfyUI execution error for prompt ${promptId}: ${JSON.stringify(errObj)}`);
    }

    // PB-004: the entry exists but matches neither a known success nor
    // a known failure. This is the schema-drift hang scenario — count
    // consecutive unknown-shape polls and bail with context.
    const statusStr = entry.status?.status_str ?? null;
    lastObservedStatus = entry.status ?? null;
    unknownStatusPolls++;
    if (unknownStatusPolls >= UNKNOWN_STATUS_BAIL_POLLS) {
      throw new Error(
        `ComfyUI returned an unrecognized status shape for prompt ${promptId} ` +
        `after ${unknownStatusPolls} polls (status_str=${JSON.stringify(statusStr)}). ` +
        `This usually means the ComfyUI history schema changed. ` +
        `Observed status: ${JSON.stringify(lastObservedStatus)}`
      );
    }
  }
}

/**
 * Download a generated image from ComfyUI.
 * @param {string} filename
 * @param {string} [subfolder]
 * @param {string} [comfyUrl]
 * @param {string} [type='output']
 * @param {{timeoutMs?: number}} [opts]
 * @returns {Promise<Buffer>}
 */
export async function downloadImage(filename, subfolder, comfyUrl = DEFAULT_URL, type = 'output', opts = {}) {
  const ALLOWED_TYPES = ['output', 'input', 'temp'];
  if (!ALLOWED_TYPES.includes(type)) {
    throw new Error(`Invalid ComfyUI image type "${type}" — must be one of: ${ALLOWED_TYPES.join(', ')}`);
  }
  if (typeof comfyUrl !== 'string' || comfyUrl.length === 0 || !/^https?:\/\//i.test(comfyUrl)) {
    throw new Error(`Invalid comfyUrl "${comfyUrl}" — must start with http:// or https://`);
  }
  const url = `${comfyUrl}/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(subfolder || '')}&type=${encodeURIComponent(type)}`;
  const res = await fetchWithTimeout(url, {}, opts.timeoutMs);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

/**
 * Upload an image to ComfyUI's input folder.
 * @param {string} filePath — local file to upload
 * @param {string} filename — name to assign in ComfyUI
 * @param {string} [comfyUrl]
 * @param {{timeoutMs?: number}} [opts]
 * @returns {Promise<string>} — assigned name from ComfyUI
 */
export async function uploadImage(filePath, filename, comfyUrl = DEFAULT_URL, opts = {}) {
  const data = await readFile(filePath);
  const formData = new FormData();
  formData.append('image', new Blob([data], { type: 'image/png' }), filename);
  formData.append('overwrite', 'true');

  const res = await fetchWithTimeout(`${comfyUrl}/upload/image`, {
    method: 'POST',
    body: formData,
  }, opts.timeoutMs);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${res.status} ${text}`);
  }

  const result = await res.json();
  return result.name;
}
