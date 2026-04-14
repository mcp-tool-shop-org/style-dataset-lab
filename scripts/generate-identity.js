#!/usr/bin/env node

/**
 * generate-identity.js — Drive ComfyUI to produce named-subject identity images.
 *
 * Reads identity packets from inputs/identity-packets/ (NOT the archetype
 * prompt packs in inputs/prompts/). Emits records with extended `identity`
 * and `lineage` blocks per canon/identity-gates.md.
 *
 * Usage:
 *   node scripts/generate-identity.js inputs/identity-packets/wave27a-identity-spine.json
 *   node scripts/generate-identity.js inputs/identity-packets/wave27a-identity-spine.json --dry-run
 *   node scripts/generate-identity.js inputs/identity-packets/wave27a-identity-spine.json --subject kael_maren
 *   node scripts/generate-identity.js inputs/identity-packets/wave27a-identity-spine.json --seeds 3
 *
 * Options:
 *   --dry-run       Print what would be generated without touching ComfyUI
 *   --subject NAME  Only generate shots for one subject (by subject_name)
 *   --seeds N       Number of discovery seeds per shot (default: 3)
 *   --phase MODE    Generation phase: discovery | follow_on (default: discovery)
 *   --anchor FILE   Anchor source image path (required for --phase follow_on)
 *   --denoise N     Denoise strength for follow_on phase (default: 0.38)
 *
 * Phases:
 *   discovery   — txt2img from prompt, 3 seeds per shot. No prior image input.
 *   follow_on   — img2img from anchor image. Requires --anchor and --denoise.
 *                 Anchor curation happens between phases (manual step).
 */

import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { join } from "node:path";

const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";
const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

// ── Defaults (match existing lab pipeline) ──

const DEFAULTS = {
  checkpoint: "dreamshaperXL_v21TurboDPMSDE.safetensors",
  loras: [{ name: "classipeintxl_v21.safetensors", weight: 1.0 }],
  steps: 8,
  cfg: 2.0,
  sampler: "dpmpp_sde",
  scheduler: "karras",
  width: 1024,
  height: 1024,
  base_seed: 27000,
};

// ── Validation ──

const REQUIRED_IDENTITY_FIELDS = [
  "subject_name",
  "subject_type",
  "faction",
  "role",
];

const REQUIRED_SHOT_FIELDS = [
  "id",
  "view_type",
  "shot_type",
  "identity_anchor",
  "scene_function",
  "prompt",
];

const VALID_VIEW_TYPES = [
  "anchor_portrait",
  "full_body",
  "context",
  "expression_variant",
  "establishing",
  "signature_interior",
  "functional_detail",
  "lived_in_proof",
];

const VALID_VARIANT_INTENTS = [
  "persistence_under_shift",
  "role_read_shift",
];

