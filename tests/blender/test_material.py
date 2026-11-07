"""Converting an existing material: maps from the node structure, adjustment nodes copied as they are."""
import bpy

from height_hex_cutter import build, collect
from tests.blender.runner import _tree_fingerprint
from tests.blender.test_build import _of, _one, _src
from tests.blender.test_files import set_paths


def _imgs(ctx, set_name):
    return {p.rsplit("\\", 1)[1]: collect.load_image(p)[0] for p in set_paths(ctx, set_name)}


class Src:
    """A hand-built source material, like the ones found in asset libraries."""

    def __init__(self, name):
        self.m = bpy.data.materials.new("hhc_t_" + name)
        self.nt = self.m.node_tree
        self.nt.nodes.clear()
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")
        self.bsdf = self.nt.nodes.new("ShaderNodeBsdfPrincipled")
        self.link(self.bsdf.outputs["BSDF"], self.out.inputs["Surface"])
        self.uv = self.nt.nodes.new("ShaderNodeTexCoord")

    def link(self, a, b):
        self.nt.links.new(a, b)

    def tex(self, img):
        t = self.nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        self.link(self.uv.outputs["UV"], t.inputs["Vector"])
        return t

    def node(self, idname, **props):
        n = self.nt.nodes.new(idname)
        for k, v in props.items():
            setattr(n, k, v)
        return n


def _convert(src):
    return build.build_material(collect.from_material(src.m), src.m.name)


def test_material_basic(ctx):
    im = _imgs(ctx, "megascans")
    s = Src("basic")
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], s.bsdf.inputs["Base Color"])
    s.link(s.tex(im["T_rock_4K_Roughness.png"]).outputs["Color"], s.bsdf.inputs["Roughness"])
    nm = s.node("ShaderNodeNormalMap", convention="DIRECTX")
    nm.inputs["Strength"].default_value = 0.6
    s.link(s.tex(im["T_rock_4K_Normal.png"]).outputs["Color"], nm.inputs["Color"])
    s.link(nm.outputs["Normal"], s.bsdf.inputs["Normal"])
    d = s.node("ShaderNodeDisplacement")
    d.inputs["Scale"].default_value = 0.1
    s.link(s.tex(im["T_rock_4K_Height.png"]).outputs["Color"], d.inputs["Height"])
    s.link(d.outputs["Displacement"], s.out.inputs["Displacement"])
    m = _convert(s)
    assert m.name == "hhc_t_basic_HHC"
    hhc = _one(m.node_tree, "ShaderNodeGroup")
    assert abs(hhc.inputs["Normal Strength"].default_value - 0.6) < 1e-6
    assert hhc.inputs["Normal Map"].default_value == "DirectX"
    assert abs(_one(m.node_tree, "ShaderNodeDisplacement").inputs["Scale"].default_value - 0.1) < 1e-6
    assert not _of(m.node_tree, "ShaderNodeNormalMap")


def test_material_chains(ctx):
    im = _imgs(ctx, "megascans")
    s = Src("chains")
    inv = s.node("ShaderNodeInvert")
    s.link(s.tex(im["T_rock_4K_Roughness.png"]).outputs["Color"], inv.inputs["Color"])
    s.link(inv.outputs["Color"], s.bsdf.inputs["Roughness"])
    hs = s.node("ShaderNodeHueSaturation")
    hs.inputs["Saturation"].default_value = 1.3
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], hs.inputs["Color"])
    s.link(hs.outputs["Color"], s.bsdf.inputs["Base Color"])
    m = _convert(s)
    nt = m.node_tree
    bsdf, hhc = _one(nt, "ShaderNodeBsdfPrincipled"), _one(nt, "ShaderNodeGroup")
    inv2 = _src(bsdf.inputs["Roughness"])
    assert inv2.bl_idname == "ShaderNodeInvert"
    t = _src(inv2.inputs["Color"])
    assert t.bl_idname == "ShaderNodeTexImage" and _src(t.inputs["Vector"]) == hhc
    hs2 = _src(bsdf.inputs["Base Color"])
    assert hs2.bl_idname == "ShaderNodeHueSaturation"
    assert abs(hs2.inputs["Saturation"].default_value - 1.3) < 1e-6
    assert _src(_src(hs2.inputs["Color"]).inputs["Vector"]) == hhc


def test_material_ao_mix(ctx):
    im = _imgs(ctx, "megascans")
    s = Src("aomix")
    mix = s.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    mix.inputs["Factor"].default_value = 0.8
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], mix.inputs[6])
    s.link(s.tex(im["T_rock_4K_AO.png"]).outputs["Color"], mix.inputs[7])
    s.link(mix.outputs[2], s.bsdf.inputs["Base Color"])
    ms = collect.from_material(s.m)
    assert "AO" in ms.maps and "Base Color" in ms.maps, ms.summary()
    m = build.build_material(ms, s.m.name)
    mixes = _of(m.node_tree, "ShaderNodeMix")
    assert len(mixes) == 1, "the source AO mix must be copied, not doubled"
    assert abs(mixes[0].inputs["Factor"].default_value - 0.8) < 1e-6
    assert _src(_one(m.node_tree, "ShaderNodeBsdfPrincipled").inputs["Base Color"]) == mixes[0]


def test_material_principled_values(ctx):
    im = _imgs(ctx, "megascans")
    s = Src("values")
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], s.bsdf.inputs["Base Color"])
    s.bsdf.inputs["IOR"].default_value = 1.33
    s.bsdf.inputs["Coat Weight"].default_value = 0.2
    s.bsdf.subsurface_method = "BURLEY"
    m = _convert(s)
    b = _one(m.node_tree, "ShaderNodeBsdfPrincipled")
    assert abs(b.inputs["IOR"].default_value - 1.33) < 1e-6
    assert abs(b.inputs["Coat Weight"].default_value - 0.2) < 1e-6
    assert b.subsurface_method == "BURLEY"


