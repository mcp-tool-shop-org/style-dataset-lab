#!/usr/bin/env node

/**
 * asset-ingest.js — `sdlab asset ingest <dir>`: register a provenance-carrying
 * asset export (asset-source.json + renders + masks + channels) into a
 * project, through the full contract of lib/asset-source.js and the
 * receiving-dock gates of lib/asset-ingest.js.
 *
 * The manifest-driven, gated sibling of `sdlab ingest` (which takes bare
 * images with no contract). See docs/asset-lane-design.md.
 *
 * PATH NOTE (deliberate deviation from resolveSafeProjectPath): the export
 * directory is allowed to live OUTSIDE the sdlab workspace — asset exports
 * live where the asset pipeline puts them (e.g. a training area on another
 * part of the disk). The source is READ-ONLY here; every path the manifest
 * references is contained to the export directory by lib/asset-source.js,
 * and every WRITE stays inside the project. Containment where it protects,
 * reach where the user explicitly points.
 *
 * Usage:
 *   sdlab asset ingest <dir> --project <name>
 *   sdlab asset ingest <dir> --project <name> --dry-run
 *   sdlab asset ingest <dir> --project <name> --json
 */

import { resolve } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { ingestAssetSource } from '../lib/asset-ingest.js';
import { result } from '../lib/log.js';

const USAGE = `Usage: sdlab asset ingest <dir> --project <name> [--dry-run] [--json]

Validate an asset export's asset-source.json (schema, containment, encoding
proofs, categorical palette proofs, the acceptance verdict) and register its
renders as candidate records. Refuses loudly on any contract violation —
nothing registers on a bad manifest.

Positional:
  dir                  Asset export directory containing asset-source.json.
                       May live outside the workspace (read-only source).

Flags:
  --project <name>     Project to register into
  --dry-run            Validate + run gates + report the plan; write nothing
  --json               Emit the result as JSON on stdout

What lands on success:
  records/<asset>__<render>.json     uncurated records (judgment: null),
                                     provenance.source: "asset", hashes,
                                     camera/facing, gate measurements
  outputs/candidates/<asset>__<render>.png
  assets/<asset>/                    manifest copy, silhouettes, channel
                                     instances, pairs, ingest-receipt.json
                                     (the receipt lists every written path —
                                     it is the undo checklist)

Next steps after ingesting:
  1. Review: sdlab curate <id> approved/rejected "explanation"
  2. Bind:   sdlab bind --project <name>`;

export async function run(argv = process.argv.slice(2)) {
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(USAGE);
    return;
  }

  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      'dry-run': { type: 'boolean', default: false },
      json: { type: 'boolean', default: false },
    },
    deprecated: { game: 'project' },
  });

  const dirArg = positionals[0];
  if (!dirArg) {
    throw inputError('INPUT_MISSING_ARGS', 'An asset export directory is required.', USAGE);
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const dryRun = flags['dry-run'] || flags.dryRun;
  const sourceDir = resolve(dirArg);

  if (!flags.json) {
    console.log(`\x1b[1msdlab asset ingest\x1b[0m — ${projectName}`);
    console.log(`  Source: ${sourceDir}`);
    if (dryRun) console.log(`  Mode:   DRY RUN (no files written)`);
    console.log('');
  }

  const report = await ingestAssetSource(projectRoot, sourceDir, { dryRun });

  if (flags.json) {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  if (report.alreadyIngested) {
    console.log(`  ○ Asset "${report.assetId}" is already ingested (same manifest hash) — nothing to do.`);
    console.log(`    Receipt: ${report.receiptPath}`);
    return;
  }

  console.log(`  \x1b[32m✓\x1b[0m Registered: ${report.created.length} render record(s)${dryRun ? ' (dry run — nothing written)' : ''}`);
  for (const id of report.created) {
    const gate = report.gates[id];
    console.log(`    ✓ ${id}  (off-palette ${gate.offpalette_pct}%${gate.withdrawn_pct_bound ? ' [diagnostic]' : ''}, blob ${gate.largest_blob_px}px)`);
  }

  if (report.skipped.length > 0) {
    console.log(`  Skipped: ${report.skipped.length} (already registered by this ingest)`);
    for (const id of report.skipped) console.log(`    ○ ${id}`);
  }

  if (report.rejected.length > 0) {
    console.log(`  \x1b[33m⚠\x1b[0m Rejected by the asset's own palette gate: ${report.rejected.length}`);
    for (const r of report.rejected) {
      const d = r.gate.dominant;
      console.log(`    ✗ ${r.render_id}: blob ${r.gate.largest_blob_px}px (limit ${'≤'} manifest gate)` +
        (d ? ` — dominant hue ${d.hue_lo}-${d.hue_hi}°, median C* ${d.median_chroma}, rgb(${d.median_rgb})` : ''));
    }
  }

  // Provenance notices — what the manifest left undeclared. Not failures:
  // the ingest succeeded. These are facts about the training data that only
  // the manifest could have supplied, printed so they are not discovered
  // later by a split or a training run that quietly assumed them.
  if (report.notices?.length > 0) {
    const gaps = report.notices.filter((n) => n.kind === 'gap');
    const infos = report.notices.filter((n) => n.kind !== 'gap');
    console.log('');
    console.log(`  \x1b[36mProvenance notices\x1b[0m (${report.notices.length}) — the ingest SUCCEEDED; these describe the records it created:`);
    if (gaps.length > 0) {
      console.log(`  \x1b[33m  gaps\x1b[0m (${gaps.length}) — declarations the manifest did not make; closing them is export-side work:`);
      for (const n of gaps) console.log(`    • [${n.code}] ${n.message}`);
    }
    if (infos.length > 0) {
      console.log(`    info (${infos.length}) — declarations it DID make that change how these records read:`);
      for (const n of infos) console.log(`    • [${n.code}] ${n.message}`);
    }
  }

  if (!dryRun && report.created.length > 0) {
    console.log('');
    result(`Receipt: ${report.receiptPath}`);
    console.log('');
    console.log('  Next steps:');
    console.log('    1. Review: sdlab curate <id> approved/rejected "explanation"');
    console.log('    2. Bind:   sdlab bind --project ' + projectName);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('asset-ingest.js') || process.argv[1].endsWith('asset-ingest'))) {
  run().catch(handleCliError);
}
