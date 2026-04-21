#!/usr/bin/env node

/**
 * select.js — Approve outputs from runs or batches.
 *
 * Usage:
 *   sdlab select --run run_2026-04-15_001 --approve 001.png,003.png
 *   sdlab select --batch batch_2026-04-16_001 --approve slot_neutral:001.png,slot_anger:001.png
 *   sdlab select --run run_2026-04-15_001 --approve 001.png --reason "best continuity" --tags portrait,keeper
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import {
  createSelectionFromRun,
  createSelectionFromBatch,
  saveSelection,
} from '../lib/selections.js';
import { info } from '../lib/log.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      run: { type: 'string' },
      batch: { type: 'string' },
      approve: { type: 'string' },
      reason: { type: 'string' },
      tags: { type: 'string' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.approve || (!flags.run && !flags.batch)) {
    console.log('Usage: sdlab select --run <id> --approve <files>');
    console.log('       sdlab select --batch <id> --approve <slot:file,...>');
    console.log('');
    console.log('Options:');
    console.log('  --run <id>          Source run');
    console.log('  --batch <id>        Source batch');
    console.log('  --approve <list>    Comma-separated files (run) or slot:file pairs (batch)');
    console.log('  --reason <text>     Why these outputs were chosen');
    console.log('  --tags <list>       Comma-separated tags');
    console.log('  --json              Output manifest as JSON');
    return;
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const reason = flags.reason || undefined;
  const tags = flags.tags ? flags.tags.split(',').map(t => t.trim()) : undefined;

  let result;

  if (flags.run) {
    // Run selection: --approve 001.png,003.png
    const approvedFiles = flags.approve.split(',').map(f => f.trim());

    result = await createSelectionFromRun({
      projectRoot,
      projectId: projectName,
      runId: flags.run,
      approvedFiles,
      reason,
      tags,
    });
  } else if (flags.batch) {
    // Batch selection: --approve slot_neutral:001.png,slot_anger:001.png
    const pairs = flags.approve.split(',').map(p => p.trim());
    const approvedSlots = pairs.map(pair => {
      const colonIdx = pair.indexOf(':');
      if (colonIdx < 0) {
        throw inputError('INPUT_BAD_FORMAT', `Invalid batch approve format: "${pair}". Use slot_id:filename`);
      }
      return {
        slotId: pair.slice(0, colonIdx),
        filename: pair.slice(colonIdx + 1),
      };
    });

    result = await createSelectionFromBatch({
      projectRoot,
      projectId: projectName,
      batchId: flags.batch,
      approvedSlots,
      reason,
      tags,
    });
  }

  const { selectionId, selectionDir, manifest } = result;

  // Save the selection
  await saveSelection(selectionDir, manifest);

  if (flags.json) {
    console.log(JSON.stringify(manifest, null, 2));
    return;
  }

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m select`);
  console.log('');
  console.log(`  Selection: ${selectionId}`);
  console.log(`  Source: ${manifest.source_type} ${manifest.source_id}`);
  if (manifest.workflow_id) console.log(`  Workflow: ${manifest.workflow_id}`);
  if (manifest.subject_id) console.log(`  Subject: ${manifest.subject_id}`);
  console.log(`  Items: ${manifest.items.length}`);
  console.log('');

  for (const item of manifest.items) {
    console.log(`  ✓ ${item.slot_or_output.padEnd(28)} → ${item.filename}  ${item.reason}`);
  }

  console.log('');
  info(`Selection: selections/${selectionId}/manifest.json`);
  info(`Chosen files: selections/${selectionId}/chosen/`);
}
