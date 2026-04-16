/**
 * Runtime run management — create, load, list run artifacts.
 *
 * A run is a frozen execution artifact: brief + seeds + outputs + manifest.
 * The run folder IS the review surface — humans open it directly.
 */

import { readFile, writeFile, mkdir, readdir, copyFile } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { getRunsDir, getBriefsDir } from './paths.js';
import { inputError } from './errors.js';

// ─── Run ID generation ───────────────────────────────────────────

/**
 * Generate a run ID: run_YYYY-MM-DD_NNN
 */
export function generateRunId(runsDir) {
  const today = new Date().toISOString().slice(0, 10);
  const prefix = `run_${today}_`;

  let maxSeq = 0;
  if (existsSync(runsDir)) {
    const existing = readdirSync(runsDir, { withFileTypes: true })
      .filter(e => e.isDirectory() && e.name.startsWith(prefix));
    for (const e of existing) {
      const seqStr = e.name.slice(prefix.length);
      const seq = parseInt(seqStr, 10);
      if (!isNaN(seq) && seq > maxSeq) maxSeq = seq;
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
  const base = baseSeed ?? Math.floor(Math.random() * 2_147_483_647);
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
        seeds.push(Math.floor(Math.random() * 2_147_483_647));
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
 * Build and save a run manifest.
 */
export async function saveRunManifest(runDir, manifest) {
  await writeFile(
    join(runDir, 'manifest.json'),
    JSON.stringify(manifest, null, 2) + '\n'
  );
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
