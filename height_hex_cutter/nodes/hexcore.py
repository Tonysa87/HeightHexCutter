"""Hexagonal cell core shared by the HHC node branches.

Every point lies in a triangle of three hex-cell centres (triangular lattice, spacing = Cell Size).
Each candidate cell i has a barycentric weight w_i (1 at its centre, 0 on the far edge; equal weights =
the hex border) and its own random offset + rotation.
"""
import math

SQ3 = math.sqrt(3.0)
TAU = 2.0 * math.pi


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

