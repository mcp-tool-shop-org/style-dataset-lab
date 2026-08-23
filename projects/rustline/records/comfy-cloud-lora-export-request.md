# Comfy Cloud feature request — a way to get a trained LoRA off the box

> **Status:** drafted 2026-08-22, NOT yet sent. Channel: the Comfy Cloud beta feedback survey
> (the MCP's `submit_feedback` only returns that link — there is no agent/Q&A endpoint), or Comfy
> support. Everything asserted below was verified against the live node catalog via `get_node`
> (uncapped, not lean) and the Comfy Cloud docs.

---

## The brief (paste this)

**Subject: Trained LoRAs can be imported but not exported — one missing output node closes the loop**

We train house-style LoRAs on Qwen-Image and use them across a game art pipeline. We're on our
fifth version of one style: 195-image dataset, rank 16, 2000 steps, single-lever discipline where
only one variable changes per version so quality is attributable.

**What already works on Cloud, and works well:**

- Importing a custom LoRA from Hugging Face into the private Model Library (`.safetensors`,
  Creator tier, API key in Secrets for private repos). This is excellent — it means our own trained
  style can generate on Cloud.
- `MakeTrainingDataset` → `ResolutionBucket` → `TrainLoraNode` is a real training path, with rank,
  optimizer, `bf16`, LoRA/LoHa/LoKr/OFT, gradient checkpointing, and an `existing_lora` input for
  continuing from a previous adapter.

**The gap:** there is no way to get the trained weights back out.

- `TrainLoraNode` outputs `LORA_MODEL`, `LOSS_MAP`, `INT`. It has no filename or save input, and
  `output_node` is `false` — it writes nothing.
- The only node in the catalog that accepts `LORA_MODEL` is `LoraModelLoader`, which applies it to a
  `MODEL` for inference inside the same graph.
- The only `output_node: true` in `model/training` is `LossGraphNode` — and it saves a **loss plot
  image**.

So a LoRA trained on Cloud exists only for the duration of the job that created it. It can be used
once, in-graph, and then it is gone. That is fine for an experiment and unusable for a style you
intend to keep: every version has to be archived, A/B'd against its predecessors at matched seeds,
gated, and shipped to a downstream pipeline.

The asymmetry is the striking part — **you can bring a LoRA in from Hugging Face, but you cannot
push one out.** Closing that one gap would turn Cloud from "can train" into a complete training
venue, and would let people who train on Cloud keep what they make.

**Smallest fixes that would work, in our order of preference:**

1. **A `SaveLoRA` node** — `LORA_MODEL` + `filename_prefix` → writes a `.safetensors` to outputs,
   downloadable exactly like a `SaveImage` result. This mirrors the existing output pattern and is
   probably the least invasive change.
2. **An HF-push node** — `LORA_MODEL` + `repo_id` (+ optional path/revision), authenticating with
   the Hugging Face key **already stored in Secrets** for private model import. This reuses
   infrastructure that exists today and makes the round trip symmetric: import from HF, train,
   push back to HF.
3. **Land the result in the Model Library automatically** — a trained `LORA_MODEL` appears in the
   user's own private library, the same place imported models land. No new transport at all.

Any one of the three unblocks it. (1) is the simplest; (2) is the most useful, because it makes
Cloud a drop-in link in an existing HF-based pipeline.

Related, lower priority: intermediate checkpoints. Our local runs save every 250 steps and we pick
the ship checkpoint by looking at the progression, because the final step is frequently not the best
one. A `save_every` on `TrainLoraNode` — or simply being able to emit several `LORA_MODEL`s — would
matter once export exists.

---

## Notes for us, not for Comfy

**Why this is worth asking rather than routing around.** Comfy expands node support based on
demand, so this is a reasonable request rather than a wishlist item. If it lands, the whole
generate → jury → retrain flywheel runs on Cloud with no local GPU and no VRAM-watchdog dependency.

**Until then, the split is:** generation on Cloud (import v5 from HF), training on the rented
ai-toolkit box that produced v4 and v5 and hands back a real `.safetensors`.

**Prerequisite either way:** the HF import needs **Creator tier or above**. Below that, generation
stays local too.

**Verification trail** — all checked 2026-08-22, uncapped:

| Claim | How verified |
|---|---|
| `model/training` is exactly 4 nodes | `search_nodes(category="model/training")` → total 4 |
| `TrainLoraNode` has no save input, `output_node: false` | `get_node(["TrainLoraNode"])` full spec |
| `LoraModelLoader` is the only `LORA_MODEL` consumer | `search_nodes(input_type="LORA_MODEL")` → total 1 |
| `LossGraphNode` saves an image | `get_node` — `filename_prefix`, "saved loss graph image" |
| `existing_lora` holds no user models | 648 options, all Comfy-provided public LoRAs |
| No HF-upload node anywhere | `search_nodes(q="huggingface hub upload push repo")` — all results download-only |
| Import: HF/Civitai, safetensors, Creator tier, Secrets | https://docs.comfy.org/cloud/import-models |
| Custom Nodes Manager is local-only | https://support.comfy.org/articles/9321608144-installing-custom-nodes |
