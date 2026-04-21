#!/usr/bin/env node

/**
 * generate-controlnet.js — ControlNet-guided discovery for structural subjects.
 *
 * For subjects where txt2img fails on anatomy (Naia) or scale (Corrigan),
 * this script uses a structural guide image with ControlNet to force
 * the body plan / hull shape, then lets SDXL fill surface language.
 *
 * Usage:
 *   node scripts/generate-controlnet.js --subject naia --guide inputs/control-guides/naia_structural_guide.png --seeds 4
 *   sdlab generate:controlnet --subject naia --guide <path> --seeds 4 --project star-freight
 */

import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { getProjectName, parseNumberFlag } from "../lib/args.js";
import { REPO_ROOT, resolveSafeProjectPath } from "../lib/paths.js";
import { readJsonFile } from "../lib/config.js";
import { inputError, runtimeError, handleCliError } from "../lib/errors.js";
import { comfyHealth, submitAndWait, downloadImage, uploadImage } from "../lib/comfyui.js";

const DEFAULTS = {
  checkpoint: "dreamshaperXL_v21TurboDPMSDE.safetensors",
  loras: [{ name: "classipeintxl_v21.safetensors", weight: 1.0 }],
  steps: 12,
  cfg: 2.5,
  sampler: "dpmpp_sde",
  scheduler: "karras",
  width: 1024,
  height: 1024,
  base_seed: 27100,
};

function parseLocalArgs(argv) {
  const get = (flag, def) => {
    const i = argv.indexOf(flag);
    if (i < 0 || i + 1 >= argv.length) return def;
    const v = argv[i + 1];
    if (typeof v === 'string' && v.startsWith('--')) {
      throw inputError('INPUT_MISSING_VALUE', `Flag ${flag} is missing its value (got another flag: ${v}).`);
    }
    return v;
  };
  return {
    subject: get("--subject", "unknown"),
    guidePath: get("--guide", null),
    prompt: get("--prompt", null),
    promptFile: get("--prompt-file", null),
    negative: get("--negative", null),
    seeds: parseNumberFlag('seeds', get("--seeds", "4"), { int: true, min: 1 }),
    weight: parseNumberFlag('weight', get("--weight", "0.70"), { min: 0, max: 2 }),
    guidanceEnd: parseNumberFlag('guidance-end', get("--guidance-end", "0.65"), { min: 0, max: 1 }),
    controlModel: get("--model", "controlnet-canny-sdxl-1.0.safetensors"),
    dryRun: argv.includes("--dry-run"),
  };
}

