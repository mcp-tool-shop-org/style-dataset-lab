#!/usr/bin/env node

/**
 * painterly-test.js — Test different denoise levels on a single image.
 * Outputs: outputs/painterly-test/<filename>_d<denoise>.png
 *
 * Usage:
 *   node scripts/painterly-test.js
 *   sdlab painterly:test --project star-freight
 */

import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { getProjectName } from "../lib/args.js";
import { REPO_ROOT } from "../lib/paths.js";
import { submitAndWait, downloadImage, uploadImage } from "../lib/comfyui.js";

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

function buildWorkflow(imagePath, denoise, loraWeight, seed) {
  const nodes = {};
  let n = 1;

  const ckpt = String(n++);
  nodes[ckpt] = { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: "dreamshaperXL_v21TurboDPMSDE.safetensors" } };

  let model = [ckpt, 0], clip = [ckpt, 1];

  const lora = String(n++);
  nodes[lora] = { class_type: "LoraLoader", inputs: { model, clip, lora_name: "classipeintxl_v21.safetensors", strength_model: loraWeight, strength_clip: loraWeight } };
  model = [lora, 0]; clip = [lora, 1];

  const img = String(n++);
  nodes[img] = { class_type: "LoadImage", inputs: { image: imagePath } };

  const enc = String(n++);
  nodes[enc] = { class_type: "VAEEncode", inputs: { pixels: [img, 0], vae: [ckpt, 2] } };

  const pos = String(n++);
  nodes[pos] = { class_type: "CLIPTextEncode", inputs: { text: PAINTERLY_PROMPT, clip } };

  const neg = String(n++);
  nodes[neg] = { class_type: "CLIPTextEncode", inputs: { text: PAINTERLY_NEGATIVE, clip } };

  const samp = String(n++);
  nodes[samp] = { class_type: "KSampler", inputs: {
    model, positive: [pos, 0], negative: [neg, 0], latent_image: [enc, 0],
    seed, steps: 10, cfg: 2.5, sampler_name: "dpmpp_sde", scheduler: "karras", denoise
  }};

  const dec = String(n++);
  nodes[dec] = { class_type: "VAEDecode", inputs: { samples: [samp, 0], vae: [ckpt, 2] } };

  const save = String(n++);
  nodes[save] = { class_type: "SaveImage", inputs: { images: [dec, 0], filename_prefix: "ptest" } };

  return nodes;
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'games', projectName);
  const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";

  const outDir = join(GAME_ROOT, "outputs/painterly-test");
  await mkdir(outDir, { recursive: true });

  // Pick two test images — one character, one environment
  const testFiles = [
    "outputs/approved/arch_keth_hex_chamber_v1.png",
    "outputs/approved/anchor_04_pilot_v1.png",
  ];

  const denoiseTests = [0.50, 0.60, 0.70];
  const loraWeight = 1.0;

  for (const testFile of testFiles) {
    const srcPath = join(GAME_ROOT, testFile);
    const fname = testFile.split("/").pop().replace(".png", "");

    console.log(`\nTesting: ${fname}`);
    const uploaded = await uploadImage(srcPath, `test_${fname}.png`, COMFY_URL);

    for (const denoise of denoiseTests) {
      const label = `${fname}_d${String(denoise).replace(".", "")}`;
      console.log(`  denoise=${denoise}, lora=${loraWeight} → ${label}.png`);

      const t = Date.now();
      const wf = buildWorkflow(uploaded, denoise, loraWeight, 42);
      const result = await submitAndWait(wf, COMFY_URL, { clientPrefix: 'test' });

      let imgFile, imgSub = "";
      for (const o of Object.values(result.outputs || {})) {
        if (o.images?.length) { imgFile = o.images[0].filename; imgSub = o.images[0].subfolder || ""; break; }
      }

      const data = await downloadImage(imgFile, imgSub, COMFY_URL);
      await writeFile(join(outDir, `${label}.png`), data);
      console.log(`    ✓ ${Date.now() - t}ms`);
    }
  }

  console.log("\nDone — check outputs/painterly-test/");
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('painterly-test.js') || process.argv[1].endsWith('painterly-test'))) {
  run().catch(e => { console.error(e.message || e); process.exit(1); });
}
