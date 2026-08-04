#!/usr/bin/env node

/**
 * sheet.js — Render an HTML contact sheet over a directory of images.
 *
 * No batch manifest required. Points the SAME HTML renderer that powers
 * `sdlab batch sheet` (lib/batch-sheet-render.js, via lib/candidate-sheet.js)
 * at an arbitrary directory under a project — outputs/candidates/,
 * outputs/approved/, outputs/, whatever — instead of requiring a
 * batches/<id>/manifest.json that only `sdlab batch generate` can produce.
 *
 * Each image is matched to its record by asset_path (when a record exists)
 * for id / curation status / prompt. Images with no matching record
 * (pre-ingest — generated but not yet re-ingested) still render, labeled by
 * filename instead of crashing or being skipped.
 *
 * Usage:
 *   sdlab sheet [<dir>] --project <name> [--out <path>] [--dry-run]
 *
 * Examples:
 *   sdlab sheet --project star-freight                     # outputs/candidates (default)
 *   sdlab sheet outputs/approved --project star-freight
 *   sdlab sheet outputs --project star-freight --dry-run    # whole tree, no write
 */

import { existsSync } from 'node:fs';
import { relative, dirname } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot, resolveSafeProjectPath } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { result } from '../lib/log.js';
import {
  buildCandidateSheetItems,
  renderCandidateSheetHTML,
  saveCandidateSheet,
  defaultSheetOutputPath,
} from '../lib/candidate-sheet.js';

const DEFAULT_DIR = 'outputs/candidates';

function posix(p) {
  return p.replace(/\\/g, '/');
}

export async function run(argv = process.argv.slice(2)) {
  // Checked against the raw argv, not via parseArgs' flag defs: parseArgs
  // only recognizes "--"-prefixed flags (see lib/args.js), so a bare "-h"
  // would otherwise fall through to the positional `dir` slot instead of
  // showing help. Mirrors bin/sdlab.js's own argvHasHelp() check.
  if (argv.includes('--help') || argv.includes('-h')) {
    printUsage();
    return;
  }

  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      out: { type: 'string' },
      'dry-run': { type: 'boolean', default: false },
    },
    positionals: ['dir'],
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const dryRun = flags['dry-run'] || flags.dryRun;

  const dirArg = positionals[0] || DEFAULT_DIR;
  // Containment check — a user-supplied path must never be joined by hand.
  const safeDir = resolveSafeProjectPath(projectRoot, dirArg, { flagName: 'dir' });
  const relDir = posix(relative(projectRoot, safeDir)) || '.';

  if (!existsSync(safeDir)) {
    throw inputError(
      'INPUT_DIR_NOT_FOUND',
      `Directory not found: ${relDir} (looked under ${projectRoot})`,
      'Try outputs/candidates, outputs/approved, outputs/rejected, outputs/borderline, or outputs (the whole tree).'
    );
  }

  const items = await buildCandidateSheetItems(projectRoot, safeDir);

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m sheet — ${projectName}`);
  console.log(`  Source: ${relDir}`);

  if (items.length === 0) {
    console.log('  No images found — nothing to render.');
    return;
  }

  const matched = items.filter((i) => i.hasRecord).length;
  console.log(`  Images: ${items.length} (${matched} with records, ${items.length - matched} pre-ingest)`);

  const outRel = flags.out
    ? flags.out
    : posix(relative(projectRoot, defaultSheetOutputPath(projectRoot, relDir)));
  const safeOut = resolveSafeProjectPath(projectRoot, outRel, { flagName: 'out' });

  if (dryRun) {
    console.log(`  \x1b[33m(dry-run)\x1b[0m would write: ${posix(relative(projectRoot, safeOut))}`);
    return;
  }

  const html = renderCandidateSheetHTML({
    items,
    title: `Contact sheet — ${projectName} — ${relDir}`,
    sourceLabel: relDir,
    sheetOutputDir: dirname(safeOut),
  });

  const written = await saveCandidateSheet(safeOut, html);
  result('sheet', posix(relative(projectRoot, written)));
}

function printUsage() {
  console.log('Usage: sdlab sheet [<dir>] --project <name> [--out <path>] [--dry-run]');
  console.log('');
  console.log('Render an HTML contact sheet over a directory of images — no batch');
  console.log('manifest required. Matches each image to its record (by asset_path)');
  console.log('when one exists; degrades to filename when it does not (pre-ingest).');
  console.log('');
  console.log('Positional:');
  console.log('  dir                 Directory to sheet, relative to the project root');
  console.log(`                      (default: ${DEFAULT_DIR})`);
  console.log('');
  console.log('Flags:');
  console.log('  --project <name>    Project to operate on');
  console.log('  --out <path>        Output HTML path, relative to project root');
  console.log('                      (default: outputs/sheets/<slugified-dir>.html)');
  console.log('  --dry-run           Report what would be written without writing it');
  console.log('');
  console.log('Examples:');
  console.log('  sdlab sheet --project star-freight');
  console.log('  sdlab sheet outputs/approved --project star-freight');
  console.log('  sdlab sheet outputs --project star-freight --dry-run');
}

// Direct execution guard — same pattern as every other script in this repo.
if (process.argv[1] && (process.argv[1].endsWith('sheet.js') || process.argv[1].endsWith('sheet'))) {
  run().catch(handleCliError);
}
