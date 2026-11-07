"""Detect maps that hold one value everywhere, so no texture is loaded for them."""
import numpy as np

try:
    import bpy
except ImportError:            # pure-Python use (unit tests)
    bpy = None

TOL = 1.0 / 255.0
_CH = {"R": 0, "G": 1, "B": 2}
# (image name, file path, size) -> per-channel values. Kept in memory: images are never written to,
# they may belong to the user's source material.
_cache = {}
_full_reads = 0                 # how many images had all their pixels read (tests)
PROBE = 64                      # side of the small copy used to rule out non-uniform images cheaply


def uniform_value(arr, tol=TOL):
    """Mean of `arr` (channel values in 0..1) if every value is within `tol` of it, else None."""
    if arr.size == 0:
        return None
    m = float(arr.mean())
    return m if float(arr.max()) - m <= tol and m - float(arr.min()) <= tol else None


def _pixels(img):
    n = img.channels
    px = np.empty(img.size[0] * img.size[1] * n, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(-1, n)


def _spread_too_wide(img, tol):
    """Per channel: True when a small copy already proves the image is not uniform. Averages of a
    region lie between its min and max, so a spread wider than 2*tol in the copy exists in the image."""
    if img.size[0] * img.size[1] <= PROBE * PROBE or img.source not in ("FILE", "TILED") or img.is_dirty:
        return [False, False, False]      # a copy of an in-memory image comes out blank: no shortcut
    small = img.copy()
    try:
        small.scale(PROBE, PROBE)
        px = _pixels(small)
    finally:
        bpy.data.images.remove(small)
    n = px.shape[1]
    return [float(px[:, min(i, n - 1)].max() - px[:, min(i, n - 1)].min()) > 2 * tol for i in range(3)]


def _key(img):
    return (img.name_full, img.filepath, tuple(img.size))


def _read(img):
    """Per-channel uniform values of an image (R, G, B), -1.0 where not uniform. Cached in memory."""
    global _full_reads
    k = _key(img)
    if k in _cache:
        return list(_cache[k])
    wide = _spread_too_wide(img, TOL)
    if all(wide):
        vals = [-1.0, -1.0, -1.0]
    else:
        _full_reads += 1
        px = _pixels(img)
        n = px.shape[1]
        vals = []
        for i in range(3):
            v = None if wide[i] else uniform_value(px[:, min(i, n - 1)])
            vals.append(-1.0 if v is None else v)
        del px
    _cache[k] = tuple(vals)
    return vals


def image_constant(img, chan=None):
    """chan None: (r, g, b) if all three channels are uniform. chan 'R'/'G'/'B': that channel's value.
    None when not uniform."""
    vals = _read(img)
    if chan is None:
        return None if min(vals) < 0.0 else tuple(vals)
    v = vals[_CH[chan]]
    return None if v < 0.0 else v
