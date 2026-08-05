/**
 * Asset-lane color math — the palette-conformance gate ported
 * formula-faithfully from facet's `tools/palette_gate.py` (read-only port,
 * 2026-08-04), plus categorical class-share measurement for declared
 * render-space channels.
 *
 * Port fidelity notes (checked against the source, not paraphrased):
 *   - sRGB → linear → XYZ(D65) → Lab with the exact constants palette_gate.py
 *     uses (which itself matches facet's e08_deltaE.py).
 *   - C* = hypot(a*, b*); hue = atan2(b*, a*) in degrees, mod 360.
 *   - A band with lo <= hi is [lo, hi]; a band with lo > hi WRAPS AROUND 0°.
 *   - off-palette = (C* > min_chroma) AND (not in any band) AND inside the
 *     EXACT silhouette (mask value > 0.5 of full scale — a keyed mask would
 *     let background into the measurement; the E01 / E08-A2 failure).
 *   - TWO numbers, because they are two different failures: total off-palette
 *     (an antialiasing-spread diagnostic — its percentage bound is WITHDRAWN
 *     per facet 2026-08-04 and gates nothing unless the palette declares one)
 *     and the LARGEST 4-CONNECTED COMPONENT (an invented garment is one big
 *     blob), which is the load-bearing gate.
 *   - The chroma floor is load-bearing, not a tuning knob: hue is undefined
 *     at low chroma (W3's steel greatsword sits at C* 1.6–2.8 inside the
 *     blue band; without the floor it would flag on every view).
 *
 * Pure functions over decoded images (lib/png-meta.js output). No I/O, no
 * channel semantics — the palette, bands, classes and tolerances all arrive
 * from the asset's manifest. (Parnas boundary: this module knows color math;
 * lib/asset-source.js knows the contract.)
 */

import { inputError } from './errors.js';

// ─── sRGB → Lab (exact palette_gate.py constants) ────────────────────

const XYZ_M = [
  [0.4124564, 0.3575761, 0.1804375],
  [0.2126729, 0.7151522, 0.0721750],
  [0.0193339, 0.1191920, 0.9503041],
];
const WHITE = [0.95047, 1.0, 1.08883];
const LAB_E = 216 / 24389;
const LAB_K = 24389 / 27;

