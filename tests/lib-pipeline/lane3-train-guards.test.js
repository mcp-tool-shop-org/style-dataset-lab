import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import YAML from 'yaml';

import {
  AI_TOOLKIT_UPSTREAM_ISSUE,
  getAiToolkitOverrideMetadata,
  buildAiToolkitConfig,
  buildPackage,
} from '../../lib/adapters/ai-toolkit.js';

import {
  buildTrainRunRecord,
  writeTrainRunJson,
  readTrainRunJson,
  attachEvalPackSha,
} from '../../lib/train-runs.js';

import {
  saveTrainingProfile,
  listTrainingProfiles,
  loadTrainingProfile,
} from '../../lib/training-profiles.js';

const FAKE_SHA_1 = 'sha256:' + '1'.repeat(64);
const FAKE_SHA_2 = 'sha256:' + '2'.repeat(64);
const FAKE_SHA_3 = 'sha256:' + '3'.repeat(64);
const FAKE_SHA_4 = 'sha256:' + '4'.repeat(64);

describe('Part D — Lane 3 LoRA training kit + C2 launcher guards (G12, G13, §3.3, §3.5, §9.2 item 6)', () => {
  it('G12 & §3.5: ai-toolkit adapter supports qwen-image target family, records py315 override sha256 + upstream issue #1087, and builds a package for cleared Portlight plsvessel data', async () => {
    assert.equal(AI_TOOLKIT_UPSTREAM_ISSUE, 'https://github.com/ostris/ai-toolkit/issues/1087');
    const overrideMeta = getAiToolkitOverrideMetadata();
    assert.ok(overrideMeta.override_file.endsWith('scripts/colab/locks/lane3.lock'));
    assert.match(overrideMeta.override_sha256, /^sha256:[0-9a-f]{64}$/);
    assert.equal(overrideMeta.upstream_issue, 'https://github.com/ostris/ai-toolkit/issues/1087');
    assert.ok(overrideMeta.packages.includes('scipy==1.12.0'));
    assert.ok(overrideMeta.packages.includes('matplotlib==3.10.1'));
    assert.ok(overrideMeta.packages.includes('sentencepiece==0.2.3'));

    // Studio Portlight ship data (plsvessel, MIT) is cleared for training and builds an ai-toolkit package
    const plsvesselProfile = {
      profile_id: 'plsvessel-portlight-ships-v1',
      label: 'Portlight Ships Anatomy LoRA (MIT)',
      target_family: 'qwen-image',
      asset_type: 'style-lora',
      eligible_lanes: ['ships'],
      adapter_targets: ['ai-toolkit'],
      trigger_override: 'plsvessel',
      is_style_lora: true,
      training_hyperparameters: {
        rank: 16,
        alpha: 16,
        steps: 1000,
        lr: 1e-4,
      },
    };
    const manifest = {
      source_export_id: 'exp_plsvessel_001',
    };

    const cfg = buildAiToolkitConfig({ profile: plsvesselProfile, manifest });
    const proc = cfg.config.process[0];
    assert.equal(proc.trigger_word, 'plsvessel');
    assert.equal(proc.model.arch, 'qwen_image');
    assert.equal(proc.model.name_or_path, 'Qwen/Qwen-Image');
    assert.equal(proc.model.quantize, true);
    assert.equal(proc.model.qtype, 'qfloat8');
    assert.equal(proc.model.quantize_te, true);
    assert.equal(proc.model.qtype_te, 'qfloat8');
    assert.equal(proc.model.low_vram, true);
    assert.equal(proc.network.linear, 16);
    assert.equal(proc.train.steps, 1000);
    assert.equal(cfg.meta.override_sha256, overrideMeta.override_sha256);
    assert.equal(cfg.meta.upstream_issue, 'https://github.com/ostris/ai-toolkit/issues/1087');
    assert.equal(cfg.meta.base_licence_id, 'Apache-2.0');

    // Also verify Flux-shaped config path
    const fluxProfile = {
      profile_id: 'plsvessel-flux-v1',
      target_family: 'flux',
      trigger_override: 'plsvessel',
    };
    const fluxCfg = buildAiToolkitConfig({ profile: fluxProfile, manifest });
    assert.equal(fluxCfg.config.process[0].model.is_flux, true);

    // buildPackage works for cleared plsvessel profile and rows
    const tmp = mkdtempSync(join(tmpdir(), 'sdlab-lane3-pkg-'));
    try {
      const imgPath = join(tmp, 'plsvessel_01.png');
      writeFileSync(imgPath, Buffer.from([0x89, 0x50, 0x4e, 0x47]));
      const pkgDir = join(tmp, 'pkg');
      const res = await buildPackage({
        packageDir: pkgDir,
        rows: [
          {
            entity_id: 'plsvessel_01',
            partition: 'train',
            asset_path: 'plsvessel_01.png',
            caption: 'plsvessel coastal timber brigantine orthographic plate',
            lane: 'ships',
          },
        ],
        profile: plsvesselProfile,
        manifest,
        projectRoot: tmp,
        copy: true,
      });
      assert.equal(res.imageCount, 1);
      const parsedYaml = YAML.parse(readFileSync(join(pkgDir, 'ai-toolkit-config.yaml'), 'utf-8'));
      assert.equal(parsedYaml.config.process[0].model.arch, 'qwen_image');
      assert.equal(parsedYaml.config.process[0].trigger_word, 'plsvessel');

      // Save, list, and load the cleared plsvessel training profile
      await saveTrainingProfile(tmp, plsvesselProfile);
      const listed = await listTrainingProfiles(tmp);
      assert.equal(listed.length, 1);
      assert.equal(listed[0].profile_id, 'plsvessel-portlight-ships-v1');
      const loadedProf = await loadTrainingProfile(tmp, 'plsvessel-portlight-ships-v1');
      assert.equal(loadedProf.trigger_override, 'plsvessel');
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it('G13 & §7: train-run.json links LoRA checkpoints + fixed-seed sample grids to dataset package sha256, config sha256, base model licence, window_id, and eval_pack_sha hook', () => {
    const tmp = mkdtempSync(join(tmpdir(), 'sdlab-lane3-run-'));
    try {
      const overrideMeta = getAiToolkitOverrideMetadata();
      // Refuses missing dataset_manifest_sha256
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'train_001',
            window_id: 'win_lane3_01',
            dataset_package_id: 'pkg_001',
            dataset_manifest_sha256: 'bad',
            config_sha256: FAKE_SHA_1,
            override_sha256: overrideMeta.override_sha256,
            base_model: {
              name: 'Qwen/Qwen-Image',
              sha256: FAKE_SHA_2,
              licence_id: 'Apache-2.0',
              licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
              date_read: '2026-11-05',
            },
            steps: [250],
            checkpoint_sha256s: { 250: FAKE_SHA_3 },
            sample_grid_sha256s: { 250: FAKE_SHA_4 },
          }),
        /TRAIN_RUN_SHA_INVALID/
      );

      // Refuses uncleared base model licence
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'train_001',
            window_id: 'win_lane3_01',
            dataset_package_id: 'pkg_001',
            dataset_manifest_sha256: FAKE_SHA_1,
            config_sha256: FAKE_SHA_1,
            override_sha256: overrideMeta.override_sha256,
            base_model: {
              name: 'black-forest-labs/FLUX.1-dev',
              sha256: FAKE_SHA_2,
              licence_id: 'FLUX-1-dev-non-commercial',
              licence_url: 'https://huggingface.co/black-forest-labs/FLUX.1-dev',
              date_read: '2026-11-05',
            },
            steps: [250],
            checkpoint_sha256s: { 250: FAKE_SHA_3 },
            sample_grid_sha256s: { 250: FAKE_SHA_4 },
          }),
        /TRAIN_RUN_LICENCE_INVALID/
      );

      // Additional validation branches in buildTrainRunRecord
      assert.throws(() => buildTrainRunRecord({}), /TRAIN_RUN_INVALID/);
      assert.throws(() => buildTrainRunRecord({ run_id: 'r1' }), /TRAIN_RUN_INVALID/);
      assert.throws(() => buildTrainRunRecord({ run_id: 'r1', window_id: 'w1' }), /TRAIN_RUN_INVALID/);
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'r1',
            window_id: 'w1',
            dataset_package_id: 'p1',
            dataset_manifest_sha256: FAKE_SHA_1,
            config_sha256: FAKE_SHA_2,
            base_model: null,
          }),
        /TRAIN_RUN_BASE_MODEL_INVALID/
      );
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'r1',
            window_id: 'w1',
            dataset_package_id: 'p1',
            dataset_manifest_sha256: FAKE_SHA_1,
            config_sha256: FAKE_SHA_2,
            base_model: { name: 'Qwen/Qwen-Image', sha256: 'bad' },
          }),
        /TRAIN_RUN_SHA_INVALID/
      );
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'r1',
            window_id: 'w1',
            dataset_package_id: 'p1',
            dataset_manifest_sha256: FAKE_SHA_1,
            config_sha256: FAKE_SHA_2,
            base_model: {
              name: 'Qwen/Qwen-Image',
              sha256: FAKE_SHA_2,
              licence_id: 'Apache-2.0',
              licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
              date_read: '2026-11-05',
            },
            steps: [],
          }),
        /TRAIN_RUN_STEPS_EMPTY/
      );
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'r1',
            window_id: 'w1',
            dataset_package_id: 'p1',
            dataset_manifest_sha256: FAKE_SHA_1,
            config_sha256: FAKE_SHA_2,
            base_model: {
              name: 'Qwen/Qwen-Image',
              sha256: FAKE_SHA_2,
              licence_id: 'Apache-2.0',
              licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
              date_read: '2026-11-05',
            },
            steps: [250],
            checkpoint_sha256s: {},
          }),
        /TRAIN_RUN_SHA_INVALID/
      );
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'r1',
            window_id: 'w1',
            dataset_package_id: 'p1',
            dataset_manifest_sha256: FAKE_SHA_1,
            config_sha256: FAKE_SHA_2,
            base_model: {
              name: 'Qwen/Qwen-Image',
              sha256: FAKE_SHA_2,
              licence_id: 'Apache-2.0',
              licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
              date_read: '2026-11-05',
            },
            steps: [250],
            checkpoint_sha256s: { 250: FAKE_SHA_3 },
            sample_grid_sha256s: { 250: 'bad' },
          }),
        /TRAIN_RUN_SHA_INVALID/
      );
      assert.throws(
        () =>
          buildTrainRunRecord({
            run_id: 'r1',
            window_id: 'w1',
            dataset_package_id: 'p1',
            dataset_manifest_sha256: FAKE_SHA_1,
            config_sha256: FAKE_SHA_2,
            base_model: {
              name: 'Qwen/Qwen-Image',
              sha256: FAKE_SHA_2,
              licence_id: 'Apache-2.0',
              licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
              date_read: '2026-11-05',
            },
            steps: [250],
            checkpoint_sha256s: { 250: FAKE_SHA_3 },
            eval_pack_sha: 'bad',
          }),
        /TRAIN_RUN_SHA_INVALID/
      );

      const record = buildTrainRunRecord({
        run_id: 'train_plsvessel_001',
        window_id: 'win_lane3_01',
        dataset_package_id: 'plsvessel_pkg_001',
        dataset_manifest_sha256: FAKE_SHA_1,
        config_sha256: FAKE_SHA_2,
        override_file: overrideMeta.override_file,
        override_sha256: overrideMeta.override_sha256,
        base_model: {
          name: 'Qwen/Qwen-Image',
          repo: 'Qwen/Qwen-Image',
          revision: 'main',
          sha256: FAKE_SHA_2,
          licence_id: 'Apache-2.0',
          licence_url: 'https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE',
          date_read: '2026-11-05',
        },
        steps: [250, 500],
        checkpoint_sha256s: {
          250: FAKE_SHA_3,
          500: FAKE_SHA_4,
        },
        sample_grid_sha256s: {
          250: FAKE_SHA_4,
          500: FAKE_SHA_3,
        },
      });

      const trainRunPath = join(tmp, 'train-run.json');
      writeTrainRunJson(trainRunPath, record);
      const loaded = readTrainRunJson(trainRunPath);
      assert.equal(loaded.run_id, 'train_plsvessel_001');
      assert.equal(loaded.dataset_package_id, 'plsvessel_pkg_001');
      assert.equal(loaded.eval_pack_sha, null);
      assert.equal(loaded.upstream_issue, 'https://github.com/ostris/ai-toolkit/issues/1087');

      // Attach eval_pack_sha after eval pack completes
      const withEval = attachEvalPackSha(trainRunPath, FAKE_SHA_1);
      assert.equal(withEval.eval_pack_sha, FAKE_SHA_1);
      assert.equal(readTrainRunJson(trainRunPath).eval_pack_sha, FAKE_SHA_1);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
