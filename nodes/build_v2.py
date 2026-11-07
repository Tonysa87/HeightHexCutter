"""Anti-tile v2 (step 3a): Object/World projection, no UVs needed (names provisional).

  AT Cells Object   (no inputs to connect) -> Height 1/2/3, Cells      -- same outputs as AT Cells
  AT Pick           (from v1, unchanged)   -> Vector, Angle, Normal Data
  AT Normal Object  normal-map Color + Normal Data -> Normal (connect to the BSDF Normal directly)

Projection: one of the three axis planes (X, Y, Z) is used per render sample, picked at random
with probability |n_axis|^Sharpness (so only where the surface is ~45 deg between two axes do
the samples mix projections). On the chosen plane the hex cells of v1 work unchanged. Every map is
still read once; the normal map is re-oriented for the chosen plane (whiteout blend with the
surface normal).

Step 3a = axis chosen by dithering only; step 3b will let the height decide the axis too.
"""
import importlib.util
import os

import bpy

_here = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_here, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ngkit = _load("ngkit")
v1 = _load("build_v1")
G = ngkit.G


def _space_factor(b, gi):
    """One Menu Switch -> 0 (Object) / 1 (World)."""
    ms = b.node("GeometryNodeMenuSwitch", data_type="FLOAT")
    ms.enum_items.clear()
    for nm in ("Object", "World"):
        ms.enum_items.new(nm)
    b.link(gi["Space"], ms.inputs["Menu"])
    ms.inputs["Object"].default_value = 0.0
    ms.inputs["World"].default_value = 1.0
    return ms.outputs["Output"]


def _vmix(b, f, a, c):
    n = b.node("ShaderNodeMix", data_type="VECTOR")
    b.set(n.inputs["Factor"], f)
    b.set(n.inputs[4], a)
    b.set(n.inputs[5], c)
    return n.outputs[1]


def build_cells_object():
    b = G("AT Cells Object", "Hex anti-tiling on Object/World coordinates, axis projection (no UVs)")
    b.inp("Scale", "NodeSocketFloat", 2.0, 0.001, 1000.0, "Texture repeats per metre")
    b.inp("Cell Size", "NodeSocketFloat", 1.0, 0.05, 100.0, "Distance between cell centres, in texture repeats")
    b.inp("Rotation", "NodeSocketFloat", 1.0, 0.0, 1.0, "Random rotation per cell (0 = none, 1 = full turn)")
    b.inp("Seed", "NodeSocketFloat", 0.0)
    b.inp("Sharpness", "NodeSocketFloat", 8.0, 1.0, 64.0, "Narrower transition between projection axes")
    sp = b.inp("Space", "NodeSocketMenu", desc="Object: follows the object. World: continuous across objects")
    for i in (1, 2, 3):
        b.out(f"Height {i}", "NodeSocketVector", "To the Vector of a height-map Image Texture")
    b.out("Cells", "NodeSocketBundle", "To AT Pick")
    gi, go = b.io()
    fw = _space_factor(b, gi)
    tc = b.node("ShaderNodeTexCoord")
    geo = b.node("ShaderNodeNewGeometry")
    vt = b.node("ShaderNodeVectorTransform", vector_type="NORMAL", convert_from="WORLD", convert_to="OBJECT")
    b.link(geo.outputs["Normal"], vt.inputs[0])
    P = b.vec("SCALE", _vmix(b, fw, tc.outputs["Object"], geo.outputs["Position"]), scale=gi["Scale"])
    N = b.vec("NORMALIZE", _vmix(b, fw, vt.outputs[0], geo.outputs["Normal"]))
    # axis chosen per sample, probability ~ |n|^sharpness
    sh = gi["Sharpness"]
    aw = b.vec("POWER", b.vec("ABSOLUTE", N), b.comb(sh, sh, sh))
    ax, ay, _ = b.sep(aw)
    r = b.math("MULTIPLY", b.sep(b.sample_random().outputs["Color"])[0], b.vec("DOT_PRODUCT", aw, (1.0, 1.0, 1.0)))
    sX = b.math("LESS_THAN", r, ax)
    sXY = b.math("LESS_THAN", r, b.math("ADD", ax, ay))
    sY = b.math("SUBTRACT", sXY, sX)
    sZ = b.math("SUBTRACT", 1.0, sXY)
    sx, sy, sz = b.sep(b.vec("SIGN", N))
    # right-handed frames: X:(T=(0,s,0),B=Z)  Y:(T=(-s,0,0),B=Z)  Z:(T=(s,0,0),B=Y)
    T = b.comb(b.math("SUBTRACT", b.math("MULTIPLY", sZ, sz), b.math("MULTIPLY", sY, sy)),
               b.math("MULTIPLY", sX, sx), 0.0)
    Bt = b.comb(0.0, sZ, b.math("ADD", sX, sY))
    Nax = b.vec("MULTIPLY", b.comb(sx, sy, sz), b.comb(sX, sY, sZ))
    st = b.comb(b.vec("DOT_PRODUCT", P, T), b.vec("DOT_PRODUCT", P, Bt), 0.0)
    seed = b.math("ADD", gi["Seed"], b.vec("DOT_PRODUCT", b.comb(sX, sY, sZ), (0.0, 17.0, 34.0)))
    core = v1.hex_core(b, st, gi["Cell Size"], gi["Rotation"], seed)
    for k in range(3):
        b.link(core["V"][k], go[f"Height {k + 1}"])
    b.link(v1.cells_bundle(b, core, T, Bt, Nax, N, fw), go["Cells"])
    for it in b.g.interface.items_tree:
        if getattr(it, "name", "") == "Space" and it.in_out == "INPUT":
            try:
                it.default_value = "Object"
            except Exception:
                pass
    return b.g


