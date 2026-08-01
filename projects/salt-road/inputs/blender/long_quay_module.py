"""Salt Road — long quay EXTERIOR module, authored as blocky proxy geometry.

Contract §7: "The crane as a two-towered building; a wet stone lip that does not look
wet; hawsers coiled chest-high." Law 2: warehouses lean op de vlucht over the quay,
hoist beams projecting. Law 3: the crane is architecture — two masonry towers with the
timber hoist house slung between. Law 5: a working quay is chokingly undersized — crowd
it. The wet lip itself is PAINT (a different ramp, §3); what the module supplies is the
stepped stone edge, the bollards, and the water stairs for that paint to land on.

CAMERA IS TRUE ORTHOGRAPHIC — this is the exterior rule from bonded_warehouse_module.py
inverted: flat-on building fronts are the point of the New Horizons town grammar
(contract §6), and ortho keeps every facade parallel to the picture plane. The oblique
"seen from slightly above" is a 10-degree pitch; parallel projection keeps verticals
vertical under pitch, which a perspective lens would not.

Run:
  blender.exe -b -P long_quay_module.py -- --out <dir>

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


# ---------------------------------------------------------------- water + quay
# Water in the foreground (-Y), facade row at the back (+Y), camera over the water.
QUAY_Z = 0.55                        # quay deck height over water
# water is a THICK slab: its tall front face catches every low ortho ray at near
# depth (clamps white = near), so the frame bottom reads as water, never as void
box("water", (0, -7.5, -3.4), (40.0, 13.0, 6.1))
box("quay_deck", (0, 2.0, QUAY_Z - 0.12), (40.0, 8.4, 0.24))
box("quay_wall", (0, -2.15, -0.95), (40.0, 0.3, 3.2))          # vertical face, deep
box("quay_lip", (0, -2.08, QUAY_Z + 0.03), (40.0, 0.55, 0.14))  # the stone lip course
# closes the underworld: without it, down-tilted rays pass beneath the deck edge and
# hit the buried halves of the facade slabs — rendered as ghost buildings in the water
box("seabed", (0, -2.0, -2.2), (46.0, 26.0, 0.3))

# mooring bollards along the lip — squat, heavy, leaning years of hawser wear
for i in range(9):
    x = -16.0 + i * 4.0
    cyl(f"bollard_{i}", (x, -1.75, QUAY_Z + 0.28), 0.16, 0.62,
        rot=(math.radians(4 if i % 2 else -3), math.radians(3 if i % 3 else 0), 0))
    cyl(f"bollard_head_{i}", (x, -1.75, QUAY_Z + 0.62), 0.21, 0.14)

# water stairs cut into the quay at one point — steps down to the tide
for s in range(5):
    box(f"water_stair_{s}", (7.6, -2.25 - s * 0.28, QUAY_Z - 0.16 - s * 0.2),
        (1.6, 0.3, 0.2))

# ---------------------------------------------------------------- the facades
# Eight distinct fronts, flat-on to camera, varied width/height/gable, every one
# leaning op de vlucht (top toward the water) with a projecting hoist beam.
FACADE_Y = 6.2
_fx = -17.4


def facade(idx, width, storeys, gable, lean_deg, hoist_load, yo=0.0):
    """One front. yo staggers the building off the row line — a real quay row is
    never flush, and the stagger is what keeps the depth map from reading as
    'identical repeating facades' (a named NOT-THAT)."""
    global _fx
    x = _fx + width / 2
    _fx += width + 0.25
    h = 2.9 * storeys + 0.6
    lean = math.radians(lean_deg)
    FY = FACADE_Y + yo
    grp = f"f{idx}"
    # main slab, grounded at z -0.6 (a buried double-height slab let low ortho rays
    # hit basement ghosts under the quay — seen in the depth pass, removed)
    zc = (h - 0.6) / 2
    box(f"{grp}_body", (x, FY, zc), (width, 0.6, h + 0.6), rot=(lean, 0, 0))

    def face_y(z):
        # y of the leaned wall face at height z (pivot at the slab centre zc)
        return FY - 0.32 - (z - zc) * math.tan(lean)

    # gable
    if gable == "step":
        for gi in range(4):
            gw = width * (0.78 - gi * 0.19)
            gz = h + 0.45 + gi * 0.62
            box(f"{grp}_gable_{gi}", (x, face_y(gz) + 0.32, gz),
                (gw, 0.6, 0.62), rot=(lean, 0, 0))
    else:  # spout gable — a single narrowing cap
        for gi, (gw, gz) in enumerate(((width * 0.62, h + 0.5), (width * 0.3, h + 1.2))):
            box(f"{grp}_gable_{gi}", (x, face_y(gz) + 0.32, gz),
                (gw, 0.6, 0.95 if gi == 0 else 0.6), rot=(lean, 0, 0))
    # window rows: shutters proud of the wall each side of a dark inset
    cols = max(2, int(width / 1.35))
    for st in range(storeys):
        wz = 1.9 + st * 2.9
        # y of the wall face at this height, given the lean
        wy = face_y(wz)
        for c in range(cols):
            wx = x - (cols - 1) * 0.62 + c * 1.24
            if abs(wx - x) < 0.5 and st > 0:
                continue  # centre column above ground floor = loading doors
            box(f"{grp}_win_{st}_{c}", (wx, wy - 0.02, wz), (0.52, 0.1, 0.78))
            box(f"{grp}_shut_a_{st}_{c}", (wx - 0.42, wy - 0.06, wz), (0.24, 0.07, 0.78))
            box(f"{grp}_shut_b_{st}_{c}", (wx + 0.42, wy - 0.06, wz), (0.24, 0.07, 0.78))
            box(f"{grp}_sill_{st}_{c}", (wx, wy - 0.05, wz - 0.45), (0.62, 0.12, 0.07))
    # loading doors up the centre line (recessed dark openings), one per upper storey
    for st in range(1, storeys):
        dz = 1.95 + st * 2.9
        box(f"{grp}_load_{st}", (x, face_y(dz) + 0.24, dz), (0.95, 0.2, 1.5))
    # ground floor door + step
    box(f"{grp}_door", (x, face_y(1.15) - 0.04, 1.15), (1.0, 0.12, 2.3))
    box(f"{grp}_doorstep", (x, FY - 0.62, 0.62 + 0.04), (1.3, 0.5, 0.14))
    # the hoist beam at the gable peak, projecting over the quay, tackle hung
    bz = h + 0.35
    by = face_y(bz) + 0.02
    box(f"{grp}_hoist_beam", (x, by - 0.55, bz), (0.22, 1.5, 0.22))
    box(f"{grp}_tackle", (x, by - 1.2, bz - 0.32), (0.14, 0.14, 0.4))
    if hoist_load:
        box(f"{grp}_hoist_rope", (x, by - 1.2, bz - 1.7), (0.05, 0.05, 2.4))
        box(f"{grp}_hoist_load", (x, by - 1.2, bz - 3.1), (0.7, 0.6, 0.55))
    return x


xs = []
xs.append(facade(1, 3.6, 4, "step", 2.4, False, yo=0.0))
xs.append(facade(2, 4.4, 3, "spout", 1.6, True, yo=0.45))
xs.append(facade(3, 3.2, 4, "step", 3.0, False, yo=-0.25))
xs.append(facade(4, 5.0, 3, "step", 2.0, False, yo=0.15))   # crane stands before this one
xs.append(facade(5, 3.8, 4, "spout", 2.6, False, yo=-0.4))
xs.append(facade(6, 4.6, 3, "step", 1.8, True, yo=0.3))
xs.append(facade(7, 3.4, 4, "spout", 2.8, False, yo=0.0))
xs.append(facade(8, 4.8, 3, "step", 2.2, False, yo=0.5))

# ---------------------------------------------------------------- THE CRANE
# Two masonry towers with the timber hoist house slung between, standing ON the quay
# forward of the facade line — a building, not a prop (law 3).
# Rebuilt BIG after looking: the first pass rendered shorter and skinnier than the
# warehouses and read as furniture — law 3 inverted. Now the towers are real masonry
# and the ridge breaks the roofline of the whole row.
CX, CY = 0.6, 2.2
for sx, tag in ((-2.7, "a"), (2.7, "b")):
    box(f"crane_tower_{tag}", (CX + sx, CY, QUAY_Z + 5.5), (3.2, 3.2, 11.0))
    box(f"crane_tower_cap_{tag}", (CX + sx, CY, QUAY_Z + 11.3), (3.7, 3.7, 0.7))
    box(f"crane_tower_door_{tag}", (CX + sx, CY - 1.62, QUAY_Z + 1.15), (1.0, 0.12, 2.1))
    for wz in (4.2, 7.4):  # slit windows up the tower faces
        box(f"crane_slit_{tag}_{wz:.0f}", (CX + sx, CY - 1.62, QUAY_Z + wz), (0.4, 0.1, 0.9))
# the timber hoist house slung between the towers, riding high over the quay
box("crane_house", (CX, CY, QUAY_Z + 8.6), (5.6, 3.4, 4.4))
box("crane_roof_L", (CX - 1.55, CY, QUAY_Z + 11.9), (3.4, 3.8, 0.24), rot=(0, math.radians(34), 0))
box("crane_roof_R", (CX + 1.55, CY, QUAY_Z + 11.9), (3.4, 3.8, 0.24), rot=(0, math.radians(-34), 0))
box("crane_ridge", (CX, CY, QUAY_Z + 12.85), (0.5, 4.0, 0.4))
# treadwheel rims bulging through the house front — the machine inside the building
for sx, tag in ((-1.9, "a"), (1.9, "b")):
    cyl(f"treadwheel_{tag}", (CX + sx, CY, QUAY_Z + 8.4), 2.0, 0.6,
        rot=(0, math.radians(90), 0))
# twin jib timbers from the house head, rising OUT over the water (the Gdansk jib
# angles up) and spread into a V so the flat-on camera reads them as diagonals
# rather than foreshortening them to points
for sx, tag, yaw in ((-0.9, "a", -16), (0.9, "b", 16)):
    box(f"crane_jib_{tag}", (CX + sx, CY - 3.6, QUAY_Z + 9.6), (0.34, 7.2, 0.4),
        rot=(math.radians(-28), 0, math.radians(yaw)))
box("crane_jib_tie", (CX, CY - 6.7, QUAY_Z + 11.25), (2.9, 0.3, 0.3))
# hoist rope from the jib head straight down to a slung load, lowering to a berth
box("crane_rope", (CX, CY - 6.7, QUAY_Z + 7.3), (0.07, 0.07, 7.9))
for i, (dx, dz) in enumerate(((-0.42, 0.0), (0.42, 0.0), (0.0, 0.62))):
    cyl(f"crane_load_cask_{i}", (CX + dx, CY - 6.7, QUAY_Z + 2.4 + dz), 0.38, 0.8,
        rot=(0, math.radians(90), 0))

# ---------------------------------------------------------------- moored ships
# Hull sides, masts and yards along the bottom edge — berths competing for a wall
# built for half their number (law 5). Hulls read as long low slabs with rail lines.
# Rebuilt after looking: the first pass moored the hulls too far out and too low —
# they rendered as slivers and the water strip read empty. Now they lie AGAINST the
# wall, bulwarks over the lip, sterncastles and tops giving the berth line a skyline.
def ship(tag, x, y, hull_len, mast_n, list_deg):
    # berthed a strake off the wall (depth pass needs ≥1.5 m of separation from the
    # quay face or hull and wall merge into one value), bulwark riding over the lip
    ld = math.radians(list_deg)
    box(f"ship_{tag}_hull", (x, y, 0.55), (hull_len, 2.6, 2.0), rot=(0, 0, ld))
    box(f"ship_{tag}_bulwark", (x, y + 1.1, 2.0), (hull_len * 0.96, 0.18, 0.6), rot=(0, 0, ld))
    box(f"ship_{tag}_wale", (x, y + 1.23, 0.9), (hull_len, 0.14, 0.2), rot=(0, 0, ld))
    box(f"ship_{tag}_sterncastle", (x - hull_len / 2 + 0.9, y, 2.15), (1.8, 2.3, 1.2), rot=(0, 0, ld))
    for m in range(mast_n):
        mx = x - hull_len / 2 + (m + 1) * hull_len / (mast_n + 1)
        cyl(f"ship_{tag}_mast_{m}", (mx, y, 5.4), 0.17, 9.6,
            rot=(math.radians(2), math.radians(list_deg * 0.4), 0))
        cyl(f"ship_{tag}_yard_{m}", (mx, y + 0.1, 7.4), 0.1, 5.4,
            rot=(0, math.radians(90), math.radians(4 - m * 3)))
        box(f"ship_{tag}_furl_{m}", (mx, y + 0.1, 7.0), (4.8, 0.36, 0.42))
        cyl(f"ship_{tag}_top_{m}", (mx, y, 8.2), 0.3, 0.25)
    # bowsprit rising over the water strip
    cyl(f"ship_{tag}_bowsprit", (x + hull_len / 2 + 1.3, y - 0.45, 2.9), 0.11, 3.8,
        rot=(0, math.radians(62), math.radians(-10)))


ship("a", -9.5, -4.6, 9.5, 2, 1.5)
ship("b", 3.0, -5.0, 7.5, 1, -2.0)
ship("c", 13.5, -4.4, 8.5, 2, 1.0)
# a dinghy working between berths
box("dinghy", (8.9, -4.9, 0.15), (2.6, 1.1, 0.7), rot=(0, 0, math.radians(14)))
box("dinghy_thwart", (8.9, -4.9, 0.42), (0.9, 1.0, 0.08), rot=(0, 0, math.radians(14)))
# gangplanks from bulwark to quay
for tag, gx in (("a", -7.0), ("b", 4.6), ("c", 12.0)):
    box(f"gang_{tag}", (gx, -2.5, QUAY_Z + 0.9), (0.85, 3.2, 0.12), rot=(math.radians(-24), 0, math.radians(6)))

# ---------------------------------------------------------------- quay clutter
# hawsers coiled chest-high — stacked tapering coils (contract's named object)
for i, hx in enumerate((-13.2, -3.9, 10.4)):
    for lvl in range(4):
        cyl(f"hawser_{i}_{lvl}", (hx, -0.7, QUAY_Z + 0.16 + lvl * 0.3),
            0.56 - lvl * 0.05, 0.3, rot=(0, 0, math.radians(i * 30 + lvl * 15)))

# cask pyramids lying on their sides
def cask_row(tag, x, y, n, z):
    for c in range(n):
        cyl(f"cask_{tag}_{c}", (x + c * 0.84 - (n - 1) * 0.42, y, z), 0.4, 0.85,
            rot=(0, math.radians(90), 0))


for i, (px, py) in enumerate(((-15.2, 1.4), (-6.8, 0.6), (6.3, 1.2), (15.0, 0.8))):
    cask_row(f"p{i}0", px, py, 3, QUAY_Z + 0.42)
    cask_row(f"p{i}1", px, py, 2, QUAY_Z + 1.16)
    if i % 2 == 0:
        cask_row(f"p{i}2", px, py, 1, QUAY_Z + 1.9)

# bale rows and crate stacks between the berths
for i, (bx, by) in enumerate(((-11.6, 0.9), (0.9 - 5.3, 1.9), (8.2, 0.7), (12.6, 2.1))):
    box(f"bale_{i}_a", (bx, by, QUAY_Z + 0.42), (1.15, 0.75, 0.8))
    box(f"bale_{i}_b", (bx + 0.25, by + 0.1, QUAY_Z + 1.2), (0.95, 0.65, 0.72), rot=(0, 0, math.radians(9)))
for i, (kx, ky) in enumerate(((-8.3, 2.3), (5.6, 0.7), (16.6, 1.9), (-1.4, 0.75))):
    box(f"crate_{i}_a", (kx, ky, QUAY_Z + 0.36), (0.72, 0.72, 0.72))
    box(f"crate_{i}_b", (kx + 0.5, ky - 0.3, QUAY_Z + 0.3), (0.6, 0.6, 0.6))
    box(f"crate_{i}_c", (kx + 0.2, ky + 0.15, QUAY_Z + 1.0), (0.6, 0.6, 0.56), rot=(0, 0, math.radians(18)))

# an anchor leaning against the quayside bitts, stock up
box("anchor_shank", (-4.9, -1.5, QUAY_Z + 0.95), (0.14, 0.14, 1.9), rot=(math.radians(12), 0, 0))
box("anchor_stock", (-4.9, -1.62, QUAY_Z + 1.68), (1.15, 0.13, 0.13), rot=(0, 0, math.radians(4)))
box("anchor_arm_a", (-5.16, -1.35, QUAY_Z + 0.16), (0.6, 0.12, 0.12), rot=(0, 0, math.radians(38)))
box("anchor_arm_b", (-4.64, -1.35, QUAY_Z + 0.16), (0.6, 0.12, 0.12), rot=(0, 0, math.radians(-38)))

# handcarts, loose casks mid-roll, a plank pile, fish baskets
for i, (hx, hy, yaw) in enumerate(((-2.7, 2.6, 24), (11.4, 1.1, -35))):
    box(f"cart_{i}_bed", (hx, hy, QUAY_Z + 0.62), (1.5, 0.9, 0.1), rot=(0, 0, math.radians(yaw)))
    cyl(f"cart_{i}_wheel_a", (hx - 0.7 * math.cos(math.radians(yaw)), hy - 0.7 * math.sin(math.radians(yaw)), QUAY_Z + 0.4), 0.4, 0.1, rot=(0, math.radians(90), math.radians(yaw)))
    cyl(f"cart_{i}_wheel_b", (hx + 0.7 * math.cos(math.radians(yaw)), hy + 0.7 * math.sin(math.radians(yaw)), QUAY_Z + 0.4), 0.4, 0.1, rot=(0, math.radians(90), math.radians(yaw)))
    box(f"cart_{i}_handle", (hx, hy - 1.0, QUAY_Z + 0.9), (0.09, 1.1, 0.09), rot=(math.radians(30), 0, math.radians(yaw)))
cyl("loose_cask_a", (6.7, 2.9, QUAY_Z + 0.4), 0.38, 0.8, rot=(0, math.radians(90), math.radians(70)))
cyl("loose_cask_b", (-10.2, 2.9, QUAY_Z + 0.4), 0.38, 0.8, rot=(0, math.radians(90), math.radians(-50)))
for p in range(4):
    box(f"plank_{p}", (14.2, 3.4, QUAY_Z + 0.1 + p * 0.09), (3.4 - p * 0.15, 0.5, 0.08),
        rot=(0, 0, math.radians(3 * (p % 2) - 1.5)))
for i in range(3):
    cyl(f"basket_{i}", (4.0 + i * 0.5, 2.75 + (i % 2) * 0.35, QUAY_Z + 0.24), 0.24, 0.44)

# toll booth clear of the crane's footing — a hut the size of a confession box
box("booth_body", (6.4, 3.1, QUAY_Z + 1.15), (1.3, 1.3, 2.3))
box("booth_roof", (6.4, 3.1, QUAY_Z + 2.45), (1.7, 1.7, 0.3))
box("booth_window", (6.4, 2.42, QUAY_Z + 1.5), (0.6, 0.1, 0.5))

# ---------------------------------------------------------------- camera
# TRUE ORTHOGRAPHIC, flat-on to the facade row, pitched 10 degrees down so the quay
# deck opens without breaking a single vertical. This is the module's identity.
cam_data = bpy.data.cameras.new("module_cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 35.0
cam = bpy.data.objects.new("module_cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -20.0, 5.2)
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
NEAR, FAR = 13.0, 29.0
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
print(f"[module] objects: {len(bpy.data.objects)}  ortho_scale={cam_data.ortho_scale}")
