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

/**
 * Check if ComfyUI is reachable.
 * @param {string} [comfyUrl]
 * @returns {Promise<boolean>}
 */
export async function comfyHealth(comfyUrl = DEFAULT_URL) {
  try {
    const res = await fetch(`${comfyUrl}/system_stats`);
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Submit a workflow and poll until complete.
 * @param {Object} workflow — ComfyUI prompt graph
 * @param {string} [comfyUrl]
 * @param {{ clientPrefix?: string, timeoutMs?: number }} [opts]
 * @returns {Promise<Object>} — history entry
 */
export async function submitAndWait(workflow, comfyUrl = DEFAULT_URL, opts = {}) {
  const { clientPrefix = 'sdl', timeoutMs = MAX_POLL_MS } = opts;
  const clientId = `${clientPrefix}-${Date.now()}`;

  const res = await fetch(`${comfyUrl}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: workflow, client_id: clientId }),
  });

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
      histRes = await fetch(`${comfyUrl}/history/${promptId}`);
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
    consecutiveHistoryFailures = 0;
    const history = await histRes.json();
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
 * @returns {Promise<Buffer>}
 */
export async function downloadImage(filename, subfolder, comfyUrl = DEFAULT_URL, type = 'output') {
  const ALLOWED_TYPES = ['output', 'input', 'temp'];
  if (!ALLOWED_TYPES.includes(type)) {
    throw new Error(`Invalid ComfyUI image type "${type}" — must be one of: ${ALLOWED_TYPES.join(', ')}`);
  }
  if (typeof comfyUrl !== 'string' || comfyUrl.length === 0 || !/^https?:\/\//i.test(comfyUrl)) {
    throw new Error(`Invalid comfyUrl "${comfyUrl}" — must start with http:// or https://`);
  }
  const url = `${comfyUrl}/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(subfolder || '')}&type=${encodeURIComponent(type)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

/**
 * Upload an image to ComfyUI's input folder.
 * @param {string} filePath — local file to upload
 * @param {string} filename — name to assign in ComfyUI
 * @param {string} [comfyUrl]
 * @returns {Promise<string>} — assigned name from ComfyUI
 */
export async function uploadImage(filePath, filename, comfyUrl = DEFAULT_URL) {
  const data = await readFile(filePath);
  const formData = new FormData();
  formData.append('image', new Blob([data], { type: 'image/png' }), filename);
  formData.append('overwrite', 'true');

  const res = await fetch(`${comfyUrl}/upload/image`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${res.status} ${text}`);
  }

  const result = await res.json();
  return result.name;
}
