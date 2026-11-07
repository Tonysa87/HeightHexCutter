"""Build a new <name>_HHC material from a MapSet and add it to an object."""
import copy

import bpy

from . import groups
from .collect import image_channel

FRAME_LABELS = {"sampler": "Sampler", "textures": "Textures", "displacement": "Displacement (not connected)"}
DISP_SCALE = 0.02
FALLBACK_SCALE = 0.5            # repeats per metre when the object has no usable UVs (2 m per texture)
CHAN_OUT = {"R": 0, "G": 1, "B": 2}
TEXTURE_ORDER = ("Base Color", "AO", "Roughness", "Metallic")
FRAME_COLORS = {"sampler": (0.20, 0.16, 0.10), "textures": (0.12, 0.17, 0.12), "displacement": (0.20, 0.12, 0.12)}


class _Builder:
    def __init__(self, mat):
        self.nt = mat.node_tree
        self.L = self.nt.links

    def node(self, idname, x, y, label="", **props):
        n = self.nt.nodes.new(idname)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (x, y)
        if label:
            n.label = label
        return n

    def link(self, a, b):
        self.L.new(a, b)

    def frame(self, key, nodes):
        fr = self.nt.nodes.new("NodeFrame")
        fr.label = FRAME_LABELS[key]
        fr.use_custom_color = True
        fr.color = FRAME_COLORS[key]
        fr.label_size = 16
        for n in nodes:
            n.parent = fr
        return fr


def _image_node(b, img, x, y, label, vector):
    t = b.node("ShaderNodeTexImage", x, y, label)
    t.image = img
    b.link(vector, t.inputs["Vector"])
    return t


def _channel_socket(b, tex, chan, seps, x, y):
    """Output socket of `tex` for one channel (None = Color); one Separate Color per packed image."""
    if chan is None:
        return tex.outputs["Color"]
    if tex.name not in seps:
        sp = b.node("ShaderNodeSeparateColor", x, y)
        b.link(tex.outputs["Color"], sp.inputs[0])
        seps[tex.name] = sp
    return seps[tex.name].outputs[CHAN_OUT[chan]]


# ---------------------------------------------------------------------------- copying source nodes
_SKIP = {"rna_type", "name", "location", "location_absolute", "parent", "select", "dimensions", "type",
         "inputs", "outputs", "internal_links", "is_active_output", "width_hidden", "warning_propagation"}


def _sock(coll, src):
    """Socket of `coll` matching `src` by identifier, then name, then position."""
    for x in coll:
        if x.identifier == src.identifier:
            return x
    if src.name in coll:
        return coll[src.name]
    i = list(src.node.inputs if src.is_output is False else src.node.outputs).index(src)
    return coll[i] if i < len(coll) else None


def _copy_ramp(dst, src):
    d, s = dst.color_ramp, src.color_ramp
    d.interpolation, d.color_mode, d.hue_interpolation = s.interpolation, s.color_mode, s.hue_interpolation
    while len(d.elements) < len(s.elements):
        d.elements.new(0.5)
    while len(d.elements) > len(s.elements):
        d.elements.remove(d.elements[-1])
    for de, se in zip(d.elements, s.elements):
        de.position, de.color = se.position, tuple(se.color)


def _copy_curves(dst, src):
    d, s = dst.mapping, src.mapping
    for dc, sc in zip(d.curves, s.curves):
        while len(dc.points) < len(sc.points):
            dc.points.new(0.5, 0.5)
        while len(dc.points) > len(sc.points):
            dc.points.remove(dc.points[-1])
        for dp, sp in zip(dc.points, sc.points):
            dp.location, dp.handle_type = tuple(sp.location), sp.handle_type
    d.update()


def copy_node(nt, src):
    """Copy of `src` in `nt`: same type, properties and unlinked input values."""
    n = nt.nodes.new(src.bl_idname)
    props = [p.identifier for p in src.bl_rna.properties if not p.is_readonly and p.identifier not in _SKIP]
    for _ in range(2):                    # twice: some properties (data_type) change which others exist
        for k in props:
            try:
                setattr(n, k, getattr(src, k))
            except (AttributeError, TypeError, ValueError, RuntimeError):
                pass
    for si in src.inputs:
        di = _sock(n.inputs, si)
        if di is not None and hasattr(si, "default_value"):
            try:
                di.default_value = si.default_value
            except (AttributeError, TypeError, ValueError):
                pass
    if getattr(src, "color_ramp", None) is not None:
        _copy_ramp(n, src)
    if getattr(src, "mapping", None) is not None and hasattr(src.mapping, "curves"):
        _copy_curves(n, src)
    return n


