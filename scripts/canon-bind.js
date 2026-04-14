#!/usr/bin/env node
/**
 * Canon Binding Pass — populate canon_assertions in all records.
 *
 * Each assertion links an asset to a specific constitution rule with
 * a verdict (pass/fail/partial) and a one-line rationale derived from
 * the judgment scores and failure modes.
 *
 * Usage:
 *   node scripts/canon-bind.js            # bind all records
 *   node scripts/canon-bind.js --dry-run  # preview without writing
 *   node scripts/canon-bind.js --stats    # print coverage stats
 */

import { readFileSync, writeFileSync, readdirSync } from 'fs';
import { join } from 'path';

const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

const RECORDS_DIR = join(GAME_ROOT, 'records');
const DRY_RUN = process.argv.includes('--dry-run');
const STATS_ONLY = process.argv.includes('--stats');

// ─── Constitution Rules ──────────────────────────────────────────────
// Each rule has: id, category, description, scoring_dimensions (which
// judgment scores map to this rule), and faction_specific flag.

const CONSTITUTION_RULES = [
  // Rendering rules (universal)
  { id: 'RND-001', category: 'rendering', desc: 'Semi-realistic painterly style',
    dims: ['style_consistency'], faction_specific: false },
  { id: 'RND-002', category: 'rendering', desc: 'Single upper-left warm lighting with soft AO shadows',
    dims: ['composition'], faction_specific: false },
  { id: 'RND-003', category: 'rendering', desc: 'Muted dusty color saturation',
    dims: ['palette_adherence'], faction_specific: false },
  { id: 'RND-004', category: 'rendering', desc: 'Full body front-facing on plain background, 70-85% fill',
    dims: ['composition'], faction_specific: false },
  { id: 'RND-005', category: 'rendering', desc: 'Readable at 128px, identifiable at 64px',
    dims: ['silhouette_clarity'], faction_specific: false },

  // Material rules (faction-specific)
  { id: 'MAT-001', category: 'material', desc: 'Every surface reads as faction material vocabulary',
    dims: ['material_fidelity', 'faction_read'], faction_specific: true },
  { id: 'MAT-002', category: 'material', desc: 'Faction-appropriate aging and wear',
    dims: ['wear_level'], faction_specific: true },

  // Shape language (faction-specific)
  { id: 'SHP-001', category: 'shape', desc: 'Faction shape language compliance',
    dims: ['silhouette_clarity', 'faction_read'], faction_specific: true },

  // Color rules (faction-specific)
  { id: 'COL-001', category: 'color', desc: 'Correct faction palette colors',
    dims: ['palette_adherence', 'faction_read'], faction_specific: true },
  { id: 'COL-002', category: 'color', desc: 'Palette ratio ~60/30/10',
    dims: ['palette_adherence'], faction_specific: true },
  { id: 'COL-003', category: 'color', desc: 'No bright saturated colors — everything muted/dusty',
    dims: ['palette_adherence'], faction_specific: false },

  // Clothing rules (faction-specific — costume subjects only)
  { id: 'CLO-001', category: 'clothing', desc: 'Layer logic: base → functional → identity → accessory',
    dims: ['clothing_logic'], faction_specific: true, lanes: ['costume'] },
  { id: 'CLO-002', category: 'clothing', desc: 'Construction matches faction building method',
    dims: ['clothing_logic', 'material_fidelity'], faction_specific: true, lanes: ['costume'] },
  { id: 'CLO-003', category: 'clothing', desc: 'Not generic sci-fi (no spandex/Star Trek/Marvel/asset store)',
    dims: ['faction_read', 'clothing_logic'], faction_specific: false },

  // Ship rules (ship subjects only)
  { id: 'SHP-EXT-001', category: 'ship', desc: 'Faction hull language — construction reads as faction-built',
    dims: ['material_fidelity', 'faction_read'], faction_specific: true, lanes: ['ship'] },
  { id: 'SHP-EXT-002', category: 'ship', desc: 'Scale and grit — working vehicle not showpiece',
    dims: ['wear_level', 'material_fidelity'], faction_specific: false, lanes: ['ship'] },
  { id: 'SHP-INT-001', category: 'interior', desc: 'Interior faction character — environmental storytelling',
    dims: ['faction_read', 'material_fidelity'], faction_specific: true, lanes: ['interior'] },
  { id: 'SHP-INT-002', category: 'interior', desc: 'Lived-in detail — coffee stains, tool marks, wear',
    dims: ['wear_level'], faction_specific: false, lanes: ['interior'] },

  // Equipment rules (equipment/prop subjects only)
  { id: 'EQP-001', category: 'equipment', desc: 'Faction design language for tools and weapons',
    dims: ['material_fidelity', 'faction_read'], faction_specific: true, lanes: ['equipment', 'prop'] },
  { id: 'EQP-002', category: 'equipment', desc: 'Tool not toy — used, worn, functional',
    dims: ['wear_level'], faction_specific: false, lanes: ['equipment', 'prop'] },
  { id: 'EQP-003', category: 'equipment', desc: 'Props carry faction identity or universal grit',
    dims: ['faction_read', 'wear_level'], faction_specific: false, lanes: ['prop'] },

  // Environment rules (environment subjects only)
  { id: 'ENV-001', category: 'environment', desc: 'Atmosphere over beauty — industrial, tense, functional',
    dims: ['style_consistency', 'wear_level'], faction_specific: false, lanes: ['environment', 'station'] },
  { id: 'ENV-002', category: 'environment', desc: 'Faction footprint in architecture and signage',
    dims: ['faction_read', 'material_fidelity'], faction_specific: true, lanes: ['environment', 'station'] },
  { id: 'ENV-003', category: 'environment', desc: 'Lighting carries mood — faction-specific lighting character',
    dims: ['palette_adherence'], faction_specific: true, lanes: ['environment', 'station', 'interior'] },
];

