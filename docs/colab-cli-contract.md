# Colab CLI contract: one kernel per session, and history keeps code and outputs

Source: google-colab-cli 0.7.4, read on 2026-11-06. The same contract is modelled by the reasoning-dataset-lab fake. This repo's fake is `tests/colab/fixtures/fake_colab.py`, and its section 4 behaviour is tested in `tests/colab/test_fake_single_kernel.py`.

1. **`colab exec` serialises on one kernel per session.**
   - Every exec on a session reuses the stored `kernel_id` (`colab_cli/commands/execution.py:198-210`: `ColabRuntime(..., kernel_id=s.kernel_id, ...)`), and Jupyter runs a kernel's cells one at a time.
   - A second exec issued while a cell is still running waits behind that cell. This happens when the local client was killed or timed out. The second exec does not run concurrently.
   - Killing the local `colab exec` does not stop the VM cell.
   - To run anything else on that session first, interrupt or restart the kernel with `colab restart-kernel -s <session>` (`commands/session.py:220`, registered at `:354`). That command calls `runtime.restart()` (`:248-251`), which is `kernel_client.restart()` (`colab_cli/runtime.py:174-178`), a server-side kernel restart.
   - The CLI source does not show what the server does to processes the cell spawned. Check that after a restart; the lane 3 kit's bundle-now kills the rung's processes by command line either way.
2. **`colab upload` and `colab download` do not use the kernel.** They go through the contents API (`commands/files.py:93`, `:123`, `:161`, `:173` → `contents.upload` / `contents.download`), so they work while a cell runs.
3. **History records exec code and exec outputs.** Every exec writes `{"code": ..., "outputs": ...}` to `~/.config/colab-cli/history/<session>.jsonl` (`execution.py:262-272`).
   - `--env` values become `os.environ[...] = <value>` lines at the top of the code (`execution.py:65-71`, prepended at `:235`), so they end up in the history and in argv.
   - A secret therefore never goes through `--env` or argv, and nothing a secret could appear in may be printed to exec output.
4. **What a fake must do:**
   - queue execs per session behind a running cell;
   - make `restart-kernel` end the running cell the way the real CLI does;
   - serve uploads and downloads independently of the kernel;
   - write a history file with code and outputs;
   - write an argv log.

   This repo's fake ends the cell's kernel process on `restart-kernel` and leaves the cell's spawned processes running (the case the kit must survive). It ends everything on `stop`, because the VM is gone.
