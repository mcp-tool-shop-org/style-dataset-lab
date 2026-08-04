/**
 * Candidate sheet — HTML contact sheet over an ARBITRARY directory of
 * images. No batch manifest required.
 *
 * lib/batch-sheet-render.js already has a complete, zero-dependency HTML
 * contact-sheet renderer, but it can only be reached from `sdlab batch
 * sheet`, which needs a batches/<id>/manifest.json that only `sdlab batch
 * generate` produces. This module reuses that renderer's shared primitives
 * (escapeHtml, computeColumns, generateCSS) rather than forking them, and
 * adds the one thing the batch path doesn't need: turning a plain directory
 * of images into reviewable tiles by matching each image to its record.
 *
 * Matching key: `asset_path` (project-root-relative, e.g.
 * "outputs/candidates/foo.png"), not a guessed id/filename convention.
 * Record id prefixes are NOT uniform across this codebase — hand-curated
 * records use the bare filename stem as their id, but lib/reingest.js
 * prefixes re-ingested records with "gen_". asset_path is the one field
 * every schema version agrees on, so it is the only safe join key.
 *
 * Images with no matching record (pre-ingest — generated but not yet
 * ingested into records/) still render: id/status/prompt degrade to
 * `null` and the tile falls back to the filename. This must never throw.
 */

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { join, relative, extname, basename, dirname } from 'node:path';
import { escapeHtml, computeColumns, generateCSS } from './batch-sheet-render.js';

// Mirrors lib/reingest.js's IMAGE_EXTENSIONS / lib/ingest.js's copy of the
// same set. Not imported from there — this is a small, stable, load-bearing
// constant duplicated by convention elsewhere in this codebase rather than
// centralized; see lib/ingest.js's own comment to that effect.
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp']);

/**
 * Normalize a path string to forward slashes with no leading "./", so
 * Windows-vs-POSIX path separators and a stray relative-path prefix never
 * cause an asset_path lookup to miss.
 */
function normalizeRelPath(p) {
  return String(p).replace(/\\/g, '/').replace(/^\.\//, '');
}

/**
 * Recursively collect every image file under `rootDir`, sorted
 * deterministically (lexicographic on the POSIX-normalized absolute path,
 * which — because every result shares the same root prefix — is exactly
 * equivalent to sorting on the relative path). Regenerating a sheet from an
 * unchanged directory always produces the same order.
 *
 * Never throws on a missing directory — returns `[]` instead, so callers
 * that already validated the directory exists (or want to treat "empty" and
 * "missing" the same way) don't need a try/catch.
 *
 * @param {string} rootDir — absolute directory to walk
 * @returns {Promise<string[]>} absolute file paths
 */
export async function walkImages(rootDir) {
  const found = [];

  async function walk(current) {
    let entries;
    try {
      entries = await readdir(current, { withFileTypes: true });
    } catch (err) {
      if (err && (err.code === 'ENOENT' || err.code === 'ENOTDIR')) return;
      throw err;
    }
    for (const entry of entries) {
      const full = join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(full);
      } else if (entry.isFile() && IMAGE_EXTENSIONS.has(extname(entry.name).toLowerCase())) {
        found.push(full);
      }
    }
  }

  await walk(rootDir);
  found.sort((a, b) => {
    const pa = normalizeRelPath(a);
    const pb = normalizeRelPath(b);
    return pa < pb ? -1 : pa > pb ? 1 : 0;
  });
  return found;
}

/**
 * Build an index of every record in a project, keyed by its normalized
 * asset_path. A malformed record file is skipped (not fatal) — same
 * resilience pattern as lib/batch-modes.js's listBatchModes(): one bad file
 * must not hide every good one.
 *
 * @param {string} projectRoot
 * @returns {Promise<Map<string, Object>>}
 */
