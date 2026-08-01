"""Salt Road — crooked stair EXTERIOR module, authored as blocky proxy geometry.

Contract §7: "Twenty-two steps, not one the same height as the last." So there are
exactly twenty-two, and a seeded jitter gives every riser its own height, every tread
its own depth, and the whole run a drift and a dogleg — crooked by construction, not
by prompt. The flanking buildings are the Director-admitted half-timber ruling
(2026-07-30): tarred structural frame proud of limewash infill, worked and industrial,
never Tudor-decorative. Moss is PAINT (and a known false-yellow — check green_pct
before believing any colour number on this subject).

Camera is TRUE ORTHOGRAPHIC, flat-on to the climb: the rise reads in silhouette, each
riser a clean horizontal step up, the section-through-a-hill-town look. The interior
telephoto rule does not apply — this is an exterior with fronts parallel to the
picture plane.

Run:
  blender.exe -b -P crooked_stair_module.py -- --out <dir>

Emits, at the plate's native 1344x768:
  module_depth.png   normalised inverted Z  (ControlNet 'depth')
  module_clay.png    flat-shaded beauty     (source for a canny/lineart guide)
  module.blend       the saved template, so the camera is reusable per module
"""
import argparse
import math
import os
import random
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
rng22 = random.Random(22)   # fixed seed: the crookedness is authored, reproducible


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


# ---------------------------------------------------------------- the 22 steps
# The stair climbs left to right across the frame. Each step is a full-height block
# from below grade to its own top, so the run is solid stone with no voids beneath.
ALLEY_W = 2.6            # depth of the stair run in y
steps = []
x = -8.2
z_top = 0.35
yaw = 0.0
y_drift = 0.0
for i in range(22):
    riser = rng22.uniform(0.13, 0.27)            # not one the same height
    tread = rng22.uniform(0.36, 0.58)            # nor the same depth
    tilt = rng22.uniform(-2.2, 2.2)              # each slab sits a little wrong
    if i == 12:                                   # the dogleg — the stair kinks
        yaw += 9.0
        y_drift += 0.35
    y_drift += rng22.uniform(-0.05, 0.09)
    z_top += riser
    x += tread
    steps.append((x, y_drift, z_top))
    box(f"step_{i + 1:02d}", (x, y_drift, (z_top - 0.5) / 2 + 0.0),
        (tread + 0.12, ALLEY_W, z_top + 0.5),
        rot=(0, 0, math.radians(yaw * 0.35 + tilt * 0.4)))
    # a worn nosing lip proud of every third riser
    if i % 3 == 0:
        box(f"nosing_{i + 1:02d}", (x - tread / 2, y_drift - 0.1, z_top - 0.03),
            (0.14, ALLEY_W * 0.9, 0.07), rot=(0, 0, math.radians(tilt * 0.3)))

TOP_X, TOP_Y, TOP_Z = steps[-1]
BOT_Z = steps[0][2]

# landing slabs at foot and head
box("landing_foot", (-9.4, 0, -0.08), (2.6, ALLEY_W + 0.8, 0.7))
box("landing_head", (TOP_X + 1.6, TOP_Y, TOP_Z - 0.35), (2.8, ALLEY_W + 0.4, 0.7))

# the gutter channel running down the wall side of the steps, stepped with them
for i in range(0, 22, 2):
    sx, sy, sz = steps[i]
    box(f"gutter_{i:02d}", (sx, sy + ALLEY_W / 2 - 0.18, sz + 0.02), (0.5, 0.3, 0.08))
    box(f"gutter_kerb_{i:02d}", (sx, sy + ALLEY_W / 2 - 0.02, sz + 0.07), (0.5, 0.08, 0.14))

# ---------------------------------------------------------------- the far side
# Three half-timber fronts stepping up the hill behind the stair, facing the camera.
# Tarred frame proud of the infill; jettied upper storeys; doors opening onto the run.
WALL_Y = ALLEY_W / 2 + 0.55


