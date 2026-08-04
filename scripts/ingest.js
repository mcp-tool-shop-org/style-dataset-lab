#!/usr/bin/env node

/**
 * ingest.js — Bring a directory of pre-existing images into the pipeline
 * as bare, uncurated candidate records.
 *
 * Closes the gap where generation happened OUTSIDE sdlab entirely (a hand
 * batch, external Python against Comfy Cloud, salvage from somewhere else)
 * and there was no CLI path to get those images into records/ for review.
 * Unlike `sdlab reingest generated` (which requires a trained LoRA's
 * training manifest) or `sdlab reingest selected` (which requires a
 * selection id only the production loop can mint), this takes any folder
 * of images and any project — no pipeline history required.
 *
 * Usage:
 *   sdlab ingest <dir> --project <name>
 *   sdlab ingest <dir> --project <name> --wave inputs/prompts/wave-v2.json
 *   sdlab ingest <dir> --project <name> --dry-run
 *   sdlab ingest <dir> --project <name> --json
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { REPO_ROOT, getProjectRoot, resolveSafeProjectPath } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { ingestDirectory } from '../lib/ingest.js';
import { result } from '../lib/log.js';

const USAGE = `Usage: sdlab ingest <dir> --project <name> [--wave <wave.json>] [--dry-run] [--json]

Scan <dir> for images and create bare candidate records (judgment: null,
canon: null, provenance.source: "external") ready for "sdlab curate".

Positional:
  dir                  Directory of images to ingest (png/jpg/jpeg/webp)

Flags:
  --project <name>     Project to operate on
  --wave <path>        Optional wave JSON (inputs/prompts/*.json shape) to
                        attach real generation provenance (seed, prompt, ...)
                        by matching each image's filename stem to an item id.
                        A sibling receipts.jsonl next to <dir> is picked up
                        automatically when present (prompt_id, seconds, status).
  --dry-run            Preview what would be created — no files written
  --json               Emit the result as JSON on stdout

Next steps after ingesting:
  1. Review: sdlab curate <id> approved/rejected "explanation"
  2. Bind:   sdlab bind --project <name>`;

export async function run(argv = process.argv.slice(2)) {
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(USAGE);
    return;
  }

  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      wave: { type: 'string' },
      'dry-run': { type: 'boolean', default: false },
      json: { type: 'boolean', default: false },
    },
    deprecated: { game: 'project' },
  });

  const dirArg = positionals[0];
  if (!dirArg) {
    throw inputError(
      'INPUT_MISSING_ARGS',
      'A source directory is required.',
      USAGE
    );
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const dryRun = flags['dry-run'] || flags.dryRun;

  // Mirrors scripts/reingest.js's --source handling: the source directory
  // of pre-existing images is allowed to live anywhere under the workspace
  // root, not just inside this specific project (e.g. a shared staging
  // inbox), while still refusing to escape the workspace entirely.
  const safeSourceDir = resolveSafeProjectPath(projectRoot, dirArg, { baseRoot: REPO_ROOT, flagName: 'dir' });

  // Mirrors scripts/generate.js's pack-path handling: a --wave file is
  // expected to live inside THIS project (inputs/prompts/*.json), so its
  // containment root defaults to the project root, not the whole workspace.
  const safeWavePath = flags.wave
    ? resolveSafeProjectPath(projectRoot, flags.wave, { flagName: 'wave' })
    : null;

  if (!flags.json) {
    console.log(`\x1b[1msdlab ingest\x1b[0m — ${projectName}`);
    console.log(`  Source: ${dirArg}`);
    if (flags.wave) console.log(`  Wave:   ${flags.wave}`);
    if (dryRun) console.log(`  Mode:   DRY RUN (no files written)`);
    console.log('');
  }

  const { created, skipped, rejected, receiptsFile } = await ingestDirectory(projectRoot, safeSourceDir, {
    wavePath: safeWavePath,
    dryRun,
  });

  if (flags.json) {
    console.log(JSON.stringify({ created, skipped, rejected, receiptsFile, dryRun }, null, 2));
    return;
  }

  if (receiptsFile) {
    console.log(`  \x1b[2mreceipts: ${receiptsFile}\x1b[0m`);
  }

  console.log(`  \x1b[32m✓\x1b[0m Created: ${created.length} record(s)${dryRun ? ' (dry run — nothing written)' : ''}`);
  if (created.length > 0 && created.length <= 25) {
    for (const id of created) console.log(`    ✓ ${id}`);
  }

  if (skipped.length > 0) {
    console.log(`  Skipped: ${skipped.length} (record already exists)`);
    if (skipped.length <= 25) {
      for (const id of skipped) console.log(`    ○ ${id}`);
    }
  }

  if (rejected.length > 0) {
    console.log(`  \x1b[33m⚠\x1b[0m Rejected: ${rejected.length} (unsafe id derived from filename — rename and re-run)`);
    for (const r of rejected) console.log(`    ✗ ${r.file}: ${r.reason}`);
  }

  if (!dryRun && created.length > 0) {
    console.log('');
    result(`Candidates: outputs/candidates/`);
    result(`Records: records/`);
    console.log('');
    console.log('  Next steps:');
    console.log('    1. Review: sdlab curate <id> approved/rejected "explanation"');
    console.log('    2. Bind:   sdlab bind --project ' + projectName);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('ingest.js') || process.argv[1].endsWith('ingest'))) {
  run().catch(handleCliError);
}
