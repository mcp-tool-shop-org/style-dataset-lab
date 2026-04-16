#!/usr/bin/env node

/**
 * export.js — Build and list versioned export packages.
 *
 * Usage:
 *   sdlab export build [--snapshot <id>] [--split <id>] [--profile <name>] [--copy] [--project <name>]
 *   sdlab export list [--project <name>]
 */

import { join } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { listSnapshots } from '../lib/snapshot.js';
import { listSplits } from '../lib/split.js';
import { buildExport, listExports, loadExport } from '../lib/export.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = argv.find(a => !a.startsWith('--') && a !== 'true') || 'list';
  const args = argv.filter(a => a !== subcommand);

  if (subcommand === 'build') {
    // Find snapshot
    let snapshotId;
    const snapIdx = args.indexOf('--snapshot');
    if (snapIdx >= 0) {
      snapshotId = args[snapIdx + 1];
    } else {
      const snapshots = await listSnapshots(projectRoot);
      if (snapshots.length === 0) throw new Error('No snapshots found. Run: sdlab snapshot create');
      snapshotId = snapshots[snapshots.length - 1].id;
    }

    // Find split
    let splitId;
    const splitIdx = args.indexOf('--split');
    if (splitIdx >= 0) {
      splitId = args[splitIdx + 1];
    } else {
      const splits = await listSplits(projectRoot);
      if (splits.length === 0) throw new Error('No splits found. Run: sdlab split build');
      splitId = splits[splits.length - 1].id;
    }

    const profileIdx = args.indexOf('--profile');
    const profileId = profileIdx >= 0 ? args[profileIdx + 1] : null;
    const copy = args.includes('--copy');

    console.log(`\x1b[1msdlab export build\x1b[0m — ${projectName}`);
    console.log(`  Snapshot: ${snapshotId}`);
    console.log(`  Split:    ${splitId}`);
    console.log(`  Profile:  ${profileId || 'canonical-package (built-in)'}`);
    console.log(`  Images:   ${copy ? 'copy' : 'symlink'}`);
    console.log('');

    const result = await buildExport(projectRoot, snapshotId, splitId, { profileId, copy });

    console.log(`  \x1b[32m✓\x1b[0m Export: ${result.exportId}`);
    console.log(`  Records: ${result.recordCount}`);
    console.log(`  Images:  ${result.imageCount}`);

  } else if (subcommand === 'list') {
    const exports = await listExports(projectRoot);
    if (exports.length === 0) {
      console.log('No exports found. Run: sdlab export build');
      return;
    }
    console.log(`\x1b[1mExports\x1b[0m — ${projectName}\n`);
    for (const e of exports) {
      console.log(`  ${e.id}  snap=${e.snapshot_id}  split=${e.split_id}  records=${e.records}  images=${e.images}  ${e.created_at}`);
    }

  } else {
    throw new Error(`Unknown subcommand: ${subcommand}. Use: build, list`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('export.js') || process.argv[1].endsWith('export'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
