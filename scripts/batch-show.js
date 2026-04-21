#!/usr/bin/env node

/**
 * batch-show.js — List batches or show batch details.
 *
 * Usage:
 *   sdlab batch show --project star-freight          # list all batches
 *   sdlab batch show batch_2025-06-30_001            # show specific batch
 *   sdlab batch show batch_2025-06-30_001 --json     # as JSON
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { listBatches, loadBatchManifest } from '../lib/batch-runs.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      batch: { type: 'string' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const batchId = positionals[0] || flags.batch;

  // List mode
  if (!batchId) {
    const batches = listBatches(projectRoot);
    if (batches.length === 0) {
      console.log('No batches found.');
      return;
    }
    console.log(`\x1b[1mstyle-dataset-lab\x1b[0m batches (${projectName})`);
    console.log('');
    for (const id of batches) {
      try {
        const manifest = loadBatchManifest(projectRoot, id);
        const mode = manifest.mode_id || '?';
        const slots = manifest.summary?.total_slots || manifest.slots?.length || 0;
        const ok = manifest.summary?.successful_slots ?? '?';
        const dry = manifest.summary?.dry_run ? ' [dry]' : '';
        const subject = manifest.subject_id ? ` (${manifest.subject_id})` : '';
        console.log(`  ${id}  ${mode.padEnd(24)} ${ok}/${slots} slots${dry}${subject}`);
      } catch {
        console.log(`  ${id}  (manifest unreadable)`);
      }
    }
    console.log('');
    return;
  }

  // Detail mode
  const manifest = loadBatchManifest(projectRoot, batchId);

  if (flags.json) {
    console.log(JSON.stringify(manifest, null, 2));
    return;
  }

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m batch ${batchId}`);
  console.log('');
  console.log(`  Mode:      ${manifest.mode_id}`);
  console.log(`  Project:   ${manifest.project_id}`);
  if (manifest.subject_id) console.log(`  Subject:   ${manifest.subject_id}`);
  if (manifest.theme) console.log(`  Theme:     ${manifest.theme}`);
  console.log(`  Created:   ${manifest.created_at}`);
  if (manifest.summary?.dry_run) console.log('  ⚠ DRY RUN');
  console.log('');
  console.log('  Slots:');
  for (const slot of manifest.slots || []) {
    const status = slot.selected_output ? '✓' : '○';
    console.log(`    ${status} ${(slot.label || slot.slot_id).padEnd(24)} run=${slot.run_id}  ${slot.selected_output || ''}`);
  }
  console.log('');
  if (manifest.sheet_paths?.length) {
    console.log('  Sheets:');
    for (const p of manifest.sheet_paths) {
      console.log(`    ${p}`);
    }
    console.log('');
  }
}
