# Salt Road style set — structural-plate blockouts (kickoff §5, contract §6).
# Fixed orthographic oblique camera, viewer-facing fronts. Renders clay (Workbench,
# cavity edges — canny source) + normalized inverted Z depth (Cycles) per scene.
# Deterministic: stair jitter seeded 730114. Run:
#   blender -b -P blockouts.py -- --out <dir>
import bpy, math, random, sys, os

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[ARGS.index("--out") + 1] if "--out" in ARGS else os.path.dirname(os.path.abspath(__file__))
BRIG = "E:/AI-Models/mesh-store/portlight-ships/brig-normalised/brig__01-pristine__sails-open.glb"
CARAVEL = "E:/AI-Models/mesh-store/portlight-ships/caravel-normalised/caravel__01-pristine__sails-open.glb"
RES = (1344, 768)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def box(name, size, loc, rot=(0, 0, 0)):
    # primitive size=1 → dimensions equal scale; scale by the full size (NOT /2 —
    # halving every box while cylinders stayed full-size caused detached massing)
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    return o


def cyl(name, r, depth, loc, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    return o


def plane(name, size, loc):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
    o = bpy.context.object
    o.name = name
    return o


def group_bbox(objs):
    import mathutils
    pts = []
    deps = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        if o.type != "MESH":
            continue
        oe = o.evaluated_get(deps)
        for c in oe.bound_box:
            pts.append(oe.matrix_world @ mathutils.Vector(c))
    xs = [p.x for p in pts]; ys = [p.y for p in pts]; zs = [p.z for p in pts]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def make_cam(pitch_deg, ortho_scale, target, dist=45.0):
    p = math.radians(pitch_deg)
    fwd = (0.0, math.cos(p), -math.sin(p))
    loc = (target[0], target[1] - fwd[1] * dist, target[2] - fwd[2] * dist)
    bpy.ops.object.camera_add(location=loc, rotation=(math.radians(90 - pitch_deg), 0, 0))
    cam = bpy.context.object
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    cam.data.clip_start = 0.1
    cam.data.clip_end = 120.0
    bpy.context.scene.camera = cam
    return cam


def frame_cam(objs, pitch_deg, margin=1.18):
    (x0, x1), (y0, y1), (z0, z1) = group_bbox(objs)
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    p = math.radians(pitch_deg)
    w = (x1 - x0)
    h = (z1 - z0) * math.cos(p) + (y1 - y0) * math.sin(p)
    aspect = RES[0] / RES[1]
    scale = max(w, h * aspect) * margin
    make_cam(pitch_deg, scale, (cx, cy, cz))


def render_pair(tag, subject_objs):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    os.makedirs(os.path.join(OUT, tag), exist_ok=True)
    # clay — Workbench, studio light, cavity edges
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "SINGLE"
    sh.single_color = (0.78, 0.78, 0.78)
    sh.show_cavity = True
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = os.path.join(OUT, tag, "clay.png")
    bpy.ops.render.render(write_still=True)
    # depth — Cycles + material_override emission keyed to camera Z depth
    # (no compositor: Scene.node_tree is gone in Blender 5.x). near = white.
    import mathutils
    cam = sc.camera
    fwd = cam.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))
    deps = bpy.context.evaluated_depsgraph_get()
    ds = []
    for o in subject_objs:
        if o.type != "MESH":
            continue
        oe = o.evaluated_get(deps)
        for c in oe.bound_box:
            p = oe.matrix_world @ mathutils.Vector(c)
            ds.append((p - cam.matrix_world.translation).dot(fwd))
    dmin, dmax = min(ds) * 0.98, max(ds) * 1.05
    mat = bpy.data.materials.get("depthmat") or bpy.data.materials.new("depthmat")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    camdata = nt.nodes.new("ShaderNodeCameraData")
    mr = nt.nodes.new("ShaderNodeMapRange")
    em = nt.nodes.new("ShaderNodeEmission")
    outp = nt.nodes.new("ShaderNodeOutputMaterial")
    mr.clamp = True
    mr.inputs["From Min"].default_value = dmin
    mr.inputs["From Max"].default_value = dmax
    mr.inputs["To Min"].default_value = 1.0
    mr.inputs["To Max"].default_value = 0.0
    nt.links.new(camdata.outputs["View Z Depth"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], outp.inputs["Surface"])
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 8
    sc.cycles.use_denoising = False
    sc.view_layers[0].material_override = mat
    sc.render.image_settings.color_mode = "BW"
    sc.render.filepath = os.path.join(OUT, tag, "depth.png")
    bpy.ops.render.render(write_still=True)
    sc.view_layers[0].material_override = None
    print("RENDERED", tag)


