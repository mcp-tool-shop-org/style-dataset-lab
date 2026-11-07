#!/usr/bin/env node

/**
 * checkpoint-eval.js — Paired early-checkpoint evaluation for style LoRAs.
 *
 * Thin CLI wrapper around scripts/checkpoint-eval/checkpoint_eval.py.
 * Enforces CUDA_VISIBLE_DEVICES="" in every spawned process.
 */

import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { getPackageRoot } from '../lib/paths.js';
import { findPython } from '../lib/measure.js';
import { handleCliError, runtimeError } from '../lib/errors.js';

const SCRIPT_PATH = join(getPackageRoot(), 'scripts', 'checkpoint-eval', 'checkpoint_eval.py');

export const USAGE = `sdlab checkpoint-eval --training-dir <dir> --run A=<dir> [--run B=<dir>] --prompts <config.yaml|json> --out <dir> [options]

Score seed-matched early-checkpoint sample trajectories (CSD top-k, content-only CLIP-T,
DINOv2 nearest-neighbour, DreamSim distance, and LoRA weight-space stable rank) on CPU
or Intel OpenVINO.

Flags:
  --training-dir <dir>        Training images directory (embedded once and cached under --out)
  --run NAME=DIR              Run sample directory (e.g. --run A=<dir> [--run B=<dir>])
  --steps <s1,s2,...>         Comma-separated checkpoint steps (e.g. 0,250,500,...)
  --prompts <path>            Trainer config.yaml or JSON with sample prompts and seed
  --prompts-b <path>          Optional separate config for run B
  --out <dir>                 Output directory (must be outside git-tracked paths for private data)
  --device <cpu|openvino>     Compute device (default: cpu; CUDA_VISIBLE_DEVICES="" always enforced)
  --checkpoint <path>         Optional LoRA .safetensors checkpoint(s) for weight-space stable rank
  --corridors <path>          Optional explicit path to corridors.md (defaults to <out>/corridors.md)
  --fake-embedder             Use deterministic synthetic embedder (for synthetic fixture tests)`;

export async function run(argv = process.argv.slice(2)) {
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(USAGE);
    return;
  }

  const py = findPython();
  if (!py) {
    throw runtimeError('PYTHON_NOT_FOUND', 'No working Python interpreter found (set SDLAB_PYTHON or put python on PATH).');
  }

  const env = { ...process.env, CUDA_VISIBLE_DEVICES: '' };
  const res = spawnSync(py, [SCRIPT_PATH, ...argv], {
    stdio: 'inherit',
    env,
  });

  if (res.status !== 0) {
    process.exitCode = res.status || 2;
  }
}

if (process.argv[1] && (process.argv[1].endsWith('checkpoint-eval.js') || process.argv[1].endsWith('checkpoint-eval'))) {
  run().catch(handleCliError);
}
