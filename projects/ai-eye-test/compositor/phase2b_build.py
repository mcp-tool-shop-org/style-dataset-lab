"""Phase 2b: scale-ablation build.

Regenerates the Phase 2 setup on a 1024x1024 canvas with 110px instances
(matching Phase 1's canvas/instance ratio), at Phase 2's statistical power
(16 seeds per count). Counts are capped at 20 because higher counts won't
fit on a 1024x1024 canvas at 110px instance size.

Purpose: isolate instance-size-relative-to-canvas from input resolution.
If Phase 2b @ 256 shows OVER-count while Phase 2 @ 256 shows UNDER-count,
we've cleanly separated the two variables — apparent instance size at the
eval resolution drives the bias direction, not input resolution per se.

Total images: 4 counts × 16 seeds = 64.
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
OUT_DIR = PROJECT_ROOT / "outputs" / "synthetic" / "phase2b"

COUNTS = [1, 5, 10, 20]
SEEDS_PER_COUNT = 16
BG_SIZE = (1024, 1024)
TARGET_INSTANCE_LONG_EDGE = 110   # matches Phase 1


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

    for n in COUNTS:
        for seed_idx in range(SEEDS_PER_COUNT):
            # Distinct seed namespace from Phase 2 (which uses 10_000 + n*100 + idx)
            seed = 20_000 + n * 100 + seed_idx
            cfg = ComposeV2Config(
                count=n,
                bg_size=BG_SIZE,
                target_instance_long_edge=TARGET_INSTANCE_LONG_EDGE,
                seed=seed,
                background="pool",
                jitter=jitter,
                use_seamless_clone=False,
                use_drop_shadow=True,
                use_color_jitter=True,
                max_overlap_frac=0.0,
            )
            res = compose_v2(cutout, cfg, bg_pool=bg_pool)
            name = f"apple_n{n:03d}_s{seed_idx:02d}"
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
        "_description": "Phase 2b scale ablation — 1024x1024 canvas, 110px instances (Phase 1 scale) at Phase 2 sample size (16 seeds/count).",
        "_config": {
            "counts": COUNTS,
            "seeds_per_count": SEEDS_PER_COUNT,
            "bg_size": list(BG_SIZE),
            "target_instance_long_edge": TARGET_INSTANCE_LONG_EDGE,
            "purpose": "Isolate instance-size-relative-to-canvas from input resolution",
        },
        "images": manifest_entries,
    }, indent=2))

    print(f"\ndone. {len(manifest_entries)}/{len(COUNTS) * SEEDS_PER_COUNT} in {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
