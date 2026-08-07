/**
 * Asset-source contract — load and validate an `asset-source.json` manifest,
 * the ingest contract of the asset lane (docs/asset-lane-design.md).
 *
 * One manifest per exported asset, living in the export directory. The
 * manifest carries ALL semantics (channels, palettes, classes, tolerances,
 * gates, acceptance); this module carries none — it proves declarations
 * against bytes:
 *
 *   1. schema      — shape, ids, the acceptance gate (verdict must be
 *                    literally "accepted"; the Director's eye is the most
 *                    canon-bound gate the studio has)
 *   2. containment — every referenced path resolves INSIDE the manifest's
 *                    directory (the export dir is untrusted input) and exists
 *   3. encoding    — a PNG's IHDR must match its declared encoding; an NPY
 *                    header must match its declared dtype/shape. A manifest
 *                    that "looks right" but disagrees with its bytes is the
 *                    failure class this lane exists to stop.
 *   4. categorical — indexed: PLTE ⊆ declared palette (structural chunk
 *                    proof, the brand/E09 contract — no pixel decode);
 *                    non-indexed + filter "nearest": EXHAUSTIVE decode proof
 *                    (every non-transparent pixel ∈ declared palette — a
 *                    complete proof, not a sample); non-indexed + "linear":
 *                    no proof here — classification happens at ingest as a
 *                    measurement with an honest unclassified share; npy:
 *                    EXHAUSTIVE value proof against declared integer classes.
 *
 * All violations are collected and refused in ONE loud error (ANDON:
 * nothing registers on a bad manifest), with the code chosen by the most
 * meaningful violation class present.
 *
 * ── Schema 1.1.0 ───────────────────────────────────────────────────────
 * Additive, per facet E11 Ruling 6: the sidecars that rode UNDECLARED
 * beside the declared channels become declarable, so they are contained,
 * proven, hashed and carried into the record instead of being invisible.
 *
 *   - render-space `npy`     — per-view owner/class maps (`owner_id_*.npy`).
 *                              1.0.0 refused these outright; the proof is a
 *                              header match PLUS shape parallel to the
 *                              render, numpy-axis-aware ([H, W], the
 *                              transpose a render-space array gets wrong).
 *   - categorical `npy`      — declares `classes: [{name, value}]` instead of
 *                              an rgb `palette`, proven exhaustively.
 *   - `json` encoding        — the measurement/camera sidecars
 *                              (`admission_*.json`, `cam.json`). The proof is
 *                              deliberately weak and SAID SO: parses as an
 *                              object, declared `required_keys` present. sdlab
 *                              does not read the values — a number in there
 *                              means what the asset says it means.
 *   - `identity.subject_name` — the split engine's authored subject-family
 *                              key. Without it lib/split.js falls back to
 *                              id-stem guessing, which reads two ingests of
 *                              one subject as two families and lets the same
 *                              subject sit in train and test.
 *
 * Every addition is OPTIONAL, so 1.0.0 manifests validate unchanged — which
 * is why this is 1.1.0 and not 2.0.0: a major bump would refuse the very
 * manifests E11 ruled to be the training input. The version gate is
 * minor-aware in the other direction: a manifest declaring a HIGHER minor
 * than this sdlab speaks is refused loudly rather than silently stripped of
 * the channels this build cannot see.
 *
 * ── Schema 1.2.0 ───────────────────────────────────────────────────────
 * Additive, per facet E12 Ruling 10b (the style directive), Rulings 23c/23f
 * (the harmonization adoption) and Rulings 20a/24b (two measured generation
 * phenomena). Same discipline as 1.1.0 — every addition OPTIONAL, so 1.0.0
 * and 1.1.0 manifests validate unchanged. Hence 1.2.0, not 2.0.0.
 *
 *   - `asset.style`          — THE REGISTER IS SUBJECT DATA. Ruling 10b was
 *                              bought by a rejection: the painterly register
 *                              two subjects earned was inherited by a third
 *                              that should read ultra-realistic — "a style
 *                              decision nobody made." The register is an
 *                              authored property of the SUBJECT, declared
 *                              here beside the palette bands, never derived
 *                              from the dataset and never inherited.
 *
 *                              `style.lora` carries a REQUIRED `declared`
 *                              discriminator — "none" or "card". That is the
 *                              ruling expressed mechanically: NO-LoRA is a
 *                              positive declaration, not the absence of a
 *                              field. A serializer that drops nulls cannot
 *                              turn a ruled NONE into silence, and "no
 *                              fixture may leave the section implicit again"
 *                              becomes something bytes can prove.
 *
 *   - `asset.tone_transform` — a deterministic, generation-free tone map
 *                              applied to the generated views BEFORE they
 *                              became the projection sources these renders
 *                              derive from (facet's Lab colour-statistics
 *                              harmonization toward a reference view,
 *                              adopted at Ruling 23f). Declared because this
 *                              lane MEASURES colour — the palette gate, the
 *                              class shares, the pre-registered ΔE
 *                              experiment — and an undeclared upstream tone
 *                              map is a systematic covariate sitting under
 *                              every one of those numbers. Pooling
 *                              harmonized-source and raw-source assets is a
 *                              legitimate choice; doing it unknowingly is
 *                              not.
 *
 *                              The proof is structural and the boundary is
 *                              stated out loud, as with `json`: sdlab checks
 *                              that `reference` names a render THIS manifest
 *                              declares, and contains + hashes + carries the
 *                              operands sidecar. It does NOT verify that the
 *                              transform was applied, that the operands are
 *                              correct, or that the arithmetic is
 *                              reversible. It records what the asset
 *                              declared, so a consumer can group by it and
 *                              an audit can replay it.
 *
 *   - `renders[].generation` — per-image generation frame + seed, because
 *                              both are MEASURED curation axes, not trivia:
 *                              (1) bust/crop-framed generation drifts
 *                              register — three independent instances
 *                              (Ruling 24b); (2) term binding is
 *                              seed-dependent — one seed resisted a prompt
 *                              term across three independent stems where the
 *                              next seed bound it (Ruling 20a), and one
 *                              view's flat-black limb reproduced three times
 *                              at that seed and cured all three times at the
 *                              next (Ruling 23d). A curator who cannot ask
 *                              "which records came from a crop frame" or
 *                              "which came from that seed" cannot act on
 *                              either finding.
 *
 *                              `generation.frame` is a CLOSED two-value enum
 *                              ("full" | "crop") for the same reason
 *                              `facing` is a derived vocabulary: it is the
 *                              axis the phenomenon was measured on, and a
 *                              free-text field where one asset writes "bust"
 *                              and another "head-crop" cannot be queried.
 *                              Everything finer is the asset's own business
 *                              and rides in `frame_detail`.
 */

