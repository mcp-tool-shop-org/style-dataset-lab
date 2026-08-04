/**
 * H2: `overall_fit: 'usable'` (lib/critique-engine.js critiqueCandidate's
 * ONLY assignment site anywhere in the codebase — confirmed by grep, nothing
 * else ever sets it) means "nobody has assessed fit yet", not "assessed and
 * found uniformly usable". Before this fix, recommendAction() could not
 * distinguish those two states, so an unreviewed run took the identical
 * `refine_from_one` branch a genuinely-reviewed run would — picking a
 * "preferred" candidate by brief-keyword drift count, not by looking at the
 * image — and scripts/critique.js printed the same confident
 * "Next: sdlab refine --run X --pick <file>" suggestion either way.
 *
 * Scoping note (do not re-litigate — matches the finding's own scoping):
 * this does NOT build an LLM judge. That is documented, deliberate future
 * work (the project's own standards audit scored UNCERTAINTY_GATED_HUMANS
 * 2/3 for exactly this reason). The defect fixed here is the PRESENTATION —
 * critique.json's shape stays backward-compatible (only an additive
 * `reviewed` field on candidates and on recommended_action).
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { critiqueCandidate, recommendAction } from '../../lib/critique-engine.js';
import { REPO_ROOT } from '../../lib/paths.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, '..', '..', 'bin', 'sdlab.js');
const PROJECTS_DIR = join(REPO_ROOT, 'projects');

// ─── lib/critique-engine.js: the reviewed signal itself ───────────────────

function candidate(overrides = {}) {
  return critiqueCandidate({
    brief: { negative_prompt: 'blurry, low quality' },
    workflow: { drift_guards: [], canon_focus: [] },
    candidate: { filename: `${overrides.filename || 'c'}.png`, seed: 1 },
    activeDimensions: [],
    generatorModel: 'qwen-image:test',
  });
}

test('H2: critiqueCandidate marks its default overall_fit as reviewed:false — a non-judgment, not a judgment', () => {
  const c = candidate();
  assert.equal(c.overall_fit, 'usable');
  assert.equal(c.reviewed, false);
});

test('H2: recommendAction returns reviewed:false when every candidate sits at the unreviewed default, and qualifies the reason text', () => {
  const candidates = [candidate({ filename: 'a' }), candidate({ filename: 'b' }), candidate({ filename: 'c' })];
  const action = recommendAction({ candidates });
  assert.equal(action.mode, 'refine_from_one');
  assert.equal(action.reviewed, false);
  assert.match(action.reason, /nobody has assessed fit/i, `expected a qualified reason, got: "${action.reason}"`);
});

test('H2: recommendAction returns reviewed:true once at least one candidate has actually been reviewed, and does not qualify the reason', () => {
  const reviewedOne = { ...candidate({ filename: 'a' }), overall_fit: 'strong', reviewed: true };
  const action = recommendAction({ candidates: [reviewedOne, candidate({ filename: 'b' })] });
  assert.equal(action.reviewed, true);
  assert.doesNotMatch(action.reason, /nobody has assessed fit/i);
});

test('H2: recommendAction is explicit about reviewed:false on the empty-candidates branch too (no undefined leaking into critique.json)', () => {
  const action = recommendAction({ candidates: [] });
  assert.equal(action.reviewed, false);
});

// ─── scripts/critique.js CLI: the printed "Next:" suggestion ──────────────

function runCli(args) {
  const res = spawnSync(process.execPath, [BIN, ...args], {
    encoding: 'utf-8',
    env: { ...process.env, SDLAB_QUIET_FALLBACK: '1' },
  });
  return { stdout: res.stdout || '', stderr: res.stderr || '', status: res.status };
}

function scaffoldCritiqueProject(name, { runId = 'run_2026-01-01_001', workflowId = 'h2-test-workflow' } = {}) {
  const projectDir = join(PROJECTS_DIR, name);
  const runDir = join(projectDir, 'runs', runId);
  mkdirSync(runDir, { recursive: true });
  writeFileSync(join(runDir, 'manifest.json'), JSON.stringify({
    run_id: runId,
    outputs: [
      { filename: 'a.png', seed: 1, status: 'ok' },
      { filename: 'b.png', seed: 2, status: 'ok' },
    ],
  }, null, 2));
  writeFileSync(join(runDir, 'brief.json'), JSON.stringify({
    brief_id: 'brief_h2_test_001',
    workflow_id: workflowId,
    negative_prompt: 'blurry, low quality',
  }, null, 2));

  const wfDir = join(projectDir, 'workflows', 'profiles');
  mkdirSync(wfDir, { recursive: true });
  writeFileSync(join(wfDir, `${workflowId}.json`), JSON.stringify({
    workflow_id: workflowId,
    label: 'H2 test workflow',
    lane_id: 'concept',
    output_mode: 'portrait_set',
    output_count: 2,
    prompt_strategy: { style_prefix: ['x'], structure: 'style_prefix', must_include: [] },
    negative_strategy: { must_avoid: ['blurry'] },
    canon_focus: [],
    drift_guards: [],
    runtime_defaults: { adapter_target: 'comfyui' },
  }, null, 2));

  return { projectDir, runId };
}

test('H2 (CLI): sdlab critique does not print a confident "Next: sdlab refine" line when nothing has been reviewed', () => {
  const name = 'sdl-h2-critique-unreviewed';
  try {
    const { runId } = scaffoldCritiqueProject(name);
    const { stdout, status } = runCli(['critique', '--project', name, '--run', runId]);
    assert.equal(status, 0, `critique exited ${status}\n${stdout}`);

    // Before the fix: this line always printed once refine_from_one fired
    // (which it always does today — nothing sets overall_fit to anything
    // else). After the fix: suppressed in favor of an honest qualifier.
    assert.doesNotMatch(stdout, /^Next: sdlab refine/m, `expected no confident "Next:" line in an unreviewed run:\n${stdout}`);
    assert.match(stdout, /nobody has assessed fit|hasn't been reviewed|has been reviewed yet/i, `expected an honest "unreviewed" qualifier in:\n${stdout}`);
  } finally {
    rmSync(join(PROJECTS_DIR, name), { recursive: true, force: true });
  }
});
