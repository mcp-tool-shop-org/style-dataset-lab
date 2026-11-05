/**
 * Review gate before canon freeze & self-verification ban (DESIGN-v3 §11.5, §12.6, G11).
 *
 * Enforces:
 *   1. Model-authored canon/prompt drafts are only ever proposed (`status: "draft"`).
 *   2. Freezing or ratifying a draft requires an explicit recorded Director accept
 *      (`approver: "human:director"`, non-empty `reason`, and matching `draft_sha256`).
 *   3. A model may never self-approve or be the deciding verifier of a canon
 *      entry or prompt it wrote (`SELF_VERIFICATION_FORBIDDEN`).
 */

import { computeDraftContentSha256 } from './canon-author.js';
import { inputError as rawInputError } from './errors.js';

function inputError(code, msg) {
  return rawInputError(code, `${code}: ${msg}`);
}

export function normalizeModelFamilyKey(modelId) {
  if (!modelId || typeof modelId !== 'string') return '';
  const lower = modelId
    .trim()
    .toLowerCase()
    .replace(/^model:/, '')
    .replace(/@sha256:[0-9a-f]{64}$/, '');
  if (!lower) return '';
  if (lower.startsWith('human:') || lower === 'human') return 'human';
  if (lower.startsWith('rule-based:') || lower === 'rule-based') return 'rule-based';
  if (lower.includes('glimmer') || lower.includes('muse-glimmer') || lower.includes('muse_glimmer')) {
    return 'family:muse-glimmer-30b';
  }
  if (lower.includes('qwen')) {
    return 'family:qwen';
  }
  if (lower.includes('gemma')) {
    return 'family:gemma';
  }
  if (lower.includes('internvl') || lower.includes('caprl-internvl')) {
    return 'family:internvl';
  }
  if (lower.includes('siglip') || lower === 'ai-eyes') {
    return 'family:siglip2';
  }
  if (lower.includes('flux') || lower === 'ae.safetensors') {
    return 'family:flux';
  }
  if (lower.includes('sd3') || lower.includes('stable-diffusion-3')) {
    return 'family:sd3';
  }
  if (
    lower.includes('sdxl') ||
    lower.includes('stable-diffusion-xl') ||
    lower.includes('dreamshaper') ||
    lower.includes('juggernaut') ||
    lower.includes('pony') ||
    lower.includes('illustrious') ||
    lower.includes('animagine')
  ) {
    return 'family:sdxl';
  }
  return lower;
}

/**
 * Enforce the §12.6 self-verification ban: a model (such as Muse-Glimmer-30B)
 * may never be the deciding reader/verifier of a canon entry or prompt it wrote.
 *
 * @param {Object} opts
 * @param {string|Object} opts.authorModel
 * @param {string|Object} opts.verifierModel
 * @param {string} [opts.context='artifact']
 * @returns {{ ok: true, authorFamily: string, verifierFamily: string }}
 */
export function assertNoSelfVerification({ authorModel, verifierModel, context = 'artifact' } = {}) {
  const authorRaw = typeof authorModel === 'object' ? authorModel?.name : authorModel;
  const verifierRaw = typeof verifierModel === 'object' ? verifierModel?.name : verifierModel;

  const authorFamily = normalizeModelFamilyKey(authorRaw);
  const verifierFamily = normalizeModelFamilyKey(verifierRaw);

  if (
    authorFamily &&
    verifierFamily &&
    authorFamily !== 'human' &&
    verifierFamily !== 'human' &&
    authorFamily === verifierFamily
  ) {
    throw inputError(
      'SELF_VERIFICATION_FORBIDDEN',
      `Self-verification forbidden on ${context}: verifier "${verifierRaw}" belongs to the same model family ("${verifierFamily}") as author "${authorRaw}".`
    );
  }

  return { ok: true, authorFamily, verifierFamily };
}

