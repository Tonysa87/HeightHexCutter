"""Anti-tile v1: hex cells whose borders follow the height map (names provisional).

  AT Cells   Vector -> Height 1/2/3 (coordinates to read the height map), Cells (bundle)
  AT Pick    Cells + Height 1/2/3 -> Vector (to every Image Texture), Angle (to AT Normal Fix)
  AT Normal Fix  (from v0)

Every point lies in a triangle of three hex-cell centres (triangular lattice, spacing =
Cell Size). Each candidate cell i has a barycentric weight w_i (1 at its centre, 0 on the
far edge; equal weights = the hex border) and its own random offset + rotation. Pick reads
the height of the three candidates and gives cell i the priority

    p_i = w_i * (1 + Height Influence * h_i)

so near a border the locally "higher" texture wins and the cut follows the shapes of the
texture. Only candidates within Softness of the best one are kept, and one of them is
chosen per render sample (probability proportional to how close it is), so the narrow
transition is blended by the renderer's sample accumulation. Maps other than height are
read once, at the chosen cell.
"""
import importlib.util
import math
import os

import bpy

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("ngkit", os.path.join(_here, "ngkit.py"))
ngkit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ngkit)
G = ngkit.G

SQ3 = math.sqrt(3.0)
TAU = 2.0 * math.pi
BUNDLE = [("V1", "VECTOR"), ("V2", "VECTOR"), ("V3", "VECTOR"), ("W", "VECTOR"), ("A", "VECTOR"),
          ("C1", "VECTOR"), ("C2", "VECTOR"), ("C3", "VECTOR"),     # C: debug colour per cell
          # projection frame (tangent T, bitangent B, axis N), surface normal Ng in the same space,
          # F = 1 when that space is World (0 = Object). Constant for UV coordinates.
          ("T", "VECTOR"), ("B", "VECTOR"), ("N", "VECTOR"), ("Ng", "VECTOR"), ("F", "FLOAT")]
NORMAL_DATA = [("Angle", "FLOAT"), ("T", "VECTOR"), ("B", "VECTOR"), ("N", "VECTOR"), ("Ng", "VECTOR"),
               ("F", "FLOAT")]


