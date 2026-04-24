/**
 * Unit tests for the shared caption builder.
 *
 * Covers both strategies:
 *   - legacy: preserves pre-refactor behavior for profiles without
 *     an explicit caption_strategy.
 *   - structured-metadata: research-backed strategy that uses only
 *     clean canon/judgment fields, never provenance.prompt.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildCaption, deriveStyleTrigger } from '../../lib/captions.js';

// --- Fixtures (shaped to match real approved anchor records) ---

const approvedRecord = {
  id: 'anchor_03_officer_v3',
  asset_path: 'outputs/approved/anchor_03_officer_v3.png',
  provenance: {
    prompt:
      'oil painting, semi-realistic painterly character concept art, muted dusty palette, ' +
      'subtle dark edges, soft upper-left directional lighting, human male fleet officer ' +
      'in his late 40s wearing a pressed steel-blue shipboard uniform jacket...',
  },
  judgment: {
    status: 'approved',
    explanation: 'Steel-blue uniform, high collar, ship corridor. Clean and institutional.',
  },
  canon: {
    faction: 'compact',
  },
};

const styleProfile = {
  profile_id: 'character-style-lora',
  caption_strategy: 'structured-metadata',
  prompt_strategy: 'trigger-word',
};

const fluxProfile = {
  profile_id: 'character-style-lora-flux',
  target_family: 'flux',
  caption_strategy: 'flux-natural-language',
  prompt_strategy: 'trigger-word',
};

const legacyProfile = {
  profile_id: 'legacy-profile',
  prompt_strategy: 'trigger-word',
  // no caption_strategy → legacy path
};

// --- deriveStyleTrigger ---

test('deriveStyleTrigger converts hyphenated profile id to underscore token', () => {
  assert.equal(deriveStyleTrigger({ profile_id: 'character-style-lora' }), 'character_style_lora');
});

test('deriveStyleTrigger returns null when profile_id is missing', () => {
  assert.equal(deriveStyleTrigger({}), null);
  assert.equal(deriveStyleTrigger(null), null);
  assert.equal(deriveStyleTrigger(undefined), null);
});

// --- structured-metadata strategy ---

test('structured-metadata caption uses trigger, faction, lane, and judgment explanation', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', styleProfile);
  assert.equal(
    caption,
    'character_style_lora, compact faction, costume, Steel-blue uniform, high collar, ship corridor. Clean and institutional.'
  );
});

test('structured-metadata caption never contains generation prompt vocabulary', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', styleProfile);
  // These tokens appear in provenance.prompt and would cause prompt bleed
  // if they leaked into the caption.
  assert.ok(!caption.includes('oil painting'));
  assert.ok(!caption.includes('painterly'));
  assert.ok(!caption.includes('muted dusty palette'));
  assert.ok(!caption.includes('directional lighting'));
});

test('structured-metadata caption dedupes group when it equals faction', () => {
  // When the partition group matches the canon faction, we emit it once
  // (via the "faction" segment) instead of twice.
  const caption = buildCaption(approvedRecord, 'costume', 'compact', styleProfile);
  const occurrences = (caption.match(/compact/g) || []).length;
  assert.equal(occurrences, 1);
});

test('structured-metadata caption keeps group when different from faction', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'bridge-officers', styleProfile);
  assert.ok(caption.includes('compact faction'));
  assert.ok(caption.includes('bridge-officers'));
});

test('structured-metadata caption omits missing fields cleanly', () => {
  const thin = { id: 'thin_01', judgment: {}, canon: {} };
  const caption = buildCaption(thin, null, null, styleProfile);
  assert.equal(caption, 'character_style_lora');
});

test('structured-metadata caption starts with trigger (first-position weighting)', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', styleProfile);
  assert.ok(caption.startsWith('character_style_lora'));
});

// --- legacy strategy (backward compatibility) ---

test('legacy caption preserves pre-refactor shape for profiles without caption_strategy', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', legacyProfile);
  // trigger, group, lane, prompt[0..200]
  assert.ok(caption.startsWith('legacy_profile, compact, costume, '));
  // Legacy DOES include sliced generation prompt — documented antipattern
  // kept only for reproducibility of any pre-existing training manifests.
  assert.ok(caption.includes('oil painting'));
});

test('legacy caption falls back to record id when provenance.prompt is absent', () => {
  const noPrompt = { id: 'hero_alpha_01', provenance: {}, judgment: {}, canon: {} };
  const caption = buildCaption(noPrompt, 'portrait', null, legacyProfile);
  assert.ok(caption.startsWith('legacy_profile, portrait, '));
  assert.ok(caption.includes('hero alpha 01'));
});

// --- flux-natural-language strategy ---

test('flux-natural-language caption uses natural-language sentence shape', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', fluxProfile);
  assert.equal(
    caption,
    'character_style_lora_flux style, a compact faction costume, Steel-blue uniform, high collar, ship corridor. Clean and institutional.'
  );
});

test('flux-natural-language caption starts with trigger + " style" (research template)', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', fluxProfile);
  assert.ok(caption.startsWith('character_style_lora_flux style,'),
    'Flux template per Pelayo Arbues: [Trigger] style, [Subject], [Scene]');
});

test('flux-natural-language caption never contains generation prompt vocabulary', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', fluxProfile);
  assert.ok(!caption.includes('oil painting'));
  assert.ok(!caption.includes('painterly'));
  assert.ok(!caption.includes('muted dusty palette'));
  assert.ok(!caption.includes('directional lighting'));
});

test('flux-natural-language caption uses article "a" before subject noun phrase', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', fluxProfile);
  // Prose shape, not comma-tag-list: the subject should be a noun phrase
  // with an article, not "compact, costume" bare tags.
  assert.ok(caption.includes('a compact faction costume'));
});

test('flux-natural-language caption omits missing fields cleanly', () => {
  const thin = { id: 'thin_01', judgment: {}, canon: {} };
  const caption = buildCaption(thin, null, null, fluxProfile);
  // Should be just the trigger segment, no stray "a " or trailing comma
  assert.equal(caption, 'character_style_lora_flux style');
});

test('flux-natural-language caption falls back to group when lane is absent', () => {
  const caption = buildCaption(approvedRecord, null, 'bridge-officers', fluxProfile);
  // lane is null, group is different from faction → group goes into subject
  assert.ok(caption.includes('a compact faction bridge-officers'));
});

test('flux-natural-language caption handles missing profile_id (no trigger)', () => {
  const noTrigger = { target_family: 'flux', caption_strategy: 'flux-natural-language' };
  const caption = buildCaption(approvedRecord, 'costume', 'compact', noTrigger);
  // Trigger segment absent; still starts with subject noun phrase
  assert.ok(caption.startsWith('a compact faction costume'));
});

// --- strategy routing ---

test('unknown caption_strategy falls back to legacy', () => {
  const weird = { ...legacyProfile, caption_strategy: 'not-a-real-strategy' };
  const caption = buildCaption(approvedRecord, 'costume', 'compact', weird);
  // Should produce the same shape as the legacy path
  assert.ok(caption.includes('oil painting'));
});

test('missing profile object does not throw', () => {
  assert.doesNotThrow(() => buildCaption(approvedRecord, 'costume', 'compact', null));
  assert.doesNotThrow(() => buildCaption(approvedRecord, 'costume', 'compact', undefined));
});

// --- trigger_override behavior (two-LoRA stack D3) ---
//
// `trigger_override` lets a profile decouple its training trigger from the
// profile_id — descriptive IDs stay descriptive, triggers stay compact and
// game-prefixed. The field is purely additive: when absent, behavior must
// be bit-identical to the pre-override implementation.

test('deriveStyleTrigger: trigger_override replaces the derived token', () => {
  assert.equal(
    deriveStyleTrigger({ profile_id: 'character-style-lora-flux', trigger_override: 'sf_char_style' }),
    'sf_char_style'
  );
});

test('deriveStyleTrigger: trigger_override wins over profile_id derivation', () => {
  // Even when profile_id exists, the override takes precedence.
  const withOverride = { profile_id: 'any-id-here', trigger_override: 'sf_world' };
  assert.equal(deriveStyleTrigger(withOverride), 'sf_world');
});

test('deriveStyleTrigger: empty-string trigger_override falls through to profile_id', () => {
  // Empty string is treated as "not set" so partial configs don't silently
  // strip the trigger entirely.
  assert.equal(
    deriveStyleTrigger({ profile_id: 'character-style-lora', trigger_override: '' }),
    'character_style_lora'
  );
});

test('deriveStyleTrigger: non-string trigger_override is ignored', () => {
  assert.equal(
    deriveStyleTrigger({ profile_id: 'character-style-lora', trigger_override: 123 }),
    'character_style_lora'
  );
  assert.equal(
    deriveStyleTrigger({ profile_id: 'character-style-lora', trigger_override: null }),
    'character_style_lora'
  );
});

test('buildCaption (flux-natural-language): trigger_override flows through to the caption', () => {
  const profile = {
    profile_id: 'character-style-lora-flux',
    target_family: 'flux',
    caption_strategy: 'flux-natural-language',
    prompt_strategy: 'trigger-word',
    trigger_override: 'sf_character_style',
  };
  const caption = buildCaption(approvedRecord, 'costume', 'compact', profile);
  assert.ok(caption.startsWith('sf_character_style style,'),
    'Flux caption must use the override token, not the hyphenated id');
  assert.ok(!caption.includes('character_style_lora_flux'),
    'Flux caption must not contain the default derived token when override is set');
});

test('buildCaption (structured-metadata): trigger_override flows through to the caption', () => {
  const profile = {
    profile_id: 'character-style-lora',
    caption_strategy: 'structured-metadata',
    prompt_strategy: 'trigger-word',
    trigger_override: 'sf_char',
  };
  const caption = buildCaption(approvedRecord, 'costume', 'compact', profile);
  assert.ok(caption.startsWith('sf_char, '),
    'SDXL caption must lead with the override token');
});

// --- Backward-compat snapshot ---
//
// D3 of the two-LoRA research requires rigorous proof that profiles WITHOUT
// trigger_override emit bit-identical captions to the pre-override
// implementation. These snapshots are the canonical "before" — any change to
// them must be intentional and land with a corresponding note, because they
// are the contract surface existing training manifests depend on.

test('backward-compat snapshot: legacy caption unchanged without trigger_override', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', legacyProfile);
  // Legacy shape: trigger, group, lane, prompt.slice(0, 200). The 200-char
  // window lands inside "wearing a pressed s[teel-blue]"; changing either
  // the window width or the segment ordering fails this snapshot.
  assert.equal(
    caption,
    'legacy_profile, compact, costume, oil painting, semi-realistic painterly character concept art, muted dusty palette, subtle dark edges, soft upper-left directional lighting, human male fleet officer in his late 40s wearing a pressed s'
  );
});

test('backward-compat snapshot: structured-metadata caption unchanged without trigger_override', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', styleProfile);
  assert.equal(
    caption,
    'character_style_lora, compact faction, costume, Steel-blue uniform, high collar, ship corridor. Clean and institutional.'
  );
});

test('backward-compat snapshot: flux-natural-language caption unchanged without trigger_override', () => {
  const caption = buildCaption(approvedRecord, 'costume', 'compact', fluxProfile);
  assert.equal(
    caption,
    'character_style_lora_flux style, a compact faction costume, Steel-blue uniform, high collar, ship corridor. Clean and institutional.'
  );
});

test('backward-compat: adding trigger_override: null is indistinguishable from omitting it', () => {
  const plain = buildCaption(approvedRecord, 'costume', 'compact', fluxProfile);
  const withNull = buildCaption(approvedRecord, 'costume', 'compact', { ...fluxProfile, trigger_override: null });
  const withUndef = buildCaption(approvedRecord, 'costume', 'compact', { ...fluxProfile, trigger_override: undefined });
  const withEmpty = buildCaption(approvedRecord, 'costume', 'compact', { ...fluxProfile, trigger_override: '' });
  assert.equal(withNull, plain);
  assert.equal(withUndef, plain);
  assert.equal(withEmpty, plain);
});
