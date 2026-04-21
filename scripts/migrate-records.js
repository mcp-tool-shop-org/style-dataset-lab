#!/usr/bin/env node
/**
 * migrate-records.js — One-time migration for curator-divergent records (Shape 2 + Shape 4)
 *
 * Normalizes verdict/scores/explanation/failures/curated_at/curator at top level
 * into the standard judgment.{status,criteria_scores,explanation,failure_modes,reviewed_at,reviewer} shape.
 *
 * Also fixes asset_path from outputs/candidates/ to outputs/approved/ when the image exists in approved/.
 *
 * DOES NOT TOUCH Shape 3 (identity packet) records — those have judgment=null by design.
 *
 * Usage:
 *   node scripts/migrate-records.js --dry-run    # Preview changes
 *   node scripts/migrate-records.js              # Apply changes
 *   sdlab project migrate --dry-run --project star-freight
 */

import { readdir, readFile, writeFile, access } from 'node:fs/promises';
import { join, basename } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { handleCliError } from '../lib/errors.js';

async function fileExists(p) {
  try { await access(p); return true; } catch { return false; }
}

function isCuratorDivergent(rec) {
  return rec.judgment === null && typeof rec.verdict === 'string' && !rec.identity;
}

function isIdentityRecord(rec) {
  return rec.identity != null;
}

async function migrateRecord(filePath, GAME_ROOT, DRY_RUN) {
  const raw = await readFile(filePath, 'utf-8');
  const rec = JSON.parse(raw);

  if (isIdentityRecord(rec)) return { file: basename(filePath), action: 'skip-identity' };

  if (!isCuratorDivergent(rec)) {
    if (rec.asset_path && rec.asset_path.includes('outputs/candidates/')) {
      const approvedPath = rec.asset_path.replace('outputs/candidates/', 'outputs/approved/');
      const fullApproved = join(GAME_ROOT, approvedPath);
      if (await fileExists(fullApproved)) {
        rec.asset_path = approvedPath;
        if (!DRY_RUN) await writeFile(filePath, JSON.stringify(rec, null, 2) + '\n');
        return { file: basename(filePath), action: 'path-fix-only', from: 'candidates/', to: 'approved/' };
      }
    }
    return { file: basename(filePath), action: 'skip-standard' };
  }

  const changes = [];

  rec.judgment = {
    status: rec.verdict || 'unknown',
    reviewer: rec.curator || 'wave25-script',
    reviewed_at: rec.curated_at || new Date().toISOString(),
    explanation: rec.explanation || '',
    criteria_scores: rec.scores || {},
    failure_modes: rec.failures || [],
    improvement_notes: null,
    confidence: 0.8,
  };
  changes.push(`verdict="${rec.verdict}" → judgment.status`);

  delete rec.verdict;
  delete rec.scores;
  delete rec.explanation;
  delete rec.failures;
  delete rec.curated_at;
  delete rec.curator;
  changes.push('removed top-level verdict/scores/explanation/failures/curated_at/curator');

  if (rec.asset_path && rec.asset_path.includes('outputs/candidates/')) {
    const approvedPath = rec.asset_path.replace('outputs/candidates/', 'outputs/approved/');
    const fullApproved = join(GAME_ROOT, approvedPath);
    if (await fileExists(fullApproved)) {
      rec.asset_path = approvedPath;
      changes.push(`asset_path: candidates/ → approved/`);
    } else {
      changes.push(`asset_path: candidates/ (image not in approved/, kept as-is)`);
    }
  }

  if (!DRY_RUN) {
    await writeFile(filePath, JSON.stringify(rec, null, 2) + '\n');
  }

  return { file: basename(filePath), action: 'migrated', changes };
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);
  const RECORDS_DIR = join(GAME_ROOT, 'records');
  const DRY_RUN = argv.includes('--dry-run');

  console.log(DRY_RUN ? '=== DRY RUN ===' : '=== APPLYING MIGRATION ===');

  const files = (await readdir(RECORDS_DIR)).filter(f => f.endsWith('.json'));
  console.log(`Found ${files.length} record files\n`);

  const results = { skipped: 0, migrated: 0, pathFixed: 0, identity: 0, errors: 0 };

  for (const file of files) {
    try {
      const result = await migrateRecord(join(RECORDS_DIR, file), GAME_ROOT, DRY_RUN);
      switch (result.action) {
        case 'skip-standard': results.skipped++; break;
        case 'skip-identity': results.identity++; break;
        case 'migrated':
          results.migrated++;
          console.log(`MIGRATE: ${result.file}`);
          result.changes.forEach(c => console.log(`  → ${c}`));
          break;
        case 'path-fix-only':
          results.pathFixed++;
          console.log(`PATH-FIX: ${result.file} (${result.from} → ${result.to})`);
          break;
      }
    } catch (err) {
      results.errors++;
      console.error(`ERROR: ${file}: ${err.message}`);
    }
  }

  console.log(`\n=== Summary ===`);
  console.log(`Standard (unchanged): ${results.skipped}`);
  console.log(`Identity (untouched): ${results.identity}`);
  console.log(`Migrated (schema fix): ${results.migrated}`);
  console.log(`Path-fixed only: ${results.pathFixed}`);
  console.log(`Errors: ${results.errors}`);
  console.log(`Total: ${files.length}`);
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('migrate-records.js') || process.argv[1].endsWith('migrate-records'))) {
  run().catch(handleCliError);
}
