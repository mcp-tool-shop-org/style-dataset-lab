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
# The transformer is still built in bf16 on the host before it is quantised; WSL on the rig is
# capped at 28 GB, and the sampler stops the run at MemAvailable < 2 GiB (HOST_RAM_CEILING).
# Estimate for the grant ask: about 24 GB VRAM peak (the example is sized for a 24 GB card);
# 25-45 min (install, load and uint3 quantisation, caching, 20 steps, one save, one 6-image grid);
# --wall-s 3600 is the cap to ask for.
# Usage: walk_b_quantised.sh --wheel-dir <dir> --hf-home <dir> --dataset-dir <dir> \
#          --evidence-root <dir> --wall-s <s> [--check | --install-only]
set -euo pipefail
# shellcheck source=scripts/colab/lane3/walk_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/walk_common.sh"
walk_main b "$@"
