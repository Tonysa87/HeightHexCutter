"""Benchmark scene and timing for the anti-tile experiments. Run inside Blender.

setup()             -> scene "AT_Bench": ortho top camera on a copy of Plane, low sun, World of the file
make_variants(src)  -> materials AT_ref_UV, AT_ref_Box, AT_hex, AT_noise from the source material
run(mat, out_dir)   -> Cycles ms/sample (warm-up, lo/hi spp) + EEVEE first/second render, saves PNGs

The user's scene and material are not modified. Displacement (Bump) is disconnected in all
variants: it re-evaluates the graph 3x and the normal map already carries the detail.
"""
import math
import os
import time

import bpy

BENCH = "AT_Bench"
REPEATS = 4.0      # texture repeats across the 2 m plane


def setup(src_obj="Plane", res=1024):
    sc = bpy.data.scenes.get(BENCH) or bpy.data.scenes.new(BENCH)
    sc.world = bpy.data.worlds.get("World")
    r = sc.render
    r.resolution_x = r.resolution_y = res
    r.resolution_percentage = 100
    r.film_transparent = False
    sc.cycles.device = "GPU"
    sc.cycles.use_adaptive_sampling = False
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 4
    col = sc.collection
    if "AT_Plane" not in bpy.data.objects:
        src = bpy.data.objects[src_obj]
        ob = src.copy()
        ob.data = src.data.copy()
        ob.name = ob.data.name = "AT_Plane"
        ob.location = (0.0, 0.0, 0.0)
        col.objects.link(ob)
    if "AT_Cam" not in bpy.data.objects:
        cam = bpy.data.objects.new("AT_Cam", bpy.data.cameras.new("AT_Cam"))
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 2.0
        cam.location = (0.0, 0.0, 5.0)
        col.objects.link(cam)
        sc.camera = cam
    if "AT_Sun" not in bpy.data.objects:
        sun = bpy.data.objects.new("AT_Sun", bpy.data.lights.new("AT_Sun", "SUN"))
        sun.data.energy = 3.0
        sun.data.angle = math.radians(1.0)
        sun.rotation_euler = (math.radians(60.0), 0.0, math.radians(30.0))   # 30 deg elevation: shows the normals
        col.objects.link(sun)
    return sc


