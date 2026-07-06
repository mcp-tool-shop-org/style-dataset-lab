/**
 * Unit tests for the ComfyUI workflow builders.
 *
 * Covers the base dispatch added for the studio's non-anime Qwen-Image path:
 *   - buildQwenGraph emits the exact DiT graph (UNETLoader + qwen_image CLIP +
 *     SD3 latent + AuraFlow shift + euler/simple KSampler) — never a checkpoint
 *   - buildWorkflowGraph routes base="qwen-image" to the Qwen graph
 *   - buildWorkflowGraph default (no base) is the unchanged SDXL checkpoint→LoRA graph
 *   - node ids/wiring match scripts/qwen_generate.py for cross-runner reproducibility
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildQwenGraph, buildWorkflowGraph, QWEN_DEFAULTS } from '../../lib/adapters/comfyui-workflows.js';

test('buildQwenGraph emits the verified Qwen-Image graph (mirrors qwen_generate.py)', () => {
  const { nodes, saveNodeId } = buildQwenGraph({
    prompt: 'a painterly bog creature',
    negativePrompt: 'anime, cartoon',
    seed: 4000,
  });

  // Loaders — diffusion-transformer base, NOT an SDXL checkpoint.
  assert.equal(nodes['37'].class_type, 'UNETLoader');
  assert.equal(nodes['37'].inputs.unet_name, QWEN_DEFAULTS.unet);
  assert.equal(nodes['38'].class_type, 'CLIPLoader');
  assert.equal(nodes['38'].inputs.type, 'qwen_image');
  assert.equal(nodes['39'].class_type, 'VAELoader');

  // Sampling spine: AuraFlow shift 3.1 → SD3 latent → euler/simple.
  assert.equal(nodes['66'].class_type, 'ModelSamplingAuraFlow');
  assert.equal(nodes['66'].inputs.shift, 3.1);
  assert.equal(nodes['5'].class_type, 'EmptySD3LatentImage');
  assert.equal(nodes['3'].class_type, 'KSampler');
  assert.equal(nodes['3'].inputs.sampler_name, 'euler');
  assert.equal(nodes['3'].inputs.scheduler, 'simple');
  assert.equal(nodes['3'].inputs.seed, 4000);
  assert.deepEqual(nodes['3'].inputs.model, ['66', 0]);
  assert.deepEqual(nodes['3'].inputs.latent_image, ['5', 0]);

  // Decode/save.
  assert.equal(nodes['8'].class_type, 'VAEDecode');
  assert.equal(nodes['9'].class_type, 'SaveImage');
  assert.equal(saveNodeId, '9');

  // NEVER a checkpoint / LoRA loader on the Qwen path.
  const types = Object.values(nodes).map((n) => n.class_type);
  assert.ok(!types.includes('CheckpointLoaderSimple'));
  assert.ok(!types.includes('LoraLoader'));
});

test('buildQwenGraph honors overrides (models, shift, sampler, dims)', () => {
  const { nodes } = buildQwenGraph({
    prompt: 'p',
    negativePrompt: 'n',
    seed: 7,
    width: 768,
    height: 1152,
    steps: 30,
    cfg: 4.0,
    sampler: 'dpmpp_2m',
    scheduler: 'karras',
    shift: 2.5,
    unet: 'qwen_image_bf16.safetensors',
    vae: 'custom_vae.safetensors',
  });
  assert.equal(nodes['37'].inputs.unet_name, 'qwen_image_bf16.safetensors');
  assert.equal(nodes['39'].inputs.vae_name, 'custom_vae.safetensors');
  assert.equal(nodes['66'].inputs.shift, 2.5);
  assert.equal(nodes['5'].inputs.width, 768);
  assert.equal(nodes['5'].inputs.height, 1152);
  assert.equal(nodes['3'].inputs.steps, 30);
  assert.equal(nodes['3'].inputs.cfg, 4.0);
  assert.equal(nodes['3'].inputs.sampler_name, 'dpmpp_2m');
  assert.equal(nodes['3'].inputs.scheduler, 'karras');
});

test('buildQwenGraph chains DiT-only LoRAs between UNETLoader and AuraFlow shift', () => {
  const { nodes } = buildQwenGraph({
    prompt: 'p',
    negativePrompt: 'n',
    seed: 1,
    loras: [
      { name: 'tallow_fen_style_v1.safetensors', weight: 0.9 },
      { name: 'second.safetensors' }, // weight omitted → 1.0
    ],
  });
  // Chain: 37 → 40 → 41 → 66. Model-only loaders — Qwen style LoRAs train the
  // DiT with the text encoder frozen, so there is no clip strength to wire.
  assert.equal(nodes['40'].class_type, 'LoraLoaderModelOnly');
  assert.equal(nodes['40'].inputs.lora_name, 'tallow_fen_style_v1.safetensors');
  assert.equal(nodes['40'].inputs.strength_model, 0.9);
  assert.deepEqual(nodes['40'].inputs.model, ['37', 0]);
  assert.equal(nodes['41'].class_type, 'LoraLoaderModelOnly');
  assert.equal(nodes['41'].inputs.strength_model, 1.0);
  assert.deepEqual(nodes['41'].inputs.model, ['40', 0]);
  assert.deepEqual(nodes['66'].inputs.model, ['41', 0]);
  // Never the SDXL model+clip loader on the Qwen path.
  const types = Object.values(nodes).map((n) => n.class_type);
  assert.ok(!types.includes('LoraLoader'));
});

test('buildQwenGraph without loras keeps the bare verified graph (no LoRA nodes)', () => {
  const { nodes } = buildQwenGraph({ prompt: 'p', negativePrompt: 'n', seed: 1 });
  const types = Object.values(nodes).map((n) => n.class_type);
  assert.ok(!types.includes('LoraLoaderModelOnly'));
  assert.deepEqual(nodes['66'].inputs.model, ['37', 0]);
});

test('buildWorkflowGraph threads project defaults.loras into the Qwen graph', () => {
  const { nodes } = buildWorkflowGraph({
    brief: { runtime_plan: {}, prompt: 'creature', negative_prompt: 'anime' },
    projectDefaults: {
      base: 'qwen-image',
      loras: [{ name: 'tallow_fen_style_v1.safetensors', weight: 0.85 }],
    },
    seed: 9,
  });
  assert.equal(nodes['40'].class_type, 'LoraLoaderModelOnly');
  assert.equal(nodes['40'].inputs.strength_model, 0.85);
  assert.deepEqual(nodes['66'].inputs.model, ['40', 0]);
});

test('buildWorkflowGraph routes base="qwen-image" to the Qwen graph', () => {
  const { nodes, saveNodeId } = buildWorkflowGraph({
    brief: { runtime_plan: {}, prompt: 'creature', negative_prompt: 'anime' },
    projectDefaults: { base: 'qwen-image', steps: 22, cfg: 3.5, width: 1024, height: 1024 },
    seed: 4002,
  });
  const types = Object.values(nodes).map((n) => n.class_type);
  assert.ok(types.includes('UNETLoader'));
  assert.ok(types.includes('ModelSamplingAuraFlow'));
  assert.ok(!types.includes('CheckpointLoaderSimple'));
  assert.equal(nodes['3'].inputs.seed, 4002);
  assert.equal(saveNodeId, '9');
});

test('buildWorkflowGraph defaults to the unchanged SDXL graph', () => {
  const { nodes, saveNodeId } = buildWorkflowGraph({
    brief: { runtime_plan: {}, prompt: 'x', negative_prompt: 'y' },
    projectDefaults: {
      checkpoint: 'dreamshaperXL.safetensors',
      loras: [{ name: 'style.safetensors', weight: 0.8 }],
    },
    seed: 1,
  });
  const types = Object.values(nodes).map((n) => n.class_type);
  assert.ok(types.includes('CheckpointLoaderSimple'));
  assert.ok(types.includes('LoraLoader'));
  assert.ok(types.includes('EmptyLatentImage')); // SDXL latent, not SD3
  assert.ok(!types.includes('UNETLoader'));
  assert.ok(!types.includes('EmptySD3LatentImage'));
  // SaveImage exists and is the reported save node.
  assert.equal(nodes[saveNodeId].class_type, 'SaveImage');
});
