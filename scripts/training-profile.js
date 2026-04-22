#!/usr/bin/env node

/**
 * training-profile.js — List and show training profiles.
 *
 * Usage:
 *   sdlab training-profile list [--project <name>]
 *   sdlab training-profile show <profile-id> [--project <name>]
 */

import { join } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { listTrainingProfiles, loadTrainingProfile } from '../lib/training-profiles.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: { project: { type: 'string' } },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = positionals[0] || 'list';

  if (subcommand === 'list') {
    const profiles = await listTrainingProfiles(projectRoot);
    if (profiles.length === 0) {
      console.log('No training profiles found. Add JSON files to training/profiles/');
      return;
    }
    console.log(`\x1b[1mTraining profiles\x1b[0m — ${projectName}\n`);
    for (const p of profiles) {
      console.log(`  ${p.profile_id.padEnd(30)} ${p.target_family.padEnd(15)} ${p.asset_type.padEnd(10)} lanes=${p.lanes}  adapters=${p.adapters.join(',')}`);
    }

  } else if (subcommand === 'show') {
    const profileId = positionals[1];
    if (!profileId) throw inputError('INPUT_MISSING_ARGS', 'Usage: sdlab training-profile show <profile-id>');

    const profile = await loadTrainingProfile(projectRoot, profileId);
    console.log(`\x1b[1mTraining profile\x1b[0m — ${profileId}\n`);
    console.log(`  Label:           ${profile.label}`);
    console.log(`  Target family:   ${profile.target_family}`);
    console.log(`  Asset type:      ${profile.asset_type}`);
    console.log(`  Intended use:    ${profile.intended_use || '(not specified)'}`);
    console.log(`  Eligible lanes:  ${profile.eligible_lanes.join(', ')}`);
    console.log(`  Adapter targets: ${profile.adapter_targets.join(', ')}`);
    if (profile.caption_strategy) console.log(`  Caption:         ${profile.caption_strategy}`);
    if (profile.base_model_recommendations?.length) {
      console.log(`  Base models:     ${profile.base_model_recommendations.join(', ')}`);
    }
    if (profile.excluded_tags?.length) {
      console.log(`  Excluded tags:   ${profile.excluded_tags.join(', ')}`);
    }
    if (profile.required_eval_pack_profiles?.length) {
      console.log(`  Required evals:  ${profile.required_eval_pack_profiles.join(', ')}`);
    }

  } else {
    throw inputError('INPUT_BAD_SUBCOMMAND', `Unknown subcommand: ${subcommand}. Use: list, show`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('training-profile.js') || process.argv[1].endsWith('training-profile'))) {
  run().catch(handleCliError);
}
