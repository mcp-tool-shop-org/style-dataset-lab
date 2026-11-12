"""In-process (import and call) tests for code the subprocess end-to-end tests exercise but coverage
cannot trace: `lane3_rung.repair_bundle_with_files` and `run_repair_bundle`, the verify-bundle missing /
unreadable / size / sha branches, the VM download split free-disk and ENOSPC paths in
`launch_guards.prepare_single_content_download`, and `remote_runner._load_launch_guards` /
`_resolve_bash`. Plus the optimizer provenance refusal in `lane3_rung.plan-run` (Part 6)."""

from __future__ import annotations

import errno
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
sys.path.insert(0, str(COLAB_DIR))

import launch_guards as lg  # noqa: E402
import lane3_rung as lr  # noqa: E402
import remote_runner as rr  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _add(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def _make_bundle(path: Path, files: dict[str, bytes], *, manifest_files: dict[str, bytes] | None = None,
                 manifest_text: str | None = None, extra: dict[str, bytes] | None = None) -> None:
    """A lane3 bundle: rung_outputs/<rel> for each file in `files`, and a training_folder_manifest.json that
    lists `manifest_files` (default: the same files) with their true sha256 / size."""
    listed = files if manifest_files is None else manifest_files
    man = {"files": [{"path": rel, "bytes": len(b), "sha256": _sha(b)} for rel, b in listed.items()]}
    with tarfile.open(path, "w:gz") as tf:
        for rel, blob in files.items():
            _add(tf, f"rung_outputs/{rel}", blob)
        if manifest_text is not None:
            _add(tf, "training_folder_manifest.json", manifest_text.encode("utf-8"))
        elif manifest_text is None and manifest_files != {}:
            _add(tf, "training_folder_manifest.json", json.dumps(man).encode("utf-8"))
        for name, blob in (extra or {}).items():
            _add(tf, name, blob)


# --------------------------------------------------------------------------------------------
# verify-bundle: missing / size / sha / unreadable / malformed branches
# --------------------------------------------------------------------------------------------


def test_verify_bundle_names_missing_size_and_sha_mismatches_and_recovered_files(tmp_path: Path) -> None:
    good = b"G" * 40
    intact = b"I" * 10
    # The bundle carries: a truncated 'size.bin', a same-size-but-different 'sha.bin', and no 'gone.bin'.
    listed = {"ok.txt": intact, "size.bin": good, "sha.bin": good, "gone.bin": b"x" * 7}
    bundle = tmp_path / "b.tar.gz"
    with tarfile.open(bundle, "w:gz") as tf:
        _add(tf, "rung_outputs/ok.txt", intact)
        _add(tf, "rung_outputs/size.bin", good[:30])
        _add(tf, "rung_outputs/sha.bin", b"H" * 40)
        _add(tf, "training_folder_manifest.json", json.dumps({
            "files": [{"path": r, "bytes": len(b), "sha256": _sha(b)} for r, b in listed.items()]
        }).encode("utf-8"))
    out = tmp_path / "check.json"
    rc = lr.main(["verify-bundle", "--bundle-tar", str(bundle), "--out", str(out), "--recovered-file", "ok.txt"])
    assert rc == 1
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rec["ok"] is False and rec["refusal_code"] == "TRAIN_OUTPUT_MANIFEST_MISMATCH"
    assert rec["missing_files"] == ["gone.bin"]
    assert sorted(rec["mismatched_files"]) == ["sha.bin", "size.bin"]
    reasons = {e["path"]: e["reason"] for e in rec["bad_entries"]}
    assert reasons == {"gone.bin": "missing", "size.bin": "size_mismatch", "sha.bin": "sha256_mismatch"}
    gone = next(e for e in rec["bad_entries"] if e["path"] == "gone.bin")
    assert gone["expected_bytes"] == 7 and gone["actual_bytes"] is None and gone["expected_sha256"] == _sha(b"x" * 7)
    assert rec["checked_files"] == 1
    assert rec["recovered_files"] == ["ok.txt"]
    assert "missing training output in bundle: rung_outputs/gone.bin" in rec["why"]
    assert "size mismatch for rung_outputs/size.bin" in rec["why"]
    assert "sha256 mismatch for rung_outputs/sha.bin" in rec["why"]


def test_verify_bundle_ok_records_recovered_files_and_malformed_manifests_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob = b"abc" * 5
    good = tmp_path / "good.tar.gz"
    _make_bundle(good, {"a.txt": blob})
    out = tmp_path / "ok.json"
    assert lr.main(["verify-bundle", "--bundle-tar", str(good), "--out", str(out), "--recovered-file", "a.txt"]) == 0
    ok = json.loads(out.read_text(encoding="utf-8"))
    assert ok == {"ok": True, "checked_files": 1, "total_bytes": len(blob), "recovered_files": ["a.txt"]}

    cases = {
        "not_json": "{not json",
        "no_files_list": json.dumps({"files": "nope"}),
        "bad_entry": json.dumps({"files": [{"bytes": 1}]}),
    }
    for label, text in cases.items():
        p = tmp_path / f"{label}.tar.gz"
        _make_bundle(p, {"a.txt": blob}, manifest_text=text)
        with pytest.raises(lr.Refusal) as exc:
            lr.verify_bundle_against_manifest(p)
        assert exc.value.code == "TRAIN_OUTPUT_MANIFEST_MISMATCH", label

    no_manifest = tmp_path / "no_manifest.tar.gz"
    _make_bundle(no_manifest, {"a.txt": blob}, manifest_files={})
    with pytest.raises(lr.Refusal) as exc2:
        lr.verify_bundle_against_manifest(no_manifest)
    assert "training_folder_manifest.json is missing" in exc2.value.detail

    # A member that cannot be read: the manifest itself, then a listed file.
    real_extract = tarfile.TarFile.extractfile

    def _no_manifest_read(self: tarfile.TarFile, member: object) -> object:
        name = getattr(member, "name", member)
        if str(name).endswith("training_folder_manifest.json"):
            return None
        return real_extract(self, member)

    monkeypatch.setattr(tarfile.TarFile, "extractfile", _no_manifest_read)
    with pytest.raises(lr.Refusal) as exc3:
        lr.verify_bundle_against_manifest(good)
    assert "training_folder_manifest.json is unreadable" in exc3.value.detail

    def _no_member_read(self: tarfile.TarFile, member: object) -> object:
        name = getattr(member, "name", member)
        if str(name).endswith("rung_outputs/a.txt"):
            return None
        return real_extract(self, member)

    monkeypatch.setattr(tarfile.TarFile, "extractfile", _no_member_read)
    with pytest.raises(lr.Refusal) as exc4:
        lr.verify_bundle_against_manifest(good)
    assert exc4.value.bad_entries[0]["reason"] == "unreadable"
    assert exc4.value.mismatched_files == ["a.txt"]


# --------------------------------------------------------------------------------------------
# repair-bundle: repair_bundle_with_files / run_repair_bundle
# --------------------------------------------------------------------------------------------


def _read_members(bundle: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with tarfile.open(bundle, "r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                fh = tf.extractfile(m)
                assert fh is not None
                rel = m.name
                while rel.startswith("./"):
                    rel = rel[2:]
                out[rel] = fh.read()
    return out


def test_repair_bundle_splices_verified_files_updates_manifest_and_verifies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = b"O" * 64
    loss = b"loss-line\n" * 5
    st = b"S" * 33  # not a valid safetensors header -> a partial checkpoint
    truth = {"model_v5/optimizer.pt": opt, "model_v5/loss.log": loss, "model_v5/model.safetensors": st}
    bundle = tmp_path / "bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as tf:
        _add(tf, "rung_outputs/model_v5/loss.log", loss[:-3])  # truncated: size mismatch
        _add(tf, "rung_outputs/manifest.jsonl", b'{"path": "model_v5/loss.log", "bytes": 1, "sha256": "x"}\n')
        _add(tf, "train_facts.json", b"{}")
        _add(tf, "training_folder_manifest.json", json.dumps({
            "files": [{"path": r, "bytes": len(b), "sha256": _sha(b)} for r, b in truth.items()]
        }).encode("utf-8"))
    assert lr.main(["verify-bundle", "--bundle-tar", str(bundle)]) == 1
    capsys.readouterr()

    stage = tmp_path / "stage"
    for rel, blob in truth.items():
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        (stage / rel).write_bytes(blob)
    rc = lr.main([
        "repair-bundle", "--bundle-tar", str(bundle), "--stage-dir", str(stage),
        "--rel-file", "model_v5/optimizer.pt", "--rel-file", "model_v5/loss.log",
        "--rel-file", "model_v5/model.safetensors",
    ])
    out = capsys.readouterr().out
    assert rc == 0 and out.startswith("BUNDLE_REPAIRED ")
    repaired = json.loads(out.split(" ", 1)[1])
    assert repaired["ok"] is True and sorted(repaired["repaired_files"]) == sorted(truth)
    assert lr.main(["verify-bundle", "--bundle-tar", str(bundle)]) == 0

    members = _read_members(bundle)
    for rel, blob in truth.items():
        assert members[f"rung_outputs/{rel}"] == blob
    lines = [json.loads(ln) for ln in members["rung_outputs/manifest.jsonl"].decode("utf-8").splitlines()]
    recovered = {ln["path"]: ln for ln in lines if ln.get("recovered_by_refetch")}
    assert sorted(recovered) == sorted(truth)
    assert recovered["model_v5/optimizer.pt"]["sha256"] == _sha(opt) and recovered["model_v5/optimizer.pt"]["partial"] is False
    assert recovered["model_v5/model.safetensors"]["partial"] is True
    # train_facts.json was refreshed from the repaired manifest (run_finish).
    facts = json.loads(members["train_facts.json"].decode("utf-8"))
    assert "model_v5/optimizer.pt" in facts["rung_outputs"]["all_files"]
    assert not list(tmp_path.glob(".sdlab_repair_*")) and not list(tmp_path.glob("*.repaired.tmp"))


def test_repair_bundle_refuses_by_name_and_leaves_the_bundle_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blob = b"q" * 9
    bundle = tmp_path / "b.tar.gz"
    _make_bundle(bundle, {"a.txt": blob})
    before = bundle.read_bytes()
    stage = tmp_path / "stage"
    stage.mkdir()

    with pytest.raises(lr.Refusal) as exc_missing_tar:
        lr.repair_bundle_with_files(tmp_path / "nope.tar.gz", stage, ["a.txt"])
    assert exc_missing_tar.value.code == "TRAIN_OUTPUT_MANIFEST_MISMATCH"

    for bad_rel, needle in (("../escape.txt", "invalid repair path"), ("", "invalid repair path"),
                            ("absent.txt", "staged repair file missing")):
        with pytest.raises(lr.Refusal) as exc_rel:
            lr.repair_bundle_with_files(bundle, stage, [bad_rel])
        assert needle in exc_rel.value.detail, bad_rel
    assert bundle.read_bytes() == before
    assert not list(tmp_path.glob(".sdlab_repair_*")) and not list(tmp_path.glob("*.repaired.tmp"))

    rc = lr.main(["repair-bundle", "--bundle-tar", str(bundle), "--stage-dir", str(stage), "--rel-file", "absent.txt"])
    assert rc == 1 and "REFUSED: TRAIN_OUTPUT_MANIFEST_MISMATCH" in capsys.readouterr().err

    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tf:
        _add(tf, "../outside.txt", b"x")
    with pytest.raises(lr.Refusal) as exc_evil:
        lr.repair_bundle_with_files(evil, stage, [])
    assert "unsafe member path" in exc_evil.value.detail


# --------------------------------------------------------------------------------------------
# launch_guards: the VM download split (free-disk check, ENOSPC mid-split, success)
# --------------------------------------------------------------------------------------------


def test_split_free_bytes_override_fake_site_env_and_real_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAKE_VM_SITE", raising=False)
    monkeypatch.delenv("FAKE_VM_DL_SPLIT_FREE_BYTES", raising=False)
    assert lg._dl_split_free_bytes(tmp_path, 1234) == 1234
    real = lg._dl_split_free_bytes(tmp_path / "not" / "yet" / "made")  # walks up to an existing parent
    assert real > 0
    monkeypatch.setenv("FAKE_VM_SITE", "1")
    monkeypatch.setenv("FAKE_VM_DL_SPLIT_FREE_BYTES", "777")
    assert lg._dl_split_free_bytes(tmp_path) == 777
    assert lg._dl_split_free_bytes(tmp_path, 5) == 5  # the explicit override still wins


def test_download_prep_missing_single_and_prefix_helpers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "content"
    root.mkdir()
    missing = lg.prepare_single_content_download(root, "nope.tar.gz", 100)
    assert missing["exists"] is False
    assert capsys.readouterr().out.startswith("SDLAB_DOWNLOAD_PREPARE_JSON ")

    data = b"z" * 50
    (root / "small.bin").write_bytes(data)
    single = lg.prepare_single_content_download(root, "small.bin", 100, emit=False)
    assert single["split"] is False and single["whole_sha256"] == _sha(data) and single["part_count"] == 1
    assert capsys.readouterr().out == ""

    assert lg._dl_safe_prefix("a b/c.tar.gz") == ".sdlab_dl_a_b_c.tar.gz"
    long_prefix = lg._dl_safe_prefix("x" * 80)
    assert long_prefix.startswith(".sdlab_dl_" + "x" * 39 + "_") and len(long_prefix) == len(".sdlab_dl_") + 39 + 1 + 8

    lg._unlink_dl_prefix_files(tmp_path / "no_such_dir", ".sdlab_dl_x")  # not a directory: a no-op
    (root / ".sdlab_dl_x.part.0000").write_bytes(b"1")
    (root / ".sdlab_dl_x.manifest.json").write_bytes(b"2")
    (root / ".sdlab_dl_y.part.0000").write_bytes(b"3")
    lg._unlink_dl_prefix_files(root, ".sdlab_dl_x")
    assert sorted(p.name for p in root.iterdir() if p.name.startswith(".sdlab_dl_")) == [".sdlab_dl_y.part.0000"]


def test_download_split_refuses_low_disk_before_any_part_is_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "content"
    root.mkdir()
    data = os.urandom(300)
    (root / "big.tar.gz").write_bytes(data)
    # `free_b < size + 16 MiB` is the whole check: one byte short of the headroom refuses, exactly size + 16 MiB free goes ahead.
    rec = lg.prepare_single_content_download(root, "big.tar.gz", 100, free_bytes_override=len(data) + 16 * 1024 * 1024 - 1)
    assert rec["split_failed"] is True and rec["error_code"] == "DOWNLOAD_SPLIT_DISK_LOW"
    assert rec["free_bytes"] == len(data) + 16 * 1024 * 1024 - 1 and rec["whole_bytes"] == len(data)
    assert f"only {len(data) + 16 * 1024 * 1024 - 1} bytes are free" in rec["why"] and "16777216 bytes of headroom" in rec["why"]
    assert not [p for p in root.iterdir() if p.name.startswith(".sdlab_dl_")]
    printed = json.loads(capsys.readouterr().out.split("SDLAB_DOWNLOAD_PREPARE_JSON ", 1)[1])
    assert printed["error_code"] == "DOWNLOAD_SPLIT_DISK_LOW"

    ok = lg.prepare_single_content_download(root, "big.tar.gz", 100, free_bytes_override=len(data) + 16 * 1024 * 1024, emit=False)
    assert ok["split"] is True and ok["part_count"] == 3 and "split_failed" not in ok
    manifest = json.loads((root / Path(ok["manifest_remote"]).name).read_text(encoding="utf-8"))
    assert manifest["whole_sha256"] == _sha(data) == ok["whole_sha256"]
    joined = b"".join((root / Path(p["remote_path"]).name).read_bytes() for p in manifest["parts"])
    assert joined == data


def test_download_split_enospc_mid_split_unlinks_partial_parts_and_reports_named_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "content"
    root.mkdir()
    data = os.urandom(450)
    (root / "big.tar.gz").write_bytes(data)
    # The FAKE_VM_SITE hook raises ENOSPC when part 2 is about to be written (parts 0 and 1 exist by then).
    monkeypatch.setenv("FAKE_VM_SITE", "1")
    monkeypatch.setenv("FAKE_VM_DL_SPLIT_ENOSPC_ON_PART", "2")
    rec = lg.prepare_single_content_download(root, "big.tar.gz", 100)
    assert rec["split_failed"] is True and rec["error_code"] == "DOWNLOAD_SPLIT_DISK_LOW"
    assert "failed at part 2" in rec["why"] and "No space left on device" in rec["why"]
    assert not [p for p in root.iterdir() if p.name.startswith(".sdlab_dl_")], "partial parts must be unlinked"
    assert "SDLAB_DOWNLOAD_PREPARE_JSON" in capsys.readouterr().out

    # A real OSError while writing a part (not the injected one) takes the same path, and emit=False prints nothing.
    monkeypatch.delenv("FAKE_VM_DL_SPLIT_ENOSPC_ON_PART")
    monkeypatch.delenv("FAKE_VM_SITE")
    real_open = Path.open

    def _boom(self: Path, mode: str = "r", *a: object, **kw: object) -> object:
        if "wb" in mode and self.name.endswith(".part.0001"):
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_open(self, mode, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", _boom)
    rec2 = lg.prepare_single_content_download(root, "big.tar.gz", 100, emit=False)
    monkeypatch.setattr(Path, "open", real_open)
    assert rec2["split_failed"] is True and "failed at part 1" in rec2["why"]
    assert not [p for p in root.iterdir() if p.name.startswith(".sdlab_dl_")]
    assert capsys.readouterr().out == ""


def test_prepare_content_downloads_skips_non_bundles_and_reports_each_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lg.prepare_content_downloads(tmp_path / "no_such_root", 100) == []
    root = tmp_path / "content"
    root.mkdir()
    assert lg.prepare_content_downloads(root, 0) == []
    (root / "a.tar.gz").write_bytes(b"a" * 10)
    (root / "b.tar.gz").write_bytes(b"b" * 250)
    (root / ".sdlab_dl_old.tar.gz").write_bytes(b"x")
    (root / "notes.txt").write_text("hi", encoding="utf-8")
    recs = lg.prepare_content_downloads(root, 100, free_bytes_override=16 * 1024 * 1024 + 10_000)
    assert [r["rel"] for r in recs] == ["a.tar.gz", "b.tar.gz"]
    assert recs[0]["split"] is False and recs[1]["part_count"] == 3
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1] == "SDLAB_DOWNLOAD_PREPARE_DONE chunk_bytes=100"
    quiet = lg.prepare_content_downloads(root, 100, free_bytes_override=16 * 1024 * 1024 + 10_000, emit=False)
    assert len(quiet) == 2 and capsys.readouterr().out == ""


# --------------------------------------------------------------------------------------------
# remote_runner
# --------------------------------------------------------------------------------------------


def test_remote_runner_scrubs_tokens_resolves_bash_and_loads_launch_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rr.scrub_line("x hf_" + "A" * 20 + " y") == "x hf_[REDACTED] y"
    assert rr.scrub_line("no token here") == "no token here"

    assert rr._resolve_bash({"PATH": os.environ.get("PATH", "")}).endswith(("bash", "bash.exe"))
    assert rr._resolve_bash({"PATH": str(tmp_path)}) == "bash" or os.name == "nt"

    # 1. a directory that holds launch_guards.py is put on sys.path and the module is returned.
    root_with = tmp_path / "with_guards"
    root_with.mkdir()
    (root_with / "launch_guards.py").write_text("MARK = 'with-guards'\n", encoding="utf-8")
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, "launch_guards", raising=False)
    mod = rr._load_launch_guards(root_with)
    assert mod.MARK == "with-guards" and str(root_with) in sys.path

    # 2. neither content_root nor the cwd has it: fall back to the directory of remote_runner.py itself.
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    monkeypatch.chdir(empty_root)
    monkeypatch.delitem(sys.modules, "launch_guards", raising=False)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != str(COLAB_DIR)])
    mod2 = rr._load_launch_guards(empty_root)
    assert hasattr(mod2, "prepare_content_downloads") and str(COLAB_DIR) in sys.path

    # 3. with no __file__ (a `colab exec` cell) and nothing to find, the import is left to sys.path.
    monkeypatch.delitem(sys.modules, "launch_guards", raising=False)
    monkeypatch.setitem(rr._load_launch_guards.__globals__, "__file__", None)
    mod3 = rr._load_launch_guards(empty_root)
    assert hasattr(mod3, "prepare_content_downloads")

    # 4. prepare_content_downloads delegates to the single source.
    content = tmp_path / "content"
    content.mkdir()
    (content / "x.tar.gz").write_bytes(b"x" * 5)
    recs = rr.prepare_content_downloads(content, 100)
    assert recs and recs[0]["rel"] == "x.tar.gz"
    capsys.readouterr()


