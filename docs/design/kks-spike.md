# The KKS spike

What the Phase 7 spike found about KKS's map data, with the evidence for each answer, before the Extractor changes. It corrects the KKS section of [games.md](games.md) and says what bears on the contract and the decisions. Terms are in [CONTEXT.md](../../CONTEXT.md). As in Phase 1 ([kk-spike.md](kk-spike.md)), the scripts were read-only, ran on UnityPy 1.25.4 (`../kkbp/importer/.venv/bin/python -I`) under the memory watchdog (`jobs/memory.py`), and aren't kept.

Read: every story Scene Bundle in `abdata/map/scene/` (31), with `map/materials/00` and `map/common/00`; the Studio bundles `studio/map/1f`, `hoteloutside_studio`, `minsyukulobby_studio`, `aquariuminside_studio` and `studio/map/common/00`; the map lists `map/list/mapinfo/*` and `studio/info/*`; Unity's bundle manifest `abdata/abdata`; `KoikatsuSunshine_Data/globalgamemanagers` and `CharaStudio_Data/globalgamemanagers`; and `KoikatsuSunshine_Data/Managed/Assembly-CSharp.dll` decompiled with `ilspycmd` (`SunLightInfo`, `MapSkyInfo`, `ActionMap`, `Studio.Map`, `VisibleChange`, `MapVisibleState`, `MapInfo`, `MapThumbnailInfo`, `CameraEffector`, Funly SkyStudio's `TimeOfDayController`, `SkyProfile`, `OrbitingBody`).

Golden Maps proposed for KKS: **hoteloutside** (outdoor: SpeedTree, a SkyStudio sky, four Times of Day, point and spot lights, two reflection probes, two batched renderers, Koikano and water shaders), **minsyukulobby** (interior: nine batched renderers, flat ambient, a custom reflection, mixed point, spot and directional lights) and **aquariuminside** (one Time of Day, the most batching, blended Grade, no SkyStudio sky).

## Summary

