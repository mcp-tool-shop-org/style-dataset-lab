"""Salt Road — weighing floor interior module, authored as blocky proxy geometry.

Contract §7: "Six brass beam-scales, only the third one trusted; a queue that forms
before the doors open." The §5 negative bans people, so the queue is authored as its
TRACES: a roped stanchion lane running from the closed double doors to the third
scale, and discrete waiting lots of cargo — a sack pile, two casks, a crate stack —
spaced down the lane like parties holding their place. The third scale is trusted, so
the third scale is where the stuff accumulates: the official weight pyramid, the assay
master's high desk, the tally board, the lantern.

Same recipe as bonded_warehouse_module.py — crude boxes and cylinders, density carried
by authored STUFF.

Run:
  blender.exe -b -P weighing_floor_module.py -- --out <dir>

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
    o.scale = Vector(size) / 2.0
    return o


def cyl(name, loc, r, depth, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc,
                                        rotation=rot, vertices=16)
    o = bpy.context.object
    o.name = name
    return o


# ---------------------------------------------------------------- the shell
# A public weighing hall seen down its axis. Camera looks along +Y from -Y.
W, D, H = 10.0, 15.0, 5.5
box("floor", (0, 0, -0.1), (W, D, 0.2))
box("ceiling", (0, 0, H), (W, D, 0.2))
box("wall_L", (-W / 2, 0, H / 2), (0.2, D, H))
box("wall_R", (W / 2, 0, H / 2), (0.2, D, H))
box("wall_back", (0, D / 2, H / 2), (W, 0.2, H))

# roof: tie beams + king posts + a ridge beam. (Angled rafters at this camera
# height rendered as diagonal slabs crowding the frame top — dropped after looking.)
for i in range(8):
    y = -D / 2 + 1.2 + i * 1.85
    box(f"tie_beam_{i}", (0, y, H - 0.6), (W, 0.3, 0.36))
    box(f"king_post_{i}", (0, y, H - 0.28), (0.22, 0.22, 0.55))
box("ridge_beam", (0, 0, H - 0.08), (0.26, D, 0.26))

# posts down both sides
for i in range(6):
    y = -D / 2 + 1.8 + i * 2.4
    for sx in (-1, 1):
        box(f"post_{'L' if sx < 0 else 'R'}_{i}", (sx * (W / 2 - 0.9), y, H / 2), (0.36, 0.36, H))

# high windows on the right wall — morning light across the scale row
for i, y in enumerate((-4.8, -1.6, 1.6, 4.8)):
    box(f"window_R_{i}", (W / 2 - 0.05, y, 4.1), (0.16, 1.1, 1.0))
# one high window on the back wall over the registry
box("window_back", (2.6, D / 2 - 0.05, 4.2), (1.2, 0.16, 1.0))

# ---------------------------------------------------------------- six beam-scales
# A row of scale gantries down the RIGHT side of the hall, receding toward the back.
# Each: two posts + crossbeam + hanger + beam + chains + pans + a low platform.
SCALE_X = 2.5
# Row compressed + pushed back after looking: with the first scale 5.5 m from the
# camera its gantry filled the right third of the frame and the row never read as SIX.
scale_ys = [-3.8, -2.1, -0.4, 1.3, 3.0, 4.7]
for i, y in enumerate(scale_ys):
    n = i + 1
    for sx in (-1.0, 1.0):
        box(f"gantry_post_{n}_{'a' if sx < 0 else 'b'}",
            (SCALE_X + sx * 1.1, y, 1.8), (0.26, 0.26, 3.6))
    box(f"gantry_beam_{n}", (SCALE_X, y, 3.62), (2.6, 0.28, 0.3))
    box(f"gantry_brace_a_{n}", (SCALE_X - 0.85, y, 3.28), (0.8, 0.18, 0.18), rot=(0, math.radians(38), 0))
    box(f"gantry_brace_b_{n}", (SCALE_X + 0.85, y, 3.28), (0.8, 0.18, 0.18), rot=(0, math.radians(-38), 0))
    box(f"scale_hanger_{n}", (SCALE_X, y, 3.28), (0.07, 0.07, 0.5))
    box(f"scale_beam_{n}", (SCALE_X, y, 3.05), (1.9, 0.1, 0.12))
    for sx in (-0.82, 0.82):
        box(f"scale_chain_{n}_{'a' if sx < 0 else 'b'}",
            (SCALE_X + sx, y, 2.4), (0.09, 0.09, 1.3))
        cyl(f"scale_pan_{n}_{'a' if sx < 0 else 'b'}",
            (SCALE_X + sx, y, 1.7), 0.45, 0.14)
    box(f"scale_platform_{n}", (SCALE_X, y, 0.07), (2.9, 1.5, 0.14))

# THE THIRD SCALE IS THE TRUSTED ONE — everything official accumulates at it.
Y3 = scale_ys[2]
# a load actually ON its pans: sacks one side, weight stack the other
box("third_load_sack_a", (SCALE_X - 0.82, Y3, 1.95), (0.6, 0.5, 0.3))
box("third_load_sack_b", (SCALE_X - 0.82, Y3 + 0.1, 2.22), (0.5, 0.42, 0.24))
for i in range(3):
    cyl(f"third_pan_weight_{i}", (SCALE_X + 0.82, Y3 + (i - 1) * 0.2, 1.85), 0.11 - i * 0.02, 0.14)
# the official weight pyramid on a stone base beside it
box("weight_base", (SCALE_X + 1.7, Y3 - 0.75, 0.12), (1.0, 1.0, 0.24))
for tier in range(4):
    r0 = 0.3 - tier * 0.062
    for k in range(max(1, 4 - tier)):
        ang = k * (2 * math.pi / max(1, 4 - tier))
        cyl(f"weight_t{tier}_{k}",
            (SCALE_X + 1.7 + math.cos(ang) * (0.28 - tier * 0.07),
             Y3 - 0.75 + math.sin(ang) * (0.28 - tier * 0.07),
             0.35 + tier * 0.24), r0, 0.22)
# assay master's high desk + stool + tally board on the gantry post
box("assay_desk_body", (SCALE_X + 1.75, Y3 + 0.75, 0.72), (0.85, 0.6, 1.0))
box("assay_desk_slope", (SCALE_X + 1.75, Y3 + 0.78, 1.28), (0.85, 0.66, 0.08), rot=(math.radians(-13), 0, 0))
box("assay_stool_seat", (SCALE_X + 1.75, Y3 + 1.45, 0.68), (0.42, 0.42, 0.06))
for dx, dy in ((-0.16, -0.16), (0.16, -0.16), (-0.16, 0.16), (0.16, 0.16)):
    box(f"assay_stool_leg_{dx:+.2f}_{dy:+.2f}",
        (SCALE_X + 1.75 + dx, Y3 + 1.45 + dy, 0.33), (0.05, 0.05, 0.66))
box("tally_board_3", (SCALE_X - 1.24, Y3, 2.9), (0.06, 0.7, 0.9))
# lantern hung over the trusted scale
box("lantern_arm", (SCALE_X, Y3, 4.06), (0.06, 0.06, 0.6))
box("lantern_3", (SCALE_X, Y3, 3.86), (0.22, 0.22, 0.3))

# a dust sheet draped over the SIXTH scale's pans (furthest, least trusted — a lump)
box("dust_sheet_6", (SCALE_X, scale_ys[5], 2.3), (1.9, 1.1, 0.55), rot=(0, 0, math.radians(4)))

# ---------------------------------------------------------------- the queue lane
# Closed double doors on the LEFT wall near the front; the roped stanchion lane runs
# from the doors diagonally to the third scale. The doors have not opened yet.
# Closed double doors in the BACK wall, left of centre — the queue faces them and
# they have not opened yet. (Moved from the left wall after looking: at this camera
# a left-wall door is out of frame, and a door nobody can see cannot be waited on.)
DOOR_X = -2.2
box("door_leaf_a", (DOOR_X - 0.78, D / 2 - 0.14, 1.6), (1.5, 0.16, 3.2))
box("door_leaf_b", (DOOR_X + 0.78, D / 2 - 0.14, 1.6), (1.5, 0.16, 3.2))
box("door_frame_top", (DOOR_X, D / 2 - 0.16, 3.36), (3.5, 0.24, 0.32))
for dxx in (-1.7, 1.7):
    box(f"door_frame_{dxx:+.1f}", (DOOR_X + dxx, D / 2 - 0.16, 1.65), (0.26, 0.24, 3.3))
for leaf_dx in (-0.78, 0.78):  # strap hinges
    for hz in (0.75, 1.7, 2.65):
        box(f"hinge_{leaf_dx:+.2f}_{hz:.2f}", (DOOR_X + leaf_dx, D / 2 - 0.24, hz), (0.95, 0.06, 0.13))
box("door_bar", (DOOR_X, D / 2 - 0.3, 1.55), (3.1, 0.14, 0.22))  # barred: not open yet
box("wicket_door", (DOOR_X + 0.78, D / 2 - 0.22, 1.02), (0.72, 0.18, 1.95))

# stanchion + sagging rope lane: door -> third scale, a gentle dogleg
lane = [(-2.2, 6.0), (-1.6, 4.7), (-1.05, 3.4), (-0.6, 2.1), (-0.3, 0.9),
        (0.1, -0.15), (0.8, -0.3)]
for i, (x, y) in enumerate(lane):
    cyl(f"stanchion_{i}", (x, y, 0.5), 0.07, 1.0)
    cyl(f"stanchion_foot_{i}", (x, y, 0.05), 0.18, 0.1)
for i in range(len(lane) - 1):
    (x0, y0), (x1, y1) = lane[i], lane[i + 1]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    span = math.hypot(x1 - x0, y1 - y0)
    yaw = math.atan2(y1 - y0, x1 - x0)
    # two sagging half-spans per gap
    for half, hx, hy in ((0, (x0 + mx) / 2, (y0 + my) / 2), (1, (mx + x1) / 2, (my + y1) / 2)):
        cyl(f"rope_{i}_{half}", (hx, hy, 0.86 - 0.06), 0.03, span / 2 + 0.05,
            rot=(0, math.radians(90 + (8 if half == 0 else -8)), yaw))

# waiting lots spaced down the lane — cargo holding its party's place
box("lot1_sack_a", (-3.1, 5.6, 0.24), (0.9, 0.7, 0.48))
box("lot1_sack_b", (-3.0, 5.7, 0.6), (0.7, 0.55, 0.3))
for i, (cx, cy) in enumerate(((-2.5, 4.3), (-2.1, 3.95))):
    cyl(f"lot2_cask_{i}", (cx, cy, 0.42), 0.36, 0.8)
box("lot3_crate_a", (-1.7, 2.9, 0.3), (0.66, 0.66, 0.6))
box("lot3_crate_b", (-1.7, 2.9, 0.85), (0.55, 0.55, 0.5), rot=(0, 0, math.radians(14)))
box("lot4_bale", (-1.3, 1.6, 0.34), (0.95, 0.6, 0.68))
cyl("lot5_cask", (-0.9, 0.45, 0.42), 0.36, 0.8, rot=(0, math.radians(90), math.radians(20)))
cyl("lot6_cask_next", (0.2, -0.7, 0.42), 0.36, 0.8)   # first in line, next on the pans

# long waiting bench along the left wall past the doors, worn smooth
box("bench_seat", (-W / 2 + 0.5, 1.4, 0.42), (0.5, 3.2, 0.08))
for dy in (-1.3, 0.0, 1.3):
    box(f"bench_leg_{dy:+.1f}", (-W / 2 + 0.5, 1.4 + dy, 0.19), (0.44, 0.1, 0.38))

# ---------------------------------------------------------------- the far end
# registry table under the back window, with the great ledger and the seal
box("registry_table", (2.2, D / 2 - 0.9, 0.8), (2.2, 0.8, 0.09))
for dx, dy in ((-0.95, -0.3), (0.95, -0.3), (-0.95, 0.3), (0.95, 0.3)):
    box(f"registry_leg_{dx:+.1f}_{dy:+.1f}", (2.2 + dx, D / 2 - 0.9 + dy, 0.38), (0.08, 0.08, 0.76))
box("registry_ledger", (2.0, D / 2 - 0.95, 0.9), (0.6, 0.42, 0.1), rot=(0, 0, math.radians(-6)))
cyl("registry_seal", (2.9, D / 2 - 0.85, 0.94), 0.06, 0.16)
box("registry_stool", (2.2, D / 2 - 1.6, 0.55), (0.45, 0.45, 0.06))

# the weight cupboard — doors open, spare weight rows on shelves
# the weight cupboard — on the LEFT wall now (the back wall belongs to the doors);
# doors open into the room, spare weight rows on shelves
CB_Y = 4.6
box("cupboard_body", (-W / 2 + 0.42, CB_Y, 1.1), (0.6, 1.6, 2.2))
box("cupboard_door_a", (-W / 2 + 0.75, CB_Y - 1.15, 1.1), (0.75, 0.06, 2.1), rot=(0, 0, math.radians(55)))
box("cupboard_door_b", (-W / 2 + 0.75, CB_Y + 1.15, 1.1), (0.75, 0.06, 2.1), rot=(0, 0, math.radians(-55)))
for s in range(3):
    box(f"cupboard_shelf_{s}", (-W / 2 + 0.47, CB_Y, 0.62 + s * 0.6), (0.5, 1.5, 0.05))
    for k in range(4):
        cyl(f"cupboard_weight_{s}_{k}", (-W / 2 + 0.47, CB_Y - 0.55 + k * 0.37, 0.78 + s * 0.6),
            0.11 - s * 0.02, 0.24 - s * 0.04)

# the great tariff board + the spare-beam wall rack between the doors and the
# registry (the back wall was bare there after the door move)
box("tariff_board", (0.1, D / 2 - 0.12, 2.9), (1.7, 0.12, 1.3))
box("tariff_ledge", (0.1, D / 2 - 0.2, 2.2), (1.8, 0.24, 0.08))
for i in range(2):
    box(f"spare_beam_wall_{i}", (0.1, D / 2 - 0.3, 1.5 + i * 0.28), (3.4, 0.12, 0.12))
for i in range(3):
    box(f"beam_rack_bracket_{i}", (-1.3 + i * 1.4, D / 2 - 0.22, 1.42), (0.14, 0.3, 0.14))
# spare pans hung on the left wall over the bench
for i in range(3):
    cyl(f"spare_pan_{i}", (-W / 2 + 0.32, 0.5 + i * 0.9, 2.3), 0.42, 0.1,
        rot=(0, math.radians(90), 0))

# spare beams leaning in the far right corner (scales awaiting repair — not trusted)
for i in range(3):
    box(f"spare_beam_{i}", (W / 2 - 0.7 - i * 0.25, D / 2 - 1.1, 1.25),
        (0.12, 0.12, 2.5), rot=(math.radians(-14 + i * 4), 0, math.radians(6 - i * 5)))

# a floor drain channel down the middle of the hall (weigh-houses hosed clean)
box("drain_channel", (-0.6, 0.55, -0.02), (0.3, D - 2.4, 0.06))

# ---------------------------------------------------------------- camera
# FIXED near-ortho telephoto, looking down the axis (interior rule — see
# bonded_warehouse_module.py: pure ortho collapses an interior).
cam_data = bpy.data.cameras.new("module_cam")
cam_data.type = "PERSP"
cam_data.lens = 58.0
cam = bpy.data.objects.new("module_cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -10.9, 2.5)
cam.rotation_euler = (math.radians(87.5), 0, 0)
scene.camera = cam

# ---------------------------------------------------------------- render setup
scene.render.resolution_x = args.width
scene.render.resolution_y = args.height
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False

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

_engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in _engines else "BLENDER_EEVEE"
NEAR, FAR = 3.0, 20.0
mat = bpy.data.materials.new("module_depth")
mat.use_nodes = True
mnt = mat.node_tree
for n in list(mnt.nodes):
    mnt.nodes.remove(n)
cam_node = mnt.nodes.new("ShaderNodeCameraData")
rng = mnt.nodes.new("ShaderNodeMapRange")
rng.inputs["From Min"].default_value = NEAR
rng.inputs["From Max"].default_value = FAR
rng.inputs["To Min"].default_value = 1.0
rng.inputs["To Max"].default_value = 0.0
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
scene.view_settings.view_transform = "Standard"
scene.render.filepath = os.path.join(args.out, "module_depth")
bpy.ops.render.render(write_still=True)

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