import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { inputError } from './errors.js';
import { SAFE_ID_RE } from './export.js';
import { parsePngMeta, decodePng } from './png-meta.js';
import { parseNpyHeader, readNpyValues, NPY_PROVABLE_DTYPES } from './npy-meta.js';
import { rgbAt, alphaAt } from './asset-masks.js';

export const ASSET_SCHEMA_VERSION = '1.2.0';
export const ASSET_MANIFEST_FILENAME = 'asset-source.json';

const ENCODINGS = new Set(['indexed', 'rgb', 'rgba', 'grayscale', 'npy', 'json']);

/**
 * Schema 1.2.0. `none` is the ruled NO-LoRA register (facet E12 Ruling 10b:
 * "none at all is better than making the same texture for everything"); a
 * manifest must SAY it rather than omit the field, so silence can never be
 * read as a decision.
 */
export const LORA_DECLARATIONS = new Set(['none', 'card']);

/**
 * Schema 1.2.0. The measured curation axis for the register-drift phenomenon
 * (E12 Ruling 24b): the subject whole in frame, versus a sub-region of it
 * generated at higher pixel density (bust, head-crop, detail crop).
 */
export const GENERATION_FRAMES = new Set(['full', 'crop']);

/**
 * Encodings that decode to pixels. Consumers that measure images (class
 * shares at ingest) must gate on this — since 1.1.0 a channel instance can
 * be an npy array or a json sidecar, and neither answers to decodePng.
 */
export const PIXEL_ENCODINGS = new Set(['indexed', 'rgb', 'rgba', 'grayscale']);
const COLOR_TYPE_BY_ENCODING = { grayscale: 0, rgb: 2, indexed: 3, rgba: 6 };
const RENDER_COLOR_TYPES = new Set([2, 6]); // trainable renders: color, 8-bit

// Violation classes, ordered by which code the single thrown error carries.
// The message always lists EVERY violation; the code names the loudest class.
const CLASS_ORDER = [
  'ASSET_NOT_ACCEPTED',
  'ASSET_MANIFEST_INVALID',
  'ASSET_PATH_ESCAPE',
  'ASSET_FILE_MISSING',
  'ASSET_ENCODING_MISMATCH',
  'ASSET_PALETTE_PROOF_FAILED',
];

function v(cls, path, message) {
  return { cls, path, message };
}

function isNonEmptyString(x) {
  return typeof x === 'string' && x.trim().length > 0;
}

function safeId(x) {
  return typeof x === 'string' && SAFE_ID_RE.test(x);
}

/**
 * Validate `asset.style` (schema 1.2.0) — the STYLE-SUPPLIED section that
 * facet E12 Ruling 10b requires every fixture to carry.
 *
 * The block is optional (1.0.0/1.1.0 manifests validate unchanged), but it is
 * ALL-OR-NOTHING once present: a style block that names a register without
 * answering the LoRA question is exactly the implicit section the ruling
 * forbids, so it is refused rather than half-accepted.
 *
 * @param {Object} style — the manifest's asset.style
 * @param {Function} bad — (jsonPath, message) => void
 */
function validateStyle(style, bad) {
  if (typeof style !== 'object' || Array.isArray(style)) {
    bad('asset.style', 'must be an object {register, lora}');
    return;
  }

  // register — the terms the subject was ruled to read as
  if (!style.register || typeof style.register !== 'object' || Array.isArray(style.register)) {
    bad('asset.style.register', 'required object {terms: [string], ruling?, record?} — the register is subject data, not a studio default');
  } else {
    const terms = style.register.terms;
    if (!Array.isArray(terms) || terms.length === 0 || !terms.every(isNonEmptyString)) {
      bad('asset.style.register.terms', 'required non-empty array of non-empty strings (e.g. ["ultra-realistic", "menacing"])');
    }
    for (const key of ['ruling', 'record']) {
      if (style.register[key] != null && !isNonEmptyString(style.register[key])) {
        bad(`asset.style.register.${key}`, 'must be a non-empty string when present (the ruling that decided this register, and where it is recorded)');
      }
    }
  }

  // lora — the discriminator is the whole point: NONE is declared, not omitted
  if (!style.lora || typeof style.lora !== 'object' || Array.isArray(style.lora)) {
    bad('asset.style.lora',
      'required object — a style block must answer the LoRA question explicitly. Use {"declared":"none"} for the ruled no-LoRA register, or {"declared":"card","card":"<live card name>"}. Omitting it is the implicit-section failure E12 Ruling 10b forbids.');
  } else if (!LORA_DECLARATIONS.has(style.lora.declared)) {
    bad('asset.style.lora.declared',
      `must be one of ${[...LORA_DECLARATIONS].join(', ')} — "none" is a positive declaration that this subject runs with NO LoRA, not the absence of a value`);
  } else if (style.lora.declared === 'card') {
    if (!isNonEmptyString(style.lora.card)) {
      bad('asset.style.lora.card', 'required non-empty string when declared is "card" — the LIVE card name as it exists in the model library, not a nickname');
    }
    if (style.lora.weight != null && typeof style.lora.weight !== 'number') {
      bad('asset.style.lora.weight', 'must be a number when present');
    }
  } else {
    // declared: "none" — carrying a card alongside it is a contradiction, and
    // silently preferring one over the other is how a register drifts back in.
    if (style.lora.card != null) {
      bad('asset.style.lora.card', 'must not be present when declared is "none" — a no-LoRA register that names a card contradicts itself');
    }
    if (style.lora.weight != null && style.lora.weight !== 0) {
      bad('asset.style.lora.weight', 'must be absent or 0 when declared is "none"');
    }
  }
}

/**
 * Validate `asset.tone_transform` (schema 1.2.0) — a deterministic tone map
 * applied upstream of these renders. Optional; complete once present.
 *
 * `reference` is checked against the manifest's own render ids: a reference
 * view that this manifest does not declare is dangling provenance, and that
 * IS checkable structurally. Everything semantic is the asset's.
 *
 * @param {Object} tt — the manifest's asset.tone_transform
 * @param {Set<string>} renderIds — ids declared in renders[]
 * @param {Function} bad — (jsonPath, message) => void
 */
