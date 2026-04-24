/**
 * Three-projection build orchestrator.
 *
 * `sdlab canon build` entry point (scripts/canon-build.js calls runBuild).
 *
 * Flow:
 *   1. Load canon-build/config.json (D9 lane map lives here).
 *   2. Load all referenced schemas + resolve schema versions (D7).
 *   3. Discover entries under `canon_root/<entity_dir>/`.
 *   4. Resolve each entry's lane (D3).
 *   5. Compute entry_hash = sha256(body || schema_version || config || project_fingerprint).
 *      Cache-hit = bypass emitter; cache-miss = run emitter + write cache (D4).
 *   6. Write outputs under `<project>/canon-build/<canon_sha>.tmp/` atomically,
 *      rename to `<canon_sha>/` on full completion.
 *   7. Manifest.json records per-entity hashes + stats for audit.
 */

import { readFile, writeFile, mkdir, rename, rm } from 'node:fs/promises';
import { join, relative, dirname } from 'node:path';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execSync } from 'node:child_process';
import { loadBuildConfig } from './load-config.js';
import { loadSchema } from './load-schema.js';
import { loadCanonEntriesInDir, entryId } from './load-entry.js';
import { resolveLane } from './lane-resolve.js';
import { getEmitter } from './emitters/index.js';
import { resolveContextMaxLines, checkContextLength } from './emitters/base.js';
import { canonEntryToRow, serializeRow, ROW_SCHEMA_VERSION } from '../rows.js';
import { computeConfigFingerprint } from '../snapshot.js';
import { loadTrainingProfile } from '../training-profiles.js';
import { deriveStyleTrigger } from '../captions.js';
import { inputError, runtimeError } from '../errors.js';
import { readFreezeStatus, resolveWatchFields, computeWatchHash } from '../freeze-stamp.js';

const BUILD_SCHEMA_VERSION = 'canon-build-manifest-1.0';

/**
 * Main entry point.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot — absolute path to the sdlab project
 * @param {boolean} [opts.full] — force full rebuild (ignore cache hits)
 * @param {boolean} [opts.noCache] — neither read nor write the cache
 * @param {boolean} [opts.dryRun] — walk + resolve + plan; write nothing
 * @param {Array<string>} [opts.only] — limit to specific entity ids
 * @returns {Promise<Object>} result summary
 */
