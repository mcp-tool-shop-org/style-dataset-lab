/**
 * PNG structural reader — dependency-free IHDR/PLTE parsing and a minimal
 * pixel decoder for the asset-lane's encoding proofs.
 *
 * Why this exists (asset lane, docs/asset-lane-kickoff.md): the ingest
 * contract validates that a channel file's ACTUAL bytes match its DECLARED
 * encoding, and that a categorical channel's palette is provably a subset
 * of the palette the manifest declares. The brand/E09 lesson is to prove
 * this structurally (PLTE chunk ⊆ declared palette) rather than sampling
 * pixels and hoping. For categorical channels that are not indexed yet
 * (facet's pre-E09 exports), the fallback proof is EXHAUSTIVE — every
 * pixel, not a sample — which needs a decoder.
 *
 * Deliberately minimal, in the repo's zero-dependency spirit:
 *   - parsePngMeta() reads only the header chunks (IHDR, PLTE, tRNS) and
 *     never inflates pixel data — cheap enough to run on every referenced
 *     file at ingest.
 *   - decodePng() supports exactly the shapes the asset contract admits:
 *     bit depth 8 for gray/RGB/RGBA (color types 0/2/6) and bit depths
 *     1/2/4/8 for indexed (color type 3); no interlacing, no 16-bit.
 *     Anything else is a structured refusal, not a silent skip — a wrong
 *     file that looks right is the failure class this lane exists to stop.
 *
 * This module knows the PNG format and nothing else: no channel roles, no
 * palettes-as-meaning, no project paths. (Parnas boundary — the manifest
 * semantics live in lib/asset-source.js.)
 */

import { inflateSync } from 'node:zlib';
import { inputError } from './errors.js';

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** Channels per PNG color type (bit-depth-independent). */
const CHANNELS_BY_COLOR_TYPE = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 };

/** Human-readable names for error messages. */
export const COLOR_TYPE_NAMES = {
  0: 'grayscale',
  2: 'rgb',
  3: 'indexed',
  4: 'grayscale-alpha',
  6: 'rgba',
};

function pngError(message, hint) {
  return inputError('PNG_INVALID', message, hint);
}

function unsupportedError(message, hint) {
  return inputError('PNG_UNSUPPORTED', message, hint);
}

/**
 * Walk the chunk stream, yielding {type, offset, length} without copying
 * data. Throws on a malformed layout (truncated chunk, missing signature).
 */
function* chunks(buf, label) {
  if (buf.length < 8 || !buf.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw pngError(`${label}: not a PNG file (bad signature).`);
  }
  let off = 8;
  while (off + 8 <= buf.length) {
    const length = buf.readUInt32BE(off);
    const type = buf.toString('latin1', off + 4, off + 8);
    const dataStart = off + 8;
    if (dataStart + length + 4 > buf.length) {
      throw pngError(`${label}: truncated ${type} chunk.`);
    }
    yield { type, dataStart, length };
    off = dataStart + length + 4; // skip CRC
    if (type === 'IEND') return;
  }
}

/**
 * Read IHDR + PLTE + tRNS without touching pixel data.
 *
 * @param {Buffer} buf — full PNG file contents
 * @param {string} [label] — filename for error messages
 * @returns {{width:number, height:number, bitDepth:number, colorType:number,
 *            colorTypeName:string, interlaced:boolean,
 *            palette:Array<[number,number,number]>|null,
 *            transparency:Uint8Array|null}}
 */
export function parsePngMeta(buf, label = 'png') {
  let ihdr = null;
  let palette = null;
  let transparency = null;

  for (const { type, dataStart, length } of chunks(buf, label)) {
    if (type === 'IHDR') {
      if (length !== 13) throw pngError(`${label}: IHDR chunk has length ${length}, expected 13.`);
      ihdr = {
        width: buf.readUInt32BE(dataStart),
        height: buf.readUInt32BE(dataStart + 4),
        bitDepth: buf[dataStart + 8],
        colorType: buf[dataStart + 9],
        interlaced: buf[dataStart + 12] !== 0,
      };
    } else if (type === 'PLTE') {
      if (length % 3 !== 0) throw pngError(`${label}: PLTE length ${length} is not a multiple of 3.`);
      palette = [];
      for (let i = 0; i < length; i += 3) {
        palette.push([buf[dataStart + i], buf[dataStart + i + 1], buf[dataStart + i + 2]]);
      }
    } else if (type === 'tRNS') {
      transparency = new Uint8Array(buf.subarray(dataStart, dataStart + length));
    } else if (type === 'IDAT') {
      break; // meta chunks precede IDAT per spec; stop before pixel data
    }
  }

  if (!ihdr) throw pngError(`${label}: missing IHDR chunk.`);
  if (!(ihdr.colorType in CHANNELS_BY_COLOR_TYPE)) {
    throw pngError(`${label}: unknown color type ${ihdr.colorType}.`);
  }
  return {
    ...ihdr,
    colorTypeName: COLOR_TYPE_NAMES[ihdr.colorType],
    palette,
    transparency,
  };
}

// ─── Pixel decoding ──────────────────────────────────────────────────

/** Paeth predictor (RFC 2083 §6.6). */
function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

