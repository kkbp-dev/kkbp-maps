# The KK spike

What Phase 1 found about KK's map data, with the evidence for each answer. It answers the "to confirm" items in [games.md](games.md) and the Phase 1 row of [roadmap.md](roadmap.md). The script it was made with was read-only, ran on UnityPy 1.25.4 (`../kkbp/importer/.venv/bin/python -I`), and isn't kept.

Maps read: 1F (`abdata/map/scene/1f.unity3d`), park (`park.unity3d`) and ground (`ground.unity3d`). Also read: `Koikatu_Data/globalgamemanagers` and `CharaStudio_Data/globalgamemanagers`, `Koikatu_Data/resources.assets` (AmplifyColor's shader), the map lists in `abdata/map/list/mapinfo/`, and `Koikatu_Data/Managed/Assembly-CSharp.dll` decompiled with `ilspycmd` (`LightmapPrefab`, `SunLightInfo`, `MapVisibleList`). Shaders were disassembled with KKBP's `importer/tools/game_shaders/dump.py`.

## Summary

| Question | Answer |
|---|---|
| Scene graph | One `Map` root per Scene Bundle; walking `Transform.m_Children` from it reaches every Transform (499 of 499 in 1F). |
| Axes | Unity `(x, y, z)` → Blender `(-x, -z, y)`, the same as KKBP's X mirror followed by Blender's glTF Y-up to Z-up. Swap each triangle's last two corners. |
| Meshes | All used meshes are readable, uncompressed, triangles only, 16-bit indices, with normals and tangents and no vertex colours. UV1 is missing on some lightmapped meshes, which then use UV0. |
| Mesh sharing | Within a Scene Bundle, repeated objects share one Mesh path id. Across Scene Bundles the same mesh has a different path id but identical content. |
| Lightmap encoding | `m_LightmapFormat 2` is RGBM. The project is linear. Decoded value = `34.493242 · a^2.2 · srgb_to_linear(rgb)`, range 0 to 34.49. |
| Directional lightmaps | `_comp_dir` holds a direction in Unity world space plus a weight. It has to be converted to Blender axes. |
| Lightmap assignment | The renderer's own `m_LightmapIndex` and `m_LightmapTilingOffset` apply, except where `LightmapPrefab` lists that renderer: then the prefab's entry replaces them at `Start`. ground relies only on the prefab. park also needs the renderers' own values. |
| Times of Day | `SunLightInfo` holds day, evening and night. It sets the sun's colour, intensity and world rotation, linear fog, the sun shafts, the AmplifyColor LUT and which sky dome is shown. Ambient light, lightmaps and reflection probes are the same for all three. |
| Grade | A 1024×32 AmplifyColor LUT: 32 slices of 32×32. It is applied to the whole frame, in sRGB-encoded values. The camera's tonemapper and exposure are not in the map files. |
| RenderSettings | Ambient is Flat (1F) or Skybox SH (park, ground). The fog is overridden by `SunLightInfo`. The skybox material is hidden behind the sky dome where a Map has one. None of the three Maps has light probes. |

## 1. The scene graph and the axes

**Walking.** The scene file (`BuildPlayer-<Scene>`) holds GameObjects, Transforms and components. The `.sharedAssets` file holds meshes, materials, textures and shaders. A reference with `m_FileID 1` points into `.sharedAssets`, `m_FileID 2` into `library/unity default resources` (Unity's built-in meshes), and `m_FileID 0` into the same file. Each Scene Bundle has a single root, `Map`. Its children are 3 to 9 groups in these Maps. A Transform's world matrix is its parent's matrix times `T · R · S` from `m_LocalPosition`, `m_LocalRotation` (a quaternion) and `m_LocalScale`. None of the three Maps has a negative determinant. Twelve renderers (7 in 1F, 5 in ground) have non-uniform world scale. "Active" means the GameObject and every ancestor have `m_IsActive`.

**One conversion.** KKBP converts in `exporters/core/src/UnitySpace.cs`: it negates X (Unity's left-handed, Y-up space to glTF's right-handed, Y-up space), and Blender's glTF importer then turns glTF's Y-up into Z-up. To stay compatible with KKBP Characters (D6), kkbp-maps uses the same two steps folded into one matrix:

```
C = | -1  0  0 |      Blender point     = C · Unity point
    |  0  0 -1 |      Blender direction = C · Unity direction (normals, light directions, directional lightmaps)
    |  0  1  0 |      Blender matrix    = C · Unity matrix · Cᵀ
                      det C = -1, so each triangle (a, b, c) becomes (a, c, b)
```

`C · R · Cᵀ` of any rotation has determinant +1, so rotations stay rotations. Scale is unchanged, metres stay metres, and Blender's UV origin is Unity's (bottom left), so UVs need no change when written through `bpy`. (KKBP flips V only because glTF's origin is the top left, and Blender's glTF importer flips it back.)

*Evidence.* After the conversion and the swap, the right-handed face normal of 96.7 % of triangles (60 meshes of 1F) and 87.8 % (52 of park) points the same way as their vertex normals. Without the swap it is 3.3 % and 12.2 %. The rest are double-sided or flipped geometry such as foliage cards. As a check of the light conversion, the 1F day sun comes out as Unity direction `(0.548, -0.394, 0.738)`, Blender `(-0.548, -0.738, -0.394)`, 23.2° above the horizon.

**Lights.** A Unity light shines along its local +Z and a Blender light along its local -Z. So a sun's Blender direction is `C · (R · (0, 0, 1))`. `SunLightInfo.angle` is a world `eulerAngles`, which Unity applies Z first, then X, then Y (`R = Ry · Rx · Rz`).

## 2. Meshes

Read with `UnityPy.helpers.MeshHelper.MeshHandler`, which gives `m_Vertices`, `m_Normals`, `m_Tangents`, `m_UV0`, `m_UV1`, `m_IndexBuffer` and the submeshes. In all three Maps, every mesh a renderer uses has these properties:

- `m_IsReadable` true, `m_MeshCompression 0`, every submesh with topology 0 (triangles), 16-bit indices.
- Normals and tangents present, no vertex colours.
- UV1, the lightmap UVs, is present on most meshes but not all: 314 of 322 used meshes in 1F, 120 of 129 in ground, but only 13 of 75 in park. A lightmapped mesh without UV1 is lit through UV0, as in Unity. All six lightmapped renderers in park are like this.
- Submeshes and material slots usually match one to one. There are exceptions: 1F has one renderer with more submeshes than materials, so its last submesh isn't drawn. ground has 3 like that and one with more materials than submeshes, where the extra material draws the last submesh again.
- No static batching (`m_StaticBatchInfo` is empty) and no LODGroups.

**Sharing.** Within a Scene Bundle, repeated objects share one Mesh path id. 1F has 38 meshes used by more than one renderer, such as `p_o_koi_nisu00` (×6) and `hana_*` (×4). ground has 5. In park nothing repeats. Across Scene Bundles, path ids differ, but the content is identical: `mo_koi_mi_kadan01_00` is path id 465 in 1F and 386 in ground, with the same vertices, indices and UV0 (SHA-1 `b27ef0c708…`), and the sky cloud meshes match the same way. **So a Prop's hash (D3) has to be computed from mesh content, never from path ids.**

**Not usable.** Two ground renderers have no mesh (`m_Mesh` is null). park's `.sharedAssets` holds 8 unreadable meshes named `<hash>(Clone)` with no vertex channels, which no MeshFilter or MeshCollider uses.

**Built-in meshes.** Three renderers in 1F and three in ground use `library/unity default resources` path id 10207, Unity's built-in Sphere. They are the sky domes (section 5), not helpers.

## 3. The lightmap encoding and the colour space

**Colour space: linear.** `PlayerSettings.m_ActiveColorSpace = 1` (Linear) in both `Koikatu_Data` and `CharaStudio_Data`. `GraphicsSettings` tier 1 has `useHDR` true.

**Encoding: RGBM.** The `Lightmap-N_comp_light` textures have `m_LightmapFormat 2`, Unity's `LightmapRGBM` usage. dLDR (`m_LightmapFormat 1`) does not occur. Their `m_ColorSpace` is 1, so the GPU decodes RGB from sRGB when sampling. Alpha is never sRGB-decoded. They are RGBA32 in 1F (uncompressed, 2048² ×3 and 512²) and DXT5 in park (512²) and ground (1024²). Each has a `Lightmap-N_comp_dir` beside it: `m_LightmapFormat 0`, `m_ColorSpace 0` (linear), same size and format. park also has `Lightmap-N_comp_shadowmask` (ARGB4444). Nothing uses them, because every light is realtime.

The decode, from the game's own Standard shader (`LIGHTMAP_ON DIRLIGHTMAP_COMBINED`, sub-program 1931 of 1F's Standard):

```
lm  = sample(unity_Lightmap, uv1)                     ; sRGB-decoded RGB, linear A
lm  = unity_Lightmap_HDR.r · lm.a ^ unity_Lightmap_HDR.g · lm.rgb
d   = sample(unity_LightmapInd, uv1)                  ; linear
lm *= (dot(N_world, d.xyz - 0.5) + 0.5) / max(d.w, 1e-4)
```

The engine sets `unity_Lightmap_HDR` at run time, so its values are not in the files. In a linear project with RGBM they are `(34.493242, 2.2)`, that is 5^2.2 and 2.2. The full decode is:

```
value = 34.493242 · a^2.2 · srgb_to_linear(rgb)          range 0 … 34.49
```

`N_world` is the normal in Unity world space. The Builder therefore compares Blender's world normal converted back with `Cᵀ`, or the Extractor converts `d.xyz - 0.5` with `C` and re-encodes it.

**Value range.** Decoded to float EXR (written in the scratchpad only):

| Lightmap | Size | Alpha range | Max | 99th pct | Mean | Texels > 1.0 |
|---|---|---|---|---|---|---|
| 1F 0 | 2048² | 0.027 – 0.278 | 2.03 | 0.82 | 0.165 | 0.47 % |
| 1F 1 | 2048² | 0.027 – 0.271 | 1.93 | 0.88 | 0.187 | 0.27 % |
| ground 0 | 1024² | 0.020 – 0.192 | 0.92 | 0.74 | 0.220 | 0 |
| ground 1 | 1024² | 0.024 – 0.192 | 0.92 | 0.72 | 0.095 | 0 |
| park 0 | 512² | 0.020 – 0.663 | 13.95 | 2.74 | 0.106 | 4.6 % (street lamps) |
| park 1 | 512² | 0.027 (constant) | 0.007 | 0.004 | 0.001 | 0 |

No texel reaches alpha 1. Most values are below 1, but street lamps reach 14, so the files need to be HDR (EXR, as D21 says). The decoded EXR opens in Blender 5.2.2 as a float image with the same range.

**Orientation.** UnityPy's `Texture2D.image` is already flipped to top-down. Written as it comes, a lightmap lines up with the UV1 charts in Blender's convention. Checked by sampling each lightmapped triangle's centre: as written, 1.8 % (1F) and 0.85 % (ground) of centres land on black background texels; flipped again, 55 % and 42 % do.

**To confirm in the look check (Phase 5).** The sRGB sampling of the RGB channels. It follows from `m_ColorSpace 1`, and without it the decode would leave out `srgb_to_linear`.

## 4. Lightmap assignment

`LightmapPrefab` (decompiled) holds `lightmapParameters[]`, entries of `{lightmapIndex, scaleOffset, renderer}`. In `Start` it sets `renderer.lightmapScaleOffset` and `renderer.lightmapIndex` from each entry whose renderer isn't null and whose index is 0 or more. Renderers it doesn't list keep the values serialized on them. Its editor-only `Setup` filled the list from every enabled child renderer with a lightmap at the time it was run. So the effective assignment is:

```
effective(renderer) = LightmapPrefab entry for renderer   if listed
                      (m_LightmapIndex, m_LightmapTilingOffset)   otherwise
index ≥ 65534 means no lightmap; lightmap UV = uv · scaleOffset.xy + scaleOffset.zw
```

| Map | Prefab entries | Agree with the renderer's own values | Lightmapped renderers not listed |
|---|---|---|---|
| 1F | 68 | 68 | 0 |
| ground | 18 | 0: every renderer's own index is 65535 | 0 |
| park | 3 | 0: own values are from another bake | 5 street lamps (`o_kouen_gaitou_00`–`04`), index 0 |

So ground confirms that the renderer's own `m_LightmapIndex` alone is wrong. park shows that `LightmapPrefab` alone is also wrong: its street lamps are lit only through their own values. With the rule above, no two renderers' lightmap UV bounding boxes overlap on any lightmap in the three Maps. park's `o_kouen_road_01` lands on lightmap 1, which is almost black everywhere (max 0.007), and its UV0 runs outside 0…1, which lightmaps clamp.

**Realtime GI.** park and ground also hold Enlighten realtime GI (`m_EnableRealtimeLightmaps` true, `GI/BuildPlayer-<Scene>/…` files). In park, 8 renderers have `m_LightmapIndexDynamic 0`: their sun bounce is solved at run time, so it can't be read from the files. In ground, all 18 Enlighten entries point at null renderers, so nothing uses it. ground's Standard shader has 2864 `DYNAMICLIGHTMAP_ON` variants; 1F's has none.

## 5. Times of Day: `SunLightInfo`

On the `Map` root: `_targetLight` (the sun), `_bgParam` (null in these Maps; it is for 2D backdrops) and `_infos[]`, one per `type` (0 day, 1 evening, 2 night). `Set(type, camera)` (decompiled) goes through the infos in order, showing the chosen one's `visibleList` objects and hiding the others' (corrected in Phase 3; an object in two lists is hidden whenever the later list isn't chosen). Then it sets:

- `light.color`, `light.intensity`, and `light.transform.eulerAngles = angle` (world rotation).
- `RenderSettings.fog = fogUse`, mode **always Linear**, `fogColor`, `fogStart`, `fogEnd`.
- the camera's `SunShafts`: `sunColor` and `sunTransform` (a child `sun` of the sun light; null at night).
- the camera's `AmplifyColorEffect`: `LutTexture`, `LutBlendTexture` (null in all three), `BlendAmount` (0).
- the 2D background texture (none here).

It changes nothing else: **ambient, lightmaps and the reflection probe are the same at every Time of Day.** The sun is realtime (`m_Lightmapping 4`), so its direct light is never in the lightmaps.

| Map | Type | Shows | Euler (x, y, z) | Colour | Int. | Fog | Shafts | LUT |
|---|---|---|---|---|---|---|---|---|
| 1F | day | `mo_koi_sky_hiru00` | 23.2, 36.6, 213.3 | 0.895 0.956 0.893 | 1.45 | 0.294 0.883 1.0, 0–500 | 0.838 grey | `Lut_Amount` |
| 1F | evening | `mo_koi_sky_yu00` | 24.4, 341.1, 212.8 | 1.0 0.75 0.375 | 1.97 | 0.919 0.603 0.203, 0–500 | 1.0 0.434 0 | `Lut_TimeSunset1` |
| 1F | night | `mo_koi_sky_yo00` | 57.1, 0, 0 | 0.380 0.564 0.654 | 1.00 | 0.231 0.196 0.338, 0–500 | none | `Lut_TimeNight1` |
| ground | day | `mo_koi_sky_hiru00` | as 1F | as 1F | 1.45 | 0.526 0.727 0.794, 0–800 | 0.063 0.121 0.132 | `Lut_Amount` |
| ground | evening | `mo_koi_sky_yu00` | as 1F | as 1F | 1.20 | as 1F, 0–800 | as 1F | `Lut_TimeSunset1` |
| ground | night | `mo_koi_sky_yo00` | 40.0, 9.1, 28.7 | as 1F | 1.00 | as 1F, 0–800 | none | `Lut_TimeNight1` |
| park | all three | nothing | 50, -70, 0 | 0.877 0.985 0.954 | 0.70 | off | none | `Lut_TimeNight1` |

**park's three infos are identical**: it is a night Map whatever Time of Day is chosen. Its map list entry (`mapinfo/20`, No 65) has no Time of Day field, and it has one thumbnail.

**Sky domes.** The objects `visibleList` toggles are sky domes. Each is Unity's built-in Sphere, scaled to a radius of 448 to 613 m around the Map and drawn with a `Skybox/Cubemap` material: `mt_koi_sky_hiru00` and `mt_koi_sky_yu00` are BC7 1024² cubemaps, `mt_koi_sky_yo00` is DXT1. The materials have `_Tint` 0.669, 0.478 and 0.5, `_Exposure` 1, and `_Rotation` 0, 291 and 0. They neither cast nor receive shadows. Under each dome are cloud planes (`mo_koi_sky_kumo*`) or, at night, a star field (`o_koi_sky_hoshi_00`). These are transparent `Standard` materials (queue 3000) whose `_EmissionMap` is their `_MainTex`. A Map with no dome (park) shows its RenderSettings skybox instead.

**The AmplifyColor LUT.** `Lut_Amount`, `Lut_TimeSunset1` and `Lut_TimeNight1` are 1024×32 RGB24 textures, `m_ColorSpace 0` (linear, no sRGB decode), bilinear, one mip. Layout, in Unity's convention (row 0 at the bottom):

```
input (r, g, b) in 0…1, N = 32
x = r · 31 + 32 · slice,  y = g · 31,  slice = b · 31 (two slices blended)
```

Checked two ways. The corners map to themselves in `Lut_Amount` (black, white, red). The layout fits the identity better than the vertically flipped one: mean error 0.116 against 0.270. None of the three LUTs is neutral, the day one included: mid grey 0.5 becomes `(0.416, 0.337, 0.388)` by day, `(0.361, 0.271, 0.271)` in the evening and `(0.161, 0.251, 0.455)` at night.

AmplifyColor's `Hidden/Amplify Color/Base` (in `Koikatu_Data/resources.assets`, 36 programs) shows how the LUT is applied in a linear project. It runs on the whole frame, sky and fog included. The steps are an optional `_Exposure` multiply, an optional tonemapper (Photographic, or the fitted ACES curve `x(2.51x + 0.03) / (x(2.43x + 0.59) + 0.14)`), an sRGB encode (`1.055·x^(1/2.4) − 0.055`), the LUT, and an sRGB decode (`x·(0.3053x + 0.6822) + 0.0125`). The tonemapper, the exposure and the dithering are settings on the game camera's `AmplifyColorEffect`, not in the map files. They are the same for every Map.

## 6. RenderSettings

| | 1F | park | ground |
|---|---|---|---|
| Ambient mode | 3 Flat: sky colour `(0.212, 0.227, 0.259)` × 1.0 | 0 Skybox: SH probe | 0 Skybox: SH probe |
| SH probe L0 (r, g, b) | 0.183 0.227 0.295 (stale, see below) | 0.127 0.134 0.121 | 0.183 0.227 0.295 |
| Fog (until `SunLightInfo` sets it) | Linear, 0–500, on | Exp², off | Linear, 0–800, on |
| Skybox material | `Default-Skybox`, `Skybox/Procedural` (exposure 1.3, sun size 0.04), hidden behind the domes | `SkyMat_Night_1`, `Skybox/6 Sided`, `_Rotation` 282, `_Exposure` 1.09, `_Tint` 0.5 | as 1F |
| Reflection | Custom: the reflection probe's baked BC6H cubemap, intensity 1 | Skybox, intensity 1, with the baked skybox reflection `m_GeneratedSkyboxReflection` (128² BC6H) | Custom with an empty slot (corrected in Phase 3), intensity 0.717 |
| Reflection probe | 1, box 70×10×107 m, baked 256² BC6H | 1, 128² | 1, 200 m box, 256² |
| `m_Sun` | the sun light | none | the sun light |
| GI | baked only | baked + realtime | baked + realtime, `m_IndirectOutputScale 0.5` |

The SH probe is stored as 27 floats, `sh[0..8]` red, `sh[9..17]` green and `sh[18..26]` blue, in Unity's L2 order. **None of the three Maps has light probes** (`LightProbes` is empty), and only 68 of 325 renderers in 1F, 8 of 75 in park and 18 of 134 in ground are lightmapped. So most Props are lit by the realtime sun, this ambient probe and the reflection probe. Lightmapped renderers take their indirect light from the lightmap instead of the probe.

1F's probe matches ground's to the last bit, although 1F's ambient mode is Flat. It looks left over from an earlier Skybox setting. In Flat mode the ambient is the sky colour. To confirm in the look check.

## 7. What contradicts games.md or the decisions

Facts, now corrected in [games.md](games.md):

1. **Built-in meshes aren't always helpers.** The sky domes are Unity's built-in Sphere. Leaving out "Unity's built-in meshes" would drop the sky.
2. **`*_kage*` isn't always a helper.** In 1F, `mo_koi_map02_kage*` and `o_koi_map02_kage` are shadow-only (`m_CastShadows 3`). In park, `o_road_kage_00`/`01` and `o_ikegaki_00_shadow` are visible fake-shadow decals (`m_CastShadows 0`), as SVS's `kage` are. The test is `m_CastShadows 3`, not the name.
3. **Lightmap assignment** is the renderer's own values overridden by `LightmapPrefab`, not `LightmapPrefab` alone (section 4).
4. **Mesh sharing** holds within a Scene Bundle only. Across Scene Bundles, Prop hashes must come from content.
5. **KK also has Enlighten realtime GI** (park, ground), not only SVS. It can't be read from the files.
6. **The sky** is a dome per Time of Day, with clouds or stars, toggled by `visibleList`. It isn't the RenderSettings skybox, which only shows where a Map has no dome.
7. **A Time of Day changes** the sun, fog, sun shafts, sky dome and LUT, nothing else. Some Maps (park) have three identical Times of Day.
8. Smaller things: the RenderSettings fog mode isn't always linear (park's is Exp², and off), but `SunLightInfo` always sets linear. park uses an `m00_` name prefix. park's 75 renderers are below the "150 to 300" range. `Xffect/heat_distortion`, `Unlit/Transparent` and `Particles/Alpha Blended` occur too.

Points that bore on decisions, settled with the user after the spike:

- **D9 and ADR 0002, the Grade in materials.** KK's Grade isn't a colour change of the albedo. It is a 3D LUT on the final frame, in sRGB-encoded values, after an optional tonemapper, and the day LUT isn't neutral. Inside a material it can only be applied to the lit result through Shader to RGB, which is EEVEE-only (D4 already makes EEVEE the matched renderer) and leaves sky and fog to be graded separately. Otherwise it has to be approximated. *Settled:* two Material Outputs, graded in EEVEE and ungraded in Cycles ([ADR 0008](../adr/0008-the-grade-is-applied-to-the-lit-result-in-eevee.md)).
- **D8 and ADR 0003, one asset per Map Variant.** park would get three identical assets. *Settled:* identical Times of Day are one Map Variant ([ADR 0009](../adr/0009-identical-times-of-day-are-one-map-variant.md)).
- **D7, the Lighting Rig.** The sky domes and their clouds and stars aren't Props or Structures. They need a place: World background, Map Variant geometry, or both. *Settled:* both. The cubemap becomes the World, and the clouds and stars stay as Map Variant geometry (D7).
- **D1, files only.** The camera's AmplifyColor tonemapper and exposure, and the sun shafts' strength, aren't in any map file. They are per-Game constants, so they need a source. *Settled:* the capture plugin reads them once, and they are kept as Game data ([ADR 0010](../adr/0010-camera-settings-are-captured-once-as-game-data.md)).
- **ADR 0002's single UDIM lightmap image.** 1F mixes 2048² and 512² lightmaps, and directional lightmaps need a second image. Whether Blender's UDIMs handle tiles of mixed sizes well is for Phase 4 (in its roadmap row).

## Open questions

- The story game camera's `AmplifyColorEffect`, `GlobalFog` and `SunShafts` settings: Studio's camera replaces all three (below), so they need a capture from the story game.

## Settled by the look check (Phase 5)

Measured against Reference Captures taken in CharaStudio (`tools/capture.py`, `tools/look.py`), as the mean CIEDE2000 difference over 35 Capture Views of the three Golden Maps.

**The tolerances** (`tests/look/KK.json`). Each view is judged twice and must pass both:

| Pass | mean ΔE | p95 ΔE | worst tile | What it measures |
|---|---|---|---|---|
| Before the Grade | 3 | 10 | 25 % | The Builder's lighting: Blender with every Grade bypassed, against the capture's frame before AmplifyColor |
| After the Grade | 5 | 15 | 40 % | The finished look, looser because `Lut_Amount` is steep in the darks and magnifies any lighting error there |

Tiles are measured on an 8 × 8 grid, against a floor of 0.05 linear luminance. They were not fitted to what passes: at the time they were set, 1F passed every view, ground 5 of 15 (before the Grade) and park none, and each failing view points at a known error (ground's window glass, park's road). Phase 5 is done when every view passes both. Apart from passing, `tools/look.py` compares each view's numbers with the look snapshot (`tests/snapshots/look/KK.json`, per Blender build), so a change that makes a passing view worse is caught too; `--update-snapshot` records them after an intended change.

- **What Studio does with `SunLightInfo`.** It shows the Map's sun, sky domes and visibility, but replaces the rest with the Studio scene's own settings: its fog (`GlobalFog`, a post effect, off by default), its sun shafts (off by default) and its filter, `Lut_Amount` unless the user picks another, at every Time of Day. Applying `Lut_Amount` to the captured frame before AmplifyColor gives the captured frame to ΔE 0.7. Studio's camera has no tonemapper, exposure 1 and no dithering. These are its Camera Profile in `builder/games.py`.
- **The game camera's fog is a post effect.** KK's cameras carry `GlobalFog` (Standard Assets), which applies the RenderSettings fog to the depth buffer after the opaque pass and leaves the sky out. ADR 0021's fog in the material is checked only once the story game is captured.
- **1F's ambient is its Flat colour,** not the stale probe: the probe makes 1F worse (+0.2).
- **Shadow-only renderers keep the sun out of rooms,** and Unity's shadow pass culls as the material draws unless the renderer is `two_sided` (ADR 0024). 1F went from ΔE 26 to 1.5 in its worst view.
- **Reflections are blurred by roughness.** Unity samples the reflection cubemap at mip `r · (1.7 − 0.7 r) · 6` of perceptual roughness `r`; the Builder samples a chain of halved maps the same way. Sharp reflections were worse on every Map (−0.7 on 1F, −0.4 on ground, −0.3 on park).
- **The sun's soft shadow angle** (0.5° against 0°) changes no view by more than 0.13.
- **The lightmaps' RGB is sRGB-decoded,** as section 3 has it: leaving the decode out makes 1F's mean ΔE 8.1 instead of 2.4 (ground and park barely move). Every lightmap of the three Maps has `m_ColorSpace 1`.
- **park's `LightmapPrefab` entries or the renderers' own values** give the same frames (within 0.05), so section 4's rule stands untested there.
- **park's largest surfaces are lit at run time.** Its 8 lightmapped renderers (the roads `o_kouen_road_00`/`01`, the lawn `o_kouen_sibahu_00`, the lamps `o_kouen_gaitou_00`–`04`) all have Enlighten real-time GI (`m_LightmapIndexDynamic 0`), which adds the sun's bounce at run time and isn't in the files. The shaded road is 3× darker in Blender than in the capture (linear 0.024 against 0.073). Replacing their lightmap with the Map's ambient helps some views and hurts others, so the bounce lies between the two. The Builder adds half the ambient on top of their lightmap (ADR 0025): before the Grade, park's mean ΔE goes from 3.80 to 3.45 and its worst tile from 66 % to 38 % (shares 0.25, 0.75 and 1 do less well).
- **Grading blended surfaces one by one costs about 0.4 on park.** Studio's `Lut_Amount` is steep in the darks (sRGB 0.3 maps to nearly 0), so grading a blended decal such as `o_road_kage_*` and the road under it separately (ADR 0008) differs from grading the composited frame: 4.88 against 4.52 on park, under 0.03 on 1F and ground. It is the price of grading inside materials.
- **Anti-aliasing order doesn't matter:** one EEVEE sample instead of 32 makes every Map slightly worse.
