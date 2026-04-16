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
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { listExports } from '../lib/export.js';
import {
  createTrainingManifest,
  validateTrainingManifest,
  loadTrainingManifest,
  listTrainingManifests,
} from '../lib/training-manifests.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = argv.find(a => !a.startsWith('--') && !a.startsWith('tm-')) || 'list';
  const args = argv.filter(a => a !== subcommand);

  if (subcommand === 'create') {
    // Required: --export and --profile
    const exportIdx = args.indexOf('--export');
    if (exportIdx < 0) {
      // Try latest export
      const exports = await listExports(projectRoot);
      if (exports.length === 0) throw new Error('No exports found. Run: sdlab export build');
    }
    const exportId = exportIdx >= 0 ? args[exportIdx + 1] : (await listExports(projectRoot)).pop().id;

    const profileIdx = args.indexOf('--profile');
    if (profileIdx < 0) throw new Error('--profile is required. Use: sdlab training-profile list');
    const profileId = args[profileIdx + 1];

    const adapterIdx = args.indexOf('--adapter');
    const adapterTarget = adapterIdx >= 0 ? args[adapterIdx + 1] : undefined;

    const baseModelIdx = args.indexOf('--base-model');
    const baseModel = baseModelIdx >= 0 ? args[baseModelIdx + 1] : undefined;

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
    const manifestId = args.find(a => a.startsWith('tm-'));
    if (!manifestId) throw new Error('Usage: sdlab training-manifest validate <manifest-id>');

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
    const manifestId = args.find(a => a.startsWith('tm-'));
    if (!manifestId) throw new Error('Usage: sdlab training-manifest show <manifest-id>');

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
    throw new Error(`Unknown subcommand: ${subcommand}. Use: create, validate, show, list`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('training-manifest.js') || process.argv[1].endsWith('training-manifest'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
