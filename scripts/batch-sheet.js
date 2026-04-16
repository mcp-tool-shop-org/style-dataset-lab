#!/usr/bin/env node

/**
 * batch-sheet.js — Re-render a batch sheet from saved manifest.
 *
 * Usage:
 *   sdlab batch sheet batch_2025-06-30_001 --project star-freight
 */

import { parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { loadBatchManifest } from '../lib/batch-runs.js';
import { getBatchMode } from '../lib/batch-modes.js';
import { renderSheetHTML, saveSheet } from '../lib/batch-sheet-render.js';
import { getBatchesDir } from '../lib/batch-runs.js';
import { join } from 'node:path';
import { inputError } from '../lib/errors.js';
import { info } from '../lib/log.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      batch: { type: 'string' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project;
  const projectRoot = getProjectRoot(projectName);
  const batchId = positionals[0] || flags.batch;

  if (!batchId) {
    console.log('Usage: sdlab batch sheet <batch-id> [--project <name>]');
    return;
  }

  const manifest = loadBatchManifest(projectRoot, batchId);
  const mode = getBatchMode(projectRoot, manifest.mode_id);
  const batchDir = join(getBatchesDir(projectRoot), batchId);

  const html = renderSheetHTML({ manifest, mode, projectRoot, batchDir });
  const sheetPath = await saveSheet(batchDir, 'primary-sheet.html', html);

  info(`Sheet written: ${sheetPath}`);
}
