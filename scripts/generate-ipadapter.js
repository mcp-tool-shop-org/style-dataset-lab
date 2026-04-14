#!/usr/bin/env node

/**
 * generate-ipadapter.js — IP-Adapter guided generation for structural subjects.
 *
 * Uses a reference image to guide the shape/structure of the output
 * while the text prompt adds identity-specific details (wear, patching, name).
 *
 * Usage:
 *   node scripts/generate-ipadapter.js --subject corrigan --ref <image> --seeds 4
 *   node scripts/generate-ipadapter.js --subject corrigan --ref <image> --seeds 4 --dry-run
 *
 * Options:
 *   --subject NAME    Subject name for output file naming
 *   --ref PATH        Reference image path (the structural truth source)
 *   --prompt TEXT      Generation prompt
 *   --negative TEXT    Negative prompt
 *   --seeds N          Number of seeds (default: 4)
 *   --weight W         IP-Adapter weight (default: 0.55)
 *   --start S          IP-Adapter start (default: 0.0)
 *   --end E            IP-Adapter end (default: 0.8)
 *   --dry-run          Print workflow without running
 */

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";
const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

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

function parseArgs() {
  const args = process.argv.slice(2);
  const get = (flag, def) => {
    const i = args.indexOf(flag);
    return i >= 0 && i + 1 < args.length ? args[i + 1] : def;
  };
  return {
    subject: get("--subject", "unknown"),
    refPath: get("--ref", null),
    prompt: get("--prompt", null),
    negative: get("--negative", null),
    seeds: parseInt(get("--seeds", "4"), 10),
    weight: parseFloat(get("--weight", "0.55")),
    start: parseFloat(get("--start", "0.0")),
    end: parseFloat(get("--end", "0.8")),
    dryRun: args.includes("--dry-run"),
  };
}

function buildIPAdapterWorkflow(prompt, negativePrompt, seed, refImageName, weight, start, end) {
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

  // Load CLIP Vision
  const clipVisionId = String(nextId++);
  nodes[clipVisionId] = {
    class_type: "CLIPVisionLoader",
    inputs: { clip_name: DEFAULTS.clip_vision_model },
  };

  // Load IP-Adapter model
  const ipaLoadId = String(nextId++);
  nodes[ipaLoadId] = {
    class_type: "IPAdapterModelLoader",
    inputs: { ipadapter_file: DEFAULTS.ipadapter_model },
  };

  // Load reference image
  const refImgId = String(nextId++);
  nodes[refImgId] = {
    class_type: "LoadImage",
    inputs: { image: refImageName },
  };

  // Apply IP-Adapter (using IPAdapterAdvanced from ComfyUI_IPAdapter_plus)
  const ipaApplyId = String(nextId++);
  nodes[ipaApplyId] = {
    class_type: "IPAdapterAdvanced",
    inputs: {
      model: modelOut,
      ipadapter: [ipaLoadId, 0],
      image: [refImgId, 0],
      clip_vision: [clipVisionId, 0],
      weight: weight,
      weight_type: "linear",
      combine_embeds: "concat",
      start_at: start,
      end_at: end,
      embeds_scaling: "V only",
    },
  };
  modelOut = [ipaApplyId, 0];

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
    inputs: { images: [vaeId, 0], filename_prefix: "ipa" },
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

const MAX_POLL_MS = 600_000; // 10 minutes

async function submitAndWait(workflow) {
  const clientId = `ipa-${Date.now()}`;
  const res = await fetch(`${COMFY_URL}/prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: workflow, client_id: clientId }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`ComfyUI submit failed: ${res.status} ${text}`);
  }
  const { prompt_id: promptId } = await res.json();
  const start = Date.now();
  while (true) {
    if (Date.now() - start > MAX_POLL_MS) throw new Error(`ComfyUI poll timeout after ${MAX_POLL_MS/1000}s for prompt ${promptId}`);
    await new Promise((r) => setTimeout(r, 1000));
    const histRes = await fetch(`${COMFY_URL}/history/${promptId}`);
    if (!histRes.ok) continue;
    const history = await histRes.json();
    const entry = history[promptId];
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

  if (!opts.refPath) {
    console.error("Error: --ref <path> is required");
    process.exit(1);
  }
  if (!opts.prompt) {
    console.error("Error: --prompt is required");
    process.exit(1);
  }

  const negative = opts.negative ||
    "photorealistic, photograph, 3d render, anime, cartoon, text, watermark, blurry, low quality";

  console.log("\x1b[1mstyle-dataset-lab\x1b[0m IP-Adapter structural discovery");
  console.log(`  Subject: ${opts.subject}`);
  console.log(`  Reference: ${opts.refPath}`);
  console.log(`  IP-Adapter: ${DEFAULTS.ipadapter_model}`);
  console.log(`  Weight: ${opts.weight}, Range: ${opts.start}-${opts.end}`);
  console.log(`  Seeds: ${opts.seeds}`);
  console.log("");

  if (!opts.dryRun) {
    const online = await comfyHealth();
    if (!online) {
      console.error("\x1b[31mError:\x1b[0m ComfyUI not reachable");
      process.exit(1);
    }
    console.log("\x1b[32m+\x1b[0m ComfyUI online");

    // Upload reference image
    const refData = await readFile(join(GAME_ROOT, opts.refPath));
    const refFilename = `ipa_ref_${opts.subject}.png`;
    const formData = new FormData();
    formData.append("image", new Blob([refData], { type: "image/png" }), refFilename);
    formData.append("overwrite", "true");
    const uploadRes = await fetch(`${COMFY_URL}/upload/image`, { method: "POST", body: formData });
    if (!uploadRes.ok) {
      console.error(`Reference upload failed: ${uploadRes.status}`);
      process.exit(1);
    }
    const uploadResult = await uploadRes.json();
    console.log(`\x1b[32m+\x1b[0m Reference uploaded: ${uploadResult.name}`);
  }

  await mkdir(join(GAME_ROOT, "outputs/candidates"), { recursive: true });

  const refFilename = `ipa_ref_${opts.subject}.png`;

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
      await writeFile(join(GAME_ROOT, destPath), imgData);
      console.log(`    \x1b[32m+\x1b[0m ${destPath} (${elapsed}ms, ${imgData.length} bytes)`);
    } catch (err) {
      console.log(`    \x1b[31mx\x1b[0m ${err.message}`);
    }
  }

  console.log("\n\x1b[32m+\x1b[0m IP-Adapter discovery complete");
  if (opts.dryRun) console.log("  (dry run)");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
