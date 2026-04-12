#!/usr/bin/env node

/**
 * generate.js — Drive ComfyUI to produce candidate assets from a prompt pack.
 *
 * Usage: node scripts/generate.js [--prompt-pack inputs/prompts/rpg-icons-lane1.json]
 *
 * For each subject × variation, submits a workflow to ComfyUI HTTP API,
 * downloads the output PNG, and writes a provenance record to records/.
 */

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join, basename } from "node:path";

const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";
const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");

// ── ComfyUI API helpers ──

async function comfyHealth() {
  try {
    const res = await fetch(`${COMFY_URL}/system_stats`);
    return res.ok;
  } catch {
    return false;
  }
}

function buildWorkflow(prompt, negativePrompt, checkpoint, loras, seed, steps, cfg, sampler, scheduler, width, height) {
  // Minimal KSampler workflow in API format
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

async function submitAndWait(workflow) {
  const clientId = `sdl-${Date.now()}`;

  // Submit
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

  // Poll history until complete
  while (true) {
    await new Promise((r) => setTimeout(r, 1000));
    const histRes = await fetch(`${COMFY_URL}/history/${prompt_id}`);
    if (!histRes.ok) continue;
    const history = await histRes.json();
    const entry = history[prompt_id];
    if (!entry) continue;
    if (entry.status?.completed) {
      return entry;
    }
    if (entry.status?.status_str === "error") {
      throw new Error(`ComfyUI generation failed: ${JSON.stringify(entry.status)}`);
    }
  }
}

async function downloadImage(filename, subfolder, type = "output") {
  const url = `${COMFY_URL}/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(subfolder || "")}&type=${type}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

// ── Main ──

async function main() {
  const args = process.argv.slice(2);
  const packPath = args.find((a) => !a.startsWith("--")) || "inputs/prompts/rpg-icons-lane1.json";
  const dryRun = args.includes("--dry-run");

  const fullPackPath = join(REPO_ROOT, packPath);
  const pack = JSON.parse(await readFile(fullPackPath, "utf-8"));

  console.log(`\x1b[1mstyle-dataset-lab\x1b[0m generate`);
  console.log(`  Lane: ${pack.lane}`);
  console.log(`  Subjects: ${pack.subjects.length}`);
  console.log(`  Variations: ${pack.variations.length}`);
  console.log(`  Total candidates: ${pack.subjects.length * pack.variations.length}`);
  console.log("");

  if (!dryRun) {
    const online = await comfyHealth();
    if (!online) {
      console.error("\x1b[31mError:\x1b[0m ComfyUI not reachable at " + COMFY_URL);
      console.error("Start ComfyUI: cd F:/AI-Models/ComfyUI-runtime && python main.py --listen 127.0.0.1 --port 8188");
      process.exit(1);
    }
    console.log("\x1b[32m✓\x1b[0m ComfyUI online");
  }

  await mkdir(join(REPO_ROOT, "outputs/candidates"), { recursive: true });
  await mkdir(join(REPO_ROOT, "records"), { recursive: true });

  const d = pack.defaults;
  let generated = 0;
  const totalExpected = pack.subjects.length * pack.variations.length;

  for (const subject of pack.subjects) {
    for (const variation of variation_list(pack.variations)) {
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
        const result = await submitAndWait(nodes);
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
        const imgData = await downloadImage(imageFile, imageSubfolder);
        const destPath = `outputs/candidates/${assetId}.png`;
        await writeFile(join(REPO_ROOT, destPath), imgData);

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
          join(REPO_ROOT, `records/${assetId}.json`),
          JSON.stringify(record, null, 2),
        );

        console.log(`    \x1b[32m✓\x1b[0m ${destPath} (${elapsed}ms, ${imgData.length} bytes)`);
      } catch (err) {
        console.log(`    \x1b[31m✗\x1b[0m ${err.message}`);
      }

      generated++;
    }
  }

  console.log("");
  console.log(`\x1b[32m✓\x1b[0m Generated ${generated} candidates`);
  if (dryRun) console.log("  (dry run — no images produced)");
}

function variation_list(variations) {
  return variations;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