def hex_core(b, P, s, rotation, seed, warp=None, warp_menu=None):
    """Three candidate hex cells around the 2D point P (z ignored), cell spacing s.
    warp (optional, in cell units): low-frequency noise displacement of the *lattice only* (the texture
    lookups keep P), so the cell borders become irregular curves instead of straight hexagon sides.
    Returns dict with V (3 rotated+offset texture coordinates), A (3 angles), C (3 random colours),
    W (barycentric weights as a vector socket)."""
    inv = b.math("DIVIDE", 1.0, s)
    q = b.vec("MULTIPLY", P, b.comb(inv, inv, 0.0))
    if warp is not None:
        # smooth 2D value noise built from White Noise hashes (already used by the node: no extra
        # shader library, unlike the Noise node which costs ~+0.3 s of EEVEE compile), shifting the
        # lattice along x. Hexagon sides run at 30/90/150 deg: none is parallel to x, so all bend.
        pn = b.vec("SCALE", q, scale=1.3)                     # ~1.3 bumps per cell
        i = b.vec("FLOOR", pn)
        f = b.vec("SUBTRACT", pn, i)
        u = b.vec("MULTIPLY", b.vec("MULTIPLY", f, f), b.vec("MULTIPLY_ADD", f, (-2.0, -2.0, 0.0), (3.0, 3.0, 0.0)))
        ux, uy, _ = b.sep(u)

        def h(off):
            n = b.node("ShaderNodeTexWhiteNoise", noise_dimensions="2D")
            b.set(n.inputs["Vector"], b.vec("ADD", i, off) if off != (0.0, 0.0, 0.0) else i)
            return n.outputs["Value"]

        lo = b.mix(ux, h((0.0, 0.0, 0.0)), h((1.0, 0.0, 0.0)))
        hi = b.mix(ux, h((0.0, 1.0, 0.0)), h((1.0, 1.0, 0.0)))
        d = b.math("MULTIPLY", b.math("SUBTRACT", b.mix(uy, lo, hi), 0.5), warp)
        qw = b.vec("ADD", q, b.comb(d, 0.0, 0.0))
        if warp_menu is None:
            q = qw
        else:   # Off / On resolved when the shader is compiled: Off costs nothing
            ms = b.node("GeometryNodeMenuSwitch", data_type="VECTOR")
            ms.enum_items.clear()
            for nm in ("Off", "On"):
                ms.enum_items.new(nm)
            b.link(warp_menu, ms.inputs["Menu"])
            b.link(q, ms.inputs["Off"])
            b.link(qw, ms.inputs["On"])
            q = ms.outputs["Output"]
    # skewed lattice coordinates: centres at a*(1,0) + b*(1/2, sqrt3/2)
    uv = b.comb(b.vec("DOT_PRODUCT", q, (1.0, -1.0 / SQ3, 0.0)), b.vec("DOT_PRODUCT", q, (0.0, 2.0 / SQ3, 0.0)))
    base = b.vec("FLOOR", uv)
    fu, fv, _ = b.sep(b.vec("SUBTRACT", uv, base))
    up = b.math("GREATER_THAN", b.math("ADD", fu, fv), 1.0)       # upper triangle
    # slot 1 switches between base (lower) and base+(1,1) (upper): its weight is 0 there
    w1 = b.math("ABSOLUTE", b.math("SUBTRACT", b.math("SUBTRACT", 1.0, fu), fv))
    w2 = b.mix(up, fu, b.math("SUBTRACT", 1.0, fv))
    w3 = b.mix(up, fv, b.math("SUBTRACT", 1.0, fu))
    verts = [b.vec("ADD", base, b.comb(up, up, 0.0)),
             b.vec("ADD", base, (1.0, 0.0, 0.0)),
             b.vec("ADD", base, (0.0, 1.0, 0.0))]
    seedv = b.comb(0.0, 0.0, seed)
    rot = b.math("MULTIPLY", rotation, TAU)
    V, A, C = [], [], []
    for L in verts:
        h = b.white(b.vec("ADD", L, seedv))
        ang = b.math("MULTIPLY", h.outputs["Value"], rot)
        centre = b.vec("SCALE", b.comb(b.vec("DOT_PRODUCT", L, (1.0, 0.5, 0.0)),
                                       b.vec("DOT_PRODUCT", L, (0.0, 0.5 * SQ3, 0.0))), scale=s)
        V.append(b.vec("ADD", b.rotz(P, ang, centre), h.outputs["Color"]))
        A.append(ang)
        C.append(h.outputs["Color"])
    return {"V": V, "A": A, "C": C, "W": b.comb(w1, w2, w3)}


def cells_bundle(b, core, T, Bt, N, Ng, F):
    return b.bundle([("V1", core["V"][0]), ("V2", core["V"][1]), ("V3", core["V"][2]),
                     ("W", core["W"]), ("A", b.comb(*core["A"])),
                     ("C1", core["C"][0]), ("C2", core["C"][1]), ("C3", core["C"][2]),
                     ("T", T), ("B", Bt), ("N", N), ("Ng", Ng), ("F", F)])


