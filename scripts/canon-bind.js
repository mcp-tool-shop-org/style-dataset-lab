#!/usr/bin/env node
/**
 * Canon Binding Pass — populate canon_assertions in all records.
 *
 * Each assertion links an asset to a specific constitution rule with
 * a verdict (pass/fail/partial) and a one-line rationale derived from
 * the judgment scores and failure modes.
 *
 * Loads rules, lanes, rubric, and terminology from per-project config files.
 * Missing config files cause a hard failure — no silent fallback.
 *
 * Usage:
 *   node scripts/canon-bind.js            # bind all records
 *   node scripts/canon-bind.js --dry-run  # preview without writing
 *   node scripts/canon-bind.js --stats    # print coverage stats
 *   sdlab bind --project star-freight --stats
 */

import { readFileSync, writeFileSync, readdirSync, existsSync } from 'fs';
import { join } from 'path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';
import { loadConstitution, loadLanes, loadRubric, loadTerminology } from '../lib/config.js';

// ─── Config-Driven Detection ────────────────────────────────────────

/**
 * Detect lane from asset ID using project lane config.
 * Tests each lane's id_patterns as regex against the lowercase ID.
 * Returns the first match, or the default_lane.
 */
function detectLane(id, prompt, lanesConfig) {
  const lower = id.toLowerCase();
  for (const lane of lanesConfig.lanes) {
    if (!lane.id_patterns || lane.id_patterns.length === 0) continue;
    for (const pattern of lane.id_patterns) {
      if (new RegExp(pattern).test(lower)) return lane.id;
    }
  }
  return lanesConfig.default_lane;
}

/**
 * Detect group (faction) from asset ID and prompt using terminology config.
 * Mirrors the exact detection order from the original hardcoded detectFaction():
 *   1. Primary ID patterns per group
 *   2. Cross-group patterns (e.g. ^cf_ → detect from ID suffix)
 *   3. Edge defaults (e.g. ^edge_ → compact)
 *   4. Prompt-based fallback patterns
 *   5. Null-faction patterns (generic rejects with no faction)
 *   6. ID fallback patterns (specific reject/borderline IDs)
 */
function detectGroup(id, prompt, termConfig) {
  // Explicit ordering for ID-based and prompt-based detection phases.
  // These can differ — e.g. ID checks reach before keth, but prompt
  // checks veshan before keth before orryn before reach.
  const idOrder = termConfig.id_detection_order || Object.keys(termConfig.groups);
  const promptOrder = termConfig.prompt_detection_order || Object.keys(termConfig.groups);

  // 1. Primary ID patterns per group (id_detection_order)
  for (const groupName of idOrder) {
    const group = termConfig.groups[groupName];
    if (!group?.id_patterns) continue;
    for (const pattern of group.id_patterns) {
      if (new RegExp(pattern).test(id)) return groupName;
    }
  }

  // 2. Cross-group patterns
  for (const [pattern, behavior] of Object.entries(termConfig.cross_group_patterns || {})) {
    if (new RegExp(pattern).test(id)) {
      if (behavior === 'detect_from_id_suffix') {
        for (const groupName of idOrder) {
          if (id.includes(groupName)) return groupName;
        }
      }
      return null;
    }
  }

  // 3. Edge defaults
  for (const [pattern, groupName] of Object.entries(termConfig.edge_defaults || {})) {
    if (new RegExp(pattern).test(id)) return groupName;
  }

  // 4. Prompt-based fallback (prompt_detection_order)
  if (prompt) {
    const p = prompt.toLowerCase();
    for (const groupName of promptOrder) {
      const group = termConfig.groups[groupName];
      if (!group?.prompt_patterns || group.prompt_patterns.length === 0) continue;
      for (const keyword of group.prompt_patterns) {
        if (new RegExp(keyword).test(p)) return groupName;
      }
    }
  }

  // 5. Null-faction patterns (generic rejects — no faction)
  for (const pattern of termConfig.null_faction_patterns || []) {
    if (new RegExp(pattern).test(id)) return null;
  }

  // 6. ID fallback patterns
  for (const [pattern, groupName] of Object.entries(termConfig.id_fallbacks || {})) {
    if (new RegExp(pattern).test(id)) return groupName;
  }

  return null;
}