def import_hull(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in set(bpy.data.objects) - before if o.type == "MESH"]
    bpy.ops.object.empty_add(location=(0, 0, 0))
    root = bpy.context.object
    for o in objs:
        if o.parent is None or o.parent not in objs:
            o.parent = root
    (x0, x1), (y0, y1), (z0, z1) = group_bbox(objs)
    # long axis along X (broadside to camera)
    if (y1 - y0) > (x1 - x0):
        root.rotation_euler[2] = math.radians(90)
        bpy.context.view_layer.update()
        (x0, x1), (y0, y1), (z0, z1) = group_bbox(objs)
    s = 14.0 / max(x1 - x0, 0.001)
    root.scale = (s, s, s)
    bpy.context.view_layer.update()
    (x0, x1), (y0, y1), (z0, z1) = group_bbox(objs)
    # sink ~10% of total height below waterline, center at x=0,y=0
    root.location = (-(x0 + x1) / 2, -(y0 + y1) / 2, -(z0 + (z1 - z0) * 0.10))
    bpy.context.view_layer.update()
    return root, objs


def scene_common_water():
    plane("water", 90, (0, 4, 0.0))
    box("backdrop", (90, 0.5, 30), (0, 22, 15))


def quay_strip(y=-6.0):
    q = box("quay", (30, 3.2, 1.5), (0, y, 0.75))
    for i, x in enumerate((-9, 0, 9)):
        cyl(f"bollard{i}", 0.28, 1.0, (x, y - 1.0, 1.5 + 0.35))
    return q


def build_hull(tag, path, yaw_deg=0.0, pitch=24):
    reset()
    root, objs = import_hull(path)
    if yaw_deg:
        root.rotation_euler[2] += math.radians(yaw_deg)
        bpy.context.view_layer.update()
    scene_common_water()
    q = quay_strip()
    frame_cam(objs, pitch, margin=1.10)
    render_pair(tag, objs + [q])


def crane_parts(with_wheel):
    parts = []
    bpy.ops.object.empty_add(location=(0, 0, 0))
    rig = bpy.context.object
    for x in (-2.3, 2.3):
        parts.append(cyl(f"tower{x}", 1.15, 7.4, (x, 0, 3.7)))
        parts.append(cyl(f"plinth{x}", 1.42, 1.1, (x, 0, 0.55)))
    parts.append(box("house", (5.8, 3.0, 2.4), (0, 0, 8.2)))
    parts.append(box("roofA", (6.2, 2.0, 0.28), (0, -0.85, 9.9), rot=(math.radians(35), 0, 0)))
    parts.append(box("roofB", (6.2, 2.0, 0.28), (0, 0.85, 9.9), rot=(math.radians(-35), 0, 0)))
    parts.append(box("jib", (0.65, 8.0, 0.65), (0, -3.0, 7.0), rot=(math.radians(28), 0, 0)))
    parts.append(cyl("rope", 0.12, 3.1, (0, -6.53, 3.55)))
    parts.append(cyl("cask", 0.62, 1.05, (0, -6.53, 1.5)))
    if with_wheel:
        parts.append(cyl("wheel", 1.85, 0.7, (0, 0, 3.2), rot=(0, math.radians(90), 0), verts=48))
        parts.append(cyl("axle", 0.18, 5.4, (0, 0, 3.2), rot=(0, math.radians(90), 0)))
        parts.append(box("galleryfloor", (4.6, 2.6, 0.35), (0, 0, 1.7)))
        for x in (-1.7, 1.7):
            for y in (-1.05, 1.05):
                parts.append(box(f"post{x}{y}", (0.24, 0.24, 4.8), (x, y, 4.1)))
    parts.append(box("base", (8.5, 5.0, 1.2), (0, 0, 0.6)))
    for p in parts:
        p.parent = rig
    rig.rotation_euler[2] = math.radians(18)
    bpy.context.view_layer.update()
    return parts