function validateToneTransform(tt, renderIds, bad) {
  if (typeof tt !== 'object' || Array.isArray(tt)) {
    bad('asset.tone_transform', 'must be an object');
    return;
  }
  if (!isNonEmptyString(tt.kind)) {
    bad('asset.tone_transform.kind', 'required non-empty string naming the transform (e.g. "lab-stats-transfer") — sdlab does not interpret it, it records and groups by it');
  }
  if (!isNonEmptyString(tt.reference)) {
    bad('asset.tone_transform.reference', 'required — the render id every other view was transferred toward');
  } else if (renderIds.size > 0 && !renderIds.has(tt.reference)) {
    bad('asset.tone_transform.reference',
      `"${tt.reference}" is not a render id declared in this manifest — a tone transform whose reference view is not in the export leaves the provenance dangling`);
  }
  if (!isNonEmptyString(tt.operands)) {
    bad('asset.tone_transform.operands', 'required path to the recorded per-view operands — it is contained, hashed and carried so the transform can be audited or replayed');
  }
  for (const key of ['space', 'scope', 'record']) {
    if (tt[key] != null && !isNonEmptyString(tt[key])) {
      bad(`asset.tone_transform.${key}`, 'must be a non-empty string when present');
    }
  }
  if (tt.reversible != null && typeof tt.reversible !== 'boolean') {
    bad('asset.tone_transform.reversible', 'must be a boolean when present — this is the asset\'s claim, which sdlab records without verifying');
  }
}

/**
 * Validate `renders[].generation` (schema 1.2.0) — per-image generation
 * provenance for curation. Optional; complete once present.
 *
 * @param {Object} gen — the render's generation block
 * @param {string} p — the render's json path prefix
 * @param {Function} bad — (jsonPath, message) => void
 */
function validateGeneration(gen, p, bad) {
  if (typeof gen !== 'object' || Array.isArray(gen)) {
    bad(`${p}.generation`, 'must be an object');
    return;
  }
  if (!GENERATION_FRAMES.has(gen.frame)) {
    bad(`${p}.generation.frame`,
      `must be one of ${[...GENERATION_FRAMES].join(', ')} — "full" is the whole subject in frame, "crop" is a sub-region generated at higher pixel density (bust, head-crop, detail). This is the axis the register-drift phenomenon was measured on; asset-specific naming goes in frame_detail.`);
  }
  // Seed: integer or digit-string. A digit-string is legal because seeds can
  // exceed what a JSON number holds exactly, and a seed that silently loses
  // its low bits cannot be grouped on — which is the entire reason it is here.
  if (gen.seed != null) {
    const okInt = Number.isInteger(gen.seed) && Number.isSafeInteger(gen.seed);
    const okStr = typeof gen.seed === 'string' && /^\d+$/.test(gen.seed);
    if (!okInt && !okStr) {
      bad(`${p}.generation.seed`, 'must be a safe integer or a string of digits (a string keeps seeds too large for exact JSON numbers groupable)');
    }
  }
  for (const key of ['frame_detail', 'stem', 'model', 'reroll_of']) {
    if (gen[key] != null && !isNonEmptyString(gen[key])) {
      bad(`${p}.generation.${key}`, 'must be a non-empty string when present');
    }
  }
}

// ─── 1. Schema ───────────────────────────────────────────────────────

/**
 * Validate the manifest's shape. Pure — no filesystem access.
 * @returns {Array<{cls:string, path:string, message:string}>}
 */
