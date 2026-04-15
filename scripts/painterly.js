#!/usr/bin/env node

/**
 * painterly.js — img2img post-processing pass via ComfyUI.
 *
 * Takes existing candidate/approved images and runs them through an img2img
 * pass with a painterly style prompt at low denoise to shift from
 * photorealistic to concept-art aesthetic while preserving composition.
 *
 * Usage:
 *   node scripts/painterly.js [--source outputs/approved] [--limit 100] [--offset 0]
 *   node scripts/painterly.js --dry-run
 *   sdlab painterly --project star-freight --limit 50
 *
 * Output: outputs/painterly/<original_filename>
 */

import { writeFile, mkdir, readdir } from "node:fs/promises";
import { join } from "node:path";
import { existsSync } from "node:fs";
import { getProjectName } from "../lib/args.js";
import { REPO_ROOT } from "../lib/paths.js";
import { comfyHealth, submitAndWait, downloadImage, uploadImage } from "../lib/comfyui.js";

// ── Config ──

const PAINTERLY_PROMPT = [
  "oil painting, visible brushstrokes, painterly concept art,",
  "semi-realistic, muted dusty palette, subtle dark edges,",
  "atmospheric directional lighting, traditional media texture,",
  "canvas grain, impasto highlights, soft color blending,",
  "art station quality concept illustration"
].join(" ");

const PAINTERLY_NEGATIVE = [
  "photorealistic, photograph, photo, 3d render, smooth CG, CGI,",
  "octane render, sharp photo detail, camera noise, lens flare,",
  "film grain, bokeh, depth of field, DSLR, ultra realistic,",
  "text, watermark, signature, blurry, low quality"
].join(" ");

const DEFAULTS = {
  checkpoint: "dreamshaperXL_v21TurboDPMSDE.safetensors",
  lora: { name: "classipeintxl_v21.safetensors", weight: 1.0 },
  denoise: 0.50,       // Tested sweet spot — visible painterly texture, composition preserved
  steps: 10,
  cfg: 2.5,
  sampler: "dpmpp_sde",
  scheduler: "karras",
  seed: 42,            // Fixed seed for reproducibility across batch
};

