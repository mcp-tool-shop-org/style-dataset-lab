"""Synthetic-fixture unit and CLI tests for scripts/checkpoint-eval/checkpoint_eval.py."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = REPO_ROOT / "scripts" / "checkpoint-eval" / "checkpoint_eval.py"

spec = importlib.util.spec_from_file_location("checkpoint_eval", MOD_PATH)
assert spec is not None and spec.loader is not None
ce = importlib.util.module_from_spec(spec)
sys.modules["checkpoint_eval"] = ce
spec.loader.exec_module(ce)


def _write_tiny_ppm(path: Path, rgb: tuple[int, int, int] = (120, 80, 40), size: int = 8) -> None:
    """Write a tiny valid binary PPM (P6) image with deterministic pixel bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"P6\n{size} {size}\n255\n".encode("ascii")
    pixel = bytes([rgb[0] & 0xFF, rgb[1] & 0xFF, rgb[2] & 0xFF])
    path.write_bytes(header + pixel * (size * size))


def _write_synthetic_safetensors(path: Path, tensors: dict[str, tuple[str, list[int], bytes]]) -> None:
    """Write a minimal valid `.safetensors` file from `(dtype, shape, raw_bytes)` entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header: dict[str, Any] = {}
    body_chunks: list[bytes] = []
    offset = 0
    for name, (dtype, shape, raw) in tensors.items():
        end = offset + len(raw)
        header[name] = {
            "dtype": dtype,
            "shape": list(shape),
            "data_offsets": [offset, end],
        }
        body_chunks.append(raw)
        offset = end
    header_bytes = json.dumps(header).encode("utf-8")
    pad = (8 - (len(header_bytes) % 8)) % 8
    header_bytes += b" " * pad
    path.write_bytes(struct.pack("<Q", len(header_bytes)) + header_bytes + b"".join(body_chunks))


def _pack_f32_matrix(rows: list[list[float]]) -> tuple[str, list[int], bytes]:
    m = len(rows)
    n = len(rows[0]) if m else 0
    flat = [float(x) for r in rows for x in r]
    return "F32", [m, n], struct.pack(f"<{len(flat)}f", *flat)


def _pack_f16_matrix(rows: list[list[float]]) -> tuple[str, list[int], bytes]:
    m = len(rows)
    n = len(rows[0]) if m else 0
    flat = [float(x) for r in rows for x in r]
    return "F16", [m, n], struct.pack(f"<{len(flat)}e", *flat)


def _make_synthetic_fixture_tree(tmp_path: Path) -> dict[str, Path]:
    """Create a synthetic training dir, config.yaml, and run A / run B sample dirs."""
    train_dir = tmp_path / "train_set"
    for i in range(6):
        _write_tiny_ppm(train_dir / f"exemplar_{i:02d}.ppm", (20 * i + 10, 40, 100 + 15 * i))

    prompts = [
        "synthstyle style, an android scout in a ruined courtyard",
        "synthstyle style, an android mechanic holding a wrench",
        "synthstyle style, an android courier in heavy rain",
        "synthstyle style, an android guard with a brass visor",
        "synthstyle style, an android diver near a rusted hatch",
        "a plain wooden chair on a white background",
    ]
    cfg_a_path = tmp_path / "config_a.yaml"
    cfg_b_path = tmp_path / "config_b.yaml"
    cfg_lines = [
        "job: extension",
        "config:",
        "  name: synthstyle_style_v1",
        "  process:",
        "    - type: sd_trainer",
        "      sample:",
        "        seed: 42",
        "        walk_seed: true",
        "        prompts:",
    ]
    for p in prompts:
        cfg_lines.append(f'          - "{p}"')
    cfg_text = "\n".join(cfg_lines) + "\n"
    cfg_a_path.write_text(cfg_text, encoding="utf-8")
    cfg_b_path.write_text(cfg_text, encoding="utf-8")

    run_a_dir = tmp_path / "run_a" / "samples"
    run_b_dir = tmp_path / "run_b" / "samples"
    for step in (0, 250, 500):
        for pidx in range(6):
            ts_a = 1780000000000 + step * 100 + pidx
            ts_b = 1790000000000 + step * 100 + pidx
            _write_tiny_ppm(
                run_a_dir / f"{ts_a}__{step:09d}_{pidx}.ppm",
                (10 + step // 10 + pidx * 7, 30 + pidx * 11, 50 + step // 20),
            )
            _write_tiny_ppm(
                run_b_dir / f"{ts_b}__{step:09d}_{pidx}.ppm",
                (12 + step // 10 + pidx * 7, 32 + pidx * 11, 55 + step // 20),
            )

    return {
        "train_dir": train_dir,
        "cfg_a": cfg_a_path,
        "cfg_b": cfg_b_path,
        "run_a": run_a_dir,
        "run_b": run_b_dir,
    }


def test_pairing_by_name_and_refusals(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    paired = ce.pair_run_samples(fx["run_a"], num_prompts=6, requested_steps=[0, 250, 500], run_label="A")
    assert list(paired.keys()) == [0, 250, 500]
    for step in (0, 250, 500):
        assert list(paired[step].keys()) == [0, 1, 2, 3, 4, 5]
        assert paired[step][3].name.endswith(f"__{step:09d}_3.ppm")

    # Missing directory refuses with RUN_DIR_NOT_FOUND
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.pair_run_samples(tmp_path / "nonexistent", num_prompts=6)
    assert exc_info.value.code == "RUN_DIR_NOT_FOUND"

    # Missing step refuses with PAIRING_MISMATCH
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.pair_run_samples(fx["run_a"], num_prompts=6, requested_steps=[0, 250, 750])
    assert exc_info.value.code == "PAIRING_MISMATCH"
    assert "missing step 750" in exc_info.value.why

    # Duplicate (step, prompt_idx) refuses with PAIRING_MISMATCH
    _write_tiny_ppm(fx["run_a"] / "9999999999999__000000250_2.ppm", (1, 2, 3))
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.pair_run_samples(fx["run_a"], num_prompts=6, requested_steps=[0, 250, 500])
    assert exc_info.value.code == "PAIRING_MISMATCH"
    assert "duplicate sample" in exc_info.value.why
    (fx["run_a"] / "9999999999999__000000250_2.ppm").unlink()

    # Non-9-digit step filenames must not match SAMPLE_FILENAME_RE
    assert ce.SAMPLE_FILENAME_RE.match("1780000000000__00250_0.png") is None
    assert ce.SAMPLE_FILENAME_RE.match("1780000000000__0000000250_0.png") is None
    assert ce.SAMPLE_FILENAME_RE.match("1780000000000__000000250_0.png") is not None

    # Out-of-range prompt index refuses with PAIRING_MISMATCH
    _write_tiny_ppm(fx["run_a"] / "9999999999999__000000250_9.ppm", (1, 2, 3))
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.pair_run_samples(fx["run_a"], num_prompts=6)
    assert exc_info.value.code == "PAIRING_MISMATCH"
    assert "outside 0..5" in exc_info.value.why
    (fx["run_a"] / "9999999999999__000000250_9.ppm").unlink()

    # Missing prompt index at a step refuses with PAIRING_MISMATCH
    removed = next(fx["run_a"].glob("*__000000500_4.ppm"))
    removed.unlink()
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.pair_run_samples(fx["run_a"], num_prompts=6, requested_steps=[0, 250, 500])
    assert exc_info.value.code == "PAIRING_MISMATCH"
    assert "missing prompt indices [4]" in exc_info.value.why


def test_seed_and_prompt_mismatch_refusal(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    cfg_a = ce.load_prompts_config(fx["cfg_a"])
    assert cfg_a["trigger_words"] == ["synthstyle style"]
    assert cfg_a["content_prompts"][0] == "an android scout in a ruined courtyard"
    assert cfg_a["content_prompts"][5] == "a plain wooden chair on a white background"
    assert cfg_a["ood_prompt_indices"] == [5]

    # Seed mismatch config
    cfg_bad_seed = tmp_path / "config_bad_seed.json"
    cfg_bad_seed.write_text(
        json.dumps({"seed": 99, "walk_seed": True, "prompts": cfg_a["prompts"]}),
        encoding="utf-8",
    )
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.verify_configs_match(cfg_a, ce.load_prompts_config(cfg_bad_seed))
    assert exc_info.value.code == "SEED_MISMATCH"

    # walk_seed mismatch config
    cfg_bad_walk = tmp_path / "config_bad_walk.json"
    cfg_bad_walk.write_text(
        json.dumps({"seed": 42, "walk_seed": False, "prompts": cfg_a["prompts"]}),
        encoding="utf-8",
    )
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.verify_configs_match(cfg_a, ce.load_prompts_config(cfg_bad_walk))
    assert exc_info.value.code == "SEED_MISMATCH"

    # Prompt list mismatch config
    cfg_bad_prompts = tmp_path / "config_bad_prompts.json"
    altered_prompts = list(cfg_a["prompts"])
    altered_prompts[2] = "synthstyle style, a completely different prompt"
    cfg_bad_prompts.write_text(
        json.dumps({"seed": 42, "walk_seed": True, "prompts": altered_prompts}),
        encoding="utf-8",
    )
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.verify_configs_match(cfg_a, ce.load_prompts_config(cfg_bad_prompts))
    assert exc_info.value.code == "PROMPT_MISMATCH"


def test_paired_statistics_against_hand_computed_values() -> None:
    # Hand-computed paired difference series (n = 6):
    # diffs = [0.04, 0.02, 0.06, 0.01, 0.05, 0.03]
    # mean = 0.21 / 6 = 0.035
    # sum((d - 0.035)^2) = 0.00175 -> var (ddof=1) = 0.00035 -> sd = sqrt(0.00035) = 0.0187082869
    # se = sd / sqrt(6) = sqrt(0.00035 / 6) = 0.0076376262
    # t_stat = 0.035 / 0.0076376262 = 4.582575695
    # Wilcoxon: all 6 diffs > 0, ranks 1..6 -> W+ = 21, W- = 0, stat = 0,
    # p_greater = 1/64 = 0.015625, p_two_sided = 2/64 = 0.03125
    a = [0.50, 0.50, 0.50, 0.50, 0.50, 0.50]
    b = [0.54, 0.52, 0.56, 0.51, 0.55, 0.53]
    stats6 = ce.compute_paired_stats(b, a)
    assert stats6["n"] == 6
    assert math.isclose(stats6["mean"], 0.035, abs_tol=1e-6)
    assert math.isclose(stats6["sd"], math.sqrt(0.00035), abs_tol=1e-6)
    assert math.isclose(stats6["se"], math.sqrt(0.00035 / 6.0), abs_tol=1e-6)
    assert math.isclose(float(stats6["t_stat"]), 4.582576, abs_tol=1e-5)
    # df=5: P(T >= 4.5825757) = 0.00296677, two-sided = 0.00593354
    assert math.isclose(stats6["t_p_greater"], 0.002967, abs_tol=5e-6)
    assert math.isclose(stats6["t_p_two_sided"], 0.005934, abs_tol=1e-5)
    assert stats6["wilcoxon"]["w_plus"] == 21.0
    assert stats6["wilcoxon"]["w_minus"] == 0.0
    assert stats6["wilcoxon"]["statistic"] == 0.0
    assert math.isclose(stats6["wilcoxon"]["p_greater"], 1.0 / 64.0, abs_tol=1e-8)
    assert math.isclose(stats6["wilcoxon"]["p_two_sided"], 2.0 / 64.0, abs_tol=1e-8)

    # Pooled n = 12 all-positive diffs -> smallest two-sided Wilcoxon p = 2 / 4096 = 0.00048828
    a12 = [0.40] * 12
    b12 = [0.40 + 0.005 * (i + 1) for i in range(12)]
    stats12 = ce.compute_paired_stats(b12, a12)
    assert stats12["n"] == 12
    assert stats12["wilcoxon"]["w_plus"] == 78.0
    assert stats12["wilcoxon"]["w_minus"] == 0.0
    assert math.isclose(stats12["wilcoxon"]["p_two_sided"], 2.0 / 4096.0, abs_tol=1e-7)

    # Mismatched length refuses with PAIRING_MISMATCH
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.compute_paired_stats([1.0, 2.0], [1.0])
    assert exc_info.value.code == "PAIRING_MISMATCH"


def test_stable_rank_on_known_matrices_and_safetensors(tmp_path: Path) -> None:
    # 1. Rank-1 outer product: B = [[3, 0], [4, 0], [0, 0]], A = [[2, 0, 0], [0, 0, 0]]
    # ΔW has single non-zero singular value 5 * 2 = 10 -> frob = 10, top_sv = 10, stable_rank = 1.0
    b_r1 = [[3.0, 0.0], [4.0, 0.0], [0.0, 0.0]]
    a_r1 = [[2.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    res_r1 = ce.compute_stable_rank_from_lora_pair(b_r1, a_r1)
    assert math.isclose(res_r1["top_singular_value"], 10.0, abs_tol=1e-6)
    assert math.isclose(res_r1["frobenius_norm"], 10.0, abs_tol=1e-6)
    assert math.isclose(res_r1["stable_rank"], 1.0, abs_tol=1e-6)

    # 2. Orthogonal rank-4 matrix with singular values [4, 2, 2, 1]:
    # ||ΔW||_F^2 = 16 + 4 + 4 + 1 = 25, ||ΔW||_2^2 = 16 -> stable_rank = 25 / 16 = 1.5625
    b_diag = [
        [4.0, 0.0, 0.0, 0.0],
        [0.0, 2.0, 0.0, 0.0],
        [0.0, 0.0, 2.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 0.0, 0.0],
    ]
    a_id = [
        [1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0, 0.0],
    ]
    res_diag = ce.compute_stable_rank_from_lora_pair(b_diag, a_id)
    assert math.isclose(res_diag["top_singular_value"], 4.0, abs_tol=1e-6)
    assert math.isclose(res_diag["frobenius_norm"], 5.0, abs_tol=1e-6)
    assert math.isclose(res_diag["stable_rank"], 1.5625, abs_tol=1e-6)
    assert [round(s, 4) for s in res_diag["singular_values"]] == [4.0, 2.0, 2.0, 1.0]

    # 3. Zero matrix -> stable_rank = 0.0
    b_zero = [[0.0, 0.0], [0.0, 0.0]]
    a_zero = [[0.0, 0.0], [0.0, 0.0]]
    res_zero = ce.compute_stable_rank_from_lora_pair(b_zero, a_zero)
    assert res_zero["stable_rank"] == 0.0
    assert res_zero["frobenius_norm"] == 0.0

    # 4. Synthetic safetensors pairwise read (ckpt 1 vs ckpt 2 where ckpt 2 scales B by 2.0)
    ckpt1 = tmp_path / "lora_step1750.safetensors"
    ckpt2 = tmp_path / "lora_step2000.safetensors"
    b_scaled = [[2.0 * x for x in row] for row in b_diag]
    _write_synthetic_safetensors(
        ckpt1,
        {
            "diffusion_model.transformer_blocks.0.attn.to_q.lora_B.weight": _pack_f32_matrix(b_diag),
            "diffusion_model.transformer_blocks.0.attn.to_q.lora_A.weight": _pack_f32_matrix(a_id),
            "diffusion_model.transformer_blocks.0.img_mlp.net.lora_B.weight": _pack_f16_matrix(b_r1),
            "diffusion_model.transformer_blocks.0.img_mlp.net.lora_A.weight": _pack_f16_matrix(a_r1),
        },
    )
    _write_synthetic_safetensors(
        ckpt2,
        {
            "diffusion_model.transformer_blocks.0.attn.to_q.lora_B.weight": _pack_f32_matrix(b_scaled),
            "diffusion_model.transformer_blocks.0.attn.to_q.lora_A.weight": _pack_f32_matrix(a_id),
            "diffusion_model.transformer_blocks.0.img_mlp.net.lora_B.weight": _pack_f16_matrix(b_r1),
            "diffusion_model.transformer_blocks.0.img_mlp.net.lora_A.weight": _pack_f16_matrix(a_r1),
        },
    )
    ws = ce.read_safetensors_weight_space([ckpt1, ckpt2])
    assert "lora_step1750.safetensors" in ws["checkpoints"]
    assert "lora_step2000.safetensors" in ws["checkpoints"]
    cmp_layers = ws["pairwise_comparison"]["layers"]
    q_cmp = cmp_layers["diffusion_model.transformer_blocks.0.attn.to_q"]
    assert math.isclose(q_cmp["norm_ratio"], 2.0, abs_tol=1e-5)
    assert math.isclose(q_cmp["cosine"], 1.0, abs_tol=1e-5)
    assert math.isclose(q_cmp["delta_stable_rank"], 0.0, abs_tol=1e-5)


def test_corridors_generation_and_tamper_refusal_end_to_end(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"

    # 1. Run A only: writes summary.json, corridors.md, and training cache
    rc_a = ce.main(
        [
            "--training-dir",
            str(fx["train_dir"]),
            "--run",
            f"A={fx['run_a']}",
            "--steps",
            "0,250,500",
            "--prompts",
            str(fx["cfg_a"]),
            "--out",
            str(out_a),
            "--fake-embedder",
        ]
    )
    assert rc_a == 0
    corridors_file = out_a / "corridors.md"
    summary_a_file = out_a / "summary.json"
    assert corridors_file.is_file()
    assert summary_a_file.is_file()
    summary_a = json.loads(summary_a_file.read_text(encoding="utf-8"))
    assert summary_a["training_set"]["cache_hit"] is False

    # Verify corridors.md carries its own sha256 and creation time and passes verification
    verified = ce.read_and_verify_corridors(corridors_file, summary_a["corridors"]["file_sha256"])
    assert verified["body_sha256"] == summary_a["corridors"]["body_sha256"]
    assert verified["file_sha256"] == summary_a["corridors"]["file_sha256"]

    # 2. Score Run B against untouched corridors.md (and re-use out_a so training embedding cache hits)
    rc_b = ce.main(
        [
            "--training-dir",
            str(fx["train_dir"]),
            "--run",
            f"A={fx['run_a']}",
            "--run",
            f"B={fx['run_b']}",
            "--steps",
            "0,250,500",
            "--prompts",
            str(fx["cfg_a"]),
            "--prompts-b",
            str(fx["cfg_b"]),
            "--corridors",
            str(corridors_file),
            "--corridors-sha",
            summary_a["corridors"]["file_sha256"],
            "--out",
            str(out_a),
            "--fake-embedder",
        ]
    )
    assert rc_b == 0
    summary_b_file = out_a / "summary-B-run_b.json"
    assert summary_b_file.is_file()
    # Run A's summary.json must never be overwritten by Run B
    assert json.loads(summary_a_file.read_text(encoding="utf-8")) == summary_a
    summary_b = json.loads(summary_b_file.read_text(encoding="utf-8"))
    assert summary_b["training_set"]["cache_hit"] is True
    assert summary_b["b_vs_a"]["pooled_n"] == 12
    assert summary_b["corridors_verdict"]["overall"] in ("promote", "borderline", "kill")

    # 3. Tamper with a threshold in corridors.md -> must refuse with CORRIDORS_TAMPERED (exit 2)
    orig_text = corridors_file.read_text(encoding="utf-8")
    tampered_text = orig_text.replace("0.85", "0.80", 1)
    assert tampered_text != orig_text
    corridors_file.write_text(tampered_text, encoding="utf-8")

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.read_and_verify_corridors(corridors_file, summary_a["corridors"]["file_sha256"])
    assert exc_info.value.code in ("CORRIDORS_TAMPERED", "CORRIDORS_SHA_MISMATCH")

    rc_tampered = ce.main(
        [
            "--training-dir",
            str(fx["train_dir"]),
            "--run",
            f"A={fx['run_a']}",
            "--run",
            f"B={fx['run_b']}",
            "--steps",
            "0,250,500",
            "--prompts",
            str(fx["cfg_a"]),
            "--prompts-b",
            str(fx["cfg_b"]),
            "--corridors",
            str(corridors_file),
            "--corridors-sha",
            summary_a["corridors"]["file_sha256"],
            "--out",
            str(tmp_path / "eval_tampered"),
            "--fake-embedder",
        ]
    )
    assert rc_tampered == 2

    # 4. Missing corridors.md when scoring Run B -> must refuse with CORRIDORS_MISSING
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.read_and_verify_corridors(tmp_path / "missing_corridors.md", summary_a["corridors"]["file_sha256"])
    assert exc_info.value.code == "CORRIDORS_MISSING"


def test_pure_stdlib_fallbacks_and_edge_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    # 1. Pure-stdlib YAML parser and safetensors/Jacobi SVD fallbacks when yaml/numpy/safetensors are absent
    real_import = builtins.__import__

    def _no_third_party_import(name: str, *args: object, **kwargs: object) -> object:
        if name in ("yaml", "numpy", "safetensors"):
            raise ImportError(f"simulated missing {name}")
        return real_import(name, *args, **kwargs)

    b_mat = [[3.0, 1.0], [1.0, 2.0], [0.5, -0.5]]
    a_mat = [[2.0, 0.5, -1.0], [0.0, 1.5, 0.5]]
    res_np = ce.compute_stable_rank_from_lora_pair(b_mat, a_mat)
    n1_np, n2_np, in_np = ce._lora_inner_product_and_norms(b_mat, a_mat, b_mat, a_mat)

    ckpt_f32_bf16 = tmp_path / "fallback.safetensors"
    bf16_raw = b"".join(struct.pack("<H", struct.unpack("<I", struct.pack("<f", v))[0] >> 16) for row in b_mat for v in row)
    _write_synthetic_safetensors(
        ckpt_f32_bf16,
        {
            "block0.sub0.lora_up.weight": ("BF16", [3, 2], bf16_raw),
            "block0.sub0.lora_down.weight": _pack_f32_matrix(a_mat),
            "flat_layer.lora_B.weight": _pack_f16_matrix(b_mat),
            "flat_layer.lora_A.weight": _pack_f16_matrix(a_mat),
            "vector_meta": ("F32", [2], struct.pack("<2f", 1.0, 2.0)),
        },
    )

    yaml_cfg_path = tmp_path / "minimal.yaml"
    yaml_cfg_path.write_text(
        "---\n"
        "# comment\n"
        'name: "synthstyle_v1"\n'
        "seed: 42\n"
        "walk_seed: true\n"
        "trigger_word: 'synthstyle style'\n"
        "prompts:\n"
        '  - "synthstyle style, prompt one\n'
        '    continued line"\n'
        "  - 'prompt two ood'\n"
        "after_prompts: done\n",
        encoding="utf-8",
    )

    with monkeypatch.context() as m:
        m.setattr(builtins, "__import__", _no_third_party_import)
        res_py = ce.compute_stable_rank_from_lora_pair(b_mat, a_mat)
        n1_py, n2_py, in_py = ce._lora_inner_product_and_norms(b_mat, a_mat, b_mat, a_mat)
        assert math.isclose(res_py["stable_rank"], res_np["stable_rank"], abs_tol=1e-5)
        assert math.isclose(res_py["frobenius_norm"], res_np["frobenius_norm"], abs_tol=1e-5)
        assert math.isclose(n1_py, n1_np, abs_tol=1e-5)
        assert math.isclose(n2_py, n2_np, abs_tol=1e-5)
        assert math.isclose(in_py, in_np, abs_tol=1e-5)

        ws_py = ce.read_safetensors_weight_space([ckpt_f32_bf16])
        assert ws_py["checkpoints"]["fallback.safetensors"]["overall"]["num_layers"] == 2

        parsed_yaml = ce.load_prompts_config(yaml_cfg_path)
        assert parsed_yaml["seed"] == 42
        assert parsed_yaml["walk_seed"] is True
        assert len(parsed_yaml["prompts"]) == 2
        assert "synthstyle style" in parsed_yaml["trigger_words"]

        # Invalid safetensors cases under pure-stdlib reader
        short_st = tmp_path / "short.safetensors"
        short_st.write_bytes(b"short")
        with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
            ce.read_safetensors_weight_space([short_st])
        assert exc_info.value.code == "INVALID_SAFETENSORS"

        bad_dtype_st = tmp_path / "bad_dtype.safetensors"
        _write_synthetic_safetensors(bad_dtype_st, {"k": ("I64", [1], b"\x00" * 8)})
        with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
            ce.read_safetensors_weight_space([bad_dtype_st])
        assert exc_info.value.code == "INVALID_SAFETENSORS"

        with pytest.raises(ValueError):
            ce.compute_stable_rank_from_lora_pair([[1.0, 2.0]], [[1.0]])

    # Also test incompatible shape with numpy active
    with pytest.raises(ValueError):
        ce.compute_stable_rank_from_lora_pair([[1.0, 2.0]], [[1.0]])

    # Checkpoint not found & no LoRA pairs
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.read_safetensors_weight_space([tmp_path / "does_not_exist.safetensors"])
    assert exc_info.value.code == "CHECKPOINT_NOT_FOUND"

    empty_st = tmp_path / "no_lora.safetensors"
    _write_synthetic_safetensors(empty_st, {"other.weight": _pack_f32_matrix([[1.0]])})
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.read_safetensors_weight_space([empty_st])
    assert exc_info.value.code == "INVALID_SAFETENSORS"


def test_math_verdict_and_cli_refusal_branches(tmp_path: Path) -> None:
    # Math helpers edge cases
    assert ce._mean([]) == 0.0
    assert ce._sample_sd([1.0]) == 0.0
    assert ce._median([]) == 0.0
    assert ce._median([1.0, 3.0, 2.0]) == 2.0
    assert ce._regularized_incomplete_beta(1.0, 1.0, 0.0) == 0.0
    assert ce._regularized_incomplete_beta(1.0, 1.0, 1.0) == 1.0
    assert ce._student_t_cdf(0.0, 0) == 0.5
    assert math.isnan(ce._student_t_cdf(float("nan"), 5))
    assert ce._student_t_cdf(float("inf"), 5) == 1.0
    assert ce._student_t_cdf(float("-inf"), 5) == 0.0
    assert ce._student_t_ppf(0.0, 5) == float("-inf")
    assert ce._student_t_ppf(1.0, 5) == float("inf")
    assert ce._student_t_ppf(0.5, 5) == 0.0
    assert ce._student_t_ppf(0.1, 5) < 0.0
    assert ce.compute_mde_one_sided(0.0, 12) == 0.0
    assert ce.compute_mde_one_sided(0.03, 1) == 0.0

    # Paired stats edge cases: all zeros, constant non-zero diff (se=0), ties in Wilcoxon
    s_zeros = ce.compute_paired_stats([1.0, 1.0], [1.0, 1.0])
    assert s_zeros["t_p_two_sided"] == 1.0
    assert s_zeros["wilcoxon"]["n_nonzero"] == 0
    s_const = ce.compute_paired_stats([2.0, 2.0, 2.0], [1.0, 1.0, 1.0])
    assert s_const["t_p_greater"] == 0.0
    s_ties = ce.compute_paired_stats([1.1, 1.1, 1.2], [1.0, 1.0, 1.0])
    assert s_ties["wilcoxon"]["w_plus"] == 6.0

    with pytest.raises(ce.CheckpointEvalRefusal):
        ce.compute_paired_stats([], [])

    # score_run_b_against_corridors all branches (promote, borderline, kill)
    fake_run_a = {
        "num_prompts": 6,
        "paired_diff_sd_estimate": {"value": 0.02, "estimator": "test"},
        "steps": {
            "250": {
                "csd_topk": {"mean": 0.50, "sd": 0.02},
                "delta_csd": {"mean": 0.15, "sd": 0.02},
                "delta_clip_t": {"mean": 0.00, "sd": 0.01},
                "delta_dino_nn": {"mean": 0.05, "sd": 0.01},
                "dreamsim_to_step0": {"mean": 0.30, "sd": 0.02},
            },
            "500": {
                "csd_topk": {"mean": 0.55, "sd": 0.02},
                "delta_csd": {"mean": 0.20, "sd": 0.02},
                "delta_clip_t": {"mean": 0.00, "sd": 0.01},
                "delta_dino_nn": {"mean": 0.06, "sd": 0.01},
                "dreamsim_to_step0": {"mean": 0.35, "sd": 0.02},
            },
        },
    }
    corridors_payload = ce.build_corridors_payload(fake_run_a)

    # All promote
    verdict_promote = ce.score_run_b_against_corridors(
        corridors_payload,
        {
            "steps": {
                "250": {
                    "delta_clip_t": {"mean": 0.01},
                    "delta_dino_nn": {"mean": 0.05},
                    "delta_csd": {"mean": 0.15},
                },
                "500": {
                    "delta_clip_t": {"mean": 0.01},
                    "delta_dino_nn": {"mean": 0.08},
                    "delta_csd": {"mean": 0.20},
                },
            }
        },
        {
            "velocity_ratio_rho_500": 0.95,
            "pooled_250_500": {"csd_topk": {"mean": 0.01}},
            "by_step": {
                "250": {"dreamsim_b_vs_a_mean": 0.10},
                "500": {"dreamsim_b_vs_a_mean": 0.12},
            },
        },
    )
    assert verdict_promote["overall"] == "promote"

    # All borderline
    verdict_borderline = ce.score_run_b_against_corridors(
        corridors_payload,
        {
            "steps": {
                "250": {
                    "delta_clip_t": {"mean": -0.018},
                    "delta_dino_nn": {"mean": 0.10},
                    "delta_csd": {"mean": 0.12},
                },
                "500": {
                    "delta_clip_t": {"mean": -0.018},
                    "delta_dino_nn": {"mean": 0.12},
                    "delta_csd": {"mean": 0.15},
                },
            }
        },
        {
            "velocity_ratio_rho_500": 0.78,
            "pooled_250_500": {"csd_topk": {"mean": -0.028}},
            "by_step": {
                "250": {"dreamsim_b_vs_a_mean": 0.20},
                "500": {"dreamsim_b_vs_a_mean": 0.21},
            },
        },
    )
    assert verdict_borderline["overall"] == "borderline"

    # All kill
    verdict_kill = ce.score_run_b_against_corridors(
        corridors_payload,
        {
            "steps": {
                "250": {
                    "delta_clip_t": {"mean": -0.040},
                    "delta_dino_nn": {"mean": 0.18},
                    "delta_csd": {"mean": 0.08},
                },
                "500": {
                    "delta_clip_t": {"mean": -0.040},
                    "delta_dino_nn": {"mean": 0.20},
                    "delta_csd": {"mean": 0.10},
                },
            }
        },
        {
            "velocity_ratio_rho_500": 0.50,
            "pooled_250_500": {"csd_topk": {"mean": -0.050}},
            "by_step": {
                "250": {"dreamsim_b_vs_a_mean": 0.28},
                "500": {"dreamsim_b_vs_a_mean": 0.30},
            },
        },
    )
    assert verdict_kill["overall"] == "kill"

    # CLI argument parser and refusal cases
    with pytest.raises(ce.CheckpointEvalRefusal):
        ce._parse_run_args(["invalid_no_equals"])
    with pytest.raises(ce.CheckpointEvalRefusal):
        ce._parse_run_args(["=empty_name"])
    assert ce._parse_steps_arg(None) is None
    assert ce._parse_steps_arg("0, 250, ,500") == [0, 250, 500]
    with pytest.raises(ce.CheckpointEvalRefusal):
        ce._parse_steps_arg("0,abc")

    # Config loading refusals
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.load_prompts_config(tmp_path / "missing_cfg.json")
    assert exc_info.value.code == "CONFIG_NOT_FOUND"

    bad_json = tmp_path / "list.json"
    bad_json.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.load_prompts_config(bad_json)
    assert exc_info.value.code == "INVALID_CONFIG"

    no_prompts_json = tmp_path / "no_prompts.json"
    no_prompts_json.write_text('{"seed": 42}', encoding="utf-8")
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.load_prompts_config(no_prompts_json)
    assert exc_info.value.code == "INVALID_CONFIG"


def test_corridors_reseal_bypass_refused(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    assert (
        ce.main(
            [
                "--training-dir",
                str(fx["train_dir"]),
                "--run",
                f"A={fx['run_a']}",
                "--steps",
                "0,250,500",
                "--prompts",
                str(fx["cfg_a"]),
                "--out",
                str(out_a),
                "--fake-embedder",
            ]
        )
        == 0
    )
    corridors_file = out_a / "corridors.md"
    summary_a = json.loads((out_a / "summary.json").read_text(encoding="utf-8"))
    orig_file_sha = summary_a["corridors"]["file_sha256"]

    # Edit a kill band to -99 and re-seal body_sha256 using _compute_corridors_body_sha256
    text = corridors_file.read_text(encoding="utf-8")
    edited = text.replace('"kill_below": -0.035', '"kill_below": -99.0', 1)
    assert edited != text
    m_sha = ce.re.search(r"^- \*\*body_sha256:\*\* `([0-9a-f]{64})`$", edited, flags=ce.re.MULTILINE)
    assert m_sha is not None
    with_placeholder = edited[: m_sha.start(1)] + ce.CORRIDORS_SHA_PLACEHOLDER + edited[m_sha.end(1) :]
    resealed_body_sha = ce._compute_corridors_body_sha256(with_placeholder)
    resealed_text = with_placeholder.replace(ce.CORRIDORS_SHA_PLACEHOLDER, resealed_body_sha, 1)
    corridors_file.write_text(resealed_text, encoding="utf-8", newline="\n")

    # Calling read_and_verify_corridors (both without sha and with original sha) must refuse
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.read_and_verify_corridors(corridors_file)
    assert exc_info.value.code in ("CORRIDORS_SHA_MISMATCH", "CORRIDORS_TAMPERED")

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info2:
        ce.read_and_verify_corridors(corridors_file, orig_file_sha)
    assert exc_info2.value.code in ("CORRIDORS_SHA_MISMATCH", "CORRIDORS_TAMPERED")


def test_corridors_overwrite_refused(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    args_a = [
        "--training-dir",
        str(fx["train_dir"]),
        "--run",
        f"A={fx['run_a']}",
        "--steps",
        "0,250,500",
        "--prompts",
        str(fx["cfg_a"]),
        "--out",
        str(out_a),
        "--fake-embedder",
    ]
    assert ce.main(args_a) == 0
    # Second run A to the same corridors path must refuse with CORRIDORS_EXISTS (rc == 2)
    assert ce.main(args_a) == 2
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"]},
            prompts_path=fx["cfg_a"],
            out_dir=out_a,
            steps=[0, 250, 500],
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "CORRIDORS_EXISTS"


def test_wrong_corridors_sha_refused(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    assert (
        ce.main(
            [
                "--training-dir",
                str(fx["train_dir"]),
                "--run",
                f"A={fx['run_a']}",
                "--steps",
                "0,250,500",
                "--prompts",
                str(fx["cfg_a"]),
                "--out",
                str(out_a),
                "--fake-embedder",
            ]
        )
        == 0
    )
    corridors_file = out_a / "corridors.md"

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_b"]},
            prompts_path=fx["cfg_a"],
            prompts_b_path=fx["cfg_b"],
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha="0" * 64,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "CORRIDORS_SHA_MISMATCH"


def _eval_runs_compat(**kwargs: Any) -> dict[str, Any]:
    import inspect

    sig = inspect.signature(ce.evaluate_runs)
    filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return ce.evaluate_runs(**filtered)


def test_swapped_run_a_dir_refused(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    summary_a = ce.evaluate_runs(
        training_dir=fx["train_dir"],
        run_dirs={"A": fx["run_a"]},
        prompts_path=fx["cfg_a"],
        out_dir=out_a,
        steps=[0, 250, 500],
        embedder=ce.FakeEmbedder(),
    )
    corridors_file = out_a / "corridors.md"
    corridors_sha = summary_a["corridors"]["file_sha256"]

    # Create a swapped run-A directory with identical filenames but altered pixel bytes
    swapped_a = tmp_path / "run_a_swapped" / "samples"
    for p in fx["run_a"].iterdir():
        _write_tiny_ppm(swapped_a / p.name, (200, 100, 50))

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        _eval_runs_compat(
            training_dir=fx["train_dir"],
            run_dirs={"A": swapped_a, "B": fx["run_b"]},
            prompts_path=fx["cfg_a"],
            prompts_b_path=fx["cfg_b"],
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "RUN_A_FINGERPRINT_MISMATCH"


def test_run_b_without_config_refused(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    summary_a = ce.evaluate_runs(
        training_dir=fx["train_dir"],
        run_dirs={"A": fx["run_a"]},
        prompts_path=fx["cfg_a"],
        out_dir=out_a,
        steps=[0, 250, 500],
        embedder=ce.FakeEmbedder(),
    )
    corridors_file = out_a / "corridors.md"
    corridors_sha = summary_a["corridors"]["file_sha256"]

    # No --prompts-b and no config.yaml/config.json inside run_b -> must refuse RUN_B_CONFIG_MISSING
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        _eval_runs_compat(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_b"]},
            prompts_path=fx["cfg_a"],
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "RUN_B_CONFIG_MISSING"


def test_run_b_seed_999_via_config_beside_refused(tmp_path: Path) -> None:
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    summary_a = ce.evaluate_runs(
        training_dir=fx["train_dir"],
        run_dirs={"A": fx["run_a"]},
        prompts_path=fx["cfg_a"],
        out_dir=out_a,
        steps=[0, 250, 500],
        embedder=ce.FakeEmbedder(),
    )
    corridors_file = out_a / "corridors.md"
    corridors_sha = summary_a["corridors"]["file_sha256"]
    cfg_a_data = ce.load_prompts_config(fx["cfg_a"])

    # Place config.yaml inside run_b where seed: 999 is under config/train
    beside_cfg = fx["run_b"] / "config.yaml"
    beside_lines = [
        "job: extension",
        "config:",
        "  name: synthstyle_style_v1",
        "  seed: 999",
        "  process:",
        "    - type: sd_trainer",
        "      train:",
        "        seed: 999",
        "      sample:",
        "        walk_seed: true",
        "        prompts:",
    ]
    for p in cfg_a_data["prompts"]:
        beside_lines.append(f'          - "{p}"')
    beside_cfg.write_text("\n".join(beside_lines) + "\n", encoding="utf-8")

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        _eval_runs_compat(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_b"]},
            prompts_path=fx["cfg_a"],
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "SEED_MISMATCH"


def test_missing_step_500_refused(tmp_path: Path) -> None:
    fake_run_a = {
        "num_prompts": 6,
        "paired_diff_sd_estimate": {"value": 0.02, "estimator": "test"},
        "steps": {
            "250": {
                "csd_topk": {"mean": 0.50, "sd": 0.02},
                "delta_csd": {"mean": 0.15, "sd": 0.02},
                "delta_clip_t": {"mean": 0.00, "sd": 0.01},
                "delta_dino_nn": {"mean": 0.05, "sd": 0.01},
                "dreamsim_to_step0": {"mean": 0.30, "sd": 0.02},
            },
            "500": {
                "csd_topk": {"mean": 0.55, "sd": 0.02},
                "delta_csd": {"mean": 0.20, "sd": 0.02},
                "delta_clip_t": {"mean": 0.00, "sd": 0.01},
                "delta_dino_nn": {"mean": 0.06, "sd": 0.01},
                "dreamsim_to_step0": {"mean": 0.35, "sd": 0.02},
            },
        },
    }
    corridors_payload = ce.build_corridors_payload(fake_run_a)

    # 1. Missing step 500 in run_b_summary when scoring against corridors must refuse STEP_MISSING
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.score_run_b_against_corridors(
            corridors_payload,
            {
                "steps": {
                    "0": {
                        "csd_topk": {"mean": 0.40},
                        "delta_clip_t": {"mean": 0.0},
                        "delta_dino_nn": {"mean": 0.0},
                        "delta_csd": {"mean": 0.0},
                    },
                    "250": {
                        "csd_topk": {"mean": 0.50},
                        "delta_clip_t": {"mean": 0.01},
                        "delta_dino_nn": {"mean": 0.04},
                        "delta_csd": {"mean": 0.15},
                    },
                }
            },
            {
                "velocity_ratio_rho_500": 0.95,
                "pooled_250_500": {"csd_topk": {"mean": 0.01}},
                "by_step": {
                    "250": {"dreamsim_b_vs_a_mean": 0.10},
                    "500": {"dreamsim_b_vs_a_mean": 0.12},
                },
            },
        )
    assert exc_info.value.code == "STEP_MISSING"
    assert "500" in exc_info.value.why

    # 2. Missing step 500 in build_corridors_payload must refuse STEP_MISSING
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info2:
        ce.build_corridors_payload(
            {
                "num_prompts": 6,
                "paired_diff_sd_estimate": {"value": 0.02, "estimator": "test"},
                "steps": {"0": fake_run_a["steps"]["250"], "250": fake_run_a["steps"]["250"]},
            }
        )
    assert exc_info2.value.code == "STEP_MISSING"
    assert "500" in exc_info2.value.why


def test_missing_dreamsim_refused() -> None:
    fake_run_a = {
        "num_prompts": 6,
        "paired_diff_sd_estimate": {"value": 0.02, "estimator": "test"},
        "steps": {
            "250": {
                "csd_topk": {"mean": 0.50, "sd": 0.02},
                "delta_csd": {"mean": 0.15, "sd": 0.02},
                "delta_clip_t": {"mean": 0.00, "sd": 0.01},
                "delta_dino_nn": {"mean": 0.05, "sd": 0.01},
                "dreamsim_to_step0": {"mean": 0.30, "sd": 0.02},
            },
            "500": {
                "csd_topk": {"mean": 0.55, "sd": 0.02},
                "delta_csd": {"mean": 0.20, "sd": 0.02},
                "delta_clip_t": {"mean": 0.00, "sd": 0.01},
                "delta_dino_nn": {"mean": 0.06, "sd": 0.01},
                "dreamsim_to_step0": {"mean": 0.35, "sd": 0.02},
            },
        },
    }
    corridors_payload = ce.build_corridors_payload(fake_run_a)

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.score_run_b_against_corridors(
            corridors_payload,
            {
                "steps": {
                    "250": {
                        "csd_topk": {"mean": 0.50},
                        "delta_clip_t": {"mean": 0.01},
                        "delta_dino_nn": {"mean": 0.05},
                        "delta_csd": {"mean": 0.15},
                    },
                    "500": {
                        "csd_topk": {"mean": 0.56},
                        "delta_clip_t": {"mean": 0.01},
                        "delta_dino_nn": {"mean": 0.08},
                        "delta_csd": {"mean": 0.20},
                    },
                }
            },
            {
                "velocity_ratio_rho_500": 0.95,
                "pooled_250_500": {"csd_topk": {"mean": 0.01}},
                "by_step": {
                    "250": {"dreamsim_b_vs_a_mean": 0.10},
                    "500": {"dreamsim_b_vs_a_mean": None},
                },
            },
        )
    assert exc_info.value.code == "METRIC_MISSING"
    assert "500" in exc_info.value.why
    assert "dreamsim" in exc_info.value.why.lower()


def test_per_layer_singular_values_from_safetensors_match_numpy(tmp_path: Path) -> None:
    try:
        import numpy as np  # type: ignore
    except ImportError:
        np = None  # type: ignore
    # Asymmetric shapes B=(6, 2), A=(2, 4) so B @ A is (6, 4) and A @ B is invalid,
    # plus a second layer B2=(4, 2), A2=(2, 4) with .alpha = 8.0 (scale = 8.0 / 2 = 4.0)
    b_asym = [
        [2.5, -0.5],
        [0.0, 1.5],
        [-1.0, 0.25],
        [0.75, 2.0],
        [1.25, -1.5],
        [-0.5, 0.5],
    ]
    a_asym = [
        [1.5, -0.5, 2.0, 0.25],
        [-0.75, 1.25, 0.5, -1.0],
    ]
    b_sq = [
        [3.0, 0.5],
        [-1.0, 2.0],
        [0.5, -1.5],
        [2.0, 1.0],
    ]
    a_sq = [
        [1.0, 2.0, -0.5, 0.0],
        [0.5, -1.0, 1.5, 2.5],
    ]
    ckpt = tmp_path / "tiny_synth.safetensors"
    _write_synthetic_safetensors(
        ckpt,
        {
            "diffusion_model.transformer_blocks.0.attn.to_q.lora_B.weight": _pack_f32_matrix(b_asym),
            "diffusion_model.transformer_blocks.0.attn.to_q.lora_A.weight": _pack_f32_matrix(a_asym),
            "diffusion_model.transformer_blocks.0.img_mlp.net.lora_B.weight": _pack_f32_matrix(b_sq),
            "diffusion_model.transformer_blocks.0.img_mlp.net.lora_A.weight": _pack_f32_matrix(a_sq),
            "diffusion_model.transformer_blocks.0.img_mlp.net.alpha": ("F32", [1], struct.pack("<f", 8.0)),
        },
    )
    ws = ce.read_safetensors_weight_space([ckpt])
    layers = ws["checkpoints"]["tiny_synth.safetensors"]["layers"]

    # Exact numpy.linalg.svd(B @ A, compute_uv=False) reference values
    expected_sv_q = [8.633089549381317, 4.8445603342680235]
    expected_frob_q = 9.899494936611665
    expected_sv_mlp = [37.98849334874042, 29.493632755099956]
    swapped_sv_mlp_top = 33.55708982476848

    if np is not None:
        dw_q = np.asarray(b_asym, dtype=np.float64) @ np.asarray(a_asym, dtype=np.float64)
        expected_sv_q = [float(x) for x in np.linalg.svd(dw_q, compute_uv=False)]
        expected_frob_q = float(np.linalg.norm(dw_q, "fro"))
        dw_mlp = (8.0 / 2.0) * (np.asarray(b_sq, dtype=np.float64) @ np.asarray(a_sq, dtype=np.float64))
        expected_sv_mlp = [float(x) for x in np.linalg.svd(dw_mlp, compute_uv=False)]
        swapped_sv_mlp_top = float(
            np.linalg.svd(
                (8.0 / 2.0) * (np.asarray(a_sq, dtype=np.float64) @ np.asarray(b_sq, dtype=np.float64)),
                compute_uv=False,
            )[0]
        )

    # Layer 1: unscaled B @ A (6x4)
    q_layer = layers["diffusion_model.transformer_blocks.0.attn.to_q"]
    assert q_layer["shape"] == [6, 4]
    assert q_layer["rank"] == 2
    assert len(q_layer["singular_values"]) == 2
    for got, exp in zip(q_layer["singular_values"], expected_sv_q):
        assert math.isclose(got, float(exp), abs_tol=1e-5)
    assert math.isclose(q_layer["top_singular_value"], float(expected_sv_q[0]), abs_tol=1e-5)
    assert math.isclose(q_layer["frobenius_norm"], expected_frob_q, abs_tol=1e-5)

    # Layer 2: scaled by alpha / rank = 8.0 / 2 = 4.0, and differs from swapped A @ B
    mlp_layer = layers["diffusion_model.transformer_blocks.0.img_mlp.net"]
    assert not math.isclose(float(expected_sv_mlp[0]), swapped_sv_mlp_top, abs_tol=1e-3)
    for got, exp in zip(mlp_layer["singular_values"], expected_sv_mlp):
        assert math.isclose(got, float(exp), abs_tol=1e-5)
    assert math.isclose(mlp_layer["top_singular_value"], float(expected_sv_mlp[0]), abs_tol=1e-5)


def test_wilcoxon_p_less_and_normal_approximation_above_n20() -> None:
    # 1. All-negative diffs (n=6): B < A -> W+ = 0, W- = 21, p_less = 1/64 = 0.015625, p_greater = 1.0
    a = [0.54, 0.52, 0.56, 0.51, 0.55, 0.53]
    b = [0.50, 0.50, 0.50, 0.50, 0.50, 0.50]
    stats_neg = ce.compute_paired_stats(b, a)
    assert math.isclose(stats_neg["t_p_less"], 0.002967, abs_tol=5e-6)
    assert math.isclose(stats_neg["t_p_greater"], 1.0 - 0.00296677, abs_tol=5e-6)
    assert stats_neg["wilcoxon"]["w_plus"] == 0.0
    assert stats_neg["wilcoxon"]["w_minus"] == 21.0
    assert math.isclose(stats_neg["wilcoxon"]["p_less"], 1.0 / 64.0, abs_tol=1e-8)
    assert math.isclose(stats_neg["wilcoxon"]["p_greater"], 1.0, abs_tol=1e-8)

    # 2. Mixed diffs (n=4): diffs = [-0.01, -0.02, -0.03, +0.04] -> W+ = 4, W- = 6
    # Subset sums <= 4 out of 16: {}, {1}, {2}, {3}, {4}, {1,2}, {1,3} -> 7 / 16 = 0.4375; >= 4 is 11 / 16 = 0.6875
    stats_mix = ce.compute_paired_stats([0.49, 0.48, 0.47, 0.54], [0.50, 0.50, 0.50, 0.50])
    assert stats_mix["wilcoxon"]["w_plus"] == 4.0
    assert stats_mix["wilcoxon"]["w_minus"] == 6.0
    assert math.isclose(stats_mix["wilcoxon"]["p_less"], 7.0 / 16.0, abs_tol=1e-8)
    assert math.isclose(stats_mix["wilcoxon"]["p_greater"], 11.0 / 16.0, abs_tol=1e-8)

    # 3. Normal approximation above n=20 (n=21 all-negative diffs)
    diffs_21 = [-0.01 * (i + 1) for i in range(21)]
    w21 = ce._wilcoxon_signed_rank(diffs_21)
    assert w21["n_nonzero"] == 21
    assert w21.get("method") == "normal_approx"
    assert w21["w_plus"] == 0.0
    assert w21["w_minus"] == 231.0
    assert w21["p_less"] < 1e-4
    assert w21["p_greater"] > 0.9999


def test_shared_parent_config_not_picked_up_for_run_b_refused(tmp_path: Path) -> None:
    """Layout runs/A, runs/B, and runs/config.yaml (run A's config) with no config inside runs/B must refuse RUN_B_CONFIG_MISSING."""
    fx = _make_synthetic_fixture_tree(tmp_path)
    runs_dir = tmp_path / "runs"
    run_a = runs_dir / "A"
    run_b = runs_dir / "B"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)
    for p in fx["run_a"].iterdir():
        (run_a / p.name).write_bytes(p.read_bytes())
    for p in fx["run_b"].iterdir():
        (run_b / p.name).write_bytes(p.read_bytes())
    shared_cfg = runs_dir / "config.yaml"
    shared_cfg.write_text(fx["cfg_a"].read_text(encoding="utf-8"), encoding="utf-8")

    out_a = tmp_path / "eval_shared"
    summary_a = ce.evaluate_runs(
        training_dir=fx["train_dir"],
        run_dirs={"A": run_a},
        prompts_path=shared_cfg,
        out_dir=out_a,
        steps=[0, 250, 500],
        embedder=ce.FakeEmbedder(),
    )
    corridors_file = out_a / "corridors.md"
    corridors_sha = summary_a["corridors"]["file_sha256"]

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": run_a, "B": run_b},
            prompts_path=shared_cfg,
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "RUN_B_CONFIG_MISSING"


