#!/usr/bin/env node

/**
 * sdlab — CLI entry point for Style Dataset Lab.
 *
 * Thin dispatcher that routes subcommands to existing scripts.
 * Each script exports run(argv) and is lazy-loaded on demand.
 */

import { enableDebug, handleCliError, inputError } from '../lib/errors.js';
import { setLogLevel } from '../lib/log.js';

const COMMANDS = {
  'init':                '../scripts/init.js',
  'generate':            '../scripts/generate.js',
  'generate:identity':   '../scripts/generate-identity.js',
  'generate:controlnet': '../scripts/generate-controlnet.js',
  'generate:ipadapter':  '../scripts/generate-ipadapter.js',
  'curate':              '../scripts/curate.js',
  'compare':             '../scripts/compare.js',
  'bind':                '../scripts/canon-bind.js',
  'canon-bind':          '../scripts/canon-bind.js',
  'painterly':           '../scripts/painterly.js',
  'painterly:test':      '../scripts/painterly-test.js',
  'migrate':             '../scripts/migrate-records.js',
  'snapshot':            '../scripts/snapshot.js',
  'eligibility':         '../scripts/eligibility.js',
  'split':               '../scripts/split.js',
  'card':                '../scripts/card.js',
  'export':              '../scripts/export.js',
  'eval-pack':           '../scripts/eval-pack.js',
  'training-profile':    '../scripts/training-profile.js',
  'training-manifest':   '../scripts/training-manifest.js',
  'training-package':    '../scripts/training-package.js',
  'eval-run':            '../scripts/eval-run.js',
  'implementation-pack': '../scripts/implementation-pack.js',
  'reingest':            '../scripts/reingest.js',
};

// Two-word commands under "project" namespace
const PROJECT_COMMANDS = {
  'doctor':  '../scripts/doctor.js',
  'migrate': '../scripts/migrate-records.js',
};

// Two-word commands under "workflow" namespace
const WORKFLOW_COMMANDS = {
  'list': '../scripts/workflow-list.js',
  'show': '../scripts/workflow-show.js',
};

// Two-word commands under "brief" namespace
const BRIEF_COMMANDS = {
  'compile': '../scripts/brief-compile.js',
  'show':    '../scripts/brief-show.js',
};

// Two-word commands under "run" namespace
const RUN_COMMANDS = {
  'generate': '../scripts/run-generate.js',
  'show':     '../scripts/run-show.js',
  'list':     '../scripts/run-list.js',
};

// Two-word commands under "critique" namespace
const CRITIQUE_COMMANDS = {
  'show': '../scripts/critique-show.js',
};

// Two-word commands under "batch" namespace
const BATCH_COMMANDS = {
  'generate': '../scripts/batch-generate.js',
  'show':     '../scripts/batch-show.js',
  'sheet':    '../scripts/batch-sheet.js',
};

// Two-word commands under "selection" namespace
const SELECTION_COMMANDS = {
  'show': '../scripts/selection-show.js',
};

function printHelp() {
  console.log(`\x1b[1msdlab\x1b[0m — Style Dataset Lab CLI\n`);
  console.log('Usage: sdlab <command> [options]\n');
  console.log('Project:');
  console.log('  init <name>          Scaffold a new project from a domain template');
  console.log('  project doctor       Validate project config and structure');
  console.log('  project migrate      Migrate record schemas');
  console.log('');
  console.log('Pipeline:');
  console.log('  generate             Generate candidates from a prompt pack');
  console.log('  generate:identity    Generate named-subject identity images');
  console.log('  generate:controlnet  ControlNet-guided structural generation');
  console.log('  generate:ipadapter   IP-Adapter reference-guided generation');
  console.log('  curate               Move candidate to approved/rejected/borderline');
  console.log('  compare              Record pairwise A-vs-B comparison');
  console.log('  bind                 Bind approved records to constitution rules');
  console.log('  painterly            Post-processing painterly style pass');
  console.log('  painterly:test       Test denoise levels on reference images');
  console.log('');
  console.log('Dataset:');
  console.log('  snapshot create      Create a frozen dataset snapshot');
  console.log('  snapshot list        List all snapshots');
  console.log('  snapshot show <id>   Show snapshot details');
  console.log('  snapshot diff <a> <b> Compare two snapshots');
  console.log('  eligibility audit    Audit record training eligibility');
  console.log('  split build          Build train/val/test split from snapshot');
  console.log('  split list           List all splits');
  console.log('  split show <id>      Show split details');
  console.log('  split audit <id>     Audit split for leakage and balance');
  console.log('  card generate        Generate dataset card (markdown + JSON)');
  console.log('  export build         Build self-contained export package');
  console.log('  export list          List all export packages');
  console.log('  eval-pack build      Build canon-aware eval pack');
  console.log('  eval-pack list       List eval packs');
  console.log('  eval-pack show <id>  Show eval pack details');
  console.log('');
  console.log('Training:');
  console.log('  training-profile list              List training profiles');
  console.log('  training-profile show <id>         Show training profile');
  console.log('  training-manifest create            Create training manifest');
  console.log('  training-manifest validate <id>     Validate manifest integrity');
  console.log('  training-manifest show <id>         Show manifest details');
  console.log('  training-manifest list              List all manifests');
  console.log('  training-package build              Build trainer-ready package');
  console.log('  training-package show <id>          Show package details');
  console.log('  training-package list               List all packages');
  console.log('  eval-run create                    Create eval run');
  console.log('  eval-run score <id> --outputs <p>  Score against eval pack');
  console.log('  eval-run show <id>                 Show eval run details');
  console.log('  eval-run list                      List all eval runs');
  console.log('  implementation-pack build           Build implementation example pack');
  console.log('  implementation-pack show <id>       Show pack details');
  console.log('  implementation-pack list            List all packs');
  console.log('  reingest generated --source <dir>  Re-ingest generated outputs');
  console.log('  reingest audit                     Audit re-ingested record status');
  console.log('');
  console.log('Production:');
  console.log('  workflow list                      List workflow profiles');
  console.log('  workflow show <id>                 Show workflow profile details');
  console.log('  brief compile                      Compile generation brief from project truth');
  console.log('  brief show <id>                    Show compiled brief');
  console.log('  run generate --brief <id>          Execute brief through ComfyUI');
  console.log('  run show <id>                      Show run details');
  console.log('  run list                           List all runs');
  console.log('  critique --run <id>                Critique a completed run');
  console.log('  critique show --run <id>           Show saved critique');
  console.log('  refine --run <id> --pick <file>    Generate refined next-pass brief');
  console.log('  batch generate --mode <id>         Execute a batch production mode');
  console.log('  batch show [batch-id]              List batches or show details');
  console.log('  batch sheet <batch-id>             Re-render batch sheet from manifest');
  console.log('  select --run <id> --approve <files> Select approved outputs from a run');
  console.log('  select --batch <id> --approve ...   Select approved outputs from a batch');
  console.log('  selection show [selection-id]       List selections or show details');
  console.log('  reingest selected --selection <id>  Re-ingest selected outputs as records');
  console.log('');
  console.log('Options:');
  console.log('  --project <name>     Project to operate on (default: star-freight)');
  console.log('  --game <name>        Deprecated alias for --project');
  console.log('  --debug              Show stack traces on error');
  console.log('  --verbose            Verbose output');
  console.log('  --quiet              Suppress non-essential output');
  console.log('  --dry-run            Preview changes without writing (where supported)');
  console.log('  --help               Show this help');
  console.log('');
  console.log('Examples:');
  console.log('  sdlab init my-project --domain character-design');
  console.log('  sdlab snapshot create --project star-freight');
  console.log('  sdlab split build --dry-run --project star-freight');
  console.log('  sdlab training-package build --debug --project star-freight');
}

