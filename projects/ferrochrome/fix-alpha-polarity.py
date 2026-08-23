#!/usr/bin/env python3
"""Repair inverted alpha on ferrochrome isolated-subject PNGs.

WHY THIS EXISTS
---------------
The cloud graph recorded in HANDOFF.md wired:

    SaveImageWithAlpha(images=VAEDecode[0], mask=RMBG[1])

RMBG (comfyui-rmbg) emits outputs [IMAGE, MASK, IMAGE]. Its MASK output is
BACKGROUND-positive, so handing it straight to SaveImageWithAlpha as alpha
punches the android OUT and keeps the studio backdrop. Every alpha PNG this
project produced before 2026-08-22 has the subject transparent and the
background opaque.

The RGB channels are untouched by the bug -- images come from VAEDecode[0],
not from RMBG -- so this is a lossless on-disk repair. No regeneration needed.

THE GRAPH FIX (do this so the bug stops recurring):

    RMBG[1] -> InvertMask -> SaveImageWithAlpha.mask

IDEMPOTENCE
-----------
Detection is by the 4px border ring: an isolated subject on a transparent
field has a mostly-transparent ring. >50% opaque ring == inverted. After
repair the ring drops near zero, so re-running this script is a no-op.

COMPENSATOR (NAMED_COMPENSATORS, workflow-standards.md)
------------------------------------------------------
  undo:  git checkout -- projects/ferrochrome/outputs
  state after rollback: PNGs return to inverted-alpha originals (RGB identical)
  owner: whoever runs this script

Usage:
    python fix-alpha-polarity.py [--dry-run] [root]
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

RING = 4
OPAQUE_RING_THRESHOLD = 0.50


def ring_opaque_fraction(alpha: np.ndarray) -> float:
    """Fraction of the outer border ring that is opaque."""
    ring = np.concatenate([
        alpha[:RING].ravel(),
        alpha[-RING:].ravel(),
        alpha[:, :RING].ravel(),
        alpha[:, -RING:].ravel(),
    ])
    return float((ring > 128).mean())


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    root = Path(args[0]) if args else Path(__file__).parent / "outputs"

    repaired = skipped = 0
    for path in sorted(root.rglob("*.png")):
        image = Image.open(path)
        if image.mode != "RGBA":
            continue

        pixels = np.array(image)
        fraction = ring_opaque_fraction(pixels[:, :, 3])
        rel = path.relative_to(root)

        if fraction <= OPAQUE_RING_THRESHOLD:
            print(f"  ok      {rel}  (ring {fraction:.0%} opaque)")
            skipped += 1
            continue

        print(f"  INVERT  {rel}  (ring {fraction:.0%} opaque)")
        repaired += 1
        if dry_run:
            continue

        pixels[:, :, 3] = 255 - pixels[:, :, 3]
        Image.fromarray(pixels, mode="RGBA").save(path)

    verb = "would repair" if dry_run else "repaired"
    print(f"\n{verb} {repaired}, left alone {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
