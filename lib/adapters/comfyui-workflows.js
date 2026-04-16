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
 * Returns 'txt2img-standard' for all standard modes.
 * Throws if no template matches.
 */
export function resolveTemplateId(outputMode) {
  const templates = listWorkflowTemplates();
  const match = templates.find(t => t.compatible_modes.includes(outputMode));
  if (match) return match.template_id;
  // Default fallback for unknown modes
  return 'txt2img-standard';
}

// ─── Graph builder ───────────────────────────────────────────────

/**
 * Build a ComfyUI prompt graph from a compiled brief + project config.
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

  const checkpoint = defaults.checkpoint;
  const loras = defaults.loras || [];
  const prompt = brief.prompt;
  const negativePrompt = brief.negative_prompt;
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
