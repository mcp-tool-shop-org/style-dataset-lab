#!/usr/bin/env node

/**
 * critique.js — Generate a critique report for a completed run.
 *
 * Usage:
 *   sdlab critique --project star-freight --run run_2026-04-15_001
 *   sdlab critique --project star-freight --run run_2026-04-15_001 --json
 */

import { parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { critiqueRun, saveCritique } from '../lib/critique-engine.js';
import { renderCritiqueMarkdown, renderCritiqueText } from '../lib/critique-render.js';
import { info } from '../lib/log.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      run: { type: 'string' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.run) {
    console.log('Usage: sdlab critique --run <id> [--project <name>]');
    console.log('');
    console.log('Options:');
    console.log('  --run <id>        Run to critique (required)');
    console.log('  --json            Output raw JSON');
    return;
  }

  const projectName = flags.project;
  const projectRoot = getProjectRoot(projectName);

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m critique`);
  console.log(`  Project: ${projectName}`);
  console.log(`  Run: ${flags.run}`);
  console.log('');

  // Generate critique
  const report = await critiqueRun({
    projectRoot,
    projectId: projectName,
    runId: flags.run,
  });

  // Save
  const md = renderCritiqueMarkdown(report);
  await saveCritique(projectRoot, flags.run, report, md);

  if (flags.json) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(renderCritiqueText(report));
    const action = report.recommended_action;
    console.log(`Critique saved to: runs/${flags.run}/critique.json`);

    if (action.mode === 'refine_from_one' && action.preferred_candidate) {
      console.log('');
      info(`Next: sdlab refine --run ${flags.run} --pick ${action.preferred_candidate}`);
    } else if (action.mode === 'accept_one' && action.preferred_candidate) {
      console.log('');
      info(`Preferred candidate: ${action.preferred_candidate}`);
    }
  }
}
