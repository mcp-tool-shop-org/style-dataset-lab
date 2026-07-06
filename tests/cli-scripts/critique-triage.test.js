/**
 * Tests for the UNCERTAINTY_GATED_HUMANS triage view — triageCandidates (the
 * pure filter) + renderCritiqueTriage (the contrastive terminal render).
 *
 * The gate: a candidate needs a human when it is `off-model` OR carries
 * >= driftThreshold drift issues. Everything else is suppressed — attention
 * gates on uncertainty, not on every item (Buçinca et al. arXiv:2410.04253).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { triageCandidates, DEFAULT_DRIFT_THRESHOLD } from '../../lib/critique-engine.js';
import { renderCritiqueTriage } from '../../lib/critique-render.js';

function cand(filename, overall_fit, driftCount) {
  return {
    filename,
    seed: 1,
    overall_fit,
    drift_issues: Array.from({ length: driftCount }, (_, i) => `drift ${i}`),
    strengths: [],
    preserve_next_pass: [],
    correct_next_pass: [],
  };
}

test('triageCandidates flags off-model regardless of drift count', () => {
  const { flagged, suppressed } = triageCandidates([cand('a.png', 'off-model', 0)]);
  assert.equal(flagged.length, 1);
  assert.equal(suppressed.length, 0);
});

test('triageCandidates flags on >= driftThreshold and suppresses below it', () => {
  const candidates = [
    cand('low.png', 'usable', 1),
    cand('at.png', 'usable', 3),
    cand('high.png', 'usable', 8),
  ];
  const { flagged, suppressed, driftThreshold } = triageCandidates(candidates, { driftThreshold: 3 });
  assert.equal(driftThreshold, 3);
  assert.deepEqual(flagged.map(c => c.filename), ['at.png', 'high.png']);
  assert.deepEqual(suppressed.map(c => c.filename), ['low.png']);
});

test('triageCandidates default threshold matches DEFAULT_DRIFT_THRESHOLD', () => {
  const { flagged } = triageCandidates([cand('x.png', 'usable', DEFAULT_DRIFT_THRESHOLD)]);
  assert.equal(flagged.length, 1);
  const { flagged: none } = triageCandidates([cand('y.png', 'usable', DEFAULT_DRIFT_THRESHOLD - 1)]);
  assert.equal(none.length, 0);
});

test('renderCritiqueTriage leads contrastively and shows only flagged', () => {
  const report = { run_id: 'run_1', brief_id: 'b1', workflow_id: 'w1' };
  const candidates = [
    cand('keep.png', 'off-model', 0),
    cand('skip1.png', 'usable', 0),
    cand('skip2.png', 'usable', 1),
  ];
  const triage = triageCandidates(candidates, { driftThreshold: 3 });
  const out = renderCritiqueTriage(report, triage);
  assert.match(out, /Default: SKIP 2\/3/);          // contrastive: states what's skipped
  assert.match(out, /Attention gates on uncertainty/); // the research framing
  assert.match(out, /keep\.png/);                    // flagged candidate shown
  assert.doesNotMatch(out, /skip1\.png/);            // suppressed candidate hidden
});

test('renderCritiqueTriage reports the empty case honestly', () => {
  const report = { run_id: 'run_2', brief_id: 'b', workflow_id: 'w' };
  const triage = triageCandidates([cand('a.png', 'usable', 0), cand('b.png', 'usable', 1)], { driftThreshold: 3 });
  const out = renderCritiqueTriage(report, triage);
  assert.match(out, /nothing flagged/);
  assert.match(out, /Default: SKIP 2\/2/);
});
