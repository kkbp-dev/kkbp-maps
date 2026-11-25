# kkbp-maps design

How kkbp-maps is meant to work. Terms are defined in [CONTEXT.md](../../CONTEXT.md). Decisions that would be surprising without context are in [docs/adr/](../adr/). What each Game's map data looks like is in [games.md](games.md), and the order of work is in [roadmap.md](roadmap.md).

Status: the KK spike's findings are in [kk-spike.md](kk-spike.md), the Map Bundle contract is in [map-bundle.md](map-bundle.md), the KK Extractor is in `extension/kkbp_maps/extractor/` (Phase 3), and the KK Builder in `extension/kkbp_maps/builder/` (Phase 4): its plan (no bpy) in `builder/`, the Blender side in `builder/blender/`, and the Name Tables in `names/`. The product shell (Phase 6) is the entry point and manifest, `deps/`, `jobs/` and `ui/`; its release checklist is [../release/v0.1.md](../release/v0.1.md).

## Shape

One Blender extension, `kkbp_maps`, in two stages:

```
game install ──Extractor──▶ Map Bundles (cache) ──Builder──▶ Map Library (.blend files + catalogs)
             (UnityPy, no bpy)                     (bpy)
```

- The **Extractor** reads a Game install from disk (ADR 0001) and writes one Map Bundle per Map. It never imports `bpy`, so its tests run on any Python, and a build resumes where it stopped.
- The **Map Bundle** is a contract in KKBP's style: JSON Schemas with `additionalProperties: false`, closed sets, a Manifest written last and a `major.minor` Schema Version ([map-bundle.md](map-bundle.md)).
- The **Builder** turns Map Bundles into a Map Library: Props, Structures and Map Variants, marked as assets with catalogs, tags and previews.
- Both run from an N-panel or from `blender -b`. Package layout: `extension/kkbp_maps/` with `extractor/` and `bundle/` (both bpy-free), `builder/`, `ui/` (the N-panel), `compat/` (the only place that checks Blender's version), `deps/` (the pinned wheels and the checks that they're installed) and `jobs/` (the Build driver and the memory watchdog, both bpy-free).

## Decisions

Numbered so code and reviews can point at them. Each says what holds now.

