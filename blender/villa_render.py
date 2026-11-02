#!/usr/bin/env python
"""
villa_render.py, photoreal render of an Adani "The North Park" villa, driven by
construction progress. Run head-less by the render service (server/server.js):

    blender -b -P blender/villa_render.py -- --out <png> [--engine CYCLES|EEVEE]
            [--samples 128] [--res 1600x1000] [--view hero|front|aerial|pool]
            [--time day|dusk] [--data <zones.json>] [--villa-no 08]
            [--neighbours 2] [--force-cpu]

Everything (geometry, materials, lighting, camera) is built in code. Textures, sky HDRIs
and plant/furniture models are CC0 assets from Poly Haven, fetched once with
`npm run assets` (blender/fetch_assets.py). Missing assets degrade gracefully.

Construction model: each zone (basement, groundFloor, firstFloor, facade, decks,
landscape, servantsQuarter) has a stage, Foundation → Structure → Finishing → Ready:
  Foundation  footings + starter bars / excavation; nothing above
  Structure   raw RCC frame, red-brick infill, open window holes, scaffolding
  Finishing   cement plaster, windows glazed; façade paint once the façade is finishing
  Ready       final paint, wood, glass railings, curtains, interiors, landscaping
"""
import bpy, sys, os, json, math, argparse, random, time
import numpy as np
from mathutils import Vector, Matrix

T_START = time.time()


def log(*a):
    print("[villa]", *a); sys.stdout.flush()


# ============================================================================ args + data
def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--engine", default="CYCLES", choices=["CYCLES", "EEVEE"])
    p.add_argument("--samples", type=int, default=128)
    p.add_argument("--res", default="1600x1000")
    p.add_argument("--data", default="")
    p.add_argument("--view", default="hero", choices=["hero", "front", "aerial", "pool"])
    p.add_argument("--time", default="day", choices=["day", "dusk"])
    p.add_argument("--villa-no", default="08")
    p.add_argument("--neighbours", type=int, default=2, help="finished villas on each side")
    p.add_argument("--force-cpu", action="store_true")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--export-web", default="", metavar="DIR",
                   help="export the stage-aware villa for the web app instead of rendering")
    return p.parse_args(argv)


ARGS = parse_args()
W, H = (int(x) for x in ARGS.res.lower().split("x"))
DUSK = ARGS.time == "dusk"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
EXPORT = bool(ARGS.export_web)
# export context: which build pass (tag) and zone the geometry being created belongs to
CUR = {"tag": "main", "zone": "site"}
WEB = {"parts": {}, "meshes": [], "instances": []}

STAGES = ("Foundation", "Structure", "Finishing", "Ready")
F, S, FI, R = range(4)
ZONES = ("basement", "groundFloor", "firstFloor", "facade", "decks", "landscape", "servantsQuarter")

# default construction state (mirrors the interactive app's demo villa); --data overrides
DATA = {"basement": "Finishing", "groundFloor": "Finishing", "firstFloor": "Structure",
        "facade": "Finishing", "decks": "Structure", "landscape": "Foundation",
        "servantsQuarter": "Structure"}
if ARGS.data and os.path.exists(ARGS.data):
    try:
        with open(ARGS.data) as f:
            raw = json.load(f)
        for k, v in raw.get("zones", raw).items():
            if k in DATA and isinstance(v, dict) and v.get("stage") in STAGES:
                DATA[k] = v["stage"]
    except Exception as e:
        log("data parse warning:", e)
STAGE = {z: STAGES.index(s) for z, s in DATA.items()}
READY = {z: R for z in ZONES}
log("stages:", DATA)


# ============================================================================ Blender compat
def ensure_nodes(idblock):
    """Blender 5.0+ always uses nodes and deprecates `use_nodes`."""
    if bpy.app.version < (5, 0, 0) or idblock.node_tree is None:
        idblock.use_nodes = True


def set_props(obj, **props):
    """Set each property that exists on this Blender version; skip the rest."""
    for k, v in props.items():
        if hasattr(obj, k):
            try:
                setattr(obj, k, v)
            except (TypeError, AttributeError, ValueError):
                pass


# ============================================================================ scene + render settings
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
random.seed(ARGS.seed)


def set_engine(name):
    if name == "EEVEE":
        for en in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                scene.render.engine = en
                return en
            except TypeError:
                continue
    scene.render.engine = "CYCLES"
    return "CYCLES"


ENGINE = set_engine(ARGS.engine)
CYCLES = ENGINE == "CYCLES"
log("engine:", ENGINE)