export function validateManifestShape(m) {
  const out = [];
  const bad = (path, message) => out.push(v('ASSET_MANIFEST_INVALID', path, message));

  if (!m || typeof m !== 'object' || Array.isArray(m)) {
    bad('$', 'manifest must be a JSON object');
    return out;
  }

  // schema_version — major must match; a HIGHER minor is refused rather
  // than accepted-and-silently-stripped. Additive minors mean a newer
  // manifest's extra channels would parse as "absent" to this build, and an
  // asset lane that quietly drops declared provenance is the failure class
  // this module exists to stop.
  if (!isNonEmptyString(m.schema_version) || !/^\d+\.\d+\.\d+$/.test(m.schema_version)) {
    bad('schema_version', 'must be a semver string, e.g. "1.1.0"');
  } else {
    const [major, minor] = m.schema_version.split('.').map(Number);
    const [ourMajor, ourMinor] = ASSET_SCHEMA_VERSION.split('.').map(Number);
    if (major !== ourMajor) {
      bad('schema_version', `major version ${m.schema_version} is not supported (this sdlab speaks ${ASSET_SCHEMA_VERSION})`);
    } else if (minor > ourMinor) {
      bad('schema_version', `${m.schema_version} declares a newer minor than this sdlab speaks (${ASSET_SCHEMA_VERSION}) — it may declare channels this build cannot see, and ingesting it would silently drop them. Upgrade sdlab.`);
    }
  }

  // identity — optional, but the split engine's only authored subject key
  if (m.identity != null) {
    if (typeof m.identity !== 'object' || Array.isArray(m.identity)) {
      bad('identity', 'must be an object');
    } else if (m.identity.subject_name != null && !safeId(m.identity.subject_name)) {
      bad('identity.subject_name', 'must match [A-Za-z0-9._-]+ — it is the split engine\'s subject-family key, and two ingests of one subject must declare the SAME value or splits will read them as two families');
    }
  }

  // asset
  if (!m.asset || typeof m.asset !== 'object') {
    bad('asset', 'required object');
  } else {
    if (!safeId(m.asset.id)) bad('asset.id', 'required; must match [A-Za-z0-9._-]+');
    for (const key of ['mesh', 'atlas']) {
      const ref = m.asset[key];
      if (ref != null && (typeof ref !== 'object' || !isNonEmptyString(ref.path))) {
        bad(`asset.${key}`, 'when present, must be an object with a non-empty "path"');
      }
    }
    // schema 1.2.0 — the STYLE-SUPPLIED section (E12 Ruling 10b)
    if (m.asset.style != null) validateStyle(m.asset.style, bad);
  }

  // acceptance — the door
  if (!m.acceptance || typeof m.acceptance !== 'object') {
    out.push(v('ASSET_NOT_ACCEPTED', 'acceptance', 'required — only accepted assets are admissible; the acceptance block records the Gate verdict'));
  } else {
    if (m.acceptance.verdict !== 'accepted') {
      out.push(v('ASSET_NOT_ACCEPTED', 'acceptance.verdict',
        `is "${m.acceptance.verdict}" — only verdict "accepted" passes the door`));
    }
    if (!isNonEmptyString(m.acceptance.gate)) bad('acceptance.gate', 'required non-empty string (which gate accepted this asset)');
    if (!isNonEmptyString(m.acceptance.date) || Number.isNaN(Date.parse(m.acceptance.date))) {
      bad('acceptance.date', 'required parseable date (ISO recommended)');
    }
    if (!isNonEmptyString(m.acceptance.record)) bad('acceptance.record', 'required non-empty link/path to the acceptance ruling');
  }

  // palette
  if (!m.palette || typeof m.palette !== 'object') {
    bad('palette', 'required object — bands come with the asset, never derived from the dataset');
  } else {
    if (typeof m.palette.min_chroma !== 'number' || m.palette.min_chroma < 0) {
      bad('palette.min_chroma', 'required number >= 0 (the chroma floor is load-bearing)');
    }
    if (!Array.isArray(m.palette.allowed_bands) || m.palette.allowed_bands.length === 0) {
      bad('palette.allowed_bands', 'required non-empty array of {name, hue_deg: [lo, hi]}');
    } else {
      m.palette.allowed_bands.forEach((b, i) => {
        if (!b || typeof b !== 'object' || !isNonEmptyString(b.name)) {
          bad(`palette.allowed_bands[${i}].name`, 'required non-empty string');
        }
        const ok = Array.isArray(b?.hue_deg) && b.hue_deg.length === 2 &&
          b.hue_deg.every((h) => typeof h === 'number' && h >= 0 && h <= 360);
        if (!ok) bad(`palette.allowed_bands[${i}].hue_deg`, 'required [lo, hi] with both in 0–360 (lo > hi wraps around 0°)');
      });
    }
    const gate = m.palette.gate;
    if (!gate || typeof gate !== 'object') {
      bad('palette.gate', 'required object {max_offpalette_pct: number|null, max_offpalette_blob_px: int}');
    } else {
      if (!Number.isInteger(gate.max_offpalette_blob_px) || gate.max_offpalette_blob_px < 0) {
        bad('palette.gate.max_offpalette_blob_px', 'required integer >= 0 (the load-bearing blob gate)');
      }
      if (gate.max_offpalette_pct != null && typeof gate.max_offpalette_pct !== 'number') {
        bad('palette.gate.max_offpalette_pct', 'must be a number or null (null = withdrawn, diagnostic only)');
      }
    }
  }

  // channels
  const channelById = new Map();
  if (m.channels != null && !Array.isArray(m.channels)) {
    bad('channels', 'must be an array of channel declarations');
  } else {
    (m.channels || []).forEach((c, i) => {
      const p = `channels[${i}]`;
      if (!c || typeof c !== 'object') { bad(p, 'must be an object'); return; }
      if (!safeId(c.id)) bad(`${p}.id`, 'required; must match [A-Za-z0-9._-]+');
      else if (channelById.has(c.id)) bad(`${p}.id`, `duplicate channel id "${c.id}"`);
      else channelById.set(c.id, c);
      if (c.space !== 'texture' && c.space !== 'render') bad(`${p}.space`, 'must be "texture" or "render"');
      if (!ENCODINGS.has(c.encoding)) bad(`${p}.encoding`, `must be one of ${[...ENCODINGS].join(', ')}`);
      if (c.space === 'texture' && !isNonEmptyString(c.path)) {
        bad(`${p}.path`, 'texture-space channels declare their single file here');
      }
      if (c.space === 'render' && c.path != null) {
        bad(`${p}.path`, 'render-space channels have per-render instances (renders[].channels), not a path here');
      }
      if (c.categorical) {
        if (c.encoding === 'json') {
          bad(`${p}`, 'json channels cannot be categorical — sdlab does not read their values, so it can prove nothing about classes');
        } else if (c.encoding === 'npy') {
          // Integer classes, not rgb — an owner/class array has no colors.
          if (!Array.isArray(c.classes) || c.classes.length === 0) {
            bad(`${p}.classes`, 'categorical npy channels must declare integer classes [{name, value: int}] (rgb palettes are for pixel encodings)');
          } else {
            const names = new Set();
            const values = new Set();
            c.classes.forEach((cls, j) => {
              if (!cls || !isNonEmptyString(cls.name)) bad(`${p}.classes[${j}].name`, 'required non-empty string');
              else if (names.has(cls.name)) bad(`${p}.classes[${j}].name`, `duplicate class name "${cls.name}"`);
              else names.add(cls.name);
              if (!Number.isInteger(cls?.value)) bad(`${p}.classes[${j}].value`, 'required integer (the value carried in the array, e.g. -1 for "unowned")');
              else if (values.has(cls.value)) bad(`${p}.classes[${j}].value`, `duplicate class value ${cls.value}`);
              else values.add(cls.value);
            });
          }
          if (c.dtype != null && !NPY_PROVABLE_DTYPES.has(c.dtype)) {
            bad(`${p}.dtype`, `categorical npy channels must use a dtype whose values can be read (${[...NPY_PROVABLE_DTYPES].join(', ')}); "${c.dtype}" would leave the class declaration unproven`);
          }
        } else {
          if (!Array.isArray(c.palette) || c.palette.length === 0) {
            bad(`${p}.palette`, 'categorical channels must declare their class palette [{name, rgb: [r,g,b]}]');
          } else {
            const names = new Set();
            c.palette.forEach((cls, j) => {
              if (!cls || !isNonEmptyString(cls.name)) bad(`${p}.palette[${j}].name`, 'required non-empty string');
              else if (names.has(cls.name)) bad(`${p}.palette[${j}].name`, `duplicate class name "${cls.name}"`);
              else names.add(cls.name);
              const ok = Array.isArray(cls?.rgb) && cls.rgb.length === 3 &&
                cls.rgb.every((n) => Number.isInteger(n) && n >= 0 && n <= 255);
              if (!ok) bad(`${p}.palette[${j}].rgb`, 'required [r, g, b] ints 0–255');
            });
          }
          if (c.filter !== 'nearest' && c.filter !== 'linear') {
            bad(`${p}.filter`, 'categorical channels must declare filter "nearest" (exact proof) or "linear" (tolerance classification)');
          }
          if (c.filter === 'linear' && (typeof c.classification_tolerance !== 'number' || c.classification_tolerance < 0)) {
            bad(`${p}.classification_tolerance`, 'linear categorical channels must declare a tolerance >= 0 (max RGB distance)');
          }
        }
      }
      if (c.encoding === 'npy') {
        if (!isNonEmptyString(c.dtype)) bad(`${p}.dtype`, 'npy channels must declare dtype (e.g. "|b1") — proven against the header');
        if (c.space === 'texture') {
          // One file, one declared shape.
          if (!Array.isArray(c.shape) || c.shape.length === 0 || !c.shape.every((n) => Number.isInteger(n) && n >= 0)) {
            bad(`${p}.shape`, 'texture-space npy channels must declare shape (array of ints) — proven against the header');
          }
        } else if (c.shape != null) {
          // Render-space instances are proven parallel to their own render,
          // which a channel-level shape cannot express across differently
          // sized renders. Declaring one invites the two to disagree.
          bad(`${p}.shape`, 'render-space npy channels do not declare shape — each instance is proven [height, width] against its own render (numpy row-major)');
        }
      }
      if (c.encoding === 'json' && c.required_keys != null) {
        const ok = Array.isArray(c.required_keys) && c.required_keys.every((k) => isNonEmptyString(k));
        if (!ok) bad(`${p}.required_keys`, 'when present, must be an array of non-empty top-level key names');
      }
    });
  }

  // renders
  const renderIds = new Set();
  if (!Array.isArray(m.renders) || m.renders.length === 0) {
    bad('renders', 'required non-empty array — an asset with no renders has nothing to ingest');
  } else {
    m.renders.forEach((r, i) => {
      const p = `renders[${i}]`;
      if (!r || typeof r !== 'object') { bad(p, 'must be an object'); return; }
      if (!safeId(r.id)) bad(`${p}.id`, 'required; must match [A-Za-z0-9._-]+');
      else if (renderIds.has(r.id)) bad(`${p}.id`, `duplicate render id "${r.id}"`);
      else renderIds.add(r.id);
      if (!isNonEmptyString(r.path)) bad(`${p}.path`, 'required');
      if (!r.camera || typeof r.camera !== 'object' || typeof r.camera.yaw_deg !== 'number') {
        bad(`${p}.camera`, 'required object with numeric yaw_deg (elevation_deg optional, default 0)');
      } else if (r.camera.elevation_deg != null && typeof r.camera.elevation_deg !== 'number') {
        bad(`${p}.camera.elevation_deg`, 'must be a number when present');
      }
      if (!isNonEmptyString(r.silhouette_mask)) {
        bad(`${p}.silhouette_mask`, 'required — the palette gate measures inside the EXACT silhouette (E08-A2)');
      }
      if (r.channels != null) {
        if (typeof r.channels !== 'object' || Array.isArray(r.channels)) {
          bad(`${p}.channels`, 'must be an object mapping channel-type id → instance path');
        } else {
          for (const [cid, cpath] of Object.entries(r.channels)) {
            const decl = channelById.get(cid);
            if (!decl) bad(`${p}.channels.${cid}`, `references undeclared channel id "${cid}"`);
            else if (decl.space !== 'render') bad(`${p}.channels.${cid}`, `channel "${cid}" is ${decl.space}-space; only render-space channels have per-render instances`);
            if (!isNonEmptyString(cpath)) bad(`${p}.channels.${cid}`, 'instance path must be a non-empty string');
          }
        }
      }
      if (r.loss_mask != null && !isNonEmptyString(r.loss_mask)) bad(`${p}.loss_mask`, 'must be a non-empty path when present');
      if (r.facing != null && !isNonEmptyString(r.facing)) bad(`${p}.facing`, 'must be a non-empty string when present');
      // schema 1.2.0 — per-image generation provenance (Rulings 20a, 24b)
      if (r.generation != null) validateGeneration(r.generation, p, bad);
      // schema 1.2.0 — a render may opt OUT of the asset-level tone transform.
      // Boolean only: the asset declares the transform once, and a render says
      // whether it carries it. Anything richer belongs in the asset block.
      if (r.tone_transform != null && typeof r.tone_transform !== 'boolean') {
        bad(`${p}.tone_transform`, 'must be a boolean when present — true/false says whether THIS render carries the asset-level tone transform; the transform itself is declared once at asset.tone_transform');
      }
      if (r.tone_transform != null && m.asset?.tone_transform == null) {
        bad(`${p}.tone_transform`, 'declares a per-render tone_transform but the manifest has no asset.tone_transform to opt in or out of');
      }
      if (r.pair != null) {
        if (typeof r.pair !== 'object' || Array.isArray(r.pair)) bad(`${p}.pair`, 'must be an object mapping pair name → path');
        else {
          for (const [name, ppath] of Object.entries(r.pair)) {
            if (!safeId(name)) bad(`${p}.pair.${name}`, 'pair names must match [A-Za-z0-9._-]+');
            if (!isNonEmptyString(ppath)) bad(`${p}.pair.${name}`, 'pair path must be a non-empty string');
          }
        }
      }
    });
  }

  // schema 1.2.0 — the tone transform, validated AFTER renders so its
  // reference can be checked against the ids this manifest actually declares
  if (m.asset?.tone_transform != null) {
    validateToneTransform(m.asset.tone_transform, renderIds, bad);
  }

  // captions (material, not captions)
  if (m.captions != null) {
    if (typeof m.captions !== 'object' || Array.isArray(m.captions)) bad('captions', 'must be an object');
    else {
      for (const key of ['subject', 'style_trigger', 'domain_tag']) {
        if (m.captions[key] != null && !isNonEmptyString(m.captions[key])) {
          bad(`captions.${key}`, 'must be a non-empty string when present');
        }
      }
    }
  }

  return out;
}

