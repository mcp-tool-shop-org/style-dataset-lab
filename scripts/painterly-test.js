#!/usr/bin/env node

/**
 * painterly-test.js — Test different denoise levels on a single image.
 * Outputs: outputs/painterly-test/<filename>_d<denoise>.png
 */

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";
const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

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

async function upload(filePath, filename) {
  const data = await readFile(filePath);
  const form = new FormData();
  form.append("image", new Blob([data], { type: "image/png" }), filename);
  form.append("overwrite", "true");
  const res = await fetch(`${COMFY_URL}/upload/image`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status} ${await res.text()}`);
  return (await res.json()).name;
}

const MAX_POLL_MS = 600_000; // 10 minutes

async function run(workflow) {
  const res = await fetch(`${COMFY_URL}/prompt`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: workflow, client_id: `test-${Date.now()}` }),
  });
  if (!res.ok) throw new Error(`ComfyUI submit failed: ${res.status} ${await res.text()}`);
  const { prompt_id: promptId } = await res.json();
  const start = Date.now();
  while (true) {
    if (Date.now() - start > MAX_POLL_MS) throw new Error(`ComfyUI poll timeout after ${MAX_POLL_MS/1000}s for prompt ${promptId}`);
    await new Promise(r => setTimeout(r, 1000));
    const histRes = await fetch(`${COMFY_URL}/history/${promptId}`);
    if (!histRes.ok) continue;
    const h = await histRes.json();
    if (h[promptId]?.status?.completed) return h[promptId];
  }
}

async function download(filename, subfolder) {
  const res = await fetch(`${COMFY_URL}/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(subfolder || "")}&type=output`);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

async function main() {
  const outDir = join(GAME_ROOT, "outputs/painterly-test");
  await mkdir(outDir, { recursive: true });

  // Pick two test images — one character, one environment
  const testFiles = [
    "outputs/approved/arch_keth_hex_chamber_v1.png",
    "outputs/approved/anchor_04_pilot_v1.png",
  ];

  const denoiseTests = [0.50, 0.60, 0.70];
  const loraWeight = 1.0;  // Full LoRA weight for stronger effect

  for (const testFile of testFiles) {
    const srcPath = join(GAME_ROOT, testFile);
    const fname = testFile.split("/").pop().replace(".png", "");

    console.log(`\nTesting: ${fname}`);
    const uploaded = await upload(srcPath, `test_${fname}.png`);

    for (const denoise of denoiseTests) {
      const label = `${fname}_d${String(denoise).replace(".", "")}`;
      console.log(`  denoise=${denoise}, lora=${loraWeight} → ${label}.png`);

      const t = Date.now();
      const wf = buildWorkflow(uploaded, denoise, loraWeight, 42);
      const result = await run(wf);

      let imgFile, imgSub = "";
      for (const o of Object.values(result.outputs || {})) {
        if (o.images?.length) { imgFile = o.images[0].filename; imgSub = o.images[0].subfolder || ""; break; }
      }

      const data = await download(imgFile, imgSub);
      await writeFile(join(outDir, `${label}.png`), data);
      console.log(`    ✓ ${Date.now() - t}ms`);
    }
  }

  console.log("\nDone — check outputs/painterly-test/");
}

main().catch(e => { console.error(e); process.exit(1); });