if CYCLES:
    backend_used = None
    if not ARGS.force_cpu:
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
                try:
                    prefs.compute_device_type = backend
                except TypeError:
                    continue
                try:
                    prefs.get_devices()
                except Exception:
                    pass
                if any(getattr(d, "type", "CPU") == backend for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = getattr(d, "type", "CPU") != "CPU"
                    scene.cycles.device = "GPU"
                    backend_used = backend
                    break
        except Exception as e:
            log("GPU setup skipped:", e)
    if backend_used is None:
        scene.cycles.device = "CPU"
    log("compute:", backend_used or "CPU")
    c = scene.cycles
    c.samples = ARGS.samples
    set_props(c, use_adaptive_sampling=True, adaptive_threshold=0.02, use_denoising=True,
              max_bounces=10, diffuse_bounces=4, glossy_bounces=4, transmission_bounces=8,
              transparent_max_bounces=48, sample_clamp_indirect=6.0, blur_glossy=1.0,
              caustics_reflective=False, caustics_refractive=False)
    set_props(scene.cycles_curves, shape="RIBBONS")
else:
    set_props(scene.eevee, taa_render_samples=max(32, ARGS.samples), use_raytracing=True,
              use_gtao=True, use_ssr=True, use_bloom=True, use_shadows=True)

r = scene.render
r.resolution_x, r.resolution_y, r.resolution_percentage = W, H, 100
r.image_settings.file_format = "PNG"
r.filepath = ARGS.out
for vt in ("AgX", "Filmic", "Standard"):
    try:
        scene.view_settings.view_transform = vt
        break
    except TypeError:
        continue
for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
    try:
        scene.view_settings.look = look
        break
    except TypeError:
        continue
scene.view_settings.exposure = 0.8 if DUSK else 0.25
log("colour:", scene.view_settings.view_transform, "/", scene.view_settings.look)

ROOT = bpy.data.collections.new("VILLAS")
scene.collection.children.link(ROOT)


# ============================================================================ materials
IMAGES = {}


def _image(path, non_color):
    if path not in IMAGES:
        img = bpy.data.images.load(path, check_existing=True)
        if non_color:
            img.colorspace_settings.name = "Non-Color"
        IMAGES[path] = img
    return IMAGES[path]


def pbr(name, tex, size=2.0, tint=None, rough=None, relief=0.004, bevel=0.01, fallback=(0.6, 0.6, 0.6)):
    """World-space, box-projected PBR material from a Poly Haven texture set.

    size   real-world size (m) one texture tile covers
    tint   RGB multiplier on the diffuse map
    rough  None = roughness map, float = constant, (lo, hi) = remapped map
    relief bump height in metres from the displacement map
    bevel  rounded-edge radius (Cycles shader bevel; catches edge highlights)
    """
    mat = bpy.data.materials.new(name)
    mat["web"] = json.dumps({"tex": tex, "tile": size, "tint": tint or (1, 1, 1),
                             "rough": rough if isinstance(rough, (int, float)) else
                             (sum(rough) / 2 if isinstance(rough, tuple) else 0.75)})
    ensure_nodes(mat)
    nt, N, L = mat.node_tree, mat.node_tree.nodes, mat.node_tree.links
    bsdf = N.get("Principled BSDF")
    folder = os.path.join(ASSETS, "textures", tex)
    geo = N.new("ShaderNodeNewGeometry")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0 / size,) * 3
    L.new(geo.outputs["Position"], mp.inputs["Vector"])

    def tex_node(fname, non_color):
        fp = os.path.join(folder, fname)
        if not os.path.exists(fp):
            return None
        n = N.new("ShaderNodeTexImage")
        n.image = _image(fp, non_color)
        n.projection, n.projection_blend = "BOX", 0.25
        L.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n

    d = tex_node("diff.jpg", False)
    if d:
        col = d.outputs["Color"]
        if tint:
            vm = N.new("ShaderNodeVectorMath")
            vm.operation = "MULTIPLY"
            L.new(col, vm.inputs[0])
            vm.inputs[1].default_value = tint
            col = vm.outputs["Vector"]
        L.new(col, bsdf.inputs["Base Color"])
    else:
        c = tint or (1, 1, 1)
        bsdf.inputs["Base Color"].default_value = (*(a * b for a, b in zip(fallback, c)), 1)

    rm = tex_node("rough.jpg", True) if not isinstance(rough, (int, float)) else None
    if rm and isinstance(rough, tuple):
        mr = N.new("ShaderNodeMapRange")
        L.new(rm.outputs["Color"], mr.inputs["Value"])
        mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = rough
        L.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    elif rm:
        L.new(rm.outputs["Color"], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = rough if isinstance(rough, (int, float)) else 0.7

    normal = None
    if CYCLES and bevel:
        bv = N.new("ShaderNodeBevel")
        bv.inputs["Radius"].default_value = bevel
        set_props(bv, samples=6)
        normal = bv.outputs["Normal"]
    h = tex_node("disp.jpg", True)
    if h and relief:
        b = N.new("ShaderNodeBump")
        b.inputs["Strength"].default_value = 1.0
        b.inputs["Distance"].default_value = relief
        L.new(h.outputs["Color"], b.inputs["Height"])
        if normal:
            L.new(normal, b.inputs["Normal"])
        normal = b.outputs["Normal"]
    if normal:
        L.new(normal, bsdf.inputs["Normal"])
    return mat


def solid(name, color, rough=0.5, metal=0.0, transmission=0.0, ior=1.45, emission=None,
          strength=0.0, alpha=1.0, coat=0.0, bevel=0.0):
    mat = bpy.data.materials.new(name)
    mat["web"] = json.dumps({"color": color, "rough": rough, "metal": metal, "glass": transmission > 0.5,
                             "emit": emission, "strength": strength})
    ensure_nodes(mat)
    N, L = mat.node_tree.nodes, mat.node_tree.links
    b = N.get("Principled BSDF")

    def put(names, val):
        for n in names:
            if n in b.inputs:
                b.inputs[n].default_value = val
                return

    put(["Base Color"], (*color, 1.0))
    put(["Roughness"], rough)
    put(["Metallic"], metal)
    put(["IOR"], ior)
    put(["Transmission Weight", "Transmission"], transmission)
    put(["Coat Weight", "Clearcoat"], coat)
    put(["Alpha"], alpha)
    if emission:
        put(["Emission Color", "Emission"], (*emission, 1.0))
        put(["Emission Strength"], strength)
    if CYCLES and bevel:
        bv = N.new("ShaderNodeBevel")
        bv.inputs["Radius"].default_value = bevel
        L.new(bv.outputs["Normal"], b.inputs["Normal"])
    return mat


def fabric(name, color):
    """Sheer curtain: diffuse mixed with translucency so daylight glows through."""
    mat = bpy.data.materials.new(name)
    mat["web"] = json.dumps({"color": color, "rough": 0.9, "metal": 0, "fabric": True})
    ensure_nodes(mat)
    N, L = mat.node_tree.nodes, mat.node_tree.links
    out = N.get("Material Output")
    b = N.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = 0.9
    set_props(b.inputs.get("Sheen Weight") or b, default_value=0.5)
    tr = N.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (*color, 1)
    mix = N.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.4
    L.new(b.outputs[0], mix.inputs[1])
    L.new(tr.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def grass_hair_mat():
    mat = bpy.data.materials.new("grass_hair")
    ensure_nodes(mat)
    N, L = mat.node_tree.nodes, mat.node_tree.links
    b = N.get("Principled BSDF")
    b.inputs["Roughness"].default_value = 0.55
    hi = N.new("ShaderNodeHairInfo")
    ramp = N.new("ShaderNodeValToRGB")
    e = ramp.color_ramp.elements
    e[0].color = (0.035, 0.085, 0.012, 1)
    e[1].color = (0.12, 0.2, 0.03, 1)
    L.new(hi.outputs["Random"], ramp.inputs["Fac"])
    # darker roots, lighter tips
    mx = N.new("ShaderNodeVectorMath")
    mx.operation = "SCALE"
    mr = N.new("ShaderNodeMapRange")
    L.new(hi.outputs["Intercept"], mr.inputs["Value"])
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 0.45, 1.15
    L.new(ramp.outputs["Color"], mx.inputs[0])
    L.new(mr.outputs["Result"], mx.inputs["Scale"])
    L.new(mx.outputs["Vector"], b.inputs["Base Color"])
    set_props(b.inputs.get("Subsurface Weight") or b, default_value=0.15)
    return mat


WARM = (1.0, 0.72, 0.42)
M = {
    "stucco":   pbr("stucco", "beige_wall_002", size=2.4, tint=(1.0, 0.93, 0.82), relief=0.004),
    "charcoal": pbr("charcoal", "white_stucco", size=2.0, tint=(0.115, 0.12, 0.125), relief=0.003),
    "plaster":  pbr("plaster", "white_stucco", size=2.0, tint=(0.66, 0.65, 0.62), relief=0.003),
    "rcc":      pbr("rcc", "concrete_wall_008", size=2.5, tint=(0.72, 0.77, 0.86), relief=0.005),
    "brick":    pbr("brick", "red_brick_03", size=1.1, relief=0.012, bevel=0),
    "wood":     pbr("wood", "oak_veneer_01", size=1.4, tint=(0.8, 0.62, 0.45), rough=(0.3, 0.55), relief=0.0005),
    "door":     pbr("door", "fine_grained_wood", size=1.6, tint=(1.25, 1.0, 0.8), rough=(0.25, 0.45), relief=0.0005),
    "pavers":   pbr("pavers", "concrete_pavers_02", size=1.6, tint=(1.05, 1.0, 0.95), relief=0.01),
    "tiles":    pbr("tiles", "concrete_tiles", size=1.8, relief=0.004),
    "asphalt":  pbr("asphalt", "asphalt_02", size=5.0, tint=(0.8, 0.8, 0.82), relief=0.006, bevel=0),
    "lawn":     pbr("lawn", "grass_ground", size=3.0, tint=(0.62, 0.95, 0.42), relief=0.01, bevel=0),
    "soil":     pbr("soil", "brown_mud_dry", size=2.5, relief=0.03, bevel=0),
    "sand":     pbr("sand", "brown_mud_dry", size=1.5, tint=(1.6, 1.35, 1.0), relief=0.01, bevel=0),
    "interior": solid("interior", (0.78, 0.74, 0.68), rough=0.85),
    "ceiling":  solid("ceiling", (0.86, 0.85, 0.82), rough=0.9),
    "floor_in": solid("floor_in", (0.62, 0.58, 0.52), rough=0.18),
    "alu":      solid("alu", (0.05, 0.052, 0.056), rough=0.32, metal=0.85, bevel=0.004),
    "metal":    solid("metal", (0.035, 0.035, 0.04), rough=0.4, metal=0.7, bevel=0.004),
    "copper":   solid("copper", (0.5, 0.27, 0.15), rough=0.38, metal=0.9, bevel=0.004),
    "glass":    solid("glass", (0.78, 0.86, 0.86), rough=0.02, transmission=1.0, ior=1.52),
    "groove":   solid("groove", (0.02, 0.02, 0.022), rough=0.8),
    "scaffold": solid("scaffold", (0.55, 0.56, 0.58), rough=0.45, metal=0.85),
    "board":    pbr("board", "oak_veneer_01", size=1.0, tint=(0.75, 0.6, 0.42), rough=0.85, relief=0.002, bevel=0),
    "rebar":    solid("rebar", (0.22, 0.12, 0.07), rough=0.6, metal=0.7),
    "pooltile": solid("pooltile", (0.42, 0.66, 0.70), rough=0.15),
    "water":    solid("water", (0.75, 0.9, 0.92), rough=0.01, transmission=1.0, ior=1.33),
    "curtain":  fabric("curtain", (0.72, 0.72, 0.64)),
    "lamp":     solid("lamp", (0.9, 0.88, 0.84), emission=WARM, strength=40.0 if DUSK else 0.3),
    "downlight": solid("downlight", (1, 1, 1), emission=WARM, strength=60.0 if DUSK else 0.0),
    "grass_hair": grass_hair_mat(),
}


# ============================================================================ geometry
class Batch:
    """Accumulates axis-aligned boxes per (name, material) and emits one mesh each."""

    def __init__(self, coll):
        self.coll, self.parts = coll, {}

    def box(self, key, mat, x0, x1, y0, y1, z0, z1):
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        if EXPORT:
            k = (CUR["tag"], CUR["zone"], mat.name)
            WEB["parts"].setdefault(k, []).extend(round(c, 3) for c in (x0, x1, y0, y1, z0, z1))
            return
        e = self.parts.setdefault((key, mat.name), [mat, [], []])
        v, f, i = e[1], e[2], len(e[1])
        v += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
              (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        f += [(i, i + 3, i + 2, i + 1), (i + 4, i + 5, i + 6, i + 7), (i, i + 1, i + 5, i + 4),
              (i + 1, i + 2, i + 6, i + 5), (i + 2, i + 3, i + 7, i + 6), (i + 3, i, i + 4, i + 7)]

    def flush(self):
        for (key, _), (mat, v, f) in self.parts.items():
            me = bpy.data.meshes.new(key)
            me.from_pydata(v, [], f)
            me.update()
            me.materials.append(mat)
            self.coll.objects.link(bpy.data.objects.new(key, me))
        self.parts.clear()


def mesh_object(coll, name, verts, faces, mat, smooth=False):
    if EXPORT and coll is not None:
        WEB["meshes"].append({"t": CUR["tag"], "z": CUR["zone"], "m": mat.name, "smooth": smooth,
                              "v": [round(c, 3) for p in verts for c in p], "f": [i for f in faces for i in f]})
        return None
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


# ============================================================================ asset library
class Library:
    """Imports Poly Haven glTF models once; places linked collection instances."""

    def __init__(self):
        self.root = bpy.data.collections.new("LIB")
        scene.collection.children.link(self.root)
        bpy.context.view_layer.layer_collection.children["LIB"].exclude = True
        self.cache = {}

    def variants(self, aid):
        if aid in self.cache:
            return self.cache[aid]
        path = os.path.join(ASSETS, "models", aid, aid + ".gltf")
        self.cache[aid] = []
        if not os.path.exists(path):
            log("asset missing (run `npm run assets`):", aid)
            return []
        t = time.time()
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        meshes = [o for o in new if o.type == "MESH"]
        bounds = []
        for o in meshes:
            if o.data.users > 1:
                o.data = o.data.copy()
            mw = o.matrix_world.copy()
            o.parent = None
            o.data.transform(mw)
            o.matrix_world = Matrix.Identity(4)
            co = np.empty(len(o.data.vertices) * 3, dtype=np.float32)
            o.data.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            bounds.append((co.min(0), co.max(0)))
        for o in new:
            if o.type != "MESH":
                bpy.data.objects.remove(o)
        # objects whose footprints overlap belong to the same plant/prop (pot + leaves...)
        group = list(range(len(meshes)))

        def find(i):
            while group[i] != i:
                i = group[i]
            return i

        for i in range(len(meshes)):
            for j in range(i + 1, len(meshes)):
                (a0, a1), (b0, b1) = bounds[i], bounds[j]
                if a0[0] < b1[0] + 0.05 and b0[0] < a1[0] + 0.05 and a0[1] < b1[1] + 0.05 and b0[1] < a1[1] + 0.05:
                    group[find(j)] = find(i)
        groups = {}
        for i in range(len(meshes)):
            groups.setdefault(find(i), []).append(i)
        for n, idx in enumerate(groups.values()):
            lo = np.min([bounds[i][0] for i in idx], 0)
            hi = np.max([bounds[i][1] for i in idx], 0)
            off = Matrix.Translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
            c = bpy.data.collections.new(f"{aid}_{n}")
            self.root.children.link(c)
            for i in idx:
                o = meshes[i]
                o.data.transform(off)
                for uc in list(o.users_collection):
                    uc.objects.unlink(o)
                c.objects.link(o)
            c["size"] = [float(v) for v in (hi - lo)]
            self.cache[aid].append(c)
        log(f"asset {aid}: {len(self.cache[aid])} variant(s), {time.time() - t:.1f}s")
        return self.cache[aid]

    def place(self, coll, aid, x, y, z=0.0, rot=None, scale=1.0, variant=None):
        vs = self.variants(aid)
        if not vs:
            return None
        c = vs[variant % len(vs)] if variant is not None else random.choice(vs)
        rot = random.uniform(0, 2 * math.pi) if rot is None else rot
        if EXPORT:
            WEB["instances"].append({"t": CUR["tag"], "z": CUR["zone"], "a": c.name,
                                     "p": [round(x, 3), round(y, 3), round(z, 3)], "r": round(rot, 3), "s": round(scale, 3)})
            return None
        e = bpy.data.objects.new(aid, None)
        e.instance_type, e.instance_collection = "COLLECTION", c
        e.location = (x, y, z)
        e.rotation_euler = (0, 0, rot)
        e.scale = (scale,) * 3
        coll.objects.link(e)
        return e


LIB = Library()


def add_grass(ob, density=260):
    """Particle-hair lawn on a flat surface object."""
    area = sum(p.area for p in ob.data.polygons)
    ob.data.materials.append(M["grass_hair"])
    mod = ob.modifiers.new("grass", "PARTICLE_SYSTEM")
    ps = mod.particle_system.settings
    ps.type = "HAIR"
    ps.count = max(50, int(area * density))
    set_props(ps, emit_from="FACE", use_emit_random=True, render_type="PATH",
              material_slot="grass_hair", child_type="INTERPOLATED",
              rendered_child_count=14, child_nbr=1, child_percent=1, child_radius=0.12,
              clump_factor=0.0, roughness_1=0.01, roughness_1_size=0.4,
              roughness_endpoint=0.012, roughness_2=0.008, child_length=1.0,
              child_length_threshold=0.35,
              root_radius=1.0, tip_radius=0.0, radius_scale=0.003, use_close_tip=True)
    # hair length is stored as the normal velocity; set it last, randomise relative to it
    ps.hair_length = 0.08
    ps.factor_random = ps.normal_factor * 0.5
    mod.particle_system.seed = random.randint(0, 9999)


def leaf_material():
    """Glossy leaf with per-instance colour variation and back-lit translucency."""
    mat = bpy.data.materials.new("leaf")
    ensure_nodes(mat)
    N, L = mat.node_tree.nodes, mat.node_tree.links
    out, b = N.get("Material Output"), N.get("Principled BSDF")
    oi = N.new("ShaderNodeObjectInfo")
    ramp = N.new("ShaderNodeValToRGB")
    e = ramp.color_ramp.elements
    e[0].color = (0.018, 0.06, 0.012, 1)
    e[1].color = (0.07, 0.15, 0.025, 1)
    L.new(oi.outputs["Random"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.38
    tr = N.new("ShaderNodeBsdfTranslucent")
    L.new(ramp.outputs["Color"], tr.inputs["Color"])
    mix = N.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.25
    L.new(b.outputs[0], mix.inputs[1])
    L.new(tr.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    return mat


_LEAF = []


def leaf_object():
    """A small bent leaf, parked far below the ground; hedges instance it via particles."""
    if not _LEAF:
        w, l = 0.022, 0.06
        verts = [(0, 0, 0), (w, l * 0.35, 0.004), (0, l, 0.01), (-w, l * 0.35, 0.004), (0, l * 0.4, -0.003)]
        faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
        ob = mesh_object(scene.collection, "leaf", verts, faces, leaf_material(), smooth=True)
        ob.location = (0, 0, -1000)
        _LEAF.append(ob)
    return _LEAF[0]


def hedge(coll, x0, x1, y0, y1, z0, h, density=2600):
    """Clipped hedge: a dark core box covered in particle-instanced leaves."""
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z0 + h), (x1, y0, z0 + h), (x1, y1, z0 + h), (x0, y1, z0 + h)]
    faces = [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    if EXPORT and coll is not None:
        WEB["parts"].setdefault((CUR["tag"], CUR["zone"], "hedge"), []).extend(
            round(c, 3) for c in (x0, x1, y0, y1, z0, z0 + h))
        return None
    core = solid("hedge_core", (0.012, 0.03, 0.008), rough=0.9) if "hedge_core" not in M else M["hedge_core"]
    M["hedge_core"] = core
    ob = mesh_object(coll, "hedge", verts, faces, core)
    area = sum(p.area for p in ob.data.polygons)
    mod = ob.modifiers.new("leaves", "PARTICLE_SYSTEM")
    ps = mod.particle_system.settings
    ps.type = "HAIR"
    ps.count = int(area * density)
    set_props(ps, emit_from="FACE", use_emit_random=True, render_type="OBJECT",
              instance_object=leaf_object(), particle_size=1.0, size_random=0.5,
              use_rotations=True, rotation_mode="NOR", rotation_factor_random=0.7,
              phase_factor_random=2.0, use_render_emitter=True)
    ps.hair_length = 0.02
    mod.particle_system.seed = random.randint(0, 9999)
    return ob


# ============================================================================ villa
PL = 0.45           # plinth / ground-floor finished level
FF0, FF1 = 3.75, 6.85  # first floor: floor level, underside of terrace slab
TR0, TR1 = 7.05, 9.85  # terrace room
WALL = 0.23


class Villa:
    """One plot. `ox` shifts it along the street; `st` maps zone -> stage index."""

    def __init__(self, ox, st, number, main):
        self.ox, self.st, self.no, self.main = ox, st, number, main
        self.coll = bpy.data.collections.new(f"villa_{number}")
        ROOT.children.link(self.coll)
        self.b = Batch(self.coll)

    # ---- primitives (local plot coordinates) ----
    def s(self, zone):
        return self.st[zone]

    def box(self, key, mat, x0, x1, y0, y1, z0, z1):
        self.b.box(key, mat, x0 + self.ox, x1 + self.ox, y0, y1, z0, z1)

    def pieces(self, key, mat, axis, a0, a1, t0, t1, z0, z1, holes=(), ztop=None):
        """Wall slab along `axis` ('x' or 'y') with rectangular holes (a0, a1, z0, z1)."""
        def put(p0, p1, q0, q1):
            if ztop is not None:
                q1 = min(q1, ztop)
            if axis == "x":
                self.box(key, mat, p0, p1, t0, t1, q0, q1)
            else:
                self.box(key, mat, t0, t1, p0, p1, q0, q1)
        a = a0
        for h0, h1, hz0, hz1 in sorted(holes):
            put(a, h0, z0, z1)
            put(h0, h1, z0, hz0)
            put(h0, h1, hz1, z1)
            a = h1
        put(a, a1, z0, z1)

    def paint(self, zone, final):
        st = self.s(zone)
        if st >= R or (st >= FI and self.s("facade") >= FI):
            return M[final]
        return M["plaster"]

    def wall(self, zone, key, axis, a0, a1, t0, t1, z0, z1, holes=(), final="stucco", inner=0):
        """Zone-aware wall: RCC frame + brick during Structure, plaster/paint after.
        inner = +1/-1 puts an interior lining on the +t / -t face (finished floors)."""
        st = self.s(zone)
        if st <= F:
            return
        if st == S:
            beam = 0.45
            self.pieces(key + "_rcc", M["rcc"], axis, a0, a1, t0, t1, z1 - beam, z1)
            edges = [a0] + [v for h in sorted(holes) for v in (h[0], h[1])] + [a1]
            cols = [(a0, a0 + 0.3), (a1 - 0.3, a1)]
            for i in range(0, len(edges) - 1, 2):
                p0, p1 = edges[i], edges[i + 1]
                if p1 - p0 > 1.6:
                    m = (p0 + p1) / 2
                    cols.append((m - 0.15, m + 0.15))
            for c0, c1 in cols:
                self.pieces(key + "_rcc", M["rcc"], axis, c0, c1, t0, t1, z0, z1 - beam)
            self.pieces(key + "_brick", M["brick"], axis, a0, a1, t0 + 0.025, t1 - 0.025,
                        z0, z1 - beam, holes)
            for h0, h1, hz0, hz1 in holes:
                if hz1 < z1 - beam - 0.05:
                    self.pieces(key + "_rcc", M["rcc"], axis, h0 - 0.15, h1 + 0.15, t0, t1,
                                hz1, min(hz1 + 0.15, z1 - beam))
            return
        self.pieces(key, self.paint(zone, final), axis, a0, a1, t0, t1, z0, z1, holes)
        if inner:
            lt = (t1, t1 + 0.012) if inner > 0 else (t0 - 0.012, t0)
            self.pieces(key + "_lining", M["interior"], axis, a0, a1, lt[0], lt[1], z0, z1, holes)

    def slab(self, zone, key, x0, x1, y0, y1, z0, z1, final="stucco"):
        st = self.s(zone)
        if st <= F:
            return
        self.box(key, M["rcc"] if st == S else self.paint(zone, final), x0, x1, y0, y1, z0, z1)

    def glazing(self, zone, key, axis, a0, a1, t, z0, z1, panes=2, curtain=0):
        """Aluminium frame + glass in a hole; optional curtains on the interior side."""
        if self.s(zone) < FI:
            return
        fw, d = 0.055, 0.07
        alu, gl = M["alu"], M["glass"]
        for p0, p1, q0, q1 in [(a0, a1, z0, z0 + fw), (a0, a1, z1 - fw, z1),
                               (a0, a0 + fw, z0, z1), (a1 - fw, a1, z0, z1)]:
            self.pieces(key + "_frame", alu, axis, p0, p1, t - d / 2, t + d / 2, q0, q1)
        for i in range(1, panes):
            m = a0 + (a1 - a0) * i / panes
            self.pieces(key + "_frame", alu, axis, m - fw / 2, m + fw / 2, t - d / 2, t + d / 2, z0, z1)
        self.pieces(key + "_glass", gl, axis, a0 + fw, a1 - fw, t - 0.006, t + 0.006, z0 + fw, z1 - fw)
        if curtain and self.s(zone) >= R:
            ct = t + curtain * 0.18
            span = a1 - a0
            self.curtain(axis, a0 + 0.05, a0 + 0.05 + span * 0.24, ct, z0 + 0.02, z1 - 0.04)
            self.curtain(axis, a1 - 0.05 - span * 0.3, a1 - 0.05, ct, z0 + 0.02, z1 - 0.04)

    def curtain(self, axis, a0, a1, t, z0, z1, pleat=0.07, depth=0.06):
        n = max(2, int((a1 - a0) / pleat))
        verts, faces = [], []
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            dt = depth * (0.5 if i % 2 else -0.5)
            for z in (z0, z1):
                verts.append((a + self.ox, t + dt, z) if axis == "x" else (t + dt + self.ox, a, z))
        for i in range(n):
            faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
        mesh_object(self.coll, "curtain", verts, faces, M["curtain"], smooth=True)

    def railing(self, zone, key, axis, a0, a1, t, z0, h=1.05):
        if self.s(zone) < FI:
            return
        self.pieces(key + "_shoe", M["alu"], axis, a0, a1, t - 0.04, t + 0.04, z0, z0 + 0.09)
        self.pieces(key + "_glass", M["glass"], axis, a0, a1, t - 0.008, t + 0.008, z0 + 0.09, z0 + h - 0.05)
        rail = M["copper"] if self.s("facade") >= R else M["alu"]
        self.pieces(key + "_rail", rail, axis, a0, a1, t - 0.035, t + 0.035, z0 + h - 0.05, z0 + h)

    def scaffold(self, key, axis, a0, a1, t, side, z0, z1):
        """Two-row tube scaffold with boards at each lift, `side` = outward direction."""
        p = 0.048
        rows = [t + side * 0.35, t + side * 1.3]
        n = max(1, int((a1 - a0) / 1.8))
        lifts = [z0 + 0.15 + 2.0 * k for k in range(int((z1 - z0) / 2.0) + 1)]
        for rr in rows:
            for k in range(n + 1):
                a = a0 + (a1 - a0) * k / n
                self.pieces(key, M["scaffold"], axis, a, a + p, rr, rr + p, 0.0, z1 + 1.0)
            for z in lifts:
                self.pieces(key, M["scaffold"], axis, a0, a1 + p, rr, rr + p, z, z + p)
        lo, hi = sorted(rows)
        for z in lifts[1:]:
            if z < z1 - 0.3:
                self.pieces(key + "_boards", M["board"], axis, a0, a1, lo + p, hi, z + p, z + p + 0.04)

    def interior(self, zone, x0, x1, y0, y1, z0, z1):
        """Finished-room surfaces + warm light, visible through the glazing."""
        if self.s(zone) < FI:
            return
        self.box(zone + "_floorin", M["floor_in"], x0, x1, y0, y1, z0, z0 + 0.012)
        self.box(zone + "_ceil", M["ceiling"], x0, x1, y0, y1, z1 - 0.012, z1)
        if self.s(zone) >= R and (self.main or DUSK) and not EXPORT:
            ld = bpy.data.lights.new(zone + "_light", "AREA")
            ld.shape, ld.size, ld.size_y = "RECTANGLE", (x1 - x0) * 0.7, (y1 - y0) * 0.7
            ld.energy = (420 if DUSK else 110) * (x1 - x0) * (y1 - y0) / 60 * (1.0 if self.main else 0.7)
            ld.color = WARM
            lo = bpy.data.objects.new(zone + "_light", ld)
            lo.location = ((x0 + x1) / 2 + self.ox, (y0 + y1) / 2, z1 - 0.05)
            self.coll.objects.link(lo)

    # ---- zones ----
    def build(self):
        for zone, step in (("groundFloor", self.ground_floor), ("firstFloor", self.first_floor),
                           ("decks", self.terrace), ("facade", self.facade_details),
                           ("basement", self.basement), ("servantsQuarter", self.servants_quarter),
                           ("decks", self.decks_rear), ("landscape", self.landscape)):
            CUR["zone"] = zone
            step()
        CUR["zone"] = "site"
        self.b.flush()

    def ground_floor(self):
        z, st = "groundFloor", self.s("groundFloor")
        if st == F:
            for x in (-4.85, -1.6, 0.9, 4.85):
                for y in (-2.65, 1.2, 5.0, 8.85):
                    self.box("footing", M["rcc"], x - 0.55, x + 0.55, y - 0.55, y + 0.55, -0.05, 0.3)
                    for dx in (-0.1, 0.1):
                        for dy in (-0.1, 0.1):
                            self.box("rebar", M["rebar"], x + dx - 0.012, x + dx + 0.012,
                                     y + dy - 0.012, y + dy + 0.012, 0.3, 1.6)
            for y in (-2.65, 1.2, 5.0, 8.85):
                self.box("plinth_beam", M["rcc"], -5.0, 5.0, y - 0.15, y + 0.15, 0.05, 0.45)
            for x in (-4.85, -1.6, 0.9, 4.85):
                self.box("plinth_beam", M["rcc"], x - 0.15, x + 0.15, -2.8, 9.0, 0.05, 0.45)
            return
        pm = M["rcc"] if st == S else M["charcoal"]
        self.box("plinth", pm, -5.1, 0.9, -2.9, 9.1, 0, PL)
        self.box("plinth", pm, 0.9, 5.1, -0.7, 9.1, 0, PL)
        self.box("plinth", pm, 0.9, 2.6, -2.9, -0.7, 0, PL)
        sm = M["rcc"] if st < R else M["tiles"]
        for i, y0 in enumerate((-3.8, -3.5, -3.2)):
            self.box("steps", sm, 0.9, 2.6, y0, -2.9, 0, 0.15 * (i + 1))
        top = FF0 - 0.2
        self.wall(z, "gf_front", "x", -5.0, 0.8, -2.8, -2.57, PL, top, [(-4.4, -0.6, PL, 3.1)], "charcoal", +1)
        self.wall(z, "gf_return", "y", -2.8, -0.37, 0.8, 1.03, PL, top, (), "charcoal")
        self.wall(z, "gf_entry", "x", 0.8, 5.0, -0.6, -0.37, PL, top, [(1.3, 2.4, PL, 3.1)], "charcoal", +1)
        self.wall(z, "gf_left", "y", -2.8, 9.0, -5.0, -4.77, PL, top, [(2.0, 4.0, 1.2, 2.8)], "charcoal", +1)
        self.wall(z, "gf_right", "y", -0.6, 9.0, 4.77, 5.0, PL, top, [(3.0, 4.2, 1.2, 2.8)], "charcoal", -1)
        self.wall(z, "gf_rear", "x", -5.0, 5.0, 8.77, 9.0, PL, top, [(-3.6, 0.6, PL, 3.1), (2.0, 4.2, 1.2, 3.0)], "charcoal", -1)
        # carport side wall carrying the cantilevered first floor
        self.wall(z, "gf_carport", "y", -4.8, -0.6, 4.77, 5.0, 0.0, top, (), "charcoal")
        self.glazing(z, "gf_win", "x", -4.4, -0.6, -2.66, PL, 3.1, panes=3, curtain=+1)
        self.glazing(z, "gf_win", "y", 2.0, 4.0, -4.86, 1.2, 2.8, curtain=+1)
        self.glazing(z, "gf_win", "y", 3.0, 4.2, 4.86, 1.2, 2.8, curtain=-1)
        self.glazing(z, "gf_win", "x", -3.6, 0.6, 8.86, PL, 3.1, panes=3, curtain=-1)
        self.glazing(z, "gf_win", "x", 2.0, 4.2, 8.86, 1.2, 3.0, curtain=-1)
        if st >= R:
            self.box("door", M["door"], 1.32, 2.38, -0.53, -0.46, PL, 3.08)
            self.box("door_handle", M["metal"], 2.18, 2.22, -0.58, -0.53, 1.0, 2.4)
        elif st >= FI:
            self.pieces("door_frame", M["alu"], "x", 1.3, 2.4, -0.52, -0.45, PL, 3.1, [(1.36, 2.34, PL, 3.04)])
        self.interior(z, -4.77, 4.77, -2.57, 8.77, PL, top)
        # first-floor slab (cast with the ground-floor structure)
        slab_mat = M["rcc"] if self.s("firstFloor") <= S else self.paint("firstFloor", "stucco")
        self.box("ff_slab", slab_mat, -5.2, 5.2, -4.8, 9.0, top, FF0)
        if st == S:
            self.scaffold("gf_scaffold", "x", -5.2, 5.2, -4.8, -1, 0.0, top)

    def first_floor(self):
        z, st = "firstFloor", self.s("firstFloor")
        if st == F:
            return
        Z0, Z1 = FF0, FF1
        # balcony frame (left) — the signature deep box
        self.wall(z, "ff_fin", "y", -4.8, -2.6, -5.2, -4.75, Z0, Z1)
        self.wall(z, "ff_fin", "y", -4.8, -2.6, -0.05, 0.4, Z0, Z1)
        self.wall(z, "ff_fascia", "x", -4.75, -0.05, -4.8, -4.5, 6.25, Z1)
        self.wall(z, "ff_upstand", "x", -4.75, -0.05, -4.8, -4.6, Z0, Z0 + 0.18)
        self.wall(z, "ff_recess", "x", -4.75, -0.05, -2.6, -2.37, Z0, Z1, [(-4.3, -0.5, Z0, 6.1)], "charcoal", +1)
        if st >= FI:
            rm = self.paint(z, "charcoal")
            self.box("ff_recess_side", rm, -4.75, -4.73, -4.5, -2.6, Z0, 6.25)
            self.box("ff_recess_side", rm, -0.07, -0.05, -4.5, -2.6, Z0, 6.25)
        # solid front (right) with framed window
        self.wall(z, "ff_front", "x", 0.4, 5.2, -4.8, -4.57, Z0, Z1, [(1.6, 4.2, 4.3, 6.3)], "stucco", +1)
        self.wall(z, "ff_left", "y", -2.6, 9.0, -5.2, -4.97, Z0, Z1, [(1.0, 3.4, 4.2, 6.3)], "stucco", +1)
        self.wall(z, "ff_right", "y", -4.8, 9.0, 4.97, 5.2, Z0, Z1, [(1.5, 1.85, 4.0, 6.5), (4.5, 6.5, 4.2, 6.3)], "stucco", -1)
        self.wall(z, "ff_rear", "x", -5.2, 5.2, 8.77, 9.0, Z0, Z1, [(-4.0, -1.0, Z0, 6.2), (1.0, 4.0, 4.2, 6.3)], "stucco", -1)
        fm = M["rcc"] if st == S else self.paint(z, "charcoal")
        for x0, x1, z0, z1 in [(1.42, 4.38, 6.3, 6.48), (1.42, 4.38, 4.12, 4.3),
                               (1.42, 1.6, 4.12, 6.48), (4.2, 4.38, 4.12, 6.48)]:
            self.box("ff_winframe", fm, x0, x1, -5.15, -4.8, z0, z1)
        self.glazing(z, "ff_win", "x", -4.3, -0.5, -2.48, Z0, 6.1, panes=3, curtain=+1)
        self.glazing(z, "ff_win", "x", 1.6, 4.2, -4.66, 4.3, 6.3, curtain=+1)
        self.glazing(z, "ff_win", "y", 1.0, 3.4, -5.08, 4.2, 6.3, curtain=+1)
        self.glazing(z, "ff_win", "y", 1.5, 1.85, 5.08, 4.0, 6.5, panes=1)
        self.glazing(z, "ff_win", "y", 4.5, 6.5, 5.08, 4.2, 6.3, curtain=-1)
        self.glazing(z, "ff_win", "x", -4.0, -1.0, 8.86, Z0, 6.2, panes=2, curtain=-1)
        self.glazing(z, "ff_win", "x", 1.0, 4.0, 8.86, 4.2, 6.3, curtain=-1)
        self.interior(z, -4.97, 4.97, -2.37, 8.77, Z0, Z1)
        self.interior(z, 0.4, 4.97, -4.57, -2.37, Z0, Z1)
        # terrace slab + edge upstand (roof of the first floor)
        slab = M["rcc"] if st == S else self.paint(z, "stucco")
        self.box("tr_slab", slab, -5.2, 5.2, -4.8, 9.0, Z1, TR0)
        for x0, x1, y0, y1 in [(-5.2, 5.2, -4.8, -4.62), (-5.2, -5.02, -4.8, 9.0), (5.02, 5.2, -4.8, 9.0)]:
            self.box("tr_curb", slab, x0, x1, y0, y1, TR0, TR0 + 0.15)
        if st == S:
            self.scaffold("ff_scaffold", "x", -5.2, 5.2, -4.8, -1, FF0, TR0 + 1.0)
            self.scaffold("ff_scaffold", "y", -4.8, 9.0, -5.2, -1, FF0, TR0 + 1.0)
            self.scaffold("ff_scaffold", "y", -4.8, 9.0, 5.2, +1, FF0, TR0 + 1.0)

    def terrace(self):
        z, st = "decks", self.s("decks")
        if self.s("firstFloor") <= F or st == F:
            return
        self.wall(z, "tr_front", "x", 0.4, 5.2, -0.4, -0.17, TR0, TR1, [(1.0, 3.6, TR0, 9.35)], "stucco", +1)
        self.wall(z, "tr_left", "y", -0.4, 9.0, 0.4, 0.63, TR0, TR1, [(3.0, 5.5, 7.9, 9.4)], "stucco", +1)
        self.wall(z, "tr_right", "y", -0.4, 9.0, 4.97, 5.2, TR0, TR1, [(1.5, 1.85, 7.4, 9.6)], "stucco", -1)
        self.wall(z, "tr_rear", "x", 0.4, 5.2, 8.77, 9.0, TR0, TR1, [(2.0, 4.0, 7.9, 9.4)], "stucco", -1)
        self.slab(z, "tr_roof", 0.4, 5.2, -0.4, 9.0, TR1, TR1 + 0.2)
        self.wall(z, "tr_parapet", "x", -5.2, 0.4, 8.8, 9.0, TR0, TR0 + 1.0)
        self.glazing(z, "tr_win", "x", 1.0, 3.6, -0.28, TR0, 9.35, panes=2, curtain=+1)
        self.glazing(z, "tr_win", "y", 3.0, 5.5, 0.52, 7.9, 9.4, curtain=+1)
        self.glazing(z, "tr_win", "y", 1.5, 1.85, 5.08, 7.4, 9.6, panes=1)
        self.glazing(z, "tr_win", "x", 2.0, 4.0, 8.86, 7.9, 9.4, curtain=-1)
        self.interior(z, 0.63, 4.97, -0.17, 8.77, TR0, TR1)
        z0 = TR0 + 0.15
        self.railing(z, "tr_rail", "x", -5.12, 5.12, -4.71, z0)
        self.railing(z, "tr_rail", "y", -4.62, 8.8, -5.11, z0)
        self.railing(z, "tr_rail", "y", -4.62, -0.4, 5.11, z0)
        self.railing(z, "bal_rail", "x", -4.75, -0.05, -4.7, FF0 + 0.18, h=0.9)
        if st >= R:
            self.box("tr_tiles", M["tiles"], -5.02, 0.4, -4.62, 8.8, TR0, TR0 + 0.02)
            self.box("tr_tiles", M["tiles"], 0.4, 5.02, -4.62, -0.4, TR0, TR0 + 0.02)
            self.box("bal_deck", M["wood"], -4.75, -0.05, -4.6, -2.6, FF0, FF0 + 0.035)
            if self.main or random.random() < 0.6:
                LIB.place(self.coll, "outdoor_table_chair_set_01", self.ox - 2.6, -2.3, TR0 + 0.02, rot=0.3)
                for x, y in ((-4.6, -4.2), (4.6, -4.2), (-4.6, 8.3)):
                    LIB.place(self.coll, "potted_plant_02", self.ox + x, y, TR0 + 0.02, scale=1.2)
                for x in (-3.4, -1.8, 2.4):
                    LIB.place(self.coll, "planter_box_01", self.ox + x, -4.35, TR0 + 0.02, rot=0, scale=1.3)
                LIB.place(self.coll, "potted_plant_01", self.ox - 0.6, -4.25, FF0 + 0.035, scale=0.9)
                LIB.place(self.coll, "potted_plant_02", self.ox - 4.3, -3.0, FF0 + 0.035, scale=0.9)
        if st == S:
            self.scaffold("tr_scaffold", "x", 0.4, 5.2, -0.4, -1, TR0, TR1 + 1.0)

    def facade_details(self):
        fa = self.s("facade")
        gf, ff, de = self.s("groundFloor"), self.s("firstFloor"), self.s("decks")
        if fa < R:
            return
        if gf >= FI:
            # entrance canopy
            self.box("canopy", M["metal"], 0.6, 4.6, -6.1, -4.8, FF0 - 0.3, FF0 - 0.22)
            # grooved cladding on the carport wall
            for k in range(7):
                zz = PL + 0.42 * (k + 1)
                self.box("groove", M["groove"], 2.6, 4.77, -0.615, -0.6, zz, zz + 0.022)
            for x in (0.95, 2.75):
                self.box("walllight", M["metal"], x - 0.06, x + 0.06, -0.72, -0.6, 2.55, 2.85)
                self.box("walllight_glow", M["lamp"], x - 0.045, x + 0.045, -0.73, -0.72, 2.6, 2.8)
        if ff >= FI:
            self.box("soffit", M["wood"], -4.75, -0.05, -4.5, -2.6, 6.2, 6.25)
            for x in (-3.9, -2.4, -0.9):
                self.box("downlight", M["downlight"], x - 0.06, x + 0.06, -3.6, -3.48, 6.185, 6.2)
                if DUSK and self.main and not EXPORT:
                    sd = bpy.data.lights.new("spot", "SPOT")
                    sd.energy, sd.spot_size, sd.spot_blend, sd.color = 120, math.radians(80), 0.6, WARM
                    so = bpy.data.objects.new("spot", sd)
                    so.location = (x + self.ox, -3.54, 6.15)
                    self.coll.objects.link(so)
        if de >= FI:
            for x0, x1, y0, y1 in [(0.32, 5.28, -0.48, -0.3), (0.32, 5.28, 8.9, 9.08),
                                   (0.32, 0.5, -0.48, 9.08), (5.1, 5.28, -0.48, 9.08)]:
                self.box("coping", M["copper"], x0, x1, y0, y1, TR1 + 0.2, TR1 + 0.26)

    def basement(self):
        """Sunken light court behind the house (the basement's daylight)."""
        st = self.s("basement")
        x0, x1, y0, y1, zb = -4.6, -1.8, 9.2, 11.2, -3.2
        wm = M["soil"] if st == F else (M["rcc"] if st <= FI else M["charcoal"])
        self.box("bsm_floor", M["soil"] if st == F else (M["rcc"] if st < R else M["tiles"]), x0, x1, y0, y1, zb - 0.2, zb)
        for a in [(x0 - 0.2, x0, y0, y1), (x1, x1 + 0.2, y0, y1), (x0 - 0.2, x1 + 0.2, y1, y1 + 0.2)]:
            self.box("bsm_wall", wm, a[0], a[1], a[2], a[3], zb, 0.02)
        if st >= FI:
            self.railing("basement", "bsm_rail", "x", x0, x1, y1 + 0.1, 0.02)
            self.railing("basement", "bsm_rail", "y", y0, y1, x0 - 0.1, 0.02)
            self.railing("basement", "bsm_rail", "y", y0, y1, x1 + 0.1, 0.02)
        if st >= R:
            LIB.place(self.coll, "potted_plant_01", self.ox - 2.4, 10.5, zb)

    def servants_quarter(self):
        z, st = "servantsQuarter", self.s("servantsQuarter")
        x0, x1, y0, y1 = -5.6, -2.2, 14.2, 17.6
        if st == F:
            for x in (x0 + 0.2, x1 - 0.2):
                for y in (y0 + 0.2, y1 - 0.2):
                    self.box("sq_footing", M["rcc"], x - 0.4, x + 0.4, y - 0.4, y + 0.4, -0.05, 0.25)
            return
        self.box("sq_plinth", M["rcc"] if st == S else M["charcoal"], x0 - 0.05, x1 + 0.05, y0 - 0.05, y1 + 0.05, 0, 0.3)
        self.wall(z, "sq_front", "x", x0, x1, y0, y0 + WALL, 0.3, 3.2, [(-4.9, -4.0, 0.3, 2.4), (-3.5, -2.6, 1.2, 2.4)], "stucco", +1)
        self.wall(z, "sq_side", "y", y0, y1, x0, x0 + WALL, 0.3, 3.2)
        self.wall(z, "sq_side", "y", y0, y1, x1 - WALL, x1, 0.3, 3.2)
        self.wall(z, "sq_rear", "x", x0, x1, y1 - WALL, y1, 0.3, 3.2)
        self.slab(z, "sq_roof", x0 - 0.1, x1 + 0.1, y0 - 0.3, y1 + 0.1, 3.2, 3.4)
        self.glazing(z, "sq_win", "x", -3.5, -2.6, y0 + 0.1, 1.2, 2.4, panes=1)
        if st >= R:
            self.box("sq_door", M["door"], -4.88, -4.02, y0 + 0.05, y0 + 0.1, 0.3, 2.38)
        if st == S:
            self.scaffold("sq_scaffold", "x", x0, x1, y0, -1, 0.3, 3.4)

    def decks_rear(self):
        """Raised poolside deck with a plunge pool (decks zone)."""
        st = self.s("decks")
        if st == F:
            return
        x0, x1, y0, y1 = -1.2, 5.6, 10.4, 16.0
        px0, px1, py0, py1 = 0.4, 4.8, 11.2, 15.2
        dm = M["rcc"] if st <= FI else M["wood"]
        top = 0.45
        for a in [(x0, x1, y0, py0), (x0, x1, py1, y1), (x0, px0, py0, py1), (px1, x1, py0, py1)]:
            self.box("deck", dm, a[0], a[1], a[2], a[3], 0, top)
        if st >= FI:
            t = 0.02
            self.box("pool_floor", M["pooltile"], px0, px1, py0, py1, 0, 0.05)
            for a in [(px0, px1, py0, py0 + t), (px0, px1, py1 - t, py1), (px0, px0 + t, py0, py1), (px1 - t, px1, py0, py1)]:
                self.box("pool_wall", M["pooltile"], a[0], a[1], a[2], a[3], 0.05, top - 0.01)
            for a in [(px0 - 0.25, px1 + 0.25, py0 - 0.25, py0), (px0 - 0.25, px1 + 0.25, py1, py1 + 0.25),
                      (px0 - 0.25, px0, py0, py1), (px1, px1 + 0.25, py0, py1)]:
                self.box("coping_stone", M["tiles"], a[0], a[1], a[2], a[3], top, top + 0.04)
        else:
            self.box("pool_floor", M["rcc"], px0, px1, py0, py1, 0, 0.05)
        if st >= R:
            self.box("water", M["water"], px0 + 0.02, px1 - 0.02, py0 + 0.02, py1 - 0.02, 0.05, top - 0.08)
            if self.main:
                LIB.place(self.coll, "outdoor_table_chair_set_01", self.ox + 2.6, 15.7, top + 0.04, rot=1.57)

    def landscape(self):
        st = self.s("landscape")
        ox = self.ox
        # ---- base ground of the plot (soil), with a hole for the basement court ----
        base = [(-6.2, 6.2, -7.6, 9.2), (-6.2, -4.8, 9.2, 18.1), (-1.6, 6.2, 9.2, 18.1), (-4.8, -1.6, 11.4, 18.1)]
        for x0, x1, y0, y1 in base:
            self.box("ground", M["soil"], x0, x1, y0, y1, -0.06, 0.02)
        # ---- compound walls ----
        if st == F:
            self.box("wall_footing", M["rcc"], -6.2, 6.2, -6.85, -6.55, 0.02, 0.2)
        else:
            wm = M["brick"] if st == S else M["charcoal"]
            for x0, x1, h in [(-6.2, 0.75, 1.35), (0.75, 0.95, 1.7), (1.85, 2.45, 1.7), (5.85, 6.2, 1.7)]:
                self.box("cwall", wm, x0, x1, -6.8, -6.6, 0, h)
            self.box("cwall", wm, 6.1, 6.3, -6.6, 18.1, 0, 1.8)
            self.box("cwall", wm, -6.2, 6.2, 17.9, 18.1, 0, 1.8)
            if st >= R:
                self.box("cwall_cap", M["copper"], -6.22, 0.77, -6.83, -6.57, 1.35, 1.38)
                for x0, x1 in [(0.73, 0.97), (1.83, 2.47), (5.83, 6.22)]:
                    self.box("pillar_lamp", M["lamp"], x0 + 0.04, x1 - 0.04, -6.78, -6.62, 1.7, 1.78)
                    self.box("pillar_cap", M["metal"], x0, x1, -6.82, -6.58, 1.78, 1.82)
                # sliding car gate: horizontal wood slats in a metal frame
                for k in range(9):
                    zz = 0.12 + k * 0.15
                    self.box("gate", M["wood"], 2.45, 5.85, -6.74, -6.68, zz, zz + 0.11)
                self.pieces("gate_frame", M["metal"], "x", 2.45, 5.85, -6.75, -6.67, 0.05, 1.5, [(2.5, 5.8, 0.1, 1.45)])
                for k in range(8):
                    zz = 0.12 + k * 0.15
                    self.box("pgate", M["wood"], 0.95, 1.85, -6.74, -6.68, zz, zz + 0.11)
                # number plate (the web app draws its own villa number)
                self.box("plate", M["copper"], 1.9, 2.4, -6.83, -6.8, 0.75, 1.3)
            if st >= R and not EXPORT:
                cu = bpy.data.curves.new("villa_no", "FONT")
                cu.body, cu.size, cu.extrude = self.no, 0.3, 0.004
                cu.align_x, cu.align_y = "CENTER", "CENTER"
                cu.materials.append(M["groove"])
                to = bpy.data.objects.new("villa_no", cu)
                to.location = (ox + 2.15, -6.836, 1.02)
                to.rotation_euler = (math.radians(90), 0, 0)
                self.coll.objects.link(to)
        # ---- surfaces ----
        if st >= FI:
            self.box("pavers", M["pavers"], 2.45, 6.1, -6.6, -0.6, 0, 0.12)
            self.box("pavers", M["pavers"], 0.95, 1.85, -6.6, -3.8, 0, 0.12)
            self.box("pavers", M["pavers"], -1.2, 5.6, 16.0, 17.9, 0, 0.12)
        if st >= R:
            lawns = [(-6.1, 0.95, -6.6, -2.9), (-6.1, -4.8, 9.1, 17.9), (-1.6, -1.2, 9.1, 17.9),
                     (-4.8, -1.6, 11.4, 17.9), (-1.2, 6.1, 9.1, 10.4), (5.6, 6.1, 10.4, 17.9), (-2.2, -1.2, 16.0, 17.9)]
            for x0, x1, y0, y1 in lawns:
                self.box("lawn_soil", M["lawn"], x0, x1, y0, y1, 0, 0.1)
                if EXPORT:
                    continue
                ob = mesh_object(self.coll, "lawn", [(x0 + ox, y0, 0.1), (x1 + ox, y0, 0.1), (x1 + ox, y1, 0.1), (x0 + ox, y1, 0.1)],
                                 [(0, 1, 2, 3)], M["lawn"])
                add_grass(ob, density=260 if self.main else 120)
            self.planting()
        elif st <= S and self.main:
            # site material stacks
            self.box("brick_stack", M["brick"], -5.4, -4.2, -6.0, -5.2, 0.02, 0.95)
            self.box("brick_stack", M["brick"], -3.9, -2.9, -6.0, -5.3, 0.02, 0.7)
            self.sand_pile(-1.4, -5.0, 1.6, 0.9)

    def planting(self):
        """Finished landscape: clipped hedges, tropical clumps, shrubs and a feature tree."""
        ox, P = self.ox, LIB.place
        tropical = (("anthurium_botany_01", (0, 1, 2), 2.0), ("calathea_orbifolia_01", (0, 1, 2), 2.2),
                    ("fern_02", (1, 2), 1.7))

        def clump(x, y, z=0.1, big=1.0):
            aid, vs, sc = random.choice(tropical)
            P(self.coll, aid, ox + x, y, z, variant=random.choice(vs), scale=sc * big * random.uniform(0.85, 1.15))

        # street-side planter outside the compound wall
        self.box("planter", M["soil"], -6.2, 6.2, -7.55, -6.8, 0, 0.18)
        hedge(self.coll, ox - 6.1, ox + 0.6, -7.3, -6.88, 0.18, 0.75)
        hedge(self.coll, ox + 5.9, ox + 6.15, -7.3, -6.88, 0.18, 0.75)
        for x in np.arange(-5.8, 0.6, 0.55):
            P(self.coll, "periwinkle_plant", ox + float(x) + random.uniform(-0.1, 0.1), -7.42, 0.18,
              scale=random.uniform(1.0, 1.4))
        # inside the wall: shrubs rising above it, tropical clumps along the house
        for x in (-5.4, -3.2, -1.0):
            P(self.coll, "searsia_lucida", ox + x, -6.05, 0.1, variant=1, scale=random.uniform(0.95, 1.2))
        for x, y in ((-4.6, -3.35), (-3.4, -3.3), (-1.4, -3.35), (-0.3, -3.3), (-5.7, -4.6), (0.5, -4.4)):
            clump(x, y)
        P(self.coll, "jacaranda_tree", ox - 4.2, -5.0, 0.1, scale=0.24)
        P(self.coll, "potted_plant_01", ox + 2.45, -1.0, PL)
        P(self.coll, "potted_plant_02", ox + 1.15, -2.65, PL)
        P(self.coll, "potted_plant_02", ox + 4.55, -1.0, 0.12)
        # rear garden borders
        hedge(self.coll, ox - 6.0, ox + 6.0, 17.35, 17.85, 0.1, 1.4)
        P(self.coll, "searsia_burchellii", ox - 0.2, 16.9, 0.1, rot=0, scale=0.42)
        for x, y in ((-5.6, 12.8), (5.6, 10.9), (5.6, 17.0)):
            P(self.coll, "searsia_lucida", ox + x, y, 0.1, variant=random.choice((0, 1)), scale=0.7)
        for x, y in ((-0.9, 10.8), (-0.9, 12.6), (5.8, 13.4), (5.8, 14.6), (-1.6, 15.6)):
            clump(x, y)

    def sand_pile(self, x, y, r, h, n=24):
        verts = [(x + self.ox, y, h + 0.02)]
        for i in range(n):
            a = 2 * math.pi * i / n
            rr = r * random.uniform(0.85, 1.1)
            verts.append((x + self.ox + rr * math.cos(a), y + rr * math.sin(a), 0.02))
        faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
        mesh_object(self.coll, "sand", verts, faces, M["sand"], smooth=True)


# ============================================================================ site
STREET_LAMPS = []


def street_lamp(b, x, y, h=4.2):
    """Modern pole lamp: slim dark pole, flat disc head with a glowing underside."""
    b.box("lamp_pole", M["metal"], x - 0.05, x + 0.05, y - 0.05, y + 0.05, 0.15, h)
    b.box("lamp_base", M["metal"], x - 0.12, x + 0.12, y - 0.12, y + 0.12, 0.15, 0.45)
    b.box("lamp_head", M["metal"], x - 0.32, x + 0.32, y - 0.32, y + 0.32, h, h + 0.06)
    b.box("lamp_glow", M["lamp"], x - 0.26, x + 0.26, y - 0.26, y + 0.26, h - 0.02, h)
    STREET_LAMPS.append((x, y, h))


def build_site(xs0, xs1):
    site = bpy.data.collections.new("site")
    ROOT.children.link(site)
    b = Batch(site)
    big = 400
    # ground around the plots (plots supply their own ground)
    b.box("field", M["lawn"], -big, big, 18.1, big, -0.06, 0.0)
    b.box("field", M["lawn"], -big, xs0, -7.6, 18.1, -0.06, 0.0)
    b.box("field", M["lawn"], xs1, big, -7.6, 18.1, -0.06, 0.0)
    b.box("field", M["lawn"], -big, big, -big, -19.4, -0.06, 0.0)
    # street: footpaths, kerbs, asphalt
    b.box("footpath", M["tiles"], -big, big, -9.0, -7.6, -0.06, 0.15)
    b.box("kerb", M["rcc"], -big, big, -9.18, -9.0, -0.06, 0.17)
    b.box("road", M["asphalt"], -big, big, -16.8, -9.18, -0.08, 0.02)
    b.box("kerb", M["rcc"], -big, big, -17.0, -16.8, -0.06, 0.17)
    b.box("footpath", M["tiles"], -big, big, -19.4, -17.0, -0.06, 0.15)
    for k in range(-60, 61):  # lane markings
        x = k * 6.0
        b.box("marking", M["ceiling"], x, x + 3.0, -13.07, -12.93, 0.02, 0.0215)
    b.flush()
    # street lamps + street trees
    lamps = Batch(site)
    for k in range(int(xs0 // 12.4) - 1, int(xs1 // 12.4) + 2):
        for x, y in ((k * 12.4 + 6.2, -8.35), (k * 12.4, -18.1)):
            street_lamp(lamps, x, y)
    lamps.flush()
    # mature trees behind the row (between roofs) and framing the street
    for x in np.arange(xs0 - 6.2, xs1 + 12.0, 12.4):
        LIB.place(site, "jacaranda_tree", float(x) + random.uniform(-1.5, 1.5), 37.0 + random.uniform(-1, 3), 0,
                  scale=random.uniform(0.75, 0.9))
    for x in (xs0 - 4.0, xs1 + 3.0):
        LIB.place(site, "jacaranda_tree", x, 6.0, 0, scale=0.7)
    return site


# ============================================================================ web export
def _srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def _save_image(img, path, fmt, quality=82):
    img.filepath_raw, img.file_format = path, fmt
    try:
        img.save(quality=quality)
    except TypeError:
        img.save()


def export_texture(name, spec, path, size=1024):
    """Tinted diffuse map for the web (tint baked in, since glTF-style viewers have no node graph)."""
    src = os.path.join(ASSETS, "textures", spec["tex"], "diff.jpg")
    img = bpy.data.images.load(src)
    img.scale(size, size)
    px = np.empty(size * size * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    lin = _srgb_to_lin(px[:, :3]) * np.array(spec["tint"], dtype=np.float32)
    px[:, :3] = _lin_to_srgb(np.clip(lin, 0, 1))
    out = bpy.data.images.new(name + "_web", size, size, alpha=False)
    out.pixels.foreach_set(px.ravel())
    _save_image(out, path, "WEBP")


def export_panorama(src, path, tint=(1, 1, 1), gain=1.0, size=(2048, 1024)):
    """Resized (optionally tinted) equirectangular sky backdrop for the web."""
    img = bpy.data.images.load(src)
    img.scale(*size)
    px = np.empty(size[0] * size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    lin = _srgb_to_lin(px[:, :3]) * np.array(tint, dtype=np.float32) * gain
    px[:, :3] = _lin_to_srgb(np.clip(lin, 0, 1))
    out = bpy.data.images.new(os.path.basename(path), size[0], size[1], alpha=False)
    out.pixels.foreach_set(px.ravel())
    _save_image(out, path, "JPEG", 85)


def export_sprites(out_dir, names):
    """Orthographic, transparent renders of plants/props, used as crossed-quad sprites on the web."""
    global EXPORT
    EXPORT = False
    set_engine("EEVEE")
    r = scene.render
    r.film_transparent = True
    r.image_settings.file_format, r.image_settings.color_mode = "WEBP", "RGBA"
    set_props(r.image_settings, quality=85)
    scene.view_settings.view_transform, scene.view_settings.exposure = "Standard", 0.0
    set_props(scene.view_settings, look="None")
    w = bpy.data.worlds.new("sprite_sky")
    ensure_nodes(w)
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.62, 0.75, 1)
    scene.world = w
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    scene.collection.objects.link(sun)
    cd = bpy.data.cameras.new("spr")
    cd.type = "ORTHO"
    cam = bpy.data.objects.new("spr", cd)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    out = {}
    for cname in names:
        c = bpy.data.collections[cname]
        sx, sy, sz = c["size"]
        size = max(sx, sz) * 1.04
        e = bpy.data.objects.new("spr", None)
        e.instance_type, e.instance_collection = "COLLECTION", c
        scene.collection.objects.link(e)
        cd.ortho_scale = size
        cam.location = (0, -80, sz / 2)
        res = 1024 if sz > 4 else 512
        r.resolution_x = r.resolution_y = res
        rel = f"spr/{cname}.webp"
        r.filepath = os.path.join(out_dir, rel)
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(e)
        out[cname] = {"img": rel, "size": round(size, 3), "cy": round(sz / 2, 3)}
    # clipped-hedge texture: a 3 m panel of particle leaves seen face-on (Cycles: per-leaf colour)
    set_engine("CYCLES")
    scene.cycles.samples = 48
    r.film_transparent = False
    hedge(scene.collection, -2.0, 2.0, 0.0, 0.6, -0.5, 4.0, density=3200)
    cd.ortho_scale = 3.0
    cam.location = (0, -80, 1.5)
    r.image_settings.color_mode = "RGB"
    r.resolution_x = r.resolution_y = 512
    r.filepath = os.path.join(out_dir, "tex", "hedge.webp")
    bpy.ops.render.render(write_still=True)
    return out


def export_web(out_dir):
    t0 = time.time()
    for sub in ("tex", "spr", "sky"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    # geometry: the client villa once per uniform stage, finished neighbours, shared site
    for s_ in range(4):
        CUR["tag"] = f"s{s_}"
        random.seed(ARGS.seed)
        Villa(0.0, {z: s_ for z in ZONES}, ARGS.villa_no, True).build()
    for k in (-1, 1):
        CUR["tag"] = "nb"
        random.seed(ARGS.seed + k * 31)
        Villa(k * 12.4, READY, f"{8 + k:02d}", False).build()
    CUR["tag"], CUR["zone"] = "site", "site"
    random.seed(ARGS.seed)
    xs0, xs1 = -18.6, 18.6
    Batch(None).box("cwall", M["charcoal"], xs0 - 0.1, xs0 + 0.1, -6.8, 18.1, 0, 1.8)
    build_site(xs0, xs1)
    log(f"web geometry: {len(WEB['parts'])} parts, {len(WEB['meshes'])} meshes, "
        f"{len(WEB['instances'])} instances ({time.time() - t0:.1f}s)")

    # materials (+ tinted textures)
    used = {k[2] for k in WEB["parts"]} | {m["m"] for m in WEB["meshes"]}
    mats = {}
    for name in sorted(used):
        if name == "hedge":
            mats[name] = {"tex": "tex/hedge.webp", "tile": 3.0, "rough": 0.8}
            continue
        spec = json.loads(bpy.data.materials[name]["web"])
        if "tex" in spec:
            rel = f"tex/{name}.webp"
            export_texture(name, spec, os.path.join(out_dir, rel), 1024 if spec["tile"] >= 2.4 else 512)
            mats[name] = {"tex": rel, "tile": spec["tile"], "rough": spec["rough"]}
        else:
            mats[name] = spec
    # sky for image-based lighting
    for key, fname in (("day", "kloofendal_48d_partly_cloudy_puresky_4k.hdr"), ("dusk", "qwantani_dusk_2_puresky_2k.hdr")):
        src = os.path.join(ASSETS, "hdri", fname)
        if os.path.exists(src):
            img = bpy.data.images.load(src)
            img.scale(1024, 512)
            _save_image(img, os.path.join(out_dir, "sky", key + ".hdr"), "HDR")
        pano = src.replace("_4k.hdr", "_tonemapped.jpg").replace("_2k.hdr", "_tonemapped.jpg")
        if os.path.exists(pano):
            dusk = key == "dusk"
            export_panorama(pano, os.path.join(out_dir, "sky", key + ".jpg"),
                            tint=(0.38, 0.58, 1.35) if dusk else (1, 1, 1), gain=0.55 if dusk else 1.0)
    sprites = export_sprites(out_dir, sorted({i["a"] for i in WEB["instances"]}))

    data = {
        "version": 1,
        "units": "metres, Blender axes (x right, y away from street, z up)",
        "stages": list(STAGES), "zones": list(ZONES),
        "materials": mats, "sprites": sprites,
        "sky": {"day": "sky/day.hdr", "dusk": "sky/dusk.hdr", "dayPano": "sky/day.jpg", "duskPano": "sky/dusk.jpg",
                "sunAzimuthDeg": -128, "sunElevationDeg": 48},
        "parts": [{"t": t, "z": z, "m": m, "b": b} for (t, z, m), b in WEB["parts"].items()],
        "meshes": WEB["meshes"], "instances": WEB["instances"],
    }
    with open(os.path.join(out_dir, "scene.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    log(f"web export written to {out_dir} in {time.time() - t0:.1f}s")


if EXPORT:
    export_web(os.path.abspath(ARGS.export_web))
    sys.exit(0)

# ============================================================================ build
t = time.time()
N_SIDE = max(0, ARGS.neighbours)
numbers = int(ARGS.villa_no) if ARGS.villa_no.isdigit() else 8
for k in range(-N_SIDE, N_SIDE + 1):
    main = k == 0
    v = Villa(k * 12.4, STAGE if main else READY, ARGS.villa_no if main else f"{numbers + k:02d}", main)
    if not main:
        random.seed(ARGS.seed + k * 31)
    v.build()
    random.seed(ARGS.seed)
xs0, xs1 = -N_SIDE * 12.4 - 6.2, N_SIDE * 12.4 + 6.2
# leftmost side compound wall
Batch_left = Batch(ROOT)
Batch_left.box("cwall", M["charcoal"], xs0 - 0.1, xs0 + 0.1, -6.8, 18.1, 0, 1.8)
Batch_left.flush()
build_site(xs0, xs1)
log(f"geometry built in {time.time() - t:.1f}s")


# ============================================================================ world + light
def hdri_sun_azimuth(img):
    """Azimuth (rad) of the brightest pixel of an equirectangular HDRI, Blender convention."""
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    lum = px.reshape(-1, 4)[:, :3].sum(1)
    i = int(lum.argmax())
    u = ((i % w) + 0.5) / w
    v = ((i // w) + 0.5) / h
    return (0.5 - u) * 2 * math.pi, (v - 0.5) * math.pi


world = bpy.data.worlds.new("sky")
scene.world = world
ensure_nodes(world)
wt = world.node_tree
bg = wt.nodes.get("Background")
hdri_name = "qwantani_dusk_2_puresky_2k.hdr" if DUSK else "kloofendal_48d_partly_cloudy_puresky_4k.hdr"
hdri_path = os.path.join(ASSETS, "hdri", hdri_name)
if os.path.exists(hdri_path):
    env = wt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(hdri_path)
    tc = wt.nodes.new("ShaderNodeTexCoord")
    mp = wt.nodes.new("ShaderNodeMapping")
    wt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    wt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    sky_col = env.outputs["Color"]
    if DUSK:
        # push the post-sunset sky toward blue hour
        tint = wt.nodes.new("ShaderNodeVectorMath")
        tint.operation = "MULTIPLY"
        tint.inputs[1].default_value = (0.38, 0.58, 1.35)
        wt.links.new(sky_col, tint.inputs[0])
        sky_col = tint.outputs["Vector"]
    wt.links.new(sky_col, bg.inputs["Color"])
    az, el = hdri_sun_azimuth(env.image)
    # place the sun front-left of the villa by day; glow behind-left at dusk
    want = math.radians(118) if DUSK else math.radians(-128)
    mp.inputs["Rotation"].default_value = (0, 0, az - want)
    bg.inputs["Strength"].default_value = 0.3 if DUSK else 1.0
    log(f"hdri {hdri_name}: sun az {math.degrees(az):.0f}° el {math.degrees(el):.0f}° -> {math.degrees(want):.0f}°")
else:
    log("HDRI missing (run `npm run assets`), using procedural sky")
    sky = wt.nodes.new("ShaderNodeTexSky")
    for st_ in ("SINGLE_SCATTERING", "NISHITA"):
        try:
            sky.sky_type = st_
            break
        except TypeError:
            continue
    set_props(sky, sun_elevation=math.radians(40), sun_rotation=math.radians(230))
    wt.links.new(sky.outputs[0], bg.inputs[0])

if DUSK:
    # street lamp bulbs on + a warm point light under each head
    for m in bpy.data.materials:
        if "bulb" in m.name.lower() and m.node_tree:
            b = m.node_tree.nodes.get("Principled BSDF")
            if b:
                b.inputs["Emission Color"].default_value = (*WARM, 1)
                b.inputs["Emission Strength"].default_value = 25.0
    for x, y, h in STREET_LAMPS:
        if -20 < y and abs(x) < 40:
            ld = bpy.data.lights.new("street", "SPOT")
            ld.energy, ld.color, ld.spot_size, ld.spot_blend = 900, WARM, math.radians(120), 0.4
            lo = bpy.data.objects.new("street", ld)
            lo.location = (x, y, h - 0.05)
            scene.collection.objects.link(lo)


# ============================================================================ camera
def camera(loc, target, lens, level=True):
    cd = bpy.data.cameras.new("cam")
    cd.lens, cd.sensor_width = lens, 36
    cam = bpy.data.objects.new("cam", cd)
    scene.collection.objects.link(cam)
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    if level:
        # two-point perspective: keep verticals straight, frame with lens shift
        flat = Vector((d.x, d.y, 0))
        cam.rotation_euler = (math.radians(90), 0, math.atan2(flat.y, flat.x) - math.pi / 2)
        cd.shift_y = (d.z / flat.length) * lens / 36 * min(1.0, W / H) if W >= H else (d.z / flat.length) * lens / 36
    else:
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam


VIEWS = {
    "hero":   ((5.6, -19.5, 1.65), (-0.9, -1.5, 4.9), 21, True),
    "front":  ((0.4, -25.0, 1.7), (0.4, 0, 5.0), 30, True),
    "aerial": ((-19.0, -27.0, 21.0), (0.0, 2.5, 2.5), 32, False),
    "pool":   ((5.3, 17.15, 1.75), (-0.8, 9.0, 4.2), 17, True),
}
loc, tgt, lens, level = VIEWS[ARGS.view]
camera(loc, tgt, lens, level)

# ============================================================================ render
os.makedirs(os.path.dirname(os.path.abspath(ARGS.out)), exist_ok=True)
log(f"scene ready in {time.time() - T_START:.1f}s; rendering {W}x{H} {ARGS.view}/{ARGS.time} -> {ARGS.out}")
bpy.ops.render.render(write_still=True)
log("done:", ARGS.out, "exists:", os.path.exists(ARGS.out), f"total {time.time() - T_START:.1f}s")