| Question | Answer |
|---|---|
| Times of Day | Four: `Morning`, `DayTime`, `Evening`, `Night`, numbered 0 to 3 in `SunLightInfo.Info.Type` (KK's 0 is day). |
| A missing Time of Day | The story game falls back to the Map's first info; Studio offers only the Times of Day a Map has. Six Maps have fewer than four infos. |
| What `SunLightInfo.Set` changes | Everything KK's does, plus the trilight ambient colours, fog density, the camera's GlobalFog switches and height, all sun shaft settings, a blended AmplifyColor LUT, AmplifyOcclusion, bloom, depth of field and vignette. All infos are hidden before the chosen one is shown, so the order of infos no longer matters. |
| Load-time scripts | `VisibleChange` runs only at H and esthetic points, not when a Map loads. `MapSkyInfo.Change` swaps the SkyStudio profile per Time of Day. |
| Grade | AmplifyColor, as in KK, but 37 of 107 infos blend two LUTs (`aceBlendAmount` 0.1 to 0.66). The camera's PostProcessing v2 isn't used by the story camera's `CameraEffector`. |
| Sky | 22 Maps have a Funly SkyStudio sky. Every profile holds one keyframe per property, so the controller's fixed sky time (0.22, never advancing) doesn't matter. Its own sun and moon lights reach only the water layer. |
| Lights | No lightmaps and no light probes in any story Map. 2 to 31 lights per Map: realtime and mixed, with layer culling masks, and pixel or vertex render modes. At most 4 pixel lights per object. |
| Shared dependencies | Each story Map points into `map/materials/00` (815 MB, 1.7 GB decompressed), some into `map/common/00`. Studio's Maps point into `studio/map/materials/00` (1.7 GB, stored uncompressed), `studio/map/common/00` and, for the KK ports, `studio/map/00/tex`. A CAB name is mapped to its bundle from the bundle headers alone. |
| Memory | Loading a Map with `map/materials/00` peaks at 3.1 to 3.6 GB in UnityPy, which decompresses the whole bundle into one buffer. |
| Static batching | 79 renderers in 10 Maps. The original mesh isn't in the Map; moved back to local space, copies of one piece differ by up to 1.2e-5 m, so exact hashes split them. Where an unbatched copy exists, its UV0 and indices match exactly and its positions within 6e-6 m. |
| SpeedTree | 11,478 material slots in 19 Maps. LODGroups of 4 levels (LOD0 to LOD2 and a billboard) or 1. Meshes carry colours and UV0 to UV3. Wind is a readable `SpeedTreeWindAsset`. |
| Room containers | A renderer-less `p_ks_` or `o_ks_` node directly under the `Map` root. KK's name pattern doesn't fit: `p_ks_r01` is hotellobby's whole room and `p_ks_r01_table00` a Prop. |

## 1. Times of Day

**The four types.** `SunLightInfo.Info.Type` is `Morning, DayTime, Evening, Night` (0 to 3). The story game maps its calendar to them in `ActionMap.CycleToType`: `WakeUp` and `Morning` to Morning, `Daytime` to DayTime, `Evening` to Evening, `Night`, `GotoMyHouse` and `MyHouse` to Night. The map list confirms the set: each entry has `ThumbnailMorningID`, `ThumbnailDayTimeID`, `ThumbnailEveningID` and `ThumbnailNightID`.

**Maps with fewer infos.** fittingroom, hotelkouisitu, aquariuminside, showerroomnozoki and toiletnozoki have only type 0 (Morning); seacretbeach has 0 and 3. The other 25 have all four.

- The story game (`ActionMap.SetCycleToSunLight`) calls `Set(type)`, and when that returns false (no info of that type) `Set(null)`, which takes the first info. So at a missing Time of Day it shows the first one. `MapSkyInfo.Change` is still called with the requested type (an index into its own list, skipped when out of range).
- Studio (`Studio.Map.Reserve`) offers only the types the Map has (`IsTimeZone`), and starts at the first one present.

So the Extractor's stop on a missing info (ADR 0015, "Consequences") is wrong for KKS: the story game's rule gives each missing Time of Day the first info's light, and ADR 0009 then merges them into one Map Variant.

**Studio's KK ports** keep KK's three infos, typed 0, 1 and 2 (`studio/map/1f`). In KKS's enum those are Morning, DayTime and Evening, which is what KKS's Studio shows: KK's night light appears as Evening.

## 2. What `SunLightInfo.Set` does in KKS

Decompiled, `Set(type, camera)` hides every info's `visibleList`, shows the chosen one's, and then sets:

- the sun light (`_targetLight`): colour, intensity, world `eulerAngles`, as in KK;
- `RenderSettings.ambientSkyColor`, `ambientEquatorColor`, `ambientGroundColor` (KK left the ambient alone);
- fog: on or off, always linear, colour, start, end, density; and on the camera's `GlobalFog`: `distanceFog`, `heightFog`, `height`, `startDistance`;
- the camera's `SunShafts`: transform, colour, threshold colour, max radius, blur radius and iterations, intensity;
- the camera's `AmplifyColorEffect`: `LutTexture`, `LutBlendTexture`, `BlendAmount`;
- the camera's `AmplifyOcclusionEffect` (tint, radius, power, bias), `BloomAndFlares` (intensity, threshold, blur spread), `DepthOfField` (focal transform, size, aperture) and `VignetteAndChromaticAberration`;
- the 2D background texture (none in the 3D Maps).

Hiding every list first and then showing the chosen one makes the order of infos irrelevant, unlike KK's `Set`, where an object in two lists depended on the order (ADR 0015). The story game then calls `UpdateCameraFog`, which switches the camera's GlobalFog with `RenderSettings.fog`, as in KK.

Over all 107 infos of the 31 Maps:

| What | Found |
|---|---|
| Grade | `Lut_Amount` alone 59 ×, `Lut_TimeSunset1` alone 8 ×, `Lut_TimeNight1` alone 3 ×; blended with a second LUT (`Lut_Normal`, `Lut_Amount`, `Lut_Live`, `Lut_TimeNight1`, `Lut_Illust`) at 0.1 to 0.66 in 37 infos. One info uses `Lut_TimeNoon1`. |
| GlobalFog | height fog on in 6 infos (height 2 m), distance fog never; 2 infos set a height of 8 m with both off. |
| Sun shafts | a shaft caster in 54 infos. |
| Bloom and ambient occlusion | non-zero in every info. |
| Fog | on in 104 infos. |

hoteloutside's night, for example, is `Lut_TimeNight1` blended 0.5 with `Lut_Amount`; aquariuminside's only info is `Lut_Amount` blended 0.3 with `Lut_TimeNight1`. Today the Extractor stops on any blended LUT.

**The camera.** The story camera's `CameraEffector` holds GlobalFog, AmplifyColor, AmplifyOcclusion, BloomAndFlares, SunShafts, Vignette, DepthOfField, Blur, CrossFade and SepiaTone: Unity's legacy image effects, not PostProcessing v2. `Unity.Postprocessing.Runtime.dll` ships, but no class in `Assembly-CSharp` uses a `PostProcessLayer` or `PostProcessVolume`, and only forest holds a `PostProcessProfile`. Whether the cameras' enabled flags, tonemapper and exposure match KK's is for the capture plugin (ADR 0010).

## 3. Load-time visibility

- **`VisibleChange`** in KKS holds lists of names, found with `FindLoop`, and has no `Start`: `Change` is called only by `HSceneProc` and `EstheticProc` when a scene at an H or esthetic point begins, and `Restore` afterwards. It doesn't run when a Map loads, so the Extractor must not replay it for KKS (it does for KK, ADR 0015). Four Maps have one.
- **`MapSkyInfo`** is on the `Map` root of 22 Maps: per Time of Day a `SkyProfile`, and `_actives` and `_inactives` lists. In the three Golden Maps' profiles both lists are empty. Day often reuses the morning profile (hoteloutside, minsyukulobby).
- **`MapVisibleState`** (seacretbeach only) switches objects by a state that `ActionMap.SettingMap` sets from the weekday: 1 on Tuesdays and Fridays, 0 otherwise. Studio doesn't call it.
- **`SetRenderQueue_Custom`** (10 Maps, 28 in minsyukulobby's Studio version) is a variant of KK's `SetRenderQueue`, to be read in the Extractor phase.

## 4. Skies: Funly SkyStudio

**The controller.** `TimeOfDayController` on `Map/light/SkySystemController` holds the profile, a sky time and the sun and moon orbits. In all three Golden Maps `m_SkyTime` is 0.22, `automaticTimeIncrement` is off and `updateGlobalIllumination` is off. Each frame it puts the profile's skybox material on `RenderSettings.skybox`, sets the profile's values on it (`SkyMaterialController`) and turns its shader keywords on or off by the profile's features.

**The profiles.** A `SkyProfile` (a MonoBehaviour asset in `map/materials/00`) holds keyframe groups: 23 colours, 119 numbers, 18 textures, 2 sphere points (sun and moon position) and 1 boolean, plus a feature switch list. **Every group in every profile read holds a single keyframe**, so each value is a constant and the sky time doesn't change it. hoteloutside's profiles use the gradient sky and noise clouds; its night profile adds the moon and three star layers. Each profile names its own skybox material, all with the shader `Funly/Sky Studio/Skybox/3D Standard`.

**What it lights.** With `SunFeature` on, the controller enables the light under the sun orbit (`OrbitingBody.BodyLight` is the first `Light` below it), aims it from the profile's sun position and sets its colour and intensity from the profile; the moon likewise. In hoteloutside both are `Map/light/SkySystemController/Sun/Light` and `Moon/Light` with culling mask 16, the water layer: **they light only the water**. `FogFeature` is off in every profile read, so `FogSyncWithGlobal` never overrides the Map's fog colour. Neither the ambient light (`SunLightInfo`'s trilight colours) nor the reflection depends on the sky: `updateGlobalIllumination` is off, so nothing renders a skybox reflection at run time, and none was baked: hoteloutside's and aquariuminside's `m_GeneratedSkyboxReflection` is empty. The look check chose what they reflect instead (ADR 0037).

**Without SkyStudio.** Nine Maps have no `MapSkyInfo` (aquariuminside, forest, hotelkouisitu, hotelsuite, seacretbeach, showerroomnozoki, toiletnozoki among them); aquariuminside's skybox is a `Skybox/Cubemap` material, as in KK. hotelsuite holds a `SkyProfile` in its own bundle but no `MapSkyInfo`. In Studio a Map without `MapSkyInfo` is drawn over the camera's background colour (`CameraClearFlags.Color`) unless the Studio scene's own sky is on; the story game's list sets `isSky` for every Map.

## 5. Lights

No story Map has lightmaps (`LightmapSettings` is empty) or light probes. The 284 lights of the 31 Maps:

| Light | Count | Note |
|---|---|---|
| Directional, realtime | 159 | 75 with mask 2048 (layer 11): the sun and per-Time-of-Day fill lights, toggled through `visibleList` (hoteloutside has 12, under `Map/light/morning`, `daytime`, `evening`, `night_light`); 43 with mask 16 (layer 4), water-only lights, SkyStudio's sun and moon among them; 18 with mask 0, lighting nothing |
| Directional, mixed | 11 | minsyukulobby's sun `shadow` among them |
| Point, mixed / realtime | 53 / 12 | 9 points with render mode Not Important, 3 Important |
| Spot, mixed / realtime / baked | 34 / 14 / 1 | 7 spots Important |

- **Layers.** Renderers are on layer 11 (10,307 of 10,474), 4 (water, 46), 0, 22, 1, 16 and 2. A light reaches a renderer only if the renderer's layer is in its culling mask. KK has one sun and no such lights; KKS needs both the layer and the mask.
- **Mixed without lightmaps.** A mixed light whose bake produced no lightmap lights in realtime, as Unity does; a baked light without a lightmap adds nothing.
- **Render mode and the pixel light count.** Every quality level in both players has `pixelLightCount` 4. In Unity's forward path each object gets up to that many pixel lights (Important ones first, then the brightest Auto ones); the rest become per-vertex or spherical-harmonics lights, and Not Important lights never get a pixel pass. So a room with more than four point lights lights each object with its four strongest only per pixel.
- **The light convention** is KK's: linear colour space, `m_LightsUseLinearIntensity` false, in both players.
- **Shadows** follow the quality level: the default (`m_CurrentQuality` 4, "Quality") draws them to 200 m with 4 cascades; the game's own setting can pick another level.

## 6. Shared dependency bundles

**Which files.** The scene file's externals name each dependency by its internal CAB name. Unity's manifest `abdata/abdata` lists dependencies per bundle too, but it lists more than the scenes use (`action/mapitem/00`, `map/advpos/...` that no external names) and it has no entry for any Studio bundle. Reading the UnityFS header and its directory alone gives every bundle's CAB names: 351 bundles under `map`, `studio` and `action` in 0.08 s, with no CAB in two bundles.

| CAB | Bundle | Used by |
|---|---|---|
| `CAB-4a5e7d4e…` | `map/materials/00` (815 MB, 6,959 LZ4 blocks, 1.7 GB decompressed) | every story Map but hotelsuite |
| `CAB-54250abf…` | `map/common/00` (5 MB) | hoteloutside, the three public toilets, showerroom |
| `CAB-f55a0ea3…` | `studio/map/materials/00` (1.7 GB, uncompressed) | the `*_studio` Maps |
| `CAB-5ed09ab4…` | `studio/map/common/00` (16 MB) | |
| `CAB-24a2cb56…` | `studio/map/00/tex` | Studio's KK ports (`1f`) |

**Memory.** UnityPy joins every decompressed block of a bundle into one buffer before reading it, so a story Map with `map/materials/00` peaks at 3.1 to 3.6 GB (hoteloutside 3.53, minsyukulobby 3.33 to 3.54, aquariuminside 3.07 to 3.63), over `golden.py`'s 3 GB limit. The Studio one is read whole as well (1.6 GB for the file alone). Most of what a Map needs from the shared bundle is a small part of it: its materials, shaders, textures and SkyStudio profiles.

**Freshness.** `extract.is_fresh` hashes every source of a Map; with the shared bundle among them that is 815 MB (or 1.7 GB) per Map per check.

## 7. Static batching

79 renderers in 10 Maps carry `m_StaticBatchInfo` and draw `Combined Mesh (root: scene)` (in the scene file), a submesh range per renderer, with the vertices in world space. All are `p_ks_r01_*` and `o_ks_r01_*` pieces (pens, partitions, registers, planters, tableware), drawn with `Standard`.

- **No original in the Map.** In minsyukulobby and aquariuminside no mesh with a batched piece's vertex count matches it: the original was replaced at build time.
- **Moving back isn't exact.** Moving a piece back by the inverse of its renderer's world matrix gives local positions, but in float32 aquariuminside's 12 copies of `p_ks_r01_partion00_00` come out as 10 different byte patterns, up to 1.17e-5 m apart, and rounding to 1e-4 doesn't merge them. Exact Content Hashes (ADR 0012) would make each copy a Candidate of its own.
- **Unbatched copies exist elsewhere.** hotellobby, hoteloutside and hukuya draw the same pieces unbatched. In hotellobby, where both occur, each batched piece matches an unbatched mesh with the same vertex count, identical UV0, identical indices and positions within 3.7e-6 to 5.9e-6 m.

So a batched piece can be recognised by its exact topology and UV0, and placed by its positions within a few micrometres, but its original is often only in another Map.

## 8. SpeedTree, levels of detail and wind

- `Nature/SpeedTree` draws 11,478 material slots in 19 Maps (hoteloutside 1,118), with `EFFECT_BUMP`, `EFFECT_HUE_VARIATION` and `GEOM_TYPE_LEAF`, `FROND`, `BRANCH`, `BRANCH_DETAIL` keywords. Their objects are named `toon_*` (930 in hoteloutside), with no Candidate prefix.
- `LODGroup`s have 4 levels (hoteloutside's `toon_tree00_00_LOD0` to `LOD2` and `_Billboard`, at screen heights 0.257, 0.136, 0.064 and 0.01) or 1 level (75 in hoteloutside, 17 in aquariuminside).
- SpeedTree meshes carry normals, tangents, colours and UV0 to UV3 (39 of 177 meshes in hoteloutside); a few other meshes carry colours.
- Each `Tree` component points to a `SpeedTreeWindAsset`, which UnityPy reads: strength and direction response, anchor offsets, oscillation tables and branch settings. hoteloutside has no `WindZone`; aquariuminside has one.

## 9. Shaders

Over every enabled renderer's material slots in the 31 Maps:

| Shader | Slots | Maps |
|---|---|---|
| `Nature/SpeedTree` | 11,478 | 19 |
| `Standard` | 4,234 | 31 |
| `Koikano/main_item_map` | 371 | 15 (hoteloutside 26, aquariuminside 9) |
| `Custom/MiniMapRoad` | 38 | 12 |
| `Koikano/sub_texture_cutout`, `sub_texture_subblendcutout` | 39 | 4 (the toilets, showerroom) |
| `Lux Water/WaterSurface` (and `Tessellation`) | 31 | 10 |
| `ProBuilder/Standard Vertex Color` | 12 | 12 |
| `NatureManufacture Shaders/Water/*` | 12 | 5 |
| `Koikano/main_clothes_item`, `main_clothes_item_glasses` | 10 | 1 (gassyukulobby) |
| `FX/MirrorReflection` (and `_Transparent`) | 8 | 8 |
| `Shader Forge/main_item` | 3 | 1 (gassyukuoutside) |
| `Koikano/sub_add_cullfront` | 3 | 1 (lighthouse) |
| `Legacy Shaders/Particles/VertexLit Blended` | 2 | 1 |

Two material slots in all 31 Maps point at nothing. `Custom/MiniMapRoad` is the mini-map's road overlay, which the player's camera never sees.

## 10. Names, lists and thumbnails

- **Prefixes.** `p_ks_…` and `o_ks_…`, with `m<NN>` for a Map's own pieces and `r<NN>` for a set shared by interiors (`p_ks_r01_*` is in nine Maps). `toon_*` is SpeedTree; area names (`HotelOut_`, `MinsyukuLo_`, `Aquarium_`) are unprefixed pieces.
- **Room containers.** Under the `Map` root of 30 Maps is one renderer-less `p_ks_` or `o_ks_` node that holds the room or the whole outdoor area: hoteloutside's `o_ks_m00hotel00_00` (187 renderers), hotellobby's `p_ks_r01` (164), lighthouse's `o_ks_m06_LightHouse00_00` (604), seacretbeach's `p_ks_m09_beachS00_00` (613). omiyageya has none. Deeper renderer-less `ks_` nodes are almost all `*col` colliders (1,381 such nodes, most named `…col`) or multi-part pieces (`p_ks_r<NN>_cloth<NN>`). KK's pattern `^(p_|o_|mo_)(o_)?koi_(stu_)?map` matches none of them, and no name pattern separates `p_ks_r01` from the Prop `p_ks_r01_table00`; their place under the root does.
- **Large Structures.** Some pieces with a renderer of their own hold hundreds of others: seacretbeach's sand `o_ks_m09_suna02_00` has 332 renderers below it, many of them SpeedTree trees. With KK's rules each would become one Structure.
- **Story list.** `map/list/mapinfo/00` and `70` (`DisplayName`, `isSky`, `isOutdoors`, `ThumbnailMorningID` to `ThumbnailNightID`, …). Six entries name no Scene Bundle (the restaurant, the shops and the activity corners).
- **Thumbnails.** A thumbnail ID is an entry of `map/list/mapthumbnailinfo/*` (`MapThumbnailInfo`: `ID`, `Bundle`, `Asset`), a Texture2D, not a sprite as in KK.
- **Studio list.** `studio/info/*`'s `Map_*` rows are `[No, category, name, bundle, asset, …]` (KK's are `[No, name, bundle, …]`): 42 KK ports in category 0 and 31 `*_studio` Maps in category 1.
- **Studio versions.** The `*_studio` bundles are separate builds: hoteloutside_studio has 865 renderers against the story's 868, minsyukulobby_studio 166 against 183. Whether their geometry hashes differ is for the Extractor; the counts suggest most will (D22).
- **Unity.** 2019.4.9f1, Mono, linear colour space, in both players.

## 11. What contradicts games.md or the decisions

Facts, now corrected in [games.md](games.md):

1. **Four Times of Day**, numbered from Morning; not "through `SunLightInfo` and `MapSkyInfo`" alone: Studio offers only those a Map has.
2. **Dependencies** are named by CAB in each scene's externals; Studio's go into Studio's own shared bundles, which Unity's manifest doesn't list.
3. **Batched renderers** have no unbatched copy in their own Map, contrary to "Unbatched copies keep their own mesh".
4. **Lights** carry culling masks and render modes, and most interior lights are mixed. "Trilight or flat ambient" holds; the trilight colours change with the Time of Day.
5. **The Grade** is AmplifyColor, often blended; PostProcessing v2 isn't the story camera's.
6. **The SkyStudio sky** is a constant per Time of Day; its lights reach only water.

Points that bear on the contract and the decisions, to settle before the Extractor changes:

- **ADR 0015** stops on a missing Time of Day, and replays `VisibleChange` at load; neither holds for KKS (sections 1 and 3).
- **The Time of Day set** needs `morning`.
- **The Grade** needs a second LUT and its blend amount.
- **Lights and renderers** need the culling mask, the layer and the render mode; the pixel light count is Game data.
- **The Sky** needs a SkyStudio kind, from the profile's constant values.
- **Height fog** becomes Map Variant data where `SunLightInfo` sets it (6 infos), beside ADR 0028's camera height fog.
- **Batched meshes** need either a tolerance (ADR 0012 hashes exactly) or a Builder step that recognises them across Maps (section 7).
- **Mesh attributes** need colours and UV2 and UV3 for SpeedTree; a renderer needs its wind.
- **Room containers** need a structural rule for KKS (section 10).
- **Memory**: reading the shared bundle whole costs 3.6 GB per Map (section 6).

## 12. Settled by the look check

Fitted on the KKS Golden Maps' Reference Captures (camera "game"), 2026-11-26; mean ΔE before the Grade for aquariuminside, hoteloutside and minsyukulobby, from 10.5, 10.7 and 5.2 at the first build:

- **Point and spot lights** agree with Unity's falloff at 0.6 of their range (`games.LIGHTS["KKS"].point_reference`; 0.2 to 0.8 tried). minsyukulobby went from 5.2 at 0.2 to 3.8; past 0.6 nothing changes.
- **An unbaked skybox reflection** reflects the ambient light (ADR 0037): hoteloutside 8.9 with the sky, 7.2 with the ambient.
- **Lux Water's opacity** is 1 − exp(−_Density · 5 m) (`materials.WATER_DEPTH`; 2, 5 and 15 m tried, against the tier's constant 0.6). aquariuminside's tank glass is a Lux surface the camera looks through, and the constant tinted everything behind it: 8.4 to 6.5.
- **The detail normal map** takes `_DetailAlbedoMap`'s tiling, as Unity's Standard samples it.
- **The camera's height fog** has heightDensity 0.5, read from the running camera.

**Realtime probes, measured and set aside.** hoteloutside's two realtime probes (a 120 m box over the whole Map, a 28 m one over the pool area) and aquariuminside's one cover nearly every renderer, so they, not ADR 0037's missing skybox reflection, are what the game reflects. The capture plugin read them from the running game (2026-11-26): each renders once, when the Map wakes (`OnAwake`), and never again, so day and night hold the same map; it renders over the skybox the scene saves (`SkyboxMaterial_night` in hoteloutside, a dull blue gradient), before SkyStudio sets the Time of Day's sky; it is 16 texels a face in hoteloutside, 128 in aquariuminside; and the scene is lit as it is at load, before `SunLightInfo.Set`. Unity's default reflection, outside every probe, is black. Rendering them in the Builder from each Map Variant (a draft Map Bundle 0.14 and ADR 0038, kept as a patch outside the repository) made hoteloutside worse (7.3 to 8.6); with the load-time sky and resolution its sky matched the game's, but not its ground, which needs the load-time lights too. Set aside until the look check shows reflections are what keeps views from passing; the pool, which the game draws as its tiles reflecting the probe (its water objects are switched off), stays approximate.

**The sea, measured.** hoteloutside's sea planes and sand are where the game draws them: the capture plugin read the renderers' bounds in the running game (2026-11-26), the sea at Unity y −5.95 at every Time of Day and the sand from −8.57 to −0.36, as the bundle has them. So where the game shows turquoise sea and the Builder sand, the difference is Lux Water's shading (the scene behind it refracted and tinted by depth, and a sky reflection over it), not the geometry. Two cheap stand-ins didn't pay: the opacity along the view through a 5 m or 2 m layer, and the reflection kept whole over what shows through; neither showed the sea, and both made aquariuminside worse (6.5 to 7.3 and 8.6).

Left as they are: the day sea's turquoise, which comes from the sand seen through Lux's refraction; the underwater haze in aquariuminside's tank.

## Open questions

- The story and Studio cameras' effect settings that no file holds: which effects are enabled, AmplifyColor's tonemapper, exposure and dithering, and the strengths the infos don't set. For the KKS capture plugin (ADR 0010).
- Whether bloom and ambient occlusion, set in every info, change the frame enough to model. For the look check.
- How Funly's `3D Standard` skybox draws its gradient, clouds, sun, moon and stars, read from its shader; and which values `SkyMaterialController` sets.
- Koikano's `main_item_map` model, from its disassembled D3D11 code.
- What the other water shaders and `SetRenderQueue_Custom` need.
