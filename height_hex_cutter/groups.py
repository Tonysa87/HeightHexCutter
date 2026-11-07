"""Create or update the HHC Anti-Tile node group in the open file.

The group is stamped with ``hhc_version``. Same version: reused. Older version: rebuilt in place with
the safe rebuild (every material using it keeps its links and values). A group that has the HHC name
but no stamp is not ours: it is left alone and ours is built under a free name. Stamped duplicates
(e.g. ``HHC Anti-Tile.001`` arriving with an appended asset) are remapped to the main group and removed.
"""
import bpy

from .nodes import ngkit, tile

GROUP_NAME = tile.GROUP_NAME
HHC_GROUP_VERSION = 2
last_notice = ""              # set when ensure_group() updated an older group (shown in the report)
STAMP = "hhc_version"


def _stamped(g):
    return g.bl_idname == "ShaderNodeTree" and g.library is None and STAMP in g


def _candidates():
    return [g for g in bpy.data.node_groups
            if _stamped(g) and (g.name == GROUP_NAME or g.name.startswith(GROUP_NAME + "."))]


def _build(name):
    g = tile.build_tile(name)
    g[STAMP] = HHC_GROUP_VERSION
    return g


def ensure_group():
    """Return the current HHC Anti-Tile group, building, updating or de-duplicating as needed."""
    global last_notice
    last_notice = ""
    groups = _candidates()
    if not groups:
        name = GROUP_NAME
        taken = {g.name for g in bpy.data.node_groups if g.library is None}
        if name in taken:                             # foreign group with our name: pick a free one
            i = 1
            while f"{GROUP_NAME}.{i:03d}" in taken:
                i += 1
            name = f"{GROUP_NAME}.{i:03d}"
        return _build(name)
    # main = exact name if stamped, else the first stamped candidate
    main = next((g for g in groups if g.name == GROUP_NAME), groups[0])
    if main[STAMP] < HHC_GROUP_VERSION:
        name, old = main.name, main[STAMP]
        _, lost = ngkit.safe_rebuild([lambda: tile.build_tile(name)], [name])
        main = next(g for g in bpy.data.node_groups if g.name == name and g.library is None)
        main[STAMP] = HHC_GROUP_VERSION
        last_notice = f"{name} updated to version {HHC_GROUP_VERSION} (was {old})"
        if lost:
            last_notice += f"; {len(lost)} link(s) could not be restored: " + \
                ", ".join(f"{t}/{n}.{s}" for t, n, s in lost[:5])
    for g in groups:                                  # duplicates (e.g. from appended assets)
        if g is not main and g[STAMP] <= main[STAMP]:
            g.user_remap(main)
            bpy.data.node_groups.remove(g)
    return main
