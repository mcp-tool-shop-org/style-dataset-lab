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
 *                    measurement with an honest unclassified share.
 *
 * All violations are collected and refused in ONE loud error (ANDON:
 * nothing registers on a bad manifest), with the code chosen by the most
 * meaningful violation class present.
 */

import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { inputError } from './errors.js';
import { SAFE_ID_RE } from './export.js';
import { parsePngMeta, decodePng } from './png-meta.js';
import { parseNpyHeader } from './npy-meta.js';
import { rgbAt, alphaAt } from './asset-masks.js';

export const ASSET_SCHEMA_VERSION = '1.0.0';
export const ASSET_MANIFEST_FILENAME = 'asset-source.json';

const ENCODINGS = new Set(['indexed', 'rgb', 'rgba', 'grayscale', 'npy']);
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

  // schema_version
  if (!isNonEmptyString(m.schema_version) || !/^\d+\.\d+\.\d+$/.test(m.schema_version)) {
    bad('schema_version', 'must be a semver string, e.g. "1.0.0"');
  } else if (m.schema_version.split('.')[0] !== ASSET_SCHEMA_VERSION.split('.')[0]) {
    bad('schema_version', `major version ${m.schema_version} is not supported (this sdlab speaks ${ASSET_SCHEMA_VERSION})`);
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
      if (c.encoding === 'npy' && c.space === 'render') {
        bad(`${p}`, 'npy channels are texture-space only in schema 1.x');
      }
      if (c.space === 'texture' && !isNonEmptyString(c.path)) {
        bad(`${p}.path`, 'texture-space channels declare their single file here');
      }
      if (c.space === 'render' && c.path != null) {
        bad(`${p}.path`, 'render-space channels have per-render instances (renders[].channels), not a path here');
      }
      if (c.categorical) {
        if (c.encoding === 'npy') bad(`${p}`, 'categorical npy channels are not supported in schema 1.x');
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
      if (c.encoding === 'npy') {
        if (!isNonEmptyString(c.dtype)) bad(`${p}.dtype`, 'npy channels must declare dtype (e.g. "|b1") — proven against the header');
        if (!Array.isArray(c.shape) || c.shape.length === 0 || !c.shape.every((n) => Number.isInteger(n) && n >= 0)) {
          bad(`${p}.shape`, 'npy channels must declare shape (array of ints) — proven against the header');
        }
      }
    });
  }

  // renders
  if (!Array.isArray(m.renders) || m.renders.length === 0) {
    bad('renders', 'required non-empty array — an asset with no renders has nothing to ingest');
  } else {
    const renderIds = new Set();
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

  // texture-space channels
  for (const c of manifest.channels || []) {
    if (c.space !== 'texture') continue;
    const jsonPath = `channels(${c.id}).path`;
    const abs = contain(c.path, jsonPath);
    if (!abs) continue;

    if (c.encoding === 'npy') {
      try {
        const header = parseNpyHeader(await readFile(abs), c.path);
        if (header.dtype !== c.dtype) {
          violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
            `"${c.path}" has dtype ${header.dtype}, manifest declares ${c.dtype}`));
        }
        if (JSON.stringify(header.shape) !== JSON.stringify(c.shape)) {
          violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath,
            `"${c.path}" has shape [${header.shape}], manifest declares [${c.shape}]`));
        }
        resolved.textureChannels.set(c.id, { relPath: c.path, abs, meta: header });
      } catch (err) {
        violations.push(v('ASSET_ENCODING_MISMATCH', jsonPath, `"${c.path}": ${err.message}`));
      }
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
 *  - indexed: PLTE ⊆ declared palette — structural, no pixel decode
 *    (the brand/E09 contract: the PLTE *is* the palette; padded or
 *    undeclared entries are violations).
 *  - non-indexed + filter "nearest": exhaustive decode — every
 *    non-transparent pixel's color must be a declared class color.
 *  - non-indexed + filter "linear": no proof (classification is an ingest
 *    measurement with an unclassified share).
 */
function proveCategorical(decl, proved, jsonPath, violations) {
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
