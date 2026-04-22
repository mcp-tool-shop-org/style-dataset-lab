"""Programmatic compositor for exact-count image generation.

Takes a clean hero instance (e.g. one SDXL-generated object on neutral bg),
cuts out its alpha via rembg, and pastes N jittered copies onto a background.
Emits (image, count, bboxes) with ground truth authored by construction.

See memory: Phase 1 MVP — one category, counts 1..20, single background type.
"""

from __future__ import annotations

import io
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image


# ---------- cutout ----------

def alpha_cutout(source_png: Path) -> Image.Image:
    """Return an RGBA PIL image with background removed via rembg (U-2-Net)."""
    from rembg import remove
    data = source_png.read_bytes()
    out = remove(data)
    return Image.open(io.BytesIO(out)).convert("RGBA")


def tight_crop_alpha(img: Image.Image) -> Image.Image:
    """Crop an RGBA image to the tight bbox of its non-transparent pixels."""
    assert img.mode == "RGBA"
    alpha = np.array(img.split()[-1])
    ys, xs = np.nonzero(alpha > 0)
    if len(xs) == 0:
        return img
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    return img.crop((int(x0), int(y0), int(x1), int(y1)))


# ---------- placement ----------

@dataclass(frozen=True)
class BBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def overlaps(self, other: "BBox", pad: int = 0) -> bool:
        return not (
            self.x2 + pad <= other.x
            or other.x2 + pad <= self.x
            or self.y2 + pad <= other.y
            or other.y2 + pad <= self.y
        )


def sample_non_overlapping(
    bg_w: int,
    bg_h: int,
    instance_sizes: list[tuple[int, int]],
    rng: random.Random,
    pad: int = 2,
    max_tries_per_instance: int = 200,
) -> list[BBox]:
    """Rejection-sample non-overlapping placements. Fails explicitly if density too high."""
    placed: list[BBox] = []
    for i, (w, h) in enumerate(instance_sizes):
        if w >= bg_w or h >= bg_h:
            raise ValueError(f"instance {i} ({w}x{h}) too large for background ({bg_w}x{bg_h})")
        for _ in range(max_tries_per_instance):
            x = rng.randint(0, bg_w - w)
            y = rng.randint(0, bg_h - h)
            cand = BBox(x, y, w, h)
            if all(not cand.overlaps(p, pad=pad) for p in placed):
                placed.append(cand)
                break
        else:
            raise RuntimeError(
                f"could not place instance {i} after {max_tries_per_instance} tries "
                f"({len(placed)}/{len(instance_sizes)} placed). Reduce count or scale."
            )
    return placed


# ---------- jitter ----------

@dataclass(frozen=True)
class JitterConfig:
    rotation_deg_min: float = 0.0
    rotation_deg_max: float = 360.0
    scale_min: float = 0.85
    scale_max: float = 1.15


def jittered(cutout: Image.Image, cfg: JitterConfig, rng: random.Random) -> Image.Image:
    angle = rng.uniform(cfg.rotation_deg_min, cfg.rotation_deg_max)
    scale = rng.uniform(cfg.scale_min, cfg.scale_max)
    rotated = cutout.rotate(angle, expand=True, resample=Image.BICUBIC)
    w = max(1, int(rotated.width * scale))
    h = max(1, int(rotated.height * scale))
    return rotated.resize((w, h), resample=Image.BICUBIC)


# ---------- backgrounds ----------

def solid_bg(size: tuple[int, int], rgb: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", size, rgb)


def noise_bg(size: tuple[int, int], rng: random.Random, base: tuple[int, int, int] = (220, 220, 220), noise: int = 8) -> Image.Image:
    w, h = size
    arr = np.full((h, w, 3), base, dtype=np.int16)
    arr += rng.randint(-noise, noise)
    arr += np.random.default_rng(rng.randint(0, 2**31)).integers(-noise, noise + 1, size=(h, w, 3), dtype=np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")


# ---------- compose ----------

@dataclass(frozen=True)
class ComposeConfig:
    count: int
    bg_size: tuple[int, int] = (1024, 1024)
    target_instance_long_edge: int = 96
    pad_between_pct: int = 2
    seed: int = 42
    bg_kind: Literal["solid", "noise"] = "noise"
    bg_rgb: tuple[int, int, int] = (220, 220, 220)
    jitter: JitterConfig = JitterConfig()


@dataclass
class ComposeResult:
    image: Image.Image
    count: int
    bboxes: list[BBox]
    seed: int

    def labels_dict(self, image_path: str) -> dict:
        return {
            "image": image_path,
            "count": self.count,
            "seed": self.seed,
            "bboxes_xywh": [[b.x, b.y, b.w, b.h] for b in self.bboxes],
        }


def _scale_to_long_edge(img: Image.Image, target_long_edge: int) -> Image.Image:
    long = max(img.width, img.height)
    if long == target_long_edge:
        return img
    scale = target_long_edge / long
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)


def compose(cutout: Image.Image, cfg: ComposeConfig) -> ComposeResult:
    rng = random.Random(cfg.seed)
    base = _scale_to_long_edge(cutout, cfg.target_instance_long_edge)

    # Pre-generate jittered instances so we know sizes before placement
    instances = [jittered(base, cfg.jitter, rng) for _ in range(cfg.count)]
    sizes = [(im.width, im.height) for im in instances]
    placements = sample_non_overlapping(*cfg.bg_size, sizes, rng, pad=cfg.pad_between_pct)

    if cfg.bg_kind == "solid":
        bg = solid_bg(cfg.bg_size, cfg.bg_rgb)
    else:
        bg = noise_bg(cfg.bg_size, rng, base=cfg.bg_rgb)

    bboxes: list[BBox] = []
    for inst, place in zip(instances, placements):
        bg.paste(inst, (place.x, place.y), inst)
        bboxes.append(place)

    return ComposeResult(image=bg, count=cfg.count, bboxes=bboxes, seed=cfg.seed)


def save(result: ComposeResult, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    img_path = out_dir / f"{name}.png"
    meta_path = out_dir / f"{name}.json"
    result.image.save(img_path, "PNG")
    meta_path.write_text(json.dumps(result.labels_dict(img_path.name), indent=2))
    return img_path