// ─── 2–4. Containment, existence, encoding + categorical proofs ──────

/**
 * Resolve a manifest-relative path, refusing absolute paths and escapes.
 * @returns {{abs: string}|{violation: Object}}
 */
function containPath(baseDir, relPath, jsonPath) {
  if (isAbsolute(relPath)) {
    return { violation: v('ASSET_PATH_ESCAPE', jsonPath, `"${relPath}" is absolute — manifest paths must be relative to the manifest's directory`) };
  }
  const abs = resolve(baseDir, relPath);
  const rel = relative(resolve(baseDir), abs);
  if (rel.startsWith('..') || isAbsolute(rel)) {
    return { violation: v('ASSET_PATH_ESCAPE', jsonPath, `"${relPath}" resolves outside the export directory`) };
  }
  return { abs };
}

async function provePng(absPath, relPath, jsonPath, expectations, violations) {
  let buf;
  try {
    buf = await readFile(absPath);
  } catch (err) {
    violations.push(v('ASSET_FILE_MISSING', jsonPath, `cannot read "${relPath}": ${err.message}`));
    return null;
  }
  let meta;
  try {
    meta = parsePngMeta(buf, relPath);
  } catch (err) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, `"${relPath}": ${err.message}`));
    return null;
  }
  if (meta.interlaced) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, `"${relPath}" is interlaced — the contract requires non-interlaced PNGs`));
    return null;
  }
  if (expectations.colorTypes && !expectations.colorTypes.has(meta.colorType)) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
      `"${relPath}" has PNG color type ${meta.colorType} (${meta.colorTypeName}); ${expectations.what} requires ${expectations.describe}`));
    return null;
  }
  return { buf, meta };
}

