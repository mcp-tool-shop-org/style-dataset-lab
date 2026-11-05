"""Unit tests for scripts/colab/lane1_render.py (Part B.2)."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "colab"))

import lane1_render as l1  # noqa: E402


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
    assert read_back["entry_id"] == "ships/brig"
    assert read_back["window_id"] == "win_lane1_stub_01"

    with pytest.raises(ValueError, match="PNG_STAMP_MISMATCH"):
        l1.verify_png_provenance(png_path, {**stamp, "owner": "wrong-owner"})

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



