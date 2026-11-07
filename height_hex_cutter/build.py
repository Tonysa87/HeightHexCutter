"""Build a new <name>_HHC material from a MapSet and add it to an object."""
import copy

import bpy

from . import groups

FRAME_LABELS = {"sampler": "Sampler", "textures": "Textures", "displacement": "Displacement"}
DISP_SCALE = 0.02
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


def build_material(ms, base_name):
    """New material `<base_name>_HHC` built from `ms`. Neither `ms` nor its sources are modified."""
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
    co, s_nodes = _sampler(b, ms, hx)
    b.link(co.outputs["Closure"], hhc.inputs["Sampler"])
    b.frame("sampler", s_nodes)

    # textures read once, through the HHC Vector
    texs, seps, socks, y = {}, {}, {}, 500
    for ch in TEXTURE_ORDER:
        r = ms.maps.get(ch)
        if r is None or r.image is None:
            continue
        if r.image.name not in texs:
            label = "ORM" if r.chan is not None else ch
            texs[r.image.name] = _image_node(b, r.image, -350, y, label, hhc.outputs["Vector"])
            y -= 300
        t = texs[r.image.name]
        socks[ch] = _channel_socket(b, t, r.chan, seps, -80, t.location.y)
    b.frame("textures", list(texs.values()) + list(seps.values()))

    _apply_principled(bsdf, ms.principled)
    col = ms.maps.get("Base Color")
    if "Base Color" in socks:
        if "AO" in socks:
            mix = b.node("ShaderNodeMix", 30, 520, data_type="RGBA", blend_type="MULTIPLY")
            mix.inputs["Factor"].default_value = 1.0
            b.link(socks["Base Color"], mix.inputs[6])
            b.link(socks["AO"], mix.inputs[7])
            b.link(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            b.link(socks["Base Color"], bsdf.inputs["Base Color"])
    elif col is not None and col.constant is not None:
        _set_input(bsdf.inputs["Base Color"], col.constant)
    for ch in ("Roughness", "Metallic"):
        r = ms.maps.get(ch)
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
        b.link(disp.outputs["Displacement"], out.inputs["Displacement"])
        b.frame("displacement", [disp])
        mat.displacement_method = "BUMP"
    return mat


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
