# `checkpoint-eval` — Paired Early-Checkpoint Metrics for Style LoRAs

`scripts/checkpoint-eval/checkpoint_eval.py` (also reachable via `sdlab checkpoint-eval`) scores seed-matched sample trajectories from style LoRA training runs to decide from early checkpoints (steps 250 and 500) whether a candidate run (**run B**) should be promoted to a full 2,000-step run against a reference trajectory (**run A**) and its step-0 base model samples.

---

## Privacy & Hardware Rules

1. **Private outputs never enter any git-tracked path.**
   - Sample images, training images, cached embeddings, `summary.json`, and `corridors.md` from private project art must **never** be committed or copied under any git-tracked directory.
   - Local evaluation outputs go only to an untracked external path (for example `E:/AI/rnd-local/projects/sdlab-colab/eval/`).
   - Repository commits contain code, documentation, and synthetic-fixture tests only.
2. **CPU or Intel OpenVINO only (`CUDA_VISIBLE_DEVICES=""`).**
   - `checkpoint_eval.py` sets `os.environ["CUDA_VISIBLE_DEVICES"] = ""` on import and refuses if CUDA is visible (`NVIDIA_GPU_FORBIDDEN`) or if an OpenVINO device is non-Intel (`OPENVINO_NO_INTEL_DEVICE`).

---

## Why Paired Per-Image Metrics Replace FID / KID at $n = 6\text{--}12$

Distributional metrics are unusable at 6–12 checkpoint sample images:
- **FID and KID fail at small $n$:** sample covariance has rank $\le n - 1$ against 2,048 Inception dimensions, with $O(1/N)$ finite-sample bias that depends on the generator (Chong & Forsyth 2020, arXiv:1911.07023; null spread $\pm 48.8$ FID and $\pm 0.040$ KID at $n = 6$).
- **CMMD** (Jayasumana et al. 2024, arXiv:2401.09603) still requires larger sample pools than a 6-prompt validation grid.
- **Raw CLIP-I and Gram matrices** are confounded by scene content and global tint.

Instead, `checkpoint-eval` pairs images by `(prompt_index, step)` across step 0 (base model before any LoRA update), reference run A, and candidate run B. With `walk_seed: true` and fixed `seed`, each prompt index $i$ uses a fixed seed (`seed + i`), cancelling prompt variance across checkpoints and runs. Pooling step 250 and step 500 across 6 prompts gives $n = 12$ paired observations.

---

## Metrics & Known Failure Modes

| Metric | What it measures | Known failure modes & confounds |
|---|---|---|
| **CSD top-$k$ ($k=5$) mean cosine to training set** (`tomg-group-umd/CSD-ViT-L`, Somepalli et al. 2024, arXiv:2404.01292) | Primary **style-adoption** score: cosine similarity of the Contrastive Style Descriptors ViT-L/14 style projection to the 5 nearest training exemplars, plus paired gain $\Delta\text{CSD}(s) = \text{CSD}(s) - \text{CSD}(0)$ and velocity ratio $\rho = \Delta\text{CSD}_B(500) / \Delta\text{CSD}_A(500)$. | Can be inflated by direct training-set memorization or global colour/contrast shifts if read without DINOv2 leakage and human grid checks; early-step LoRA scale ($1.0$ vs $1.3\text{--}1.4$) can also understate learned direction. |
| **Content-only CLIP-T** (`openai/clip-vit-base-patch32`) | **Prompt-control guardrail:** image-text cosine similarity after stripping the style trigger phrase(s) from each prompt, plus paired change $\Delta\text{CLIP-T}(s) = \text{CLIP-T}(s) - \text{CLIP-T}(0)$. | Insensitive to fine-grained anatomical or stylistic artifacts; a steep drop ($\Delta\text{CLIP-T}$ falling more than $0.025$ below run A) signals that style pressure is overwriting prompt semantics. |
| **DINOv2 nearest-neighbour cosine to training set** (`facebook/dinov2-base`, Oquab et al. 2023, arXiv:2304.07193; CSGO pairing, Xing et al. 2024) | **Memorization & content-leakage guardrail:** 1-NN cosine similarity to the training set (tracked across all prompts and specifically on out-of-distribution trap prompts without trigger words), plus $\Delta\text{DINO-NN}(s)$ vs step 0. | In-domain prompts that share subject categories with the training set naturally raise DINOv2 similarity; out-of-distribution prompts (e.g. a plain object prompt) isolate subject/layout leakage. If $\Delta\text{DINO-NN}$ exceeds $+0.085$ above run A or exceeds $\Delta\text{CSD}$, the checkpoint is copying training content. |
| **DreamSim perceptual distance** (`ssundaram21/dreamsim` `open_clip_vitb32` v0.2.1, Fu et al. 2023, arXiv:2306.09344) | **Trajectory parity & perceptual drift:** cosine distance $1 - \cos(e_x, e_y)$ between seed-matched images of run B and run A at the same step, and between step $s$ and step 0 within a run. | Captures mid-level layout/pose/colour shifts jointly; high $\text{DreamSim}(B, A) > 0.25$ is only a kill signal when accompanied by lower CSD style adoption (otherwise B may have taken a valid alternative composition path). |
| **LoRA weight-space stable rank & alignment** (CPU read of `.safetensors`) | For each LoRA layer $\Delta W = B \cdot A$ (rank 16): singular values $\sigma_1 \ge \dots \ge \sigma_r$, **stable rank** $\|\Delta W\|_F^2 / \|\Delta W\|_2^2$, top singular value $\sigma_1$, Frobenius norm $\|\Delta W\|_F$, and (across two checkpoints) layer-wise norm ratio and flattened update cosine. | A collapse of stable rank below $\sim 2.0$ paired with a surging $\sigma_1$ warns of rank-1 colour tint or memorization spike. Weight norms alone cannot replace pixel-level CSD/CLIP-T/DINOv2 checks because layer sensitivity varies across blocks. |

