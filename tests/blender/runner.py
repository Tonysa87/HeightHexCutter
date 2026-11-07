"""Blender-side test runner for the HHC add-on (run through tools/hhc_test.sh).

Safety rules:
- runs only when the open file is HHC.blend (the user's dedicated test file);
- every datablock a test creates is named with the prefix ``hhc_t_`` or loaded from tests/fixtures,
  and is removed after the test;
- materials and node groups that do not belong to the tests are fingerprinted before and after the run;
  any difference is reported as the failure ``fingerprint``.
"""
import importlib
import os
import traceback
import types

import bpy

PREFIX = "hhc_t_"
TEST_FILE = "HHC.blend"
HHC_GROUP_PREFIXES = ("HHC Anti-Tile", "_test_", "_v05_")


def _is_test_name(name):
    return name.startswith(PREFIX)


def _is_hhc_group(name):
    return name.startswith(HHC_GROUP_PREFIXES) or _is_test_name(name)


def _value(s):
    if not hasattr(s, "default_value"):
        return None
    v = s.default_value
    if isinstance(v, (str, int, float, bool)):
        return round(v, 6) if isinstance(v, float) else v
    try:
        return tuple(round(x, 6) for x in v)
    except TypeError:
        return repr(v)


def _tree_fingerprint(nt):
    nodes = []
    for n in sorted(nt.nodes, key=lambda n: n.name):
        vals = tuple((s.identifier, _value(s)) for s in n.inputs if not s.is_linked)
        extra = ()
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            extra = (n.image.name, n.image.colorspace_settings.name)
        nodes.append((n.name, n.bl_idname, n.label, n.parent.name if n.parent else "",
                      n.node_tree.name if getattr(n, "node_tree", None) else "", vals, extra))
    links = sorted((l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier)
                   for l in nt.links)
    return (tuple(nodes), tuple(links))


def fingerprint():
    """Fingerprint of everything the tests must not touch."""
    fp = {}
    for m in bpy.data.materials:
        if _is_test_name(m.name):
            continue
        fp["M:" + m.name] = (m.displacement_method, m.use_fake_user,
                             _tree_fingerprint(m.node_tree) if m.node_tree else None)
    for g in bpy.data.node_groups:
        if not _is_hhc_group(g.name):
            fp["G:" + g.name] = _tree_fingerprint(g)
    for o in bpy.data.objects:
        if not _is_test_name(o.name):
            fp["O:" + o.name] = tuple(s.material.name if s.material else None for s in o.material_slots)
    for im in bpy.data.images:
        if not _is_fixture_image(im):
            fp["I:" + im.name] = (im.filepath, im.colorspace_settings.name)
    return fp


def _norm(p):
    return p.replace("\\", "/").lower()


def _is_fixture_image(im):
    return "tests/fixtures/" in _norm(im.filepath) or _is_test_name(im.name)


def _remove(idb):
    try:
        coll = {
            bpy.types.Material: bpy.data.materials, bpy.types.Object: bpy.data.objects,
            bpy.types.Mesh: bpy.data.meshes, bpy.types.Image: bpy.data.images,
            bpy.types.ShaderNodeTree: bpy.data.node_groups, bpy.types.Collection: bpy.data.collections,
        }
        for t, c in coll.items():
            if isinstance(idb, t):
                c.remove(idb)
                return
    except ReferenceError:
        pass


def cleanup():
    """Remove every test datablock (objects first, then their data, then materials, images, groups)."""
    for o in [o for o in bpy.data.objects if _is_test_name(o.name)]:
        bpy.data.objects.remove(o)
    for c in [c for c in bpy.data.collections if _is_test_name(c.name)]:
        bpy.data.collections.remove(c)
    for me in [m for m in bpy.data.meshes if _is_test_name(m.name) and m.users == 0]:
        bpy.data.meshes.remove(me)
    for m in [m for m in bpy.data.materials if _is_test_name(m.name)]:
        bpy.data.materials.remove(m)
    for im in [im for im in bpy.data.images if _is_fixture_image(im)]:
        bpy.data.images.remove(im)
    # HHC groups left without users (the user's own file never had any)
    for _ in range(3):
        for g in [g for g in bpy.data.node_groups if _is_hhc_group(g.name) and g.users == 0]:
            bpy.data.node_groups.remove(g)


def _ctx(root):
    sets = root.rstrip("/") + "/tests/fixtures/sets"
    tmp = bpy.app.tempdir or os.environ.get("TEMP", ".")
    return types.SimpleNamespace(root=root, sets=sets, tmp=tmp, cleanup=[])


def _test_modules(root):
    here = os.path.join(root, "tests", "blender")
    names = sorted(f[:-3] for f in os.listdir(here) if f.startswith("test_") and f.endswith(".py"))
    mods, errors = [], []
    for n in names:
        try:
            mods.append(importlib.import_module("tests.blender." + n))
        except Exception:
            errors.append([n + " (import)", traceback.format_exc(limit=4)])
    return mods, errors


def run(root, pattern=""):
    if bpy.path.basename(bpy.data.filepath) != TEST_FILE:
        return {"error": f"refusing to run: open file is {bpy.data.filepath!r}, not {TEST_FILE}"}
    res = {"file": bpy.data.filepath, "passed": [], "failed": []}
    before = fingerprint()
    try:
        mods, errors = _test_modules(root)
        res["failed"] += [e for e in errors if not pattern or pattern in e[0]]
        for mod in mods:
            mname = mod.__name__.rsplit(".", 1)[1]
            for fname in sorted(n for n in dir(mod) if n.startswith("test_")):
                fn = getattr(mod, fname)
                if not callable(fn) or (pattern and pattern not in mname and pattern not in fname):
                    continue
                ctx = _ctx(root)
                try:
                    fn(ctx)
                    res["passed"].append(f"{mname}.{fname}")
                except Exception:
                    res["failed"].append([f"{mname}.{fname}", traceback.format_exc(limit=6)])
                finally:
                    for idb in reversed(ctx.cleanup):
                        _remove(idb)
                    cleanup()
    finally:
        cleanup()
    after = fingerprint()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    if changed:
        res["failed"].append(["fingerprint", "changed outside the tests: " + ", ".join(changed)])
    res["summary"] = f"{len(res['passed'])} passed, {len(res['failed'])} failed"
    return res
