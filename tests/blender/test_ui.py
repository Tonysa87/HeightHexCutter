"""Operators, registration and the asset-library code path."""
import json
import os

import bpy

import height_hex_cutter
from height_hex_cutter import collect, ui
from tests.blender.test_files import set_paths
from tests.blender.test_material import Src, _imgs


def _active_obj(name="op"):
    me = bpy.data.meshes.new("hhc_t_" + name)
    ob = bpy.data.objects.new("hhc_t_" + name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    return ob


class _Registered:
    def __enter__(self):
        height_hex_cutter.register()
        return self

    def __exit__(self, *exc):
        height_hex_cutter.unregister()


def _src_material(ctx, name):
    im = _imgs(ctx, "megascans")
    s = Src(name)
    s.link(s.tex(im["T_rock_4K_BaseColor.png"]).outputs["Color"], s.bsdf.inputs["Base Color"])
    s.link(s.tex(im["T_rock_4K_Roughness.png"]).outputs["Color"], s.bsdf.inputs["Roughness"])
    return s.m


def test_register_cycle(ctx):
    height_hex_cutter.register()
    height_hex_cutter.unregister()
    with _Registered():
        for op in ("from_asset", "from_material", "from_files", "name_files"):
            assert hasattr(bpy.ops.hhc, op), op
        assert hasattr(bpy.types, "HHC_PT_panel")
    assert not hasattr(bpy.types, "HHC_PT_panel")


def test_op_from_material(ctx):
    src = _src_material(ctx, "opsrc")
    ob = _active_obj()
    ob.data.materials.append(bpy.data.materials.new("hhc_t_existing"))
    with _Registered():
        assert bpy.ops.hhc.from_material(material=src.name) == {"FINISHED"}
    assert len(ob.material_slots) == 2 and ob.material_slots[1].material.name == "hhc_t_opsrc_HHC"
    assert ob.active_material_index == 1


def test_op_name_files(ctx):
    ob = _active_obj()
    with _Registered():
        r = bpy.ops.hhc.name_files(name="hhc_t_Ground", files_json=json.dumps(set_paths(ctx, "ambientcg_noheight")))
    assert r == {"FINISHED"}
    assert ob.material_slots[0].material.name == "hhc_t_Ground_HHC"


def test_report_text(ctx):
    ob = _active_obj()
    mat, report = ui.convert_files(set_paths(ctx, "megascans"), "hhc_t_rep", ob)
    assert mat.name == "hhc_t_rep_HHC"
    assert report.startswith("hhc_t_rep_HHC: Base Color=") and "Metallic=0 (constant)" in report, report
    shared = bpy.data.objects.new("hhc_t_shared", ob.data)
    bpy.context.scene.collection.objects.link(shared)
    _, report2 = ui.convert_files(set_paths(ctx, "megascans"), "hhc_t_rep", ob)
    assert "shared by 2 objects" in report2, report2


def test_asset_external_library(ctx):
    src = _src_material(ctx, "libsrc")
    src.asset_mark()
    path = os.path.join(ctx.tmp, "hhc_t_library.blend")
    bpy.data.libraries.write(path, {src}, fake_user=True)
    bpy.data.materials.remove(src)
    for im in [i for i in bpy.data.images if "T_rock_4K_Roughness" in i.filepath]:
        bpy.data.images.remove(im)                # roughness only in the library: must be appended
    kept = next(i for i in bpy.data.images if "T_rock_4K_BaseColor" in i.filepath)
    n_libs = len(bpy.data.libraries)
    imgs_before = set(bpy.data.images)
    ob = _active_obj()
    mat, _ = ui.convert_asset(path, "hhc_t_libsrc", ob)
    assert mat.name == "hhc_t_libsrc_HHC" and ob.material_slots[0].material == mat
    assert "hhc_t_libsrc" not in bpy.data.materials, "appended source material left in the file"
    col = [i for i in bpy.data.images if "T_rock_4K_BaseColor" in i.filepath]
    assert col == [kept], [i.name for i in col]
    new = [i for i in bpy.data.images if i not in imgs_before]
    assert [i.name for i in new if i.users == 0] == [], "orphan images left by the append"
    assert any("T_rock_4K_Roughness" in i.filepath for i in new), "roughness should have come from the library"
    assert len(bpy.data.libraries) == n_libs
    os.remove(path)


def test_no_valid_object(ctx):
    src = _src_material(ctx, "noobj")
    n = len(bpy.data.materials)
    empty = bpy.data.objects.new("hhc_t_empty", None)
    bpy.context.scene.collection.objects.link(empty)
    with _Registered():
        for active in (None, empty):
            bpy.context.view_layer.objects.active = active
            try:
                r = bpy.ops.hhc.from_material(material=src.name)
            except RuntimeError:
                r = {"CANCELLED"}
            assert r == {"CANCELLED"}, (active, r)
    assert len(bpy.data.materials) == n, "a material was created without a valid object"
