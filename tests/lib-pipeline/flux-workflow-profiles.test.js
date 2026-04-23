/**
 * Tests for the Flux-target ComfyUI workflow profiles.
 *
 * Verifies:
 *   - Each Flux profile loads as valid JSON with the expected schema shape
 *   - runtime_defaults are Flux-appropriate (low CFG, euler sampler, Flux checkpoint)
 *   - Content sections (prompt_strategy, negative_strategy, canon_focus,
 *     drift_guards) match the SDXL counterparts — the Flux migration
 *     changes the runtime, NOT the creative intent of each workflow.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

const PROFILES_DIR = join(
  import.meta.dirname,
  '..',
  '..',
  'projects',
  'star-freight',
  'workflows',
  'profiles'
);

const PAIRS = [
  ['character-portrait-set',    'character-portrait-set-flux'],
  ['environment-moodboard',     'environment-moodboard-flux'],
  ['expression-sheet',          'expression-sheet-flux'],
];

async function loadProfile(name) {
  const raw = await readFile(join(PROFILES_DIR, `${name}.json`), 'utf-8');
  return JSON.parse(raw);
}

// --- Schema presence ---

for (const [_sdxlName, fluxName] of PAIRS) {
  test(`${fluxName} loads with the expected top-level keys`, async () => {
    const profile = await loadProfile(fluxName);
    assert.ok(profile.workflow_id, 'workflow_id required');
    assert.ok(profile.label, 'label required');
    assert.ok(profile.description, 'description required');
    assert.ok(profile.lane_id, 'lane_id required');
    assert.ok(profile.prompt_strategy, 'prompt_strategy required');
    assert.ok(profile.negative_strategy, 'negative_strategy required');
    assert.ok(Array.isArray(profile.canon_focus), 'canon_focus must be array');
    assert.ok(Array.isArray(profile.drift_guards), 'drift_guards must be array');
    assert.ok(profile.runtime_defaults, 'runtime_defaults required');
  });
}

// --- Flux runtime defaults ---

for (const [_sdxlName, fluxName] of PAIRS) {
  test(`${fluxName} runtime_defaults target Flux (cfg ≤ 1.5, euler sampler, Flux checkpoint)`, async () => {
    const profile = await loadProfile(fluxName);
    const rt = profile.runtime_defaults;

    // Flux-dev is a distilled model — CFG should be near 1.0, never the
    // SDXL-era 6.5. Values above ~1.5 indicate the profile was copied
    // without updating the distilled-model guidance.
    assert.ok(rt.cfg <= 1.5, `Flux profiles must run near CFG 1.0 (got ${rt.cfg})`);

    // Steps in the Flux-dev recommended range (20-28).
    assert.ok(rt.steps >= 20 && rt.steps <= 28,
      `Flux-dev steps should be 20-28 (got ${rt.steps})`);

    // Sampler and scheduler should be Flux-appropriate. 'euler' + 'simple'
    // is the canonical Flux pairing; dpmpp_2m (SDXL default) would be a
    // regression signal.
    assert.equal(rt.sampler, 'euler',
      `Flux profiles should use 'euler' sampler (got '${rt.sampler}')`);
    assert.equal(rt.scheduler, 'simple',
      `Flux profiles should pair euler with 'simple' scheduler (got '${rt.scheduler}')`);

    // Checkpoint must name Flux — no SDXL checkpoints by accident.
    assert.ok(rt.checkpoint, 'runtime_defaults.checkpoint required for Flux profiles');
    assert.ok(/flux/i.test(rt.checkpoint),
      `checkpoint must name Flux (got '${rt.checkpoint}')`);
    assert.ok(!/sdxl|dreamshaper|stable-diffusion-xl/i.test(rt.checkpoint),
      `checkpoint must not reference SDXL (got '${rt.checkpoint}')`);
  });
}

// --- Creative intent preserved from SDXL counterparts ---

for (const [sdxlName, fluxName] of PAIRS) {
  test(`${fluxName} preserves creative intent from ${sdxlName}`, async () => {
    const sdxl = await loadProfile(sdxlName);
    const flux = await loadProfile(fluxName);

    // Lane and output mode describe what the workflow is FOR. These
    // should be identical — slice 4 changes the engine, not the intent.
    assert.equal(flux.lane_id, sdxl.lane_id, 'lane_id must match SDXL counterpart');
    assert.equal(flux.output_mode, sdxl.output_mode, 'output_mode must match SDXL counterpart');
    assert.equal(flux.output_count, sdxl.output_count, 'output_count must match SDXL counterpart');
    assert.equal(flux.subject_mode, sdxl.subject_mode, 'subject_mode must match SDXL counterpart');

    // Prompt/negative/canon/guard content is the creative contract with
    // the canon. Flux migration must not silently soften guards or drop
    // required elements.
    assert.deepEqual(flux.prompt_strategy, sdxl.prompt_strategy,
      'prompt_strategy must be preserved verbatim');
    assert.deepEqual(flux.negative_strategy, sdxl.negative_strategy,
      'negative_strategy must be preserved verbatim');
    assert.deepEqual(flux.canon_focus, sdxl.canon_focus,
      'canon_focus must be preserved verbatim');
    assert.deepEqual(flux.drift_guards, sdxl.drift_guards,
      'drift_guards must be preserved verbatim');
  });
}

// --- Naming contract ---

for (const [sdxlName, fluxName] of PAIRS) {
  test(`${fluxName} workflow_id matches its filename`, async () => {
    const profile = await loadProfile(fluxName);
    assert.equal(profile.workflow_id, fluxName,
      'workflow_id must equal the filename stem so batch tools can resolve it');
    assert.ok(profile.label.includes('(Flux)'),
      'label must carry the "(Flux)" suffix so operators can distinguish the two in UI/listings');
  });
}
