# Colab Launch Kits (`scripts/colab/`)

Pinned, bounded launch kits for Lane 1 (`scripts/colab/launch_lane1_stub.sh`, render) and Lane 3 (`scripts/colab/launch_lane3_stub.sh`, install stub and GPU training rung), sharing window lifecycle and guard primitives in `scripts/colab/colab_window.sh` and `scripts/colab/launch_guards.py`.

See [`REAL_SERVICE_ASSUMPTIONS.md`](./REAL_SERVICE_ASSUMPTIONS.md) for the full interaction audit against `google-colab-cli` v0.7.4 and the remote Colab runtime.

---

## Step Timeouts and From-Trip Cleanup Bounds

Every `colab` CLI call and lock wait from session open through cleanup is wrapped in `colab_run_bounded` (`timeout -k <kill_grace_s> <timeout_s>` in a subshell with `trap - TERM INT`, so child processes always inherit default `SIGTERM`/`SIGINT` dispositions).

| Step / Bound | Default Constant | Timeout (`s`) | `-k` Grace (`s`) | Max Step Bound (`s`) | Log / Refusal Marker |
|---|---|---:|---:|---:|---|
| Open-lock wait (`/tmp/colab-window-open.lock`) | `COLAB_OPEN_LOCK_TIMEOUT_S_DEFAULT` | `180` | `10` | `190` | `REFUSED: OPEN_LOCK_TIMEOUT` |
| Session open (`colab new`) | `COLAB_NEW_TIMEOUT_S_DEFAULT` | `180` | `10` | `190` | `NEW_TIMEOUT` / `REFUSED: SESSION_OPEN_FAILED` |
| File upload (`colab upload`) | `COLAB_UPLOAD_TIMEOUT_S_DEFAULT` (`--upload-timeout-s` / `COLAB_UPLOAD_TIMEOUT_S`) | `120` | `10` | `130` | `UPLOAD_TIMEOUT` / `REFUSED: UPLOAD_FAILED` (`UPLOAD_TIMEOUT_INVALID`, `UPLOAD_TIMEOUT_TOO_SHORT`) |
| Post-open / closing `colab sessions` | `COLAB_SESSIONS_TIMEOUT_S_DEFAULT` | `30` | `10` | `40` | `SESSIONS_TIMEOUT` / `REFUSED: SHAPE_MISMATCH` |
| Bundle download (`colab download`) | `COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT` (`--download-timeout-s` / `COLAB_DOWNLOAD_TIMEOUT_S`, or projected on `--job` via `--download-floor-mb-s`) | `300` | `10` | `310` | `SALVAGE_STEP_TIMEOUT download` / `REFUSED: DOWNLOAD_FAILED` (`DOWNLOAD_TIMEOUT_INVALID`, `DOWNLOAD_TIMEOUT_REQUIRED`, `DOWNLOAD_TIMEOUT_TOO_SHORT`) |
| Salvage `colab restart-kernel` (Lane 3) | `COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT` | `180` | `10` | `190` | `SALVAGE_STEP_TIMEOUT restart-kernel` |
| Salvage `lane3_bundle_now.py` `colab exec` (Lane 3) | `COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT` | `330` (over `--timeout 300`) | `10` | `340` | `SALVAGE_STEP_TIMEOUT bundle-now` |
| Salvage `colab download` (Lane 3) | `COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT` (scales with `--download-timeout-s` / `COLAB_DOWNLOAD_TIMEOUT_S`) | `300` | `10` | `310` | `SALVAGE_STEP_TIMEOUT download` |
| Total salvage deadline (Lane 3) | `SALVAGE_DEADLINE_S` (`190 + 340 + (download_timeout_s + 10)`) | `840` | — | `840` | `SALVAGE_DEADLINE_EXCEEDED <step>` |
| Session close (`colab stop`, 2 attempts) | `COLAB_STOP_TIMEOUT_S_DEFAULT` (`60`), `COLAB_STOP_ATTEMPTS_DEFAULT` (`2`) | `60` x 2 | `10` x 2 | `140` | `STOP_TIMEOUT`, `STOP_RETRY` |
| Wall watcher first wait (`max(COLAB_WALL_ESCALATE_S, COLAB_IN_FLIGHT_BOUND_S)`) | `COLAB_WALL_ESCALATE_S_DEFAULT` (`30`), `COLAB_IN_FLIGHT_BOUND_S` (`310`) | `max(30, 310)` | — | `310` | `WALL_WATCHER_ESCALATED` (`stop_path: "watcher"`, `watcher_wait: "escalated_no_cleanup"`) |

