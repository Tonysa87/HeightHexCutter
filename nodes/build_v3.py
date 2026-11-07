"""Anti-tile v3: one node per mode, the height (and normal) map given once through a closure.

  AT Anti-Tile UV      Sampler + Vector  -> Vector, Height, Normal, Cell Color
  AT Anti-Tile Object  Sampler           -> Vector, Height, Normal, Cell Color   (no UVs, 2 projections)

Sampler = a Closure zone in the material:  Closure Input (Vector) -> Height map [-> Normal map]
-> Closure Output (Height, Normal). The node evaluates it at every candidate cell (3 in UV, 6 in
Object mode) to let the height decide where cells meet, then once more at the chosen cell for the
final Height and Normal. Only the Height output of the candidate evaluations is used, so Blender
compiles the normal map only once. The other maps (colour, roughness, AO...) are plain Image
Textures fed by the node's Vector output: they are read once.

Normal output: world-space normal, connect it to the BSDF Normal (no Normal Map node needed).
If the closure has no Normal item, the surface normal is returned.
"""
import importlib.util
import math
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
SAMPLER_IN = [("VECTOR", "Vector")]
SAMPLER_OUT = [("FLOAT", "Height"), ("RGBA", "Normal")]


def _eval(b, closure, vec):
    ev = b.node("NodeEvaluateClosure")
    for t, n in SAMPLER_IN:
        ev.input_items.new(t, n)
    for t, n in SAMPLER_OUT:
        ev.output_items.new(t, n)
    b.link(closure, ev.inputs["Closure"])
    b.link(vec, ev.inputs["Vector"])
    return ev


def _common_inputs(b):
    b.inp("Sampler", "NodeSocketClosure",
          desc="Closure: Vector -> Height (and optionally Normal). Put your height map inside it")


def _blend_inputs(b):
    b.inp("Cell Size", "NodeSocketFloat", 1.0, 0.05, 100.0, "Distance between cell centres, in texture repeats")
    b.inp("Rotation", "NodeSocketFloat", 1.0, 0.0, 1.0, "Random rotation per cell (0 = none, 1 = full turn)")
    b.inp("Seed", "NodeSocketFloat", 0.0)
    b.inp("Height Influence", "NodeSocketFloat", 1.5, 0.0, 10.0,
          "How far the higher texture pushes into its neighbour (0 = plain hexagons)")
    b.inp("Softness", "NodeSocketFloat", 0.005, 0.0005, 1.0,
          "Width of the blended band along the cut (wider bands smear in EEVEE)")
    b.inp("Normal Strength", "NodeSocketFloat", 1.0, 0.0, 4.0)
    b.inp("Edge Warp", "NodeSocketFloat", 1.0, 0.0, 2.0,
          "Bends the straight cell sides where the height cannot (flat areas). 0 = straight sides (~5% cost either way)")


def _outputs(b):
    b.out("Vector", "NodeSocketVector", "Connect to the Vector of every other Image Texture of the material")
    b.out("Height", "NodeSocketFloat", "Height at the chosen cell (e.g. for Displacement)")
    b.out("Normal", "NodeSocketVector", "Connect to the BSDF Normal")
    b.out("Cell Color", "NodeSocketColor", "Debug: random colour of the chosen cell (free when unused)")
    b.out("Axis Color", "NodeSocketColor", "Debug: projection axis used (red X, green Y, blue Z; UV = blue)")


def _pick(b, prios, rnd, softness):
    """Dithered choice among candidates: keep those within `softness` of the best priority and pick
    one per sample with probability proportional to how close it is. Returns 0/1 selectors."""
    pmax = prios[0]
    for p in prios[1:]:
        pmax = b.math("MAXIMUM", pmax, p)
    thr = b.math("SUBTRACT", pmax, softness)
    d = [b.math("MAXIMUM", b.math("SUBTRACT", p, thr), 0.0) for p in prios]
    tot = d[0]
    for x in d[1:]:
        tot = b.math("ADD", tot, x)
    r = b.math("MULTIPLY", rnd, tot)
    sel, cum, prev = [], None, None
    for i, x in enumerate(d):
        cum = x if cum is None else b.math("ADD", cum, x)
        lt = b.math("LESS_THAN", r, cum) if i < len(d) - 1 else 1.0
        sel.append(lt if prev is None else b.math("SUBTRACT", lt, prev))
        prev = lt
    return sel


