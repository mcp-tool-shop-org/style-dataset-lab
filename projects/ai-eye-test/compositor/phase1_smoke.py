"""Phase 1 smoke: take one SDXL hero instance, cut it out, compose at counts [1, 5, 10, 20].

Emits 4 composite PNGs + 4 ground-truth JSON files into
`projects/ai-eye-test/outputs/synthetic/phase1/`.

Run:  python compositor/phase1_smoke.py
"""

from __future__ import annotations

from pathlib import Path

from compositor import (
    ComposeConfig,
    JitterConfig,
    alpha_cutout,
    compose,
    save,
    tight_crop_alpha,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HERO_SRC = PROJECT_ROOT / "outputs" / "candidates" / "hero_green_apple_v1.png"
OUT_DIR = PROJECT_ROOT / "outputs" / "synthetic" / "phase1"
CUTOUT_DIR = PROJECT_ROOT / "outputs" / "cutouts"


def main() -> int:
    assert HERO_SRC.exists(), f"missing hero source {HERO_SRC}"
    print(f"hero:   {HERO_SRC}")

    # 1. Cutout
    CUTOUT_DIR.mkdir(parents=True, exist_ok=True)
    cutout_path = CUTOUT_DIR / "hero_green_apple_v1.png"
    cutout = tight_crop_alpha(alpha_cutout(HERO_SRC))
    cutout.save(cutout_path, "PNG")
    print(f"cutout: {cutout_path}  {cutout.size}")

    # 2. Compose at varied counts
    counts = [1, 5, 10, 20]
    jitter = JitterConfig(rotation_deg_min=-15, rotation_deg_max=15, scale_min=0.85, scale_max=1.15)

    for n in counts:
        cfg = ComposeConfig(
            count=n,
            bg_size=(1024, 1024),
            target_instance_long_edge=110,
            pad_between_pct=6,
            seed=42 + n,
            bg_kind="noise",
            bg_rgb=(225, 225, 225),
            jitter=jitter,
        )
        res = compose(cutout, cfg)
        img_path = save(res, OUT_DIR, f"apple_n{n:03d}")
        print(f"n={n:>2}  -> {img_path.name}  bboxes={len(res.bboxes)}  seed={res.seed}")

    print(f"\ndone. outputs in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