async function main() {
  const args = process.argv.slice(2);

  // Global flags
  if (args.includes('--debug')) enableDebug();
  if (args.includes('--verbose')) setLogLevel('verbose');
  if (args.includes('--quiet')) setLogLevel('quiet');

  if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
    printHelp();
    process.exit(0);
  }

  let command = args[0];
  let commandArgs = args.slice(1);

  // Handle "project <subcommand>" two-word form
  if (command === 'project' && args[1] && PROJECT_COMMANDS[args[1]]) {
    commandArgs = args.slice(2);
    const modulePath = PROJECT_COMMANDS[args[1]];
    const mod = await import(modulePath);
    await mod.run(commandArgs);
    return;
  }

  // Handle "workflow <subcommand>" two-word form
  if (command === 'workflow' && args[1] && WORKFLOW_COMMANDS[args[1]]) {
    commandArgs = args.slice(2);
    const modulePath = WORKFLOW_COMMANDS[args[1]];
    const mod = await import(modulePath);
    await mod.run(commandArgs);
    return;
  }

  // Handle "brief <subcommand>" two-word form
  if (command === 'brief' && args[1] && BRIEF_COMMANDS[args[1]]) {
    commandArgs = args.slice(2);
    const modulePath = BRIEF_COMMANDS[args[1]];
    const mod = await import(modulePath);
    await mod.run(commandArgs);
    return;
  }

  // Handle "run <subcommand>" two-word form
  if (command === 'run' && args[1] && RUN_COMMANDS[args[1]]) {
    commandArgs = args.slice(2);
    const modulePath = RUN_COMMANDS[args[1]];
    const mod = await import(modulePath);
    await mod.run(commandArgs);
    return;
  }

  // Handle "critique" — bare or "critique show" two-word form
  if (command === 'critique') {
    if (args[1] && CRITIQUE_COMMANDS[args[1]]) {
      commandArgs = args.slice(2);
      const modulePath = CRITIQUE_COMMANDS[args[1]];
      const mod = await import(modulePath);
      await mod.run(commandArgs);
      return;
    }
    // Bare "critique" → generate critique
    const mod = await import('../scripts/critique.js');
    await mod.run(commandArgs);
    return;
  }

  // Handle "refine" — single command
  if (command === 'refine') {
    const mod = await import('../scripts/refine.js');
    await mod.run(commandArgs);
    return;
  }

  // Handle "batch <subcommand>" two-word form
  if (command === 'batch' && args[1] && BATCH_COMMANDS[args[1]]) {
    commandArgs = args.slice(2);
    const modulePath = BATCH_COMMANDS[args[1]];
    const mod = await import(modulePath);
    await mod.run(commandArgs);
    return;
  }

  // Handle "select" — single command
  if (command === 'select') {
    const mod = await import('../scripts/select.js');
    await mod.run(commandArgs);
    return;
  }

  // Handle "selection <subcommand>" two-word form
  if (command === 'selection' && args[1] && SELECTION_COMMANDS[args[1]]) {
    commandArgs = args.slice(2);
    const modulePath = SELECTION_COMMANDS[args[1]];
    const mod = await import(modulePath);
    await mod.run(commandArgs);
    return;
  }

  const modulePath = COMMANDS[command];
  if (!modulePath) {
    throw inputError('INPUT_UNKNOWN_COMMAND', `Unknown command: ${command}`, 'Run "sdlab --help" for available commands.');
  }

  const mod = await import(modulePath);
  await mod.run(commandArgs);
}

main().catch(handleCliError);
