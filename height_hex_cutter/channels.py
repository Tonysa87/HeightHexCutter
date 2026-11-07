"""Guess the PBR channel of an image from its file name (pure Python, no bpy).

Texture sets name their maps with suffixes (``_BaseColor``, ``_diff``, ``_AO``, ``_nor_gl``, ``_H``...).
The last recognised word wins, so asset names such as ``metal_plate_diff`` still read as colour.
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
_NOISE = re.compile(r"\d+k?|v\d+|\d+x\d+")


def _words(filename):
    stem = os.path.splitext(os.path.basename(filename.replace("\\", "/")))[0].lower()
    return [t for t in re.split(r"[^a-z0-9]+", stem) if t and not _NOISE.fullmatch(t)]


def _match(words):
    for w in reversed(words):
        for ch, full in KEYS:
            if w in full:
                return ch
    joined = "".join(words)
    for ch, full in KEYS:                     # glued names: "T_xxx_BaseColor" written as one word
        if any(k in joined for k in full if len(k) >= 5):
            return ch
    if words and words[-1] in SINGLE:
        return SINGLE[words[-1]]
    return None


def detect_channel(filename):
    """Return (channel, is_directx). channel is one of CHANNELS or None when unknown."""
    words = _words(filename)
    ch = _match(words)
    dx = ch == "Normal" and ("dx" in words or "directx" in words or "".join(words).endswith("normaldx"))
    return ch, dx
