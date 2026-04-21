#!/usr/bin/env node

/**
 * export.js — Build and list versioned export packages.
 *
 * Usage:
 *   sdlab export build [--snapshot <id>] [--split <id>] [--profile <name>] [--copy] [--project <name>]
 *   sdlab export list [--project <name>]
 */

import { join } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { listSnapshots } from '../lib/snapshot.js';
import { listSplits } from '../lib/split.js';
import { buildExport, listExports } from '../lib/export.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      snapshot: { type: 'string' },
      split: { type: 'string' },
      profile: { type: 'string' },
      copy: { type: 'boolean', default: false },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = positionals[0] || 'list';

  if (subcommand === 'build') {
    let snapshotId = flags.snapshot;
    if (!snapshotId) {
      const snapshots = await listSnapshots(projectRoot);
      if (snapshots.length === 0) throw inputError('INPUT_NO_SNAPSHOT', 'No snapshots found. Run: sdlab snapshot create');
      snapshotId = snapshots[snapshots.length - 1].id;
    }

    let splitId = flags.split;
    if (!splitId) {
      const splits = await listSplits(projectRoot);
      if (splits.length === 0) throw inputError('INPUT_NO_SPLIT', 'No splits found. Run: sdlab split build');
      splitId = splits[splits.length - 1].id;
    }

    console.log(`\x1b[1msdlab export build\x1b[0m — ${projectName}`);
    console.log(`  Snapshot: ${snapshotId}`);
    console.log(`  Split:    ${splitId}`);
    console.log(`  Profile:  ${flags.profile || 'canonical-package (built-in)'}`);
    console.log(`  Images:   ${flags.copy ? 'copy' : 'symlink'}`);
    console.log('');

    const result = await buildExport(projectRoot, snapshotId, splitId, { profileId: flags.profile, copy: flags.copy });

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
    throw inputError('INPUT_BAD_SUBCOMMAND', `Unknown subcommand: ${subcommand}. Use: build, list`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('export.js') || process.argv[1].endsWith('export'))) {
  run().catch(handleCliError);
}
