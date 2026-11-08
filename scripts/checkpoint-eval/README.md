# `checkpoint-eval` — Paired Early-Checkpoint Metrics for Style LoRAs

`scripts/checkpoint-eval/checkpoint_eval.py` (also reachable via `sdlab checkpoint-eval`) scores seed-matched sample trajectories from style LoRA training runs to decide from early checkpoints (steps 250 and 500) whether a candidate run (**run B**) should be promoted to a full 2,000-step run against a reference trajectory (**run A**) and its step-0 base model samples.

---

## Privacy & Hardware Rules

1. **Private outputs never enter any git-tracked path.**
   - Sample images, training images, cached embeddings, `summary.json`, `summary-B-<name>.json`, and `corridors.md` from private project art must **never** be committed or copied under any git-tracked directory.
   - Local evaluation outputs go only to an untracked external path (for example `<private-out>/eval/`).
   - Repository commits contain code, documentation, and synthetic-fixture tests only.
2. **CPU or Intel OpenVINO only (`CUDA_VISIBLE_DEVICES=""`).**
   - `checkpoint_eval.py` sets `os.environ["CUDA_VISIBLE_DEVICES"] = ""` on import and refuses if CUDA is visible (`NVIDIA_GPU_FORBIDDEN`) or if an OpenVINO device is non-Intel (`OPENVINO_NO_INTEL_DEVICE`).

---

## Why Paired Per-Image Metrics Replace FID / KID at $n = 6\text{--}12$

Distributional metrics are unusable at 6–12 checkpoint sample images:
- **FID and KID fail at small $n$:** sample covariance has rank $\le n - 1$ against 2,048 Inception dimensions, with $O(1/N)$ finite-sample bias that depends on the generator (Chong & Forsyth 2020, arXiv:1911.07023; null spread $\pm 48.8$ FID and $\pm 0.040$ KID at $n = 6$).
- **CMMD** (Jayasumana et al. 2024, arXiv:2401.09603) still requires larger sample pools than a 6-prompt validation grid.
- **Raw CLIP-I and Gram matrices** are confounded by scene content and global tint.

Instead, `checkpoint-eval` pairs images by `(prompt_index, step)` across step 0 (base model before any LoRA update), reference run A, and candidate run B. Sample filenames must carry a 9-digit zero-padded step field (`<timestamp>__<step:09d>_<prompt_idx>.<ext>`). With `walk_seed: true` and fixed `seed`, each prompt index $i$ uses a fixed seed (`seed + i`), cancelling prompt variance across checkpoints and runs. Pooling step 250 and step 500 across 6 prompts gives $n = 12$ paired observations.

---

## Metrics & Known Failure Modes

| Metric | What it measures | Known failure modes & confounds |
|---|---|---|
| **CSD top-$k$ ($k=5$) mean cosine to training set** (`tomg-group-umd/CSD-ViT-L`, Somepalli et al. 2024, arXiv:2404.01292) | Primary **style-adoption** score: cosine similarity of the Contrastive Style Descriptors ViT-L/14 style projection to the 5 nearest training exemplars, plus paired gain $\Delta\text{CSD}(s) = \text{CSD}(s) - \text{CSD}(0)$ and velocity ratio $\rho = \Delta\text{CSD}_B(500) / \Delta\text{CSD}_A(500)$. | Can be inflated by direct training-set memorization or global colour/contrast shifts if read without DINOv2 leakage and human grid checks; early-step LoRA scale ($1.0$ vs $1.3\text{--}1.4$) can also understate learned direction. |
| **Content-only CLIP-T** (`openai/clip-vit-base-patch32`) | **Prompt-control guardrail:** image-text cosine similarity after stripping the style trigger phrase(s) from each prompt, plus paired change $\Delta\text{CLIP-T}(s) = \text{CLIP-T}(s) - \text{CLIP-T}(0)$. | Insensitive to fine-grained anatomical or stylistic artifacts; a steep drop ($\Delta\text{CLIP-T}$ falling more than $0.025$ below run A) signals that style pressure is overwriting prompt semantics. |
| **DINOv2 nearest-neighbour cosine to training set** (`facebook/dinov2-base`, Oquab et al. 2023, arXiv:2304.07193; CSGO pairing, Xing et al. 2024) | **Memorization & content-leakage guardrail:** 1-NN cosine similarity to the training set (tracked across all prompts and specifically on out-of-distribution trap prompts without trigger words), plus $\Delta\text{DINO-NN}(s)$ vs step 0. | In-domain prompts that share subject categories with the training set naturally raise DINOv2 similarity; out-of-distribution prompts (e.g. a plain object prompt) isolate subject/layout leakage. If $\Delta\text{DINO-NN}$ exceeds $+0.085$ above run A or exceeds $\Delta\text{CSD}$, the checkpoint is copying training content. |
| **DreamSim perceptual distance** (`ssundaram21/dreamsim` `open_clip_vitb32` v0.2.1, Fu et al. 2023, arXiv:2306.09344) | **Trajectory parity & perceptual drift:** cosine distance $1 - \cos(e_x, e_y)$ between seed-matched images of run B and run A at the same step, and between step $s$ and step 0 within a run. | Captures mid-level layout/pose/colour shifts jointly; high $\text{DreamSim}(B, A) > 0.25$ is only a kill signal when accompanied by lower CSD style adoption (otherwise B may have taken a valid alternative composition path). |
| **LoRA weight-space stable rank & alignment** (CPU read of `.safetensors`) | For each LoRA layer $\Delta W = (\alpha / r) B \cdot A$ (or unscaled $B \cdot A$ when no `.alpha` tensor is stored in `.safetensors`): singular values $\sigma_1 \ge \dots \ge \sigma_r$, **stable rank** $\|\Delta W\|_F^2 / \|\Delta W\|_2^2$, top singular value $\sigma_1$, Frobenius norm $\|\Delta W\|_F$, and (across two checkpoints) layer-wise norm ratio and flattened update cosine. | A collapse of stable rank below $\sim 2.0$ paired with a surging $\sigma_1$ warns of rank-1 colour tint or memorization spike. Weight norms alone cannot replace pixel-level CSD/CLIP-T/DINOv2 checks because layer sensitivity varies across blocks. |

