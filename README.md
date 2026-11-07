# Height Hex Cutter (HHC)

**Version 0.5**: working prototype, with known issues to fix before 1.0.

> The node groups in the code and in the test `.blend` are still named `AT …` (provisional prefix);
> renaming them to `HHC …` is a separate step.

Anti-tiling for **natural PBR textures** (terrain, rock, weathered plaster, raw concrete) in
**Blender 5.2**, built from native shader nodes only: no OSL, runs on the GPU in both **Cycles** and
**EEVEE**. It is not meant for tiles, bricks, parquet or geometric patterns.

Goal: a single node you add to a material and connect to its textures, making the repetition
impossible to spot by eye. It must stay cheap both at render time and at EEVEE shader compilation.
The final result is meant to be baked to UV textures.

> **Status (2026-11-07):** working prototype, single node `AT Anti-Tile`.
> Full summary in [docs/project-status.md](docs/project-status.md); research, cost model and
> lessons learned in [docs/research-and-lessons.md](docs/research-and-lessons.md).

---

## How it works

1. **Hexagonal cells.** The surface is split into hexagonal cells; each cell offsets and rotates the
   texture at random.
2. **Height decides the boundary.** At every point the 3 neighbouring hexagons are compared (6 in
   Object mode: 3 cells for each of the 2 dominant projections). The priority of each one is
   `cell weight × (1 + Height Influence × height)`, so the "taller" texture wins at the boundary and
   the cut follows the shapes in the texture instead of a straight line.
3. **One read per map (dithering).** Along the cut a thin band remains (Softness) in which one of the
   candidate cells is picked at random for every render sample, and the renderer itself averages
   the samples. Colour, roughness, normal, AO and metallic are read **only once**, at the chosen
   cell, so normal and roughness stay consistent without being blended.
   - **Only the height** is read several times: 3 in UV mode and 6 in Object mode, plus 1 at the
     chosen cell.
   - The idea comes from *Stochastic Texture Filtering* (NVIDIA).
4. **Edge Warp.** A light noise warps the cell grid, so the hexagon sides don't stay straight where
   the height is flat.
5. **Normal map.** The normal map is rotated together with its cell and, in Object mode, reoriented
   for the projection axis. The output is a normal ready for the BSDF.

## Usage (manual, for now)

```
 Closure Input (Vector) ─┬─> Image Texture HEIGHT ──> Closure Output (Height)
                         └─> Image Texture NORMAL ──> Closure Output (Normal)
                                                           │ Closure
                                                           v
                                                   [AT Anti-Tile]  Sampler
                                     Vector ──> colour, AO, roughness, metallic Image Textures
                                     Normal ──> Principled BSDF Normal  (no Normal Map node)
                                     Height ──> (Displacement, see notes)
```

1. Add a **Closure** zone (Add → Utilities → Closure).
   - In the *Closure Input* create a **Vector** input.
   - In the *Closure Output* create the outputs **Height** (Float) and **Normal** (Color).
2. Put the height and normal Image Textures (Non-Color) inside the zone, wired as shown above.
3. Connect the *Closure Output* to the **Sampler** input of the `AT Anti-Tile` node.
4. Connect the node's **Vector** output to the other Image Textures and **Normal** to the BSDF Normal.

The node groups can be regenerated from code (see below). The manual setup is meant to be replaced
by an operator that creates the zone automatically: it is one of the next steps.

### `AT Anti-Tile` parameters

| Parameter | Meaning | Current value |
|---|---|---|
| Projection | **UV** (uses Vector, or the active UV map if unconnected) / **Object** (no UVs, projection on the 2 dominant axes). The branch not chosen is not compiled | Object |
| Scale | UV: repeats per UV unit. Object: repeats per metre | 2 |
| Cell Size | distance between cell centres, in texture repeats | 1 |
| Rotation | random rotation per cell (0 = none, 1 = full turn) | 1 |
| Seed | random variant | 0 |
| Height Influence | how far the height can "invade" the neighbouring cell (0 = pure hexagons) | 1.5 |
| Softness | width of the transition band. **Keep it low**: above about 0.01 EEVEE blurs the bands | 0.005 |
| Normal Strength | normal map strength | 1 |
| Edge Warp | bends the straight cell sides (0 = straight). Costs about 5% even at 0 | 1 |
| Sharpness | Object only: how fast the second projection fades out | 4 |
| Space | Object only: Object (follows the object) / World (continuous across objects) | Object |

Debug outputs, free when unconnected:
- **Cell Color**: a random colour per cell;
- **Axis Color**: the projection axis used (red X, green Y, blue Z, in object space).

### Important usage notes
- **EEVEE:** keep Softness low (about 0.005). Closest interpolation also fixes the blurred bands, but
  slows EEVEE down by about 40%.
- **Displacement in Bump mode: don't use it.** It creates streaks along the axes, because it tilts
  the normal the node uses to choose the projection, and it adds noise in the bands. The normal map
  already carries the relief. An internal "Height Bump" without these problems is one of the next
  steps.
- **True displacement** (geometry): not supported yet. Random dithering does not average over
  vertices, so a deterministic mode will be needed.
- **Bake:** verified that dithering converges in a Cycles bake too (results/bake_check).

## Project layout

```
nodes/                      node group builders (Python, run inside Blender)
  ngkit.py                  helpers: node creation, bundles, auto-layout, safe rebuild
  build_v3.py               CURRENT: AT Anti-Tile (+ single-mode AT Anti-Tile UV / Object)
  build_v1.py               hex_core (grid, cells, Edge Warp), used by v3; historical v1 groups
  build_v0.py, build_v2.py  historical (pure dither; multi-node Object) — only used by old tests
bench/                      test bench and measurements
  bench.py                  AT_Bench scene, test materials, timings (Cycles ms/sample,
                            EEVEE compilation), make_v3_material(), run(), run_objects()
  eevee_band_test.py, band_metrics.py      EEVEE blurred-band tests
  normal_check.py, normal_metrics.py       normal check against a reference bump
  projection_test.py        renamed test group (_test_*) to try changes without touching the real ones
tools/                      WSL → Blender (Windows) bridge
  bmcp.sh / bmcp.ps1        send Python code to the Blender MCP add-on (127.0.0.1:9876)
  blrun.sh                  same, with the project modules preloaded
results/                    images and notes for each step (step1, step2, step3a, step3b, eevee_band,
                            statue_lines, bake_check)
docs/                       summaries
```

### Regenerating the groups in the open file
```bash
tools/blrun.sh 'gs, lost = V3.build_all(); result = {"lost": lost}'
```
`build_all()` uses the **safe rebuild**: it saves and restores the links and values of every material
using the groups. **Never call `build_tile()` or the other builders directly** on the real groups:
it would disconnect every material. For experiments use `PT.build_test_group(V3)` (`_test_*`
groups).

### Requirements
- Blender 5.2 on Windows, with the **Blender Lab MCP** add-on running.
- The scripts in `tools/` drive Blender from WSL. The MCP server runs in a Windows Python venv
  (`%USERPROFILE%\.blender-mcp\venv`); the `tools/` scripts also work without it.
