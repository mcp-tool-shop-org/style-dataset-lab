/**
 * judgment-provenance — can it tell a fabricated rationale from a true one?
 *
 * The whole value of this module is DISCRIMINATION. A detector that flags
 * every corpus is worthless in the same way one that flags none is, so every
 * test below pairs a positive with the negative that nearly looks like it.
 *
 * The negative case is not hypothetical. `projects/tallow-fen` has 54 of 293
 * rationales reused verbatim — and they are legitimate: two strings, x28 and
 * x26, each accurately describing ONE systematic defect across exactly the
 * images that have it. An earlier revision of `formatProvenanceWarning`
 * asserted a Law 2 violation on reuse alone and therefore accused that corpus
 * of fabrication. These tests exist so that cannot come back.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  classifyJudgmentOrigin,
  auditJudgmentProvenance,
  formatProvenanceWarning,
  formatReuseNote,
  JUDGMENT_ORIGIN,
} from '../../lib/judgment-provenance.js';

const rec = (id, reviewer, explanation) => ({
  id,
  judgment: reviewer === null ? null : { reviewer, explanation, status: 'approved' },
});

// ── origin classification ────────────────────────────────────────────────

test('classifies the bulk-script reviewers that actually wrote the damage', () => {
  assert.equal(classifyJudgmentOrigin(rec('a', 'bulk_curate_v1', 'x')), JUDGMENT_ORIGIN.SCRIPT);
  assert.equal(classifyJudgmentOrigin(rec('b', 'bulk_curate_v2', 'x')), JUDGMENT_ORIGIN.SCRIPT);
  assert.equal(classifyJudgmentOrigin(rec('c', 'wave25-script', 'x')), JUDGMENT_ORIGIN.SCRIPT);
});

test('a human reviewer is not mistaken for a script', () => {
  assert.equal(classifyJudgmentOrigin(rec('a', 'human:mike', 'x')), JUDGMENT_ORIGIN.HUMAN);
  assert.equal(classifyJudgmentOrigin(rec('b', 'human', 'x')), JUDGMENT_ORIGIN.HUMAN);
});

test('an unrecognised reviewer is UNKNOWN, never assumed human', () => {
  // Assuming human is exactly how 948 fabricated rationales passed as
  // curation. `claude:fable-5` is a real reviewer id in tallow-fen — an LLM,
  // neither a person nor one of the known bulk scripts.
  assert.equal(classifyJudgmentOrigin(rec('a', 'claude:fable-5', 'x')), JUDGMENT_ORIGIN.UNKNOWN);
  assert.equal(classifyJudgmentOrigin(rec('b', 'some-new-tool', 'x')), JUDGMENT_ORIGIN.UNKNOWN);
});

test('a missing or empty judgment is NONE / UNKNOWN, not a silent pass', () => {
  assert.equal(classifyJudgmentOrigin(rec('a', null)), JUDGMENT_ORIGIN.NONE);
  assert.equal(classifyJudgmentOrigin({ id: 'b' }), JUDGMENT_ORIGIN.NONE);
  assert.equal(classifyJudgmentOrigin(rec('c', '   ', 'x')), JUDGMENT_ORIGIN.UNKNOWN);
});

// ── the discrimination that matters ──────────────────────────────────────

test('WARNS on a script-minted corpus (the star-freight shape)', () => {
  const canned = 'On-style gritty space costume. Faction-appropriate material vocabulary.';
  const records = [
    ...Array.from({ length: 40 }, (_, i) => rec(`s${i}`, 'bulk_curate_v2', canned)),
    ...Array.from({ length: 5 }, (_, i) => rec(`h${i}`, 'human:mike', `unique reason ${i}`)),
  ];
  const audit = auditJudgmentProvenance(records);

  assert.equal(audit.by_origin.script, 40);
  assert.equal(audit.by_origin.human, 5);

  const warning = formatProvenanceWarning(audit);
  assert.ok(warning, 'a script-minted corpus must produce a warning');
  assert.match(warning, /bulk script/);
  assert.match(warning, /Law 2/);
  // The neutral note must stay silent when the warning has already fired,
  // so the operator gets one message rather than two about one thing.
  assert.equal(formatReuseNote(audit), null);
});

test('does NOT accuse a human corpus that reuses a rationale (the tallow-fen shape)', () => {
  // 28 images genuinely share one systematic defect. The rationale is
  // accurate for every one of them. This is good curation of a bad wave.
  const realDefect = "style on-target but the style descriptor's lantern-light noun literalized";
  const records = [
    ...Array.from({ length: 28 }, (_, i) => rec(`d${i}`, 'human:mike', realDefect)),
    ...Array.from({ length: 20 }, (_, i) => rec(`u${i}`, 'human:mike', `distinct reason ${i}`)),
  ];
  const audit = auditJudgmentProvenance(records);

  assert.equal(audit.by_origin.script, 0);
  assert.ok(audit.reused_rationale_records >= 28, 'reuse is still measured and reported');

  // THE load-bearing assertion. Reuse alone must never produce the
  // fabrication warning — that was the bug.
  assert.equal(
    formatProvenanceWarning(audit),
    null,
    'reuse without a script reviewer must NOT be reported as fabrication',
  );

  const note = formatReuseNote(audit);
  assert.ok(note, 'it should still be surfaced, neutrally');
  assert.doesNotMatch(note, /Law 2|fabricat|uncurated/i, 'the note must not read as an accusation');
});

test('stays completely silent on a clean corpus', () => {
  const records = Array.from({ length: 30 }, (_, i) =>
    rec(`c${i}`, 'human:mike', `genuinely unique rationale number ${i}`));
  const audit = auditJudgmentProvenance(records);

  assert.equal(audit.by_origin.script, 0);
  assert.equal(audit.reused_rationale_records, 0);
  assert.equal(formatProvenanceWarning(audit), null);
  assert.equal(formatReuseNote(audit), null, 'a clean corpus gets no banner at all');
});

// ── the audit's own numbers ──────────────────────────────────────────────

test('reuse threshold excludes incidental sharing', () => {
  // Two records sharing a terse reason is coincidence; the threshold (3)
  // must not count it. 144 is not coincidence.
  const records = [
    rec('a', 'human:mike', 'out of focus'),
    rec('b', 'human:mike', 'out of focus'),
    rec('c', 'human:mike', 'unique'),
  ];
  const audit = auditJudgmentProvenance(records);
  assert.equal(audit.reused_rationale_records, 0, 'a pair is below threshold');

  const records3 = [...records, rec('d', 'human:mike', 'out of focus')];
  const audit3 = auditJudgmentProvenance(records3);
  assert.equal(audit3.reused_rationale_records, 3, 'three crosses it');
});

test('the audit never mutates the records it reads', () => {
  // The Director's ruling was "mark, don't touch". This module derives its
  // signal at read time; if it ever starts writing, this fails.
  const records = [rec('a', 'bulk_curate_v1', 'canned'), rec('b', 'human:mike', 'real')];
  const before = JSON.stringify(records);
  auditJudgmentProvenance(records);
  formatProvenanceWarning(auditJudgmentProvenance(records));
  assert.equal(JSON.stringify(records), before, 'records must be untouched');
});
