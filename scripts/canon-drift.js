/**
 * `sdlab canon drift` — drift report (D7 command).
 *
 * For every frozen or on-canon-change entry, computes the current watch-hash
 * and compares against the hash stamped in the latest canon-build manifest.
 * Surfaces:
 *   - Frozen entries whose current projection drifts from their witness.
 *   - on-canon-change entries where the watch-fields have changed since freeze.
 *   - Overrides since a given build hash (or since the last clean build).
 */

import { parseArgs } from 'node:util';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { loadBuildConfig } from '../lib/canon-build/load-config.js';
import { loadCanonEntriesInDir } from '../lib/canon-build/load-entry.js';
import { loadSchema } from '../lib/canon-build/load-schema.js';
import { readFreezeStatus, resolveWatchFields, computeWatchHash } from '../lib/freeze-stamp.js';
import { readEventsSince } from '../lib/freeze-events.js';
import { inputError } from '../lib/errors.js';

export async function run(argv) {
  const parsed = parseArgs({
    args: argv,
    options: {
      project: { type: 'string' },
      game:    { type: 'string' },
      since:   { type: 'string' },
      json:    { type: 'boolean', default: false },
    },
    allowPositionals: true,
    strict: false,
  });

  const projectName = parsed.values.project || parsed.values.game;
  if (!projectName) throw inputError('INPUT_MISSING_FLAG', '--project required');

  const projectRoot = join(process.cwd(), 'projects', projectName);
  const config = await loadBuildConfig(join(projectRoot, 'canon-build', 'config.json'), projectRoot);

  // Load latest build manifest for the stamped watch-hashes
  const latestManifest = await findLatestBuildManifest(projectRoot);

  // Load schemas for version info
  const schemas = {};
  for (const schemaName of Object.keys(config.entity_dirs)) {
    const path = join(config.schema_dir, schemaName);
    schemas[schemaName] = await loadSchema(path);
  }

  // Walk entries, compute drift
  const drifted = [];
  const cleanFrozen = [];
  let totalEntries = 0;
  let autoCount = 0;

  for (const [schemaName, subdir] of Object.entries(config.entity_dirs)) {
    const dir = join(config.canon_root, subdir);
    const entries = await loadCanonEntriesInDir(dir);
    for (const entry of entries) {
      totalEntries++;
      const status = readFreezeStatus(entry.frontmatter);
      if (status === 'auto') { autoCount++; continue; }

      const watchFields = resolveWatchFields(entry.frontmatter, schemaName, config);
      const currentHash = computeWatchHash(
        entry.frontmatter,
        watchFields,
        schemas[schemaName].version,
      );

      // Look up stamped hash from latest manifest. The manifest stores a
      // richer stamp object (status / watch_hash / watch_fields /
      // locked_at_build); the drift comparison only needs `.watch_hash`.
      const entityId = entry.frontmatter.id;
      const stamp = latestManifest?.frozen_entries_hashes?.[entityId] || null;
      const stampedHash = stamp?.watch_hash || null;

      if (stampedHash && stampedHash !== currentHash) {
        drifted.push({
          entity_id: entityId,
          schema_kind: schemaName.replace('.schema.json', ''),
          status,
          locked_at_build: stamp?.locked_at_build || entry.frontmatter.freeze?.locked_at_build || null,
          witness_hash: stampedHash,
          current_hash: currentHash,
          watch_fields: watchFields,
        });
      } else if (stampedHash) {
        cleanFrozen.push({
          entity_id: entityId,
          status,
          witness_hash: stampedHash,
        });
      } else {
        // Entry is frozen now but was not in the last build manifest (e.g.
        // newly frozen since). Flag as "no witness yet" rather than mis-
        // classifying as either drifted or clean.
        cleanFrozen.push({
          entity_id: entityId,
          status,
          witness_hash: null,
          note: 'no witness in latest build — rebuild to stamp',
        });
      }
    }
  }

  // Events since a reference build hash
  const sinceHash = parsed.values.since || latestManifest?.generated_from || null;
  const eventsSince = sinceHash
    ? await readEventsSince(projectRoot, sinceHash)
    : [];

  const report = {
    project_id: config.project_id,
    latest_build: latestManifest?.generated_from || null,
    latest_built_at: latestManifest?.built_at || null,
    entities_total: totalEntries,
    entities_auto: autoCount,
    entities_frozen_clean: cleanFrozen.length,
    entities_drifted: drifted.length,
    drifted,
    overrides_since: eventsSince.filter((e) => e.type !== 'freeze'),
  };

  if (parsed.values.json) {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  renderHumanReport(report);
}

function renderHumanReport(r) {
  console.log(`Drift report for ${r.project_id}`);
  console.log(`  latest build:    ${r.latest_build || '(no build output found)'}`);
  console.log(`  latest built_at: ${r.latest_built_at || '(unknown)'}`);
  console.log('');
  console.log(`  auto entries:            ${r.entities_auto}`);
  console.log(`  frozen entries (clean):  ${r.entities_frozen_clean}`);
  console.log(`  frozen entries (drift):  ${r.entities_drifted}`);
  console.log('');

  if (r.drifted.length > 0) {
    console.log('Drifted frozen entries:');
    for (const d of r.drifted) {
      console.log(`  ${d.schema_kind}:${d.entity_id} (${d.status})`);
      console.log(`    witness hash:  ${d.witness_hash.slice(0, 16)}...`);
      console.log(`    current hash:  ${d.current_hash.slice(0, 16)}...`);
      console.log(`    watch fields:  ${d.watch_fields.join(', ') || '(none)'}`);
    }
    console.log('');
  } else if (r.entities_frozen_clean > 0) {
    console.log('No drift detected on frozen entries.');
    console.log('');
  }

  if (r.overrides_since.length > 0) {
    console.log(`Overrides since last build (${r.overrides_since.length}):`);
    for (const e of r.overrides_since) {
      console.log(`  ${e.type.padEnd(10)} ${e.entity_id} by ${e.by} — ${e.reason}`);
    }
  }
}

async function findLatestBuildManifest(projectRoot) {
  const canonBuildDir = join(projectRoot, 'canon-build');
  if (!existsSync(canonBuildDir)) return null;
  const entries = await readdir(canonBuildDir, { withFileTypes: true });
  const candidates = entries
    .filter((e) => e.isDirectory() && !e.name.startsWith('.') && !e.name.includes('.tmp'))
    .map((e) => e.name);

  let latest = null;
  let latestTime = 0;
  for (const name of candidates) {
    const manifestPath = join(canonBuildDir, name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const manifest = JSON.parse(await readFile(manifestPath, 'utf-8'));
      const built = new Date(manifest.built_at || 0).getTime();
      if (built > latestTime) {
        latestTime = built;
        latest = manifest;
      }
    } catch {
      continue;
    }
  }
  return latest;
}
