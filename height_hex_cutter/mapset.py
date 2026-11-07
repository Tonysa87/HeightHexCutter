"""What the add-on found in a source: which image (or constant) feeds each channel."""
from dataclasses import dataclass, field

from .channels import CHANNELS


@dataclass
class MapRef:
    image: object                      # bpy.types.Image, or None for a constant
    chan: str = None                   # None = whole image, "R"/"G"/"B" = one channel of a packed map
    constant: object = None            # float or (r, g, b) when the map is uniform
    chain: list = field(default_factory=list)   # source nodes between image and Principled (copied)
    target: str = ""                   # Principled input fed by this map
    fallback: bool = False             # True when Height was taken from AO or Base Color


@dataclass
class MapSet:
    maps: dict = field(default_factory=dict)
    normal_dx: bool = False
    normal_strength: float = 1.0
    disp_scale: float = None
    principled: dict = field(default_factory=dict)
    ignored: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    uv_scale: float = 1.0              # Mapping scale of the source (repeats per UV unit)
    node_values: dict = field(default_factory=dict)   # settings of a source HHC/AT node, kept as they are
    source_tree: object = None         # node tree the chains were read from (from_material only)
    source_bsdf: object = None         # its Principled BSDF

    def summary(self):
        parts = []
        for ch in CHANNELS:
            r = self.maps.get(ch)
            if r is None:
                continue
            if r.constant is not None:
                v = r.constant
                txt = f"({', '.join(f'{x:g}' for x in v)})" if isinstance(v, tuple) else f"{v:g}"
                parts.append(f"{ch}={txt} (constant)")
            else:
                parts.append(f"{ch}={r.image.name}" + (f".{r.chan}" if r.chan else ""))
        s = ", ".join(parts)
        if self.ignored:
            s += " | ignored: " + ", ".join(self.ignored)
        if self.notes:
            s += " | " + "; ".join(self.notes)
        return s