/**
 * Reverse the per-scanline filters in place, returning the raw (still
 * possibly bit-packed) scanline bytes with the filter bytes stripped.
 */
function unfilter(raw, height, bytesPerLine, bpp, label) {
  const out = Buffer.alloc(height * bytesPerLine);
  let inOff = 0;
  for (let y = 0; y < height; y++) {
    const filter = raw[inOff++];
    const lineStart = y * bytesPerLine;
    const prevStart = (y - 1) * bytesPerLine;
    for (let x = 0; x < bytesPerLine; x++) {
      const cur = raw[inOff + x];
      const left = x >= bpp ? out[lineStart + x - bpp] : 0;
      const up = y > 0 ? out[prevStart + x] : 0;
      const upLeft = y > 0 && x >= bpp ? out[prevStart + x - bpp] : 0;
      let value;
      switch (filter) {
        case 0: value = cur; break;
        case 1: value = cur + left; break;
        case 2: value = cur + up; break;
        case 3: value = cur + ((left + up) >> 1); break;
        case 4: value = cur + paeth(left, up, upLeft); break;
        default:
          throw pngError(`${label}: unknown scanline filter ${filter} at row ${y}.`);
      }
      out[lineStart + x] = value & 0xff;
    }
    inOff += bytesPerLine;
  }
  return out;
}

/** Unpack sub-byte indexed scanlines (bit depths 1/2/4) to one index per byte. */
function unpackIndices(lines, width, height, bitDepth, bytesPerLine) {
  const out = new Uint8Array(width * height);
  const perByte = 8 / bitDepth;
  const mask = (1 << bitDepth) - 1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const byte = lines[y * bytesPerLine + Math.floor(x / perByte)];
      const shift = 8 - bitDepth * ((x % perByte) + 1);
      out[y * width + x] = (byte >> shift) & mask;
    }
  }
  return out;
}

/**
 * Decode a PNG's pixels into a flat typed array.
 *
 * Supported: color types 0/2/6 at bit depth 8, color type 3 at bit depths
 * 1/2/4/8, non-interlaced. Everything else throws PNG_UNSUPPORTED with the
 * exact reason — the caller decides whether that's a contract violation.
 *
 * @param {Buffer} buf — full PNG file contents
 * @param {string} [label] — filename for error messages
 * @returns {{width:number, height:number, colorType:number, bitDepth:number,
 *            channels:number, data:Uint8Array,
 *            palette:Array<[number,number,number]>|null}}
 *   For color type 3, `data` holds palette INDICES (one per pixel) and
 *   `palette` holds the PLTE entries; for other types, `data` holds
 *   interleaved channel bytes.
 */
export function decodePng(buf, label = 'png') {
  const meta = parsePngMeta(buf, label);
  const { width, height, bitDepth, colorType } = meta;

  if (meta.interlaced) {
    throw unsupportedError(
      `${label}: interlaced (Adam7) PNGs are not supported by the asset contract.`,
      'Re-export without interlacing.'
    );
  }
  const indexed = colorType === 3;
  if (!indexed && bitDepth !== 8) {
    throw unsupportedError(
      `${label}: bit depth ${bitDepth} for ${COLOR_TYPE_NAMES[colorType]} is not supported (8 only).`,
      'Re-export at 8 bits per channel.'
    );
  }
  if (indexed && ![1, 2, 4, 8].includes(bitDepth)) {
    throw unsupportedError(`${label}: bit depth ${bitDepth} is invalid for an indexed PNG.`);
  }
  if (indexed && !meta.palette) {
    throw pngError(`${label}: indexed PNG has no PLTE chunk.`);
  }

  // Concatenate IDAT payloads, inflate once.
  const idatParts = [];
  for (const { type, dataStart, length } of chunks(buf, label)) {
    if (type === 'IDAT') idatParts.push(buf.subarray(dataStart, dataStart + length));
  }
  if (idatParts.length === 0) throw pngError(`${label}: no IDAT chunks.`);
  let raw;
  try {
    raw = inflateSync(Buffer.concat(idatParts));
  } catch (err) {
    throw pngError(`${label}: IDAT inflate failed (${err.message}).`);
  }

  const channels = CHANNELS_BY_COLOR_TYPE[colorType];
  const bitsPerPixel = channels * bitDepth;
  const bytesPerLine = Math.ceil((width * bitsPerPixel) / 8);
  const bpp = Math.max(1, bitsPerPixel >> 3);

  const expected = height * (bytesPerLine + 1);
  if (raw.length < expected) {
    throw pngError(`${label}: decompressed pixel data is short (${raw.length} < ${expected}).`);
  }

  const lines = unfilter(raw, height, bytesPerLine, bpp, label);

  let data;
  if (indexed && bitDepth < 8) {
    data = unpackIndices(lines, width, height, bitDepth, bytesPerLine);
  } else {
    // 8-bit paths: lines are already one byte per sample, tightly packed.
    data = new Uint8Array(lines.buffer, lines.byteOffset, width * height * channels);
    // Copy so callers can't be surprised by the underlying Buffer pool.
    data = new Uint8Array(data);
  }

  return { width, height, colorType, bitDepth, channels, data, palette: meta.palette };
}