function buildImg2ImgWorkflow(imagePath, seed) {
  const nodes = {};
  let nextId = 1;

  const ckptId = String(nextId++);
  nodes[ckptId] = {
    class_type: "CheckpointLoaderSimple",
    inputs: { ckpt_name: DEFAULTS.checkpoint },
  };

  let modelOut = [ckptId, 0];
  let clipOut = [ckptId, 1];

  const loraId = String(nextId++);
  nodes[loraId] = {
    class_type: "LoraLoader",
    inputs: {
      model: modelOut,
      clip: clipOut,
      lora_name: DEFAULTS.lora.name,
      strength_model: DEFAULTS.lora.weight,
      strength_clip: DEFAULTS.lora.weight,
    },
  };
  modelOut = [loraId, 0];
  clipOut = [loraId, 1];

  const loadImgId = String(nextId++);
  nodes[loadImgId] = {
    class_type: "LoadImage",
    inputs: { image: imagePath },
  };

  const vaeEncId = String(nextId++);
  nodes[vaeEncId] = {
    class_type: "VAEEncode",
    inputs: {
      pixels: [loadImgId, 0],
      vae: [ckptId, 2],
    },
  };

  const posId = String(nextId++);
  nodes[posId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: PAINTERLY_PROMPT, clip: clipOut },
  };

  const negId = String(nextId++);
  nodes[negId] = {
    class_type: "CLIPTextEncode",
    inputs: { text: PAINTERLY_NEGATIVE, clip: clipOut },
  };

  const samplerId = String(nextId++);
  nodes[samplerId] = {
    class_type: "KSampler",
    inputs: {
      model: modelOut,
      positive: [posId, 0],
      negative: [negId, 0],
      latent_image: [vaeEncId, 0],
      seed,
      steps: DEFAULTS.steps,
      cfg: DEFAULTS.cfg,
      sampler_name: DEFAULTS.sampler,
      scheduler: DEFAULTS.scheduler,
      denoise: DEFAULTS.denoise,
    },
  };

  const vaeDecId = String(nextId++);
  nodes[vaeDecId] = {
    class_type: "VAEDecode",
    inputs: {
      samples: [samplerId, 0],
      vae: [ckptId, 2],
    },
  };

  const saveId = String(nextId++);
  nodes[saveId] = {
    class_type: "SaveImage",
    inputs: {
      images: [vaeDecId, 0],
      filename_prefix: "painterly",
    },
  };

  return { nodes, saveNodeId: saveId };
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);
  const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";

  const dryRun = argv.includes("--dry-run");

  // Parse args
  let sourceDir = "outputs/approved";
  let limit = 100;
  let offset = 0;

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--source" && argv[i + 1]) sourceDir = argv[++i];
    if (argv[i] === "--limit" && argv[i + 1]) limit = parseInt(argv[++i]);
    if (argv[i] === "--offset" && argv[i + 1]) offset = parseInt(argv[++i]);
  }

  const fullSourceDir = join(GAME_ROOT, sourceDir);
  const outDir = join(GAME_ROOT, "outputs/painterly");
  await mkdir(outDir, { recursive: true });

  // Collect source PNGs
  const allFiles = (await readdir(fullSourceDir))
    .filter(f => f.endsWith(".png"))
    .sort();

  // Skip already-processed files
  const existingPainterly = new Set(
    existsSync(outDir) ? (await readdir(outDir)).filter(f => f.endsWith(".png")) : []
  );

  const toProcess = allFiles
    .filter(f => !existingPainterly.has(f))
    .slice(offset, offset + limit);

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m painterly pass`);
  console.log(`  Source: ${sourceDir}`);
  console.log(`  Total source images: ${allFiles.length}`);
  console.log(`  Already processed: ${existingPainterly.size}`);
  console.log(`  To process: ${toProcess.length}`);
  console.log(`  Denoise: ${DEFAULTS.denoise}`);
  console.log(`  LoRA weight: ${DEFAULTS.lora.weight}`);
  console.log("");

  if (toProcess.length === 0) {
    console.log("Nothing to process.");
    return;
  }

  if (!dryRun) {
    const online = await comfyHealth(COMFY_URL);
    if (!online) {
      throw new Error("ComfyUI not reachable at " + COMFY_URL);
    }
    console.log("\x1b[32m✓\x1b[0m ComfyUI online");
  }

  let processed = 0;
  let errors = 0;

  for (const file of toProcess) {
    const srcPath = join(fullSourceDir, file);
    console.log(`  [${processed + 1}/${toProcess.length}] ${file}`);

    if (dryRun) {
      processed++;
      continue;
    }

    try {
      const startMs = Date.now();

      // Upload source image to ComfyUI
      const uploadedName = await uploadImage(srcPath, file, COMFY_URL);

      // Build and submit img2img workflow
      const { nodes } = buildImg2ImgWorkflow(uploadedName, DEFAULTS.seed);
      const result = await submitAndWait(nodes, COMFY_URL, { clientPrefix: 'sdl-paint' });
      const elapsed = Date.now() - startMs;

      // Find output image
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
        console.log(`    \x1b[33m⚠\x1b[0m No output image`);
        errors++;
        processed++;
        continue;
      }

      // Download and save with original filename
      const imgData = await downloadImage(imageFile, imageSubfolder, COMFY_URL);
      await writeFile(join(outDir, file), imgData);

      const kb = Math.round(imgData.length / 1024);
      console.log(`    \x1b[32m✓\x1b[0m outputs/painterly/${file} (${elapsed}ms, ${kb}KB)`);

    } catch (err) {
      console.log(`    \x1b[31m✗\x1b[0m ${err.message}`);
      errors++;
    }

    processed++;
  }

  console.log(`\n\x1b[32m✓\x1b[0m Painterly pass: ${processed - errors} success, ${errors} errors`);
  if (dryRun) console.log("  (dry run — no images processed)");
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('painterly.js') || process.argv[1].endsWith('painterly'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
