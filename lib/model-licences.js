/**
 * Model and LoRA licence catalog and verification helpers (G4, §5.2–§5.3).
 *
 * Cleared SPDX licences for CC-BY-4.0 dataset/LoRA release:
 *   Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, CC0-1.0, CC-BY-4.0
 *
 * Studio Portlight ship data and the `plsvessel` LoRA (`mcp-tool-shop/portlight-ships-anatomy`
 * and `mcp-tool-shop/portlight-ships-anatomy-lora`) are the studio's own, licensed
 * under MIT, and cleared for training and CC-BY-4.0 release.
 *
 * Excluded models (FLUX.1-dev, FLUX.2-dev, FLUX.2-klein-9B, SD 3.5,
 * Qwen-Image 2.1, and community SDXL merges) are explicitly flagged
 * `cc_by_4_eligible: false` and `excluded: true`.
 */

import { inputError } from './errors.js';

export const CLEARED_SPDX_IDS = Object.freeze([
  'Apache-2.0',
  'MIT',
  'BSD-2-Clause',
  'BSD-3-Clause',
  'CC0-1.0',
  'CC-BY-4.0',
]);

const KNOWN_CATALOG = Object.freeze([
  // Cleared studio Portlight ship data and `plsvessel` LoRA (MIT)
  {
    pattern: /^(?:plsvessel|portlight[_-]ships[_-]anatomy)/i,
    spdx_id: 'MIT',
    url: 'https://huggingface.co/mcp-tool-shop/portlight-ships-anatomy-lora',
    verified_at: '2026-11-05',
    cc_by_4_eligible: true,
    excluded: false,
    status: 'cleared',
  },
  // Excluded Qwen-Image 2.1 proprietary API (§5.3)
  {
    pattern: /^qwen[_-]image[_-]2\.1/i,
    spdx_id: 'PROPRIETARY-API',
    url: 'https://www.alibabacloud.com/help/en/model-studio/',
    verified_at: '2026-10-25',
    cc_by_4_eligible: false,
    excluded: true,
    status: 'excluded',
    reason: 'Proprietary API-only model; no open weights',
  },
  // Cleared Qwen-Image 20B and VAE (§5.2)
  {
    pattern: /^qwen[_-]image/i,
    spdx_id: 'Apache-2.0',
    url: 'https://github.com/QwenLM/Qwen-Image/blob/main/LICENSE',
    verified_at: '2026-10-25',
    cc_by_4_eligible: true,
    excluded: false,
    status: 'cleared',
  },
  // Cleared Qwen 2.5 VL 7B text encoder (§5.2)
  {
    pattern: /^qwen[_-]?2\.5[_-]vl[_-]7b/i,
    spdx_id: 'Apache-2.0',
    url: 'https://github.com/QwenLM/Qwen2.5-VL/blob/main/LICENSE',
    verified_at: '2026-10-28',
    cc_by_4_eligible: true,
    excluded: false,
    status: 'cleared',
  },
  // Cleared FLUX.2 [klein] 4B and FLUX.2 VAE (§5.2)
  {
    pattern: /^(?:flux[_-]?2[_-]klein[_-](?:base[_-])?4b|flux2[_-]vae|ae\.safetensors)/i,
    spdx_id: 'Apache-2.0',
    url: 'https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md',
    verified_at: '2026-10-25',
    cc_by_4_eligible: true,
    excluded: false,
    status: 'cleared',
  },
  // Cleared Muse Glimmer 30B / Qwen3-VL-30B-A3B-Instruct / Qwen2.5-VL-32B (§5.2)
  {
    pattern: /^qwen(?:3[_-]vl[_-]30b[_-]a3b|2\.5[_-]vl[_-]32b|2\.5[:_-]14b|3[:_-]14b)/i,
    spdx_id: 'Apache-2.0',
    url: 'https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Instruct/blob/main/LICENSE',
    verified_at: '2026-10-25',
    cc_by_4_eligible: true,
    excluded: false,
    status: 'cleared',
  },
  // Excluded FLUX.1 [dev] (§5.3)
  {
    pattern: /^flux[_-]?1[_-]dev/i,
    spdx_id: 'FLUX-1-DEV-NC',
    url: 'https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md',
    verified_at: '2026-10-25',
    cc_by_4_eligible: false,
    excluded: true,
    status: 'excluded',
    reason: 'FLUX.1 [dev] Non-Commercial License restricts model and derivatives',
  },
  // Excluded FLUX.2 [dev] and FLUX.2 [klein] 9B (§5.3)
  {
    pattern: /^flux[_-]?2[_-](?:dev|klein[_-](?:base[_-])?9b)/i,
    spdx_id: 'FLUX-2-NC',
    url: 'https://huggingface.co/black-forest-labs/FLUX.2-dev/blob/main/LICENSE.md',
    verified_at: '2026-10-25',
    cc_by_4_eligible: false,
    excluded: true,
    status: 'excluded',
    reason: 'FLUX.2 Non-Commercial License',
  },
  // Excluded Stable Diffusion 3.5 family (§5.3)
  {
    pattern: /^(?:sd3\.?5|stable[_-]diffusion[_-]3\.?5)/i,
    spdx_id: 'STABILITY-COMMUNITY',
    url: 'https://huggingface.co/stabilityai/stable-diffusion-3.5-large/blob/main/LICENSE.md',
    verified_at: '2026-10-25',
    cc_by_4_eligible: false,
    excluded: true,
    status: 'excluded',
    reason: 'Stability AI Community License revenue cap and derivative terms',
  },
  // Excluded community SDXL merges (§5.3)
  {
    pattern: /^(?:dreamshaper|juggernaut|pony|illustrious|animagine)/i,
    spdx_id: 'UNCLEARED-COMMUNITY-MERGE',
    url: null,
    verified_at: '2026-10-25',
    cc_by_4_eligible: false,
    excluded: true,
    status: 'excluded',
    reason: 'Community SDXL merge without audited upstream weight lineage',
  },
]);

