# The Games' map data

What a survey of the HF Patched installs found (KK HF Patch v4.2, KKS v2.2, SVS v2.0), read with UnityPy 1.25.4. Paths are relative to the game folder. The Phase 1 spike checks the items marked *to confirm*.

## Common to all three

- Map bundles are standard UnityFS with LZ4HC compression and no encryption. They carry type trees, so UnityPy reads every component, MonoBehaviours included.
- Every 3D Map is a streamed Scene Bundle: `BuildPlayer-<Scene>` and `BuildPlayer-<Scene>.sharedAssets`, with one `Assets/…/<Scene>.unity` path.
- Object names are ASCII, romanized Japanese, with Unity's ` (N)` duplicate suffixes. Prefixes: `p_` props, `mo_` and `o_` shell geometry, `n_` groups. Repeated objects share one Mesh (path id), which makes Prop hashing reliable.
- Every Shader object carries a compiled D3D11 blob, so shaders can be disassembled as KKBP's `importer/tools/game_shaders/dump.py` does.
- No crunched textures. Normal maps are DXT5 with the DXT5nm swizzle.
- Helpers to leave out: inactive GameObjects, disabled renderers, shadow-only casters (`castShadows = 3`), collider-only objects, Unity's built-in meshes. Layer names aren't in the bundles, only their numbers.
- Map names are Japanese. SVS keeps its lists in MemoryPack binaries; KK and KKS keep them in Excel-style MonoBehaviours.

## KK

- Unity 5.6.2f1, Mono, built-in render pipeline; post effects from AmplifyColor and AmplifyOcclusion.
- 41 Scene Bundles in `abdata/map/scene/` (about 1.1 GB), each self-contained; 2 Studio-only Maps in `abdata/studio/map/`.
- Lists: `abdata/map/list/mapinfo/*` (`MapName`, `No`, `AssetBundleName`, `AssetName`, `isOutdoors`, thumbnails) and Studio's `abdata/studio/info/*` (`Map_*`).
- A single `Map` root with 3 to 18 group nodes, usually 150 to 300 MeshRenderers per Map. No static batching, no LODGroups; meshes are readable.
- Shaders: 22 in all, mostly Unity `Standard`; also `Shader Forge/main_*`, `Custom/StandardDouble`, skyboxes and particles.
- Lightmaps: baked directional lightmaps (`Lightmap-N_comp_light`, `_comp_dir`, up to 2048²) in most Maps; `m_LightmapsMode 1`, `m_LightmapFormat 2` (*to confirm*: RGBM, and whether the project is gamma or linear). Which renderer uses which lightmap comes from the `LightmapPrefab` component, not the renderer's own `m_LightmapIndex`. No lightmaps in backyard, courtyard, rooftop or livestage.
- Lights: one realtime directional sun per Map, plus RenderSettings ambient (skybox SH or flat), linear fog and a procedural or 6-sided skybox.
- Times of Day: day, evening, night, in `SunLightInfo`: sun angle, colour and intensity, fog, sun shafts, an AmplifyColor LUT, and a `visibleList` of objects to show. The lightmaps are the same for all three.
- Helpers: `Cube (N)` collision boxes, `*_kage*` and `p_koi_map00_shadow` shadow casters.
- Mods: 53 Sideloader map zipmods (305 Scene Bundles, 8.5 GB), laid out like the base game and stored uncompressed.

## KKS

- Unity 2019.4.9f1, Mono, built-in pipeline with PostProcessing v2 and AmplifyColor.
- 31 small Scene Bundles in `abdata/map/scene/` that depend on `abdata/map/materials/00.unity3d` (815 MB) and some on `map/common/00`. `hotelsuite` is self-contained.
- Studio: 76 bundles (about 5 GB) in `abdata/studio/map/`. 42 are KK Maps rebuilt for 2019.4, which keep their KK lightmaps; 31 are `*_studio` versions of KKS Maps.
- Lists: `map/list/mapinfo/*` (adds `DisplayName`, `isSky`, thumbnails per Time of Day) and `studio/info/*`.
- Shaders: 35, mostly `Standard` and `Nature/SpeedTree`; Illusion's `Koikano/main_item_map`, `map_tiling`, `sub_mob`; Lux Water, NatureManufacture River, ProBuilder, Funly SkyStudio.
- 79 renderers in 10 interior Maps are statically batched into one `Combined Mesh (root: scene)` per Map; `m_StaticBatchInfo` gives each one's submesh range. Unbatched copies keep their own mesh.
- Vegetation is SpeedTree: LOD0 to LOD2 plus a billboard.
- No lightmaps. 2 to 31 realtime lights per Map, reflection probes, trilight or flat ambient.
- Times of Day: four, through `SunLightInfo` (with ambient colours and fog) and `MapSkyInfo`, which points at Funly SkyStudio `SkyProfile`s. Some objects exist once per Time of Day and are toggled by `visibleList`.
- Helpers: `obstacle (N)`, `navmesh_*`, `SEmesh_*`, `*col`.
- Mods: 28 Sideloader map zipmods (223 Scene Bundles, 5.5 GB).

## SVS

- Unity 2021.3.33f1, IL2CPP, URP (Volume, Beautify). There is no Studio.
- One island in 7 Scene Bundles, `abdata/map/scene/000_00/00` to `06`. Dependencies per the `sv_abdata` manifest: textures in `map/data/t_0N`, SpeedTree in `map/data/ttree_000_00`, and `chara/mt_ramp_000_00`. The scenes also hold Enlighten realtime GI data.
- Indoor rooms (own rooms, love hotel, public toilet, storehouse) are 2D backdrops in `map/prefabs/`. Their H furniture is 3D, in `h/item/mapitem/000_01`.
- Lists: MemoryPack `maplist.bytes` in `map/list/*`, naming each entry's Scene Bundle and its lightmap settings.
- Shaders: 19, mostly URP Lit and SpeedTree8; also Lux URP volumes and Illusion's `lif_*`.
- Lightmaps are outside the scenes: `map/lightmapsettings/000_00/0N` hold four `LightmapSettingsSaveData` sets, one per Time of Day (*to confirm*). Each has BC6H colour lightmaps (4096²), BC7 directional ones, an ARGB4444 shadowmask, reflection cubemaps, and `LightmapIndices` matched to renderers by object name.
- 31 to 86 lights per scene (point, spot, directional, area), about 70 % realtime. Trilight ambient, linear fog, no skybox material.
- Helpers: `CollisionObject*`, `nav_Plane_*`, `fog_box`, `sun_ray_fog`. The `kage` decals are visible fake shadows, not helpers.
- No map mods.
