"""EEVEE smear along the cell cuts: test variants on the bench wall copy (run inside Blender).

The wall copy AT_Wall is rendered by a frontal camera with copies of the unified-node material
(AT_v3u_obj, Projection = Object) changing only texture interpolation and Softness.
"""
import os

import bpy
import mathutils

CAM = "AT_CamWall"


def wall_camera():
    sc = bpy.data.scenes["AT_Bench"]
    cam = bpy.data.objects.get(CAM)
    if cam is None:
        cam = bpy.data.objects.new(CAM, bpy.data.cameras.new(CAM))
        sc.collection.objects.link(cam)
    cam.data.lens = 50
    # the wall copy is rotated 90 deg: its broad face looks along +X (spans y 1.08..2.94, z 0..1.44)
    cam.location = (3.3, 2.0, 0.72)
    cam.rotation_euler = (mathutils.Vector((0.03, 2.0, 0.72)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    return cam


def variant(name, interp="Linear", softness=0.03, debug=False, src="AT_v3u_obj"):
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    m = bpy.data.materials[src].copy()
    m.name = name
    nt = m.node_tree
    at = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeGroup" and n.node_tree.name == "AT Anti-Tile")
    at.inputs["Softness"].default_value = softness
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeTexImage":
            n.interpolation = interp
    if debug:   # pure cell colour as emission
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(at.outputs["Cell Color"], em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m.name


def render(BE, mat, path, engine, samples, res=(1280, 720)):
    """Render AT_Wall alone with `mat`; returns wall-clock seconds."""
    sc = bpy.data.scenes["AT_Bench"]
    wall = bpy.data.objects["AT_Wall"]
    hide = {n: bpy.data.objects[n].hide_render for n in ("AT_Plane", "AT_Statue", "AT_Wall")}
    for n in hide:
        bpy.data.objects[n].hide_render = n != "AT_Wall"
    for sl in wall.material_slots:
        sl.material = bpy.data.materials[mat]
    old_cam, old_res = sc.camera, (sc.render.resolution_x, sc.render.resolution_y)
    sc.camera = wall_camera()
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.engine = engine
    sc.cycles.samples = samples
    sc.eevee.taa_render_samples = samples
    try:
        with BE._QuietViewports():
            return BE._render(sc, path)
    finally:
        sc.camera = old_cam
        sc.render.resolution_x, sc.render.resolution_y = old_res
        for n, v in hide.items():
            bpy.data.objects[n].hide_render = v
