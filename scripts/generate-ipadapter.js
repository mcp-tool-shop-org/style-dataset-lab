#!/usr/bin/env node

/**
 * generate-ipadapter.js — IP-Adapter guided generation for structural subjects.
 *
 * Uses a reference image to guide the shape/structure of the output
 * while the text prompt adds identity-specific details.
 *
 * Usage:
 *   node scripts/generate-ipadapter.js --subject corrigan --ref <image> --seeds 4
 *   sdlab generate:ipadapter --subject corrigan --ref <image> --seeds 4 --project star-freight
 */

import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { getProjectName, parseNumberFlag } from "../lib/args.js";
import { REPO_ROOT, resolveSafeProjectPath } from "../lib/paths.js";
import { inputError, runtimeError, handleCliError } from "../lib/errors.js";
import { comfyHealth, submitAndWait, downloadImage, uploadImage } from "../lib/comfyui.js";

const DEFAULTS = {
  checkpoint: "dreamshaperXL_v21TurboDPMSDE.safetensors",
  loras: [{ name: "classipeintxl_v21.safetensors", weight: 1.0 }],
  ipadapter_model: "ip-adapter-plus_sdxl_vit-h.safetensors",
  clip_vision_model: "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
  steps: 10,
  cfg: 2.5,
  sampler: "dpmpp_sde",
  scheduler: "karras",
  width: 1024,
  height: 1024,
  base_seed: 27200,
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
    refPath: get("--ref", null),
    prompt: get("--prompt", null),
    negative: get("--negative", null),
    seeds: parseNumberFlag('seeds', get("--seeds", "4"), { int: true, min: 1 }),
    weight: parseNumberFlag('weight', get("--weight", "0.55"), { min: 0, max: 2 }),
    start: parseNumberFlag('start', get("--start", "0.0"), { min: 0, max: 1 }),
    end: parseNumberFlag('end', get("--end", "0.8"), { min: 0, max: 1 }),
    dryRun: argv.includes("--dry-run"),
  };
}

function buildIPAdapterWorkflow(prompt, negativePrompt, seed, refImageName, weight, start, end) {
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

  // CLIP Vision
  const clipVisionId = String(nextId++);
  nodes[clipVisionId] = {
    class_type: "CLIPVisionLoader",
    inputs: { clip_name: DEFAULTS.clip_vision_model },
  };

  // IP-Adapter model
  const ipaLoaderId = String(nextId++);
  nodes[ipaLoaderId] = {
    class_type: "IPAdapterModelLoader",
    inputs: { ipadapter_file: DEFAULTS.ipadapter_model },
  };

  // Load reference image
  const refImgId = String(nextId++);
  nodes[refImgId] = {
    class_type: "LoadImage",
    inputs: { image: refImageName },
  };

  // Apply IP-Adapter
  const ipaApplyId = String(nextId++);
  nodes[ipaApplyId] = {
    class_type: "IPAdapterAdvanced",
    inputs: {
      model: modelOut,
      ipadapter: [ipaLoaderId, 0],
      clip_vision: [clipVisionId, 0],
      image: [refImgId, 0],
      weight,
      weight_type: "linear",
      combine_embeds: "concat",
      embeds_scaling: "V only",
      start_at: start,
      end_at: end,
    },
  };
  modelOut = [ipaApplyId, 0];

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

  const latentId = String(nextId++);
  nodes[latentId] = {
    class_type: "EmptyLatentImage",
    inputs: { width: DEFAULTS.width, height: DEFAULTS.height, batch_size: 1 },
  };

  const samplerId = String(nextId++);
  nodes[samplerId] = {
    class_type: "KSampler",
    inputs: {
      model: modelOut,
      positive: [posId, 0],
      negative: [negId, 0],
      latent_image: [latentId, 0],
      seed,
      steps: DEFAULTS.steps,
      cfg: DEFAULTS.cfg,
      sampler_name: DEFAULTS.sampler,
      scheduler: DEFAULTS.scheduler,
      denoise: 1.0,
    },
  };

  const vaeId = String(nextId++);
  nodes[vaeId] = {
    class_type: "VAEDecode",
    inputs: { samples: [samplerId, 0], vae: [ckptId, 2] },
  };

  const saveId = String(nextId++);
  nodes[saveId] = {
    class_type: "SaveImage",
    inputs: { images: [vaeId, 0], filename_prefix: "ipa" },
  };

  return nodes;
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);
  const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";

  const opts = parseLocalArgs(argv);

  if (!opts.refPath) {
    throw inputError('INPUT_MISSING_FLAG', "--ref <path> is required");
  }
  if (!opts.prompt) {
    throw inputError('INPUT_MISSING_FLAG', "--prompt is required");
  }

  // Validate --ref path stays inside project tree.
  const safeRefPath = resolveSafeProjectPath(GAME_ROOT, opts.refPath, { flagName: 'ref' });

  const negative = opts.negative ||
    "photorealistic, photograph, 3d render, anime, cartoon, text, watermark, blurry, low quality";

  console.log("\x1b[1mstyle-dataset-lab\x1b[0m IP-Adapter structural discovery");
  console.log(`  Subject: ${opts.subject}`);
  console.log(`  Reference: ${opts.refPath}`);
  console.log(`  IP-Adapter: ${DEFAULTS.ipadapter_model}`);
  console.log(`  Weight: ${opts.weight}, Range: ${opts.start}-${opts.end}`);
  console.log(`  Seeds: ${opts.seeds}`);
  console.log("");

  const refFilename = `ipa_ref_${opts.subject}.png`;

  if (!opts.dryRun) {
    const online = await comfyHealth(COMFY_URL);
    if (!online) {
      throw runtimeError('RUNTIME_COMFY_UNREACHABLE', "ComfyUI not reachable at " + COMFY_URL);
    }
    console.log("\x1b[32m+\x1b[0m ComfyUI online");

    await uploadImage(safeRefPath, refFilename, COMFY_URL);
    console.log(`\x1b[32m+\x1b[0m Reference uploaded: ${refFilename}`);
  }

  await mkdir(join(GAME_ROOT, "outputs/candidates"), { recursive: true });

  for (let si = 0; si < opts.seeds; si++) {
    const seed = DEFAULTS.base_seed + si;
    const assetId = `${opts.subject}_ipa_s${si}`;
    const destPath = `outputs/candidates/${assetId}.png`;

    console.log(`  [${si + 1}/${opts.seeds}] ${assetId} (seed: ${seed})`);

    if (opts.dryRun) continue;

    const startMs = Date.now();
    const workflow = buildIPAdapterWorkflow(
      opts.prompt, negative, seed,
      refFilename, opts.weight, opts.start, opts.end
    );

    try {
      const result = await submitAndWait(workflow, COMFY_URL, { clientPrefix: 'ipa' });
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
    } catch (err) {
      console.log(`    \x1b[31mx\x1b[0m ${err.message}`);
    }
  }

  console.log("\n\x1b[32m+\x1b[0m IP-Adapter discovery complete");
  if (opts.dryRun) console.log("  (dry run)");
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('generate-ipadapter.js') || process.argv[1].endsWith('generate-ipadapter'))) {
  run().catch(handleCliError);
}
