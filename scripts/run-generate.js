#!/usr/bin/env node

/**
 * run-generate.js — Execute a compiled brief through ComfyUI.
 *
 * Usage:
 *   sdlab run generate --brief brief_2026-04-15_001 --project star-freight
 *   sdlab run generate --brief brief_2026-04-15_001 --project star-freight --dry-run
 *   sdlab run generate --brief brief_2026-04-15_001 --project star-freight --seed 42
 */

import { parseArgs, getProjectName, parseNumberFlag } from '../lib/args.js';
import { getProjectRoot, getRunsDir } from '../lib/paths.js';
import { loadCompiledBrief } from '../lib/brief-compiler.js';
import { executeRun } from '../lib/adapters/comfyui-runner.js';
import { saveRunSummary, renderRunText } from '../lib/run-summary.js';
import { info } from '../lib/log.js';
import { join } from 'node:path';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      brief: { type: 'string' },
      seed: { type: 'string' },
      'dry-run': { type: 'boolean' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.brief) {
    console.log('Usage: sdlab run generate --brief <id> [--project <name>]');
    console.log('');
    console.log('Options:');
    console.log('  --brief <id>      Compiled brief ID (required)');
    console.log('  --seed <n>        Override base seed');
    console.log('  --dry-run         Prepare run dir without submitting to ComfyUI');
    console.log('  --json            Output manifest as JSON');
    return;
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m run generate`);
  console.log(`  Project: ${projectName}`);
  console.log(`  Brief: ${flags.brief}`);
  if (flags['dry-run']) console.log('  ⚠ DRY RUN');
  console.log('');

  // Load brief
  const brief = await loadCompiledBrief(projectRoot, flags.brief);

  // Execute
  const manifest = await executeRun({
    projectRoot,
    projectName,
    brief,
    baseSeed: flags.seed ? parseNumberFlag('seed', flags.seed, { int: true, min: 0 }) : undefined,
    dryRun: flags['dry-run'] || false,
  });

  // Save summary
  const runDir = join(getRunsDir(projectRoot), manifest.run_id);
  await saveRunSummary(runDir, manifest);

  console.log('');
  if (flags.json) {
    console.log(JSON.stringify(manifest, null, 2));
  } else {
    console.log(renderRunText(manifest));
    console.log('');
    info(`Run saved to: runs/${manifest.run_id}/`);
  }
}
