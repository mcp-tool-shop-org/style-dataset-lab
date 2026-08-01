"""Salt Road — counting house interior module, authored as blocky proxy geometry.

Contract §7: "A standing desk, a ledger, a wax jack burned to a stub; the window faces
the water." The window is the anchor: it is a real APERTURE in the back wall, so the
depth pass reads it as far-void and the sampler paints harbour light through it, with
the standing desk silhouetted in front.

Same recipe as bonded_warehouse_module.py — crude boxes and cylinders, density carried
by authored STUFF (v4 finding: interiors fail on density, not surface). The counting
house's stuff is paper: pigeonhole shelving with rolled documents, ledger rows, deed
boxes, a public counter rail dividing the room the way a bank floor divides.

Run:
  blender.exe -b -P counting_house_module.py -- --out <dir>

Emits, at the plate's native 1344x768:
  module_depth.png   normalised inverted Z  (ControlNet 'depth')
  module_clay.png    flat-shaded beauty     (source for a canny/lineart guide)
  module.blend       the saved template, so the camera is reusable per module
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--width", type=int, default=1344)
ap.add_argument("--height", type=int, default=768)
args = ap.parse_args(argv)
os.makedirs(args.out, exist_ok=True)

# ---------------------------------------------------------------- clean slate
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def box(name, loc, size, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    # size is the FULL extent: base cube spans ±0.5, so scale == size.
    # (bonded_warehouse's /2 helper makes half-size boxes; its scene is uniformly
    # blobby and survived it, but precision placement math needs true extents.)
    o.scale = Vector(size)
    return o


def cyl(name, loc, r, depth, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc,
                                        rotation=rot, vertices=16)
    o = bpy.context.object
    o.name = name
    return o


# ---------------------------------------------------------------- the shell
# A panelled counting room seen down its axis. Camera looks along +Y from -Y.
# Lower and tighter than the warehouse: this is a room money is counted in.
W, D, H = 8.0, 11.0, 3.6
box("floor", (0, 0, -0.1), (W, D, 0.2))
box("ceiling", (0, 0, H), (W, D, 0.2))
box("wall_L", (-W / 2, 0, H / 2), (0.2, D, H))
box("wall_R", (W / 2, 0, H / 2), (0.2, D, H))

# back wall built AROUND the window aperture — the window faces the water.
# Aperture 2.6 wide x 1.6 tall, sill at 1.05. Depth sees through it to far-void.
AW, AH, SILL = 2.6, 1.6, 1.05
box("wall_back_L", (-(W / 2 + AW / 2) / 2 - 0.0, D / 2, H / 2), ((W - AW) / 2, 0.2, H))
box("wall_back_R", ((W / 2 + AW / 2) / 2 + 0.0, D / 2, H / 2), ((W - AW) / 2, 0.2, H))
# recentre the two flanking pieces properly
bpy.data.objects["wall_back_L"].location.x = -(AW / 2 + (W - AW) / 4)
bpy.data.objects["wall_back_R"].location.x = (AW / 2 + (W - AW) / 4)
box("wall_back_below", (0, D / 2, SILL / 2), (AW, 0.2, SILL))
box("wall_back_above", (0, D / 2, (H + SILL + AH) / 2), (AW, 0.2, H - SILL - AH))
# mullions crossing the aperture — small panes, early-modern glazing
for i, mx in enumerate((-0.65, 0.0, 0.65)):
    box(f"mullion_v_{i}", (mx, D / 2, SILL + AH / 2), (0.07, 0.14, AH))
box("mullion_h", (0, D / 2, SILL + AH / 2), (AW, 0.14, 0.07))
box("window_sill", (0, D / 2 - 0.12, SILL), (AW + 0.3, 0.3, 0.09))

# ceiling joists — close-set, a low panelled ceiling with visible timber
for i in range(14):
    y = -D / 2 + 0.6 + i * 0.75
    box(f"joist_{i}", (0, y, H - 0.14), (W, 0.16, 0.2))
box("girder_mid", (0, -0.5, H - 0.3), (W, 0.3, 0.3))

# wainscot panelling rails along both walls (shallow relief the clay pass can read)
for sx in (-1, 1):
    box(f"wainscot_rail_{'L' if sx < 0 else 'R'}",
        (sx * (W / 2 - 0.14), 0, 1.15), (0.08, D, 0.1))

# ---------------------------------------------------------------- clerks' end
# Low dais before the window; the standing desk on it, silhouetted against the light.
box("dais", (0, D / 2 - 1.5, 0.09), (4.6, 2.6, 0.18))

# the standing desk — sloped top, contract's named object
box("desk_body", (0, D / 2 - 1.35, 0.62), (1.5, 0.72, 0.9))
box("desk_slope", (0, D / 2 - 1.32, 1.14), (1.5, 0.78, 0.09), rot=(math.radians(-14), 0, 0))
box("desk_ledge", (0, D / 2 - 0.97, 1.02), (1.5, 0.07, 0.07))
# the ledger, open — two leaves angled like a spread book
box("ledger_L", (-0.19, D / 2 - 1.33, 1.2), (0.36, 0.5, 0.05), rot=(math.radians(-14), math.radians(7), 0))
box("ledger_R", (0.19, D / 2 - 1.33, 1.2), (0.36, 0.5, 0.05), rot=(math.radians(-14), math.radians(-7), 0))
# the wax jack burned to a stub, and the inkwell beside it
cyl("wax_jack_base", (0.58, D / 2 - 1.18, 1.26), 0.07, 0.05)
cyl("wax_jack_stub", (0.58, D / 2 - 1.18, 1.32), 0.025, 0.07)
cyl("inkwell", (-0.58, D / 2 - 1.2, 1.28), 0.055, 0.09)
box("sand_shaker", (-0.44, D / 2 - 1.12, 1.28), (0.07, 0.07, 0.11))
# tall stool behind the desk
for dx, dy in ((-0.2, -0.2), (0.2, -0.2), (-0.2, 0.2), (0.2, 0.2)):
    box(f"stool_leg_{dx:+.1f}_{dy:+.1f}", (dx * 1.0, D / 2 - 2.35 + dy, 0.45), (0.06, 0.06, 0.9))
box("stool_seat", (0, D / 2 - 2.35, 0.93), (0.5, 0.5, 0.07))

# strongbox by the dais — iron-banded chest
box("strongbox", (2.2, D / 2 - 1.4, 0.42), (1.05, 0.68, 0.66))
for i, bx in enumerate((-0.3, 0.0, 0.3)):
    box(f"strongbox_band_{i}", (2.2 + bx, D / 2 - 1.4, 0.42), (0.07, 0.72, 0.7))
box("strongbox_lid", (2.2, D / 2 - 1.4, 0.79), (1.09, 0.72, 0.1))

# coin scale on its side table, left of the desk
box("scale_table", (-2.3, D / 2 - 1.5, 0.42), (0.9, 0.62, 0.06))
for dx, dy in ((-0.38, -0.24), (0.38, -0.24), (-0.38, 0.24), (0.38, 0.24)):
    box(f"scale_table_leg_{dx:+.1f}_{dy:+.1f}", (-2.3 + dx, D / 2 - 1.5 + dy, 0.2), (0.06, 0.06, 0.4))
box("coin_scale_pillar", (-2.3, D / 2 - 1.5, 0.68), (0.05, 0.05, 0.44))
box("coin_scale_beam", (-2.3, D / 2 - 1.5, 0.9), (0.6, 0.04, 0.04))
for sx in (-0.26, 0.26):
    cyl(f"coin_pan_{sx:+.2f}", (-2.3 + sx, D / 2 - 1.5, 0.78), 0.09, 0.03)
for i in range(4):  # small weight row beside the scale
    cyl(f"coin_weight_{i}", (-2.62 + i * 0.09, D / 2 - 1.28, 0.47), 0.028, 0.05)

# ---------------------------------------------------------------- the paper walls
# left wall: pigeonhole shelving stuffed with rolled documents — the counting house's
# equivalent of the warehouse's cask stacks. Grid of dividers, rolls poking out.
PH_X = -W / 2 + 0.35
box("pigeon_frame", (PH_X, 1.2, 1.5), (0.5, 4.6, 2.4))
for i in range(6):  # shelves
    box(f"pigeon_shelf_{i}", (PH_X + 0.05, 1.2, 0.42 + i * 0.43), (0.46, 4.6, 0.05))
for i in range(9):  # vertical dividers
    box(f"pigeon_div_{i}", (PH_X + 0.05, -1.0 + i * 0.55, 1.5), (0.46, 0.05, 2.4))
# rolled documents in holes, varied stick-out — deterministic scatter
_roll = 0
for r in range(5):
    for c in range(8):
        if (r * 7 + c * 3) % 3 == 0:
            continue  # some holes empty — a full grid reads as texture, not stuff
        _roll += 1
        cyl(f"doc_roll_{_roll}",
            (PH_X + 0.28 + ((r + c) % 3) * 0.04, -0.86 + c * 0.55, 0.64 + r * 0.43),
            0.045, 0.5, rot=(0, math.radians(90), 0))

# right wall: ledger shelf rows — books standing in ranks, tops staggered
LS_X = W / 2 - 0.33
for s in range(3):
    z = 1.15 + s * 0.55
    box(f"ledger_shelf_{s}", (LS_X, 0.8, z - 0.03), (0.42, 4.2, 0.05))
    for b in range(11):
        h = 0.34 + ((b * 5 + s * 3) % 4) * 0.03
        box(f"book_{s}_{b}", (LS_X, -1.15 + b * 0.39, z + h / 2 + 0.005),
            (0.3, 0.3, h), rot=(0, 0, math.radians(((b + s) % 3 - 1) * 2)))
# deed boxes under the lowest shelf
for i in range(4):
    box(f"deed_box_{i}", (LS_X - 0.05, -0.9 + i * 1.0, 0.3), (0.5, 0.72, 0.5))
    box(f"deed_box_lid_{i}", (LS_X - 0.05, -0.9 + i * 1.0, 0.58), (0.54, 0.76, 0.07))

# ---------------------------------------------------------------- the counter rail
# The public third: a waist-high counter rail with turned posts and a wicket gate,
# the way a bank floor divides. Money passes over the counter top.
RAIL_Y = -1.6
for i, x in enumerate((-3.4, -2.4, -1.4, 0.6, 1.6, 2.6, 3.6)):
    cyl(f"rail_post_{i}", (x, RAIL_Y, 0.55), 0.09, 1.1)
box("rail_top", (0.1, RAIL_Y, 1.12), (7.4, 0.14, 0.06))
box("counter_top", (0.1, RAIL_Y, 1.02), (7.4, 0.46, 0.07))
# solid panel fronts under the counter — after looking: bare posts rendered as
# floating lines; a bank counter is a WALL you pass money over
for px, pw in ((-3.7, 0.6), (-2.4, 2.0), (1.6, 2.0), (3.1, 1.0), (3.8, 0.4)):
    box(f"counter_panel_{px:+.1f}", (px, RAIL_Y + 0.02, 0.55), (pw, 0.08, 1.02))
# wicket gate, ajar
box("wicket", (-0.4, RAIL_Y - 0.18, 0.58), (0.9, 0.07, 1.05), rot=(0, 0, math.radians(28)))

# second clerk's flat table inside the rail, with paper stacks and a letter press
box("table2", (-2.1, 0.4, 0.74), (1.6, 0.9, 0.07))
for dx, dy in ((-0.7, -0.36), (0.7, -0.36), (-0.7, 0.36), (0.7, 0.36)):
    box(f"table2_leg_{dx:+.1f}_{dy:+.1f}", (-2.1 + dx, 0.4 + dy, 0.36), (0.07, 0.07, 0.72))
for i in range(3):
    box(f"paper_stack_{i}", (-2.5 + i * 0.42, 0.32 + (i % 2) * 0.22, 0.815 + 0.02 * (i % 2)),
        (0.34, 0.46, 0.07 + 0.04 * ((i + 1) % 2)))
box("letter_press_base", (-1.55, 0.6, 0.81), (0.3, 0.3, 0.07))
box("letter_press_top", (-1.55, 0.6, 1.0), (0.3, 0.3, 0.06))
cyl("letter_press_screw", (-1.55, 0.6, 0.92), 0.035, 0.24)
box("clerk_chair_seat", (-2.1, -0.5, 0.46), (0.48, 0.44, 0.06))
box("clerk_chair_back", (-2.1, -0.28, 0.85), (0.48, 0.06, 0.85))
for dx, dy in ((-0.19, -0.16), (0.19, -0.16), (-0.19, 0.16), (0.19, 0.16)):
    box(f"chair_leg_{dx:+.1f}_{dy:+.1f}", (-2.1 + dx, -0.5 + dy, 0.22), (0.05, 0.05, 0.44))

# chart rack on the right wall inside the rail — rolled charts leaning
box("chart_rack", (3.2, -0.4, 0.5), (0.7, 0.5, 1.0))
for i in range(4):
    cyl(f"chart_roll_{i}", (3.05 + (i % 2) * 0.26, -0.52 + (i // 2) * 0.26, 1.25),
        0.05, 1.5, rot=(math.radians(8 + i * 4), math.radians(-6 + i * 3), 0))

# ---------------------------------------------------------------- the public side
# waiting bench along the right wall, worn smooth; a satchel left on it
box("bench_seat", (3.35, -3.6, 0.44), (0.5, 2.4, 0.07))
for dy in (-1.0, 1.0):
    box(f"bench_leg_{dy:+.1f}", (3.35, -3.6 + dy, 0.2), (0.44, 0.09, 0.4))
box("bench_satchel", (3.32, -3.1, 0.56), (0.36, 0.5, 0.2), rot=(0, 0, math.radians(12)))

# small hearth on the left wall, public side — recessed firebox with a mantel
box("hearth_jamb_L", (-W / 2 + 0.18, -3.9, 0.6), (0.36, 0.22, 1.2))
box("hearth_jamb_R", (-W / 2 + 0.18, -2.9, 0.6), (0.36, 0.22, 1.2))
box("hearth_lintel", (-W / 2 + 0.18, -3.4, 1.28), (0.4, 1.24, 0.18))
box("hearth_mantel", (-W / 2 + 0.2, -3.4, 1.42), (0.5, 1.5, 0.09))
cyl("hearth_pot", (-W / 2 + 0.35, -3.4, 0.16), 0.14, 0.3)
# candle sconces on the rail posts nearest the desk
for i, x in enumerate((-1.4, 1.6)):
    box(f"sconce_{i}", (x, RAIL_Y - 0.1, 1.5), (0.09, 0.09, 0.05))
    cyl(f"sconce_candle_{i}", (x, RAIL_Y - 0.1, 1.58), 0.02, 0.12)

# door in the front-left, ajar — where the queue will come from
box("door_leaf", (-3.1, -D / 2 + 0.25, 1.05), (1.0, 0.08, 2.1), rot=(0, 0, math.radians(-38)))
box("door_frame_L", (-3.7, -D / 2 + 0.06, 1.05), (0.12, 0.12, 2.1))
box("door_frame_R", (-2.5, -D / 2 + 0.06, 1.05), (0.12, 0.12, 2.1))
box("door_lintel2", (-3.1, -D / 2 + 0.06, 2.16), (1.34, 0.12, 0.12))

# ---------------------------------------------------------------- wall dressing
# After looking: the back wall was bare either side of the window. The §1 look
# statement runs "under a running clock" — so the clock hangs where every clerk
# sees it, with the tariff boards opposite.
cyl("clock_face", (2.6, D / 2 - 0.18, 2.75), 0.35, 0.14, rot=(math.radians(90), 0, 0))
box("clock_case", (2.6, D / 2 - 0.14, 2.1), (0.34, 0.2, 0.95))
box("notice_board_a", (-2.5, D / 2 - 0.12, 2.5), (1.1, 0.1, 0.85))
box("notice_board_b", (-3.3, D / 2 - 0.12, 2.35), (0.6, 0.1, 0.5))
box("tide_board", (-2.0, D / 2 - 0.12, 1.7), (0.8, 0.1, 0.5), rot=(0, math.radians(2), 0))
# chart shelf right of the window with rolled charts
box("chart_shelf", (3.3, D / 2 - 0.3, 2.9), (1.3, 0.4, 0.06))
for i in range(4):
    cyl(f"chart_shelf_roll_{i}", (2.85 + i * 0.3, D / 2 - 0.3, 3.02), 0.07, 0.9,
        rot=(0, math.radians(90), math.radians(4 * (i % 2))))
# public-side props: a coat rack by the door, a strapped trunk, a barrel rolled in
cyl("coat_rack_post", (-2.6, -3.9, 0.9), 0.05, 1.8)
for i, ang in enumerate((0, 60, 120)):
    box(f"coat_rack_arm_{i}", (-2.6 + 0.18 * math.cos(math.radians(ang)),
                               -3.9 + 0.18 * math.sin(math.radians(ang)), 1.72),
        (0.4, 0.05, 0.05), rot=(0, 0, math.radians(ang)))
box("hung_cloak", (-2.75, -3.8, 1.25), (0.3, 0.22, 0.9))
box("trunk", (2.2, -4.2, 0.36), (1.0, 0.6, 0.6), rot=(0, 0, math.radians(-16)))
for si, sx in enumerate((-0.18, 0.2)):
    box(f"trunk_strap_{si}", (2.2 + sx, -4.2 - sx * 0.3, 0.36), (0.08, 0.64, 0.64),
        rot=(0, 0, math.radians(-16)))
cyl("public_barrel", (-1.3, -4.55, 0.4), 0.34, 0.78)

# ---------------------------------------------------------------- camera
# FIXED near-ortho telephoto, looking down the axis toward the water window.
# Interior rule from bonded_warehouse_module.py: pure ortho collapses an interior;
# a 58mm lens set back is the correct reading. Saved into module.blend.
cam_data = bpy.data.cameras.new("module_cam")
cam_data.type = "PERSP"
cam_data.lens = 58.0
cam = bpy.data.objects.new("module_cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -8.9, 1.95)
cam.rotation_euler = (math.radians(88.0), 0, 0)  # a touch down, to open the floor
scene.camera = cam

# ---------------------------------------------------------------- render setup
scene.render.resolution_x = args.width
scene.render.resolution_y = args.height
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False

# Workbench for the clay pass: flat, fast, no lighting model to fight the LoRA later.
scene.render.engine = "BLENDER_WORKBENCH"
shading = scene.display.shading
shading.light = "STUDIO"
shading.color_type = "SINGLE"
shading.single_color = (0.62, 0.60, 0.56)
shading.show_cavity = True
shading.background_type = "VIEWPORT"
shading.background_color = (0.88, 0.87, 0.84)
scene.render.filepath = os.path.join(args.out, "module_clay")
bpy.ops.render.render(write_still=True)

# Depth via a camera-distance emission shader (survives Blender 5 compositor drift).
# Near = bright, matching what ControlNet depth preprocessors emit.
_engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in _engines else "BLENDER_EEVEE"
NEAR, FAR = 2.4, 16.0
mat = bpy.data.materials.new("module_depth")
mat.use_nodes = True
mnt = mat.node_tree
for n in list(mnt.nodes):
    mnt.nodes.remove(n)
cam_node = mnt.nodes.new("ShaderNodeCameraData")
rng = mnt.nodes.new("ShaderNodeMapRange")
rng.inputs["From Min"].default_value = NEAR
rng.inputs["From Max"].default_value = FAR
rng.inputs["To Min"].default_value = 1.0     # near = white
rng.inputs["To Max"].default_value = 0.0     # far  = black
rng.clamp = True
emit = mnt.nodes.new("ShaderNodeEmission")
mout = mnt.nodes.new("ShaderNodeOutputMaterial")
mnt.links.new(cam_node.outputs["View Z Depth"], rng.inputs["Value"])
mnt.links.new(rng.outputs[0], emit.inputs["Color"])
mnt.links.new(emit.outputs[0], mout.inputs["Surface"])

for ob in scene.objects:
    if ob.type == "MESH":
        ob.data.materials.clear()
        ob.data.materials.append(mat)

world = bpy.data.worlds.new("black")
world.use_nodes = False
world.color = (0, 0, 0)
scene.world = world
scene.view_settings.view_transform = "Standard"   # no filmic curve on a depth map
scene.render.filepath = os.path.join(args.out, "module_depth")
bpy.ops.render.render(write_still=True)

# Stretch the depth map to the FULL 0-1 range — a compressed map silently weakens
# effective control strength (see bonded_warehouse_module.py).
import numpy as _np
_img = bpy.data.images.load(os.path.join(args.out, "module_depth.png"))
_px = _np.array(_img.pixels[:], dtype=_np.float32).reshape(-1, 4)
_lo, _hi = float(_px[:, :3].min()), float(_px[:, :3].max())
if _hi - _lo > 1e-6:
    _px[:, :3] = (_px[:, :3] - _lo) / (_hi - _lo)
    _img.pixels = _px.ravel().tolist()
    _img.file_format = "PNG"
    _img.save()
print(f"[module] depth normalised {_lo:.3f}-{_hi:.3f} -> 0-1 full range")

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, "module.blend"))
print(f"[module] wrote clay + depth + module.blend to {args.out}")
print(f"[module] objects: {len(bpy.data.objects)}")
