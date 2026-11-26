# The Map Bundle contract

The contract between the Extractor and the Builder: the JSON Schemas in `schema/`, the closed sets in `schema/sets/`, and the rules below, which the schemas can't express. Why it looks this way is in [docs/design/map-bundle.md](../../../docs/design/map-bundle.md); terms are in [CONTEXT.md](../../../CONTEXT.md). The checker in this package checks all of it: `check(path)` returns every problem it finds, and `check(path, deep=True)` re-hashes the mesh files too.

| Bundle file | Schema |
|---|---|
| `manifest.json` | `manifest.schema.json` |
| `map.json` | `map.schema.json` |
| `scene.json` | `scene.schema.json` |
| `meshes.json` | `meshes.schema.json` |
| `materials.json` | `materials.schema.json` |
| `textures.json` | `textures.schema.json` |
| `lightmaps.json` | `lightmaps.schema.json` |
| `variants.json` | `variants.schema.json` |
| `assets.json` | `assets.schema.json` |

Every schema has an `$id` under `https://schemas.kkbp-maps.invalid/0.12/`. The host doesn't exist; the checker loads the files from this folder and resolves the relative `$ref`s. The schemas are strict (`additionalProperties: false`) and use only the keywords the checker's validator knows (ADR 0013).

## Schema Version

`major.minor`. While the major is 0, a Builder accepts only bundles of exactly its own version, and every contract change raises the minor (ADR 0014). From `1.0`, at the first release, a Builder accepts every bundle of its own major and ignores unknown fields; an additive change raises the minor and any other the major. Changing what a Content Hash covers is never additive. This is version `0.12`.

## Conventions

- **Files.** The bundle folder holds the nine data files, `meshes/<id>.bin` for each mesh and `textures/<id>.<format>` for each texture, and nothing else. All JSON is UTF-8 without a byte order mark. The Extractor writes `manifest.json` last; a folder without one is an unfinished bundle.
- **Numbers.** Every number with a fraction or an exponent is a float32 value written as its shortest decimal that reads back as the same float32 (`0.895`, not `0.8949999809265137`). No NaN or infinity.
- **Space** (ADR 0011). Every position, rotation, scale and direction is in Blender's space: right-handed, +Z up, metres. Quaternions are unit quaternions `[w, x, y, z]`. A light shines along its local −Z. UVs have their origin at the bottom left. Image files are stored top row first. Triangle winding is Blender's. The sky's rotation is in degrees about +Z.
- **Colours** are `[r, g, b, a]` as the game serialized them, with no colour space conversion. A texture's `color_space` says how its file's values are meant: `srgb` for sRGB-encoded colours that the game decodes when it samples them, `linear` for values used as stored. Normal maps are standard tangent-space maps, unpacked from Unity's DXT5nm, and `linear`. An EXR is always `linear`, half float, with ZIP compression (ZIP or ZIPS).
- **Ids.** Nodes are numbered by their position in `scene.json`. Meshes, materials and textures are identified by Content Hash (ADR 0012). Lightmap Sets have short ids of their own. A Map Variant's id is the first Time of Day it covers.
- **Ordered lists.** Lists of Times of Day and of mesh attributes keep their set's order and name each value once. `keywords` and `hidden` are sorted and name each value once.
- **Names** are the game's own. A mesh or material seen under several names keeps the first.

## Content Hashes

`H(x)` is the first 32 hex digits of the SHA-256 of `x`. `C(v)` is the canonical JSON of a value: keys sorted, no spaces (`json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`), every value the schema types as `number` written as a float (`1.0`, never `1`; `0.0`, never `-0.0`), and the integer fields as integers.

