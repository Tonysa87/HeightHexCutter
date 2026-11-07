"""Guess the PBR channel of an image from its file name (pure Python, no bpy).

Texture sets name their maps with suffixes (``_BaseColor``, ``_diff``, ``_AO``, ``_nor_gl``, ``_H``...).
Rules, in order:
1. a single-letter last word (``T_Rusty_Metal_4K_B``) decides;
2. otherwise the words are scanned from the end: the first channel word decides, unless a word of a
   channel the add-on does not handle comes first or sits right before it (``leaf_translucency_color``,
   ``metal_plate_preview``) - then the file is ignored;
3. otherwise glued names are searched, the key found furthest right wins.
camelCase names are split into words first (``RustyMetalAlbedo``).
"""
import os
import re

CHANNELS = ("Base Color", "AO", "Roughness", "Metallic", "Normal", "Height", "ORM")
IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".tga", ".bmp", ".webp", ".hdr"))

# (channel, full-word tokens)
KEYS = (
    ("ORM", {"orm", "arm", "occlusionroughnessmetallic"}),
    ("AO", {"ao", "ambientocclusion", "occlusion", "ambient"}),
    ("Normal", {"normal", "normals", "nrm", "nor", "norm", "normalgl", "normaldx", "nrml"}),
    ("Roughness", {"roughness", "rough", "rgh"}),
    ("Metallic", {"metallic", "metalness", "metal", "mtl"}),
    ("Height", {"height", "displacement", "disp", "displace", "bump", "depth"}),
    ("Base Color", {"basecolor", "albedo", "diffuse", "diff", "color", "colour", "col", "base"}),
)
# single-letter suffix, only as the last word ("d" is left out: diffuse or DirectX?)
SINGLE = {"h": "Height", "n": "Normal", "r": "Roughness", "m": "Metallic", "b": "Base Color", "c": "Base Color"}
# words of channels the add-on does not handle, and of non-map images
OTHER = {"emission", "emissive", "emit", "opacity", "alpha", "transparency", "translucency", "transmission",
         "sss", "subsurface", "specular", "spec", "gloss", "glossiness", "cavity", "mask", "sheen", "fuzz",
         "preview", "thumbnail", "thumb", "curvature", "id"}
_NOISE = re.compile(r"\d+k?|v\d+|\d+x\d+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _words(filename):
    stem = os.path.splitext(os.path.basename(filename.replace("\\", "/")))[0]
    stem = _CAMEL.sub("_", stem).lower()
    return [t for t in re.split(r"[^a-z0-9]+", stem) if t and not _NOISE.fullmatch(t)]


def _word_channel(w):
    return next((ch for ch, full in KEYS if w in full), None)


def _match(words):
    if not words:
        return None
    if words[-1] in SINGLE:
        return SINGLE[words[-1]]
    joined = "".join(words)
    if any(k in joined for k in ("occlusionroughnessmetallic", "ambientocclusionroughnessmetallic")):
        return "ORM"
    for i in range(len(words) - 1, -1, -1):
        w = words[i]
        if w in OTHER:
            return None
        ch = _word_channel(w)
        if ch is not None:
            return None if i > 0 and words[i - 1] in OTHER else ch
    best = None                               # glued names: the key found furthest right wins
    for ch, full in KEYS:
        for k in full:
            if len(k) >= 5:
                pos = joined.rfind(k)
                if pos >= 0 and (best is None or pos + len(k) > best[0]):
                    best = (pos + len(k), ch)
    return best[1] if best else None


def detect_channel(filename):
    """Return (channel, is_directx). channel is one of CHANNELS or None when unknown."""
    words = _words(filename)
    ch = _match(words)
    dx = ch == "Normal" and ("dx" in words or "directx" in words or "".join(words).endswith("normaldx"))
    return ch, dx