---

## Statistical & Weight-Space Limits

1. **Pooled $n = 12$ is 6 prompts × 2 steps, not 12 independent observations.**
   - Pooling step 250 and step 500 across the same 6 prompt seeds repeats each prompt trajectory twice. Because step 250 and step 500 from the same prompt and seed are positively correlated within-prompt pairs rather than independent draws, treating the pooled $t$-test as $\text{df} = 11$ overstates the statistical evidence. Read the per-step ($n = 6$, $\text{df} = 5$) tests alongside the pooled summary.
2. **The MDE's SD is run A's step-to-step SD, not a $B - A$ SD.**
   - Before any run B exists, the minimum detectable effect (MDE) reported in run A's `summary.json` and `corridors.md` uses run A's across-prompt step-to-step $\Delta\text{CSD}$ standard deviation (`mean_sd_of_step_to_step_delta_csd_across_prompts_in_run_A`) as a proxy, not a measured between-run $B - A$ paired-difference SD. Once run B is scored, `b_vs_a.measured_per_step_paired_diff_sd` records the actual $B - A$ SD.
3. **Top singular value and Frobenius norm scaling when `.safetensors` carry no `.alpha` tensors.**
   - When a checkpoint `.safetensors` file includes per-layer `<layer>.alpha` (or `<layer>.lora_alpha`) tensors, `read_safetensors_weight_space` scales $\Delta W = (\alpha / \text{rank}) B \cdot A$ and records `alpha` and `scale = alpha / rank`. When `.safetensors` carry no `.alpha` tensors (as in standard `ai-toolkit` exports where `linear_alpha` lives only in `config.yaml`), top singular value ($\sigma_1$) and Frobenius norm ($\|\Delta W\|_F$) are reported on the unscaled product $B \cdot A$ (`alpha: null`, `scale: 1.0`). Stable rank $\|\Delta W\|_F^2 / \|\Delta W\|_2^2$ and cosine alignment are scale-invariant in both cases.
4. **Wilcoxon signed-rank exact enumeration vs normal approximation.**
   - The Wilcoxon signed-rank test uses exact $2^n$ sign-flip enumeration (with mid-ranks for ties) for $n \le 20$ non-zero paired differences (`method: "exact"`) and switches to the tie-corrected normal approximation above $n = 20$ (`method: "normal_approx"`), reporting `p_greater`, `p_less`, and `p_two_sided`.

---

## Model Licences & Attribution (Verified at Source Before Download)

All model licences were read at their upstream source prior to downloading or running weights:

| Model | Role | Licence | Source URL | Date Read |
|---|---|---|---|---|
| `tomg-group-umd/CSD-ViT-L` (`learn2phoenix/CSD`) | CSD ViT-L/14 style descriptor | **CC-BY-4.0** (weights) / **MIT** (code & OpenAI CLIP ViT-L/14 architecture) | `https://huggingface.co/tomg-group-umd/CSD-ViT-L/raw/main/README.md` ; `https://raw.githubusercontent.com/learn2phoenix/CSD/main/LICENSE` | 2026-11-07 |
| `openai/clip-vit-base-patch32` | Content-only CLIP-T (trigger words stripped) | **MIT** | `https://raw.githubusercontent.com/openai/CLIP/main/LICENSE` ; `https://huggingface.co/openai/clip-vit-base-patch32/raw/main/README.md` | 2026-11-07 |
| `facebook/dinov2-base` (`facebookresearch/dinov2`) | DINOv2 1-NN memorization & leakage guard | **Apache-2.0** | `https://raw.githubusercontent.com/facebookresearch/dinov2/main/LICENSE` ; `https://huggingface.co/facebook/dinov2-base/raw/main/README.md` | 2026-11-07 |
| `ssundaram21/dreamsim` (`open_clip_vitb32`, `v0.2.1`) | DreamSim perceptual distance | **MIT** (DreamSim & OpenCLIP ViT-B/32) / **Apache-2.0** (DINO backbone) | `https://raw.githubusercontent.com/ssundaram21/dreamsim/main/LICENSE` ; `https://raw.githubusercontent.com/mlfoundations/open_clip/main/LICENSE` | 2026-11-07 |