- **Mesh:** `H(file bytes)` of `meshes/<id>.bin`.
- **Texture:** `H(header + pixels)` of the full-size image, before any size limit (D21): `header` is `b"kkbp-maps texture\0"` followed by width, height and channel count as little-endian uint32, and `pixels` are the channel values the file holds, rows top first, interleaved per pixel in the order grey, alpha or R, G, B, A (one byte each for PNG, little-endian float16 for EXR). The checker doesn't re-hash textures.
- **Material:** `H(C({"shader", "keywords", "render_queue", "colors", "floats", "vectors", "textures"}))`, each as in `materials.json` but with `textures` holding only `raw`, `texture`, `offset` and `scale`, sorted by `raw`. Name, Blend Mode and double-sidedness are left out: the Extractor derives them from the rest.
- **Shape** of a node: `H(C({"mesh": m, "draws": d, "parts": p}))`, with `"shadows_only": true` added when its renderer only casts shadows. `m` is its renderer's mesh or null, `d` its renderer's draws as `[submesh, material]` pairs in order (or `[]`), and `p` the sorted placed hashes of its children, leaving out every child that is a sky node or the root of another Placement.
- **Placed** hash of a node: `H(C({"shape": s, "translation": t, "rotation": r, "scale": k}))`, its shape with its local transform.
- **Candidate:** the shape of each of its Placement roots. So a Candidate's hash depends on its meshes, materials and the transforms of its parts relative to its root, not on where it stands (D3).
- **Geometry hash** of the Map: `H(C({"roots": p}))`, `p` being the sorted placed hashes of the root nodes, this time leaving nothing out: sky nodes and nested Placements are part of the geometry.

## Texture Roles

The Extractor maps Raw Properties to Roles:

| Role | Raw Properties |
|---|---|
| `main` | `_MainTex`, `_BaseMap` |
| `normal` | `_BumpMap` |
| `occlusion` | `_OcclusionMap` |
| `metallic_gloss` | `_MetallicGlossMap` |
| `specular_gloss` | `_SpecGlossMap` |
| `emission` | `_EmissionMap` |
| `height` | `_ParallaxMap` |
| `detail_mask` | `_DetailMask` |
| `detail_main` | `_DetailAlbedoMap`, SpeedTree's `_DetailTex` |
| `detail_normal` | `_DetailNormalMap` |

Every other slot is known by its Raw Property only. Illusion's own shaders (KK's `Shader Forge/main_*`) get rows here as the Extractor learns their slots; a new row is no schema change, a new Role is.

## The AmplifyColor LUT

`amplify_32x32` is a 1024 × 32 linear PNG: 32 slices of 32 × 32 side by side. For a colour `(r, g, b)` in 0…1, sRGB-encoded as AmplifyColor sees it, `slice = b · 31` (two slices blended), the column is `r · 31 + 32 · slice` and the row is `g · 31` counted from the **bottom**, so PNG row `31 − g · 31`.

A Grade may carry a `blend`: a second LUT of the same layout and an amount. The Grade is then `(1 − amount) · lut(c) + amount · blend(c)`, as AmplifyColor does when its `BlendAmount` isn't 0 (KKS, kks-spike.md section 2).

## Rules the schemas can't express

### Manifest and files

- `schema_version` is the checker's own while the major is 0.
- `map` is `map.json`'s `key`.
- `contents` counts what the data files hold: nodes, meshes, materials, textures, Lightmap Sets, Map Variants, Candidates and Placements. `bytes` is the size of every file in the folder except `manifest.json`.
- Every file in the folder is a data file, a listed mesh's file or a listed texture's file.
- Each source `path` appears once.

### Map

- `thumbnails` cover only the Map's Times of Day, each at most once. A thumbnail is a PNG.
- Each `(list, no)` and each skip `reason` appears once.
- `geometry_hash` is the Map's geometry hash.

### Nodes

- A node's `id` is its position in the list, and its parent, if any, comes before it.
- Every rotation is a unit quaternion (within 1e-3), and no scale component is 0.
- A renderer's `mesh` and every draw's `material` exist, and each draw's `submesh` is one its mesh has.
- Every child of a sky node is a sky node.
- A renderer's `wind` is an index into `winds`, and every wind is used. A wind's `flags` are sorted. Wind is how the game moves a tree; it isn't part of any Content Hash.

### Meshes

