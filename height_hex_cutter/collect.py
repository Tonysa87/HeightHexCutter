"""Find the maps of a texture set (image files) or of an existing material -> MapSet."""
import os

import bpy

from .channels import IMAGE_EXTS, detect_channel
from .mapset import MapRef, MapSet
from .uniform import image_constant

PACKED = (("AO", "R"), ("Roughness", "G"), ("Metallic", "B"))
GRAY = ("AO", "Roughness", "Metallic", "Height")


def _key(path, library=None):
    return os.path.normcase(os.path.normpath(bpy.path.abspath(path, library=library)))


def load_image(path):
    """(image, newly_loaded). An image already in the file with the same absolute path is reused."""
    k = _key(path)
    for im in bpy.data.images:
        if im.filepath and _key(im.filepath, im.library) == k:
            return im, False
    return bpy.data.images.load(path, check_existing=False), True


def _set_colorspace(img, channel):
    if channel == "Base Color" and (img.is_float or os.path.splitext(img.filepath)[1].lower() in (".exr", ".hdr")):
        for name in ("Linear Rec.709", "Linear"):   # EXR/HDR colour is stored linear
            try:
                img.colorspace_settings.name = name
                return
            except TypeError:
                pass
        return
    try:
        img.colorspace_settings.name = "sRGB" if channel == "Base Color" else "Non-Color"
    except TypeError:
        pass


DATA_SPACES = {"Non-Color", "Raw", "Generic Data"}


def colorspace_notes(ms):
    """Note (never fix) images whose colour space looks wrong for their channel: they may be shared
    with other materials, changing them would change those too."""
    seen = set()
    for ch, r in ms.maps.items():
        im = r.image
        if im is None or im in seen:
            continue
        seen.add(im)
        cs = im.colorspace_settings.name
        if ch == "Base Color":
            bad, want = (cs in DATA_SPACES and not im.is_float), "sRGB"
        else:
            bad, want = (cs not in DATA_SPACES and "linear" not in cs.lower()), "Non-Color"
        if bad:
            ms.notes.append(f"{im.name}: colour space {cs}, expected {want} (not changed)")


def resolve_constants(ms):
    """Replace uniform maps by values (Base Color / Roughness / Metallic) or drop them (AO / Normal /
    Height), as the spec says. Works on any MapSet."""
    for ch in list(ms.maps):
        r = ms.maps[ch]
        if r.image is None or r.constant is not None:
            continue
        if any(n.bl_idname != "ShaderNodeTexImage" for n in r.chain):
            continue                      # adjustment nodes after it: keep the texture, copy the chain
        if ch == "Base Color" or ch == "Normal":
            v = image_constant(r.image, r.chan)
            if v is not None and r.chan is not None:
                v = (v, v, v)
        else:
            v = image_constant(r.image, r.chan or "R")
        if v is None:
            continue
        if ch in ("AO", "Normal", "Height"):
            del ms.maps[ch]
            ms.notes.append(f"{r.image.name}: uniform {ch}, not used")
        else:
            ms.maps[ch] = MapRef(None, constant=v, target=r.target)


def _drop_unused(new_images, ms):
    used = {r.image for r in ms.maps.values() if r.image is not None}
    for im in new_images:
        if im not in used and im.users == 0:
            bpy.data.images.remove(im)


def from_files(paths):
    """MapSet from a list of image files (channels from the file names)."""
    ms = MapSet()
    single, orm, normal, new = {}, None, None, []
    for p in paths:
        name = os.path.basename(p.replace("\\", "/"))
        if os.path.splitext(p)[1].lower() not in IMAGE_EXTS:
            ms.ignored.append(f"{name} (not an image)")
            continue
        ch, dx = detect_channel(p)
        if ch is None:
            ms.ignored.append(name)
            continue
        if ch == "Normal" and normal is not None and (dx or not normal[1]):
            ms.ignored.append(f"{name} (duplicate Normal)")
            continue                      # keep the first normal; an OpenGL one replaces a DirectX one
        if (ch in single) or (ch == "ORM" and orm is not None):
            ms.ignored.append(f"{name} (duplicate {ch})")
            continue
        img, is_new = load_image(p)
        if is_new:
            new.append(img)
            _set_colorspace(img, "ORM" if ch == "ORM" else ch)
        if ch == "ORM":
            orm = img
        elif ch == "Normal":
            normal = (img, dx)
        else:
            single[ch] = img
    for ch, img in single.items():
        ms.maps[ch] = MapRef(img)
    if normal is not None:
        ms.maps["Normal"] = MapRef(normal[0])
        ms.normal_dx = normal[1]
    if orm is not None:
        for ch, c in PACKED:
            ms.maps.setdefault(ch, MapRef(orm, chan=c))
    resolve_constants(ms)
    _drop_unused(new, ms)
    colorspace_notes(ms)
    return ms


