/**
 * Lane 2 canon and prompt authoring adapter (DESIGN-v3 §3.2, §9.2 item 7, §11, G10).
 *
 * Calls a local loopback OpenAI-compatible HTTP endpoint (e.g., llama-server or
 * Ollama serving Muse-Glimmer-30B-A3B-GGUF under Apache-2.0) to draft visual
 * canon entries and per-class prompts + negatives.
 *
 * Every model-authored output starts with `status: "draft"` and `judgment: null`,
 * carrying the model name, digest, SPDX licence (`Apache-2.0`), credit note,
 * `messages_sha256`, and `draft_sha256`.
 */

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { canonicalize } from './freeze-stamp.js';
import { inputError as rawInputError } from './errors.js';

function inputError(code, msg) {
  return rawInputError(code, `${code}: ${msg}`);
}

export const MIN_LLAMA_SERVER_BUILD = 10353;

export const GLIMMER_CREDIT_NOTE =
  'Canon and prompt drafting assisted by Muse-Glimmer-30B-A3B (GlimmerLabs, Apache-2.0); vision inspection via Qwen3-VL mmproj (Apache-2.0).';

export const GLIMMER_DEFAULT_MODEL = Object.freeze({
  name: 'Muse-Glimmer-30B-A3B-Q4_K_M.gguf',
  repo: 'GlimmerLabs/Muse-Glimmer-30B-A3B-GGUF',
  digest: 'sha256:' + '3'.repeat(64),
  licence_id: 'Apache-2.0',
  licence_url: 'https://huggingface.co/GlimmerLabs/Muse-Glimmer-30B-A3B-GGUF/blob/main/LICENSE',
  date_read: '2026-11-05',
  credit_note: GLIMMER_CREDIT_NOTE,
});

export const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function sha256String(str) {
  return 'sha256:' + createHash('sha256').update(str, 'utf-8').digest('hex');
}

function sha256Buffer(buf) {
  return 'sha256:' + createHash('sha256').update(buf).digest('hex');
}

function normalizeSha256(val) {
  if (typeof val !== 'string') return null;
  const trimmed = val.trim().toLowerCase();
  const hex = trimmed.startsWith('sha256:') ? trimmed.slice(7) : trimmed;
  if (!/^[0-9a-f]{64}$/.test(hex)) return null;
  return `sha256:${hex}`;
}

/**
 * Enforce that the Lane 2 LLM endpoint is strictly loopback-bound (§3.2, §6, §11.3).
 *
 * @param {string} endpointUrl
 * @returns {URL}
 */
export function assertLoopbackEndpoint(endpointUrl) {
  let parsed;
  try {
    parsed = new URL(endpointUrl);
  } catch {
    throw inputError(
      'LANE2_NON_LOOPBACK_ENDPOINT',
      `Invalid Lane 2 endpoint URL "${endpointUrl}". Must be http://127.0.0.1:<port>/...`
    );
  }
  const host = parsed.hostname.toLowerCase();
  if (!LOOPBACK_HOSTS.has(host)) {
    throw inputError(
      'LANE2_NON_LOOPBACK_ENDPOINT',
      `Lane 2 endpoint "${endpointUrl}" binds to non-loopback host "${host}". Must bind to 127.0.0.1.`
    );
  }
  return parsed;
}

/**
 * Pre-check the llama.cpp `llama-server` build (`>= b10353` for Qwen3.5 /
 * Muse-Glimmer-30B-A3B) and optional `mmproj` vision projector (§9.2 item 7, §11.3).
 *
 * @param {Object} opts
 * @param {string|number} opts.llamaServerBuild — e.g. 'b10353' or 10400
 * @param {boolean} [opts.vision=false] — whether vision inspection / plate reading is active
 * @param {string} [opts.mmprojPath]
 * @param {string} [opts.mmprojSha256]
 * @param {boolean} [opts.verifyFiles=false]
 * @returns {{ ok: true, buildNumber: number, vision: boolean, mmprojSha256: string|null }}
 */
