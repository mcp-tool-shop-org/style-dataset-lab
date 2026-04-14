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
 */

import { readdir, readFile, writeFile, access } from 'node:fs/promises';
import { join, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = new URL('.', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1');
const REPO_ROOT = join(__dirname, '..');
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);
const RECORDS_DIR = join(GAME_ROOT, 'records');
const DRY_RUN = process.argv.includes('--dry-run');

async function fileExists(p) {
  try { await access(p); return true; } catch { return false; }
}

function isCuratorDivergent(rec) {
  // Shape 2/4: has verdict at top level, judgment is null
  return rec.judgment === null && typeof rec.verdict === 'string' && !rec.identity;
}

function isIdentityRecord(rec) {
  // Shape 3: has identity block — Grounded pipeline, DO NOT TOUCH
  return rec.identity != null;
}

async function migrateRecord(filePath) {
  const raw = await readFile(filePath, 'utf-8');
  const rec = JSON.parse(raw);

  // Skip identity records entirely — Grounded pipeline
  if (isIdentityRecord(rec)) return { file: basename(filePath), action: 'skip-identity' };

  // Skip records that are already in standard shape
  if (!isCuratorDivergent(rec)) {
    // Still check for stale asset_path on standard records
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

  // Migrate curator-divergent record
  const changes = [];

  // Build judgment object from top-level fields
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

  // Remove top-level divergent fields
  delete rec.verdict;
  delete rec.scores;
  delete rec.explanation;
  delete rec.failures;
  delete rec.curated_at;
  delete rec.curator;
  changes.push('removed top-level verdict/scores/explanation/failures/curated_at/curator');

  // Fix asset_path if image moved to approved/
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

async function main() {
  console.log(DRY_RUN ? '=== DRY RUN ===' : '=== APPLYING MIGRATION ===');

  const files = (await readdir(RECORDS_DIR)).filter(f => f.endsWith('.json'));
  console.log(`Found ${files.length} record files\n`);

  const results = { skipped: 0, migrated: 0, pathFixed: 0, identity: 0, errors: 0 };

  for (const file of files) {
    try {
      const result = await migrateRecord(join(RECORDS_DIR, file));
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

main().catch(err => { console.error(err); process.exit(1); });
