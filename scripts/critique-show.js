#!/usr/bin/env node

/**
 * critique-show.js — Display a saved critique report.
 *
 * Usage:
 *   sdlab critique show --project star-freight --run run_2026-04-15_001
 *   sdlab critique show --project star-freight --run run_2026-04-15_001 --json
 *   sdlab critique show --project star-freight --run run_2026-04-15_001 --md
 */

import { parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { loadCritique } from '../lib/critique-engine.js';
import { renderCritiqueMarkdown, renderCritiqueText } from '../lib/critique-render.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      run: { type: 'string' },
      json: { type: 'boolean' },
      md: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.run) {
    console.log('Usage: sdlab critique show --run <id> [--project <name>]');
    console.log('');
    console.log('Options:');
    console.log('  --run <id>        Run ID (required)');
    console.log('  --json            Output raw JSON');
    console.log('  --md              Output full Markdown');
    return;
  }

  const projectName = flags.project;
  const projectRoot = getProjectRoot(projectName);

  const report = loadCritique(projectRoot, flags.run);

  if (flags.json) {
    console.log(JSON.stringify(report, null, 2));
  } else if (flags.md) {
    console.log(renderCritiqueMarkdown(report));
  } else {
    console.log(renderCritiqueText(report));
  }
}