def build_normal_object():
    b = G("AT Normal Object", "Normal map for projected coordinates: undo the cell rotation, "
                              "orient it on the chosen axis, blend with the surface (whiteout)")
    b.inp("Color", "NodeSocketColor", (0.5, 0.5, 1.0, 1.0), desc="Normal map image colour (OpenGL)")
    b.inp("Normal Data", "NodeSocketBundle", desc="From AT Pick")
    b.inp("Strength", "NodeSocketFloat", 1.0, 0.0, 4.0)
    b.out("Normal", "NodeSocketVector", "World-space normal: connect to the BSDF Normal")
    gi, go = b.io()
    d = b.unbundle(gi["Normal Data"], v1.NORMAL_DATA)
    nt = b.vec("MULTIPLY_ADD", gi["Color"], (2.0, 2.0, 2.0), (-1.0, -1.0, -1.0))
    nt = b.rotz(nt, d["Angle"], invert=True)
    k = gi["Strength"]
    tx, ty, tz = b.sep(b.vec("MULTIPLY", nt, b.comb(k, k, 1.0)))
    Ng = d["Ng"]
    n = b.vec("ADD", b.vec("ADD",
              b.vec("SCALE", d["T"], scale=b.math("ADD", tx, b.vec("DOT_PRODUCT", Ng, d["T"]))),
              b.vec("SCALE", d["B"], scale=b.math("ADD", ty, b.vec("DOT_PRODUCT", Ng, d["B"])))),
              b.vec("SCALE", d["N"], scale=b.math("MULTIPLY", tz, b.math("ABSOLUTE", b.vec("DOT_PRODUCT", Ng, d["N"])))))
    n = b.vec("NORMALIZE", n)
    vt = b.node("ShaderNodeVectorTransform", vector_type="NORMAL", convert_from="OBJECT", convert_to="WORLD")
    b.link(n, vt.inputs[0])
    b.link(b.vec("NORMALIZE", _vmix(b, d["F"], vt.outputs[0], n)), go["Normal"])
    return b.g


BUNDLE6 = ([(f"V{i}", "VECTOR") for i in range(1, 7)] + [(f"C{i}", "VECTOR") for i in range(1, 7)] +
           [("Wa", "VECTOR"), ("Wb", "VECTOR"), ("Aa", "VECTOR"), ("Ab", "VECTOR"),
            ("Ta", "VECTOR"), ("Ba", "VECTOR"), ("Na", "VECTOR"), ("Tb", "VECTOR"), ("Bb", "VECTOR"), ("Nb", "VECTOR"),
            ("Ng", "VECTOR"), ("F", "FLOAT")])


def _frame(b, M, S):
    """Projection frame for the axis selected by the 0/1 mask vector M (S = sign of the normal)."""
    mx, my, mz = b.sep(M)
    sx, sy, sz = b.sep(S)
    T = b.comb(b.math("SUBTRACT", b.math("MULTIPLY", mz, sz), b.math("MULTIPLY", my, sy)),
               b.math("MULTIPLY", mx, sx), 0.0)
    Bt = b.comb(0.0, mz, b.math("ADD", mx, my))
    return T, Bt, b.vec("MULTIPLY", S, M)


