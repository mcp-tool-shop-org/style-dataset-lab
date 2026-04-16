#!/usr/bin/env node

/**
 * reingest.js — Re-ingest generated outputs as new project records.
 *
 * Usage:
 *   sdlab reingest generated --source <dir> --manifest <id> [--dry-run] [--project <name>]
 *   sdlab reingest audit [--project <name>]
 */

import { join } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { reingestGenerated, auditReingest } from '../lib/reingest.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = argv.find(a => !a.startsWith('--')) || 'audit';
  const args = argv.filter(a => a !== subcommand);

  if (subcommand === 'generated') {
    const sourceIdx = args.indexOf('--source');
    if (sourceIdx < 0) throw new Error('--source <dir> is required (directory of generated images)');
    const sourcePath = args[sourceIdx + 1];

    const manifestIdx = args.indexOf('--manifest');
    if (manifestIdx < 0) throw new Error('--manifest <id> is required (training manifest that produced the outputs)');
    const manifestId = args[manifestIdx + 1];

    const dryRun = args.includes('--dry-run');

    console.log(`\x1b[1msdlab reingest generated\x1b[0m — ${projectName}`);
    console.log(`  Source:   ${sourcePath}`);
    console.log(`  Manifest: ${manifestId}`);
    if (dryRun) console.log(`  Mode:     DRY RUN (no records written)`);
    console.log('');

    const result = await reingestGenerated(projectRoot, sourcePath, manifestId, { dryRun });

    console.log(`  \x1b[32m✓\x1b[0m Created: ${result.created} records`);
    if (result.skipped > 0) {
      console.log(`  Skipped: ${result.skipped} (already exist)`);
    }
    if (result.created > 0) {
      console.log('');
      console.log('  Next steps:');
      console.log('    1. Review: sdlab curate <id> approved/rejected "explanation"');
      console.log('    2. Bind:   sdlab bind --project ' + projectName);
      console.log('    3. Then eligible for future snapshots');
    }

  } else if (subcommand === 'selected') {
    // Delegate to reingest-selected.js
    const { run: runSelected } = await import('./reingest-selected.js');
    await runSelected(args);
    return;

  } else if (subcommand === 'audit') {
    console.log(`\x1b[1msdlab reingest audit\x1b[0m — ${projectName}\n`);

    const result = await auditReingest(projectRoot);

    if (result.total === 0) {
      console.log('  No re-ingested records found (gen_* prefix).');
      return;
    }

    console.log(`  Re-ingested records: ${result.total}`);
    console.log(`  Reviewed:            ${result.reviewed}`);
    console.log(`  Unreviewed:          ${result.unreviewed}`);
    console.log(`  Canon-bound:         ${result.bound}`);
    console.log(`  Unbound:             ${result.unbound}`);

    if (result.unreviewed > 0) {
      console.log(`\n  \x1b[33m⚠\x1b[0m ${result.unreviewed} records awaiting review`);
    }
    if (result.unbound > 0) {
      console.log(`  \x1b[33m⚠\x1b[0m ${result.unbound} reviewed records not yet canon-bound`);
    }
    if (result.unreviewed === 0 && result.unbound === 0) {
      console.log(`\n  \x1b[32m✓\x1b[0m All re-ingested records are reviewed and canon-bound`);
    }

  } else {
    throw new Error(`Unknown subcommand: ${subcommand}. Use: generated, selected, audit`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('reingest.js') || process.argv[1].endsWith('reingest'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
