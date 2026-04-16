#!/usr/bin/env node

/**
 * card.js — Generate dataset cards.
 *
 * Usage:
 *   sdlab card generate --snapshot <id> --split <id> [--project <name>]
 */

import { join } from 'node:path';
import { writeFile } from 'node:fs/promises';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { listSnapshots } from '../lib/snapshot.js';
import { listSplits } from '../lib/split.js';
import { generateCard } from '../lib/card.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = argv.find(a => !a.startsWith('--')) || 'generate';
  const args = argv.filter(a => a !== subcommand);

  if (subcommand === 'generate') {
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

    console.log(`\x1b[1msdlab card generate\x1b[0m — ${projectName}`);
    console.log(`  Snapshot: ${snapshotId}`);
    console.log(`  Split:    ${splitId}`);
    console.log('');

    const { markdown, json } = await generateCard(projectRoot, snapshotId, splitId);

    // Write to project root
    const mdPath = join(projectRoot, 'dataset-card.md');
    const jsonPath = join(projectRoot, 'dataset-card.json');
    await writeFile(mdPath, markdown);
    await writeFile(jsonPath, JSON.stringify(json, null, 2) + '\n');

    console.log(`  \x1b[32m✓\x1b[0m dataset-card.md`);
    console.log(`  \x1b[32m✓\x1b[0m dataset-card.json`);

  } else {
    throw new Error(`Unknown subcommand: ${subcommand}. Use: generate`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('card.js') || process.argv[1].endsWith('card'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
