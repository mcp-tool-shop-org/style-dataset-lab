#!/usr/bin/env node

/**
 * workflow-list.js — List workflow profiles for a project.
 *
 * Usage:
 *   sdlab workflow list --project star-freight
 *   sdlab workflow list --project star-freight --json
 */

import { getProjectName, parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { listWorkflowProfiles } from '../lib/workflow-profiles.js';

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
  const profiles = await listWorkflowProfiles(projectRoot);

  if (flags.json) {
    console.log(JSON.stringify(profiles, null, 2));
    return;
  }

  console.log(`\x1b[1msdlab workflow list\x1b[0m — ${projectName}\n`);

  if (profiles.length === 0) {
    console.log('  No workflow profiles found.');
    console.log(`  Add profiles to projects/${projectName}/workflows/profiles/`);
    return;
  }

  // Table header
  const idW = Math.max(12, ...profiles.map(p => p.workflow_id.length));
  const laneW = Math.max(6, ...profiles.map(p => p.lane_id.length));
  const modeW = Math.max(7, ...profiles.map(p => (p.subject_mode || 'optional').length));
  const outW = Math.max(11, ...profiles.map(p => p.output_mode.length));

  const header = `  ${'WORKFLOW'.padEnd(idW)}  ${'LANE'.padEnd(laneW)}  ${'SUBJECT'.padEnd(modeW)}  ${'OUTPUT MODE'.padEnd(outW)}  COUNT`;
  console.log(header);
  console.log('  ' + '─'.repeat(header.length - 2));

  for (const p of profiles) {
    const line = `  ${p.workflow_id.padEnd(idW)}  ${p.lane_id.padEnd(laneW)}  ${(p.subject_mode || 'optional').padEnd(modeW)}  ${p.output_mode.padEnd(outW)}  ${p.output_count}`;
    console.log(line);
  }

  console.log(`\n  ${profiles.length} workflow(s)`);
}

if (process.argv[1] && (process.argv[1].endsWith('workflow-list.js') || process.argv[1].endsWith('workflow-list'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