def build_cells_biplanar():
    b = G("AT Cells Biplanar", "Hex anti-tiling on Object/World coordinates: 3 cells on each of the two "
                               "dominant axis planes (6 candidates); AT Pick 6 lets the height decide")
    b.inp("Scale", "NodeSocketFloat", 2.0, 0.001, 1000.0, "Texture repeats per metre")
    b.inp("Cell Size", "NodeSocketFloat", 1.0, 0.05, 100.0, "Distance between cell centres, in texture repeats")
    b.inp("Rotation", "NodeSocketFloat", 1.0, 0.0, 1.0, "Random rotation per cell (0 = none, 1 = full turn)")
    b.inp("Seed", "NodeSocketFloat", 0.0)
    b.inp("Sharpness", "NodeSocketFloat", 4.0, 1.0, 64.0, "How fast the second projection fades out")
    b.inp("Space", "NodeSocketMenu", desc="Object: follows the object. World: continuous across objects")
    for i in range(1, 7):
        b.out(f"Height {i}", "NodeSocketVector", "To the Vector of a height-map Image Texture")
    b.out("Cells", "NodeSocketBundle", "To AT Pick 6")
    gi, go = b.io()
    fw = _space_factor(b, gi)
    tc = b.node("ShaderNodeTexCoord")
    geo = b.node("ShaderNodeNewGeometry")
    vt = b.node("ShaderNodeVectorTransform", vector_type="NORMAL", convert_from="WORLD", convert_to="OBJECT")
    b.link(geo.outputs["Normal"], vt.inputs[0])
    P = b.vec("SCALE", _vmix(b, fw, tc.outputs["Object"], geo.outputs["Position"]), scale=gi["Scale"])
    N = b.vec("NORMALIZE", _vmix(b, fw, vt.outputs[0], geo.outputs["Normal"]))
    S = b.vec("SIGN", b.vec("ADD", N, (1e-7, 1e-7, 1e-7)))
    sh = gi["Sharpness"]
    aw = b.vec("ADD", b.vec("POWER", b.vec("ABSOLUTE", N), b.comb(sh, sh, sh)), (0.0, 1e-6, 2e-6))  # tie-break
    ax, ay, az = b.sep(aw)
    amax = b.math("MAXIMUM", b.math("MAXIMUM", ax, ay), az)
    amin = b.math("MINIMUM", b.math("MINIMUM", ax, ay), az)
    one = (1.0, 1.0, 1.0)
    Mmax = b.vec("SUBTRACT", one, b.vec("SIGN", b.vec("SUBTRACT", b.comb(amax, amax, amax), aw)))
    Mmin = b.vec("SUBTRACT", one, b.vec("SIGN", b.vec("SUBTRACT", aw, b.comb(amin, amin, amin))))
    Mmed = b.vec("SUBTRACT", b.vec("SUBTRACT", one, Mmax), Mmin)
    wa = amax
    wb = b.vec("DOT_PRODUCT", aw, Mmed)
    tot = b.math("ADD", wa, wb)
    wa = b.math("DIVIDE", wa, tot)
    wb = b.math("DIVIDE", wb, tot)
    items, heights = [], []
    out = {}
    for tagname, M, w in (("a", Mmax, wa), ("b", Mmed, wb)):
        T, Bt, Nax = _frame(b, M, S)
        st = b.comb(b.vec("DOT_PRODUCT", P, T), b.vec("DOT_PRODUCT", P, Bt), 0.0)
        seed = b.math("ADD", gi["Seed"], b.vec("DOT_PRODUCT", M, (0.0, 17.0, 34.0)))
        core = v1.hex_core(b, st, gi["Cell Size"], gi["Rotation"], seed)
        out[tagname] = (core, T, Bt, Nax, b.vec("SCALE", core["W"], scale=w))
        heights += core["V"]
    for i, v in enumerate(heights):
        b.link(v, go[f"Height {i + 1}"])
    ca, cb = out["a"][0], out["b"][0]
    items = ([(f"V{i + 1}", v) for i, v in enumerate(ca["V"] + cb["V"])] +
             [(f"C{i + 1}", c) for i, c in enumerate(ca["C"] + cb["C"])] +
             [("Wa", out["a"][4]), ("Wb", out["b"][4]), ("Aa", b.comb(*ca["A"])), ("Ab", b.comb(*cb["A"])),
              ("Ta", out["a"][1]), ("Ba", out["a"][2]), ("Na", out["a"][3]),
              ("Tb", out["b"][1]), ("Bb", out["b"][2]), ("Nb", out["b"][3]), ("Ng", N), ("F", fw)])
    b.link(b.bundle(items), go["Cells"])
    for it in b.g.interface.items_tree:
        if getattr(it, "name", "") == "Space" and it.in_out == "INPUT":
            try:
                it.default_value = "Object"
            except Exception:
                pass
    return b.g