# ---------------------------------------------------------------------------- from a material
STOP = {"ShaderNodeTexCoord", "ShaderNodeMapping", "ShaderNodeUVMap", "ShaderNodeNormalMap", "ShaderNodeBump",
        "ShaderNodeDisplacement", "NodeGroupInput", "NodeClosureOutput", "NodeClosureInput"}
SEPARATE = {"ShaderNodeSeparateColor", "ShaderNodeSeparateRGB"}
TARGETS = ("Base Color", "Roughness", "Metallic")


def image_channel(img):
    """Channel guessed from the image file name, then from the datablock name."""
    ch, dx = detect_channel(img.filepath) if img.filepath else (None, False)
    return (ch, dx) if ch is not None else detect_channel(img.name)


def is_hhc_like(tree):
    """An HHC (or v0.5 AT) anti-tile group: closure input 'Sampler', outputs 'Vector' and 'Normal'."""
    if tree is None:
        return False
    ins = {i.name: i.socket_type for i in tree.interface.items_tree
           if i.item_type == "SOCKET" and i.in_out == "INPUT"}
    outs = {i.name for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "OUTPUT"}
    return ins.get("Sampler") == "NodeSocketClosure" and {"Vector", "Normal"} <= outs


def upstream(sock):
    """Everything feeding `sock`. Returns (leaves, nodes): leaves = [(image node, chan)], chan None or
    'R'/'G'/'B' when read through a Separate Color; nodes = the other nodes met, in visiting order.
    Stops at images, coordinate and normal/bump/displacement nodes, and HHC groups."""
    leaves, nodes, seen = [], [], set()

    def walk(s, chan):
        for l in s.links:
            if l.is_muted:
                continue
            n = l.from_node
            if n.bl_idname == "ShaderNodeTexImage":
                if n.image is not None and n not in [x for x, _ in leaves]:
                    leaves.append((n, chan))
                continue
            if n.bl_idname in STOP or (n.bl_idname == "ShaderNodeGroup" and is_hhc_like(n.node_tree)):
                continue
            c = chan
            if n.bl_idname in SEPARATE:
                i = list(n.outputs).index(l.from_socket)
                c = "RGB"[i] if i < 3 else None
            if n.name in seen:
                continue
            seen.add(n.name)
            nodes.append(n)
            for i in n.inputs:
                walk(i, c)

    walk(sock, None)
    return leaves, nodes


def _value(v):
    return v if isinstance(v, (str, int, float, bool)) else tuple(v)


def _active_output(nt):
    outs = [n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"]
    return next((n for n in outs if n.is_active_output), outs[0] if outs else None)


def _principled(nt, out):
    if out is not None and out.inputs["Surface"].is_linked:
        n = out.inputs["Surface"].links[0].from_node
        if n.bl_idname == "ShaderNodeBsdfPrincipled":
            return n
    return next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)


def _first_image(sock):
    leaves, _ = upstream(sock)
    return leaves[0] if leaves else None


def _read_principled(ms, bsdf):
    for s in bsdf.inputs:
        if not s.is_linked and hasattr(s, "default_value") and s.name not in ("Normal", "Tangent", "Coat Normal"):
            ms.principled[s.name] = _value(s.default_value)
    for prop in ("distribution", "subsurface_method"):
        ms.principled["@" + prop] = getattr(bsdf, prop)
    for target in TARGETS:
        leaves, nodes = upstream(bsdf.inputs[target])
        if not leaves:
            continue
        chain = nodes + [t for t, _ in leaves]
        if target == "Base Color":
            ao = [(t, c) for t, c in leaves if image_channel(t.image)[0] == "AO"]
            col = sorted([(t, c) for t, c in leaves if (t, c) not in ao],
                         key=lambda e: e[0].image.colorspace_settings.name != "sRGB")
            if col:
                ms.maps["Base Color"] = MapRef(col[0][0].image, col[0][1], chain=chain, target=target)
            if ao:
                ms.maps["AO"] = MapRef(ao[0][0].image, ao[0][1])
        else:
            t, c = leaves[0]
            ms.maps[target] = MapRef(t.image, c, chain=chain, target=target)
    for s in bsdf.inputs:
        if s.is_linked and s.name not in TARGETS + ("Normal",):
            for t, _ in upstream(s)[0]:
                ms.ignored.append(f"{t.image.name} ({s.name})")


def _read_normal(ms, sock):
    for l in sock.links:
        n = l.from_node
        if n.bl_idname == "NodeReroute":
            _read_normal(ms, n.inputs[0])
        elif n.bl_idname == "ShaderNodeNormalMap" and "Normal" not in ms.maps:
            e = _first_image(n.inputs["Color"])
            if e is not None:
                ms.maps["Normal"] = MapRef(e[0].image)
                ms.normal_dx = getattr(n, "convention", "OPENGL") == "DIRECTX"
                if not n.inputs["Strength"].is_linked:
                    ms.normal_strength = n.inputs["Strength"].default_value
        elif n.bl_idname == "ShaderNodeBump":
            e = _first_image(n.inputs["Height"])
            if e is not None and "Height" not in ms.maps:
                ms.maps["Height"] = MapRef(e[0].image, e[1])
            _read_normal(ms, n.inputs["Normal"])


