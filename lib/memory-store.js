/**
 * sdlab-native persistent memory store to offrig's schema (DESIGN-v3 §7, §12.1–§12.6).
 *
 * Two stores only:
 *   - Global:  <rootDir>/memory/global/entries.jsonl
 *   - Project: <rootDir>/projects/<project>/memory/entries.jsonl
 *
 * Precedence & safety rules:
 *   1. Lookup order: global active entries, then project active entries.
 *   2. Explicit override only: a project entry overriding or contradicting a
 *      global entry must set `overrides: <global_id>`, `reason`, and
 *      `approver: "human:director"`. Silent contradiction is refused.
 *   3. No cross-talk: loading a project's memory reads only global + that
 *      project's store. Any cross-project store request is refused.
 *   4. Promotion rule: promoting a project rule to global writes a reviewed
 *      `promotion` entry (`approver: "human:director"`, `reason`) and keeps
 *      the project entry intact.
 *   5. Proposed vs active: model-authored proposals (`author: "model:..."`)
 *      must start as `status: "proposed"` with `approver: null`; only an
 *      explicit human Director approval transitions them to `status: "active"`.
 *   6. Sealed holdout guard: refuses any memory proposal citing a sealed
 *      holdout record id.
 */

import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  appendFileSync,
} from 'node:fs';
import { dirname, join } from 'node:path';
import { canonicalize } from './freeze-stamp.js';
import { assertNoSelfVerification } from './canon-review-gate.js';
import { inputError as rawInputError } from './errors.js';

function inputError(code, msg) {
  return rawInputError(code, `${code}: ${msg}`);
}

export const MEMORY_SCOPES = Object.freeze(['global', 'project']);

export const MEMORY_KINDS = Object.freeze([
  'rule',
  'failure_example',
  'banned_token',
  'checklist',
  'promotion',
]);

export const MEMORY_STATUSES = Object.freeze([
  'proposed',
  'active',
  'superseded',
  'rejected',
]);

export const ALLOWED_VERDICTS = Object.freeze(['pass', 'fail', 'cannot_tell']);

export const ALLOWED_FAILURE_MODES = Object.freeze([
  'silhouette_drift',
  'palette_violation',
  'material_mismatch',
  'era_anachronism',
  'rigging_tangle',
  'perspective_violation',
  'lighting_glare',
  'anatomy_distortion',
  'text_watermark',
  'framing_crop',
]);

function sha256String(str) {
  return 'sha256:' + createHash('sha256').update(str, 'utf-8').digest('hex');
}

function normalizeSha256(val) {
  if (typeof val !== 'string') return null;
  const trimmed = val.trim().toLowerCase();
  const hex = trimmed.startsWith('sha256:') ? trimmed.slice(7) : trimmed;
  if (!/^[0-9a-f]{64}$/.test(hex)) return null;
  return `sha256:${hex}`;
}

function validateProjectSlug(project) {
  if (
    !project ||
    typeof project !== 'string' ||
    project.includes('..') ||
    project.includes('/') ||
    project.includes('\\')
  ) {
    throw inputError(
      'MEMORY_CROSS_TALK_FORBIDDEN',
      `Invalid or unsafe project slug "${project}".`
    );
  }
  return project;
}

/**
 * Resolve the JSONL path for either the global memory store or a single project store.
 *
 * @param {string} rootDir
 * @param {'global'|'project'} scope
 * @param {string|null} [project]
 * @returns {string}
 */
export function getMemoryStorePath(rootDir, scope, project = null) {
  if (scope === 'global') {
    return join(rootDir, 'memory', 'global', 'entries.jsonl');
  }
  if (scope === 'project') {
    validateProjectSlug(project);
    return join(rootDir, 'projects', project, 'memory', 'entries.jsonl');
  }
  throw inputError('MEMORY_SCOPE_INVALID', `Unknown memory scope "${scope}".`);
}

/**
 * Read all raw rows from a memory store file.
 *
 * @param {string} storePath
 * @returns {Array<Object>}
 */
