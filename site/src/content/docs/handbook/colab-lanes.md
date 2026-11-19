---
title: Colab Lanes
description: Opt-in launch kits that run a render or a LoRA training step on your own Google Colab account, under a spending cap, and stop their own session.
sidebar:
  order: 12
---

`sdlab` is local by default. The Colab lanes are the one opt-in exception: launch kits under `scripts/colab/` that run a render or a LoRA training step on your own Google Colab account. They are **experimental**. They have completed real render and training windows on a Colab GPU, but their flags and records can still change.

## What a lane does

A lane is one launcher script that you run from your own machine. It opens one Colab session, runs one job, brings the results back, and stops the session.

| Lane | Launcher | What it runs |
|---|---|---|
| Lane 1, render | `scripts/colab/launch_lane1_stub.sh` | Headless ComfyUI renders from a jobs file (`--render`), or a CPU rehearsal of the install and weights download (`--render-cpu-stub`) |
| Lane 3, training | `scripts/colab/launch_lane3_stub.sh` | A LoRA training run from a job file and a dataset manifest (`--train`) |

Every launcher:

1. **Checks its own inputs first.** It verifies the pinned sha256 of every script it uploads, including itself, and refuses to open a session if one differs.
2. **Runs under a spending cap.** It reads your live Colab balance and rate, and ends the run at the wall time, at the cap, or when the job stalls or dies. The cap reserves the time that cleanup needs.
3. **Uploads only the files you point it at.**
4. **Brings the results back and records the window.** `window.json` holds the card, the balances, the rate and the sha256 of every downloaded file. When a guard trips, a salvage step still tries to bring back what was produced.
5. **Stops its own session on every exit,** from an exit trap on your machine.

## Run the CPU rehearsal first

Each lane has a CPU rehearsal that installs the pinned environment and checks the downloads on a cheap CPU session. Run it at the commit you intend to use before any paid GPU window, and run the GPU window at that same commit.

## Pictures and licences

- The render lane accepts only weights whose licence is `Apache-2.0` or `MIT`, and refuses any other.
- Rendered pictures carry `licence: "CC-BY-4.0"` and `credit: "mcp-tool-shop"` in their provenance.
- `scripts/colab/lane1_jobs_from_canon.py` builds a jobs file from a canon folder at an exact git commit, so every picture traces back to the canon text that produced it.

## The phase file

Each lane's script on the Colab VM writes its phase (`setup`, `run` or `bundle`) to a small file, `phase.txt`, that the launcher reads.

- Writers replace the file in one step, so the launcher never reads a half-written file.
- If a write fails, the run stops with `PHASE_WRITE_FAILED` (exit `77`). It does not carry on with a stale phase.
- An empty read keeps the last known phase. A stuck job is still caught, because the stall clocks reset only when the phase word changes.

## Where the detail is

The full contract is in the repository: [`scripts/colab/README.md`](https://github.com/mcp-tool-shop-org/style-dataset-lab/blob/main/scripts/colab/README.md) covers the timeouts, the cleanup bounds, the guards and every refusal code. [`docs/colab-cli-contract.md`](https://github.com/mcp-tool-shop-org/style-dataset-lab/blob/main/docs/colab-cli-contract.md) records what the kits assume about the `colab` CLI.
