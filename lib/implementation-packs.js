/**
 * Implementation example packs.
 *
 * Shows how to use the trained asset in practice: prompt examples,
 * lane-targeted examples, subject continuity examples, known failure
 * cases, and re-ingest guidance.
 *
 * Every implementation pack is tied to a training manifest.
 */

import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { loadTrainingManifest } from './training-manifests.js';
import { loadTrainingProfile } from './training-profiles.js';
import { loadProjectConfig, detectLane, detectGroup } from './config.js';
import { loadSplitPartition } from './split.js';
import { loadRecord } from './records.js';

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

  // Build prompt examples — per-lane best records
  const promptExamples = [];
  const laneExamples = new Map();

  for (const entry of [...testEntries, ...trainEntries.slice(0, 50)]) {
    const record = await loadRecord(recordsDir, entry.record_id);
    if (!record) continue;
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

  for (const file of allFiles) {
    if (failCount >= 10) break;
    const record = JSON.parse(await readFile(join(recordsDir, file), 'utf-8'));
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

  // Build subject continuity examples
  const subjectExamples = [];
  const bySubject = new Map();

  for (const entry of [...testEntries, ...trainEntries]) {
    const record = await loadRecord(recordsDir, entry.record_id);
    if (!record?.identity?.subject_name) continue;
    const name = record.identity.subject_name;
    if (!bySubject.has(name)) bySubject.set(name, []);
    bySubject.get(name).push(record);
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
  const implId = generateImplId();
  const implDir = join(projectRoot, 'training', 'implementations', implId);
  await mkdir(implDir, { recursive: true });

  const implManifest = {
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
    },
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
  return JSON.parse(await readFile(path, 'utf-8'));
}