export function readStoreEntries(storePath) {
  if (!existsSync(storePath)) return [];
  return readFileSync(storePath, 'utf-8')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function writeStoreEntries(storePath, entries) {
  mkdirSync(dirname(storePath), { recursive: true });
  const body = entries.map((e) => JSON.stringify(e)).join('\n') + (entries.length ? '\n' : '');
  writeFileSync(storePath, body, 'utf-8');
}

function checkSealedHoldoutCitations(entry, sealedHoldoutIds = []) {
  if (!Array.isArray(sealedHoldoutIds) || sealedHoldoutIds.length === 0) return;
  const refs = Array.isArray(entry.evidence_refs) ? entry.evidence_refs.map(String) : [];
  const statement = String(entry.statement || '');
  for (const holdoutId of sealedHoldoutIds) {
    if (!holdoutId) continue;
    const hitInRefs = refs.some((r) => r === holdoutId || r.includes(holdoutId));
    const hitInStatement = statement.includes(holdoutId);
    if (hitInRefs || hitInStatement) {
      throw inputError(
        'MEMORY_HOLDOUT_CITATION_FORBIDDEN',
        `Memory entry "${entry.id}" cites sealed holdout record "${holdoutId}" (§12.6).`
      );
    }
  }
}

/**
 * Append a validated memory entry to the global or project store (§12.2–§12.6).
 *
 * @param {Object} opts
 * @param {string} opts.rootDir
 * @param {Object} opts.entry
 * @param {Array<string>} [opts.sealedHoldoutIds]
 * @returns {Object}
 */
export function appendMemoryEntry({ rootDir, entry, sealedHoldoutIds = [] }) {
  if (!entry || typeof entry !== 'object') {
    throw inputError('MEMORY_ENTRY_INVALID', 'Memory entry must be an object.');
  }
  const {
    id,
    scope,
    project = null,
    kind,
    rule_key = null,
    status = 'proposed',
    statement,
    evidence_refs = [],
    author,
    approver = null,
    overrides = null,
    superseded_by = null,
    reason = null,
    promoted_from = null,
    created_at = new Date().toISOString(),
    approved_at = null,
  } = entry;

  if (!id || typeof id !== 'string') {
    throw inputError('MEMORY_ENTRY_INVALID', 'Memory entry requires a non-empty string "id".');
  }
  if (!MEMORY_SCOPES.includes(scope)) {
    throw inputError('MEMORY_SCOPE_INVALID', `Memory entry "${id}" has invalid scope "${scope}".`);
  }
  if (scope === 'global' && project !== null) {
    throw inputError('MEMORY_SCOPE_INVALID', `Global memory entry "${id}" must have project: null.`);
  }
  if (scope === 'project') {
    validateProjectSlug(project);
  }
  if (!MEMORY_KINDS.includes(kind)) {
    throw inputError('MEMORY_KIND_INVALID', `Memory entry "${id}" has invalid kind "${kind}".`);
  }
  if (!MEMORY_STATUSES.includes(status)) {
    throw inputError('MEMORY_STATUS_INVALID', `Memory entry "${id}" has invalid status "${status}".`);
  }
  if (!statement || typeof statement !== 'string' || !statement.trim()) {
    throw inputError('MEMORY_ENTRY_INVALID', `Memory entry "${id}" requires a non-empty statement.`);
  }
  if (!author || typeof author !== 'string') {
    throw inputError('MEMORY_ENTRY_INVALID', `Memory entry "${id}" requires an author.`);
  }

  // Sealed holdout citation guard (§12.6)
  checkSealedHoldoutCitations({ id, statement, evidence_refs }, sealedHoldoutIds);

  const isModelAuthor = author.startsWith('model:');
  if (isModelAuthor && status !== 'proposed' && kind !== 'promotion') {
    throw inputError(
      'MEMORY_MODEL_ACTIVE_FORBIDDEN',
      `Model-authored memory entry "${id}" (${author}) must start as status "proposed", not "${status}" (§12.4).`
    );
  }

  if (status === 'active') {
    if (!approver || !String(approver).startsWith('human:')) {
      throw inputError(
        'MEMORY_APPROVER_REQUIRED',
        `Active memory entry "${id}" requires a human Director approver ("human:director").`
      );
    }
  }

  // Global vs project precedence and explicit-override checks (§12.3)
  const globalPath = getMemoryStorePath(rootDir, 'global', null);
  const globalEntries = readStoreEntries(globalPath);
  const activeGlobalEntries = globalEntries.filter((e) => e.status === 'active');

  if (scope === 'project') {
    if (overrides) {
      const targetGlobal = activeGlobalEntries.find((g) => g.id === overrides);
      if (!targetGlobal) {
        throw inputError(
          'MEMORY_OVERRIDE_INVALID',
          `Project memory entry "${id}" overrides "${overrides}", which is not an active global entry.`
        );
      }
      if (!reason || typeof reason !== 'string' || !reason.trim()) {
        throw inputError(
          'MEMORY_OVERRIDE_INVALID',
          `Project memory entry "${id}" overriding global "${overrides}" requires a non-empty "reason".`
        );
      }
      if (!approver || !String(approver).startsWith('human:')) {
        throw inputError(
          'MEMORY_OVERRIDE_INVALID',
          `Project memory entry "${id}" overriding global "${overrides}" requires approver "human:director".`
        );
      }
    } else if (rule_key) {
      const conflictingGlobal = activeGlobalEntries.find(
        (g) => g.rule_key && g.rule_key === rule_key && g.statement !== statement
      );
      if (conflictingGlobal) {
        throw inputError(
          'MEMORY_SILENT_CONTRADICTION',
          `Project memory entry "${id}" contradicts active global rule "${conflictingGlobal.id}" on rule_key "${rule_key}" without setting overrides: "${conflictingGlobal.id}" (§12.3).`
        );
      }
    }
  }

  const normalizedEntry = {
    id,
    scope,
    project: scope === 'global' ? null : project,
    kind,
    ...(rule_key ? { rule_key } : {}),
    status,
    statement: statement.trim(),
    evidence_refs: Array.isArray(evidence_refs) ? evidence_refs : [],
    author,
    approver: status === 'proposed' ? null : approver,
    overrides: overrides || null,
    superseded_by: superseded_by || null,
    ...(reason ? { reason } : {}),
    ...(promoted_from ? { promoted_from } : {}),
    created_at,
    approved_at: status === 'active' ? approved_at || created_at : null,
  };

  const storePath = getMemoryStorePath(rootDir, scope, project);
  mkdirSync(dirname(storePath), { recursive: true });
  appendFileSync(storePath, JSON.stringify(normalizedEntry) + '\n', 'utf-8');
  return normalizedEntry;
}

/**
 * Transition a `proposed` memory entry to `active` upon explicit Director review (§12.4).
 *
 * @param {Object} opts
 * @param {string} opts.rootDir
 * @param {'global'|'project'} opts.scope
 * @param {string|null} [opts.project]
 * @param {string} opts.id
 * @param {string} opts.approver
 * @param {string} [opts.reason]
 * @param {string} [opts.approvedAt]
 * @returns {Object}
 */
export function approveProposedMemoryEntry({
  rootDir,
  scope,
  project = null,
  id,
  approver,
  reason = null,
  approvedAt = new Date().toISOString(),
}) {
  if (!approver || !String(approver).startsWith('human:')) {
    throw inputError(
      'MEMORY_APPROVER_REQUIRED',
      `Only a human Director ("human:director") may approve proposed memory entry "${id}".`
    );
  }
  const storePath = getMemoryStorePath(rootDir, scope, project);
  const entries = readStoreEntries(storePath);
  const idx = entries.findIndex((e) => e.id === id);
  if (idx === -1) {
    throw inputError('MEMORY_ENTRY_NOT_FOUND', `Memory entry "${id}" not found in ${scope} store.`);
  }

  const updated = {
    ...entries[idx],
    status: 'active',
    approver,
    ...(reason ? { reason } : {}),
    approved_at: approvedAt,
  };
  entries[idx] = updated;
  writeStoreEntries(storePath, entries);
  return updated;
}

/**
 * Promote an active project memory entry to the global store with an explicit
 * `promotion` audit record, keeping the project entry intact (§12.3).
 *
 * @param {Object} opts
 * @param {string} opts.rootDir
 * @param {string} opts.sourceProject
 * @param {string} opts.sourceEntryId
 * @param {string} opts.newGlobalId
 * @param {string} opts.approver
 * @param {string} opts.reason
 * @param {string} [opts.createdAt]
 * @returns {Object}
 */
export function promoteProjectMemoryToGlobal({
  rootDir,
  sourceProject,
  sourceEntryId,
  newGlobalId,
  approver,
  reason,
  createdAt = new Date().toISOString(),
}) {
  if (!approver || !String(approver).startsWith('human:')) {
    throw inputError(
      'MEMORY_APPROVER_REQUIRED',
      'Promoting a project memory entry to global requires approver "human:director".'
    );
  }
  if (!reason || typeof reason !== 'string' || !reason.trim()) {
    throw inputError(
      'MEMORY_PROMOTION_REASON_REQUIRED',
      'Promoting a project memory entry to global requires a non-empty reason.'
    );
  }
  const projectPath = getMemoryStorePath(rootDir, 'project', sourceProject);
  const projectEntries = readStoreEntries(projectPath);
  const sourceEntry = projectEntries.find((e) => e.id === sourceEntryId && e.status === 'active');
  if (!sourceEntry) {
    throw inputError(
      'MEMORY_ENTRY_NOT_FOUND',
      `Active project memory entry "${sourceEntryId}" not found in project "${sourceProject}".`
    );
  }

  return appendMemoryEntry({
    rootDir,
    entry: {
      id: newGlobalId,
      scope: 'global',
      project: null,
      kind: 'promotion',
      rule_key: sourceEntry.rule_key || null,
      status: 'active',
      statement: sourceEntry.statement,
      evidence_refs: sourceEntry.evidence_refs,
      author: sourceEntry.author,
      approver,
      overrides: null,
      superseded_by: null,
      reason: reason.trim(),
      promoted_from: {
        project: sourceProject,
        entry_id: sourceEntryId,
      },
      created_at: createdAt,
      approved_at: createdAt,
    },
  });
}

/**
 * Compute canonical `sha256:<64hex>` over a list of active memory entries.
 *
 * @param {Array<Object>} activeEntries
 * @returns {string}
 */
export function computeStoreSha256(activeEntries) {
  const sorted = [...activeEntries].sort((a, b) => String(a.id).localeCompare(String(b.id)));
  return sha256String(canonicalize(sorted));
}

/**
 * Load effective active memory for a project (§12.3):
 *   1. Reads ONLY `memory/global/entries.jsonl` and `projects/<project>/memory/entries.jsonl` (no cross-talk).
 *   2. Filters to `status === "active"` (`proposed`, `superseded`, `rejected` never enter prompts).
 *   3. Applies explicit project `overrides` against global entries.
 *   4. Returns global active entries first, followed by project active entries.
 *
 * @param {Object} opts
 * @param {string} opts.rootDir
 * @param {string} opts.project
 * @param {Array<string>} [opts.extraProjectStores] — forbidden cross-project stores (throws if non-empty)
 * @returns {Object}
 */
export function loadEffectiveMemory({ rootDir, project, extraProjectStores = [] }) {
  validateProjectSlug(project);
  if (Array.isArray(extraProjectStores) && extraProjectStores.length > 0) {
    const illegal = extraProjectStores.filter((p) => p !== project);
    if (illegal.length > 0) {
      throw inputError(
        'MEMORY_CROSS_TALK_FORBIDDEN',
        `Cross-project memory load forbidden: project "${project}" attempted to read [${illegal.join(', ')}] (§12.3).`
      );
    }
  }

  const globalPath = getMemoryStorePath(rootDir, 'global', null);
  const projectPath = getMemoryStorePath(rootDir, 'project', project);

  const globalRaw = readStoreEntries(globalPath);
  const projectRaw = readStoreEntries(projectPath);

  const globalActiveAll = globalRaw.filter((e) => e.status === 'active' && !e.superseded_by);
  const projectActive = projectRaw.filter((e) => e.status === 'active' && !e.superseded_by);

  const overriddenGlobalIds = new Set(
    projectActive.map((e) => e.overrides).filter((id) => typeof id === 'string' && id.length > 0)
  );

  const effectiveGlobalActive = globalActiveAll.filter((g) => !overriddenGlobalIds.has(g.id));
  const activeEntries = [...effectiveGlobalActive, ...projectActive];

  return {
    project,
    memory_sha_global: computeStoreSha256(globalActiveAll),
    memory_sha_project: computeStoreSha256(projectActive),
    globalActive: globalActiveAll,
    projectActive,
    activeEntries,
  };
}

/**
 * Write `memory-snapshot.json` for a Lane 2 window (§7, §12.5).
 *
 * @param {Object} opts
 * @param {string} opts.rootDir
 * @param {string} opts.project
 * @param {string} opts.windowId
 * @param {string} opts.outPath
 * @param {string} [opts.createdAt]
 * @returns {Object}
 */
export function writeMemorySnapshot({
  rootDir,
  project,
  windowId,
  outPath,
  createdAt = new Date().toISOString(),
}) {
  const loaded = loadEffectiveMemory({ rootDir, project });
  const snapshot = {
    window_id: windowId,
    project,
    memory_sha_global: loaded.memory_sha_global,
    memory_sha_project: loaded.memory_sha_project,
    global_active_ids: loaded.globalActive.map((e) => e.id),
    project_active_ids: loaded.projectActive.map((e) => e.id),
    active_entries: loaded.activeEntries,
    created_at: createdAt,
  };
  if (outPath) {
    mkdirSync(dirname(outPath), { recursive: true });
    writeFileSync(outPath, JSON.stringify(snapshot, null, 2) + '\n', 'utf-8');
  }
  return snapshot;
}

/**
 * Diff two memory snapshots (`snapA` vs `snapB`) by active entry IDs and SHAs (§12.5).
 *
 * @param {Object} snapA
 * @param {Object} snapB
 * @returns {Object}
 */
export function diffMemorySnapshots(snapA, snapB) {
  const mapA = new Map((snapA.active_entries || []).map((e) => [e.id, e]));
  const mapB = new Map((snapB.active_entries || []).map((e) => [e.id, e]));

  const added = [];
  const removed = [];
  const changed = [];

  for (const [id, entryB] of mapB.entries()) {
    if (!mapA.has(id)) {
      added.push(id);
    } else if (canonicalize(mapA.get(id)) !== canonicalize(entryB)) {
      changed.push(id);
    }
  }
  for (const id of mapA.keys()) {
    if (!mapB.has(id)) {
      removed.push(id);
    }
  }

  return {
    globalChanged: snapA.memory_sha_global !== snapB.memory_sha_global,
    projectChanged: snapA.memory_sha_project !== snapB.memory_sha_project,
    added: added.sort(),
    removed: removed.sort(),
    changed: changed.sort(),
  };
}

/**
 * Append a structured vision verdict row to `verdicts.jsonl` carrying both
 * `memory_sha_global` and `memory_sha_project`, `canon_sha`, `verifier_model`,
 * `sampling`, `verdict`, and closed-list `failure_modes` (§7, §11.4, §12.5).
 *
 * @param {Object} opts
 * @returns {Object}
 */
export function recordVisionVerdict({
  verdictsPath,
  windowId,
  imageSha256,
  canonSha,
  memorySnapshot,
  verifierModel,
  authorModel = null,
  sampling = { temperature: 0, top_p: 1.0, seed: 0 },
  verdict,
  failureModes = [],
  allowedFailureModes = ALLOWED_FAILURE_MODES,
  notes = '',
  createdAt = new Date().toISOString(),
}) {
  if (authorModel) {
    assertNoSelfVerification({
      authorModel,
      verifierModel,
      context: `verdict for ${imageSha256}`,
    });
  }

  const normImageSha = normalizeSha256(imageSha256);
  const normCanonSha = normalizeSha256(canonSha);
  if (!normImageSha || !normCanonSha) {
    throw inputError('VERDICT_SHA_INVALID', 'recordVisionVerdict requires valid 64-hex imageSha256 and canonSha.');
  }
  if (!memorySnapshot?.memory_sha_global || !memorySnapshot?.memory_sha_project) {
    throw inputError(
      'VERDICT_MEMORY_SHA_MISSING',
      'recordVisionVerdict requires memorySnapshot with memory_sha_global and memory_sha_project.'
    );
  }
  if (!ALLOWED_VERDICTS.includes(verdict)) {
    throw inputError(
      'VERDICT_INVALID',
      `Verdict must be one of [${ALLOWED_VERDICTS.join(', ')}], got "${verdict}".`
    );
  }

  const allowedSet = new Set(allowedFailureModes);
  for (const mode of failureModes) {
    if (!allowedSet.has(mode)) {
      throw inputError(
        'VERDICT_FAILURE_MODE_INVALID',
        `Failure mode "${mode}" is not in the closed failure-mode list [${[...allowedSet].join(', ')}].`
      );
    }
  }

  if (!verifierModel?.name || !normalizeSha256(verifierModel?.digest) || verifierModel?.licence_id !== 'Apache-2.0') {
    throw inputError(
      'VERDICT_MODEL_PIN_INVALID',
      'verifierModel must include name, 64-hex digest, and licence_id: "Apache-2.0".'
    );
  }

  const row = {
    window_id: windowId,
    image_sha256: normImageSha,
    canon_sha: normCanonSha,
    memory_sha_global: memorySnapshot.memory_sha_global,
    memory_sha_project: memorySnapshot.memory_sha_project,
    verifier_model: {
      name: verifierModel.name,
      digest: normalizeSha256(verifierModel.digest),
      licence_id: verifierModel.licence_id,
    },
    sampling: {
      temperature: sampling.temperature ?? 0,
      top_p: sampling.top_p ?? 1.0,
      seed: sampling.seed ?? 0,
    },
    verdict,
    failure_modes: [...failureModes],
    notes: String(notes || ''),
    created_at: createdAt,
  };

  if (verdictsPath) {
    mkdirSync(dirname(verdictsPath), { recursive: true });
    appendFileSync(verdictsPath, JSON.stringify(row) + '\n', 'utf-8');
  }
  return row;
}
