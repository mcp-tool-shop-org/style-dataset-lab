#!/usr/bin/env bash
# Lane 3 GPU-rung walk (b), on the rig's RTX 5090 under a card grant: a quantised stand-in of the
# rung config, so the steps a 32 GB card cannot reach with the real config run end to end: the
# train step, the step-20 checkpoint save, the sample grid (one, at step 20) and the kit's copy-off
# and manifest path. The stand-in is ai-toolkit's documented Qwen-Image quantisation at beb94824
# (config/examples/train_lora_qwen_image_24gb.yaml): quantize true with qtype
# "uint3|<accuracy recovery adapter>" (ostris/accuracy_recovery_adapters
# qwen_image_torchao_uint3.safetensors at daf7bdfa..., pre-downloaded into --hf-home, since the run
# is offline), quantize_te true with qtype_te qfloat8, and low_vram true; every other value is the
# rung's (steps/save/sample 20, skip_first_sample, rank 16, adamw8bit, buckets 512/768/1024, the
# six prompts at 1024^2, 25 steps, guidance 3). It is not the rung config: what only the paid rung
# proves is listed in scripts/colab/REAL_SERVICE_ASSUMPTIONS.md.
# HOST RAM (read at ai-toolkit beb94824): this walk is NOT expected to fit the rig's WSL (28 GB).
# The quantised path still builds the whole bf16 transformer on the host first: the model's .load()
# calls load_model(..., quantize_on_load=False) (toolkit/models/v2/_mixin.py:265), which runs
# diffusers' from_pretrained (:549; safetensors.torch.load_file to cpu, diffusers
# models/model_loading_utils.py:177), and only then aitk_post_load (:268) quantises it, moving one
# block at a time to the GPU for the math (:484, :928). No call site passes quantize_on_load=True,
# and that path also quantises after the full load (:555). The only load that skips the bf16 host
# copy is a pre-quantized Comfy-Org checkpoint (:358, qwen_image.py:15-25): unpinned third-party
# weights, not in the cache, not used here. Projected host peak: at least the 38.05 GiB bf16
# transformer (the sampler stops the run at MemAvailable < 2 GiB, HOST_RAM_CEILING).
# Estimate for a grant ask, if it is run at all: about 24 GB VRAM peak (the example is sized for a
# 24 GB card); 25-45 min; --wall-s 3600.
# Sandbox: as walk (a): no network, HF cache read-only, HF_HUB_OFFLINE=1, `timeout --kill-after`
# wall, a 28 GiB VRAM bound above the idle baseline, killed by PID.
# Usage (in order): --check, --prepare (network on, no GPU), then the GPU run (no mode flag):
#   walk_b_quantised.sh --wheel-dir <dir> --hf-home <dir> --dataset-dir <dir> \
#     --evidence-root /mnt/e/<dir> --wall-s <s> [--check | --prepare | --offline-install-check]
set -euo pipefail
# shellcheck source=scripts/colab/lane3/walk_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/walk_common.sh"
walk_main b "$@"