- `attributes` start with `position` and `normal`. `uv0_zw` needs `uv0` and `uv1_zw` needs `uv1`.
- The mesh file is exactly as long as its record says: `4 · vertices ·` the sum of each attribute's floats (position, normal 3; color0, uv2, uv3 4; uv0, uv0_zw, uv1, uv1_zw 2) bytes of attributes, then `4 ·` the sum of `index_counts` bytes of indices. Every index count is a multiple of 3.
- Deep check only: the file's hash is the mesh's `id`, and every index is below `vertices`.
- A `batched` mesh was split out of a static batch (ADR 0034). Two meshes **match** when one of them is `batched`, they have the same vertex count, attributes, `uv0` and indices exactly, and every position and normal component lies within 1e-4 of the other's. The Extractor gives every batched mesh that matches an earlier mesh of the same Map that mesh, so no two meshes of a bundle match; the Builder treats matching meshes of different Maps as one.

### Textures

- Each texture's file exists, its PNG or EXR header gives the record's width and height, and an EXR is `linear`, half float, ZIP-compressed. A PNG is 8-bit grey, grey and alpha, RGB or RGBA, not interlaced.

### Materials

- A material's `id` is its Content Hash.
- Each `raw` and each `role` appears at most once per material.
- Every texture it names exists.

### Use

- Every mesh, material and texture is used by something: a renderer, a material, a Lightmap Set, a Map Variant or a thumbnail.
- Every Lightmap Set is used by at least one Map Variant.

### Lightmap Sets

- Set ids are unique, and so are lightmap `index`es within a set.
- A `color` is an EXR; a `direction` is a `linear` PNG of the same size as its colour.
- A renderer's `realtime_gi` says the game adds Enlighten's real-time GI to it at run time. The bounced light isn't carried; the Builder approximates it (ADR 0025).
- Each assignment names a node with a renderer that isn't a sky node, at most once per set, and a lightmap of its set. `uv` 1 needs a mesh with `uv1`; `uv` 0 needs one with `uv0`.

### Map Variants

- Every Time of Day in `map.json` is covered by exactly one Map Variant, and a Map Variant covers no other. Its `id` is the first Time of Day it covers.
- No two Map Variants are equal: two whose records are the same in everything but `id` and `times_of_day` must be one (ADR 0009). Equal means equal canonical JSON, compared exactly.
- `hidden` nodes exist. `lightmap_set` names a set that exists.
- A Sky's `geometry` names sky nodes that the Map Variant doesn't hide. Every sky node with a renderer is under the `geometry` of at least one Map Variant.
- A light lights a renderer only where the renderer's `layer` is in the light's `culling_mask` (bit `layer`). How many lights a renderer takes per pixel is the Game's, by the lights' `render_mode`; the bundle doesn't say.
- A renderer's `reflection_probes` is Unity's reflection probe usage. A renderer that is `off` takes only its Map Variant's own reflection (its `texture`, or none), never a probe (ADR 0026).
- A Sky's cubemap, a reflection's texture and every probe's texture are EXRs. A `material` Sky's keywords are sorted, each of its texture slots appears once, and its textures exist; a cubemap among them is an equirectangular EXR like the others. A reflection's texture is null only where the game holds no cubemap for its source. A Grade's `lut` is a `linear` PNG of 1024 × 32, and so is its `blend`'s.
- A fog's `camera` and a sun shafts record's settings beyond `color` are what the Map sets on the camera's effects at that Time of Day. Where they are absent the Camera Profile's apply; where present they replace the Camera Profile's switches and values of the same name, and the camera still draws them only if the Camera Profile says it has the effect.
- A Grade's `blend` mixes a second LUT's result into the first's: `(1 − amount) · lut(c) + amount · blend(c)`, both looked up as the AmplifyColor LUT section says. It is left out where the amount is 0.

### Candidates and Placements

- A Candidate's `hash` appears once, and its `kind` follows its `rule`: `p_prefix` is a `prop`, every other rule a `structure`.
- A Placement root is a node that isn't a sky node and roots one Placement only.
- No Placement root lies inside a Prop's Placement, and no Structure's Placement root lies inside another Structure's Placement. So a Prop may stand inside a Structure, and nothing else nests.
- Every renderer that isn't on a sky node belongs to a Placement: it is a Placement root or lies under one. A `shadows_only` renderer may instead belong to none: it is then drawn only in the Map's Variants, as the hidden caster that keeps the sun out of a room (ADR 0024).
- Every Placement root's shape is its Candidate's `hash`.