function validatePacket(pack) {
  const errors = [];

  if (!pack.lane) errors.push("Missing 'lane'");
  if (!pack.style_prefix) errors.push("Missing 'style_prefix'");
  if (!pack.negative_base) errors.push("Missing 'negative_base'");
  if (!pack.subjects?.length) errors.push("No subjects defined");

  for (const subject of pack.subjects || []) {
    const sn = subject.subject_name || "(unnamed)";

    for (const field of REQUIRED_IDENTITY_FIELDS) {
      if (!subject[field]) {
        errors.push(`Subject ${sn}: missing required field '${field}'`);
      }
    }

    if (!subject.identity_lock) {
      errors.push(`Subject ${sn}: missing identity_lock`);
    } else if (subject.subject_type === "named_character") {
      if (!subject.identity_lock.non_negotiable_details?.length) {
        errors.push(`Subject ${sn}: identity_lock missing non_negotiable_details`);
      }
      if (!subject.identity_lock.forbidden_drift_cues?.length) {
        errors.push(`Subject ${sn}: identity_lock missing forbidden_drift_cues`);
      }
    } else if (subject.subject_type === "named_ship") {
      if (!subject.identity_lock.non_negotiable_details?.length) {
        errors.push(`Subject ${sn}: ship identity_lock missing non_negotiable_details`);
      }
      if (!subject.identity_lock.recurring_identity_cues?.length) {
        errors.push(`Subject ${sn}: ship identity_lock missing recurring_identity_cues`);
      }
    }

    for (const shot of subject.shots || []) {
      for (const field of REQUIRED_SHOT_FIELDS) {
        if (shot[field] === undefined || shot[field] === null) {
          errors.push(`Subject ${sn}, shot ${shot.id || "(unnamed)"}: missing '${field}'`);
        }
      }

      if (!VALID_VIEW_TYPES.includes(shot.view_type)) {
        errors.push(`Subject ${sn}, shot ${shot.id}: invalid view_type '${shot.view_type}'`);
      }

      // Variant intent enforcement
      if (shot.view_type === "expression_variant") {
        if (!shot.variant_intent) {
          errors.push(`Subject ${sn}, shot ${shot.id}: expression_variant missing variant_intent`);
        } else if (!VALID_VARIANT_INTENTS.includes(shot.variant_intent)) {
          errors.push(
            `Subject ${sn}, shot ${shot.id}: invalid variant_intent '${shot.variant_intent}'. ` +
            `Must be one of: ${VALID_VARIANT_INTENTS.join(", ")}`
          );
        }
        if (!shot.variant_constraint) {
          errors.push(`Subject ${sn}, shot ${shot.id}: expression_variant missing variant_constraint`);
        }
      }
    }
  }

  return errors;
}

// ── ComfyUI API ──

async function comfyHealth() {
  try {
    const res = await fetch(`${COMFY_URL}/system_stats`);
    return res.ok;
  } catch {
    return false;
  }
}

function buildTxt2ImgWorkflow(prompt, negativePrompt, seed) {
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
    inputs: { images: [vaeId, 0], filename_prefix: "idp" },
  };

  return nodes;
}

