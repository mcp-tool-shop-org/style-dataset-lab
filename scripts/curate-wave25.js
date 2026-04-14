#!/usr/bin/env node
/**
 * Curation for wave 25 (expanded universe).
 *
 * Based on visual review of all 60 candidates:
 * - REJECT25* subjects → rejected (anti-examples)
 * - Strong hits → approved with high scores
 * - Partial hits → approved with moderate scores + notes
 * - Misses → rejected with explanations of what went wrong
 *
 * Usage:
 *   node scripts/curate-wave25.js
 *   node scripts/curate-wave25.js --dry-run
 */

import { readFileSync, writeFileSync, readdirSync, renameSync, existsSync, mkdirSync } from 'fs';
import { join, basename } from 'path';

const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

const RECORDS_DIR = join(GAME_ROOT, 'records');
const CANDIDATES_DIR = join(GAME_ROOT, 'outputs', 'candidates');
const APPROVED_DIR = join(GAME_ROOT, 'outputs', 'approved');
const REJECTED_DIR = join(GAME_ROOT, 'outputs', 'rejected');
const DRY_RUN = process.argv.includes('--dry-run');

for (const dir of [APPROVED_DIR, REJECTED_DIR]) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

// ─── Scoring profiles ──────────────────────────────────────────

const STRONG_HIT = {
  silhouette_clarity: 0.85, palette_adherence: 0.80, material_fidelity: 0.80,
  faction_read: 0.75, wear_level: 0.85, style_consistency: 0.85,
  clothing_logic: 0.70, composition: 0.85
};

const PARTIAL_HIT = {
  silhouette_clarity: 0.70, palette_adherence: 0.70, material_fidelity: 0.70,
  faction_read: 0.50, wear_level: 0.75, style_consistency: 0.75,
  clothing_logic: 0.55, composition: 0.75
};

// ─── Subject classifications ──────────────────────────────────────────

// Strong hits — approved with high scores
const STRONG_HITS = new Set([
  'keth_molt_before', 'keth_molt_emerging', 'keth_hivesong', 'keth_pheromone_library',
  'veshan_forge_trial', 'veshan_forge_trial_judgment',
  'orryn_sealed_mantle', 'orryn_crystal_inheritance',
  'thresh_young',
  'mire_at_work',
  'vaelk_proxy_market',
  'architect_jump_gate', 'architect_archive_node', 'architect_ruin_surface',
  'drift_kelp_bed',
  'translator_rig'
]);

// Partial hits — approved with moderate scores
const PARTIAL_HITS = new Set([
  'veshan_battle_opera', 'veshan_scale_reader',
  'orryn_drift_parliament', 'orryn_drift_parliament_failed',
  'drift_kelp_ambush',
  'vaelk_proxy_trade',
  'station_climate_border',
  'pidgin_trade_sign'
]);

// Misses — rejected with explanations
const MISS_EXPLANATIONS = {
  thresh_old_station: {
    explanation: "Thresh crystalline organism not visible — rendered as standard station corridor with human. Need to foreground the crystalline growth formation.",
    failures: ["species_not_rendered", "concept_miss"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.5, material_fidelity: 0.6, faction_read: 0.1, wear_level: 0.7, style_consistency: 0.7, clothing_logic: 0.3, composition: 0.6 }
  },
  smuggler_cant_meeting: {
    explanation: "All figures rendered as human — no multi-species element. The cross-species communication concept requires at least 2 different species visible.",
    failures: ["species_not_rendered", "concept_miss"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.6, material_fidelity: 0.7, faction_read: 0.1, wear_level: 0.7, style_consistency: 0.7, clothing_logic: 0.5, composition: 0.7 }
  },
  mire_reforming: {
    explanation: "Green-tinted corridor with organic matter but no clear colonial organism reforming. The aggregation process needs to be the focal point.",
    failures: ["concept_miss"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.6, material_fidelity: 0.6, faction_read: 0.3, wear_level: 0.7, style_consistency: 0.7, clothing_logic: 0.3, composition: 0.6 }
  },
  mire_hull_breach: {
    explanation: "Rendered as military cockpit scene — no Mire organism flowing through hull breach. Complete concept miss.",
    failures: ["species_not_rendered", "concept_miss"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.4, material_fidelity: 0.5, faction_read: 0.0, wear_level: 0.6, style_consistency: 0.5, clothing_logic: 0.3, composition: 0.6 }
  }
};

