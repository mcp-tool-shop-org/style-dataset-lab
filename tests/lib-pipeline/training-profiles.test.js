/**
 * Validator tests for training profiles.
 *
 * Focused on the trigger_override field added for the two-LoRA stack contract
 * (research ref: two-LoRA stack D3, 2026-04-24). The existing REQUIRED_FIELDS
 * path is exercised indirectly by flux-profiles.test.js and others; these
 * tests pin down the new field's constraints.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateProfile } from '../../lib/training-profiles.js';

// Minimal baseline profile that satisfies all required fields + uses only
// registered adapters. Extend with `trigger_override` per-case.
function baseProfile(overrides = {}) {
  return {
    profile_id: 'character-style-lora-flux',
    label: 'Character Style LoRA (Flux)',
    target_family: 'flux',
    asset_type: 'lora',
    eligible_lanes: ['costume', 'equipment'],
    adapter_targets: ['generic-image-caption', 'diffusers-lora'],
    ...overrides,
  };
}

// --- Absent / null / undefined → valid ---

test('trigger_override: omitting the field passes validation (backward compat)', () => {
  const { valid, errors } = validateProfile(baseProfile());
  assert.equal(valid, true, `errors: ${errors.join('; ')}`);
});

test('trigger_override: explicit null passes validation', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: null }));
  assert.equal(valid, true, `errors: ${errors.join('; ')}`);
});

// --- Valid values ---

test('trigger_override: well-formed game-prefixed value passes', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: 'sf_character_style' }));
  assert.equal(valid, true, `errors: ${errors.join('; ')}`);
});

test('trigger_override: value with digits passes', () => {
  const { valid } = validateProfile(baseProfile({ trigger_override: 'sf_kael_maren_v2' }));
  assert.equal(valid, true);
});

test('trigger_override: minimal 2-char value passes when not on deny-list', () => {
  const { valid } = validateProfile(baseProfile({ trigger_override: 'gr' }));
  assert.equal(valid, true);
});

// --- Format violations ---

test('trigger_override: rejects non-string values', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: 42 }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('must be a string')),
    `expected "must be a string" error, got: ${errors.join('; ')}`);
});

test('trigger_override: rejects empty string (ambiguous intent)', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: '' }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('non-empty')),
    `expected non-empty-string error, got: ${errors.join('; ')}`);
});

test('trigger_override: rejects hyphens (T5 SentencePiece fragments unpredictably)', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: 'sf-character-style' }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('^[a-z0-9_]+$')),
    `expected format error, got: ${errors.join('; ')}`);
});

test('trigger_override: rejects uppercase', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: 'SF_Character' }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('^[a-z0-9_]+$')),
    `expected format error, got: ${errors.join('; ')}`);
});

test('trigger_override: rejects whitespace and punctuation', () => {
  for (const bad of ['sf style', 'sf.style', 'sf/style', 'sf!style']) {
    const { valid } = validateProfile(baseProfile({ trigger_override: bad }));
    assert.equal(valid, false, `expected "${bad}" to fail validation`);
  }
});

// --- Generic-suffix deny-list ---

test('trigger_override: rejects bare "style"', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: 'style' }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('generic suffix')),
    `expected deny-list error, got: ${errors.join('; ')}`);
  assert.ok(errors.some((e) => e.includes('sf_style')),
    'error should hint at game-prefixed fix');
});

test('trigger_override: rejects bare "character"', () => {
  const { valid, errors } = validateProfile(baseProfile({ trigger_override: 'character' }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('generic suffix')));
});

test('trigger_override: rejects bare "anime"', () => {
  const { valid } = validateProfile(baseProfile({ trigger_override: 'anime' }));
  assert.equal(valid, false);
});

test('trigger_override: rejects bare "realistic"', () => {
  const { valid } = validateProfile(baseProfile({ trigger_override: 'realistic' }));
  assert.equal(valid, false);
});

test('trigger_override: allows game-prefixed version of deny-list terms', () => {
  // The whole point of the deny-list is that *prefixed* versions are fine.
  for (const good of ['sf_style', 'sf_character', 'gr_anime', 'fr_realistic']) {
    const { valid, errors } = validateProfile(baseProfile({ trigger_override: good }));
    assert.equal(valid, true, `expected "${good}" to pass; got: ${errors.join('; ')}`);
  }
});

// --- entity_id_scope (D8 per-character LoRA row filter) ---

test('entity_id_scope: omitting the field passes validation (backward compat)', () => {
  const { valid } = validateProfile(baseProfile());
  assert.equal(valid, true);
});

test('entity_id_scope: explicit null passes validation', () => {
  const { valid } = validateProfile(baseProfile({ entity_id_scope: null }));
  assert.equal(valid, true);
});

test('entity_id_scope: well-formed game-prefixed value passes', () => {
  const { valid, errors } = validateProfile(baseProfile({ entity_id_scope: 'sf_kael_maren' }));
  assert.equal(valid, true, `errors: ${errors.join('; ')}`);
});

test('entity_id_scope: rejects non-string values', () => {
  const { valid, errors } = validateProfile(baseProfile({ entity_id_scope: 42 }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('must be a string')));
});

test('entity_id_scope: rejects empty string (ambiguous intent)', () => {
  const { valid, errors } = validateProfile(baseProfile({ entity_id_scope: '' }));
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes('non-empty')));
});

test('entity_id_scope: rejects hyphens and uppercase (same constraint as trigger_override)', () => {
  const { valid: v1 } = validateProfile(baseProfile({ entity_id_scope: 'sf-kael' }));
  assert.equal(v1, false);
  const { valid: v2 } = validateProfile(baseProfile({ entity_id_scope: 'SF_KAEL' }));
  assert.equal(v2, false);
});

test('entity_id_scope and trigger_override are independent fields', () => {
  const { valid, errors } = validateProfile(baseProfile({
    trigger_override: 'gr_heracles',
    entity_id_scope: 'heracles',
  }));
  assert.equal(valid, true, `errors: ${errors.join('; ')}`);
});
