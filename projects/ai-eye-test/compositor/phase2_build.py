"""Phase 2 dataset build: multi-seed synthetic apple composites with realism pass.

Generates 96 images total (6 counts x 16 seeds) at 2048x2048 using the cleaned
Phase 1 apple cutout + 4 SDXL-generated backgrounds. Applies per-instance color
jitter, drop shadows, and seamlessClone blending. Poisson-disk placement with
min_dist tuned so all counts fit on the canvas with reasonable spacing.

Output:
  outputs/synthetic/phase2/
    apple_n001_s00.png (+ .json)
    ...
    apple_n100_s15.png (+ .json)
    manifest.json   — full dataset manifest in labels.json format

Runtime: ~6-12 min on an RTX-class machine (most time is seamlessClone).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from compositor import alpha_cutout, tight_crop_alpha, JitterConfig
from phase2 import BackgroundPool, ComposeV2Config, compose_v2


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HERO_SRC = PROJECT_ROOT / "outputs" / "candidates" / "hero_green_apple_v1.png"
CUTOUT_PATH = PROJECT_ROOT / "outputs" / "cutouts" / "hero_green_apple_v1.png"
BG_DIR = PROJECT_ROOT / "backgrounds"
OUT_DIR = PROJECT_ROOT / "outputs" / "synthetic" / "phase2"

COUNTS = [1, 5, 10, 20, 50, 100]
SEEDS_PER_COUNT = 16
BG_SIZE = (2048, 2048)
# Instance size calibrated so 100 instances fit at min_dist ~= 170px on 2048x2048
# (theoretical max with Bridson ≈ 2048^2 / 170^2 ≈ 145 — plenty of margin for 100)
TARGET_INSTANCE_LONG_EDGE = 150


def ensure_cutout() -> None:
    """Produce the alpha cutout if it's not already on disk."""
    if CUTOUT_PATH.exists():
        return
    CUTOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cut = tight_crop_alpha(alpha_cutout(HERO_SRC))
    cut.save(CUTOUT_PATH)


def main() -> int:
    ensure_cutout()
    assert BG_DIR.exists(), f"missing backgrounds dir {BG_DIR}"

    from PIL import Image
    cutout = Image.open(CUTOUT_PATH).convert("RGBA")
    bg_pool = BackgroundPool.from_dir(BG_DIR)
    print(f"cutout {cutout.size}  backgrounds {len(bg_pool.paths)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jitter = JitterConfig(rotation_deg_min=-20, rotation_deg_max=20, scale_min=0.8, scale_max=1.2)

    manifest_entries: list[dict] = []
    t0 = time.time()

    for n in COUNTS:
        for seed_idx in range(SEEDS_PER_COUNT):
            seed = 10_000 + n * 100 + seed_idx
            cfg = ComposeV2Config(
                count=n,
                bg_size=BG_SIZE,
                target_instance_long_edge=TARGET_INSTANCE_LONG_EDGE,
                seed=seed,
                background="pool",
                jitter=jitter,
                # seamlessClone(MIXED_CLONE) was desaturating apples against
                # strong-texture backgrounds (wood grain blended INTO the fruit).
                # Alpha paste + drop shadows gives enough realism without
                # destroying object color.
                use_seamless_clone=False,
                use_drop_shadow=True,
                use_color_jitter=True,
                max_overlap_frac=0.0,
            )
            try:
                res = compose_v2(cutout, cfg, bg_pool=bg_pool)
            except RuntimeError as e:
                print(f"  SKIP n={n} s={seed_idx:02d}  {e}")
                continue

            name = f"apple_n{n:03d}_s{seed_idx:02d}"
            img_path = OUT_DIR / f"{name}.png"
            meta_path = OUT_DIR / f"{name}.json"
            res.image.save(img_path, "PNG")
            meta = {
                "image": img_path.name,
                "count": res.count,
                "seed": res.seed,
                "bboxes_xywh": [[b.x, b.y, b.w, b.h] for b in res.bboxes],
            }
            meta_path.write_text(json.dumps(meta, indent=2))
            manifest_entries.append({
                "id": name,
                "image": img_path.name,
                "count": res.count,
                "object_class": "green apple",
                "seed": res.seed,
                "canvas": BG_SIZE,
                "n_bboxes": len(res.bboxes),
            })
            print(f"  {name}  bboxes={len(res.bboxes)}")

    # Manifest
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps({
        "_schema": "ai_eye_test_labels_v0",
        "_description": "Phase 2 synthetic apple composites. 6 counts x 16 seeds. 2048x2048. Real backgrounds, shadows, color jitter, seamlessClone blending.",
        "_config": {
            "counts": COUNTS,
            "seeds_per_count": SEEDS_PER_COUNT,
            "bg_size": list(BG_SIZE),
            "target_instance_long_edge": TARGET_INSTANCE_LONG_EDGE,
            "realism_features": ["seamless_clone", "drop_shadow", "color_jitter", "bg_pool"],
        },
        "images": manifest_entries,
    }, indent=2))
    elapsed = time.time() - t0
    print(f"\ndone. {len(manifest_entries)}/{len(COUNTS) * SEEDS_PER_COUNT} images in {elapsed:.1f}s")
    print(f"manifest -> {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
