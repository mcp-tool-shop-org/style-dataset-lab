#!/usr/bin/env node

/**
 * eval-run.js — Create, score, and inspect eval runs.
 *
 * Usage:
 *   sdlab eval-run create --manifest <id> --eval-pack <id> [--project <name>]
 *   sdlab eval-run score <eval-run-id> --outputs <path> [--project <name>]
 *   sdlab eval-run show <eval-run-id> [--project <name>]
 *   sdlab eval-run list [--project <name>]
 */

import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { listTrainingManifests } from '../lib/training-manifests.js';
import { listEvalPacks } from '../lib/eval-pack.js';
import { createEvalRun, scoreEvalRun, loadEvalRun, listEvalRuns } from '../lib/eval-runs.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = argv.find(a => !a.startsWith('--') && !a.startsWith('er-')) || 'list';
  const args = argv.filter(a => a !== subcommand);

  if (subcommand === 'create') {
    // Find manifest
    let manifestId;
    const manifestIdx = args.indexOf('--manifest');
    if (manifestIdx >= 0) {
      manifestId = args[manifestIdx + 1];
    } else {
      const manifests = await listTrainingManifests(projectRoot);
      if (manifests.length === 0) throw new Error('No training manifests. Run: sdlab training-manifest create');
      manifestId = manifests[manifests.length - 1].id;
    }

    // Find eval pack
    let evalPackId;
    const evalIdx = args.indexOf('--eval-pack');
    if (evalIdx >= 0) {
      evalPackId = args[evalIdx + 1];
    } else {
      const packs = await listEvalPacks(projectRoot);
      if (packs.length === 0) throw new Error('No eval packs. Run: sdlab eval-pack build');
      evalPackId = packs[packs.length - 1].id;
    }

    console.log(`\x1b[1msdlab eval-run create\x1b[0m — ${projectName}`);
    console.log(`  Manifest:  ${manifestId}`);
    console.log(`  Eval pack: ${evalPackId}`);
    console.log('');

    const result = await createEvalRun(projectRoot, manifestId, evalPackId);
    console.log(`  \x1b[32m✓\x1b[0m Eval run: ${result.evalRunId}`);
    console.log(`  Status: created (use "sdlab eval-run score" to score outputs)`);

  } else if (subcommand === 'score') {
    const evalRunId = args.find(a => a.startsWith('er-'));
    if (!evalRunId) throw new Error('Usage: sdlab eval-run score <eval-run-id> --outputs <path>');

    const outputsIdx = args.indexOf('--outputs');
    if (outputsIdx < 0) throw new Error('--outputs <path> is required (JSONL with record_id, accept, notes)');
    const outputsPath = args[outputsIdx + 1];

    console.log(`\x1b[1msdlab eval-run score\x1b[0m — ${evalRunId}\n`);

    const { scorecard } = await scoreEvalRun(projectRoot, evalRunId, outputsPath);

    const verdict = scorecard.overall_verdict === 'pass'
      ? `\x1b[32mPASS\x1b[0m` : `\x1b[31mFAIL\x1b[0m`;
    console.log(`  Verdict: ${verdict} (${(scorecard.overall_score * 100).toFixed(1)}%)`);
    console.log(`  Outputs: ${scorecard.output_count} (${scorecard.accepted_count} accepted, ${scorecard.rejected_count} rejected)`);
    console.log('');
    console.log('  Tasks:');
    for (const [name, task] of Object.entries(scorecard.tasks)) {
      const status = task.passed ? '\x1b[32m✓\x1b[0m' : '\x1b[31m✗\x1b[0m';
      console.log(`    ${status} ${name.padEnd(24)} ${(task.score * 100).toFixed(1)}%`);
    }

  } else if (subcommand === 'show') {
    const evalRunId = args.find(a => a.startsWith('er-'));
    if (!evalRunId) throw new Error('Usage: sdlab eval-run show <eval-run-id>');

    const run = await loadEvalRun(projectRoot, evalRunId);
    console.log(`\x1b[1mEval run\x1b[0m — ${evalRunId}\n`);
    console.log(`  Created:   ${run.created_at}`);
    console.log(`  Status:    ${run.status}`);
    console.log(`  Manifest:  ${run.training_manifest_id}`);
    console.log(`  Eval pack: ${run.eval_pack_id}`);
    console.log(`  Profile:   ${run.training_profile_id}`);
    console.log(`  Adapter:   ${run.adapter_target}`);

    if (run.scorecard) {
      console.log('');
      console.log(`  Verdict:   ${run.scorecard.overall_verdict.toUpperCase()}`);
      console.log(`  Score:     ${(run.scorecard.overall_score * 100).toFixed(1)}%`);
      console.log(`  Outputs:   ${run.scorecard.output_count} (${run.scorecard.accepted_count} accepted)`);
    }

  } else if (subcommand === 'list') {
    const runs = await listEvalRuns(projectRoot);
    if (runs.length === 0) {
      console.log('No eval runs found. Run: sdlab eval-run create');
      return;
    }
    console.log(`\x1b[1mEval runs\x1b[0m — ${projectName}\n`);
    for (const r of runs) {
      const verdict = r.verdict ? ` verdict=${r.verdict}` : '';
      console.log(`  ${r.id}  manifest=${r.manifest}  status=${r.status}${verdict}  ${r.created_at}`);
    }

  } else {
    throw new Error(`Unknown subcommand: ${subcommand}. Use: create, score, show, list`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('eval-run.js') || process.argv[1].endsWith('eval-run'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