def _select_vec(b, socks, sel):
    acc = b.vec("SCALE", socks[0], scale=sel[0])
    for s, k in zip(socks[1:], sel[1:]):
        acc = b.vec("MULTIPLY_ADD", s, b.comb(k, k, k), acc)
    return acc


def _select_float(b, socks, sel):
    acc = b.math("MULTIPLY", socks[0], sel[0])
    for s, k in zip(socks[1:], sel[1:]):
        acc = b.math("MULTIPLY_ADD", s, k, acc)
    return acc


def _has_normal(b, ncol):
    """1 if the closure delivered a normal map colour (a missing item evaluates to black)."""
    return b.math("GREATER_THAN", b.vec("LENGTH", ncol), 0.001)


def _vmix(b, f, a, c):
    n = b.node("ShaderNodeMix", data_type="VECTOR")
    b.set(n.inputs["Factor"], f)
    b.set(n.inputs[4], a)
    b.set(n.inputs[5], c)
    return n.outputs[1]


# ----------------------------------------------------------------------------------------------
def _branch_uv(b, gi, P):
    """UV / 2D branch. Returns dict of the four output sockets."""
    o = {}
    core = v1.hex_core(b, P, gi["Cell Size"], gi["Rotation"], gi["Seed"], gi["Edge Warp"])
    k = gi["Height Influence"]
    W = b.sep(core["W"])
    prios = []
    for v, w in zip(core["V"], W):
        h = _eval(b, gi["Sampler"], v).outputs["Height"]
        prios.append(b.math("MULTIPLY", w, b.math("MULTIPLY_ADD", h, k, 1.0)))
    sel = _pick(b, prios, b.sample_random().outputs["Value"], gi["Softness"])
    vec = _select_vec(b, core["V"], sel)
    o["Vector"] = vec
    o["Cell Color"] = _select_vec(b, core["C"], sel)
    fin = _eval(b, gi["Sampler"], vec)
    o["Height"] = fin.outputs["Height"]
    # normal map: undo the cell rotation, then the usual tangent-space Normal Map node (active UV map)
    ang = _select_float(b, core["A"], sel)
    nt = b.vec("MULTIPLY_ADD", fin.outputs["Normal"], (2.0, 2.0, 2.0), (-1.0, -1.0, -1.0))
    nt = b.vec("MULTIPLY_ADD", b.rotz(nt, ang, invert=True), (0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    nm = b.node("ShaderNodeNormalMap")
    b.link(gi["Normal Strength"], nm.inputs["Strength"])
    b.link(nt, nm.inputs["Color"])
    geo = b.node("ShaderNodeNewGeometry")
    o["Normal"] = _vmix(b, _has_normal(b, fin.outputs["Normal"]), geo.outputs["Normal"], nm.outputs["Normal"])
    o["Axis Color"] = b.comb(0.0, 0.0, 1.0)
    return o


def _branch_object(b, gi):
    """Object/World projection branch (2 dominant axes x 3 cells). Returns dict of output sockets."""
    o = {}
    # space: one Menu Switch -> 0 Object / 1 World
    ms = b.node("GeometryNodeMenuSwitch", data_type="FLOAT")
    ms.enum_items.clear()
    for nm in ("Object", "World"):
        ms.enum_items.new(nm)
    b.link(gi["Space"], ms.inputs["Menu"])
    ms.inputs["Object"].default_value = 0.0
    ms.inputs["World"].default_value = 1.0
    fw = ms.outputs["Output"]
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
    # the second projection fades out before it swaps with the weakest axis: no seam where they swap
    absN = b.vec("ABSOLUTE", N)
    nmin = b.vec("DOT_PRODUCT", absN, Mmin)
    fade = b.node("ShaderNodeClamp")
    b.set(fade.inputs["Value"], b.math("MULTIPLY", b.math("SUBTRACT", b.vec("DOT_PRODUCT", absN, Mmed), nmin), 16.0))
    wb = b.math("MULTIPLY", b.vec("DOT_PRODUCT", aw, Mmed), fade.outputs[0])
    tot = b.math("ADD", wa, wb)
    k = gi["Height Influence"]
    cand = []            # (vector, angle, colour, priority, projection index)
    frames = []
    for pi, (M, w) in enumerate(((Mmax, b.math("DIVIDE", wa, tot)), (Mmed, b.math("DIVIDE", wb, tot)))):
        mx, my, mz = b.sep(M)
        sx, sy, sz = b.sep(S)
        # right-handed frames: X:(T=(0,s,0),B=Z)  Y:(T=(-s,0,0),B=Z)  Z:(T=(s,0,0),B=Y)
        T = b.comb(b.math("SUBTRACT", b.math("MULTIPLY", mz, sz), b.math("MULTIPLY", my, sy)),
                   b.math("MULTIPLY", mx, sx), 0.0)
        Bt = b.comb(0.0, mz, b.math("ADD", mx, my))
        frames.append((T, Bt, b.vec("MULTIPLY", S, M)))
        st = b.comb(b.vec("DOT_PRODUCT", P, T), b.vec("DOT_PRODUCT", P, Bt), 0.0)
        seed = b.math("ADD", gi["Seed"], b.vec("DOT_PRODUCT", M, (0.0, 17.0, 34.0)))
        core = v1.hex_core(b, st, gi["Cell Size"], gi["Rotation"], seed, gi["Edge Warp"])
        for v, a, c, wc in zip(core["V"], core["A"], core["C"], b.sep(core["W"])):
            h = _eval(b, gi["Sampler"], v).outputs["Height"]
            cand.append((v, a, c, b.math("MULTIPLY", b.math("MULTIPLY", wc, w), b.math("MULTIPLY_ADD", h, k, 1.0)), pi))
    sel = _pick(b, [c[3] for c in cand], b.sample_random().outputs["Value"], gi["Softness"])
    vec = _select_vec(b, [c[0] for c in cand], sel)
    o["Vector"] = vec
    o["Cell Color"] = _select_vec(b, [c[2] for c in cand], sel)
    fin = _eval(b, gi["Sampler"], vec)
    o["Height"] = fin.outputs["Height"]
    ang = _select_float(b, [c[1] for c in cand], sel)
    fa = sel[0]
    for s in sel[1:3]:
        fa = b.math("ADD", fa, s)          # 1 if the chosen cell is on the dominant projection
    T, Bt, Nax = (_vmix(b, fa, frames[1][i], frames[0][i]) for i in range(3))
    o["Axis Color"] = b.vec("ABSOLUTE", Nax)
    # normal map: undo the cell rotation, orient on the chosen plane, whiteout with the surface normal
    nt = b.vec("MULTIPLY_ADD", fin.outputs["Normal"], (2.0, 2.0, 2.0), (-1.0, -1.0, -1.0))
    nt = b.rotz(nt, ang, invert=True)
    ks = gi["Normal Strength"]
    tx, ty, tz = b.sep(b.vec("MULTIPLY", nt, b.comb(ks, ks, 1.0)))
    n = b.vec("ADD", b.vec("ADD",
              b.vec("SCALE", T, scale=b.math("ADD", tx, b.vec("DOT_PRODUCT", N, T))),
              b.vec("SCALE", Bt, scale=b.math("ADD", ty, b.vec("DOT_PRODUCT", N, Bt)))),
              b.vec("SCALE", Nax, scale=b.math("MULTIPLY", tz, b.math("ABSOLUTE", b.vec("DOT_PRODUCT", N, Nax)))))
    n = b.vec("NORMALIZE", n)
    vt2 = b.node("ShaderNodeVectorTransform", vector_type="NORMAL", convert_from="OBJECT", convert_to="WORLD")
    b.link(n, vt2.inputs[0])
    nw = b.vec("NORMALIZE", _vmix(b, fw, vt2.outputs[0], n))
    o["Normal"] = _vmix(b, _has_normal(b, fin.outputs["Normal"]), geo.outputs["Normal"], nw)
    return o


def _menu_default(g, name, value):
    for it in g.interface.items_tree:
        if getattr(it, "name", "") == name and it.in_out == "INPUT":
            try:
                it.default_value = value
            except Exception:
                pass


def _link_outputs(b, go, o):
    for k in ("Vector", "Height", "Normal", "Cell Color", "Axis Color"):
        b.link(o[k], go[k])


def build_tile_uv():
    b = G("AT Anti-Tile UV", "Anti-tiling on UV (or any 2D) coordinates; height and normal map in the Sampler")
    _common_inputs(b)
    b.inp("Vector", "NodeSocketVector", desc="Texture coordinates (e.g. UV -> Mapping)")
    _blend_inputs(b)
    _outputs(b)
    gi, go = b.io()
    _link_outputs(b, go, _branch_uv(b, gi, gi["Vector"]))
    ngkit.auto_layout(b.g)
    return b.g


def _object_inputs(b):
    b.inp("Sharpness", "NodeSocketFloat", 4.0, 1.0, 64.0, "Object: how fast the second projection fades out")
    b.inp("Space", "NodeSocketMenu", desc="Object: follows the object. World: continuous across objects")


def build_tile_object():
    b = G("AT Anti-Tile Object", "Anti-tiling on Object/World coordinates, no UVs: hex cells on the two "
                                 "dominant axis planes, the height decides cells and projections")
    _common_inputs(b)
    b.inp("Scale", "NodeSocketFloat", 2.0, 0.001, 1000.0, "Texture repeats per metre")
    _blend_inputs(b)
    _object_inputs(b)
    _outputs(b)
    gi, go = b.io()
    _link_outputs(b, go, _branch_object(b, gi))
    _menu_default(b.g, "Space", "Object")
    ngkit.auto_layout(b.g)
    return b.g


def build_tile():
    """The single node: Projection menu UV / Object. The menu is resolved when the shader is compiled,
    so only the chosen branch costs anything."""
    b = G("AT Anti-Tile", "Anti-tiling for natural PBR textures. Projection UV (uses Vector, or the active "
                          "UV map when nothing is connected) or Object (no UVs needed). Put the height "
                          "(and normal) map in the Sampler closure; connect Vector to the other textures")
    _common_inputs(b)
    b.inp("Projection", "NodeSocketMenu", desc="UV: texture coordinates. Object: projected from the object, no UVs")
    b.inp("Vector", "NodeSocketVector", desc="UV mode only: coordinates (empty = active UV map)")
    b.inp("Scale", "NodeSocketFloat", 1.0, 0.001, 1000.0, "UV: repeats per UV unit. Object: repeats per metre")
    _blend_inputs(b)
    _object_inputs(b)
    _outputs(b)
    gi, go = b.io()
    # UV branch: Vector if connected, else the active UV map; times Scale
    tc = b.node("ShaderNodeTexCoord")
    has_vec = b.math("GREATER_THAN", b.vec("LENGTH", gi["Vector"]), 0.0)
    P = b.vec("SCALE", _vmix(b, has_vec, tc.outputs["UV"], gi["Vector"]), scale=gi["Scale"])
    items = ("Vector", "Height", "Normal", "Cell Color", "Axis Color")
    ou = _branch_uv(b, gi, P)
    oo = _branch_object(b, gi)
    ms = b.node("GeometryNodeMenuSwitch", data_type="BUNDLE")
    ms.enum_items.clear()
    for nm in ("UV", "Object"):
        ms.enum_items.new(nm)
    b.link(gi["Projection"], ms.inputs["Menu"])
    b.link(b.bundle([(k, ou[k]) for k in items]), ms.inputs["UV"])
    b.link(b.bundle([(k, oo[k]) for k in items]), ms.inputs["Object"])
    sel = b.unbundle(ms.outputs["Output"], [("Vector", "VECTOR"), ("Height", "FLOAT"), ("Normal", "VECTOR"),
                                            ("Cell Color", "VECTOR"), ("Axis Color", "VECTOR")])
    _link_outputs(b, go, sel)
    _menu_default(b.g, "Space", "Object")
    _menu_default(b.g, "Projection", "Object")
    ngkit.auto_layout(b.g)
    return b.g


GROUPS = ["AT Anti-Tile UV", "AT Anti-Tile Object", "AT Anti-Tile"]


def build_all():
    return ngkit.safe_rebuild([build_tile_uv, build_tile_object, build_tile], GROUPS)