### Cleanup Bounds Measured From the Trip (`cleanup_stop_attempted_by_s`, `cleanup_bound_s`)

Because a wall or signal trip can arrive while a synchronous foreground step (`colab download`, `colab upload`, or `colab sessions`) is already in flight, the worst-case time from the trip to `colab stop` includes the longest bounded foreground step after session open:

- **`in_flight_bound_s`** = `max(COLAB_DOWNLOAD_TIMEOUT_S, COLAB_UPLOAD_TIMEOUT_S, COLAB_SESSIONS_TIMEOUT_S) + COLAB_KILL_GRACE_S` = `300 + 10 = 310` s at the default `300` s download timeout (`--download-timeout-s <int>` or `COLAB_DOWNLOAD_TIMEOUT_S=<int>`, recorded as `download_timeout_s` in `window.json`; non-positive or non-integer values refuse `DOWNLOAD_TIMEOUT_INVALID` before `colab new`).
- **Lane 1 (`render`, no post-failure salvage step):**
  - `cleanup_stop_attempted_by_s` = `310 + 0 = 310` s
  - `cleanup_bound_s` = `310 + 2 * (60 + 10) = 450` s
  - `cleanup_reserve` at `10.5`/h = `(450 / 3600) * 10.5 = 1.3125` CCU (`1.1875` CCU at `9.5`/h; `0.0325` CCU on CPU at `0.26`/h).
- **Lane 3 (`train`, with post-failure salvage):**
  - `cleanup_stop_attempted_by_s` = `310 + ((180 + 10) + (330 + 10) + (300 + 10)) = 310 + 840 = 1150` s
  - `cleanup_bound_s` = `310 + 840 + 2 * (60 + 10) = 1290` s
  - `cleanup_reserve` at `10.5`/h = `(1290 / 3600) * 10.5 = 3.7625` CCU (`3.404167` CCU at `9.5`/h; `0.093167` CCU on CPU at `0.26`/h).

### Wall Watcher Pre-Trip Liveness Poll and Post-Trip Escalation (`stop_path` and `watcher_wait`)

During the pre-trip wait (`wall_s - grace_s`), the independent wall watcher (`colab_run_wall_watcher`) polls the launcher's liveness (`kill -0` / `os.kill(main_pid, 0)`) about every `1` s instead of sleeping in a single long `sleep`:
- **Normal early finish before the trip (`STOP_COMPLETED` logged):** If the launcher exits normally before the wall trip after `colab_stop_and_log_closing` logs `STOP_COMPLETED`, the watcher exits `0` without running a stop (**no double stop**; `stop_path: "trap"`, `watcher_wait: "none"`).
- **Launcher death before `colab new` (no session opened):** If `MAIN_PID` disappears before `session_open_started.txt` or `session_opened.txt` is written, the watcher kills any tracked child processes, cleans up `.watcher_tracked_pids.txt`, and exits `0` with no `colab stop` call.
- **Launcher death before the trip after a session was opened (`watcher_wait: "launcher_gone_pre_trip"`):** If `MAIN_PID` disappears before the wall trip when `session_open_started.txt` or `session_opened.txt` exists and `STOP_COMPLETED` has not been logged, the watcher kills all tracked child PIDs (`out_dir/.watcher_tracked_pids.txt`), runs the bounded `colab_stop_and_log_closing` itself, and writes `watcher_wait: "launcher_gone_pre_trip"` and `stop_path: "watcher"`, plus `window.json` and `outcome.draft.json`, exactly as on the post-trip escalation path.
  - **Pre-trip launcher-death bound:** The stop starts within about `1` s plus the in-flight kill grace (`COLAB_KILL_GRACE_S = 10` s) of the launcher's death, and completes within `stop_bound_s` (`2 * (60 + 10) = 140` s default) after that.
  - **Honest `--dry` bounds:** `--dry` prints both spend bounds and their max — the cap path (`worst_case_cap_path = cap`) and the launcher-death path (`worst_case_launcher_death_path = (death_time + cleanup_bound_s) / 3600 * priced_rate`, where `death_time` is at most the moment the cap would trip) — along with one `assumptions:` line naming the assumption each bound rests on (`cap_path` assumes a live launcher trips the cap guard and runs `cleanup_on_exit`; `launcher_death_path` assumes the wall watcher survives launcher death to poll `kill -0` every `1` s and run bounded `colab stop`).