export async function buildAssetPathIndex(projectRoot) {
  const recordsDir = join(projectRoot, 'records');
  const index = new Map();

  let files;
  try {
    files = await readdir(recordsDir);
  } catch (err) {
    if (err && err.code === 'ENOENT') return index;
    throw err;
  }

  for (const file of files) {
    if (!file.endsWith('.json')) continue;
    let record;
    try {
      record = JSON.parse(await readFile(join(recordsDir, file), 'utf-8'));
    } catch {
      continue; // malformed record file — skip, don't abort the whole scan
    }
    if (record && typeof record.asset_path === 'string' && record.asset_path.length > 0) {
      index.set(normalizeRelPath(record.asset_path), record);
    }
  }

  return index;
}

/**
 * Build the per-tile item list for a candidate sheet: every image under
 * `targetDir`, matched against the project's records by asset_path.
 *
 * Each item degrades gracefully when no record matches (pre-ingest state):
 * id/status/prompt are `null` and `hasRecord` is `false` — the caller
 * renders the filename instead. This never throws for that case.
 *
 * `status` distinguishes three states:
 *   - no record at all           → status: null,        hasRecord: false
 *   - record exists, unjudged    → status: 'uncurated',  hasRecord: true
 *   - record exists, judged      → status: <judgment.status>, hasRecord: true
 *
 * Ordering is deterministic (inherited from walkImages' sort) — regenerating
 * a sheet over an unchanged directory produces byte-identical item order.
 *
 * @param {string} projectRoot
 * @param {string} targetDir — absolute directory to sheet
 * @returns {Promise<Array<Object>>}
 */
export async function buildCandidateSheetItems(projectRoot, targetDir) {
  const [images, index] = await Promise.all([
    walkImages(targetDir),
    buildAssetPathIndex(projectRoot),
  ]);

  return images.map((absPath) => {
    const relFromRoot = normalizeRelPath(relative(projectRoot, absPath));
    const record = index.get(relFromRoot) || null;
    const hasRecord = !!record;
    return {
      absPath,
      relFromRoot,
      filename: basename(absPath),
      id: hasRecord ? (record.id ?? null) : null,
      status: hasRecord ? (record.judgment?.status ?? 'uncurated') : null,
      prompt: hasRecord ? (record.provenance?.prompt ?? null) : null,
      hasRecord,
    };
  });
}

/** Truncate long prompt text for inline display; full text stays in the title attribute. */
function truncate(str, max) {
  if (str.length <= max) return str;
  return `${str.slice(0, max - 1)}…`;
}

// Supplemental CSS for candidate-specific tile chrome (id/status/prompt).
// Appended to lib/batch-sheet-render.js's generateCSS() output rather than
// duplicating its grid/.cell/.label-bar/dark-theme rules.
const CANDIDATE_EXTRA_CSS = `
    .cell .cand-id-row {
      display: flex; align-items: center; justify-content: space-between; gap: 8px;
    }
    .cell .cand-id {
      font-weight: 600; color: #ccc;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .cell .cand-id--missing { color: #888; font-style: italic; font-weight: 400; }
    .cell .cand-status {
      flex: none;
      font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.03em;
      padding: 2px 6px; border-radius: 3px;
      background: #333; color: #aaa;
    }
    .cell .cand-status--approved { background: #1f4d2e; color: #8fdfa8; }
    .cell .cand-status--rejected { background: #4d1f1f; color: #df8f8f; }
    .cell .cand-status--borderline { background: #4d451f; color: #dfd08f; }
    .cell .cand-status--uncurated { background: #333333; color: #999; }
    .cell .cand-status--none { background: #262626; color: #666; }
    .cell .cand-prompt {
      margin-top: 4px; font-size: 0.72rem; color: #888; line-height: 1.3;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
      overflow: hidden;
    }
`;

/**
 * Render a single candidate tile. Image src is a RELATIVE path from the
 * directory the sheet HTML will be written to, to the image file — never
 * base64. These corpora run into the thousands of images; embedding would
 * make the sheet unopenable.
 */
