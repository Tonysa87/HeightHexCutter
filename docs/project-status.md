# Project status — 2026-11-07 (v0.5, add-on)

## Where we are
- **Add-on `height_hex_cutter`** (Blender extension, version 0.5.0): builds a new `<name>_HHC`
  material from a material asset (Asset Browser right-click), a material of the file or a set of image
  files (Shader Editor N panel, tab HHC). Design: `docs/superpowers/specs/2026-11-07-hhc-addon-design.md`.
- **Single node `HHC Anti-Tile`** (`height_hex_cutter/nodes/tile.py`), with a Projection menu UV / Object
  and a Normal Map menu OpenGL / DirectX; the group is version-stamped and updated safely.
  - Height and normal map reach it through a closure (the add-on builds it).
  - All other maps are read only once.
- **Tests:** 31 Blender tests (`tools/hhc_test.sh`, only in a file named `HHC.blend`) and pure-Python
  unit tests; a slow cost check against v0.5 (`tools/hhc_test.sh test_cost`).
- **First test round fixes:** Displacement left unconnected (Bump drew lines in Cycles and doubled the
  cost), Scale computed from the source size at conversion. Real-material
  cost (boulder, Cycles): original 0.64 ms/sample, HHC Object 1.24, HHC UV 0.74.
- **Cost of the HHC node vs v0.5 `AT Anti-Tile`** (same material, 512², fixtures, RTX 4090):
  Cycles 3.716 vs 3.704 ms/sample (+0.3%), EEVEE compile 1.31 vs 1.34 s; +5 nodes, about 3 compiled.

## Measured costs

RTX 4090, Cycles in ms per sample; median of 3, viewports paused.

| Case | Plain UV | Box | dither v0 | v1 UV + height | Object 3a | **Object 3b / single node** |
|---|---|---|---|---|---|---|
| Plane 1024², 4K textures | 3.76 | 3.88 | 4.05 | 4.66 (+24%) | – | – |
| Wall + statue 1280×720 | 1.80 | 1.93 | – | 2.28 | 2.68 | 2.90 (+61% vs UV, +50% vs Box) |

- **Edge Warp:** +5% in Cycles (2.93 → 3.09 ms); EEVEE compilation +11% (0.90 → 1.00 s, median of
  5, within the run-to-run spread).
- **EEVEE compilation:** plain material about 0.27 s; single node in Object mode about 0.7–0.9 s.
  The measurement varies a lot, see the lessons learned.
- **Previous prototype (Opus Tessellatum), for comparison:** triplanar with 9 full reads; according
  to its README, EEVEE compilation took 1.37 s, and 3.67 s with Displacement.

## Timeline

| Step | What | Outcome | Results |
|---|---|---|---|
| 0 | Fresh restart. Research: industry, literature, Blender sources. Review of the Opus Tessellatum prototype (rejected as an extension for its cost) and of Hex Scatter (ideas only, its licence forbids redistribution) | **Single-read dithering** chosen | `docs/research-and-lessons.md` |
| 1 | v0: hexagons and noise zones with a random band, on UVs | Repetition gone, cost ≈ UV. **Blend judged very poor** (wide band); EEVEE with Linear blurs the bands (mipmaps) | `results/step1` |
| 2 | v1: height decides the boundary (3 candidates, AT Cells + AT Pick) | Boundaries almost invisible; +24% | `results/step2` |
| – | Bake check (done ahead of schedule) | Dithering **converges** in a Cycles bake | `results/bake_check` |
| 3a | Object projection, axis picked by dithering | No UV seams, but wide bands between axes | `results/step3a` |
| 3b | Axis decided by height: 6 candidates (2 axes × 3 cells) | Cuts between axes follow the height | `results/step3b` |
| v3 | **Single node with closure**: only one height in the tree; material laid out with frames | Same cost and image as 3b | – |
| v3+ | Projection menu UV / Object in the same node | The branch not chosen is not compiled (verified) | – |
| EEVEE | Flat grey bands along the cuts in EEVEE | Cause: Softness 0.03 too wide + mipmaps. **Softness 0.005** fixes it at no cost | `results/eevee_band` |
| Statue | Sharp lines on the statue | Object normals **verified** on every axis (0.77–0.84). Cause: cuts between cells where the height is flat → straight hexagon side. **Edge Warp** | `results/statue_lines` |

## Open issues and known limits
1. **Displacement in Bump mode.** Causes streaks along the axes, because it tilts the normal the
   node uses to choose the projection (the same cause was found on the Opus Tessellatum prototype
   and confirmed here). It also triples the cost. In this project the white dots look like
   fireflies instead.
   → Proposal: an **internal Height Bump**, with 2 extra reads of the height only, *inside the cell
   already chosen*, so no noise and no triple cost.
2. **True displacement and height bake:** a deterministic mode will be needed, i.e. a hard cut with
   no random band.
   - Confirmed on a flat-shaded Roundcube (Subdivision 2, Object projection, Displacement and
     Bump): dark slits open along face edges; they vanish with smooth shading or with Bump Only.
     Cause: with flat shading the vertices are split per face and each face is displaced along its
     own normal; in Object mode the node also picks the projection from that normal, so adjacent
     faces can read a different height at the same point. Workaround for now: smooth shading when
     using true displacement.
3. ~~**Interface.**~~ Solved by the add-on: the whole material, closure included, is built in one action.
4. **Edge Warp costs even at 0.** An On/Off menu switch doesn't work: with several Menu Switches on
   the same menu, the menu ends up with no items. A single Bundle-type switch could solve it, but the
   code needs restructuring.
5. **Recurring features from afar.** The most distinctive spots (for example the light "comma")
   remain recognisable, rotated. → Proposal: low-frequency macro variation on colour and roughness.
6. **Stretching** on surfaces at about 45° between two axes (up to about 1.7×). Typical of every
   per-axis projection.
7. **Object scale:** in Object mode the texture follows the object's scale, like a UV texture (a
   non-uniform scale stretches it). Apply the scale (Ctrl+A) for real-world size. A compensation in the
   node was tried (3 Vector Transforms) and dropped: it worked, but applying the scale does the same at
   zero cost.
8. **Materials without a height map:** no fallback. → Proposal: use the colour luminance.
9. **The Space menu of old test materials** is sometimes not restored by the rebuild: it falls back
   to the first item, Object.
10. ~~**Names.**~~ Solved: the node is `HHC Anti-Tile`; old `AT` materials are still recognised as sources.

## Proposed next steps, in order
1. Internal Height Bump, without noise and without the ×3 cost, plus a warning about Displacement in
   Bump mode.
2. ~~One-click operator and extension packaging~~ (done: the add-on). Next: two independent test rounds,
   fixes, then promotion to v1.0.
3. Macro variation, for repetition seen from afar.
4. UV bake, with the deterministic mode for height and displacement.
5. Optimise EEVEE compilation: the choice among 6 candidates can be written with fewer nodes.
6. Objective repetition metric with TexTile (`pip install textile-metric`).
