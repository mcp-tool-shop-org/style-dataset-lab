/**
 * ComfyUI HTTP API client — extracted from 5 generation scripts.
 *
 * All functions take comfyUrl as a parameter so projects can override
 * the default localhost:8188 endpoint.
 */

import { readFile } from 'node:fs/promises';

const DEFAULT_URL = 'http://127.0.0.1:8188';
const MAX_POLL_MS = 600_000; // 10 minutes

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

  const start = Date.now();
  while (true) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`ComfyUI poll timeout after ${timeoutMs / 1000}s for prompt ${promptId}`);
    }
    await new Promise(r => setTimeout(r, 1000));
    const histRes = await fetch(`${comfyUrl}/history/${promptId}`);
    if (!histRes.ok) continue;
    const history = await histRes.json();
    const entry = history[promptId];
    if (!entry) continue;
    if (entry.status?.completed) return entry;
    if (entry.status?.status_str === 'error') {
      throw new Error(`ComfyUI generation failed: ${JSON.stringify(entry.status)}`);
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
  const url = `${comfyUrl}/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(subfolder || '')}&type=${type}`;
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
