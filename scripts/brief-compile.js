#!/usr/bin/env node

/**
 * brief-compile.js — Compile a generation brief from project truth.
 *
 * Usage:
 *   sdlab brief compile --project star-freight --workflow character-portrait-set --subject kael_maren
 *   sdlab brief compile --project star-freight --workflow environment-moodboard
 *   sdlab brief compile --project star-freight --workflow character-portrait-set --subject kael_maren --reference sf_001,sf_018
 *   sdlab brief compile --project star-freight --workflow character-portrait-set --subject kael_maren --output-count 8 --json
 */

import { parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { compileBrief, saveCompiledBrief } from '../lib/brief-compiler.js';
import { info } from '../lib/log.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      workflow: { type: 'string' },
      subject: { type: 'string' },
      asset: { type: 'string' },
      'implementation-pack': { type: 'string' },
      reference: { type: 'string' },
      'output-count': { type: 'string' },
      width: { type: 'string' },
      height: { type: 'string' },
      steps: { type: 'string' },
      cfg: { type: 'string' },
      sampler: { type: 'string' },
      'seed-mode': { type: 'string' },
      json: { type: 'boolean' },
      'dry-run': { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.workflow) {
    console.log('Usage: sdlab brief compile --workflow <id> [--subject <id>] [--project <name>]');
    console.log('');
    console.log('Options:');
    console.log('  --workflow <id>         Workflow profile to use (required)');
    console.log('  --subject <id>          Subject ID for subject-driven workflows');
    console.log('  --asset <id>            Training asset reference');
    console.log('  --implementation-pack <id>  Implementation pack reference');
    console.log('  --reference <ids>       Comma-separated reference record IDs');
    console.log('  --output-count <n>      Override output count');
    console.log('  --width <px>            Override width');
    console.log('  --height <px>           Override height');
    console.log('  --steps <n>             Override steps');
    console.log('  --cfg <n>               Override CFG scale');
    console.log('  --sampler <name>        Override sampler');
    console.log('  --seed-mode <mode>      Override seed mode (fixed|increment|random)');
    console.log('  --json                  Output raw JSON');
    console.log('  --dry-run               Preview without saving');
    return;
  }

  const projectName = flags.project;
  const projectRoot = getProjectRoot(projectName);

  // Parse reference IDs
  const referenceIds = flags.reference
    ? flags.reference.split(',').map(s => s.trim()).filter(Boolean)
    : undefined;

  // Parse overrides
  const overrides = {};
  if (flags['output-count']) overrides.output_count = parseInt(flags['output-count'], 10);
  if (flags.width) overrides.width = parseInt(flags.width, 10);
  if (flags.height) overrides.height = parseInt(flags.height, 10);
  if (flags.steps) overrides.steps = parseInt(flags.steps, 10);
  if (flags.cfg) overrides.cfg = parseFloat(flags.cfg);
  if (flags.sampler) overrides.sampler = flags.sampler;
  if (flags['seed-mode']) overrides.seed_mode = flags['seed-mode'];

  const brief = await compileBrief({
    projectRoot,
    projectId: projectName,
    workflowId: flags.workflow,
    subjectId: flags.subject,
    assetRef: flags.asset,
    implementationPackRef: flags['implementation-pack'],
    referenceIds,
    overrides,
  });

  if (flags.json) {
    console.log(JSON.stringify(brief, null, 2));
    if (!flags['dry-run']) {
      await saveCompiledBrief(projectRoot, brief);
    }
    return;
  }

  if (!flags['dry-run']) {
    const { jsonPath, mdPath } = await saveCompiledBrief(projectRoot, brief);
    info(`\x1b[1msdlab brief compile\x1b[0m — ${projectName}\n`);
    info(`  Brief ID:   ${brief.brief_id}`);
    info(`  Workflow:   ${brief.workflow_id}`);
    info(`  Lane:       ${brief.lane_id}`);
    if (brief.subject_id) info(`  Subject:    ${brief.subject_id}`);
    info(`  Outputs:    ${brief.expected_outputs.output_count}× ${brief.expected_outputs.output_mode}`);
    info('');
    info(`  Saved: ${jsonPath}`);
    info(`         ${mdPath}`);
  } else {
    info(`\x1b[1msdlab brief compile\x1b[0m — dry run\n`);
    info(`  Brief ID:   ${brief.brief_id}`);
    info(`  Workflow:   ${brief.workflow_id}`);
    info(`  Lane:       ${brief.lane_id}`);
    if (brief.subject_id) info(`  Subject:    ${brief.subject_id}`);
    info(`  Outputs:    ${brief.expected_outputs.output_count}× ${brief.expected_outputs.output_mode}`);
    info('');
    info('  Prompt:');
    info(`    ${brief.prompt}`);
    info('');
    info('  Negative:');
    info(`    ${brief.negative_prompt}`);
    info('');
    if (brief.drift_warnings?.length > 0) {
      info('  Drift warnings:');
      for (const w of brief.drift_warnings) {
        info(`    \x1b[33m⚠\x1b[0m ${w}`);
      }
    }
  }
}

if (process.argv[1] && (process.argv[1].endsWith('brief-compile.js') || process.argv[1].endsWith('brief-compile'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