/**
 * Normalize a licence descriptor into the canonical `{ spdx_id, licence_id, url, licence_url, verified_at, date_read, cc_by_4_eligible, excluded, status }` shape.
 */
function normalizeLicenceObject(raw) {
  const spdxId = raw.spdx_id || raw.licence_id || null;
  const url = raw.url || raw.licence_url || null;
  const verifiedAt = raw.verified_at || raw.date_read || null;
  const excluded = Boolean(raw.excluded);
  const eligible =
    !excluded &&
    raw.cc_by_4_eligible !== false &&
    Boolean(spdxId && CLEARED_SPDX_IDS.includes(spdxId)) &&
    typeof url === 'string' &&
    url.trim().length > 0 &&
    typeof verifiedAt === 'string' &&
    verifiedAt.trim().length > 0;
  return {
    spdx_id: spdxId,
    licence_id: spdxId,
    url,
    licence_url: url,
    verified_at: verifiedAt,
    date_read: verifiedAt,
    cc_by_4_eligible: eligible,
    excluded,
    status: raw.status || (eligible ? 'cleared' : excluded ? 'excluded' : 'unknown'),
    ...(raw.reason ? { reason: raw.reason } : {}),
  };
}

/**
 * Resolve licence metadata for a model or LoRA filename.
 *
 * @param {string} name - Model or LoRA filename
 * @param {Object|null} [explicitLicence] - Explicit override `{ licence_id, licence_url, date_read }`
 * @param {Object|null} [modelLicences] - Map of `filename -> licence` overrides
 */
export function resolveModelLicence(name, explicitLicence = null, modelLicences = null) {
  if (!name || typeof name !== 'string') {
    return normalizeLicenceObject({ status: 'unknown', cc_by_4_eligible: false });
  }

  // Always check catalog first for excluded models so an override cannot mask an excluded model.
  const baseName = name.split(/[\\/]/).pop();
  const catalogMatch = KNOWN_CATALOG.find((entry) => entry.pattern.test(baseName));
  if (catalogMatch && catalogMatch.excluded) {
    return normalizeLicenceObject(catalogMatch);
  }

  const override = explicitLicence || (modelLicences && (modelLicences[name] || modelLicences[baseName]));
  if (override && typeof override === 'object') {
    return normalizeLicenceObject(override);
  }

  if (catalogMatch) {
    return normalizeLicenceObject(catalogMatch);
  }

  return normalizeLicenceObject({ status: 'unknown', cc_by_4_eligible: false });
}

