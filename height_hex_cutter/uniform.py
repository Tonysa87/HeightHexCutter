"""Detect maps that hold one value everywhere, so no texture is loaded for them."""
import numpy as np

TOL = 1.0 / 255.0
_CH = {"R": 0, "G": 1, "B": 2}
# (image name, file path, size) -> per-channel values. Kept in memory: images are never written to,
# they may belong to the user's source material.
_cache = {}


def uniform_value(arr, tol=TOL):
    """Mean of `arr` (channel values in 0..1) if every value is within `tol` of it, else None."""
    if arr.size == 0:
        return None
    m = float(arr.mean())
    return m if float(np.abs(arr - m).max()) <= tol else None


def _key(img):
    return (img.name_full, img.filepath, tuple(img.size))


def _read(img):
    """Per-channel uniform values of an image (R, G, B), -1.0 where not uniform. Cached in memory."""
    k = _key(img)
    if k in _cache:
        return list(_cache[k])
    n = img.channels
    px = np.empty(img.size[0] * img.size[1] * n, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, n)
    vals = []
    for i in range(3):
        v = uniform_value(px[:, min(i, n - 1)])
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
