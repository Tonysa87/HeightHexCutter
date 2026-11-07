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
    try:
        img.colorspace_settings.name = "sRGB" if channel == "Base Color" else "Non-Color"
    except TypeError:
        pass


def resolve_constants(ms):
    """Replace uniform maps by values (Base Color / Roughness / Metallic) or drop them (AO / Normal /
    Height), as the spec says. Works on any MapSet."""
    for ch in list(ms.maps):
        r = ms.maps[ch]
        if r.image is None or r.constant is not None:
            continue
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
            ms.maps[ch] = MapRef(None, constant=v, chain=r.chain, target=r.target)


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
        if os.path.splitext(p)[1].lower() not in IMAGE_EXTS:
            continue
        ch, dx = detect_channel(p)
        name = os.path.basename(p.replace("\\", "/"))
        if ch is None:
            ms.ignored.append(name)
            continue
        if ch == "Normal" and normal is not None and (dx or not normal[1]):
            continue                      # keep the first normal; an OpenGL one replaces a DirectX one
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
    return ms
