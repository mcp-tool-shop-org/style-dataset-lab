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

// --- Stacked workflow profile (two-LoRA stack contract D4) ---

test('character-portrait-stacked-flux loads with the required stacking block', async () => {
  const profile = await loadProfile('character-portrait-stacked-flux');
  assert.ok(profile.stacking, 'stacking block required on stacked workflow profiles');
  assert.equal(profile.stacking.default_world_lora_profile, 'character-style-lora-flux',
    'character-domain stacker must pair with character-style-lora-flux World by contract');
  assert.equal(profile.stacking.requires_character_lora, true,
    'stacked character portrait workflow must require a character LoRA');
  assert.equal(profile.stacking.allow_extra_lora, false,
    'D4 default: forbid extra LoRAs unless explicitly opted in');
});

test('character-portrait-stacked-flux enforces Flux 1 dev ≤3 LoRA cap', async () => {
  const profile = await loadProfile('character-portrait-stacked-flux');
  assert.ok(profile.stacking.max_loras <= 3,
    `Flux 1 dev cap is ≤3 LoRAs before quality degrades (got ${profile.stacking.max_loras})`);
});

test('character-portrait-stacked-flux default weights match contract §3', async () => {
  const profile = await loadProfile('character-portrait-stacked-flux');
  const w = profile.stacking.default_weights;
  // Contract §3: style 0.5/0.5, character 0.9/0.7 (starting values).
  assert.equal(w.world.strength_model, 0.5);
  assert.equal(w.world.strength_clip, 0.5);
  assert.equal(w.character.strength_model, 0.9);
  assert.equal(w.character.strength_clip, 0.7);
});

test('character-portrait-stacked-flux default weights sit inside contract bands', async () => {
  // Contract §3 bands (per LoRA role):
  //   style/world:  strength_model 0.3-0.6, strength_clip 0.3-0.7
  //   character:    strength_model 0.7-1.1, strength_clip 0.5-0.9
  const profile = await loadProfile('character-portrait-stacked-flux');
  const w = profile.stacking.default_weights;
  assert.ok(w.world.strength_model >= 0.3 && w.world.strength_model <= 0.6,
    `world.strength_model must be in [0.3, 0.6] (got ${w.world.strength_model})`);
  assert.ok(w.world.strength_clip >= 0.3 && w.world.strength_clip <= 0.7,
    `world.strength_clip must be in [0.3, 0.7] (got ${w.world.strength_clip})`);
  assert.ok(w.character.strength_model >= 0.7 && w.character.strength_model <= 1.1,
    `character.strength_model must be in [0.7, 1.1] (got ${w.character.strength_model})`);
  assert.ok(w.character.strength_clip >= 0.5 && w.character.strength_clip <= 0.9,
    `character.strength_clip must be in [0.5, 0.9] (got ${w.character.strength_clip})`);
});

test('character-portrait-stacked-flux load_order is world → character', async () => {
  const profile = await loadProfile('character-portrait-stacked-flux');
  assert.deepEqual(profile.stacking.load_order, ['world', 'character'],
    'contract §3: style → character load order for reproducibility');
});

test('character-portrait-stacked-flux preserves creative intent from character-portrait-set-flux', async () => {
  const base = await loadProfile('character-portrait-set-flux');
  const stacked = await loadProfile('character-portrait-stacked-flux');
  // Stacking is an engine change (two LoRAs instead of one). Creative contract
  // with the canon should stay intact.
  assert.equal(stacked.lane_id, base.lane_id);
  assert.equal(stacked.output_mode, base.output_mode);
  assert.deepEqual(stacked.canon_focus, base.canon_focus);
  assert.deepEqual(stacked.drift_guards, base.drift_guards);
});

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
