"""Tiny helper to build shader node groups from Python."""
import bpy


class G:
    def __init__(self, name, desc=""):
        g = next((x for x in bpy.data.node_groups if x.name == name and x.library is None), None)
        if g is None:
            g = bpy.data.node_groups.new(name, "ShaderNodeTree")
        else:
            g.nodes.clear()
            g.interface.clear()
        g.description = desc
        self.g = g
        self.k = 0

    # interface ----------------------------------------------------------------
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

    def io(self):
        gi = self.g.nodes.new("NodeGroupInput")
        go = self.g.nodes.new("NodeGroupOutput")
        gi.location = (-300, 0)
        go.location = (2400, 0)
        return gi.outputs, go.inputs

    # nodes --------------------------------------------------------------------
    def node(self, t, **props):
        n = self.g.nodes.new(t)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (200 * (self.k // 8), -150 * (self.k % 8))
        self.k += 1
        return n

    def link(self, a, b):
        self.g.links.new(a, b)

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

    def sep(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.set(n.inputs[0], v)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def mix(self, f, a, b):
        """Float lerp a -> b."""
        n = self.node("ShaderNodeMix", data_type="FLOAT")
        self.set(n.inputs["Factor"], f)
        self.set(n.inputs[2], a)
        self.set(n.inputs[3], b)
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

    def sample_random(self):
        """Per-sample random in [0,1): White Noise of the (sub-pixel jittered) shading position."""
        return self.white(self.node("ShaderNodeNewGeometry").outputs["Position"])

    def bundle(self, items):
        """items: list of (name, socket) -> Bundle socket."""
        n = self.node("NodeCombineBundle")
        n.bundle_items.clear()
        for name, sock in items:
            n.bundle_items.new("VECTOR" if sock.type in ("VECTOR", "RGBA") else "FLOAT", name)
        for name, sock in items:
            self.link(sock, n.inputs[name])
        return n.outputs["Bundle"]

    def unbundle(self, bsock, items):
        """items: list of (name, 'VECTOR'|'FLOAT') -> dict name -> socket."""
        n = self.node("NodeSeparateBundle")
        n.bundle_items.clear()
        for name, t in items:
            n.bundle_items.new(t, name)
        self.link(bsock, n.inputs["Bundle"])
        return {name: n.outputs[name] for name, _ in items}


def snapshot_users(group_names):
    """Remember links and input values of every group node (in materials and node groups) that uses
    one of `group_names`, so rebuilding a group (which clears its interface) does not unplug them."""
    trees = [m.node_tree for m in bpy.data.materials if m.node_tree] + list(bpy.data.node_groups)
    snap = []
    for t in trees:
        for n in t.nodes:
            if n.bl_idname == "ShaderNodeGroup" and n.node_tree and n.node_tree.name in group_names:
                vals = {}
                for s in n.inputs:
                    if hasattr(s, "default_value") and not s.is_linked:
                        v = s.default_value
                        # menus are strings (keep them whole), vectors/colours become tuples
                        vals[s.name] = v if isinstance(v, (str, int, float, bool)) else tuple(v)
                ins = [(s.name, l.from_node.name, (l.from_socket.identifier, l.from_socket.name))
                       for s in n.inputs for l in s.links]
                outs = [(s.name, l.to_node.name, (l.to_socket.identifier, l.to_socket.name))
                        for s in n.outputs for l in s.links]
                snap.append((t, n.name, vals, ins, outs))
    return snap


def _set_value(n, k, v):
    try:
        n.inputs[k].default_value = v
        return True
    except Exception:
        return False


def restore_users(snap):
    lost = []
    menus = []
    for t, name, vals, ins, outs in snap:
        n = t.nodes.get(name)
        if n is None:
            continue
        for k, v in vals.items():
            if k in n.inputs and hasattr(n.inputs[k], "default_value"):
                if not _set_value(n, k, v):
                    menus.append((t, name, k, v))   # menu items exist only after the tree update
        def find(socks, key):
            # identifiers of group-node sockets change when a group is rebuilt: fall back to the name
            ident, nm = key
            return next((s for s in socks if s.identifier == ident), None) or \
                next((s for s in socks if s.name == nm), None)

        for sname, fnode, fid in ins:
            src = t.nodes.get(fnode)
            so = find(src.outputs, fid) if src else None
            if so is not None and sname in n.inputs:
                t.links.new(so, n.inputs[sname])
            else:
                lost.append((t.name, name, sname))
        for sname, tnode, tid in outs:
            dst = t.nodes.get(tnode)
            si = find(dst.inputs, tid) if dst else None
            if si is not None and sname in n.outputs:
                t.links.new(n.outputs[sname], si)
            else:
                lost.append((t.name, name, sname))
    if menus:
        # let Blender propagate the new menu items to the group nodes, then set the menus
        for g in {t for t, *_ in menus}:
            g.update_tag()
        for ng in bpy.data.node_groups:
            ng.update_tag()
        bpy.context.view_layer.update()
        for t, name, k, v in menus:
            if not _set_value(t.nodes[name], k, v):
                lost.append((t.name, name, k))
    return lost


def safe_rebuild(builders, names):
    """Run the group builders while keeping every user of those groups wired."""
    snap = snapshot_users(set(names))
    groups = [f() for f in builders]
    return groups, restore_users(snap)


def _est_height(n):
    """Rough drawn height of a node (real dimensions exist only after the editor has drawn it)."""
    rows = sum(1 for s in n.outputs if s.enabled) + sum(1 for s in n.inputs if s.enabled and not s.hide)
    extra = 60 if n.bl_idname in ("ShaderNodeTexImage", "ShaderNodeVectorRotate", "ShaderNodeMix",
                                   "ShaderNodeVectorTransform", "GeometryNodeMenuSwitch") else 20
    return 36 + 22 * rows + extra


def auto_layout(tree, dx=260, gap=30, sweeps=4):
    """Layered left-to-right layout: column = longest path from the inputs, rows ordered by the mean
    row of the linked nodes (fewer crossings). Frames and reroutes are left alone."""
    nodes = [n for n in tree.nodes if n.bl_idname not in ("NodeFrame", "NodeReroute")]
    preds = {n.name: set() for n in nodes}
    succs = {n.name: set() for n in nodes}
    for l in tree.links:
        a, c = l.from_node.name, l.to_node.name
        if a in preds and c in preds and a != c:
            preds[c].add(a)
            succs[a].add(c)
    depth = {}

    def d(name, stack=()):
        if name in depth:
            return depth[name]
        if name in stack:
            return 0
        depth[name] = v = 0 if not preds[name] else 1 + max(d(p, stack + (name,)) for p in preds[name])
        return v

    for n in nodes:
        d(n.name)
    # outputs to the far right, inputs to the far left
    last = max(depth.values()) + 1 if depth else 1
    for n in nodes:
        if n.bl_idname == "NodeGroupOutput":
            depth[n.name] = last
        if n.bl_idname == "NodeGroupInput":
            depth[n.name] = 0
    # pull nodes right, next to their first consumer (shorter links)
    for n in sorted(nodes, key=lambda n: -depth[n.name]):
        if succs[n.name] and n.bl_idname != "NodeGroupInput":
            depth[n.name] = max(depth[n.name], min(depth[s] for s in succs[n.name]) - 1)
    cols = {}
    for n in nodes:
        cols.setdefault(depth[n.name], []).append(n)
    order = {n.name: i for i, n in enumerate(nodes)}
    for _ in range(sweeps):
        for c in sorted(cols):
            for n in cols[c]:
                nb = [order[p] for p in preds[n.name] | succs[n.name] if p in order]
                n["_k"] = sum(nb) / len(nb) if nb else order[n.name]
            cols[c].sort(key=lambda n: n["_k"])
            for i, n in enumerate(cols[c]):
                order[n.name] = i
    by = {n.bl_idname: n for n in nodes}
    for c, ns in cols.items():
        y = 0.0
        hs = [_est_height(n) for n in ns]
        total = sum(hs) + gap * (len(ns) - 1)
        y = total / 2
        for n, h in zip(ns, hs):
            n.location = (c * dx, y)
            y -= h + gap
            if "_k" in n:
                del n["_k"]