// ─── Lane Detection ──────────────────────────────────────────────────
// Determines which subject category an asset belongs to, so lane-specific
// rules (CLO for costumes, SHP for ships, etc.) are applied correctly.

function detectLane(id, prompt) {
  const lower = id.toLowerCase();
  // Ship exterior prefixes
  if (/^ship_ext_|^se_|^ship_/.test(lower)) return 'ship';
  // Ship interior prefixes
  if (/^ship_int_|^si_|^int_|^interior_/.test(lower)) return 'interior';
  // Station/port prefixes
  if (/^station_|^port_|^stn_/.test(lower)) return 'station';
  // Equipment/weapon prefixes
  if (/^eqp_|^wpn_|^weapon_|^tool_|^equip_/.test(lower)) return 'equipment';
  // Prop prefixes
  if (/^prop_|^food_|^sign_|^furn_/.test(lower)) return 'prop';
  // Environment prefixes
  if (/^env_|^planet_|^landing_|^mine_/.test(lower)) return 'environment';
  // Default: costume (all existing assets are costumes)
  return 'costume';
}

// ─── Faction Detection ───────────────────────────────────────────────

const FACTION_MATERIAL = {
  compact: 'Pressed (machine-stamped, regulation-issued)',
  keth: 'Grown (cultivated, secreted, bio-film)',
  veshan: 'Forged (hammered, riveted, layered)',
  orryn: 'Woven (modular, interlocking, reconfigurable)',
  reach: 'Stripped (torn, welded from scrap, jury-rigged)',
};

const FACTION_SHAPES = {
  compact: 'Rectangles, straight edges, 90° corners',
  keth: 'Segments, arcs, compound curves',
  veshan: 'Triangles, chevrons, sharp angles',
  orryn: 'Ellipses, flowing curves, translucent layers',
  reach: 'Asymmetric, irregular, mismatched',
};

const FACTION_WEAR = {
  compact: 'Maintained but impersonal — kept to standard',
  keth: 'Alive — aging means growing, not decaying',
  veshan: 'Battle-scarred with pride — damage displayed',
  orryn: 'Adaptive — reconfigured, not worn',
  reach: 'Jury-rigged — functional ugly',
};

