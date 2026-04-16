/**
 * ComfyUI runner — executes a brief through ComfyUI and captures outputs.
 *
 * Orchestrates: seed plan → graph build → submit → poll → download → manifest.
 * Each image in the seed plan becomes one submission to ComfyUI.
 */

import { writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { comfyHealth, submitAndWait, downloadImage } from '../comfyui.js';
import { buildWorkflowGraph, resolveTemplateId } from './comfyui-workflows.js';
import { buildSeedPlan, prepareRunDir, saveRunManifest } from '../runtime-runs.js';
import { loadProjectConfig } from '../config.js';
import { log, info, warn } from '../log.js';
import { runtimeError } from '../errors.js';

/**
 * Execute a brief: build graphs, submit to ComfyUI, capture outputs.
 *
 * @param {Object} opts
 * @param {string} opts.projectRoot — absolute project path
 * @param {string} opts.projectName — project name
 * @param {Object} opts.brief — compiled brief object
 * @param {number} [opts.baseSeed] — override base seed
 * @param {boolean} [opts.dryRun] — if true, prepare run dir but do not submit
 * @returns {Promise<Object>} — manifest
 */
export async function executeRun({ projectRoot, projectName, brief, baseSeed, dryRun = false }) {
  const config = loadProjectConfig(projectRoot);
  const defaults = config.meta?.defaults ?? {};
  const comfyUrl = defaults.comfy_url || process.env.COMFY_URL || 'http://127.0.0.1:8188';

  // Resolve template
  const outputMode = brief.expected_outputs?.output_mode || 'portrait_set';
  const templateId = resolveTemplateId(outputMode);
  const outputCount = brief.expected_outputs?.output_count || brief.runtime_plan?.output_count || 4;

  // Build seed plan
  const seedMode = brief.runtime_plan?.seed_mode || 'increment';
  const seedPlan = buildSeedPlan({ seedMode, outputCount, baseSeed });

  // Prepare run directory
  const { runId, runDir } = await prepareRunDir(projectRoot, brief);

  info(`Run ${runId} — ${outputCount} images, seed mode: ${seedMode}, base: ${seedPlan.base_seed}`);
  info(`Template: ${templateId}, ComfyUI: ${comfyUrl}`);

  // Health check
  if (!dryRun) {
    const healthy = await comfyHealth(comfyUrl);
    if (!healthy) {
      throw runtimeError(
        'COMFYUI_OFFLINE',
        `ComfyUI not reachable at ${comfyUrl}`,
        'Start ComfyUI or set COMFY_URL / project defaults.comfy_url'
      );
    }
    info('ComfyUI online');
  }

  const outputs = [];
  const errors = [];

  for (let i = 0; i < outputCount; i++) {
    const seed = seedPlan.seeds[i];
    const imageIndex = String(i + 1).padStart(3, '0');

    log(`  [${i + 1}/${outputCount}] seed: ${seed}`);

    if (dryRun) {
      outputs.push({
        index: i,
        seed,
        status: 'dry_run',
        filename: `${imageIndex}.png`,
      });
      continue;
    }

    const startMs = Date.now();

    try {
      // Build graph
      const { nodes } = buildWorkflowGraph({
        brief,
        projectDefaults: defaults,
        seed,
      });

      // Submit and wait
      const result = await submitAndWait(nodes, comfyUrl, {
        clientPrefix: `sdl-run-${runId}`,
      });

      const elapsed = Date.now() - startMs;

      // Extract output image
      const nodeOutputs = result.outputs || {};
      let imageFile = null;
      let imageSubfolder = '';
      for (const nodeOut of Object.values(nodeOutputs)) {
        if (nodeOut.images && nodeOut.images.length > 0) {
          imageFile = nodeOut.images[0].filename;
          imageSubfolder = nodeOut.images[0].subfolder || '';
          break;
        }
      }

      if (!imageFile) {
        warn(`  No output image for seed ${seed}`);
        outputs.push({ index: i, seed, status: 'no_output', elapsed_ms: elapsed });
        continue;
      }

      // Download and save
      const imgData = await downloadImage(imageFile, imageSubfolder, comfyUrl);
      const destFilename = `${imageIndex}.png`;
      await writeFile(join(runDir, 'outputs', destFilename), imgData);

      outputs.push({
        index: i,
        seed,
        status: 'ok',
        filename: destFilename,
        bytes: imgData.length,
        elapsed_ms: elapsed,
        comfy_filename: imageFile,
      });

      log(`    ✓ ${destFilename} (${imgData.length} bytes, ${(elapsed / 1000).toFixed(1)}s)`);
    } catch (err) {
      const elapsed = Date.now() - startMs;
      warn(`    ✗ seed ${seed}: ${err.message}`);
      errors.push({ index: i, seed, error: err.message });
      outputs.push({
        index: i,
        seed,
        status: 'error',
        error: err.message,
        elapsed_ms: elapsed,
      });
    }
  }

  // Build manifest
  const manifest = {
    run_id: runId,
    brief_id: brief.brief_id,
    project_id: brief.project_id,
    workflow_template_id: templateId,
    adapter_target: 'comfyui',
    output_mode: outputMode,
    output_count: outputCount,
    created_at: new Date().toISOString(),
    seed_plan: seedPlan,
    comfy_url: comfyUrl,
    checkpoint: defaults.checkpoint,
    loras: defaults.loras || [],
    runtime_plan: brief.runtime_plan,
    outputs,
    errors,
    dry_run: dryRun,
    success_count: outputs.filter(o => o.status === 'ok' || o.status === 'dry_run').length,
    error_count: errors.length,
  };

  await saveRunManifest(runDir, manifest);

  return manifest;
}
