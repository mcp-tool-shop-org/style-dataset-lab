#!/usr/bin/env python3
"""wave-runner — bulk Salt Road plate generation against Comfy Cloud.

Consumes a prompt-foundry wave JSON + formula.json, builds the pinned explicit
Qwen-2512 graph per item (txt2img or depth-ControlNet), submits via the
verified comfy_cloud_bridge transport (X-API-Key, server<->server), polls to
terminal state, downloads into the sdlab inbox. Resume-safe: items whose output
file already exists are skipped. Receipts appended to receipts.jsonl.

  python wave-runner.py --wave wave-v2.json [--concurrency 4] [--limit N]
"""
import argparse
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(PROJ, "inbox", "generated", "set-v2-2026-07-30")
BRIDGE_PATH = r"E:\AI\sprite-foundry-packs\packages\pirate-raiders-3d\_cloud_sweep\comfy_cloud_bridge.py"

spec = importlib.util.spec_from_file_location("bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def build_graph(item, F):
    S = F["settings"]
    pos = F["preambles"][item["preamble"]] + ", " + item["subject"]
    neg = F["negatives"][item["neg"]] + item.get("negExtra", "")
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": S["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": S["clip"], "type": S["clip_type"]}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": S["vae"]}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": S["shift"]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": pos}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": neg}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": S["width"], "height": S["height"], "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "seed": item["seed"], "steps": S["steps"],
              "cfg": S["cfg"], "sampler_name": S["sampler"], "scheduler": S["scheduler"],
              "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0], "denoise": S["denoise"]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": f"saltroad_{item['id']}"}},
    }
    cn = item.get("cn")
    if cn:
        g["11"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": S["controlnet_model"]}}
        g["12"] = {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["11", 0], "type": cn["type"]}}
        g["13"] = {"class_type": "LoadImage", "inputs": {"image": cn["image"]}}
        g["14"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": ["5", 0], "negative": ["6", 0], "control_net": ["12", 0], "image": ["13", 0],
            "strength": cn["strength"], "start_percent": 0, "end_percent": cn["end"], "vae": ["3", 0]}}
        g["8"]["inputs"]["positive"] = ["14", 0]
        g["8"]["inputs"]["negative"] = ["14", 1]
    return g


def receipt(path, obj):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default=os.path.join(HERE, "wave-v2.json"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    key = bridge.get_api_key()
    with open(os.path.join(HERE, "formula.json"), encoding="utf-8") as fh:
        F = json.load(fh)
    with open(args.wave, encoding="utf-8") as fh:
        wave = json.load(fh)

    os.makedirs(OUT_DIR, exist_ok=True)
    rpath = os.path.join(OUT_DIR, "receipts.jsonl")

    todo = []
    for item in wave["items"]:
        out = os.path.join(OUT_DIR, f"{item['id']}.png")
        if os.path.exists(out):
            print(f"skip (exists): {item['id']}")
            continue
        todo.append(item)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} items to generate -> {OUT_DIR}")

    inflight = {}  # pid -> item
    done = failed = 0
    idx = 0
    while todo[idx:] or inflight:
        while len(inflight) < args.concurrency and idx < len(todo):
            item = todo[idx]; idx += 1
            try:
                pid = bridge.submit(build_graph(item, F), key)
                inflight[pid] = (item, time.time())
                print(f"submitted {item['id']} ({pid[:8]}) [{idx}/{len(todo)}]")
            except bridge.CloudError as e:
                failed += 1
                print(f"SUBMIT FAIL {item['id']}: {e}")
                receipt(rpath, {"id": item["id"], "status": "submit_failed", "error": str(e)[:300]})
        time.sleep(5)
        for pid in list(inflight):
            item, t0 = inflight[pid]
            try:
                _, _, raw = bridge._req("GET", f"/api/job/{pid}/status", key)
                st = json.loads(raw).get("status")
            except Exception as e:
                print(f"poll error {item['id']}: {e}")
                continue
            if st in ("success", "completed"):
                try:
                    images = bridge.fetch_outputs(pid, key)
                    _, fn, sub, typ = images[0]
                    data = bridge.download(fn, sub, typ, key)
                    out = os.path.join(OUT_DIR, f"{item['id']}.png")
                    with open(out, "wb") as fh:
                        fh.write(data)
                    done += 1
                    print(f"DONE {item['id']} ({int(time.time()-t0)}s) [{done} done/{failed} failed]")
                    receipt(rpath, {"id": item["id"], "status": "ok", "prompt_id": pid,
                                    "seed": item["seed"], "secs": int(time.time() - t0)})
                except Exception as e:
                    failed += 1
                    print(f"DOWNLOAD FAIL {item['id']}: {e}")
                    receipt(rpath, {"id": item["id"], "status": "download_failed", "prompt_id": pid, "error": str(e)[:300]})
                del inflight[pid]
            elif st in ("failed", "cancelled", "error", "timeout"):
                failed += 1
                print(f"JOB FAIL {item['id']}: {st}")
                receipt(rpath, {"id": item["id"], "status": st, "prompt_id": pid})
                del inflight[pid]
            elif time.time() - t0 > 900:
                failed += 1
                print(f"TIMEOUT {item['id']} (900s)")
                receipt(rpath, {"id": item["id"], "status": "poll_timeout", "prompt_id": pid})
                del inflight[pid]
    print(f"WAVE COMPLETE: {done} ok, {failed} failed")


if __name__ == "__main__":
    main()
