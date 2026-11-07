"""Detail loss along the cell cuts (numpy only). Usage: python3 band_metrics.py <dir with EB_*.png>"""
import os
import sys

import numpy as np
from PIL import Image


def load(f):
    return np.asarray(Image.open(f).convert("RGB")).astype(float)


def box(a, r):
    """Mean over a (2r+1)^2 window (edge-padded)."""
    p = np.pad(a, r, mode="edge")
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s / (k * k)


def dilate(m, it):
    for _ in range(it):
        p = np.pad(m, 1)
        m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return m


def erode(m, it):
    return ~dilate(~m, it)


def detail(img, mask):
    y = img @ [0.2126, 0.7152, 0.0722]
    m, m2 = box(y, 2), box(y * y, 2)
    return np.sqrt(np.maximum(m2 - m * m, 0))[mask].mean()


def main(d):
    dbg = load(os.path.join(d, "EB_dbg_cy64.png"))
    bg = dbg[5, 5]
    wall = np.abs(dbg - bg).sum(-1) > 25
    g = np.zeros(dbg.shape[:2])
    g[:, 1:] = np.abs(np.diff(dbg, axis=1)).sum(-1)
    g[1:, :] = np.maximum(g[1:, :], np.abs(np.diff(dbg, axis=0)).sum(-1))
    core = erode(wall, 10)
    edges = (g > 60) & core
    band = dilate(edges, 4) & core
    inner = core & ~dilate(edges, 12)
    print(f"pixels: wall {wall.sum()}  band {band.sum()}  inner {inner.sum()}")
    ref = load(os.path.join(d, "EB_Linear_s0.03_cy1024.png"))
    print(f"{'variant':30s} {'detail band':>11s} {'inner':>7s} {'band/inner':>10s} {'diff vs Cycles (band)':>22s}")
    for f in sorted(x for x in os.listdir(d) if x.startswith("EB_") and "dbg" not in x):
        im = load(os.path.join(d, f))
        db, di = detail(im, band), detail(im, inner)
        print(f"{f[:-4]:30s} {db:11.2f} {di:7.2f} {db / di:10.2f} {np.abs(im - ref).mean(-1)[band].mean():22.2f}")


if __name__ == "__main__":
    main(sys.argv[1])