export function verifyGlimmerRuntime({
  llamaServerBuild,
  vision = false,
  mmprojPath = null,
  mmprojSha256 = null,
  verifyFiles = false,
} = {}) {
  const rawBuild = String(llamaServerBuild ?? '').trim();
  const match = /(\d{4,6})/.exec(rawBuild);
  const buildNumber = match ? Number(match[1]) : NaN;
  if (!Number.isFinite(buildNumber) || buildNumber < MIN_LLAMA_SERVER_BUILD) {
    throw inputError(
      'LANE2_LLAMA_SERVER_TOO_OLD',
      `Muse-Glimmer-30B-A3B (Qwen3.5 architecture) requires llama-server >= b${MIN_LLAMA_SERVER_BUILD}; got "${rawBuild}".`
    );
  }

  let normalizedMmprojSha = null;
  if (vision) {
    normalizedMmprojSha = normalizeSha256(mmprojSha256);
    if (!mmprojPath || !normalizedMmprojSha) {
      throw inputError(
        'LANE2_MMPROJ_MISSING',
        'Vision mode on Muse-Glimmer-30B-A3B requires --mmproj (mmproj-F16.gguf or mmproj-BF16.gguf) with a pinned 64-hex sha256.'
      );
    }
    if (verifyFiles) {
      if (!existsSync(mmprojPath)) {
        throw inputError('LANE2_MMPROJ_MISSING', `mmproj file not found at "${mmprojPath}".`);
      }
      const actualSha = sha256Buffer(readFileSync(mmprojPath));
      if (actualSha !== normalizedMmprojSha) {
        throw inputError(
          'LANE2_MMPROJ_SHA_MISMATCH',
          `mmproj sha256 mismatch: got ${actualSha}, expected ${normalizedMmprojSha}.`
        );
      }
    }
  }

  return {
    ok: true,
    buildNumber,
    vision: Boolean(vision),
    mmprojSha256: normalizedMmprojSha,
  };
}

/**
 * Compute the canonical content hash of a canon/prompt draft so any edit after
 * Director ratification is detected by the freeze gate.
 *
 * @param {Object} draft
 * @returns {string}
 */
export function computeDraftContentSha256(draft) {
  const payload = {
    class_id: draft.class_id || draft.entry_id || null,
    prompt: draft.prompt || '',
    negative_prompt: draft.negative_prompt || '',
    canon_entry_draft: draft.canon_entry_draft || null,
    messages_sha256: draft.messages_sha256 || null,
  };
  return sha256String(canonicalize(payload));
}

/**
 * Build the request messages for drafting a visual canon class and prompt.
 *
 * @param {Object} opts
 * @param {string} opts.classId
 * @param {string} opts.brief
 * @param {Object} [opts.canonContext]
 * @returns {{ messages: Array<Object>, messagesSha256: string }}
 */
export function buildCanonDraftMessages({ classId, brief, canonContext = {} }) {
  const messages = [
    {
      role: 'system',
      content:
        'You are the sdlab Lane 2 canon and prompt drafter (Muse-Glimmer-30B-A3B, Apache-2.0). ' +
        'Return strict JSON with keys: class_id, canon_entry_draft, prompt, negative_prompt.',
    },
    {
      role: 'user',
      content: JSON.stringify({
        class_id: classId,
        brief,
        canon_context: canonContext,
      }),
    },
  ];
  const messagesSha256 = sha256String(canonicalize(messages));
  return { messages, messagesSha256 };
}

/**
 * Draft a visual canon entry and class prompt via a loopback OpenAI-compatible
 * endpoint (`http://127.0.0.1:<port>/v1/chat/completions`) (G10, §3.2, §11).
 *
 * Always emits `status: "draft"` and `judgment: null`.
 *
 * @param {Object} opts
 * @param {string} opts.endpoint
 * @param {string} opts.classId
 * @param {string} opts.brief
 * @param {Object} [opts.canonContext]
 * @param {Object} [opts.modelPin]
 * @param {string} [opts.createdAt]
 * @returns {Promise<Object>}
 */
