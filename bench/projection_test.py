"""Projection-priority test: materials using a renamed test build of AT Anti-Tile (run inside Blender).
Creates NEW group nodes (never swaps node_tree on an existing node: that crashed Blender 5.2)."""
import bpy


def build_test_group(V3):
    orig = V3.G
    V3.G = lambda name, desc="": orig("_test_" + name, desc)
    try:
        return V3.build_tile()
    finally:
        V3.G = orig


def make(name, src="AT_v3u_obj", tree="_test_AT Anti-Tile", **values):
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    m = bpy.data.materials[src].copy()
    m.name = name
    m.use_fake_user = True          # bench materials are often unassigned: keep them when the file is saved
    nt = m.node_tree
    old_n = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeGroup" and n.node_tree.name.startswith("AT Anti-Tile"))
    vals = {s.name: s.default_value for s in old_n.inputs
            if hasattr(s, "default_value") and not s.is_linked and s.type not in ("MENU", "VECTOR")}
    li = [(s.name, l.from_socket) for s in old_n.inputs for l in s.links]
    lo = [(s.name, l.to_socket) for s in old_n.outputs for l in s.links]
    gn = nt.nodes.new("ShaderNodeGroup")
    gn.node_tree = bpy.data.node_groups[tree]
    gn.location = old_n.location_absolute.copy()
    gn.width = old_n.width
    nt.nodes.remove(old_n)
    for k, fs in li:
        nt.links.new(fs, gn.inputs[k])
    for k, ts in lo:
        nt.links.new(gn.outputs[k], ts)
    vals.update(values)
    for k, v in vals.items():
        if k in gn.inputs:
            gn.inputs[k].default_value = v
    gn.inputs["Projection"].default_value = "Object"
    gn.inputs["Space"].default_value = "Object"
    return m.name
