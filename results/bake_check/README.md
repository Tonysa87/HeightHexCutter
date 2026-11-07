# Bake check: does the per-sample dithering converge in a Cycles bake?

Date: 2026-11-07 — Blender 5.2.2, Cycles GPU (OptiX, RTX 4090). Done ahead of schedule; kept as the
reference for the future bake work.

## Question
The anti-tile nodes choose the cell at random for every render sample (White Noise of the shading
Position, which moves sub-pixel at every sample), and rely on sample accumulation to blend the
transition. For a camera render this works. In a bake Cycles samples inside each texel: does the
Position change per sample there too, or does the transition freeze into a fixed noise?

## Setup
- Object `AT_Plane` (scene `AT_Bench`), material v1 (AT Cells + AT Pick, Height Influence 1.5).
- Bake type Diffuse, Color pass only, 1024 × 1024, margin 4, `use_clear`.
- Two materials:
  - `AT_v1_bake`: the normal v1 colour.
  - `AT_v1_bake_dbg`: random colour per chosen cell, with Softness raised to 0.3 so the dithered
    bands are wide (harsh case).
- 1 sample vs 64 samples.

## Result
| Bake | High-frequency energy (mean abs Laplacian, 8-bit) |
|---|---|
| debug, 1 sample | 40.6 |
| debug, 64 samples | 11.6 |
| v1 colour, 1 sample | 90.7 |
| v1 colour, 64 samples | 30.4 |

At 1 sample the bands are salt-and-pepper; at 64 samples they are smooth gradients
(`bake_1_vs_64_samples.png`). **The bake jitters the position per sample: dithering converges
in the bake as in a camera render.** (The v1-colour 1-sample value also contains the texture's own
aliasing without per-texel AA.)

## Notes for the bake phase
- Use enough bake samples for the transition bands (64 looked clean here with Softness 0.3; the
  default Softness 0.03 gives much narrower bands).
- Not yet tested: Normal bake (tangent space) of the dithered normal, EEVEE (no bake), very
  low sample counts with denoising.