function renderCandidateCell(item, sheetOutputDir) {
  const relImg = normalizeRelPath(relative(sheetOutputDir, item.absPath));
  const imgTag = `<img src="${escapeHtml(relImg)}" alt="${escapeHtml(item.filename)}" loading="lazy">`;

  const idHtml = item.id
    ? `<span class="cand-id">${escapeHtml(item.id)}</span>`
    : `<span class="cand-id cand-id--missing">${escapeHtml(item.filename)}</span>`;

  const statusText = item.hasRecord ? (item.status || 'uncurated') : 'no record';
  const statusClass = item.hasRecord ? `cand-status--${item.status || 'uncurated'}` : 'cand-status--none';
  const statusHtml = `<span class="cand-status ${escapeHtml(statusClass)}">${escapeHtml(statusText)}</span>`;

  const promptHtml = item.prompt
    ? `<div class="cand-prompt" title="${escapeHtml(item.prompt)}">${escapeHtml(truncate(item.prompt, 200))}</div>`
    : '';

  return `  <div class="cell">${imgTag}
    <div class="label-bar">
      <div class="cand-id-row">${idHtml}${statusHtml}</div>
      ${promptHtml}
    </div>
  </div>`;
}

/**
 * Render a full candidate sheet HTML document.
 *
 * @param {Object} opts
 * @param {Object[]} opts.items — from buildCandidateSheetItems()
 * @param {string} opts.title
 * @param {string} opts.sourceLabel — human-readable source dir (for the meta line)
 * @param {string} opts.sheetOutputDir — absolute dir the HTML file will be written to (image srcs are relative to this)
 * @param {string} [opts.generatedAt] — ISO timestamp; defaults to now (pass explicitly for deterministic tests)
 * @returns {string} HTML
 */
export function renderCandidateSheetHTML({ items, title, sourceLabel, sheetOutputDir, generatedAt }) {
  const columns = computeColumns(items.length || 1);
  const css = generateCSS('grid', columns, items.length) + CANDIDATE_EXTRA_CSS;
  const cellsHtml = items.map((item) => renderCandidateCell(item, sheetOutputDir)).join('\n');

  const matched = items.filter((i) => i.hasRecord).length;
  const preIngest = items.length - matched;

  const statusCounts = {};
  for (const item of items) {
    if (!item.hasRecord) continue;
    const key = item.status || 'uncurated';
    statusCounts[key] = (statusCounts[key] || 0) + 1;
  }
  const statusSummary = Object.entries(statusCounts)
    .map(([k, v]) => `${k}: ${v}`)
    .join(', ');

  const metaLine = [
    `Source: ${escapeHtml(sourceLabel)}`,
    `${items.length} image${items.length === 1 ? '' : 's'}`,
    `${matched} with record${matched === 1 ? '' : 's'}${statusSummary ? ` (${escapeHtml(statusSummary)})` : ''}`,
    `${preIngest} pre-ingest`,
  ].join(' | ');

  const stamp = generatedAt || new Date().toISOString();

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${escapeHtml(title)}</title>
<style>${css}</style>
</head>
<body>
<header>
  <h1>${escapeHtml(title)}</h1>
  <p class="meta">${metaLine}</p>
</header>
<div class="grid">${cellsHtml}
</div>
<footer>
  <p>Generated by style-dataset-lab — ${escapeHtml(stamp)}</p>
</footer>
</body>
</html>`;
}

/**
 * Turn a project-relative directory path into a filesystem-safe filename
 * stem, so the same source dir always maps to the same output filename
 * (regenerating overwrites in place instead of accumulating duplicates).
 */
export function slugifyRelPath(relPath) {
  const norm = normalizeRelPath(relPath || '');
  const slug = norm
    .replace(/[\\/]+/g, '-')
    .replace(/[^a-zA-Z0-9-_.]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return slug || 'sheet';
}

/**
 * Default output path for a candidate sheet over `relDir`.
 * @param {string} projectRoot
 * @param {string} relDir — project-relative source directory
 */
export function defaultSheetOutputPath(projectRoot, relDir) {
  return join(projectRoot, 'outputs', 'sheets', `${slugifyRelPath(relDir)}.html`);
}

/**
 * Write a candidate sheet HTML document to disk, creating parent
 * directories as needed.
 * @param {string} outputPath — absolute path to write
 * @param {string} html
 * @returns {Promise<string>} outputPath
 */
export async function saveCandidateSheet(outputPath, html) {
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, html);
  return outputPath;
}
