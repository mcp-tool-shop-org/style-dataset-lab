# Real-Service Assumption Audit (`scripts/colab/` via `colab-runner`)

Window lifecycle, `colab` CLI invocation bounds, cap/wall/dead-job watchdogs, chunked `.tar.partNNNN` output downloads, token scrubbing/quarantine, and `outcome.json` booking are handled by [`colab-runner`](https://github.com/mcp-tool-shop-org/colab-runner).

`style-dataset-lab` retains the domain-specific VM jobs (`scripts/colab/lane1/vm_job.sh`, `scripts/colab/lane3/vm_job.sh`), declarative window manifests (`scripts/colab/lane1/colab-window.toml`, `scripts/colab/lane3/colab-window.toml`), pinned dependency locks and preflight drift check (`scripts/colab/preflight_resolve.sh`), Lane 1 render runner (`scripts/colab/lane1_render.py`, `scripts/colab/lane1_jobs_from_canon.py`), and Lane 3 rung/verification helpers (`scripts/colab/lane3_rung.py`).
