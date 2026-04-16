#!/usr/bin/env node

/**
 * training-package.js — Build and inspect training packages.
 *
 * Usage:
 *   sdlab training-package build --manifest <id> [--adapter <target>] [--copy] [--project <name>]
 *   sdlab training-package show <package-id> [--project <name>]
 *   sdlab training-package list [--project <name>]
 */

import { join } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { listTrainingManifests } from '../lib/training-manifests.js';
import { buildTrainingPackage, listTrainingPackages, loadTrainingPackage } from '../lib/training-packages.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = argv.find(a => !a.startsWith('--') && !a.startsWith('tp-') && !a.startsWith('tm-')) || 'list';
  const args = argv.filter(a => a !== subcommand);

  if (subcommand === 'build') {
    // Find manifest
    let manifestId;
    const manifestIdx = args.indexOf('--manifest');
    if (manifestIdx >= 0) {
      manifestId = args[manifestIdx + 1];
    } else {
      const manifests = await listTrainingManifests(projectRoot);
      if (manifests.length === 0) throw new Error('No training manifests found. Run: sdlab training-manifest create');
      manifestId = manifests[manifests.length - 1].id;
    }

    const adapterIdx = args.indexOf('--adapter');
    const adapterOverride = adapterIdx >= 0 ? args[adapterIdx + 1] : undefined;
    const copy = args.includes('--copy');

    console.log(`\x1b[1msdlab training-package build\x1b[0m — ${projectName}`);
    console.log(`  Manifest: ${manifestId}`);
    if (adapterOverride) console.log(`  Adapter:  ${adapterOverride}`);
    console.log(`  Images:   ${copy ? 'copy' : 'symlink'}`);
    console.log('');

    const result = await buildTrainingPackage(projectRoot, manifestId, { copy, adapterOverride });

    console.log(`  \x1b[32m✓\x1b[0m Package: ${result.packageId}`);
    console.log(`  Records: ${result.records}`);
    console.log(`  Images:  ${result.images}`);

  } else if (subcommand === 'show') {
    const packageId = args.find(a => a.startsWith('tp-'));
    if (!packageId) throw new Error('Usage: sdlab training-package show <package-id>');

    const pkg = await loadTrainingPackage(projectRoot, packageId);
    console.log(`\x1b[1mTraining package\x1b[0m — ${packageId}\n`);
    console.log(`  Created:  ${pkg.created_at}`);
    console.log(`  Profile:  ${pkg.training_profile_id}`);
    console.log(`  Adapter:  ${pkg.adapter_target}`);
    console.log(`  Manifest: ${pkg.training_manifest_id}`);
    console.log(`  Export:   ${pkg.source_export_id}`);
    console.log(`  Records:  ${pkg.counts.total_records} (train=${pkg.counts.train} val=${pkg.counts.val} test=${pkg.counts.test})`);
    console.log(`  Images:   ${pkg.counts.images}`);

  } else if (subcommand === 'list') {
    const packages = await listTrainingPackages(projectRoot);
    if (packages.length === 0) {
      console.log('No training packages found. Run: sdlab training-package build');
      return;
    }
    console.log(`\x1b[1mTraining packages\x1b[0m — ${projectName}\n`);
    for (const p of packages) {
      console.log(`  ${p.id}  profile=${p.profile}  adapter=${p.adapter}  records=${p.records}  images=${p.images}  ${p.created_at}`);
    }

  } else {
    throw new Error(`Unknown subcommand: ${subcommand}. Use: build, show, list`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('training-package.js') || process.argv[1].endsWith('training-package'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
