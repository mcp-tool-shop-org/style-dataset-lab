"""Tests for the compositor. Focus on the tricky logic (non-overlap + labels)."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from compositor import (
    BBox,
    ComposeConfig,
    JitterConfig,
    compose,
    jittered,
    sample_non_overlapping,
    save,
    tight_crop_alpha,
)


# ---------- bbox ----------

def test_bbox_overlaps_adjacent_not_overlapping():
    a = BBox(0, 0, 10, 10)
    b = BBox(10, 0, 10, 10)  # touches on right edge
    assert not a.overlaps(b, pad=0)


def test_bbox_overlaps_with_pad():
    a = BBox(0, 0, 10, 10)
    b = BBox(10, 0, 10, 10)
    assert a.overlaps(b, pad=1)  # pad=1 forces a 1px gap


def test_bbox_overlaps_overlapping():
    a = BBox(0, 0, 10, 10)
    b = BBox(5, 5, 10, 10)
    assert a.overlaps(b)


# ---------- placement ----------

def test_sample_non_overlapping_produces_disjoint_boxes():
    rng = random.Random(0)
    sizes = [(32, 32)] * 20
    boxes = sample_non_overlapping(1024, 1024, sizes, rng, pad=2)
    assert len(boxes) == 20
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert not a.overlaps(b, pad=2)


def test_sample_non_overlapping_fails_when_overcrowded():
    rng = random.Random(0)
    # 100 of 32x32 on a 40x40 bg = impossible
    sizes = [(32, 32)] * 100
    with pytest.raises(RuntimeError):
        sample_non_overlapping(40, 40, sizes, rng, pad=2)


def test_sample_non_overlapping_rejects_instance_larger_than_bg():
    rng = random.Random(0)
    with pytest.raises(ValueError):
        sample_non_overlapping(10, 10, [(20, 20)], rng)


# ---------- jitter ----------

def test_jitter_is_deterministic_given_seed():
    src = Image.new("RGBA", (64, 32), (255, 0, 0, 255))
    cfg = JitterConfig()
    a = jittered(src, cfg, random.Random(42))
    b = jittered(src, cfg, random.Random(42))
    assert a.size == b.size


# ---------- tight crop ----------

def test_tight_crop_alpha_shrinks_to_visible_bbox():
    # 100x100 image with a 20x20 opaque square at (10, 10)
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    patch = Image.new("RGBA", (20, 20), (255, 255, 255, 255))
    img.paste(patch, (10, 10), patch)
    cropped = tight_crop_alpha(img)
    assert cropped.size == (20, 20)


# ---------- compose ----------

@pytest.fixture
def tiny_cutout() -> Image.Image:
    # small opaque disc on a transparent 64x64 canvas
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    cx, cy, r = 32, 32, 24
    arr = np.array(img)
    yy, xx = np.ogrid[:64, :64]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    arr[mask] = (40, 140, 40, 255)
    return Image.fromarray(arr, mode="RGBA")


def test_compose_emits_exact_count(tiny_cutout):
    cfg = ComposeConfig(count=10, bg_size=(512, 512), target_instance_long_edge=48, seed=7)
    res = compose(tiny_cutout, cfg)
    assert res.count == 10
    assert len(res.bboxes) == 10


def test_compose_bboxes_inside_canvas(tiny_cutout):
    cfg = ComposeConfig(count=12, bg_size=(512, 512), target_instance_long_edge=48, seed=3)
    res = compose(tiny_cutout, cfg)
    for b in res.bboxes:
        assert 0 <= b.x and 0 <= b.y
        assert b.x2 <= 512 and b.y2 <= 512


def test_compose_bboxes_non_overlapping(tiny_cutout):
    cfg = ComposeConfig(count=15, bg_size=(1024, 1024), target_instance_long_edge=48, seed=9)
    res = compose(tiny_cutout, cfg)
    for i, a in enumerate(res.bboxes):
        for b in res.bboxes[i + 1:]:
            assert not a.overlaps(b), f"overlap between {a} and {b}"


def test_compose_is_deterministic_given_seed(tiny_cutout):
    cfg = ComposeConfig(count=8, bg_size=(512, 512), target_instance_long_edge=48, seed=11)
    a = compose(tiny_cutout, cfg)
    b = compose(tiny_cutout, cfg)
    assert [b.__dict__ for b in a.bboxes] == [b.__dict__ for b in b.bboxes]


def test_save_writes_image_and_json(tiny_cutout, tmp_path: Path):
    cfg = ComposeConfig(count=5, bg_size=(256, 256), target_instance_long_edge=32, seed=1)
    res = compose(tiny_cutout, cfg)
    img_path = save(res, tmp_path, "sample")
    assert img_path.exists()
    meta = (tmp_path / "sample.json").read_text()
    assert '"count": 5' in meta
    assert '"bboxes_xywh":' in meta
