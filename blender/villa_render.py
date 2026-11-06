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
    p.add_argument("--view", default="hero",
                   choices=["hero", "front", "aerial", "pool", "p8front", "p8left", "p8aerial", "p8cut"])
    p.add_argument("--time", default="day", choices=["day", "dusk"])
    p.add_argument("--villa-no", default="08")
    p.add_argument("--neighbours", type=int, default=2, help="finished villas on each side")
    p.add_argument("--model", default="legacy", choices=["legacy", "phase8"],
                   help="phase8 = The North Park Phase 8 villa built from Adani's published unit plans")
    p.add_argument("--type", default="B", choices=["B", "C", "C1"], help="phase8 unit type")
    p.add_argument("--palette", default="tan", choices=["tan", "grey"], help="phase8 facade colour scheme")
    p.add_argument("--cutaway", default="", choices=["", "gf", "ff"],
                   help="phase8: cut the villa above this floor to show its layout")
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
CUR = {"tag": "main", "zone": "site", "lid": False}   # lid: slab/ceiling over a floor (hidden in the floor explorer)
WEB = {"parts": {}, "meshes": [], "instances": []}

STAGES = ("Foundation", "Structure", "Finishing", "Ready")
F, S, FI, R = range(4)
ZONES = ("basement", "groundFloor", "firstFloor", "secondFloor", "facade", "decks", "landscape",
         "servantsQuarter")

# default construction state (mirrors the interactive app's demo villa); --data overrides
DATA = {"basement": "Finishing", "groundFloor": "Finishing", "firstFloor": "Structure",
        "secondFloor": "Foundation", "facade": "Finishing", "decks": "Structure",
        "landscape": "Foundation", "servantsQuarter": "Structure"}
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
scene.view_settings.exposure = 0.8 if DUSK else (-0.35 if ARGS.cutaway else 0.25)
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