function srgbToLinear(c) {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function labF(t) {
  return t > LAB_E ? Math.cbrt(t) : (LAB_K * t + 16) / 116;
}

/**
 * Convert one sRGB pixel (0–255 ints) to Lab.
 * @returns {[number, number, number]} [L, a, b]
 */
export function srgbToLab(r8, g8, b8) {
  const r = srgbToLinear(r8 / 255);
  const g = srgbToLinear(g8 / 255);
  const b = srgbToLinear(b8 / 255);
  const x = (XYZ_M[0][0] * r + XYZ_M[0][1] * g + XYZ_M[0][2] * b) / WHITE[0];
  const y = (XYZ_M[1][0] * r + XYZ_M[1][1] * g + XYZ_M[1][2] * b) / WHITE[1];
  const z = (XYZ_M[2][0] * r + XYZ_M[2][1] * g + XYZ_M[2][2] * b) / WHITE[2];
  const fx = labF(x);
  const fy = labF(y);
  const fz = labF(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

// ─── Decoded-image pixel access ──────────────────────────────────────

/**
 * Read pixel i of a decoded PNG as [r, g, b] (0–255), independent of the
 * source color type (grayscale, RGB, RGBA, or indexed via its PLTE).
 */
export function rgbAt(img, i) {
  switch (img.colorType) {
    case 0: {
      const v = img.data[i];
      return [v, v, v];
    }
    case 2: {
      const o = i * 3;
      return [img.data[o], img.data[o + 1], img.data[o + 2]];
    }
    case 6: {
      const o = i * 4;
      return [img.data[o], img.data[o + 1], img.data[o + 2]];
    }
    case 3: {
      const entry = img.palette[img.data[i]];
      return [entry[0], entry[1], entry[2]];
    }
    default:
      throw inputError('PNG_UNSUPPORTED', `rgbAt: unsupported color type ${img.colorType}.`);
  }
}

/** Alpha of pixel i (255 when the image has no alpha channel). */
export function alphaAt(img, i) {
  return img.colorType === 6 ? img.data[i * 4 + 3] : 255;
}

/**
 * Binarize a decoded grayscale silhouette: value > 127 (i.e. > 0.5 of full
 * scale, matching palette_gate.py's `> 0.5` on a /255 float) = figure.
 * @returns {Uint8Array} 0/1 per pixel
 */
export function silhouetteToMask(img, label = 'silhouette') {
  if (img.colorType !== 0) {
    throw inputError(
      'ASSET_ENCODING_MISMATCH',
      `${label}: silhouette masks must be grayscale PNGs (color type 0), got ${img.colorType}.`
    );
  }
  const mask = new Uint8Array(img.width * img.height);
  for (let i = 0; i < mask.length; i++) mask[i] = img.data[i] > 127 ? 1 : 0;
  return mask;
}

// ─── Connected components (4-connectivity, matching scipy.ndimage.label
//     with its default cross-shaped structure) ────────────────────────

/**
 * Size in pixels of the largest 4-connected component of a 0/1 mask.
 */
export function largestComponent4(mask, width, height) {
  const visited = new Uint8Array(mask.length);
  const stack = new Int32Array(mask.length);
  let largest = 0;
  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || visited[start]) continue;
    let top = 0;
    stack[top++] = start;
    visited[start] = 1;
    let size = 0;
    while (top > 0) {
      const i = stack[--top];
      size++;
      const x = i % width;
      const y = (i - x) / width;
      if (x > 0 && mask[i - 1] && !visited[i - 1]) { visited[i - 1] = 1; stack[top++] = i - 1; }
      if (x < width - 1 && mask[i + 1] && !visited[i + 1]) { visited[i + 1] = 1; stack[top++] = i + 1; }
      if (y > 0 && mask[i - width] && !visited[i - width]) { visited[i - width] = 1; stack[top++] = i - width; }
      if (y < height - 1 && mask[i + width] && !visited[i + width]) { visited[i + width] = 1; stack[top++] = i + width; }
    }
    if (size > largest) largest = size;
  }
  return largest;
}

// ─── The palette gate ────────────────────────────────────────────────

function median(values) {
  if (values.length === 0) return 0;
  const sorted = Float64Array.from(values).sort();
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function round(v, places) {
  const f = 10 ** places;
  return Math.round(v * f) / f;
}

/**
 * Run the ported palette-conformance gate on one render.
 *
 * @param {Object} renderImg — decoded render (lib/png-meta.js decodePng)
 * @param {Object} silhouetteImg — decoded grayscale silhouette, same dims
 * @param {Object} palette — the manifest's palette block:
 *   {min_chroma, allowed_bands: [{name, hue_deg: [lo, hi]}],
 *    gate: {max_offpalette_pct: number|null, max_offpalette_blob_px: number}}
 * @param {string} [label] — for error messages
 * @returns {{figure_px:number, offpalette_px:number, offpalette_pct:number,
 *            largest_blob_px:number, pass:boolean, withdrawn_pct_bound:boolean,
 *            dominant:Object|null}}
 */
export function paletteGate(renderImg, silhouetteImg, palette, label = 'render') {
  if (renderImg.width !== silhouetteImg.width || renderImg.height !== silhouetteImg.height) {
    // The parallel-mask ANDON from palette_gate.py: a mask that does not
    // match its image measures the wrong pixels silently.
    throw inputError(
      'ASSET_MASK_MISMATCH',
      `${label}: silhouette is ${silhouetteImg.width}x${silhouetteImg.height} but the render is ${renderImg.width}x${renderImg.height}.`
    );
  }

  const mask = silhouetteToMask(silhouetteImg, `${label} silhouette`);
  const bands = palette.allowed_bands.map((b) => ({
    lo: Number(b.hue_deg[0]),
    hi: Number(b.hue_deg[1]),
  }));
  const cmin = Number(palette.min_chroma);
  const maxPct = palette.gate.max_offpalette_pct == null ? null : Number(palette.gate.max_offpalette_pct);
  const maxBlob = Number(palette.gate.max_offpalette_blob_px);

  const n = renderImg.width * renderImg.height;
  const off = new Uint8Array(n);
  let figurePx = 0;
  let offPx = 0;
  const offChroma = [];
  const offHue = [];
  const offRgb = [];

  for (let i = 0; i < n; i++) {
    if (!mask[i]) continue;
    figurePx++;
    const [r, g, b] = rgbAt(renderImg, i);
    const [, a, bb] = srgbToLab(r, g, b);
    const chroma = Math.hypot(a, bb);
    if (chroma <= cmin) continue; // hue undefined below the floor
    let hue = (Math.atan2(bb, a) * 180) / Math.PI;
    hue = ((hue % 360) + 360) % 360;
    let inBand = false;
    for (const { lo, hi } of bands) {
      if (lo <= hi ? hue >= lo && hue <= hi : hue >= lo || hue <= hi) { inBand = true; break; }
    }
    if (inBand) continue;
    off[i] = 1;
    offPx++;
    offChroma.push(chroma);
    offHue.push(hue);
    offRgb.push([r, g, b]);
  }

  const pct = (100 * offPx) / Math.max(figurePx, 1);
  const blob = offPx > 0 ? largestComponent4(off, renderImg.width, renderImg.height) : 0;
  const pass = blob <= maxBlob && (maxPct === null || pct <= maxPct);

  // Dominant off-palette mass, so a failure is diagnosable, not just flagged
  // (same 36-bin histogram + medians as the source).
  let dominant = null;
  if (offPx > 0) {
    const hist = new Array(36).fill(0);
    for (const h of offHue) hist[Math.min(35, Math.floor(h / 10))]++;
    let top = 0;
    for (let i = 1; i < 36; i++) if (hist[i] > hist[top]) top = i;
    dominant = {
      hue_lo: top * 10,
      hue_hi: (top + 1) * 10,
      share_of_offpalette: round((hist[top] / offPx) * 100, 1),
      median_chroma: round(median(offChroma), 1),
      median_rgb: [
        Math.round(median(offRgb.map((p) => p[0]))),
        Math.round(median(offRgb.map((p) => p[1]))),
        Math.round(median(offRgb.map((p) => p[2]))),
      ],
    };
  }

  return {
    figure_px: figurePx,
    offpalette_px: offPx,
    offpalette_pct: round(pct, 4),
    largest_blob_px: blob,
    pass,
    withdrawn_pct_bound: maxPct === null,
    dominant,
  };
}

// ─── Categorical class shares ────────────────────────────────────────

/**
 * Measure per-class coverage of a categorical render-space channel inside
 * the silhouette. Shares are computed for EVERY declared class — this module
 * never knows which class matters; the manifest's consumers do.
 *
 * `filter: "nearest"` ⇒ exact color match (tolerance 0).
 * `filter: "linear"`  ⇒ nearest declared class within
 *                       `classification_tolerance` (RGB euclidean); pixels
 *                       beyond it are honestly `unclassified`.
 * Fully transparent pixels (alpha 0) are excluded — background, not class.
 *
 * @param {Object} channelImg — decoded channel instance
 * @param {Object} silhouetteImg — decoded grayscale silhouette, same dims
 * @param {Object} decl — the channel declaration:
 *   {palette: [{name, rgb: [r,g,b]}], filter, classification_tolerance?}
 * @param {string} [label]
 * @returns {{figure_px:number,
 *            classes:Object<string,{px:number, share:number}>,
 *            unclassified:{px:number, share:number}}}
 */
export function classShares(channelImg, silhouetteImg, decl, label = 'channel') {
  if (channelImg.width !== silhouetteImg.width || channelImg.height !== silhouetteImg.height) {
    throw inputError(
      'ASSET_MASK_MISMATCH',
      `${label}: channel is ${channelImg.width}x${channelImg.height} but the silhouette is ${silhouetteImg.width}x${silhouetteImg.height}.`
    );
  }
  const mask = silhouetteToMask(silhouetteImg, `${label} silhouette`);
  const tolerance = decl.filter === 'nearest' ? 0 : Number(decl.classification_tolerance ?? 0);
  const tol2 = tolerance * tolerance;
  const classes = decl.palette.map((c) => ({ name: c.name, rgb: c.rgb, px: 0 }));

  let figurePx = 0;
  let unclassified = 0;
  const n = channelImg.width * channelImg.height;

  for (let i = 0; i < n; i++) {
    if (!mask[i]) continue;
    if (alphaAt(channelImg, i) === 0) continue; // transparent = background
    figurePx++;
    const [r, g, b] = rgbAt(channelImg, i);
    let best = -1;
    let bestD = Infinity;
    for (let c = 0; c < classes.length; c++) {
      const [cr, cg, cb] = classes[c].rgb;
      const d = (r - cr) * (r - cr) + (g - cg) * (g - cg) + (b - cb) * (b - cb);
      if (d < bestD) { bestD = d; best = c; }
    }
    if (best >= 0 && bestD <= tol2) classes[best].px++;
    else unclassified++;
  }

  const share = (px) => round((100 * px) / Math.max(figurePx, 1), 4);
  const out = {};
  for (const c of classes) out[c.name] = { px: c.px, share: share(c.px) };
  return {
    figure_px: figurePx,
    classes: out,
    unclassified: { px: unclassified, share: share(unclassified) },
  };
}