// Reject examples — always rejected
const REJECT_EXPLANATIONS = {
  REJECT25_clean_alien: {
    explanation: "Clean sterile alien civilization — Star Trek utopia aesthetic. Violates every grit principle.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.1, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.2, composition: 0.7 }
  },
  REJECT25_fantasy_alien: {
    explanation: "Fantasy wizard alien with robes and magic staff — high fantasy, not grounded sci-fi.",
    failures: ["wrong_genre", "costume_not_clothes"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.1, style_consistency: 0.1, clothing_logic: 0.1, composition: 0.6 }
  }
};

// ─── Process ──────────────────────────────────────────

const wave25Files = readdirSync(CANDIDATES_DIR).filter(f =>
  f.endsWith('.png') && readdirSync(RECORDS_DIR).some(r => {
    try {
      const rec = JSON.parse(readFileSync(join(RECORDS_DIR, r), 'utf-8'));
      return rec.file === f && rec.lane === 'wave25-expanded-universe';
    } catch { return false; }
  })
);

// Fallback: match by known subject IDs
const ALL_SUBJECTS = [
  ...STRONG_HITS, ...PARTIAL_HITS,
  ...Object.keys(MISS_EXPLANATIONS),
  ...Object.keys(REJECT_EXPLANATIONS)
];

// Find wave25 records directly by filename match
const recordFiles = readdirSync(RECORDS_DIR).filter(r => r.endsWith('.json'));
const candidates = recordFiles.filter(rf => {
  return ALL_SUBJECTS.some(subj => rf.startsWith(subj));
});

let approved = 0, rejected = 0, skipped = 0;

for (const recordFile of candidates) {
  let record;
  try {
    record = JSON.parse(readFileSync(join(RECORDS_DIR, recordFile), 'utf-8'));
  } catch { continue; }

  const file = basename(record.asset_path || '');
  const subjectId = record.id?.replace(/_v[12]$/, '') || file.replace(/_v[12]\.png$/, '');

  // Already curated?
  if (record.verdict) {
    console.log(`  ⏭ ${file} already curated (${record.verdict})`);
    skipped++;
    continue;
  }

  let verdict, scores, explanation, failures;

  if (REJECT_EXPLANATIONS[subjectId]) {
    const r = REJECT_EXPLANATIONS[subjectId];
    verdict = 'rejected';
    scores = r.scores;
    explanation = r.explanation;
    failures = r.failures;
  } else if (MISS_EXPLANATIONS[subjectId]) {
    const m = MISS_EXPLANATIONS[subjectId];
    verdict = 'rejected';
    scores = m.scores;
    explanation = m.explanation;
    failures = m.failures;
  } else if (STRONG_HITS.has(subjectId)) {
    verdict = 'approved';
    scores = { ...STRONG_HIT };
    explanation = `Strong hit — concept reads clearly, style consistent, gritty lived-in aesthetic.`;
    failures = [];
  } else if (PARTIAL_HITS.has(subjectId)) {
    verdict = 'approved';
    scores = { ...PARTIAL_HIT };
    explanation = `Partial hit — atmosphere and style correct, some species anatomy or concept details missed.`;
    failures = ['partial_species_accuracy'];
  } else {
    console.log(`  ⚠ Unknown subject ${subjectId} for ${file}, skipping`);
    skipped++;
    continue;
  }

  // Update record
  record.verdict = verdict;
  record.scores = scores;
  record.explanation = explanation;
  record.failures = failures;
  record.curated_at = new Date().toISOString();
  record.curator = 'wave25-script';

  // Move file
  const srcPath = join(CANDIDATES_DIR, file);
  const dstDir = verdict === 'approved' ? APPROVED_DIR : REJECTED_DIR;
  const dstPath = join(dstDir, file);

  if (!DRY_RUN) {
    writeFileSync(join(RECORDS_DIR, recordFile), JSON.stringify(record, null, 2));
    if (existsSync(srcPath)) {
      renameSync(srcPath, dstPath);
    }
  }

  const icon = verdict === 'approved' ? '✓' : '✗';
  console.log(`  ${icon} ${file} → ${verdict}`);
  if (verdict === 'approved') approved++;
  else rejected++;
}

console.log(`\nWave 25 curation: ${approved} approved, ${rejected} rejected, ${skipped} skipped`);
if (DRY_RUN) console.log('  (dry run — no files moved)');
