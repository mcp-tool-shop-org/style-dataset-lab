#!/usr/bin/env node

/**
 * eligibility.js — Audit training/eval eligibility for all project records.
 *
 * Usage:
 *   sdlab eligibility audit [--project <name>] [--profile <id>]
 */

import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { loadProjectConfig, loadSelectionProfile } from '../lib/config.js';
import { handleCliError } from '../lib/errors.js';
import { evaluateEligibility, categorizeExclusions } from '../lib/eligibility.js';
import { auditJudgmentProvenance, formatProvenanceWarning, formatReuseNote } from '../lib/judgment-provenance.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      profile: { type: 'string' },
    },
    deprecated: { game: 'project' },
    allowUnknown: true,
  });

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);

  const profile = loadSelectionProfile(projectRoot, flags.profile);
  const config = loadProjectConfig(projectRoot);

  const recordsDir = join(projectRoot, 'records');
  const files = (await readdir(recordsDir)).filter(f => f.endsWith('.json')).sort();

  console.log(`\x1b[1msdlab eligibility audit\x1b[0m — ${projectName}`);
  console.log(`  Profile: ${flags.profile || 'training-default (built-in)'}`);
  console.log(`  Records: ${files.length}`);
  console.log('');

  const eligible = [];
  const excluded = [];
  const nearMiss = [];
  // Retained for the judgment-provenance audit below, which is a corpus-level
  // question (is this rationale reused across records?) and cannot be answered
  // one record at a time.
  const allRecords = [];

  for (const file of files) {
    const raw = await readFile(join(recordsDir, file), 'utf-8');
    const record = JSON.parse(raw);
    allRecords.push(record);

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

  const categories = categorizeExclusions(excluded);
  console.log('  Exclusion breakdown:');
  for (const [cat, count] of Object.entries(categories)) {
    if (count > 0) {
      const bar = '█'.repeat(Math.min(Math.round(count / files.length * 50), 50));
      console.log(`    ${cat.padEnd(20)} ${String(count).padStart(4)}  ${bar}`);
    }
  }

  // Judgment provenance (Law 2). Eligibility asks "does this record have a
  // judgment"; it has never asked "does that judgment describe THIS image."
  // On star-freight the difference is 948 of 1,182 records — rationales a
  // deleted bulk script selected by id-prefix, one string reused on 144
  // images. Those records pass every eligibility check and land in training
  // sets carrying an explanation about a category, not a picture.
  //
  // Read-only: nothing here mutates a record (Director's ruling, 2026-08-04).
  const provenance = auditJudgmentProvenance(allRecords);
  const provenanceWarning = formatProvenanceWarning(provenance);
  if (provenanceWarning) {
    console.log('');
    console.log(`  \x1b[33m⚠\x1b[0m ${provenanceWarning}`);
    if (provenance.top_reused.length > 0) {
      console.log('    Most-reused rationales:');
      for (const r of provenance.top_reused.slice(0, 3)) {
        const snippet = r.explanation.length > 62
          ? `${r.explanation.slice(0, 62)}…`
          : r.explanation;
        console.log(`      ×${String(r.count).padStart(3)}  "${snippet}"`);
      }
    }
  } else {
    // No script reviewer. Reuse here is usually a real systematic defect
    // described accurately across the wave it affected — informational, not a
    // finding. Printed at the same indent but without the warning glyph, so it
    // reads as context rather than an accusation.
    const reuseNote = formatReuseNote(provenance);
    if (reuseNote) {
      console.log('');
      console.log(`    ${reuseNote}`);
    }
  }

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
  run().catch(handleCliError);
}
