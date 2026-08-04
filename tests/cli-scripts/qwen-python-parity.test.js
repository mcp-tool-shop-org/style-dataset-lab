/**
 * Cross-language pinning parity: scripts/qwen_generate.py claims to emit a
 * byte-identical comfy_workflow_sha to the JS path (lib/adapters/comfyui-workflows.js
 * buildQwenGraph + lib/run-manifest.js comfyWorkflowSha) for the same wave. Three
 * bugs broke that claim (SDL-H11, SDL-H3, SDL-H4):
 *
 *   H11 — sampler/scheduler/shift were hardcoded in qwen_graph() and never read
 *         from the wave, so a non-default wave produced a different graph (and a
 *         confidently-wrong receipt) than the JS side.
 *   H3  — Python's _js_number() delegated to repr(), which disagrees with JS
 *         Number::toString in the [1e-6, 1e-4) magnitude band and on exponent
 *         zero-padding, so a float in that band hashed differently.
 *   H4  — dict.get("weight", 1.0) only substitutes on a MISSING key, never on an
 *         explicit JSON null, so {"weight": null} produced a Python None where JS
 *         `l.weight ?? 1.0` produces 1 — splitting both the hash and the literal
 *         strength_model submitted to ComfyUI.
 *
 * This test drives the REAL CLI script end-to-end (spawns `python
 * scripts/qwen_generate.py`) with a wave crafted to hit all three at once — a
 * non-default sampler/scheduler/shift, a LoRA with an explicit null weight, and a
 * second LoRA with a weight in the H3-divergent float band — then asserts its
 * emitted comfy_workflow_sha equals the hash the JS path computes for the
 * equivalent graph. A wave with `subjects: []` makes main() run the full
 * pinning computation and write generation.json without ever contacting
 * ComfyUI (the per-subject loop is simply empty), so no running ComfyUI
 * instance or GPU is required.
 *
 * `npm test` runs Node only — Python is a runtime dependency of this ONE
 * bridge script, not of the package. Skip gracefully (not fail) when `python`
 * is unavailable so CI on a Python-less runner stays green.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildQwenGraph } from '../../lib/adapters/comfyui-workflows.js';
import { comfyWorkflowSha } from '../../lib/run-manifest.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..', '..');
const QWEN_SCRIPT = join(REPO_ROOT, 'scripts', 'qwen_generate.py');

function findPython() {
  for (const cmd of ['python', 'python3']) {
    const res = spawnSync(cmd, ['--version'], { encoding: 'utf-8' });
    if (res.status === 0) return cmd;
  }
  return null;
}

const PYTHON = findPython();

// A wave engineered to exercise all three findings in one pass:
//   - sampler/scheduler/shift all non-default (H11)
//   - lora_detail weight is explicit JSON null (H4)
//   - lora_style weight (5e-5) sits in the H3-divergent [1e-6, 1e-4) band
const WAVE = {
  wave: 'parity-check',
  style_prefix: 'test style prefix',
  defaults: {
    negative: 'blurry, low quality',
    width: 832,
    height: 1216,
    steps: 28,
    cfg: 4.0,
    base_seed: 12345,
    sampler: 'dpmpp_2m',
    scheduler: 'karras',
    shift: 5.0,
    loras: [
      { name: 'lora_style.safetensors', weight: 0.00005 },
      { name: 'lora_detail.safetensors', weight: null },
    ],
  },
  subjects: [], // empty on purpose — see module docstring above
};

function runPythonPinning() {
  const dir = mkdtempSync(join(tmpdir(), 'sdlab-qwen-parity-'));
  try {
    const wavePath = join(dir, 'wave.json');
    const outDir = join(dir, 'out');
    writeFileSync(wavePath, JSON.stringify(WAVE, null, 2));

    const res = spawnSync(PYTHON, [QWEN_SCRIPT, '--wave', wavePath, '--out', outDir], {
      encoding: 'utf-8',
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        // Point the (unused, since --hash-models is not passed) model-hash
        // lookup at somewhere harmless instead of the real rig path, so this
        // test does not implicitly depend on E:/AI-Models existing.
        SDLAB_MODELS_DIR: dir,
      },
    });
    assert.equal(res.status, 0, `qwen_generate.py exited ${res.status}\nstdout: ${res.stdout}\nstderr: ${res.stderr}`);

    const receipt = JSON.parse(readFileSync(join(outDir, 'generation.json'), 'utf-8'));
    return receipt;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function jsGraphForWave() {
  const d = WAVE.defaults;
  // Mirrors main()'s pin_graph = qwen_graph(prefix or "x", neg, base_seed, w, h,
  // steps, cfg, "sdl", loras=loras, sampler=..., scheduler=..., shift=...) —
  // prompt/negative/seed/filename_prefix are normalized out of the hash, so
  // only the structural fields below need to match.
  return buildQwenGraph({
    prompt: WAVE.style_prefix,
    negativePrompt: d.negative,
    seed: d.base_seed,
    width: d.width,
    height: d.height,
    steps: d.steps,
    cfg: d.cfg,
    sampler: d.sampler,
    scheduler: d.scheduler,
    shift: d.shift,
    loras: d.loras,
    filenamePrefix: 'sdl',
  }).nodes;
}

test('qwen_generate.py comfy_workflow_sha matches the JS buildQwenGraph hash for a non-default sampler/scheduler/shift + null-weight + divergent-float-weight wave (SDL-H11/H3/H4)', { skip: PYTHON ? false : 'python not found on PATH — skipping cross-language parity check' }, () => {
  const receipt = runPythonPinning();
  const pyHash = receipt?.pinning?.comfy_workflow_sha;
  assert.ok(pyHash && pyHash.startsWith('sha256:'), `expected a sha256: hash, got ${JSON.stringify(pyHash)}`);

  const jsHash = comfyWorkflowSha(jsGraphForWave());
  assert.equal(pyHash, jsHash, 'Python and JS produced different comfy_workflow_sha for the same wave — pinning contract is broken');
});

test('qwen_generate.py receipt records the WAVE\'s sampler/scheduler/shift, not hardcoded euler/simple/3.1 (SDL-H11)', { skip: PYTHON ? false : 'python not found on PATH — skipping' }, () => {
  const receipt = runPythonPinning();
  assert.equal(receipt.sampler, 'dpmpp_2m');
  assert.equal(receipt.scheduler, 'karras');
  assert.equal(receipt.shift, 5.0);
});

test('qwen_generate.py resolves an explicit null LoRA weight to 1.0, mirroring JS `l.weight ?? 1.0` (SDL-H4)', { skip: PYTHON ? false : 'python not found on PATH — skipping' }, () => {
  const receipt = runPythonPinning();
  const detail = receipt.pinning.loras.find((l) => l.name === 'lora_detail.safetensors');
  assert.ok(detail, 'expected lora_detail.safetensors in pinning.loras');
  assert.equal(detail.weight, 1, `null weight should default to 1.0, got ${JSON.stringify(detail.weight)}`);

  // The OTHER lora's explicit weight (not null) must pass through unchanged —
  // guards against a fix that defaults everything instead of only nullish.
  const style = receipt.pinning.loras.find((l) => l.name === 'lora_style.safetensors');
  assert.ok(style, 'expected lora_style.safetensors in pinning.loras');
  assert.equal(style.weight, 0.00005);
});