def _copy_chain(b, ms, r, texs, bsdf):
    """Recreate the source nodes between the image(s) and the Principled input `r.target`."""
    names = {n.name for n in r.chain}
    sb = ms.source_bsdf
    copies = {}
    for n in r.chain:
        if n.bl_idname != "ShaderNodeTexImage":
            c = copy_node(b.nt, n)
            c.location = (n.location_absolute - sb.location_absolute) + bsdf.location
            copies[n.name] = c
    for l in ms.source_tree.links:
        if l.is_muted or l.from_node.name not in names:
            continue
        if l.to_node.name in copies:
            to = _sock(copies[l.to_node.name].inputs, l.to_socket)
        elif l.to_node == sb and l.to_socket.name == r.target:
            to = bsdf.inputs[r.target]
        else:
            continue
        fn = l.from_node
        src_node = texs[fn.image] if fn.bl_idname == "ShaderNodeTexImage" else copies[fn.name]
        frm = _sock(src_node.outputs, l.from_socket)
        if frm is not None and to is not None:
            b.link(frm, to)
    return list(copies.values())


def _label_for(img, default):
    ch = image_channel(img)[0]
    return default if ch is None else ch


def _set_input(sock, v):
    if sock.type == "RGBA":
        vv = v if isinstance(v, tuple) else (v, v, v)
        sock.default_value = (vv[0], vv[1], vv[2], 1.0)
    else:
        sock.default_value = v if not isinstance(v, tuple) else 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def _apply_principled(bsdf, values):
    for k, v in values.items():
        if k.startswith("@"):                              # node property (distribution, subsurface_method)
            try:
                setattr(bsdf, k[1:], v)
            except (AttributeError, TypeError):
                pass
        elif k in bsdf.inputs and not bsdf.inputs[k].is_linked:
            try:
                bsdf.inputs[k].default_value = v
            except (TypeError, ValueError):
                pass


def _sampler(b, ms, hhc_x):
    """Closure zone with Height (or its fallback) and Normal. Returns (closure output node, nodes)."""
    x0 = hhc_x - 1100
    ci = b.node("NodeClosureInput", x0, -150)
    co = b.node("NodeClosureOutput", x0 + 820, -150)
    ci.pair_with_output(co)
    co.input_items.new("VECTOR", "Vector")
    co.output_items.new("FLOAT", "Height")
    co.output_items.new("RGBA", "Normal")
    vec = ci.outputs["Vector"]
    nodes, seps = [ci, co], {}
    h = ms.maps.get("Height")
    if h is not None and h.image is not None:
        label = "Height" if not h.fallback else "Height from AO"
        t = _image_node(b, h.image, x0 + 220, 0, label, vec)
        nodes.append(t)
        b.link(_channel_socket(b, t, h.chan, seps, x0 + 520, 0), co.inputs["Height"])
    elif ms.maps.get("Base Color") is not None and ms.maps["Base Color"].image is not None:
        c = ms.maps["Base Color"]
        t = _image_node(b, c.image, x0 + 220, 0, "Base Color", vec)
        bw = b.node("ShaderNodeRGBToBW", x0 + 500, 40)
        ramp = b.node("ShaderNodeValToRGB", x0 + 500, -40, "Height from Base Color (adjust)")
        b.link(_channel_socket(b, t, c.chan, seps, x0 + 500, 120), bw.inputs["Color"])
        b.link(bw.outputs["Val"], ramp.inputs["Fac"])
        b.link(ramp.outputs["Color"], co.inputs["Height"])
        nodes += [t, bw, ramp]
    n = ms.maps.get("Normal")
    if n is not None and n.image is not None:
        t = _image_node(b, n.image, x0 + 220, -320, "Normal", vec)
        nodes.append(t)
        b.link(t.outputs["Color"], co.inputs["Normal"])
    nodes += list(seps.values())
    return co, nodes


def _height_fallback(ms):
    """Spec order: Height -> AO -> Base Color (handled in _sampler) -> none."""
    if "Height" not in ms.maps and ms.maps.get("AO") is not None and ms.maps["AO"].image is not None:
        ao = ms.maps["AO"]
        ms.maps["Height"] = type(ao)(ao.image, chan=ao.chan, fallback=True)