- **D1 Files only.** The Extractor reads the game's files and never starts the game (ADR 0001).
- **D2 Order.** KK first, then KKS, then SVS. Vanilla and DLC Maps first; Sideloader map mods (KK and KKS) later.
- **D3 Props.** A Prop is a `p_` subtree, kept once per Map Library by a hash of its meshes, materials and relative transforms, and tagged with every Map it appears in. Shell pieces are Structures (ADR 0004). A room container such as `p_koi_map71_park` is walked into, not made one Candidate (ADR 0019), and an unprefixed copy with a Prop's shape is a Placement of that Prop (ADR 0023).
- **D4 EEVEE first.** The look is matched in EEVEE with the Standard view transform. Cycles renders sensibly but isn't matched.
- **D5 Two stages, one extension.** See "Shape".
- **D6 Separate repository.** kkbp-maps adapts KKBP's patterns rather than sharing code with it, and stays compatible with KKBP Characters: the same scale, axes, units and colour space.
- **D7 Lighting.** Map Variants use the Game's own Lightmap Set where it has one (KK, SVS, KKS's ported KK Studio Maps), plus a Lighting Rig recreated from the game's lights, sky, ambient light and fog. Props and Structures carry no lightmap. KK's Sky Domes become the Map Variant's World background (the cubemap with its tint, exposure and rotation), and their clouds and stars stay as geometry in that Map Variant only, never as assets. The ambient light, lightmaps and reflections are computed in the Variant Materials, and in EEVEE the World only shows the Sky to the camera (ADR 0020).
- **D8 One asset per Map Variant** (ADR 0003). Times of Day that light a Map the same are one Map Variant, tagged with each of them (ADR 0009).
- **D9 The Grade lives in materials**, through Variant Materials around shared Base Materials (ADR 0002). In EEVEE the Grade is applied to the lit result through Shader to RGB; a second Material Output gives Cycles the ungraded BSDF (ADR 0008).
- **D10 One Map Library per Game**: `KK Maps`, `KKS Maps`, `SVS Maps`, with catalogs `Maps/<area>`, `Props/<category>` and `Structures/<area>`. Nothing is shared across Games. Catalog UUIDs are uuid5 of the Game and the catalog path (`KK/Props/Furniture`), so they stay the same across rebuilds and differ between Games. A Map Library is a folder with one file per Map, one for the Props and one for the Structures (ADR 0022); each Game's folder is registered as an asset library of its own.
- **D11 SVS's indoor rooms** are 2D sprites in the game: their 3D H furniture becomes Props and the backdrops are skipped.
- **D12 Level of detail.** Only LOD0 is kept; billboards are dropped. Vegetation gets a simple generic wind, scaled from the SpeedTree wind where it can be read.
- **D13 Shaders in tiers.** The PBR families (Unity Standard, URP Lit, SpeedTree, SpeedTree8) become Principled BSDF by fixed Unity-to-Blender rules. Illusion's own map shaders (KK's Shader Forge `main_*`, KKS's Koikano `main_item_map`, `map_tiling`) get Game Shader Models from their disassembled D3D11 code, as in KKBP (its ADR 0041). In KK only lovehotel uses one (`main_item`, 2 renderers), so its model waits until a Golden Map needs it, and it is approximated as Principled until then. Unlit shaders are rebuilt exactly, KK's foliage among them, which is drawn with `Particles/Alpha Blended` on plain meshes. Water and rivers are approximated. Particle systems, mirrors, heat haze and volumetric beams are skipped at first. The Build Report lists every material each tier approximated or left out.
- **D14 Names** come from the Name Tables in the repository: English Map names, a romaji-to-English word list, and category rules with overrides. Tags: Game, Maps, Time of Day, indoor or outdoor, category. A word the tables don't know keeps its romaji and is listed in the Build Report.
- **D15 KKBP Characters.** Each Map Variant records its light and Grade, for a later KKBP Hook that re-grades a Character to match. kkbp-maps makes no KKBP changes.
- **D16 Dependencies ship inside the extension**, one zip per platform with its own wheels, installed by Blender with the extension; numpy and attrs are Blender's own (ADR 0029, superseding ADR 0005).
- **D17 Tests are local**, with a release checklist on Windows and macOS arm64, and the look is checked against Reference Captures (ADR 0006).
- **D18 Building a library.** The N-panel picks the game folder (the Game is detected), the Maps (all by default, with a disk and time estimate), an output folder and a Camera Profile (each Map's own by default). The output folder holds the Map Library (`KK Maps/`) and the Bundle Folder (`Map Bundles/`), which is kept between builds. The build runs outside Blender's process: a driver runs each step in its own watched process, the Extractor on Blender's Python and the Builder in `blender -b`. It can be cancelled and resumed, stops with Blender, and skips and reports a Map that fails or runs short of memory. Afterwards it offers to register the Map Library in Blender's Preferences, and asks first. Map Variants use the game's own thumbnails; Props and Structures get EEVEE previews.
- **D19 Blender 5.2 LTS** is the minimum; every check runs on it and on the latest release.
- **D20 Game content is never committed** (ADR 0007).
- **D21 Files out.** Textures are written as PNG; HDR lightmaps and cubemaps as EXR. An optional size limit scales textures down.
- **D22 Studio Maps.** A Studio Map is a Map of its own only when its geometry hash differs from the story Map's.
- **D23 Developer tools are Python**, not shell scripts, so they run on all three platforms.
- **D24 Camera settings.** The game camera's tonemapper, exposure and sun shafts aren't in the map files. The capture plugin reads them once per Game, and they are kept in the repository as Game data, one Camera Profile per game camera (ADR 0010). Each Map names the Camera Profile that shows it.
- **D25 The Map Bundle** is in Blender's space (ADR 0011), names meshes, materials and textures by Content Hash (ADR 0012), and is checked by `bundle/`'s own validator (ADR 0013). Its Schema Version is `0.x`, matched exactly, until the contract covers every Game (ADR 0014, amended by ADR 0030). See [map-bundle.md](map-bundle.md).

## ADRs

- [0001 Maps are read from the game's files, not captured in the running game](../adr/0001-maps-are-read-from-the-game-files.md)
- [0002 The Grade is applied inside materials, through Variant Materials around shared Base Materials](../adr/0002-the-grade-is-applied-inside-variant-materials.md)
- [0003 Each Time of Day is its own Map asset](../adr/0003-each-time-of-day-is-its-own-map-asset.md)
- [0004 Shell pieces are published as Structure assets beside the Props](../adr/0004-shell-pieces-are-structure-assets.md)
- [0005 Python dependencies download at first run](../adr/0005-dependencies-download-at-first-run.md) (superseded by 0029)
- [0006 Tests run locally, and the look is checked against Reference Captures](../adr/0006-tests-are-local-and-the-look-is-checked-against-reference-captures.md)
- [0007 Game content is never committed](../adr/0007-game-content-is-never-committed.md)
- [0008 The Grade is applied to the lit result in EEVEE, with an ungraded output for Cycles](../adr/0008-the-grade-is-applied-to-the-lit-result-in-eevee.md)
- [0009 Times of Day that light a Map the same are one Map Variant](../adr/0009-identical-times-of-day-are-one-map-variant.md)
- [0010 The game camera's settings are captured once and kept as Game data](../adr/0010-camera-settings-are-captured-once-as-game-data.md)
- [0011 The Map Bundle is in Blender's space, with meshes as raw buffers](../adr/0011-the-map-bundle-is-in-blender-space-with-raw-mesh-buffers.md)
- [0012 Meshes, materials and textures are named by Content Hash](../adr/0012-meshes-materials-and-textures-are-named-by-content-hash.md)
- [0013 The checker validates the JSON Schemas itself](../adr/0013-the-checker-validates-the-schemas-itself.md)
- [0014 The Schema Version stays 0.x until the first release](../adr/0014-the-schema-version-stays-0x-until-the-first-release.md)
- [0015 The Extractor replays what the game shows when a Map loads](../adr/0015-the-extractor-replays-the-games-start-up-visibility.md)
- [0016 Sky Domes are kept as sky nodes without a renderer](../adr/0016-sky-domes-are-renderer-less-sky-nodes.md)
- [0017 Every readable renderer is carried, whatever its shader](../adr/0017-every-readable-renderer-is-carried-whatever-its-shader.md)
- [0018 Materials keep only the properties their shader declares](../adr/0018-materials-keep-only-their-shaders-properties.md)
- [0019 Room containers are walked into, not made one Candidate](../adr/0019-room-containers-are-walked-into.md)
- [0020 Indirect light is computed in Variant Materials, and the World draws only the sky](../adr/0020-indirect-light-is-computed-in-variant-materials.md)
- [0021 Fog is applied in the material, before the Grade](../adr/0021-fog-is-applied-in-the-material-before-the-grade.md)
- [0022 A Map Library is one file per Map, plus one for the Props and one for the Structures, with data copied between them](../adr/0022-a-map-library-is-one-file-per-map-with-data-copied.md)
- [0023 Unprefixed copies of a Prop are its Placements, and unbaked reflection probes are left out](../adr/0023-unprefixed-copies-of-a-prop-are-its-placements.md)
- [0024 Shadow Casters are carried, and renderers keep Unity's shadow mode](../adr/0024-shadow-casters-are-carried.md)
- [0025 Real-time GI is approximated from the ambient light](../adr/0025-real-time-gi-is-approximated-from-the-ambient.md)
- [0026 A renderer can refuse reflection probes](../adr/0026-a-renderer-can-refuse-reflection-probes.md)
- [0027 Blended surfaces are sorted by their bounds' centre](../adr/0027-blended-surfaces-are-sorted-by-their-bounds-centre.md)
- [0028 The story camera's height fog is drawn in the materials and the World](../adr/0028-the-story-cameras-height-fog-is-drawn-in-materials-and-the-world.md)
- [0029 The wheels ship inside the extension, one zip per platform](../adr/0029-the-wheels-ship-inside-a-zip-per-platform.md)
- [0030 The Schema Version stays 0.x through v0.1](../adr/0030-the-schema-version-stays-0x-through-v0-1.md)
