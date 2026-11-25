# The Games' map data

What a survey of the HF Patched installs found (KK HF Patch v4.2, KKS v2.2, SVS v2.0), read with UnityPy 1.25.4. Paths are relative to the game folder. The Phase 1 spike checked KK's items; its evidence is in [kk-spike.md](kk-spike.md). Items still marked *to confirm* belong to later Games.

## Common to all three

- Map bundles are standard UnityFS with LZ4HC compression and no encryption. They carry type trees, so UnityPy reads every component, MonoBehaviours included.
- Every 3D Map is a streamed Scene Bundle: `BuildPlayer-<Scene>` and `BuildPlayer-<Scene>.sharedAssets`, with one `Assets/…/<Scene>.unity` path.
- Object names are ASCII, romanized Japanese, with Unity's ` (N)` duplicate suffixes. Prefixes: `p_` props, `mo_` and `o_` shell geometry, `n_` groups. Within a Scene Bundle, repeated objects share one Mesh (path id). Across Scene Bundles the same mesh has another path id but identical content, so Prop hashes come from mesh content.
- Every Shader object carries a compiled D3D11 blob, so shaders can be disassembled as KKBP's `importer/tools/game_shaders/dump.py` does.
- No crunched textures. Normal maps are DXT5 with the DXT5nm swizzle.
- Helpers to leave out: inactive GameObjects, disabled renderers, renderers with no mesh, collider-only objects. Shadow-only casters (`m_CastShadows 3`) are carried as Shadow Casters (ADR 0024). Unity's built-in meshes are helpers except where a sky dome uses the built-in Sphere (KK). Unity's built-in objects are read from the player's `<Name>_Data/Resources/` files (ADR 0031): warehouse's Shadow Caster draws with `Legacy Shaders/Diffuse` from `unity_builtin_extra`. Layer names aren't in the bundles, only their numbers.
- Map names are Japanese. SVS keeps its lists in MemoryPack binaries; KK and KKS keep them in Excel-style MonoBehaviours.

## KK

- Unity 5.6.2f1, Mono, built-in render pipeline; post effects from AmplifyColor and AmplifyOcclusion.
- 41 Scene Bundles in `abdata/map/scene/` (about 1.1 GB), each self-contained; 2 Studio-only Maps in `abdata/studio/map/`.
- Lists: `abdata/map/list/mapinfo/*` (`MapName`, `No`, `AssetBundleName`, `AssetName`, `isOutdoors`, thumbnails) and Studio's `abdata/studio/info/*` (`Map_*`).
- A single `Map` root with 3 to 18 group nodes, usually 150 to 300 MeshRenderers per Map (park has 75). No static batching, no LODGroups. Every mesh a renderer uses is readable, uncompressed, triangles with 16-bit indices, with normals and tangents and no vertex colours. Some lightmapped meshes have no UV1 and are lit through UV0.
- Linear colour space (`PlayerSettings.m_ActiveColorSpace 1`), HDR.
- Shaders: 22 in all, mostly Unity `Standard`; also `Shader Forge/main_*`, `Custom/StandardDouble`, skyboxes (`Skybox/Procedural`, `6 Sided`, `Cubemap`), particles, `Unlit/Transparent` and `Xffect/heat_distortion`.
- Lightmaps: baked directional lightmaps (`Lightmap-N_comp_light`, `_comp_dir`, up to 2048², RGBA32 or DXT5) in most Maps; `m_LightmapsMode 1`. `_comp_light` is RGBM (`m_LightmapFormat 2`) sampled as sRGB: value = 34.493242 · a^2.2 · srgb_to_linear(rgb). `_comp_dir` holds a Unity world-space direction. Which renderer uses which lightmap: the renderer's own `m_LightmapIndex` and `m_LightmapTilingOffset`, replaced by its `LightmapPrefab` entry where it has one (some Maps, like ground, rely on `LightmapPrefab` alone; park also on the renderers' own values). No lightmaps in backyard, courtyard, rooftop or livestage.
- Some Maps (park, ground) also carry Enlighten realtime GI, which the game solves at run time; park lights 8 renderers with it.
- Lights: one realtime directional sun per Map, plus RenderSettings ambient (skybox SH or flat), fog and a procedural or 6-sided skybox. 1F, park and ground have no light probes, so their unlightmapped renderers get the ambient SH and a baked reflection probe. A renderer whose `m_ReflectionProbeUsage` is 0 (Off) takes the scene's default reflection instead (ADR 0026): three in ground, one in 1F.
- Sky: Maps with a view of the sky, such as 1F and ground, have a sky dome per Time of Day: Unity's built-in Sphere (448 to 613 m radius) with a `Skybox/Cubemap` material, plus cloud or star meshes. The RenderSettings skybox only shows where a Map has no dome.
- Times of Day: day, evening, night, in `SunLightInfo`: sun world rotation, colour and intensity, linear fog, sun shafts, an AmplifyColor LUT, and a `visibleList` of objects to show (the sky domes). Ambient, lightmaps and reflection probes are the same for all three. Some Maps (park) have three identical entries.
- Grade: AmplifyColor LUTs are 1024×32 (32 slices of 32×32, R across a slice, G up from the bottom row, B by slice), applied to the whole frame in sRGB-encoded values. The camera's tonemapper and exposure are not in the map files.
- Helpers: `Cube (N)` collision boxes, and shadow-only casters such as 1F's `*_kage*` and `p_koi_map00_shadow`. Not every `*_kage*` or `*_shadow` is a helper: park's are visible fake-shadow decals.
- Mods: 53 Sideloader map zipmods (305 Scene Bundles, 8.5 GB), laid out like the base game and stored uncompressed.
- Found by the Extractor (Phase 3), over all 43 Maps: every Map has a `SunLightInfo` with all three Times of Day (park one distinct lighting state, train and traincrowded two) and exactly one light, a realtime directional sun. Light probes are empty in the five Maps checked (1F, park, ground, myroom, church), and the Extractor stops on a Map whose probes aren't. The only built-in meshes with a renderer are the Sky Domes; the others (151 in 1F) are collider-only. `VisibleChange` (24 instances) toggles objects in `Start`, and `SetRenderQueue` (4) changes render queues in `Awake`. SpriteRenderers are action-point `Icon`s only. Navigation meshes (`nav_map02_00`, `o_koi_map34_nav`) are renderers with no material.
- Textures, as found in Phase 3: a Texture2D's data is stored bottom row first, but a cubemap's faces are stored top row first in Direct3D's face convention. The reflection probes and park's skybox reflection are BC6H with values above 1 (1F's up to 2.07), which Pillow's decoder clamps. park's 6 Sided skybox faces are 2048² (Front +Z, Back −Z, Left +X, Right −X, Up +Y, Down −Y), upright as stored.
- Name prefixes, as found in Phase 3: `p_` isn't always a Prop. In 33 of the 43 Maps, a `p_koi_map…`, `p_o_koi_map…` or `p_koi_stu_map…` node holds a whole room or shell (park's `p_koi_map71_park`, libraryroom's `p_koi_map21_00` with 231 `p_` Props inside). The Extractor walks into these room containers (ADR 0019). In 2f, libraryroom and lockerroom the game also places plain copies of a `p_` Prop under `MapObjectGroup` without its prefix (`isu00`, `isu0200`, `c00`); they are that Prop's Placements (ADR 0023). akikyoushitu has a reflection probe in baked mode that was never baked, which Unity ignores.

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
