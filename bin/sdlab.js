#!/usr/bin/env node

/**
 * sdlab — CLI entry point for Style Dataset Lab.
 *
 * Thin dispatcher that routes subcommands to existing scripts.
 * Each script exports run(argv) and is lazy-loaded on demand.
 */

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
};

// Two-word commands under "project" namespace
const PROJECT_COMMANDS = {
  'doctor':  '../scripts/doctor.js',
  'migrate': '../scripts/migrate-records.js',
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
  console.log('Options:');
  console.log('  --project <name>     Project to operate on (default: star-freight)');
  console.log('  --game <name>        Deprecated alias for --project');
  console.log('  --help               Show this help');
  console.log('');
  console.log('Examples:');
  console.log('  sdlab init my-project --domain character-design');
  console.log('  sdlab generate inputs/prompts/wave1.json --project star-freight');
  console.log('  sdlab bind --stats --project star-freight');
  console.log('  sdlab project doctor --project star-freight');
}

async function main() {
  const args = process.argv.slice(2);

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
    try {
      const mod = await import(modulePath);
      await mod.run(commandArgs);
    } catch (err) {
      console.error(`\x1b[31mError:\x1b[0m ${err.message}`);
      process.exit(1);
    }
    return;
  }

  const modulePath = COMMANDS[command];
  if (!modulePath) {
    console.error(`Unknown command: ${command}`);
    console.error(`Run "sdlab --help" for available commands.`);
    process.exit(1);
  }

  try {
    const mod = await import(modulePath);
    await mod.run(commandArgs);
  } catch (err) {
    console.error(`\x1b[31mError:\x1b[0m ${err.message}`);
    process.exit(1);
  }
}

main();