When the independent wall watcher (`colab_run_wall_watcher`) trips at `wall_s - grace_s`:
1. It writes the trip epoch (`time.time()` float seconds formatted as `%.6f\n`) to `wall_trip_epoch.txt`, logs `REFUSED: WALL_GUARD_TRIPPED`, kills `EXEC_PID` if set, and sends `SIGTERM` to the launcher (`MAIN_PID`).
2. At the top of `cleanup_on_exit` (`colab_enter_cleanup_trap`), the launcher writes its cleanup start epoch into `cleanup_started.txt` (in the same `%.6f\n` float epoch format and from the same `time.time()` clock as `wall_trip_epoch.txt`, with `date -u +%s` fallback) before running post-failure salvage, and right before `colab_stop_and_log_closing` it writes `stop_reached.txt`. When `colab stop` succeeds (`stop_rc == 0`), `colab_stop_and_log_closing` logs `STOP_COMPLETED attempt=<k>/<n> session=<session>` to `stop.log` and `guards.log`, and only *after* `colab_stop_and_log_closing` returns does the launcher terminate `WALL_WATCHER_PID` (`stop_path: "trap"`, `watcher_wait: "cleanup_seen"` in `window.json`).
3. **First wait (`max(COLAB_WALL_ESCALATE_S, COLAB_IN_FLIGHT_BOUND_S)`, measured from the trip):** Because POSIX shells defer `SIGTERM` traps until an in-flight synchronous foreground command (`colab download`, `colab upload`, or `colab sessions`, bounded by `COLAB_IN_FLIGHT_BOUND_S = 310` s) returns, the watcher's first wait for `cleanup_started.txt` is `first_wait_s = max(COLAB_WALL_ESCALATE_S, COLAB_IN_FLIGHT_BOUND_S)` (`max(30, 310) = 310` s in production), measured from the trip (`trip_mono + first_wait_s`). This lets a legitimate in-flight step (such as the post-exec `colab download` of the bundle) finish and enter `cleanup_on_exit` cleanly instead of being `SIGKILL`ed at `30` s. If `cleanup_started.txt` still has not appeared when `first_wait_s` expires (for example because a pre-open step ignored `TERM` past the in-flight bound), the watcher escalates immediately with `watcher_wait: "escalated_no_cleanup"`.
4. **Second wait (`COLAB_CLEANUP_STOP_ATTEMPTED_BY_S`, measured from the trip) and `STOP_COMPLETED` verification:** Once `cleanup_started.txt` (or `stop_reached.txt`) appears, the watcher waits until `trip_mono + COLAB_CLEANUP_STOP_ATTEMPTED_BY_S` (measured from the trip, *never* from `cleanup_started.txt`) for `STOP_COMPLETED` in `stop.log` / `guards.log`. Merely writing `stop_reached.txt` does not satisfy the watcher; only a completed `colab stop` (`STOP_COMPLETED`) causes the watcher to exit `0` (`watcher_wait: "cleanup_seen"`). If `STOP_COMPLETED` has not been logged by `trip_mono + COLAB_CLEANUP_STOP_ATTEMPTED_BY_S`, the watcher escalates with `watcher_wait: "escalated_cleanup_overran"`.
5. **Launcher death at any point after the trip (`watcher_wait: "escalated_launcher_gone"`):** In both the first wait and the second wait, if `MAIN_PID` disappears (`kill(main_pid, 0)` fails, e.g. `SIGKILL` to the launcher before or during salvage, or after `stop_reached.txt` was written while `colab stop` was still in flight) and `STOP_COMPLETED` has not been logged, the watcher immediately kills any tracked in-flight/salvage/stop children (`out_dir/.watcher_tracked_pids.txt`) and runs the bounded two-attempt `colab stop` itself (`stop_path: "watcher"`, `watcher_wait: "escalated_launcher_gone"`), finishing within `cleanup_bound_s` from the trip.
6. **Proof that the worst case stays within `cleanup_bound_s` (`310 + 840 + 140 = 1290` s on Lane 3; `310 + 0 + 140 = 450` s on Lane 1):**
   - Let $t_{\text{trip}} = 0$. Both the first wait (`max(COLAB_WALL_ESCALATE_S, COLAB_IN_FLIGHT_BOUND_S) = 310` s) and the second wait (`cleanup_stop_attempted_by_s = in_flight_bound_s + salvage_bound_s`) are anchored at $t_{\text{trip}} = 0$, not at `cleanup_start`.
   - Any in-flight foreground step at the time of the trip finishes (or is killed by `timeout -k 10`) at $t_{\text{cleanup\_start}} \le \text{in\_flight\_bound\_s} = 310$ s.
   - Post-failure salvage on Lane 3 is bounded by `SALVAGE_DEADLINE_S = 840` s (`0` s on Lane 1), and the watcher's second deadline is anchored at $t_{\text{trip}} + \text{cleanup\_stop\_attempted\_by\_s} = 310 + 840 = 1150$ s (`310` s on Lane 1). Whether the launcher finishes salvage on time, overruns salvage, or dies mid-cleanup (`SIGKILL`), `colab stop` is guaranteed to be started by the launcher or the watcher no later than $t \le \text{cleanup\_stop\_attempted\_by\_s} = 1150$ s (`310` s on Lane 1).
   - Bounded `colab stop` runs at most `COLAB_STOP_ATTEMPTS = 2` attempts under `timeout -k 10 60` (`2 * (60 + 10) = 140` s). Therefore `colab stop` finishes by at most:
     $$\text{in\_flight\_bound\_s} + \text{salvage\_bound\_s} + \text{stop\_bound\_s} = 310 + 840 + 140 = 1290\text{ s} = \text{cleanup\_bound\_s}$$
     on Lane 3 (and $310 + 0 + 140 = 450\text{ s} = \text{cleanup\_bound\_s}$ on Lane 1).
   - `window.json` and `outcome.draft.json` record `stop_path: "watcher" | "trap"` and `watcher_wait: "none" | "cleanup_seen" | "escalated_no_cleanup" | "escalated_cleanup_overran" | "escalated_launcher_gone" | "launcher_gone_pre_trip"`.