export async function draftCanonClassViaEndpoint({
  endpoint,
  classId,
  brief,
  canonContext = {},
  modelPin = GLIMMER_DEFAULT_MODEL,
  createdAt = new Date().toISOString(),
}) {
  assertLoopbackEndpoint(endpoint);
  if (!classId || typeof classId !== 'string') {
    throw inputError('LANE2_CLASS_ID_REQUIRED', 'draftCanonClassViaEndpoint requires a non-empty classId.');
  }
  const authorModel = {
    name: modelPin.name || GLIMMER_DEFAULT_MODEL.name,
    repo: modelPin.repo || GLIMMER_DEFAULT_MODEL.repo,
    digest: normalizeSha256(modelPin.digest) || GLIMMER_DEFAULT_MODEL.digest,
    licence_id: modelPin.licence_id || 'Apache-2.0',
    licence_url: modelPin.licence_url || GLIMMER_DEFAULT_MODEL.licence_url,
    date_read: modelPin.date_read || GLIMMER_DEFAULT_MODEL.date_read,
    credit_note: modelPin.credit_note || GLIMMER_CREDIT_NOTE,
  };
  if (authorModel.licence_id !== 'Apache-2.0') {
    throw inputError(
      'LANE2_LICENCE_INVALID',
      `Lane 2 canon authoring model "${authorModel.name}" must carry licence_id "Apache-2.0" (got "${authorModel.licence_id}").`
    );
  }

  const { messages, messagesSha256 } = buildCanonDraftMessages({ classId, brief, canonContext });

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: authorModel.name,
      temperature: 0.2,
      top_p: 0.9,
      messages,
    }),
  });

  if (!response.ok) {
    throw inputError(
      'LANE2_ENDPOINT_ERROR',
      `Lane 2 endpoint ${endpoint} returned HTTP ${response.status}.`
    );
  }

  const body = await response.json();
  const rawContent = body?.choices?.[0]?.message?.content || '{}';
  let parsedContent;
  try {
    parsedContent = typeof rawContent === 'string' ? JSON.parse(rawContent) : rawContent;
  } catch {
    parsedContent = {
      prompt: String(rawContent),
      negative_prompt: '',
      canon_entry_draft: { id: classId, notes: String(rawContent) },
    };
  }

  const draftBase = {
    draft_id: `draft_${classId}`,
    class_id: classId,
    entry_id: classId,
    status: 'draft',
    judgment: null,
    prompt: parsedContent.prompt || '',
    negative_prompt: parsedContent.negative_prompt || '',
    canon_entry_draft: parsedContent.canon_entry_draft || { id: classId },
    author_model: authorModel,
    messages_sha256: messagesSha256,
    created_at: createdAt,
  };

  const draftSha256 = computeDraftContentSha256(draftBase);
  return {
    ...draftBase,
    draft_sha256: draftSha256,
  };
}

/**
 * Write `prompts.jsonl` and its companion `prompts.jsonl.sha256` (§7).
 *
 * @param {string} promptsPath
 * @param {Array<Object>} drafts
 * @returns {{ promptsPath: string, sha256Path: string, sha256: string }}
 */
export function writePromptsJsonl(promptsPath, drafts) {
  mkdirSync(dirname(promptsPath), { recursive: true });
  const content = drafts.map((d) => JSON.stringify(d)).join('\n') + '\n';
  writeFileSync(promptsPath, content, 'utf-8');
  const digest = sha256String(content);
  const sha256Path = `${promptsPath}.sha256`;
  writeFileSync(sha256Path, `${digest}  prompts.jsonl\n`, 'utf-8');
  return { promptsPath, sha256Path, sha256: digest };
}

/**
 * Read `prompts.jsonl` rows from disk.
 *
 * @param {string} promptsPath
 * @returns {Array<Object>}
 */
export function readPromptsJsonl(promptsPath) {
  const raw = readFileSync(promptsPath, 'utf-8');
  return raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}
