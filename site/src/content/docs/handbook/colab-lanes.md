---
title: Colab Lanes
description: Opt-in launch manifests that run a render or a LoRA training window on Google Colab through colab-runner, under a spend cap and wall bound, and stop their own session.
sidebar:
  order: 12
---

`sdlab` is local by default. The Colab lanes under `scripts/colab/` are opt-in manifests launched via [`colab-runner`](https://github.com/mcp-tool-shop-org/colab-runner).

## What a lane runs

Each lane ships a declarative `colab-window.toml` spec and a VM script (`vm_job.sh`):

| Lane | Manifest | What it runs |
|---|---|---|
| Lane 1, render | `scripts/colab/lane1/colab-window.toml` | Headless ComfyUI renders (`LANE1_MODE=render`), CPU rehearsal (`LANE1_MODE=render_cpu_stub`), or CPU stub (`LANE1_MODE=stub`) via `scripts/colab/lane1/vm_job.sh` |
| Lane 3, training | `scripts/colab/lane3/colab-window.toml` | Pinned `uv`/wheel install stub (`LANE3_MODE=install`) or LoRA training run (`LANE3_MODE=train`) via `scripts/colab/lane3/vm_job.sh` |

`colab-runner` checks spec fields and staged input hashes upfront, enforces card/shape and open-time rate limits, stops running windows only on spend cap, wall limit, or dead/stalled jobs, collects outputs through chunked `.tar.partNNNN` downloads into `collected/` or `salvage/`, confirms session teardown, and writes `outcome.json`. Uploading results to Hugging Face stays outside the runner (`hf upload`).

## Where the detail is

See [`scripts/colab/README.md`](https://github.com/mcp-tool-shop-org/style-dataset-lab/blob/main/scripts/colab/README.md) for retained helper scripts and [`docs/colab-locks.md`](https://github.com/mcp-tool-shop-org/style-dataset-lab/blob/main/docs/colab-locks.md) for pinned lock maintenance.
