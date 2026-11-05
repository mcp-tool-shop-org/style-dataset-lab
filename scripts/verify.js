#!/usr/bin/env node

/**
 * sdlab verify — Offline end-to-end provenance chain verification (G9, §2.2–§2.3).
 *
 * Walks:
 *   image -> record (G5 owner + CC-BY-4.0)
 *         -> canon (G6 canon_sha + entry_sha256)
 *         -> model licence (G4 SPDX id + licence_url + date_read)
 *         -> run manifest (workflow sha + verdict separation)
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { inputError, handleCliError } from '../lib/errors.js';
import { verifyProvenanceChain } from '../lib/verify-chain.js';

export async function run(argv = process.argv.slice(2)) {
  const parsed = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      game: { type: 'string' },
      record: { type: 'string' },
      snapshot: { type: 'string' },
      json: { type: 'boolean' },
      'allow-empty': { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = getProjectName(argv);
  const projectDir = getProjectRoot(projectName);

  const report = await verifyProvenanceChain(projectDir, {
    recordId: parsed.flags.record || null,
    snapshotId: parsed.flags.snapshot || null,
    allowEmpty: parsed.flags['allow-empty'] === true,
  });

  if (parsed.flags.json) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(`\x1b[1msdlab verify\x1b[0m — ${projectName}`);
    console.log(`  Records checked: ${report.records_checked} (${report.passed_count} passed, ${report.failed_count} failed)`);
    for (const f of report.failures) {
      console.error(`  \x1b[31m✗\x1b[0m [${f.code}] ${f.message}`);
    }
    if (report.ok) {
      console.log(`  \x1b[32m✓\x1b[0m Provenance chain intact (CC-BY-4.0 eligible)`);
    }
  }

  if (!report.ok) {
    const codes = [...new Set(report.failures.map((f) => f.code))].join(', ');
    throw inputError(
      'PROVENANCE_VERIFY_FAILED',
      `Provenance verification failed for project "${projectName}" (${report.failures.length} failure(s): ${codes})`,
      'Fix the broken provenance link(s) reported above before releasing or exporting under CC-BY-4.0.',
    );
  }

  return report;
}

if (process.argv[1] && (process.argv[1].endsWith('verify.js') || process.argv[1].endsWith('verify'))) {
  run().catch(handleCliError);
}