def _read_sampler(ms, nt):
    for gn in nt.nodes:
        if gn.bl_idname != "ShaderNodeGroup" or not is_hhc_like(gn.node_tree):
            continue
        if not gn.inputs["Sampler"].is_linked:
            continue
        co = gn.inputs["Sampler"].links[0].from_node
        if co.bl_idname != "NodeClosureOutput":
            continue
        if "Normal" in co.inputs and "Normal" not in ms.maps:
            e = _first_image(co.inputs["Normal"])
            if e is not None:
                ms.maps["Normal"] = MapRef(e[0].image)
        if "Height" in co.inputs and "Height" not in ms.maps:
            leaves, nodes = upstream(co.inputs["Height"])
            if leaves:
                img, chan = leaves[0][0].image, leaves[0][1]
                guess = image_channel(img)[0]
                col = ms.maps.get("Base Color")
                ao = ms.maps.get("AO")
                if nodes or guess == "Base Color" or (col is not None and img == col.image):
                    pass                  # Base Color fallback (through RGB to BW + ramp): rebuilt by build
                elif guess == "AO" or (ao is not None and img == ao.image):
                    ms.maps["Height"] = MapRef(img, chan, fallback=True)
                else:
                    ms.maps["Height"] = MapRef(img, chan)
        for i in gn.inputs:
            if i.name not in ("Sampler", "Vector") and not i.is_linked and hasattr(i, "default_value"):
                ms.node_values[i.name] = _value(i.default_value)
        if "Normal Map" in gn.inputs:
            ms.normal_dx = gn.inputs["Normal Map"].default_value == "DirectX"
        if "Normal Strength" in gn.inputs and not gn.inputs["Normal Strength"].is_linked:
            ms.normal_strength = gn.inputs["Normal Strength"].default_value


def _fill_in(ms, nt):
    used = {r.image for r in ms.maps.values() if r.image is not None}
    for t in nt.nodes:
        if t.bl_idname != "ShaderNodeTexImage" or t.image is None or t.image in used:
            continue
        ch, dx = image_channel(t.image)
        if ch == "ORM":
            for c, k in PACKED:
                ms.maps.setdefault(c, MapRef(t.image, chan=k))
        elif ch is not None and ch not in ms.maps:
            ms.maps[ch] = MapRef(t.image)
            if ch == "Normal":
                ms.normal_dx = dx
        used.add(t.image)


def _mapping_scale(nt, ms):
    """Scale of the Mapping node in front of the source textures (repeats per UV unit), 1 if none."""
    imgs = {r.image for r in ms.maps.values() if r.image is not None}
    for t in nt.nodes:
        if t.bl_idname != "ShaderNodeTexImage" or t.image not in imgs:
            continue
        sock = t.inputs["Vector"]
        while sock.is_linked:
            n = sock.links[0].from_node
            if n.bl_idname == "ShaderNodeMapping":
                sc = n.inputs["Scale"]
                if sc.is_linked:
                    return 1.0
                sx, sy = sc.default_value[0], sc.default_value[1]
                v = (abs(sx) + abs(sy)) / 2 or 1.0
                return 1.0 / v if n.vector_type == "TEXTURE" else v
            if n.bl_idname != "NodeReroute":
                break
            sock = n.inputs[0]
    return 1.0


def from_material(mat):
    """MapSet read from a material's node structure, then completed from image file names.
    The material is only read, never modified."""
    ms = MapSet()
    nt = mat.node_tree
    if nt is None:
        return ms
    out = _active_output(nt)
    bsdf = _principled(nt, out)
    ms.source_tree = nt
    ms.source_bsdf = bsdf
    if bsdf is not None:
        _read_principled(ms, bsdf)
        _read_normal(ms, bsdf.inputs["Normal"])
    if out is not None and out.inputs["Displacement"].is_linked:
        d = out.inputs["Displacement"].links[0].from_node
        if d.bl_idname == "ShaderNodeDisplacement":
            e = _first_image(d.inputs["Height"])
            if e is not None and "Height" not in ms.maps:
                ms.maps["Height"] = MapRef(e[0].image, e[1])
            if not d.inputs["Scale"].is_linked:
                ms.disp_scale = d.inputs["Scale"].default_value
    _fill_in(ms, nt)
    _read_sampler(ms, nt)
    ms.uv_scale = _mapping_scale(nt, ms)
    resolve_constants(ms)
    colorspace_notes(ms)
    return ms
