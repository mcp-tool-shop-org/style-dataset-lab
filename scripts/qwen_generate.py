#!/usr/bin/env python3
"""Studio NON-ANIME generation on Qwen-Image (the verified base) via ComfyUI.

Reads a canon-derived WAVE json ({style_prefix, defaults, subjects:[{id,prompt,variations}]}) and
generates each subject on Qwen-Image, saving images + a provenance receipt (PIN_PER_STEP) to an
output dir. This is the bridge generator until sdlab's buildWorkflowGraph() gains native Qwen
support (tracked follow-on). It is the studio's NON-ANIME path — see memory/feedback_no_anime.md.

All Qwen-Image components are on the rig (diffusion_models/text_encoders/vae). Run with ComfyUI's
embedded python (has PIL): start the watchdog (E:/AI/training/_watchdog.ps1) before GPU runs.

    python qwen_generate.py --wave <wave.json> --out <dir> [--variations N]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

COMFY = "http://127.0.0.1:8188"
COMFY_OUT = Path(r"E:/AI-Models/ComfyUI_windows_portable/ComfyUI/output")

# Qwen-Image native components (on rig). NON-ANIME base — never an anime checkpoint.
QWEN_UNET = "qwen_image_fp8_e4m3fn.safetensors"
QWEN_CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
QWEN_VAE = "qwen_image_vae.safetensors"


def qwen_graph(pos: str, neg: str, seed: int, w: int, h: int, steps: int, cfg: float, prefix: str,
               loras: list | None = None) -> dict:
    """loras: [{name, weight}] chained as DiT-only LoraLoaderModelOnly nodes (ids from
    "40", between UNETLoader and ModelSamplingAuraFlow) — mirrors sdlab buildQwenGraph.
    Model-only because studio Qwen style LoRAs train the transformer with the text
    encoder frozen."""
    nodes = {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": QWEN_UNET, "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": QWEN_CLIP, "type": "qwen_image"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": QWEN_VAE}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": ["38", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["38", 0]}},
    }
    model_out = ["37", 0]
    for i, lora in enumerate(loras or []):
        lid = str(40 + i)
        nodes[lid] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "lora_name": lora["name"], "strength_model": lora.get("weight", 1.0), "model": model_out}}
        model_out = [lid, 0]
    nodes.update({
        "66": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.1, "model": model_out}},
        "5": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler",
              "scheduler": "simple", "denoise": 1.0, "model": ["66", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["8", 0]}},
    })
    return nodes


def _post(path: str, payload: dict):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{COMFY}{path}", json.dumps(payload).encode(), {"Content-Type": "application/json"}), timeout=90).read())


def generate(pos: str, neg: str, seed: int, dst: Path, **kw) -> Path:
    g = qwen_graph(pos, neg, seed, kw["w"], kw["h"], kw["steps"], kw["cfg"], dst.stem, loras=kw.get("loras"))
    pid = _post("/prompt", {"prompt": g, "client_id": uuid.uuid4().hex})["prompt_id"]
    for _ in range(1200):
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=30).read())
        if pid in hist and hist[pid].get("outputs"):
            img = hist[pid]["outputs"]["9"]["images"][0]
            src = COMFY_OUT / img["subfolder"] / img["filename"]
            for _w in range(120):
                if src.exists():
                    Image.open(src).convert("RGB").save(dst)
                    return dst
                time.sleep(0.5)
        time.sleep(0.5)
    raise RuntimeError("ComfyUI generation timed out")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--variations", type=int, default=None, help="override per-subject variation count")
    args = ap.parse_args()

    wave = json.loads(args.wave.read_text(encoding="utf-8"))
    prefix = wave.get("style_prefix", "")
    d = wave.get("defaults", {})
    neg = d.get("negative", "")
    w, h = d.get("width", 1024), d.get("height", 1024)
    steps, cfg = d.get("steps", 22), d.get("cfg", 3.5)
    base_seed = d.get("base_seed", 1000)
    loras = d.get("loras", [])
    args.out.mkdir(parents=True, exist_ok=True)

    receipt = {"wave": wave.get("wave"), "base": "qwen-image", "unet": QWEN_UNET, "clip": QWEN_CLIP,
               "vae": QWEN_VAE, "sampler": "euler", "scheduler": "simple", "shift": 3.1,
               "steps": steps, "cfg": cfg, "size": [w, h], "style_prefix": prefix, "negative": neg,
               "loras": loras, "items": []}
    seed = base_seed
    for subj in wave["subjects"]:
        nvar = args.variations if args.variations is not None else subj.get("variations", 1)
        pos = f"{prefix}, {subj['prompt']}" if prefix else subj["prompt"]
        for v in range(nvar):
            dst = args.out / f"{subj['id']}_v{v}.png"
            generate(pos, neg, seed, dst, w=w, h=h, steps=steps, cfg=cfg, loras=loras)
            print(f"  {subj['id']} v{v} (seed {seed}) -> {dst.name}", flush=True)
            receipt["items"].append({"id": subj["id"], "variation": v, "seed": seed, "file": dst.name, "prompt": pos})
            seed += 1

    (args.out / "generation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"\n{len(receipt['items'])} images -> {args.out}  (+ generation.json provenance)")


if __name__ == "__main__":
    main()
