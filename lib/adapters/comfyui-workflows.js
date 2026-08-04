/**
 * ComfyUI workflow adapter — builds executable ComfyUI prompt graphs from briefs.
 *
 * The brief carries everything needed: prompt, negative, runtime plan,
 * plus project defaults for checkpoint/LoRAs. This module translates
 * that into a ComfyUI node graph.
 */

import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { getRuntimeDir } from '../paths.js';

// ─── Template registry ───────────────────────────────────────────

/**
 * List available workflow templates from runtime/comfyui/.
 */
export function listWorkflowTemplates() {
  const dir = join(getRuntimeDir(), 'comfyui');
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter(f => f.endsWith('.json'))
    .map(f => {
      const data = JSON.parse(readFileSync(join(dir, f), 'utf-8'));
      return {
        template_id: data.template_id,
        label: data.label,
        compatible_modes: data.compatible_modes || [],
      };
    });
}

/**
 * Resolve a template for a given output mode.
 *
 * Returns the first template declaring `outputMode` in its `compatible_modes`,
 * and falls back to `'txt2img-standard'` when none matches — it does NOT
 * throw. (The docstring claimed a throw until 2026-08-04; a caller written
 * against that claim would guard a branch that cannot fire and would miss the
 * silent-default case, where an unrecognised mode renders through the standard
 * SDXL graph instead of failing loudly.)
 *
 * The fallback is also what makes an install with no `runtime/comfyui/`
 * templates degrade rather than crash — see `getRuntimeDir()` in lib/paths.js.
 */
export function resolveTemplateId(outputMode) {
  const templates = listWorkflowTemplates();
  const match = templates.find(t => t.compatible_modes.includes(outputMode));
  if (match) return match.template_id;
  // Default fallback for unknown modes
  return 'txt2img-standard';
}

// ─── Qwen-Image native defaults ──────────────────────────────────
// The studio's verified NON-ANIME base (Apache-2.0, on rig). See
// memory/studio-sprite-pipeline-2026-06.md + memory/feedback_no_anime.md.
// These mirror scripts/qwen_generate.py exactly so both runners emit an
// identical graph for a given (prompt, seed) — PIN_PER_STEP reproducibility.
export const QWEN_DEFAULTS = Object.freeze({
  unet: 'qwen_image_fp8_e4m3fn.safetensors',
  clip: 'qwen_2.5_vl_7b_fp8_scaled.safetensors',
  vae: 'qwen_image_vae.safetensors',
  clip_type: 'qwen_image',
  weight_dtype: 'default',
  shift: 3.1,
  sampler: 'euler',
  scheduler: 'simple',
  steps: 22,
  cfg: 3.5,
  width: 1024,
  height: 1024,
});

/**
 * Build the Qwen-Image ComfyUI prompt graph.
 *
 * Diffusion-transformer base (UNETLoader + qwen_image CLIP + SD3 latent +
 * AuraFlow model-sampling shift) — NOT an SDXL checkpoint. This is the studio's
 * non-anime path; never wire an anime checkpoint here. Node ids and wiring
 * match scripts/qwen_generate.py so output is reproducible across runners.
 *
 * `loras` chains DiT-only adapters (LoraLoaderModelOnly) between the
 * UNETLoader and ModelSamplingAuraFlow. Model-only on purpose: studio Qwen
 * style LoRAs train the transformer with the text encoder frozen, so there
 * is no clip strength to wire (unlike the SDXL LoraLoader path). LoRA node
 * ids start at '40' — also mirrored in qwen_generate.py.
 *
 * @returns {{ nodes: Object, saveNodeId: string }}
 */
export function buildQwenGraph({
  prompt,
  negativePrompt,
  seed,
  width = QWEN_DEFAULTS.width,
  height = QWEN_DEFAULTS.height,
  steps = QWEN_DEFAULTS.steps,
  cfg = QWEN_DEFAULTS.cfg,
  sampler = QWEN_DEFAULTS.sampler,
  scheduler = QWEN_DEFAULTS.scheduler,
  shift = QWEN_DEFAULTS.shift,
  unet = QWEN_DEFAULTS.unet,
  clip = QWEN_DEFAULTS.clip,
  vae = QWEN_DEFAULTS.vae,
  clipType = QWEN_DEFAULTS.clip_type,
  weightDtype = QWEN_DEFAULTS.weight_dtype,
  loras = [],
  filenamePrefix = 'sdl_run',
}) {
  const nodes = {
    '37': { class_type: 'UNETLoader', inputs: { unet_name: unet, weight_dtype: weightDtype } },
    '38': { class_type: 'CLIPLoader', inputs: { clip_name: clip, type: clipType } },
    '39': { class_type: 'VAELoader', inputs: { vae_name: vae } },
    '6': { class_type: 'CLIPTextEncode', inputs: { text: prompt, clip: ['38', 0] } },
    '7': { class_type: 'CLIPTextEncode', inputs: { text: negativePrompt, clip: ['38', 0] } },
  };

  // DiT LoRA chain: 37 → 40 → 41 → … → ModelSamplingAuraFlow.
  let modelOut = ['37', 0];
  let loraId = 40;
  for (const lora of loras) {
    const id = String(loraId++);
    nodes[id] = {
      class_type: 'LoraLoaderModelOnly',
      inputs: {
        lora_name: lora.name,
        strength_model: lora.weight ?? 1.0,
        model: modelOut,
      },
    };
    modelOut = [id, 0];
  }

  Object.assign(nodes, {
    '66': { class_type: 'ModelSamplingAuraFlow', inputs: { shift, model: modelOut } },
    '5': { class_type: 'EmptySD3LatentImage', inputs: { width, height, batch_size: 1 } },
    '3': {
      class_type: 'KSampler',
      inputs: {
        seed,
        steps,
        cfg,
        sampler_name: sampler,
        scheduler,
        denoise: 1.0,
        model: ['66', 0],
        positive: ['6', 0],
        negative: ['7', 0],
        latent_image: ['5', 0],
      },
    },
    '8': { class_type: 'VAEDecode', inputs: { samples: ['3', 0], vae: ['39', 0] } },
    '9': { class_type: 'SaveImage', inputs: { filename_prefix: filenamePrefix, images: ['8', 0] } },
  });
  return { nodes, saveNodeId: '9' };
}