def test_run_b_config_same_as_run_a_refused(tmp_path: Path) -> None:
    """Refuse RUN_B_CONFIG_IS_RUN_A when B's config resolves to the same file as run A's config or --prompts."""
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    summary_a = ce.evaluate_runs(
        training_dir=fx["train_dir"],
        run_dirs={"A": fx["run_a"]},
        prompts_path=fx["cfg_a"],
        out_dir=out_a,
        steps=[0, 250, 500],
        embedder=ce.FakeEmbedder(),
    )
    corridors_file = out_a / "corridors.md"
    corridors_sha = summary_a["corridors"]["file_sha256"]

    # Case 1: --prompts-b resolves to the same file as --prompts
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_b"]},
            prompts_path=fx["cfg_a"],
            prompts_b_path=fx["cfg_a"].parent / "." / fx["cfg_a"].name,
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "RUN_B_CONFIG_IS_RUN_A"

    # Case 2: --prompts points to config inside B's samples dir, and B auto-discovers that same file
    cfg_in_b = fx["run_b"] / "config.yaml"
    cfg_in_b.write_text(fx["cfg_a"].read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info2:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_b"]},
            prompts_path=cfg_in_b,
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info2.value.code == "RUN_B_CONFIG_IS_RUN_A"

    # Case 3: run A has config.yaml inside run A's samples dir, and --prompts-b points to it
    cfg_in_a = fx["run_a"] / "config.yaml"
    cfg_in_a.write_text(fx["cfg_a"].read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info3:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_b"]},
            prompts_path=fx["cfg_a"],
            prompts_b_path=cfg_in_a,
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info3.value.code == "RUN_B_CONFIG_IS_RUN_A"


def test_run_b_dir_same_as_run_a_refused(tmp_path: Path) -> None:
    """Refuse RUN_B_IS_RUN_A when B's samples directory resolves to A's."""
    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    summary_a = ce.evaluate_runs(
        training_dir=fx["train_dir"],
        run_dirs={"A": fx["run_a"]},
        prompts_path=fx["cfg_a"],
        out_dir=out_a,
        steps=[0, 250, 500],
        embedder=ce.FakeEmbedder(),
    )
    corridors_file = out_a / "corridors.md"
    corridors_sha = summary_a["corridors"]["file_sha256"]

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_a"] / "."},
            prompts_path=fx["cfg_a"],
            prompts_b_path=fx["cfg_b"],
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=corridors_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info.value.code == "RUN_B_IS_RUN_A"


def test_corridors_band_check_alone_refused(tmp_path: Path) -> None:
    """Re-seal a band-tampered corridors file, pass that file's own sha as --corridors-sha, and assert CORRIDORS_TAMPERED."""
    import hashlib

    fx = _make_synthetic_fixture_tree(tmp_path)
    out_a = tmp_path / "eval_a"
    ce.evaluate_runs(
        training_dir=fx["train_dir"],
        run_dirs={"A": fx["run_a"]},
        prompts_path=fx["cfg_a"],
        out_dir=out_a,
        steps=[0, 250, 500],
        embedder=ce.FakeEmbedder(),
    )
    corridors_file = out_a / "corridors.md"

    text = corridors_file.read_text(encoding="utf-8")
    edited = text.replace('"kill_below": -0.035', '"kill_below": -99.0', 1)
    assert edited != text
    m_sha = ce.re.search(r"^- \*\*body_sha256:\*\* `([0-9a-f]{64})`$", edited, flags=ce.re.MULTILINE)
    assert m_sha is not None
    with_placeholder = edited[: m_sha.start(1)] + ce.CORRIDORS_SHA_PLACEHOLDER + edited[m_sha.end(1) :]
    resealed_body_sha = ce._compute_corridors_body_sha256(with_placeholder)
    resealed_text = with_placeholder.replace(ce.CORRIDORS_SHA_PLACEHOLDER, resealed_body_sha, 1)
    corridors_file.write_text(resealed_text, encoding="utf-8", newline="\n")
    tampered_file_sha = hashlib.sha256(corridors_file.read_bytes()).hexdigest()

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info:
        ce.read_and_verify_corridors(corridors_file, expected_sha256=tampered_file_sha)
    assert exc_info.value.code == "CORRIDORS_TAMPERED"

    with pytest.raises(ce.CheckpointEvalRefusal) as exc_info2:
        ce.evaluate_runs(
            training_dir=fx["train_dir"],
            run_dirs={"A": fx["run_a"], "B": fx["run_b"]},
            prompts_path=fx["cfg_a"],
            prompts_b_path=fx["cfg_b"],
            out_dir=out_a,
            steps=[0, 250, 500],
            corridors_path=corridors_file,
            corridors_sha=tampered_file_sha,
            embedder=ce.FakeEmbedder(),
        )
    assert exc_info2.value.code == "CORRIDORS_TAMPERED"


def test_wilcoxon_normal_approx_p_less_with_ties_kills_m3() -> None:
    """Hand-computed normal-approximation p_less with ties at n=21 (> 20) that kills continuity-correction sign mutation M3."""
    # n = 21 non-zero diffs:
    # - 4 tied at +1.0 -> ranks 1..4, avg rank 2.5 -> W+ contribution = 10.0 (tie group t=4: 4*3*5 = 60)
    # - 3 tied at -2.0 -> ranks 5..7, avg rank 6.0 -> W- contribution = 18.0 (tie group t=3: 3*2*4 = 24)
    # - 10 distinct negative diffs -3.0..-12.0 -> ranks 8..17 -> W- contribution = 125.0
    # - 4 distinct positive diffs +13.0..+16.0 -> ranks 18..21 -> W+ contribution = 78.0
    # Total: W+ = 88.0, W- = 143.0, mu = 0.25 * 21 * 22 = 115.5
    # tie_term = 0.5 * (60 + 24) = 42.0
    # var = (21 * 22 * 43 - 42.0) / 24.0 = 19824 / 24.0 = 826.0, sigma = sqrt(826.0)
    # z_less = (88.0 - 115.5 + 0.5) / sqrt(826.0) = -27.0 / sqrt(826.0)
    # p_less = 0.5 * (1 + erf(-27.0 / sqrt(1652.0))) = 0.1737499974 -> 0.17375
    # (Under M3 where +0.5 is mutated to -0.5, z_less = -28.0 / sqrt(826.0) -> p_less = 0.16496427)
    diffs = (
        [1.0, 1.0, 1.0, 1.0]
        + [-2.0, -2.0, -2.0]
        + [-float(k) for k in range(3, 13)]
        + [float(k) for k in range(13, 17)]
    )
    res = ce._wilcoxon_signed_rank(diffs)
    assert res["n_nonzero"] == 21
    assert res["method"] == "normal_approx"
    assert res["w_plus"] == 88.0
    assert res["w_minus"] == 143.0
    assert res["statistic"] == 88.0
    expected_p_less = round(0.5 * (1.0 + math.erf(-27.0 / math.sqrt(1652.0))), 8)
    expected_p_greater = round(0.5 * math.erfc(-28.0 / math.sqrt(1652.0)), 8)
    expected_p_two = round(math.erfc(27.0 / math.sqrt(1652.0)), 8)
    assert expected_p_less == 0.17374984
    assert math.isclose(res["p_less"], expected_p_less, abs_tol=1e-8)
    assert math.isclose(res["p_greater"], expected_p_greater, abs_tol=1e-8)
    assert math.isclose(res["p_two_sided"], expected_p_two, abs_tol=1e-8)