function buildControlNetWorkflow(prompt, negativePrompt, seed, guideImagePath, controlModel, weight, guidanceEnd) {
  const nodes = {};
  let nextId = 1;

  const ckptId = String(nextId++);
  nodes[ckptId] = {
    class_type: "CheckpointLoaderSimple",
    inputs: { ckpt_name: DEFAULTS.checkpoint },
  };

  let modelOut = [ckptId, 0];
  let clipOut = [ckptId, 1];

  for (const lora of DEFAULTS.loras) {
    const loraId = String(nextId++);
    nodes[loraId] = {
      class_type: "LoraLoader",
      inputs: {
        model: modelOut, clip: clipOut,
        lora_name: lora.name,
        strength_model: lora.weight, strength_clip: lora.weight,
      },
    };
    modelOut = [loraId, 0];
    clipOut = [loraId, 1];
  }

  // Load guide image
  const guideId = String(nextId++);
  nodes[guideId] = {
    class_type: "LoadImage",
    inputs: { image: guideImagePath },
  };

  // ControlNet loader
  const cnLoadId = String(nextId++);
  nodes[cnLoadId] = {
    class_type: "ControlNetLoader",
    inputs: { control_net_name: controlModel },
  };

  // Text encoders
  const posId = String(nextId++);
  nodes[posId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: prompt, clip: clipOut },
  };

  const negId = String(nextId++);
  nodes[negId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: negativePrompt, clip: clipOut },
  };

  // Apply ControlNet
  const cnApplyId = String(nextId++);
  nodes[cnApplyId] = {
    class_type: "ControlNetApplyAdvanced",
    inputs: {
      positive: [posId, 0],
      negative: [negId, 0],
      control_net: [cnLoadId, 0],
      image: [guideId, 0],
      strength: weight,
      start_percent: 0.0,
      end_percent: guidanceEnd,
    },
  };

  // Empty latent
  const latentId = String(nextId++);
  nodes[latentId] = {
    class_type: "EmptyLatentImage",
    inputs: { width: DEFAULTS.width, height: DEFAULTS.height, batch_size: 1 },
  };

  // KSampler
  const samplerId = String(nextId++);
  nodes[samplerId] = {
    class_type: "KSampler",
    inputs: {
      model: modelOut,
      positive: [cnApplyId, 0],
      negative: [cnApplyId, 1],
      latent_image: [latentId, 0],
      seed,
      steps: DEFAULTS.steps,
      cfg: DEFAULTS.cfg,
      sampler_name: DEFAULTS.sampler,
      scheduler: DEFAULTS.scheduler,
      denoise: 1.0,
    },
  };

  // VAE Decode
  const vaeId = String(nextId++);
  nodes[vaeId] = {
    class_type: "VAEDecode",
    inputs: { samples: [samplerId, 0], vae: [ckptId, 2] },
  };

  const saveId = String(nextId++);
  nodes[saveId] = {
    class_type: "SaveImage",
    inputs: { images: [vaeId, 0], filename_prefix: "cn" },
  };

  return nodes;
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);
  const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";

  const opts = parseLocalArgs(argv);

  if (!opts.guidePath) {
    throw inputError('INPUT_MISSING_FLAG', "--guide <path> is required");
  }

  // Validate guide stays inside the project tree.
  const safeGuide = resolveSafeProjectPath(GAME_ROOT, opts.guidePath, { flagName: 'guide' });

  // Resolve prompt
  let prompt = opts.prompt;
  let negative = opts.negative;

  if (opts.promptFile && !prompt) {
    const safePromptFile = resolveSafeProjectPath(GAME_ROOT, opts.promptFile, { flagName: 'prompt-file' });
    const pf = await readJsonFile(safePromptFile, { requiredFields: ['prompt'] });
    prompt = pf.prompt;
    negative = negative || pf.negative;
  }

  if (!prompt) {
    throw inputError('INPUT_MISSING_FLAG', "--prompt or --prompt-file required");
  }

  if (!negative) {
    negative = "photorealistic, photograph, 3d render, smooth CG, anime, cartoon, text, watermark, blurry, low quality";
  }

  console.log("\x1b[1mstyle-dataset-lab\x1b[0m ControlNet structural discovery");
  console.log(`  Subject: ${opts.subject}`);
  console.log(`  Guide: ${opts.guidePath}`);
  console.log(`  ControlNet model: ${opts.controlModel}`);
  console.log(`  Weight: ${opts.weight}, Guidance end: ${opts.guidanceEnd}`);
  console.log(`  Seeds: ${opts.seeds}`);
  console.log(`  Steps: ${DEFAULTS.steps}, CFG: ${DEFAULTS.cfg}`);
  console.log("");

  if (!opts.dryRun) {
    const online = await comfyHealth(COMFY_URL);
    if (!online) {
      throw runtimeError('RUNTIME_COMFY_UNREACHABLE', "ComfyUI not reachable at " + COMFY_URL);
    }
    console.log("\x1b[32m+\x1b[0m ComfyUI online");
  }

  const guideFullPath = safeGuide;
  const guideFilename = `cn_guide_${opts.subject}.png`;

  if (!opts.dryRun) {
    await uploadImage(guideFullPath, guideFilename, COMFY_URL);
    console.log(`\x1b[32m+\x1b[0m Guide uploaded: ${guideFilename}`);
  }

  await mkdir(join(GAME_ROOT, "outputs/candidates"), { recursive: true });

  let successes = 0, failures = 0;
  for (let si = 0; si < opts.seeds; si++) {
    const seed = DEFAULTS.base_seed + si;
    const assetId = `${opts.subject}_cn_s${si}`;
    const destPath = `outputs/candidates/${assetId}.png`;

    console.log(`  [${si + 1}/${opts.seeds}] ${assetId} (seed: ${seed})`);

    if (opts.dryRun) continue;

    const startMs = Date.now();
    const workflow = buildControlNetWorkflow(
      prompt, negative, seed,
      guideFilename, opts.controlModel,
      opts.weight, opts.guidanceEnd
    );

    try {
      const result = await submitAndWait(workflow, COMFY_URL, { clientPrefix: 'cn' });
      const elapsed = Date.now() - startMs;

      const outputs = result.outputs || {};
      let imageFile = null;
      let imageSubfolder = "";
      for (const nodeOut of Object.values(outputs)) {
        if (nodeOut.images?.length > 0) {
          imageFile = nodeOut.images[0].filename;
          imageSubfolder = nodeOut.images[0].subfolder || "";
          break;
        }
      }

      if (!imageFile) {
        console.log("    \x1b[33m!\x1b[0m No output image");
        continue;
      }

      const imgData = await downloadImage(imageFile, imageSubfolder, COMFY_URL);
      await writeFile(join(GAME_ROOT, destPath), imgData);
      console.log(`    \x1b[32m+\x1b[0m ${destPath} (${elapsed}ms, ${imgData.length} bytes)`);
      successes++;
    } catch (err) {
      console.log(`    \x1b[31mx\x1b[0m ${err.message}`);
      failures++;
    }
  }

  console.log(`\n\x1b[32m+\x1b[0m ControlNet discovery complete (${successes} success, ${failures} failed)`);
  if (opts.dryRun) console.log("  (dry run)");
  if (!opts.dryRun && failures > 0 && successes === 0) {
    throw runtimeError('RUNTIME_ALL_FAILED', `All ${opts.seeds} ControlNet generation attempts failed.`);
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('generate-controlnet.js') || process.argv[1].endsWith('generate-controlnet'))) {
  run().catch(handleCliError);
}
