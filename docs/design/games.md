# The Games' map data

What a survey of the HF Patched installs found (KK HF Patch v4.2, KKS v2.2, SVS v2.0), read with UnityPy 1.25.4. Paths are relative to the game folder. The Phase 1 spike checked KK's items; its evidence is in [kk-spike.md](kk-spike.md). The Phase 7 spike checked KKS's, in [kks-spike.md](kks-spike.md). Items still marked *to confirm* belong to later Games.

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

The Phase 7 spike checked these; its evidence is in [kks-spike.md](kks-spike.md).

- Unity 2019.4.9f1, Mono, built-in pipeline, linear colour space, `m_LightsUseLinearIntensity` false (as KK), `pixelLightCount` 4 at every quality level. The story camera uses Unity's legacy image effects (GlobalFog, AmplifyColor, AmplifyOcclusion, BloomAndFlares, SunShafts, DepthOfField, Vignette), not PostProcessing v2.
- 31 Scene Bundles in `abdata/map/scene/`. Each scene names its dependencies by CAB in its externals: `map/materials/00` (815 MB, 1.7 GB decompressed) for all but `hotelsuite`, which is self-contained, and `map/common/00` for five. Unity's manifest `abdata/abdata` lists more dependencies than the scenes use, and no Studio bundle. A bundle's CAB names can be read from its header alone.
- Studio: 76 bundles (about 5 GB) in `abdata/studio/map/`: 42 KK Maps rebuilt for 2019.4, which keep their KK lightmaps and KK's three `SunLightInfo` types (KKS shows them as Morning, Day and Evening), and 31 `*_studio` builds of KKS Maps. They depend on `studio/map/materials/00` (1.7 GB, stored uncompressed), `studio/map/common/00` and, for the KK ports, `studio/map/00/tex`.
- Lists: `map/list/mapinfo/*` (adds `DisplayName`, `isSky`, and a thumbnail ID per Time of Day into `map/list/mapthumbnailinfo/*`, which names a Texture2D by bundle and asset); six entries name no Scene Bundle. `studio/info/*`'s `Map_*` rows are `[No, category, name, bundle, asset, …]`.
- Shaders: mostly `Nature/SpeedTree` (11,478 material slots in 19 Maps) and `Standard`; Illusion's `Koikano/main_item_map` (371 in 15 Maps), `sub_texture_cutout`, `sub_texture_subblendcutout`, `main_clothes_item`, `sub_add_cullfront`, and one `Shader Forge/main_item`; Lux Water, NatureManufacture River, ProBuilder, `FX/MirrorReflection`, and the mini-map's `Custom/MiniMapRoad`.
- 79 renderers in 10 Maps, all `p_ks_r01_*` and `o_ks_r01_*` pieces, are statically batched into one `Combined Mesh (root: scene)` per Map, in world space; `m_StaticBatchInfo` gives each one's submesh range. The original mesh isn't in the Map, only sometimes in another Map, where its UV0 and indices match exactly and its positions to within 6e-6 m.
- Vegetation is SpeedTree (`toon_*`): LODGroups of LOD0 to LOD2 plus a billboard, or of one level. Its meshes carry colours and UV0 to UV3; each `Tree` names a readable `SpeedTreeWindAsset`.
- No lightmaps and no light probes in the story Maps. 2 to 31 lights per Map: realtime and mixed (a mixed light without a lightmap lights in realtime), with layer culling masks (water-only lights on layer 4, most renderers on layer 11) and pixel or vertex render modes. Reflection probes; trilight (outdoors) or flat (indoors) ambient.
- Times of Day: four, `SunLightInfo.Info.Type` Morning, DayTime, Evening, Night (0 to 3). Six Maps have fewer infos; the story game then shows the first info, and Studio offers only those present. `Set` hides every info's `visibleList` and shows the chosen one's, and sets the sun, the trilight ambient colours, linear fog with GlobalFog's switches and height, the sun shafts, a possibly blended AmplifyColor LUT (37 of 107 infos blend two), ambient occlusion, bloom, depth of field and vignette. Some objects exist once per Time of Day and are toggled by `visibleList`.
- Sky: in 22 Maps `MapSkyInfo` gives each Time of Day a Funly SkyStudio `SkyProfile`, whose every property is a single keyframe (a constant), drawn with `Funly/Sky Studio/Skybox/3D Standard`. Its sun and moon lights reach only the water layer. The other Maps use Unity's skyboxes.
- `VisibleChange` runs only at H and esthetic points, not when a Map loads. `MapVisibleState` (seacretbeach) switches objects by the weekday.
- Room containers: one renderer-less `p_ks_` or `o_ks_` node directly under the `Map` root in 30 of the 31 Maps (`o_ks_m00hotel00_00`, `p_ks_r01`). Names: `p_ks_`/`o_ks_` with `m<NN>` for a Map's own pieces and `r<NN>` for sets shared between interiors.
- Helpers: `obstacle (N)`, `navmesh_*`, `SEmesh_*`, `*col` (1,381 renderer-less `ks_` nodes are colliders named `…col`).
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
