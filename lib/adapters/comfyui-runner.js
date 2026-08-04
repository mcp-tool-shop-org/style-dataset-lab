/**
 * ComfyUI runner — executes a brief through ComfyUI and captures outputs.
 *
 * Orchestrates: seed plan → graph build → submit → poll → download → manifest.
 * Each image in the seed plan becomes one submission to ComfyUI.
 */

import { writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { comfyHealthDetailed, submitAndWait, downloadImage } from '../comfyui.js';
import { buildWorkflowGraph, resolveTemplateId, QWEN_DEFAULTS } from './comfyui-workflows.js';
import { buildSeedPlan, prepareRunDir, saveRunManifest, checkpointRunManifest } from '../runtime-runs.js';
import { loadProjectConfig } from '../config.js';
import { pickOutputImage } from '../comfyui-output.js';
import { buildPinning, seedPolicyFromMode, createHashCache, flushHashCache } from '../run-manifest.js';
import { SCHEMA_VERSION } from '../snapshot.js';
import { log, info, warn } from '../log.js';
import { runtimeError } from '../errors.js';

// B04: comfyHealthDetailed()'s `reason` maps to an ACTIONABLE hint, instead
// of every failure mode sharing the same "start ComfyUI" advice — which is
// simply wrong for an `http-<5xx>` (ComfyUI is up and answering) and useless
// for `dns`/`refused` against a misconfigured URL.
const HEALTH_REASON_HINTS = {
  timeout: 'ComfyUI accepted the connection but never responded — it may be loading a custom node or a large model. Wait and retry, or check its console for a stuck step.',
  refused: 'Start ComfyUI, or check COMFY_URL / project defaults.comfy_url — the connection was actively refused.',
  dns: 'COMFY_URL / project defaults.comfy_url does not resolve — check for a typo in the hostname.',
  unknown: 'Start ComfyUI or set COMFY_URL / project defaults.comfy_url.',
};

function healthReasonHint(reason) {
  if (reason && reason.startsWith('http-')) {
    return `ComfyUI responded with ${reason.slice('http-'.length)} — it is reachable but reported an error; check its console/logs.`;
  }
  return HEALTH_REASON_HINTS[reason] || HEALTH_REASON_HINTS.unknown;
}

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
export async function executeRun({ projectRoot, projectName, brief, baseSeed, dryRun = false, hashModels = false }) {
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
    // B04: use the reason-carrying check so a 503-while-loading, a refused
    // connection, a DNS typo, and a genuine timeout each get their OWN
    // actionable hint instead of the identical (and sometimes factually
    // wrong) "ComfyUI not reachable — start ComfyUI" message.
    const health = await comfyHealthDetailed(comfyUrl);
    if (!health.ok) {
      throw runtimeError(
        'COMFYUI_OFFLINE',
        `ComfyUI not reachable at ${comfyUrl} (${health.reason})`,
        healthReasonHint(health.reason)
      );
    }
    info('ComfyUI online');
  }

  const outputs = [];
  const errors = [];
  // B01: fixed at run start and reused by every mid-loop checkpoint AND the
  // final manifest, so `created_at` never drifts between an incremental
  // snapshot and the finished manifest for the same run.
  const createdAt = new Date().toISOString();

  // B01: checkpointRunManifest() existed (with a docstring saying exactly
  // this) but had zero production callers — comfyui-runner.js only called
  // saveRunManifest() once, after the whole loop. A run killed partway
  // through wrote NO manifest at all, so listRuns() silently skipped the
  // directory entirely: no id, no `run show`, no resume. This snapshot
  // mirrors the final manifest's shape (minus `pinning`, computed only
  // after the loop) so a partial manifest.json is readable by the same
  // code that reads a finished one.
  function buildManifestSnapshot() {
    return {
      run_id: runId,
      schema_version: SCHEMA_VERSION,
      brief_id: brief.brief_id,
      project_id: brief.project_id,
      workflow_template_id: templateId,
      adapter_target: 'comfyui',
      output_mode: outputMode,
      output_count: outputCount,
      created_at: createdAt,
      seed_plan: seedPlan,
      comfy_url: comfyUrl,
      checkpoint: defaults.checkpoint,
      loras: defaults.loras || [],
      pinning: null,
      runtime_plan: brief.runtime_plan,
      outputs,
      errors,
      dry_run: dryRun,
      success_count: outputs.filter(o => o.status === 'ok' || o.status === 'dry_run').length,
      error_count: errors.length,
    };
  }

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
      await checkpointRunManifest(runDir, buildManifestSnapshot());
      continue;
    }

    const startMs = Date.now();

    try {
      // Build graph
      const { nodes, saveNodeId } = buildWorkflowGraph({
        brief,
        projectDefaults: defaults,
        seed,
      });

      // Submit and wait
      const result = await submitAndWait(nodes, comfyUrl, {
        clientPrefix: `sdl-run-${runId}`,
      });

      const elapsed = Date.now() - startMs;

      // Extract output image — prefer the explicit save node from the
      // workflow builder (or `expected_outputs.save_node_id` from the
      // brief/profile), falling back to the highest numeric node id.
      const preferNodeId = brief.expected_outputs?.save_node_id ?? saveNodeId;
      const picked = pickOutputImage(result.outputs, { preferNodeId });

      if (!picked) {
        warn(`  No output image for seed ${seed}`);
        outputs.push({ index: i, seed, status: 'no_output', elapsed_ms: elapsed });
        await checkpointRunManifest(runDir, buildManifestSnapshot());
        continue;
      }

      // Download and save
      const imgData = await downloadImage(picked.filename, picked.subfolder, comfyUrl);
      const destFilename = `${imageIndex}.png`;
      await writeFile(join(runDir, 'outputs', destFilename), imgData);

      outputs.push({
        index: i,
        seed,
        status: 'ok',
        filename: destFilename,
        bytes: imgData.length,
        elapsed_ms: elapsed,
        comfy_filename: picked.filename,
        comfy_node_id: picked.nodeId,
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

    // B01: checkpoint after every completed output (success OR error) so a
    // crash/interruption mid-loop leaves a partial, readable manifest.json
    // instead of an orphan directory — this is the call the docstring on
    // checkpointRunManifest() always described but nothing ever made.
    await checkpointRunManifest(runDir, buildManifestSnapshot());
  }

  // PIN_PER_STEP: pin the exact graph + model/LoRA content identity + seed
  // policy via the shared contract (lib/run-manifest.js). One run = one prompt
  // across N seeds, so the pin is wave-level (per-item seed is normalized out of
  // comfy_workflow_sha and kept in seed_plan). Best-effort — a build/hash failure
  // degrades to null pinning rather than failing the run.
  let pinning = null;
  try {
    const isQwen = String(defaults.base || '').toLowerCase() === 'qwen-image';
    const pinModels = isQwen
      ? {
          unet: defaults.unet || QWEN_DEFAULTS.unet,
          clip: defaults.clip || QWEN_DEFAULTS.clip,
          vae: defaults.vae || QWEN_DEFAULTS.vae,
        }
      : { checkpoint: defaults.checkpoint };
    const pinCache = hashModels ? createHashCache() : undefined;
    const { nodes: pinNodes } = buildWorkflowGraph({ brief, projectDefaults: defaults, seed: seedPlan.seeds[0] ?? 0 });
    pinning = buildPinning({
      graph: pinNodes,
      models: pinModels,
      loras: defaults.loras || [],
      seedPolicy: seedPolicyFromMode(seedMode),
      hashModels,
      cache: pinCache,
    });
    flushHashCache(pinCache);
  } catch (err) {
    warn(`pinning skipped: ${err.message}`);
  }

  // Build manifest — reuses buildManifestSnapshot() (same helper the
  // mid-loop checkpoints use) so the finished manifest and every
  // incremental checkpoint before it are byte-for-byte the same shape,
  // just with `pinning` filled in and no `incremental`/`last_checkpoint_at`
  // stamp (that stamp is what lets a reader tell "done" from "still going").
  const manifest = {
    ...buildManifestSnapshot(),
    pinning,
  };

  await saveRunManifest(runDir, manifest);

  return manifest;
}
