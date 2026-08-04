#!/usr/bin/env node

/**
 * generate.js — Drive ComfyUI to produce candidate assets from a prompt pack.
 *
 * Usage: node scripts/generate.js [--prompt-pack inputs/prompts/rpg-icons-lane1.json]
 *        sdlab generate inputs/prompts/wave1.json --project star-freight
 *
 * For each subject × variation, submits a workflow to ComfyUI HTTP API,
 * downloads the output PNG, and writes a provenance record to records/.
 */

import { writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { parseArgs, getProjectName } from "../lib/args.js";
import { getProjectRoot, resolveSafeProjectPath } from "../lib/paths.js";
import { readJsonFile, loadProjectMeta, resolveGpuModel } from "../lib/config.js";
import { runtimeError, inputError, handleCliError } from "../lib/errors.js";
import { comfyHealth, submitAndWait, downloadImage } from "../lib/comfyui.js";
import { pickOutputImage } from "../lib/comfyui-output.js";
import { buildQwenGraph, QWEN_DEFAULTS } from "../lib/adapters/comfyui-workflows.js";
import { buildPinning, SEED_POLICIES, createHashCache, flushHashCache } from "../lib/run-manifest.js";
import { info, result } from "../lib/log.js";

/**
 * Format milliseconds as a human ETA string like "6m 12s" or "42s".
 */
function formatEta(ms) {
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}m ${s}s`;
}

/**
 * COMFY_URL precedence:
 *   1. process.env.COMFY_URL (explicit user env)
 *   2. project defaults.comfy_url (set by `sdlab project doctor`)
 *   3. built-in default http://127.0.0.1:8188
 * The adapter (lib/adapters/comfyui-runner.js) applies the same precedence.
 */

function buildWorkflow(prompt, negativePrompt, checkpoint, loras, seed, steps, cfg, sampler, scheduler, width, height, ipAdapterConfig) {
  const nodes = {};
  let nextId = 1;

  // Checkpoint loader
  const ckptId = String(nextId++);
  nodes[ckptId] = {
    class_type: "CheckpointLoaderSimple",
    inputs: { ckpt_name: checkpoint },
  };

  let modelOut = [ckptId, 0];
  let clipOut = [ckptId, 1];

  // LoRA loaders (chained)
  for (const lora of loras) {
    const loraId = String(nextId++);
    nodes[loraId] = {
      class_type: "LoraLoader",
      inputs: {
        model: modelOut,
        clip: clipOut,
        lora_name: lora.name,
        strength_model: lora.weight,
        strength_clip: lora.clip_weight ?? lora.weight,
      },
    };
    modelOut = [loraId, 0];
    clipOut = [loraId, 1];
  }

  // IP-Adapter for style reference (if configured)
  if (ipAdapterConfig) {
    // Load CLIP Vision model
    const clipVisionId = String(nextId++);
    nodes[clipVisionId] = {
      class_type: "CLIPVisionLoader",
      inputs: { clip_name: ipAdapterConfig.clip_vision_model },
    };

    // Load IP-Adapter model
    const ipaLoaderId = String(nextId++);
    nodes[ipaLoaderId] = {
      class_type: "IPAdapterModelLoader",
      inputs: { ipadapter_file: ipAdapterConfig.model },
    };

    // Load reference image
    const refImageId = String(nextId++);
    nodes[refImageId] = {
      class_type: "LoadImage",
      inputs: { image: ipAdapterConfig.reference_image },
    };

    // Apply IP-Adapter
    const ipaApplyId = String(nextId++);
    nodes[ipaApplyId] = {
      class_type: "IPAdapterApply",
      inputs: {
        ipadapter: [ipaLoaderId, 0],
        clip_vision: [clipVisionId, 0],
        image: [refImageId, 0],
        model: modelOut,
        weight: ipAdapterConfig.weight || 0.6,
        noise: ipAdapterConfig.noise || 0.0,
        weight_type: ipAdapterConfig.weight_type || "linear",
        start_at: ipAdapterConfig.start_at || 0.0,
        end_at: ipAdapterConfig.end_at || 1.0,
      },
    };

    modelOut = [ipaApplyId, 0];
  }

  // CLIP Text Encode — positive
  const posId = String(nextId++);
  nodes[posId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: prompt, clip: clipOut },
  };

  // CLIP Text Encode — negative
  const negId = String(nextId++);
  nodes[negId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: negativePrompt, clip: clipOut },
  };

  // Empty latent image
  const latentId = String(nextId++);
  nodes[latentId] = {
    class_type: "EmptyLatentImage",
    inputs: { width, height, batch_size: 1 },
  };

  // KSampler
  const samplerId = String(nextId++);
  nodes[samplerId] = {
    class_type: "KSampler",
    inputs: {
      model: modelOut,
      positive: [posId, 0],
      negative: [negId, 0],
      latent_image: [latentId, 0],
      seed,
      steps,
      cfg,
      sampler_name: sampler,
      scheduler,
      denoise: 1.0,
    },
  };

  // VAE Decode
  const vaeId = String(nextId++);
  nodes[vaeId] = {
    class_type: "VAEDecode",
    inputs: {
      samples: [samplerId, 0],
      vae: [ckptId, 2],
    },
  };

  // Save Image
  const saveId = String(nextId++);
  nodes[saveId] = {
    class_type: "SaveImage",
    inputs: {
      images: [vaeId, 0],
      filename_prefix: "sdl",
    },
  };

  return { nodes, saveNodeId: saveId };
}

/**
 * Detect the input schema and normalize to a unified shape:
 *   { lane, style_prefix, negative, defaults, base, jobs:[{assetId, subjectId, variationId, prompt, seed, loras}] }
 *
 * Two accepted schemas (both produce jobs in subject-major order, so the legacy
 * seed sequence stays byte-identical):
 *
 *   • Legacy pack — top-level `lane` + `variations` (array) applied to every
 *     subject. seed = base_seed + jobIndex + (variation.seed_offset||0);
 *     assetId = `${subject.id}_${variation.id}`; `negative` is top-level.
 *
 *   • Wave (what `sdlab init` scaffolds, e.g. example-wave.json) — each subject
 *     carries `variations` as an integer count; `negative` lives in `defaults`.
 *     seed = base_seed + jobIndex; assetId = `${subject.id}_v${v}`. This matches
 *     scripts/qwen_generate.py's seed/filename scheme.
 *
 * `base` resolves: input.base → input.defaults.base → project.json defaults.base
 * → "sdxl". `"qwen-image"` routes to the non-anime Qwen graph.
 */
function normalizeGenerationInput(raw, projectMeta) {
  if (!Array.isArray(raw.subjects) || raw.subjects.length === 0) {
    throw inputError(
      'INPUT_MISSING_FIELDS',
      'Prompt pack/wave must have a non-empty "subjects" array.',
      'See inputs/prompts/example-wave.json for the expected shape.'
    );
  }
  const defaults = raw.defaults || {};
  const base = String(
    raw.base || defaults.base || projectMeta?.defaults?.base || 'sdxl'
  ).toLowerCase();
  const baseSeed = Number.isFinite(defaults.base_seed) ? defaults.base_seed : 0;
  const stylePrefix = raw.style_prefix || '';
  const compose = (p) => (stylePrefix ? `${stylePrefix}, ${p}` : p);

  const jobs = [];
  let k = 0;

  if (Array.isArray(raw.variations)) {
    // Legacy pack schema
    if (!raw.lane) {
      throw inputError(
        'INPUT_MISSING_FIELDS',
        'Legacy pack (top-level "variations" array) requires a "lane".',
        'Add a "lane" string, or use the wave schema (per-subject integer "variations").'
      );
    }
    const negative = raw.negative ?? '';
    for (const subject of raw.subjects) {
      for (const variation of raw.variations) {
        jobs.push({
          assetId: `${subject.id}_${variation.id}`,
          subjectId: subject.id,
          variationId: variation.id,
          prompt: compose(subject.prompt),
          seed: baseSeed + k + (variation.seed_offset || 0),
          loras: variation.loras || [],
        });
        k++;
      }
    }
    return { lane: raw.lane, style_prefix: stylePrefix, negative, defaults, base, jobs, schema: 'pack' };
  }

  // Wave schema
  const negative = raw.negative ?? defaults.negative ?? '';
  for (const subject of raw.subjects) {
    const nvar = Number.isFinite(subject.variations) ? subject.variations : 1;
    for (let v = 0; v < nvar; v++) {
      jobs.push({
        assetId: `${subject.id}_v${v}`,
        subjectId: subject.id,
        variationId: `v${v}`,
        prompt: compose(subject.prompt),
        seed: baseSeed + k,
        loras: [],
      });
      k++;
    }
  }
  return { lane: raw.wave || raw.lane || 'default', style_prefix: stylePrefix, negative, defaults, base, jobs, schema: 'wave' };
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = getProjectRoot(projectName);
  const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";

  const parsed = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      game: { type: 'string' },
      'dry-run': { type: 'boolean' },
      resume: { type: 'boolean' },
      'hash-models': { type: 'boolean' },
    },
    deprecated: { game: 'project' },
  });
  const packPath = parsed.positionals[0] || "inputs/prompts/rpg-icons-lane1.json";
  const dryRun = parsed.flags['dry-run'] === true;
  const resume = parsed.flags['resume'] === true;
  // PIN_PER_STEP: --hash-models opts into content hashing of the checkpoint/
  // unet/clip/vae/LoRA files (best-effort, cached). Without it the pinning block
  // still records comfy_workflow_sha + model name/size + seed_policy.
  const hashModels = parsed.flags['hash-models'] === true;
  const hashCache = hashModels ? createHashCache() : undefined;

  const fullPackPath = resolveSafeProjectPath(GAME_ROOT, packPath, { flagName: 'pack-path' });
  const raw = await readJsonFile(fullPackPath);
  const projectMeta = loadProjectMeta(GAME_ROOT);
  const gpuModel = resolveGpuModel(projectMeta?.defaults);
  const pack = normalizeGenerationInput(raw, projectMeta);

  const d = pack.defaults;
  const base = pack.base;
  const isQwen = base === 'qwen-image';

  // Resolve effective sampler params once. Qwen applies its own defaults when a
  // wave omits them; SDXL uses the pack defaults exactly as authored (unchanged).
  const resolved = isQwen
    ? {
        width: d.width || QWEN_DEFAULTS.width,
        height: d.height || QWEN_DEFAULTS.height,
        steps: d.steps || QWEN_DEFAULTS.steps,
        cfg: d.cfg || QWEN_DEFAULTS.cfg,
        sampler: d.sampler || QWEN_DEFAULTS.sampler,
        scheduler: d.scheduler || QWEN_DEFAULTS.scheduler,
      }
    : {
        width: d.width,
        height: d.height,
        steps: d.steps,
        cfg: d.cfg,
        sampler: d.sampler,
        scheduler: d.scheduler,
      };

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m generate`);
  console.log(`  Lane: ${pack.lane}`);
  console.log(`  Base: ${base}${isQwen ? ' \x1b[2m(non-anime)\x1b[0m' : ''}`);
  console.log(`  Subjects: ${raw.subjects.length}`);
  console.log(`  Total candidates: ${pack.jobs.length}`);
  console.log("");

  if (!dryRun) {
    const online = await comfyHealth(COMFY_URL);
    if (!online) {
      throw runtimeError('RUNTIME_COMFY_UNREACHABLE', "ComfyUI not reachable at " + COMFY_URL, 'Start ComfyUI or set COMFY_URL to the right host.');
    }
    console.log("\x1b[32m✓\x1b[0m ComfyUI online");
  }

  // SDL-M11: only create output dirs on a real run — a --dry-run preview must
  // be side-effect-free (README.md promises "preview the effect first").
  if (!dryRun) {
    await mkdir(join(GAME_ROOT, "outputs/candidates"), { recursive: true });
    await mkdir(join(GAME_ROOT, "records"), { recursive: true });
  }

  let generated = 0;
  let errors = 0;
  let skipped = 0;
  const totalExpected = pack.jobs.length;
  const runStartMs = Date.now();

  for (const job of pack.jobs) {
    const { assetId, prompt: fullPrompt, seed, loras } = job;

    // --resume: skip jobs whose record + image are both already on disk.
    // Seeds are precomputed per job index, so skipping never shifts later seeds.
    if (resume && !dryRun) {
      const recordPath = join(GAME_ROOT, `records/${assetId}.json`);
      const imagePath = join(GAME_ROOT, `outputs/candidates/${assetId}.png`);
      if (existsSync(recordPath) && existsSync(imagePath)) {
        console.log(`  [${generated + 1}/${totalExpected}] ${assetId} \x1b[2m(resumed — skipped)\x1b[0m`);
        generated++;
        skipped++;
        continue;
      }
    }

    console.log(`  [${generated + 1}/${totalExpected}] ${assetId} (seed: ${seed}, loras: ${isQwen ? (d.loras || []).length : loras.length})`);

    if (dryRun) {
      generated++;
      continue;
    }

    const startMs = Date.now();
    const { nodes, saveNodeId } = isQwen
      ? buildQwenGraph({
          prompt: fullPrompt,
          negativePrompt: pack.negative,
          seed,
          width: resolved.width,
          height: resolved.height,
          steps: resolved.steps,
          cfg: resolved.cfg,
          sampler: resolved.sampler,
          scheduler: resolved.scheduler,
          shift: d.shift ?? QWEN_DEFAULTS.shift,
          unet: d.unet || QWEN_DEFAULTS.unet,
          clip: d.clip || QWEN_DEFAULTS.clip,
          vae: d.vae || QWEN_DEFAULTS.vae,
          clipType: d.clip_type || QWEN_DEFAULTS.clip_type,
          weightDtype: d.weight_dtype || QWEN_DEFAULTS.weight_dtype,
          loras: d.loras || [],
          filenamePrefix: 'sdl',
        })
      : buildWorkflow(
          fullPrompt, pack.negative,
          d.checkpoint, loras, seed,
          resolved.steps, resolved.cfg, resolved.sampler, resolved.scheduler,
          resolved.width, resolved.height,
        );

    try {
      const submitResult = await submitAndWait(nodes, COMFY_URL);
      const elapsed = Date.now() - startMs;

      // Prefer the explicit SaveImage node from the builder; fall back
      // to highest numeric node id (see lib/comfyui-output.js).
      const picked = pickOutputImage(submitResult.outputs, { preferNodeId: saveNodeId });
      if (!picked) {
        console.log(`    \x1b[33m⚠\x1b[0m No output image found`);
        generated++;
        continue;
      }

      // Download and save
      const imgData = await downloadImage(picked.filename, picked.subfolder, COMFY_URL);
      const destPath = `outputs/candidates/${assetId}.png`;
      await writeFile(join(GAME_ROOT, destPath), imgData);

      // Write provenance record (base-aware: Qwen records unet/clip/vae/shift,
      // SDXL records checkpoint/loras).
      const provenance = {
        workflow_id: pack.lane,
        workflow_version: "1.0.0",
        base,
        prompt: fullPrompt,
        negative_prompt: pack.negative,
        seed,
        steps: resolved.steps,
        cfg: resolved.cfg,
        sampler: resolved.sampler,
        scheduler: resolved.scheduler,
        width: resolved.width,
        height: resolved.height,
        generation_time_ms: elapsed,
        gpu_model: gpuModel,
        batch_index: generated,
      };
      if (isQwen) {
        provenance.unet = d.unet || QWEN_DEFAULTS.unet;
        provenance.clip = d.clip || QWEN_DEFAULTS.clip;
        provenance.vae = d.vae || QWEN_DEFAULTS.vae;
        provenance.shift = d.shift ?? QWEN_DEFAULTS.shift;
        provenance.loras = d.loras || [];
      } else {
        provenance.checkpoint = d.checkpoint;
        provenance.loras = loras;
      }

      // PIN_PER_STEP: pin the exact graph + model/LoRA content identity + seed
      // policy via the shared contract (lib/run-manifest.js). Model hashing is
      // wave-constant; the shared cache means it runs at most once per wave.
      provenance.pinning = buildPinning({
        graph: nodes,
        models: isQwen
          ? { unet: provenance.unet, clip: provenance.clip, vae: provenance.vae }
          : { checkpoint: d.checkpoint },
        loras: isQwen ? (d.loras || []) : loras,
        seedPolicy: SEED_POLICIES.BASE_INCREMENT,
        hashModels,
        cache: hashCache,
      });

      const record = {
        id: assetId,
        schema_version: "1.0.0",
        created_at: new Date().toISOString(),
        asset_path: destPath,
        image: { format: "png", width: resolved.width, height: resolved.height, bytes: imgData.length },
        provenance,
        judgment: null,
        canon: null,
        iteration: null,
      };

      await writeFile(
        join(GAME_ROOT, `records/${assetId}.json`),
        JSON.stringify(record, null, 2),
      );

      console.log(`    \x1b[32m✓\x1b[0m ${destPath} (${elapsed}ms, ${imgData.length} bytes)`);
    } catch (err) {
      console.log(`    \x1b[31m✗\x1b[0m ${err.message}`);
      errors++;
    }

    generated++;

    // ETA every 5 items (not every item — too noisy for long runs).
    if (!dryRun && generated > 0 && generated % 5 === 0 && generated < totalExpected) {
      const elapsedTotal = Date.now() - runStartMs;
      const avgMs = elapsedTotal / generated;
      const remaining = totalExpected - generated;
      const etaMs = avgMs * remaining;
      info('generate', `progress ${generated}/${totalExpected} — avg ${formatEta(avgMs)}/item, ETA ~${formatEta(etaMs)}`);
    }
  }

  // Persist any newly computed model hashes so the next wave reuses them.
  flushHashCache(hashCache);

  console.log("");
  const succeeded = generated - errors - skipped;
  const totalElapsedMs = Date.now() - runStartMs;
  const skippedSuffix = skipped > 0 ? `, ${skipped} resumed` : '';
  console.log(`\x1b[32m✓\x1b[0m Generated ${succeeded} candidates (${errors} errors${skippedSuffix})`);
  if (!dryRun && generated > skipped) {
    const ran = generated - skipped;
    const avgMs = totalElapsedMs / ran;
    console.log(`  Total: ${formatEta(totalElapsedMs)} — avg ${formatEta(avgMs)}/item over ${ran} new`);
  }
  if (dryRun) console.log("  (dry run — no images produced)");
  // Always print the output directory so scripted pipelines can parse it,
  // even under --quiet.
  if (!dryRun && succeeded > 0) {
    result(`Candidates: ${join(GAME_ROOT, 'outputs/candidates')}`);
    result(`Records: ${join(GAME_ROOT, 'records')}`);
  }
  if (!dryRun && errors > 0 && succeeded === 0) {
    throw runtimeError('RUNTIME_ALL_FAILED', `All ${totalExpected} generation attempts failed.`);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('generate.js') || process.argv[1].endsWith('generate'))) {
  run().catch(handleCliError);
}
