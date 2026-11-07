"""Height Hex Cutter (HHC): one-click anti-tiled materials for natural PBR textures."""


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()
