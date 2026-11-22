# kkbp-maps design

How kkbp-maps is meant to work. Terms are defined in [CONTEXT.md](../../CONTEXT.md). Decisions that would be surprising without context are in [docs/adr/](../adr/). What each Game's map data looks like is in [games.md](games.md), and the order of work is in [roadmap.md](roadmap.md).

Status: designed, no code yet.

## Shape

One Blender extension, `kkbp_maps`, in two stages:

```
game install ──Extractor──▶ Map Bundles (cache) ──Builder──▶ Map Library (.blend files + catalogs)
             (UnityPy, no bpy)                     (bpy)
```

- The **Extractor** reads a Game install from disk (ADR 0001) and writes one Map Bundle per Map. It never imports `bpy`, so its tests run on any Python, and a build resumes where it stopped.
- The **Map Bundle** is a contract in KKBP's style: JSON Schemas with `additionalProperties: false`, closed sets, a Manifest written last and a `major.minor` Schema Version.
- The **Builder** turns Map Bundles into a Map Library: Props, Structures and Map Variants, marked as assets with catalogs, tags and previews.
- Both run from an N-panel or from `blender -b`. Planned package layout: `extension/kkbp_maps/` with `extractor/` and `bundle/` (both bpy-free), `builder/`, `ui/`, `compat/` (the only place that checks Blender's version) and `deps/` (the first-run installer).

## Decisions

Numbered so code and reviews can point at them. Each says what holds now.

- **D1 Files only.** The Extractor reads the game's files and never starts the game (ADR 0001).
- **D2 Order.** KK first, then KKS, then SVS. Vanilla and DLC Maps first; Sideloader map mods (KK and KKS) later.
- **D3 Props.** A Prop is a `p_` subtree, kept once per Map Library by a hash of its meshes, materials and relative transforms, and tagged with every Map it appears in. Shell pieces are Structures (ADR 0004).
- **D4 EEVEE first.** The look is matched in EEVEE with the Standard view transform. Cycles renders sensibly but isn't matched.
- **D5 Two stages, one extension.** See "Shape".
- **D6 Separate repository.** kkbp-maps adapts KKBP's patterns rather than sharing code with it, and stays compatible with KKBP Characters: the same scale, axes, units and colour space.
- **D7 Lighting.** Map Variants use the Game's own Lightmap Set where it has one (KK, SVS, KKS's ported KK Studio Maps), plus a Lighting Rig recreated from the game's lights, sky, ambient light and fog. Props and Structures carry no lightmap.
- **D8 One asset per Map Variant** (ADR 0003).
- **D9 The Grade lives in materials**, through Variant Materials around shared Base Materials (ADR 0002).
- **D10 One Map Library per Game**: `KK Maps`, `KKS Maps`, `SVS Maps`, with catalogs `Maps/<area>`, `Props/<category>` and `Structure/<area>`. Nothing is shared across Games. Catalog UUIDs are uuid5 of the catalog path, so they stay the same across rebuilds.
- **D11 SVS's indoor rooms** are 2D sprites in the game: their 3D H furniture becomes Props and the backdrops are skipped.
- **D12 Level of detail.** Only LOD0 is kept; billboards are dropped. Vegetation gets a simple generic wind, scaled from the SpeedTree wind where it can be read.
- **D13 Shaders in tiers.** The PBR families (Unity Standard, URP Lit, SpeedTree, SpeedTree8) become Principled BSDF by fixed Unity-to-Blender rules. Illusion's own map shaders (KK's Shader Forge `main_*`, KKS's Koikano `main_item_map`, `map_tiling`) get Game Shader Models from their disassembled D3D11 code, as in KKBP (its ADR 0041). Water and rivers are approximated. Particles and volumetric beams are skipped at first.
- **D14 Names** come from the Name Tables in the repository: English Map names, a romaji-to-English word list, and category rules with overrides. Tags: Game, Maps, Time of Day, indoor or outdoor, category. A word the tables don't know keeps its romaji and is listed in the Build Report.
- **D15 KKBP Characters.** Each Map Variant records its light and Grade, for a later KKBP Hook that re-grades a Character to match. kkbp-maps makes no KKBP changes.
- **D16 Dependencies download at first run** (ADR 0005).
- **D17 Tests are local**, with a release checklist on Windows and macOS arm64, and the look is checked against Reference Captures (ADR 0006).
- **D18 Building a library.** The N-panel picks the game folder (the Game is detected), the Maps (all by default, with a disk and time estimate) and an output folder. The build runs as a background `blender -b` job that can resume. Afterwards it offers to register the Map Library in Blender's Preferences, and asks first. Map Variants use the game's own thumbnails; Props and Structures get EEVEE previews.
- **D19 Blender 5.2 LTS** is the minimum; every check runs on it and on the latest release.
- **D20 Game content is never committed** (ADR 0007).
- **D21 Files out.** Textures are written as PNG; HDR lightmaps and cubemaps as EXR. An optional size limit scales textures down.
- **D22 Studio Maps.** A Studio Map is a Map of its own only when its geometry hash differs from the story Map's.
- **D23 Developer tools are Python**, not shell scripts, so they run on all three platforms.

## ADRs

- [0001 Maps are read from the game's files, not captured in the running game](../adr/0001-maps-are-read-from-the-game-files.md)
- [0002 The Grade is applied inside materials, through Variant Materials around shared Base Materials](../adr/0002-the-grade-is-applied-inside-variant-materials.md)
- [0003 Each Time of Day is its own Map asset](../adr/0003-each-time-of-day-is-its-own-map-asset.md)
- [0004 Shell pieces are published as Structure assets beside the Props](../adr/0004-shell-pieces-are-structure-assets.md)
- [0005 Python dependencies download at first run](../adr/0005-dependencies-download-at-first-run.md)
- [0006 Tests run locally, and the look is checked against Reference Captures](../adr/0006-tests-are-local-and-the-look-is-checked-against-reference-captures.md)
- [0007 Game content is never committed](../adr/0007-game-content-is-never-committed.md)
