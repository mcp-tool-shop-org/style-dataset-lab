"""The lane 3 CPU stub is an install-path stub: its acceptance ends at the import gate.

The local walk of 2026-11-06 showed that ai-toolkit's run.py cannot run on a CPU VM (it calls
torch.cuda.current_device() at import) and that the synthetic job has no model. The CPU stub now
stops after the import gate, writes TRAIN_SKIPPED and records train=skipped_cpu_stub; the training
step stays in the remote script behind LANE3_MODE=train, for a GPU rung designed later.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
LAUNCHER = COLAB_DIR / "launch_lane3_stub.sh"
WINDOW_SH = COLAB_DIR / "colab_window.sh"
sys.path.insert(0, str(REPO_ROOT / "tests" / "colab" / "fixtures"))

import fake_colab as fc  # noqa: E402

SKIP_LINE = "TRAIN_SKIPPED: cpu stub; training needs a GPU rung"


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "bash executable not found"
    return found


def _p(p: Path) -> str:
    return fc._to_posix(p)


def _mixed(p: Path) -> str:
    """A path both bash and the host Python read the same way (C:/... on Windows)."""
    return p.resolve().as_posix()


def _run(cmd: list[str], env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, check=False)


def _emit(tmp_path: Path) -> str:
    emitted = tmp_path / "remote_lane3_stub.sh"
    em = _run([_bash(), _p(LAUNCHER), "--emit-remote-script", _p(emitted)])
    assert em.returncode == 0, em.stderr
    return emitted.read_text(encoding="utf-8")


def _extract_block(script_text: str, name: str) -> str:
    lines = script_text.split("\n")
    start = lines.index(f"# >>> {name}")
    end = lines.index(f"# <<< {name}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


def _fake_nvidia_smi(bin_dir: Path, gpu: bool) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "#!/usr/bin/env bash\necho 'GPU 0: NVIDIA A100-SXM4-40GB (UUID: GPU-fake)'\n"
        if gpu
        else "#!/usr/bin/env bash\necho 'NVIDIA-SMI has failed because it could not communicate with the NVIDIA driver.' >&2\nexit 9\n"
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
    block = _extract_block(_emit(tmp_path), "sdlab-lane3-mode")
    bin_dir = tmp_path / "vm-bin"
    _fake_nvidia_smi(bin_dir, gpu)
    gate = tmp_path / "mode_gate.sh"
    gate.write_text(
        "set -euo pipefail\n" + block + 'echo "MODE_OK ${LANE3_MODE} cvd=[${CUDA_VISIBLE_DEVICES-unset}]"\n',
        encoding="utf-8",
        newline="\n",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("LANE3_") and k != "CUDA_VISIBLE_DEVICES"}
    if mode is not None:
        env["LANE3_MODE"] = mode
    if model is not None:
        env["LANE3_MODEL_NAME_OR_PATH"] = model
    env.update(extra or {})
    return _run([_bash(), "-c", f'export PATH="{_p(bin_dir)}:$PATH"; bash "{_p(gate)}"'], env)


# --- the remote mode gate ----------------------------------------------------------------------


def test_install_mode_is_the_default_and_hides_the_gpu(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, None, gpu=True, model=None)
    assert res.returncode == 0, res.stderr
    assert "MODE_OK install cvd=[]" in res.stdout


def test_train_mode_refuses_on_a_cpu_vm(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, "train", gpu=False, model="some/model")
    assert res.returncode == 1
    assert "REFUSED: TRAIN_REQUIRES_GPU:" in res.stderr
    assert "MODE_OK" not in res.stdout


@pytest.mark.parametrize("model", [None, "", 'bad"model\nmodel:', "two words"])
def test_train_mode_refuses_without_a_model(tmp_path: Path, model: str | None) -> None:
    res = _run_mode_gate(tmp_path, "train", gpu=True, model=model)
    assert res.returncode == 1
    assert "REFUSED: TRAIN_MODEL_REQUIRED:" in res.stderr
    assert "MODE_OK" not in res.stdout


def test_train_mode_with_gpu_and_model_passes_the_gate(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, "train", gpu=True, model="org/model-name_v1.0", extra=RUNG_ENV)
    assert res.returncode == 0, res.stderr
    assert "MODE_OK train cvd=[unset]" in res.stdout


@pytest.mark.parametrize(
    ("var", "value", "code"),
    [
        ("LANE3_MODEL_REVISION", None, "TRAIN_MODEL_REVISION_REQUIRED"),
        ("LANE3_MODEL_REVISION", "main", "TRAIN_MODEL_REVISION_REQUIRED"),
        ("LANE3_HOST_RAM_REQUIRED_GIB", None, "HOST_RAM_THRESHOLD_MISSING"),
        ("LANE3_HOST_RAM_REQUIRED_GIB", "0", "HOST_RAM_THRESHOLD_MISSING"),
        ("LANE3_HOST_RAM_REQUIRED_GIB", "lots", "HOST_RAM_THRESHOLD_MISSING"),
        ("LANE3_DOWNLOAD_MAX_SECONDS", None, "DOWNLOAD_LIMIT_MISSING"),
        ("LANE3_DOWNLOAD_MAX_SECONDS", "0", "DOWNLOAD_LIMIT_MISSING"),
    ],
)
def test_train_mode_refuses_each_missing_rung_value(tmp_path: Path, var: str, value: str | None, code: str) -> None:
    extra = dict(RUNG_ENV)
    if value is None:
        del extra[var]
    else:
        extra[var] = value
    res = _run_mode_gate(tmp_path, "train", gpu=True, model="Qwen/Qwen-Image", extra=extra)
    assert res.returncode == 1
    assert f"REFUSED: {code}:" in res.stderr
    assert "MODE_OK" not in res.stdout


def test_unknown_mode_is_refused(tmp_path: Path) -> None:
    res = _run_mode_gate(tmp_path, "trian", gpu=True, model="m")
    assert res.returncode == 1
    assert "REFUSED: LANE3_MODE_INVALID: LANE3_MODE=trian" in res.stderr


# --- the train-or-skip step --------------------------------------------------------------------


def _vm_with_venv(vm: Path, run_py_rc: int, write_checkpoint: bool) -> None:
    (vm / "lane3_out" / "checkpoints").mkdir(parents=True)
    (vm / "lane3_out" / "setup.log").write_text("VENV_IMPORT torch ...\nSENTENCEPIECE_OK 0.2.1\n", encoding="utf-8")
    venv_bin = vm / "venv-lane3" / "bin"
    venv_bin.mkdir(parents=True)
    ckpt = vm / "lane3_out" / "checkpoints" / "synth_lora_000000001.safetensors"
    ckpt_line = f"printf 'SAFETENSORS' > '{_mixed(ckpt)}'\n" if write_checkpoint else ""
    (venv_bin / "python").write_text(
        "#!/usr/bin/env bash\n"
        'case "${1:-}" in\n'
        "  *run.py)\n"
        "    echo 'trainer line one'\n"
        "    echo 'RuntimeError: Found no NVIDIA driver on your system.'\n"
        f"    {ckpt_line}"
        f"    exit {run_py_rc}\n"
        "    ;;\n"
        "esac\n"
        f'exec "{_mixed(Path(fc._resolve_python()))}" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    (venv_bin / "python").chmod(0o755)


def _run_train_or_skip(tmp_path: Path, mode: str | None, model: str | None, run_py_rc: int = 0, write_checkpoint: bool = True) -> tuple[subprocess.CompletedProcess[str], Path]:
    block = _extract_block(_emit(tmp_path), "sdlab-train-or-skip")
    vm = tmp_path / "vm"
    _vm_with_venv(vm, run_py_rc, write_checkpoint)
    step = tmp_path / "train_or_skip.sh"
    step.write_text(
        "set -euo pipefail\n" + block.replace("/content", _mixed(vm))
        + 'echo "STATE ${LANE3_TRAIN_STATE} ckpt=[${CHECKPOINT_PATH}]"\n',
        encoding="utf-8",
        newline="\n",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("LANE3_")}
    if mode is not None:
        env["LANE3_MODE"] = mode
    if model is not None:
        env["LANE3_MODEL_NAME_OR_PATH"] = model
    return _run([_bash(), _p(step)], env), vm


def test_install_mode_skips_training_and_says_so(tmp_path: Path) -> None:
    res, vm = _run_train_or_skip(tmp_path, None, None)
    assert res.returncode == 0, res.stderr
    assert "STATE skipped_cpu_stub ckpt=[]" in res.stdout
    assert SKIP_LINE in (vm / "lane3_out" / "setup.log").read_text(encoding="utf-8")
    # Nothing of the training step ran: no synthetic package, job, train log or phase change.
    for name in ("synth_pkg", "synth_job.yaml", "train.log", "phase.txt"):
        assert not (vm / "lane3_out" / name).exists(), name




# --- the kit: --train is refused before any colab call -----------------------------------------


@pytest.mark.parametrize(
    ("card_args", "code"),
    [([], "TRAIN_REQUIRES_GPU"), (["--card", "CPU"], "TRAIN_REQUIRES_GPU"), (["--card", "A100"], "TRAIN_MODEL_REQUIRED")],
)
def test_kit_train_flag_is_refused_before_any_colab_call(tmp_path: Path, card_args: list[str], code: str) -> None:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    out_dir = tmp_path / "out"
    res = _run([_bash(), _p(LAUNCHER), "--train", *card_args, "--out-dir", _p(out_dir), "--session", "sdlab-l3-train"], env)
    assert res.returncode == 2
    assert f"REFUSED: {code}:" in res.stderr
    assert not (state_dir / "calls.log").exists()


def test_kit_emit_with_train_needs_the_rung_values(tmp_path: Path) -> None:
    res = _run([_bash(), _p(LAUNCHER), "--emit-remote-script", _p(tmp_path / "r.sh"), "--train"])
    assert res.returncode == 2
    assert "REFUSED: TRAIN_MODEL_REQUIRED:" in res.stderr
    assert not (tmp_path / "r.sh").exists()


def test_kit_passes_a_train_mode_only_with_train(tmp_path: Path) -> None:
    plain = tmp_path / "plain.sh"
    assert _run([_bash(), _p(LAUNCHER), "--emit-remote-script", _p(plain)]).returncode == 0
    assert "LANE3_" not in (tmp_path / "plain.sh.env").read_text(encoding="utf-8")
    rung = tmp_path / "rung.sh"
    res = _run([_bash(), _p(LAUNCHER), "--emit-remote-script", _p(rung), "--train", "--model", "Qwen/Qwen-Image",
                "--model-revision", RUNG_ENV["LANE3_MODEL_REVISION"], "--host-ram-required-gib", "96.5",
                "--download-max-seconds", "1800"])
    assert res.returncode == 0, res.stderr
    env_lines = (tmp_path / "rung.sh.env").read_text(encoding="utf-8").splitlines()
    for line in ("LANE3_MODE=train", "LANE3_MODEL_NAME_OR_PATH=Qwen/Qwen-Image",
                 f"LANE3_MODEL_REVISION={RUNG_ENV['LANE3_MODEL_REVISION']}", "LANE3_HOST_RAM_REQUIRED_GIB=96.5",
                 "LANE3_DOWNLOAD_MAX_SECONDS=1800", "LANE3_DISK_REQUIRED_GIB=75", "LANE3_GPU_SMOKE_SECONDS=5",
                 "LANE3_DOWNLOAD_PROBE_SECONDS=60", "LANE3_DOWNLOAD_PROBE_BYTES=2147483648"):
        assert line in env_lines, line
    # The emitted script is the same file either way: train mode is the environment, not the script.
    assert rung.read_text(encoding="utf-8") == plain.read_text(encoding="utf-8")


def test_kit_train_options_need_train(tmp_path: Path) -> None:
    res = _run([_bash(), _p(LAUNCHER), "--emit-remote-script", _p(tmp_path / "r.sh"), "--model", "a/b"])
    assert res.returncode == 2
    assert "REFUSED: TRAIN_OPTION_WITHOUT_TRAIN:" in res.stderr


# --- end to end against the fake: success ends at the import gate ------------------------------


def _bundle_members(bundle: Path) -> dict[str, str]:
    with tarfile.open(bundle, "r:gz") as tf:
        return {
            Path(m.name).name: tf.extractfile(m).read().decode("utf-8")  # type: ignore[union-attr]
            for m in tf.getmembers()
            if m.isfile()
        }


def test_cpu_stub_success_ends_at_the_import_gate_with_the_bundle(tmp_path: Path) -> None:
    _, state_dir, env = fc.make_fake_colab_env(tmp_path)
    env["GUARD_POLL_INTERVAL_S"] = "0.2"
    # A rig-side LANE3_MODE never reaches the VM (colab exec passes only --env values).
    env["LANE3_MODE"] = "train"
    out_dir = tmp_path / "out"
    res = _run([_bash(), _p(LAUNCHER), "--out-dir", _p(out_dir), "--session", "sdlab-l3-install"], env, timeout=120)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    win = json.loads((out_dir / "window.json").read_text(encoding="utf-8"))
    assert win["status"] == "ok" and win["refusal_code"] is None
    assert win["train"] == "skipped_cpu_stub"
    assert win["trained"] is False
    assert win["lane3_mode"] == "install"
    assert win["checkpoint_path"] is None
    assert "lane3_stub_bundle.tar.gz" in win["downloaded_files"]
    outcome = json.loads((out_dir / "outcome.draft.json").read_text(encoding="utf-8"))
    assert outcome["status"] == "ok" and outcome["train"] == "skipped_cpu_stub" and outcome["trained"] is False

    members = _bundle_members(out_dir / "lane3_stub_bundle.tar.gz")
    for name in ("setup.log", "wheels.log", "sentencepiece.txt", "python_identity.json", "vm_window.json"):
        assert name in members, name
    assert SKIP_LINE in members["setup.log"]
    assert "train.log" not in members and "synth_job.yaml" not in members
    vitals = (out_dir / "vitals.log").read_text(encoding="utf-8")
    assert "LANE3_MODE=install CUDA_VISIBLE_DEVICES=" in vitals
    assert "ai-toolkit/run.py" not in vitals


# --- the window writer: skipped is never a trained result --------------------------------------


def _write_train_window(tmp_path: Path, vm_train: object, exit_code: int, lane: str = "train") -> tuple[dict, dict]:
    out_dir = tmp_path / f"w_{lane}_{vm_train}_{exit_code}".replace(" ", "_")
    out_dir.mkdir()
    rec = json.dumps({"python": "3.12.15", "train": vm_train, "trained": True}).encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("./vm_window.json")
        info.size = len(rec)
        tf.addfile(info, io.BytesIO(rec))
    (out_dir / "lane3_stub_bundle.tar.gz").write_bytes(buf.getvalue())
    res = _run(
        [
            _bash(),
            "-c",
            f'source "{_p(WINDOW_SH)}"\n'
            f'colab_write_window_and_outcome "{_p(Path(sys.executable))}" "{_p(out_dir)}" {lane} s1 CPU-high-mem '
            f"0.05 900 60 0.01 2026-11-06T00:00:00Z 2026-11-06T00:01:00Z {exit_code} '{{}}'",
        ],
        os.environ.copy(),
    )
    assert res.returncode == 0, res.stderr
    return (
        json.loads((out_dir / "window.json").read_text(encoding="utf-8")),
        json.loads((out_dir / "outcome.draft.json").read_text(encoding="utf-8")),
    )


@pytest.mark.parametrize(
    ("vm_train", "exit_code", "train", "trained"),
    [
        ("skipped_cpu_stub", 0, "skipped_cpu_stub", False),
        ("trained", 0, "trained", True),
        ("trained", 1, "trained", False),
        ("yes", 0, None, False),
        (None, 0, None, False),
    ],
)
def test_window_writer_reads_train_state_strictly(tmp_path: Path, vm_train: object, exit_code: int, train: object, trained: bool) -> None:
    win, outcome = _write_train_window(tmp_path, vm_train, exit_code)
    assert win["train"] == train and win["trained"] is trained
    assert outcome["train"] == train and outcome["trained"] is trained


def test_window_writer_adds_no_train_fields_to_other_lanes(tmp_path: Path) -> None:
    _, outcome = _write_train_window(tmp_path, "skipped_cpu_stub", 0, lane="render")
    assert "train" not in outcome and "trained" not in outcome
