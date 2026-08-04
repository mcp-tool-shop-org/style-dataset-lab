/**
 * Implementation example packs.
 *
 * Shows how to use the trained asset in practice: prompt examples,
 * lane-targeted examples, subject continuity examples, known failure
 * cases, and re-ingest guidance.
 *
 * Every implementation pack is tied to a training manifest.
 */

import { readFile, writeFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { loadTrainingManifest } from './training-manifests.js';
import { loadTrainingProfile } from './training-profiles.js';
import { loadProjectConfig, detectLane, detectGroup } from './config.js';
import { loadSplitPartition } from './split.js';
import { loadRecord } from './records.js';
import { SCHEMA_VERSION, checkManifestVersion, claimIdDir } from './snapshot.js';
import { warn } from './log.js';

function generateImplId() {
  const now = new Date();
  const date = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = randomBytes(2).toString('hex');
  return `impl-${date.slice(0, 8)}-${date.slice(8, 14)}-${rand}`;
}

/**
 * Build an implementation pack from a training manifest.
 *
 * @param {string} projectRoot
 * @param {string} manifestId
 * @returns {Promise<{implId: string, prompts: number, failures: number, subjects: number}>}
 */
export async function buildImplementationPack(projectRoot, manifestId) {
  const manifest = await loadTrainingManifest(projectRoot, manifestId);
  const profile = await loadTrainingProfile(projectRoot, manifest.training_profile_id);
  const config = loadProjectConfig(projectRoot);
  const recordsDir = join(projectRoot, 'records');

  // Load test partition records (best for implementation examples)
  const testEntries = await loadSplitPartition(projectRoot, manifest.source_split_id, 'test');

  // Also load some train records for broader coverage
  const trainEntries = await loadSplitPartition(projectRoot, manifest.source_split_id, 'train');

  // F3: a record the split promised (via source_split_id's train/test
  // partitions) whose file was later deleted from records/ must not
  // silently drop out of the implementation pack with no counter, no
  // warning, no id recorded. loadRecord() returns null on ENOENT
  // (lib/records.js); previously `if (!record) continue` was the entire
  // handling at both loops below. WARN + ledger (not hard-fail): an
  // implementation pack is an illustrative/example artifact, not the
  // Law-4 reproducibility-guaranteeing one (export.js and
  // training-packages.js are, and hard-fail on the identical situation).
  const missingRecords = [];

  // Build prompt examples — per-lane best records
  const promptExamples = [];
  const laneExamples = new Map();

  for (const entry of [...testEntries, ...trainEntries.slice(0, 50)]) {
    const record = await loadRecord(recordsDir, entry.record_id);
    if (!record) {
      missingRecords.push({ record_id: entry.record_id, stage: 'implementation-pack', source: 'prompt-examples' });
      continue;
    }
    if (record.judgment?.status !== 'approved') continue;

    const prompt = record.provenance?.prompt || '';
    const lane = detectLane(record.id, prompt, config.lanes);
    const group = detectGroup(record.id, prompt, config.terminology);

    // Filter by profile lanes
    if (profile.eligible_lanes.length > 0 && !profile.eligible_lanes.includes(lane)) continue;

    if (!laneExamples.has(lane)) laneExamples.set(lane, []);
    if (laneExamples.get(lane).length < 3) {
      laneExamples.get(lane).push(record);

      const passRatio = record.canon?.assertion_count > 0
        ? record.canon.pass_count / record.canon.assertion_count : 0;

      promptExamples.push({
        record_id: record.id,
        lane,
        group: group || 'unknown',
        prompt: prompt.slice(0, 500),
        pass_ratio: +passRatio.toFixed(3),
        asset_path: record.asset_path,
        usage_note: `Use as ${lane} reference for ${group || 'general'} style`,
      });
    }
  }

  // Build known failure cases from rejected records
  const knownFailures = [];
  const allFiles = (await readdir(recordsDir)).filter(f => f.endsWith('.json')).sort();
  let failCount = 0;
  // F4: adopt the DB-003 pattern already proven in snapshot.js's
  // createSnapshot (and mirrored in eval-pack.js's buildEvalPack) — this
  // loop was the one place left in the codebase still doing a bare
  // JSON.parse per record file with no try/catch. One truncated/corrupt
  // record file threw a filename-free SyntaxError here and discarded the
  // prompt-examples work (the loop above) and the subject-continuity work
  // (the loop below) this function had already computed, since every
  // artifact is written to disk only at the very end of
  // buildImplementationPack — skip, count, warn, continue instead.
  const unreadable = [];

  for (const file of allFiles) {
    if (failCount >= 10) break;
    let record;
    try {
      record = JSON.parse(await readFile(join(recordsDir, file), 'utf-8'));
    } catch (err) {
      unreadable.push({ record_id: file.replace(/\.json$/, ''), file, error: err.message });
      continue;
    }
    if (record.judgment?.status !== 'rejected') continue;

    const prompt = record.provenance?.prompt || '';
    const lane = detectLane(record.id, prompt, config.lanes);
    if (profile.eligible_lanes.length > 0 && !profile.eligible_lanes.includes(lane)) continue;

    const failureModes = record.judgment?.failure_modes || [];
    if (failureModes.length === 0 && !record.judgment?.explanation) continue;

    knownFailures.push({
      record_id: record.id,
      lane,
      failure_modes: failureModes,
      explanation: record.judgment?.explanation || null,
      lesson: `Avoid: ${failureModes.join(', ') || record.judgment?.explanation?.slice(0, 100)}`,
    });
    failCount++;
  }
  // F4: surface unreadable records loudly (DB-003 parity) — same shape,
  // same warn() visibility as snapshot.js's createSnapshot.
  if (unreadable.length > 0) {
    const sample = unreadable.slice(0, 5).map(u => u.file).join(', ');
    warn(
      `implementation-pack: ${unreadable.length} record file(s) were unreadable and skipped` +
      (unreadable.length > 5 ? ` (first 5: ${sample}, ...)` : ` (${sample})`),
    );
  }

  // Build subject continuity examples
  const subjectExamples = [];
  const bySubject = new Map();

  for (const entry of [...testEntries, ...trainEntries]) {
    const record = await loadRecord(recordsDir, entry.record_id);
    // F3: keep "record file is missing" (a data-integrity problem worth a
    // warning) distinct from "record loaded fine but simply has no
    // identity.subject_name" (the normal, expected case for most records —
    // not a missing-record situation). The original combined
    // `!record?.identity?.subject_name` check could not tell these apart.
    if (!record) {
      missingRecords.push({ record_id: entry.record_id, stage: 'implementation-pack', source: 'subject-continuity' });
      continue;
    }
    if (!record.identity?.subject_name) continue;
    const name = record.identity.subject_name;
    if (!bySubject.has(name)) bySubject.set(name, []);
    bySubject.get(name).push(record);
  }

  // F3: warn once for both loops combined — the ledger records which
  // loop(s) actually hit the miss via `source`, so the summary line stays
  // useful even though it's a single warning for the whole pack build.
  if (missingRecords.length > 0) {
    const sample = missingRecords.slice(0, 10).map(m => `${m.record_id} (${m.source})`);
    warn(
      `implementation-pack: ${missingRecords.length} record(s) referenced by split "${manifest.source_split_id}" ` +
      `could not be loaded from ${recordsDir}` +
      (missingRecords.length > 10 ? ` — first 10: ${sample.join(', ')}, ...` : ` — ${sample.join(', ')}`),
    );
  }

  for (const [name, records] of [...bySubject].sort((a, b) => b[1].length - a[1].length).slice(0, 5)) {
    subjectExamples.push({
      subject_name: name,
      record_count: records.length,
      record_ids: records.map(r => r.id).sort(),
      faction: records[0].identity?.faction || null,
      note: `${records.length} views of ${name} — use to verify identity consistency`,
    });
  }

  // Build expected behaviors
  const expectedBehaviors = {
    style_markers: buildStyleMarkers(profile, config),
    forbidden_patterns: buildForbiddenPatterns(config),
    quality_thresholds: config.rubric.thresholds || {},
  };

  // Write implementation pack
  // SDL-M10: atomically claim the implementation-pack id/dir — closes the
  // check-then-act race the old existsSync+recursive-mkdir pattern had
  // (D-005's intent, now actually race-proof; see claimIdDir in snapshot.js).
  const { id: implId, dir: implDir } = await claimIdDir(
    join(projectRoot, 'training', 'implementations'),
    generateImplId,
    {
      code: 'IMPL_PACK_ID_COLLISION',
      message: 'Could not claim a unique implementation-pack ID — every candidate collided with an existing implementation-pack directory.',
      hint: 'Retry; if this persists, another sdlab process may be creating implementation packs in a tight loop.',
    },
  );

  const implManifest = {
    // DB-001 / DB-006: stamp manifest schema version
    schema_version: SCHEMA_VERSION,
    implementation_pack_id: implId,
    created_at: new Date().toISOString(),
    created_by: 'sdlab-implementation-v1',
    training_manifest_id: manifestId,
    training_profile_id: manifest.training_profile_id,
    counts: {
      prompt_examples: promptExamples.length,
      known_failures: knownFailures.length,
      subject_examples: subjectExamples.length,
      lanes_covered: laneExamples.size,
      // F3: how many split-referenced records could not be loaded while
      // building this pack. 0 in the common case; see missing_records
      // below for the actual ids.
      missing_records: missingRecords.length,
      // F4: how many record files (from the known-failures scan over ALL
      // of records/) existed but threw on JSON.parse — distinct from
      // missing_records above, which is "no file at all". 0 in the common
      // case; see unreadable_records below for the actual files.
      unreadable_records: unreadable.length,
    },
    // F3: ledger of every record_id that failed to load while building
    // this pack (mirrors the images_failed pattern export.js established
    // at export time) — record_id + stage + which loop hit it, so an
    // operator can trace it without re-diffing the split against records/.
    missing_records: missingRecords,
    // F4: ledger of record files that existed but failed to JSON.parse
    // (DB-003 parity with snapshot.js's `errors` field).
    unreadable_records: unreadable,
  };

  await writeFile(join(implDir, 'manifest.json'), JSON.stringify(implManifest, null, 2) + '\n');
  await writeFile(join(implDir, 'prompts.jsonl'), promptExamples.map(p => JSON.stringify(p)).join('\n') + '\n');
  await writeFile(join(implDir, 'known-failures.json'), JSON.stringify(knownFailures, null, 2) + '\n');
  await writeFile(join(implDir, 'expected-behaviors.json'), JSON.stringify(expectedBehaviors, null, 2) + '\n');

  if (subjectExamples.length > 0) {
    await writeFile(join(implDir, 'subject-continuity.json'), JSON.stringify(subjectExamples, null, 2) + '\n');
  }

  // Write eval tasks JSONL — tasks that can be run against generated outputs
  const evalTasks = promptExamples.map(p => ({
    task: 'generate_and_compare',
    prompt: p.prompt,
    lane: p.lane,
    reference_record: p.record_id,
    expected: 'style-consistent output matching canon',
  }));
  await writeFile(join(implDir, 'eval-tasks.jsonl'), evalTasks.map(t => JSON.stringify(t)).join('\n') + '\n');

  // Write reingest guide
  const reingestGuide = generateReingestGuide(profile, manifest);
  await writeFile(join(implDir, 'reingest-guide.md'), reingestGuide);

  // Write README
  const readme = generateImplReadme(implManifest, profile, manifest);
  await writeFile(join(implDir, 'README.md'), readme);

  return {
    implId,
    prompts: promptExamples.length,
    failures: knownFailures.length,
    subjects: subjectExamples.length,
  };
}

function buildStyleMarkers(profile, config) {
  const markers = [];
  const constitution = config.constitution;
  if (constitution?.rules) {
    for (const rule of constitution.rules.slice(0, 10)) {
      markers.push({ rule_id: rule.id, summary: rule.summary || rule.id });
    }
  }
  return markers;
}

function buildForbiddenPatterns(config) {
  const forbidden = [];
  const rubric = config.rubric;
  if (rubric?.failure_to_rules) {
    for (const [mode, rules] of Object.entries(rubric.failure_to_rules)) {
      forbidden.push({ failure_mode: mode, linked_rules: rules });
    }
  }
  return forbidden;
}

function generateReingestGuide(profile, manifest) {
  return `# Re-ingest Guide

## When to re-ingest

After using the trained ${profile.asset_type} (${profile.label}) to generate new images,
accepted outputs should be re-ingested into the project as new records.

## How to re-ingest

\`\`\`bash
sdlab reingest generated --project <name> --source <outputs-dir>
\`\`\`

## Rules

1. Generated outputs enter as new records with \`provenance.source: "generated"\`
2. They must go through normal curation (\`sdlab curate\`)
3. They must be canon-bound (\`sdlab bind\`)
4. No bypass around review — generated work is judged like everything else
5. Accepted re-ingested records become eligible for future snapshots

## Provenance fields

Re-ingested records carry:

- \`provenance.source\`: \`"generated"\`
- \`provenance.training_manifest_id\`: \`"${manifest.training_manifest_id}"\`
- \`provenance.training_profile_id\`: \`"${manifest.training_profile_id}"\`
- \`provenance.adapter_target\`: \`"${manifest.adapter_target}"\`
- \`provenance.base_model\`: \`"${manifest.base_model || '(not specified)'}"\`
`;
}

function generateImplReadme(impl, profile, manifest) {
  return `# Implementation Pack: ${impl.implementation_pack_id}

**Profile:** ${profile.label} (${profile.profile_id})
**Training manifest:** ${manifest.training_manifest_id}
**Created:** ${impl.created_at}

## Contents

| File | Description |
|------|-------------|
| prompts.jsonl | ${impl.counts.prompt_examples} prompt examples across ${impl.counts.lanes_covered} lanes |
| known-failures.json | ${impl.counts.known_failures} documented failure cases to avoid |
| expected-behaviors.json | Style markers and forbidden patterns from constitution |
| subject-continuity.json | ${impl.counts.subject_examples} named-subject groups for identity testing |
| eval-tasks.jsonl | Generate-and-compare tasks for automated evaluation |
| reingest-guide.md | How to re-ingest accepted generated outputs |

## Usage

1. Load the trained ${profile.asset_type} with the prompt strategy from the profile
2. Use prompts.jsonl as starting points for each lane
3. Check generated outputs against expected-behaviors.json
4. Compare with known-failures.json to catch common drift
5. For named subjects, verify against subject-continuity.json
6. Re-ingest accepted outputs per reingest-guide.md
`;
}

/**
 * List all implementation packs.
 */
export async function listImplementationPacks(projectRoot) {
  const dir = join(projectRoot, 'training', 'implementations');
  if (!existsSync(dir)) return [];

  const entries = await readdir(dir, { withFileTypes: true });
  const packs = [];

  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('impl-')) continue;
    const manifestPath = join(dir, entry.name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const data = JSON.parse(await readFile(manifestPath, 'utf-8'));
      packs.push({
        id: data.implementation_pack_id,
        created_at: data.created_at,
        manifest: data.training_manifest_id,
        profile: data.training_profile_id,
        prompts: data.counts.prompt_examples,
        failures: data.counts.known_failures,
      });
    } catch { /* skip */ }
  }

  return packs.sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/**
 * Load an implementation pack manifest.
 */
export async function loadImplementationPack(projectRoot, implId) {
  const path = join(projectRoot, 'training', 'implementations', implId, 'manifest.json');
  if (!existsSync(path)) {
    throw new Error(`Implementation pack "${implId}" not found at ${path}`);
  }
  const manifest = JSON.parse(await readFile(path, 'utf-8'));
  checkManifestVersion(manifest, 'implementation-pack');
  return manifest;
}
