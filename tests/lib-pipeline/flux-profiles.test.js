/**
 * Integration tests for the Flux-target training profiles.
 *
 * Verifies:
 *   - Both Flux profiles load and pass validation
 *   - They declare target_family: flux, caption_strategy: flux-natural-language
 *   - They reference FLUX.1-dev in base_model_recommendations
 *   - Their adapter_targets resolve against the current registry
 *   - End-to-end: loading a profile and passing it to buildCaption emits
 *     the Flux natural-language sentence shape on a real approved record
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { loadTrainingProfile, validateProfile } from '../../lib/training-profiles.js';
import { buildCaption } from '../../lib/captions.js';

const PROJECT_ROOT = join(import.meta.dirname, '..', '..', 'projects', 'star-freight');

// --- Profile loading + validation ---

test('character-style-lora-flux profile loads and validates', async () => {
  const profile = await loadTrainingProfile(PROJECT_ROOT, 'character-style-lora-flux');
  const { valid, errors } = validateProfile(profile);
  assert.equal(valid, true, `validation errors: ${errors.join('; ')}`);
  assert.equal(profile.profile_id, 'character-style-lora-flux');
  assert.equal(profile.target_family, 'flux');
  assert.equal(profile.caption_strategy, 'flux-natural-language');
});

test('environment-mood-lora-flux profile loads and validates', async () => {
  const profile = await loadTrainingProfile(PROJECT_ROOT, 'environment-mood-lora-flux');
  const { valid, errors } = validateProfile(profile);
  assert.equal(valid, true, `validation errors: ${errors.join('; ')}`);
  assert.equal(profile.profile_id, 'environment-mood-lora-flux');
  assert.equal(profile.target_family, 'flux');
  assert.equal(profile.caption_strategy, 'flux-natural-language');
});

test('Flux profiles target FLUX.1-dev base model', async () => {
  const charProfile = await loadTrainingProfile(PROJECT_ROOT, 'character-style-lora-flux');
  assert.ok(
    charProfile.base_model_recommendations.some((m) => m.includes('FLUX.1-dev')),
    'character-style-lora-flux must recommend FLUX.1-dev'
  );

  const envProfile = await loadTrainingProfile(PROJECT_ROOT, 'environment-mood-lora-flux');
  assert.ok(
    envProfile.base_model_recommendations.some((m) => m.includes('FLUX.1-dev')),
    'environment-mood-lora-flux must recommend FLUX.1-dev'
  );
});

test('Flux profiles keep existing registered adapter targets', async () => {
  // Slice 2 does not add a new adapter (slice 3 work). Flux-target profiles
  // should reuse generic-image-caption and diffusers-lora, which produce
  // layouts ai-toolkit/diffusers can consume.
  const profile = await loadTrainingProfile(PROJECT_ROOT, 'character-style-lora-flux');
  assert.ok(profile.adapter_targets.includes('generic-image-caption'));
  assert.ok(profile.adapter_targets.includes('diffusers-lora'));
});

// --- End-to-end: profile drives caption strategy ---

test('loading Flux profile and building a caption produces NL sentence shape', async () => {
  const profile = await loadTrainingProfile(PROJECT_ROOT, 'character-style-lora-flux');

  const record = JSON.parse(
    await readFile(
      join(PROJECT_ROOT, 'records', 'anchor_03_officer_v3.json'),
      'utf-8'
    )
  );

  const caption = buildCaption(record, 'costume', 'compact', profile);

  // The Flux natural-language template: "[Trigger] style, a [Subject], [Scene]."
  assert.ok(caption.startsWith('character_style_lora_flux style,'),
    'Flux caption must lead with "<trigger> style,"');
  assert.ok(caption.includes('a compact faction costume'),
    'Flux caption must use prose subject with article ("a compact faction costume")');
  assert.ok(caption.includes('Steel-blue uniform, high collar, ship corridor'),
    'Flux caption must carry the judgment.explanation scene');

  // Must not leak generation-prompt style vocabulary
  assert.ok(!caption.includes('oil painting'));
  assert.ok(!caption.includes('painterly'));
  assert.ok(!caption.includes('directional lighting'));
});

// --- Coexistence with SDXL profiles ---

test('SDXL and Flux profiles coexist with different caption strategies', async () => {
  const sdxlProfile = await loadTrainingProfile(PROJECT_ROOT, 'character-style-lora');
  const fluxProfile = await loadTrainingProfile(PROJECT_ROOT, 'character-style-lora-flux');

  assert.equal(sdxlProfile.target_family, 'sdxl');
  assert.equal(fluxProfile.target_family, 'flux');
  assert.equal(sdxlProfile.caption_strategy, 'structured-metadata');
  assert.equal(fluxProfile.caption_strategy, 'flux-natural-language');

  // Same record, same context, different profile → different caption shape
  const record = JSON.parse(
    await readFile(
      join(PROJECT_ROOT, 'records', 'anchor_03_officer_v3.json'),
      'utf-8'
    )
  );

  const sdxlCaption = buildCaption(record, 'costume', 'compact', sdxlProfile);
  const fluxCaption = buildCaption(record, 'costume', 'compact', fluxProfile);

  assert.notEqual(sdxlCaption, fluxCaption);
  assert.ok(!sdxlCaption.includes(' style,'), 'SDXL caption should not use the "<trigger> style" prefix');
  assert.ok(fluxCaption.includes(' style,'), 'Flux caption must use the "<trigger> style" prefix');
});
