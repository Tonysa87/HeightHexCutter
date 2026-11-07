"""Entry points: Asset Browser context menu, Shader Editor N panel (tab HHC) and their operators."""
import json
import os

import bpy

from . import build, collect

MESH_LIKE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME"}


# ---------------------------------------------------------------------------- conversions
def check_object(ob):
    if ob is None:
        raise ValueError("Select an object to receive the new material")
    if ob.type not in MESH_LIKE or ob.data is None or not hasattr(ob.data, "materials"):
        raise ValueError(f"'{ob.name}' cannot hold materials")
    if ob.data.library is not None or ob.data.override_library is not None:
        raise ValueError(f"'{ob.name}' uses linked data: its materials cannot be changed")


def _finish(ms, base_name, ob):
    mat = build.build_material(ms, base_name)
    build.assign_to_object(ob, mat)
    report = f"{mat.name}: {ms.summary()}"
    if ob.data.users > 1:
        report += f" | mesh shared by {ob.data.users} objects: the slot was added to all of them"
    return mat, report


def convert_material(src, ob):
    """New <src>_HHC material from a material of the file. Returns (material, report)."""
    check_object(ob)
    return _finish(collect.from_material(src), src.name, ob)


def convert_files(paths, name, ob):
    """New <name>_HHC material from image files. Returns (material, report)."""
    check_object(ob)
    ms = collect.from_files(paths)
    if not ms.maps:
        raise ValueError("No texture map recognised in the selected files")
    return _finish(ms, name, ob)


def _key(im):
    return collect._key(im.filepath, im.library) if im.filepath else None


def convert_asset(path, name, ob):
    """New <name>_HHC material from a material asset stored in another .blend file.
    The asset is appended temporarily; images already in this file are reused; whatever the append
    brought and the new material does not use is removed again."""
    check_object(ob)
    before = {"images": set(bpy.data.images), "groups": set(bpy.data.node_groups),
              "materials": set(bpy.data.materials), "libraries": set(bpy.data.libraries)}
    with bpy.data.libraries.load(path, link=False) as (src_data, dst_data):
        if name not in src_data.materials:
            raise ValueError(f"Material '{name}' not found in {path}")
        dst_data.materials = [name]
    src = dst_data.materials[0]
    try:
        have = {_key(im): im for im in before["images"] if _key(im)}
        for im in [i for i in bpy.data.images if i not in before["images"]]:
            k = _key(im)
            if k in have:
                im.user_remap(have[k])
                bpy.data.images.remove(im)
        return _finish(collect.from_material(src), name, ob)
    finally:
        for m in [m for m in bpy.data.materials if m not in before["materials"] and m == src]:
            bpy.data.materials.remove(m)
        for g in [g for g in bpy.data.node_groups if g not in before["groups"] and g.users == 0]:
            bpy.data.node_groups.remove(g)
        for im in [i for i in bpy.data.images if i not in before["images"] and i.users == 0]:
            bpy.data.images.remove(im)
        for lib in [lb for lb in bpy.data.libraries if lb not in before["libraries"] and lb.users == 0]:
            bpy.data.libraries.remove(lib)


