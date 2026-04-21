#!/usr/bin/env node

/**
 * workflow-show.js — Show details of a workflow profile.
 *
 * Usage:
 *   sdlab workflow show character-portrait-set --project star-freight
 *   sdlab workflow show character-portrait-set --json
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { getWorkflowProfile } from '../lib/workflow-profiles.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      json: { type: 'boolean' },
    },
    positionals: ['workflowId'],
    deprecated: { game: 'project' },
  });

  const workflowId = positionals[0];
  if (!workflowId) {
    console.log('Usage: sdlab workflow show <workflow-id> [--project <name>]');
    return;
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const profile = await getWorkflowProfile(projectRoot, workflowId);

  if (flags.json) {
    console.log(JSON.stringify(profile, null, 2));
    return;
  }

  console.log(`\x1b[1msdlab workflow show\x1b[0m — ${workflowId}\n`);
  console.log(`  Label:        ${profile.label}`);
  if (profile.description) {
    console.log(`  Description:  ${profile.description}`);
  }
  console.log(`  Lane:         ${profile.lane_id}`);
  console.log(`  Subject:      ${profile.subject_mode || 'optional'}`);
  console.log(`  Output mode:  ${profile.output_mode}`);
  console.log(`  Output count: ${profile.output_count}`);
  console.log('');

  console.log('  \x1b[1mPrompt strategy:\x1b[0m');
  console.log(`    Style prefix:  ${profile.prompt_strategy.style_prefix.join(', ')}`);
  console.log(`    Structure:     ${profile.prompt_strategy.structure}`);
  console.log(`    Must include:  ${profile.prompt_strategy.must_include.join(', ')}`);
  if (profile.prompt_strategy.optional_blocks?.length > 0) {
    console.log(`    Optional:      ${profile.prompt_strategy.optional_blocks.join(', ')}`);
  }
  console.log('');

  console.log('  \x1b[1mNegative strategy:\x1b[0m');
  console.log(`    Must avoid:    ${profile.negative_strategy.must_avoid.join(', ')}`);
  if (profile.negative_strategy.lane_specific_avoid?.length > 0) {
    console.log(`    Lane avoid:    ${profile.negative_strategy.lane_specific_avoid.join(', ')}`);
  }
  console.log('');

  console.log('  \x1b[1mCanon focus:\x1b[0m');
  console.log(`    ${profile.canon_focus.join(', ')}`);
  console.log('');

  console.log('  \x1b[1mDrift guards:\x1b[0m');
  for (const guard of profile.drift_guards) {
    console.log(`    ⚠ ${guard}`);
  }
  console.log('');

  console.log('  \x1b[1mRuntime defaults:\x1b[0m');
  const rd = profile.runtime_defaults;
  console.log(`    Adapter:   ${rd.adapter_target}`);
  if (rd.width) console.log(`    Size:      ${rd.width}×${rd.height || rd.width}`);
  if (rd.steps) console.log(`    Steps:     ${rd.steps}`);
  if (rd.cfg) console.log(`    CFG:       ${rd.cfg}`);
  if (rd.sampler) console.log(`    Sampler:   ${rd.sampler}`);
  if (rd.seed_mode) console.log(`    Seed mode: ${rd.seed_mode}`);

  if (profile.required_reference_roles?.length > 0) {
    console.log('');
    console.log(`  \x1b[1mRequired references:\x1b[0m ${profile.required_reference_roles.join(', ')}`);
  }
  if (profile.preferred_reference_tags?.length > 0) {
    console.log(`  \x1b[1mPreferred tags:\x1b[0m ${profile.preferred_reference_tags.join(', ')}`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('workflow-show.js') || process.argv[1].endsWith('workflow-show'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
