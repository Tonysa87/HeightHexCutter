# Project status — 2026-11-07 (v0.5)

## Where we are
- **Single node `AT Anti-Tile`** (`nodes/build_v3.py`), with a Projection menu UV / Object.
  - Height and normal map reach it through a closure.
  - All other maps are read only once.
- **Material in use:** "Painted Damaged Wall AT" in the test file `anti-tile1.blend` (not included
  in the repository), assigned to a plane, a broken wall and an antique sculpture.
  - Values: Projection Object, Scale 2/m, Height Influence 1.5, Softness 0.005, Edge Warp 1.0,
    Sharpness 4.
  - Displacement (Bump) is still connected to the material output: a deliberate choice for now,
    but it causes streaks (see open issues).
- **Test scene `AT_Bench`** in the same file:
  - copies of the three objects with their own data: AT_Plane, AT_Wall, AT_Statue;
  - cameras: AT_Cam (orthographic, top view), AT_CamClose, AT_CamObj, AT_CamStatue, AT_CamWall;
  - light AT_Sun.
  - Unassigned test materials are lost on save unless they have a fake user.

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
3. **Interface.** The closure zone has to be built by hand. → Proposal: an "add Anti-Tile" operator
   that creates the zone and moves height and normal into it automatically.
4. **Edge Warp costs even at 0.** An On/Off menu switch doesn't work: with several Menu Switches on
   the same menu, the menu ends up with no items. A single Bundle-type switch could solve it, but the
   code needs restructuring.
5. **Recurring features from afar.** The most distinctive spots (for example the light "comma")
   remain recognisable, rotated. → Proposal: low-frequency macro variation on colour and roughness.
6. **Stretching** on surfaces at about 45° between two axes (up to about 1.7×). Typical of every
   per-axis projection.
7. **Non-uniform object scale:** not compensated in Object mode.
8. **Materials without a height map:** no fallback. → Proposal: use the colour luminance.
9. **The Space menu of old test materials** is sometimes not restored by the rebuild: it falls back
   to the first item, Object.
10. **Names:** node groups still use the provisional "AT …" prefix.

## Proposed next steps, in order
1. Internal Height Bump, without noise and without the ×3 cost, plus a warning about Displacement in
   Bump mode.
2. One-click operator to create the closure. Then packaging as an extension: final names and panel.
3. Macro variation, for repetition seen from afar.
4. UV bake, with the deterministic mode for height and displacement.
5. Optimise EEVEE compilation: the choice among 6 candidates can be written with fewer nodes.
6. Objective repetition metric with TexTile (`pip install textile-metric`).