def build_cells():
    b = G("AT Cells", "Hex anti-tiling, step 1: three candidate cells per point")
    b.inp("Vector", "NodeSocketVector", desc="Texture coordinates (e.g. Mapping output)")
    b.inp("Cell Size", "NodeSocketFloat", 1.0, 0.05, 100.0, "Distance between cell centres, in texture repeats")
    b.inp("Rotation", "NodeSocketFloat", 1.0, 0.0, 1.0, "Random rotation per cell (0 = none, 1 = full turn)")
    b.inp("Seed", "NodeSocketFloat", 0.0)
    for i in (1, 2, 3):
        b.out(f"Height {i}", "NodeSocketVector", "To the Vector of a height-map Image Texture")
    b.out("Cells", "NodeSocketBundle", "To AT Pick")
    gi, go = b.io()
    core = hex_core(b, gi["Vector"], gi["Cell Size"], gi["Rotation"], gi["Seed"])
    for k in range(3):
        b.link(core["V"][k], go[f"Height {k + 1}"])
    z = b.comb(0.0, 0.0, 1.0)
    b.link(cells_bundle(b, core, b.comb(1.0, 0.0, 0.0), b.comb(0.0, 1.0, 0.0), z, z,
                        b.math("ADD", 0.0, 0.0)), go["Cells"])
    return b.g


def build_pick():
    b = G("AT Pick", "Hex anti-tiling, step 2: the height decides where cells meet")
    b.inp("Cells", "NodeSocketBundle", desc="From AT Cells")
    for i in (1, 2, 3):
        b.inp(f"Height {i}", "NodeSocketFloat", 0.5, 0.0, 1.0, f"Height map read at AT Cells 'Height {i}'")
    b.inp("Height Influence", "NodeSocketFloat", 1.5, 0.0, 10.0,
          "How far the higher texture can push into the neighbour cell (0 = plain hexagons)")
    b.inp("Softness", "NodeSocketFloat", 0.03, 0.001, 1.0, "Width of the blended band along the cut")
    b.out("Vector", "NodeSocketVector", "Connect to every Image Texture of the material")
    b.out("Angle", "NodeSocketFloat", "Per-cell rotation, for AT Normal Fix")
    b.out("Cell Color", "NodeSocketColor", "Debug: random colour of the chosen cell (free when unused)")
    b.out("Normal Data", "NodeSocketBundle", "To AT Normal Object (projected coordinates)")
    gi, go = b.io()
    c = b.unbundle(gi["Cells"], BUNDLE)
    k = gi["Height Influence"]
    H = b.comb(gi["Height 1"], gi["Height 2"], gi["Height 3"])
    p = b.vec("MULTIPLY", c["W"], b.vec("MULTIPLY_ADD", H, b.comb(k, k, k), (1.0, 1.0, 1.0)))
    px, py, pz = b.sep(p)
    thr = b.math("SUBTRACT", b.math("MAXIMUM", b.math("MAXIMUM", px, py), pz), gi["Softness"])
    wd = b.vec("MAXIMUM", b.vec("SUBTRACT", p, b.comb(thr, thr, thr)), (0.0, 0.0, 0.0))
    wx, wy, _ = b.sep(wd)
    r = b.math("MULTIPLY", b.sample_random().outputs["Value"], b.vec("DOT_PRODUCT", wd, (1.0, 1.0, 1.0)))
    s1 = b.math("LESS_THAN", r, wx)
    s12 = b.math("LESS_THAN", r, b.math("ADD", wx, wy))
    s2 = b.math("SUBTRACT", s12, s1)
    s3 = b.math("SUBTRACT", 1.0, s12)
    v = b.vec("ADD", b.vec("ADD", b.vec("SCALE", c["V1"], scale=s1), b.vec("SCALE", c["V2"], scale=s2)),
              b.vec("SCALE", c["V3"], scale=s3))
    b.link(v, go["Vector"])
    ang = b.vec("DOT_PRODUCT", c["A"], b.comb(s1, s2, s3))
    b.link(ang, go["Angle"])
    b.link(b.bundle([("Angle", ang), ("T", c["T"]), ("B", c["B"]), ("N", c["N"]), ("Ng", c["Ng"]),
                     ("F", c["F"])]), go["Normal Data"])
    col = b.vec("ADD", b.vec("ADD", b.vec("SCALE", c["C1"], scale=s1), b.vec("SCALE", c["C2"], scale=s2)),
                b.vec("SCALE", c["C3"], scale=s3))
    b.link(col, go["Cell Color"])
    return b.g


def build_all():
    return [build_cells(), build_pick()]
