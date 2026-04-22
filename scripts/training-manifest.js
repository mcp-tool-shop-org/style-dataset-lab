#!/usr/bin/env node

/**
 * training-manifest.js — Create, validate, list, and show training manifests.
 *
 * Usage:
 *   sdlab training-manifest create --export <id> --profile <id> [--adapter <target>] [--base-model <name>] [--project <name>]
 *   sdlab training-manifest validate <manifest-id> [--project <name>]
 *   sdlab training-manifest show <manifest-id> [--project <name>]
 *   sdlab training-manifest list [--project <name>]
 */

import { join } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { listExports } from '../lib/export.js';
import {
  createTrainingManifest,
  validateTrainingManifest,
  loadTrainingManifest,
  listTrainingManifests,
} from '../lib/training-manifests.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      export: { type: 'string' },
      profile: { type: 'string' },
      adapter: { type: 'string' },
      'base-model': { type: 'string' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = positionals.find(a => !a.startsWith('tm-')) || 'list';

  if (subcommand === 'create') {
    let exportId = flags.export;
    if (!exportId) {
      const exports = await listExports(projectRoot);
      if (exports.length === 0) throw inputError('INPUT_NO_EXPORT', 'No exports found. Run: sdlab export build');
      exportId = exports[exports.length - 1].id;
    }

    if (!flags.profile) throw inputError('INPUT_MISSING_FLAG', '--profile is required. Use: sdlab training-profile list');
    const profileId = flags.profile;

    const adapterTarget = flags.adapter;
    const baseModel = flags['base-model'] || flags.baseModel;

    console.log(`\x1b[1msdlab training-manifest create\x1b[0m — ${projectName}`);
    console.log(`  Export:  ${exportId}`);
    console.log(`  Profile: ${profileId}`);
    if (adapterTarget) console.log(`  Adapter: ${adapterTarget}`);
    if (baseModel) console.log(`  Base:    ${baseModel}`);
    console.log('');

    const result = await createTrainingManifest(projectRoot, exportId, profileId, {
      adapterTarget,
      baseModel,
    });

    console.log(`  \x1b[32m✓\x1b[0m Manifest: ${result.manifestId}`);

  } else if (subcommand === 'validate') {
    const manifestId = positionals.find(a => a.startsWith('tm-'));
    if (!manifestId) throw inputError('INPUT_MISSING_ARGS', 'Usage: sdlab training-manifest validate <manifest-id>');

    console.log(`\x1b[1msdlab training-manifest validate\x1b[0m — ${manifestId}\n`);
    const { valid, issues } = await validateTrainingManifest(projectRoot, manifestId);

    if (valid) {
      console.log(`  \x1b[32m✓\x1b[0m Manifest is valid — all references intact, fingerprints match`);
    } else {
      console.log(`  \x1b[31m✗\x1b[0m Manifest has issues:`);
      for (const issue of issues) {
        console.log(`    - ${issue}`);
      }
    }

  } else if (subcommand === 'show') {
    const manifestId = positionals.find(a => a.startsWith('tm-'));
    if (!manifestId) throw inputError('INPUT_MISSING_ARGS', 'Usage: sdlab training-manifest show <manifest-id>');

    const manifest = await loadTrainingManifest(projectRoot, manifestId);
    console.log(`\x1b[1mTraining manifest\x1b[0m — ${manifestId}\n`);
    console.log(`  Created:     ${manifest.created_at}`);
    console.log(`  Profile:     ${manifest.training_profile_id}`);
    console.log(`  Export:      ${manifest.source_export_id}`);
    console.log(`  Snapshot:    ${manifest.source_snapshot_id}`);
    console.log(`  Split:       ${manifest.source_split_id}`);
    console.log(`  Adapter:     ${manifest.adapter_target}`);
    console.log(`  Base model:  ${manifest.base_model || '(not specified)'}`);
    console.log(`  Caption:     ${manifest.caption_mode}`);
    console.log(`  Records:     ${manifest.dataset_counts?.records || 0}`);
    console.log(`  Fingerprint: ${manifest.config_fingerprint.slice(0, 16)}...`);
    console.log(`  Export hash: ${manifest.export_manifest_hash.slice(0, 16)}...`);
    if (manifest.linked_eval_pack_ids?.length) {
      console.log(`  Eval packs:  ${manifest.linked_eval_pack_ids.length}`);
    }

  } else if (subcommand === 'list') {
    const manifests = await listTrainingManifests(projectRoot);
    if (manifests.length === 0) {
      console.log('No training manifests found. Run: sdlab training-manifest create');
      return;
    }
    console.log(`\x1b[1mTraining manifests\x1b[0m — ${projectName}\n`);
    for (const m of manifests) {
      console.log(`  ${m.id}  profile=${m.profile}  export=${m.export_id}  adapter=${m.adapter}  records=${m.records}  ${m.created_at}`);
    }

  } else {
    throw inputError('INPUT_BAD_SUBCOMMAND', `Unknown subcommand: ${subcommand}. Use: create, validate, show, list`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('training-manifest.js') || process.argv[1].endsWith('training-manifest'))) {
  run().catch(handleCliError);
}
