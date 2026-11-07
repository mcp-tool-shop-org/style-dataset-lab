# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Fixed

- **Colab kits: the live host-RAM guard measures private memory, not the page cache** - window `sdlab-l3-rung-g4a` (G4, 2026-11-06) stopped during latent caching on `HOST_RAM_PROJECTION_EXCEEDED`, a false positive: `colab_window.sh` read `AnonPages` and then overwrote it with cgroup `memory.current`, which counts the page cache of the 57.7 GB model download. Its last sample read `memory.current` 173,117 MiB, `AnonPages` 52,492 MiB, `MemAvailable` 125,790 MiB, `MemTotal` 181,130 MiB, `memory.max` `max`: (173,117 + 2,048) x 1.05 = 183,924 > 181,130 tripped; on `AnonPages` it is 57,268. The guard now projects from private memory, the pages the kernel cannot reclaim: cgroup `memory.stat` `anon` + `shmem` when the vitals carry it, else `/proc/meminfo` `AnonPages` + `Shmem` (shmem counts because Colab VMs have no swap, so tmpfs and shared-memory tensors cannot be dropped), every value from one sample; `memory.current` is recorded and never used. A second check trips on `MemAvailable` - delta x 1.05 < 2048 MiB: the kernel's own reclaim-aware figure also falls for unreclaimable memory that is not anon (slab, page tables, driver-pinned buffers), and 2 GiB is the floor the lane-3 walks already stop at. The cgroup `memory.max` stays the ceiling when it is a number (`max` = no limit). The vitals emitters of both lanes now print `CGROUP_MEM_STAT: anon|shmem|file` and `MEM: Shmem`.
- **Colab kits: host-RAM guard review fixes (sdlab #64 review)**
  - **The stall guard counts run output only.** The shell filter that separates run output from vitals lines did not match the new `CGROUP_MEM_STAT:` lines, so every 15 s vitals block counted as progress and `STALL_GUARD_TRIPPED` could not fire. It also matched only `ps` rows that start with a number, while a real `ps -ef` row starts with the user, so a running worker's row counted too. The count now comes from `launch_guards.py --run-output-bytes`, which skips every prefix in `VITALS_LINE_PREFIXES` and every worker `ps` row. A test checks every emitter (both launchers and the fake's) against that one list.
  - **A torn sample is never a reading.** The guard read the newest block that had anon, so a block cut after `anon`/`file` had no MemTotal: the kit's 12288 MB default stood in (57,265 > 12,288, a false trip on a G4), and a number cut mid-write (`anon 55`) read as about 0 MB private (fail-open). The guard now reads only a complete sample: one that reaches `HARNESS:` and has MemTotal, MemAvailable and the full `memory.stat` triple or `AnonPages`, with every field line ending in a newline. A torn newest sample falls back to the one before it.
  - **No default ever stands in for a reading.** The kit's 512/12288 defaults are gone: the RAM check reads `vitals.log` itself (`--check-ram --ram-vitals-file`). With no vitals stream yet (pre-open), or fewer than two samples and none complete, the poll's check is skipped and logged as such. With two or more samples and neither the newest nor the one before complete, the window stops on `HOST_RAM_UNREADABLE`: samples are 15 s apart and written in milliseconds, so that is an emitter that does not print what the guard needs, and a blind guard is not run.
  - **Remaining unnamed stops.** The post-exec final vitals check now logs its refusal (it predates #64), and the launchers' independent wall watcher writes `REFUSED: WALL_GUARD_TRIPPED`. The fake's vitals print the real emitter's lines (`CGROUP_MEM_STAT`, `MemAvailable`, `AnonPages`, `Shmem`), and `ram_replay` can end on a torn sample (`FAKE_COLAB_RAM_TORN`). `colab_window.sh` is mode 100755 again.
  - **One sample per block, every part tested (confirming review).**
    - A `=== VITALS` header is now split on wherever it appears, not only at column 0: job output with no trailing newline, such as a `\r` progress bar, can put the header mid-line.
    - Each block is cut at the end of its first `HARNESS:` line, so a block can no longer pair one sample's meminfo with the next sample's `anon`. This is hardening: the real g4a log had all 17 headers at column 0.
    - New tests cover a sample cut after `MemAvailable` but before `HARNESS:`, a sample missing only `MemTotal`, and a complete sample with no private-memory source.
    - Each new test fails under the mutation it targets: dropping the `HARNESS:` check, defaulting `MemTotal`, or splitting only at `^`.
  - Kit pins re-pinned. scripts/colab coverage 96.34%, floor 90 (unchanged).
- **Colab kits: every live-guard trip is a named refusal with its numbers in `guards.log`** - a RAM trip returned without a `REFUSED` line (its message went to stderr only), so `window.json` read `refusal_code: null` and `status: failed`. `HOST_RAM_PROJECTION_EXCEEDED` is now logged with `colab_refuse_logged`, after a record of the private memory, its source, the delta, the factor, the ceiling and `MemAvailable`, tripped or not. The same was true of the other trips: the wall/cap guard (`WALL_GUARD_TRIPPED`, `CAP_GUARD_TRIPPED`, `COLAB_USAGE_PARSE_FAILED`) and the vitals guard (`DEAD_HARNESS_TRIPPED`, `STALL_GUARD_TRIPPED`, `SETUP_STALL_TRIPPED`) wrote their record but no refusal line; each now names itself, and a guard that exits non-zero without a record is `GUARD_FAILED`. `window.json` and `outcome.draft.json` carry `why` (the refusal line's text). Kit pins re-pinned (`launch_guards.py`, `colab_window.sh`, both launchers). scripts/colab coverage 96.41%, floor 90 (unchanged).
- **Colab kits: the mid-run re-baseline can no longer hide our rise** (from reasoning-dataset-lab's re-reads review) - the neighbour re-baseline used our *last* stable rate, so a low stable read taken while a closing neighbour's rate led its count by two reads (a T4's 1.07 closing beside our 8.88 reads 7.81) left a baseline for a neighbour that was gone, and our later rise to 10.50 read 9.43 under `--max-rate` 9.5 and never tripped. It now uses the highest stable rate seen (`launch_guards.update_window_rate`). The floor also applies mid-run: a stable window rate below `GPU_RATE_FLOOR` is recorded `below_floor` and counts as a bad read toward the 3-read `ASSIGNMENTS_UNREADABLE` limit, never accepted.

### Added

- **Colab lane 3: the 500-step GPU rung (`--rung-job 20|500`, `RUNG_JOB_REQUIRED`, `scripts/colab/lane3/rung-qwen-image-500.yaml`)** — adds the committed 500-step rung config (`train.steps: 500`, `save.save_every: 250`, `sample.sample_every: 250`, keeping `train.skip_first_sample: true` and `datasets[0].num_workers: 0`) beside the 20-step `rung-qwen-image.yaml`. `launch_lane3_stub.sh --train` now requires `--rung-job 20|500` with no default (`RUNG_JOB_REQUIRED`, refused before any `colab` call; `--rung-job` without `--train` is `TRAIN_OPTION_WITHOUT_TRAIN`). Each job carries its own pinned sha256 (`PINNED_RUNG_YAML_SHA` for `20`, `PINNED_RUNG500_YAML_SHA` for `500`), verified before opening, and the selected file is uploaded as `/content/rung-qwen-image.yaml`. `window.json` and `outcome.draft.json` record `rung_job` and `rung_job_sha256`. Fake-colab end-to-end stop-path tests prove that when a 500-step run is stopped mid-run after step 250 by either the rig-side cap guard (`CAP_GUARD_TRIPPED`) or the independent wall guard (`WALL_GUARD_TRIPPED`) with a half-written step-500 checkpoint on disk, the downloaded bundle keeps the complete step-250 checkpoint (`rustline_style_v5_000000250.safetensors`) and all 6 step-250 samples, marks the half-written step-500 checkpoint `partial` in `manifest.jsonl` (`partial_checkpoints`), and records the stopped/partial run and guard refusal in `window.json`.
- **Colab kits: the GPU machine shape is explicit (`--shape standard|high-mem`, `SHAPE_REQUIRED`, `SHAPE_MISMATCH`)** — `colab_window.sh` sent `--high-mem` with every GPU card, and google-colab-cli 0.7.4 drops it only for L4, V5E1 and V6E1 (`colab_cli/client.py:90-111`), so a G4 was opened as High-RAM, a shape nobody had priced (our G4 measurement is G4 Standard, 8.90/h). A GPU card now needs `--shape` in both lanes, through one shared gate (`colab_shape_gate_arm`, checked again by `colab_open_session_locked`), refused before any `colab` call when it is missing or invalid; `--high-mem` reaches `colab new` only for `high-mem`. After the open the session's `colab sessions` row must show the requested Shape (High-RAM / Standard), or the kit refuses `SHAPE_MISMATCH`, stops the session and records both values. `--shape standard` on L4, V5E1 or V6E1 is refused (`SHAPE_STANDARD_UNAVAILABLE`); they expect High-RAM. `window.json` carries `shape_requested` and `shape_check`. CPU stubs are unchanged: always `colab new --high-mem`, no `--shape`. The fake CLI's `colab sessions` now prints real rows with the Shape (`FAKE_COLAB_SESSION_SHAPE` forces a mismatch).
- **Colab kits: lock resolution is time-bounded (`--exclude-newer`), so an upstream release can no longer cause `LOCK_DRIFT`** — `scripts/colab/preflight_resolve.sh` re-ran each lane's `uv pip compile` unbounded, so transformers 5.22.2 (PyPI, 2026-11-06 15:42:54Z) against `lane1.lock`'s 5.22.1 failed "Colab pre-flight resolve — lane 1" on every PR, and every transitive dependency of both lanes floated the same way. Each lock now has a committed bound beside it, `scripts/colab/locks/<lane>.exclude-newer` (one RFC 3339 UTC instant, `YYYY-MM-DDTHH:MM:SSZ`, `#` comments allowed), and the drift check passes it to uv 0.13.5's `--exclude-newer`, with `UV_EXCLUDE_NEWER`/`UV_EXCLUDE_NEWER_PACKAGE` cleared. A missing file is `LOCK_TIMESTAMP_MISSING`; a malformed, impossible or future one is `LOCK_TIMESTAMP_MALFORMED`, checked before any compile. Both lanes are bounded at `2026-11-06T15:00:00Z`, under which the compile reproduces the committed locks' names, versions and hashes exactly (89 and 158 pins); the lock files are byte-identical (sha256 unchanged, so `PINNED_LOCK_SHA` and `PINNED_OVERRIDE_SHA` stay). The comparison leaves out uv's two-line header, which records the command. New `scripts/colab/relock.sh <lane> --exclude-newer <instant|now>` writes a lock and its bound together, sharing the compile with the drift check (`scripts/colab/lock_common.sh`); a bump is a PR that moves the bound and re-locks (`docs/colab-locks.md`). PyPI lists an upload time for every file; the PyTorch index only for some (torch, torchaudio, triton), and uv 0.13.5 hides files without one, so resolution falls to PyPI for those. Still outside the bound: lane 3's two local wheels (pinned by sha256 and git commit), files an index removes after the bound, and PyTorch-index files that later gain an upload time. `scripts/colab` coverage 96.27% (unchanged: no Python file under `scripts/colab` changed), floor 90.
- **Colab kits: a GPU window runs on its live rate (`RATE_UNREAD`, `RATE_ABOVE_MAX`, `--max-rate`)** — the cap guard spends the larger of the balance drop and rate x elapsed (`launch_guards.py:303-309`), and when the post-open `colab usage` rate read 0.00 it projected with the configured CPU rate, 0.26/h (`launch_guards.py:148-174`, `colab_window.sh:219`), which is what lane 3 rung 1 recorded on an A100-80 billing 8.88/h. On a GPU card the projection now uses only the live post-open rate: the kit polls `colab usage` right after open (up to 24 polls, 5 s apart) and refuses `RATE_UNREAD` without a positive rate, before any upload. `--train` requires `--max-rate <units/h>`; a window rate (post-open minus pre-open, since `colab usage` reports the account) above it is `RATE_ABOVE_MAX`. The reading and the limit are in `window.json` (`rate_check`). CPU stubs keep the labelled configured rate.
- **Colab kits: one GPU rate gate for every lane, and a neighbour no longer ends our window** - lane 1 took no `--max-rate` and ran a GPU card on the account rate. Both lanes now go through one gate in `colab_window.sh`: `colab_gpu_rate_gate_arm` before the open, and `colab_open_session_locked`, which refuses `GPU_RATE_GATE_NOT_ARMED` for an unarmed GPU card. After the open it starts the cap clock and reads the stable window rate. `colab usage`'s "Active assignments" count is recorded with every reading. A changed count, once two reads at the new count agree, re-baselines the neighbour (account rate minus our last stable rate) instead of reading a parallel window's open as our rise, or its close as a drop. Before the window's first stable read, a missing count or 0 means "not yet registered" and counts only against the `RATE_UNREAD` poll budget. After it, a missing count or 0 for 3 reads in a row ends the window with `ASSIGNMENTS_UNREADABLE`. Known limit: a neighbour opening on the same read our own rate rises folds that rise into the baseline; pricing at max(`--max-rate`, highest seen) bounds it. Stability pairs are at least 5 s apart mid-run as well. CPU stubs are unchanged.
- **Colab kits: the window rate needs a floor and stability, and is priced at `--max-rate` or above** - `colab usage` reports the account rate, so a neighbour window made a 0.26 pre-open and 9.14 post-open read look like this window's. The window rate (post-open minus pre-open) counts only at or above `GPU_RATE_FLOOR` (1.00/h; the lowest GPU card read, a T4, billed 1.07/h, and the highest CPU rate is 0.26/h) and when two reads 5 s apart agree within 0.01. Otherwise the kit refuses with `RATE_UNREAD`. The cap and the projection are priced at the higher of `--max-rate` and the highest stable window rate, so a low window rate cannot stretch the cap. The rate is re-read on every live cycle, and a stable rate above `--max-rate` refuses mid-run too. Every reading is recorded in `window.json` (`rate_readings`). The cap clock starts when the open succeeds (`cap_clock_started_at`), and every usage call runs under `timeout -k`. Every GPU window requires `--max-rate` (`MAX_RATE_REQUIRED`).
- **Colab lane 3: the GPU rung (`launch_lane3_stub.sh --train`)** — the kit now runs the remote script's `LANE3_MODE=train` on a GPU card, with every request value required and refused by name before any `colab` call: `--model` (`TRAIN_MODEL_REQUIRED`), `--model-revision` (40-hex commit, `TRAIN_MODEL_REVISION_REQUIRED`), `--host-ram-required-gib` (`HOST_RAM_THRESHOLD_MISSING`), `--download-max-seconds` (`DOWNLOAD_LIMIT_MISSING`), `--dataset-dir` (`TRAIN_DATASET_REQUIRED`), a CPU card (`TRAIN_REQUIRES_GPU`), and an HF read token in `HF_TOKEN_GGUF_READ` (`HF_READ_TOKEN_MISSING`; environment only, handed to the VM's download step alone, scrubbed from every log, and recorded only as `hf_token_used`). On the VM, before any model download, `scripts/colab/lane3_rung.py guards` runs a GPU smoke check through the lane's own torch (a timed bf16 1024x1024 matmul on cuda plus one bitsandbytes `AdamW8bit` step; `GPU_SMOKE_FAILED`, recording device, driver, `torch.version.cuda` and the bitsandbytes version), checks free disk on the HF cache's and the training folder's filesystems against 75 GiB (`DISK_FREE_LOW`) and `MemAvailable` from `/proc/meminfo` against the request's threshold (`HOST_RAM_LOW`), and records `/dev/shm`; all measurements reach `window.json` (`train_guards`) whether they pass or not. The model snapshot is downloaded at the pinned revision with a probe: after the first 60 s or 2 GiB of new bytes the full download time is projected from the measured rate and a throttled VM stops with `DOWNLOAD_TOO_SLOW`; bytes, seconds, MB/s and any 429/retry lines are recorded (`model_download`). The job is the committed `scripts/colab/lane3/rung-qwen-image.yaml` (the rustline v5 Qwen-Image config with steps/save/sample at 20, `skip_first_sample`, `num_workers: 0`, and the model given as the local snapshot path so the pinned weights are the ones loaded), run with the hub offline on a 12-image fixture set (`scripts/colab/lane3/rung-dataset.json`, Salt Road plates, cc-by-4.0, sha256-checked rig side and on the VM; `DATASET_FILE_MISSING`, `DATASET_SHA_MISMATCH`). Each checkpoint and sample is copied into the bundle as it is saved, with a sha256 manifest line, and the kit downloads the bundle at the end and, after any failure, whatever it holds. Coverage of `scripts/colab`: 93.97% before, measured after in the PR (CI floor 90 unchanged).
- **Lane 3 GPU-rung local walks (`scripts/colab/lane3/walk_a_real_load.sh`, `walk_b_quantised.sh`)** — run the kit's own train-mode remote script on the rig's GPU in a bwrap-bound `/content` under a card grant: (a) the real config up to its expected CUDA OOM at the transformer load, sampling host RSS and VRAM every second to measure the host-RAM peak the request's threshold comes from; (b) ai-toolkit's documented Qwen-Image quantisation as a stand-in, through the train step, save, sample grid and copy-off. `walk_probe.py` holds the sampler, the summary, the `GPU_BUSY` check and the walk (b) YAML derivation.

- **Colab lane 3 GPU rung, review fixes** — the HF read token now reaches the VM only as a mode-600 file from a private tmpfs directory, uploaded with `colab upload` (never `--env` or argv, which google-colab-cli writes into its per-session history and `ps` shows); the VM reads it and shreds it before anything else runs, and the kit prints a reminder to check the CLI history after the window (`HF_TOKEN_STAGING_FAILED`, `HF_TOKEN_SHRED_FAILED`). After a rig-side kill (wall, cap, stall, dead harness) the kit runs `lane3_bundle_now.py` on the VM, which stops the rung, sweeps the training folder and tars `lane3_out`, so the outputs still come back. A run with no sample image is `TRAIN_SAMPLE_MISSING`. `--train` needs explicit `--wall-s` and `--cap` (`TRAIN_WALL_REQUIRED`, `TRAIN_CAP_REQUIRED`) and a wall that covers the download limit plus 900 s install plus 1800 s training (`TRAIN_WALL_TOO_SHORT`). Copy-off skips a vanished file instead of dying, and a final sweep runs after training. Model-metadata failures are named (`MODEL_AUTH_FAILED`, `MODEL_REVISION_NOT_FOUND`, `MODEL_METADATA_FAILED`), on the VM and in a rig-side check before any spend. The download has a hard limit in its own thread (`DOWNLOAD_TOO_SLOW`). The walks run offline after a `--prepare` step (no network, read-only HF cache, `HF_HUB_OFFLINE=1`), under `timeout --kill-after` and `--die-with-parent`, with VRAM bounded at 28 GiB above the logged idle baseline, enforced by PID and evidence only under `/mnt/e/`.
- **Colab lane 3 GPU rung, confirming-review fixes** — every exec on a session runs on its one kernel, so the failure path now runs `colab restart-kernel` before `lane3_bundle_now.py` (a new exec would otherwise queue behind the killed exec's still-running cell); the fake CLI models one kernel per session, restart-kernel and history with code and outputs (`docs/colab-cli-contract.md`). Lines relayed from the VM and the download-failure tail are scrubbed of `hf_` tokens. The token is staged before `colab new`. A checkpoint whose safetensors header or size does not check out is `partial` and does not satisfy the checkpoint check. The rig's model check refuses a cross-host redirect. The walk sampler stops when VRAM cannot be read and bounds nvidia-smi at 5 s. A timing flake in a setup-stall test is fixed (3 s stall limit).

### Fixed

- **Colab lane 3 kit: `local-wheels.lock` written with a literal backslash-n** — window `sdlab-l3-stub-4` installed the whole 157-package lock and then uv refused `lane3_out/local-wheels.lock` (`Trailing \n is not allowed`), because the Python heredoc that writes it sits inside the kit's unquoted `REMOTEEOF` heredoc, which turned the intended backslash-newline into a literal backslash-n. Each line is now `<pkg>==<ver> --hash=sha256:<sha>` ended by `chr(10)`. A sweep of every line both kits' heredocs change found no other case (the rest are the intended `\$` expansions). The fake CLI now runs the uploaded script's own lock step (`# >>> sdlab-local-wheels-lock` block) and hands the lock to real uv, failing the stub with `LOCAL_WHEELS_LOCK_REJECTED`; `tests/colab/test_lane3_local_wheels_lock.py` runs the step as uploaded and installs the lock with real uv (it fails on a3f44394 with the window's uv error). `scripts/colab` coverage 93.97% (unchanged: no Python file under `scripts/colab` changed), floor 90.
- **Colab lane 3: `torchaudio` missing from the lock** — found by the local walk: ai-toolkit's `run.py` imports `torchaudio` (`toolkit/config_modules.py:7` at the pin; upstream installs it beside torch, README `:152-153`). `lane3.in` adds `torchaudio==2.11.1` (the +cu132 build that imports against the lock's torch 2.15.0+cu132; upstream's 2.11.0+cu130 refuses with a CUDA version mismatch), the lock is 158 pins, and the import gate checks `torchaudio`.
- **Colab lane 3: a failed training step now names itself** — `run.py`'s failure used to end the script with no `REFUSED` line and no bundle; it now prints the tail of `train.log` on the exec stream and `REFUSED: TRAIN_FAILED`.

### Added

- **`launch_lane3_stub.sh --emit-remote-script <file>`** — writes the remote script byte for byte as a window would upload it (one writer function serves both paths) plus `<file>.env` with the `--env` values, then exits. It makes no `colab` call and is refused beside any window option (`EMIT_REMOTE_SCRIPT_EXCLUSIVE`). `REAL_SERVICE_ASSUMPTIONS.md` documents the local walk it enables.

- **Colab kits: defects two real CPU stub windows exposed** — `colab upload` is one Jupyter contents-API PUT and creates no directory (google-colab-cli 0.7.4 `colab_cli/contents.py:56-72`), so lane 3's first wheel upload into `/content/wheels/` failed with HTTP 500 before any exec. Both kits now upload flat into `/content` and the remote script makes its own directories and moves the wheels (`REMOTE_DIR_CREATE_FAILED`); every upload and download is checked (`UPLOAD_FAILED` / `DOWNLOAD_FAILED` with the HTTP status, `REMOTE_PARENT_UNVERIFIED` for any destination outside `/content`). The fake CLI now enforces the same contract (contract block `contents_api`), and the pre-fix upload sequence fails against it. `window.json` takes `refusal_code` only from `REFUSED: <CODE>` lines in `guards.log`, the exec stream and the bundle's `setup.log`, skipping vitals `PROC:` sections, so the import gate's own command line in a `ps` row no longer marks a good run `VENV_IMPORT_OUTSIDE_VENV`. The pre-flight's refusals now carry the `REFUSED:` prefix.
- **Colab kits: hardening** — `--out-dir` is required (`OUT_DIR_REQUIRED`), and a live run refuses one on tmpfs/ramfs or under `/tmp`, `/var/tmp` or `/dev/shm` (`OUT_DIR_VOLATILE`) before any `colab` call. `EXPECTED_*_SHA` overrides and lane 3's fixture-manifest hook are honoured only in fake-colab test mode (the flag and the fake-marked CLI); otherwise `PIN_OVERRIDE_IN_LIVE_RUN`. The VM records the interpreter's identity (uv key, `BUILD`, download URL, `sys.version`, binary sha256) in `setup.log` and `window.json` (`python_identity`) and refuses `PYTHON_BUILD_MISMATCH` unless the build is `20261021`, the python-build-standalone release whose sha256 uv 0.13.5 embeds and checks. CI installs uv 0.13.5 with `--require-hashes` (PyPI sha256 of the manylinux x86_64 wheel). `scripts/colab` coverage 93.97% (826/879 statements, unchanged: no Python file under `scripts/colab` changed; the 20 new tests cover the shell kits and the fake), floor 90.

### Changed

- **Colab lane 3: the CPU stub is an install-path stub; training is a GPU rung** — the local walk of 2026-11-06 showed that ai-toolkit's `run.py` cannot run on any CPU VM (at the pin it calls `torch.cuda.current_device()` while importing `extensions_built_in/diffusion_models/omnigen2/src/ops/triton/layer_norm.py:46`) and that the synthetic job had no `model:` block. The lane 3 remote script now runs in `LANE3_MODE=install` unless told otherwise, and the kit never tells it otherwise: after the import gate it writes `TRAIN_SKIPPED: cpu stub; training needs a GPU rung` to `setup.log`, still bundles the install evidence (`setup.log`, `wheels.log`, the import gate's output, `python_identity.json`) and exits 0, and `window.json` records `train: skipped_cpu_stub`, `checkpoint_path: null`. `window.json` and `outcome.draft.json` for lane `train` carry `train` (`skipped_cpu_stub`, `trained`, or `null`) and `trained`, true only when the window ended ok and the VM reported `trained`, so a skipped run can never read as a trained one. The training step stays in the script behind `LANE3_MODE=train` for the later GPU rung: refused before any install on a VM with no NVIDIA GPU (`TRAIN_REQUIRES_GPU`) or without a plain `LANE3_MODEL_NAME_OR_PATH` (`TRAIN_MODEL_REQUIRED`; the script picks no model), an unknown mode is `LANE3_MODE_INVALID`, the job targets `cuda:0`, and a missing checkpoint is `TRAIN_CHECKPOINT_MISSING`. The kit's `--train` is refused before any `colab` call (`TRAIN_REQUIRES_GPU` on a CPU card, `TRAIN_MODEL_REQUIRED` otherwise). `window.json` now reads the `TRAIN_*` codes. The fake runs the uploaded script's own mode gate on a CPU VM and returns a real bundle; `tests/colab/test_lane3_install_stub.py` covers the gate, the skip, the train step's refusals (the `TRAIN_FAILED` test moved under the train mode) and the window fields. `scripts/colab` coverage 93.97% (unchanged: no Python file under `scripts/colab` changed), floor 90.
- **Colab launch kits (`scripts/colab/`): wheel-only installs from hash-locked lock files, per-lane Python, real `ai-toolkit` pin, and free pre-flight resolve** — Lane 1 now runs on CPython `3.14.9` against `scripts/colab/locks/lane1.lock` (89 pins) and Lane 3 runs on CPython `3.12.15` against `scripts/colab/locks/lane3.lock` (157 pins, replacing `scripts/colab/ai-toolkit-override-py315.txt`) plus pre-built local wheels recorded in `scripts/colab/locks/lane3-local-wheels.json` (`lycoris_lora-1.8.3-py3-none-any.whl` and `diffusers-0.39.0.dev0-py3-none-any.whl`). Re-pinned `ostris/ai-toolkit` to upstream commit `beb94824c51480a04d3c86c718603676fdef6938`. Every `uv pip install` uses `--require-hashes --only-binary :all:` with `UV_NO_BUILD=1`; missing wheels, hash mismatches, lock drift, or missing upstream git pins fail with named refusals (`WHEEL_MISSING`, `LOCK_HASH_MISMATCH`, `LOCAL_WHEEL_MISSING`, `LOCAL_WHEEL_SHA_MISMATCH`, `LOCK_DRIFT`, `PIN_NOT_FOUND`). Added `scripts/colab/preflight_resolve.sh` (invoked before any `colab` CLI call and in CI).
- **Colab kits, review fixes** — the `tests/colab` suite builds its own fixture wheels, manifest and a local two-commit git repo, so it no longer reads pre-built wheels from the rig and passes on a CI runner. No machine path remains in the kits or the wheel manifest: lane 3 requires `--wheel-dir` or `SDLAB_WHEEL_DIR` (`WHEEL_DIR_REQUIRED`). The pre-flight fetches each pinned commit by sha (the kit pin and the manifest's `diffusers` commit), so a valid non-tip commit passes; an unreachable server is `PIN_CHECK_UNAVAILABLE`, not `PIN_NOT_FOUND`. It refuses any uv other than the kits' 0.13.5 (`UV_VERSION_MISMATCH`), reports a failed compile as `LOCK_COMPILE_FAILED` (`LOCK_DRIFT` only for a successful compile that differs) and missing tools or inputs as `PREFLIGHT_TOOL_MISSING` / `LOCK_INPUT_MISSING`, and honours its test hooks only under the fake `colab` CLI (`PREFLIGHT_TEST_HOOK_IN_LIVE_RUN` otherwise). On the VM, a failed lock install is classified from uv's own log by `scripts/colab/classify_install_log.py` (`WHEEL_MISSING`, `LOCK_HASH_MISMATCH`, `INSTALL_NETWORK_FAILURE`, `INSTALL_FAILED`, with the log tail in the refusal). uv itself is installed by hash (`pip install --require-hashes` with the PyPI sha256 of the manylinux x86_64 wheel), and `uv venv` no longer seeds an unpinned pip. `scripts/colab` coverage 93.69% → 93.97%.

## [3.5.1] - 2026-11-05

### Changed

- **Portlight ship data cleared and quarantine removed** — the studio's Portlight ship data (`mcp-tool-shop/portlight-ships-anatomy`) and `plsvessel` LoRA (`mcp-tool-shop/portlight-ships-anatomy-lora`) are cleared under the MIT licence for training and CC-BY-4.0 release. Removed the quarantine patterns and checks in `lib/model-licences.js`, `lib/adapters/ai-toolkit.js`, `lib/train-runs.js`, and `lib/verify-chain.js`, and added the cleared MIT catalogue entry for `plsvessel` / `portlight-ships-anatomy`.

## [3.5.0] - 2026-11-05

**Provenance you can prove, canon a model can draft but not decide, and the first Colab lanes.** Tests **791 → 926**.

### Added

- **`sdlab asset ingest <dir>`** — the asset lane. Admits a 3D asset's re-rendered turnaround as provenance-carrying training data, against an `asset-source.json` contract (schema 1.3.0). Every declaration (channels, palette bands, gate thresholds, the acceptance verdict, the style register, how the renders came to exist) is proven against the actual bytes, and the whole ingest is refused on any violation. Records land uncurated with `provenance.source: "asset"`. Missing-but-optional declarations are reported as notices rather than failures. Contract: `docs/asset-lane-design.md`.
- **`sdlab verify --project <name>`** — walks the release provenance chain offline for each record: owner and CC-BY-4.0 licence on the record, the bound canon entry (by `canon_sha` and entry hash), the licence of every model and LoRA (SPDX id, licence URL, date read, and the file's sha256), and the workflow hash in the run manifest. A missing link fails.
- **`sdlab canon draft`** — a local model drafts canon entries and prompts through a loopback-only, OpenAI-compatible endpoint. Output is written with `status: "draft"`, `judgment: null`, and `drafted_by_model` / `author_model` on every path. Keys a model could use to pre-fill a ratification, judgment or status are stripped from its output.
- **Canon review gate and memory store.** The freeze gate refuses any model-drafted entry unless a person approved it, with a reason and the sha256 of the exact draft approved. A persistent memory store keeps every draft and decision, marking model authorship.
- **Run provenance in images.** Lane-1 renders stamp their generation provenance into PNG metadata. Training runs record what trained them (`lib/train-runs.js`), including Qwen LoRA support through ai-toolkit.

### Experimental

- **Colab launch kits** (`scripts/colab/`) for a lane-1 render and a lane-3 training step on your own Colab account. They pin every input by hash, check the real `colab` CLI contract, cap spend from your live balance (refusing to start if the balance can't be read), watch setup and run separately for stalls, and stop their own session on exit. **They have not yet completed a live window end to end.**
- The canon draft and review gate are complete, but no single command yet drives drafting, review and freeze together.

### Changed

- Every pull request now runs CI; pushes stay paths-gated. Coverage is uploaded to Codecov, and the repository carries an Atlas map checked in CI.
- The landing site moved to Astro 7.

### Fixed

- Updated `devalue` and `brace-expansion` to their patched releases.
- Removed home paths and an account handle from the tree.

## [3.4.0] - 2026-08-04

**Dogfood swarm.** A full health pass (bugs/security, then proactive hardening, then user-facing copy) followed by three new commands. Tests **400 → 791**. Every fix carries a test proven to fail against the unfixed code.

The through-line: this package had never been exercised outside its own repo checkout, where the workspace root and the package root happen to be the same directory. Most of what follows falls out of that.

### Added

- **`sdlab ingest <dir>`** — bring externally-generated images into a project as bare, uncurated candidate records. There was previously no path in: `reingest generated` requires a trained LoRA's manifest and `reingest selected` requires a selection only the production loop can mint. Records land with `judgment: null`, `canon: null` and `provenance.source: "external"` — it never invents a judgment, a score, or a caption.
- **`sdlab sheet [<dir>]`** — an HTML contact sheet over any directory of candidates, for visual triage before full-resolution review. Shows record id, curation status and prompt per tile; degrades to filename for images with no record yet. Images are referenced by relative path, so a 99-image sheet is ~110 KB and stays openable.
- **`sdlab measure <target>`** — deterministic palette and texture measurement attached to records as numbers. Ported from the validated salt-road audit instruments. **Measurement, not verdict**: it never sets `judgment` or `overall_fit`. Requires Python 3.9+ with Pillow/numpy/scipy; without them it fails with a clear structured error rather than degrading silently.
- **Judgment-provenance reporting** in `sdlab eligibility audit` — distinguishes judgments a person made from judgments a bulk script minted, read-only, without modifying any record.
- `--resume` on `generate:identity`, `generate:controlnet` and `generate:ipadapter`, including the seed-advances-on-skip discipline that makes a resumed run reproduce what an uninterrupted one would have produced.

### Fixed

- **`sdlab init` wrote user projects into `node_modules/`.** `REPO_ROOT` resolved from the module's own location, so for anyone installing from npm rather than cloning, every project — canon, records, judgments, snapshots, exports — landed inside the installed package, where the next `npm ci` silently destroyed it. Replaced with a workspace resolver (`SDLAB_ROOT` → walk up from cwd for `projects/` → module root if it is the checkout → cwd) that refuses any root inside `node_modules`. A separate package root now serves `templates/` and `runtime/`, which ship in the tarball and are not workspace content.
- **`--project` accepted a traversing value.** `--project ../../some-sibling-repo` resolved outside the sandbox and was accepted; ~26 scripts then wrote beneath it. `getProjectRoot()` now rejects separators and `..`, and every script routes through it.
- **`sdlab project doctor` printed a failure and exited 0** on a missing project — and `npm run verify` and the CI smoke step both gate on that exit code.
- **Subject leakage with an audit that certified it clean.** The split's subject-family fallback split one subject across two families (`_v1` suffix vs `v2` infix, case-sensitively), and the leakage audit re-read the same family map the assignment used, so it could not detect that class at all — while the dataset card printed "Subject leakage: None (verified)". Added an independent stem cross-check; the card now withholds "verified" unless both checks pass and the guessed-family share is immaterial. A split predating the cross-check now says so instead of claiming verification it never received.
- **`training-package build` produced an empty package and exited 0 on Windows** without Developer Mode: no symlink guard, and a bare `catch { continue; }` in all three adapters dropped image, caption and metadata row together.
- **`eval-run score` returned `overall_verdict: "pass"` for a missing eval pack** — `[].every()` is vacuously true, so a moved or deleted pack scored zero tasks as a pass.
- **Pinning parity between the JS and Python runners.** Float formatting diverged (`0.00005` vs `5e-05`), an explicit `null` LoRA weight defaulted differently, and the Python bridge hardcoded `sampler`/`scheduler`/`shift` **inside its own pinning receipt** — asserting values it never read.
- The freeze gate failed open on a malformed `status` (a capital `F` silently disabled protection). Captions fell back into curation metadata. `checksums.txt` was written and never verified. No `fetch` in the ComfyUI client carried a timeout. `--dry-run` created directories. `run generate` wrote its manifest only at the end, so an interrupted long run left no record at all and did not appear in `run list`.
- `migrate-records.js` was excluded from the npm tarball while still dispatched and documented — every npm user running `sdlab migrate` got `Cannot find module`. `runtime/` did not ship at all. 30 KB of Python bytecode did.
- Three scripts that fabricated curation rationales from a filename-prefix regex were deleted.

### Changed

- Error hints across `doctor`'s ~38 failure sites now carry a concrete next action, and `INPUT_UNKNOWN_PROJECT` names both causes (wrong directory vs missing project) rather than assuming the second.
- `sdlab critique` no longer presents its automatic `Next:` suggestion as a considered judgment when nothing has been reviewed — every candidate is stamped `usable` by default and nothing changes it, so the ranking was drift-count tiebreaking, not assessment.
- `sdlab init` scaffolds a per-project `.gitignore`; generated contact sheets and re-ingest staging images are ignored.

## [3.3.0] - 2026-07-06

**Provenance hardening.** This release closes the three weakest workflow-standards scores (PIN_PER_STEP, EXTERNAL_VERIFIER, UNCERTAINTY_GATED_HUMANS) so shipped, production LoRA work is byte-for-byte reproducible and the verifier/human-gate muscles are in place. No breaking changes — every new field is additive and optional; legacy manifests and records load unchanged.

### Added

- **PIN_PER_STEP — run-manifest pinning contract** (`lib/run-manifest.js`, the single source of truth): every generation writer now records a `pinning` block so a wave is byte-for-byte replayable —
  - **`comfy_workflow_sha`** — SHA-256 of the exact ComfyUI graph submitted (per-item seed + prompt normalized out, so one hash pins the whole wave's pipeline skeleton). The JS runners (`generate.js`, `comfyui-runner.js`) and the Python bridge (`scripts/qwen_generate.py`) produce a **byte-identical** hash for the same graph.
  - **Model + LoRA content identity** — `unet`/`clip`/`vae`/`checkpoint` and each LoRA upgraded from a bare filename to `{name, size_bytes, sha256}`. `sha256` is opt-in via `--hash-models` (best-effort, resolved under the ComfyUI models dir, cached by `(name, size, mtime)` so multi-GB checkpoints aren't re-hashed every wave); `size_bytes` is always recorded when the file resolves. Unresolvable files record `sha256: null` with a `hash_note` — a hash is never fabricated.
  - **`seed_policy`** — records the intent behind seed selection (`base+increment`, `explicit-per-item`, `fixed`, `random`), not just the values.
  - New `--hash-models` flag on `sdlab generate` and `sdlab run generate` (and `scripts/qwen_generate.py`).
- **EXTERNAL_VERIFIER — judge/generator provenance** (`lib/verifier.js`): curate and critique records now carry **`judged_by_model`** (`human` / `rule-based:sdlab-critique-v1`) and **`generator_model`** (derived as `<base>:<model>`, e.g. `qwen-image:qwen_image_fp8_e4m3fn`), and a **WARN fires when the two are the same model** — the self-verification failure mode. (Today's rule-based critique engine is a different artifact class from the generator, so the warning does not fire; the fields + warning install the muscle for when an LLM critique mode enters the loop.)
- **UNCERTAINTY_GATED_HUMANS —**
  - **`sdlab critique --triage`** surfaces only the candidates that need a human — `off-model` OR ≥ `--drift-threshold` (default 3) drift issues — so attention gates on uncertainty rather than on every item. The full `critique.json` is unchanged; triage is a view over it.
  - **Contrastive freeze-gate refusals** — the freeze bypass prompt now leads with the default action and the system's reasoning (`Default: REFUSE — "<id>" is <status> frozen by <by> on <date>, reason: "<why>". Override with --i-know --reason ONLY if your change does not touch the watched fields [...]`), and `curate <id> borderline` prints a contrastive HOLD advisory.

### Changed

- **Manifest `SCHEMA_VERSION` 2.2.0 → 2.3.0** — the ComfyUI run manifest now stamps `schema_version` and carries the `pinning` block. Readers still `checkManifestVersion()`-warn (never throw) on mismatch, so pre-3.3.0 manifests load fine.

### Tests & coverage

- **400 tests, 0 failing** (368 → 400: +32 for pinning, verifier fields, triage, and contrastive freeze wording). Coverage: statements **63.53%** / branches **75.77%** / functions **69.04%**.



The **canon authoring** release. A new `sdlab canon *` namespace turns a project's canon entity store into the projections training actually consumes, and wraps a witness-backed freeze spine around entries that must not drift — plus first-class Flux and Qwen-Image training paths.

### Added

- **Canon authoring namespace (`sdlab canon *`)** — the headline of this release:
  - **`sdlab canon build`** (#16) — builds three canonical projections from a project's canon entity store: `dataset.jsonl` (for training adapters), `prompts/<id>.j2` (Jinja2 templates for ComfyUI invocation), and `context/<id>.md` (narrative blocks for Role OS dispatch). Output keyed by `<canon_sha>` with a content-addressable cache under `canon-build/.cache/`. Flags: `--full`, `--no-cache`, `--dry-run`, `--only <ids>`, `--json`, `--quiet`.
  - **`sdlab canon freeze` / `unfreeze` / `freeze-status`** (#17) — witness-chain freeze tooling. `freeze` stamps a freeze block on an entry (witnessed against a canon-build output via `locked_at_build`), writing both the entry frontmatter and an append-only `canon-build/freeze-events.jsonl`. Statuses: `frozen` (regen refused; unfreeze ceremony required) and `soft-advisory` (refused by default, bypassable with `--i-know`). `--reason` is required on freeze/unfreeze — the audit record depends on it. `freeze-status` is a read-only glance at an entry's state.
  - **`sdlab canon drift`** (#19) — for every frozen / on-canon-change entry, recomputes the watch-field hash and compares against the hash stamped in the latest canon-build manifest; reports drifted entries and overrides since a given build.
- **Canon schema system** (#18) — Star Freight Grounded canon shipped as worked example data (28 entities across 5 entry schemas), demonstrating the entity format `canon build` consumes.
- **`flux-natural-language` caption strategy** (#11) — natural-language captions for Flux.1-dev LoRA training, alongside the existing SDXL trigger-word strategy.
- **Two-LoRA stack training contract** (#15) — threads the `is_style_lora` boolean through profiles and adapters (world/style LoRAs → `true`, per-character subject LoRAs → `false`), driving trainer regularization for the two-LoRA stacking pattern.
- **Flux training targets** — Flux-target training profiles (#12) and Flux-target ComfyUI workflow profiles (#13) for Star Freight, plus the **`ai-toolkit` adapter** for Flux LoRA training (#14): emits `dataset/<partition>/<record_id>.{png,txt}` + `metadata/<partition>.jsonl` + an `ai-toolkit-config.yaml` that Ostris [ai-toolkit](https://github.com/ostris/ai-toolkit) consumes directly. Flux-only — rejects non-Flux profiles with `ADAPTER_TARGET_FAMILY_MISMATCH`; emits `is_style` from the profile's `is_style_lora`. Registered in `ADAPTER_REGISTRY` beside `generic-image-caption` and `diffusers-lora`.
- **Qwen-Image native generation** (#24) — native non-anime Qwen-Image generation path with a `gpu_model` override.
- **Qwen DiT LoRA chain** (#25) — DiT LoRA chaining in both Qwen runners, with tallow-fen style-LoRA dataset wiring.

### Fixed

- **Caption prompt bleed** (#9) — routed captions through the shared research-backed builder so prompt fragments no longer bleed across records.
- **Freeze witness-chain drift** (#19) — the drift CLI reads `.watch_hash` from the rich freeze stamp, and `freeze-status` surfaces resolved `watch_fields`.

### Changed

- Training adapter registry now exposes three adapters — `generic-image-caption`, `diffusers-lora`, `ai-toolkit`; the handbook reference and README document the `ai-toolkit` Flux-only precondition.
- `projects/`: rustline and tallow-fen production style datasets added as worked examples (repo-clone content; not shipped in the npm package).

### Dependencies

- **`yaml@^2.8.3`** added as a runtime dependency for the ai-toolkit YAML config (#14), kept current in the range (#23). CI: `actions/checkout` 6→7 (#30), `codecov/codecov-action` 5→7 (#31).

### Tests & coverage

- **368 tests, 0 failing.** Coverage: statements **60.36%** / branches **75.5%** / functions **68.35%**.

## [3.1.0] - 2026-04-22

### Added — `--resume` for `generate` and `batch generate`

- **`sdlab generate --resume`** — skip subjects whose record JSON and output PNG are already on disk. Seeds remain stable: skipped slots still advance the seed counter so resumed runs are bit-identical to a fresh run that reaches the same point. Final summary now reports `(N errors, M resumed)`.
- **`sdlab batch generate --resume <batch_id>`** — re-runs only failed/missing slots in an existing batch, keeps the same `batch_id`, and inherits `mode_id`/`subject_id`/`theme`/`asset_ref` from the prior manifest. Surfaces "(C/T slots already complete)" in the header. Throws `BATCH_NOT_FOUND` for a bad id and `BATCH_NO_PROGRESS` for pre-checkpoint manifests that can't be partially resumed.
- **Manifest format:** `slots[].status` is now persisted (`'ok'` or `'error'`) so resume can distinguish failures from successes. Older manifests fall back to "selected_output truthy = success" for compatibility.
- New helpers: `buildCompletedSlotMap()`, `openBatchDirForResume()` in `lib/batch-runs.js`.
- 7 new tests in `tests/lib-pipeline/batch-resume.test.js`.

### Fixed — Deterministic SaveImage node selection (PB-003)

- **`lib/comfyui-output.js`** (new): `pickOutputImage(outputs, { preferNodeId })` selects the canonical SaveImage output deterministically. Previously, `comfyui-runner.js` and `generate.js` used `Object.values(outputs)` and broke on the first node with images — first-wins ordering depends on ComfyUI's execution scheduler, not the workflow graph.
- **Selection precedence:** explicit `preferNodeId` (from the workflow builder's `saveNodeId` or a brief's `expected_outputs.save_node_id`) → highest numeric node id (typical "final save" convention) → first iteration entry (only for non-numeric ids).
- `lib/adapters/comfyui-runner.js` and `scripts/generate.js` both updated to thread `saveNodeId` through to the picker.
- Run output records now include `comfy_node_id` so the chosen save node is auditable from the manifest.
- 9 new tests in `tests/lib-pipeline/comfyui-output.test.js`.

### Added — CI coverage reporting

- **`c8`** added as a `devDependency`; new `npm run coverage` script runs the full test suite under c8 with text + lcov + text-summary reporters (covering `lib/**/*.js`).
- **CI**: Node 22 matrix entry now runs `npm run coverage` and uploads `coverage/lcov.info` to Codecov via `codecov/codecov-action@v5` (`continue-on-error: true` so a Codecov outage never blocks the PR).
- **README**: CI and Codecov badges added beside the npm/license badges.
- **`.gitignore`**: `coverage/` and `.nyc_output/` excluded.
- Baseline coverage at this commit: **statements 40.6% / branches 70.7% / functions 54.0%** — meaningful coverage on `lib/snapshot.js`, `lib/split.js`, `lib/log.js`, `lib/args.js`, `lib/runtime-runs.js`; adapters and selection layers still uncovered (deferred to future passes).

### Fixed — Mobile nav on landing + handbook (SB-SDL-007)

- **`site/src/layouts/SiteLayout.astro`**: header was `hidden md:flex` for both the link nav and the npm/GitHub buttons, leaving phones with the brand mark and nothing else. Added a hamburger toggle (`md:hidden`) that opens a drawer containing all the same links plus npm/GitHub. Implemented as a `<details>`/`<summary>` so it works without any JavaScript or framework dependency.
- The desktop nav and the GitHub button still render unchanged at `md:` and up.

### Changed — Training adapter registry (DB-007)

- **`lib/training-adapters.js`** (new): explicit `ADAPTER_REGISTRY` with `loadAdapter()`, `listAdapters()`, `isRegisteredAdapter()`. Replaces the hand-maintained adapter list embedded in a `lib/training-packages.js` error string.
- **`lib/training-packages.js`**: dropped its private `loadAdapter()`; now imports from the registry. Unknown adapters throw `ADAPTER_NOT_REGISTERED` (input error, exit 1) with the available-adapter list always in sync. Registered-but-missing modules throw `ADAPTER_MODULE_LOAD_FAILED` (distinct from a typo).
- **`lib/training-profiles.js`**: `validateProfile()` now rejects profiles whose `adapter_targets[]` cite an unregistered adapter — surfaces typos at profile load time instead of at package-build time.
- 8 new tests in `tests/lib-pipeline/training-adapters.test.js`.

To add a new adapter (e.g. `kohya-lora`, `onedtrainer`): write `lib/adapters/<id>.js` exporting `buildPackage(opts)` and add a one-line entry to `ADAPTER_REGISTRY`. The error message, profile validation, and (eventually) CLI completion all pick it up automatically.

## [3.0.1] - 2026-04-21

### Fixed — Dogfood swarm health pass (Stage A: bugs & security)

- **Four Laws enforcement** (`lib/snapshot.js`, `lib/split.js`, `lib/export.js`):
  - Export now inherits `snapshot.config_fingerprint` instead of recomputing; throws `FINGERPRINT_DRIFT` on mismatch (Law 4).
  - Deterministic majority-lane per family with lexicographic tie-break, recorded in `audit.family_lane_decisions` (Law 3).
  - Unassigned-family fallback now throws instead of silently landing in train.
  - `existsSync` guards across snapshot/split/export/eval/training-manifest/training-package/impl-pack prevent ID collisions from overwriting frozen artifacts (Law 1).
  - `included.jsonl` entries now carry `rules_checked`, `profile_id`, and `config_fingerprint` for explainable inclusion (Law 2).
- **Security hardening**: path-traversal rejection on `record.asset_path` and all user-supplied `--source`/`--guide`/`--anchor`/`--ref`/`--outputs`/`--prompt-file`/`--packet-file`/`--domain` flags; URL validation on ComfyUI endpoints; safe filename regex at selection boundaries.
- **CLI structured errors**: ~25 scripts converted from raw `throw new Error` to `inputError`/`runtimeError` so exit codes are correct (1 = user error, 2 = runtime).
- **Pipeline correctness**: brief fingerprint uses recursive `canonicalize()` — deterministic across nested key reordering; override precedence fixed (`||` → `??` so legit zero/empty overrides are preserved); negative-prompt dedup switched from substring to token-exact match; adapter output filenames keyed by `record.id` to prevent basename collisions silently dropping records.
- **Re-ingest**: now actually copies images to `outputs/candidates/` instead of writing records that point at missing files.
- **Curate ordering**: `curate.js` moves image first, then updates record; bulk-curate trio gained `--dry-run` and standard error handling.

### Added — Dogfood swarm humanization pass (Stage B/C)

- **ComfyUI progress**: `submitAndWait` emits heartbeats every 15 s (queued → generating → completed); bails fast on `execution_error` or unknown status shapes instead of timing out silently.
- **Atomic manifest writes**: run/batch manifests use temp-file + rename; `checkpointRunManifest` saves progress after every slot so a crash no longer orphans GPU work.
- **`schema_version` enforcement**: every manifest (`snapshot`, `split`, `export`, `eval-pack`, `eval-run`, `training-manifest`, `training-package`, `implementation-pack`) now stamps `schema_version: '2.2.0'` with warn-on-mismatch loaders.
- **Export truthfulness**: tracks `expected`/`actual`/`failed` counts with per-record reasons and stderr warnings (no more silent-skip under `catch {}`).
- **Snapshot resilience**: malformed record JSON lands in `errors[]` instead of aborting the snapshot.
- **Split audit**: `deviation_from_target` per lane + `overall_deviation_score` in audit output.
- **Eval scorecards**: `sample_record_ids` up to 5 per failure bucket so operators can investigate.
- **CLI help**: `sdlab <cmd> --help` now works for 15 top commands via `HELP_TEXT` registry.
- **Did-you-mean**: hand-rolled Levenshtein suggestion for typo'd commands and flags.
- **`--project` fallback**: loud 2-line stderr warning when falling back to `star-freight` (silence with `SDLAB_QUIET_FALLBACK=1`).
- **Signal handling**: `SIGINT` (130), `SIGTERM` (143), `uncaughtException`, `unhandledRejection` handlers at `main()` so Ctrl+C surfaces a clean message.
- **ETA**: generate and batch-generate print ETA every 5 items with rolling averages.
- **`result()`/`success()` helpers**: artifact paths always print regardless of `--quiet`.
- **`sdlab init`**: scaffolded projects now get a `README.md` with quick commands, layout, and TODO sections.
- **Per-domain example waves**: all 5 domain templates ship `inputs/prompts/example-wave.json` with subjects matching their lane `id_patterns`.
- **Troubleshooting section**: README covers ComfyUI connection failure, missing weights, doctor errors, `--project` fallback, and bug reporting.
- **Install as primary CTA**: landing page leads with a copy-to-clipboard install command; `og:image`/`twitter:card` meta added via `SiteLayout`.

### Changed

- Moved `HANDOFF.md`, `WAVE_PLAN.md`, `WAVE27A_SESSION_STATE.md` to `docs/internal/` with a README explaining the archive.
- `lib/deprecation.js`: `--game` deprecation target bumped from "v3.0" (lying, package is 3.0) to "v4.0".
- Handbook `reference.md` and `architecture.md` rewritten against the v3.0 CLI surface (`--project`, `projects/<name>/`); `--game` demoted to a Legacy section.
- One-off Star Freight wave-curate scripts excluded from the npm tarball via `files`-field negations (137 → 135 files, 179.3 → 173.9 kB).

### Infrastructure

- **Test suite**: 0 → 98 tests across 12 files (`tests/lib-pipeline/`, `tests/lib-dataset/`, `tests/cli-scripts/`).
- **CI**: added `pull_request` trigger; `publish.yml` now runs `npm ci` + `npm run verify` + `npm test` + tag-vs-version guard before `npm publish`; `permissions: contents: read` and `persist-credentials: false` across all workflows; npm cache on every `setup-node`.
- **`package-lock.json`** regenerated from stale v2.2.1 to v3.0.1.
- **Governance**: added `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md`, `.github/PULL_REQUEST_TEMPLATE.md`.
- **Dependabot**: groups restricted to `minor`/`patch` so breaking majors get individual PRs.

## [3.0.0] - 2026-04-16

### Added

- **Selection + Reintegration (Phase 4E)** — close the production loop from generation back to corpus
  - `sdlab select --run <id> --approve <files>` — select approved outputs from a run
  - `sdlab select --batch <id> --approve <slot:file,...>` — select approved outputs from a batch
  - `sdlab selection show [selection-id]` — list selections or show details
  - `sdlab reingest selected --selection <id>` — re-ingest selected outputs as candidate records
  - `--reason` and `--tags` flags for selection context
  - `--dry-run` and `--json` output support
- **Selection engine** (`lib/selections.js`) — create selection artifacts from runs or batches
  - Selection ID generation (`selection_YYYY-MM-DD_NNN`)
  - Run and batch selection with output validation
  - Chosen files copied into `selections/<id>/chosen/`
  - Manifest, summary.json, and summary.md written per selection
- **Generated provenance** (`lib/generated-provenance.js`) — build provenance blocks for re-ingested records
  - Traces back through run → brief → workflow → seed → config fingerprint
  - Normalizes run and batch source context into a single shape
- **Re-ingest from selections** (`lib/reingest-selected.js`) — create candidate records from selections
  - Records carry `source: generated` provenance with full generation provenance block
  - Images copied to `inbox/generated/`
  - Records tagged: `generated`, `selected`, workflow ID, subject ID
  - No auto-bypass around review — records are staged for normal curation
  - Provenance log written as `provenance.jsonl`
- **JSON schemas** for selections and generated records (`schemas/`)
- Doctor validates new project directories (`selections/`, `inbox/generated/`)
- Init scaffolds `selections/` and `inbox/generated/` directories

### Changed

- **README** rewritten to describe the full production loop: canon → dataset → training → brief → run → critique → batch → select → re-ingest
- **Landing page** updated: new headline, description, 4-tab preview (Start, Dataset, Produce, Close the loop), 7 feature cards including production workflow and selection
- **Handbook** updated: index shows production loop diagram, new [Production Loop](handbook/production-loop/) page with complete end-to-end walkthrough
- **Package metadata** updated: description, keywords (`generation-workflow`, `batch-production`, `reintegration`), version badge
- Version bumped to **v3.0.0** — the repo is now a full production workbench, not just a dataset preparation system

## [2.6.0] - 2026-04-16

### Added

- **Batch production modes (Phase 4D)** — coordinated multi-slot generation with reviewable sheet output
  - `sdlab batch generate --mode <id>` — execute a batch production mode (expression sheets, environment boards, etc.)
  - `sdlab batch show [batch-id]` — list all batches or show batch details
  - `sdlab batch sheet <batch-id>` — re-render batch sheet from saved manifest
  - `--dry-run` flag prepares batch directory and briefs without submitting to ComfyUI
- **Batch modes** (`lib/batch-modes.js`) — load, validate, and list batch mode definitions from `workflows/batch-modes/`
- **Batch compiler** (`lib/batch-compiler.js`) — expand one batch mode into multiple slot briefs with controlled per-slot deltas
- **Batch runs** (`lib/batch-runs.js`) — batch directory creation (`batch_YYYY-MM-DD_NNN`), coordinated slot execution, manifest save/load
- **Batch sheet renderer** (`lib/batch-sheet-render.js`) — HTML review surfaces with CSS grid layout, dark theme, zero dependencies
- **4 starter batch modes** for Star Freight: expression-sheet, environment-board, silhouette-pack, continuity-variants
- **JSON schemas** for batch mode definitions and batch manifests (`schemas/`)
- Doctor validates batch mode definitions (batch_type, subject_mode, slot uniqueness, layout, workflow references)
- Init scaffolds `workflows/batch-modes/` and `batches/` directories

## [2.5.0] - 2026-04-16

### Added

- **Critique + Refine loop (Phase 4C)** — inspect run outputs and generate focused next-pass briefs
  - `sdlab critique --run <id>` — generate structured critique of a completed run
  - `sdlab critique show --run <id>` — display saved critique (text, JSON, markdown)
  - `sdlab refine --run <id> --pick <file>` — generate refined next-pass brief from critique
  - CLI override flags: `--preserve`, `--push`, `--suppress` for manual delta control
- **Critique engine** (`lib/critique-engine.js`) — brief-driven candidate analysis
  - 10 critique dimensions activated by workflow canon focus and drift guards
  - Per-candidate structured notes: strengths, drift issues, preserve/correct next pass
  - Run-level recommendation: accept_one, refine_from_one, rerun_broader, discard_run
  - Workflow-specific emphasis by output mode (portrait, expression, moodboard, etc.)
- **Refine briefs** (`lib/refine-briefs.js`) — delta-layered brief generation
  - Preserve/push/suppress instructions derived from critique + CLI overrides
  - Prompt refinement: original prompt preserved, delta instructions appended
  - Negative prompt extension: suppress items added without replacing existing negatives
  - Refined briefs point back to parent brief + source run + picked candidate
- **JSON schemas** for critique reports and refined briefs (`schemas/`)
- Critique and refine artifacts stored in run directory: `runs/<id>/critique.json`, `runs/<id>/refine/`

## [2.4.0] - 2026-04-16

### Added

- **ComfyUI runtime adapter (Phase 4B)** — execute compiled briefs through ComfyUI and capture run artifacts
  - `sdlab run generate --brief <id>` — execute a brief through ComfyUI, capture outputs to runs/
  - `sdlab run show <id>` — show run manifest and results
  - `sdlab run list` — list all runs for a project
  - `--dry-run` flag prepares run directory without submitting to ComfyUI
  - `--seed <n>` override for reproducible generation
- **Run management** (`lib/runtime-runs.js`) — run ID generation (`run_YYYY-MM-DD_NNN`), seed plans (fixed/increment/random), run directory preparation, manifest save/load
- **ComfyUI workflow adapter** (`lib/adapters/comfyui-workflows.js`) — builds ComfyUI prompt graphs from compiled briefs, template resolution by output mode
- **ComfyUI runner** (`lib/adapters/comfyui-runner.js`) — orchestrates seed plan → graph build → submit → poll → download → manifest for each image
- **Run summaries** (`lib/run-summary.js`) — generates summary.json and summary.md in each run directory
- **Runtime templates** (`runtime/comfyui/txt2img-standard.json`) — declarative workflow template metadata
- Doctor validates runtime templates (Section 10)
- `runs/` added to project scaffold

## [2.3.0] - 2026-04-15

### Added

- **Production workbench spine (Phase 4A)** — workflow profiles and brief compiler
  - `sdlab workflow list` — list workflow profiles for a project
  - `sdlab workflow show <id>` — show workflow profile details
  - `sdlab brief compile` — compile a deterministic generation brief from project truth
  - `sdlab brief show <id>` — show compiled brief (text, JSON, or markdown)
- **Workflow profiles** — production recipes defining output shape, canon constraints, drift guards, and runtime defaults
  - 6 output modes: portrait_set, expression_sheet, variant_pack, moodboard, silhouette_sheet, turnaround
  - 12 canon focus categories: silhouette, material_language, palette, anatomy, costume_logic, era_logic, scale_logic, lighting, surface_wear, gesture, composition, faction_read
  - Subject mode enforcement: required, optional, forbidden
- **Brief compiler** — merges 6 layers of project truth into a frozen generation contract:
  - Project canon → lane config → subject identity → training asset hints → workflow profile → CLI overrides
  - Structured prompt assembly (no freeform prompt soup)
  - Deterministic output: same inputs produce identical briefs
  - Config fingerprint (SHA-256) for change detection
  - Outputs JSON + human-readable Markdown
- **3 starter workflows for Star Freight**: character-portrait-set, expression-sheet, environment-moodboard
- **10 domain template workflows** across 5 domains (game-art, character-design, creature-design, architecture, vehicle-mech)
- **New library modules:** `lib/workflow-profiles.js`, `lib/brief-compiler.js`, `lib/brief-render.js`
- **Doctor validates workflow profiles** — checks schema, lane references, subject mode, runtime defaults
- **Init scaffolds `workflows/profiles/` and `briefs/`** directories and copies domain workflow templates

### Key properties

- Workflow profiles are NOT training profiles — they drive generation, not training
- Briefs are frozen contracts — the creative runtime boundary between planning and execution
- Subject constraints are hard when subject_mode = required (fail loudly if missing)
- Drift guards appear as explicit warnings, never hidden in metadata

## [2.2.0] - 2026-04-16

### Added

- **Training + implementation spine** -- complete model-asset pipeline from export package to trained asset
  - `sdlab training-profile list/show` -- training profile management (what kind of model asset to produce)
  - `sdlab training-manifest create/validate/show/list` -- frozen training contracts with export hash and config fingerprint
  - `sdlab training-package build/show/list` -- trainer-ready packages with adapter boundary
  - `sdlab eval-run create/score/show/list` -- score generated outputs against eval packs, produce scorecards
  - `sdlab implementation-pack build/show/list` -- prompt examples, known failures, subject continuity, reingest guide
  - `sdlab reingest generated/audit` -- re-ingest accepted generated outputs as new records with provenance
- **Adapter system** for trainer-specific packaging:
  - `generic-image-caption` -- image folders + metadata JSONL
  - `diffusers-lora` -- image + caption .txt sidecars for diffusers fine-tuning
- **Two starter training profiles** for Star Freight: `character-style-lora`, `environment-mood-lora`
- **New library modules:** `lib/training-profiles.js`, `lib/training-manifests.js`, `lib/training-packages.js`, `lib/eval-runs.js`, `lib/implementation-packs.js`, `lib/reingest.js`, `lib/adapters/generic-image-caption.js`, `lib/adapters/diffusers-lora.js`

### Key properties

- Training manifests are frozen -- if config, export, or profile changes, a new manifest is required
- Adapters transform layout but never mutate inclusion or split truth
- Generated outputs re-enter through normal review (no bypass)
- Every eval run links back to a training manifest and eval pack (no orphans)

## [2.1.0] - 2026-04-16

### Added

- **Dataset spine** -- complete snapshot-to-export pipeline with proof at every stage
  - `sdlab snapshot create/list/show/diff` -- frozen, deterministic record selections with config fingerprinting
  - `sdlab eligibility audit` -- training eligibility evaluation with explicit reason traces
  - `sdlab split build/list/show/audit` -- subject-isolated, lane-balanced train/val/test splitting
  - `sdlab card generate` -- dataset card generation (markdown + JSON twin)
  - `sdlab export build/list` -- self-contained export packages with manifest, metadata, images, splits, checksums
  - `sdlab eval-pack build/list/show` -- canon-aware eval packs (4 task types)
- **New library modules:**
  - `lib/snapshot.js` -- snapshot creation, loading, diffing
  - `lib/eligibility.js` -- eligibility evaluation with reason traces and exclusion categorization
  - `lib/split.js` -- subject isolation (identity/lineage/suffix), mulberry32 PRNG, lane-balanced splitting, leakage audit
  - `lib/card.js` -- dataset card rendering from snapshot + split + config
  - `lib/export.js` -- export package builder with checksums and reproducibility manifest
  - `lib/eval-pack.js` -- four eval task types (lane coverage, forbidden drift, anchor/gold, subject continuity)
- **Selection, split, and export profiles** in `lib/config.js` with sensible defaults
- **Detection functions** (`detectLane`, `detectGroup`) extracted from canon-bind into `lib/config.js` for reuse

### Key properties

- Snapshots are frozen -- once created, never silently changes
- Inclusion is explainable -- every record has a reason trace
- Splits preserve canon truth -- no subject family appears in multiple partitions
- Exports are reproducible -- rebuildable from snapshot ref + split ref + config fingerprint

## [2.0.0] - 2026-04-15

### Breaking changes

- **`games/` renamed to `projects/`** -- all project data now lives under `projects/<name>/`
- **`--game` renamed to `--project`** -- `--game` still works with a deprecation warning (will be removed in v3.0)
- **Canon-bind loads from config files** -- rules, lanes, rubric, and terminology are now per-project JSON, not hardcoded

### Added

- **`sdlab` CLI** -- unified command-line interface (`bin/sdlab.js`)
  - `sdlab init <name> --domain <domain>` -- scaffold projects from domain templates
  - `sdlab project doctor` -- validate project config and structure
  - `sdlab bind`, `sdlab curate`, `sdlab generate`, etc. -- all pipeline commands
- **Shared library** (`lib/`) -- 6 modules replacing duplicated code across 13 scripts
  - `lib/args.js` -- unified argument parser with `--project` and deprecated `--game` support
  - `lib/paths.js` -- centralized path resolution
  - `lib/comfyui.js` -- ComfyUI HTTP client (extracted from 5 scripts)
  - `lib/config.js` -- per-project JSON config loader
  - `lib/records.js` -- record I/O utilities
  - `lib/deprecation.js` -- one-shot deprecation warnings
- **Per-project config files** -- 5 JSON files per project:
  - `project.json` -- identity, domain, generation defaults
  - `constitution.json` -- rules with rationale templates
  - `lanes.json` -- subject lanes with regex detection patterns
  - `rubric.json` -- scoring dimensions, thresholds, failure-to-rule mappings
  - `terminology.json` -- group vocabulary with separate `id_detection_order` and `prompt_detection_order`
- **5 domain starter templates** -- game-art, character-design, creature-design, architecture, vehicle-mech
- **Training profile placeholders** in domain templates (eligible lanes, thresholds, export format)

### Changed

- Canon-bind is now fully config-driven -- loads rules, lanes, dimensions, thresholds, group vocabulary, and rationale templates from per-project JSON files
- Missing config files cause hard failure with actionable error messages (no silent fallback)
- All 10 CLI-exposed scripts refactored to export `run(argv)` for CLI dispatch
- Net code reduction: ~305 lines removed from deduplication

### Migration

1. Rename `games/` to `projects/`
2. Use `--project` instead of `--game` (or keep `--game` with deprecation warning)
3. For canon-bind: add 5 JSON config files to your project (use `sdlab init` as reference)

Star Freight config files are included as the canonical example.

## [1.2.0] - 2026-04-14

- Added `templates/` with blank constitution, review rubric, and example prompt pack
- npm package now ships scripts + templates only (zero game data)
- Fixed game data leak in v1.0.0/v1.1.0 npm packages (games/ was included in tarball)
- All docs reframed around the pipeline (canon, prompts, generate, curate, bind, compare, export)
- README, handbook, and landing page updated for v1.2.0

## [1.1.0] - 2026-04-14

- Monorepo restructure: each game lives in `games/<name>/` with isolated canon, records, and assets
- All scripts accept `--game <name>` flag (default: `star-freight`)
- Existing Star Freight data moved to `games/star-freight/`
- Translations added (7 languages: ja, zh, es, fr, hi, it, pt-BR)

## [0.5.0] - 2026-04-14

- Identity packet system for waves 27A, 27B, and 28
- Painterly pipeline for stylized asset generation

## [0.4.0] - 2026-03-28

- Wave 26: station identities
- Pairwise comparison tooling for quality ranking

## [0.3.0] - 2026-03-15

- Wave 25: alien species generation
- Negative prompt fix (`human` in negative for alien anatomy)
- Wave 25b: regeneration pass for failed outputs

## [0.2.0] - 2026-02-20

- Waves 11-24: expanded category coverage
- Canon binding system linking outputs to design intent

## [0.1.0] - 2026-01-10

- Initial scaffold and ComfyUI integration
- Waves 1-10: character costumes (gritty space theme)
- First export: 570 training units in TRL format
