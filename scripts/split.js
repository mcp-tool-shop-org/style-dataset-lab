#!/usr/bin/env node

/**
 * split.js — Build, show, and audit dataset splits.
 *
 * Usage:
 *   sdlab split build [--snapshot <id>] [--profile <name>] [--project <name>]
 *   sdlab split list [--project <name>]
 *   sdlab split show <split-id> [--project <name>]
 *   sdlab split audit <split-id> [--project <name>]
 */

import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { loadSplitProfile } from '../lib/config.js';
import { listSnapshots } from '../lib/snapshot.js';
import { createSplit, loadSplit, loadSplitAudit, listSplits } from '../lib/split.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = argv.find(a => !a.startsWith('--')) || 'list';
  const args = argv.filter(a => a !== subcommand);

  if (subcommand === 'build') {
    // Find snapshot ID
    let snapshotId;
    const snapIdx = args.indexOf('--snapshot');
    if (snapIdx >= 0) {
      snapshotId = args[snapIdx + 1];
    } else {
      // Use latest snapshot
      const snapshots = await listSnapshots(projectRoot);
      if (snapshots.length === 0) {
        throw new Error('No snapshots found. Run: sdlab snapshot create');
      }
      snapshotId = snapshots[snapshots.length - 1].id;
    }

    const profileIdx = args.indexOf('--profile');
    const profileId = profileIdx >= 0 ? args[profileIdx + 1] : null;
    const profile = loadSplitProfile(projectRoot, profileId);

    console.log(`\x1b[1msdlab split build\x1b[0m — ${projectName}`);
    console.log(`  Snapshot: ${snapshotId}`);
    console.log(`  Profile:  ${profileId || 'balanced-default (built-in)'}`);
    console.log(`  Strategy: ${profile.strategy}`);
    console.log(`  Ratios:   ${profile.train_ratio}/${profile.val_ratio}/${profile.test_ratio}`);
    console.log(`  Seed:     ${profile.seed}`);
    console.log('');

    const result = await createSplit(projectRoot, snapshotId, profile);

    console.log(`  \x1b[32m✓\x1b[0m Split: ${result.splitId}`);
    console.log(`  Train: ${result.train}`);
    console.log(`  Val:   ${result.val}`);
    console.log(`  Test:  ${result.test}`);

    // Show audit summary
    const audit = await loadSplitAudit(projectRoot, result.splitId);
    console.log('');
    if (audit.leakage_check.passed) {
      console.log(`  \x1b[32m✓\x1b[0m No subject leakage detected`);
    } else {
      console.log(`  \x1b[31m✗\x1b[0m Subject leakage detected:`);
      for (const issue of audit.leakage_check.issues) {
        console.log(`    family="${issue.family}" (${issue.record_count} records) → ${issue.leaked_to.join(', ')}`);
      }
    }

    console.log(`  Families: ${audit.family_count} (train=${audit.families_per_split.train}, val=${audit.families_per_split.val}, test=${audit.families_per_split.test})`);

  } else if (subcommand === 'list') {
    const splits = await listSplits(projectRoot);
    if (splits.length === 0) {
      console.log('No splits found. Run: sdlab split build');
      return;
    }
    console.log(`\x1b[1mSplits\x1b[0m — ${projectName}\n`);
    for (const s of splits) {
      console.log(`  ${s.id}  snap=${s.snapshot_id}  train=${s.train} val=${s.val} test=${s.test}  families=${s.families}  ${s.created_at}`);
    }

  } else if (subcommand === 'show') {
    const splitId = args.find(a => a.startsWith('split-'));
    if (!splitId) throw new Error('Usage: sdlab split show <split-id>');

    const manifest = await loadSplit(projectRoot, splitId);
    console.log(`\x1b[1mSplit\x1b[0m — ${splitId}\n`);
    console.log(`  Created:  ${manifest.created_at}`);
    console.log(`  Snapshot: ${manifest.snapshot_id}`);
    console.log(`  Records:  ${manifest.counts.total_records}`);
    console.log(`  Families: ${manifest.counts.total_families}`);
    console.log(`  Train:    ${manifest.counts.train}`);
    console.log(`  Val:      ${manifest.counts.val}`);
    console.log(`  Test:     ${manifest.counts.test}`);
    console.log('');
    console.log('  Profile:');
    for (const [k, v] of Object.entries(manifest.profile)) {
      console.log(`    ${k}: ${JSON.stringify(v)}`);
    }
    if (manifest.warnings.length > 0) {
      console.log('');
      console.log('  Warnings:');
      for (const w of manifest.warnings) {
        console.log(`    ⚠ ${w}`);
      }
    }

  } else if (subcommand === 'audit') {
    const splitId = args.find(a => a.startsWith('split-'));
    if (!splitId) throw new Error('Usage: sdlab split audit <split-id>');

    const audit = await loadSplitAudit(projectRoot, splitId);
    console.log(`\x1b[1mSplit audit\x1b[0m — ${splitId}\n`);

    // Leakage check
    if (audit.leakage_check.passed) {
      console.log(`  \x1b[32m✓\x1b[0m Leakage check: PASSED`);
    } else {
      console.log(`  \x1b[31m✗\x1b[0m Leakage check: FAILED`);
      for (const issue of audit.leakage_check.issues) {
        console.log(`    family="${issue.family}" (${issue.record_count} records) leaked to: ${issue.leaked_to.join(', ')}`);
      }
    }

    // Family distribution
    console.log(`\n  Families: ${audit.family_count}`);
    console.log(`    Train: ${audit.families_per_split.train}`);
    console.log(`    Val:   ${audit.families_per_split.val}`);
    console.log(`    Test:  ${audit.families_per_split.test}`);

    // Lane balance
    console.log('\n  Lane balance:');
    console.log(`    ${'Lane'.padEnd(20)} ${'Total'.padStart(6)} ${'Train%'.padStart(8)} ${'Val%'.padStart(8)} ${'Test%'.padStart(8)}`);
    console.log(`    ${'─'.repeat(52)}`);
    for (const [lane, b] of Object.entries(audit.lane_balance).sort((a, b) => b[1].total - a[1].total)) {
      console.log(`    ${lane.padEnd(20)} ${String(b.total).padStart(6)} ${String(b.train_pct + '%').padStart(8)} ${String(b.val_pct + '%').padStart(8)} ${String(b.test_pct + '%').padStart(8)}`);
    }

  } else {
    throw new Error(`Unknown subcommand: ${subcommand}. Use: build, list, show, audit`);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('split.js') || process.argv[1].endsWith('split'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
