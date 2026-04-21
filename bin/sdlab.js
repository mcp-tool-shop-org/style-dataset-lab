#!/usr/bin/env node

/**
 * sdlab — CLI entry point for Style Dataset Lab.
 *
 * Thin dispatcher that routes subcommands to existing scripts.
 * Each script exports run(argv) and is lazy-loaded on demand.
 */

import { enableDebug, handleCliError, inputError } from '../lib/errors.js';
import { setLogLevel } from '../lib/log.js';
import { findClosest } from '../lib/args.js';

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

// ─── Per-command help ─────────────────────────────────────────────────
//
// Keyed by the user-facing command (including two-word forms joined by
// a space). Help text is plain — no color codes — to stay readable in
// dumb terminals and when piped to files.

const HELP_TEXT = {
  'init': `sdlab init <project-name> [--domain <domain>]

Scaffold a new project from a domain template.

Positional:
  project-name         Lowercase, hyphen-separated (e.g. "my-project")

Flags:
  --domain <id>        Domain template (default: generic)

Examples:
  sdlab init my-project
  sdlab init heist-crew --domain character-design

Run "sdlab init" with no arguments to see the available domains.`,

  'project doctor': `sdlab project doctor --project <name>

Validate project config and directory structure. Reports missing
required files, unmigrated record schemas, and orphaned outputs.

Flags:
  --project <name>     Project to audit (required in practice)
  --verbose            Show per-check detail
  --quiet              Only print PASS / FAIL summary`,

  'generate': `sdlab generate [<pack-path>] --project <name> [--dry-run]

Generate candidates from a prompt pack (JSON file under
projects/<name>/inputs/prompts/).

Positional:
  pack-path            Path to the prompt pack (default: inputs/prompts/rpg-icons-lane1.json)

Flags:
  --project <name>     Project to operate on
  --dry-run            Preview work without contacting ComfyUI

Env:
  COMFY_URL            ComfyUI HTTP endpoint (default: http://127.0.0.1:8188)

Precedence: CLI flag > env COMFY_URL > project defaults > built-in default.`,

  'batch generate': `sdlab batch generate --mode <id> [--subject <id>] [--theme <label>] --project <name>

Execute a batch production mode (expression sheet, silhouette pack,
environment board, etc).

Flags:
  --mode <id>          Batch mode id (required)
  --subject <id>       Subject for subject-driven modes
  --theme <label>      Theme label for environment modes
  --asset <id>         Training asset reference
  --project <name>     Project to operate on
  --dry-run            Prepare batch without submitting to ComfyUI
  --json               Output manifest as JSON`,

  'brief compile': `sdlab brief compile --profile <id> --project <name>

Compile a generation brief from project canon (constitution, lanes,
workflow profile).

Flags:
  --profile <id>       Workflow profile id to compile against
  --project <name>     Project to operate on
  --out <path>         Optional explicit output path`,

  'run generate': `sdlab run generate --brief <id> --project <name> [--dry-run]

Execute a compiled brief through ComfyUI.

Flags:
  --brief <id>         Brief id to execute (required)
  --project <name>     Project to operate on
  --dry-run            Plan without submitting to ComfyUI`,

  'critique': `sdlab critique --run <id> --project <name>

Critique a completed run. Writes a critique record alongside the run.

Flags:
  --run <id>           Run id to critique (required)
  --project <name>     Project to operate on
  --json               Emit critique as JSON on stdout`,

  'refine': `sdlab refine --run <id> --pick <file> --project <name>

Generate a refined next-pass brief based on a specific pick from a
prior run.

Flags:
  --run <id>           Source run id (required)
  --pick <file>        Picked output filename inside the run (required)
  --project <name>     Project to operate on`,

  'batch sheet': `sdlab batch sheet <batch-id> --project <name>

Re-render a batch's contact sheet from its manifest.

Positional:
  batch-id             Batch id to re-render

Flags:
  --project <name>     Project to operate on`,

  'select': `sdlab select [--run <id>|--batch <id>] --approve <files> --project <name>

Select approved outputs from a run or batch.

Flags:
  --run <id>           Source run id
  --batch <id>         Source batch id
  --approve <files>    Comma-separated output filenames to approve
  --project <name>     Project to operate on`,

  'curate': `sdlab curate <asset_id> <approved|rejected|borderline> <explanation> [--scores k:v,...] [--failures f1,f2] --project <name>

Record a judgment on a candidate and move it to the matching outputs
subdirectory.

Positional:
  asset_id             Candidate asset id
  status               approved | rejected | borderline
  explanation          Short reason (quoted)

Flags:
  --scores k:v,...     Per-dimension scores (e.g. silhouette:0.9,palette:0.8)
  --failures f1,f2     Named failure tags (comma-separated)
  --notes "…"          Optional free-form note
  --list               Print uncurated candidates and exit
  --dry-run            Preview without moving files
  --project <name>     Project to operate on`,

  'canon-bind': `sdlab canon-bind --project <name> [--lane <id>]

Bind approved records to constitution rules.

Flags:
  --project <name>     Project to operate on
  --lane <id>          Restrict binding to a single lane`,

  'snapshot': `sdlab snapshot <create|list|show|diff> [args] --project <name>

Manage frozen dataset snapshots.

Subcommands:
  create               Create a new snapshot from approved records
  list                 List all snapshots (default subcommand)
  show <id>            Show snapshot details
  diff <a> <b>         Compare two snapshots

Flags:
  --profile <name>     Selection profile (create only)
  --project <name>     Project to operate on
  --dry-run            Preview snapshot contents without writing`,

  'split': `sdlab split <build|list|show|audit> [args] --project <name>

Manage train/val/test splits from a snapshot.

Subcommands:
  build                Build a split from a snapshot
  list                 List all splits
  show <id>            Show split details
  audit <id>           Audit a split for leakage and balance

Flags:
  --project <name>     Project to operate on`,

  'export': `sdlab export <build|list> [args] --project <name>

Build and list self-contained export packages.

Subcommands:
  build                Build a new export package
  list                 List all export packages

Flags:
  --project <name>     Project to operate on`,
};