### Interruptible Salvage and Post-Exec Download Salvage

- On Lane 3, `EXEC_IN_FLIGHT=1` remains armed through the normal post-exec `colab_download_checked`. If the normal post-exec download fails or times out, any partial local file is removed and `cleanup_on_exit` still runs `lane3_download_bundle_after_failure` (`colab restart-kernel` -> `lane3_bundle_now.py` -> `colab download`) to recover the bundle before `colab stop`.
- During salvage, each step runs via `colab_run_bounded_salvage_step` (backgrounded child subshell + `wait` loop). A single `SIGTERM`/`SIGINT` to the launcher is logged (`CLEANUP_SIGNAL count=1 action=continue_bounded_cleanup`) without aborting salvage; a second `SIGTERM`/`SIGINT` (`count >= 2`) immediately kills the in-flight salvage child (`SALVAGE_ABORTED_BY_SIGNAL`), sets `COLAB_CLEANUP_SKIP_SALVAGE=1`, skips any remaining salvage steps, and proceeds straight to `colab stop`.

### Lane 3 Rung vs Real-Run Inputs, Paid-Run Guards, and Complete Output Copy-Off

Under `--train`, `launch_lane3_stub.sh` supports two mutually exclusive job/dataset paths (`JOB_CONFLICT` if mixed; `RUNG_JOB_REQUIRED` if neither is passed):
- **Rung path (`--rung-job 20|500`):** binds the committed rung YAMLs (`PINNED_RUNG_YAML_SHA`, `PINNED_RUNG500_YAML_SHA`) and fixture manifest (`scripts/colab/lane3/rung-dataset.json`, `PINNED_RUNG_DATASET_SHA`), recording `rung_job`, `rung_job_sha256`, `job_sha256`, `dataset_manifest_sha256`, and `dataset_archive_sha256` in `window.json` and `outcome.draft.json`.
- **Real-run path (`--job <path> --job-sha <64-hex> --dataset-manifest <path> --dataset-manifest-sha <64-hex>`):** verifies `--job` against `--job-sha` (`JOB_REQUIRED`, `JOB_SHA_REQUIRED`, `JOB_FILE_MISSING`, `JOB_SHA_MISMATCH`), checks the 40-hex `--model-revision` (`TRAIN_MODEL_REVISION_REQUIRED`) and single active `__LANE3_TRAINING_FOLDER__`, `__LANE3_DATASET_DIR__`, and `__LANE3_MODEL_PATH__` placeholders (`JOB_TEMPLATE_INVALID` via `lane3_rung.py check-job`), and verifies `--dataset-manifest` against `--dataset-manifest-sha` plus every listed image's existence and sha256 (`DATASET_MANIFEST_REQUIRED`, `DATASET_MANIFEST_SHA_REQUIRED`, `DATASET_MANIFEST_MISSING`, `DATASET_MANIFEST_SHA_MISMATCH`, `DATASET_MANIFEST_INVALID`, `DATASET_FILE_MISSING`, `DATASET_SHA_MISMATCH`) — all before `colab new`.
- **Semantic job & rig-side paid-run guards (`check-job` + `plan-run`, before `colab new`):**
  1. **Bundle download timeout (Part 1):** on `--job`, the `300` s default is refused (`DOWNLOAD_TIMEOUT_REQUIRED`); pass `--download-timeout-s <s>` / `COLAB_DOWNLOAD_TIMEOUT_S=<s>` or project it from `ceil(steps / save_every) * checkpoint_size_bytes + samples_and_logs_bytes` divided by `--download-floor-mb-s <MB/s>` (`DOWNLOAD_TIMEOUT_TOO_SHORT` if an explicit value is below the projection). Both normal and salvage download bounds use the resolved value (`download_timeout_s`, `salvage_download_timeout_s`, `download_timeout_basis` in `window.json`).
  2. **Upload timeout (Part 2):** configurable via `--upload-timeout-s <s>` / `COLAB_UPLOAD_TIMEOUT_S=<s>` (`UPLOAD_TIMEOUT_INVALID`), refusing `UPLOAD_TIMEOUT_TOO_SHORT` on the rig when `dataset_archive_bytes / (upload_floor_mb_s * 1e6) > upload_timeout_s` (`upload_timeout_check` in receipts).
  3. **Full `check-job` coverage (Part 3):** scans every string value in the job YAML and refuses any unpinned hub reference (`org/name`, `|org/name`, `<prefix>|org/name`, or URL not pinned to `@<40-hex>` / `/resolve/<40-hex>/`) as `JOB_UNPINNED_HUB_REF`; requires `--model` and every pinned hub reference to appear on the kit's cleared licence allow-list (`JOB_MODEL_LICENCE_NOT_ALLOWED`); refuses missing or `> steps` `save_every` (`JOB_SAVE_CADENCE_INVALID`) or `sample_every` / disabled sampling (`JOB_SAMPLE_CADENCE_INVALID`); refuses `trigger_word` combined with `cache_text_embeddings: true` (`JOB_TRIGGER_WITH_CACHED_EMBEDDINGS`, citing `ostris/ai-toolkit@beb94824` `config/examples/train_lora_qwen_image_24gb.yaml:15`); and requires explicit `caption_dropout_rate` plus `caption_dropout_source` (`JOB_CAPTION_DROPOUT_INVALID`, citing `toolkit/config_modules.py:968` `0.0` vs `train_lora_qwen_image_24gb.yaml:34` `0.05` at `beb94824`).
  4. **Wall allowance from the job (Part 4):** replaces the old fixed `1800` s allowance with `ceil(steps * seconds_per_step) + download_max_seconds + setup_allowance_s + download_timeout_s` (`TRAIN_STEP_TIME_REQUIRED`, `TRAIN_WALL_TOO_SHORT`, recorded under `wall_allowance` in receipts).
  5. **Keep all model output, disk projection, and manifest check (Part 5):** refuses before opening when `ceil((ceil(steps / save_every) * checkpoint_size_bytes + optimizer_size_bytes) * copy_tar_overhead)` is missing (`TRAIN_OUTPUT_PROJECTION_REQUIRED`) or cannot fit within the VM disk budget (`TRAIN_OUTPUT_DISK_LOW`, checked again on the VM before `run.py` and before `tar` via `BUNDLE_DISK_LOW`, recorded under `output_disk_projection`). `copy-off` copies every regular file in the training folder (checkpoints, optimizer state, resolved config, loss/other logs, samples, and `_*` directories such as `_latent_cache/`), writes `training_folder_manifest.json` (relative path, bytes, sha256) on the VM before the final sweep, and verifies every file in the downloaded bundle on the rig (`verify-bundle`, failing with `TRAIN_OUTPUT_MANIFEST_MISMATCH` on any missing or size/sha256-mismatched file and recording `training_output_manifest_check`).
