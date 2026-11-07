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
