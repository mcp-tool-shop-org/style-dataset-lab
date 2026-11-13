"""Unit tests for scripts/colab/lane1_render.py (Part B.2)."""

from __future__ import annotations

from collections.abc import Iterator
import json
import os
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "colab"))

import lane1_render as l1  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_process_env() -> Iterator[None]:
    """Ensure `HF_HUB_OFFLINE=1` set by `run_weights_download` never leaks into subsequent tests."""
    saved = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def make_minimal_png_with_prompt(prompt_graph: dict[str, Any], seed_byte: int = 1) -> bytes:
    """Create a valid minimal 1x1 RGB PNG containing a ComfyUI `prompt` tEXt chunk."""
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    raw_scanline = bytes([0, seed_byte & 0xFF, (seed_byte * 7) & 0xFF, (seed_byte * 13) & 0xFF])
    idat_data = zlib.compress(raw_scanline)
    idat_crc = zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    base_png = l1.PNG_SIGNATURE + ihdr + idat + iend
    return l1.write_png_text_chunks(base_png, {"prompt": json.dumps(prompt_graph, sort_keys=True)})


class FakeComfyClient:
    """Deterministic fake ComfyUI client for offline CI testing without ComfyUI installed."""

    def __init__(self) -> None:
        self.queued: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self._prompts: dict[str, dict[str, Any]] = {}

    def queue_prompt(self, workflow: dict[str, Any], extra_pnginfo: dict[str, str] | None = None) -> str:
        idx = len(self.queued) + 1
        prompt_id = f"fake_prompt_{idx:03d}"
        self.queued.append((prompt_id, workflow, extra_pnginfo or {}))
        self._prompts[prompt_id] = workflow
        return prompt_id

    def wait_for_completion(self, prompt_id: str, timeout: float = 120.0, poll_interval: float = 0.2) -> dict[str, Any]:
        return {
            "outputs": {
                "3": {
                    "images": [
                        {
                            "filename": f"{prompt_id}.png",
                            "subfolder": "",
                            "type": "output",
                        }
                    ]
                }
            }
        }

    def download_image(self, _comfy_url: str, filename: str, _subfolder: str = "", _img_type: str = "output") -> bytes:
        prompt_id = filename.removesuffix(".png")
        workflow = self._prompts[prompt_id]
        # Deterministic pixel payload derived from workflow JSON so identical jobs yield identical bytes
        digest_byte = int(l1.sha256_bytes(json.dumps(workflow, sort_keys=True).encode("utf-8"))[-2:], 16)
        return make_minimal_png_with_prompt(workflow, seed_byte=digest_byte)


def test_job_compilation_qwen_lora_and_stub_fixture() -> None:
    job = {
        "job_id": "brig_001",
        "prompt": "Portlight brig in broadside profile",
        "negative": "blurry, cropped",
        "seed": 4201,
        "steps": 22,
        "cfg": 3.5,
        "shift": 3.1,
        "width": 1024,
        "height": 1024,
        "loras": [
            {"name": "hull_v1.safetensors", "weight": 0.8},
            {"name": "rig_v1.safetensors", "weight": 0.6},
        ],
    }
    graph = l1.build_qwen_lora_graph(job)
    assert graph["37"]["class_type"] == "UNETLoader"
    assert graph["40"]["class_type"] == "LoraLoaderModelOnly"
    assert graph["40"]["inputs"]["model"] == ["37", 0]
    assert graph["40"]["inputs"]["lora_name"] == "hull_v1.safetensors"
    assert graph["41"]["class_type"] == "LoraLoaderModelOnly"
    assert graph["41"]["inputs"]["model"] == ["40", 0]
    assert graph["66"]["inputs"]["model"] == ["41", 0]
    assert graph["3"]["inputs"]["seed"] == 4201

    stub_graph = l1.build_stub_fixture_graph({"job_id": "stub_01", "seed": 7, "width": 64, "height": 64})
    assert stub_graph["1"]["class_type"] == "EmptyImage"
    assert stub_graph["1"]["inputs"]["width"] == 64
    assert stub_graph["2"]["class_type"] == "ImageInvert"
    assert stub_graph["3"]["class_type"] == "SaveImage"


def test_stamp_write_and_read_back_and_validation(tmp_path: Path) -> None:
    raw_png = make_minimal_png_with_prompt({"1": {"class_type": "EmptyImage"}}, seed_byte=5)
    stamp = {
        "owner": "mcp-tool-shop",
        "licence": "CC-BY-4.0",
        "credit": "mcp-tool-shop",
        "canon_sha": "a881cb5ba656e0618080d2269498fda7f36ac93a",
        "entry_id": "ships/brig",
        "entry_sha256": "sha256:" + "11" * 32,
        "run_id": "run_2026-11-05_001",
        "workflow_sha": "sha256:" + "22" * 32,
        "window_id": "win_lane1_stub_01",
    }
    stamped_bytes = l1.stamp_png_provenance(raw_png, stamp)
    png_path = tmp_path / "stamped.png"
    png_path.write_bytes(stamped_bytes)

    read_back = l1.verify_png_provenance(png_path, stamp)
    assert read_back["owner"] == "mcp-tool-shop"
    assert read_back["licence"] == "CC-BY-4.0"
    assert read_back["credit"] == "mcp-tool-shop"
    assert read_back["entry_id"] == "ships/brig"
    assert read_back["window_id"] == "win_lane1_stub_01"

    with pytest.raises(ValueError, match="PNG_STAMP_MISMATCH"):
        l1.verify_png_provenance(png_path, {**stamp, "owner": "wrong-owner"})

    with pytest.raises(ValueError, match="PNG_STAMP_MISMATCH"):
        l1.verify_png_provenance(png_path, {**stamp, "credit": "wrong-credit"})

    with pytest.raises(ValueError, match="PNG_STAMP_MISSING"):
        l1.stamp_png_provenance(raw_png, {"owner": "mcp-tool-shop"})


