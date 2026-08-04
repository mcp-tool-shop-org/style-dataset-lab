/**
 * SDL-H1 — buildCaption('subject-natural-language') must FAIL LOUD when
 * canon.subject is missing, never silently fall back to
 * buildFluxNaturalLanguageCaption (which reads judgment.explanation — a
 * curation field, not scene content).
 *
 * Real-world defect: projects/salt-road/records/*.json carry records where
 * judgment.explanation holds Director curation rulings ("Director ruling
 * 2026-07-30: cull the flat and crude...") rather than scene descriptions.
 * The project's training profile sets caption_strategy: 'subject-natural-language'.
 * Before this fix, a record missing canon.subject would silently caption
 * from that ruling text — reintroducing exactly the prompt-bleed antipattern
 * buildSubjectNaturalLanguageCaption's own docstring says it exists to prevent.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildCaption } from '../../lib/captions.js';

const subjectProfile = {
  profile_id: 'saltroad-style-lora',
  caption_strategy: 'subject-natural-language',
  prompt_strategy: 'trigger-word',
};

// Modeled directly on the real salt-road defect records: judgment.explanation
// carries a Director curation ruling, canon.subject was never populated.
const recordWithNoSubject = {
  id: 'salt-road-env-014',
  provenance: {
    prompt: 'oil painting, painterly early-modern trading port, muted palette...',
  },
  judgment: {
    status: 'rejected',
    explanation: 'Director ruling 2026-07-30: cull the flat and crude lighting, resubmit with better depth.',
  },
  canon: {
    // subject intentionally absent — this is the defect condition
  },
};

const recordWithSubject = {
  id: 'salt-road-env-015',
  provenance: {
    prompt: 'oil painting, painterly early-modern trading port, muted palette...',
  },
  judgment: {
    status: 'approved',
    explanation: 'Director ruling 2026-07-30: pool look approved, ship it.',
  },
  canon: {
    subject: 'a fog-wrapped harbor quay at dawn, moored cogs, gulls overhead',
  },
};

// --- RED-branch coverage: missing/blank subject fails loud ---

test('subject-natural-language: throws CAPTION_SUBJECT_MISSING when canon.subject is absent', () => {
  assert.throws(
    () => buildCaption(recordWithNoSubject, 'environment', null, subjectProfile),
    (err) => {
      assert.equal(err.code, 'CAPTION_SUBJECT_MISSING');
      return true;
    },
  );
});

test('subject-natural-language: thrown error names the record id', () => {
  assert.throws(
    () => buildCaption(recordWithNoSubject, 'environment', null, subjectProfile),
    (err) => {
      assert.match(err.message, /salt-road-env-014/);
      assert.match(err.hint, /salt-road-env-014/);
      return true;
    },
  );
});

test('subject-natural-language: thrown hint tells the operator what to populate', () => {
  assert.throws(
    () => buildCaption(recordWithNoSubject, 'environment', null, subjectProfile),
    (err) => {
      assert.match(err.hint, /canon\.subject/);
      return true;
    },
  );
});

test('subject-natural-language: NEVER produces a caption containing curation/judgment text on the missing-subject path', () => {
  // The whole point of the fix: no caption string is ever synthesized from
  // judgment.explanation for this strategy. Assert this two ways — (a) the
  // call throws instead of returning, and (b) if by some regression it ever
  // did return a string, it must not contain the curation text. (b) is a
  // belt-and-suspenders check that survives even if someone changes throw
  // to a soft-return later without reading this test.
  let caption;
  let threw = false;
  try {
    caption = buildCaption(recordWithNoSubject, 'environment', null, subjectProfile);
  } catch {
    threw = true;
  }
  assert.equal(threw, true, 'must throw rather than return a caption');
  assert.equal(caption, undefined);
});

test('subject-natural-language: blank-string canon.subject also fails loud (whitespace-only)', () => {
  const blank = { ...recordWithSubject, canon: { subject: '   ' } };
  assert.throws(
    () => buildCaption(blank, 'environment', null, subjectProfile),
    (err) => err.code === 'CAPTION_SUBJECT_MISSING',
  );
});

test('subject-natural-language: non-string canon.subject also fails loud', () => {
  const wrongType = { ...recordWithSubject, canon: { subject: 42 } };
  assert.throws(
    () => buildCaption(wrongType, 'environment', null, subjectProfile),
    (err) => err.code === 'CAPTION_SUBJECT_MISSING',
  );
});

// --- Happy path: unaffected when canon.subject IS populated ---

test('subject-natural-language: builds trigger + subject when canon.subject is present', () => {
  const caption = buildCaption(recordWithSubject, 'environment', null, subjectProfile);
  assert.equal(
    caption,
    'saltroad_style_lora style, a fog-wrapped harbor quay at dawn, moored cogs, gulls overhead',
  );
});

test('subject-natural-language: happy path never leaks judgment.explanation even though it is present on the record', () => {
  const caption = buildCaption(recordWithSubject, 'environment', null, subjectProfile);
  assert.ok(!caption.includes('Director ruling'));
  assert.ok(!caption.includes('pool look approved'));
});

test('subject-natural-language: happy path never leaks provenance.prompt', () => {
  const caption = buildCaption(recordWithSubject, 'environment', null, subjectProfile);
  assert.ok(!caption.includes('oil painting'));
  assert.ok(!caption.includes('muted palette'));
});

test('subject-natural-language: trailing period on canon.subject is stripped (no double period)', () => {
  const withPeriod = { ...recordWithSubject, canon: { subject: 'a quiet harbor at dawn.' } };
  const caption = buildCaption(withPeriod, 'environment', null, subjectProfile);
  assert.equal(caption, 'saltroad_style_lora style, a quiet harbor at dawn');
});

// --- Backward compatibility: other strategies unaffected by this fix ---

test('other strategies (flux-natural-language) are untouched by the subject-natural-language fix', () => {
  const fluxProfile = {
    profile_id: 'character-style-lora-flux',
    target_family: 'flux',
    caption_strategy: 'flux-natural-language',
  };
  // This record has judgment.explanation and no canon.subject — under
  // flux-natural-language (a DIFFERENT strategy, used correctly by projects
  // whose judgment.explanation legitimately IS scene text), that is fine and
  // must not throw.
  const record = {
    id: 'sf_officer_01',
    judgment: { explanation: 'Steel-blue uniform, high collar, ship corridor.' },
    canon: { faction: 'compact' },
  };
  assert.doesNotThrow(() => buildCaption(record, 'costume', 'compact', fluxProfile));
});

test('other strategies (structured-metadata) are untouched by the subject-natural-language fix', () => {
  const styleProfile = {
    profile_id: 'character-style-lora',
    caption_strategy: 'structured-metadata',
  };
  const record = {
    id: 'sf_officer_01',
    judgment: { explanation: 'Steel-blue uniform, high collar, ship corridor.' },
    canon: { faction: 'compact' },
  };
  assert.doesNotThrow(() => buildCaption(record, 'costume', 'compact', styleProfile));
});