function buildImg2ImgWorkflow(prompt, negativePrompt, seed, imagePath, denoise) {
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

  // Load source image
  const loadImgId = String(nextId++);
  nodes[loadImgId] = {
    class_type: "LoadImage",
    inputs: { image: imagePath },
  };

  // Encode image to latent via VAE
  const encodeId = String(nextId++);
  nodes[encodeId] = {
    class_type: "VAEEncode",
    inputs: { pixels: [loadImgId, 0], vae: [ckptId, 2] },
  };

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

  const samplerId = String(nextId++);
  nodes[samplerId] = {
    class_type: "KSampler",
    inputs: {
      model: modelOut,
      positive: [posId, 0],
      negative: [negId, 0],
      latent_image: [encodeId, 0],
      seed,
      steps: 10,
      cfg: 2.5,
      sampler_name: DEFAULTS.sampler,
      scheduler: DEFAULTS.scheduler,
      denoise,
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
    inputs: { images: [vaeId, 0], filename_prefix: "idp" },
  };

  return nodes;
}

const MAX_POLL_MS = 600_000; // 10 minutes

async function submitAndWait(workflow) {
  const clientId = `idp-${Date.now()}`;
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

// ── Record Builder ──

function buildRecord(pack, subject, shot, seed, seedIndex, imgData, destPath, elapsedMs, phase, anchorInfo) {
  const assetId = `${shot.id}_s${seedIndex}`;
  const fullPrompt = `${pack.style_prefix}, ${shot.prompt}`;
  const negativePrompt = [
    pack.negative_base,
    shot.negative_additions || "",
  ].filter(Boolean).join(", ");

  return {
    id: assetId,
    schema_version: "2.0.0",
    created_at: new Date().toISOString(),
    asset_path: destPath,
    image: {
      format: "png",
      width: DEFAULTS.width,
      height: DEFAULTS.height,
      bytes: imgData.length,
    },
    provenance: {
      workflow_id: pack.lane,
      workflow_version: "1.0.0",
      checkpoint: DEFAULTS.checkpoint,
      loras: DEFAULTS.loras,
      prompt: fullPrompt,
      negative_prompt: negativePrompt,
      seed,
      steps: phase === "follow_on" ? 10 : DEFAULTS.steps,
      cfg: phase === "follow_on" ? 2.5 : DEFAULTS.cfg,
      sampler: DEFAULTS.sampler,
      scheduler: DEFAULTS.scheduler,
      width: DEFAULTS.width,
      height: DEFAULTS.height,
      generation_time_ms: elapsedMs,
      gpu_model: "RTX 5080",
      denoise: phase === "follow_on" ? (anchorInfo?.denoise || 0.38) : 1.0,
    },
    identity: {
      subject_name: subject.subject_name,
      subject_type: subject.subject_type,
      faction: subject.faction,
      role: subject.role,
      view_type: shot.view_type,
      shot_type: shot.shot_type,
      identity_anchor: shot.identity_anchor,
      location_name: shot.location_name || null,
      ship_name: subject.subject_type === "named_ship" ? subject.subject_name : null,
      scene_function: shot.scene_function,
      variant_intent: shot.variant_intent || null,
      variant_constraint: shot.variant_constraint || null,
    },
    lineage: {
      generation_phase: phase === "follow_on" ? "follow_on" : "discovery",
      anchor_source_image: anchorInfo?.source_image || null,
      anchor_subject_version: anchorInfo?.subject_version || null,
      identity_persistence_score: null,
      derived_from_record_id: anchorInfo?.record_id || null,
    },
    judgment: null,
    canon: null,
    iteration: null,
  };
}

// ── Main ──

async function main() {
  const args = process.argv.slice(2);
  const packPath = args.find((a) => !a.startsWith("--"));
  const dryRun = args.includes("--dry-run");
  const subjectFilter = args.includes("--subject")
    ? args[args.indexOf("--subject") + 1]
    : null;
  const seedCount = args.includes("--seeds")
    ? parseInt(args[args.indexOf("--seeds") + 1], 10)
    : 3;
  const phase = args.includes("--phase")
    ? args[args.indexOf("--phase") + 1]
    : "discovery";
  const anchorPath = args.includes("--anchor")
    ? args[args.indexOf("--anchor") + 1]
    : null;
  const denoise = args.includes("--denoise")
    ? parseFloat(args[args.indexOf("--denoise") + 1])
    : 0.38;

  if (!packPath) {
    console.error("Usage: node scripts/generate-identity.js <packet-file> [options]");
    process.exit(1);
  }

  if (phase === "follow_on" && !anchorPath) {
    console.error("Error: --phase follow_on requires --anchor <image-path>");
    process.exit(1);
  }

  const fullPackPath = join(GAME_ROOT, packPath);
  const pack = JSON.parse(await readFile(fullPackPath, "utf-8"));

  // Validate
  const errors = validatePacket(pack);
  if (errors.length > 0) {
    console.error("\x1b[31mPacket validation failed:\x1b[0m");
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }

  // Filter subjects if requested
  let subjects = pack.subjects;
  if (subjectFilter) {
    subjects = subjects.filter((s) => s.subject_name === subjectFilter);
    if (subjects.length === 0) {
      console.error(`No subject found with name '${subjectFilter}'`);
      process.exit(1);
    }
  }

  // Count shots
  const totalShots = subjects.reduce((sum, s) => sum + s.shots.length, 0);
  const totalImages = totalShots * seedCount;

  console.log("\x1b[1mstyle-dataset-lab\x1b[0m identity-packet generator");
  console.log(`  Lane: ${pack.lane}`);
  console.log(`  Phase: ${phase}`);
  console.log(`  Subjects: ${subjects.length}`);
  console.log(`  Shots: ${totalShots}`);
  console.log(`  Seeds per shot: ${seedCount}`);
  console.log(`  Total images: ${totalImages}`);
  if (phase === "follow_on") {
    console.log(`  Anchor: ${anchorPath}`);
    console.log(`  Denoise: ${denoise}`);
  }
  console.log("");

  if (!dryRun) {
    const online = await comfyHealth();
    if (!online) {
      console.error("\x1b[31mError:\x1b[0m ComfyUI not reachable at " + COMFY_URL);
      console.error(
        "Start ComfyUI: cd F:/AI-Models/ComfyUI-runtime && python main.py --listen 127.0.0.1 --port 8188"
      );
      process.exit(1);
    }
    console.log("\x1b[32m+\x1b[0m ComfyUI online");
  }

  await mkdir(join(GAME_ROOT, "outputs/candidates"), { recursive: true });
  await mkdir(join(GAME_ROOT, "records"), { recursive: true });

  let generated = 0;
  let imageIndex = 0;

  for (const subject of subjects) {
    console.log(`\n\x1b[1m${subject.subject_name}\x1b[0m (${subject.subject_type}, ${subject.faction})`);

    for (const shot of subject.shots) {
      console.log(`  ${shot.id} [${shot.view_type}]`);

      const fullPrompt = `${pack.style_prefix}, ${shot.prompt}`;
      const negativePrompt = [
        pack.negative_base,
        shot.negative_additions || "",
      ].filter(Boolean).join(", ");

      for (let si = 0; si < seedCount; si++) {
        const seed = DEFAULTS.base_seed + imageIndex;
        const assetId = `${shot.id}_s${si}`;
        const destPath = `outputs/candidates/${assetId}.png`;

        console.log(`    [${generated + 1}/${totalImages}] ${assetId} (seed: ${seed})`);

        if (dryRun) {
          generated++;
          imageIndex++;
          continue;
        }

        const startMs = Date.now();
        let workflow;

        if (phase === "follow_on") {
          workflow = buildImg2ImgWorkflow(fullPrompt, negativePrompt, seed, anchorPath, denoise);
        } else {
          workflow = buildTxt2ImgWorkflow(fullPrompt, negativePrompt, seed);
        }

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
            console.log("      \x1b[33m!\x1b[0m No output image");
            generated++;
            imageIndex++;
            continue;
          }

          const imgData = await downloadImage(imageFile, imageSubfolder);
          await writeFile(join(GAME_ROOT, destPath), imgData);

          const anchorInfo =
            phase === "follow_on"
              ? {
                  source_image: anchorPath,
                  subject_version: `${subject.subject_name}_v1`,
                  denoise,
                  record_id: null,
                }
              : null;

          const record = buildRecord(
            pack, subject, shot, seed, si,
            imgData, destPath, elapsed, phase, anchorInfo
          );

          await writeFile(
            join(GAME_ROOT, `records/${assetId}.json`),
            JSON.stringify(record, null, 2)
          );

          console.log(`      \x1b[32m+\x1b[0m ${destPath} (${elapsed}ms, ${imgData.length} bytes)`);
        } catch (err) {
          console.log(`      \x1b[31mx\x1b[0m ${err.message}`);
        }

        generated++;
        imageIndex++;
      }
    }
  }

  console.log(`\n\x1b[32m+\x1b[0m Generated ${generated} images`);
  if (dryRun) console.log("  (dry run — no images produced)");

  // Summary
  console.log("\nNext steps:");
  if (phase === "discovery") {
    console.log("  1. Review candidates in outputs/candidates/");
    console.log("  2. Select anchors and move to outputs/approved/");
    console.log("  3. Update anchor records: generation_phase -> 'anchor', identity_anchor -> true");
    console.log("  4. Run follow_on phase: --phase follow_on --anchor <anchor-image>");
  } else {
    console.log("  1. Review follow-on images against their anchor");
    console.log("  2. Score identity_persistence_score in the lineage block");
    console.log("  3. Apply identity gates (IC-1..6 or IL-1..5) for acceptance");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
