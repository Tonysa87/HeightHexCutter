# HHC add-on: one-click HHC materials — design

Date: 2026-11-07. Status: agreed with the user in conversation; reviewed by a builder check; waiting for the user's approval of this document.

## Intent

Today an HHC material has to be wired by hand: closure zone, height and normal inside it, the node,
every other texture fed by the node's Vector output, AO multiply, displacement. That is slow and easy
to get wrong. The user wants a Blender add-on that takes an existing material (or a set of image
files), recognises its maps, and builds a new, tidy HHC material from them, ready to use. All
tuning then happens on the HHC node itself; the add-on is only a builder.

The add-on is also the moment to finish the rename from the provisional `AT` prefix to `HHC`, and to
get rid of the Italian labels left in hand-built materials.

## What the user will see

### Entry points (only these three)
1. **Asset Browser → right-click a material asset → "HHC: Use This Material"**
   (local or external asset library).
2. **Shader Editor → N panel → tab "HHC" → "From Material…"**: a search popup listing the materials
   in the file that contain at least one Image Texture. Same result as entry 1.
3. **Shader Editor → N panel → tab "HHC" → "From Image Files…"**: Blender's file browser,
   multi-select. After the selection the user is asked for a name (pre-filled with the folder name).

The N panel contains nothing else. No settings, no map list, no bake: every setting lives on the
HHC node.

### Result of every entry point
- A **new material** named `<source name>_HHC` (entries 1–2) or `<typed name>_HHC` (entry 3).
  Blender's usual `.001` suffix applies if the name is taken. **The source material is never
  modified.**
- The new material is **added to the active object**: appended as a new slot at the end if the object
  already has material slots, as the first slot if it has none. The new slot becomes the active slot.
  Faces are not reassigned (on an object with existing materials nothing changes visually until the
  user assigns faces; this was accepted).
- If there is no active object, or it cannot hold materials, the operator stops with a clear error and
  creates nothing.
- An INFO report lists which file went to which channel, which maps became constant values, and which
  files were ignored.

### Layout of the generated material
Laid out as in the user's reference screenshot, left to right, with short English frame labels:

```
[Frame "Sampler"]                                   [Frame "Textures"]
 Closure Input (Vector) ─┬─> Height image ─┐          Base Color image ─┐
                         └─> Normal image ─┴> Closure Output           AO image ─── Multiply ─> Principled BSDF ─> Material Output
                                               │ Sampler              Roughness image ─────────┘        ▲             ▲
                                          [HHC Anti-Tile] ── Vector ─> (all images in "Textures")    Normal      Displacement
                                               ├─ Normal ─────────────────────────────────────────────┘             │
                                               └─ Height ──────────────────────────────> [Frame "Displacement"] Displacement node
```

- **Sampler** (the closure zone): Height (or its fallback, see below) and Normal images.
- **HHC Anti-Tile** node between the sampler and the textures.
- **Textures**: Base Color, AO, Roughness, Metallic, each fed by the node's Vector output.
- Base Color × AO through a Mix (Multiply, factor 1) into Principled Base Color. No AO → Base Color
  goes straight in.
- HHC Normal output → Principled Normal directly (no Normal Map node: the HHC node decodes the normal
  map itself).
- **Only when a real Height map exists:** HHC Height output → Displacement node → Material Output
  Displacement, and material setting **Displacement = Bump Only** (the user can change it
  afterwards). Without a Height map **no Displacement or Bump node is created** and the Material
  Output Displacement socket stays empty: the height fallback below still feeds the sampler (it drives
  the cell cuts), but it is not used as relief. If the user finds a height map later, they put it in
  the sampler and add the Displacement node by hand.