def half_timber(idx, x0, x1, base_z, storeys, jetty):
    w = x1 - x0
    cx = (x0 + x1) / 2
    h = 2.75 * storeys
    y = WALL_Y + 0.3
    grp = f"ht{idx}"
    box(f"{grp}_infill", (cx, y, base_z + h / 2), (w, 0.5, h))
    # sill beam, storey rails, wall plate — the horizontal frame
    for k in range(storeys + 1):
        box(f"{grp}_rail_{k}", (cx, y - 0.3, base_z + k * 2.75 + (0.12 if k == 0 else 0)),
            (w + 0.08, 0.16, 0.24))
    # posts — vertical frame, uneven spacing
    px = x0 + 0.18
    k = 0
    while px < x1 - 0.1:
        box(f"{grp}_post_{k}", (px, y - 0.3, base_z + h / 2), (0.2, 0.16, h))
        px += rng22.uniform(1.0, 1.6)
        k += 1
    # diagonal braces in the lower panels
    for bi, bx in enumerate((x0 + w * 0.22, x0 + w * 0.72)):
        box(f"{grp}_brace_{bi}", (bx, y - 0.3, base_z + 1.05),
            (0.16, 0.14, 1.7), rot=(0, math.radians(34 if bi % 2 else -34), 0))
    # jettied upper storey leaning over the stair
    if jetty and storeys > 1:
        box(f"{grp}_jetty", (cx, y - 0.42, base_z + 2.75), (w + 0.2, 0.75, 0.3))
        for ji in range(3):
            box(f"{grp}_jetty_bracket_{ji}", (x0 + w * (0.2 + ji * 0.3), y - 0.6, base_z + 2.5),
                (0.14, 0.5, 0.14), rot=(math.radians(38), 0, 0))
        box(f"{grp}_upper", (cx, y - 0.32, base_z + 2.75 + 1.4), (w + 0.2, 0.55, 2.6))
        for k in range(3):
            box(f"{grp}_upper_post_{k}", (x0 + w * (0.15 + k * 0.35), y - 0.62, base_z + 4.1),
                (0.18, 0.14, 2.5))
    # roofline — a simple eave slab pitched back
    rz = base_z + h + (0.55 if jetty and storeys > 1 else 0.35)
    box(f"{grp}_eave", (cx, y - 0.15, rz), (w + 0.5, 1.1, 0.18), rot=(math.radians(16), 0, 0))
    # windows with shutters
    for st in range(storeys):
        wz = base_z + 1.5 + st * 2.75
        wy = y - (0.66 if (jetty and st == 1) else 0.34)
        for wxx in (cx - w * 0.26, cx + w * 0.26):
            box(f"{grp}_win_{st}_{wxx:.1f}", (wxx, wy, wz), (0.5, 0.1, 0.7))
            box(f"{grp}_shut_a_{st}_{wxx:.1f}", (wxx - 0.4, wy - 0.03, wz), (0.22, 0.07, 0.7))
            box(f"{grp}_shut_b_{st}_{wxx:.1f}", (wxx + 0.4, wy - 0.03, wz), (0.22, 0.07, 0.7))


half_timber(1, -9.8, -4.6, 0.0, 2, True)
half_timber(2, -4.4, 1.6, 1.4, 2, False)
half_timber(3, 1.8, 7.4, 2.9, 2, True)

# doors opening onto the run — each doorstep meets the stair at its own height
for di, (dx, dz) in enumerate(((-6.4, 0.42), (-1.2, 1.85), (4.6, 3.6))):
    box(f"door_{di}", (dx, WALL_Y + 0.06, dz + 1.0), (0.95, 0.14, 2.0))
    box(f"door_frame_{di}", (dx, WALL_Y + 0.1, dz + 2.06), (1.2, 0.18, 0.16))
    box(f"doorstep_{di}", (dx, WALL_Y - 0.3, dz + 0.07), (1.2, 0.5, 0.16))

# ---------------------------------------------------------------- the near side
# Lower-left: a house corner crops into frame, the alley squeezing past it.
box("near_corner", (-8.9, -ALLEY_W / 2 - 1.15, 1.7), (2.4, 1.6, 4.6))
box("near_corner_eave", (-8.9, -ALLEY_W / 2 - 1.15, 4.1), (2.9, 2.0, 0.16), rot=(math.radians(-14), 0, 0))
box("near_corner_post", (-7.75, -ALLEY_W / 2 - 0.42, 1.6), (0.2, 0.18, 4.4))
box("near_corner_window", (-8.6, -ALLEY_W / 2 - 0.34, 2.3), (0.5, 0.1, 0.68))

# iron handrail up the near edge of the middle flight — posts follow the rise
rail_pts = [steps[i] for i in range(6, 17, 2)]
for ri, (rx, ry, rz) in enumerate(rail_pts):
    box(f"rail_post_{ri}", (rx, ry - ALLEY_W / 2 + 0.14, rz + 0.5), (0.06, 0.06, 1.0))
for ri in range(len(rail_pts) - 1):
    (x0, y0, z0), (x1, y1, z1) = rail_pts[ri], rail_pts[ri + 1]
    span = math.hypot(x1 - x0, z1 - z0)
    pitch = math.atan2(z1 - z0, x1 - x0)
    box(f"rail_run_{ri}", ((x0 + x1) / 2, (y0 + y1) / 2 - ALLEY_W / 2 + 0.14, (z0 + z1) / 2 + 1.0),
        (span + 0.1, 0.07, 0.07), rot=(0, -pitch, 0))

# rope handrail on the wall side of the upper flight — rings + sagging spans
ring_pts = [steps[i] for i in range(14, 22, 3)]
for gi, (gx, gy, gz) in enumerate(ring_pts):
    box(f"rope_ring_{gi}", (gx, gy + ALLEY_W / 2 + 0.28, gz + 1.05), (0.1, 0.08, 0.16))
