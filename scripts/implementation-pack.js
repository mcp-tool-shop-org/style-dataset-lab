#!/usr/bin/env node

/**
 * implementation-pack.js — Build and inspect implementation example packs.
 *
 * Usage:
 *   sdlab implementation-pack build --manifest <id> [--project <name>]
 *   sdlab implementation-pack show <impl-id> [--project <name>]
 *   sdlab implementation-pack list [--project <name>]
 */

import { join } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { listTrainingManifests } from '../lib/training-manifests.js';
import { buildImplementationPack, listImplementationPacks, loadImplementationPack } from '../lib/implementation-packs.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      manifest: { type: 'string' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = positionals.find(a => !a.startsWith('impl-') && !a.startsWith('tm-')) || 'list';

  if (subcommand === 'build') {
    let manifestId = flags.manifest;
    if (!manifestId) {
      const manifests = await listTrainingManifests(projectRoot);
      if (manifests.length === 0) throw inputError('INPUT_NO_MANIFEST', 'No training manifests. Run: sdlab training-manifest create');
      manifestId = manifests[manifests.length - 1].id;
    }

    console.log(`\x1b[1msdlab implementation-pack build\x1b[0m — ${projectName}`);
    console.log(`  Manifest: ${manifestId}`);
    console.log('');

    const result = await buildImplementationPack(projectRoot, manifestId);

    console.log(`  \x1b[32m✓\x1b[0m Implementation pack: ${result.implId}`);
    console.log(`  Prompt examples:      ${result.prompts}`);
    console.log(`  Known failures:       ${result.failures}`);
    console.log(`  Subject continuity:   ${result.subjects}`);

  } else if (subcommand === 'show') {
    const implId = positionals.find(a => a.startsWith('impl-'));
    if (!implId) throw inputError('INPUT_MISSING_ARGS', 'Usage: sdlab implementation-pack show <impl-id>');

    const pack = await loadImplementationPack(projectRoot, implId);
    console.log(`\x1b[1mImplementation pack\x1b[0m — ${implId}\n`);
    console.log(`  Created:    ${pack.created_at}`);
    console.log(`  Manifest:   ${pack.training_manifest_id}`);
    console.log(`  Profile:    ${pack.training_profile_id}`);
    console.log(`  Prompts:    ${pack.counts.prompt_examples}`);
    console.log(`  Failures:   ${pack.counts.known_failures}`);
    console.log(`  Subjects:   ${pack.counts.subject_examples}`);
    console.log(`  Lanes:      ${pack.counts.lanes_covered}`);

  } else if (subcommand === 'list') {
    const packs = await listImplementationPacks(projectRoot);
    if (packs.length === 0) {
      console.log('No implementation packs. Run: sdlab implementation-pack build');
      return;
    }
    console.log(`\x1b[1mImplementation packs\x1b[0m — ${projectName}\n`);
    for (const p of packs) {
      console.log(`  ${p.id}  manifest=${p.manifest}  prompts=${p.prompts}  failures=${p.failures}  ${p.created_at}`);
    }

  } else {
    throw inputError('INPUT_BAD_SUBCOMMAND', `Unknown subcommand: ${subcommand}. Use: build, show, list`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('implementation-pack.js') || process.argv[1].endsWith('implementation-pack'))) {
  run().catch(handleCliError);
}
