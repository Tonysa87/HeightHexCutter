"""Object-mode normal check (run inside Blender).

Renders the statue copy with three emission materials showing world normals as colours:
  ours : AT Anti-Tile Normal output (normal map undone/oriented per projection)
  bump : Bump node driven by AT Anti-Tile Height (independent ground truth for the detail direction)
  geo  : Geometry normal (no detail)
Softness is set very low so the dithered bands (where Bump is unreliable) are ~1 pixel.
"""
import bpy
import mathutils

CAM = "AT_CamStatue"


def _emit_vector(nt, sock):
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    for lk in list(out.inputs["Displacement"].links):
        nt.links.remove(lk)
    vm = nt.nodes.new("ShaderNodeVectorMath")
    vm.operation = "MULTIPLY_ADD"
    vm.inputs[1].default_value = (0.5, 0.5, 0.5)
    vm.inputs[2].default_value = (0.5, 0.5, 0.5)
    nt.links.new(sock, vm.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(vm.outputs[0], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])


def make(src="AT_v3u_obj", softness=0.0005, bump_distance=0.005, extra=None):
    made = []
    for kind in ("ours", "bump", "geo"):
        name = f"NC_{kind}"
        old = bpy.data.materials.get(name)
        if old:
            bpy.data.materials.remove(old)
        m = bpy.data.materials[src].copy()
        m.name = name
        nt = m.node_tree
        at = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeGroup" and n.node_tree.name == "AT Anti-Tile")
        at.inputs["Softness"].default_value = softness
        for k, v in (extra or {}).items():
            at.inputs[k].default_value = v
        if kind == "ours":
            _emit_vector(nt, at.outputs["Normal"])
        elif kind == "bump":
            bp = nt.nodes.new("ShaderNodeBump")
            bp.inputs["Distance"].default_value = bump_distance
            nt.links.new(at.outputs["Height"], bp.inputs["Height"])
            _emit_vector(nt, bp.outputs["Normal"])
        else:
            _emit_vector(nt, nt.nodes.new("ShaderNodeNewGeometry").outputs["Normal"])
        made.append(name)
    return made


VIEWS = {  # name: camera location (looking at the statue centre)
    "px": (2.2, 3.49, 0.75), "nx": (-2.2, 3.49, 0.75), "py": (0.0, 5.7, 0.75), "ny": (0.0, 1.3, 0.75),
    "pz": (0.05, 3.55, 3.2),
}


def render_views(BE, out_dir, samples=64, res=(700, 900)):
    sc = bpy.data.scenes["AT_Bench"]
    cam = bpy.data.objects.get("AT_CamNC")
    if cam is None:
        cam = bpy.data.objects.new("AT_CamNC", bpy.data.cameras.new("AT_CamNC"))
        sc.collection.objects.link(cam)
    cam.data.lens = 50
    for v, loc in VIEWS.items():
        cam.location = loc
        cam.rotation_euler = (mathutils.Vector((0.01, 3.49, 0.7)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        render_all(BE, f"{out_dir}/{v}", samples, res, cam="AT_CamNC")


def render_all(BE, out_dir, samples=64, res=(900, 1100), obj="AT_Statue", cam=CAM):
    sc = bpy.data.scenes["AT_Bench"]
    old_ft = sc.render.film_transparent
    sc.render.film_transparent = True
    sc.render.image_settings.color_mode = "RGBA"
    target = bpy.data.objects[obj]
    hide = {n: bpy.data.objects[n].hide_render for n in ("AT_Plane", "AT_Statue", "AT_Wall")}
    for n in hide:
        bpy.data.objects[n].hide_render = n != obj
    old_cam, old_res, old_vt = sc.camera, (sc.render.resolution_x, sc.render.resolution_y), sc.view_settings.view_transform
    old_depth = sc.render.image_settings.color_depth
    sc.camera = bpy.data.objects[cam]
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.color_depth = "16"
    try:
        with BE._QuietViewports():
            for kind in ("ours", "bump", "geo"):
                for sl in target.material_slots:
                    sl.material = bpy.data.materials[f"NC_{kind}"]
                BE._render(sc, f"{out_dir}/NC_{kind}.png")
    finally:
        sc.camera = old_cam
        sc.render.resolution_x, sc.render.resolution_y = old_res
        sc.view_settings.view_transform = old_vt
        sc.render.image_settings.color_depth = old_depth
        sc.render.film_transparent = old_ft
        sc.render.image_settings.color_mode = "RGB"
        for n, v in hide.items():
            bpy.data.objects[n].hide_render = v