function detectFaction(id, prompt) {
  // ID-based detection (most reliable)
  if (/^(anchor_|c_|c2_|c6_|c10_)/.test(id)) return 'compact';
  if (/^(v_|v3_|v7_|v10_)/.test(id)) return 'veshan';
  if (/^(sr_|sr4_|sr8_|sr10_)/.test(id)) return 'reach';
  if (/^(k_|k\d+_)/.test(id)) return 'keth';
  if (/^(o_|o\d+_)/.test(id)) return 'orryn';

  // Cross-faction: detect from ID suffix
  if (/^cf_/.test(id)) {
    if (/compact/.test(id)) return 'compact';
    if (/veshan/.test(id)) return 'veshan';
    if (/reach/.test(id)) return 'reach';
    if (/keth/.test(id)) return 'keth';
    if (/orryn/.test(id)) return 'orryn';
  }

  // Edge cases: detect from prompt
  if (/^edge_/.test(id)) return 'compact'; // edge cases are human subjects

  // Reject/borderline: detect from prompt content
  if (prompt) {
    const p = prompt.toLowerCase();
    if (/reptilian|veshan|scales|crest/.test(p)) return 'veshan';
    if (/arthropod|keth|chitin|antennae/.test(p)) return 'keth';
    if (/cephalopod|orryn|tentacle|chromatophore/.test(p)) return 'orryn';
    if (/salvaged|scrap|jury.rigged|outlaw|pirate/.test(p)) return 'reach';
  }

  // Reject IDs: try to detect from naming
  if (/wrong_material_v/.test(id)) return 'veshan';
  if (/generic_scifi|too_clean|too_heroic|star_trek|cyberpunk|fantasy_knight|warhammer|too_sexy|steampunk|fashion_model|pin_up|fortnite|mmorpg|superhero|invisible|xenomorph|zombified|samurai/.test(id)) return null; // no faction — generic reject

  if (/veshan|cute_dragon|generic_lizard|veshan_robot|veshan_human/.test(id)) return 'veshan';
  if (/reach|pirate|matching_gang|space_cowboy/.test(id)) return 'reach';
  if (/keth/.test(id)) return 'keth';

  // Borderline
  if (/almost_right_compact/.test(id)) return 'compact';
  if (/almost_right_veshan/.test(id)) return 'veshan';
  if (/almost_right_reach/.test(id)) return 'reach';

  return null; // unknown faction
}

// ─── Failure Mode → Rule Mapping ─────────────────────────────────────

const FAILURE_TO_RULES = {
  generic_scifi: ['CLO-003'],
  too_clean: ['MAT-002', 'COL-003'],
  wrong_material: ['MAT-001'],
  wrong_shapes: ['SHP-001'],
  wrong_palette: ['COL-001', 'COL-002', 'COL-003'],
  photorealistic: ['RND-001'],
  '3d_render': ['RND-001'],
  bad_composition: ['RND-004'],
  costume_not_clothes: ['CLO-001', 'CLO-002'],
  faction_unreadable: ['MAT-001', 'SHP-001', 'COL-001'],
  anime_style: ['RND-001'],
  hero_pose: ['RND-004'],
};

// ─── Assertion Generation ────────────────────────────────────────────

function generateAssertions(record) {
  const { id, judgment, provenance } = record;
  if (!judgment || !judgment.criteria_scores) return null;

  const { status, criteria_scores, failure_modes = [], explanation = '' } = judgment;
  const prompt = provenance?.prompt || '';
  const faction = detectFaction(id, prompt);
  const lane = detectLane(id, prompt);
  const assertions = [];

  for (const rule of CONSTITUTION_RULES) {
    // Skip faction-specific rules for unknown-faction rejects
    if (rule.faction_specific && !faction) continue;

    // Skip lane-specific rules that don't apply to this asset's lane
    if (rule.lanes && !rule.lanes.includes(lane)) continue;

    // Calculate average score from mapped dimensions
    const dimScores = rule.dims
      .map(d => criteria_scores[d])
      .filter(s => s !== undefined && s !== null);
    if (dimScores.length === 0) continue;
    const avgScore = dimScores.reduce((a, b) => a + b, 0) / dimScores.length;

    // Check if any failure mode maps to this rule
    const failedByMode = failure_modes.some(fm =>
      (FAILURE_TO_RULES[fm] || []).includes(rule.id)
    );

    // Determine verdict
    let verdict;
    if (status === 'rejected') {
      if (failedByMode || avgScore < 0.4) {
        verdict = 'fail';
      } else if (avgScore < 0.6) {
        verdict = 'partial';
      } else {
        verdict = 'pass'; // rejected asset can still pass some rules
      }
    } else if (status === 'borderline') {
      if (avgScore >= 0.7) verdict = 'pass';
      else if (avgScore >= 0.5) verdict = 'partial';
      else verdict = 'fail';
    } else { // approved
      if (avgScore >= 0.7) verdict = 'pass';
      else if (avgScore >= 0.5) verdict = 'partial';
      else verdict = 'fail'; // unlikely for approved
    }

    // Build rationale
    let rationale = buildRationale(rule, verdict, avgScore, faction, explanation);

    assertions.push({
      rule_id: rule.id,
      category: rule.category,
      verdict,
      score: Math.round(avgScore * 100) / 100,
      rationale,
      ...(faction && rule.faction_specific ? { faction, faction_context: getFactionContext(rule, faction) } : {}),
    });
  }

  return assertions;
}

