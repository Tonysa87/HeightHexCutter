"""HHC Anti-Tile node group: interface, defaults, versioned setup."""
import bpy

from height_hex_cutter import groups

INPUTS = ["Sampler", "Projection", "Vector", "Scale", "Cell Size", "Rotation", "Seed", "Height Influence",
          "Softness", "Normal Strength", "Normal Map", "Edge Warp", "Sharpness", "Space"]
OUTPUTS = ["Vector", "Height", "Normal", "Cell Color", "Axis Color"]
DEFAULTS = {"Scale": 1.0, "Cell Size": 1.0, "Rotation": 1.0, "Seed": 0.0, "Height Influence": 1.5,
            "Softness": 0.005, "Normal Strength": 1.0, "Edge Warp": 1.0, "Sharpness": 4.0}
MENUS = {"Projection": "Object", "Normal Map": "OpenGL", "Space": "Object"}


def _material(name):
    m = bpy.data.materials.new("hhc_t_" + name)
    return m


def _group_node(mat, tree):
    n = mat.node_tree.nodes.new("ShaderNodeGroup")
    n.node_tree = tree
    return n


def _hhc_groups():
    return [g for g in bpy.data.node_groups if g.name.startswith(groups.GROUP_NAME)]


def test_group_interface(ctx):
    g = groups.ensure_group()
    assert g.name == "HHC Anti-Tile", g.name
    ins = [i.name for i in g.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"]
    outs = [i.name for i in g.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "OUTPUT"]
    assert ins == INPUTS, ins
    assert outs == OUTPUTS, outs
    vec = next(i for i in g.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"
               and i.name == "Vector")
    assert vec.hide_value, "Vector input must hide its value fields"
    n = _group_node(_material("iface"), g)
    for k, v in DEFAULTS.items():
        assert abs(n.inputs[k].default_value - v) < 1e-6, (k, n.inputs[k].default_value)
    for k, v in MENUS.items():
        assert n.inputs[k].default_value == v, (k, n.inputs[k].default_value)
    assert g.get("hhc_version") == groups.HHC_GROUP_VERSION


def test_normal_map_menu_items(ctx):
    n = _group_node(_material("menu"), groups.ensure_group())
    n.inputs["Normal Map"].default_value = "DirectX"
    assert n.inputs["Normal Map"].default_value == "DirectX"


def test_ensure_idempotent(ctx):
    a = groups.ensure_group()
    b = groups.ensure_group()
    assert a == b
    assert len(_hhc_groups()) == 1, [g.name for g in _hhc_groups()]


def test_group_versioning(ctx):
    # (a) older stamp -> rebuilt in place, users stay wired
    g = groups.ensure_group()
    g["hhc_version"] = 0
    m = _material("ver")
    n = _group_node(m, g)
    tex = m.node_tree.nodes.new("ShaderNodeTexImage")
    m.node_tree.links.new(n.outputs["Vector"], tex.inputs["Vector"])
    n.inputs["Scale"].default_value = 3.0
    g2 = groups.ensure_group()
    assert g2 == g and g2.get("hhc_version") == groups.HHC_GROUP_VERSION
    n = m.node_tree.nodes[n.name]
    assert n.outputs["Vector"].is_linked, "link lost in the rebuild"
    assert abs(n.inputs["Scale"].default_value - 3.0) < 1e-6
    # (b) an unstamped group with the HHC name is left alone
    g.name = "hhc_t_renamed"
    foreign = bpy.data.node_groups.new("HHC Anti-Tile", "ShaderNodeTree")
    g3 = groups.ensure_group()
    assert g3 != foreign and g3.get("hhc_version") == groups.HHC_GROUP_VERSION
    assert len(foreign.nodes) == 0 and "hhc_version" not in foreign
    bpy.data.node_groups.remove(foreign)
    for x in list(bpy.data.node_groups):
        if x.name.startswith("HHC Anti-Tile"):
            bpy.data.node_groups.remove(x)
    # (c) a stamped duplicate is remapped to the main group and removed
    main = groups.ensure_group()
    dup = main.copy()
    assert dup.name != main.name and dup.get("hhc_version") == groups.HHC_GROUP_VERSION
    m2 = _material("dup")
    nd = _group_node(m2, dup)
    got = groups.ensure_group()
    assert got == main
    assert m2.node_tree.nodes[nd.name].node_tree == main
    assert len(_hhc_groups()) == 1, [x.name for x in _hhc_groups()]


def test_group_update_reported(ctx):
    g = groups.ensure_group()
    g["hhc_version"] = groups.HHC_GROUP_VERSION - 1
    groups.ensure_group()
    assert f"updated to version {groups.HHC_GROUP_VERSION}" in groups.last_notice, groups.last_notice
    groups.ensure_group()
    assert groups.last_notice == "", "notice must be cleared when nothing was updated"


def test_linked_group_ignored(ctx):
    import os
    g = groups.ensure_group()
    path = os.path.join(ctx.tmp, "hhc_t_grouplib.blend")
    bpy.data.libraries.write(path, {g}, fake_user=True)
    bpy.data.node_groups.remove(g)
    with bpy.data.libraries.load(path, link=True) as (src, dst):
        dst.node_groups = ["HHC Anti-Tile"]
    linked = dst.node_groups[0]
    assert linked.library is not None
    got = groups.ensure_group()
    assert got.library is None and got != linked
    lib = linked.library
    bpy.data.node_groups.remove(linked)
    bpy.data.libraries.remove(lib)
    os.remove(path)


def _render_mean_diff(ctx, ob_a, ob_b, mat):
    import numpy as np
    sc = bpy.data.scenes.new("hhc_t_scene")
    cam = bpy.data.objects.new("hhc_t_cam", bpy.data.cameras.new("hhc_t_cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1.6
    cam.location = (0, 0, 5)
    sc.collection.objects.link(cam)
    sc.camera = cam
    sun = bpy.data.objects.new("hhc_t_sun", bpy.data.lights.new("hhc_t_sun", "SUN"))
    sun.rotation_euler = (0.9, 0, 0.5)
    sc.collection.objects.link(sun)
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 16
    sc.cycles.seed = 0
    sc.render.resolution_x = sc.render.resolution_y = 64
    pix = []
    for ob in (ob_a, ob_b):
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        sc.collection.objects.link(ob)
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        path = f"{ctx.tmp}\\hhc_t_scale_{ob.name}.png"
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True, scene=sc.name)
        sc.collection.objects.unlink(ob)
        im = bpy.data.images.load(path)
        im.name = "hhc_t_render"
        a = np.empty(64 * 64 * 4, np.float32)
        im.pixels.foreach_get(a)
        bpy.data.images.remove(im)
        pix.append(a.reshape(-1, 4)[:, :3])
    return float(np.abs(pix[0] - pix[1]).mean())


def test_object_scale_compensated(ctx):
    """A 1 m plane scaled 2x renders like a 2 m plane: Scale means repeats per metre."""
    from height_hex_cutter import build, collect
    from tests.blender.test_build import _plane
    from tests.blender.test_files import set_paths
    m = build.build_material(collect.from_files(set_paths(ctx, "megascans")), "hhc_t_scl")
    _one = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeGroup")
    _one.inputs["Scale"].default_value = 1.0
    d_uniform = _render_mean_diff(ctx, _plane("half", size=1.0, scale=(2, 2, 1)), _plane("full", size=2.0), m)
    me = bpy.data.meshes.new("hhc_t_thin")
    me.from_pydata([(-0.5, -1, 0), (0.5, -1, 0), (0.5, 1, 0), (-0.5, 1, 0)], [], [(0, 1, 2, 3)])
    thin = bpy.data.objects.new("hhc_t_thin", me)
    thin.scale = (2, 1, 1)
    bpy.context.scene.collection.objects.link(thin)
    d_nonuni = _render_mean_diff(ctx, thin, _plane("full2", size=2.0), m)
    ctx.info.update(diff_uniform=round(d_uniform, 4), diff_nonuniform=round(d_nonuni, 4))
    assert d_uniform < 0.01 and d_nonuni < 0.01, (d_uniform, d_nonuni)
