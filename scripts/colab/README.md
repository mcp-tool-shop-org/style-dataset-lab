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
| File upload (`colab upload`) | `COLAB_UPLOAD_TIMEOUT_S_DEFAULT` | `120` | `10` | `130` | `UPLOAD_TIMEOUT` / `REFUSED: UPLOAD_FAILED` |
| Post-open / closing `colab sessions` | `COLAB_SESSIONS_TIMEOUT_S_DEFAULT` | `30` | `10` | `40` | `SESSIONS_TIMEOUT` / `REFUSED: SHAPE_MISMATCH` |
| Bundle download (`colab download`) | `COLAB_DOWNLOAD_TIMEOUT_S_DEFAULT` | `300` | `10` | `310` | `SALVAGE_STEP_TIMEOUT download` / `REFUSED: DOWNLOAD_FAILED` |
| Salvage `colab restart-kernel` (Lane 3) | `COLAB_SALVAGE_RESTART_TIMEOUT_S_DEFAULT` | `180` | `10` | `190` | `SALVAGE_STEP_TIMEOUT restart-kernel` |
| Salvage `lane3_bundle_now.py` `colab exec` (Lane 3) | `COLAB_SALVAGE_EXEC_TIMEOUT_S_DEFAULT` | `330` (over `--timeout 300`) | `10` | `340` | `SALVAGE_STEP_TIMEOUT bundle-now` |
| Salvage `colab download` (Lane 3) | `COLAB_SALVAGE_DOWNLOAD_TIMEOUT_S_DEFAULT` | `300` | `10` | `310` | `SALVAGE_STEP_TIMEOUT download` |
| Total salvage deadline (Lane 3) | `SALVAGE_DEADLINE_S` | `840` | — | `840` | `SALVAGE_DEADLINE_EXCEEDED <step>` |
| Session close (`colab stop`, 2 attempts) | `COLAB_STOP_TIMEOUT_S_DEFAULT` (`60`), `COLAB_STOP_ATTEMPTS_DEFAULT` (`2`) | `60` x 2 | `10` x 2 | `140` | `STOP_TIMEOUT`, `STOP_RETRY` |
| Wall watcher escalation delay | `COLAB_WALL_ESCALATE_S_DEFAULT` | `30` | — | `30` | `WALL_WATCHER_ESCALATED` (`stop_path: "watcher"`) |

### Cleanup Bounds Measured From the Trip (`cleanup_stop_attempted_by_s`, `cleanup_bound_s`)

Because a wall or signal trip can arrive while a synchronous foreground step (`colab download`, `colab upload`, or `colab sessions`) is already in flight, the worst-case time from the trip to `colab stop` includes the longest bounded foreground step after session open:

- **`in_flight_bound_s`** = `max(COLAB_DOWNLOAD_TIMEOUT_S, COLAB_UPLOAD_TIMEOUT_S, COLAB_SESSIONS_TIMEOUT_S) + COLAB_KILL_GRACE_S` = `300 + 10 = 310` s.
- **Lane 1 (`render`, no post-failure salvage step):**
  - `cleanup_stop_attempted_by_s` = `310 + 0 = 310` s
  - `cleanup_bound_s` = `310 + 2 * (60 + 10) = 450` s
  - `cleanup_reserve` at `10.5`/h = `(450 / 3600) * 10.5 = 1.3125` CCU (`1.1875` CCU at `9.5`/h; `0.0325` CCU on CPU at `0.26`/h).
- **Lane 3 (`train`, with post-failure salvage):**
  - `cleanup_stop_attempted_by_s` = `310 + ((180 + 10) + (330 + 10) + (300 + 10)) = 310 + 840 = 1150` s
  - `cleanup_bound_s` = `310 + 840 + 2 * (60 + 10) = 1290` s
  - `cleanup_reserve` at `10.5`/h = `(1290 / 3600) * 10.5 = 3.7625` CCU (`3.404167` CCU at `9.5`/h; `0.093167` CCU on CPU at `0.26`/h).

### Wall Watcher Escalation (`stop_path`)

When the independent wall watcher (`colab_run_wall_watcher`) trips at `wall_s - grace_s`:
1. It writes `REFUSED: WALL_GUARD_TRIPPED`, kills `EXEC_PID` if set, and sends `SIGTERM` to the launcher (`MAIN_PID`).
2. When the launcher's `EXIT` trap reaches `colab_stop_and_log_closing`, it writes `stop_started.txt` (`stop_path: "trap"` in `window.json`).
3. If `stop_started.txt` has not appeared after `COLAB_WALL_ESCALATE_S` (`30` s — for example because the launcher is blocked in a foreground step waiting for its step timeout), the watcher logs `WALL_WATCHER_ESCALATED`, writes `stop_path.txt` (`watcher`), runs bounded two-attempt `colab stop` and closing `colab usage`/`colab sessions` itself, and sends `SIGKILL` to `MAIN_PID`. `window.json` records `stop_path: "watcher"` (or `"trap"` when the `EXIT` trap ran `colab stop`).

### Interruptible Salvage and Post-Exec Download Salvage

- On Lane 3, `EXEC_IN_FLIGHT=1` remains armed through the normal post-exec `colab_download_checked`. If the normal post-exec download fails or times out, any partial local file is removed and `cleanup_on_exit` still runs `lane3_download_bundle_after_failure` (`colab restart-kernel` -> `lane3_bundle_now.py` -> `colab download`) to recover the bundle before `colab stop`.
- During salvage, each step runs via `colab_run_bounded_salvage_step` (backgrounded child subshell + `wait` loop). A single `SIGTERM`/`SIGINT` to the launcher is logged (`CLEANUP_SIGNAL count=1 action=continue_bounded_cleanup`) without aborting salvage; a second `SIGTERM`/`SIGINT` (`count >= 2`) immediately kills the in-flight salvage child (`SALVAGE_ABORTED_BY_SIGNAL`), sets `COLAB_CLEANUP_SKIP_SALVAGE=1`, skips any remaining salvage steps, and proceeds straight to `colab stop`.

---

## Residual Risk: External `SIGKILL` to the Launcher

No in-process shell trap (`EXIT`, `TERM`, `INT`) can catch `SIGKILL` (`kill -9`).

- **What is left running if an external `SIGKILL` kills the launcher (and its wall watcher) before `colab stop` runs:**
  - The remote Colab runtime assignment (VM, GPU/CPU session, and any running kernel/training processes on the VM) remains active on Google Colab's servers and continues billing compute units against the account until Colab's server-side idle/assignment timeout or manual termination.
  - If `SIGKILL` hits only `MAIN_PID` while the background wall watcher is still alive, the watcher's escalation path will still run `colab stop -s <session>` once the wall limit + `COLAB_WALL_ESCALATE_S` elapses. If `SIGKILL` kills the entire process group (both launcher and watcher), no local process remains to call `colab stop`.
- **How a stranded session is found and stopped:**
  1. **Automatic visibility on the next window open:** Every GPU window open runs `colab sessions` (`sessions_after_open.txt`) and reads `colab usage`'s `Active assignments: <n>` (`rate_readings`). An unexpected extra assignment (`Active assignments > 1`) or an unexpected session row in `colab sessions` immediately surfaces the still-open session.
  2. **Manual inspection and stop from the rig:** Run `colab sessions` to list all active server assignments and `colab usage` to verify `Active assignments` and current burn rate, then stop each stranded session by name with:
     ```bash
     colab sessions
     colab stop -s <session-name>
     colab usage
     ```
