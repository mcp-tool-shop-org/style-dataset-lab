"""In-process (import and call) tests for code that subprocess tests exercise:
`lane3_rung.repair_bundle_with_files` and `run_repair_bundle`, the verify-bundle missing /
unreadable / size / sha branches, and the optimizer provenance refusal in `lane3_rung.plan-run`."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COLAB_DIR = REPO_ROOT / "scripts" / "colab"
sys.path.insert(0, str(COLAB_DIR))

import lane3_rung as lr  # noqa: E402


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
