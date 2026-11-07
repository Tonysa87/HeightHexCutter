"""Images and texture sets: uniform maps, loading from files."""
import numpy as np

import bpy

from height_hex_cutter import uniform
from height_hex_cutter.uniform import image_constant


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
    # cached in memory, never on the image (images may belong to the user's source material)
    assert len(packed.keys()) == 0, list(packed.keys())
    assert any(k[0] == packed.name_full for k in uniform._cache), "not cached"
    px = np.random.default_rng(5).random(16 * 16 * 4, dtype=np.float32)
    packed.pixels.foreach_set(px)
    assert abs(image_constant(packed, "G") - 0.5) <= 1 / 255, "second call re-read the pixels"


# ---------------------------------------------------------------------------- loading texture sets
import os  # noqa: E402

from height_hex_cutter import collect  # noqa: E402


def set_paths(ctx, name):
    d = ctx.sets + "\\" + name
    return [d + "\\" + f for f in sorted(os.listdir(d))]


def _cs(ref):
    return ref.image.colorspace_settings.name


def test_files_megascans(ctx):
    ms = collect.from_files(set_paths(ctx, "megascans"))
    for ch in ("Base Color", "AO", "Roughness", "Normal", "Height"):
        assert ch in ms.maps and ms.maps[ch].image is not None, (ch, ms.summary())
    assert ms.maps["Metallic"].image is None and ms.maps["Metallic"].constant == 0.0, ms.summary()
    assert ms.normal_dx is False
    assert _cs(ms.maps["Base Color"]) == "sRGB"
    for ch in ("AO", "Roughness", "Normal", "Height"):
        assert _cs(ms.maps[ch]) == "Non-Color", ch
    assert not any("T_rock_4K_Metallic" in im.filepath for im in bpy.data.images), "uniform map left loaded"


def test_files_orm(ctx):
    ms = collect.from_files(set_paths(ctx, "polyhaven_orm"))
    ao, ro = ms.maps["AO"], ms.maps["Roughness"]
    assert ao.image is ro.image and ao.image.name.startswith("rock_arm"), ms.summary()
    assert (ao.chan, ro.chan) == ("R", "G")
    assert ms.maps["Metallic"].constant == 0.0 and ms.maps["Metallic"].image is None
    assert "Normal" in ms.maps and "Height" in ms.maps


def test_files_directx(ctx):
    assert collect.from_files(set_paths(ctx, "directx")).normal_dx is True


def test_files_gl_and_dx(ctx):
    ms = collect.from_files(set_paths(ctx, "gl_and_dx"))
    assert ms.normal_dx is False and ms.maps["Normal"].image.name.startswith("y_normal_gl"), ms.summary()


def test_files_extras(ctx):
    ms = collect.from_files(set_paths(ctx, "extras"))
    assert ms.ignored == ["x_emission.png", "x_opacity.png"], ms.ignored
    assert "Height" not in ms.maps, ms.summary()
    assert any("x_H.png" in n for n in ms.notes), ms.notes


def test_files_reuse(ctx):
    ms = collect.from_files(set_paths(ctx, "megascans"))
    n = len(bpy.data.images)
    ms.maps["Roughness"].image.colorspace_settings.name = "Linear Rec.709"
    ms2 = collect.from_files(set_paths(ctx, "megascans"))
    assert len(bpy.data.images) == n, "images loaded twice"
    assert ms2.maps["Roughness"].image is ms.maps["Roughness"].image
    assert _cs(ms2.maps["Roughness"]) == "Linear Rec.709", "colour space of an existing image changed"
