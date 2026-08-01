#!/usr/bin/env python3
"""measure-palette — quantify the yellow bias across the approved plates.

Not a vibe check: per plate, bin every reasonably-saturated pixel by hue and
report the share falling in the YELLOW band vs the contract's intended
RED-OCHRE band. The contract's facade anchors are ochre-warm #c9a877 (hue ~33
deg) and ochre-red #a86b4c (hue ~19 deg). Saturated lemon/canary yellow sits
~45-65 deg. Anything with a big 45-65 mass is off-contract.
"""
import colorsys, os, glob, json
from PIL import Image

APPROVED = r"E:\AI\style-dataset-lab\projects\salt-road\outputs\approved"

def anchor_hue(hexs):
    r, g, b = (int(hexs[i:i+2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360

print(f"contract anchors: ochre-warm #c9a877 = {anchor_hue('#c9a877'):.1f} deg | "
      f"ochre-red #a86b4c = {anchor_hue('#a86b4c'):.1f} deg\n")

rows = []
for p in sorted(glob.glob(os.path.join(APPROVED, "*.png"))):
    im = Image.open(p).convert("RGB").resize((240, 137))
    yellow = redochre = other = 0
    for (r, g, b) in im.getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s < 0.22 or v < 0.18:      # ignore greys/darks — stone, tar, shadow
            continue
        hd = h * 360
        if 42 <= hd <= 70:            # lemon / canary / saturated yellow
            yellow += 1
        elif 8 <= hd < 42:            # red-ochre .. warm-ochre (the contract band)
            redochre += 1
        else:
            other += 1
    tot = yellow + redochre + other
    if tot == 0:
        continue
    rows.append({
        "plate": os.path.basename(p).replace("styleset_", "").replace(".png", ""),
        "yellow_pct": round(100 * yellow / tot, 1),
        "redochre_pct": round(100 * redochre / tot, 1),
        "ratio": round(yellow / max(redochre, 1), 2),
    })

rows.sort(key=lambda r: -r["yellow_pct"])
print(f"{'plate':40s} {'yellow%':>8s} {'redochre%':>10s} {'y/r':>6s}")
for r in rows:
    flag = "  <-- YELLOW-DOMINANT" if r["yellow_pct"] >= 25 and r["ratio"] >= 1.0 else ""
    print(f"{r['plate']:40s} {r['yellow_pct']:8.1f} {r['redochre_pct']:10.1f} {r['ratio']:6.2f}{flag}")

offenders = [r for r in rows if r["yellow_pct"] >= 25 and r["ratio"] >= 1.0]
ymean = sum(r["yellow_pct"] for r in rows) / len(rows)
rmean = sum(r["redochre_pct"] for r in rows) / len(rows)
print(f"\nplates: {len(rows)} | mean yellow {ymean:.1f}% | mean red-ochre {rmean:.1f}%")
print(f"YELLOW-DOMINANT plates: {len(offenders)}")
json.dump({"rows": rows, "offenders": [o["plate"] for o in offenders]},
          open(r"E:\AI\style-dataset-lab\projects\salt-road\inputs\prompts\palette-audit.json", "w"), indent=2)