function buildRationale(rule, verdict, score, faction, explanation) {
  const scorePct = Math.round(score * 100);

  if (verdict === 'pass') {
    switch (rule.id) {
      case 'RND-001': return `Painterly rendering achieved (${scorePct}%)`;
      case 'RND-002': return `Lighting reads correctly — warm upper-left with soft shadows`;
      case 'RND-003': return `Palette is muted and dusty — no bright saturated colors`;
      case 'RND-004': return `Full body, front-facing, plain background, correct fill`;
      case 'RND-005': return `Silhouette readable at gameplay scale (${scorePct}%)`;
      case 'MAT-001': return `Surfaces read as ${faction ? FACTION_MATERIAL[faction] : 'faction material'} (${scorePct}%)`;
      case 'MAT-002': return `Wear level appropriate — ${faction ? FACTION_WEAR[faction] : 'faction-correct aging'}`;
      case 'SHP-001': return `Shape language compliant — ${faction ? FACTION_SHAPES[faction] : 'faction shapes'}`;
      case 'COL-001': return `Faction palette present and dominant (${scorePct}%)`;
      case 'COL-002': return `Color ratios read as ~60/30/10`;
      case 'COL-003': return `Colors muted and lived-in — no neon or bright saturated tones`;
      case 'CLO-001': return `Layer logic follows base → functional → identity → accessory`;
      case 'CLO-002': return `Construction matches ${faction ? 'faction' : ''} building method`;
      case 'CLO-003': return `Not generic sci-fi — reads as faction-specific and lived-in`;
      default: return `Passes ${rule.id} (${scorePct}%)`;
    }
  }

  if (verdict === 'fail') {
    switch (rule.id) {
      case 'RND-001': return `Not painterly — reads as photorealistic/3D/anime (${scorePct}%)`;
      case 'RND-002': return `Lighting incorrect or flat`;
      case 'RND-003': return `Colors too bright or saturated — not muted/dusty`;
      case 'RND-004': return `Composition fails — not full body/centered/plain bg (${scorePct}%)`;
      case 'RND-005': return `Silhouette unreadable at gameplay scale (${scorePct}%)`;
      case 'MAT-001': return `Surfaces don't read as ${faction ? FACTION_MATERIAL[faction] : 'any faction material'} (${scorePct}%)`;
      case 'MAT-002': return `Wear level wrong — ${faction ? 'doesn\'t match ' + FACTION_WEAR[faction] : 'inappropriate aging'}`;
      case 'SHP-001': return `Shape language violates faction — wrong geometry (${scorePct}%)`;
      case 'COL-001': return `Faction palette missing or wrong colors (${scorePct}%)`;
      case 'COL-002': return `Color ratios off — primary doesn't dominate`;
      case 'COL-003': return `Bright saturated colors present — violates muted/dusty rule`;
      case 'CLO-001': return `Layer logic broken — layers don't follow faction system`;
      case 'CLO-002': return `Construction doesn't match faction building method (${scorePct}%)`;
      case 'CLO-003': return `Reads as generic sci-fi — not faction-specific (${scorePct}%)`;
      default: return `Fails ${rule.id} (${scorePct}%)`;
    }
  }

  // partial
  return `Partially meets ${rule.desc.toLowerCase()} (${scorePct}%)`;
}

function getFactionContext(rule, faction) {
  switch (rule.id) {
    case 'MAT-001': return FACTION_MATERIAL[faction] || null;
    case 'MAT-002': return FACTION_WEAR[faction] || null;
    case 'SHP-001': return FACTION_SHAPES[faction] || null;
    case 'COL-001':
    case 'COL-002': return `Faction primary should dominate at ~60%`;
    case 'CLO-001': return `base → functional → identity → accessory`;
    case 'CLO-002':
      switch (faction) {
        case 'compact': return 'Machine-made, identical cuts, zero personalization';
        case 'keth': return 'Grown on wearer or harvested from communal bio-stocks';
        case 'veshan': return 'Smith-forged, imperfections intentional';
        case 'orryn': return 'Modular panels that clip together magnetically';
        case 'reach': return 'Assembled from salvage, nothing matches';
        default: return null;
      }
    default: return null;
  }
}