---

## Model Licences (Verified at Source Before Download)

All model licences were read at their upstream source prior to downloading or running weights:

| Model | Role | Licence | Source URL | Date Read |
|---|---|---|---|---|
| `tomg-group-umd/CSD-ViT-L` (`learn2phoenix/CSD`) | CSD ViT-L/14 style descriptor | **CC-BY-4.0** (weights) / **MIT** (code & OpenAI CLIP ViT-L/14 architecture) | `https://huggingface.co/tomg-group-umd/CSD-ViT-L/raw/main/README.md` ; `https://raw.githubusercontent.com/learn2phoenix/CSD/main/LICENSE` | 2026-11-07 |
| `openai/clip-vit-base-patch32` | Content-only CLIP-T (trigger words stripped) | **MIT** | `https://raw.githubusercontent.com/openai/CLIP/main/LICENSE` ; `https://huggingface.co/openai/clip-vit-base-patch32/raw/main/README.md` | 2026-11-07 |
| `facebook/dinov2-base` (`facebookresearch/dinov2`) | DINOv2 1-NN memorization & leakage guard | **Apache-2.0** | `https://raw.githubusercontent.com/facebookresearch/dinov2/main/LICENSE` ; `https://huggingface.co/facebook/dinov2-base/raw/main/README.md` | 2026-11-07 |
| `ssundaram21/dreamsim` (`open_clip_vitb32`, `v0.2.1`) | DreamSim perceptual distance | **MIT** (DreamSim & OpenCLIP ViT-B/32) / **Apache-2.0** (DINO backbone) | `https://raw.githubusercontent.com/ssundaram21/dreamsim/main/LICENSE` ; `https://raw.githubusercontent.com/mlfoundations/open_clip/main/LICENSE` | 2026-11-07 |

---

## Pre-Registered Corridors (`corridors.md`) & Tamper Refusal

1. **Before any run B exists**, running `checkpoint-eval` on `--run A=<samples_dir>` writes `<out>/corridors.md` anchored to run A's measured step-250 and step-500 values, sample size ($n = 6$ per step, $n = 12$ pooled across steps 250 and 500), and measured per-step paired-difference SD estimate.
2. `corridors.md` records its UTC `created_at` timestamp and its self-verifying `body_sha256` digest.
3. **When `--run B=<samples_dir>` is scored later**, `checkpoint-eval` reads `corridors.md` first and recomputes its digest. If any byte in `corridors.md` was modified after creation, the tool refuses with exit code 2:
   ```text
   REFUSED: CORRIDORS_TAMPERED: corridors.md was modified after creation ...
   ```

---

## Usage

```bash
# 1. Evaluate reference run A (steps 0..2000), cache training embeddings, read LoRA checkpoints, and lock corridors.md:
python scripts/checkpoint-eval/checkpoint_eval.py \
  --training-dir E:/AI/training/dataset_rustline_v5 \
  --run A=E:/AI/training/rustline_v5_ckpts/samples \
  --steps 0,250,500,750,1000,1250,1500,1750,2000 \
  --prompts E:/AI/training/rustline_v5_ckpts/config.yaml \
  --checkpoint E:/AI/training/rustline_v5_ckpts/rustline_style_v5_000001750.safetensors \
  --checkpoint E:/AI/training/rustline_v5_ckpts/rustline_style_v5.safetensors \
  --out E:/AI/rnd-local/projects/sdlab-colab/eval/run-A-v5 \
  --device openvino

# 2. Score a candidate run B at steps 0, 250, 500 against the locked corridors.md:
python scripts/checkpoint-eval/checkpoint_eval.py \
  --training-dir E:/AI/training/dataset_rustline_v5 \
  --run A=E:/AI/training/rustline_v5_ckpts/samples \
  --run B=E:/AI/rnd-local/projects/sdlab-colab/eval/run-B-samples \
  --steps 0,250,500 \
  --prompts E:/AI/training/rustline_v5_ckpts/config.yaml \
  --corridors E:/AI/rnd-local/projects/sdlab-colab/eval/run-A-v5/corridors.md \
  --out E:/AI/rnd-local/projects/sdlab-colab/eval/run-B-score \
  --device openvino
```