def build_crane(tag, close):
    reset()
    parts = crane_parts(with_wheel=close)
    scene_common_water()
    box("quayfloor", (30, 10, 0.4), (0, 1.5, -0.2))
    if close:
        focus = [p for p in parts if p.name in ("wheel", "axle", "galleryfloor", "jib", "cask", "rope") or p.name.startswith(("tower", "post", "plinth"))]
        frame_cam(focus, 17, margin=1.12)
    else:
        frame_cam(parts, 21, margin=1.15)
    render_pair(tag, parts)


def build_door(tag):
    reset()
    bpy.ops.object.empty_add(location=(0, 0, 0))
    root = bpy.context.object
    parts = []
    parts.append(box("facade", (7.6, 0.7, 9.4), (0, 0.35, 4.7)))
    for x in (-1.35, 1.35):
        parts.append(box(f"jamb{x}", (0.34, 0.5, 3.7), (x, -0.25, 1.85)))
    parts.append(box("lintel", (3.1, 0.5, 0.4), (0, -0.25, 3.85)))
    parts.append(box("door", (2.36, 0.3, 3.5), (0, 0.13, 1.75)))
    for x in (-2.3, 2.3):
        parts.append(box(f"win{x}", (1.0, 0.45, 1.2), (x, -0.12, 6.0)))
    parts.append(box("beam", (0.4, 2.4, 0.4), (0, -0.9, 8.3)))
    parts.append(cyl("tackle", 0.16, 0.6, (0, -1.9, 7.6)))
    parts.append(box("plaque", (0.7, 0.12, 0.9), (1.75, -0.06, 2.6)))
    for p in parts:
        p.parent = root
    root.rotation_euler[0] = math.radians(-4.5)  # op de vlucht lean toward viewer
    bpy.context.view_layer.update()
    th = box("threshold", (3.6, 1.6, 0.34), (0, -0.8, 0.17))
    # flanking neighbours fill the frame edges (kills the void flanks)
    nL = box("neighbourL", (9.0, 1.0, 8.2), (-8.6, 0.5, 4.1), rot=(math.radians(-2.5), 0, 0))
    nR = box("neighbourR", (9.0, 1.0, 8.8), (8.6, 0.5, 4.4), rot=(math.radians(-3.5), 0, 0))
    plane("ground", 80, (0, 0, 0.0))
    box("backdrop", (120, 0.5, 50), (0, 8, 20))
    make_cam(11, 17.0, (0, 0, 4.55))
    render_pair(tag, parts + [th, nL, nR])


def build_stair(tag):
    reset()
    rng = random.Random(730114)
    top = 6.0
    tread = 0.62
    steps = []
    z = top
    for i in range(22):
        rise = 0.26 + rng.uniform(-0.08, 0.10)
        steps.append(box(f"step{i}", (2.4, tread, max(z, 0.06)), (0, 1.0 + i * tread, max(z, 0.06) / 2)))
        z -= rise
    walls = []
    for sx, lean in ((-1.9, 2.5), (1.9, -2.5)):
        walls.append(box(f"wall{sx}", (0.9, 16.5, 8.5), (sx, 7.5, 4.25), rot=(0, math.radians(lean), 0)))
    # building masses fill the frame edges; low roof slabs give the paint a roofline
    for sx in (-5.2, 5.2):
        walls.append(box(f"mass{sx}", (6.8, 15.5, 7.2), (sx, 7.5, 3.6)))
        walls.append(box(f"roof{sx}", (7.4, 16.0, 0.4), (sx, 7.5, 7.6), rot=(0, math.radians(-9 if sx > 0 else 9), 0)))
    plane("water", 60, (0, 18.5, -0.4))
    box("backdrop", (60, 0.5, 24), (0, 26, 12))
    make_cam(34, 13.5, (0, 7.0, 2.8))
    render_pair(tag, steps + walls)


build_hull("p16-hull-brig", BRIG, yaw_deg=0.0, pitch=24)
build_hull("p17-hull-caravel", CARAVEL, yaw_deg=-32.0, pitch=24)
build_crane("p04-crane-tower", close=False)
build_crane("p05-crane-treadwheel", close=True)
build_door("p07-bonded-door")
build_stair("p14-crooked-stair")
print("ALL BLOCKOUTS DONE ->", OUT)