/**
 * Build rationale string from rule's template, interpolating variables.
 */
function buildRationale(rule, verdict, score, groupName, termConfig) {
  const scorePct = Math.round(score * 100);
  const group = groupName ? termConfig.groups[groupName] : null;
  const groupMaterial = group?.material || 'faction material';
  const groupShapes = group?.shapes || 'faction shapes';
  const groupWear = group?.wear || 'faction-correct aging';

  let template;
  if (verdict === 'pass') {
    template = rule.rationale_pass;
  } else if (verdict === 'fail') {
    template = rule.rationale_fail;
  } else {
    // partial — use generic template
    return `Partially meets ${rule.desc.toLowerCase()} (${scorePct}%)`;
  }

  if (!template) {
    // Fallback for rules without templates
    return verdict === 'pass'
      ? `Passes ${rule.id} (${scorePct}%)`
      : `Fails ${rule.id} (${scorePct}%)`;
  }

  // Interpolate template variables
  return template
    .replace(/\$\{scorePct\}/g, String(scorePct))
    .replace(/\$\{groupMaterial\}/g, groupMaterial)
    .replace(/\$\{groupShapes\}/g, groupShapes)
    .replace(/\$\{groupWear\}/g, groupWear);
}

/**
 * Get faction context string for a rule from terminology config.
 */
function getGroupContext(rule, groupName, termConfig) {
  // Check rule-specific overrides in terminology
  const contextOverride = termConfig.faction_context?.[rule.id];
  if (contextOverride) return contextOverride;

  // Check group-specific construction context
  const group = groupName ? termConfig.groups[groupName] : null;
  if (group?.construction?.[rule.id]) return group.construction[rule.id];

  // Fallback by rule category
  switch (rule.id) {
    case 'MAT-001': return group?.material || null;
    case 'MAT-002': return group?.wear || null;
    case 'SHP-001': return group?.shapes || null;
    default: return null;
  }
}

// ─── Assertion Generation ────────────────────────────────────────────

function generateAssertions(record, constitutionRules, lanesConfig, rubricConfig, termConfig) {
  const { id, judgment, provenance } = record;
  if (!judgment || !judgment.criteria_scores) return null;

  const { status, criteria_scores, failure_modes = [], explanation = '' } = judgment;
  const prompt = provenance?.prompt || '';
  const group = detectGroup(id, prompt, termConfig);
  const lane = detectLane(id, prompt, lanesConfig);
  const assertions = [];

  const failureToRules = rubricConfig.failure_to_rules || {};
  const thresholds = rubricConfig.thresholds || {};

  for (const rule of constitutionRules) {
    // Skip group-specific rules for unknown-group rejects
    if (rule.faction_specific && !group) continue;

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
      (failureToRules[fm] || []).includes(rule.id)
    );

    // Determine verdict using rubric thresholds
    let verdict;
    if (status === 'rejected') {
      const t = thresholds.rejected || { fail_ceiling: 0.4, partial_ceiling: 0.6 };
      if (failedByMode || avgScore < t.fail_ceiling) {
        verdict = 'fail';
      } else if (avgScore < t.partial_ceiling) {
        verdict = 'partial';
      } else {
        verdict = 'pass'; // rejected asset can still pass some rules
      }
    } else if (status === 'borderline') {
      const t = thresholds.borderline || { pass: 0.7, partial: 0.5 };
      if (avgScore >= t.pass) verdict = 'pass';
      else if (avgScore >= t.partial) verdict = 'partial';
      else verdict = 'fail';
    } else { // approved
      const t = thresholds.approved || { pass: 0.7, partial: 0.5 };
      if (avgScore >= t.pass) verdict = 'pass';
      else if (avgScore >= t.partial) verdict = 'partial';
      else verdict = 'fail'; // unlikely for approved
    }

    const rationale = buildRationale(rule, verdict, avgScore, group, termConfig);

    assertions.push({
      rule_id: rule.id,
      category: rule.category,
      verdict,
      score: Math.round(avgScore * 100) / 100,
      rationale,
      ...(group && rule.faction_specific ? { faction: group, faction_context: getGroupContext(rule, group, termConfig) } : {}),
    });
  }

  return assertions;
}

