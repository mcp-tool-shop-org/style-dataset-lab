#!/usr/bin/env node

/**
 * doctor.js — Validate project config completeness and correctness.
 *
 * Checks structural health without deep business logic linting.
 * Every check produces a specific, actionable message on failure.
 *
 * Usage:
 *   sdlab project doctor --project star-freight
 *   node scripts/doctor.js --project my-project
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { getProjectName } from '../lib/args.js';
import { REPO_ROOT } from '../lib/paths.js';

const REQUIRED_CONFIG_FILES = [
  'project.json',
  'constitution.json',
  'lanes.json',
  'rubric.json',
  'terminology.json',
];

const REQUIRED_DIRS = [
  'canon',
  'records',
  'comparisons',
  'inputs/prompts',
  'outputs/candidates',
  'outputs/approved',
  'outputs/rejected',
  'exports',
  'snapshots',
  'splits',
  'eval-packs',
  'training/profiles',
  'training/manifests',
  'training/packages',
  'training/eval-runs',
  'training/implementations',
];

function pass(msg) { console.log(`  \x1b[32m✓\x1b[0m ${msg}`); }
function fail(msg) { console.log(`  \x1b[31m✗\x1b[0m ${msg}`); }
function warn(msg) { console.log(`  \x1b[33m⚠\x1b[0m ${msg}`); }

function tryParseJson(filePath) {
  try {
    return { data: JSON.parse(readFileSync(filePath, 'utf-8')), error: null };
  } catch (err) {
    return { data: null, error: err.message };
  }
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const projectDir = join(REPO_ROOT, 'projects', projectName);

  console.log(`\x1b[1msdlab project doctor\x1b[0m — ${projectName}`);
  console.log(`  Path: ${projectDir}\n`);

  let passes = 0;
  let failures = 0;
  let warnings = 0;

  // ── 1. Project directory exists ──
  if (!existsSync(projectDir)) {
    fail(`Project directory not found: ${projectDir}`);
    console.log(`\n  Run: sdlab init ${projectName} --domain <domain>`);
    return;
  }
  pass('Project directory exists');
  passes++;

  // ── 2. Required config files present and parseable ──
  console.log('');
  const configs = {};
  for (const file of REQUIRED_CONFIG_FILES) {
    const filePath = join(projectDir, file);
    if (!existsSync(filePath)) {
      fail(`Missing: ${file}`);
      failures++;
      continue;
    }
    const { data, error } = tryParseJson(filePath);
    if (error) {
      fail(`${file} — invalid JSON: ${error}`);
      failures++;
      continue;
    }
    configs[file] = data;
    pass(`${file} — valid JSON`);
    passes++;
  }

  // ── 3. Required directories ──
  console.log('');
  for (const dir of REQUIRED_DIRS) {
    if (existsSync(join(projectDir, dir))) {
      pass(`${dir}/`);
      passes++;
    } else {
      warn(`${dir}/ — missing (will be created on first use)`);
      warnings++;
    }
  }

  // ── 4. Project.json validation ──
  const meta = configs['project.json'];
  if (meta) {
    console.log('');
    if (meta.name) { pass(`project.json: name = "${meta.name}"`); passes++; }
    else { fail('project.json: missing "name"'); failures++; }

    if (meta.domain) { pass(`project.json: domain = "${meta.domain}"`); passes++; }
    else { warn('project.json: no "domain" set'); warnings++; }
  }

  // ── 5. Constitution validation ──
  const constitution = configs['constitution.json'];
  if (constitution) {
    console.log('');
    const rules = constitution.rules || (Array.isArray(constitution) ? constitution : []);
    if (rules.length === 0) {
      fail('constitution.json: no rules defined');
      failures++;
    } else {
      pass(`constitution.json: ${rules.length} rules`);
      passes++;

      // Check required rule fields
      const ruleIds = new Set();
      let ruleErrors = 0;
      for (const rule of rules) {
        if (!rule.id) { fail(`constitution.json: rule missing "id"`); ruleErrors++; continue; }
        if (ruleIds.has(rule.id)) { fail(`constitution.json: duplicate rule ID "${rule.id}"`); ruleErrors++; }
        ruleIds.add(rule.id);
        if (!rule.dims || rule.dims.length === 0) {
          fail(`constitution.json: rule ${rule.id} has no "dims" (scoring dimensions)`);
          ruleErrors++;
        }
      }
      if (ruleErrors === 0) { pass('constitution.json: all rules have id + dims'); passes++; }
      else { failures += ruleErrors; }
    }
  }

  // ── 6. Lanes validation ──
  const lanes = configs['lanes.json'];
  if (lanes) {
    console.log('');
    const laneList = lanes.lanes || [];
    if (laneList.length === 0) {
      warn('lanes.json: no lanes defined (default lane only)');
      warnings++;
    } else {
      pass(`lanes.json: ${laneList.length} lanes`);
      passes++;

      // Check lane IDs unique
      const laneIds = new Set();
      let laneErrors = 0;
      for (const lane of laneList) {
        if (!lane.id) { fail('lanes.json: lane missing "id"'); laneErrors++; continue; }
        if (laneIds.has(lane.id)) { fail(`lanes.json: duplicate lane ID "${lane.id}"`); laneErrors++; }
        laneIds.add(lane.id);

        // Check patterns compile
        for (const pattern of lane.id_patterns || []) {
          try { new RegExp(pattern); }
          catch { fail(`lanes.json: lane "${lane.id}" has invalid pattern "${pattern}"`); laneErrors++; }
        }
      }
      if (laneErrors === 0) { pass('lanes.json: all lane IDs unique, patterns compile'); passes++; }
      else { failures += laneErrors; }
    }

    if (!lanes.default_lane) {
      warn('lanes.json: no "default_lane" set');
      warnings++;
    }
  }

  // ── 7. Rubric validation ──
  const rubric = configs['rubric.json'];
  if (rubric) {
    console.log('');
    const dims = rubric.dimensions || [];
    if (dims.length === 0) {
      fail('rubric.json: no dimensions defined');
      failures++;
    } else {
      pass(`rubric.json: ${dims.length} dimensions`);
      passes++;
    }

    if (!rubric.thresholds) {
      fail('rubric.json: missing "thresholds"');
      failures++;
    } else {
      pass('rubric.json: thresholds present');
      passes++;
    }

    // Cross-reference: constitution dims should exist in rubric
    if (constitution && dims.length > 0) {
      const dimSet = new Set(dims);
      const rules = constitution.rules || [];
      const missingDims = new Set();
      for (const rule of rules) {
        for (const d of rule.dims || []) {
          if (!dimSet.has(d)) missingDims.add(d);
        }
      }
      if (missingDims.size > 0) {
        fail(`rubric.json: constitution references dimensions not in rubric: ${[...missingDims].join(', ')}`);
        failures++;
      } else {
        pass('rubric.json: all constitution dimensions present in rubric');
        passes++;
      }
    }

    // Check failure_to_rules references valid rule IDs
    if (rubric.failure_to_rules && constitution) {
      const ruleIds = new Set((constitution.rules || []).map(r => r.id));
      let badRefs = 0;
      for (const [mode, ruleList] of Object.entries(rubric.failure_to_rules)) {
        for (const ruleId of ruleList) {
          if (!ruleIds.has(ruleId)) {
            fail(`rubric.json: failure mode "${mode}" references unknown rule "${ruleId}"`);
            badRefs++;
          }
        }
      }
      if (badRefs === 0 && Object.keys(rubric.failure_to_rules).length > 0) {
        pass(`rubric.json: ${Object.keys(rubric.failure_to_rules).length} failure modes, all reference valid rules`);
        passes++;
      }
      if (badRefs > 0) failures += badRefs;
    }
  }

  // ── 8. Terminology validation ──
  const terminology = configs['terminology.json'];
  if (terminology) {
    console.log('');
    const groups = Object.keys(terminology.groups || {});
    if (groups.length === 0) {
      pass('terminology.json: no groups defined (valid for projects without faction/group system)');
      passes++;
    } else {
      pass(`terminology.json: ${groups.length} groups (${groups.join(', ')})`);
      passes++;

      // Check detection order references valid groups
      for (const orderKey of ['id_detection_order', 'prompt_detection_order']) {
        const order = terminology[orderKey] || [];
        for (const name of order) {
          if (!terminology.groups[name]) {
            fail(`terminology.json: ${orderKey} references unknown group "${name}"`);
            failures++;
          }
        }
      }

      // Check group patterns compile
      let patternErrors = 0;
      for (const [gName, group] of Object.entries(terminology.groups)) {
        for (const pattern of group.id_patterns || []) {
          try { new RegExp(pattern); }
          catch { fail(`terminology.json: group "${gName}" has invalid id_pattern "${pattern}"`); patternErrors++; }
        }
        for (const pattern of group.prompt_patterns || []) {
          try { new RegExp(pattern); }
          catch { fail(`terminology.json: group "${gName}" has invalid prompt_pattern "${pattern}"`); patternErrors++; }
        }
      }
      if (patternErrors === 0) { pass('terminology.json: all detection patterns compile'); passes++; }
      else { failures += patternErrors; }
    }
  }

  // ── 9. Records sanity check ──
  const recordsDir = join(projectDir, 'records');
  if (existsSync(recordsDir)) {
    console.log('');
    const recordFiles = readdirSync(recordsDir).filter(f => f.endsWith('.json'));
    if (recordFiles.length > 0) {
      // Spot-check first 3 records
      let recordErrors = 0;
      const sample = recordFiles.slice(0, 3);
      for (const f of sample) {
        const { data, error } = tryParseJson(join(recordsDir, f));
        if (error) { fail(`records/${f}: invalid JSON`); recordErrors++; }
        else if (!data.id) { fail(`records/${f}: missing "id"`); recordErrors++; }
      }
      if (recordErrors === 0) {
        pass(`${recordFiles.length} records (spot-check passed)`);
        passes++;
      } else {
        failures += recordErrors;
      }
    } else {
      pass('records/ — empty (new project)');
      passes++;
    }
  }

  // ── Summary ──
  console.log('');
  const status = failures === 0 ? '\x1b[32mHEALTHY\x1b[0m' : '\x1b[31mFAILED\x1b[0m';
  console.log(`═══ ${status} — ${passes} passed, ${failures} failed, ${warnings} warnings ═══`);

  if (failures > 0) {
    throw new Error(`Project "${projectName}" has ${failures} issue(s).`);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('doctor.js') || process.argv[1].endsWith('doctor'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