/**
 * Prove an npy file against its declaration.
 *
 * @param {number[]|null} expectShape — for render-space instances, the
 *   [height, width] the array must be parallel to (numpy row-major, so a
 *   [width, height] export is a transpose and is caught here). Null for
 *   texture-space channels, which declare their own shape.
 */
async function proveNpy(absPath, relPath, jsonPath, decl, expectShape, violations) {
  let buf;
  try {
    buf = await readFile(absPath);
  } catch (err) {
    violations.push(v('ASSET_FILE_MISSING', jsonPath, `cannot read "${relPath}": ${err.message}`));
    return null;
  }
  let header;
  try {
    header = parseNpyHeader(buf, relPath);
  } catch (err) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, `"${relPath}": ${err.message}`));
    return null;
  }

  let ok = true;
  if (header.dtype !== decl.dtype) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
      `"${relPath}" has dtype ${header.dtype}, manifest declares ${decl.dtype}`));
    ok = false;
  }
  if (expectShape) {
    const rankOk = header.shape.length === 2 || header.shape.length === 3;
    if (!rankOk || header.shape[0] !== expectShape[0] || header.shape[1] !== expectShape[1]) {
      violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
        `"${relPath}" has shape [${header.shape}]; a render-space array must open [height, width] = [${expectShape[0]}, ${expectShape[1]}] to be parallel to its render (numpy is row-major — a [width, height] export is transposed)`));
      ok = false;
    }
  } else if (JSON.stringify(header.shape) !== JSON.stringify(decl.shape)) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
      `"${relPath}" has shape [${header.shape}], manifest declares [${decl.shape}]`));
    ok = false;
  }
  return ok ? { buf, meta: header } : null;
}

/**
 * Prove a json sidecar. The proof is deliberately shallow and the contract
 * says so out loud: the file parses as an object and carries the keys the
 * manifest declared required. sdlab does NOT read the values — a number in
 * an admission sidecar means whatever the asset says it means, and pretending
 * to verify semantics the lane does not own is worse than declaring the
 * boundary.
 */
async function proveJson(absPath, relPath, jsonPath, decl, violations) {
  let buf;
  try {
    buf = await readFile(absPath);
  } catch (err) {
    violations.push(v('ASSET_FILE_MISSING', jsonPath, `cannot read "${relPath}": ${err.message}`));
    return null;
  }
  let parsed;
  try {
    parsed = JSON.parse(buf.toString('utf-8'));
  } catch (err) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, `"${relPath}" is not valid JSON: ${err.message}`));
    return null;
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, `"${relPath}" must be a JSON object`));
    return null;
  }
  const missing = (decl.required_keys || []).filter((k) => parsed[k] === undefined);
  if (missing.length > 0) {
    violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
      `"${relPath}" is missing declared required key(s): ${missing.join(', ')}`));
    return null;
  }
  return { buf, meta: { keys: Object.keys(parsed) } };
}

/**
 * Prove every referenced file against its declaration. Reads bytes; decodes
 * pixels only where a proof requires it.
 *
 * @param {Object} manifest — shape-valid manifest
 * @param {string} baseDir — the manifest's directory (untrusted export dir)
 * @returns {Promise<{violations: Array, resolved: Object}>}
 *   resolved: {
 *     baseDir, mesh, atlas,
 *     textureChannels: Map<id, {relPath, abs, meta?}>,
 *     renders: Map<id, {render, relPath, abs, meta,
 *                       silhouette: {relPath, abs, meta},
 *                       instances: Map<channelId, {relPath, abs, meta}>,
 *                       lossMask: {relPath, abs, meta}|null,
 *                       pairs: Map<name, {relPath, abs, meta}>}>
 *   }
 */
