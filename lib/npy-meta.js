/**
 * NPY header reader — structural validation for .npy channel files in the
 * asset-lane ingest contract (docs/asset-lane-kickoff.md).
 *
 * The asset contract lets a manifest declare a channel stored as a NumPy
 * array (facet's standing sidecars, e.g. a styled/unstyled mask or a future
 * per-texel view-owner map). sdlab never interprets the array's MEANING —
 * it proves the file's declared dtype and shape match its actual header,
 * the same way lib/png-meta.js proves a PNG's declared encoding matches
 * its IHDR. Header only; the payload is hashed, not parsed.
 *
 * Format reference: NumPy NEP 1 (the .npy format, versions 1.0/2.0/3.0):
 * magic "\x93NUMPY", one version byte pair, a little-endian header length
 * (2 bytes for v1, 4 bytes for v2+), then a Python dict literal with keys
 * 'descr', 'fortran_order', 'shape'.
 *
 * Schema 1.1.0 adds `readNpyValues` — still no MEANING, but a categorical
 * npy channel declares its classes, and "declared ⊆ actual" is provable only
 * by looking at the values. Kept to single-byte dtypes: those are what a
 * per-pixel class/owner map is, and a reader that cannot honestly decode a
 * dtype says so rather than skipping the proof silently.
 */

import { inputError } from './errors.js';

const MAGIC = Buffer.from('\x93NUMPY', 'latin1');

function npyError(message, hint) {
  return inputError('NPY_INVALID', message, hint);
}

/**
 * Parse a .npy file's header.
 *
 * @param {Buffer} buf — at least the first ~64KB of the file (the whole
 *   file is fine; only the header is read)
 * @param {string} [label] — filename for error messages
 * @returns {{dtype:string, fortranOrder:boolean, shape:number[],
 *            version:string, headerLength:number, dataOffset:number}}
 */
export function parseNpyHeader(buf, label = 'npy') {
  if (buf.length < 10 || !buf.subarray(0, 6).equals(MAGIC)) {
    throw npyError(`${label}: not a .npy file (bad magic).`);
  }
  const major = buf[6];
  const minor = buf[7];
  let headerLength;
  let headerStart;
  if (major === 1) {
    headerLength = buf.readUInt16LE(8);
    headerStart = 10;
  } else if (major === 2 || major === 3) {
    if (buf.length < 12) throw npyError(`${label}: truncated v${major} header.`);
    headerLength = buf.readUInt32LE(8);
    headerStart = 12;
  } else {
    throw npyError(`${label}: unsupported .npy format version ${major}.${minor}.`);
  }
  if (buf.length < headerStart + headerLength) {
    throw npyError(`${label}: truncated header (declared ${headerLength} bytes).`);
  }

  const header = buf.toString('latin1', headerStart, headerStart + headerLength);

  const descrMatch = header.match(/'descr'\s*:\s*'([^']+)'/);
  const fortranMatch = header.match(/'fortran_order'\s*:\s*(True|False)/);
  const shapeMatch = header.match(/'shape'\s*:\s*\(([^)]*)\)/);
  if (!descrMatch || !fortranMatch || !shapeMatch) {
    throw npyError(`${label}: header dict is missing descr/fortran_order/shape.`);
  }

  const shape = shapeMatch[1]
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => {
      const n = Number(s);
      if (!Number.isInteger(n) || n < 0) {
        throw npyError(`${label}: non-integer dimension "${s}" in shape.`);
      }
      return n;
    });

  return {
    dtype: descrMatch[1],
    fortranOrder: fortranMatch[1] === 'True',
    shape,
    version: `${major}.${minor}`,
    headerLength,
    dataOffset: headerStart + headerLength,
  };
}

/**
 * Single-byte dtypes whose values this contract can read. A categorical npy
 * channel must declare one of these — see readNpyValues.
 */
export const NPY_PROVABLE_DTYPES = new Set(['|i1', '|u1', '|b1']);

/**
 * Read an npy payload as a typed array. Single-byte dtypes only, so element
 * order is byte order and `fortran_order` does not change the VALUE SET a
 * categorical proof examines (it changes which index means which pixel —
 * that is the consumer's business, and numpy reads the flag itself).
 *
 * Also catches a truncation the header-only parse cannot: a file whose
 * payload is shorter than its declared shape.
 *
 * @param {Buffer} buf — the whole file
 * @param {ReturnType<typeof parseNpyHeader>} header
 * @param {string} [label]
 * @returns {Int8Array|Uint8Array}
 */
export function readNpyValues(buf, header, label = 'npy') {
  if (!NPY_PROVABLE_DTYPES.has(header.dtype)) {
    throw npyError(
      `${label}: dtype ${header.dtype} is not one this contract reads values from.`,
      `Value proofs cover ${[...NPY_PROVABLE_DTYPES].join(', ')} — the single-byte dtypes a per-pixel class or owner map uses. Export the channel in one of those, or drop "categorical" and let it ride as an opaque declared array.`
    );
  }
  const count = header.shape.reduce((a, b) => a * b, 1);
  const available = buf.length - header.dataOffset;
  if (available < count) {
    throw npyError(
      `${label}: truncated payload — shape ${JSON.stringify(header.shape)} needs ${count} byte(s), the file carries ${available} after the header.`
    );
  }
  const Ctor = header.dtype === '|i1' ? Int8Array : Uint8Array;
  return new Ctor(buf.buffer, buf.byteOffset + header.dataOffset, count);
}
