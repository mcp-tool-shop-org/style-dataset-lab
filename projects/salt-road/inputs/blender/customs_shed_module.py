"""Salt Road — customs shed interior module, authored as blocky proxy geometry.

Contract §7: "The stamp, the tally, the marks on every cask." Law 4: the marks are
graphic design and they are PAINT — what the module supplies is the flow of goods the
marks certify: the jumbled unexamined queue inside the in-door, the examination counter
where one crate stands open, the customs desk with the stamp, the tally sticks and the
seal press, the neat sealed ranks beyond it, and the bonded cage in the corner for what
failed. The out-door in the back wall is a real APERTURE swung open, so the depth pass
reads daylight-to-the-quay through it.

Same recipe as bonded_warehouse_module.py — crude boxes and cylinders, density carried
by authored STUFF.

Run:
  blender.exe -b -P customs_shed_module.py -- --out <dir>

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
    o.scale = Vector(size)
    return o


def cyl(name, loc, r, depth, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc,
                                        rotation=rot, vertices=16)
    o = bpy.context.object
    o.name = name
    return o


# ---------------------------------------------------------------- the shell
# A working shed seen down its axis. Camera looks along +Y from -Y.
W, D, H = 9.0, 13.0, 4.6
box("floor", (0, 0, -0.1), (W, D, 0.2))
box("ceiling", (0, 0, H), (W, D, 0.2))
box("wall_L", (-W / 2, 0, H / 2), (0.2, D, H))
box("wall_R", (W / 2, 0, H / 2), (0.2, D, H))

# back wall with the OUT-DOOR aperture, doors swung open to the quay daylight
AP_X, AP_W, AP_H = 1.8, 2.4, 2.7
box("wall_back_L", (-(W / 2 - (AP_X - AP_W / 2)) / 2 + -W / 2 * 0 + (-W / 2 + (AP_X - AP_W / 2 + W / 2) / 2), D / 2, H / 2),
    (AP_X - AP_W / 2 + W / 2, 0.2, H))
bpy.data.objects["wall_back_L"].location.x = (-W / 2 + (AP_X - AP_W / 2)) / 2
box("wall_back_R", ((AP_X + AP_W / 2 + W / 2) / 2, D / 2, H / 2), (W / 2 - (AP_X + AP_W / 2), 0.2, H))
box("wall_back_above", (AP_X, D / 2, (H + AP_H) / 2), (AP_W, 0.2, H - AP_H))
# door leaves swung open into the shed
box("outdoor_leaf_a", (AP_X - AP_W / 2 - 0.35, D / 2 - 0.55, AP_H / 2), (0.1, 1.2, AP_H - 0.1), rot=(0, 0, math.radians(58)))
box("outdoor_leaf_b", (AP_X + AP_W / 2 + 0.35, D / 2 - 0.55, AP_H / 2), (0.1, 1.2, AP_H - 0.1), rot=(0, 0, math.radians(-58)))
box("outdoor_lintel", (AP_X, D / 2 + 0.02, AP_H + 0.14), (AP_W + 0.5, 0.3, 0.3))

# roof trusses
for i in range(7):
    y = -D / 2 + 1.1 + i * 1.8
    box(f"tie_beam_{i}", (0, y, H - 0.5), (W, 0.28, 0.32))
    box(f"rafter_L_{i}", (-W / 4, y, H - 0.05), (W / 2, 0.2, 0.2), rot=(0, math.radians(17), 0))
    box(f"rafter_R_{i}", (W / 4, y, H - 0.05), (W / 2, 0.2, 0.2), rot=(0, math.radians(-17), 0))

# posts down both sides, tally boards hung on three of them
for i in range(5):
    y = -D / 2 + 1.5 + i * 2.5
    for sx in (-1, 1):
        box(f"post_{'L' if sx < 0 else 'R'}_{i}", (sx * (W / 2 - 0.85), y, H / 2), (0.32, 0.32, H))
for i, y in enumerate((-3.5, -1.0, 1.5)):
    box(f"tally_board_{i}", (-(W / 2 - 0.66), y, 2.2), (0.07, 0.85, 1.1))

# high windows on the left wall
for i, y in enumerate((-4.2, -0.9, 2.4)):
    box(f"window_L_{i}", (-W / 2 + 0.05, y, 3.6), (0.16, 1.0, 0.85))

# ---------------------------------------------------------------- the in-door
# Left wall near the front — where goods enter. One leaf still swung inward.
box("indoor_leaf", (-W / 2 + 0.55, -4.6, 1.35), (0.1, 1.3, 2.6), rot=(0, 0, math.radians(-42)))
box("indoor_frame_a", (-W / 2 + 0.12, -5.45, 1.4), (0.2, 0.2, 2.8))
box("indoor_frame_b", (-W / 2 + 0.12, -3.75, 1.4), (0.2, 0.2, 2.8))
box("indoor_lintel", (-W / 2 + 0.12, -4.6, 2.86), (0.2, 1.9, 0.22))

# ---------------------------------------------------------------- unexamined side
# The jumble inside the in-door: casks on end, crates askew, bales — waiting for the
# stamp, nothing aligned yet.
for i, (cx, cy, yaw) in enumerate(((-3.2, -4.4, 0), (-2.4, -4.7, 0), (-2.8, -3.7, 0),
                                   (-3.4, -2.9, 0), (-2.2, -2.7, 0))):
    cyl(f"unex_cask_{i}", (cx, cy, 0.42), 0.37, 0.84, rot=(0, 0, math.radians(yaw)))
cyl("unex_cask_tipped", (-1.6, -3.4, 0.38), 0.37, 0.84, rot=(0, math.radians(90), math.radians(35)))
for i, (kx, ky, yaw) in enumerate(((-3.5, -1.7, 12), (-2.5, -1.5, -18), (-3.0, -0.8, 30))):
    box(f"unex_crate_{i}", (kx, ky, 0.34), (0.7, 0.7, 0.68), rot=(0, 0, math.radians(yaw)))
box("unex_crate_high", (-2.9, -1.3, 1.02), (0.6, 0.6, 0.58), rot=(0, 0, math.radians(-8)))
for i, (bx, by) in enumerate(((-1.6, -2.0), (-1.9, -1.1))):
    box(f"unex_bale_{i}", (bx, by, 0.36), (1.0, 0.62, 0.7), rot=(0, 0, math.radians(i * 22 - 10)))
box("unex_sack_a", (-1.2, -4.3, 0.26), (0.8, 0.6, 0.5))
box("unex_sack_b", (-1.1, -4.2, 0.62), (0.65, 0.5, 0.26))

# ---------------------------------------------------------------- the counter
# The examination counter down the middle: heavy trestle table, one crate OPEN with
# its lid off and a pry bar across it, sacking pulled back.
box("counter_top", (0.4, -0.9, 0.92), (1.4, 4.6, 0.12))
for dy in (-2.0, 0.0, 2.0):
    box(f"counter_trestle_a_{dy:+.1f}", (0.0, -0.9 + dy, 0.45), (0.12, 0.5, 0.9), rot=(0, math.radians(14), 0))
    box(f"counter_trestle_b_{dy:+.1f}", (0.8, -0.9 + dy, 0.45), (0.12, 0.5, 0.9), rot=(0, math.radians(-14), 0))
box("open_crate", (0.4, -2.2, 1.28), (0.72, 0.72, 0.6))
box("open_crate_lid", (1.15, -2.5, 1.02), (0.72, 0.72, 0.07), rot=(0, math.radians(24), math.radians(30)))
box("pry_bar", (0.35, -2.1, 1.62), (0.06, 0.9, 0.06), rot=(0, 0, math.radians(28)))
box("sacking_fold", (0.4, -1.5, 1.06), (0.9, 0.7, 0.16), rot=(0, 0, math.radians(-8)))
cyl("counter_cask", (0.4, 0.4, 1.4), 0.36, 0.8)     # next cask up, standing on the counter
box("counter_scale_post", (0.4, 1.6, 1.5), (0.06, 0.06, 1.0))
box("counter_scale_arm", (0.4, 1.6, 1.98), (0.7, 0.05, 0.05))
for sy in (-0.3, 0.3):
    cyl(f"counter_scale_pan_{sy:+.1f}", (0.4, 1.6 + sy, 1.78), 0.16, 0.04)

# ---------------------------------------------------------------- the desk
# The customs desk against the right wall mid-hall: THE STAMP, the tally sticks, the
# seal press, the ledger, the wax brazier — the machinery of certification.
box("customs_desk", (3.0, -0.4, 0.82), (1.6, 0.95, 0.1))
for dx, dy in ((-0.7, -0.4), (0.7, -0.4), (-0.7, 0.4), (0.7, 0.4)):
    box(f"desk_leg_{dx:+.1f}_{dy:+.1f}", (3.0 + dx, -0.4 + dy, 0.39), (0.09, 0.09, 0.78))
box("desk_ledger", (2.7, -0.55, 0.94), (0.55, 0.4, 0.09), rot=(0, 0, math.radians(8)))
cyl("the_stamp_handle", (3.35, -0.6, 1.04), 0.03, 0.16)
cyl("the_stamp_head", (3.35, -0.6, 0.92), 0.07, 0.08)
box("seal_press_base", (3.6, -0.15, 0.9), (0.3, 0.3, 0.08))
box("seal_press_frame", (3.6, -0.15, 1.12), (0.24, 0.1, 0.36))
cyl("seal_press_screw", (3.6, -0.15, 1.3), 0.035, 0.2)
box("tally_bundle", (2.85, -0.1, 0.9), (0.3, 0.14, 0.1), rot=(0, 0, math.radians(-14)))
for i in range(5):  # loose tally sticks fanned beside the bundle
    box(f"tally_stick_{i}", (3.05 + i * 0.045, 0.12, 0.88), (0.035, 0.34, 0.03),
        rot=(0, 0, math.radians(-20 + i * 9)))
cyl("wax_brazier", (3.7, -0.75, 0.98), 0.11, 0.16)
cyl("wax_stick", (3.52, -0.82, 0.92), 0.02, 0.18, rot=(0, math.radians(70), 0))
box("desk_stool", (3.0, -1.35, 0.55), (0.45, 0.45, 0.06))
for dx, dy in ((-0.17, -0.17), (0.17, -0.17), (-0.17, 0.17), (0.17, 0.17)):
    box(f"stool_leg_{dx:+.2f}_{dy:+.2f}", (3.0 + dx, -1.35 + dy, 0.26), (0.05, 0.05, 0.52))
# lantern over the desk from the nearest post
box("desk_lantern_arm", (3.6, -0.4, 3.0), (0.7, 0.06, 0.06))
box("desk_lantern", (3.3, -0.4, 2.78), (0.2, 0.2, 0.3))

# ---------------------------------------------------------------- the rail + gate
# Barrier rail across the hall between counter and sealed side; goods pass the gate
# only stamped. A gap at the counter's end is the gate, standing open.
RAIL_Y = 1.9
for i, x in enumerate((-3.7, -2.5, -1.3, 1.7, 2.9, 4.0)):
    cyl(f"rail_post_{i}", (x, RAIL_Y, 0.5), 0.06, 1.0)
box("rail_top_a", (-2.5, RAIL_Y, 1.03), (2.6, 0.12, 0.07))
box("rail_top_b", (2.85, RAIL_Y, 1.03), (2.5, 0.12, 0.07))
box("rail_mid_a", (-2.5, RAIL_Y, 0.55), (2.6, 0.07, 0.06))
box("rail_mid_b", (2.85, RAIL_Y, 0.55), (2.5, 0.07, 0.06))
box("gate_leaf", (0.15, RAIL_Y + 0.4, 0.55), (1.1, 0.07, 0.95), rot=(0, 0, math.radians(52)))

# ---------------------------------------------------------------- sealed side
# Beyond the rail: neat ranks — casks on end in rows, crates squared, bales aligned.
# Order is what a stamp buys.
for r in range(3):
    for c in range(4):
        cyl(f"sealed_cask_{r}_{c}", (-3.3 + c * 0.85, 2.9 + r * 0.95, 0.42), 0.37, 0.84)
for r in range(2):
    for c in range(3):
        box(f"sealed_crate_{r}_{c}", (0.4 + c * 0.8, 3.1 + r * 0.9, 0.36), (0.68, 0.68, 0.7))
box("sealed_crate_top", (1.2, 3.55, 1.06), (0.68, 0.68, 0.66))
for i in range(3):
    box(f"sealed_bale_{i}", (3.2, 2.7 + i * 0.8, 0.4), (1.05, 0.68, 0.78))

# the bonded cage in the far right corner — lattice of flat bars, a lock plate,
# two seized casks inside
CAGE_X, CAGE_Y = 3.55, 5.3
for i in range(6):
    box(f"cage_bar_v_{i}", (CAGE_X - 1.25 + i * 0.5, CAGE_Y - 1.1, 1.25), (0.06, 0.06, 2.5))
for i in range(6):
    box(f"cage_bar_side_{i}", (CAGE_X - 1.45, CAGE_Y - 0.9 + i * 0.36, 1.25), (0.06, 0.06, 2.5))
for zz in (0.7, 1.5, 2.3):
    box(f"cage_rail_front_{zz:.1f}", (CAGE_X, CAGE_Y - 1.1, zz), (2.6, 0.07, 0.09))
    box(f"cage_rail_side_{zz:.1f}", (CAGE_X - 1.45, CAGE_Y, zz), (0.07, 2.4, 0.09))
box("cage_lockplate", (CAGE_X - 0.4, CAGE_Y - 1.14, 1.1), (0.3, 0.08, 0.4))
cyl("seized_cask_a", (CAGE_X - 0.4, CAGE_Y + 0.3, 0.42), 0.37, 0.84)
cyl("seized_cask_b", (CAGE_X + 0.5, CAGE_Y + 0.1, 0.42), 0.37, 0.84)

# back-wall dressing left of the out-door — after looking, that half was bare:
# the tariff board, a hanging steelyard, a shelf of small chests, one high window
box("tariff_board_cs", (-2.2, D / 2 - 0.12, 2.6), (1.5, 0.12, 1.1))
box("steelyard_arm", (-0.6, D / 2 - 0.25, 2.5), (1.1, 0.06, 0.06))
box("steelyard_weight", (-1.0, D / 2 - 0.25, 2.25), (0.14, 0.14, 0.3))
cyl("steelyard_hook", (-0.2, D / 2 - 0.25, 2.3), 0.04, 0.35)
box("back_shelf", (-3.6, D / 2 - 0.3, 1.6), (1.4, 0.4, 0.06))
for i in range(3):
    box(f"shelf_chest_{i}", (-4.05 + i * 0.46, D / 2 - 0.3, 1.8), (0.38, 0.34, 0.3))
box("window_back_cs", (-2.2, D / 2 - 0.05, 3.7), (1.0, 0.16, 0.8))

# handcart parked by the out-door, empty, shafts down
box("cart_bed", (1.7, 4.6, 0.6), (0.95, 1.5, 0.1), rot=(0, 0, math.radians(12)))
for s in (-1, 1):
    cyl(f"cart_wheel_{s}", (1.7 + s * 0.55, 4.75, 0.4), 0.4, 0.1, rot=(0, math.radians(90), math.radians(12)))
box("cart_shaft_a", (1.35, 3.75, 0.3), (0.07, 1.2, 0.07), rot=(math.radians(-24), 0, math.radians(12)))
box("cart_shaft_b", (1.95, 3.9, 0.3), (0.07, 1.2, 0.07), rot=(math.radians(-24), 0, math.radians(12)))

# ---------------------------------------------------------------- camera
# FIXED near-ortho telephoto, looking down the axis toward the open out-door
# (interior rule — see bonded_warehouse_module.py: pure ortho collapses an interior).
cam_data = bpy.data.cameras.new("module_cam")
cam_data.type = "PERSP"
cam_data.lens = 58.0
cam = bpy.data.objects.new("module_cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -9.9, 2.3)
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
NEAR, FAR = 2.6, 18.5
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