/**
 * Record an explicit Director ratification on a model-authored canon/prompt draft (G11).
 *
 * @param {Object} opts
 * @param {Object} opts.draft
 * @param {string} opts.approver — must be "human:director" (or "human:<id>")
 * @param {string} opts.reason
 * @param {string} [opts.at]
 * @returns {Object} ratified draft
 */
export function ratifyCanonDraft({
  draft,
  approver,
  reason,
  at = new Date().toISOString(),
} = {}) {
  if (!draft || typeof draft !== 'object') {
    throw inputError('CANON_DRAFT_INVALID', 'ratifyCanonDraft requires a draft object.');
  }
  const approverStr = String(approver || '').trim();
  if (approverStr.startsWith('model:') || !approverStr.startsWith('human:')) {
    throw inputError(
      'CANON_SELF_APPROVAL_FORBIDDEN',
      `Canon draft "${draft.class_id || draft.draft_id}" can only be ratified by a human Director ("human:director"), got "${approverStr}".`
    );
  }
  const reasonStr = String(reason || '').trim();
  if (!reasonStr) {
    throw inputError(
      'CANON_RATIFICATION_REASON_REQUIRED',
      `Ratifying canon draft "${draft.class_id || draft.draft_id}" requires a non-empty reason.`
    );
  }

  const contentSha = computeDraftContentSha256(draft);
  return {
    ...draft,
    status: 'ratified',
    judgment: 'accepted',
    draft_sha256: contentSha,
    ratification: {
      status: 'accepted',
      approver: approverStr,
      reason: reasonStr,
      at,
      draft_sha256: contentSha,
    },
  };
}

/**
 * Assert that a canon entry or prompt draft has been explicitly ratified by
 * the Director before it can be frozen (G11, §11.5).
 *
 * Refuses:
 *   - `status === "draft"` or missing `ratification` on a model-authored draft
 *   - `ratification.approver` not starting with `"human:"`
 *   - `ratification.draft_sha256` mismatch against the current draft content
 *
 * @param {Object} draftOrFrontmatter
 * @returns {{ ok: true, ratification: Object|null }}
 */
export function assertDirectorRatifiedForFreeze(draftOrFrontmatter) {
  if (!draftOrFrontmatter || typeof draftOrFrontmatter !== 'object') {
    throw inputError('CANON_DRAFT_INVALID', 'Cannot verify freeze gate on empty draft/frontmatter.');
  }

  const status = draftOrFrontmatter.status || draftOrFrontmatter.draft_status || null;
  const isModelDraft =
    status === 'draft' ||
    status === 'ratified' ||
    Boolean(draftOrFrontmatter.ratification) ||
    Boolean(draftOrFrontmatter.author_model) ||
    Boolean(draftOrFrontmatter.drafted_by_model);

  if (!isModelDraft) {
    return { ok: true, ratification: null };
  }

  const ratification = draftOrFrontmatter.ratification;
  if (
    status === 'draft' ||
    !ratification ||
    ratification.status !== 'accepted' ||
    typeof ratification.approver !== 'string' ||
    !ratification.approver.startsWith('human:') ||
    typeof ratification.reason !== 'string' ||
    !ratification.reason.trim()
  ) {
    throw inputError(
      'CANON_DRAFT_UNRATIFIED',
      `Refusing to freeze model-authored draft "${draftOrFrontmatter.class_id || draftOrFrontmatter.id || 'unknown'}": ` +
        'status is still "draft" or lacks an explicit human Director ratification (`approver: "human:director"`, `reason`).'
    );
  }

  if (draftOrFrontmatter.prompt !== undefined || draftOrFrontmatter.canon_entry_draft !== undefined) {
    const actualSha = computeDraftContentSha256(draftOrFrontmatter);
    if (ratification.draft_sha256 !== actualSha) {
      throw inputError(
        'CANON_DRAFT_SHA_MISMATCH',
        `Draft content for "${draftOrFrontmatter.class_id || draftOrFrontmatter.id}" changed after Director ratification ` +
          `(got ${actualSha}, ratified ${ratification.draft_sha256}). Re-ratify before freezing.`
      );
    }
  }

  return { ok: true, ratification };
}
