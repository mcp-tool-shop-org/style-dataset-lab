/**
 * _resume.js — internal helper module (NOT a CLI command; underscore prefix
 * matches the existing scripts/_batch_cut.py / _seam_cutout.py convention
 * for "helper, not dispatched by bin/sdlab.js").
 *
 * H5: generate.js was the only one of the four ComfyUI generator scripts
 * that implemented `--resume` — skip an asset whose provenance record AND
 * output image already exist on disk, WITHOUT skipping its seed slot, so a
 * resumed run stays bit-identical to an uninterrupted one. generate-identity
 * / generate-controlnet / generate-ipadapter had no --resume at all, which
 * is expensive specifically for generate-identity (the priciest per-image
 * generator in the pipeline): interrupting a 12-subject run after subject 9
 * meant regenerating all 12 from scratch.
 *
 * Extracted here (once) so all four generators — and any future one — get
 * the same discipline by importing it, instead of by copy-pasting the check
 * next to generate.js's inline version. `lib/` is outside this fix's file
 * ownership, so this lives under scripts/** instead; see the dispatch
 * report for the full rationale.
 *
 * `requireRecord` exists because not every generator writes a provenance
 * record: generate.js and generate-identity.js both write
 * records/<id>.json, but generate-controlnet.js and generate-ipadapter.js
 * are lighter-weight discovery scripts that only ever write the output PNG
 * — they have no records/ write path at all. Requiring a record that a
 * script structurally never writes would make --resume a permanent no-op
 * for those two, which is worse than not having the flag. Pass
 * `{ requireRecord: false }` for generators with no records/ write path.
 */
import { existsSync } from 'node:fs';
import { join } from 'node:path';

/**
 * @param {string} projectRoot — GAME_ROOT
 * @param {string} assetId — the record id / output filename stem (no extension)
 * @param {Object} [opts]
 * @param {boolean} [opts.requireRecord=true] — also require records/<id>.json
 * @param {string} [opts.recordsSubdir='records']
 * @param {string} [opts.candidatesSubdir='outputs/candidates']
 * @returns {boolean} true when the asset is safe to skip on --resume
 */
export function isResumable(projectRoot, assetId, opts = {}) {
  const requireRecord = opts.requireRecord !== false;
  const candidatesSubdir = opts.candidatesSubdir || 'outputs/candidates';
  const imagePath = join(projectRoot, candidatesSubdir, `${assetId}.png`);
  if (!existsSync(imagePath)) return false;

  if (!requireRecord) return true;

  const recordsSubdir = opts.recordsSubdir || 'records';
  const recordPath = join(projectRoot, recordsSubdir, `${assetId}.json`);
  return existsSync(recordPath);
}

/**
 * Print the standard "(resumed — skipped)" progress line — matches
 * generate.js's console.log verbatim so all four generators read
 * identically under --resume.
 */
export function logResumedSkip(index, total, assetId) {
  console.log(`  [${index}/${total}] ${assetId} \x1b[2m(resumed — skipped)\x1b[0m`);
}
