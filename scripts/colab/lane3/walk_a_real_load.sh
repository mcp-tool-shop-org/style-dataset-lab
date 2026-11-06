#!/usr/bin/env bash
# Lane 3 GPU-rung walk (a), on the rig's RTX 5090 under a card grant: the REAL rung config
# (lane3/rung-qwen-image.yaml: Qwen/Qwen-Image bf16, quantize false, low_vram false) through the
# kit's own train-mode remote script, with the guards in place, from install through the model
# download step (the weights are already in the --hf-home cache) and the fixture dataset to
# ai-toolkit's model load, where it is EXPECTED to fail with a CUDA OOM: the bf16 transformer is
# 38.05 GiB and the card has 32 GB. At ai-toolkit beb94824 the transformer is built on the host and
# placed on cuda inside its own load (qwen_image.py:105 -> toolkit/models/v2/_mixin.py:450-451,
# `self.to(device)`, device cuda when low_vram is false), before the text encoder is even loaded
# and before any latent or text-embedding caching, so the OOM is expected there, in the
# "Loading transformer" phase; the text encoder and transformer are never co-resident on this card.
# What it measures: peak host RSS of the run's process tree while the transformer is built on the
# host (the number the request's --host-ram-required-gib comes from: peak + 20%), where in the log
# the peak happened, peak VRAM per phase, how far it got, and the exact OOM line.
# Host-RAM threshold: a 1 GiB placeholder for this walk only (it is the walk that measures it).
# WSL on the rig is capped at 28 GB (.wslconfig): if the host-side build needs more, the sampler
# stops the run at MemAvailable < 2 GiB (HOST_RAM_CEILING in the summary), which gives a lower
# bound, not the peak.
# Estimate for the grant ask: VRAM up to the whole card (32 GB, then OOM); 10-20 min (install from
# a warm uv cache, model load from E:); --wall-s 1800 is the cap to ask for.
# Usage: walk_a_real_load.sh --wheel-dir <dir> --hf-home <dir> --dataset-dir <dir> \
#          --evidence-root <dir> --wall-s <s> [--check | --install-only]
set -euo pipefail
# shellcheck source=scripts/colab/lane3/walk_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/walk_common.sh"
walk_main a "$@"