- Displacement node: Scale copied from the source material's Displacement node if it has one,
  otherwise 0.02 (Blender's default of 1.0 is far too strong); Midlevel 0.5.
- Node labels are the channel names in English ("Base Color", "AO", "Roughness", "Metallic",
  "Height", "Normal", "ORM").

### Node defaults
Projection **Object**. Other inputs keep the group defaults; the group defaults are updated to the
values tuned so far: Scale 1, Cell Size 1, Rotation 1, Seed 0, Height Influence 1.5,
Softness 0.005, Normal Strength 1, Edge Warp 1.0, Sharpness 4, Space Object.

## Map recognition

### Channels handled
Base Color, AO, Roughness, Metallic, Normal, Height, and ORM/ARM packed maps. Anything else
(emission, opacity, specular, SSS, translucency…) is **ignored and listed in the report**.

### From a material (entries 1–2)
First read the node structure, as Opus Tessellatum did (`collect_material_maps` in its add-on, used
as reference only): images upstream of Principled Base Color (an AO multiplied in is recognised as
AO), Roughness, Metallic; Normal Map node → Normal (its `convention` gives OpenGL/DirectX); Bump
Height or Displacement Height → Height; Separate Color channels → packed map. Then fill in any
channel still missing from the file names of the remaining Image Texture nodes. If the source is
already an HHC material, its maps are read the same way (the images inside its sampler count).

External asset library materials are appended temporarily, read, then removed; images already in the
file (same absolute path) are reused instead of the appended copies, and appended images left without
users are removed.

### From file names (entry 3, and the fill-in above)
Classic suffixes and tokens, case-insensitive, ignoring resolution/version tokens (`4k`, `2048`,
`v2`…): e.g. `basecolor albedo diffuse diff color col`, `ao ambientocclusion occlusion`,
`roughness rough`, `metallic metalness metal`, `normal nrm nor normalgl normaldx`,
`height displacement disp bump`, `orm arm`, plus single-letter last tokens (`_H`, `_N`, `_R`, `_M`…).
`dx`/`directx` in a normal map name → DirectX. Opus Tessellatum's `CHANNEL_KEYS` / `detect_channel`
is a good starting point. If both a GL and a DX normal are present, prefer GL.

Colour spaces: Base Color sRGB, everything else Non-Color.

### ORM / ARM packed maps
One Image Texture, one Separate Color: R → AO, G → Roughness, B → Metallic. Not split into separate
files. If a separate map for one of these channels also exists, the separate map wins for that
channel.

### Adjustment nodes between an image and the BSDF
Nodes sitting between a recognised image and its Principled input (Invert on a gloss map, Color Ramp
or Math on roughness, Hue/Saturation or Brightness/Contrast on colour, an AO Mix with a factor below 1,
etc.) are **copied as they are** into the new material, with the same settings, between the HHC-fed
image and the Principled input. Normal Map node Strength is carried over to the HHC node's Normal
Strength; Bump/Displacement Scale to the new Displacement node.

### Constant maps
Each image (or each used channel of a packed map) is checked once by reading its pixels. If it is
uniform (every pixel within 1/255 of the mean, per channel), no texture is loaded for it:
- Base Color / Roughness / Metallic → the value is written into the Principled BSDF input.
- AO uniform → dropped (no Multiply).
- Normal uniform (flat) → treated as missing.
- Height uniform → treated as missing (fallback below).
- A packed map whose three used channels are all uniform is not loaded at all.

Missing maps simply have no node; their Principled input keeps its default.

### Height fallback (the node needs a height to decide where cells meet)
In order, the first available goes into the sampler's Height:
1. the Height map;
2. the AO map (cavities dark, relief bright);
3. the Base Color map → RGB to BW → **Color Ramp**, inside the sampler, labelled
   "Height from Base Color (adjust)", so the user can tune contrast/threshold or invert it;
4. none → the sampler has no height (constant), the node falls back to plain hexagons softened by
   Edge Warp.

The normal map is not used as a height source (it encodes slopes, not heights).

## Node changes (part of this work)

1. **Rename** `AT Anti-Tile` → **`HHC Anti-Tile`**; the helper and single-mode groups move to the
   `HHC` prefix too. The add-on builds the groups it needs into the current file the first time it is
   used, from code shipped inside the add-on (`nodes/ngkit.py`, the `hex_core` part of
   `nodes/build_v1.py`, `nodes/build_v3.py`, ported into the add-on package).
2. **Vector input: hide its value fields** (`hide_value`). With nothing connected the node already
   falls back to the active UV map (length test in `build_tile`); the visible 0,0,0 fields suggest a
   connection is required and, if edited, silently disable the fallback.
3. **New menu input "Normal Map": OpenGL / DirectX**, same name and items as Blender's Normal Map
   node `convention`. DirectX flips the green channel of the normal map read from the sampler,
   in both the UV and the Object branch. The add-on sets it from the detected convention.
   Pitfall from earlier work: several Menu Switches on the same menu input leave the menu with no
   items. Use **one** Menu Switch (Float: OpenGL 1, DirectX −1, the same trick as the Space menu) and
   use its output in both branches.
4. Group defaults updated as listed under *Node defaults*.

Cost constraint: none of this may make the shader measurably heavier. The menu is resolved at
compile time; the green flip is one multiply.

## Packaging

A Blender extension (`blender_manifest.toml`), id `height_hex_cutter`, name "Height Hex Cutter",
version 0.5.0, maintainer Tonysa87, Blender ≥ 5.2, add-on code in its own folder of this repository.
Licence: GPL-3.0-or-later, required for add-ons on extensions.blender.org (builder's call, flagged
to the user). A small build script producing the installable zip, like Opus Tessellatum's `build.py`.

All user-facing text, labels, reports, comments and file names in English.

## Goals
- One action from an asset, a scene material or a set of files to a correct, tidy HHC material.
- Correct channel recognition on common sources (Megascans/Fab, Poly Haven, ambientCG, Substance
  exports).
- No uniform texture ever loaded.

## Non-goals (for this step)
- Settings, map swapping or bake in the panel (the old Opus panel had them; not wanted now).
- Opacity/alpha, emission and other channels.
- Converting a material in place, or migrating existing `AT …` materials in the user's test file.
- Internal Height Bump, deterministic mode, macro variation (later roadmap steps).

## Anti-goals (failure even if it technically works)
- Touching the source material, or any material other than the new one.
- A heavier shader than today's node.
- Italian text anywhere in the add-on, the generated material or the repository.
- Rebuilding existing HHC groups in a file in a way that disconnects materials already using them
  (always the safe rebuild, see `docs/research-and-lessons.md`).

## Testing constraints
- The user's open file contains their own materials: never test on them. Use the `AT_Bench` scene and
  new test objects/materials only, and diff the user's materials before/after any test session.
- Ask the user before running Blender (headless or through the MCP bridge).
- Verify on at least: a Megascans-style asset (Color, AO, Roughness, Metallic all black, Normal,
  Height), a set with an ORM map, a set without height (AO fallback, then colour fallback), a DirectX
  normal set, an external asset library material. Check the generated shader cost against today's
  node (Cycles ms/sample, EEVEE compile) with `bench/bench.py`.

## Decisions taken by the designer (flagged to the user, not discussed in detail)
- **Principled settings and unlinked inputs** are copied from the source material's Principled BSDF
  (values of inputs without a map, distribution, subsurface method). Entry 3 uses Blender defaults.
- **Colour spaces:** set only on images loaded by the add-on. An image datablock already used by
  another material is never modified (that would change the source material); if its colour space
  looks wrong for its channel, the report says so.
- **Existing groups in the file:** the add-on stamps its groups with a version property
  (`hhc_version`). Same version → reused. Older version → updated with the safe rebuild (links and
  values of every material using it are preserved) and reported. A group with an HHC name but no
  stamp is not touched; the add-on builds its own under a free name. Duplicates arriving with
  appended assets (`HHC Anti-Tile.001` with the same stamp) are remapped to the main group and
  removed.
- **Single source of node code:** the add-on package becomes the only home of the node builders.
  `nodes/` is folded into it (historical builders v0/v2 stay in the git history at tag `v0.5`),
  `bench/` imports from the add-on and uses HHC names.
- **Old `AT …` materials as sources:** a material using `AT Anti-Tile` is read like an HHC material
  (maps taken from its sampler).
- **Material slots:** if the last slot of the active object is empty it is filled instead of adding
  a new one. Slots are added to the mesh data (Blender's default), so objects sharing the mesh get the
  slot too; the report mentions it when the mesh has more than one user.

## Left to the builder
Exact node positions and spacing; frame colours; operator ids and class names; how the pixel
uniformity check is implemented (numpy over `Image.pixels.foreach_get`, cached per image);
report wording; the build script.

## Changes after the first test round (2026-11-07, agreed with the user)
- **Displacement is created but not connected.** In Bump mode Cycles re-evaluates the whole node at
  offset points, each with its own random cell choice: straight lines along the screen axes on flat
  surfaces, and about 2× the cost (boulder: 2.61 vs 1.24 ms/sample). The Displacement node is still
  built (scale from the source) inside a frame labelled "Displacement (not connected)"; the material's
  displacement method is left at Blender's default. The normal map carries the relief; an internal
  Height Bump (next step, before 1.0) will add relief without these problems.
- **Scale matches the source.** At conversion the HHC Scale (repeats per metre) is computed from the
  target object: `Scale = source Mapping scale / metres per UV unit`, with metres per UV unit =
  sqrt(object-space surface area / UV area) of the active UV map. No usable UVs →
  0.5 (2 m per texture). From image files the Mapping scale is 1. A converted HHC/AT source keeps
  its own node settings instead.
- **Object scale is not compensated in the node** (decided after trying it): like a UV texture, the
  texture follows the object's scale; apply the scale for real-world size. estimate_scale works in
  object space, so the converted size matches the source on scaled objects too.
- The report warns when the object has no UV map (the UV projection would not work on it).