// "bind" is a short alias for "canon-bind" — share help.
HELP_TEXT['bind'] = HELP_TEXT['canon-bind'];

function printCommandHelp(key) {
  const text = HELP_TEXT[key];
  if (!text) return false;
  console.log(text);
  return true;
}

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
  console.log('  canon-bind           Bind approved records to constitution rules');
  console.log('                       ("bind" is a short alias for canon-bind)');
  console.log('  painterly            Post-processing painterly style pass');
  console.log('  painterly:test       Calibrate painterly denoise level on sample images');
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
  console.log('  reingest generated --source <dir> --manifest <id>  Re-ingest generated outputs');
  console.log('  reingest selected --selection <id> Re-ingest selected outputs as records');
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
  console.log('  --project <name>     Project to operate on (no default — fallback to "star-freight" with warning)');
  console.log('  --game <name>        Deprecated alias for --project');
  console.log('  --debug              Show stack traces on error');
  console.log('  --verbose            Verbose output');
  console.log('  --quiet              Suppress non-essential output');
  console.log('  --dry-run            Preview changes without writing (where supported)');
  console.log('  --help               Show this help (or per-command help with "sdlab <cmd> --help")');
  console.log('');
  console.log('Examples:');
  console.log('  sdlab init my-project --domain character-design');
  console.log('  sdlab generate --help');
  console.log('  sdlab snapshot create --project star-freight');
  console.log('  sdlab split build --dry-run --project star-freight');
  console.log('  sdlab training-package build --debug --project star-freight');
}

// All top-level command tokens users can type (including two-word heads).
function allKnownCommands() {
  const oneWord = Object.keys(COMMANDS);
  const heads = ['project', 'workflow', 'brief', 'run', 'critique', 'refine', 'batch', 'select', 'selection'];
  return [...new Set([...oneWord, ...heads])];
}

