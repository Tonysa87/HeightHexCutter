# Research, cost model and lessons learned

## 1. Initial research: summary
Three parallel surveys: what the industry does, scientific literature, Blender 5.2 sources.

**The industry saves by reading less, not with smarter maths.**
- **Unreal TextureVariation** produces *one* coordinate shared by every map, with a height input and
  a dither option. This is exactly the usage pattern we wanted.
- **Jason Booth (MicroSplat)** uses height blending and skips zero-weight samples: on average about
  1.5 reads instead of 3.
- **Unity Terrain and Karma** use hex × triplanar, i.e. 9 reads. Karma has reported artefacts on the
  normals.

**Literature:**
- **Stochastic Texture Filtering** (Pharr et al., I3D 2024): in a path tracer you pick *one* cell per
  sample, with probability equal to its weight, and the renderer does the averaging. This is the
  basis of our dithering.
- **Mishkinis:** height-based priority.
- **Quilez, technique 3:** 2 reads, noise-driven choice.
- **Mix-Max** (Fournier and Sauvage, 2024): confirms that "height max" is the right operator.
- Everything requiring per-texture precomputation was discarded: Wang tiles, histogram tables,
  Lutz–Gilet, full Mix-Max. It would break "drop the node in and connect it".

**Hex Scatter** (commercial asset; "Studio-Friendly" licence, redistribution forbidden):
- Used for ideas only: the hexagonal grid built from two offset lattices, and the single-read
  Dithered variant that returns just a Vector.
- Hard to use because the images live *inside* the groups: the group has to be duplicated per
  material and a script has to be run.

## 2. Blender 5.2 cost model
Verified in the sources, branch `blender-v5.2-release`.

- **Inline copies.** Every group instance, every Evaluate Closure and every unrolled iteration is
  copied in full into the compiled code. EEVEE does not merge identical computations (CSE); Cycles
  does.
- **Bump and Displacement in Bump mode:** the upstream graph is evaluated 3 times, in both engines.
- **Unused branches:**
  - Mix on colours, floats and vectors always computes both branches.
  - Mix Shader skips the unused branch only in Cycles, and only with a factor of exactly 0 or 1.
  - **Menu Switch is free:** the branch not chosen is not compiled. Verified: the single node in
    Object mode generates the same shader as the Object-only node.
- **Per-sample randomness:** there is no dedicated node. However, the position jitters by a fraction
  of a pixel at every sample, both in Cycles and in EEVEE's TAA, and White Noise works on the exact
  bits of its input. So `White Noise(Position)` gives a new number at every sample. It works in
  bakes too.
- **EEVEE mipmaps:** with Linear, EEVEE uses `textureGrad` with derivatives computed over 2×2 pixel
  quads. If neighbouring pixels pick different cells, the smallest mipmap is used. Closest and Cubic
  don't use mipmaps. Cubic costs 4 reads: about 3× in Cycles.
- **EEVEE compilation:** grows with the size of the generated code.
  - A **Noise** node pulls in its whole library: about +0.3 s.
  - **White Noise** is light.
  - A connected **alpha** triples the passes to compile (prepass and shadows).

## 3. Paths tried and discarded

| Path | Why discarded |
|---|---|
| Wide random band (v0) | dirty blend, blurred bands in EEVEE |
| Quilez-style noise zones instead of hexagons | similar to hexagons but slightly more expensive; hexagons preferred |
| Cubic for EEVEE | 3× the cost in Cycles |
| Closest for EEVEE | works, but EEVEE about +40%; low Softness is enough |
| Projection axis picked by dithering only (3a) | wide bands between axes |
| Low Sharpness for projection transitions | changes 2–5% of the pixels: not the cause |
| High Height Influence against straight lines | ineffective where heights are equal |
| Edge Warp with the Noise node | EEVEE compilation +40–60% |
| Vertical Edge Warp with Noise Fac | doesn't bend the vertical hexagon sides |
| Edge Warp On/Off switch with several Menu Switches | the menu ends up with no items |
| Image as a group input | 5.2 shader groups have no Image socket type → closure |

## 4. Lessons learned and technical pitfalls
- **Rebuilding a group wipes its interface** and disconnects every material using it. Always use
  `ngkit.safe_rebuild` (i.e. `build_all()`) and check the user material before and after. Use
  `_test_*` groups for experiments.
- **Blender crash** (access violation): changing the `node_tree` of an existing group node and
  writing its sockets in the same call. Create a new node instead.
- **Menus in groups:** the value must be restored as a string, and after a graph update. Several
  Menu Switches connected to the same menu don't work.
- **Cycles measurements:** viewports in Rendered mode compete for the GPU, and writing PNGs to the
  `\\wsl.localhost` share is slow and erratic. Pause the viewports, save renders to a local temp
  folder, and use the median.
- **EEVEE compilation measurements:** EEVEE reuses shaders with identical code. Use a different
  random structure for every measurement and take the median of 5.
- **PIL** reads 16-bit RGBA PNGs as 8-bit.
- **Test materials with no users** are not saved in the .blend. Give them a fake user.
- **WSL and Blender:** the MCP add-on listens on Windows' 127.0.0.1, which is not reachable from
  WSL. The MCP server therefore runs in a Windows Python environment, and the `tools/` scripts go
  through PowerShell.
- **Cost discipline:** a fix that makes the material heavier is not worth it.
