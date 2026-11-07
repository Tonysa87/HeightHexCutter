"""Building <name>_HHC materials from a MapSet, and adding them to objects."""
import bpy

from height_hex_cutter import build, collect, groups
from tests.blender.test_files import set_paths


def _of(nt, idname):
    return [n for n in nt.nodes if n.bl_idname == idname]


def _one(nt, idname):
    ns = _of(nt, idname)
    assert len(ns) == 1, (idname, [n.name for n in ns])
    return ns[0]


def _src(sock):
    assert sock.is_linked, sock.name
    return sock.links[0].from_node


def _tex(nt, label):
    return next(n for n in _of(nt, "ShaderNodeTexImage") if n.label == label)


def _make(ctx, set_name, base="hhc_t_rock"):
    return build.build_material(collect.from_files(set_paths(ctx, set_name)), base)


def _zone(nt):
    return _one(nt, "NodeClosureInput"), _one(nt, "NodeClosureOutput")


def test_build_megascans(ctx):
    m = _make(ctx, "megascans")
    nt = m.node_tree
    assert m.name == "hhc_t_rock_HHC", m.name
    hhc = _one(nt, "ShaderNodeGroup")
    assert hhc.node_tree == groups.ensure_group()
    bsdf, out = _one(nt, "ShaderNodeBsdfPrincipled"), _one(nt, "ShaderNodeOutputMaterial")
    ci, co = _zone(nt)
    assert [i.name for i in co.input_items] == ["Vector"]
    outs = {i.name: i.socket_type for i in co.output_items}
    assert outs == {"Height": "FLOAT", "Normal": "RGBA"}, outs
    assert _src(hhc.inputs["Sampler"]) == co
    h, n = _tex(nt, "Height"), _tex(nt, "Normal")
    assert _src(co.inputs["Height"]) == h and _src(co.inputs["Normal"]) == n
    assert _src(h.inputs["Vector"]) == ci and _src(n.inputs["Vector"]) == ci
    for lab in ("Base Color", "AO", "Roughness"):
        assert _src(_tex(nt, lab).inputs["Vector"]) == hhc, lab
    mix = _src(bsdf.inputs["Base Color"])
    assert mix.bl_idname == "ShaderNodeMix" and mix.data_type == "RGBA" and mix.blend_type == "MULTIPLY"
    assert abs(mix.inputs["Factor"].default_value - 1.0) < 1e-6
    assert {_src(mix.inputs[6]), _src(mix.inputs[7])} == {_tex(nt, "Base Color"), _tex(nt, "AO")}
    assert _src(bsdf.inputs["Roughness"]) == _tex(nt, "Roughness")
    assert not bsdf.inputs["Metallic"].is_linked and bsdf.inputs["Metallic"].default_value == 0.0
    assert _src(bsdf.inputs["Normal"]) == hhc
    assert not _of(nt, "ShaderNodeNormalMap")
    disp = _one(nt, "ShaderNodeDisplacement")
    assert abs(disp.inputs["Scale"].default_value - 0.02) < 1e-6
    assert abs(disp.inputs["Midlevel"].default_value - 0.5) < 1e-6
    assert _src(disp.inputs["Height"]) == hhc and _src(out.inputs["Displacement"]) == disp
    assert m.displacement_method == "BUMP"
    frames = sorted(f.label for f in _of(nt, "NodeFrame"))
    assert frames == ["Displacement", "Sampler", "Textures"], frames
    for nd in nt.nodes:
        assert nd.label.isascii(), nd.label


def test_build_no_height_ao(ctx):
    m = _make(ctx, "ambientcg_noheight")
    nt = m.node_tree
    ci, co = _zone(nt)
    hsrc = _src(co.inputs["Height"])
    assert hsrc.bl_idname == "ShaderNodeTexImage" and "AmbientOcclusion" in hsrc.image.filepath
    assert _src(hsrc.inputs["Vector"]) == ci
    assert not _of(nt, "ShaderNodeDisplacement") and not _of(nt, "ShaderNodeBump")
    assert not _one(nt, "ShaderNodeOutputMaterial").inputs["Displacement"].is_linked


def test_build_no_height_no_ao(ctx):
    m = _make(ctx, "noheight_noao")
    nt = m.node_tree
    ci, co = _zone(nt)
    ramp = _src(co.inputs["Height"])
    assert ramp.bl_idname == "ShaderNodeValToRGB" and ramp.label == "Height from Base Color (adjust)"
    bw = _src(ramp.inputs["Fac"])
    assert bw.bl_idname == "ShaderNodeRGBToBW"
    t = _src(bw.inputs["Color"])
    assert t.bl_idname == "ShaderNodeTexImage" and "basecolor" in t.image.filepath and _src(t.inputs["Vector"]) == ci
    assert not _of(nt, "ShaderNodeDisplacement")


def test_build_directx(ctx):
    m = _make(ctx, "directx")
    assert _one(m.node_tree, "ShaderNodeGroup").inputs["Normal Map"].default_value == "DirectX"


def test_build_orm(ctx):
    m = _make(ctx, "polyhaven_orm")
    nt = m.node_tree
    orm = [t for t in _of(nt, "ShaderNodeTexImage") if "arm" in t.image.filepath and _src(t.inputs["Vector"]).bl_idname == "ShaderNodeGroup"]
    assert len(orm) == 1 and orm[0].label == "ORM", [t.label for t in orm]
    sep = _one(nt, "ShaderNodeSeparateColor")
    assert _src(sep.inputs[0]) == orm[0]
    bsdf = _one(nt, "ShaderNodeBsdfPrincipled")
    rl = bsdf.inputs["Roughness"].links[0]
    assert rl.from_node == sep and rl.from_socket.identifier == sep.outputs[1].identifier
    mix = _src(bsdf.inputs["Base Color"])
    ao_link = next(l for l in (mix.inputs[6].links + mix.inputs[7].links) if l.from_node == sep)
    assert ao_link.from_socket.identifier == sep.outputs[0].identifier
    assert not bsdf.inputs["Metallic"].is_linked and bsdf.inputs["Metallic"].default_value == 0.0


def _obj(name, n_slots=0, last_empty=False):
    me = bpy.data.meshes.new("hhc_t_" + name)
    ob = bpy.data.objects.new("hhc_t_" + name, me)
    bpy.context.scene.collection.objects.link(ob)
    for i in range(n_slots):
        me.materials.append(None if (last_empty and i == n_slots - 1) else bpy.data.materials.new(f"hhc_t_s{i}"))
    return ob


def test_assign_slots(ctx):
    m = bpy.data.materials.new("hhc_t_assign_HHC")
    a = _obj("a")
    assert build.assign_to_object(a, m) == 0 and a.material_slots[0].material == m
    b = _obj("b", 2)
    assert build.assign_to_object(b, m) == 2 and len(b.material_slots) == 3
    assert b.material_slots[2].material == m and b.active_material_index == 2
    c = _obj("c", 2, last_empty=True)
    assert build.assign_to_object(c, m) == 1 and len(c.material_slots) == 2
    assert c.material_slots[1].material == m


def test_convert_twice(ctx):
    m1 = _make(ctx, "megascans")
    n_img = len(bpy.data.images)
    m2 = _make(ctx, "megascans")
    assert (m1.name, m2.name) == ("hhc_t_rock_HHC", "hhc_t_rock_HHC.001"), (m1.name, m2.name)
    assert len([g for g in bpy.data.node_groups if g.name.startswith("HHC Anti-Tile")]) == 1
    assert len(bpy.data.images) == n_img