// ─── Graph builder ───────────────────────────────────────────────

/**
 * Build a ComfyUI prompt graph from a compiled brief + project config.
 *
 * Dispatches on `projectDefaults.base`: `"qwen-image"` emits the Qwen graph
 * (non-anime studio base); anything else (default) emits the SDXL checkpoint →
 * LoRA chain → KSampler graph. The SDXL path is unchanged.
 *
 * @param {Object} opts
 * @param {Object} opts.brief — compiled brief from brief-compiler
 * @param {Object} opts.projectDefaults — project.json defaults block
 * @param {number} opts.seed — specific seed for this generation
 * @returns {{ nodes: Object, saveNodeId: string }}
 */
export function buildWorkflowGraph({ brief, projectDefaults, seed }) {
  const rp = brief.runtime_plan;
  const defaults = projectDefaults;

  const prompt = brief.prompt;
  const negativePrompt = brief.negative_prompt;

  // ── Qwen-Image branch (non-anime studio base) ──
  if (String(defaults.base || '').toLowerCase() === 'qwen-image') {
    return buildQwenGraph({
      prompt,
      negativePrompt,
      seed,
      width: rp.width || defaults.width || QWEN_DEFAULTS.width,
      height: rp.height || defaults.height || QWEN_DEFAULTS.height,
      steps: rp.steps || defaults.steps || QWEN_DEFAULTS.steps,
      cfg: rp.cfg || defaults.cfg || QWEN_DEFAULTS.cfg,
      sampler: rp.sampler || defaults.sampler || QWEN_DEFAULTS.sampler,
      scheduler: rp.scheduler || defaults.scheduler || QWEN_DEFAULTS.scheduler,
      shift: defaults.shift ?? QWEN_DEFAULTS.shift,
      unet: defaults.unet || QWEN_DEFAULTS.unet,
      clip: defaults.clip || QWEN_DEFAULTS.clip,
      vae: defaults.vae || QWEN_DEFAULTS.vae,
      clipType: defaults.clip_type || QWEN_DEFAULTS.clip_type,
      weightDtype: defaults.weight_dtype || QWEN_DEFAULTS.weight_dtype,
      loras: defaults.loras || [],
    });
  }

  // ── SDXL branch (default) ──
  const checkpoint = defaults.checkpoint;
  const loras = defaults.loras || [];
  const width = rp.width || defaults.width || 1024;
  const height = rp.height || defaults.height || 1024;
  const steps = rp.steps || defaults.steps || 30;
  const cfg = rp.cfg || defaults.cfg || 6.5;
  const sampler = rp.sampler || defaults.sampler || 'dpmpp_2m';
  const scheduler = rp.scheduler || defaults.scheduler || 'karras';

  const nodes = {};
  let nextId = 1;

  // Checkpoint loader
  const ckptId = String(nextId++);
  nodes[ckptId] = {
    class_type: 'CheckpointLoaderSimple',
    inputs: { ckpt_name: checkpoint },
  };

  let modelOut = [ckptId, 0];
  let clipOut = [ckptId, 1];

  // LoRA loaders (chained)
  for (const lora of loras) {
    const loraId = String(nextId++);
    nodes[loraId] = {
      class_type: 'LoraLoader',
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
    class_type: 'CLIPTextEncode',
    inputs: { text: prompt, clip: clipOut },
  };

  // CLIP Text Encode — negative
  const negId = String(nextId++);
  nodes[negId] = {
    class_type: 'CLIPTextEncode',
    inputs: { text: negativePrompt, clip: clipOut },
  };

  // Empty latent image
  const latentId = String(nextId++);
  nodes[latentId] = {
    class_type: 'EmptyLatentImage',
    inputs: { width, height, batch_size: 1 },
  };

  // KSampler
  const samplerId = String(nextId++);
  nodes[samplerId] = {
    class_type: 'KSampler',
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
    class_type: 'VAEDecode',
    inputs: {
      samples: [samplerId, 0],
      vae: [ckptId, 2],
    },
  };

  // Save Image
  const saveId = String(nextId++);
  nodes[saveId] = {
    class_type: 'SaveImage',
    inputs: {
      images: [vaeId, 0],
      filename_prefix: 'sdl_run',
    },
  };

  return { nodes, saveNodeId: saveId };
}
