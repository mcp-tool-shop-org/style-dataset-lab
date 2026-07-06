from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

out = Path(r"E:/AI/style-dataset-lab/projects/hesperia/outputs/npcs-wave-2")
ids = ["ledgerhand", "lodestone", "lasthold", "vex", "kess", "mirella",
       "marek_dren", "joren_kade", "silas_rook", "grindwheel", "splice_forge",
       "administrator_kaelen", "bulwark", "curator_valerius", "marshal_corvus", "cormac_rell"]
tiles = []
for i in ids:
    for v in (0, 1):
        p = out / f"{i}_v{v}.png"
        if p.exists():
            tiles.append((f"{i} v{v}", p))

COLS, TW, TH, LBL = 6, 270, 347, 22
rows = (len(tiles) + COLS - 1) // COLS
W, H = COLS * TW, rows * (TH + LBL)
sheet = Image.new("RGB", (W, H), (12, 12, 16))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("arialbd.ttf", 14)
except Exception:
    font = ImageFont.load_default()

for idx, (lbl, p) in enumerate(tiles):
    c, r = idx % COLS, idx // COLS
    x, y = c * TW, r * (TH + LBL)
    draw.rectangle([x, y, x + TW, y + LBL], fill=(30, 30, 40))
    draw.text((x + 4, y + 3), lbl, fill=(255, 228, 110), font=font)
    sheet.paste(Image.open(p).convert("RGB").resize((TW, TH)), (x, y + LBL))

sheet.save(out / "_contact_sheet.png")
print("npc2 contact:", out / "_contact_sheet.png", sheet.size)
