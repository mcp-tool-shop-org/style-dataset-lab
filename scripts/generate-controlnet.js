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
 *   node scripts/generate-controlnet.js --subject corrigan --guide inputs/control-guides/corrigan_structural_guide.png --seeds 4
 *   node scripts/generate-controlnet.js --subject naia --guide ... --dry-run
 *
 * Options:
 *   --subject NAME   Subject name (used for output file naming)
 *   --guide PATH     Path to structural guide image (white-on-black silhouette)
 *   --prompt TEXT     Generation prompt (or reads from --prompt-file)
 *   --prompt-file F   JSON file with {prompt, negative} fields
 *   --negative TEXT   Negative prompt override
 *   --seeds N         Number of seeds (default: 4)
 *   --weight W        ControlNet weight (default: 0.70)
 *   --guidance-end E  ControlNet guidance end (default: 0.65)
 *   --model M         ControlNet model filename (default: controlnet-canny-sdxl-1.0.safetensors)
 *   --dry-run         Print workflow without running
 */

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";
const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");

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

function parseArgs() {
  const args = process.argv.slice(2);
  const get = (flag, def) => {
    const i = args.indexOf(flag);
    return i >= 0 && i + 1 < args.length ? args[i + 1] : def;
  };
  return {
    subject: get("--subject", "unknown"),
    guidePath: get("--guide", null),
    prompt: get("--prompt", null),
    promptFile: get("--prompt-file", null),
    negative: get("--negative", null),
    seeds: parseInt(get("--seeds", "4"), 10),
    weight: parseFloat(get("--weight", "0.70")),
    guidanceEnd: parseFloat(get("--guidance-end", "0.65")),
    controlModel: get("--model", "controlnet-canny-sdxl-1.0.safetensors"),
    dryRun: args.includes("--dry-run"),
  };
}

function buildControlNetWorkflow(prompt, negativePrompt, seed, guideImagePath, controlModel, weight, guidanceEnd) {
  const nodes = {};
  let nextId = 1;

  // Checkpoint
  const ckptId = String(nextId++);
  nodes[ckptId] = {
    class_type: "CheckpointLoaderSimple",
    inputs: { ckpt_name: DEFAULTS.checkpoint },
  };

  let modelOut = [ckptId, 0];
  let clipOut = [ckptId, 1];

  // LoRA
  for (const lora of DEFAULTS.loras) {
    const loraId = String(nextId++);
    nodes[loraId] = {
      class_type: "LoraLoader",
      inputs: {
        model: modelOut,
        clip: clipOut,
        lora_name: lora.name,
        strength_model: lora.weight,
        strength_clip: lora.weight,
      },
    };
    modelOut = [loraId, 0];
    clipOut = [loraId, 1];
  }

  // Load guide image
  const loadGuideId = String(nextId++);
  nodes[loadGuideId] = {
    class_type: "LoadImage",
    inputs: { image: guideImagePath },
  };

  // Load ControlNet model
  const cnLoadId = String(nextId++);
  nodes[cnLoadId] = {
    class_type: "ControlNetLoader",
    inputs: { control_net_name: controlModel },
  };

  // Positive prompt
  const posId = String(nextId++);
  nodes[posId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: prompt, clip: clipOut },
  };

  // Negative prompt
  const negId = String(nextId++);
  nodes[negId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: negativePrompt, clip: clipOut },
  };

  // Apply ControlNet (Advanced for start/end control)
  const cnApplyId = String(nextId++);
  nodes[cnApplyId] = {
    class_type: "ControlNetApplyAdvanced",
    inputs: {
      positive: [posId, 0],
      negative: [negId, 0],
      control_net: [cnLoadId, 0],
      image: [loadGuideId, 0],
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

  // Save
  const saveId = String(nextId++);
  nodes[saveId] = {
    class_type: "SaveImage",
    inputs: { images: [vaeId, 0], filename_prefix: "cn" },
  };

  return nodes;
}

async function comfyHealth() {
  try {
    const res = await fetch(`${COMFY_URL}/system_stats`);
    return res.ok;
  } catch {
    return false;
  }
}

async function submitAndWait(workflow) {
  const clientId = `cn-${Date.now()}`;
  const res = await fetch(`${COMFY_URL}/prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: workflow, client_id: clientId }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`ComfyUI submit failed: ${res.status} ${text}`);
  }

  const { prompt_id } = await res.json();

  while (true) {
    await new Promise((r) => setTimeout(r, 1000));
    const histRes = await fetch(`${COMFY_URL}/history/${prompt_id}`);
    if (!histRes.ok) continue;
    const history = await histRes.json();
    const entry = history[prompt_id];
    if (!entry) continue;
    if (entry.status?.completed) return entry;
    if (entry.status?.status_str === "error") {
      throw new Error(`ComfyUI error: ${JSON.stringify(entry.status)}`);
    }
  }
}

async function downloadImage(filename, subfolder, type = "output") {
  const url = `${COMFY_URL}/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(subfolder || "")}&type=${type}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

async function main() {
  const opts = parseArgs();

  if (!opts.guidePath) {
    console.error("Error: --guide <path> is required");
    process.exit(1);
  }

  // Resolve prompt
  let prompt = opts.prompt;
  let negative = opts.negative;

  if (opts.promptFile && !prompt) {
    const pf = JSON.parse(await readFile(join(REPO_ROOT, opts.promptFile), "utf-8"));
    prompt = pf.prompt;
    negative = negative || pf.negative;
  }

  if (!prompt) {
    console.error("Error: --prompt or --prompt-file required");
    process.exit(1);
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
    const online = await comfyHealth();
    if (!online) {
      console.error("\x1b[31mError:\x1b[0m ComfyUI not reachable at " + COMFY_URL);
      process.exit(1);
    }
    console.log("\x1b[32m+\x1b[0m ComfyUI online");
  }

  // The guide image needs to be in ComfyUI's input directory
  // Copy it there
  const guideFullPath = join(REPO_ROOT, opts.guidePath);
  const guideData = await readFile(guideFullPath);
  const guideFilename = `cn_guide_${opts.subject}.png`;

  if (!opts.dryRun) {
    // Upload via ComfyUI upload endpoint
    const formData = new FormData();
    formData.append("image", new Blob([guideData], { type: "image/png" }), guideFilename);
    formData.append("overwrite", "true");

    const uploadRes = await fetch(`${COMFY_URL}/upload/image`, {
      method: "POST",
      body: formData,
    });

    if (!uploadRes.ok) {
      const text = await uploadRes.text();
      console.error(`Guide upload failed: ${uploadRes.status} ${text}`);
      process.exit(1);
    }
    const uploadResult = await uploadRes.json();
    console.log(`\x1b[32m+\x1b[0m Guide uploaded: ${uploadResult.name}`);
  }

  await mkdir(join(REPO_ROOT, "outputs/candidates"), { recursive: true });

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
      const result = await submitAndWait(workflow);
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

      const imgData = await downloadImage(imageFile, imageSubfolder);
      await writeFile(join(REPO_ROOT, destPath), imgData);
      console.log(`    \x1b[32m+\x1b[0m ${destPath} (${elapsed}ms, ${imgData.length} bytes)`);
    } catch (err) {
      console.log(`    \x1b[31mx\x1b[0m ${err.message}`);
    }
  }

  console.log("\n\x1b[32m+\x1b[0m ControlNet discovery complete");
  if (opts.dryRun) console.log("  (dry run)");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
