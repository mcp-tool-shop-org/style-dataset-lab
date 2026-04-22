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
 *   sdlab generate:identity inputs/identity-packets/wave27a.json --project star-freight
 *
 * Options:
 *   --dry-run       Print what would be generated without touching ComfyUI
 *   --subject NAME  Only generate shots for one subject (by subject_name)
 *   --seeds N       Number of discovery seeds per shot (default: 3)
 *   --phase MODE    Generation phase: discovery | follow_on (default: discovery)
 *   --anchor FILE   Anchor source image path (required for --phase follow_on)
 *   --denoise N     Denoise strength for follow_on phase (default: 0.38)
 */

import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { getProjectName, parseNumberFlag } from "../lib/args.js";
import { REPO_ROOT, resolveSafeProjectPath } from "../lib/paths.js";
import { readJsonFile } from "../lib/config.js";
import { inputError, runtimeError, handleCliError } from "../lib/errors.js";
import { comfyHealth, submitAndWait, downloadImage } from "../lib/comfyui.js";

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

// ── ComfyUI Workflows ──

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

  const loadImgId = String(nextId++);
  nodes[loadImgId] = {
    class_type: "LoadImage",
    inputs: { image: imagePath },
  };

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

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);
  const COMFY_URL = process.env.COMFY_URL || "http://127.0.0.1:8188";

  // Collect positionals, skipping values that belong to known flags
  const knownFlagsWithValue = new Set(['--subject', '--seeds', '--phase', '--anchor', '--denoise', '--project', '--game']);
  const positionals = [];
  for (let k = 0; k < argv.length; k++) {
    const a = argv[k];
    if (a.startsWith('--')) {
      if (!a.includes('=') && knownFlagsWithValue.has(a)) k++;
      continue;
    }
    positionals.push(a);
  }
  const packPath = positionals[0];
  const dryRun = argv.includes("--dry-run");
  const subjectFilter = argv.includes("--subject")
    ? argv[argv.indexOf("--subject") + 1]
    : null;
  const seedCount = argv.includes("--seeds")
    ? parseNumberFlag('seeds', argv[argv.indexOf("--seeds") + 1], { int: true, min: 1 })
    : 3;
  const phase = argv.includes("--phase")
    ? argv[argv.indexOf("--phase") + 1]
    : "discovery";
  const anchorPath = argv.includes("--anchor")
    ? argv[argv.indexOf("--anchor") + 1]
    : null;
  const denoise = argv.includes("--denoise")
    ? parseNumberFlag('denoise', argv[argv.indexOf("--denoise") + 1], { min: 0, max: 1 })
    : 0.38;

  if (!packPath) {
    throw inputError('INPUT_MISSING_ARGS', "Usage: sdlab generate:identity <packet-file> [options]");
  }

  if (phase === "follow_on" && !anchorPath) {
    throw inputError('INPUT_MISSING_FLAG', "--phase follow_on requires --anchor <image-path>");
  }

  const fullPackPath = resolveSafeProjectPath(GAME_ROOT, packPath, { flagName: 'packet-file' });
  if (anchorPath) resolveSafeProjectPath(GAME_ROOT, anchorPath, { flagName: 'anchor' });
  const pack = await readJsonFile(fullPackPath, { requiredFields: ['subjects'] });

  const vErrors = validatePacket(pack);
  if (vErrors.length > 0) {
    throw inputError('INPUT_BAD_PACKET', "Packet validation failed:\n  " + vErrors.join("\n  "));
  }

  let subjects = pack.subjects;
  if (subjectFilter) {
    subjects = subjects.filter((s) => s.subject_name === subjectFilter);
    if (subjects.length === 0) {
      throw inputError('INPUT_UNKNOWN_SUBJECT', `No subject found with name '${subjectFilter}'`);
    }
  }

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
    const online = await comfyHealth(COMFY_URL);
    if (!online) {
      throw runtimeError('RUNTIME_COMFY_UNREACHABLE', "ComfyUI not reachable at " + COMFY_URL);
    }
    console.log("\x1b[32m+\x1b[0m ComfyUI online");
  }

  await mkdir(join(GAME_ROOT, "outputs/candidates"), { recursive: true });
  await mkdir(join(GAME_ROOT, "records"), { recursive: true });

  let generated = 0;
  let errors = 0;
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
          const result = await submitAndWait(workflow, COMFY_URL, { clientPrefix: 'idp' });
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

          const imgData = await downloadImage(imageFile, imageSubfolder, COMFY_URL);
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
          errors++;
        }

        generated++;
        imageIndex++;
      }
    }
  }

  const succeeded = generated - errors;
  console.log(`\n\x1b[32m+\x1b[0m Generated ${succeeded} images (${errors} errors)`);
  if (dryRun) console.log("  (dry run — no images produced)");
  if (!dryRun && errors > 0 && succeeded === 0) {
    throw runtimeError('RUNTIME_ALL_FAILED', `All ${generated} generation attempts failed.`);
  }

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

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('generate-identity.js') || process.argv[1].endsWith('generate-identity'))) {
  run().catch(handleCliError);
}
