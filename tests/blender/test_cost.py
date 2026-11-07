"""Slow checks (run with: tools/hhc_test.sh test_cost).

1. The HHC Anti-Tile node is not heavier than the v0.5 AT Anti-Tile (same material otherwise).
2. A DirectX normal map with Normal Map = DirectX renders like the OpenGL one with OpenGL.
"""
import importlib.util

import numpy as np

import bpy

from bench import bench as BE
from height_hex_cutter import build, collect
from tests.blender.test_files import set_paths

PREFIX = "hhc_t_"


def _v05_group(ctx):
    path = ctx.root + "/tests/fixtures/v05/build_v3.py"
    spec = importlib.util.spec_from_file_location("hhc_t_v05_build_v3", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    orig = m.G
    m.G = lambda name, desc="": orig("_v05_" + name, desc)
    return m.build_tile()


def _swap_group(src, name, tree):
    """Copy of `src` whose anti-tile node uses `tree` (new node, same links and values)."""
    m = src.copy()
    m.name = name
    nt = m.node_tree
    old = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeGroup")
    gn = nt.nodes.new("ShaderNodeGroup")
    gn.node_tree = tree
    gn.location = old.location
    for s in old.inputs:
        if s.name in gn.inputs:
            for l in s.links:
                nt.links.new(l.from_socket, gn.inputs[s.name])
            if not s.is_linked and hasattr(s, "default_value") and s.type != "MENU":
                gn.inputs[s.name].default_value = s.default_value
    for s in old.outputs:
        for l in s.links:
            nt.links.new(gn.outputs[s.name], l.to_socket)
    nt.nodes.remove(old)
    gn.inputs["Projection"].default_value = "Object"
    gn.inputs["Space"].default_value = "Object"
    return m


def test_cost_vs_v05(ctx):
    BE.setup(PREFIX, res=512)
    hhc = build.build_material(collect.from_files(set_paths(ctx, "megascans")), PREFIX + "cost")
    old = _swap_group(hhc, PREFIX + "cost_v05", _v05_group(ctx))
    kw = dict(prefix=PREFIX, spp_lo=16, spp_hi=272, reps=3)
    r_old = BE.run(old.name, ctx.tmp, **kw)
    r_new = BE.run(hhc.name, ctx.tmp, **kw)
    n_old, n_new = BE.node_count(old.node_tree), BE.node_count(hhc.node_tree)
    ctx.info.update(v05=r_old, hhc=r_new, nodes_v05=n_old, nodes_hhc=n_new)
    assert r_new["cycles_ms_per_spp"] <= r_old["cycles_ms_per_spp"] * 1.05, (r_old, r_new)
    assert n_new - n_old <= 5, (n_old, n_new)


def _render_pixels(ctx, sc, mat, tag):
    plane = bpy.data.objects[PREFIX + "Plane"]
    plane.data.materials.clear()
    plane.data.materials.append(mat)
    path = f"{ctx.tmp}\\hhc_t_normal_{tag}.png"
    with BE.QuietViewports():
        BE.render(sc, path)
    im = bpy.data.images.load(path)
    im.name = PREFIX + "render_" + tag
    px = np.empty(im.size[0] * im.size[1] * 4, np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(-1, 4)[:, :3]


def test_cost_directx_normal(ctx):
    sc = BE.setup(PREFIX, res=128)
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 256
    gl = collect.from_files(set_paths(ctx, "megascans"))
    dx_paths = [p for p in set_paths(ctx, "megascans") if "Normal" not in p] + \
               [p for p in set_paths(ctx, "directx") if "NormalDX" in p]
    dx = collect.from_files(dx_paths)
    assert dx.normal_dx and not gl.normal_dx
    m_gl = build.build_material(gl, PREFIX + "ngl")
    m_dx = build.build_material(dx, PREFIX + "ndx")
    m_wrong = build.build_material(dx, PREFIX + "nwrong")
    next(n for n in m_wrong.node_tree.nodes if n.bl_idname == "ShaderNodeGroup").inputs["Normal Map"].default_value = "OpenGL"
    a = _render_pixels(ctx, sc, m_gl, "gl")
    b = _render_pixels(ctx, sc, m_dx, "dx")
    c = _render_pixels(ctx, sc, m_wrong, "wrong")
    d_ok, d_wrong = float(np.abs(a - b).mean()), float(np.abs(a - c).mean())
    ctx.info.update(diff_dx_as_dx=round(d_ok, 5), diff_dx_as_gl=round(d_wrong, 5))
    assert d_ok < 0.01, d_ok
    assert d_wrong > 3 * d_ok and d_wrong > 0.005, (d_ok, d_wrong)
