# Colab Launch Kits (`scripts/colab/`)

Lane 1 (render) and Lane 3 (training) launch through [`colab-runner`](https://github.com/mcp-tool-shop-org/colab-runner) from declarative window manifests (`colab-window.toml`) plus VM job entrypoints (`vm_job.sh`):

| Lane | Manifest & Script | Entrypoint |
|---|---|---|
| Lane 1 (render) | `scripts/colab/lane1/colab-window.toml` + `scripts/colab/lane1/vm_job.sh` | `python -m colab_runner launch --spec scripts/colab/lane1/colab-window.toml --cap C --max-rate R --out-dir D` |
| Lane 3 (train) | `scripts/colab/lane3/colab-window.toml` + `scripts/colab/lane3/vm_job.sh` | `python -m colab_runner launch --spec scripts/colab/lane3/colab-window.toml --cap C --max-rate R --out-dir D` |

`colab-runner` owns session opening under a cross-process lock, pool-ceiling and card/shape checks, pre/post-open rate attribution, spend/wall/dead-job guards, streaming `.tar.partNNNN` output downloads, token scrubbing/quarantine, session closing confirmation, and `outcome.json` booking. Publishing remains external via `hf repos create --private` / `hf upload` on `<out-dir>/collected`.

## Retained `scripts/colab/` components

- `scripts/colab/preflight_resolve.sh`, `scripts/colab/lock_common.sh`, `scripts/colab/relock.sh`, `scripts/colab/locks/`: deterministic `uv 0.13.5` resolution and `--exclude-newer` drift checks against `lane1/vm_job.sh` (`PINNED_LOCK_SHA`) and `lane3/vm_job.sh` (`PINNED_OVERRIDE_SHA`). For live Lane 3 runs, place the two pinned wheels listed in `scripts/colab/locks/lane3-local-wheels.json` under `scripts/colab/locks/wheels/` (gitignored).
- `scripts/colab/classify_install_log.py`: shared installer failure classifier.
- `scripts/colab/lane1_render.py` and `scripts/colab/lane1_jobs_from_canon.py`: ComfyUI headless queue runner, provenance tEXt stamping, and canon job builder.
- `scripts/colab/lane3_rung.py` and `scripts/colab/lane3/`: dataset packaging/verification, job YAML validation/rendering, copy-off watcher, bundle verification, and local GPU walk harnesses.
