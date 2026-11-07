"""Generate tiny texture sets for the tests: python3 tests/fixtures/make_sets.py

64x64 8-bit PNGs with seeded smooth noise, named like real libraries (Megascans/Fab, Poly Haven,
ambientCG...). Output: tests/fixtures/sets/<set>/ (git-ignored, regenerated at will).
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sets")
N = 64


def smooth(seed, cells=8):
    rng = np.random.default_rng(seed)
    g = rng.random((cells + 1, cells + 1))
    x = np.linspace(0, cells, N, endpoint=False)
    i = x.astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = g[np.ix_(i, i)] * (1 - f)[:, None] + g[np.ix_(i, i + 1)] * f[:, None]
    b = g[np.ix_(i + 1, i)] * (1 - f)[:, None] + g[np.ix_(i + 1, i + 1)] * f[:, None]
    v = a * (1 - f)[None, :] + b * f[None, :]
    return (v - v.min()) / (v.max() - v.min())


def gray(v):
    return Image.fromarray((np.clip(v, 0, 1) * 255).round().astype(np.uint8)).convert("L")


def rgb(r, g, b):
    return Image.fromarray((np.clip(np.dstack([r, g, b]), 0, 1) * 255).round().astype(np.uint8)).convert("RGB")


def normal_from(h, strength=4.0):
    gy, gx = np.gradient(h)
    n = np.dstack([-gx * strength * N / 8, -gy * strength * N / 8, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5          # OpenGL convention


def main():
    h = smooth(1)
    col = rgb(smooth(2) * 0.6 + 0.2, smooth(3) * 0.5 + 0.2, smooth(4) * 0.4 + 0.2)
    ao = gray(0.4 + 0.6 * h)
    rough = gray(0.5 + 0.4 * smooth(5))
    zero = gray(np.zeros((N, N)))
    half = gray(np.full((N, N), 0.5))
    ngl = normal_from(h)
    nrm_gl = rgb(ngl[..., 0], ngl[..., 1], ngl[..., 2])
    nrm_dx = rgb(ngl[..., 0], 1.0 - ngl[..., 1], ngl[..., 2])
    arm = rgb(0.4 + 0.6 * h, 0.5 + 0.4 * smooth(5), np.zeros((N, N)))
    sets = {
        "megascans": {"T_rock_4K_BaseColor": col, "T_rock_4K_AO": ao, "T_rock_4K_Roughness": rough,
                      "T_rock_4K_Metallic": zero, "T_rock_4K_Normal": nrm_gl, "T_rock_4K_Height": gray(h)},
        "polyhaven_orm": {"rock_diff_2k": col, "rock_arm_2k": arm, "rock_nor_gl_2k": nrm_gl,
                          "rock_disp_2k": gray(h)},
        "ambientcg_noheight": {"Ground_Color": col, "Ground_AmbientOcclusion": ao, "Ground_NormalGL": nrm_gl,
                               "Ground_Roughness": rough},
        "noheight_noao": {"wall_basecolor": col, "wall_normal": nrm_gl, "wall_roughness": rough},
        "directx": {"bark_Color": col, "bark_NormalDX": nrm_dx, "bark_Height": gray(h)},
        "extras": {"x_basecolor": col, "x_emission": rough, "x_opacity": rough, "x_H": half},
        "gl_and_dx": {"y_color": col, "y_normal_gl": nrm_gl, "y_normal_dx": nrm_dx},
    }
    for s, files in sets.items():
        d = os.path.join(OUT, s)
        os.makedirs(d, exist_ok=True)
        for name, im in files.items():
            im.save(os.path.join(d, name + ".png"))
    print(OUT)


if __name__ == "__main__":
    main()
