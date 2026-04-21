#!/usr/bin/env node

/**
 * reingest-selected.js — Re-ingest selected outputs as candidate records.
 *
 * Usage:
 *   sdlab reingest selected --selection selection_2026-04-16_001 --project star-freight
 *   sdlab reingest selected --selection selection_2026-04-16_001 --dry-run
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { reingestSelection } from '../lib/reingest-selected.js';
import { info } from '../lib/log.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      selection: { type: 'string' },
      'dry-run': { type: 'boolean' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.selection) {
    console.log('Usage: sdlab reingest selected --selection <id> [--project <name>]');
    console.log('');
    console.log('Options:');
    console.log('  --selection <id>   Selection to re-ingest (required)');
    console.log('  --dry-run          Preview without writing records');
    console.log('  --json             Output as JSON');
    return;
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const dryRun = flags['dry-run'] || false;

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m reingest selected`);
  console.log(`  Selection: ${flags.selection}`);
  console.log(`  Project: ${projectName}`);
  if (dryRun) console.log('  ⚠ DRY RUN');
  console.log('');

  const { created, skipped } = await reingestSelection({
    projectRoot,
    projectId: projectName,
    selectionId: flags.selection,
    dryRun,
  });

  if (flags.json) {
    console.log(JSON.stringify({ created, skipped }, null, 2));
    return;
  }

  if (created.length > 0) {
    console.log(`  Created ${created.length} candidate record(s):`);
    for (const id of created) {
      console.log(`    ✓ ${id}`);
    }
  }

  if (skipped.length > 0) {
    console.log(`  Skipped ${skipped.length} (already exist):`);
    for (const id of skipped) {
      console.log(`    ○ ${id}`);
    }
  }

  console.log('');
  if (!dryRun && created.length > 0) {
    info('Records staged for review. Use sdlab curate to approve/reject.');
    info(`Images copied to inbox/generated/`);
  }
}
