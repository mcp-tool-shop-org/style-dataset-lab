"""Shadow ablation: regenerate ONLY the n=100 × 16 seeds from Phase 2
with drop shadows DISABLED. Same seeds, same backgrounds, same placement —
the only variable is the shadow effect.

Output: outputs/synthetic/phase2_noshadow/ with 16 apple_n100_s{00..15}.png

Tests the hypothesis that the Phase 2 @ 2048 / n=100 over-count (signed +42.7)
is driven by drop-shadows being counted as extra instances at high resolution.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from compositor import JitterConfig, alpha_cutout, tight_crop_alpha
from phase2 import BackgroundPool, ComposeV2Config, compose_v2


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HERO_SRC = PROJECT_ROOT / "outputs" / "candidates" / "hero_green_apple_v1.png"
CUTOUT_PATH = PROJECT_ROOT / "outputs" / "cutouts" / "hero_green_apple_v1.png"
BG_DIR = PROJECT_ROOT / "backgrounds"
OUT_DIR = PROJECT_ROOT / "outputs" / "synthetic" / "phase2_noshadow"

N = 100
SEEDS_PER_COUNT = 16
BG_SIZE = (2048, 2048)
TARGET_INSTANCE_LONG_EDGE = 150


def ensure_cutout() -> None:
    if CUTOUT_PATH.exists():
        return
    CUTOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cut = tight_crop_alpha(alpha_cutout(HERO_SRC))
    cut.save(CUTOUT_PATH)


def main() -> int:
    ensure_cutout()
    from PIL import Image
    cutout = Image.open(CUTOUT_PATH).convert("RGBA")
    bg_pool = BackgroundPool.from_dir(BG_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jitter = JitterConfig(rotation_deg_min=-20, rotation_deg_max=20, scale_min=0.8, scale_max=1.2)
    manifest_entries: list[dict] = []
    t0 = time.time()

    for seed_idx in range(SEEDS_PER_COUNT):
        # Must match phase2_build.py seed formula exactly: 10_000 + n*100 + seed_idx
        seed = 10_000 + N * 100 + seed_idx
        cfg = ComposeV2Config(
            count=N,
            bg_size=BG_SIZE,
            target_instance_long_edge=TARGET_INSTANCE_LONG_EDGE,
            seed=seed,
            background="pool",
            jitter=jitter,
            use_seamless_clone=False,
            use_drop_shadow=False,   # <-- THE ABLATION
            use_color_jitter=True,
            max_overlap_frac=0.0,
        )
        res = compose_v2(cutout, cfg, bg_pool=bg_pool)
        name = f"apple_n{N:03d}_s{seed_idx:02d}"
        img_path = OUT_DIR / f"{name}.png"
        meta_path = OUT_DIR / f"{name}.json"
        res.image.save(img_path, "PNG")
        meta_path.write_text(json.dumps({
            "image": img_path.name,
            "count": res.count,
            "seed": res.seed,
            "bboxes_xywh": [[b.x, b.y, b.w, b.h] for b in res.bboxes],
        }, indent=2))
        manifest_entries.append({
            "id": name, "image": img_path.name, "count": res.count,
            "object_class": "green apple", "seed": res.seed,
            "canvas": BG_SIZE, "n_bboxes": len(res.bboxes),
        })
        print(f"  {name}  bboxes={len(res.bboxes)}")

    (OUT_DIR / "manifest.json").write_text(json.dumps({
        "_schema": "ai_eye_test_labels_v0",
        "_description": "Shadow ablation — Phase 2 n=100 with drop_shadow=False. 16 seeds. Same placements as phase2/apple_n100_s*.png.",
        "_ablation": {"drop_shadow": False, "baseline": "phase2"},
        "images": manifest_entries,
    }, indent=2))

    print(f"\ndone. {len(manifest_entries)}/{SEEDS_PER_COUNT} in {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
