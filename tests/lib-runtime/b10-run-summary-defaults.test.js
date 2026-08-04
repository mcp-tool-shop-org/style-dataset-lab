/**
 * Unit tests for B10 in lib/run-summary.js.
 *
 * `manifest.outputs` was indexed with no `|| []` fallback in FOUR spots
 * (buildRunSummary x2, renderRunMarkdown x1, renderRunText x2) while
 * `manifest.errors || []` two lines away was already defensive. A
 * legacy/truncated manifest (missing `outputs` entirely — e.g. hand-edited,
 * or from a schema version that used a different field name) crashed
 * `sdlab run show` with a bare TypeError instead of naming the missing
 * field.
 *
 * The finding named lines 15-16 (buildRunSummary) and 57/114 (the two
 * for-loops); this fix also covers lines 101-102 (renderRunText's own two
 * `.filter` calls), the identical defect in the same function, not
 * explicitly enumerated by line number but reproducible the same way.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildRunSummary, renderRunMarkdown, renderRunText } from '../../lib/run-summary.js';

function legacyManifestMissingOutputs() {
  // A manifest with NO `outputs` field at all — the exact shape a
  // legacy/truncated/hand-edited manifest.json can have.
  return {
    run_id: 'run_2026-01-01_001',
    brief_id: 'brief_1',
    project_id: 'p1',
    adapter_target: 'comfyui',
    output_mode: 'portrait_set',
    created_at: '2026-01-01T00:00:00.000Z',
    dry_run: false,
    success_count: 0,
    error_count: 0,
    output_count: 3,
    seed_plan: { base_seed: 1, seeds: [1, 2, 3] },
    checkpoint: 'model.safetensors',
    // outputs: intentionally absent
  };
}

test('buildRunSummary does not throw on a manifest with no outputs field (B10)', () => {
  const manifest = legacyManifestMissingOutputs();
  assert.doesNotThrow(() => buildRunSummary(manifest));
  const summary = buildRunSummary(manifest);
  assert.equal(summary.total_elapsed_ms, 0);
  assert.equal(summary.avg_elapsed_ms, 0);
});

test('renderRunMarkdown does not throw on a manifest with no outputs field (B10)', () => {
  const manifest = legacyManifestMissingOutputs();
  assert.doesNotThrow(() => renderRunMarkdown(manifest));
  const md = renderRunMarkdown(manifest);
  assert.match(md, /# Run: run_2026-01-01_001/);
});

test('renderRunText does not throw on a manifest with no outputs field (B10 — this is the exact `sdlab run show` crash)', () => {
  const manifest = legacyManifestMissingOutputs();
  assert.doesNotThrow(() => renderRunText(manifest));
  const text = renderRunText(manifest);
  assert.match(text, /Run: run_2026-01-01_001/);
  assert.match(text, /Results: 0\/3 succeeded/);
});

test('buildRunSummary/renderRunMarkdown/renderRunText still work correctly on a normal, well-formed manifest (no false positive)', () => {
  const manifest = {
    ...legacyManifestMissingOutputs(),
    outputs: [
      { index: 0, seed: 1, status: 'ok', filename: '001.png', elapsed_ms: 1000 },
      { index: 1, seed: 2, status: 'error', error: 'boom', elapsed_ms: 500 },
    ],
    errors: [{ index: 1, seed: 2, error: 'boom' }],
  };

  const summary = buildRunSummary(manifest);
  assert.equal(summary.total_elapsed_ms, 1000);
  assert.equal(summary.avg_elapsed_ms, 1000);

  const md = renderRunMarkdown(manifest);
  assert.match(md, /001\.png/);
  assert.match(md, /boom/);

  const text = renderRunText(manifest);
  assert.match(text, /001\.png/);
  assert.match(text, /Errors: 1/);
});
