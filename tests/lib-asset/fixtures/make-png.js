/**
 * Test-only PNG encoder — the counterpart of lib/png-meta.js's decoder.
 *
 * Exists so asset-lane tests can materialize ANY png the contract might
 * meet — valid indexed/rgb/rgba/grayscale files, sub-byte indexed depths,
 * padded palettes, interlace flags, wrong bit depths — without committed
 * binary fixtures or a Python dependency. Filter 0 on every scanline by
 * default; `scanlines` accepts pre-filtered rows for decoder filter tests.
 */

import { deflateSync } from 'node:zlib';

// ─── CRC32 (PNG chunk checksums) ─────────────────────────────────────

const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const out = Buffer.alloc(12 + data.length);
  out.writeUInt32BE(data.length, 0);
  out.write(type, 4, 'latin1');
  data.copy(out, 8);
  out.writeUInt32BE(crc32(out.subarray(4, 8 + data.length)), 8 + data.length);
  return out;
}

const CHANNELS_BY_COLOR_TYPE = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 };

/**
 * Encode a PNG.
 *
 * @param {Object} opts
 * @param {number} opts.width
 * @param {number} opts.height
 * @param {number} opts.colorType — 0 gray, 2 rgb, 3 indexed, 6 rgba
 * @param {number} [opts.bitDepth=8] — 1/2/4/8 for indexed, 8 otherwise
 * @param {Uint8Array|number[]} [opts.data] — one sample value per channel per
 *   pixel (indices for indexed), unpacked; required unless scanlines given
 * @param {Array<[number,number,number]>} [opts.palette] — PLTE entries (indexed)
 * @param {Buffer} [opts.scanlines] — pre-filtered raw scanline stream
 *   (filter byte + packed bytes per row); overrides data
 * @param {number} [opts.interlace=0]
 * @returns {Buffer}
 */
export function encodePng({ width, height, colorType, bitDepth = 8, data, palette, scanlines, interlace = 0 }) {
  const channels = CHANNELS_BY_COLOR_TYPE[colorType];

  let raw;
  if (scanlines) {
    raw = scanlines;
  } else {
    const bitsPerPixel = channels * bitDepth;
    const bytesPerLine = Math.ceil((width * bitsPerPixel) / 8);
    raw = Buffer.alloc(height * (bytesPerLine + 1));
    for (let y = 0; y < height; y++) {
      const rowStart = y * (bytesPerLine + 1);
      raw[rowStart] = 0; // filter: None
      if (bitDepth === 8) {
        for (let i = 0; i < width * channels; i++) {
          raw[rowStart + 1 + i] = data[y * width * channels + i];
        }
      } else {
        // sub-byte indexed packing
        const perByte = 8 / bitDepth;
        for (let x = 0; x < width; x++) {
          const idx = data[y * width + x];
          const byteOff = rowStart + 1 + Math.floor(x / perByte);
          const shift = 8 - bitDepth * ((x % perByte) + 1);
          raw[byteOff] |= (idx & ((1 << bitDepth) - 1)) << shift;
        }
      }
    }
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = bitDepth;
  ihdr[9] = colorType;
  ihdr[10] = 0; // compression
  ihdr[11] = 0; // filter method
  ihdr[12] = interlace;

  const parts = [
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
  ];
  if (colorType === 3) {
    const plte = Buffer.alloc((palette || []).length * 3);
    (palette || []).forEach(([r, g, b], i) => {
      plte[i * 3] = r; plte[i * 3 + 1] = g; plte[i * 3 + 2] = b;
    });
    parts.push(chunk('PLTE', plte));
  }
  parts.push(chunk('IDAT', deflateSync(raw)));
  parts.push(chunk('IEND', Buffer.alloc(0)));
  return Buffer.concat(parts);
}

/**
 * Apply a PNG filter FORWARD to raw scanlines (for decoder filter tests:
 * encode with a chosen filter per row, expect the decoder to invert it).
 *
 * @param {Uint8Array} samples — unpacked 8-bit samples, width*channels per row
 * @param {number} width
 * @param {number} height
 * @param {number} channels
 * @param {number[]} filters — one PNG filter id (0–4) per row
 * @returns {Buffer} raw scanline stream (filter byte + filtered bytes per row)
 */
export function forwardFilter(samples, width, height, channels, filters) {
  const bpl = width * channels;
  const out = Buffer.alloc(height * (bpl + 1));
  const prior = new Uint8Array(bpl);
  for (let y = 0; y < height; y++) {
    const f = filters[y];
    out[y * (bpl + 1)] = f;
    for (let x = 0; x < bpl; x++) {
      const cur = samples[y * bpl + x];
      const left = x >= channels ? samples[y * bpl + x - channels] : 0;
      const up = y > 0 ? prior[x] : 0;
      const upLeft = y > 0 && x >= channels ? prior[x - channels] : 0;
      let val;
      switch (f) {
        case 0: val = cur; break;
        case 1: val = cur - left; break;
        case 2: val = cur - up; break;
        case 3: val = cur - ((left + up) >> 1); break;
        case 4: {
          const p = left + up - upLeft;
          const pa = Math.abs(p - left);
          const pb = Math.abs(p - up);
          const pc = Math.abs(p - upLeft);
          const pred = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
          val = cur - pred;
          break;
        }
        default: throw new Error(`bad filter ${f}`);
      }
      out[y * (bpl + 1) + 1 + x] = val & 0xff;
    }
    for (let x = 0; x < bpl; x++) prior[x] = samples[y * bpl + x];
  }
  return out;
}
