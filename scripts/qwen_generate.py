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
import hashlib
import json
import math
import os
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

# ─── PIN_PER_STEP pinning contract ────────────────────────────────────────────
# Mirror of lib/run-manifest.js (the JS helper is the field-name authority). This
# receipt carries the IDENTICAL `pinning` block so a wave produced by this bridge
# generator is pinned the same way as one produced through the JS `sdlab generate`
# / `sdlab run generate` paths. Keep PINNING_VERSION + the field names in lockstep
# with lib/run-manifest.js.
PINNING_VERSION = "1.0.0"
MODELS_DIR = os.environ.get(
    "SDLAB_MODELS_DIR", r"E:/AI-Models/ComfyUI_windows_portable/ComfyUI/models"
)
HASH_CACHE_FILE = os.environ.get("SDLAB_HASH_CACHE") or str(
    Path(MODELS_DIR) / ".sdlab-hash-cache.json"
)
# kind → candidate subdirs under the models dir, in search order (mirror of JS).
_KIND_SUBDIRS = {
    "unet": ["diffusion_models", "unet"],
    "clip": ["text_encoders", "clip"],
    "vae": ["vae"],
    "checkpoint": ["checkpoints"],
    "lora": ["loras"],
}


def _js_number(n) -> str:
    """Format a number the way JS String(n) does, so the graph hash matches the JS
    helper: integer-valued floats drop the decimal (1.0 -> "1"), others use the
    shortest round-trip repr (3.1 -> "3.1")."""
    if isinstance(n, bool):
        return "true" if n else "false"
    if isinstance(n, int):
        return str(n)
    if isinstance(n, float):
        if not math.isfinite(n):
            return "null"
        return str(int(n)) if n.is_integer() else repr(n)
    return "null"


def _stable_stringify(value) -> str:
    """Deterministic serialization mirroring lib/run-manifest.js stableStringify:
    object keys sorted, arrays in order, JS-style number/string formatting."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _js_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable_stringify(v) for v in value) + "]"
    if isinstance(value, dict):
        # JS omits `undefined` keys; Python has no undefined, and None maps to JS
        # `null` which stableStringify DOES serialize — so serialize every key.
        parts = [
            json.dumps(k, ensure_ascii=False) + ":" + _stable_stringify(value[k])
            for k in sorted(value.keys())
        ]
        return "{" + ",".join(parts) + "}"
    return "null"


def _normalize_graph_for_hash(graph: dict) -> dict:
    """Blank per-item nondeterminism (seed, prompt text, filename_prefix) so the
    whole wave shares one comfy_workflow_sha. Mirror of the JS normalizer."""
    out = {}
    for nid, node in (graph or {}).items():
        inputs = dict(node.get("inputs", {}))
        cls = node.get("class_type")
        if cls in ("KSampler", "KSamplerAdvanced"):
            if "seed" in inputs:
                inputs["seed"] = 0
            if "noise_seed" in inputs:
                inputs["noise_seed"] = 0
        elif cls == "CLIPTextEncode":
            if "text" in inputs:
                inputs["text"] = ""
        elif cls == "SaveImage":
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = ""
        out[nid] = {"class_type": cls, "inputs": inputs}
    return out


def _comfy_workflow_sha(graph: dict):
    if not graph:
        return None
    payload = _stable_stringify(_normalize_graph_for_hash(graph))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_model_path(name: str, kind: str):
    if not name:
        return None
    subdirs = list(_KIND_SUBDIRS.get(kind, []))
    for group in _KIND_SUBDIRS.values():
        subdirs.extend(group)
    subdirs.append(".")
    seen = set()
    for sub in subdirs:
        cand = os.path.join(MODELS_DIR, sub, name)
        if cand in seen:
            continue
        seen.add(cand)
        if os.path.exists(cand):
            return cand
    return None


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _load_hash_cache() -> dict:
    try:
        with open(HASH_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_hash_cache(cache: dict) -> None:
    try:
        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def _hash_model_file(name: str, kind: str, do_hash: bool, cache: dict) -> dict:
    """Best-effort {name, size_bytes, sha256} for a model/LoRA file (mirror of the
    JS hashModelFile). size_bytes is always filled when resolvable; sha256 is
    gated behind do_hash and cached by (name, size, mtime)."""
    if not name:
        return {"name": name, "size_bytes": None, "sha256": None, "hash_note": "no filename"}
    resolved = _resolve_model_path(name, kind)
    if not resolved:
        return {"name": name, "size_bytes": None, "sha256": None, "hash_note": f"unresolved under {MODELS_DIR}"}
    try:
        st = os.stat(resolved)
        size_bytes = st.st_size
        mtime_ms = round(st.st_mtime * 1000)
    except OSError:
        return {"name": name, "size_bytes": None, "sha256": None, "hash_note": "stat failed"}
    if not do_hash:
        return {"name": name, "size_bytes": size_bytes, "sha256": None, "hash_note": "hash skipped (pass --hash-models)"}
    key = f"{name}:{size_bytes}:{mtime_ms}"
    if key in cache:
        return {"name": name, "size_bytes": size_bytes, "sha256": cache[key]}
    try:
        sha = _sha256_file(resolved)
    except OSError:
        return {"name": name, "size_bytes": size_bytes, "sha256": None, "hash_note": "hash failed (read error)"}
    cache[key] = sha
    return {"name": name, "size_bytes": size_bytes, "sha256": sha}


def _build_pinning(graph, models, loras, seed_policy, do_hash, cache) -> dict:
    """Assemble the pinning block — identical shape to lib/run-manifest.js buildPinning."""
    model_hashes = {}
    for role, kind in (("unet", "unet"), ("clip", "clip"), ("vae", "vae"), ("checkpoint", "checkpoint")):
        if models.get(role):
            model_hashes[role] = _hash_model_file(models[role], kind, do_hash, cache)
    lora_hashes = []
    for lora in loras or []:
        entry = _hash_model_file(lora.get("name"), "lora", do_hash, cache)
        entry["weight"] = lora.get("weight", 1.0)
        lora_hashes.append(entry)
    return {
        "pinning_version": PINNING_VERSION,
        "comfy_workflow_sha": _comfy_workflow_sha(graph),
        "seed_policy": seed_policy,
        "models": model_hashes,
        "loras": lora_hashes,
    }


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
    ap.add_argument("--hash-models", action="store_true",
                    help="content-hash the unet/clip/vae/LoRA files into the pinning block (best-effort, cached)")
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

    # PIN_PER_STEP: pin the exact graph + model/LoRA content identity + seed policy.
    # The wave shares ONE comfy_workflow_sha (per-item seed + prompt are normalized
    # out and recorded per item in items[]). seed_policy is "explicit-per-item"
    # because each item's seed is written verbatim below. Mirror of the JS contract.
    hash_cache = _load_hash_cache()
    pin_graph = qwen_graph(prefix or "x", neg, base_seed, w, h, steps, cfg, "sdl", loras=loras)
    receipt["pinning"] = _build_pinning(
        pin_graph,
        {"unet": QWEN_UNET, "clip": QWEN_CLIP, "vae": QWEN_VAE},
        loras,
        "explicit-per-item",
        args.hash_models,
        hash_cache,
    )

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

    if args.hash_models:
        _save_hash_cache(hash_cache)
    (args.out / "generation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"\n{len(receipt['items'])} images -> {args.out}  (+ generation.json provenance)")


if __name__ == "__main__":
    main()