/**
 * Check whether a model/LoRA entry carries a non-empty sha256 digest.
 */
export function hasModelSha256(entry) {
  if (!entry || typeof entry !== 'object') return false;
  return typeof entry.sha256 === 'string' && entry.sha256.trim().length > 0;
}

/**
 * Normalize a model identifier to its canonical family key (DESIGN-v3 §12.5).
 */
export function normalizeModelFamilyKey(modelId) {
  if (!modelId || typeof modelId !== 'string') return '';
  const raw = modelId.trim().toLowerCase();
  if (!raw) return '';
  if (raw.startsWith('human:') || raw === 'human') return 'human';
  if (raw.startsWith('rule-based:')) return 'rule-based';
  const stripped = raw
    .replace(/^model:/, '')
    .replace(/@sha256:[0-9a-f]{64}$/, '')
    .replace(/\.(safetensors|ckpt|pt|pth|bin|gguf)$/, '');
  if (stripped.includes('glimmer') || stripped.includes('muse-glimmer') || stripped.includes('muse_glimmer')) {
    return 'family:muse-glimmer-30b';
  }
  if (stripped.includes('qwen')) {
    return 'family:qwen';
  }
  if (stripped.includes('gemma')) {
    return 'family:gemma';
  }
  if (stripped.includes('internvl')) {
    return 'family:internvl';
  }
  if (stripped.includes('siglip') || stripped.includes('ai-eyes')) {
    return 'family:siglip2';
  }
  if (stripped.includes('flux') || stripped === 'ae') {
    return 'family:flux';
  }
  if (/^(?:sd3\.?5|stable[_-]diffusion[_-]3\.?5)/.test(stripped)) {
    return 'family:sd3';
  }
  if (
    stripped.startsWith('sdxl') ||
    stripped.includes('stable-diffusion-xl') ||
    stripped.includes('stable_diffusion_xl') ||
    /^(?:dreamshaper|juggernaut|pony|illustrious|animagine)/.test(stripped)
  ) {
    return 'family:sdxl';
  }
  return stripped;
}

/**
 * Check whether a model/LoRA pinning entry has a valid cleared SPDX licence,
 * non-empty URL, non-empty date_read, and (by default) a non-empty sha256.
 */
export function isClearedLicenceEntry(entry, { requireSha256 = true } = {}) {
  if (!entry || typeof entry !== 'object') return false;
  if (requireSha256 && !hasModelSha256(entry)) return false;
  const lic = entry.licence || {};
  const spdxId = entry.licence_id || lic.spdx_id || lic.licence_id;
  const url = entry.licence_url || lic.url || lic.licence_url;
  const dateRead = entry.date_read || lic.verified_at || lic.date_read;
  if (lic.excluded === true || lic.cc_by_4_eligible === false) return false;
  if (!spdxId || !CLEARED_SPDX_IDS.includes(spdxId)) return false;
  if (typeof url !== 'string' || !url.trim()) return false;
  if (typeof dateRead !== 'string' || !dateRead.trim()) return false;
  return true;
}

/**
 * Enforce that every model and LoRA in a pinning block has a cleared licence
 * unless `allowUnlicensedResearch` is explicitly set.
 */
export function assertClearedPinningLicences(models, loras, { allowUnlicensedResearch = false, requireSha256 = false } = {}) {
  if (allowUnlicensedResearch) return;
  const entries = [
    ...Object.entries(models || {}).map(([role, entry]) => ({ role, ...entry })),
    ...(loras || []).map((entry, idx) => ({ role: `lora[${idx}]`, ...entry })),
  ];
  const bad = entries.filter((e) => !isClearedLicenceEntry(e, { requireSha256 }));
  if (bad.length > 0) {
    const summary = bad
      .map((b) => `${b.role}:${b.name || '<unnamed>'} (${b.licence_id || 'unlicensed'})`)
      .join(', ');
    throw inputError(
      'MODEL_LICENCE_REJECTED',
      `Model/LoRA licence check failed for: ${summary}`,
      'Only cleared SPDX weights (Apache-2.0, MIT, BSD-*, CC0-1.0, CC-BY-4.0) with a verified licence_url are eligible for CC-BY-4.0 release.',
    );
  }
}
