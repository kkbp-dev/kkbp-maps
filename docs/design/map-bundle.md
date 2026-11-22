# Map Bundle

The Map Bundle is the versioned contract between the Extractor and the Builder: the folder the Extractor writes for one Map, and the only thing the Builder reads. It follows KKBP's Export Bundle in style (JSON Schemas with `additionalProperties: false`, closed sets, a Manifest written last, a `major.minor` Schema Version), but not in format. Terms are in [CONTEXT.md](../../CONTEXT.md).

The contract itself, with the schemas, the closed sets and every rule the schemas can't express, is in [extension/kkbp_maps/bundle/](../../extension/kkbp_maps/bundle/README.md). This note says what it holds and why.

## Layout

```
manifest.json      written last: Game, Map, Schema Version, Extractor, options, sources, contents
map.json           Map metadata: Times of Day, lists, thumbnails, Camera Profile, geometry hash, what was skipped
scene.json         the nodes: tree, local transforms, renderers
meshes.json        one record per unique mesh
meshes/<hash>.bin  the mesh data
materials.json     materials by Raw Property, textures by Texture Role
textures.json      one record per texture, for every use
textures/<hash>.png|.exr
lightmaps.json     the Lightmap Sets
variants.json      the Map Variants: lights, ambient, fog, reflection, Sky, sun shafts, Grade, shown objects
assets.json        Prop and Structure Candidates with their Placements
```

Nothing else is in the folder. The Builder's own cache lives elsewhere.

## Decisions

- **One space** (ADR 0011). Everything is already in Blender's space; the Extractor converts from Unity in one module. Quaternions are `[w, x, y, z]`. Images are stored top row first, and UVs keep Unity's bottom-left origin, which is Blender's. A light shines along its local −Z. The sky's rotation is in degrees about +Z.
- **Content Hashes** (ADR 0012). Meshes, materials and textures are identified and named by Content Hash; nodes by integers in walk order. Prop and Structure Candidates carry a Merkle hash of their meshes, materials and relative transforms (D3), and the Map a hash of its whole node tree (D22).
- **Numbers.** Every float is a float32 value written as its shortest round-trip decimal, so files read well and hashes over them are stable. Colours are as the game serialized them; only decoded textures (lightmaps, cubemaps) hold converted values, and they say so through their colour space.
- **Meshes** are raw float32 and uint32 buffers, one file per unique mesh, with `position`, `normal`, `uv0` and `uv1` (ADR 0011). No tangents.
- **What the Extractor resolves.** The bundle holds what the game shows, not what it stores: Helpers are left out, the lightmap each renderer uses is resolved (kk-spike, section 4), submeshes and material slots are paired, sky domes become a Sky record, and Times of Day that light the Map the same are one Map Variant (ADR 0009).
- **What the Builder decides.** The Extractor proposes Candidates by the game's name prefixes; the Name Tables' overrides are applied by the Builder, so changing them needs no new extraction. English names are the Builder's too: the bundle keeps the game's names.
- **Map Variants.** Each lists the Times of Day it covers. Two Times of Day are one Map Variant when everything else in their records is equal, exactly. A Map without a Time of Day switch has one Map Variant covering all of its Game's Times of Day.
- **The Sky** of a Map Variant is its Sky Dome's cubemap (or the skybox where there is no dome) as an equirectangular EXR at rotation 0, with tint, exposure and rotation as values, and the dome's clouds or stars as nodes flagged `sky` (D7).
- **The Grade** names its LUT and layout. The settings of the camera it runs behind aren't in the bundle: `map.json` names a Camera Profile (`game` or `studio`), and the Builder finds that profile in the repository's Game data (ADR 0010).
- **Lightmap Sets** are a list, so a Map can have several. Each lists its lightmaps (the colour decoded from RGBM into linear EXR, D21; the direction re-encoded in Blender's world axes) and, per renderer, the lightmap index, scale-offset and UV set.
- **Version.** `0.2`, accepted only as an exact match until the first release (ADR 0014).
- **No Game Extensions.** Everything KK needs can be said without Game-specific fields. Later Games add set values and optional fields to the shared core.

## Later Games

Where each would go, without designing it here. Each is a Schema Version change.

| What | Where |
|---|---|
| KKS's and SVS's four Times of Day | a value in the Time of Day set |
| Realtime lights (KKS, SVS) | `lights` already holds point, spot and area lights with a mode |
| SVS's external Lightmap Sets, matched by name | more sets in `lightmaps.json`, one per Map Variant; the Extractor matches names to nodes. A shadowmask becomes an optional texture on a lightmap |
| KKS's PostProcessing and SVS's Volume Grades | new `kind`s in the Grade's union |
| KKS's SkyStudio skies | a new `kind` in the Sky's union |
| KKS's statically batched meshes | split by the Extractor; no change |
| SpeedTree | `color0` and `uv2` and up in the mesh attributes, and an optional `wind` on a renderer |
| KKS's shared dependency bundles | more `sources` in the Manifest |
| Light probes | an optional list in a Map Variant |

## The checker

`bundle/` never imports `bpy` and uses only the standard library and relative imports, so the Extractor, the Builder, the tests and the developer tools all use it.

```python
from bundle import check
problems = check(path)             # schemas and rules; [] when the bundle is valid
problems = check(path, deep=True)  # also re-hashes every mesh file
```

It validates the JSON Schemas with its own validator for the keywords they use (ADR 0013). `tools/check_bundle.py <bundle>...` runs a deep check from the command line. A reader that hands the Builder typed sections comes with the Builder (Phase 4).

## Testing

`tests/bundle_builder.py` writes small, valid Map Bundles into a temporary folder, with real PNG, EXR and mesh files, and the tests break them one rule at a time. A test checks that the validator agrees with `jsonschema` on all of them. Golden Maps get the same check from Phase 3.

```
../kkbp/importer/.venv/bin/python -I -m pytest tests
```