def pbr(name, tex, size=2.0, tint=None, rough=None, relief=0.004, bevel=0.01, fallback=(0.6, 0.6, 0.6),
        sat=None):
    """World-space, box-projected PBR material from a Poly Haven texture set.

    size   real-world size (m) one texture tile covers
    tint   RGB multiplier on the diffuse map
    rough  None = roughness map, float = constant, (lo, hi) = remapped map
    relief bump height in metres from the displacement map
    bevel  rounded-edge radius (Cycles shader bevel; catches edge highlights)
    sat    saturation applied to the diffuse map before the tint (0 = greyscale)
    """
    mat = bpy.data.materials.new(name)
    mat["web"] = json.dumps({"tex": tex, "tile": size, "tint": tint or (1, 1, 1),
                             "sat": 1.0 if sat is None else sat,
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
        if sat is not None:
            hs = N.new("ShaderNodeHueSaturation")
            hs.inputs["Saturation"].default_value = sat
            L.new(col, hs.inputs["Color"])
            col = hs.outputs["Color"]
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
# Phase 8 palette (colours sampled from Adani's brochure renders) + interiors for the cut-away views
M.update({
    "tan":      pbr("tan", "beige_wall_002", size=2.4, tint=(1.45, 1.2, 1.05), relief=0.004),
    "slate":    pbr("slate", "white_stucco", size=2.0, tint=(0.13, 0.155, 0.15), relief=0.003),
    "block":    pbr("block", "red_brick_03", size=2.9, sat=0.0, tint=(3.4, 3.4, 3.3), relief=0.01, bevel=0),
    "marble":   solid("marble", (0.70, 0.62, 0.50), rough=0.12, coat=0.3),
    "vtile":    solid("vtile", (0.52, 0.52, 0.50), rough=0.22),
    "fab_light": solid("fab_light", (0.70, 0.66, 0.58), rough=0.9),
    "fab_dark": solid("fab_dark", (0.16, 0.15, 0.14), rough=0.85),
    "white":    solid("white", (0.88, 0.88, 0.86), rough=0.25),
    "granite":  solid("granite", (0.08, 0.075, 0.07), rough=0.25, coat=0.4),
    "rug":      solid("rug", (0.42, 0.38, 0.34), rough=1.0),
    "label":    solid("label", (0.015, 0.015, 0.016), rough=0.7),
    "steel":    solid("steel", (0.62, 0.62, 0.6), rough=0.3, metal=0.9),
    "cap":      solid("cap", (0.035, 0.035, 0.038), rough=0.8),
})


# ============================================================================ geometry
class Batch:
    """Accumulates axis-aligned boxes per (name, material) and emits one mesh each."""

    def __init__(self, coll):
        self.coll, self.parts = coll, {}

    def box(self, key, mat, x0, x1, y0, y1, z0, z1):
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        if EXPORT:
            k = (CUR["tag"], CUR["zone"], mat.name, CUR["lid"])
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
    """A small bent leaf, parked far below the ground; hedges instance it via particles.
    It faces +X: hair instancing aligns +X with the surface normal, so leaves lie on the hedge."""
    if not _LEAF:
        w, l = 0.022, 0.06
        verts = [(0, 0, 0), (0.004, w, l * 0.35), (0.01, 0, l), (0.004, -w, l * 0.35), (-0.003, 0, l * 0.4)]
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
        WEB["parts"].setdefault((CUR["tag"], CUR["zone"], "hedge", False), []).extend(
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
              phase_factor_random=2.0, use_advanced_hair=True)   # rotation settings need advanced hair
    ob.show_instancer_for_render = True
    # hair instances are scaled by the hair length: 1.0 keeps leaves at their modelled size
    ps.hair_length = 1.0
    mod.particle_system.seed = random.randint(0, 9999)
    return ob


# ============================================================================ villa
PL = 0.45           # plinth / ground-floor finished level
FF0, FF1 = 3.75, 6.85  # first floor: floor level, underside of terrace slab
TR0, TR1 = 7.05, 9.85  # terrace room
WALL = 0.23


class Villa:
    """One plot. `ox` shifts it along the street; `st` maps zone -> stage index."""
    infill = "brick"   # wall infill shown during the Structure stage

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
            self.pieces(key + "_brick", M[self.infill], axis, a0, a1, t0 + 0.025, t1 - 0.025,
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


# ============================================================================ Phase 8 villa (real plans)
# Geometry read off Adani's published Type B unit plan (The North Park, Phase 8 brochure) at
# 118 px per metre, snapped to its room-size table. Plan coordinates: u runs left -> right seen
# from the street, v runs from the house's rear wall (v = 0) toward the street. Type C is the
# mirror image of B; C1 is C without the rear servant block.
P8_UC, P8_VF = 4.25, 12.86             # plot centre (u), and the v that maps to y = 0
P8_PLOT_U, P8_PLOT_V = (-2.25, 10.75), (-2.36, 19.56)
P8_W = P8_PLOT_U[1] - P8_PLOT_U[0]     # 13.0 m wide plots
P8_ZONES = ("groundFloor", "firstFloor", "secondFloor", "facade", "decks", "landscape", "servantsQuarter")
LV = {"G": 0.45, "1": 3.90, "2": 7.35, "R": 10.80}   # finished floor levels + roof top
SLAB, CEIL = 0.20, 3.25                   # slab thickness; finished floor to slab soffit
LIFT = (5.45, 7.33, 6.85, 8.95)           # lift shaft, outer (u0, u1, v0, v1)
STAIR = (7.33, 8.34, 4.80, 10.28)         # stair well
COLS = [(0.1, 0.1), (3.82, 0.1), (5.45, 0.1), (8.44, 0.1), (0.1, 4.74), (3.82, 4.74), (5.45, 4.74),
        (8.44, 4.74), (0.1, 10.34), (2.7, 10.34), (5.45, 10.34), (8.44, 10.34), (0.1, 15.68),
        (2.4, 15.68), (4.85, 15.68), (5.45, 12.64), (8.44, 12.64)]


def rect_minus(u0, u1, v0, v1, holes):
    """Axis-aligned rectangle minus rectangular holes (u0, u1, v0, v1), as a list of rectangles."""
    us = sorted({u0, u1, *(c for h in holes for c in (h[0], h[1]) if u0 < c < u1)})
    out = []
    for a, b in zip(us, us[1:]):
        cuts = sorted((max(h[2], v0), min(h[3], v1)) for h in holes
                      if h[0] <= a + 1e-6 and h[1] >= b - 1e-6 and h[2] < v1 and h[3] > v0)
        v = v0
        for c0, c1 in cuts:
            if c0 > v:
                out.append((a, b, v, c0))
            v = max(v, c1)
        if v < v1:
            out.append((a, b, v, v1))
    return out


# furniture, as boxes in a local frame: a runs along the back edge (0..W), b away from it (0..D)
def _bed(W, D):
    return [("bed", "wood", 0, W, 0.06, D, 0, 0.3), ("bed", "fab_light", 0.04, W - 0.04, 0.1, D - 0.03, 0.3, 0.52),
            ("bed", "fab_dark", 0, W, 0, 0.06, 0, 1.15), ("bed", "white", 0.14, W / 2 - 0.05, 0.14, 0.55, 0.52, 0.66),
            ("bed", "white", W / 2 + 0.05, W - 0.14, 0.14, 0.55, 0.52, 0.66),
            ("bed", "fab_dark", 0.02, W - 0.02, D - 0.62, D - 0.12, 0.52, 0.555)]


def _sofa(W, D, mat="fab_light"):
    return [("sofa", mat, 0, W, 0, D, 0, 0.42), ("sofa", mat, 0, W, 0, 0.22, 0.42, 0.85),
            ("sofa", mat, 0, 0.18, 0.22, D, 0.42, 0.62), ("sofa", mat, W - 0.18, W, 0.22, D, 0.42, 0.62)]


def _armchair(W, D):
    return _sofa(W, D, "fab_dark")


def _table(W, D, h=0.75, mat="wood"):
    return [("table", mat, 0, W, 0, D, h - 0.04, h)] + [
        ("table", mat, a, a + 0.06, b, b + 0.06, 0, h - 0.04) for a in (0.06, W - 0.12) for b in (0.06, D - 0.12)]


def _low_table(W, D):
    return _table(W, D, 0.4)


def _chair(W, D):
    return [("chair", "fab_dark", 0, W, 0, D, 0.42, 0.48), ("chair", "fab_dark", 0, W, 0, 0.06, 0.48, 0.92)] + [
        ("chair", "metal", a, a + 0.03, b, b + 0.03, 0, 0.42) for a in (0.03, W - 0.06) for b in (0.03, D - 0.06)]


def _block(key, mat, h):
    return lambda W, D: [(key, mat, 0, W, 0, D, 0, h)]


def _counter(W, D):
    return [("counter", "white", 0, W, 0, D, 0, 0.86), ("counter", "granite", 0, W, 0, D, 0.86, 0.9)]


def _vanity(W, D):
    return [("vanity", "wood", 0, W, 0, D, 0.45, 0.8), ("vanity", "granite", 0, W, 0, D, 0.8, 0.84),
            ("vanity", "white", W / 2 - 0.25, W / 2 + 0.25, 0.08, D - 0.08, 0.84, 0.92)]


def _wc(W, D):
    return [("wc", "white", 0, W, 0, 0.18, 0.25, 0.9), ("wc", "white", 0.02, W - 0.02, 0.18, D, 0.25, 0.42)]


def _tv(W, D):
    return [("tv", "wood", 0, W, 0, D, 0, 0.45), ("tv", "groove", W * 0.15, W * 0.85, 0.02, 0.06, 0.9, 1.7)]


class Phase8Villa(Villa):
    """A North Park Phase 8 villa: ground + two floors and a terrace garden, from the published plans."""
    infill = "block"   # Adani's site photo shows grey concrete blockwork, not brick

    PALETTES = {"tan": {"gf": "charcoal", "ff": "tan", "box": "tan", "sf": "tan", "accent": "charcoal"},
                "grey": {"gf": "charcoal", "ff": "slate", "box": "slate", "sf": "tan", "accent": "charcoal"}}

    def __init__(self, ox, st, number, main, vtype="B", palette="tan", cut=None, last=False):
        super().__init__(ox, st, number, main)
        self.vtype, self.sx = vtype, (-1 if vtype in ("C", "C1") else 1)
        self.servant = vtype != "C1"
        self.pal = self.PALETTES[palette]
        self.cut = cut or None
        self.zcut = {"gf": LV["G"] + 2.4, "ff": LV["1"] + 2.4}.get(self.cut)
        self.last = last

    # ---- stages: an upper floor cannot be ahead of the floor that carries it ----
    def s(self, zone):
        st = self.st.get(zone, R)
        gf, ff = self.st.get("groundFloor", R), self.st.get("firstFloor", R)
        if zone in ("firstFloor", "secondFloor") and gf <= F:
            return F
        if zone == "secondFloor" and ff <= F:
            return F
        return st

    # ---- cut-away: everything is clipped at zcut; cut walls get a dark cap so the plan reads ----
    def box(self, key, mat, x0, x1, y0, y1, z0, z1):
        if self.zcut is not None:
            if z0 >= self.zcut - 1e-4:
                return
            if z1 > self.zcut:
                z1 = self.zcut - 0.012
                if mat is not M["glass"]:
                    super().box(key + "_cap", M["cap"], x0, x1, y0, y1, z1, self.zcut)
        super().box(key, mat, x0, x1, y0, y1, z0, z1)

    def curtain(self, *a, **k):
        if self.zcut is None:
            super().curtain(*a, **k)

    # ---- plan (u, v) -> local (x, y) ----
    def X(self, u):
        return self.sx * (u - P8_UC)

    def Y(self, v):
        return P8_VF - v

    def ur(self, along, a0, a1):
        """A plan range along u or v, as a sorted local range along x or y."""
        if along == "u":
            return tuple(sorted((self.X(a0), self.X(a1))))
        return (self.Y(a1), self.Y(a0))

    def ub(self, key, mat, u0, u1, v0, v1, z0, z1):
        x0, x1 = self.ur("u", u0, u1)
        y0, y1 = self.ur("v", v0, v1)
        self.box(key, mat, x0, x1, y0, y1, z0, z1)

    @staticmethod
    def _ax(along):
        return "x" if along == "u" else "y"

    def _t(self, along, t):
        return self.Y(t) if along == "u" else self.X(t)

    def _sgn(self, along, sign):
        """A +t/-t side in plan coordinates, as a side in local coordinates."""
        return -sign if along == "u" else sign * self.sx

    def W(self, zone, key, along, a0, a1, t0, t1, z0, z1, holes=(), final=None, inner=0):
        """Wall along u or v; t0..t1 is its thickness band in the other plan axis."""
        a = self.ur(along, a0, a1)
        t = self.ur("v" if along == "u" else "u", t0, t1)
        hs = [(*self.ur(along, h0, h1), hz0, hz1) for h0, h1, hz0, hz1 in holes]
        self.wall(zone, key, self._ax(along), a[0], a[1], t[0], t[1], z0, z1, hs,
                  final or self.pal["gf"], self._sgn(along, inner) if inner else 0)

    def Pt(self, zone, key, along, a0, a1, t0, t1, z0, z1, holes=()):
        """Interior partition: blockwork, then plaster, then the interior paint."""
        self.W(zone, key, along, a0, a1, t0, t1, z0, z1, holes, final="interior")

    def G(self, zone, key, along, a0, a1, t, z0, z1, panes=2, curtain=0):
        a = self.ur(along, a0, a1)
        self.glazing(zone, key, self._ax(along), a[0], a[1], self._t(along, t), z0, z1, panes,
                     self._sgn(along, curtain) if curtain else 0)

    def RL(self, zone, key, along, a0, a1, t, z0, h=1.05):
        a = self.ur(along, a0, a1)
        self.railing(zone, key, self._ax(along), a[0], a[1], self._t(along, t), z0, h)

    def SC(self, key, along, a0, a1, t, side, z0, z1):
        a = self.ur(along, a0, a1)
        self.scaffold(key, self._ax(along), a[0], a[1], self._t(along, t), self._sgn(along, side), z0, z1)

    def SL(self, zone, key, u0, u1, v0, v1, z0, z1, holes=(), final=None):
        """Zone-aware slab with rectangular openings."""
        for a0, a1, b0, b1 in rect_minus(u0, u1, v0, v1, holes):
            x0, x1 = self.ur("u", a0, a1)
            y0, y1 = self.ur("v", b0, b1)
            self.slab(zone, key, x0, x1, y0, y1, z0, z1, final or self.pal["gf"])

    def put(self, aid, u, v, z, rot=None, scale=1.0, variant=None):
        if self.zcut is not None and z >= self.zcut:
            return
        r = None if rot is None else (-rot if self.sx > 0 else rot + math.pi)
        LIB.place(self.coll, aid, self.ox + self.X(u), self.Y(v), z, rot=r, scale=scale, variant=variant)

    def fit(self, items, u0, u1, v0, v1, back, z):
        """Furniture: `items(W, D)` boxes against the `back` edge ('u0', 'u1', 'v0' or 'v1')."""
        along_v = back in ("u0", "u1")
        w, d = (v1 - v0, u1 - u0) if along_v else (u1 - u0, v1 - v0)
        for key, mat, a0, a1, b0, b1, h0, h1 in items(w, d):
            if back == "v0":
                r = (u0 + a0, u0 + a1, v0 + b0, v0 + b1)
            elif back == "v1":
                r = (u1 - a1, u1 - a0, v1 - b1, v1 - b0)
            elif back == "u0":
                r = (u0 + b0, u0 + b1, v1 - a1, v1 - a0)
            else:
                r = (u1 - b1, u1 - b0, v0 + a0, v0 + a1)
            self.ub(key, M[mat], *r, z + h0, z + h1)

    def lawn(self, u0, u1, v0, v1, z=0.0, density=260):
        self.ub("lawn_soil", M["lawn"], u0, u1, v0, v1, z, z + 0.1)
        if EXPORT or (self.zcut is not None and z >= self.zcut):
            return
        (x0, x1), (y0, y1), o = self.ur("u", u0, u1), self.ur("v", v0, v1), self.ox
        ob = mesh_object(self.coll, "lawn", [(x0 + o, y0, z + 0.1), (x1 + o, y0, z + 0.1), (x1 + o, y1, z + 0.1),
                                             (x0 + o, y1, z + 0.1)], [(0, 1, 2, 3)], M["lawn"])
        add_grass(ob, density=density if self.main else density // 2)

    def hedge_u(self, u0, u1, v0, v1, z0, h):
        (x0, x1), (y0, y1) = self.ur("u", u0, u1), self.ur("v", v0, v1)
        hedge(self.coll, x0 + self.ox, x1 + self.ox, y0, y1, z0, h)

    def label(self, text, u, v, z, size=0.3):
        if EXPORT:
            return
        cu = bpy.data.curves.new("label", "FONT")
        cu.body, cu.size, cu.align_x, cu.align_y = text, size, "CENTER", "CENTER"
        cu.materials.append(M["label"])
        ob = bpy.data.objects.new("label", cu)
        ob.location = (self.ox + self.X(u), self.Y(v), z + 0.01)
        self.coll.objects.link(ob)

    def room(self, zone, u0, u1, v0, v1, lvl, floor="marble", label=None):
        """Finished floor + ceiling + a warm light (or, cut away, a room label).
        label = text, or (text, u, v, size) to place it clear of the furniture."""
        st = self.s(zone)
        if st < FI:
            return
        z0 = LV[lvl]
        self.ub(zone + "_floor", M[floor] if st >= R else M["plaster"], u0, u1, v0, v1, z0, z0 + 0.015)
        if self.zcut is None:
            CUR["lid"] = True
            self.ub(zone + "_ceil", M["ceiling"], u0, u1, v0, v1, z0 + CEIL - 0.015, z0 + CEIL)
            CUR["lid"] = False
            if st >= R and (self.main or DUSK) and not EXPORT:
                ld = bpy.data.lights.new(zone + "_light", "AREA")
                ld.shape, ld.size, ld.size_y = "RECTANGLE", (u1 - u0) * 0.6, (v1 - v0) * 0.6
                ld.energy = (420 if DUSK else 90) * (u1 - u0) * (v1 - v0) / 60 * (1.0 if self.main else 0.7)
                ld.color = WARM
                lo = bpy.data.objects.new(zone + "_light", ld)
                lo.location = (self.ox + self.X((u0 + u1) / 2), self.Y((v0 + v1) / 2), z0 + CEIL - 0.05)
                self.coll.objects.link(lo)
        elif label and st >= R and self.zcut - 3.0 < z0 < self.zcut:   # only the floor being shown
            text, lu, lv, size = label if isinstance(label, tuple) else (label, (u0 + u1) / 2, (v0 + v1) / 2, 0.3)
            self.label(text, lu, lv, z0 + 0.015, size)

    def lift(self, zone, lvl, top):
        st = self.s(zone)
        if st == F:
            return
        u0, u1, v0, v1 = LIFT
        z0, w = LV[lvl], 0.15
        self.W(zone, "lift", "v", v0, v1, u0, u0 + w, z0, top, [(v0 + 0.55, v0 + 1.55, z0, z0 + 2.2)], "interior")
        self.W(zone, "lift", "v", v0, v1, u1 - w, u1, z0, top, (), "interior")
        self.W(zone, "lift", "u", u0 + w, u1 - w, v0, v0 + w, z0, top, (), "interior")
        self.W(zone, "lift", "u", u0 + w, u1 - w, v1 - w, v1, z0, top, (), "interior")
        if st >= R:
            self.ub("lift_door", M["steel"], u0 - 0.02, u0 + 0.03, v0 + 0.55, v0 + 1.55, z0, z0 + 2.2)

    def stairs(self, zone, z0, z1, v_start, v_end):
        """A straight flight in the stair well, solid underneath, from (v_start, z0) to (v_end, z1)."""
        st = self.s(zone)
        if st == F:
            return
        n = max(2, round((z1 - z0) / 0.16))
        mat = M["rcc"] if st < R else M["marble"]
        for i in range(n):
            a = v_start + (v_end - v_start) * i / n
            b = v_start + (v_end - v_start) * (i + 1) / n
            lo, hi = sorted((a, b))
            self.ub("stair", mat, STAIR[0] + 0.03, STAIR[1] - 0.03, lo, hi, z0, z0 + (z1 - z0) * (i + 1) / n)

    def footings(self):
        for u, v in COLS:
            self.ub("footing", M["rcc"], u - 0.55, u + 0.55, v - 0.55, v + 0.55, -0.05, 0.3)
            for du in (-0.1, 0.1):
                for dv in (-0.1, 0.1):
                    self.ub("rebar", M["rebar"], u + du - 0.012, u + du + 0.012, v + dv - 0.012, v + dv + 0.012,
                            0.3, 1.6)
        for v, u0, u1 in ((0.1, 0.0, 8.54), (4.74, 0.0, 8.54), (10.34, 0.0, 8.54), (15.68, 0.0, 4.95),
                          (12.64, 5.3, 8.54)):
            self.ub("plinth_beam", M["rcc"], u0, u1, v - 0.15, v + 0.15, 0.05, 0.45)
        for u, v1 in ((0.1, 15.83), (3.82, 4.9), (5.45, 15.83), (8.44, 12.8)):
            self.ub("plinth_beam", M["rcc"], u - 0.15, u + 0.15, -0.05, v1, 0.05, 0.45)

    # ---- zones ----
    def build(self):
        for zone, step in (("groundFloor", self.gf), ("firstFloor", self.ff), ("secondFloor", self.sf),
                           ("servantsQuarter", self.sq), ("decks", self.decks), ("facade", self.facade),
                           ("landscape", self.land)):
            CUR["zone"] = zone
            step()
        CUR["zone"] = "site"
        self.b.flush()

    def gf(self):
        z, st = "groundFloor", self.s("groundFloor")
        if st == F:
            self.footings()
            return
        g, top = LV["G"], LV["1"] - SLAB
        cg, box = self.pal["gf"], self.pal["box"]
        pm = M["rcc"] if st == S else M[cg]
        # raised ground-floor slab under the house, the porch and the drawing-room verandah
        for r in ((0.0, 8.54, 0.0, 12.74), (0.0, 4.91, 12.74, 15.78), (4.79, 6.50, 12.74, 14.48),
                  (4.79, 5.83, 14.48, 15.78), (6.50, 8.54, 12.74, 13.70), (0.0, 4.29, 15.78, 16.78)):
            self.ub("plinth", pm, *r, 0.0, g)
        sm = M["rcc"] if st < R else M["tiles"]
        for i in range(2):   # steps down from the entrance verandah and the drawing-room verandah
            self.ub("steps", sm, 6.50, 8.54, 13.70 + 0.3 * i, 14.0 + 0.3 * i, 0.0, g - 0.15 * (i + 1))
            self.ub("steps", sm, 1.6, 2.8, 16.78 + 0.3 * i, 17.08 + 0.3 * i, 0.0, g - 0.15 * (i + 1))
        # outer walls (exterior paint outside, interior lining inside)
        self.W(z, "gf_rear", "u", 0.0, 8.54, 0.0, 0.2, g, top,
               [(4.35, 4.95, g + 1.7, g + 2.4), (6.75, 7.65, g, g + 2.4)], cg, +1)
        self.W(z, "gf_left", "v", 0.0, 15.78, 0.0, 0.2, g, top,
               [(1.4, 3.4, g + 0.75, g + 2.7), (5.1, 10.0, g, g + 2.85)], cg, +1)
        self.W(z, "gf_right", "v", 0.0, 12.74, 8.34, 8.54, g, top,
               [(1.2, 3.6, g + 1.05, g + 2.25), (8.9, 9.35, g + 0.4, g + 3.0)], cg, -1)
        self.W(z, "gf_front", "u", 0.0, 4.91, 15.58, 15.78, g, top, [(0.7, 4.05, g, g + 2.85)], cg, -1)
        self.W(z, "gf_entry", "u", 6.50, 8.54, 12.54, 12.74, g, top,
               [(6.66, 6.92, g, g + 2.75), (7.02, 8.14, g, g + 2.75)], box, -1)
        self.W(z, "gf_pwd", "v", 12.74, 14.48, 6.38, 6.50, g, top, (), cg)
        self.W(z, "gf_pwd", "u", 4.91, 6.38, 14.28, 14.48, g, top, [(5.15, 6.15, g + 1.6, g + 2.5)], cg, -1)
        self.W(z, "gf_duct", "u", 4.91, 5.83, 15.58, 15.78, g, top, (), cg)
        self.W(z, "gf_duct", "v", 14.48, 15.58, 5.71, 5.83, g, top, (), cg)
        self.G(z, "gf_win", "v", 1.4, 3.4, 0.1, g + 0.75, g + 2.7, 2, +1)
        self.G(z, "gf_win", "v", 5.1, 10.0, 0.1, g, g + 2.85, 4, +1)
        self.G(z, "gf_win", "v", 1.2, 3.6, 8.44, g + 1.05, g + 2.25, 2, -1)
        self.G(z, "gf_win", "v", 8.9, 9.35, 8.44, g + 0.4, g + 3.0, 1)
        self.G(z, "gf_win", "u", 0.7, 4.05, 15.68, g, g + 2.85, 3, -1)
        self.G(z, "gf_win", "u", 6.66, 6.92, 12.64, g, g + 2.75, 1)
        self.G(z, "gf_win", "u", 4.35, 4.95, 0.1, g + 1.7, g + 2.4, 1)
        self.G(z, "gf_win", "u", 5.15, 6.15, 14.38, g + 1.6, g + 2.5, 1)
        if st >= R:
            self.ub("door", M["door"], 7.04, 8.12, 12.60, 12.68, g, g + 2.73)
            self.ub("door_handle", M["metal"], 7.18, 7.22, 12.68, 12.73, g + 0.6, g + 2.1)
        # partitions
        Pt = self.Pt
        Pt(z, "gf_p", "v", 10.40, 15.58, 4.79, 4.91, g, top, [(10.5, 11.9, g, g + 2.4)])
        Pt(z, "gf_p", "u", 4.91, 6.38, 12.54, 12.74, g, top, [(5.25, 6.05, g, g + 2.4)])
        Pt(z, "gf_p", "u", 0.2, 3.88, 4.68, 4.80, g, top, [(2.85, 3.7, g, g + 2.4)])
        Pt(z, "gf_p", "v", 0.2, 4.68, 3.76, 3.88, g, top, [(1.0, 1.8, g, g + 2.4)])
        Pt(z, "gf_p", "u", 3.88, 5.39, 2.34, 2.46, g, top)
        Pt(z, "gf_p", "u", 3.88, 5.39, 3.68, 3.80, g, top, [(4.2, 5.0, g, g + 2.2)])
        Pt(z, "gf_p", "v", 0.2, 4.68, 5.39, 5.51, g, top)
        Pt(z, "gf_p", "u", 5.51, 8.34, 4.68, 4.80, g, top, [(5.65, 6.55, g, g + 2.4)])
        Pt(z, "gf_p", "u", 5.45, 7.33, 5.33, 5.45, g, top)
        Pt(z, "gf_p", "v", 5.45, 6.85, 5.45, 5.57, g, top, [(5.75, 6.55, g, g + 2.2)])
        Pt(z, "gf_p", "v", 5.45, 6.85, 7.33, 7.45, g, top)
        for u0, u1 in ((0.2, 0.9), (2.8, 3.6)):
            Pt(z, "gf_p", "u", u0, u1, 10.28, 10.40, g, top)
        self.lift(z, "G", top)
        self.stairs(z, g, LV["1"], 10.1, 5.0)
        for r, fl, lab in (((0.2, 3.76, 0.2, 4.68), "vtile", ("GUEST BEDROOM\n3.56 x 4.48 m", 2.0, 2.75, 0.22)),
                           ((3.88, 5.39, 0.2, 2.34), "vtile", ("TOILET", 4.75, 1.5, 0.18)),
                           ((3.88, 5.39, 2.46, 3.68), "vtile", None),
                           ((5.51, 8.34, 0.2, 4.68), "vtile", ("KITCHEN\n2.83 x 4.48 m", 6.6, 2.45, 0.24)),
                           ((0.2, 5.39, 4.80, 10.28), "marble", ("DINING & FAMILY\n5.19 x 5.48 m", 2.6, 8.2, 0.3)),
                           ((5.51, 7.33, 4.80, 10.28), "marble", ("LIFT", 6.39, 7.9, 0.2)),
                           ((0.2, 4.79, 10.40, 15.58), "marble", ("DRAWING ROOM\n4.59 x 5.18 m", 2.75, 14.0, 0.28)),
                           ((4.91, 8.34, 10.40, 12.54), "marble", ("FOYER", 6.1, 11.5, 0.26)),
                           ((4.91, 6.38, 12.74, 14.28), "marble", ("POWDER", 5.85, 12.95, 0.14))):
            self.room(z, *r, "G", fl, lab)
        if st >= R:
            self.furnish_gf(g)
        # first-floor slab (cast with the ground-floor structure): floor, deck shade, balcony, porch beam
        holes = [(STAIR[0], STAIR[1], 4.80, 7.0), (LIFT[0] + 0.15, LIFT[1] - 0.15, LIFT[2] + 0.15, LIFT[3] - 0.15)]
        CUR["lid"] = True
        self.SL(z, "ff_slab", 0.0, 8.54, 0.0, 15.18, top, LV["1"], holes, self.pal["accent"])
        CUR["lid"] = False
        self.SL(z, "ff_slab", -0.45, 0.0, 0.0, 10.28, top, LV["1"], (), self.pal["accent"])
        self.SL(z, "ff_beam", 4.91, 8.54, 14.88, 15.18, top - 0.4, top, (), self.pal["ff"])
        self.SL(z, "ff_box", -0.63, 5.05, 15.18, 16.68, LV["1"] - 0.45, LV["1"], (), box)
        self.SL(z, "ff_box", -0.63, 0.0, 10.28, 15.18, LV["1"] - 0.45, LV["1"], (), box)
        if st == S:
            self.SC("gf_scaffold", "u", -0.6, 8.54, 16.68, +1, 0.0, top)

    def furnish_gf(self, g):
        f = self.fit
        f(_bed, 0.95, 2.85, 0.2, 2.35, "v0", g)
        f(_block("wardrobe", "wood", 2.3), 0.3, 2.7, 4.1, 4.68, "v1", g)
        f(_wc, 4.6, 5.0, 0.2, 0.8, "v0", g)
        f(_vanity, 3.88, 4.43, 1.0, 2.0, "u0", g)
        f(_counter, 7.72, 8.34, 0.82, 4.68, "u1", g)
        f(_counter, 5.51, 8.34, 0.2, 0.82, "v0", g)
        f(_table, 1.6, 3.6, 5.7, 6.7, "v0", g)
        for uu in (1.7, 2.37, 3.03):
            f(_chair, uu, uu + 0.45, 5.15, 5.6, "v0", g)
            f(_chair, uu, uu + 0.45, 6.8, 7.25, "v1", g)
        f(_chair, 1.0, 1.45, 5.98, 6.43, "u0", g)
        f(_chair, 3.75, 4.2, 5.98, 6.43, "u1", g)
        f(_sofa, 0.9, 3.1, 9.3, 10.2, "v1", g)
        f(_block("rug", "rug", 0.012), 1.2, 3.9, 11.6, 14.6, "v0", g)
        f(_sofa, 0.25, 1.15, 11.4, 14.3, "u0", g)
        f(_sofa, 1.5, 3.7, 10.6, 11.5, "v0", g)
        f(_armchair, 1.7, 2.5, 14.5, 15.3, "v1", g)
        f(_armchair, 2.8, 3.6, 14.5, 15.3, "v1", g)
        f(_low_table, 2.0, 3.2, 12.4, 13.5, "v0", g)
        f(_tv, 4.35, 4.79, 12.2, 14.2, "u1", g)
        f(_wc, 5.6, 6.0, 13.7, 14.28, "v1", g)
        f(_vanity, 4.91, 5.4, 12.9, 13.9, "u0", g)

    def ff(self):
        z, st = "firstFloor", self.s("firstFloor")
        if st == F:
            return
        f1, top = LV["1"], LV["2"] - SLAB
        cf, box = self.pal["ff"], self.pal["box"]
        self.W(z, "ff_rear", "u", 0.0, 8.54, 0.0, 0.2, f1, top, [(6.2, 7.0, f1 + 1.6, f1 + 2.3)], cf, +1)
        self.W(z, "ff_left", "v", 0.0, 15.18, 0.0, 0.2, f1, top,
               [(1.2, 3.6, f1 + 0.45, f1 + 2.7), (5.4, 9.8, f1, f1 + 2.85), (13.6, 14.4, f1 + 1.6, f1 + 2.3)], cf, +1)
        self.W(z, "ff_right", "v", 0.0, 15.18, 8.34, 8.54, f1, top, [(8.9, 9.35, f1 + 0.3, f1 + 2.9)], cf, -1)
        self.W(z, "ff_front", "u", 0.0, 8.54, 14.98, 15.18, f1, top,
               [(3.3, 4.65, f1, f1 + 2.75), (5.75, 7.85, f1 + 0.6, f1 + 2.6)], cf, -1)
        self.G(z, "ff_win", "v", 1.2, 3.6, 0.1, f1 + 0.45, f1 + 2.7, 2, +1)
        self.G(z, "ff_win", "v", 5.4, 9.8, 0.1, f1, f1 + 2.85, 4, +1)
        self.G(z, "ff_win", "v", 13.6, 14.4, 0.1, f1 + 1.6, f1 + 2.3, 1)
        self.G(z, "ff_win", "v", 8.9, 9.35, 8.44, f1 + 0.3, f1 + 2.9, 1)
        self.G(z, "ff_win", "u", 3.3, 4.65, 15.08, f1, f1 + 2.75, 2, -1)
        self.G(z, "ff_win", "u", 5.75, 7.85, 15.08, f1 + 0.6, f1 + 2.6, 2, -1)
        self.G(z, "ff_win", "u", 6.2, 7.0, 0.1, f1 + 1.6, f1 + 2.3, 1)
        # the signature deep frame around the balcony: left panel, right fin, lid
        self.W(z, "ff_box", "v", 10.28, 15.18, -0.63, 0.0, f1, LV["2"] + 0.25,
               [(13.6, 14.4, f1 + 1.6, f1 + 2.3)], box)
        self.W(z, "ff_box", "v", 15.18, 16.68, -0.63, 0.0, f1, top, (), box)
        self.W(z, "ff_box", "v", 15.18, 16.68, 4.79, 5.05, f1, top, (), box)
        self.SL(z, "ff_box", -0.63, 5.05, 15.18, 16.68, top, LV["2"] + 0.25, (), box)
        Pt = self.Pt
        Pt(z, "ff_p", "u", 0.2, 5.39, 4.68, 4.80, f1, top, [(3.7, 4.6, f1, f1 + 2.4)])
        Pt(z, "ff_p", "v", 0.2, 4.68, 5.39, 5.51, f1, top, [(2.7, 4.3, f1, f1 + 2.4)])
        Pt(z, "ff_p", "u", 5.51, 8.34, 1.90, 2.02, f1, top, [(6.4, 7.2, f1, f1 + 2.2)])
        Pt(z, "ff_p", "u", 5.51, 8.34, 4.68, 4.80, f1, top)
        Pt(z, "ff_p", "u", 0.2, 8.34, 10.28, 10.40, f1, top, [(3.7, 4.6, f1, f1 + 2.4)])
        Pt(z, "ff_p", "v", 10.40, 14.98, 3.03, 3.15, f1, top, [(11.0, 11.9, f1, f1 + 2.4)])
        Pt(z, "ff_p", "u", 0.2, 3.03, 13.18, 13.30, f1, top, [(1.0, 1.8, f1, f1 + 2.2)])
        Pt(z, "ff_p", "u", 5.51, 7.33, 5.68, 5.80, f1, top, [(5.9, 6.7, f1, f1 + 2.2)])
        self.lift(z, "1", top)
        self.stairs(z, f1, LV["2"], 10.1, 5.0)
        for r, fl, lab in (((0.2, 5.39, 0.2, 4.68), "marble", ("MASTER BEDROOM 1\n5.19 x 4.48 m", 4.2, 2.6, 0.2)),
                           ((5.51, 8.34, 0.2, 1.90), "vtile", ("TOILET 1", 6.9, 1.2, 0.18)),
                           ((5.51, 8.34, 2.02, 4.68), "marble", ("DRESS 1", 6.6, 2.75, 0.2)),
                           ((0.2, 5.39, 4.80, 10.28), "vtile", ("LOUNGE / LIBRARY\n5.19 x 5.48 m", 4.2, 7.3, 0.22)),
                           ((5.51, 7.33, 5.80, 10.28), "marble", ("LIFT", 6.39, 7.9, 0.2)),
                           ((0.2, 3.03, 10.40, 13.18), "marble", ("DRESS 2", 1.9, 11.35, 0.18)),
                           ((0.2, 3.03, 13.30, 14.98), "vtile", ("TOILET 2", 1.6, 13.9, 0.18)),
                           ((3.15, 8.34, 10.40, 14.98), "marble", ("MASTER BEDROOM 2\n5.19 x 4.58 m", 4.6, 13.0, 0.22)),
                           ((0.2, 4.79, 15.18, 16.68), "wood", ("BALCONY  4.59 x 1.50 m", 2.5, 15.95, 0.22))):
            self.room(z, *r, "1", fl, lab)
        if st >= R:
            self.furnish_ff(f1)
        # second-floor slab = roof of this floor + the terrace floor, with its parapet upstands
        holes = [(STAIR[0], STAIR[1], 4.80, 7.0), (LIFT[0] + 0.15, LIFT[1] - 0.15, LIFT[2] + 0.15, LIFT[3] - 0.15)]
        CUR["lid"] = True
        self.SL(z, "sf_slab", 0.0, 8.54, 0.0, 15.18, top, LV["2"], holes, cf)
        CUR["lid"] = False
        for r in ((0.0, 8.54, 15.06, 15.18), (0.0, 0.12, 10.38, 15.06), (8.42, 8.54, 10.38, 15.06)):
            self.SL(z, "tr_upstand", *r, LV["2"], LV["2"] + 0.25, (), cf)
        if st == S:
            self.SC("ff_scaffold", "u", -0.63, 8.54, 16.68, +1, f1, LV["2"] + 1.0)
            self.SC("ff_scaffold", "v", 0.0, 10.28, -0.45, -1, f1, LV["2"] + 1.0)
            self.SC("ff_scaffold", "v", 0.0, 15.18, 8.54, +1, f1, LV["2"] + 1.0)

    def furnish_ff(self, f1):
        f = self.fit
        f(_bed, 1.6, 3.5, 0.2, 2.35, "v0", f1)
        f(_armchair, 0.3, 1.05, 1.5, 2.25, "u0", f1)
        f(_block("wardrobe", "wood", 2.4), 7.74, 8.34, 2.1, 4.6, "u1", f1)
        f(_wc, 7.6, 8.2, 0.2, 0.8, "v0", f1)
        f(_vanity, 5.51, 6.1, 0.4, 1.6, "u0", f1)
        f(_sofa, 1.0, 3.0, 6.9, 7.75, "v0", f1)
        f(_low_table, 1.5, 2.5, 8.15, 8.75, "v0", f1)
        f(_tv, 1.0, 3.2, 9.85, 10.28, "v1", f1)
        f(_counter, 0.3, 3.6, 4.80, 5.35, "v0", f1)
        f(_bed, 6.15, 8.34, 11.55, 13.45, "u1", f1)
        f(_sofa, 5.1, 7.4, 10.45, 11.25, "v0", f1)
        f(_block("wardrobe", "wood", 2.4), 0.2, 0.8, 10.5, 13.1, "u0", f1)
        f(_block("wardrobe", "wood", 2.4), 0.8, 2.9, 10.4, 11.0, "v0", f1)
        f(_wc, 0.3, 0.9, 14.3, 14.98, "v1", f1)
        f(_vanity, 2.45, 3.03, 13.5, 14.6, "u1", f1)

    def sf(self):
        z, st = "secondFloor", self.s("secondFloor")
        f2 = LV["2"]
        if st == F:
            if self.s("firstFloor") >= S:   # column starter bars waiting on the first-floor roof
                for u, v in COLS:
                    if v <= 10.4:
                        for du in (-0.1, 0.1):
                            for dv in (-0.1, 0.1):
                                self.ub("rebar", M["rebar"], u + du - 0.012, u + du + 0.012,
                                        v + dv - 0.012, v + dv + 0.012, f2, f2 + 1.2)
            return
        top, r0 = LV["R"] - SLAB, LV["R"]
        cs, acc = self.pal["sf"], self.pal["accent"]
        self.W(z, "sf_rear", "u", 0.0, 8.54, 0.0, 0.2, f2, top, [(6.2, 7.0, f2 + 1.6, f2 + 2.3)], cs, +1)
        self.W(z, "sf_left", "v", 0.0, 10.38, 0.0, 0.2, f2, top, [(1.2, 3.6, f2 + 0.45, f2 + 2.7)], cs, +1)
        self.W(z, "sf_right", "v", 0.0, 10.38, 8.34, 8.54, f2, top, [(8.9, 9.35, f2 + 0.3, f2 + 2.9)], acc, -1)
        self.W(z, "sf_front", "u", 0.0, 5.45, 10.18, 10.38, f2, top,
               [(0.45, 2.75, f2, f2 + 2.75), (3.7, 5.3, f2, f2 + 2.75)], cs, -1)
        self.W(z, "sf_front", "u", 5.45, 8.54, 10.18, 10.38, f2, top, [(6.0, 8.0, f2 + 1.3, f2 + 2.0)], acc, -1)
        self.G(z, "sf_win", "v", 1.2, 3.6, 0.1, f2 + 0.45, f2 + 2.7, 2, +1)
        self.G(z, "sf_win", "v", 8.9, 9.35, 8.44, f2 + 0.3, f2 + 2.9, 1)
        self.G(z, "sf_win", "u", 0.45, 2.75, 10.28, f2, f2 + 2.75, 3, -1)
        self.G(z, "sf_win", "u", 3.7, 5.3, 10.28, f2, f2 + 2.75, 2, -1)
        self.G(z, "sf_win", "u", 6.0, 8.0, 10.28, f2 + 1.3, f2 + 2.0, 3)
        self.G(z, "sf_win", "u", 6.2, 7.0, 0.1, f2 + 1.6, f2 + 2.3, 1)
        Pt = self.Pt
        Pt(z, "sf_p", "u", 0.2, 5.39, 4.68, 4.80, f2, top, [(3.7, 4.6, f2, f2 + 2.4)])
        Pt(z, "sf_p", "v", 0.2, 4.68, 5.39, 5.51, f2, top, [(2.7, 4.3, f2, f2 + 2.4)])
        Pt(z, "sf_p", "u", 5.51, 8.34, 1.90, 2.02, f2, top, [(6.4, 7.2, f2, f2 + 2.2)])
        Pt(z, "sf_p", "u", 5.51, 8.34, 4.68, 4.80, f2, top)
        self.lift(z, "2", top)
        for r, fl in (((0.2, 5.39, 0.2, 4.68), "marble"), ((5.51, 8.34, 0.2, 1.90), "vtile"),
                      ((5.51, 8.34, 2.02, 4.68), "marble"), ((0.2, 5.39, 4.80, 10.18), "marble"),
                      ((5.51, 7.33, 4.80, 10.18), "marble")):
            self.room(z, *r, "2", fl)
        if st >= R:
            f = self.fit
            f(_bed, 1.6, 3.5, 0.2, 2.35, "v0", f2)
            f(_sofa, 1.2, 3.4, 7.0, 7.85, "v0", f2)
            f(_low_table, 1.8, 2.8, 8.2, 8.8, "v0", f2)
        # roof: slab with overhangs to the left and over the terrace doors, parapet, lift overrun
        CUR["lid"] = True
        for r in ((0.0, 8.54, 0.0, 10.38), (-0.63, 0.0, 0.0, 10.95), (0.0, 5.45, 10.38, 10.95)):
            self.SL(z, "roof", *r, top, r0, (), cs)
        for r in ((-0.63, 8.54, 0.0, 0.12), (-0.63, -0.51, 0.12, 10.83), (-0.63, 5.45, 10.83, 10.95),
                  (5.33, 5.45, 10.38, 10.83), (5.45, 8.54, 10.26, 10.38), (8.42, 8.54, 0.12, 10.26)):
            self.SL(z, "parapet", *r, r0, r0 + 0.3, (), cs)
        self.SL(z, "overrun", LIFT[0], LIFT[1], LIFT[2], LIFT[3], r0, r0 + 1.2, (), acc)
        CUR["lid"] = False
        if st == S:
            self.SC("sf_scaffold", "u", -0.63, 8.54, 10.95, +1, f2, r0 + 1.0)
            self.SC("sf_scaffold", "v", 0.0, 10.38, -0.63, -1, f2, r0 + 1.0)

    def sq(self):
        """Servant room, toilet and hand-wash at the rear boundary (single storey, roof terrace)."""
        if not self.servant:
            return
        z, st = "servantsQuarter", self.s("servantsQuarter")
        if st == F:
            for u, v in ((0.1, -2.26), (2.42, -2.26), (5.79, -2.26), (2.42, -0.1), (5.79, -1.25)):
                self.ub("sq_footing", M["rcc"], u - 0.4, u + 0.4, v - 0.4, v + 0.4, -0.05, 0.25)
            return
        g, top, cs = 0.30, 3.0, self.pal["gf"]
        pm = M["rcc"] if st == S else M[cs]
        self.ub("sq_plinth", pm, 0.0, 2.48, -2.36, 0.0, 0.0, g)
        self.ub("sq_plinth", pm, 2.48, 5.85, -2.36, -1.15, 0.0, g)
        self.W(z, "sq_rear", "u", 0.0, 5.85, -2.36, -2.16, g, top, (), cs, +1)
        self.W(z, "sq_left", "v", -2.16, 0.0, 0.0, 0.2, g, top, [(-1.6, -0.6, g + 1.0, g + 2.1)], cs, +1)
        self.W(z, "sq_mid", "v", -2.16, 0.0, 2.36, 2.48, g, top, [(-0.95, -0.15, g, g + 2.1)], cs)
        self.W(z, "sq_front", "u", 2.48, 5.85, -1.35, -1.15, g, top,
               [(2.7, 3.45, g, g + 2.1), (4.4, 5.6, g, g + 2.1)], cs, -1)
        self.W(z, "sq_right", "v", -2.16, -1.35, 5.73, 5.85, g, top, (), cs)
        self.Pt(z, "sq_p", "v", -2.16, -1.35, 3.6, 3.72, g, top)
        self.G(z, "sq_win", "v", -1.6, -0.6, 0.1, g + 1.0, g + 2.1, 2)
        if st >= R:
            self.ub("sq_door", M["door"], 2.40, 2.44, -0.93, -0.17, g, g + 2.08)
            self.ub("sq_door", M["door"], 2.72, 3.43, -1.27, -1.23, g, g + 2.08)
        for r in ((0.0, 2.48, -2.36, 0.0), (2.48, 5.85, -2.36, -1.15)):
            self.SL(z, "sq_roof", *r, top, top + 0.2, (), cs)
        self.SL(z, "sq_upstand", 0.0, 5.85, -2.36, -2.24, top + 0.2, top + 0.5, (), cs)
        if st == S:
            self.SC("sq_scaffold", "u", 2.48, 5.85, -1.15, +1, g, top + 0.2)

    def decks(self):
        z, st = "decks", self.s("decks")
        g, f1, f2 = LV["G"], LV["1"], LV["2"]
        gf, ff = self.s("groundFloor"), self.s("firstFloor")
        # timber deck beside the dining room
        if st >= S:
            self.ub("deck", M["rcc"] if st < R else M["wood"], -2.15, 0.0, 4.6, 10.48, 0.0, 0.3)
        if st >= R:
            self.put("outdoor_table_chair_set_01", -1.1, 6.4, 0.3, rot=math.pi / 2)
            self.put("potted_plant_02", -1.8, 9.9, 0.3, scale=1.1)
            if gf >= FI:
                self.ub("verandah", M["tiles"], 0.0, 4.29, 15.78, 16.78, g, g + 0.02)
        # first-floor balcony: glass railing between the frame panels
        if ff >= S and st >= FI:
            self.RL(z, "bal_rail", "u", 0.0, 4.79, 16.58, f1, h=1.05)
            if st >= R:
                self.put("potted_plant_01", 0.6, 16.2, f1 + 0.015, scale=0.9)
                self.put("potted_plant_02", 4.2, 16.2, f1 + 0.015, scale=0.9)
        # second-floor terrace garden
        if ff < S:
            return
        if st >= FI:
            for along, a0, a1, t in (("u", 0.0, 8.54, 15.12), ("v", 10.38, 15.06, 0.06), ("v", 10.38, 15.06, 8.48)):
                self.RL(z, "tr_rail", along, a0, a1, t, f2 + 0.25, h=1.0)
        if st == FI:
            self.ub("tr_tiles", M["tiles"], 0.12, 8.42, 10.38, 15.06, f2, f2 + 0.02)
        if st < R:
            return
        self.lawn(0.12, 8.42, 10.38, 15.06, f2 - 0.08, density=200)
        for u0, u1 in ((0.2, 0.8), (7.74, 8.34)):    # long planters along both sides
            self.ub("planter", M[self.pal["accent"]], u0, u1, 11.0, 14.7, f2, f2 + 0.5)
            self.ub("planter_soil", M["soil"], u0 + 0.04, u1 - 0.04, 11.04, 14.66, f2 + 0.5, f2 + 0.52)
            for k in range(5):
                self.put(random.choice(("fern_02", "calathea_orbifolia_01", "anthurium_botany_01")),
                         (u0 + u1) / 2, 11.35 + k * 0.75, f2 + 0.52, scale=random.uniform(1.4, 1.9))
        # timber deck under a steel pergola, with a lounge set
        self.ub("tr_deck", M["wood"], 1.0, 3.3, 11.3, 14.1, f2, f2 + 0.12)
        for u, v in ((1.05, 11.35), (3.17, 11.35), (1.05, 13.97), (3.17, 13.97)):
            self.ub("pergola", M["metal"], u, u + 0.08, v, v + 0.08, f2 + 0.12, f2 + 2.6)
        self.ub("pergola", M["metal"], 1.0, 3.3, 11.3, 11.42, f2 + 2.5, f2 + 2.65)
        self.ub("pergola", M["metal"], 1.0, 3.3, 13.98, 14.1, f2 + 2.5, f2 + 2.65)
        for k in range(10):
            uu = 1.08 + k * 0.23
            self.ub("pergola_slat", M["wood"], uu, uu + 0.06, 11.3, 14.1, f2 + 2.65, f2 + 2.75)
        self.fit(_sofa, 1.3, 3.0, 11.45, 12.3, "v0", f2 + 0.12)
        self.fit(_armchair, 1.3, 2.05, 13.2, 13.95, "v1", f2 + 0.12)
        self.fit(_armchair, 2.25, 3.0, 13.2, 13.95, "v1", f2 + 0.12)
        self.fit(_low_table, 1.75, 2.55, 12.5, 13.0, "v0", f2 + 0.12)
        self.put("outdoor_table_chair_set_01", 5.9, 12.9, f2 + 0.02, rot=0.4)
        for u, v in ((0.5, 15.0), (8.0, 15.0), (4.4, 10.7)):
            self.put("potted_plant_02", u, v - 0.3, f2 + 0.02, scale=1.1)
        for k in range(4):   # stepping stones from the lounge doors across the lawn
            self.ub("step_stone", M["tiles"], 3.6, 4.4, 10.7 + k * 0.95, 11.3 + k * 0.95, f2 + 0.02, f2 + 0.05)

    def facade(self):
        z, fa = "facade", self.s("facade")
        g, f1, f2, r0 = LV["G"], LV["1"], LV["2"], LV["R"]
        gf, ff, sf = self.s("groundFloor"), self.s("firstFloor"), self.s("secondFloor")
        acc = self.pal["accent"]
        if fa >= FI and gf >= S and ff >= S:
            # car-porch canopy: steel frame with louvres, cantilevered from the first-floor slab
            u0, u1, v0, v1, zc = 5.78, 8.72, 15.18, 18.9, f1 - SLAB - 0.35
            for r in ((u0, u1, v1 - 0.12, v1), (u0, u0 + 0.12, v0, v1 - 0.12), (u1 - 0.12, u1, v0, v1 - 0.12)):
                self.ub("canopy", M["metal"], *r, zc, zc + 0.16)
            for k in range(int((v1 - v0 - 0.2) / 0.22)):
                vv = v0 + 0.08 + k * 0.22
                self.ub("canopy_louvre", M["metal"], u0 + 0.12, u1 - 0.12, vv, vv + 0.08, zc + 0.03, zc + 0.13)
        if fa < R:
            return
        if gf >= FI:
            for k in range(6):   # grooved cladding on the porch walls
                zz = g + 0.45 * (k + 1)
                self.ub("groove", M["groove"], 4.91, 6.50, 14.48, 14.495, zz, zz + 0.02)
                self.ub("groove", M["groove"], 6.50, 6.515, 12.74, 14.48, zz, zz + 0.02)
            for k in range(9):   # timber louvres over the powder-room window
                uu = 5.17 + k * 0.11
                self.ub("louvre", M["wood"], uu, uu + 0.05, 14.48, 14.56, g + 1.6, g + 2.5)
            self.ub("soffit", M["wood"], 6.50, 8.54, 12.74, 14.88, f1 - SLAB - 0.04, f1 - SLAB)
            for u in (6.9, 7.9):
                self.ub("walllight", M["metal"], u - 0.06, u + 0.06, 12.74, 12.86, g + 2.85, g + 3.15)
                self.ub("walllight_glow", M["lamp"], u - 0.045, u + 0.045, 12.86, 12.87, g + 2.9, g + 3.1)
        if ff >= FI:
            # deep frame around the bedroom window, timber soffit + downlights in the balcony frame
            for r in ((5.53, 8.07, 2.6, 2.82), (5.53, 8.07, 0.38, 0.6), (5.53, 5.75, 0.6, 2.6), (7.85, 8.07, 0.6, 2.6)):
                self.ub("picture_frame", M[acc], r[0], r[1], 15.18, 15.6, f1 + r[2], f1 + r[3])
            self.ub("soffit", M["wood"], 0.0, 4.79, 15.18, 16.68, f2 - SLAB - 0.04, f2 - SLAB)
            for u in (1.0, 2.4, 3.8):
                self.ub("downlight", M["downlight"], u - 0.06, u + 0.06, 15.9, 16.02, f2 - SLAB - 0.055, f2 - SLAB - 0.04)
        if sf >= FI:
            # projecting slot window on the top floor, lined in timber
            for r in ((5.8, 8.2, 2.0, 2.22), (5.8, 8.2, 1.08, 1.3), (5.8, 6.0, 1.3, 2.0), (8.0, 8.2, 1.3, 2.0)):
                self.ub("slot_frame", M[acc], r[0], r[1], 10.38, 10.8, f2 + r[2], f2 + r[3])
            for r in ((6.0, 8.0, 1.98, 2.0), (6.0, 8.0, 1.3, 1.32)):
                self.ub("slot_lining", M["wood"], r[0], r[1], 10.38, 10.8, f2 + r[2], f2 + r[3])
            for u0, u1 in ((6.0, 6.02), (7.98, 8.0)):
                self.ub("slot_lining", M["wood"], u0, u1, 10.38, 10.8, f2 + 1.32, f2 + 1.98)
            for r in ((-0.63, 8.54, 0.0, 0.12), (-0.63, -0.51, 0.12, 10.83), (-0.63, 5.45, 10.83, 10.95),
                      (5.33, 5.45, 10.38, 10.83), (5.45, 8.54, 10.26, 10.38), (8.42, 8.54, 0.12, 10.26)):
                self.ub("coping", M["copper"], r[0] - 0.02, r[1] + 0.02, r[2] - 0.02, r[3] + 0.02, r0 + 0.3, r0 + 0.34)

    def land(self):
        z, st = "landscape", self.s("landscape")
        (pu0, pu1), (pv0, pv1) = P8_PLOT_U, P8_PLOT_V
        hw = P8_W / 2
        # plot ground up to the footpath (y -7.6), plus a green strip behind the rear wall
        self.ub("ground", M["soil"], pu0, pu1, pv0, 20.46, -0.06, 0.02)
        self.ub("ground", M["lawn"], pu0, pu1, pv0 - 2.9, pv0, -0.06, 0.0)
        yf0, yf1 = self.ur("v", 19.46, 19.66)
        yb0, yb1 = self.ur("v", -2.36, -2.16)
        if st == F:
            self.box("wall_footing", M["rcc"], -hw, hw, yf0, yf1, 0.02, 0.2)
        else:
            wm = M["block"] if st == S else (M["plaster"] if st == FI else M[self.pal["gf"]])
            fh = 1.0
            for u0, u1, h in ((pu0, 4.55, fh), (4.55, 4.85, 1.3), (5.75, 6.05, 1.3), (10.45, pu1, 1.3)):
                self.ub("cwall", wm, u0, u1, 19.46, 19.66, 0.0, h)
            # side walls: each plot draws its -x side, the last plot of a row closes the +x side
            self.box("cwall", wm, -hw - 0.1, -hw + 0.1, yb0, yf1, 0.0, 1.5)
            if self.last:
                self.box("cwall", wm, hw - 0.1, hw + 0.1, yb0, yf1, 0.0, 1.5)
            for u0, u1 in (((pu0 + 0.1, 0.0), (5.85, pu1 - 0.1)) if self.servant else ((pu0 + 0.1, pu1 - 0.1),)):
                self.ub("cwall", wm, u0, u1, -2.36, -2.16, 0.0, 2.1)
            if st >= R:
                self.ub("cwall_cap", M["copper"], pu0, 4.55, 19.43, 19.69, fh, fh + 0.03)
                for u0, u1 in ((4.55, 4.85), (5.75, 6.05), (10.45, pu1)):
                    self.ub("pillar_lamp", M["lamp"], u0 + 0.04, u1 - 0.04, 19.48, 19.64, 1.3, 1.38)
                    self.ub("pillar_cap", M["metal"], u0, u1, 19.44, 19.68, 1.38, 1.42)
                for k in range(7):   # timber-slat gates: pedestrian + sliding car gate
                    zz = 0.12 + k * 0.15
                    self.ub("gate", M["wood"], 6.05, 10.45, 19.53, 19.59, zz, zz + 0.11)
                    self.ub("pgate", M["wood"], 4.85, 5.75, 19.53, 19.59, zz, zz + 0.11)
                self.ub("gate_frame", M["metal"], 6.05, 10.45, 19.52, 19.6, 1.16, 1.2)
                self.ub("plate", M["copper"], 3.85, 4.45, 19.66, 19.69, 0.35, 0.85)
                if not EXPORT:
                    cu = bpy.data.curves.new("villa_no", "FONT")
                    cu.body, cu.size, cu.extrude = self.no, 0.2, 0.004
                    cu.align_x, cu.align_y = "CENTER", "CENTER"
                    cu.materials.append(M["groove"])
                    to = bpy.data.objects.new("villa_no", cu)
                    to.location = (self.ox + self.X(4.15), self.Y(19.695), 0.6)
                    to.rotation_euler = (math.radians(90), 0, 0)
                    self.coll.objects.link(to)
        if st >= FI:
            for r in ((5.83, 10.65, 14.48, 19.46), (4.91, 5.83, 15.78, 19.46), (6.50, 10.65, 14.30, 14.48),
                      (8.54, 10.65, 12.74, 14.30), (8.54, 9.95, -2.16, 12.74), (2.48, 8.54, -1.15, 0.0),
                      (5.85, 8.54, -2.16, -1.15), (4.55, pu1, 19.66, 20.46)):
                self.ub("pavers", M["pavers"], *r, 0.0, 0.12)
        if st >= R:
            lawns = [(pu0 + 0.1, 0.0, -2.16, 4.6), (pu0 + 0.1, 0.0, 10.48, 19.46), (0.0, 4.29, 17.38, 19.46),
                     (0.0, 1.6, 16.78, 17.38), (2.8, 4.29, 16.78, 17.38)]
            if not self.servant:
                lawns.append((0.0, 5.85, -2.16, 0.0))
            for r in lawns:
                self.lawn(*r)
            self.ub("planter", M["soil"], 4.29, 4.91, 15.78, 19.46, 0.0, 0.14)
            self.ub("planter", M["soil"], 9.95, 10.65, -2.16, 14.30, 0.0, 0.14)
            self.planting()
        elif st <= S and self.main:
            # site material: block stacks and a sand heap on the front lawn
            self.ub("block_stack", M["block"], 0.4, 1.6, 17.6, 18.4, 0.02, 0.95)
            self.ub("block_stack", M["block"], 1.9, 2.9, 17.7, 18.3, 0.02, 0.7)
            x, y = self.X(3.6), self.Y(18.2)
            self.sand_pile(x, y, 0.9, 0.7)

    def planting(self):
        P = self.put
        tropical = (("anthurium_botany_01", (0, 1, 2), 2.0), ("calathea_orbifolia_01", (0, 1, 2), 2.2),
                    ("fern_02", (1, 2), 1.7))

        def clump(u, v, z=0.1, big=1.0):
            aid, vs, sc = random.choice(tropical)
            P(aid, u, v, z, variant=random.choice(vs), scale=sc * big * random.uniform(0.85, 1.15))

        (pu0, pu1), _ = P8_PLOT_U, P8_PLOT_V
        # street planter outside the front wall (hedge + flowers), shrubs inside rising above it
        self.ub("planter", M["soil"], pu0, 4.55, 19.66, 20.41, 0.0, 0.18)
        self.hedge_u(pu0 + 0.1, 4.4, 19.7, 20.1, 0.18, 0.7)
        for k in range(12):
            P("periwinkle_plant", pu0 + 0.35 + k * 0.55, 20.25, 0.18, scale=random.uniform(1.0, 1.4))
        for u in (-1.6, 0.6, 2.8):
            P("searsia_lucida", u, 19.0, 0.1, variant=1, scale=random.uniform(0.95, 1.2))
        for u, v in ((0.4, 17.0), (3.9, 17.0), (-1.7, 14.5), (-1.7, 12.0), (-1.7, 3.6), (-1.7, 1.2), (4.6, 16.4),
                     (4.6, 17.6), (4.6, 18.8)):
            clump(u, v)
        self.hedge_u(10.0, 10.6, -2.0, 14.2, 0.14, 0.95)
        for u, v in ((-1.5, 18.6), (-1.5, 17.0)):
            P("searsia_lucida", u, v, 0.1, variant=0, scale=0.75)
        P("searsia_burchellii", -1.3, -1.3, 0.1, scale=0.4)
        P("potted_plant_01", 6.75, 13.4, LV["G"])
        P("potted_plant_02", 8.3, 13.4, LV["G"])
        P("potted_plant_02", 0.4, 16.4, LV["G"])


# ============================================================================ site
STREET_LAMPS = []


def street_lamp(b, x, y, h=4.2):
    """Modern pole lamp: slim dark pole, flat disc head with a glowing underside."""
    b.box("lamp_pole", M["metal"], x - 0.05, x + 0.05, y - 0.05, y + 0.05, 0.15, h)
    b.box("lamp_base", M["metal"], x - 0.12, x + 0.12, y - 0.12, y + 0.12, 0.15, 0.45)
    b.box("lamp_head", M["metal"], x - 0.32, x + 0.32, y - 0.32, y + 0.32, h, h + 0.06)
    b.box("lamp_glow", M["lamp"], x - 0.26, x + 0.26, y - 0.26, y + 0.26, h - 0.02, h)
    STREET_LAMPS.append((x, y, h))


def build_site(xs0, xs1, spacing=12.4, framing_trees=True):
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
    for k in range(int(xs0 // spacing) - 1, int(xs1 // spacing) + 2):
        for x, y in ((k * spacing + spacing / 2, -8.35), (k * spacing, -18.1)):
            street_lamp(lamps, x, y)
    lamps.flush()
    # mature trees behind the row (between roofs) and framing the street
    for x in np.arange(xs0 - spacing / 2, xs1 + spacing, spacing):
        LIB.place(site, "jacaranda_tree", float(x) + random.uniform(-1.5, 1.5), 37.0 + random.uniform(-1, 3), 0,
                  scale=random.uniform(0.75, 0.9))
    if framing_trees:
        # keep the whole canopy (and the web sprite's crossed quads) clear of the outermost plots
        vs = LIB.variants("jacaranda_tree")
        half = max(list(vs[0]["size"])) * 0.7 * 0.52 + 0.5 if vs else 9.5
        for x in (xs0 - half, xs1 + half):
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
    lin = _srgb_to_lin(px[:, :3])
    sat = spec.get("sat", 1.0)
    if sat != 1.0:   # same as the shader's Hue/Saturation node: blend toward the pixel's luminance
        lum = (lin @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[:, None]
        lin = lum + (lin - lum) * sat
    lin = lin * np.array(spec["tint"], dtype=np.float32)
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
    for sub in ("tex", "spr"):   # regenerated below; drop files left over from an older model
        for f in os.listdir(os.path.join(out_dir, sub)):
            if f.endswith(".webp"):
                os.remove(os.path.join(out_dir, sub, f))
    # geometry: the client villa once per uniform stage, finished neighbours, shared site
    phase8 = ARGS.model == "phase8"
    zones = P8_ZONES if phase8 else ZONES
    for s_ in range(4):
        CUR["tag"] = f"s{s_}"
        random.seed(ARGS.seed)
        if phase8:
            Phase8Villa(0.0, {z: s_ for z in zones}, ARGS.villa_no, True, ARGS.type, ARGS.palette).build()
        else:
            Villa(0.0, {z: s_ for z in zones}, ARGS.villa_no, True).build()
    for k in (-1, 1):
        CUR["tag"] = "nb"
        random.seed(ARGS.seed + k * 31)
        if phase8:
            Phase8Villa(k * P8_W, READY, "", False, {"B": "C", "C": "B", "C1": "B"}[ARGS.type],
                        "grey" if ARGS.palette == "tan" else "tan", last=k == 1).build()
        else:
            Villa(k * 12.4, READY, f"{8 + k:02d}", False).build()
    CUR["tag"], CUR["zone"] = "site", "site"
    random.seed(ARGS.seed)
    if phase8:
        build_site(-1.5 * P8_W, 1.5 * P8_W, P8_W)
    else:
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
        "stages": list(STAGES), "zones": list(zones), "model": ARGS.model,
        "materials": mats, "sprites": sprites,
        "sky": {"day": "sky/day.hdr", "dusk": "sky/dusk.hdr", "dayPano": "sky/day.jpg", "duskPano": "sky/dusk.jpg",
                "sunAzimuthDeg": -128, "sunElevationDeg": 48},
        "parts": [dict({"t": t, "z": z, "m": m, "b": b}, **({"lid": 1} if lid else {}))
                  for (t, z, m, lid), b in WEB["parts"].items()],
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
digits = "".join(ch for ch in ARGS.villa_no if ch.isdigit())
numbers = int(digits) if digits else 8
if ARGS.model == "phase8":
    # a row of Phase 8 villas; neighbours alternate type (mirror) and colour scheme
    other = {"B": "C", "C": "B", "C1": "B"}[ARGS.type]
    alt = "grey" if ARGS.palette == "tan" else "tan"
    prefix = ARGS.villa_no[:ARGS.villa_no.find(digits)] if digits else ""
    for k in range(-N_SIDE, N_SIDE + 1):
        main = k == 0
        random.seed(ARGS.seed if main else ARGS.seed + k * 31)
        Phase8Villa(k * P8_W, STAGE if main else READY,
                    ARGS.villa_no if main else f"{prefix}{numbers + k:02d}", main,
                    ARGS.type if main else other, ARGS.palette if k % 2 == 0 else alt,
                    ARGS.cutaway if main else None, last=k == N_SIDE).build()
    random.seed(ARGS.seed)
    xs0, xs1 = -N_SIDE * P8_W - P8_W / 2, N_SIDE * P8_W + P8_W / 2
    build_site(xs0, xs1, P8_W, framing_trees=not ARGS.cutaway)
else:
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
    # Phase 8 villa (house spans x -4.25..4.29, front y -2.9, terrace z 7.35, roof z 10.8)
    "p8front":  ((8.5, -19.0, 1.6), (0.2, -1.2, 5.3), 24, True),
    "p8left":   ((-12.0, -20.5, 1.7), (-1.0, -0.5, 5.2), 26, True),
    "p8aerial": ((-17.0, -27.0, 18.0), (0.4, 2.5, 3.6), 30, False),
    "p8cut":    ((-6.0, -10.5, 22.0), (0.3, 4.6, 0.5), 30, False),
}
loc, tgt, lens, level = VIEWS[ARGS.view]
if ARGS.view == "p8cut" and ARGS.cutaway == "ff":
    loc, tgt = (loc[0], loc[1], loc[2] + LV["1"]), (tgt[0], tgt[1], tgt[2] + LV["1"])
camera(loc, tgt, lens, level)

# ============================================================================ render
os.makedirs(os.path.dirname(os.path.abspath(ARGS.out)), exist_ok=True)
log(f"scene ready in {time.time() - T_START:.1f}s; rendering {W}x{H} {ARGS.view}/{ARGS.time} -> {ARGS.out}")
bpy.ops.render.render(write_still=True)
log("done:", ARGS.out, "exists:", os.path.exists(ARGS.out), f"total {time.time() - T_START:.1f}s")