- **Batched dataset upload (both paths):** before `colab new`, `lane3_rung.py dataset --pack-archive` packs the verified images into one deterministic tar (`dataset_archive_sha256.txt`), uploaded in a single `colab upload` to `/content/lane3_dataset.tar`; on the VM, `lane3_rung.py dataset --archive /content/lane3_dataset.tar --archive-sha ...` verifies the archive sha256 (`DATASET_ARCHIVE_SHA_MISMATCH`) and re-hashes every extracted image against the manifest (`DATASET_SHA_MISMATCH`) before training.

---

## Residual Risk: External `SIGKILL` to the Launcher

No in-process shell trap (`EXIT`, `TERM`, `INT`) can catch `SIGKILL` (`kill -9`).

- **What is left running if an external `SIGKILL` kills the launcher (and its wall watcher) before `colab stop` runs:**
  - The remote Colab runtime assignment (VM, GPU/CPU session, and any running kernel/training processes on the VM) remains active on Google Colab's servers and continues billing compute units against the account until Colab's server-side idle/assignment timeout or manual termination.
  - If `SIGKILL` hits only `MAIN_PID` while the background wall watcher is still alive:
    - **Before the wall trip (`watcher_wait: "launcher_gone_pre_trip"`):** The watcher polls `kill -0` about every `1` s during the pre-trip wait. When `MAIN_PID` disappears after a session was opened (`session_open_started.txt` or `session_opened.txt`) and before `STOP_COMPLETED`, the stop starts within about `1` s plus the in-flight kill grace of the launcher's death and completes within `stop_bound_s` (`140` s default) after that (`stop_path: "watcher"`, `watcher_wait: "launcher_gone_pre_trip"`).
    - **At or after the wall trip (`watcher_wait: "escalated_launcher_gone"`):** The watcher immediately kills any tracked child processes and runs bounded `colab stop -s <session>` itself (`watcher_wait: "escalated_launcher_gone"`), finishing within `cleanup_bound_s` of the trip.
    - If `SIGKILL` kills the entire process group (both launcher and watcher), no local process remains to call `colab stop`.
- **How a stranded session is found and stopped:**
  1. **Automatic visibility on the next window open:** Every GPU window open runs `colab sessions` (`sessions_after_open.txt`) and reads `colab usage`'s `Active assignments: <n>` (`rate_readings`). An unexpected extra assignment (`Active assignments > 1`) or an unexpected session row in `colab sessions` immediately surfaces the still-open session.
  2. **Manual inspection and stop from the rig:** Run `colab sessions` to list all active server assignments and `colab usage` to verify `Active assignments` and current burn rate, then stop each stranded session by name with:
     ```bash
     colab sessions
     colab stop -s <session-name>
     colab usage
     ```
