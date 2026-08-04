#!/usr/bin/env node

/**
 * critique.js — Generate a critique report for a completed run.
 *
 * Usage:
 *   sdlab critique --project star-freight --run run_2026-04-15_001
 *   sdlab critique --project star-freight --run run_2026-04-15_001 --json
 */

import { parseArgs, getProjectName, parseNumberFlag } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { critiqueRun, saveCritique, triageCandidates, DEFAULT_DRIFT_THRESHOLD } from '../lib/critique-engine.js';
import { renderCritiqueMarkdown, renderCritiqueText, renderCritiqueTriage } from '../lib/critique-render.js';
import { info } from '../lib/log.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      run: { type: 'string' },
      json: { type: 'boolean' },
      triage: { type: 'boolean' },
      'drift-threshold': { type: 'string' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.run) {
    console.log('Usage: sdlab critique --run <id> [--project <name>] [--triage]');
    console.log('');
    console.log('Options:');
    console.log('  --run <id>            Run to critique (required)');
    console.log('  --triage             Show only candidates needing attention (off-model OR ≥ threshold drift issues)');
    console.log(`  --drift-threshold <n>  Drift-issue count that flags a candidate under --triage (default ${DEFAULT_DRIFT_THRESHOLD})`);
    console.log('  --json               Output raw JSON');
    return;
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m critique`);
  console.log(`  Project: ${projectName}`);
  console.log(`  Run: ${flags.run}`);
  console.log('');

  // Generate critique
  const report = await critiqueRun({
    projectRoot,
    projectId: projectName,
    runId: flags.run,
  });

  // Save the FULL report — triage is a view over it, never a mutation.
  const md = renderCritiqueMarkdown(report);
  await saveCritique(projectRoot, flags.run, report, md);

  // UNCERTAINTY_GATED_HUMANS: --triage surfaces only the candidates that need a
  // human — off-model OR >= threshold drift issues — so attention isn't spent on
  // every item. The full critique.json still holds all candidates.
  if (flags.triage) {
    const driftThreshold = flags['drift-threshold']
      ? parseNumberFlag('drift-threshold', flags['drift-threshold'], { int: true, min: 0 })
      : DEFAULT_DRIFT_THRESHOLD;
    const triage = triageCandidates(report.candidates, { driftThreshold });
    if (flags.json) {
      console.log(JSON.stringify({
        run_id: report.run_id,
        triage: { drift_threshold: driftThreshold, flagged_count: triage.flagged.length, suppressed_count: triage.suppressed.length },
        candidates: triage.flagged,
      }, null, 2));
    } else {
      console.log(renderCritiqueTriage(report, triage));
      console.log(`Full critique saved to: runs/${flags.run}/critique.json`);
    }
    return;
  }

  if (flags.json) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(renderCritiqueText(report));
    const action = report.recommended_action;
    console.log(`Critique saved to: runs/${flags.run}/critique.json`);

    // H2: `refine_from_one` fires today purely from every candidate sitting
    // at the unreviewed default overall_fit "usable" (nothing in the
    // codebase currently sets it to anything else) — action.reviewed
    // (lib/critique-engine.js recommendAction) distinguishes that from an
    // actually-assessed run. Printing "Next: ..." with the same confidence
    // either way presented brief-keyword drift tiebreaking as a considered
    // recommendation. Qualify instead of suppressing outright — the pick is
    // still a reasonable place to look first, it's just not a judgment.
    if (action.mode === 'refine_from_one' && action.preferred_candidate) {
      console.log('');
      if (action.reviewed) {
        info(`Next: sdlab refine --run ${flags.run} --pick ${action.preferred_candidate}`);
      } else {
        info(`No candidate has been reviewed yet — every image is at the rule-based pass's default "usable" ` +
          `until a human or LLM judge assesses fit.`);
        info(`If you want to proceed anyway: sdlab refine --run ${flags.run} --pick ${action.preferred_candidate} ` +
          `(picked by fewest rule-based drift issues, not by looking at the image).`);
      }
    } else if (action.mode === 'accept_one' && action.preferred_candidate) {
      console.log('');
      info(`Preferred candidate: ${action.preferred_candidate}`);
    }
  }
}
