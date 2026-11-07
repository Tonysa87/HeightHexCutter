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
    if any(k.endswith("height_hex_cutter") for k in bpy.context.preferences.addons.keys()):
        return                                # an installed copy uses the same ids: do not unregister it
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
    calls = (lambda: bpy.ops.hhc.from_material(material=src.name),
             lambda: bpy.ops.hhc.name_files(name="hhc_t_x", files_json=json.dumps(set_paths(ctx, "megascans"))),
             lambda: bpy.ops.hhc.from_files("INVOKE_DEFAULT"))
    with _Registered():
        for active in (None, empty):
            bpy.context.view_layer.objects.active = active
            for call in calls:
                try:
                    r = call()
                except RuntimeError:
                    r = {"CANCELLED"}
                assert r == {"CANCELLED"}, (active, r)
    assert len(bpy.data.materials) == n, "a material was created without a valid object"


def test_op_errors_leave_nothing(ctx):
    _active_obj()
    n = len(bpy.data.materials)
    missing = ctx.tmp + "\\hhc_t_missing_diff.png"
    with _Registered():
        try:
            r = bpy.ops.hhc.name_files(name="hhc_t_missing", files_json=json.dumps([missing]))
        except RuntimeError:
            r = {"CANCELLED"}
        assert r == {"CANCELLED"}, r
        assert len(bpy.data.materials) == n
        orig = ui.build.assign_to_object          # fail after the material was built
        ui.build.assign_to_object = lambda ob, mat: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            try:
                r = bpy.ops.hhc.name_files(name="hhc_t_boom", files_json=json.dumps(set_paths(ctx, "megascans")))
            except RuntimeError:
                r = {"CANCELLED"}
        finally:
            ui.build.assign_to_object = orig
    assert r == {"CANCELLED"}, r
    assert "hhc_t_boom_HHC" not in bpy.data.materials, "half-built material left behind"


def test_asset_menu_once(ctx):
    def _asset_menu(self, context):           # stands for the same add-on loaded from another path
        pass
    _asset_menu.__module__ = "bl_ext.user_default.height_hex_cutter.ui"
    menu = bpy.types.ASSETBROWSER_MT_context_menu
    menu.append(_asset_menu)
    try:
        with _Registered():
            funcs = [f for f in menu._dyn_ui_initialize() if getattr(f, "__name__", "") == "_asset_menu"
                     and getattr(f, "__module__", "").endswith("height_hex_cutter.ui")]
            assert len(funcs) == 1, [f.__module__ for f in funcs]
    finally:
        try:
            menu.remove(_asset_menu)
        except ValueError:
            pass


def test_report_no_uv(ctx):
    me = bpy.data.meshes.new("hhc_t_nouv")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new("hhc_t_nouv", me)
    bpy.context.scene.collection.objects.link(ob)
    _, report = ui.convert_files(set_paths(ctx, "megascans"), "hhc_t_nouv", ob)
    assert "no UV map" in report, report
