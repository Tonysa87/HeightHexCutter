"""Anti-tile v0: dithered single-fetch cell selection (experiment, names provisional).

Run inside Blender. Builds three shader node groups:
  AT Hex Dither    Vector -> Vector, Angle   (hexagonal cells)
  AT Noise Dither  Vector -> Vector, Angle   (irregular regions from a low-frequency noise)
  AT Normal Fix    normal-map Color + Angle -> Color  (undo the per-cell rotation)

Idea: every cell gets a random offset/rotation of the texture coordinates. Near a cell
border the cell is chosen at random for each render sample (White Noise of the shading
position, which is jittered sub-pixel at every sample), so the renderer's own sample
accumulation blends the cells *after shading*. Every map is read once.
"""
import math

import bpy

SQ3 = math.sqrt(3.0)
TAU = 2.0 * math.pi


class G:
    """Minimal helper to build a node group."""

    def __init__(self, name, desc=""):
        g = bpy.data.node_groups.get(name)
        if g is None:
            g = bpy.data.node_groups.new(name, "ShaderNodeTree")
        else:
            g.nodes.clear()
            g.interface.clear()
        g.description = desc
        self.g = g
        self.k = 0

    def inp(self, name, stype, default=None, mn=None, mx=None, desc=""):
        s = self.g.interface.new_socket(name, in_out="INPUT", socket_type=stype)
        for attr, v in (("default_value", default), ("min_value", mn), ("max_value", mx)):
            if v is not None and hasattr(s, attr):
                setattr(s, attr, v)
        s.description = desc
        return s

    def out(self, name, stype, desc=""):
        s = self.g.interface.new_socket(name, in_out="OUTPUT", socket_type=stype)
        s.description = desc
        return s

    def node(self, t, **props):
        n = self.g.nodes.new(t)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (200 * (self.k // 6), -160 * (self.k % 6))
        self.k += 1
        return n

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.g.links.new(v, sock)
        elif v is not None:
            sock.default_value = v

    def math(self, op, a, b=None, c=None):
        n = self.node("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b, c)):
            self.set(n.inputs[i], v)
        return n.outputs[0]

    def vec(self, op, a, b=None, c=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        if c is not None:
            self.set(n.inputs[2], c)
        if scale is not None:
            self.set(n.inputs["Scale"], scale)
        return n.outputs["Value"] if op in ("DISTANCE", "LENGTH", "DOT_PRODUCT") else n.outputs["Vector"]

    def comb(self, x=0.0, y=0.0, z=0.0):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.set(n.inputs[i], v)
        return n.outputs[0]

    def white(self, v):
        n = self.node("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
        self.set(n.inputs["Vector"], v)
        return n

    def rotz(self, v, angle, center=None, invert=False):
        n = self.node("ShaderNodeVectorRotate", rotation_type="Z_AXIS", invert=invert)
        self.set(n.inputs["Vector"], v)
        self.set(n.inputs["Angle"], angle)
        if center is not None:
            self.set(n.inputs["Center"], center)
        return n.outputs[0]

    def io(self):
        gi = self.g.nodes.new("NodeGroupInput")
        go = self.g.nodes.new("NodeGroupOutput")
        gi.location = (-300, 0)
        go.location = (1600, 0)
        return gi.outputs, go.inputs


def _common_inputs(b, size_desc):
    b.inp("Vector", "NodeSocketVector", desc="Texture coordinates (e.g. Mapping output)")
    b.inp("Cell Size", "NodeSocketFloat", 1.0, 0.05, 100.0, size_desc)
    b.inp("Blend", "NodeSocketFloat", 0.3, 0.0, 1.0, "Width of the dithered transition between cells")
    b.inp("Rotation", "NodeSocketFloat", 1.0, 0.0, 1.0, "Random rotation per cell (0 = none, 1 = full turn)")
    b.inp("Seed", "NodeSocketFloat", 0.0)
    b.out("Vector", "NodeSocketVector", "Connect to every Image Texture of the material")
    b.out("Angle", "NodeSocketFloat", "Per-cell rotation, for AT Normal Fix")


def _finish(b, gi, go, P, cell_id, center):
    """Random offset + rotation from the cell id."""
    seed = b.comb(0.0, 0.0, gi["Seed"])
    h = b.white(b.vec("ADD", cell_id, seed))
    ang = b.math("MULTIPLY", h.outputs["Value"], b.math("MULTIPLY", gi["Rotation"], TAU))
    uv = b.vec("ADD", b.rotz(P, ang, center), h.outputs["Color"])
    b.g.links.new(uv, go["Vector"])
    b.g.links.new(ang, go["Angle"])


def build_hex():
    b = G("AT Hex Dither", "Dithered hexagonal anti-tiling: one texture read per map")
    _common_inputs(b, "Distance between hex cell centres, in texture repeats")
    gi, go = b.io()
    P = gi["Vector"]
    inv = b.math("DIVIDE", 1.0, gi["Cell Size"])
    # per-sample jitter (z stays 0): the cell is picked at a jittered point
    rnd = b.white(b.node("ShaderNodeNewGeometry").outputs["Position"])
    jit = b.vec("MULTIPLY", rnd.outputs["Color"], b.comb(gi["Blend"], gi["Blend"], 0.0))
    x = b.vec("MULTIPLY_ADD", P, b.comb(inv, inv, 0.0), jit)
    # nearest hex centre: two rectangular lattices offset by (0.5, sqrt3/2)
    inc = (1.0, SQ3, 1.0)
    half = (0.5, 0.5 * SQ3, 0.0)
    cA = b.vec("SNAP", b.vec("ADD", x, half), inc)
    cB = b.vec("ADD", b.vec("SNAP", x, inc), half)
    pick_b = b.math("GREATER_THAN", b.vec("DISTANCE", x, cA), b.vec("DISTANCE", x, cB))
    mix = b.node("ShaderNodeMix", data_type="VECTOR")
    b.set(mix.inputs["Factor"], pick_b)
    b.set(mix.inputs[4], cA)
    b.set(mix.inputs[5], cB)
    c = mix.outputs[1]
    _finish(b, gi, go, P, c, b.vec("SCALE", c, scale=gi["Cell Size"]))
    return b.g


def build_noise(levels=12.0, noise_scale=0.25):
    b = G("AT Noise Dither", "Dithered anti-tiling on irregular noise regions: one texture read per map")
    _common_inputs(b, "Size of the regions, in texture repeats")
    gi, go = b.io()
    P = gi["Vector"]
    inv = b.math("DIVIDE", 1.0, gi["Cell Size"])
    q = b.vec("MULTIPLY", P, b.comb(inv, inv, 0.0))
    nz = b.node("ShaderNodeTexNoise", noise_dimensions="2D")
    b.set(nz.inputs["Vector"], q)
    nz.inputs["Scale"].default_value = noise_scale
    nz.inputs["Detail"].default_value = 0.0
    rnd = b.white(b.node("ShaderNodeNewGeometry").outputs["Position"])
    # region index = floor(noise * levels + per-sample jitter * blend)
    i = b.math("FLOOR", b.math("MULTIPLY_ADD", nz.outputs["Fac"], levels,
                               b.math("MULTIPLY", rnd.outputs["Value"], gi["Blend"])))
    _finish(b, gi, go, P, b.comb(i, 0.0, 0.0), None)
    return b.g


def build_normal_fix():
    b = G("AT Normal Fix", "Rotate a tangent-space normal map back by the per-cell angle")
    b.inp("Color", "NodeSocketColor", (0.5, 0.5, 1.0, 1.0), desc="Normal map image colour")
    b.inp("Angle", "NodeSocketFloat", 0.0)
    b.out("Color", "NodeSocketColor", "To the Normal Map node")
    gi, go = b.io()
    n = b.vec("MULTIPLY_ADD", gi["Color"], (2.0, 2.0, 2.0), (-1.0, -1.0, -1.0))
    r = b.rotz(n, gi["Angle"], invert=True)
    b.g.links.new(b.vec("MULTIPLY_ADD", r, (0.5, 0.5, 0.5), (0.5, 0.5, 0.5)), go["Color"])
    return b.g


def build_all():
    return [build_hex(), build_noise(), build_normal_fix()]


if __name__ == "__main__" or "result" in globals():
    gs = build_all()
    result = {g.name: len(g.nodes) - 2 for g in gs}
