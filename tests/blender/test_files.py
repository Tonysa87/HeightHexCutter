"""Images and texture sets: uniform maps, loading from files."""
import numpy as np

import bpy

from height_hex_cutter.uniform import CACHE, image_constant


def _img(name, rgb_fn, size=16):
    im = bpy.data.images.new("hhc_t_" + name, size, size)
    px = np.zeros((size * size, 4), np.float32)
    px[:, 3] = 1.0
    rng = np.random.default_rng(3)
    for i, f in enumerate(rgb_fn):
        px[:, i] = f(rng, size * size)
    im.pixels.foreach_set(px.ravel())
    return im


def const(v):
    return lambda rng, n: np.full(n, v, np.float32)


def noise(rng, n):
    return rng.random(n, dtype=np.float32)


def test_image_constant(ctx):
    solid = _img("solid", (const(0.0), const(0.0), const(0.0)))
    assert image_constant(solid) == (0.0, 0.0, 0.0)
    assert image_constant(_img("noise", (noise, noise, noise))) is None
    packed = _img("packed", (noise, const(0.5), const(0.0)))
    assert abs(image_constant(packed, "G") - 0.5) <= 1 / 255
    assert image_constant(packed, "R") is None
    assert image_constant(packed, "B") == 0.0
    # cached: the pixels are not read again for the same file/size
    assert CACHE in packed
    px = np.random.default_rng(5).random(16 * 16 * 4, dtype=np.float32)
    packed.pixels.foreach_set(px)
    assert abs(image_constant(packed, "G") - 0.5) <= 1 / 255, "second call re-read the pixels"
