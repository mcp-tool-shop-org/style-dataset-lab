#!/usr/bin/env node

/**
 * batch-generate.js — Execute a batch production mode.
 *
 * Usage:
 *   sdlab batch generate --mode expression-sheet --subject captain-orryn --project star-freight
 *   sdlab batch generate --mode environment-board --theme freeport-night --project star-freight
 *   sdlab batch generate --mode silhouette-pack --project star-freight --dry-run
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot, getRunsDir } from '../lib/paths.js';
import { compileBatch } from '../lib/batch-compiler.js';
import { getBatchMode } from '../lib/batch-modes.js';
import {
  createBatchDir,
  openBatchDirForResume,
  executeBatchRuns,
  saveBatchManifest,
} from '../lib/batch-runs.js';
import { renderSheetHTML, saveSheet } from '../lib/batch-sheet-render.js';
import { info, result } from '../lib/log.js';
import { join } from 'node:path';
import { writeFile } from 'node:fs/promises';

export async function run(argv = process.argv.slice(2)) {
  const { flags } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      mode: { type: 'string' },
      subject: { type: 'string' },
      theme: { type: 'string' },
      asset: { type: 'string' },
      resume: { type: 'string' },
      'dry-run': { type: 'boolean' },
      json: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });

  if (!flags.mode && !flags.resume) {
    console.log('Usage: sdlab batch generate --mode <id> [--subject <id>] [--theme <label>] [--project <name>]');
    console.log('       sdlab batch generate --resume <batch_id> [--project <name>]');
    console.log('');
    console.log('Options:');
    console.log('  --mode <id>        Batch mode (required unless --resume is given)');
    console.log('  --subject <id>     Subject for subject-driven modes');
    console.log('  --theme <label>    Theme label for environment modes');
    console.log('  --asset <id>       Training asset reference');
    console.log('  --resume <id>      Resume an existing batch — re-runs only failed/missing slots');
    console.log('  --dry-run          Prepare batch without submitting to ComfyUI');
    console.log('  --json             Output manifest as JSON');
    return;
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const dryRun = flags['dry-run'] || false;
  const resumeId = flags.resume || null;

  // Resume short-circuit: load prior manifest and reuse its mode_id + subject/theme
  // so the user only needs to pass --resume <batch_id>.
  let batchId;
  let batchDir;
  let priorResults = [];
  let resumedMode = null;
  let resumedSubject = null;
  let resumedTheme = null;
  let resumedAsset = null;
  if (resumeId) {
    const opened = openBatchDirForResume(projectRoot, resumeId);
    batchId = opened.batchId;
    batchDir = opened.batchDir;
    priorResults = opened.priorResults;
    resumedMode = opened.priorManifest.mode_id || null;
    resumedSubject = opened.priorManifest.subject_id || null;
    resumedTheme = opened.priorManifest.theme || null;
    resumedAsset = opened.priorManifest.asset_ref || null;
  }

  const modeId = flags.mode || resumedMode;
  const subjectId = flags.subject || resumedSubject;
  const theme = flags.theme || resumedTheme;
  const assetRef = flags.asset || resumedAsset;

  // Load mode for display
  const mode = getBatchMode(projectRoot, modeId);

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m batch generate`);
  console.log(`  Project: ${projectName}`);
  console.log(`  Mode: ${mode.label} (${mode.mode_id})`);
  console.log(`  Type: ${mode.batch_type}`);
  console.log(`  Slots: ${mode.variant_plan.length}`);
  if (subjectId) console.log(`  Subject: ${subjectId}`);
  if (theme) console.log(`  Theme: ${theme}`);
  if (resumeId) {
    const completed = priorResults.filter(r => r && r.status === 'ok').length;
    console.log(`  Resume: ${resumeId} (${completed}/${priorResults.length} slots already complete)`);
  }
  if (dryRun) console.log('  ⚠ DRY RUN');
  console.log('');

  // 1. Compile batch briefs
  const { baseBrief, slotBriefs } = await compileBatch({
    projectRoot,
    projectId: projectName,
    modeId,
    subjectId,
    theme,
    assetRef,
  });

  // 2. Create or reuse batch directory
  if (!resumeId) {
    const created = await createBatchDir(projectRoot);
    batchId = created.batchId;
    batchDir = created.batchDir;
  }
  info('batch-generate', `Batch: ${batchId}`);

  // 3. Execute runs
  const batchStartMs = Date.now();
  const results = await executeBatchRuns({
    projectRoot,
    projectName,
    batchDir,
    mode,
    slotBriefs,
    dryRun,
    priorResults,
  });
  const batchElapsedMs = Date.now() - batchStartMs;
  if (!dryRun && results.length > 0) {
    const avgSec = Math.round(batchElapsedMs / results.length / 1000);
    const totalSec = Math.round(batchElapsedMs / 1000);
    info('batch-generate', `Completed ${results.length} slot(s) in ${totalSec}s (avg ${avgSec}s/slot)`);
  }

  // 4. Build manifest
  const manifest = {
    batch_id: batchId,
    project_id: projectName,
    mode_id: mode.mode_id,
    created_at: new Date().toISOString(),
    brief_ids: results.map(r => r.brief_id),
    run_ids: results.map(r => r.run_id),
    slots: results.map(r => ({
      slot_id: r.slot_id,
      label: r.label,
      brief_id: r.brief_id,
      run_id: r.run_id,
      status: r.status,
      selected_output: r.selected_output,
      ...(r.error ? { error: r.error } : {}),
    })),
    sheet_paths: [],
    summary: {
      total_slots: results.length,
      successful_slots: results.filter(r => r.selected_output).length,
      dry_run: dryRun,
    },
  };

  if (subjectId) manifest.subject_id = subjectId;
  if (theme) manifest.theme = theme;
  if (assetRef) manifest.asset_ref = assetRef;
  if (resumeId) manifest.resumed_from = resumeId;

  // 5. Render sheet
  const sheetHtml = renderSheetHTML({ manifest, mode, projectRoot, batchDir });
  const sheetPath = await saveSheet(batchDir, 'primary-sheet.html', sheetHtml);
  manifest.sheet_paths.push('sheets/primary-sheet.html');

  // 6. Save manifest + summary
  await saveBatchManifest(batchDir, manifest);

  // Write summary.md
  const summaryLines = [
    `# Batch: ${batchId}`,
    '',
    `**Mode:** ${mode.label} (${mode.mode_id})`,
    `**Type:** ${mode.batch_type}`,
    `**Project:** ${projectName}`,
  ];
  if (manifest.subject_id) summaryLines.push(`**Subject:** ${manifest.subject_id}`);
  if (manifest.theme) summaryLines.push(`**Theme:** ${manifest.theme}`);
  summaryLines.push(`**Created:** ${manifest.created_at}`);
  if (dryRun) summaryLines.push('**⚠ DRY RUN**');
  summaryLines.push('');
  summaryLines.push('## Slots');
  summaryLines.push('');
  summaryLines.push('| Slot | Run | Output |');
  summaryLines.push('|------|-----|--------|');
  for (const r of results) {
    summaryLines.push(`| ${r.label} | ${r.run_id} | ${r.selected_output || '—'} |`);
  }
  summaryLines.push('');
  await writeFile(join(batchDir, 'summary.md'), summaryLines.join('\n'));

  // 7. Output
  console.log('');
  if (flags.json) {
    console.log(JSON.stringify(manifest, null, 2));
  } else {
    console.log(`Batch: ${batchId}`);
    console.log(`Slots: ${results.length}`);
    console.log('');
    for (const r of results) {
      const status = r.selected_output ? '✓' : '○';
      console.log(`  ${status} ${r.label.padEnd(24)} → ${r.run_id}  ${r.selected_output || '(dry run)'}`);
    }
    console.log('');
    // Primary artifact paths — always print (survives --quiet) so pipelines
    // can parse the output location.
    result(`Sheet: batches/${batchId}/sheets/primary-sheet.html`);
    result(`Manifest: batches/${batchId}/manifest.json`);
  }
}
