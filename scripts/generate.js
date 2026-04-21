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
import { join } from "node:path";
import { getProjectName } from "../lib/args.js";
import { REPO_ROOT, resolveSafeProjectPath } from "../lib/paths.js";
import { readJsonFile } from "../lib/config.js";
import { runtimeError, handleCliError } from "../lib/errors.js";
import { comfyHealth, submitAndWait, downloadImage } from "../lib/comfyui.js";

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

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);
  const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";

  // Extract first positional that isn't a value for a --flag.
  // parseArgs is overkill here; instead we skip tokens that come right after a --flag.
  const positionals = [];
  for (let k = 0; k < argv.length; k++) {
    const a = argv[k];
    if (a.startsWith('--')) {
      if (!a.includes('=') && k + 1 < argv.length && !argv[k + 1].startsWith('--')) k++;
      continue;
    }
    positionals.push(a);
  }
  const packPath = positionals[0] || "inputs/prompts/rpg-icons-lane1.json";
  const dryRun = argv.includes("--dry-run");

  const fullPackPath = resolveSafeProjectPath(GAME_ROOT, packPath, { flagName: 'pack-path' });
  const pack = await readJsonFile(fullPackPath, { requiredFields: ['lane', 'subjects', 'variations', 'defaults'] });

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m generate`);
  console.log(`  Lane: ${pack.lane}`);
  console.log(`  Subjects: ${pack.subjects.length}`);
  console.log(`  Variations: ${pack.variations.length}`);
  console.log(`  Total candidates: ${pack.subjects.length * pack.variations.length}`);
  console.log("");

  if (!dryRun) {
    const online = await comfyHealth(COMFY_URL);
    if (!online) {
      throw runtimeError('RUNTIME_COMFY_UNREACHABLE', "ComfyUI not reachable at " + COMFY_URL, 'Start ComfyUI or set COMFY_URL to the right host.');
    }
    console.log("\x1b[32m✓\x1b[0m ComfyUI online");
  }

  await mkdir(join(GAME_ROOT, "outputs/candidates"), { recursive: true });
  await mkdir(join(GAME_ROOT, "records"), { recursive: true });

  const d = pack.defaults;
  let generated = 0;
  let errors = 0;
  const totalExpected = pack.subjects.length * pack.variations.length;

  for (const subject of pack.subjects) {
    for (const variation of pack.variations) {
      const assetId = `${subject.id}_${variation.id}`;
      const seed = (d.base_seed + generated) + (variation.seed_offset || 0);
      const fullPrompt = `${pack.style_prefix}, ${subject.prompt}`;
      const loras = variation.loras || [];

      console.log(`  [${generated + 1}/${totalExpected}] ${assetId} (seed: ${seed}, loras: ${loras.length})`);

      if (dryRun) {
        generated++;
        continue;
      }

      const startMs = Date.now();
      const { nodes } = buildWorkflow(
        fullPrompt, pack.negative,
        d.checkpoint, loras, seed,
        d.steps, d.cfg, d.sampler, d.scheduler,
        d.width, d.height,
      );

      try {
        const result = await submitAndWait(nodes, COMFY_URL);
        const elapsed = Date.now() - startMs;

        // Find output image
        const outputs = result.outputs || {};
        let imageFile = null;
        let imageSubfolder = "";
        for (const nodeOut of Object.values(outputs)) {
          if (nodeOut.images && nodeOut.images.length > 0) {
            imageFile = nodeOut.images[0].filename;
            imageSubfolder = nodeOut.images[0].subfolder || "";
            break;
          }
        }

        if (!imageFile) {
          console.log(`    \x1b[33m⚠\x1b[0m No output image found`);
          generated++;
          continue;
        }

        // Download and save
        const imgData = await downloadImage(imageFile, imageSubfolder, COMFY_URL);
        const destPath = `outputs/candidates/${assetId}.png`;
        await writeFile(join(GAME_ROOT, destPath), imgData);

        // Write provenance record
        const record = {
          id: assetId,
          schema_version: "1.0.0",
          created_at: new Date().toISOString(),
          asset_path: destPath,
          image: { format: "png", width: d.width, height: d.height, bytes: imgData.length },
          provenance: {
            workflow_id: pack.lane,
            workflow_version: "1.0.0",
            checkpoint: d.checkpoint,
            loras,
            prompt: fullPrompt,
            negative_prompt: pack.negative,
            seed,
            steps: d.steps,
            cfg: d.cfg,
            sampler: d.sampler,
            scheduler: d.scheduler,
            width: d.width,
            height: d.height,
            generation_time_ms: elapsed,
            gpu_model: "RTX 5080",
            batch_index: generated,
          },
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
    }
  }

  console.log("");
  const succeeded = generated - errors;
  console.log(`\x1b[32m✓\x1b[0m Generated ${succeeded} candidates (${errors} errors)`);
  if (dryRun) console.log("  (dry run — no images produced)");
  if (!dryRun && errors > 0 && succeeded === 0) {
    throw runtimeError('RUNTIME_ALL_FAILED', `All ${totalExpected} generation attempts failed.`);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('generate.js') || process.argv[1].endsWith('generate'))) {
  run().catch(handleCliError);
}
