#!/usr/bin/env node

/**
 * eval-pack.js — Build and inspect canon-aware eval packs.
 *
 * Usage:
 *   sdlab eval-pack build [--project <name>]
 *   sdlab eval-pack list [--project <name>]
 *   sdlab eval-pack show <eval-id> [--project <name>]
 */

import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { buildEvalPack, listEvalPacks, loadEvalPack } from '../lib/eval-pack.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: { project: { type: 'string' } },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);
  const subcommand = positionals[0] || 'list';

  if (subcommand === 'build') {
    console.log(`\x1b[1msdlab eval-pack build\x1b[0m — ${projectName}\n`);

    const result = await buildEvalPack(projectRoot);

    console.log(`  \x1b[32m✓\x1b[0m Eval pack: ${result.evalId}`);
    console.log('');
    console.log('  Tasks:');
    for (const [task, count] of Object.entries(result.tasks)) {
      console.log(`    ${task.padEnd(24)} ${count} records`);
    }
    const total = Object.values(result.tasks).reduce((s, n) => s + n, 0);
    console.log(`    ${'─'.repeat(36)}`);
    console.log(`    ${'total'.padEnd(24)} ${total} records`);

  } else if (subcommand === 'list') {
    const packs = await listEvalPacks(projectRoot);
    if (packs.length === 0) {
      console.log('No eval packs found. Run: sdlab eval-pack build');
      return;
    }
    console.log(`\x1b[1mEval packs\x1b[0m — ${projectName}\n`);
    for (const p of packs) {
      console.log(`  ${p.id}  total=${p.total}  lane=${p.tasks.lane_coverage} drift=${p.tasks.forbidden_drift} gold=${p.tasks.anchor_gold} cont=${p.tasks.subject_continuity}  ${p.created_at}`);
    }

  } else if (subcommand === 'show') {
    const evalId = positionals.find(a => a.startsWith('eval-'));
    if (!evalId) throw inputError('INPUT_MISSING_ARGS', 'Usage: sdlab eval-pack show <eval-id>');

    const manifest = await loadEvalPack(projectRoot, evalId);
    console.log(`\x1b[1mEval pack\x1b[0m — ${evalId}\n`);
    console.log(`  Created: ${manifest.created_at}`);
    console.log(`  Project: ${manifest.project}`);
    console.log('');
    console.log('  Tasks:');
    for (const [task, count] of Object.entries(manifest.task_counts)) {
      console.log(`    ${task.padEnd(24)} ${count} records`);
    }
    console.log(`\n  Total: ${manifest.total_records} records`);

    // Show sample from each task file
    const evalDir = join(projectRoot, 'eval-packs', evalId);
    for (const taskFile of ['lane-coverage', 'forbidden-drift', 'anchor-gold', 'subject-continuity']) {
      const raw = await readFile(join(evalDir, `${taskFile}.jsonl`), 'utf-8');
      const entries = raw.trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
      if (entries.length > 0) {
        console.log(`\n  ${taskFile} (first 3):`);
        for (const entry of entries.slice(0, 3)) {
          const summary = entry.record_id || entry.subject_name;
          const detail = entry.pass_ratio != null ? `ratio=${entry.pass_ratio}` :
            entry.violations ? `violations=${entry.violations.length}` :
              `records=${entry.record_count}`;
          console.log(`    ${summary}  ${detail}`);
        }
      }
    }

  } else {
    throw inputError('INPUT_BAD_SUBCOMMAND', `Unknown subcommand: ${subcommand}. Use: build, list, show`);
  }
}

if (process.argv[1] && (process.argv[1].endsWith('eval-pack.js') || process.argv[1].endsWith('eval-pack'))) {
  run().catch(handleCliError);
}
