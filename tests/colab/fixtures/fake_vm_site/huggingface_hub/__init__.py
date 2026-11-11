"""Stand-in for huggingface_hub on the fake GPU VM: the model listing and a snapshot download
that writes sparse blobs into HF_HOME at a simulated network rate.

FAKE_HF_TOTAL_BYTES   apparent size of the repo (default 3 GiB), split over FAKE_HF_FILES files (4)
FAKE_HF_RATE_BPS      simulated download rate in bytes/s (default: effectively instant)
FAKE_HF_429=1         print a throttling line the way the hub client logs a retried 429
FAKE_HF_FAIL=1        fail the download with an HTTP error
FAKE_HF_INFO_ERROR    401 | 404rev | net: the metadata call fails the way the hub client does
FAKE_HF_STALL=1       the download stalls after its first file but keeps printing progress
FAKE_HF_EXPECT_TOKEN  the read token the kit was given: the download must use exactly it (and logs
                      it, so the tests prove the kit's scrubbers remove it); unset, no token at all
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import time
from pathlib import Path


def _files() -> list[tuple[str, int]]:
    total = int(os.environ.get("FAKE_HF_TOTAL_BYTES", str(3 * 1024**3)))
    n = int(os.environ.get("FAKE_HF_FILES", "4"))
    return [(f"transformer/diffusion_pytorch_model-{i + 1:05d}-of-{n:05d}.safetensors", total // n) for i in range(n)]


def _blob_payload(filename: str) -> bytes:
    blobs_dir = os.environ.get("FAKE_HF_BLOBS_DIR")
    if blobs_dir:
        root = Path(blobs_dir)
        for cand in (root / filename, root / Path(filename).name):
            if cand.is_file():
                data = cand.read_bytes()
                break
        else:
            data = b""
    else:
        data = b""
    if not data:
        target_bytes = max(int(os.environ.get("FAKE_HF_FILE_BYTES", "4096")), 128)
        hdr = json.dumps({"w": {"dtype": "U8", "shape": [64], "data_offsets": [0, 64]}}).encode("utf-8")
        prefix = struct.pack("<Q", len(hdr)) + hdr
        payload_len = max(64, target_bytes - len(prefix))
        hdr = json.dumps({"w": {"dtype": "U8", "shape": [payload_len], "data_offsets": [0, payload_len]}}).encode("utf-8")
        data = struct.pack("<Q", len(hdr)) + hdr + (b"S" * payload_len)
    if os.environ.get("FAKE_HF_TRUNCATE_SAFETENSORS") == "1" and len(data) > 16:
        data = data[:-8]
    if os.environ.get("FAKE_HF_CORRUPT_SHA") == "1":
        data = data[:-1] + bytes([data[-1] ^ 0xFF])
    return data


def _check_token(token: object) -> None:
    want = os.environ.get("FAKE_HF_EXPECT_TOKEN")
    if want:
        if token != want:
            raise AssertionError("the rung did not hand the request's read token to the download")
    elif token is not False or os.environ.get("HF_TOKEN"):
        raise AssertionError("the rung must download unauthenticated")


class _Sibling:
    def __init__(self, rfilename: str, size: int) -> None:
        self.rfilename = rfilename
        self.size = size


class _Info:
    def __init__(self, siblings: list[_Sibling]) -> None:
        self.siblings = siblings


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class HfHubHTTPError(Exception):
    def __init__(self, msg: str, status: int) -> None:
        super().__init__(msg)
        self.response = _Response(status)


class RevisionNotFoundError(HfHubHTTPError):
    pass


class HfApi:
    def model_info(self, repo_id: str, revision: str | None = None, files_metadata: bool = False,
                   token: object = None) -> _Info:
        err = os.environ.get("FAKE_HF_INFO_ERROR")
        if err == "401":
            raise HfHubHTTPError("401 Client Error: Unauthorized (Invalid credentials in Authorization header)", 401)
        if err == "404rev":
            raise RevisionNotFoundError(f"404 Client Error: Revision Not Found for url: .../revision/{revision}", 404)
        if err == "net":
            raise ConnectionError("Max retries exceeded (Connection refused)")
        _check_token(token)
        siblings = [_Sibling(name, size) for name, size in _files()]
        stream_override = os.environ.get("FAKE_HF_STREAM_BYTES")
        blobs_dir = os.environ.get("FAKE_HF_BLOBS_DIR")
        if blobs_dir and Path(blobs_dir).is_dir():
            for p in sorted(Path(blobs_dir).rglob("*")):
                if p.is_file():
                    rel = p.relative_to(Path(blobs_dir)).as_posix()
                    sz = int(stream_override) if stream_override else p.stat().st_size
                    siblings.append(_Sibling(rel, sz))
        return _Info(siblings)


def hf_hub_download(
    repo_id: str,
    filename: str,
    revision: str | None = None,
    token: object = None,
) -> str:
    _check_token(token)
    if token:
        print(f"Authenticated file download with token {token}", flush=True)
    if os.environ.get("FAKE_HF_FAIL") == "1":
        raise OSError("401 Client Error: Repository Not Found")
    if os.environ.get("FAKE_HF_429") == "1":
        print("HTTP Error 429 thrown while requesting GET https://huggingface.co/... Retrying in 1s [Retry 1/5].", flush=True)
    stream_override = os.environ.get("FAKE_HF_STREAM_BYTES")
    payload = b"" if stream_override else _blob_payload(filename)
    size = int(stream_override) if stream_override else len(payload)
    rate = float(os.environ.get("FAKE_HF_RATE_BPS", "1e15"))
    repo = Path(os.environ["HF_HOME"]) / "hub" / ("models--" + repo_id.replace("/", "--"))
    blobs = repo / "blobs"
    snap = repo / "snapshots" / str(revision)
    blobs.mkdir(parents=True, exist_ok=True)
    safe_name = filename.replace("/", "__")
    blob = blobs / f"file_{safe_name}"
    inc = blobs / f"file_{safe_name}.incomplete"
    written = 0
    with inc.open("wb") as fh:
        while written < size:
            step = max(int(rate * 0.05), 1)
            nxt = min(size, written + step)
            if stream_override:
                fh.truncate(nxt)
            else:
                fh.write(payload[written:nxt])
                fh.flush()
            written = nxt
            if rate < 1e12:
                time.sleep(0.05)
    if os.environ.get("FAKE_HF_STALL") == "1":
        while True:
            print("Downloading file:  50%|#####     | [00:01<00:01]", flush=True)
            time.sleep(0.2)
    inc.replace(blob)
    dest = snap / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    try:
        os.symlink(os.path.relpath(blob, dest.parent), dest)
    except OSError:
        shutil.move(str(blob), str(dest))
    return str(dest)


def snapshot_download(repo_id: str, revision: str | None = None, token: object = None) -> str:
    _check_token(token)
    if token:
        print(f"Authenticated download with token {token}", flush=True)
    if os.environ.get("FAKE_HF_FAIL") == "1":
        raise OSError("401 Client Error: Repository Not Found")
    if os.environ.get("FAKE_HF_429") == "1":
        print("HTTP Error 429 thrown while requesting GET https://huggingface.co/... Retrying in 1s [Retry 1/5].", flush=True)
    rate = float(os.environ.get("FAKE_HF_RATE_BPS", "1e15"))
    repo = Path(os.environ["HF_HOME"]) / "hub" / ("models--" + repo_id.replace("/", "--"))
    blobs = repo / "blobs"
    snap = repo / "snapshots" / str(revision)
    blobs.mkdir(parents=True, exist_ok=True)
    for idx, (name, size) in enumerate(_files()):
        blob = blobs / f"blob{idx}"
        inc = blobs / f"blob{idx}.incomplete"
        written = 0
        with inc.open("wb") as fh:
            while written < size:
                written = min(size, written + max(int(rate * 0.05), 1))
                fh.truncate(written)
                if rate < 1e12:
                    time.sleep(0.05)
        if os.environ.get("FAKE_HF_STALL") == "1" and idx == 1:
            while True:
                print("Fetching 4 files:  25%|##5       | 1/4 [00:01<00:03]", flush=True)
                time.sleep(0.2)
        inc.rename(blob)
        dest = snap / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            os.symlink(os.path.relpath(blob, dest.parent), dest)
    return str(snap)