// ─── Main ────────────────────────────────────────────────────────────

const files = readdirSync(RECORDS_DIR).filter(f => f.endsWith('.json'));
let bound = 0, skipped = 0, alreadyBound = 0;
const factionCounts = {};
const verdictCounts = { pass: 0, fail: 0, partial: 0 };

for (const file of files) {
  const path = join(RECORDS_DIR, file);
  const record = JSON.parse(readFileSync(path, 'utf-8'));

  // Skip records without judgment
  if (!record.judgment || !record.judgment.criteria_scores) {
    skipped++;
    continue;
  }

  // Check if already bound
  if (record.canon?.assertions?.length > 0 && !process.argv.includes('--force')) {
    alreadyBound++;
    continue;
  }

  const assertions = generateAssertions(record);
  if (!assertions || assertions.length === 0) {
    skipped++;
    continue;
  }

  // Track stats
  const faction = detectFaction(record.id, record.provenance?.prompt);
  factionCounts[faction || 'unknown'] = (factionCounts[faction || 'unknown'] || 0) + 1;
  for (const a of assertions) {
    verdictCounts[a.verdict] = (verdictCounts[a.verdict] || 0) + 1;
  }

  if (STATS_ONLY) {
    bound++;
    continue;
  }

  // Build canon object (nested — our rich format)
  record.canon = {
    constitution_version: '1.0.0',
    bound_at: new Date().toISOString(),
    bound_by: 'canon-bind-v1',
    faction: faction || null,
    assertions,
    assertion_count: assertions.length,
    pass_count: assertions.filter(a => a.verdict === 'pass').length,
    fail_count: assertions.filter(a => a.verdict === 'fail').length,
    partial_count: assertions.filter(a => a.verdict === 'partial').length,
  };

  // Also write flat canon_assertions (repo-dataset expects this at top level)
  record.canon_assertions = assertions;

  // Write canon_explanation for triangle completion
  const passCount = assertions.filter(a => a.verdict === 'pass').length;
  const failCount = assertions.filter(a => a.verdict === 'fail').length;
  const status = record.judgment.status;
  if (status === 'approved') {
    record.canon_explanation = `Approved: passes ${passCount}/${assertions.length} constitution rules. ${faction ? `Faction: ${faction}.` : ''} ${record.judgment.explanation || ''}`.trim();
  } else if (status === 'rejected') {
    const failedRules = assertions.filter(a => a.verdict === 'fail').map(a => a.rule_id).join(', ');
    record.canon_explanation = `Rejected: fails ${failedRules}. ${record.judgment.explanation || ''}`.trim();
  } else {
    record.canon_explanation = `Borderline: ${passCount} pass, ${failCount} fail out of ${assertions.length} rules. ${record.judgment.explanation || ''}`.trim();
  }

  if (!DRY_RUN) {
    writeFileSync(path, JSON.stringify(record, null, 2) + '\n');
  }
  bound++;

  if (DRY_RUN && bound <= 3) {
    console.log(`\n─── ${record.id} (${record.judgment.status}) ───`);
    console.log(`Faction: ${faction || 'unknown'}`);
    for (const a of assertions) {
      console.log(`  ${a.verdict.toUpperCase().padEnd(7)} ${a.rule_id} — ${a.rationale}`);
    }
  }
}

console.log(`\n═══ Canon Binding ${DRY_RUN ? '(DRY RUN) ' : STATS_ONLY ? '(STATS) ' : ''}Summary ═══`);
console.log(`Records: ${files.length}`);
console.log(`Bound: ${bound}`);
console.log(`Already bound: ${alreadyBound}`);
console.log(`Skipped (no judgment): ${skipped}`);
console.log(`\nFaction distribution:`);
for (const [f, c] of Object.entries(factionCounts).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${f}: ${c}`);
}
console.log(`\nVerdict totals (across all assertions):`);
for (const [v, c] of Object.entries(verdictCounts)) {
  console.log(`  ${v}: ${c}`);
}
