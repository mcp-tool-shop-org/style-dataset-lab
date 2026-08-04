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
import { REPO_ROOT, getProjectRoot, getRuntimeDir } from '../lib/paths.js';
import { runtimeError, handleCliError } from '../lib/errors.js';

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
  'workflows/profiles',
  'workflows/batch-modes',
  'briefs',
  'runs',
  'batches',
  'selections',
  'inbox/generated',
];

function pass(msg) { console.log(`  \x1b[32m✓\x1b[0m ${msg}`); }
// M1: fail() carried no hint — every OTHER command in this CLI prints a
// "Hint:" line (lib/errors.js handleCliError) when one is available, but
// doctor's ~40 failure sites just dropped it on the floor. Doctor is the
// tool people run when confused; its output IS the error-recovery story.
// hint is optional so existing terse call sites (a handful of genuinely
// self-explanatory failures) keep working unchanged.
function fail(msg, hint) {
  console.log(`  \x1b[31m✗\x1b[0m ${msg}`);
  if (hint) console.log(`    \x1b[33mHint:\x1b[0m ${hint}`);
}
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
  // SDL-C3-completion: resolve through the hardened getProjectRoot() instead of
  // a raw join(REPO_ROOT, 'projects', projectName) — the raw join let a
  // --project value like "../../ai-eyes-mcp" escape the projects/ directory
  // entirely (path traversal). getProjectRoot() rejects any name containing
  // "/", "\" or ".." (INPUT_UNSAFE_PROJECT_NAME) and re-verifies containment,
  // and throws INPUT_UNKNOWN_PROJECT (with the same "run sdlab init" hint this
  // function used to print by hand) when the project does not exist.
  //
  // That second throw is also the SDL-C4 fix: this function used to check
  // existence itself with `if (!existsSync(projectDir)) { fail(...); return; }`
  // — a bare `return` that resolved the run() promise successfully, so
  // handleCliError's process.exit() never ran and `sdlab project doctor
  // --project <missing>` exited 0. getProjectRoot() throws instead of
  // returning, so a missing project now rejects run() and reaches the CLI's
  // normal nonzero-exit error path — the ANDON gate this command IS (it's
  // exactly what `npm run verify` and the CI smoke-test step call).
  const projectDir = getProjectRoot(projectName);

  console.log(`\x1b[1msdlab project doctor\x1b[0m — ${projectName}`);
  console.log(`  Path: ${projectDir}\n`);

  let passes = 0;
  let failures = 0;
  let warnings = 0;

  // ── 1. Project directory exists ──
  // Guaranteed true here — getProjectRoot() above already throws otherwise.
  // Recorded as a pass so the check numbering below stays stable.
  pass('Project directory exists');
  passes++;

  // ── 2. Required config files present and parseable ──
  console.log('');
  const configs = {};
  for (const file of REQUIRED_CONFIG_FILES) {
    const filePath = join(projectDir, file);
    if (!existsSync(filePath)) {
      fail(
        `Missing: ${file}`,
        `Run "sdlab init <name> --domain <domain>" to scaffold it, or hand-author ${file} — see ` +
        `templates/domains/*/${file} for the expected shape.`
      );
      failures++;
      continue;
    }
    const { data, error } = tryParseJson(filePath);
    if (error) {
      fail(`${file} — invalid JSON: ${error}`, `Open ${filePath} and fix the syntax error above.`);
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
    else { fail('project.json: missing "name"', 'Add a top-level "name" field matching the project directory name.'); failures++; }

    if (meta.domain) { pass(`project.json: domain = "${meta.domain}"`); passes++; }
    else { warn('project.json: no "domain" set'); warnings++; }
  }

  // ── 5. Constitution validation ──
  const constitution = configs['constitution.json'];
  if (constitution) {
    console.log('');
    const rules = constitution.rules || (Array.isArray(constitution) ? constitution : []);
    if (rules.length === 0) {
      fail(
        'constitution.json: no rules defined',
        'Add at least one rule object to the "rules" array — see templates/domains/*/constitution.json for the shape.'
      );
      failures++;
    } else {
      pass(`constitution.json: ${rules.length} rules`);
      passes++;

      // Check required rule fields
      // M1: localize WHICH index is missing an id, and WHICH TWO indices
      // collide on a duplicate — a rule id is not the record's only
      // identity, and "duplicate rule ID X" without saying where left the
      // operator grepping the file by hand.
      const ruleIdFirstIndex = new Map(); // id -> first index that defined it
      let ruleErrors = 0;
      for (const [i, rule] of rules.entries()) {
        if (!rule.id) {
          fail(`constitution.json: rule missing "id"`, `Add an "id" field to rules[${i}] (e.g. "STY-002").`);
          ruleErrors++;
          continue;
        }
        if (ruleIdFirstIndex.has(rule.id)) {
          fail(
            `constitution.json: duplicate rule ID "${rule.id}"`,
            `rules[${ruleIdFirstIndex.get(rule.id)}] and rules[${i}] both use id "${rule.id}" — give one of them a unique id.`
          );
          ruleErrors++;
        } else {
          ruleIdFirstIndex.set(rule.id, i);
        }
        if (!rule.dims || rule.dims.length === 0) {
          fail(
            `constitution.json: rule ${rule.id} has no "dims" (scoring dimensions)`,
            `Add a non-empty "dims" array to rules[${i}] (e.g. ["style_consistency"]) — see rubric.json's "dimensions" for valid values.`
          );
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

      // Check lane IDs unique — same index-localization as constitution rules above.
      const laneIdFirstIndex = new Map();
      let laneErrors = 0;
      for (const [i, lane] of laneList.entries()) {
        if (!lane.id) {
          fail('lanes.json: lane missing "id"', `Add an "id" field to lanes[${i}].`);
          laneErrors++;
          continue;
        }
        if (laneIdFirstIndex.has(lane.id)) {
          fail(
            `lanes.json: duplicate lane ID "${lane.id}"`,
            `lanes[${laneIdFirstIndex.get(lane.id)}] and lanes[${i}] both use id "${lane.id}" — give one of them a unique id.`
          );
          laneErrors++;
        } else {
          laneIdFirstIndex.set(lane.id, i);
        }

        // Check patterns compile
        for (const pattern of lane.id_patterns || []) {
          try { new RegExp(pattern); }
          catch {
            fail(
              `lanes.json: lane "${lane.id}" has invalid pattern "${pattern}"`,
              `Fix the regular expression syntax for lane "${lane.id}"'s id_patterns entry "${pattern}".`
            );
            laneErrors++;
          }
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
      fail(
        'rubric.json: no dimensions defined',
        'Add at least one dimension string to "dimensions" (e.g. ["style_consistency", "composition"]).'
      );
      failures++;
    } else {
      pass(`rubric.json: ${dims.length} dimensions`);
      passes++;
    }

    if (!rubric.thresholds) {
      fail(
        'rubric.json: missing "thresholds"',
        'Add a "thresholds" object with approved/borderline/rejected bands — see templates/domains/*/rubric.json for the shape.'
      );
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
        fail(
          `rubric.json: constitution references dimensions not in rubric: ${[...missingDims].join(', ')}`,
          `Add [${[...missingDims].map(d => `"${d}"`).join(', ')}] to rubric.json's "dimensions" array, or fix the referencing rule(s) in constitution.json.`
        );
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
            fail(
              `rubric.json: failure mode "${mode}" references unknown rule "${ruleId}"`,
              `Add a rule with id "${ruleId}" to constitution.json, or remove it from rubric.json's failure_to_rules["${mode}"].`
            );
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
            fail(
              `terminology.json: ${orderKey} references unknown group "${name}"`,
              `Add "${name}" to terminology.json's "groups" object, or remove it from "${orderKey}".`
            );
            failures++;
          }
        }
      }

      // Check group patterns compile
      let patternErrors = 0;
      for (const [gName, group] of Object.entries(terminology.groups)) {
        for (const pattern of group.id_patterns || []) {
          try { new RegExp(pattern); }
          catch {
            fail(
              `terminology.json: group "${gName}" has invalid id_pattern "${pattern}"`,
              `Fix the regular expression syntax for group "${gName}"'s id_patterns entry "${pattern}".`
            );
            patternErrors++;
          }
        }
        for (const pattern of group.prompt_patterns || []) {
          try { new RegExp(pattern); }
          catch {
            fail(
              `terminology.json: group "${gName}" has invalid prompt_pattern "${pattern}"`,
              `Fix the regular expression syntax for group "${gName}"'s prompt_patterns entry "${pattern}".`
            );
            patternErrors++;
          }
        }
      }
      if (patternErrors === 0) { pass('terminology.json: all detection patterns compile'); passes++; }
      else { failures += patternErrors; }
    }
  }

  // ── 9. Workflow profile validation ──
  const workflowDir = join(projectDir, 'workflows', 'profiles');
  if (existsSync(workflowDir)) {
    console.log('');
    const wfFiles = readdirSync(workflowDir).filter(f => f.endsWith('.json'));
    if (wfFiles.length > 0) {
      const VALID_SUBJECT_MODES = ['required', 'optional', 'forbidden'];
      const VALID_OUTPUT_MODES = ['portrait_set', 'expression_sheet', 'variant_pack', 'moodboard', 'silhouette_sheet', 'turnaround'];
      const laneIds = new Set((lanes?.lanes || []).map(l => l.id));

      let wfErrors = 0;
      for (const file of wfFiles) {
        const { data, error } = tryParseJson(join(workflowDir, file));
        if (error) {
          fail(`workflows/profiles/${file} — invalid JSON: ${error}`, `Open workflows/profiles/${file} and fix the syntax error above.`);
          wfErrors++;
          continue;
        }

        const missing = ['workflow_id', 'label', 'lane_id', 'output_mode', 'output_count',
          'prompt_strategy', 'negative_strategy', 'canon_focus', 'drift_guards', 'runtime_defaults']
          .filter(f => data[f] === undefined || data[f] === null);
        if (missing.length > 0) {
          fail(`workflows/profiles/${file} — missing fields: ${missing.join(', ')}`, `Add [${missing.join(', ')}] to workflows/profiles/${file}.`);
          wfErrors++;
          continue;
        }

        if (data.lane_id && laneIds.size > 0 && !laneIds.has(data.lane_id)) {
          fail(
            `workflows/profiles/${file} — lane_id "${data.lane_id}" not found in lanes.json`,
            `Use one of lanes.json's existing lane ids [${[...laneIds].join(', ')}], or add "${data.lane_id}" as a new lane.`
          );
          wfErrors++;
        }

        if (data.subject_mode && !VALID_SUBJECT_MODES.includes(data.subject_mode)) {
          fail(`workflows/profiles/${file} — invalid subject_mode "${data.subject_mode}"`, `subject_mode must be one of: ${VALID_SUBJECT_MODES.join(', ')}.`);
          wfErrors++;
        }

        if (!VALID_OUTPUT_MODES.includes(data.output_mode)) {
          fail(`workflows/profiles/${file} — invalid output_mode "${data.output_mode}"`, `output_mode must be one of: ${VALID_OUTPUT_MODES.join(', ')}.`);
          wfErrors++;
        }

        const ps = data.prompt_strategy;
        if (!ps || !Array.isArray(ps.style_prefix) || !ps.structure || !Array.isArray(ps.must_include)) {
          fail(
            `workflows/profiles/${file} — prompt_strategy needs style_prefix[], structure, must_include[]`,
            `Add prompt_strategy.style_prefix (array), .structure (string), and .must_include (array) to workflows/profiles/${file}.`
          );
          wfErrors++;
        }

        const ns = data.negative_strategy;
        if (!ns || !Array.isArray(ns.must_avoid)) {
          fail(`workflows/profiles/${file} — negative_strategy needs must_avoid[]`, `Add negative_strategy.must_avoid (array) to workflows/profiles/${file}.`);
          wfErrors++;
        }

        if (!data.runtime_defaults?.adapter_target) {
          fail(`workflows/profiles/${file} — runtime_defaults needs adapter_target`, `Add runtime_defaults.adapter_target (e.g. "comfyui") to workflows/profiles/${file}.`);
          wfErrors++;
        }
      }

      if (wfErrors === 0) {
        pass(`${wfFiles.length} workflow profiles — all valid`);
        passes++;
      } else {
        failures += wfErrors;
      }
    } else {
      pass('workflows/profiles/ — empty (no workflows yet)');
      passes++;
    }
  }

  // ── 10. Batch mode validation ──
  const batchModesDir = join(projectDir, 'workflows', 'batch-modes');
  if (existsSync(batchModesDir)) {
    console.log('');
    const bmFiles = readdirSync(batchModesDir).filter(f => f.endsWith('.json'));
    if (bmFiles.length > 0) {
      const VALID_BATCH_TYPES = ['expression_sheet', 'environment_board', 'silhouette_pack', 'continuity_variants'];
      const VALID_SUBJECT_MODES_BM = ['required', 'optional', 'forbidden'];
      const VALID_LAYOUTS = ['grid', 'moodboard', 'strip', 'freeform'];
      const wfFiles = existsSync(join(projectDir, 'workflows', 'profiles'))
        ? readdirSync(join(projectDir, 'workflows', 'profiles')).filter(f => f.endsWith('.json')).map(f => f.replace('.json', ''))
        : [];

      let bmErrors = 0;
      for (const file of bmFiles) {
        const { data, error } = tryParseJson(join(batchModesDir, file));
        if (error) {
          fail(`workflows/batch-modes/${file} — invalid JSON: ${error}`, `Open workflows/batch-modes/${file} and fix the syntax error above.`);
          bmErrors++;
          continue;
        }

        if (!data.mode_id) { fail(`workflows/batch-modes/${file} — missing mode_id`, `Add a "mode_id" field to workflows/batch-modes/${file}.`); bmErrors++; }
        if (!data.batch_type || !VALID_BATCH_TYPES.includes(data.batch_type)) {
          fail(`workflows/batch-modes/${file} — invalid batch_type "${data.batch_type}"`, `batch_type must be one of: ${VALID_BATCH_TYPES.join(', ')}.`);
          bmErrors++;
        }
        if (data.subject_mode && !VALID_SUBJECT_MODES_BM.includes(data.subject_mode)) {
          fail(`workflows/batch-modes/${file} — invalid subject_mode "${data.subject_mode}"`, `subject_mode must be one of: ${VALID_SUBJECT_MODES_BM.join(', ')}.`);
          bmErrors++;
        }
        if (data.base_workflow_id && wfFiles.length > 0 && !wfFiles.includes(data.base_workflow_id)) {
          fail(
            `workflows/batch-modes/${file} — base_workflow_id "${data.base_workflow_id}" not found in profiles`,
            `Use one of the existing workflow ids [${wfFiles.join(', ')}], or add a matching profile under workflows/profiles/.`
          );
          bmErrors++;
        }
        if (!Array.isArray(data.variant_plan) || data.variant_plan.length === 0) {
          fail(`workflows/batch-modes/${file} — variant_plan must be non-empty array`, `Add at least one slot to variant_plan in workflows/batch-modes/${file}.`);
          bmErrors++;
        } else {
          const slotIds = data.variant_plan.map(s => s.slot_id);
          const dupes = slotIds.filter((id, i) => slotIds.indexOf(id) !== i);
          if (dupes.length > 0) {
            fail(`workflows/batch-modes/${file} — duplicate slot_ids: ${[...new Set(dupes)].join(', ')}`, `Give each entry in variant_plan a unique slot_id.`);
            bmErrors++;
          }
        }
        if (data.assembly?.layout && !VALID_LAYOUTS.includes(data.assembly.layout)) {
          fail(`workflows/batch-modes/${file} — invalid assembly.layout "${data.assembly.layout}"`, `assembly.layout must be one of: ${VALID_LAYOUTS.join(', ')}.`);
          bmErrors++;
        }
      }

      if (bmErrors === 0) {
        pass(`${bmFiles.length} batch modes — all valid`);
        passes++;
      } else {
        failures += bmErrors;
      }
    } else {
      pass('workflows/batch-modes/ — empty (no batch modes yet)');
      passes++;
    }
  }

  // ── 11. Runtime templates check ──
  {
    console.log('');
    // PACKAGE-relative, not workspace-relative — `runtime/` ships inside the
    // npm tarball (see getPackageRoot() in lib/paths.js). Joining it to
    // REPO_ROOT made doctor report "runtime/comfyui/ — directory not found"
    // for every installed user while the templates sat in the package.
    const runtimeDir = join(getRuntimeDir(), 'comfyui');
    if (existsSync(runtimeDir)) {
      const templateFiles = readdirSync(runtimeDir).filter(f => f.endsWith('.json'));
      if (templateFiles.length > 0) {
        let templateErrors = 0;
        for (const file of templateFiles) {
          const { data, error } = tryParseJson(join(runtimeDir, file));
          if (error) {
            fail(`runtime/comfyui/${file}: invalid JSON — ${error}`, `Open ${join(runtimeDir, file)} and fix the syntax error above.`);
            templateErrors++;
            continue;
          }
          if (!data.template_id) { fail(`runtime/comfyui/${file}: missing template_id`, `Add a "template_id" field to ${file}.`); templateErrors++; }
          if (!data.compatible_modes || !Array.isArray(data.compatible_modes)) {
            fail(`runtime/comfyui/${file}: missing compatible_modes[]`, `Add a "compatible_modes" array to ${file}.`);
            templateErrors++;
          }
        }
        if (templateErrors === 0) {
          pass(`${templateFiles.length} runtime templates — all valid`);
          passes++;
        } else {
          failures += templateErrors;
        }
      } else {
        warn('runtime/comfyui/ — no templates found');
        warnings++;
      }
    } else {
      warn('runtime/comfyui/ — directory not found');
      warnings++;
    }
  }

  // ── 12. Records sanity check ──
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
        if (error) {
          fail(`records/${f}: invalid JSON`, `Open records/${f} and fix the syntax error, or delete/regenerate it if it's an aborted write.`);
          recordErrors++;
        } else if (!data.id) {
          fail(`records/${f}: missing "id"`, `Add an "id" field to records/${f} matching its filename stem.`);
          recordErrors++;
        }
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
    throw runtimeError(
      'PROJECT_UNHEALTHY',
      `Project "${projectName}" has ${failures} issue(s).`,
      `Fix the ✗ lines above — each one now carries its own Hint: with a concrete next action — then re-run: sdlab project doctor --project ${projectName}`
    );
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('doctor.js') || process.argv[1].endsWith('doctor'))) {
  run().catch(handleCliError);
}
