#!/usr/bin/env node

/**
 * snapshot.js — Create, list, show, and diff dataset snapshots.
 *
 * Usage:
 *   sdlab snapshot create [--profile <name>] [--project <name>]
 *   sdlab snapshot list [--project <name>]
 *   sdlab snapshot show <snapshot-id> [--project <name>]
 *   sdlab snapshot diff <id-a> <id-b> [--project <name>]
 */

import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { loadSelectionProfile } from '../lib/config.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { createSnapshot, loadSnapshot, listSnapshots, diffSnapshots } from '../lib/snapshot.js';
import { categorizeExclusions } from '../lib/eligibility.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      profile: { type: 'string' },
      'dry-run': { type: 'boolean', default: false },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = positionals[0] || 'list';
  const dryRun = flags['dry-run'] || flags.dryRun;

  if (subcommand === 'create') {
    const profile = loadSelectionProfile(projectRoot, flags.profile);

    console.log(`\x1b[1msdlab snapshot create\x1b[0m — ${projectName}`);
    console.log(`  Profile: ${flags.profile || 'training-default (built-in)'}`);
    if (dryRun) console.log('  Mode: DRY RUN (no files written)');
    console.log('');

    const result = await createSnapshot(projectRoot, profile, { dryRun });

    console.log(`  \x1b[32m✓\x1b[0m Snapshot: ${result.snapshotId}`);
    console.log(`  Included: ${result.included}`);
    console.log(`  Excluded: ${result.excluded}`);

    if (!dryRun) {
      const summary = JSON.parse(
        await readFile(join(projectRoot, 'snapshots', result.snapshotId, 'summary.json'), 'utf-8')
      );
      console.log('\n  Lane distribution:');
      for (const [lane, count] of Object.entries(summary.lane_distribution).sort((a, b) => b[1] - a[1])) {
        console.log(`    ${lane}: ${count}`);
      }
      console.log('\n  Faction distribution:');
      for (const [f, c] of Object.entries(summary.faction_distribution).sort((a, b) => b[1] - a[1])) {
        console.log(`    ${f}: ${c}`);
      }

      const excludedRaw = await readFile(
        join(projectRoot, 'snapshots', result.snapshotId, 'excluded.jsonl'), 'utf-8'
      );
      const excluded = excludedRaw.trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
      const categories = categorizeExclusions(excluded);
      console.log('\n  Exclusion reasons:');
      for (const [cat, count] of Object.entries(categories)) {
        if (count > 0) console.log(`    ${cat}: ${count}`);
      }
    }

  } else if (subcommand === 'list') {
    const snapshots = await listSnapshots(projectRoot);
    if (snapshots.length === 0) {
      console.log('No snapshots found. Run: sdlab snapshot create');
      return;
    }
    console.log(`\x1b[1mSnapshots\x1b[0m — ${projectName}\n`);
    for (const s of snapshots) {
      console.log(`  ${s.id}  included=${s.included}  excluded=${s.excluded}  fp=${s.fingerprint}  ${s.created_at}`);
    }

  } else if (subcommand === 'show') {
    const snapshotId = positionals[1] || positionals.find(a => a.startsWith('snap-'));
    if (!snapshotId) throw inputError('INPUT_MISSING_ARGS', 'Usage: sdlab snapshot show <snapshot-id>');

    const manifest = await loadSnapshot(projectRoot, snapshotId);
    console.log(`\x1b[1mSnapshot\x1b[0m — ${snapshotId}\n`);
    console.log(`  Created: ${manifest.created_at}`);
    console.log(`  Project: ${manifest.project_name}`);
    console.log(`  Frozen:  ${manifest.frozen}`);
    console.log(`  Records: ${manifest.counts.total_records}`);
    console.log(`  Included: ${manifest.counts.included}`);
    console.log(`  Excluded: ${manifest.counts.excluded}`);
    console.log(`  Config fingerprint: ${manifest.config_fingerprint}`);
    console.log('');
    console.log('  Selection profile:');
    for (const [k, v] of Object.entries(manifest.selection_profile)) {
      console.log(`    ${k}: ${JSON.stringify(v)}`);
    }

  } else if (subcommand === 'diff') {
    const snapIds = positionals.slice(1).filter(a => a.startsWith('snap-'));
    if (snapIds.length < 2) throw inputError('INPUT_MISSING_ARGS', 'Usage: sdlab snapshot diff <id-a> <id-b>');

    const diff = await diffSnapshots(projectRoot, snapIds[0], snapIds[1]);
    console.log(`\x1b[1mSnapshot diff\x1b[0m — ${snapIds[0]} vs ${snapIds[1]}\n`);
    console.log(`  ${snapIds[0]}: ${diff.countA} records`);
    console.log(`  ${snapIds[1]}: ${diff.countB} records`);
    console.log(`  Shared: ${diff.shared.length}`);
    console.log(`  Added in ${snapIds[1]}: ${diff.added.length}`);
    console.log(`  Removed from ${snapIds[0]}: ${diff.removed.length}`);

    if (diff.added.length > 0 && diff.added.length <= 20) {
      console.log('\n  Added:');
      for (const id of diff.added) console.log(`    + ${id}`);
    }
    if (diff.removed.length > 0 && diff.removed.length <= 20) {
      console.log('\n  Removed:');
      for (const id of diff.removed) console.log(`    - ${id}`);
    }

  } else {
    throw inputError('INPUT_BAD_SUBCOMMAND', `Unknown subcommand: ${subcommand}. Use: create, list, show, diff`);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('snapshot.js') || process.argv[1].endsWith('snapshot'))) {
  run().catch(handleCliError);
}
