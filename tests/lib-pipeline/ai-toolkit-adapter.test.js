/**
 * Integration tests for the ai-toolkit adapter.
 *
 * Builds a small training package in a tmp dir and asserts that:
 *   - images land at dataset/<partition>/<record_id>.png
 *   - .txt caption sidecars sit next to images
 *   - metadata/<partition>.jsonl has structured rows
 *   - ai-toolkit-config.yaml parses as YAML and carries Flux fields
 *   - SDXL profiles are rejected with a clear error
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import YAML from 'yaml';
import { buildPackage, buildAiToolkitConfig } from '../../lib/adapters/ai-toolkit.js';

const fluxProfile = {
  profile_id: 'character-style-lora-flux',
  label: 'Character Style LoRA (Flux)',
  target_family: 'flux',
  asset_type: 'lora',
  caption_strategy: 'flux-natural-language',
  prompt_strategy: 'trigger-word',
  base_model_recommendations: ['black-forest-labs/FLUX.1-dev'],
  adapter_targets: ['ai-toolkit'],
  eligible_lanes: ['costume'],
};

const sdxlProfile = {
  ...fluxProfile,
  profile_id: 'character-style-lora',
  target_family: 'sdxl',
  caption_strategy: 'structured-metadata',
};

const fakeManifest = {
  source_export_id: 'exp-20260423-abcd',
  source_split_id: 'split-01',
};

async function makeProject() {
  const projectRoot = await mkdtemp(join(tmpdir(), 'sdlab-aitk-src-'));
  const packageDir = await mkdtemp(join(tmpdir(), 'sdlab-aitk-pkg-'));
  await mkdir(join(projectRoot, 'outputs', 'approved'), { recursive: true });
  // A minimal but real PNG header is enough — adapter only copies/symlinks bytes.
  const pngMagic = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  await writeFile(join(projectRoot, 'outputs', 'approved', 'anchor_01.png'), pngMagic);
  await writeFile(join(projectRoot, 'outputs', 'approved', 'anchor_02.png'), pngMagic);
  return { projectRoot, packageDir };
}

function cleanup(dirs) {
  return Promise.all(dirs.map(d => rm(d, { recursive: true, force: true })));
}

// Canonical rows (D6 shape) — what the records-flow produces via recordToRow,
// and what canon-build emits to dataset.jsonl. Adapters only understand rows.
function makeRows() {
  return [
    {
      schema_version: 'canon-build-dataset-1.0',
      entity_id: 'anchor_01',
      schema_kind: 'record',
      lane: 'costume',
      partition: 'train',
      asset_path: 'outputs/approved/anchor_01.png',
      caption: 'character_style_lora_flux style, a compact faction costume, On-style costume.',
      trigger: 'character_style_lora_flux',
      subject_filter_key: 'Jace Delvari',
      group: 'compact',
      pass_ratio: 0.9,
    },
    {
      schema_version: 'canon-build-dataset-1.0',
      entity_id: 'anchor_02',
      schema_kind: 'record',
      lane: 'costume',
      partition: 'train',
      asset_path: 'outputs/approved/anchor_02.png',
      caption: 'character_style_lora_flux style, a compact faction costume, Clean anchor.',
      trigger: 'character_style_lora_flux',
      subject_filter_key: 'Renna Vasik',
      group: 'compact',
      pass_ratio: 1.0,
    },
  ];
}

test('ai-toolkit adapter writes images, .txt sidecars, JSONL, and YAML config', async () => {
  const { projectRoot, packageDir } = await makeProject();
  try {
    const result = await buildPackage({
      packageDir,
      rows: makeRows(),
      profile: fluxProfile,
      manifest: fakeManifest,
      config: {},
      projectRoot,
      copy: true, // safer in tmp dirs than symlinks
    });

    assert.equal(result.imageCount, 2);

    // Image files
    const img1 = await readFile(join(packageDir, 'dataset', 'train', 'anchor_01.png'));
    assert.ok(img1.length > 0);

    // Caption sidecars next to images
    const cap1 = await readFile(join(packageDir, 'dataset', 'train', 'anchor_01.txt'), 'utf8');
    assert.ok(cap1.length > 0, 'caption sidecar non-empty');
    assert.ok(cap1.endsWith('\n'), 'caption ends with newline');

    // JSONL audit rows
    const jsonl = await readFile(join(packageDir, 'metadata', 'train.jsonl'), 'utf8');
    const rows = jsonl.trim().split('\n').map(l => JSON.parse(l));
    assert.equal(rows.length, 2);
    assert.equal(rows[0].record_id, 'anchor_01');
    assert.equal(rows[0].file, 'dataset/train/anchor_01.png');
    assert.equal(rows[0].caption_file, 'dataset/train/anchor_01.txt');
    assert.equal(rows[0].subject, 'Jace Delvari');

    // YAML config at package root
    const yamlText = await readFile(join(packageDir, 'ai-toolkit-config.yaml'), 'utf8');
    const cfg = YAML.parse(yamlText);
    assert.equal(cfg.job, 'extension');
    assert.equal(cfg.meta.name, 'character-style-lora-flux');
    assert.equal(cfg.config.name, 'character-style-lora-flux-exp-20260423-abcd');
    const process = cfg.config.process[0];
    assert.equal(process.type, 'sd_trainer');
    assert.equal(process.model.is_flux, true);
    assert.equal(process.model.quantize, true);
    assert.equal(process.model.name_or_path, 'black-forest-labs/FLUX.1-dev');
    assert.equal(process.train.noise_scheduler, 'flowmatch');
    assert.equal(process.train.optimizer, 'adamw8bit');
    assert.equal(process.train.dtype, 'bf16');
    assert.equal(process.sample.sampler, 'flowmatch');
    assert.equal(process.network.type, 'lora');
    assert.equal(process.datasets[0].folder_path, './dataset/train');
    assert.equal(process.datasets[0].caption_ext, 'txt');
  } finally {
    await cleanup([projectRoot, packageDir]);
  }
});

test('ai-toolkit adapter rejects SDXL profile with ADAPTER_TARGET_FAMILY_MISMATCH', async () => {
  const { projectRoot, packageDir } = await makeProject();
  try {
    await assert.rejects(
      () => buildPackage({
        packageDir,
        rows: makeRows(),
        profile: sdxlProfile,
        manifest: fakeManifest,
        config: {},
        projectRoot,
        copy: true,
      }),
      err => {
        assert.equal(err.code, 'ADAPTER_TARGET_FAMILY_MISMATCH');
        assert.match(err.message, /flux/);
        return true;
      }
    );
  } finally {
    await cleanup([projectRoot, packageDir]);
  }
});

test('buildAiToolkitConfig uses trigger derived from profile_id in sample prompt', () => {
  const cfg = buildAiToolkitConfig({ profile: fluxProfile, manifest: fakeManifest });
  const prompt = cfg.config.process[0].sample.prompts[0];
  assert.ok(prompt.startsWith('character_style_lora_flux'), `expected trigger prefix, got: ${prompt}`);
});

test('buildAiToolkitConfig falls back to FLUX.1-dev when profile has no base_model_recommendations', () => {
  const cfg = buildAiToolkitConfig({
    profile: { ...fluxProfile, base_model_recommendations: undefined },
    manifest: fakeManifest,
  });
  assert.equal(cfg.config.process[0].model.name_or_path, 'black-forest-labs/FLUX.1-dev');
});

test('buildAiToolkitConfig handles missing manifest source_export_id gracefully', () => {
  const cfg = buildAiToolkitConfig({ profile: fluxProfile, manifest: {} });
  assert.match(cfg.config.name, /^character-style-lora-flux-/);
});

test('buildAiToolkitConfig emits is_style: true when profile.is_style_lora === true', () => {
  const cfg = buildAiToolkitConfig({
    profile: { ...fluxProfile, is_style_lora: true },
    manifest: fakeManifest,
  });
  assert.equal(cfg.config.process[0].is_style, true);
});

test('buildAiToolkitConfig emits is_style: false when profile.is_style_lora is unset', () => {
  const cfg = buildAiToolkitConfig({ profile: fluxProfile, manifest: fakeManifest });
  assert.equal(cfg.config.process[0].is_style, false);
});

test('buildAiToolkitConfig emits is_style: false when profile.is_style_lora === false (per-character LoRA)', () => {
  const cfg = buildAiToolkitConfig({
    profile: { ...fluxProfile, is_style_lora: false },
    manifest: fakeManifest,
  });
  assert.equal(cfg.config.process[0].is_style, false);
});

// --- training_hyperparameters override (two-LoRA stack contract) ---

test('buildAiToolkitConfig: World-LoRA defaults when no hyperparameters set (rank 32, alpha = rank, steps 2500)', () => {
  const cfg = buildAiToolkitConfig({ profile: fluxProfile, manifest: fakeManifest });
  const process = cfg.config.process[0];
  assert.equal(process.network.linear, 32);
  assert.equal(process.network.linear_alpha, 32);
  assert.equal(process.train.steps, 2500);
});

test('buildAiToolkitConfig: training_hyperparameters.rank flows through to network.linear', () => {
  const cfg = buildAiToolkitConfig({
    profile: { ...fluxProfile, training_hyperparameters: { rank: 16 } },
    manifest: fakeManifest,
  });
  assert.equal(cfg.config.process[0].network.linear, 16);
  // alpha falls back to = rank when unset
  assert.equal(cfg.config.process[0].network.linear_alpha, 16);
});

test('buildAiToolkitConfig: training_hyperparameters.alpha flows through to network.linear_alpha', () => {
  const cfg = buildAiToolkitConfig({
    profile: { ...fluxProfile, training_hyperparameters: { rank: 16, alpha: 8 } },
    manifest: fakeManifest,
  });
  assert.equal(cfg.config.process[0].network.linear, 16);
  assert.equal(cfg.config.process[0].network.linear_alpha, 8);
});

test('buildAiToolkitConfig: training_hyperparameters.steps flows through to train.steps', () => {
  const cfg = buildAiToolkitConfig({
    profile: { ...fluxProfile, training_hyperparameters: { steps: 1800 } },
    manifest: fakeManifest,
  });
  assert.equal(cfg.config.process[0].train.steps, 1800);
});

test('buildAiToolkitConfig: per-character LoRA shape (rank 16, alpha 8, steps 2000, is_style false)', () => {
  const perCharacterProfile = {
    ...fluxProfile,
    profile_id: 'sf-kael-maren-lora',
    is_style_lora: false,
    training_hyperparameters: { rank: 16, alpha: 8, steps: 2000 },
    trigger_override: 'sf_kael_maren',
  };
  const cfg = buildAiToolkitConfig({ profile: perCharacterProfile, manifest: fakeManifest });
  const process = cfg.config.process[0];
  assert.equal(process.network.linear, 16);
  assert.equal(process.network.linear_alpha, 8);
  assert.equal(process.train.steps, 2000);
  assert.equal(process.is_style, false);
  assert.ok(process.sample.prompts[0].startsWith('sf_kael_maren'),
    `sample prompt should use the trigger_override, got: ${process.sample.prompts[0]}`);
});

test('buildAiToolkitConfig: trigger_override flows through to sample prompt', () => {
  const cfg = buildAiToolkitConfig({
    profile: { ...fluxProfile, trigger_override: 'sf_character_style' },
    manifest: fakeManifest,
  });
  const prompt = cfg.config.process[0].sample.prompts[0];
  assert.ok(prompt.startsWith('sf_character_style'),
    `expected override-derived trigger, got: ${prompt}`);
  assert.ok(!prompt.includes('character_style_lora_flux'),
    'override must replace the profile_id-derived token');
});
