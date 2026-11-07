"""Correlation of the normal *detail* (normal - geometric normal) between our Object-mode normals and the
Bump-from-height ground truth, per dominant axis/sign of the surface. Usage: python3 normal_metrics.py <dir>"""
import os
import sys

import numpy as np
from PIL import Image


def load(d, k):
    raw = np.asarray(Image.open(os.path.join(d, f"NC_{k}.png")))
    a = raw.astype(float) / (255.0 if raw.dtype == np.uint8 else 65535.0)   # PIL reads RGBA16 PNGs as 8-bit
    return a[..., :3] * 2.0 - 1.0, a[..., 3]


def corr(a, b):
    a = a - a.mean(0)
    b = b - b.mean(0)
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-12))


def main(root):
    dirs = [os.path.join(root, x) for x in sorted(os.listdir(root)) if os.path.isdir(os.path.join(root, x))] or [root]
    acc = {}
    for d in dirs:
        (ours, a), (bump, _), (geo, _) = (load(d, k) for k in ("ours", "bump", "geo"))
        valid = a > 0.999                                # fully covered object pixels
        do, db = (ours - geo), (bump - geo)
        ax = np.argmax(np.abs(geo), axis=-1)
        sg = np.take_along_axis(np.sign(geo), ax[..., None], -1)[..., 0]
        for i, an in enumerate("XYZ"):
            for s, sn in ((1, "+"), (-1, "-")):
                m = valid & (ax == i) & (sg == s)
                acc.setdefault(sn + an, [[], []])
                acc[sn + an][0].append(do[m]); acc[sn + an][1].append(db[m])
    print("normal detail: ours vs Bump-from-height (1 = same direction, 0 = unrelated, <0 = flipped)")
    for k, (A, B) in acc.items():
        A, B = np.concatenate(A), np.concatenate(B)
        if len(A) > 2000:
            print(f"  surface facing {k}: pixels {len(A):7d}  corr {corr(A, B):.3f}")


if __name__ == "__main__":
    main(sys.argv[1])
