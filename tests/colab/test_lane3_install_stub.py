"""Lane 3 install/mode gates checked directly against `scripts/colab/lane3/vm_job.sh`."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VM_JOB = REPO_ROOT / "scripts" / "colab" / "lane3" / "vm_job.sh"
SKIP_LINE = "TRAIN_SKIPPED: cpu stub; training needs a GPU rung"


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _p(p: Path) -> str:
    s = p.resolve().as_posix()
    return f"/{s[0].lower()}{s[2:]}" if (len(s) >= 2 and s[1] == ":") else s


def _extract_block(name: str) -> str:
    lines = VM_JOB.read_text(encoding="utf-8").split("\n")
    start = lines.index(f"# >>> {name}")
    end = lines.index(f"# <<< {name}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


def _fake_nvidia_smi(bin_dir: Path, gpu: bool) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "#!/usr/bin/env bash\necho 'GPU 0: NVIDIA A100-SXM4-40GB (UUID: GPU-fake)'\n"
        if gpu
        else "#!/usr/bin/env bash\necho 'NVIDIA-SMI has failed' >&2\nexit 9\n"
    )
    (bin_dir / "nvidia-smi").write_text(body, encoding="utf-8", newline="\n")
    (bin_dir / "nvidia-smi").chmod(0o755)


RUNG_ENV = {
    "LANE3_MODEL_REVISION": "75e0b4be04f60ec59a75f475837eced720f823b6",
    "LANE3_HOST_RAM_REQUIRED_GIB": "96.5",
    "LANE3_DOWNLOAD_MAX_SECONDS": "1800",
}


def _run_mode_gate(tmp_path: Path, mode: str | None, gpu: bool, model: str | None,
                   extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "vm-bin"
    _fake_nvidia_smi(bin_dir, gpu)
    gate = tmp_path / "mode_gate.sh"
    gate.write_text(
        "set -euo pipefail\n" + _extract_block("sdlab-lane3-mode") + 'echo "MODE_OK ${LANE3_MODE} cvd=[${CUDA_VISIBLE_DEVICES-unset}]"\n',
        encoding="utf-8", newline="\n",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("LANE3_") and k != "CUDA_VISIBLE_DEVICES"}
    if mode is not None:
        env["LANE3_MODE"] = mode
    if model is not None:
        env["LANE3_MODEL_NAME_OR_PATH"] = model
    env.update(extra or {})
    return subprocess.run(
        [_bash(), "-c", f'export PATH="{_p(bin_dir)}:$PATH"; bash "{_p(gate)}"'],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )


def test_install_mode_is_the_default_and_hides_the_gpu(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, None, gpu=True, model=None)
    assert res.returncode == 0, res.stderr
    assert "MODE_OK install cvd=[]" in res.stdout


def test_train_mode_refuses_on_a_cpu_vm(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, "train", gpu=False, model="some/model")
    assert res.returncode == 1
    assert "REFUSED: TRAIN_REQUIRES_GPU:" in res.stderr


@pytest.mark.parametrize("model", [None, "", 'bad"model\nmodel:', "two words"])
def test_train_mode_refuses_without_a_model(tmp_path: Path, model: str | None) -> None:
    res = _run_mode_gate(tmp_path, "train", gpu=True, model=model)
    assert res.returncode == 1
    assert "REFUSED: TRAIN_MODEL_REQUIRED:" in res.stderr


def test_train_mode_with_gpu_and_model_passes_the_gate(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, "train", gpu=True, model="org/model_v1", extra=RUNG_ENV)
    assert res.returncode == 0, res.stderr
    assert "MODE_OK train cvd=[unset]" in res.stdout


@pytest.mark.parametrize(
    ("var", "value", "code"),
    [
        ("LANE3_MODEL_REVISION", None, "TRAIN_MODEL_REVISION_REQUIRED"),
        ("LANE3_MODEL_REVISION", "main", "TRAIN_MODEL_REVISION_REQUIRED"),
        ("LANE3_HOST_RAM_REQUIRED_GIB", None, "HOST_RAM_THRESHOLD_MISSING"),
        ("LANE3_HOST_RAM_REQUIRED_GIB", "0", "HOST_RAM_THRESHOLD_MISSING"),
        ("LANE3_DOWNLOAD_MAX_SECONDS", None, "DOWNLOAD_LIMIT_MISSING"),
        ("LANE3_DOWNLOAD_MAX_SECONDS", "0", "DOWNLOAD_LIMIT_MISSING"),
    ],
)
def test_train_mode_refuses_each_missing_rung_value(tmp_path: Path, var: str, value: str | None, code: str) -> None:
    extra = dict(RUNG_ENV)
    if value is None:
        extra.pop(var, None)
    else:
        extra[var] = value
    res = _run_mode_gate(tmp_path, "train", gpu=True, model="org/model", extra=extra)
    assert res.returncode == 1 and f"REFUSED: {code}:" in res.stderr


def test_unknown_mode_is_refused(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, "trian", gpu=True, model="m")
    assert res.returncode == 1 and "REFUSED: LANE3_MODE_INVALID: LANE3_MODE=trian" in res.stderr
