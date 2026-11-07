"""Benchmark scene and timing for HHC materials. Run inside Blender (tools/blrun.sh).

setup(prefix="HHC_")      -> scene "<prefix>Bench": its own 2 m grid plane, ortho top camera, low sun
run(mat, out_dir, ...)    -> Cycles ms/sample (warm-up, lo/hi spp) + EEVEE first/second render, saves PNGs
node_count(tree)          -> nodes after inlining groups

Nothing of the user's scene is used or modified: the bench builds its own objects.
"""
import math
import os
import time

import bpy


def names(prefix="HHC_"):
    return {k: prefix + k for k in ("Bench", "Plane", "Cam", "Sun")}


def setup(prefix="HHC_", res=1024):
    n = names(prefix)
    sc = bpy.data.scenes.get(n["Bench"]) or bpy.data.scenes.new(n["Bench"])
    sc.world = bpy.data.worlds.get("World") or sc.world
    r = sc.render
    r.resolution_x = r.resolution_y = res
    r.resolution_percentage = 100
    r.film_transparent = False
    sc.cycles.device = "GPU"
    sc.cycles.use_adaptive_sampling = False
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 4
    sc.cycles.seed = 0
    col = sc.collection
    if n["Plane"] not in bpy.data.objects:
        me = bpy.data.meshes.new(n["Plane"])
        me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        me.uv_layers.new(name="UVMap")
        ob = bpy.data.objects.new(n["Plane"], me)
        col.objects.link(ob)
    if n["Cam"] not in bpy.data.objects:
        cam = bpy.data.objects.new(n["Cam"], bpy.data.cameras.new(n["Cam"]))
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 2.0
        cam.location = (0.0, 0.0, 5.0)
        col.objects.link(cam)
    sc.camera = bpy.data.objects[n["Cam"]]
    if n["Sun"] not in bpy.data.objects:
        sun = bpy.data.objects.new(n["Sun"], bpy.data.lights.new(n["Sun"], "SUN"))
        sun.data.energy = 3.0
        sun.data.angle = math.radians(1.0)
        sun.rotation_euler = (math.radians(60.0), 0.0, math.radians(30.0))   # 30 deg elevation: shows the normals
        col.objects.link(sun)
    return sc


def render(sc, path):
    """Render `sc` and write `path`; returns the wall time in seconds."""
    sc.render.filepath = path.replace("/", "\\")     # UNC path; "//" would mean blend-relative
    sc.render.image_settings.file_format = "PNG"
    t = time.perf_counter()
    bpy.ops.render.render(write_still=True, scene=sc.name)
    return time.perf_counter() - t


class QuietViewports:
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


def run(mat_name, out_dir, prefix="HHC_", spp_lo=32, spp_hi=544, eevee_taa=64, do_cycles=True, do_eevee=True,
        reps=3):
    """Cycles: median over `reps` of (t_hi - t_lo) / (spp_hi - spp_lo); the last hi render is saved."""
    n = names(prefix)
    sc = bpy.data.scenes[n["Bench"]]
    plane = bpy.data.objects[n["Plane"]]
    plane.data.materials.clear()
    plane.data.materials.append(bpy.data.materials[mat_name])
    os.makedirs(out_dir, exist_ok=True)
    res = {"material": mat_name}
    with QuietViewports():
        if do_cycles:
            sc.render.engine = "CYCLES"
            # timed renders write to a local temp dir: writing over the network share is slow and noisy
            tmp = os.path.join(bpy.app.tempdir or os.environ.get("TEMP", "."), "hhc_bench_tmp.png")
            sc.cycles.samples = 4
            render(sc, tmp)                              # warm-up: images, kernels
            ms = []
            for _ in range(reps):
                sc.cycles.samples = spp_lo
                t_lo = render(sc, tmp)
                sc.cycles.samples = spp_hi
                t_hi = render(sc, tmp)
                ms.append(1000 * (t_hi - t_lo) / (spp_hi - spp_lo))
            ms.sort()
            import shutil
            shutil.copyfile(tmp, os.path.join(out_dir, f"{mat_name}_cycles.png"))
            res.update(cycles_ms_per_spp=round(ms[len(ms) // 2], 3), cycles_spread=round(ms[-1] - ms[0], 3))
        if do_eevee:
            sc.render.engine = "BLENDER_EEVEE"
            sc.eevee.taa_render_samples = eevee_taa
            t1 = render(sc, os.path.join(out_dir, "_tmp.png"))
            t2 = render(sc, os.path.join(out_dir, f"{mat_name}_eevee.png"))
            res.update(eevee_first_s=round(t1, 3), eevee_second_s=round(t2, 3), eevee_compile_s=round(t1 - t2, 3))
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