def build_pick6():
    b = G("AT Pick 6", "Height decides among 6 candidates (3 cells x 2 projections)")
    b.inp("Cells", "NodeSocketBundle", desc="From AT Cells Biplanar")
    for i in range(1, 7):
        b.inp(f"Height {i}", "NodeSocketFloat", 0.5, 0.0, 1.0, f"Height map read at 'Height {i}'")
    b.inp("Height Influence", "NodeSocketFloat", 1.5, 0.0, 10.0,
          "How far the higher texture can push into the neighbour (0 = plain cells / projections)")
    b.inp("Softness", "NodeSocketFloat", 0.03, 0.001, 1.0, "Width of the blended band along the cut")
    b.out("Vector", "NodeSocketVector", "Connect to every Image Texture of the material")
    b.out("Cell Color", "NodeSocketColor", "Debug: random colour of the chosen cell (free when unused)")
    b.out("Normal Data", "NodeSocketBundle", "To AT Normal Object")
    gi, go = b.io()
    c = b.unbundle(gi["Cells"], BUNDLE6)
    k = gi["Height Influence"]
    kk = b.comb(k, k, k)
    Ha = b.comb(gi["Height 1"], gi["Height 2"], gi["Height 3"])
    Hb = b.comb(gi["Height 4"], gi["Height 5"], gi["Height 6"])
    pa = b.vec("MULTIPLY", c["Wa"], b.vec("MULTIPLY_ADD", Ha, kk, (1.0, 1.0, 1.0)))
    pb = b.vec("MULTIPLY", c["Wb"], b.vec("MULTIPLY_ADD", Hb, kk, (1.0, 1.0, 1.0)))
    m6 = b.vec("MAXIMUM", pa, pb)
    mx, my, mz = b.sep(m6)
    thr = b.math("SUBTRACT", b.math("MAXIMUM", b.math("MAXIMUM", mx, my), mz), gi["Softness"])
    T3 = b.comb(thr, thr, thr)
    da = b.vec("MAXIMUM", b.vec("SUBTRACT", pa, T3), (0.0, 0.0, 0.0))
    db = b.vec("MAXIMUM", b.vec("SUBTRACT", pb, T3), (0.0, 0.0, 0.0))
    ones = (1.0, 1.0, 1.0)
    ta = b.vec("DOT_PRODUCT", da, ones)
    r = b.math("MULTIPLY", b.sample_random().outputs["Value"], b.math("ADD", ta, b.vec("DOT_PRODUCT", db, ones)))
    # cumulative selection over the 6 weights: s_i = [r < cum_i] - [r < cum_{i-1}]
    d = list(b.sep(da)) + list(b.sep(db))
    cum, prev, sel = None, 0.0, []
    for i, w in enumerate(d):
        cum = w if cum is None else b.math("ADD", cum, w)
        lt = b.math("LESS_THAN", r, cum) if i < 5 else 1.0
        sel.append(b.math("SUBTRACT", lt, prev) if i > 0 else lt)
        prev = lt
    acc = b.vec("SCALE", c["V1"], scale=sel[0])
    col = b.vec("SCALE", c["C1"], scale=sel[0])
    for i in range(1, 6):
        acc = b.vec("MULTIPLY_ADD", c[f"V{i + 1}"], b.comb(sel[i], sel[i], sel[i]), acc)
        col = b.vec("MULTIPLY_ADD", c[f"C{i + 1}"], b.comb(sel[i], sel[i], sel[i]), col)
    b.link(acc, go["Vector"])
    b.link(col, go["Cell Color"])
    sa = b.comb(sel[0], sel[1], sel[2])
    sb = b.comb(sel[3], sel[4], sel[5])
    ang = b.math("ADD", b.vec("DOT_PRODUCT", c["Aa"], sa), b.vec("DOT_PRODUCT", c["Ab"], sb))
    fa = b.vec("DOT_PRODUCT", sa, ones)          # 1 if the chosen cell is on projection a
    fb = b.math("SUBTRACT", 1.0, fa)

    def pick_frame(x, y):
        return b.vec("MULTIPLY_ADD", c[x], b.comb(fa, fa, fa), b.vec("SCALE", c[y], scale=fb))

    b.link(b.bundle([("Angle", ang), ("T", pick_frame("Ta", "Tb")), ("B", pick_frame("Ba", "Bb")),
                     ("N", pick_frame("Na", "Nb")), ("Ng", c["Ng"]), ("F", c["F"])]), go["Normal Data"])
    return b.g


GROUPS = ["AT Cells", "AT Pick", "AT Cells Object", "AT Normal Object", "AT Cells Biplanar", "AT Pick 6"]


def build_all():
    """Rebuild every group; existing materials keep their links and values (lost ones are returned)."""
    groups, lost = ngkit.safe_rebuild([v1.build_cells, v1.build_pick, build_cells_object, build_normal_object,
                                       build_cells_biplanar, build_pick6], GROUPS)
    return groups, lost