# ---------------------------------------------------------------------------- operators
class _Convert:
    bl_options = {"REGISTER", "UNDO"}

    def run(self, fn, *args):
        before = set(bpy.data.materials)
        try:
            mat, report = fn(*args)
        except Exception as e:            # unreadable file, missing library...: leave nothing behind
            for m in [m for m in bpy.data.materials if m not in before]:
                for ob in bpy.data.objects:
                    if ob.data is not None and hasattr(ob.data, "materials"):
                        for i, slot_mat in enumerate(ob.data.materials):
                            if slot_mat == m:
                                ob.data.materials[i] = None
                bpy.data.materials.remove(m)
            self.report({"ERROR"}, str(e) if isinstance(e, ValueError) else f"HHC: {type(e).__name__}: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, report)
        return {"FINISHED"}


class HHC_OT_from_asset(_Convert, bpy.types.Operator):
    bl_idname = "hhc.from_asset"
    bl_label = "HHC: Use This Material"
    bl_description = "Create a new <name>_HHC anti-tiled material from this material asset and add it to the active object"

    @classmethod
    def poll(cls, context):
        a = getattr(context, "asset", None)
        return a is not None and a.id_type == "MATERIAL"

    def execute(self, context):
        a = context.asset
        ob = context.view_layer.objects.active
        if a.local_id is not None:
            return self.run(convert_material, a.local_id, ob)
        return self.run(convert_asset, a.full_library_path, a.name, ob)


_items = []      # Blender needs the enum strings to stay referenced


def _material_items(self, context):
    mats = sorted((m for m in bpy.data.materials if m.node_tree and any(
        n.bl_idname == "ShaderNodeTexImage" and n.image for n in m.node_tree.nodes)), key=lambda m: m.name.lower())
    _items[:] = [(m.name, m.name, "", "MATERIAL", i) for i, m in enumerate(mats)] or [("NONE", "(no material with textures)", "")]
    return _items


class HHC_OT_from_material(_Convert, bpy.types.Operator):
    bl_idname = "hhc.from_material"
    bl_label = "From Material…"
    bl_description = "Create a new <name>_HHC anti-tiled material from a material of this file and add it to the active object"
    bl_property = "material"

    material: bpy.props.EnumProperty(name="Material", items=_material_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        src = bpy.data.materials.get(self.material)
        if src is None:
            self.report({"ERROR"}, "No material chosen")
            return {"CANCELLED"}
        return self.run(convert_material, src, context.view_layer.objects.active)


class HHC_OT_from_files(bpy.types.Operator):
    bl_idname = "hhc.from_files"
    bl_label = "From Image Files…"
    bl_description = "Pick the image files of a texture set (multi-select) and create a new <name>_HHC material"

    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    directory: bpy.props.StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})
    filter_image: bpy.props.BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        paths = [os.path.join(self.directory, f.name) for f in self.files if f.name]
        if not paths:
            self.report({"ERROR"}, "No file selected")
            return {"CANCELLED"}
        folder = os.path.basename(os.path.normpath(self.directory)) or "Material"
        bpy.ops.hhc.name_files("INVOKE_DEFAULT", name=folder, files_json=json.dumps(paths))
        return {"FINISHED"}


class HHC_OT_name_files(_Convert, bpy.types.Operator):
    bl_idname = "hhc.name_files"
    bl_label = "New HHC Material"
    bl_description = "Name of the new material (_HHC is added)"

    name: bpy.props.StringProperty(name="Name", description="The material is called <name>_HHC")
    files_json: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "name")
        self.layout.label(text=f"Material: {self.name}_HHC")

    def execute(self, context):
        name = self.name.strip() or "Material"
        return self.run(convert_files, json.loads(self.files_json or "[]"), name, context.view_layer.objects.active)


class HHC_PT_panel(bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "HHC"
    bl_label = "Height Hex Cutter"

    @classmethod
    def poll(cls, context):
        return getattr(context.space_data, "tree_type", "") == "ShaderNodeTree"

    def draw(self, context):
        col = self.layout.column(align=True)
        col.scale_y = 1.3
        col.operator("hhc.from_material", icon="MATERIAL")
        col.operator("hhc.from_files", icon="FILEBROWSER")


def _asset_menu(self, context):
    a = getattr(context, "asset", None)
    if a is not None and a.id_type == "MATERIAL":
        self.layout.separator()
        self.layout.operator("hhc.from_asset", icon="NODE_MATERIAL")


CLASSES = (HHC_OT_from_asset, HHC_OT_from_material, HHC_OT_from_files, HHC_OT_name_files, HHC_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.ASSETBROWSER_MT_context_menu.append(_asset_menu)


def unregister():
    bpy.types.ASSETBROWSER_MT_context_menu.remove(_asset_menu)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