### CC-BY-4.0 Attribution — Contrastive Style Descriptors (CSD)

> **CSD-ViT-L weights attribution:** Gowthami Somepalli, Anubhav Gupta, Kamal Gupta, Shramay Palta, Micah Goldblum, Jonas Geiping, Abhinav Shrivastava, and Tom Goldstein, *"Measuring Style Similarity in Diffusion Models"*, 2024 ([arXiv:2404.01292](https://arxiv.org/abs/2404.01292), weights at [tomg-group-umd/CSD-ViT-L](https://huggingface.co/tomg-group-umd/CSD-ViT-L), code at [learn2phoenix/CSD](https://github.com/learn2phoenix/CSD)), licensed under [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/).

---

## Pre-Registered Corridors Lock (`corridors.md`) & Fail-Closed Refusals

1. **No overwrite (`CORRIDORS_EXISTS`):**
   - Running `checkpoint-eval` for run A writes `<out>/corridors.md` (or `--corridors <path>`). If the target corridors file already exists, `checkpoint-eval` refuses (`CORRIDORS_EXISTS`) with no force flag; a new run A or re-seal must write a new file name.
2. **External SHA-256 lock (`--corridors-sha` / `CORRIDORS_SHA_MISMATCH`):**
   - Run A records the full file SHA-256 of the corridors file outside the file in run A's `summary.json` (`corridors.file_sha256`).
   - When scoring a candidate run B, `--corridors-sha <hex>` is **required** and verified against the corridors file on disk before any scoring happens (`CORRIDORS_SHA_MISMATCH` on missing or mismatched digest).
   - The in-file `body_sha256` field is kept only as a naive-edit check and **is not the lock** (anyone with the script could otherwise edit a band and re-run the body hash function; `read_and_verify_corridors` also re-derives the decision bands from `run_a_anchors` and enforces the external `--corridors-sha`).
3. **Run A sample-set binding (`run_a_fingerprint` / `RUN_A_FINGERPRINT_MISMATCH`):**
   - `corridors.md` embeds `run_a_fingerprint`, the SHA-256 over run A's sorted sample filenames and per-file SHA-256 digests. When scoring run B, `checkpoint-eval` re-fingerprints `--run A=<dir>` and refuses (`RUN_A_FINGERPRINT_MISMATCH`) if run A's sample directory was swapped or altered.
4. **Run B must bring its own config (`RUN_B_CONFIG_MISSING`):**
   - Scoring run B requires either `--prompts-b <path>` or a `config.yaml` / `config.yml` / `config.json` alongside run B's sample directory (or its parent). `checkpoint-eval` never falls back to run A's config and refuses (`RUN_B_CONFIG_MISSING` or `SEED_MISMATCH` / `PROMPT_MISMATCH`) before scoring.
5. **Fail closed on missing steps or metrics (`STEP_MISSING` / `METRIC_MISSING`):**
   - Missing required steps (`0`, `250`, `500`) or any missing/non-finite metric refuses immediately with `STEP_MISSING` or `METRIC_MISSING` naming the step and metric.
   - Scoring run B writes its output to `<out>/summary-B-<name>.json` and never overwrites run A's `summary.json`.

---

## Usage

```bash
# 1. Evaluate reference run A (steps 0..2000), cache training embeddings, read LoRA checkpoints, and seal corridors.md:
python scripts/checkpoint-eval/checkpoint_eval.py \
  --training-dir <training-dir> \
  --run A=<samples-dir>/run-A/samples \
  --steps 0,250,500,750,1000,1250,1500,1750,2000 \
  --prompts <samples-dir>/run-A/config.yaml \
  --checkpoint <samples-dir>/run-A/lora_000001750.safetensors \
  --checkpoint <samples-dir>/run-A/lora_final.safetensors \
  --out <private-out>/run-A \
  --device openvino

# 2. Score a candidate run B at steps 0, 250, 500 against the locked corridors.md (writes summary-B-<name>.json):
python scripts/checkpoint-eval/checkpoint_eval.py \
  --training-dir <training-dir> \
  --run A=<samples-dir>/run-A/samples \
  --run B=<samples-dir>/run-B/samples \
  --steps 0,250,500 \
  --prompts <samples-dir>/run-A/config.yaml \
  --prompts-b <samples-dir>/run-B/config.yaml \
  --corridors <private-out>/run-A/corridors.md \
  --corridors-sha <64-hex-file-sha256-from-run-A-summary.json> \
  --out <private-out>/run-A \
  --device openvino
```