export async function proveFiles(manifest, baseDir) {
  const violations = [];
  const resolved = {
    baseDir,
    mesh: null,
    atlas: null,
    toneOperands: null,
    textureChannels: new Map(),
    renders: new Map(),
  };
  const channelById = new Map((manifest.channels || []).map((c) => [c.id, c]));

  const contain = (relPath, jsonPath) => {
    const r = containPath(baseDir, relPath, jsonPath);
    if (r.violation) { violations.push(r.violation); return null; }
    if (!existsSync(r.abs)) {
      violations.push(v('ASSET_FILE_MISSING', jsonPath, `"${relPath}" does not exist in the export directory`));
      return null;
    }
    return r.abs;
  };

  // mesh / atlas: existence (+ atlas PNG parse when it is a .png, so its
  // dimensions land in the receipt)
  for (const key of ['mesh', 'atlas']) {
    const ref = manifest.asset?.[key];
    if (!ref) continue;
    const abs = contain(ref.path, `asset.${key}.path`);
    if (!abs) continue;
    let meta = null;
    if (key === 'atlas' && ref.path.toLowerCase().endsWith('.png')) {
      try {
        meta = parsePngMeta(await readFile(abs), ref.path);
      } catch (err) {
        violations.push(v('ASSET_ENCODING_MISMATCH', `asset.${key}.path`, `"${ref.path}": ${err.message}`));
      }
    }
    resolved[key] = { relPath: ref.path, abs, meta };
  }

  // tone-transform operands (schema 1.2.0): contained, parsed as an object,
  // then hashed and carried by the ingest. The proof stops at "it is a JSON
  // object that exists inside the export" — the same declared-weak boundary
  // as a `json` channel. sdlab reads no operand values and verifies no
  // arithmetic; it makes the declaration auditable, not true.
  const ttDecl = manifest.asset?.tone_transform;
  if (ttDecl?.operands) {
    const abs = contain(ttDecl.operands, 'asset.tone_transform.operands');
    if (abs) {
      const proved = await proveJson(abs, ttDecl.operands, 'asset.tone_transform.operands', {}, violations);
      if (proved) resolved.toneOperands = { relPath: ttDecl.operands, abs, meta: proved.meta };
    }
  }

  // texture-space channels
  for (const c of manifest.channels || []) {
    if (c.space !== 'texture') continue;
    const jsonPath = `channels(${c.id}).path`;
    const abs = contain(c.path, jsonPath);
    if (!abs) continue;

    if (c.encoding === 'npy') {
      const proved = await proveNpy(abs, c.path, jsonPath, c, null, violations);
      if (!proved) continue;
      resolved.textureChannels.set(c.id, { relPath: c.path, abs, meta: proved.meta });
      if (c.categorical) proveCategorical(c, proved, `channels(${c.id})`, violations);
      continue;
    }

    if (c.encoding === 'json') {
      const proved = await proveJson(abs, c.path, jsonPath, c, violations);
      if (!proved) continue;
      resolved.textureChannels.set(c.id, { relPath: c.path, abs, meta: proved.meta });
      continue;
    }

    const expectType = COLOR_TYPE_BY_ENCODING[c.encoding];
    const proved = await provePng(abs, c.path, jsonPath, {
      colorTypes: new Set([expectType]),
      what: `declared encoding "${c.encoding}"`,
      describe: `color type ${expectType}`,
    }, violations);
    if (!proved) continue;
    resolved.textureChannels.set(c.id, { relPath: c.path, abs, meta: proved.meta });

    // Categorical proofs on texture channels
    if (c.categorical) {
      proveCategorical(c, proved, `channels(${c.id})`, violations);
    }
  }

  // renders + silhouettes + instances + loss masks + pairs
  for (const r of manifest.renders || []) {
    const rEntry = { render: r, relPath: r.path, abs: null, meta: null, silhouette: null, instances: new Map(), lossMask: null, pairs: new Map() };

    const rAbs = contain(r.path, `renders(${r.id}).path`);
    if (rAbs) {
      const proved = await provePng(rAbs, r.path, `renders(${r.id}).path`, {
        colorTypes: RENDER_COLOR_TYPES,
        what: 'a trainable render',
        describe: 'rgb (2) or rgba (6)',
      }, violations);
      if (proved) {
        if (proved.meta.bitDepth !== 8) {
          violations.push(v('ASSET_ENCODING_MISMATCH', `renders(${r.id}).path`, `"${r.path}" is ${proved.meta.bitDepth}-bit; renders must be 8-bit`));
        } else {
          rEntry.abs = rAbs;
          rEntry.meta = proved.meta;
        }
      }
    }

    const sAbs = r.silhouette_mask ? contain(r.silhouette_mask, `renders(${r.id}).silhouette_mask`) : null;
    if (sAbs) {
      const proved = await provePng(sAbs, r.silhouette_mask, `renders(${r.id}).silhouette_mask`, {
        colorTypes: new Set([0]),
        what: 'a silhouette mask',
        describe: 'grayscale (0)',
      }, violations);
      if (proved) {
        rEntry.silhouette = { relPath: r.silhouette_mask, abs: sAbs, meta: proved.meta };
        if (rEntry.meta && (proved.meta.width !== rEntry.meta.width || proved.meta.height !== rEntry.meta.height)) {
          violations.push(v('ASSET_ENCODING_MISMATCH', `renders(${r.id}).silhouette_mask`,
            `silhouette is ${proved.meta.width}x${proved.meta.height} but the render is ${rEntry.meta.width}x${rEntry.meta.height} — masks are parallel to renders`));
        }
      }
    }

    for (const [cid, cpath] of Object.entries(r.channels || {})) {
      const decl = channelById.get(cid);
      if (!decl || decl.space !== 'render') continue; // shape stage already flagged
      const jsonPath = `renders(${r.id}).channels.${cid}`;
      const iAbs = contain(cpath, jsonPath);
      if (!iAbs) continue;

      // npy instances (schema 1.1.0): proven parallel to their own render.
      // The render's dims are only known if the render itself proved, so an
      // unproven render skips the parallelism check rather than inventing one.
      if (decl.encoding === 'npy') {
        const expectShape = rEntry.meta ? [rEntry.meta.height, rEntry.meta.width] : null;
        const proved = await proveNpy(iAbs, cpath, jsonPath, decl, expectShape, violations);
        if (!proved) continue;
        rEntry.instances.set(cid, { relPath: cpath, abs: iAbs, meta: proved.meta });
        if (decl.categorical) proveCategorical(decl, proved, jsonPath, violations);
        continue;
      }

      // json sidecars (schema 1.1.0): parse + declared keys, nothing deeper.
      if (decl.encoding === 'json') {
        const proved = await proveJson(iAbs, cpath, jsonPath, decl, violations);
        if (!proved) continue;
        rEntry.instances.set(cid, { relPath: cpath, abs: iAbs, meta: proved.meta });
        continue;
      }

      const expectType = COLOR_TYPE_BY_ENCODING[decl.encoding];
      const proved = await provePng(iAbs, cpath, jsonPath, {
        colorTypes: new Set([expectType]),
        what: `channel "${cid}" (declared "${decl.encoding}")`,
        describe: `color type ${expectType}`,
      }, violations);
      if (!proved) continue;
      if (rEntry.meta && (proved.meta.width !== rEntry.meta.width || proved.meta.height !== rEntry.meta.height)) {
        violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
          `instance is ${proved.meta.width}x${proved.meta.height} but the render is ${rEntry.meta.width}x${rEntry.meta.height}`));
        continue;
      }
      rEntry.instances.set(cid, { relPath: cpath, abs: iAbs, meta: proved.meta });
      if (decl.categorical) {
        proveCategorical(decl, proved, jsonPath, violations);
      }
    }

    if (r.loss_mask) {
      const jsonPath = `renders(${r.id}).loss_mask`;
      const lAbs = contain(r.loss_mask, jsonPath);
      if (lAbs) {
        const proved = await provePng(lAbs, r.loss_mask, jsonPath, {
          colorTypes: new Set([0]),
          what: 'a loss mask (soft weights)',
          describe: 'grayscale (0)',
        }, violations);
        if (proved) rEntry.lossMask = { relPath: r.loss_mask, abs: lAbs, meta: proved.meta };
      }
    }

    for (const [name, ppath] of Object.entries(r.pair || {})) {
      const jsonPath = `renders(${r.id}).pair.${name}`;
      const pAbs = contain(ppath, jsonPath);
      if (!pAbs) continue;
      const proved = await provePng(pAbs, ppath, jsonPath, {
        colorTypes: new Set([0, 2, 6]),
        what: 'a conditioning pair image',
        describe: 'grayscale, rgb, or rgba',
      }, violations);
      if (proved) rEntry.pairs.set(name, { relPath: ppath, abs: pAbs, meta: proved.meta });
    }

    resolved.renders.set(r.id, rEntry);
  }

  return { violations, resolved };
}

