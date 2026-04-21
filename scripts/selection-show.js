#!/usr/bin/env node

/**
 * selection-show.js — Show selection details or list all selections.
 *
 * Usage:
 *   sdlab selection show --project star-freight
 *   sdlab selection show --selection selection_2026-04-16_001
 *   sdlab selection show selection_2026-04-16_001 --json
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { loadSelection, listSelections, getSelectionsDir } from '../lib/selections.js';
import { join } from 'node:path';
import { existsSync, readFileSync } from 'node:fs';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      selection: { type: 'string' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const selectionId = positionals[0] || flags.selection;

  // List mode
  if (!selectionId) {
    const selections = listSelections(projectRoot);
    if (selections.length === 0) {
      console.log('No selections found.');
      return;
    }
    console.log(`\x1b[1mstyle-dataset-lab\x1b[0m selections (${projectName})`);
    console.log('');
    for (const id of selections) {
      try {
        const m = loadSelection(projectRoot, id);
        const items = m.items?.length || 0;
        const src = `${m.source_type}:${m.source_id}`;
        const ready = m.reingest_ready ? '✓' : '○';
        const subject = m.subject_id ? ` (${m.subject_id})` : '';
        console.log(`  ${ready} ${id}  ${src.padEnd(32)} ${items} items${subject}`);
      } catch {
        console.log(`  ? ${id}  (manifest unreadable)`);
      }
    }
    console.log('');
    return;
  }

  // Detail mode
  const manifest = loadSelection(projectRoot, selectionId);

  if (flags.json) {
    console.log(JSON.stringify(manifest, null, 2));
    return;
  }

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m selection ${selectionId}`);
  console.log('');
  console.log(`  Source:          ${manifest.source_type} ${manifest.source_id}`);
  if (manifest.workflow_id) console.log(`  Workflow:        ${manifest.workflow_id}`);
  if (manifest.subject_id) console.log(`  Subject:         ${manifest.subject_id}`);
  console.log(`  Created:         ${manifest.created_at}`);
  console.log(`  Re-ingest ready: ${manifest.reingest_ready ? 'yes' : 'no'}`);
  console.log('');
  console.log('  Chosen outputs:');
  for (const item of manifest.items || []) {
    const seedStr = item.seed !== undefined ? `seed=${item.seed}` : '';
    console.log(`    ✓ ${item.slot_or_output.padEnd(28)} → ${item.filename}  ${seedStr}`);
    if (item.reason) console.log(`      ${item.reason}`);
    if (item.tags?.length) console.log(`      tags: ${item.tags.join(', ')}`);
  }

  // Check provenance log
  const provPath = join(getSelectionsDir(projectRoot), selectionId, 'provenance.jsonl');
  if (existsSync(provPath)) {
    console.log('');
    console.log('  Provenance log: provenance.jsonl');
  }
  console.log('');
}
