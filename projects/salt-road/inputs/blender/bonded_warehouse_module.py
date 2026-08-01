"""Salt Road — bonded warehouse interior module, authored as blocky proxy geometry.

Contract §2: "Perspective is locked in Blender, never in the prompt. A template .blend
with a fixed orthographic camera supplies depth + normal + lineart passes per module;
the LoRA supplies the paint."

This is that template, built procedurally so the module is reproducible from source
rather than from a binary nobody can diff. Geometry is deliberately CRUDE -- boxes and
cylinders. A depth pass does not care about bevels, and contract law 6 is explicit that
light comes first and geometry second, never texture-painted fake shadow. What the
module supplies is SPACE and the placement of stuff; the LoRA supplies the paint.

The object inventory is taken from the v4 density finding (2026-08-01): interiors were
short on flat_hf/lap_var not because the surface was wrong but because the scene had
too little in it. Every object the dense prompt named is built here, so the depth pass
carries the density instead of hoping the sampler invents it.

Run:
  blender.exe -b -P bonded_warehouse_module.py -- --out <dir>

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
# A long bonded warehouse seen down its axis. Camera looks along -Y.
W, D, H = 9.0, 16.0, 6.0          # width, depth, height in metres
box("floor", (0, 0, -0.1), (W, D, 0.2))
box("ceiling", (0, 0, H), (W, D, 0.2))
box("wall_L", (-W / 2, 0, H / 2), (0.2, D, H))
box("wall_R", (W / 2, 0, H / 2), (0.2, D, H))
box("wall_back", (0, D / 2, H / 2), (W, 0.2, H))

# roof trusses — the tarred timber the contract's material table calls the darkest value
for i in range(9):
    y = -D / 2 + 1.0 + i * 1.8
    box(f"tie_beam_{i}", (0, y, H - 0.55), (W, 0.28, 0.34))
    box(f"rafter_L_{i}", (-W / 4, y, H - 0.05), (W / 2, 0.22, 0.22), rot=(0, math.radians(18), 0))
    box(f"rafter_R_{i}", (W / 4, y, H - 0.05), (W / 2, 0.22, 0.22), rot=(0, math.radians(-18), 0))

# posts down both sides
for i in range(7):
    y = -D / 2 + 1.6 + i * 2.2
    for sx in (-1, 1):
        box(f"post_{'L' if sx < 0 else 'R'}_{i}", (sx * (W / 2 - 1.0), y, H / 2), (0.34, 0.34, H))

# ---------------------------------------------------------------- the gallery
# "a timber gallery running above" — the single biggest density win in the v4 test
GY = 2.2
box("gallery_deck", (-W / 2 + 1.9, GY, 3.1), (3.4, 9.0, 0.18))
box("gallery_beam", (-W / 2 + 3.5, GY, 2.95), (0.26, 9.0, 0.36))
for i in range(10):                      # balustrade
    box(f"baluster_{i}", (-W / 2 + 3.5, GY - 4.2 + i * 0.95, 3.55), (0.1, 0.1, 0.8))
box("gallery_rail", (-W / 2 + 3.5, GY, 3.98), (0.14, 9.0, 0.12))

# ---------------------------------------------------------------- the stuff
def cask_stack(x, y, rows=3, per=3, z0=0.42):
    """Casks lying on their sides, stacked -- contract law 4's 'someone's money'."""
    for r in range(rows):
        for c in range(per - r):
            cyl(f"cask_{x:.0f}_{y:.0f}_{r}_{c}",
                (x, y + (c + r * 0.5) * 0.86 - (per - 1) * 0.43, z0 + r * 0.78),
                0.39, 0.82, rot=(0, math.radians(90), 0))

def sack_stack(x, y, levels=4):
    for l in range(levels):
        for c in (-1, 1):
            box(f"sack_{x:.0f}_{y:.0f}_{l}_{c}",
                (x, y + c * 0.42, 0.18 + l * 0.34), (1.0, 0.78, 0.32))

for i, y in enumerate((-6.2, -3.4, -0.6, 2.2, 5.0)):
    cask_stack(-2.9, y)                       # left aisle: casks three deep
    sack_stack(3.1, y)                        # right: sacks on plank shelving
    box(f"shelf_{i}", (3.1, y, 1.45), (2.4, 2.2, 0.14))
    for l in range(3):                        # a second level of sacks on the shelf
        box(f"sack_hi_{i}_{l}", (3.1, y - 0.5 + l * 0.5, 1.72), (1.0, 0.44, 0.3))

# loading ramp angled down to the boards
box("ramp", (0.2, -1.4, 0.62), (1.7, 5.2, 0.16), rot=(math.radians(-13), 0, 0))
box("ramp_kerb_L", (-0.63, -1.4, 0.66), (0.1, 5.2, 0.2), rot=(math.radians(-13), 0, 0))
box("ramp_kerb_R", (1.03, -1.4, 0.66), (0.1, 5.2, 0.2), rot=(math.radians(-13), 0, 0))

# beam-scale hung from a roof timber — contract §7's weighing floor motif
box("scale_beam", (1.4, -4.6, 4.15), (1.5, 0.1, 0.1))
for sx in (-0.66, 0.66):
    box(f"scale_chain_{sx:.0f}", (1.4 + sx, -4.6, 3.75), (0.04, 0.04, 0.8))
    cyl(f"scale_pan_{sx:.0f}", (1.4 + sx, -4.6, 3.34), 0.34, 0.1)
box("scale_hanger", (1.4, -4.6, 4.6), (0.06, 0.06, 0.9))

# clerk's standing desk with ledger + wax jack (contract §7 counting house)
box("desk", (3.0, -6.6, 0.95), (1.7, 0.85, 0.12))
for dx, dy in ((-0.7, -0.3), (0.7, -0.3), (-0.7, 0.3), (0.7, 0.3)):
    box(f"desk_leg_{dx:.0f}_{dy:.0f}", (3.0 + dx, -6.6 + dy, 0.44), (0.1, 0.1, 0.9))
box("ledger", (3.0, -6.7, 1.05), (0.62, 0.44, 0.08), rot=(math.radians(-8), 0, 0))
cyl("wax_jack", (3.5, -6.5, 1.12), 0.06, 0.24)

# handcart + crates in the foreground
box("cart_bed", (-2.6, -7.4, 0.62), (1.5, 0.95, 0.12))
for sx in (-1, 1):
    cyl(f"cart_wheel_{sx}", (-2.6 + sx * 0.72, -7.4, 0.4), 0.4, 0.1, rot=(0, math.radians(90), 0))
box("cart_handle", (-2.6, -8.1, 0.95), (0.1, 1.1, 0.1), rot=(math.radians(28), 0, 0))
for i, (cx, cy) in enumerate(((0.9, -7.9), (1.7, -7.6), (1.3, -8.3))):
    box(f"crate_{i}", (cx, cy, 0.34), (0.68, 0.68, 0.68))

# coiled rope + tackle blocks on wall pegs
for i, y in enumerate((-5.0, -2.0, 1.0, 4.0)):
    cyl(f"rope_coil_{i}", (W / 2 - 0.45, y, 2.5), 0.3, 0.16, rot=(0, math.radians(90), 0))
    box(f"tackle_{i}", (-W / 2 + 0.45, y + 1.0, 2.7), (0.16, 0.26, 0.4))

# high windows — the contract's "shafts of dusty light from small high windows"
for i, y in enumerate((-4.5, 0.0, 4.5)):
    box(f"window_{i}", (W / 2 - 0.05, y, 4.4), (0.16, 1.0, 0.9))

# ---------------------------------------------------------------- camera
# FIXED ORTHOGRAPHIC, looking down the axis. This is the module's identity: every
# re-render of this module must reuse this camera or the "locked perspective" claim
# is void. Saved into module.blend so it travels with the file.
# ⚠ NOT true orthographic, and that is deliberate. A pure ortho camera looking down the
# axis of an interior sees NO convergence: the side walls, floor and ceiling are edge-on
# and collapse to lines, leaving only the back wall. Verified by rendering it. The
# contract's §6 wording is "minimal perspective recession", not zero, and the studio's
# proven sprite framing is "telephoto perspective = near-ortho, minimal distortion"
# (sprite_render.py). A long lens set well back is the correct reading for an INTERIOR
# module; keep true ortho for exterior building fronts, where flat-on is the point.
cam_data = bpy.data.cameras.new("module_cam")
cam_data.type = "PERSP"
cam_data.lens = 58.0                            # long enough that verticals stay vertical
cam = bpy.data.objects.new("module_cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -11.2, 2.55)
cam.rotation_euler = (math.radians(87.5), 0, 0)  # a touch down, to open the floor
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
# Without this the world stays black and the clay pass reads as objects floating in
# void, which is useless as a lineart source -- edges need something to sit against.
shading.background_type = "VIEWPORT"
shading.background_color = (0.88, 0.87, 0.84)
scene.render.filepath = os.path.join(args.out, "module_clay")
bpy.ops.render.render(write_still=True)

# Depth via EEVEE + compositor Z, normalised then inverted so near = bright, which is
# the convention the ControlNet depth preprocessors emit.
# Engine enum differs across Blender majors (EEVEE_NEXT in 4.2-4.x, EEVEE in 5.x).
# Pick whichever this build actually offers rather than pinning a name that moved.
_engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in _engines else "BLENDER_EEVEE"
# Depth as a SHADER, not a compositor pass. Blender 5 replaced scene.node_tree with a
# node group AND dropped CompositorNodeComposite AND moved OutputFile.base_path -- three
# breaking changes in one subsystem. A camera-distance emission shader renders the depth
# map directly as the beauty image and touches none of that API, so this module keeps
# building across Blender majors. Near = bright, matching what ControlNet depth
# preprocessors emit.
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

# Stretch the depth map to the FULL 0-1 range. Per the Comfy consult (2026-08-01) the
# Fun Union depth head is trained near=white/far=black (which our shader already emits,
# so no inversion) but expects a full-range map -- a compressed one silently weakens
# effective control strength, so two modules with different scene depths would not be
# controlled equally hard at the same `strength`. Measured before this fix: 62-243.
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