function argvHasHelp(argv) {
  return argv.includes('--help') || argv.includes('-h');
}

// ─── Signal + fatal-error handlers ────────────────────────────────────

function installProcessHandlers() {
  const onSignal = (sig) => {
    const code = sig === 'SIGINT' ? 130 : 143;
    process.stderr.write(`\n\x1b[31m✗ Interrupted by ${sig}. Partial output may exist.\x1b[0m\n`);
    process.exit(code);
  };
  process.on('SIGINT', () => onSignal('SIGINT'));
  process.on('SIGTERM', () => onSignal('SIGTERM'));

  process.on('uncaughtException', (err) => {
    handleCliError(err);
    // handleCliError exits, but guard anyway.
    process.exit(2);
  });
  process.on('unhandledRejection', (reason) => {
    const err = reason instanceof Error ? reason : new Error(String(reason));
    handleCliError(err);
    process.exit(2);
  });
}

async function main() {
  installProcessHandlers();

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

  // ── Two-word dispatch tables and --help interception ──
  // For every two-word namespace, we check "cmd sub --help" first,
  // then the single-word "cmd --help", then fall through to dispatch.

  const twoWord = (head, table) => ({ head, table });
  const namespaces = [
    twoWord('project', PROJECT_COMMANDS),
    twoWord('workflow', WORKFLOW_COMMANDS),
    twoWord('brief', BRIEF_COMMANDS),
    twoWord('run', RUN_COMMANDS),
    twoWord('batch', BATCH_COMMANDS),
    twoWord('selection', SELECTION_COMMANDS),
  ];

  // "project", "workflow", "brief", "run", "batch", "selection" two-word forms
  for (const { head, table } of namespaces) {
    if (command === head && args[1] && table[args[1]]) {
      commandArgs = args.slice(2);
      const twoWordKey = `${head} ${args[1]}`;
      if (argvHasHelp(commandArgs) && printCommandHelp(twoWordKey)) return;
      const mod = await import(table[args[1]]);
      await mod.run(commandArgs);
      return;
    }
  }

  // "critique" — bare or "critique show"
  if (command === 'critique') {
    if (args[1] && CRITIQUE_COMMANDS[args[1]]) {
      commandArgs = args.slice(2);
      if (argvHasHelp(commandArgs) && printCommandHelp(`critique ${args[1]}`)) return;
      const mod = await import(CRITIQUE_COMMANDS[args[1]]);
      await mod.run(commandArgs);
      return;
    }
    if (argvHasHelp(commandArgs) && printCommandHelp('critique')) return;
    const mod = await import('../scripts/critique.js');
    await mod.run(commandArgs);
    return;
  }

  // "refine" — single command
  if (command === 'refine') {
    if (argvHasHelp(commandArgs) && printCommandHelp('refine')) return;
    const mod = await import('../scripts/refine.js');
    await mod.run(commandArgs);
    return;
  }

  // "select" — single command
  if (command === 'select') {
    if (argvHasHelp(commandArgs) && printCommandHelp('select')) return;
    const mod = await import('../scripts/select.js');
    await mod.run(commandArgs);
    return;
  }

  const modulePath = COMMANDS[command];
  if (!modulePath) {
    const suggestion = findClosest(command, allKnownCommands());
    const hint = suggestion
      ? `Did you mean "${suggestion}"? (Run "sdlab --help" for all commands.)`
      : 'Run "sdlab --help" for available commands.';
    throw inputError('INPUT_UNKNOWN_COMMAND', `Unknown command: ${command}`, hint);
  }

  // Per-command --help for one-word commands
  if (argvHasHelp(commandArgs) && printCommandHelp(command)) return;

  const mod = await import(modulePath);
  await mod.run(commandArgs);
}

main().catch(handleCliError);