def build_material(ms, base_name, ob=None):
    """New material `<base_name>_HHC` built from `ms`. Neither `ms` nor its sources are modified.
    `ob`: the object that will receive it; the node Scale is computed from its UVs (see estimate_scale),
    unless the source was an HHC material, whose node settings are kept."""
    ms = copy.copy(ms)
    ms.maps = dict(ms.maps)
    _height_fallback(ms)
    real_height = "Height" in ms.maps and not ms.maps["Height"].fallback
    mat = bpy.data.materials.new(base_name + "_HHC")
    nt = mat.node_tree
    nt.nodes.clear()
    b = _Builder(mat)
    hx = -650
    out = b.node("ShaderNodeOutputMaterial", 600, 300)
    bsdf = b.node("ShaderNodeBsdfPrincipled", 250, 300)
    b.link(bsdf.outputs["BSDF"], out.inputs["Surface"])
    hhc = b.node("ShaderNodeGroup", hx, 100)
    hhc.node_tree = groups.ensure_group()
    hhc.width = 220
    if ms.normal_dx:
        hhc.inputs["Normal Map"].default_value = "DirectX"
    hhc.inputs["Normal Strength"].default_value = ms.normal_strength
    if ms.node_values:
        for k, v in ms.node_values.items():
            if k in hhc.inputs and hasattr(hhc.inputs[k], "default_value"):
                try:
                    hhc.inputs[k].default_value = v
                except (TypeError, ValueError):
                    pass
    elif ob is not None:
        hhc.inputs["Scale"].default_value = estimate_scale(ob, ms.uv_scale)
    co, s_nodes = _sampler(b, ms, hx)
    b.link(co.outputs["Closure"], hhc.inputs["Sampler"])
    b.frame("sampler", s_nodes)

    # textures read once, through the HHC Vector
    texs, seps, socks, y = {}, {}, {}, 500
    chained = [ch for ch in ("Base Color", "Roughness", "Metallic")
               if ms.maps.get(ch) is not None and ms.maps[ch].chain and ms.maps[ch].image is not None]

    def tex(img, label):
        nonlocal y
        if img not in texs:
            texs[img] = _image_node(b, img, -350, y, label, hhc.outputs["Vector"])
            y -= 300
        return texs[img]

    for ch in TEXTURE_ORDER:
        r = ms.maps.get(ch)
        if r is None or r.image is None:
            continue
        if ch in chained:
            for n in r.chain:
                if n.bl_idname == "ShaderNodeTexImage":
                    tex(n.image, ch if n.image == r.image else _label_for(n.image, "Texture"))
            continue
        if ch == "AO" and "Base Color" in chained:
            continue                      # the source decides how AO is used (copied with its chain)
        t = tex(r.image, "ORM" if r.chan is not None else ch)
        socks[ch] = _channel_socket(b, t, r.chan, seps, -80, t.location.y)
    b.frame("textures", list(texs.values()) + list(seps.values()))
    for ch in chained:
        _copy_chain(b, ms, ms.maps[ch], texs, bsdf)

    _apply_principled(bsdf, ms.principled)
    col = ms.maps.get("Base Color")
    if "Base Color" in chained:
        pass
    elif "Base Color" in socks:
        if "AO" in socks:
            mix = b.node("ShaderNodeMix", 30, 520, data_type="RGBA", blend_type="MULTIPLY")
            mix.inputs["Factor"].default_value = 1.0
            b.link(socks["Base Color"], mix.inputs[6])
            b.link(socks["AO"], mix.inputs[7])
            b.link(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            b.link(socks["Base Color"], bsdf.inputs["Base Color"])
    elif col is not None and col.constant is not None:
        if "AO" in socks:                 # uniform colour, textured AO: still multiply
            mix = b.node("ShaderNodeMix", 30, 520, data_type="RGBA", blend_type="MULTIPLY")
            mix.inputs["Factor"].default_value = 1.0
            _set_input(mix.inputs[6], col.constant)
            b.link(socks["AO"], mix.inputs[7])
            b.link(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            _set_input(bsdf.inputs["Base Color"], col.constant)
    for ch in ("Roughness", "Metallic"):
        r = ms.maps.get(ch)
        if ch in chained:
            continue
        if ch in socks:
            b.link(socks[ch], bsdf.inputs[ch])
        elif r is not None and r.constant is not None:
            _set_input(bsdf.inputs[ch], r.constant)
    if ms.maps.get("Normal") is not None:
        b.link(hhc.outputs["Normal"], bsdf.inputs["Normal"])
    if real_height:
        disp = b.node("ShaderNodeDisplacement", 250, -450)
        disp.inputs["Scale"].default_value = ms.disp_scale if ms.disp_scale is not None else DISP_SCALE
        disp.inputs["Midlevel"].default_value = 0.5
        b.link(hhc.outputs["Height"], disp.inputs["Height"])
        # not linked to the output: Blender's bump re-runs the node at offset points, each with its own
        # random cell choice (lines in Cycles, ~2x cost). Link it by hand for true displacement.
        b.frame("displacement", [disp])
    return mat


def estimate_scale(ob, uv_scale=1.0):
    """HHC Scale (repeats per metre) that gives the texture the size it has with the object's UVs:
    uv_scale / (metres per UV unit), metres per UV unit = sqrt(world area / UV area) of the active UV map."""
    import numpy as np
    me = getattr(ob, "data", None)
    if ob is None or ob.type != "MESH" or me is None or me.uv_layers.active is None:
        return FALLBACK_SCALE
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    if nt == 0:
        return FALLBACK_SCALE
    tl = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tl)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) @ np.array(ob.matrix_world.to_3x3()).T
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    p = co[lv[tl]].reshape(-1, 3, 3)
    a_world = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum()
    u = uv[tl].reshape(-1, 3, 2)
    e1, e2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
    a_uv = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
    if a_uv < 1e-12 or a_world <= 0.0:
        return FALLBACK_SCALE
    return float(uv_scale / np.sqrt(a_world / a_uv))


def assign_to_object(ob, mat):
    """Add `mat` to `ob`: fills an empty last slot, else appends a slot (first slot if none).
    The slot becomes active. Returns its index."""
    if ob is None or not hasattr(ob.data, "materials"):
        raise ValueError("The active object cannot hold materials")
    slots = ob.material_slots
    if len(slots) and slots[-1].material is None:
        i = len(slots) - 1
        slots[i].material = mat
    else:
        ob.data.materials.append(mat)
        i = len(ob.material_slots) - 1
    ob.active_material_index = i
    return i