def test_remote_runner_runs_script_and_prepares_downloads_or_refuses_without_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rr.run_remote_script(env={}) == 2
    cap = capsys.readouterr()
    assert "REFUSED: SDLAB_REMOTE_SCRIPT is required" in cap.err and "SDLAB_REMOTE_RC=2" in cap.out

    content = tmp_path / "content"
    content.mkdir()
    (content / "r.tar.gz").write_bytes(b"r" * 20)
    script = tmp_path / "s.sh"
    script.write_text("echo hello hf_" + "B" * 20 + "\nexit 3\n", encoding="utf-8", newline="\n")
    monkeypatch.delitem(sys.modules, "launch_guards", raising=False)
    env = dict(os.environ)
    env.update({"SDLAB_CONTENT": str(content), "SDLAB_DL_CHUNK_BYTES": "100"})
    rc = rr.run_remote_script(str(script), env=env)
    out = capsys.readouterr().out
    assert rc == 3 and "hello hf_[REDACTED]" in out and "SDLAB_REMOTE_RC=3" in out
    assert "SDLAB_DOWNLOAD_PREPARE_JSON" in out and "SDLAB_DOWNLOAD_PREPARE_DONE chunk_bytes=100" in out


# --------------------------------------------------------------------------------------------
# Part 6: a real --job must state where optimizer_size_bytes came from
# --------------------------------------------------------------------------------------------


def test_optimizer_size_provenance_must_read_measured_or_estimate() -> None:
    f = lr._resolve_optimizer_size_provenance
    assert f(None, {"optimizer_size_source": "measured: runs/rustline_v5/optimizer.pt on the 11-04 run"}, True) == (
        "measured: runs/rustline_v5/optimizer.pt on the 11-04 run", "job_meta")
    assert f("estimate: 2 x 8-bit state of 16-rank LoRA, 160 MiB", {}, True) == (
        "estimate: 2 x 8-bit state of 16-rank LoRA, 160 MiB", "cli")
    # The built-in rungs (--rung-job, not a real job) keep their fixed estimate and need no statement.
    assert f(None, {}, False) == (None, None)
    for bad in (None, "", "guess: about 512 MiB", "measured:", "measured", "estimate:   "):
        with pytest.raises(lr.Refusal) as exc:
            f(bad, {}, True)
        assert exc.value.code == "OPTIMIZER_SIZE_SOURCE_REQUIRED", bad
