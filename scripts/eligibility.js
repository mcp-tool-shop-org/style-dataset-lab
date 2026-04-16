#!/usr/bin/env node

/**
 * eligibility.js — Audit training/eval eligibility for all project records.
 *
 * Usage:
 *   sdlab eligibility audit [--project <name>]
 */

import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { loadProjectConfig, loadSelectionProfile } from '../lib/config.js';
import { evaluateEligibility, categorizeExclusions } from '../lib/eligibility.js';

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectRoot = join(REPO_ROOT, 'projects', projectName);

  const profileIdx = argv.indexOf('--profile');
  const profileId = profileIdx >= 0 ? argv[profileIdx + 1] : null;
  const profile = loadSelectionProfile(projectRoot, profileId);
  const config = loadProjectConfig(projectRoot);

  const recordsDir = join(projectRoot, 'records');
  const files = (await readdir(recordsDir)).filter(f => f.endsWith('.json')).sort();

  console.log(`\x1b[1msdlab eligibility audit\x1b[0m — ${projectName}`);
  console.log(`  Profile: ${profileId || 'training-default (built-in)'}`);
  console.log(`  Records: ${files.length}`);
  console.log('');

  const eligible = [];
  const excluded = [];
  const nearMiss = []; // Records with exactly 1 failing reason

  for (const file of files) {
    const raw = await readFile(join(recordsDir, file), 'utf-8');
    const record = JSON.parse(raw);

    const result = evaluateEligibility(record, profile, config.lanes, config.terminology);

    if (result.eligible) {
      eligible.push(record.id);
    } else {
      excluded.push({ record_id: record.id, reasons: result.reasons });
      if (result.reasons.length === 1) {
        nearMiss.push({ record_id: record.id, reason: result.reasons[0] });
      }
    }
  }

  console.log(`  \x1b[32m✓\x1b[0m Eligible: ${eligible.length}`);
  console.log(`  \x1b[31m✗\x1b[0m Excluded: ${excluded.length}`);
  console.log('');

  // Categorize exclusions
  const categories = categorizeExclusions(excluded);
  console.log('  Exclusion breakdown:');
  for (const [cat, count] of Object.entries(categories)) {
    if (count > 0) {
      const bar = '█'.repeat(Math.min(Math.round(count / files.length * 50), 50));
      console.log(`    ${cat.padEnd(20)} ${String(count).padStart(4)}  ${bar}`);
    }
  }

  // Near-miss improvement opportunities
  if (nearMiss.length > 0) {
    console.log(`\n  Improvement opportunities (${nearMiss.length} records with 1 failing check):`);
    const byReason = {};
    for (const nm of nearMiss) {
      byReason[nm.reason] = (byReason[nm.reason] || 0) + 1;
    }
    for (const [reason, count] of Object.entries(byReason).sort((a, b) => b[1] - a[1]).slice(0, 5)) {
      console.log(`    ${count} records: ${reason}`);
    }
  }

  console.log('');
  const pct = ((eligible.length / files.length) * 100).toFixed(1);
  console.log(`  Eligibility rate: ${pct}% (${eligible.length}/${files.length})`);
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('eligibility.js') || process.argv[1].endsWith('eligibility'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