def test_material_filename_fillin(ctx):
    im = _imgs(ctx, "megascans")
    s = Src("fillin")
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], s.bsdf.inputs["Base Color"])
    s.tex(im["T_rock_4K_AO.png"])                          # present but not linked
    ms = collect.from_material(s.m)
    assert ms.maps["AO"].image == im["T_rock_4K_AO.png"], ms.summary()


def test_material_at_source(ctx):
    """A v0.5 material: closure Sampler with Height + Normal feeding an anti-tile group node."""
    im = _imgs(ctx, "megascans")
    g = bpy.data.node_groups.new("hhc_t_legacy AT Anti-Tile", "ShaderNodeTree")
    g.interface.new_socket("Sampler", in_out="INPUT", socket_type="NodeSocketClosure")
    for n, t in (("Vector", "NodeSocketVector"), ("Height", "NodeSocketFloat"), ("Normal", "NodeSocketVector")):
        g.interface.new_socket(n, in_out="OUTPUT", socket_type=t)
    s = Src("legacy")
    ci, co = s.node("NodeClosureInput"), s.node("NodeClosureOutput")
    ci.pair_with_output(co)
    co.input_items.new("VECTOR", "Vector")
    co.output_items.new("FLOAT", "Height")
    co.output_items.new("RGBA", "Normal")
    for name, item in (("T_rock_4K_Height.png", "Height"), ("T_rock_4K_Normal.png", "Normal")):
        t = s.node("ShaderNodeTexImage")
        t.image = im[name]
        s.link(ci.outputs["Vector"], t.inputs["Vector"])
        s.link(t.outputs["Color"], co.inputs[item])
    gn = s.node("ShaderNodeGroup")
    gn.node_tree = g
    s.link(co.outputs["Closure"], gn.inputs["Sampler"])
    s.link(gn.outputs["Normal"], s.bsdf.inputs["Normal"])
    c = s.tex(im["T_rock_4K_BaseColor.png"])
    s.link(gn.outputs["Vector"], c.inputs["Vector"])
    s.link(c.outputs["Color"], s.bsdf.inputs["Base Color"])
    ms = collect.from_material(s.m)
    assert ms.maps["Height"].image == im["T_rock_4K_Height.png"], ms.summary()
    assert ms.maps["Normal"].image == im["T_rock_4K_Normal.png"], ms.summary()
    assert ms.maps["Base Color"].image == im["T_rock_4K_BaseColor.png"]


def test_source_material_untouched(ctx):
    im = _imgs(ctx, "megascans")
    s = Src("untouched")
    inv = s.node("ShaderNodeInvert")
    s.link(s.tex(im["T_rock_4K_Roughness.png"]).outputs["Color"], inv.inputs["Color"])
    s.link(inv.outputs["Color"], s.bsdf.inputs["Roughness"])
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], s.bsdf.inputs["Base Color"])
    nm = s.node("ShaderNodeNormalMap")
    s.link(s.tex(im["T_rock_4K_Normal.png"]).outputs["Color"], nm.inputs["Color"])
    s.link(nm.outputs["Normal"], s.bsdf.inputs["Normal"])
    me = bpy.data.meshes.new("hhc_t_untouched")
    obs = []
    for i in range(2):
        o = bpy.data.objects.new(f"hhc_t_untouched{i}", me if i == 0 else me.copy())
        bpy.context.scene.collection.objects.link(o)
        o.data.materials.append(s.m)
        obs.append(o)
    before = (_tree_fingerprint(s.nt), {n: i.colorspace_settings.name for n, i in im.items()}, s.m.users)
    _convert(s)
    after = (_tree_fingerprint(s.nt), {n: i.colorspace_settings.name for n, i in im.items()}, s.m.users)
    assert before == after
    assert all(o.material_slots[0].material == s.m for o in obs)


def test_material_hhc_source_ao_fallback(ctx):
    """Re-converting an HHC material whose sampler height is the AO fallback: still a fallback."""
    m1 = build.build_material(collect.from_files(set_paths(ctx, "ambientcg_noheight")), "hhc_t_cg")
    ms = collect.from_material(m1)
    assert ms.maps["Height"].fallback, ms.summary()
    m2 = build.build_material(ms, "hhc_t_cg2")
    assert not _of(m2.node_tree, "ShaderNodeDisplacement")


def test_material_hhc_source_color_fallback(ctx):
    m1 = build.build_material(collect.from_files(set_paths(ctx, "noheight_noao")), "hhc_t_wall")
    ms = collect.from_material(m1)
    assert "Height" not in ms.maps or ms.maps["Height"].fallback, ms.summary()
    m2 = build.build_material(ms, "hhc_t_wall2")
    assert not _of(m2.node_tree, "ShaderNodeDisplacement")
    assert any(n.label == "Height from Base Color (adjust)" for n in _of(m2.node_tree, "ShaderNodeValToRGB"))


def test_material_colorspace_note(ctx):
    im = _imgs(ctx, "megascans")
    s = Src("csnote")
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], s.bsdf.inputs["Base Color"])
    s.link(s.tex(im["T_rock_4K_Roughness.png"]).outputs["Color"], s.bsdf.inputs["Roughness"])
    im["T_rock_4K_Roughness.png"].colorspace_settings.name = "sRGB"
    ms = collect.from_material(s.m)
    assert "T_rock_4K_Roughness.png: colour space sRGB, expected Non-Color (not changed)" in ms.notes, ms.notes
    assert im["T_rock_4K_Roughness.png"].colorspace_settings.name == "sRGB"