// ─── Main ────────────────────────────────────────────────────────────

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const PROJECT_ROOT = join(REPO_ROOT, 'projects', projectName);
  const RECORDS_DIR = join(PROJECT_ROOT, 'records');
  const DRY_RUN = argv.includes('--dry-run');
  const STATS_ONLY = argv.includes('--stats');
  const FORCE = argv.includes('--force');

  // Load project config — fail loudly if missing
  if (!existsSync(join(PROJECT_ROOT, 'constitution.json'))) {
    throw new Error(
      `No constitution.json found in ${PROJECT_ROOT}.\n` +
      `Canon binding requires per-project config files.\n` +
      `Run: sdlab init ${projectName} --domain <domain>`
    );
  }

  const constitutionConfig = loadConstitution(PROJECT_ROOT);
  const lanesConfig = loadLanes(PROJECT_ROOT);
  const rubricConfig = loadRubric(PROJECT_ROOT);
  const termConfig = loadTerminology(PROJECT_ROOT);

  if (!constitutionConfig.rules || constitutionConfig.rules.length === 0) {
    throw new Error(`constitution.json has no rules — cannot bind.`);
  }

  const constitutionRules = constitutionConfig.rules;
  const constitutionVersion = constitutionConfig.version || '1.0.0';

  const files = readdirSync(RECORDS_DIR).filter(f => f.endsWith('.json'));
  let bound = 0, skipped = 0, alreadyBound = 0;
  const groupCounts = {};
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
    if (record.canon?.assertions?.length > 0 && !FORCE) {
      alreadyBound++;
      continue;
    }

    const assertions = generateAssertions(record, constitutionRules, lanesConfig, rubricConfig, termConfig);
    if (!assertions || assertions.length === 0) {
      skipped++;
      continue;
    }

    // Track stats
    const group = detectGroup(record.id, record.provenance?.prompt, termConfig);
    groupCounts[group || 'unknown'] = (groupCounts[group || 'unknown'] || 0) + 1;
    for (const a of assertions) {
      verdictCounts[a.verdict] = (verdictCounts[a.verdict] || 0) + 1;
    }

    if (STATS_ONLY) {
      bound++;
      continue;
    }

    // Build canon object
    record.canon = {
      constitution_version: constitutionVersion,
      bound_at: new Date().toISOString(),
      bound_by: 'canon-bind-v1',
      faction: group || null,
      assertions,
      assertion_count: assertions.length,
      pass_count: assertions.filter(a => a.verdict === 'pass').length,
      fail_count: assertions.filter(a => a.verdict === 'fail').length,
      partial_count: assertions.filter(a => a.verdict === 'partial').length,
    };

    // Flat canon_assertions for repo-dataset
    record.canon_assertions = assertions;

    // Canon explanation
    const passCount = assertions.filter(a => a.verdict === 'pass').length;
    const failCount = assertions.filter(a => a.verdict === 'fail').length;
    const status = record.judgment.status;
    if (status === 'approved') {
      record.canon_explanation = `Approved: passes ${passCount}/${assertions.length} constitution rules. ${group ? `Faction: ${group}.` : ''} ${record.judgment.explanation || ''}`.trim();
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
      console.log(`Faction: ${group || 'unknown'}`);
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
  for (const [f, c] of Object.entries(groupCounts).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${f}: ${c}`);
  }
  console.log(`\nVerdict totals (across all assertions):`);
  for (const [v, c] of Object.entries(verdictCounts)) {
    console.log(`  ${v}: ${c}`);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('canon-bind.js') || process.argv[1].endsWith('canon-bind'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