def test_copy_back_cadence_and_resume_after_deliberate_kill_with_fake_client(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.jsonl"
    renders_path = tmp_path / "renders.jsonl"
    out_dir = tmp_path / "out"
    copy_back_dir = tmp_path / "copy_back"

    jobs = [
        {
            "job_id": f"job_{i:02d}",
            "run_id": "run_stub_001",
            "template_id": "stub_fixture_64",
            "seed": 100 + i,
            "width": 64,
            "height": 64,
            "canon_sha": "a881cb5ba656e0618080d2269498fda7f36ac93a",
            "entry_id": "ships/brig",
            "entry_sha256": "sha256:" + f"{i:02x}" * 32,
            "workflow_sha": "sha256:" + "ab" * 32,
        }
        for i in (1, 2, 3)
    ]
    jobs_path.write_text("\n".join(json.dumps(j) for j in jobs) + "\n", encoding="utf-8")

    fake_client_1 = FakeComfyClient()
    summary_1 = l1.run_queue(
        jobs_path=jobs_path,
        renders_path=renders_path,
        out_dir=out_dir,
        comfy_url="http://127.0.0.1:8188",
        window_id="win_lane1_test",
        copy_back_dir=copy_back_dir,
        copy_back_every=2,
        kill_after=1,
        client=fake_client_1,
        image_downloader=fake_client_1.download_image,
        system_stats_fetcher=lambda _url: {"system": {"os": "posix"}, "devices": [{"type": "cpu"}]},
    )
    assert summary_1["killed_early"] is True
    assert summary_1["rendered"] == 1
    assert summary_1["skipped"] == 0
    assert summary_1["copy_backs"] == 0
    assert len(fake_client_1.queued) == 1

    job1_png = out_dir / "job_01.png"
    assert job1_png.exists()
    sha_before_resume = l1.sha256_file(job1_png)

    # Resume with a fresh FakeComfyClient: job_01 must be skipped, jobs 2 and 3 rendered,
    # copy_back triggered on cadence (copy_back_every=2), and job_01 hash identical before & after.
    fake_client_2 = FakeComfyClient()
    summary_2 = l1.run_queue(
        jobs_path=jobs_path,
        renders_path=renders_path,
        out_dir=out_dir,
        comfy_url="http://127.0.0.1:8188",
        window_id="win_lane1_test",
        copy_back_dir=copy_back_dir,
        copy_back_every=2,
        kill_after=None,
        client=fake_client_2,
        image_downloader=fake_client_2.download_image,
        system_stats_fetcher=lambda _url: {"system": {"os": "posix"}, "devices": [{"type": "cpu"}]},
    )
    assert summary_2["killed_early"] is False
    assert summary_2["skipped"] == 1
    assert summary_2["rendered"] == 2
    assert summary_2["copy_backs"] == 1
    assert len(fake_client_2.queued) == 2

    sha_after_resume = l1.sha256_file(job1_png)
    assert sha_after_resume == sha_before_resume
    assert l1.sha256_file(copy_back_dir / "job_01.png") == sha_before_resume
    assert l1.sha256_file(copy_back_dir / "job_02.png") == l1.sha256_file(out_dir / "job_02.png")
    assert l1.sha256_file(copy_back_dir / "job_03.png") == l1.sha256_file(out_dir / "job_03.png")

    rows = [json.loads(line) for line in renders_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["job_id"] for r in rows] == ["job_01", "job_02", "job_03"]
    assert rows[0]["png_sha256"] == sha_before_resume


def test_loopback_guards_and_weight_staging_and_window_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert l1.assert_loopback_url("http://127.0.0.1:8188") == ("127.0.0.1", 8188)
    with pytest.raises(ValueError, match="LANE1_NON_LOOPBACK_BIND"):
        l1.assert_loopback_url("http://0.0.0.0:8188")

    assert l1.verify_loopback_sockets(["127.0.0.1:8188"], 8188) == ["127.0.0.1:8188"]
    with pytest.raises(ValueError, match="LANE1_NON_LOOPBACK_SOCKET"):
        l1.verify_loopback_sockets(["0.0.0.0:8188"], 8188)
    with pytest.raises(ValueError, match="LANE1_COMFY_SOCKET_NOT_FOUND"):
        l1.verify_loopback_sockets(["127.0.0.1:9999"], 8188)

    weight_file = tmp_path / "dummy.safetensors"
    weight_file.write_bytes(b"safedatabytes")
    w_sha = l1.sha256_file(weight_file)
    manifest_path = tmp_path / "weights.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "name": "dummy.safetensors",
                    "sha256": w_sha,
                    "licence_id": "Apache-2.0",
                    "licence_url": "https://www.apache.org/licenses/LICENSE-2.0",
                    "date_read": "2026-10-25",
                    "local_path": str(weight_file),
                }
            ]
        ),
        encoding="utf-8",
    )
    staged = l1.stage_weights(manifest_path)
    assert len(staged) == 1
    assert staged[0]["verified"] is True

    win_path = tmp_path / "window.json"
    rec = l1.write_window_json(
        win_path,
        window_id="win_01",
        comfy_url="http://127.0.0.1:8188",
        system_python="3.13.16",
        sockets=["127.0.0.1:8188"],
        expected_python=l1.sys.version.split()[0],
    )
    assert rec["window_id"] == "win_01"
    assert rec["comfy_bind"] == "127.0.0.1:8188"

    with pytest.raises(ValueError, match="LANE1_PYTHON_VERSION_MISMATCH"):
        l1.write_window_json(
            win_path,
            window_id="win_01",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            sockets=["127.0.0.1:8188"],
            expected_python="0.0.0",
        )

    # Fallback chunk readers and validation error branches
    sample_png = make_minimal_png_with_prompt({"1": {"class_type": "EmptyImage"}}, seed_byte=9)
    fb_chunks = l1._read_png_text_chunks_fallback(sample_png)
    assert "prompt" in fb_chunks
    fb_meta = l1._read_workflow_metadata_fallback(sample_png)
    assert fb_meta.has_prompt is True
    with pytest.raises(ValueError, match="PNG_INVALID"):
        l1._read_png_text_chunks_fallback(b"not_a_png")
    with pytest.raises(ValueError, match="PNG_INVALID"):
        l1.write_png_text_chunks(b"not_a_png", {"k": "v"})

    assert l1.normalize_sha256(None) is None
    assert l1.normalize_sha256("not_a_hex_sha") is None
    assert l1.unwrap_text_val(None) is None
    assert l1.unwrap_text_val('"hello"') == "hello"
    assert l1.unwrap_text_val('"unterminated\\') == '"unterminated\\'

    with pytest.raises(ValueError, match="LANE1_COMFY_SOCKET_NOT_FOUND"):
        l1.verify_loopback_sockets([], 8188)
    assert l1.verify_loopback_sockets(["127.0.0.1:8188", "0.0.0.0:22", "[::]:22"], 8188) == ["127.0.0.1:8188"]
    assert l1.verify_loopback_sockets(["no_colon", "127.0.0.1:badport", "127.0.0.1:8188"], 8188) == ["127.0.0.1:8188"]

    # Weight staging error branches
    empty_m = tmp_path / "empty_m.json"
    empty_m.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="LANE1_WEIGHT_MANIFEST_EMPTY"):
        l1.stage_weights(empty_m)

    bad_sha_m = tmp_path / "bad_sha_m.json"
    bad_sha_m.write_text('[{"name": "x.safetensors", "sha256": "bad"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="LANE1_WEIGHT_SHA_MISSING"):
        l1.stage_weights(bad_sha_m)

    bad_lic_m = tmp_path / "bad_lic_m.json"
    bad_lic_m.write_text(
        json.dumps([{"name": "x.safetensors", "sha256": w_sha, "licence_id": "NC-1.0"}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LANE1_WEIGHT_LICENCE_INVALID"):
        l1.stage_weights(bad_lic_m)

    missing_f_m = tmp_path / "missing_f_m.json"
    missing_f_m.write_text(
        json.dumps(
            [
                {
                    "name": "x.safetensors",
                    "sha256": w_sha,
                    "licence_id": "Apache-2.0",
                    "licence_url": "https://apache.org",
                    "date_read": "2026-10-25",
                    "local_path": str(tmp_path / "missing.safetensors"),
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LANE1_WEIGHT_FILE_MISSING"):
        l1.stage_weights(missing_f_m)

    mismatch_m = tmp_path / "mismatch_m.json"
    mismatch_m.write_text(
        json.dumps(
            [
                {
                    "name": "dummy.safetensors",
                    "sha256": "0" * 64,
                    "licence_id": "Apache-2.0",
                    "licence_url": "https://apache.org",
                    "date_read": "2026-10-25",
                    "local_path": str(weight_file),
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LANE1_WEIGHT_SHA_MISMATCH"):
        l1.stage_weights(mismatch_m)

    # CLI main() invocation with hermetic /proc fixture directory (ComfyUI + wildcard sshd)
    proc_fixture = tmp_path / "proc_cli"
    (proc_fixture / "net").mkdir(parents=True)
    (proc_fixture / "4242" / "fd").mkdir(parents=True)
    (proc_fixture / "4242" / "fd" / "3").write_text("socket:[12345]\n", encoding="utf-8")
    (proc_fixture / "net" / "tcp").write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:1FFC 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0\n"
        "   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22001 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    (proc_fixture / "net" / "tcp6").write_text(
        "  sl  local_address                         rem_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 00000000000000000000000000000000:0016 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22002 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SDLAB_EXPECTED_PYTHON", l1.sys.version.split()[0])
    cli_win_path = tmp_path / "cli_win.json"
    cli_rc = l1.main(
        [
            "--cpu",
            "--bootstrap",
            "--comfy-pid",
            "4242",
            "--proc-root",
            str(proc_fixture),
            "--window-json",
            str(cli_win_path),
            "--weight-manifest",
            str(manifest_path),
            "--system-python-bin",
            l1.sys.executable,
        ]
    )
    assert cli_rc == 0
    cli_win = json.loads(cli_win_path.read_text(encoding="utf-8"))
    assert cli_win["listening_sockets"] == ["127.0.0.1:8188"]
    assert cli_win["other_listeners"] == ["0.0.0.0:22", "[::]:22"]


def test_real_vm_facts_proc_net_tcp_ss_and_system_python_without_defaults(tmp_path: Path) -> None:
    proc_tcp = tmp_path / "proc_net_tcp"
    proc_tcp.write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:1FFC 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0\n"
        "   1: 0100007F:1FFC 0100007F:C350 01 00000000:00000000 00:00000000 00000000     0        0 12346 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    parsed_v4 = l1.parse_proc_net_tcp(proc_tcp.read_text(encoding="utf-8"), ipv6=False)
    assert parsed_v4 == ["127.0.0.1:8188"]

    proc_tcp6 = tmp_path / "proc_net_tcp6"
    proc_tcp6.write_text(
        "  sl  local_address                         rem_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 00000000000000000000000001000000:1FFC 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12347 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    parsed_v6 = l1.parse_proc_net_tcp(proc_tcp6.read_text(encoding="utf-8"), ipv6=True)
    assert parsed_v6 == ["[::1]:8188"]

    ss_sample = (
        "State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess\n"
        "LISTEN 0      128        127.0.0.1:8188      0.0.0.0:*\n"
        "LISTEN 0      128            [::1]:8188         [::]:*\n"
    )
    assert l1.parse_ss_tln(ss_sample) == ["127.0.0.1:8188", "[::1]:8188"]

    probed_socks = l1.probe_listening_sockets(proc_net_tcp=proc_tcp, proc_net_tcp6=proc_tcp6)
    assert probed_socks == ["127.0.0.1:8188", "[::1]:8188"]

    probed_py = l1.probe_system_python(runner=lambda _cmd: "Python 3.13.16\n")
    assert probed_py == "3.13.16"
    with pytest.raises(ValueError, match="LANE1_NO_MEASURED_SYSTEM_PYTHON"):
        l1.probe_system_python(runner=lambda _cmd: "")

    # No fallback to [f"{host}:{port}"] when OS socket tables yield no listening sockets
    with pytest.raises(ValueError, match="LANE1_NO_MEASURED_SOCKETS"):
        l1.write_window_json(
            tmp_path / "no_socks_win.json",
            window_id="win_no_socks",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            proc_net_tcp=tmp_path / "nonexistent_tcp",
            proc_net_tcp6=tmp_path / "nonexistent_tcp6",
            ss_runner=lambda: "",
        )

    # Wildcard 0.0.0.0:8188 in /proc/net/tcp is caught and refused
    wildcard_tcp = tmp_path / "wildcard_tcp"
    wildcard_tcp.write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 00000000:1FFC 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LANE1_NON_LOOPBACK_SOCKET"):
        l1.write_window_json(
            tmp_path / "wild_win.json",
            window_id="win_wild",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            proc_net_tcp=wildcard_tcp,
            proc_net_tcp6=tmp_path / "nonexistent_tcp6",
        )

    # write_window_json measures both system_python and listening_sockets when not supplied
    measured_win = l1.write_window_json(
        tmp_path / "measured_win.json",
        window_id="win_measured",
        comfy_url="http://127.0.0.1:8188",
        expected_python=l1.sys.version.split()[0],
        proc_net_tcp=proc_tcp,
        proc_net_tcp6=proc_tcp6,
        system_python_runner=lambda _cmd: "Python 3.13.16\n",
    )
    assert measured_win["system_python"] == "3.13.16"
    assert measured_win["listening_sockets"] == ["127.0.0.1:8188", "[::1]:8188"]
    assert measured_win["other_listeners"] == []


def test_hermetic_proc_comfy_socket_guard_and_other_listeners(tmp_path: Path) -> None:
    """Hermetic /proc fixture tests for ComfyUI socket inode/port guard and other_listeners."""
    tcp_header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    tcp6_header = "  sl  local_address                         rem_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"

    # Case 1: ComfyUI on loopback (127.0.0.1:8188 + [::1]:8188) with unrelated wildcard sshd (0.0.0.0:22 + [::]:22)
    proc_ok = tmp_path / "proc_ok"
    (proc_ok / "net").mkdir(parents=True)
    (proc_ok / "4242" / "fd").mkdir(parents=True)
    (proc_ok / "4242" / "fd" / "3").write_text("socket:[12345]\n", encoding="utf-8")
    (proc_ok / "4242" / "fd" / "4").write_text("socket:[12347]\n", encoding="utf-8")
    (proc_ok / "net" / "tcp").write_text(
        tcp_header
        + "   0: 0100007F:1FFC 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0\n"
        + "   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22001 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    (proc_ok / "net" / "tcp6").write_text(
        tcp6_header
        + "   0: 00000000000000000000000001000000:1FFC 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12347 1 0000000000000000 100 0 0 10 0\n"
        + "   1: 00000000000000000000000000000000:0016 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22002 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )

    # Port fallback when /proc/<pid>/fd is absent passes and records sshd in other_listeners
    win_port_ok = l1.write_window_json(
        tmp_path / "win_port_ok.json",
        window_id="win_port_ok",
        comfy_url="http://127.0.0.1:8188",
        system_python="3.13.16",
        expected_python=l1.sys.version.split()[0],
        proc_net_tcp=proc_ok / "net" / "tcp",
        proc_net_tcp6=proc_ok / "net" / "tcp6",
    )
    assert win_port_ok["listening_sockets"] == ["127.0.0.1:8188", "[::1]:8188"]
    assert win_port_ok["other_listeners"] == ["0.0.0.0:22", "[::]:22"]

    win_pid_ok = l1.write_window_json(
        tmp_path / "win_pid_ok.json",
        window_id="win_pid_ok",
        comfy_url="http://127.0.0.1:8188",
        system_python="3.13.16",
        expected_python=l1.sys.version.split()[0],
        comfy_pid=4242,
        proc_root=proc_ok,
    )
    assert win_pid_ok["listening_sockets"] == ["127.0.0.1:8188", "[::1]:8188"]
    assert win_pid_ok["other_listeners"] == ["0.0.0.0:22", "[::]:22"]

    # Case 2: ComfyUI on 0.0.0.0 or [::] refuses with LANE1_NON_LOOPBACK_SOCKET
    proc_wild_v4 = tmp_path / "proc_wild_v4"
    (proc_wild_v4 / "net").mkdir(parents=True)
    (proc_wild_v4 / "4242" / "fd").mkdir(parents=True)
    (proc_wild_v4 / "4242" / "fd" / "3").write_text("socket:[55501]\n", encoding="utf-8")
    (proc_wild_v4 / "net" / "tcp").write_text(
        tcp_header + "   0: 00000000:1FFC 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 55501 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LANE1_NON_LOOPBACK_SOCKET"):
        l1.write_window_json(
            tmp_path / "win_wild_v4.json",
            window_id="win_wild_v4",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            comfy_pid=4242,
            proc_root=proc_wild_v4,
        )

    proc_wild_v6 = tmp_path / "proc_wild_v6"
    (proc_wild_v6 / "net").mkdir(parents=True)
    (proc_wild_v6 / "4242" / "fd").mkdir(parents=True)
    (proc_wild_v6 / "4242" / "fd" / "3").write_text("socket:[55502]\n", encoding="utf-8")
    (proc_wild_v6 / "net" / "tcp6").write_text(
        tcp6_header + "   0: 00000000000000000000000000000000:1FFC 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 55502 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LANE1_NON_LOOPBACK_SOCKET"):
        l1.write_window_json(
            tmp_path / "win_wild_v6.json",
            window_id="win_wild_v6",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            comfy_pid=4242,
            proc_root=proc_wild_v6,
        )

    # Case 3: No socket found for the ComfyUI PID or port refuses with LANE1_COMFY_SOCKET_NOT_FOUND
    proc_no_pid_sock = tmp_path / "proc_no_pid_sock"
    (proc_no_pid_sock / "net").mkdir(parents=True)
    (proc_no_pid_sock / "4242" / "fd").mkdir(parents=True)
    (proc_no_pid_sock / "4242" / "fd" / "3").write_text("socket:[99999]\n", encoding="utf-8")
    (proc_no_pid_sock / "net" / "tcp").write_text(
        tcp_header + "   0: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22001 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LANE1_COMFY_SOCKET_NOT_FOUND"):
        l1.write_window_json(
            tmp_path / "win_no_pid_sock.json",
            window_id="win_no_pid_sock",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            comfy_pid=4242,
            proc_root=proc_no_pid_sock,
        )

    with pytest.raises(ValueError, match="LANE1_COMFY_SOCKET_NOT_FOUND"):
        l1.write_window_json(
            tmp_path / "win_no_port_sock.json",
            window_id="win_no_port_sock",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            proc_net_tcp=proc_no_pid_sock / "net" / "tcp",
        )


def test_comfy_pid_fd_fail_closed_and_socket_match_mode_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 4: fail closed when comfy_pid is given and fd dir is absent or unreadable; record socket_match and comfy_pid."""
    tcp_header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    proc_fx = tmp_path / "proc_fx"
    (proc_fx / "net").mkdir(parents=True)
    (proc_fx / "4242" / "fd").mkdir(parents=True)
    (proc_fx / "4242" / "fd" / "3").write_text("socket:[12345]\n", encoding="utf-8")
    (proc_fx / "net" / "tcp").write_text(
        tcp_header
        + "   0: 0100007F:1FFC 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0\n"
        + "   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22001 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )

    # 1. PID given, fd dir absent -> refuses LANE1_COMFY_PID_FD_UNREADABLE (no fallback to port)
    with pytest.raises(ValueError, match="LANE1_COMFY_PID_FD_UNREADABLE"):
        l1.write_window_json(
            tmp_path / "win_absent_fd.json",
            window_id="win_absent_fd",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            comfy_pid=9999,
            proc_root=proc_fx,
        )

    # 2. PID given, iterdir raises PermissionError (monkeypatched) -> refuses LANE1_COMFY_PID_FD_UNREADABLE
    orig_iterdir = Path.iterdir
    fd_target = proc_fx / "4242" / "fd"

    def _deny_iterdir(self: Path):  # type: ignore[no-untyped-def]
        if self == fd_target:
            raise PermissionError("Permission denied reading /proc/4242/fd")
        return orig_iterdir(self)

    with monkeypatch.context() as mp:
        mp.setattr(Path, "iterdir", _deny_iterdir)
        with pytest.raises(ValueError, match="LANE1_COMFY_PID_FD_UNREADABLE"):
            l1.write_window_json(
                tmp_path / "win_perm_fd.json",
                window_id="win_perm_fd",
                comfy_url="http://127.0.0.1:8188",
                system_python="3.13.16",
                expected_python=l1.sys.version.split()[0],
                comfy_pid=4242,
                proc_root=proc_fx,
            )

    # 3. No PID, port mode -> socket_match == "port" and comfy_pid is None; inode mode -> socket_match == "inode" and comfy_pid recorded
    win_port = l1.write_window_json(
        tmp_path / "win_port_mode.json",
        window_id="win_port_mode",
        comfy_url="http://127.0.0.1:8188",
        system_python="3.13.16",
        expected_python=l1.sys.version.split()[0],
        proc_net_tcp=proc_fx / "net" / "tcp",
    )
    assert win_port["socket_match"] == "port"
    assert win_port["comfy_pid"] is None

    win_inode = l1.write_window_json(
        tmp_path / "win_inode_mode.json",
        window_id="win_inode_mode",
        comfy_url="http://127.0.0.1:8188",
        system_python="3.13.16",
        expected_python=l1.sys.version.split()[0],
        comfy_pid=4242,
        proc_root=proc_fx,
    )
    assert win_inode["socket_match"] == "inode"
    assert win_inode["comfy_pid"] == 4242

    # 4. Single prefix on LANE1_NO_MEASURED_SOCKETS (not doubled with LANE1_COMFY_SOCKET_NOT_FOUND)
    with pytest.raises(ValueError, match=r"^LANE1_NO_MEASURED_SOCKETS: no listening TCP sockets"):
        l1.write_window_json(
            tmp_path / "win_no_socks_single_code.json",
            window_id="win_no_socks_single_code",
            comfy_url="http://127.0.0.1:8188",
            system_python="3.13.16",
            expected_python=l1.sys.version.split()[0],
            proc_net_tcp=tmp_path / "missing_tcp",
            proc_net_tcp6=tmp_path / "missing_tcp6",
            ss_runner=lambda: "",
        )


def _make_safetensors_blob(tag: bytes = b"WEIGHT_BLOB", *, truncate: bool = False) -> bytes:
    data = tag * 16
    hdr = json.dumps(
        {"w": {"dtype": "U8", "shape": [len(data)], "data_offsets": [0, len(data)]}},
        separators=(",", ":"),
    ).encode("utf-8")
    blob = struct.pack("<Q", len(hdr)) + hdr + data
    return blob[:-8] if truncate else blob


def test_validate_weights_manifest_and_render_jobs_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib

    # Missing, malformed, and empty manifests
    with pytest.raises(l1.Refusal) as exc_info:
        l1.validate_weights_manifest(tmp_path / "missing_manifest.json")
    assert exc_info.value.code == "WEIGHTS_MANIFEST_INVALID"

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not-json", encoding="utf-8")
    with pytest.raises(l1.Refusal) as exc_info:
        l1.validate_weights_manifest(bad_json)
    assert exc_info.value.code == "WEIGHTS_MANIFEST_INVALID"

    empty_list = tmp_path / "empty.json"
    empty_list.write_text("[]\n", encoding="utf-8")
    with pytest.raises(l1.Refusal) as exc_info:
        l1.validate_weights_manifest(empty_list)
    assert exc_info.value.code == "WEIGHTS_MANIFEST_INVALID"

    non_dict = tmp_path / "non_dict.json"
    non_dict.write_text('["not_an_object"]\n', encoding="utf-8")
    with pytest.raises(l1.Refusal) as exc_info:
        l1.validate_weights_manifest(non_dict)
    assert exc_info.value.code == "WEIGHTS_MANIFEST_INVALID"

    valid_item = {
        "repo": "Qwen/Qwen-Image",
        "revision": "a" * 40,
        "file": "qwen_image_fp8.safetensors",
        "dest": "diffusion_models",
        "sha256": "sha256:" + "b" * 64,
        "licence_id": "Apache-2.0",
    }
    manifest_bad_cases = [
        ({k: v for k, v in valid_item.items() if k != "licence_id"}, "WEIGHTS_LICENCE_INVALID"),
        ({**valid_item, "licence_id": "Proprietary-Unknown"}, "WEIGHTS_LICENCE_INVALID"),
        ({**valid_item, "repo": "bad repo without slash"}, "WEIGHTS_MANIFEST_INVALID"),
        ({**valid_item, "revision": "main"}, "WEIGHTS_REVISION_INVALID"),
        ({**valid_item, "file": "../escape.safetensors"}, "WEIGHTS_MANIFEST_INVALID"),
        ({**valid_item, "dest": "checkpoints"}, "WEIGHTS_DEST_INVALID"),
        ({**valid_item, "sha256": "short"}, "WEIGHTS_MANIFEST_INVALID"),
    ]
    for idx, (row_obj, expected_code) in enumerate(manifest_bad_cases):
        p = tmp_path / f"bad_manifest_{idx}.json"
        p.write_text(json.dumps([row_obj]), encoding="utf-8")
        with pytest.raises(l1.Refusal) as exc_info:
            l1.validate_weights_manifest(p)
        assert exc_info.value.code == expected_code

    good_manifest = tmp_path / "good_manifest.json"
    good_manifest.write_text(json.dumps([{**valid_item, "hf_token_required": True}]), encoding="utf-8")
    parsed_manifest = l1.validate_weights_manifest(good_manifest)
    assert parsed_manifest[0]["sha256"] == "b" * 64
    assert parsed_manifest[0]["hf_token_required"] is True

    # Jobs validation refusals (and prompt privacy check)
    valid_job = {
        "job_id": "job_01",
        "run_id": "run_01",
        "template_id": "qwen_txt2img_lora",
        "prompt": "PRIVATE_PROMPT_MARKER_9911",
        "seed": 42,
        "width": 512,
        "height": 512,
        "steps": 20,
        "canon_sha": "a" * 40,
        "entry_id": "ships/brig",
        "entry_sha256": "sha256:" + "1" * 64,
        "licence": "CC-BY-4.0",
        "credit": "mcp-tool-shop",
    }
    good_jobs = tmp_path / "good_jobs.jsonl"
    good_jobs.write_text(json.dumps(valid_job) + "\n", encoding="utf-8")
    good_jobs_sha = hashlib.sha256(good_jobs.read_bytes()).hexdigest()

    with pytest.raises(l1.Refusal) as exc_info:
        l1.validate_render_jobs(good_jobs, "not-64-hex")
    assert exc_info.value.code == "RENDER_JOBS_SHA_REQUIRED"

    with pytest.raises(l1.Refusal) as exc_info:
        l1.validate_render_jobs(tmp_path / "missing.jsonl", good_jobs_sha)
    assert exc_info.value.code == "JOBS_FILE_MISSING"

    with pytest.raises(l1.Refusal) as exc_info:
        l1.validate_render_jobs(good_jobs, "0" * 64)
    assert exc_info.value.code == "JOBS_SHA_MISMATCH"

    def _write_jobs_text(name: str, text: str) -> tuple[Path, str]:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        return p, hashlib.sha256(p.read_bytes()).hexdigest()

    job_bad_cases = [
        ("empty.jsonl", "\n", "RENDER_JOB_INVALID"),
        ("badjson.jsonl", "{broken\n", "RENDER_JOB_INVALID"),
        ("nonobj.jsonl", "[1,2,3]\n", "RENDER_JOB_INVALID"),
        ("badid.jsonl", json.dumps({**valid_job, "job_id": "../bad"}) + "\n", "RENDER_JOB_INVALID"),
        ("dupid.jsonl", (json.dumps(valid_job) + "\n") * 2, "RENDER_JOB_INVALID"),
        ("stubtpl.jsonl", json.dumps({**valid_job, "template_id": "stub_fixture_64"}) + "\n", "JOB_TEMPLATE_INVALID"),
        ("norun.jsonl", json.dumps({**valid_job, "run_id": ""}) + "\n", "RENDER_JOB_INVALID"),
        ("badcanon.jsonl", json.dumps({**valid_job, "canon_sha": "shortsha"}) + "\n", "RENDER_JOB_INVALID"),
        ("badentrysha.jsonl", json.dumps({**valid_job, "entry_sha256": "not-a-sha"}) + "\n", "RENDER_JOB_INVALID"),
        ("badlic.jsonl", json.dumps({**valid_job, "licence": "MIT"}) + "\n", "RENDER_JOB_INVALID"),
        ("nocredit.jsonl", json.dumps({k: v for k, v in valid_job.items() if k != "credit"}) + "\n", "RENDER_JOB_INVALID"),
        ("badcredit.jsonl", json.dumps({**valid_job, "credit": "wrong-credit"}) + "\n", "RENDER_JOB_INVALID"),
        ("noprompt.jsonl", json.dumps({**valid_job, "prompt": "   "}) + "\n", "RENDER_JOB_INVALID"),
        ("boolseed.jsonl", json.dumps({**valid_job, "seed": True}) + "\n", "RENDER_JOB_INVALID"),
        ("badsize.jsonl", json.dumps({**valid_job, "width": 0}) + "\n", "RENDER_JOB_INVALID"),
        ("badsteps.jsonl", json.dumps({**valid_job, "steps": 0}) + "\n", "RENDER_JOB_INVALID"),
    ]
    for fname, body, expected_code in job_bad_cases:
        jp, jsha = _write_jobs_text(fname, body)
        with pytest.raises(l1.Refusal) as exc_info:
            l1.validate_render_jobs(jp, jsha)
        assert exc_info.value.code == expected_code
        assert "PRIVATE_PROMPT_MARKER_9911" not in exc_info.value.detail

    # run_validate_inputs & main --validate-render-inputs (including HF_READ_TOKEN_MISSING)
    monkeypatch.delenv("HF_TOKEN_GGUF_READ", raising=False)
    rc_missing_tok = l1.main(
        [
            "--validate-render-inputs",
            "--weights-manifest",
            str(good_manifest),
            "--jobs",
            str(good_jobs),
            "--jobs-sha256",
            good_jobs_sha,
        ]
    )
    assert rc_missing_tok == 1
    assert "REFUSED: HF_READ_TOKEN_MISSING:" in capsys.readouterr().err

    assert l1.main(["--validate-render-inputs"]) == 1
    assert "REFUSED: RENDER_MANIFEST_REQUIRED:" in capsys.readouterr().err

    monkeypatch.setenv("HF_TOKEN_GGUF_READ", "hf_unitTestToken1234567890")
    with pytest.raises(l1.Refusal) as exc_info:
        l1.run_validate_inputs(manifest_path=good_manifest, jobs_path=None, jobs_sha256=None, allow_no_jobs=False)
    assert exc_info.value.code == "RENDER_JOBS_REQUIRED"

    rc_ok = l1.main(
        [
            "--validate-render-inputs",
            "--weights-manifest",
            str(good_manifest),
            "--jobs",
            str(good_jobs),
            "--jobs-sha256",
            good_jobs_sha,
        ]
    )
    assert rc_ok == 0
    assert "RENDER_INPUTS_OK " in capsys.readouterr().out


def test_lane1_gpu_smoke_and_vm_guards_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_site = REPO_ROOT / "tests" / "colab" / "fixtures" / "fake_vm_site"
    monkeypatch.syspath_prepend(str(fake_site))
    import importlib

    fake_torch = importlib.import_module("torch")

    # Happy GPU smoke
    ticks = iter([0.0, 0.02, 0.06, 0.06])
    smoke_rec = l1.lane1_gpu_smoke(torch_mod=fake_torch, clock=lambda: next(ticks, 0.1), target_s=0.05)
    assert smoke_rec["device_name"] == "NVIDIA A100-SXM4-80GB"
    assert smoke_rec["matmul_iters"] >= 64

    # No CUDA available
    monkeypatch.setenv("FAKE_VM_GPU_SMOKE", "no_cuda")
    with pytest.raises(RuntimeError, match="is_available"):
        l1.lane1_gpu_smoke(torch_mod=fake_torch, target_s=0.01)
    monkeypatch.delenv("FAKE_VM_GPU_SMOKE", raising=False)

    # Non-finite matmul check
    class _NanTorch:
        __version__ = "2.15.0+cu130"
        bfloat16 = "bfloat16"
        version = fake_torch.version
        cuda = fake_torch.cuda
        device = staticmethod(fake_torch.device)
        randn = staticmethod(fake_torch.randn)

        @staticmethod
        def isfinite(_t: Any) -> Any:
            return fake_torch._Bool(False)

    with pytest.raises(RuntimeError, match="not finite"):
        l1.lane1_gpu_smoke(torch_mod=_NanTorch, clock=lambda: 1.0, target_s=0.0)

    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       33554432 kB\nMemAvailable:   25165824 kB\n", encoding="utf-8")
    shm = tmp_path / "shm"
    shm.mkdir()
    hf_home = tmp_path / "hf"
    models_dir = tmp_path / "models"
    lane1_out = tmp_path / "out"
    for d in (hf_home, models_dir, lane1_out):
        d.mkdir()

    class _Usage:
        def __init__(self, free_gib: float) -> None:
            self.total = int(100 * l1.GIB)
            self.used = int((100 - free_gib) * l1.GIB)
            self.free = int(free_gib * l1.GIB)

    # GPU + disk + RAM failures all reported in refusals
    guards_fail = tmp_path / "guards_fail.json"
    rc_fail = l1.run_vm_guards(
        hf_home=hf_home,
        models_dir=models_dir,
        lane1_out=lane1_out,
        disk_required_gib=50.0,
        smoke_seconds=0.01,
        ram_required_gib="64",
        meminfo_path=meminfo,
        shm_path=shm,
        out_path=guards_fail,
        cpu_stub=False,
        smoke_fn=lambda **_kw: (_ for _ in ()).throw(RuntimeError("no gpu")),
        driver_fn=lambda: {"nvidia_smi_rc": 9},
        disk_usage_fn=lambda _p: _Usage(5.0),
    )
    assert rc_fail == 1
    err_txt = capsys.readouterr().err
    assert "REFUSED: GPU_SMOKE_FAILED:" in err_txt
    assert "REFUSED: DISK_FREE_LOW:" in err_txt
    assert "REFUSED: HOST_RAM_LOW:" in err_txt

    # Missing RAM threshold
    rc_noram = l1.run_vm_guards(
        hf_home=hf_home,
        models_dir=models_dir,
        lane1_out=lane1_out,
        disk_required_gib=0.001,
        smoke_seconds=0.01,
        ram_required_gib=None,
        meminfo_path=meminfo,
        shm_path=shm,
        out_path=tmp_path / "guards_noram.json",
        cpu_stub=True,
        disk_usage_fn=lambda _p: _Usage(80.0),
    )
    assert rc_noram == 1
    assert "REFUSED: HOST_RAM_THRESHOLD_MISSING:" in capsys.readouterr().err

    # CLI --vm-guards --cpu-stub pass
    monkeypatch.setenv("SDLAB_TEST_DISK_REQUIRED_GIB", "0.001")
    guards_ok = tmp_path / "guards_ok.json"
    rc_cli = l1.main(
        [
            "--vm-guards",
            "--cpu-stub",
            "--hf-home",
            str(hf_home),
            "--models-dir",
            str(models_dir),
            "--lane1-out",
            str(lane1_out),
            "--ram-required-gib",
            "4",
            "--meminfo",
            str(meminfo),
            "--shm",
            str(shm),
            "--guards-out",
            str(guards_ok),
        ]
    )
    assert rc_cli == 0
    assert json.loads(guards_ok.read_text(encoding="utf-8"))["gpu"]["skipped_cpu_stub"] is True


def test_run_weights_download_merge_facts_and_peak_vram(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib
    import os
    import subprocess

    fake_site = REPO_ROOT / "tests" / "colab" / "fixtures" / "fake_vm_site"
    monkeypatch.syspath_prepend(str(fake_site))
    monkeypatch.setenv(
        "PYTHONPATH",
        str(fake_site) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
    )
    for k in ("HF_HOME", "HF_TOKEN", "HF_TOKEN_GGUF_READ", "HUGGING_FACE_HUB_TOKEN", "HF_HUB_OFFLINE", "FAKE_HF_EXPECT_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    blobs_dir = tmp_path / "blobs"
    blobs_dir.mkdir()
    good_st = _make_safetensors_blob(b"GOOD_VAE_ST")
    (blobs_dir / "vae.safetensors").write_bytes(good_st)
    good_sha = hashlib.sha256(good_st).hexdigest()
    monkeypatch.setenv("FAKE_HF_BLOBS_DIR", str(blobs_dir))

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "repo": "madebyollin/taesd",
                    "revision": "6" * 40,
                    "file": "vae.safetensors",
                    "dest": "vae",
                    "sha256": good_sha,
                    "licence_id": "MIT",
                }
            ]
        ),
        encoding="utf-8",
    )

    # expected_file_bytes matches sibling by filename and refuses missing filenames
    assert l1.expected_file_bytes("madebyollin/taesd", "6" * 40, "vae.safetensors") == len(good_st)
    with pytest.raises(FileNotFoundError):
        l1.expected_file_bytes("madebyollin/taesd", "6" * 40, "other.bin")

    # Missing --weights-manifest on CLI
    assert l1.main(["--download-weights"]) == 1
    assert "REFUSED: RENDER_MANIFEST_REQUIRED:" in capsys.readouterr().err

    # Missing max_seconds
    assert (
        l1.run_weights_download(
            manifest_path=manifest,
            hf_home=tmp_path / "hf0",
            models_dir=tmp_path / "m0",
            max_seconds_raw=None,
            log_path=tmp_path / "dl0.log",
            out_path=tmp_path / "dl0.json",
        )
        == 1
    )
    assert "REFUSED: DOWNLOAD_LIMIT_MISSING:" in capsys.readouterr().err

    # Hub metadata error classification (401 -> MODEL_AUTH_FAILED, 404rev -> MODEL_REVISION_NOT_FOUND)
    for err_mode, exp_code in (("401", "MODEL_AUTH_FAILED"), ("404rev", "MODEL_REVISION_NOT_FOUND")):
        monkeypatch.setenv("FAKE_HF_INFO_ERROR", err_mode)
        rc_err = l1.run_weights_download(
            manifest_path=manifest,
            hf_home=tmp_path / f"hf_{err_mode}",
            models_dir=tmp_path / f"m_{err_mode}",
            max_seconds_raw="60",
            log_path=tmp_path / f"dl_{err_mode}.log",
            out_path=tmp_path / f"dl_{err_mode}.json",
        )
        assert rc_err == 1
        assert f"REFUSED: {exp_code}:" in capsys.readouterr().err
    monkeypatch.delenv("FAKE_HF_INFO_ERROR", raising=False)

    # Probe DOWNLOAD_TOO_SLOW (slow rate against large expected size)
    monkeypatch.setenv("FAKE_HF_STREAM_BYTES", str(50_000_000))
    monkeypatch.setenv("FAKE_HF_RATE_BPS", "5000")
    rc_slow = l1.run_weights_download(
        manifest_path=manifest,
        hf_home=tmp_path / "hf_slow",
        models_dir=tmp_path / "m_slow",
        max_seconds_raw="10",
        probe_seconds=0.1,
        probe_bytes=100,
        poll_s=0.05,
        log_path=tmp_path / "dl_slow.log",
        out_path=tmp_path / "dl_slow.json",
    )
    assert rc_slow == 1
    assert "REFUSED: DOWNLOAD_TOO_SLOW:" in capsys.readouterr().err
    monkeypatch.delenv("FAKE_HF_STREAM_BYTES", raising=False)
    monkeypatch.delenv("FAKE_HF_RATE_BPS", raising=False)

    # Child download failure -> MODEL_DOWNLOAD_FAILED
    monkeypatch.setenv("FAKE_HF_FAIL", "1")
    rc_dlfail = l1.run_weights_download(
        manifest_path=manifest,
        hf_home=tmp_path / "hf_fail",
        models_dir=tmp_path / "m_fail",
        max_seconds_raw="60",
        poll_s=0.02,
        log_path=tmp_path / "dl_fail.log",
        out_path=tmp_path / "dl_fail.json",
    )
    assert rc_dlfail == 1
    assert "REFUSED: MODEL_DOWNLOAD_FAILED:" in capsys.readouterr().err
    monkeypatch.delenv("FAKE_HF_FAIL", raising=False)

    # WEIGHTS_SHA_MISMATCH
    monkeypatch.setenv("FAKE_HF_CORRUPT_SHA", "1")
    rc_shafail = l1.run_weights_download(
        manifest_path=manifest,
        hf_home=tmp_path / "hf_corrupt",
        models_dir=tmp_path / "m_corrupt",
        max_seconds_raw="60",
        poll_s=0.02,
        log_path=tmp_path / "dl_corrupt.log",
        out_path=tmp_path / "dl_corrupt.json",
    )
    assert rc_shafail == 1
    assert "REFUSED: WEIGHTS_SHA_MISMATCH:" in capsys.readouterr().err
    assert not (tmp_path / "m_corrupt" / "vae" / "vae.safetensors").exists()
    monkeypatch.delenv("FAKE_HF_CORRUPT_SHA", raising=False)

    # WEIGHTS_CORRUPT (matching sha256 on truncated safetensors)
    trunc_st = _make_safetensors_blob(b"TRUNCATED_VAE", truncate=True)
    (blobs_dir / "trunc.safetensors").write_bytes(trunc_st)
    trunc_manifest = tmp_path / "trunc_manifest.json"
    trunc_manifest.write_text(
        json.dumps(
            [
                {
                    "repo": "madebyollin/taesd",
                    "revision": "6" * 40,
                    "file": "trunc.safetensors",
                    "dest": "vae",
                    "sha256": hashlib.sha256(trunc_st).hexdigest(),
                    "licence_id": "MIT",
                }
            ]
        ),
        encoding="utf-8",
    )
    rc_trunc = l1.run_weights_download(
        manifest_path=trunc_manifest,
        hf_home=tmp_path / "hf_trunc",
        models_dir=tmp_path / "m_trunc",
        max_seconds_raw="60",
        poll_s=0.02,
        log_path=tmp_path / "dl_trunc.log",
        out_path=tmp_path / "dl_trunc.json",
    )
    assert rc_trunc == 1
    assert "REFUSED: WEIGHTS_CORRUPT:" in capsys.readouterr().err
    assert not (tmp_path / "m_trunc" / "vae" / "trunc.safetensors").exists()

    # Happy authenticated download + log token scrubbing + merge_render_facts
    secret_tok = "hf_unitDownloadSecret998877"
    monkeypatch.setenv("HF_TOKEN_GGUF_READ", secret_tok)
    monkeypatch.setenv("FAKE_HF_EXPECT_TOKEN", secret_tok)
    lane1_out = tmp_path / "lane1_out_ok"
    lane1_out.mkdir()
    dl_log = lane1_out / "weights_download.log"
    dl_json = lane1_out / "weights_download.json"
    rc_good = l1.main(
        [
            "--download-weights",
            "--weights-manifest",
            str(manifest),
            "--hf-home",
            str(tmp_path / "hf_good"),
            "--models-dir",
            str(tmp_path / "m_good"),
            "--max-seconds",
            "60",
            "--probe-seconds",
            "0.1",
            "--probe-bytes",
            "64",
            "--poll-s",
            "0.02",
            "--download-log",
            str(dl_log),
            "--download-out",
            str(dl_json),
        ]
    )
    assert rc_good == 0
    assert secret_tok not in dl_log.read_text(encoding="utf-8")
    assert (tmp_path / "m_good" / "vae" / "vae.safetensors").is_file()
    capsys.readouterr()

    assert (
        l1.main(
            [
                "--merge-render-facts",
                "--lane1-out",
                str(lane1_out),
                "--render-state",
                "rendered",
            ]
        )
        == 0
    )
    merged_win = json.loads((lane1_out / "vm_window.json").read_text(encoding="utf-8"))
    assert merged_win["render"] == "rendered"
    assert merged_win["hf_token_used"] is True
    assert merged_win["weights_download"]["files"][0]["safetensors_verified"] is True

    # read_peak_vram_mib on CUDA stats + smi_runner and on CPU stats
    vram_cuda = l1.read_peak_vram_mib(
        "http://127.0.0.1:8188",
        system_stats_fetcher=lambda _u: {
            "devices": [{"type": "cuda", "name": "cuda:0", "vram_total": 80 * l1.GIB, "vram_free": 68 * l1.GIB, "vram_peak": 15 * l1.GIB}]
        },
        smi_runner=lambda *_a, **_kw: subprocess.CompletedProcess(["nvidia-smi"], 0, "16384\n", ""),
    )
    assert vram_cuda == 16384.0
    vram_cpu = l1.read_peak_vram_mib(
        "http://127.0.0.1:8188",
        system_stats_fetcher=lambda _u: {"devices": [{"type": "cpu", "name": "cpu", "vram_total": 0, "vram_free": 0}]},
    )
    assert vram_cpu == 0.0


def test_lane1_cpu_stub_imports_and_runs_without_lane3_rung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import http.server
    import os
    import shutil
    import subprocess
    import threading
    import time as std_time
    import types
    import urllib.parse

    with pytest.raises(AttributeError):
        _ = l1._nonexistent_attr_for_pep562

    isolated_dir = tmp_path / "stub_content"
    isolated_dir.mkdir()
    isolated_script = isolated_dir / "lane1_render.py"
    shutil.copyfile(REPO_ROOT / "scripts" / "colab" / "lane1_render.py", isolated_script)
    assert not (isolated_dir / "lane3_rung.py").exists()

    stored_pngs: dict[str, bytes] = {}

    class _StubComfyHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _send_json(self, obj: object) -> None:
            raw = json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/system_stats":
                self._send_json(
                    {
                        "system": {"os": "posix", "comfyui_version": "0.3.14"},
                        "devices": [{"name": "cpu", "type": "cpu", "vram_total": 0, "vram_free": 0}],
                    }
                )
                return
            if parsed.path.startswith("/history/"):
                pid = parsed.path.rsplit("/", 1)[-1]
                self._send_json(
                    {
                        pid: {
                            "outputs": {"3": {"images": [{"filename": f"{pid}.png", "subfolder": "", "type": "output"}]}},
                            "status": {"completed": True},
                        }
                    }
                )
                return
            if parsed.path == "/view":
                fname = (urllib.parse.parse_qs(parsed.query).get("filename") or [""])[0]
                png = stored_pngs[fname]
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)
                return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            wf = payload.get("prompt") or {}
            pid = "stub_prompt_001"
            stored_pngs[f"{pid}.png"] = make_minimal_png_with_prompt(wf, seed_byte=9)
            self._send_json({"prompt_id": pid, "number": 1})

    srv = http.server.HTTPServer(("127.0.0.1", 0), _StubComfyHandler)
    srv_port = srv.server_address[1]
    srv_thread = threading.Thread(target=srv.serve_forever, daemon=True)
    srv_thread.start()
    try:
        stub_row = {
            "job_id": "stub_01",
            "run_id": "run_stub_01",
            "template_id": "stub_fixture_64",
            "seed": 101,
            "width": 64,
            "height": 64,
            "canon_sha": "a881cb5ba656e0618080d2269498fda7f36ac93a",
            "entry_id": "ships/brig",
            "entry_sha256": "sha256:" + "1" * 64,
            "workflow_sha": "sha256:" + "2" * 64,
        }
        jobs_file = isolated_dir / "jobs.jsonl"
        jobs_file.write_text(json.dumps(stub_row) + "\n", encoding="utf-8", newline="\n")
        renders_file = isolated_dir / "renders.jsonl"
        png_dir = isolated_dir / "pngs"

        fake_site = REPO_ROOT / "tests" / "colab" / "fixtures" / "fake_vm_site"
        clean_env: dict[str, str] = {"PYTHONPATH": str(fake_site)}
        for keep_key in ("PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE"):
            if keep_key in os.environ:
                clean_env[keep_key] = os.environ[keep_key]

        res = subprocess.run(
            [
                sys.executable,
                str(isolated_script),
                "--cpu",
                "--comfy-url",
                f"http://127.0.0.1:{srv_port}",
                "--jobs",
                str(jobs_file),
                "--renders",
                str(renders_file),
                "--out-dir",
                str(png_dir),
            ],
            cwd=str(isolated_dir),
            env=clean_env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert (png_dir / "stub_01.png").is_file()
        rows = [json.loads(ln) for ln in renders_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(rows) == 1 and rows[0]["job_id"] == "stub_01" and rows[0]["status"] == "ok"
    finally:
        srv.shutdown()
        srv.server_close()

    # Controlled clock check for positive wall_s / wall_ms recording in run_queue
    ticks = iter([99.0, 100.0, 101.25])
    monkeypatch.setattr(
        l1,
        "time",
        types.SimpleNamespace(
            time=lambda: next(ticks, 101.25),
            strftime=std_time.strftime,
            gmtime=std_time.gmtime,
            sleep=std_time.sleep,
            monotonic=std_time.monotonic,
        ),
    )
    fake_client = FakeComfyClient()
    timed_renders = tmp_path / "timed_renders.jsonl"
    timed_out = tmp_path / "timed_pngs"
    l1.run_queue(
        jobs_path=jobs_file,
        renders_path=timed_renders,
        out_dir=timed_out,
        comfy_url="http://127.0.0.1:8188",
        client=fake_client,
        image_downloader=fake_client.download_image,
        system_stats_fetcher=lambda _u: {"devices": [{"type": "cpu", "name": "cpu", "vram_total": 0, "vram_free": 0}]},
    )
    timed_row = json.loads(timed_renders.read_text(encoding="utf-8").strip())
    assert timed_row["wall_s"] == 1.25
    assert timed_row["wall_ms"] == 1250


def test_weights_download_probe_compares_single_file_baseline_in_same_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib
    import os

    fake_site = REPO_ROOT / "tests" / "colab" / "fixtures" / "fake_vm_site"
    monkeypatch.syspath_prepend(str(fake_site))
    monkeypatch.setenv(
        "PYTHONPATH",
        str(fake_site) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
    )
    for k in ("HF_HOME", "HF_TOKEN", "HF_TOKEN_GGUF_READ", "HUGGING_FACE_HUB_TOKEN", "HF_HUB_OFFLINE", "FAKE_HF_EXPECT_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    blobs_dir = tmp_path / "blobs"
    blobs_dir.mkdir()
    vae_blob = _make_safetensors_blob(b"V" * 600)
    (blobs_dir / "vae.safetensors").write_bytes(vae_blob)
    vae_sha = hashlib.sha256(vae_blob).hexdigest()
    monkeypatch.setenv("FAKE_HF_BLOBS_DIR", str(blobs_dir))

    # 1. Earlier larger cached file in the same repo must NOT mask DOWNLOAD_TOO_SLOW on a smaller uncached file
    rev = "7" * 40
    hf_home = tmp_path / "hf_same_repo"
    repo_cache = hf_home / "hub" / "models--Qwen--Qwen-Image"
    (repo_cache / "blobs").mkdir(parents=True)
    (repo_cache / "blobs" / "cached_encoder_blob").write_bytes(b"E" * 20_000)
    assert len(vae_blob) < 20_000

    same_repo_manifest = tmp_path / "same_repo_manifest.json"
    same_repo_manifest.write_text(
        json.dumps(
            [
                {
                    "repo": "Qwen/Qwen-Image",
                    "revision": rev,
                    "file": "vae.safetensors",
                    "dest": "vae",
                    "sha256": vae_sha,
                    "licence_id": "Apache-2.0",
                }
            ]
        ),
        encoding="utf-8",
    )

    now = [0.0]

    class _SlowSecondFileProc:
        def __init__(self, stdout_fh: Any) -> None:
            self._stdout = stdout_fh
            self._polls = 0
            self.killed = False

        def poll(self) -> int | None:
            if self.killed:
                return -9
            self._polls += 1
            if self._polls == 1:
                return None
            inc = repo_cache / "blobs" / "vae.incomplete"
            inc.unlink(missing_ok=True)
            snap_out = repo_cache / "snapshots" / rev / "vae.safetensors"
            snap_out.parent.mkdir(parents=True, exist_ok=True)
            snap_out.write_bytes(vae_blob)
            self._stdout.write(f"FILE_PATH {snap_out}\n")
            self._stdout.flush()
            return 0

        def kill(self) -> None:
            self.killed = True

        def wait(self) -> int:
            return -9 if self.killed else 0

    def _slow_sleep(_dt: float) -> None:
        now[0] += 2.0
        (repo_cache / "blobs" / "vae.incomplete").write_bytes(b"x" * 100)

    out_slow = tmp_path / "dl_same_repo.json"
    rc_slow = l1.run_weights_download(
        manifest_path=same_repo_manifest,
        hf_home=hf_home,
        models_dir=tmp_path / "m_same_repo",
        max_seconds_raw="10",
        probe_seconds=1.0,
        probe_bytes=50,
        poll_s=0.01,
        log_path=tmp_path / "dl_same_repo.log",
        out_path=out_slow,
        expected_fn=lambda *_a, **_kw: len(vae_blob),
        popen=lambda _cmd, stdout, **_kw: _SlowSecondFileProc(stdout),
        clock=lambda: now[0],
        sleep=_slow_sleep,
    )
    assert rc_slow == 1
    assert "REFUSED: DOWNLOAD_TOO_SLOW:" in capsys.readouterr().err
    dl_rec = json.loads(out_slow.read_text(encoding="utf-8"))
    assert dl_rec["refusal"] == "DOWNLOAD_TOO_SLOW"
    assert dl_rec["files"][0]["cached_bytes_at_start"] == 0
    assert dl_rec["files"][0]["downloaded_bytes"] == 100
    assert dl_rec["files"][0]["probe"]["too_slow"] is True

    # 2. Missing filename in repo metadata refuses MODEL_METADATA_FAILED before spawning download
    missing_manifest = tmp_path / "missing_file_manifest.json"
    missing_manifest.write_text(
        json.dumps(
            [
                {
                    "repo": "Qwen/Qwen-Image",
                    "revision": "7" * 40,
                    "file": "absent.safetensors",
                    "dest": "vae",
                    "sha256": vae_sha,
                    "licence_id": "Apache-2.0",
                }
            ]
        ),
        encoding="utf-8",
    )
    popen_called = False

    def _unexpected_popen(*_a: Any, **_kw: Any) -> Any:
        nonlocal popen_called
        popen_called = True
        raise AssertionError("popen must not run when filename is absent from repo metadata")

    rc_missing = l1.run_weights_download(
        manifest_path=missing_manifest,
        hf_home=tmp_path / "hf_missing",
        models_dir=tmp_path / "m_missing",
        max_seconds_raw="30",
        log_path=tmp_path / "dl_missing.log",
        out_path=tmp_path / "dl_missing.json",
        popen=_unexpected_popen,
    )
    assert rc_missing == 1
    assert popen_called is False
    assert "REFUSED: MODEL_METADATA_FAILED:" in capsys.readouterr().err

    # 3. Warm single-file cache in snapshots/<rev>/<file> under HF_HUB_OFFLINE=1 uses single-file size
    warm_hf = tmp_path / "hf_warm"
    warm_snap = warm_hf / "hub" / "models--Qwen--Qwen-Image" / "snapshots" / rev / "vae.safetensors"
    warm_snap.parent.mkdir(parents=True)
    warm_snap.write_bytes(vae_blob)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    class _WarmProc:
        def __init__(self, stdout_fh: Any) -> None:
            stdout_fh.write(f"FILE_PATH {warm_snap}\n")
            stdout_fh.flush()

        def poll(self) -> int:
            return 0

        def kill(self) -> None:
            return

        def wait(self) -> int:
            return 0

    out_warm = tmp_path / "dl_warm.json"
    rc_warm = l1.run_weights_download(
        manifest_path=same_repo_manifest,
        hf_home=warm_hf,
        models_dir=tmp_path / "m_warm",
        max_seconds_raw="10",
        log_path=tmp_path / "dl_warm.log",
        out_path=out_warm,
        popen=lambda _cmd, stdout, **_kw: _WarmProc(stdout),
    )
    assert rc_warm == 0
    warm_rec = json.loads(out_warm.read_text(encoding="utf-8"))
    assert warm_rec["offline"] is True
    assert warm_rec["files"][0]["cached_bytes_at_start"] == len(vae_blob)
    assert warm_rec["files"][0]["expected_bytes"] == len(vae_blob)


def test_example_qwen_2512_manifest_and_strict_apache_mit_allowlist_and_model_exclusions(tmp_path: Path) -> None:
    example_path = REPO_ROOT / "scripts" / "colab" / "lane1" / "weights-manifest-qwen-image-2512.example.json"
    assert example_path.is_file()
    example_rows = json.loads(example_path.read_text(encoding="utf-8"))
    assert isinstance(example_rows, list) and len(example_rows) == 3
    assert [r["file"] for r in example_rows] == [
        "split_files/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors",
        "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "split_files/vae/qwen_image_vae.safetensors",
    ]
    for row in example_rows:
        assert row["repo"] == l1.PINNED_COMFY_REPACK_REPO == "Comfy-Org/Qwen-Image"
        assert row["revision"] == l1.PINNED_COMFY_REPACK_REVISION == "1f12b17be14c89b026c51a91d67c32f84bb047bc"
        assert row["licence_id"] == "Apache-2.0"
        assert row["licence_url"].startswith("https://huggingface.co/Comfy-Org/Qwen-Image/blob/1f12b17be14c89b026c51a91d67c32f84bb047bc/README.md")
        assert row["upstream_licence_url"].startswith("https://")
        if row["dest"] in ("diffusion_models", "vae"):
            assert row["upstream_base_repo"] == l1.PINNED_BASE_MODEL_REPO == "Qwen/Qwen-Image-2512"
            assert row["upstream_base_revision"] == l1.PINNED_BASE_MODEL_REVISION == "25468b98e3276ca6700de15c6628e51b7de54a26"
        assert str(row["sha256"]).startswith("<REPLACE_WITH_64_HEX_SHA256_")

    # Raw example manifest refuses until placeholder shas are replaced with real 64-hex digests
    with pytest.raises(l1.Refusal) as exc_placeholder:
        l1.validate_weights_manifest(example_path)
    assert exc_placeholder.value.code == "WEIGHTS_MANIFEST_INVALID"

    filled_path = tmp_path / "filled_manifest.json"
    filled_rows = [{**r, "sha256": f"{idx + 1}" * 64} for idx, r in enumerate(example_rows)]
    filled_path.write_text(json.dumps(filled_rows, indent=2), encoding="utf-8")
    validated = l1.validate_weights_manifest(filled_path)
    assert len(validated) == 3
    assert {v["spdx_id"] for v in validated} == {"Apache-2.0"}

    # Allow-list contains strictly Apache-2.0 and MIT ids only; every other licence is refused by name
    assert set(l1.CLEARED_LICENCES.values()) == {"Apache-2.0", "MIT"}
    for accepted_lic in ("Apache-2.0", "apache-2.0", "MIT", "mit"):
        p_ok = tmp_path / f"lic_ok_{accepted_lic}.json"
        p_ok.write_text(json.dumps([{**filled_rows[0], "licence_id": accepted_lic}]), encoding="utf-8")
        assert l1.validate_weights_manifest(p_ok)[0]["spdx_id"] in {"Apache-2.0", "MIT"}

    for rejected_lic in ("CC-BY-4.0", "CC-BY-NC-4.0", "BSD-3-Clause", "GPL-3.0", "qwen-research", "other"):
        p_bad = tmp_path / f"lic_bad_{rejected_lic}.json"
        p_bad.write_text(json.dumps([{**filled_rows[0], "licence_id": rejected_lic}]), encoding="utf-8")
        with pytest.raises(l1.Refusal) as exc_lic:
            l1.validate_weights_manifest(p_bad)
        assert exc_lic.value.code == "WEIGHTS_LICENCE_INVALID"
        assert rejected_lic in exc_lic.value.detail

    # Excluded non-commercial Qwen-Image 2.1, Turbo, 2steps, Lightning, and distill/non_official weights refused
    excluded_targets = [
        {"repo": "Qwen/Qwen-Image-2.1", "file": "model.safetensors"},
        {"repo": "Comfy-Org/Qwen-Image", "file": "split_files/diffusion_models/qwen_image_2.1_fp8.safetensors"},
        {"repo": "Qwen/Qwen-Image-Turbo", "file": "turbo.safetensors"},
        {"repo": "Comfy-Org/Qwen-Image", "file": "non_official/diffusion_models/qwen_image_2steps.safetensors"},
        {"repo": "lightx2v/Qwen-Image-Lightning", "file": "lightning.safetensors"},
    ]
    for idx, patch in enumerate(excluded_targets):
        p_ex = tmp_path / f"excluded_{idx}.json"
        p_ex.write_text(json.dumps([{**filled_rows[0], **patch}]), encoding="utf-8")
        with pytest.raises(l1.Refusal) as exc_mod:
            l1.validate_weights_manifest(p_ex)
        assert exc_mod.value.code == "WEIGHTS_MODEL_EXCLUDED"


def test_background_removal_refuses_rmbg_and_non_birefnet_but_allows_birefnet_mit(tmp_path: Path) -> None:
    default_graph = l1.build_qwen_lora_graph({"prompt": "synthetic study", "seed": 1})
    assert default_graph["37"]["inputs"]["unet_name"] == "qwen_image_2512_fp8_e4m3fn.safetensors"
    l1.check_background_removal_allowed(default_graph, {"job_id": "j1"})

    # RMBG-2.0 / BRIA refused in weights manifest, job model_pins, and workflow graph
    rmbg_manifest = tmp_path / "rmbg_manifest.json"
    rmbg_manifest.write_text(
        json.dumps(
            [
                {
                    "repo": "briaai/RMBG-2.0",
                    "revision": "a" * 40,
                    "file": "model.safetensors",
                    "dest": "diffusion_models",
                    "sha256": "b" * 64,
                    "licence_id": "MIT",
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(l1.Refusal) as exc_mf:
        l1.validate_weights_manifest(rmbg_manifest)
    assert exc_mf.value.code == "BG_REMOVAL_FORBIDDEN"

    for bad_node in (
        {"class_type": "BRIA_RMBG_Zho", "inputs": {"model": "RMBG-2.0"}},
        {"class_type": "ImageRemoveBackground+", "inputs": {"method": "rembg"}},
        {"class_type": "InspyrenetRembg", "inputs": {}},
        {"class_type": "BiRefNet_Node", "inputs": {"fallback": "RMBG-2.0"}},
    ):
        wf = {**default_graph, "99": bad_node}
        with pytest.raises(l1.Refusal) as exc_wf:
            l1.check_background_removal_allowed(wf, {"job_id": "j_bad"})
        assert exc_wf.value.code == "BG_REMOVAL_FORBIDDEN"

    with pytest.raises(l1.Refusal) as exc_pin:
        l1.check_background_removal_allowed(default_graph, {"job_id": "j_pin", "bg_removal": "RMBG-2.0"})
    assert exc_pin.value.code == "BG_REMOVAL_FORBIDDEN"

    # Explicit BiRefNet (MIT) node is allowed when RMBG is absent
    birefnet_wf = l1.build_qwen_lora_graph({"job_id": "j_birefnet", "prompt": "synthetic study", "bg_removal": "BiRefNet"})
    assert birefnet_wf["90"]["class_type"] == "BiRefNetRemoveBackground"
    l1.check_background_removal_allowed(birefnet_wf, {"job_id": "j_birefnet", "bg_removal": "BiRefNet"})


def test_local_disk_staging_refuses_mounts_and_drive_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    local_hf = tmp_path / "local_hf"
    local_models = tmp_path / "local_models"
    mounts_ok = tmp_path / "mounts_ok"
    mounts_ok.write_text(f"/dev/sda1 {tmp_path.resolve().as_posix()} ext4 rw,relatime 0 0\n", encoding="utf-8")

    for target_p in (local_hf, local_models):
        ok_rec = l1.verify_local_disk_staging(target_p, mounts_path=mounts_ok)
        assert ok_rec["fstype"] == "ext4"
        assert ok_rec["local_disk"] is True

    # Google Drive mount path (/content/drive/...) is refused immediately
    with pytest.raises(l1.Refusal) as exc_drive:
        l1.verify_local_disk_staging(Path("/content/drive/MyDrive/weights"), mounts_path=mounts_ok)
    assert exc_drive.value.code == "WEIGHTS_MOUNT_FORBIDDEN"

    # FUSE / NFS / CIFS mounts are refused when staging weights
    for bad_fs in ("fuse.drive", "gcsfuse", "nfs4", "cifs", "9p"):
        mounts_bad = tmp_path / f"mounts_{bad_fs}"
        mounts_bad.write_text(
            f"remote:{bad_fs} {local_models.resolve().as_posix()} {bad_fs} rw 0 0\n",
            encoding="utf-8",
        )
        with pytest.raises(l1.Refusal) as exc_fs:
            l1.verify_local_disk_staging(local_models, mounts_path=mounts_bad)
        assert exc_fs.value.code == "WEIGHTS_MOUNT_FORBIDDEN"

    # run_vm_guards records and refuses WEIGHTS_MOUNT_FORBIDDEN when models_dir sits on FUSE
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       33554432 kB\nMemAvailable:   25165824 kB\n", encoding="utf-8")
    shm = tmp_path / "shm"
    shm.mkdir()
    mounts_fuse = tmp_path / "mounts_fuse"
    mounts_fuse.write_text(f"drive {local_models.resolve().as_posix()} fuse.drive rw 0 0\n", encoding="utf-8")
    guards_out = tmp_path / "guards_mount_bad.json"
    rc_guards = l1.run_vm_guards(
        hf_home=local_hf,
        models_dir=local_models,
        lane1_out=tmp_path / "out",
        disk_required_gib=0.001,
        smoke_seconds=0.01,
        ram_required_gib="1",
        meminfo_path=meminfo,
        shm_path=shm,
        out_path=guards_out,
        cpu_stub=True,
        mounts_path=mounts_fuse,
    )
    assert rc_guards == 1
    assert "REFUSED: WEIGHTS_MOUNT_FORBIDDEN:" in capsys.readouterr().err


def test_colab_runtime_cuda_probe_hf_429_retry_and_render_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib
    import os

    # 1. Colab runtime version + /usr/local/cuda* probe
    release_file = tmp_path / "colab-release"
    release_file.write_text('COLAB_RELEASE_TAG="release-colab-20261112_RC01"\n', encoding="utf-8")
    usr_local = tmp_path / "usr_local"
    cuda_126 = usr_local / "cuda-12.6"
    cuda_130 = usr_local / "cuda-13.0"
    cuda_126.mkdir(parents=True)
    cuda_130.mkdir(parents=True)
    (cuda_126 / "version.json").write_text('{"cuda":{"version":"12.6.3"}}', encoding="utf-8")
    (cuda_130 / "version.txt").write_text("CUDA Version 13.0.1\n", encoding="utf-8")
    rt_info = l1.probe_colab_runtime_and_cuda(release_path=release_file, cuda_parent=usr_local)
    assert rt_info["colab_runtime_version"] == "release-colab-20261112_RC01"
    assert [c["name"] for c in rt_info["cuda_paths"]] == ["cuda-12.6", "cuda-13.0"]
    assert [c["path"] for c in rt_info["cuda_paths"]] == [cuda_126.as_posix(), cuda_130.as_posix()]
    assert rt_info["cuda_paths"][0]["cuda_version"] == "12.6.3"
    assert rt_info["cuda_paths"][1]["cuda_version"] == "CUDA Version 13.0.1"

    # 2. HF 429 retry with bounded backoff in run_weights_download + HF_HUB_OFFLINE=1 once staged
    fake_site = REPO_ROOT / "tests" / "colab" / "fixtures" / "fake_vm_site"
    monkeypatch.syspath_prepend(str(fake_site))
    for k in ("HF_HOME", "HF_TOKEN", "HF_TOKEN_GGUF_READ", "HUGGING_FACE_HUB_TOKEN", "HF_HUB_OFFLINE", "FAKE_HF_EXPECT_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    blob = _make_safetensors_blob(b"Z" * 256)
    blob_sha = hashlib.sha256(blob).hexdigest()
    blobs_dir = tmp_path / "blobs"
    blobs_dir.mkdir()
    (blobs_dir / "vae.safetensors").write_bytes(blob)
    monkeypatch.setenv("FAKE_HF_BLOBS_DIR", str(blobs_dir))
    monkeypatch.setenv("FAKE_HF_INFO_429_COUNT", "1")

    manifest_p = tmp_path / "m429.json"
    manifest_p.write_text(
        json.dumps(
            [
                {
                    "repo": "Comfy-Org/Qwen-Image",
                    "revision": "1f12b17be14c89b026c51a91d67c32f84bb047bc",
                    "file": "vae.safetensors",
                    "dest": "vae",
                    "sha256": blob_sha,
                    "licence_id": "Apache-2.0",
                }
            ]
        ),
        encoding="utf-8",
    )

    dl_calls = 0
    staged_src = tmp_path / "downloaded_vae.safetensors"
    staged_src.write_bytes(blob)

    class _Retry429Proc:
        def __init__(self, stdout_fh: Any, fail_429: bool) -> None:
            self._rc = 1 if fail_429 else 0
            if fail_429:
                stdout_fh.write("HfHubHTTPError: 429 Client Error: Too Many Requests\n")
            else:
                stdout_fh.write(f"FILE_PATH {staged_src}\n")
            stdout_fh.flush()

        def poll(self) -> int:
            return self._rc

        def kill(self) -> None:
            return

        def wait(self) -> int:
            return self._rc

    def _popen_retry(_cmd: list[str], stdout: Any, **_kw: Any) -> _Retry429Proc:
        nonlocal dl_calls
        dl_calls += 1
        return _Retry429Proc(stdout, fail_429=(dl_calls <= 2))

    sleeps: list[float] = []
    out_ok = tmp_path / "dl_429_ok.json"
    rc_ok = l1.run_weights_download(
        manifest_path=manifest_p,
        hf_home=tmp_path / "hf_429_ok",
        models_dir=tmp_path / "models_429_ok",
        max_seconds_raw="30",
        backoff_base_s=0.5,
        log_path=tmp_path / "dl_429_ok.log",
        out_path=out_ok,
        popen=_popen_retry,
        sleep=lambda s: sleeps.append(s),
    )
    assert rc_ok == 0
    assert dl_calls == 3
    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    rec_ok = json.loads(out_ok.read_text(encoding="utf-8"))
    assert rec_ok["http_429_retries"] == 3  # 1 metadata 429 + 2 file-download 429s
    assert rec_ok["hf_hub_offline_after_stage"] is True
    assert sleeps == [0.5, 0.5, 1.0]

    # Exhausting max_seconds during persistent 429s refuses DOWNLOAD_TOO_SLOW inside the bound
    os.environ.pop("HF_HUB_OFFLINE", None)
    monkeypatch.setenv("FAKE_HF_INFO_429_COUNT", "0")
    out_exhaust = tmp_path / "dl_429_exhaust.json"
    clock_vals = iter([0.0, 0.1, 0.2, 0.9, 1.5])
    rc_exhaust = l1.run_weights_download(
        manifest_path=manifest_p,
        hf_home=tmp_path / "hf_429_ex",
        models_dir=tmp_path / "models_429_ex",
        max_seconds_raw="1",
        backoff_base_s=2.0,
        log_path=tmp_path / "dl_429_ex.log",
        out_path=out_exhaust,
        popen=lambda _cmd, stdout, **_kw: _Retry429Proc(stdout, fail_429=True),
        clock=lambda: next(clock_vals, 2.0),
        sleep=lambda _s: None,
    )
    assert rc_exhaust == 1
    assert "REFUSED: DOWNLOAD_TOO_SLOW:" in capsys.readouterr().err

    # 3. Heartbeat advances strictly on rendered images (not skipped jobs) and detects stale runs
    hb_path = tmp_path / "hb" / "render_heartbeat.json"
    hb0 = l1.write_render_heartbeat(
        hb_path,
        window_id="win_hb",
        state="running",
        total_jobs=3,
        skipped_jobs=0,
        images_rendered=0,
        heartbeat_seq=0,
        started_at_epoch=100.0,
        last_image_at_epoch=None,
        last_job_id=None,
    )
    assert l1.evaluate_render_heartbeat(hb0, max_idle_s=30.0, now_epoch=125.0)["ok"] is True
    stale0 = l1.evaluate_render_heartbeat(hb0, max_idle_s=30.0, now_epoch=135.0)
    assert stale0["ok"] is False and stale0["tripped"] is True and stale0["code"] == "RENDER_HEARTBEAT_STALE"

    hb1 = l1.write_render_heartbeat(
        hb_path,
        window_id="win_hb",
        state="running",
        total_jobs=3,
        skipped_jobs=1,
        images_rendered=1,
        heartbeat_seq=1,
        started_at_epoch=100.0,
        last_image_at_epoch=130.0,
        last_job_id="job_01",
    )
    assert l1.evaluate_render_heartbeat(hb1, max_idle_s=30.0, now_epoch=155.0)["ok"] is True
    assert l1.evaluate_render_heartbeat(hb1, max_idle_s=30.0, now_epoch=165.0)["ok"] is False
    done_hb = {**hb1, "state": "completed"}
    assert l1.evaluate_render_heartbeat(done_hb, max_idle_s=1.0, now_epoch=9999.0)["ok"] is True

    # 4. PNG provenance stamp requires both licence=CC-BY-4.0 and credit=mcp-tool-shop on write and read-back
    raw_png = make_minimal_png_with_prompt({"1": {"class_type": "EmptyImage"}}, seed_byte=7)
    base_stamp = {
        "owner": "mcp-tool-shop",
        "licence": "CC-BY-4.0",
        "credit": "mcp-tool-shop",
        "canon_sha": "a" * 40,
        "entry_id": "tools/compass_01",
        "entry_sha256": "sha256:" + "b" * 64,
        "run_id": "run_01",
        "workflow_sha": "sha256:" + "c" * 64,
        "window_id": "win_01",
    }
    stamped = l1.stamp_png_provenance(raw_png, base_stamp)
    verified_stamp = l1.verify_png_provenance(stamped, base_stamp)
    assert verified_stamp["licence"] == "CC-BY-4.0"
    assert verified_stamp["credit"] == "mcp-tool-shop"
    with pytest.raises(ValueError, match="PNG_STAMP_MISSING"):
        l1.stamp_png_provenance(raw_png, {k: v for k, v in base_stamp.items() if k != "credit"})
    stripped_credit_png = l1.write_png_text_chunks(stamped, {"sdlab:credit": None})
    with pytest.raises(ValueError, match="PNG_STAMP_MISSING"):
        l1.verify_png_provenance(stripped_credit_png, base_stamp)
