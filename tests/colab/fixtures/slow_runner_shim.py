"""Test fixture that installs PATH/SDLAB_PYTHON sleep shims around the fake colab CLI and rig Python."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import fake_colab as fc


def install_slow_runner_shim(
    monkeypatch: Any,
    *,
    colab_delay_s: float = 1.0,
    guard_python_delay_s: float = 1.5,
    extra_modules: Sequence[Any] = (),
) -> list[Path]:
    """Wrap `fake_colab.make_fake_colab_env` so every `colab` CLI call sleeps `colab_delay_s` and
    every `launch_guards.py` invocation on the rig (`*launch_guards.py*`, excluding VM worker/kernel
    helpers) sleeps `guard_python_delay_s`. Returns the list of fake `state_dir` Paths created
    under the shim so callers can inspect `slow_shim.log`."""
    orig_make = fc.make_fake_colab_env
    real_py = fc._to_posix(Path(fc._resolve_python()))
    fake_py_posix = fc._to_posix(Path(fc.__file__).resolve())
    recorded_state_dirs: list[Path] = []

    def _slow_make_fake_colab_env(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
        bin_dir, state_dir, env = orig_make(tmp_path)
        recorded_state_dirs.append(state_dir)
        log_posix = fc._to_posix(state_dir / "slow_shim.log")

        py_shim_body = (
            "#!/usr/bin/env bash\n"
            'case " $* " in\n'
            "  *--detached-worker*|*colab_kernel_launcher.py*|*fake_colab.py*) ;;\n"
            "  *launch_guards.py*)\n"
            f"    printf 'GUARD_PY %s\\n' \"$*\" >> '{log_posix}'\n"
            f"    sleep {guard_python_delay_s!r}\n"
            "    ;;\n"
            "esac\n"
            f"exec '{real_py}' \"$@\"\n"
        )
        py3_shim = bin_dir / "python3"
        py3_shim.write_text(py_shim_body, encoding="utf-8", newline="\n")
        py3_shim.chmod(0o755)
        py_shim = bin_dir / "python"
        py_shim.write_text(py_shim_body, encoding="utf-8", newline="\n")
        py_shim.chmod(0o755)

        colab_shim = bin_dir / "colab"
        colab_shim.write_text(
            "#!/usr/bin/env bash\n"
            "#SDLAB_FAKE_COLAB_CLI=1\n"
            "set -euo pipefail\n"
            f"printf 'FAKE_COLAB %s\\n' \"$*\" >> '{log_posix}'\n"
            f"sleep {colab_delay_s!r}\n"
            f"exec '{real_py}' -S '{fake_py_posix}' \"$@\"\n",
            encoding="utf-8",
            newline="\n",
        )
        colab_shim.chmod(0o755)
        env["SDLAB_PYTHON"] = fc._to_posix(py3_shim)
        return bin_dir, state_dir, env

    monkeypatch.setattr(fc, "make_fake_colab_env", _slow_make_fake_colab_env)
    for mod in extra_modules:
        if hasattr(mod, "_make_fake_colab_env"):
            monkeypatch.setattr(mod, "_make_fake_colab_env", _slow_make_fake_colab_env)
    return recorded_state_dirs
