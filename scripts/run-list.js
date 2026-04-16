#!/usr/bin/env node

/**
 * run-list.js — List all runs for a project.
 *
 * Usage:
 *   sdlab run list --project star-freight
 *   sdlab run list --project star-freight --json
 */

import { parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { listRuns } from '../lib/runtime-runs.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project;
  const projectRoot = getProjectRoot(projectName);
  const runs = listRuns(projectRoot);

  if (flags.json) {
    console.log(JSON.stringify(runs, null, 2));
    return;
  }

  if (runs.length === 0) {
    console.log('No runs found. Run: sdlab run generate --brief <id>');
    return;
  }

  console.log(`\x1b[1mRuns for ${projectName}\x1b[0m (${runs.length})\n`);

  const header = '  ' +
    'Run ID'.padEnd(26) +
    'Brief'.padEnd(26) +
    'Mode'.padEnd(18) +
    'Count'.padEnd(8) +
    'Created';
  console.log(header);
  console.log('  ' + '─'.repeat(90));

  for (const r of runs) {
    const line = '  ' +
      (r.run_id || '').padEnd(26) +
      (r.brief_id || '').padEnd(26) +
      (r.adapter_target || '?').padEnd(18) +
      String(r.output_count ?? '?').padEnd(8) +
      (r.created_at ? r.created_at.slice(0, 16) : '?');
    console.log(line);
  }
}
