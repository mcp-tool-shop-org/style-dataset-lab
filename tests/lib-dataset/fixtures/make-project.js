/**
 * Tiny project fixture factory for lib-dataset tests.
 *
 * Creates a minimal tmp project with synthetic records so tests
 * exercise snapshot → split → export flow end-to-end.
 */

import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export function createTmpProject({ records = [], name = 'testproj' } = {}) {
  const projectRoot = mkdtempSync(join(tmpdir(), 'sdlab-test-'));
  mkdirSync(join(projectRoot, 'records'), { recursive: true });

  // Minimal project config files
  writeFileSync(
    join(projectRoot, 'project.json'),
    JSON.stringify({ meta: { name, display_name: name, domain: 'test', version: '1.0.0' } }, null, 2),
  );
  writeFileSync(
    join(projectRoot, 'constitution.json'),
    JSON.stringify({ version: '1.0.0', rules: [] }, null, 2),
  );
  writeFileSync(
    join(projectRoot, 'lanes.json'),
    JSON.stringify({
      default_lane: 'concept',
      lanes: [
        { id: 'concept', id_patterns: ['concept', 'subj_[0-9]*[02468]_'] },
        { id: 'portrait', id_patterns: ['portrait', 'subj_[0-9]*[13579]_', 'subject_[0-9]*[13579]_'] },
      ],
    }, null, 2),
  );
  writeFileSync(
    join(projectRoot, 'rubric.json'),
    JSON.stringify({ dimensions: [], thresholds: { pass: 0.6 } }, null, 2),
  );
  writeFileSync(
    join(projectRoot, 'terminology.json'),
    JSON.stringify({ groups: [] }, null, 2),
  );

  // Write records
  for (const rec of records) {
    writeFileSync(
      join(projectRoot, 'records', `${rec.id}.json`),
      JSON.stringify(rec, null, 2),
    );
  }

  return {
    projectRoot,
    cleanup() {
      try { rmSync(projectRoot, { recursive: true, force: true }); } catch { /* noop */ }
    },
  };
}

/** Build a minimal eligible record. */
export function makeRecord({
  id,
  status = 'approved',
  passCount = 5,
  assertionCount = 5,
  lane = 'concept',
  assetPath = null,
  identity = null,
  lineage = null,
} = {}) {
  return {
    id,
    schema_version: '2.1.0',
    created_at: '2025-01-01T00:00:00.000Z',
    asset_path: assetPath || `inputs/${id}.png`,
    image: { format: 'png', width: 1024, height: 1024, bytes: 1000 },
    provenance: { prompt: `${lane} reference for ${id}` },
    judgment: { status, failure_modes: [] },
    canon: {
      assertion_count: assertionCount,
      pass_count: passCount,
      assertions: Array.from({ length: assertionCount }, (_, i) => ({
        rule_id: `r${i}`,
        verdict: i < passCount ? 'pass' : 'fail',
      })),
    },
    ...(identity ? { identity } : {}),
    ...(lineage ? { lineage } : {}),
  };
}
