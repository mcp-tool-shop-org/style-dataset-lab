#!/usr/bin/env node

/**
 * run-show.js — Show details of a completed run.
 *
 * Usage:
 *   sdlab run show run_2026-04-16_001 --project star-freight
 *   sdlab run show run_2026-04-16_001 --project star-freight --json
 *   sdlab run show run_2026-04-16_001 --project star-freight --md
 */

import { parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { loadRun, listRuns } from '../lib/runtime-runs.js';
import { renderRunText, renderRunMarkdown } from '../lib/run-summary.js';

export async function run(argv = process.argv.slice(2)) {
  const { positionals, flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      json: { type: 'boolean' },
      md: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  const runId = positionals[0];
  const projectName = flags.project;
  const projectRoot = getProjectRoot(projectName);

  // No run ID → list runs
  if (!runId) {
    const runs = listRuns(projectRoot);
    if (runs.length === 0) {
      console.log('No runs found. Run: sdlab run generate --brief <id>');
      return;
    }

    console.log(`\x1b[1mRuns for ${projectName}\x1b[0m (${runs.length})\n`);
    console.log('  ID                       Brief                      Mode            Outputs  Adapter');
    console.log('  ─'.padEnd(100, '─'));
    for (const r of runs) {
      const id = (r.run_id || '').padEnd(24);
      const brief = (r.brief_id || '').padEnd(24);
      const mode = (r.output_count != null ? `${r.output_count}` : '?').padStart(7);
      const adapter = r.adapter_target || '?';
      // output_mode if we have it
      console.log(`  ${id}  ${brief}  ${mode}  ${adapter}`);
    }
    return;
  }

  // Show single run
  const manifest = await loadRun(projectRoot, runId);

  if (flags.json) {
    console.log(JSON.stringify(manifest, null, 2));
  } else if (flags.md) {
    console.log(renderRunMarkdown(manifest));
  } else {
    console.log(renderRunText(manifest));
  }
}
