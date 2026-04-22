"""Phase 2 compositor primitives.

Adds to Phase 1:
- Bridson Poisson-disk placement (O(n) for hundreds of instances)
- cv2.seamlessClone(MIXED_CLONE) blending — kills alpha halos
- Drop shadows
- Per-instance color jitter
- BackgroundPool rotation
- Optional controlled overlap (z-ordered) per Ghiasi CVPR 2021

compose_v2() uses all of the above. Compatible with the existing ComposeResult
schema from Phase 1 so the same labels_dict() shape feeds the eval harness.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageFilter

from compositor import BBox, ComposeResult, _scale_to_long_edge, jittered, JitterConfig


# ---------- Bridson Poisson-disk ----------

def bridson_poisson_disk(
    width: int,
    height: int,
    min_dist: float,
    rng: random.Random,
    k: int = 30,
) -> list[tuple[float, float]]:
    """Bridson 2007 fast Poisson-disk sampling — O(n). Returns points with at
    least min_dist between them. Fills as many as fit given min_dist + canvas."""
    cell = min_dist / math.sqrt(2)
    gw = max(1, int(math.ceil(width / cell)))
    gh = max(1, int(math.ceil(height / cell)))
    grid: list[list[tuple[float, float] | None]] = [[None] * gw for _ in range(gh)]

    def _grid_coords(p: tuple[float, float]) -> tuple[int, int]:
        return int(p[0] / cell), int(p[1] / cell)

    def _in_neighborhood(p: tuple[float, float]) -> bool:
        gx, gy = _grid_coords(p)
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = gx + dx, gy + dy
                if 0 <= nx < gw and 0 <= ny < gh:
                    q = grid[ny][nx]
                    if q is not None:
                        if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < min_dist ** 2:
                            return True
        return False

    points: list[tuple[float, float]] = []
    active: list[int] = []

    start = (rng.uniform(0, width), rng.uniform(0, height))
    points.append(start)
    sx, sy = _grid_coords(start)
    grid[sy][sx] = start
    active.append(0)

    while active:
        idx = rng.choice(active)
        base = points[idx]
        placed_new = False
        for _ in range(k):
            r = rng.uniform(min_dist, 2 * min_dist)
            theta = rng.uniform(0, 2 * math.pi)
            cand = (base[0] + r * math.cos(theta), base[1] + r * math.sin(theta))
            if 0 <= cand[0] < width and 0 <= cand[1] < height and not _in_neighborhood(cand):
                cx, cy = _grid_coords(cand)
                grid[cy][cx] = cand
                points.append(cand)
                active.append(len(points) - 1)
                placed_new = True
                break
        if not placed_new:
            active.remove(idx)
    return points


# ---------- blending ----------

def _alpha_paste(bg_rgb: np.ndarray, fg_rgba: np.ndarray, top_left: tuple[int, int]) -> None:
    """In-place alpha compositing of fg_rgba onto bg_rgb at top_left."""
    x, y = top_left
    fh, fw = fg_rgba.shape[:2]
    bh, bw = bg_rgb.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(bw, x + fw), min(bh, y + fh)
    if x0 >= x1 or y0 >= y1:
        return
    fx0, fy0 = x0 - x, y0 - y
    fx1, fy1 = fx0 + (x1 - x0), fy0 + (y1 - y0)
    fg_rgb = fg_rgba[fy0:fy1, fx0:fx1, :3].astype(np.float32)
    alpha = (fg_rgba[fy0:fy1, fx0:fx1, 3:4].astype(np.float32)) / 255.0
    dst = bg_rgb[y0:y1, x0:x1].astype(np.float32)
    bg_rgb[y0:y1, x0:x1] = (alpha * fg_rgb + (1 - alpha) * dst).astype(np.uint8)


def seamless_paste(bg_rgb: np.ndarray, fg_rgba: np.ndarray, center: tuple[int, int]) -> np.ndarray:
    """cv2.seamlessClone with MIXED_CLONE. Falls back to alpha paste on failure.

    fg_rgba must be a tight crop of the instance. center is (x, y) in bg coords.
    Returns the new bg (seamlessClone is not in-place)."""
    fh, fw = fg_rgba.shape[:2]
    mask = (fg_rgba[:, :, 3] > 10).astype(np.uint8) * 255
    fg_rgb = cv2.cvtColor(fg_rgba, cv2.COLOR_RGBA2RGB)
    # seamlessClone requires the instance to fit entirely within the bg
    bh, bw = bg_rgb.shape[:2]
    half_w, half_h = fw // 2, fh // 2
    cx, cy = center
    if not (half_w + 1 <= cx < bw - half_w - 1 and half_h + 1 <= cy < bh - half_h - 1):
        # fall back to alpha paste
        bg_copy = bg_rgb.copy()
        _alpha_paste(bg_copy, fg_rgba, (cx - half_w, cy - half_h))
        return bg_copy
    try:
        return cv2.seamlessClone(fg_rgb, bg_rgb, mask, center, cv2.MIXED_CLONE)
    except cv2.error:
        bg_copy = bg_rgb.copy()
        _alpha_paste(bg_copy, fg_rgba, (cx - half_w, cy - half_h))
        return bg_copy


# ---------- shadows ----------

def add_drop_shadow(cutout_rgba: Image.Image, offset: tuple[int, int] = (6, 10), blur: int = 14, opacity: float = 0.35) -> Image.Image:
    """Add a soft drop shadow below the cutout. Returns a new larger RGBA image."""
    ox, oy = offset
    pad = max(blur * 3, abs(ox) + abs(oy) + blur)
    w, h = cutout_rgba.size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    alpha = cutout_rgba.split()[-1]
    shadow_alpha = alpha.point(lambda v: int(v * opacity))
    shadow = Image.new("RGBA", cutout_rgba.size, (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(shadow, (pad + ox, pad + oy), shadow)
    canvas.paste(cutout_rgba, (pad, pad), cutout_rgba)
    return canvas


# ---------- color jitter ----------

def color_jittered(cutout_rgba: Image.Image, rng: random.Random, hue_shift: int = 5, sat_mul: tuple[float, float] = (0.85, 1.15), val_mul: tuple[float, float] = (0.9, 1.1)) -> Image.Image:
    """Lightweight per-instance color jitter in HSV. Preserves alpha."""
    rgba = np.array(cutout_rgba)
    alpha = rgba[:, :, 3]
    hsv = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[:, :, 0] = (hsv[:, :, 0] + rng.randint(-hue_shift, hue_shift)) % 180
    hsv[:, :, 1] *= rng.uniform(*sat_mul)
    hsv[:, :, 2] *= rng.uniform(*val_mul)
    hsv = np.clip(hsv, 0, 255).astype(np.uint8)
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    out = np.dstack([rgb, alpha])
    return Image.fromarray(out, mode="RGBA")


# ---------- background pool ----------

@dataclass
class BackgroundPool:
    paths: list[Path]

    @classmethod
    def from_dir(cls, dir_path: Path) -> "BackgroundPool":
        paths = sorted(dir_path.glob("*.png")) + sorted(dir_path.glob("*.jpg"))
        if not paths:
            raise FileNotFoundError(f"no backgrounds found in {dir_path}")
        return cls(paths=paths)

    def pick(self, rng: random.Random, size: tuple[int, int]) -> Image.Image:
        path = rng.choice(self.paths)
        im = Image.open(path).convert("RGB")
        return im.resize(size, Image.LANCZOS) if im.size != size else im


# ---------- Phase 2 compose ----------

@dataclass(frozen=True)
class ComposeV2Config:
    count: int
    bg_size: tuple[int, int] = (2048, 2048)
    target_instance_long_edge: int = 180
    seed: int = 42
    background: Literal["pool", "noise", "solid"] = "pool"
    bg_rgb: tuple[int, int, int] = (220, 220, 220)
    jitter: JitterConfig = JitterConfig(rotation_deg_min=-15, rotation_deg_max=15, scale_min=0.8, scale_max=1.2)
    use_seamless_clone: bool = True
    use_drop_shadow: bool = True
    use_color_jitter: bool = True
    max_overlap_frac: float = 0.0  # 0.0 = no overlap; 0.3 = allow 30% bbox overlap


def compose_v2(cutout: Image.Image, cfg: ComposeV2Config, bg_pool: BackgroundPool | None = None) -> ComposeResult:
    rng = random.Random(cfg.seed)
    base = _scale_to_long_edge(cutout, cfg.target_instance_long_edge)

    # Background
    if cfg.background == "pool":
        if bg_pool is None:
            raise ValueError("background='pool' requires bg_pool")
        bg_pil = bg_pool.pick(rng, cfg.bg_size)
    elif cfg.background == "solid":
        bg_pil = Image.new("RGB", cfg.bg_size, cfg.bg_rgb)
    else:  # noise
        arr = np.full((cfg.bg_size[1], cfg.bg_size[0], 3), cfg.bg_rgb, dtype=np.int16)
        np_rng = np.random.default_rng(rng.randint(0, 2**31))
        arr += np_rng.integers(-8, 9, size=arr.shape, dtype=np.int16)
        bg_pil = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    bg_rgb = np.array(bg_pil)  # (H, W, 3)

    # Place instance centers with Poisson-disk, then verify/adjust for instance sizes
    # Minimum distance = instance long edge * (1 - overlap) * safety factor
    min_dist = cfg.target_instance_long_edge * (1 - cfg.max_overlap_frac) * 1.1
    centers = bridson_poisson_disk(cfg.bg_size[0], cfg.bg_size[1], min_dist, rng, k=30)
    if len(centers) < cfg.count:
        raise RuntimeError(
            f"Poisson-disk placed {len(centers)} candidates, need {cfg.count}. "
            f"Reduce count, reduce target_instance_long_edge, or increase bg_size."
        )
    rng.shuffle(centers)
    centers = centers[: cfg.count]

    bboxes: list[BBox] = []
    for cx, cy in centers:
        inst = jittered(base, cfg.jitter, rng)
        if cfg.use_color_jitter:
            inst = color_jittered(inst, rng)
        if cfg.use_drop_shadow:
            inst = add_drop_shadow(inst)

        # Tight crop of the instance in case shadow added transparent padding we don't want the center-based paste to use
        inst_rgba = np.array(inst)
        alpha = inst_rgba[:, :, 3]
        ys, xs = np.nonzero(alpha > 0)
        if len(xs) == 0:
            continue
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        inst_rgba = inst_rgba[y0:y1, x0:x1]
        ih, iw = inst_rgba.shape[:2]

        paste_cx = int(cx)
        paste_cy = int(cy)
        top_left = (paste_cx - iw // 2, paste_cy - ih // 2)

        if cfg.use_seamless_clone:
            bg_rgb = seamless_paste(bg_rgb, inst_rgba, (paste_cx, paste_cy))
        else:
            _alpha_paste(bg_rgb, inst_rgba, top_left)

        bboxes.append(BBox(top_left[0], top_left[1], iw, ih))

    final = Image.fromarray(bg_rgb, "RGB")
    return ComposeResult(image=final, count=cfg.count, bboxes=bboxes, seed=cfg.seed)