/**
 * Categorical channel proofs.
 *  - npy: exhaustive value scan — every element must be a declared class
 *    value. The array analogue of the "nearest" pixel proof: a class map has
 *    no antialiasing to forgive, so an undeclared value is a real violation.
 *  - indexed: PLTE ⊆ declared palette — structural, no pixel decode
 *    (the brand/E09 contract: the PLTE *is* the palette; padded or
 *    undeclared entries are violations).
 *  - non-indexed + filter "nearest": exhaustive decode — every
 *    non-transparent pixel's color must be a declared class color.
 *  - non-indexed + filter "linear": no proof (classification is an ingest
 *    measurement with an unclassified share).
 */
function proveCategorical(decl, proved, jsonPath, violations) {
  if (decl.encoding === 'npy') {
    const declaredValues = new Set(decl.classes.map((c) => c.value));
    let values;
    try {
      values = readNpyValues(proved.buf, proved.meta, jsonPath);
    } catch (err) {
      violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, err.message));
      return;
    }
    const shown = [...declaredValues].sort((a, b) => a - b).join(', ');
    for (let i = 0; i < values.length; i++) {
      if (!declaredValues.has(values[i])) {
        violations.push(v('ASSET_PALETTE_PROOF_FAILED', jsonPath,
          `value ${values[i]} at flat index ${i} is not a declared class value (declared: ${shown}) — a categorical npy channel is proven exhaustively, not sampled`));
        return; // one offending value names the failure; no need to flood
      }
    }
    return;
  }

  const declared = new Set(decl.palette.map((c) => c.rgb.join(',')));

  if (decl.encoding === 'indexed') {
    const plte = proved.meta.palette || [];
    for (const entry of plte) {
      if (!declared.has(entry.join(','))) {
        violations.push(v('ASSET_PALETTE_PROOF_FAILED', jsonPath,
          `PLTE entry rgb(${entry.join(', ')}) is not in the declared class palette — E09 discipline: PLTE ⊆ declared palette, no padding`));
      }
    }
    return;
  }

  if (decl.filter === 'nearest') {
    let img;
    try {
      img = decodePng(proved.buf, jsonPath);
    } catch (err) {
      violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, err.message));
      return;
    }
    const n = img.width * img.height;
    for (let i = 0; i < n; i++) {
      if (alphaAt(img, i) === 0) continue;
      const rgb = rgbAt(img, i);
      if (!declared.has(rgb.join(','))) {
        violations.push(v('ASSET_PALETTE_PROOF_FAILED', jsonPath,
          `pixel ${i % img.width},${Math.floor(i / img.width)} is rgb(${rgb.join(', ')}) — not a declared class color; a "nearest"-filtered categorical channel must be exact (this is an exhaustive proof, not a sample)`));
        return; // one offending color names the failure; no need to flood
      }
    }
  }
}

// ─── Orchestration ───────────────────────────────────────────────────

function throwViolations(manifestPath, violations) {
  const order = new Map(CLASS_ORDER.map((c, i) => [c, i]));
  const sorted = [...violations].sort((a, b) => (order.get(a.cls) ?? 99) - (order.get(b.cls) ?? 99));
  const code = sorted[0].cls;
  const MAX_LINES = 20;
  const lines = sorted.slice(0, MAX_LINES).map((x) => `  - [${x.cls}] ${x.path}: ${x.message}`);
  if (sorted.length > MAX_LINES) lines.push(`  … and ${sorted.length - MAX_LINES} more`);
  throw inputError(
    code,
    `${manifestPath}: ${sorted.length} contract violation(s) — nothing was registered.`,
    `Fix the manifest/export and re-run.\n${lines.join('\n')}`
  );
}

/**
 * Load + fully validate an asset-source manifest. Throws one structured
 * error listing every violation; returns the manifest and resolved file map
 * on success.
 *
 * @param {string} manifestPath — absolute path to asset-source.json
 * @returns {Promise<{manifest: Object, resolved: Object, manifestRaw: Buffer}>}
 */
export async function validateAssetSource(manifestPath) {
  if (!existsSync(manifestPath)) {
    throw inputError(
      'ASSET_MANIFEST_NOT_FOUND',
      `No ${ASSET_MANIFEST_FILENAME} at ${manifestPath}.`,
      'The export directory must contain the asset\'s manifest. See docs/asset-lane-design.md for the contract.'
    );
  }
  const manifestRaw = await readFile(manifestPath);
  let manifest;
  try {
    manifest = JSON.parse(manifestRaw.toString('utf-8'));
  } catch (err) {
    throw inputError('ASSET_MANIFEST_INVALID', `${manifestPath} is not valid JSON: ${err.message}`,
      'Fix the JSON syntax and re-run.');
  }

  const shapeViolations = validateManifestShape(manifest);
  if (shapeViolations.length > 0) {
    // Refuse before touching any referenced file: a manifest whose SHAPE is
    // wrong cannot be trusted to name files safely.
    throwViolations(manifestPath, shapeViolations);
  }

  const { violations, resolved } = await proveFiles(manifest, dirname(manifestPath));
  if (violations.length > 0) throwViolations(manifestPath, violations);

  return { manifest, resolved, manifestRaw };
}

// ─── Derived facing vocabulary ───────────────────────────────────────

const FACING_TOKENS = [
  'front',                        // 0°
  'three-quarter front-right',    // 45°
  'right profile',                // 90°
  'three-quarter back-right',     // 135°
  'back',                         // 180°
  'three-quarter back-left',      // 225°
  'left profile',                 // 270°
  'three-quarter front-left',     // 315°
];

/**
 * Deterministic facing token from camera yaw/elevation. Yaw 0 = front;
 * buckets are 45° wide, centered on the eight canonical directions;
 * |elevation| >= 30° appends an elevation clause. Camera-relative naming —
 * "right" means the camera orbited toward the subject's right side of frame.
 *
 * The manifest may override per-render (`renders[].facing`) when the asset
 * disagrees; this is the mechanical default. Per facet E01 (and Cheng et
 * al. 2024, Continuous 3D Words): captions must carry facing — a
 * front-facing phrase on a rear view makes the text fight the image.
 */
export function facingFromCamera(camera) {
  const yaw = ((Number(camera.yaw_deg) % 360) + 360) % 360;
  const elevation = Number(camera.elevation_deg ?? 0);
  const bucket = Math.round(yaw / 45) % 8;
  let token = FACING_TOKENS[bucket];
  if (elevation >= 30) token += ', viewed from above';
  else if (elevation <= -30) token += ', viewed from below';
  return token;
}
