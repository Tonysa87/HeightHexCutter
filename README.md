# Height Hex Cutter (HHC)

**Version 0.5**: working prototype, with known issues to fix before 1.0.

Anti-tiling for **natural PBR textures** (terrain, rock, weathered plaster, raw concrete) in
**Blender 5.2**, built from native shader nodes only: no OSL, runs on the GPU in both **Cycles** and
**EEVEE**. It is not meant for tiles, bricks, parquet or geometric patterns.

One node, `HHC Anti-Tile`, makes the repetition of a texture impossible to spot by eye, and stays
cheap both at render time and at EEVEE shader compilation. The add-on builds the whole material for
you from an asset, a material of the file or a set of image files.

> Full status in [docs/project-status.md](docs/project-status.md); research, cost model and lessons
> learned in [docs/research-and-lessons.md](docs/research-and-lessons.md).

---

## Install

1. `python3 build.py` → `dist/height_hex_cutter-0.5.0.zip` (or download it from the releases).
2. Blender: *Edit → Preferences → Get Extensions → ⌄ → Install from Disk…* and pick the zip.

## Use

Select the object that should receive the material, then use one of:

| Where | Action |
|---|---|
| **Asset Browser** | right-click a material → **HHC: Use This Material** (local or external library) |
| **Shader Editor → N panel → HHC** | **From Material…**: pick a material of the file |
| **Shader Editor → N panel → HHC** | **From Image Files…**: multi-select the maps of a texture set, then type a name |

A **new material `<name>_HHC`** is created; the source material is never modified. It is added to the
active object: in a new slot at the end if the object already has materials (faces are not
reassigned), as the first slot if it has none. The status bar reports which file went to which channel.

### What the add-on recognises
- **Maps:** Base Color, AO, Roughness, Metallic, Normal, Height, and packed **ORM/ARM** maps (one
  texture split by channel). Names are read from the usual suffixes (`_BaseColor`, `_diff`, `_B`,
  `_AO`, `_rough`, `_nor_gl`, `_NormalDX`, `_H`, `_disp`, `_arm`…); from a material, the node
  structure is read first.
- **Uniform maps** (an all-black Metallic, a flat AO…) are not loaded: their value goes straight into
  the Principled BSDF.
- **Adjustment nodes** between a texture and the BSDF in the source (Invert, Color Ramp, Hue/Saturation,
  an AO Mix…) are copied as they are. Normal Map Strength and convention, and the Displacement scale,
  are carried over.
- Other channels (emission, opacity, specular…) are ignored and listed in the report.

### The generated material
```
[Sampler] Closure Input ─┬─> Height ─┐                 [Textures] Base Color ─┐
                         └─> Normal ─┴─> Closure Output          AO ──────── Multiply ─> Principled BSDF ─> Output
                                              │ Sampler          Roughness ────────────────┘   ▲   ▲            ▲
                                       [HHC Anti-Tile] ── Vector ─> all textures            Normal Metallic  Displacement
                                              ├─ Normal ──────────────────────────────────────┘     (value)       │
                                              └─ Height ─────────────────────────────> [Displacement] Bump Only
```
- **Height** decides where cells meet. Without a height map the sampler uses the **AO** map, or else
  the **Base Color through a Color Ramp** (label *Height from Base Color (adjust)*): tune it if light
  does not mean "high" in that texture.
- **Displacement** is created only with a real height map, with the material set to **Bump Only**.
  Without one there is no displacement node; add it by hand if you find a height map later.

## `HHC Anti-Tile` parameters

| Parameter | Meaning | Default |
|---|---|---|
| Projection | **UV** (uses Vector, or the active UV map when nothing is connected) / **Object** (no UVs, projection on the 2 dominant axes). The branch not chosen is not compiled | Object |
| Scale | UV: repeats per UV unit. Object: repeats per metre | 1 |
| Cell Size | distance between cell centres, in texture repeats | 1 |
| Rotation | random rotation per cell (0 = none, 1 = full turn) | 1 |
| Seed | random variant | 0 |
| Height Influence | how far the height can "invade" the neighbouring cell (0 = pure hexagons) | 1.5 |
| Softness | width of the transition band. **Keep it low**: above about 0.01 EEVEE blurs the bands | 0.005 |
| Normal Strength | normal map strength | 1 |
| Normal Map | convention of the normal map in the sampler: OpenGL / DirectX | OpenGL |
| Edge Warp | bends the straight cell sides (0 = straight). Costs about 5% even at 0 | 1 |
| Sharpness | Object only: how fast the second projection fades out | 4 |
| Space | Object only: Object (follows the object) / World (continuous across objects) | Object |

Debug outputs, free when unconnected: **Cell Color** (a random colour per cell) and **Axis Color**
(projection axis used: red X, green Y, blue Z, in object space).

### Usage notes
- **EEVEE:** keep Softness low (about 0.005).
- **Displacement in Bump mode** evaluates the node 3 times and can show streaks along the projection
  axes in Object mode. The normal map already carries the relief; an internal Height Bump is planned.
- **True displacement** (geometry) is not supported yet: random dithering does not average over
  vertices. On flat-shaded meshes it also opens cracks along face edges: use smooth shading.
- **Bake:** dithering converges in a Cycles bake (results/bake_check).

## How it works

1. **Hexagonal cells.** The surface is split into hexagonal cells; each cell offsets and rotates the
   texture at random.
2. **Height decides the boundary.** At every point the 3 neighbouring hexagons are compared (6 in
   Object mode: 3 cells for each of the 2 dominant projections). The priority of each one is
   `cell weight × (1 + Height Influence × height)`, so the "taller" texture wins at the boundary and
   the cut follows the shapes in the texture instead of a straight line.
3. **One read per map (dithering).** Along the cut a thin band remains (Softness) in which one of the
   candidate cells is picked at random for every render sample, and the renderer averages the
   samples. Colour, roughness, normal, AO and metallic are read **only once**, at the chosen cell.
   Only the height is read several times (3 in UV, 6 in Object, plus 1). The idea comes from
   *Stochastic Texture Filtering* (NVIDIA).
4. **Edge Warp** bends the cell grid so hexagon sides don't stay straight where the height is flat.
5. **Normal map** is rotated with its cell and, in Object mode, reoriented for the projection axis.

## Development

```
height_hex_cutter/          the extension: manifest, operators/panel (ui.py), map recognition
                            (channels.py, uniform.py, collect.py), material builder (build.py),
                            node group setup (groups.py) and builders (nodes/)
tests/unit/                 pure-Python tests:      python3 -m unittest discover tests/unit
tests/blender/              tests run inside Blender: tools/hhc_test.sh [pattern]
                            (only in a file named HHC.blend; slow cost check: tools/hhc_test.sh test_cost)
tests/fixtures/make_sets.py tiny generated texture sets used by the tests
bench/                      timing (Cycles ms/sample, EEVEE compile) and image metrics
tools/                      WSL → Blender (Windows) bridge through the Blender MCP add-on (127.0.0.1:9876)
results/                    images and notes of each development step
docs/                       status, research, design and plans
build.py                    builds the extension zip
```

The node group is stamped with a version: when a newer add-on finds an older `HHC Anti-Tile` in a
file, it rebuilds it in place keeping every material that uses it wired.

Requirements for development: Blender 5.2 on Windows with the **Blender Lab MCP** add-on running;
the scripts in `tools/` drive it from WSL.