for gi in range(len(ring_pts) - 1):
    (x0, y0, z0), (x1, y1, z1) = ring_pts[gi], ring_pts[gi + 1]
    span = math.hypot(x1 - x0, z1 - z0)
    pitch = math.atan2(z1 - z0, x1 - x0)
    cyl(f"rope_span_{gi}", ((x0 + x1) / 2, (y0 + y1) / 2 + ALLEY_W / 2 + 0.26, (z0 + z1) / 2 + 0.92),
        0.035, span, rot=(0, math.radians(90) - pitch, 0))

# ---------------------------------------------------------------- the stuff
# the lantern on its bracket at the dogleg
DOG_X, DOG_Y, DOG_Z = steps[12]
box("lantern_bracket", (DOG_X - 0.2, WALL_Y - 0.28, DOG_Z + 2.5), (0.55, 0.08, 0.08))
box("lantern", (DOG_X - 0.45, WALL_Y - 0.3, DOG_Z + 2.2), (0.32, 0.32, 0.46))

# barrels and a crate on the wider landings; firewood under the first jetty
cyl("barrel_foot", (-9.0, 0.75, 0.42 - 0.35 + BOT_Z), 0.36, 0.8)
cyl("barrel_head_a", (TOP_X + 1.3, TOP_Y + 0.75, TOP_Z + 0.4), 0.36, 0.8)
cyl("barrel_head_b", (TOP_X + 2.1, TOP_Y + 0.55, TOP_Z + 0.4), 0.33, 0.74)
box("crate_mid", (DOG_X + 0.55, DOG_Y + 0.85, DOG_Z + 0.34), (0.62, 0.62, 0.6),
    rot=(0, 0, math.radians(17)))
for fi in range(3):
    box(f"firewood_{fi}", (-6.2 + fi * 0.1, WALL_Y - 0.5, 0.55 + fi * 0.22),
        (1.1 - fi * 0.2, 0.45, 0.2), rot=(0, 0, math.radians(fi * 6 - 5)))
box("bucket", (-3.4, -0.4, 1.98 + 0.14), (0.28, 0.28, 0.3))
box("broom", (4.2, WALL_Y - 0.2, 3.6 + 0.8), (0.06, 0.06, 1.6), rot=(math.radians(-12), math.radians(8), 0))

# a squeezed sliver of sky-gap between buildings 2 and 3 — the alley continues up
box("gap_wall", (1.7, WALL_Y + 1.6, 4.4), (0.5, 2.4, 6.0))

# ---------------------------------------------------------------- the hill itself
# After looking: the frame's lower right was void — the buildings floated on air.
# Foundation masses run under each front down to below grade, and past the head
# landing the ground is HELD by a retaining face with buttresses; the stair's
# gutter discharges through a culvert spout onto a splash block at its foot.
box("found_1", (-7.2, WALL_Y + 0.42, -0.3), (5.2, 0.75, 0.7))
box("found_2", (-1.4, WALL_Y + 0.42, 0.45), (6.0, 0.75, 2.0))
# one solid hillside mass under the head landing and building 3 — the depth pass
# showed a void there (rays slipping past a thin foundation into nothing)
box("found_3", (5.0, 1.35, 1.85), (6.4, 1.9, 4.9))
# the street apron at the stair's foot: the ground the camera stands over, so the
# frame bottom reads as near pavement instead of a black hole
box("apron", (0.0, -3.8, -2.12), (21.5, 5.4, 4.15))
# (thick, like the quay's water slab: the tall front face catches the lowest ortho
# rays at near depth, so the frame bottom clamps white instead of black void)
box("retain_face", (7.1, TOP_Y + 0.2, (TOP_Z - 0.9) / 2), (3.4, 2.6, TOP_Z + 0.1))
box("retain_cap", (7.1, TOP_Y + 0.2, TOP_Z - 0.55), (3.6, 2.8, 0.24))
for i, bx in enumerate((6.2, 7.9)):
    box(f"buttress_{i}", (bx, TOP_Y - 1.15, 1.1), (0.9, 0.6, 3.2), rot=(math.radians(-6), 0, 0))
box("culvert_spout", (8.3, TOP_Y - 1.1, 1.5), (0.5, 1.1, 0.3), rot=(math.radians(-18), 0, 0))
box("splash_block", (8.6, TOP_Y - 1.55, 0.1), (0.9, 0.9, 0.5))

# ---------------------------------------------------------------- camera
# TRUE ORTHOGRAPHIC, flat-on to the climb, pitched 10 degrees down. The module's
# identity — every re-render must reuse this camera (saved into module.blend).
cam_data = bpy.data.cameras.new("module_cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 21.0
cam = bpy.data.objects.new("module_cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (-0.4, -14.0, 3.9)
cam.rotation_euler = (math.radians(80.0), 0, 0)
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
NEAR, FAR = 11.0, 19.5
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
print(f"[module] objects: {len(bpy.data.objects)}  steps=22")
