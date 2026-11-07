"""Create or update the HHC Anti-Tile node group in the open file.

The group is stamped with ``hhc_version``. Same version: reused. Older version: rebuilt in place with
the safe rebuild (every material using it keeps its links and values). A group that has the HHC name
but no stamp is not ours: it is left alone and ours is built under a free name. Stamped duplicates
(e.g. ``HHC Anti-Tile.001`` arriving with an appended asset) are remapped to the main group and removed.
"""
import bpy

from .nodes import ngkit, tile

GROUP_NAME = tile.GROUP_NAME
HHC_GROUP_VERSION = 1
STAMP = "hhc_version"


def _stamped(g):
    return g.bl_idname == "ShaderNodeTree" and STAMP in g


def _candidates():
    return [g for g in bpy.data.node_groups
            if _stamped(g) and (g.name == GROUP_NAME or g.name.startswith(GROUP_NAME + "."))]


def _build(name):
    g = tile.build_tile(name)
    g[STAMP] = HHC_GROUP_VERSION
    return g


def ensure_group():
    """Return the current HHC Anti-Tile group, building, updating or de-duplicating as needed."""
    groups = _candidates()
    if not groups:
        name = GROUP_NAME
        if name in bpy.data.node_groups:              # foreign group with our name: pick a free one
            i = 1
            while f"{GROUP_NAME}.{i:03d}" in bpy.data.node_groups:
                i += 1
            name = f"{GROUP_NAME}.{i:03d}"
        return _build(name)
    # main = exact name if stamped, else the first stamped candidate
    main = next((g for g in groups if g.name == GROUP_NAME), groups[0])
    for g in groups:
        if g is not main and g[STAMP] == main[STAMP]:
            g.user_remap(main)
            bpy.data.node_groups.remove(g)
    if main[STAMP] < HHC_GROUP_VERSION:
        name = main.name
        _, lost = ngkit.safe_rebuild([lambda: tile.build_tile(name)], [name])
        main = bpy.data.node_groups[name]
        main[STAMP] = HHC_GROUP_VERSION
    return main
