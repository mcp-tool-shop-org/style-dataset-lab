#!/usr/bin/env python3
"""Alpha-cut sprites via ComfyUI's native BiRefNet background removal, for the A1 seam-test.

Replicates the shipped "Remove Background (BiRefNet)" subgraph:
  LoadImage -> LoadBackgroundRemovalModel -> RemoveBackground -> InvertMask -> JoinImageWithAlpha -> SaveImage
Outputs RGBA PNGs (figure on transparency) and copies them to the Godot seam-test sprites dir.

Inputs must already be in ComfyUI/input. Run with ComfyUI's embedded python:
    python _seam_cutout.py seam_front seam_pitch30 seam_pitch40
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.request
import uuid
from pathlib import Path

COMFY = "http://127.0.0.1:8188"
COMFY_OUT = Path(r"E:/AI-Models/ComfyUI_windows_portable/ComfyUI/output")
GODOT_SPRITES = Path(r"E:/AI/hesperia/game/seam_test/sprites")
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


def run_one(name: str) -> Path:
    g = graph(f"{name}.png", f"seamcut_{name}")
    pid = post("/prompt", {"prompt": g, "client_id": uuid.uuid4().hex})["prompt_id"]
    for _ in range(600):
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=30).read())
        if pid in hist and hist[pid].get("outputs"):
            img = hist[pid]["outputs"]["6"]["images"][0]
            src = COMFY_OUT / img["subfolder"] / img["filename"]
            for _w in range(120):
                if src.exists():
                    GODOT_SPRITES.mkdir(parents=True, exist_ok=True)
                    dst = GODOT_SPRITES / f"{name}.png"
                    shutil.copyfile(src, dst)
                    return dst
                time.sleep(0.5)
        time.sleep(0.5)
    raise RuntimeError(f"cutout timed out for {name}")


def main() -> None:
    names = sys.argv[1:]
    if not names:
        print("usage: _seam_cutout.py <name> [<name> ...]  (names are ComfyUI/input stems, no .png)")
        sys.exit(2)
    for n in names:
        dst = run_one(n)
        print(f"  cut {n} -> {dst}", flush=True)
    print(f"\nSEAMCUT DONE: {len(names)} sprite(s) -> {GODOT_SPRITES}")


if __name__ == "__main__":
    main()
