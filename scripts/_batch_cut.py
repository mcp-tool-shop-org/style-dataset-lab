#!/usr/bin/env python3
"""Batch alpha-cut cast turnaround views via ComfyUI's native BiRefNet (RGBA out).
For each character, cuts its 8 restylized views -> out/<char>/<view>.png on transparency.
Free Qwen (POST /free) before running so BiRefNet doesn't co-reside with the 28 GB transformer.

    python _batch_cut.py --restylized <dir-of-per-char> --out <dir> --chars rustgrave,hearthframe,dustwhisper
"""
from __future__ import annotations
import argparse, json, shutil, time, urllib.request, uuid
from pathlib import Path

COMFY = "http://127.0.0.1:8188"
COMFY_OUT = Path(r"E:/AI-Models/ComfyUI_windows_portable/ComfyUI/output")
COMFY_IN = Path(r"E:/AI-Models/ComfyUI_windows_portable/ComfyUI/input")
MODEL = "birefnet.safetensors"


def graph(image_filename: str, out_prefix: str) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "2": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": MODEL}},
        "3": {"class_type": "RemoveBackground", "inputs": {"image": ["1", 0], "bg_removal_model": ["2", 0]}},
        "4": {"class_type": "InvertMask", "inputs": {"mask": ["3", 0]}},
        "5": {"class_type": "JoinImageWithAlpha", "inputs": {"image": ["1", 0], "alpha": ["4", 0]}},
        "6": {"class_type": "SaveImage", "inputs": {"filename_prefix": out_prefix, "images": ["5", 0]}},
    }


def post(path: str, payload: dict):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{COMFY}{path}", json.dumps(payload).encode(), {"Content-Type": "application/json"}), timeout=120).read())


def cut_one(src: Path, staged_name: str, dst: Path):
    shutil.copyfile(src, COMFY_IN / f"{staged_name}.png")
    g = graph(f"{staged_name}.png", f"cut_{staged_name}")
    pid = post("/prompt", {"prompt": g, "client_id": uuid.uuid4().hex})["prompt_id"]
    for _ in range(600):
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=30).read())
        if pid in hist and hist[pid].get("outputs"):
            img = hist[pid]["outputs"]["6"]["images"][0]
            srcp = COMFY_OUT / img["subfolder"] / img["filename"]
            for _w in range(120):
                if srcp.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(srcp, dst)
                    return
                time.sleep(0.5)
        time.sleep(0.5)
    raise RuntimeError(f"cut timed out: {src}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restylized", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chars", required=True)
    args = ap.parse_args()
    rdir = Path(args.restylized); odir = Path(args.out)
    n = 0
    for c in args.chars.split(","):
        c = c.strip()
        for v in sorted((rdir / c).glob("*.png")):
            cut_one(v, f"{c}_{v.stem}", odir / c / f"{v.stem}.png")
            n += 1
            print(f"  cut {c}/{v.stem}", flush=True)
    print(f"BATCH CUT DONE: {n} sprites -> {odir}", flush=True)


if __name__ == "__main__":
    main()