export async function runBuild(opts) {
  const { projectRoot, full = false, noCache = false, dryRun = false, only = null } = opts;

  const configPath = join(projectRoot, 'canon-build', 'config.json');
  const config = await loadBuildConfig(configPath, projectRoot);

  // Load schemas
  const schemas = {};
  for (const schemaName of Object.keys(config.entity_dirs)) {
    const schemaPath = join(config.schema_dir, schemaName);
    if (!existsSync(schemaPath)) {
      throw inputError(
        'CANON_SCHEMA_NOT_FOUND',
        `Schema file ${schemaName} not found at ${schemaPath}`,
        `Check canon-build/config.json schema_dir and the schema filename.`,
      );
    }
    schemas[schemaName] = await loadSchema(schemaPath);
  }

  // Resolve the training profile (for trigger + caption strategy)
  let profile = null;
  let trigger = null;
  if (config.profile_id) {
    profile = await loadTrainingProfile(projectRoot, config.profile_id);
    trigger = deriveStyleTrigger(profile);
  }

  // Compute the generated_from stamp (git SHA if available, else content-sha)
  const generatedFrom = resolveGeneratedFrom(config.canon_root);
  // Path-safe variant for filesystem use — Windows cannot contain ":" in a
  // directory name, so "content-sha:abc" becomes "content-sha-abc" on disk.
  // The manifest fields (generated_from in rows, manifest.json, context
  // frontmatter) carry the original unsanitized value so audit tooling can
  // reason about it directly.
  const generatedFromDir = generatedFrom.replace(/:/g, '-');

  // Compute cache inputs that apply to every entry
  const projectFingerprint = computeConfigFingerprint(projectRoot);
  const buildConfigHash = sha256(config.raw_text || '');

  // Discover all entries
  const entries = [];
  const schemaChangeTriggersFullRebuild = await detectSchemaChange(projectRoot, schemas, full);

  for (const [schemaName, subdir] of Object.entries(config.entity_dirs)) {
    const dir = join(config.canon_root, subdir);
    const loaded = await loadCanonEntriesInDir(dir);
    for (const entry of loaded) {
      const id = entryId(entry);
      if (only && !only.includes(id)) continue;
      entries.push({ entry, schemaName, id });
    }
  }

  // Emit per-entity
  const outputDir = join(projectRoot, 'canon-build', generatedFromDir);
  const stagingDir = join(projectRoot, 'canon-build', `${generatedFromDir}.tmp-${process.pid}`);
  const cacheDir = join(projectRoot, 'canon-build', '.cache');

  const effectiveFull = full || schemaChangeTriggersFullRebuild;
  const contextLimitFailures = [];
  const rows = [];
  let cached = 0;
  let rebuilt = 0;

  for (const { entry, schemaName, id } of entries) {
    const schemaInfo = schemas[schemaName];
    const entryHashInputs = {
      entryBody: entry.rawText,
      schemaVersion: schemaInfo.version,
      buildConfigJson: config.raw_text,
      projectFingerprint,
    };
    const entryHash = sha256(
      `${entryHashInputs.entryBody}\0${entryHashInputs.schemaVersion}\0${entryHashInputs.buildConfigJson}\0${entryHashInputs.projectFingerprint}`
    );

    const emitter = getEmitter(schemaName);
    if (!emitter) {
      throw inputError(
        'CANON_EMITTER_NOT_FOUND',
        `No emitter registered for schema "${schemaName}"`,
        `Register an emitter in lib/canon-build/emitters/index.js.`,
      );
    }

    const lane = resolveLane(entry, schemaName, config.schema_to_lane);
    const emitCtx = {
      trigger,
      lane,
      generatedFrom,
      entryHash,
    };

    let rendered;
    const cacheKeyDir = join(cacheDir, entryHash);
    const cacheHit = !effectiveFull && !noCache && existsSync(cacheKeyDir);

    if (cacheHit) {
      rendered = await readCachedRender(cacheKeyDir);
      cached++;
    } else {
      rendered = emitter(entry, emitCtx);
      rebuilt++;
      if (!noCache && !dryRun) {
        await writeCachedRender(cacheKeyDir, rendered);
      }
    }

    // Enforce context length
    const maxLines = resolveContextMaxLines(rendered.schemaKind, config.context_limits);
    const failure = checkContextLength(rendered.context, maxLines, id, rendered.schemaKind);
    if (failure) contextLimitFailures.push(failure);

    // Resolve asset_path — look up visual.reference_plate_uri, then top-level
    const refPath = entry.frontmatter.visual?.reference_plate_uri
      || entry.frontmatter.reference_plate_uri
      || null;

    // Build the row
    const row = canonEntryToRow({
      entry: entry.frontmatter,
      schemaKind: rendered.schemaKind,
      assetPath: refPath,
      lane,
      caption: rendered.caption,
      trigger,
      partition: 'train',
      entryHash,
      generatedFrom,
    });
    rows.push(row);

    // Stash the rendered prompt + context on the entry for later writing
    entry._rendered = rendered;
    entry._row = row;
    entry._lane = lane;
    entry._id = id;
    entry._entryHash = entryHash;
  }

  if (contextLimitFailures.length) {
    const summary = contextLimitFailures
      .map((f) => `  ${f.schemaKind}:${f.entityId} → ${f.lineCount} lines (cap ${f.maxLines})`)
      .join('\n');
    throw runtimeError(
      'CANON_CONTEXT_LENGTH_EXCEEDED',
      `${contextLimitFailures.length} context file(s) exceeded their line cap:\n${summary}`,
      'Trim narrative fields or raise the per-schema context_limits.<schema>.max_lines in canon-build/config.json.',
    );
  }

  if (dryRun) {
    return {
      dryRun: true,
      generated_from: generatedFrom,
      entities_total: entries.length,
      entities_cached: cached,
      entities_rebuilt: rebuilt,
      rows: rows.length,
      output_dir: outputDir,
    };
  }

  // Write to staging, then atomic rename.
  await rm(stagingDir, { recursive: true, force: true });
  await mkdir(join(stagingDir, 'dataset'), { recursive: true });
  await mkdir(join(stagingDir, 'prompts'), { recursive: true });
  await mkdir(join(stagingDir, 'context'), { recursive: true });

  // Write prompts + context
  for (const { entry } of entries) {
    const r = entry._rendered;
    const id = entry._id;
    await writeFile(join(stagingDir, 'prompts', `${id}.j2`), r.prompt, 'utf-8');
    await writeFile(join(stagingDir, 'context', `${id}.md`), r.context, 'utf-8');
  }

  // Write dataset.jsonl (all + per-lane-per-partition)
  const allLines = rows.map((r) => serializeRow(r)).join('\n') + (rows.length ? '\n' : '');
  await writeFile(join(stagingDir, 'dataset', 'all.jsonl'), allLines, 'utf-8');

  // Group by (lane × partition)
  const byLaneAndPartition = {};
  for (const row of rows) {
    const key = `${row.lane}-${row.partition}`;
    if (!byLaneAndPartition[key]) byLaneAndPartition[key] = [];
    byLaneAndPartition[key].push(row);
  }
  for (const [key, laneRows] of Object.entries(byLaneAndPartition)) {
    const content = laneRows.map((r) => serializeRow(r)).join('\n') + '\n';
    await writeFile(join(stagingDir, 'dataset', `${key}.jsonl`), content, 'utf-8');
  }

  // Freeze drift pass — stamp frozen_entries_hashes (D1 witness chain).
  // For every entry with a non-auto freeze status, compute the watch-hash
  // of its currently-watched fields. Drift is computed by later builds or
  // the `sdlab canon drift` command by diffing their hash against this.
  const frozenEntriesHashes = {};
  const drift = [];
  const priorManifest = await loadPreviousManifest(projectRoot, outputDir);
  for (const { entry, schemaName, id } of entries) {
    const status = readFreezeStatus(entry.frontmatter);
    if (status === 'auto') continue;
    const watchFields = resolveWatchFields(entry.frontmatter, schemaName, config);
    const watchHash = computeWatchHash(
      entry.frontmatter,
      watchFields,
      schemas[schemaName].version,
    );
    frozenEntriesHashes[id] = {
      status,
      watch_hash: watchHash,
      watch_fields: watchFields,
      locked_at_build: entry.frontmatter.freeze?.locked_at_build || null,
    };
    // Compute drift against prior build's stamp, if any.
    const priorHash = priorManifest?.frozen_entries_hashes?.[id]?.watch_hash;
    if (priorHash && priorHash !== watchHash) {
      drift.push({
        entity_id: id,
        schema_kind: schemaName.replace('.schema.json', ''),
        status,
        prior_hash: priorHash,
        current_hash: watchHash,
      });
    }
  }

  // Write manifest
  const manifest = {
    schema_version: BUILD_SCHEMA_VERSION,
    row_schema_version: ROW_SCHEMA_VERSION,
    generated_from: generatedFrom,
    built_at: new Date().toISOString(),
    project_id: config.project_id,
    schema_versions: Object.fromEntries(
      Object.entries(schemas).map(([k, v]) => [k, v.version])
    ),
    build_config_hash: buildConfigHash,
    project_config_fingerprint: projectFingerprint,
    per_entity_hashes: Object.fromEntries(entries.map(({ entry, id }) => [id, entry._entryHash])),
    frozen_entries_hashes: frozenEntriesHashes,
    drift_against_prior: drift,
    stats: {
      entities_total: entries.length,
      entities_cached: cached,
      entities_rebuilt: rebuilt,
      dataset_rows: rows.length,
      frozen_entries: Object.keys(frozenEntriesHashes).length,
      drifted_entries: drift.length,
      schema_change_full_rebuild: schemaChangeTriggersFullRebuild,
    },
  };
  await writeFile(
    join(stagingDir, 'manifest.json'),
    JSON.stringify(manifest, null, 2) + '\n',
    'utf-8'
  );

  // Atomic swap: remove old output, rename staging → output.
  await rm(outputDir, { recursive: true, force: true });
  await rename(stagingDir, outputDir);

  // Update the "latest" schema-version snapshot for change detection next run.
  await writeLatestSchemaVersions(projectRoot, manifest.schema_versions);

  return {
    dryRun: false,
    generated_from: generatedFrom,
    entities_total: entries.length,
    entities_cached: cached,
    entities_rebuilt: rebuilt,
    rows: rows.length,
    output_dir: outputDir,
    frozen_entries: Object.keys(frozenEntriesHashes).length,
    drift: drift,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────

function sha256(s) {
  return createHash('sha256').update(String(s)).digest('hex');
}

async function writeCachedRender(cacheKeyDir, rendered) {
  await mkdir(cacheKeyDir, { recursive: true });
  await writeFile(join(cacheKeyDir, 'meta.json'),
    JSON.stringify({ schemaKind: rendered.schemaKind }, null, 2) + '\n', 'utf-8');
  await writeFile(join(cacheKeyDir, 'caption.txt'), rendered.caption, 'utf-8');
  await writeFile(join(cacheKeyDir, 'prompt.j2'), rendered.prompt, 'utf-8');
  await writeFile(join(cacheKeyDir, 'context.md'), rendered.context, 'utf-8');
}

async function readCachedRender(cacheKeyDir) {
  const meta = JSON.parse(await readFile(join(cacheKeyDir, 'meta.json'), 'utf-8'));
  const [caption, prompt, context] = await Promise.all([
    readFile(join(cacheKeyDir, 'caption.txt'), 'utf-8'),
    readFile(join(cacheKeyDir, 'prompt.j2'), 'utf-8'),
    readFile(join(cacheKeyDir, 'context.md'), 'utf-8'),
  ]);
  return { schemaKind: meta.schemaKind, caption, prompt, context };
}

/**
 * Detect if any schema file's version has changed since the last build.
 * Returns true when a full rebuild is warranted.
 */
async function detectSchemaChange(projectRoot, schemas, explicitFull) {
  if (explicitFull) return false; // --full already forces rebuild; no need to also flag change
  const snapshotPath = join(projectRoot, 'canon-build', '.cache', '_schema-versions.json');
  if (!existsSync(snapshotPath)) return true; // first run = full rebuild
  try {
    const prev = JSON.parse(await readFile(snapshotPath, 'utf-8'));
    for (const [name, info] of Object.entries(schemas)) {
      if (prev[name] !== info.version) return true;
    }
    return false;
  } catch {
    return true; // corrupted snapshot = full rebuild
  }
}

async function writeLatestSchemaVersions(projectRoot, versions) {
  const path = join(projectRoot, 'canon-build', '.cache', '_schema-versions.json');
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, JSON.stringify(versions, null, 2) + '\n', 'utf-8');
}

/**
 * Load the previous build's manifest (if any) so drift can be computed
 * against the most-recent frozen_entries_hashes stamp. Returns null if
 * no prior build exists.
 */
async function loadPreviousManifest(projectRoot, currentOutputDir) {
  const canonBuildDir = join(projectRoot, 'canon-build');
  if (!existsSync(canonBuildDir)) return null;
  let candidates;
  try { candidates = readdirSync(canonBuildDir); } catch { return null; }
  let latest = null;
  let latestTime = 0;
  for (const name of candidates) {
    const full = join(canonBuildDir, name);
    if (full === currentOutputDir) continue;
    if (name.startsWith('.') || name.includes('.tmp')) continue;
    const manifestPath = join(full, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const m = JSON.parse(readFileSync(manifestPath, 'utf-8'));
      const t = new Date(m.built_at || 0).getTime();
      if (t > latestTime) { latestTime = t; latest = m; }
    } catch { /* skip */ }
  }
  return latest;
}

/**
 * Resolve generated_from: git HEAD SHA for the canon_root's repo, or a
 * content-sha fallback computed over all entry contents when canon_root is
 * not under git control (greek-rpg today).
 */
function resolveGeneratedFrom(canonRoot) {
  try {
    const out = execSync('git rev-parse HEAD', {
      cwd: canonRoot,
      stdio: ['ignore', 'pipe', 'ignore'],
      encoding: 'utf-8',
    }).trim();
    if (out && /^[0-9a-f]{7,}$/.test(out)) return out;
  } catch {
    // not a git repo — fall through
  }
  // Fallback: content-sha over the whole canon tree (stable, determinstic).
  return `content-sha:${contentShaOfTree(canonRoot).slice(0, 16)}`;
}

function contentShaOfTree(root) {
  const hash = createHash('sha256');
  if (!existsSync(root)) return hash.digest('hex');
  walkFiles(root, (absPath) => {
    hash.update(relative(root, absPath).replace(/\\/g, '/'));
    hash.update('\0');
    try { hash.update(readFileSync(absPath)); } catch {}
    hash.update('\0');
  });
  return hash.digest('hex');
}

function walkFiles(dir, cb) {
  let entries;
  try { entries = readdirSync(dir); } catch { return; }
  entries.sort();
  for (const name of entries) {
    const full = join(dir, name);
    let st;
    try { st = statSync(full); } catch { continue; }
    if (st.isDirectory()) walkFiles(full, cb);
    else if (st.isFile()) cb(full);
  }
}
