from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

art = Path(r"E:/AI/hesperia/art/world-plates-w1")
subjects = [("vertical_city", 4), ("the_towers", 4), ("under_city_hub", 4), ("rust_communion", 4),
            ("failing_lattice", 4), ("toxic_basin", 4), ("radiation_reaches", 4), ("polar_front", 4),
            ("landed_ark", 4), ("dead_sky_hesperos", 3), ("sams_road", 4)]
TW, TH, LBL, COLS = 400, 229, 26, 4
W = COLS * TW
H = sum(TH + LBL for _ in subjects)
sheet = Image.new("RGB", (W, H), (12, 12, 16))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("arial.ttf", 17)
    fsm = ImageFont.truetype("arialbd.ttf", 18)
except Exception:
    font = fsm = ImageFont.load_default()

y = 0
for sid, nvar in subjects:
    draw.rectangle([0, y, W, y + LBL], fill=(30, 30, 40))
    draw.text((6, y + 4), sid, fill=(205, 215, 235), font=fsm)
    y += LBL
    for v in range(nvar):
        p = art / f"{sid}_v{v}.png"
        if p.exists():
            sheet.paste(Image.open(p).convert("RGB").resize((TW, TH)), (v * TW, y))
            draw.text((v * TW + 5, y + 3), f"v{v}", fill=(255, 228, 110), font=font)
    y += TH

sheet.save(art / "_contact_sheet.png")
print("contact sheet:", art / "_contact_sheet.png", sheet.size)