def _texs(nt):
    return [n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage"]


def _strip_displacement(m):
    out = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    for lk in list(out.inputs["Displacement"].links):
        m.node_tree.links.remove(lk)


def _base_copy(src, name):
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    m = src.copy()
    m.name = name
    _strip_displacement(m)
    mp = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (REPEATS, REPEATS, REPEATS)
    return m, mp


def _normal_tex(nt):
    nm = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeNormalMap")
    return nm, nm.inputs["Color"].links[0].from_node


def make_variants(src_name="Painted Damaged Wall", groups=("AT Hex Dither", "AT Noise Dither")):
    src = bpy.data.materials[src_name]
    made = []
    m, mp = _base_copy(src, "AT_ref_UV")
    made.append(m.name)
    # Box: Object coordinates (plane spans -1..1 -> same repeats with half the scale)
    m, mp = _base_copy(src, "AT_ref_Box")
    nt = m.node_tree
    tc = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = (REPEATS / 2,) * 3
    for t in _texs(nt):
        t.projection = "BOX"
        t.projection_blend = 0.2
    made.append(m.name)
    for gname in groups:
        m, mp = _base_copy(src, "AT_" + gname.split()[1].lower())
        nt = m.node_tree
        gn = nt.nodes.new("ShaderNodeGroup")
        gn.node_tree = bpy.data.node_groups[gname]
        gn.location = (mp.location.x + 200, mp.location.y - 250)
        nt.links.new(mp.outputs["Vector"], gn.inputs["Vector"])
        for t in _texs(nt):
            nt.links.new(gn.outputs["Vector"], t.inputs["Vector"])
        nm, ntex = _normal_tex(nt)
        fix = nt.nodes.new("ShaderNodeGroup")
        fix.node_tree = bpy.data.node_groups["AT Normal Fix"]
        fix.location = (nm.location.x - 200, nm.location.y - 150)
        nt.links.new(ntex.outputs["Color"], fix.inputs["Color"])
        nt.links.new(gn.outputs["Angle"], fix.inputs["Angle"])
        nt.links.new(fix.outputs["Color"], nm.inputs["Color"])
        made.append(m.name)
    return made


def _render(sc, path):
    """Render and write `path` (every timed render writes, so lo/hi pay the same I/O)."""
    sc.render.filepath = path.replace("/", "\\")     # UNC path; "//" would mean blend-relative
    sc.render.image_settings.file_format = "PNG"
    t = time.perf_counter()
    bpy.ops.render.render(write_still=True, scene=sc.name)
    return time.perf_counter() - t


class _QuietViewports:
    """Rendered/Material-preview viewports compete for the GPU: switch them to Solid while timing."""

    def __enter__(self):
        self.saved = []
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == "VIEW_3D":
                    sh = a.spaces.active.shading
                    if sh.type in ("RENDERED", "MATERIAL"):
                        self.saved.append((sh, sh.type))
                        sh.type = "SOLID"
        return self

    def __exit__(self, *exc):
        for sh, t in self.saved:
            sh.type = t


def run(mat_name, out_dir, **kw):
    with _QuietViewports():
        return _run(mat_name, out_dir, **kw)


def _run(mat_name, out_dir, spp_lo=32, spp_hi=544, eevee_taa=64, do_cycles=True, do_eevee=True, reps=3,
         assign=True, tag=""):
    """Cycles: median over `reps` of (t_hi - t_lo) / (spp_hi - spp_lo); the last hi render is saved."""
    sc = bpy.data.scenes[BENCH]
    if assign:
        bpy.data.objects["AT_Plane"].material_slots[0].material = bpy.data.materials[mat_name]
    mat_name = mat_name + tag
    os.makedirs(out_dir, exist_ok=True)
    res = {"material": mat_name}
    if do_cycles:
        sc.render.engine = "CYCLES"
        # timed renders write to a local temp dir: writing over the network share is slow and noisy
        tmp = os.path.join(bpy.app.tempdir or os.environ.get("TEMP", "."), "at_bench_tmp.png")
        sc.cycles.samples = 4
        _render(sc, tmp)                              # warm-up: images, kernels
        ms = []
        for _ in range(reps):
            sc.cycles.samples = spp_lo
            t_lo = _render(sc, tmp)
            sc.cycles.samples = spp_hi
            t_hi = _render(sc, tmp)
            ms.append(1000 * (t_hi - t_lo) / (spp_hi - spp_lo))
        ms.sort()
        import shutil
        shutil.copyfile(tmp, os.path.join(out_dir, f"{mat_name}_cycles.png").replace("/", "\\"))
        res.update(cycles_ms_per_spp=round(ms[len(ms) // 2], 3), cycles_spread=round(ms[-1] - ms[0], 3))
    if do_eevee:
        sc.render.engine = "BLENDER_EEVEE"
        sc.eevee.taa_render_samples = eevee_taa
        t1 = _render(sc, os.path.join(out_dir, "_tmp.png"))
        t2 = _render(sc, os.path.join(out_dir, f"{mat_name}_eevee.png"))
        res.update(eevee_first_s=round(t1, 3), eevee_second_s=round(t2, 3),
                   eevee_compile_s=round(t1 - t2, 3))
    return res


def node_count(tree):
    """Nodes after inlining all groups (frames, reroutes and group IO excluded)."""
    n = 0
    for nd in tree.nodes:
        if nd.bl_idname == "ShaderNodeGroup" and nd.node_tree:
            n += node_count(nd.node_tree)
        elif nd.bl_idname not in ("NodeFrame", "NodeReroute", "NodeGroupInput", "NodeGroupOutput"):
            n += 1
    return n


def make_height_variant(name="AT_v1", src_name="Painted Damaged Wall", influence=1.5, softness=0.03,
                        interpolation=None):
    """Material using AT Cells + AT Pick (+ AT Normal Fix): 3 extra height-only reads."""
    src = bpy.data.materials[src_name]
    m, mp = _base_copy(src, name)
    nt = m.node_tree
    texs = _texs(nt)
    htex = next(t for t in texs if "height" in t.image.name.lower())
    cells = nt.nodes.new("ShaderNodeGroup")
    cells.node_tree = bpy.data.node_groups["AT Cells"]
    cells.location = (mp.location.x + 200, mp.location.y - 300)
    pick = nt.nodes.new("ShaderNodeGroup")
    pick.node_tree = bpy.data.node_groups["AT Pick"]
    pick.location = (cells.location.x + 500, cells.location.y)
    pick.inputs["Height Influence"].default_value = influence
    pick.inputs["Softness"].default_value = softness
    nt.links.new(mp.outputs["Vector"], cells.inputs["Vector"])
    nt.links.new(cells.outputs["Cells"], pick.inputs["Cells"])
    for i in (1, 2, 3):
        h = nt.nodes.new("ShaderNodeTexImage")
        h.image = htex.image
        h.interpolation = htex.interpolation
        h.label = f"Height {i} (AT)"
        h.location = (cells.location.x + 250, cells.location.y - 280 * i)
        nt.links.new(cells.outputs[f"Height {i}"], h.inputs["Vector"])
        nt.links.new(h.outputs["Color"], pick.inputs[f"Height {i}"])
    for t in texs:
        nt.links.new(pick.outputs["Vector"], t.inputs["Vector"])
    nm, ntex = _normal_tex(nt)
    fix = nt.nodes.new("ShaderNodeGroup")
    fix.node_tree = bpy.data.node_groups["AT Normal Fix"]
    fix.location = (nm.location.x - 200, nm.location.y - 150)
    nt.links.new(ntex.outputs["Color"], fix.inputs["Color"])
    nt.links.new(pick.outputs["Angle"], fix.inputs["Angle"])
    nt.links.new(fix.outputs["Color"], nm.inputs["Color"])
    if interpolation:
        for t in _texs(nt):
            t.interpolation = interpolation
    return m.name


def debug_view(mat_name, path, mix=0.5, samples=256):
    """Render `mat_name` with the chosen-cell colour blended over the base colour (Cycles)."""
    src = bpy.data.materials[mat_name]
    name = mat_name + "_dbg"
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    m = src.copy()
    m.name = name
    nt = m.node_tree
    pick = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeGroup" and n.node_tree.name == "AT Pick")
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    base = bsdf.inputs["Base Color"].links[0].from_socket
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.inputs["Factor"].default_value = mix
    nt.links.new(base, mx.inputs[6])
    nt.links.new(pick.outputs["Cell Color"], mx.inputs[7])
    nt.links.new(mx.outputs[2], bsdf.inputs["Base Color"])
    sc = bpy.data.scenes[BENCH]
    bpy.data.objects["AT_Plane"].material_slots[0].material = m
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    with _QuietViewports():
        _render(sc, path)
    return name


OBJ_COPIES = {"Broken Wall 01": "AT_Wall", "Antique Sculpture 03": "AT_Statue"}


def setup_objects():
    """Bench-only copies of the wall and statue (own mesh data) + a perspective camera."""
    import mathutils
    sc = bpy.data.scenes[BENCH]
    for src, dst in OBJ_COPIES.items():
        if dst not in bpy.data.objects:
            o = bpy.data.objects[src].copy()
            o.data = bpy.data.objects[src].data.copy()
            o.name = o.data.name = dst
            sc.collection.objects.link(o)
        bpy.data.objects[dst].hide_render = True
    cam = bpy.data.objects.get("AT_CamObj")
    if cam is None:
        cam = bpy.data.objects.new("AT_CamObj", bpy.data.cameras.new("AT_CamObj"))
        sc.collection.objects.link(cam)
    cam.data.lens = 35
    cam.location = (2.6, -0.6, 1.3)
    cam.rotation_euler = (mathutils.Vector((0.0, 2.7, 0.65)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    return [OBJ_COPIES[k] for k in OBJ_COPIES]


def run_objects(mat_name, out_dir, res=(1280, 720), **kw):
    """Same timing as run(), on the wall + statue copies seen by AT_CamObj (plane hidden)."""
    sc = bpy.data.scenes[BENCH]
    obs = [bpy.data.objects[n] for n in OBJ_COPIES.values()]
    plane = bpy.data.objects["AT_Plane"]
    for o in obs:
        for sl in o.material_slots:
            sl.material = bpy.data.materials[mat_name]
        o.hide_render = False
    plane.hide_render = True
    old_cam, old_res = sc.camera, (sc.render.resolution_x, sc.render.resolution_y)
    sc.camera = bpy.data.objects["AT_CamObj"]
    sc.render.resolution_x, sc.render.resolution_y = res
    try:
        with _QuietViewports():
            return _run(mat_name, out_dir, assign=False, tag="_obj", **kw)
    finally:
        sc.camera = old_cam
        sc.render.resolution_x, sc.render.resolution_y = old_res
        plane.hide_render = False
        for o in obs:
            o.hide_render = True


def make_object_variant(name="AT_v2", src_name="Painted Damaged Wall", scale=2.0, influence=1.5,
                        softness=0.03, sharpness=8.0, interpolation=None, cells_group="AT Cells Object",
                        pick_group="AT Pick", n_heights=3):
    """Object-projected material: AT Cells Object + 3 height reads + AT Pick + AT Normal Object."""
    src = bpy.data.materials[src_name]
    m, mp = _base_copy(src, name)
    nt = m.node_tree
    texs = _texs(nt)
    htex = next(t for t in texs if "height" in t.image.name.lower())
    cells = nt.nodes.new("ShaderNodeGroup")
    cells.node_tree = bpy.data.node_groups[cells_group]
    cells.location = (mp.location.x + 200, mp.location.y - 300)
    cells.inputs["Scale"].default_value = scale
    if "Sharpness" in cells.inputs:
        cells.inputs["Sharpness"].default_value = sharpness
    pick = nt.nodes.new("ShaderNodeGroup")
    pick.node_tree = bpy.data.node_groups[pick_group]
    pick.location = (cells.location.x + 500, cells.location.y)
    pick.inputs["Height Influence"].default_value = influence
    pick.inputs["Softness"].default_value = softness
    nt.links.new(cells.outputs["Cells"], pick.inputs["Cells"])
    for i in range(1, n_heights + 1):
        h = nt.nodes.new("ShaderNodeTexImage")
        h.image = htex.image
        h.interpolation = htex.interpolation
        h.label = f"Height {i} (AT)"
        h.location = (cells.location.x + 250, cells.location.y - 280 * i)
        nt.links.new(cells.outputs[f"Height {i}"], h.inputs["Vector"])
        nt.links.new(h.outputs["Color"], pick.inputs[f"Height {i}"])
    for t in texs:
        nt.links.new(pick.outputs["Vector"], t.inputs["Vector"])
    nm, ntex = _normal_tex(nt)
    no = nt.nodes.new("ShaderNodeGroup")
    no.node_tree = bpy.data.node_groups["AT Normal Object"]
    no.location = (nm.location.x, nm.location.y - 200)
    nt.links.new(ntex.outputs["Color"], no.inputs["Color"])
    nt.links.new(pick.outputs["Normal Data"], no.inputs["Normal Data"])
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    nt.links.new(no.outputs["Normal"], bsdf.inputs["Normal"])
    nt.nodes.remove(nm)
    for n in (mp, next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexCoord")):
        nt.nodes.remove(n)
    if interpolation:
        for t in _texs(nt):
            t.interpolation = interpolation
    return m.name


def _frame(nt, label, nodes, color=(0.18, 0.18, 0.18)):
    fr = nt.nodes.new("NodeFrame")
    fr.label = label
    fr.use_custom_color = True
    fr.color = color
    fr.label_size = 16
    for n in nodes:
        loc = n.location_absolute.copy()
        n.parent = fr
        n.location_absolute = loc
    return fr


def make_v3_material(name, mode="OBJECT", src_name="Painted Damaged Wall", scale=2.0, uv_scale=4.0,
                     influence=1.5, softness=0.005, interpolation=None):
    """One AT Anti-Tile node; the material's own Height and Normal images move into the Sampler closure.
    Tidy left-to-right layout: [coordinates] -> Sampler closure -> AT node -> textures -> BSDF -> output."""
    src = bpy.data.materials[src_name]
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    m = src.copy()
    m.name = name
    m.use_fake_user = True
    nt = m.node_tree
    L = nt.links
    find = lambda t: next(n for n in nt.nodes if n.bl_idname == t)
    out, bsdf = find("ShaderNodeOutputMaterial"), find("ShaderNodeBsdfPrincipled")
    tc, mp, nmap = find("ShaderNodeTexCoord"), find("ShaderNodeMapping"), find("ShaderNodeNormalMap")
    disp = find("ShaderNodeDisplacement")
    texs = _texs(nt)
    htex = next(t for t in texs if "height" in t.image.name.lower())
    ntex = nmap.inputs["Color"].links[0].from_node
    others = [t for t in texs if t not in (htex, ntex)]
    mixes = [n for n in nt.nodes if n.bl_idname == "ShaderNodeMix"]
    for lk in list(out.inputs["Displacement"].links):
        L.remove(lk)
    # Sampler closure with the material's own height + normal images
    ci, co = nt.nodes.new("NodeClosureInput"), nt.nodes.new("NodeClosureOutput")
    ci.pair_with_output(co)
    co.input_items.new("VECTOR", "Vector")
    co.output_items.new("FLOAT", "Height")
    co.output_items.new("RGBA", "Normal")
    for t in (htex, ntex):
        for lk in list(t.inputs["Vector"].links) + list(t.outputs["Color"].links):
            L.remove(lk)
        L.new(ci.outputs["Vector"], t.inputs["Vector"])
    L.new(htex.outputs["Color"], co.inputs["Height"])
    L.new(ntex.outputs["Color"], co.inputs["Normal"])
    nt.nodes.remove(nmap)
    at = nt.nodes.new("ShaderNodeGroup")
    at.node_tree = bpy.data.node_groups["AT Anti-Tile Object" if mode == "OBJECT" else "AT Anti-Tile UV"]
    at.width = 200
    L.new(co.outputs["Closure"], at.inputs["Sampler"])
    at.inputs["Height Influence"].default_value = influence
    at.inputs["Softness"].default_value = softness
    if mode == "OBJECT":
        at.inputs["Scale"].default_value = scale
        nt.nodes.remove(mp)
        nt.nodes.remove(tc)
        tc = mp = None
    else:
        mp.inputs["Scale"].default_value = (uv_scale,) * 3
        L.new(mp.outputs["Vector"], at.inputs["Vector"])
    for t in others:
        for lk in list(t.inputs["Vector"].links):
            L.remove(lk)
        L.new(at.outputs["Vector"], t.inputs["Vector"])
    L.new(at.outputs["Normal"], bsdf.inputs["Normal"])
    L.new(at.outputs["Height"], disp.inputs["Height"])
    if interpolation:
        for t in texs:
            t.interpolation = interpolation
    # ---- layout (columns, y up) ----
    def put(n, x, y):
        n.location_absolute = (x, y)
    x0 = -1500
    if tc:
        put(tc, x0 - 200, 300)
        put(mp, x0 + 20, 300)
    put(ci, x0, -250)
    put(htex, x0 + 200, -150)
    put(ntex, x0 + 200, -450)
    put(co, x0 + 520, -250)
    put(at, -700, 100)
    order = sorted(others, key=lambda t: ["diffuse", "albedo", "color", "ao", "rough", "metal"].index(
        next((k for k in ["diffuse", "albedo", "color", "ao", "rough", "metal"] if k in t.image.name.lower()), "metal")))
    for i, t in enumerate(order):
        put(t, -380, 420 - 300 * i)
    for i, mx in enumerate(mixes):
        put(mx, -60, 380 - 220 * i)
    put(bsdf, 220, 300)
    put(out, 560, 300)
    put(disp, 220, -500)
    _frame(nt, "Height + Normal  (Sampler: closure letta dal nodo AT)", [ci, htex, ntex, co], (0.20, 0.16, 0.10))
    if tc:
        _frame(nt, "Coordinate UV", [tc, mp], (0.12, 0.14, 0.20))
    _frame(nt, "Altre texture (Vector dal nodo AT)", order, (0.12, 0.17, 0.12))
    _frame(nt, "Displacement (scollegato: bump + dither = rumore)", [disp], (0.20, 0.12, 0.12))
    return m.name
