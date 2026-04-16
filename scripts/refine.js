#!/usr/bin/env node

/**
 * refine.js — Generate a refined next-pass brief from critique.
 *
 * Usage:
 *   sdlab refine --project star-freight --run run_2026-04-15_001 --pick 003.png
 *   sdlab refine --run run_2026-04-15_001 --pick 003.png --push "stronger faction read" --suppress "extra ornament"
 *   sdlab refine --run run_2026-04-15_001 --pick 003.png --json
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseArgs } from '../lib/args.js';
import { getProjectRoot, getRunsDir } from '../lib/paths.js';
import { loadCritique } from '../lib/critique-engine.js';
import {
  extractDelta,
  buildRefinedBrief,
  saveRefinedBrief,
  renderRefinedBriefMarkdown,
} from '../lib/refine-briefs.js';
import { info } from '../lib/log.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      run: { type: 'string' },
      pick: { type: 'string' },
      preserve: { type: 'string' },
      push: { type: 'string' },
      suppress: { type: 'string' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.run || !flags.pick) {
    console.log('Usage: sdlab refine --run <id> --pick <filename> [--project <name>]');
    console.log('');
    console.log('Options:');
    console.log('  --run <id>             Run to refine from (required)');
    console.log('  --pick <filename>      Candidate filename to refine from (required)');
    console.log('  --preserve <notes>     Comma-separated preserve instructions');
    console.log('  --push <notes>         Comma-separated push instructions');
    console.log('  --suppress <notes>     Comma-separated suppress instructions');
    console.log('  --json                 Output raw JSON');
    return;
  }

  const projectName = flags.project;
  const projectRoot = getProjectRoot(projectName);
  const runId = flags.run;
  const pickedFilename = flags.pick;

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m refine`);
  console.log(`  Project: ${projectName}`);
  console.log(`  Run: ${runId}`);
  console.log(`  Picked: ${pickedFilename}`);
  console.log('');

  // Load critique
  const critique = loadCritique(projectRoot, runId);

  // Load parent brief from the run
  const runDir = join(getRunsDir(projectRoot), runId);
  const parentBrief = JSON.parse(readFileSync(join(runDir, 'brief.json'), 'utf-8'));

  // Parse CLI delta overrides
  const cliOverrides = {
    preserve: flags.preserve ? flags.preserve.split(',').map(s => s.trim()).filter(Boolean) : [],
    push: flags.push ? flags.push.split(',').map(s => s.trim()).filter(Boolean) : [],
    suppress: flags.suppress ? flags.suppress.split(',').map(s => s.trim()).filter(Boolean) : [],
  };

  // Extract delta from critique + overrides
  const delta = extractDelta(critique, pickedFilename, cliOverrides);

  // Build refined brief
  const refineDir = join(runDir, 'refine');
  const refinedBrief = buildRefinedBrief({
    parentBrief,
    critique,
    pickedCandidate: pickedFilename,
    delta,
    runId,
    refineDir,
  });

  // Save
  const { jsonPath, mdPath } = await saveRefinedBrief(projectRoot, runId, refinedBrief);

  if (flags.json) {
    console.log(JSON.stringify(refinedBrief, null, 2));
  } else {
    console.log(`Refined brief: ${refinedBrief.brief_id}`);
    console.log(`Parent: ${refinedBrief.parent_brief_id}`);
    console.log(`Source: ${runId} → ${pickedFilename}`);
    console.log('');

    if (delta.preserve.length > 0) {
      console.log('Preserve:');
      for (const p of delta.preserve) console.log(`  ✓ ${p}`);
    }
    if (delta.push.length > 0) {
      console.log('Push:');
      for (const p of delta.push) console.log(`  → ${p}`);
    }
    if (delta.suppress.length > 0) {
      console.log('Suppress:');
      for (const s of delta.suppress) console.log(`  ✗ ${s}`);
    }

    console.log('');
    info(`Saved: runs/${runId}/refine/${refinedBrief.brief_id}.json`);
    info(`Next: sdlab run generate --brief ${refinedBrief.brief_id} (from refine dir)`);
  }
}
