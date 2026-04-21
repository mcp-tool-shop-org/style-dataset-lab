#!/usr/bin/env node

/**
 * init.js — Scaffold a new project from a domain template.
 *
 * Usage:
 *   sdlab init my-project --domain character-design
 *   sdlab init my-project                              # uses 'generic' domain
 *   node scripts/init.js my-project --domain game-art
 */

import { mkdir, readdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import { join, basename } from 'node:path';
import { existsSync } from 'node:fs';
import { REPO_ROOT } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';

const TEMPLATES_DIR = join(REPO_ROOT, 'templates');
const PROJECTS_DIR = join(REPO_ROOT, 'projects');

const PROJECT_DIRS = [
  'canon',
  'records',
  'comparisons',
  'inputs/prompts',
  'inputs/identity-packets',
  'inputs/references',
  'inputs/control-guides',
  'outputs/candidates',
  'outputs/approved',
  'outputs/rejected',
  'outputs/borderline',
  'outputs/painterly',
  'outputs/painterly-test',
  'exports',
  'snapshots',
  'splits',
  'eval-packs',
  'training/profiles',
  'training/manifests',
  'training/packages',
  'training/eval-runs',
  'training/implementations',
  'workflows/profiles',
  'workflows/batch-modes',
  'briefs',
  'runs',
  'batches',
  'selections',
  'inbox/generated',
];

function isValidName(name) {
  return /^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(name) || /^[a-z0-9]$/.test(name);
}

async function listDomains() {
  const domainsDir = join(TEMPLATES_DIR, 'domains');
  if (!existsSync(domainsDir)) return [];
  const entries = await readdir(domainsDir, { withFileTypes: true });
  return entries.filter(e => e.isDirectory()).map(e => e.name);
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = argv.find(a => !a.startsWith('--'));

  // Parse --domain
  let domain = 'generic';
  const domainIdx = argv.indexOf('--domain');
  if (domainIdx >= 0 && argv[domainIdx + 1]) {
    domain = argv[domainIdx + 1];
  }

  if (!projectName) {
    const domains = await listDomains();
    console.log('Usage: sdlab init <project-name> [--domain <domain>]\n');
    console.log('Available domains:');
    console.log('  generic              Minimal starter (default)');
    for (const d of domains) {
      console.log(`  ${d.padEnd(20)} Domain-specific starter`);
    }
    return;
  }

  if (!isValidName(projectName)) {
    throw inputError(
      'INPUT_BAD_NAME',
      `Invalid project name "${projectName}".`,
      `Use lowercase letters, numbers, and hyphens (e.g. "my-project").`
    );
  }

  // Validate --domain to prevent path traversal via template lookup.
  if (!isValidName(domain)) {
    throw inputError(
      'INPUT_BAD_DOMAIN',
      `Invalid --domain "${domain}".`,
      `Use lowercase letters, numbers, and hyphens (e.g. "character-design").`
    );
  }

  const projectDir = join(PROJECTS_DIR, projectName);
  if (existsSync(projectDir)) {
    throw inputError(
      'INPUT_PROJECT_EXISTS',
      `Project "${projectName}" already exists at ${projectDir}`
    );
  }

  // Resolve domain template source
  let domainDir = null;
  if (domain !== 'generic') {
    domainDir = join(TEMPLATES_DIR, 'domains', domain);
    if (!existsSync(domainDir)) {
      const domains = await listDomains();
      throw inputError(
        'INPUT_UNKNOWN_DOMAIN',
        `Domain "${domain}" not found.`,
        `Available: generic, ${domains.join(', ')}`
      );
    }
  }

  console.log(`\x1b[1msdlab init\x1b[0m`);
  console.log(`  Project: ${projectName}`);
  console.log(`  Domain:  ${domain}`);
  console.log(`  Path:    ${projectDir}`);
  console.log('');

  // Create directory structure
  for (const dir of PROJECT_DIRS) {
    await mkdir(join(projectDir, dir), { recursive: true });
  }
  console.log(`  \x1b[32m✓\x1b[0m Created ${PROJECT_DIRS.length} directories`);

  // Copy config files from domain template or generate generic ones
  const configFiles = ['project.json', 'constitution.json', 'lanes.json', 'rubric.json', 'terminology.json'];

  if (domainDir) {
    for (const file of configFiles) {
      const src = join(domainDir, file);
      if (existsSync(src)) {
        let content = await readFile(src, 'utf-8');
        // Replace template project name
        if (file === 'project.json') {
          const parsed = JSON.parse(content);
          parsed.name = projectName;
          content = JSON.stringify(parsed, null, 2) + '\n';
        }
        await writeFile(join(projectDir, file), content);
        console.log(`  \x1b[32m✓\x1b[0m ${file} (from ${domain} template)`);
      }
    }
  } else {
    // Generic starters
    await writeFile(join(projectDir, 'project.json'), JSON.stringify({
      name: projectName,
      display_name: projectName.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      domain: 'generic',
      version: '0.1.0',
      defaults: {
        checkpoint: '',
        loras: [],
        width: 1024,
        height: 1024,
        steps: 8,
        cfg: 2.0,
        sampler: 'dpmpp_sde',
        scheduler: 'karras',
        comfy_url: 'http://127.0.0.1:8188'
      }
    }, null, 2) + '\n');

    await writeFile(join(projectDir, 'constitution.json'), JSON.stringify({
      version: '0.1.0',
      rules: [
        { id: 'STY-001', category: 'style', desc: 'Consistent visual style across all assets',
          dims: ['style_consistency'], faction_specific: false,
          rationale_pass: 'Style consistency achieved (${scorePct}%)',
          rationale_fail: 'Style inconsistent (${scorePct}%)' },
        { id: 'CMP-001', category: 'composition', desc: 'Clean composition and framing',
          dims: ['composition'], faction_specific: false,
          rationale_pass: 'Composition reads clearly (${scorePct}%)',
          rationale_fail: 'Composition unclear or cluttered (${scorePct}%)' },
      ]
    }, null, 2) + '\n');

    await writeFile(join(projectDir, 'lanes.json'), JSON.stringify({
      default_lane: 'default',
      lanes: [
        { id: 'default', label: 'Default', description: 'All assets', id_patterns: [] }
      ]
    }, null, 2) + '\n');

    await writeFile(join(projectDir, 'rubric.json'), JSON.stringify({
      dimensions: ['style_consistency', 'composition', 'detail', 'originality'],
      thresholds: {
        approved: { pass: 0.7, partial: 0.5 },
        borderline: { pass: 0.7, partial: 0.5 },
        rejected: { fail_ceiling: 0.4, partial_ceiling: 0.6 }
      },
      failure_to_rules: {}
    }, null, 2) + '\n');

    await writeFile(join(projectDir, 'terminology.json'), JSON.stringify({
      group_label: 'group',
      id_detection_order: [],
      prompt_detection_order: [],
      groups: {},
      cross_group_patterns: {},
      edge_defaults: {},
      null_faction_patterns: [],
      id_fallbacks: {},
      faction_context: {}
    }, null, 2) + '\n');

    for (const file of configFiles) {
      console.log(`  \x1b[32m✓\x1b[0m ${file} (generic starter)`);
    }
  }

  // Copy canon markdown templates
  const canonTemplates = ['constitution.md', 'review-rubric.md'];
  const wroteCanon = {};
  for (const file of canonTemplates) {
    const src = join(TEMPLATES_DIR, 'canon', file);
    if (existsSync(src)) {
      await copyFile(src, join(projectDir, 'canon', file));
      wroteCanon[file] = true;
      console.log(`  \x1b[32m✓\x1b[0m canon/${file}`);
    }
  }

  // Copy example prompt pack — prefer per-domain example (subjects match domain lane id_patterns),
  // fall back to legacy global template if it exists (pre-v3.0.1 installs may still ship it).
  let wroteExamplePack = false;
  const domainExamplePack = domainDir
    ? join(domainDir, 'inputs', 'prompts', 'example-wave.json')
    : null;
  const globalExamplePack = join(TEMPLATES_DIR, 'inputs', 'prompts', 'example-wave.json');
  const examplePack =
    domainExamplePack && existsSync(domainExamplePack) ? domainExamplePack
    : existsSync(globalExamplePack) ? globalExamplePack
    : null;
  if (examplePack) {
    await copyFile(examplePack, join(projectDir, 'inputs', 'prompts', 'example-wave.json'));
    wroteExamplePack = true;
    console.log(`  \x1b[32m✓\x1b[0m inputs/prompts/example-wave.json`);
  }

  // Copy domain workflow profiles if available
  if (domainDir) {
    const domainWorkflowsDir = join(domainDir, 'workflows', 'profiles');
    if (existsSync(domainWorkflowsDir)) {
      const wfFiles = (await readdir(domainWorkflowsDir)).filter(f => f.endsWith('.json'));
      for (const file of wfFiles) {
        await copyFile(
          join(domainWorkflowsDir, file),
          join(projectDir, 'workflows', 'profiles', file)
        );
        console.log(`  \x1b[32m✓\x1b[0m workflows/profiles/${file}`);
      }
    }
  }

  // Write a starter README.md inside the project so users have a home base
  // with copy-pasteable next commands and a place for their notes.
  const readmeLines = [
    `# ${projectName}`,
    '',
    `A \`style-dataset-lab\` project — domain: **${domain}**.`,
    '',
    '## Quick commands',
    '',
    '```bash',
    `# Validate that the scaffold is healthy`,
    `sdlab project doctor --project ${projectName}`,
    '',
  ];
  if (wroteExamplePack) {
    readmeLines.push(
      `# Generate candidates from the example prompt pack`,
      `sdlab generate inputs/prompts/example-wave.json --project ${projectName}`,
      ''
    );
  } else {
    readmeLines.push(
      `# Generate candidates (add a prompt pack under inputs/prompts/ first)`,
      `sdlab generate <pack-path> --project ${projectName}`,
      ''
    );
  }
  readmeLines.push(
    `# Curate a candidate (approved | rejected | borderline)`,
    `sdlab curate <asset_id> approved "reads clean" --project ${projectName}`,
    '',
    `# Bind approved records to constitution rules`,
    `sdlab canon-bind --project ${projectName}`,
    '',
    `# Create a frozen dataset snapshot`,
    `sdlab snapshot create --project ${projectName}`,
    '```',
    '',
    '## Project layout',
    '',
    '- `project.json` — defaults (checkpoint, width, height, sampler)',
    '- `constitution.json` — machine-readable style rules',
    '- `canon/` — human-authored style reference (constitution.md, review-rubric.md)',
    '- `inputs/prompts/` — generation prompt packs',
    '- `outputs/candidates/` — raw generated PNGs',
    '- `outputs/approved/` · `outputs/rejected/` · `outputs/borderline/` — curated outputs',
    '- `records/` — provenance + judgment records (one JSON per candidate)',
    '- `snapshots/` · `splits/` · `exports/` — frozen dataset artifacts',
    '',
    '## Docs',
    '',
    '- Handbook: https://mcp-tool-shop-org.github.io/style-dataset-lab/',
    '- CLI reference: `sdlab --help` (or `sdlab <cmd> --help` for any command)',
    '',
    '## TODO',
    '',
    '- [ ] Fill in `canon/constitution.md` with your style rules',
    '- [ ] Encode those rules in `constitution.json` for canon-bind',
    '- [ ] Add at least one prompt pack under `inputs/prompts/`',
    '- [ ] Run `sdlab project doctor` and fix any warnings',
    ''
  );
  await writeFile(join(projectDir, 'README.md'), readmeLines.join('\n'));
  console.log(`  \x1b[32m✓\x1b[0m README.md`);

  console.log('');
  console.log(`\x1b[32m✓\x1b[0m Project "${projectName}" initialized`);
  console.log('');
  console.log('Next steps:');
  let step = 1;
  if (wroteCanon['constitution.md']) {
    console.log(`  ${step++}. Edit ${projectName}/canon/constitution.md — define your visual rules`);
  }
  console.log(`  ${step++}. Edit ${projectName}/constitution.json — encode rules for canon-bind`);
  if (wroteExamplePack) {
    console.log(`  ${step++}. Run: sdlab generate inputs/prompts/example-wave.json --project ${projectName}`);
  } else {
    console.log(`  ${step++}. Create prompt packs under ${projectName}/inputs/prompts/`);
    console.log(`  ${step++}. Run: sdlab generate <pack> --project ${projectName}`);
  }
  console.log(`  ${step++}. Run: sdlab project doctor --project ${projectName}`);
  console.log('');
  console.log(`See ${projectName}/README.md for the full quick-start.`);
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('init.js') || process.argv[1].endsWith('init'))) {
  run().catch(handleCliError);
}
