"""Unit and CLI tests for scripts/colab/lane1_jobs_from_canon.py using a synthetic git canon repo."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_COLAB = REPO_ROOT / "scripts" / "colab"
if str(SCRIPTS_COLAB) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_COLAB))

import lane1_jobs_from_canon as ljc  # noqa: E402
import lane1_render as l1  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "Synthetic Test"
    env["GIT_AUTHOR_EMAIL"] = "synthetic@example.invalid"
    env["GIT_COMMITTER_NAME"] = "Synthetic Test"
    env["GIT_COMMITTER_EMAIL"] = "synthetic@example.invalid"
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def _make_synthetic_canon_repo(root: Path) -> tuple[Path, Path, str, dict[str, bytes]]:
    repo = root / "synthetic_canon_repo"
    canon_dir = repo / "canon"
    (canon_dir / "tools").mkdir(parents=True)
    (canon_dir / "lamps").mkdir(parents=True)

    files: dict[str, str] = {
        # Tier 1: frontmatter:prompt
        "canon/tools/compass_01.md": (
            "---\n"
            "title: Synthetic Brass Compass\n"
            'prompt: "a synthetic brass pocket compass on a wooden workbench, clean line study"\n'
            "---\n"
            "# Synthetic Brass Compass\n\n"
            "Unchosen body paragraph.\n"
        ),
        # Tier 2: frontmatter:visual
        "canon/tools/caliper_02.md": (
            "---\n"
            "name: Vernier Caliper\n"
            "summary: Precision steel bench instrument.\n"
            "visual:\n"
            "  silhouette_cue: Slender stepped jaw bar\n"
            "  material_dominant: brushed carbon steel\n"
            "  lighting_mood: crisp workbench daylight\n"
            "  signature_features:\n"
            "    - knurled thumb roller\n"
            "    - etched millimeter scale\n"
            "---\n"
            "# Vernier Caliper\n\n"
            "Fallback body text.\n"
        ),
        # Tier 3: section:visual
        "canon/tools/kettle_03.md": (
            "---\n"
            "title: Cast Kettle\n"
            "status: active\n"
            "---\n"
            "# Cast Kettle (Fixture)\n\n"
            "General note paragraph.\n\n"
            "## Visual Identity\n\n"
            "- A hammered tin kettle beside a **ceramic** mug on neutral linen [invented] (C:12).\n\n"
            "## Notes\n\n"
            "Trailing section.\n"
        ),
        # Tier 4: section:at_a_glance
        "canon/lamps/lantern_04.md": (
            "# Glass Desk Lantern\n\n"
            "## At a glance\n\n"
            "Tall cylindrical [glass lantern](https://example.invalid) with warm filament glow.\n"
        ),
        # Tier 5: body:first_paragraph
        "canon/lamps/sconce_05.md": (
            "---\n"
            "category: fixture\n"
            "---\n"
            "# Wall Sconce\n\n"
            "```txt\n"
            "ignored code block\n"
            "```\n\n"
            "| col | val |\n"
            "| --- | --- |\n\n"
            "> Simple iron wall sconce mounted on pale plaster\n"
        ),
        "canon/tools/held_item.md": (
            "---\n"
            "status: held\n"
            'prompt: "should never be rendered"\n'
            "---\n"
            "# Held Item\n"
        ),
        "canon/tools/empty_entry.md": (
            "---\n"
            "category: blank\n"
            "---\n"
            "# Heading Only\n"
        ),
        "canon/tools/dup.md": "# Dup One\n\nFirst body.\n",
        "canon/lamps/dup.md": "# Dup Two\n\nSecond body.\n",
    }

    raw_bytes: dict[str, bytes] = {}
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        b = content.encode("utf-8", errors="strict")
        p.write_bytes(b)
        raw_bytes[rel] = b

    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial synthetic MIT canon fixture")
    commit_sha = _git(repo, "rev-parse", "HEAD")
    return repo, canon_dir, commit_sha, raw_bytes


def test_build_jobs_from_synthetic_canon_extracts_prompts_hashes_and_cc_by_credit(tmp_path: Path) -> None:
    _repo, canon_dir, commit_sha, raw_bytes = _make_synthetic_canon_repo(tmp_path)

    # Mutate working tree after commit to prove builder reads exact blobs from git commit, not dirty disk
    (canon_dir / "tools" / "compass_01.md").write_text(
        '---\nprompt: "DIRTY UNCOMMITTED WORKING TREE TEXT"\n---\n',
        encoding="utf-8",
    )

    out_jobs = tmp_path / "out" / "jobs.jsonl"
    sha_file = tmp_path / "out" / "jobs.sha256"
    summary = ljc.build_jobs_from_canon(
        canon_dir=canon_dir,
        canon_commit=commit_sha[:12],
        entry_ids=[
            "tools/compass_01",
            "caliper_02",
            "tools/kettle_03.md",
            "lamps/lantern_04",
            "lamps/sconce_05",
        ],
        out_path=out_jobs,
        sha256_out=sha_file,
        run_id="run_synth_01",
        seeds=[5000, 5001],
        width=768,
        height=768,
        steps=24,
        cfg=3.0,
        style_prefix="synthetic studio ink",
        loras=ljc._parse_lora_specs(["synth_lora_v1.safetensors:0.75"]),
    )

    assert summary["canon_sha"] == commit_sha
    assert summary["job_count"] == 10
    assert summary["canon_licence"] == "MIT"
    assert summary["licence"] == "CC-BY-4.0"
    assert summary["credit"] == "mcp-tool-shop"
    assert summary["prompt_rule"] == ljc.PROMPT_EXTRACTION_RULE
    assert sha_file.read_text(encoding="utf-8").strip() == summary["jobs_sha256"]

    # Output jobs.jsonl passes lane1_render's strict rig-side validator directly
    validated = l1.validate_render_jobs(out_jobs, summary["jobs_sha256"])
    assert validated["job_count"] == 10

    rows = [json.loads(line) for line in out_jobs.read_text(encoding="utf-8").splitlines() if line.strip()]
    first_seed_rows = rows[0::2]
    second_seed_rows = rows[1::2]
    assert [r["entry_id"] for r in first_seed_rows] == [
        "tools/compass_01",
        "tools/caliper_02",
        "tools/kettle_03",
        "lamps/lantern_04",
        "lamps/sconce_05",
    ]
    assert [r["prompt_source"] for r in first_seed_rows] == [
        "frontmatter:prompt",
        "frontmatter:visual",
        "section:visual",
        "section:at_a_glance",
        "body:first_paragraph",
    ]

    expected_blobs = [
        raw_bytes["canon/tools/compass_01.md"],
        raw_bytes["canon/tools/caliper_02.md"],
        raw_bytes["canon/tools/kettle_03.md"],
        raw_bytes["canon/lamps/lantern_04.md"],
        raw_bytes["canon/lamps/sconce_05.md"],
    ]
    expected_prompts = [
        "synthetic studio ink. a synthetic brass pocket compass on a wooden workbench, clean line study",
        (
            "synthetic studio ink. Vernier Caliper: Precision steel bench instrument. "
            "Slender stepped jaw bar. brushed carbon steel. crisp workbench daylight. "
            "Signature features: knurled thumb roller, etched millimeter scale."
        ),
        "synthetic studio ink. Cast Kettle. A hammered tin kettle beside a ceramic mug on neutral linen.",
        "synthetic studio ink. Glass Desk Lantern. Tall cylindrical glass lantern with warm filament glow.",
        "synthetic studio ink. Wall Sconce. Simple iron wall sconce mounted on pale plaster.",
    ]

    for row5000, row5001, blob, exp_prompt in zip(
        first_seed_rows, second_seed_rows, expected_blobs, expected_prompts, strict=True
    ):
        assert row5000["seed"] == 5000
        assert row5001["seed"] == 5001
        for row in (row5000, row5001):
            assert row["canon_sha"] == commit_sha
            assert row["entry_sha256"] == "sha256:" + hashlib.sha256(blob).hexdigest()
            assert row["prompt"] == exp_prompt
            assert "DIRTY UNCOMMITTED" not in row["prompt"]
            assert row["canon_licence"] == "MIT"
            assert row["licence"] == "CC-BY-4.0"
            assert row["credit"] == "mcp-tool-shop"
            assert row["owner"] == "mcp-tool-shop"
            assert row["workflow_sha"].startswith("sha256:")
            assert row["model_pins"]["base_repo"] == l1.PINNED_BASE_MODEL_REPO
            assert row["model_pins"]["base_revision"] == l1.PINNED_BASE_MODEL_REVISION
            assert row["model_pins"]["repack_repo"] == l1.PINNED_COMFY_REPACK_REPO
            assert row["model_pins"]["repack_revision"] == l1.PINNED_COMFY_REPACK_REVISION
            assert row["loras"] == [{"name": "synth_lora_v1.safetensors", "weight": 0.75}]

    # Minimal frontmatter fallback parser works even without PyYAML
    minimal_parsed = ljc._parse_minimal_frontmatter(
        "# comment\nname: Sample Tool\nheld: false\nvisual:\n  silhouette_cue: Tapered blade\n  signature_features:\n    - brass ferrule\n"
    )
    assert minimal_parsed["name"] == "Sample Tool"
    assert minimal_parsed["held"] is False
    assert minimal_parsed["visual"]["silhouette_cue"] == "Tapered blade"
    assert minimal_parsed["visual"]["signature_features"] == ["brass ferrule"]


def test_jobs_builder_refusals_for_held_missing_ambiguous_bad_commit_and_cli(tmp_path: Path) -> None:
    _repo, canon_dir, commit_sha, _raw = _make_synthetic_canon_repo(tmp_path)

    # Held entry refused
    with pytest.raises(ljc.CanonJobsError) as exc_held:
        ljc.build_jobs_from_canon(
            canon_dir=canon_dir,
            canon_commit=commit_sha,
            entry_ids=["tools/held_item"],
            out_path=tmp_path / "held.jsonl",
        )
    assert exc_held.value.code == "CANON_ENTRY_HELD"

    # Empty body entry refused
    with pytest.raises(ljc.CanonJobsError) as exc_empty:
        ljc.build_jobs_from_canon(
            canon_dir=canon_dir,
            canon_commit=commit_sha,
            entry_ids=["tools/empty_entry"],
            out_path=tmp_path / "empty.jsonl",
        )
    assert exc_empty.value.code == "CANON_PROMPT_EMPTY"

    # Missing entry refused
    with pytest.raises(ljc.CanonJobsError) as exc_miss:
        ljc.build_jobs_from_canon(
            canon_dir=canon_dir,
            canon_commit=commit_sha,
            entry_ids=["tools/does_not_exist"],
            out_path=tmp_path / "miss.jsonl",
        )
    assert exc_miss.value.code == "CANON_ENTRY_MISSING"

    # Ambiguous bare basename (canon/tools/dup.md vs canon/lamps/dup.md) refused
    with pytest.raises(ljc.CanonJobsError) as exc_ambig:
        ljc.build_jobs_from_canon(
            canon_dir=canon_dir,
            canon_commit=commit_sha,
            entry_ids=["dup"],
            out_path=tmp_path / "ambig.jsonl",
        )
    assert exc_ambig.value.code == "CANON_ENTRY_AMBIGUOUS"

    # Unsafe entry id, duplicate entry, empty list, bad geometry, bad seed, bad template, bad commit
    bad_canon_calls = [
        ({"entry_ids": ["../escape"]}, "CANON_ENTRY_INVALID"),
        ({"entry_ids": ["tools/compass_01", "tools/compass_01.md"]}, "CANON_DUPLICATE_ENTRY"),
        ({"entry_ids": []}, "CANON_ENTRIES_EMPTY"),
        ({"seeds": [True]}, "RENDER_JOB_INVALID"),
        ({"template_id": "stub_fixture_64"}, "JOB_TEMPLATE_INVALID"),
        ({"canon_commit": ""}, "CANON_COMMIT_INVALID"),
        ({"canon_commit": "-badflag"}, "CANON_COMMIT_INVALID"),
        ({"canon_commit": "deadbeef" * 5}, "CANON_COMMIT_INVALID"),
        ({"canon_dir": tmp_path / "missing_parent" / "sub"}, "CANON_DIR_MISSING"),
    ]
    for overrides, expected_code in bad_canon_calls:
        kwargs = {
            "canon_dir": canon_dir,
            "canon_commit": commit_sha,
            "entry_ids": ["tools/compass_01"],
            "out_path": tmp_path / "bad.jsonl",
            **overrides,
        }
        with pytest.raises(ljc.CanonJobsError) as exc_info:
            ljc.build_jobs_from_canon(**kwargs)  # type: ignore[arg-type]
        assert exc_info.value.code == expected_code

    # Bad LoRA specs refused
    for bad_lora in (["bad:notfloat"], [":0.8"]):
        with pytest.raises(ljc.CanonJobsError) as exc_lora:
            ljc._parse_lora_specs(bad_lora)
        assert exc_lora.value.code == "CANON_LORA_INVALID"

    # Non-positive width/steps caught by validate_render_jobs gate
    for geom_override in ({"width": 0}, {"steps": 0}):
        with pytest.raises(l1.Refusal) as exc_geom:
            ljc.build_jobs_from_canon(
                canon_dir=canon_dir,
                canon_commit=commit_sha,
                entry_ids=["tools/compass_01"],
                out_path=tmp_path / "bad_geom.jsonl",
                **geom_override,  # type: ignore[arg-type]
            )
        assert exc_geom.value.code == "RENDER_JOB_INVALID"

    non_git = tmp_path / "plain_dir"
    non_git.mkdir()
    with pytest.raises(ljc.CanonJobsError) as exc_nongit:
        ljc.build_jobs_from_canon(
            canon_dir=non_git,
            canon_commit=commit_sha,
            entry_ids=["x"],
            out_path=tmp_path / "nongit.jsonl",
        )
    assert exc_nongit.value.code == "CANON_NOT_GIT_REPO"

    # In-process main() covers happy path, missing entries-file, CanonJobsError, and l1.Refusal
    entries_file = tmp_path / "entries.txt"
    entries_file.write_text("# synthetic list\ntools/compass_01\nlamps/lantern_04\n", encoding="utf-8")
    inproc_out = tmp_path / "inproc_jobs.jsonl"
    assert (
        ljc.main(
            [
                "--canon-dir",
                str(canon_dir),
                "--canon-commit",
                commit_sha,
                "--entries-file",
                str(entries_file),
                "--lora",
                "plain_style.safetensors",
                "--run-id",
                "run_cli_01",
                "--out",
                str(inproc_out),
            ]
        )
        == 0
    )
    inproc_rows = [json.loads(ln) for ln in inproc_out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(inproc_rows) == 2
    assert inproc_rows[0]["loras"] == [{"name": "plain_style.safetensors", "weight": 1.0}]

    assert (
        ljc.main(
            [
                "--canon-dir",
                str(canon_dir),
                "--canon-commit",
                commit_sha,
                "--entries-file",
                str(tmp_path / "absent_entries.txt"),
                "--out",
                str(tmp_path / "absent_out.jsonl"),
            ]
        )
        == 1
    )
    assert (
        ljc.main(
            [
                "--canon-dir",
                str(canon_dir),
                "--canon-commit",
                commit_sha,
                "--entry",
                "tools/compass_01",
                "--width",
                "0",
                "--out",
                str(tmp_path / "zero_w.jsonl"),
            ]
        )
        == 1
    )

    # Subprocess CLI invocation covers __main__ entry point and stderr refusal formatting
    cli_out = tmp_path / "cli_jobs.jsonl"
    res_ok = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_COLAB / "lane1_jobs_from_canon.py"),
            "--canon-dir",
            str(canon_dir),
            "--canon-commit",
            commit_sha,
            "--entry",
            "tools/compass_01",
            "--out",
            str(cli_out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_ok.returncode == 0, res_ok.stderr
    assert "JOBS_BUILT " in res_ok.stdout

    res_bad = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_COLAB / "lane1_jobs_from_canon.py"),
            "--canon-dir",
            str(canon_dir),
            "--canon-commit",
            commit_sha,
            "--entry",
            "tools/held_item",
            "--out",
            str(tmp_path / "cli_bad.jsonl"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_bad.returncode == 1
    assert "REFUSED: CANON_ENTRY_HELD:" in res_bad.stderr
