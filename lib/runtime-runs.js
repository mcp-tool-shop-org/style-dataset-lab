/**
 * Runtime run management — create, load, list run artifacts.
 *
 * A run is a frozen execution artifact: brief + seeds + outputs + manifest.
 * The run folder IS the review surface — humans open it directly.
 */

import { readFile, writeFile, mkdir, readdir, copyFile, rename, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { randomInt } from 'node:crypto';
import { getRunsDir, getBriefsDir } from './paths.js';
import { inputError } from './errors.js';
import { verbose } from './log.js';

// ─── Run ID generation ───────────────────────────────────────────

/**
 * Generate a run ID: run_YYYY-MM-DD_NNN
 */
// PB-008: tighten regex so stray directories like 'run_<date>_001_wip'
// don't inflate the sequence via parseInt's lenient parsing.
const RUN_SEQ_RE = /^(\d{3})$/;

export function generateRunId(runsDir) {
  const today = new Date().toISOString().slice(0, 10);
  const prefix = `run_${today}_`;

  let maxSeq = 0;
  if (existsSync(runsDir)) {
    const existing = readdirSync(runsDir, { withFileTypes: true })
      .filter(e => e.isDirectory() && e.name.startsWith(prefix));
    for (const e of existing) {
      const seqStr = e.name.slice(prefix.length);
      const match = RUN_SEQ_RE.exec(seqStr);
      if (!match) continue;
      const seq = parseInt(match[1], 10);
      if (seq > maxSeq) maxSeq = seq;
    }
  }

  const seq = String(maxSeq + 1).padStart(3, '0');
  return `${prefix}${seq}`;
}

// ─── Seed planning ───────────────────────────────────────────────

/**
 * Build a deterministic seed plan.
 * @param {Object} opts
 * @param {'fixed'|'increment'|'random'} opts.seedMode
 * @param {number} opts.outputCount
 * @param {number} [opts.baseSeed] — explicit base seed (default: random)
 * @returns {{ base_seed: number, seeds: number[] }}
 */
export function buildSeedPlan({ seedMode, outputCount, baseSeed }) {
  const base = baseSeed ?? randomInt(2_147_483_647);
  const seeds = [];

  switch (seedMode) {
    case 'fixed':
      for (let i = 0; i < outputCount; i++) seeds.push(base);
      break;
    case 'increment':
      for (let i = 0; i < outputCount; i++) seeds.push(base + i);
      break;
    case 'random':
      seeds.push(base);
      for (let i = 1; i < outputCount; i++) {
        seeds.push(randomInt(2_147_483_647));
      }
      break;
    default:
      // Default to increment
      for (let i = 0; i < outputCount; i++) seeds.push(base + i);
  }

  return { base_seed: base, seeds };
}

// ─── Run directory setup ─────────────────────────────────────────

/**
 * Prepare a run directory and copy brief artifacts into it.
 * @returns {{ runId: string, runDir: string }}
 */
export async function prepareRunDir(projectRoot, brief) {
  const runsDir = getRunsDir(projectRoot);
  const runId = generateRunId(runsDir);
  const runDir = join(runsDir, runId);

  await mkdir(join(runDir, 'outputs'), { recursive: true });

  // Copy brief artifacts
  const briefsDir = getBriefsDir(projectRoot);
  const briefJsonSrc = join(briefsDir, `${brief.brief_id}.json`);
  const briefMdSrc = join(briefsDir, `${brief.brief_id}.md`);

  await writeFile(join(runDir, 'brief.json'), JSON.stringify(brief, null, 2) + '\n');

  if (existsSync(briefMdSrc)) {
    await copyFile(briefMdSrc, join(runDir, 'brief.md'));
  }

  // Write standalone prompt/negative files for easy inspection
  await writeFile(join(runDir, 'prompt.txt'), brief.prompt || '');
  await writeFile(join(runDir, 'negative-prompt.txt'), brief.negative_prompt || '');

  return { runId, runDir };
}

// ─── Manifest ────────────────────────────────────────────────────

/**
 * Atomic write: write to a temp file in the same directory, then rename.
 * Rename is atomic on the same filesystem, so a crash mid-write can never
 * leave a half-written manifest in place of a good one.
 *
 * PB-002 / PB-005: callers may invoke this after each slot/candidate to
 * produce incremental checkpoints.
 */
async function atomicWriteJson(targetPath, obj) {
  const tmpPath = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  const body = JSON.stringify(obj, null, 2) + '\n';
  try {
    await writeFile(tmpPath, body);
    await rename(tmpPath, targetPath);
  } catch (err) {
    // Best-effort cleanup of the temp file on failure.
    try { await unlink(tmpPath); } catch { /* ignore */ }
    throw err;
  }
}

/**
 * Build and save a run manifest.
 *
 * PB-002: uses atomic write (temp + rename) so a crash mid-write cannot
 * corrupt an existing manifest. Safe to call repeatedly for incremental
 * checkpointing after each output completes.
 */
export async function saveRunManifest(runDir, manifest) {
  const target = join(runDir, 'manifest.json');
  await atomicWriteJson(target, manifest);
  verbose(`saveRunManifest: wrote ${target}`);
}

/**
 * Incremental checkpoint — same shape as saveRunManifest but stamps
 * `incremental: true` and `last_checkpoint_at` so a human reading a
 * partial manifest knows the run is in progress.
 *
 * PB-002: call after each completed output in long-running loops so a
 * crash/interruption leaves a partial record instead of an orphan dir.
 */
export async function checkpointRunManifest(runDir, manifest) {
  const snapshot = {
    ...manifest,
    incremental: true,
    last_checkpoint_at: new Date().toISOString(),
  };
  await atomicWriteJson(join(runDir, 'manifest.json'), snapshot);
  verbose(`checkpointRunManifest: ${manifest.run_id} (${manifest.outputs?.length ?? 0} outputs)`);
}

// ─── Load / List ─────────────────────────────────────────────────

/**
 * Load a run manifest by ID.
 */
export async function loadRun(projectRoot, runId) {
  const runDir = join(getRunsDir(projectRoot), runId);
  const manifestPath = join(runDir, 'manifest.json');

  if (!existsSync(manifestPath)) {
    throw inputError(
      'RUN_NOT_FOUND',
      `Run "${runId}" not found`,
      `Check the run ID or run: sdlab run generate --brief <id>`
    );
  }

  return JSON.parse(await readFile(manifestPath, 'utf-8'));
}

/**
 * List all runs in a project.
 */
export function listRuns(projectRoot) {
  const runsDir = getRunsDir(projectRoot);
  if (!existsSync(runsDir)) return [];

  const entries = readdirSync(runsDir, { withFileTypes: true })
    .filter(e => e.isDirectory() && e.name.startsWith('run_'))
    .sort((a, b) => a.name.localeCompare(b.name));

  const runs = [];
  for (const entry of entries) {
    const manifestPath = join(runsDir, entry.name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;

    try {
      const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
      runs.push({
        run_id: manifest.run_id,
        brief_id: manifest.brief_id,
        workflow_template_id: manifest.workflow_template_id,
        output_count: manifest.output_count,
        created_at: manifest.created_at,
        adapter_target: manifest.adapter_target,
      });
    } catch {
      // Skip malformed
    }
  }

  return runs;
}
