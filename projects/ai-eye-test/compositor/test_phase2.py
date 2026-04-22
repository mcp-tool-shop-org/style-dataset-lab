"""Tests for Phase 2 compositor primitives."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from phase2 import (
    BackgroundPool,
    ComposeV2Config,
    add_drop_shadow,
    bridson_poisson_disk,
    color_jittered,
    compose_v2,
    seamless_paste,
)


# ---------- Bridson Poisson-disk ----------

def test_bridson_points_in_bounds():
    pts = bridson_poisson_disk(1000, 1000, min_dist=50, rng=random.Random(0))
    for x, y in pts:
        assert 0 <= x < 1000
        assert 0 <= y < 1000


def test_bridson_min_dist_enforced():
    min_dist = 60
    pts = bridson_poisson_disk(1000, 1000, min_dist=min_dist, rng=random.Random(0))
    # Check all pairs are at least min_dist apart
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            d2 = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            assert d2 + 1e-6 >= min_dist ** 2, f"{a} and {b} closer than {min_dist}"


def test_bridson_scales_to_hundreds():
    # 2048x2048 with min_dist=120 fits ~150-200 points in practice (theoretical max ~290)
    pts = bridson_poisson_disk(2048, 2048, min_dist=120, rng=random.Random(0))
    assert len(pts) >= 150


def test_bridson_deterministic_given_seed():
    a = bridson_poisson_disk(500, 500, 40, random.Random(7))
    b = bridson_poisson_disk(500, 500, 40, random.Random(7))
    assert a == b


# ---------- shadows ----------

def test_drop_shadow_grows_canvas():
    src = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    shadowed = add_drop_shadow(src)
    assert shadowed.size[0] > src.size[0]
    assert shadowed.size[1] > src.size[1]


def test_drop_shadow_preserves_source_alpha():
    src = Image.new("RGBA", (50, 50), (0, 200, 0, 255))
    shadowed = add_drop_shadow(src)
    # somewhere in the output, full green alpha should exist (the source)
    arr = np.array(shadowed)
    full = arr[arr[:, :, 3] == 255]
    assert len(full) > 0
    assert (full[:, :3].mean(axis=0) == [0, 200, 0]).all() or (full[:, 1].max() >= 190)


# ---------- color jitter ----------

def test_color_jitter_preserves_alpha_mask():
    # Cutout with a specific alpha shape
    src = np.zeros((20, 20, 4), dtype=np.uint8)
    src[5:15, 5:15, :3] = [100, 150, 200]
    src[5:15, 5:15, 3] = 255
    img = Image.fromarray(src, "RGBA")
    out = color_jittered(img, random.Random(0))
    out_arr = np.array(out)
    assert (out_arr[:, :, 3] == src[:, :, 3]).all(), "alpha channel should be unchanged"


def test_color_jitter_actually_changes_rgb():
    src = np.zeros((20, 20, 4), dtype=np.uint8)
    src[:, :, :3] = [120, 130, 140]
    src[:, :, 3] = 255
    img = Image.fromarray(src, "RGBA")
    out = np.array(color_jittered(img, random.Random(0)))
    # If jitter is actually applied, at least some RGB values change
    assert (out[:, :, :3] != src[:, :, :3]).any()


# ---------- seamless paste ----------

def test_seamless_paste_does_not_crash_and_returns_same_shape():
    bg = np.full((400, 400, 3), 200, dtype=np.uint8)
    fg = np.zeros((60, 60, 4), dtype=np.uint8)
    fg[10:50, 10:50, :3] = [80, 180, 80]
    fg[10:50, 10:50, 3] = 255
    out = seamless_paste(bg, fg, (200, 200))
    assert out.shape == bg.shape


def test_seamless_paste_falls_back_at_edge():
    bg = np.full((400, 400, 3), 200, dtype=np.uint8)
    fg = np.zeros((60, 60, 4), dtype=np.uint8)
    fg[10:50, 10:50, :3] = [80, 180, 80]
    fg[10:50, 10:50, 3] = 255
    # Request a center near the edge that seamlessClone rejects — should still return
    out = seamless_paste(bg, fg, (5, 5))
    assert out.shape == bg.shape


# ---------- compose_v2 ----------

@pytest.fixture
def apple_like_cutout() -> Image.Image:
    img = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
    arr = np.array(img)
    cx, cy, r = 40, 40, 30
    yy, xx = np.ogrid[:80, :80]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    arr[mask] = (40, 180, 40, 255)
    return Image.fromarray(arr, "RGBA")


def test_compose_v2_noise_bg_emits_requested_count(apple_like_cutout):
    cfg = ComposeV2Config(
        count=8,
        bg_size=(512, 512),
        target_instance_long_edge=48,
        background="noise",
        use_seamless_clone=False,
        use_drop_shadow=False,
        use_color_jitter=False,
        seed=3,
    )
    res = compose_v2(apple_like_cutout, cfg)
    assert res.count == 8
    assert len(res.bboxes) == 8


def test_compose_v2_is_deterministic_given_seed(apple_like_cutout):
    cfg = ComposeV2Config(
        count=5,
        bg_size=(256, 256),
        target_instance_long_edge=32,
        background="noise",
        use_seamless_clone=False,
        use_drop_shadow=False,
        use_color_jitter=False,
        seed=11,
    )
    a = compose_v2(apple_like_cutout, cfg)
    b = compose_v2(apple_like_cutout, cfg)
    assert [(bb.x, bb.y, bb.w, bb.h) for bb in a.bboxes] == [
        (bb.x, bb.y, bb.w, bb.h) for bb in b.bboxes
    ]


def test_compose_v2_fails_loud_when_overcrowded(apple_like_cutout):
    cfg = ComposeV2Config(
        count=100,
        bg_size=(128, 128),  # way too small
        target_instance_long_edge=40,
        background="noise",
        seed=1,
    )
    with pytest.raises(RuntimeError):
        compose_v2(apple_like_cutout, cfg)
